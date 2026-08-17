"""G-1 baseline: real generation on CURRENT HEAD, measure relation type distribution.

Why this exists: every stored blueprint in the repo predates the Aug 10-12
six-type prompt fix (latest stored = 2026-07-23). So the brief's "65 relations,
all prerequisite" is a pre-fix number and cannot be used as the baseline for
this round. This script produces a post-fix measurement.

Captures per-section raw model output AND assembled output in the SAME run
(cross-run subtraction is meaningless — model output varies per call).

Usage (from backend/, credentials sourced):
    .venv/bin/python ../scripts/g1_baseline.py
Writes /tmp/kb-gen/g1_baseline.json
"""
import asyncio, json, os, sys, uuid, time, collections
sys.path.insert(0, '.')

import course_teaching_plan_v3 as tp
import course_service as cs
from course_service import CourseService

OUT = os.environ.get('G1_OUT', '/tmp/kb-gen/g1_baseline.json')
REQ = os.environ.get('G1_REQ', '/tmp/kb-gen/req.json')

raw_by_node = collections.defaultdict(list)   # node_id -> [ [relation dicts], ... ] per call
assembled_by_node = {}                        # node_id -> [relation dicts]
state = {'stages': [], 'model': os.environ.get('AI_MODEL')}
T0 = time.time()


def dump():
    json.dump(state, open(OUT, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=2, default=str)


def mark(name, **kw):
    state['stages'].append({'stage': name, 't': round(time.time() - T0, 1), **kw})
    print(f"[{state['stages'][-1]['t']:>7}s] {name} {kw}", flush=True)
    dump()


_norm = tp.normalize_teaching_plan_batch_v3
def spy_norm(payload, **kw):
    for s in (payload or {}).get('sections') or []:
        if isinstance(s, dict):
            rels = [r for r in (s.get('knowledge_relations') or []) if isinstance(r, dict)]
            raw_by_node[str(s.get('node_id'))].append(rels)
    return _norm(payload, **kw)


_asm = tp.assemble_course_teaching_plan_v3
def spy_asm(**kw):
    out = _asm(**kw)
    for s in out.get('sections') or []:
        assembled_by_node[str(s.get('node_id'))] = [
            r for r in (s.get('knowledge_relations') or []) if isinstance(r, dict)
        ]
    return out


for mod in (tp, cs):
    if hasattr(mod, 'normalize_teaching_plan_batch_v3'):
        mod.normalize_teaching_plan_batch_v3 = spy_norm
    if hasattr(mod, 'assemble_course_teaching_plan_v3'):
        mod.assemble_course_teaching_plan_v3 = spy_asm


def counts(rels):
    return dict(collections.Counter(str(r.get('relation_type') or '?') for r in rels))


async def main():
    svc = CourseService()
    req = json.load(open(REQ))
    cid = str(uuid.uuid4())
    mark('start', course_id=cid, req=os.path.basename(REQ))
    course = None
    try:
        course = await svc.build_course_draft(
            course_id=cid, topic=req['subject'],
            target_audience=req['target_audience'], depth='intermediate',
            requirements=req['requirements'], course_type='systematic',
            teacher_course_brief=req['teacher_course_brief'],
        )
        mark('draft_done', nodes=len(course.get('nodes') or []))
    except Exception as e:
        mark('build_interrupted', error=str(e)[:300])

    # Raw model output (last call per node) vs assembled.
    raw_last = {n: v[-1] for n, v in raw_by_node.items() if v}
    raw_all = [r for rels in raw_last.values() for r in rels]
    asm_all = [r for rels in assembled_by_node.values() for r in rels]

    state['per_section'] = {
        n: {
            'calls': [len(c) for c in raw_by_node.get(n, [])],
            'raw_last_n': len(raw_last.get(n, [])),
            'raw_last_types': counts(raw_last.get(n, [])),
            'assembled_n': len(assembled_by_node.get(n, [])),
            'assembled_types': counts(assembled_by_node.get(n, [])),
        }
        for n in sorted(set(raw_by_node) | set(assembled_by_node))
    }
    state['raw_total'] = {'n': len(raw_all), 'types': counts(raw_all), 'distinct': len(counts(raw_all))}
    state['assembled_total'] = {'n': len(asm_all), 'types': counts(asm_all), 'distinct': len(counts(asm_all))}

    if course:
        kb = course.get('course_knowledge_base') or {}
        kb_rels = [r for r in (kb.get('relations') or []) if isinstance(r, dict)]
        state['compiled_kb'] = {
            'points': len(kb.get('knowledge_points') or []),
            'n': len(kb_rels), 'types': counts(kb_rels), 'distinct': len(counts(kb_rels)),
        }
        state['course'] = course

    dump()
    print('\n=== RAW (model output, last call per node) ===', flush=True)
    print(f"  n={state['raw_total']['n']} distinct={state['raw_total']['distinct']} {state['raw_total']['types']}", flush=True)
    print('=== ASSEMBLED ===', flush=True)
    print(f"  n={state['assembled_total']['n']} distinct={state['assembled_total']['distinct']} {state['assembled_total']['types']}", flush=True)
    if course:
        print('=== COMPILED KB ===', flush=True)
        print(f"  n={state['compiled_kb']['n']} distinct={state['compiled_kb']['distinct']} {state['compiled_kb']['types']}", flush=True)
    print(f'\nwrote {OUT}', flush=True)

asyncio.run(main())
