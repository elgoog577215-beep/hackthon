from __future__ import annotations

import json
import logging

import pytest

import runtime_metrics
from runtime_metrics import (
    record_cross_asset_partial,
    record_heartbeat_timeout,
    record_model_error,
    record_persistence_failure,
    record_recovery_result,
    record_task_wait,
)
from storage import Storage


def _events(caplog) -> list[dict]:
    events: list[dict] = []
    for record in caplog.records:
        message = record.getMessage()
        if not message.startswith("runtime_metric "):
            continue
        events.append(json.loads(message.removeprefix("runtime_metric ")))
    return events


def test_runtime_metrics_emit_six_low_cardinality_contracts(caplog) -> None:
    caplog.set_level(logging.INFO, logger="lingzhi.runtime_metrics")

    record_task_wait(
        task_type="course_generation",
        queued_at="2026-09-04T10:00:00+08:00",
        started_at="2026-09-04T10:00:07+08:00",
    )
    record_heartbeat_timeout(
        timeout_policy="stream_inactivity",
        phase="teacher_lesson_script_generation",
        elapsed_seconds=61,
    )
    record_persistence_failure(
        component="task_index",
        operation="lifecycle_save",
        error=OSError("replace failed"),
    )
    record_recovery_result(
        task_type="slide_deck_variant_build",
        trigger="service_restart",
        result="resumed",
    )
    record_cross_asset_partial(operation_count=5, failed_count=1)
    record_model_error(error_code="provider_rate_limited", retryable=True)

    events = _events(caplog)
    assert [event["metric"] for event in events] == [
        "task_wait_duration",
        "heartbeat_timeout",
        "persistence_failure",
        "recovery_result",
        "cross_asset_partial",
        "model_error_classification",
    ]
    assert events[0]["labels"] == {
        "duration_bucket": "5s_15s",
        "task_type": "course_generation",
    }
    assert events[1]["labels"] == {
        "duration_bucket": "1m_5m",
        "phase": "script",
        "timeout_policy": "stream_inactivity",
    }
    assert events[2]["labels"]["reason_code"] == "atomic_replace_failed"
    assert events[3]["labels"]["result"] == "resumed"
    assert events[4]["labels"] == {
        "failed_count_bucket": "1",
        "operation_count_bucket": "2_5",
    }
    assert events[5]["labels"] == {
        "error_code": "provider_rate_limited",
        "retryable": "true",
    }
    assert all(event["schema_version"] == "runtime_metric_v1" for event in events)


def test_runtime_metrics_never_log_content_prompt_material_or_identity(caplog) -> None:
    caplog.set_level(logging.INFO, logger="lingzhi.runtime_metrics")
    secrets = {
        "COURSE_BODY_SECRET",
        "PROMPT_SECRET",
        "MATERIAL_FILENAME_SECRET.pdf",
        "teacher@example.com",
        "course-identity-123",
        "lesson-identity-456",
        "task-identity-789",
    }
    poisoned = " ".join(sorted(secrets))

    record_task_wait(task_type=poisoned, queued_at=poisoned)
    record_heartbeat_timeout(
        timeout_policy=poisoned,
        phase=poisoned,
        elapsed_seconds=poisoned,
    )
    record_persistence_failure(
        component=poisoned,
        operation=poisoned,
        error=RuntimeError(poisoned),
        reason_code=poisoned,
    )
    record_recovery_result(
        task_type=poisoned,
        trigger=poisoned,
        result=poisoned,
    )
    record_cross_asset_partial(
        operation_count=poisoned,
        failed_count=poisoned,
    )
    record_model_error(error_code=poisoned, retryable=poisoned)

    payload = json.dumps(_events(caplog), ensure_ascii=False)
    assert all(secret not in payload for secret in secrets)
    assert set(_events(caplog)[0]) == {"schema_version", "metric", "labels"}
    assert all(
        set(event) == {"schema_version", "metric", "labels"}
        for event in _events(caplog)
    )


def test_generic_storage_failure_uses_same_metric_entry(tmp_path, monkeypatch, caplog) -> None:
    caplog.set_level(logging.INFO, logger="lingzhi.runtime_metrics")
    storage = Storage(data_dir=str(tmp_path))

    def fail_replace(*_args, **_kwargs) -> None:
        raise OSError("disk payload should not become a metric label")

    monkeypatch.setattr(storage, "_atomic_save_generic_data", fail_replace)
    with pytest.raises(OSError, match="disk payload"):
        storage.update_data("ledger.json", lambda _current: {"private": "body"})

    events = _events(caplog)
    assert events[-1] == {
        "schema_version": "runtime_metric_v1",
        "metric": "persistence_failure",
        "labels": {
            "component": "generic_data",
            "operation": "update",
            "reason_code": "atomic_replace_failed",
        },
    }
    assert "disk payload" not in json.dumps(events)
    assert "private" not in json.dumps(events)


def test_metric_logging_failure_never_changes_runtime_result(monkeypatch) -> None:
    def fail_log(*_args, **_kwargs) -> None:
        raise RuntimeError("logging unavailable")

    monkeypatch.setattr(runtime_metrics.LOGGER, "info", fail_log)
    record_model_error(error_code="provider_timeout", retryable=True)
