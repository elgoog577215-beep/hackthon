import asyncio
from copy import deepcopy

import pytest

from backend.tests.test_teacher_course_change import context, document, MemoryCourseStorage
from course_evolution import CourseEvolutionRepository, accept_change_set, undo_change_set
from course_evolution.teacher_planning import create_teacher_course_change_plan, review_teacher_course_change_scope
from course_evolution.change_planning import CourseChangeSystemBlocker
from course_evolution.partial_review import readiness, applied_units
from course_repository import CourseDocumentRepository


async def make_partial_plan(tmp_path):
    repo = CourseEvolutionRepository(tmp_path / 'evolution')
    ctx = context()
    target = next(u for u in ctx.units if u.asset_type == 'course_content')
    async def analyze(overview, candidates, instruction):
        return {'signal_kind': 'semantic', 'structure': {'required': False}, 'affected_units': [{
            'unit_id': target.unit_id, 'disposition': 'rewrite_partial',
            'content_patches': [{'field': 'markdown', 'before': '受力图', 'after': '自由体图'}],
        }] if target.unit_id in {c['unit_id'] for c in candidates} else []}
    state = await create_teacher_course_change_plan(context=ctx, user_id='teacher', request_id='first',
        instruction='统一术语', repository=repo, analyzer=analyze)
    plan = state.change_sets[-1]
    missing = next(u.unit_id for u in ctx.units if u.asset_type == 'question_bank')
    plan.impact_summary['coverage']['unscanned_unit_ids'] = [missing]
    plan.impact_summary['coverage']['source_revisions'].pop(missing, None)
    plan.impact_summary['coverage']['scanned_units'] -= 1
    plan.teacher_change_planning.intent.system_blockers = [CourseChangeSystemBlocker(
        code='analysis_incomplete', message='one pending', affected_unit_count=1)]
    plan.teacher_change_planning.status = 'blocked'
    repo.save(state)
    return repo, ctx, plan, missing


@pytest.mark.asyncio
async def test_independent_content_can_be_reviewed_applied_and_undone_while_scan_incomplete(tmp_path):
    repo, ctx, plan, missing = await make_partial_plan(tmp_path)
    migration = plan.teacher_change_planning.unit_migrations[0]
    reviewed = review_teacher_course_change_scope(repository=repo, user_id='teacher', course_id='course-1',
        change_set_id=plan.change_set_id, selected_migration_ids=[migration.migration_id])
    assert reviewed.change_sets[-1].impact_summary['scope_review']['selected_migration_ids'] == [migration.migration_id]
    doc = document()
    raw = {'course_id': 'course-1', 'course_name': doc.title, 'course_schema_version': 'course_document_v1',
        'course_document': doc.model_dump(mode='json'), 'course_document_revision': doc.document_revision,
        'course_document_authoritative': True, 'course_operation_log': []}
    documents = CourseDocumentRepository(MemoryCourseStorage(raw))
    applied = await asyncio.to_thread(accept_change_set, raw, user_id='teacher', change_set_id=plan.change_set_id,
        selected_scope='current', selected_operation_ids=[migration.metadata['operation_id']],
        repository=repo, document_repository=documents)
    assert documents.load_document('course-1')[0].blocks[0].payload['markdown'] == '先给出自由体图，再列方程。'
    assert applied.change_sets[-1].impact_summary['coverage']['unscanned_unit_ids'] == [missing]
    assert migration.source_unit_ids[0] in applied_units(applied.change_sets[-1])
    calls = []
    async def rescan(overview, candidates, instruction):
        calls.extend(c['unit_id'] for c in candidates)
        return {'affected_units': [], 'signal_kind': 'semantic', 'structure': {'required': False}}
    continued = await create_teacher_course_change_plan(context=ctx, user_id='teacher', request_id='continued',
        instruction=plan.request_text, repository=repo, analyzer=rescan, supersedes_plan_id=plan.change_set_id,
        rescan_incomplete_only=True)
    assert calls == [missing]
    assert continued.change_sets[0].status == 'applied'
    assert continued.change_sets[-1].impact_summary['continued_from_plan_id'] == plan.change_set_id
    assert not continued.change_sets[-1].operations
    await asyncio.to_thread(undo_change_set, user_id='teacher', course_id='course-1', change_set_id=plan.change_set_id,
        repository=repo, document_repository=documents)
    assert documents.load_document('course-1')[0].blocks[0].payload['markdown'] == '先给出受力图，再列方程。'


