from __future__ import annotations

from copy import deepcopy

import pytest

from assessment_blueprint import (
    compile_course_assessment_blueprint,
)
from assessment_contracts import (
    compile_assessment_objectives,
    compile_course_assessment_profile,
)
from assessment_quality import evaluate_question_contract_quality
from assessment_retrieval import (
    compile_local_reference_package,
    enrich_reference_package_with_web,
    references_for_objective,
)
from routers.question_bank import _require_complete_generation


FAMILIES = (
    "general",
    "math_formal",
    "programming_engineering",
    "natural_science",
    "life_medical",
    "humanities_social",
    "language_learning",
    "business_career",
)


def _course(family: str = "general") -> dict:
    return {
        "course_id": f"benchmark-{family}",
        "course_name": f"{family} 基准课程",
        "difficulty": "intermediate",
        "subject_pedagogy_profile": {
            "primary_mode": family,
            "user_locked": True,
        },
        "generation_request": {
            "web_question_enrichment": {
                "mode": "auto_on_gap",
            },
        },
        "evidence_catalog": [],
        "nodes": [{
            "node_id": "node-1",
            "node_level": 2,
            "node_name": "核心章节",
            "node_content": (
                "这是用于构建可验证题目的章节材料，包含明确条件、"
                "关键概念、应用场景和结果检查要求。PRIVATE_BODY_SENTINEL"
            ),
            "learning_objective": "解释核心概念并在新情境中正确应用",
            "key_points": ["核心概念", "边界条件", "结果验证"],
            "difficulty_contract": {
                "target_level": "intermediate",
            },
        }],
    }


@pytest.mark.parametrize("family", FAMILIES)
def test_eight_subject_families_compile_diverse_generation_blueprints(
    family: str,
):
    course = _course(family)
    profile = compile_course_assessment_profile(course)
    objectives = compile_assessment_objectives(course, profile)

    blueprint = compile_course_assessment_blueprint(
        course,
        profile=profile,
        objectives=objectives,
    )

    slots = blueprint["nodes"][0]["slots"]
    assert blueprint["schema_version"] == (
        "course_assessment_blueprint_v2"
    )
    assert len(slots) == 3
    assert len({slot["input_mode"] for slot in slots}) >= 2
    assert sum(
        slot["input_mode"] == "rich_text"
        for slot in slots
    ) <= 1
    assert all(
        slot["input_contract"]["schema_version"]
        == "input_contract_v2"
        for slot in slots
    )
    assert blueprint["diversity_policy"]["passed"] is True


def test_programming_blueprint_is_not_all_implementation_tasks():
    course = _course("programming_engineering")
    course["nodes"][0]["learning_objective"] = (
        "编写函数实现一个可验证的数据转换"
    )
    course["nodes"][0]["assessment"] = [
        "实现函数并通过自动化测试",
    ]
    blueprint = compile_course_assessment_blueprint(course)
    slots = blueprint["nodes"][0]["slots"]

    assert [slot["question_type"] for slot in slots] == [
        "output_prediction",
        "debugging_trace",
        "implementation_task",
    ]
    assert [slot["input_mode"] for slot in slots] == [
        "choice",
        "structured_fields",
        "code",
    ]
    assert slots[-1]["selection_reason"] == (
        "explicit_implementation_objective"
    )


def test_conceptual_programming_node_uses_state_transfer_mastery():
    course = _course("programming_engineering")
    course["nodes"][0].update({
        "node_name": "1.7 对象生命周期管理：创建、使用与销毁",
        "learning_objective": (
            "解释引用计数和垃圾回收如何共同管理对象生命周期"
        ),
        "key_points": ["引用计数", "垃圾回收", "对象生命周期"],
    })

    blueprint = compile_course_assessment_blueprint(course)
    slots = blueprint["nodes"][0]["slots"]

    assert [slot["question_type"] for slot in slots] == [
        "output_prediction",
        "debugging_trace",
        "state_trace_transfer",
    ]
    assert [slot["input_mode"] for slot in slots] == [
        "choice",
        "structured_fields",
        "structured_fields",
    ]
    assert slots[-1]["validation_mode"] == (
        "expert_rubric_validator"
    )
    assert slots[-1]["selection_reason"] == (
        "conceptual_or_non_runner_objective"
    )


def test_java_course_does_not_claim_hidden_test_runner_support():
    course = _course("programming_engineering")
    course["course_name"] = "Java 并发编程"
    course["nodes"][0]["node_content"] += " 使用 Java 语言完成分析。"

    blueprint = compile_course_assessment_blueprint(course)
    slots = blueprint["nodes"][0]["slots"]

    assert all(slot["input_mode"] != "code" for slot in slots)
    assert slots[-1]["question_type"] == "state_trace_transfer"
    assert slots[-1]["validation_mode"] == "expert_rubric_validator"


