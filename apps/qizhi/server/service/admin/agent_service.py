from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models import BizException, SystemException
from common.utils.datetime import format_datetime
from common.utils.logger import get_logger
from infra.db.models.agent import Agent
from service.admin.models import (
    AdminAgentDetail,
    AgentOperationParams,
    AgentReorderParams,
    AgentToggleParams,
)

logger = get_logger(__name__)


class AdminAgentService:
    """运营后台的智能体管理服务。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_all(self) -> list[AdminAgentDetail]:
        rows = (await self.db.execute(
            select(Agent).order_by(Agent.sort_order.asc(), Agent.create_time.asc())
        )).scalars().all()
        return [_to_admin_detail(a) for a in rows]

    async def operate(self, params: AgentOperationParams) -> str | None:
        if params.operation == "create":
            return await self._create(params)
        if params.operation == "update":
            await self._update(params)
            return params.id
        if params.operation == "delete":
            await self._delete(params)
            return None
        logger.warning(f"[agent_service.py] 不支持的操作: {params.operation}")
        raise BizException(f"不支持的操作: {params.operation}")

    async def toggle(self, params: AgentToggleParams) -> None:
        agent = await self._get_or_raise(params.id)
        agent.enabled = params.enabled
        await self.db.commit()

    async def reorder(self, params: AgentReorderParams) -> None:
        """整体重排：按 id_list 给出的顺序，重置全部智能体的 sort_order 为 10/20/30/...

        要求 id_list 覆盖当前所有智能体，否则报错——避免漏行残留旧值导致排序紊乱。
        """
        if not params.id_list:
            logger.warning("[agent_service.py] id_list 不能为空")
            raise BizException("id_list 不能为空")

        # 取所有 agent，确保提交的 id_list 是全集
        all_agents = (await self.db.execute(select(Agent))).scalars().all()
        all_ids = {a.id for a in all_agents}
        provided = set(params.id_list)
        if len(params.id_list) != len(provided):
            logger.warning("[agent_service.py] id_list 中存在重复 ID")
            raise BizException("id_list 中存在重复 ID")
        missing = all_ids - provided
        extra = provided - all_ids
        if missing or extra:
            logger.warning(
                f"[agent_service.py] id_list 必须覆盖所有智能体（缺失 {len(missing)} 个，多余 {len(extra)} 个）"
            )
            raise BizException(
                f"id_list 必须覆盖所有智能体（缺失 {len(missing)} 个，多余 {len(extra)} 个）"
            )

        agent_map = {a.id: a for a in all_agents}
        for idx, aid in enumerate(params.id_list):
            agent_map[aid].sort_order = (idx + 1) * 10
        await self.db.commit()

    # ---------- 私有 ----------

    async def _get_or_raise(self, agent_id: str | None) -> Agent:
        if not agent_id:
            logger.warning("[agent_service.py] 智能体 ID 不能为空")
            raise BizException("智能体 ID 不能为空")
        agent = (await self.db.execute(
            select(Agent).where(Agent.id == agent_id)
        )).scalars().first()
        if not agent:
            logger.error(f"[agent_service.py] 智能体不存在: {agent_id}")
            raise SystemException(f"智能体不存在: {agent_id}")
        return agent

    async def _next_sort_order(self) -> int:
        max_order = (await self.db.execute(
            select(func.max(Agent.sort_order))
        )).scalar()
        return int(max_order or 0) + 10

    async def _create(self, params: AgentOperationParams) -> str:
        if not params.title or not params.title.strip():
            logger.warning("[agent_service.py] 标题不能为空")
            raise BizException("标题不能为空")
        if not params.description or not params.description.strip():
            logger.warning("[agent_service.py] 描述不能为空")
            raise BizException("描述不能为空")
        if not params.icon_path or not params.icon_path.strip():
            logger.warning("[agent_service.py] 图标 SVG path 不能为空")
            raise BizException("图标 SVG path 不能为空")

        sort_order = params.sort_order if params.sort_order is not None else await self._next_sort_order()
        agent = Agent(
            card_key=params.card_key,
            title=params.title.strip(),
            description=params.description.strip(),
            tags=params.tags or [],
            popular=bool(params.popular) if params.popular is not None else False,
            badge_bg=params.badge_bg or "#DEE8FF",
            badge_fg=params.badge_fg or "#2F4AA6",
            icon_path=params.icon_path.strip(),
            href=params.href,
            route_to=params.route_to,
            enabled=bool(params.enabled) if params.enabled is not None else False,
            sort_order=sort_order,
        )
        self.db.add(agent)
        await self.db.commit()
        return agent.id

    async def _update(self, params: AgentOperationParams) -> None:
        agent = await self._get_or_raise(params.id)
        if params.card_key is not None:
            agent.card_key = params.card_key or None
        if params.title is not None:
            agent.title = params.title
        if params.description is not None:
            agent.description = params.description
        if params.tags is not None:
            agent.tags = params.tags
        if params.popular is not None:
            agent.popular = bool(params.popular)
        if params.badge_bg is not None:
            agent.badge_bg = params.badge_bg
        if params.badge_fg is not None:
            agent.badge_fg = params.badge_fg
        if params.icon_path is not None:
            agent.icon_path = params.icon_path
        if params.href is not None:
            agent.href = params.href or None
        if params.route_to is not None:
            agent.route_to = params.route_to or None
        if params.enabled is not None:
            agent.enabled = bool(params.enabled)
        if params.sort_order is not None:
            agent.sort_order = int(params.sort_order)
        await self.db.commit()

    async def _delete(self, params: AgentOperationParams) -> None:
        agent = await self._get_or_raise(params.id)
        await self.db.delete(agent)
        await self.db.commit()


def _to_admin_detail(agent: Agent) -> AdminAgentDetail:
    return AdminAgentDetail(
        id=agent.id,
        card_key=agent.card_key,
        title=agent.title or "",
        description=agent.description or "",
        tags=list(agent.tags or []),
        popular=bool(agent.popular),
        badge_bg=agent.badge_bg or "",
        badge_fg=agent.badge_fg or "",
        icon_path=agent.icon_path or "",
        href=agent.href,
        route_to=agent.route_to,
        sort_order=int(agent.sort_order or 0),
        enabled=bool(agent.enabled),
        create_time=format_datetime(agent.create_time),
        update_time=format_datetime(agent.update_time),
    )
