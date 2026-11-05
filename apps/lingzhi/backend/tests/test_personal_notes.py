from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from types import SimpleNamespace

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
import pytest

from ai_teacher_state import AITeacherRepository
from dependencies import require_task_manager
from routers import study
from storage import Storage
from study.auth import study_identity
from study.notes import get_note, resolve_note_context, update_note
from study.repository import StudyConflict, StudyRepository


@pytest.fixture
def env(tmp_path, monkeypatch):
    import study.assistant as assistant
    import learning_events
    chats = AITeacherRepository(tmp_path / "chats")
    monkeypatch.setattr(assistant, "ai_teacher_repository", chats)
    events = []
    monkeypatch.setattr(learning_events, "record_learning_event", lambda **kw: events.append(kw))
    repo = StudyRepository(Storage(str(tmp_path / "data")))
    material = {"id": "m", "owner_id": "student", "request_key": "create-material-request", "fingerprint": "f",
                "title": "测试课程", "purpose": "systematic", "status": "completed", "task_id": "task",
                "created_at": "now", "updated_at": "now", "plans": [], "notes": {"r": {"content": "原整课笔记", "updated_at": "before"}},
                "request": {"source_sections": [], "generated_sections": [{"node_id": "s"}]},
                "revisions": [{"id": "r", "status": "completed", "sections": [
                    {"id": "s", "title": "导数", "complete": True, "content": "已保存正文", "blocks": [
                        {"block_id": "b", "title": "导数定义", "content_type": "definition", "content": "导数是变化率。", "answer_to": ""},
                        {"block_id": "other", "title": "求导方法", "content_type": "method", "content": "先检查条件。", "answer_to": ""},
                    ]}]}]}
    repo.reserve("student", material["request_key"], "f", material)
    app = FastAPI()
    app.include_router(study.router, prefix="/api")

    def identity(request: Request):
        return {"id": request.headers.get("x-test-user", "student"), "role": "student"}

    app.dependency_overrides[study_identity] = identity
    app.dependency_overrides[study.repository] = lambda: repo
    app.dependency_overrides[require_task_manager] = lambda: SimpleNamespace(tasks={})
    return TestClient(app), repo, chats, events


def payload(**extra):
    return {"request_id": "note-request-000001", "revision_id": "r", "section_id": "s", "block_id": "b",
            "quote": "导数是变化率", "anchor_prefix": "", "anchor_suffix": "。", "content": "这个极限如何理解？",
            "kind": "note", "question_state": "open", "important": False, **extra}


def seed_answer(chats, *, owner="student", material_id="m", revision="r", message_id="answer", status="complete", **context):
    def update(conversation):
        conversation["messages"].append({"message_id": message_id, "role": "assistant", "status": status,
            "content": "解释与例子", "context_ref": {"material_id": material_id, "revision_id": revision,
                "section_id": "s", "block_id": "b", "quote": "导数是变化率。", **context}})
    chats.material_conversation(owner, material_id, revision, update)


def test_note_create_is_idempotent_private_and_keeps_the_single_legacy_owner(env):
    client, repo, _, events = env
    request = payload()
    first = client.post("/api/study/materials/m/notes", json=request)
    assert first.status_code == 200, first.text
    note = first.json()
    assert note["content_type"] == "definition" and note["section_title"] == "导数"
    assert note["location_status"] == "current" and note["source_type"] == "self" and note["version"] == 1
    assert len(note["source_sha256"]) == 64
    assert client.post("/api/study/materials/m/notes", json=request).json() == note
    assert client.post("/api/study/materials/m/notes", json={**request, "content": "不一样"}).status_code == 409
    assert len(events) == 1 and events[0]["result"] == {"saved": True}
    assert "concept_ids" not in events[0]
    saved = repo.get("student", "m")
    assert saved["notes"]["r"]["content"] == "原整课笔记"
    assert len(saved["notes"]["r"]["entries"]) == 1
    public = client.get("/api/study/materials/m").json()["notes"]["r"]
    assert public["entries"] == [note] and "request_id" not in public["entries"][0]
    for method, path, body in [("get", "/notes", None), ("post", "/notes", request),
                               ("patch", "/notes/" + note["id"], {"expected_version": 1, "content": "steal"})]:
        options = {"headers": {"x-test-user": "other-student"}}
        if body is not None:
            options["json"] = body
        assert getattr(client, method)("/api/study/materials/m" + path, **options).status_code == 404


