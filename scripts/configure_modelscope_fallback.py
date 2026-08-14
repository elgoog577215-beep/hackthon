#!/usr/bin/env python3
"""Atomically provision production AI primary and fallback settings."""

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
    "AI_API_KEY",
    "AI_API_BASE",
    "AI_MODEL",
    "AI_MODEL_FAST",
    "AI_MODEL_CANDIDATES",
    "AI_MODEL_FAST_CANDIDATES",
    "AI_ASSESSMENT_GENERATOR_MODELS",
    "AI_ASSESSMENT_SOLVER_MODELS",
    "AI_ASSESSMENT_REVIEWER_MODELS",
    "AI_PPT_STORY_MODELS",
    "AI_PPT_VISUAL_MODELS",
    "MODELSCOPE_API_KEY",
    "MODELSCOPE_BASE_URL",
    "MODELSCOPE_MODEL",
    "SLIDE_DECK_V6_ENABLED",
    "SLIDE_DECK_V6_DEFAULT_ENABLED",
)
MODEL_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
TRUSTED_DEEPSEEK_HOST = "api.deepseek.com"
TRUSTED_MODELSCOPE_HOST = "api-inference.modelscope.cn"
SUPPORTED_DEEPSEEK_MODELS = frozenset({"deepseek-v4-pro", "deepseek-v4-flash"})


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


def _model_list(
    value: object,
    field: str,
    *,
    allowed: frozenset[str] | None = None,
) -> list[str]:
    raw_value = _single_line(value, field)
    models = [item.strip() for item in raw_value.split(",")]
    if not models or any(
        not item
        or not MODEL_PATTERN.fullmatch(item)
        or (allowed is not None and item not in allowed)
        for item in models
    ):
        raise ValueError(f"{field} contains an invalid model")
    return models


def _validate_deepseek_endpoint(base_url: str) -> None:
    parsed = urlparse(base_url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != TRUSTED_DEEPSEEK_HOST
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path.rstrip("/") not in {"", "/v1"}
    ):
        raise ValueError("primary_base_url must be the trusted DeepSeek endpoint")


def _validate_modelscope_endpoint(base_url: str) -> None:
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
        raise ValueError(
            "fallback_base_url must be the trusted ModelScope v1 endpoint"
        )


def _validated_settings(payload: object) -> dict[str, str]:
    if not isinstance(payload, dict):
        raise ValueError("configuration payload must be an object")

    primary_api_key = _single_line(
        payload.get("primary_api_key"),
        "primary_api_key",
    )
    primary_base_url = _single_line(
        payload.get("primary_base_url"),
        "primary_base_url",
    )
    _validate_deepseek_endpoint(primary_base_url)

    primary_model_fields = {
        "smart_models": _model_list(
            payload.get("smart_models"),
            "smart_models",
            allowed=SUPPORTED_DEEPSEEK_MODELS,
        ),
        "fast_models": _model_list(
            payload.get("fast_models"),
            "fast_models",
            allowed=SUPPORTED_DEEPSEEK_MODELS,
        ),
        "assessment_generator_models": _model_list(
            payload.get("assessment_generator_models"),
            "assessment_generator_models",
            allowed=SUPPORTED_DEEPSEEK_MODELS,
        ),
        "assessment_solver_models": _model_list(
            payload.get("assessment_solver_models"),
            "assessment_solver_models",
            allowed=SUPPORTED_DEEPSEEK_MODELS,
        ),
        "assessment_reviewer_models": _model_list(
            payload.get("assessment_reviewer_models"),
            "assessment_reviewer_models",
            allowed=SUPPORTED_DEEPSEEK_MODELS,
        ),
        "ppt_story_models": _model_list(
            payload.get("ppt_story_models"),
            "ppt_story_models",
            allowed=SUPPORTED_DEEPSEEK_MODELS,
        ),
        "ppt_visual_models": _model_list(
            payload.get("ppt_visual_models"),
            "ppt_visual_models",
            allowed=SUPPORTED_DEEPSEEK_MODELS,
        ),
    }

    fallback_api_key = _single_line(
        payload.get("fallback_api_key"),
        "fallback_api_key",
    )
    fallback_base_url = _single_line(
        payload.get("fallback_base_url"),
        "fallback_base_url",
    )
    _validate_modelscope_endpoint(fallback_base_url)
    fallback_model = _single_line(
        payload.get("fallback_model"),
        "fallback_model",
    )
    if not MODEL_PATTERN.fullmatch(fallback_model):
        raise ValueError("fallback_model contains unsupported characters")

    slide_deck_v6_enabled = _boolean_setting(
        payload.get("slide_deck_v6_enabled"),
        "slide_deck_v6_enabled",
    )
    slide_deck_v6_default_enabled = _boolean_setting(
        payload.get("slide_deck_v6_default_enabled"),
        "slide_deck_v6_default_enabled",
    )

    smart_models = primary_model_fields["smart_models"]
    fast_models = primary_model_fields["fast_models"]

    return {
        "AI_API_KEY": primary_api_key,
        "AI_API_BASE": primary_base_url.rstrip("/"),
        "AI_MODEL": smart_models[0],
        "AI_MODEL_FAST": fast_models[0],
        "AI_MODEL_CANDIDATES": ",".join(smart_models),
        "AI_MODEL_FAST_CANDIDATES": ",".join(fast_models),
        "AI_ASSESSMENT_GENERATOR_MODELS": ",".join(
            primary_model_fields["assessment_generator_models"]
        ),
        "AI_ASSESSMENT_SOLVER_MODELS": ",".join(
            primary_model_fields["assessment_solver_models"]
        ),
        "AI_ASSESSMENT_REVIEWER_MODELS": ",".join(
            primary_model_fields["assessment_reviewer_models"]
        ),
        "AI_PPT_STORY_MODELS": ",".join(
            primary_model_fields["ppt_story_models"]
        ),
        "AI_PPT_VISUAL_MODELS": ",".join(
            primary_model_fields["ppt_visual_models"]
        ),
        "MODELSCOPE_API_KEY": fallback_api_key,
        "MODELSCOPE_BASE_URL": fallback_base_url,
        "MODELSCOPE_MODEL": fallback_model,
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
        print(f"Production AI configuration failed: {error}", file=sys.stderr)
        return 1
    print("Production AI configuration updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
