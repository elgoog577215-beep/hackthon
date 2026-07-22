from content_blocks import set_node_content_blocks
from learning_asset_storage import LearningAssetRepository
from learning_assets import (
    compile_learning_asset_plan,
    compile_learning_assets,
    evaluate_learning_asset_quality,
)


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
            "node_content": (
                "## print 的输出副作用\n\n调用 print 会把格式化后的文本写入标准输出。\n\n"
                "## 标准输出流\n\n标准输出流是程序向运行环境发送普通文本结果的默认通道。"
            ),
            "learning_objective": "能够运行并解释 print 程序",
            "knowledge_structure": [{
                "concept_group": "程序输出行为",
                "description": "区分函数调用、输出副作用与标准输出通道",
                "knowledge_points": [{
                    "name": "print 的输出副作用",
                    "statement": "调用 print 会把格式化后的内容写入标准输出，而不是把该内容作为函数返回值。",
                    "knowledge_type": "principle",
                    "conditions": ["程序运行环境提供标准输出通道"],
                    "boundaries": ["输出副作用不等同于函数返回值"],
                    "capability_points": [{
                        "name": "解释 print 调用结果",
                        "observable_behavior": "运行 print 程序并区分屏幕输出与返回值",
                    }],
                    "misconceptions": [{
                        "name": "把 print 输出当成返回值",
                        "observable_error_pattern": "把屏幕上出现的文本写成 print 调用的返回值",
                        "discrimination": "分别观察标准输出与表达式求值结果",
                        "repair_strategy": "同时记录 print 的屏幕输出和返回值后进行对照",
                    }],
                    "mastery_criteria": [{
                        "name": "print 行为辨析达标",
                        "observable_performance": "独立运行示例并准确解释输出副作用与返回值的差别",
                        "verification_method": "运行包含赋值和 print 的对照程序并解释结果",
                    }],
                    "entry_reason": "这是理解程序输出的课程入口。",
                    "relations": [{
                        "target_name": "标准输出流",
                        "relation_type": "applies_to",
                        "reason": "print 的输出副作用具体作用于标准输出流",
                    }],
                }, {
                    "name": "标准输出流",
                    "statement": "标准输出流是程序向运行环境发送普通结果文本的默认输出通道。",
                    "knowledge_type": "definition",
                    "conditions": ["运行环境没有重定向标准输出"],
                    "boundaries": ["标准错误流不是标准输出流"],
                    "capability_points": [{
                        "name": "识别标准输出",
                        "observable_behavior": "给定程序运行记录，准确标出写入标准输出的内容",
                    }],
                    "mastery_criteria": [{
                        "name": "标准输出识别达标",
                        "observable_performance": "在包含返回值与错误输出的案例中独立识别标准输出",
                        "verification_method": "对三个混合输出案例分类并说明依据",
                    }],
                }],
            }],
            "key_points": ["print 的输出副作用", "标准输出流"],
            "assessment": ["提交可运行程序并说明输出"],
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

    assert question["question_type"] == "state_trace_transfer"
    assert question["input_contract"]["mode"] == "structured_fields"
    assert question["revision_id"].startswith("qr_")
    assert question["assessment_intent_revision_id"].startswith("air_")
    assert question["assessment_intent"]["target_knowledge"]
    assert question["assessment_intent"]["target_skills"]
    assert question["assessment_intent"]["observable_actions"]
    assert question["assessment_intent"]["answer_invariants"]
    assert criterion["assessment_bindings"] == [question["revision_id"]]
    assert misconception["assessment_bindings"] == [question["revision_id"]]
    assert len(bundle["quality_report"]["gates"]) == 5
    assert bundle["quality_report"]["passed"] is True

    course_map = bundle["assets"]["course_knowledge_map"][0]
    assert course_map["schema_version"] == "course_knowledge_map_v2"
    assert course_map["status"] == "active"
    assert course_map["coverage"]["unmapped_count"] == 0
    assert course_map["coverage"]["mapped_count"] == course_map["coverage"]["mapping_count"]
    assert question["concept_ids"] == question["course_knowledge_refs"]
    assert question["concept_ids"]
    assert criterion["concept_ids"] == question["concept_ids"]
    assert misconception["concept_ids"]
    assert set(misconception["concept_ids"]).issubset(question["concept_ids"])
    block_refs = course["nodes"][0]["content_blocks"][0]["metadata"]["concept_refs"]
    assert block_refs
    assert set(block_refs).issubset(question["concept_ids"])
    knowledge_view = bundle["assets"]["knowledge_library"][0]
    assert knowledge_view["library_id"].startswith("ckb_")
    assert knowledge_view["course_knowledge_base_revision_id"].startswith("ckbr_")
    assert knowledge_view["nodes"]
    assert knowledge_view["schema_version"] == "knowledge_library_view_v3"
    assert all(
        node["source_status"] in {"course_path", "course_source"}
        for node in knowledge_view["nodes"]
    )
    assert all(
        node["identity_scope"] == "course_local"
        for node in knowledge_view["nodes"]
        if node["node_type"] == "knowledge_point"
    )
    progression = bundle["assets"]["chapter_progression_contracts"][0]
    assert progression["chapter_id"] == "L2-1-1"
    assert progression["required_objective_ids"] == [criterion["objective_id"]]
    assert progression["revision_id"].startswith("cpcr_")


