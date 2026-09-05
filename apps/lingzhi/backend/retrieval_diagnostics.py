"""Strict, read-only production diagnostics for every retrieval consumer."""

from __future__ import annotations

from typing import Any

from web_retrieval import RetrievalGateway, RetrievalRequest


class RetrievalDiagnosticError(RuntimeError):
    """Raised when production retrieval is unavailable or falls back locally."""


def assert_retrieval_feature(feature: dict[str, Any]) -> None:
    """Require a globally enabled, configured SearXNG retrieval feature."""

    required = {
        "mode": feature.get("mode") == "on",
        "enabled": feature.get("enabled") is True,
        "enabled_for_user": feature.get("enabled_for_user") is True,
        "provider": feature.get("provider") == "searxng",
        "provider_configured": feature.get("provider_configured") is True,
    }
    failures = [name for name, passed in required.items() if not passed]
    if failures:
        raise RetrievalDiagnosticError(
            "retrieval feature is not live: " + ", ".join(failures)
        )


async def run_retrieval_matrix(
    gateway: RetrievalGateway,
    *,
    query: str,
) -> dict[str, dict[str, Any]]:
    """Exercise course, assessment, AI-teacher, and PPT-image retrieval."""

    requests = (
        RetrievalRequest(purpose="course", enabled=True, queries=[query]),
        RetrievalRequest(purpose="assessment", enabled=True, queries=[query]),
        RetrievalRequest(purpose="ai_teacher", enabled=True, queries=[query]),
        RetrievalRequest(
            purpose="ppt_image",
            enabled=True,
            queries=["human heart anatomy"],
            category="images",
        ),
    )
    result: dict[str, dict[str, Any]] = {}
    for request in requests:
        package = await gateway.retrieve(request)
        receipt = package.get("receipt") or {}
        source_count = int(receipt.get("source_count") or 0)
        status = str(package.get("status") or receipt.get("status") or "")
        if status != "completed" or source_count < 1:
            errors = ", ".join(receipt.get("error_codes") or []) or "no_sources"
            raise RetrievalDiagnosticError(
                f"{request.purpose} retrieval failed: status={status}; errors={errors}"
            )
        result[request.purpose] = {
            "status": status,
            "category": request.category,
            "queries": package.get("queries") or [],
            "source_count": source_count,
            "sources": [
                {
                    "title": source.get("title"),
                    "url": source.get("url"),
                    "trust_tier": source.get("trust_tier"),
                }
                for source in (package.get("sources") or [])[:3]
            ],
        }
    return result


__all__ = [
    "RetrievalDiagnosticError",
    "assert_retrieval_feature",
    "run_retrieval_matrix",
]
