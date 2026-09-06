#!/usr/bin/env python3
"""通过灵知真实 `AIBase` 输出脱敏浙大 Qwen 路由证据。"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "backend"))
logging.getLogger("httpx").setLevel(logging.WARNING)

from ai_base import AIBase  # noqa: E402
from text_ai_provider_policy import EXPECTED_TEXT_MODEL  # noqa: E402


async def _probe(
    *,
    provider_profile: str | None,
    model_role: str,
    use_fast_model: bool,
) -> dict[str, object]:
    provider = AIBase(provider_profile=provider_profile)
    telemetry: list[dict[str, object]] = []
    response = await provider._call_llm(
        '{"probe":true}',
        system_prompt='Return only this JSON object: {"ok":true}',
        use_fast_model=use_fast_model,
        enable_thinking=False,
        retry_count=1,
        max_attempts=1,
        max_tokens=64,
        reject_truncated=True,
        raise_on_failure=True,
        json_mode=True,
        model_role=model_role,
        telemetry_sink=telemetry.append,
    )
    parsed = provider._extract_json(response or "") or {}
    attempts = [
        {
            "model_id": str(item.get("model_id") or ""),
            "provider_route": str(item.get("provider_route") or "primary"),
            "status": str(item.get("status") or "unknown"),
            "duration_ms": int(item.get("duration_ms") or 0),
        }
        for item in telemetry
        if isinstance(item, dict)
    ]
    if parsed.get("ok") is not True:
        raise RuntimeError(f"{model_role or 'general'} probe returned invalid JSON")
    if not attempts or any(
        item["model_id"] != EXPECTED_TEXT_MODEL
        or item["provider_route"] != "primary"
        or item["status"] != "completed"
        for item in attempts
    ):
        raise RuntimeError(f"{model_role or 'general'} probe used an invalid route")
    return {
        "role": model_role or "general",
        "status": "completed",
        "attempts": attempts,
    }


async def main() -> int:
    forbidden = [
        key
        for key in (
            "MODELSCOPE_API_KEY",
            "MODELSCOPE_BASE_URL",
            "MODELSCOPE_MODEL",
        )
        if os.getenv(key)
    ]
    if forbidden:
        raise RuntimeError("forbidden ModelScope text settings remain")

    results = [
        await _probe(
            provider_profile=None,
            model_role="",
            use_fast_model=False,
        ),
        await _probe(
            provider_profile="ppt",
            model_role="ppt_story",
            use_fast_model=False,
        ),
        await _probe(
            provider_profile="ppt",
            model_role="ppt_visual",
            use_fast_model=True,
        ),
    ]
    print(json.dumps({"model": EXPECTED_TEXT_MODEL, "routes": results}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
