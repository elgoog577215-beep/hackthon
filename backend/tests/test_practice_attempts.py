from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

import learning_events
from learning_progress import build_learning_progress, project_learning_objective_bindings
from practice_attempts import AttemptConflict, InvalidAttemptTransition, PracticeAttemptRepository
from practice_grading import PracticeGrader
from practice_contracts import enrich_question_contract
from question_bank import build_question_bank
from routers import practice as practice_router


class MemoryStorage:
    def __init__(self):
        self.data = {}

    def load_data(self, filename):
        return deepcopy(self.data.get(filename, []))

    def save_data(self, filename, value):
        self.data[filename] = deepcopy(value)


def _course():
    question = {
        "asset_id": "q1",
        "revision_id": "qr1",
        "node_id": "n1",
        "objective_id": "lo_placeholder",
        "objective_revision_id": "lor_placeholder",
        "question_type": "short_answer",
        "prompt": "解释向量的两个基本属性。",
        "answer_spec": {
            "type": "exact",
            "correct_answer": "大小和方向",
            "criteria": ["说明大小", "说明方向"],
            "pass_score": 70,
        },
    }
    criterion = {
        "criterion_id": "mc1",
        "revision_id": "mcr1",
        "node_id": "n1",
        "observable_performance": "能够说明向量的大小与方向",
        "assessment_bindings": ["qr1"],
    }
    return {
        "course_id": "c1",
        "course_name": "线性代数",
        "current_course_version_id": "cv1",
        "nodes": [{
            "node_id": "n1",
            "node_level": 2,
            "node_name": "向量",
            "learning_objective": "能够解释向量",
            "node_content": "向量具有大小与方向。",
        }],
        "learning_assets": {
            "questions": [question],
            "mastery_criteria": [criterion],
            "checklist": [],
            "misconceptions": [],
            "final_assessment": [],
        },
    }


def _payload(**extra):
    return {
        "question_revision_id": "qr1",
        "course_version_id": "cv1",
        "node_id": "n1",
        "objective_id": "lo1",
        "objective_revision_id": "lor1",
        "criterion_id": "mc1",
        "criterion_revision_id": "mcr1",
        "practice_level": "mastery_check",
        **extra,
    }


def test_solution_payload_exposes_steps_structured_answer_and_checks():
    payload = practice_router._solution_payload({
        "answer_spec": {
            "criteria": ["旋转判断正确"],
            "canonical_answer": {
                "preorder": [30, 20, 10, 25, 40, 50],
                "rotations": ["在30执行LL右旋", "在20执行RR左旋"],
            },
            "solution_spec": {
                "schema_version": "solution_spec_v1",
                "summary": "逐次插入并在首次失衡祖先处旋转。",
                "steps": ["插入10后在30执行LL右旋", "插入50后在20执行RR左旋"],
                "final_answer": {
                    "preorder": [30, 20, 10, 25, 40, 50],
                },
                "checks": ["中序严格递增", "所有平衡因子绝对值不超过1"],
                "representation": {
                    "kind": "tree",
                    "content": "    30\n   /  \\\n 20    40",
                },
            },
        },
        "result_checks": ["最终高度正确"],
    })

    assert payload["schema_version"] == "solution_spec_v1"
    assert payload["steps"][0].startswith("插入10")
    assert payload["final_answer"]["preorder"] == [30, 20, 10, 25, 40, 50]
    assert payload["checks"] == ["中序严格递增", "所有平衡因子绝对值不超过1"]
    assert payload["representation"]["kind"] == "tree"


def test_practice_list_does_not_expose_answers_or_frozen_hint_contents(
    monkeypatch,
):
    course = _course()
    question = course["learning_assets"]["questions"][0]
    question["answer_spec"]["canonical_answer"] = {
        "preorder": [30, 20, 10],
    }
    question["answer_spec"]["solution_spec"] = {
        "schema_version": "solution_spec_v1",
        "steps": ["标准解题步骤"],
        "final_answer": {"preorder": [30, 20, 10]},
        "checks": ["中序递增"],
    }
    question["hint_contract"] = {
        "levels": [
            {"level": 1, "content": "只应通过提示接口返回"},
        ],
    }
    question["question_spec"] = {
        "answer_spec": deepcopy(question["answer_spec"]),
        "hint_contract": deepcopy(question["hint_contract"]),
    }

    async def fake_course(_course_id):
        return deepcopy(course)

    monkeypatch.setattr(practice_router, "get_course_or_404", fake_course)
    app = FastAPI()
    app.include_router(practice_router.router, prefix="/api")
    client = TestClient(app, headers={"X-User-Id": "u1"})

    response = client.get(
        "/api/courses/c1/practice",
        params={"node_id": "n1", "scope": "node"},
    )

    assert response.status_code == 200
    projected = response.json()["questions"][0]
    assert projected["prompt"] == question["prompt"]
    assert "answer_spec" not in projected
    assert "hint_contract" not in projected
    assert "question_spec" not in projected


