from __future__ import annotations

import pytest

from assessment_generation_policy import resolve_assessment_generation_policy
from assessment_orchestrator import (
    AssessmentGenerationOrchestrator,
    SemanticPreflightFailure,
    _objective_for_design_brief,
    _slot_for_design_brief,
)
from assessment_semantics import (
    compile_question_design_brief,
    evaluate_question_semantic_preflight,
)
from solution_contracts import worked_solution_is_complete


def _brief(question_type: str) -> dict:
    return compile_question_design_brief(
        objective={
            "objective_id": "obj-1",
            "node_id": "node-1",
            "objective": "Apply Python object semantics",
            "knowledge": ["object identity"],
            "skills": ["trace execution"],
            "misconceptions": ["immutability means every value is copied"],
            "observable_evidence": ["correct final state"],
            "risk_level": "low",
        },
        slot={
            "slot_id": "slot-1",
            "question_type": question_type,
            "input_mode": "choice",
            "validation_mode": "state_trace_validator",
            "risk_level": "low",
            "input_contract": {
                "schema_version": "input_contract_v2",
                "mode": "choice",
            },
        },
        reference_summary={
            "content_covered": True,
            "method_covered": True,
            "content_reference_count": 1,
            "authoring_pattern_count": 1,
        },
        practice_level="concept_check",
        variant_index=0,
    )


def test_design_brief_scopes_each_practice_level_to_one_primary_target():
    objective = {
        "objective_id": "obj-scope",
        "node_id": "node-scope",
        "objective": "掌握极限、导数与积分的完整章节目标",
        "knowledge": ["极限", "导数", "定积分"],
        "skills": ["辨析极限", "计算导数", "迁移定积分"],
        "misconceptions": ["极限等于点值", "导数等于函数值", "积分恒为面积"],
        "observable_evidence": ["证据一", "证据二", "证据三"],
        "risk_level": "low",
    }
    slot = {
        "slot_id": "slot-scope",
        "question_type": "numeric_response",
        "input_mode": "numeric_unit",
        "validation_mode": "numeric_unit_validator",
        "risk_level": "low",
        "input_contract": {},
    }

    briefs = [
        compile_question_design_brief(
            objective=objective,
            slot=slot,
            practice_level=level,
            variant_index=index,
        )
        for index, level in enumerate((
            "concept_check",
            "objective_practice",
            "mastery_check",
        ))
    ]

    assert [item["primary_knowledge"] for item in briefs] == [
        "极限", "导数", "定积分",
    ]
    assert all(
        len(item["required_observable_evidence"]) == 1
        and item["assessment_scope_contract"]["one_primary_target"] is True
        for item in briefs
    )
    assert [
        item["assessment_scope_contract"]["learner_action_limit"]
        for item in briefs
    ] == [1, 2, 3]


def test_design_brief_scope_is_the_public_and_review_objective():
    objective = {
        "objective_id": "obj-calculus",
        "objective": "完成整讲推导、应用、比较与检查",
        "knowledge": ["差商极限", "基础求导"],
        "skills": ["完整推导", "比较瞬时速度与平均速度"],
        "misconceptions": ["函数值等于导数"],
        "observable_evidence": ["整讲综合报告"],
        "answer_modalities": ["experiment_plan"],
        "difficulty_contract": {"target_level": "intermediate"},
    }
    slot = {
        "question_type": "selected_response",
        "difficulty_contract": {
            "target_level": "foundational",
            "expected_reasoning_steps": [1, 2],
        },
    }
    brief = {
        "primary_knowledge": "差商极限",
        "primary_skill": "辨析差商极限的成立条件",
        "primary_misconception": "只检查单侧极限",
        "required_observable_evidence": ["排除一个典型误解"],
        "question_type": "selected_response",
    }

    scoped = _objective_for_design_brief(
        objective,
        design_brief=brief,
        slot=slot,
    )

    assert scoped["objective"] == "辨析差商极限的成立条件"
    assert scoped["skills"] == ["辨析差商极限的成立条件"]
    assert scoped["observable_evidence"] == ["排除一个典型误解"]
    assert scoped["answer_modalities"] == ["selected_response"]
    assert scoped["difficulty_contract"]["target_level"] == "foundational"


