import json
from copy import deepcopy

import pytest

from assessment_generation_policy import resolve_assessment_generation_policy
from assessment_orchestrator import UniversalAssessmentModel


def context(slot_id="slot-a"):
    return {"assessment_slot": {"slot_id": slot_id, "assessment_binding_schema": "atomic_assessment_v1",
                                "input_mode": "choice", "knowledge": ["目标规则"]}}


def plan():
    return {"public_material": "给定输入5", "ask": "结果是多少？", "target_rule": "目标规则",
            "incorrect_rule": "仅改变目标规则", "correct_prediction": "2", "incorrect_prediction": "3",
            "trace": "保持输入5，分别得到2和3", "options": ["2", "3"]}


@pytest.mark.asyncio
async def test_atomic_generator_designs_before_rendering_without_mutating_context():
    model = object.__new__(UniversalAssessmentModel)
    seen = []
    async def call(policy, prompt, **kwargs):
        seen.append((policy.stage, prompt))
        if policy.stage == "design":
            return json.dumps({"plans": [{"slot_id": "slot-a", "plan": plan()}]})
        return json.dumps({"question_spec": {}, "solution": {}})
    model._assessment_llm_call = call
    ctx = context()
    before = deepcopy(ctx)
    result = await model.generate_candidate(ctx, call_policy=resolve_assessment_generation_policy(None).call_policy("generate", ctx))
    assert [s for s, _ in seen] == ["design", "generate"]
    assert "private_measurement_design" in seen[1][1]
    assert result["solution"]["measurement_plan"]["correct_prediction"] == "2"
    assert ctx == before


@pytest.mark.asyncio
async def test_legacy_generator_does_not_add_design_call():
    model = object.__new__(UniversalAssessmentModel)
    stages = []
    async def call(policy, prompt, **kwargs):
        stages.append(policy.stage)
        return '{"question_spec":{},"solution":{}}'
    model._assessment_llm_call = call
    await model.generate_candidate({}, call_policy=resolve_assessment_generation_policy(None).call_policy("generate"))
    assert stages == ["generate"]


def test_design_mapping_rejects_cross_slot_or_duplicate_plans():
    from assessment_measurement_design import attach_measurement_designs
    from ai_base import AIProviderRequestError
    for entries in ([], [{"slot_id": "other", "plan": plan()}],
                    [{"slot_id": "slot-a", "plan": plan()}] * 2):
        with pytest.raises(AIProviderRequestError):
            attach_measurement_designs([context()], {"plans": entries})


def test_recovery_routes_by_failed_artifact_not_by_knowledge_id():
    from assessment_measurement_design import evidence_recovery_action
    assert evidence_recovery_action(["TRACE_CONTROL_STRUCTURE_CHANGED"], validation_passed=True) == "review"
    assert evidence_recovery_action(["EXPLANATION_OPERATOR_FIXITY_ERROR"], validation_passed=True) == "solve"
    assert evidence_recovery_action(["ANSWER_RULE_DISCLOSED"], validation_passed=True) == "author"
    assert evidence_recovery_action(["TRACE_CONTROL_STRUCTURE_CHANGED"], validation_passed=False) == "author"
    assert evidence_recovery_action(["OBSERVATION_NOT_DISCRIMINATING"], validation_passed=True) == "author"
