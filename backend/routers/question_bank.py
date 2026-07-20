"""Teacher-facing course-local question-bank APIs."""

from __future__ import annotations

import asyncio
import atexit
from concurrent.futures import Future
from copy import deepcopy
import logging
import os
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
    slot_for,
)
from assessment_compiler import compile_formal_task_contract
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
    refresh_question_bank_bundle,
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
    resume_existing: bool = True

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


def _configured_rebuild_worker_count() -> int:
    try:
        value = int(
            os.getenv("QUESTION_BANK_REBUILD_MAX_WORKERS", "1")
        )
    except ValueError:
        value = 1
    return max(1, min(4, value))


question_bank_rebuild_executor = QuestionBankRebuildExecutor(
    max_workers=_configured_rebuild_worker_count(),
)
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
        "chapter_rebuild": _chapter_rebuild_progress(course, bundle),
        "items": items,
        "total": len(items),
        "access_scope": "teacher_authenticated_course_management",
    }


_PRACTICE_LEVELS = {
    "concept_check",
    "objective_practice",
    "mastery_check",
}


def _modern_published_chapter_node_ids(
    course: dict[str, Any],
    bundle: dict[str, Any] | None,
) -> set[str]:
    """Infer chapters already replaced by a complete v2 question set.

    Some courses started their migration before chapter checkpoints were
    introduced.  The active bundle is authoritative in that case: a chapter
    counts only when all three practice slots are published and have passed
    the v2 quality gate.
    """

    course_node_ids = {
        str(node.get("node_id") or "")
        for node in course.get("nodes") or []
        if (
            int(node.get("node_level") or 1) == 2
            and node.get("node_id")
        )
    }
    blueprint = (bundle or {}).get("assessment_blueprint") or {}
    solutions = (bundle or {}).get("solution_envelopes") or {}
    levels_by_node: dict[str, set[str]] = {}
    for item in (bundle or {}).get("items") or []:
        node_id = str(item.get("node_id") or "")
        quality = item.get("quality_report") or {}
        if (
            node_id not in course_node_ids
            or item.get("assessment_role") != "practice"
            or item.get("lifecycle_status") != "approved"
            or item.get("generation_status") != "published"
            or quality.get("schema_version")
            != "question_quality_report_v2"
            or quality.get("passed") is not True
        ):
            continue
        hydrated = deepcopy(item)
        level = str(
            next(
                iter(item.get("practice_levels") or []),
                item.get("practice_level") or "",
            )
        )
        assessment_slot = slot_for(
            blueprint,
            node_id=node_id,
            practice_level=level,
        )
        if assessment_slot:
            hydrated["assessment_slot"] = assessment_slot
        solution = solutions.get(
            str(item.get("solution_revision_id") or "")
        )
        compiled = compile_formal_task_contract(
            hydrated,
            solution,
        )
        validation = compiled.get("contract_validation") or {}
        quality_hash = str(
            quality.get("compiled_contract_hash") or ""
        )
        if (
            validation.get("passed") is not True
            or (
                quality_hash
                and quality_hash
                != compiled.get("compiled_contract_hash")
            )
        ):
            continue
        levels = {
            str(value)
            for value in (
                item.get("practice_levels")
                or [item.get("practice_level")]
            )
            if str(value) in _PRACTICE_LEVELS
        }
        levels_by_node.setdefault(node_id, set()).update(levels)
    return {
        node_id
        for node_id, levels in levels_by_node.items()
        if levels == _PRACTICE_LEVELS
    }


