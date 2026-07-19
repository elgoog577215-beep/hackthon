import json

from course_planning_budget import (
    CoursePlanningBudget,
    build_compact_planning_context,
    build_teaching_plan_batches,
)
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
    assert all(item["estimated_input_tokens"] <= 8000 for item in batches)
    assert all(item["estimated_output_tokens"] <= 10000 for item in batches)


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
