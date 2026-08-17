from __future__ import annotations

import asyncio
from copy import deepcopy

import pytest

from ai_base import AIProviderRequestError
from assessment_orchestrator import (
    AssessmentGenerationOrchestrator,
    UniversalAssessmentModel,
    _batch_generation_prompt,
    _SemanticEvaluationBatcher,
)
from question_bank import approved_formal_tasks, build_question_bank


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
    # 假模型必须真的让出事件循环。
    #
    # 合批只在「有兄弟题同时在飞」时才发生，而零延迟的假模型不会让出控制权：
    # 第一个槽位一路跑完（生成→求解→评审→修复）都不 await 任何会挂起的东西，
    # 另外两个槽位根本还没开始，于是在飞数恒为 1。
    #
    # 旧用例之所以能测到合批，是因为当时的合批器**无条件等窗口**——那个等待
    # 本身制造了交错。现在按「有兄弟才合批」改掉之后，这个副作用没有了，
    # 假模型必须自己表达出真实存在的并发。
    _LATENCY = 0.01

    def __init__(self) -> None:
        self.generate_calls = 0
        self.solve_calls = 0
        self.repair_calls = 0
        self.solve_payloads: list[dict] = []

    async def generate_candidate(self, context: dict) -> dict:
        self.generate_calls += 1
        await asyncio.sleep(self._LATENCY)
        return _proposal(10, context)

    async def solve_candidate(
        self,
        public_question_spec: dict,
    ) -> dict:
        self.solve_calls += 1
        self.solve_payloads.append(public_question_spec)
        await asyncio.sleep(self._LATENCY)
        mode = (
            public_question_spec.get("input_contract") or {}
        ).get("mode")
        if mode == "choice":
            return {
                "answer": "A",
                "summary": "根据热量与功的正负号约定逐项判断。",
                "work": ["系统吸热时Q取正，对外做功时W取正。"],
                "checks": ["所选记录同时满足两项符号约定"],
                "option_analysis": [
                    {
                        "option_id": "A",
                        "is_correct": True,
                        "explanation": "同时满足吸热为正、对外做功为正。",
                    },
                    {
                        "option_id": "B",
                        "is_correct": False,
                        "explanation": "与题面给出的吸热和做功过程矛盾。",
                    },
                ],
            }
        if mode == "structured_fields":
            return {
                "answer": {
                    "rubric_scores": {
                        "完成任务并给出可复核证据": 1.0,
                    },
                    "confidence": 0.95,
                },
                "summary": "比较两组能量记录并用守恒方程定位矛盾。",
                "work": ["分别代入ΔU=Q-W，比较记录值与计算值。"],
                "checks": ["修正后满足ΔU+W=Q"],
            }
        return {
            "answer": {"value": 12, "unit": "kJ"},
            "summary": "先统一符号和单位，再代入热力学第一定律。",
            "work": ["代入ΔU=Q-W=20 kJ-8 kJ=12 kJ。"],
            "checks": ["回代得到ΔU+W=20 kJ=Q"],
        }

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


class ProfileAwareBatchModel(BatchRepairingModel):
    def __init__(self) -> None:
        super().__init__()
        self.generation_batch_sizes: list[int] = []
        self.solve_batch_sizes: list[int] = []
        self.call_policies: list[object] = []

    async def generate_candidate_batch(
        self,
        contexts: list[dict],
        *,
        call_policy=None,
    ) -> dict[str, dict]:
        self.batch_generate_calls += 1
        self.generation_batch_sizes.append(len(contexts))
        self.call_policies.append(call_policy)
        return {
            context["assessment_slot"]["slot_id"]: _proposal(
                12,
                context,
            )
            for context in contexts
        }

    async def solve_candidate(
        self,
        public_question_spec: dict,
        *,
        call_policy=None,
    ) -> dict:
        self.call_policies.append(call_policy)
        return await super().solve_candidate(public_question_spec)

    async def solve_candidate_batch(
        self,
        items: list[dict],
        *,
        call_policy=None,
    ) -> dict[str, dict]:
        self.solve_batch_sizes.append(len(items))
        self.call_policies.append(call_policy)
        return {
            str(item["slot_id"]): await super().solve_candidate(
                item["question_spec"]
            )
            for item in items
        }


