"""Teacher-facing course-local question-bank APIs."""

from __future__ import annotations

import asyncio
import atexit
from concurrent.futures import Future
from copy import deepcopy
import logging
from threading import Event, Thread
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException, Query, status
from pydantic import BaseModel, Field, model_validator

from assessment_orchestrator import AssessmentGenerationOrchestrator
from assessment_contracts import (
    compile_assessment_objectives,
    compile_course_assessment_profile,
)
from assessment_blueprint import (
    compile_course_assessment_blueprint,
)
from assessment_retrieval import (
    compile_local_reference_package,
    enrich_reference_package_with_web,
)
from course_document import COURSE_DOCUMENT_SCHEMA
from course_repository import CourseDocumentRepository
from course_versioning import stable_hash
from course_versions import course_version_repository
from dependencies import get_course_or_404
from learning_asset_storage import learning_asset_repository
from learning_assets import compile_learning_assets
from learner_context import require_user_id
from material_storage import material_repository
from question_bank import (
    filter_question_bank_items,
    load_active_question_bank,
    question_bank_repository,
    reconcile_item_question_bank,
    reconcile_question_bank,
    reconcile_scoped_question_bank,
    recalculate_question_bank_coverage,
    review_question_bank_item,
    revise_question_bank_item,
)
from question_bank_jobs import (
    question_bank_rebuild_job_repository,
)
from storage import storage
from storage_utils import save_course_compat

router = APIRouter(
    prefix="/courses/{course_id}/question-bank",
    tags=["question_bank"],
)

logger = logging.getLogger(__name__)


class QuestionBankRebuildRequest(BaseModel):
    request_id: str | None = Field(default=None, min_length=8, max_length=200)
    scope: Literal["course", "nodes", "items"] = "course"
    node_ids: list[str] = Field(default_factory=list, max_length=200)
    revision_ids: list[str] = Field(
        default_factory=list,
        max_length=200,
    )
    mode: Literal["incremental", "full"] = "incremental"

    @model_validator(mode="after")
    def validate_scope(self):
        self.node_ids = sorted({
            str(value).strip()
            for value in self.node_ids
            if str(value).strip()
        })
        self.revision_ids = sorted({
            str(value).strip()
            for value in self.revision_ids
            if str(value).strip()
        })
        if self.scope == "nodes" and not self.node_ids:
            raise ValueError(
                "node_ids are required when scope is nodes"
            )
        if self.scope == "items" and not self.revision_ids:
            raise ValueError(
                "revision_ids are required when scope is items"
            )
        if self.scope == "course":
            self.node_ids = []
            self.revision_ids = []
        elif self.scope == "nodes":
            self.revision_ids = []
        return self


class QuestionBankRebuildExecutor:
    """Run every rebuild coroutine on one durable event loop.

    The assessment orchestrator owns asyncio primitives and an async HTTP
    client.  Creating a fresh loop with ``asyncio.run`` for every job binds
    those shared objects to the first job's loop and makes the next job fail.
    A dedicated loop also preserves provider cooldown and request-spacing
    state across a migration.
    """

    def __init__(self, *, max_workers: int = 2) -> None:
        self.instance_id = f"qbw_{uuid4().hex}"
        self._max_concurrency = max(1, max_workers)
        self._loop = asyncio.new_event_loop()
        self._ready = Event()
        self._thread = Thread(
            target=self._run_loop,
            name="question-bank-rebuild-loop",
            daemon=True,
        )
        self._semaphore: asyncio.Semaphore | None = None
        self._thread.start()
        self._ready.wait()

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._semaphore = asyncio.Semaphore(
            self._max_concurrency,
        )
        self._ready.set()
        try:
            self._loop.run_forever()
        finally:
            pending = asyncio.all_tasks(self._loop)
            for task in pending:
                task.cancel()
            if pending:
                self._loop.run_until_complete(
                    asyncio.gather(
                        *pending,
                        return_exceptions=True,
                    ),
                )
            self._loop.close()

    async def _run_bounded(self, coroutine) -> None:
        semaphore = self._semaphore
        if semaphore is None:
            raise RuntimeError("question bank rebuild loop is not ready")
        async with semaphore:
            await coroutine

    def submit(
        self,
        *,
        job_id: str,
        course_id: str,
        payload: QuestionBankRebuildRequest,
        course: dict[str, Any],
    ) -> Future[None]:
        future = asyncio.run_coroutine_threadsafe(
            self._run_bounded(
                _run_rebuild_job(
                    job_id=job_id,
                    course_id=course_id,
                    payload=payload,
                    course=deepcopy(course),
                ),
            ),
            self._loop,
        )
        future.add_done_callback(self._report_failure)
        return future

    @staticmethod
    def _report_failure(future: Future[None]) -> None:
        try:
            future.result()
        except Exception:
            logger.exception(
                "Question-bank rebuild coroutine exited unexpectedly",
            )

    def shutdown(self, *, timeout: float = 5.0) -> None:
        if not self._loop.is_running():
            return
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=max(0.0, timeout))


