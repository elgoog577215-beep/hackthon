"""Read existing working handouts into the shared frozen evidence contract."""
from copy import deepcopy

from course_document import stable_hash
from course_knowledge_context import build_knowledge_generation_context, documents_from_text_sources


def handout_sources(raw, state, lesson_id=""):
    titles = {s['section_id']: s.get('title', '') for s in (raw.get('course_document') or {}).get('sections', [])}
    lessons, sources = [], []
    for lid, lesson in state.get('lessons', {}).items():
        if lesson_id and lid != lesson_id:
            continue
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


def handout_context(raw, state, lesson_id=""):
    lessons, sources = handout_sources(raw, state, lesson_id)
    if lesson_id and not lessons:
        from course_repository import CourseDocumentConflict
        raise CourseDocumentConflict("本讲没有可用的已保存讲义，请先生成本讲讲义")
    course = deepcopy(raw)
    # Tree extraction observes saved handouts, not old upload caches or sample facts.
    for key in ('evidence_package', 'evidence_catalog', 'course_knowledge_scope_contract'):
        course.pop(key, None)
    if lesson_id:
        course.pop('course_plan', None)
        course.pop('course_outline', None)
    course['generation_stage_artifacts'] = {}
    course['parsed_documents'], course['material_bindings'] = documents_from_text_sources(raw['course_id'], sources)
    course['knowledge_scope_units'] = [{'node_id': l['lesson_id'], 'title': l['title']} for l in lessons]
    context = build_knowledge_generation_context(course)
    context['source_mode'] = 'handouts'
    if lesson_id:
        context['scope_lesson_id'] = lesson_id
        context['cross_lesson_alignment_contract'] = 'per_point_relations_v3'
        context['reference_knowledge'] = [{'key': f'E{i}', **{k: deepcopy(point.get(k)) for k in ('knowledge_id', 'revision_id', 'name', 'statement', 'conditions', 'knowledge_type', 'meta_question', 'meta_answer', 'section_refs')}}
            for i, point in enumerate((raw.get('course_knowledge_base') or {}).get('knowledge_points', []), 1)
            if (point.get('section_refs') or [point.get('topic')])
            and any(point.get('section_refs') or [point.get('topic')])
            and lesson_id not in (point.get('section_refs') or [point.get('topic')])]
        ref_keys = {p['knowledge_id']: p['key'] for p in context['reference_knowledge']}
        previous = raw.get('course_knowledge_base') or {}
        titles = {s['section_id']: s.get('title', '') for s in (raw.get('course_document') or {}).get('sections', [])}
        context['reference_lessons'] = [{'lesson_id': lid, 'title': titles.get(lid, lid),
            'knowledge_keys': [p['key'] for p in context['reference_knowledge'] if lid in (p.get('section_refs') or [])]}
            for lid in dict.fromkeys(lid for p in context['reference_knowledge'] for lid in (p.get('section_refs') or []))]
        context['reference_relations'] = [{'source_key': ref_keys[r['source_id']], 'target_key': ref_keys[r['target_id']], 'type': r['type'], 'reason': r.get('reason', ''), 'conditions': r.get('conditions', [])}
            for r in previous.get('relations', []) if r.get('source_id') in ref_keys and r.get('target_id') in ref_keys]
        categories = {c['id']: c for c in previous.get('categories', [])}
        needed = set()
        for point in previous.get('knowledge_points', []):
            if point['knowledge_id'] not in ref_keys:
                continue
            parent = point.get('parent_id')
            while parent in categories and parent not in needed:
                needed.add(parent)
                parent = categories[parent].get('parent_id')
        context['reference_categories'] = [{'id': c['id'], 'name': c['name'], 'parent_id': c.get('parent_id'), 'knowledge_keys': [ref_keys[p['knowledge_id']] for p in previous.get('knowledge_points', []) if p['knowledge_id'] in ref_keys and p.get('parent_id') == c['id']]}
            for c in previous.get('categories', []) if c['id'] in needed]

    context['handout_lessons'] = lessons
    context['handout_source_refs'] = {s['id']: s['handout_ref'] for s in sources}
    context['material_coverage']['source_mode'] = 'generated_course_handouts'
    context['policy']['handouts_are_generated_content_not_independent_evidence'] = True
    context['revision_id'] = stable_hash({k: v for k, v in context.items() if k != 'revision_id'}, prefix='kgctx_')
    return context


