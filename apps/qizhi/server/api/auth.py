import os

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from common.models import ApiResponse, BizException
from infra.db import get_db
from service.auth import AuthService
from common.utils.logger import get_logger

logger = get_logger(__name__)


router = APIRouter()


# ---------- 依赖注入 ----------

async def get_auth_service(db: AsyncSession = Depends(get_db)) -> AuthService:
    return AuthService(db)


# ---------- API 接口 ----------

@router.get(
    "/url",
    summary="获取 OAuth 授权地址",
    response_model=ApiResponse[str],
)
async def query_authorize_url(
    service: AuthService = Depends(get_auth_service),
) -> ApiResponse[str]:
    """返回浙大 OAuth 登录授权地址，前端拿到 URL 后应跳转到认证中心完成授权。"""
    url = service.build_authorize_url()
    return ApiResponse.success_response(url)


@router.get(
    "/callback",
    summary="处理 OAuth 回调并签发 Token",
    response_model=ApiResponse[str],
)
async def oauth_callback(
    code: str,
    service: AuthService = Depends(get_auth_service),
) -> ApiResponse[str]:
    """接收 OAuth 回调授权码，完成用户信息同步并签发系统访问 token。"""
    token = await service.login(code)
    return ApiResponse.success_response(token)


@router.post(
    "/test-login",
    summary="测试登录（仅开发环境）",
    response_model=ApiResponse[str],
)
async def test_login(
    name: str,
    zju_id: str,
    service: AuthService = Depends(get_auth_service),
) -> ApiResponse[str]:
    """开发环境专用：直接签发测试用户 token，跳过统一身份认证。"""
    if os.getenv("ENV") not in ("LOCAL", "DEV"):
        logger.warning(f"[auth.py] 测试登录仅在非生产环境可用")
        raise BizException("测试登录仅在非生产环境可用")
    token = await service.test_login(name, zju_id)
    return ApiResponse.success_response(token)
