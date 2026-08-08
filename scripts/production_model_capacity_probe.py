#!/usr/bin/env python3
"""Probe production ModelScope model availability with minimal token usage."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
from typing import Any

import httpx


CANDIDATES = (
    "deepseek-ai/DeepSeek-V4-Pro",
    "deepseek-ai/DeepSeek-V4-Flash-0731",
    "Qwen/Qwen3.5-27B",
    "Qwen/Qwen3.5-35B-A3B",
    "Qwen/Qwen3-30B-A3B",
    "Qwen/Qwen3-8B",
    "stepfun-ai/Step-3.5-Flash",
    "ZhipuAI/GLM-4.7-Flash",
)


def classify_error(status_code: int, code: str, message: str) -> str:
    normalized = f"{code} {message}".casefold()
    if "insufficient balance" in normalized or "arrearage" in normalized:
        return "balance_exhausted"
    if "insufficient_quota" in normalized or "allocated quota" in normalized:
        return "token_quota_limited"
    if "rate limit" in normalized or "too many requests" in normalized:
        return "request_rate_limited"
    if status_code in {401, 403}:
        return "access_denied"
    if status_code == 404 or "model_not" in normalized:
        return "model_unavailable"
    return "request_failed"


async def main() -> dict[str, Any]:
    api_key = str(os.getenv("MODELSCOPE_API_KEY") or "").strip()
    base_url = str(
        os.getenv("MODELSCOPE_BASE_URL")
        or "https://api-inference.modelscope.cn/v1/"
    ).rstrip("/")
    if not api_key:
        raise RuntimeError("MODELSCOPE_API_KEY is not configured")

    headers = {"Authorization": f"Bearer {api_key}"}
    timeout = httpx.Timeout(60.0, connect=15.0)
    async with httpx.AsyncClient(headers=headers, timeout=timeout) as client:
        catalog_response = await client.get(f"{base_url}/models")
        catalog_response.raise_for_status()
        catalog_payload = catalog_response.json()
        catalog = {
            str(item.get("id") or "")
            for item in catalog_payload.get("data") or []
            if isinstance(item, dict) and item.get("id")
        }
        results: list[dict[str, Any]] = []
        for model in CANDIDATES:
            if model not in catalog:
                results.append({
                    "model": model,
                    "status": "not_in_catalog",
                    "http_status": None,
                    "latency_ms": 0,
                })
                continue
            started = time.perf_counter()
            try:
                response = await client.post(
                    f"{base_url}/chat/completions",
                    json={
                        "model": model,
                        "messages": [
                            {
                                "role": "system",
                                "content": "Return only OK.",
                            },
                            {"role": "user", "content": "OK?"},
                        ],
                        "stream": False,
                        "max_tokens": 8,
                    },
                )
                latency_ms = int(round(
                    (time.perf_counter() - started) * 1000
                ))
                payload = response.json()
                if response.is_success:
                    choice = next(iter(payload.get("choices") or []), {})
                    content = str(
                        (choice.get("message") or {}).get("content") or ""
                    )
                    results.append({
                        "model": model,
                        "status": "available",
                        "http_status": response.status_code,
                        "latency_ms": latency_ms,
                        "returned_content": bool(content.strip()),
                    })
                    continue
                error = payload.get("error") or {}
                code = str(error.get("code") or error.get("type") or "")
                message = str(error.get("message") or "")
                results.append({
                    "model": model,
                    "status": classify_error(
                        response.status_code,
                        code,
                        message,
                    ),
                    "http_status": response.status_code,
                    "latency_ms": latency_ms,
                    "error_code": code[:160],
                    "error_message": message[:300],
                })
            except Exception as error:
                results.append({
                    "model": model,
                    "status": "transport_error",
                    "http_status": None,
                    "latency_ms": int(round(
                        (time.perf_counter() - started) * 1000
                    )),
                    "error_type": type(error).__name__,
                    "error_message": str(error)[:300],
                })
            await asyncio.sleep(1.0)

    return {
        "schema_version": "production_model_capacity_probe_v1",
        "probed_at": datetime.now(timezone.utc).isoformat(),
        "provider": "modelscope_production_fallback_key",
        "catalog_model_count": len(catalog),
        "probe_max_output_tokens": 8,
        "results": results,
    }


if __name__ == "__main__":
    output = Path(os.environ.get(
        "LINGZHI_MODEL_PROBE_OUTPUT",
        "model-capacity.json",
    ))
    try:
        payload = asyncio.run(main())
    except Exception as error:
        payload = {
            "schema_version": "production_model_capacity_probe_v1",
            "status": "failed",
            "error_type": type(error).__name__,
            "error_message": str(error)[:300],
        }
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