def merge_lesson_tree(existing, candidate, lesson_id):
    """Replace one lecture's membership; retain other lectures and stable IDs."""
    result = deepcopy(candidate)
    old_points = {p['knowledge_id']: p for p in existing.get('knowledge_points', [])}
    def scopes(point):
        return point.get('section_refs') or ([point['topic']] if point.get('topic') else [])
    retained = {}
    for kid, original in old_points.items():
        if lesson_id not in scopes(original):
            retained[kid] = deepcopy(original)
        elif other := [lid for lid in scopes(original) if lid != lesson_id]:
            point = deepcopy(original)
            point['section_refs'] = other
            point['topic'] = other[0]
            point['source_quotes'] = [q for q in point.get('source_quotes', []) if (q.get('handout_ref') or {}).get('lesson_id') != lesson_id]
            point['source_refs'] = list(dict.fromkeys(q['evidence_id'] for q in point['source_quotes']))
            retained[kid] = point
    for point in candidate['knowledge_points']:
        kid = point['knowledge_id']
        if kid not in retained:
            retained[kid] = deepcopy(point)
            continue
        shared = retained[kid]
        shared['section_refs'] = list(dict.fromkeys([*scopes(shared), *scopes(point)]))
        for quote in point.get('source_quotes', []):
            if quote not in shared.setdefault('source_quotes', []): shared['source_quotes'].append(deepcopy(quote))
        shared['source_refs'] = list(dict.fromkeys([*shared.get('source_refs', []), *point.get('source_refs', [])]))
        # Only lecture/source bindings changed; keep the existing semantic revision.
    result['knowledge_points'] = list(retained.values())
    result['terminology_revision'] = stable_hash(sorted((kid, p['name']) for kid, p in retained.items()), prefix='term_')
    categories = {c['id']: deepcopy(c) for c in existing.get('categories', [])}
    categories.update({c['id']: deepcopy(c) for c in candidate['categories']})
    needed = set()
    for point in retained.values():
        parent = point.get('parent_id')
        while parent in categories and parent not in needed:
            needed.add(parent); parent = categories[parent].get('parent_id')
    result['categories'] = [c for cid, c in categories.items() if cid in needed]
    result['concept_groups'] = [{**c, 'concept_group_id': c['id']} for c in result['categories']]
    edges = {}
    for edge in existing.get('relations', []):
        a, b = edge['source_id'], edge['target_id']
        if a not in retained or b not in retained: continue
        if edge.get('scope_lesson_id') == lesson_id: continue
        if not edge.get('scope_lesson_id') and all(set(scopes(old_points.get(k, {}))) == {lesson_id} for k in [a, b]): continue
        edges[edge['id']] = deepcopy(edge)
    for edge in candidate['relations']:
        if edge['source_id'] not in retained or edge['target_id'] not in retained:
            from course_repository import CourseDocumentConflict
            raise CourseDocumentConflict('关联的元知识已不在课程中，请显式复用本讲需要保留的知识')
        edges[edge['id']] = {**deepcopy(edge), 'scope_lesson_id': lesson_id}
    adjacency = {}
    for edge in edges.values():
        if edge['type'] == 'prerequisite': adjacency.setdefault(edge['source_id'], []).append(edge['target_id'])
    seen, visiting = set(), set()
    def visit(node):
        if node in visiting:
            from course_repository import CourseDocumentConflict
            raise CourseDocumentConflict('跨讲先修关系存在环，候选未采用')
        if node in seen: return
        visiting.add(node)
        for target in adjacency.get(node, []): visit(target)
        visiting.remove(node); seen.add(node)
    for node in adjacency: visit(node)
    result['relations'] = list(edges.values())
    from knowledge_relations import relation_index
    result['relation_index'] = relation_index(result)
    lessons = {l['topic']: deepcopy(l) for l in existing.get('lessons', [])}
    lessons.update({l['topic']: deepcopy(l) for l in candidate['lessons']})
    result['lessons'] = list(lessons.values())
    sources = {s['evidence_id']: deepcopy(s) for s in existing.get('sources', [])}
    sources.update({s['evidence_id']: deepcopy(s) for s in candidate['sources']})
    result['sources'] = list(sources.values())
    handouts = {s['lesson_id']: deepcopy(s) for s in existing.get('source_handouts', [])}
    handouts.update({s['lesson_id']: deepcopy(s) for s in candidate.get('source_handouts', [])})
    result['source_handouts'] = list(handouts.values())
    result['lesson_revisions'] = {**existing.get('lesson_revisions', {}), lesson_id: candidate['revision_id']}
    result['scope_lesson_id'] = lesson_id
    result['base_knowledge_revision'] = existing.get('revision_id', '')
    result['provenance'] = '按讲次更新知识树；其他讲沿用已采用内容，关联建议待审阅'
    result['revision_id'] = stable_hash({k: v for k, v in result.items() if k != 'revision_id'}, prefix='kb_')
    return result


