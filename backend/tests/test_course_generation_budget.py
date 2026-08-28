from __future__ import annotations

import json
import re
from types import SimpleNamespace

import pytest

from ai_base import AIBase, AIRequestBudgetExceeded
from course_generation_budget import CourseGenerationBudget
from course_generation.prompts import CoursePromptComposer
from course_generation.service import CourseService
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


def test_environment_cannot_disable_per_request_safety_fuses(
    monkeypatch,
):
    # The legacy total-section setting is deliberately ignored.
    monkeypatch.setenv("COURSE_GENERATION_MAX_SECTIONS", "999")
    monkeypatch.setenv("COURSE_GENERATION_MAX_INPUT_TOKENS", "999999")
    monkeypatch.setenv("COURSE_GENERATION_MAX_INPUT_CHARS", "999999")
    monkeypatch.setenv(
        "COURSE_GENERATION_PROVIDER_MAX_ATTEMPTS",
        "99",
    )
    monkeypatch.setenv(
        "COURSE_CONTENT_INACTIVITY_TIMEOUT_SECONDS",
        "99999",
    )
    monkeypatch.setenv("COURSE_CONTENT_NODE_TIMEOUT_SECONDS", "99999")
    monkeypatch.setenv("COURSE_CONTENT_STAGE_TIMEOUT_SECONDS", "99999")

    budget = CourseGenerationBudget.from_env()

    assert "max_sections" not in budget.to_dict()
    assert budget.max_input_chars == 48_000
    assert budget.max_input_tokens == 24_000
    assert budget.provider_max_attempts == 2
    assert budget.content_inactivity_timeout_seconds == 240
    assert "content_node_timeout_seconds" not in budget.to_dict()
    assert "content_stage_timeout_seconds" not in budget.to_dict()


def test_content_budget_is_a_resumable_window_not_a_course_size_cap():
    budget = CourseGenerationBudget()

    assert budget.content_concurrency == 8
    assert budget.content_inactivity_timeout_seconds == 90
    assert not hasattr(budget, "content_node_timeout_seconds")
    assert not hasattr(budget, "content_stage_timeout_seconds")
    assert "max_sections" not in budget.to_dict()


