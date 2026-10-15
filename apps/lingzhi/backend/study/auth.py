"""Explicit local student login for experiments; production uses Qizhi identity.

Local passwords and opaque session hashes stay in the configured data directory.
Neither browser actor headers nor a client-supplied role grant student identity.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import time
import uuid

from fastapi import HTTPException, Request


class LocalStudyAuth:
    def __init__(self, storage, *, enabled: bool | None = None) -> None:
        self.storage = storage
        self.enabled = (os.getenv("LINGZHI_LOCAL_STUDY_AUTH", "").lower() == "true"
                        if enabled is None else enabled)

    def require_enabled(self):
        if not self.enabled or os.getenv("QIZHI_AUTH_VERIFY_URL", "").strip():
            raise HTTPException(403, "请使用启智统一登录")

    @staticmethod
    def digest(password: str, salt: str) -> str:
        return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()

    def login(self, username: str, password: str, *, register: bool = False) -> dict:
        self.require_enabled()
        username = username.strip().lower()
        if not re.fullmatch(r"[a-z0-9_.-]{3,40}", username) or not 8 <= len(password) <= 128:
            raise HTTPException(422, "用户名需为 3–40 位字母、数字或 ._-；密码需为 8–128 位")
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        result = {}

        def update(current):
            current = current or {"users": {}, "sessions": {}}
            users = current["users"]
            user = users.get(username)
            if register:
                if user:
                    raise HTTPException(409, "用户名已使用")
                salt = secrets.token_hex(16)
                user = {"id": f"local-student:{uuid.uuid4()}", "username": username,
                        "salt": salt, "password_hash": self.digest(password, salt)}
                users[username] = user
            # Constant-cost failed login, with the same public error for unknown users.
            candidate = self.digest(password, user["salt"] if user else "00" * 16)
            if not user or not hmac.compare_digest(candidate, user["password_hash"]):
                raise HTTPException(401, "用户名或密码不正确")
            current["sessions"] = {key: value for key, value in current["sessions"].items()
                                   if value["expires_at"] > time.time()}
            current["sessions"][token_hash] = {"owner_id": user["id"], "username": username,
                                              "expires_at": time.time() + 24 * 3600}
            result.update({"token": token, "user": {"id": user["id"], "username": username, "role": "student"}})
            return current

        self.storage.update_data("study_accounts.json", update)
        return result

    def resolve(self, authorization: str) -> dict:
        self.require_enabled()
        if not authorization.lower().startswith("bearer "):
            raise HTTPException(401, "请登录学生学习空间")
        digest = hashlib.sha256(authorization[7:].strip().encode()).hexdigest()
        with self.storage._lock_generic_data("study_accounts.json"):
            accounts = self.storage._read_generic_data_from_disk(
                self.storage._generic_data_path("study_accounts.json")) or {}
        session = (accounts.get("sessions") or {}).get(digest)
        if not session or session["expires_at"] <= time.time():
            raise HTTPException(401, "登录已失效，请重新登录")
        return {"id": session["owner_id"], "username": session["username"], "role": "student"}

    def logout(self, authorization: str):
        self.require_enabled()
        token = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
        digest = hashlib.sha256(token.encode()).hexdigest()
        def update(current):
            current = current or {}
            current.get("sessions", {}).pop(digest, None)
            return current
        self.storage.update_data("study_accounts.json", update)


def study_identity(request: Request) -> dict:
    identity = getattr(request.state, "qizhi_identity", None)
    if identity:
        return {"id": identity.actor_id, "username": identity.actor_id, "role": identity.role}
    if getattr(request.state, "local_study_identity", None):
        return request.state.local_study_identity
    from storage import storage
    return LocalStudyAuth(storage).resolve(request.headers.get("Authorization", ""))
