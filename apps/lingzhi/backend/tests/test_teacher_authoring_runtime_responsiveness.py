"""Manual saves must leave the server event loop available for other requests."""
import json
import threading
from copy import deepcopy
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from dependencies import get_teacher_lesson_authoring_repository, require_task_manager
from routers import teacher_lesson_authoring as routes
from teacher_lesson_authoring import TeacherLessonAuthoringError, TeacherLessonAuthoringRepository


@pytest.mark.asyncio
@pytest.mark.parametrize(('method', 'path', 'payload'), [
    ('PATCH', 'plan', {'plan': {}}),
    ('PUT', 'script', {'sections': []}),
])
async def test_manual_save_keeps_synchronous_owner_work_off_the_event_loop(tmp_path, monkeypatch, method, path, payload):
    event_loop_thread = threading.get_ident()
    called = []

    def read_source(*args, **kwargs):
        assert threading.get_ident() != event_loop_thread, 'Owner I/O blocks every request when executed on the event loop'
        called.append(True)
        raise TeacherLessonAuthoringError('source_read_failed', 'Unable to read source')

    monkeypatch.setattr(routes, '_source_course', read_source)
    repository = TeacherLessonAuthoringRepository(tmp_path / 'authoring')
    app = FastAPI()
    app.include_router(routes.router, prefix='/api')
    app.dependency_overrides[require_task_manager] = lambda: SimpleNamespace()
    app.dependency_overrides[get_teacher_lesson_authoring_repository] = lambda: repository
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        response = await client.request(method, f'/api/teacher/courses/c/lessons/L1-1/{path}/draft', json=payload)
    assert called == [True]
    assert response.status_code == 409
    assert response.json()['detail']['code'] == 'source_read_failed'


def test_fast_authoring_json_preserves_unicode_frozen_inputs_and_input_isolation(tmp_path):
    repo = TeacherLessonAuthoringRepository(tmp_path / 'authoring')
    value = repo.load('course-1')
    value['jobs']['job-1'] = {'id': 'job-1', 'type': 'course_knowledge_tree_generation', 'status': 'paused',
                             'request_snapshot': {'source': '中文讲义\nα + β'}, 'raw_response': '已有结果'}
    before = deepcopy(value)
    saved = repo._save(value)
    assert value == before
    assert json.loads(repo._path('course-1').read_text(encoding='utf-8')) == saved
    assert repo.load('course-1')['jobs']['job-1']['request_snapshot'] == before['jobs']['job-1']['request_snapshot']
    assert not list(repo.root.glob('*.tmp'))
