from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models import BizException
from infra.db import User
from service.user.models import UserUpdateParams
from common.utils.logger import get_logger

logger = get_logger(__name__)


class UserService:
    """
    用户服务
    """

    def __init__(self, db: AsyncSession):
        self.db = db


    # ---------- 公共方法 ----------

    async def update_user(self, params: UserUpdateParams, current_user: User) -> None:
        """更新当前用户资料"""
        # phone/email 都走"唯一性预检查"，避免触发数据库唯一索引异常
        if params.phone:
            user_by_phone = (await self.db.execute(select(User).where(User.phone == params.phone))).scalars().first()
            if user_by_phone:
                logger.warning(f"[service.py] 手机号已被注册: {params.phone}")
                raise BizException(f"手机号已被注册: {params.phone}")
            current_user.phone = params.phone

        if params.email:
            user_by_email = (await self.db.execute(select(User).where(User.email == params.email))).scalars().first()
            if user_by_email:
                logger.warning(f"[service.py] 邮箱已被注册: {params.email}")
                raise BizException(f"邮箱已被注册: {params.email}")
            current_user.email = params.email

        await self.db.commit()

    async def delete_user(self, current_user: User) -> None:
        """删除用户及其相关数据"""
        # 依赖数据库外键级联清理关联数据
        await self.db.delete(current_user)
        await self.db.commit()
