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
from course_pedagogy import MODULES, attach_module_plans_to_plan, resolve_pedagogy_profile
from course_prompt_composer import CoursePromptComposer
from models import CourseGenerationRequest


def _plan(
    section_count: int = 4,
    *,
    difficulty_level: str = "intermediate",
    subject: str = "线性代数",
    requested_mode: str = "math_formal",
) -> tuple[dict, object]:
    profile = resolve_pedagogy_profile(
        subject=subject,
        requested_mode=requested_mode,
    )
    plan = {
        "course_title": subject,
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
        difficulty_level,
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

    archetype_ids = set()
    for section in example["chapters"][0]["sections"]:
        module_ids = {item["module_id"] for item in section["module_plan"]}
        archetype = section["lesson_archetype"]
        archetype_ids.add(archetype["archetype_id"])
        assert {"lesson_goal", "core_explanation"} <= module_ids
        assert set(archetype["module_ids"]) <= module_ids
        assert "composition_case_extension" in module_ids
        assert all(item.get("module_instance_id") for item in section["module_plan"])
    assert len(archetype_ids) >= 3

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


def test_difficulty_level_changes_block_recipe_even_with_balanced_style():
    beginner, _profile = _plan(difficulty_level="beginner")
    intermediate, _profile = _plan(difficulty_level="intermediate")
    advanced, _profile = _plan(difficulty_level="advanced")

    beginner_result = attach_composition_to_plan(beginner, "balanced")
    intermediate_result = attach_composition_to_plan(intermediate, "balanced")
    advanced_result = attach_composition_to_plan(advanced, "balanced")

    beginner_sections = beginner["chapters"][0]["sections"]
    intermediate_sections = intermediate["chapters"][0]["sections"]
    advanced_sections = advanced["chapters"][0]["sections"]
    assert all(
        "difficulty_scaffolded_example"
        in {item["module_id"] for item in section["module_plan"]}
        for section in beginner_sections
    )
    assert "difficulty_guided_practice" in {
        item["module_id"] for item in beginner_sections[-1]["module_plan"]
    }
    assert all(
        not any(
            item["module_id"].startswith("difficulty_")
            for item in section["module_plan"]
        )
        for section in intermediate_sections
    )
    assert "math_proof" in {
        item["module_id"] for item in advanced_sections[1]["module_plan"]
    }
    assert {
        "math_proof",
        "math_modeling",
        "difficulty_transfer_challenge",
    } <= {item["module_id"] for item in advanced_sections[-1]["module_plan"]}

    beginner_distribution = beginner_result["course_block_distribution"]
    intermediate_distribution = intermediate_result["course_block_distribution"]
    advanced_distribution = advanced_result["course_block_distribution"]
    assert beginner_distribution["difficulty_added_blocks"] > 0
    assert intermediate_distribution["difficulty_added_blocks"] == 0
    assert advanced_distribution["difficulty_added_blocks"] > 0
    assert (
        advanced_distribution["role_counts"]["reasoning"]
        > intermediate_distribution["role_counts"].get("reasoning", 0)
    )


def test_advanced_recipe_uses_subject_modules_and_deduplicates_shared_selection():
    plan, _profile = _plan(
        4,
        difficulty_level="advanced",
        subject="Python 工程实践",
        requested_mode="programming_engineering",
    )
    attach_composition_to_plan(plan, "theory_driven")
    sections = plan["chapters"][0]["sections"]

    early_reasoning = [
        item
        for item in sections[0]["module_plan"]
        if item["module_id"] == "composition_deep_reasoning"
    ]
    assert len(early_reasoning) == 1
    assert {
        "composition_style",
        "difficulty_level",
    } <= set(early_reasoning[0]["selection_reasons"])
    assert "engineering_testing" in {
        item["module_id"] for item in sections[1]["module_plan"]
    }
    assert {
        "engineering_testing",
        "engineering_architecture",
        "difficulty_transfer_challenge",
    } <= {item["module_id"] for item in sections[-1]["module_plan"]}

    math_plan, _profile = _plan(2, difficulty_level="advanced")
    first_section = math_plan["chapters"][0]["sections"][0]
    first_section["module_plan"].append(
        MODULES["math_proof"].to_dict(
            source_mode="math_formal",
            required=False,
        )
    )
    attach_composition_to_plan(math_plan, "balanced")
    proof_modules = [
        item
        for item in first_section["module_plan"]
        if item["module_id"] == "math_proof"
    ]
    assert len(proof_modules) == 1
    assert proof_modules[0]["required"] is True
    assert proof_modules[0]["composition_source"] == "difficulty_level"
    assert proof_modules[0]["selection_reasons"] == [
        "subject_optional",
        "difficulty_level",
    ]


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
    assert block.payload["selection_reasons"] == ["composition_style"]
    assert block.payload["block_difficulty_contract"]["target_level"] == "intermediate"


def test_final_course_block_keeps_difficulty_recipe_selection_trace():
    plan, _profile = _plan(1, difficulty_level="advanced")
    attach_composition_to_plan(plan, "balanced")
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
    _user_prompt, system_prompt = CoursePromptComposer().build_content_prompt(
        course_data={
            "course_id": "course-difficulty-recipe",
            "course_name": "难度配方测试",
            "nodes": [node],
            "subject_pedagogy_profile": plan["subject_pedagogy_profile"],
            "difficulty_profile": {"target_level": "advanced"},
            "course_composition_profile": plan["course_composition_profile"],
        },
        node=node,
        context="无资料",
    )
    assert "必需模块 `## 证明与推导`" in system_prompt
    assert "必需模块 `## 数学建模`" in system_prompt
    assert "必需模块 `## 迁移挑战`" in system_prompt

    set_node_content_blocks(
        node,
        "## 证明与推导\n\n逐步说明结论成立所依赖的条件与推导依据。",
    )
    document = document_from_generation_draft({
        "course_id": "course-difficulty-recipe",
        "course_name": "难度配方测试",
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

    block = next(
        item
        for item in document.blocks
        if item.payload.get("module_id") == "math_proof"
    )
    assert block.role == "reasoning"
    assert block.payload["composition_source"] == "difficulty_level"
    assert block.payload["selection_reasons"] == ["difficulty_level"]
    assert block.payload["block_difficulty_contract"]["target_level"] == "advanced"
