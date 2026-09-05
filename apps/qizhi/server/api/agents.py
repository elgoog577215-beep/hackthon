from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from common.models import ApiResponse
from common.models.operation_log import FeatureType
from infra.db import User, get_db
from service.admin import AgentPublicService, PublicAgentDetail
from service.auth import get_current_user
from service.operation_log import log_operation


router = APIRouter()


async def get_agent_public_service(db: AsyncSession = Depends(get_db)) -> AgentPublicService:
    return AgentPublicService(db)


@router.get(
    "/public",
    summary="查询已上架的智能体广场列表（公开接口，不需登录）",
    response_model=ApiResponse[list[PublicAgentDetail]],
)
async def list_public_agents(
    service: AgentPublicService = Depends(get_agent_public_service),
) -> ApiResponse[list[PublicAgentDetail]]:
    """首页智能体广场拉取使用：返回所有已上架的智能体，按 sort_order 升序。

    首页对未登录用户可见，因此该接口不要求登录。
    """
    agents = await service.list_published_agents()
    return ApiResponse.success_response(agents)


@router.post(
    "/visit/{agent_id}",
    summary="记录智能体访问（埋点专用，不阻塞跳转）",
    response_model=ApiResponse[None],
)
async def visit_agent(
    agent_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[None]:
    """前端在用户点击首页智能体卡片时调用一次。仅记录埋点，不做其他业务动作。"""
    await log_operation(
        db,
        user_id=current_user.id,
        feature_type=FeatureType.AGENT,
        feature_key=agent_id,
        action="visit",
    )
    return ApiResponse.success_response(None)
