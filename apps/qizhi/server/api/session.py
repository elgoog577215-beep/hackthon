from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from common.models import ApiResponse
from infra.db import User, get_db
from service.auth import get_current_user
from service.session import SessionDetail, SessionService, SessionSummary


router = APIRouter()


# ---------- 依赖注入 ----------

async def get_session_service(db: AsyncSession = Depends(get_db)) -> SessionService:
    return SessionService(db)


# ---------- API 接口 ----------

@router.get(
    "",
    summary="按 ID 查询会话",
    response_model=ApiResponse[SessionDetail],
)
async def query_session_by_id(
    id: str,
    service: SessionService = Depends(get_session_service),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[SessionDetail]:
    """根据会话 ID 返回单个会话详情。"""
    session = await service.get_session_by_id(id, current_user)
    return ApiResponse.success_response(session)


@router.get(
    "/list",
    summary="查询会话列表",
    response_model=ApiResponse[list[SessionSummary]],
)
async def list_sessions(
    service: SessionService = Depends(get_session_service),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[list[SessionSummary]]:
    """返回当前登录用户可访问的会话列表。"""
    sessions = await service.list_sessions(current_user)
    return ApiResponse.success_response(sessions)


@router.delete(
    "/delete",
    summary="删除会话",
    response_model=ApiResponse[None],
)
async def delete_session(
    id: str,
    service: SessionService = Depends(get_session_service),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[None]:
    """根据会话 ID 删除会话及关联数据。"""
    await service.delete_session(id, current_user)
    return ApiResponse.success_response(None)
