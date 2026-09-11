"""Whole-course candidates on the existing TaskManager queue and journal."""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from copy import deepcopy
from typing import Any

from course_generation_errors import classify_generation_failure

from .core import CourseEvolutionPlan, CourseEvolutionRepository, CourseEvolutionState, course_evolution_repository
from .teacher_execution import generate_teacher_course_change_candidates

ANALYSIS_TASK_TYPE = "teacher_course_change_analysis"
CANDIDATE_TASK_TYPE = "teacher_course_change_generation"
TASK_TYPE = CANDIDATE_TASK_TYPE
_ACTIVE_STATUSES = {"pending", "running"}
logger = logging.getLogger(__name__)


def _safe_analysis_technical_message(error: BaseException, *, expose: bool) -> str:
    if not expose:
        return f"{type(error).__name__}: 详细异常已记录在服务器日志中"
    message = " ".join(str(error).split())[:500] or type(error).__name__
    message = re.sub(
        r"(?i)\b(api[_-]?key|authorization|token)\b\s*[:=]\s*\S+",
        r"\1=<redacted>",
        message,
    )
    message = re.sub(r"(?i)\bbearer\s+\S+", "Bearer <redacted>", message)
    return message


def _analysis_failure_contract(error: BaseException) -> tuple[str, dict[str, Any]]:
    failure = classify_generation_failure(error)
    code = str(failure.get("code") or "generation_failed")
    error_type = type(error).__name__
    if code == "generation_failed" and isinstance(error, ValueError):
        code = "course_change_plan_invalid"

    if error_type == "TeacherCourseChangeSourceUnavailable" or code in {"course_missing", "workspace_missing"}:
        stage = "course_context"
    elif code.startswith("provider_") or code in {
        "generation_budget_exceeded",
        "generation_deadline_exceeded",
        "response_truncated",
    }:
        stage = "ai_analysis"
    elif code == "revision_conflict" or isinstance(error, OSError):
        stage = "plan_persistence"
    elif isinstance(error, ValueError):
        stage = "plan_validation"
    else:
        stage = "plan_creation"

    public_messages = {
        "course_change_plan_invalid": "AI 返回的课程修改方案没有通过校验，请保留原要求后重试。",
        "provider_timeout": "AI 服务响应超时，请稍后按原要求重试。",
        "provider_rate_limited": "AI 服务当前请求过多，请稍后按原要求重试。",
        "provider_quota_exhausted": "AI 服务额度暂不可用，请联系管理员后重试。",
        "provider_auth_failed": "AI 服务认证失败，请联系管理员检查模型配置。",
        "provider_unavailable": "AI 服务暂时不可用，请稍后按原要求重试。",
        "response_truncated": "AI 返回的分析结果不完整，请按原要求重试。",
        "generation_budget_exceeded": "本次课程分析内容超过处理预算，请缩小范围后重试。",
        "generation_deadline_exceeded": "本次课程分析超过允许时长，请稍后重试。",
        "course_missing": "当前课程已不存在，请返回课程列表重新进入。",
        "workspace_missing": "课程生成工作区已失效，请重新进入课程后重试。",
        "revision_conflict": "课程内容已发生变化，请刷新课程后重新分析。",
    }
    if stage == "plan_persistence" and code == "generation_failed":
        public_message = "课程修改方案暂时无法保存，请保留原要求后重试。"
    else:
        public_message = public_messages.get(
            code,
            "课程修改方案处理失败，请保留原要求后重试；若持续失败，请查看技术详情。",
        )
    expose_technical = isinstance(error, (ValueError, TimeoutError, OSError)) or code != "generation_failed"
    technical_message = _safe_analysis_technical_message(error, expose=expose_technical)
    detail = {
        "code": code,
        "failure_stage": stage,
        "exception_type": error_type,
        "public_message": public_message,
        "technical_message": technical_message,
        "translation_key": str(failure.get("translation_key") or ""),
        "retryable": bool(failure.get("retryable", True)),
    }
    return public_message, detail


def latest_analysis_task(manager: Any, user_id: str, course_id: str) -> dict[str, Any] | None:
    """Return the newest whole-course analysis task owned by this teacher."""

    candidates = [
        task
        for task in manager.tasks.values()
        if task.get("type") == ANALYSIS_TASK_TYPE
        and str(task.get("course_id") or "") == course_id
        and str(task.get("owner_id") or "") == user_id
    ]
    if not candidates:
        return None
    candidates.sort(
        key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""),
        reverse=True,
    )
    return manager.get_task_summary(str(candidates[0]["id"]))


