"""Per-request and resumable-work-window budgets for course generation.

These settings never cap total course size.  They bound one provider request or
one resumable execution window so a large course is split, checkpointed and
continued instead of rejected or sent as one oversized payload.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass

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


class TeacherScriptGenerationTimeout(AIProviderRequestError):
    """A teacher-script model call exceeded its active execution window."""

    retryable = True
    code = "lesson_script_model_timeout"


@dataclass(frozen=True)
class CourseGenerationBudget:
    max_input_chars: int = 32_000
    max_input_tokens: int = 16_000
    outline_max_output_tokens: int = 8192
    content_max_output_tokens: int = 8192
    provider_max_attempts: int = 2
    # Legacy field name: structured calls now interpret this as continuous
    # stream inactivity, never total wall-clock duration.
    call_timeout_seconds: int = 90
    content_inactivity_timeout_seconds: int = 90
    # Starts only after a request owns the shared teaching-model slot. Queue
    # time is deliberately excluded so a large lesson batch cannot expire
    # while it is merely waiting for capacity.
    teacher_script_request_timeout_seconds: int = 180
    # 正文并行阶段的默认并发。**8 是按端点实测定的，不是拍的**——
    # 标定方法与完整数据见 `docs/验收/并发容量标定运行手册.md`。
    #
    # 走真实流式正文路径（`content_parallel_bench.py`）、8 个小节、多轮取均值：
    #   并发 4  墙钟 82.0s  排队 0.3s  有效并行度 3.51  单节中位 35.2s
    #   并发 6  墙钟 66.4s  排队 0.8s  有效并行度 4.68  单节中位 33.9s
    #   并发 8  墙钟 65.5s  排队 2.7s  有效并行度 5.63  单节中位 44.4s
    #
    # 4 -> 8 墙钟降 20.1%，这条是实的。但 **6 与 8 分不出高下**
    # （均值差 1.0s，多轮区间高度重叠），取 8 只是保守选择，不是"8 明显更优"。
    # 再往上单节耗时明显变长（端点把并发摊薄，每条流都变慢），收益被吃掉。
    #
    # ⚠️ **换端点或换模型必须重新标定**，最优并发是端点属性不是代码属性。
    # 换端点后照手册跑一遍即可。日常无需改代码：
    # `COURSE_CONTENT_CONCURRENCY` 随时可覆盖（免费额度时降到 2/4）。
    content_concurrency: int = 8
    content_max_retries: int = 1

    @classmethod
    def from_env(cls) -> CourseGenerationBudget:
        return cls(
            max_input_chars=_env_int(
                "COURSE_GENERATION_MAX_INPUT_CHARS",
                32_000,
                minimum=8_000,
                maximum=48_000,
            ),
            max_input_tokens=_env_int(
                "COURSE_GENERATION_MAX_INPUT_TOKENS",
                16_000,
                minimum=2000,
                maximum=24_000,
            ),
            outline_max_output_tokens=_env_int(
                "COURSE_OUTLINE_MAX_OUTPUT_TOKENS",
                8192,
                minimum=1024,
                maximum=8192,
            ),
            content_max_output_tokens=_env_int(
                "COURSE_CONTENT_MAX_OUTPUT_TOKENS",
                8192,
                minimum=2048,
                maximum=32000,
            ),
            provider_max_attempts=_env_int(
                "COURSE_GENERATION_PROVIDER_MAX_ATTEMPTS",
                2,
                minimum=1,
                maximum=2,
            ),
            call_timeout_seconds=_env_int(
                "COURSE_GENERATION_INACTIVITY_TIMEOUT_SECONDS",
                90,
                minimum=30,
                maximum=600,
            ),
            content_inactivity_timeout_seconds=_env_int(
                "COURSE_CONTENT_INACTIVITY_TIMEOUT_SECONDS",
                90,
                minimum=30,
                maximum=240,
            ),
            teacher_script_request_timeout_seconds=_env_int(
                "COURSE_TEACHER_SCRIPT_REQUEST_TIMEOUT_SECONDS",
                180,
                minimum=30,
                maximum=600,
            ),
            content_concurrency=_env_int(
                "COURSE_CONTENT_CONCURRENCY",
                8,
                minimum=1,
                maximum=16,
            ),
            content_max_retries=_env_int(
                "COURSE_CONTENT_MAX_RETRIES",
                1,
                minimum=0,
                maximum=2,
            ),
        )

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


__all__ = [
    "CourseGenerationBudget",
    "CourseGenerationBudgetExceeded",
    "CourseGenerationDeadlineExceeded",
]