question_bank_rebuild_executor = QuestionBankRebuildExecutor()
atexit.register(question_bank_rebuild_executor.shutdown)
assessment_generation_orchestrator = AssessmentGenerationOrchestrator()


class QuestionBankReviewRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    note: str = Field(default="", max_length=2000)
    expected_bundle_revision_id: str | None = Field(default=None, max_length=200)


class QuestionBankRevisionRequest(BaseModel):
    patch: dict[str, Any]
    expected_bundle_revision_id: str | None = Field(default=None, max_length=200)


@router.get("")
async def get_question_bank(
    course_id: str,
    node_id: str | None = Query(default=None, max_length=200),
    source_type: str | None = Query(default=None, max_length=50),
    lifecycle_status: str | None = Query(default=None, max_length=50),
    risk: str | None = Query(default=None, max_length=100),
    archetype_id: str | None = Query(default=None, max_length=100),
    validation_mode: str | None = Query(default=None, max_length=100),
    risk_level: str | None = Query(default=None, max_length=50),
    objective_id: str | None = Query(default=None, max_length=200),
    generation_status: str | None = Query(default=None, max_length=50),
    x_user_id: str | None = Header(
        default=None,
        alias="X-User-Id",
    ),
):
    require_user_id(x_user_id)
    course = await get_course_or_404(course_id)
    bundle = load_active_question_bank(
        course,
        repository=question_bank_repository,
    )
    if not bundle:
        raise HTTPException(
            status_code=404,
            detail={"code": "question_bank_not_built"},
        )
    items = filter_question_bank_items(
        bundle,
        node_id=node_id,
        source_type=source_type,
        lifecycle_status=lifecycle_status,
        risk=risk,
        archetype_id=archetype_id,
        validation_mode=validation_mode,
        risk_level=risk_level,
        objective_id=objective_id,
        generation_status=generation_status,
    )
    return {
        "schema_version": "question_bank_api_v1",
        "course_id": course_id,
        "bundle_revision_id": bundle.get("bundle_revision_id"),
        "coverage": bundle.get("coverage") or {},
        "assessment_profile": bundle.get("assessment_profile") or {},
        "assessment_objectives": (
            bundle.get("assessment_objectives") or []
        ),
        "assessment_blueprint": (
            bundle.get("assessment_blueprint") or {}
        ),
        "reference_package": (
            bundle.get("reference_package") or {}
        ),
        "generation_summary": _generation_summary(
            bundle,
            items,
        ),
        "review_queue": bundle.get("review_queue") or {},
        "web_enrichment": bundle.get("web_enrichment") or {},
        "items": items,
        "total": len(items),
        "access_scope": "teacher_authenticated_course_management",
    }


def _generation_summary(
    bundle: dict[str, Any],
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    question_types: dict[str, int] = {}
    input_modes: dict[str, int] = {}
    scores: list[int] = []
    for item in items:
        question_type = str(
            item.get("question_type") or "unknown"
        )
        question_types[question_type] = (
            question_types.get(question_type, 0) + 1
        )
        input_mode = str(
            (item.get("input_contract") or {}).get("mode")
            or "compatibility_text"
        )
        input_modes[input_mode] = input_modes.get(input_mode, 0) + 1
        score = (item.get("quality_report") or {}).get("score")
        if isinstance(score, (int, float)):
            scores.append(int(score))
    audit = bundle.get("generation_audit") or {}
    return {
        "question_type_distribution": question_types,
        "input_mode_distribution": input_modes,
        "quality_scores": {
            "count": len(scores),
            "minimum": min(scores) if scores else None,
            "maximum": max(scores) if scores else None,
            "average": (
                round(sum(scores) / len(scores), 2)
                if scores
                else None
            ),
        },
        "generation_calls": audit.get("generation_calls", 0),
        "repair_calls": audit.get("repair_calls", 0),
        "failure_count": audit.get("failure_count", 0),
        "items": deepcopy(audit.get("items") or []),
    }


@router.post("/rebuild", status_code=status.HTTP_202_ACCEPTED)
async def rebuild_question_bank(
    course_id: str,
    payload: QuestionBankRebuildRequest,
    x_user_id: str | None = Header(
        default=None,
        alias="X-User-Id",
    ),
):
    actor_id = require_user_id(x_user_id)
    course = await get_course_or_404(course_id)
    if payload.scope == "nodes":
        known_node_ids = {
            str(node.get("node_id") or "")
            for node in course.get("nodes") or []
            if int(node.get("node_level") or 1) == 2
        }
        unknown = sorted(set(payload.node_ids) - known_node_ids)
        if unknown:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "question_bank_rebuild_nodes_unknown",
                    "node_ids": unknown,
                },
            )
    elif payload.scope == "items":
        bundle = _require_bundle(course)
        requested_revisions = set(payload.revision_ids)
        selected_items = [
            item
            for item in bundle.get("items") or []
            if str(item.get("revision_id") or "")
            in requested_revisions
        ]
        if not selected_items:
            raw_bundle = question_bank_repository.load_bundle(
                course_id
            )
            selected_items = [
                item
                for item in (raw_bundle or {}).get("items") or []
                if str(item.get("revision_id") or "")
                in requested_revisions
            ]
        found_revisions = {
            str(item.get("revision_id") or "")
            for item in selected_items
        }
        unknown = sorted(
            requested_revisions - found_revisions
        )
        if unknown:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "question_bank_rebuild_items_unknown",
                    "revision_ids": unknown,
                },
            )
        payload.node_ids = sorted({
            str(node_id)
            for item in selected_items
            for node_id in (
                item.get("node_ids")
                or [item.get("node_id")]
            )
            if node_id
        })
        if not payload.node_ids:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "question_bank_rebuild_item_nodes_missing",
                },
            )
    job, created = (
        question_bank_rebuild_job_repository.create_job(
            course_id,
            request_id=payload.request_id,
            scope=payload.scope,
            node_ids=payload.node_ids,
            revision_ids=payload.revision_ids,
            mode=payload.mode,
            actor_id=actor_id,
            worker_id=str(
                getattr(
                    question_bank_rebuild_executor,
                    "instance_id",
                    "question-bank-worker",
                )
            ),
        )
    )
    if created:
        question_bank_rebuild_executor.submit(
            job_id=str(job["job_id"]),
            course_id=course_id,
            payload=payload,
            course=course,
        )
    return _job_response(
        job,
        deduplicated=not created,
    )


