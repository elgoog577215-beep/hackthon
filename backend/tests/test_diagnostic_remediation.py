from copy import deepcopy

import diagnostic_service
import learning_events
from fastapi import FastAPI
from fastapi.testclient import TestClient
from assessment_tasks import project_assessment_task
from diagnostic_service import (
    advance_workflow_after_grade,
    consider_course_failure,
    invalidate_stale_workflows,
    workflow_view,
)
from diagnostic_workflows import DiagnosticWorkflowRepository
from practice_attempts import PracticeAttemptRepository
from learning_progress import project_learning_objective_bindings
from routers import diagnostics as diagnostics_router
from routers import practice as practice_router


class MemoryStorage:
    def __init__(self):
        self.data = {}

    def load_data(self, filename):
        return deepcopy(self.data.get(filename, []))

    def save_data(self, filename, value):
        self.data[filename] = deepcopy(value)


def _course(version="cv1"):
    objective = {
        "objective_id": "lo1",
        "objective_revision_id": "lor1",
        "node_id": "n1",
        "learning_objective": "能够说明向量的大小与方向",
        "concept_ids": ["math.vector"],
        "skill_unit_ids": ["skill.vector.describe"],
        "mistake_point_ids": ["mistake.vector.direction"],
        "improvement_point_ids": ["improve.vector.compare"],
    }
    exact = {
        **objective,
        "question_type": "short_answer",
        "answer_spec": {"type": "exact", "correct_answer": "大小和方向", "pass_score": 70},
    }
    return {
        "course_id": "c1",
        "current_course_version_id": version,
        "nodes": [{"node_id": "n1", "node_name": "向量"}],
        "learning_assets": {
            "questions": [{**exact, "revision_id": "qr1", "practice_level": "mastery_check"}],
            "mastery_criteria": [{
                "criterion_id": "mc1", "revision_id": "mcr1", "node_id": "n1",
                "objective_revision_id": "lor1", "assessment_bindings": ["qr1"],
            }],
            "diagnostic_templates": [{
                **exact, "revision_id": "dt1", "practice_level": "diagnostic_probe",
            }],
            "remediation_units": [{
                "revision_id": "ru1", "objective_revision_id": "lor1", "category": "process_error",
                "remediation_objective": "只修复大小与方向的判断",
                "micro_explanation": "分别检查大小和方向。",
                "worked_contrast": "比较同向与反向向量。",
                "content_block_ids": ["b1"],
                "guided_task": {**exact, "revision_id": "gt1", "practice_level": "remediation_guided"},
            }],
            "validation_questions": [
                {
                    **exact, "revision_id": f"vq{index}", "practice_level": "remediation_validation",
                    "quality_status": "passed",
                }
                for index in (1, 2)
            ],
            "misconceptions": [],
            "final_assessment": [],
        },
    }


def _attempt(repo, *, attempt_id, result, purpose="course_practice", task_revision_id="qr1", **extra):
    attempt, _ = repo.create_once("u1", "c1", {
        "attempt_id": attempt_id,
        "resume": False,
        "task_revision_id": task_revision_id,
        "question_revision_id": task_revision_id,
        "task_purpose": purpose,
        "course_version_id": "cv1",
        "node_id": "n1",
        "node_name": "向量",
        "objective_id": "lo1",
        "objective_revision_id": "lor1",
        "criterion_id": "mc1",
        "criterion_revision_id": "mcr1",
        **extra,
    })
    submitted, _ = repo.submit(
        "u1", "c1", attempt_id, expected_revision=attempt["revision"],
        request_id=f"request-{attempt_id}", answer_payload={"text": "回答"}, active_seconds=10,
    )
    return repo.apply_grade(
        "u1", "c1", attempt_id, expected_revision=submitted["revision"], result=result,
    )


def _result(passed, support=0):
    return {
        "status": "graded", "passed": passed, "score": 100 if passed else 0,
        "grading_confidence": 1.0, "support_level": support,
        "mastery_eligible": bool(passed and support == 0),
        "rubric_results": [{"criterion": "答案正确", "met": passed}],
    }


