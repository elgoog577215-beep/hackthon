"""G-2 acceptance: real generation WITH uploaded material, measure source landing rate.

Why a materials-backed run is required: `_source_grounding` derives every count
from `source_refs`, which only exist when the course has an evidence package.
A run with no materials structurally reports 0 forever — that is the honest
value, not a bug. So the landing rate can only be lifted off 0 by a run that
actually has material to bind against.

Usage (from backend/, credentials sourced):
    .venv/bin/python ../scripts/g2_source_binding.py
Writes /tmp/kb-gen/g2_binding.json
"""
import asyncio, json, os, sys, uuid, time, collections
sys.path.insert(0, '.')

from course_generation.service import CourseService
import course_knowledge_base as ckb
import course_generation.service as cs
import course_teaching_plan_v3 as tp
import evidence_package as evp

OUT = os.environ.get('G2_OUT', '/tmp/kb-gen/g2_binding.json')
REQ = os.environ.get('G2_REQ', '/tmp/kb-gen/req.json')
MATERIAL = os.environ.get('G2_MATERIAL', '/tmp/kb-gen/material_ac_dc.md')

# Generation reliably stops at the content-stage quality gate, which is AFTER the
# teaching plan is assembled but BEFORE compile_course_knowledge_base ever runs.
# A first attempt spied only on the compiler and captured nothing (compile_calls=0).
# So capture the two real inputs the measurement actually needs — the frozen
# evidence package and the assembled sections — and compile them here.
captured = {'package': None, 'sections': {}, 'kb': None, 'course_data': None}

_freeze = evp.freeze_evidence_package


def spy_freeze(**kw):
    pkg = _freeze(**kw)
    captured['package'] = pkg.model_dump(mode='json')
    return pkg


_asm = tp.assemble_course_teaching_plan_v3


def spy_asm(**kw):
    out = _asm(**kw)
    for s in out.get('sections') or []:
        if isinstance(s, dict) and s.get('knowledge_structure'):
            # Keyed by node_id so a retry replaces rather than duplicates.
            captured['sections'][str(s.get('node_id'))] = s
    return out


_compile = ckb.compile_course_knowledge_base


def spy_compile(course_data, **kw):
    out = _compile(course_data, **kw)
    if (out or {}).get('knowledge_points'):
        captured['kb'] = out
        captured['course_data'] = course_data
    return out


evp.freeze_evidence_package = spy_freeze
for mod in (cs,):
    if hasattr(mod, 'freeze_evidence_package'):
        mod.freeze_evidence_package = spy_freeze
for mod in (tp, cs):
    if hasattr(mod, 'assemble_course_teaching_plan_v3'):
        mod.assemble_course_teaching_plan_v3 = spy_asm
for mod in (ckb, cs):
    if hasattr(mod, 'compile_course_knowledge_base'):
        mod.compile_course_knowledge_base = spy_compile

state = {'stages': [], 'model': os.environ.get('AI_MODEL')}
T0 = time.time()


def dump():
    json.dump(state, open(OUT, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=2, default=str)


def mark(name, **kw):
    state['stages'].append({'stage': name, 't': round(time.time() - T0, 1), **kw})
    print(f"[{state['stages'][-1]['t']:>7}s] {name} {kw}", flush=True)
    dump()


async def main():
    svc = CourseService()
    req = json.load(open(REQ))
    content = open(MATERIAL, encoding='utf-8').read()
    cid = str(uuid.uuid4())
    mark('start', course_id=cid, material_chars=len(content))

    course = None
    try:
        course = await svc.build_course_draft(
            course_id=cid, topic=req['subject'],
            target_audience=req['target_audience'], depth='intermediate',
            requirements=req['requirements'], course_type='systematic',
            teacher_course_brief=req['teacher_course_brief'],
            materials=[{
                'filename': 'ac_dc_textbook.md',
                'content': content,
                'usage': 'content_source',
                'importance': 'core',
                'user_description': '交流电与直流电教学资料',
            }],
            grounding_strategy='material_first',
        )
        mark('draft_done', nodes=len(course.get('nodes') or []))
    except Exception as e:
        mark('build_interrupted', error=str(e)[:300])

    kb = (course or {}).get('course_knowledge_base') or captured['kb'] or {}
    source_course = course or captured['course_data'] or {}
    if not kb:
        # Compile from what the run actually produced. Same compiler, same
        # frozen package — only the surrounding pipeline is missing.
        sections = list(captured['sections'].values())
        if not (sections and captured['package']):
            mark('nothing_to_measure',
                 sections=len(sections), package=bool(captured['package']))
            return
        source_course = {
            'course_id': cid,
            'evidence_package': captured['package'],
            'nodes': [
                {**s, 'node_level': 2, 'node_type': 'section',
                 'node_name': s.get('title') or s.get('node_name') or s.get('node_id')}
                for s in sections
            ],
        }
        kb = _compile(source_course)
        mark('compiled_locally', sections=len(sections),
             points=len(kb.get('knowledge_points') or []))
    mark('measuring', from_returned_course=bool(course))

    points = [p for p in (kb.get('knowledge_points') or []) if isinstance(p, dict)]
    total = len(points)
    bound = [p for p in points if p.get('source_bindings')]
    by_origin = collections.Counter(
        str(b.get('origin') or '?')
        for p in points for b in (p.get('source_bindings') or [])
    )
    status = collections.Counter(
        str(p.get('source_status') or '') for p in points
    )

    state['evidence'] = {
        'package_revision_id': (source_course.get('evidence_package') or {}).get('package_revision_id'),
        'evidence_units': len((source_course.get('evidence_package') or {}).get('units') or []),
        'evidence_catalog': len(source_course.get('evidence_catalog') or []),
        'material_bindings': len(source_course.get('material_bindings') or []),
    }
    state['landing'] = {
        'knowledge_point_count': total,
        'point_bound_count': len(bound),
        'point_binding_ratio': round(len(bound) / total, 4) if total else 0.0,
        'binding_origins': dict(by_origin),
        'source_status_counts': dict(status),
    }
    state['bound_examples'] = [
        {'name': p.get('name'), 'bindings': p.get('source_bindings')}
        for p in bound[:5]
    ]
    state['unbound_names'] = [p.get('name') for p in points if not p.get('source_bindings')]

    view = source_course.get('course_knowledge_library') or {}
    if not view:
        # Not attached yet when generation stopped early — project it here so the
        # denominator and the per-point detail come from the same compile.
        view = ckb.build_course_knowledge_library_view(kb, {}, {}, course_data=source_course)
    state['view_source_grounding'] = view.get('source_grounding') or {}

    rels = [r for r in (kb.get('relations') or []) if isinstance(r, dict)]
    state['relations'] = {
        'n': len(rels),
        'types': dict(collections.Counter(str(r.get('relation_type') or '?') for r in rels)),
    }
    state['course'] = source_course
    dump()

    print('\n=== G-2 SOURCE LANDING ===', flush=True)
    print(f"  evidence units      : {state['evidence']['evidence_units']}", flush=True)
    print(f"  knowledge points    : {total}   <- denominator", flush=True)
    print(f"  points with binding : {len(bound)}", flush=True)
    print(f"  landing ratio       : {state['landing']['point_binding_ratio']}", flush=True)
    print(f"  binding origins     : {dict(by_origin)}", flush=True)
    print(f"  source_status       : {dict(status)}", flush=True)
    print(f"  view grounding      : {state['view_source_grounding']}", flush=True)
    print(f"\n=== relations === n={state['relations']['n']} {state['relations']['types']}", flush=True)
    print(f'\nwrote {OUT}', flush=True)

asyncio.run(main())