def test_attempt_repository_preserves_retries_and_rejects_stale_drafts(tmp_path):
    repository = PracticeAttemptRepository(tmp_path)
    first, created = repository.create_once("u1", "c1", _payload(attempt_id="a1"))
    assert created is True
    saved = repository.update_draft(
        "u1", "c1", "a1", expected_revision=1, answer_payload={"text": "草稿"}, active_seconds=4
    )
    assert saved["revision"] == 2
    with pytest.raises(AttemptConflict):
        repository.update_draft(
            "u1", "c1", "a1", expected_revision=1, answer_payload={"text": "旧设备覆盖"}
        )

    submitted, changed = repository.submit(
        "u1",
        "c1",
        "a1",
        expected_revision=2,
        request_id="request-0001",
        answer_payload={"text": "大小和方向"},
        active_seconds=8,
    )
    assert changed is True
    graded = repository.apply_grade(
        "u1", "c1", "a1", expected_revision=submitted["revision"], result={"status": "graded", "passed": True}
    )
    assert graded["status"] == "graded"
    with pytest.raises(InvalidAttemptTransition):
        repository.update_draft(
            "u1", "c1", "a1", expected_revision=graded["revision"], answer_payload={"text": "覆盖历史"}
        )

    retry, retry_created = repository.create_once("u1", "c1", _payload(resume=False))
    assert retry_created is True
    assert retry["attempt_id"] != first["attempt_id"]
    assert retry["attempt_number"] == 2
    assert len(repository.list("u1", "c1")) == 2
    assert repository.list("u2", "c1") == []


def test_hint_levels_are_ordered_and_irreversible(tmp_path):
    repository = PracticeAttemptRepository(tmp_path)
    attempt, _ = repository.create_once("u1", "c1", _payload())
    with pytest.raises(InvalidAttemptTransition):
        repository.reveal_hint(
            "u1", "c1", attempt["attempt_id"], expected_revision=1, level=2
        )
    first, created = repository.reveal_hint(
        "u1", "c1", attempt["attempt_id"], expected_revision=1, level=1
    )
    assert created is True
    duplicate, duplicate_created = repository.reveal_hint(
        "u1", "c1", attempt["attempt_id"], expected_revision=first["revision"], level=1
    )
    assert duplicate_created is False
    assert duplicate["revealed_hint_levels"] == [1]


def test_abandoned_attempt_is_preserved_and_cannot_be_edited(tmp_path):
    repository = PracticeAttemptRepository(tmp_path)
    attempt, _ = repository.create_once("u1", "c1", _payload())
    abandoned = repository.abandon(
        "u1", "c1", attempt["attempt_id"], expected_revision=attempt["revision"]
    )
    assert abandoned["status"] == "abandoned"
    assert repository.list("u1", "c1")[0]["attempt_id"] == attempt["attempt_id"]
    with pytest.raises(InvalidAttemptTransition):
        repository.update_draft(
            "u1", "c1", attempt["attempt_id"],
            expected_revision=abandoned["revision"], answer_payload={"text": "覆盖"},
        )


def test_concurrent_attempt_creation_does_not_lose_records(tmp_path):
    repository = PracticeAttemptRepository(tmp_path)

    def create(index: int):
        return repository.create_once(
            "u1",
            "c1",
            _payload(attempt_id=f"attempt-{index}", resume=False),
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(create, range(40)))

    assert len(repository.list("u1", "c1")) == 40


