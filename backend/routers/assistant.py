"""AI 问答与聊天摘要路由。"""

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
import hashlib
import json
import sys, os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from ai_qa_service import classify_model_failure
from ai_teacher_actions import execute_proposal, propose_action
from ai_teacher_context import build_ai_teacher_context, context_public_summary
from ai_teacher_retrieval import (
    merge_ai_teacher_retrieval,
    retrieve_ai_teacher_sources,
    should_retrieve_for_message,
)
from ai_teacher_state import ai_teacher_repository
from course_evolution_intake import (
    CourseEvolutionRequest,
    record_course_evolution_request,
)
from dependencies import get_course_or_404
from learning_contracts import LearnerCourseScope
from models import AskQuestionRequest
from ai_service import ai_service
from fastapi.responses import StreamingResponse
from learner_context import require_user_id
from learning_events import record_learning_event, summarize_text
from product_runtime_policy import demo_overrides_enabled

router = APIRouter(tags=["assistant"])


@router.post("/ask_events")
async def ask_question_events(req: AskQuestionRequest, request: Request):
    if not req.course_id:
        raise HTTPException(status_code=422, detail="course_id is required")
    course = await get_course_or_404(req.course_id)
    user_id = require_user_id(request.headers.get("X-User-Id"))
    learning_scope = LearnerCourseScope.from_course(
        course,
        user_id=user_id,
        expected_course_id=req.course_id,
    )
    conversation = None
    if req.conversation_id:
        conversation = await run_in_threadpool(
            ai_teacher_repository.get_conversation,
            user_id,
            req.course_id,
            req.conversation_id,
        )
    if not conversation:
        conversation = await run_in_threadpool(
            ai_teacher_repository.create_conversation,
            user_id,
            req.course_id,
            title=summarize_text(req.question, limit=40),
            course_version_id=str(course.get("current_course_version_id") or ""),
            conversation_id=req.conversation_id,
        )
    conversation_id = str(conversation.get("conversation_id") or "")
    previous_assistant = next((
        item for item in reversed(conversation.get("messages") or [])
        if item.get("role") == "assistant" and item.get("status") == "complete"
    ), None)
    user_message = await run_in_threadpool(
        ai_teacher_repository.append_message,
        user_id,
        req.course_id,
        conversation_id,
        {
            "message_id": _stable_user_message_id(
                user_id=user_id,
                course_id=req.course_id,
                request_id=req.request_id or "",
            ),
            "role": "user",
            "content": req.question,
            "context_ref": req.context_ref,
            "task_ref": req.task_ref,
        },
    )
    record_course_evolution_request(
        CourseEvolutionRequest(
            scope=learning_scope,
            request_id=str(req.request_id or user_message.get("message_id") or ""),
            instruction=req.question,
            entrypoint="ai_teacher",
            requested_scope="current_section" if req.node_id else "whole_course",
            section_id=req.node_id,
            section_name=req.node_name,
            conversation_id=conversation_id,
            selection=req.selection or "",
            surface_entrypoint=req.entrypoint,
            context_ref=req.context_ref,
            task_ref=req.task_ref,
        ),
        recorder=record_learning_event,
    )

    conversation = await run_in_threadpool(
        ai_teacher_repository.get_conversation,
        user_id,
        req.course_id,
        conversation_id,
    )
    context_package = await run_in_threadpool(
        build_ai_teacher_context,
        course,
        user_id=user_id,
        question=req.question,
        node_id=req.node_id or None,
        selection=req.selection or "",
        perspective=req.perspective,
        entrypoint=req.entrypoint,
        context_ref=req.context_ref,
        task_ref=req.task_ref,
        conversation=conversation,
    )
    public_context = context_public_summary(context_package)
    assistant_message_id = f"aim_{os.urandom(16).hex()}"
    direct_action = None if req.perspective == "teacher" else _direct_action(req.question)
    retrieval_requested = req.perspective != "teacher" and should_retrieve_for_message(
        conversation,
        direct_action=direct_action,
    )

    async def event_stream_with_event():
        answer_context = context_package
        answer_public = public_context
        retrieval_package: dict = {}
        retrieval_receipt: dict = {}
        fallback_notice = ""
        yield _qa_event("context", {
            "conversation_id": conversation_id,
            "user_message_id": user_message.get("message_id"),
            "assistant_message_id": assistant_message_id,
            **public_context,
        })
        if retrieval_requested:
            yield _qa_event("retrieval", {"status": "started"})
            try:
                retrieval_package = await retrieve_ai_teacher_sources(
                    course,
                    question=req.question,
                    node_id=req.node_id,
                    user_id=user_id,
                )
            except Exception:
                retrieval_package = {
                    "schema_version": "retrieval_package_v1",
                    "status": "failed_fallback_local",
                    "revision": 1,
                    "sources": [],
                    "receipt": {
                        "schema_version": "retrieval_receipt_v1",
                        "status": "failed_fallback_local",
                        "error_codes": ["provider_error"],
                        "query_count": 0,
                        "source_count": 0,
                    },
                }
            answer_context = merge_ai_teacher_retrieval(
                context_package,
                retrieval_package,
            )
            answer_public = context_public_summary(answer_context)
            web_source_count = int(
                (answer_context.get("web_retrieval") or {}).get(
                    "source_count"
                )
                or 0
            )
            retrieval_receipt = dict(
                retrieval_package.get("receipt") or {}
            )
            if (
                retrieval_package.get("status") == "completed"
                and web_source_count > 0
            ):
                retrieval_event_status = "completed"
            else:
                retrieval_event_status = "failed_fallback_local"
                retrieval_receipt["status"] = retrieval_event_status
                error_codes = list(
                    retrieval_receipt.get("error_codes") or []
                )
                if not error_codes:
                    error_codes.append("no_sources")
                retrieval_receipt["error_codes"] = error_codes
                fallback_notice = (
                    "联网检索失败，本回答未完成外部核验。\n\n"
                )
            yield _qa_event("retrieval", {
                "status": retrieval_event_status,
                "receipt": retrieval_receipt,
            })
        yield _qa_event(
            "sources",
            {"sources": answer_public.get("sources") or []},
        )

        if direct_action:
            payload = _direct_action_payload(
                direct_action,
                req=req,
                previous_assistant=previous_assistant,
            )
            if not payload.get("content"):
                answer = "当前没有可保存的上一条回答或选中内容。"
                await run_in_threadpool(
                    ai_teacher_repository.append_message,
                    user_id,
                    req.course_id,
                    conversation_id,
                    {
                        "message_id": assistant_message_id,
                        "role": "assistant",
                        "content": answer,
                        "context_ref": public_context.get("scene") or {},
                    },
                )
                yield _qa_event("final_answer", {"answer": answer, "message_id": assistant_message_id})
                yield _qa_event("done", {"conversation_id": conversation_id, "message_id": assistant_message_id})
                return
            proposal = await run_in_threadpool(
                propose_action,
                course,
                user_id=user_id,
                action_type=direct_action,
                target_ref={
                    "node_id": req.node_id,
                    "course_version_id": course.get("current_course_version_id"),
                    "content_anchor": (req.context_ref or {}).get("content_anchor") or {},
                },
                payload=payload,
                conversation_id=conversation_id,
                message_id=str(user_message.get("message_id") or ""),
                reason="用户在当前轮次明确要求执行该动作。",
                evidence_refs=[],
                confirmation_mode="user_command",
                origin="user_command",
            )
            proposal_id = str(proposal.get("proposal_id") or "")
            try:
                receipt = await run_in_threadpool(
                    execute_proposal,
                    course,
                    user_id=user_id,
                    proposal_id=proposal_id,
                    idempotency_key=f"direct:{user_message.get('message_id')}:{direct_action}",
                )
            except BaseException:
                # A direct action is proposed and executed inside one turn, so
                # a proposal left `presented` after the turn dies is a half
                # action: nothing ran, yet it stays confirmable later against
                # context the learner already abandoned. Cancel it explicitly.
                await run_in_threadpool(
                    _cancel_pending_proposal,
                    user_id,
                    req.course_id,
                    proposal_id,
                )
                raise
            answer = str(receipt.get("summary") or "操作已处理。")
            await run_in_threadpool(
                ai_teacher_repository.append_message,
                user_id,
                req.course_id,
                conversation_id,
                {
                    "message_id": assistant_message_id,
                    "role": "assistant",
                    "content": answer,
                    "context_ref": public_context.get("scene") or {},
                    "receipt_id": receipt.get("receipt_id"),
                },
            )
            yield _qa_event("receipt", receipt)
            yield _qa_event("final_answer", {"answer": answer, "message_id": assistant_message_id})
            yield _qa_event("done", {"conversation_id": conversation_id, "message_id": assistant_message_id})
            return

        if _assistant_demo_mode(req.course_id):
            answer = fallback_notice + _demo_teacher_answer(req.question)
            await run_in_threadpool(
                ai_teacher_repository.append_message,
                user_id,
                req.course_id,
                conversation_id,
                {
                    "message_id": assistant_message_id,
                    "role": "assistant",
                    "content": answer,
                    "context_ref": public_context.get("scene") or {},
                    "task_ref": req.task_ref,
                    "sources": answer_public.get("sources") or [],
                    "retrieval_receipt": retrieval_receipt,
                },
            )
            record_learning_event(
                event_type="assistant_answer_completed",
                actor="assistant",
                source="ai_teacher.ask_events",
                user_id=user_id,
                course_id=req.course_id,
                course_version_id=course.get("current_course_version_id"),
                node_id=req.node_id,
                node_name=req.node_name,
                evidence={
                    "question": summarize_text(req.question),
                    "conversation_id": conversation_id,
                    "source_ids": [
                        item.get("source_id")
                        for item in answer_public.get("sources") or []
                    ],
                },
                result={
                    "answer_summary": summarize_text(answer),
                    "output_chars": len(answer),
                    "metadata_emitted": True,
                    "response_mode": "local_demo",
                },
            )
            yield _qa_event("final_answer", {
                "answer": answer,
                "message_id": assistant_message_id,
            })
            yield _qa_event("done", {
                "conversation_id": conversation_id,
                "message_id": assistant_message_id,
            })
            return

        full_text = ""
        if fallback_notice:
            yield _qa_event("answer", {"chunk": fallback_notice})

        # One persistence path for every way this turn can end — completed,
        # classified provider failure, or cancelled by the client. `finally`
        # owns it so a disconnect (which resumes the generator at the await
        # point with GeneratorExit/CancelledError, and cannot yield afterwards)
        # still records the turn the learner actually saw.
        outcome = "cancelled"
        failure: dict[str, Any] = {}
        try:
            async for chunk in ai_service.answer_question_events(
                question=req.question,
                context_package=answer_context,
            ):
                full_text += chunk
                yield chunk
            streamed_error = _extract_sse_error(full_text)
            if streamed_error:
                outcome, failure = "failed", streamed_error
            else:
                outcome = "completed"
        except (GeneratorExit, asyncio.CancelledError):
            raise
        except Exception as exc:
            # The service classifies provider failures itself and normally
            # reports them inside the stream. Anything escaping here failed
            # before or outside that path, so classify it the same way rather
            # than reporting one opaque code.
            classified = classify_model_failure(exc)
            outcome = "failed"
            failure = {
                "code": classified.code,
                "message": classified.message,
                "retryable": classified.retryable,
                "emit_error_event": True,
            }
        finally:
            answer = fallback_notice + _extract_sse_answer(full_text)
            await _persist_answer_turn(
                outcome,
                user_id=user_id,
                course=course,
                req=req,
                conversation_id=conversation_id,
                assistant_message_id=assistant_message_id,
                answer=answer,
                scene=public_context.get("scene") or {},
                sources=answer_public.get("sources") or [],
                retrieval_receipt=retrieval_receipt,
                failure=failure,
            )

        if outcome == "failed":
            if failure.get("emit_error_event"):
                yield _qa_event("error", {
                    "code": failure.get("code"),
                    "message": failure.get("message"),
                    "retryable": bool(failure.get("retryable")),
                })
            yield _qa_event("done", {"conversation_id": conversation_id, "message_id": assistant_message_id})
            return

        yield _qa_event("final_answer", {
            "answer": answer,
            "message_id": assistant_message_id,
        })
        yield _qa_event("done", {"conversation_id": conversation_id, "message_id": assistant_message_id})

    return StreamingResponse(
        event_stream_with_event(),
        media_type="text/event-stream"
    )


