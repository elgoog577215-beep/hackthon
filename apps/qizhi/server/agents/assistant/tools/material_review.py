import json
import logging
import os
from collections.abc import AsyncIterator

from pydantic import BaseModel
from sqlalchemy import select

from agents.assistant.context import Context
from agents.assistant.tools.registry import tool_registry
from common.config import settings
from common.models import BizException, SystemException
from common.models.constants import COZE_UPLOAD_TIMEOUT, COZE_API_BASE
from common.utils import HTTPMethodEnum, http_request, stream_sse
from infra.db import Session
from common.utils.logger import get_logger

logger = get_logger(__name__)


@tool_registry.register(
    description="对全国高校青年教师教学竞赛(青教赛)或全国高校教师教学创新大赛(教创赛)的教学文件材料进行分析评审。注意，如果用户想要对教学文件材料进行分析评审但没有提到青教赛和教创赛，不要调用此工具，而是先对用户提供的材料进行通用分析评审，再询问用户是否需要使用青教赛和教创赛的标准进行分析评审。",
    loading_message="正在进行教学材料评审，预计时长3分钟，请耐心等待...",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "用户问题或评审指令"},
        },
        "required": ["query"],
    },
)
async def material_review(payload: dict, context: Context) -> AsyncIterator[str]:
    """调用 Coze 材料评审 Bot，流式返回评审文本。"""
    # 1) 解析输入：优先用 payload.query，缺失时回退到会话最后一条消息
    planned_payload = payload if isinstance(payload, dict) else {}
    query = str(planned_payload.get("query") or "").strip()
    if not query:
        query = next((m["content"] for m in reversed(context.messages) if m.get("role") == "user" and m.get("content")), "")
    if not query:
        logger.warning(f"[material_review.py] 材料评审缺少 query 参数")
        raise BizException("材料评审缺少 query 参数")

    # 2) 读取会话：复用已有 coze conversation_id，保证多轮连续
    session = (await context.db.execute(select(Session).where(Session.id == context.session_id))).scalars().first()
    if not session:
        logger.error(f"[material_review.py] 会话不存在: {context.session_id}")
        raise SystemException(f"会话不存在: {context.session_id}")

    coze_conversation_id = session.sub_session_id
    if coze_conversation_id:
        url = f"{COZE_API_BASE}/v3/chat?conversation_id={coze_conversation_id}"
    else:
        url = f"{COZE_API_BASE}/v3/chat"

    # 3) 可选附件上传：将本地文件先上传到 Coze，拿到 file_id
    file_ids: list[str] = []
    if context.file_paths:
        upload_url = f"{COZE_API_BASE}/v1/files/upload"
        upload_headers = {"Authorization": f"Bearer {settings.COZE_API_KEY}"}
        for path in context.file_paths:
            if not path or not os.path.exists(path):
                logger.warning("material_review skip missing file: %s", path)
                continue

            with open(path, "rb") as file_obj:
                response = await http_request(
                    HTTPMethodEnum.POST,
                    upload_url,
                    headers=upload_headers,
                    files={"file": (os.path.basename(path), file_obj, "application/octet-stream")},
                    timeout=COZE_UPLOAD_TIMEOUT,
                )

            class _CozeFileData(BaseModel):
                id: str | None = None
                file_id: str | None = None

            class _CozeUploadResponse(BaseModel):
                data: _CozeFileData | None = None
                id: str | None = None
                file_id: str | None = None

            resp = _CozeUploadResponse.model_validate(response)
            file_id = resp.data and (resp.data.id or resp.data.file_id) or resp.id or resp.file_id
            if not file_id:
                logger.error(f"[material_review.py] 上传 Coze 文件失败，未返回 file_id")
                raise SystemException("上传 Coze 文件失败，未返回 file_id")
            file_ids.append(str(file_id))
    # 4) 组装消息：有附件则使用 object_string；否则用纯文本
    if file_ids:
        objects: list[dict[str, str]] = [{"type": "text", "text": query}]
        objects.extend({"type": "file", "file_id": file_id} for file_id in file_ids)
        additional_messages = [
            {
                "role": "user",
                "content_type": "object_string",
                "content": json.dumps(objects, ensure_ascii=False),
            }
        ]
    else:
        additional_messages = [{"role": "user", "content": query, "content_type": "text"}]

    # 5) 发起流式对话请求
    headers = {
        "Authorization": f"Bearer {settings.COZE_API_KEY}",
        "Content-Type": "application/json",
    }
    body = {
        "bot_id": settings.COZE_BOT_ID,
        "user_id": context.current_user.id or "eduaihome",
        "additional_messages": additional_messages,
        "stream": True,
    }

    # 6) 处理 SSE：记录会话ID、转发增量文本、记录失败日志
    async for event, data in stream_sse(
        HTTPMethodEnum.POST,
        url,
        headers=headers,
        body=body,
    ):
        if event == "conversation.chat.created" and isinstance(data, dict):
            new_conversation_id = data.get("conversation_id")
            if new_conversation_id:
                session.sub_session_id = new_conversation_id
                await context.db.commit()
        elif event == "conversation.message.delta" and isinstance(data, dict):
            content = data.get("content")
            if content:
                yield str(content)
        elif event == "conversation.chat.failed":
            logger.error(f"[material_review.py] Coze 材料评审失败: {json.dumps(data, ensure_ascii=False)}")
            raise SystemException(f"Coze 材料评审失败: {json.dumps(data, ensure_ascii=False)}")
