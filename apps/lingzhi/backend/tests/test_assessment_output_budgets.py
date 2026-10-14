import pytest

from assessment_orchestrator import UniversalAssessmentModel
from assessment_generation_policy import resolve_assessment_generation_policy


@pytest.mark.parametrize("stage", ["generate", "repair", "solve", "review"])
@pytest.mark.parametrize("floor", [0, 10000])
async def test_structured_output_budget_is_not_reduced_by_thinking_switch_or_batch(monkeypatch, stage, floor):
    monkeypatch.setenv("ASSESSMENT_MIN_OUTPUT_TOKENS", str(floor))
    monkeypatch.setenv("AI_THINKING_ENABLED", "false")
    model = UniversalAssessmentModel()
    calls = []
    async def call(prompt, **kwargs):
        calls.append(kwargs)
        return ('{"question_spec":{},"solution":{},"answer":{},"passed":true,'
                '"candidates":[{"slot_id":"s","candidate":{}}],'
                '"repairs":[{"slot_id":"s","candidate":{}}],'
                '"solutions":[{"slot_id":"s","solution":{"answer":{}}}],'
                '"reports":[{"slot_id":"s","report":{"passed":true}}]}')
    monkeypatch.setattr(model, "_call_llm", call)
    spec = {"input_contract": {"mode": "structured_fields"}}
    slot = {"slot_id": "s", "input_mode": "structured_fields"}
    context = {"assessment_slot": slot}
    policy = resolve_assessment_generation_policy("complete").call_policy(stage, context)
    if stage == "generate":
        await model.generate_candidate(context, call_policy=policy)
        await model.generate_candidate_batch([context, context], call_policy=policy)
    elif stage == "repair":
        await model.repair_candidate(context, {}, {}, call_policy=policy)
        await model.repair_candidate_batch([{"slot_id": "s", "context": context}] * 2, call_policy=policy)
    elif stage == "solve":
        await model.solve_candidate(spec, call_policy=policy)
        await model.solve_candidate_batch([{"slot_id": "s", "question_spec": spec}] * 2, call_policy=policy)
    else:
        await model.evaluate_candidate(spec, {}, {}, slot, call_policy=policy)
        await model.evaluate_candidate_batch([{"slot_id": "s", "question_spec": spec, "slot": slot}] * 2, call_policy=policy)
    minimum = max(floor, 4096 if stage == "review" else 8192)
    assert calls[0]["max_tokens"] >= minimum
    assert calls[1]["max_tokens"] >= 2 * calls[0]["max_tokens"]
    assert all(call["reject_truncated"] and not call["enable_thinking"] for call in calls)
