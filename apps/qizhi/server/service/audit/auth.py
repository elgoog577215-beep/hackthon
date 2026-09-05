import secrets

from fastapi import Header

from common.config import settings
from common.models.exception import AuthException
from common.utils.logger import get_logger


logger = get_logger(__name__)


async def require_audit_service_token(
    x_audit_service_token: str | None = Header(default=None, alias="X-Audit-Service-Token"),
) -> None:
    """校验 X-Audit-Service-Token，匹配 settings.AUDIT_SERVICE_TOKEN。

    secrets.compare_digest 做常量时间比较，避免时序攻击；token 未配置时端点退化为关闭。
    """
    expected = settings.AUDIT_SERVICE_TOKEN
    if not expected:
        logger.warning("[audit.auth] AUDIT_SERVICE_TOKEN 未配置，拒绝所有请求")
        raise AuthException("audit service disabled")
    if not x_audit_service_token or not secrets.compare_digest(x_audit_service_token, expected):
        logger.warning("[audit.auth] 无效或缺失 X-Audit-Service-Token")
        raise AuthException("invalid audit service token")