@router.get("/rebuilds/{job_id}")
async def get_question_bank_rebuild(
    course_id: str,
    job_id: str,
    x_user_id: str | None = Header(
        default=None,
        alias="X-User-Id",
    ),
):
    require_user_id(x_user_id)
    await get_course_or_404(course_id)
    job = question_bank_rebuild_job_repository.load(
        course_id,
        job_id,
    )
    if not job:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "question_bank_rebuild_job_not_found",
            },
        )
    return _job_response(job, deduplicated=False)


def _job_response(
    job: dict[str, Any],
    *,
    deduplicated: bool,
) -> dict[str, Any]:
    result = deepcopy(job)
    result["deduplicated"] = deduplicated
    result["status_url"] = (
        f"/api/courses/{job['course_id']}/question-bank/"
        f"rebuilds/{job['job_id']}"
    )
    return result


async def _run_rebuild_job(
    *,
    job_id: str,
    course_id: str,
    payload: QuestionBankRebuildRequest,
    course: dict[str, Any],
) -> None:
    repository = question_bank_rebuild_job_repository
    try:
        repository.start(job_id)
        result = await _execute_question_bank_rebuild(
            course_id=course_id,
            payload=payload,
            course=course,
            job_id=job_id,
        )
        repository.complete(job_id, result=result)
    except HTTPException as exc:
        detail = exc.detail
        if isinstance(detail, dict):
            code = str(detail.get("code") or "rebuild_failed")
            message = str(
                detail.get("message")
                or detail.get("detail")
                or code
            )
        else:
            code = "rebuild_failed"
            message = str(detail)
        repository.fail(
            job_id,
            code=code,
            message=message,
            retryable=exc.status_code >= 500,
        )
    except Exception as exc:
        logger.exception(
            "Question-bank rebuild failed: course_id=%s job_id=%s",
            course_id,
            job_id,
        )
        repository.fail(
            job_id,
            code="question_bank_rebuild_failed",
            message=str(exc)[:1000] or "题库重建失败",
            retryable=True,
        )


