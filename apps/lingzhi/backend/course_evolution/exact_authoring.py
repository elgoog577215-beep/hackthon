"""Route approved projected text edits to the existing teacher handout owner."""
from copy import deepcopy
from typing import Any


from .content_patches import EXACT_AUTHORING_ACTION as ACTION


def _source(authoring: dict[str, Any], operation: Any, course_data: dict[str, Any]):
    from teacher_content_projection import project_teacher_content
    projected = project_teacher_content(course_data, authoring=authoring)
    current_block = next((b for b in projected.get('course_document', {}).get('blocks', []) if b.get('block_id') == operation.target_block_id), None)
    if not current_block or current_block.get('internal_revision') != operation.payload.get('expected_block_revision'):
        raise ValueError('这条讲义内容已经变化，请重新核对修改建议')
    matches = []
    for lesson_id, lesson in (authoring.get('lessons') or {}).items():
        revision = next((r for r in lesson.get('script_revisions') or [] if r.get('revision_id') == lesson.get('working_script_revision_id')), None)
        if not revision:
            continue
        for section in revision.get('sections') or []:
            if str(section.get('section_node_id') or '') != operation.target_section_id:
                continue
            for block in section.get('blocks') or []:
                if block.get('block_id') == operation.target_block_id:
                    matches.append((lesson_id, lesson, revision, section, block))
    if len(matches) != 1:
        raise ValueError('无法唯一定位这条正文对应的教师讲义，请重新分析')
    lesson_id, lesson, revision, section, block = matches[0]
    before = (operation.payload.get('before_block') or {}).get('payload') or {}
    after = (operation.payload.get('proposed_block') or {}).get('payload') or {}
    if lesson.get('source_state', 'current') != 'current' or revision.get('source_lesson_plan_revision_id') != lesson.get('working_revision_id'):
        raise ValueError('本讲教案来源已变化，请更新讲义后再应用')
    original = str(before.get('markdown') or before.get('text') or before.get('content') or '').replace('\r\n', '\n').strip()
    if original != str(block.get('content') or '').replace('\r\n', '\n').strip():
        raise ValueError('讲义正文已经变化，请重新核对修改建议')
    changed = {key for key in set(before) | set(after) if before.get(key) != after.get(key)}
    if 'title' in changed:
        raise ValueError('讲内标题必须与教案一致，请保留原标题后再修改正文，或先修改教案')
    if not changed.issubset({'markdown', 'text', 'content', 'title', 'knowledge_names'}):
        raise ValueError('请在讲义正文或标题中修改内容，派生摘要不能单独写入')
    replacement = deepcopy(block)
    for field in changed:
        if field in {'markdown', 'text', 'content'}:
            replacement['content'] = str(after.get(field) or '')
            replacement.pop('summary', None)
        else:
            if before.get(field) != block.get(field):
                raise ValueError('讲义字段已经变化，请重新核对修改建议')
            replacement[field] = deepcopy(after.get(field))
    return lesson_id, revision, section, replacement


def route_exact_operations(*, course_data, user_id, change_set_id, operation_ids, evolution_repository, authoring_repository):
    if course_data.get('teacher_production_schema') != 'unified_teacher_v1':
        return
    from .partial_review import require_partial_operations
    from .content_patches import require_current_patch_preview
    course_id = str(course_data['course_id'])
    state = evolution_repository.load(user_id, course_id)
    plan = next(p for p in state.change_sets if p.change_set_id == change_set_id)
    if plan.status != 'pending':
        return
    require_partial_operations(plan, operation_ids)
    require_current_patch_preview(plan, operation_ids)
    chosen = set(operation_ids if operation_ids is not None else [op.operation_id for op in plan.operations])
    authoring = authoring_repository.load(course_id)
    routes = {}
    for operation in plan.operations:
        if operation.operation_id not in chosen or operation.operation_type != 'REPLACE_COURSE_BLOCK':
            continue
        lesson_id, revision, _, _ = _source(authoring, operation, course_data)
        if any(other.operation_id in chosen and other.operation_type == 'APPLY_DOMAIN_CANDIDATE'
               and other.payload.get('lesson_unit_id') == lesson_id and other.payload.get('domain') in {'lesson_plan', 'script'}
               and other.payload.get('action') != ACTION for other in plan.operations):
            raise ValueError('同一讲次同时选择了正文和整讲修改，请先保留一套建议再应用，避免相互覆盖')
        routes[operation.operation_id] = (deepcopy(operation.payload), lesson_id, revision['revision_id'])
    if not routes:
        return
    def update(current):
        target = next(p for p in current.change_sets if p.change_set_id == change_set_id)
        if target.status != 'pending' or target.review_revision != plan.review_revision:
            raise ValueError('方案已变化，请重新打开修改建议')
        for op in target.operations:
            if op.operation_id in routes:
                previous, lesson_id, revision_id = routes[op.operation_id]
                if op.payload != previous:
                    raise ValueError('修改建议已变化，请重新核对')
                op.operation_type = 'APPLY_DOMAIN_CANDIDATE'
                op.payload.update(domain='script', action=ACTION, lesson_unit_id=lesson_id,
                                  base_revision_id=revision_id, previous_revision_id=revision_id)
        return current
    evolution_repository.update(user_id, course_id, update)


def prepare_exact_candidate(*, operation, plan, course_id, course_data, repository):
    lesson_id, revision, section, replacement = _source(repository.load(course_id), operation, course_data)
    candidate_id = operation.payload.get('candidate_id')
    candidate = repository.script_ai_candidate(course_id, lesson_id, candidate_id) if candidate_id else None
    if not (candidate and candidate.get('status') == 'pending' and candidate.get('base_revision_id') == revision['revision_id']
            and candidate.get('candidate_group_id') == f'{plan.change_set_id}:{operation.operation_id}'
            and candidate.get('block_replacements') == {operation.target_block_id: replacement}):
        candidate = repository.save_script_ai_candidate(course_id, lesson_id,
            base_revision_id=revision['revision_id'], section_node_id=section['section_node_id'], instruction=plan.request_text,
            replacement_text=str(replacement.get('content') or ''), block_replacements={operation.target_block_id: replacement},
            source_lesson_plan_revision_id=revision['source_lesson_plan_revision_id'],
            candidate_group_id=f'{plan.change_set_id}:{operation.operation_id}')
    operation.payload.update(candidate_id=candidate['candidate_id'], base_revision_id=revision['revision_id'], previous_revision_id=revision['revision_id'])
    return candidate