def test_course_budget_has_no_total_section_rejection():
    budget = CourseGenerationBudget()

    assert not hasattr(budget, "ensure_section_count")
    assert not hasattr(budget, "max_sections")


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
        if "全课章节骨架 V2" in system_prompt:
            return json.dumps({
                "course_title": "结构化课程",
                "positioning": "完成一个可检查成果",
                "learning_objectives": ["解释并应用核心方法"],
                "prerequisites": [],
                "chapters": [
                    {
                        "chapter_number": chapter,
                        "title": f"阶段 {chapter}",
                        "learning_focus": f"完成阶段 {chapter}",
                        "section_count": 3,
                    }
                    for chapter in range(1, 7)
                ],
            }, ensure_ascii=False)
        match = re.search(
            r"## 当前批次\n(\{.*?\})\n\n## 当前章已完成",
            system_prompt,
            re.S,
        )
        assert match, system_prompt
        spec = json.loads(match.group(1))
        return json.dumps({
            "sections": [
                {
                    "node_id": node_id,
                    "title": f"核心方法 {node_id}",
                    "learning_objective": "能解释并应用核心方法",
                    "prerequisite_node_ids": [],
                    "assessment": ["完成一次应用任务"],
                    "scope_boundary": "只覆盖当前方法",
                }
                for node_id in spec["expected_node_ids"]
            ],
        }, ensure_ascii=False)

    monkeypatch.setattr(service, "_call_llm", fake_call)
    result = await service.build_course_draft(
        course_id="course-long-requirement",
        topic="课程生成结构",
        requirements="掌握课程生成结构；" * 4_000,
        stop_after_outline=True,
    )

    assert len(payloads) == 7
    for user_prompt, system_prompt, kwargs in payloads:
        assert len(user_prompt) + len(system_prompt) <= 32_000
        assert AIBase.estimate_request_tokens(
            user_prompt,
            system_prompt,
        ) <= 16_000
        assert kwargs["max_input_chars"] == 32_000
        assert kwargs["max_input_tokens"] == 16_000
    outline_stage = result["generation_stage_artifacts"]["outline"]
    assert outline_stage["strategy"] == "hierarchical_chapter_batches"
    assert outline_stage["adaptive_compaction_count"] >= 1
    assert outline_stage["prompt_detail_levels"][0] in {
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

    assert "已确认的前序教学责任" in context
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


def test_realistic_section_reaches_full_detail_instead_of_silent_minimal():
    """真实体量的小节必须能选到 full 正文 prompt。

    输入预算过低时 select_budgeted_prompt 会静默降级到 minimal，
    把教学画像、难度契约、总编契约、细知识结构等全部丢掉——
    表现为"生成成功"，实际却是用最贫瘠的上下文生成的。
    """
    from course_generation.adaptive import (
        PromptCandidate,
        prompt_detail_levels_for_source,
        select_budgeted_prompt,
    )
    from course_generation.prompts import CoursePromptComposer

    budget = CourseGenerationBudget()
    composer = CoursePromptComposer()
    # 12 个知识点、8 条易错、6 条验收：常规大学课程小节的量级。
    node = {
        "node_id": "L2-3-2",
        "node_level": 2,
        "node_name": "3.2 离散型与连续型随机变量",
        "learning_objective": "能够区分离散型与连续型随机变量并正确使用分布律与密度函数",
        "scope_boundary": "只负责一维随机变量的分布描述，不展开多维联合分布",
        "prerequisite_node_ids": ["L2-3-1"],
        "key_points": [f"知识点{index}的规范名称" for index in range(1, 13)],
        "misconceptions": [
            f"把{index}号条件当作无条件成立，忽略定义域与可积性要求"
            for index in range(1, 9)
        ],
        "assessment": [
            f"完成第{index}类任务并说明判断依据与边界" for index in range(1, 7)
        ],
        "knowledge_structure": [{
            "concept_group": f"概念组{index}",
            "group_description": "把随机试验结果数量化并描述其取值规律" * 4,
            "knowledge_points": [{
                "name": f"知识点{index}-{offset}的规范名称",
                "statement": "该知识在当前课程中的成立条件、适用边界与典型用法" * 4,
                "capability": "能够在新情境中独立判断适用条件并完成计算",
                "mistake_points": [{
                    "name": f"忽略知识点{index}-{offset}的成立条件",
                    "description": "在不满足可积性或独立性时直接套用结论" * 2,
                }],
            } for offset in range(1, 3)],
        } for index in range(1, 6)],
        "module_plan": [{
            "module_id": module_id,
            "label": label,
            "block_role": role,
            "required": True,
            "output_contract": f"{label}必须产出的可检查内容" * 2,
            "prompt_instruction": f"{label}的具体写作要求" * 2,
        } for module_id, label, role in (
            ("lesson_goal", "本节任务", "objective"),
            ("core_explanation", "核心教学", "concept"),
            ("math_worked_example", "示范例题", "example"),
            ("learner_action", "学习者行动", "activity"),
            ("feedback_check", "检查与反馈", "feedback"),
        )],
        "difficulty_contract": {
            "target_level": "intermediate",
            "challenge": {"reasoning_depth": 3, "transfer_distance": 3},
            "support": {"scaffold_intensity": 3},
            "mastery": {"independence": 3},
        },
        "grounding_contract": {},
    }
    course_data = {
        "course_id": "budget-detail-course",
        "course_name": "概率论基础：从随机事件到中心极限定理",
        "target_audience": "大学一年级学生",
        "subject_pedagogy_profile": {
            "primary_mode": "math_formal",
            "secondary_mode": None,
            "rationale": "数学课程需要形式化定义与推导" * 4,
            "evidence": [],
            "enabled_module_ids": [],
        },
        "difficulty_profile": {
            "target_level": "intermediate",
            "rationale": "面向大一学生的系统性课程" * 4,
        },
        "nodes": [node],
    }
    context = "## 已确认的前序教学责任\n" + "\n".join(
        f"- 第{index}节：完成对应教学责任并交付可观察证据"
        for index in range(1, 6)
    )

    levels = prompt_detail_levels_for_source(
        {"node": node, "context": context},
        max_input_chars=budget.max_input_chars,
    )
    candidates = []
    for level in levels:
        user_prompt, system_prompt = composer.build_content_prompt(
            course_data=course_data,
            node=node,
            context=context,
            detail_level=level,
        )
        candidates.append(PromptCandidate(
            detail_level=level,
            user_prompt=user_prompt,
            system_prompt=system_prompt,
        ))
    selected = select_budgeted_prompt(
        iter(candidates),
        max_input_chars=budget.max_input_chars,
        max_input_tokens=budget.max_input_tokens,
        token_estimator=AIBase.estimate_request_tokens,
    )

    assert selected is not None
    assert selected.detail_level == "full"
    # full 变体确实比 minimal 大得多，说明这不是一个恰好都能过的小 fixture。
    minimal = next(
        item for item in candidates if item.detail_level == "minimal"
    )
    full_tokens = AIBase.estimate_request_tokens(
        selected.user_prompt, selected.system_prompt
    )
    minimal_tokens = AIBase.estimate_request_tokens(
        minimal.user_prompt, minimal.system_prompt
    )
    assert full_tokens > minimal_tokens * 1.5
    # 旧的 7000 token 闸门会把这一节挤到 minimal。
    assert full_tokens > 7_000


def test_content_concurrency_default_matches_measured_endpoint_capacity(
    monkeypatch,
):
    """正文并发默认值 = 实测端点容量，且必须可被环境变量覆盖（B-4）。

    走真实流式正文路径多轮实测（`backend/tools/content_parallel_bench.py`）：
    并发 4 墙钟均值 82.0s / 并发 6 为 66.4s / 并发 8 为 65.5s。
    **4 -> 8 降 20.1%**，但 6 与 8 分不出高下（均值差 1.0s，区间重叠）；
    再往上单节耗时明显变长。取 8 是保守选择。

    标定方法与判据见 `docs/验收/并发容量标定运行手册.md`——
    **换端点或换模型必须重测**，最优并发是端点属性不是代码属性。
    """
    monkeypatch.delenv("COURSE_CONTENT_CONCURRENCY", raising=False)
    assert CourseGenerationBudget.from_env().content_concurrency == 8

    # 换端点/免费额度时必须能立刻降下来，且不用改代码
    monkeypatch.setenv("COURSE_CONTENT_CONCURRENCY", "2")
    assert CourseGenerationBudget.from_env().content_concurrency == 2
    monkeypatch.setenv("COURSE_CONTENT_CONCURRENCY", "1")
    assert CourseGenerationBudget.from_env().content_concurrency == 1

    # 也能往上调
    monkeypatch.setenv("COURSE_CONTENT_CONCURRENCY", "12")
    assert CourseGenerationBudget.from_env().content_concurrency == 12

    monkeypatch.setenv("COURSE_CONTENT_CONCURRENCY", "999")
    assert CourseGenerationBudget.from_env().content_concurrency == 16


@pytest.mark.asyncio
async def test_node_runtime_counts_model_calls_cumulatively(monkeypatch):
    """E-1 账单：真实服务必须逐次累加调用数，本地降级不计数。"""
    service = CourseService()
    node = {
        "node_id": "L2-1-1",
        "node_level": 2,
        "node_name": "调用计数",
        "learning_objective": "能解释调用计数",
        "scope_boundary": "只覆盖当前小节",
        "key_points": ["计数"],
        "assessment": ["说明一次计数"],
        "module_plan": [{
            "module_id": "core_explanation",
            "label": "核心讲解",
            "required": True,
            "output_contract": "解释计数",
        }],
        "difficulty_contract": {},
        "grounding_contract": {},
    }
    course = {
        "course_id": "course-call-ledger",
        "course_name": "调用账单课程",
        "course_generation_brief": {},
        "nodes": [node],
    }

    async def fake_stream(**_kwargs):
        yield "## 核心讲解\n\n稳定知识具有明确条件与边界，并可用于应用任务。"

    async def on_chunk(_chunk):
        return None

    monkeypatch.setattr(service, "_stream_llm", fake_stream)
    await service.generate_node_content_stream(
        course_id=course["course_id"], node=node,
        config=NodeGenerationConfig(), on_chunk=on_chunk, course_data=course,
    )
    assert node["generation_runtime"]["model_call_count"] == 1

    # 第二次真实调用：累加，而不是被重置。
    await service.generate_node_content_stream(
        course_id=course["course_id"], node=node,
        config=NodeGenerationConfig(), on_chunk=on_chunk, course_data=course,
    )
    assert node["generation_runtime"]["model_call_count"] == 2

    # 本地降级没有打到提供方，不得计入账单。
    async def failed_stream(**_kwargs):
        if False:
            yield ""
        raise AIRequestBudgetExceeded("模拟提供方前置失败")

    monkeypatch.setattr(service, "_stream_llm", failed_stream)
    await service.generate_node_content_stream(
        course_id=course["course_id"], node=node,
        config=NodeGenerationConfig(), on_chunk=on_chunk, course_data=course,
    )
    assert node["generation_runtime"]["generation_source"] == (
        "deterministic_local_fallback"
    )
    assert node["generation_runtime"]["model_call_count"] == 2
