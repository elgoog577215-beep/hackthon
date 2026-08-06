"""Stable failure classification for the course generation chain.

The generation worker catches everything in one place. Before this module the
catch site stored ``str(exc)`` as the user-facing reason, so a provider timeout
and a corrupt course reached the teacher as the same unexplained sentence, and
raw payload sizes or model IDs leaked into the UI.

This module maps an exception to a stable ``code`` plus a translation key. It is
deliberately a pure function with no TaskManager dependency so the mapping can be
unit-tested directly.

Precedence follows the signal quality:

1. ``exc.code`` — several domain errors already declare one
   (``CourseGenerationBudgetExceeded``, ``CourseGenerationDeadlineExceeded``,
   ``SlideStoryPlanPrerequisiteError``, ``RetrievalProviderError``).
2. Exception type — the workspace/document/version conflicts.
3. Provider heuristics — reuses ``AIBase`` classification rather than
   re-implementing quota/rate-limit/auth string matching.

``retryable`` mirrors the attribute the node retry loop already honours; it is
surfaced so the UI can say whether continuing is worth attempting.
"""

from __future__ import annotations

from typing import Any


GENERATION_ERROR_TRANSLATION_PREFIX = "taskObservability.errors"

# Codes are the wire contract shared with the frontend. Keep them snake_case to
# match the existing import-chain codes (``import_source_missing`` etc.).
GENERATION_ERROR_CODES = {
    "provider_rate_limited",
    "provider_quota_exhausted",
    "provider_auth_failed",
    "provider_unavailable",
    "provider_timeout",
    "generation_budget_exceeded",
    "generation_deadline_exceeded",
    "response_truncated",
    "workspace_missing",
    "revision_conflict",
    "course_missing",
    "generation_failed",
}

_RETRYABLE_BY_CODE = {
    "provider_rate_limited": True,
    "provider_quota_exhausted": False,
    "provider_auth_failed": False,
    "provider_unavailable": True,
    "provider_timeout": True,
    "generation_budget_exceeded": False,
    "generation_deadline_exceeded": False,
    "response_truncated": True,
    "workspace_missing": False,
    "revision_conflict": False,
    "course_missing": False,
    "generation_failed": True,
}

# Codes already declared by domain exceptions, mapped onto the wire vocabulary.
_DECLARED_CODE_ALIASES = {
    "course_generation_budget_exceeded": "generation_budget_exceeded",
    "course_generation_deadline_exceeded": "generation_deadline_exceeded",
    "course_planning_budget_exceeded": "generation_budget_exceeded",
}

_TYPE_NAME_CODES = {
    "GenerationWorkspaceNotFound": "workspace_missing",
    "GenerationWorkspaceConflict": "revision_conflict",
    "CourseDocumentConflict": "revision_conflict",
    "CourseMigrationConflict": "revision_conflict",
    "CourseVersionConflict": "revision_conflict",
    "CourseDocumentNotFound": "course_missing",
    "AIRequestBudgetExceeded": "generation_budget_exceeded",
    "AIResponseTruncated": "response_truncated",
}

_PROVIDER_KIND_CODES = {
    "quota_exhausted": "provider_quota_exhausted",
    "rate_limited": "provider_rate_limited",
}


def _declared_code(exc: BaseException) -> str | None:
    """Read a code the exception already carries, if it is a usable string."""
    for attribute in ("code", "error_code"):
        raw = getattr(exc, attribute, None)
        if not isinstance(raw, str):
            continue
        value = raw.strip()
        if not value:
            continue
        return _DECLARED_CODE_ALIASES.get(value, value)
    return None


def _provider_code(exc: BaseException) -> str | None:
    """Classify provider failures by reusing AIBase's own heuristics."""
    try:
        from ai_base import AIBase, AIProviderRequestError, AIProviderUnavailable
    except ImportError:  # pragma: no cover - defensive
        return None

    if not isinstance(exc, (AIProviderRequestError, AIProviderUnavailable)):
        # Timeouts can arrive as plain asyncio/httpx errors.
        if isinstance(exc, TimeoutError):
            return "provider_timeout"
        return None

    if AIBase._is_authentication_error(exc):
        return "provider_auth_failed"

    reason = str(getattr(exc, "reason", "") or "").strip().lower()
    if reason in {"not_configured", "authentication_failed"}:
        return "provider_auth_failed"

    message = str(exc).lower()
    if "timeout" in message or "timed out" in message:
        return "provider_timeout"

    kind = AIBase._capacity_failure_kind(exc)
    mapped = _PROVIDER_KIND_CODES.get(kind)
    if mapped:
        return mapped
    return "provider_unavailable"


def classify_generation_failure(exc: BaseException) -> dict[str, Any]:
    """Map a generation-chain exception to a stable, user-explainable failure.

    Returns ``{code, translation_key, retryable, technical_detail}``. The caller
    keeps ``technical_detail`` for the collapsible "technical reason" area and
    must not use it as the primary message.
    """
    code = _declared_code(exc)
    if code not in GENERATION_ERROR_CODES:
        code = None
    if code is None:
        code = _TYPE_NAME_CODES.get(type(exc).__name__)
    if code is None:
        code = _provider_code(exc)
    if code is None:
        code = "generation_failed"

    retryable = _RETRYABLE_BY_CODE.get(code, True)
    # An exception may state its own retryability, but only trust it when we did
    # not derive something more specific: ``AIProviderRequestError`` declares a
    # class-level ``retryable = True`` that would otherwise mask a quota-
    # exhausted or auth failure, both of which retrying cannot fix.
    declared_retryable = exc.__dict__.get("retryable")
    if not isinstance(declared_retryable, bool):
        own_class_value = type(exc).__dict__.get("retryable")
        if isinstance(own_class_value, bool):
            declared_retryable = own_class_value
    if isinstance(declared_retryable, bool) and code == "generation_failed":
        retryable = declared_retryable

    return {
        "code": code,
        "translation_key": f"{GENERATION_ERROR_TRANSLATION_PREFIX}.{code}",
        "retryable": retryable,
        "technical_detail": str(exc)[:500],
    }


__all__ = [
    "GENERATION_ERROR_CODES",
    "GENERATION_ERROR_TRANSLATION_PREFIX",
    "classify_generation_failure",
]
