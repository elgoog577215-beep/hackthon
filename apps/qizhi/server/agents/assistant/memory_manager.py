from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.utils import compose_user_message
from infra.db import SessionHistory


class MemoryManager:
    """
    记忆管理器
    """

    @staticmethod
    async def query_messages(session_id: str, db: AsyncSession) -> list[dict[str, str]]:
        # 仅加载"成功消息"，避免失败记录污染上下文
        histories = (await db.execute(
            select(SessionHistory)
            .where(SessionHistory.session_id == session_id, SessionHistory.status == "success")
            .order_by(SessionHistory.create_time.asc())
        )).scalars().all()
        # 历史 user 消息若带附件解析文本，重新拼回上下文（与当前轮注入逻辑一致），
        # 保证跨轮也能让模型看到此前上传的文档内容；assistant 消息无附件文本，原样返回。
        return [
            {
                "role": item.role,
                "content": compose_user_message(item.message_content or "", item.file_contents),
            }
            for item in histories
        ]

    @staticmethod
    async def insert_message(
        *,
        db: AsyncSession,
        session_id: str,
        chat_id: str,
        user_id: str,
        role: str,
        message: str,
        message_type: str = "text",
        file_paths: list[str] | None = None,
        file_contents: str | None = None,
        cost_time: int | None = None,
        status: str = "success",
        error_message: str | None = None,
    ) -> None:
        # 每轮都立即 commit，保证流式中断时也能保留已产生日志
        record = SessionHistory(
            session_id=session_id,
            chat_id=chat_id,
            user_id=user_id,
            role=role,
            message_type=message_type,
            message_content=message,
            file_paths=file_paths or [],
            file_contents=file_contents or None,
            cost_time=cost_time,
            status=status,
            error_message=error_message,
        )
        db.add(record)
        await db.commit()

    @staticmethod
    async def clear_session_history(session_id: str, db: AsyncSession) -> None:
        await db.execute(delete(SessionHistory).where(SessionHistory.session_id == session_id))
        await db.commit()
