"""Multi-scope change proposals for canonical course documents.

Generalizes the single-block candidate-first workflow in
`block_regeneration.py` to arbitrary scopes (block / section / sections /
chapters / book) and to change sets containing multiple items that can each
be accepted or rejected independently. `block_regeneration.py` is left
untouched and continues to work as a standalone single-block special case.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import threading
from typing import Any, Callable, Literal
import uuid

from course_commands import CourseCommandService
from course_document import stable_hash
from course_repository import CourseDocumentConflict, CourseDocumentRepository


CHANGE_PROPOSAL_SCHEMA = "change_proposal_v1"
_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]+$")

ChangeProposalScope = Literal["block", "section", "sections", "chapters", "book"]
ChangeProposalSource = Literal["manual", "evidence", "kb_link"]
ChangeProposalStatus = Literal["pending", "resolved"]
ChangeProposalItemStatus = Literal["pending", "applied", "rejected"]
# Only allowed change: added to distinguish an item whose `block_id` actually
# names a course content block (the pre-existing, only supported meaning) from
# one where `block_id` names a knowledge-graph node id (used by the course<->KB
# linkage feature in course_knowledge_map.py / subject_knowledge.py). Defaults
# to "course_block" so every pre-existing caller/proposal is unaffected.
ChangeProposalTargetKind = Literal["course_block", "kg_node"]
_TARGET_KINDS = {"course_block", "kg_node"}


class ChangeProposalNotFound(KeyError):
    pass


class ChangeProposalConflict(RuntimeError):
    def __init__(self, message: str, *, proposal: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.proposal = deepcopy(proposal) if proposal else None


class ChangeProposalRepository:
    """JSON-file, atomic-write repository, mirroring BlockRegenerationCandidateRepository."""

    def __init__(self, root_dir: str | Path | None = None) -> None:
        from storage import DATA_DIR

        self.root_dir = Path(root_dir or Path(DATA_DIR) / "change_proposals")
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, threading.RLock] = {}
        self._locks_guard = threading.Lock()

    @staticmethod
    def proposal_id_for(course_id: str, request_id: str) -> str:
        if not course_id or not request_id:
            raise ValueError("Course and request identifiers are required")
        return stable_hash({"course_id": course_id, "request_id": request_id}, prefix="cps_")

    def load(self, proposal_id: str) -> dict[str, Any]:
        self._validate_id(proposal_id)
        path = self._path(proposal_id)
        if not path.exists():
            raise ChangeProposalNotFound(proposal_id)
        return self._read(path)

    def load_optional(self, proposal_id: str) -> dict[str, Any] | None:
        try:
            return self.load(proposal_id)
        except ChangeProposalNotFound:
            return None

    def list_for_course(self, course_id: str, *, status: str | None = None) -> list[dict[str, Any]]:
        matches: list[dict[str, Any]] = []
        for path in self.root_dir.glob("cps_*.json"):
            proposal = self._read(path)
            if proposal.get("course_id") != course_id:
                continue
            if status is not None and proposal.get("status") != status:
                continue
            matches.append(proposal)
        matches.sort(key=lambda item: str(item.get("created_at") or ""))
        return matches

    def create(self, proposal: dict[str, Any]) -> dict[str, Any]:
        value, _created = self.create_once(proposal)
        return value

    def create_once(self, proposal: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        proposal_id = str(proposal.get("proposal_id") or "")
        self._validate_id(proposal_id)
        with self._lock(proposal_id):
            existing = self.load_optional(proposal_id)
            if existing:
                return existing, False
            value = deepcopy(proposal)
            value["schema_version"] = CHANGE_PROPOSAL_SCHEMA
            self._atomic_write(self._path(proposal_id), value)
            return deepcopy(value), True

    def update(
        self,
        proposal_id: str,
        updater: Callable[[dict[str, Any]], dict[str, Any] | None],
    ) -> dict[str, Any]:
        self._validate_id(proposal_id)
        with self._lock(proposal_id):
            current = self.load(proposal_id)
            updated = updater(deepcopy(current))
            value = current if updated is None else updated
            if not isinstance(value, dict):
                raise ChangeProposalConflict("Proposal updater returned invalid data")
            self._atomic_write(self._path(proposal_id), value)
            return deepcopy(value)

    def update_if(
        self,
        proposal_id: str,
        predicate: Callable[[dict[str, Any]], bool],
        updater: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> tuple[dict[str, Any], bool]:
        self._validate_id(proposal_id)
        with self._lock(proposal_id):
            current = self.load(proposal_id)
            if not predicate(deepcopy(current)):
                return current, False
            value = updater(deepcopy(current))
            if not isinstance(value, dict):
                raise ChangeProposalConflict("Proposal updater returned invalid data")
            self._atomic_write(self._path(proposal_id), value)
            return deepcopy(value), True

    def _path(self, proposal_id: str) -> Path:
        return self.root_dir / f"{proposal_id}.json"

    def _lock(self, proposal_id: str) -> threading.RLock:
        with self._locks_guard:
            return self._locks.setdefault(proposal_id, threading.RLock())

    @staticmethod
    def _validate_id(value: str) -> None:
        if not value or not _SAFE_ID.match(value):
            raise ValueError("Invalid change proposal identifier")

    @staticmethod
    def _read(path: Path) -> dict[str, Any]:
        with path.open(encoding="utf-8") as handle:
            value = json.load(handle)
        if not isinstance(value, dict):
            raise ChangeProposalConflict("Change proposal must contain an object")
        return value

    @staticmethod
    def _atomic_write(path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        try:
            with temp.open("w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, path)
        finally:
            if temp.exists():
                temp.unlink()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_proposal(
    repository: ChangeProposalRepository,
    course_id: str,
    *,
    request_id: str,
    scope: ChangeProposalScope,
    target_block_ids: list[str],
    items: list[dict[str, Any]],
    source: ChangeProposalSource = "manual",
    generation_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a ChangeProposal. Idempotent per (course_id, request_id).

    Each entry in `items` MUST already contain: `block_id`, `before`, `after`,
    `reason`. `item_id` is assigned here if missing. `target_kind` is optional
    and defaults to "course_block"; pass "kg_node" when `block_id` actually
    names a knowledge-graph node id rather than a course content block.
    """
    if not target_block_ids:
        raise ValueError("target_block_ids must explicitly list every affected node")
    if not items:
        raise ValueError("A change proposal requires at least one item")

    proposal_id = repository.proposal_id_for(course_id, request_id)
    now = _now()
    normalized_items: list[dict[str, Any]] = []
    for raw_item in items:
        block_id = str(raw_item.get("block_id") or "")
        if not block_id:
            raise ValueError("Each item requires a block_id")
        if block_id not in target_block_ids:
            raise ValueError(
                f"Item block_id {block_id!r} is not listed in target_block_ids"
            )
        target_kind = str(raw_item.get("target_kind") or "course_block")
        if target_kind not in _TARGET_KINDS:
            raise ValueError(f"Invalid target_kind {target_kind!r}")
        normalized_items.append({
            "item_id": str(raw_item.get("item_id") or uuid.uuid4().hex),
            "block_id": block_id,
            "target_kind": target_kind,
            "before": raw_item.get("before"),
            "after": raw_item.get("after"),
            "reason": str(raw_item.get("reason") or ""),
            "status": "pending",
            "resolved_at": None,
            "resolution_reason": None,
            "receipt": None,
        })

    placeholder = {
        "schema_version": CHANGE_PROPOSAL_SCHEMA,
        "proposal_id": proposal_id,
        "request_id": request_id,
        "course_id": course_id,
        "scope": scope,
        "target_block_ids": list(target_block_ids),
        "items": normalized_items,
        "source": source,
        "status": "pending",
        "created_at": now,
        "resolved_at": None,
        "generation_meta": dict(generation_meta or {}),
    }
    proposal, _created = repository.create_once(placeholder)
    return proposal


