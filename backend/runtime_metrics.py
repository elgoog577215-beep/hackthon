"""Low-cardinality operational metrics emitted through the existing logger.

The runtime has one process-wide logging pipeline already.  These helpers add
actionable, machine-readable events to that pipeline without creating another
database or JSON ledger.  Public helpers deliberately accept only the small
pieces of runtime state needed for aggregation; identifiers, prompts, course
content and material metadata have no place in the contract.

Metric emission is best-effort.  Observability must never make generation,
persistence or recovery fail.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

SCHEMA_VERSION = "runtime_metric_v1"
LOGGER = logging.getLogger("lingzhi.runtime_metrics")

_TASK_TYPES = {
    "course_generation",
    "course_import",
    "teacher_outline_generation",
    "teacher_lesson_plan_generation",
    "teacher_lesson_script_generation",
    "teaching_representation_build",
    "slide_deck_variant_build",
}
_TIMEOUT_POLICIES = {
    "request_wall_clock",
    "stream_inactivity",
    "provider_timeout",
}
_PERSISTENCE_COMPONENTS = {
    "course_evolution_journal",
    "generic_data",
    "task_index",
    "teacher_asset",
}
_PERSISTENCE_OPERATIONS = {
    "lifecycle_save",
    "save",
    "update",
}
_PERSISTENCE_REASONS = {
    "atomic_replace_failed",
    "directory_unavailable",
    "fsync_failed",
    "journal_save_failed",
    "serialization_failed",
    "unknown",
}
_RECOVERY_TRIGGERS = {
    "manual_resume",
    "quality_gate_repair",
    "service_restart",
}
_RECOVERY_RESULTS = {
    "completed",
    "failed",
    "resumed",
    "skipped",
    "unavailable",
}
_MODEL_ERROR_CODES = {
    "generation_budget_exceeded",
    "generation_deadline_exceeded",
    "generation_failed",
    "provider_auth_failed",
    "provider_quota_exhausted",
    "provider_rate_limited",
    "provider_timeout",
    "provider_unavailable",
    "response_truncated",
}


def _enum(value: Any, allowed: set[str], fallback: str) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in allowed else fallback


def _duration_bucket(seconds: Any) -> str:
    try:
        value = max(0.0, float(seconds))
    except (TypeError, ValueError):
        return "unknown"
    if value < 1:
        return "lt_1s"
    if value < 5:
        return "1s_5s"
    if value < 15:
        return "5s_15s"
    if value < 60:
        return "15s_60s"
    if value < 300:
        return "1m_5m"
    return "gte_5m"


def _count_bucket(value: Any) -> str:
    try:
        count = max(0, int(value))
    except (TypeError, ValueError):
        return "unknown"
    if count == 0:
        return "0"
    if count == 1:
        return "1"
    if count <= 5:
        return "2_5"
    return "gte_6"


def _phase(value: Any) -> str:
    """Collapse runtime phase names into a stable production-chain vocabulary."""
    phase = str(value or "").strip().lower()
    if not phase:
        return "unknown"
    if "outline" in phase or "blueprint" in phase:
        return "outline"
    if "lesson_plan" in phase or "teaching_plan" in phase:
        return "lesson_plan"
    if "script" in phase or "lecture" in phase:
        return "script"
    if "slide" in phase or "ppt" in phase or "representation" in phase:
        return "ppt"
    if "question" in phase or "assessment" in phase or "practice" in phase:
        return "assessment"
    if "content" in phase or "node" in phase:
        return "course_content"
    if "import" in phase or "material" in phase:
        return "import"
    if "recover" in phase or "resum" in phase:
        return "recovery"
    return "other"


def _persistence_reason(error: BaseException | None) -> str:
    if error is None:
        return "unknown"
    if isinstance(error, (TypeError, ValueError)):
        return "serialization_failed"
    if isinstance(error, FileNotFoundError):
        return "directory_unavailable"
    message = str(error).casefold()
    if "fsync" in message or "sync" in message:
        return "fsync_failed"
    if "replace" in message or isinstance(error, OSError):
        return "atomic_replace_failed"
    return "unknown"


def _emit(metric: str, labels: dict[str, str]) -> None:
    try:
        LOGGER.info(
            "runtime_metric %s",
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "metric": metric,
                    "labels": labels,
                },
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            ),
        )
    except Exception:  # pragma: no cover - logging must never affect the task
        pass


def record_task_wait(*, task_type: Any, queued_at: Any, started_at: Any = None) -> None:
    try:
        queued = datetime.fromisoformat(str(queued_at or ""))
        started = (
            datetime.fromisoformat(str(started_at))
            if started_at
            else datetime.now(tz=queued.tzinfo)
        )
        seconds: Any = (started - queued).total_seconds()
    except (TypeError, ValueError):
        seconds = None
    _emit(
        "task_wait_duration",
        {
            "task_type": _enum(task_type, _TASK_TYPES, "other"),
            "duration_bucket": _duration_bucket(seconds),
        },
    )


def record_heartbeat_timeout(
    *,
    timeout_policy: Any,
    phase: Any,
    elapsed_seconds: Any,
) -> None:
    _emit(
        "heartbeat_timeout",
        {
            "timeout_policy": _enum(
                timeout_policy,
                _TIMEOUT_POLICIES,
                "unknown",
            ),
            "phase": _phase(phase),
            "duration_bucket": _duration_bucket(elapsed_seconds),
        },
    )


def record_persistence_failure(
    *,
    component: Any,
    operation: Any,
    error: BaseException | None = None,
    reason_code: Any = None,
) -> None:
    reason = _enum(reason_code, _PERSISTENCE_REASONS, "unknown")
    if reason == "unknown":
        reason = _persistence_reason(error)
    _emit(
        "persistence_failure",
        {
            "component": _enum(
                component,
                _PERSISTENCE_COMPONENTS,
                "other",
            ),
            "operation": _enum(
                operation,
                _PERSISTENCE_OPERATIONS,
                "other",
            ),
            "reason_code": reason,
        },
    )


def record_recovery_result(
    *,
    task_type: Any,
    trigger: Any,
    result: Any,
) -> None:
    _emit(
        "recovery_result",
        {
            "task_type": _enum(task_type, _TASK_TYPES, "other"),
            "trigger": _enum(trigger, _RECOVERY_TRIGGERS, "other"),
            "result": _enum(result, _RECOVERY_RESULTS, "failed"),
        },
    )


def record_cross_asset_partial(
    *,
    operation_count: Any,
    failed_count: Any,
) -> None:
    _emit(
        "cross_asset_partial",
        {
            "operation_count_bucket": _count_bucket(operation_count),
            "failed_count_bucket": _count_bucket(failed_count),
        },
    )


def record_model_error(*, error_code: Any, retryable: Any) -> None:
    _emit(
        "model_error_classification",
        {
            "error_code": _enum(
                error_code,
                _MODEL_ERROR_CODES,
                "generation_failed",
            ),
            "retryable": "true" if retryable is True else "false",
        },
    )


__all__ = [
    "record_cross_asset_partial",
    "record_heartbeat_timeout",
    "record_model_error",
    "record_persistence_failure",
    "record_recovery_result",
    "record_task_wait",
]