async def _persist_answer_turn(
    outcome: str,
    *,
    user_id: str,
    course: dict,
    req: AskQuestionRequest,
    conversation_id: str,
    assistant_message_id: str,
    answer: str,
    scene: dict,
    sources: list,
    retrieval_receipt: dict,
    failure: dict,
) -> None:
    """Record one assistant turn, whichever way the answer stream ended.

    A cancelled turn keeps exactly the text the learner already read: dropping
    it would make the turn look like it never happened, and inventing more
    would present unseen model output as something they read.
    """
    failure_code = (
        ""
        if outcome == "completed"
        else str(failure.get("code") or "") or ("cancelled" if outcome == "cancelled" else "model_unavailable")
    )
    content = answer
    if outcome != "completed" and not content:
        content = str(failure.get("message") or "")
    await run_in_threadpool(
        ai_teacher_repository.append_message,
        user_id,
        req.course_id,
        conversation_id,
        {
            "message_id": assistant_message_id,
            "role": "assistant",
            "content": content,
            "context_ref": scene,
            "task_ref": req.task_ref,
            "sources": sources,
            "retrieval_receipt": retrieval_receipt,
            **({} if outcome == "completed" else {
                "status": "failed",
                "failure_code": failure_code,
            }),
        },
    )
    if outcome == "completed":
        record_learning_event(
            event_type="assistant_answer_completed",
            actor="assistant",
            source="ai_teacher.ask_events",
            user_id=user_id,
            course_id=req.course_id,
            course_version_id=course.get("current_course_version_id"),
            node_id=req.node_id,
            node_name=req.node_name,
            evidence={
                "question": summarize_text(req.question),
                "conversation_id": conversation_id,
                "source_ids": [item.get("source_id") for item in sources],
            },
            result={
                "answer_summary": summarize_text(answer),
                "output_chars": len(answer),
                "metadata_emitted": True,
            },
        )
        return
    record_learning_event(
        event_type=(
            "assistant_answer_cancelled"
            if outcome == "cancelled"
            else "assistant_answer_failed"
        ),
        actor="assistant",
        source="ai_teacher.ask_events",
        user_id=user_id,
        course_id=req.course_id,
        course_version_id=course.get("current_course_version_id"),
        node_id=req.node_id,
        node_name=req.node_name,
        evidence={
            "question": summarize_text(req.question),
            "conversation_id": conversation_id,
        },
        result={
            "failure_code": failure_code,
            "retryable": bool(failure.get("retryable", outcome == "cancelled")),
            "output_chars": len(answer),
        },
    )


