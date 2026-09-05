"""Relocate a pending knowledge candidate onto a newer base revision.

A candidate pins the knowledge revision it was computed against. When the base
moves before the teacher confirms, the command service refuses it — correct,
but blunt: a candidate for *this* knowledge point is thrown away because
somebody edited *another* one. Teachers experience that as "my work vanished
because a colleague saved first".

Relocation asks a narrower question: is the thing this candidate targets still
there, and still saying what the candidate assumed? If yes, the candidate can
be recomputed against the new base and re-offered. If the target moved in a way
the candidate's intent no longer survives — it was split, merged away, retired,
or someone else already changed the very field this candidate edits — that is a
real conflict and must be reported, not silently re-applied.

The distinction this module exists to preserve:

- **relocated**: the target is intact and the edited field is untouched. Safe to
  recompute; the teacher re-confirms against fresh impact.
- **conflict**: the target or the field moved. The teacher must decide; we say
  exactly which case it is instead of a generic "please retry".

Nothing here writes. Relocation produces a new candidate that still requires
explicit confirmation — a relocated candidate is not an applied one.
"""

from __future__ import annotations

from typing import Any

from course_knowledge_point_edits import (
    POINT_EDIT_OPERATIONS,
    build_point_edit_candidate,
)

RELOCATION_SCHEMA = "course_knowledge_candidate_relocation_v1"

RELOCATION_OUTCOMES = ("unchanged", "relocated", "conflict")

