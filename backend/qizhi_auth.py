"""Trusted Qizhi session bridge for production Lingzhi deployments.

Lingzhi keeps ``X-User-Id`` as its internal actor contract. When
``QIZHI_AUTH_VERIFY_URL`` is configured, the browser-provided actor is ignored:
the Qizhi bearer token is verified against Qizhi's current-user endpoint and a
stable ``qizhi:<user-id>`` actor is injected into the request instead.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import time
from dataclasses import dataclass
from typing import Any

import requests
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


AUTH_REQUIRED_CODE = "qizhi_auth_required"
AUTH_FORBIDDEN_CODE = "qizhi_role_forbidden"
AUTH_UNAVAILABLE_CODE = "qizhi_auth_unavailable"
DEFAULT_ALLOWED_ROLES = frozenset({"teacher", "admin"})


@dataclass(frozen=True)
class QizhiIdentity:
    actor_id: str
    role: str


class QizhiAuthError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


class QizhiIdentityVerifier:
    """Resolve Qizhi bearer tokens without copying the Qizhi JWT secret."""

    def __init__(
        self,
        verify_url: str,
        *,
        allowed_roles: set[str] | frozenset[str] = DEFAULT_ALLOWED_ROLES,
        timeout_seconds: float = 5.0,
        cache_ttl_seconds: float = 60.0,
        max_cache_entries: int = 2048,
    ) -> None:
        self.verify_url = str(verify_url or "").strip()
        self.allowed_roles = frozenset(
            str(role).strip() for role in allowed_roles if str(role).strip()
        )
        self.timeout_seconds = timeout_seconds
        self.cache_ttl_seconds = cache_ttl_seconds
        self.max_cache_entries = max_cache_entries
        self._cache: dict[str, tuple[float, QizhiIdentity]] = {}
        self._lock = asyncio.Lock()

    @property
    def enabled(self) -> bool:
        return bool(self.verify_url)

    async def resolve(self, authorization: str | None) -> QizhiIdentity:
        normalized = str(authorization or "").strip()
        if not normalized.lower().startswith("bearer ") or not normalized[7:].strip():
            raise QizhiAuthError(401, AUTH_REQUIRED_CODE, "请先通过启智统一登录")

        cache_key = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        now = time.monotonic()
        async with self._lock:
            cached = self._cache.get(cache_key)
            if cached and cached[0] > now:
                return cached[1]
            if cached:
                self._cache.pop(cache_key, None)

        identity = await asyncio.to_thread(self._verify_upstream, normalized)
        async with self._lock:
            if len(self._cache) >= self.max_cache_entries:
                oldest_key = min(self._cache, key=lambda key: self._cache[key][0])
                self._cache.pop(oldest_key, None)
            self._cache[cache_key] = (now + self.cache_ttl_seconds, identity)
        return identity

    def _verify_upstream(self, authorization: str) -> QizhiIdentity:
        try:
            response = requests.get(
                self.verify_url,
                headers={"Authorization": authorization, "Accept": "application/json"},
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise QizhiAuthError(
                503,
                AUTH_UNAVAILABLE_CODE,
                "统一身份服务暂时不可用，请稍后重试",
            ) from exc

        if response.status_code in {401, 403}:
            raise QizhiAuthError(401, AUTH_REQUIRED_CODE, "登录已失效，请重新登录")
        if response.status_code != 200:
            raise QizhiAuthError(
                503,
                AUTH_UNAVAILABLE_CODE,
                "统一身份服务暂时不可用，请稍后重试",
            )

        try:
            payload: dict[str, Any] = response.json()
        except ValueError as exc:
            raise QizhiAuthError(
                503,
                AUTH_UNAVAILABLE_CODE,
                "统一身份服务返回异常，请稍后重试",
            ) from exc

        user = payload.get("data") if payload.get("success") is True else None
        user_id = str(user.get("id") if isinstance(user, dict) else "").strip()
        role = str(user.get("role") if isinstance(user, dict) else "").strip().lower()
        if not user_id:
            raise QizhiAuthError(401, AUTH_REQUIRED_CODE, "登录已失效，请重新登录")
        if role not in self.allowed_roles:
            raise QizhiAuthError(403, AUTH_FORBIDDEN_CODE, "当前账号没有教师课程权限")
        return QizhiIdentity(actor_id=f"qizhi:{user_id}", role=role)


def configured_verifier() -> QizhiIdentityVerifier:
    allowed = {
        value.strip().lower()
        for value in os.getenv("QIZHI_AUTH_ALLOWED_ROLES", "teacher,admin").split(",")
        if value.strip()
    }
    return QizhiIdentityVerifier(
        os.getenv("QIZHI_AUTH_VERIFY_URL", ""),
        allowed_roles=allowed or DEFAULT_ALLOWED_ROLES,
        timeout_seconds=float(os.getenv("QIZHI_AUTH_TIMEOUT_SECONDS", "5")),
        cache_ttl_seconds=float(os.getenv("QIZHI_AUTH_CACHE_TTL_SECONDS", "60")),
    )


def _replace_header(request: Request, name: str, value: str) -> None:
    target = name.lower().encode("latin-1")
    headers = [
        item for item in request.scope.get("headers", []) if item[0].lower() != target
    ]
    headers.append((target, value.encode("latin-1")))
    request.scope["headers"] = headers


def auth_error_response(exc: QizhiAuthError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": {"code": exc.code, "message": exc.message}},
    )


class QizhiIdentityMiddleware(BaseHTTPMiddleware):
    """Require Qizhi teacher/admin sessions for production API requests."""

    def __init__(self, app, *, verifier: QizhiIdentityVerifier) -> None:
        super().__init__(app)
        self.verifier = verifier

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        path = request.url.path
        protected = path.startswith("/api/") and path != "/api/health"
        if not self.verifier.enabled or not protected or request.method == "OPTIONS":
            return await call_next(request)
        try:
            identity = await self.verifier.resolve(request.headers.get("Authorization"))
        except QizhiAuthError as exc:
            return auth_error_response(exc)
        _replace_header(request, "X-User-Id", identity.actor_id)
        _replace_header(request, "X-Qizhi-Role", identity.role)
        return await call_next(request)


def websocket_authorization(websocket) -> str:
    """Read a bearer token from a non-echoed WebSocket subprotocol entry."""
    values = [
        value.strip()
        for value in websocket.headers.get("sec-websocket-protocol", "").split(",")
    ]
    prefix = "qizhi-bearer."
    token = next(
        (value[len(prefix) :] for value in values if value.startswith(prefix)),
        "",
    )
    return f"Bearer {token}" if token else ""


__all__ = [
    "AUTH_FORBIDDEN_CODE",
    "AUTH_REQUIRED_CODE",
    "AUTH_UNAVAILABLE_CODE",
    "QizhiAuthError",
    "QizhiIdentity",
    "QizhiIdentityMiddleware",
    "QizhiIdentityVerifier",
    "auth_error_response",
    "configured_verifier",
    "websocket_authorization",
]