def _chapter_rebuild_progress(
    course: dict[str, Any],
    bundle: dict[str, Any] | None,
) -> dict[str, Any]:
    checkpoint = deepcopy(
        course.get("question_bank_chapter_rebuild") or {}
    )
    course_node_ids = [
        str(node.get("node_id") or "")
        for node in course.get("nodes") or []
        if (
            int(node.get("node_level") or 1) == 2
            and node.get("node_id")
        )
    ]
    known = set(course_node_ids)
    checkpoint_published = {
        str(node_id)
        for node_id in checkpoint.get("published_node_ids") or []
        if str(node_id) in known
    }
    inferred = _modern_published_chapter_node_ids(course, bundle)
    published = (
        checkpoint_published & inferred
        if checkpoint_published
        else set(inferred)
    )
    total = len(course_node_ids)
    completed = len(published)
    status_value = str(checkpoint.get("status") or "")
    if total and completed == total:
        progress_status = "completed"
    elif completed:
        progress_status = (
            status_value
            if status_value in {"running", "failed"}
            else "partial"
        )
    else:
        progress_status = (
            status_value
            if status_value in {"running", "failed"}
            else "not_started"
        )
    return {
        "schema_version": "question_bank_chapter_rebuild_v1",
        **checkpoint,
        "status": progress_status,
        "published_node_ids": [
            node_id
            for node_id in course_node_ids
            if node_id in published
        ],
        "inferred_node_ids": [
            node_id
            for node_id in course_node_ids
            if node_id in inferred
        ],
        "total_chapters": total,
        "completed_chapters": completed,
        "remaining_chapters": max(0, total - completed),
        "can_resume": bool(0 < completed < total),
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


@router.get("/rebuilds/active")
async def get_active_question_bank_rebuild(
    course_id: str,
    x_user_id: str | None = Header(
        default=None,
        alias="X-User-Id",
    ),
):
    require_user_id(x_user_id)
    course = await get_course_or_404(course_id)
    job = question_bank_rebuild_job_repository.active_for_course(
        course_id,
    )
    if not job:
        checkpoint = (
            course.get("question_bank_chapter_rebuild") or {}
        )
        checkpoint_job_id = str(
            checkpoint.get("job_id") or ""
        )
        if (
            checkpoint.get("status") in {"running", "failed"}
            and checkpoint_job_id
        ):
            job = question_bank_rebuild_job_repository.load(
                course_id,
                checkpoint_job_id,
            )
    if not job:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "question_bank_active_rebuild_not_found",
            },
        )
    return _job_response(job, deduplicated=False)


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
            retryable=bool(
                exc.status_code >= 500
                or code
                in {
                    "chapter_question_generation_failed",
                    "chapter_publication_incomplete",
                }
            ),
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
        published_chapters = len(published_node_ids)
        overall_completed_items = (
            resumed_chapter_count * 3 + completed_items
            if chapter_publication_enabled
            else completed_items
        )
        overall_total_items = (
            max(1, total_chapters * 3)
            if chapter_publication_enabled
            else total_items
        )
        progress = 50 + min(
            9,
            int(
                overall_completed_items
                * 9
                / overall_total_items
            ),
        )
        current_chapter = str(event.get("node_name") or "")
        if not current_chapter:
            current_node_id = str(event.get("node_id") or "")
            current_chapter = next(
                (
                    str(node.get("node_name") or current_node_id)
                    for node in course_for_bank.get("nodes") or []
                    if str(node.get("node_id") or "")
                    == current_node_id
                ),
                current_node_id,
            )
        chapter_item = (
            (completed_items - 1) % 3 + 1
            if completed_items
            else 0
        )
        details = {
            **deepcopy(event),
            "published_chapters": published_chapters,
            "total_chapters": total_chapters,
            "current_chapter": current_chapter,
            "current_chapter_item": chapter_item,
            "chapter_item_total": 3,
        }
        repository.heartbeat(
            job_id,
            stage_id="question_generation",
            progress=progress,
            message=(
                (
                    f"已发布 {published_chapters}/"
                    f"{total_chapters} 个章节 · "
                    f"正在生成 {current_chapter} "
                    f"第 {chapter_item}/3 道题"
                )
                if chapter_publication_enabled
                else (
                    f"正在生成第 {completed_items}/"
                    f"{total_items} 道候选题"
                )
            ),
            details=details,
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
    chapter_publication_enabled = payload.scope in {
        "course",
        "nodes",
    }
    course_node_ids = [
        str(node.get("node_id") or "")
        for node in course_for_bank.get("nodes") or []
        if (
            int(node.get("node_level") or 1) == 2
            and node.get("node_id")
        )
    ]
    campaign_node_ids = (
        course_node_ids
        if payload.scope == "course"
        else [
            node_id
            for node_id in payload.node_ids
            if node_id in set(course_node_ids)
        ]
    )
    checkpoint = deepcopy(
        course.get("question_bank_chapter_rebuild") or {}
    )
    resumable_checkpoint = bool(
        payload.scope == "course"
        and payload.resume_existing
        and checkpoint.get("status") in {"running", "failed"}
        and checkpoint.get("blueprint_revision_id")
        == assessment_blueprint.get("blueprint_revision_id")
    )
    checkpoint_node_ids = {
        str(node_id)
        for node_id in (
            checkpoint.get("published_node_ids") or []
            if resumable_checkpoint
            else []
        )
        if str(node_id) in set(course_node_ids)
    }
    checkpoint_node_ids &= _modern_published_chapter_node_ids(
        course,
        previous,
    )
    inferred_node_ids = (
        _modern_published_chapter_node_ids(course, previous)
        if (
            payload.scope == "course"
            and payload.resume_existing
            and not resumable_checkpoint
        )
        else set()
    )
    # A fully migrated bank should still allow an intentional full rebuild.
    # Inference is only a bootstrap for interrupted/partial migrations.
    if len(inferred_node_ids) == len(course_node_ids):
        inferred_node_ids = set()
    published_node_ids = {
        *checkpoint_node_ids,
        *inferred_node_ids,
    }
    resumed_chapter_count = len(published_node_ids)
    campaign_id = (
        str(checkpoint.get("campaign_id") or "")
        if resumable_checkpoint
        else ""
    ) or str(payload.request_id or job_id)
    target_node_ids = (
        [
            node_id
            for node_id in campaign_node_ids
            if node_id not in published_node_ids
        ]
        if chapter_publication_enabled
        else (
            payload.node_ids
            if payload.scope in {"nodes", "items"}
            else None
        )
    )
    rolling_bank = previous
    rolling_assets = previous_assets
    rolling_course = deepcopy(course)
    failed_chapters: list[dict[str, Any]] = []
    processed_chapter_count = 0
    total_chapters = len(campaign_node_ids)

    async def publish_completed_chapter(
        event: dict[str, Any],
    ) -> None:
        nonlocal rolling_bank
        nonlocal rolling_assets
        nonlocal rolling_course
        nonlocal processed_chapter_count
        node_id = str(event.get("node_id") or "")
        processed_chapter_count += 1
        if not event.get("passed"):
            failure = {
                "node_id": node_id,
                "node_name": str(
                    event.get("node_name") or node_id
                ),
                "error_code": str(
                    event.get("error_code")
                    or "chapter_quality_failed"
                ),
                "error_message": str(
                    event.get("error_message")
                    or "章节内至少一道题未通过质量门"
                )[:500],
            }
            failed_chapters.append(failure)
            repository.heartbeat(
                job_id,
                stage_id="question_generation",
                progress=50 + min(
                    9,
                    int(
                        len(published_node_ids)
                        * 9
                        / max(1, total_chapters)
                    ),
                ),
                message=(
                    f"章节生成未通过：{failure['node_name']}；"
                    "旧题保持不变"
                ),
                details={
                    **deepcopy(event),
                    "chapter_status": "failed",
                    "published_chapters": len(
                        published_node_ids
                    ),
                    "total_chapters": total_chapters,
                    "failed_chapters": deepcopy(
                        failed_chapters
                    ),
                },
            )
            return

        source_node = next(
            (
                deepcopy(node)
                for node in course_for_bank.get("nodes") or []
                if str(node.get("node_id") or "") == node_id
            ),
            None,
        )
        if source_node is None:
            raise ValueError(
                f"chapter node missing during publication: {node_id}"
            )
        chapter_course = deepcopy(course_for_bank)
        chapter_course["nodes"] = [source_node]
        chapter_course["_assessment_generated_contracts"] = {
            node_id: deepcopy(event.get("contracts") or {})
        }
        chapter_course["_assessment_generation_audit"] = {
            "schema_version": "question_generation_audit_v2",
            "course_id": course_id,
            "planned_item_count": 3,
            "failure_count": 0,
            "items": deepcopy(event.get("audit_items") or []),
            "chapter_publication": True,
        }
        chapter_course["_course_assessment_blueprint"] = deepcopy(
            assessment_blueprint
        )
        chapter_course["_question_reference_package"] = deepcopy(
            reference_package
        )
        _require_complete_generation(chapter_course)
        chapter_assets = compile_learning_assets(
            chapter_course,
            legacy_tasks=legacy_tasks,
        )
        chapter_bundle = chapter_assets.pop(
            "question_bank_bundle"
        )
        merged_bundle = reconcile_scoped_question_bank(
            rolling_bank,
            chapter_bundle,
            node_ids=[node_id],
            preserve_reviewed=payload.mode == "incremental",
            preserve_global_assessments=True,
        )
        merged_bundle = recalculate_question_bank_coverage(
            course_for_bank,
            merged_bundle,
        )
        prior_campaign_audit = (
            (rolling_bank or {}).get("generation_audit") or {}
        )
        prior_audit_items = (
            deepcopy(prior_campaign_audit.get("items") or [])
            if prior_campaign_audit.get("campaign_id")
            == campaign_id
            else []
        )
        audit_by_slot = {
            (
                str(item.get("node_id") or ""),
                str(item.get("practice_level") or ""),
            ): deepcopy(item)
            for item in [
                *prior_audit_items,
                *list(event.get("audit_items") or []),
            ]
            if isinstance(item, dict)
        }
        merged_bundle["generation_audit"] = {
            "schema_version": "question_generation_audit_v2",
            "campaign_id": campaign_id,
            "planned_item_count": total_chapters * 3,
            "published_item_count": len(audit_by_slot),
            "failure_count": 0,
            "items": list(audit_by_slot.values()),
            "chapter_publication": True,
        }
        merged_bundle = refresh_question_bank_bundle(
            merged_bundle
        )
        compiled_assets = compile_learning_assets(
            course_for_bank,
            question_bank_bundle=merged_bundle,
        )
        compiled_assets.pop("question_bank_bundle", None)
        compiled_assets = _select_publishable_asset_bundle(
            rolling_assets,
            compiled_assets,
            merged_bundle,
        )
        stored = question_bank_repository.save_bundle(
            course_id,
            merged_bundle,
            activate=False,
        )
        stored_assets = learning_asset_repository.save_bundle(
            course_id,
            compiled_assets,
            activate=False,
        )
        next_published_node_ids = {
            *published_node_ids,
            node_id,
        }
        all_chapters_published = bool(
            len(next_published_node_ids) == total_chapters
            and not failed_chapters
            and processed_chapter_count
            == len(target_node_ids or [])
        )
        publication_base = deepcopy(rolling_course)
        if payload.scope == "course":
            publication_base[
                "question_bank_chapter_rebuild"
            ] = {
                "schema_version": (
                    "question_bank_chapter_rebuild_v1"
                ),
                "campaign_id": campaign_id,
                "job_id": job_id,
                "blueprint_revision_id": (
                    assessment_blueprint.get(
                        "blueprint_revision_id"
                    )
                ),
                "status": (
                    "completed"
                    if all_chapters_published
                    else "running"
                ),
                "published_node_ids": sorted(
                    next_published_node_ids
                ),
                "failed_chapters": deepcopy(
                    failed_chapters
                ),
                "total_chapters": total_chapters,
            }
        published_course = await _publish_rebuilt_course(
            course_id,
            publication_base,
            stored,
            stored_assets,
            request_id=(
                payload.request_id
                if all_chapters_published
                else None
            ),
            previous_question_bank_revision_id=(
                str(
                    (rolling_bank or {}).get(
                        "bundle_revision_id"
                    )
                    or ""
                )
                or None
            ),
            previous_asset_revision_id=(
                str(
                    (rolling_assets or {}).get(
                        "bundle_revision_id"
                    )
                    or ""
                )
                or None
            ),
            changed_node_ids=[node_id],
        )
        published_node_ids.add(node_id)
        rolling_bank = stored
        rolling_assets = stored_assets
        rolling_course = published_course
        repository.heartbeat(
            job_id,
            stage_id="question_generation",
            progress=50 + min(
                9,
                int(
                    len(published_node_ids)
                    * 9
                    / max(1, total_chapters)
                ),
            ),
            message=(
                f"已发布 {len(published_node_ids)}/"
                f"{total_chapters} 个章节 · "
                f"刚完成 {event.get('node_name') or node_id}"
            ),
            details={
                **deepcopy(event),
                "chapter_status": "published",
                "published_chapters": len(
                    published_node_ids
                ),
                "total_chapters": total_chapters,
                "published_node_ids": sorted(
                    published_node_ids
                ),
                "failed_chapters": deepcopy(failed_chapters),
            },
        )

    course_for_bank = (
        await assessment_generation_orchestrator.prepare_course(
            course_for_bank,
            node_ids=target_node_ids,
            on_progress=report_generation_progress,
            on_chapter_complete=(
                publish_completed_chapter
                if chapter_publication_enabled
                else None
            ),
            reference_package=reference_package,
        )
    )
    if chapter_publication_enabled:
        if failed_chapters:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "chapter_question_generation_failed",
                    "message": (
                        "部分章节未通过质量门；已发布章节保持生效，"
                        "失败章节继续使用旧题"
                    ),
                    "failed_chapters": deepcopy(
                        failed_chapters
                    ),
                    "published_chapters": len(
                        published_node_ids
                    ),
                    "total_chapters": total_chapters,
                },
            )
        if (
            rolling_bank is None
            or rolling_assets is None
            or len(published_node_ids) != total_chapters
        ):
            raise HTTPException(
                status_code=500,
                detail={
                    "code": "chapter_publication_incomplete",
                    "message": (
                        "章节生成已结束，但发布检查未完整通过"
                    ),
                    "published_chapters": len(
                        published_node_ids
                    ),
                    "total_chapters": total_chapters,
                },
            )
        repository.advance(
            job_id,
            stage_id="independent_solving",
            message="所有已发布章节均已完成独立求解",
        )
        repository.advance(
            job_id,
            stage_id="quality_validation",
            message="正在复核整门课程的题型与质量分布",
        )
        repository.advance(
            job_id,
            stage_id="waiting_review",
            message="正在计算章节审核队列",
        )
        response = _rebuild_response(
            course_id,
            payload.request_id,
            rolling_bank,
            rolling_assets,
            rolling_course,
            deduplicated=False,
        )
        if payload.scope == "nodes":
            response["review_queue"] = _scope_review_queue(
                response.get("review_queue") or {},
                node_ids=set(campaign_node_ids),
                assessment_roles={"practice"},
            )
        if not (response.get("review_queue") or {}).get(
            "blocking_count"
        ):
            repository.advance(
                job_id,
                stage_id="publication",
                message=(
                    f"已按章节发布 {total_chapters}/"
                    f"{total_chapters} 个章节"
                ),
            )
        return response

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
                "error_message": str(
                    item.get("error_message") or ""
                )[:500],
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


