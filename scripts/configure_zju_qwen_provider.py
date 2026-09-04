#!/usr/bin/env python3
"""原子配置灵知的浙大自建 Qwen 文本路由。"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse


EXPECTED_MODEL = "qwen3.8-27b"
MANAGED_SETTINGS = (
    "ZJU_QWEN_API_KEY",
    "ZJU_QWEN_BASE_URL",
    "AI_LOCAL_PROVIDER",
    "AI_API_KEY",
    "AI_API_BASE",
    "AI_MODEL",
    "AI_MODEL_FAST",
    "AI_MODEL_CANDIDATES",
    "AI_MODEL_FAST_CANDIDATES",
    "AI_ASSESSMENT_GENERATOR_MODELS",
    "AI_ASSESSMENT_SOLVER_MODELS",
    "AI_ASSESSMENT_REVIEWER_MODELS",
    "AI_PPT_API_KEY",
    "AI_PPT_API_BASE",
    "AI_PPT_STORY_MODELS",
    "AI_PPT_VISUAL_MODELS",
    "AI_THINKING_ENABLED",
    "SLIDE_DECK_V6_ENABLED",
    "SLIDE_DECK_V6_DEFAULT_ENABLED",
    "TEACHER_SCRIPT_ANIMATION_ENABLED",
)
REMOVED_TEXT_SETTINGS = (
    "MODELSCOPE_API_KEY",
    "MODELSCOPE_BASE_URL",
    "MODELSCOPE_MODEL",
    "MODELSCOPE_MODEL_CANDIDATES",
    "MODELSCOPE_MODEL_FAST_CANDIDATES",
)


def _single_line(value: object, field: str) -> str:
    normalized = str(value or "").strip()
    if not normalized or "\n" in normalized or "\r" in normalized:
        raise ValueError(f"{field} must be a non-empty single-line value")
    return normalized


def _normalized_base_url(value: object) -> str:
    normalized = _single_line(value, "base_url").rstrip("/")
    parsed = urlparse(normalized)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path.rstrip("/") != "/v1"
    ):
        raise ValueError("base_url must be an HTTP(S) OpenAI-compatible /v1 endpoint")
    port = f":{parsed.port}" if parsed.port is not None else ""
    return (
        f"{parsed.scheme.lower()}://{parsed.hostname.lower()}"
        f"{port}{parsed.path.rstrip('/')}"
    )


def _boolean_setting(value: object, field: str) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    normalized = _single_line(value, field).lower()
    if normalized not in {"true", "false"}:
        raise ValueError(f"{field} must be true or false")
    return normalized


def _validated_settings(payload: object) -> dict[str, str]:
    if not isinstance(payload, dict):
        raise ValueError("configuration payload must be an object")

    api_key = _single_line(payload.get("api_key"), "api_key")
    base_url = _normalized_base_url(payload.get("base_url"))
    model = _single_line(payload.get("model"), "model")
    if model != EXPECTED_MODEL:
        raise ValueError(f"model must be {EXPECTED_MODEL}")

    slide_enabled = _boolean_setting(
        payload.get("slide_deck_v6_enabled", True),
        "slide_deck_v6_enabled",
    )
    slide_default_enabled = _boolean_setting(
        payload.get("slide_deck_v6_default_enabled", True),
        "slide_deck_v6_default_enabled",
    )
    teacher_script_animation_enabled = _boolean_setting(
        payload.get("teacher_script_animation_enabled", False),
        "teacher_script_animation_enabled",
    )
    settings = {
        "ZJU_QWEN_API_KEY": api_key,
        "ZJU_QWEN_BASE_URL": base_url,
        "AI_LOCAL_PROVIDER": "http",
        "AI_API_KEY": api_key,
        "AI_API_BASE": base_url,
        "AI_PPT_API_KEY": api_key,
        "AI_PPT_API_BASE": base_url,
        "AI_THINKING_ENABLED": "false",
        "SLIDE_DECK_V6_ENABLED": slide_enabled,
        "SLIDE_DECK_V6_DEFAULT_ENABLED": slide_default_enabled,
        "TEACHER_SCRIPT_ANIMATION_ENABLED": teacher_script_animation_enabled,
    }
    for key in (
        "AI_MODEL",
        "AI_MODEL_FAST",
        "AI_MODEL_CANDIDATES",
        "AI_MODEL_FAST_CANDIDATES",
        "AI_ASSESSMENT_GENERATOR_MODELS",
        "AI_ASSESSMENT_SOLVER_MODELS",
        "AI_ASSESSMENT_REVIEWER_MODELS",
        "AI_PPT_STORY_MODELS",
        "AI_PPT_VISUAL_MODELS",
    ):
        settings[key] = EXPECTED_MODEL
    return settings


def _updated_env_content(existing: str, settings: dict[str, str]) -> str:
    output: list[str] = []
    written: set[str] = set()
    managed_or_removed = {*MANAGED_SETTINGS, *REMOVED_TEXT_SETTINGS}
    for line in existing.splitlines(keepends=True):
        key = line.split("=", 1)[0] if "=" in line else ""
        if key not in managed_or_removed:
            output.append(line)
            continue
        if key in REMOVED_TEXT_SETTINGS or key in written:
            continue
        newline = "\r\n" if line.endswith("\r\n") else "\n"
        output.append(f"{key}={settings[key]}{newline}")
        written.add(key)

    if output and not output[-1].endswith(("\n", "\r")):
        output[-1] += "\n"
    for key in MANAGED_SETTINGS:
        if key not in written:
            output.append(f"{key}={settings[key]}\n")
    return "".join(output)


def configure(env_file: Path, payload: object) -> None:
    settings = _validated_settings(payload)
    existing = env_file.read_text(encoding="utf-8") if env_file.exists() else ""
    updated = _updated_env_content(existing, settings)
    env_file.parent.mkdir(parents=True, exist_ok=True)

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=env_file.parent,
            prefix=f".{env_file.name}.",
            delete=False,
        ) as temporary:
            temporary.write(updated)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, env_file)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path("/opt/lingzhi/state/.env"),
    )
    args = parser.parse_args()
    try:
        payload = json.loads(sys.stdin.read())
        configure(args.env_file, payload)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"AI provider configuration failed: {error}", file=sys.stderr)
        return 1
    print(f"ZJU Qwen text provider configured: model={EXPECTED_MODEL}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
