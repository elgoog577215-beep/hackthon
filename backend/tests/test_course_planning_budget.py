import json

from ai_base import AIBase
from course_planning_budget import (
    CoursePlanningBudget,
    build_compact_planning_context,
    build_teaching_plan_batches,
    select_batch_knowledge_registry,
)
from course_prompt_composer import CoursePromptComposer
from course_teaching_plan_v3 import (
    normalize_teaching_plan_batch_v3,
    normalize_teaching_plan_skeleton_v3,
    promote_course_teaching_plan_v3,
    validate_teaching_plan_batch_v3,
    validate_teaching_plan_skeleton_v3,
)


def _section(index, chapter_id="chapter-1"):
    return {
        "node_id": f"L2-1-{index}",
        "chapter_id": chapter_id,
        "title": f"第{index}节",
        "learning_objective": f"完成任务{index}",
        "scope_boundary": f"只负责任务{index}",
        "prerequisite_node_ids": [],
        "difficulty_contract": {
            "target_level": "intermediate",
            "scaffolding": "guided",
        },
        "module_plan": [{
            "module_id": "core_explanation",
            "label": "核心讲解",
            "block_role": "concept",
            "required": True,
            "output_contract": "解释核心知识并给出边界",
        }],
    }


def test_planning_context_deduplicates_shared_contracts():
    sections = [_section(index) for index in range(1, 13)]
    context = build_compact_planning_context(
        sections,
        composition_style="worked_example_first",
    )

    assert len(context["module_catalog"]) == 1
    assert context["difficulty_baseline"]["target_level"] == "intermediate"
    assert all(not item["difficulty_delta"] for item in context["sections"])
    assert all(item["allowed_module_ids"] == ["core_explanation"] for item in context["sections"])

    naive = json.dumps(sections, ensure_ascii=False)
    compact = json.dumps(context, ensure_ascii=False)
    assert len(compact) < len(naive) * 0.8


def test_compact_plan_is_promoted_to_one_stable_v3_contract():
    compact = {
        "schema_version": "course_teaching_plan_v2",
        "source_outline_revision_id": "outline-1",
        "sections": [{
            "node_id": "L2-1-1",
            "knowledge_structure": [{
                "concept_group": "核心",
                "knowledge_points": [{
                    "name": "稳定知识",
                    "statement": "稳定知识有明确陈述",
                    "prerequisite_names": [],
                }],
            }],
            "reused_knowledge_names": [],
            "teaching_modules": [{
                "module_id": "core_explanation",
                "knowledge_names": ["稳定知识"],
            }],
        }],
    }

    first = promote_course_teaching_plan_v3(
        compact,
        outline_revision_id="outline-1",
    )
    resumed = promote_course_teaching_plan_v3(
        first,
        outline_revision_id="outline-1",
    )

    assert first["schema_version"] == "course_teaching_plan_v3"
    assert first["skeleton_revision_id"].startswith(
        "teaching_skeleton_"
    )
    assert resumed == first


def test_batch_planner_prefers_chapter_boundaries_and_enforces_budgets():
    sections = [
        *[_section(index, "chapter-1") for index in range(1, 5)],
        *[_section(index, "chapter-2") for index in range(5, 9)],
    ]
    skeleton = {
        "sections": [{
            "node_id": item["node_id"],
            "owned_knowledge_keys": [f"{item['node_id']}-K1", f"{item['node_id']}-K2"],
            "reused_knowledge_keys": [],
        } for item in sections],
    }
    batches = build_teaching_plan_batches(
        sections,
        skeleton,
        CoursePlanningBudget(batch_max_sections=3, batch_max_knowledge=5),
    )

    assert [item["section_ids"] for item in batches] == [
        ["L2-1-1", "L2-1-2"],
        ["L2-1-3", "L2-1-4"],
        ["L2-1-5", "L2-1-6"],
        ["L2-1-7", "L2-1-8"],
    ]
    assert all(item["knowledge_count"] <= 5 for item in batches)
    assert all(item["estimated_input_tokens"] <= 7000 for item in batches)
    assert all(item["estimated_output_tokens"] <= 8000 for item in batches)