@pytest.mark.asyncio
async def test_incomplete_only_retry_uses_plan_results_without_task_checkpoint(tmp_path):
    repo, ctx, plan, missing = await make_partial_plan(tmp_path)
    seen, progress = [], []
    async def analyze(overview, candidates, instruction):
        seen.extend(c['unit_id'] for c in candidates)
        return {'signal_kind': 'semantic', 'affected_units': [], 'structure': {'required': False}}
    async def report(detail, checkpoint):
        progress.append(deepcopy(detail))
    state = await create_teacher_course_change_plan(context=ctx, user_id='teacher', request_id='retry',
        instruction=plan.request_text, repository=repo, analyzer=analyze, supersedes_plan_id=plan.change_set_id,
        rescan_incomplete_only=True, on_scan_progress=report)
    assert seen == [missing]
    assert progress[0]['retained_units'] == len(ctx.units) - 1
    assert state.change_sets[-1].impact_summary['coverage']['unscanned_unit_ids'] == []
    assert state.change_sets[-1].teacher_change_planning.unit_migrations


@pytest.mark.asyncio
async def test_rescan_rechecks_only_changed_success_and_missing_items(tmp_path):
    repo, ctx, plan, missing = await make_partial_plan(tmp_path)
    changed = next(u for u in ctx.units if u.asset_type == 'script')
    changed.source_revision = 'changed-after-analysis'
    seen = []
    async def analyze(overview, candidates, instruction):
        seen.extend(c['unit_id'] for c in candidates)
        return {'signal_kind': 'semantic', 'affected_units': [], 'structure': {'required': False}}
    await create_teacher_course_change_plan(context=ctx, user_id='teacher', request_id='retry-changed',
        instruction=plan.request_text, repository=repo, analyzer=analyze, supersedes_plan_id=plan.change_set_id,
        rescan_incomplete_only=True)
    assert set(seen) == {missing, changed.unit_id}


@pytest.mark.asyncio
async def test_rescan_preserves_unapplied_manual_candidate_edits(tmp_path):
    repo, ctx, plan, missing = await make_partial_plan(tmp_path)
    migration = plan.teacher_change_planning.unit_migrations[0]
    review_teacher_course_change_scope(repository=repo, user_id='teacher', course_id='course-1',
        change_set_id=plan.change_set_id, selected_migration_ids=[migration.migration_id],
        manual_content_edits={migration.migration_id: {'/markdown': '老师保留的人工修改正文'}})
    async def analyze(overview, candidates, instruction):
        return {'signal_kind': 'semantic', 'affected_units': [], 'structure': {'required': False}}
    result = await create_teacher_course_change_plan(context=ctx, user_id='teacher', request_id='manual-retry',
        instruction=plan.request_text, repository=repo, analyzer=analyze, supersedes_plan_id=plan.change_set_id,
        rescan_incomplete_only=True)
    candidate = next(o for o in result.change_sets[-1].operations if o.operation_type == 'REPLACE_COURSE_BLOCK')
    assert candidate.payload['proposed_block']['payload']['markdown'] == '老师保留的人工修改正文'


@pytest.mark.asyncio
@pytest.mark.parametrize('barrier', ['unscanned', 'teacher_question', 'unknown_coverage', 'shared_scope'])
async def test_partial_review_cannot_bypass_real_dependencies(tmp_path, barrier):
    repo, ctx, plan, missing = await make_partial_plan(tmp_path)
    migration = plan.teacher_change_planning.unit_migrations[0]
    if barrier == 'unscanned':
        plan.impact_summary['coverage']['unscanned_unit_ids'].append(migration.source_unit_ids[0])
    elif barrier == 'teacher_question':
        plan.teacher_change_planning.intent.blocking_questions = ['教师需要决定范围']
        plan.teacher_change_planning.intent.can_proceed_without_clarification = False
    elif barrier == 'unknown_coverage':
        plan.impact_summary['coverage']['source_revisions'] = {}
    else:
        migration.asset_type = 'script'
        plan.impact_summary['scan_unit_index'] = {}
    repo.save(repo.load('teacher', 'course-1').model_copy(update={'change_sets': [plan]}))
    assert migration.migration_id not in readiness(plan)['eligible_migration_ids']
    with pytest.raises(ValueError, match='所选修改'):
        review_teacher_course_change_scope(repository=repo, user_id='teacher', course_id='course-1',
            change_set_id=plan.change_set_id, selected_migration_ids=[migration.migration_id])


