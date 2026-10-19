from __future__ import annotations

import asyncio
import json
from copy import deepcopy

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from course_generation_budget import CourseGenerationBudget
from dependencies import require_task_manager
from jobs.manager import TaskManager
from material_parser import parse_material_asset
from qizhi_auth import QizhiIdentityMiddleware, QizhiIdentityVerifier
from routers import study, tasks as tasks_router
from storage import Storage
from study.auth import LocalStudyAuth
from study.repository import StudyRepository, StudyConflict
from study.service import create_material, freeze_request, plan_prompt, validate_plans


class SharedWriter:
    def __init__(self):
        self._generation_budget = CourseGenerationBudget.from_env()
        self.calls = []
        self.fail_section = None

    async def _call_llm(self, prompt, *args, **kwargs):
        request = json.loads(prompt.rpartition('\n')[2])
        self.calls.append(('scope', kwargs))
        return json.dumps({'sections': [{'node_id': section['node_id'],
                         'knowledge_structure': [{'knowledge_points': [{'name': '向量', 'statement': '有序分量'}, {'name': '组合', 'statement': '分量的运算'}]}],
                         'knowledge_relations': [{'source_name': '向量', 'target_name': '组合', 'relation_type': 'applies_to', 'reason': '向量是组合的对象',
                                                 'source_refs': [{'evidence_id': section['blocks'][0]['evidence_id']}]}]}
                        for section in request['source_sections']]})

    async def generate_teacher_handout(self, **kwargs):
        section_id = kwargs['outline_sections'][0]['node_id']
        self.calls.append((section_id, kwargs))
        body = (f'<!-- section:{section_id} -->\n'
                '<!-- block:{"type":"definition","title":"向量","key":"d","knowledge":["向量"]} -->\n'
                '向量用有序分量表示。\n'
                '<!-- block:{"type":"exercise","title":"自测","key":"q"} -->\n求两向量的和。\n'
                '<!-- block:{"type":"answer","title":"参考解答","key":"a","answer_to":"q"} -->\n按分量相加。\n')
        await kwargs['on_content_delta'](body)
        if section_id == self.fail_section:
            raise RuntimeError('provider interrupted')
        return {'text': body, 'section_ids': [section_id], 'telemetry': []}


@pytest.fixture
def setup_study(tmp_path, monkeypatch):
    import jobs.manager as jobs
    import storage as storage_module
    import learning_events
    import study.assistant as personal_assistant
    from ai_teacher_state import AITeacherRepository
    monkeypatch.setattr(personal_assistant, 'ai_teacher_repository', AITeacherRepository(tmp_path / 'ai_teacher'))
    monkeypatch.setenv('LINGZHI_LOCAL_STUDY_AUTH', 'true')
    monkeypatch.delenv('QIZHI_AUTH_VERIFY_URL', raising=False)
    monkeypatch.setenv('GIT_AUTO_SYNC_ENABLED', 'false')
    monkeypatch.setattr(jobs, 'TASKS_FILE', tmp_path / 'generation_jobs.json')
    local_storage = Storage(str(tmp_path / 'data'))
    monkeypatch.setattr(study, 'storage', local_storage)
    monkeypatch.setattr(storage_module, 'storage', local_storage)
    monkeypatch.setattr(learning_events, 'storage', local_storage)
    writer = SharedWriter()
    manager = TaskManager(local_storage, writer, None, runtime_mode='isolated_test')
    repo = StudyRepository(local_storage)
    app = FastAPI()
    app.include_router(study.router, prefix='/api')
    app.include_router(tasks_router.router, prefix='/api')
    app.dependency_overrides[require_task_manager] = lambda: manager
    app.dependency_overrides[study.repository] = lambda: repo
    return TestClient(app), manager, repo, writer


def account(client, username='student_a'):
    result = client.post('/api/study/auth/register', json={'username': username, 'password': 'Testing2026!'})
    assert result.status_code == 200
    data = result.json()
    return data['user']['id'], {'Authorization': 'Bearer ' + data['token']}


def request_for(source, purpose='systematic'):
    return {'request_id': 'idempotent_request_12345', 'title': '两章讲义', 'purpose': purpose,
            'level': 'beginner', 'time_minutes': 60, 'requirements': '', 'language': 'zh',
            'selections': [{'asset_id': source['id'], 'section_id': section['id']} for section in source['sections']]}


def add_source(client, headers):
    result = client.post('/api/study/sources/text', headers=headers,
                         json={'title': '资料.md', 'content': '# 第一章\n\n向量及线性组合。\n\n# 第二章\n\n矩阵与方程组。'})
    assert result.status_code == 200
    return result.json()


