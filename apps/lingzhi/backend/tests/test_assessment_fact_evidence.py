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


@pytest.mark.parametrize("plan,expected", [
    ({"kind": "arithmetic", "expression": "16384/8"}, 2048),
    ({"kind": "dynamic_array", "append_count": 4}, 11),
    ({"kind": "range_sum", "values": [1,2,3,4,5], "start": 0, "end": 2}, 6),
    ({"kind": "treap_depth", "n": 3, "rank": 2}, "1"),
    ({"kind": "zipf_coverage", "n": 10, "alpha": 1, "threshold": "9/10"}, 8),
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
