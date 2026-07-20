from assessment_compiler import compile_formal_task_contract


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