async def enqueue_analysis(
    *,
    manager: Any,
    user_id: str,
    course_id: str,
    request_id: str,
    instruction: str,
    supersedes_plan_id: str = "",
    literal_replacement: dict[str, str] | None = None,
    asset_types: list[str] | None = None,
    confirmed_interpretation: bool = False,
    clarification_set_id: str = "",
    clarification_answers: list[dict[str, Any]] | None = None,
    rescan_incomplete_only: bool = False,
) -> dict[str, Any]:
    """Persist whole-course analysis before any model call and return immediately."""

    async with manager._creation_lock:
        owned = [
            task
            for task in manager.tasks.values()
            if task.get("type") == ANALYSIS_TASK_TYPE
            and str(task.get("course_id") or "") == course_id
            and str(task.get("owner_id") or "") == user_id
        ]
        duplicate = next(
            (
                task
                for task in owned
                if str((task.get("request_snapshot") or {}).get("request_id") or "")
                == request_id
            ),
            None,
        )
        if duplicate is not None:
            return manager.get_task_summary(str(duplicate["id"]))
        if any(str(task.get("status") or "") in _ACTIVE_STATUSES for task in owned):
            raise ValueError("当前课程已有整课影响分析正在运行，请等待完成后再提交")

        job_id = f"course-change-analysis-{uuid.uuid4().hex}"
        await manager.create_task(
            course_id,
            ANALYSIS_TASK_TYPE,
            task_id=job_id,
            enqueue=False,
            request_snapshot={
                "request_id": request_id,
                "instruction": instruction,
                "supersedes_plan_id": supersedes_plan_id,
                "literal_replacement": literal_replacement,
                "asset_types": asset_types,
                "confirmed_interpretation": confirmed_interpretation,
                "clarification_set_id": clarification_set_id,
                "clarification_answers": clarification_answers or [],
                "rescan_incomplete_only": rescan_incomplete_only,
                "_retrieval_actor_id": user_id,
            },
        )
        try:
            await manager._update_phase(
                job_id,
                "course_change_analysis_queued",
                0,
                "整课影响分析已进入后台",
                phase_detail={"request_id": request_id},
            )
            await manager._task_queue.put(job_id)
        except BaseException:
            async with manager._lock:
                manager._remove_task_strict(job_id)
            raise
        return manager.get_task_summary(job_id)