def _find_item(proposal: dict[str, Any], item_id: str) -> dict[str, Any]:
    for item in proposal.get("items") or []:
        if item.get("item_id") == item_id:
            return item
    raise ChangeProposalNotFound(item_id)


def _recompute_status(proposal: dict[str, Any]) -> dict[str, Any]:
    items = proposal.get("items") or []
    all_resolved = bool(items) and all(item.get("status") != "pending" for item in items)
    proposal["status"] = "resolved" if all_resolved else "pending"
    if all_resolved and not proposal.get("resolved_at"):
        proposal["resolved_at"] = _now()
    if not all_resolved:
        proposal["resolved_at"] = None
    return proposal


async def apply_item(
    repository: ChangeProposalRepository,
    command_service: CourseCommandService,
    proposal_id: str,
    item_id: str,
    *,
    expected_document_revision: str,
    expected_block_revision: str,
    actor: str,
) -> dict[str, Any]:
    """Apply a single item of a change proposal via CourseCommandService.replace_block.

    Only a `pending` item may be applied; re-applying an already-resolved item
    raises ChangeProposalConflict instead of silently overwriting it.
    """
    proposal = repository.load(proposal_id)
    item = _find_item(proposal, item_id)
    if item.get("status") != "pending":
        raise ChangeProposalConflict(
            f"Item cannot be applied from status {item.get('status')}",
            proposal=proposal,
        )
    after = item.get("after")
    if not isinstance(after, dict) or "payload" not in after:
        raise ChangeProposalConflict("Item 'after' payload is invalid", proposal=proposal)
    payload = after["payload"]
    if not isinstance(payload, dict):
        raise ChangeProposalConflict("Item 'after' payload must be an object", proposal=proposal)

    try:
        receipt = await command_service.replace_block(
            proposal["course_id"],
            command_id=f"change-proposal-{proposal_id}-{item_id}",
            expected_document_revision=expected_document_revision,
            expected_block_revision=expected_block_revision,
            block_id=str(item["block_id"]),
            payload=payload,
            reason=str(item.get("reason") or "变更集应用"),
            actor=actor,
        )
    except CourseDocumentConflict as exc:
        raise ChangeProposalConflict(str(exc), proposal=proposal) from exc

    def _apply_updater(current: dict[str, Any]) -> dict[str, Any]:
        target = _find_item(current, item_id)
        if target.get("status") != "pending":
            raise ChangeProposalConflict(
                f"Item cannot be applied from status {target.get('status')}",
                proposal=current,
            )
        target["status"] = "applied"
        target["resolved_at"] = _now()
        target["receipt"] = receipt
        return _recompute_status(current)

    def _predicate(current: dict[str, Any]) -> bool:
        target = _find_item(current, item_id)
        return target.get("status") == "pending"

    updated, changed = repository.update_if(proposal_id, _predicate, _apply_updater)
    if not changed:
        latest_item = _find_item(updated, item_id)
        raise ChangeProposalConflict(
            f"Item cannot be applied from status {latest_item.get('status')}",
            proposal=updated,
        )
    return updated


