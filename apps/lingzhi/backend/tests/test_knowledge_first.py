import asyncio
import json
from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from course_document import CourseDocument, refresh_document_revision
from course_repository import CourseDocumentConflict, CourseDocumentRepository
from knowledge_first import KnowledgeFirstService, material, compile_tree, compile_handout
from knowledge_first import parse_response
from storage import Storage
from teacher_lesson_authoring import TeacherLessonAuthoringRepository


def tree_response():
    package = material()
    return {"groups": [{"topic": t, "name": section["title"], "knowledge_ids": [p["knowledge_id"] for p in b["points"] if p["key"] in section["required_knowledge_keys"]]}
                       for t, b in package["bundles"].items() for section in b["sections"]]}


def handout_response(topic):
    return {"introduction": "下面从表达式类型与控制流开始学习本讲的规则及适用条件。",
            "explanations": [{"knowledge_id": p["knowledge_id"], "text": p["statement"] + " 适用条件：" + "；".join(p["conditions"])} for p in material()["bundles"][topic]["points"]],
            "summary": "解题时先检查适用条件，再逐步应用对应规则，并核对表达式类型和语句范围。"}


@pytest.fixture
def svc(tmp_path):
    storage = Storage(str(tmp_path / "data"))
    doc = refresh_document_revision(CourseDocument(course_id="c-pilot", title="C17"))
    storage.update_course_data("c-pilot", lambda _: {"course_id": "c-pilot", "course_name": "C17", "owner_id": "owner", "authoring_surface": "teacher",
        "course_schema_version": "course_document_v1", "course_document": doc.model_dump(mode="json"), "course_document_revision": doc.document_revision})
    repository = CourseDocumentRepository(storage)
    authoring = TeacherLessonAuthoringRepository(tmp_path / "authoring", canonical_storage=storage)
    return KnowledgeFirstService(repository, authoring)


def initialize(svc):
    svc.initialize("c-pilot", svc.repository.load_raw("c-pilot")["course_document_revision"], workflow="knowledge_first_c17_v1")


def start(svc, topic, request_id="test"):
    v = svc.view("c-pilot")
    return svc.start("c-pilot", topic, request_id, v["knowledge_revision"], v["document_revision"])[0]


async def generate(svc, topic, request_id="test"):
    response = tree_response() if topic == "tree" else handout_response(topic)
    async def call(*args, **kwargs):
        assert kwargs["max_attempts"] == 1
        return json.dumps(response, ensure_ascii=False)
    svc.provider_factory = lambda: SimpleNamespace(_call_llm=call, model_smart="test-qwen", client=None)
    job = start(svc, topic, request_id)
    await svc.run("c-pilot", job["id"])
    assert svc.authoring.load("c-pilot")["jobs"][job["id"]]["status"] == "completed"
    assert svc.authoring.load("c-pilot")["jobs"][job["id"]]["model"] == "test-qwen"
    return job


async def adopted(svc):
    initialize(svc)
    job = await generate(svc, "tree")
    v = svc.view("c-pilot")
    svc.adopt("c-pilot", job["id"], "", v["document_revision"])
    return job


def test_tree_preserves_49_atoms_and_rejects_duplicate_foreign_missing():
    response = tree_response()
    tree = compile_tree(material(), response)
    assert len(tree["knowledge_points"]) == 49
    for mutation in (lambda r: r["groups"].pop(), lambda r: r["groups"][0]["knowledge_ids"].append("unknown"),
                     lambda r: r["groups"][0]["knowledge_ids"].append(r["groups"][0]["knowledge_ids"][0])):
        bad = deepcopy(response); mutation(bad)
        with pytest.raises(CourseDocumentConflict): compile_tree(material(), bad)


def test_json_fence_is_only_format_normalization():
    assert parse_response('```json\n{"groups": []}\n```') == {"groups": []}
    for text in ('explanation {"groups": []}', '```json\n{"groups": [', '{"groups": []} trailing'):
        with pytest.raises(json.JSONDecodeError): parse_response(text)
    with pytest.raises(CourseDocumentConflict): parse_response('{"a":1,"a":2}')


