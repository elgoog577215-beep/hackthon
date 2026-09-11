from copy import deepcopy

import pytest

from backend.tests.test_course_change_review_drafts import patch_plan
from backend.tests.test_partial_course_change import make_partial_plan
from backend.tests.test_teacher_course_change import context
from course_evolution import CourseEvolutionRepository
from course_evolution.content_patches import compile_patches
from course_evolution.partial_review import readiness, require_partial_operations
from course_evolution.patch_reconciliation import reconcile_fragment_patches
from course_evolution.patch_review import PatchValidationError, section_inventory
from course_evolution.teacher_planning import create_teacher_course_change_plan, review_teacher_course_change_scope


def patch(before, after, field='markdown'):
    return dict(field=field, before=before, after=after, replace_all=False)


def test_wrong_field_is_atomic_even_when_another_patch_matches():
    payload = {'title': '运行结果与核对', 'summary': '摘要中的任务', 'markdown': '正式原文'}
    for anchor in ('运行结果与核对', '摘要中的任务'):
        with pytest.raises(PatchValidationError) as caught:
            compile_patches(payload, [patch('正式原文', '新正文'), patch(anchor, anchor + '新增项目')])
        assert caught.value.code == 'patch_source_mismatch'
    assert payload['markdown'] == '正式原文'


def test_prose_must_not_be_spliced_into_a_code_function():
    body = '```csharp\nprivate void Update()\n{\n    ReadInput();\n}\n```\n'
    with pytest.raises(PatchValidationError, match='代码示例内部'):
        compile_patches({'markdown': body}, [patch('private void Update()\n{', 'private void Update()\n{\n}\n\n### 实践项目：输入采集\n要求')])
    # An actual code edit and prose after a complete fenced example are valid.
    assert compile_patches({'markdown': body}, [patch('ReadInput();', 'CollectInput();')])[1]
    assert compile_patches({'markdown': body}, [patch(body, body + '\n### 实践项目：输入采集\n要求')])[1]


def test_bold_and_markdown_acceptance_headings_are_same_section_but_code_is_not():
    original = '物理步长说明。\n\n### 验收标准\n1. 验证30与240 FPS。'
    after = '物理步长说明。\n\n**验收标准：**\n1. 比较帧率。\n\n### 验收标准\n1. 验证30与240 FPS。'
    _, _, warnings = compile_patches({'markdown': original}, [patch(original, after)])
    assert any('验收标准' in warning for warning in warnings)
    assert section_inventory('~~~text\n### 验收标准\n~~~\n') == {}
    assert original.endswith('1. 验证30与240 FPS。')


@pytest.mark.asyncio
async def test_reconciliation_uses_full_original_and_preserves_unique_acceptance_constraints():
    ctx = context()
    unit = next(u for u in ctx.units if u.asset_type == 'course_content')
    body = '物理步长说明。\n\n### 验收标准\n1. 比较30与240 FPS，偏差小于5%。\n2. 窗口恢复后无跳跃。'
    unit.metadata['course_block']['payload']['markdown'] = body
    duplicated = body.replace('物理步长说明。', '物理步长说明。\n\n**验收标准：**\n1. 验证帧率无关性。')
    analysis = {'affected_units': [{'unit_id': unit.unit_id, 'content_patches': [patch(body, duplicated)]}]}
    merged = body.replace('1. 比较', '1. 日志记录输入优先级。\n2. 比较').replace('2. 窗口', '3. 窗口')
    calls = []
    async def analyzer(overview, candidates, instruction):
        calls.append((overview, candidates))
        assert candidates[0]['content'] == body
        return {'affected_units': [{'unit_id': unit.unit_id, 'content_patches': [patch(body, merged)]}]}
    await reconcile_fragment_patches(analysis, ctx, analyzer, '补充实践', eligible_ids={unit.unit_id})
    result, _, warnings = compile_patches(unit.metadata['course_block']['payload'], analysis['affected_units'][0]['content_patches'])
    assert len(calls) == 1 and not warnings
    assert result['markdown'].count('验收标准') == 1
    assert '偏差小于5%' in result['markdown'] and '窗口恢复后无跳跃' in result['markdown']