def test_legacy_subject_binding_cannot_replace_course_local_view():
    course = _course()
    course["knowledge_library_binding"] = {
        "library_id": "math.linear_algebra.v1",
        "revision_id": "legacy-shared-revision",
        "binding_status": "pinned",
    }

    bundle = compile_learning_assets(course)

    assert bundle["assets"]["course_knowledge_base"][0]["schema_version"] == "course_knowledge_base_v2"
    assert bundle["assets"]["knowledge_library"][0]["library_id"].startswith("ckb_")
    assert bundle["assets"]["knowledge_library"][0]["identity_scope"] == "course_local"
    assert bundle["assets"]["course_knowledge_map"][0]["knowledge_library_id"].startswith("ckb_")


def test_legacy_linear_algebra_outline_is_degraded_without_borrowing_subject_identity():
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

    assert bundle["quality_report"]["passed"] is False
    assert course_map["coverage"]["status"] == "partial"
    assert knowledge_view["identity_scope"] == "course_local"
    assert knowledge_view["lifecycle_status"] == "degraded"
    assert not any(
        str(item).startswith("math.")
        for item in question["concept_ids"]
    )
    assert question["skill_unit_ids"] == []
    assert question["mistake_point_ids"] == []
    assert knowledge_view["skill_units"] == []
    assert knowledge_view["mistake_points"] == []
    assert knowledge_view["improvement_points"] == []
    assert knowledge_view["nodes"] == []
    assert knowledge_view["quality_report"]["issue_count"] > 0
    assert knowledge_view["quality_report"]["blocking_issue_count"] > 0
    assert knowledge_view["quality_report"]["issues"] == []
    assert knowledge_view["quality_report"]["blocking_issues"] == []


def test_quality_gate_rejects_missing_required_questions():
    course = _course()
    bundle = compile_learning_assets(course)
    bundle["assets"]["questions"] = []
    report = evaluate_learning_asset_quality(course, bundle["plan"], bundle["assets"])
    assert report["passed"] is False
    assert any(item["asset_type"] == "questions" for item in report["blocking_issues"])


def test_unpublished_enhancement_candidates_do_not_block_core_course_release():
    course = _course()
    bundle = compile_learning_assets(course)
    diagnostic = bundle["assets"]["diagnostic_templates"][0]
    diagnostic["quality_status"] = "failed"
    final = bundle["assets"]["final_assessment"][0]
    final["quality_report"] = {"passed": False, "status": "failed"}
    final["review_status"] = "needs_review"

    report = evaluate_learning_asset_quality(
        course,
        bundle["plan"],
        bundle["assets"],
    )

    assert not any(
        item["asset_type"] in {"diagnostic_remediation", "final_assessment"}
        for item in report["blocking_issues"]
    )
    assert any(
        item["asset_type"] == "diagnostic_remediation"
        for item in report["warnings"]
    )
    assert any(
        "候选稿" in item["message"]
        for item in report["warnings"]
    )


