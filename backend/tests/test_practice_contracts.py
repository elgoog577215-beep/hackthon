from practice_contracts import enrich_question_contract


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