@pytest.mark.asyncio
async def test_partial_application_requires_explicit_review_and_never_takes_all_operations(tmp_path):
    from course_evolution.partial_review import require_partial_operations
    repo, _, plan, _ = await make_partial_plan(tmp_path)
    with pytest.raises(ValueError, match='明确选择'):
        require_partial_operations(plan, None)
    with pytest.raises(ValueError, match='明确选择'):
        require_partial_operations(plan, [plan.operations[0].operation_id])


@pytest.mark.asyncio
async def test_partial_structure_confirmation_cannot_bypass_incomplete_scan(tmp_path):
    repo, _, plan, _ = await make_partial_plan(tmp_path)
    migration = plan.teacher_change_planning.unit_migrations[0]
    with pytest.raises(ValueError, match='所选修改'):
        review_teacher_course_change_scope(repository=repo, user_id='teacher', course_id='course-1',
            change_set_id=plan.change_set_id, selected_migration_ids=[migration.migration_id], confirm_structure=True)


@pytest.mark.asyncio
@pytest.mark.parametrize('barrier', ['structure', 'stale', 'retire'])
async def test_partial_readiness_explains_real_waiting_reason(tmp_path, barrier):
    _, _, plan, _ = await make_partial_plan(tmp_path)
    m = plan.teacher_change_planning.unit_migrations[0]
    expected = {'structure': 'structure_dependency', 'stale': 'source_stale', 'retire': 'shared_scope'}[barrier]
    if barrier == 'structure':
        plan.teacher_change_planning.execution_strategies = ['structural_regeneration']
    elif barrier == 'stale':
        m.metadata['source_state'] = 'stale'
    else:
        m.disposition = 'retire'
    assert readiness(plan)['waiting'][m.migration_id] == expected


@pytest.mark.asyncio
async def test_wrong_retry_goal_or_scope_cannot_reuse_old_judgments(tmp_path):
    repo, ctx, plan, _ = await make_partial_plan(tmp_path)
    for instruction, asset_types in [('改成完全不同目标', None), (plan.request_text, ['script'])]:
        with pytest.raises(ValueError, match='补查必须'):
            await create_teacher_course_change_plan(context=ctx, user_id='teacher', request_id=instruction,
                instruction=instruction, repository=repo, supersedes_plan_id=plan.change_set_id,
                asset_types=asset_types, rescan_incomplete_only=True)


@pytest.mark.asyncio
async def test_long_inputs_are_scanned_in_small_complete_fragments(tmp_path):
    from course_evolution.teacher_planning import TeacherCourseChangeUnit
    repo = CourseEvolutionRepository(tmp_path)
    ctx = context()
    body = 'FIRST_MARKER\n' + '长代码说明\n' * 900 + '\nLAST_MARKER'
    ctx.units = [TeacherCourseChangeUnit(unit_id='script:lecture:block', asset_type='script',
        unit_type='script_block', title='Code example', text=body, source_revision='r1')]
    pieces = []
    async def analyze(overview, candidates, instruction):
        pieces.extend(item['content'] for item in candidates)
        assert sum(len(item['content']) for item in candidates) <= 2400
        return {'affected_units': [], 'signal_kind': 'semantic', 'structure': {'required': False}}
    result = await create_teacher_course_change_plan(context=ctx, user_id='teacher', request_id='small-fragments',
        instruction='检查全部内容', repository=repo, analyzer=analyze)
    assert result.change_sets[-1].impact_summary['coverage']['scanned_units'] == 1
    assert all(len(piece) <= 1200 for piece in pieces)
    assert pieces[0].startswith('FIRST_MARKER') and pieces[-1].endswith('LAST_MARKER')
    reconstructed = pieces[0]
    for piece in pieces[1:]:
        overlap = min(100, len(piece))
        assert reconstructed.endswith(piece[:overlap])
        reconstructed += piece[overlap:]
    assert reconstructed == body


