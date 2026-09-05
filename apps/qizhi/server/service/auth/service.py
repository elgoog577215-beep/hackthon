import jwt
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urlencode
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.config import settings
from common.models.constants import (
    DEFAULT_HTTP_TIMEOUT,
    UserRole,
    ZJU_OAUTH_ACCESS_TOKEN_URL,
    ZJU_OAUTH_AUTHORIZE_URL,
    ZJU_OAUTH_PROFILE_URL,
)
from common.utils.logger import get_logger
from common.models.exception import AuthException, SystemException
from common.utils.http import HTTPMethodEnum, http_request
from infra.db import User, get_db
from infra.db.sequence import generate_id

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/user/login", auto_error=False)

logger = get_logger(__name__)

class AuthService:
    """ZJU OAuth服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ---------- 公共方法 ----------

    @staticmethod
    def create_access_token(user_id: str) -> str:
        """创建JWT Token"""
        to_encode = {
            "data": user_id,
            "exp": datetime.now(timezone.utc) + timedelta(seconds=settings.ACCESS_TOKEN_EXPIRE_SECONDS),
        }
        return jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256")

    @staticmethod
    def build_authorize_url() -> str:
        """构造授权URL"""
        params = {
            "response_type": "code",
            "client_id": settings.APP_KEY,
            "redirect_uri": settings.APP_URL,
        }
        query = urlencode(params, safe="-_.~", quote_via=quote)
        return f"{ZJU_OAUTH_AUTHORIZE_URL}?{query}"

    async def login(self, code: str) -> str:
        """根据授权码获取用户信息，并生成 JWT Token"""
        # 步骤 1：code -> access_token
        # code 换 access_token
        params = {
            "client_id": settings.APP_KEY,
            "client_secret": settings.APP_SECRET,
            "code": code,
            "redirect_uri": settings.APP_URL,
        }
        try:
            result = await http_request(
                HTTPMethodEnum.GET,
                ZJU_OAUTH_ACCESS_TOKEN_URL,
                params=params,
                timeout=DEFAULT_HTTP_TIMEOUT,
            )
            access_token = result.get("access_token")
        except Exception as e:
            logger.error(f"[service.py] 获取 access_token 失败: {e}")
            raise SystemException(f"获取 access_token 失败: {e}")

        # 步骤 2：access_token -> 用户档案
        params = {
            "access_token": access_token,
        }
        try:
            data = await http_request(
                HTTPMethodEnum.GET,
                ZJU_OAUTH_PROFILE_URL,
                params=params,
                timeout=DEFAULT_HTTP_TIMEOUT,
            )
            attributes = data.get("attributes")
            logger.info(f"[service.py] ZJU OAuth profile attributes: {attributes}")
            for attribute in attributes:
                if "CODE" in attribute:
                    zju_id = attribute["CODE"]
                elif "XM" in attribute:
                    name = attribute["XM"]
                elif "DWMC" in attribute:
                    department = attribute["DWMC"]
        except Exception as e:
            logger.error(f"[service.py] 获取用户信息失败: {e}")
            raise SystemException(f"获取用户信息失败: {e}")

        # 步骤 3：本地用户映射（存在即复用，不存在则自动创建）
        result = await self.db.execute(select(User).where(User.zju_id == zju_id))
        existing_user = result.scalars().first()

        # 用户已存在
        if existing_user:
            return AuthService.create_access_token(existing_user.id)

        # 用户不存在，自动创建新用户。白名单内的 zju_id 直接落 admin，免再开第二次后台。
        role = UserRole.ADMIN.value if zju_id in settings.ADMIN_ZJU_IDS else UserRole.TEACHER.value
        user = User(
            zju_id=zju_id,
            name=name,
            department=department,
            role=role,
        )
        self.db.add(user)
        await self.db.commit()
        return AuthService.create_access_token(user.id)

    async def test_login(self, name: str, zju_id: str) -> str:
        """创建或使用测试用户，签发 token（仅开发环境）"""
        logger.info("测试登录")
        user = (await self.db.execute(select(User).where(User.zju_id == zju_id))).scalars().first()
        if not user:
            role = UserRole.ADMIN.value if zju_id in settings.ADMIN_ZJU_IDS else UserRole.STUDENT.value
            user = User(
                id=generate_id(),
                zju_id=zju_id,
                name=name,
                department="启智项目组",
                role=role,
            )
            self.db.add(user)
            await self.db.commit()
        return AuthService.create_access_token(user.id)


async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """获取当前登录用户（从 Header 读取 token）"""
    if not token:
        logger.warning(f"[service.py] 未提供认证令牌")
        raise AuthException("未提供认证令牌")

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        user_id = payload.get("data")
        if not user_id:
            logger.warning(f"[service.py] 认证令牌无效")
            raise AuthException("认证令牌无效")

        user = (await db.execute(select(User).where(User.id == user_id))).scalars().first()
        if not user:
            logger.warning(f"[service.py] 用户不存在")
            raise AuthException("用户不存在")

        return user
    except jwt.PyJWTError:
        logger.warning(f"[service.py] 认证令牌无效")
        raise AuthException("认证令牌无效")


def require_roles(*allowed: UserRole):
    """生成 FastAPI 依赖：当前用户的 role 必须命中 allowed 中之一，否则 401。"""
    allowed_values = {r.value for r in allowed}

    async def _guard(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed_values:
            logger.warning(
                f"[service.py] role denied: have={user.role} need={sorted(allowed_values)}"
            )
            raise AuthException("无操作权限")
        return user

    return _guard


# 教师可用端点：admin 默认覆盖 teacher 场景，避免管理员因为 role=admin 反而进不了教师页
get_current_teacher = require_roles(UserRole.TEACHER, UserRole.ADMIN)
