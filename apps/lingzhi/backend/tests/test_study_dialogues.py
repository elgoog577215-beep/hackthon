from copy import deepcopy
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from ai_teacher_state import AITeacherRepository
from learning_records import LearningRecordRepository
from routers import study_dialogues as routes
from knowledge_mastery import build_knowledge_profile


@pytest.mark.asyncio
@pytest.mark.parametrize('fenced', [False, True])
async def test_model_accepts_wrapped_json_and_preserves_latex_without_retry(monkeypatch, fenced):
    from ai_service import ai_service
    raw = r'{"reply":"按 $\vec{u}$ 与 $\\vec{v}$ 组合。","draft":"结果是 (5,4)。"}'
    if fenced:
        raw = '```json\n' + raw + '\n```'
    call = AsyncMock(return_value=raw)
    monkeypatch.setattr(ai_service, '_call_llm', call)
    result = await routes._model({'source': 'u=(1,2), v=(2,1)'}, action='discuss', language='zh')
    assert result == {'reply': r'按 $\vec{u}$ 与 $\vec{v}$ 组合。', 'draft': '结果是 (5,4)。'}
    assert call.await_count == 1
    assert call.call_args.kwargs['request_timeout_seconds'] == 120
    assert call.call_args.kwargs['max_attempts'] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('raw', ['not JSON', '{"reply":"unfinished"',
                                '{"reply":"answer","draft":""}', '["reply","draft"]'])
async def test_model_still_rejects_incomplete_or_invalid_contract_without_retry(monkeypatch, raw):
    from ai_service import ai_service
    from fastapi import HTTPException
    call = AsyncMock(return_value=raw)
    monkeypatch.setattr(ai_service, '_call_llm', call)
    with pytest.raises(HTTPException) as error:
        await routes._model({}, action='discuss', language='zh')
    assert error.value.status_code == 503
    assert call.await_count == 1


@pytest.fixture
def env(tmp_path, monkeypatch):
    course = {"course_id":"c", "current_course_version_id":"cv1", "nodes":[{"node_id":"n", "node_name":"Division", "node_level":2, "node_content":"Integer division discards fractional parts."}],
              "course_knowledge_base":{"lifecycle_status":"active", "revision_id":"kb", "knowledge_points":[{"knowledge_id":"k", "revision_id":"kr", "name":"Division", "statement":"Integer division discards fractional parts.", "meta_question":"Explain integer division and give an example.", "status":"active", "granularity_status":"atomic", "course_block_refs":["b"]}]}}
    conversations = AITeacherRepository(tmp_path / "chats")
    records = LearningRecordRepository(tmp_path / "notes")
    monkeypatch.setattr(routes, 'ai_teacher_repository', conversations)
    monkeypatch.setattr(routes, 'learning_record_repository', records)
    monkeypatch.setattr(routes, 'get_course_or_404', AsyncMock(side_effect=lambda _:deepcopy(course)))
    monkeypatch.setattr(routes, '_base', lambda c:c['course_knowledge_base'])
    monkeypatch.setattr(routes, '_source', lambda c,n,q,a:(c['nodes'][0], {'block_id':'b', 'block_revision_id':'br'}))
    model = AsyncMock(return_value={"reply":"Consider the fractional part.", "draft":"A single organized note."})
    monkeypatch.setattr(routes, '_model', model)
    events = []
    monkeypatch.setattr(routes, 'record_learning_event', lambda **kw: events.append({"event_id":f"e{len(events)}", "created_at":f"2026-10-11T12:00:{len(events):02}Z", **kw}) or events[-1])
    from routers import learning_records
    monkeypatch.setattr(learning_records, '_record_event', lambda *a, **kw:None)
    app = FastAPI()
    app.include_router(routes.router, prefix='/courses/{course_id}')
    client = TestClient(app)
    def open_note(user='u', **extra):
        return client.post('/courses/c/study-dialogues/open', headers={'X-User-Id':user}, json={'kind':'note','node_id':'n','quote':'Integer division','course_version_id':'cv1', **extra})
    def command(conversation, action, user='u', request_id=None, **extra):
        return client.post(f"/courses/c/study-dialogues/{conversation['conversation_id']}/command", headers={'X-User-Id':user}, json={'expected_revision':conversation['study_workspace']['revision'], 'request_id':request_id or f"request-{conversation['study_workspace']['revision']}-{action}", 'action':action, **extra})
    return open_note, command, records, model, events, course


def test_source_reuses_one_conversation_and_one_note_across_saves(env):
    open_note, command, records, model, events, _ = env
    first = open_note().json()
    assert open_note().json()['conversation_id'] == first['conversation_id']
    assert records.list('u','c') == []
    first = command(first,'draft',text='My first explanation').json()
    first = command(first,'save').json()
    note_id = first['study_workspace']['record_id']
    assert open_note(record_id=note_id).json()['conversation_id'] == first['conversation_id']
    first = command(first,'draft',text='A revised explanation').json()
    first = command(first,'save').json()
    assert len(records.list('u','c')) == 1
    assert records.list('u','c')[0]['content'] == 'A revised explanation'
    assert len(first['study_workspace']['versions']) == 2
    first = command(first,'restore',version=1).json()
    assert first['study_workspace']['draft'] == 'My first explanation'
    assert records.list('u','c')[0]['content'] == 'A revised explanation'
    assert not events
    model.assert_not_called()


def test_refinement_is_a_proposal_and_requires_adoption_then_save(env):
    open_note, command, records, model, *_ = env
    first = open_note().json()
    first = command(first,'draft',text='My words').json()
    first = command(first,'refine').json()
    assert first['study_workspace']['draft'] == 'My words'
    assert first['study_workspace']['proposal'] == 'A single organized note.'
    assert records.list('u','c') == []
    first = command(first,'adopt').json()
    assert first['study_workspace']['draft'] == 'A single organized note.'
    first = command(first,'save').json()
    assert len(records.list('u','c')) == 1
    assert records.list('u','c')[0]['metadata']['study_assisted'] is True