@pytest.mark.asyncio
async def test_deterministic_grading_tracks_support_strength():
    grader = PracticeGrader()
    question = _course()["learning_assets"]["questions"][0]
    result = await grader.grade(question, {
        "status": "submitted",
        "submitted_answer_payload": {"text": "大小和方向"},
        "revealed_hint_levels": [1],
        "ai_support_level": 0,
        "solution_revealed": False,
    })
    assert result["passed"] is True
    assert result["evidence_strength"] == "lightly_supported"
    assert result["mastery_eligible"] is True


@pytest.mark.asyncio
async def test_concept_check_never_becomes_mastery_evidence():
    grader = PracticeGrader()
    question = _course()["learning_assets"]["questions"][0]
    question["practice_level"] = "concept_check"
    question["validation_policy"] = {
        "mastery_eligible": False,
        "max_support_level_for_mastery": 1,
    }
    result = await grader.grade(question, {
        "status": "submitted",
        "submitted_answer_payload": {"text": "大小和方向"},
        "revealed_hint_levels": [],
    })
    assert result["passed"] is True
    assert result["mastery_eligible"] is False


@pytest.mark.asyncio
async def test_open_rubric_without_provider_waits_for_review():
    grader = PracticeGrader()
    grader.client = None
    question = _course()["learning_assets"]["questions"][0]
    question["answer_spec"] = {"type": "rubric", "criteria": ["说明概念"], "pass_score": 70}
    result = await grader.grade(question, {
        "status": "submitted",
        "submitted_answer_payload": {"text": "这是一个开放回答"},
        "revealed_hint_levels": [],
    })
    assert result["status"] == "pending_review"
    assert result["score"] is None
    assert result["mastery_eligible"] is False


def test_practice_api_resumes_submits_idempotently_and_projects_mastery(monkeypatch, tmp_path):
    repository = PracticeAttemptRepository(tmp_path)
    storage = MemoryStorage()
    monkeypatch.setattr(practice_router, "practice_attempt_repository", repository)
    monkeypatch.setattr(learning_events, "storage", storage)

    async def fake_course(_course_id):
        return _course()

    monkeypatch.setattr(practice_router, "get_course_or_404", fake_course)
    app = FastAPI()
    app.include_router(practice_router.router, prefix="/api")
    client = TestClient(app, headers={"X-User-Id": "u1"})

    first = client.post("/api/courses/c1/practice/attempts", json={"question_revision_id": "qr1"})
    second = client.post("/api/courses/c1/practice/attempts", json={"question_revision_id": "qr1"})
    assert first.status_code == 200
    assert second.json()["status"] == "resumed"
    attempt = first.json()["attempt"]

    saved = client.patch(
        f"/api/courses/c1/practice/attempts/{attempt['attempt_id']}/draft",
        json={"expected_revision": 1, "answer_payload": {"text": "大小和方向"}, "active_seconds": 12},
    )
    assert saved.status_code == 200
    submission = {
        "expected_revision": 2,
        "answer_payload": {"text": "大小和方向"},
        "active_seconds": 12,
        "request_id": "submit-0001",
    }
    submitted = client.post(
        f"/api/courses/c1/practice/attempts/{attempt['attempt_id']}/submit", json=submission
    )
    repeated = client.post(
        f"/api/courses/c1/practice/attempts/{attempt['attempt_id']}/submit", json=submission
    )
    assert submitted.status_code == 200
    assert submitted.json()["result"]["passed"] is True
    assert repeated.json()["status"] == "already_submitted"

    stored = repository.list("u1", "c1")
    course = project_learning_objective_bindings(_course())
    progress = build_learning_progress(
        course,
        user_id="u1",
        events=[],
        attempts=stored,
    )
    assert progress["nodes"][0]["mastery_status"] == "mastered"
    events = learning_events.load_learning_events(course_id="c1")
    assert [item["event_type"] for item in events] == [
        "practice_attempt_started",
        "practice_attempt_submitted",
        "practice_attempt_graded",
    ]
    assert all(item["attempt_id"] == attempt["attempt_id"] for item in events)


