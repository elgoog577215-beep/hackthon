from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

from ai_base import AIBase, AIRequestBudgetExceeded
from course_generation_budget import (
    CourseGenerationBudget,
    CourseGenerationBudgetExceeded,
)
from course_prompt_composer import CoursePromptComposer
from course_service import CourseService
from models import NodeGenerationConfig


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


def test_default_content_waves_fit_inside_stage_deadline():
    budget = CourseGenerationBudget()
    worst_case_seconds = (
        math.ceil(budget.max_sections / budget.content_concurrency)
        * budget.content_node_timeout_seconds
    )

    assert worst_case_seconds <= budget.content_stage_timeout_seconds


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


@pytest.mark.asyncio
async def test_outline_compacts_forty_thousand_character_requirement_before_api(
    monkeypatch,
):
    service = CourseService()
    payloads = []

    async def fake_call(prompt, system_prompt, **kwargs):
        payloads.append((prompt, system_prompt, kwargs))
        return """{
          "course_title": "结构化课程",
          "positioning": "完成一个可检查成果",
          "learning_objectives": ["解释并应用核心方法"],
          "prerequisites": [],
          "chapters": [{
            "chapter_number": 1,
            "title": "基础",
            "learning_focus": "建立核心能力",
            "sections": [{
              "node_id": "L2-1-1",
              "section_number": "1.1",
              "title": "核心方法",
              "learning_objective": "能解释并应用核心方法",
              "prerequisite_node_ids": [],
              "assessment": ["完成一次应用任务"],
              "scope_boundary": "只覆盖当前方法"
            }]
          }]
        }"""

    monkeypatch.setattr(service, "_call_llm", fake_call)
    result = await service.build_course_draft(
        course_id="course-long-requirement",
        topic="课程生成结构",
        requirements="掌握课程生成结构；" * 4_000,
        stop_after_outline=True,
    )

    assert len(payloads) == 1
    user_prompt, system_prompt, kwargs = payloads[0]
    assert len(user_prompt) + len(system_prompt) <= 20_000
    assert AIBase.estimate_request_tokens(
        user_prompt,
        system_prompt,
    ) <= 7_000
    assert kwargs["max_input_chars"] == 20_000
    assert kwargs["max_input_tokens"] == 7_000
    outline_stage = result["generation_stage_artifacts"]["outline"]
    assert outline_stage["adaptive_compaction_count"] == 1
    assert outline_stage["prompt_detail_levels"][-1] in {
        "compact",
        "minimal",
    }


@pytest.mark.asyncio
async def test_node_content_uses_minimal_semantic_prompt_instead_of_failing(
    monkeypatch,
):
    service = CourseService()
    captured = {}
    node = {
        "node_id": "L2-1-1",
        "node_level": 2,
        "node_name": "超长小节",
        "learning_objective": "理解核心机制",
        "scope_boundary": "只覆盖当前机制",
        "key_points": ["稳定知识"],
        "knowledge_structure": [{
            "concept_group": "核心",
            "knowledge_points": [{
                "name": "稳定知识",
                "statement": "稳定知识具有明确条件与边界",
            }],
        }],
        "assessment": ["完成一次应用任务"],
        "module_plan": [{
            "module_id": "core_explanation",
            "label": "核心讲解",
            "required": True,
            "output_contract": "解释稳定知识并给出边界",
        }],
        "difficulty_contract": {},
        "grounding_contract": {},
    }
    course = {
        "course_id": "course-long-node",
        "course_name": "长上下文课程",
        "course_generation_brief": {
            "style_requirements": ["少废话"],
            "raw_requirement": "要求" * 40_000,
        },
        "subject_pedagogy_profile": {"notes": "画像" * 40_000},
        "difficulty_profile": {"notes": "难度" * 40_000},
        "course_composition_profile": {"notes": "编排" * 40_000},
        "nodes": [node],
    }

    async def fake_stream(**kwargs):
        captured.update(kwargs)
        yield "## 核心讲解\n\n稳定知识具有明确条件与边界，并可用于应用任务。"

    monkeypatch.setattr(service, "_stream_llm", fake_stream)
    chunks = []

    async def on_chunk(chunk):
        chunks.append(chunk)

    content = await service.generate_node_content_stream(
        course_id=course["course_id"],
        node=node,
        config=NodeGenerationConfig(custom_instruction="指令" * 40_000),
        on_chunk=on_chunk,
        course_data=course,
    )

    assert "稳定知识" in content
    assert len(captured["prompt"]) + len(captured["system_prompt"]) <= 20_000
    assert AIBase.estimate_request_tokens(
        captured["prompt"],
        captured["system_prompt"],
    ) <= 7_000
    runtime = node["generation_runtime"]
    assert runtime["prompt_detail_level"] == "minimal"
    assert runtime["adaptive_compaction"] is True
    assert runtime["generation_source"] == "model"


