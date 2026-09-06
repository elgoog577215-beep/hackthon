"""Proactive-suggestion gating must survive refresh and follow the learner across devices.

`build_trigger_candidate` already refuses to fire on weak evidence (only the 7
strong runtime actions qualify) and already suppresses a rejected candidate for
the same action + target + evidence revision. What it had no notion of was the
*cost of interrupting a person*:

* it fires anywhere, including mid-reading;
* it has no frequency ceiling, so a learner with three blocking issues gets
  three interruptions in a row;
* `not_now` only holds until the evidence revision changes, and a "due review"
  produces new revisions constantly — so "not now" could come back minutes later.

The owner's decisions (2026-08-12): show only at natural pauses; at most 2 per
learning session and 1 per node; `not_now` additionally silent for 24 hours even
if the evidence revision moved; `never` stays permanent.

All three live server-side on purpose. A client-side counter would reset on
refresh and would not follow the learner to a second device, which the archived
spec explicitly forbids ("拒绝和抑制 MUST 在刷新与跨设备后保持有效").
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import ai_teacher_actions
from ai_teacher_actions import (
    NODE_SUGGESTION_LIMIT,
    NOT_NOW_QUIET_HOURS,
    SESSION_SUGGESTION_LIMIT,
    build_trigger_candidate,
    record_suggestion_shown,
    reject_proposal,
)
from ai_teacher_state import AITeacherRepository


def _course() -> dict:
    return {
        "course_id": "course-ai",
        "current_course_version_id": "cv-1",
        "course_name": "线性代数",
        "nodes": [
            {"node_id": "node-1", "node_name": "向量", "node_level": 2, "node_content": "正文"},
            {"node_id": "node-2", "node_name": "矩阵", "node_level": 2, "node_content": "正文"},
        ],
    }


def _runtime(
    action_type: str = "resume_diagnostic",
    *,
    node_id: str = "node-1",
    revision: str = "runtime-1",
) -> dict:
    return {
        "runtime_revision_id": revision,
        "context": {
            "course_id": "course-ai",
            "course_version_id": "cv-1",
            "node_id": node_id,
            "objective_id": "obj-1",
            "objective_revision_id": "objr-1",
        },
        "continuation": {
            "primary_action": {
                "action_id": f"action-{node_id}",
                "action_type": action_type,
                "reason_code": "diagnostic_open",
                "task_ref": {"kind": "diagnostic", "object_id": f"dg-{node_id}", "node_id": node_id},
            }
        },
    }


def _patch_runtime(monkeypatch, runtime: dict) -> None:
    monkeypatch.setattr(ai_teacher_actions, "build_learning_runtime", lambda *a, **k: runtime)


def _repository(tmp_path: Path) -> AITeacherRepository:
    return AITeacherRepository(tmp_path / "interactions")


# --------------------------------------------------------------------------
# Timing: natural pauses only
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "moment",
    ["section_completed", "practice_submitted", "course_entered"],
)
def test_candidate_is_offered_at_each_natural_pause(monkeypatch, tmp_path: Path, moment: str):
    _patch_runtime(monkeypatch, _runtime())
    repository = _repository(tmp_path)

    candidate = build_trigger_candidate(
        _course(),
        user_id="u1",
        node_id="node-1",
        moment=moment,
        session_id="sess-1",
        repository=repository,
    )

    assert candidate is not None
    assert candidate["moment"] == moment


def test_candidate_is_withheld_while_the_learner_is_reading(monkeypatch, tmp_path: Path):
    """Mid-reading is the one place a strong candidate must still stay silent."""
    _patch_runtime(monkeypatch, _runtime())
    repository = _repository(tmp_path)

    assert build_trigger_candidate(
        _course(),
        user_id="u1",
        node_id="node-1",
        moment="reading",
        session_id="sess-1",
        repository=repository,
    ) is None


def test_unknown_moment_is_treated_as_not_a_pause(monkeypatch, tmp_path: Path):
    _patch_runtime(monkeypatch, _runtime())
    repository = _repository(tmp_path)

    assert build_trigger_candidate(
        _course(),
        user_id="u1",
        node_id="node-1",
        moment="scrolled_fast",
        session_id="sess-1",
        repository=repository,
    ) is None


def test_weak_runtime_action_still_never_triggers(monkeypatch, tmp_path: Path):
    """The pre-existing strong-evidence gate must keep working at a pause."""
    _patch_runtime(monkeypatch, _runtime("complete_reading"))
    repository = _repository(tmp_path)

    assert build_trigger_candidate(
        _course(),
        user_id="u1",
        node_id="node-1",
        moment="section_completed",
        session_id="sess-1",
        repository=repository,
    ) is None


# --------------------------------------------------------------------------
# Budget: 2 per session, 1 per node — persisted, so it survives a refresh
# --------------------------------------------------------------------------

def test_session_budget_stops_the_third_suggestion(monkeypatch, tmp_path: Path):
    repository = _repository(tmp_path)
    shown = []
    for index, node_id in enumerate(("node-1", "node-2", "node-3"), start=1):
        _patch_runtime(monkeypatch, _runtime(node_id=node_id, revision=f"runtime-{index}"))
        candidate = build_trigger_candidate(
            _course(),
            user_id="u1",
            node_id=node_id,
            moment="section_completed",
            session_id="sess-1",
            repository=repository,
        )
        if candidate:
            shown.append(candidate)
            record_suggestion_shown(
                user_id="u1",
                course_id="course-ai",
                candidate=candidate,
                session_id="sess-1",
                repository=repository,
            )

    assert len(shown) == SESSION_SUGGESTION_LIMIT == 2


def test_node_budget_stops_a_second_suggestion_on_the_same_node(monkeypatch, tmp_path: Path):
    repository = _repository(tmp_path)
    _patch_runtime(monkeypatch, _runtime(node_id="node-1", revision="runtime-1"))
    first = build_trigger_candidate(
        _course(),
        user_id="u1",
        node_id="node-1",
        moment="section_completed",
        session_id="sess-1",
        repository=repository,
    )
    record_suggestion_shown(
        user_id="u1",
        course_id="course-ai",
        candidate=first,
        session_id="sess-1",
        repository=repository,
    )

    # Same node, different evidence revision: the dedupe key no longer matches,
    # so only the per-node ceiling can stop this one.
    _patch_runtime(monkeypatch, _runtime(node_id="node-1", revision="runtime-2"))
    second = build_trigger_candidate(
        _course(),
        user_id="u1",
        node_id="node-1",
        moment="section_completed",
        session_id="sess-1",
        repository=repository,
    )

    assert first is not None
    assert second is None
    assert NODE_SUGGESTION_LIMIT == 1


def test_budget_is_persisted_so_a_refresh_cannot_reset_it(monkeypatch, tmp_path: Path):
    """A fresh repository object over the same directory = a reloaded page."""
    _patch_runtime(monkeypatch, _runtime(node_id="node-1"))
    first_repository = _repository(tmp_path)
    candidate = build_trigger_candidate(
        _course(),
        user_id="u1",
        node_id="node-1",
        moment="section_completed",
        session_id="sess-1",
        repository=first_repository,
    )
    record_suggestion_shown(
        user_id="u1",
        course_id="course-ai",
        candidate=candidate,
        session_id="sess-1",
        repository=first_repository,
    )

    reloaded = _repository(tmp_path)
    _patch_runtime(monkeypatch, _runtime(node_id="node-1", revision="runtime-2"))
    assert build_trigger_candidate(
        _course(),
        user_id="u1",
        node_id="node-1",
        moment="section_completed",
        session_id="sess-1",
        repository=reloaded,
    ) is None


def test_budget_follows_the_learner_to_a_second_device(monkeypatch, tmp_path: Path):
    """Same user + same session id from another device shares one budget."""
    repository = _repository(tmp_path)
    _patch_runtime(monkeypatch, _runtime(node_id="node-1"))
    candidate = build_trigger_candidate(
        _course(),
        user_id="u1",
        node_id="node-1",
        moment="section_completed",
        session_id="sess-shared",
        repository=repository,
    )
    record_suggestion_shown(
        user_id="u1",
        course_id="course-ai",
        candidate=candidate,
        session_id="sess-shared",
        repository=repository,
    )

    _patch_runtime(monkeypatch, _runtime(node_id="node-1", revision="runtime-2"))
    assert build_trigger_candidate(
        _course(),
        user_id="u1",
        node_id="node-1",
        moment="course_entered",
        session_id="sess-shared",
        repository=repository,
    ) is None


def test_a_new_session_gets_a_fresh_session_budget(monkeypatch, tmp_path: Path):
    """The ceiling is per learning session, not permanent."""
    repository = _repository(tmp_path)
    for index, node_id in enumerate(("node-1", "node-2"), start=1):
        _patch_runtime(monkeypatch, _runtime(node_id=node_id, revision=f"runtime-{index}"))
        candidate = build_trigger_candidate(
            _course(),
            user_id="u1",
            node_id=node_id,
            moment="section_completed",
            session_id="sess-1",
            repository=repository,
        )
        record_suggestion_shown(
            user_id="u1",
            course_id="course-ai",
            candidate=candidate,
            session_id="sess-1",
            repository=repository,
        )

    _patch_runtime(monkeypatch, _runtime(node_id="node-3", revision="runtime-3"))
    assert build_trigger_candidate(
        _course(),
        user_id="u1",
        node_id="node-3",
        moment="section_completed",
        session_id="sess-2",
        repository=repository,
    ) is not None


# --------------------------------------------------------------------------
# not_now: 24-hour floor, independent of evidence revision
# --------------------------------------------------------------------------

def test_not_now_stays_quiet_for_24h_even_when_the_evidence_revision_moves(
    monkeypatch,
    tmp_path: Path,
):
    """The case that made "not now" feel broken: due-review keeps re-revising."""
    repository = _repository(tmp_path)
    _patch_runtime(monkeypatch, _runtime(node_id="node-1", revision="runtime-1"))
    candidate = build_trigger_candidate(
        _course(),
        user_id="u1",
        node_id="node-1",
        moment="section_completed",
        session_id="sess-1",
        repository=repository,
    )
    repository.save_suppression("u1", "course-ai", {
        "suppression_key": candidate["dedupe_key"],
        "evidence_revision": candidate["runtime_revision_id"],
        "mode": "not_now",
        "quiet_until": (datetime.now(timezone.utc) + timedelta(hours=NOT_NOW_QUIET_HOURS)).isoformat(),
    })

    # New evidence revision, new session, fresh budget — only the 24h floor is left.
    _patch_runtime(monkeypatch, _runtime(node_id="node-1", revision="runtime-2"))
    assert build_trigger_candidate(
        _course(),
        user_id="u1",
        node_id="node-1",
        moment="section_completed",
        session_id="sess-2",
        repository=repository,
    ) is None
    assert NOT_NOW_QUIET_HOURS == 24


def test_not_now_returns_after_the_quiet_window_expires(monkeypatch, tmp_path: Path):
    repository = _repository(tmp_path)
    _patch_runtime(monkeypatch, _runtime(node_id="node-1", revision="runtime-1"))
    candidate = build_trigger_candidate(
        _course(),
        user_id="u1",
        node_id="node-1",
        moment="section_completed",
        session_id="sess-1",
        repository=repository,
    )
    repository.save_suppression("u1", "course-ai", {
        "suppression_key": candidate["dedupe_key"],
        "evidence_revision": "runtime-1",
        "mode": "not_now",
        "quiet_until": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
    })

    _patch_runtime(monkeypatch, _runtime(node_id="node-1", revision="runtime-2"))
    assert build_trigger_candidate(
        _course(),
        user_id="u1",
        node_id="node-1",
        moment="section_completed",
        session_id="sess-2",
        repository=repository,
    ) is not None


def test_never_remains_permanent(monkeypatch, tmp_path: Path):
    repository = _repository(tmp_path)
    _patch_runtime(monkeypatch, _runtime(node_id="node-1", revision="runtime-1"))
    candidate = build_trigger_candidate(
        _course(),
        user_id="u1",
        node_id="node-1",
        moment="section_completed",
        session_id="sess-1",
        repository=repository,
    )
    repository.save_suppression("u1", "course-ai", {
        "suppression_key": candidate["dedupe_key"],
        "evidence_revision": "runtime-1",
        "mode": "never",
        "quiet_until": (datetime.now(timezone.utc) - timedelta(days=400)).isoformat(),
    })

    _patch_runtime(monkeypatch, _runtime(node_id="node-1", revision="runtime-2"))
    assert build_trigger_candidate(
        _course(),
        user_id="u1",
        node_id="node-1",
        moment="section_completed",
        session_id="sess-9",
        repository=repository,
    ) is None


def test_rejecting_a_proposal_writes_the_24h_quiet_window(monkeypatch, tmp_path: Path):
    """`not_now` from the real reject path must carry the floor, not just tests."""
    repository = _repository(tmp_path)
    monkeypatch.setattr(ai_teacher_actions, "build_learning_runtime", lambda *a, **k: _runtime())
    proposal = ai_teacher_actions.propose_action(
        _course(),
        user_id="u1",
        action_type="create_note",
        target_ref={"node_id": "node-1"},
        payload={"node_id": "node-1", "title": "t", "content": "c"},
        repository=repository,
    )

    result = reject_proposal(
        _course(),
        user_id="u1",
        proposal_id=proposal["proposal_id"],
        reason="not_now",
        repository=repository,
    )

    quiet_until = str(result["suppression"].get("quiet_until") or "")
    assert quiet_until
    parsed = datetime.fromisoformat(quiet_until.replace("Z", "+00:00"))
    delta_hours = (parsed - datetime.now(timezone.utc)).total_seconds() / 3600
    assert 23 < delta_hours <= 24


def test_never_rejection_records_no_expiring_window(monkeypatch, tmp_path: Path):
    repository = _repository(tmp_path)
    monkeypatch.setattr(ai_teacher_actions, "build_learning_runtime", lambda *a, **k: _runtime())
    proposal = ai_teacher_actions.propose_action(
        _course(),
        user_id="u1",
        action_type="create_note",
        target_ref={"node_id": "node-1"},
        payload={"node_id": "node-1", "title": "t", "content": "c"},
        repository=repository,
    )

    result = reject_proposal(
        _course(),
        user_id="u1",
        proposal_id=proposal["proposal_id"],
        reason="never",
        repository=repository,
    )

    assert result["suppression"]["mode"] == "never"
    assert not result["suppression"].get("quiet_until")


# --------------------------------------------------------------------------
# HTTP surface: the same three rules must hold through the router
# --------------------------------------------------------------------------

def _client(monkeypatch, tmp_path: Path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from routers import ai_teacher as router_module

    repository = _repository(tmp_path)

    async def get_course(course_id: str):
        assert course_id == "course-ai"
        return _course()

    monkeypatch.setattr(router_module, "get_course_or_404", get_course)
    monkeypatch.setattr(router_module, "ai_teacher_repository", repository)
    for name in ("build_trigger_candidate", "record_suggestion_shown", "suppress_suggestion"):
        original = getattr(router_module, name)

        def bound(*args, _original=original, **kwargs):
            kwargs.setdefault("repository", repository)
            return _original(*args, **kwargs)

        monkeypatch.setattr(router_module, name, bound)

    app = FastAPI()
    app.include_router(router_module.router)
    return TestClient(app), repository


def _ask(client, *, moment: str, node_id: str = "node-1", session_id: str = "sess-1"):
    return client.get(
        "/api/ai-teacher/trigger",
        params={
            "course_id": "course-ai",
            "node_id": node_id,
            "moment": moment,
            "session_id": session_id,
        },
        headers={"X-User-Id": "u1"},
    ).json()["candidate"]


def test_router_withholds_a_candidate_mid_reading(monkeypatch, tmp_path: Path):
    _patch_runtime(monkeypatch, _runtime())
    client, _repository = _client(monkeypatch, tmp_path)

    assert _ask(client, moment="reading") is None
    assert _ask(client, moment="section_completed") is not None


def test_router_enforces_the_session_budget_across_requests(monkeypatch, tmp_path: Path):
    """Each request is independent — only persisted state can hold the ceiling."""
    client, _repository = _client(monkeypatch, tmp_path)
    delivered = 0
    for index, node_id in enumerate(("node-1", "node-2", "node-3"), start=1):
        _patch_runtime(monkeypatch, _runtime(node_id=node_id, revision=f"runtime-{index}"))
        candidate = _ask(client, moment="section_completed", node_id=node_id)
        if not candidate:
            continue
        delivered += 1
        response = client.post(
            "/api/ai-teacher/trigger/shown",
            json={
                "course_id": "course-ai",
                "trigger_id": candidate["trigger_id"],
                "dedupe_key": candidate["dedupe_key"],
                "node_id": candidate["node_id"],
                "session_id": "sess-1",
                "moment": candidate["moment"],
            },
            headers={"X-User-Id": "u1"},
        )
        assert response.status_code == 200

    assert delivered == SESSION_SUGGESTION_LIMIT


def test_router_keeps_a_rejected_suggestion_quiet_across_sessions(monkeypatch, tmp_path: Path):
    """Reject through the real endpoint, then confirm the 24h floor holds."""
    _patch_runtime(monkeypatch, _runtime())
    client, repository = _client(monkeypatch, tmp_path)
    candidate = _ask(client, moment="section_completed")
    assert candidate is not None

    repository.save_suppression("u1", "course-ai", {
        "suppression_key": candidate["dedupe_key"],
        "evidence_revision": candidate["runtime_revision_id"],
        "mode": "not_now",
        "quiet_until": (datetime.now(timezone.utc) + timedelta(hours=NOT_NOW_QUIET_HOURS)).isoformat(),
    })

    # New evidence revision AND a new session: nothing but the quiet window left.
    _patch_runtime(monkeypatch, _runtime(revision="runtime-later"))
    assert _ask(client, moment="course_entered", session_id="sess-2") is None


def test_router_suppress_endpoint_holds_not_now_for_24h(monkeypatch, tmp_path: Path):
    """A dismissed suggestion has no proposal, so it needs its own suppress path."""
    _patch_runtime(monkeypatch, _runtime())
    client, _repository = _client(monkeypatch, tmp_path)
    candidate = _ask(client, moment="section_completed")

    response = client.post(
        "/api/ai-teacher/trigger/suppress",
        json={
            "course_id": "course-ai",
            "dedupe_key": candidate["dedupe_key"],
            "runtime_revision_id": candidate["runtime_revision_id"],
            "reason": "not_now",
        },
        headers={"X-User-Id": "u1"},
    )
    assert response.status_code == 200
    assert response.json()["mode"] == "not_now"

    _patch_runtime(monkeypatch, _runtime(revision="runtime-later"))
    assert _ask(client, moment="course_entered", session_id="sess-fresh") is None


def test_router_suppress_endpoint_makes_never_permanent(monkeypatch, tmp_path: Path):
    _patch_runtime(monkeypatch, _runtime())
    client, repository = _client(monkeypatch, tmp_path)
    candidate = _ask(client, moment="section_completed")

    client.post(
        "/api/ai-teacher/trigger/suppress",
        json={
            "course_id": "course-ai",
            "dedupe_key": candidate["dedupe_key"],
            "runtime_revision_id": candidate["runtime_revision_id"],
            "reason": "never",
        },
        headers={"X-User-Id": "u1"},
    )

    stored = repository.list_suppressions("u1", "course-ai")[0]
    assert stored["mode"] == "never"
    assert not stored.get("quiet_until")
    _patch_runtime(monkeypatch, _runtime(revision="runtime-much-later"))
    assert _ask(client, moment="course_entered", session_id="sess-much-later") is None