def test_twenty_one_section_plan_uses_scoped_bounded_batch_prompts():
    sections = [
        _section(index, f"chapter-{(index - 1) // 3 + 1}")
        for index in range(1, 22)
    ]
    planning_context = build_compact_planning_context(
        sections,
        composition_style="balanced",
    )
    registry = []
    identities = []
    for index, section in enumerate(sections, start=1):
        keys = [f"K{index:02d}-{offset}" for offset in range(1, 4)]
        identities.append({
            "node_id": section["node_id"],
            "owned_knowledge_keys": keys,
            "reused_knowledge_keys": [],
        })
        for offset, key in enumerate(keys, start=1):
            registry.append({
                "knowledge_key": key,
                "name": f"第{index}节知识{offset}",
                "statement": (
                    f"第{index}节知识{offset}的稳定陈述，"
                    "用于检验批次输入是否只携带直接相关知识。"
                ),
                "owner_node_id": section["node_id"],
                "reused_in_node_ids": [],
                "prerequisite_keys": (
                    [f"K{index - 1:02d}-3"] if index > 1 and offset == 1 else []
                ),
                "module_ids": ["core_explanation"],
            })
    skeleton = {
        "revision_id": "skeleton-21",
        "knowledge_registry": registry,
        "sections": identities,
    }
    budget = CoursePlanningBudget()
    skeleton_prompt = (
        CoursePromptComposer().build_teaching_plan_skeleton_v3_prompt(
            course_title="规模回归课程",
            positioning="验证结构预算",
            learning_objectives=[],
            planning_context=planning_context,
        )
    )
    assert AIBase.estimate_request_tokens(
        "规划全课知识职责骨架 V3，只输出 JSON。",
        skeleton_prompt,
    ) <= budget.max_input_tokens
    batches = build_teaching_plan_batches(
        planning_context["sections"],
        skeleton,
        budget,
    )
    composer = CoursePromptComposer()
    compact_by_id = {
        item["node_id"]: item
        for item in planning_context["sections"]
    }
    identity_by_id = {
        item["node_id"]: item
        for item in identities
    }
    prompt_chars = 0
    prompt_tokens = []
    for spec in batches:
        section_ids = spec["section_ids"]
        system_prompt = composer.build_teaching_plan_batch_v3_prompt(
            course_title="规模回归课程",
            positioning="验证结构预算",
            batch_spec=spec,
            batch_sections=[
                compact_by_id[node_id] for node_id in section_ids
            ],
            knowledge_registry=select_batch_knowledge_registry(
                skeleton,
                section_ids,
            ),
            section_identities=[
                identity_by_id[node_id] for node_id in section_ids
            ],
            module_catalog=planning_context["module_catalog"],
            skeleton_revision_id="skeleton-21",
        )
        user_prompt = f"生成详细小节教案批次 {spec['batch_id']}，只输出 JSON。"
        prompt_chars += len(user_prompt) + len(system_prompt)
        prompt_tokens.append(
            AIBase.estimate_request_tokens(user_prompt, system_prompt)
        )

    assert len(batches) == 7
    assert max(prompt_tokens) <= budget.max_input_tokens
    assert prompt_chars < 100_000


def test_twenty_four_section_rich_skeleton_stays_under_final_input_gate():
    module_ids = [
        "lesson_goal",
        "core_explanation",
        "learner_action",
        "feedback_check",
        "math_intuition",
        "math_formalization",
        "math_worked_example",
        "math_variation",
        "math_error_analysis",
    ]
    sections = []
    for index in range(1, 25):
        section = _section(
            index,
            f"chapter-{(index - 1) // 3 + 1}",
        )
        section["difficulty_contract"] = {
            "target_level": "intermediate",
            "node_role": (
                "worked_example"
                if index % 3 == 1
                else "guided_practice"
            ),
            "subject_task": (
                "在新情境中比较方案、处理约束并论证取舍，"
                "形成可观察且可复验的完整学习任务"
            ),
            "new_concept_load": 2,
            "challenge": {
                "reasoning_depth": 4,
                "abstraction": 4,
                "transfer_distance": 3,
                "integration_scope": 3,
                "task_complexity": 4,
                "prerequisite_load": 3,
            },
            "support": {
                "scaffold_intensity": 3,
                "pacing_granularity": 3,
                "feedback_frequency": 3,
            },
            "mastery": {
                "accuracy": 4,
                "execution": 4,
                "explanation": 4,
                "independence": 3,
                "transfer": 3,
            },
        }
        section["module_plan"] = [
            {
                "module_id": module_id,
                "label": f"模块 {module_index}",
                "block_role": "concept",
                "required": True,
                "output_contract": (
                    "解释当前知识的成立条件、边界、示例与检查方式"
                ),
            }
            for module_index, module_id in enumerate(
                module_ids,
                start=1,
            )
        ]
        sections.append(section)

    context = build_compact_planning_context(
        sections,
        composition_style="balanced",
    )
    prompt = (
        CoursePromptComposer().build_teaching_plan_skeleton_v3_prompt(
            course_title="二十四节规模回归课程",
            positioning="验证真实难度和模块合同不会撑爆骨架请求",
            learning_objectives=["理解", "应用", "迁移"],
            planning_context=context,
        )
    )
    estimated = AIBase.estimate_request_tokens(
        "规划全课知识职责骨架 V3，只输出 JSON。",
        prompt,
    )

    assert estimated <= CoursePlanningBudget().max_input_tokens
    assert prompt.count('"module_sets"') == 1


