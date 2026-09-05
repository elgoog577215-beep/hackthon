"""Allow-listed provider telemetry shared by PPT planning adapters."""
from __future__ import annotations
from typing import Any
from slide_deck_v6_models import AIProviderAttemptDiagnosticV1

class AIPlannerInvocationError(RuntimeError):
    """Provider failure with only allow-listed, non-content telemetry attached."""

    def __init__(
        self,
        error: BaseException,
        *,
        telemetry: list[dict[str, Any]] | None = None,
    ) -> None:
        self.original_error = error
        self.telemetry = [
            item.model_dump(mode="json")
            for item in _sanitize_provider_attempts(telemetry or [])
        ]
        super().__init__(str(error) or type(error).__name__)


class _AIPlannerResponse(dict[str, Any]):
    def __init__(
        self,
        value: dict[str, Any],
        *,
        telemetry: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(value)
        self.telemetry = [
            item.model_dump(mode="json")
            for item in _sanitize_provider_attempts(telemetry or [])
        ]


def _sanitize_provider_attempts(
    telemetry: list[dict[str, Any]],
) -> list[AIProviderAttemptDiagnosticV1]:
    """Keep operational routing data while dropping prompts, keys, and responses."""

    records: list[AIProviderAttemptDiagnosticV1] = []
    for ordinal, raw in enumerate(telemetry, start=1):
        if not isinstance(raw, dict):
            continue
        provider = str(
            raw.get("provider")
            or raw.get("provider_route")
            or "shared-ai-pool"
        )
        model = str(
            raw.get("model")
            or raw.get("model_id")
            or "provider-selected"
        )
        try:
            attempt = max(1, int(raw.get("provider_attempt") or raw.get("attempt") or ordinal))
        except (TypeError, ValueError):
            attempt = ordinal
        try:
            duration_ms = max(0, int(raw.get("duration_ms") or 0))
        except (TypeError, ValueError):
            duration_ms = 0
        try:
            queue_wait_ms = max(0, int(raw.get("queue_wait_ms") or 0))
        except (TypeError, ValueError):
            queue_wait_ms = 0
        try:
            physical_request_count = max(
                0,
                int(raw.get("physical_request_count") or 0),
            )
        except (TypeError, ValueError):
            physical_request_count = 0
        try:
            input_tokens = max(0, int(
                raw.get("input_tokens")
                or raw.get("estimated_input_tokens")
                or 0
            ))
        except (TypeError, ValueError):
            input_tokens = 0
        try:
            output_tokens = max(0, int(
                raw.get("output_tokens")
                or raw.get("estimated_output_tokens")
                or 0
            ))
        except (TypeError, ValueError):
            output_tokens = 0
        tokens_source = str(raw.get("tokens_source") or "unknown")
        if tokens_source not in {"provider", "estimate", "unknown"}:
            tokens_source = "unknown"
        records.append(AIProviderAttemptDiagnosticV1(
            provider=provider,
            model=model,
            attempt=attempt,
            status=str(raw.get("status") or "unknown"),
            duration_ms=duration_ms,
            queue_wait_ms=queue_wait_ms,
            physical_request_count=physical_request_count,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            tokens_source=tokens_source,
            failure_kind=str(raw.get("failure_kind") or ""),
            error_code=str(raw.get("error_code") or ""),
        ))
    return records


def _provider_attempts_from(value: Any) -> list[AIProviderAttemptDiagnosticV1]:
    telemetry = getattr(value, "telemetry", [])
    return _sanitize_provider_attempts(telemetry if isinstance(telemetry, list) else [])

