import json
import math
from copy import deepcopy

from ai_base import AIBase
from course_generation_adaptive import merge_teaching_skeleton_part
from course_planning_budget import (
    CoursePlanningBudget,
    build_compact_planning_context,
    build_teaching_plan_batches,
    select_batch_knowledge_registry,
)
from course_prompt_composer import CoursePromptComposer
from course_service import CourseService
from course_teaching_plan_v3 import (
    compile_course_knowledge_graph_draft,
    compile_frozen_course_knowledge_graph,
    merge_knowledge_and_teaching_batches,
    normalize_course_knowledge_batch_v1,
    normalize_teaching_execution_batch_v1,
    normalize_teaching_plan_batch_v3,
    normalize_teaching_plan_skeleton_v3,
    promote_course_teaching_plan_v3,
    restore_teaching_plan_skeleton_from_graph_draft,
    validate_course_knowledge_batch_v1,
    validate_teaching_execution_batch_v1,
    validate_teaching_plan_batch_v3,
    validate_teaching_plan_skeleton_v3,
)


def _knowledge_detail(key, name):
    return {
        "knowledge_key": key,
        "concept_group": "核心机制",
        "group_description": "用于验证知识冻结",
        "knowledge_type": "concept",
        "conditions": [f"已识别{name}的对象"],
        "boundaries": [f"条件不成立时不能使用{name}"],
        "capability_points": [{
            "observable_behavior": f"能独立说明{name}的条件",
        }],
        "misconceptions": [{
            "observable_error_pattern": f"未检查条件就使用{name}",
            "discrimination": "核对对象、条件与结论",
            "repair_strategy": "补写条件清单后重做",
        }],
        "mastery_criteria": [{
            "observable_performance": f"无提示完成{name}的变式任务",
            "verification_method": "用正例、反例和边界例验证",
        }],
        "source_refs": [],
        "confidence": "medium",
    }


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


def test_default_planning_has_no_whole_course_wall_clock_deadline():
    budget = CoursePlanningBudget()
    section_count = 24
    skeleton_waves = math.ceil(
        section_count / budget.skeleton_max_sections
    )
    detail_batches = math.ceil(
        section_count / budget.batch_max_sections
    )
    detail_waves = math.ceil(detail_batches / budget.concurrency)

    assert skeleton_waves > 0
    assert detail_waves > 0
    assert budget.batch_timeout_seconds == 90
    assert budget.total_timeout_seconds == 0


