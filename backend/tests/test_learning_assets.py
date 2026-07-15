from learning_assets import (
    compile_learning_asset_plan,
    compile_learning_assets,
    evaluate_learning_asset_quality,
)
from content_blocks import set_node_content_blocks
from learning_asset_storage import LearningAssetRepository


def _course(mode="programming_engineering"):
    course = {
        "course_id": "course-1",
        "course_name": "Python 工程",
        "course_purpose": "systematic",
        "subject_pedagogy_profile": {
            "primary_mode": mode,
            "secondary_mode": None,
            "secondary_intensity": None,
            "confidence": "high",
            "evidence": [],
            "rationale": "test",
            "enabled_module_ids": [],
            "user_locked": True,
        },
        "nodes": [{
            "node_id": "L2-1-1",
            "node_level": 2,
            "node_name": "第一个程序",
            "node_content": "## 核心概念\n\nprint 将内容写入标准输出。",
            "learning_objective": "能够运行并解释 print 程序",
            "key_points": ["print", "标准输出"],
            "assessment": ["提交可运行程序并说明输出"],
            "misconceptions": ["把 print 当成返回值"],
            "prerequisite_node_ids": [],
            "difficulty_contract": {
                "challenge": {"reasoning_steps": 2},
                "support": {"scaffold_intensity": 3},
            },
            "grounding_contract": {},
        }],
    }
    set_node_content_blocks(course["nodes"][0], course["nodes"][0]["node_content"])
    return course


def test_plan_uses_course_purpose_and_subject_mode():
    plan = compile_learning_asset_plan(_course())
    assert plan["primary_mode"] == "programming_engineering"
    assert "questions" in plan["enabled_asset_types"]
    assert "knowledge_library" in plan["enabled_asset_types"]
    assert "subject_knowledge" not in plan["enabled_asset_types"]
    assert "teaching_standards" not in plan["enabled_asset_types"]
    assert "course_knowledge_map" in plan["enabled_asset_types"]


def test_assets_have_stable_revisions_and_five_passing_gates():
    course = _course()
    bundle = compile_learning_assets(course)
    questions = bundle["assets"]["questions"]
    question = next(item for item in questions if item["practice_level"] == "mastery_check")
    criterion = bundle["assets"]["mastery_criteria"][0]
    misconception = bundle["assets"]["misconceptions"][0]

    assert question["question_type"] == "implementation_task"
    assert question["revision_id"].startswith("qr_")
    assert criterion["assessment_bindings"] == [question["revision_id"]]
    assert misconception["assessment_bindings"] == [question["revision_id"]]
    assert len(bundle["quality_report"]["gates"]) == 5
    assert bundle["quality_report"]["passed"] is True

    course_map = bundle["assets"]["course_knowledge_map"][0]
    assert course_map["schema_version"] == "course_knowledge_map_v1"
    assert course_map["status"] == "library_unavailable"
    assert question["concept_ids"] == []
    assert criterion["concept_ids"] == question["concept_ids"]
    assert misconception["concept_ids"] == question["concept_ids"]
    assert course["nodes"][0]["content_blocks"][0]["metadata"]["concept_refs"] == question["concept_ids"]
    progression = bundle["assets"]["chapter_progression_contracts"][0]
    assert progression["chapter_id"] == "L2-1-1"
    assert progression["required_objective_ids"] == [criterion["objective_id"]]
    assert progression["revision_id"].startswith("cpcr_")


def test_linear_algebra_assets_bind_one_formal_knowledge_library():
    course = _course(mode="math_formal")
    course["course_name"] = "线性代数"
    node = course["nodes"][0]
    node.update({
        "node_name": "高斯消元法",
        "node_content": "## 核心概念\n\n用高斯消元法步骤与行简化阶梯形求解线性方程组。",
        "learning_objective": "能够完成高斯消元并判断解结构",
        "key_points": ["高斯消元法步骤与行简化阶梯形"],
        "misconceptions": ["遇到零主元仍直接相除"],
        "assessment": ["完成消元并解释主元选择"],
    })
    node.pop("knowledge_structure", None)
    node["content_blocks"] = []
    set_node_content_blocks(node, node["node_content"])

    bundle = compile_learning_assets(course)
    course_map = bundle["assets"]["course_knowledge_map"][0]
    knowledge_view = bundle["assets"]["knowledge_library"][0]
    question = bundle["assets"]["questions"][0]
    misconception = bundle["assets"]["misconceptions"][0]

    assert bundle["quality_report"]["passed"] is True
    assert course_map["coverage"]["status"] == "mapped"
    assert "math.la.system.gaussian_elimination.forward" in question["concept_ids"]
    assert question["skill_unit_ids"]
    assert question["mistake_point_ids"]
    assert "improvement_point_ids" in question
    assert misconception["standard_fit"] == "hit"
    assert misconception["mistake_point_id"]
    assert knowledge_view["nodes"][0]["node_type"] == "subject"
    assert knowledge_view["skill_units"]
    assert knowledge_view["mistake_points"]
    assert knowledge_view["improvement_points"]
    assert not {"course", "chapter", "section"}.intersection(
        item["node_type"] for item in knowledge_view["nodes"]
    )


