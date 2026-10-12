"""Read existing working handouts into the shared frozen evidence contract."""
from copy import deepcopy

from course_document import stable_hash
from course_knowledge_context import build_knowledge_generation_context, documents_from_text_sources


def handout_sources(raw, state):
    titles = {s['section_id']: s.get('title', '') for s in (raw.get('course_document') or {}).get('sections', [])}
    lessons, sources = [], []
    for lid, lesson in state.get('lessons', {}).items():
        rid = lesson.get('working_script_revision_id')
        revision = next((r for r in lesson.get('script_revisions', []) if r.get('revision_id') == rid), None)
        if not revision:
            continue
        start = len(sources)
        for section in revision.get('sections', []):
            for block in section.get('blocks', []):
                content = str(block.get('content') or '').strip()
                if not content or block.get('status', 'completed') not in {'completed', 'complete', 'ready'}:
                    continue
                ref = {'lesson_id': lid, 'script_revision_id': rid,
                       'section_id': section.get('section_node_id'), 'block_id': block.get('block_id')}
                sources.append({'id': stable_hash(ref, prefix='hs_'), 'scope_id': lid, 'text': content,
                    'provenance': 'generated_course_handout', 'handout_ref': ref})
        if len(sources) > start:
            lessons.append({'key': lid, 'lesson_id': lid, 'title': titles.get(lid) or lesson.get('title') or lid,
                'script_revision_id': rid, 'block_count': len(sources) - start})
    return lessons, sources


def handout_context(raw, state):
    lessons, sources = handout_sources(raw, state)
    course = deepcopy(raw)
    # Tree extraction observes saved handouts, not old upload caches or sample facts.
    for key in ('evidence_package', 'evidence_catalog', 'course_knowledge_scope_contract'):
        course.pop(key, None)
    course['generation_stage_artifacts'] = {}
    course['parsed_documents'], course['material_bindings'] = documents_from_text_sources(raw['course_id'], sources)
    course['knowledge_scope_units'] = [{'node_id': l['lesson_id'], 'title': l['title']} for l in lessons]
    context = build_knowledge_generation_context(course)
    context['source_mode'] = 'handouts'
    context['handout_lessons'] = lessons
    context['handout_source_refs'] = {s['id']: s['handout_ref'] for s in sources}
    context['material_coverage']['source_mode'] = 'generated_course_handouts'
    context['policy']['handouts_are_generated_content_not_independent_evidence'] = True
    context['revision_id'] = stable_hash({k: v for k, v in context.items() if k != 'revision_id'}, prefix='kgctx_')
    return context


def visible_handout_tree(tree, document, handouts):
    """Project an adopted tree onto disclosed, still-matching handout blocks."""
    visible = {b['block_id'] for b in document.get('blocks', [])}
    result = deepcopy(tree)
    def included(point):
        quotes = point.get('source_quotes') or []
        return bool(quotes) and all(
            (ref := quote.get('handout_ref') or {}).get('block_id') in visible
            and (handouts.get(ref.get('lesson_id')) or {}).get('revision_id') == ref.get('script_revision_id')
            for quote in quotes)
    result['knowledge_points'] = [p for p in result['knowledge_points'] if included(p)]
    point_ids = {p['knowledge_id'] for p in result['knowledge_points']}
    groups = {c['id']: c for c in result['categories']}
    keep = set()
    for point in result['knowledge_points']:
        cid = point.get('parent_id')
        while cid in groups and cid not in keep:
            keep.add(cid); cid = groups[cid].get('parent_id')
    result['categories'] = [c for c in result['categories'] if c['id'] in keep]
    result['concept_groups'] = [c for c in result['concept_groups'] if c['id'] in keep]
    result['relations'] = [r for r in result['relations'] if r['source_id'] in point_ids and r['target_id'] in point_ids]
    lesson_ids = {lid for p in result['knowledge_points'] for lid in p.get('section_refs', [])}
    evidence_ids = {eid for p in result['knowledge_points'] for eid in p.get('source_refs', [])}
    result['lessons'] = [{**l, 'knowledge_ids': [k for k in l['knowledge_ids'] if k in point_ids]} for l in result['lessons'] if l['topic'] in lesson_ids]
    result['source_handouts'] = [s for s in result.get('source_handouts', []) if s['lesson_id'] in lesson_ids]
    result['sources'] = [s for s in result.get('sources', []) if s['evidence_id'] in evidence_ids]
    result.update(gaps=[], gap_records=[], uncovered_evidence_ids=[], projection_scope='visible_handout_blocks')
    return result
