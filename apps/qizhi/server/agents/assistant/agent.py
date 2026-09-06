import json
import time
from typing import Any, AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from agents.assistant.context import Context
from agents.assistant.memory_manager import MemoryManager
from agents.assistant.models import ChatRequest
from agents.assistant.tools.registry import tool_registry
from agents.llm import stream_chat
from agents.prompt_manager import PromptManager
from common.utils import SseEventEnum, build_attachment_text, build_sse_response, compose_user_message
from common.utils.logger import get_logger
from infra.db import Session, User, generate_id

logger = get_logger(__name__)


async def stream(
    db: AsyncSession, request: ChatRequest, current_user: User
) -> AsyncIterator[dict[str, Any]]:
    start_time = time.perf_counter()

    if not request.session_id:
        session = Session(title=request.query, user_id=current_user.id)
        db.add(session)
        await db.flush()
        request.session_id = session.id

    context = await build_context(db, request, current_user)
    yield build_sse_response(SseEventEnum.START, {"session_id": context.session_id})

    try:
        async for event in react_loop(context, db, start_time=start_time):
            yield event
    except Exception as exc:
        logger.exception("ReAct loop failed")
        yield build_sse_response(SseEventEnum.ERROR, {"error": str(exc)})
        cost_ms = int((time.perf_counter() - start_time) * 1000)
        await MemoryManager.insert_message(
            db=db,
            session_id=context.session_id,
            chat_id=context.chat_id,
            user_id=context.current_user.id,
            role="assistant",
            message="",
            status="error",
            error_message=str(exc),
            cost_time=cost_ms,
        )
    finally:
        cost_ms = int((time.perf_counter() - start_time) * 1000)
        yield build_sse_response(SseEventEnum.END, {"cost_time": cost_ms})


async def build_context(
    db: AsyncSession, request: ChatRequest, current_user: User
) -> Context:
    # 解析上传附件为文本（一次性）：注入本轮 user 消息，并落库供历史重建复用
    attachment_text = build_attachment_text(request.file_paths)

    # 用户传了附件但一个字都没解析出来：如实告知模型，避免它回复“没收到文件，请粘贴内容”误导用户
    if request.file_paths and not attachment_text:
        logger.warning(
            f"[agent.py] 用户上传了 {len(request.file_paths)} 个附件但未解析出任何文本: {request.file_paths}"
        )
        user_content = (
            f"{request.query}\n\n"
            "【系统提示：用户上传了附件，但系统未能从中解析出任何文本内容（常见原因："
            "扫描件/图片型 PDF、空文档，或文件读取失败）。请如实告知用户附件未能成功读取，"
            "并建议改用可复制文字的文档；不要回复“我没有收到文件”之类暗示用户未上传的话。】"
        )
    else:
        user_content = compose_user_message(request.query, attachment_text)

    context = Context(
        db=db,
        session_id=request.session_id,
        chat_id=generate_id(),
        current_user=current_user,
        messages=[
            *await MemoryManager.query_messages(request.session_id, db),
            {"role": "user", "content": user_content},
        ],
        file_paths=request.file_paths or [],
    )
    await MemoryManager.insert_message(
        db=db,
        session_id=context.session_id,
        chat_id=context.chat_id,
        user_id=context.current_user.id,
        role="user",
        message=request.query,
        file_paths=request.file_paths or [],
        file_contents=attachment_text,
    )
    return context


# ---------------------------------------------------------------------------
# ReAct 循环（Plan + ReAct 混合架构）
# ---------------------------------------------------------------------------