def test_section_and_course_notes_work_but_marks_require_a_real_block(env):
    client, *_ = env
    course = client.post("/api/study/materials/m/notes", json=payload(section_id="", block_id="", quote="", anchor_suffix=""))
    assert course.status_code == 200 and course.json()["section_id"] == ""
    section = client.post("/api/study/materials/m/notes", json=payload(request_id="note-request-000002", block_id="", quote="", anchor_suffix=""))
    assert section.status_code == 200 and section.json()["section_title"] == "导数"
    mark = client.post("/api/study/materials/m/notes", json=payload(request_id="note-request-000003", content="", kind="mark", important=True))
    assert mark.status_code == 200 and mark.json()["important"]
    for invalid in [dict(block_id="foreign"), dict(section_id="foreign"), dict(revision_id="old"),
                    dict(kind="mark", block_id="", quote="", anchor_suffix=""), dict(block_id="", quote="无原文")]:
        response = client.post("/api/study/materials/m/notes", json=payload(request_id="note-request-invalid", **invalid))
        assert response.status_code == 409


def test_atomic_note_updates_reject_lost_edits_and_legacy_save_preserves_entries(env, monkeypatch):
    client, repo, *_ = env
    before = repo.get("student", "m")
    note = client.post("/api/study/materials/m/notes", json=payload()).json()

    def edit(content):
        try:
            return update_note(repo, "student", "m", note["id"], {"expected_version": 1, "content": content})
        except StudyConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(edit, ["我的理解甲", "我的理解乙"]))
    assert sum(value == "conflict" for value in results) == 1
    saved = next(value for value in results if isinstance(value, dict))
    assert saved["version"] == 2
    assert client.patch("/api/study/materials/m/notes/" + note["id"], json={"expected_version": 1, "question_state": "answered"}).status_code == 409
    updated = client.patch("/api/study/materials/m/notes/" + note["id"], json={"expected_version": 2, "question_state": "answered"}).json()
    assert updated["question_state"] == "answered"
    assert updated["quote"] == note["quote"] and updated["source_sha256"] == note["source_sha256"]
    # Model a legacy tab that read the material before any structured entry was
    # created. Its whole-course save must not replace today's entries.
    monkeypatch.setattr(repo, "get", lambda *_: deepcopy(before))
    repo.save_note("student", "m", "r", "更新整课笔记")
    actual = repo.ledger()["m"]["notes"]["r"]
    assert actual["content"] == "更新整课笔记" and actual["entries"][0]["version"] == 3


def test_read_projection_keeps_original_quotes_and_reports_source_changes_without_writes(env):
    client, repo, _, events = env
    note = client.post("/api/study/materials/m/notes", json=payload()).json()
    original = repo.get("student", "m")
    revisions = deepcopy(original["revisions"])
    revisions[0]["sections"][0]["blocks"][0]["content"] = "补充条件后的定义。"
    repo.update("student", "m", {"revisions": revisions})
    snapshot = repo.get("student", "m")
    projected = client.get("/api/study/materials/m/notes").json()["entries"][0]
    assert projected["location_status"] == "changed" and projected["quote"] == note["quote"]
    assert repo.get("student", "m") == snapshot and len(events) == 1
    with pytest.raises(StudyConflict, match="原文"):
        resolve_note_context(snapshot, note["id"], 1)
    revisions[0]["sections"][0]["blocks"] = []
    repo.update("student", "m", {"revisions": revisions})
    assert client.get("/api/study/materials/m/notes").json()["entries"][0]["location_status"] == "missing"
    revisions.append({**deepcopy(original["revisions"][0]), "id": "r2"})
    repo.update("student", "m", {"revisions": revisions})
    assert client.get("/api/study/materials/m/notes").json()["entries"] == []
    old = client.get("/api/study/materials/m/notes?revision_id=r").json()["entries"][0]
    assert old["location_status"] == "historical" and old["content"] == note["content"]
    assert get_note(repo.get("student", "m"), note["id"])["location_status"] == "historical"