def test_design_brief_scope_is_also_the_semantic_review_slot():
    slot = {
        "slot_id": "slot-calculus-concept",
        "input_mode": "choice",
        "response_format": "classification_with_reasons",
        "knowledge": ["导数应用"],
        "skills": ["提交完整导数应用分析、符号表与迁移说明"],
        "misconceptions": ["课程级旧误区"],
        "difficulty_contract": {
            "target_level": "foundational",
            "expected_reasoning_steps": [1, 2],
        },
    }
    brief = {
        "primary_knowledge": "导数符号与函数趋势",
        "primary_skill": "辨析导数变号与局部极值",
        "primary_misconception": "只凭导数为零判断极值",
        "required_observable_evidence": ["排除一个典型误解"],
    }

    scoped = _slot_for_design_brief(slot, design_brief=brief)

    assert scoped["slot_id"] == "slot-calculus-concept"
    assert scoped["response_format"] == "choice"
    assert scoped["skills"] == ["辨析导数变号与局部极值"]
    assert scoped["observable_evidence"] == ["排除一个典型误解"]
    assert slot["response_format"] == "classification_with_reasons"


def test_choice_worked_solution_accepts_model_analysis_alias():
    assert worked_solution_is_complete(
        {
            "canonical_answer": "C",
            "worked_solution": {
                "summary": "分别检查左右差商极限并比较二者。",
                "steps": [{
                    "title": "比较左右极限",
                    "explanation": "左极限为负一，右极限为一。",
                    "result": "双侧极限不存在。",
                }],
                "final_answer": "C",
                "checks": ["左右极限不相等"],
                "option_analysis": [
                    {"id": option_id, "analysis": f"选项 {option_id} 的依据"}
                    for option_id in ("A", "B", "C", "D")
                ],
            },
        },
        option_ids=("A", "B", "C", "D"),
    )


def _contract(
    *,
    question_type: str,
    stimulus: str,
    task: str,
    canonical_answer,
    options: list[dict] | None = None,
) -> dict:
    brief = _brief(question_type)
    return {
        "question_type": question_type,
        "design_brief": brief,
        "prompt": f"{stimulus}\n{task}",
        "question_spec": {
            "stimulus": {"rendered_text": stimulus},
            "task": {
                "rendered_text": task,
                "deliverable": "one answer",
            },
            "options": options or [],
            "risk_contract": {
                "risk_level": "low",
                "requires_teacher_review": False,
            },
        },
        "solution_envelope": {
            "canonical_answer": canonical_answer,
            "rubric": ["state the result and verify it"],
            "solution_graph": {
                "schema_version": "solution_graph_v1",
                "steps": [{
                    "step_id": "trace",
                    "action": "trace the learner-visible material",
                    "check": "compare the final result",
                }],
            },
        },
    }


def test_output_prediction_rejects_concept_question_with_irrelevant_code():
    contract = _contract(
        question_type="output_prediction",
        stimulus=(
            "```python\n"
            "items = (1, 2, 3)\n"
            "alias = items\n"
            "```"
        ),
        task=(
            "Which option best reflects the core idea of avoiding side "
            "effects with immutable objects?"
        ),
        canonical_answer="A",
        options=[
            {"id": "A", "text": "Prefer immutable values."},
            {"id": "B", "text": "Always use global variables."},
        ],
    )

    report = evaluate_question_semantic_preflight(contract)
    codes = {issue["code"] for issue in report["issues"]}

    assert report["passed"] is False
    assert "QUESTION_TYPE_SEMANTIC_MISMATCH" in codes
    assert "MATERIAL_NOT_REQUIRED" in codes


