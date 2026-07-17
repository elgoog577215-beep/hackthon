"""Teacher/author initiated changes for canonical base course documents.

The historical module/API name is kept as a compatibility surface. New code
must treat records with ``write_target == "base_course"`` as
``CourseAuthoringChange`` objects. Learner evidence belongs to the personal
adaptation pipeline and is never allowed to reach ``CourseCommandService``.
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


COURSE_AUTHORING_CHANGE_SCHEMA = "course_authoring_change_v1"
# Compatibility constant for existing imports. Newly persisted records use the
# explicit authoring schema below.
CHANGE_PROPOSAL_SCHEMA = COURSE_AUTHORING_CHANGE_SCHEMA
_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]+$")

ChangeProposalScope = Literal["block", "section", "sections", "chapters", "book"]
ChangeProposalSource = Literal[
    "manual",
    "representation_semantic",
    "block_regeneration",
    "evidence",
    "kb_link",
]
ChangeWriteTarget = Literal["base_course", "personal_overlay", "knowledge_review"]
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

    write_target: ChangeWriteTarget = (
        "personal_overlay"
        if source == "evidence"
        else "knowledge_review"
        if source == "kb_link"
        else "base_course"
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
    source: Literal["manual", "representation_semantic", "block_regeneration"] = "manual",
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


async def apply_objective_item(
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
    library_repository: Any,
) -> dict[str, Any]:
    """Accept a pending `target_kind == "kg_node"` item.

    Unlike `apply_item` (which replaces a course block's canonical content),
    a kg_node item's `after` payload only ever carries a review note (see
    `course_knowledge_map.propose_kb_linkage_from_block_change`) - there is
    no proposed replacement text to write. "Accepting" it means recording an
    operator review acknowledgement in a mutable sidecar owned by the pinned
    library revision and marks the proposal item resolved. The formal revision
    remains immutable.
    """
    proposal = repository.load(proposal_id)
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

    binding = course_data.get("knowledge_library_binding") or {}
    library_id = str(binding.get("library_id") or "")
    revision_id = str(binding.get("revision_id") or "")
    knowledge_id = str(item.get("block_id") or "")
    if not library_id or not revision_id:
        raise ChangeProposalConflict("未能定位该知识节点所属的知识库", proposal=proposal)

    try:
        entry = library_repository.record_node_review(
            library_id,
            revision_id,
            knowledge_id,
            note=str(after.get("note") or ""),
            source_block_id=str(after.get("source_block_id") or ""),
            proposal_id=proposal_id,
            item_id=item_id,
            reviewed_by=actor,
        )
    except KeyError as exc:
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
        target["receipt"] = {"kind": "kg_node_review_acknowledged", **entry}
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
    """Reject one item and keep learner evidence separate from course authoring.

    Rejections flow back into the learner evidence trail only for proposals
    created from learning evidence or proposals that write to a personal
    overlay. Rejecting a base-course authoring change is a maintainer action
    and must not alter any learner model.
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
    "change_proposal_repository",
    "create_authoring_change",
    "create_proposal",
    "reject_item",
    "regenerate_item",
]
