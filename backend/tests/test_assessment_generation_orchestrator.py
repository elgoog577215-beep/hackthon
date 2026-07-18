from __future__ import annotations

from assessment_orchestrator import AssessmentGenerationOrchestrator
from question_bank import build_question_bank


def _course() -> dict:
    return {
        "course_id": "course-orchestrator",
        "course_name": "热力学",
        "course_purpose": "systematic",
        "difficulty": "intermediate",
        "subject_pedagogy_profile": {
            "primary_mode": "natural_science",
            "user_locked": True,
        },
        "generation_request": {
            "course_purpose": "systematic",
            "web_question_enrichment": {"enabled": False},
        },
        "material_bindings": [],
        "evidence_catalog": [],
        "nodes": [{
            "node_id": "thermo-1",
            "node_level": 2,
            "node_name": "热力学第一定律",
            "node_content": (
                "封闭系统吸收热量 Q=20 kJ，同时对外做功 W=8 kJ。"
                "采用 ΔU=Q-W，能量均以 kJ 计，并检查能量守恒。"
            ),
            "learning_objective": "使用热力学第一定律计算内能变化",
            "key_points": ["能量守恒", "热力学第一定律"],
            "assessment": ["列式计算内能变化并核对单位"],
            "grounding_contract": {"question_evidence_ids": []},
            "difficulty_contract": {"target_level": "intermediate"},
        }],
    }


class RepairingModel:
    def __init__(self) -> None:
        self.generate_calls = 0
        self.solve_calls = 0
        self.repair_calls = 0
        self.solve_payloads: list[dict] = []

    async def generate_candidate(self, context: dict) -> dict:
        self.generate_calls += 1
        return _proposal(10)

    async def solve_candidate(self, public_question_spec: dict) -> dict:
        self.solve_calls += 1
        self.solve_payloads.append(public_question_spec)
        return {"answer": {"value": 12, "unit": "kJ"}}

    async def repair_candidate(
        self,
        context: dict,
        candidate: dict,
        validation: dict,
    ) -> dict:
        self.repair_calls += 1
        return _proposal(12)


class DisagreeingModel(RepairingModel):
    async def repair_candidate(
        self,
        context: dict,
        candidate: dict,
        validation: dict,
    ) -> dict:
        self.repair_calls += 1
        return _proposal(11)


def _proposal(answer: float) -> dict:
    return {
        "question_spec": {
            "stimulus": {
                "kind": "numeric_calculation",
                "data": {
                    "heat": {"value": 20, "unit": "kJ"},
                    "work": {"value": 8, "unit": "kJ"},
                },
                "rendered_text": (
                    "封闭系统吸收热量20 kJ，并对外做功8 kJ。"
                ),
            },
            "task": {
                "action": "calculate",
                "rendered_text": (
                    "采用 ΔU=Q-W 计算内能变化，写出代入过程并核对单位。"
                ),
                "deliverable": "计算过程、内能变化与单位检查",
            },
            "constraints": [
                "热量流入取正",
                "系统对外做功取正",
            ],
            "response_contract": {
                "format": "numeric_with_unit",
                "required_parts": ["formula", "work", "answer", "unit_check"],
            },
        },
        "solution": {
            "validation_mode": "numeric_unit_validator",
            "canonical_answer": {"value": answer, "unit": "kJ"},
            "rubric": ["列式正确", "数值正确", "单位正确"],
            "validator_config": {
                "absolute_tolerance": 0.01,
                "relative_tolerance": 0.001,
            },
            "solution_graph": {
                "schema_version": "solution_graph_v1",
                "steps": [{
                    "step_id": "sign",
                    "action": "根据约定确定热量与功的正负号",
                    "check": "Q=+20 kJ，W=+8 kJ",
                }, {
                    "step_id": "substitute",
                    "action": "代入 ΔU=Q-W",
                    "check": "两个量使用相同单位",
                }, {
                    "step_id": "verify",
                    "action": "检查结果和能量守恒",
                    "check": "ΔU+W=Q",
                }],
            },
        },
    }


async def test_orchestrator_uses_one_explicit_repair_and_isolates_solver():
    model = RepairingModel()
    orchestrator = AssessmentGenerationOrchestrator(model=model)

    prepared = await orchestrator.prepare_course(_course())

    assert model.generate_calls == 3
    assert model.solve_calls == 6
    assert model.repair_calls == 3
    assert all(
        "canonical_answer" not in repr(payload)
        and "solution" not in payload
        for payload in model.solve_payloads
    )
    contracts = prepared["_assessment_generated_contracts"]["thermo-1"]
    assert set(contracts) == {
        "concept_check",
        "objective_practice",
        "mastery_check",
    }
    assert all(
        contract["solution_envelope"]["canonical_answer"]
        == {"value": 12, "unit": "kJ"}
        for contract in contracts.values()
    )
    assert all(
        contract["solution_validation"]["auto_publish_eligible"]
        is True
        for contract in contracts.values()
    )
    assert prepared["_assessment_generation_audit"]["repair_calls"] == 3


async def test_second_disagreement_stops_and_forces_teacher_review():
    model = DisagreeingModel()
    orchestrator = AssessmentGenerationOrchestrator(model=model)

    prepared = await orchestrator.prepare_course(_course())
    contract = prepared["_assessment_generated_contracts"][
        "thermo-1"
    ]["objective_practice"]

    assert model.generate_calls == 3
    assert model.repair_calls == 3
    assert model.solve_calls == 6
    assert contract["review_required"] is True
    assert (
        contract["solution_validation"]["auto_publish_eligible"]
        is False
    )
    assert {
        issue["code"]
        for issue in contract["solution_validation"]["issues"]
    } == {"independent_solution_mismatch"}


async def test_prepared_contracts_drive_real_question_bank_items():
    model = RepairingModel()
    prepared = await AssessmentGenerationOrchestrator(
        model=model
    ).prepare_course(_course())

    bundle = build_question_bank(prepared)
    generated = [
        item
        for item in bundle["items"]
        if item.get("assessment_role") == "practice"
    ]

    assert len(generated) == 3
    assert all("20 kJ" in item["prompt"] for item in generated)
    assert all(
        item["validation_mode"] == "numeric_unit_validator"
        for item in generated
    )
    assert all(
        bundle["solution_envelopes"][
            item["solution_revision_id"]
        ]["canonical_answer"] == {"value": 12, "unit": "kJ"}
        for item in generated
    )