async def _execute_question_bank_rebuild(
    *,
    course_id: str,
    payload: QuestionBankRebuildRequest,
    course: dict[str, Any],
    job_id: str,
) -> dict[str, Any]:
    repository = question_bank_rebuild_job_repository
    previous = question_bank_repository.load_bundle(course_id)
    previous_assets = learning_asset_repository.load_bundle(course_id)
    if (
        payload.request_id
        and previous
        and previous_assets
        and course.get("question_bank_last_rebuild_request_id")
        == payload.request_id
    ):
        return _rebuild_response(
            course_id,
            payload.request_id,
            previous,
            previous_assets,
            course,
            deduplicated=True,
        )
    repository.advance(
        job_id,
        stage_id="material_parsing",
        message="正在解析题目资料与课程正文",
    )
    course_for_bank = deepcopy(course)
    course_for_bank["evidence_catalog"] = _load_course_evidence(
        course.get("material_bindings") or []
    )
    repository.advance(
        job_id,
        stage_id="assessment_profile",
        message="正在编译课程测评画像",
    )
    legacy_tasks = []
    if not previous:
        assets = (
            (previous_assets or {}).get("assets")
            or course.get("learning_assets")
            or {}
        )
        legacy_tasks = [
            *(assets.get("questions") or []),
            *(assets.get("final_assessment") or []),
        ]
    repository.advance(
        job_id,
        stage_id="objective_compilation",
        message="正在编译节点能力目标",
    )
    repository.advance(
        job_id,
        stage_id="source_retrieval",
        message="正在检索课程内来源与覆盖缺口",
    )
    repository.advance(
        job_id,
        stage_id="archetype_planning",
        message="正在规划题型原型与验证方式",
    )
    repository.advance(
        job_id,
        stage_id="question_generation",
        message="正在生成三层候选题",
    )

    async def report_generation_progress(
        event: dict[str, Any],
    ) -> None:
        completed_items = int(event.get("completed_items") or 0)
        total_items = max(1, int(event.get("total_items") or 1))
        progress = 50 + min(
            9,
            int(completed_items * 9 / total_items),
        )
        repository.heartbeat(
            job_id,
            stage_id="question_generation",
            progress=progress,
            message=(
                f"正在生成第 {completed_items}/{total_items} 道候选题"
            ),
            details=event,
        )

    assessment_profile = compile_course_assessment_profile(
        course_for_bank
    )
    assessment_objectives = compile_assessment_objectives(
        course_for_bank,
        assessment_profile,
    )
    assessment_blueprint = compile_course_assessment_blueprint(
        course_for_bank,
        profile=assessment_profile,
        objectives=assessment_objectives,
    )
    reference_package = compile_local_reference_package(
        course_for_bank,
        objectives=assessment_objectives,
        blueprint=assessment_blueprint,
    )
    reference_package = await enrich_reference_package_with_web(
        course_for_bank,
        reference_package,
        objectives=assessment_objectives,
    )
    course_for_bank = (
        await assessment_generation_orchestrator.prepare_course(
            course_for_bank,
            node_ids=(
                payload.node_ids
                if payload.scope in {"nodes", "items"}
                else None
            ),
            on_progress=report_generation_progress,
            reference_package=reference_package,
        )
    )
    _require_complete_generation(course_for_bank)
    initial_assets = compile_learning_assets(
        course_for_bank,
        legacy_tasks=legacy_tasks,
    )
    bundle = initial_assets.pop("question_bank_bundle")
    compiled_knowledge_base = next(
        iter(
            initial_assets["assets"].get("course_knowledge_base")
            or []
        ),
        None,
    )
    if compiled_knowledge_base:
        course_for_bank["course_knowledge_base"] = deepcopy(
            compiled_knowledge_base
        )
    compiled_knowledge_map = next(
        iter(
            initial_assets["assets"].get("course_knowledge_map")
            or []
        ),
        None,
    )
    if compiled_knowledge_map:
        course_for_bank["course_knowledge_map"] = deepcopy(
            compiled_knowledge_map
        )
    repository.advance(
        job_id,
        stage_id="independent_solving",
        message="正在执行独立求解与确定性验证",
    )
    repository.advance(
        job_id,
        stage_id="quality_validation",
        message="正在执行质量门与风险分级",
    )
    if payload.scope == "nodes":
        bundle = reconcile_scoped_question_bank(
            previous,
            bundle,
            node_ids=payload.node_ids,
            preserve_reviewed=payload.mode == "incremental",
        )
    elif payload.scope == "items":
        bundle = reconcile_item_question_bank(
            previous,
            bundle,
            revision_ids=payload.revision_ids,
        )
    else:
        bundle = reconcile_question_bank(
            previous,
            bundle,
            preserve_reviewed=payload.mode == "incremental",
        )
    bundle = recalculate_question_bank_coverage(
        course_for_bank,
        bundle,
    )
    compiled_assets = compile_learning_assets(
        course_for_bank,
        question_bank_bundle=bundle,
    )
    compiled_assets.pop("question_bank_bundle", None)
    compiled_assets = _select_publishable_asset_bundle(
        previous_assets,
        compiled_assets,
        bundle,
    )
    stored = question_bank_repository.save_bundle(
        course_id,
        bundle,
        activate=False,
    )
    stored_assets = learning_asset_repository.save_bundle(
        course_id,
        compiled_assets,
        activate=False,
    )
    deduplicated = bool(
        previous
        and previous.get("bundle_revision_id") == stored.get("bundle_revision_id")
        and previous_assets
        and previous_assets.get("bundle_revision_id")
        == stored_assets.get("bundle_revision_id")
        and course.get("question_bank_bundle_revision_id")
        == stored.get("bundle_revision_id")
        and course.get("learning_asset_bundle_revision_id")
        == stored_assets.get("bundle_revision_id")
    )
    published_course = course
    if not deduplicated:
        repository.advance(
            job_id,
            stage_id="waiting_review",
            message="正在计算审核队列与安全发布范围",
        )
        published_course = await _publish_rebuilt_course(
            course_id,
            course,
            stored,
            stored_assets,
            request_id=payload.request_id,
            previous_question_bank_revision_id=(
                str(previous.get("bundle_revision_id") or "")
                if previous
                else None
            ),
            previous_asset_revision_id=(
                str(previous_assets.get("bundle_revision_id") or "")
                if previous_assets
                else None
            ),
        )
    response = _rebuild_response(
        course_id,
        payload.request_id,
        stored,
        stored_assets,
        published_course,
        deduplicated=deduplicated,
    )
    if not (response.get("review_queue") or {}).get(
        "blocking_count"
    ):
        repository.advance(
            job_id,
            stage_id="publication",
            message="题库与课程修订发布完成",
        )
    return response


