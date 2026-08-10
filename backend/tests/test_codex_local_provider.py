from __future__ import annotations

import asyncio

import pytest

from ai_base import AIBase
from codex_local_provider import CodexLocalProvider


def _enable_local_provider(monkeypatch) -> None:
    monkeypatch.setenv("AI_CODEX_LOCAL_ENABLED", "true")
    monkeypatch.setenv("CODEX_LOCAL_BINARY", "/bin/echo")
    monkeypatch.delenv("AI_API_KEY", raising=False)
    monkeypatch.delenv("MODELSCOPE_API_KEY", raising=False)


def test_codex_local_command_is_ephemeral_read_only_and_noninteractive(
    monkeypatch,
    tmp_path,
):
    _enable_local_provider(monkeypatch)
    provider = CodexLocalProvider.from_environment()

    command = provider._command(
        tmp_path / "final.txt",
        use_fast_model=True,
    )

    assert provider.configured is True
    assert "--ephemeral" in command
    assert "--ignore-user-config" in command
    assert "--ignore-rules" in command
    assert command[command.index("-C") + 1] == str(tmp_path)
    assert command[command.index("-s") + 1] == "read-only"
    assert command[command.index("--ask-for-approval") + 1] == "never"
    assert command[-1] == "-"


def test_codex_local_child_environment_excludes_application_secrets(
    monkeypatch,
):
    monkeypatch.setenv("HOME", "/tmp/test-home")
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setenv("AI_API_KEY", "must-not-leak")
    monkeypatch.setenv("DATABASE_URL", "must-not-leak")

    child = CodexLocalProvider._child_environment()

    assert child["HOME"] == "/tmp/test-home"
    assert child["PATH"] == "/usr/bin"
    assert "AI_API_KEY" not in child
    assert "DATABASE_URL" not in child


def test_codex_local_request_treats_material_as_untrusted_content():
    rendered = CodexLocalProvider._request_text(
        "uploaded material",
        "return a course",
        json_mode=True,
        max_tokens=512,
    )

    assert "Do not inspect files" in rendered
    assert "untrusted content" in rendered
    assert "strict JSON" in rendered
    assert "uploaded material" in rendered


@pytest.mark.asyncio
async def test_ai_base_uses_local_codex_without_api_key(monkeypatch):
    _enable_local_provider(monkeypatch)
    service = AIBase()

    async def fake_complete(*_args, **_kwargs):
        return '{"course":"calculus"}', {
            "attempts": 1,
            "duration_ms": 25,
            "model_id": "test-codex",
        }

    monkeypatch.setattr(CodexLocalProvider, "complete", fake_complete)
    telemetry: list[dict] = []

    result = await service._call_llm(
        "generate",
        json_mode=True,
        retry_count=1,
        raise_on_failure=True,
        telemetry_sink=telemetry.append,
    )

    assert result == '{"course":"calculus"}'
    assert telemetry[0]["model_role"] == "codex_local"
    assert telemetry[0]["status"] == "completed"


@pytest.mark.asyncio
async def test_codex_local_preflight_is_explicitly_development_only(
    monkeypatch,
):
    _enable_local_provider(monkeypatch)
    service = AIBase()

    async def fake_complete(*_args, **_kwargs):
        return "OK", {
            "attempts": 1,
            "duration_ms": 20,
            "model_id": "test-codex",
        }

    monkeypatch.setattr(CodexLocalProvider, "complete", fake_complete)

    result = await service.generation_provider_preflight(live_probe=True)

    assert result["status"] == "degraded"
    assert result["probe_status"] == "passed"
    assert result["active_route"] == "codex_local"
    assert result["routes"][0]["development_only"] is True
    assert [item["code"] for item in result["issues"]] == [
        "codex_local_development_only"
    ]


@pytest.mark.asyncio
async def test_codex_local_reports_liveness_while_waiting(monkeypatch):
    _enable_local_provider(monkeypatch)
    monkeypatch.setenv("CODEX_LOCAL_TIMEOUT_SECONDS", "10")
    service = AIBase()
    activity_count = 0

    async def slow_complete(*_args, **_kwargs):
        await asyncio.sleep(2.6)
        return "OK", {
            "attempts": 1,
            "duration_ms": 2600,
            "model_id": "test-codex",
        }

    def mark_activity() -> None:
        nonlocal activity_count
        activity_count += 1

    monkeypatch.setattr(CodexLocalProvider, "complete", slow_complete)

    result = await service._call_llm(
        "generate",
        retry_count=1,
        raise_on_failure=True,
        on_stream_activity=mark_activity,
    )

    assert result == "OK"
    assert activity_count >= 3