@pytest.mark.asyncio
async def test_repair_outage_keeps_scan_results_and_retained_units_are_not_called_again():
    ctx = context()
    units = [u for u in ctx.units if u.asset_type == 'course_content']
    unit = units[0]
    analysis = {'affected_units': [{'unit_id': unit.unit_id, 'content_patches': [patch('不存在', '新文本')]}]}
    original = deepcopy(analysis)
    calls = []
    async def unavailable(*args):
        calls.append(args)
        raise TimeoutError('provider timeout')
    await reconcile_fragment_patches(analysis, ctx, unavailable, '补充实践', eligible_ids=set())
    assert not calls
    await reconcile_fragment_patches(analysis, ctx, unavailable, '补充实践', eligible_ids={unit.unit_id})
    assert len(calls) == 1 and analysis == original


@pytest.mark.asyncio
async def test_scan_does_not_flatten_summary_and_knowledge_labels_into_body(tmp_path):
    ctx = context()
    unit = next(u for u in ctx.units if u.asset_type == 'course_content')
    unit.full_text_fields = {'/markdown': '正式正文', '/summary': '摘要另有文字', '/knowledge_names/0': '知识名'}
    ctx.units = [unit]
    async def analyzer(overview, candidates, instruction):
        assert len(candidates) == 1
        assert candidates[0]['content'] == '正式正文'
        assert candidates[0]['content_field'] == 'markdown'
        assert candidates[0]['block_title'] == unit.metadata['course_block']['payload']['title']
        return {'affected_units': []}
    await create_teacher_course_change_plan(context=ctx, user_id='teacher', request_id='provenance', instruction='补充实践',
        repository=CourseEvolutionRepository(tmp_path), analyzer=analyzer)


@pytest.mark.asyncio
async def test_failed_patch_can_be_replaced_with_local_manual_draft_without_applying(tmp_path):
    plan = await patch_plan(tmp_path, [patch('摘要而非正文', '新增项目')])
    repo = CourseEvolutionRepository(tmp_path)
    migration = plan.teacher_change_planning.unit_migrations[0]
    assert migration.candidate_status == 'failed' and not plan.operations
    original = deepcopy(migration.metadata['course_block'])
    saved = review_teacher_course_change_scope(repository=repo, user_id='teacher', course_id='course-1',
        change_set_id=plan.change_set_id, selected_migration_ids=[migration.migration_id], selection_only=True,
        manual_content_edits={migration.migration_id: {'/markdown': '老师修正的项目与统一验收标准。'}}).change_sets[-1]
    repaired = saved.teacher_change_planning.unit_migrations[0]
    assert repaired.candidate_status == 'ready' and not repaired.metadata.get('candidate_error')
    assert saved.operations[0].payload['before_block'] == original
    assert saved.operations[0].payload['proposed_block']['payload']['markdown'] == '老师修正的项目与统一验收标准。'
    assert not saved.selected_operation_ids and not saved.impact_summary.get('scope_review')
    assert saved.impact_summary['affected_units'][0]['candidate_status'] == 'ready'


@pytest.mark.asyncio
@pytest.mark.parametrize('disposition', ['regenerate', 'reuse_rebind'])
async def test_failed_regenerate_proposal_can_be_replaced_by_an_explicit_local_edit(tmp_path, disposition):
    plan = await patch_plan(tmp_path, [patch('错误标题', '新标题', field='title')])
    repo = CourseEvolutionRepository(tmp_path)
    state = repo.load('teacher', 'course-1')
    migration = state.change_sets[-1].teacher_change_planning.unit_migrations[0]
    migration.disposition = disposition
    repo.save(state)
    saved = review_teacher_course_change_scope(repository=repo, user_id='teacher', course_id='course-1',
        change_set_id=plan.change_set_id, selected_migration_ids=[migration.migration_id], selection_only=True,
        manual_content_edits={migration.migration_id: {'/markdown': '老师明确编写的局部正文。'}}).change_sets[-1]
    assert saved.teacher_change_planning.unit_migrations[0].disposition == 'rewrite_partial'
    assert saved.impact_summary['affected_units'][0]['disposition'] == 'rewrite_partial'
    assert not saved.selected_operation_ids


