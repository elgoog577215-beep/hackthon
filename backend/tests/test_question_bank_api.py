import asyncio
from copy import deepcopy
from threading import Thread

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from course_versions import CourseVersionRepository
from learning_asset_storage import LearningAssetRepository
from question_bank import QuestionBankRepository, build_question_bank
from question_bank_jobs import QuestionBankRebuildJobRepository
from routers import question_bank


class MemoryCourseStorage:
    def __init__(self, course):
        self.course = deepcopy(course)
        self.save_count = 0

    async def save_course(self, course_id, course):
        assert course_id == course["course_id"]
        self.course = deepcopy(course)
        self.save_count += 1


class BlockingRebuildExecutor:
    """Complete the durable job before the test request returns."""

    def submit(
        self,
        *,
        job_id,
        course_id,
        payload,
        course,
    ):
        worker = Thread(
            target=asyncio.run,
            args=(question_bank._run_rebuild_job(
                job_id=job_id,
                course_id=course_id,
                payload=payload,
                course=deepcopy(course),
            ),),
        )
        worker.start()
        worker.join()


def _course():
    return {
        "course_id": "course-api",
        "course_name": "概率论",
        "course_purpose": "systematic",
        "difficulty": "intermediate",
        "generation_request": {"web_question_enrichment": {"enabled": False}},
        "material_bindings": [],
        "nodes": [{
            "node_id": "node-1",
            "node_level": 2,
            "node_name": "条件概率",
            "learning_objective": "能计算并解释条件概率",
            "key_points": ["条件概率", "样本空间"],
            "assessment": ["计算给定事件的条件概率并检查范围"],
            "grounding_contract": {"question_evidence_ids": []},
            "difficulty_contract": {"target_level": "intermediate"},
        }],
    }


def _client(monkeypatch, tmp_path):
    repository = QuestionBankRepository(tmp_path / "question-banks")
    asset_repository = LearningAssetRepository(tmp_path / "learning-assets")
    version_repository = CourseVersionRepository(tmp_path / "course-versions")
    job_repository = QuestionBankRebuildJobRepository(
        tmp_path / "question-bank-rebuilds"
    )
    course_storage = MemoryCourseStorage(_course())

    async def get_course(course_id: str):
        course = deepcopy(course_storage.course)
        course["course_id"] = course_id
        return course

    monkeypatch.setattr(question_bank, "question_bank_repository", repository)
    monkeypatch.setattr(
        question_bank,
        "learning_asset_repository",
        asset_repository,
        raising=False,
    )
    monkeypatch.setattr(
        question_bank,
        "course_version_repository",
        version_repository,
        raising=False,
    )
    monkeypatch.setattr(
        question_bank,
        "question_bank_rebuild_job_repository",
        job_repository,
    )
    monkeypatch.setattr(
        question_bank,
        "question_bank_rebuild_executor",
        BlockingRebuildExecutor(),
    )
    monkeypatch.setattr(question_bank, "storage", course_storage, raising=False)
    monkeypatch.setattr(question_bank, "get_course_or_404", get_course)
    repository.asset_repository = asset_repository
    repository.version_repository = version_repository
    repository.course_storage = course_storage
    app = FastAPI()
    app.include_router(question_bank.router, prefix="/api")
    return TestClient(app), repository


def _rebuild(client, request_id):
    created = client.post(
        "/api/courses/course-api/question-bank/rebuild",
        headers={"X-User-Id": "teacher-1"},
        json={"request_id": request_id},
    )
    assert created.status_code == 202
    status = client.get(
        created.json()["status_url"],
        headers={"X-User-Id": "teacher-1"},
    )
    assert status.status_code == 200
    job = status.json()
    assert job["status"] in {"completed", "waiting_review"}
    assert job["result"]
    return created.json(), job


