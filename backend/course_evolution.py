"""Evidence-driven plans that grow the current canonical course.

Persisted v1 personal-overlay data remains readable for migration. New plans
write versioned ``CourseDocument`` revisions through canonical domain commands.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import re
import threading
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Literal

from pydantic import BaseModel, Field

from course_commands import CourseCommandService
from course_document import CourseBlock, CourseDocument, stable_hash
from course_knowledge_base import compile_course_knowledge_base, knowledge_binding_for_section
from course_repository import CourseDocumentConflict, CourseDocumentRepository
from course_revisions import revision_vector_for_document
from learning_asset_storage import learning_asset_repository
from learning_events import load_learning_events
from learning_records import learning_record_repository
from practice_attempts import practice_attempt_repository

COURSE_EVOLUTION_SCHEMA = "course_evolution_v2"
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
    evidence_assessment: dict[str, Any] = Field(default_factory=dict)
    recommended_scope: Literal["current", "current_and_next"] = "current"
    affected_block_ids: list[str] = Field(default_factory=list)
    temporary_support: str = ""
    validation_plan: str = ""
    status: HypothesisStatus = "observing"
    created_at: str
    updated_at: str


class CourseEvolutionOperation(BaseModel):
    operation_id: str
    operation_type: Literal[
        "INSERT_COURSE_SUPPORT",
        "INSERT_PERSONAL_SUPPORT",
        "ADD_TRANSITION_SUPPORT",
        "ADD_CHECKPOINT",
        "ADD_TARGETED_PRACTICE",
        "ADD_ANIMATION",
        "REPLACE_COURSE_BLOCK",
        "INSERT_COURSE_BLOCK",
        "FOLD_COURSE_BLOCK",
        "REORDER_COURSE_BLOCK",
        "ADJUST_COURSE_DIFFICULTY",
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


class CourseEvolutionPlan(BaseModel):
    plan_kind: Literal["course_evolution_plan", "personal_adaptation_plan"] = "course_evolution_plan"
    write_target: Literal["course_document", "personal_overlay"] = "course_document"
    change_set_id: str
    user_id: str
    course_id: str
    hypothesis_id: str
    source_kind: Literal[
        "learning_evidence",
        "manual_section_request",
        "manual_request",
    ] = "learning_evidence"
    target_section_id: str = ""
    request_text: str = ""
    growth_direction: Literal["remediation", "challenge", "author_directed"] = "remediation"
    generation_status: Literal["suggested", "generating", "ready", "failed", "stale"] = "ready"
    requested_roles: list[str] = Field(default_factory=list)
    replaces_change_set_id: str = ""
    base_revision_vector: dict[str, str] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    operations: list[CourseEvolutionOperation] = Field(default_factory=list)
    scope_selection: Literal[
        "current_block",
        "current_section",
        "whole_course",
    ] = "current_section"
    allowed_scopes: list[Literal["current", "current_and_next"]] = Field(default_factory=list)
    selected_scope: Literal["current", "current_and_next"] | None = None
    selected_operation_ids: list[str] = Field(default_factory=list)
    excluded_operation_ids: list[str] = Field(default_factory=list)
    impact_summary: dict[str, Any] = Field(default_factory=dict)
    expected_effect: str
    status: ChangeSetStatus = "pending"
    created_at: str
    updated_at: str
    accepted_at: str | None = None
    resolved_at: str | None = None
    applied_block_ids: list[str] = Field(default_factory=list)
    application_receipt: dict[str, Any] = Field(default_factory=dict)
    undo_receipt: dict[str, Any] = Field(default_factory=dict)
    effect_evaluation: dict[str, Any] = Field(default_factory=dict)


class CourseEvolutionState(BaseModel):
    schema_version: Literal["course_evolution_v1", "course_evolution_v2"] = COURSE_EVOLUTION_SCHEMA
    user_id: str
    course_id: str
    evidence_items: list[EvidenceItem] = Field(default_factory=list)
    hypotheses: list[AdaptationHypothesis] = Field(default_factory=list)
    change_sets: list[CourseEvolutionPlan] = Field(default_factory=list)
    revision: str = ""
    updated_at: str


class PersonalCourseOverlay(BaseModel):
    schema_version: Literal[
        "personal_course_overlay_v1",
        "personal_course_overlay_v2",
    ] = "personal_course_overlay_v2"
    overlay_id: str
    user_id: str
    course_id: str
    base_revision_vector: dict[str, str] = Field(default_factory=dict)
    current_revision_vector: dict[str, str] = Field(default_factory=dict)
    active_plan_ids: list[str] = Field(default_factory=list)
    operations: list[CourseEvolutionOperation] = Field(default_factory=list)
    resolution_status: Literal[
        "empty",
        "active",
        "partially_active",
        "conflicted",
    ] = "empty"
    relocations: list[dict[str, Any]] = Field(default_factory=list)
    conflicts: list[dict[str, Any]] = Field(default_factory=list)
    revision: str
    updated_at: str
    deprecated: bool = True


# Compatibility aliases for persisted v1 imports.
PersonalAdaptationOperation = CourseEvolutionOperation
PersonalAdaptationPlan = CourseEvolutionPlan
CourseEvolutionChangeSet = CourseEvolutionPlan


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
        with self._lock(key):
            return self._load_unlocked(user_id, course_id, key)

    def save(self, state: CourseEvolutionState) -> CourseEvolutionState:
        key = self._key(state.user_id, state.course_id)
        with self._lock(key):
            return self._save_unlocked(state, key)

    def update(
        self,
        user_id: str,
        course_id: str,
        updater: Callable[[CourseEvolutionState], CourseEvolutionState | None],
    ) -> CourseEvolutionState:
        """Read, mutate and persist one learner-course state under one lock.

        Generation routes use this to claim a stable request before any model
        call. Two identical requests therefore share one persisted plan instead
        of both appending parallel candidates.
        """
        key = self._key(user_id, course_id)
        with self._lock(key):
            current = self._load_unlocked(user_id, course_id, key)
            updated = updater(current)
            value = current if updated is None else updated
            if not isinstance(value, CourseEvolutionState):
                value = CourseEvolutionState.model_validate(value)
            if value.user_id != user_id or value.course_id != course_id:
                raise ValueError("Course evolution updater changed learner or course ownership")
            return self._save_unlocked(value, key)

    def _load_unlocked(
        self,
        user_id: str,
        course_id: str,
        key: str,
    ) -> CourseEvolutionState:
        path = self.root / f"{key}.json"
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

    def _save_unlocked(
        self,
        state: CourseEvolutionState,
        key: str,
    ) -> CourseEvolutionState:
        path = self.root / f"{key}.json"
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
        state.schema_version = COURSE_EVOLUTION_SCHEMA
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
    asset_bundle = learning_asset_repository.load_bundle(course_id) or {}
    learning_assets = asset_bundle.get("assets") if isinstance(asset_bundle, dict) else {}
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
        learning_assets=learning_assets if isinstance(learning_assets, dict) else {},
    )
    from section_evolution import ensure_challenge_suggestions

    ensure_challenge_suggestions(state, document)
    _evaluate_applied_effects(state, user_id=user_id)
    return repository.save(state)


def accept_change_set(
    course_data: dict[str, Any],
    *,
    user_id: str,
    change_set_id: str,
    selected_scope: Literal["current", "current_and_next"],
    selected_operation_ids: list[str] | None = None,
    repository: CourseEvolutionRepository | None = None,
    document_repository: CourseDocumentRepository | None = None,
) -> CourseEvolutionState:
    repository = repository or course_evolution_repository
    course_id = str(course_data.get("course_id") or "")
    if not course_id:
        raise ValueError("Course identifier is required")
    document_repository = document_repository or _default_document_repository()
    document, canonical = document_repository.load_document(course_id)
    if not canonical:
        raise ValueError("Course must be migrated before course growth can be applied")
    state = repository.load(user_id, course_id)
    change_set = _change_set(state, change_set_id)
    if change_set.status == "applied":
        same_selection = (
            selected_operation_ids is None
            or set(selected_operation_ids) == set(change_set.selected_operation_ids)
        )
        if change_set.selected_scope == selected_scope and same_selection:
            return state
        raise ValueError("Course change set has already been applied with another review selection")
    if change_set.status != "pending":
        raise ValueError(f"Course change set cannot be accepted from {change_set.status}")
    if change_set.generation_status != "ready":
        raise ValueError("Course change set has not finished generating")
    if selected_scope not in change_set.allowed_scopes:
        raise ValueError("Selected scope is not allowed for this change set")

    eligible_operations = [
        operation
        for operation in change_set.operations
        if operation.operation_type != "ADJUST_COURSE_DIFFICULTY"
        and (selected_scope == "current_and_next" or operation.scope == "current")
    ]
    eligible_operation_ids = [operation.operation_id for operation in eligible_operations]
    if selected_operation_ids is None:
        accepted_operation_ids = eligible_operation_ids
    else:
        requested_operation_ids = list(dict.fromkeys(selected_operation_ids))
        unknown_operation_ids = sorted(
            set(requested_operation_ids) - set(eligible_operation_ids)
        )
        if unknown_operation_ids:
            raise ValueError(
                "Selected course evolution operations are unavailable: "
                + ", ".join(unknown_operation_ids)
            )
        accepted_operation_ids = [
            operation_id
            for operation_id in eligible_operation_ids
            if operation_id in requested_operation_ids
        ]
    if not accepted_operation_ids:
        raise ValueError("Select at least one course evolution operation")
    accepted_operation_id_set = set(accepted_operation_ids)
    excluded_operation_ids = [
        operation_id
        for operation_id in eligible_operation_ids
        if operation_id not in accepted_operation_id_set
    ]

    current_vector = revision_vector_for_document(document).revisions
    for key, revision in change_set.base_revision_vector.items():
        if key in current_vector and current_vector[key] != revision:
            change_set.status = "stale"
            change_set.updated_at = _now()
            repository.save(state)
            raise ValueError("Course changed after this candidate was generated")

    replaced: CourseEvolutionPlan | None = None
    replaced_retire_block_ids: list[str] = []
    if change_set.replaces_change_set_id:
        replaced = _change_set(state, change_set.replaces_change_set_id)
        if replaced.status != "applied":
            raise ValueError("Replaced course evolution plan is no longer active")
        replaced_retire_block_ids = list(replaced.applied_block_ids)

    replacements, insertions, folded_retire_block_ids, reorderings = _course_block_mutations(
        change_set,
        document,
        selected_scope=selected_scope,
        selected_operation_ids=accepted_operation_id_set,
    )
    command_id = f"course-evolution-apply:{user_id}:{change_set.change_set_id}"
    try:
        receipt = asyncio.run(CourseCommandService(document_repository).apply_block_operation_group(
            course_id,
            command_id=command_id,
            expected_document_revision=document.document_revision,
            insertions=insertions,
            replacements=replacements,
            retire_block_ids=[
                *replaced_retire_block_ids,
                *folded_retire_block_ids,
            ],
            reorderings=reorderings,
            reason=f"学习证据驱动课程生长：{change_set.hypothesis_id}",
            actor=f"learner:{user_id}",
        ))
    except CourseDocumentConflict as exc:
        change_set.status = "stale"
        change_set.updated_at = _now()
        repository.save(state)
        raise ValueError(str(exc)) from exc

    change_set.selected_scope = selected_scope
    change_set.selected_operation_ids = accepted_operation_ids
    change_set.excluded_operation_ids = excluded_operation_ids
    change_set.status = "applied"
    change_set.plan_kind = "course_evolution_plan"
    change_set.write_target = "course_document"
    change_set.accepted_at = _now()
    change_set.resolved_at = change_set.accepted_at
    change_set.updated_at = change_set.accepted_at
    inserted_block_ids = [item["block"].block_id for item in insertions]
    replaced_block_ids = [str(item["block_id"]) for item in replacements]
    folded_block_ids = [
        operation.target_block_id
        for operation in change_set.operations
        if operation.operation_type == "FOLD_COURSE_BLOCK"
        and operation.operation_id in accepted_operation_id_set
    ]
    reordered_block_ids = [
        operation.target_block_id
        for operation in change_set.operations
        if operation.operation_type == "REORDER_COURSE_BLOCK"
        and operation.operation_id in accepted_operation_id_set
    ]
    change_set.applied_block_ids = list(dict.fromkeys([
        *replaced_block_ids,
        *inserted_block_ids,
        *folded_block_ids,
        *reordered_block_ids,
    ]))
    change_set.application_receipt = {
        **deepcopy(receipt),
        "inserted_block_ids": inserted_block_ids,
        "replaced_block_ids": replaced_block_ids,
        "folded_block_ids": folded_block_ids,
        "reordered_block_ids": reordered_block_ids,
        "accepted_operation_ids": accepted_operation_ids,
        "excluded_operation_ids": excluded_operation_ids,
        "replacement_journal": [
            {
                "block_id": operation.target_block_id,
                "before_block": deepcopy(operation.payload.get("before_block") or {}),
            }
            for operation in change_set.operations
            if operation.operation_type == "REPLACE_COURSE_BLOCK"
            and operation.operation_id in accepted_operation_id_set
        ],
        "path_operation_journal": [
            {
                "operation_id": operation.operation_id,
                "operation_type": operation.operation_type,
                "block_id": operation.target_block_id,
                "before_status": str(
                    next(
                        block.status
                        for block in document.blocks
                        if block.block_id == operation.target_block_id
                    )
                ),
                "before_after_block_id": _previous_active_block_id(
                    document,
                    operation.target_block_id,
                ),
            }
            for operation in change_set.operations
            if operation.operation_type in {
                "FOLD_COURSE_BLOCK",
                "REORDER_COURSE_BLOCK",
            }
            and operation.operation_id in accepted_operation_id_set
        ],
    }
    hypothesis = _hypothesis(state, change_set.hypothesis_id)
    baseline_evidence = [
        item for item in state.evidence_items
        if item.evidence_id in change_set.evidence_ids
    ]
    change_set.impact_summary["effect_baseline"] = {
        "captured_at": change_set.accepted_at,
        "problem_type": hypothesis.problem_type,
        "diagnosis": hypothesis.claim,
        "selected_scope": selected_scope,
        "target_block_ids": [
            operation.target_block_id
            for operation in change_set.operations
            if operation.operation_id in accepted_operation_id_set
        ],
        "evidence_ids": list(change_set.evidence_ids),
        "practice_attempt_ids": [
            item.source_id
            for item in baseline_evidence
            if item.source_type == "practice_attempt"
        ],
        "practice_task_ids": list(
            change_set.impact_summary.get("source_practice_task_ids") or []
        ),
        "knowledge_node_ids": list(
            change_set.impact_summary.get("knowledge_node_ids") or []
        ),
        "ability_point_ids": list(
            change_set.impact_summary.get("ability_point_ids") or []
        ),
        "misconception_point_ids": list(
            change_set.impact_summary.get("misconception_point_ids") or []
        ),
    }
    if replaced is not None:
        replaced.status = "undone"
        replaced.resolved_at = change_set.accepted_at
        replaced.updated_at = change_set.accepted_at
        replaced.undo_receipt = {
            "operation": "replaced_by_course_evolution_plan",
            "replacement_change_set_id": change_set.change_set_id,
            "retired_block_ids": replaced_retire_block_ids,
            "document_revision": receipt.get("document_revision"),
        }
        replaced.effect_evaluation = {
            **replaced.effect_evaluation,
            "resolution": "replaced_by_adjustment",
            "replacement_change_set_id": change_set.change_set_id,
        }
    hypothesis.status = "evaluating"
    hypothesis.updated_at = change_set.accepted_at
    return repository.save(state)


def create_adjustment_plan(
    *,
    user_id: str,
    course_id: str,
    change_set_id: str,
    repository: CourseEvolutionRepository | None = None,
    document_repository: CourseDocumentRepository | None = None,
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

    operations: list[CourseEvolutionOperation] = []
    for operation in source.operations:
        payload = deepcopy(operation.payload)
        if operation.operation_type in {"INSERT_COURSE_SUPPORT", "INSERT_PERSONAL_SUPPORT"}:
            payload["body"] = (
                "改用具体状态对照：先指出变化前的对象，再逐步说明每次操作改变了什么，"
                "最后让学习者用自己的话连接操作与结论。"
            )
            payload["contrast"] = "替换上一版抽象解释；范围外课程正文保持不变。"
        elif operation.operation_type == "ADD_ANIMATION":
            payload["animation_spec"] = _adjusted_animation_spec(
                payload.get("animation_spec") or {},
                source.change_set_id,
            )
            payload["steps"] = [
                {"index": frame.get("index"), "label": frame.get("label")}
                for frame in payload["animation_spec"].get("fallback_frames") or []
            ]
        elif operation.operation_type in {"ADD_CHECKPOINT", "ADD_TARGETED_PRACTICE"}:
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
    document_repository = document_repository or _default_document_repository()
    document, canonical = document_repository.load_document(course_id)
    if not canonical:
        raise ValueError("Course must be migrated before an adjustment can be generated")
    replacement = CourseEvolutionPlan(
        change_set_id=stable_hash({
            "source_change_set_id": source.change_set_id,
            "effect_evaluation": source.effect_evaluation,
            "adjustment": "state_contrast_v1",
        }, prefix="ces_"),
        user_id=user_id,
        course_id=course_id,
        hypothesis_id=source.hypothesis_id,
        replaces_change_set_id=source.change_set_id,
        base_revision_vector=_bound_revision_vector(
            document,
            [
                operation.target_block_id
                for operation in operations
            ],
        ),
        evidence_ids=list(source.evidence_ids),
        operations=operations,
        scope_selection=source.scope_selection,
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
    document_repository: CourseDocumentRepository | None = None,
) -> CourseEvolutionState:
    repository = repository or course_evolution_repository
    state = repository.load(user_id, course_id)
    change_set = _change_set(state, change_set_id)
    if change_set.status != "applied":
        raise ValueError(f"Course change set cannot be undone from {change_set.status}")
    if change_set.write_target == "course_document":
        if not change_set.applied_block_ids:
            raise ValueError("Applied course evolution plan has no recorded course blocks")
        document_repository = document_repository or _default_document_repository()
        document, canonical = document_repository.load_document(course_id)
        if not canonical:
            raise ValueError("Course must be migrated before course growth can be undone")
        command_id = f"course-evolution-undo:{user_id}:{change_set.change_set_id}"
        blocks_by_id = {block.block_id: block for block in document.blocks}
        replacement_journal = list(
            change_set.application_receipt.get("replacement_journal") or []
        )
        replacements: list[dict[str, Any]] = []
        for item in replacement_journal:
            block_id = str(item.get("block_id") or "")
            current = blocks_by_id.get(block_id)
            before_block = item.get("before_block") or {}
            before_payload = before_block.get("payload") if isinstance(before_block, dict) else None
            if current is None or not isinstance(before_payload, dict):
                raise ValueError("Course block needed for undo is unavailable")
            replacements.append({
                "block_id": block_id,
                "expected_block_revision": current.internal_revision,
                "payload": deepcopy(before_payload),
                "asset_refs": list(before_block.get("asset_refs") or []),
                "objective_refs": list(before_block.get("objective_refs") or []),
                "concept_refs": list(before_block.get("concept_refs") or []),
                "evidence_refs": list(before_block.get("evidence_refs") or []),
                "visibility_rule": deepcopy(before_block.get("visibility_rule") or {}),
            })
        inserted_block_ids = list(
            change_set.application_receipt["inserted_block_ids"]
            if "inserted_block_ids" in change_set.application_receipt
            else [
                block_id
                for block_id in change_set.applied_block_ids
                if block_id not in {
                    str(item.get("block_id") or "")
                    for item in replacement_journal
                }
            ]
        )
        path_operation_journal = list(
            change_set.application_receipt.get("path_operation_journal") or []
        )
        restore_block_ids = [
            str(item.get("block_id") or "")
            for item in path_operation_journal
            if item.get("operation_type") == "FOLD_COURSE_BLOCK"
            and str(item.get("before_status") or "final") != "retired"
        ]
        reverse_reorderings = [
            {
                "block_id": str(item.get("block_id") or ""),
                "after_block_id": str(item.get("before_after_block_id") or ""),
            }
            for item in reversed(path_operation_journal)
            if item.get("operation_type") == "REORDER_COURSE_BLOCK"
        ]
        try:
            receipt = asyncio.run(CourseCommandService(document_repository).apply_block_operation_group(
                course_id,
                command_id=command_id,
                expected_document_revision=document.document_revision,
                insertions=[],
                replacements=replacements,
                retire_block_ids=inserted_block_ids,
                restore_block_ids=restore_block_ids,
                reorderings=reverse_reorderings,
                reason=f"撤销学习证据驱动课程生长：{change_set.hypothesis_id}",
                actor=f"learner:{user_id}",
            ))
        except CourseDocumentConflict as exc:
            raise ValueError(str(exc)) from exc
        change_set.undo_receipt = deepcopy(receipt)
    change_set.status = "undone"
    change_set.resolved_at = _now()
    change_set.updated_at = change_set.resolved_at
    hypothesis = _hypothesis(state, change_set.hypothesis_id)
    hypothesis.status = "observing"
    hypothesis.updated_at = change_set.resolved_at
    return repository.save(state)


def personal_course_overlay(
    state: CourseEvolutionState,
    *,
    current_revision_vector: dict[str, str] | None = None,
) -> PersonalCourseOverlay:
    active_plans = [
        item for item in state.change_sets
        if item.status == "applied" and item.write_target == "personal_overlay"
    ]
    operations: list[CourseEvolutionOperation] = []
    active_plan_ids: list[str] = []
    relocations: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    for plan in active_plans:
        plan_has_active_operation = False
        for operation in plan.operations:
            if plan.selected_scope == "current" and operation.scope == "next":
                continue
            resolution = _resolve_personal_overlay_operation(
                plan,
                operation,
                current_revision_vector=current_revision_vector,
            )
            if resolution["status"] == "conflict":
                conflicts.append(resolution)
                continue
            operations.append(operation.model_copy(deep=True))
            plan_has_active_operation = True
            if resolution["status"] == "relocated":
                relocations.append(resolution)
        if plan_has_active_operation:
            active_plan_ids.append(plan.change_set_id)
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
        "current_revision_vector": current_revision_vector or {},
        "active_plan_ids": active_plan_ids,
        "operations": [item.model_dump(mode="json") for item in operations],
        "relocations": relocations,
        "conflicts": conflicts,
    }
    resolution_status: Literal[
        "empty",
        "active",
        "partially_active",
        "conflicted",
    ]
    if not active_plans:
        resolution_status = "empty"
    elif conflicts and operations:
        resolution_status = "partially_active"
    elif conflicts:
        resolution_status = "conflicted"
    else:
        resolution_status = "active"
    return PersonalCourseOverlay(
        overlay_id=stable_hash(
            {"user_id": state.user_id, "course_id": state.course_id},
            prefix="pco_",
        ),
        user_id=state.user_id,
        course_id=state.course_id,
        base_revision_vector=base_revision_vector,
        current_revision_vector=current_revision_vector or {},
        active_plan_ids=active_plan_ids,
        operations=operations,
        resolution_status=resolution_status,
        relocations=relocations,
        conflicts=conflicts,
        revision=stable_hash(payload, prefix="pcr_"),
        updated_at=updated_at,
    )


def _resolve_personal_overlay_operation(
    plan: CourseEvolutionPlan,
    operation: CourseEvolutionOperation,
    *,
    current_revision_vector: dict[str, str] | None,
) -> dict[str, Any]:
    """Rebase a deprecated overlay operation only when its semantic anchor is intact."""
    result = {
        "plan_id": plan.change_set_id,
        "operation_id": operation.operation_id,
        "target_block_id": operation.target_block_id,
        "target_section_id": operation.target_section_id,
    }
    if current_revision_vector is None:
        return {**result, "status": "active", "reason": "revision_context_unavailable"}

    block_key = f"block:{operation.target_block_id}" if operation.target_block_id else ""
    section_key = f"section:{operation.target_section_id}" if operation.target_section_id else ""
    expected_block_revision = plan.base_revision_vector.get(block_key) if block_key else None
    expected_section_revision = plan.base_revision_vector.get(section_key) if section_key else None
    current_block_revision = current_revision_vector.get(block_key) if block_key else None
    current_section_revision = current_revision_vector.get(section_key) if section_key else None
    revisions = {
        "expected": {
            key: value
            for key, value in (
                (block_key, expected_block_revision),
                (section_key, expected_section_revision),
            )
            if key and value is not None
        },
        "current": {
            key: value
            for key, value in (
                (block_key, current_block_revision),
                (section_key, current_section_revision),
            )
            if key and value is not None
        },
    }

    if expected_block_revision is not None:
        if current_block_revision is None:
            return {
                **result,
                **revisions,
                "status": "conflict",
                "reason": "target_block_removed",
                "requires_user_resolution": True,
            }
        if current_block_revision != expected_block_revision:
            return {
                **result,
                **revisions,
                "status": "conflict",
                "reason": "target_block_revision_changed",
                "requires_user_resolution": True,
            }
        if (
            expected_section_revision is not None
            and current_section_revision != expected_section_revision
        ):
            return {
                **result,
                **revisions,
                "status": "relocated",
                "reason": "section_rebased_target_block_unchanged",
                "requires_user_resolution": False,
            }
        return {
            **result,
            **revisions,
            "status": "active",
            "reason": "target_revision_unchanged",
        }

    if expected_section_revision is not None:
        if current_section_revision is None:
            reason = "target_section_removed"
        elif current_section_revision != expected_section_revision:
            reason = "target_section_revision_changed"
        else:
            return {
                **result,
                **revisions,
                "status": "active",
                "reason": "target_revision_unchanged",
            }
        return {
            **result,
            **revisions,
            "status": "conflict",
            "reason": reason,
            "requires_user_resolution": True,
        }

    return {
        **result,
        **revisions,
        "status": "conflict",
        "reason": "missing_base_revision_binding",
        "requires_user_resolution": True,
    }


def course_evolution_view(
    state: CourseEvolutionState,
    *,
    current_revision_vector: dict[str, str] | None = None,
) -> dict[str, Any]:
    payload = state.model_dump(mode="json")
    payload["view_schema_version"] = "course_evolution_v2"
    payload["course_evolution_plans"] = deepcopy(payload["change_sets"])
    payload["adaptation_plans"] = deepcopy(payload["change_sets"])
    for plan in payload["adaptation_plans"]:
        plan["plan_id"] = plan["change_set_id"]
    for plan in payload["course_evolution_plans"]:
        plan["plan_id"] = plan["change_set_id"]
    legacy_overlay = personal_course_overlay(
        state,
        current_revision_vector=current_revision_vector,
    )
    # PersonalCourseOverlay is a migration reader only. Do not expose its
    # operations as a second durable course/content projection.
    payload["legacy_overlay_migration"] = {
        "schema_version": "legacy_overlay_migration_v1",
        "resolution_status": legacy_overlay.resolution_status,
        "requires_migration": bool(legacy_overlay.active_plan_ids or legacy_overlay.conflicts),
        "conflicts": deepcopy(legacy_overlay.conflicts),
    }
    payload["permissions"] = {
        "write_target": "course_document",
        "can_modify_current_course": True,
        "can_modify_other_courses": False,
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
    learning_assets: dict[str, Any] | None = None,
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
        formal_failures = [
            item for item in positive
            if item.evidence_kind == "formal_failure"
        ]
        explicit_statements = [
            item for item in positive
            if item.evidence_kind == "explicit_comprehension_gap"
            and item.strength >= 0.82
        ]
        explicit_contracts = [
            (item, _strong_self_report_contract(item.summary))
            for item in explicit_statements
        ]
        strong_explicit_statements = [
            item
            for item, contract in explicit_contracts
            if contract["is_strong"]
        ]
        scoped_explicit_statements = [
            item
            for item, contract in explicit_contracts
            if contract["is_strong"]
            and contract["scope"] == "current_and_next"
        ]
        latest_explicit_contract = next((
            contract
            for _item, contract in reversed(explicit_contracts)
            if contract["is_strong"]
        ), {})
        repeated_formal_failure = len({
            item.source_id for item in formal_failures if item.source_id
        }) >= 2
        corroborated_formal_failure = bool(formal_failures) and len(source_types) >= 2
        single_explicit_local_support = (
            len(positive) == 1
            and len(explicit_statements) == 1
        )
        strong_explicit_support = bool(strong_explicit_statements)
        explicit_scoped_support = bool(scoped_explicit_statements)
        actionable = (
            strong_explicit_support
            or single_explicit_local_support
            or corroborated_formal_failure
            or repeated_formal_failure
        )
        scope = "current_and_next" if (
            actionable
            and (
                explicit_scoped_support
                or (
                    bool(formal_failures)
                    and (
                        len(source_types) >= 3
                        or (repeated_formal_failure and len(source_types) >= 2)
                    )
                )
            )
        ) else "current"
        evidence_assessment = {
            "evidence_count": len(positive),
            "independent_source_count": len(source_types),
            "source_types": sorted(source_types),
            "formal_failure_count": len(formal_failures),
            "counterevidence_count": len(counter),
            "has_explicit_statement": bool(explicit_statements),
            "has_strong_self_report": strong_explicit_support,
            "has_explicit_scope": explicit_scoped_support,
            "explicit_scope": "current_and_next" if explicit_scoped_support else (
                str(latest_explicit_contract.get("scope") or "")
            ),
            "explicit_request_contract": deepcopy(latest_explicit_contract),
            "requested_supports": list(
                latest_explicit_contract.get("requested_supports") or []
            ),
            "has_formal_evidence": bool(formal_failures),
            "actionable": actionable,
            "maturity": (
                "explicit_scoped_request"
                if explicit_scoped_support
                else "confirmed_gap"
                if scope == "current_and_next"
                else "corroborated_gap"
                if corroborated_formal_failure or repeated_formal_failure
                else "explicit_local_support"
                if strong_explicit_support or single_explicit_local_support
                else "observing"
            ),
            "gate_reason": (
                "学生明确说明已会内容、持续困难、所需讲法和后续范围，可立即生成当前位置及相关后续候选"
                if explicit_scoped_support
                else "三类独立证据与正式失败共同指向同一缺口"
                if scope == "current_and_next"
                else "正式失败已获得另一类独立证据支持"
                if corroborated_formal_failure
                else "同一能力出现重复正式失败"
                if repeated_formal_failure
                else "学生给出明确、可执行的当前位置学习请求，仅生成低风险局部候选"
                if strong_explicit_support
                else "学生明确表达理解困难，仅建议当前位置低风险支持"
                if single_explicit_local_support
                else "尚缺正式证据或重复独立信号，继续观察"
            ),
        }
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
                claim=_diagnosis_claim(positive, knowledge_base),
                target_block_id=block_id,
                created_at=now,
                updated_at=now,
            )
            state.hypotheses.append(hypothesis)
        hypothesis.claim = _diagnosis_claim(positive, knowledge_base)
        hypothesis.support_evidence_ids = [item.evidence_id for item in positive]
        hypothesis.counterevidence_ids = [item.evidence_id for item in counter]
        # The combined score is allowed to exceed 1 internally because it is also
        # used by the actionability threshold. The public confidence remains a
        # probability-like value and must never exceed 1.
        hypothesis.confidence = round(min(1.0, max(0.0, score)), 3)
        hypothesis.confidence_reasons = _confidence_reasons(positive, counter, source_types)
        hypothesis.evidence_assessment = evidence_assessment
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
        if hypothesis.status in {"accepted", "evaluating", "effective"}:
            continue
        evidence_signature = stable_hash(sorted(hypothesis.support_evidence_ids), prefix="esg_")
        latest_resolved = next((
            item for item in reversed(state.change_sets)
            if item.hypothesis_id == hypothesis_id
            and item.status in {"rejected", "undone"}
        ), None)
        if latest_resolved is not None:
            resolved_evidence_ids = set(latest_resolved.evidence_ids)
            has_new_strong_request = any(
                item.evidence_id not in resolved_evidence_ids
                for item in strong_explicit_statements
            )
            if not has_new_strong_request:
                hypothesis.status = (
                    "rejected"
                    if latest_resolved.status == "rejected"
                    else "observing"
                )
                hypothesis.evidence_assessment["blocked_by_previous_resolution"] = True
                hypothesis.evidence_assessment["gate_reason"] = (
                    "同一批证据形成的方案已被学生拒绝或撤销；"
                    "只有新的强学习请求才能再次生成候选。"
                )
                continue
        if hypothesis.status == "rejected" and not strong_explicit_support:
            continue
        hypothesis.status = "actionable"
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
        if cooldown and cooldown > now and not strong_explicit_support:
            continue
        change_set = _build_change_set(
            state,
            document,
            hypothesis,
            evidence_signature=evidence_signature,
            knowledge_base=knowledge_base,
            learning_assets=learning_assets,
        )
        for previous in state.change_sets:
            if (
                previous.hypothesis_id == hypothesis_id
                and previous.status == "pending"
                and previous.change_set_id != change_set.change_set_id
            ):
                previous.status = "stale"
                previous.resolved_at = now
                previous.updated_at = now
                previous.effect_evaluation = {
                    "status": "superseded",
                    "reason": "新的学习证据改变了判断强度或影响范围，已由最新方案替代。",
                    "replacement_change_set_id": change_set.change_set_id,
                }
        state.change_sets.append(change_set)
        hypothesis.status = "candidate_created"


def _build_change_set(
    state: CourseEvolutionState,
    document: CourseDocument,
    hypothesis: AdaptationHypothesis,
    *,
    evidence_signature: str,
    knowledge_base: dict[str, Any] | None = None,
    learning_assets: dict[str, Any] | None = None,
) -> CourseEvolutionPlan:
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
    targeted_practice = _targeted_practice_for(
        section_id=target.section_id,
        binding=target_binding,
        evidence=[
            item
            for item in state.evidence_items
            if item.evidence_id in hypothesis.support_evidence_ids
        ],
        learning_assets=learning_assets or {},
    )
    animation_spec = _animation_spec_for_block(
        target,
        title=target_title,
        evidence_signature=evidence_signature,
        knowledge_refs=target_binding["knowledge_ids"],
        composition_order=(
            "复合变换" in hypothesis.claim
            or "先后顺序" in hypothesis.claim
        ),
    )
    operations: list[CourseEvolutionOperation] = []

    def append_operation(operation_type: str, block_id: str, scope: str, reason: str, payload: dict[str, Any]) -> None:
        block = blocks[block_id]
        operation_payload = {
            "change_set_seed": evidence_signature,
            "operation_type": operation_type,
            "block_id": block_id,
            "scope": scope,
            "payload": payload,
        }
        operations.append(CourseEvolutionOperation(
            operation_id=stable_hash(operation_payload, prefix="ceo_"),
            operation_type=operation_type,
            target_block_id=block_id,
            target_section_id=block.section_id,
            scope=scope,
            reason=reason,
            payload=payload,
        ))

    append_operation(
        "INSERT_COURSE_SUPPORT",
        target.block_id,
        "current",
        "当前证据指向概念原因与计算步骤之间的断裂。",
        {
            "body": f"先不要只记步骤。围绕“{target_title}”，把它看成一次关系或过程：先说明为什么需要这一步，再说明每一步改变了什么，最后回到原结论。",
            "contrast": f"原内容保留不变；这段课程补充只负责连接“怎么做”和“为什么”。原段核心：{target_text[:120]}",
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
            "animation_spec": animation_spec,
            "steps": [
                {
                    "index": frame.get("index"),
                    "label": frame.get("label"),
                }
                for frame in animation_spec.get("fallback_frames") or []
            ],
            "contrast": "若动态演示不可用，使用同样三步的静态分解图。",
        },
    )
    append_operation(
        "ADD_TARGETED_PRACTICE",
        target.block_id,
        "current",
        "当前课程中存在与能力点和易错点匹配的正式题目；确认后插入本节，用于验证新增解释是否有效。",
        {
            "body": "完成一项与当前能力缺口直接对应的独立检查；这不是追加题量，而是验证刚才的理解是否真正建立。",
            "prompt": targeted_practice["prompt"],
            "objective": "验证概念原因，而不是重复计算。",
            "practice_task_id": targeted_practice["revision_id"],
            "practice_asset_id": targeted_practice["asset_id"],
            "practice_intent": "standard",
            "requires_confirmation": True,
            "knowledge_refs": target_binding["knowledge_ids"],
            "ability_refs": target_binding["skill_ids"],
            "misconception_refs": target_binding["misconception_ids"],
            "expected_effect": "能够解释当前操作的语义作用，并迁移到后续同能力任务。",
        },
    )
    for index, block_id in enumerate(hypothesis.affected_block_ids[1:]):
        block = blocks[block_id]
        title = str(block.payload.get("title") or sections.get(block.section_id, {}).title if sections.get(block.section_id) else "后续内容")
        if index == 0:
            append_operation(
                "ADD_TRANSITION_SUPPORT",
                block_id,
                "next",
                "当前概念是下一处学习内容的前置，需要补一条承接而不是重写后文。",
                {
                    "body": f"进入“{title}”前，先回看上一处概念在这里承担什么作用，再继续当前推导。",
                    "objective": "把当前理解迁移到下一处学习内容。",
                },
            )
        else:
            append_operation(
                "ADD_CHECKPOINT",
                block_id,
                "next",
                "后续推导继续依赖当前概念，需要在关键位置检查先后关系是否仍被正确理解。",
                {
                    "body": f"继续“{title}”前，先确认每个操作的作用对象与执行顺序。",
                    "prompt": "请指出这里应先执行哪一步，并用概念含义解释理由。",
                    "objective": "在后续推导中独立判断操作顺序，而不是只复述计算步骤。",
                },
            )
    now = _now()
    affected_section_ids = {
        blocks[block_id].section_id
        for block_id in hypothesis.affected_block_ids
        if block_id in blocks
    }
    bound_keys = _bound_revision_vector(document, hypothesis.affected_block_ids)
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
    source_practice_task_ids = sorted({
        item.anchor.practice_task_id
        for item in linked_evidence
        if item.anchor.practice_task_id
    })
    validation_task_ids = list(targeted_practice.get("validation_task_ids") or [])
    knowledge_labels = _knowledge_labels(knowledge_base, knowledge_ids)
    ability_labels = _ability_labels(knowledge_base, ability_ids)
    misconception_labels = _misconception_labels(knowledge_base, misconception_ids)
    explicit_request = next((
        item
        for item in reversed(linked_evidence)
        if _strong_self_report_contract(item.summary)["is_strong"]
    ), None)
    requested_supports = list(
        hypothesis.evidence_assessment.get("requested_supports") or []
    )
    return CourseEvolutionPlan(
        change_set_id=stable_hash({
            "user_id": state.user_id,
            "course_id": state.course_id,
            "hypothesis_id": hypothesis.hypothesis_id,
            "evidence_signature": evidence_signature,
        }, prefix="ces_"),
        user_id=state.user_id,
        course_id=state.course_id,
        hypothesis_id=hypothesis.hypothesis_id,
        target_section_id=target.section_id,
        request_text=explicit_request.summary if explicit_request else "",
        requested_roles=requested_supports,
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
            "knowledge_labels": knowledge_labels,
            "ability_labels": ability_labels,
            "misconception_labels": misconception_labels,
            "diagnosis": hypothesis.claim,
            "validation_plan": hypothesis.validation_plan,
            "evidence_assessment": deepcopy(hypothesis.evidence_assessment),
            "trigger_contract": deepcopy(
                hypothesis.evidence_assessment.get("explicit_request_contract") or {}
            ),
            "scope_reason": str(
                hypothesis.evidence_assessment.get("gate_reason") or ""
            ),
            "evidence_source_types": sorted({item.source_type for item in linked_evidence}),
            "affected_section_ids": sorted(affected_section_ids),
            "source_practice_task_ids": source_practice_task_ids,
            "validation_task_ids": validation_task_ids,
            "protected": ["范围外课程内容", "其他课程", "历史作答", "笔记原文", "课程知识库"],
            "representation_impacts": ["当前位置解释", "分步演示", "下一节承接", "后续顺序检查", "独立理解检查"],
        },
        expected_effect="减少同类概念求助，并提高后续独立解释与正式练习表现。",
        created_at=now,
        updated_at=now,
    )


def _targeted_practice_for(
    *,
    section_id: str,
    binding: dict[str, list[str]],
    evidence: list[EvidenceItem],
    learning_assets: dict[str, Any],
) -> dict[str, Any]:
    """Choose a current-course formal task; never borrow from another course."""
    candidates = [
        item
        for key in ("validation_questions", "questions")
        for item in learning_assets.get(key) or []
        if isinstance(item, dict)
        and str(item.get("status") or "active") == "active"
        and str(item.get("revision_id") or item.get("task_revision_id") or "")
    ]
    failed_task_ids = {
        item.anchor.practice_task_id
        for item in evidence
        if item.anchor.practice_task_id
    }
    knowledge_ids = set(binding.get("knowledge_ids") or [])
    skill_ids = set(binding.get("skill_ids") or [])
    misconception_ids = set(binding.get("misconception_ids") or [])

    def score(item: dict[str, Any]) -> tuple[int, str]:
        revision_id = str(item.get("revision_id") or item.get("task_revision_id") or "")
        value = 0
        if str(item.get("node_id") or "") == section_id:
            value += 30
        value += len(knowledge_ids & set(item.get("course_knowledge_refs") or item.get("concept_ids") or [])) * 5
        value += len(skill_ids & set(item.get("course_skill_refs") or item.get("skill_unit_ids") or [])) * 9
        value += len(misconception_ids & set(item.get("course_misconception_refs") or item.get("misconception_ids") or [])) * 13
        if item in (learning_assets.get("validation_questions") or []):
            value += 4
        if revision_id in failed_task_ids:
            value -= 100
        return value, revision_id

    ranked: list[dict[str, Any]] = []
    seen_revision_ids: set[str] = set()
    for candidate in sorted(
        candidates,
        key=lambda item: (-score(item)[0], score(item)[1]),
    ):
        revision_id = str(
            candidate.get("revision_id")
            or candidate.get("task_revision_id")
            or ""
        )
        if not revision_id or revision_id in seen_revision_ids or score(candidate)[0] <= 0:
            continue
        seen_revision_ids.add(revision_id)
        ranked.append(candidate)

    selected = ranked[0] if ranked else None
    validation_task_ids = [
        str(item.get("revision_id") or item.get("task_revision_id") or "")
        for item in ranked
    ]
    if selected is not None:
        return {
            "asset_id": str(selected.get("asset_id") or selected.get("question_id") or ""),
            "revision_id": str(selected.get("revision_id") or selected.get("task_revision_id") or ""),
            "prompt": str(selected.get("prompt") or "完成这道针对性练习，并解释你的判断依据。"),
            "validation_task_ids": validation_task_ids,
        }
    return {
        "asset_id": "",
        "revision_id": "",
        "prompt": "用自己的话说明：这一步为什么必要？如果省略，会在哪个后续结论上出错？",
        "validation_task_ids": [],
    }


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
    composition_order: bool = False,
) -> dict[str, Any]:
    fallback = _animation_fallback_steps()
    if composition_order:
        fallback = [
            {"index": 1, "label": "从原始图形 v 开始"},
            {"index": 2, "label": "先应用右侧变换 B"},
            {"index": 3, "label": "再应用左侧变换 A"},
        ]
        keyframes = [
            AnimationKeyframe(
                index=1,
                label=fallback[0]["label"],
                state={
                    "focus": "input",
                    "description": "先固定同一个输入，暂不执行任何变换。",
                    "formula": "v",
                    "shape_points": "0,0 35,0 0,-25",
                    "vector_x": "35",
                    "vector_y": "0",
                },
                transformations=["show_input_shape", "highlight_formula_input"],
            ),
            AnimationKeyframe(
                index=2,
                label=fallback[1]["label"],
                state={
                    "focus": "right_transform",
                    "description": "ABv 中 B 紧挨输入 v，因此先由 B 作用，得到中间状态 Bv。",
                    "formula": "Bv",
                    "shape_points": "0,0 0,-35 -25,0",
                    "vector_x": "0",
                    "vector_y": "-35",
                },
                transformations=["apply_right_matrix", "hold_intermediate_state"],
            ),
            AnimationKeyframe(
                index=3,
                label=fallback[2]["label"],
                state={
                    "focus": "left_transform",
                    "description": "随后 A 作用在已经得到的 Bv 上，最终结果是 A(Bv)，不是 B(Av)。",
                    "formula": "A(Bv)",
                    "shape_points": "0,0 35,-35 -25,0",
                    "vector_x": "35",
                    "vector_y": "-35",
                },
                transformations=["apply_left_matrix", "compare_composition_order"],
            ),
        ]
    else:
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
            "kind": "course_state_transition",
        }, prefix="ans_"),
        title=(
            "复合变换顺序：为什么先做右边"
            if composition_order
            else f"{title}：分步变换演示"
        ),
        scene={
            "kind": "linear_transform_composition" if composition_order else "state_transition",
            "renderer": "linear_transform_composition_v1" if composition_order else "step_timeline_v1",
            "fallback": "static_keyframes",
            **({
                "left_operator": "A",
                "right_operator": "B",
                "composition": "ABv = A(Bv)",
            } if composition_order else {}),
        },
        object_bindings=[
            {
                "object_id": f"course-block:{block.block_id}",
                "object_type": "course_block",
                "role": "semantic_source",
            },
            *([
                {"object_id": "matrix:B", "object_type": "linear_transform", "role": "first_applied"},
                {"object_id": "matrix:A", "object_type": "linear_transform", "role": "second_applied"},
                {"object_id": "shape:v", "object_type": "plane_shape", "role": "input"},
            ] if composition_order else []),
        ],
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
            "动画在二维坐标平面依次展示原始图形、先应用右侧变换 B、"
            "再应用左侧变换 A，说明 ABv 等于 A(Bv)；每一帧均可暂停并阅读文字说明。"
            if composition_order
            else "动画依次展示输入与目标、单步变换及中间状态、最终结论之间的联系；"
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
        operation_ids = {
            operation.operation_id for operation in change_set.operations
        }
        animation_operation_ids = {
            operation.operation_id
            for operation in change_set.operations
            if operation.operation_type == "ADD_ANIMATION"
        }
        composition_operation_ids = {
            operation.operation_id
            for operation in change_set.operations
            if operation.operation_type == "ADD_ANIMATION"
            and str(
                (((operation.payload.get("animation_spec") or {}).get("scene") or {}).get("renderer"))
                or ""
            ) == "linear_transform_composition_v1"
        }
        feedback = [
            item for item in events
            if item.get("event_type") == "adaptive_block_feedback"
            and str(item.get("created_at") or "") >= change_set.accepted_at
            and str((item.get("metadata") or {}).get("adaptive_block_id") or "")
            in operation_ids
        ]
        interactions = [
            item for item in events
            if item.get("event_type") == "adaptive_block_interaction"
            and str(item.get("created_at") or "") >= change_set.accepted_at
            and str((item.get("metadata") or {}).get("adaptive_block_id") or "")
            in operation_ids
        ]
        later_attempts = [
            item for item in attempts
            if item.get("status") == "graded"
            and str(item.get("graded_at") or item.get("updated_at") or "") >= change_set.accepted_at
            and _attempt_matches_change_set(item, change_set)
        ]
        evidence_attempt_ids = {
            item.source_id
            for item in state.evidence_items
            if item.evidence_id in change_set.evidence_ids
            and item.source_type == "practice_attempt"
        }
        source_task_ids = set(
            change_set.impact_summary.get("source_practice_task_ids") or []
        )
        baseline_attempts = [
            item for item in attempts
            if item.get("status") == "graded"
            and (
                str(item.get("attempt_id") or "") in evidence_attempt_ids
                or (
                    str(
                        item.get("task_revision_id")
                        or item.get("question_revision_id")
                        or ""
                    ) in source_task_ids
                    and str(item.get("graded_at") or item.get("updated_at") or "")
                    < change_set.accepted_at
                )
            )
        ]
        helpful = any((item.get("result") or {}).get("feedback") == "helpful" for item in feedback)
        unhelpful = any((item.get("result") or {}).get("feedback") == "not_helpful" for item in feedback)
        correct_composition_answer = any(
            str((item.get("metadata") or {}).get("adaptive_block_id") or "")
            in composition_operation_ids
            and (item.get("result") or {}).get("interaction") == "animation_answered"
            and (item.get("result") or {}).get("correct") is True
            for item in interactions
        )
        generic_animation_engagement = any(
            str((item.get("metadata") or {}).get("adaptive_block_id") or "")
            in (animation_operation_ids - composition_operation_ids)
            and (item.get("result") or {}).get("interaction") == "animation_played"
            for item in interactions
        )
        engaged = correct_composition_answer or generic_animation_engagement
        passed = any((item.get("result") or {}).get("passed") is True for item in later_attempts)
        failed = sum((item.get("result") or {}).get("passed") is False for item in later_attempts)
        passed_attempts = [
            item for item in later_attempts
            if (item.get("result") or {}).get("passed") is True
        ]
        failed_attempts = [
            item for item in later_attempts
            if (item.get("result") or {}).get("passed") is False
        ]
        passed_task_ids = {
            str(
                item.get("task_revision_id")
                or item.get("question_revision_id")
                or ""
            )
            for item in passed_attempts
            if str(
                item.get("task_revision_id")
                or item.get("question_revision_id")
                or ""
            )
        }
        failed_task_ids = {
            str(
                item.get("task_revision_id")
                or item.get("question_revision_id")
                or ""
            )
            for item in failed_attempts
            if str(
                item.get("task_revision_id")
                or item.get("question_revision_id")
                or ""
            )
        }
        challenge_growth = change_set.growth_direction == "challenge"
        repeated_challenge_failure = (
            len(failed_task_ids) >= 2
            or (not failed_task_ids and failed >= 2)
        )
        if challenge_growth:
            # A challenge plan starts from an already-mastered base level.
            # Passing an independent harder task is direct evidence for the
            # growth plan and does not require an earlier UI interaction.
            # Harder-task failures only calibrate the new challenge; they must
            # never erase the learner's established base-level mastery.
            if passed:
                status = "effective"
            elif repeated_challenge_failure:
                status = "ineffective"
            else:
                status = "insufficient_evidence"
        elif (helpful or engaged) and passed:
            status = "effective"
        elif unhelpful and failed >= 2:
            status = "harmful"
        elif unhelpful or failed >= 2:
            status = "ineffective"
        else:
            status = "insufficient_evidence"
        verification_level = (
            "confirmed"
            if status == "effective" and len(passed_task_ids) >= 2
            else "initial_support"
            if status == "effective"
            else "not_verified"
        )
        baseline_latest = max(
            baseline_attempts,
            key=lambda item: str(item.get("graded_at") or item.get("updated_at") or ""),
            default=None,
        )
        follow_up_best = max(
            later_attempts,
            key=lambda item: _attempt_score(item) if _attempt_score(item) is not None else -1,
            default=None,
        )
        baseline_score = _attempt_score(baseline_latest)
        follow_up_score = _attempt_score(follow_up_best)
        score_delta = (
            round(follow_up_score - baseline_score, 1)
            if (
                not challenge_growth
                and baseline_score is not None
                and follow_up_score is not None
            )
            else None
        )
        if challenge_growth:
            interpretation = (
                "一项更高挑战已独立通过，旧难度掌握继续保留；还需要不同任务持续确认。"
                if verification_level == "initial_support"
                else "多个不同的更高挑战持续通过，挑战升级获得稳定证据支持。"
                if verification_level == "confirmed"
                else (
                    "旧难度掌握继续保留；更高挑战连续未通过，说明本次挑战跨度或支架需要调整，"
                    "不能据此倒推出原知识点未掌握。"
                )
                if status == "ineffective"
                else "旧难度掌握继续保留；目前还没有足够的新难度独立复验证据。"
            )
        else:
            interpretation = (
                "本轮独立复验通过，原判断获得新证据支持；仍需后续不同任务持续确认。"
                if verification_level == "initial_support"
                else "多个不同正式任务持续通过，当前课程变化获得稳定证据支持。"
                if verification_level == "confirmed"
                else "证据尚不足以判断课程变化的效果。"
            )
        change_set.effect_evaluation = {
            "status": status,
            "verification_level": verification_level,
            "growth_direction": change_set.growth_direction,
            "feedback_event_ids": [item.get("event_id") for item in feedback],
            "interaction_event_ids": [item.get("event_id") for item in interactions],
            "attempt_ids": [item.get("attempt_id") for item in later_attempts],
            "mastery_transition": (
                {
                    "base_difficulty": "mastered_preserved",
                    "higher_challenge": (
                        "validated"
                        if status == "effective"
                        else "needs_adjustment"
                        if status == "ineffective"
                        else "awaiting_validation"
                    ),
                }
                if challenge_growth
                else {}
            ),
            "verification_summary": {
                "baseline": {
                    "attempt_count": len(baseline_attempts),
                    "attempt_id": str((baseline_latest or {}).get("attempt_id") or ""),
                    "score": baseline_score,
                    "passed": (
                        ((baseline_latest or {}).get("result") or {}).get("passed")
                        if baseline_latest else None
                    ),
                },
                "course_change": {
                    "applied_block_count": len(change_set.applied_block_ids),
                    "interaction_completed": engaged,
                    "composition_answer_correct": correct_composition_answer,
                },
                "follow_up": {
                    "attempt_count": len(later_attempts),
                    "passed_attempt_count": len(passed_attempts),
                    "attempt_id": str((follow_up_best or {}).get("attempt_id") or ""),
                    "score": follow_up_score,
                    "passed": (
                        ((follow_up_best or {}).get("result") or {}).get("passed")
                        if follow_up_best else None
                    ),
                    "distinct_task_count": len(passed_task_ids),
                    "task_ids": sorted(passed_task_ids),
                    "failed_distinct_task_count": len(failed_task_ids),
                    "failed_task_ids": sorted(failed_task_ids),
                },
                "score_delta": score_delta,
                "interpretation": interpretation,
            },
            "recommended_action": (
                "keep" if status == "effective"
                else "rollback" if status == "harmful"
                else "adjust" if status == "ineffective"
                else "collect_more_evidence"
            ),
            "follow_up_candidate": (
                {
                    "candidate_type": "adjust_challenge_growth",
                    "status": "available",
                    "source_change_set_id": change_set.change_set_id,
                    "reason": (
                        "旧难度掌握保持不变；当前更高挑战连续未通过，"
                        "建议缩小挑战跨度或增加必要支架后重新复验。"
                    ),
                }
                if challenge_growth and status == "ineffective"
                else
                {
                    "candidate_type": "rollback_course_evolution",
                    "status": "pending_confirmation",
                    "source_change_set_id": change_set.change_set_id,
                    "reason": "负面反馈与重复失败同时出现，建议撤销当前课程变化。",
                }
                if status == "harmful"
                else {
                    "candidate_type": "adjust_course_evolution",
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
    change_set: CourseEvolutionPlan,
) -> bool:
    impact = change_set.impact_summary
    task_id = str(
        attempt.get("task_revision_id")
        or attempt.get("question_revision_id")
        or ""
    )
    source_task_ids = set(impact.get("source_practice_task_ids") or [])
    validation_task_ids = set(impact.get("validation_task_ids") or [])
    if task_id and task_id in source_task_ids:
        return False
    if validation_task_ids:
        return bool(task_id and task_id in validation_task_ids)

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


def _attempt_score(attempt: dict[str, Any] | None) -> float | None:
    if not attempt:
        return None
    result = attempt.get("result") or {}
    raw_score = result.get("score")
    if isinstance(raw_score, (int, float)) and not isinstance(raw_score, bool):
        return round(float(raw_score), 1)
    passed = result.get("passed")
    if passed is True:
        return 100.0
    if passed is False:
        return 0.0
    return None


def _evolution_demo_mode() -> bool:
    """Demo recordings may relax the strong-evidence contract via env flag."""
    return os.getenv("EVOLUTION_DEMO_MODE", "").strip().lower() in {
        "1", "true", "yes", "on",
    }


def _strong_self_report_contract(statement: str) -> dict[str, Any]:
    """Recognize a complete, actionable learner request without matching one script.

    A broad course change needs an explicit semantic contract: the learner
    distinguishes what they can already do from the conceptual gap, says the
    gap is persistent, requests a supported teaching response, and names the
    boundary. A weaker request can still become strong local evidence when it
    precisely identifies the current scope and asks for a concrete explanation.
    """
    text = _compact(statement)
    capability_patterns = (
        r"(?:我)?(?:会|能|可以|已经掌握|已经会).{0,12}(?:计算|做题|操作|步骤|求解|套公式|运算)",
        r"(?:计算|做题|操作|步骤|求解|套公式|运算).{0,6}(?:我)?(?:会|能|没问题)",
    )
    gap_patterns = (
        r"(?:不理解|没理解|不明白|没明白|搞不清|弄不清|看不懂).{0,10}(?:为什么|原因|含义|原理|顺序)?",
        r"(?:顺序|概念|原理|含义).{0,8}(?:理解反|弄反|搞反|不清楚)",
        r"(?:卡在|困在).{0,16}(?:为什么|原因|含义|原理|顺序)",
    )
    persistence_markers = (
        "一直", "总是", "反复", "始终", "经常", "老是", "每次", "仍然", "还是",
    )
    downstream_scope_patterns = (
        r"本(?:小)?节.{0,12}(?:后面|后续|之后|接下来)",
        r"(?:后面|后续|之后|接下来).{0,10}(?:相关内容|相关章节|相关小节|相关部分)",
        r"(?:当前|这)(?:一)?节.{0,8}(?:以及|和|及).{0,8}(?:后面|后续|之后)",
    )
    local_scope_markers = (
        "本节", "本小节", "这一节", "这节", "当前小节", "当前位置", "这里", "这部分",
    )
    support_markers = {
        "explanation": (
            "解释", "讲清", "说明原因", "说明为什么", "分步讲", "展开讲", "详细讲",
        ),
        "animation": (
            "动画", "动态演示", "可视化", "几何图", "图形演示", "分步演示",
        ),
        "practice": (
            "让我计算", "让我进行计算", "让我做题", "再做一题", "练习", "理解检查", "检查理解",
        ),
    }

    capability_text = next(
        (
            match.group("capability").strip()
            for pattern in (
                r"(?P<capability>[^，。！？；\n]{1,24}?(?:计算|做题|操作|步骤|求解|套公式|运算))"
                r"(?:我)?(?:会|能|可以|已经掌握|已经会)(?:做|完成)?",
            )
            if (match := re.search(pattern, text))
        ),
        "",
    )
    capability_text = capability_text or next(
        (
            match.group(0)
            for pattern in capability_patterns
            if (match := re.search(pattern, text))
        ),
        "",
    )
    gap_text = next(
        (
            match.group(0)
            for pattern in gap_patterns
            if (match := re.search(pattern, text))
        ),
        "",
    )
    if (
        "复合" in text
        and any(marker in text for marker in ("顺序", "先后", "先右后左", "右后左"))
        and gap_text
    ):
        gap_text = "不理解复合变换顺序"
    has_capability = bool(capability_text)
    has_gap = bool(gap_text)
    has_persistence = any(marker in text for marker in persistence_markers)
    requested_supports = [
        support
        for support, markers in support_markers.items()
        if any(marker in text for marker in markers)
    ]
    if any(re.search(pattern, text) for pattern in downstream_scope_patterns):
        scope = "current_and_next"
    elif any(marker in text for marker in local_scope_markers):
        scope = "current"
    else:
        scope = ""

    complete_contract = bool(
        has_capability
        and has_gap
        and has_persistence
        and requested_supports
        and scope
    )
    if _evolution_demo_mode() and not complete_contract:
        # Demo mode (EVOLUTION_DEMO_MODE=1): a clear gap plus a concrete
        # teaching request is enough to trigger growth, so a recording can
        # rely on one scripted sentence instead of a full evidence trail.
        complete_contract = bool(has_gap and requested_supports)
        if complete_contract and not scope:
            scope = "current"
    precise_local_request = bool(
        has_gap
        and scope == "current"
        and requested_supports
        and any(marker in text for marker in ("每一步", "具体", "详细", "逐步", "完整"))
    )
    return {
        "is_strong": complete_contract or precise_local_request,
        "is_complete_contract": complete_contract,
        "has_capability_boundary": has_capability,
        "has_explicit_gap": has_gap,
        "has_persistence": has_persistence,
        "has_teaching_request": bool(requested_supports),
        "requested_supports": requested_supports,
        "capability_text": capability_text,
        "gap_text": gap_text,
        "scope": scope,
    }


def strong_self_report_contract(statement: str) -> dict[str, Any]:
    """Public parser shared by learner-facing course-adjustment entrypoints."""
    return deepcopy(_strong_self_report_contract(statement))


def _event_signal(event: dict[str, Any]) -> tuple[str, float, bool]:
    event_type = str(event.get("event_type") or "")
    statement = str((event.get("evidence") or {}).get("statement") or "")
    feedback = str((event.get("result") or {}).get("feedback") or "")
    if event_type == "learner_self_reported":
        contract = _strong_self_report_contract(statement)
        if contract["is_strong"]:
            return "explicit_comprehension_gap", 0.96, False
        explicit = any(marker in statement for marker in ("完全看不懂", "不理解为什么", "推导跳步", "还是没懂", "没有解决"))
        return "explicit_comprehension_gap", 0.9 if explicit else 0.56, False
    if event_type == "assistant_question_submitted":
        question = str((event.get("evidence") or {}).get("question") or "")
        contract = _strong_self_report_contract(question)
        if contract["is_strong"]:
            return "explicit_comprehension_gap", 0.96, False
        explicit = any(marker in question for marker in (
            "完全看不懂", "不理解为什么", "为什么要", "推导跳步", "还是没懂", "不会",
        ))
        return "learner_question", 0.84 if explicit else 0.48, False
    if event_type == "assistant_answer_feedback_submitted":
        return "assistant_feedback", 0.72 if feedback == "unclear" else 0.55, feedback in {"resolved", "helpful"}
    # These are audit events for durable records that are projected separately
    # below. Counting both copies would turn one learner action into two pieces
    # of evidence and inflate the adaptation confidence.
    if event_type in {
        "practice_attempt_graded",
        "learning_record_created",
        "learning_record_updated",
    }:
        return "", 0.0, False
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


def _diagnosis_claim(
    evidence: list[EvidenceItem],
    knowledge_base: dict[str, Any] | None,
) -> str:
    """Turn multiple evidence traces into one knowledge-grounded learner claim."""
    summaries = " ".join(item.summary for item in evidence)
    knowledge_ids = {
        value for item in evidence for value in item.anchor.knowledge_node_ids
    }
    ability_ids = {
        value for item in evidence for value in item.anchor.ability_point_ids
    }
    misconception_ids = {
        value for item in evidence for value in item.anchor.misconception_point_ids
    }
    knowledge_labels = _knowledge_labels(knowledge_base, knowledge_ids)
    ability_labels = _ability_labels(knowledge_base, ability_ids)
    misconception_labels = _misconception_labels(knowledge_base, misconception_ids)
    procedural_strength = any(marker in summaries for marker in (
        "会计算", "会做", "能算", "步骤会", "计算会", "计算我会", "规则会",
    ))
    order_gap = any(marker in summaries for marker in (
        "变换顺序", "乘法顺序", "复合顺序", "复合变换的先后顺序", "先右后左",
        "先做右边", "顺序总是理解反",
    ))
    ability_focus = _ability_focus(ability_labels[0]) if ability_labels else ""

    if procedural_strength and order_gap:
        return "学习者会执行计算，但尚未理解复合变换的先后顺序。"
    if procedural_strength and ability_focus:
        return f"学习者会执行计算，但尚未理解{ability_focus}。"
    if procedural_strength and knowledge_labels:
        return f"学习者会执行步骤，但尚未形成对「{_knowledge_focus(knowledge_labels[0])}」的概念理解。"
    if ability_labels:
        return f"多条学习证据共同指向「{ability_labels[0]}」这一能力缺口。"
    if misconception_labels:
        return f"多条学习证据共同命中易错点「{misconception_labels[0]}」。"
    if knowledge_labels:
        return f"多条学习证据共同指向「{_knowledge_focus(knowledge_labels[0])}」的理解缺口。"
    return "多条学习证据共同指向当前概念的理解缺口，而不是单次作答波动。"


def _ability_focus(label: str) -> str:
    focus = re.sub(
        r"^(能够|能|解释|理解|判断|应用|分析|说明|辨析|掌握|使用|完成)",
        "",
        str(label or "").strip(),
    ).strip()
    if "复合" in focus and "顺序" in focus:
        return "复合变换的先后顺序"
    return focus or str(label or "").strip()


def _knowledge_focus(label: str) -> str:
    return re.sub(
        r"(的)?(含义|概念|原理|基础)$",
        "",
        str(label or "").strip(),
    ).strip() or str(label or "").strip()


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
    if count == 1:
        return [block_id]

    source_binding = _knowledge_binding_for_anchor(
        knowledge_base or {},
        section_id=ordered[index].section_id,
        block_id=block_id,
    )
    source_knowledge_ids = set(source_binding["knowledge_ids"])
    related_knowledge_ids = set(source_knowledge_ids)
    for relation in (knowledge_base or {}).get("relations") or []:
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
        for binding in (knowledge_base or {}).get("bindings") or []
        if binding.get("target_type") == "course_block"
        and set(binding.get("knowledge_ids") or []) & related_knowledge_ids
    }
    source_section_id = ordered[index].section_id
    following = ordered[index + 1:]
    related = [item for item in following if item.block_id in related_block_ids]

    def spread_sections(items: list[CourseBlock]) -> list[CourseBlock]:
        """Put the first block of each later section before same-section tails."""
        first_by_section: list[CourseBlock] = []
        remainder: list[CourseBlock] = []
        seen_sections: set[str] = set()
        for item in items:
            if item.section_id not in seen_sections:
                first_by_section.append(item)
                seen_sections.add(item.section_id)
            else:
                remainder.append(item)
        return [*first_by_section, *remainder]

    related_later = spread_sections([
        item for item in related if item.section_id != source_section_id
    ])
    related_current = [
        item for item in related if item.section_id == source_section_id
    ]
    fallback_later = spread_sections([
        item
        for item in following
        if item.section_id != source_section_id
        and item.block_id not in related_block_ids
    ])
    fallback_current = [
        item
        for item in following
        if item.section_id == source_section_id
        and item.block_id not in related_block_ids
    ]

    selected = [block_id]
    # A "current and related later" request must visibly reach at least one
    # later section when the course contains one. Knowledge-linked nodes stay
    # first; sparse legacy bindings fall back to the earliest later sections
    # instead of consuming the entire budget on sibling blocks in the current
    # section.
    for item in [
        *related_later,
        *related_current,
        *fallback_later,
        *fallback_current,
    ]:
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


def _default_document_repository() -> CourseDocumentRepository:
    from storage import storage

    return CourseDocumentRepository(storage)


def _bound_revision_vector(
    document: CourseDocument,
    block_ids: list[str],
) -> dict[str, str]:
    vector = revision_vector_for_document(document).revisions
    blocks = {block.block_id: block for block in document.blocks}
    section_ids = {
        blocks[block_id].section_id
        for block_id in block_ids
        if block_id in blocks
    }
    allowed = {
        *(f"block:{block_id}" for block_id in block_ids),
        *(f"section:{section_id}" for section_id in section_ids),
    }
    return {key: value for key, value in vector.items() if key in allowed}


def _course_block_insertions(
    change_set: CourseEvolutionPlan,
    document: CourseDocument,
    *,
    selected_scope: Literal["current", "current_and_next"],
    selected_operation_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    if change_set.course_id != document.course_id:
        raise ValueError("Course evolution plan belongs to another course")
    blocks = {block.block_id: block for block in document.blocks}
    kind_by_operation = {
        "INSERT_COURSE_SUPPORT": "callout",
        "INSERT_PERSONAL_SUPPORT": "callout",
        "ADD_TRANSITION_SUPPORT": "callout",
        "ADD_CHECKPOINT": "callout",
        "ADD_TARGETED_PRACTICE": "practice_ref",
        "ADD_ANIMATION": "diagram",
    }
    role_by_operation = {
        "INSERT_COURSE_SUPPORT": "remediation",
        "INSERT_PERSONAL_SUPPORT": "remediation",
        "ADD_TRANSITION_SUPPORT": "transfer",
        "ADD_CHECKPOINT": "checkpoint",
        "ADD_TARGETED_PRACTICE": "checkpoint",
        "ADD_ANIMATION": "reasoning",
    }
    title_by_operation = {
        "INSERT_COURSE_SUPPORT": "针对当前理解的补充",
        "INSERT_PERSONAL_SUPPORT": "针对当前理解的补充",
        "ADD_TRANSITION_SUPPORT": "进入后续内容前",
        "ADD_CHECKPOINT": "理解检查",
        "ADD_TARGETED_PRACTICE": "针对性练习",
        "ADD_ANIMATION": "分步演示",
    }
    insertions: list[dict[str, Any]] = []
    for operation in change_set.operations:
        if selected_scope == "current" and operation.scope == "next":
            continue
        if (
            selected_operation_ids is not None
            and operation.operation_id not in selected_operation_ids
        ):
            continue
        target = blocks.get(operation.target_block_id)
        if target is None or target.status == "retired":
            raise ValueError("Course evolution target block is unavailable")
        if operation.target_section_id and operation.target_section_id != target.section_id:
            raise ValueError("Course evolution target section does not match its block")
        block_id = stable_hash({
            "course_id": document.course_id,
            "change_set_id": change_set.change_set_id,
            "operation_id": operation.operation_id,
        }, prefix="ceb_")
        payload = deepcopy(operation.payload)
        if operation.operation_type == "ADD_TARGETED_PRACTICE":
            validation_task_ids = [
                str(value).strip()
                for value in change_set.impact_summary.get("validation_task_ids") or []
                if str(value).strip()
            ]
            primary_task_id = str(payload.get("practice_task_id") or "").strip()
            if primary_task_id and primary_task_id not in validation_task_ids:
                validation_task_ids.insert(0, primary_task_id)
            payload["validation_task_ids"] = list(dict.fromkeys(validation_task_ids))
        payload.update({
            "title": title_by_operation[operation.operation_type],
            "markdown": _course_evolution_markdown(operation),
            "course_evolution": {
                "schema_version": "course_evolution_block_v1",
                "change_set_id": change_set.change_set_id,
                "operation_id": operation.operation_id,
                "hypothesis_id": change_set.hypothesis_id,
                "evidence_ids": list(change_set.evidence_ids),
                "reason": operation.reason,
                "expected_effect": change_set.expected_effect,
            },
        })
        knowledge_refs = [
            str(value)
            for value in payload.get("knowledge_refs") or target.concept_refs
            if value
        ]
        insertions.append({
            "after_block_id": target.block_id,
            "block": CourseBlock(
                block_id=block_id,
                section_id=target.section_id,
                position=target.position + 1,
                kind=kind_by_operation[operation.operation_type],
                role=role_by_operation[operation.operation_type],
                payload=payload,
                asset_refs=list(payload.get("validation_task_ids") or []),
                objective_refs=list(target.objective_refs),
                concept_refs=knowledge_refs,
                evidence_refs=list(change_set.evidence_ids),
                status="final",
            ),
        })
    if not insertions:
        raise ValueError("Course evolution plan contains no operations in the selected scope")
    return insertions


def _course_block_mutations(
    change_set: CourseEvolutionPlan,
    document: CourseDocument,
    *,
    selected_scope: Literal["current", "current_and_next"],
    selected_operation_ids: set[str] | None = None,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[str],
    list[dict[str, str]],
]:
    """Compile reviewed section edits and legacy growth blocks into one commit."""
    replacements: list[dict[str, Any]] = []
    insertions: list[dict[str, Any]] = []
    canonical_operations = {
        "REPLACE_COURSE_BLOCK",
        "INSERT_COURSE_BLOCK",
        "FOLD_COURSE_BLOCK",
        "REORDER_COURSE_BLOCK",
        "ADJUST_COURSE_DIFFICULTY",
    }
    has_canonical_operations = any(
        operation.operation_type in canonical_operations
        for operation in change_set.operations
    )
    if not has_canonical_operations:
        return (
            replacements,
            _course_block_insertions(
                change_set,
                document,
                selected_scope=selected_scope,
                selected_operation_ids=selected_operation_ids,
            ),
            [],
            [],
        )

    if change_set.course_id != document.course_id:
        raise ValueError("Course evolution plan belongs to another course")
    blocks = {block.block_id: block for block in document.blocks}
    section_ids = {section.section_id for section in document.sections}
    retire_block_ids: list[str] = []
    reorderings: list[dict[str, str]] = []
    for operation in change_set.operations:
        if selected_scope == "current" and operation.scope == "next":
            continue
        if operation.operation_type == "ADJUST_COURSE_DIFFICULTY":
            continue
        if (
            selected_operation_ids is not None
            and operation.operation_id not in selected_operation_ids
        ):
            continue
        if operation.operation_type == "FOLD_COURSE_BLOCK":
            current = blocks.get(operation.target_block_id)
            if current is None or current.status == "retired":
                raise ValueError("Course evolution fold target is unavailable")
            retire_block_ids.append(current.block_id)
            continue
        if operation.operation_type == "REORDER_COURSE_BLOCK":
            current = blocks.get(operation.target_block_id)
            if current is None or current.status == "retired":
                raise ValueError("Course evolution reorder target is unavailable")
            after_block_id = str(operation.payload.get("after_block_id") or "")
            if after_block_id:
                anchor = blocks.get(after_block_id)
                if anchor is None or anchor.status == "retired":
                    raise ValueError("Course evolution reorder anchor is unavailable")
                if anchor.section_id != current.section_id:
                    raise ValueError("Course evolution reorder crossed its section boundary")
                if anchor.block_id == current.block_id:
                    raise ValueError("Course evolution reorder cannot anchor to itself")
            reorderings.append({
                "block_id": current.block_id,
                "after_block_id": after_block_id,
            })
            continue
        proposed_raw = operation.payload.get("proposed_block")
        if not isinstance(proposed_raw, dict):
            raise ValueError("Course evolution candidate is incomplete")
        proposed = CourseBlock.model_validate(proposed_raw)
        if proposed.section_id not in section_ids:
            raise ValueError("Course evolution candidate targets an unknown section")
        if operation.target_section_id and proposed.section_id != operation.target_section_id:
            raise ValueError("Course evolution candidate crossed its section boundary")
        if operation.operation_type == "REPLACE_COURSE_BLOCK":
            current = blocks.get(operation.target_block_id)
            if current is None or current.status == "retired":
                raise ValueError("Course evolution target block is unavailable")
            if proposed.block_id != current.block_id or proposed.section_id != current.section_id:
                raise ValueError("Course evolution replacement changed stable block identity")
            replacements.append({
                "block_id": current.block_id,
                "expected_block_revision": str(
                    operation.payload.get("expected_block_revision")
                    or current.internal_revision
                ),
                "payload": deepcopy(proposed.payload),
                "asset_refs": list(proposed.asset_refs),
                "objective_refs": list(proposed.objective_refs),
                "concept_refs": list(proposed.concept_refs),
                "evidence_refs": list(proposed.evidence_refs),
                "visibility_rule": deepcopy(proposed.visibility_rule),
            })
            continue
        if operation.operation_type == "INSERT_COURSE_BLOCK":
            anchor_id = str(
                operation.payload.get("after_block_id")
                or operation.target_block_id
            )
            anchor = blocks.get(anchor_id)
            if anchor is None or anchor.status == "retired":
                raise ValueError("Course evolution insertion anchor is unavailable")
            if proposed.section_id != anchor.section_id:
                raise ValueError("Course evolution insertion crossed its section boundary")
            insertions.append({
                "after_block_id": anchor_id,
                "block": proposed,
            })

    if not replacements and not insertions and not retire_block_ids and not reorderings:
        raise ValueError("Course evolution plan contains no content mutations")
    return replacements, insertions, retire_block_ids, reorderings


def _previous_active_block_id(
    document: CourseDocument,
    block_id: str,
) -> str:
    target = next(
        (block for block in document.blocks if block.block_id == block_id),
        None,
    )
    if target is None:
        return ""
    ordered = sorted(
        (
            block
            for block in document.blocks
            if block.section_id == target.section_id
            and block.status != "retired"
        ),
        key=lambda block: (block.position, block.block_id),
    )
    index = next(
        (position for position, block in enumerate(ordered) if block.block_id == block_id),
        -1,
    )
    return ordered[index - 1].block_id if index > 0 else ""


def _course_evolution_markdown(operation: CourseEvolutionOperation) -> str:
    payload = operation.payload
    parts = [str(payload.get("body") or "").strip()]
    if payload.get("contrast"):
        parts.append(f"> {str(payload['contrast']).strip()}")
    if payload.get("prompt"):
        prompt_label = "请完成" if operation.operation_type == "ADD_TARGETED_PRACTICE" else "请思考"
        parts.append(f"**{prompt_label}：** {str(payload['prompt']).strip()}")
    if payload.get("objective"):
        parts.append(f"**完成标准：** {str(payload['objective']).strip()}")
    steps = [
        str(item.get("label") or "").strip()
        for item in payload.get("steps") or []
        if isinstance(item, dict) and str(item.get("label") or "").strip()
    ]
    if steps:
        parts.append("\n".join(
            f"{index}. {label}"
            for index, label in enumerate(steps, start=1)
        ))
    return "\n\n".join(part for part in parts if part)


def _course_document(course_data: dict[str, Any]) -> CourseDocument:
    raw = course_data.get("course_document")
    if not isinstance(raw, dict):
        from course_document import document_from_legacy_course

        return document_from_legacy_course(course_data)
    return CourseDocument.model_validate(raw)


def _block_text(payload: dict[str, Any]) -> str:
    value = str(payload.get("markdown") or payload.get("text") or payload.get("content") or "")
    # Course evidence should quote the readable teaching text, not implementation
    # syntax from embedded diagrams or HTML layouts. Besides looking noisy, a
    # truncated fenced block can be reparsed as malformed Markdown after the
    # excerpt is inserted into a new course block.
    value = re.sub(r"```[\s\S]*?```", " ", value)
    value = re.sub(r"<[^>]+>", " ", value)
    return _compact(value, limit=240)


def _compact(value: Any, *, limit: int = 180) -> str:
    text = re.sub(r"[`*_#>\[\]()]", " ", str(value or ""))
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit].rstrip() + "..."


def _change_set(state: CourseEvolutionState, change_set_id: str) -> CourseEvolutionPlan:
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
    "CourseEvolutionOperation",
    "CourseEvolutionPlan",
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
    "personal_course_overlay",
    "reject_change_set",
    "reject_adaptation_plan",
    "synchronize_and_evaluate_course_evolution",
    "undo_change_set",
    "undo_adaptation_plan",
]
