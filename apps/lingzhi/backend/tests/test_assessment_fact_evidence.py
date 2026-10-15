from copy import deepcopy
from fractions import Fraction

import pytest


def test_model_confidence_cannot_certify_a_false_treap_premise():
    from assessment_fact_evidence import evaluate_fact_evidence
    spec = {"stimulus": {"rendered_text": "Treap的键为1到n，优先级独立均匀随机。已知 E[D(i)] = H_n - 1，其中 H_n 为调和数，根深度为0。"},
            "task": {"rendered_text": "求所有键的平均深度。"}}
    report = evaluate_fact_evidence(spec, {"canonical_answer": "H_n - 1"})
    assert report["status"] == "contradicted"
    assert report["counterexample"]["expected"] == "1"
    assert report["counterexample"]["claimed"] == "5/6"


@pytest.mark.parametrize("claim", ["已知 16384/8=1024。", "已知 2+3+1+5=8。", "已知 1+2+3=9。", "已知 0.8852>=0.90。"])
def test_false_numeric_premises_have_executable_counterexamples(claim):
    from assessment_fact_evidence import evaluate_fact_evidence
    report=evaluate_fact_evidence({"stimulus":{"rendered_text":claim}, "task":{"rendered_text":"据此计算。"}}, {})
    assert report["status"] == "contradicted"
    assert report["counterexample"]["method"] == "exact_rational_comparison"


def test_question_asking_to_refute_a_false_statement_is_not_itself_rejected():
    from assessment_fact_evidence import evaluate_fact_evidence
    report=evaluate_fact_evidence({"stimulus":{"rendered_text":"已知 1+2+3=9。"}, "task":{"rendered_text":"判断上述说法是否正确并反驳。"}}, {})
    assert report["status"] == "unverified"


@pytest.mark.parametrize("plan,expected", [
    ({"kind": "arithmetic", "expression": "16384/8"}, 2048),
    ({"kind": "dynamic_array", "append_count": 4}, 11),
    ({"kind": "range_sum", "values": [1,2,3,4,5], "start": 0, "end": 2}, 6),
    ({"kind": "treap_depth", "n": 3, "rank": 2}, "1"),
    ({"kind": "zipf_coverage", "n": 10, "alpha": 1, "threshold": "9/10"}, 8),
    ({"kind": "state_operations", "initial_state": [1], "operations": [{"op":"append","value":2}]}, [1,2]),
])
def test_computed_plans_bind_the_whole_question_and_reject_answer_mutation(plan, expected):
    from assessment_fact_evidence import build_computed_candidate, evaluate_fact_evidence
    candidate = build_computed_candidate(plan)
    spec, solution = candidate["question_spec"], candidate["solution"]
    report = evaluate_fact_evidence(spec, solution)
    assert report["status"] == "verified"
    assert report["result"] == expected
    changed = deepcopy(solution)
    changed["canonical_answer"]["conclusion"] = "wrong"
    assert evaluate_fact_evidence(spec, changed)["status"] == "contradicted"
    spec["stimulus"]["rendered_text"] += "\n已知任意树的所有节点深度相同。"
    assert evaluate_fact_evidence(spec, solution)["status"] == "unverified"


def test_forged_verification_and_generator_hints_are_not_evidence():
    from assessment_fact_evidence import evaluate_fact_evidence
    spec = {"stimulus": {"rendered_text": "原有100件取走40件。"}, "task": {"rendered_text": "剩余多少件？"},
            "solver_contract": {"kind": "numeric_expression", "expression": "100+40"},
            "factual_validation": {"status": "verified"}}
    assert evaluate_fact_evidence(spec, {"canonical_answer":140})["status"] == "unverified"


def test_fact_gate_is_revision_bound_and_legacy_questions_are_not_reclassified():
    from assessment_fact_evidence import apply_fact_evidence, fact_publication_state, build_computed_candidate
    candidate = build_computed_candidate({"kind":"treap_depth","n":3,"rank":2})
    contract = {"question_spec": candidate["question_spec"], "solution_envelope": candidate["solution"]}
    assert fact_publication_state(contract) == "legacy"
    apply_fact_evidence(contract)
    assert fact_publication_state(contract) == "verified"
    contract["question_spec"]["task"]["rendered_text"] += " 并证明所有键期望深度都相等。"
    assert fact_publication_state(contract) != "verified"


