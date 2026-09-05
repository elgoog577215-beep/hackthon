import asyncio

import pytest

from ai_base import (
    AIProviderRequestError,
    AIProviderUnavailable,
    AIRequestBudgetExceeded,
    AIResponseTruncated,
)
from course_generation_budget import (
    CourseGenerationBudgetExceeded,
    CourseGenerationDeadlineExceeded,
)
from course_generation_errors import (
    GENERATION_ERROR_CODES,
    classify_generation_failure,
)
from generation_workspace import (
    GenerationWorkspaceConflict,
    GenerationWorkspaceNotFound,
)


def test_declared_codes_are_reused_instead_of_reinvented():
    """Domain errors already carry a code; the classifier must not ignore it."""
    budget = classify_generation_failure(CourseGenerationBudgetExceeded("too big"))
    deadline = classify_generation_failure(CourseGenerationDeadlineExceeded("too slow"))

    assert budget["code"] == "generation_budget_exceeded"
    assert deadline["code"] == "generation_deadline_exceeded"
    assert budget["retryable"] is False
    assert deadline["retryable"] is False


def test_provider_failures_are_separated_by_cause():
    """A rate limit and an auth failure need different next actions."""
    rate_limited = classify_generation_failure(
        AIProviderRequestError("Error code: 429 limit_burst_rate reached")
    )
    quota = classify_generation_failure(
        AIProviderRequestError("insufficient_quota for this organization")
    )
    auth = classify_generation_failure(AIProviderUnavailable("authentication_failed"))
    unavailable = classify_generation_failure(AIProviderUnavailable("provider_down"))

    assert rate_limited["code"] == "provider_rate_limited"
    assert quota["code"] == "provider_quota_exhausted"
    assert auth["code"] == "provider_auth_failed"
    assert unavailable["code"] == "provider_unavailable"

    # Retrying a rate limit is sensible; retrying a bad key or a dry quota is not.
    assert rate_limited["retryable"] is True
    assert quota["retryable"] is False
    assert auth["retryable"] is False


def test_truncated_and_budget_ai_errors_keep_their_own_meaning():
    truncated = classify_generation_failure(AIResponseTruncated("hit max_tokens"))
    budget = classify_generation_failure(
        AIRequestBudgetExceeded("payload 210000 tokens > budget")
    )

    assert truncated["code"] == "response_truncated"
    assert truncated["retryable"] is True
    assert budget["code"] == "generation_budget_exceeded"
    assert budget["retryable"] is False


def test_workspace_and_revision_conflicts_are_not_provider_errors():
    missing = classify_generation_failure(GenerationWorkspaceNotFound("job-1"))
    conflict = classify_generation_failure(GenerationWorkspaceConflict("stale"))

    assert missing["code"] == "workspace_missing"
    assert conflict["code"] == "revision_conflict"
    assert missing["retryable"] is False
    assert conflict["retryable"] is False


def test_timeout_is_classified_even_without_a_provider_wrapper():
    assert classify_generation_failure(TimeoutError("timed out"))["code"] == "provider_timeout"
    assert classify_generation_failure(
        AIProviderRequestError("request timed out after 120s")
    )["code"] == "provider_timeout"


def test_unknown_failures_stay_generic_but_never_leak_the_raw_reason_as_message():
    """The raw text is kept as technical detail only, and is length-bounded."""
    result = classify_generation_failure(RuntimeError("x" * 900))

    assert result["code"] == "generation_failed"
    assert result["translation_key"] == "taskObservability.errors.generation_failed"
    assert len(result["technical_detail"]) == 500


def test_every_produced_code_is_part_of_the_published_contract():
    samples = [
        CourseGenerationBudgetExceeded("a"),
        CourseGenerationDeadlineExceeded("b"),
        AIProviderRequestError("429 rate limit"),
        AIProviderUnavailable("not_configured"),
        AIResponseTruncated("c"),
        GenerationWorkspaceNotFound("d"),
        GenerationWorkspaceConflict("e"),
        TimeoutError("f"),
        RuntimeError("g"),
        ValueError("h"),
    ]

    for exc in samples:
        assert classify_generation_failure(exc)["code"] in GENERATION_ERROR_CODES


def test_a_specific_classification_is_not_masked_by_an_inherited_retryable():
    """AIProviderRequestError declares retryable=True at class level.

    A quota-exhausted failure inherits that flag, but retrying cannot refill a
    quota. The derived code must win over the inherited default.
    """
    quota = classify_generation_failure(
        AIProviderRequestError("insufficient_quota for this organization")
    )
    assert quota["code"] == "provider_quota_exhausted"
    assert quota["retryable"] is False


def test_unclassified_failures_still_honour_a_declared_retryable_flag():
    """When we learned nothing specific, the exception's own claim is all we have."""

    class DeliberatelyFinal(RuntimeError):
        retryable = False

    result = classify_generation_failure(DeliberatelyFinal("give up"))
    assert result["code"] == "generation_failed"
    assert result["retryable"] is False


def test_cancellation_is_never_reported_as_a_failure_by_the_caller():
    """CancelledError must not reach the classifier - the worker handles it first.

    Guards the contract: if this ever changes, a user's own pause would be
    classified and shown back to them as a generation error.
    """
    assert not issubclass(asyncio.CancelledError, Exception)