def test_knowledge_freezes_before_teaching_and_merges_without_identity_drift():
    sections = [_section(1)]
    skeleton = normalize_teaching_plan_skeleton_v3({
        "knowledge_registry": [
            {
                "knowledge_key": "K001",
                "name": "基础对象",
                "statement": "先识别任务中的基础对象。",
                "owner_node_id": "L2-1-1",
                "prerequisite_keys": [],
                "module_ids": ["core_explanation"],
            },
            {
                "knowledge_key": "K002",
                "name": "条件判断",
                "statement": "基于对象判断方法的成立条件。",
                "owner_node_id": "L2-1-1",
                "prerequisite_keys": ["K001"],
                "module_ids": ["core_explanation"],
            },
        ],
        "sections": [{
            "node_id": "L2-1-1",
            "owned_knowledge_keys": ["K001", "K002"],
            "reused_knowledge_keys": [],
        }],
    }, outline_revision_id="outline-1")
    spec = {"batch_id": "TP-B01", "section_ids": ["L2-1-1"]}
    knowledge = normalize_course_knowledge_batch_v1({
        "sections": [{
            "node_id": "L2-1-1",
            "knowledge_details": [
                _knowledge_detail("K001", "基础对象"),
                _knowledge_detail("K002", "条件判断"),
            ],
            "knowledge_relations": [{
                "source_key": "K001",
                "target_key": "K002",
                "relation_type": "prerequisite",
                "reason": "必须先识别对象，才能核对方法条件。",
            }],
        }],
    }, batch_id="TP-B01", skeleton_revision_id=skeleton["revision_id"])
    assert validate_course_knowledge_batch_v1(
        knowledge,
        batch_spec=spec,
        skeleton=skeleton,
        sections=sections,
    )["passed"] is True

    graph = compile_frozen_course_knowledge_graph(
        skeleton=skeleton,
        knowledge_batches=[knowledge],
    )
    assert graph["status"] == "knowledge_frozen"
    assert graph["source_skeleton_revision_id"] == skeleton["revision_id"]

    teaching = normalize_teaching_execution_batch_v1({
        "sections": [{
            "node_id": "L2-1-1",
            "teaching_modules": [{
                "module_id": "core_explanation",
                "teaching_purpose": "建立对象与条件之间的判断链",
                "knowledge_keys": ["K001", "K002"],
                "teaching_guidance": "先识别对象，再用反例检查条件。",
                "teacher_activity": "呈现正反两例并追问判断依据。",
                "student_activity": "标注对象、条件并完成判断。",
            }],
            "key_difficulties": ["区分对象和成立条件"],
            "teacher_activities": ["组织反例辨析"],
            "student_activities": ["完成条件分类"],
            "in_class_checks": ["独立完成一个边界例判断"],
            "homework": ["设计一个反例并解释失效条件"],
        }],
    }, batch_id="TP-B01", skeleton_revision_id=skeleton["revision_id"],
        knowledge_revision_id=graph["revision_id"])
    assert validate_teaching_execution_batch_v1(
        teaching,
        batch_spec=spec,
        skeleton=skeleton,
        sections=sections,
        knowledge_revision_id=graph["revision_id"],
    )["passed"] is True
    merged = merge_knowledge_and_teaching_batches(
        knowledge_batches=[knowledge],
        teaching_batches=[teaching],
        skeleton_revision_id=skeleton["revision_id"],
    )
    assert merged[0]["sections"][0]["knowledge_details"]
    assert merged[0]["sections"][0]["teaching_modules"]


def test_stage_prompts_have_one_professional_responsibility_each():
    composer = CoursePromptComposer()
    spec = {"batch_id": "TP-B01", "section_ids": ["L2-1-1"]}
    sections = build_compact_planning_context(
        [_section(1)],
        composition_style="balanced",
    )["sections"]
    registry = [{
        "knowledge_key": "K001",
        "name": "基础对象",
        "statement": "识别基础对象。",
        "owner_node_id": "L2-1-1",
        "prerequisite_keys": [],
        "module_ids": ["core_explanation"],
    }]
    identities = [{
        "node_id": "L2-1-1",
        "owned_knowledge_keys": ["K001"],
        "reused_knowledge_keys": [],
    }]
    knowledge_prompt = composer.build_course_knowledge_batch_v1_prompt(
        course_title="职责隔离课程",
        positioning="验证链路",
        batch_spec=spec,
        batch_sections=sections,
        knowledge_registry=registry,
        section_identities=identities,
        skeleton_revision_id="skeleton-1",
    )
    teaching_prompt = composer.build_teaching_execution_batch_v1_prompt(
        course_title="职责隔离课程",
        positioning="验证链路",
        batch_spec=spec,
        batch_sections=sections,
        frozen_knowledge=[{
            **registry[0],
            **_knowledge_detail("K001", "基础对象"),
        }],
        section_identities=identities,
        module_catalog=[{"module_id": "core_explanation"}],
        knowledge_revision_id="knowledge-1",
    )
    assert "本阶段禁止返回 `teaching_modules`" in knowledge_prompt
    assert "本阶段禁止返回 `knowledge_details`" in teaching_prompt
    assert "冻结知识修订：knowledge-1" in teaching_prompt


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