def _require_complete_generation(
    course: dict[str, Any],
) -> None:
    """Fail before persistence when any planned slot was discarded."""
    audit = course.get("_assessment_generation_audit") or {}
    items = audit.get("items") or []
    planned_count = int(audit.get("planned_item_count") or 0)
    failure_count = int(audit.get("failure_count") or 0)
    discarded = sum(
        str(item.get("final_decision") or "") == "discard"
        for item in items
        if isinstance(item, dict)
    )
    if (
        not planned_count
        or len(items) != planned_count
        or failure_count
        or discarded
    ):
        failures = [
            {
                "node_id": str(item.get("node_id") or ""),
                "practice_level": str(
                    item.get("practice_level") or ""
                ),
                "error_code": str(item.get("error_code") or ""),
                "last_attempt": deepcopy(
                    (item.get("attempts") or [{}])[-1]
                ),
            }
            for item in items
            if isinstance(item, dict)
            and str(item.get("final_decision") or "") == "discard"
        ]
        raise RuntimeError(
            "question_generation_incomplete:"
            f"planned={planned_count},"
            f"completed={len(items)},"
            f"failed={failure_count},"
            f"discarded={discarded},"
            f"details={failures[:5]}"
        )


def _rebuild_response(
    course_id: str,
    request_id: str | None,
    question_bank_bundle: dict[str, Any],
    asset_bundle: dict[str, Any],
    course: dict[str, Any],
    *,
    deduplicated: bool,
) -> dict[str, Any]:
    publication_mode = str(
        asset_bundle.get("publication_mode") or "full_recompile"
    )
    return {
        "schema_version": "question_bank_rebuild_v1",
        "course_id": course_id,
        "request_id": request_id,
        "status": (
            "partial"
            if publication_mode.startswith("question_bank_partial")
            else "completed"
        ),
        "deduplicated": deduplicated,
        "bundle_revision_id": question_bank_bundle["bundle_revision_id"],
        "learning_asset_bundle_revision_id": asset_bundle[
            "bundle_revision_id"
        ],
        "course_version_id": course.get(
            "current_course_version_id"
        ),
        "publication_mode": publication_mode,
        "coverage": question_bank_bundle["coverage"],
        "review_queue": question_bank_bundle["review_queue"],
        "web_enrichment": question_bank_bundle["web_enrichment"],
    }


