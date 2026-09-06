"""Deterministic learner model projected from formal learning evidence."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import math
from typing import Any

from course_knowledge_map import (
    knowledge_ids_for_section,
    project_course_knowledge_map,
    project_learning_assets_to_knowledge,
)
from course_versioning import stable_hash


SCHEMA_VERSION = "learner_model_v1"
ACTIVE_RECORD_STATUSES = {"active", "open", "explaining", "awaiting_verification", "reopened", "pending", "due"}
CURRENT_ATTEMPT_STATUSES = {"submitted", "grading", "graded"}


def build_learner_model(
    course_data: dict[str, Any],
    *,
    user_id: str,
    events: list[dict[str, Any]],
    snapshot: dict[str, Any] | None,
    records: list[dict[str, Any]],
    attempts: list[dict[str, Any]],
    workflow: dict[str, Any],
    progress: dict[str, Any],
    source_revision_vector: dict[str, Any],
) -> dict[str, Any]:
    """Build a read-only model without storing or calling an AI provider."""
    course_id = str(course_data.get("course_id") or "")
    course_version_id = str(course_data.get("current_course_version_id") or "")
    course_map = project_course_knowledge_map(course_data)
    skill_ids_by_node = _formal_refs_by_node(course_data, "skill_unit_ids")
    objective_models = [
        _objective_model(
            objective,
            knowledge_ids=knowledge_ids_for_section(
                course_map,
                str(objective.get("node_id") or ""),
            ),
            skill_unit_ids=skill_ids_by_node.get(str(objective.get("node_id") or ""), []),
            course_version_id=course_version_id,
            events=events,
            records=records,
            attempts=attempts,
            workflow=workflow,
        )
        for objective in progress.get("nodes") or []
    ]
    knowledge_states = _knowledge_states(objective_models)
    skill_states = _skill_states(objective_models)
    mistake_signals = _mistake_signals(workflow)
    evidence_catalog = _evidence_catalog(events, records, attempts, workflow)
    observed_at = _latest_timestamp(evidence_catalog)
    sufficiency = _data_sufficiency(objective_models, evidence_catalog)
    strengths = [
        _model_item(item, reason_code="formally_mastered")
        for item in objective_models
        if item.get("mastery_status") == "mastered" and item.get("confidence") == "high"
    ]
    needs_attention = [
        _model_item(item, reason_code=str((item.get("support_need") or {}).get("reason_code") or "needs_attention"))
        for item in objective_models
        if (item.get("support_need") or {}).get("status") not in {"none", "unknown"}
    ]
    self_reports = [
        {
            "source_id": item.get("event_id"),
            "statement": str((item.get("evidence") or {}).get("statement") or ""),
            "scope": str((item.get("evidence") or {}).get("scope") or "course"),
            "observed_at": item.get("created_at"),
        }
        for item in events
        if item.get("event_type") == "learner_self_reported"
        and str((item.get("evidence") or {}).get("statement") or "").strip()
    ]
    model_revision_id = stable_hash({
        "schema_version": SCHEMA_VERSION,
        "user_id": user_id,
        "course_id": course_id,
        "source_revision_vector": source_revision_vector,
        "course_knowledge_map_revision_id": course_map.get("revision_id"),
    }, prefix="lmr_")

    return {
        "schema_version": SCHEMA_VERSION,
        "model_revision_id": model_revision_id,
        "user_id": user_id,
        "course_id": course_id,
        "course_version_id": course_version_id,
        "source_revision_vector": deepcopy(source_revision_vector),
        "observed_at": observed_at,
        "data_sufficiency": sufficiency,
        "summary": {
            "total_objectives": len(objective_models),
            "started_objectives": sum(item.get("reading_status") != "not_started" for item in objective_models),
            "learned_objectives": sum(item.get("reading_status") == "learned" for item in objective_models),
            "mastered_objectives": sum(item.get("mastery_status") == "mastered" for item in objective_models),
            "needs_attention_objectives": len(needs_attention),
            "covered_knowledge": len(knowledge_states),
            "mastered_knowledge": sum(item.get("status") == "mastered" for item in knowledge_states),
            "needs_attention_knowledge": sum(item.get("status") == "needs_attention" for item in knowledge_states),
            "covered_skills": len(skill_states),
            "needs_attention_skills": sum(item.get("status") == "needs_attention" for item in skill_states),
            "confirmed_mistake_signals": len(mistake_signals),
            "formal_evidence_count": sufficiency["formal_evidence_count"],
            "active_record_count": sum(item.get("status") in ACTIVE_RECORD_STATUSES for item in records),
        },
        "objectives": objective_models,
        "knowledge_coordinate": {
            "knowledge_library_id": course_map.get("knowledge_library_id"),
            "knowledge_library_version": course_map.get("knowledge_library_version"),
            "course_map_revision_id": course_map.get("revision_id"),
        },
        "knowledge_states": knowledge_states,
        "skill_states": skill_states,
        "mistake_signals": mistake_signals,
        "strengths": strengths,
        "needs_attention": needs_attention,
        "self_reports": self_reports,
        "evidence_catalog": evidence_catalog,
        "model_policy": {
            "deterministic": True,
            "ai_writable": False,
            "reading_is_mastery": False,
            "legacy_profile_included": False,
            "learning_os_included": False,
            "knowledge_state_is_projection": True,
            "skill_state_is_projection": True,
            "mistake_requires_confirmed_diagnosis": True,
            "personal_state_can_modify_library": False,
        },
    }


def learner_model_summary(model: dict[str, Any], *, node_id: str | None = None) -> dict[str, Any]:
    objective = next((
        item for item in model.get("objectives") or []
        if node_id and str(item.get("node_id") or "") == node_id
    ), None)
    current_knowledge_ids = set((objective or {}).get("knowledge_ids") or [])
    current_skill_ids = set((objective or {}).get("skill_unit_ids") or [])
    return {
        "model_revision_id": model.get("model_revision_id"),
        "observed_at": model.get("observed_at"),
        "data_sufficiency": deepcopy(model.get("data_sufficiency") or {}),
        "summary": deepcopy(model.get("summary") or {}),
        "current_objective": deepcopy(objective),
        "knowledge_coordinate": deepcopy(model.get("knowledge_coordinate") or {}),
        "current_knowledge_states": deepcopy([
            item for item in model.get("knowledge_states") or []
            if item.get("knowledge_id") in current_knowledge_ids
        ]),
        "current_skill_states": deepcopy([
            item for item in model.get("skill_states") or []
            if item.get("skill_unit_id") in current_skill_ids
        ]),
        "current_mistake_signals": deepcopy([
            item for item in model.get("mistake_signals") or []
            if current_skill_ids.intersection(item.get("skill_unit_ids") or [])
        ]),
        "strengths": deepcopy((model.get("strengths") or [])[:3]),
        "needs_attention": deepcopy((model.get("needs_attention") or [])[:3]),
    }


def is_model_item_current(item: dict[str, Any], *, now: datetime | None = None) -> bool:
    """Return whether a time-bounded conclusion may drive current behavior."""
    valid_until = str(item.get("valid_until") or "").strip()
    if not valid_until:
        return True
    try:
        boundary = datetime.fromisoformat(valid_until.replace("Z", "+00:00"))
        if boundary.tzinfo is None:
            boundary = boundary.replace(tzinfo=timezone.utc)
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        return boundary >= current
    except (TypeError, ValueError):
        return False


def _objective_model(
    objective: dict[str, Any],
    *,
    knowledge_ids: list[str],
    skill_unit_ids: list[str],
    course_version_id: str,
    events: list[dict[str, Any]],
    records: list[dict[str, Any]],
    attempts: list[dict[str, Any]],
    workflow: dict[str, Any],
) -> dict[str, Any]:
    node_id = str(objective.get("node_id") or "")
    objective_revision_id = str(objective.get("objective_revision_id") or "")
    relevant_attempts = [
        item for item in attempts
        if item.get("status") in CURRENT_ATTEMPT_STATUSES
        and str(item.get("node_id") or "") == node_id
        and str(item.get("course_version_id") or "") == course_version_id
        and str(item.get("objective_revision_id") or "") == objective_revision_id
    ]
    relevant_records = [
        item for item in records
        if str(item.get("node_id") or "") == node_id
        and item.get("status") in ACTIVE_RECORD_STATUSES
    ]
    relevant_events = [
        item for item in events
        if str(item.get("node_id") or "") == node_id
        and (
            not item.get("objective_revision_id")
            or str(item.get("objective_revision_id") or "") == objective_revision_id
        )
    ]
    evidence_refs = _objective_evidence_refs(objective, relevant_attempts, relevant_records, relevant_events)
    support_need = _support_need(
        objective,
        attempts=relevant_attempts,
        records=relevant_records,
        workflow=workflow,
        evidence_refs=evidence_refs,
    )
    confidence = _confidence(objective, relevant_attempts, evidence_refs)
    observed_at = _latest_timestamp(evidence_refs)
    return {
        "objective_id": objective.get("objective_id"),
        "objective_revision_id": objective_revision_id,
        "node_id": node_id,
        "node_name": str(objective.get("node_name") or ""),
        "statement": str(objective.get("statement") or ""),
        "knowledge_ids": list(knowledge_ids),
        "skill_unit_ids": _unique([
            *skill_unit_ids,
            *[
                str(skill_id)
                for attempt in relevant_attempts
                for skill_id in attempt.get("skill_unit_ids") or []
            ],
        ]),
        "reading_status": str(objective.get("reading_status") or "not_started"),
        "mastery_status": str(objective.get("mastery_status") or "not_checked"),
        "has_historical_evidence": bool(objective.get("has_historical_evidence")),
        "confidence": confidence,
        "support_need": support_need,
        "evidence_refs": evidence_refs[:12],
        "observed_at": observed_at,
        "valid_until": _valid_until(
            observed_at,
            days=90 if str(objective.get("mastery_status") or "") == "mastered" else 30,
        ),
    }


def _knowledge_states(objectives: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for objective in objectives:
        for knowledge_id in objective.get("knowledge_ids") or []:
            grouped.setdefault(str(knowledge_id), []).append(objective)

    states: list[dict[str, Any]] = []
    for knowledge_id, linked in grouped.items():
        support_needed = any(
            (item.get("support_need") or {}).get("status") not in {"none", "unknown"}
            for item in linked
        )
        if support_needed:
            status = "needs_attention"
        elif linked and all(item.get("mastery_status") == "mastered" for item in linked):
            status = "mastered"
        elif linked and all(item.get("reading_status") == "learned" for item in linked):
            status = "learned"
        elif any(item.get("reading_status") != "not_started" for item in linked):
            status = "in_progress"
        else:
            status = "not_started"
        evidence_refs = _dedupe_evidence([
            ref for item in linked for ref in item.get("evidence_refs") or []
        ])
        state = {
            "knowledge_id": knowledge_id,
            "status": status,
            "confidence": _aggregate_confidence(linked, evidence_refs),
            "objective_ids": _unique([str(item.get("objective_id") or "") for item in linked]),
            "node_ids": _unique([str(item.get("node_id") or "") for item in linked]),
            "evidence_refs": evidence_refs[:12],
            "observed_at": _latest_timestamp(evidence_refs),
        }
        state["revision_id"] = stable_hash(state, prefix="lksr_")
        states.append(state)
    return sorted(states, key=lambda item: item["knowledge_id"])


def _skill_states(objectives: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for objective in objectives:
        for skill_id in objective.get("skill_unit_ids") or []:
            grouped.setdefault(str(skill_id), []).append(objective)

    states: list[dict[str, Any]] = []
    for skill_id, linked in grouped.items():
        support_needed = any(
            (item.get("support_need") or {}).get("status") not in {"none", "unknown"}
            for item in linked
        )
        if support_needed:
            status = "needs_attention"
        elif linked and all(item.get("mastery_status") == "mastered" for item in linked):
            status = "mastered"
        elif any(item.get("reading_status") != "not_started" for item in linked):
            status = "in_progress"
        else:
            status = "not_started"
        evidence_refs = _dedupe_evidence([
            ref for item in linked for ref in item.get("evidence_refs") or []
        ])
        state = {
            "skill_unit_id": skill_id,
            "status": status,
            "confidence": _aggregate_confidence(linked, evidence_refs),
            "objective_ids": _unique([str(item.get("objective_id") or "") for item in linked]),
            "node_ids": _unique([str(item.get("node_id") or "") for item in linked]),
            "evidence_refs": evidence_refs[:12],
            "observed_at": _latest_timestamp(evidence_refs),
        }
        state["revision_id"] = stable_hash(state, prefix="lssr_")
        states.append(state)
    return sorted(states, key=lambda item: item["skill_unit_id"])


def _mistake_signals(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    case = workflow.get("case") or {}
    if not case.get("diagnostic_case_id"):
        return []
    signals: list[dict[str, Any]] = []
    for hypothesis in case.get("hypotheses") or []:
        if hypothesis.get("status") != "confirmed":
            continue
        for mistake_id in hypothesis.get("confirmed_mistake_point_ids") or []:
            evidence_refs = [
                {
                    "source_id": item.get("attempt_id"),
                    "type": "diagnostic_probe",
                    "status": "confirmed",
                    "outcome": item.get("kind"),
                    "strength": "independent",
                    "observed_at": case.get("updated_at") or case.get("created_at"),
                }
                for item in hypothesis.get("evidence_for") or []
                if item.get("attempt_id")
            ]
            signal = {
                "mistake_point_id": str(mistake_id),
                "status": "confirmed",
                "confidence": str(hypothesis.get("confidence_level") or "high"),
                "skill_unit_ids": list(hypothesis.get("skill_unit_ids") or case.get("skill_unit_ids") or []),
                "node_id": case.get("node_id"),
                "diagnostic_case_id": case.get("diagnostic_case_id"),
                "hypothesis_id": hypothesis.get("hypothesis_id"),
                "evidence_refs": evidence_refs,
                "observed_at": case.get("updated_at") or case.get("created_at"),
            }
            signal["revision_id"] = stable_hash(signal, prefix="lmsr_")
            signals.append(signal)
    return signals


def _formal_refs_by_node(course_data: dict[str, Any], field: str) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    assets = project_learning_assets_to_knowledge(
        course_data,
        course_data.get("learning_assets") or {},
    )
    for collection in ("questions", "mastery_criteria", "diagnostic_templates", "remediation_units"):
        for item in assets.get(collection) or []:
            node_id = str(item.get("node_id") or "")
            if not node_id:
                continue
            result[node_id] = _unique([
                *result.get(node_id, []),
                *[str(value) for value in item.get(field) or []],
            ])
    return result


def _aggregate_confidence(
    objectives: list[dict[str, Any]],
    evidence_refs: list[dict[str, Any]],
) -> str:
    if not evidence_refs:
        return "insufficient"
    confidences = {str(item.get("confidence") or "insufficient") for item in objectives}
    if confidences == {"high"}:
        return "high"
    return "medium" if confidences.intersection({"high", "medium"}) else "limited"


def _dedupe_evidence(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    result = []
    for value in values:
        key = (str(value.get("type") or ""), str(value.get("source_id") or ""))
        if key in seen:
            continue
        seen.add(key)
        result.append(deepcopy(value))
    return result


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _objective_evidence_refs(
    objective: dict[str, Any],
    attempts: list[dict[str, Any]],
    records: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for attempt in attempts:
        source_id = str(attempt.get("attempt_id") or "")
        if not source_id or source_id in seen:
            continue
        seen.add(source_id)
        result = attempt.get("result") or {}
        refs.append({
            "source_id": source_id,
            "type": "practice_attempt",
            "status": str(attempt.get("status") or ""),
            "outcome": "passed" if result.get("passed") is True else "not_passed" if result.get("passed") is False else "pending",
            "strength": _attempt_strength(attempt),
            "observed_at": attempt.get("updated_at") or attempt.get("created_at"),
        })
    for record in records:
        source_id = str(record.get("record_id") or "")
        if not source_id or source_id in seen:
            continue
        seen.add(source_id)
        refs.append({
            "source_id": source_id,
            "type": f"learning_record:{record.get('record_type')}",
            "status": str(record.get("status") or ""),
            "outcome": "user_retained",
            "strength": "self_report",
            "observed_at": record.get("updated_at") or record.get("created_at"),
        })
    progress_ids = {str(item) for item in objective.get("evidence_event_ids") or [] if item}
    for event in events:
        source_id = str(event.get("event_id") or "")
        if not source_id or source_id in seen:
            continue
        if source_id not in progress_ids and event.get("event_type") not in {
            "node_learning_started", "node_learning_completed", "learner_self_reported",
        }:
            continue
        seen.add(source_id)
        refs.append({
            "source_id": source_id,
            "type": f"learning_event:{event.get('event_type')}",
            "status": "recorded",
            "outcome": str((event.get("result") or {}).get("reading_status") or "fact"),
            "strength": "explicit" if event.get("actor") == "user" else "derived",
            "observed_at": event.get("created_at"),
        })
    return sorted(refs, key=lambda item: str(item.get("observed_at") or ""), reverse=True)


def _support_need(
    objective: dict[str, Any],
    *,
    attempts: list[dict[str, Any]],
    records: list[dict[str, Any]],
    workflow: dict[str, Any],
    evidence_refs: list[dict[str, Any]],
) -> dict[str, Any]:
    objective_revision_id = str(objective.get("objective_revision_id") or "")
    case = workflow.get("case") or {}
    if case and str(case.get("objective_revision_id") or "") == objective_revision_id and case.get("status") not in {"resolved", "dismissed", "abandoned"}:
        return _inference("active_diagnostic", "high", evidence_refs)
    if str(objective.get("mastery_status") or "") == "needs_review":
        return _inference("formal_evidence_needs_review", "high", evidence_refs)
    independent_failures = [
        item for item in attempts
        if (item.get("result") or {}).get("passed") is False
        and float((item.get("result") or {}).get("grading_confidence") or 0) >= 0.72
        and int((item.get("result") or {}).get("support_level") or 0) <= 1
    ]
    if len(independent_failures) >= 2:
        return _inference("repeated_independent_failure", "high", evidence_refs)
    if any(item.get("record_type") == "issue" for item in records):
        return _inference("open_user_issue", "medium", evidence_refs)
    if independent_failures:
        return {
            "status": "unknown",
            "reason_code": "single_formal_failure_insufficient",
            "confidence": "low",
            "evidence_refs": [
                item.get("source_id") for item in evidence_refs[:5] if item.get("source_id")
            ],
        }
    return {
        "status": "none" if evidence_refs else "unknown",
        "reason_code": "no_current_support_need" if evidence_refs else "insufficient_evidence",
        "confidence": "insufficient" if not evidence_refs else "low",
        "evidence_refs": [],
    }


def _inference(reason_code: str, confidence: str, evidence_refs: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "status": "needs_support",
        "reason_code": reason_code,
        "confidence": confidence,
        "evidence_refs": [item.get("source_id") for item in evidence_refs[:5] if item.get("source_id")],
    }


def _confidence(
    objective: dict[str, Any],
    attempts: list[dict[str, Any]],
    evidence_refs: list[dict[str, Any]],
) -> str:
    if objective.get("mastery_status") == "mastered" and any(
        (item.get("result") or {}).get("passed") is True and _attempt_strength(item) == "independent"
        for item in attempts
    ):
        return "high"
    reliable = [item for item in attempts if float((item.get("result") or {}).get("grading_confidence") or 0) >= 0.72]
    if len(reliable) >= 2:
        return "medium"
    if evidence_refs:
        return "low"
    return "insufficient"


def _attempt_strength(attempt: dict[str, Any]) -> str:
    result = attempt.get("result") or {}
    support_level = int(result.get("support_level") or attempt.get("support_level") or 0)
    return "independent" if support_level <= 1 else "supported"


def _evidence_catalog(
    events: list[dict[str, Any]],
    records: list[dict[str, Any]],
    attempts: list[dict[str, Any]],
    workflow: dict[str, Any],
) -> list[dict[str, Any]]:
    catalog = [
        {
            "source_id": item.get("attempt_id"),
            "type": "practice_attempt",
            "node_id": item.get("node_id"),
            "objective_revision_id": item.get("objective_revision_id"),
            "status": item.get("status"),
            "observed_at": item.get("updated_at") or item.get("created_at"),
        }
        for item in attempts
        if item.get("status") in CURRENT_ATTEMPT_STATUSES and item.get("attempt_id")
    ]
    catalog.extend({
        "source_id": item.get("record_id"),
        "type": f"learning_record:{item.get('record_type')}",
        "node_id": item.get("node_id"),
        "objective_revision_id": item.get("objective_revision_id"),
        "status": item.get("status"),
        "observed_at": item.get("updated_at") or item.get("created_at"),
    } for item in records if item.get("record_id"))
    catalog.extend({
        "source_id": item.get("event_id"),
        "type": f"learning_event:{item.get('event_type')}",
        "node_id": item.get("node_id"),
        "objective_revision_id": item.get("objective_revision_id"),
        "status": "recorded",
        "observed_at": item.get("created_at"),
    } for item in events if item.get("event_id"))
    case = workflow.get("case") or {}
    if case.get("diagnostic_case_id"):
        catalog.append({
            "source_id": case.get("diagnostic_case_id"),
            "type": "diagnostic_case",
            "node_id": case.get("node_id"),
            "objective_revision_id": case.get("objective_revision_id"),
            "status": case.get("status"),
            "observed_at": case.get("updated_at") or case.get("created_at"),
        })
    return sorted(catalog, key=lambda item: str(item.get("observed_at") or ""), reverse=True)[:100]


def _log_damped_score(labeled_weights: list[tuple[str, float]]) -> float:
    """Aggregate (label, weight) pairs with diminishing returns per label.

    Each repetition of the same evidence label contributes
    ``weight * log2(1 + count_of_label)`` instead of ``weight * count``, so
    piling up many same-type occurrences gives sub-linear, diminishing
    credit (spec: "不得仅以固定次数作为唯一触发条件"). Distinct labels are
    summed independently, which additionally rewards evidence that is
    diverse in kind over evidence that merely repeats.
    """
    counts: dict[str, int] = {}
    weight_by_label: dict[str, float] = {}
    for label, weight in labeled_weights:
        counts[label] = counts.get(label, 0) + 1
        weight_by_label[label] = weight
    return sum(weight_by_label[label] * math.log2(1 + count) for label, count in counts.items())


# Formal-evidence weights used only by `_data_sufficiency` (model-wide
# confidence gating). `diagnostic_case` (a confirmed multi-probe diagnostic
# hypothesis) is weighted well above a single `practice_attempt` because it
# is inherently a stronger, independently-corroborated signal.
_FORMAL_EVIDENCE_WEIGHTS: dict[str, float] = {
    "diagnostic_case": 4.0,
    "practice_attempt": 2.0,
}
_FORMAL_STRONG_SCORE = 4.0  # one diagnostic_case alone reaches this
_FORMAL_MODERATE_SCORE = 2.0  # one graded practice_attempt alone reaches this


def _data_sufficiency(objectives: list[dict[str, Any]], catalog: list[dict[str, Any]]) -> dict[str, Any]:
    formal = [
        item for item in catalog
        if item.get("type") == "diagnostic_case"
        or (item.get("type") == "practice_attempt" and item.get("status") == "graded")
    ]
    covered_objectives = sum(bool(item.get("evidence_refs")) for item in objectives)
    labeled_weights = [
        (
            "diagnostic_case" if item.get("type") == "diagnostic_case" else "practice_attempt",
            _FORMAL_EVIDENCE_WEIGHTS["diagnostic_case" if item.get("type") == "diagnostic_case" else "practice_attempt"],
        )
        for item in formal
    ]
    score = _log_damped_score(labeled_weights)
    # "strong" still requires breadth across objectives (covered_objectives),
    # not just one deep vein of evidence on a single objective; "moderate" is
    # reached either by a moderately-scored evidence pool or by breadth alone.
    if score >= _FORMAL_STRONG_SCORE and covered_objectives >= 2:
        level = "strong"
    elif score >= _FORMAL_MODERATE_SCORE or covered_objectives >= 2:
        level = "moderate"
    elif catalog:
        level = "limited"
    else:
        level = "none"
    return {
        "level": level,
        "formal_evidence_count": len(formal),
        "total_evidence_count": len(catalog),
        "covered_objective_count": covered_objectives,
        "reason_code": "sufficient_for_bounded_inference" if level in {"moderate", "strong"} else "insufficient_for_stable_inference",
    }


# --- Evidence-driven change-proposal trigger (learning-evidence adaptation) ---
#
# This scores a *single block's* raw evidence events (typically
# `LearningEvent.event_type == "learner_self_reported"`) to decide whether an
# `evaluate_and_propose_change`-style caller (see `learner_model_service.py`)
# should generate a pending `ChangeProposal`. It intentionally reuses the same
# "log-damped, multi-label" scoring philosophy as `_data_sufficiency` above,
# but with a distinct, evidence-specific weight table, because the two
# decisions answer different questions (model-wide confidence vs. a single
# block's need for a supplementary explanation).
#
# `LearningEvent` has no dedicated "intensity"/"strength" field today, so the
# mapping below is a deliberate best-effort classification of the closest
# available signals:
#   - explicit_incomprehension: `learner_self_reported` whose free-text
#     `evidence.statement` contains an unambiguous "I cannot follow this at
#     all" marker (e.g. "完全看不懂"). This is the closest analogue in the
#     current schema to "a single very strong, explicit piece of evidence
#     with a stated reason" from spec Scenario "证据门槛判定" — a single
#     occurrence MUST be able to trigger on its own.
#   - reexplain_request: `learner_self_reported` asking for more detail /
#     re-explanation (e.g. "讲得更详细", "没懂") without declaring total
#     incomprehension. Individually weak; needs to recur or combine with
#     other evidence to be trustworthy.
#   - issue_record: an open `learning_record` of `record_type == "issue"` —
#     the closest existing analogue to an explicit negative rating.
#   - generic_event: any other evidence-bearing event touching the block
#     (e.g. passive re-reads); very weak signal, contributes mostly through
#     volume and is capped by log-damping so it can never dominate.
_INCOMPREHENSION_MARKERS = ("完全看不懂", "完全不懂", "听不懂", "看不懂", "无法理解", "看不明白")
_REEXPLAIN_MARKERS = ("更详细", "再详细", "讲清楚", "没懂", "不太懂", "再解释", "举例", "再讲")

_EVIDENCE_TRIGGER_WEIGHTS: dict[str, float] = {
    "explicit_incomprehension": 5.0,
    "issue_record": 2.5,
    "reexplain_request": 2.0,
    "generic_event": 0.5,
}

# A single event whose recency-adjusted weight clears this bar triggers
# immediately, regardless of how many other events exist (spec: single
# strong evidence MAY trigger without a "multiple occurrences" requirement).
SINGLE_STRONG_EVIDENCE_THRESHOLD = 4.0
# The log-damped, diversity-adjusted aggregate of weaker evidence must clear
# this bar to trigger (spec: weak evidence MUST be judged in combination,
# never by a fixed count alone).
AGGREGATE_TRIGGER_THRESHOLD = 4.0
_RECENT_WINDOW_DAYS = 14
_STALE_RECENCY_MULTIPLIER = 0.6  # time-decayed evidence still counts, but less


def classify_evidence_event(event: dict[str, Any]) -> tuple[str, float]:
    """Map one evidence-bearing event dict to (label, base_weight).

    See the module-level comment above `_INCOMPREHENSION_MARKERS` for the
    mapping rationale.
    """
    event_type = str(event.get("event_type") or "")
    if event_type == "learner_self_reported":
        statement = str((event.get("evidence") or {}).get("statement") or "")
        if any(marker in statement for marker in _INCOMPREHENSION_MARKERS):
            return "explicit_incomprehension", _EVIDENCE_TRIGGER_WEIGHTS["explicit_incomprehension"]
        if any(marker in statement for marker in _REEXPLAIN_MARKERS):
            return "reexplain_request", _EVIDENCE_TRIGGER_WEIGHTS["reexplain_request"]
        return "reexplain_request", _EVIDENCE_TRIGGER_WEIGHTS["reexplain_request"] * 0.5
    if str(event.get("record_type") or "") == "issue":
        return "issue_record", _EVIDENCE_TRIGGER_WEIGHTS["issue_record"]
    return "generic_event", _EVIDENCE_TRIGGER_WEIGHTS["generic_event"]


def _recency_multiplier(created_at: Any, reference: datetime) -> float:
    if not created_at:
        return _STALE_RECENCY_MULTIPLIER
    try:
        observed = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return _STALE_RECENCY_MULTIPLIER
    age_days = (reference - observed).total_seconds() / 86400
    return 1.0 if 0 <= age_days <= _RECENT_WINDOW_DAYS else _STALE_RECENCY_MULTIPLIER


def evaluate_evidence_trigger(
    events: list[dict[str, Any]],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Decide whether one block's evidence events cross the adaptation
    trigger threshold. Pure function — does not read or write any state.

    Returns a dict with `triggered`, `reason_code`, `score`, and
    `matched_labels` so callers/tests can inspect *why* a decision was made,
    not just the boolean outcome.
    """
    if not events:
        return {"triggered": False, "reason_code": "no_evidence", "score": 0.0, "matched_labels": []}

    reference = now or datetime.now(timezone.utc)
    classified = [
        (*classify_evidence_event(event), _recency_multiplier(event.get("created_at"), reference))
        for event in events
    ]

    # Single strong evidence path: one sufficiently strong, recent-enough
    # event is enough on its own (spec Scenario "证据门槛判定").
    strongest_label, strongest_weight, strongest_recency = max(
        classified, key=lambda item: item[1] * item[2]
    )
    strongest_score = strongest_weight * strongest_recency
    if strongest_score >= SINGLE_STRONG_EVIDENCE_THRESHOLD:
        return {
            "triggered": True,
            "reason_code": "single_strong_evidence",
            "score": round(strongest_score, 3),
            "matched_labels": [strongest_label],
        }

    # Weak/aggregate path: combine count + strength + type diversity +
    # recency instead of a fixed occurrence count.
    per_label_weight_sum: dict[str, float] = {}
    per_label_count: dict[str, int] = {}
    for label, weight, recency in classified:
        adjusted = weight * recency
        per_label_weight_sum[label] = per_label_weight_sum.get(label, 0.0) + adjusted
        per_label_count[label] = per_label_count.get(label, 0) + 1
    labels = sorted(per_label_count)
    aggregate_score = sum(
        (per_label_weight_sum[label] / per_label_count[label]) * math.log2(1 + per_label_count[label])
        for label in labels
    )
    diversity_bonus = 1.0 + 0.15 * (len(labels) - 1)
    aggregate_score *= diversity_bonus

    triggered = aggregate_score >= AGGREGATE_TRIGGER_THRESHOLD
    return {
        "triggered": triggered,
        "reason_code": "aggregate_weak_evidence" if triggered else "insufficient_evidence",
        "score": round(aggregate_score, 3),
        "matched_labels": labels,
    }


