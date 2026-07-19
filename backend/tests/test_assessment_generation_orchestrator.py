from __future__ import annotations

import asyncio
from copy import deepcopy

from ai_base import AIProviderRequestError
from assessment_orchestrator import (
    AssessmentGenerationOrchestrator,
    UniversalAssessmentModel,
    _SemanticEvaluationBatcher,
)
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
            "web_question_enrichment": {"mode": "off"},
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
        return _proposal(10, context)

    async def solve_candidate(
        self,
        public_question_spec: dict,
    ) -> dict:
        self.solve_calls += 1
        self.solve_payloads.append(public_question_spec)
        mode = (
            public_question_spec.get("input_contract") or {}
        ).get("mode")
        if mode == "choice":
            return {"answer": "A"}
        if mode == "structured_fields":
            return {
                "answer": {
                    "rubric_scores": {
                        "完成任务并给出可复核证据": 1.0,
                    },
                    "confidence": 0.95,
                }
            }
        return {"answer": {"value": 12, "unit": "kJ"}}

    async def repair_candidate(
        self,
        context: dict,
        candidate: dict,
        validation: dict,
    ) -> dict:
        self.repair_calls += 1
        return _proposal(12, context)

    async def evaluate_candidate(
        self,
        public_question_spec: dict,
        independent_solution: dict,
        objective: dict,
        slot: dict,
    ) -> dict:
        return {
            "passed": True,
            "confidence": 0.95,
            "solution_consistent": True,
            "dimensions": {
                "curriculum_targeting": 20,
                "answerability_and_completeness": 15,
                "difficulty_fit": 10,
                "clarity": 5,
            },
            "evidence": ["题面明确包含章节目标"],
            "issues": [],
        }


class BatchRepairingModel(RepairingModel):
    def __init__(self) -> None:
        super().__init__()
        self.batch_generate_calls = 0
        self.batch_evaluate_calls = 0

    async def generate_candidate_batch(
        self,
        contexts: list[dict],
    ) -> dict[str, dict]:
        self.batch_generate_calls += 1
        return {
            context["assessment_slot"]["slot_id"]: _proposal(
                12,
                context,
            )
            for context in contexts
        }

    async def evaluate_candidate_batch(
        self,
        items: list[dict],
    ) -> dict[str, dict]:
        self.batch_evaluate_calls += 1
        return {
            item["slot_id"]: {
                "passed": True,
                "confidence": 0.95,
                "solution_consistent": True,
                "dimensions": {
                    "curriculum_targeting": 20,
                    "answerability_and_completeness": 15,
                    "difficulty_fit": 10,
                    "clarity": 5,
                },
                "evidence": ["题面明确包含章节目标"],
                "issues": [],
            }
            for item in items
        }


class FlakySolverBatchModel(BatchRepairingModel):
    def __init__(self) -> None:
        super().__init__()
        self.solve_attempts = 0

    async def solve_candidate(
        self,
        public_question_spec: dict,
    ) -> dict:
        self.solve_attempts += 1
        if self.solve_attempts == 1:
            raise AIProviderRequestError(
                "invalid_independent_solution_json"
            )
        return await super().solve_candidate(
            public_question_spec
        )


class DisagreeingModel(RepairingModel):
    async def repair_candidate(
        self,
        context: dict,
        candidate: dict,
        validation: dict,
    ) -> dict:
        self.repair_calls += 1
        return _proposal(11, context)


class MalformedThenValidModel(RepairingModel):
    async def generate_candidate(self, context: dict) -> dict:
        self.generate_calls += 1
        if self.generate_calls == 1:
            proposal = _proposal(12, context)
            proposal["question_spec"]["stimulus"] = "not-an-object"
            return proposal
        return _proposal(12, context)


