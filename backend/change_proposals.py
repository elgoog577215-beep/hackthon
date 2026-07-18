"""Teacher/author initiated changes for canonical course documents.

The historical module/API name is kept as a compatibility surface. New code
must treat records with ``write_target == "base_course"`` as
``CourseAuthoringChange`` objects. Learner evidence belongs to
``course_evolution``; reviewed plans there reach the same canonical
``CourseDocument`` through a grouped command instead of creating a second
proposal or overlay circuit here.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import threading
from typing import Any, AsyncIterator, Callable, Iterator, Literal
import uuid

from course_commands import CourseCommandService
from course_document import refresh_block_revision, stable_hash
from course_repository import CourseDocumentConflict, CourseDocumentRepository


COURSE_AUTHORING_CHANGE_SCHEMA = "course_authoring_change_v1"
# Compatibility constant for existing imports. Newly persisted records use the
# explicit authoring schema below.
CHANGE_PROPOSAL_SCHEMA = COURSE_AUTHORING_CHANGE_SCHEMA
_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]+$")
# Demo-only process-local transaction boundary; this is not a distributed lock.
_TRANSITION_LOCKS: dict[str, threading.Lock] = {}
_TRANSITION_LOCKS_GUARD = threading.Lock()

ChangeProposalScope = Literal["block", "section", "sections", "chapters", "book"]
ChangeProposalSource = Literal[
    "manual",
    "representation_semantic",
    "block_regeneration",
    "personalization",
    "evidence",
    "kb_link",
]
ChangeWriteTarget = Literal["base_course", "knowledge_review"]
ChangeProposalStatus = Literal["pending", "resolved"]
ChangeProposalItemStatus = Literal["pending", "applied", "rejected"]
# ``block_id`` is retained as the compatibility identifier field. Its actual
# entity type is explicit so authoring changes never disguise a section
# learning-objective update as a content-block replacement.
ChangeProposalTargetKind = Literal["course_block", "course_objective", "kg_node"]
_TARGET_KINDS = {"course_block", "course_objective", "kg_node"}


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


def _transition_locks(proposal_id: str, course_id: str) -> list[threading.Lock]:
    keys = sorted({f"proposal:{proposal_id}", f"course:{course_id}"})
    with _TRANSITION_LOCKS_GUARD:
        return [_TRANSITION_LOCKS.setdefault(key, threading.Lock()) for key in keys]


def _proposal_course_ids(
    repository: ChangeProposalRepository,
    proposal_id: str,
) -> tuple[str, str]:
    proposal = repository.load(proposal_id)
    return proposal_id, str(proposal.get("course_id") or "")


@contextmanager
def _proposal_transition(
    repository: ChangeProposalRepository,
    proposal_id: str,
) -> Iterator[None]:
    locks = _transition_locks(*_proposal_course_ids(repository, proposal_id))
    for lock in locks:
        lock.acquire()
    try:
        yield
    finally:
        for lock in reversed(locks):
            lock.release()


@asynccontextmanager
async def _async_proposal_transition(
    repository: ChangeProposalRepository,
    proposal_id: str,
) -> AsyncIterator[None]:
    locks = _transition_locks(*_proposal_course_ids(repository, proposal_id))
    acquired: list[threading.Lock] = []
    try:
        for lock in locks:
            while not lock.acquire(blocking=False):
                await asyncio.sleep(0.001)
            acquired.append(lock)
        yield
    finally:
        for lock in reversed(acquired):
            lock.release()


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
    and defaults to "course_block"; pass "course_objective" when `block_id`
    names a section id, or "kg_node" when it names a knowledge-graph node id.
    """
    if source == "evidence":
        raise ValueError(
            "Learning evidence must create a reviewed course evolution plan, "
            "not a legacy change proposal"
        )
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
            "selected": bool(raw_item.get("selected", True)),
            "expected_block_revision": str(raw_item.get("expected_block_revision") or ""),
            "status": "pending",
            "resolved_at": None,
            "resolution_reason": None,
            "receipt": None,
        })

    write_target: ChangeWriteTarget = (
        "knowledge_review" if source == "kb_link" else "base_course"
    )
    placeholder = {
        "schema_version": CHANGE_PROPOSAL_SCHEMA,
        "change_kind": "course_authoring_change" if write_target == "base_course" else "legacy_compatibility_change",
        "write_target": write_target,
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


def create_authoring_change(
    repository: ChangeProposalRepository,
    course_id: str,
    *,
    request_id: str,
    scope: ChangeProposalScope,
    target_block_ids: list[str],
    items: list[dict[str, Any]],
    source: Literal["manual", "representation_semantic", "block_regeneration", "personalization"] = "manual",
    generation_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a base-course authoring change through the compatibility store."""

    return create_proposal(
        repository,
        course_id,
        request_id=request_id,
        scope=scope,
        target_block_ids=target_block_ids,
        items=items,
        source=source,
        generation_meta=generation_meta,
    )


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


def _require_no_pending_operation(proposal: dict[str, Any]) -> None:
    if proposal.get("pending_operation") is not None:
        raise ChangeProposalConflict(
            "Proposal has an operation awaiting recovery",
            proposal=proposal,
        )


def require_single_item_apply(
    proposal: dict[str, Any],
    *,
    expected_document_revision: str | None = None,
) -> None:
    if proposal.get("source") == "personalization":
        raise ChangeProposalConflict(
            "Personalization proposals must use the atomic apply-selected endpoint",
            proposal=proposal,
        )
    base_revision = str(
        (proposal.get("generation_meta") or {}).get("base_document_revision") or ""
    )
    if (
        base_revision
        and expected_document_revision is not None
        and expected_document_revision != base_revision
    ):
        raise ChangeProposalConflict(
            "Current revision does not match the proposal base document revision",
            proposal=proposal,
        )


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
    async with _async_proposal_transition(repository, proposal_id):
        return await _apply_item_locked(
            repository,
            command_service,
            proposal_id,
            item_id,
            expected_document_revision=expected_document_revision,
            expected_block_revision=expected_block_revision,
            actor=actor,
        )


async def _apply_item_locked(
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
    _require_no_pending_operation(proposal)
    require_single_item_apply(
        proposal,
        expected_document_revision=expected_document_revision,
    )
    if proposal.get("write_target") == "personal_overlay" or proposal.get("source") == "evidence":
        raise ChangeProposalConflict(
            "Personal adaptation cannot modify the base course document",
            proposal=proposal,
        )
    if proposal.get("write_target") not in {None, "base_course"}:
        raise ChangeProposalConflict(
            "This change does not target the base course document",
            proposal=proposal,
        )
    item = _find_item(proposal, item_id)
    if item.get("status") != "pending":
        raise ChangeProposalConflict(
            f"Item cannot be applied from status {item.get('status')}",
            proposal=proposal,
        )
    after = item.get("after")
    if after is None:
        raise ChangeProposalConflict(
            "该条目内容尚未生成（等待重新生成完成），暂时无法接受；"
            "请先点击“重新生成”，或联系管理员处理。",
            proposal=proposal,
        )
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


async def apply_selected_items(
    repository: ChangeProposalRepository,
    course_repository: CourseDocumentRepository,
    proposal_id: str,
    item_ids: list[str],
    *,
    expected_document_revision: str,
    actor: str,
) -> dict[str, Any]:
    async with _async_proposal_transition(repository, proposal_id):
        return await _apply_selected_items_locked(
            repository,
            course_repository,
            proposal_id,
            item_ids,
            expected_document_revision=expected_document_revision,
            actor=actor,
        )


async def _apply_selected_items_locked(
    repository: ChangeProposalRepository,
    course_repository: CourseDocumentRepository,
    proposal_id: str,
    item_ids: list[str],
    *,
    expected_document_revision: str,
    actor: str,
) -> dict[str, Any]:
    """Validate and apply selected course-block items in one document commit."""
    proposal = repository.load(proposal_id)
    if proposal.get("write_target") not in {None, "base_course"}:
        raise ChangeProposalConflict(
            "This change does not target the base course document",
            proposal=proposal,
        )
    normalized_ids = [str(item_id) for item_id in item_ids if str(item_id)]
    if not normalized_ids or len(set(normalized_ids)) != len(normalized_ids):
        raise ChangeProposalConflict(
            "At least one unique change item must be selected",
            proposal=proposal,
        )

    base_revision = str((proposal.get("generation_meta") or {}).get("base_document_revision") or "")
    if proposal.get("source") == "personalization" and not base_revision:
        raise ChangeProposalConflict(
            "Personalization proposal is missing its base document revision",
            proposal=proposal,
        )
    if base_revision and expected_document_revision != base_revision:
        raise ChangeProposalConflict(
            "Apply revision does not match the proposal base document revision",
            proposal=proposal,
        )

    sorted_ids = sorted(normalized_ids)
    selected_ids = set(normalized_ids)
    course_id = str(proposal.get("course_id") or "")
    command_id = f"apply-selected-{proposal_id}-{'-'.join(sorted_ids)}"
    for item_id in normalized_ids:
        _find_item(proposal, item_id)

    pending_operation = proposal.get("pending_operation")
    if pending_operation is not None and (
        pending_operation.get("kind") != "apply_selected"
        or pending_operation.get("command_id") != command_id
        or sorted(pending_operation.get("item_ids") or []) != sorted_ids
        or pending_operation.get("expected_document_revision") != expected_document_revision
    ):
        raise ChangeProposalConflict(
            "Another proposal operation is awaiting recovery",
            proposal=proposal,
        )

    def finalize(receipt: dict[str, Any]) -> dict[str, Any]:
        def _apply_updater(current: dict[str, Any]) -> dict[str, Any]:
            current_pending = current.get("pending_operation")
            if current_pending is not None and current_pending.get("command_id") != command_id:
                raise ChangeProposalConflict(
                    "Another proposal operation is awaiting recovery",
                    proposal=current,
                )
            for current_item in current.get("items") or []:
                if current_item.get("item_id") not in selected_ids:
                    continue
                current_item["status"] = "applied"
                current_item["resolved_at"] = current_item.get("resolved_at") or _now()
                current_item["receipt"] = receipt
            current["pending_operation"] = None
            return _recompute_status(current)

        updated = repository.update(proposal_id, _apply_updater)
        return {
            "proposal": updated,
            "receipt": receipt,
            "document": course_repository.document_envelope(course_id),
        }

    existing_receipt = course_repository.receipt_for_command(course_id, command_id)
    if existing_receipt:
        return finalize(existing_receipt)

    document, canonical = course_repository.load_document(course_id)
    if not canonical:
        raise ChangeProposalConflict(
            "Course must be migrated before applying changes",
            proposal=proposal,
        )
    if document.document_revision != expected_document_revision:
        raise ChangeProposalConflict("Course document revision changed", proposal=proposal)

    blocks_by_id = {block.block_id: block for block in document.blocks}
    prepared: list[tuple[dict[str, Any], Any, dict[str, Any]]] = []
    for item_id in normalized_ids:
        item = _find_item(proposal, item_id)
        if (item.get("target_kind") or "course_block") != "course_block":
            raise ChangeProposalConflict(
                "Selected change item does not target a course block",
                proposal=proposal,
            )
        if item.get("status") != "pending":
            raise ChangeProposalConflict(
                f"Item cannot be applied from status {item.get('status')}",
                proposal=proposal,
            )
        target = blocks_by_id.get(str(item.get("block_id") or ""))
        if target is None:
            raise ChangeProposalConflict("Course block not found", proposal=proposal)
        expected_block_revision = str(item.get("expected_block_revision") or "")
        if not expected_block_revision or target.internal_revision != expected_block_revision:
            raise ChangeProposalConflict("Course block revision changed", proposal=proposal)

        before = item.get("before")
        after = item.get("after")
        if not isinstance(before, dict) or not isinstance(after, dict):
            raise ChangeProposalConflict(
                "Selected change item requires structured before and after values",
                proposal=proposal,
            )
        if str(before.get("block_id") or "") != target.block_id:
            raise ChangeProposalConflict("Course block identity changed", proposal=proposal)
        before_payload = before.get("payload")
        after_payload = after.get("payload")
        if not isinstance(before_payload, dict) or before_payload != target.payload:
            raise ChangeProposalConflict("Course block content changed", proposal=proposal)
        if not isinstance(after_payload, dict):
            raise ChangeProposalConflict("Item 'after' payload is invalid", proposal=proposal)
        prepared.append((item, target, deepcopy(after_payload)))

    operation = {
        "kind": "apply_selected",
        "command_id": command_id,
        "item_ids": sorted_ids,
        "expected_document_revision": expected_document_revision,
        "started_at": _now(),
    }

    if pending_operation is None:
        def _set_pending_operation(current: dict[str, Any]) -> dict[str, Any]:
            if current.get("pending_operation") is not None:
                raise ChangeProposalConflict(
                    "Another proposal operation is awaiting recovery",
                    proposal=current,
                )
            for item_id in normalized_ids:
                current_item = _find_item(current, item_id)
                if current_item.get("status") != "pending":
                    raise ChangeProposalConflict(
                        f"Item cannot be applied from status {current_item.get('status')}",
                        proposal=current,
                    )
            current["pending_operation"] = operation
            return current

        proposal = repository.update(proposal_id, _set_pending_operation)

    for _item, target, payload in prepared:
        target.payload = payload
        refresh_block_revision(target)

    affected_block_ids = [target.block_id for _item, target, _payload in prepared]
    try:
        receipt = await course_repository.commit_document(
            str(proposal["course_id"]),
            document,
            expected_revision=expected_document_revision,
            operation={
                "command_id": command_id,
                "operation": "apply_selected_authoring_changes",
                "affected_block_ids": affected_block_ids,
                "reason": "应用个性化课程改进",
                "actor": actor,
            },
        )
    except CourseDocumentConflict as exc:
        try:
            repository.update(
                proposal_id,
                lambda current: {**current, "pending_operation": None},
            )
        except Exception:
            pass
        raise ChangeProposalConflict(str(exc), proposal=proposal) from exc
    return finalize(receipt)


async def apply_objective_item(
    repository: ChangeProposalRepository,
    command_service: CourseCommandService,
    proposal_id: str,
    item_id: str,
    *,
    expected_document_revision: str,
    actor: str,
) -> dict[str, Any]:
    async with _async_proposal_transition(repository, proposal_id):
        return await _apply_objective_item_locked(
            repository,
            command_service,
            proposal_id,
            item_id,
            expected_document_revision=expected_document_revision,
            actor=actor,
        )


async def _apply_objective_item_locked(
    repository: ChangeProposalRepository,
    command_service: CourseCommandService,
    proposal_id: str,
    item_id: str,
    *,
    expected_document_revision: str,
    actor: str,
) -> dict[str, Any]:
    """Apply a section learning-objective authoring change to the course truth."""
    proposal = repository.load(proposal_id)
    require_single_item_apply(
        proposal,
        expected_document_revision=expected_document_revision,
    )
    if proposal.get("write_target") not in {None, "base_course"}:
        raise ChangeProposalConflict(
            "This change does not target the base course document",
            proposal=proposal,
        )
    item = _find_item(proposal, item_id)
    if (item.get("target_kind") or "course_block") != "course_objective":
        raise ChangeProposalConflict(
            "Change item does not target a course learning objective",
            proposal=proposal,
        )
    if item.get("status") != "pending":
        raise ChangeProposalConflict(
            f"Item cannot be applied from status {item.get('status')}",
            proposal=proposal,
        )
    before = item.get("before")
    after = item.get("after")
    if not isinstance(before, dict) or not isinstance(after, dict):
        raise ChangeProposalConflict(
            "Course objective change requires structured before and after values",
            proposal=proposal,
        )
    expected_objective_revision = str(before.get("objective_revision_id") or "")
    next_objective = str(after.get("learning_objective") or "").strip()
    if not expected_objective_revision or not next_objective:
        raise ChangeProposalConflict(
            "Course objective change is missing its revision or target value",
            proposal=proposal,
        )

    try:
        receipt = await command_service.update_section_objective(
            proposal["course_id"],
            command_id=f"change-proposal-{proposal_id}-{item_id}",
            expected_document_revision=expected_document_revision,
            expected_objective_revision=expected_objective_revision,
            section_id=str(item["block_id"]),
            learning_objective=next_objective,
            reason=str(item.get("reason") or "课程目标变更应用"),
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

    updated, changed = repository.update_if(
        proposal_id,
        lambda current: _find_item(current, item_id).get("status") == "pending",
        _apply_updater,
    )
    if not changed:
        latest_item = _find_item(updated, item_id)
        raise ChangeProposalConflict(
            f"Item cannot be applied from status {latest_item.get('status')}",
            proposal=updated,
        )
    return updated


def apply_kg_node_item(
    repository: ChangeProposalRepository,
    proposal_id: str,
    item_id: str,
    *,
    actor: str,
    course_data: dict[str, Any],
) -> dict[str, Any]:
    """Accept a pending `target_kind == "kg_node"` item.

    Unlike `apply_item` (which replaces a course block's canonical content),
    A kg_node item's ``after`` payload carries a review note, not replacement
    knowledge text. Accepting it records a course-local acknowledgement on the
    proposal itself. Any actual knowledge rewrite remains a separate action in
    the course knowledge maintenance surface.
    """
    proposal = repository.load(proposal_id)
    _require_no_pending_operation(proposal)
    item = _find_item(proposal, item_id)
    if item.get("status") != "pending":
        raise ChangeProposalConflict(
            f"Item cannot be applied from status {item.get('status')}",
            proposal=proposal,
        )
    after = item.get("after")
    if after is None:
        raise ChangeProposalConflict(
            "该条目内容尚未生成（等待重新生成完成），暂时无法接受；"
            "请先点击“重新生成”，或联系管理员处理。",
            proposal=proposal,
        )
    if not isinstance(after, dict):
        raise ChangeProposalConflict("Item 'after' payload is invalid", proposal=proposal)

    knowledge_id = str(item.get("block_id") or "")
    if not knowledge_id:
        raise ChangeProposalConflict("未能定位当前课程知识节点", proposal=proposal)
    from course_knowledge_base import compile_course_knowledge_base

    knowledge_base = course_data.get("course_knowledge_base") or compile_course_knowledge_base(
        deepcopy(course_data)
    )
    valid_ids = {
        str(point.get("knowledge_id") or "")
        for point in knowledge_base.get("knowledge_points") or []
    }
    if knowledge_id not in valid_ids:
        raise ChangeProposalConflict("该知识节点不属于当前课程", proposal=proposal)
    entry = {
        "knowledge_scope": "current_course_only",
        "knowledge_id": knowledge_id,
        "note": str(after.get("note") or ""),
        "source_block_id": str(after.get("source_block_id") or ""),
        "reviewed_by": actor,
        "reviewed_at": _now(),
    }

    def _apply_updater(current: dict[str, Any]) -> dict[str, Any]:
        target = _find_item(current, item_id)
        if target.get("status") != "pending":
            raise ChangeProposalConflict(
                f"Item cannot be applied from status {target.get('status')}",
                proposal=current,
            )
        target["status"] = "applied"
        target["resolved_at"] = _now()
        target["receipt"] = {"kind": "course_knowledge_review_acknowledged", **entry}
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
    with _proposal_transition(repository, proposal_id):
        return _reject_item_locked(
            repository,
            proposal_id,
            item_id,
            reason=reason,
        )


def _reject_item_locked(
    repository: ChangeProposalRepository,
    proposal_id: str,
    item_id: str,
    *,
    reason: str | None = None,
) -> dict[str, Any]:
    """Reject one item and keep learner evidence separate from course authoring.

    Rejections flow back into the learner evidence trail only for proposals
    created from learning evidence or proposals that write to a personal
    overlay. Rejecting a base-course authoring change is a maintainer action
    and must not alter any learner model.
    """
    proposal = repository.load(proposal_id)
    _require_no_pending_operation(proposal)
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

    if updated.get("source") == "evidence" or updated.get("write_target") == "personal_overlay":
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


def _try_regenerate_evidence_after(
    proposal: dict[str, Any],
    target: dict[str, Any],
) -> dict[str, Any] | None:
    """Best-effort re-run of the MVP template generator for an evidence-sourced,
    course-block-targeted item, so "regenerate" produces a genuinely new (even
    if still template-based) `after.payload` instead of always leaving the new
    item stuck in the "awaiting generation" state.

    Only attempted when the proposal's `source == "evidence"` (i.e. it was
    created by `learner_model_service.evaluate_and_propose_change`) and the
    item targets a real course block (`target_kind == "course_block"`, the
    default). `kb_link`/manual items, or evidence items missing the
    `user_id` needed to re-load the triggering evidence, fall back to
    leaving `after=None` — the caller treats that as the honest "awaiting
    generation" signal.

    Never raises: any failure (missing course/block/events, import errors)
    is swallowed and treated as "could not regenerate right now", which is
    always a safe/legal outcome for this item.
    """
    if proposal.get("source") != "evidence":
        return None
    if (target.get("target_kind") or "course_block") != "course_block":
        return None
    block_id = target.get("block_id")
    course_id = proposal.get("course_id")
    user_id = str((proposal.get("generation_meta") or {}).get("user_id") or "")
    if not block_id or not course_id or not user_id:
        return None
    try:
        # Deferred import: learner_model_service imports this module at
        # module scope (`create_proposal`, `change_proposal_repository`), so
        # importing it back at module scope here would create a cycle.
        from learner_model_service import _generate_supplement_payload
        from learning_events import load_learning_events

        course_repository = _load_course_document_repository()
        document, _is_canonical = course_repository.load_document(course_id)
        block = next((b for b in document.blocks if b.block_id == block_id), None)
        if block is None:
            return None
        events = load_learning_events(
            user_id=user_id,
            course_id=course_id,
            node_id=block_id,
            event_type="learner_self_reported",
        )
        content_key = (
            "markdown" if "markdown" in block.payload
            else ("text" if "text" in block.payload else "content")
        )
        new_content, _generation_method = _generate_supplement_payload(block.payload, events)
        new_payload = dict(block.payload)
        new_payload[content_key] = new_content
        return {"payload": new_payload}
    except Exception:
        return None


def _load_course_document_repository() -> CourseDocumentRepository:
    """`CourseDocumentRepository` needs a storage backend; reuse the same
    module-level `storage` singleton the rest of this codebase uses, imported
    lazily to avoid widening this module's module-scope import surface."""
    from storage import storage

    return CourseDocumentRepository(storage)


def regenerate_item(
    repository: ChangeProposalRepository,
    proposal_id: str,
    item_id: str,
    *,
    extra_instruction: str | None = None,
    generated_after: dict[str, Any] | None = None,
    generation_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    with _proposal_transition(repository, proposal_id):
        return _regenerate_item_locked(
            repository,
            proposal_id,
            item_id,
            extra_instruction=extra_instruction,
            generated_after=generated_after,
            generation_meta=generation_meta,
        )


def _regenerate_item_locked(
    repository: ChangeProposalRepository,
    proposal_id: str,
    item_id: str,
    *,
    extra_instruction: str | None = None,
    generated_after: dict[str, Any] | None = None,
    generation_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Mark the original item rejected (recording the regeneration request as the
    reason) and append a fresh item for the same block.

    When the proposal is evidence-sourced and targets a real course block, this
    makes a best-effort attempt to immediately re-run the same MVP template
    generator `evaluate_and_propose_change` uses (`_template_supplement_text`)
    against the current block content and evidence, so the new item's `after`
    is populated with a genuinely fresh (still template-based, not LLM-based)
    payload. When that isn't possible (manual/kb_link proposals, missing
    user_id, missing block/course, or any other failure), the new item's
    `after` is left `None` — this is a deliberate, contractual "content not
    yet generated / awaiting regeneration" signal, not a silent placeholder:
    `apply_item` refuses to apply such an item with an explicit error, and the
    frontend must render it as a pending-generation state rather than a blank
    diff.
    """
    if generated_after is not None and (
        not isinstance(generated_after, dict)
        or not isinstance(generated_after.get("payload"), dict)
    ):
        raise ValueError("Regenerated content requires an object payload")

    proposal = repository.load(proposal_id)
    _require_no_pending_operation(proposal)
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
        regenerated_after = (
            deepcopy(generated_after)
            if generated_after is not None
            else _try_regenerate_evidence_after(current, target)
        )
        new_item = {
            "item_id": new_item_id,
            "block_id": target["block_id"],
            "target_kind": target.get("target_kind") or "course_block",
            "before": target.get("before"),
            "after": regenerated_after,
            "reason": target.get("reason") or "",
            "status": "pending",
            "resolved_at": None,
            "resolution_reason": None,
            "receipt": None,
            "regenerated_from": item_id,
            "extra_instruction": extra_instruction,
            "generation_meta": deepcopy(generation_meta or {}),
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
    "COURSE_AUTHORING_CHANGE_SCHEMA",
    "CHANGE_PROPOSAL_SCHEMA",
    "ChangeProposalConflict",
    "ChangeProposalNotFound",
    "ChangeProposalRepository",
    "apply_item",
    "apply_selected_items",
    "change_proposal_repository",
    "create_authoring_change",
    "create_proposal",
    "reject_item",
    "regenerate_item",
]