def test_short_keys_resolve_to_fixed_ids():
    package = material()
    assignments = {key: s["title"] for b in package["bundles"].values() for s in b["sections"] for key in s["required_knowledge_keys"]}
    tree = compile_tree(package, {"assignments": assignments})
    assert {p["knowledge_id"] for p in tree["knowledge_points"]} == {p["knowledge_id"] for b in package["bundles"].values() for p in b["points"]}
    response = handout_response("if")
    keys = {p["knowledge_id"]: p["key"] for p in package["bundles"]["if"]["points"]}
    for item in response["explanations"]: item["key"] = keys[item.pop("knowledge_id")]
    assert compile_handout(tree, package["bundles"]["if"], response)["blocks"]


@pytest.mark.parametrize("topic", ["types", "if", "for"])
def test_handout_source_guards_and_frozen_answers(topic):
    tree = compile_tree(material(), tree_response())
    bundle = material()["bundles"][topic]
    response = handout_response(topic)
    result = compile_handout(tree, bundle, response)
    assert {r["knowledge_id"] for b in result["blocks"] for r in b["knowledge_refs"]} == {p["knowledge_id"] for p in bundle["points"]}
    for e in bundle["example_bank"]:
        block = next(b for b in result["blocks"] if b["block_id"].endswith(e["key"]))
        assert e["code"] in block["content"] and e["answer_stdout"] in block["content"]
        assert block["answer_refs"] == [e["answer_ref"]]
    assert any(b["role"] == "misconception" for b in result["blocks"])
    response["explanations"].pop()
    with pytest.raises(CourseDocumentConflict): compile_handout(tree, bundle, response)


@pytest.mark.asyncio
async def test_flow_projection_reload_history_and_staleness(svc):
    await adopted(svc)
    for topic in ("types", "if", "for"): await generate(svc, topic, topic)
    view = svc.view("c-pilot")
    assert len(view["history"]) == 1
    assert [len(h["revisions"]) for h in view["handouts"]] == [1, 1, 1]
    # Reopen durable files, not in-memory objects.
    svc.authoring = TeacherLessonAuthoringRepository(svc.authoring.root, canonical_storage=svc.storage)
    from teacher_content_projection import project_teacher_content
    projected = project_teacher_content(svc.repository.load_raw("c-pilot"), authoring=svc.authoring.load("c-pilot"))
    assert len(projected["nodes"]) == 3
    assert any(b["concept_refs"] for b in projected["course_document"]["blocks"])
    assert all(b["payload"].get("source_knowledge_revision") == view["knowledge_revision"] for b in projected["course_document"]["blocks"])
    assert all(h["source_knowledge_revision"] == view["knowledge_revision"] for h in projected["teacher_handouts"].values())
    assert all(h['source_context_revision'] and h['source_evidence_package_revision'] for h in projected['teacher_handouts'].values())
    assert all(b['payload']['source_context_revision'] for b in projected['course_document']['blocks'])
    old = deepcopy(view["handouts"])
    def move(raw):
        raw["course_knowledge_base"]["revision_id"] = "new"
        return raw
    svc.storage.update_course_data("c-pilot", move)
    assert all(h["revisions"][0]["stale"] for h in svc.view("c-pilot")["handouts"])
    assert svc.view("c-pilot")["handouts"][0]["revisions"][0]["sections"] == old[0]["revisions"][0]["sections"]


@pytest.mark.asyncio
async def test_generation_requires_adoption_and_deduplicates(svc):
    initialize(svc)
    with pytest.raises(CourseDocumentConflict): start(svc, "types")
    first = start(svc, "tree")
    assert start(svc, "tree")["id"] == first["id"]
    with pytest.raises(CourseDocumentConflict): start(svc, "tree", "another")
    svc.authoring.cancel_job("c-pilot", first["id"])
    with pytest.raises(CourseDocumentConflict): svc.initialize("c-pilot", svc.view("c-pilot")["document_revision"])


