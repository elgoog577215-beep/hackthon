from functools import partial
from copy import deepcopy

import pytest

from backend.tests.test_teacher_change_durable import fixture
from backend.tests.test_teacher_course_change import MemoryCourseStorage
from course_document import CourseDocument, document_from_legacy_course
from course_repository import CourseDocumentRepository
from course_evolution.application import CourseEvolutionApplicationService
import course_evolution.application as application_module
from course_evolution.core import accept_change_set
from course_evolution.teacher_planning import build_teacher_course_change_context, create_teacher_course_change_plan, review_teacher_course_change_scope
from teacher_content_projection import project_teacher_content
from teaching_representations import TeachingRepresentationRepository
from question_bank import QuestionBankRepository


@pytest.mark.asyncio
async def test_projected_text_edits_apply_to_teacher_handout_and_undo_in_reverse_order(tmp_path, monkeypatch):
    import asyncio
    course, authoring, evolution, _ = fixture(tmp_path)
    monkeypatch.setattr('teacher_content_projection.authoring_repository', lambda storage: authoring)
    lesson = authoring.lesson('course-1', 'L1-1')
    base = next(r for r in lesson['script_revisions'] if r['revision_id'] == lesson['working_script_revision_id'])
    sections = deepcopy(base['sections'])
    second = deepcopy(sections[0]['blocks'][0])
    second['block_id'] = 'tsb-second-exact-target'
    second['content'] += '\n\n第二个独立示例。'
    sections[0]['blocks'].append(second)
    authoring.save_script_revision('course-1', 'L1-1', sections,
        source_lesson_plan_revision_id=base['source_lesson_plan_revision_id'])
    course.update(authoring_surface='teacher', teacher_production_schema='unified_teacher_v1',
                  course_document=document_from_legacy_course(course).model_dump(mode='json'),
                  course_schema_version='course_document_v1', course_document_authoritative=True)
    raw = project_teacher_content(course, authoring=authoring.load('course-1'))
    document = CourseDocument.model_validate(raw['course_document'])
    assert len(document.blocks) >= 2
    ctx = build_teacher_course_change_context(course_id='course-1', document=document, preview=None,
        authoring=authoring.load('course-1'), question_bank=None, representation_registries=[])
    targets = [u for u in ctx.units if u.asset_type == 'course_content'][:2]
    async def analyze(overview, candidates, instruction):
        ids = {c['unit_id'] for c in candidates}
        return {'structure': {'required': False}, 'affected_units': [{
            'unit_id': u.unit_id, 'disposition': 'rewrite_partial', 'content_patches': [
                {'field': 'markdown', 'before': '核心概念的定义', 'after': '核心概念的定义与边界', 'replace_all': True},
            ]} for u in targets if u.unit_id in ids]}
    state = await create_teacher_course_change_plan(context=ctx, user_id='teacher', request_id='owner-route',
        instruction='补充定义边界', repository=evolution, analyzer=analyze)
    plan = state.change_sets[-1]
    assert len(plan.operations) == 2
    review_teacher_course_change_scope(repository=evolution, user_id='teacher', course_id='course-1',
        change_set_id=plan.change_set_id, selected_migration_ids=[m.migration_id for m in plan.teacher_change_planning.unit_migrations])
    documents = CourseDocumentRepository(MemoryCourseStorage(raw))
    service = CourseEvolutionApplicationService(evolution_repository=evolution, document_repository=documents,
        authoring_repository=authoring, representation_repository=TeachingRepresentationRepository(tmp_path / 'representations'),
        question_bank_repository=QuestionBankRepository(tmp_path / 'questions'), course_service=None)
    monkeypatch.setattr(application_module, 'accept_change_set', partial(accept_change_set, repository=evolution))
    original_revision = authoring.lesson('course-1', 'L1-1')['working_script_revision_id']
    ids = [op.operation_id for op in plan.operations]
    applied = await asyncio.to_thread(service.accept, course_data=raw, user_id='teacher', change_set_id=plan.change_set_id,
        selected_scope='current', selected_operation_ids=ids)
    saved = authoring.lesson('course-1', 'L1-1')
    assert saved['working_script_revision_id'] != original_revision
    revision = next(r for r in saved['script_revisions'] if r['revision_id'] == saved['working_script_revision_id'])
    changed = [b for s in revision['sections'] for b in s['blocks'] if '定义与边界' in b['content']]
    assert len(changed) == 2
    assert all(entry.status == 'applied' for entry in applied.change_sets[-1].operation_journal)
    await asyncio.to_thread(service.undo, user_id='teacher', course_id='course-1', change_set_id=plan.change_set_id)
    assert authoring.lesson('course-1', 'L1-1')['working_script_revision_id'] == original_revision