def test_dialogue_updates_one_draft_without_saving_or_scoring(env):
    open_note, command, records, model, events, _ = env
    first = open_note().json()
    first = command(first, 'discuss', text='My first understanding').json()
    assert first['study_workspace']['draft'] == 'A single organized note.'
    assert first['study_workspace']['proposal'] is None
    assert first['study_workspace']['solution_seen'] is True
    assert not records.list('u', 'c') and not events
    first = command(first, 'draft', text='My edited version').json()
    model.return_value = {'reply':'Added your example.', 'draft':'My edited version with an example.'}
    first = command(first, 'discuss', text='Include this example').json()
    assert model.call_args.args[0]['draft'] == 'My edited version'
    assert first['study_workspace']['draft'] == 'My edited version with an example.'
    assert not records.list('u', 'c')
    first = command(first, 'save').json()
    assert len(records.list('u', 'c')) == 1
    assert records.list('u', 'c')[0]['content'] == first['study_workspace']['draft']


def test_clarification_does_not_clear_existing_draft(env):
    open_note, command, _, model, *_ = env
    first = command(open_note().json(), 'draft', text='Keep this understanding').json()
    model.return_value = {'reply':'Which example do you mean?', 'draft':None}
    first = command(first, 'discuss', text='What about that example?').json()
    assert first['study_workspace']['draft'] == 'Keep this understanding'


def test_draft_changed_in_another_client_blocks_late_ai_overwrite(env):
    open_note, command, _, model, *_ = env
    first = open_note().json()
    async def simultaneous_edit(*args, **kwargs):
        routes.ai_teacher_repository.update_study_conversation('u','c',first['conversation_id'],1,
            lambda current:current['study_workspace'].update(draft='Newer human edit'))
        return {'reply':'Late response', 'draft':'Outdated generated draft'}
    model.side_effect = simultaneous_edit
    assert command(first, 'discuss', text='Explain').status_code == 409
    latest = routes.ai_teacher_repository.get_conversation('u','c',first['conversation_id'])
    assert latest['study_workspace']['draft'] == 'Newer human edit'


def test_isolation_conflicts_idempotence_and_source_changes(env):
    open_note, command, records, model, events, course = env
    first = open_note().json()
    assert command(first,'draft',user='other',text='attack').status_code == 404
    changed = command(first,'draft',text='Mine',request_id='same-request').json()
    assert command(first,'draft',text='Mine',request_id='same-request').status_code == 200
    assert command(first,'draft',text='Other',request_id='same-request').status_code == 409
    assert command(first,'draft',text='Stale').status_code == 409
    course['current_course_version_id'] = 'cv2'
    assert command(changed,'save').status_code == 409
    assert not records.list('u','c')


def test_checks_update_only_exact_current_knowledge_and_dedupe_same_question(env):
    open_note, command, records, model, events, course = env
    first = open_note().json()
    model.return_value = {'passed':True,'confidence':.93,'feedback':'Your example supports the rule.'}
    assert command(first,'check',knowledge_id='unknown',text='5 / 2 is 2').status_code == 409
    first = command(first,'check',knowledge_id='k',text='5 / 2 is 2 because both operands are integers.').json()
    profile = lambda:build_knowledge_profile(course['course_knowledge_base'],course_id='c',course_version_id='cv1',user_id='u',attempts=[],events=events)['nodes'][0]
    assert profile()['mastery'] == 66.7
    assert profile()['independent_count'] == 1
    first = command(first,'check',knowledge_id='k',text='5 / 2 is 2.').json()
    assert profile()['assessment_count'] == 1
    assert profile()['independent_count'] == 0
    assert events[-1]['result']['support_level'] == 1
    assert records.list('u','c') == []


def test_late_model_response_does_not_write_newer_source(env):
    open_note, command, records, model, events, course = env
    first = open_note().json()
    async def mutate(*args, **kwargs):
        course['current_course_version_id'] = 'cv2'
        return {'reply':'late','draft':None}
    model.side_effect = mutate
    assert command(first,'discuss',text='Help').status_code == 409
    assert not records.list('u','c') and not events


def test_full_ai_draft_is_not_mastery_evidence_even_from_another_note(env):
    open_note, command, records, model, events, course = env
    first = command(open_note().json(), 'refine').json()
    second = open_note(quote='Another selection').json()
    model.return_value = {'passed':True,'confidence':.96,'feedback':'Matches the answer.'}
    response = command(second,'check',knowledge_id='k',text='Copied explanation')
    assert response.status_code == 200
    assert events[-1]['result']['solution_revealed'] is True
    profile = build_knowledge_profile(course['course_knowledge_base'],course_id='c',course_version_id='cv1',user_id='u',attempts=[],events=events)
    assert profile['nodes'][0]['mastery'] is None
    assert not records.list('u','c')


def test_external_note_edit_requires_explicit_refresh_before_overwrite(env):
    open_note, command, records, *_ = env
    first = command(open_note().json(),'draft',text='Original').json()
    first = command(first,'save').json()
    note = records.list('u','c')[0]
    records.update('u','c',note['record_id'],expected_revision=note['revision'],changes={'content':'Edited elsewhere'})
    first = command(first,'draft',text='My local draft').json()
    assert command(first,'save').status_code == 409
    refreshed = command(first,'refresh').json()
    assert refreshed['study_workspace']['versions'][-1]['content'] == 'Edited elsewhere'
    assert refreshed['study_workspace']['draft'] == 'My local draft'
    assert command(refreshed,'save').status_code == 200