class ConcurrencyTrackingModel(RepairingModel):
    def __init__(self) -> None:
        super().__init__()
        self.active_generations = 0
        self.max_active_generations = 0

    async def generate_candidate(self, context: dict) -> dict:
        self.generate_calls += 1
        self.active_generations += 1
        self.max_active_generations = max(
            self.max_active_generations,
            self.active_generations,
        )
        try:
            await asyncio.sleep(0.02)
            return _proposal(12, context)
        finally:
            self.active_generations -= 1


class LongTaskThenRepairModel(RepairingModel):
    async def generate_candidate(self, context: dict) -> dict:
        self.generate_calls += 1
        proposal = _proposal(10, context)
        if (
            context["assessment_slot"]["practice_level"]
            == "mastery_check"
        ):
            proposal["question_spec"]["task"][
                "rendered_text"
            ] = "过长任务说明" * 80
        return proposal


def _proposal(answer: float, context: dict) -> dict:
    slot = context["assessment_slot"]
    mode = slot["input_mode"]
    validation_mode = slot["validation_mode"]
    practice_level = slot["practice_level"]
    objective = context["objective"]["objective"]
    options = (
        [
            {"id": "A", "label": "系统吸热且对外做功"},
            {"id": "B", "label": "系统既不吸热也不做功"},
        ]
        if mode == "choice"
        else []
    )
    canonical_answer = (
        "A"
        if mode == "choice"
        else (
            {"rubric": ["完成任务并给出可复核证据"]}
            if mode == "structured_fields"
            else {"value": answer, "unit": "kJ"}
        )
    )
    validator_config = (
        {
            "pass_score": 0.7,
            "confidence_threshold": 0.85,
            "rubric": ["完成任务并给出可复核证据"],
        }
        if mode == "structured_fields"
        else {
            "absolute_tolerance": 0.01,
            "relative_tolerance": 0.001,
        }
    )
    return {
        "question_spec": {
            "stimulus": {
                "kind": slot["archetype_id"],
                "data": {
                    "heat": {"value": 20, "unit": "kJ"},
                    "work": {"value": 8, "unit": "kJ"},
                },
                "rendered_text": (
                    f"{objective}（{practice_level}）："
                    "封闭系统吸收热量20 kJ，并对外做功8 kJ。"
                ),
            },
            "task": {
                "action": "calculate",
                "rendered_text": (
                    "采用 ΔU=Q-W 完成蓝图规定的作答，"
                    f"写出过程并核对单位和结论；层级为{practice_level}。"
                ),
                "deliverable": "过程、答案和结果检查",
            },
            "constraints": [
                "热量流入取正",
                "系统对外做功取正",
            ],
            "response_contract": {
                "format": slot["response_format"],
                "required_parts": [
                    "work",
                    "answer",
                    "result_check",
                ],
            },
            "options": options,
        },
        "solution": {
            "validation_mode": validation_mode,
            "canonical_answer": canonical_answer,
            "rubric": [
                "完成任务并给出可复核证据",
            ],
            "validator_config": validator_config,
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


async def test_orchestrator_uses_bounded_repair_and_isolates_solver():
    model = RepairingModel()
    prepared = await AssessmentGenerationOrchestrator(
        model=model
    ).prepare_course(_course())

    assert model.generate_calls == 3
    assert model.solve_calls == 4
    assert model.repair_calls == 1
    assert all(
        "canonical_answer" not in repr(payload)
        and "solution" not in payload
        for payload in model.solve_payloads
    )
    contracts = prepared["_assessment_generated_contracts"][
        "thermo-1"
    ]
    assert set(contracts) == {
        "concept_check",
        "objective_practice",
        "mastery_check",
    }
    assert contracts["objective_practice"][
        "solution_envelope"
    ]["canonical_answer"] == {"value": 12, "unit": "kJ"}
    assert all(
        contract["quality_report"]["score"] >= 85
        for contract in contracts.values()
    )
    audit = prepared["_assessment_generation_audit"]
    assert audit["repair_calls"] == 1
    assert audit["max_repairs_per_question"] == 3
    assert audit["schema_version"] == "question_generation_audit_v2"


async def test_three_disagreements_discard_only_failed_slot():
    model = DisagreeingModel()
    prepared = await AssessmentGenerationOrchestrator(
        model=model
    ).prepare_course(_course())
    contract = prepared["_assessment_generated_contracts"][
        "thermo-1"
    ]["objective_practice"]

    assert model.generate_calls == 3
    assert model.repair_calls == 3
    assert model.solve_calls == 6
    assert contract["generation_status"] == "discarded"
    audit_item = next(
        item
        for item in prepared["_assessment_generation_audit"][
            "items"
        ]
        if item["practice_level"] == "objective_practice"
    )
    assert len(audit_item["attempts"]) == 4
    assert audit_item["final_decision"] == "discard"


async def test_prepared_contracts_drive_diverse_question_bank_items():
    prepared = await AssessmentGenerationOrchestrator(
        model=RepairingModel()
    ).prepare_course(_course())

    bundle = build_question_bank(prepared)
    generated = [
        item
        for item in bundle["items"]
        if item.get("assessment_role") == "practice"
    ]

    assert len(generated) == 3
    assert all("20 kJ" in item["prompt"] for item in generated)
    assert {
        item["input_contract"]["mode"]
        for item in generated
    } == {"choice", "numeric_unit", "structured_fields"}
    numeric = next(
        item
        for item in generated
        if item["input_contract"]["mode"] == "numeric_unit"
    )
    assert bundle["solution_envelopes"][
        numeric["solution_revision_id"]
    ]["canonical_answer"] == {"value": 12, "unit": "kJ"}
    assert bundle["assessment_blueprint"][
        "schema_version"
    ] == "course_assessment_blueprint_v2"


async def test_malformed_nested_candidate_is_regenerated_not_discarded():
    model = MalformedThenValidModel()

    prepared = await AssessmentGenerationOrchestrator(
        model=model
    ).prepare_course(_course())

    audit = prepared["_assessment_generation_audit"]
    assert audit["failure_count"] == 0
    assert model.generate_calls == 4
    first = audit["items"][0]
    assert first["attempts"][0]["issue_codes"] == [
        "MODEL_OUTPUT_SCHEMA_INVALID"
    ]
    assert first["final_decision"] == "publish"


async def test_slots_generate_with_bounded_concurrency(monkeypatch):
    monkeypatch.setenv("ASSESSMENT_SLOT_CONCURRENCY", "2")
    model = ConcurrencyTrackingModel()

    prepared = await AssessmentGenerationOrchestrator(
        model=model
    ).prepare_course(_course())

    assert model.max_active_generations == 2
    assert set(
        prepared["_assessment_generated_contracts"]["thermo-1"]
    ) == {
        "concept_check",
        "objective_practice",
        "mastery_check",
    }
    assert prepared["_assessment_generation_audit"][
        "failure_count"
    ] == 0


async def test_node_uses_one_batch_generation_call_when_supported():
    model = BatchRepairingModel()

    prepared = await AssessmentGenerationOrchestrator(
        model=model
    ).prepare_course(_course())

    audit = prepared["_assessment_generation_audit"]
    assert model.batch_generate_calls == 1
    assert model.batch_evaluate_calls == 1
    assert model.generate_calls == 1
    assert model.solve_calls == 3
    assert audit["batch_generation_calls"] == 1
    assert audit["batch_generation_fallback_count"] == 0
    assert audit["batch_semantic_evaluation_calls"] == 1
    assert audit["batch_semantic_fallback_count"] == 0
    assert audit["generation_calls"] == 2
    assert audit["model_call_count"] == 6
    assert len(audit["call_timings"]) == 6
    assert {
        timing["role"]
        for timing in audit["call_timings"]
    } == {"generator", "solver", "reviewer"}
    assert all(
        timing["duration_ms"] >= 0
        for timing in audit["call_timings"]
    )


async def test_semantic_batcher_coalesces_two_open_reviews():
    model = BatchRepairingModel()
    audit = {
        "semantic_evaluation_calls": 0,
        "batch_semantic_evaluation_calls": 0,
        "batch_semantic_fallback_count": 0,
        "call_timings": [],
    }
    batcher = _SemanticEvaluationBatcher(
        model=model,
        audit=audit,
        max_wait_seconds=1,
    )

    async def review(slot_id: str) -> dict:
        return await batcher.evaluate(
            contract={
                "question_spec": {
                    "task": {"rendered_text": slot_id},
                },
            },
            independent={
                "answer": {"confidence": 0.95},
                "checks": [],
            },
            objective={"objective_id": "objective-1"},
            slot={"slot_id": slot_id},
        )

    first, second = await asyncio.gather(
        review("open-1"),
        review("open-2"),
    )

    assert first["passed"] is True
    assert second["passed"] is True
    assert model.batch_evaluate_calls == 1
    assert audit["semantic_evaluation_calls"] == 1
    assert audit["batch_semantic_evaluation_calls"] == 1
    assert audit["batch_semantic_fallback_count"] == 0
    assert audit["call_timings"][0]["batch_size"] == 2


async def test_solver_format_retry_keeps_generated_candidate():
    model = FlakySolverBatchModel()

    prepared = await AssessmentGenerationOrchestrator(
        model=model
    ).prepare_course(_course())

    audit = prepared["_assessment_generation_audit"]
    assert audit["independent_solution_calls"] == 4
    assert audit["independent_solution_retry_count"] == 1
    assert audit["generation_calls"] == 2
    assert audit["repair_calls"] == 0
    assert audit["failure_count"] == 0
    assert any(
        timing["operation"]
        == "independent_solve_format_retry"
        for timing in audit["call_timings"]
    )


async def test_task_length_preflight_repairs_before_independent_solving():
    model = LongTaskThenRepairModel()

    prepared = await AssessmentGenerationOrchestrator(
        model=model
    ).prepare_course(_course())

    mastery = next(
        item
        for item in prepared["_assessment_generation_audit"]["items"]
        if item["practice_level"] == "mastery_check"
    )
    assert mastery["attempts"][0]["issue_codes"] == ["TASK_TOO_LONG"]
    assert mastery["attempts"][0]["next_action"] == "repair"
    assert model.repair_calls == 2
    assert model.solve_calls == 4
    assert mastery["final_decision"] == "publish"


async def test_choice_generation_uses_fast_non_thinking_json_mode(
    monkeypatch,
):
    captured = {}
    model = UniversalAssessmentModel()

    async def fake_call(prompt, **kwargs):
        captured.update(kwargs)
        return '{"question_spec": {}, "solution": {}}'

    monkeypatch.setattr(model, "_call_llm", fake_call)

    await model.generate_candidate({
        "assessment_slot": {"input_mode": "choice"},
    })

    assert captured["use_fast_model"] is True
    assert captured["enable_thinking"] is False
    assert captured["json_mode"] is True
    assert captured["max_tokens"] == 2048


async def test_scoped_orchestration_only_calls_models_for_requested_nodes():
    course = _course()
    second = deepcopy(course["nodes"][0])
    second.update({
        "node_id": "thermo-2",
        "node_name": "热力学第二定律",
        "learning_objective": "判断热过程方向并说明熵变依据",
    })
    course["nodes"].append(second)
    model = RepairingModel()
    progress_events: list[dict] = []

    async def record_progress(event: dict) -> None:
        progress_events.append(event)

    prepared = await AssessmentGenerationOrchestrator(
        model=model
    ).prepare_course(
        course,
        node_ids=["thermo-2"],
        on_progress=record_progress,
    )

    assert set(prepared["_assessment_generated_contracts"]) == {
        "thermo-2",
    }
    assert model.generate_calls == 3
    assert model.solve_calls == 4
    assert model.repair_calls == 1
    assert [event["completed_items"] for event in progress_events] == [
        1,
        2,
        3,
    ]
    assert all(event["total_items"] == 3 for event in progress_events)
    assert all(
        event["node_id"] == "thermo-2"
        for event in progress_events
    )
