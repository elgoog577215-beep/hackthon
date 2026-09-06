from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from common.models import ApiResponse
from infra.db import User, get_db
from service.auth import get_current_user
from service.user import (
    UserDeleteParams,
    UserDetail,
    UserOperationParams,
    UserService,
    UserUpdateParams,
    user_to_detail,
)


router = APIRouter()


# ---------- 依赖注入 ----------

async def get_user_service(db: AsyncSession = Depends(get_db)) -> UserService:
    return UserService(db)


# ---------- API 接口 ----------

@router.get(
    "/current",
    summary="查询当前登录用户",
    response_model=ApiResponse[UserDetail],
)
async def query_current_user(
    current_user: User = Depends(get_current_user),
) -> ApiResponse[UserDetail]:
    """根据认证信息返回当前登录用户详情。"""
    return ApiResponse.success_response(user_to_detail(current_user))


@router.post(
    "/operation",
    summary="执行用户资料操作",
    response_model=ApiResponse[None],
)
async def operate_user(
    params: UserOperationParams,
    service: UserService = Depends(get_user_service),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[None]:
    """对当前用户执行资料操作，具体行为由 operation 字段决定。"""
    match params:
        case UserUpdateParams():
            await service.update_user(params, current_user)
        case UserDeleteParams():
            await service.delete_user(current_user)
    return ApiResponse.success_response(None)
