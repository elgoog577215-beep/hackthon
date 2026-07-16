"""Evidence-driven, learner-isolated course evolution state and projections."""

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


class CourseEvolutionOperation(BaseModel):
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


class CourseEvolutionChangeSet(BaseModel):
    change_set_id: str
    user_id: str
    course_id: str
    hypothesis_id: str
    base_revision_vector: dict[str, str] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    operations: list[CourseEvolutionOperation] = Field(default_factory=list)
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
    change_sets: list[CourseEvolutionChangeSet] = Field(default_factory=list)
    revision: str = ""
    updated_at: str


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
    state = repository.load(user_id, course_id)
    state.evidence_items = _collect_evidence(course_data, document, user_id=user_id)
    _evaluate_hypotheses_and_candidates(state, document)
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
    hypothesis = _hypothesis(state, change_set.hypothesis_id)
    hypothesis.status = "evaluating"
    hypothesis.updated_at = change_set.accepted_at
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
                "ADD_ANIMATION": "counterexample",
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
                },
                "reason_code": "accepted_evidence_driven_growth",
                "evidence_refs": change_set.evidence_ids,
                "status": "active",
                "expires_at": "",
                "feedback": {"value": "unrated", "options": ["helpful", "not_helpful", "dismissed"]},
            })
    return blocks


def course_evolution_view(state: CourseEvolutionState) -> dict[str, Any]:
    payload = state.model_dump(mode="json")
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
            anchor=_resolve_anchor(document, event),
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
            anchor=_resolve_anchor(document, record),
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
            anchor=_resolve_anchor(document, attempt),
            created_at=str(attempt.get("graded_at") or attempt.get("updated_at") or _now()),
        ))
    return sorted(items, key=lambda item: item.created_at)


def _evaluate_hypotheses_and_candidates(
    state: CourseEvolutionState,
    document: CourseDocument,
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
        affected = _affected_blocks(document, block_id, scope=scope)
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
        )
        state.change_sets.append(change_set)
        hypothesis.status = "candidate_created"


def _build_change_set(
    state: CourseEvolutionState,
    document: CourseDocument,
    hypothesis: AdaptationHypothesis,
    *,
    evidence_signature: str,
) -> CourseEvolutionChangeSet:
    blocks = {item.block_id: item for item in document.blocks}
    sections = {item.section_id: item for item in document.sections}
    target = blocks[hypothesis.target_block_id]
    target_text = _block_text(target.payload)
    target_title = str(target.payload.get("title") or sections.get(target.section_id, {}).title if sections.get(target.section_id) else "当前内容")
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
            "steps": [
                {"index": 1, "label": "确定输入与目标"},
                {"index": 2, "label": "执行当前变换并观察中间状态"},
                {"index": 3, "label": "把中间状态连接到最终结论"},
            ],
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
    return CourseEvolutionChangeSet(
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
            "protected": ["基础课程", "其他学习者课程", "历史作答", "笔记原文", "正式知识库"],
            "representation_impacts": ["个人讲义补充", "分步演示", "理解检查"],
        },
        expected_effect="减少同类概念求助，并提高后续独立解释与正式练习表现。",
        created_at=now,
        updated_at=now,
    )


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
        ]
        helpful = any((item.get("result") or {}).get("feedback") == "helpful" for item in feedback)
        unhelpful = any((item.get("result") or {}).get("feedback") == "not_helpful" for item in feedback)
        passed = any((item.get("result") or {}).get("passed") is True for item in later_attempts)
        failed = sum((item.get("result") or {}).get("passed") is False for item in later_attempts)
        if helpful and passed:
            status = "effective"
        elif unhelpful and failed >= 2:
            status = "ineffective"
        else:
            status = "insufficient_evidence"
        change_set.effect_evaluation = {
            "status": status,
            "feedback_event_ids": [item.get("event_id") for item in feedback],
            "attempt_ids": [item.get("attempt_id") for item in later_attempts],
            "evaluated_at": _now(),
        }
        hypothesis = _hypothesis(state, change_set.hypothesis_id)
        if status in {"effective", "ineffective", "harmful"}:
            hypothesis.status = status
            hypothesis.updated_at = _now()


def _event_signal(event: dict[str, Any]) -> tuple[str, float, bool]:
    event_type = str(event.get("event_type") or "")
    statement = str((event.get("evidence") or {}).get("statement") or "")
    feedback = str((event.get("result") or {}).get("feedback") or "")
    if event_type == "learner_self_reported":
        explicit = any(marker in statement for marker in ("完全看不懂", "不理解为什么", "推导跳步", "还是没懂", "没有解决"))
        return "explicit_comprehension_gap", 0.9 if explicit else 0.56, False
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
        or evidence.get("quote")
        or result.get("feedback")
        or event.get("event_type")
    )


def _resolve_anchor(document: CourseDocument, source: dict[str, Any]) -> EvidenceAnchor:
    vector = revision_vector_for_document(document).revisions
    blocks = {item.block_id: item for item in document.blocks}
    section_ids = {item.section_id for item in document.sections}
    raw_anchor = source.get("anchor") or (source.get("evidence") or {}).get("anchor") or (source.get("metadata") or {}).get("content_anchor") or {}
    block_id = str(
        raw_anchor.get("content_block_id")
        or raw_anchor.get("block_id")
        or (source.get("metadata") or {}).get("block_id")
        or ""
    )
    node_id = str(source.get("node_id") or "")
    if not block_id and node_id in blocks:
        block_id = node_id
    section_id = blocks[block_id].section_id if block_id in blocks else (node_id if node_id in section_ids else "")
    if not block_id and section_id:
        block = next((item for item in document.blocks if item.section_id == section_id and item.status != "retired"), None)
        block_id = block.block_id if block else ""
    revision = vector.get(f"block:{block_id}", "") if block_id else ""
    return EvidenceAnchor(
        section_id=section_id,
        block_id=block_id,
        span=deepcopy(raw_anchor.get("span") or {}),
        knowledge_node_ids=[str(item) for item in source.get("concept_ids") or [] if item],
        ability_point_ids=[str(item) for item in source.get("skill_unit_ids") or [] if item],
        misconception_point_ids=[str(item) for item in source.get("mistake_point_ids") or [] if item],
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
    return [item.block_id for item in ordered[index:index + count]]


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


def _change_set(state: CourseEvolutionState, change_set_id: str) -> CourseEvolutionChangeSet:
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


course_evolution_repository = CourseEvolutionRepository()

__all__ = [
    "AdaptationHypothesis",
    "CourseEvolutionChangeSet",
    "CourseEvolutionRepository",
    "CourseEvolutionState",
    "EvidenceItem",
    "accept_change_set",
    "course_evolution_repository",
    "course_evolution_view",
    "project_applied_adaptive_blocks",
    "reject_change_set",
    "synchronize_and_evaluate_course_evolution",
    "undo_change_set",
]
