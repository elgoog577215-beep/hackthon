import asyncio
from copy import deepcopy
from threading import Thread

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from assessment_blueprint import (
    compile_course_assessment_blueprint,
    slot_for,
)
from assessment_contracts import (
    compile_assessment_objectives,
    compile_course_assessment_profile,
)
from assessment_generation import generate_universal_question_contract
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


class DeterministicAssessmentOrchestrator:
    """Keep API tests local and independent from provider availability."""

    def __init__(self, *, fail_node_id: str = ""):
        self.fail_node_id = fail_node_id
        self.requested_node_ids = []

    async def prepare_course(
        self,
        course_data,
        *,
        node_ids=None,
        on_progress=None,
        on_chapter_complete=None,
        reference_package=None,
    ):
        self.requested_node_ids.append(
            None if node_ids is None else list(node_ids)
        )
        prepared = deepcopy(course_data)
        profile = compile_course_assessment_profile(prepared)
        objectives = compile_assessment_objectives(prepared, profile)
        blueprint = compile_course_assessment_blueprint(
            prepared,
            profile=profile,
            objectives=objectives,
        )
        objective_by_node = {
            str(objective["node_id"]): objective
            for objective in objectives
        }
        requested = set(node_ids or []) if node_ids is not None else None
        contracts = {}
        audit_items = []
        completed = 0
        target_nodes = [
            node
            for node in prepared.get("nodes") or []
            if int(node.get("node_level") or 1) == 2
            and (
                requested is None
                or str(node.get("node_id") or "") in requested
            )
        ]
        total = len(target_nodes) * 3
        for node in target_nodes:
            node_id = str(node.get("node_id") or "")
            objective = objective_by_node[node_id]
            contracts[node_id] = {}
            node_audit_items = []
            for variant_index, practice_level in enumerate((
                "concept_check",
                "objective_practice",
                "mastery_check",
            )):
                slot = slot_for(
                    blueprint,
                    node_id=node_id,
                    practice_level=practice_level,
                )
                contract = generate_universal_question_contract(
                    prepared,
                    node,
                    profile=profile,
                    objective=objective,
                    practice_level=practice_level,
                    variant_index=variant_index,
                    slot=slot,
                    references=[],
                )
                mode = str(
                    (
                        contract["question_spec"].get(
                            "input_contract"
                        )
                        or {}
                    ).get("mode")
                    or ""
                )
                if mode == "choice":
                    contract["question_spec"]["options"] = [
                        {"id": "A", "text": "满足题面全部条件"},
                        {"id": "B", "text": "不满足题面关键条件"},
                    ]
                    canonical = "A"
                    option_analysis = [
                        {
                            "option_id": "A",
                            "is_correct": True,
                            "explanation": "该选项满足题面给出的全部条件。",
                        },
                        {
                            "option_id": "B",
                            "is_correct": False,
                            "explanation": "该选项遗漏题面的关键条件。",
                        },
                    ]
                elif mode == "numeric_unit":
                    canonical = {"value": 0.5, "unit": "1"}
                    option_analysis = []
                else:
                    canonical = {
                        "answer": "根据题面条件形成的完整示例结论",
                        "evidence": ["使用题面给出的关键条件"],
                        "result_check": "结论满足全部约束",
                    }
                    option_analysis = []
                contract["solution_envelope"][
                    "canonical_answer"
                ] = canonical
                contract["solution_envelope"]["worked_solution"] = {
                    "schema_version": "worked_solution_v1",
                    "summary": "先整理题面条件，再完成计算或推导并检查结论。",
                    "steps": [{
                        "title": "建立条件",
                        "explanation": "把题面给出的已知量和限制条件逐项对应到求解过程。",
                        "result": "得到可直接代入或推导的条件集合",
                    }, {
                        "title": "完成求解",
                        "explanation": "按照课程定义完成计算或论证，形成具体结论。",
                        "result": "得到最终参考答案",
                    }],
                    "final_answer": deepcopy(canonical),
                    "checks": ["逐项核对最终答案是否满足题面约束"],
                    "option_analysis": option_analysis,
                    "common_errors": ["遗漏题面条件，导致结论不可验证。"],
                }
                contract["review_required"] = False
                contract["risk_flags"] = []
                contract["question_spec"]["risk_contract"] = {
                    **(
                        contract["question_spec"].get(
                            "risk_contract"
                        )
                        or {}
                    ),
                    "risk_level": "low",
                    "requires_teacher_review": False,
                }
                contract["solution_validation"] = {
                    **(
                        contract.get("solution_validation")
                        or {}
                    ),
                    "passed": True,
                    "status": "passed",
                    "auto_publish_eligible": True,
                    "issues": [],
                }
                contract["quality_report"] = {
                    "schema_version": (
                        "question_quality_report_v2"
                    ),
                    "passed": True,
                    "status": "passed",
                    "score": 95,
                    "hard_gates": {},
                    "issues": [],
                    "decision": "publish",
                }
                if (
                    node_id == self.fail_node_id
                    and practice_level == "mastery_check"
                ):
                    contract["generation_status"] = "discarded"
                contracts[node_id][practice_level] = contract
                item_audit = {
                    "node_id": node_id,
                    "practice_level": practice_level,
                    "final_decision": (
                        "discard"
                        if contract.get("generation_status")
                        == "discarded"
                        else "publish"
                    ),
                    "attempts": [{
                        "attempt": 1,
                        "passed": (
                            contract.get("generation_status")
                            != "discarded"
                        ),
                    }],
                }
                audit_items.append(item_audit)
                node_audit_items.append(item_audit)
                completed += 1
                if on_progress is not None:
                    await on_progress({
                        "node_id": node_id,
                        "practice_level": practice_level,
                        "completed_items": completed,
                        "total_items": total,
                    })
            if on_chapter_complete is not None:
                chapter_passed = node_id != self.fail_node_id
                await on_chapter_complete({
                    "node_id": node_id,
                    "node_name": str(
                        node.get("node_name") or node_id
                    ),
                    "passed": chapter_passed,
                    "contracts": deepcopy(contracts[node_id]),
                    "audit_items": deepcopy(node_audit_items),
                    "completed_items": completed,
                    "total_items": total,
                    "error_code": (
                        ""
                        if chapter_passed
                        else "chapter_quality_failed"
                    ),
                    "error_message": (
                        ""
                        if chapter_passed
                        else "掌握检查未通过质量门"
                    ),
                })
        prepared["_assessment_generated_contracts"] = contracts
        prepared["_assessment_generation_audit"] = {
            "schema_version": "question_generation_audit_v2",
            "planned_item_count": total,
            "failure_count": sum(
                item["final_decision"] == "discard"
                for item in audit_items
            ),
            "items": audit_items,
        }
        prepared["_course_assessment_blueprint"] = blueprint
        prepared["_question_reference_package"] = (
            deepcopy(reference_package) if reference_package else {}
        )
        return prepared


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


