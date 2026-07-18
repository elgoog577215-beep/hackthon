"""Versioned formal-practice attempts, hints, grading, and history."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from assessment_tasks import project_assessment_task, resolve_assessment_task
from course_knowledge_map import project_learning_assets_to_knowledge
from course_learning_availability import (
    project_course_learning_availability,
    project_practice_availability,
)
from dependencies import get_course_or_404
from diagnostic_service import advance_workflow_after_grade, workflow_view
from diagnostic_workflows import WorkflowConflict, diagnostic_workflow_repository
from learner_context import require_user_id
from learning_events import load_learning_events, record_learning_event, summarize_text
from learning_asset_storage import learning_asset_repository
from learning_progress import project_learning_objective_bindings
from practice_attempts import (
    AttemptConflict,
    InvalidAttemptTransition,
    practice_attempt_repository,
)
from practice_grading import practice_grader
from question_bank import approved_formal_tasks, question_bank_repository
from storage import storage

router = APIRouter(prefix="/courses/{course_id}/practice", tags=["practice"])

logger = logging.getLogger(__name__)


class AttemptCreate(BaseModel):
    task_revision_id: str | None = None
    question_revision_id: str | None = None
    practice_run_id: str = ""
    attempt_id: str | None = None
    resume: bool = True
    origin_attempt_id: str | None = Field(default=None, max_length=200)
    practice_intent: Literal["standard", "targeted_retry", "unseen_validation"] = "standard"


class DraftUpdate(BaseModel):
    expected_revision: int = Field(ge=1)
    answer_payload: dict[str, Any] = Field(default_factory=dict)
    active_seconds: int = Field(default=0, ge=0, le=86400)


class RevisionAction(BaseModel):
    expected_revision: int = Field(ge=1)


class PracticeRefreshRequest(BaseModel):
    current_task_revision_id: str = Field(min_length=1, max_length=200)
    node_id: str | None = Field(default=None, max_length=200)
    scope: Literal["node", "final", "all"] = "node"


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
        "questions": [_student_question_payload(item) for item in questions],
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
    if payload.practice_intent == "unseen_validation":
        await _require_solution_validation_attempt(
            course,
            task,
            user_id=user_id,
            course_id=course_id,
            origin_attempt_id=payload.origin_attempt_id,
        )
    else:
        _require_current_workflow_task(course, task)
    if payload.practice_intent == "targeted_retry":
        if not payload.origin_attempt_id:
            raise HTTPException(status_code=422, detail="origin_attempt_id is required for targeted retry")
        try:
            origin_attempt = await run_in_threadpool(
                practice_attempt_repository.get,
                user_id,
                course_id,
                payload.origin_attempt_id,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Origin attempt not found") from exc
        if not _needs_review(origin_attempt):
            raise HTTPException(status_code=409, detail="Origin attempt is not eligible for targeted retry")
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
        "origin_attempt_id": payload.origin_attempt_id,
        "practice_intent": payload.practice_intent,
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
    return {
        "status": "created" if created else "resumed",
        "attempt": attempt,
        "solution": (
            _solution_payload(task)
            if attempt.get("solution_revealed")
            else None
        ),
    }


@router.post("/refresh")
async def refresh_practice_question(
    course_id: str,
    payload: PracticeRefreshRequest,
    request: Request,
):
    """Select another immutable approved task without regenerating in-session."""
    course = project_learning_objective_bindings(
        await get_course_or_404(course_id)
    )
    user_id = require_user_id(request.headers.get("X-User-Id"))
    questions = _questions(
        course,
        node_id=payload.node_id,
        scope=payload.scope,
    )
    current = next((
        item
        for item in questions
        if _task_revision_id(item) == payload.current_task_revision_id
    ), None)
    if not current:
        raise HTTPException(
            status_code=404,
            detail="Current task revision is not active in this course scope",
        )
    alternatives = [
        item
        for item in questions
        if _task_revision_id(item) != payload.current_task_revision_id
        and _normalized_question_prompt(item)
        != _normalized_question_prompt(current)
    ]
    if not alternatives:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "no_alternative_question",
                "message": "当前范围没有其他已冻结题目",
            },
        )
    attempts = await run_in_threadpool(
        practice_attempt_repository.list,
        user_id,
        course_id,
    )
    attempted_revision_ids = {
        str(
            item.get("task_revision_id")
            or item.get("question_revision_id")
            or ""
        )
        for item in attempts
    }
    current_level = str(current.get("practice_level") or "")
    ranked = sorted(
        enumerate(alternatives),
        key=lambda pair: (
            _task_revision_id(pair[1]) in attempted_revision_ids,
            str(pair[1].get("practice_level") or "") != current_level,
            pair[0],
        ),
    )
    selected = ranked[0][1]
    return {
        "status": "selected",
        "selection_policy": "frozen_course_question",
        "question": _student_question_payload(selected),
        "has_alternative": True,
        "attempt_history_preserved": True,
    }


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
    validation_task = _unseen_validation_task(course, attempt)
    return {
        "status": "revealed",
        "solution": _solution_payload(question or {}),
        "attempt": attempt,
        "validation_requirement": {
            "required": validation_task is not None,
            "status": "pending" if validation_task else "unavailable",
            "task_revision_id": (
                validation_task.get("task_revision_id")
                or validation_task.get("revision_id")
                if validation_task
                else None
            ),
            "practice_intent": "unseen_validation",
            "origin_attempt_id": attempt_id,
        },
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
    try:
        workflow = await run_in_threadpool(
            advance_workflow_after_grade,
            course,
            user_id=user_id,
            attempt=graded,
            task=question,
        )
    except WorkflowConflict:
        # Optimistic-lock conflict: the grade is already persisted (`graded` above), but the
        # workflow's version moved under us (e.g. a concurrent submission/abandon touched the
        # same case/session). advance_workflow_after_grade re-reads the workflow state from
        # scratch each call, so retrying once with the now-current revision resolves the vast
        # majority of conflicts. We must not let this become an unhandled 500: that would leave
        # the answer graded but the diagnostic workflow permanently stuck in "answered but never
        # judged", recoverable only via manual disagree/abandon.
        logger.warning(
            "workflow_conflict_on_grade_advance: retrying once user_id=%s course_id=%s attempt_id=%s",
            user_id, course_id, attempt_id,
        )
        try:
            workflow = await run_in_threadpool(
                advance_workflow_after_grade,
                course,
                user_id=user_id,
                attempt=graded,
                task=question,
            )
        except WorkflowConflict:
            # Still conflicting after one retry: give up advancing for this request rather than
            # retrying indefinitely. The grade itself is safely persisted; fall back to the
            # current workflow snapshot so the response is well-formed instead of a bare 500.
            # A subsequent request against the same attempt (already_submitted branch below)
            # will still see an unadvanced workflow, so log at error level for follow-up.
            logger.error(
                "workflow_conflict_on_grade_advance: retry also failed, workflow left unadvanced "
                "user_id=%s course_id=%s attempt_id=%s",
                user_id, course_id, attempt_id,
            )
            workflow = workflow_view(user_id, course_id, node_id=attempt.get("node_id"))
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
        bank_finals = _question_bank_final_tasks(course)
        if bank_finals or _has_active_question_bank(course):
            return bank_finals
        return [
            item
            for item in assets.get("final_assessment") or []
            if item.get("review_status") in {None, "approved"}
        ]
    questions = [
        *_question_bank_imported_tasks(course),
        *_question_bank_practice_overlay(
            course,
            assets.get("questions") or [],
        ),
    ]
    questions.extend(_question_bank_web_tasks(course))
    growth_task_ids = _course_evolution_practice_task_ids(course)
    questions.extend(
        item
        for item in assets.get("validation_questions") or []
        if str(item.get("revision_id") or item.get("task_revision_id") or "") in growth_task_ids
    )
    questions = _unique_revision_items(questions)
    if scope == "node" and node_id:
        questions = [item for item in questions if item.get("node_id") == node_id]
    return questions


def _student_question_payload(question: dict[str, Any]) -> dict[str, Any]:
    payload = dict(question)
    for field in (
        "answer_spec",
        "hint_contract",
        "question_spec",
        "grading_policy",
        "quality_report",
        "source_records",
    ):
        payload.pop(field, None)
    return payload


def _task_revision_id(question: dict[str, Any]) -> str:
    return str(
        question.get("task_revision_id")
        or question.get("revision_id")
        or ""
    )


def _normalized_question_prompt(question: dict[str, Any]) -> str:
    return " ".join(str(question.get("prompt") or "").split()).casefold()


def _find_question(course: dict[str, Any], revision_id: str) -> dict[str, Any] | None:
    assets = _learning_assets(course)
    legacy_finals = (
        []
        if _has_active_question_bank(course)
        else [
            item
            for item in assets.get("final_assessment") or []
            if item.get("review_status") in {None, "approved"}
        ]
    )
    return next((
        item for item in [
            *_question_bank_practice_overlay(
                course,
                assets.get("questions") or [],
            ),
            *_question_bank_imported_tasks(course),
            *_question_bank_web_tasks(course),
            *_question_bank_final_tasks(course),
            *legacy_finals,
        ]
        if item.get("revision_id") == revision_id
    ), None)


def _resolve_task(course: dict[str, Any], user_id: str, revision_id: str) -> dict[str, Any] | None:
    assets = _learning_assets(course)
    if revision_id in _course_evolution_practice_task_ids(course):
        growth_task = next((
            item
            for item in assets.get("validation_questions") or []
            if str(item.get("revision_id") or item.get("task_revision_id") or "") == revision_id
        ), None)
        if growth_task:
            return project_assessment_task(
                growth_task,
                purpose="course_practice",
                source="course_evolution",
            )
    course_with_assets = {
        **course,
        "learning_assets": _raw_learning_assets(course),
    }
    bank_finals = _question_bank_final_tasks(course)
    if _has_active_question_bank(course):
        course_with_assets["learning_assets"] = {
            **course_with_assets["learning_assets"],
            "questions": [
                *_question_bank_imported_tasks(course),
                *_question_bank_practice_overlay(
                    course,
                    course_with_assets["learning_assets"].get("questions") or [],
                ),
                *_question_bank_web_tasks(course),
            ],
            "final_assessment": bank_finals,
        }
    return resolve_assessment_task(
        course_with_assets,
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
        _raw_learning_assets(course),
    )


def _raw_learning_assets(course: dict[str, Any]) -> dict[str, Any]:
    course_id = str(course.get("course_id") or "")
    bundle = learning_asset_repository.load_bundle(course_id) if course_id else None
    assets = bundle.get("assets") if isinstance(bundle, dict) else None
    return assets if isinstance(assets, dict) else (course.get("learning_assets") or {})


def _question_bank_final_tasks(course: dict[str, Any]) -> list[dict[str, Any]]:
    course_id = str(course.get("course_id") or "")
    bundle = question_bank_repository.load_bundle(course_id) if course_id else None
    if not bundle:
        return []
    return [
        *approved_formal_tasks(bundle, assessment_role="coverage_task"),
        *approved_formal_tasks(bundle, assessment_role="cross_chapter_transfer"),
    ]


def _unseen_validation_task(
    course: dict[str, Any],
    attempt: dict[str, Any],
) -> dict[str, Any] | None:
    node_id = str(attempt.get("node_id") or "")
    original_revision = str(
        attempt.get("task_revision_id")
        or attempt.get("question_revision_id")
        or ""
    )
    return next(
        (
            project_assessment_task(
                item,
                purpose="remediation_validation",
                source="course_asset_reserve",
            )
            for item in _learning_assets(course).get("validation_questions") or []
            if str(item.get("node_id") or "") == node_id
            and str(item.get("revision_id") or "") != original_revision
            and item.get("quality_status") == "passed"
        ),
        None,
    )


async def _require_solution_validation_attempt(
    course: dict[str, Any],
    task: dict[str, Any],
    *,
    user_id: str,
    course_id: str,
    origin_attempt_id: str | None,
) -> None:
    if not origin_attempt_id:
        raise HTTPException(
            status_code=422,
            detail="origin_attempt_id is required for unseen validation",
        )
    try:
        origin = await run_in_threadpool(
            practice_attempt_repository.get,
            user_id,
            course_id,
            origin_attempt_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Origin attempt not found") from exc
    if not origin.get("solution_revealed"):
        raise HTTPException(
            status_code=409,
            detail="Origin attempt has not revealed a solution",
        )
    expected = _unseen_validation_task(course, origin)
    expected_revision = str(
        (expected or {}).get("task_revision_id")
        or (expected or {}).get("revision_id")
        or ""
    )
    if (
        not expected_revision
        or expected_revision != str(task.get("task_revision_id") or "")
    ):
        raise HTTPException(
            status_code=409,
            detail="Task is not the required unseen validation",
        )


def _has_active_question_bank(course: dict[str, Any]) -> bool:
    course_id = str(course.get("course_id") or "")
    return bool(course_id and question_bank_repository.load_bundle(course_id))


def _question_bank_web_tasks(course: dict[str, Any]) -> list[dict[str, Any]]:
    course_id = str(course.get("course_id") or "")
    bundle = question_bank_repository.load_bundle(course_id) if course_id else None
    if not bundle:
        return []
    return approved_formal_tasks(bundle, assessment_role="web_enriched_practice")


def _question_bank_imported_tasks(course: dict[str, Any]) -> list[dict[str, Any]]:
    course_id = str(course.get("course_id") or "")
    bundle = question_bank_repository.load_bundle(course_id) if course_id else None
    if not bundle:
        return []
    return approved_formal_tasks(bundle, assessment_role="imported_practice")


def _question_bank_practice_tasks(course: dict[str, Any]) -> list[dict[str, Any]]:
    course_id = str(course.get("course_id") or "")
    bundle = question_bank_repository.load_bundle(course_id) if course_id else None
    if not bundle:
        return []
    return approved_formal_tasks(bundle, assessment_role="practice")


def _question_bank_practice_overlay(
    course: dict[str, Any],
    asset_questions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Prefer bank-backed compiled tasks and replace stale template peers."""
    bank_tasks = _question_bank_practice_tasks(course)
    if not bank_tasks:
        return [] if _has_active_question_bank(course) else list(asset_questions)

    assets_by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for question in asset_questions:
        key = (
            str(question.get("node_id") or ""),
            str(question.get("practice_level") or ""),
        )
        assets_by_key.setdefault(key, []).append(question)

    result: list[dict[str, Any]] = []
    for bank_task in bank_tasks:
        key = (
            str(bank_task.get("node_id") or ""),
            str(bank_task.get("practice_level") or ""),
        )
        bank_item_revision = str(
            bank_task.get("question_bank_item_revision_id") or ""
        )
        compiled = next(
            (
                question
                for question in assets_by_key.get(key) or []
                if bank_item_revision
                and str(
                    question.get("question_bank_item_revision_id") or ""
                )
                == bank_item_revision
            ),
            None,
        )
        result.append(compiled or bank_task)

    return _unique_revision_items(result)