def test_question_bank_list_review_revision_and_conflict(monkeypatch, tmp_path):
    client, repository = _client(monkeypatch, tmp_path)
    stored = repository.save_bundle("course-api", build_question_bank(_course()))
    final = next(item for item in stored["items"] if item["review_required"])

    listed = client.get(
        "/api/courses/course-api/question-bank",
        headers={"X-User-Id": "teacher-1"},
        params={"lifecycle_status": "needs_review"},
    )
    assert listed.status_code == 200
    assert listed.json()["review_queue"]["blocking_count"] >= 1

    stale = client.post(
        f"/api/courses/course-api/question-bank/items/{final['revision_id']}/reviews",
        headers={"X-User-Id": "teacher-1"},
        json={
            "decision": "approved",
            "expected_bundle_revision_id": "stale",
        },
    )
    assert stale.status_code == 409

    approved = client.post(
        f"/api/courses/course-api/question-bank/items/{final['revision_id']}/reviews",
        headers={"X-User-Id": "teacher-1"},
        json={
            "decision": "approved",
            "note": "量规清晰",
            "expected_bundle_revision_id": stored["bundle_revision_id"],
        },
    )
    assert approved.status_code == 200
    assert approved.json()["item"]["lifecycle_status"] == "approved"
    approved_bundle_revision = approved.json()["bundle_revision_id"]

    revised = client.post(
        f"/api/courses/course-api/question-bank/items/{final['revision_id']}/revisions",
        headers={"X-User-Id": "teacher-1"},
        json={
            "patch": {"prompt": "给定两个条件事件，完成计算、解释与结果检查。"},
            "expected_bundle_revision_id": approved_bundle_revision,
        },
    )
    assert revised.status_code == 201
    assert revised.json()["item"]["parent_revision_id"] == final["revision_id"]
    assert revised.json()["item"]["lifecycle_status"] == "needs_review"

    oversized = client.post(
        f"/api/courses/course-api/question-bank/items/{revised.json()['item']['revision_id']}/revisions",
        headers={"X-User-Id": "teacher-1"},
        json={"patch": {"prompt": "x" * 12_001}},
    )
    assert oversized.status_code == 422

    leaked_answer = client.post(
        f"/api/courses/course-api/question-bank/items/{revised.json()['item']['revision_id']}/revisions",
        headers={"X-User-Id": "teacher-1"},
        json={"patch": {"answer_spec": {"correct_answer": "SECRET"}}},
    )
    assert leaked_answer.status_code == 422
    assert "private solution contract" in leaked_answer.json()["detail"]


def test_question_bank_review_rejects_failed_quality_item(monkeypatch, tmp_path):
    client, repository = _client(monkeypatch, tmp_path)
    bundle = build_question_bank(_course())
    pending = next(item for item in bundle["items"] if item["review_required"])
    pending["quality_report"] = {
        "schema_version": "question_item_quality_v1",
        "passed": False,
        "status": "failed",
        "issues": [{"code": "question:answer_not_executable", "severity": "critical"}],
    }
    stored = repository.save_bundle("course-api", bundle)

    response = client.post(
        f"/api/courses/course-api/question-bank/items/{pending['revision_id']}/reviews",
        headers={"X-User-Id": "teacher-1"},
        json={
            "decision": "approved",
            "expected_bundle_revision_id": stored["bundle_revision_id"],
        },
    )

    assert response.status_code == 422
    assert "failed quality" in response.json()["detail"]


def test_question_bank_rebuild_is_idempotent_and_returns_coverage(monkeypatch, tmp_path):
    client, repository = _client(monkeypatch, tmp_path)

    first, first_job = _rebuild(client, "request-123")
    second = client.post(
        "/api/courses/course-api/question-bank/rebuild",
        headers={"X-User-Id": "teacher-1"},
        json={"request_id": "request-123"},
    )

    result = first_job["result"]
    assert first_job["status"] == "waiting_review"
    assert result["coverage"]["coverage_ratio"] == 0
    assert second.status_code == 202
    assert second.json()["job_id"] == first["job_id"]
    assert second.json()["deduplicated"] is True
    assert result["learning_asset_bundle_revision_id"]

    active_assets = repository.asset_repository.load_bundle("course-api")
    assert active_assets is not None
    assert active_assets["bundle_revision_id"] == result[
        "learning_asset_bundle_revision_id"
    ]
    assert all(
        "用自己的话说明" not in item["prompt"]
        for item in active_assets["assets"]["questions"]
    )

    saved_course = repository.course_storage.course
    assert saved_course["question_bank_bundle_revision_id"] == result[
        "bundle_revision_id"
    ]
    assert saved_course["learning_asset_bundle_revision_id"] == result[
        "learning_asset_bundle_revision_id"
    ]
    assert saved_course["current_course_version_id"]
    assert (
        repository.version_repository.current_version_id("course-api")
        == saved_course["current_course_version_id"]
    )
    assert repository.course_storage.save_count == 1


def test_question_bank_rebuild_preserves_teacher_review_decisions(monkeypatch, tmp_path):
    client, repository = _client(monkeypatch, tmp_path)
    stored = repository.save_bundle("course-api", build_question_bank(_course()))
    pending = next(item for item in stored["items"] if item["review_required"])

    approved = client.post(
        f"/api/courses/course-api/question-bank/items/{pending['revision_id']}/reviews",
        headers={"X-User-Id": "teacher-1"},
        json={
            "decision": "approved",
            "expected_bundle_revision_id": stored["bundle_revision_id"],
        },
    )
    assert approved.status_code == 200

    _, rebuilt = _rebuild(client, "request-preserve-review")
    assert rebuilt["result"]["bundle_revision_id"]
    latest = repository.load_bundle("course-api")
    preserved = next(
        item for item in latest["items"] if item["item_id"] == pending["item_id"]
    )
    assert preserved["lifecycle_status"] == "approved"
    assert preserved["review_history"]


