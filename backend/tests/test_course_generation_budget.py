from __future__ import annotations

from types import SimpleNamespace

import pytest

from ai_base import AIBase, AIRequestBudgetExceeded
from course_generation_budget import (
    CourseGenerationBudget,
    CourseGenerationBudgetExceeded,
)
from course_prompt_composer import CoursePromptComposer
from course_service import CourseService


class _CountingCompletions:
    def __init__(self) -> None:
        self.calls = 0

    async def create(self, **_kwargs):
        self.calls += 1
        raise AssertionError("oversized request reached provider")


@pytest.mark.asyncio
async def test_forty_thousand_character_request_is_rejected_before_provider(
    monkeypatch,
):
    monkeypatch.setenv("AI_API_KEY", "test-key")
    completions = _CountingCompletions()
    service = AIBase()
    service.client = SimpleNamespace(
        chat=SimpleNamespace(completions=completions)
    )

    with pytest.raises(AIRequestBudgetExceeded, match="输入超过硬预算"):
        await service._call_llm(
            "四" * 40_000,
            "课程生成",
            max_input_tokens=7000,
            max_input_chars=20_000,
            raise_on_failure=True,
        )

    assert completions.calls == 0


@pytest.mark.asyncio
async def test_character_gate_blocks_payload_even_below_token_estimate_limit(
    monkeypatch,
):
    monkeypatch.setenv("AI_API_KEY", "test-key")
    completions = _CountingCompletions()
    service = AIBase()
    service.client = SimpleNamespace(
        chat=SimpleNamespace(completions=completions)
    )
    prompt = "a" * 20_500
    assert AIBase.estimate_request_tokens(prompt, "") < 7_000

    with pytest.raises(AIRequestBudgetExceeded, match="char_limit=20000"):
        await service._call_llm(
            prompt,
            max_input_tokens=7_000,
            max_input_chars=20_000,
            raise_on_failure=True,
        )

    assert completions.calls == 0


def test_environment_cannot_disable_course_generation_hard_caps(
    monkeypatch,
):
    monkeypatch.setenv("COURSE_GENERATION_MAX_SECTIONS", "999")
    monkeypatch.setenv("COURSE_GENERATION_MAX_INPUT_TOKENS", "999999")
    monkeypatch.setenv("COURSE_GENERATION_MAX_INPUT_CHARS", "999999")
    monkeypatch.setenv(
        "COURSE_GENERATION_PROVIDER_MAX_ATTEMPTS",
        "99",
    )
    monkeypatch.setenv(
        "COURSE_CONTENT_STAGE_TIMEOUT_SECONDS",
        "99999",
    )

    budget = CourseGenerationBudget.from_env()

    assert budget.max_sections == 32
    assert budget.max_input_chars == 24_000
    assert budget.max_input_tokens == 8000
    assert budget.provider_max_attempts == 2
    assert budget.content_stage_timeout_seconds == 900


def test_oversized_course_scope_fails_before_outline_generation():
    budget = CourseGenerationBudget(max_sections=24)

    budget.ensure_section_count(24)
    with pytest.raises(
        CourseGenerationBudgetExceeded,
        match="最多支持 24 个小节",
    ):
        budget.ensure_section_count(25)


def test_continuation_context_is_bounded_and_keeps_recent_tail():
    draft = "\n".join(
        f"## 模块 {index}\n" + ("正文" * 600)
        for index in range(1, 31)
    )

    compact = CoursePromptComposer._compact_continuation_draft(draft)

    assert len(compact) <= 6100
    assert "已省略较早草稿" in compact
    assert "模块 30" in compact
    assert compact.count("- 已完成模块：") == 1


def test_token_estimate_treats_chinese_as_near_token_per_character():
    estimated = AIBase.estimate_request_tokens(
        "课程生成" * 1_000,
        "",
    )

    assert estimated >= 4_000


def test_parallel_node_context_never_depends_on_generated_predecessor_body():
    course = {
        "course_generation_brief": {},
        "nodes": [
            {
                "node_id": "L2-1-1",
                "node_level": 2,
                "node_name": "1.1 前序",
                "learning_objective": "能完成前序任务",
                "node_content": "不应进入提示词的正文标记",
            },
            {
                "node_id": "L2-1-2",
                "node_level": 2,
                "node_name": "1.2 当前",
            },
        ],
    }

    context = CourseService._build_persisted_generation_context(
        course,
        course["nodes"][1],
    )

    assert "已冻结前序教学责任" in context
    assert "能完成前序任务" in context
    assert "不应进入提示词的正文标记" not in context


def test_large_linear_course_context_stays_bounded_by_frozen_responsibilities():
    nodes = [
        {
            "node_id": f"L2-1-{index}",
            "node_level": 2,
            "node_name": f"1.{index} 前序",
            "learning_objective": f"能完成前序任务 {index}",
            "key_points": [f"知识 {index}"],
            "node_content": f"正文标记-{index}-" + ("很长正文" * 2_000),
        }
        for index in range(1, 22)
    ]
    nodes.append({
        "node_id": "L2-1-22",
        "node_level": 2,
        "node_name": "1.22 当前",
    })
    course = {
        "course_generation_brief": {},
        "nodes": nodes,
    }

    context = CourseService._build_persisted_generation_context(
        course,
        nodes[-1],
    )

    assert "正文标记-" not in context
    assert "能完成前序任务 21" in context
    assert "能完成前序任务 1；" not in context
    assert len(context) < 2_000
