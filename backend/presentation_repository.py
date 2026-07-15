"""Atomic filesystem repository for presentation deck state.

Presentation data is deliberately isolated from the course document store.  A
deck has one mutable manifest/working snapshot and append-only revisions.  Any
manifest pointer is switched only after the referenced entity is durable.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any, Literal

from presentation_models import (
    ArtifactReceipt,
    DeckProposal,
    DeckRevision,
    GenerationWorkingSnapshot,
    PresentationDeck,
    PresentationEvent,
    QualityReport,
    utc_now,
)
from storage import DATA_DIR


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,199}$")
_ARTIFACT_NAMES = {"html": "deck.html", "pptx": "deck.pptx"}


class PresentationRepositoryConflict(RuntimeError):
    """A repository precondition or idempotency contract was violated."""


class IdempotencyKeyReuseConflict(PresentationRepositoryConflict):
    """A request/command id was reused for a different operation or intent."""


class StaleRevisionConflict(PresentationRepositoryConflict):
    """A command was based on a revision that is no longer active."""


class ArtifactAccessError(PresentationRepositoryConflict):
    """A requested artifact is missing, stale, or outside its receipt root."""


class PresentationRepository:
    def __init__(self, root_dir: str | Path | None = None) -> None:
        self.root_dir = Path(root_dir or Path(DATA_DIR) / "presentation_decks").resolve()
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, threading.RLock] = {}
        self._locks_guard = threading.RLock()

    # ------------------------------------------------------------------
    # Deck lifecycle and aggregate reads
    # ------------------------------------------------------------------

    def create_deck(
        self,
        deck: PresentationDeck | dict[str, Any],
        source_snapshot: dict[str, Any],
        *,
        request_id: str | None = None,
        operation: str = "create_presentation",
        fingerprint_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        model = PresentationDeck.model_validate(self._object(deck))
        self._validate_id(model.course_id)
        self._validate_id(model.deck_id)
        snapshot = self._validate_source_snapshot(model, source_snapshot)
        course_receipt = self._course_request_receipt(model.course_id, request_id) if request_id else None
        effective_operation = str(operation or "create_presentation")
        intent = fingerprint_payload if fingerprint_payload is not None else {
            "course_id": model.course_id,
            "title": model.title,
            "scope": model.scope.model_dump(mode="json"),
            "purpose": model.purpose,
            "template_id": model.template_id,
            "source_snapshot_sha256": model.source_ref.source_snapshot_sha256,
        }
        request_fingerprint = self._fingerprint_argument(intent)

        # The receipt is course-scoped, so creation attempts for the same
        # course must share a lock even though every retry proposes a fresh
        # deck id.
        with self._lock(model.course_id):
            if course_receipt and course_receipt.exists():
                saved = self._read_json(course_receipt)
                if saved.get("request_id") != request_id or saved.get("course_id") != model.course_id:
                    raise PresentationRepositoryConflict("request_receipt_mismatch")
                self._assert_receipt_intent(
                    saved,
                    operation=effective_operation,
                    fingerprint=request_fingerprint,
                    fingerprint_key="request_fingerprint",
                )
                return self.load_manifest(str(saved["deck_id"]), course_id=model.course_id)

            directory = self._deck_dir(model.course_id, model.deck_id, create=False)
            manifest_path = directory / "manifest.json"
            if manifest_path.exists():
                current = self._read_json(manifest_path)
                if current == model.model_dump(mode="json"):
                    return current
                raise PresentationRepositoryConflict("deck_already_exists")

            directory.mkdir(parents=True, exist_ok=True)
            # Entity first, pointer last.
            self._atomic_write(directory / "source_snapshot.json", snapshot)
            self._atomic_write(manifest_path, model.model_dump(mode="json"))
            if course_receipt:
                self._atomic_write(course_receipt, {
                    "schema_version": "presentation-request-receipt/v1",
                    "request_id": request_id,
                    "operation": effective_operation,
                    "request_fingerprint": request_fingerprint,
                    "course_id": model.course_id,
                    "deck_id": model.deck_id,
                    "created_at": utc_now(),
                })
            return model.model_dump(mode="json")

    def list_decks(self, course_id: str) -> list[dict[str, Any]]:
        self._validate_id(course_id)
        directory = self.root_dir / course_id
        if not directory.exists():
            return []
        result: list[dict[str, Any]] = []
        for deck_dir in directory.iterdir():
            if not deck_dir.is_dir() or not _SAFE_ID.match(deck_dir.name):
                continue
            path = deck_dir / "manifest.json"
            if path.exists():
                result.append(self.load_manifest(deck_dir.name, course_id=course_id))
        return sorted(result, key=lambda item: str(item.get("updated_at") or ""), reverse=True)

    def load_manifest(self, deck_id: str, *, course_id: str | None = None) -> dict[str, Any]:
        directory = self._locate_deck(deck_id, course_id=course_id)
        path = directory / "manifest.json"
        if not path.exists():
            raise KeyError(f"Unknown presentation deck: {deck_id}")
        manifest = PresentationDeck.model_validate(self._read_json(path)).model_dump(mode="json")
        self._assert_manifest_pointers(directory, manifest)
        return manifest

    def get_deck(self, deck_id: str, *, course_id: str | None = None) -> dict[str, Any]:
        manifest = self.load_manifest(deck_id, course_id=course_id)
        result: dict[str, Any] = {"manifest": manifest}
        result["active_revision"] = (
            self.get_revision(deck_id, manifest["active_revision_id"], course_id=manifest["course_id"])
            if manifest.get("active_revision_id") else None
        )
        result["working"] = self.load_working(deck_id, course_id=manifest["course_id"])
        result["quality"] = (
            self.get_quality(deck_id, manifest["latest_quality_report_id"], course_id=manifest["course_id"])
            if manifest.get("latest_quality_report_id") else None
        )
        result["artifact"] = (
            self.get_artifact(
                manifest["latest_artifact_id"], deck_id=deck_id, course_id=manifest["course_id"]
            ) if manifest.get("latest_artifact_id") else None
        )
        return result

    def load_source_snapshot(self, deck_id: str, *, course_id: str | None = None) -> dict[str, Any]:
        directory = self._locate_deck(deck_id, course_id=course_id)
        snapshot = self._read_json(directory / "source_snapshot.json")
        manifest = self.load_manifest(deck_id, course_id=directory.parent.name)
        self._validate_source_snapshot(PresentationDeck.model_validate(manifest), snapshot)
        return snapshot

    # ------------------------------------------------------------------
    # Generation working state and replay log
    # ------------------------------------------------------------------

    def save_working(
        self,
        deck_id: str,
        snapshot: GenerationWorkingSnapshot | dict[str, Any],
        *,
        expected_revision_id: str | None = None,
        course_id: str | None = None,
    ) -> dict[str, Any]:
        model = GenerationWorkingSnapshot.model_validate(self._object(snapshot))
        if model.deck_id != deck_id:
            raise PresentationRepositoryConflict("working_deck_mismatch")
        directory = self._locate_deck(deck_id, course_id=course_id)
        with self._lock(deck_id):
            manifest = self.load_manifest(deck_id, course_id=directory.parent.name)
            self._check_revision(manifest, expected_revision_id)
            active = manifest.get("active_generation_id")
            if active and active != model.generation_id:
                raise PresentationRepositoryConflict("generation_already_active")
            self._validate_id(model.generation_id)
            payload = model.model_dump(mode="json")
            self._atomic_write(directory / "working" / f"{model.generation_id}.json", payload)
            manifest["active_generation_id"] = model.generation_id
            manifest["status"] = "generating"
            manifest["updated_at"] = utc_now()
            self._atomic_write(directory / "manifest.json", manifest)
            return payload

    def load_working(
        self,
        deck_id: str,
        generation_id: str | None = None,
        *,
        course_id: str | None = None,
    ) -> dict[str, Any] | None:
        directory = self._locate_deck(deck_id, course_id=course_id)
        if generation_id is None:
            generation_id = self.load_manifest(deck_id, course_id=directory.parent.name).get("active_generation_id")
        if not generation_id:
            return None
        self._validate_id(generation_id)
        path = directory / "working" / f"{generation_id}.json"
        if not path.exists():
            return None
        return GenerationWorkingSnapshot.model_validate(self._read_json(path)).model_dump(mode="json")

    def clear_active_generation(
        self,
        deck_id: str,
        generation_id: str,
        *,
        status: Literal["draft", "editing", "failed"] = "failed",
        course_id: str | None = None,
    ) -> dict[str, Any]:
        directory = self._locate_deck(deck_id, course_id=course_id)
        with self._lock(deck_id):
            manifest = self.load_manifest(deck_id, course_id=directory.parent.name)
            if manifest.get("active_generation_id") not in {None, generation_id}:
                raise PresentationRepositoryConflict("generation_id_mismatch")
            manifest["active_generation_id"] = None
            manifest["status"] = status
            manifest["updated_at"] = utc_now()
            self._atomic_write(directory / "manifest.json", manifest)
            return manifest

    def append_event(
        self,
        deck_id: str,
        event: PresentationEvent | dict[str, Any],
        *,
        course_id: str | None = None,
    ) -> dict[str, Any]:
        model = PresentationEvent.model_validate(self._object(event))
        if model.deck_id != deck_id:
            raise PresentationRepositoryConflict("event_deck_mismatch")
        self._validate_id(model.generation_id)
        directory = self._locate_deck(deck_id, course_id=course_id)
        path = directory / "streams" / f"{model.generation_id}.json"
        with self._lock(deck_id):
            stream = self._read_json(path) if path.exists() else {
                "schema_version": "presentation-event-stream/v1",
                "deck_id": deck_id,
                "generation_id": model.generation_id,
                "events": [],
            }
            events = stream.get("events") or []
            if stream.get("deck_id") != deck_id or stream.get("generation_id") != model.generation_id:
                raise PresentationRepositoryConflict("event_stream_identity_mismatch")
            if events:
                last = PresentationEvent.model_validate(events[-1])
                if model.event_seq <= last.event_seq:
                    existing = next((item for item in events if item.get("event_seq") == model.event_seq), None)
                    if existing == model.model_dump(mode="json"):
                        return deepcopy(existing)
                    raise PresentationRepositoryConflict("event_sequence_conflict")
                if model.event_seq != last.event_seq + 1:
                    raise PresentationRepositoryConflict("event_sequence_gap")
            elif model.event_seq != 1:
                raise PresentationRepositoryConflict("event_sequence_must_start_at_one")
            payload = model.model_dump(mode="json")
            events.append(payload)
            stream["events"] = events
            self._atomic_write(path, stream)
            if model.event_type in {"generation_complete", "error"}:
                manifest = self.load_manifest(deck_id, course_id=directory.parent.name)
                if manifest.get("active_generation_id") == model.generation_id:
                    manifest["active_generation_id"] = None
                    if model.event_type == "generation_complete":
                        manifest["status"] = "editing"
                    elif manifest.get("active_revision_id"):
                        manifest["status"] = "editing"
                    else:
                        manifest["status"] = "failed"
                    manifest["updated_at"] = utc_now()
                    self._atomic_write(directory / "manifest.json", manifest)
            return payload

    def replay_events(
        self,
        deck_id: str,
        generation_id: str,
        after_seq: int = 0,
        *,
        course_id: str | None = None,
    ) -> list[dict[str, Any]]:
        self._validate_id(generation_id)
        directory = self._locate_deck(deck_id, course_id=course_id)
        path = directory / "streams" / f"{generation_id}.json"
        if not path.exists():
            return []
        stream = self._read_json(path)
        if stream.get("deck_id") != deck_id or stream.get("generation_id") != generation_id:
            raise PresentationRepositoryConflict("event_stream_identity_mismatch")
        return [
            PresentationEvent.model_validate(item).model_dump(mode="json")
            for item in stream.get("events") or []
            if int(item.get("event_seq") or 0) > max(0, int(after_seq))
        ]

    # ------------------------------------------------------------------
    # Immutable revisions and edit records
    # ------------------------------------------------------------------

    def append_revision(
        self,
        deck_id: str,
        revision: DeckRevision | dict[str, Any],
        *,
        expected_revision_id: str | None = None,
        command_id: str | None = None,
        command_operation: str | None = None,
        command_metadata: dict[str, Any] | None = None,
        course_id: str | None = None,
        activate: bool = True,
    ) -> dict[str, Any]:
        model = DeckRevision.model_validate(self._object(revision))
        if model.deck_id != deck_id:
            raise PresentationRepositoryConflict("revision_deck_mismatch")
        directory = self._locate_deck(deck_id, course_id=course_id)
        operation = str(command_operation or "append_revision")
        metadata = deepcopy(command_metadata or {})
        metadata.setdefault("expected_revision_id", expected_revision_id)
        revision_intent = model.model_dump(mode="json")
        revision_intent.pop("revision_id", None)
        revision_intent.pop("created_at", None)
        command_fingerprint = self._idempotency_fingerprint({
            "operation": operation,
            "deck_id": deck_id,
            "expected_revision_id": expected_revision_id,
            "activate": activate,
            "metadata": metadata,
            "revision": revision_intent,
        })
        with self._lock(deck_id):
            if command_id:
                existing = self.get_command_receipt(
                    deck_id,
                    command_id,
                    course_id=directory.parent.name,
                    operation=operation,
                    fingerprint_payload={"fingerprint": command_fingerprint},
                )
                if existing is not None:
                    return existing
            manifest = self.load_manifest(deck_id, course_id=directory.parent.name)
            self._check_revision(manifest, expected_revision_id)
            if model.source_snapshot_id != manifest["source_ref"]["source_snapshot_id"]:
                raise PresentationRepositoryConflict("revision_source_snapshot_mismatch")
            if model.parent_revision_id:
                self.get_revision(deck_id, model.parent_revision_id, course_id=directory.parent.name)
            self._validate_id(model.revision_id)
            path = directory / "revisions" / f"{model.revision_id}.json"
            payload = model.model_dump(mode="json")
            if path.exists():
                if self._read_json(path) != payload:
                    raise PresentationRepositoryConflict("immutable_revision_conflict")
            else:
                self._atomic_write(path, payload)
            if activate:
                manifest["active_revision_id"] = model.revision_id
                manifest["active_generation_id"] = None
                manifest["status"] = "editing"
                manifest["updated_at"] = utc_now()
                self._atomic_write(directory / "manifest.json", manifest)
            receipt = {
                "schema_version": "presentation-revision-receipt/v2",
                "operation": operation,
                "command_id": command_id,
                "command_fingerprint": command_fingerprint,
                "deck_id": deck_id,
                "revision_id": model.revision_id,
                "active_revision_id": manifest.get("active_revision_id"),
                "expected_revision_id": expected_revision_id,
                "created_at": utc_now(),
            }
            for key, value in metadata.items():
                if key not in receipt:
                    receipt[key] = deepcopy(value)
            if command_id:
                self.save_command_receipt(
                    deck_id,
                    command_id,
                    receipt,
                    course_id=directory.parent.name,
                    operation=operation,
                    fingerprint_payload={"fingerprint": command_fingerprint},
                )
            return receipt

    def get_revision(
        self,
        deck_id: str,
        revision_id: str | None = None,
        *,
        course_id: str | None = None,
    ) -> dict[str, Any]:
        directory = self._locate_deck(deck_id, course_id=course_id)
        if revision_id is None:
            revision_id = self.load_manifest(deck_id, course_id=directory.parent.name).get("active_revision_id")
        if not revision_id:
            raise KeyError(f"Deck {deck_id} has no active revision")
        self._validate_id(revision_id)
        path = directory / "revisions" / f"{revision_id}.json"
        if not path.exists():
            raise KeyError(f"Unknown presentation revision: {revision_id}")
        return DeckRevision.model_validate(self._read_json(path)).model_dump(mode="json")

    def restore_revision(
        self,
        deck_id: str,
        source_revision_id: str,
        *,
        expected_revision_id: str,
        command_id: str,
        course_id: str | None = None,
    ) -> dict[str, Any]:
        directory = self._locate_deck(deck_id, course_id=course_id)
        with self._lock(deck_id):
            source = self.get_revision(deck_id, source_revision_id, course_id=directory.parent.name)
            revision_id = f"rev_{uuid.uuid4().hex}"
            restored = deepcopy(source)
            restored.update({
                "revision_id": revision_id,
                "parent_revision_id": expected_revision_id,
                "reason": "restore",
                "created_at": utc_now(),
                "created_by": "user",
            })
            return self.append_revision(
                deck_id,
                restored,
                expected_revision_id=expected_revision_id,
                command_id=command_id,
                command_operation="restore_revision",
                command_metadata={
                    "restored_from_revision_id": source_revision_id,
                    "expected_revision_id": expected_revision_id,
                },
                course_id=directory.parent.name,
            )

    def save_proposal(
        self,
        deck_id: str,
        proposal: DeckProposal | dict[str, Any],
        *,
        course_id: str | None = None,
    ) -> dict[str, Any]:
        model = DeckProposal.model_validate(self._object(proposal))
        if model.deck_id != deck_id:
            raise PresentationRepositoryConflict("proposal_deck_mismatch")
        directory = self._locate_deck(deck_id, course_id=course_id)
        request_intent = {
            "operation": "create_proposal",
            "deck_id": deck_id,
            "base_revision_id": model.base_revision_id,
            "scope": model.scope,
            "slide_ids": model.slide_ids,
            "prompt": model.prompt,
        }
        with self._lock(deck_id):
            repeated = self.get_request_receipt(
                deck_id,
                model.request_id,
                course_id=directory.parent.name,
                operation="create_proposal",
                fingerprint_payload=request_intent,
            )
            if repeated:
                existing = self.get_proposal(
                    deck_id, str(repeated["proposal_id"]), course_id=directory.parent.name
                )
                if existing.get("proposal_id") != model.proposal_id:
                    return existing
                if existing == model.model_dump(mode="json"):
                    return existing
            manifest = self.load_manifest(deck_id, course_id=directory.parent.name)
            if model.status == "proposed" and model.base_revision_id != manifest.get("active_revision_id"):
                raise StaleRevisionConflict("stale_proposal_base")
            self._validate_id(model.proposal_id)
            payload = model.model_dump(mode="json")
            path = directory / "proposals" / f"{model.proposal_id}.json"
            if path.exists():
                current = self._read_json(path)
                if current != payload:
                    current_contract = {key: value for key, value in current.items() if key != "status"}
                    next_contract = {key: value for key, value in payload.items() if key != "status"}
                    allowed_transition = current.get("status") == "proposed" and payload.get("status") in {
                        "applied", "cancelled", "stale"
                    }
                    if current_contract != next_contract or not allowed_transition:
                        raise PresentationRepositoryConflict("immutable_proposal_conflict")
                    self._atomic_write(path, payload)
            else:
                self._atomic_write(path, payload)
            self.save_request_receipt(deck_id, model.request_id, {
                "schema_version": "presentation-request-receipt/v2",
                "operation": "create_proposal",
                "request_id": model.request_id,
                "deck_id": deck_id,
                "proposal_id": model.proposal_id,
                "created_at": utc_now(),
            }, course_id=directory.parent.name, operation="create_proposal", fingerprint_payload=request_intent)
            return payload

    def get_proposal(
        self,
        deck_id: str,
        proposal_id: str,
        *,
        course_id: str | None = None,
    ) -> dict[str, Any]:
        self._validate_id(proposal_id)
        directory = self._locate_deck(deck_id, course_id=course_id)
        path = directory / "proposals" / f"{proposal_id}.json"
        if not path.exists():
            raise KeyError(f"Unknown presentation proposal: {proposal_id}")
        return DeckProposal.model_validate(self._read_json(path)).model_dump(mode="json")

    def update_proposal_status(
        self,
        deck_id: str,
        proposal_id: str,
        status: Literal["proposed", "applied", "cancelled", "stale"],
        *,
        course_id: str | None = None,
    ) -> dict[str, Any]:
        """Change only proposal lifecycle state; proposal patches remain immutable."""
        directory = self._locate_deck(deck_id, course_id=course_id)
        with self._lock(deck_id):
            proposal = self.get_proposal(deck_id, proposal_id, course_id=directory.parent.name)
            proposal["status"] = status
            payload = DeckProposal.model_validate(proposal).model_dump(mode="json")
            self._atomic_write(directory / "proposals" / f"{proposal_id}.json", payload)
            return payload

    def save_quality(
        self,
        deck_id: str,
        report: QualityReport | dict[str, Any],
        *,
        expected_revision_id: str | None = None,
        course_id: str | None = None,
        activate: bool = True,
    ) -> dict[str, Any]:
        model = QualityReport.model_validate(self._object(report))
        if model.deck_id != deck_id:
            raise PresentationRepositoryConflict("quality_deck_mismatch")
        directory = self._locate_deck(deck_id, course_id=course_id)
        with self._lock(deck_id):
            manifest = self.load_manifest(deck_id, course_id=directory.parent.name)
            self._check_revision(manifest, expected_revision_id)
            if model.source_snapshot_id != manifest["source_ref"]["source_snapshot_id"]:
                raise PresentationRepositoryConflict("quality_source_snapshot_mismatch")
            self._validate_id(model.report_id)
            path = directory / "quality" / f"{model.report_id}.json"
            payload = model.model_dump(mode="json")
            if path.exists():
                current = self._read_json(path)
                if current != payload:
                    immutable_keys = (
                        "report_id", "deck_id", "revision_id", "source_snapshot_id",
                        "checked_at", "render_measurement",
                    )
                    same_identity = all(current.get(key) == payload.get(key) for key in immutable_keys)
                    issue_prefix = payload.get("issues", [])[: len(current.get("issues", []))] == current.get("issues", [])
                    allowed_block = payload.get("status") == "blocked" and same_identity and issue_prefix
                    if not allowed_block:
                        raise PresentationRepositoryConflict("immutable_quality_report_conflict")
                    self._atomic_write(path, payload)
            else:
                self._atomic_write(path, payload)
            if activate:
                manifest["latest_quality_report_id"] = model.report_id
                if model.status == "blocked":
                    manifest["status"] = "quality_blocked"
                manifest["updated_at"] = utc_now()
                self._atomic_write(directory / "manifest.json", manifest)
            return payload

    def get_quality(
        self,
        deck_id: str,
        report_id: str | None = None,
        *,
        course_id: str | None = None,
    ) -> dict[str, Any]:
        directory = self._locate_deck(deck_id, course_id=course_id)
        if report_id is None:
            report_id = self.load_manifest(deck_id, course_id=directory.parent.name).get("latest_quality_report_id")
        if not report_id:
            raise KeyError(f"Deck {deck_id} has no quality report")
        self._validate_id(report_id)
        path = directory / "quality" / f"{report_id}.json"
        if not path.exists():
            raise KeyError(f"Unknown presentation quality report: {report_id}")
        return QualityReport.model_validate(self._read_json(path)).model_dump(mode="json")

    # ------------------------------------------------------------------
    # Artifact receipts and safe file resolution
    # ------------------------------------------------------------------

    def artifact_directory(
        self,
        deck_id: str,
        artifact_id: str,
        *,
        course_id: str | None = None,
    ) -> Path:
        self._validate_id(artifact_id)
        directory = self._locate_deck(deck_id, course_id=course_id) / "artifacts" / artifact_id
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def save_artifact(
        self,
        deck_id: str,
        receipt: ArtifactReceipt | dict[str, Any],
        *,
        expected_revision_id: str | None = None,
        command_id: str | None = None,
        course_id: str | None = None,
    ) -> dict[str, Any]:
        model = ArtifactReceipt.model_validate(self._object(receipt))
        if model.deck_id != deck_id:
            raise PresentationRepositoryConflict("artifact_deck_mismatch")
        directory = self._locate_deck(deck_id, course_id=course_id)
        command_intent = {
            "operation": "finalize_presentation",
            "deck_id": deck_id,
            "expected_revision_id": expected_revision_id or model.revision_id,
        }
        with self._lock(deck_id):
            if command_id:
                repeated = self.get_command_receipt(
                    deck_id,
                    command_id,
                    course_id=directory.parent.name,
                    operation="finalize_presentation",
                    fingerprint_payload=command_intent,
                )
                if repeated:
                    return repeated
            manifest = self.load_manifest(deck_id, course_id=directory.parent.name)
            self._check_revision(manifest, expected_revision_id or model.revision_id)
            if model.revision_id != manifest.get("active_revision_id"):
                raise StaleRevisionConflict("artifact_revision_is_not_active")
            if model.source_snapshot_id != manifest["source_ref"]["source_snapshot_id"]:
                raise PresentationRepositoryConflict("artifact_source_snapshot_mismatch")
            quality = self.get_quality(deck_id, model.quality_report_id, course_id=directory.parent.name)
            if quality.get("status") != "passed" or quality.get("revision_id") != model.revision_id:
                raise PresentationRepositoryConflict("artifact_quality_report_not_passed")
            normalized = self._normalize_artifact_receipt(directory, model)
            artifact_dir = directory / "artifacts" / model.artifact_id
            for kind, digest_field in (("html", "html_sha256"), ("pptx", "pptx_sha256")):
                path = artifact_dir / _ARTIFACT_NAMES[kind]
                if not path.is_file():
                    raise ArtifactAccessError(f"artifact_{kind}_missing")
                if self._file_sha256(path) != normalized[digest_field]:
                    raise ArtifactAccessError(f"artifact_{kind}_checksum_mismatch")
            self._atomic_write(artifact_dir / "receipt.json", normalized)
            manifest["latest_artifact_id"] = model.artifact_id
            manifest["status"] = "exported"
            manifest["updated_at"] = utc_now()
            self._atomic_write(directory / "manifest.json", manifest)
            result = {
                **normalized,
                "command_id": command_id,
                "operation": "finalize_presentation",
                "expected_revision_id": expected_revision_id or model.revision_id,
            }
            if command_id:
                result = self.save_command_receipt(
                    deck_id,
                    command_id,
                    result,
                    course_id=directory.parent.name,
                    operation="finalize_presentation",
                    fingerprint_payload=command_intent,
                )
            return result

    def get_artifact(
        self,
        artifact_id: str,
        *,
        deck_id: str | None = None,
        course_id: str | None = None,
    ) -> dict[str, Any]:
        directory = self._locate_artifact(artifact_id, deck_id=deck_id, course_id=course_id)
        receipt = ArtifactReceipt.model_validate(self._read_json(directory / "receipt.json")).model_dump(mode="json")
        manifest = self.load_manifest(receipt["deck_id"], course_id=directory.parents[2].name)
        receipt["stale"] = receipt["revision_id"] != manifest.get("active_revision_id")
        return receipt

    def resolve_artifact_file(
        self,
        artifact_id: str,
        kind: Literal["html", "pptx"],
        *,
        deck_id: str | None = None,
        course_id: str | None = None,
    ) -> Path:
        if kind not in _ARTIFACT_NAMES:
            raise ArtifactAccessError("unknown_artifact_kind")
        artifact_dir = self._locate_artifact(artifact_id, deck_id=deck_id, course_id=course_id)
        receipt = self.get_artifact(artifact_id, deck_id=deck_id, course_id=course_id)
        if receipt.get("stale"):
            raise ArtifactAccessError("artifact_stale")
        raw = receipt[f"{kind}_path"]
        path = self._resolve_receipt_path(artifact_dir.parents[1], artifact_dir, raw)
        expected = (artifact_dir / _ARTIFACT_NAMES[kind]).resolve()
        if path != expected or not path.is_file():
            raise ArtifactAccessError("artifact_path_invalid")
        if self._file_sha256(path) != receipt[f"{kind}_sha256"]:
            raise ArtifactAccessError("artifact_checksum_mismatch")
        return path

    # ------------------------------------------------------------------
    # Request and command idempotency receipts
    # ------------------------------------------------------------------

    def get_request_receipt(
        self,
        deck_id: str,
        request_id: str,
        *,
        course_id: str | None = None,
        operation: str | None = None,
        fingerprint_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        receipt = self._get_operation_receipt(deck_id, "requests", request_id, course_id=course_id)
        if receipt is not None and operation is not None:
            self._assert_receipt_intent(
                receipt,
                operation=operation,
                fingerprint=self._fingerprint_argument(fingerprint_payload),
                fingerprint_key="request_fingerprint",
            )
        return receipt

    def save_request_receipt(
        self,
        deck_id: str,
        request_id: str,
        receipt: dict[str, Any],
        *,
        course_id: str | None = None,
        overwrite: bool = False,
        operation: str | None = None,
        fingerprint_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = deepcopy(receipt)
        effective_operation = str(operation or payload.get("operation") or payload.get("kind") or "request")
        fingerprint = str(payload.get("request_fingerprint") or "") or self._fingerprint_argument(
            fingerprint_payload or self._default_receipt_intent(payload, effective_operation)
        )
        payload["operation"] = effective_operation
        payload["request_fingerprint"] = fingerprint
        return self._save_operation_receipt(
            deck_id, "requests", "request_id", request_id, payload,
            course_id=course_id, overwrite=overwrite,
            fingerprint_key="request_fingerprint",
        )

    def get_command_receipt(
        self,
        deck_id: str,
        command_id: str,
        *,
        course_id: str | None = None,
        operation: str | None = None,
        fingerprint_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        receipt = self._get_operation_receipt(deck_id, "commands", command_id, course_id=course_id)
        if receipt is not None and operation is not None:
            self._assert_receipt_intent(
                receipt,
                operation=operation,
                fingerprint=self._fingerprint_argument(fingerprint_payload),
                fingerprint_key="command_fingerprint",
            )
        return receipt

    def save_command_receipt(
        self,
        deck_id: str,
        command_id: str,
        receipt: dict[str, Any],
        *,
        course_id: str | None = None,
        overwrite: bool = False,
        operation: str | None = None,
        fingerprint_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = deepcopy(receipt)
        effective_operation = str(operation or payload.get("operation") or "command")
        fingerprint = str(payload.get("command_fingerprint") or "") or self._fingerprint_argument(
            fingerprint_payload or self._default_receipt_intent(payload, effective_operation)
        )
        payload["operation"] = effective_operation
        payload["command_fingerprint"] = fingerprint
        return self._save_operation_receipt(
            deck_id, "commands", "command_id", command_id, payload,
            course_id=course_id, overwrite=overwrite,
            fingerprint_key="command_fingerprint",
        )

    # ------------------------------------------------------------------
    # Internal validation and filesystem helpers
    # ------------------------------------------------------------------

    def _get_operation_receipt(
        self,
        deck_id: str,
        bucket: str,
        raw_id: str,
        *,
        course_id: str | None,
    ) -> dict[str, Any] | None:
        directory = self._locate_deck(deck_id, course_id=course_id)
        path = directory / "receipts" / bucket / self._receipt_filename(raw_id)
        if not path.exists():
            return None
        receipt = self._read_json(path)
        key = "request_id" if bucket == "requests" else "command_id"
        if receipt.get(key) != raw_id:
            raise PresentationRepositoryConflict(f"{key}_receipt_mismatch")
        return receipt

    def _save_operation_receipt(
        self,
        deck_id: str,
        bucket: str,
        id_key: str,
        raw_id: str,
        receipt: dict[str, Any],
        *,
        course_id: str | None,
        overwrite: bool,
        fingerprint_key: str,
    ) -> dict[str, Any]:
        if not raw_id:
            raise ValueError(f"{id_key} is required")
        directory = self._locate_deck(deck_id, course_id=course_id)
        payload = deepcopy(receipt)
        payload[id_key] = raw_id
        payload.setdefault("deck_id", deck_id)
        path = directory / "receipts" / bucket / self._receipt_filename(raw_id)
        with self._lock(deck_id):
            if path.exists():
                current = self._read_json(path)
                if current.get(id_key) != raw_id:
                    raise PresentationRepositoryConflict(f"{id_key}_receipt_mismatch")
                self._assert_receipt_intent(
                    current,
                    operation=str(payload.get("operation") or ""),
                    fingerprint=str(payload.get(fingerprint_key) or ""),
                    fingerprint_key=fingerprint_key,
                )
                if not overwrite or current == payload:
                    return current
            self._atomic_write(path, payload)
            return payload

    @staticmethod
    def _assert_receipt_intent(
        receipt: dict[str, Any],
        *,
        operation: str,
        fingerprint: str,
        fingerprint_key: str,
    ) -> None:
        current_operation = str(receipt.get("operation") or receipt.get("kind") or "")
        current_fingerprint = str(receipt.get(fingerprint_key) or "")
        if current_operation != operation or (fingerprint and current_fingerprint != fingerprint):
            raise IdempotencyKeyReuseConflict(
                f"idempotency_key_reused: stored={current_operation or 'unknown'}, requested={operation}"
            )

    @classmethod
    def _fingerprint_argument(cls, payload: dict[str, Any] | None) -> str:
        if not payload:
            return ""
        supplied = payload.get("fingerprint") if len(payload) == 1 else None
        if isinstance(supplied, str) and supplied.startswith("sha256:"):
            return supplied
        return cls._idempotency_fingerprint(payload)

    @staticmethod
    def _default_receipt_intent(receipt: dict[str, Any], operation: str) -> dict[str, Any]:
        output_or_volatile = {
            "schema_version", "request_id", "command_id", "created_at",
            "request_fingerprint", "command_fingerprint", "generation_id",
            "proposal_id", "artifact_id", "revision_id", "active_revision_id",
            "html_path", "pptx_path", "html_sha256", "pptx_sha256",
        }
        return {
            "operation": operation,
            "intent": {
                key: deepcopy(value)
                for key, value in receipt.items()
                if key not in output_or_volatile and key not in {"operation", "kind"}
            },
        }

    @staticmethod
    def _idempotency_fingerprint(payload: dict[str, Any]) -> str:
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
        return f"sha256:{hashlib.sha256(raw.encode('utf-8')).hexdigest()}"

    def _validate_source_snapshot(
        self, deck: PresentationDeck, source_snapshot: dict[str, Any]
    ) -> dict[str, Any]:
        snapshot = deepcopy(source_snapshot)
        if not isinstance(snapshot, dict):
            raise ValueError("source snapshot must be an object")
        snapshot_id = str(snapshot.get("source_snapshot_id") or "")
        digest = str(snapshot.get("source_snapshot_sha256") or "")
        if snapshot_id != deck.source_ref.source_snapshot_id:
            raise PresentationRepositoryConflict("source_snapshot_id_mismatch")
        expected = self._source_snapshot_sha256(snapshot)
        if digest != expected or digest != deck.source_ref.source_snapshot_sha256:
            raise PresentationRepositoryConflict("source_snapshot_digest_mismatch")
        if str(snapshot.get("course_id") or "") != deck.course_id:
            raise PresentationRepositoryConflict("source_snapshot_course_mismatch")
        return snapshot

    def _assert_manifest_pointers(self, directory: Path, manifest: dict[str, Any]) -> None:
        pointers = (
            (manifest.get("active_revision_id"), directory / "revisions", ".json"),
            (manifest.get("active_generation_id"), directory / "working", ".json"),
            (manifest.get("latest_quality_report_id"), directory / "quality", ".json"),
        )
        for identifier, parent, suffix in pointers:
            if identifier and not (parent / f"{identifier}{suffix}").is_file():
                raise PresentationRepositoryConflict(f"manifest_pointer_missing:{identifier}")
        artifact_id = manifest.get("latest_artifact_id")
        if artifact_id and not (directory / "artifacts" / artifact_id / "receipt.json").is_file():
            raise PresentationRepositoryConflict(f"manifest_pointer_missing:{artifact_id}")

    @staticmethod
    def _check_revision(manifest: dict[str, Any], expected_revision_id: str | None) -> None:
        if expected_revision_id is not None and manifest.get("active_revision_id") != expected_revision_id:
            raise StaleRevisionConflict(
                f"stale_revision: expected {expected_revision_id}, active {manifest.get('active_revision_id')}"
            )

    def _normalize_artifact_receipt(
        self, deck_dir: Path, receipt: ArtifactReceipt
    ) -> dict[str, Any]:
        self._validate_id(receipt.artifact_id)
        artifact_dir = (deck_dir / "artifacts" / receipt.artifact_id).resolve()
        for kind in _ARTIFACT_NAMES:
            self._resolve_receipt_path(deck_dir, artifact_dir, getattr(receipt, f"{kind}_path"))
        payload = receipt.model_dump(mode="json")
        payload["html_path"] = f"artifacts/{receipt.artifact_id}/deck.html"
        payload["pptx_path"] = f"artifacts/{receipt.artifact_id}/deck.pptx"
        payload["stale"] = False
        return payload

    @staticmethod
    def _resolve_receipt_path(deck_dir: Path, artifact_dir: Path, raw: str) -> Path:
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = deck_dir / candidate
        resolved = candidate.resolve()
        if resolved.parent != artifact_dir.resolve():
            raise ArtifactAccessError("artifact_path_outside_receipt_root")
        return resolved

    def _locate_artifact(
        self,
        artifact_id: str,
        *,
        deck_id: str | None,
        course_id: str | None,
    ) -> Path:
        self._validate_id(artifact_id)
        if deck_id:
            path = self._locate_deck(deck_id, course_id=course_id) / "artifacts" / artifact_id
            self._assert_within(path, self.root_dir)
            if (path / "receipt.json").is_file():
                return path
            raise KeyError(f"Unknown presentation artifact: {artifact_id}")
        matches: list[Path] = []
        course_dirs = [self.root_dir / course_id] if course_id else list(self.root_dir.iterdir())
        for course_dir in course_dirs:
            if not course_dir.is_dir() or not _SAFE_ID.match(course_dir.name):
                continue
            for candidate_deck in course_dir.iterdir():
                path = candidate_deck / "artifacts" / artifact_id
                self._assert_within(path, self.root_dir)
                if candidate_deck.is_dir() and (path / "receipt.json").is_file():
                    matches.append(path)
        if len(matches) != 1:
            if not matches:
                raise KeyError(f"Unknown presentation artifact: {artifact_id}")
            raise PresentationRepositoryConflict("ambiguous_artifact_id")
        return matches[0]

    def _locate_deck(self, deck_id: str, *, course_id: str | None = None) -> Path:
        self._validate_id(deck_id)
        if course_id is not None:
            self._validate_id(course_id)
            path = self.root_dir / course_id / deck_id
            self._assert_within(path, self.root_dir)
            if (path / "manifest.json").is_file():
                return path
            raise KeyError(f"Unknown presentation deck: {deck_id}")
        matches: list[Path] = []
        for course_dir in self.root_dir.iterdir():
            if not course_dir.is_dir() or not _SAFE_ID.match(course_dir.name):
                continue
            path = course_dir / deck_id
            self._assert_within(path, self.root_dir)
            if (path / "manifest.json").is_file():
                matches.append(path)
        if len(matches) != 1:
            if not matches:
                raise KeyError(f"Unknown presentation deck: {deck_id}")
            raise PresentationRepositoryConflict("ambiguous_deck_id")
        return matches[0]

    def _deck_dir(self, course_id: str, deck_id: str, *, create: bool) -> Path:
        self._validate_id(course_id)
        self._validate_id(deck_id)
        directory = self.root_dir / course_id / deck_id
        self._assert_within(directory, self.root_dir)
        if create:
            directory.mkdir(parents=True, exist_ok=True)
        return directory

    def _course_request_receipt(self, course_id: str, request_id: str | None) -> Path:
        assert request_id is not None
        return self.root_dir / course_id / "_requests" / self._receipt_filename(request_id)

    @staticmethod
    def _assert_within(path: Path, root: Path) -> None:
        try:
            path.resolve().relative_to(root.resolve())
        except ValueError as exc:
            raise ValueError("Repository path escapes configured root") from exc

    @staticmethod
    def _receipt_filename(raw_id: str) -> str:
        if not raw_id:
            raise ValueError("idempotency id is required")
        return f"{hashlib.sha256(raw_id.encode('utf-8')).hexdigest()}.json"

    def _lock(self, deck_id: str) -> threading.RLock:
        self._validate_id(deck_id)
        with self._locks_guard:
            return self._locks.setdefault(deck_id, threading.RLock())

    @staticmethod
    def _validate_id(value: str) -> None:
        if not value or not _SAFE_ID.match(str(value)):
            raise ValueError("Invalid repository identifier")

    @staticmethod
    def _object(value: Any) -> dict[str, Any]:
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")
        if not isinstance(value, dict):
            raise TypeError("Expected a model or object")
        return deepcopy(value)

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        with path.open(encoding="utf-8") as handle:
            value = json.load(handle)
        if not isinstance(value, dict):
            raise ValueError(f"Expected object in {path}")
        return value

    @staticmethod
    def _atomic_write(path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            with temp.open("w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, path)
        finally:
            if temp.exists():
                temp.unlink()

    @staticmethod
    def _source_snapshot_sha256(snapshot: dict[str, Any]) -> str:
        payload = deepcopy(snapshot)
        payload.pop("source_snapshot_sha256", None)
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
        return f"sha256:{hashlib.sha256(raw.encode('utf-8')).hexdigest()}"

    @staticmethod
    def _file_sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return f"sha256:{digest.hexdigest()}"


presentation_repository = PresentationRepository()


__all__ = [
    "ArtifactAccessError",
    "IdempotencyKeyReuseConflict",
    "PresentationRepository",
    "PresentationRepositoryConflict",
    "StaleRevisionConflict",
    "presentation_repository",
]
