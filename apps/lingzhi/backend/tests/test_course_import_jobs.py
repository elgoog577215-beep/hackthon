from __future__ import annotations

from copy import deepcopy

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from course_repository import CourseDocumentRepository
from dependencies import require_task_manager
from jobs.manager import TaskManager, TaskRecoveryConflict
from routers import markdown_import


class ImportStorage:
    def __init__(self, data_dir) -> None:
        self._data_dir = str(data_dir)
        self.courses: dict[str, dict] = {}

    def load_course(self, course_id: str):
        return deepcopy(self.courses.get(course_id))

    async def save_course(self, course_id: str, data: dict) -> None:
        self.courses[course_id] = deepcopy(data)


def import_manager(tmp_path, monkeypatch) -> tuple[TaskManager, ImportStorage]:
    import jobs.manager as task_manager_module

    monkeypatch.setattr(task_manager_module, 'TASKS_FILE', tmp_path / 'tasks.json')
    storage = ImportStorage(tmp_path / 'data')
    manager = TaskManager(
        storage,
        course_service=None,
        ws_service=None,
        document_repository=CourseDocumentRepository(storage),
    )
    return manager, storage


def test_markdown_import_job_route_returns_accepted_task(tmp_path, monkeypatch):
    manager, _storage = import_manager(tmp_path, monkeypatch)
    app = FastAPI()
    app.include_router(markdown_import.router)
    app.dependency_overrides[require_task_manager] = lambda: manager
    client = TestClient(app)

    response = client.post(
        '/api/import_markdown/jobs',
        headers={'X-User-Id': 'teacher-a'},
        files={
            'file': (
                'linear-algebra.md',
                b'# Linear Algebra\n\nVectors have magnitude and direction.\n',
                'text/markdown',
            ),
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload['job_id']
    assert payload['course_id']
    summary = manager.get_task_summary(payload['job_id'])
    assert summary['type'] == 'course_import'
    assert summary['current_phase'] == 'material_receiving'
    assert manager.tasks[payload['job_id']]['owner_id'] == 'teacher-a'


@pytest.mark.asyncio
async def test_markdown_import_job_exposes_all_d05_stages_and_persists_course(tmp_path, monkeypatch):
    manager, storage = import_manager(tmp_path, monkeypatch)

    created = await manager.create_markdown_import_job(
        filename='linear-algebra.md',
        content=b'# Linear Algebra\n\nVectors have magnitude and direction.\n',
        content_type='text/markdown',
        enqueue=False,
    )
    await manager._process_task(created['job_id'])

    summary = manager.get_task_summary(created['job_id'])
    assert summary['type'] == 'course_import'
    assert summary['status'] == 'completed'
    assert summary['progress'] == 100
    assert summary['course_name'] == 'Linear Algebra'
    assert [entry['phase'] for entry in summary['phase_history']] == [
        'material_receiving',
        'material_parsing',
        'source_retrieval',
        'content_generation',
        'quality_validation',
        'exporting',
        'completed',
    ]
    assert all(entry['status'] == 'completed' for entry in summary['phase_history'])
    assert summary['heartbeat_at']
    assert storage.load_course(created['course_id']) is not None
    assert not manager.import_source_path(created['job_id']).exists()


@pytest.mark.asyncio
async def test_markdown_import_validation_failure_is_visible_and_requests_replacement(tmp_path, monkeypatch):
    manager, _storage = import_manager(tmp_path, monkeypatch)
    created = await manager.create_markdown_import_job(
        filename='notes.md',
        content='只有正文，没有标题。'.encode(),
        content_type='text/markdown',
        enqueue=False,
    )

    await manager._process_task(created['job_id'])

    summary = manager.get_task_summary(created['job_id'])
    assert summary['status'] == 'failed'
    assert summary['progress'] < 100
    assert summary['current_phase'] == 'material_parsing'
    assert summary['error_code'] == 'markdown_heading_missing'
    assert '至少一个标题' in summary['error_user_message']
    assert summary['phase_history'][-1]['status'] == 'error'
    assert summary['recovery']['can_resume'] is False
    assert summary['recovery']['reason_code'] == 'replace_source_required'


@pytest.mark.asyncio
@pytest.mark.parametrize('cancelled_status', ['cancelled', 'canceled'])
async def test_cancelled_import_cannot_resume_even_with_reusable_source(
    tmp_path,
    monkeypatch,
    cancelled_status,
):
    manager, _storage = import_manager(tmp_path, monkeypatch)
    task_id = f'{cancelled_status}-import'
    manager.tasks[task_id] = {
        'id': task_id,
        'job_id': task_id,
        'course_id': 'course-1',
        'type': 'course_import',
        'status': cancelled_status,
        'phase': 'material_parsing',
        'import_retryable': True,
    }
    source_path = manager.import_source_path(task_id)
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_bytes(b'# preserved import source')

    recovery = manager.get_task_summary(task_id)['recovery']

    assert recovery['state'] == 'cancelled'
    assert recovery['can_resume'] is False
    assert recovery['reason_code'] == 'job_cancelled'
    with pytest.raises(TaskRecoveryConflict):
        await manager.resume_task(task_id)
    assert manager.tasks[task_id]['status'] == cancelled_status


@pytest.mark.asyncio
async def test_import_resume_reuses_parsed_checkpoint_after_transient_export_failure(tmp_path, monkeypatch):
    manager, storage = import_manager(tmp_path, monkeypatch)
    created = await manager.create_markdown_import_job(
        filename='linear-algebra.md',
        content=b'# Linear Algebra\n\nVectors have magnitude and direction.\n',
        content_type='text/markdown',
        enqueue=False,
    )
    original = manager._course_document_repository.create_imported_course
    calls = 0

    async def fail_once(course_id: str, *, imported_course: dict):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError('disk temporarily unavailable')
        return await original(course_id, imported_course=imported_course)

    monkeypatch.setattr(manager._course_document_repository, 'create_imported_course', fail_once)
    await manager._run_job(created['job_id'])

    failed = manager.get_task_summary(created['job_id'])
    assert failed['status'] == 'failed'
    assert failed['recovery']['can_resume'] is True
    assert failed['recovery']['checkpoint']['parsed_ready'] is True
    assert manager.import_checkpoint_path(created['job_id']).exists()

    resumed = await manager.resume_task(created['job_id'])
    assert resumed['status'] == 'resumed'
    await manager._process_task(created['job_id'])

    completed = manager.get_task_summary(created['job_id'])
    assert completed['status'] == 'completed'
    assert storage.load_course(created['course_id']) is not None
    assert calls == 2