def _two_chapter_course():
    course = _course()
    course["nodes"].append({
        "node_id": "node-2",
        "node_level": 2,
        "node_name": "贝叶斯公式",
        "learning_objective": "能使用贝叶斯公式更新条件概率",
        "key_points": ["贝叶斯公式", "全概率公式"],
        "assessment": ["根据先验概率和证据计算后验概率"],
        "grounding_contract": {"question_evidence_ids": []},
        "difficulty_contract": {"target_level": "intermediate"},
    })
    return course


def _client(
    monkeypatch,
    tmp_path,
    *,
    course=None,
    orchestrator=None,
):
    repository = QuestionBankRepository(tmp_path / "question-banks")
    asset_repository = LearningAssetRepository(tmp_path / "learning-assets")
    version_repository = CourseVersionRepository(tmp_path / "course-versions")
    job_repository = QuestionBankRebuildJobRepository(
        tmp_path / "question-bank-rebuilds"
    )
    course_storage = MemoryCourseStorage(course or _course())

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
    monkeypatch.setattr(
        question_bank,
        "assessment_generation_orchestrator",
        orchestrator or DeterministicAssessmentOrchestrator(),
    )
    monkeypatch.setattr(question_bank, "storage", course_storage, raising=False)
    monkeypatch.setattr(question_bank, "get_course_or_404", get_course)
    repository.asset_repository = asset_repository
    repository.version_repository = version_repository
    repository.course_storage = course_storage
    app = FastAPI()
    app.include_router(question_bank.router, prefix="/api")
    return TestClient(app), repository