def test_batch_registry_contains_only_current_and_direct_prerequisite_keys():
    skeleton = {
        "knowledge_registry": [
            {
                "knowledge_key": f"K{index}",
                "prerequisite_keys": [f"K{index - 1}"] if index > 1 else [],
            }
            for index in range(1, 61)
        ],
        "sections": [{
            "node_id": "L2-1-20",
            "owned_knowledge_keys": ["K20"],
            "reused_knowledge_keys": [],
        }],
    }

    selected = select_batch_knowledge_registry(
        skeleton,
        ["L2-1-20"],
    )

    assert [item["knowledge_key"] for item in selected] == ["K19", "K20"]


def test_skeleton_rejects_prerequisite_reserved_for_a_future_section():
    sections = [_section(1), _section(2)]
    skeleton = normalize_teaching_plan_skeleton_v3({
        "knowledge_registry": [
            {
                "knowledge_key": "K1",
                "name": "当前知识",
                "statement": "当前小节负责的知识",
                "owner_node_id": "L2-1-1",
                "reused_in_node_ids": [],
                "prerequisite_keys": ["K2"],
                "module_ids": ["core_explanation"],
            },
            {
                "knowledge_key": "K2",
                "name": "未来知识",
                "statement": "后续小节保留的知识",
                "owner_node_id": "L2-1-2",
                "reused_in_node_ids": [],
                "prerequisite_keys": [],
                "module_ids": ["core_explanation"],
            },
        ],
        "sections": [
            {"node_id": "L2-1-1", "owned_knowledge_keys": ["K1"], "reused_knowledge_keys": []},
            {"node_id": "L2-1-2", "owned_knowledge_keys": ["K2"], "reused_knowledge_keys": []},
        ],
    }, outline_revision_id="outline-1")

    report = validate_teaching_plan_skeleton_v3(skeleton, sections=sections)

    assert not report["passed"]
    assert "teaching_skeleton:future_prerequisite" in {
        issue["code"] for issue in report["blocking_issues"]
    }


def test_batch_requires_a_credible_misconception_for_each_owned_knowledge():
    sections = [_section(1)]
    skeleton = normalize_teaching_plan_skeleton_v3({
        "knowledge_registry": [{
            "knowledge_key": "K1",
            "name": "核心知识",
            "statement": "需要展开的核心知识",
            "owner_node_id": "L2-1-1",
            "reused_in_node_ids": [],
            "prerequisite_keys": [],
            "module_ids": ["core_explanation"],
        }],
        "sections": [{
            "node_id": "L2-1-1",
            "owned_knowledge_keys": ["K1"],
            "reused_knowledge_keys": [],
        }],
    }, outline_revision_id="outline-1")
    batch = normalize_teaching_plan_batch_v3({
        "sections": [{
            "node_id": "L2-1-1",
            "knowledge_details": [{
                "knowledge_key": "K1",
                "capability_points": [{"observable_behavior": "能解释核心知识"}],
                "misconceptions": [],
                "mastery_criteria": [{
                    "observable_performance": "独立完成解释",
                    "verification_method": "按量规检查",
                }],
            }],
            "knowledge_relations": [],
            "teaching_modules": [],
        }],
    }, batch_id="TP-B01", skeleton_revision_id=skeleton["revision_id"])

    report = validate_teaching_plan_batch_v3(
        batch,
        batch_spec={"batch_id": "TP-B01", "section_ids": ["L2-1-1"]},
        skeleton=skeleton,
        sections=sections,
    )

    assert not report["passed"]
    assert "teaching_batch:missing_misconception" in {
        issue["code"] for issue in report["blocking_issues"]
    }