def test_targeted_retry_attempt_preserves_origin_and_intent(monkeypatch, tmp_path):
    repository = PracticeAttemptRepository(tmp_path)
    storage = MemoryStorage()
    monkeypatch.setattr(practice_router, "practice_attempt_repository", repository)
    monkeypatch.setattr(learning_events, "storage", storage)

    async def fake_course(_course_id):
        return _course()

    monkeypatch.setattr(practice_router, "get_course_or_404", fake_course)
    app = FastAPI()
    app.include_router(practice_router.router, prefix="/api")
    client = TestClient(app, headers={"X-User-Id": "u1"})
    origin, _ = repository.create_once("u1", "c1", _payload(attempt_id="failed-attempt-1"))
    submitted, _ = repository.submit(
        "u1",
        "c1",
        origin["attempt_id"],
        expected_revision=origin["revision"],
        request_id="failed-submit-1",
        answer_payload={"text": "错误答案"},
        active_seconds=5,
    )
    repository.apply_grade(
        "u1",
        "c1",
        origin["attempt_id"],
        expected_revision=submitted["revision"],
        result={"status": "graded", "passed": False, "mastery_eligible": False},
    )

    response = client.post("/api/courses/c1/practice/attempts", json={
        "task_revision_id": "qr1",
        "resume": False,
        "origin_attempt_id": "failed-attempt-1",
        "practice_intent": "targeted_retry",
    })

    assert response.status_code == 200
    attempt = response.json()["attempt"]
    assert attempt["origin_attempt_id"] == "failed-attempt-1"
    assert attempt["practice_intent"] == "targeted_retry"


def test_accepted_course_growth_validation_task_uses_formal_asset_repository(monkeypatch, tmp_path):
    repository = PracticeAttemptRepository(tmp_path)
    storage = MemoryStorage()
    monkeypatch.setattr(practice_router, "practice_attempt_repository", repository)
    monkeypatch.setattr(learning_events, "storage", storage)
    course = _course()
    course["course_document"] = {
        "blocks": [{
            "block_id": "growth-practice",
            "section_id": "n1",
            "status": "final",
            "payload": {
                "practice_task_id": "rvtr-growth-1",
                "course_evolution": {"change_set_id": "growth-plan-1"},
            },
        }],
    }
    validation_task = {
        "asset_id": "growth-validation-1",
        "revision_id": "rvtr-growth-1",
        "node_id": "n1",
        "objective_id": "lo-placeholder",
        "objective_revision_id": "lor-placeholder",
        "question_type": "short_answer",
        "prompt": "解释为什么 ABv 等于 A(Bv)，并判断哪一个变换先发生。",
        "answer_spec": {
            "type": "rubric",
            "criteria": ["说明 B 先作用", "解释复合顺序"],
            "pass_score": 70,
        },
        "practice_level": "remediation_validation",
        "quality_status": "passed",
        "status": "active",
        "validation_policy": {
            "mastery_eligible": True,
            "max_support_level_for_mastery": 0,
        },
    }
    monkeypatch.setattr(
        practice_router.learning_asset_repository,
        "load_bundle",
        lambda _course_id: {
            "assets": {
                **course["learning_assets"],
                "validation_questions": [validation_task],
            },
        },
    )

    async def fake_course(_course_id):
        return deepcopy(course)

    monkeypatch.setattr(practice_router, "get_course_or_404", fake_course)
    app = FastAPI()
    app.include_router(practice_router.router, prefix="/api")
    client = TestClient(app, headers={"X-User-Id": "u1"})

    practice = client.get("/api/courses/c1/practice", params={"node_id": "n1"})
    assert practice.status_code == 200
    assert "rvtr-growth-1" in {
        item.get("revision_id") or item.get("task_revision_id")
        for item in practice.json()["questions"]
    }

    created = client.post(
        "/api/courses/c1/practice/attempts",
        json={"task_revision_id": "rvtr-growth-1", "resume": False},
    )
    assert created.status_code == 200
    attempt = created.json()["attempt"]
    assert attempt["task_revision_id"] == "rvtr-growth-1"
    assert attempt["task_purpose"] == "course_practice"
    assert attempt["task_source"] == "course_evolution"


