from course_design_contract import (
    COURSE_DESIGN_CONTRACT_VERSION,
    compile_course_design_contract,
    format_course_design_stage_brief,
    project_course_design_contract,
)
from course_pedagogy import (
    compile_subject_generation_template,
    resolve_pedagogy_profile,
)
from course_prompt_composer import CoursePromptComposer
from assessment_orchestrator import _generation_context


def _contract(course_type: str = "systematic") -> dict:
    profile = resolve_pedagogy_profile(subject="微积分")
    type_contract = {
        "systematic": {
            "organizing_question": "如何系统掌握微积分？",
            "planning_sequence": ["先修", "概念", "应用"],
            "outline_requirements": ["按先修关系推进"],
            "completion_evidence": "能够解释、计算并迁移",
        },
        "project": {
            "organizing_question": "如何完成一个数值建模项目？",
            "planning_sequence": ["交付物", "里程碑", "验证"],
            "outline_requirements": ["围绕项目里程碑组织"],
            "completion_evidence": "交付可运行的建模成果",
        },
    }[course_type]
    brief = {
        "course_type": course_type,
        "course_type_label": "系统学习" if course_type == "systematic" else "项目实战",
        "audience": "大学一年级",
        "course_type_contract": type_contract,
        "course_intent": {
            "type": course_type,
            "expected_deliverable": "一份可复核的微积分建模报告",
        },
        "learner_starting_profile": {"status": "insufficient"},
        "course_shape_constraints": {"chapter_count": 4, "section_count": 12},
        "hard_constraints": ["必须覆盖极限、导数和积分"],
        "expected_deliverables": ["一份可复核的微积分建模报告"],
    }
    return compile_course_design_contract(
        brief=brief,
        subject_template=compile_subject_generation_template(profile),
        difficulty_profile={"level": "intermediate"},
        gap_assessment={"status": "gap_detected"},
        adaptation_decision={"strategy": "preserve_target_extend"},
        grounding_strategy="material_first",
    )


def test_design_contract_is_stable_and_freezes_product_circuit():
    first = _contract()
    second = _contract()

    assert first == second
    assert first["schema_version"] == COURSE_DESIGN_CONTRACT_VERSION
    assert first["revision_id"].startswith("design_")
    assert first["product_circuit"]["user_confirmation_gates"] == [
        "outline",
        "release",
    ]
    assert first["product_circuit"]["sequence"].index(
        "knowledge_freeze"
    ) < first["product_circuit"]["sequence"].index("teaching")


def test_stage_projection_keeps_shared_identity_without_leaking_other_jobs():
    contract = _contract()
    teaching = project_course_design_contract(contract, "teaching")
    content = project_course_design_contract(contract, "content")

    assert teaching["revision_id"] == content["revision_id"]
    assert teaching["stage"] == "teaching"
    assert "subject_lesson_plan_contract" in teaching["stage_contract"]
    assert "subject_content_contract" not in teaching["stage_contract"]
    assert "subject_content_contract" in content["stage_contract"]
    assert "subject_assessment_contract" not in content["stage_contract"]


def test_every_stage_declares_decision_sequence_and_silent_preflight():
    contract = _contract()

    for stage in (
        "outline",
        "outline_expansion",
        "knowledge_identity",
        "knowledge_enrichment",
        "teaching",
        "content",
        "assessment",
    ):
        projection = project_course_design_contract(contract, stage)
        stage_contract = projection["stage_contract"]
        rendered = format_course_design_stage_brief(projection)

        assert len(stage_contract["decision_sequence"]) >= 3
        assert len(stage_contract["silent_checks"]) >= 3
        assert "执行优先级" in rendered
        assert "输入隔离" in rendered
        assert "决策顺序" in rendered
        assert "提交前静默核验" in rendered


def test_outline_batch_receives_course_type_and_subject_contract_after_split():
    contract = _contract("project")
    prompt = CoursePromptComposer().build_outline_batch_v2_prompt(
        course_title="微积分项目实战",
        positioning="用微积分完成数值建模",
        learning_objectives=["完成并解释建模报告"],
        chapter={
            "chapter_number": 1,
            "title": "变化率建模",
            "learning_focus": "形成可验证的变化率模型",
        },
        neighbor_chapters=[],
        batch_spec={
            "start_section_index": 1,
            "end_section_index": 2,
            "expected_node_ids": ["L2-1-1", "L2-1-2"],
        },
        previous_sections=[],
        evidence_hints=[],
        skeleton_revision_id="outline-skeleton-1",
        design_contract=contract,
    )

    assert "统一课程设计契约（小节目录投影）" in prompt
    assert "围绕项目里程碑组织" in prompt
    assert "从直觉与多重表征进入正式定义" in prompt
    assert contract["revision_id"] in prompt


def test_compact_prompt_preserves_non_compressible_stage_quality_kernel():
    contract = _contract("project")
    composer = CoursePromptComposer()
    prompt = composer.build_outline_skeleton_v2_prompt(
        subject="微积分项目实战",
        audience="大学一年级",
        brief=contract["shared"],
        profile=resolve_pedagogy_profile(subject="微积分"),
        difficulty_profile={"level": "intermediate"},
        gap_assessment={},
        adaptation_decision={},
        material_context="",
        design_contract=contract,
        detail_level="minimal",
    )

    assert "唯一允许输出" in prompt
    assert "禁止修改" in prompt
    assert "执行优先级" in prompt
    assert "输入隔离" in prompt
    assert "决策顺序" in prompt
    assert "提交前静默核验" in prompt
    assert "直觉不能替代定义" in prompt
    assert "章节能推进到最终成果" in prompt
    assert contract["revision_id"] in prompt


def test_content_prompt_consumes_only_content_projection():
    contract = _contract()
    course = {
        "course_name": "微积分",
        "target_audience": "大学一年级",
        "course_design_contract": contract,
        "difficulty_profile": {"level": "intermediate"},
        "course_composition_profile": {},
        "nodes": [],
    }
    node = {
        "node_id": "L2-1-1",
        "node_name": "极限的直觉与定义",
        "node_level": 2,
        "learning_objective": "能用定义判断一个简单极限",
        "module_plan": [{
            "module_id": "core_explanation",
            "label": "核心讲解",
            "required": True,
            "output_contract": "解释定义与成立条件",
            "prompt_instruction": "先给直觉，再给正式定义",
        }],
        "grounding_contract": {},
    }
    course["nodes"] = [node]

    _, prompt = CoursePromptComposer().build_content_prompt(
        course_data=course,
        node=node,
        context="无额外资料",
    )

    assert "统一课程设计契约（正文投影" in prompt
    assert contract["revision_id"] in prompt
    assert "subject_content_contract_v2" in prompt
    assert "subject_assessment_contract_v2" not in prompt


def test_assessment_context_consumes_only_assessment_projection():
    contract = _contract()
    assessment = project_course_design_contract(contract, "assessment")
    context = _generation_context(
        profile={
            "profile_revision_id": "assessment-profile-1",
            "course_design_contract": assessment,
        },
        objective={"objective_id": "obj-1", "objective": "判断极限"},
        slot={"slot_id": "slot-1", "input_mode": "rich_text"},
        references=[],
        practice_level="mastery_check",
        variant_index=2,
    )

    projected = context["profile"]["course_design_contract"]
    assert projected["revision_id"] == contract["revision_id"]
    assert "subject_assessment_contract" in projected["stage_contract"]
    assert "subject_content_contract" not in projected["stage_contract"]
