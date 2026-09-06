"""AI 生成链路的资源访问边界。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from infra.db import Resource


async def get_owned_resource(
    db: AsyncSession,
    resource_id: str,
    creator_id: str,
) -> Resource | None:
    """只返回属于当前用户的资源，避免 Agent 绕过 ResourceService 的权限过滤。"""
    return (
        await db.execute(
            select(Resource).where(
                Resource.id == resource_id,
                Resource.creator_id == creator_id,
            )
        )
    ).scalars().first()
