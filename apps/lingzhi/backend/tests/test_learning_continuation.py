from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from learning_continuation import build_learning_continuation
from routers import learning_continuation as continuation_router


def _course(*, mastery_required=False, prerequisite_policy="advisory"):
    return {
        "course_id": "course-1",
        "course_name": "测试课程",
        "current_course_version_id": "cv1",
        "nodes": [
            {"node_id": "c1", "node_name": "第一章", "node_level": 1, "parent_node_id": "root"},
            {
                "node_id": "n1", "node_name": "目标一", "node_level": 2,
                "parent_node_id": "c1", "node_content": "目标一正文" * 20,
                "prerequisite_node_ids": [],
            },
            {
                "node_id": "n2", "node_name": "目标二", "node_level": 2,
                "parent_node_id": "c1", "node_content": "目标二正文" * 20,
                "prerequisite_node_ids": ["n1"],
            },
            {"node_id": "c2", "node_name": "第二章", "node_level": 1, "parent_node_id": "root"},
            {
                "node_id": "n3", "node_name": "目标三", "node_level": 2,
                "parent_node_id": "c2", "node_content": "目标三正文" * 20,
                "prerequisite_node_ids": ["n2"],
            },
        ],
        "learning_assets": {
            "questions": [
                {
                    "asset_id": f"q-{node_id}-{practice_level}",
                    "revision_id": f"qr-{node_id}-{practice_level}",
                    "node_id": node_id,
                    "objective_id": f"lo-{node_id}",
                    "objective_revision_id": f"lor-{node_id}",
                    "practice_level": practice_level,
                    "status": "active",
                }
                for node_id in ("n1", "n2", "n3")
                for practice_level in ("concept_check", "mastery_check")
            ],
            "chapter_progression_contracts": [
                {
                    "chapter_id": chapter_id,
                    "mastery_required": mastery_required,
                    "prerequisite_policy": prerequisite_policy,
                    "completion_policy": "reading_covered",
                }
                for chapter_id in ("c1", "c2")
            ],
        },
    }


def _progress(*, n1=("not_started", "not_checked"), n2=("not_started", "not_checked"), n3=("not_started", "not_checked")):
    nodes = []
    for node_id, statuses in (("n1", n1), ("n2", n2), ("n3", n3)):
        nodes.append({
            "objective_id": f"lo-{node_id}",
            "objective_revision_id": f"lor-{node_id}",
            "statement": f"学习 {node_id}",
            "node_id": node_id,
            "node_name": node_id,
            "reading_status": statuses[0],
            "mastery_status": statuses[1],
            "evidence_event_ids": [],
            "practice_attempt_ids": [f"pa-{node_id}"] if statuses[1] == "needs_review" else [],
        })
    return {"nodes": nodes}


def _build(**overrides):
    values = {
        "course_data": _course(),
        "user_id": "u1",
        "node_id": "n1",
        "progress": _progress(),
        "snapshot": None,
        "attempts": [],
        "workflow": {"phase": "practice", "case": None, "session": None, "current_task": None},
        "records": [],
        "events": [],
        "now": datetime(2026, 7, 11, tzinfo=timezone.utc),
    }
    values.update(overrides)
    course_data = values.pop("course_data")
    return build_learning_continuation(course_data, **values)


def test_first_entry_starts_first_objective_without_fabricating_mastery():
    result = _build()

    assert result["entry_mode"] == "first_entry"
    assert result["progress"] == {
        "learning": "not_started",
        "mastery": "not_checked",
        "task_continuity": "none",
    }
    assert result["primary_action"]["action_type"] == "start_objective"
    assert result["primary_action"]["node_id"] == "n1"


def test_started_objective_requires_explicit_reading_completion():
    result = _build(progress=_progress(n1=("in_progress", "not_checked")))

    assert result["entry_mode"] == "continue_learning"
    assert result["primary_action"]["action_type"] == "complete_reading"
    assert result["primary_action"]["node_id"] == "n1"


