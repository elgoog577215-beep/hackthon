from practice_contracts import (
    enrich_question_contract,
    project_default_single_choice,
)


def test_legacy_question_uses_reasoning_path_instead_of_generic_hint_fallback():
    enriched = enrich_question_contract({
        "revision_id": "qr-legacy",
        "question_type": "worked_solution",
        "prompt": "给定两组实验数据A=[2,4,6]、B=[3,5,7]，比较均值并说明差异。",
        "deliverable": "两组均值、差值和证据结论",
        "constraints": ["结论不得超出给定数据"],
        "result_checks": ["均值可以由原始数据复算"],
        "answer_spec": {
            "criteria": ["两组均值正确", "差值方向正确", "结论有数据依据"],
            "canonical_answer": {
                "mean_a": 4,
                "mean_b": 5,
                "difference": 1,
            },
            "pass_score": 70,
        },
    })

    assert enriched["reasoning_path"]["schema_version"] == "reasoning_path_v1"
    assert enriched["reasoning_path"]["input_anchors"]
    assert enriched["hint_contract"]["generator"] == "reasoning_path_v1"
    assert all(level["step_refs"] for level in enriched["hint_contract"]["levels"])
    assert all(
        "整理输入—选择方法" not in level["content"]
        and "先澄清任务最终要验证什么" not in level["content"]
        for level in enriched["hint_contract"]["levels"]
    )
    assert (
        enriched["answer_spec"]["solution_spec"]["schema_version"]
        == "solution_spec_v1"
    )


def test_frozen_reasoning_path_hint_contract_is_not_replaced():
    question = {
        "revision_id": "qr-current",
        "question_type": "worked_solution",
        "prompt": "具体题目",
        "reasoning_path": {
            "schema_version": "reasoning_path_v1",
            "input_anchors": [{"path": "input"}],
            "steps": [{"step_id": "orient"}],
        },
        "hint_contract": {
            "generator": "reasoning_path_v1",
            "levels": [{
                "level": level,
                "content": f"冻结提示{level}",
                "step_refs": ["orient"],
            } for level in (1, 2, 3)],
        },
        "answer_spec": {"criteria": ["完成任务"]},
    }

    enriched = enrich_question_contract(question)

    assert [
        level["content"] for level in enriched["hint_contract"]["levels"]
    ] == ["冻结提示1", "冻结提示2", "冻结提示3"]


def test_generated_practice_contract_projects_to_private_single_choice_answer():
    projected = project_default_single_choice({
        "prompt": "根据矩阵计算结果并完成判断。",
        "deliverable": "矩阵乘积与行列式",
        "estimated_minutes": 8,
        "question_spec": {
            "task": {
                "rendered_text": "计算矩阵乘积，并判断结果是否可逆。",
                "deliverable": "矩阵乘积与判断",
            },
            "stimulus": {
                "rendered_text": "给定 A=[[1,1],[0,1]]，B=[[2,0],[1,1]]。"
            },
            "response_contract": {"format": "worked_solution"},
            "solution_revision_id": "sol-original",
        },
        "solution_envelope": {
            "solution_revision_id": "sol-original",
            "canonical_answer": {
                "product": [[3, 1], [1, 1]],
                "determinant": 2,
                "invertible": True,
            },
            "rubric": ["乘积正确", "可逆性判断正确"],
            "validator_config": {"pass_score": 70},
            "legacy_answer_spec": {
                "criteria": ["乘积正确", "可逆性判断正确"],
                "pass_score": 70,
                "solution_spec": {
                    "schema_version": "solution_spec_v1",
                    "final_answer": {
                        "product": [[3, 1], [1, 1]],
                        "determinant": 2,
                        "invertible": True,
                    },
                },
            },
        },
    }, misconception_labels=["把矩阵乘法误当成逐元素相乘"])

    assert projected["question_type"] == "single_choice"
    assert projected["deliverable"] == "一个唯一选项"
    assert projected["estimated_minutes"] == 5
    assert projected["question_spec"]["response_contract"] == {
        "format": "single_choice",
        "required_parts": ["selected_option_id"],
        "option_count": 4,
        "selection_limit": 1,
    }
    assert [item["option_id"] for item in projected["options"]] == [
        "A",
        "B",
        "C",
        "D",
    ]
    assert len({item["text"] for item in projected["options"]}) == 4
    private_answer = projected["solution_envelope"]["choice_answer_spec"]
    assert private_answer["correct_option_id"] in {"A", "B", "C", "D"}
    assert private_answer["canonical_answer"]["determinant"] == 2
    assert projected["question_spec"]["solution_revision_id"].startswith("sol_")
    assert projected["question_spec"]["solution_revision_id"] != "sol-original"
    assert "correct_option_id" not in projected
    assert "answer_spec" not in projected


def test_rubric_task_without_unique_model_answer_becomes_best_response_choice():
    projected = project_default_single_choice({
        "prompt": "根据两则史料形成有限结论。",
        "deliverable": "论点、两条证据、推理连接和局限说明",
        "estimated_minutes": 8,
        "question_spec": {
            "task": {
                "rendered_text": "引用两则材料论证社会结构变化。",
                "deliverable": "完整史料论证",
            },
            "stimulus": {
                "rendered_text": "材料 A 记录就业增长；材料 B 记录地区差异。"
            },
            "response_contract": {"format": "evidence_argument"},
            "solution_revision_id": "sol-rubric",
        },
        "solution_envelope": {
            "solution_revision_id": "sol-rubric",
            "canonical_answer": None,
            "rubric": [
                "论点范围适当",
                "准确引用两则材料",
                "证据与结论有明确推理",
                "说明至少一项材料局限",
            ],
            "legacy_answer_spec": {
                "criteria": [
                    "论点范围适当",
                    "准确引用两则材料",
                    "证据与结论有明确推理",
                    "说明至少一项材料局限",
                ],
                "expected_keywords": ["史料证据"],
                "pass_score": 70,
                "solution_spec": {
                    "schema_version": "solution_spec_v1",
                    "response_requirements": ["论点、证据、推理、局限"],
                },
            },
        },
    })

    private_answer = projected["solution_envelope"]["choice_answer_spec"]
    assert projected["question_type"] == "single_choice"
    assert len(projected["options"]) == 4
    assert len({item["text"] for item in projected["options"]}) == 4
    assert "比较下列四份作答方案" in projected["prompt"]
    assert private_answer["canonical_answer"]["selection_basis"] == (
        "rubric_complete_response"
    )
    assert len(
        private_answer["canonical_answer"]["required_criteria"]
    ) == 4
    assert private_answer["solution_spec"]["final_answer"] == (
        private_answer["canonical_answer"]
    )
