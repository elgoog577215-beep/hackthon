from fastapi import Depends

from common.config import settings
from common.models.constants import UserRole
from common.models.exception import AuthException
from common.utils.logger import get_logger
from infra.db import User
from service.auth import get_current_user

logger = get_logger(__name__)


def is_admin_user(user: User | None) -> bool:
    """判断给定用户是否为管理员：优先看 DB role；ADMIN_ZJU_IDS 作为兜底（启动 bootstrap 之前的 race）。"""
    if user is None:
        return False
    if user.role == UserRole.ADMIN.value:
        return True
    return bool(user.zju_id) and user.zju_id in settings.ADMIN_ZJU_IDS


async def get_current_admin(current_user: User = Depends(get_current_user)) -> User:
    """运营后台路由的鉴权依赖。"""
    if not is_admin_user(current_user):
        logger.warning(f"[auth.py] 无管理员权限: zju_id={current_user.zju_id if current_user else None}")
        raise AuthException("无管理员权限")
    return current_user
