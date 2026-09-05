from zoneinfo import ZoneInfo

from infra.db import User
from service.user.models import UserDetail


def user_to_detail(user: User | None) -> UserDetail | None:
    if not user:
        return None
    return UserDetail(
        id=user.id,
        zju_id=user.zju_id,
        name=user.name,
        department=user.department,
        phone=user.phone,
        email=user.email,
        role=user.role or "student",
        create_time=user.create_time.astimezone(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S"),
    )