def test_legacy_practice_migration_is_idempotent_and_historical_only(monkeypatch, tmp_path):
    storage = MemoryStorage()
    monkeypatch.setattr(learning_events, "storage", storage)

    async def fake_course(_course_id):
        return _course()

    monkeypatch.setattr(practice_router, "get_course_or_404", fake_course)
    app = FastAPI()
    app.include_router(practice_router.router, prefix="/api")
    client = TestClient(app, headers={"X-User-Id": "u1"})
    payload = {
        "wrong_answers": [{"nodeId": "n1", "question": "旧题", "timestamp": 1}],
        "quiz_history": [{"nodeId": "n1", "totalQuestions": 3, "correctCount": 1, "timestamp": 2}],
    }
    first = client.post("/api/courses/c1/practice/migrate-legacy", json=payload)
    second = client.post("/api/courses/c1/practice/migrate-legacy", json=payload)
    assert first.json()["created"] == 2
    assert second.json()["created"] == 0
    events = learning_events.load_learning_events(course_id="c1")
    assert all((item.get("result") or {}).get("mastery_eligible") is False for item in events)


def test_active_question_bank_replaces_same_level_legacy_template(monkeypatch):
    course = _course()
    course["nodes"][0].update({
        "key_points": ["向量大小", "向量方向"],
        "assessment": ["根据给定坐标计算向量大小并检查结果"],
        "difficulty_contract": {"target_level": "intermediate"},
        "grounding_contract": {"question_evidence_ids": []},
    })
    stale = course["learning_assets"]["questions"][0]
    stale["practice_level"] = "concept_check"
    stale["prompt"] = (
        "用自己的话说明“向量”的含义，并指出它在本节中成立或适用的关键条件。"
    )
    bundle = build_question_bank(course)
    bank_revisions = {
        task["revision_id"]
        for item in bundle["items"]
        if item["assessment_role"] == "practice"
        and item["lifecycle_status"] == "approved"
        for task in [item["formal_task"]]
    }

    monkeypatch.setattr(
        practice_router.question_bank_repository,
        "load_bundle",
        lambda _course_id: deepcopy(bundle),
    )
    monkeypatch.setattr(
        practice_router.learning_asset_repository,
        "load_bundle",
        lambda _course_id: {"assets": deepcopy(course["learning_assets"])},
    )

    questions = practice_router._questions(course, node_id="n1", scope="node")
    returned_revisions = {
        item.get("revision_id") or item.get("task_revision_id")
        for item in questions
    }

    assert bank_revisions <= returned_revisions
    assert stale["revision_id"] not in returned_revisions
    assert all("用自己的话说明" not in item["prompt"] for item in questions)


def test_active_question_bank_never_falls_back_to_unreviewed_asset_questions(monkeypatch):
    course = _course()
    course["course_name"] = "未知跨领域课程"
    course["subject_pedagogy_profile"] = {
        "primary_mode": "general",
        "secondary_mode": None,
        "secondary_intensity": None,
        "confidence": "low",
        "evidence": [],
        "rationale": "需要教师确认学科适配器",
        "enabled_module_ids": [],
        "user_locked": True,
    }
    course["nodes"][0].update({
        "node_name": "未知主题X",
        "learning_objective": "完成尚未定义的跨领域任务",
        "key_points": ["未知能力A", "未知能力B"],
        "assessment": ["提交成果"],
        "difficulty_contract": {"target_level": "intermediate"},
        "grounding_contract": {"question_evidence_ids": []},
    })
    bundle = build_question_bank(course)
    assert all(
        item["lifecycle_status"] == "needs_review"
        for item in bundle["items"]
        if item["assessment_role"] == "practice"
    )

    monkeypatch.setattr(
        practice_router.question_bank_repository,
        "load_bundle",
        lambda _course_id: deepcopy(bundle),
    )
    monkeypatch.setattr(
        practice_router.learning_asset_repository,
        "load_bundle",
        lambda _course_id: {"assets": deepcopy(course["learning_assets"])},
    )

    assert practice_router._questions(course, node_id="n1", scope="node") == []