def _cancel_pending_proposal(user_id: str, course_id: str, proposal_id: str) -> None:
    """Retire a direct-action proposal whose turn never reached execution."""
    if not proposal_id:
        return
    try:
        current = ai_teacher_repository.get_proposal(user_id, course_id, proposal_id)
        if not current or current.get("status") not in {"presented", "confirmed", "executing"}:
            return
        ai_teacher_repository.update_proposal(
            user_id,
            course_id,
            proposal_id,
            status="cancelled",
            changes={"failure_reason": "answer stream ended before execution"},
        )
    except (KeyError, ValueError, OSError):
        # Best-effort cleanup: never let it mask the original failure.
        pass


def _direct_action(question: str) -> str | None:
    normalized = "".join(str(question or "").split())
    if any(pattern in normalized for pattern in ["帮我记成笔记", "保存为笔记", "帮我记下来"]):
        return "create_note"
    if any(pattern in normalized for pattern in ["标记为不懂", "创建一个问题", "记为问题"]):
        return "create_issue"
    return None


def _direct_action_payload(
    action_type: str,
    *,
    req: AskQuestionRequest,
    previous_assistant: dict | None,
) -> dict:
    if action_type == "create_note":
        content = str(req.selection or (previous_assistant or {}).get("content") or "")
        return {
            "node_id": req.node_id,
            "title": summarize_text(content, limit=80),
            "content": content,
            "quote": req.selection or "",
            "anchor": (req.context_ref or {}).get("content_anchor") or {},
        }
    content = str(req.selection or req.question or "")
    return {
        "node_id": req.node_id,
        "title": summarize_text(content, limit=80),
        "content": content,
        "quote": req.selection or "",
        "anchor": (req.context_ref or {}).get("content_anchor") or {},
    }


