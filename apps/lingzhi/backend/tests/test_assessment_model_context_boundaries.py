import json

from assessment_orchestrator import UniversalAssessmentModel, _batch_solution_prompt, _batch_evaluation_prompt


def public_question():
    return {"stimulus": {"rendered_text": "成本为2、3、1、5。"},
            "task": {"rendered_text": "求总成本"}, "input_contract": {"mode": "structured_fields"},
            "solver_contract": {"expression": "AUTHOR_HINT_8"},
            "provenance": {"private": "AUTHOR_INTERNAL_METADATA"}}


async def test_single_solver_sees_public_problem_without_author_hint(monkeypatch):
    captured = {}
    async def call(self, policy, prompt, **kwargs):
        captured["prompt"] = prompt
        return json.dumps({"answer": 11})
    monkeypatch.setattr(UniversalAssessmentModel, "_assessment_llm_call", call)
    await UniversalAssessmentModel().solve_candidate(public_question())
    assert "AUTHOR_HINT" not in captured["prompt"]
    assert "AUTHOR_INTERNAL" not in captured["prompt"]
    schema = captured["prompt"].split("只输出JSON：", 1)[1].split("。\n", 1)[0]
    assert list(json.loads(schema))[0] == "work"
    assert list(json.loads(schema))[-1] == "answer"


def test_batch_solver_has_the_same_public_only_work_first_contract():
    prompt = _batch_solution_prompt([{"slot_id": "s", "question_spec": public_question()}])
    assert "AUTHOR_HINT" not in prompt and "AUTHOR_INTERNAL" not in prompt
    schema = json.loads(prompt.split("<REQUIRED_OUTPUT_SCHEMA>\n")[1].split("\n</REQUIRED_OUTPUT_SCHEMA>")[0])
    assert list(schema["solutions"][0]["solution"])[0] == "work"
    assert list(schema["solutions"][0]["solution"])[-1] == "answer"


def test_ordinary_review_does_not_invent_atomic_counterfactual_or_leak_solver_hint():
    prompt = _batch_evaluation_prompt([{"slot_id": "s", "question_spec": public_question(), "slot": {}}])
    assert "AUTHOR_HINT" not in prompt and "AUTHOR_INTERNAL" not in prompt
    envelope = json.loads(prompt.split("<REQUIRED_OUTPUT_ENVELOPE>\n")[1].split("\n</REQUIRED_OUTPUT_ENVELOPE>")[0])
    witness = envelope["reports"][0]["report"]["review_witness"]
    assert "observation_test" not in witness
    assert "delivery_checks" in witness
    assert "hypothetical skipped loop" not in prompt


def test_atomic_review_keeps_its_counterfactual_evidence_contract():
    prompt = _batch_evaluation_prompt([{"slot_id": "s", "question_spec": public_question(),
        "slot": {"assessment_binding_schema": "atomic_assessment_v1"}}])
    schema = json.loads(prompt.split("<REQUIRED_OUTPUT_ENVELOPE>\n")[1].split("\n</REQUIRED_OUTPUT_ENVELOPE>")[0])
    assert "observation_test" in schema["reports"][0]["report"]["review_witness"]
