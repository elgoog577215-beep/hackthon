"""Explicit password-free learner identity for loopback development only."""

from __future__ import annotations

import os
from urllib.parse import urlsplit

from fastapi import Request


def development_identity(request: Request) -> dict | None:
    if (
        os.getenv("LINGZHI_RUNTIME_MODE") != "development"
        or os.getenv("LINGZHI_DEV_SURFACE") != "student"
        or os.getenv("QIZHI_AUTH_VERIFY_URL", "").strip()
    ):
        return None
    local = {"127.0.0.1", "::1", "localhost"}
    if not request.client or request.client.host not in local or request.url.hostname not in local:
        return None
    if request.headers.get("Forwarded") or request.headers.get("X-Forwarded-For"):
        return None
    origin = request.headers.get("Origin")
    if origin:
        try:
            parsed = urlsplit(origin)
        except ValueError:
            return None
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in local:
            return None
    return {"id": "local-student:development", "username": "开发学习空间", "role": "student"}