def _rebuild(client, request_id, *, mode="incremental"):
    created = client.post(
        "/api/courses/course-api/question-bank/rebuild",
        headers={"X-User-Id": "teacher-1"},
        json={"request_id": request_id, "mode": mode},
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


def test_full_rebuild_publishes_each_chapter_atomically(
    monkeypatch,
    tmp_path,
):
    client, repository = _client(
        monkeypatch,
        tmp_path,
        course=_two_chapter_course(),
    )

    _, rebuilt = _rebuild(
        client,
        "request-chapter-publication",
        mode="full",
    )

    active = repository.load_bundle("course-api")
    assert active is not None
    active_nodes = {
        str(item.get("node_id") or "")
        for item in active["items"]
        if (
            item.get("assessment_role") == "practice"
            and item.get("lifecycle_status") != "retired"
        )
    }
    assert active_nodes == {"node-1", "node-2"}
    assert active["generation_audit"]["campaign_id"] == (
        "request-chapter-publication"
    )
    assert active["generation_audit"]["published_item_count"] == 6
    assert len(active["generation_audit"]["items"]) == 6
    checkpoint = (
        repository.course_storage.course[
            "question_bank_chapter_rebuild"
        ]
    )
    assert checkpoint["status"] == "completed"
    assert checkpoint["published_node_ids"] == [
        "node-1",
        "node-2",
    ]
    assert repository.course_storage.save_count == 2
    assert rebuilt["result"]["bundle_revision_id"] == (
        active["bundle_revision_id"]
    )


def test_node_rebuild_publishes_each_selected_chapter_atomically(
    monkeypatch,
    tmp_path,
):
    course = _two_chapter_course()
    client, repository = _client(
        monkeypatch,
        tmp_path,
        course=course,
    )
    repository.save_bundle(
        "course-api",
        build_question_bank(course),
    )

    created = client.post(
        "/api/courses/course-api/question-bank/rebuild",
        headers={"X-User-Id": "teacher-1"},
        json={
            "request_id": "request-node-publication",
            "scope": "nodes",
            "node_ids": ["node-1"],
            "mode": "incremental",
            "resume_existing": False,
        },
    )
    assert created.status_code == 202
    status = client.get(
        created.json()["status_url"],
        headers={"X-User-Id": "teacher-1"},
    )
    assert status.status_code == 200
    rebuilt = status.json()
    assert rebuilt["status"] == "completed"
    assert rebuilt["result"]["review_queue"][
        "blocking_count"
    ] == 0

    active = repository.load_bundle("course-api")
    assert active is not None
    assert active["generation_audit"]["campaign_id"] == (
        "request-node-publication"
    )
    assert active["generation_audit"]["planned_item_count"] == 3
    assert active["generation_audit"]["published_item_count"] == 3
    assert "question_bank_chapter_rebuild" not in (
        repository.course_storage.course
    )
    assert repository.course_storage.save_count == 1


def test_partial_v2_bank_is_detected_and_rebuild_continues_remaining_chapters(
    monkeypatch,
    tmp_path,
):
    orchestrator = DeterministicAssessmentOrchestrator()
    client, repository = _client(
        monkeypatch,
        tmp_path,
        course=_two_chapter_course(),
        orchestrator=orchestrator,
    )
    partial = build_question_bank(_two_chapter_course())
    for item in partial.get("items") or []:
        if (
            item.get("node_id") == "node-1"
            and item.get("assessment_role") == "practice"
        ):
            item["quality_report"] = {
                "schema_version": "question_quality_report_v2",
                "passed": True,
                "status": "passed",
                "score": 92,
            }
            item["lifecycle_status"] = "approved"
            item["review_status"] = "approved"
            item["generation_status"] = "published"
    repository.save_bundle("course-api", partial)

    listed = client.get(
        "/api/courses/course-api/question-bank",
        headers={"X-User-Id": "teacher-1"},
    )
    assert listed.status_code == 200
    progress = listed.json()["chapter_rebuild"]
    assert progress["status"] == "partial"
    assert progress["completed_chapters"] == 1
    assert progress["remaining_chapters"] == 1
    assert progress["can_resume"] is True
    assert progress["published_node_ids"] == ["node-1"]

    _, rebuilt = _rebuild(
        client,
        "request-continue-v2-migration",
        mode="full",
    )

    assert rebuilt["result"]["bundle_revision_id"]
    assert orchestrator.requested_node_ids == [["node-2"]]
    checkpoint = repository.course_storage.course[
        "question_bank_chapter_rebuild"
    ]
    assert checkpoint["status"] == "completed"
    assert checkpoint["published_node_ids"] == [
        "node-1",
        "node-2",
    ]


def test_full_rebuild_can_explicitly_ignore_partial_v2_progress(
    monkeypatch,
    tmp_path,
):
    orchestrator = DeterministicAssessmentOrchestrator()
    client, repository = _client(
        monkeypatch,
        tmp_path,
        course=_two_chapter_course(),
        orchestrator=orchestrator,
    )
    partial = build_question_bank(_two_chapter_course())
    for item in partial.get("items") or []:
        if (
            item.get("node_id") == "node-1"
            and item.get("assessment_role") == "practice"
        ):
            item["quality_report"] = {
                "schema_version": "question_quality_report_v2",
                "passed": True,
                "status": "passed",
                "score": 92,
            }
            item["lifecycle_status"] = "approved"
            item["generation_status"] = "published"
    repository.save_bundle("course-api", partial)

    created = client.post(
        "/api/courses/course-api/question-bank/rebuild",
        headers={"X-User-Id": "teacher-1"},
        json={
            "request_id": "request-force-full-v2-rebuild",
            "mode": "full",
            "resume_existing": False,
        },
    )

    assert created.status_code == 202
    assert orchestrator.requested_node_ids == [[
        "node-1",
        "node-2",
    ]]


def test_failed_chapter_keeps_old_questions_and_retry_resumes_remaining(
    monkeypatch,
    tmp_path,
):
    client, repository = _client(
        monkeypatch,
        tmp_path,
        course=_two_chapter_course(),
        orchestrator=DeterministicAssessmentOrchestrator(
            fail_node_id="node-2",
        ),
    )
    original = repository.save_bundle(
        "course-api",
        build_question_bank(_two_chapter_course()),
    )
    old_node_two_revisions = {
        str(item.get("revision_id") or "")
        for item in original["items"]
        if (
            item.get("node_id") == "node-2"
            and item.get("assessment_role") == "practice"
            and item.get("lifecycle_status") != "retired"
        )
    }

    created = client.post(
        "/api/courses/course-api/question-bank/rebuild",
        headers={"X-User-Id": "teacher-1"},
        json={
            "request_id": "request-chapter-partial-failure",
            "mode": "full",
        },
    )
    failed = client.get(
        created.json()["status_url"],
        headers={"X-User-Id": "teacher-1"},
    ).json()

    assert failed["status"] == "failed"
    assert failed["error"]["code"] == (
        "chapter_question_generation_failed"
    )
    partial = repository.load_bundle("course-api")
    assert partial is not None
    current_node_two_revisions = {
        str(item.get("revision_id") or "")
        for item in partial["items"]
        if (
            item.get("node_id") == "node-2"
            and item.get("assessment_role") == "practice"
            and item.get("lifecycle_status") != "retired"
        )
    }
    assert current_node_two_revisions == old_node_two_revisions
    assert repository.course_storage.course[
        "question_bank_chapter_rebuild"
    ]["published_node_ids"] == ["node-1"]
    resumable = client.get(
        "/api/courses/course-api/question-bank/rebuilds/active",
        headers={"X-User-Id": "teacher-1"},
    )
    assert resumable.status_code == 200
    assert resumable.json()["job_id"] == failed["job_id"]
    assert resumable.json()["status"] == "failed"

    monkeypatch.setattr(
        question_bank,
        "assessment_generation_orchestrator",
        DeterministicAssessmentOrchestrator(),
    )
    _, resumed = _rebuild(
        client,
        "request-chapter-resume",
        mode="full",
    )

    assert resumed["result"]["coverage"]
    checkpoint = repository.course_storage.course[
        "question_bank_chapter_rebuild"
    ]
    assert checkpoint["status"] == "completed"
    assert checkpoint["published_node_ids"] == [
        "node-1",
        "node-2",
    ]
    assert repository.course_storage.save_count == 2


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
        "question_bank_partial_overlay"
    )
    active = repository.asset_repository.load_bundle("course-api")
    assert active["quality_report"]["passed"] is True
    assert active["publication_mode"] == (
        "question_bank_partial_overlay"
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


def test_partial_overlay_merges_new_chapter_questions_and_replaces_same_slot():
    previous_questions = [
        {
            "revision_id": "task-node-1-old",
            "node_id": "node-1",
            "assessment_role": "practice",
            "practice_level": "concept_check",
            "prompt": "旧题",
        },
        {
            "revision_id": "task-node-legacy",
            "node_id": "node-legacy",
            "assessment_role": "practice",
            "practice_level": "concept_check",
            "prompt": "应保留的旧章节题目",
        },
    ]
    approved_tasks = [
        {
            "revision_id": "task-node-1-new",
            "node_id": "node-1",
            "assessment_role": "practice",
            "practice_level": "concept_check",
            "prompt": "更新后的题目",
        },
        {
            "revision_id": "task-node-2",
            "node_id": "node-2",
            "assessment_role": "practice",
            "practice_level": "concept_check",
            "prompt": "新章节题目",
        },
    ]
    previous_assets = {
        "schema_version": "learning_assets_v2",
        "plan": {"enabled_asset_types": ["questions"]},
        "assets": {
            "questions": previous_questions,
            "final_assessment": [{"revision_id": "final-1"}],
        },
        "quality_report": {"passed": True},
    }
    compiled_assets = {
        "quality_report": {"passed": False},
        "assets": {"questions": []},
    }
    partial_bank = {
        "course_id": "course-api",
        "bundle_revision_id": "qbb-partial-overlay",
        "coverage": {"coverage_ratio": 0.5},
        "items": [
            {
                "assessment_role": "practice",
                "lifecycle_status": "approved",
                "quality_report": {"passed": True},
                "formal_task_revision_id": task["revision_id"],
                "formal_task": task,
            }
            for task in approved_tasks
        ],
    }

    selected = question_bank._select_publishable_asset_bundle(
        previous_assets,
        compiled_assets,
        partial_bank,
    )

    assert selected["publication_mode"] == "question_bank_partial_overlay"
    assert selected["assets"]["questions"] == [
        approved_tasks[0],
        previous_questions[1],
        approved_tasks[1],
    ]
    assert selected["assets"]["final_assessment"] == [
        {"revision_id": "final-1"}
    ]
