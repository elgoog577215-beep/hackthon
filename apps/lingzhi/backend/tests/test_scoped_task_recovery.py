from copy import deepcopy
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from backend.tests.test_teacher_lesson_authoring import lecture_course_data
from dependencies import get_teacher_lesson_authoring_repository, require_task_manager
from routers import teacher_lesson_authoring as routes
from teacher_lesson_authoring import TeacherLessonAuthoringRepository
from teaching_design.lesson_arrangement import recommend_lesson_arrangement


@pytest.mark.parametrize('sibling_status,include_completed', [('completed', False), ('completed', True), ('failed', False)])
def test_batch_resume_only_selected_incomplete_jobs(tmp_path, monkeypatch, sibling_status, include_completed):
    repository = TeacherLessonAuthoringRepository(tmp_path)
    source = {**lecture_course_data(), 'blueprint_revision_id': 'outline-v1'}
    jobs = []
    for lid, status in [('L1-1', 'failed'), ('L1-2', sibling_status)]:
        job = repository.create_job('course-1', lid, request_id=lid, source_outline_revision_id='outline-v1')
        jobs.append(repository.update_job('course-1', job['id'], status=status, parent_job_id='original-batch',
            input_fingerprint='frozen', request_snapshot={'generation_contract_version': 'lesson_plan_single_v2'},
            error={'code': 'lesson_plan_generation_failed', 'retryable': True} if status == 'failed' else None))
    state = repository.load('course-1')
    state['outline_revision_id'] = 'outline-v1'
    repository._save(state)
    sibling_before = deepcopy(repository.get_job('course-1', jobs[1]['id']))
    tm = SimpleNamespace(storage=None, get_generation_workspace_course=lambda _: source, get_generation_preview=lambda _: None)
    lessons = []
    for job in jobs:
        arrangement = recommend_lesson_arrangement(source, job['lesson_unit_id'], source_outline_revision_id='outline-v1')
        lessons.append({'lesson_unit_id': job['lesson_unit_id'], 'arrangement': arrangement,
            'sections': [{'section_node_id': key} for key in dict.fromkeys(b['section_node_id'] for b in arrangement['blocks'])],
            'plan': {'ready': job['status'] == 'completed', 'can_generate': True}})
    monkeypatch.setattr(routes, '_lesson_projection', lambda *args, **kwargs: lessons)
    monkeypatch.setattr(routes, '_lesson_plan_material_scope', lambda *args, **kwargs: {
        'source_package_id': '', 'source_asset_id': '', 'material_asset_ids': []})
    launched = []

    async def generate(course_id, lesson_id, body, request, manager, repo):
        routes._validated_teacher_asset_resume_job(repo, course_id=course_id, resume_job_id=body.resume_job_id,
            lesson_unit_id=lesson_id, job_type='teacher_lesson_plan_generation',
            source_revision_field='source_outline_revision_id', source_revision_id='outline-v1')
        job, created = repo.resume_lesson_generation(course_id, body.resume_job_id, input_fingerprint='frozen')
        if created:
            launched.append(lesson_id)
        return {'job': job}

    monkeypatch.setattr(routes, 'generate_lesson_plan', generate)
    app = FastAPI()
    app.include_router(routes.router, prefix='/api')
    app.dependency_overrides[require_task_manager] = lambda: tm
    app.dependency_overrides[get_teacher_lesson_authoring_repository] = lambda: repository
    ids = [jobs[0]['id']] + ([jobs[1]['id']] if include_completed else [])
    with TestClient(app) as client:
        response = client.post('/api/teacher/courses/course-1/lesson-plans/generate-all',
            json={'request_id': 'resume-selected', 'resume_job_ids': ids})
    assert response.status_code == 202, response.json()
    assert launched == ['L1-1']
    assert repository.get_job('course-1', jobs[1]['id']) == sibling_before
    assert response.json()['skipped_lesson_ids'] == ['L1-2']
