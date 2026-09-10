from copy import deepcopy

import pytest

from backend.tests.test_partial_course_change import make_partial_plan
from backend.tests.test_teacher_course_change import context
from course_evolution import CourseEvolutionRepository
from course_evolution.partial_review import require_partial_operations
from course_evolution.teacher_execution import _selected_migrations
from course_evolution.teacher_planning import create_teacher_course_change_plan, review_teacher_course_change_scope


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
    assert saved.impact_summary['scope_review']['selection_only'] is True
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
    selected = next_plan.impact_summary['scope_review']['selected_migration_ids']
    assert len(selected) == 1
    assert next(m for m in next_plan.teacher_change_planning.unit_migrations if m.migration_id == selected[0]).source_unit_ids == migration.source_unit_ids


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