def reject_item(
    repository: ChangeProposalRepository,
    proposal_id: str,
    item_id: str,
    *,
    reason: str | None = None,
) -> dict[str, Any]:
    """Reject a single pending item and record `reason` on the item.

    Evidence back-flow: spec §4 "AI 变更 MUST 以待确认形式呈现" hard-requires
    that a rejection reason flows back into the learner's evidence trail as a
    new `LearningEvent`, not just onto the change-proposal item itself. That
    write happens *here* (inside the state-machine module), not only in the
    HTTP router layer (`routers/change_proposals.py`). Reasoning: this module
    is otherwise a pure state machine with no dependency on
    `learning_events.py`, which is the cleaner default layering — but a
    router-only implementation would silently skip the MUST for any caller
    that invokes `reject_item` directly (background jobs, batch/regrade
    tooling, tests), which is a real and likely path here (this module already
    has non-HTTP callers). A missed hard requirement is worse than the extra
    coupling, so the single choke point every rejection passes through
    (`reject_item` itself) is what performs the write. The import of
    `learning_events` is deferred to function scope to avoid a module-level
    dependency/import-cycle risk given `learning_events.py` may in turn touch
    course/learner services.

    `event_type="learner_self_reported"` is reused deliberately (not a new
    enum value) so the rejection reason is picked up by the *existing*
    evidence classification/trigger logic in `learner_model.py`
    (`classify_evidence_event` / `evaluate_evidence_trigger`) without any
    change to that logic, and so it also goes through the existing
    `_maybe_trigger_evidence_evaluation` hook in `learning_events.py` that can
    generate a follow-up change proposal from strong-enough evidence.

    Decision on empty `reason`: if the student rejects without typing a
    reason, we still emit one low-strength generic evidence event (rather
    than silently doing nothing). Silence would make the change-proposal
    history inconsistent with the evidence trail (a rejection happened, the
    student had *some* implicit judgment, but nothing about it is ever
    recoverable from `learning_events.json`). The event's `evidence.statement`
    is left empty/marked so it classifies as the weakest signal
    (`reexplain_request` at half-weight in `classify_evidence_event`, since it
    won't match any incomprehension/reexplain marker) and can only ever
    contribute in aggregate with other evidence, never trigger alone.
    """
    proposal = repository.load(proposal_id)
    item = _find_item(proposal, item_id)
    if item.get("status") != "pending":
        raise ChangeProposalConflict(
            f"Item cannot be rejected from status {item.get('status')}",
            proposal=proposal,
        )

    def _reject_updater(current: dict[str, Any]) -> dict[str, Any]:
        target = _find_item(current, item_id)
        if target.get("status") != "pending":
            raise ChangeProposalConflict(
                f"Item cannot be rejected from status {target.get('status')}",
                proposal=current,
            )
        target["status"] = "rejected"
        target["resolved_at"] = _now()
        target["resolution_reason"] = reason
        return _recompute_status(current)

    def _predicate(current: dict[str, Any]) -> bool:
        target = _find_item(current, item_id)
        return target.get("status") == "pending"

    updated, changed = repository.update_if(proposal_id, _predicate, _reject_updater)
    if not changed:
        latest_item = _find_item(updated, item_id)
        raise ChangeProposalConflict(
            f"Item cannot be rejected from status {latest_item.get('status')}",
            proposal=updated,
        )

    rejected_item = _find_item(updated, item_id)
    _record_rejection_evidence(updated, rejected_item, reason=reason)
    return updated


