from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from infra.db.models.agent import Agent
from service.admin.models import PublicAgentDetail


class AgentPublicService:
    """对外公开的智能体广场服务：仅返回 enabled=True 的卡片。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_published_agents(self) -> list[PublicAgentDetail]:
        rows = (await self.db.execute(
            select(Agent)
            .where(Agent.enabled.is_(True))
            .order_by(Agent.sort_order.asc(), Agent.create_time.asc())
        )).scalars().all()
        return [_to_public(a) for a in rows]


def _to_public(agent: Agent) -> PublicAgentDetail:
    return PublicAgentDetail(
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
    )