def test_mastery_action_points_to_the_exact_mastery_task_without_creating_an_attempt():
    result = _build(
        course_data=_course(mastery_required=True),
        node_id="n2",
        progress=_progress(
            n1=("learned", "evidence_insufficient"),
            n2=("learned", "evidence_insufficient"),
        ),
    )

    action = result["primary_action"]
    assert action["action_type"] == "start_mastery_check"
    assert result["current_objective"]["node_id"] == "n1"
    assert action["task_ref"]["kind"] == "practice"
    assert action["task_ref"]["object_id"] == ""
    assert action["task_ref"]["task_revision_id"] == "qr-n1-mastery_check"
    assert action["task_ref"]["context"]["node_id"] == "n1"
    assert action["task_ref"]["context"]["objective_revision_id"]


def test_standard_course_missing_mastery_task_blocks_before_empty_practice():
    course = _course(mastery_required=True)
    course["generation_schema_version"] = "course_generation_v5"
    course["learning_assets"]["questions"] = [
        item for item in course["learning_assets"]["questions"]
        if item["node_id"] != "n1"
    ]
    result = _build(
        course_data=course,
        progress=_progress(
            n1=("learned", "evidence_insufficient"),
            n2=("learned", "evidence_insufficient"),
        ),
    )

    action = result["primary_action"]
    assert result["course_availability"]["mode"] == "standard"
    assert action["action_type"] == "repair_course_assets"
    assert action["reason_code"] == "required_practice_missing"
    assert action["availability"] == "unavailable"
    assert action["blocking"] is True


def test_declared_reading_only_course_advances_without_fabricating_mastery():
    course = _course(mastery_required=True)
    course["learning_asset_plan"] = {
        "schema_version": "learning_asset_plan_v1",
        "reading_only_degraded": True,
    }
    course["learning_assets"]["questions"] = []
    result = _build(
        course_data=course,
        progress=_progress(
            n1=("learned", "evidence_insufficient"),
            n2=("learned", "evidence_insufficient"),
        ),
    )

    assert result["course_availability"]["mode"] == "reading_only"
    assert result["chapter_result"]["state"] == "covered_unverified"
    assert result["primary_action"]["action_type"] == "start_next_chapter"


def test_completed_objective_advances_current_target_without_resetting_entry_mode():
    result = _build(progress=_progress(n1=("learned", "evidence_insufficient")))

    assert result["current_objective"]["node_id"] == "n2"
    assert result["primary_action"]["node_id"] == "n2"
    assert result["entry_mode"] == "continue_learning"


def test_active_remediation_outranks_due_review():
    workflow = {
        "phase": "remediation",
        "case": {
            "diagnostic_case_id": "dc1", "status": "remediating", "revision": 3,
            "course_version_id": "cv1", "node_id": "n1",
        },
        "session": {
            "remediation_session_id": "rs1", "status": "active", "revision": 2,
            "course_version_id": "cv1",
        },
        "current_task": {"task_revision_id": "rt1"},
    }
    records = [{
        "record_id": "review1", "record_type": "review_task", "status": "due",
        "node_id": "n2", "revision": 1,
    }]

    result = _build(workflow=workflow, records=records)

    assert result["primary_action"]["action_type"] == "resume_remediation"
    assert result["secondary_notices"][0]["notice_type"] == "due_review"


def test_other_chapter_workflow_is_notice_not_primary_action():
    workflow = {
        "phase": "remediation",
        "case": {
            "diagnostic_case_id": "dc1", "status": "remediating", "revision": 3,
            "course_version_id": "cv1", "node_id": "n1",
        },
        "session": {
            "remediation_session_id": "rs1", "status": "active", "revision": 2,
            "course_version_id": "cv1",
        },
        "current_task": {"task_revision_id": "rt1"},
    }

    result = _build(node_id="n3", workflow=workflow)

    assert result["primary_action"]["action_type"] == "start_objective"
    assert result["primary_action"]["node_id"] == "n3"
    assert result["secondary_notices"][0]["notice_type"] == "other_chapter_workflow"