def _record_rejection_evidence(
    proposal: dict[str, Any],
    item: dict[str, Any],
    *,
    reason: str | None,
) -> None:
    """Best-effort write of a `LearningEvent` capturing why a change-proposal
    item was rejected. Never raises: a failure here must not roll back or mask
    the already-committed rejection, mirroring the "best-effort side effect"
    pattern already used elsewhere in this codebase (see
    `_maybe_trigger_evidence_evaluation` in `learning_events.py`).
    """
    try:
        from learning_events import record_learning_event

        normalized_reason = str(reason or "").strip()
        statement = (
            normalized_reason
            if normalized_reason
            else "学生拒绝了该变更建议，但未填写拒绝理由。"
        )
        record_learning_event(
            event_type="learner_self_reported",
            actor="learner",
            source="change_proposal_rejection",
            course_id=proposal.get("course_id"),
            node_id=item.get("block_id"),
            evidence={
                "statement": statement,
                "reason_provided": bool(normalized_reason),
                "change_proposal_id": proposal.get("proposal_id"),
                "change_proposal_item_id": item.get("item_id"),
            },
            metadata={
                "change_proposal_scope": proposal.get("scope"),
            },
        )
    except Exception:
        pass


def regenerate_item(
    repository: ChangeProposalRepository,
    proposal_id: str,
    item_id: str,
    *,
    extra_instruction: str | None = None,
) -> dict[str, Any]:
    """Mark the original item rejected (recording the regeneration request as the
    reason) and append a fresh pending item skeleton for the same block. The new
    item does not reuse the old `after` content — callers (e.g. a generation
    service) are expected to fill it in before it is applied.
    """
    proposal = repository.load(proposal_id)
    item = _find_item(proposal, item_id)
    if item.get("status") != "pending":
        raise ChangeProposalConflict(
            f"Item cannot be regenerated from status {item.get('status')}",
            proposal=proposal,
        )

    new_item_id = uuid.uuid4().hex

    def _regenerate_updater(current: dict[str, Any]) -> dict[str, Any]:
        target = _find_item(current, item_id)
        if target.get("status") != "pending":
            raise ChangeProposalConflict(
                f"Item cannot be regenerated from status {target.get('status')}",
                proposal=current,
            )
        target["status"] = "rejected"
        target["resolved_at"] = _now()
        target["resolution_reason"] = extra_instruction or "regenerate_requested"
        new_item = {
            "item_id": new_item_id,
            "block_id": target["block_id"],
            "target_kind": target.get("target_kind") or "course_block",
            "before": target.get("before"),
            "after": None,
            "reason": target.get("reason") or "",
            "status": "pending",
            "resolved_at": None,
            "resolution_reason": None,
            "receipt": None,
            "regenerated_from": item_id,
            "extra_instruction": extra_instruction,
        }
        items = list(current.get("items") or [])
        items.append(new_item)
        current["items"] = items
        target_block_ids = set(current.get("target_block_ids") or [])
        target_block_ids.add(target["block_id"])
        current["target_block_ids"] = sorted(target_block_ids)
        return _recompute_status(current)

    def _predicate(current: dict[str, Any]) -> bool:
        target = _find_item(current, item_id)
        return target.get("status") == "pending"

    updated, changed = repository.update_if(proposal_id, _predicate, _regenerate_updater)
    if not changed:
        latest_item = _find_item(updated, item_id)
        raise ChangeProposalConflict(
            f"Item cannot be regenerated from status {latest_item.get('status')}",
            proposal=updated,
        )
    return updated


change_proposal_repository = ChangeProposalRepository()


__all__ = [
    "CHANGE_PROPOSAL_SCHEMA",
    "ChangeProposalConflict",
    "ChangeProposalNotFound",
    "ChangeProposalRepository",
    "apply_item",
    "change_proposal_repository",
    "create_proposal",
    "reject_item",
    "regenerate_item",
]