def test_skeleton_shards_rekey_and_reconcile_cross_shard_reuse():
    prior = {
        "knowledge_registry": [{
            "knowledge_key": "K001",
            "name": "基础条件",
            "statement": "基础条件先于后续应用",
            "owner_node_id": "L2-1-1",
            "reused_in_node_ids": [],
            "prerequisite_keys": [],
            "module_ids": ["core_explanation"],
        }],
        "sections": [{
            "node_id": "L2-1-1",
            "owned_knowledge_keys": ["K001"],
            "reused_knowledge_keys": [],
        }],
    }
    part = {
        "knowledge_registry": [{
            "knowledge_key": "K001",
            "name": "后续应用",
            "statement": "后续应用建立在基础条件上",
            "owner_node_id": "L2-1-2",
            "reused_in_node_ids": [],
            "prerequisite_keys": ["K001"],
            "module_ids": ["core_explanation"],
        }],
        "sections": [{
            "node_id": "L2-1-2",
            "owned_knowledge_keys": ["K001"],
            "reused_knowledge_keys": ["K001"],
        }],
    }

    merged = merge_teaching_skeleton_part(
        prior,
        part,
        outline_revision_id="outline-1",
    )

    assert [
        item["knowledge_key"] for item in merged["knowledge_registry"]
    ] == ["K001", "K002"]
    assert merged["sections"][1]["owned_knowledge_keys"] == ["K002"]
    assert merged["sections"][1]["reused_knowledge_keys"] == ["K001"]
    assert merged["knowledge_registry"][0]["reused_in_node_ids"] == [
        "L2-1-2"
    ]
    assert merged["knowledge_registry"][1]["prerequisite_keys"] == [
        "K001"
    ]


def test_reconciled_skeleton_projects_an_upstream_knowledge_graph_draft():
    skeleton = normalize_teaching_plan_skeleton_v3({
        "knowledge_registry": [{
            "knowledge_key": "K001",
            "name": "基础条件",
            "statement": "先判断条件是否成立",
            "owner_node_id": "L2-1-1",
            "reused_in_node_ids": ["L2-1-2"],
            "prerequisite_keys": [],
            "module_ids": ["core_explanation"],
        }, {
            "knowledge_key": "K002",
            "name": "迁移应用",
            "statement": "在新情境中应用规则",
            "owner_node_id": "L2-1-2",
            "reused_in_node_ids": [],
            "prerequisite_keys": ["K001"],
            "module_ids": ["guided_practice"],
        }],
        "sections": [{
            "node_id": "L2-1-1",
            "owned_knowledge_keys": ["K001"],
            "reused_knowledge_keys": [],
        }, {
            "node_id": "L2-1-2",
            "owned_knowledge_keys": ["K002"],
            "reused_knowledge_keys": ["K001"],
        }],
    }, outline_revision_id="outline-1")

    draft = compile_course_knowledge_graph_draft(skeleton)

    assert draft["schema_version"] == "course_knowledge_graph_draft_v1"
    assert draft["status"] == "identity_frozen"
    assert draft["topology"]["is_dag"] is True
    assert draft["topology"]["root_knowledge_keys"] == ["K001"]
    assert draft["edges"][0]["source_knowledge_key"] == "K001"
    assert draft["edges"][0]["target_knowledge_key"] == "K002"
    assert draft["edges"][0]["direction"] == "source_before_target"
    assert draft["section_bindings"][1]["reused_knowledge_keys"] == ["K001"]

    restored = restore_teaching_plan_skeleton_from_graph_draft(
        draft,
        outline_revision_id="outline-1",
    )

    assert restored == skeleton


def test_graph_draft_cannot_restore_a_tampered_skeleton_revision():
    skeleton = normalize_teaching_plan_skeleton_v3({
        "knowledge_registry": [{
            "knowledge_key": "K001",
            "name": "基础条件",
            "statement": "先判断条件是否成立",
            "owner_node_id": "L2-1-1",
            "reused_in_node_ids": [],
            "prerequisite_keys": [],
            "module_ids": ["core_explanation"],
        }],
        "sections": [{
            "node_id": "L2-1-1",
            "owned_knowledge_keys": ["K001"],
            "reused_knowledge_keys": [],
        }],
    }, outline_revision_id="outline-1")
    draft = compile_course_knowledge_graph_draft(skeleton)
    draft["source_skeleton_revision_id"] = "teaching_skeleton_tampered"

    assert restore_teaching_plan_skeleton_from_graph_draft(
        draft,
        outline_revision_id="outline-1",
    ) == {}