async def react_loop(
    context: Context, db: AsyncSession, *, start_time: float
) -> AsyncIterator[dict[str, Any]]:
    tools = json.dumps(tool_registry.planner_specs(), ensure_ascii=False, indent=2)
    system_prompt = PromptManager.get_prompt("assistant", tools=tools)

    for i in range(context.max_rounds):
        context.round = i + 1

        content = ""
        # 流式追踪状态
        tracker = _FieldTracker()

        async for chunk in stream_chat(
            system_prompt=system_prompt,
            user_prompt="",
            history=context.messages,
        ):
            content += chunk
            async for event in tracker.feed(content, context):
                yield event

        # 流结束后再 flush 一次，确保残留内容被输出
        async for event in tracker.flush(context):
            yield event

        parsed = parse_react_output(content)
        if parsed is None:
            # 模型输出无效 JSON，给一次重试机会（把错误作为 Observation 丢回去）
            logger.warning(f"[agent.py] 第 {context.round} 轮模型输出无效 JSON，尝试重试。原始输出:\n{content[:500]}")
            context.add_message({
                "role": "user",
                "content": "Observation: 你上一次的输出格式不正确。请严格按 JSON 格式输出，只输出 JSON，不要加 Markdown 代码块或其他说明文字。",
            })
            continue

        thought = parsed.get("thought", "")
        plan = parsed.get("plan")
        actions = parsed.get("actions", [])
        final_answer = parsed.get("final_answer")

        # 处理 plan（仅第一轮；plan 已设置后不再重复处理）
        if plan and context.round == 1 and context.plan is None:
            context.plan = plan
            # 如果 plan 没有被流式完整输出（比如模型一次性吐完），兜底输出
            if tracker.plan_yielded_len == 0:
                yield build_sse_response(SseEventEnum.PLAN, {"content": plan})

        has_actions = actions is not None and isinstance(actions, list) and len(actions) > 0
        has_final = final_answer is not None

        if has_final and not has_actions:
            # 兜底：如果 final_answer 没有被完整流式输出
            if not tracker.answer_fully_yielded:
                yield build_sse_response(SseEventEnum.MESSAGE, {"content": final_answer})

            context.add_message({"role": "assistant", "content": final_answer})
            cost_ms = int((time.perf_counter() - start_time) * 1000)
            await MemoryManager.insert_message(
                db=db,
                session_id=context.session_id,
                chat_id=context.chat_id,
                user_id=context.current_user.id,
                role="assistant",
                message=final_answer,
                cost_time=cost_ms,
            )
            return

        if has_actions:
            observations = []
            for action in actions:
                action_id = action.get("id", "")
                tool_name = action.get("tool_name", "")
                payload = action.get("args", {})
                if not isinstance(payload, dict):
                    payload = {}

                tool = tool_registry.get(tool_name)
                loading_msg = tool.loading_message if tool and tool.loading_message else f"正在调用 {tool_name}"
                yield build_sse_response(
                    SseEventEnum.LOADING,
                    {"message": loading_msg},
                )

                try:
                    result = await run_tool(context, tool_name, payload)
                    observations.append({
                        "id": action_id,
                        "tool_name": tool_name,
                        "status": "success",
                        "result": str(result),
                    })
                except Exception as exc:
                    logger.exception(f"Tool {tool_name} failed")
                    observations.append({
                        "id": action_id,
                        "tool_name": tool_name,
                        "status": "error",
                        "result": str(exc),
                    })
                    # 工具执行中的数据库错误可能导致事务回滚，清理 session 防止后续操作挂掉
                    try:
                        await context.db.rollback()
                    except Exception:
                        pass

            # 将 assistant 消息以 JSON 格式记录到 Memory（与 system prompt 输出要求一致，防止模型脱轨）
            assistant_payload: dict[str, Any] = {
                "thought": thought,
                "actions": actions,
                "final_answer": None,
            }
            if plan:
                assistant_payload["plan"] = plan
            context.add_message({
                "role": "assistant",
                "content": json.dumps(assistant_payload, ensure_ascii=False),
            })

            # 将 observations 记录为 user 消息（Observation）
            obs_text = json.dumps(observations, ensure_ascii=False)
            context.add_message({
                "role": "user",
                "content": f"Observation: {obs_text}",
            })
        else:
            # 模型未给出有效响应（没有 actions 也没有 final_answer，或 actions 格式不对）
            # 把错误信息交给模型让它自己纠正，而不是直接中断
            err_msg = "你上一次的输出没有包含有效的 actions 或 final_answer。"
            if actions is not None and not isinstance(actions, list):
                err_msg = "你上一次的 actions 字段格式不正确，必须是数组。"
            logger.warning(f"[agent.py] 第 {context.round} 轮模型未给出有效响应，尝试纠正。parsed={parsed}")
            context.add_message({
                "role": "user",
                "content": f"Observation: {err_msg} 请重新思考，按 JSON 格式输出：如果有工具要调用就填 actions，如果已完成就填 final_answer。",
            })
            continue

    fallback = "抱歉，我处理这个问题需要更多步骤，您可以尝试简化描述。"
    yield build_sse_response(SseEventEnum.MESSAGE, {"content": fallback})
    context.add_message({"role": "assistant", "content": fallback})
    cost_ms = int((time.perf_counter() - start_time) * 1000)
    await MemoryManager.insert_message(
        db=db,
        session_id=context.session_id,
        chat_id=context.chat_id,
        user_id=context.current_user.id,
        role="assistant",
        message=fallback,
        cost_time=cost_ms,
    )


# ---------------------------------------------------------------------------
# 流式字段追踪器（用于 plan / final_answer 的增量 SSE 输出）
# ---------------------------------------------------------------------------