def test_rebuild_overlays_bank_on_passing_legacy_assets_when_full_recompile_fails(
    monkeypatch,
    tmp_path,
):
    client, repository = _client(monkeypatch, tmp_path)
    legacy_assets = {
        "schema_version": "learning_assets_v2",
        "plan": {"enabled_asset_types": ["questions"]},
        "assets": {
            "questions": [{
                "revision_id": "legacy-question-1",
                "node_id": "node-1",
                "practice_level": "concept_check",
                "prompt": (
                    "用自己的话说明“条件概率”的含义，并指出它成立或适用的关键条件。"
                ),
                "answer_spec": {
                    "criteria": ["说明定义", "说明关键条件"],
                },
            }],
            "final_assessment": [],
        },
        "quality_report": {
            "schema_version": "asset_quality_v1",
            "passed": True,
            "blocking_issues": [],
            "warnings": [],
            "gates": [],
        },
    }
    stored_legacy = repository.asset_repository.save_bundle(
        "course-api",
        legacy_assets,
    )
    repository.course_storage.course.update({
        "learning_assets": deepcopy(legacy_assets["assets"]),
        "learning_asset_plan": deepcopy(legacy_assets["plan"]),
        "learning_asset_bundle_revision_id": stored_legacy[
            "bundle_revision_id"
        ],
        "asset_quality_report": deepcopy(
            legacy_assets["quality_report"]
        ),
    })

    _, response = _rebuild(client, "request-legacy-overlay")
    result = response["result"]

    assert result["publication_mode"] == (
        "question_bank_waiting_review_overlay"
    )
    active = repository.asset_repository.load_bundle("course-api")
    assert active["quality_report"]["passed"] is True
    assert active["publication_mode"] == (
        "question_bank_waiting_review_overlay"
    )
    binding = active["assets"]["question_bank_publications"][0]
    assert (
        binding["question_bank_bundle_revision_id"]
        == result["bundle_revision_id"]
    )
    assert binding["quality_report"]["passed"] is False
    assert active["bundle_revision_id"] != stored_legacy[
        "bundle_revision_id"
    ]


@pytest.mark.parametrize("compiled_passed", [False, True])
def test_first_rebuild_keeps_unapproved_question_bank_out_of_learning_tasks(
    compiled_passed,
):
    compiled_assets = {
        "quality_report": {
            "schema_version": "asset_quality_v1",
            "passed": compiled_passed,
        },
        "assets": {"questions": []},
    }
    partial_bank = {
        "course_id": "course-api",
        "bundle_revision_id": "qbb-partial",
        "coverage": {"coverage_ratio": 0.5},
        "items": [{
            "assessment_role": "practice",
            "lifecycle_status": "needs_review",
            "quality_report": {"passed": False},
        }],
    }

    selected = question_bank._select_publishable_asset_bundle(
        None,
        compiled_assets,
        partial_bank,
    )

    assert selected["publication_mode"] == "question_bank_waiting_review"
    assert selected["quality_report"]["passed"] is True
    assert selected["quality_report"]["scope"] == (
        "question_bank_waiting_review"
    )
    assert selected["assets"]["questions"] == []


def test_safe_approved_subset_builds_explicit_partial_overlay():
    formal_task = {
        "revision_id": "task-approved",
        "node_id": "node-approved",
        "practice_level": "concept_check",
        "prompt": "给定可运行代码，判断实际输出并说明规则。",
    }
    compiled_assets = {
        "plan": {"enabled_asset_types": ["questions"]},
        "quality_report": {"passed": False},
        "assets": {"questions": []},
    }
    partial_bank = {
        "course_id": "course-api",
        "bundle_revision_id": "qbb-partial-safe",
        "coverage": {"coverage_ratio": 0.5},
        "items": [{
            "assessment_role": "practice",
            "lifecycle_status": "approved",
            "quality_report": {"passed": True},
            "formal_task_revision_id": "task-approved",
            "formal_task": formal_task,
        }],
    }

    selected = question_bank._select_publishable_asset_bundle(
        None,
        compiled_assets,
        partial_bank,
    )

    assert selected["publication_mode"] == "question_bank_partial"
    assert selected["quality_report"]["passed"] is True
    assert selected["quality_report"]["scope"] == "approved_question_subset"
    assert selected["question_bank_publication_quality"][
        "coverage_complete"
    ] is False
    assert selected["assets"]["questions"] == [formal_task]
