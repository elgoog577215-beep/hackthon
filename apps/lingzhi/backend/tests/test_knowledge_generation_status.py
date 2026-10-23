import asyncio
import json
from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.tests.test_knowledge_first import svc, initialize, start, tree_response
from dependencies import get_course_document_repository, get_teacher_lesson_authoring_repository
from routers.knowledge_first import router


def client_for(svc):
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_course_document_repository] = lambda: svc.repository
    app.dependency_overrides[get_teacher_lesson_authoring_repository] = lambda: svc.authoring
    return TestClient(app)


def test_light_status_omits_bodies_and_does_not_copy_or_write_authoring(svc, monkeypatch):
    initialize(svc)
    job = start(svc, "tree")
    svc.authoring.update_job("c-pilot", job["id"], status="running", phase="model_streaming",
        partial_text="PRIVATE BODY" * 100000, received_chars=1200000, last_content_at="2026-10-17T00:00:00+00:00")
    before = svc.authoring._path("c-pilot").read_bytes()
    monkeypatch.setattr(svc.authoring, "load", lambda *_: pytest.fail("status copied the full authoring document"))
    status = svc.status("c-pilot", source_mode="handouts")
    encoded = json.dumps(status, ensure_ascii=False)
    assert len(encoded.encode()) < 20000
    assert "PRIVATE BODY" not in encoded
    assert not {"tree", "history", "candidate", "candidates", "handouts", "partial_text"} & status.keys()
    assert status["active_jobs"][0]["received_chars"] == 1200000
    assert status["active_jobs"][0]["phase"] == "model_streaming"
    assert svc.authoring._path("c-pilot").read_bytes() == before


def test_result_version_ignores_stream_updates_but_tracks_completion_and_sources(svc):
    initialize(svc)
    job = start(svc, "tree")
    first = svc.status("c-pilot")
    svc.authoring.update_job("c-pilot", job["id"], status="running", partial_text="more", received_chars=4)
    assert svc.status("c-pilot")["result_version"] == first["result_version"]
    svc.authoring.update_job("c-pilot", job["id"], status="failed", phase="failed")
    second = svc.status("c-pilot")
    assert second["result_version"] != first["result_version"]
    svc.storage.update_course_data("c-pilot", lambda r: {**r, "course_document_revision": "changed"})
    assert svc.status("c-pilot")["result_version"] != second["result_version"]


def test_status_has_owner_only_visibility_and_matches_full_view_version(svc):
    initialize(svc)
    start(svc, "tree")
    client = client_for(svc)
    url = "/api/courses/c-pilot/knowledge-first"
    assert client.get(url + "/status", headers={"X-User-Id": "foreign"}).status_code == 404
    status = client.get(url + "/status", headers={"X-User-Id": "owner"})
    assert status.status_code == 200
    assert status.json()["result_version"] == client.get(url, headers={"X-User-Id": "owner"}).json()["result_version"]
    svc.storage.update_course_data("c-pilot", lambda r: {**r, "is_published": True})
    public = client.get(url + "/status", headers={"X-User-Id": "foreign"})
    assert public.status_code == 200
    assert public.json()["can_edit"] is False
    assert public.json()["jobs"] == public.json()["active_jobs"] == []


def test_event_stream_replays_completed_job_and_rejects_published_readers(svc):
    initialize(svc)
    job = start(svc, 'tree')
    svc.authoring.update_job('c-pilot', job['id'], status='failed', phase='failed')
    client = client_for(svc)
    url = '/api/courses/c-pilot/knowledge-first/events/' + job['id']
    response = client.get(url, headers={'X-User-Id': 'owner'})
    assert response.status_code == 200
    assert response.headers['content-type'].startswith('text/event-stream')
    assert 'event: snapshot' in response.text and 'event: complete' in response.text
    assert 'request_snapshot' not in response.text
    svc.storage.update_course_data('c-pilot', lambda r: {**r, 'is_published': True})
    assert client.get(url, headers={'X-User-Id': 'foreign'}).status_code == 404
    assert client.get(url + '-unknown', headers={'X-User-Id': 'owner'}).status_code == 404


def test_status_reads_course_once_for_authorization_and_projection(svc, monkeypatch):
    initialize(svc)
    reads = []
    load = svc.repository.load_raw
    def recorded_load(course_id):
        reads.append(course_id)
        return load(course_id)
    monkeypatch.setattr(svc.repository, "load_raw", recorded_load)
    result = client_for(svc).get('/api/courses/c-pilot/knowledge-first/status', headers={'X-User-Id': 'owner'})
    assert result.status_code == 200
    assert reads == ['c-pilot']