class _FieldTracker:
    """追踪 JSON 输出中 plan 和 final_answer 字段的流式位置，增量 yield SSE 事件。"""

    def __init__(self) -> None:
        # plan 追踪
        self.plan_quote_pos: int | None = None
        self.plan_yielded_len = 0
        self.plan_closed = False

        # final_answer 追踪
        self.answer_quote_pos: int | None = None
        self.answer_yielded_len = 0
        self.answer_closed = False
        self.answer_fully_yielded = False

    async def feed(self, content: str, context: Context) -> AsyncIterator[dict[str, Any]]:
        """每收到一个 chunk 后调用，增量检测并 yield SSE 事件。"""
        # ---- 追踪 plan ----
        if context.round == 1 and context.plan is None and not self.plan_closed:
            if self.plan_quote_pos is None:
                idx = content.rfind('"plan"')
                if idx != -1:
                    after = content[idx + len('"plan"') :]
                    for j, c in enumerate(after):
                        if c == '"':
                            self.plan_quote_pos = idx + len('"plan"') + j
                            break
                        elif not c.isspace() and c != ":":
                            break
            else:
                total_len = len(content) - (self.plan_quote_pos + 1)
                if total_len > self.plan_yielded_len:
                    full_text = content[self.plan_quote_pos + 1 : self.plan_quote_pos + 1 + total_len]
                    end_pos = find_json_string_end(full_text, self.plan_yielded_len)
                    if end_pos != -1:
                        text_to_yield = full_text[self.plan_yielded_len:end_pos]
                        if text_to_yield:
                            yield build_sse_response(SseEventEnum.PLAN, {"content": text_to_yield})
                        self.plan_yielded_len = end_pos
                        self.plan_closed = True
                    else:
                        new_text = full_text[self.plan_yielded_len:]
                        if new_text:
                            yield build_sse_response(SseEventEnum.PLAN, {"content": new_text})
                        self.plan_yielded_len = total_len

        # ---- 追踪 final_answer ----
        if not self.answer_closed:
            if self.answer_quote_pos is None:
                idx = content.rfind('"final_answer"')
                if idx != -1:
                    after = content[idx + len('"final_answer"') :]
                    for j, c in enumerate(after):
                        if c == '"':
                            self.answer_quote_pos = idx + len('"final_answer"') + j
                            break
                        elif not c.isspace() and c != ":":
                            break
            else:
                total_len = len(content) - (self.answer_quote_pos + 1)
                if total_len > self.answer_yielded_len:
                    full_text = content[self.answer_quote_pos + 1 : self.answer_quote_pos + 1 + total_len]
                    end_pos = find_json_string_end(full_text, self.answer_yielded_len)
                    if end_pos != -1:
                        text_to_yield = full_text[self.answer_yielded_len:end_pos]
                        if text_to_yield:
                            yield build_sse_response(SseEventEnum.MESSAGE, {"content": text_to_yield})
                        self.answer_yielded_len = end_pos
                        self.answer_closed = True
                        self.answer_fully_yielded = True
                    else:
                        new_text = full_text[self.answer_yielded_len:]
                        if new_text:
                            yield build_sse_response(SseEventEnum.MESSAGE, {"content": new_text})
                        self.answer_yielded_len = total_len

    async def flush(self, context: Context) -> AsyncIterator[dict[str, Any]]:
        """流结束后调用，处理可能的残留。当前逻辑在 feed 中已覆盖，保留扩展性。"""
        # plan 和 final_answer 的闭环已在 feed 中处理
        # 如果内容极短且没有触发引号检测（如 null 或空字符串），不处理
        if 0:
            yield {}


# ---------------------------------------------------------------------------
# 输出解析与工具执行
# ---------------------------------------------------------------------------

def parse_react_output(content: str) -> dict[str, Any] | None:
    """解析模型 ReAct JSON 输出。解析失败时返回 None（由调用方决定是否重试）。"""
    if not content or not content.strip():
        return None

    content = content.strip()

    # 去除 Markdown 代码块包裹
    if content.startswith("```"):
        lines = content.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        content = "\n".join(lines).strip()

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # 尝试截断提取第一个 { ... } 区域
    start = content.find("{")
    end = content.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(content[start : end + 1])
        except json.JSONDecodeError:
            pass

    return None


async def run_tool(context: Context, tool_name: str, payload: dict[str, Any]) -> str:
    tool = tool_registry.get(tool_name)
    if not tool:
        raise Exception(f"工具不存在: {tool_name}")

    result = await tool.handler(payload, context)

    if hasattr(result, "__aiter__"):
        chunks = []
        async for chunk in result:
            chunks.append(str(chunk))
        return "".join(chunks)

    return str(result)


def find_json_string_end(s: str, start: int = 0) -> int:
    """查找 JSON 字符串的结束引号，跳过转义引号。"""
    i = start
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s):
            i += 2
        elif s[i] == '"':
            return i
        else:
            i += 1
    return -1