def _model_item(item: dict[str, Any], *, reason_code: str) -> dict[str, Any]:
    return {
        "objective_id": item.get("objective_id"),
        "objective_revision_id": item.get("objective_revision_id"),
        "node_id": item.get("node_id"),
        "node_name": item.get("node_name"),
        "reason_code": reason_code,
        "confidence": item.get("confidence"),
        "evidence_refs": [ref.get("source_id") for ref in item.get("evidence_refs") or [] if ref.get("source_id")][:5],
        "observed_at": item.get("observed_at"),
        "valid_until": item.get("valid_until"),
    }


def _latest_timestamp(items: list[dict[str, Any]]) -> str | None:
    values = [str(item.get("observed_at") or "") for item in items if item.get("observed_at")]
    return max(values) if values else None


def _valid_until(value: str | None, *, days: int) -> str | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return (parsed + timedelta(days=days)).isoformat()
    except (TypeError, ValueError):
        return None


__all__ = [
    "SCHEMA_VERSION",
    "AGGREGATE_TRIGGER_THRESHOLD",
    "SINGLE_STRONG_EVIDENCE_THRESHOLD",
    "build_learner_model",
    "classify_evidence_event",
    "evaluate_evidence_trigger",
    "is_model_item_current",
    "learner_model_summary",
]