def test_status_limits_historical_jobs_to_latest_per_scope_and_keeps_blockers(svc):
    initialize(svc)
    for i in range(35):
        job = start(svc, "tree", str(i))
        svc.authoring.update_job("c-pilot", job["id"], status="failed", partial_text="secret")
    blocker = svc.authoring.create_job("c-pilot", "unknown-scope", job_type="teacher_lesson_script_generation", request_id="source")
    snapshot = svc.status("c-pilot", source_mode="handouts")
    assert len(snapshot["jobs"]) == 1
    assert snapshot["blocking_job_ids"] == [blocker["id"]]
    assert "secret" not in json.dumps(snapshot)


@pytest.mark.asyncio
async def test_streaming_progress_reports_real_characters_and_keeps_original_data(svc):
    initialize(svc)
    before = deepcopy(svc.repository.load_raw("c-pilot"))
    entered = asyncio.Event()
    release = asyncio.Event()
    async def call(*args, **kwargs):
        kwargs["on_content_delta"]("真实片段")
        entered.set()
        await release.wait()
        return json.dumps(tree_response())
    svc.provider_factory = lambda: SimpleNamespace(_call_llm=call, model_smart="test", client=None)
    job = start(svc, "tree")
    task = asyncio.create_task(svc.run("c-pilot", job["id"]))
    try:
        await entered.wait()
        await asyncio.sleep(2.1)
        status = svc.status("c-pilot")
        current = status["active_jobs"][0]
        assert current["phase"] == "model_streaming"
        assert current["received_chars"] == 4
        assert current["last_content_at"] and current["elapsed_seconds"] >= 2
    finally:
        release.set()
        await task
    assert svc.repository.load_raw("c-pilot") == before
    assert svc.status("c-pilot")["jobs"][0]["status"] == "completed"



def test_status_uses_last_committed_projection_while_checkpoint_writer_holds_course_lock(svc,monkeypatch):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    initialize(svc);job=start(svc,'tree');svc.status('c-pilot')
    entered=threading.Event();release=threading.Event();save=svc.authoring._save
    def slow_save(value):
        entered.set();assert release.wait(4);return save(value)
    monkeypatch.setattr(svc.authoring,'_save',slow_save)
    with ThreadPoolExecutor(max_workers=2) as executor:
        writer=executor.submit(svc.authoring.update_job,'c-pilot',job['id'],status='running')
        assert entered.wait(2)
        try:
            status=executor.submit(svc.status,'c-pilot').result(timeout=.3)
            assert status['jobs'][0]['status']=='pending'
        finally:release.set();writer.result(timeout=4)
    assert svc.status('c-pilot')['jobs'][0]['status']=='running'


def test_checkpoint_revisions_do_not_invalidate_whole_view_while_generation_is_active(svc):
    initialize(svc);job=start(svc,'tree')
    first=svc.status('c-pilot')['result_version']
    svc.authoring.update_job('c-pilot',job['id'],status='running',knowledge_pipeline='inventory_atomic_v1',checkpoint={'atomic_pipeline':{'revision':1}})
    assert svc.status('c-pilot')['result_version']==first
    svc.authoring.update_job('c-pilot',job['id'],checkpoint={'atomic_pipeline':{'revision':2}})
    assert svc.status('c-pilot')['result_version']==first
    svc.authoring.update_job('c-pilot',job['id'],status='failed')
    assert svc.status('c-pilot')['result_version']!=first



def test_progress_summary_omits_model_responses_and_does_not_copy_historical_pipelines():
    from knowledge_atomic import project_runs
    class NeverCopy:
        def __deepcopy__(self,memo):raise AssertionError('historical pipeline was copied')
    old={'id':'old','status':'failed','knowledge_lesson_id':'l','checkpoint':{'atomic_pipeline':{'large':NeverCopy()}}}
    current={'id':'new','status':'running','knowledge_lesson_id':'l','checkpoint':{'atomic_pipeline':{
        'generation_contract':'knowledge_registry_v5','schema_version':'inventory_atomic_v1','revision':2,
        'inventory_batches':[{'id':'inventory-1','status':'completed','request':{'raw_response':'PRIVATE'*100000}}],
        'batches':[],'truth_review':{'status':'pending','batches':[{'id':'truth-1','status':'pending'}]}}}}
    runs=project_runs({'jobs':{'old':old,'new':current}}, {})
    assert runs[0]['job_id']=='new'
    assert len(json.dumps(runs))<10000
    assert runs[0]['pipeline']['truth_review']['batches'][0]['id']=='truth-1'