def test_output_prediction_accepts_concrete_observable_result():
    contract = _contract(
        question_type="output_prediction",
        stimulus=(
            "```python\n"
            "values = [1, 2]\n"
            "alias = values\n"
            "alias.append(3)\n"
            "print(values)\n"
            "```"
        ),
        task="Predict the exact printed output and explain the alias state.",
        canonical_answer="A",
        options=[
            {"id": "A", "text": "[1, 2, 3]"},
            {"id": "B", "text": "[1, 2]"},
        ],
    )

    report = evaluate_question_semantic_preflight(contract)

    assert report["passed"] is True
    assert report["material_bindings"]


def test_output_prediction_accepts_unity_csharp_observable_phenomenon():
    contract = _contract(
        question_type="output_prediction",
        stimulus=(
            "```csharp\n"
            "void Update() { transform.position += Vector3.right; }\n"
            "```"
        ),
        task="预测帧率波动时会产生什么运行现象，并说明回调顺序。",
        canonical_answer="A",
        options=[
            {"id": "A", "text": "移动速度随帧率变化"},
            {"id": "B", "text": "移动速度保持恒定"},
        ],
    )

    report = evaluate_question_semantic_preflight(contract)

    assert report["passed"] is True
    assert report["checks"]["learner_visible_code"] is True
    assert report["checks"]["observable_result_requested"] is True


def test_output_prediction_accepts_chinese_predicted_final_state():
    contract = _contract(
        question_type="output_prediction",
        stimulus=(
            "```csharp\n"
            "void Update() { transform.Translate(Vector3.forward * 10f); }\n"
            "```"
        ),
        task=(
            "基于上述代码和帧率波动的场景，预测物体在视觉上的最终运动状态，"
            "并指出导致该状态的关键调用机制。"
        ),
        canonical_answer="A",
        options=[
            {"id": "A", "text": "移动速度随帧率变化"},
            {"id": "B", "text": "移动速度保持恒定"},
        ],
    )

    report = evaluate_question_semantic_preflight(contract)

    assert report["passed"] is True
    assert report["checks"]["observable_result_requested"] is True


def test_state_trace_transfer_accepts_chinese_state_tracking_sequence():
    contract = _contract(
        question_type="state_trace_transfer",
        stimulus=(
            "```csharp\n"
            "void FixedUpdate() { rb.AddForce(Vector3.right); }\n"
            "void LateUpdate() { camera.position = rb.position; }\n"
            "```"
        ),
        task="给出修复后的状态跟踪序列，并标明每一步的回调顺序。",
        canonical_answer={
            "trace": ["FixedUpdate applies force", "LateUpdate follows"],
        },
    )

    report = evaluate_question_semantic_preflight(contract)

    assert report["passed"] is True
    assert report["checks"]["observable_state_transfer"] is True
    assert report["checks"]["material_binding_valid"] is True


def test_debugging_trace_rejects_false_error_premise():
    contract = _contract(
        question_type="debugging_trace",
        stimulus=(
            "```python\n"
            "values = [1, 2, 3]\n"
            "print(sum(values))\n"
            "```"
        ),
        task="Locate the bug, explain its cause, repair it, and retest.",
        canonical_answer={
            "analysis": "There is no error; the code is correct as written.",
        },
    )

    report = evaluate_question_semantic_preflight(contract)
    codes = {issue["code"] for issue in report["issues"]}

    assert report["passed"] is False
    assert "FALSE_ERROR_PREMISE" in codes


def test_debugging_trace_requires_location_repair_and_retest_evidence():
    contract = _contract(
        question_type="debugging_trace",
        stimulus=(
            "```python\n"
            "def average(values):\n"
            "    return sum(values) / (len(values) - 1)\n"
            "print(average([2, 4, 6]))\n"
            "```"
        ),
        task="Locate the defect, explain its cause, repair it, and retest.",
        canonical_answer={
            "location": "line 2 denominator",
            "cause": "subtracting one uses the wrong item count",
            "repair": "replace len(values) - 1 with len(values)",
            "retest": "the expected result is 4.0",
        },
    )

    report = evaluate_question_semantic_preflight(contract)

    assert report["passed"] is True