def test_other_chapter_attempt_is_notice_not_resumed():
    attempt = {
        "attempt_id": "pa1", "revision": 2, "status": "in_progress", "node_id": "n1",
        "course_version_id": "cv1", "answer_payload": {"text": "draft"},
    }

    result = _build(node_id="n3", attempts=[attempt])

    assert result["primary_action"]["action_type"] == "start_objective"
    assert result["primary_action"]["node_id"] == "n3"
    assert result["secondary_notices"][0]["notice_type"] == "other_chapter_attempt"


def test_in_progress_attempt_resumes_but_pending_review_does_not_block():
    in_progress = {
        "attempt_id": "pa1", "revision": 2, "status": "in_progress", "node_id": "n1",
        "course_version_id": "cv1", "answer_payload": {"text": "draft"}, "created_at": "2026-07-10T00:00:00+00:00",
    }
    result = _build(attempts=[in_progress])
    assert result["primary_action"]["action_type"] == "resume_practice_attempt"

    grading = {**in_progress, "attempt_id": "pa2", "status": "grading"}
    result = _build(attempts=[grading])
    assert result["primary_action"]["action_type"] == "start_objective"
    assert result["secondary_notices"][0]["notice_type"] == "pending_review"


def test_version_change_has_highest_priority_and_preserves_conflict_reference():
    snapshot = {
        "snapshot_id": "ls1", "revision": 4, "course_version_id": "cv0",
        "node_id": "n1", "task_state": {"kind": "reading"},
    }

    result = _build(snapshot=snapshot)

    assert result["entry_mode"] == "version_change"
    assert result["progress"]["task_continuity"] == "stale"
    assert result["primary_action"]["action_type"] == "confirm_version_change"
    assert result["primary_action"]["requires_confirmation"] is True
    assert result["version_conflicts"] == [{"kind": "snapshot", "object_id": "ls1", "version_id": "cv0"}]
    assert result["version_transition"]["current_version_id"] == "cv1"
    assert result["version_transition"]["snapshot"]["action"] == "migrate"
    assert result["version_transition"]["snapshot"]["resolution_status"] == "node_fallback"


def test_missing_prerequisite_evidence_is_notice_but_reliable_required_gap_blocks():
    result = _build(node_id="n3")
    assert result["risks"][0]["level"] == "notice"
    assert result["primary_action"]["action_type"] == "start_objective"

    result = _build(
        course_data=_course(prerequisite_policy="required"),
        node_id="n3",
        progress=_progress(n2=("learned", "needs_review")),
    )
    assert result["risks"][0]["level"] == "action_required"
    assert result["primary_action"]["action_type"] == "resolve_prerequisite_gap"
    assert result["progress"]["task_continuity"] == "blocked"


def test_unknown_legacy_prerequisite_reference_is_not_shown_as_an_empty_risk():
    course = _course()
    course["nodes"][4]["prerequisite_node_ids"] = ["missing-node"]

    result = _build(course_data=course, node_id="n3")

    assert result["risks"] == []
    assert result["secondary_notices"] == []


def test_reading_complete_without_assets_can_advance_with_insufficient_evidence():
    result = _build(progress=_progress(n1=("learned", "evidence_insufficient"), n2=("learned", "evidence_insufficient")))

    assert result["chapter_result"]["state"] == "covered_unverified"
    assert result["progress"]["mastery"] == "evidence_insufficient"
    assert result["primary_action"]["action_type"] == "start_next_chapter"
    assert result["primary_action"]["node_id"] == "n3"


def test_open_issue_is_handled_after_required_learning_not_as_a_hard_blocker():
    records = [{
        "record_id": "issue1", "record_type": "issue", "status": "open",
        "node_id": "n1", "revision": 1, "category": "question",
    }]
    result = _build(
        progress=_progress(n1=("learned", "evidence_insufficient"), n2=("learned", "evidence_insufficient")),
        records=records,
    )

    assert result["progress"]["task_continuity"] == "none"
    assert result["primary_action"]["action_type"] == "resolve_open_issue"
    assert result["primary_action"]["blocking"] is False


