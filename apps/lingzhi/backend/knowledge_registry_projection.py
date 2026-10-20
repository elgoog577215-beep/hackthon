"""Compile reviewed knowledge into the existing course tree and material reader."""
from collections import defaultdict
from copy import deepcopy

from course_document import stable_hash
from generic_knowledge import input_revision, sources
from handout_knowledge import knowledge_facts, merge_lesson_tree
from knowledge_registry_contract import CONTRACT, FIELDS
from knowledge_relations import relation_index


def material_records(context, keys):
    available = sources(context)
    records = []
    for key in dict.fromkeys(keys):
        unit = available.get(key)
        if unit is None:
            raise ValueError('程序材料记录引用未知输入键')
        record = {'evidence_id': unit['evidence_id'], 'quote': unit['source_text'],
                  'locator': deepcopy(unit['locator']), 'source_kind': 'generation_input',
                  'quote_scope': 'input_material', 'provenance_kind': 'generation_input'}
        refs = context.get('handout_source_refs', {})
        ref = next((refs[bid] for bid in unit.get('block_ids', []) if bid in refs), None)
        if ref:
            record['handout_ref'] = deepcopy(ref)
        records.append(record)
    return records


def build_tree(raw, context, pipeline, job_id, *, hierarchy=None, preview=False):
    registry = pipeline.get('registry') or {'points': [
        point for batch in pipeline['inventory_batches'] for point in batch.get('points', [])], 'issues': []}
    points = []
    lesson_id = context['scope_lesson_id']
    root = {'id': stable_hash({'course': raw['course_id'], 'lesson': lesson_id}, prefix='kg_'),
            'name': context['handout_lessons'][0]['title'], 'parent_id': None}
    names = pipeline.get('names', {}).get('result', {})
    issues = deepcopy(registry.get('issues', []))
    by_name = defaultdict(list)
    key_map = {}
    for index, candidate in enumerate(registry['points'], 1):
        old = candidate.get('_registered_point')
        kid = candidate.get('knowledge_id') or stable_hash(
            {'course': raw['course_id'], 'job': job_id, 'candidate': candidate['key']}, prefix='kp_')
        row = names.get(candidate['key'], {})
        name = old.get('name') if old else row.get('name', candidate['statement'])
        question = old.get('meta_question') if old else row.get('meta_question', '请解释：' + candidate['statement'])
        point = deepcopy(old) if old else {}
        point.update(id=kid, knowledge_id=kid, key=f'K{index}', name=name, meta_question=question,
                     meta_answer=old.get('meta_answer', candidate['statement']) if old else candidate['statement'],
                     statement=candidate['statement'], conditions=deepcopy(candidate.get('conditions', [])),
                     knowledge_type=candidate.get('knowledge_type', 'rule'), parent_id=root['id'],
                     primary_concept_group_id=root['id'], section_refs=[lesson_id], topic=lesson_id,
                     granularity_status='candidate', verification_status='model_reviewed_semantics_pending',
                     provenance_contract='input_material_record_v1',
                     identity_members=deepcopy(candidate.get('identity_members', [])),
                     identity_decisions=deepcopy(candidate.get('identity_decisions', [])),
                     review_pending=candidate.get('review_pending', False))
        for field in ('symbol_definitions', 'teaching_context', 'examples'):
            if not old or field in old:
                point[field] = deepcopy(candidate.get(field, []))
        point['source_quotes'] = material_records(context, candidate['input_material_keys'])
        point['source_refs'] = list(dict.fromkeys(q['evidence_id'] for q in point['source_quotes']))
        point.setdefault('aliases', [])
        point['revision_id'] = old.get('revision_id') if old and old.get('revision_id') else stable_hash(knowledge_facts(point), prefix='kpv_')
        point['content_review'] = {'contract': CONTRACT, 'semantics_verified': False,
                                   'decisions': deepcopy(candidate.get('identity_decisions', []))}
        points.append(point)
        key_map[candidate['key']] = point['key']
        by_name[name].append(point['key'])
        if not preview and (name.rstrip().endswith(('？', '?')) or len(name) > 100):
            issues.append({'code': 'display_name_review', 'severity': 'review',
                           'point_key': point['key'], 'message': '短名称需要确认表达'})
    for issue in issues:
        issue['point_key'] = key_map.get(issue.get('point_key'), issue.get('point_key'))
    for name, keys in by_name.items():
        if len(keys) > 1:
            issues.append({'code': 'display_name_collision', 'severity': 'review',
                           'point_keys': keys, 'message': '不同知识暂用相同名称：' + name})
    categories = [root]
    if hierarchy:
        from knowledge_hierarchy import apply_hierarchy
        categories, points = apply_hierarchy(hierarchy, points)
    units = sources(context)
    tree = {'schema_version': 'course_knowledge_base_v2', 'tree_schema': 'knowledge_first_generic_v1',
            'status': 'candidate', 'categories': categories, 'knowledge_points': points, 'relations': [],
            'concept_groups': [{**c, 'concept_group_id': c['id']} for c in categories],
            'lessons': [{'topic': lesson_id, 'title': root['name'], 'knowledge_ids': [p['knowledge_id'] for p in points]}],
            'misconceptions': [], 'skill_units': [], 'bindings': [], 'mastery_criteria': [],
            'source_mode': 'handouts', 'source_contract': 'input_material_record_v1',
            'provenance_contract': 'input_material_record_v1', 'generation_contract': CONTRACT,
            'source_handouts': deepcopy(context['handout_lessons']),
            'source_unit_contract': context.get('source_unit_contract'),
            'source_evidence_package_revision': context['evidence_package']['package_revision_id'],
            'source_input_revision': input_revision(raw, context),
            'sources': [{'evidence_id': u['evidence_id'], 'locator': deepcopy(u['locator'])} for u in units.values()],
            'uncovered_evidence_ids': [], 'gaps': [], 'gap_records': [],
            'scope': '本讲知识候选', 'provenance': '记录生成使用的材料；未执行内容来源校验',
            'atomic_assessment': {'schema_version': CONTRACT, 'ready_for_adoption': not preview and
                not any(i['severity'] == 'blocking' for i in issues), 'semantics_verified': False,
                'issues': issues, 'source_issues': [], 'uncovered_passages': [], 'relation_status': 'not_run',
                'inventory_count': len(points)},
            'terminology_revision': stable_hash([p['name'] for p in points], prefix='term_')}
    tree['revision_id'] = stable_hash(tree, prefix='kb_')
    existing = raw.get('course_knowledge_base') or {}
    result = merge_lesson_tree(existing, tree, lesson_id)
    current_ids = {p['knowledge_id'] for p in points}
    old_points = [p for p in existing.get('knowledge_points', []) if lesson_id in p.get('section_refs', [])]
    result['identity_changes'] = {'retired_points': [
        {k: p.get(k) for k in ('knowledge_id', 'revision_id', 'name', 'statement')}
        for p in old_points if p['knowledge_id'] not in current_ids],
        'new_ids': sorted(current_ids - {p['knowledge_id'] for p in existing.get('knowledge_points', [])})}
    result['relation_index'] = relation_index(result)
    if preview:
        result.update(generation_preview=True, generation_job_id=job_id)
    return result