@pytest.mark.asyncio
async def test_repair_removes_old_approval_and_survives_incomplete_only_retry(tmp_path):
    repo, ctx, plan, missing = await make_partial_plan(tmp_path)
    state = repo.load('teacher', 'course-1')
    plan = state.change_sets[-1]
    migration = plan.teacher_change_planning.unit_migrations[0]
    op = plan.operations[0]
    invalid = [patch('不存在的片段', '新增项目')]
    op.payload['content_patches'] = invalid
    migration.metadata['content_patches'] = invalid
    plan.impact_summary['scan_analysis']['affected_units'][0]['content_patches'] = invalid
    plan.impact_summary['scope_review'] = {'selected_operation_ids': [op.operation_id], 'selected_migration_ids': [migration.migration_id]}
    plan.selected_operation_ids = [op.operation_id]
    repo.save(state)
    saved = review_teacher_course_change_scope(repository=repo, user_id='teacher', course_id='course-1',
        change_set_id=plan.change_set_id, selected_migration_ids=[migration.migration_id], selection_only=True,
        manual_content_edits={migration.migration_id: {'/markdown': '老师修正的完整正文。'}}).change_sets[-1]
    assert saved.impact_summary['scope_review']['selected_operation_ids'] == []
    assert saved.impact_summary['scope_review']['selected_migration_ids'] == []
    with pytest.raises(ValueError):
        require_partial_operations(saved, [saved.operations[0].operation_id])
    async def analyzer(overview, candidates, instruction):
        assert [c['unit_id'] for c in candidates] == [missing]
        return {'affected_units': []}
    continued = await create_teacher_course_change_plan(context=ctx, user_id='teacher', request_id='repair-retry',
        instruction=plan.request_text, repository=repo, analyzer=analyzer,
        supersedes_plan_id=plan.change_set_id, rescan_incomplete_only=True)
    new = continued.change_sets[-1]
    assert new.operations[0].payload['proposed_block']['payload']['markdown'] == '老师修正的完整正文。'
    assert new.teacher_change_planning.unit_migrations[0].metadata['manually_edited']


@pytest.mark.asyncio
async def test_unscanned_or_changed_source_cannot_be_repaired_from_old_snapshot(tmp_path):
    repo, ctx, plan, missing = await make_partial_plan(tmp_path)
    state = repo.load('teacher', 'course-1')
    target = state.change_sets[-1]
    migration = target.teacher_change_planning.unit_migrations[0]
    target.impact_summary['coverage']['unscanned_unit_ids'].extend(migration.source_unit_ids)
    repo.save(state)
    assert migration.migration_id not in readiness(target)['editable_migration_ids']
    with pytest.raises(ValueError, match='完整检查'):
        review_teacher_course_change_scope(repository=repo, user_id='teacher', course_id='course-1',
            change_set_id=plan.change_set_id, selected_migration_ids=[migration.migration_id], selection_only=True,
            manual_content_edits={migration.migration_id: {'/markdown': '不应覆盖'}})
    unit = next(u for u in ctx.units if u.unit_id in migration.source_unit_ids)
    unit.metadata['course_block']['payload']['markdown'] = '另外一位老师的新正文'
    with pytest.raises(ValueError, match='原文已变化'):
        review_teacher_course_change_scope(repository=repo, user_id='teacher', course_id='course-1',
            change_set_id=plan.change_set_id, selected_migration_ids=[migration.migration_id], selection_only=True,
            manual_content_edits={migration.migration_id: {'/markdown': '不应覆盖'}}, context=ctx)