def test_soft_delete_checks_version_hides_record_and_does_not_resurrect_a_retried_create(env):
    client, repo, *_ = env
    note = client.post("/api/study/materials/m/notes", json=payload()).json()
    path = "/api/study/materials/m/notes/" + note["id"]
    assert client.delete(path + "?expected_version=2").status_code == 409
    assert client.delete(path + "?expected_version=1").json() == {"deleted": True, "id": note["id"], "version": 2}
    assert client.delete(path + "?expected_version=1").status_code == 200
    assert client.get("/api/study/materials/m/notes").json()["entries"] == []
    assert client.get("/api/study/materials/m").json()["notes"]["r"]["entries"] == []
    assert client.post("/api/study/materials/m/notes", json=payload()).status_code == 409
    assert repo.get("student", "m")["notes"]["r"]["entries"][0]["deleted_at"]


def test_ai_answer_capture_uses_its_own_exact_scope_and_rejects_foreign_pending_or_spoofed_refs(env):
    client, _, chats, _ = env
    seed_answer(chats)
    note = client.post("/api/study/materials/m/notes", json=payload(source_message_id="answer", quote="伪造摘录")).json()
    assert note["source_type"] == "ai" and note["quote"] == "导数是变化率。" and note["anchor_suffix"] == ""
    assert client.post("/api/study/materials/m/notes", json=payload(request_id="different-request-1", source_message_id="answer", block_id="other")).status_code == 409
    seed_answer(chats, message_id="unfinished", status="running")
    seed_answer(chats, owner="other-student", message_id="private")
    seed_answer(chats, material_id="other-material", message_id="foreign-material")
    seed_answer(chats, revision="old", message_id="old-revision")
    for message_id in ["unfinished", "private", "foreign-material", "old-revision", "unknown"]:
        assert client.post("/api/study/materials/m/notes", json=payload(request_id="capture-invalid-001", source_message_id=message_id)).status_code == 409


def test_confirmed_ai_draft_keeps_participation_and_cannot_overwrite_a_newer_note(env):
    client, repo, chats, _ = env
    note = client.post("/api/study/materials/m/notes", json=payload()).json()
    seed_answer(chats, note_id=note["id"], note_version=1)
    path = "/api/study/materials/m/notes/" + note["id"]
    saved = client.patch(path, json={"expected_version": 1, "content": "我修改了 AI 建议后保存", "source_message_id": "answer"})
    assert saved.status_code == 200, saved.text
    assert saved.json()["source_type"] == "ai" and saved.json()["version"] == 2
    assert client.patch(path, json={"expected_version": 2, "content": "旧AI覆盖", "source_message_id": "answer"}).status_code == 409
    manual = client.patch(path, json={"expected_version": 2, "content": "自己的补充"}).json()
    assert manual["source_type"] == "ai" and manual["source_message_id"] == "answer"
    with pytest.raises(StudyConflict, match="修改"):
        resolve_note_context(repo.get("student", "m"), note["id"], 1)
    assert resolve_note_context(repo.get("student", "m"), note["id"], 3)["content"] == "自己的补充"
    seed_answer(chats, message_id="unrelated", note_id="another-note", note_version=3)
    assert client.patch(path, json={"expected_version": 3, "content": "错误关联", "source_message_id": "unrelated"}).status_code == 409