def test_quality_gate_rejects_missing_required_questions():
    course = _course()
    bundle = compile_learning_assets(course)
    bundle["assets"]["questions"] = []
    report = evaluate_learning_asset_quality(course, bundle["plan"], bundle["assets"])
    assert report["passed"] is False
    assert any(item["asset_type"] == "questions" for item in report["blocking_issues"])


def test_quality_gate_rejects_missing_persisted_content_and_progression_contract():
    course = _course()
    bundle = compile_learning_assets(course)
    course["nodes"][0]["content_blocks"] = []
    bundle["assets"]["chapter_progression_contracts"] = []

    report = evaluate_learning_asset_quality(course, bundle["plan"], bundle["assets"])

    assert report["passed"] is False
    assert any(item["asset_type"] == "content_blocks" for item in report["blocking_issues"])
    assert any(item["asset_type"] == "chapter_progression_contracts" for item in report["blocking_issues"])


def test_material_organization_explicitly_declares_reading_only():
    course = _course()
    course["course_purpose"] = "material_organization"

    bundle = compile_learning_assets(course)

    assert bundle["plan"]["reading_only_degraded"] is True
    assert bundle["assets"]["questions"] == []
    assert bundle["assets"]["chapter_progression_contracts"][0]["mastery_required"] is False


def test_questions_compile_formal_practice_contracts():
    assets = compile_learning_assets(_course())["assets"]
    questions = assets["questions"]
    final = assets["final_assessment"][0]
    assert [item["practice_level"] for item in questions] == ["concept_check", "objective_practice", "mastery_check"]
    assert questions[0]["question_type"] == "short_answer"
    assert questions[0]["input_contract"]["mode"] == "rich_text"
    assert all(item["input_contract"]["mode"] == "code_and_text" for item in questions[1:])
    assert all([hint["level"] for hint in item["hint_contract"]["levels"]] == [1, 2, 3] for item in questions)
    assert all(item["grading_policy"]["method"] == "rubric_ai" for item in questions)
    assert "print" in questions[0]["answer_spec"]["criteria"][0]
    assert questions[0]["answer_spec"]["criteria"] != questions[2]["answer_spec"]["criteria"]
    assert all(marker in " ".join(questions[1]["answer_spec"]["criteria"]) for marker in ("依据", "过程", "检查"))
    assert final["practice_level"] == "final_assessment"
    assert len(assets["diagnostic_templates"]) == 1
    assert len(assets["remediation_units"]) == 1
    assert len(assets["validation_questions"]) == 2
    assert all(item["quality_status"] == "passed" for item in assets["validation_questions"])
    assert all(item["validation_policy"]["mastery_eligible"] is True for item in assets["validation_questions"])


def test_mastery_prompt_exposes_every_scored_assessment_item():
    course = _course()
    course["nodes"][0]["assessment"] = [
        "提交可运行程序并说明输出",
        "解释标准输出与返回值的区别",
        "给出一个错误示例并修正",
    ]

    bundle = compile_learning_assets(course)
    mastery = next(
        item for item in bundle["assets"]["questions"]
        if item["practice_level"] == "mastery_check"
    )

    assert all(item in mastery["prompt"] for item in course["nodes"][0]["assessment"])


def test_quality_gate_rejects_hidden_mastery_rubric_requirements():
    course = _course()
    course["nodes"][0]["assessment"] = [
        "提交可运行程序并说明输出",
        "解释标准输出与返回值的区别",
    ]
    bundle = compile_learning_assets(course)
    mastery = next(
        item for item in bundle["assets"]["questions"]
        if item["practice_level"] == "mastery_check"
    )
    mastery["prompt"] = "请提交可运行程序并说明输出。"

    report = evaluate_learning_asset_quality(course, bundle["plan"], bundle["assets"])

    assert report["passed"] is False
    assert any(
        item["asset_type"] == "questions" and "隐藏评分要求" in item["message"]
        for item in report["blocking_issues"]
    )


def test_asset_repository_keeps_immutable_bundle_revisions(tmp_path):
    repository = LearningAssetRepository(tmp_path)
    first = repository.save_bundle("course-1", compile_learning_assets(_course()))
    changed_course = _course()
    changed_course["nodes"][0]["key_points"].append("解释器")
    second = repository.save_bundle("course-1", compile_learning_assets(changed_course))

    assert first["bundle_revision_id"] != second["bundle_revision_id"]
    assert repository.load_bundle("course-1", first["bundle_revision_id"])["bundle_revision_id"] == first["bundle_revision_id"]
    assert repository.load_bundle("course-1")["bundle_revision_id"] == second["bundle_revision_id"]
