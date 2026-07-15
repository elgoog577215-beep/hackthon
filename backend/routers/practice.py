"""Versioned formal-practice attempts, hints, grading, and history."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from assessment_tasks import resolve_assessment_task
from course_knowledge_map import project_learning_assets_to_knowledge
from course_learning_availability import (
    project_course_learning_availability,
    project_practice_availability,
)
from dependencies import get_course_or_404
from diagnostic_service import advance_workflow_after_grade, workflow_view
from diagnostic_workflows import diagnostic_workflow_repository
from learner_context import require_user_id
from learning_events import load_learning_events, record_learning_event, summarize_text
from learning_progress import project_learning_objective_bindings
from practice_attempts import (
    AttemptConflict,
    InvalidAttemptTransition,
    practice_attempt_repository,
)
from practice_grading import practice_grader
from storage import storage

router = APIRouter(prefix="/courses/{course_id}/practice", tags=["practice"])


class AttemptCreate(BaseModel):
    task_revision_id: str | None = None
    question_revision_id: str | None = None
    practice_run_id: str = ""
    attempt_id: str | None = None
    resume: bool = True


class DraftUpdate(BaseModel):
    expected_revision: int = Field(ge=1)
    answer_payload: dict[str, Any] = Field(default_factory=dict)
    active_seconds: int = Field(default=0, ge=0, le=86400)


class RevisionAction(BaseModel):
    expected_revision: int = Field(ge=1)


class AISupportAction(RevisionAction):
    level: int = Field(ge=1, le=3)
    summary: str = Field(default="", max_length=1000)


class AttemptSubmission(DraftUpdate):
    request_id: str = Field(min_length=8, max_length=200)


class LegacyPracticeData(BaseModel):
    wrong_answers: list[dict[str, Any]] = Field(default_factory=list, max_length=500)
    quiz_history: list[dict[str, Any]] = Field(default_factory=list, max_length=500)


@router.get("")
async def get_practice(
    course_id: str,
    request: Request,
    node_id: str | None = None,
    scope: Literal["node", "final", "all"] = "node",
):
    course = project_learning_objective_bindings(await get_course_or_404(course_id))
    user_id = require_user_id(request.headers.get("X-User-Id"))
    questions = _questions(course, node_id=node_id, scope=scope)
    attempts = await run_in_threadpool(practice_attempt_repository.list, user_id, course_id)
    return {
        "schema_version": "formal_practice_api_v1",
        "course_id": course_id,
        "course_version_id": course.get("current_course_version_id"),
        "node_id": node_id,
        "scope": scope,
        "course_availability": project_course_learning_availability(course),
        "practice_availability": project_practice_availability(
            course,
            scope=scope,
            node_id=node_id,
            scoped_question_count=len(questions),
        ),
        "questions": questions,
        "active_attempts": [item for item in attempts if item.get("status") == "in_progress"],
        "summary": _attempt_summary(attempts),
    }


@router.get("/history")
async def get_practice_history(
    course_id: str,
    request: Request,
    node_id: str | None = None,
    view: Literal["all", "needs_review", "legacy"] = "all",
):
    user_id = require_user_id(request.headers.get("X-User-Id"))
    course = await get_course_or_404(course_id)
    attempts = await run_in_threadpool(practice_attempt_repository.list, user_id, course_id)
    if node_id:
        attempts = [item for item in attempts if item.get("node_id") == node_id]
    if view == "needs_review":
        attempts = [item for item in attempts if _needs_review(item)]
    legacy = []
    if view in {"all", "legacy"}:
        legacy = [
            event for event in load_learning_events(user_id=user_id, course_id=course_id)
            if event.get("event_type") == "legacy_practice_imported"
        ]
    if view == "legacy":
        attempts = []
    return {
        "course_id": course_id,
        "view": view,
        "attempts": list(reversed(attempts)),
        "legacy_events": list(reversed(legacy)),
        "summary": _attempt_summary(attempts),
    }


@router.post("/attempts")
async def create_attempt(course_id: str, payload: AttemptCreate, request: Request):
    course = project_learning_objective_bindings(await get_course_or_404(course_id))
    user_id = require_user_id(request.headers.get("X-User-Id"))
    revision_id = str(payload.task_revision_id or payload.question_revision_id or "")
    if not revision_id:
        raise HTTPException(status_code=422, detail="task_revision_id is required")
    task = _resolve_task(course, user_id, revision_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task revision not found in current course version")
    _require_current_workflow_task(course, task)
    criterion = _criterion_for_task(course, task)
    data = {
        "attempt_id": payload.attempt_id,
        "practice_run_id": payload.practice_run_id,
        "resume": payload.resume,
        "practice_level": task.get("practice_level"),
        "task_revision_id": revision_id,
        "task_purpose": task.get("task_purpose") or "course_practice",
        "task_source": task.get("task_source") or "course_asset",
        "course_version_id": course.get("current_course_version_id"),
        "node_id": task.get("node_id"),
        "node_name": _node_name(course, task.get("node_id")),
        "objective_id": task.get("objective_id"),
        "objective_revision_id": task.get("objective_revision_id"),
        "criterion_id": (criterion or {}).get("criterion_id"),
        "criterion_revision_id": (criterion or {}).get("revision_id"),
        "question_revision_id": revision_id,
        "question_type": task.get("question_type"),
        "input_contract": task.get("input_contract") or {},
        "concept_ids": task.get("concept_ids") or [],
        "skill_unit_ids": task.get("skill_unit_ids") or [],
        "mistake_point_ids": task.get("mistake_point_ids") or [],
        "improvement_point_ids": task.get("improvement_point_ids") or [],
        "diagnostic_case_id": task.get("diagnostic_case_id"),
        "remediation_session_id": task.get("remediation_session_id"),
    }
    attempt, created = await run_in_threadpool(
        practice_attempt_repository.create_once,
        user_id,
        course_id,
        data,
    )
    if created:
        _record_attempt_event("practice_attempt_started", attempt, user_id=user_id)
    return {"status": "created" if created else "resumed", "attempt": attempt}


@router.get("/attempts/active")
async def get_active_attempt(
    course_id: str,
    request: Request,
    task_revision_id: str | None = Query(default=None, min_length=1),
    question_revision_id: str | None = Query(default=None, min_length=1),
):
    revision_id = str(task_revision_id or question_revision_id or "")
    if not revision_id:
        raise HTTPException(status_code=422, detail="task_revision_id is required")
    user_id = require_user_id(request.headers.get("X-User-Id"))
    attempts = await run_in_threadpool(practice_attempt_repository.list, user_id, course_id)
    active = next((
        item for item in reversed(attempts)
        if str(item.get("task_revision_id") or item.get("question_revision_id") or "") == revision_id
        and item.get("status") == "in_progress"
    ), None)
    return {"attempt": active}


@router.patch("/attempts/{attempt_id}/draft")
async def update_attempt_draft(
    course_id: str,
    attempt_id: str,
    payload: DraftUpdate,
    request: Request,
):
    user_id = require_user_id(request.headers.get("X-User-Id"))
    try:
        attempt = await run_in_threadpool(
            practice_attempt_repository.update_draft,
            user_id,
            course_id,
            attempt_id,
            expected_revision=payload.expected_revision,
            answer_payload=payload.answer_payload,
            active_seconds=payload.active_seconds,
        )
    except AttemptConflict as exc:
        raise HTTPException(status_code=409, detail={"code": "attempt_conflict", "current": exc.current}) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Attempt not found") from exc
    except InvalidAttemptTransition as exc:
        raise HTTPException(status_code=409, detail="Attempt is no longer editable") from exc
    return {"status": "saved", "attempt": attempt}


@router.post("/attempts/{attempt_id}/hints/{level}")
async def reveal_attempt_hint(
    course_id: str,
    attempt_id: str,
    level: int,
    payload: RevisionAction,
    request: Request,
):
    course = project_learning_objective_bindings(await get_course_or_404(course_id))
    user_id = require_user_id(request.headers.get("X-User-Id"))
    try:
        current = await run_in_threadpool(practice_attempt_repository.get, user_id, course_id, attempt_id)
        question = _resolve_task(course, user_id, str(current.get("task_revision_id") or current.get("question_revision_id") or ""))
        if not question:
            raise HTTPException(status_code=409, detail="Task revision is no longer active")
        hint = next((
            item for item in ((question.get("hint_contract") or {}).get("levels") or [])
            if int(item.get("level") or 0) == level
        ), None)
        if not hint:
            raise HTTPException(status_code=404, detail="Hint level not found")
        attempt, created = await run_in_threadpool(
            practice_attempt_repository.reveal_hint,
            user_id,
            course_id,
            attempt_id,
            expected_revision=payload.expected_revision,
            level=level,
        )
    except AttemptConflict as exc:
        raise HTTPException(status_code=409, detail={"code": "attempt_conflict", "current": exc.current}) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Attempt not found") from exc
    except (ValueError, InvalidAttemptTransition) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if created:
        _record_attempt_event(
            "practice_hint_revealed",
            attempt,
            user_id=user_id,
            evidence={"level": level, "kind": hint.get("kind")},
        )
    return {"status": "revealed", "hint": hint, "attempt": attempt}


@router.post("/attempts/{attempt_id}/ai-support")
async def record_attempt_ai_support(
    course_id: str,
    attempt_id: str,
    payload: AISupportAction,
    request: Request,
):
    user_id = require_user_id(request.headers.get("X-User-Id"))
    try:
        attempt = await run_in_threadpool(
            practice_attempt_repository.record_ai_support,
            user_id,
            course_id,
            attempt_id,
            expected_revision=payload.expected_revision,
            level=payload.level,
        )
    except AttemptConflict as exc:
        raise HTTPException(status_code=409, detail={"code": "attempt_conflict", "current": exc.current}) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Attempt not found") from exc
    except (ValueError, InvalidAttemptTransition) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _record_attempt_event(
        "practice_ai_support_used",
        attempt,
        user_id=user_id,
        evidence={"level": payload.level, "summary": summarize_text(payload.summary)},
    )
    return {"status": "recorded", "attempt": attempt}


@router.post("/attempts/{attempt_id}/solution")
async def reveal_attempt_solution(
    course_id: str,
    attempt_id: str,
    payload: RevisionAction,
    request: Request,
):
    course = project_learning_objective_bindings(await get_course_or_404(course_id))
    user_id = require_user_id(request.headers.get("X-User-Id"))
    current = await run_in_threadpool(practice_attempt_repository.get, user_id, course_id, attempt_id)
    if current.get("status") == "in_progress" and int(current.get("attempt_number") or 1) < 2:
        raise HTTPException(status_code=409, detail="Complete one submission before revealing the full solution")
    question = _resolve_task(course, user_id, str(current.get("task_revision_id") or current.get("question_revision_id") or ""))
    try:
        attempt, created = await run_in_threadpool(
            practice_attempt_repository.reveal_solution,
            user_id,
            course_id,
            attempt_id,
            expected_revision=payload.expected_revision,
        )
    except AttemptConflict as exc:
        raise HTTPException(status_code=409, detail={"code": "attempt_conflict", "current": exc.current}) from exc
    if created:
        _record_attempt_event("practice_solution_revealed", attempt, user_id=user_id)
    return {
        "status": "revealed",
        "solution": _solution_payload(question or {}),
        "attempt": attempt,
    }


@router.post("/attempts/{attempt_id}/abandon")
async def abandon_attempt(
    course_id: str,
    attempt_id: str,
    payload: RevisionAction,
    request: Request,
):
    user_id = require_user_id(request.headers.get("X-User-Id"))
    try:
        attempt = await run_in_threadpool(
            practice_attempt_repository.abandon,
            user_id,
            course_id,
            attempt_id,
            expected_revision=payload.expected_revision,
        )
    except AttemptConflict as exc:
        raise HTTPException(status_code=409, detail={"code": "attempt_conflict", "current": exc.current}) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Attempt not found") from exc
    except InvalidAttemptTransition as exc:
        raise HTTPException(status_code=409, detail="Attempt is no longer editable") from exc
    _record_attempt_event("practice_attempt_abandoned", attempt, user_id=user_id)
    return {"status": "abandoned", "attempt": attempt}


@router.post("/attempts/{attempt_id}/submit")
async def submit_attempt(
    course_id: str,
    attempt_id: str,
    payload: AttemptSubmission,
    request: Request,
):
    course = project_learning_objective_bindings(await get_course_or_404(course_id))
    user_id = require_user_id(request.headers.get("X-User-Id"))
    current = await run_in_threadpool(practice_attempt_repository.get, user_id, course_id, attempt_id)
    question = _resolve_task(course, user_id, str(current.get("task_revision_id") or current.get("question_revision_id") or ""))
    if not question:
        invalidated, created = await run_in_threadpool(
            practice_attempt_repository.invalidate,
            user_id,
            course_id,
            attempt_id,
            reason="task_revision_not_active",
        )
        if created:
            _record_attempt_event("practice_attempt_invalidated", invalidated, user_id=user_id)
        raise HTTPException(status_code=409, detail={"code": "task_revision_invalidated", "attempt": invalidated})
    if not _has_answer(payload.answer_payload):
        raise HTTPException(status_code=422, detail="Answer payload is empty")
    try:
        attempt, submitted = await run_in_threadpool(
            practice_attempt_repository.submit,
            user_id,
            course_id,
            attempt_id,
            expected_revision=payload.expected_revision,
            request_id=payload.request_id,
            answer_payload=payload.answer_payload,
            active_seconds=payload.active_seconds,
        )
    except AttemptConflict as exc:
        raise HTTPException(status_code=409, detail={"code": "attempt_conflict", "current": exc.current}) from exc
    except InvalidAttemptTransition as exc:
        raise HTTPException(status_code=409, detail="Attempt cannot be submitted") from exc
    if not submitted and attempt.get("result"):
        return {
            "status": "already_submitted",
            "attempt": attempt,
            "result": attempt.get("result"),
            "workflow": workflow_view(user_id, course_id, node_id=attempt.get("node_id")),
        }
    if submitted:
        _record_attempt_event(
            "practice_attempt_submitted",
            attempt,
            user_id=user_id,
            evidence={
                "answer": payload.answer_payload,
                "active_seconds": payload.active_seconds,
                "support_level": _support_level(attempt),
            },
        )
    try:
        result = await practice_grader.grade(question, attempt)
    except Exception:
        result = {
            "status": "pending_review",
            "score": None,
            "passed": None,
            "rubric_results": [],
            "feedback": "自动评阅暂时中断，答案已保存并进入待评阅",
            "grading_confidence": 0.0,
            "grading_method": "rubric_ai",
            "mastery_eligible": False,
        }
    graded = await run_in_threadpool(
        practice_attempt_repository.apply_grade,
        user_id,
        course_id,
        attempt_id,
        expected_revision=int(attempt.get("revision") or 0),
        result=result,
    )
    event_type = "practice_grading_requested" if graded.get("status") == "grading" else "practice_attempt_graded"
    _record_attempt_event(event_type, graded, user_id=user_id, result=result)
    workflow = await run_in_threadpool(
        advance_workflow_after_grade,
        course,
        user_id=user_id,
        attempt=graded,
        task=question,
    )
    return {
        "status": "pending_review" if graded.get("status") == "grading" else "graded",
        "attempt": graded,
        "result": result,
        "workflow": workflow,
    }


@router.post("/migrate-legacy")
async def migrate_legacy_practice(
    course_id: str,
    payload: LegacyPracticeData,
    request: Request,
):
    course = await get_course_or_404(course_id)
    user_id = require_user_id(request.headers.get("X-User-Id"))
    existing = {
        str((event.get("metadata") or {}).get("migration_key") or "")
        for event in load_learning_events(user_id=user_id, course_id=course_id)
        if event.get("event_type") == "legacy_practice_imported"
    }
    node_ids = {str(item.get("node_id") or "") for item in course.get("nodes") or []}
    created_keys: list[str] = []
    skipped = 0
    for kind, items in (("wrong_answer", payload.wrong_answers), ("quiz_history", payload.quiz_history)):
        for item in items:
            node_id = str(item.get("nodeId") or item.get("node_id") or "")
            if node_id and node_id not in node_ids:
                skipped += 1
                continue
            key = _legacy_key(user_id, course_id, kind, item)
            if key in existing:
                continue
            record_learning_event(
                event_type="legacy_practice_imported",
                actor="migration",
                source="legacy.frontend.localStorage",
                user_id=user_id,
                course_id=course_id,
                course_version_id=course.get("current_course_version_id"),
                node_id=node_id or None,
                node_name=str(item.get("nodeName") or item.get("node_name") or ""),
                evidence={"kind": kind, "legacy_payload": item, "confidence": "low"},
                result={"historical_only": True, "mastery_eligible": False},
                metadata={"migration_key": key},
            )
            existing.add(key)
            created_keys.append(key)
    return {"status": "migrated", "created": len(created_keys), "created_keys": created_keys, "skipped": skipped}


def _questions(course: dict[str, Any], *, node_id: str | None, scope: str) -> list[dict[str, Any]]:
    assets = _learning_assets(course)
    if scope == "final":
        return list(assets.get("final_assessment") or [])
    questions = list(assets.get("questions") or [])
    if scope == "node" and node_id:
        questions = [item for item in questions if item.get("node_id") == node_id]
    return questions


def _find_question(course: dict[str, Any], revision_id: str) -> dict[str, Any] | None:
    assets = _learning_assets(course)
    return next((
        item for item in [*(assets.get("questions") or []), *(assets.get("final_assessment") or [])]
        if item.get("revision_id") == revision_id
    ), None)


def _resolve_task(course: dict[str, Any], user_id: str, revision_id: str) -> dict[str, Any] | None:
    return resolve_assessment_task(
        course,
        revision_id,
        extra_tasks=diagnostic_workflow_repository.all_tasks(user_id, str(course.get("course_id") or "")),
    )


def _require_current_workflow_task(course: dict[str, Any], task: dict[str, Any]) -> None:
    if task.get("task_purpose") == "course_practice":
        return
    if not task.get("diagnostic_case_id"):
        raise HTTPException(status_code=409, detail={"code": "diagnostic_workflow_not_started"})
    if task.get("course_version_id") and task.get("course_version_id") != course.get("current_course_version_id"):
        raise HTTPException(status_code=409, detail={"code": "diagnostic_workflow_stale"})


def _criterion_for_task(course: dict[str, Any], task: dict[str, Any]) -> dict[str, Any] | None:
    if task.get("task_purpose") == "course_practice":
        return _criterion_for_question(course, str(task.get("task_revision_id") or task.get("revision_id") or ""))
    return next((
        item for item in _learning_assets(course).get("mastery_criteria") or []
        if (
            item.get("objective_revision_id") == task.get("objective_revision_id")
            if task.get("objective_revision_id")
            else item.get("node_id") == task.get("node_id")
        )
    ), None)


def _criterion_for_question(course: dict[str, Any], revision_id: str) -> dict[str, Any] | None:
    return next((
        item for item in _learning_assets(course).get("mastery_criteria") or []
        if revision_id in (item.get("assessment_bindings") or [])
    ), None)


def _learning_assets(course: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    return project_learning_assets_to_knowledge(
        course,
        course.get("learning_assets") or {},
    )


def _node_name(course: dict[str, Any], node_id: Any) -> str:
    return str(next((
        item.get("node_name") for item in course.get("nodes") or [] if item.get("node_id") == node_id
    ), "") or "")


def _record_attempt_event(
    event_type: str,
    attempt: dict[str, Any],
    *,
    user_id: str,
    evidence: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return record_learning_event(
        event_type=event_type,
        actor="user" if event_type not in {"practice_attempt_graded", "practice_grading_requested", "practice_attempt_invalidated"} else "system",
        source="practice.attempts",
        user_id=user_id,
        course_id=attempt.get("course_id"),
        course_version_id=attempt.get("course_version_id"),
        node_id=attempt.get("node_id"),
        node_name=str(attempt.get("node_name") or ""),
        objective_id=attempt.get("objective_id"),
        objective_revision_id=attempt.get("objective_revision_id"),
        concept_ids=attempt.get("concept_ids") or [],
        skill_unit_ids=attempt.get("skill_unit_ids") or [],
        mistake_point_ids=attempt.get("mistake_point_ids") or [],
        improvement_point_ids=attempt.get("improvement_point_ids") or [],
        question_revision_id=attempt.get("question_revision_id"),
        task_revision_id=attempt.get("task_revision_id") or attempt.get("question_revision_id"),
        task_purpose=attempt.get("task_purpose"),
        criterion_id=attempt.get("criterion_id"),
        criterion_revision_id=attempt.get("criterion_revision_id"),
        attempt_id=attempt.get("attempt_id"),
        diagnostic_case_id=attempt.get("diagnostic_case_id"),
        remediation_session_id=attempt.get("remediation_session_id"),
        operation_id=f"attempt:{attempt.get('attempt_id')}:{attempt.get('revision')}:{event_type}",
        idempotency_key=f"{event_type}:{attempt.get('attempt_id')}:{attempt.get('revision')}",
        entity_type="practice_attempt",
        entity_id=attempt.get("attempt_id"),
        entity_revision=attempt.get("revision"),
        evidence=evidence or {},
        result=result or {},
        metadata={
            "practice_level": attempt.get("practice_level"),
            "attempt_number": attempt.get("attempt_number"),
            "task_revision_id": attempt.get("task_revision_id"),
            "task_purpose": attempt.get("task_purpose"),
            "diagnostic_case_id": attempt.get("diagnostic_case_id"),
            "remediation_session_id": attempt.get("remediation_session_id"),
        },
    )


def _solution_payload(question: dict[str, Any]) -> dict[str, Any]:
    spec = question.get("answer_spec") or {}
    return {
        "criteria": spec.get("criteria") or [],
        "reference_concepts": spec.get("expected_keywords") or [],
        "correct_answer": spec.get("correct_answer"),
        "guidance": "对照评分维度检查条件、过程、结论和验证是否完整。",
    }


def _has_answer(payload: dict[str, Any]) -> bool:
    return any(value not in (None, "", [], {}) for value in payload.values())


def _support_level(attempt: dict[str, Any]) -> int:
    return max([
        0,
        int(attempt.get("ai_support_level") or 0),
        *[int(item) for item in attempt.get("revealed_hint_levels") or []],
        3 if attempt.get("solution_revealed") else 0,
    ])


def _needs_review(attempt: dict[str, Any]) -> bool:
    result = attempt.get("result") or {}
    return attempt.get("status") == "grading" or result.get("passed") is False or result.get("mastery_eligible") is False


def _attempt_summary(attempts: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total": len(attempts),
        "in_progress": sum(item.get("status") == "in_progress" for item in attempts),
        "graded": sum(item.get("status") == "graded" for item in attempts),
        "pending_review": sum(item.get("status") == "grading" for item in attempts),
        "needs_review": sum(_needs_review(item) for item in attempts),
    }


def _legacy_key(user_id: str, course_id: str, kind: str, item: dict[str, Any]) -> str:
    raw = json.dumps({
        "user_id": user_id,
        "course_id": course_id,
        "kind": kind,
        "node_id": item.get("nodeId") or item.get("node_id"),
        "question": item.get("question"),
        "timestamp": item.get("timestamp"),
    }, ensure_ascii=False, sort_keys=True)
    return f"legacy_practice:{hashlib.sha256(raw.encode('utf-8')).hexdigest()}"


__all__ = ["router"]
