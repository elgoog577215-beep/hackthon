"""Targeted single-point knowledge edits for the teacher UI.

The command layer in `course_knowledge_commands` takes a whole proposed
knowledge base. That is the right contract for a domain command — it makes the
proposal explicit and reviewable — but it is the wrong thing to put on the wire.
Real courses measured in this repo carry knowledge bases inside ~10 MB course
envelopes; making a browser download one, mutate a single field, and POST it
back would be slow, would burn bandwidth on every keystroke-sized edit, and
would let a stale client overwrite fields it never intended to touch.

So the UI sends a *description* of the edit — which knowledge point, which
field, the new value — and this module rebuilds the proposed knowledge base
server-side from the current active one. Two consequences worth stating:

1. The edit is deterministic. The same spec against the same base revision
   always yields the same proposal, which is what lets confirm recompute the
   proposal instead of trusting a client-supplied payload.
2. The client can only change what the spec allows. A targeted edit cannot
   silently rewrite stable IDs, relations or bindings, because it never gets to
   hand over a full knowledge base at all.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from course_knowledge_commands import (
    KnowledgeCommandRejected,
    build_knowledge_candidate,
)
from course_versioning import stable_hash

# Field each operation is allowed to touch. Anything not listed here is not
# reachable from the targeted-edit path, by construction rather than by check.
POINT_EDIT_OPERATIONS = {
    "revise_knowledge_point": "statement",
    "rename_knowledge_point": "name",
}

MAX_VALUE_LENGTH = 2000


def _text(value: Any) -> str:
    return str(value or "").strip()


def apply_point_edit(
    knowledge_base: dict[str, Any],
    *,
    knowledge_id: str,
    operation: str,
    value: str,
) -> dict[str, Any]:
    """Return a copy of the knowledge base with one field of one point changed.

    Only the target point's own revision is refreshed. Leaving every other
    record's revision untouched is what makes the downstream impact analysis
    report a localized blast radius instead of "the whole base moved".
    """
    field = POINT_EDIT_OPERATIONS.get(operation)
    if not field:
        raise KnowledgeCommandRejected(
            "knowledge_point_edit_unsupported",
            f"定向编辑不支持操作 {operation}",
            detail=sorted(POINT_EDIT_OPERATIONS),
        )
    new_value = _text(value)
    if not new_value:
        raise KnowledgeCommandRejected(
            "knowledge_point_edit_empty_value",
            "编辑内容不能为空",
        )
    if len(new_value) > MAX_VALUE_LENGTH:
        raise KnowledgeCommandRejected(
            "knowledge_point_edit_value_too_long",
            f"编辑内容超过 {MAX_VALUE_LENGTH} 字上限",
        )

    proposed = deepcopy(knowledge_base)
    target = next(
        (
            item
            for item in proposed.get("knowledge_points") or []
            if isinstance(item, dict) and _text(item.get("knowledge_id")) == _text(knowledge_id)
        ),
        None,
    )
    if target is None:
        raise KnowledgeCommandRejected(
            "knowledge_point_not_found",
            "知识点不在当前知识库中，请刷新后重试",
        )
    if _text(target.get(field)) == new_value:
        raise KnowledgeCommandRejected(
            "knowledge_point_edit_no_change",
            "编辑内容与当前内容相同，无需修订",
        )

    target[field] = new_value
    target["revision_id"] = stable_hash(
        {key: item for key, item in target.items() if key != "revision_id"},
        prefix="ckpr_",
    )
    proposed["revision_id"] = stable_hash(
        {
            "base": _text(knowledge_base.get("revision_id")),
            "knowledge_id": _text(knowledge_id),
            "field": field,
            "value": new_value,
        },
        prefix="ckbr_",
    )
    return proposed


def build_point_edit_candidate(
    course_data: dict[str, Any],
    *,
    knowledge_id: str,
    operation: str,
    value: str,
    reason: str,
    actor: str = "user",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build (candidate, proposed_knowledge_base) for one targeted point edit."""
    active = course_data.get("course_knowledge_base") or {}
    if not active.get("knowledge_points"):
        raise KnowledgeCommandRejected(
            "knowledge_base_unavailable",
            "当前课程还没有可维护的知识库",
        )
    proposed = apply_point_edit(
        active, knowledge_id=knowledge_id, operation=operation, value=value,
    )
    candidate = build_knowledge_candidate(
        course_data,
        operation=operation,
        proposed_knowledge_base=proposed,
        reason=reason,
        actor=actor,
    )
    return candidate, proposed


__all__ = [
    "MAX_VALUE_LENGTH",
    "POINT_EDIT_OPERATIONS",
    "apply_point_edit",
    "build_point_edit_candidate",
]
