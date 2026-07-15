"""Typed AI-teacher proposals, idempotent execution, receipts, and triggers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Any

from ai_teacher_state import AITeacherRepository, ai_teacher_repository
from learning_events import record_learning_event
from learning_records import (
    InvalidRecordTransition,
    RecordConflict,
    enrich_record_payload,
    learning_record_repository,
    project_record,
)
from learning_runtime import build_learning_runtime


ACTION_TYPES = {
    "create_note",
    "create_issue",
    "create_review_task",
    "create_bookmark",
    "open_runtime_action",
}
RECORD_ACTION_TYPES = {
    "create_note": "note",
    "create_issue": "issue",
    "create_review_task": "review_task",
    "create_bookmark": "bookmark",
}
STRONG_RUNTIME_ACTIONS = {
    "confirm_version_change",
    "resume_diagnostic",
    "resume_remediation",
    "resume_validation",
    "resolve_diagnostic_support",
    "resolve_blocking_issue",
    "start_due_review",
}


class ProposalStale(Exception):
    pass


class ActionForbidden(Exception):
    pass


def propose_action(
    course: dict[str, Any],
    *,
    user_id: str,
    action_type: str,
    target_ref: dict[str, Any],
    payload: dict[str, Any],
    conversation_id: str = "",
    message_id: str = "",
    reason: str = "",
    evidence_refs: list[dict[str, Any]] | None = None,
    confirmation_mode: str = "explicit",
    origin: str = "assistant",
    repository: AITeacherRepository | None = None,
) -> dict[str, Any]:
    repository = repository or ai_teacher_repository
    if action_type not in ACTION_TYPES:
        raise ActionForbidden(f"unsupported AI teacher action: {action_type}")
    course_id = str(course.get("course_id") or "")
    node_id = str(target_ref.get("node_id") or payload.get("node_id") or "")
    runtime = build_learning_runtime(course, user_id=user_id, node_id=node_id or None)
    runtime_revision_id = str(runtime.get("runtime_revision_id") or "")
    dedupe_key = _dedupe_key(
        action_type,
        target_ref,
        evidence_refs or [],
        runtime_revision_id,
        message_id,
    )
    return repository.create_proposal(user_id, course_id, {
        "conversation_id": conversation_id,
        "message_id": message_id,
        "action_type": action_type,
        "target_ref": target_ref,
        "payload_preview": _payload_preview(action_type, payload),
        "payload": payload,
        "reason": reason,
        "evidence_refs": evidence_refs or [],
        "expected_effect": _expected_effect(action_type),
        "confirmation_mode": confirmation_mode,
        "runtime_revision_id": runtime_revision_id,
        "expected_revisions": {
            "course_version_id": str(course.get("current_course_version_id") or ""),
            "runtime_revision_id": runtime_revision_id,
        },
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat(),
        "dedupe_key": dedupe_key,
        "undo_capability": "archive_record" if action_type in RECORD_ACTION_TYPES else "none",
        "origin": origin,
    })


def execute_proposal(
    course: dict[str, Any],
    *,
    user_id: str,
    proposal_id: str,
    idempotency_key: str,
    repository: AITeacherRepository | None = None,
) -> dict[str, Any]:
    repository = repository or ai_teacher_repository
    course_id = str(course.get("course_id") or "")
    existing = repository.receipt_for_key(user_id, course_id, idempotency_key)
    if existing:
        return existing
    proposal = repository.get_proposal(user_id, course_id, proposal_id)
    if not proposal:
        raise KeyError(proposal_id)
    if str(proposal.get("action_type") or "") not in ACTION_TYPES:
        raise ActionForbidden("proposal action is not registered")
    if proposal.get("status") == "rejected":
        raise ActionForbidden("proposal was rejected")
    if proposal.get("status") == "succeeded" and proposal.get("receipt_id"):
        receipt = repository.get_receipt(user_id, course_id, str(proposal["receipt_id"]))
        if receipt:
            return receipt
    _require_not_expired(proposal)

    node_id = str((proposal.get("target_ref") or {}).get("node_id") or "")
    runtime_before = build_learning_runtime(course, user_id=user_id, node_id=node_id or None)
    expected_runtime = str(proposal.get("runtime_revision_id") or "")
    current_runtime = str(runtime_before.get("runtime_revision_id") or "")
    if expected_runtime and expected_runtime != current_runtime:
        repository.update_proposal(
            user_id,
            course_id,
            proposal_id,
            status="stale",
            changes={"failure_reason": "learning runtime changed"},
        )
        receipt = _save_failure_receipt(
            repository,
            user_id=user_id,
            course_id=course_id,
            proposal=proposal,
            idempotency_key=idempotency_key,
            status="stale",
            reason="学习状态已经变化，请重新计算建议。",
            runtime_revision_id=current_runtime,
        )
        return receipt

    repository.update_proposal(
        user_id,
        course_id,
        proposal_id,
        status="executing",
        changes={"confirmed_at": _now()},
    )
    action_type = str(proposal.get("action_type") or "")
    try:
        if action_type in RECORD_ACTION_TYPES:
            affected = _execute_record_action(
                course,
                user_id=user_id,
                proposal=proposal,
                record_type=RECORD_ACTION_TYPES[action_type],
            )
        elif action_type == "open_runtime_action":
            affected = [{
                "kind": "runtime_action",
                "task_ref": (runtime_before.get("continuation") or {}).get("primary_action") or {},
            }]
        else:  # pragma: no cover - protected by ACTION_TYPES
            raise ActionForbidden("action has no executor")
    except (ValueError, KeyError, RecordConflict, InvalidRecordTransition) as exc:
        repository.update_proposal(
            user_id,
            course_id,
            proposal_id,
            status="failed",
            changes={"failure_reason": str(exc)},
        )
        return _save_failure_receipt(
            repository,
            user_id=user_id,
            course_id=course_id,
            proposal=proposal,
            idempotency_key=idempotency_key,
            status="failed",
            reason=str(exc),
            runtime_revision_id=current_runtime,
        )

    runtime_after = build_learning_runtime(course, user_id=user_id, node_id=node_id or None)
    receipt = repository.save_receipt(user_id, course_id, {
        "conversation_id": proposal.get("conversation_id"),
        "proposal_id": proposal_id,
        "command_id": f"cmd_{hashlib.sha256(idempotency_key.encode('utf-8')).hexdigest()[:24]}",
        "idempotency_key": idempotency_key,
        "status": "succeeded",
        "action_type": action_type,
        "affected_refs": affected,
        "runtime_revision_before": current_runtime,
        "runtime_revision_after": runtime_after.get("runtime_revision_id"),
        "summary": _success_summary(action_type),
        "undo_capability": proposal.get("undo_capability") or "none",
    })
    repository.update_proposal(
        user_id,
        course_id,
        proposal_id,
        status="succeeded",
        changes={"executed_at": _now(), "receipt_id": receipt.get("receipt_id")},
    )
    return receipt


def reject_proposal(
    course: dict[str, Any],
    *,
    user_id: str,
    proposal_id: str,
    reason: str,
    repository: AITeacherRepository | None = None,
) -> dict[str, Any]:
    repository = repository or ai_teacher_repository
    course_id = str(course.get("course_id") or "")
    proposal = repository.get_proposal(user_id, course_id, proposal_id)
    if not proposal:
        raise KeyError(proposal_id)
    updated = repository.update_proposal(
        user_id,
        course_id,
        proposal_id,
        status="rejected",
        changes={"rejected_at": _now(), "failure_reason": reason},
    )
    mode = reason if reason in {"not_now", "irrelevant", "already_done", "never"} else "not_now"
    suppression = repository.save_suppression(user_id, course_id, {
        "suppression_key": str(proposal.get("dedupe_key") or proposal_id),
        "action_type": proposal.get("action_type"),
        "target_ref": proposal.get("target_ref") or {},
        "evidence_revision": proposal.get("runtime_revision_id"),
        "mode": mode,
        "proposal_id": proposal_id,
    })
    return {"proposal": updated, "suppression": suppression}


def undo_receipt(
    course: dict[str, Any],
    *,
    user_id: str,
    receipt_id: str,
    idempotency_key: str,
    repository: AITeacherRepository | None = None,
) -> dict[str, Any]:
    repository = repository or ai_teacher_repository
    course_id = str(course.get("course_id") or "")
    existing = repository.receipt_for_key(user_id, course_id, idempotency_key)
    if existing:
        return existing
    receipt = repository.get_receipt(user_id, course_id, receipt_id)
    if not receipt:
        raise KeyError(receipt_id)
    if receipt.get("undo_capability") != "archive_record":
        raise ActionForbidden("this action cannot be undone")
    affected = next((item for item in receipt.get("affected_refs") or [] if item.get("kind") == "learning_record"), None)
    if not affected:
        raise ActionForbidden("receipt has no reversible record")
    record_id = str(affected.get("record_id") or "")
    current = next((
        item for item in learning_record_repository.list(user_id, course_id)
        if item.get("record_id") == record_id
    ), None)
    if not current:
        raise KeyError(record_id)
    expected_revision = int(affected.get("revision") or 0)
    if int(current.get("revision") or 0) != expected_revision:
        raise ProposalStale("record changed after the original action")
    archived, _ = learning_record_repository.update(
        user_id,
        course_id,
        record_id,
        expected_revision=expected_revision,
        changes={"status": "archived"},
    )
    _record_record_event("learning_record_archived", archived, user_id=user_id, source="ai_teacher.undo")
    node_id = str(archived.get("node_id") or "")
    runtime = build_learning_runtime(course, user_id=user_id, node_id=node_id or None)
    return repository.save_receipt(user_id, course_id, {
        "conversation_id": receipt.get("conversation_id"),
        "proposal_id": receipt.get("proposal_id"),
        "command_id": f"cmd_{hashlib.sha256(idempotency_key.encode('utf-8')).hexdigest()[:24]}",
        "idempotency_key": idempotency_key,
        "status": "succeeded",
        "action_type": "undo_create_record",
        "affected_refs": [{"kind": "learning_record", "record_id": record_id, "revision": archived.get("revision")}],
        "runtime_revision_before": receipt.get("runtime_revision_after"),
        "runtime_revision_after": runtime.get("runtime_revision_id"),
        "summary": "已撤销并归档学习记录。",
        "undo_capability": "none",
        "undo_of_receipt_id": receipt_id,
    })


def build_trigger_candidate(
    course: dict[str, Any],
    *,
    user_id: str,
    node_id: str | None,
    repository: AITeacherRepository | None = None,
) -> dict[str, Any] | None:
    repository = repository or ai_teacher_repository
    course_id = str(course.get("course_id") or "")
    runtime = build_learning_runtime(course, user_id=user_id, node_id=node_id)
    action = (runtime.get("continuation") or {}).get("primary_action") or {}
    action_type = str(action.get("action_type") or "")
    if action_type not in STRONG_RUNTIME_ACTIONS:
        return None
    target_ref = action.get("task_ref") or {
        "node_id": (runtime.get("context") or {}).get("node_id"),
        "objective_revision_id": (runtime.get("context") or {}).get("objective_revision_id"),
    }
    evidence_revision = str(runtime.get("runtime_revision_id") or "")
    suppression_key = _dedupe_key("explain_runtime_action", target_ref, [], evidence_revision, "")
    for suppression in repository.list_suppressions(user_id, course_id):
        if suppression.get("suppression_key") != suppression_key:
            continue
        if suppression.get("mode") == "never" or suppression.get("evidence_revision") == evidence_revision:
            return None
    return {
        "trigger_id": f"ait_{suppression_key[:24]}",
        "trigger_type": "runtime_support",
        "scope_ref": target_ref,
        "evidence_refs": action.get("evidence_refs") or [],
        "confidence": 1.0,
        "severity": "high" if action_type in {"confirm_version_change", "resolve_diagnostic_support"} else "medium",
        "eligible_action": "explain_runtime_action",
        "runtime_action": action,
        "dedupe_key": suppression_key,
        "runtime_revision_id": evidence_revision,
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat(),
    }


def _execute_record_action(
    course: dict[str, Any],
    *,
    user_id: str,
    proposal: dict[str, Any],
    record_type: str,
) -> list[dict[str, Any]]:
    payload = dict(proposal.get("payload") or {})
    target_ref = proposal.get("target_ref") or {}
    node_id = str(payload.get("node_id") or target_ref.get("node_id") or "")
    if not node_id:
        raise ValueError("node_id is required for learning records")
    payload.update({
        "record_id": str(payload.get("record_id") or f"air_{proposal.get('proposal_id')}"),
        "record_type": record_type,
        "status": payload.get("status") or {
            "note": "active",
            "issue": "open",
            "review_task": "pending",
            "bookmark": "active",
        }[record_type],
        "node_id": node_id,
        "origin": "assistant_confirmed" if proposal.get("origin") != "user_command" else "user_command",
        "metadata": {
            **dict(payload.get("metadata") or {}),
            "ai_proposal_id": proposal.get("proposal_id"),
            "ai_conversation_id": proposal.get("conversation_id"),
        },
    })
    enriched = enrich_record_payload(course, payload)
    record, created = learning_record_repository.create_once(
        user_id,
        str(course.get("course_id") or ""),
        enriched,
    )
    if created:
        _record_record_event("learning_record_created", record, user_id=user_id, source="ai_teacher.action")
    return [{
        "kind": "learning_record",
        "record_id": record.get("record_id"),
        "record_type": record.get("record_type"),
        "revision": record.get("revision"),
        "node_id": record.get("node_id"),
        "record": project_record(record, course),
    }]


def _record_record_event(event_type: str, record: dict[str, Any], *, user_id: str, source: str) -> None:
    record_learning_event(
        event_type=event_type,
        actor="user",
        source=source,
        user_id=user_id,
        course_id=record.get("course_id"),
        course_version_id=record.get("course_version_id"),
        node_id=record.get("node_id"),
        node_name=record.get("node_name", ""),
        objective_id=record.get("objective_id"),
        objective_revision_id=record.get("objective_revision_id"),
        record_id=record.get("record_id"),
        record_type=record.get("record_type"),
        operation_id=f"record:{record.get('record_id')}:{record.get('revision')}",
        idempotency_key=f"{event_type}:{record.get('record_id')}:{record.get('revision')}",
        entity_type="learning_record",
        entity_id=record.get("record_id"),
        entity_revision=record.get("revision"),
        evidence={
            "quote": record.get("quote", ""),
            "anchor": record.get("anchor") or {},
            "origin": record.get("origin"),
        },
        result={"status": record.get("status"), "revision": record.get("revision")},
        metadata=record.get("metadata") or {},
    )


def _save_failure_receipt(
    repository: AITeacherRepository,
    *,
    user_id: str,
    course_id: str,
    proposal: dict[str, Any],
    idempotency_key: str,
    status: str,
    reason: str,
    runtime_revision_id: str,
) -> dict[str, Any]:
    return repository.save_receipt(user_id, course_id, {
        "conversation_id": proposal.get("conversation_id"),
        "proposal_id": proposal.get("proposal_id"),
        "command_id": f"cmd_{hashlib.sha256(idempotency_key.encode('utf-8')).hexdigest()[:24]}",
        "idempotency_key": idempotency_key,
        "status": status,
        "action_type": proposal.get("action_type"),
        "affected_refs": [],
        "runtime_revision_after": runtime_revision_id,
        "summary": reason,
        "failure_reason": reason,
        "undo_capability": "none",
    })


def _require_not_expired(proposal: dict[str, Any]) -> None:
    expires_at = str(proposal.get("expires_at") or "")
    if not expires_at:
        return
    try:
        expires = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except ValueError:
        return
    if expires < datetime.now(timezone.utc):
        raise ProposalStale("proposal expired")


def _dedupe_key(
    action_type: str,
    target_ref: dict[str, Any],
    evidence_refs: list[dict[str, Any]],
    runtime_revision_id: str,
    message_id: str,
) -> str:
    payload = json.dumps(
        {
            "action_type": action_type,
            "target_ref": target_ref,
            "evidence_refs": evidence_refs,
            "runtime_revision_id": runtime_revision_id,
            "message_id": message_id,
        },
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _payload_preview(action_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": str(payload.get("title") or "")[:200],
        "content": str(payload.get("content") or payload.get("quote") or "")[:500],
        "due_at": payload.get("due_at"),
        "action_type": action_type,
    }


def _expected_effect(action_type: str) -> str:
    labels = {
        "create_note": "创建一条学习笔记",
        "create_issue": "创建一条待解决问题",
        "create_review_task": "创建一条复习任务",
        "create_bookmark": "创建一个课程书签",
        "open_runtime_action": "打开当前统一学习动作",
    }
    return labels[action_type]


def _success_summary(action_type: str) -> str:
    labels = {
        "create_note": "已保存为笔记。",
        "create_issue": "已标记为待解决问题。",
        "create_review_task": "已创建复习任务。",
        "create_bookmark": "已创建书签。",
        "open_runtime_action": "已准备打开当前学习任务。",
    }
    return labels[action_type]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "ACTION_TYPES",
    "ActionForbidden",
    "ProposalStale",
    "build_trigger_candidate",
    "execute_proposal",
    "propose_action",
    "reject_proposal",
    "undo_receipt",
]
