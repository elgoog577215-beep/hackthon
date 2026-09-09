import asyncio
from copy import deepcopy

import pytest

from backend.tests.test_teacher_course_change import context, document, MemoryCourseStorage
from course_evolution import CourseEvolutionRepository, accept_change_set, undo_change_set
from course_evolution.teacher_planning import create_teacher_course_change_plan, review_teacher_course_change_scope
from course_evolution.change_planning import CourseChangeSystemBlocker
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
    applied = accept_change_set(raw, user_id='teacher', change_set_id=plan.change_set_id,
        selected_scope='current', selected_operation_ids=[migration.metadata['operation_id']],
        repository=repo, document_repository=documents)
    assert documents.load_document('course-1')[0].blocks[0].payload['markdown'] == '先给出自由体图，再列方程。'
    assert applied.change_sets[-1].impact_summary['coverage']['unscanned_unit_ids'] == [missing]
    undo_change_set(user_id='teacher', course_id='course-1', change_set_id=plan.change_set_id,
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
