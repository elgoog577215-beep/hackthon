from copy import deepcopy
import json

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from content_blocks import normalize_blocks, project_course_content_blocks, resolve_content_anchor
from learning_snapshots import LearningSnapshotRepository, SnapshotConflict
from routers import learning_snapshots as snapshot_router


def _course() -> dict:
    return {
        "course_id": "course-1",
        "current_course_version_id": "cv2",
        "nodes": [
            {
                "node_id": "node-1",
                "node_name": "第一节",
                "node_level": 2,
                "node_content": "## 概念\n\n旧正文\n\n## 例子\n\n示例内容",
                "content_blocks": [],
            },
            {
                "node_id": "node-2",
                "node_name": "第二节",
                "node_level": 2,
                "node_content": "## 应用\n\n应用内容",
                "content_blocks": [],
            },
        ],
    }


def _request(user_id: str = "user-1") -> Request:
    return Request({
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(b"x-user-id", user_id.encode("utf-8"))],
    })


def _update(expected_revision: int = 0) -> snapshot_router.SnapshotUpdate:
    return snapshot_router.SnapshotUpdate(
        expected_revision=expected_revision,
        course_version_id="cv2",
        node_id="node-1",
        node_name="第一节",
        content_anchor={
            "block_id": "node-1-1-concept",
            "block_revision_id": "cbr_old",
            "content_fingerprint": "cbf_old",
            "block_type": "concept",
            "title": "概念",
            "progress": 0.4,
        },
        session={"session_id": "session-1", "device_id": "device-1"},
        activity_at="2026-07-11T10:00:00+00:00",
    )


def test_content_block_revision_changes_without_changing_block_id():
    old = normalize_blocks("node-1", [], "## 概念\n\n旧正文")[0]
    updated = normalize_blocks("node-1", [{**old, "content": "新正文"}], "")[0]

    assert old["block_id"] == updated["block_id"]
    assert old["block_revision_id"] != updated["block_revision_id"]
    assert old["content_fingerprint"] != updated["content_fingerprint"]


def test_old_course_projection_adds_anchor_metadata_without_mutating_source():
    course = _course()
    projected = project_course_content_blocks(course)

    assert course["nodes"][0]["content_blocks"] == []
    first = projected["nodes"][0]["content_blocks"][0]
    assert first["block_id"] == "node-1-1-concept"
    assert first["block_revision_id"].startswith("cbr_")
    assert first["content_fingerprint"].startswith("cbf_")


def test_anchor_resolution_reports_exact_and_updated_block():
    course = project_course_content_blocks(_course())
    block = course["nodes"][0]["content_blocks"][0]
    exact = resolve_content_anchor(course, node_id="node-1", anchor={**block, "progress": 0.5})
    changed = deepcopy(course)
    changed["nodes"][0]["content_blocks"][0]["content"] = "已经更新的正文"
    updated = resolve_content_anchor(changed, node_id="node-1", anchor={**block, "progress": 0.5})

    assert exact["status"] == "exact"
    assert exact["resolved_anchor"]["progress"] == 0.5
    assert updated["status"] == "updated_block"
    assert updated["content_changed"] is True
    assert updated["resolved_anchor"]["block_revision_id"] != block["block_revision_id"]


def test_anchor_resolution_uses_fingerprint_then_explicit_fallbacks():
    course = project_course_content_blocks(_course())
    block = course["nodes"][0]["content_blocks"][1]
    remapped = resolve_content_anchor(
        course,
        node_id="node-1",
        anchor={"block_id": "removed", "content_fingerprint": block["content_fingerprint"]},
    )
    node_fallback = resolve_content_anchor(course, node_id="node-2", anchor={"block_id": "missing"})
    course_fallback = resolve_content_anchor(course, node_id="deleted", anchor={"block_id": "missing"})

    assert remapped["status"] == "fingerprint_remap"
    assert remapped["resolved_anchor"]["block_id"] == block["block_id"]
    assert node_fallback["status"] == "node_fallback"
    assert node_fallback["resolved_anchor"]["node_id"] == "node-2"
    assert course_fallback["status"] == "course_fallback"
    assert course_fallback["resolved_anchor"]["node_id"] == "node-1"


def test_snapshot_repository_isolates_users_and_rejects_stale_revision(tmp_path):
    repository = LearningSnapshotRepository(tmp_path)
    first = repository.save("user-1", "course-1", expected_revision=0, payload={"node_id": "node-1"})
    other = repository.save("user-2", "course-1", expected_revision=0, payload={"node_id": "node-2"})

    assert first["revision"] == 1
    assert repository.load("user-1", "course-1")["node_id"] == "node-1"
    assert other["snapshot_id"] != first["snapshot_id"]
    with pytest.raises(SnapshotConflict) as conflict:
        repository.save("user-1", "course-1", expected_revision=0, payload={"node_id": "stale"})
    assert conflict.value.current["revision"] == 1


def test_snapshot_repository_delete_and_corrupt_file_recovery(tmp_path):
    repository = LearningSnapshotRepository(tmp_path)
    repository.save("user-1", "course-1", expected_revision=0, payload={"node_id": "node-1"})
    path = next(tmp_path.glob("*.json"))
    path.write_text("{broken", encoding="utf-8")

    assert repository.load("user-1", "course-1") is None
    assert list(tmp_path.glob("*.corrupt-*.json"))
    repository.save("user-1", "course-1", expected_revision=0, payload={"node_id": "node-2"})
    assert repository.delete("user-1", "course-1") is True
    assert repository.delete("user-1", "course-1") is False


@pytest.mark.asyncio
async def test_snapshot_api_create_load_conflict_and_delete(monkeypatch, tmp_path):
    repository = LearningSnapshotRepository(tmp_path)

    async def fake_course(_course_id):
        return _course()

    monkeypatch.setattr(snapshot_router, "learning_snapshot_repository", repository)
    monkeypatch.setattr(snapshot_router, "get_course_or_404", fake_course)

    created = await snapshot_router.put_learning_snapshot("course-1", _update(), _request())
    loaded = await snapshot_router.get_learning_snapshot("course-1", _request())

    assert created["snapshot"]["revision"] == 1
    assert loaded["snapshot"]["node_id"] == "node-1"
    assert loaded["resolution"]["status"] == "updated_block"

    with pytest.raises(HTTPException) as conflict:
        await snapshot_router.put_learning_snapshot("course-1", _update(), _request())
    assert conflict.value.status_code == 409
    assert conflict.value.detail["current_snapshot"]["revision"] == 1

    deleted = await snapshot_router.delete_learning_snapshot("course-1", _request())
    assert deleted["status"] == "deleted"


def test_repository_writes_valid_json(tmp_path):
    repository = LearningSnapshotRepository(tmp_path)
    repository.save("user", "course", expected_revision=0, payload={"node_id": "n"})
    data = json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))
    assert data["schema_version"] == 2
