import json
from enum import Enum
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from common.utils.logger import get_logger
from infra.db import AuditLog
from infra.db.sequence import generate_id


logger = get_logger(__name__)


PAYLOAD_MAX_BYTES = 8 * 1024
PAYLOAD_PREVIEW_BYTES = 1024
ACTION_MAX_LEN = 100
TARGET_TYPE_MAX_LEN = 50
TARGET_LABEL_MAX_LEN = 200
ACTOR_TYPE_MAX_LEN = 20
ACTOR_LABEL_MAX_LEN = 200
RESULT_MAX_LEN = 20
USER_AGENT_MAX_LEN = 500
IP_MAX_LEN = 64
IDEMPOTENCY_KEY_MAX_LEN = 128


_REDACT_KEYS: set[str] = {
    "password", "passwd", "pwd",
    "token", "access_token", "refresh_token", "id_token",
    "secret", "api_key", "apikey",
    "authorization", "auth",
    "cookie", "credential", "credentials",
}


class AuditActorType(str, Enum):
    """审计日志责任主体类型。

    actor_type 永远由路由层根据鉴权决定，不接受请求体决定，以免绕过权限伪装。
    """
    ADMIN = "admin"
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"


def redact_payload(value: Any) -> Any:
    """递归把命中 _REDACT_KEYS 的值替换为 '***'。dict / list 外原样返回。"""
    if isinstance(value, dict):
        return {
            k: ("***" if isinstance(k, str) and k.lower() in _REDACT_KEYS else redact_payload(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact_payload(item) for item in value]
    return value


def _truncate_json(value: Any) -> Any:
    """JSON 序列化后超过 8KiB 的载荷转成预览块。"""
    if value is None:
        return None
    try:
        s = json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return {"_truncated": True, "_reason": "non-json", "_repr": repr(value)[:PAYLOAD_PREVIEW_BYTES]}
    if len(s.encode("utf-8")) <= PAYLOAD_MAX_BYTES:
        return value
    return {
        "_truncated": True,
        "_size": len(s),
        "_preview": s[:PAYLOAD_PREVIEW_BYTES],
    }


def _trim(value: str | None, max_len: int) -> str | None:
    if value is None:
        return None
    if len(value) <= max_len:
        return value
    return value[:max_len]


async def log_audit(
    db: AsyncSession,
    *,
    actor_type: AuditActorType | str,
    action: str,
    actor_id: str | None = None,
    actor_label: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    target_label: str | None = None,
    payload: dict[str, Any] | None = None,
    result: str | None = None,
    request_ip: str | None = None,
    user_agent: str | None = None,
    extra: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
) -> None:
    """写一条审计日志。

    Fail-safe：与 log_operation 同款 —— 任何异常都吞并 warning，绝不向调用栈外抛错误污染业务请求。
    (actor_type, idempotency_key) 冲突的 IntegrityError 也在这里被吞，正是想要的重试语义。
    """
    try:
        actor_type_value = (
            actor_type.value if isinstance(actor_type, AuditActorType) else str(actor_type)
        )
        log = AuditLog(
            id=generate_id(),
            actor_type=_trim(actor_type_value, ACTOR_TYPE_MAX_LEN) or AuditActorType.SYSTEM.value,
            actor_id=actor_id,
            actor_label=_trim(actor_label, ACTOR_LABEL_MAX_LEN),
            action=_trim(action, ACTION_MAX_LEN) or "unknown",
            target_type=_trim(target_type, TARGET_TYPE_MAX_LEN),
            target_id=target_id,
            target_label=_trim(target_label, TARGET_LABEL_MAX_LEN),
            payload=_truncate_json(redact_payload(payload)) if payload is not None else None,
            result=_trim(result, RESULT_MAX_LEN),
            request_ip=_trim(request_ip, IP_MAX_LEN),
            user_agent=_trim(user_agent, USER_AGENT_MAX_LEN),
            extra=_truncate_json(redact_payload(extra)) if extra is not None else None,
            idempotency_key=_trim(idempotency_key, IDEMPOTENCY_KEY_MAX_LEN),
        )
        db.add(log)
        await db.commit()
    except Exception as e:
        logger.warning(
            f"[audit] 写入审计日志失败: action={action} actor_type={actor_type} err={e}",
            exc_info=True,
        )
        try:
            await db.rollback()
        except Exception:
            pass