async def test_web_retrieval_runs_before_generation_with_minimal_query():
    course = _course("math_formal")
    profile = compile_course_assessment_profile(course)
    objectives = compile_assessment_objectives(course, profile)
    blueprint = compile_course_assessment_blueprint(
        course,
        profile=profile,
        objectives=objectives,
    )
    package = compile_local_reference_package(
        course,
        objectives=objectives,
        blueprint=blueprint,
    )
    queries: list[str] = []

    async def search(query: str, *, num_results: int):
        queries.append(query)
        return [{
            "url": "https://example.edu/open-question",
            "title": "Open assessment example",
            "text": (
                "Given a function and constraints, select the valid claim, "
                "show a calculation, and justify the result."
            ),
            "open_license": True,
        }]

    enriched = await enrich_reference_package_with_web(
        course,
        package,
        objectives=objectives,
        search=search,
    )

    assert queries
    assert "PRIVATE_BODY_SENTINEL" not in queries[0]
    assert "selected_response" in queries[0]
    assert enriched["web"]["status"] == "completed"
    assert enriched["references"][0]["reuse_policy"] == (
        "reference_only"
    )
    assert enriched["schema_version"] == (
        "question_reference_package_v2"
    )
    assert enriched["content_coverage"][0]["covered"] is True
    assert enriched["method_coverage"]


def test_teacher_question_bank_has_highest_authoring_priority():
    course = _course("general")
    course["evidence_catalog"] = [{
        "kind": "question",
        "purpose": "question_source",
        "source_text": (
            f"{course['nodes'][0]['learning_objective']} "
            "A. valid boundary B. invalid boundary"
        ),
        "rights_basis": "teacher_asserted",
    }]
    profile = compile_course_assessment_profile(course)
    objectives = compile_assessment_objectives(course, profile)
    blueprint = compile_course_assessment_blueprint(
        course,
        profile=profile,
        objectives=objectives,
    )

    package = compile_local_reference_package(
        course,
        objectives=objectives,
        blueprint=blueprint,
    )
    references = references_for_objective(
        package,
        str(objectives[0]["objective_id"]),
        limit=10,
    )

    assert references
    assert references[0]["source_type"] == "teacher_question_bank"


async def test_method_gap_triggers_web_even_when_content_is_covered():
    course = _course("programming_engineering")
    profile = compile_course_assessment_profile(course)
    objectives = compile_assessment_objectives(course, profile)
    blueprint = compile_course_assessment_blueprint(
        course,
        profile=profile,
        objectives=objectives,
    )
    package = compile_local_reference_package(
        course,
        objectives=objectives,
        blueprint=blueprint,
    )
    assert package["content_coverage"][0]["covered"] is True
    assert any(
        not item["covered"]
        for item in package["method_coverage"]
    )
    calls = 0

    async def search(query: str, *, num_results: int):
        nonlocal calls
        calls += 1
        return [{
            "url": f"https://example.edu/pattern-{calls}",
            "title": "Open authoring pattern",
            "text": (
                "```python\nprint(1 + 1)\n``` "
                "Predict the exact output. A. 2 B. 1"
            ),
            "open_license": True,
        }]

    enriched = await enrich_reference_package_with_web(
        course,
        package,
        objectives=objectives,
        search=search,
    )

    assert calls > 0
    assert enriched["web"]["status"] == "completed"
    assert any(
        item["source_type"] == "trusted_web_reference"
        for item in enriched["authoring_patterns"]
    )


async def test_web_failure_uses_builtin_authoring_templates():
    course = _course("programming_engineering")
    profile = compile_course_assessment_profile(course)
    objectives = compile_assessment_objectives(course, profile)
    blueprint = compile_course_assessment_blueprint(
        course,
        profile=profile,
        objectives=objectives,
    )
    package = compile_local_reference_package(
        course,
        objectives=objectives,
        blueprint=blueprint,
    )

    async def failing_search(query: str, *, num_results: int):
        raise RuntimeError("search unavailable")

    enriched = await enrich_reference_package_with_web(
        course,
        package,
        objectives=objectives,
        search=failing_search,
    )

    assert enriched["web"]["status"] == "failed_fallback_local"
    assert any(
        item["source_type"] == "builtin_subject_template"
        for item in enriched["authoring_patterns"]
    )
    assert all(
        item["covered"]
        for item in enriched["method_coverage"]
    )