@pytest.mark.parametrize("plan", [
    {"kind":"arithmetic","expression":"__import__('os').getcwd()"},
    {"kind":"treap_depth","n":10000000,"rank":2},
    {"kind":"treap_depth","n":3,"rank":0},
    {"kind":"range_sum","values":[1,2],"start":1,"end":0},
    {"kind":"zipf_coverage","n":10,"alpha":1,"threshold":"2"},
    {"kind":"dynamic_array","append_count":True},
])
def test_unbounded_or_invalid_computation_plans_are_rejected(plan):
    from assessment_fact_evidence import build_computed_candidate
    with pytest.raises(ValueError):
        build_computed_candidate(plan)


def test_unknown_proof_is_retained_for_fact_review_even_when_model_awards_full_marks():
    from assessment_orchestrator import _apply_quality_decision
    from assessment_fact_evidence import apply_fact_evidence
    contract = {"question_spec":{"stimulus":{"rendered_text":"未经证实的定理。"},"task":{"rendered_text":"证明定理。"}},
                "solution_envelope":{"canonical_answer":"模型说正确"}, "solution_validation":{"passed":True}}
    apply_fact_evidence(contract)
    _apply_quality_decision(contract,{"passed":True,"issues":[]},{"passed":True,"confidence":1.0})
    assert contract["review_required"]
    assert not contract["solution_validation"]["auto_publish_eligible"]
    assert "facts_unverified" in contract["risk_flags"]


async def test_generation_retains_unknown_facts_without_publishing_or_repeating_generation():
    from backend.tests.test_assessment_generation_orchestrator import RepairingModel, _course
    from assessment_orchestrator import AssessmentGenerationOrchestrator
    model = RepairingModel()
    prepared = await AssessmentGenerationOrchestrator(model=model).prepare_course(
        _course(), node_ids=["thermo-1"], practice_levels_by_node={"thermo-1":["mastery_check"]})
    contract = prepared["_assessment_generated_contracts"]["thermo-1"]["mastery_check"]
    assert contract["solution_validation"]["factual_validation"]["status"] == "unverified"
    assert contract["review_required"]
    assert model.generate_calls == model.solve_calls == 1
    assert model.repair_calls == 0
    assert prepared["_assessment_generation_audit"]["items"][0]["final_decision"] == "teacher_review"


async def test_pending_fact_review_is_a_retained_slot_when_resuming():
    from backend.tests.test_assessment_generation_orchestrator import RepairingModel, _course
    from assessment_orchestrator import AssessmentGenerationOrchestrator
    from question_bank import build_question_bank
    from routers.question_bank import _published_practice_levels_by_node
    prepared = await AssessmentGenerationOrchestrator(model=RepairingModel()).prepare_course(
        _course(), node_ids=["thermo-1"], practice_levels_by_node={"thermo-1":["mastery_check"]})
    bank = build_question_bank(prepared)
    retained = _published_practice_levels_by_node(prepared, bank, include_fact_review=True)
    assert "mastery_check" in retained["thermo-1"]


def test_review_queue_survives_publication_policy_and_job_finishes_as_review(tmp_path):
    from question_bank import _mandatory_review_reason
    from question_bank_jobs import QuestionBankRebuildJobRepository
    item = {"source_type":"generated", "quality_report":{"passed":True},
            "solution_validation":{"passed":True}, "risk_flags":["facts_unverified"], "review_required":True}
    assert _mandatory_review_reason(item) == "risk:facts_unverified"
    repo = QuestionBankRebuildJobRepository(tmp_path)
    job,_ = repo.create_job("facts", request_id="facts-1", scope="nodes", node_ids=["n1"], mode="incremental", actor_id="teacher")
    final = repo.complete(job["job_id"], result={"review_queue":{"blocking_count":1,"items":[item]}})
    assert final["status"] == "waiting_review"
    assert "待事实复核" in final["message"]
    assert final["error"] is None


async def test_wrong_premise_is_blocked_even_when_all_model_roles_agree():
    from backend.tests.test_assessment_generation_orchestrator import RepairingModel, _course
    from assessment_orchestrator import AssessmentGenerationOrchestrator
    class WrongPremiseModel(RepairingModel):
        async def generate_candidate(self, context):
            candidate = await super().generate_candidate(context)
            candidate["question_spec"]["stimulus"]["rendered_text"] = "Treap的键为1到n，优先级独立均匀随机。已知 E[D(i)] = H_n - 1，根深度0。"
            candidate["question_spec"]["task"]["rendered_text"] = "求所有键的平均深度并解释依据。"
            return candidate
    prepared = await AssessmentGenerationOrchestrator(model=WrongPremiseModel()).prepare_course(
        _course(), node_ids=["thermo-1"], practice_levels_by_node={"thermo-1":["mastery_check"]})
    c = prepared["_assessment_generated_contracts"]["thermo-1"]["mastery_check"]
    assert c["generation_status"] == "discarded"
    assert "TASK_PREMISE_FALSE" in {i["code"] for i in c["quality_report"]["issues"]}