def _select_publishable_asset_bundle(
    previous_assets: dict[str, Any] | None,
    compiled_assets: dict[str, Any],
    question_bank_bundle: dict[str, Any],
) -> dict[str, Any]:
    approved_items = [
        item
        for item in question_bank_bundle.get("items") or []
        if item.get("lifecycle_status") == "approved"
        and item.get("assessment_role") in {
            "practice",
            "imported_practice",
            "web_enriched_practice",
        }
    ]
    approved_items_passed = bool(approved_items) and all(
        (item.get("quality_report") or {}).get("passed")
        for item in approved_items
    )
    coverage_complete = float(
        (question_bank_bundle.get("coverage") or {}).get(
            "coverage_ratio"
        )
        or 0
    ) == 1
    publication_quality = {
        "schema_version": "question_bank_publication_quality_v1",
        "passed": approved_items_passed and coverage_complete,
        "approved_subset_passed": approved_items_passed,
        "coverage_complete": coverage_complete,
        "approved_task_count": len(approved_items),
        "coverage_ratio": (
            question_bank_bundle.get("coverage") or {}
        ).get("coverage_ratio"),
        "compiled_assets_passed": bool(
            (compiled_assets.get("quality_report") or {}).get("passed")
        ),
        "previous_assets_available": bool(
            previous_assets
            and (previous_assets.get("quality_report") or {}).get("passed")
        ),
    }
    previous_assets_passed = bool(
        previous_assets
        and (previous_assets.get("quality_report") or {}).get("passed")
    )
    if not approved_items_passed:
        if previous_assets_passed:
            return _overlay_question_bank_publication(
                previous_assets,
                question_bank_bundle,
                [],
                publication_quality,
                publication_mode="question_bank_waiting_review_overlay",
                compatibility_policy=(
                    "preserve_passing_assets_until_review_completes"
                ),
            )
        return _approved_question_subset_bundle(
            compiled_assets,
            question_bank_bundle,
            [],
            publication_quality,
            publication_mode="question_bank_waiting_review",
            quality_scope="question_bank_waiting_review",
        )
    if not coverage_complete:
        if previous_assets_passed:
            return _overlay_question_bank_publication(
                previous_assets,
                question_bank_bundle,
                approved_items,
                publication_quality,
                publication_mode="question_bank_partial_overlay",
                compatibility_policy=(
                    "preserve_passing_assets_and_overlay_safe_partial_bank"
                ),
            )
        return _approved_question_subset_bundle(
            compiled_assets,
            question_bank_bundle,
            approved_items,
            publication_quality,
            publication_mode="question_bank_partial",
            quality_scope="approved_question_subset",
        )

    if (compiled_assets.get("quality_report") or {}).get("passed"):
        selected = deepcopy(compiled_assets)
        selected["publication_mode"] = "full_recompile"
        selected["question_bank_publication_quality"] = publication_quality
        return selected
    if not previous_assets_passed:
        return _approved_question_subset_bundle(
            compiled_assets,
            question_bank_bundle,
            approved_items,
            publication_quality,
            publication_mode="question_bank_only",
            quality_scope="question_bank_only",
        )

    return _overlay_question_bank_publication(
        previous_assets,
        question_bank_bundle,
        approved_items,
        publication_quality,
        publication_mode="question_bank_overlay",
        compatibility_policy=(
            "preserve_passing_legacy_assets_and_overlay_approved_bank_tasks"
        ),
    )


def _approved_question_subset_bundle(
    compiled_assets: dict[str, Any],
    question_bank_bundle: dict[str, Any],
    approved_items: list[dict[str, Any]],
    publication_quality: dict[str, Any],
    *,
    publication_mode: str,
    quality_scope: str,
) -> dict[str, Any]:
    binding = _question_bank_publication_binding(
        question_bank_bundle,
        approved_items,
        publication_quality,
        compatibility_policy=quality_scope,
    )
    plan = deepcopy(compiled_assets.get("plan") or {})
    plan["enabled_asset_types"] = ["questions"]
    plan["reading_only_degraded"] = False
    return {
        "schema_version": "learning_assets_v2",
        "plan": plan,
        "assets": {
            "questions": [
                deepcopy(item["formal_task"])
                for item in approved_items
                if isinstance(item.get("formal_task"), dict)
            ],
            "final_assessment": [],
            "question_bank_publications": [binding],
        },
        "quality_report": {
            "schema_version": "asset_quality_v1",
            "scope": quality_scope,
            "passed": True,
            "gates": [{
                "gate": "approved_question_subset",
                "passed": True,
                "issues": [],
            }],
            "issues": [],
            "blocking_issues": [],
            "warnings": [],
        },
        "publication_mode": publication_mode,
        "question_bank_publication_quality": publication_quality,
    }


def _overlay_question_bank_publication(
    previous_assets: dict[str, Any],
    question_bank_bundle: dict[str, Any],
    approved_items: list[dict[str, Any]],
    publication_quality: dict[str, Any],
    *,
    publication_mode: str,
    compatibility_policy: str,
) -> dict[str, Any]:
    binding = _question_bank_publication_binding(
        question_bank_bundle,
        approved_items,
        publication_quality,
        compatibility_policy=compatibility_policy,
    )
    selected = deepcopy(previous_assets)
    selected.pop("bundle_revision_id", None)
    selected["assets"] = deepcopy(selected.get("assets") or {})
    selected["assets"]["question_bank_publications"] = [binding]
    selected["publication_mode"] = publication_mode
    selected["question_bank_publication_quality"] = publication_quality
    return selected


def _question_bank_publication_binding(
    question_bank_bundle: dict[str, Any],
    approved_items: list[dict[str, Any]],
    publication_quality: dict[str, Any],
    *,
    compatibility_policy: str,
) -> dict[str, Any]:
    binding = {
        "schema_version": "question_bank_publication_v1",
        "course_id": question_bank_bundle.get("course_id"),
        "question_bank_bundle_revision_id": question_bank_bundle.get(
            "bundle_revision_id"
        ),
        "formal_task_revision_ids": [
            item.get("formal_task_revision_id")
            for item in approved_items
            if item.get("formal_task_revision_id")
        ],
        "quality_report": publication_quality,
        "compatibility_policy": compatibility_policy,
    }
    binding["revision_id"] = stable_hash(
        binding,
        prefix="qbpr_",
    )
    return binding


