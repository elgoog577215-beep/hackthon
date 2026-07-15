"""Local, server-side LLM provider profile storage.

Secrets deliberately never leave this module in API responses.  The file is
intended for a single-user local deployment and is excluded from Git.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from threading import RLock
from typing import Any


class LLMProfileStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or Path(__file__).parent / "data" / "llm_profiles.json"
        self._lock = RLock()
        self._revision = 0

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"active_profile_id": None, "profiles": []}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(payload.get("profiles"), list):
                return payload
        except (OSError, json.JSONDecodeError):
            pass
        return {"active_profile_id": None, "profiles": []}

    def _write(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass
        self._revision += 1

    @staticmethod
    def _summary(profile: dict[str, Any], active_id: str | None) -> dict[str, Any]:
        return {
            "id": profile["id"],
            "name": profile["name"],
            "api_base": profile["api_base"],
            "smart_model": profile.get("smart_model", ""),
            "fast_model": profile.get("fast_model", ""),
            "has_api_key": bool(profile.get("api_key")),
            "is_active": profile["id"] == active_id,
        }

    def list(self) -> dict[str, Any]:
        with self._lock:
            payload = self._read()
            active_id = payload.get("active_profile_id")
            return {
                "active_profile_id": active_id,
                "profiles": [self._summary(item, active_id) for item in payload["profiles"]],
            }

    def create(self, data: dict[str, str], activate: bool = True) -> dict[str, Any]:
        with self._lock:
            payload = self._read()
            profile = {"id": str(uuid.uuid4()), **data}
            payload["profiles"].append(profile)
            if activate or not payload.get("active_profile_id"):
                payload["active_profile_id"] = profile["id"]
            self._write(payload)
            return self._summary(profile, payload["active_profile_id"])

    def activate(self, profile_id: str) -> dict[str, Any]:
        with self._lock:
            payload = self._read()
            profile = next((item for item in payload["profiles"] if item["id"] == profile_id), None)
            if profile is None:
                raise KeyError(profile_id)
            payload["active_profile_id"] = profile_id
            self._write(payload)
            return self._summary(profile, profile_id)

    def config_for(self, profile_id: str) -> dict[str, str]:
        with self._lock:
            profile = next((item for item in self._read()["profiles"] if item["id"] == profile_id), None)
            if profile is None:
                raise KeyError(profile_id)
            return {
                "api_key": profile.get("api_key", ""),
                "api_base": profile.get("api_base", ""),
                "smart_model": profile.get("smart_model", ""),
                "fast_model": profile.get("fast_model", ""),
            }

    def active_config(self) -> tuple[int, dict[str, str]]:
        """Return the active local profile, falling back to environment config."""
        with self._lock:
            payload = self._read()
            active_id = payload.get("active_profile_id")
            profile = next((item for item in payload["profiles"] if item["id"] == active_id), None)
            if profile:
                return self._revision, {
                    "api_key": profile.get("api_key", ""),
                    "api_base": profile.get("api_base", ""),
                    "smart_model": profile.get("smart_model", ""),
                    "fast_model": profile.get("fast_model", ""),
                }
            return self._revision, {
                "api_key": os.getenv("AI_API_KEY", ""),
                "api_base": os.getenv("AI_API_BASE", "https://api-inference.modelscope.cn/v1"),
                "smart_model": os.getenv("AI_MODEL", ""),
                "fast_model": os.getenv("AI_MODEL_FAST", ""),
            }


llm_profile_store = LLMProfileStore()
