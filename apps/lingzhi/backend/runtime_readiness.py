"""Fast, side-effect-free runtime readiness projection."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from text_ai_provider_policy import (
    EXPECTED_TEXT_MODEL,
    TextAIProviderPolicyError,
    enforce_text_ai_provider_policy,
)


_MODEL_ENV_KEYS = (
    "AI_MODEL",
    "AI_MODEL_FAST",
    "AI_MODEL_CANDIDATES",
    "AI_MODEL_FAST_CANDIDATES",
    "AI_ASSESSMENT_GENERATOR_MODELS",
    "AI_ASSESSMENT_SOLVER_MODELS",
    "AI_ASSESSMENT_REVIEWER_MODELS",
    "AI_PPT_STORY_MODELS",
    "AI_PPT_VISUAL_MODELS",
)


def _configured_models(environment: Mapping[str, str]) -> list[str]:
    models: list[str] = []
    for key in _MODEL_ENV_KEYS:
        models.extend(
            item.strip()
            for item in str(environment.get(key, "") or "").split(",")
            if item.strip()
        )
    return models


def text_model_configuration_health(
    environment: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Validate configuration only; never instantiate or call a provider."""
    values = environment if environment is not None else os.environ
    models = _configured_models(values)
    try:
        if not models:
            raise TextAIProviderPolicyError("text_provider_models_missing")
        enforce_text_ai_provider_policy(
            api_base=values.get("AI_API_BASE", ""),
            models=models,
            environment=values,
        )
    except TextAIProviderPolicyError as exc:
        return {
            "configured": False,
            "model": EXPECTED_TEXT_MODEL,
            "reason_code": exc.reason,
        }
    return {
        "configured": True,
        "model": EXPECTED_TEXT_MODEL,
        "reason_code": None,
    }


def data_directory_health(storage: Any) -> dict[str, Any]:
    raw_path = getattr(storage, "_data_dir", None)
    if raw_path is None:
        return {
            "ready": False,
            "readable": False,
            "writable": False,
            "reason_code": "data_directory_unknown",
        }
    path = Path(raw_path)
    exists = path.is_dir()
    readable = exists and os.access(path, os.R_OK | os.X_OK)
    writable = exists and os.access(path, os.W_OK | os.X_OK)
    reason_code = None
    if not exists:
        reason_code = "data_directory_missing"
    elif not readable:
        reason_code = "data_directory_unreadable"
    elif not writable:
        reason_code = "data_directory_unwritable"
    return {
        "ready": bool(exists and readable and writable),
        "readable": bool(readable),
        "writable": bool(writable),
        "reason_code": reason_code,
    }


def compile_runtime_readiness(
    *,
    task_manager: Any,
    storage: Any,
    environment: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    values = environment if environment is not None else os.environ
    leader = (
        task_manager.leader_health()
        if task_manager is not None
        else {"mode": "unavailable", "state": "missing", "ready": False}
    )
    task_index = (
        task_manager.task_index_health()
        if task_manager is not None
        else {
            "state": "unavailable",
            "ready": False,
            "recovery": "none",
            "error_code": "task_manager_unavailable",
        }
    )
    data_directory = data_directory_health(storage)
    text_model = text_model_configuration_health(values)
    ready = bool(
        leader.get("ready")
        and task_index.get("ready")
        and data_directory.get("ready")
        and text_model.get("configured")
    )
    return {
        "status": "ready" if ready else "degraded",
        "ready": ready,
        "version": str(
            values.get("LINGZHI_RELEASE_SHA")
            or values.get("GITHUB_SHA")
            or "development"
        ),
        "checks": {
            "leader": leader,
            "task_index": task_index,
            "data_directory": data_directory,
            "text_model": text_model,
        },
    }


__all__ = [
    "compile_runtime_readiness",
    "data_directory_health",
    "text_model_configuration_health",
]
