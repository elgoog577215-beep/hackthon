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
from study.service import create_material, freeze_request, plan_prompt, validate_direct_outline, validate_plans


class SharedWriter:
    def __init__(self):
        self._generation_budget = CourseGenerationBudget.from_env()
        self.calls = []
        self.fail_section = None

    async def _call_llm(self, prompt, *args, **kwargs):
        request = json.loads(prompt.rpartition('\n')[2])
        if 'learning_goal_and_scene' in request:
            self.calls.append(('direct_outline', kwargs))
            return json.dumps({'sections': [
                {'title': 'C语言基础', 'learning_objective': '能解释变量、类型与表达式，并完成基础运算。'},
                {'title': '成像项目中的数据处理', 'learning_objective': '能用数组和函数组织简单的图像数据处理流程。'},
            ]})
        self.calls.append(('scope', kwargs))
        return json.dumps({'sections': [{'node_id': section['node_id'],
                         'knowledge_structure': [{'knowledge_points': [{'name': '向量', 'statement': '有序分量', 'source_refs': [{'evidence_id': section['blocks'][0]['evidence_id']}]}, {'name': '组合', 'statement': '分量的运算', 'source_refs': [{'evidence_id': section['blocks'][0]['evidence_id']}]}]}],
                         'learning_paths': [], 'knowledge_relations': [{'source_name': '向量', 'target_name': '组合', 'relation_type': 'applies_to', 'reason': '向量是组合的对象',
                                                 'source_refs': [{'evidence_id': section['blocks'][0]['evidence_id'], 'quote': section['blocks'][0]['text']}]}]}
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


def test_guest_entry_is_explicit_and_never_bypasses_school_auth(setup_study, monkeypatch):
    client, *_ = setup_study
    monkeypatch.delenv('LINGZHI_GUEST_STUDY_AUTH', raising=False)
    assert client.post('/api/study/auth/guest').status_code == 403
    monkeypatch.setenv('LINGZHI_GUEST_STUDY_AUTH', 'true')
    monkeypatch.setenv('QIZHI_AUTH_VERIFY_URL', 'https://identity.example/verify')
    assert client.post('/api/study/auth/guest').status_code == 403
    assert client.get('/api/study/auth/config').json()['guest_login_enabled'] is False


def test_guest_cookie_restores_identity_without_password_or_plaintext_storage(setup_study, monkeypatch):
    client, _, repo, _ = setup_study
    monkeypatch.setenv('LINGZHI_LOCAL_STUDY_AUTH', 'false')
    monkeypatch.setenv('LINGZHI_GUEST_STUDY_AUTH', 'true')
    config = client.get('/api/study/auth/config').json()
    assert config['guest_login_enabled'] and not config['local_login_enabled']
    response = client.post('/api/study/auth/guest')
    first = response.json()
    assert first['user']['role'] == 'student' and first['user']['guest']
    assert 'HttpOnly' in response.headers['set-cookie']
    assert 'SameSite=lax' in response.headers['set-cookie']
    assert 'Max-Age=7776000' in response.headers['set-cookie']
    assert response.headers['cache-control'] == 'no-store'
    assert client.post('/api/study/auth/guest').json() == first
    headers = {'Authorization': 'Bearer ' + first['token']}
    assert client.get('/api/study/auth/me', headers=headers).json() == first['user']
    ledger = repo.storage.load_data('study_accounts.json')
    assert ledger['users'] == {}
    assert first['token'] not in json.dumps(ledger)
    monkeypatch.setenv('LINGZHI_GUEST_STUDY_AUTH', 'false')
    assert client.get('/api/study/auth/me', headers=headers).status_code == 403


def test_guest_browsers_have_isolated_sources_and_cannot_claim_teacher_identity(setup_study, monkeypatch):
    from study.identity_middleware import LocalStudyIdentityMiddleware
    client, _, repo, _ = setup_study
    client.app.add_middleware(LocalStudyIdentityMiddleware, course_storage=repo.storage)
    monkeypatch.setenv('LINGZHI_GUEST_STUDY_AUTH', 'true')
    first = client.post('/api/study/auth/guest').json()
    headers = {'Authorization': 'Bearer ' + first['token']}
    source = add_source(client, headers)
    client.cookies.clear()
    second = client.post('/api/study/auth/guest').json()
    assert first['user']['id'] != second['user']['id']
    other = {'Authorization': 'Bearer ' + second['token'], 'X-User-Id': first['user']['id']}
    assert client.get('/api/study/sources', headers=other).json() == []
    assert client.get(f"/api/study/sources/{source['id']}/download", headers=other).status_code == 404
    assert client.post('/api/courses', headers=headers, json={}).status_code == 403
    assert client.get('/api/study/auth/me', headers=other).json()['id'] == second['user']['id']
    assert client.get('/api/study/auth/me', headers={'X-User-Id': first['user']['id']}).status_code == 401


def test_guest_cookie_cannot_resume_a_password_account_or_forged_identity(setup_study, monkeypatch):
    from study.auth import GUEST_COOKIE
    client, *_ = setup_study
    monkeypatch.setenv('LINGZHI_GUEST_STUDY_AUTH', 'true')
    owner, headers = account(client)
    for cookie in (headers['Authorization'][7:], owner, 'forged-session'):
        client.cookies.clear()
        client.cookies.set(GUEST_COOKIE, cookie)
        response = client.post('/api/study/auth/guest', json={'id': owner, 'role': 'teacher'})
        assert response.json()['user']['id'] != owner
        assert response.json()['user']['role'] == 'student'


def test_guest_logout_revokes_cookie_and_bearer_session(setup_study, monkeypatch):
    from study.auth import GUEST_COOKIE
    client, *_ = setup_study
    monkeypatch.setenv('LINGZHI_GUEST_STUDY_AUTH', 'true')
    guest = client.post('/api/study/auth/guest').json()
    headers = {'Authorization': 'Bearer ' + guest['token']}
    assert client.post('/api/study/auth/logout', headers=headers).status_code == 200
    assert not client.cookies.get(GUEST_COOKIE)
    assert client.get('/api/study/auth/me', headers=headers).status_code == 401
    assert client.post('/api/study/auth/guest').json()['user']['id'] != guest['user']['id']


def test_guest_session_expiry_creates_new_identity_and_https_cookie_is_secure(setup_study, monkeypatch):
    import study.auth as auth_module
    client, *_ = setup_study
    monkeypatch.setenv('LINGZHI_GUEST_STUDY_AUTH', 'true')
    now = auth_module.time.time()
    monkeypatch.setattr(auth_module.time, 'time', lambda: now)
    first = client.post('/api/study/auth/guest').json()
    monkeypatch.setattr(auth_module.time, 'time', lambda: now + auth_module.GUEST_SESSION_SECONDS + 1)
    assert client.post('/api/study/auth/guest').json()['user']['id'] != first['user']['id']
    with TestClient(client.app, base_url='https://testserver') as https:
        assert 'Secure' in https.post('/api/study/auth/guest').headers['set-cookie']


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


def test_student_upload_disables_file_and_batch_size_limits(setup_study, monkeypatch):
    client, _manager, repo, _writer = setup_study
    _owner, headers = account(client)
    saved_limits = []

    class UploadRepo:
        async def save_upload(self, _file, **kwargs):
            saved_limits.append(kwargs)
            return object()

    async def parsed_source(_source_repo, _asset):
        return {'status': 'parsed', 'sections': []}

    monkeypatch.setattr(StudyRepository, 'sources', lambda _self, _owner: UploadRepo())
    monkeypatch.setattr(study, 'parse_source', parsed_source)
    response = client.post('/api/study/sources/upload', headers=headers,
                           files={'file': ('small.pdf', b'not-parsed-in-this-test', 'application/pdf')})
    assert response.status_code == 200
    assert saved_limits == [{'upload_batch_id': 'study', 'enforce_limits': False}]


@pytest.mark.asyncio
async def test_direct_generation_builds_self_study_handout_without_sources(setup_study):
    client, manager, repo, writer = setup_study
    owner, headers = account(client)
    request = {
        'request_id': 'direct_generation_request_12345', 'title': 'C语言：面向图像项目',
        'purpose': 'systematic', 'selections': [],
        'level': 'beginner', 'time_minutes': 90,
        'requirements': '我想做一个华为成像项目，希望理论结合场景，并安排实战练习。', 'language': 'zh',
    }
    created = client.post('/api/study/materials', headers=headers, json=request)
    assert created.status_code == 200, created.text
    material = created.json()
    assert material['generation_mode'] == 'direct'
    assert material['sources'] == []

    await manager._process_task(material['task_id'])

    saved = StudyRepository(Storage(repo.storage._data_dir)).get(owner, material['id'])
    assert saved['status'] == 'completed'
    assert saved['request']['source_sections'] == []
    assert [section['title'] for section in saved['request']['generated_sections']] == ['C语言基础', '成像项目中的数据处理']
    assert len(saved['revisions'][0]['sections']) == 2
    assert all(section['complete'] and section['source'] == {'kind': 'ai_generated'}
               for section in saved['revisions'][0]['sections'])
    assert all('按学生的目标与场景直接生成' in call[1]['requirements']
               for call in writer.calls if call[0].startswith('study-section-'))
    writing_calls = [call[1] for call in writer.calls if call[0].startswith('study-section-')]
    for number, call in enumerate(writing_calls, 1):
        profile = call['course_context']['student_learning']
        assert profile['current_lecture'] == number
        assert profile['learner_request']['total_study_minutes'] == 90
        assert profile['learner_request']['goal_and_scene'] == request['requirements']
        assert [item['title'] for item in profile['course_map']] == ['C语言基础', '成像项目中的数据处理']
        assert all(item['learning_objective'] for item in profile['course_map'])
        assert '整门课程预计学习 90 分钟' in call['requirements']
        assert '预计阅读 90 分钟' not in call['requirements']
    assert writer.calls[0][0] == 'direct_outline'
    assert client.get(f"/api/study/materials/{material['id']}/export", headers=headers).status_code == 200
    assert client.get(f"/api/study/materials/{material['id']}", headers=headers).json()['sources'] == []

    async def answer_from_handout(prompt, _system, **_kwargs):
        context = json.loads(prompt)
        assert context['source'] == {'kind': 'ai_generated'}
        assert context['handout']
        return '我根据当前讲义解释这个问题。'

    writer._call_llm = answer_from_handout
    assistant = client.post(f"/api/study/materials/{material['id']}/assistant", headers=headers, json={
        'request_id': 'direct_handout_question_12345', 'revision_id': saved['revisions'][0]['id'],
        'section_id': saved['revisions'][0]['sections'][0]['id'], 'text': '请解释这讲的重点。', 'language': 'zh',
    })
    assert assistant.status_code == 200, assistant.text
    assistant_task_id = assistant.json()['messages'][-1]['task_ref']['task_id']
    await manager._process_task(assistant_task_id)
    conversation = client.get(f"/api/study/materials/{material['id']}/assistant", headers=headers).json()
    assert conversation['messages'][-1]['content'] == '我根据当前讲义解释这个问题。'


def test_legacy_material_mode_without_selected_ranges_falls_back_to_direct_generation(setup_study):
    client, _manager, _repo, _writer = setup_study
    _owner, headers = account(client)
    request = {
        'request_id': 'legacy_material_mode_without_scope_123', 'title': '没有资料',
        'purpose': 'systematic', 'generation_mode': 'materials', 'selections': [],
        'level': 'beginner', 'time_minutes': 60, 'requirements': '', 'language': 'zh',
    }
    response = client.post('/api/study/materials', headers=headers, json=request)
    assert response.status_code == 200, response.text
    assert response.json()['generation_mode'] == 'direct'


def test_generation_request_accepts_more_than_six_selected_ranges():
    request = study.GenerationRequest.model_validate({
        'request_id': 'many_ranges_request_12345', 'title': '多章节课程', 'purpose': 'systematic',
        'selections': [{'asset_id': 'mat-' + str(index).zfill(32), 'section_id': f'chapter-{index}'}
                       for index in range(1, 9)],
    })
    assert len(request.selections) == 8


def test_direct_outline_requires_unique_complete_lectures():
    assert len(validate_direct_outline(json.dumps({'sections': [
        {'title': '第一讲', 'learning_objective': '理解概念。'},
        {'title': '第二讲', 'learning_objective': '完成应用。'},
    ]}))) == 2
    with pytest.raises(ValueError, match='重复讲次'):
        validate_direct_outline(json.dumps({'sections': [
            {'title': '同一讲', 'learning_objective': '目标一。'},
            {'title': '同一讲', 'learning_objective': '目标二。'},
        ]}))


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
        last_handout = next(call[1] for call in reversed(writer.calls) if call[0].startswith('study-section-'))
        assert last_handout['completed_sections'] == []
        prior = last_handout['course_context']['completed_lecture_index']
        assert len(prior) == 1 and prior[0]['blocks'][0]['title'] == '向量'
        assert 'content' not in prior[0] and 'content' not in prior[0]['blocks'][0]

        assert ('应试讲义' if purpose == 'exam_prep' else '整体理解讲义') in last_handout['requirements']
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
    assert len(writer.calls) == 2  # each chapter once; concepts wait for saved handout
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
    assert len(writer.calls) == 5  # only the missing chapter, then two concept sections
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


@pytest.mark.asyncio
@pytest.mark.parametrize("with_sources", [False, True])
async def test_both_source_paths_save_concepts_bound_to_handout_and_allow_legacy_repair(setup_study, with_sources):
    client, manager, repo, writer = setup_study
    owner, headers = account(client)
    request = request_for(add_source(client, headers))
    if not with_sources:
        request["selections"] = []
    material = await create_material(manager, repo, owner, request)
    await manager._process_task(material["task_id"])
    saved = repo.get(owner, material["id"])
    assert saved["status"] == "completed"
    assert len(saved["plans"]) == len(saved["revisions"][0]["sections"]) == 2
    for plan, section in zip(saved["plans"], saved["revisions"][0]["sections"]):
        ref = plan["knowledge_relations"][0]["source_refs"][0]
        assert ref["kind"] == "handout" and ref["revision_id"] == saved["revisions"][0]["id"]
        assert ref["block_id"] == section["blocks"][0]["block_id"]
        assert "asset_id" not in ref and "filename" not in ref
    assert client.get(f"/api/study/materials/{material['id']}", headers=headers).json()["concepts_complete"]
    repo.save_note(owner, material["id"], material["task_id"], "不能丢失的笔记")
    repo.update(owner, material["id"], {"plans": []})  # pre-fix completed handout
    before = repo.get(owner, material["id"])
    calls = len(writer.calls)
    for _ in range(2):
        response = client.post(f"/api/study/materials/{material['id']}/continue", headers=headers)
        assert response.status_code == 200 and response.json()["task_id"] == material["task_id"]
    await manager._process_task(material["task_id"])
    after = repo.get(owner, material["id"])
    assert after["revisions"] == before["revisions"]
    assert after["notes"] == before["notes"]
    assert [call[0] for call in writer.calls[calls:]] == ["scope", "scope"]
    assert client.get(f"/api/study/materials/{material['id']}", headers=headers).json()["concepts_complete"]
    await manager.resume_task(material["task_id"])
    assert manager.tasks[material["task_id"]]["status"] == "completed"


@pytest.mark.asyncio
async def test_concept_failure_preserves_text_and_partial_maps_then_continues_only_missing(setup_study):
    client, manager, repo, writer = setup_study
    owner, headers = account(client)
    material = await create_material(manager, repo, owner, request_for(add_source(client, headers)))
    original_call = writer._call_llm
    async def fail_second(prompt, *args, **kwargs):
        result = await original_call(prompt, *args, **kwargs)
        if json.loads(result)["sections"][0]["node_id"] == "study-section-2":
            raise RuntimeError("interrupted concepts")
        return result
    writer._call_llm = fail_second
    await manager._run_job(material["task_id"])
    before = repo.get(owner, material["id"])
    assert before["status"] == "failed"
    assert all(section["complete"] for section in before["revisions"][0]["sections"])
    assert len(before["plans"]) == 1
    writer._call_llm = original_call
    calls = len(writer.calls)
    await manager.resume_task(material["task_id"])
    await manager._process_task(material["task_id"])
    after = repo.get(owner, material["id"])
    assert after["status"] == "completed" and len(after["plans"]) == 2
    assert after["revisions"][0]["sections"] == before["revisions"][0]["sections"]
    assert after["plans"][0] == before["plans"][0]
    assert [call[0] for call in writer.calls[calls:]] == ["scope"]


@pytest.mark.asyncio
async def test_legacy_concept_repair_recreates_missing_task_without_replacing_revision(setup_study):
    client, manager, repo, writer = setup_study
    owner, headers = account(client)
    material = await create_material(manager, repo, owner, request_for(add_source(client, headers)))
    await manager._process_task(material["task_id"])
    saved = repo.get(owner, material["id"])
    repo.update(owner, material["id"], {"plans": []})
    manager.tasks.pop(material["task_id"])
    assert client.post(f"/api/study/materials/{material['id']}/continue", headers=headers).status_code == 200
    await manager._process_task(material["task_id"])
    assert repo.get(owner, material["id"])["revisions"] == saved["revisions"]


def test_concept_evidence_uses_server_owned_block_refs_and_rejects_unknown_endpoints():
    from study.service import concept_source
    section = {"id": "s", "title": "概念", "blocks": [{"block_id": "b", "content": "A是B的前置条件。"}]}
    source = concept_source({"id": "r"}, section)
    plan = {"sections": [{"node_id": "s", "knowledge_structure": [{"knowledge_points": [{"name": "A"}, {"name": "B"}]}],
              "knowledge_relations": [{"source_name": "A", "target_name": "B", "relation_type": "prerequisite", "reason": "前置条件",
                  "source_refs": [{"evidence_id": "b", "quote": "模型虚构的原文"}]}]}]}
    validated = validate_plans(json.dumps(plan), [source])
    ref = validated[0]["knowledge_relations"][0]["source_refs"][0]
    assert ref["block_id"] == "b" and ref["revision_id"] == "r"
    assert "quote" not in ref
    invalid = deepcopy(plan)
    invalid["sections"][0]["knowledge_relations"][0]["source_refs"][0]["evidence_id"] = "invented"
    with pytest.raises(ValueError, match="来源"):
        validate_plans(json.dumps(invalid), [source])
    plan["sections"][0]["knowledge_relations"][0]["target_name"] = "不存在"
    with pytest.raises(ValueError, match="概念"):
        validate_plans(json.dumps(plan), [source])


@pytest.mark.asyncio
async def test_uploaded_materials_keep_the_same_goal_time_and_course_context(setup_study):
    client, manager, repo, writer = setup_study
    owner, headers = account(client)
    request = {**request_for(add_source(client, headers)), 'requirements': '用向量解释游戏角色的移动', 'time_minutes': 30}
    material = client.post('/api/study/materials', headers=headers, json=request).json()
    await manager._run_job(material['task_id'])
    calls = [kwargs for name, kwargs in writer.calls if name.startswith('study-section-')]
    assert calls
    for number, kwargs in enumerate(calls, 1):
        context = kwargs['course_context']['student_learning']
        assert context['learner_request']['goal_and_scene'] == request['requirements']
        assert context['current_lecture'] == number
        assert len(context['course_map']) == len(request['selections'])
        assert '整门课程预计学习 30 分钟' in kwargs['requirements']
        assert kwargs['outline_sections'][0]['blocks']  # Exact sources still reach the shared writer.
        assert '补充' in kwargs['requirements']
    assert repo.get(owner, material['id'])['status'] == 'completed'


@pytest.mark.asyncio
async def test_legacy_reading_aids_upgrade_is_explicit_and_failure_retains_old_map_and_notes(setup_study):
    client, manager, repo, writer = setup_study
    owner, headers = account(client)
    material = await create_material(manager, repo, owner, request_for(add_source(client, headers)))
    await manager._process_task(material['task_id'])
    saved = repo.get(owner, material['id'])
    legacy = deepcopy(saved['plans'])
    for plan in legacy:
        plan.pop('reading_schema_version')
        plan.pop('learning_paths')
    repo.update(owner, material['id'], {'plans': legacy})
    repo.save_note(owner, material['id'], material['task_id'], '保留我的理解')
    before = repo.get(owner, material['id'])
    count = len(writer.calls)
    for _ in range(2):
        value = client.get('/api/study/materials/' + material['id'], headers=headers).json()
        assert value['concepts_complete'] and not value['reading_tools_complete']
        assert set(value['reading_tool_states'].values()) == {'legacy'}
    assert len(writer.calls) == count
    original = writer._call_llm
    async def fail(*args, **kwargs):
        raise RuntimeError('provider failed during explicit upgrade')
    writer._call_llm = fail
    assert client.post('/api/study/materials/' + material['id'] + '/continue', headers=headers).status_code == 200
    await manager._run_job(material['task_id'])
    interrupted = repo.get(owner, material['id'])
    assert interrupted['revisions'] == before['revisions']
    assert interrupted['notes'] == before['notes']
    assert interrupted['plans'] == legacy
    writer._call_llm = original
    await manager.resume_task(material['task_id'])
    await manager._process_task(material['task_id'])
    after = repo.get(owner, material['id'])
    assert after['revisions'] == before['revisions'] and after['notes'] == before['notes']
    assert [call[0] for call in writer.calls[count:]] == ['scope', 'scope']
    assert client.get('/api/study/materials/' + material['id'], headers=headers).json()['reading_tools_complete']


def test_completed_lecture_index_cost_does_not_grow_with_prose_and_preserves_records():
    from study.service import completed_lecture_index
    sections = [{'id': 's1', 'title': '第一讲', 'complete': True, 'content': '正文' * 50000,
                 'draft_text': '完整原始响应' * 10000,
                 'blocks': [{'block_id': 'b1', 'content_type': 'definition', 'title': '变量', 'content': '长定义' * 10000}]},
                {'id': 's2', 'title': '第二讲', 'complete': False, 'fragment': '未完成片段'}]
    original = deepcopy(sections)
    index = completed_lecture_index(sections)
    assert index == [{'section_id': 's1', 'title': '第一讲', 'blocks': [{'block_id': 'b1', 'type': 'definition', 'title': '变量'}]}]
    assert sections == original
    sections[0]['content'] += '更多正文' * 100000
    assert completed_lecture_index(sections) == index
