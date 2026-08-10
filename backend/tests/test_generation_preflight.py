from __future__ import annotations

import pytest

from generation_preflight import build_generation_preflight
from material_storage import MaterialRepository


class FakeAIService:
    def __init__(self, projection: dict):
        self.projection = projection

    async def generation_provider_preflight(self, *, live_probe: bool = True) -> dict:
        assert live_probe is True
        return self.projection


def _provider(*, status: str = "ready", issues: list[dict] | None = None) -> dict:
    return {
        "status": status,
        "probe_status": "passed",
        "active_route": "primary",
        "duration_ms": 12,
        "routes": [{"route": "primary", "configured": True}],
        "capacity": {"limit": 3, "in_flight": 0},
        "issues": issues or [],
    }


@pytest.mark.asyncio
async def test_preflight_blocks_missing_material_and_keeps_stable_identity(tmp_path):
    repository = MaterialRepository(tmp_path / "materials")
    request = {
        "subject": "线性代数",
        "course_type": "systematic",
        "material_bindings": [{"asset_id": "mat-missing", "usage_policy": "must_use"}],
        "teacher_course_brief": {"section_count": 8},
    }

    first = await build_generation_preflight(
        request,
        ai_service=FakeAIService(_provider()),
        repository=repository,
    )
    second = await build_generation_preflight(
        request,
        ai_service=FakeAIService(_provider()),
        repository=repository,
    )

    assert first["status"] == "blocked"
    assert first["preflight_id"] == second["preflight_id"]
    assert first["acceptance_required"] is False
    assert [item["code"] for item in first["issues"]] == ["material_missing"]
    assert first["materials"]["readable"] == 0


@pytest.mark.asyncio
async def test_preflight_degraded_requires_explicit_acceptance(tmp_path):
    warning = {
        "code": "provider_redundancy_missing",
        "severity": "warning",
        "scope": "provider",
        "message": "只有一条模型路线。",
        "action": "配置备用路线。",
        "item_id": "",
    }
    result = await build_generation_preflight(
        {
            "subject": "概率论",
            "teacher_course_brief": {"section_count": 12},
        },
        ai_service=FakeAIService(_provider(status="degraded", issues=[warning])),
        repository=MaterialRepository(tmp_path / "materials"),
    )

    assert result["status"] == "degraded"
    assert result["acceptance_required"] is True
    assert result["capacity"]["recommended_concurrency"] == 3
    assert result["capacity"]["estimated_sections"] == 12


@pytest.mark.asyncio
async def test_preflight_blocks_requested_retrieval_when_rollout_is_off(tmp_path, monkeypatch):
    monkeypatch.setenv("WEB_RETRIEVAL_V2_MODE", "off")
    result = await build_generation_preflight(
        {"subject": "现代物理", "retrieval": {"enabled": True}},
        ai_service=FakeAIService(_provider()),
        repository=MaterialRepository(tmp_path / "materials"),
        actor_id="teacher-1",
    )

    assert result["status"] == "blocked"
    assert result["retrieval"]["status"] == "blocked"
    assert "retrieval_not_enabled" in {
        item["code"] for item in result["issues"]
    }