def _repositories(monkeypatch, tmp_path):
    attempts = PracticeAttemptRepository(tmp_path / "attempts")
    workflows = DiagnosticWorkflowRepository(tmp_path / "workflows")
    monkeypatch.setattr(diagnostic_service, "practice_attempt_repository", attempts)
    monkeypatch.setattr(diagnostic_service, "diagnostic_workflow_repository", workflows)
    monkeypatch.setattr(diagnostic_service, "_event", lambda *args, **kwargs: None)
    return attempts, workflows


def test_two_failures_open_one_case_and_bind_tasks(monkeypatch, tmp_path):
    attempts, workflows = _repositories(monkeypatch, tmp_path)
    course = project_learning_objective_bindings(_course())
    task = project_assessment_task(course["learning_assets"]["questions"][0], purpose="course_practice", source="course_asset")
    first = _attempt(attempts, attempt_id="a1", result=_result(False))
    assert consider_course_failure(course, user_id="u1", attempt=first, task=task) is None

    second = _attempt(attempts, attempt_id="a2", result=_result(False))
    case = consider_course_failure(course, user_id="u1", attempt=second, task=task)
    duplicate = consider_course_failure(course, user_id="u1", attempt=second, task=task)

    assert case["diagnostic_case_id"] == duplicate["diagnostic_case_id"]
    assert len(workflows.list_cases("u1", "c1")) == 1
    assert case["diagnostic_tasks"][0]["diagnostic_case_id"] == case["diagnostic_case_id"]
    assert case["hypotheses"][0]["status"] == "testing"

    projection = advance_workflow_after_grade(course, user_id="u1", attempt=second, task=task)
    assert projection["phase"] == "diagnostic"
    assert projection["current_task"]["task_purpose"] == "diagnostic_probe"


def test_confirm_remediate_and_close_only_after_independent_validation(monkeypatch, tmp_path):
    attempts, workflows = _repositories(monkeypatch, tmp_path)
    course = _course()
    formal = project_assessment_task(course["learning_assets"]["questions"][0], purpose="course_practice", source="course_asset")
    _attempt(attempts, attempt_id="a1", result=_result(False))
    failed = _attempt(attempts, attempt_id="a2", result=_result(False))
    case = consider_course_failure(course, user_id="u1", attempt=failed, task=formal)

    probe = case["diagnostic_tasks"][0]
    probe_attempt = _attempt(
        attempts, attempt_id="probe1", result=_result(False), purpose="diagnostic_probe",
        task_revision_id=probe["task_revision_id"], diagnostic_case_id=case["diagnostic_case_id"],
    )
    after_probe = advance_workflow_after_grade(course, user_id="u1", attempt=probe_attempt, task=probe)
    assert after_probe["case"]["status"] == "remediating"
    session = after_probe["session"]
    assert session["unit"]["remediation_objective"] == "只修复大小与方向的判断"

    guided = session["tasks"][0]
    guided_attempt = _attempt(
        attempts, attempt_id="guided1", result=_result(True, support=1), purpose="remediation_guided",
        task_revision_id=guided["task_revision_id"], diagnostic_case_id=case["diagnostic_case_id"],
        remediation_session_id=session["remediation_session_id"],
    )
    after_guided = advance_workflow_after_grade(course, user_id="u1", attempt=guided_attempt, task=guided)
    assert after_guided["phase"] == "validation"

    validation = next(item for item in session["tasks"] if item["task_purpose"] == "remediation_validation")
    supported = _attempt(
        attempts, attempt_id="validation-supported", result=_result(True, support=1),
        purpose="remediation_validation", task_revision_id=validation["task_revision_id"],
        diagnostic_case_id=case["diagnostic_case_id"], remediation_session_id=session["remediation_session_id"],
    )
    inconclusive = advance_workflow_after_grade(course, user_id="u1", attempt=supported, task=validation)
    assert inconclusive["case"]["status"] != "resolved"
    assert inconclusive["session"]["current_task_revision_id"] != validation["task_revision_id"]

    next_validation = inconclusive["current_task"]
    independent = _attempt(
        attempts, attempt_id="validation-independent", result=_result(True),
        purpose="remediation_validation", task_revision_id=next_validation["task_revision_id"],
        diagnostic_case_id=case["diagnostic_case_id"], remediation_session_id=session["remediation_session_id"],
    )
    resolved = advance_workflow_after_grade(course, user_id="u1", attempt=independent, task=next_validation)
    assert resolved["phase"] == "resolved"
    assert resolved["case"]["status"] == "resolved"
    assert resolved["current_task"] is None


