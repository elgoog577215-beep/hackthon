from copy import deepcopy

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

import learning_events
from learning_records import (
    InvalidRecordTransition,
    LearningRecordRepository,
    RecordConflict,
    enrich_record_payload,
    project_record,
)
from routers import learning_records as records_router


class MemoryStorage:
    def __init__(self):
        self.data = {}
        self.annotations = []

    def load_data(self, filename):
        return deepcopy(self.data.get(filename, []))

    def save_data(self, filename, value):
        self.data[filename] = deepcopy(value)

    def load_annotations(self):
        return deepcopy(self.annotations)


def _course(content="向量具有大小与方向。"):
    return {
        "course_id": "c1",
        "course_name": "线性代数",
        "current_course_version_id": "cv1",
        "nodes": [{
            "node_id": "n1",
            "node_level": 2,
            "node_name": "向量",
            "learning_objective": "能够解释向量",
            "node_content": f"## 定义\n\n{content}",
        }],
    }


def _payload(record_type="note"):
    return {
        "record_type": record_type,
        "node_id": "n1",
        "node_name": "向量",
        "quote": "向量具有大小与方向。",
        "title": "向量定义",
        "content": "大小和方向缺一不可。",
        "origin": "user",
        "priority": "medium",
        "tags": ["定义"],
    }


def test_repository_isolates_users_and_enforces_revision_conflicts(tmp_path):
    repository = LearningRecordRepository(tmp_path)
    first = repository.create("u1", "c1", _payload())
    repository.create("u2", "c1", _payload())

    assert len(repository.list("u1", "c1")) == 1
    assert len(repository.list("u2", "c1")) == 1

    updated, kind = repository.update(
        "u1",
        "c1",
        first["record_id"],
        expected_revision=1,
        changes={"content": "新的理解"},
    )
    assert kind == "updated"
    assert updated["revision"] == 2
    with pytest.raises(RecordConflict):
        repository.update(
            "u1",
            "c1",
            first["record_id"],
            expected_revision=1,
            changes={"content": "冲突覆盖"},
        )


def test_record_lifecycle_rejects_invalid_transitions(tmp_path):
    repository = LearningRecordRepository(tmp_path)
    issue = repository.create("u1", "c1", _payload("issue"))
    resolved, kind = repository.update(
        "u1", "c1", issue["record_id"], expected_revision=1, changes={"status": "resolved"}
    )
    assert kind == "status_changed"
    assert resolved["resolved_at"]

    with pytest.raises(InvalidRecordTransition):
        repository.update(
            "u1", "c1", issue["record_id"], expected_revision=2, changes={"status": "explaining"}
        )


def test_record_anchor_projects_content_updates_without_losing_history(tmp_path):
    repository = LearningRecordRepository(tmp_path)
    enriched = enrich_record_payload(_course(), _payload())
    record = repository.create("u1", "c1", enriched)
    current = project_record(record, _course())
    changed = project_record(record, _course("向量由大小和方向共同定义。"))

    assert current["migration_status"] == "current"
    assert changed["migration_status"] in {"content_updated", "needs_confirmation"}
    assert changed["record_id"] == record["record_id"]


def test_text_anchor_uses_context_to_resolve_repeated_quotes(tmp_path):
    content = "第一处向量用于定义。第二处向量用于例题。"
    course = _course(content)
    second_start = content.rfind("向量")
    payload = {
        **_payload(),
        "quote": "向量",
        "anchor": {
            "text_quote": "向量",
            "text_position": {
                "start": second_start,
                "end": second_start + 2,
                "prefix": content[max(0, second_start - 80):second_start],
                "suffix": content[second_start + 2:second_start + 82],
                "occurrence": 1,
            },
        },
    }
    repository = LearningRecordRepository(tmp_path)
    record = repository.create("u1", "c1", enrich_record_payload(course, payload))

    projected = project_record(record, course)

    assert projected["anchor_resolution"]["text"]["status"] == "exact"
    assert projected["anchor_resolution"]["text"]["resolved_position"]["occurrence"] == 1
    assert projected["migration_status"] == "current"


def test_text_anchor_remaps_after_content_is_inserted_before_quote(tmp_path):
    original = "向量具有大小与方向。"
    changed = "先说明背景。向量具有大小与方向。"
    repository = LearningRecordRepository(tmp_path)
    record = repository.create("u1", "c1", enrich_record_payload(_course(original), _payload()))

    projected = project_record(record, _course(changed))

    assert projected["anchor_resolution"]["text"]["status"] == "quote_remap"
    assert projected["anchor_resolution"]["text"]["resolved_position"]["start"] > 0
    assert projected["migration_status"] == "content_updated"


