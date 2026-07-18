from copy import deepcopy

from content_blocks import set_node_content_blocks
from course_composition import (
    attach_composition_to_plan,
    compile_composition_profile,
    normalize_composition_style,
    project_block_difficulty,
)
from course_difficulty import (
    assess_readiness,
    attach_difficulty_contracts_to_plan,
    compile_difficulty_profile,
    decide_adaptation,
)
from course_document import document_from_generation_draft
from course_pedagogy import attach_module_plans_to_plan, resolve_pedagogy_profile
from models import CourseGenerationRequest


def _plan(section_count: int = 4) -> tuple[dict, object]:
    profile = resolve_pedagogy_profile(
        subject="线性代数",
        requested_mode="math_formal",
    )
    plan = {
        "course_title": "线性代数",
        "chapters": [{
            "chapter_number": 1,
            "title": "向量与变换",
            "sections": [
                {
                    "section_number": f"1.{index}",
                    "node_id": f"L2-1-{index}",
                    "title": f"课程小节 {index}",
                    "learning_objective": "能够解释并应用当前概念",
                    "key_points": [f"知识点 {index}"],
                    "assessment": ["完成可检查任务"],
                    "prerequisite_node_ids": [],
                }
                for index in range(1, section_count + 1)
            ],
        }],
    }
    attach_module_plans_to_plan(plan, profile)
    difficulty = compile_difficulty_profile(
        "intermediate",
        primary_mode=profile.primary_mode,
    )
    attach_difficulty_contracts_to_plan(
        plan,
        profile=difficulty,
        adaptation=decide_adaptation(assess_readiness(difficulty)),
    )
    return plan, profile


def test_request_defaults_to_balanced_composition_and_keeps_legacy_optional():
    request = CourseGenerationRequest(subject="线性代数")
    legacy = CourseGenerationRequest(subject="线性代数", style="academic")

    assert request.composition_style.value == "balanced"
    assert request.style is None
    assert legacy.composition_style is None
    assert legacy.style.value == "academic"


def test_legacy_styles_map_deterministically_to_composition_profiles():
    assert normalize_composition_style(legacy_style="academic")[0].value == "theory_driven"
    assert normalize_composition_style(legacy_style="industrial")[0].value == "example_driven"
    assert normalize_composition_style(legacy_style="socratic")[0].value == "inquiry_driven"
    assert normalize_composition_style(legacy_style="humorous")[0].value == "balanced"
    assert compile_composition_profile()["resolved_from"] == "default"


def test_composition_preserves_subject_required_modules_and_changes_distribution():
    balanced, _profile = _plan()
    example = deepcopy(balanced)
    theory = deepcopy(balanced)

    balanced_result = attach_composition_to_plan(balanced, "balanced")
    example_result = attach_composition_to_plan(example, "example_driven")
    theory_result = attach_composition_to_plan(theory, "theory_driven")

    for section in example["chapters"][0]["sections"]:
        module_ids = {item["module_id"] for item in section["module_plan"]}
        assert {"lesson_goal", "core_explanation", "math_formalization"} <= module_ids
        assert "composition_case_extension" in module_ids
        assert all(item.get("module_instance_id") for item in section["module_plan"])

    balanced_distribution = balanced_result["course_block_distribution"]
    example_distribution = example_result["course_block_distribution"]
    theory_distribution = theory_result["course_block_distribution"]
    assert example_distribution["role_counts"]["example"] > balanced_distribution["role_counts"]["example"]
    assert example_distribution["role_counts"]["application"] > balanced_distribution["role_counts"].get("application", 0)
    assert theory_distribution["role_counts"]["reasoning"] > balanced_distribution["role_counts"].get("reasoning", 0)
    assert theory_distribution["role_counts"]["counterexample"] > balanced_distribution["role_counts"].get("counterexample", 0)


def test_project_style_progresses_from_scenario_to_project_task():
    plan, _profile = _plan(6)
    attach_composition_to_plan(plan, "project_driven")
    sections = plan["chapters"][0]["sections"]

    first_added = [
        item["module_id"]
        for item in sections[0]["module_plan"]
        if item["composition_source"] == "composition_style"
    ]
    final_added = [
        item["module_id"]
        for item in sections[-1]["module_plan"]
        if item["composition_source"] == "composition_style"
    ]
    assert first_added == ["composition_real_application"]
    assert final_added == ["composition_project_task"]


def test_block_difficulty_projects_role_specific_support_and_autonomy():
    node_contract = {
        "target_level": "advanced",
        "node_role": "transfer",
        "challenge": {"reasoning_depth": 4, "task_complexity": 4, "transfer_distance": 4},
        "support": {"scaffold_intensity": 2},
        "exercise_contract": {
            "autonomy": 4,
            "transfer_distance": 4,
            "feedback_timing": "after_attempt",
        },
    }

    concept = project_block_difficulty(node_contract, "concept")
    activity = project_block_difficulty(node_contract, "activity")
    transfer = project_block_difficulty(node_contract, "transfer")

    assert concept["scaffold_level"] > activity["scaffold_level"]
    assert activity["autonomy_level"] > concept["autonomy_level"]
    assert transfer["transfer_level"] >= activity["transfer_level"]
    assert concept["target_level"] == "advanced"


def test_final_course_block_keeps_composition_and_difficulty_trace():
    plan, _profile = _plan(1)
    attach_composition_to_plan(plan, "example_driven")
    section = plan["chapters"][0]["sections"][0]
    node = {
        "node_id": "L2-1-1",
        "parent_node_id": "L1-1",
        "node_name": "1.1 课程小节",
        "node_level": 2,
        "learning_objective": section["learning_objective"],
        "module_plan": section["module_plan"],
        "node_content": "",
        "content_blocks": [],
    }
    set_node_content_blocks(
        node,
        "## 补充案例\n\n用一个完整案例完成当前知识点的判断与检查。",
    )
    document = document_from_generation_draft({
        "course_id": "course-composition",
        "course_name": "课程编排测试",
        "nodes": [
            {
                "node_id": "L1-1",
                "parent_node_id": "root",
                "node_name": "第一章",
                "node_level": 1,
            },
            node,
        ],
    })

    block = next(item for item in document.blocks if item.section_id == "L2-1-1")
    assert block.role == "example"
    assert block.payload["module_id"] == "composition_case_extension"
    assert block.payload["composition_source"] == "composition_style"
    assert block.payload["composition_style"] == "example_driven"
    assert block.payload["module_instance_id"]
    assert block.payload["block_difficulty_contract"]["target_level"] == "intermediate"
