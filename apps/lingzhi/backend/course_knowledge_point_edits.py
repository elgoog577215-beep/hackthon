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


def resolve_knowledge_id(
    knowledge_base: dict[str, Any],
    knowledge_id: str,
    *,
    course_data: dict[str, Any] | None = None,
) -> str:
    """Map an id the client is holding onto the stored knowledge base's id.

    The knowledge tree the teacher clicks is a *view*. When a course's stored
    ``source_course_fingerprint`` no longer matches its content — which is the
    case for every real course in this repo, because the fingerprint covers
    fields that later pipelines legitimately rewrite —
    ``apply_persisted_course_knowledge_base`` refuses the stored base and the
    view is recompiled from the blueprint. Recompilation re-derives ids from
    the section/name, so the view shows ``ckp_871…`` while the stored base
    holds ``ckp_fcf…`` for the very same knowledge point.

    Failing with "知识点不在当前知识库中" in that situation is technically true
    and practically useless: the teacher is looking straight at the point. So
    fall back to resolving by course-local identity (section + normalized
    name), which is what both ids were derived from in the first place. If that
    cannot be resolved either, the caller still gets the not-found error.

    Deliberately *not* rewriting the stored fingerprint here: that would be a
    silent repair of someone else's data on a read path.
    """
    wanted = _text(knowledge_id)
    if not wanted:
        return ""
    points = knowledge_base.get("knowledge_points") or []
    if any(_text(item.get("knowledge_id")) == wanted for item in points if isinstance(item, dict)):
        return wanted

    view = _recompiled_view(course_data)
    source = next(
        (
            item
            for item in view.get("knowledge_points") or []
            if isinstance(item, dict) and _text(item.get("knowledge_id")) == wanted
        ),
        None,
    )
    if source is None:
        return ""
    return _match_by_identity(points, source)


def _recompiled_view(course_data: dict[str, Any] | None) -> dict[str, Any]:
    """The knowledge base the client's view was compiled from, if we can rebuild it."""
    if not isinstance(course_data, dict):
        return {}
    try:
        from copy import deepcopy

        from course_knowledge_base import compile_course_knowledge_base

        working = deepcopy(course_data)
        working.pop("course_knowledge_base", None)
        return compile_course_knowledge_base(working)
    except Exception:  # noqa: BLE001 - a failed fallback must not break the edit path
        return {}


def _match_by_identity(
    points: list[Any],
    source: dict[str, Any],
) -> str:
    """Find the stored point that means the same thing as `source`."""
    name = _normalized(source.get("name"))
    sections = {_text(item) for item in source.get("section_refs") or []}
    aliases = {_normalized(item) for item in source.get("aliases") or []}
    aliases.discard("")

    for item in points:
        if not isinstance(item, dict):
            continue
        candidate_names = {_normalized(item.get("name"))}
        candidate_names.update(_normalized(alias) for alias in item.get("aliases") or [])
        if name and name not in candidate_names and not (aliases & candidate_names):
            continue
        item_sections = {_text(ref) for ref in item.get("section_refs") or []}
        # Same name in the same section is the identity both ids were built on.
        if not sections or not item_sections or (sections & item_sections):
            return _text(item.get("knowledge_id"))
    return ""


def _normalized(value: Any) -> str:
    import re

    return re.sub(r"[^0-9a-z一-鿿]+", "", str(value or "").lower())


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

    if field == "name":
        # A rename must keep the old name resolvable. Teaching-plan edit paths
        # address knowledge by name (`sections/<id>/knowledge/<name>/<field>`)
        # and the plan projection binds plan points to knowledge IDs by name,
        # falling back to aliases. Dropping the old name would silently break
        # both — the knowledge_id survives, but every name-keyed reference to
        # it stops resolving. Retiring a name is a migration, not a side effect
        # of typing a new one.
        aliases = [_text(item) for item in target.get("aliases") or [] if _text(item)]
        old_name = _text(target.get(field))
        if old_name and old_name not in aliases:
            aliases.append(old_name)
        target["aliases"] = aliases

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
    resolved = resolve_knowledge_id(active, knowledge_id, course_data=course_data)
    proposed = apply_point_edit(
        active, knowledge_id=resolved or knowledge_id, operation=operation, value=value,
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
    "resolve_knowledge_id",
]
