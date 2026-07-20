"""Hard runtime budgets for the first-course generation pipeline.

The limits in this module are product safety boundaries, not performance hints.
Environment variables may tune them only inside the code-level caps below, so a
deployment cannot accidentally restore hour-long waits or oversized requests.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Any

from ai_base import AIProviderRequestError


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


class CourseGenerationBudgetExceeded(RuntimeError):
    """A request cannot safely enter the model pipeline."""

    retryable = False
    code = "course_generation_budget_exceeded"


class CourseGenerationDeadlineExceeded(AIProviderRequestError):
    """A bounded generation unit exhausted its active runtime budget."""

    retryable = False
    code = "course_generation_deadline_exceeded"


@dataclass(frozen=True)
class CourseGenerationBudget:
    max_sections: int = 24
    max_input_chars: int = 20_000
    max_input_tokens: int = 7000
    outline_max_output_tokens: int = 4096
    content_max_output_tokens: int = 8192
    provider_max_attempts: int = 2
    call_timeout_seconds: int = 90
    content_node_timeout_seconds: int = 75
    content_stage_timeout_seconds: int = 480
    content_concurrency: int = 4
    content_max_retries: int = 1

    @classmethod
    def from_env(cls) -> CourseGenerationBudget:
        return cls(
            max_sections=_env_int(
                "COURSE_GENERATION_MAX_SECTIONS",
                24,
                minimum=1,
                maximum=32,
            ),
            max_input_chars=_env_int(
                "COURSE_GENERATION_MAX_INPUT_CHARS",
                20_000,
                minimum=8_000,
                maximum=24_000,
            ),
            max_input_tokens=_env_int(
                "COURSE_GENERATION_MAX_INPUT_TOKENS",
                7000,
                minimum=2000,
                maximum=8000,
            ),
            outline_max_output_tokens=_env_int(
                "COURSE_OUTLINE_MAX_OUTPUT_TOKENS",
                4096,
                minimum=1024,
                maximum=8192,
            ),
            content_max_output_tokens=_env_int(
                "COURSE_CONTENT_MAX_OUTPUT_TOKENS",
                8192,
                minimum=2048,
                maximum=12000,
            ),
            provider_max_attempts=_env_int(
                "COURSE_GENERATION_PROVIDER_MAX_ATTEMPTS",
                2,
                minimum=1,
                maximum=2,
            ),
            call_timeout_seconds=_env_int(
                "COURSE_GENERATION_CALL_TIMEOUT_SECONDS",
                90,
                minimum=30,
                maximum=180,
            ),
            content_node_timeout_seconds=_env_int(
                "COURSE_CONTENT_NODE_TIMEOUT_SECONDS",
                75,
                minimum=60,
                maximum=240,
            ),
            content_stage_timeout_seconds=_env_int(
                "COURSE_CONTENT_STAGE_TIMEOUT_SECONDS",
                480,
                minimum=120,
                maximum=900,
            ),
            content_concurrency=_env_int(
                "COURSE_CONTENT_CONCURRENCY",
                4,
                minimum=1,
                maximum=6,
            ),
            content_max_retries=_env_int(
                "COURSE_CONTENT_MAX_RETRIES",
                1,
                minimum=0,
                maximum=2,
            ),
        )

    def ensure_section_count(self, section_count: Any) -> None:
        try:
            actual = int(section_count or 0)
        except (TypeError, ValueError):
            return
        if actual > self.max_sections:
            raise CourseGenerationBudgetExceeded(
                f"单门课程最多支持 {self.max_sections} 个小节，当前请求为 "
                f"{actual} 个；请拆分为多门课程后再生成"
            )

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


__all__ = [
    "CourseGenerationBudget",
    "CourseGenerationBudgetExceeded",
    "CourseGenerationDeadlineExceeded",
]