def test_debugging_trace_accepts_chinese_diagnosis_repair_and_verification():
    contract = _contract(
        question_type="debugging_trace",
        stimulus=(
            "```csharp\n"
            "void Update() { rb.velocity = Vector3.right; }\n"
            "```"
        ),
        task=(
            "诊断代码缺陷并提交修正方案，说明运行时错误现象、根本原因、"
            "修改后的代码片段以及验证方法。"
        ),
        canonical_answer={
            "trace": "角色移动时高频抖动，且受 FPS 影响速度不稳定。",
            "diagnosis": (
                "根本原因是 Rigidbody 物理属性在 Update 中被重复覆盖。"
            ),
            "result_check": (
                "将 velocity 修改为在 FixedUpdate 中设置，"
                "验证多帧录制无速度叠加。"
            ),
        },
    )

    report = evaluate_question_semantic_preflight(contract)

    assert report["passed"] is True
    assert report["checks"]["repair_evidence_present"] is True


class _ReviewerCountingModel:
    def __init__(self) -> None:
        self.calls = 0

    async def evaluate_candidate(self, *args, **kwargs):
        self.calls += 1
        return {
            "passed": True,
            "confidence": 0.95,
            "solution_consistent": True,
            "dimensions": {},
            "evidence": ["independent semantic review"],
            "issues": [],
        }


class _SolverCountingModel(_ReviewerCountingModel):
    def __init__(self) -> None:
        super().__init__()
        self.solve_calls = 0

    async def solve_candidate(self, public_question_spec):
        self.solve_calls += 1
        return {"answer": "A"}


async def test_semantic_failure_is_blocked_before_independent_solver():
    model = _SolverCountingModel()
    orchestrator = AssessmentGenerationOrchestrator(model=model)
    brief = _brief("output_prediction")
    base = {
        "schema_version": "universal_question_contract_v1",
        "question_type": "output_prediction",
        "design_brief": brief,
        "question_spec": {
            "schema_version": "question_spec_v2",
            "course_id": "course-1",
            "node_id": "node-1",
            "practice_level": "concept_check",
            "input_contract": {
                "schema_version": "input_contract_v2",
                "mode": "choice",
            },
            "risk_contract": {
                "risk_level": "low",
                "requires_teacher_review": False,
            },
            "stimulus": {"rendered_text": "placeholder material"},
            "task": {"rendered_text": "placeholder instruction"},
        },
        "solution_envelope": {
            "schema_version": "solution_envelope_v1",
            "validation_mode": "state_trace_validator",
        },
    }
    candidate = {
        "question_spec": {
            "stimulus": {
                "rendered_text": (
                    "```python\n"
                    "items = (1, 2, 3)\n"
                    "alias = items\n"
                    "```"
                ),
            },
            "task": {
                "rendered_text": (
                    "Which option best reflects the core idea of immutable "
                    "objects in this design?"
                ),
                "deliverable": "one option",
            },
            "constraints": [],
            "response_contract": {"format": "choice"},
            "options": [
                {"id": "A", "text": "avoid side effects"},
                {"id": "B", "text": "use global state"},
            ],
        },
        "solution": {
            "validation_mode": "state_trace_validator",
            "canonical_answer": "A",
            "rubric": ["select the correct concept"],
            "validator_config": {},
            "solution_graph": {
                "schema_version": "solution_graph_v1",
                "steps": [{
                    "step_id": "concept",
                    "action": "identify the concept",
                    "check": "compare the option",
                }],
            },
        },
    }
    audit = {
        "semantic_preflight_calls": 0,
        "independent_solution_calls": 0,
        "call_timings": [],
    }

    with pytest.raises(SemanticPreflightFailure) as captured:
        await orchestrator._solve_and_build(
            base,
            candidate,
            audit,
            generation_policy=resolve_assessment_generation_policy("complete"),
            solution_batcher=None,
        )

    assert model.solve_calls == 0
    assert audit["independent_solution_calls"] == 0
    assert {
        issue["code"]
        for issue in captured.value.report["issues"]
    } >= {
        "QUESTION_TYPE_SEMANTIC_MISMATCH",
        "MATERIAL_NOT_REQUIRED",
    }