@pytest.mark.asyncio
async def test_analysis_prompt_does_not_resend_duplicate_full_editable_fields():
    from types import SimpleNamespace
    from course_generation.service import CourseService
    seen = []
    async def llm(prompt, **kwargs):
        seen.append((prompt, kwargs))
        return '{"affected_units": []}'
    service = SimpleNamespace(_call_llm=llm, _extract_json=lambda value: {'affected_units': []})
    await CourseService.analyze_teacher_course_change(service, {}, [
        {'unit_id': 'u', 'content': 'UNIQUE_CODE_BODY', 'editable_fields': {'markdown': 'UNIQUE_CODE_BODY'}}
    ], '检查全部内容')
    assert seen[0][0].count('UNIQUE_CODE_BODY') == 1
    assert seen[0][1]['wait_for_capacity'] is True


@pytest.mark.asyncio
async def test_failed_long_fragment_is_recovered_in_smaller_parts_without_losing_text():
    from course_evolution.semantic_scan import scan_batches
    body = 'A' * 1100 + 'END'
    accepted = []
    async def analyze(overview, items, instruction):
        if any(len(i['content']) > 600 for i in items):
            raise TimeoutError('slow code fragment')
        accepted.extend(i['content'] for i in items)
        return {'affected_units': [], 'structure': {'required': False}}
    _, scanned, missing, failures, _ = await scan_batches(overview={}, batches=[[{'unit_id': 'u', 'content': body}]],
        instruction='test', revisions={}, analyzer=analyze)
    assert scanned == {'u'} and not missing and not failures
    assert accepted and accepted[-1].endswith('END')
    assert all(len(s) <= 600 for s in accepted)


@pytest.mark.asyncio
async def test_very_long_code_uses_smaller_fragments_before_a_timeout(tmp_path):
    from course_evolution.teacher_planning import TeacherCourseChangeUnit
    ctx = context()
    ctx.units = [TeacherCourseChangeUnit(unit_id='code', asset_type='course_content', unit_type='course_block',
        title='code', text='```csharp\n' + 'int counter;\n' * 600 + '```', source_revision='r')]
    async def analyze(overview, items, instruction):
        assert all(len(i['content']) <= 600 for i in items)
        return {'affected_units': [], 'structure': {'required': False}}
    state = await create_teacher_course_change_plan(context=ctx, user_id='teacher', request_id='code-small',
        instruction='check', repository=CourseEvolutionRepository(tmp_path), analyzer=analyze)
    assert state.change_sets[-1].impact_summary['coverage']['scanned_units'] == 1


@pytest.mark.asyncio
async def test_invalid_model_ids_get_bounded_feedback_instead_of_being_accepted():
    from course_evolution.semantic_scan import scan_batches
    seen = []
    async def analyze(overview, items, instruction):
        seen.append(overview)
        if not overview.get('analysis_validation_feedback'):
            return {'affected_units': [{'unit_id': 'invented'}]}
        assert overview['analysis_validation_feedback']['allowed_unit_ids'] == ['u']
        return {'affected_units': [{'unit_id': 'u', 'content_patches': []}]}
    _, scanned, missing, failures, _ = await scan_batches(overview={}, batches=[[{'unit_id': 'u', 'content': 'text'}]],
        instruction='test', revisions={}, analyzer=analyze)
    assert scanned == {'u'} and not missing and not failures
    assert len(seen) <= 3


@pytest.mark.asyncio
async def test_connection_outage_is_not_retried_as_thirty_bad_content_items():
    import httpx
    from ai_base import AIProviderRequestError
    from course_evolution.semantic_scan import scan_batches
    calls, waits = [], []
    async def analyze(overview, items, instruction):
        calls.append(items)
        try:
            raise httpx.ConnectTimeout('provider connection unavailable')
        except httpx.ConnectTimeout as error:
            raise AIProviderRequestError('Request timed out.') from error
    async def sleep(seconds):
        waits.append(seconds)
    batches = [[{'unit_id': str(i), 'content': 'example'}] for i in range(30)]
    _, scanned, missing, failures, _ = await scan_batches(overview={}, batches=batches,
        instruction='check', revisions={}, analyzer=analyze, sleep=sleep)
    assert len(calls) == 2 and len(waits) == 1
    assert not scanned and missing == {str(i) for i in range(30)}
    assert failures[0]['code'] == 'provider_unavailable'