@pytest.mark.asyncio
@pytest.mark.parametrize("stop", ["cancel", "source"])
async def test_late_result_cannot_overwrite(svc, stop):
    await adopted(svc)
    job = start(svc, "types", "late")
    async def call(*args, **kwargs):
        if stop == "cancel": svc.authoring.cancel_job("c-pilot", job["id"])
        else:
            def update(raw):
                raw["course_knowledge_base"]["revision_id"] = "changed"
                return raw
            svc.storage.update_course_data("c-pilot", update)
        return json.dumps(handout_response("types"))
    svc.provider_factory = lambda: SimpleNamespace(_call_llm=call, model_smart="test", client=None)
    await svc.run("c-pilot", job["id"])
    assert not svc.view("c-pilot")["handouts"][0]["revisions"]
    assert svc.authoring.load("c-pilot")["jobs"][job["id"]]["status"] == ("cancelled" if stop == "cancel" else "failed")


@pytest.mark.asyncio
async def test_single_failed_model_call_preserves_current_handout(svc):
    await adopted(svc)
    await generate(svc, "types", "good")
    before = svc.view("c-pilot")["handouts"][0]
    calls = []
    async def call(*args, **kwargs):
        calls.append(1); kwargs["on_content_delta"]("partial")
        raise TimeoutError()
    svc.provider_factory = lambda: SimpleNamespace(_call_llm=call, model_smart="test", client=None)
    job = start(svc, "types", "fail")
    await svc.run("c-pilot", job["id"])
    assert calls == [1]
    assert svc.view("c-pilot")["handouts"][0] == before
    assert svc.authoring.load("c-pilot")["jobs"][job["id"]]["partial_text"] == "partial"


def test_endpoint_owner_private_and_shared_read(svc):
    from routers.knowledge_first import router
    from dependencies import get_course_document_repository, get_teacher_lesson_authoring_repository
    app = FastAPI(); app.include_router(router, prefix="/api")
    app.dependency_overrides[get_course_document_repository] = lambda: svc.repository
    app.dependency_overrides[get_teacher_lesson_authoring_repository] = lambda: svc.authoring
    client = TestClient(app); url = "/api/courses/c-pilot/knowledge-first"
    assert client.get(url, headers={"X-User-Id": "foreign"}).status_code == 404
    assert client.get(url, headers={"X-User-Id": "owner"}).status_code == 200
    svc.storage.update_course_data("c-pilot", lambda r: {**r, "is_published": True, "authoring_surface": "learner"})
    shared = client.get(url, headers={"X-User-Id": "foreign"})
    assert shared.status_code == 200 and not shared.json()["can_edit"] and not shared.json()["jobs"]
    assert client.post(url + "/initialize", headers={"X-User-Id": "foreign"}, json={"document_revision": svc.view("c-pilot")["document_revision"]}).status_code == 404
    # Student owner has the same write boundary.
    assert client.post(url + "/initialize", headers={"X-User-Id": "owner"}, json={"document_revision": svc.view("c-pilot")["document_revision"]}).status_code == 200


@pytest.mark.asyncio
async def test_adoption_keeps_real_history_and_point_identities(svc, monkeypatch):
    await adopted(svc)
    await generate(svc, "types", "first-handout")
    old = svc.view("c-pilot")
    response = tree_response()
    response["groups"][0]["name"] = "字面量类型"
    monkeypatch.setitem(globals(), "tree_response", lambda: response)
    job = await generate(svc, "tree", "second-tree")
    svc.adopt("c-pilot", job["id"], old["knowledge_revision"], old["document_revision"])
    new = svc.view("c-pilot")
    assert len(new["history"]) == 2
    assert new["knowledge_revision"] != old["knowledge_revision"]
    assert [(p["knowledge_id"], p["revision_id"]) for p in new["tree"]["knowledge_points"]] == [(p["knowledge_id"], p["revision_id"]) for p in old["tree"]["knowledge_points"]]
    handout = new["handouts"][0]["revisions"][0]
    assert handout["stale"] and handout["source_knowledge_revision"] == old["knowledge_revision"]