def test_active_question_bank_never_falls_back_to_legacy_final_assessment(monkeypatch):
    course = _course()
    course["nodes"][0].update({
        "key_points": ["向量大小", "向量方向"],
        "assessment": ["根据给定坐标计算向量大小并检查结果"],
        "difficulty_contract": {"target_level": "intermediate"},
        "grounding_contract": {"question_evidence_ids": []},
    })
    course["learning_assets"]["final_assessment"] = [{
        "revision_id": "legacy-final",
        "prompt": "旧版综合题",
        "review_status": None,
    }]
    bundle = build_question_bank(course)
    assert not any(
        item["lifecycle_status"] == "approved"
        for item in bundle["items"]
        if item["assessment_role"] in {"coverage_task", "cross_chapter_transfer"}
    )

    monkeypatch.setattr(
        practice_router.question_bank_repository,
        "load_bundle",
        lambda _course_id: deepcopy(bundle),
    )
    monkeypatch.setattr(
        practice_router.learning_asset_repository,
        "load_bundle",
        lambda _course_id: {"assets": deepcopy(course["learning_assets"])},
    )

    assert practice_router._questions(course, node_id=None, scope="final") == []


def test_legacy_server_records_are_not_implicitly_imported_for_current_user(monkeypatch, tmp_path):
    storage = MemoryStorage()
    storage.data["learning_records.json"] = {
        "c1": {
            "node_records": {
                "n1": {
                    "node_name": "向量",
                    "quiz_records": [{
                        "question_id": "old-q1",
                        "is_correct": False,
                        "timestamp": "2026-03-01T10:00:00",
                    }],
                },
            },
        },
    }
    repository = PracticeAttemptRepository(tmp_path)
    monkeypatch.setattr(practice_router, "storage", storage)
    monkeypatch.setattr(practice_router, "practice_attempt_repository", repository)
    monkeypatch.setattr(learning_events, "storage", storage)

    async def fake_course(_course_id):
        return _course()

    monkeypatch.setattr(practice_router, "get_course_or_404", fake_course)
    app = FastAPI()
    app.include_router(practice_router.router, prefix="/api")
    client = TestClient(app, headers={"X-User-Id": "u1"})

    assert client.get("/api/courses/c1/practice", params={"node_id": "n1"}).status_code == 200
    assert client.get("/api/courses/c1/practice", params={"node_id": "n1"}).status_code == 200
    events = learning_events.load_learning_events(course_id="c1")
    imported = [item for item in events if item["event_type"] == "legacy_practice_imported"]
    assert imported == []


def _submit_setup(monkeypatch, tmp_path):
    repository = PracticeAttemptRepository(tmp_path)
    storage = MemoryStorage()
    monkeypatch.setattr(practice_router, "practice_attempt_repository", repository)
    monkeypatch.setattr(learning_events, "storage", storage)

    async def fake_course(_course_id):
        return _course()

    monkeypatch.setattr(practice_router, "get_course_or_404", fake_course)
    app = FastAPI()
    app.include_router(practice_router.router, prefix="/api")
    client = TestClient(app, headers={"X-User-Id": "u1"})

    first = client.post("/api/courses/c1/practice/attempts", json={"question_revision_id": "qr1"})
    attempt = first.json()["attempt"]
    client.patch(
        f"/api/courses/c1/practice/attempts/{attempt['attempt_id']}/draft",
        json={"expected_revision": 1, "answer_payload": {"text": "大小和方向"}, "active_seconds": 12},
    )
    return repository, client, attempt


def test_submit_survives_single_workflow_conflict_by_retrying(monkeypatch, tmp_path):
    from diagnostic_workflows import WorkflowConflict

    repository, client, attempt = _submit_setup(monkeypatch, tmp_path)

    calls = {"n": 0}
    real_advance = practice_router.advance_workflow_after_grade

    def flaky_advance(course, *, user_id, attempt, task):
        calls["n"] += 1
        if calls["n"] == 1:
            raise WorkflowConflict(current={"revision": 99})
        return real_advance(course, user_id=user_id, attempt=attempt, task=task)

    monkeypatch.setattr(practice_router, "advance_workflow_after_grade", flaky_advance)

    submission = {
        "expected_revision": 2,
        "answer_payload": {"text": "大小和方向"},
        "active_seconds": 12,
        "request_id": "submit-conflict-0001",
    }
    response = client.post(
        f"/api/courses/c1/practice/attempts/{attempt['attempt_id']}/submit", json=submission
    )

    # No unhandled 500: the retry absorbed the single conflict.
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "graded"
    # The graded result itself is never lost, regardless of the workflow retry.
    assert body["result"]["passed"] is True
    assert calls["n"] == 2

    stored = next(item for item in repository.list("u1", "c1") if item["attempt_id"] == attempt["attempt_id"])
    assert stored["status"] == "graded"
    assert (stored.get("result") or {}).get("passed") is True


