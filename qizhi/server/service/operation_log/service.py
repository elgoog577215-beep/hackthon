from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from common.models.operation_log import FeatureType
from common.utils.logger import get_logger
from infra.db import UserOperationLog
from infra.db.sequence import generate_id


logger = get_logger(__name__)


async def log_operation(
    db: AsyncSession,
    *,
    user_id: str | None,
    feature_type: FeatureType | str,
    feature_key: str | None = None,
    action: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """写一条用户操作日志。

    设计取舍：埋点写在路由入口处（请求成功 enter 就计数），失败时仅 warning，
    确保业务请求不会因为日志失败被搞挂。匿名用户（无 user_id）直接跳过。
    """
    if not user_id:
        return
    try:
        log = UserOperationLog(
            id=generate_id(),
            user_id=user_id,
            feature_type=feature_type.value if isinstance(feature_type, FeatureType) else feature_type,
            feature_key=feature_key,
            action=action,
            extra=extra,
        )
        db.add(log)
        await db.commit()
    except Exception as e:
        logger.warning(f"[operation_log] 写入日志失败: feature={feature_type} err={e}", exc_info=True)