def test_frozen_graph_restores_module_suggestions_before_recipe_rebuild():
    plan = {
        "chapters": [{
            "sections": [{
                "node_id": "L2-1-1",
                "suggested_module_ids": ["core_explanation"],
            }],
        }],
    }
    course_data = {
        "course_knowledge_scope_contract": {
            "revision_id": "outline-1",
        },
        "course_knowledge_graph_draft": {
            "status": "identity_frozen",
            "source_outline_revision_id": "outline-1",
            "nodes": [{
                "owner_node_id": "L2-1-1",
                "module_ids": [
                    "math_intuition",
                    "core_explanation",
                ],
            }],
            "section_bindings": [{
                "node_id": "L2-1-1",
            }],
        },
    }

    restored = CourseService._apply_frozen_graph_module_suggestions(
        deepcopy(plan),
        course_data,
    )

    assert restored["chapters"][0]["sections"][0][
        "suggested_module_ids"
    ] == ["core_explanation", "math_intuition"]


def test_knowledge_graph_draft_never_labels_a_cycle_as_a_dag():
    skeleton = normalize_teaching_plan_skeleton_v3({
        "knowledge_registry": [{
            "knowledge_key": "K001", "name": "甲", "statement": "甲",
            "owner_node_id": "L2-1-1", "prerequisite_keys": ["K002"],
        }, {
            "knowledge_key": "K002", "name": "乙", "statement": "乙",
            "owner_node_id": "L2-1-1", "prerequisite_keys": ["K001"],
        }],
        "sections": [{
            "node_id": "L2-1-1",
            "owned_knowledge_keys": ["K001", "K002"],
            "reused_knowledge_keys": [],
        }],
    }, outline_revision_id="outline-1")

    draft = compile_course_knowledge_graph_draft(skeleton)

    assert draft["topology"]["is_dag"] is False
    assert draft["status"] == "needs_review"
    assert draft["quality"]["cyclic_knowledge_keys"] == ["K001", "K002"]


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


def test_single_oversized_section_becomes_adaptive_unit_instead_of_exception():
    section = _section(1)
    section["title"] = "超长标题" * 3_000
    skeleton = {
        "sections": [{
            "node_id": section["node_id"],
            "owned_knowledge_keys": [f"K{index:02d}" for index in range(20)],
            "reused_knowledge_keys": [],
        }],
    }

    batches = build_teaching_plan_batches(
        [section],
        skeleton,
        CoursePlanningBudget(),
    )

    assert len(batches) == 1
    assert batches[0]["section_ids"] == ["L2-1-1"]
    assert batches[0]["requires_adaptive_compaction"] is True


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
    overall_guidance = {
        "positioning": "让知识理解、方法应用与迁移任务形成连续进阶",
        "target_audience": "具备必要前置基础的学习者",
        "learning_objectives": [
            "解释核心概念及成立条件",
            "独立应用关键方法",
            "在变式任务中完成迁移",
        ],
        "prerequisites": ["课程规定的前置知识"],
        "teaching_throughline": "从概念建构进入示例分析，再用独立任务验证迁移",
        "assessment_methods": ["解释题", "变式任务", "综合应用"],
    }
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
            overall_guidance=overall_guidance,
        )
        user_prompt = f"生成详细小节教案批次 {spec['batch_id']}，只输出 JSON。"
        prompt_chars += len(user_prompt) + len(system_prompt)
        prompt_tokens.append(
            AIBase.estimate_request_tokens(user_prompt, system_prompt)
        )

    assert len(batches) == 21
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
