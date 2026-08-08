#!/usr/bin/env python3
"""Atomically provision the production-only ModelScope fallback settings."""

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
    "MODELSCOPE_API_KEY",
    "MODELSCOPE_BASE_URL",
    "MODELSCOPE_MODEL",
    "MODELSCOPE_MODEL_CANDIDATES",
    "MODELSCOPE_MODEL_FAST_CANDIDATES",
)
MODEL_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
TRUSTED_MODELSCOPE_HOST = "api-inference.modelscope.cn"


def _single_line(value: object, field: str) -> str:
    normalized = str(value or "").strip()
    if not normalized or "\n" in normalized or "\r" in normalized:
        raise ValueError(f"{field} must be a non-empty single-line value")
    return normalized


def _validated_models(
    value: object,
    field: str,
    legacy_model: str,
) -> list[str]:
    candidates = [legacy_model] if value is None else value
    if not isinstance(candidates, list) or not candidates:
        raise ValueError(f"{field} must be a non-empty array")

    validated: list[str] = []
    for index, candidate in enumerate(candidates):
        model = _single_line(candidate, f"{field}[{index}]")
        if not MODEL_PATTERN.fullmatch(model):
            raise ValueError(f"{field}[{index}] contains unsupported characters")
        if model not in validated:
            validated.append(model)
    return validated


def _validated_settings(payload: object) -> dict[str, str]:
    if not isinstance(payload, dict):
        raise ValueError("configuration payload must be an object")

    api_key = _single_line(payload.get("api_key"), "api_key")
    base_url = _single_line(payload.get("base_url"), "base_url")
    model = _single_line(payload.get("model"), "model")
    smart_models = _validated_models(
        payload.get("smart_models"),
        "smart_models",
        model,
    )
    fast_models = _validated_models(
        payload.get("fast_models"),
        "fast_models",
        model,
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
    if not MODEL_PATTERN.fullmatch(model):
        raise ValueError("model contains unsupported characters")

    return {
        "MODELSCOPE_API_KEY": api_key,
        "MODELSCOPE_BASE_URL": base_url,
        "MODELSCOPE_MODEL": model,
        "MODELSCOPE_MODEL_CANDIDATES": ",".join(smart_models),
        "MODELSCOPE_MODEL_FAST_CANDIDATES": ",".join(fast_models),
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
        print(f"ModelScope fallback configuration failed: {error}", file=sys.stderr)
        return 1
    print("ModelScope fallback configuration updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
