from copy import deepcopy
import json

import pytest
from ai_teacher_state import AITeacherRepository
from jobs.manager import TaskManager
from study import assistant
from .test_personal_study import setup_study, account, add_source, request_for


async def ready(setup_study):
    client, manager, repo, writer = setup_study
    owner, headers = account(client)
    material = client.post('/api/study/materials', headers=headers, json=request_for(add_source(client, headers))).json()
    await manager._run_job(material['task_id'])
    material = repo.get(owner, material['id'])
    section = material['revisions'][0]['sections'][0]
    payload = {'request_id': 'assistant-request-1234567', 'revision_id': material['revisions'][0]['id'],
               'section_id': section['id'], 'block_id': section['blocks'][0]['block_id'], 'quote': '有序分量',
               'text': '解释为什么要按分量相加', 'language': 'zh'}
    return client, manager, repo, writer, owner, headers, material, payload


@pytest.mark.asyncio
async def test_assistant_private_context_idempotent_stream_and_reopen(setup_study, monkeypatch):
    client, manager, repo, writer, owner, headers, material, payload = await ready(setup_study)
    before = deepcopy(repo.get(owner, material['id']))
    other, other_headers = account(client, 'student_b')
    path = '/api/study/materials/' + material['id'] + '/assistant'
    assert client.get(path, headers=other_headers).status_code == 404
    assert client.post(path, headers=other_headers, json=payload).status_code == 404
    assert client.get(path, headers={'X-User-Id': owner}).status_code == 401
    first = client.post(path, headers=headers, json=payload).json()
    repeated = client.post(path, headers=headers, json=payload).json()
    assert [m['message_id'] for m in first['messages']] == [m['message_id'] for m in repeated['messages']]
    assert len(first['messages']) == 2
    assert first['resource_ref']['type'] == 'personal_material' and first['course_id'] == ''
    task_id = first['messages'][-1]['task_ref']['task_id']
    assert client.get('/api/tasks/'+task_id, headers={'X-User-Id': owner}).status_code == 404
    assert client.post(path, headers=headers, json={**payload, 'text': 'another question'}).status_code == 409
    assert client.post(path, headers=headers, json={**payload, 'request_id': 'new-request-12345678', 'section_id': 'other'}).status_code == 409
    assert client.post(path, headers=headers, json={**payload, 'request_id': 'new-request-12345678', 'revision_id': 'old'}).status_code == 409
    calls = []
    async def model(prompt, system, **kwargs):
        context = json.loads(prompt); calls.append((context, system, kwargs))
        await kwargs['on_content_delta']('向量的和')
        assert assistant.ai_teacher_repository.material_conversation(owner, material['id'], payload['revision_id'])['messages'][-1]['content'] == '向量的和'
        return '向量的和是按分量相加。依据：第一章，资料.md。'
    monkeypatch.setattr(writer, '_call_llm', model)
    await manager._run_job(task_id)
    saved = client.get(path, headers=headers).json()
    assert saved['messages'][-1]['status'] == 'complete'
    assert '按分量相加' in saved['messages'][-1]['content']
    assert calls[0][0]['block']['title'] == '向量'
    assert calls[0][0]['source']['source_sha256'] == before['request']['source_sections'][0]['source_sha256']
    assert 'vector_plot' in calls[0][1] and calls[0][2]['max_attempts'] == 1
    assert repo.get(owner, material['id']) == before
    assert not repo.storage.load_data('learning_events.json')
    history = AITeacherRepository(assistant.ai_teacher_repository.root)
    assert history.material_conversation(owner, material['id'], payload['revision_id'])['messages'][-1]['status'] == 'complete'
    assert history.list_conversations(owner, material['id']) == []
    assert history.material_conversation(other, material['id'], payload['revision_id'])['messages'] == []


@pytest.mark.asyncio
async def test_failed_answer_keeps_fragment_and_explicit_same_task_resume_after_restart(setup_study, monkeypatch):
    client, manager, repo, writer, owner, headers, material, payload = await ready(setup_study)
    path = '/api/study/materials/' + material['id'] + '/assistant'
    turn = client.post(path, headers=headers, json=payload).json()
    task_id = turn['messages'][-1]['task_ref']['task_id']
    async def failed(prompt, system, **kwargs):
        await kwargs['on_content_delta']('这是一个真实片段。')
        raise RuntimeError('model interrupted')
    monkeypatch.setattr(writer, '_call_llm', failed)
    await manager._run_job(task_id)
    assert client.get(path, headers=headers).json()['messages'][-1]['content'] == '这是一个真实片段。'
    reloaded = TaskManager(repo.storage, writer, None, runtime_mode='isolated_test')
    assert reloaded.tasks[task_id]['resource_ref']['id'] == material['id']
    assert not reloaded.tasks[task_id]['request_snapshot']
    async def success(prompt, system, **kwargs): return '完整回复。'
    monkeypatch.setattr(writer, '_call_llm', success)
    await reloaded.resume_task(task_id)
    await reloaded._process_task(task_id)
    response = assistant.ai_teacher_repository.material_conversation(owner, material['id'], payload['revision_id'])['messages'][-1]
    assert response['content'] == '完整回复。' and response['status'] == 'complete'
    assert len(assistant.ai_teacher_repository.material_conversation(owner, material['id'], payload['revision_id'])['messages']) == 2
