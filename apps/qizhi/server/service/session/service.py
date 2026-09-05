from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models import SystemException
from infra.db import Session, SessionHistory, User
from service.session.converters import session_to_detail, session_to_summary
from service.session.models import SessionSummary, SessionDetail
from common.utils.logger import get_logger

logger = get_logger(__name__)


class SessionService:
    """
    会话服务
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ---------- 公共方法 ----------

    async def get_session_by_id(self, id: str, current_user: User) -> SessionDetail | None:
        """根据 id 查询会话详情"""
        session = await self._get_session_or_raise(id, current_user.id)

        histories = (await self.db.execute(
            select(SessionHistory)
            .where(
                SessionHistory.session_id == id,
                SessionHistory.user_id == current_user.id,
            )
            .order_by(SessionHistory.create_time.asc())
        )).scalars().all()
        return session_to_detail(session, histories)

    async def list_sessions(self, current_user: User) -> list[SessionSummary]:
        """查询会话列表"""
        return [session_to_summary(s) for s in (await self.db.execute(
            select(Session)
            .where(Session.user_id == current_user.id)
            .order_by(Session.create_time.desc())
        )).scalars().all()]

    async def delete_session(self, id: str, current_user: User) -> None:
        """删除会话"""
        session = await self._get_session_or_raise(id, current_user.id)
        await self.db.delete(session)
        await self.db.commit()

    # ---------- 私有方法 ----------

    async def _get_session_or_raise(self, session_id: str, user_id: str) -> Session:
        """按 ID 查询会话并校验归属，否则抛出异常。"""
        session = (await self.db.execute(
            select(Session)
            .where(
                Session.id == session_id,
                Session.user_id == user_id,
            )
        )).scalars().first()
        if not session:
            logger.error(f"[service.py] 会话不存在或无权限: {session_id}")
            raise SystemException(f"会话不存在或无权限: {session_id}")
        return session
