"""Evidence admission is separate from answer agreement; no model or storage I/O."""

import re
from copy import deepcopy
from difflib import SequenceMatcher

from course_versioning import stable_hash
from question_measurement_contract import (
    fixed_input_witness_issues,
    measurement_findings,
    observation_prediction_issues,
    review_witness_issues,
)

EVIDENCE_SCHEMA = "question_evidence_admission_v2"
CHECKS = (
    "language_aligned",
    "no_answer_leakage",
    "explanation_consistent",
    "independently_assessable",
    "options_unambiguous",
    "observation_discriminates",
    "reasoning_grounded",
    "prerequisites_within_scope",
)


def _normalized(text: str) -> str:
    return re.sub(r"[\W_]+", "", str(text)).lower()


def evidence_findings(contract: dict, brief: dict | None = None) -> list[dict]:
    brief = brief or contract.get("design_brief") or {}
    spec = contract.get("question_spec") or {}
    stimulus = str((spec.get("stimulus") or {}).get("rendered_text") or "")
    prompt = str(contract.get("prompt") or stimulus + "\n" + str((spec.get("task") or {}).get("rendered_text") or ""))
    issues = []

    def add(code, message, evidence):
        issues.append({"code": code, "severity": "critical", "message": message, "evidence": str(evidence)[:240]})

    language = brief.get("language_contract") or contract.get("language_contract") or {}
    if language.get("language_standard") == "C17":
        fences = re.findall(r"```([^\n]*)\n([\s\S]*?)```", prompt)
        foreign = [tag for tag, _ in fences if tag.strip().lower() not in {"", "c", "text", "plaintext"}]
        prose = re.sub(r"```[\s\S]*?```", "", prompt)
        if foreign or re.search(
            r"(?:在|以下|上述|本题|采用|使用|符合)\s*(?:C\+\+\d*|Python\s*\d*(?:\.\d+)?|C23|JavaScript)", prose, re.I
        ):
            add(
                "COURSE_LANGUAGE_MISMATCH",
                "题目必须使用课程锁定的C17语义和C代码；不得改为C++、Python或其他版本。",
                foreign or prose,
            )
        if any(re.search(r"\belif\b|\bfor\s+\w+\s+in\s+|\bstd::|\bcout\s*<<", body) for _, body in fences):
            if not any(i["code"] == "COURSE_LANGUAGE_MISMATCH" for i in issues):
                add("COURSE_LANGUAGE_MISMATCH", "代码围栏标记与实际语法不符；当前任务要求C17。", prompt)
    if not (brief.get("assessment_binding_schema") or contract.get("assessment_binding_schema")):
        return issues
    issues.extend(measurement_findings(contract, brief))
    # Only assertions outside code are candidates; the alternatives themselves
    # and a proposition explicitly posed as a question are not disclosures.
    prose = re.sub(r"```[\s\S]*?```", "", stimulus or prompt)
    target = _normalized(brief.get("primary_knowledge") or "")
    canonical = (contract.get("solution_envelope") or contract.get("answer_spec") or {}).get("canonical_answer")
    options = spec.get("options") or contract.get("options") or []
    if (
        re.search(r"最后一行|last line", prompt, re.I)
        and options
        and all(
            len(str(o.get("text") or o.get("label") or "").replace("\\n", "\n").strip().splitlines()) > 1
            for o in options
        )
    ):
        add("RESPONSE_SCOPE_MISMATCH", "题目只问最后一行，但所有选项都包含多行完整输出，没有符合要求的选项。", prompt)
    correct_texts = [_normalized(o.get("text")) for o in options if o.get("id") == canonical]
    for sentence in re.findall(r"[^。！？!?\n]+[。！？!?]?", prose):
        if sentence.endswith(("?", "？")) or re.search(r"^\s*是否|几次|哪一个|哪一项|请选择|选择正确", sentence):
            continue
        normalized = _normalized(sentence)
        if any(len(answer) >= 8 and answer in normalized for answer in correct_texts):
            add(
                "ANSWER_RULE_DISCLOSED",
                "题干断言已包含正确选项内容；移除答案提示或改成需要应用规则的新情境。",
                sentence,
            )
            break
        if len(target) >= 12 and (target in normalized or SequenceMatcher(None, target, normalized).ratio() >= 0.65):
            add("ANSWER_RULE_DISCLOSED", "题干直接陈述了本题所测规则，不能作为独立掌握检查。", sentence)
            break
    return issues


