from assessment_compiler import compile_formal_task_contract
import pytest


@pytest.mark.parametrize("question_type,answer", [
    ("single_choice", "B"),
    ("multiple_choice", ["A", "B"]),
    ("true_false", "A"),
])
def test_imported_choice_without_input_contract_uses_exact_grading(question_type, answer):
    compiled = compile_formal_task_contract({
        "question_type": question_type,
        "options": [{"option_id": "A", "text": "观察"},
                    {"option_id": "B", "text": "用户旅程图"}],
        "answer_spec": {"type": question_type, "correct_answer": answer},
    })
    assert compiled["input_contract"]["mode"] == "choice"
    assert compiled["grading_policy"]["method"] == "deterministic"


def test_imported_choice_preserves_explicit_legacy_rubric_policy():
    compiled = compile_formal_task_contract({
        "question_type": "single_choice",
        "options": [{"option_id": "A", "text": "观察"},
                    {"option_id": "B", "text": "用户旅程图"}],
        "answer_spec": {"type": "single_choice", "correct_answer": "B"},
        "formal_task": {"grading_policy": {"method": "rubric_ai"}},
    })
    assert compiled["grading_policy"]["method"] == "rubric_ai"


def test_legacy_non_choice_cached_grading_policy_is_preserved():
    compiled = compile_formal_task_contract({
        "question_type": "short_answer",
        "formal_task": {"compiled_contract_hash": "qcc_cached_text",
                        "grading_policy": {"method": "rubric_ai_with_reference"}},
    })
    assert compiled["grading_policy"]["method"] == "rubric_ai_with_reference"


@pytest.mark.asyncio
async def test_cached_imported_choice_contract_is_recompiled_without_model_grading(monkeypatch):
    from practice_grading import PracticeGrader

    item = {
        "question_type": "single_choice",
        "options": [{"option_id": "A", "text": "5why分析法"},
                    {"option_id": "B", "text": "用户旅程图分析法"}],
        "answer_spec": {"type": "single_choice", "correct_answer": "B", "correct_option_id": "B"},
        "formal_task": {"compiled_contract_hash": "qcc_legacy_cache",
                        "grading_policy": {"method": "rubric_ai"}},
    }
    compiled = compile_formal_task_contract(item)
    assert compiled["grading_policy"]["method"] == "deterministic"
    grader = PracticeGrader()

    async def no_model(*args, **kwargs):
        pytest.fail("An imported choice must use its confirmed option IDs")

    monkeypatch.setattr(grader, "_grade_rubric", no_model)
    for option, expected in [("A", 0), ("B", 100)]:
        result = await grader.grade({**item, **compiled}, {
            "answer_payload": {"selected_option_ids": [option]},
        })
        assert result["score"] == expected
        assert result["grading_method"] == "deterministic"


def _v2_item(**overrides):
    item = {
        "question_type": "output_prediction",
        "practice_levels": ["concept_check"],
        "question_spec": {
            "schema_version": "question_spec_v2",
            "input_contract": {
                "schema_version": "input_contract_v2",
                "mode": "choice",
                "required": True,
            },
            "options": [
                {"id": "A", "text": "1"},
                {"id": "B", "text": "2"},
            ],
        },
        "input_contract": {
            "schema_version": "input_contract_v2",
            "mode": "choice",
            "required": True,
        },
    }
    item.update(overrides)
    return item


def test_final_contract_rejects_choice_label_on_structured_input():
    structured = {
        "schema_version": "input_contract_v2",
        "mode": "structured_fields",
        "required": True,
        "fields": [],
    }
    item = _v2_item(
        question_type="single_choice",
        input_contract=structured,
        question_spec={
            "schema_version": "question_spec_v2",
            "input_contract": structured,
        },
    )

    compiled = compile_formal_task_contract(
        item,
        {
            "validation_mode": "expert_rubric_validator",
            "canonical_answer": {"reason": "answer"},
            "rubric": ["给出判断依据"],
            "worked_solution": {
                "summary": "先依据题面条件判断，再核对结论是否满足要求。",
                "steps": ["逐项检查题面条件并形成判断依据。"],
                "final_answer": {"reason": "answer"},
                "checks": ["结论回应全部题目要求"],
            },
        },
    )

    assert compiled["contract_validation"]["passed"] is False
    assert {
        issue["code"]
        for issue in compiled["contract_validation"]["issues"]
    } == {"QUESTION_TYPE_INPUT_MODE_MISMATCH"}


def test_final_contract_rejects_public_private_choice_drift():
    compiled = compile_formal_task_contract(
        _v2_item(),
        {
            "validation_mode": "exact_validator",
            "choice_answer_spec": {
                "correct_option_id": "A",
                "options": [
                    {"id": "A", "text": "different"},
                    {"id": "B", "text": "2"},
                ],
            },
        },
    )

    assert compiled["contract_validation"]["passed"] is False
    assert "PUBLIC_PRIVATE_OPTIONS_MISMATCH" in {
        issue["code"]
        for issue in compiled["contract_validation"]["issues"]
    }


def test_legacy_text_fallback_remains_visible_but_not_mastery_eligible():
    compiled = compile_formal_task_contract(
        {
            "question_type": "implementation_task",
            "practice_levels": ["mastery_check"],
            "question_spec": {
                "schema_version": "question_spec_v2",
            },
            "formal_task": {
                "grading_policy": {"method": "rubric_ai"},
            },
        },
        {
            "validation_mode": "code_validator",
            "canonical_answer": "legacy answer",
            "rubric": ["说明实现与检查过程"],
        },
    )

    assert compiled["compatibility_mode"] == "legacy_text"
    assert compiled["contract_validation"]["passed"] is True
    assert compiled["grading_policy"]["method"] == "rubric_ai"
    assert compiled["validation_policy"]["mastery_eligible"] is False


def test_compiler_preserves_complete_worked_solution_for_choice():
    compiled = compile_formal_task_contract(
        _v2_item(),
        {
            "validation_mode": "exact_validator",
            "canonical_answer": "A",
            "worked_solution": {
                "schema_version": "worked_solution_v1",
                "summary": "先计算题面表达式，再逐项比较各选项。",
                "steps": [{
                    "title": "计算",
                    "explanation": "代入题面数据得到结果1。",
                    "result": "1",
                }],
                "final_answer": "A",
                "checks": ["把结果代回题面条件"],
                "option_analysis": [
                    {
                        "option_id": "A",
                        "is_correct": True,
                        "explanation": "与计算结果1一致。",
                    },
                    {
                        "option_id": "B",
                        "is_correct": False,
                        "explanation": "与计算结果1不一致。",
                    },
                ],
            },
        },
    )

    solution = compiled["answer_spec"]["solution_spec"]
    assert compiled["contract_validation"]["passed"] is True
    assert solution["summary"].startswith("先计算")
    assert solution["steps"] == ["计算；代入题面数据得到结果1。；1"]
    assert {
        item["option_id"]
        for item in solution["option_analysis"]
    } == {"A", "B"}