def test_local_identity_password_session_and_header_spoof(setup_study):
    client, manager, repo, _writer = setup_study
    owner, headers = account(client)
    assert client.get('/api/study/auth/me', headers={'X-User-Id': owner}).status_code == 401
    assert client.get('/api/study/auth/me', headers={**headers, 'X-User-Id': 'teacher-forged'}).json()['id'] == owner
    assert client.post('/api/study/auth/login', json={'username': 'student_a', 'password': 'wrong_password'}).status_code == 401
    accounts = repo.storage.load_data('study_accounts.json')
    assert 'Testing2026!' not in json.dumps(accounts)
    assert headers['Authorization'][7:] not in json.dumps(accounts)
    assert client.post('/api/study/auth/register', json={'username': 'evil', 'password': 'Testing2026!', 'role': 'teacher'}).status_code == 422
    assert client.post('/api/study/auth/logout', headers={'Authorization': headers['Authorization'].replace('Bearer ', 'bearer ')}).status_code == 200
    assert client.get('/api/study/auth/me', headers=headers).status_code == 401


def test_file_upload_parses_downloads_and_rejects_unsupported_files(setup_study):
    client, _manager, _repo, _writer = setup_study
    _owner, headers = account(client)
    content = '# 向量\n\nu=(1,2)，v=(2,1)，u+2v=(5,4)。'.encode('utf-8')
    uploaded = client.post('/api/study/sources/upload', headers=headers,
                           files={'file': ('向量.md', content, 'text/markdown')})
    assert uploaded.status_code == 200
    source = uploaded.json()
    assert source['status'] == 'parsed' and source['sections']
    downloaded = client.get(f"/api/study/sources/{source['id']}/download", headers=headers)
    assert downloaded.status_code == 200 and downloaded.content == content
    assert client.post('/api/study/sources/upload', headers=headers,
                       files={'file': ('bad.exe', b'unsupported', 'application/octet-stream')}).status_code == 422


def test_students_cannot_read_sources_materials_notes_or_tasks_of_others(setup_study):
    client, manager, repo, _writer = setup_study
    owner, headers = account(client)
    _other, other_headers = account(client, 'student_b')
    source = add_source(client, headers)
    assert len(client.get('/api/study/sources', headers=headers).json()) == 1
    assert client.get('/api/study/sources', headers=other_headers).json() == []
    assert client.get(f"/api/study/sources/{source['id']}/download", headers=other_headers).status_code == 404
    assert client.get(f"/api/study/sources/{source['id']}/download", headers=headers).status_code == 200
    material = client.post('/api/study/materials', headers=headers, json=request_for(source)).json()
    assert manager.tasks[material['task_id']]['owner_id'] == owner
    assert manager.tasks[material['task_id']]['course_id'] == ''
    assert client.get('/api/study/materials', headers=other_headers).json() == []
    for path in ['', '/export']:
        assert client.get(f"/api/study/materials/{material['id']}{path}", headers=other_headers).status_code == 404
    assert client.post(f"/api/study/materials/{material['id']}/continue", headers=other_headers).status_code == 404
    note = {'revision_id': material['task_id'], 'content': '私有笔记'}
    assert client.put(f"/api/study/materials/{material['id']}/note", headers=other_headers, json=note).status_code == 404
    assert client.post('/api/study/materials', headers=other_headers, json=request_for(source)).status_code == 422


@pytest.mark.asyncio
async def test_shared_writer_purposes_completed_sections_save_notes_and_reopen(setup_study):
    client, manager, repo, writer = setup_study
    owner, headers = account(client)
    source = add_source(client, headers)
    for purpose in ('systematic', 'exam_prep'):
        request = request_for(source, purpose)
        request['request_id'] += purpose
        material = await create_material(manager, repo, owner, request)
        await manager._process_task(material['task_id'])
        saved = StudyRepository(Storage(repo.storage._data_dir)).get(owner, material['id'])
        assert saved['status'] == 'completed'
        assert len(saved['revisions'][0]['sections']) == 2
        assert all(section['complete'] for section in saved['revisions'][0]['sections'])
        assert all(section['blocks'][-1]['answer_to'] == section['blocks'][1]['block_id'] for section in saved['revisions'][0]['sections'])
        assert '应试讲义' in writer.calls[-1][1]['requirements'] if purpose == 'exam_prep' else '整体理解讲义' in writer.calls[-1][1]['requirements']
        repo.save_note(owner, material['id'], material['task_id'], '理解记录')
        repo.save_note(owner, material['id'], material['task_id'], '理解记录')
        assert StudyRepository(Storage(repo.storage._data_dir)).get(owner, material['id'])['notes'][material['task_id']]['content'] == '理解记录'
        with pytest.raises(StudyConflict):
            repo.save_note(owner, material['id'], 'unknown-revision', '错误版本')
    assert len(repo.list(owner)) == 2
    events = repo.storage.load_data('learning_events.json')
    assert len(events) == 2
    assert all(event['entity_type'] == 'personal_material' and event['user_id'] == owner for event in events)
    assert all(event['result'] == {'saved': True} and not event['evidence'] for event in events)
    assert not list((repo.sources(owner).root.parent.parent / 'courses').glob('*.json'))


