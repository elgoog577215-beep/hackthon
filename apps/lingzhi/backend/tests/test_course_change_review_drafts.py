from copy import deepcopy

import pytest

from backend.tests.test_partial_course_change import make_partial_plan
from backend.tests.test_teacher_course_change import context
from course_evolution import CourseEvolutionRepository
from course_evolution.partial_review import require_partial_operations
from course_evolution.partial_review import readiness
from course_evolution.teacher_execution import _selected_migrations
from course_evolution.teacher_planning import create_teacher_course_change_plan, review_teacher_course_change_scope


@pytest.mark.asyncio
async def test_exact_current_block_edit_can_proceed_while_unrelated_decisions_wait(tmp_path):
    from course_evolution.change_planning import CourseStructureOperation
    repo, _, plan, _ = await make_partial_plan(tmp_path)
    state = repo.load('teacher', 'course-1')
    target = state.change_sets[0]
    target.teacher_change_planning.intent.blocking_questions = ['确认其他章节的实践项目形式']
    target.teacher_change_planning.intent.can_proceed_without_clarification = False
    target.teacher_change_planning.structural_operations = [CourseStructureOperation(operation_id='tree',
        operation_type='REBUILD_OUTLINE', source_node_ids=['c1'], base_blueprint_revision_id='r', idempotency_key='tree', reason='待确认的结构建议',
        proposed_nodes=[{'provisional_id': 'new-c1', 'title': '新讲次', 'parent_ref': 'root', 'source_node_ids': ['c1']}])]
    repo.save(state)
    migration = target.teacher_change_planning.unit_migrations[0]
    result = review_teacher_course_change_scope(repository=repo, user_id='teacher', course_id='course-1',
        change_set_id=plan.change_set_id, selected_migration_ids=[migration.migration_id])
    reviewed = result.change_sets[0]
    require_partial_operations(reviewed, [migration.metadata['operation_id']])
    assert reviewed.teacher_change_planning.status == 'blocked'
    assert reviewed.teacher_change_planning.intent.blocking_questions
    assert [m.migration_id for m in _selected_migrations(reviewed)] == [migration.migration_id]


def test_patch_compiler_preserves_explicit_literal_replacements_and_rejects_conflicts():
    from course_evolution.content_patches import compile_patches
    body, _, _ = compile_patches({'markdown': 'A A'}, [{'field': 'markdown', 'before': 'A', 'after': 'A\n\nB', 'replace_all': True}], literal=True)
    assert body['markdown'].count('B') == 2
    with pytest.raises(ValueError, match='重叠'):
        compile_patches({'markdown': 'ABC'}, [
            {'field': 'markdown', 'before': 'AB', 'after': 'X'},
            {'field': 'markdown', 'before': 'BC', 'after': 'Y'},
        ])


@pytest.mark.asyncio
async def test_waiting_scope_can_be_saved_without_authorizing_execution(tmp_path):
    repo, ctx, plan, missing = await make_partial_plan(tmp_path)
    state = repo.load('teacher', 'course-1')
    state.change_sets[0].teacher_change_planning.intent.blocking_questions = ['确认项目范围']
    state.change_sets[0].teacher_change_planning.intent.can_proceed_without_clarification = False
    repo.save(state)
    migration = plan.teacher_change_planning.unit_migrations[0]
    result = review_teacher_course_change_scope(repository=repo, user_id='teacher', course_id='course-1',
        change_set_id=plan.change_set_id, selected_migration_ids=[migration.migration_id], selection_only=True)
    saved = result.change_sets[-1]
    assert saved.impact_summary['scope_selection']['selected_migration_ids'] == [migration.migration_id]
    assert saved.teacher_change_planning.status == 'blocked'
    assert saved.selected_operation_ids == []
    with pytest.raises(ValueError):
        _selected_migrations(saved)
    with pytest.raises(ValueError):
        require_partial_operations(saved, [migration.metadata['operation_id']])
    async def analyze(*args):
        return {'affected_units': [], 'structure': {'required': False}}
    continued = await create_teacher_course_change_plan(context=ctx, user_id='teacher', request_id='selection-retry',
        instruction=plan.request_text, repository=repo, analyzer=analyze, supersedes_plan_id=plan.change_set_id,
        rescan_incomplete_only=True)
    next_plan = continued.change_sets[-1]
    selected = next_plan.impact_summary['scope_selection']['selected_migration_ids']
    assert len(selected) == 1
    assert next(m for m in next_plan.teacher_change_planning.unit_migrations if m.migration_id == selected[0]).source_unit_ids == migration.source_unit_ids


@pytest.mark.asyncio
async def test_title_dependency_can_be_resolved_in_a_draft_without_approving_application(tmp_path):
    repo, _, _, _ = await make_partial_plan(tmp_path)
    state = repo.load('teacher', 'course-1')
    plan = state.change_sets[0]
    migration = plan.teacher_change_planning.unit_migrations[0]
    operation = plan.operations[0]
    original_title = operation.payload['before_block']['payload']['title']
    operation.payload['proposed_block']['payload']['title'] = '新项目标题'
    migration.metadata['manually_edited'] = True
    repo.save(state)
    gate = readiness(plan)
    assert gate['waiting'][migration.migration_id] == 'title_dependency'
    assert migration.migration_id in gate['editable_migration_ids']
    updated = review_teacher_course_change_scope(repository=repo, user_id='teacher', course_id='course-1',
        change_set_id=plan.change_set_id, selected_migration_ids=[migration.migration_id], selection_only=True,
        manual_content_edits={migration.migration_id: {'/title': original_title}}).change_sets[0]
    assert migration.migration_id in readiness(updated)['eligible_migration_ids']
    assert not updated.impact_summary.get('scope_review')
    with pytest.raises(ValueError):
        require_partial_operations(updated, [operation.operation_id])


