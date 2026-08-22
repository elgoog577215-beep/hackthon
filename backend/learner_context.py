"""Request actor boundaries shared by teacher and learner domains.

``X-User-Id`` is still a lightweight local identity rather than authentication,
but it must be stable anywhere ownership or private learning state is persisted.
Teacher routes use the actor helpers; learner routes keep their domain-specific
error contract through the compatibility helpers below.
"""

from __future__ import annotations

from fastapi import HTTPException


DEFAULT_USER_ID = "default_user"
LEARNER_ID_HEADER = "X-User-Id"


def resolve_user_id(value: str | None = None) -> str:
    """Resolve the identity used by read-only legacy compatibility code."""
    user_id = str(value or "").strip()
    return user_id or DEFAULT_USER_ID


def resolve_actor_id(value: str | None = None) -> str:
    """Resolve a request actor for read-only legacy compatibility code."""
    return resolve_user_id(value)


def require_actor_id(value: str | None) -> str:
    """Require a stable, non-shared actor for ownership-scoped operations."""
    actor_id = str(value or "").strip()
    if not actor_id or actor_id == DEFAULT_USER_ID:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "actor_identity_required",
                "message": "当前操作需要稳定的用户身份",
            },
        )
    if len(actor_id) > 160:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "actor_identity_invalid",
                "message": "用户身份格式无效",
            },
        )
    return actor_id


def require_user_id(value: str | None) -> str:
    """Require a stable, non-shared identity for learner-scoped operations."""
    user_id = str(value or "").strip()
    if not user_id or user_id == DEFAULT_USER_ID:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "learner_identity_required",
                "message": "正式学习写入需要稳定的学习者身份",
            },
        )
    if len(user_id) > 160:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "learner_identity_invalid",
                "message": "学习者身份格式无效",
            },
        )
    return user_id


__all__ = [
    "DEFAULT_USER_ID",
    "LEARNER_ID_HEADER",
    "require_actor_id",
    "require_user_id",
    "resolve_actor_id",
    "resolve_user_id",
]