@pytest.mark.asyncio
async def test_duplicate_requests_and_task_write_failure_keep_same_id(setup_study, monkeypatch):
    client, manager, repo, writer = setup_study
    owner, headers = account(client)
    request = request_for(add_source(client, headers))
    material, repeated = await asyncio.gather(create_material(manager, repo, owner, request), create_material(manager, repo, owner, request))
    assert material['id'] == repeated['id']
    assert len(manager.tasks) == 1
    with pytest.raises(StudyConflict):
        await create_material(manager, repo, owner, {**request, 'purpose': 'exam_prep'})
    request['request_id'] = 'recovery_request_123456'
    original = manager.create_task
    async def fail(*args, **kwargs):
        raise OSError('disk unavailable')
    monkeypatch.setattr(manager, 'create_task', fail)
    with pytest.raises(OSError):
        await create_material(manager, repo, owner, request)
    reserved = repo.list(owner)[0]
    monkeypatch.setattr(manager, 'create_task', original)
    result = await create_material(manager, repo, owner, request)
    assert result['id'] == reserved['id']
    assert result['task_id'] == reserved['task_id']


@pytest.mark.asyncio
async def test_interruption_manual_resume_preserves_completed_chapter_without_retry(setup_study):
    client, manager, repo, writer = setup_study
    owner, headers = account(client)
    material = await create_material(manager, repo, owner, request_for(add_source(client, headers)))
    writer.fail_section = 'study-section-2'
    await manager._run_job(material['task_id'])
    interrupted = repo.get(owner, material['id'])
    first = deepcopy(interrupted['revisions'][0]['sections'][0])
    assert first['complete']
    assert not interrupted['revisions'][0]['sections'][1]['complete']
    assert len(writer.calls) == 3  # one scope, each chapter exactly once
    assert manager.tasks[material['task_id']]['status'] == 'failed'
    await manager._reconcile_task_after_restart(material['task_id'])
    assert manager.tasks[material['task_id']]['status'] == 'failed'
    writer.fail_section = None
    # A real new manager reloads the compact terminal ledger: no snapshot.
    reloaded = TaskManager(repo.storage, writer, None, runtime_mode='isolated_test')
    assert not reloaded.tasks[material['task_id']]['request_snapshot']
    await reloaded.resume_task(material['task_id'])
    await reloaded._process_task(material['task_id'])
    assert repo.get(owner, material['id'])['revisions'][0]['sections'][0] == first
    assert len(writer.calls) == 4  # explicit continuation writes only the missing chapter
    assert repo.get(owner, material['id'])['status'] == 'completed'


@pytest.mark.asyncio
async def test_restart_pauses_same_task_and_keeps_frozen_sources(setup_study):
    client, manager, repo, writer = setup_study
    owner, headers = account(client)
    source = add_source(client, headers)
    material = await create_material(manager, repo, owner, request_for(source))
    original = deepcopy(material['request'])
    asset = repo.sources(owner).get_asset(source['id'])
    repo.sources(owner).source_path(asset).write_text('changed on disk', encoding='utf-8')
    manager.tasks[material['task_id']]['status'] = 'running'
    assert not await manager._reconcile_task_after_restart(material['task_id'])
    assert manager.tasks[material['task_id']]['status'] == 'paused'
    assert writer.calls == []
    assert repo.get(owner, material['id'])['request'] == original


@pytest.mark.asyncio
async def test_continuation_reset_without_new_output_does_not_erase_saved_fragment(setup_study, monkeypatch):
    client, manager, repo, writer = setup_study
    owner, headers = account(client)
    material = await create_material(manager, repo, owner, request_for(add_source(client, headers)))
    writer.fail_section = 'study-section-2'
    await manager._run_job(material['task_id'])
    previous = deepcopy(repo.get(owner, material['id'])['revisions'][0]['sections'])
    assert previous[1]['content']
    async def reset_then_fail(**kwargs):
        await kwargs['on_content_reset']()
        raise RuntimeError('provider timed out before new output')
    monkeypatch.setattr(writer, 'generate_teacher_handout', reset_then_fail)
    await manager.resume_task(material['task_id'])
    await manager._run_job(material['task_id'])
    assert repo.get(owner, material['id'])['revisions'][0]['sections'] == previous
    assert manager.tasks[material['task_id']]['status'] == 'failed'