def _quality_contract() -> tuple[dict, dict, dict]:
    objective = {
        "objective": "使用热力学第一定律计算内能变化",
        "knowledge": ["热力学第一定律"],
        "skills": ["列式计算"],
        "source_excerpt": "课程材料中的热力学第一定律说明。",
    }
    slot = {
        "difficulty_contract": {"target_level": "intermediate"},
    }
    contract = {
        "prompt": (
            "使用热力学第一定律计算内能变化。\n\n"
            "封闭系统吸热20 kJ并对外做功8 kJ，求内能变化并核对单位。"
        ),
        "input_contract": {
            "schema_version": "input_contract_v2",
            "mode": "numeric_unit",
            "required": True,
            "fields": [
                {"field_id": "value", "kind": "number"},
                {"field_id": "unit", "kind": "short_text"},
                {"field_id": "work", "kind": "rich_text"},
            ],
        },
        "question_spec": {
            "schema_version": "question_spec_v2",
            "archetype_id": "numeric_calculation",
            "stimulus": {
                "rendered_text": "封闭系统吸热20 kJ并对外做功8 kJ。",
            },
            "task": {
                "rendered_text": "求内能变化并核对单位。",
            },
            "constraints": ["采用 ΔU=Q-W"],
            "response_contract": {"format": "numeric_with_unit"},
            "difficulty_contract": {
                "target_level": "intermediate",
            },
            "input_contract": {
                "schema_version": "input_contract_v2",
                "mode": "numeric_unit",
                "required": True,
                "fields": [
                    {"field_id": "value", "kind": "number"},
                    {"field_id": "unit", "kind": "short_text"},
                    {"field_id": "work", "kind": "rich_text"},
                ],
            },
        },
        "solution_envelope": {
            "validation_mode": "numeric_unit_validator",
            "canonical_answer": {"value": 12, "unit": "kJ"},
            "rubric": ["列式正确", "结果和单位正确"],
            "worked_solution": {
                "schema_version": "worked_solution_v1",
                "summary": "统一符号与单位后，代入热力学第一定律计算。",
                "steps": ["ΔU=Q-W=20 kJ-8 kJ=12 kJ。"],
                "final_answer": {"value": 12, "unit": "kJ"},
                "checks": ["回代得到ΔU+W=Q"],
            },
        },
        "solution_validation": {
            "passed": True,
            "deterministic": True,
            "independent_solution_present": True,
        },
    }
    return contract, objective, slot


def test_quality_score_passes_at_85_and_blocks_reference_copy():
    contract, objective, slot = _quality_contract()
    passing = evaluate_question_contract_quality(
        contract,
        objective=objective,
        slot=slot,
        semantic_report={
            "passed": True,
            "confidence": 1.0,
            "dimensions": {
                "curriculum_targeting": 20,
                "answerability_and_completeness": 15,
                "difficulty_fit": 10,
                "clarity": 5,
            },
        },
    )
    assert passing["passed"] is True
    assert passing["score"] == 100

    copied = evaluate_question_contract_quality(
        contract,
        objective=objective,
        slot=slot,
        references=[{
            "reference_excerpt": contract["prompt"],
        }],
        semantic_report=passing["semantic"],
    )
    assert copied["passed"] is False
    assert copied["reference_similarity"] >= 0.65
    assert "REFERENCE_SIMILARITY_HIGH" in {
        issue["code"] for issue in copied["issues"]
    }


def test_quality_gate_rejects_missing_worked_solution():
    contract, objective, slot = _quality_contract()
    contract["solution_envelope"].pop("worked_solution")

    report = evaluate_question_contract_quality(
        contract,
        objective=objective,
        slot=slot,
        semantic_report={
            "passed": True,
            "confidence": 1.0,
        },
    )

    assert report["passed"] is False
    assert "WORKED_SOLUTION_INCOMPLETE" in {
        issue["code"] for issue in report["issues"]
    }


def test_quality_gate_rejects_task_contract_as_canonical_answer():
    contract, objective, slot = _quality_contract()
    contract["solution_envelope"]["canonical_answer"] = {
        "objective": "完成综合任务",
        "required_evidence": ["给出证据"],
        "required_parts": ["结论"],
    }
    contract["solution_envelope"]["worked_solution"][
        "final_answer"
    ] = contract["solution_envelope"]["canonical_answer"]

    report = evaluate_question_contract_quality(
        contract,
        objective=objective,
        slot=slot,
        semantic_report={
            "passed": True,
            "confidence": 1.0,
        },
    )

    assert report["passed"] is False
    assert "ANSWER_CONTRACT_PLACEHOLDER" in {
        issue["code"] for issue in report["issues"]
    }