async def run_analysis(manager: Any, job_id: str, *, service: Any = None) -> None:
    """Run one restart-safe whole-course analysis task."""

    task = manager.tasks[job_id]
    request = task.get("request_snapshot") or {}
    course_id = str(task.get("course_id") or "")
    user_id = str(task.get("owner_id") or "")
    request_id = str(request.get("request_id") or "")
    if str(task.get("status") or "") not in _ACTIVE_STATUSES:
        return
    if service is None:
        from dependencies import (
            get_course_document_repository,
            get_teacher_lesson_authoring_repository,
        )
        from question_bank import question_bank_repository
        from teaching_representations import teaching_representation_repository

        from .application import CourseEvolutionApplicationService

        service = CourseEvolutionApplicationService(
            evolution_repository=course_evolution_repository,
            document_repository=get_course_document_repository(),
            authoring_repository=get_teacher_lesson_authoring_repository(),
            representation_repository=teaching_representation_repository,
            question_bank_repository=question_bank_repository,
            course_service=manager.course_service,
            task_manager=manager,
        )

    await manager._update_task_status(job_id, "running", message="正在分析整课影响")
    await manager._update_phase(
        job_id,
        "course_change_analysis",
        5,
        "正在读取课程结构与相关课程文件",
        phase_detail={"request_id": request_id},
    )
    checkpoint = deepcopy(task.get("analysis_checkpoint") or {})
    if not checkpoint:
        supersedes = str(request.get("supersedes_plan_id") or "")
        previous = sorted((
            candidate for candidate in manager.tasks.values()
            if candidate.get("id") != job_id
            and candidate.get("type") == ANALYSIS_TASK_TYPE
            and str(candidate.get("owner_id") or "") == user_id
            and str(candidate.get("course_id") or "") == course_id
            and candidate.get("status") in {"failed", "completed"}
            and candidate.get("analysis_checkpoint")
            and (
                (supersedes and (candidate.get("phase_detail") or {}).get("plan_id") == supersedes)
                or (not supersedes and candidate.get("status") == "failed")
            )
        ), key=lambda candidate: str(candidate.get("updated_at") or ""), reverse=True)
        if previous:
            checkpoint = deepcopy(previous[0]["analysis_checkpoint"])

    async def scan_progress(detail: dict[str, Any], saved: dict[str, Any]) -> None:
        async with manager._lock:
            current = manager.tasks.get(job_id)
            if not current or current.get("status") not in _ACTIVE_STATUSES:
                raise asyncio.CancelledError()
            current["analysis_checkpoint"] = deepcopy(saved)
            manager.save_tasks(strict=True)
        total = max(1, int(detail.get("total_parts") or 0))
        done = int(detail.get("completed_parts") or 0)
        failed = int(detail.get("failed_parts") or 0)
        message = (
            f"正在合并《{detail.get('repair_title') or '当前内容'}》的修改建议，已保留检查结果"
            if detail.get('reconciling_content')
            else f"本次 AI 请求失败，等待 {int(detail.get('retry_after_seconds') or 0)} 秒后重试"
            if detail.get("waiting_for_provider")
            else "正在重新请求 AI，已保留完成结果"
            if detail.get("retrying_provider")
            else f"已保留 {detail['retained_units']} 项检查结果；本次已检查 {done}/{detail.get('total_parts', 0)} 段"
            if detail.get('retained_units')
            else f"已检查 {done}/{detail.get('total_parts', 0)} 段课程内容"
        )
        await manager._update_phase(
            job_id, "course_change_analysis", 5 + int(90 * (done + failed) / total),
            message,
            phase_detail={"request_id": request_id, "scan": detail},
        )

    generation = asyncio.create_task(
        service.create_teacher_plan(
            course_id=course_id,
            user_id=user_id,
            request_id=request_id,
            instruction=str(request.get("instruction") or ""),
            supersedes_plan_id=str(request.get("supersedes_plan_id") or ""),
            literal_replacement=request.get("literal_replacement"),
            asset_types=request.get("asset_types"),
            confirmed_interpretation=bool(request.get("confirmed_interpretation")),
            clarification_set_id=str(request.get("clarification_set_id") or ""),
            clarification_answers=request.get("clarification_answers") or [],
            scan_checkpoint=checkpoint,
            on_scan_progress=scan_progress,
            rescan_incomplete_only=bool(request.get('rescan_incomplete_only')),
        )
    )
    try:
        while not generation.done():
            await asyncio.wait({generation}, timeout=15)
            if not generation.done():
                current = manager.tasks.get(job_id) or {}
                await manager._update_phase(
                    job_id,
                    "course_change_analysis",
                    int(current.get("progress") or 5),
                    str(current.get("message") or "正在分析整课影响"),
                    phase_detail=deepcopy(current.get("phase_detail") or {"request_id": request_id}),
                )
        state = await generation
        plan = next(
            item
            for item in state.change_sets
            if str(item.impact_summary.get("request_id") or "") == request_id
        )
        coverage = plan.impact_summary.get('coverage') or {}
        pending = len(coverage.get('unscanned_unit_ids') or [])
        detail = {**deepcopy((manager.tasks[job_id].get('phase_detail') or {})),
                  'request_id': request_id, 'plan_id': plan.change_set_id,
                  'analysis_outcome': 'incomplete' if pending else 'complete',
                  'coverage': {key: coverage.get(key, 0) for key in ('scanned_units', 'indexed_units', 'retained_units')},
                  'pending_units': pending}
        message = (f"本次检查已结束，尚有 {pending} 项未完成，已保留成功结果"
                   if pending else "整课影响分析完成")
        await manager._update_phase(
            job_id,
            "course_change_analysis",
            100,
            message,
            phase_detail=detail,
        )
        await manager._update_task_status(job_id, "completed", message=message)
    except asyncio.CancelledError:
        raise
    except Exception as error:
        public_message, error_detail = _analysis_failure_contract(error)
        logger.exception(
            "Whole-course analysis failed job_id=%s request_id=%s stage=%s code=%s",
            job_id,
            request_id,
            error_detail["failure_stage"],
            error_detail["code"],
        )
        await manager._update_task_status(
            job_id,
            "failed",
            message=public_message,
            error=error_detail["technical_message"],
            error_detail=error_detail,
        )
    finally:
        if not generation.done():
            generation.cancel()
            await asyncio.gather(generation, return_exceptions=True)