def evidence_content_revision(item: dict) -> str:
    spec = item.get("question_spec") or {}
    options = item.get("options") or spec.get("options") or []
    return stable_hash(
        {
            "prompt": item.get("prompt"),
            "options": [{"id": o.get("id"), "text": o.get("text") or o.get("label")} for o in options],
            "solution_revision_id": item.get("solution_revision_id")
            or (item.get("solution_envelope") or {}).get("solution_revision_id"),
            "primary_knowledge_ids": item.get("primary_knowledge_ids"),
            "knowledge_revision_refs": item.get("knowledge_revision_refs"),
        },
        prefix="qev_",
    )


def stamp_evidence_admission(contract: dict, report: dict) -> dict:
    checks = {key: (report.get("evidence_checks") or {}).get(key) is True for key in CHECKS}
    local = evidence_findings(contract)
    witness = report.get("review_witness") or {}
    witness_issues = review_witness_issues(contract, witness)
    eligible = bool(
        report.get("reviewer_triggered") is True
        and report.get("passed") is True
        and report.get("solution_consistent") is True
        and all(checks.values())
        and not local
        and not witness_issues
    )
    admission = {
        "schema_version": EVIDENCE_SCHEMA,
        "eligible": eligible,
        "checks": checks,
        "local_issues": [*local, *witness_issues],
        "review_witness": witness,
        "witness_verified": not witness_issues,
        "content_revision": evidence_content_revision(contract),
    }
    contract["evidence_admission"] = admission
    return admission


def independent_evidence_admitted(item: dict) -> bool:
    admission = item.get("evidence_admission") or {}
    return bool(
        admission.get("schema_version") == EVIDENCE_SCHEMA
        and admission.get("eligible") is True
        and admission.get("witness_verified") is True
        and all((admission.get("checks") or {}).get(k) is True for k in CHECKS)
        and admission.get("content_revision") == evidence_content_revision(item)
        and not evidence_findings(item)
        and not fixed_input_witness_issues(str(item.get("prompt") or ""), admission.get("review_witness") or {})
        and not observation_prediction_issues(
            str(item.get("prompt") or ""), (admission.get("review_witness") or {}).get("observation_test") or {}
        )
    )


def revalidate_evidence_admission(item: dict, solution: dict) -> dict:
    """Recheck stored evidence with its private solution; can revoke, never grant.

    Returning a new projection preserves the historical question and model audit.
    No extra model call is needed to apply newly available deterministic checks.
    """
    admission = deepcopy(item.get("evidence_admission") or {})
    slot = item.get("assessment_slot") or {}
    brief = item.get("design_brief") or {
        "assessment_binding_schema": item.get("assessment_binding_schema"),
        "primary_knowledge": next(iter(slot.get("knowledge") or []), ""),
        "language_contract": slot.get("language_contract") or {},
        "answer_fact_contract": {
            "fact_basis": [e.get("reference_excerpt") for e in slot.get("target_content_evidence") or []]
        },
    }
    context = {**item, "solution_envelope": solution, "design_brief": brief}
    issues = [*evidence_findings(context)]
    if solution:
        issues.extend(review_witness_issues(context, admission.get("review_witness") or {}))
    else:
        issues.extend(fixed_input_witness_issues(str(item.get("prompt") or ""), admission.get("review_witness") or {}))
        issues.extend(
            observation_prediction_issues(
                str(item.get("prompt") or ""), (admission.get("review_witness") or {}).get("observation_test") or {}
            )
        )
    if not solution:
        issues.append(
            {
                "code": "PRIVATE_SOLUTION_UNAVAILABLE",
                "severity": "critical",
                "message": "无法核对本题私有答案与解析，暂不提供独立掌握题。",
            }
        )
    if not independent_evidence_admitted(item) or issues:
        admission["eligible"] = False
        admission["local_issues"] = [*(admission.get("local_issues") or []), *issues]
    return admission