class BatchRepairAwareModel(ProfileAwareBatchModel):
    def __init__(self) -> None:
        super().__init__()
        self.repair_batch_sizes: list[int] = []

    async def generate_candidate_batch(
        self,
        contexts: list[dict],
        *,
        call_policy=None,
    ) -> dict[str, dict]:
        generated = await super().generate_candidate_batch(
            contexts,
            call_policy=call_policy,
        )
        for candidate in generated.values():
            candidate["question_spec"]["task"]["rendered_text"] = (
                "过长任务说明" * 80
            )
        return generated

    async def repair_candidate_batch(
        self,
        items: list[dict],
        *,
        call_policy=None,
    ) -> dict[str, dict]:
        self.repair_batch_sizes.append(len(items))
        self.call_policies.append(call_policy)
        return {
            str(item["slot_id"]): _proposal(12, item["context"])
            for item in items
        }


class PartialBatchRepairModel(BatchRepairAwareModel):
    async def repair_candidate_batch(
        self,
        items: list[dict],
        *,
        call_policy=None,
    ) -> dict[str, dict]:
        repaired = await super().repair_candidate_batch(
            items,
            call_policy=call_policy,
        )
        first_slot_id = str(items[0]["slot_id"])
        return {first_slot_id: repaired[first_slot_id]}


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
            {
                "rubric_scores": {
                    "完成任务并给出可复核证据": 1.0,
                },
                "confidence": 0.95,
            }
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
    materials = {
        "concept_check": (
            "系统吸热时 Q 取正，系统对外做功时 W 取正。"
            "现需判断一组热量与功的符号记录是否符合约定。"
        ),
        "objective_practice": (
            "封闭系统吸收热量20 kJ，并对外做功8 kJ。"
        ),
        "mastery_check": (
            "工程师给出两个封闭系统过程的能量审计表，"
            "其中一个过程不满足能量守恒，需要定位并修正。"
        ),
    }
    tasks = {
        "concept_check": "选择唯一符合热量与功符号约定的记录。",
        "objective_practice": (
            "采用 ΔU=Q-W 计算内能变化，写出过程并核对单位。"
        ),
        "mastery_check": (
            "比较两个过程，指出矛盾记录并给出修正后的守恒检查。"
        ),
    }
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
                    f"{materials[practice_level]}"
                ),
            },
            "task": {
                "action": "calculate",
                "rendered_text": (
                    tasks[practice_level]
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
            "worked_solution": {
                "schema_version": "worked_solution_v1",
                "summary": (
                    "根据符号约定，代入热力学第一定律并检查能量守恒。"
                ),
                "steps": [{
                    "title": "确定符号",
                    "explanation": "系统吸热时Q为正，对外做功时W为正。",
                    "result": "Q=+20 kJ，W=+8 kJ",
                }, {
                    "title": "代入计算",
                    "explanation": "将热量和功代入ΔU=Q-W。",
                    "calculation": "ΔU=20-8=12 kJ",
                    "result": "内能增加12 kJ",
                }],
                "final_answer": canonical_answer,
                "checks": ["回代验证ΔU+W=Q"],
                "option_analysis": (
                    [{
                        "option_id": "A",
                        "is_correct": True,
                        "explanation": "同时满足吸热和对外做功的符号约定。",
                    }, {
                        "option_id": "B",
                        "is_correct": False,
                        "explanation": "与题面给出的能量交换过程矛盾。",
                    }]
                    if mode == "choice"
                    else []
                ),
                "common_errors": ["把系统对外做功误记为负值。"],
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
    assert audit["first_pass_pass_count"] == 2
    assert audit["first_pass_pass_rate"] == pytest.approx(2 / 3, abs=0.001)


async def test_orchestrator_generates_only_rejected_practice_slots():
    model = RepairingModel()
    prepared = await AssessmentGenerationOrchestrator(
        model=model
    ).prepare_course(
        _course(),
        node_ids=["thermo-1"],
        practice_levels_by_node={"thermo-1": ["concept_check"]},
    )

    contracts = prepared["_assessment_generated_contracts"]["thermo-1"]
    assert set(contracts) == {"concept_check"}
    assert model.generate_calls == 1
    assert prepared["_assessment_generation_audit"]["planned_item_count"] == 1


async def test_three_disagreements_discard_only_failed_slot():
    model = DisagreeingModel()
    prepared = await AssessmentGenerationOrchestrator(
        model=model
    ).prepare_course(_course())
    contract = prepared["_assessment_generated_contracts"][
        "thermo-1"
    ]["objective_practice"]

    # G3：按题的模型求解预算止住了「一道病态题反复求解」的循环。
    #
    # 改动前 generate 3 + repair 3 + solve 6 = 12 次模型调用，最后仍然 discard。
    # 独立求解承担真实的正确性验证，所以不能删；但也不该无上限重试。现在求解
    # 用满 3 次预算即停，转人工复核——结论相同（discard），求解从 6 降到 5，
    # 且第 4 轮不再白跑一次求解。
    assert model.generate_calls == 3
    assert model.repair_calls == 3
    assert model.solve_calls == 5
    assert model.solve_calls <= 6, "求解次数不得回退到无预算时的水平"
    assert contract["generation_status"] == "discarded"
    audit_item = next(
        item
        for item in prepared["_assessment_generation_audit"][
            "items"
        ]
        if item["practice_level"] == "objective_practice"
    )
    # 停在哪、为什么停，审计里要看得出来
    assert audit_item["model_solve_budget"] == {
        "used": 3,
        "limit": 3,
        "exhausted": True,
    }
    assert audit_item["attempts"][-1]["issue_codes"] == [
        "MODEL_SOLVE_BUDGET_EXHAUSTED"
    ]
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
    assert any("20 kJ" in item["prompt"] for item in generated)
    assert len({
        item["diversity_signature"]["material_digest"]
        for item in generated
    }) == 3
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
    assert numeric["design_brief_summary"][
        "schema_version"
    ] == "question_design_brief_v1"
    assert numeric["semantic_preflight"]["passed"] is True
    assert numeric["material_bindings"]
    assert "content_coverage" in bundle["reference_package"]
    assert "method_coverage" in bundle["reference_package"]
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


async def test_multiple_repair_nodes_generate_concurrently(monkeypatch):
    monkeypatch.setenv("ASSESSMENT_NODE_CONCURRENCY", "2")
    started_nodes: set[str] = set()
    both_started = asyncio.Event()

    class CrossNodeModel(RepairingModel):
        async def generate_candidate(self, context: dict) -> dict:
            objective_id = str(
                (context.get("assessment_slot") or {}).get("objective_id") or ""
            )
            started_nodes.add(objective_id)
            if len(started_nodes) == 2:
                both_started.set()
            await both_started.wait()
            return await super().generate_candidate(context)

    course = _course()
    second = deepcopy(course["nodes"][0])
    second["node_id"] = "thermo-2"
    second["node_name"] = "热力学第二小节"
    course["nodes"].append(second)
    chapter_events: list[dict] = []

    prepared = await asyncio.wait_for(
        AssessmentGenerationOrchestrator(
            model=CrossNodeModel(),
        ).prepare_course(
            course,
            node_ids=["thermo-1", "thermo-2"],
            on_chapter_complete=chapter_events.append,
        ),
        timeout=1,
    )

    assert len(started_nodes) == 2
    assert {event["node_id"] for event in chapter_events} == {
        "thermo-1",
        "thermo-2",
    }
    assert set(prepared["_assessment_generated_contracts"]) == {
        "thermo-1",
        "thermo-2",
    }
    assert all(
        set(contracts) == {
            "concept_check",
            "objective_practice",
            "mastery_check",
        }
        for contracts in prepared["_assessment_generated_contracts"].values()
    )


async def test_provider_quota_fallback_is_not_auto_published():
    class QuotaFailureModel(RepairingModel):
        async def generate_candidate(self, context: dict) -> dict:
            raise AIProviderRequestError("429 insufficient balance")

    chapter_events: list[dict] = []
    prepared = await AssessmentGenerationOrchestrator(
        model=QuotaFailureModel(),
    ).prepare_course(
        _course(),
        node_ids=["thermo-1"],
        practice_levels_by_node={"thermo-1": ["concept_check"]},
        on_chapter_complete=chapter_events.append,
    )

    contract = prepared["_assessment_generated_contracts"]["thermo-1"][
        "concept_check"
    ]
    audit = prepared["_assessment_generation_audit"]
    assert contract["generation_status"] == "discarded"
    assert contract["review_required"] is False
    assert "ai_validation_unavailable" in contract["risk_flags"]
    assert contract["solution_validation"]["passed"] is False
    assert contract["solution_validation"]["auto_publish_eligible"] is False
    assert contract["generation_degradation"]["teacher_review_recommended"] is True
    assert audit["fallback_count"] == 1
    assert audit["items"][0]["final_decision"] == "discard"
    assert chapter_events[0]["passed"] is False
    bank = build_question_bank(prepared)
    assert not any(
        item.get("generation_status") == "published"
        for item in bank["items"]
    )
    assert approved_formal_tasks(bank, assessment_role="practice") == []


async def test_node_uses_one_batch_generation_call_when_supported():
    model = BatchRepairingModel()

    prepared = await AssessmentGenerationOrchestrator(
        model=model
    ).prepare_course(_course())

    audit = prepared["_assessment_generation_audit"]
    assert model.batch_generate_calls == 1
    # 这一节里只有 mastery_check 一道题会触发语义评审，等它评审时另外两道
    # 已经做完了——在飞只剩它自己。此时进合批只会为一个永远不会来的兄弟
    # 白等一个窗口（默认 1 秒），所以直接走单条评审。
    #
    # 旧断言写的是 `batch_evaluate_calls == 1`，那记录的是当时"无条件等窗口、
    # 超时后发一条 batch_size=1 的合批调用"的行为：同样是一次模型请求，
    # 只是多等了一秒。改成有兄弟才合批之后，这里应当是单条。
    assert model.batch_evaluate_calls == 0
    assert audit["semantic_evaluation_calls"] == 1
    assert audit["semantic_batch_skipped_solo"] == 1
    assert model.generate_calls == 1
    assert model.solve_calls == 3
    assert audit["batch_generation_calls"] == 1
    assert audit["batch_generation_fallback_count"] == 0
    assert audit["batch_semantic_evaluation_calls"] == 0
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
        captured["prompt"] = prompt
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
    assert isinstance(captured["prompt"], str)
    assert "<REQUIRED_OUTPUT_SCHEMA>" in captured["prompt"]


async def test_scoped_orchestration_only_calls_models_for_requested_nodes():
    course = _course()
    second = deepcopy(course["nodes"][0])
    second.update({
        "node_id": "thermo-2",
        "node_name": "热力学第二定律",
        "learning_objective": "判断热过程方向并说明熵变依据",
    })
    course["nodes"].append(second)
    model = BatchRepairingModel()
    progress_events: list[dict] = []
    chapter_events: list[dict] = []

    async def record_progress(event: dict) -> None:
        progress_events.append(event)

    async def record_chapter(event: dict) -> None:
        chapter_events.append(event)

    prepared = await AssessmentGenerationOrchestrator(
        model=model
    ).prepare_course(
        course,
        node_ids=["thermo-2"],
        on_progress=record_progress,
        on_chapter_complete=record_chapter,
    )

    assert set(prepared["_assessment_generated_contracts"]) == {
        "thermo-2",
    }
    # M2：scoped_repair 也走批量首轮候选与合批评审。
    #
    # 改动前这里是 batch=0 / generate=3 / solve=4 / repair=1，共 8 次模型调用——
    # deliberate 档的 scoped_repair 落进全链路最慢的分支。而 scoped_repair 正是
    # 教师点了重建、正等着看结果的场景。现在同样的输入是 5 次。
    assert model.batch_generate_calls == 1
    assert model.generate_calls == 1
    assert model.solve_calls == 3
    assert model.repair_calls == 0
    assert (
        model.batch_generate_calls
        + model.generate_calls
        + model.solve_calls
        + model.repair_calls
    ) == 5, "scoped_repair 的模型调用数不得回退到批量化之前"
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
    assert len(chapter_events) == 1
    assert chapter_events[0]["node_id"] == "thermo-2"
    assert chapter_events[0]["passed"] is True
    assert set(chapter_events[0]["contracts"]) == {
        "concept_check",
        "objective_practice",
        "mastery_check",
    }
    assert len(chapter_events[0]["audit_items"]) == 3
    assert chapter_events[0]["audit_snapshot"][
        "assessment_generation_profile"
    ] == "deliberate"
    assert chapter_events[0]["audit_snapshot"][
        "assessment_generation_policy_version"
    ]
    assert chapter_events[0]["audit_snapshot"]["logical_call_count"] >= 1
    assert chapter_events[0]["audit_snapshot"]["wall_clock_ms"] >= 0


async def test_fast_profile_batches_three_candidates_and_two_simple_solutions():
    model = ProfileAwareBatchModel()

    prepared = await AssessmentGenerationOrchestrator(
        model=model
    ).prepare_course(
        _course(),
        generation_profile="fast",
        generation_scope="full_generation",
    )

    audit = prepared["_assessment_generation_audit"]
    assert model.generation_batch_sizes == [3]
    assert 2 in model.solve_batch_sizes
    assert model.generate_calls == 0
    assert audit["assessment_generation_profile"] == "fast"
    assert audit["assessment_generation_policy_version"]
    assert audit["max_generation_attempts_per_question"] == 2
    assert audit["max_repairs_per_question"] == 1
    assert audit["thinking_requested_call_count"] == 0
    assert all(
        timing.get("thinking_requested") is False
        for timing in audit["call_timings"]
    )


async def test_fast_profile_batches_all_failed_repairs_once():
    model = BatchRepairAwareModel()

    prepared = await AssessmentGenerationOrchestrator(
        model=model
    ).prepare_course(
        _course(),
        generation_profile="fast",
        generation_scope="full_generation",
    )

    audit = prepared["_assessment_generation_audit"]
    # 一次修复最多合 2 条，不是 3 条。
    #
    # `repair_candidate` 单条给每题 6144 输出预算，`repair_candidate_batch`
    # 给 min(12288, 4096*n)：n=2 时每题 6144 持平，n=3 时被 12288 截成
    # 4096/题——合批会**悄悄把修复的输出预算砍掉三分之一**。少发一次请求
    # 换质量下降，正是不允许的方向，所以按预算反推批量上限（见
    # `_REPAIR_BATCH_MAX_ITEMS`）。
    #
    # 于是三道题是「2 条合批 + 1 条走单条」，而不是一次 3 条。
    assert model.repair_batch_sizes == [2]
    assert model.repair_calls == 1
    assert audit["batch_repair_calls"] == 1
    assert audit["batch_repair_fallback_count"] == 0
    assert any(
        timing.get("operation") == "repair_batch"
        and timing.get("batch_size") == 2
        for timing in audit["call_timings"]
    )
    assert audit["failure_count"] == 0


async def test_lone_question_never_waits_for_a_batch_window():
    """只有一道题在飞时，不得进合批路径、不得等窗口。

    这是 `1e8fb290` 被回退的直接原因：合批器无条件等 `max_wait_seconds`，
    而真机形状是每小节 1 道题（40 节 × 1 题），窗口里永远只有一条——
    实测 99%（74/75）的"合批"只装了一道题，白等延迟还把每题输出预算从
    单条口径降到合批口径。

    断言用挂钟时间：单题整轮必须远小于一个合批窗口（修复 0.1s + 语义 1s），
    只数调用次数是抓不到"多等了一秒"的。
    """

    model = BatchRepairAwareModel()
    started = asyncio.get_running_loop().time()
    prepared = await AssessmentGenerationOrchestrator(
        model=model
    ).prepare_course(
        _course(),
        node_ids=["thermo-1"],
        practice_levels_by_node={"thermo-1": ["concept_check"]},
        generation_profile="fast",
        generation_scope="full_generation",
    )
    elapsed = asyncio.get_running_loop().time() - started

    audit = prepared["_assessment_generation_audit"]
    assert model.repair_batch_sizes == [], "单题不得走合批修复"
    assert model.solve_batch_sizes == [], "单题不得走合批求解"
    # 这一道题一次就过，没走到修复；被跳过的是求解合批。断言"至少有一处
    # 合批因为独苗而被跳过"，而不是钉死在具体哪一处。
    assert sum(
        int(audit.get(key) or 0)
        for key in (
            "repair_batch_skipped_solo",
            "solve_batch_skipped_solo",
            "semantic_batch_skipped_solo",
        )
    ) >= 1
    # 语义窗口默认 1 秒、修复窗口 0.1 秒；单题若还在等窗口这里必然超时。
    assert elapsed < 0.5, (
        f"单题整轮耗时 {elapsed:.3f}s，疑似仍在等合批窗口"
    )


async def test_solo_gate_holds_even_if_batch_windows_are_widened(
    monkeypatch,
):
    """把合批窗口调大 20 倍，单题该多快还多快。

    钉住的是「保护独苗的是 gate，不是窗口取值」。只断言默认配置下跑得快，
    等于默认窗口恰好很短时也能通过——以后有人把 `max_wait_seconds` 或
    `ASSESSMENT_SEMANTIC_BATCH_WAIT_SECONDS` 调大、同时把 gate 去掉，
    那种断言是抓不住的。这里反过来：**先把窗口调到明显能被观测的量级**
    （修复 2s、语义 3s），再要求单题整轮远小于它。gate 一旦失效，
    这道用例会以秒级超时的形式炸掉，而不是悄悄退化。
    """

    import assessment_orchestrator as orchestrator_module

    monkeypatch.setenv("ASSESSMENT_SEMANTIC_BATCH_WAIT_SECONDS", "3")
    original_init = orchestrator_module._CandidateRepairBatcher.__init__

    def widened_init(self, **kwargs):
        kwargs["max_wait_seconds"] = 2.0
        original_init(self, **kwargs)

    monkeypatch.setattr(
        orchestrator_module._CandidateRepairBatcher,
        "__init__",
        widened_init,
    )
    original_solve_init = (
        orchestrator_module._IndependentSolutionBatcher.__init__
    )

    def widened_solve_init(self, **kwargs):
        kwargs["max_wait_seconds"] = 2.0
        original_solve_init(self, **kwargs)

    monkeypatch.setattr(
        orchestrator_module._IndependentSolutionBatcher,
        "__init__",
        widened_solve_init,
    )

    model = BatchRepairAwareModel()
    started = asyncio.get_running_loop().time()
    await AssessmentGenerationOrchestrator(model=model).prepare_course(
        _course(),
        node_ids=["thermo-1"],
        practice_levels_by_node={"thermo-1": ["concept_check"]},
        generation_profile="fast",
        generation_scope="full_generation",
    )
    elapsed = asyncio.get_running_loop().time() - started

    assert model.repair_batch_sizes == []
    assert model.solve_batch_sizes == []
    # 窗口已被调到 2-3 秒；gate 有效时单题根本不该碰到它们。
    assert elapsed < 1.0, (
        f"单题整轮 {elapsed:.3f}s——窗口被调大后跟着变慢，"
        "说明保护独苗的不是 gate 而是窗口恰好很短"
    )


async def test_batch_never_shrinks_per_item_output_budget():
    """合批不得把每题的输出预算压到单条之下。

    修复单条给 6144，合批给 min(12288, 4096*n)：n=3 时每题只剩 4096。
    「少发一次请求」不能拿这个换——这正是不许放宽契约凑数字那条红线。
    """

    from assessment_orchestrator import _REPAIR_BATCH_MAX_ITEMS

    single_budget = 6144
    batch_ceiling = 12288
    assert _REPAIR_BATCH_MAX_ITEMS >= 1
    per_item = batch_ceiling // _REPAIR_BATCH_MAX_ITEMS
    assert per_item >= single_budget, (
        f"合批 {_REPAIR_BATCH_MAX_ITEMS} 条时每题只有 {per_item}，"
        f"低于单条的 {single_budget}"
    )


async def test_fast_batch_repair_is_atomic_when_a_slot_is_missing():
    prepared = await AssessmentGenerationOrchestrator(
        model=PartialBatchRepairModel()
    ).prepare_course(
        _course(),
        generation_profile="fast",
        generation_scope="full_generation",
    )

    contracts = prepared["_assessment_generated_contracts"]["thermo-1"]
    audit = prepared["_assessment_generation_audit"]
    # 合批修复缺槽位时，**这一批里的题**全部失败，不牵连没进这一批的题。
    #
    # 三道题现在是「2 条合批 + 1 条单条」（批量上限由输出预算反推，见
    # `_REPAIR_BATCH_MAX_ITEMS`）。模型只回了第一个 slot，于是那一批的 2 道
    # 整批判失败——原子性仍然成立；剩下那道走单条路径、不受这批影响，
    # 正常产出。旧断言的 3 全废是"三道题挤在同一批里"时的数字。
    assert audit["batch_repair_fallback_count"] == 1
    assert audit["failure_count"] == 2
    assert sorted(
        item["final_decision"] for item in audit["items"]
    ) == ["discard", "discard", "publish"]
    assert {
        contract["generation_status"]
        for contract in contracts.values()
    } == {"discarded", "ready"}


def test_fast_batch_prompt_deduplicates_shared_course_context() -> None:
    shared_marker = "SHARED_COURSE_FACTS_MARKER"
    contexts = [
        {
            "profile": {"course_purpose": "systematic"},
            "objective": {"objective_id": "objective-1"},
            "assessment_slot": {"slot_id": f"slot-{index}"},
            "question_design_brief": {"brief": f"brief-{index}"},
            "practice_level": f"level-{index}",
            "variant_index": index,
            "reference_patterns": [],
            "content_evidence": [],
            "reference_coverage": {},
            "untrusted_source_package": {
                "source_excerpt": shared_marker,
            },
        }
        for index in range(3)
    ]

    prompt = _batch_generation_prompt(contexts, compact=True)

    assert prompt.count(shared_marker) == 1
    for index in range(3):
        assert prompt.count(f"slot-{index}") == 1


async def test_fast_profile_stops_after_one_repair_attempt():
    model = DisagreeingModel()

    prepared = await AssessmentGenerationOrchestrator(
        model=model
    ).prepare_course(
        _course(),
        generation_profile="fast",
        generation_scope="scoped_repair",
    )

    contract = prepared["_assessment_generated_contracts"][
        "thermo-1"
    ]["objective_practice"]
    audit_item = next(
        item
        for item in prepared["_assessment_generation_audit"]["items"]
        if item["practice_level"] == "objective_practice"
    )
    assert model.repair_calls == 1
    assert len(audit_item["attempts"]) == 2
    assert contract["generation_status"] == "discarded"


async def test_single_node_repair_runs_its_practice_levels_concurrently(
    monkeypatch,
):
    """M2：只重建一个小节时，三个练习层级并发跑，不再串行空转两个槽位。

    scoped_repair 是「教师点了某一节重建、正等着看结果」的场景。改动前它走
    串行 for，一个层级做完才做下一个。
    """
    monkeypatch.setenv("ASSESSMENT_NODE_CONCURRENCY", "3")
    in_flight = 0
    peak_in_flight = 0

    class ConcurrencyProbeModel(RepairingModel):
        async def generate_candidate(self, context: dict) -> dict:
            nonlocal in_flight, peak_in_flight
            in_flight += 1
            peak_in_flight = max(peak_in_flight, in_flight)
            try:
                await asyncio.sleep(0)
                return await super().generate_candidate(context)
            finally:
                in_flight -= 1

    await AssessmentGenerationOrchestrator(
        model=ConcurrencyProbeModel(),
    ).prepare_course(_course(), node_ids=["thermo-1"])

    assert peak_in_flight > 1, (
        "单小节重建时三个练习层级仍在串行，槽位被空转"
    )


async def test_multi_node_repair_keeps_sections_interleaved(monkeypatch):
    """M2 的另一半：并发不能把小节之间的交替吃掉。

    全局槽位信号量只管总量、不管先后。若让每个小节把三个层级一次性投出去，
    先到的小节会吃满全部槽位，后面的小节一个都起不来，多小节重建退化成
    一节一节顺序做、章节回调也不再交替。这条锁住那个边界。
    """
    monkeypatch.setenv("ASSESSMENT_NODE_CONCURRENCY", "2")
    started_nodes: set[str] = set()
    both_started = asyncio.Event()

    class CrossNodeModel(RepairingModel):
        async def generate_candidate(self, context: dict) -> dict:
            objective_id = str(
                (context.get("assessment_slot") or {}).get("objective_id") or ""
            )
            started_nodes.add(objective_id)
            if len(started_nodes) == 2:
                both_started.set()
            await both_started.wait()
            return await super().generate_candidate(context)

    course = _course()
    second = deepcopy(course["nodes"][0])
    second["node_id"] = "thermo-2"
    second["node_name"] = "热力学第二小节"
    course["nodes"].append(second)

    # 两个小节必须都能开工；做不到这里会因 both_started 永不置位而超时。
    await asyncio.wait_for(
        AssessmentGenerationOrchestrator(
            model=CrossNodeModel(),
        ).prepare_course(course, node_ids=["thermo-1", "thermo-2"]),
        timeout=2,
    )
    assert len(started_nodes) == 2

async def test_settled_questions_survive_a_failing_sibling_in_same_section():
    """同一小节里某道题失败，不能连累已经成功的其他题（按题检查点）。"""

    class OneLevelFailsModel(RepairingModel):
        async def generate_candidate(self, context: dict) -> dict:
            level = str(context.get("practice_level") or "")
            if level == "mastery_check":
                raise AIProviderRequestError("429 insufficient balance")
            return await super().generate_candidate(context)

    chapter_events: list[dict] = []
    prepared = await AssessmentGenerationOrchestrator(
        model=OneLevelFailsModel(),
    ).prepare_course(
        _course(),
        node_ids=["thermo-1"],
        practice_levels_by_node={
            "thermo-1": [
                "concept_check",
                "objective_practice",
                "mastery_check",
            ],
        },
        on_chapter_complete=chapter_events.append,
    )

    event = chapter_events[0]
    # 整节仍然不算通过——失败的那道题必须重来。
    assert event["passed"] is False
    # 但成功的两道题必须被单独结算出来，供调用方落盘。
    assert set(event["settled_practice_levels"]) == {
        "concept_check",
        "objective_practice",
    }
    assert "mastery_check" not in event["settled_practice_levels"]
    contracts = prepared["_assessment_generated_contracts"]["thermo-1"]
    for level in ("concept_check", "objective_practice"):
        assert contracts[level]["generation_status"] != "discarded"
