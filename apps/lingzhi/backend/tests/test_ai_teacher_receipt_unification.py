"""Every AI-teacher confirm/undo outcome must end in one persisted receipt shape.

The action protocol already returned a persisted `ActionReceipt` when the
learning runtime moved under a proposal, but the neighbouring terminal outcomes
(expired proposal, rejected proposal, undo against a changed or missing record,
undo of a non-reversible receipt) raised bare HTTP errors instead. Those paths
left no audit row, no idempotent replay and no machine-readable reason, so the
client could not tell "nothing happened" apart from "something half happened".
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

import ai_teacher_actions
from ai_teacher_actions import (
    RECEIPT_SCHEMA_VERSION,
    execute_proposal,
    propose_action,
    reject_proposal,
    undo_receipt,
)
from ai_teacher_state import AITeacherRepository
from learning_records import LearningRecordRepository
from routers import ai_teacher as ai_teacher_router


def _course() -> dict:
    return {
        "course_id": "course-ai",
        "current_course_version_id": "cv-1",
        "course_name": "AI receipts",
        "nodes": [{
            "node_id": "node-1",
            "node_name": "变量",
            "node_level": 2,
            "node_content": "## 变量绑定\n变量名通过绑定指向当前值。",
            "learning_objective": "能够解释变量绑定",
        }],
    }


def _runtime() -> dict:
    return {
        "runtime_revision_id": "runtime-1",
        "revision_vector": {"course_version_id": "cv-1", "events": "e1"},
        "context": {
            "course_id": "course-ai",
            "course_version_id": "cv-1",
            "node_id": "node-1",
            "objective_id": "obj-1",
            "objective_revision_id": "objr-1",
        },
        "active_task": {},
        "progress": {"nodes": []},
        "records": {},
        "practice": {},
        "diagnostic": {},
        "learner_model": {"model_revision_id": "model-1"},
        "continuation": {"primary_action": {"action_id": "a-1", "action_type": "complete_reading"}},
    }


def _repositories(monkeypatch, tmp_path: Path):
    interactions = AITeacherRepository(tmp_path / "interactions")
    records = LearningRecordRepository(tmp_path / "records")
    monkeypatch.setattr(ai_teacher_actions, "build_learning_runtime", lambda *a, **k: _runtime())
    monkeypatch.setattr(ai_teacher_actions, "learning_record_repository", records)
    monkeypatch.setattr(ai_teacher_actions, "record_learning_event", lambda **kwargs: None)
    return interactions, records


def _note_proposal(interactions: AITeacherRepository) -> dict:
    return propose_action(
        _course(),
        user_id="u1",
        action_type="create_note",
        target_ref={"node_id": "node-1"},
        payload={"node_id": "node-1", "title": "变量", "content": "变量保存可变化的值"},
        confirmation_mode="user_command",
        origin="user_command",
        repository=interactions,
    )


def _assert_receipt_shape(receipt: dict) -> None:
    """Every receipt, success or failure, exposes the same audit surface."""
    assert receipt["schema_version"] == RECEIPT_SCHEMA_VERSION
    for key in (
        "receipt_id",
        "proposal_id",
        "command_id",
        "idempotency_key",
        "status",
        "action_type",
        "result_code",
        "affected_refs",
        "summary",
        "undo_capability",
    ):
        assert key in receipt, f"receipt is missing {key}"
    assert receipt["status"] in {"succeeded", "failed", "stale"}
    assert isinstance(receipt["affected_refs"], list)
    if receipt["status"] != "succeeded":
        assert receipt["affected_refs"] == []
        assert receipt["failure_reason"]


def test_successful_action_receipt_carries_the_unified_shape(monkeypatch, tmp_path: Path):
    interactions, records = _repositories(monkeypatch, tmp_path)
    proposal = _note_proposal(interactions)

    receipt = execute_proposal(
        _course(),
        user_id="u1",
        proposal_id=proposal["proposal_id"],
        idempotency_key="confirm-ok-1",
        repository=interactions,
    )

    _assert_receipt_shape(receipt)
    assert receipt["status"] == "succeeded"
    assert receipt["result_code"] == "note_created"
    assert len(records.list("u1", "course-ai")) == 1


def test_expired_proposal_confirm_returns_a_persisted_stale_receipt(monkeypatch, tmp_path: Path):
    interactions, records = _repositories(monkeypatch, tmp_path)
    proposal = _note_proposal(interactions)
    stored = interactions.get_proposal("u1", "course-ai", proposal["proposal_id"])
    stored["expires_at"] = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    monkeypatch.setattr(
        interactions,
        "get_proposal",
        lambda *_args, **_kwargs: dict(stored),
    )

    receipt = execute_proposal(
        _course(),
        user_id="u1",
        proposal_id=proposal["proposal_id"],
        idempotency_key="confirm-expired-1",
        repository=interactions,
    )

    _assert_receipt_shape(receipt)
    assert receipt["status"] == "stale"
    assert receipt["result_code"] == "proposal_expired"
    # An expired proposal must not have executed anything.
    assert records.list("u1", "course-ai") == []
    # And the failure is replayable under the same idempotency key.
    replay = interactions.receipt_for_key("u1", "course-ai", "confirm-expired-1")
    assert replay["receipt_id"] == receipt["receipt_id"]


def test_rejected_proposal_confirm_returns_a_persisted_failed_receipt(monkeypatch, tmp_path: Path):
    interactions, records = _repositories(monkeypatch, tmp_path)
    proposal = _note_proposal(interactions)
    reject_proposal(
        _course(),
        user_id="u1",
        proposal_id=proposal["proposal_id"],
        reason="not_now",
        repository=interactions,
    )

    receipt = execute_proposal(
        _course(),
        user_id="u1",
        proposal_id=proposal["proposal_id"],
        idempotency_key="confirm-rejected-1",
        repository=interactions,
    )

    _assert_receipt_shape(receipt)
    assert receipt["status"] == "failed"
    assert receipt["result_code"] == "proposal_rejected"
    assert records.list("u1", "course-ai") == []


def test_runtime_change_receipt_uses_the_same_result_code_vocabulary(monkeypatch, tmp_path: Path):
    interactions, records = _repositories(monkeypatch, tmp_path)
    proposal = _note_proposal(interactions)
    moved = _runtime()
    moved["runtime_revision_id"] = "runtime-2"
    monkeypatch.setattr(ai_teacher_actions, "build_learning_runtime", lambda *a, **k: moved)

    receipt = execute_proposal(
        _course(),
        user_id="u1",
        proposal_id=proposal["proposal_id"],
        idempotency_key="confirm-stale-runtime-1",
        repository=interactions,
    )

    _assert_receipt_shape(receipt)
    assert receipt["status"] == "stale"
    assert receipt["result_code"] == "runtime_changed"
    assert records.list("u1", "course-ai") == []


def test_undo_of_a_non_reversible_receipt_returns_a_persisted_receipt(monkeypatch, tmp_path: Path):
    interactions, _records = _repositories(monkeypatch, tmp_path)
    proposal = propose_action(
        _course(),
        user_id="u1",
        action_type="open_runtime_action",
        target_ref={"node_id": "node-1"},
        payload={"node_id": "node-1"},
        repository=interactions,
    )
    receipt = execute_proposal(
        _course(),
        user_id="u1",
        proposal_id=proposal["proposal_id"],
        idempotency_key="confirm-runtime-action-1",
        repository=interactions,
    )
    assert receipt["undo_capability"] == "none"

    undone = undo_receipt(
        _course(),
        user_id="u1",
        receipt_id=receipt["receipt_id"],
        idempotency_key="undo-not-supported-1",
        repository=interactions,
    )

    _assert_receipt_shape(undone)
    assert undone["status"] == "failed"
    assert undone["result_code"] == "undo_not_supported"
    assert undone["undo_of_receipt_id"] == receipt["receipt_id"]


def test_undo_of_a_changed_record_returns_a_persisted_stale_receipt(monkeypatch, tmp_path: Path):
    interactions, records = _repositories(monkeypatch, tmp_path)
    proposal = _note_proposal(interactions)
    receipt = execute_proposal(
        _course(),
        user_id="u1",
        proposal_id=proposal["proposal_id"],
        idempotency_key="confirm-note-2",
        repository=interactions,
    )
    stored = records.list("u1", "course-ai")[0]
    records.update(
        "u1",
        "course-ai",
        stored["record_id"],
        expected_revision=int(stored["revision"]),
        changes={"content": "学习者自己改写了这条笔记"},
    )

    undone = undo_receipt(
        _course(),
        user_id="u1",
        receipt_id=receipt["receipt_id"],
        idempotency_key="undo-stale-1",
        repository=interactions,
    )

    _assert_receipt_shape(undone)
    assert undone["status"] == "stale"
    assert undone["result_code"] == "undo_target_changed"
    # The learner's own edit must survive a refused undo.
    assert records.list("u1", "course-ai")[0]["status"] != "archived"


def test_successful_undo_receipt_keeps_the_unified_shape(monkeypatch, tmp_path: Path):
    interactions, records = _repositories(monkeypatch, tmp_path)
    proposal = _note_proposal(interactions)
    receipt = execute_proposal(
        _course(),
        user_id="u1",
        proposal_id=proposal["proposal_id"],
        idempotency_key="confirm-note-3",
        repository=interactions,
    )

    undone = undo_receipt(
        _course(),
        user_id="u1",
        receipt_id=receipt["receipt_id"],
        idempotency_key="undo-ok-1",
        repository=interactions,
    )

    _assert_receipt_shape(undone)
    assert undone["status"] == "succeeded"
    assert undone["result_code"] == "record_archived"
    assert records.list("u1", "course-ai")[0]["status"] == "archived"


def _router_client(monkeypatch, tmp_path: Path):
    interactions, records = _repositories(monkeypatch, tmp_path)

    async def get_course(course_id: str):
        assert course_id == "course-ai"
        return _course()

    monkeypatch.setattr(ai_teacher_router, "get_course_or_404", get_course)
    monkeypatch.setattr(ai_teacher_router, "ai_teacher_repository", interactions)
    for name in ("propose_action", "execute_proposal", "reject_proposal", "undo_receipt"):
        original = getattr(ai_teacher_router, name)

        def bound(*args, _original=original, **kwargs):
            kwargs.setdefault("repository", interactions)
            return _original(*args, **kwargs)

        monkeypatch.setattr(ai_teacher_router, name, bound)
    app = FastAPI()
    app.include_router(ai_teacher_router.router)
    return TestClient(app), interactions, records


def test_router_returns_a_receipt_body_instead_of_a_bare_conflict(monkeypatch, tmp_path: Path):
    client, interactions, records = _router_client(monkeypatch, tmp_path)
    created = client.post(
        "/api/ai-teacher/proposals",
        json={
            "course_id": "course-ai",
            "action_type": "create_note",
            "target_ref": {"node_id": "node-1"},
            "payload": {"node_id": "node-1", "title": "变量", "content": "变量保存可变化的值"},
        },
        headers={"X-User-Id": "u1"},
    )
    assert created.status_code == 200
    proposal_id = created.json()["proposal_id"]
    client.post(
        f"/api/ai-teacher/proposals/{proposal_id}/reject",
        json={"course_id": "course-ai", "reason": "not_now"},
        headers={"X-User-Id": "u1"},
    )

    confirmed = client.post(
        f"/api/ai-teacher/proposals/{proposal_id}/confirm",
        json={"course_id": "course-ai", "idempotency_key": "router-rejected-1"},
        headers={"X-User-Id": "u1"},
    )

    assert confirmed.status_code == 200
    _assert_receipt_shape(confirmed.json())
    assert confirmed.json()["result_code"] == "proposal_rejected"
    assert records.list("u1", "course-ai") == []


def test_router_still_reports_a_missing_proposal_as_not_found(monkeypatch, tmp_path: Path):
    client, _interactions, _records = _router_client(monkeypatch, tmp_path)

    response = client.post(
        "/api/ai-teacher/proposals/aip_missing/confirm",
        json={"course_id": "course-ai", "idempotency_key": "router-missing-1"},
        headers={"X-User-Id": "u1"},
    )

    assert response.status_code == 404