def _qa_event(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _stable_user_message_id(
    *,
    user_id: str,
    course_id: str,
    request_id: str,
) -> str:
    normalized_request_id = str(request_id or "").strip()
    if not normalized_request_id:
        return ""
    digest = hashlib.sha256(
        f"{user_id}\0{course_id}\0{normalized_request_id}".encode("utf-8")
    ).hexdigest()
    return f"aim_{digest[:32]}"


def _extract_sse_answer(text: str) -> str:
    chunks: list[str] = []
    final_answer = ""
    for event_name, payload in _iter_sse_events(text):
        if event_name == "answer":
            chunks.append(str(payload.get("chunk") or ""))
        elif event_name == "final_answer":
            final_answer = str(payload.get("answer") or "")
    return final_answer or "".join(chunks)


def _extract_sse_error(text: str) -> dict | None:
    """Return the classified failure the answer stream reported, if any."""
    for event_name, payload in _iter_sse_events(text):
        if event_name == "error":
            return payload
    return None


def _iter_sse_events(text: str):
    for block in text.replace("\r\n", "\n").split("\n\n"):
        event_name = ""
        data_lines: list[str] = []
        for line in block.split("\n"):
            if line.startswith("event:"):
                event_name = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data_lines.append(line.split(":", 1)[1].lstrip())
        if not event_name or not data_lines:
            continue
        try:
            payload = json.loads("\n".join(data_lines))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            yield event_name, payload


def _assistant_demo_mode(course_id: str) -> bool:
    """录屏模式使用本地定稿回答，避免外部模型状态影响演示。"""
    return demo_overrides_enabled(course_id)


def _demo_teacher_answer(question: str) -> str:
    """返回可预测的演示回答；课程生长仍由正式证据链独立完成。"""
    text = "".join(str(question or "").split())
    is_composition_request = (
        "矩阵乘法" in text
        and "复合变换" in text
        and any(marker in text for marker in ("动画", "几何", "图形"))
        and any(marker in text for marker in ("后面", "后续"))
    )
    if is_composition_request:
        return (
            "我已经理解你的学习边界：矩阵乘法计算已经掌握，持续困难是"
            "复合变换的先后顺序；你希望先看几何动画，再进行计算，并让调整"
            "覆盖本节及相关后续。课程生长方案已生成，确认前不会修改正式课程。"
        )
    return (
        "这次学习请求已在本地演示模式中记录。系统会先展示理解到的学习证据"
        "与影响范围，只有在你确认后才会更新正式课程。"
    )
