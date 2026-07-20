"""AI 问答与聊天摘要路由。"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
import json
import sys, os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from ai_teacher_actions import execute_proposal, propose_action
from ai_teacher_context import build_ai_teacher_context, context_public_summary
from ai_teacher_state import ai_teacher_repository
from dependencies import get_course_or_404
from models import AskQuestionRequest
from ai_service import ai_service
from fastapi.responses import StreamingResponse
from learner_context import require_user_id
from learning_events import record_learning_event, summarize_text

router = APIRouter(tags=["assistant"])


@router.post("/ask_events")
async def ask_question_events(req: AskQuestionRequest, request: Request):
    if not req.course_id:
        raise HTTPException(status_code=422, detail="course_id is required")
    course = await get_course_or_404(req.course_id)
    user_id = require_user_id(request.headers.get("X-User-Id"))
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
            "role": "user",
            "content": req.question,
            "context_ref": req.context_ref,
            "task_ref": req.task_ref,
        },
    )
    record_learning_event(
        event_type="assistant_question_submitted",
        actor="user",
        source="ai_teacher.ask_events",
        user_id=user_id,
        course_id=req.course_id,
        course_version_id=course.get("current_course_version_id"),
        node_id=req.node_id,
        node_name=req.node_name,
        evidence={
            "question": summarize_text(req.question),
            "selection": summarize_text(req.selection or ""),
            "entrypoint": req.entrypoint,
            "conversation_id": conversation_id,
        },
        metadata={"task_ref": req.task_ref or {}, "context_ref": req.context_ref or {}},
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
        entrypoint=req.entrypoint,
        context_ref=req.context_ref,
        task_ref=req.task_ref,
        conversation=conversation,
    )
    public_context = context_public_summary(context_package)
    assistant_message_id = f"aim_{os.urandom(16).hex()}"
    direct_action = _direct_action(req.question)

    async def event_stream_with_event():
        yield _qa_event("context", {
            "conversation_id": conversation_id,
            "user_message_id": user_message.get("message_id"),
            "assistant_message_id": assistant_message_id,
            **public_context,
        })
        yield _qa_event("sources", {"sources": public_context.get("sources") or []})

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
            receipt = await run_in_threadpool(
                execute_proposal,
                course,
                user_id=user_id,
                proposal_id=str(proposal.get("proposal_id") or ""),
                idempotency_key=f"direct:{user_message.get('message_id')}:{direct_action}",
            )
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
            answer = _demo_teacher_answer(req.question)
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
                    "sources": public_context.get("sources") or [],
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
                        for item in public_context.get("sources") or []
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
        try:
            async for chunk in ai_service.answer_question_events(
                question=req.question,
                context_package=context_package,
            ):
                full_text += chunk
                yield chunk
        except Exception:
            error_message = "AI 老师暂时不可用，课程和正式学习任务仍可继续使用。"
            await run_in_threadpool(
                ai_teacher_repository.append_message,
                user_id,
                req.course_id,
                conversation_id,
                {
                    "message_id": assistant_message_id,
                    "role": "assistant",
                    "content": error_message,
                    "context_ref": public_context.get("scene") or {},
                    "status": "failed",
                },
            )
            yield _qa_event("error", {"code": "model_unavailable", "message": error_message})
            yield _qa_event("done", {"conversation_id": conversation_id, "message_id": assistant_message_id})
            return
        answer = _extract_sse_answer(full_text)
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
                "sources": public_context.get("sources") or [],
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
                "source_ids": [item.get("source_id") for item in public_context.get("sources") or []],
            },
            result={
                "answer_summary": summarize_text(answer),
                "output_chars": len(full_text),
                "metadata_emitted": True,
            },
        )
        yield _qa_event("done", {"conversation_id": conversation_id, "message_id": assistant_message_id})

    return StreamingResponse(
        event_stream_with_event(),
        media_type="text/event-stream"
    )


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


def _extract_sse_answer(text: str) -> str:
    chunks: list[str] = []
    final_answer = ""
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
        if event_name == "answer":
            chunks.append(str(payload.get("chunk") or ""))
        elif event_name == "final_answer":
            final_answer = str(payload.get("answer") or "")
    return final_answer or "".join(chunks)


def _assistant_demo_mode(course_id: str) -> bool:
    """录屏模式使用本地定稿回答，避免外部模型状态影响演示。"""
    return (
        str(course_id or "") == "demo-matrix-growth-v2"
        and os.getenv("EVOLUTION_DEMO_MODE", "").strip().lower()
        in {"1", "true", "yes", "on"}
    )


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
