from copy import deepcopy

import learning_continuation
import learning_runtime
import learning_version_transition as transition
from content_blocks import project_course_content_blocks
from learning_records import LearningRecordRepository, enrich_record_payload
from learning_snapshots import LearningSnapshotRepository
from practice_attempts import PracticeAttemptRepository


def _course(*, version="cv2", content="更新后的向量定义"):
    return {
        "course_id": "c1",
        "course_name": "线性代数",
        "current_course_version_id": version,
        "nodes": [{
            "node_id": "n1",
            "node_level": 2,
            "node_name": "向量",
            "learning_objective": "能够解释向量",
            "node_content": f"## 定义\n\n{content}",
        }],
        "learning_assets": {
            "questions": [{
                "asset_id": "q1", "revision_id": "qr2", "node_id": "n1",
                "practice_level": "mastery_check", "mastery_criterion_ids": ["mc1"],
            }],
            "mastery_criteria": [{
                "criterion_id": "mc1", "revision_id": "mcr2", "node_id": "n1",
                "observable_performance": "解释向量", "assessment_bindings": ["qr2"],
            }],
        },
    }


def _old_snapshot(course):
    old = project_course_content_blocks(_course(version="cv1", content="旧向量定义"))
    block = old["nodes"][0]["content_blocks"][0]
    return {
        "course_version_id": "cv1",
        "node_id": "n1",
        "node_name": "向量",
        "content_anchor": {**block, "progress": 0.45},
        "session": {"session_id": "s1", "device_id": "d1", "started_at": "2026-07-12T00:00:00Z"},
        "task_state": {
            "kind": "practice", "object_id": "pa1", "task_revision_id": "qr1", "status": "active",
            "context": {"course_id": "c1", "course_version_id": "cv1", "node_id": "n1"},
            "return_node_id": "n1", "draft_revision": 2, "metadata": {},
        },
        "interaction_state": {"conversation_id": "conv1", "issue_id": "", "remediation_session_id": "rem1"},
        "fallback_scroll_top": 240,
        "activity_at": "2026-07-12T00:00:00Z",
        "source": "live",
    }


def test_plan_classifies_snapshot_attempt_workflow_and_records(tmp_path):
    course = _course()
    record_repository = LearningRecordRepository(tmp_path / "records")
    record = record_repository.create("u1", "c1", enrich_record_payload(_course(version="cv1", content="旧向量定义"), {
        "record_type": "note", "node_id": "n1", "quote": "旧向量定义", "content": "个人理解",
    }))
    plan = transition.build_version_transition_plan(
        course,
        user_id="u1",
        snapshot={"snapshot_id": "ls1", **_old_snapshot(course)},
        attempts=[{
            "attempt_id": "pa1", "course_version_id": "cv1", "status": "in_progress",
            "node_id": "n1", "task_revision_id": "qr1", "answer_payload": {"text": "草稿"},
        }],
        workflow={
            "case": {"diagnostic_case_id": "dc1", "course_version_id": "cv1", "status": "testing"},
            "session": None,
        },
        records=[record],
    )

    assert plan["source_version_ids"] == ["cv1"]
    assert plan["snapshot"]["resolution_status"] == "updated_block"
    assert plan["snapshot"]["action"] == "migrate"
    assert plan["attempts"][0]["action"] == "invalidate"
    assert plan["workflows"][0]["action"] == "mark_stale"
    assert plan["records"]["total"] == 1
    assert plan["can_confirm"] is True


def test_deleted_snapshot_requires_explicit_target():
    course = _course()
    snapshot = _old_snapshot(course)
    snapshot["node_id"] = "deleted"
    snapshot["content_anchor"] = {"block_id": "missing", "content_fingerprint": "missing"}

    plan = transition.build_version_transition_plan(
        course,
        user_id="u1",
        snapshot={"snapshot_id": "ls1", **snapshot},
        attempts=[],
        workflow={"case": None, "session": None},
        records=[],
    )

    assert plan["snapshot"]["resolution_status"] == "course_fallback"
    assert plan["requires_target_node"] is True
    assert plan["can_confirm"] is False


def test_confirmation_migrates_pointer_invalidates_task_and_is_idempotent(monkeypatch, tmp_path):
    course = _course()
    snapshots = LearningSnapshotRepository(tmp_path / "snapshots")
    attempts = PracticeAttemptRepository(tmp_path / "attempts")
    records = LearningRecordRepository(tmp_path / "records")
    saved_snapshot = snapshots.save("u1", "c1", expected_revision=0, payload=_old_snapshot(course))
    attempt, _ = attempts.create_once("u1", "c1", {
        "attempt_id": "pa1", "course_version_id": "cv1", "node_id": "n1",
        "task_revision_id": "qr1", "question_revision_id": "qr1", "answer_payload": {"text": "草稿"},
    })
    events = []
    plan = transition.build_version_transition_plan(
        course,
        user_id="u1",
        snapshot=saved_snapshot,
        attempts=[attempt],
        workflow={"case": None, "session": None},
        records=[],
    )
    projection = {"projection_revision_id": "projection-1", "version_transition": plan}

    monkeypatch.setattr(transition, "learning_snapshot_repository", snapshots)
    monkeypatch.setattr(transition, "practice_attempt_repository", attempts)
    monkeypatch.setattr(transition, "learning_record_repository", records)
    monkeypatch.setattr(transition, "invalidate_stale_workflows", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(transition, "load_learning_events", lambda **_kwargs: deepcopy(events))

    def save_event(**payload):
        event = {"event_id": "evt1", **deepcopy(payload)}
        events.append(event)
        return event

    monkeypatch.setattr(transition, "record_learning_event", save_event)
    monkeypatch.setattr(
        learning_continuation,
        "build_learning_continuation",
        lambda *_args, **_kwargs: deepcopy(projection) if snapshots.load("u1", "c1")["course_version_id"] == "cv1" else {
            "projection_revision_id": "projection-after",
            "version_transition": None,
        },
    )
    monkeypatch.setattr(learning_runtime, "build_learning_runtime", lambda *_args, **_kwargs: {
        "snapshot": {"current": snapshots.load("u1", "c1")},
        "continuation": {"version_transition": None},
    })

    first = transition.confirm_version_transition(
        course,
        user_id="u1",
        expected_projection_revision_id="projection-1",
        request_id="request-1",
        node_id="n1",
    )
    second = transition.confirm_version_transition(
        course,
        user_id="u1",
        expected_projection_revision_id="stale-after-success",
        request_id="request-1",
        node_id="n1",
    )

    migrated = snapshots.load("u1", "c1")
    invalidated = attempts.get("u1", "c1", "pa1")
    assert first["status"] == "confirmed"
    assert second["status"] == "already_confirmed"
    assert migrated["course_version_id"] == "cv2"
    assert migrated["task_state"]["kind"] == "reading"
    assert migrated["task_state"]["metadata"]["invalidated_task_id"] == "pa1"
    assert invalidated["status"] == "invalidated"
    assert invalidated["course_version_id"] == "cv1"
    assert invalidated["answer_payload"] == {"text": "草稿"}
    assert len(events) == 1

    events.clear()
    recovered = transition.confirm_version_transition(
        course,
        user_id="u1",
        expected_projection_revision_id="stale-after-interruption",
        request_id="request-1",
        node_id="n1",
    )
    assert recovered["status"] == "already_confirmed"
    assert events[0]["source"] == "learning_continuation.version_change.recovery"
