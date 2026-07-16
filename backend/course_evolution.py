"""Evidence-driven personal adaptation plans and learner-isolated overlays.

The persisted v1 schema and legacy function names remain readable. The
canonical product boundary is explicit: accepted plans project a
``PersonalCourseOverlay`` and never mutate the base ``CourseDocument``.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import threading
from typing import Any, Literal

from pydantic import BaseModel, Field

from course_document import CourseDocument, stable_hash
from course_knowledge_base import compile_course_knowledge_base, knowledge_binding_for_section
from course_revisions import revision_vector_for_document
from learning_events import load_learning_events
from learning_records import learning_record_repository
from practice_attempts import practice_attempt_repository

COURSE_EVOLUTION_SCHEMA = "course_evolution_v1"
HypothesisStatus = Literal[
    "observing", "actionable", "candidate_created", "accepted", "rejected",
    "evaluating", "effective", "ineffective", "harmful", "expired",
]
ChangeSetStatus = Literal["pending", "accepted", "rejected", "applied", "stale", "undone"]


class EvidenceAnchor(BaseModel):
    section_id: str = ""
    block_id: str = ""
    span: dict[str, Any] = Field(default_factory=dict)
    knowledge_node_ids: list[str] = Field(default_factory=list)
    ability_point_ids: list[str] = Field(default_factory=list)
    misconception_point_ids: list[str] = Field(default_factory=list)
    practice_task_id: str = ""
    source_revision: str = ""
    resolution_status: Literal["resolved", "partial", "unresolved"] = "unresolved"


class EvidenceItem(BaseModel):
    evidence_id: str
    user_id: str
    course_id: str
    source_type: Literal["learning_event", "learning_record", "practice_attempt"]
    source_id: str
    evidence_kind: str
    summary: str
    strength: float = 0.0
    is_counterevidence: bool = False
    anchor: EvidenceAnchor
    created_at: str


class AdaptationHypothesis(BaseModel):
    hypothesis_id: str
    user_id: str
    course_id: str
    problem_type: str
    claim: str
    target_block_id: str
    support_evidence_ids: list[str] = Field(default_factory=list)
    counterevidence_ids: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    confidence_reasons: list[str] = Field(default_factory=list)
    recommended_scope: Literal["current", "current_and_next"] = "current"
    affected_block_ids: list[str] = Field(default_factory=list)
    temporary_support: str = ""
    validation_plan: str = ""
    status: HypothesisStatus = "observing"
    created_at: str
    updated_at: str


class PersonalAdaptationOperation(BaseModel):
    operation_id: str
    operation_type: Literal[
        "INSERT_PERSONAL_SUPPORT",
        "ADD_TRANSITION_SUPPORT",
        "ADD_CHECKPOINT",
        "ADD_ANIMATION",
    ]
    target_block_id: str
    target_section_id: str = ""
    scope: Literal["current", "next"] = "current"
    reason: str
    payload: dict[str, Any] = Field(default_factory=dict)


class AnimationKeyframe(BaseModel):
    index: int
    label: str
    state: dict[str, str] = Field(default_factory=dict)
    transformations: list[str] = Field(default_factory=list)
    duration_ms: int = 1200
    pause_after: bool = True


class AnimationSpec(BaseModel):
    schema_version: Literal["animation_spec_v1"] = "animation_spec_v1"
    animation_id: str
    title: str
    scene: dict[str, str] = Field(default_factory=dict)
    object_bindings: list[dict[str, Any]] = Field(default_factory=list)
    knowledge_refs: list[str] = Field(default_factory=list)
    keyframes: list[AnimationKeyframe] = Field(default_factory=list)
    fallback_frames: list[dict[str, Any]] = Field(default_factory=list)
    accessibility_text: str = ""


class PersonalAdaptationPlan(BaseModel):
    plan_kind: Literal["personal_adaptation_plan"] = "personal_adaptation_plan"
    write_target: Literal["personal_overlay"] = "personal_overlay"
    change_set_id: str
    user_id: str
    course_id: str
    hypothesis_id: str
    replaces_change_set_id: str = ""
    base_revision_vector: dict[str, str] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    operations: list[PersonalAdaptationOperation] = Field(default_factory=list)
    allowed_scopes: list[Literal["current", "current_and_next"]] = Field(default_factory=list)
    selected_scope: Literal["current", "current_and_next"] | None = None
    impact_summary: dict[str, Any] = Field(default_factory=dict)
    expected_effect: str
    status: ChangeSetStatus = "pending"
    created_at: str
    updated_at: str
    accepted_at: str | None = None
    resolved_at: str | None = None
    effect_evaluation: dict[str, Any] = Field(default_factory=dict)


class CourseEvolutionState(BaseModel):
    schema_version: Literal["course_evolution_v1"] = COURSE_EVOLUTION_SCHEMA
    user_id: str
    course_id: str
    evidence_items: list[EvidenceItem] = Field(default_factory=list)
    hypotheses: list[AdaptationHypothesis] = Field(default_factory=list)
    change_sets: list[PersonalAdaptationPlan] = Field(default_factory=list)
    revision: str = ""
    updated_at: str


class PersonalCourseOverlay(BaseModel):
    schema_version: Literal["personal_course_overlay_v1"] = "personal_course_overlay_v1"
    overlay_id: str
    user_id: str
    course_id: str
    base_revision_vector: dict[str, str] = Field(default_factory=dict)
    active_plan_ids: list[str] = Field(default_factory=list)
    operations: list[PersonalAdaptationOperation] = Field(default_factory=list)
    revision: str
    updated_at: str


# Compatibility aliases for persisted v1 data and imports. New code should use
# PersonalAdaptationPlan and PersonalAdaptationOperation.
CourseEvolutionOperation = PersonalAdaptationOperation
CourseEvolutionChangeSet = PersonalAdaptationPlan


class CourseEvolutionRepository:
    def __init__(self, root: str | Path | None = None) -> None:
        if root is None:
            from storage import DATA_DIR

            root = Path(DATA_DIR) / "course_evolution"
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, threading.RLock] = {}
        self._guard = threading.Lock()

    def load(self, user_id: str, course_id: str) -> CourseEvolutionState:
        key = self._key(user_id, course_id)
        path = self.root / f"{key}.json"
        with self._lock(key):
            if not path.exists():
                return self._refresh(CourseEvolutionState(
                    user_id=user_id,
                    course_id=course_id,
                    updated_at=_now(),
                ))
            with path.open(encoding="utf-8") as handle:
                state = CourseEvolutionState.model_validate(json.load(handle))
            if state.user_id != user_id or state.course_id != course_id:
                raise ValueError("Course evolution state belongs to another learner or course")
            return state

    def save(self, state: CourseEvolutionState) -> CourseEvolutionState:
        key = self._key(state.user_id, state.course_id)
        path = self.root / f"{key}.json"
        with self._lock(key):
            value = self._refresh(state)
            temp = path.with_suffix(f".{threading.get_ident()}.tmp")
            try:
                with temp.open("w", encoding="utf-8") as handle:
                    json.dump(value.model_dump(mode="json"), handle, ensure_ascii=False, indent=2)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp, path)
            finally:
                if temp.exists():
                    temp.unlink()
            return value

    @staticmethod
    def _key(user_id: str, course_id: str) -> str:
        return hashlib.sha256(f"{user_id}\0{course_id}".encode()).hexdigest()

    def _lock(self, key: str) -> threading.RLock:
        with self._guard:
            return self._locks.setdefault(key, threading.RLock())

    @staticmethod
    def _refresh(state: CourseEvolutionState) -> CourseEvolutionState:
        state.updated_at = _now()
        payload = state.model_dump(mode="json", exclude={"revision", "updated_at"})
        state.revision = stable_hash(payload, prefix="cev_")
        return state


def synchronize_and_evaluate_course_evolution(
    course_data: dict[str, Any],
    *,
    user_id: str,
    repository: CourseEvolutionRepository | None = None,
) -> CourseEvolutionState:
    repository = repository or course_evolution_repository
    course_id = str(course_data.get("course_id") or "")
    if not course_id or not user_id:
        raise ValueError("Course and learner identifiers are required")
    document = _course_document(course_data)
    # Knowledge compilation normalizes legacy fields in-place. Personal
    # adaptation is a read-only consumer, so compile from an isolated snapshot.
    knowledge_base = compile_course_knowledge_base(deepcopy(course_data))
    state = repository.load(user_id, course_id)
    state.evidence_items = _collect_evidence(
        course_data,
        document,
        user_id=user_id,
        knowledge_base=knowledge_base,
    )
    _evaluate_hypotheses_and_candidates(
        state,
        document,
        knowledge_base=knowledge_base,
    )
    _evaluate_applied_effects(state, user_id=user_id)
    return repository.save(state)


def accept_change_set(
    course_data: dict[str, Any],
    *,
    user_id: str,
    change_set_id: str,
    selected_scope: Literal["current", "current_and_next"],
    repository: CourseEvolutionRepository | None = None,
) -> CourseEvolutionState:
    repository = repository or course_evolution_repository
    document = _course_document(course_data)
    state = repository.load(user_id, document.course_id)
    change_set = _change_set(state, change_set_id)
    if change_set.status == "applied" and change_set.selected_scope == selected_scope:
        return state
    if change_set.status != "pending":
        raise ValueError(f"Course change set cannot be accepted from {change_set.status}")
    if selected_scope not in change_set.allowed_scopes:
        raise ValueError("Selected scope is not allowed for this change set")
    current_vector = revision_vector_for_document(document).revisions
    for key, revision in change_set.base_revision_vector.items():
        if key in current_vector and current_vector[key] != revision:
            change_set.status = "stale"
            change_set.updated_at = _now()
            repository.save(state)
            raise ValueError("Course changed after this candidate was generated")
    change_set.selected_scope = selected_scope
    change_set.status = "applied"
    change_set.accepted_at = _now()
    change_set.resolved_at = change_set.accepted_at
    change_set.updated_at = change_set.accepted_at
    if change_set.replaces_change_set_id:
        replaced = _change_set(state, change_set.replaces_change_set_id)
        if replaced.status != "applied":
            raise ValueError("Replaced personal adaptation is no longer active")
        replaced.status = "undone"
        replaced.resolved_at = change_set.accepted_at
        replaced.updated_at = change_set.accepted_at
        replaced.effect_evaluation = {
            **replaced.effect_evaluation,
            "resolution": "replaced_by_adjustment",
            "replacement_change_set_id": change_set.change_set_id,
        }
    hypothesis = _hypothesis(state, change_set.hypothesis_id)
    hypothesis.status = "evaluating"
    hypothesis.updated_at = change_set.accepted_at
    return repository.save(state)


def create_adjustment_plan(
    *,
    user_id: str,
    course_id: str,
    change_set_id: str,
    repository: CourseEvolutionRepository | None = None,
) -> CourseEvolutionState:
    """Create a reviewable replacement after an applied plan proves ineffective."""
    repository = repository or course_evolution_repository
    state = repository.load(user_id, course_id)
    source = _change_set(state, change_set_id)
    effect_status = str(source.effect_evaluation.get("status") or "")
    if source.status != "applied" or effect_status not in {"ineffective", "harmful"}:
        raise ValueError("Only ineffective or harmful active adaptations can be adjusted")
    existing = next((
        item for item in state.change_sets
        if item.replaces_change_set_id == source.change_set_id and item.status == "pending"
    ), None)
    if existing:
        return state

    operations: list[PersonalAdaptationOperation] = []
    for operation in source.operations:
        payload = deepcopy(operation.payload)
        if operation.operation_type == "INSERT_PERSONAL_SUPPORT":
            payload["body"] = (
                "改用具体状态对照：先指出变化前的对象，再逐步说明每次操作改变了什么，"
                "最后让学习者用自己的话连接操作与结论。"
            )
            payload["contrast"] = "替换上一版抽象解释；基础课程正文保持不变。"
        elif operation.operation_type == "ADD_ANIMATION":
            payload["animation_spec"] = _adjusted_animation_spec(
                payload.get("animation_spec") or {},
                source.change_set_id,
            )
            payload["steps"] = [
                {"index": frame.get("index"), "label": frame.get("label")}
                for frame in payload["animation_spec"].get("fallback_frames") or []
            ]
        elif operation.operation_type == "ADD_CHECKPOINT":
            payload["body"] = "比较两个具体状态，指出哪一步改变了对象之间的关系。"
            payload["prompt"] = "请先指认变化，再解释原因；不要只复述计算步骤。"
        operations.append(operation.model_copy(update={
            "operation_id": stable_hash({
                "source_operation_id": operation.operation_id,
                "adjustment": "state_contrast_v1",
            }, prefix="ceo_"),
            "reason": "后续证据显示上一版支持未达到预期，改用具体状态对照并缩短推理跨度。",
            "payload": payload,
        }, deep=True))

    now = _now()
    replacement = PersonalAdaptationPlan(
        change_set_id=stable_hash({
            "source_change_set_id": source.change_set_id,
            "effect_evaluation": source.effect_evaluation,
            "adjustment": "state_contrast_v1",
        }, prefix="ces_"),
        user_id=user_id,
        course_id=course_id,
        hypothesis_id=source.hypothesis_id,
        replaces_change_set_id=source.change_set_id,
        base_revision_vector=deepcopy(source.base_revision_vector),
        evidence_ids=list(source.evidence_ids),
        operations=operations,
        allowed_scopes=list(source.allowed_scopes),
        impact_summary={
            **deepcopy(source.impact_summary),
            "adjustment_of": source.change_set_id,
            "protected": list(source.impact_summary.get("protected") or []),
        },
        expected_effect="用更具体的状态对照替换无效支持，再通过同能力任务复验。",
        created_at=now,
        updated_at=now,
    )
    state.change_sets.append(replacement)
    return repository.save(state)


def reject_change_set(
    *,
    user_id: str,
    course_id: str,
    change_set_id: str,
    reason: str = "",
    repository: CourseEvolutionRepository | None = None,
) -> CourseEvolutionState:
    repository = repository or course_evolution_repository
    state = repository.load(user_id, course_id)
    change_set = _change_set(state, change_set_id)
    if change_set.status != "pending":
        raise ValueError(f"Course change set cannot be rejected from {change_set.status}")
    change_set.status = "rejected"
    change_set.resolved_at = _now()
    change_set.updated_at = change_set.resolved_at
    change_set.effect_evaluation = {
        "status": "not_applied",
        "reason": reason,
        "cooldown_until": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
    }
    hypothesis = _hypothesis(state, change_set.hypothesis_id)
    hypothesis.status = "rejected"
    hypothesis.updated_at = change_set.resolved_at
    return repository.save(state)


def undo_change_set(
    *,
    user_id: str,
    course_id: str,
    change_set_id: str,
    repository: CourseEvolutionRepository | None = None,
) -> CourseEvolutionState:
    repository = repository or course_evolution_repository
    state = repository.load(user_id, course_id)
    change_set = _change_set(state, change_set_id)
    if change_set.status != "applied":
        raise ValueError(f"Course change set cannot be undone from {change_set.status}")
    change_set.status = "undone"
    change_set.resolved_at = _now()
    change_set.updated_at = change_set.resolved_at
    hypothesis = _hypothesis(state, change_set.hypothesis_id)
    hypothesis.status = "observing"
    hypothesis.updated_at = change_set.resolved_at
    return repository.save(state)


def project_applied_adaptive_blocks(
    state: CourseEvolutionState,
    *,
    node_id: str | None = None,
) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for change_set in state.change_sets:
        if change_set.status != "applied":
            continue
        for operation in change_set.operations:
            if change_set.selected_scope == "current" and operation.scope == "next":
                continue
            target_node_id = operation.target_section_id or operation.target_block_id
            if node_id and target_node_id != node_id:
                continue
            kind = {
                "INSERT_PERSONAL_SUPPORT": "explanation",
                "ADD_TRANSITION_SUPPORT": "transition",
                "ADD_CHECKPOINT": "understanding_check",
                "ADD_ANIMATION": "animation",
            }[operation.operation_type]
            blocks.append({
                "adaptive_block_id": operation.operation_id,
                "change_set_id": change_set.change_set_id,
                "anchor": {
                    "node_id": target_node_id,
                    "content_block_id": operation.target_block_id,
                    "placement": "after_block",
                },
                "kind": kind,
                "role": "accepted_personal_course_growth",
                "payload": {
                    "body": str(operation.payload.get("body") or ""),
                    "contrast": str(operation.payload.get("contrast") or ""),
                    "prompt": str(operation.payload.get("prompt") or ""),
                    "objective": str(operation.payload.get("objective") or ""),
                    "steps": operation.payload.get("steps") or [],
                    "animation_spec": deepcopy(operation.payload.get("animation_spec") or {}),
                    "knowledge_refs": list(operation.payload.get("knowledge_refs") or []),
                    "ability_refs": list(operation.payload.get("ability_refs") or []),
                    "expected_effect": str(operation.payload.get("expected_effect") or ""),
                },
                "reason_code": "accepted_evidence_driven_growth",
                "evidence_refs": change_set.evidence_ids,
                "status": "active",
                "expires_at": "",
                "feedback": {"value": "unrated", "options": ["helpful", "not_helpful", "dismissed"]},
            })
    return blocks


def personal_course_overlay(state: CourseEvolutionState) -> PersonalCourseOverlay:
    active_plans = [item for item in state.change_sets if item.status == "applied"]
    operations = [
        operation.model_copy(deep=True)
        for plan in active_plans
        for operation in plan.operations
        if plan.selected_scope != "current" or operation.scope != "next"
    ]
    base_revision_vector: dict[str, str] = {}
    for plan in active_plans:
        base_revision_vector.update(plan.base_revision_vector)
    updated_at = max(
        [item.updated_at for item in active_plans] or [state.updated_at],
    )
    payload = {
        "user_id": state.user_id,
        "course_id": state.course_id,
        "base_revision_vector": base_revision_vector,
        "active_plan_ids": [item.change_set_id for item in active_plans],
        "operations": [item.model_dump(mode="json") for item in operations],
    }
    return PersonalCourseOverlay(
        overlay_id=stable_hash(
            {"user_id": state.user_id, "course_id": state.course_id},
            prefix="pco_",
        ),
        user_id=state.user_id,
        course_id=state.course_id,
        base_revision_vector=base_revision_vector,
        active_plan_ids=payload["active_plan_ids"],
        operations=operations,
        revision=stable_hash(payload, prefix="pcr_"),
        updated_at=updated_at,
    )


def course_evolution_view(state: CourseEvolutionState) -> dict[str, Any]:
    payload = state.model_dump(mode="json")
    payload["view_schema_version"] = "personal_course_adaptation_v1"
    payload["adaptation_plans"] = deepcopy(payload["change_sets"])
    for plan in payload["adaptation_plans"]:
        plan["plan_id"] = plan["change_set_id"]
        plan["plan_kind"] = "personal_adaptation_plan"
    payload["personal_course_overlay"] = personal_course_overlay(state).model_dump(mode="json")
    payload["permissions"] = {
        "write_target": "personal_overlay",
        "can_modify_base_course": False,
        "can_modify_other_learners": False,
        "can_modify_course_knowledge_base": False,
    }
    payload["summary"] = {
        "evidence_count": len(state.evidence_items),
        "actionable_hypothesis_count": sum(
            item.status in {"actionable", "candidate_created", "evaluating"}
            for item in state.hypotheses
        ),
        "pending_change_set_count": sum(item.status == "pending" for item in state.change_sets),
        "applied_change_set_count": sum(item.status == "applied" for item in state.change_sets),
    }
    return payload


def _collect_evidence(
    course_data: dict[str, Any],
    document: CourseDocument,
    *,
    user_id: str,
    knowledge_base: dict[str, Any] | None = None,
) -> list[EvidenceItem]:
    course_id = document.course_id
    items: list[EvidenceItem] = []
    for event in load_learning_events(user_id=user_id, course_id=course_id):
        source_id = str(event.get("event_id") or "")
        if not source_id:
            continue
        kind, strength, counter = _event_signal(event)
        if strength <= 0:
            continue
        summary = _event_summary(event)
        items.append(EvidenceItem(
            evidence_id=stable_hash({"type": "learning_event", "id": source_id}, prefix="evi_"),
            user_id=user_id,
            course_id=course_id,
            source_type="learning_event",
            source_id=source_id,
            evidence_kind=kind,
            summary=summary,
            strength=strength,
            is_counterevidence=counter,
            anchor=_resolve_anchor(document, event, knowledge_base=knowledge_base),
            created_at=str(event.get("created_at") or _now()),
        ))
    for record in learning_record_repository.list(user_id, course_id):
        if record.get("status") == "archived":
            continue
        source_id = str(record.get("record_id") or "")
        record_type = str(record.get("record_type") or "")
        strength = {"issue": 0.68, "note": 0.5, "review_task": 0.58, "bookmark": 0.15}.get(record_type, 0.0)
        if not source_id or strength <= 0:
            continue
        items.append(EvidenceItem(
            evidence_id=stable_hash({"type": "learning_record", "id": source_id}, prefix="evi_"),
            user_id=user_id,
            course_id=course_id,
            source_type="learning_record",
            source_id=source_id,
            evidence_kind=f"record_{record_type}",
            summary=_compact(record.get("content") or record.get("quote") or record.get("title")),
            strength=strength,
            is_counterevidence=record.get("status") in {"resolved", "completed"},
            anchor=_resolve_anchor(document, record, knowledge_base=knowledge_base),
            created_at=str(record.get("created_at") or _now()),
        ))
    for attempt in practice_attempt_repository.list(user_id, course_id):
        if attempt.get("status") != "graded":
            continue
        source_id = str(attempt.get("attempt_id") or "")
        result = attempt.get("result") or {}
        passed = result.get("passed") is True
        confidence = float(result.get("grading_confidence") or 0.5)
        strength = min(0.95, 0.62 + confidence * 0.35)
        if not source_id:
            continue
        items.append(EvidenceItem(
            evidence_id=stable_hash({"type": "practice_attempt", "id": source_id}, prefix="evi_"),
            user_id=user_id,
            course_id=course_id,
            source_type="practice_attempt",
            source_id=source_id,
            evidence_kind="formal_success" if passed else "formal_failure",
            summary="正式练习已通过" if passed else _compact(result.get("feedback") or "正式练习未通过"),
            strength=strength,
            is_counterevidence=passed,
            anchor=_resolve_anchor(document, attempt, knowledge_base=knowledge_base),
            created_at=str(attempt.get("graded_at") or attempt.get("updated_at") or _now()),
        ))
    return sorted(items, key=lambda item: item.created_at)


def _evaluate_hypotheses_and_candidates(
    state: CourseEvolutionState,
    document: CourseDocument,
    *,
    knowledge_base: dict[str, Any] | None = None,
) -> None:
    grouped: dict[str, list[EvidenceItem]] = {}
    for item in state.evidence_items:
        if item.anchor.block_id:
            grouped.setdefault(item.anchor.block_id, []).append(item)
    for block_id, evidence in grouped.items():
        positive = [item for item in evidence if not item.is_counterevidence]
        counter = [item for item in evidence if item.is_counterevidence]
        if not positive:
            continue
        score = _combined_strength(positive, counter)
        source_types = {item.source_type for item in positive}
        strongest = max(item.strength for item in positive)
        actionable = strongest >= 0.82 or score >= 1.18
        scope = "current_and_next" if (
            actionable
            and len(source_types) >= 2
            and any(item.evidence_kind == "formal_failure" for item in positive)
        ) else "current"
        hypothesis_id = stable_hash({
            "user_id": state.user_id,
            "course_id": state.course_id,
            "block_id": block_id,
            "problem_type": "conceptual_gap",
        }, prefix="ahp_")
        now = _now()
        hypothesis = next((item for item in state.hypotheses if item.hypothesis_id == hypothesis_id), None)
        affected = _affected_blocks(
            document,
            block_id,
            scope=scope,
            knowledge_base=knowledge_base,
        )
        if hypothesis is None:
            hypothesis = AdaptationHypothesis(
                hypothesis_id=hypothesis_id,
                user_id=state.user_id,
                course_id=state.course_id,
                problem_type="conceptual_gap",
                claim="学习者可能会操作步骤，但尚未建立当前概念的原因、条件与后续推导之间的联系。",
                target_block_id=block_id,
                created_at=now,
                updated_at=now,
            )
            state.hypotheses.append(hypothesis)
        hypothesis.support_evidence_ids = [item.evidence_id for item in positive]
        hypothesis.counterevidence_ids = [item.evidence_id for item in counter]
        hypothesis.confidence = round(score, 3)
        hypothesis.confidence_reasons = _confidence_reasons(positive, counter, source_types)
        hypothesis.recommended_scope = scope
        hypothesis.affected_block_ids = affected
        hypothesis.temporary_support = "先在当前位置补充原因解释、分步演示和一次不计入掌握的理解检查。"
        hypothesis.validation_plan = "观察后续同能力正式题、求助次数和对新增支持的反馈。"
        hypothesis.updated_at = now
        if counter and _combined_strength([], counter) <= -0.8:
            hypothesis.status = "expired"
            continue
        if not actionable:
            if hypothesis.status not in {"accepted", "evaluating", "effective"}:
                hypothesis.status = "observing"
            continue
        if hypothesis.status in {"rejected", "accepted", "evaluating", "effective"}:
            continue
        hypothesis.status = "actionable"
        evidence_signature = stable_hash(sorted(hypothesis.support_evidence_ids), prefix="esg_")
        existing = next((
            item for item in state.change_sets
            if item.hypothesis_id == hypothesis_id
            and item.evidence_ids == hypothesis.support_evidence_ids
            and item.status in {"pending", "applied"}
        ), None)
        if existing:
            hypothesis.status = "candidate_created" if existing.status == "pending" else "evaluating"
            continue
        rejected = next((
            item for item in reversed(state.change_sets)
            if item.hypothesis_id == hypothesis_id and item.status == "rejected"
        ), None)
        cooldown = str((rejected.effect_evaluation if rejected else {}).get("cooldown_until") or "")
        if cooldown and cooldown > now:
            continue
        change_set = _build_change_set(
            state,
            document,
            hypothesis,
            evidence_signature=evidence_signature,
            knowledge_base=knowledge_base,
        )
        state.change_sets.append(change_set)
        hypothesis.status = "candidate_created"


def _build_change_set(
    state: CourseEvolutionState,
    document: CourseDocument,
    hypothesis: AdaptationHypothesis,
    *,
    evidence_signature: str,
    knowledge_base: dict[str, Any] | None = None,
) -> PersonalAdaptationPlan:
    blocks = {item.block_id: item for item in document.blocks}
    sections = {item.section_id: item for item in document.sections}
    target = blocks[hypothesis.target_block_id]
    target_text = _block_text(target.payload)
    target_title = str(target.payload.get("title") or sections.get(target.section_id, {}).title if sections.get(target.section_id) else "当前内容")
    target_binding = _knowledge_binding_for_anchor(
        knowledge_base or {},
        section_id=target.section_id,
        block_id=target.block_id,
    )
    operations: list[PersonalAdaptationOperation] = []

    def append_operation(operation_type: str, block_id: str, scope: str, reason: str, payload: dict[str, Any]) -> None:
        block = blocks[block_id]
        operation_payload = {
            "change_set_seed": evidence_signature,
            "operation_type": operation_type,
            "block_id": block_id,
            "scope": scope,
            "payload": payload,
        }
        operations.append(PersonalAdaptationOperation(
            operation_id=stable_hash(operation_payload, prefix="ceo_"),
            operation_type=operation_type,
            target_block_id=block_id,
            target_section_id=block.section_id,
            scope=scope,
            reason=reason,
            payload=payload,
        ))

    append_operation(
        "INSERT_PERSONAL_SUPPORT",
        target.block_id,
        "current",
        "当前证据指向概念原因与计算步骤之间的断裂。",
        {
            "body": f"先不要只记步骤。围绕“{target_title}”，把它看成一次关系或过程：先说明为什么需要这一步，再说明每一步改变了什么，最后回到原结论。",
            "contrast": f"原内容保留不变；这段个人补充只负责连接“怎么做”和“为什么”。原段核心：{target_text[:120]}",
            "objective": "能够解释步骤背后的原因，并把原因迁移到下一处推导。",
        },
    )
    append_operation(
        "ADD_ANIMATION",
        target.block_id,
        "current",
        "空间或过程关系优先使用分步表达，而不是继续堆文字。",
        {
            "body": "分步演示：每一步只改变一个对象，并在变化后暂停检查。",
            "animation_spec": _animation_spec_for_block(
                target,
                title=target_title,
                evidence_signature=evidence_signature,
                knowledge_refs=target_binding["knowledge_ids"],
            ),
            "steps": _animation_fallback_steps(),
            "contrast": "若动态演示不可用，使用同样三步的静态分解图。",
        },
    )
    append_operation(
        "ADD_CHECKPOINT",
        target.block_id,
        "current",
        "需要用一次低风险检查确认新增解释是否真的建立了联系。",
        {
            "body": "用自己的话说明：这一步为什么必要？如果省略，会在哪个后续结论上出错？",
            "prompt": "请不用复述公式，只解释这一步的作用与后果。",
            "objective": "验证概念原因，而不是重复计算。",
            "knowledge_refs": target_binding["knowledge_ids"],
            "ability_refs": target_binding["skill_ids"],
            "expected_effect": "能够解释当前操作的语义作用，并迁移到后续同能力任务。",
        },
    )
    for block_id in hypothesis.affected_block_ids[1:]:
        block = blocks[block_id]
        title = str(block.payload.get("title") or sections.get(block.section_id, {}).title if sections.get(block.section_id) else "后续内容")
        append_operation(
            "ADD_TRANSITION_SUPPORT",
            block_id,
            "next",
            "当前概念是后续推导的前置，需要提前补一条承接而不是重写后文。",
            {
                "body": f"进入“{title}”前，先回看上一处概念在这里承担什么作用，再继续当前推导。",
                "objective": "把当前理解迁移到后续节点。",
            },
        )
    now = _now()
    vector = revision_vector_for_document(document).revisions
    affected_section_ids = {
        blocks[block_id].section_id
        for block_id in hypothesis.affected_block_ids
        if block_id in blocks
    }
    bound_keys = {
        key: value
        for key, value in vector.items()
        if key in {f"block:{block_id}" for block_id in hypothesis.affected_block_ids}
        or key in {f"section:{section_id}" for section_id in affected_section_ids}
    }
    linked_evidence = [
        item for item in state.evidence_items
        if item.evidence_id in hypothesis.support_evidence_ids
    ]
    knowledge_ids = {
        value for item in linked_evidence for value in item.anchor.knowledge_node_ids
    }
    ability_ids = {
        value for item in linked_evidence for value in item.anchor.ability_point_ids
    }
    misconception_ids = {
        value for item in linked_evidence for value in item.anchor.misconception_point_ids
    }
    return PersonalAdaptationPlan(
        change_set_id=stable_hash({
            "user_id": state.user_id,
            "course_id": state.course_id,
            "hypothesis_id": hypothesis.hypothesis_id,
            "evidence_signature": evidence_signature,
        }, prefix="ces_"),
        user_id=state.user_id,
        course_id=state.course_id,
        hypothesis_id=hypothesis.hypothesis_id,
        base_revision_vector=bound_keys,
        evidence_ids=hypothesis.support_evidence_ids,
        operations=operations,
        allowed_scopes=["current", "current_and_next"] if len(hypothesis.affected_block_ids) > 1 else ["current"],
        impact_summary={
            "direct_block_ids": [hypothesis.target_block_id],
            "dependent_block_ids": hypothesis.affected_block_ids[1:],
            "knowledge_node_ids": sorted({
                value for item in linked_evidence for value in item.anchor.knowledge_node_ids
            }),
            "ability_point_ids": sorted({
                value for item in linked_evidence for value in item.anchor.ability_point_ids
            }),
            "misconception_point_ids": sorted({
                value for item in linked_evidence for value in item.anchor.misconception_point_ids
            }),
            "knowledge_labels": _knowledge_labels(knowledge_base, knowledge_ids),
            "ability_labels": _ability_labels(knowledge_base, ability_ids),
            "misconception_labels": _misconception_labels(knowledge_base, misconception_ids),
            "affected_section_ids": sorted(affected_section_ids),
            "protected": ["基础课程", "其他学习者课程", "历史作答", "笔记原文", "正式知识库"],
            "representation_impacts": ["个人讲义补充", "分步演示", "理解检查"],
        },
        expected_effect="减少同类概念求助，并提高后续独立解释与正式练习表现。",
        created_at=now,
        updated_at=now,
    )


def _animation_fallback_steps() -> list[dict[str, Any]]:
    return [
        {"index": 1, "label": "确定输入、对象与目标"},
        {"index": 2, "label": "执行当前变换并观察中间状态"},
        {"index": 3, "label": "把中间状态连接到最终结论"},
    ]


def _animation_spec_for_block(
    block: Any,
    *,
    title: str,
    evidence_signature: str,
    knowledge_refs: list[str],
) -> dict[str, Any]:
    fallback = _animation_fallback_steps()
    keyframes = [
        AnimationKeyframe(
            index=1,
            label=fallback[0]["label"],
            state={"focus": "input", "description": "标出起始对象和预期结果"},
            transformations=["highlight_input", "highlight_goal"],
        ),
        AnimationKeyframe(
            index=2,
            label=fallback[1]["label"],
            state={"focus": "transition", "description": "只执行一个变换并保留中间状态"},
            transformations=["apply_single_transform", "hold_intermediate_state"],
        ),
        AnimationKeyframe(
            index=3,
            label=fallback[2]["label"],
            state={"focus": "result", "description": "比较中间状态和最终结论"},
            transformations=["connect_intermediate_to_result", "show_semantic_relation"],
        ),
    ]
    spec = AnimationSpec(
        animation_id=stable_hash({
            "block_id": block.block_id,
            "evidence_signature": evidence_signature,
            "kind": "personal_state_transition",
        }, prefix="ans_"),
        title=f"{title}：分步变换演示",
        scene={
            "kind": "state_transition",
            "renderer": "step_timeline_v1",
            "fallback": "static_keyframes",
        },
        object_bindings=[{
            "object_id": f"course-block:{block.block_id}",
            "object_type": "course_block",
            "role": "semantic_source",
        }],
        knowledge_refs=_unique([*knowledge_refs, *block.concept_refs]),
        keyframes=keyframes,
        fallback_frames=[
            {
                **step,
                "description": keyframes[index].state["description"],
            }
            for index, step in enumerate(fallback)
        ],
        accessibility_text=(
            "动画依次展示输入与目标、单步变换及中间状态、最终结论之间的联系；"
            "每一帧均可暂停并以静态文字步骤阅读。"
        ),
    )
    return spec.model_dump(mode="json")


def _adjusted_animation_spec(
    source: dict[str, Any],
    source_change_set_id: str,
) -> dict[str, Any]:
    value = deepcopy(source)
    value["schema_version"] = "animation_spec_v1"
    value["animation_id"] = stable_hash({
        "source_animation_id": source.get("animation_id"),
        "source_change_set_id": source_change_set_id,
        "adjustment": "state_contrast_v1",
    }, prefix="ans_")
    value["title"] = f"{source.get('title') or '分步演示'}（状态对照版）"
    value["scene"] = {
        **(source.get("scene") or {}),
        "comparison_mode": "before_after",
    }
    for frame in value.get("keyframes") or []:
        frame["transformations"] = [
            *(frame.get("transformations") or []),
            "compare_before_after",
        ]
    return value


def _evaluate_applied_effects(state: CourseEvolutionState, *, user_id: str) -> None:
    events = load_learning_events(user_id=user_id, course_id=state.course_id)
    attempts = practice_attempt_repository.list(user_id, state.course_id)
    for change_set in state.change_sets:
        if change_set.status != "applied" or not change_set.accepted_at:
            continue
        feedback = [
            item for item in events
            if item.get("event_type") == "adaptive_block_feedback"
            and str(item.get("created_at") or "") >= change_set.accepted_at
            and str((item.get("metadata") or {}).get("adaptive_block_id") or "")
            in {operation.operation_id for operation in change_set.operations}
        ]
        later_attempts = [
            item for item in attempts
            if item.get("status") == "graded"
            and str(item.get("graded_at") or item.get("updated_at") or "") >= change_set.accepted_at
            and _attempt_matches_change_set(item, change_set)
        ]
        helpful = any((item.get("result") or {}).get("feedback") == "helpful" for item in feedback)
        unhelpful = any((item.get("result") or {}).get("feedback") == "not_helpful" for item in feedback)
        passed = any((item.get("result") or {}).get("passed") is True for item in later_attempts)
        failed = sum((item.get("result") or {}).get("passed") is False for item in later_attempts)
        if helpful and passed:
            status = "effective"
        elif unhelpful and failed >= 2:
            status = "harmful"
        elif unhelpful or failed >= 2:
            status = "ineffective"
        else:
            status = "insufficient_evidence"
        change_set.effect_evaluation = {
            "status": status,
            "feedback_event_ids": [item.get("event_id") for item in feedback],
            "attempt_ids": [item.get("attempt_id") for item in later_attempts],
            "recommended_action": (
                "keep" if status == "effective"
                else "rollback" if status == "harmful"
                else "adjust" if status == "ineffective"
                else "collect_more_evidence"
            ),
            "follow_up_candidate": (
                {
                    "candidate_type": "rollback_personal_adaptation",
                    "status": "pending_confirmation",
                    "source_change_set_id": change_set.change_set_id,
                    "reason": "负面反馈与重复失败同时出现，建议撤销当前个人适配。",
                }
                if status == "harmful"
                else {
                    "candidate_type": "adjust_personal_adaptation",
                    "status": "available",
                    "source_change_set_id": change_set.change_set_id,
                    "reason": "当前支持没有改善后续表现，可生成另一种解释与检查方案。",
                }
                if status == "ineffective"
                else {}
            ),
            "evaluated_at": _now(),
        }
        hypothesis = _hypothesis(state, change_set.hypothesis_id)
        if status in {"effective", "ineffective", "harmful"}:
            hypothesis.status = status
            hypothesis.updated_at = _now()


def _attempt_matches_change_set(
    attempt: dict[str, Any],
    change_set: PersonalAdaptationPlan,
) -> bool:
    impact = change_set.impact_summary
    section_ids = set(impact.get("affected_section_ids") or [])
    node_id = str(attempt.get("node_id") or (attempt.get("context") or {}).get("node_id") or "")
    if node_id and node_id in section_ids:
        return True

    knowledge_ids = set(impact.get("knowledge_node_ids") or [])
    ability_ids = set(impact.get("ability_point_ids") or [])
    result = attempt.get("result") or {}
    attempt_knowledge = {
        str(value) for value in [
            *(attempt.get("concept_ids") or []),
            *(attempt.get("course_knowledge_refs") or []),
            *(result.get("concept_ids") or []),
            *(result.get("course_knowledge_refs") or []),
        ] if value
    }
    attempt_abilities = {
        str(value) for value in [
            *(attempt.get("skill_unit_ids") or []),
            *(attempt.get("ability_point_ids") or []),
            *(result.get("skill_unit_ids") or []),
            *(result.get("ability_point_ids") or []),
        ] if value
    }
    return bool(
        (knowledge_ids and attempt_knowledge & knowledge_ids)
        or (ability_ids and attempt_abilities & ability_ids)
    )


def _event_signal(event: dict[str, Any]) -> tuple[str, float, bool]:
    event_type = str(event.get("event_type") or "")
    statement = str((event.get("evidence") or {}).get("statement") or "")
    feedback = str((event.get("result") or {}).get("feedback") or "")
    if event_type == "learner_self_reported":
        explicit = any(marker in statement for marker in ("完全看不懂", "不理解为什么", "推导跳步", "还是没懂", "没有解决"))
        return "explicit_comprehension_gap", 0.9 if explicit else 0.56, False
    if event_type == "assistant_question_submitted":
        question = str((event.get("evidence") or {}).get("question") or "")
        explicit = any(marker in question for marker in (
            "完全看不懂", "不理解为什么", "为什么要", "推导跳步", "还是没懂", "不会",
        ))
        return "learner_question", 0.84 if explicit else 0.48, False
    if event_type == "assistant_answer_feedback_submitted":
        return "assistant_feedback", 0.72 if feedback == "unclear" else 0.55, feedback in {"resolved", "helpful"}
    if event_type == "practice_attempt_graded":
        passed = (event.get("result") or {}).get("passed") is True
        return "formal_success" if passed else "formal_failure", 0.88, passed
    if event_type in {"learning_record_created", "learning_record_updated"}:
        return "learning_record", 0.5, False
    if event_type == "adaptive_block_feedback":
        return "support_feedback", 0.64, feedback == "helpful"
    return "", 0.0, False


def _event_summary(event: dict[str, Any]) -> str:
    evidence = event.get("evidence") or {}
    result = event.get("result") or {}
    return _compact(
        evidence.get("statement")
        or evidence.get("question")
        or evidence.get("quote")
        or result.get("feedback")
        or event.get("event_type")
    )


def _resolve_anchor(
    document: CourseDocument,
    source: dict[str, Any],
    *,
    knowledge_base: dict[str, Any] | None = None,
) -> EvidenceAnchor:
    vector = revision_vector_for_document(document).revisions
    blocks = {item.block_id: item for item in document.blocks}
    section_ids = {item.section_id for item in document.sections}
    metadata = source.get("metadata") or {}
    context_ref = metadata.get("context_ref") or {}
    raw_anchor = (
        source.get("anchor")
        or (source.get("evidence") or {}).get("anchor")
        or metadata.get("content_anchor")
        or context_ref.get("content_anchor")
        or {}
    )
    block_id = str(
        raw_anchor.get("content_block_id")
        or raw_anchor.get("block_id")
        or metadata.get("block_id")
        or ""
    )
    node_id = str(source.get("node_id") or context_ref.get("node_id") or "")
    if not block_id and node_id in blocks:
        block_id = node_id
    section_id = blocks[block_id].section_id if block_id in blocks else (node_id if node_id in section_ids else "")
    if not block_id and section_id:
        block = next((item for item in document.blocks if item.section_id == section_id and item.status != "retired"), None)
        block_id = block.block_id if block else ""
    revision = vector.get(f"block:{block_id}", "") if block_id else ""
    knowledge_refs = [str(item) for item in source.get("concept_ids") or [] if item]
    ability_refs = [str(item) for item in source.get("skill_unit_ids") or [] if item]
    misconception_refs = [str(item) for item in source.get("mistake_point_ids") or [] if item]
    if knowledge_base:
        resolved = _knowledge_binding_for_anchor(
            knowledge_base,
            section_id=section_id,
            block_id=block_id,
        )
        knowledge_refs = _unique([*knowledge_refs, *resolved["knowledge_ids"]])
        ability_refs = _unique([*ability_refs, *resolved["skill_ids"]])
        misconception_refs = _unique([*misconception_refs, *resolved["misconception_ids"]])
    return EvidenceAnchor(
        section_id=section_id,
        block_id=block_id,
        span=deepcopy(raw_anchor.get("span") or {}),
        knowledge_node_ids=knowledge_refs,
        ability_point_ids=ability_refs,
        misconception_point_ids=misconception_refs,
        practice_task_id=str(source.get("task_revision_id") or source.get("question_revision_id") or ""),
        source_revision=revision,
        resolution_status="resolved" if block_id else ("partial" if section_id else "unresolved"),
    )


def _combined_strength(positive: list[EvidenceItem], counter: list[EvidenceItem]) -> float:
    if not positive and counter:
        return -round(sum(item.strength for item in counter), 3)
    by_type: dict[str, float] = {}
    for item in positive:
        by_type[item.source_type] = max(by_type.get(item.source_type, 0.0), item.strength)
    score = sum(math.log1p(value * 1.5) for value in by_type.values())
    score += max((item.strength for item in positive), default=0.0) * 0.45
    score -= sum(item.strength for item in counter) * 0.55
    return round(score, 3)


def _confidence_reasons(
    positive: list[EvidenceItem],
    counter: list[EvidenceItem],
    source_types: set[str],
) -> list[str]:
    reasons = [f"{len(positive)} 条支持证据，来自 {len(source_types)} 类独立来源"]
    if any(item.evidence_kind == "explicit_comprehension_gap" for item in positive):
        reasons.append("包含学生明确表达的理解困难")
    if any(item.evidence_kind == "formal_failure" for item in positive):
        reasons.append("包含正式练习结果")
    if counter:
        reasons.append(f"同时保留 {len(counter)} 条反证并降低判断强度")
    return reasons


def _affected_blocks(
    document: CourseDocument,
    block_id: str,
    *,
    scope: str,
    knowledge_base: dict[str, Any] | None = None,
) -> list[str]:
    ordered = sorted(
        [item for item in document.blocks if item.status != "retired"],
        key=lambda item: (
            next((section.position for section in document.sections if section.section_id == item.section_id), 0),
            item.position,
            item.block_id,
        ),
    )
    index = next((position for position, item in enumerate(ordered) if item.block_id == block_id), -1)
    if index < 0:
        return [block_id]
    count = 4 if scope == "current_and_next" else 1
    if count == 1 or not knowledge_base:
        return [item.block_id for item in ordered[index:index + count]]

    source_binding = _knowledge_binding_for_anchor(
        knowledge_base,
        section_id=ordered[index].section_id,
        block_id=block_id,
    )
    source_knowledge_ids = set(source_binding["knowledge_ids"])
    related_knowledge_ids = set(source_knowledge_ids)
    for relation in knowledge_base.get("relations") or []:
        source_id = str(relation.get("source_knowledge_id") or relation.get("source_id") or "")
        target_id = str(relation.get("target_knowledge_id") or relation.get("target_id") or "")
        relation_type = str(relation.get("relation_type") or "")
        if relation_type in {"prerequisite", "derives", "applies_to", "generalizes"}:
            if source_id in source_knowledge_ids and target_id:
                related_knowledge_ids.add(target_id)
            if relation_type == "prerequisite" and target_id in source_knowledge_ids and source_id:
                related_knowledge_ids.add(source_id)

    related_block_ids = {
        str(binding.get("target_id") or "")
        for binding in knowledge_base.get("bindings") or []
        if binding.get("target_type") == "course_block"
        and set(binding.get("knowledge_ids") or []) & related_knowledge_ids
    }
    selected = [block_id]
    for item in ordered[index + 1:]:
        if item.block_id in related_block_ids and item.block_id not in selected:
            selected.append(item.block_id)
        if len(selected) >= count:
            return selected
    for item in ordered[index + 1:]:
        if item.block_id not in selected:
            selected.append(item.block_id)
        if len(selected) >= count:
            break
    return selected


def _knowledge_binding_for_anchor(
    knowledge_base: dict[str, Any],
    *,
    section_id: str,
    block_id: str,
) -> dict[str, list[str]]:
    relevant = [
        item
        for item in knowledge_base.get("bindings") or []
        if item.get("target_type") == "course_block"
        and str(item.get("target_id") or "") == block_id
    ]
    if relevant:
        knowledge_ids = _unique([
            value for item in relevant for value in item.get("knowledge_ids") or []
        ])
        skill_ids = _unique([
            value for item in relevant for value in item.get("skill_ids") or []
        ])
    elif section_id:
        section_binding = knowledge_binding_for_section(knowledge_base, section_id)
        knowledge_ids = list(section_binding.get("course_knowledge_refs") or [])
        skill_ids = list(section_binding.get("course_skill_refs") or [])
    else:
        knowledge_ids = []
        skill_ids = []
    point_ids = set(knowledge_ids)
    misconception_ids = _unique([
        str(item.get("misconception_id") or "")
        for item in knowledge_base.get("misconceptions") or []
        if str(item.get("primary_knowledge_id") or "") in point_ids
        or bool(set(item.get("knowledge_ids") or []) & point_ids)
    ])
    return {
        "knowledge_ids": knowledge_ids,
        "skill_ids": skill_ids,
        "misconception_ids": misconception_ids,
    }


def _knowledge_labels(knowledge_base: dict[str, Any] | None, ids: set[str]) -> list[str]:
    if not knowledge_base:
        return []
    return _unique([
        str(item.get("name") or item.get("statement") or "")
        for item in knowledge_base.get("knowledge_points") or []
        if str(item.get("knowledge_id") or "") in ids
    ])


def _ability_labels(knowledge_base: dict[str, Any] | None, ids: set[str]) -> list[str]:
    if not knowledge_base:
        return []
    return _unique([
        str(item.get("name") or item.get("observable_behavior") or item.get("description") or "")
        for item in knowledge_base.get("skill_units") or []
        if str(item.get("skill_id") or "") in ids
    ])


def _misconception_labels(knowledge_base: dict[str, Any] | None, ids: set[str]) -> list[str]:
    if not knowledge_base:
        return []
    return _unique([
        str(item.get("name") or item.get("description") or item.get("trigger") or "")
        for item in knowledge_base.get("misconceptions") or []
        if str(item.get("misconception_id") or "") in ids
    ])


def _unique(values: list[Any]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if str(value).strip()))


def _course_document(course_data: dict[str, Any]) -> CourseDocument:
    raw = course_data.get("course_document")
    if not isinstance(raw, dict):
        from course_document import document_from_legacy_course

        return document_from_legacy_course(course_data)
    return CourseDocument.model_validate(raw)


def _block_text(payload: dict[str, Any]) -> str:
    return _compact(payload.get("markdown") or payload.get("text") or payload.get("content"), limit=240)


def _compact(value: Any, *, limit: int = 180) -> str:
    text = re.sub(r"[`*_#>\[\]()]", " ", str(value or ""))
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit].rstrip() + "..."


def _change_set(state: CourseEvolutionState, change_set_id: str) -> PersonalAdaptationPlan:
    item = next((value for value in state.change_sets if value.change_set_id == change_set_id), None)
    if item is None:
        raise KeyError(change_set_id)
    return item


def _hypothesis(state: CourseEvolutionState, hypothesis_id: str) -> AdaptationHypothesis:
    item = next((value for value in state.hypotheses if value.hypothesis_id == hypothesis_id), None)
    if item is None:
        raise KeyError(hypothesis_id)
    return item


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# Canonical names. Legacy names stay available for stored v1 data and callers.
accept_adaptation_plan = accept_change_set
reject_adaptation_plan = reject_change_set
undo_adaptation_plan = undo_change_set


course_evolution_repository = CourseEvolutionRepository()

__all__ = [
    "PersonalAdaptationOperation",
    "PersonalAdaptationPlan",
    "PersonalCourseOverlay",
    "AdaptationHypothesis",
    "accept_adaptation_plan",
    "CourseEvolutionChangeSet",
    "CourseEvolutionRepository",
    "CourseEvolutionState",
    "EvidenceItem",
    "accept_change_set",
    "course_evolution_repository",
    "course_evolution_view",
    "project_applied_adaptive_blocks",
    "personal_course_overlay",
    "reject_change_set",
    "reject_adaptation_plan",
    "synchronize_and_evaluate_course_evolution",
    "undo_change_set",
    "undo_adaptation_plan",
]
