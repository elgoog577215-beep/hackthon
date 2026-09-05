"""Whole-course candidates on the existing TaskManager queue and journal."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from .core import CourseEvolutionPlan, CourseEvolutionRepository, CourseEvolutionState, course_evolution_repository
from .teacher_execution import generate_teacher_course_change_candidates

TASK_TYPE = "teacher_course_change_generation"


async def enqueue_candidates(*, manager: Any, service: Any, user_id: str, course_id: str, plan_id: str) -> Any:
    repository = service.evolution_repository
    async with manager._creation_lock:
        state = repository.load(user_id, course_id)
        plan = next((p for p in state.change_sets if p.change_set_id == plan_id), None)
        if plan is None:
            raise KeyError(plan_id)
        if plan.status != "pending" or not plan.impact_summary.get("scope_review"):
            raise ValueError("请先确认当前方案的影响范围")
        existing = manager.get_task(plan.generation_job_id) if plan.generation_job_id else None
        if (
            existing
            and existing.get("status") in {"pending", "running"}
            and (existing.get("request_snapshot") or {}).get("review_revision") == plan.review_revision
        ):
            return state
        job_id = f"course-change-{uuid.uuid4().hex}"
        review_revision = plan.review_revision
        await manager.create_task(
            course_id,
            TASK_TYPE,
            task_id=job_id,
            enqueue=False,
            request_snapshot={"plan_id": plan_id, "review_revision": review_revision, "_retrieval_actor_id": user_id},
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
