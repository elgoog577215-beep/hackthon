"""Whitelisted knowledge commands with atomic course/knowledge coordination.

The course knowledge base is the course's底座, and it has to evolve without
regenerating the whole course every time. That needs two things this module
provides and the existing rebuild path does not:

1. **A whitelist.** AI may not write knowledge freely. Every change arrives as a
   named command, is validated against the knowledge quality gate, and stays a
   *candidate* until the user confirms it. `course_knowledge_rebuild` writes
   through `update_metadata`, which produces no receipt and no revision event —
   fine for a full recompile, not enough for a targeted edit anyone can audit.
2. **Atomic coordination.** A knowledge revision and the course revision it
   depends on must land together or not at all. This builds on the repository's
   existing `apply_metadata_command`: one per-course lock, one idempotency key,
   one receipt. If the knowledge payload fails validation the command raises
   *before* any write, so the course keeps its previous knowledge base; if the
   course document moved underneath, the expected-revision check rejects the
   command rather than committing knowledge against a stale course.

What this module deliberately does not do: it never becomes a second knowledge
store. The knowledge base lives where it always lived, on the course envelope,
written by the course repository. This only gates *how* it changes.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from course_knowledge_base import (
    COURSE_KNOWLEDGE_BASE_SCHEMA,
    validate_course_knowledge_base,
)
from course_knowledge_impact import build_knowledge_impact_report
from course_knowledge_revisions import knowledge_revision_event
from course_repository import CourseDocumentConflict, CourseDocumentRepository
from course_versioning import stable_hash

KNOWLEDGE_CANDIDATE_SCHEMA = "course_knowledge_candidate_v1"
KNOWLEDGE_RECEIPT_SCHEMA = "course_knowledge_receipt_v1"

# Whitelisted knowledge operations. An operation outside this set is refused
# before anything is read, so a new write path cannot appear by accident.
KNOWLEDGE_COMMANDS = {
    "add_knowledge_point",
    "revise_knowledge_point",
    "split_knowledge_point",
    "merge_knowledge_points",
    "rename_knowledge_point",
    "retire_knowledge_point",
    "adjust_relation",
    "adjust_binding",
}

# Operations that move stable identity and therefore require an explicit
# old -> new mapping. Without it, historical practice attempts and learning
# events keep references that resolve to nothing.
_IDENTITY_MOVING_COMMANDS = {
    "split_knowledge_point",
    "merge_knowledge_points",
    "retire_knowledge_point",
}


class KnowledgeCommandRejected(RuntimeError):
    """A knowledge command failed a gate before any state changed."""

    def __init__(self, code: str, message: str, *, detail: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(value: Any) -> str:
    return str(value or "").strip()


def build_knowledge_candidate(
    course_data: dict[str, Any],
    *,
    operation: str,
    proposed_knowledge_base: dict[str, Any],
    reason: str,
    identity_map: dict[str, Any] | None = None,
    actor: str = "ai",
) -> dict[str, Any]:
    """Validate a proposed knowledge base and describe it as a candidate.

    Pure analysis: the active knowledge base is untouched until the candidate is
    confirmed. The returned payload pins the base revision it was computed
    against, which is what lets `confirm_knowledge_candidate` detect that the
    course moved in the meantime instead of applying a stale edit.
    """
    if operation not in KNOWLEDGE_COMMANDS:
        raise KnowledgeCommandRejected(
            "knowledge_command_not_whitelisted",
            f"知识命令 {operation} 不在白名单中",
            detail=sorted(KNOWLEDGE_COMMANDS),
        )
    if not _text(reason):
        raise KnowledgeCommandRejected(
            "knowledge_command_missing_reason",
            "知识命令必须说明修改理由，否则无法审阅",
        )
    if not isinstance(proposed_knowledge_base, dict):
        raise KnowledgeCommandRejected(
            "knowledge_candidate_invalid_payload",
            "知识候选负载必须是知识库对象",
        )
    if proposed_knowledge_base.get("schema_version") != COURSE_KNOWLEDGE_BASE_SCHEMA:
        raise KnowledgeCommandRejected(
            "knowledge_candidate_invalid_schema",
            "知识候选不是当前知识库格式",
        )

    active = course_data.get("course_knowledge_base") or {}
    mapping = dict(identity_map or {})
    if operation in _IDENTITY_MOVING_COMMANDS and not mapping:
        raise KnowledgeCommandRejected(
            "knowledge_identity_map_required",
            f"{operation} 会移动稳定知识 ID，必须提供旧新 ID 映射",
        )

    quality = validate_course_knowledge_base(
        proposed_knowledge_base, course_data=course_data,
    )
    event = knowledge_revision_event(
        active,
        proposed_knowledge_base,
        operation=operation,
        identity_map=mapping,
    )
    impact = build_knowledge_impact_report(
        event,
        course_data=course_data,
        knowledge_base=proposed_knowledge_base,
    )

    candidate = {
        "schema_version": KNOWLEDGE_CANDIDATE_SCHEMA,
        "course_id": _text(course_data.get("course_id")),
        "operation": operation,
        "reason": _text(reason),
        "actor": _text(actor) or "ai",
        # Base revisions this candidate was computed against. Confirmation
        # re-checks both; drift means recompute, not apply.
        "base_knowledge_revision_id": _text(active.get("revision_id")),
        "base_document_revision": _text(course_data.get("course_document_revision")),
        "identity_map": event.identity_map,
        "quality_report": quality,
        "revision_event": event.model_dump(mode="json"),
        "impact_report": impact,
        "identity_preserved": event.identity_preserved,
        # A candidate that fails the quality gate or breaks identity is still
        # returned — the reviewer needs to see why it was refused — but it is
        # explicitly not confirmable.
        "confirmable": bool(quality.get("passed")) and event.identity_preserved,
        "blocking_issues": quality.get("blocking_issues") or [],
        "created_at": _now(),
    }
    candidate["candidate_id"] = stable_hash(
        {
            "course_id": candidate["course_id"],
            "operation": operation,
            "base": candidate["base_knowledge_revision_id"],
            "target": _text(proposed_knowledge_base.get("revision_id")),
            "identity_map": candidate["identity_map"],
        },
        prefix="ckc_",
    )
    return candidate


class CourseKnowledgeCommandService:
    """Commits knowledge revisions atomically with the course they belong to."""

    def __init__(self, repository: CourseDocumentRepository) -> None:
        self.repository = repository

    async def confirm_knowledge_candidate(
        self,
        course_id: str,
        *,
        command_id: str,
        candidate: dict[str, Any],
        proposed_knowledge_base: dict[str, Any],
        actor: str = "user",
    ) -> dict[str, Any]:
        """Apply a confirmed candidate, or apply nothing at all.

        Every rejection below happens before `apply_metadata_command` is
        entered, so a refused command leaves the previous knowledge base in
        place. Once inside, the repository's per-course lock makes the knowledge
        write and the course revision vector update a single commit — they
        cannot half-land.
        """
        if not _text(command_id):
            raise KnowledgeCommandRejected(
                "knowledge_command_missing_id",
                "知识命令必须携带 command_id 才能保证幂等",
            )
        operation = _text(candidate.get("operation"))
        if operation not in KNOWLEDGE_COMMANDS:
            raise KnowledgeCommandRejected(
                "knowledge_command_not_whitelisted",
                f"知识命令 {operation} 不在白名单中",
            )
        if not candidate.get("confirmable"):
            raise KnowledgeCommandRejected(
                "knowledge_candidate_not_confirmable",
                "知识候选未通过质量门或破坏了稳定身份，不能确认",
                detail=candidate.get("blocking_issues"),
            )

        # Replaying the same command_id must return the original receipt rather
        # than re-applying: the caller may be a retry after a lost response.
        existing = self.repository.receipt_for_command(course_id, command_id)
        if existing:
            return existing

        current = self.repository.load_course_view(course_id)
        active = current.get("course_knowledge_base") or {}
        if _text(active.get("revision_id")) != _text(candidate.get("base_knowledge_revision_id")):
            raise KnowledgeCommandRejected(
                "knowledge_base_revision_changed",
                "知识库在确认前已发生变化，请基于当前修订重新计算候选",
            )

        expected_document_revision = _text(current.get("course_document_revision"))
        candidate_document_revision = _text(candidate.get("base_document_revision"))
        if candidate_document_revision and candidate_document_revision != expected_document_revision:
            raise KnowledgeCommandRejected(
                "course_document_revision_changed",
                "课程正文在确认前已发生变化，请基于当前修订重新计算候选",
            )

        payload = deepcopy(proposed_knowledge_base)

        def mutation(raw: dict[str, Any]) -> None:
            raw["course_knowledge_base"] = payload
            raw["course_knowledge_quality_report"] = candidate.get("quality_report")
            history = list(raw.get("course_knowledge_revision_log") or [])
            history.append({
                "schema_version": KNOWLEDGE_RECEIPT_SCHEMA,
                "command_id": command_id,
                "candidate_id": _text(candidate.get("candidate_id")),
                "operation": operation,
                "reason": _text(candidate.get("reason")),
                "actor": _text(actor) or "user",
                "previous_revision_id": _text(active.get("revision_id")),
                "revision_id": _text(payload.get("revision_id")),
                "identity_map": candidate.get("identity_map") or {},
                "changed_source_keys": (
                    candidate.get("revision_event") or {}
                ).get("changed_source_keys") or [],
                "committed_at": _now(),
            })
            # Bounded like the course operation log: this is an audit trail for
            # recent evolution, not an event store.
            raw["course_knowledge_revision_log"] = history[-200:]

        try:
            receipt = await self.repository.apply_metadata_command(
                course_id,
                expected_document_revision=expected_document_revision,
                operation={
                    "command_id": command_id,
                    "operation": f"knowledge:{operation}",
                    "reason": _text(candidate.get("reason")),
                    "actor": _text(actor) or "user",
                },
                mutation=mutation,
            )
        except CourseDocumentConflict as error:
            # The repository refused mid-flight; nothing was saved.
            raise KnowledgeCommandRejected(
                "course_revision_conflict",
                f"课程修订冲突，知识修订未生效：{error}",
            ) from error

        receipt = deepcopy(receipt)
        receipt["knowledge_revision_id"] = _text(payload.get("revision_id"))
        receipt["previous_knowledge_revision_id"] = _text(active.get("revision_id"))
        receipt["candidate_id"] = _text(candidate.get("candidate_id"))
        receipt["identity_map"] = candidate.get("identity_map") or {}
        return receipt

    def knowledge_revision_log(self, course_id: str) -> list[dict[str, Any]]:
        """Recent confirmed knowledge revisions, oldest first."""
        current = self.repository.load_course_view(course_id)
        return list(current.get("course_knowledge_revision_log") or [])


__all__ = [
    "KNOWLEDGE_CANDIDATE_SCHEMA",
    "KNOWLEDGE_COMMANDS",
    "KNOWLEDGE_RECEIPT_SCHEMA",
    "CourseKnowledgeCommandService",
    "KnowledgeCommandRejected",
    "build_knowledge_candidate",
]