def knowledge_facts(point):
    return {**{key: point.get(key) for key in ('knowledge_id', 'name', 'statement', 'conditions', 'knowledge_type', 'meta_question', 'meta_answer')},
            **{key: deepcopy(point[key]) for key in ('symbol_definitions', 'teaching_context', 'examples') if key in point}}


def lesson_fingerprint(tree, lesson_id):
    points = [p for p in tree.get('knowledge_points', []) if lesson_id in (p.get('section_refs') or [p.get('topic')])]
    ids = {p['knowledge_id'] for p in points}
    categories = {c['id']: c for c in tree.get('categories', [])}; groups = set()
    for point in points:
        parent = point.get('parent_id')
        while parent in categories and parent not in groups:
            groups.add(parent); parent = categories[parent].get('parent_id')
    relations = [r for r in tree.get('relations', []) if r.get('scope_lesson_id') == lesson_id or (not r.get('scope_lesson_id') and r['source_id'] in ids and r['target_id'] in ids)]
    return stable_hash({'points': sorted([{**knowledge_facts(p), 'parent_id': p.get('parent_id')} for p in points], key=lambda p: p['knowledge_id']),
        'categories': [categories[cid] for cid in sorted(groups)], 'relations': sorted(relations, key=lambda r: r['id'])}, prefix='klf_')


def handout_input_signature(context):
    # Other lecture adoption may change the reference catalog, not this input.
    reference_keys = {'revision_id', 'knowledge_revision', 'terminology_revision', 'reference_knowledge', 'reference_relations', 'reference_categories', 'reference_lessons', 'cross_lesson_alignment_contract'}
    return stable_hash({k: v for k, v in context.items() if k not in reference_keys}, prefix='kls_')


def slice_lesson_tree(tree, lesson_id):
    result = deepcopy(tree)
    result['knowledge_points'] = [p for p in result['knowledge_points'] if lesson_id in (p.get('section_refs') or [p.get('topic')])]
    for point in result['knowledge_points']:
        point['section_refs'] = [lesson_id]; point['topic'] = lesson_id
        point['source_quotes'] = [q for q in point.get('source_quotes', []) if (q.get('handout_ref') or {}).get('lesson_id') == lesson_id]
        point['source_refs'] = list(dict.fromkeys(q['evidence_id'] for q in point['source_quotes']))
    result['relations'] = [r for r in result['relations'] if r.get('scope_lesson_id') == lesson_id]
    result['lessons'] = [l for l in result['lessons'] if l['topic'] == lesson_id]
    result['source_handouts'] = [l for l in result.get('source_handouts', []) if l['lesson_id'] == lesson_id]
    evidence_ids = {eid for p in result['knowledge_points'] for eid in p['source_refs']}
    result['sources'] = [s for s in result.get('sources', []) if s['evidence_id'] in evidence_ids]
    return result


def visible_handout_tree(tree, document, handouts):
    """Project an adopted tree onto disclosed, still-matching handout blocks."""
    visible = {b['block_id'] for b in document.get('blocks', [])}
    result = deepcopy(tree)
    # Inventory review can include unpublished source fragments and retired identities.
    for field in ('knowledge_inventory', 'inventory_source_coverage', 'identity_changes', 'atomic_assessment', 'relation_assessment',
                  'semantic_equivalence','knowledge_coverage','content_review_summary'):
        result.pop(field, None)
    def included(point):
        quotes = point.get('source_quotes') or []
        if any(not q.get('handout_ref') for q in quotes):
            return any(ref.get('knowledge_id') == point['knowledge_id'] and ref.get('revision_id') == point.get('revision_id')
                for block in document.get('blocks', []) for ref in (block.get('payload') or {}).get('knowledge_refs', []))
        return bool(quotes) and all(
            (ref := quote.get('handout_ref') or {}).get('block_id') in visible
            and (handouts.get(ref.get('lesson_id')) or {}).get('revision_id') == ref.get('script_revision_id')
            for quote in quotes)
    result['knowledge_points'] = [p for p in result['knowledge_points'] if included(p)]
    for point in result['knowledge_points']:
        for field in ('inventory_attachments', 'inventory_keys', 'generation_batch_id', 'content_review', 'semantic_equivalents',
                      'check_records','semantic_review','truth_review','identity_members','identity_decisions'):
            point.pop(field, None)
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
    from knowledge_relations import relation_index
    result['relation_index'] = relation_index(result)
    return result