def test_learning_record_api_and_events(monkeypatch, tmp_path):
    repository = LearningRecordRepository(tmp_path)
    storage = MemoryStorage()
    monkeypatch.setattr(records_router, "learning_record_repository", repository)
    monkeypatch.setattr(learning_events, "storage", storage)

    async def fake_course(_course_id):
        return _course()

    monkeypatch.setattr(records_router, "get_course_or_404", fake_course)
    app = FastAPI()
    app.include_router(records_router.router, prefix="/api")
    client = TestClient(app, headers={"X-User-Id": "u1"})

    created = client.post("/api/courses/c1/learning-records", json=_payload("issue"))
    assert created.status_code == 200
    record = created.json()
    assert record["objective_revision_id"]
    assert record["anchor"]["block_revision_id"]

    updated = client.patch(
        f"/api/courses/c1/learning-records/{record['record_id']}",
        json={"expected_revision": 1, "status": "resolved"},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "resolved"

    conflict = client.patch(
        f"/api/courses/c1/learning-records/{record['record_id']}",
        json={"expected_revision": 1, "content": "旧版本覆盖"},
    )
    assert conflict.status_code == 409

    events = learning_events.load_learning_events(course_id="c1")
    assert [item["event_type"] for item in events] == [
        "learning_record_created",
        "learning_record_status_changed",
    ]
    assert events[0]["record_id"] == record["record_id"]
    assert events[0]["record_type"] == "issue"


def test_duplicate_record_id_is_idempotent_for_object_and_event(monkeypatch, tmp_path):
    repository = LearningRecordRepository(tmp_path)
    storage = MemoryStorage()
    monkeypatch.setattr(records_router, "learning_record_repository", repository)
    monkeypatch.setattr(learning_events, "storage", storage)

    async def fake_course(_course_id):
        return _course()

    monkeypatch.setattr(records_router, "get_course_or_404", fake_course)
    app = FastAPI()
    app.include_router(records_router.router, prefix="/api")
    client = TestClient(app, headers={"X-User-Id": "u1"})
    payload = {**_payload("note"), "record_id": "stable-client-id"}

    first = client.post("/api/courses/c1/learning-records", json=payload)
    second = client.post("/api/courses/c1/learning-records", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert len(repository.list("u1", "c1")) == 1
    assert len(learning_events.load_learning_events(course_id="c1")) == 1


def test_legacy_annotation_migration_is_idempotent_and_degrades_wrong_items(monkeypatch, tmp_path):
    repository = LearningRecordRepository(tmp_path)
    storage = MemoryStorage()
    storage.annotations = [
        {
            "anno_id": "a-note",
            "course_id": "c1",
            "node_id": "n1",
            "user_id": "u1",
            "answer": "我的理解",
            "anno_summary": "向量笔记",
            "source_type": "user",
        },
        {
            "anno_id": "a-wrong",
            "course_id": "c1",
            "node_id": "n1",
            "user_id": "u1",
            "question": "旧错题",
            "answer": "旧解析",
            "source_type": "wrong",
        },
        {
            "anno_id": "a-format",
            "course_id": "c1",
            "node_id": "n1",
            "user_id": "u1",
            "source_type": "format",
        },
    ]
    monkeypatch.setattr(records_router, "learning_record_repository", repository)
    monkeypatch.setattr(records_router, "storage", storage)
    monkeypatch.setattr(learning_events, "storage", storage)

    async def fake_course(_course_id):
        return _course()

    monkeypatch.setattr(records_router, "get_course_or_404", fake_course)
    app = FastAPI()
    app.include_router(records_router.router, prefix="/api")
    client = TestClient(app, headers={"X-User-Id": "u1"})

    first = client.post("/api/courses/c1/learning-records/migrate-legacy-annotations")
    second = client.post("/api/courses/c1/learning-records/migrate-legacy-annotations")
    assert first.json()["created"] == 2
    assert second.json()["created"] == 0
    by_origin = {item["origin"]: item for item in first.json()["records"]}
    assert by_origin["legacy_annotation"]["record_type"] == "note"
    assert by_origin["legacy_wrong_annotation"]["record_type"] == "review_task"
    assert by_origin["legacy_wrong_annotation"]["status"] == "pending"


def test_legacy_annotation_migration_never_leaks_unowned_or_other_user_records(
    monkeypatch,
    tmp_path,
):
    repository = LearningRecordRepository(tmp_path)
    storage = MemoryStorage()
    storage.annotations = [
        {
            "anno_id": "owned-by-u1",
            "course_id": "c1",
            "node_id": "n1",
            "user_id": "u1",
            "answer": "u1 的历史笔记",
            "source_type": "user",
        },
        {
            "anno_id": "unowned",
            "course_id": "c1",
            "node_id": "n1",
            "answer": "旧单机版本未记录归属",
            "source_type": "user",
        },
    ]
    monkeypatch.setattr(records_router, "learning_record_repository", repository)
    monkeypatch.setattr(records_router, "storage", storage)
    monkeypatch.setattr(learning_events, "storage", storage)

    async def fake_course(_course_id):
        return _course()

    monkeypatch.setattr(records_router, "get_course_or_404", fake_course)
    app = FastAPI()
    app.include_router(records_router.router, prefix="/api")

    u2 = TestClient(app, headers={"X-User-Id": "u2"})
    automatic = u2.post(
        "/api/courses/c1/learning-records/migrate-legacy-annotations",
        json={"include_unowned": False},
    )
    assert automatic.json()["created"] == 0
    assert repository.list("u2", "c1") == []

    claimed = u2.post(
        "/api/courses/c1/learning-records/migrate-legacy-annotations",
        json={"include_unowned": True},
    )
    assert claimed.json()["created"] == 1
    assert repository.list("u2", "c1")[0]["metadata"]["claimed_unowned"] is True
    assert repository.list("u1", "c1") == []