async def _publish_rebuilt_course(
    course_id: str,
    course: dict[str, Any],
    question_bank_bundle: dict[str, Any],
    asset_bundle: dict[str, Any],
    *,
    request_id: str | None,
    previous_question_bank_revision_id: str | None,
    previous_asset_revision_id: str | None,
) -> dict[str, Any]:
    updated = _course_with_rebuilt_assets(
        course,
        question_bank_bundle,
        asset_bundle,
    )
    if request_id:
        updated["question_bank_last_rebuild_request_id"] = request_id
    is_canonical = (
        course.get("course_schema_version") == COURSE_DOCUMENT_SCHEMA
        or course.get("course_document_authoritative") is True
    )
    version_id: str | None = None
    if not is_canonical:
        base_version_id = course_version_repository.current_version_id(
            course_id
        )
        if not base_version_id:
            initial = course_version_repository.ensure_initial_version(
                course_id,
                course,
            )
            base_version_id = str(initial["version_id"])
        version = course_version_repository.create_version(
            course_id,
            updated,
            reason="重建课程题库并发布具体练习题",
            operation="question_bank_rebuild",
            base_version_id=base_version_id,
            changed_node_ids=[
                str(node.get("node_id") or "")
                for node in course.get("nodes") or []
                if node.get("node_id")
            ],
            activate=False,
        )
        version_id = str(version["version_id"])
        updated["current_course_version_id"] = version_id
        updated["blueprint_revision_id"] = version.get(
            "blueprint_revision_id"
        )

    persisted = False
    bank_activated = False
    assets_activated = False
    try:
        await _persist_rebuilt_course(course_id, course, updated)
        persisted = True
        question_bank_repository.activate_bundle(
            course_id,
            str(question_bank_bundle["bundle_revision_id"]),
        )
        bank_activated = True
        learning_asset_repository.activate_bundle(
            course_id,
            str(asset_bundle["bundle_revision_id"]),
        )
        assets_activated = True
        if version_id:
            course_version_repository.activate_version(
                course_id,
                version_id,
            )
        return updated
    except Exception:
        if assets_activated:
            _restore_bundle_pointer(
                learning_asset_repository,
                course_id,
                previous_asset_revision_id,
            )
        if bank_activated:
            _restore_bundle_pointer(
                question_bank_repository,
                course_id,
                previous_question_bank_revision_id,
            )
        if persisted:
            await _persist_rebuilt_course(course_id, updated, course)
        raise


def _course_with_rebuilt_assets(
    course: dict[str, Any],
    question_bank_bundle: dict[str, Any],
    asset_bundle: dict[str, Any],
) -> dict[str, Any]:
    updated = deepcopy(course)
    updated["learning_asset_plan"] = deepcopy(asset_bundle["plan"])
    updated["learning_assets"] = deepcopy(asset_bundle["assets"])
    updated["learning_asset_bundle_revision_id"] = asset_bundle[
        "bundle_revision_id"
    ]
    updated["asset_quality_report"] = deepcopy(
        asset_bundle["quality_report"]
    )
    updated["question_bank_bundle_revision_id"] = question_bank_bundle[
        "bundle_revision_id"
    ]
    updated["question_bank_coverage"] = deepcopy(
        question_bank_bundle["coverage"]
    )
    updated["question_bank_review_queue"] = deepcopy(
        question_bank_bundle["review_queue"]
    )
    updated["web_question_enrichment"] = deepcopy(
        question_bank_bundle["web_enrichment"]
    )
    knowledge_base = next(
        iter(updated["learning_assets"].get("course_knowledge_base") or []),
        None,
    )
    if knowledge_base:
        updated["course_knowledge_base"] = deepcopy(knowledge_base)
        updated["course_knowledge_quality_report"] = deepcopy(
            knowledge_base.get("quality_report")
        )
    knowledge_map = next(
        iter(updated["learning_assets"].get("course_knowledge_map") or []),
        None,
    )
    if knowledge_map:
        updated["course_knowledge_map"] = deepcopy(knowledge_map)
    return updated


async def _persist_rebuilt_course(
    course_id: str,
    previous: dict[str, Any],
    updated: dict[str, Any],
) -> None:
    is_canonical = (
        previous.get("course_schema_version") == COURSE_DOCUMENT_SCHEMA
        or previous.get("course_document_authoritative") is True
    )
    if not is_canonical:
        await save_course_compat(storage, course_id, updated)
        return
    keys = {
        "learning_asset_plan",
        "learning_assets",
        "learning_asset_bundle_revision_id",
        "asset_quality_report",
        "question_bank_bundle_revision_id",
        "question_bank_coverage",
        "question_bank_review_queue",
        "web_question_enrichment",
        "question_bank_last_rebuild_request_id",
        "course_knowledge_base",
        "course_knowledge_quality_report",
        "course_knowledge_map",
    }
    updates = {
        key: deepcopy(updated[key])
        for key in keys
        if key in updated
    }
    repository = CourseDocumentRepository(storage)
    await repository.update_metadata(course_id, updates)


