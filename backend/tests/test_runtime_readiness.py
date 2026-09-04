from __future__ import annotations

import json
from pathlib import Path

import pytest

from runtime_readiness import compile_runtime_readiness


class HealthyTaskManager:
    def leader_health(self):
        return {"mode": "leader", "state": "acquired", "ready": True}

    def task_index_health(self):
        return {
            "state": "ready",
            "ready": True,
            "recovery": "primary",
            "error_code": None,
        }


class StorageBoundary:
    def __init__(self, path: Path) -> None:
        self._data_dir = path


def configured_environment() -> dict[str, str]:
    return {
        "LINGZHI_RELEASE_SHA": "abc123",
        "ZJU_QWEN_API_KEY": "test-secret",
        "ZJU_QWEN_BASE_URL": "https://private.example/v1",
        "AI_LOCAL_PROVIDER": "http",
        "AI_API_KEY": "test-secret",
        "AI_API_BASE": "https://private.example/v1",
        "AI_MODEL": "qwen3.8-27b",
        "AI_MODEL_FAST": "qwen3.8-27b",
    }


def test_readiness_reports_all_local_checks_without_calling_model(tmp_path):
    result = compile_runtime_readiness(
        task_manager=HealthyTaskManager(),
        storage=StorageBoundary(tmp_path),
        environment=configured_environment(),
    )

    assert result == {
        "status": "ready",
        "ready": True,
        "version": "abc123",
        "checks": {
            "leader": {"mode": "leader", "state": "acquired", "ready": True},
            "task_index": {
                "state": "ready",
                "ready": True,
                "recovery": "primary",
                "error_code": None,
            },
            "data_directory": {
                "ready": True,
                "readable": True,
                "writable": True,
                "reason_code": None,
            },
            "text_model": {
                "configured": True,
                "model": "qwen3.8-27b",
                "reason_code": None,
            },
        },
    }


def test_degraded_task_index_fails_readiness_but_keeps_other_checks(tmp_path):
    manager = HealthyTaskManager()
    manager.task_index_health = lambda: {
        "state": "degraded",
        "ready": False,
        "recovery": "unavailable",
        "error_code": "generation_job_index_unrecoverable",
    }

    result = compile_runtime_readiness(
        task_manager=manager,
        storage=StorageBoundary(tmp_path),
        environment=configured_environment(),
    )

    assert result["status"] == "degraded"
    assert result["ready"] is False
    assert result["checks"]["task_index"]["error_code"] == (
        "generation_job_index_unrecoverable"
    )


def test_model_configuration_check_is_fail_closed_and_never_needs_network(tmp_path):
    environment = configured_environment()
    environment["AI_MODEL"] = "another-model"

    result = compile_runtime_readiness(
        task_manager=HealthyTaskManager(),
        storage=StorageBoundary(tmp_path),
        environment=environment,
    )

    assert result["ready"] is False
    assert result["checks"]["text_model"] == {
        "configured": False,
        "model": "qwen3.8-27b",
        "reason_code": "text_provider_model_mismatch",
    }


@pytest.mark.asyncio
async def test_liveness_stays_successful_when_readiness_is_degraded(monkeypatch):
    import dependencies

    previous_task_manager = dependencies.get_task_manager_optional()
    try:
        import main

        monkeypatch.setattr(
            main,
            "compile_runtime_readiness",
            lambda **_kwargs: {
                "status": "degraded",
                "ready": False,
                "version": "test",
                "checks": {},
            },
        )
        monkeypatch.setattr(
            main,
            "retrieval_feature_state",
            lambda: {
                "enabled": False,
                "mode": "disabled",
                "provider": "none",
                "provider_configured": False,
            },
        )

        assert (await main.health_check())["status"] == "ok"
        readiness_response = main.read_root()
        assert readiness_response.status_code == 503
        assert json.loads(readiness_response.body)["status"] == "degraded"
    finally:
        dependencies.init_task_manager(previous_task_manager)