def test_question_analysis_is_compiled_without_ai_and_missing_contract_is_blocked():
    course = _course()
    bundle = compile_learning_assets(course)
    course["question_analysis_required"] = True

    questions = [
        item
        for items in bundle["assets"].values()
        for item in items
        if isinstance(item, dict) and item.get("question_analysis")
    ]
    assert questions
    assert all(
        item["question_analysis"]["analysis_source"]
        == "compiled_contract"
        for item in questions
    )
    questions[0].pop("question_analysis")
    report = evaluate_learning_asset_quality(
        course,
        bundle["plan"],
        bundle["assets"],
    )

    assert report["passed"] is False
    assert any(
        "题目合同" in item["message"]
        for item in report["blocking_issues"]
    )


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
    finals = assets["final_assessment"]
    final = finals[0]
    assert [item["practice_level"] for item in questions] == ["concept_check", "objective_practice", "mastery_check"]
    assert [item["question_type"] for item in questions] == [
        "output_prediction",
        "debugging_trace",
        "state_trace_transfer",
    ]
    assert [item["input_contract"]["mode"] for item in questions] == [
        "choice",
        "structured_fields",
        "structured_fields",
    ]
    assert [option["id"] for option in questions[0]["options"]] == [
        "A",
        "B",
        "C",
        "D",
    ]
    assert len({
        option["text"]
        for option in questions[0]["options"]
    }) == 4
    assert all(not item["options"] for item in questions[1:])
    assert all([hint["level"] for hint in item["hint_contract"]["levels"]] == [1, 2, 3] for item in questions)
    assert questions[0]["grading_policy"]["method"] == "deterministic"
    assert all(
        item["grading_policy"]["method"]
        == "rubric_ai_with_reference"
        for item in questions[1:]
    )
    assert "print" in questions[0]["answer_spec"]["criteria"][0]
    assert questions[0]["answer_spec"]["criteria"] != questions[2]["answer_spec"]["criteria"]
    assert all(marker in " ".join(questions[1]["answer_spec"]["criteria"]) for marker in ("依据", "过程", "检查"))
    assert final["practice_level"] == "final_assessment"
    assert 3 <= len(finals) <= 8
    assert all(item["review_status"] == "needs_review" for item in finals)
    assert all(item["quality_report"]["passed"] is True for item in finals)
    assert all(item["deliverable"] and item["input_materials"] and item["constraints"] for item in finals)
    assert any(item["assessment_role"] == "cross_chapter_transfer" for item in finals)
    assert len(assets["diagnostic_templates"]) == 1
    assert len(assets["remediation_units"]) == 1
    assert len(assets["validation_questions"]) == 2
    assert all(
        item["quality_status"] == item["quality_report"]["status"]
        for item in [*assets["diagnostic_templates"], *assets["validation_questions"]]
    )
    assert all(item["validation_policy"]["mastery_eligible"] is True for item in assets["validation_questions"])
    assert all(
        [hint["evidence_effect"] for hint in item["hint_contract"]["levels"]]
        == ["limited_mastery", "not_independent", "not_mastery"]
        for item in [*questions, *finals]
    )


def test_all_generated_learning_tasks_preserve_valid_subject_contracts():
    assets = compile_learning_assets(_course())["assets"]
    generated_tasks = [
        *assets["questions"],
        *assets["diagnostic_templates"],
        *(unit["guided_task"] for unit in assets["remediation_units"]),
        *assets["validation_questions"],
    ]

    assert {
        task["question_spec"]["schema_version"]
        for task in generated_tasks
    } == {"question_spec_v1", "question_spec_v2"}
    assert all(
        task["domain_validation"]["passed"]
        for task in generated_tasks
    )
    assert all(
        (
            task["question_spec"].get("adapter_id")
            or (
                task["question_spec"].get("validation_plugin")
                or {}
            ).get("adapter_id")
            or ""
        ).startswith("programming.")
        for task in generated_tasks
    )
    assert all(task["input_materials"] and task["result_checks"] for task in generated_tasks)
    validation_stimuli = {
        task["question_spec"]["stimulus"]["rendered_text"]
        for task in assets["validation_questions"]
    }
    shown_stimuli = {
        task["question_spec"]["stimulus"]["rendered_text"]
        for task in assets["questions"]
    }
    assert len(validation_stimuli) == 2
    assert validation_stimuli.isdisjoint(shown_stimuli)


