"""Versioned navigation labels on the course envelope, outside semantic hashes.

Canonical trees and completed authoring jobs stay immutable. A label is bound to
one knowledge ID AND semantic revision; it never silently follows a new claim.
"""
from copy import deepcopy

from course_document import stable_hash
from course_errors import CourseDocumentConflict

CONTRACT = 'knowledge_presentation_v1'


def _require(condition, message):
    if not condition:
        raise CourseDocumentConflict(message)


def present_tree(tree, presentation):
    if not tree:
        return tree
    result = deepcopy(tree)
    records = (presentation or {}).get('labels', {})
    for point in result.get('knowledge_points', []):
        record = records.get(point.get('knowledge_id'), {}).get(point.get('revision_id'))
        if record:
            point['display_name'] = record['name']
            point['display_aliases'] = deepcopy(record.get('previous_names', []))
    result['presentation_revision'] = (presentation or {}).get('revision_id', '')
    return result


def present_view(view, presentation):
    result = deepcopy(view)
    for key in ('tree', 'candidate'):
        result[key] = present_tree(result.get(key), presentation)
    result['history'] = [present_tree(tree, presentation) for tree in result.get('history', [])]
    for key in ('candidates', 'generation_previews'):
        for record in result.get(key, []):
            record['tree'] = present_tree(record.get('tree'), presentation)
    result['presentation_revision'] = (presentation or {}).get('revision_id', '')
    return result


def update_presentation(svc, course_id, *, actor, command_id, expected_document,
                        expected_knowledge, expected_presentation, tree_revision, labels):
    """Atomic, exact-scope command; no tree, source, question or learner writes."""
    _require(isinstance(command_id, str) and 0 < len(command_id) <= 100, '修改标识无效')
    _require(isinstance(labels, list) and 0 < len(labels) <= 240, '请选择要修改的知识名称')
    seen = set()
    for row in labels:
        _require(isinstance(row, dict) and set(row) == {'knowledge_id', 'knowledge_revision', 'name'},
                 '名称修改不能包含知识正文或其他字段')
        _require(all(isinstance(v, str) and v.strip() and len(v) <= 200 for v in row.values()), '知识名称或引用无效')
        _require(row['knowledge_id'] not in seen, '知识引用重复')
        seen.add(row['knowledge_id'])
    fingerprint = stable_hash({'document': expected_document, 'knowledge': expected_knowledge,
                              'presentation': expected_presentation, 'tree': tree_revision, 'labels': labels}, prefix='kdisp_req_')
    receipt = {}
    with svc.authoring._course_lock(course_id):
        state = svc.authoring.load(course_id)

        def update(raw):
            _require(raw.get('owner_id') == actor, '课程不存在或无权限')
            previous = raw.get('knowledge_presentation') or {}
            saved = (previous.get('receipts') or {}).get(command_id)
            if saved:
                _require(saved['request_fingerprint'] == fingerprint, '修改标识已用于其他内容')
                receipt.update(saved)
                return raw
            _require(not any(j.get('status') in {'pending', 'running'} for j in state['jobs'].values()),
                     '课程已有运行任务，请完成后再修改名称')
            _require(raw.get('course_document_revision') == expected_document
                     and (raw.get('course_knowledge_base') or {}).get('revision_id', '') == expected_knowledge,
                     '课程或知识版本已变化，请刷新')
            _require(previous.get('revision_id', '') == expected_presentation, '知识名称已变化，请刷新')
            targets = [raw.get('course_knowledge_base') or {}]
            targets += [j['checkpoint']['candidate'] for j in state['jobs'].values()
                        if j.get('type') == 'course_knowledge_tree_generation' and j.get('status') == 'completed'
                        and (j.get('checkpoint') or {}).get('candidate')]
            tree = next((t for t in targets if t.get('revision_id') == tree_revision), None)
            _require(tree is not None, '目标知识树已变化或不存在')
            points = {p['knowledge_id']: p for p in tree.get('knowledge_points', [])}
            records = deepcopy(previous.get('labels', {}))
            changes = []
            for row in labels:
                kid, revision, name = row['knowledge_id'], row['knowledge_revision'], row['name'].strip()
                point = points.get(kid)
                _require(point is not None and point.get('revision_id') == revision, '知识引用或语义版本已变化')
                old = records.setdefault(kid, {}).get(revision, {})
                old_name = old.get('name') or point['name']
                aliases = list(old.get('previous_names', []))
                if old.get('name') and old_name != name and old_name not in aliases:
                    aliases.append(old_name)
                records[kid][revision] = {'name': name, 'previous_names': aliases}
                changes.append({**row, 'name': name, 'previous_name': old_name})
            revision = stable_hash(records, prefix='kdisp_')
            receipt.update(command_id=command_id, request_fingerprint=fingerprint,
                           presentation_revision=revision, previous_revision=previous.get('revision_id', ''),
                           tree_revision=tree_revision, changes=changes, actor=actor)
            raw['knowledge_presentation'] = {'schema_version': CONTRACT, 'revision_id': revision, 'labels': records,
                'receipts': {**previous.get('receipts', {}), command_id: deepcopy(receipt)}}
            return raw

        svc.storage.update_course_data(course_id, update)
    return receipt