@pytest.mark.asyncio
async def test_restart_freezes_job_without_model_call(svc):
    from routers.teacher_lesson_authoring import recover_teacher_generation_jobs
    initialize(svc)
    job = start(svc, "tree")
    svc.authoring.update_job("c-pilot", job["id"], status="running", partial_text="saved fragment")
    await recover_teacher_generation_jobs(SimpleNamespace(), svc.authoring)
    restored = svc.authoring.load("c-pilot")["jobs"][job["id"]]
    assert restored["status"] == "failed" and restored["partial_text"] == "saved fragment"


def test_existing_knowledge_consumers_preserve_tree_identity():
    from course_knowledge_base import compile_course_knowledge_base, validate_course_knowledge_base
    from course_knowledge_revisions import knowledge_revision_vector
    tree = compile_tree(material(), tree_response())
    tree["status"] = "accepted"
    before = deepcopy(tree)
    view = compile_course_knowledge_base({"course_id": "c-pilot", "nodes": [], "course_knowledge_base": tree})
    assert tree == before
    assert view["revision_id"] == tree["revision_id"] and len(view["knowledge_points"]) == 49
    assert len([key for key in knowledge_revision_vector(tree).revisions if key.startswith('relation:')]) == 3
    report = validate_course_knowledge_base(tree)
    assert not [issue for issue in report["issues"] if issue["severity"] == "critical"]


@pytest.mark.asyncio
async def test_unverified_teaching_candidate_cannot_be_adopted(svc):
    initialize(svc)
    job = start(svc, "tree", "teaching-candidate")
    candidate = compile_tree(material(), tree_response())
    candidate["teaching_assessment"] = {"ready_for_adoption": False}
    svc.authoring.update_job("c-pilot", job["id"], status="completed", checkpoint={"candidate": candidate})
    with pytest.raises(CourseDocumentConflict, match="教学补全候选"):
        svc.adopt("c-pilot", job["id"], "", svc.view("c-pilot")["document_revision"])
    assert not svc.view("c-pilot")["knowledge_revision"]


@pytest.mark.asyncio
async def test_shared_context_is_sent_and_source_change_blocks_late_tree(svc):
    initialize(svc)
    job=start(svc,'tree','context-test')
    recorded=svc.authoring.load('c-pilot')['jobs'][job['id']]
    context=recorded['request_snapshot']['knowledge_generation_context']
    assert len(context['evidence_package']['units'])==49
    assert recorded['source_context_revision']==context['revision_id']
    async def call(prompt, **kwargs):
        assert context['revision_id'] in prompt
        assert context['evidence_package']['package_revision_id'] in prompt
        svc.storage.update_course_data('c-pilot',lambda raw:{**raw,'generation_request':{'requirements':'changed goal'}})
        return json.dumps(tree_response())
    svc.provider_factory=lambda:SimpleNamespace(_call_llm=call,model_smart='test',client=None)
    await svc.run('c-pilot',job['id'])
    assert svc.authoring.load('c-pilot')['jobs'][job['id']]['status']=='failed'
    assert svc.view('c-pilot')['candidate'] is None


@pytest.mark.asyncio
async def test_context_change_after_candidate_blocks_adoption(svc):
    initialize(svc);job=await generate(svc,'tree','context-adoption')
    view=svc.view('c-pilot')
    svc.storage.update_course_data('c-pilot',lambda raw:{**raw,'course_profile':{'course_goal':'new'}})
    with pytest.raises(CourseDocumentConflict,match='上下文'):
        svc.adopt('c-pilot',job['id'],'',view['document_revision'])