def test_missing_approved_bank_item_uses_concrete_question_contract():
    course = _course()
    empty_bank = {
        "course_id": course["course_id"],
        "items": [],
    }

    questions = compile_learning_assets(
        course,
        question_bank_bundle=empty_bank,
    )["assets"]["questions"]

    assert len(questions) == 3
    assert all(
        item["question_spec"]["schema_version"] == "question_spec_v1"
        and item["domain_validation"]["passed"]
        and item["input_materials"]
        and item["deliverable"]
        and item["constraints"]
        and item["result_checks"]
        for item in questions
    )
    mastery = next(
        item
        for item in questions
        if item["practice_level"] == "mastery_check"
    )
    assert mastery["question_spec"]["target"]["assessment_actions"]
    assert mastery["question_spec"]["task"]["deliverable"]


def test_compilation_uses_the_reviewed_question_bank_revision_as_source_of_truth():
    course = _course()
    initial = compile_learning_assets(course)
    bank = initial["question_bank_bundle"]
    practice_item = next(
        item
        for item in bank["items"]
        if item["assessment_role"] == "practice"
        and item["practice_levels"] == ["concept_check"]
    )
    reviewed_prompt = (
        "输入材料：散列表容量为 11，键序列为 18、29、40。"
        "任务：写出除留余数法得到的三个地址，并说明为何发生冲突。"
        "限制条件：逐项列出取模过程，并检查所有地址是否位于 0 至 10。"
    )
    practice_item["prompt"] = reviewed_prompt
    practice_item["formal_task"]["prompt"] = reviewed_prompt

    rebuilt = compile_learning_assets(
        course,
        question_bank_bundle=bank,
    )

    question = next(
        item
        for item in rebuilt["assets"]["questions"]
        if item["node_id"] == practice_item["node_id"]
        and item["practice_level"] == "concept_check"
    )
    assert question["prompt"] == reviewed_prompt
    assert (
        question["question_bank_item_revision_id"]
        == practice_item["revision_id"]
    )


def test_mastery_keeps_scoring_contract_internal_and_prompt_concise():
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

    assert mastery["question_spec"]["target"]["assessment_actions"] == (
        course["nodes"][0]["assessment"]
    )
    assert mastery["answer_spec"]["criteria"]
    assert "评分检查点" not in mastery["prompt"]
    assert "限制条件：" not in mastery["prompt"]


def test_quality_gate_accepts_internal_mastery_rubric_for_a_concrete_prompt():
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
    mastery["prompt"] = (
        "运行给定代码，写出两行标准输出和 print 的返回值，"
        "并说明输出副作用与返回值的区别。"
    )

    report = evaluate_learning_asset_quality(course, bundle["plan"], bundle["assets"])

    assert report["passed"] is True


def test_asset_repository_keeps_immutable_bundle_revisions(tmp_path):
    repository = LearningAssetRepository(tmp_path)
    first = repository.save_bundle("course-1", compile_learning_assets(_course()))
    changed_course = _course()
    changed_course["nodes"][0]["knowledge_structure"][0]["knowledge_points"][0]["statement"] += " 该行为可以被重定向。"
    second = repository.save_bundle("course-1", compile_learning_assets(changed_course))

    assert first["bundle_revision_id"] != second["bundle_revision_id"]
    assert repository.load_bundle("course-1", first["bundle_revision_id"])["bundle_revision_id"] == first["bundle_revision_id"]
    assert repository.load_bundle("course-1")["bundle_revision_id"] == second["bundle_revision_id"]