def test_course_version_change_marks_active_workflow_stale(monkeypatch, tmp_path):
    attempts, workflows = _repositories(monkeypatch, tmp_path)
    course = _course()
    formal = project_assessment_task(course["learning_assets"]["questions"][0], purpose="course_practice", source="course_asset")
    _attempt(attempts, attempt_id="a1", result=_result(False))
    failed = _attempt(attempts, attempt_id="a2", result=_result(False))
    case = consider_course_failure(course, user_id="u1", attempt=failed, task=formal)

    changed = invalidate_stale_workflows(_course("cv2"), user_id="u1")
    stored = workflows.get_case("u1", "c1", case["diagnostic_case_id"])
    assert changed == 1
    assert stored["status"] == "stale"
    assert workflow_view("u1", "c1")["phase"] == "practice"


def test_low_confidence_or_supported_failures_do_not_trigger(monkeypatch, tmp_path):
    attempts, _ = _repositories(monkeypatch, tmp_path)
    course = _course()
    formal = project_assessment_task(course["learning_assets"]["questions"][0], purpose="course_practice", source="course_asset")
    weak = _result(False, support=2)
    _attempt(attempts, attempt_id="a1", result=deepcopy(weak))
    second = _attempt(attempts, attempt_id="a2", result=deepcopy(weak))
    assert consider_course_failure(course, user_id="u1", attempt=second, task=formal) is None


def test_diagnostic_task_uses_same_practice_attempt_api(monkeypatch, tmp_path):
    attempts, workflows = _repositories(monkeypatch, tmp_path)
    course = _course()
    task = project_assessment_task(
        course["learning_assets"]["diagnostic_templates"][0],
        purpose="diagnostic_probe",
        source="diagnostic_workflow",
    )
    case, _ = workflows.create_case_once("u1", "c1", {
        "course_version_id": "cv1",
        "node_id": "n1",
        "objective_id": task["objective_id"],
        "objective_revision_id": task["objective_revision_id"],
        "diagnostic_tasks": [task],
        "current_task_revision_id": task["task_revision_id"],
        "hypotheses": [],
    })

    async def fake_course(_course_id):
        return course

    monkeypatch.setattr(practice_router, "get_course_or_404", fake_course)
    monkeypatch.setattr(practice_router, "practice_attempt_repository", attempts)
    monkeypatch.setattr(practice_router, "diagnostic_workflow_repository", workflows)
    monkeypatch.setattr(diagnostics_router, "get_course_or_404", fake_course)
    monkeypatch.setattr(diagnostics_router, "diagnostic_workflow_repository", workflows)
    monkeypatch.setattr(learning_events, "storage", MemoryStorage())
    app = FastAPI()
    app.include_router(practice_router.router, prefix="/api")
    app.include_router(diagnostics_router.router, prefix="/api")
    client = TestClient(app, headers={"X-User-Id": "u1"})

    active = client.get("/api/courses/c1/diagnostics/active?node_id=n1")
    created = client.post("/api/courses/c1/practice/attempts", json={
        "task_revision_id": task["task_revision_id"],
    })

    assert active.status_code == 200
    assert active.json()["phase"] == "diagnostic"
    assert created.status_code == 200
    assert created.json()["attempt"]["task_purpose"] == "diagnostic_probe"
    assert created.json()["attempt"]["diagnostic_case_id"] == case["diagnostic_case_id"]
    assert created.json()["attempt"]["skill_unit_ids"] == ["skill.vector.describe"]
    assert created.json()["attempt"]["mistake_point_ids"] == ["mistake.vector.direction"]