def _course_evolution_practice_task_ids(course: dict[str, Any]) -> set[str]:
    document = course.get("course_document") or {}
    task_ids: set[str] = set()
    for block in document.get("blocks") or []:
        if not isinstance(block, dict) or block.get("status") == "retired":
            continue
        payload = block.get("payload") or {}
        if not isinstance(payload, dict) or not isinstance(payload.get("course_evolution"), dict):
            continue
        revision_ids = [
            payload.get("practice_task_id"),
            *(payload.get("validation_task_ids") or []),
        ]
        task_ids.update(
            str(revision_id).strip()
            for revision_id in revision_ids
            if str(revision_id or "").strip()
        )
    return task_ids


def _unique_revision_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        revision_id = str(item.get("revision_id") or item.get("task_revision_id") or "")
        if not revision_id or revision_id in seen:
            continue
        seen.add(revision_id)
        result.append(item)
    return result


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
            "origin_attempt_id": attempt.get("origin_attempt_id"),
            "practice_intent": attempt.get("practice_intent") or "standard",
        },
    )


def _solution_payload(question: dict[str, Any]) -> dict[str, Any]:
    spec = question.get("answer_spec") or {}
    structured = spec.get("solution_spec") or {}
    final_answer = (
        structured["final_answer"]
        if "final_answer" in structured
        else spec.get("canonical_answer")
    )
    if final_answer is None:
        final_answer = spec.get("correct_answer")
    steps = structured.get("steps") or spec.get("solution_trace") or []
    checks = (
        structured.get("checks")
        or question.get("result_checks")
        or spec.get("criteria")
        or []
    )
    summary = str(
        structured.get("summary")
        or question.get("explanation")
        or "对照标准步骤、最终答案和结果检查，定位本次作答缺失的证据。"
    )
    return {
        "schema_version": "solution_spec_v1",
        "summary": summary,
        "steps": steps,
        "final_answer": final_answer,
        "checks": checks,
        "representation": structured.get("representation"),
        "criteria": spec.get("criteria") or [],
        "reference_concepts": spec.get("expected_keywords") or [],
        "correct_answer": spec.get("correct_answer"),
        "guidance": summary,
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
