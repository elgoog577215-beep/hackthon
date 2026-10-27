"""Bind an open-answer review to the exact proposed teaching/grading artifact."""
from copy import deepcopy

from course_versioning import stable_hash
from solution_contracts import worked_solution_is_complete
from assessment_fact_evidence import fact_publication_state

SOLUTION_PROTOCOL = "assessment_solution_protocol_v1"
OPEN_VALIDATORS = {"expert_rubric_validator", "language_rubric_validator"}
DELIVERY_FIELDS = ("canonical_answer", "worked_solution", "rubric", "acceptable_answers", "validator_config", "solution_graph")


def numeric_domain_issue(slot, independent):
    if slot.get('assessment_purpose')!='criterion_check' or slot.get('input_mode')!='numeric_unit':
        return None
    if independent.get('result_status')=='determinate':
        return None
    return {'code':'ANSWER_DOMAIN_MISMATCH','severity':'critical',
            'message':'本题未形成确定的数值结果，不能用0或数量替代不存在、无界或条件不足的结果。',
            'evidence':{'result_status':independent.get('result_status','unverified')}}


def delivery_solution(contract: dict) -> dict:
    solution = contract.get("solution_envelope") or {}
    return {key: deepcopy(solution[key]) for key in DELIVERY_FIELDS if key in solution}


def delivery_hash(contract: dict) -> str:
    spec = {key: value for key, value in (contract.get("question_spec") or {}).items()
            if key != "solution_revision_id"}
    return stable_hash({"question": spec, "solution": delivery_solution(contract)}, prefix="delivery_")


def review_solution_payload(contract: dict, independent: dict) -> dict:
    payload = {key: deepcopy(independent.get(key)) for key in
               ("answer", "summary", "work", "checks", "option_analysis", "common_errors")}
    payload["delivery_solution"] = delivery_solution(contract)
    payload["author_answer_proposal"] = deepcopy((contract.get("solution_envelope") or {}).get("author_answer_proposal"))
    return payload


def attest_final_solution_review(contract: dict, report: dict, expected_hash: str) -> dict:
    protocol = contract.get("solution_protocol") or (contract.get("solution_envelope") or {}).get("final_solution_review") or {}
    if protocol.get("schema_version") != SOLUTION_PROTOCOL:
        return report
    result = deepcopy(report)
    stable = delivery_hash(contract) == expected_hash
    solution = contract.get("solution_envelope") or {}
    same_answer = solution.get("canonical_answer") == (solution.get("independent_solution_record") or {}).get("answer")
    complete = worked_solution_is_complete(solution)
    if not stable or not same_answer or not complete:
        result["passed"] = result["solution_consistent"] = False
        result.setdefault("issues", []).append({
            "code": "FINAL_SOLUTION_CHANGED" if not stable else "WORKED_SOLUTION_INCOMPLETE",
            "severity": "critical", "message": "最终题面或答案与被评审的解答不一致，禁止发布。",
        })
    accepted = bool(result.get("passed") is True and result.get("solution_consistent") is True
                    and float(result.get("confidence") or 0) >= .85 and stable and same_answer and complete)
    pending_facts = fact_publication_state(contract) == "unverified"
    protocol.update(reviewed_delivery_hash=expected_hash, accepted=accepted,
                    resolution=("pending_fact_review" if pending_facts else "independent_supported") if accepted else "unresolved")
    validation = contract.setdefault("solution_validation", {})
    validation["passed"] = accepted
    validation["status"] = ("needs_fact_review" if pending_facts else "semantic_validated") if accepted else "pending_semantic_review"
    validation["independent_solution_present"] = True
    validation.setdefault("checks", {})["final_solution_review"] = accepted
    contract["domain_validation"] = deepcopy(validation)
    return result


def final_solution_review_valid(contract: dict) -> bool:
    protocol = contract.get("solution_protocol") or (contract.get("solution_envelope") or {}).get("final_solution_review") or {}
    if protocol.get("schema_version") != SOLUTION_PROTOCOL:
        return True  # Historical questions retain their original contract.
    solution = contract.get("solution_envelope") or {}
    return bool(protocol.get("accepted") is True
                and protocol.get("reviewed_delivery_hash") == delivery_hash(contract)
                and solution.get("canonical_answer") == (solution.get("independent_solution_record") or {}).get("answer")
                and worked_solution_is_complete(solution))