# Why a candidate could not be carried onto the new base. Each maps to a
# different teacher action, which is why they are not collapsed into one code.
CONFLICT_REASONS = {
    "target_missing": "候选针对的知识点已不存在（可能被拆分、合并或退役）",
    "target_field_changed": "候选要修改的字段已被他人改动",
    "target_identity_moved": "候选针对的知识点身份已迁移",
    "operation_unsupported": "该候选的操作不支持重定位",
    "base_unavailable": "当前课程没有可用的知识库",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _point(knowledge_base: dict[str, Any] | None, knowledge_id: str) -> dict[str, Any] | None:
    for item in (knowledge_base or {}).get("knowledge_points") or []:
        if isinstance(item, dict) and _text(item.get("knowledge_id")) == _text(knowledge_id):
            return item
    return None


def _conflict(reason: str, **extra: Any) -> dict[str, Any]:
    return {
        "schema_version": RELOCATION_SCHEMA,
        "outcome": "conflict",
        "reason": reason,
        "message": CONFLICT_REASONS.get(reason, reason),
        "candidate": None,
        **extra,
    }


def _mapped_successors(course_data: dict[str, Any], knowledge_id: str) -> list[str]:
    """Resolve a retired knowledge id to its successors via the revision log.

    Confirmed knowledge commands persist their ``identity_map`` into
    ``course_knowledge_revision_log``. Following it lets a stale candidate say
    "this point became these two" instead of the useless "it is gone". The log
    is walked newest-first so a chain of migrations reports the most recent hop.
    """
    wanted = _text(knowledge_id)
    for entry in reversed(course_data.get("course_knowledge_revision_log") or []):
        if not isinstance(entry, dict):
            continue
        mapping = entry.get("identity_map")
        if not isinstance(mapping, dict):
            continue
        successors = mapping.get(wanted)
        if successors:
            values = successors if isinstance(successors, (list, tuple)) else [successors]
            resolved = [_text(item) for item in values if _text(item)]
            if resolved:
                return sorted(dict.fromkeys(resolved))
    return []


def _touched_by_later_command(
    course_data: dict[str, Any],
    knowledge_id: str,
    operation: str,
) -> bool:
    """Did a confirmed command already edit this point the same way?

    Used only when the caller could not supply the previous knowledge base. The
    revision log records each confirmed command's ``changed_source_keys``, which
    carry ``point:<id>`` entries, so we can tell that *someone* edited this very
    point without being able to diff the values. Refusing on that signal is the
    conservative choice: relocating would overwrite an edit we cannot inspect.
    """
    wanted = f"point:{_text(knowledge_id)}"
    for entry in course_data.get("course_knowledge_revision_log") or []:
        if not isinstance(entry, dict):
            continue
        if _text(entry.get("operation")) != _text(operation):
            continue
        keys = entry.get("changed_source_keys")
        if isinstance(keys, list) and wanted in {_text(item) for item in keys}:
            return True
    return False


def relocate_point_edit_candidate(
    course_data: dict[str, Any],
    *,
    knowledge_id: str,
    operation: str,
    value: str,
    reason: str,
    base_knowledge_revision_id: str,
    previous_knowledge_base: dict[str, Any] | None = None,
    actor: str = "user",
) -> dict[str, Any]:
    """Re-anchor a pending point-edit candidate onto the current knowledge base.

    ``previous_knowledge_base`` is the revision the candidate was computed
    against. It is optional: without it we can still detect a missing target,
    but we cannot tell "nobody touched this field" from "someone changed it to
    something else", so the result is conservative.
    """
    active = course_data.get("course_knowledge_base") or {}
    if not active.get("knowledge_points"):
        return _conflict("base_unavailable")

    field = POINT_EDIT_OPERATIONS.get(operation)
    if not field:
        return _conflict("operation_unsupported", operation=operation)

    current_revision = _text(active.get("revision_id"))
    if current_revision == _text(base_knowledge_revision_id):
        # Base never moved; the candidate is still valid as computed.
        candidate, _ = build_point_edit_candidate(
            course_data,
            knowledge_id=knowledge_id,
            operation=operation,
            value=value,
            reason=reason,
            actor=actor,
        )
        return {
            "schema_version": RELOCATION_SCHEMA,
            "outcome": "unchanged",
            "reason": "base_revision_unchanged",
            "message": "知识库未发生变化，候选仍然有效",
            "candidate": candidate,
            "base_knowledge_revision_id": current_revision,
        }

    target = _point(active, knowledge_id)
    if target is None:
        # The stable id is gone. Distinguish "split/merged with a recorded
        # mapping" from "plain disappearance": the confirmed knowledge commands
        # persist their identity_map into course_knowledge_revision_log, so a
        # migration can be resolved to its successors instead of dead-ending.
        detail: dict[str, Any] = {"knowledge_id": _text(knowledge_id)}
        successors = _mapped_successors(course_data, knowledge_id)
        if successors:
            return _conflict(
                "target_identity_moved",
                successor_knowledge_ids=successors,
                **detail,
            )
        return _conflict("target_missing", **detail)

    before = None
    if isinstance(previous_knowledge_base, dict):
        before = _point(previous_knowledge_base, knowledge_id)
    if before is not None and _text(before.get(field)) != _text(target.get(field)):
        # Someone edited the same field. Re-applying would silently discard
        # their change, so the teacher has to reconcile the two.
        return _conflict(
            "target_field_changed",
            knowledge_id=_text(knowledge_id),
            field=field,
            previous_value=_text(before.get(field)),
            current_value=_text(target.get(field)),
        )
    if before is None and _touched_by_later_command(course_data, knowledge_id, operation):
        # Callers that only kept the base revision id (the HTTP path) cannot
        # hand us the old payload. The revision log still records which point
        # each confirmed command touched, which is enough to refuse rather than
        # overwrite work we cannot inspect.
        return _conflict(
            "target_field_changed",
            knowledge_id=_text(knowledge_id),
            field=field,
            current_value=_text(target.get(field)),
        )

    # Target intact and the edited field untouched: recompute against the new
    # base so the teacher re-confirms with fresh impact rather than stale.
    candidate, _ = build_point_edit_candidate(
        course_data,
        knowledge_id=knowledge_id,
        operation=operation,
        value=value,
        reason=reason,
        actor=actor,
    )
    return {
        "schema_version": RELOCATION_SCHEMA,
        "outcome": "relocated",
        "reason": "recomputed_on_new_base",
        "message": "知识库已变化，候选已按当前修订重新计算，请再次确认",
        "candidate": candidate,
        "previous_base_knowledge_revision_id": _text(base_knowledge_revision_id),
        "base_knowledge_revision_id": _text(active.get("revision_id")),
    }


def relocation_snapshot(result: dict[str, Any]) -> dict[str, Any]:
    """Compact, stable projection for regression snapshots."""
    candidate = result.get("candidate") or {}
    return {
        "outcome": _text(result.get("outcome")),
        "reason": _text(result.get("reason")),
        "confirmable": bool(candidate.get("confirmable")) if candidate else False,
    }


__all__ = [
    "CONFLICT_REASONS",
    "RELOCATION_OUTCOMES",
    "RELOCATION_SCHEMA",
    "relocate_point_edit_candidate",
    "relocation_snapshot",
]