def test_submit_does_not_500_and_does_not_retry_forever_on_persistent_conflict(monkeypatch, tmp_path):
    from diagnostic_workflows import WorkflowConflict

    repository, client, attempt = _submit_setup(monkeypatch, tmp_path)

    calls = {"n": 0}

    def always_conflicting_advance(course, *, user_id, attempt, task):
        calls["n"] += 1
        raise WorkflowConflict(current={"revision": 99})

    monkeypatch.setattr(practice_router, "advance_workflow_after_grade", always_conflicting_advance)

    submission = {
        "expected_revision": 2,
        "answer_payload": {"text": "大小和方向"},
        "active_seconds": 12,
        "request_id": "submit-conflict-0002",
    }
    response = client.post(
        f"/api/courses/c1/practice/attempts/{attempt['attempt_id']}/submit", json=submission
    )

    # Even when the conflict persists past the retry, the endpoint must return a well-formed
    # response (not a bare 500) and must not retry indefinitely.
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "graded"
    assert body["result"]["passed"] is True
    assert calls["n"] == 2  # exactly one retry, never more

    stored = next(item for item in repository.list("u1", "c1") if item["attempt_id"] == attempt["attempt_id"])
    assert stored["status"] == "graded"
    assert (stored.get("result") or {}).get("passed") is True


def test_solution_reveal_requires_an_unseen_equivalent_validation(monkeypatch, tmp_path):
    repository = PracticeAttemptRepository(tmp_path)
    event_storage = MemoryStorage()
    course = _course()
    validation = enrich_question_contract({
        "asset_id": "validation-1",
        "revision_id": "vqr1",
        "node_id": "n1",
        "question_type": "short_answer",
        "prompt": "在一个未展示的新情境中说明向量的大小和方向，并检查结论。",
        "answer_spec": {
            "type": "exact",
            "correct_answer": "大小和方向",
            "criteria": ["说明大小", "说明方向", "检查结论"],
            "pass_score": 70,
        },
        "practice_level": "remediation_validation",
        "quality_status": "passed",
    }, practice_level="remediation_validation")
    course["learning_assets"]["validation_questions"] = [validation]

    class NoQuestionBank:
        @staticmethod
        def load_bundle(_course_id):
            return None

    async def fake_course(_course_id):
        return deepcopy(course)

    monkeypatch.setattr(practice_router, "practice_attempt_repository", repository)
    monkeypatch.setattr(practice_router, "get_course_or_404", fake_course)
    monkeypatch.setattr(practice_router, "question_bank_repository", NoQuestionBank())
    monkeypatch.setattr(learning_events, "storage", event_storage)
    app = FastAPI()
    app.include_router(practice_router.router, prefix="/api")
    client = TestClient(app, headers={"X-User-Id": "u1"})

    created = client.post(
        "/api/courses/c1/practice/attempts",
        json={"task_revision_id": "qr1"},
    ).json()["attempt"]
    submitted = client.post(
        f"/api/courses/c1/practice/attempts/{created['attempt_id']}/submit",
        json={
            "expected_revision": created["revision"],
            "answer_payload": {"text": "大小和方向"},
            "active_seconds": 10,
            "request_id": "submit-solution-1",
        },
    ).json()["attempt"]
    revealed = client.post(
        f"/api/courses/c1/practice/attempts/{created['attempt_id']}/solution",
        json={"expected_revision": submitted["revision"]},
    )

    assert revealed.status_code == 200
    requirement = revealed.json()["validation_requirement"]
    assert requirement["required"] is True
    assert requirement["task_revision_id"] == "vqr1"
    assert revealed.json()["attempt"]["solution_revealed"] is True

    validation_attempt = client.post(
        "/api/courses/c1/practice/attempts",
        json={
            "task_revision_id": "vqr1",
            "practice_intent": "unseen_validation",
            "origin_attempt_id": created["attempt_id"],
            "resume": False,
        },
    )
    assert validation_attempt.status_code == 200
    assert validation_attempt.json()["attempt"]["practice_intent"] == "unseen_validation"
    assert validation_attempt.json()["attempt"]["origin_attempt_id"] == created["attempt_id"]
