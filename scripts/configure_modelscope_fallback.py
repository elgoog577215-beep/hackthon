#!/usr/bin/env python3
"""Atomically provision the PPT primary route and ModelScope fallback."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

ENVIRONMENT_KEYS = (
    "AI_PPT_API_KEY",
    "AI_PPT_API_BASE",
    "MODELSCOPE_API_KEY",
    "MODELSCOPE_BASE_URL",
    "MODELSCOPE_MODEL",
    "AI_PPT_STORY_MODELS",
    "AI_PPT_VISUAL_MODELS",
    "SLIDE_DECK_V6_ENABLED",
    "SLIDE_DECK_V6_DEFAULT_ENABLED",
)
MODEL_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
TRUSTED_MODELSCOPE_HOST = "api-inference.modelscope.cn"
TRUSTED_DEEPSEEK_HOST = "api.deepseek.com"


def _single_line(value: object, field: str) -> str:
    normalized = str(value or "").strip()
    if not normalized or "\n" in normalized or "\r" in normalized:
        raise ValueError(f"{field} must be a non-empty single-line value")
    return normalized


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
    base_url = _single_line(payload.get("base_url"), "base_url")
    model = _single_line(payload.get("model"), "model")
    ppt_api_key = _single_line(payload.get("ppt_api_key"), "ppt_api_key")
    ppt_api_base = _single_line(payload.get("ppt_api_base"), "ppt_api_base")
    ppt_story_models = _single_line(
        payload.get("ppt_story_models"),
        "ppt_story_models",
    )
    ppt_visual_models = _single_line(
        payload.get("ppt_visual_models"),
        "ppt_visual_models",
    )
    slide_deck_v6_enabled = _boolean_setting(
        payload.get("slide_deck_v6_enabled"),
        "slide_deck_v6_enabled",
    )
    slide_deck_v6_default_enabled = _boolean_setting(
        payload.get("slide_deck_v6_default_enabled"),
        "slide_deck_v6_default_enabled",
    )

    parsed = urlparse(base_url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != TRUSTED_MODELSCOPE_HOST
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path.rstrip("/") != "/v1"
    ):
        raise ValueError("base_url must be the trusted ModelScope v1 endpoint")
    ppt_parsed = urlparse(ppt_api_base)
    if (
        ppt_parsed.scheme != "https"
        or ppt_parsed.hostname != TRUSTED_DEEPSEEK_HOST
        or ppt_parsed.username
        or ppt_parsed.password
        or ppt_parsed.query
        or ppt_parsed.fragment
        or ppt_parsed.path.rstrip("/") not in {"", "/v1"}
    ):
        raise ValueError("ppt_api_base must be the trusted DeepSeek endpoint")
    if not MODEL_PATTERN.fullmatch(model):
        raise ValueError("model contains unsupported characters")
    for field, model_list in (
        ("ppt_story_models", ppt_story_models),
        ("ppt_visual_models", ppt_visual_models),
    ):
        models = [item.strip() for item in model_list.split(",")]
        if not models or any(
            not item or not MODEL_PATTERN.fullmatch(item)
            for item in models
        ):
            raise ValueError(f"{field} contains an invalid model")

    return {
        "AI_PPT_API_KEY": ppt_api_key,
        "AI_PPT_API_BASE": ppt_api_base,
        "MODELSCOPE_API_KEY": api_key,
        "MODELSCOPE_BASE_URL": base_url,
        "MODELSCOPE_MODEL": model,
        "AI_PPT_STORY_MODELS": ppt_story_models,
        "AI_PPT_VISUAL_MODELS": ppt_visual_models,
        "SLIDE_DECK_V6_ENABLED": slide_deck_v6_enabled,
        "SLIDE_DECK_V6_DEFAULT_ENABLED": slide_deck_v6_default_enabled,
    }


def _updated_env_content(existing: str, settings: dict[str, str]) -> str:
    output: list[str] = []
    replaced: set[str] = set()
    for line in existing.splitlines(keepends=True):
        matched_key = next(
            (
                key
                for key in ENVIRONMENT_KEYS
                if line.startswith(f"{key}=")
            ),
            None,
        )
        if matched_key is None:
            output.append(line)
            continue
        if matched_key in replaced:
            continue
        newline = "\r\n" if line.endswith("\r\n") else "\n"
        output.append(f"{matched_key}={settings[matched_key]}{newline}")
        replaced.add(matched_key)

    if output and not output[-1].endswith(("\n", "\r")):
        output[-1] += "\n"
    for key in ENVIRONMENT_KEYS:
        if key not in replaced:
            output.append(f"{key}={settings[key]}\n")
    return "".join(output)


def configure(env_file: Path, payload: object) -> None:
    settings = _validated_settings(payload)
    existing = (
        env_file.read_text(encoding="utf-8")
        if env_file.exists()
        else ""
    )
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
    print("PPT primary and ModelScope fallback configuration updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
