"""Fail-closed client for the isolated formal code runner."""

from __future__ import annotations

import asyncio
from copy import deepcopy
import os
from typing import Any

import requests


class CodeRunnerUnavailable(RuntimeError):
    pass


class CodeRunnerClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        token: str | None = None,
    ) -> None:
        self.base_url = (
            base_url
            if base_url is not None
            else os.getenv("FORMAL_RUNNER_URL", "")
        ).rstrip("/")
        self.token = (
            token
            if token is not None
            else os.getenv("FORMAL_RUNNER_TOKEN", "")
        )

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.token)

    async def register_test_bundle(
        self,
        *,
        language: str,
        tests: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/internal/test-bundles",
            {
                "language": language,
                "tests": deepcopy(tests),
            },
        )

    async def judge(
        self,
        *,
        task_revision_id: str,
        language: str,
        code: str,
        test_bundle_id: str,
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/internal/judge",
            {
                "task_revision_id": task_revision_id,
                "language": language,
                "code": code,
                "test_bundle_id": test_bundle_id,
            },
        )

    async def health(self) -> dict[str, Any]:
        return await self._request("GET", "/internal/health", None)

    async def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if not self.configured:
            raise CodeRunnerUnavailable("formal_runner_not_configured")

        def call() -> dict[str, Any]:
            try:
                response = requests.request(
                    method,
                    f"{self.base_url}{path}",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.token}",
                    },
                    timeout=(2, 35),
                )
                response.raise_for_status()
                value = response.json()
            except Exception as exc:
                raise CodeRunnerUnavailable(
                    "formal_runner_unavailable"
                ) from exc
            if not isinstance(value, dict):
                raise CodeRunnerUnavailable(
                    "formal_runner_invalid_response"
                )
            return value

        return await asyncio.to_thread(call)


code_runner_client = CodeRunnerClient()


__all__ = [
    "CodeRunnerClient",
    "CodeRunnerUnavailable",
    "code_runner_client",
]
