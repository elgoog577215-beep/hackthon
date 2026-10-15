from copy import deepcopy

from backend.tests.test_question_bank_api import _client, _rebuild, DeterministicAssessmentOrchestrator
from routers import question_bank


def test_append_preserves_every_existing_question_and_answer_then_fill_does_not_duplicate(monkeypatch,tmp_path):
    client, repo = _client(monkeypatch,tmp_path)
    _rebuild(client,'original-bank')
    before=deepcopy(repo.load_bundle('course-api'))
    assert len(before['items'])==3
    response=client.post('/api/courses/course-api/question-bank/rebuild',headers={'X-User-Id':'teacher-1'},json={
        'request_id':'append-two-items','scope':'nodes','node_ids':['node-1'],
        'questions_per_lesson':2,'append_only':True,'mode':'full'})
    assert response.status_code==202,response.text
    job=client.get(response.json()['status_url'],headers={'X-User-Id':'teacher-1'}).json()
    assert job['status']=='completed',job
    after=repo.load_bundle('course-api')
    assert len(after['items'])==5
    by_revision={i['revision_id']:i for i in after['items']}
    assert all(by_revision[i['revision_id']]==i for i in before['items'])
    assert all(after['solution_envelopes'][k]==v for k,v in before['solution_envelopes'].items())
    response=client.post('/api/courses/course-api/question-bank/rebuild',headers={'X-User-Id':'teacher-1'},json={
        'request_id':'fill-already-five','scope':'nodes','node_ids':['node-1'],
        'questions_per_lesson':5,'append_only':False})
    assert response.status_code==202,response.text
    job=client.get(response.json()['status_url'],headers={'X-User-Id':'teacher-1'}).json()
    assert job['status']=='completed',job
    assert repo.load_bundle('course-api')['items']==after['items']


def test_quantity_retry_uses_frozen_slots_and_only_generates_missing_item(monkeypatch,tmp_path):
    orchestrator=DeterministicAssessmentOrchestrator()
    client,repo=_client(monkeypatch,tmp_path,orchestrator=orchestrator)
    _rebuild(client,'baseline-three')
    orchestrator.fail_node_id='node-1'
    body={'request_id':'append-partial','scope':'nodes','node_ids':['node-1'],'questions_per_lesson':3,'append_only':True}
    first=client.post('/api/courses/course-api/question-bank/rebuild',headers={'X-User-Id':'teacher-1'},json=body).json()
    job=client.get(first['status_url'],headers={'X-User-Id':'teacher-1'}).json()
    assert job['status']=='failed',job
    partial=deepcopy(repo.load_bundle('course-api'))
    assert len(partial['items'])==5
    orchestrator.fail_node_id=''
    body.update(request_id='retry-partial',quantity_batch_id=first['job_id'])
    second=client.post('/api/courses/course-api/question-bank/rebuild',headers={'X-User-Id':'teacher-1'},json=body)
    assert second.status_code==202,second.text
    job=client.get(second.json()['status_url'],headers={'X-User-Id':'teacher-1'}).json()
    assert job['status']=='completed',job
    assert len(repo.load_bundle('course-api')['items'])==6
    assert sum(map(len,orchestrator.requested_practice_levels[-1].values()))==1
    current={i['revision_id']:i for i in repo.load_bundle('course-api')['items']}
    assert all(current[i['revision_id']]==i for i in partial['items'])
