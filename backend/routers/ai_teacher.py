"""AI-teacher conversations, action proposals, receipts, and trigger coordination."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from ai_teacher_actions import (
    ActionForbidden,
    ProposalStale,
    build_trigger_candidate,
    execute_proposal,
    propose_action,
    reject_proposal,
    undo_receipt,
)
from ai_teacher_state import ai_teacher_repository
from dependencies import get_course_or_404
from learner_context import require_user_id
from learning_events import load_learning_events, record_learning_event, summarize_text


router = APIRouter(prefix="/api/ai-teacher", tags=["ai_teacher"])


class ConversationCreate(BaseModel):
    course_id: str = Field(min_length=1, max_length=160)
    title: str = Field(default="", max_length=200)
    conversation_id: str | None = Field(default=None, max_length=160)


class ProposalCreate(BaseModel):
    course_id: str = Field(min_length=1, max_length=160)
    conversation_id: str = Field(default="", max_length=160)
    message_id: str = Field(default="", max_length=160)
    action_type: Literal[
        "create_note",
        "create_issue",
        "create_review_task",
        "create_bookmark",
        "open_runtime_action",
    ]
    target_ref: dict[str, Any] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(default="", max_length=1000)
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list, max_length=20)
    confirmation_mode: Literal["explicit", "user_command"] = "explicit"
    origin: Literal["assistant", "user_command", "user_click"] = "assistant"


class ProposalConfirm(BaseModel):
    course_id: str = Field(min_length=1, max_length=160)
    idempotency_key: str = Field(min_length=8, max_length=200)


class ProposalReject(BaseModel):
    course_id: str = Field(min_length=1, max_length=160)
    reason: Literal["not_now", "irrelevant", "already_done", "never"] = "not_now"


class ReceiptUndo(BaseModel):
    course_id: str = Field(min_length=1, max_length=160)
    idempotency_key: str = Field(min_length=8, max_length=200)


class AnswerFeedbackCreate(BaseModel):
    course_id: str = Field(min_length=1, max_length=160)
    feedback: Literal["resolved", "unclear"]
    node_id: str = Field(default="", max_length=160)
    node_name: str = Field(default="", max_length=500)
    action: Literal["explain", "example", "simplify", "ask"]
    content_anchor: dict[str, Any] = Field(default_factory=dict)


@router.get("/conversations")
async def list_conversations(
    request: Request,
    course_id: str = Query(min_length=1, max_length=160),
):
    await get_course_or_404(course_id)
    user_id = require_user_id(request.headers.get("X-User-Id"))
    conversations = await run_in_threadpool(
        ai_teacher_repository.list_conversations,
        user_id,
        course_id,
    )
    return {"course_id": course_id, "conversations": conversations}


@router.post("/conversations")
async def create_conversation(payload: ConversationCreate, request: Request):
    course = await get_course_or_404(payload.course_id)
    user_id = require_user_id(request.headers.get("X-User-Id"))
    conversation = await run_in_threadpool(
        ai_teacher_repository.create_conversation,
        user_id,
        payload.course_id,
        title=payload.title,
        course_version_id=str(course.get("current_course_version_id") or ""),
        conversation_id=payload.conversation_id,
    )
    return conversation


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    request: Request,
    course_id: str = Query(min_length=1, max_length=160),
):
    await get_course_or_404(course_id)
    user_id = require_user_id(request.headers.get("X-User-Id"))
    conversation = await run_in_threadpool(
        ai_teacher_repository.get_conversation,
        user_id,
        course_id,
        conversation_id,
    )
    if not conversation:
        raise HTTPException(status_code=404, detail="AI conversation not found")
    return conversation


@router.post("/conversations/{conversation_id}/messages/{message_id}/feedback")
async def record_answer_feedback(
    conversation_id: str,
    message_id: str,
    payload: AnswerFeedbackCreate,
    request: Request,
):
    course = await get_course_or_404(payload.course_id)
    user_id = require_user_id(request.headers.get("X-User-Id"))
    conversation = await run_in_threadpool(
        ai_teacher_repository.get_conversation,
        user_id,
        payload.course_id,
        conversation_id,
    )
    if not conversation:
        raise HTTPException(status_code=404, detail="AI conversation not found")
    message = next((
        item for item in conversation.get("messages") or []
        if item.get("message_id") == message_id
    ), None)
    if not message:
        raise HTTPException(status_code=404, detail="AI message not found")
    if message.get("role") != "assistant" or message.get("status") != "complete":
        raise HTTPException(status_code=409, detail="Only completed assistant messages accept feedback")

    existing = next((
        event for event in reversed(await run_in_threadpool(
            load_learning_events,
            user_id=user_id,
            course_id=payload.course_id,
            event_type="assistant_answer_feedback_submitted",
        ))
        if str((event.get("metadata") or {}).get("message_id") or "") == message_id
    ), None)
    if existing:
        if (existing.get("result") or {}).get("feedback") != payload.feedback:
            raise HTTPException(status_code=409, detail="Answer feedback already recorded")
        return {
            "status": "recorded",
            "event_id": existing.get("event_id"),
            "feedback": payload.feedback,
        }

    context_ref = message.get("context_ref") or {}
    event = await run_in_threadpool(
        record_learning_event,
        event_type="assistant_answer_feedback_submitted",
        actor="user",
        source="ai_teacher.answer_feedback",
        user_id=user_id,
        course_id=payload.course_id,
        course_version_id=course.get("current_course_version_id"),
        node_id=payload.node_id or str(context_ref.get("node_id") or ""),
        node_name=payload.node_name or str(context_ref.get("node_name") or ""),
        evidence={
            "conversation_id": conversation_id,
            "message_id": message_id,
            "answer_summary": summarize_text(str(message.get("content") or "")),
        },
        result={"feedback": payload.feedback},
        metadata={
            "conversation_id": conversation_id,
            "message_id": message_id,
            "inline_ai_action": payload.action,
            "content_anchor": payload.content_anchor,
        },
    )

    node_id = payload.node_id or str(context_ref.get("node_id") or "")
    if payload.feedback == "unclear" and node_id:
        # A student marking an AI answer "unclear" is functionally the same
        # comprehension-gap signal `learner_self_reported` already models
        # (see `learner_model.classify_evidence_event`); mirror it into that
        # shape so AI Q&A actually feeds the existing evidence-trigger
        # pipeline (`learner_model_service.evaluate_and_propose_change`)
        # instead of only ever producing a feedback record nothing reads.
        await run_in_threadpool(
            record_learning_event,
            event_type="learner_self_reported",
            actor="user",
            source="ai_teacher.answer_feedback",
            user_id=user_id,
            course_id=payload.course_id,
            course_version_id=course.get("current_course_version_id"),
            node_id=node_id,
            node_name=payload.node_name or str(context_ref.get("node_name") or ""),
            evidence={
                "statement": "这段看不懂，AI 老师的解答没有解决理解困难",
                "conversation_id": conversation_id,
                "message_id": message_id,
            },
            result={"feedback": payload.feedback},
            metadata={
                "conversation_id": conversation_id,
                "message_id": message_id,
                "derived_from": "assistant_answer_feedback_submitted",
            },
        )

    return {"status": "recorded", "event_id": event["event_id"], "feedback": payload.feedback}


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    request: Request,
    course_id: str = Query(min_length=1, max_length=160),
):
    await get_course_or_404(course_id)
    user_id = require_user_id(request.headers.get("X-User-Id"))
    deleted = await run_in_threadpool(
        ai_teacher_repository.delete_conversation,
        user_id,
        course_id,
        conversation_id,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="AI conversation not found")
    return {"status": "deleted", "conversation_id": conversation_id}


@router.post("/proposals")
async def create_proposal(payload: ProposalCreate, request: Request):
    course = await get_course_or_404(payload.course_id)
    user_id = require_user_id(request.headers.get("X-User-Id"))
    try:
        proposal = await run_in_threadpool(
            propose_action,
            course,
            user_id=user_id,
            action_type=payload.action_type,
            target_ref=payload.target_ref,
            payload=payload.payload,
            conversation_id=payload.conversation_id,
            message_id=payload.message_id,
            reason=payload.reason,
            evidence_refs=payload.evidence_refs,
            confirmation_mode=payload.confirmation_mode,
            origin=payload.origin,
        )
    except ActionForbidden as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return proposal


@router.post("/proposals/{proposal_id}/confirm")
async def confirm_proposal(
    proposal_id: str,
    payload: ProposalConfirm,
    request: Request,
):
    course = await get_course_or_404(payload.course_id)
    user_id = require_user_id(request.headers.get("X-User-Id"))
    try:
        return await run_in_threadpool(
            execute_proposal,
            course,
            user_id=user_id,
            proposal_id=proposal_id,
            idempotency_key=payload.idempotency_key,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="AI proposal not found") from exc
    except ActionForbidden as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ProposalStale as exc:
        raise HTTPException(status_code=409, detail={"code": "proposal_stale", "message": str(exc)}) from exc


@router.post("/proposals/{proposal_id}/reject")
async def reject_action_proposal(
    proposal_id: str,
    payload: ProposalReject,
    request: Request,
):
    course = await get_course_or_404(payload.course_id)
    user_id = require_user_id(request.headers.get("X-User-Id"))
    try:
        return await run_in_threadpool(
            reject_proposal,
            course,
            user_id=user_id,
            proposal_id=proposal_id,
            reason=payload.reason,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="AI proposal not found") from exc


@router.post("/receipts/{receipt_id}/undo")
async def undo_action_receipt(
    receipt_id: str,
    payload: ReceiptUndo,
    request: Request,
):
    course = await get_course_or_404(payload.course_id)
    user_id = require_user_id(request.headers.get("X-User-Id"))
    try:
        return await run_in_threadpool(
            undo_receipt,
            course,
            user_id=user_id,
            receipt_id=receipt_id,
            idempotency_key=payload.idempotency_key,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="AI receipt or affected object not found") from exc
    except ActionForbidden as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ProposalStale as exc:
        raise HTTPException(status_code=409, detail={"code": "undo_stale", "message": str(exc)}) from exc


@router.get("/trigger")
async def get_trigger_candidate(
    request: Request,
    course_id: str = Query(min_length=1, max_length=160),
    node_id: str | None = Query(default=None, max_length=160),
):
    course = await get_course_or_404(course_id)
    user_id = require_user_id(request.headers.get("X-User-Id"))
    candidate = await run_in_threadpool(
        build_trigger_candidate,
        course,
        user_id=user_id,
        node_id=node_id,
    )
    return {"candidate": candidate}


__all__ = ["router"]