def _scope_review_queue(
    queue: dict[str, Any],
    *,
    node_ids: set[str],
    assessment_roles: set[str],
) -> dict[str, Any]:
    """Report only review work introduced by a scoped rebuild."""
    result = deepcopy(queue)
    blocking_items = [
        deepcopy(item)
        for item in queue.get("items") or []
        if (
            str(item.get("node_id") or "") in node_ids
            and str(item.get("assessment_role") or "")
            in assessment_roles
        )
    ]
    sample_items = [
        deepcopy(item)
        for item in queue.get("sample_items") or []
        if (
            str(item.get("node_id") or "") in node_ids
            and str(item.get("assessment_role") or "")
            in assessment_roles
        )
    ]
    result["items"] = blocking_items
    result["sample_items"] = sample_items
    result["blocking_count"] = len(blocking_items)
    result["sample_count"] = len(sample_items)
    result["tier_counts"] = {
        "auto_publish": 0,
        "mandatory_review": len(blocking_items),
        "sample_review": len(sample_items),
    }
    return result


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
    selected["assets"]["questions"] = _merge_approved_question_assets(
        selected["assets"].get("questions") or [],
        approved_items,
    )
    selected["assets"]["question_bank_publications"] = [binding]
    selected["publication_mode"] = publication_mode
    selected["question_bank_publication_quality"] = publication_quality
    return selected