async def patch_plan(tmp_path, patches, *, body=None, mirrors=False):
    ctx = context()
    unit = next(u for u in ctx.units if u.asset_type == 'course_content')
    if body is not None:
        unit.metadata['course_block']['payload']['markdown'] = body
    if mirrors:
        payload = unit.metadata['course_block']['payload']
        payload['feedback_structure'] = {'sections': [{'markdown': payload['markdown']}]}
    ctx.units = [unit]
    async def analyze(*args):
        return {
            'signal_kind': 'semantic', 'structure': {'required': False},
            'affected_units': [{'unit_id': unit.unit_id, 'disposition': 'rewrite_partial', 'content_patches': patches}],
        }
    result = await create_teacher_course_change_plan(context=ctx, user_id='teacher', request_id='patch-test',
        instruction='补充实践项目', repository=CourseEvolutionRepository(tmp_path), analyzer=analyze)
    return result.change_sets[-1]


@pytest.mark.asyncio
async def test_overlapping_scan_patches_do_not_insert_the_same_project_twice(tmp_path):
    patch = {'field': 'markdown', 'before': '受力图', 'after': '受力图\n\n实践项目：测量加速度', 'replace_all': False}
    plan = await patch_plan(tmp_path, [patch, deepcopy(patch)])
    assert plan.operations[0].payload['proposed_block']['payload']['markdown'].count('实践项目') == 1


@pytest.mark.asyncio
async def test_repeated_source_anchor_does_not_duplicate_semantic_expansion(tmp_path):
    patch = {'field': 'markdown', 'before': '原始说明', 'after': '原始说明\n\n实践项目：测量加速度', 'replace_all': True}
    plan = await patch_plan(tmp_path, [patch], body='原始说明\n\n其他知识\n\n原始说明')
    body = plan.operations[0].payload['proposed_block']['payload']['markdown']
    assert body.count('实践项目') == 1
    assert body.count('原始说明') == 2


@pytest.mark.asyncio
async def test_body_preview_does_not_concatenate_structured_mirrors(tmp_path):
    patch = {'field': 'markdown', 'before': '受力图', 'after': '自由体图', 'replace_all': True}
    plan = await patch_plan(tmp_path, [patch], mirrors=True)
    migration = plan.teacher_change_planning.unit_migrations[0]
    assert migration.metadata['after_content'] == plan.operations[0].payload['proposed_block']['payload']['markdown']


@pytest.mark.asyncio
async def test_old_duplicate_candidates_are_repaired_before_review_but_manual_edits_are_kept(tmp_path):
    from course_evolution.content_patches import refresh_exact_candidates, require_current_patch_preview
    patch = {'field': 'markdown', 'before': '原始说明', 'after': '原始说明\n\n实践项目：测量加速度', 'replace_all': True}
    plan = await patch_plan(tmp_path, [patch], body='原始说明\n\n其他知识\n\n原始说明')
    operation = plan.operations[0]
    operation.payload['content_patches'] = [patch]
    operation.payload['proposed_block']['payload']['markdown'] = operation.payload['before_block']['payload']['markdown'].replace(patch['before'], patch['after'])
    with pytest.raises(ValueError, match='重复插入'):
        require_current_patch_preview(plan, [operation.operation_id])
    migration = plan.teacher_change_planning.unit_migrations[0]
    refresh_exact_candidates(plan, [migration.migration_id])
    assert operation.payload['proposed_block']['payload']['markdown'].count('实践项目') == 1
    require_current_patch_preview(plan, [operation.operation_id])
    operation.payload['proposed_block']['payload']['markdown'] = '教师保留的两段\n\n教师保留的两段'
    migration.metadata['manually_edited'] = True
    refresh_exact_candidates(plan, [migration.migration_id])
    require_current_patch_preview(plan, [operation.operation_id])
    assert operation.payload['proposed_block']['payload']['markdown'].count('教师保留') == 2


@pytest.mark.asyncio
async def test_repairing_a_saved_choice_invalidates_previous_application_approval(tmp_path):
    patch = {'field': 'markdown', 'before': '原始说明', 'after': '原始说明\n\n实践项目', 'replace_all': True}
    plan = await patch_plan(tmp_path, [patch], body='原始说明\n\n原始说明')
    repo = CourseEvolutionRepository(tmp_path)
    state = repo.load('teacher', 'course-1')
    plan = state.change_sets[-1]
    operation = plan.operations[0]
    migration = plan.teacher_change_planning.unit_migrations[0]
    operation.payload['content_patches'] = [patch]
    operation.payload['proposed_block']['payload']['markdown'] = '原始说明\n\n实践项目\n\n原始说明\n\n实践项目'
    plan.impact_summary['scope_review'] = {'selected_operation_ids': [operation.operation_id], 'selected_migration_ids': [migration.migration_id]}
    plan.selected_operation_ids = [operation.operation_id]
    repo.save(state)
    updated = review_teacher_course_change_scope(repository=repo, user_id='teacher', course_id='course-1',
        change_set_id=plan.change_set_id, selected_migration_ids=[migration.migration_id], selection_only=True).change_sets[-1]
    assert updated.operations[0].payload['proposed_block']['payload']['markdown'].count('实践项目') == 1
    assert updated.impact_summary['scope_review']['selected_operation_ids'] == []
    assert updated.selected_operation_ids == []