async def enqueue_candidates(*, manager: Any, service: Any, user_id: str, course_id: str, plan_id: str) -> Any:
    repository = service.evolution_repository
    async with manager._creation_lock:
        state = repository.load(user_id, course_id)
        plan = next((p for p in state.change_sets if p.change_set_id == plan_id), None)
        if plan is None:
            raise KeyError(plan_id)
        if plan.status != "pending" or not plan.impact_summary.get("scope_review"):
            raise ValueError("请先确认当前方案的影响范围")
        answer_snapshot = plan.teacher_change_planning.intent.clarification_answer_snapshot if plan.teacher_change_planning else None
        answer_digest = answer_snapshot.answer_digest if answer_snapshot else ""
        existing = manager.get_task(plan.generation_job_id) if plan.generation_job_id else None
        if (
            existing
            and existing.get("status") in {"pending", "running"}
            and (existing.get("request_snapshot") or {}).get("review_revision") == plan.review_revision
            and str((existing.get("request_snapshot") or {}).get("clarification_answer_digest") or "") == answer_digest
        ):
            return state
        job_id = f"course-change-{uuid.uuid4().hex}"
        review_revision = plan.review_revision
        await manager.create_task(
            course_id,
            CANDIDATE_TASK_TYPE,
            task_id=job_id,
            enqueue=False,
            request_snapshot={
                "plan_id": plan_id,
                "review_revision": review_revision,
                "clarification_answer_digest": answer_digest,
                "_retrieval_actor_id": user_id,
            },
        )
        try:

            def claim(current: CourseEvolutionState) -> CourseEvolutionState:
                target = next(p for p in current.change_sets if p.change_set_id == plan_id)
                if target.status != "pending" or target.review_revision != review_revision:
                    raise ValueError("方案已变化，请重新打开当前方案")
                target.generation_job_id = job_id
                target.generation_status = "generating"
                target.impact_summary.pop("generation_error", None)
                return current

            result = repository.update(user_id, course_id, claim)
            await manager._task_queue.put(job_id)
            return result
        except BaseException:

            def release(current: CourseEvolutionState) -> CourseEvolutionState:
                target = next((p for p in current.change_sets if p.change_set_id == plan_id), None)
                if target and target.generation_job_id == job_id:
                    target.generation_status = "failed"
                    target.impact_summary["generation_error"] = "任务未能入队，请重试。"
                return current

            repository.update(user_id, course_id, release)
            async with manager._lock:
                manager._remove_task_strict(job_id)
            raise