def _merge_approved_question_assets(
    previous_questions: list[dict[str, Any]],
    approved_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Overlay approved formal tasks without dropping unrelated assets."""

    approved_questions = [
        deepcopy(item["formal_task"])
        for item in approved_items
        if isinstance(item.get("formal_task"), dict)
    ]
    if not approved_questions:
        return deepcopy(previous_questions)
    approved_by_slot = {
        _question_asset_slot(question): question
        for question in approved_questions
    }
    merged: list[dict[str, Any]] = []
    emitted_slots: set[tuple[str, str, str] | tuple[str, str]] = set()

    for previous in previous_questions:
        question = deepcopy(previous)
        slot = _question_asset_slot(question)
        if slot in emitted_slots:
            continue
        merged.append(deepcopy(approved_by_slot.get(slot, question)))
        emitted_slots.add(slot)

    for question in approved_questions:
        slot = _question_asset_slot(question)
        if slot in emitted_slots:
            continue
        merged.append(deepcopy(approved_by_slot[slot]))
        emitted_slots.add(slot)

    return merged


def _question_asset_slot(
    question: dict[str, Any],
) -> tuple[str, str, str] | tuple[str, str]:
    node_id = str(question.get("node_id") or "")
    practice_level = str(question.get("practice_level") or "")
    if node_id and practice_level:
        return (
            node_id,
            str(question.get("assessment_role") or "practice"),
            practice_level,
        )
    return (
        "revision",
        str(
            question.get("revision_id")
            or question.get("formal_task_revision_id")
            or stable_hash(question, prefix="question_")
        ),
    )


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
    changed_node_ids: list[str] | None = None,
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
            changed_node_ids=(
                list(changed_node_ids)
                if changed_node_ids is not None
                else [
                    str(node.get("node_id") or "")
                    for node in course.get("nodes") or []
                    if node.get("node_id")
                ]
            ),
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
        "question_bank_chapter_rebuild",
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