def test_production_compiles_a_plan_before_rendering_instead_of_trusting_authored_answer():
    from assessment_fact_evidence import build_computed_candidate, computed_independent_solution
    from assessment_orchestrator import _contract_from_candidate, _apply_independent_validation
    from backend.tests.test_assessment_solution_protocol import example
    base, _, validation = example()
    base["question_spec"].update(build_computed_candidate({"kind":"treap_depth","n":3,"rank":2})["question_spec"])
    base["question_spec"]["input_contract"]["fields"][-1]["kind"] = "short_text"
    candidate = {"question_spec":{"computation_plan":{"kind":"treap_depth","n":3,"rank":2}},"solution":{}}
    contract = _contract_from_candidate(base, candidate)
    independent = computed_independent_solution(contract["question_spec"])
    assert independent is not None
    _apply_independent_validation(contract, validation, independent)
    assert contract["solution_validation"]["factual_validation"]["status"] == "verified"
    assert contract["solution_envelope"]["canonical_answer"]["conclusion"] == "1"


def test_generation_wire_offers_computation_plan_and_traceable_premises():
    from assessment_orchestrator import _generation_prompt_v2
    prompt=_generation_prompt_v2({"assessment_slot":{"input_mode":"structured_fields"}},compact=True)
    assert '"computation_plan"' in prompt
    assert '"premise_bindings"' in prompt


def test_publication_boundary_rechecks_fact_evidence_instead_of_cached_approval():
    from assessment_fact_evidence import build_computed_candidate, apply_fact_evidence
    from question_bank import _apply_tiered_review_policy
    candidate = build_computed_candidate({"kind":"treap_depth","n":3,"rank":2})
    contract = {"question_spec":candidate["question_spec"],"solution_envelope":candidate["solution"]}
    apply_fact_evidence(contract)
    item = {"id":"q", "revision_id":"r", "solution_revision_id":"s", "source_type":"generated",
            "assessment_role":"practice", "question_spec":contract["question_spec"], "risk_flags":[],
            "quality_report":{"passed":True}, "solution_validation":{"passed":True}, "review_required":False}
    candidate["solution"]["canonical_answer"]["conclusion"] = "wrong"
    _apply_tiered_review_policy([item], {}, solution_envelopes={"s":candidate["solution"]})
    assert item["lifecycle_status"] != "approved"


def test_public_fact_status_never_contains_private_answers_or_counterexamples():
    from assessment_fact_evidence import build_computed_candidate, apply_fact_evidence
    c=build_computed_candidate({"kind":"treap_depth","n":3,"rank":2})
    contract={"question_spec":c["question_spec"],"solution_envelope":c["solution"]}
    apply_fact_evidence(contract)
    visible=contract["solution_validation"]["factual_validation"]
    assert "result" not in visible and "counterexample" not in visible
    assert contract["solution_envelope"]["factual_validation"]["result"] == "1"


def test_proof_references_are_resolved_against_frozen_server_evidence_not_model_citations():
    from assessment_fact_evidence import apply_fact_evidence
    quote="每次扩容将容量翻倍。"
    contract={"question_spec":{"stimulus":{"rendered_text":quote}, "task":{"rendered_text":"证明摊还界。"}},
              "solution_envelope":{"canonical_answer":"待核验的证明", "premise_bindings":[
                  {"claim":quote,"quote":quote,"reference_id":"book-1"},
                  {"claim":quote,"quote":quote,"reference_id":"invented-citation"}],
                  "factual_source_evidence":[{"reference_id":"book-1","reference_excerpt":quote,"source_type":"course_materials"}]}}
    report=apply_fact_evidence(contract)
    assert report["status"] == "unverified", "quotation is traceability, not a mathematical correctness oracle"
    assert report["source_bindings"][0]["status"] == "matched"
    assert report["source_bindings"][1]["status"] == "missing_reference"
    assert report["source_bindings"][0]["source_snapshot_hash"]
