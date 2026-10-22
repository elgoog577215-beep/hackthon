"""Compile reviewed knowledge into the existing course tree and material reader."""
from collections import defaultdict
from copy import deepcopy
from knowledge_short_names import cached_name, meaning_key, CONTRACT as PREVIEW_NAME_CONTRACT

from course_document import stable_hash
from generic_knowledge import input_revision, sources
from handout_knowledge import merge_lesson_tree
from knowledge_registry_contract import CONTRACT
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
    projected_candidates = []
    for index, candidate in enumerate(registry['points'], 1):
        old = candidate.get('_registered_point')
        kid = candidate.get('knowledge_id') or stable_hash(
            {'course': raw['course_id'], 'job': pipeline.get('identity_job_id',job_id), 'candidate': candidate['key']}, prefix='kp_')
        row = names.get(candidate['key']) or cached_name(pipeline, candidate) or {}
        name = old.get('name') if old else row.get('name')
        if not name:
            if preview:
                continue  # Unnamed content is saved, but is not a navigation leaf yet.
            raise ValueError('知识点缺少短知识名')
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
        for field in ('coverage_unit_ids','profile_focus','check_intents','semantic_review','truth_review','check_records'):
            if field in candidate:
                point[field]=deepcopy(candidate[field])
        point['source_quotes'] = material_records(context, candidate['input_material_keys'])
        point['source_refs'] = list(dict.fromkeys(q['evidence_id'] for q in point['source_quotes']))
        point.setdefault('aliases', [])
        meaning = meaning_key(point)
        frozen = pipeline.setdefault('point_revisions', {}).get(kid, {})
        if old and old.get('revision_id'):
            point['revision_id'] = old['revision_id']
        elif frozen.get('meaning') == meaning and frozen.get('revision_id'):
            point['revision_id'] = frozen['revision_id']
        else:
            point['revision_id'] = stable_hash({'knowledge_id': kid, 'meaning': meaning}, prefix='kpv_')
        pipeline['point_revisions'][kid] = {'meaning': meaning, 'revision_id': point['revision_id']}
        for check in point.get('check_records',[]):
            check.update(knowledge_id=kid,knowledge_revision=point['revision_id'],
                check_id=stable_hash({'knowledge':kid,'candidate':check['candidate_key'],'intent':check['check_intent']},prefix='kcheck_'))
        point['content_review'] = {'contract': CONTRACT, 'semantics_verified': False,
                                   'decisions': deepcopy(candidate.get('identity_decisions', []))}
        points.append(point)
        projected_candidates.append(candidate)
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
            'semantic_revision_contract': 'knowledge_meaning_revision_v1',
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
    current_by_id = {p['knowledge_id']:p for p in points}
    for point in result['knowledge_points']:
        if point['knowledge_id'] in current_by_id:
            for field in ('coverage_unit_ids','profile_focus','check_intents','check_records'):
                if field in current_by_id[point['knowledge_id']]:
                    point[field] = deepcopy(current_by_id[point['knowledge_id']][field])
    frozen_units=pipeline.get('frozen_units',pipeline.get('coverage_review',pipeline.get('coverage_plan',{})).get('units',[]))
    if frozen_units:
        from knowledge_coverage import coverage_report
        review_batches = pipeline.get('semantic_review', {}).get('batches', [])
        resolutions = [*pipeline.get('extraction_resolutions',[]),
            *[r for b in review_batches if b.get('status')=='completed' for r in b['result']['resolutions']]]
        by_candidate={candidate['key']:point['knowledge_id'] for candidate,point in zip(projected_candidates,points)}
        resolutions.extend({**deepcopy(r),'knowledge_id':by_candidate[r['target_key']]} for r in registry.get('check_resolutions',[]) if r['target_key'] in by_candidate)
        report=coverage_report(frozen_units,points,resolutions if review_batches or 'extraction_resolutions' in pipeline else None)
        result['knowledge_coverage']={**report,'units':deepcopy(frozen_units),'plan_origin':pipeline.get('plan_origin','model_planned')}
        if review_batches:
            records = [r for b in review_batches if b.get('status')=='completed' for r in b['result']['reviews']]
            result['content_review_summary'] = {'contract':pipeline['semantic_review'].get('contract','knowledge_semantic_review_v1'),
                'reviewed_count':len(records), 'non_knowledge_count':len(resolutions),
                'split_count':sum(len(r['conclusions'])>1 for r in records),
                'refuted_count':sum(r['challenge']['result']=='refuted' for r in records),
                'semantics_verified':False}
        if report['missing_unit_ids'] and not preview:
            result['atomic_assessment']['ready_for_adoption']=False
            result['atomic_assessment']['issues'].append({'code':'knowledge_coverage_gap','severity':'blocking',
                'message':'知识清单仍有未承载项：'+','.join(report['missing_unit_ids'])})
    current_ids = {p['knowledge_id'] for p in points}
    old_points = [p for p in existing.get('knowledge_points', []) if lesson_id in p.get('section_refs', [])]
    result['identity_changes'] = {'retired_points': [
        {k: p.get(k) for k in ('knowledge_id', 'revision_id', 'name', 'statement')}
        for p in old_points if p['knowledge_id'] not in current_ids],
        'new_ids': sorted(current_ids - {p['knowledge_id'] for p in existing.get('knowledge_points', [])})}
    result['relation_index'] = relation_index(result)
    if preview:
        result.update(generation_preview=True, generation_job_id=job_id, preview_naming_contract=PREVIEW_NAME_CONTRACT)
    return result