def _restore_bundle_pointer(
    repository: Any,
    course_id: str,
    previous_revision_id: str | None,
) -> None:
    if previous_revision_id:
        repository.activate_bundle(course_id, previous_revision_id)
        return
    pointer = repository.root_dir / course_id / "current.json"
    if pointer.exists():
        pointer.unlink()


@router.get("/items/{revision_id}/solution")
async def get_question_bank_item_solution(
    course_id: str,
    revision_id: str,
    x_user_id: str | None = Header(
        default=None,
        alias="X-User-Id",
    ),
):
    require_user_id(x_user_id)
    course = await get_course_or_404(course_id)
    bundle = _require_bundle(course)
    item = next(
        (
            candidate
            for candidate in bundle.get("items") or []
            if str(candidate.get("revision_id") or "")
            == revision_id
        ),
        None,
    )
    if not item:
        raise HTTPException(
            status_code=404,
            detail={"code": "question_bank_item_not_found"},
        )
    solution_revision_id = str(
        item.get("solution_revision_id") or ""
    )
    solution = (
        bundle.get("solution_envelopes") or {}
    ).get(solution_revision_id)
    if not solution:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "question_bank_solution_not_found",
                "solution_revision_id": solution_revision_id,
            },
        )
    return {
        "schema_version": "question_bank_solution_api_v1",
        "course_id": course_id,
        "item_revision_id": revision_id,
        "solution_revision_id": solution_revision_id,
        "solution_envelope": deepcopy(solution),
        "solution_validation": deepcopy(
            item.get("solution_validation") or {}
        ),
        "hint_contract": deepcopy(
            item.get("hint_contract") or {}
        ),
        "access_scope": "teacher_authenticated_course_management",
    }


@router.post("/items/{revision_id}/reviews")
async def review_question(
    course_id: str,
    revision_id: str,
    payload: QuestionBankReviewRequest,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
):
    reviewer_id = require_user_id(x_user_id)
    course = await get_course_or_404(course_id)
    bundle = _require_bundle(course)
    _require_expected_revision(bundle, payload.expected_bundle_revision_id)
    try:
        updated = review_question_bank_item(
            bundle,
            revision_id,
            decision=payload.decision,
            reviewer_id=reviewer_id,
            note=payload.note,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    stored = question_bank_repository.save_bundle(course_id, updated)
    return _mutation_response(stored, revision_id)


@router.post("/items/{revision_id}/revisions", status_code=status.HTTP_201_CREATED)
async def revise_question(
    course_id: str,
    revision_id: str,
    payload: QuestionBankRevisionRequest,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
):
    editor_id = require_user_id(x_user_id)
    course = await get_course_or_404(course_id)
    bundle = _require_bundle(course)
    _require_expected_revision(bundle, payload.expected_bundle_revision_id)
    try:
        updated = revise_question_bank_item(
            bundle,
            revision_id,
            patch=payload.patch,
            editor_id=editor_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    stored = question_bank_repository.save_bundle(course_id, updated)
    edited = next(
        (
            item
            for item in stored.get("items") or []
            if item.get("parent_revision_id") == revision_id
        ),
        None,
    )
    return {
        **_mutation_response(stored, str((edited or {}).get("revision_id") or revision_id)),
        "item": edited,
    }


def _require_bundle(
    course: dict[str, Any],
) -> dict[str, Any]:
    bundle = load_active_question_bank(
        course,
        repository=question_bank_repository,
    )
    if not bundle:
        raise HTTPException(
            status_code=404,
            detail={"code": "question_bank_not_built"},
        )
    return bundle


def _require_expected_revision(
    bundle: dict[str, Any],
    expected_revision_id: str | None,
) -> None:
    if (
        expected_revision_id
        and expected_revision_id != bundle.get("bundle_revision_id")
    ):
        raise HTTPException(
            status_code=409,
            detail={"code": "question_bank_revision_conflict"},
        )


def _load_course_evidence(bindings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for binding in bindings:
        asset_id = str(binding.get("asset_id") or "")
        if not asset_id or asset_id in seen:
            continue
        seen.add(asset_id)
        try:
            result.extend(material_repository.load_evidence(asset_id))
        except (OSError, ValueError):
            continue
    return result


def _mutation_response(
    bundle: dict[str, Any],
    item_revision_id: str,
) -> dict[str, Any]:
    item = next(
        (
            value
            for value in bundle.get("items") or []
            if value.get("revision_id") == item_revision_id
        ),
        None,
    )
    return {
        "schema_version": "question_bank_mutation_v1",
        "course_id": bundle.get("course_id"),
        "bundle_revision_id": bundle.get("bundle_revision_id"),
        "review_queue": bundle.get("review_queue") or {},
        "item": item,
    }


__all__ = ["router"]