def test_progression_contract_can_leave_optional_objective_for_later():
    course = _course()
    course["learning_assets"]["chapter_progression_contracts"][0]["required_objective_ids"] = ["lo-n1"]
    result = _build(
        course_data=course,
        progress=_progress(n1=("learned", "evidence_insufficient"), n2=("not_started", "not_checked")),
    )

    assert result["chapter_result"]["state"] == "covered_unverified"
    assert result["primary_action"]["action_type"] == "start_next_chapter"


def test_projection_revision_depends_on_input_revisions_not_time():
    first = _build(now=datetime(2026, 7, 11, tzinfo=timezone.utc))
    second = _build(now=datetime(2026, 7, 12, tzinfo=timezone.utc))

    assert first["projection_revision_id"] == second["projection_revision_id"]

    changed = _build(records=[{
        "record_id": "r1", "revision": 1, "record_type": "review_task", "status": "pending",
    }])
    assert first["projection_revision_id"] != changed["projection_revision_id"]


def test_continuation_api_and_risk_deferral_revision_guard(monkeypatch):
    async def course_or_404(_course_id):
        return _course()

    current = _build(node_id="n3")
    monkeypatch.setattr(continuation_router, "get_course_or_404", course_or_404)
    monkeypatch.setattr(continuation_router, "build_learning_continuation", lambda *_args, **_kwargs: current)
    recorded = []
    monkeypatch.setattr(continuation_router, "record_learning_event", lambda **payload: recorded.append(payload) or payload)
    app = FastAPI()
    app.include_router(continuation_router.router, prefix="/api")
    client = TestClient(app)

    response = client.get("/api/courses/course-1/learning-continuation?node_id=n3", headers={"X-User-Id": "u1"})
    assert response.status_code == 200
    assert response.json()["primary_action"]["action_type"] == "start_objective"

    risk_id = current["risks"][0]["risk_id"]
    conflict = client.post(
        f"/api/courses/course-1/learning-continuation/risks/{risk_id}/defer",
        json={"expected_projection_revision_id": "old", "node_id": "n3"},
        headers={"X-User-Id": "u1"},
    )
    assert conflict.status_code == 409

    deferred = client.post(
        f"/api/courses/course-1/learning-continuation/risks/{risk_id}/defer",
        json={"expected_projection_revision_id": current["projection_revision_id"], "node_id": "n3"},
        headers={"X-User-Id": "u1"},
    )
    assert deferred.status_code == 200
    assert recorded[0]["event_type"] == "entry_risk_deferred"


def test_version_transition_confirmation_api_and_revision_conflict(monkeypatch):
    async def course_or_404(_course_id):
        return _course()

    monkeypatch.setattr(continuation_router, "get_course_or_404", course_or_404)
    captured = {}

    def confirm(_course, **payload):
        captured.update(payload)
        return {"status": "confirmed", "runtime": {"continuation": {"version_transition": None}}}

    monkeypatch.setattr(continuation_router, "confirm_version_transition", confirm)
    app = FastAPI()
    app.include_router(continuation_router.router, prefix="/api")
    client = TestClient(app)

    response = client.post(
        "/api/courses/course-1/learning-continuation/version-change/confirm",
        json={
            "expected_projection_revision_id": "projection-1",
            "request_id": "request-1",
            "node_id": "n1",
        },
        headers={"X-User-Id": "u1"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"
    assert captured["user_id"] == "u1"
    assert captured["expected_projection_revision_id"] == "projection-1"

    monkeypatch.setattr(
        continuation_router,
        "confirm_version_transition",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            continuation_router.VersionTransitionConflict({"projection_revision_id": "current"})
        ),
    )
    conflict = client.post(
        "/api/courses/course-1/learning-continuation/version-change/confirm",
        json={"expected_projection_revision_id": "old", "request_id": "request-2"},
        headers={"X-User-Id": "u1"},
    )

    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "learning_version_transition_revision_conflict"