def test_quality_gate_regenerates_cross_type_semantic_duplicate():
    contract, objective, slot = _quality_contract()
    existing = deepcopy(contract)
    existing["question_type"] = "selected_response"
    contract["question_type"] = "structured_application"

    report = evaluate_question_contract_quality(
        contract,
        objective=objective,
        slot={**slot, "discipline_family": "natural_science"},
        existing_questions=[existing],
        semantic_report={
            "passed": True,
            "confidence": 1.0,
            "dimensions": {
                "curriculum_targeting": 20,
                "answerability_and_completeness": 15,
                "difficulty_fit": 10,
                "clarity": 5,
            },
        },
    )

    assert report["passed"] is False
    assert report["decision"] == "regenerate"
    assert report["diversity_report"]["passed"] is False
    assert "SEMANTIC_DUPLICATE_QUESTION" in {
        issue["code"] for issue in report["issues"]
    }


def test_code_question_fails_closed_without_runner_attestation():
    contract, objective, slot = _quality_contract()
    contract = deepcopy(contract)
    contract["solution_envelope"]["validation_mode"] = (
        "code_validator"
    )
    contract["solution_validation"]["validator_result"] = {
        "runner_attested": False,
    }

    report = evaluate_question_contract_quality(
        contract,
        objective=objective,
        slot=slot,
        semantic_report={
            "passed": True,
            "confidence": 1.0,
            "dimensions": {
                "curriculum_targeting": 20,
                "answerability_and_completeness": 15,
                "difficulty_fit": 10,
                "clarity": 5,
            },
        },
    )

    assert report["passed"] is False
    assert "RUNNER_ATTESTATION_MISSING" in {
        issue["code"] for issue in report["issues"]
    }


def test_question_that_references_code_requires_a_visible_fenced_block():
    contract, objective, slot = _quality_contract()
    contract = deepcopy(contract)
    contract["question_spec"]["stimulus"]["rendered_text"] = (
        "考虑以下代码：\n\nclass Demo:\n    pass\n\nobj = Demo()"
    )
    contract["question_spec"]["task"]["rendered_text"] = (
        "根据上述代码判断 type(obj) 的结果。"
    )
    contract["prompt"] = (
        f"{contract['question_spec']['stimulus']['rendered_text']}\n"
        f"{contract['question_spec']['task']['rendered_text']}"
    )

    report = evaluate_question_contract_quality(
        contract,
        objective=objective,
        slot=slot,
        semantic_report={
            "passed": True,
            "confidence": 1.0,
            "dimensions": {
                "curriculum_targeting": 20,
                "answerability_and_completeness": 15,
                "difficulty_fit": 10,
                "clarity": 5,
            },
        },
    )

    assert report["passed"] is False
    assert "CODE_MATERIAL_NOT_RENDERABLE" in {
        issue["code"] for issue in report["issues"]
    }


def test_debugging_trace_cannot_publish_with_only_a_code_placeholder():
    contract, objective, slot = _quality_contract()
    contract = deepcopy(contract)
    contract["question_type"] = "debugging_trace"
    contract["question_spec"]["stimulus"]["rendered_text"] = (
        "\u4e0b\u9762\u662f\u4e00\u6bb5 Python \u4ee3\u7801\u53ca\u5176"
        "\u6267\u884c\u8f68\u8ff9\uff0c\u8bf7\u6839\u636e\u4ee3\u7801"
        "\u5206\u6790\u95ee\u9898\u3002"
    )
    contract["question_spec"]["task"]["rendered_text"] = (
        "\u5206\u6790\u7ed9\u5b9a\u4ee3\u7801\u548c\u6267\u884c"
        "\u8f68\u8ff9\uff0c\u5e76\u63d0\u4f9b\u89e3\u51b3\u65b9\u6848\u3002"
    )
    contract["prompt"] = "\n".join([
        contract["question_spec"]["stimulus"]["rendered_text"],
        contract["question_spec"]["task"]["rendered_text"],
    ])
    contract["input_materials"] = [
        contract["question_spec"]["stimulus"]["rendered_text"],
    ]

    report = evaluate_question_contract_quality(
        contract,
        objective=objective,
        slot=slot,
        semantic_report={
            "passed": True,
            "confidence": 1.0,
            "dimensions": {
                "curriculum_targeting": 20,
                "answerability_and_completeness": 15,
                "difficulty_fit": 10,
                "clarity": 5,
            },
        },
    )

    assert report["passed"] is False
    assert report["hard_gates"]["code_rendering"] is False
    assert "CODE_MATERIAL_NOT_RENDERABLE" in {
        issue["code"] for issue in report["issues"]
    }


def test_incomplete_generation_is_blocked_before_persistence():
    course = {
        "_assessment_generation_audit": {
            "planned_item_count": 2,
            "failure_count": 1,
            "items": [
                {"final_decision": "publish"},
                {
                    "final_decision": "discard",
                    "error_code": "AIProviderUnavailable",
                    "error_message": "daily quota exceeded",
                },
            ],
        },
    }

    with pytest.raises(
        RuntimeError,
        match="daily quota exceeded",
    ):
        _require_complete_generation(course)