def test_source_reference_and_nonempty_scope_contract(setup_study):
    client, manager, repo, writer = setup_study
    owner, headers = account(client)
    frozen = freeze_request(repo, owner, request_for(add_source(client, headers)))
    bad = {'sections': [{'node_id': section['node_id'], 'knowledge_structure': [{'knowledge_points': [{'name': 'A'}]}],
                        'knowledge_relations': [{'source_refs': [{'evidence_id': 'made-up'}]}]} for section in frozen['source_sections']]}
    with pytest.raises(ValueError, match='来源'):
        validate_plans(json.dumps(bad), frozen['source_sections'])
    request = request_for(add_source(client, headers))
    request['selections'] *= 2
    with pytest.raises(ValueError, match='重复'):
        freeze_request(repo, owner, request)


def test_book_title_keeps_real_chapter_ranges_and_fenced_planning_json(setup_study):
    client, manager, repo, _writer = setup_study
    owner, headers = account(client)
    source = client.post('/api/study/sources/text', headers=headers,
                         json={'title': '书本.md', 'content': '# 书名\n\n导言。\n\n## 第一章\n\n向量。\n\n## 第二章\n\n矩阵。'}).json()
    assert [section['title'] for section in source['sections']] == ['书名', '第一章', '第二章']
    request = request_for(source)
    request['selections'] = request['selections'][1:]
    frozen = freeze_request(repo, owner, request)
    projection = json.loads(plan_prompt(frozen).rpartition('\n')[2])
    assert [section['node_id'] for section in projection['source_sections']] == ['study-section-1', 'study-section-2']
    assert all(set(block) == {'evidence_id', 'text', 'locator'} for section in projection['source_sections'] for block in section['blocks'])
    plans = {'sections': [{'node_id': section['node_id'], 'knowledge_structure': [{'knowledge_points': [{'name': '概念'}]}],
                           'knowledge_relations': []} for section in frozen['source_sections']]}
    assert validate_plans('```json\n' + json.dumps(plans) + '\n```', frozen['source_sections']) == plans['sections']


def test_legacy_teacher_task_headers_cannot_observe_control_or_clear_personal_jobs(setup_study):
    client, manager, repo, _writer = setup_study
    owner, headers = account(client)
    material = client.post('/api/study/materials', headers=headers, json=request_for(add_source(client, headers))).json()
    task_id = material['task_id']
    spoof = {'X-User-Id': owner}
    assert client.get('/api/tasks', headers=spoof).json() == []
    assert client.get(f'/api/tasks/{task_id}', headers=spoof).status_code == 404
    assert client.get(f'/api/tasks/{task_id}/recovery', headers=spoof).status_code == 404
    for operation in ['pause', 'resume']:
        assert client.post(f'/api/tasks/{task_id}/{operation}', headers=spoof).status_code == 404
    assert client.delete(f'/api/tasks/{task_id}', headers=spoof).status_code == 404
    manager.tasks[task_id]['status'] = 'failed'
    assert client.delete('/api/tasks/failed', headers=spoof).json()['removed'] == 0
    assert client.delete('/api/tasks?scope=invalid', headers=spoof).json()['removed'] == 0
    assert task_id in manager.tasks
    assert client.get('/api/study/materials/'+material['id'], headers=headers).status_code == 200


def test_qizhi_student_scope_verified_without_teacher_access(monkeypatch):
    class Response:
        status_code = 200
        def json(self):
            return {'success': True, 'data': {'id': 'real-student', 'role': 'student'}}
    monkeypatch.setattr('qizhi_auth.requests.get', lambda *args, **kwargs: Response())
    app = FastAPI()
    app.add_middleware(QizhiIdentityMiddleware, verifier=QizhiIdentityVerifier('http://identity/current'))
    @app.get('/api/study/auth/me')
    def me(request: Request):
        return {'id': request.state.qizhi_identity.actor_id}
    @app.get('/api/teacher/courses/private')
    def teacher_only():
        return {'secret': 'teacher'}
    client = TestClient(app)
    headers = {'Authorization': 'Bearer verified', 'X-User-Id': 'spoofed'}
    assert client.get('/api/study/auth/me', headers=headers).json() == {'id': 'qizhi:real-student'}
    assert client.get('/api/teacher/courses/private', headers=headers).status_code == 403


def test_material_summary_preserves_explicit_course_links_without_exposing_source_text():
    material = {
        "id": "own-material", "title": "个人复习", "purpose": "exam_prep",
        "status": "completed", "task_id": "task", "updated_at": "now",
        "request": {"source_sections": [
            {"course_origin": {"course_id": "course-b"}, "text": "private"},
            {"course_origin": {"course_id": "course-a", "release_id": "old-version"}},
            {"course_origin": {"course_id": "course-b"}},
            {"course_origin": None}, {"course_origin": {"course_id": 42}},
        ]},
    }
    result = study.material_summary(material)
    assert result["source_course_ids"] == ["course-a", "course-b"]
    assert "request" not in result
    assert "private" not in json.dumps(result)
    material.pop("request")
    assert study.material_summary(material)["source_course_ids"] == []