async def run_candidates(
    manager: Any,
    job_id: str,
    *,
    repository: CourseEvolutionRepository | None = None,
    authoring_repository: Any = None,
    representation_repository: Any = None,
) -> None:
    # Resolve the same repository used by teacher routes, including live jobs.
    from dependencies import get_teacher_lesson_authoring_repository
    from teaching_representations import teaching_representation_repository

    repository = repository or course_evolution_repository
    authoring_repository = authoring_repository or get_teacher_lesson_authoring_repository()
    representation_repository = representation_repository or teaching_representation_repository
    task = manager.tasks[job_id]
    request = task.get("request_snapshot") or {}
    course_id, user_id = str(task["course_id"]), str(task.get("owner_id") or "")
    plan_id = str(request.get("plan_id") or "")

    def current_plan() -> CourseEvolutionPlan | None:
        return next((p for p in repository.load(user_id, course_id).change_sets if p.change_set_id == plan_id), None)

    def active() -> bool:
        plan = current_plan()
        return bool(
            plan
            and plan.status == "pending"
            and plan.generation_job_id == job_id
            and plan.review_revision == request.get("review_revision")
            and (
                (
                    plan.teacher_change_planning.intent.clarification_answer_snapshot.answer_digest
                    if plan.teacher_change_planning
                    and plan.teacher_change_planning.intent.clarification_answer_snapshot
                    else ""
                )
                == str(request.get("clarification_answer_digest") or "")
            )
            and manager.tasks.get(job_id, {}).get("status") in {"pending", "running"}
        )

    progress_counts = [0, 0]

    async def progress(done: int, total: int) -> None:
        progress_counts[:] = [done, total]
        if not active():
            raise ValueError("方案或任务已变化，旧候选已停止")
        await manager._update_phase(
            job_id,
            "course_change_candidates",
            int(95 * done / max(1, total)),
            f"已处理 {done}/{total} 项修改候选",
            phase_detail={"plan_id": plan_id, "completed": done, "total": total},
        )

    if not active():
        await manager._update_task_status(job_id, "cancelled", message="方案已修改或放弃")
        return
    await manager._update_task_status(job_id, "running", message="正在形成修改候选")
    try:
        course = await asyncio.to_thread(manager._course_document_repository.load_course_view, course_id)
        workspace = manager.get_generation_workspace_course_for_task(
            course_id,
            task_type="teacher_outline_generation",
            require_confirmed_outline=False,
            require_usable_outline=True,
        )
        if isinstance(workspace, dict) and workspace.get("nodes"):
            course = workspace
        generation = asyncio.create_task(
            generate_teacher_course_change_candidates(
                course_data=course,
                user_id=user_id,
                change_set_id=plan_id,
                repository=repository,
                authoring_repository=authoring_repository,
                representation_repository=representation_repository,
                question_bank_repository=manager._question_bank_repository,
                course_service=manager.course_service,
                job_id=job_id,
                on_progress=progress,
            )
        )
        try:
            while not generation.done():
                await asyncio.wait({generation}, timeout=15)
                if not generation.done():
                    await progress(*progress_counts)
            state = await generation
        finally:
            if not generation.done():
                generation.cancel()
                await asyncio.gather(generation, return_exceptions=True)
        plan = next(p for p in state.change_sets if p.change_set_id == plan_id)
        failed = int((plan.impact_summary.get("candidate_bundle") or {}).get("failed_migration_count") or 0)
        await manager._update_task_status(
            job_id,
            "failed" if failed else "completed",
            message="部分候选需要处理，可保留成功项并重试" if failed else "修改候选已就绪",
            error_detail={"code": "course_change_candidate_failed", "retryable": True} if failed else None,
        )
    except asyncio.CancelledError:
        # The existing manager preserves pending on shutdown; persisted
        # candidates are reused by this exact job when the leader restarts.
        raise
    except Exception as error:
        failure_message = str(error)
        if not active():
            await manager._update_task_status(job_id, "cancelled", message="方案已修改或放弃")
            return

        def fail(current: CourseEvolutionState) -> CourseEvolutionState:
            plan = next(p for p in current.change_sets if p.change_set_id == plan_id)
            if plan.status == "pending" and plan.generation_job_id == job_id:
                plan.generation_status = "failed"
                plan.impact_summary["generation_error"] = failure_message
            return current

        repository.update(user_id, course_id, fail)
        await manager._update_task_status(
            job_id,
            "failed",
            message="修改候选生成失败，已保留完成项",
            error=str(error),
            error_detail={"code": "course_change_candidate_failed", "retryable": True},
        )


def reconcile_candidate_jobs(
    manager: Any, repository: CourseEvolutionRepository, user_id: str, course_id: str
) -> CourseEvolutionState:
    state = repository.load(user_id, course_id)
    stopped = {
        p.change_set_id: p.generation_job_id
        for p in state.change_sets
        if p.status == "pending"
        and p.generation_status == "generating"
        and p.generation_job_id
        and (manager.get_task(p.generation_job_id) or {}).get("status") not in {"pending", "running"}
    }
    if not stopped:
        return state

    def reconcile(current: CourseEvolutionState) -> CourseEvolutionState:
        for plan in current.change_sets:
            if (
                plan.status == "pending"
                and plan.generation_status == "generating"
                and stopped.get(plan.change_set_id) == plan.generation_job_id
            ):
                plan.generation_status = "failed"
                plan.impact_summary["generation_error"] = "生成任务已停止，已保存的候选仍可查看；可以继续生成剩余项。"
        return current

    return repository.update(user_id, course_id, reconcile)
