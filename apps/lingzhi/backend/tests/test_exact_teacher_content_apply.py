from copy import deepcopy

import pytest

from backend.tests.test_teacher_change_durable import fixture
from backend.tests.test_teacher_lesson_authoring import course_data as full_course_data
from backend.tests.test_teacher_course_change import MemoryCourseStorage
from course_document import CourseDocument, document_from_legacy_course
from course_repository import CourseDocumentRepository
from course_evolution.application import CourseEvolutionApplicationService
from course_evolution.teacher_planning import build_teacher_course_change_context, create_teacher_course_change_plan, review_teacher_course_change_scope
from teacher_content_projection import project_teacher_content
from teaching_representations import TeachingRepresentationRepository
from question_bank import QuestionBankRepository
from teacher_script import compile_teacher_script_module_contract, compile_teacher_script_section, validate_teacher_script_section


@pytest.mark.asyncio
@pytest.mark.parametrize('scenario', ['apply', 'interrupted', 'source_drift', 'quality_failure'])
async def test_projected_text_edits_apply_to_teacher_handout_and_undo_in_reverse_order(tmp_path, monkeypatch, scenario):
    import asyncio
    course, authoring, evolution, _ = fixture(tmp_path)
    monkeypatch.setattr('teacher_content_projection.authoring_repository', lambda storage: authoring)
    lesson = authoring.lesson('course-1', 'L1-1')
    base_plan = deepcopy(next(r for r in lesson['revisions'] if r['revision_id'] == lesson['working_revision_id'])['plan'])
    second = deepcopy(base_plan['sections'][0])
    second['node_id'] = 'L2-1-2'
    base_plan['sections'].append(second)
    full = full_course_data()
    course['nodes'].append(deepcopy(next(n for n in full['nodes'] if n['node_id'] == 'L2-1-2')))
    course['course_plan']['chapters'][0]['sections'].append(deepcopy(full['course_plan']['chapters'][0]['sections'][1]))
    lesson = authoring.save_plan_revision('course-1', 'L1-1', base_plan, source_outline_revision_id='outline-v1')
    source_plan = next(r for r in lesson['revisions'] if r['revision_id'] == lesson['working_revision_id'])['plan']
    sections = []
    for section_plan in source_plan['sections']:
        node = next(n for n in course['nodes'] if n['node_id'] == section_plan['node_id'])
        contract = compile_teacher_script_module_contract(node, section_plan)
        markdown = '\n\n'.join('## '+m['title']+'\n\n我们先看核心概念的定义：定义、成立条件和适用边界共同决定一个判断是否成立。请用一个反例检验它。' for m in contract['modules'])
        section = compile_teacher_script_section(markdown, contract)
        section['quality_report'] = validate_teacher_script_section(section, contract)
        assert section['quality_report']['passed']
        sections.append(section)
    authoring.save_script_revision('course-1', 'L1-1', sections,
        source_lesson_plan_revision_id=lesson['working_revision_id'])
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
    original_revision = authoring.lesson('course-1', 'L1-1')['working_script_revision_id']
    ids = [op.operation_id for op in plan.operations]
    initial_revision_count = len(authoring.lesson('course-1', 'L1-1')['script_revisions'])
    if scenario == 'source_drift':
        changed_sections = deepcopy(sections)
        changed_sections[0]['blocks'][0]['content'] += '\n\n教师后来补充的原文。'
        live = authoring.save_script_revision('course-1', 'L1-1', changed_sections,
            source_lesson_plan_revision_id=lesson['working_revision_id'])
        with pytest.raises(ValueError, match='已经变化'):
            await asyncio.to_thread(service.accept, course_data=raw, user_id='teacher', change_set_id=plan.change_set_id,
                selected_scope='current', selected_operation_ids=ids)
        assert authoring.lesson('course-1', 'L1-1')['working_script_revision_id'] == live['working_script_revision_id']
        return
    if scenario == 'quality_failure':
        monkeypatch.setattr('course_evolution.teacher_execution.validate_teacher_script_section', lambda *args: {'passed': False})
        failed = await asyncio.to_thread(service.accept, course_data=raw, user_id='teacher', change_set_id=plan.change_set_id,
            selected_scope='current', selected_operation_ids=ids)
        assert all(entry.status == 'failed' for entry in failed.change_sets[-1].operation_journal)
        assert authoring.lesson('course-1', 'L1-1')['working_script_revision_id'] == original_revision
        return
    if scenario == 'interrupted':
        import course_evolution.teacher_execution as execution
        from course_evolution.core import CourseEvolutionJournalPersistenceError
        original_persist = execution._persist_journal_entry
        def fail_completed_journal(plan, entry, **kwargs):
            if entry.status == 'applied':
                raise CourseEvolutionJournalPersistenceError('test interruption after owner write')
            return original_persist(plan, entry, **kwargs)
        monkeypatch.setattr(execution, '_persist_journal_entry', fail_completed_journal)
        with pytest.raises(CourseEvolutionJournalPersistenceError):
            await asyncio.to_thread(service.accept, course_data=raw, user_id='teacher', change_set_id=plan.change_set_id,
                selected_scope='current', selected_operation_ids=ids)
        monkeypatch.setattr(execution, '_persist_journal_entry', original_persist)
    applied = await asyncio.to_thread(service.accept, course_data=raw, user_id='teacher', change_set_id=plan.change_set_id,
        selected_scope='current', selected_operation_ids=ids)
    saved = authoring.lesson('course-1', 'L1-1')
    assert saved['working_script_revision_id'] != original_revision
    revision = next(r for r in saved['script_revisions'] if r['revision_id'] == saved['working_script_revision_id'])
    changed = [b for s in revision['sections'] for b in s['blocks'] if '定义与边界' in b['content']]
    assert len(changed) == 2
    assert all(entry.status == 'applied' for entry in applied.change_sets[-1].operation_journal)
    assert len(saved['script_revisions']) == initial_revision_count + 2
    await asyncio.to_thread(service.accept, course_data=raw, user_id='teacher', change_set_id=plan.change_set_id,
        selected_scope='current', selected_operation_ids=ids)
    assert authoring.lesson('course-1', 'L1-1')['working_script_revision_id'] == saved['working_script_revision_id']
    undone = await asyncio.to_thread(service.undo, user_id='teacher', course_id='course-1', change_set_id=plan.change_set_id)
    assert undone.change_sets[-1].status == 'undone', undone.change_sets[-1].undo_receipt
    restored = authoring.lesson('course-1', 'L1-1')
    live = next(r for r in restored['script_revisions'] if r['revision_id'] == restored['working_script_revision_id'])
    original = next(r for r in restored['script_revisions'] if r['revision_id'] == original_revision)
    assert [b['content'] for s in live['sections'] for b in s['blocks']] == [b['content'] for s in original['sections'] for b in s['blocks']]
    assert undone.change_sets[-1].status == 'undone'