@pytest.mark.asyncio
async def test_node_provider_failure_degrades_only_that_node(monkeypatch):
    service = CourseService()
    node = {
        "node_id": "L2-1-1",
        "node_level": 2,
        "node_name": "稳定性",
        "learning_objective": "能解释稳定性",
        "scope_boundary": "只覆盖当前小节",
        "key_points": ["故障隔离"],
        "assessment": ["说明一次局部降级"],
        "module_plan": [{
            "module_id": "core_explanation",
            "label": "核心讲解",
            "required": True,
            "output_contract": "解释故障隔离",
        }],
        "difficulty_contract": {},
        "grounding_contract": {},
    }
    course = {
        "course_id": "course-provider-fallback",
        "course_name": "稳定性课程",
        "course_generation_brief": {},
        "nodes": [node],
    }

    async def failed_stream(**_kwargs):
        if False:
            yield ""
        raise AIRequestBudgetExceeded("模拟提供方前置失败")

    monkeypatch.setattr(service, "_stream_llm", failed_stream)
    chunks = []

    async def on_chunk(chunk):
        chunks.append(chunk)

    content = await service.generate_node_content_stream(
        course_id=course["course_id"],
        node=node,
        config=NodeGenerationConfig(),
        on_chunk=on_chunk,
        course_data=course,
    )

    assert "## 核心讲解" in content
    assert node["generation_runtime"]["generation_source"] == (
        "deterministic_local_fallback"
    )
    assert node["needs_manual_review"] is True


@pytest.mark.asyncio
async def test_node_provider_failure_preserves_existing_draft_for_resume(
    monkeypatch,
):
    service = CourseService()
    node = {
        "node_id": "L2-1-1",
        "node_level": 2,
        "node_name": "草稿恢复",
        "learning_objective": "完成当前小节",
        "scope_boundary": "只覆盖当前小节",
        "key_points": ["恢复边界"],
        "assessment": ["说明恢复边界"],
        "module_plan": [{
            "module_id": "core_explanation",
            "label": "核心讲解",
            "required": True,
            "output_contract": "解释恢复边界",
        }],
        "difficulty_contract": {},
        "grounding_contract": {},
    }
    course = {
        "course_id": "course-draft-resume",
        "course_name": "草稿恢复课程",
        "course_generation_brief": {},
        "nodes": [node],
    }

    async def failed_stream(**_kwargs):
        if False:
            yield ""
        raise AIRequestBudgetExceeded("模拟续写失败")

    monkeypatch.setattr(service, "_stream_llm", failed_stream)
    chunks = []

    async def on_chunk(chunk):
        chunks.append(chunk)

    with pytest.raises(AIRequestBudgetExceeded, match="模拟续写失败"):
        await service.generate_node_content_stream(
            course_id=course["course_id"],
            node=node,
            config=NodeGenerationConfig(),
            on_chunk=on_chunk,
            course_data=course,
            existing_draft="## 已生成草稿\n\n保留这段真实内容。",
        )

    assert chunks == []
    assert node["generation_runtime"]["continued_from_chars"] > 0
    assert node["generation_runtime"]["generation_source"] == "model"


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