async def test_clean_low_risk_deterministic_question_skips_llm_review():
    model = _ReviewerCountingModel()
    orchestrator = AssessmentGenerationOrchestrator(model=model)
    contract = _contract(
        question_type="output_prediction",
        stimulus="```python\nprint(1 + 1)\n```",
        task="Predict the exact printed output.",
        canonical_answer="A",
        options=[
            {"id": "A", "text": "2"},
            {"id": "B", "text": "1"},
        ],
    )
    contract["solution_validation"] = {
        "deterministic": True,
        "passed": True,
    }
    contract["semantic_preflight"] = (
        evaluate_question_semantic_preflight(contract)
    )
    audit = {"semantic_evaluation_calls": 0, "call_timings": []}

    report = await orchestrator._semantic_report(
        contract,
        independent={"answer": "A"},
        objective={"objective_id": "obj-1"},
        slot={"slot_id": "slot-1"},
        audit=audit,
    )

    assert report["passed"] is True
    assert report["reviewer_triggered"] is False
    assert model.calls == 0


@pytest.mark.parametrize(
    "practice_level",
    ["objective_practice", "mastery_check"],
)
async def test_higher_practice_levels_require_semantic_review_even_when_deterministic(
    practice_level,
):
    model = _ReviewerCountingModel()
    orchestrator = AssessmentGenerationOrchestrator(model=model)
    contract = _contract(
        question_type="output_prediction",
        stimulus="```python\nprint(1 + 1)\n```",
        task="Predict the exact printed output.",
        canonical_answer="A",
        options=[
            {"id": "A", "text": "2"},
            {"id": "B", "text": "1"},
        ],
    )
    contract["question_spec"]["practice_level"] = practice_level
    contract["solution_validation"] = {
        "deterministic": True,
        "passed": True,
    }
    contract["semantic_preflight"] = (
        evaluate_question_semantic_preflight(contract)
    )
    audit = {"semantic_evaluation_calls": 0, "call_timings": []}

    report = await orchestrator._semantic_report(
        contract,
        independent={"answer": "A"},
        objective={"objective_id": "obj-1"},
        slot={"slot_id": "slot-1"},
        audit=audit,
    )

    assert report["reviewer_triggered"] is True
    assert model.calls == 1


async def test_open_or_warned_question_invokes_isolated_llm_review():
    model = _ReviewerCountingModel()
    orchestrator = AssessmentGenerationOrchestrator(model=model)
    contract = _contract(
        question_type="case_analysis",
        stimulus="A short case with two constraints.",
        task="Use both constraints to justify a decision.",
        canonical_answer={"rubric": ["uses both constraints"]},
    )
    contract["solution_validation"] = {
        "deterministic": False,
        "passed": True,
    }
    contract["semantic_preflight"] = {
        "schema_version": "question_semantic_preflight_v1",
        "passed": True,
        "requires_llm_review": True,
        "issues": [],
    }
    audit = {"semantic_evaluation_calls": 0, "call_timings": []}

    report = await orchestrator._semantic_report(
        contract,
        independent={"answer": {"text": "decision"}},
        objective={"objective_id": "obj-1"},
        slot={"slot_id": "slot-1"},
        audit=audit,
    )

    assert report["reviewer_triggered"] is True
    assert model.calls == 1
