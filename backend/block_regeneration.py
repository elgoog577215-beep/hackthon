"""Candidate-first regeneration for canonical course blocks."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import threading
from typing import Any, Callable
import uuid

from change_proposals import ChangeProposalRepository, create_authoring_change
from course_commands import CourseCommandService
from course_document import CourseBlock, stable_hash
from course_repository import CourseDocumentConflict, CourseDocumentRepository
from learning_events import record_learning_event, summarize_text
from storage import DATA_DIR


BLOCK_REGENERATION_SCHEMA = "block_regeneration_candidate_v1"
BLOCK_REGENERATION_PROCESS_ID = uuid.uuid4().hex
PERSONALIZATION_RELATED_TIMEOUT_SECONDS = 8.0
PERSONALIZATION_IDEMPOTENCY_WAIT_SECONDS = 30.0
_PERSONALIZATION_REQUEST_TASKS: dict[
    tuple[str, str], tuple[str, asyncio.Task[dict[str, Any]]]
] = {}
_PERSONALIZATION_REQUEST_TASKS_GUARD = threading.Lock()
_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]+$")
_CONTENT_KEYS = {"markdown", "text"}
_ERROR_MARKERS = (
    "[error:",
    "生成失败",
    "无法生成",
    "模型暂时不可用",
    "i cannot comply",
    "i can't comply",
)
_PERSONALIZATION_ROLE_PRIORITY = {
    "simplify": (
        "prerequisite", "misconception", "example", "concept", "reasoning",
        "summary", "checkpoint", "remediation",
    ),
    "expand": (
        "reasoning", "example", "application", "counterexample", "transfer",
        "concept", "summary", "checkpoint",
    ),
    "custom": (
        "concept", "reasoning", "example", "application", "misconception",
        "counterexample", "summary", "transfer",
    ),
}


class BlockRegenerationNotFound(KeyError):
    pass


class BlockRegenerationConflict(RuntimeError):
    def __init__(self, message: str, *, candidate: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.candidate = deepcopy(candidate) if candidate else None


class PersonalizationGenerationInProgress(RuntimeError):
    """A matching personalization request is still producing its proposal."""


class BlockRegenerationCandidateRepository:
    def __init__(self, root_dir: str | Path | None = None) -> None:
        self.root_dir = Path(root_dir or Path(DATA_DIR) / "block_regeneration_candidates")
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, threading.RLock] = {}
        self._locks_guard = threading.Lock()

    @staticmethod
    def candidate_id_for(course_id: str, block_id: str, request_id: str) -> str:
        if not course_id or not block_id or not request_id:
            raise ValueError("Course, block, and request identifiers are required")
        return stable_hash(
            {"course_id": course_id, "block_id": block_id, "request_id": request_id},
            prefix="brc_",
        )

    def load(self, candidate_id: str) -> dict[str, Any]:
        self._validate_id(candidate_id)
        path = self._path(candidate_id)
        if not path.exists():
            raise BlockRegenerationNotFound(candidate_id)
        return self._read(path)

    def load_optional(self, candidate_id: str) -> dict[str, Any] | None:
        try:
            return self.load(candidate_id)
        except BlockRegenerationNotFound:
            return None

    def create(self, candidate: dict[str, Any]) -> dict[str, Any]:
        value, _created = self.create_once(candidate)
        return value

    def create_once(self, candidate: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        candidate_id = str(candidate.get("candidate_id") or "")
        self._validate_id(candidate_id)
        with self._lock(candidate_id):
            existing = self.load_optional(candidate_id)
            if existing:
                return existing, False
            value = deepcopy(candidate)
            value["schema_version"] = BLOCK_REGENERATION_SCHEMA
            self._atomic_write(self._path(candidate_id), value)
            return deepcopy(value), True

    def update(
        self,
        candidate_id: str,
        updater: Callable[[dict[str, Any]], dict[str, Any] | None],
    ) -> dict[str, Any]:
        self._validate_id(candidate_id)
        with self._lock(candidate_id):
            current = self.load(candidate_id)
            updated = updater(deepcopy(current))
            value = current if updated is None else updated
            if not isinstance(value, dict):
                raise BlockRegenerationConflict("Candidate updater returned invalid data")
            value["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._atomic_write(self._path(candidate_id), value)
            return deepcopy(value)

    def update_if(
        self,
        candidate_id: str,
        predicate: Callable[[dict[str, Any]], bool],
        updater: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> tuple[dict[str, Any], bool]:
        self._validate_id(candidate_id)
        with self._lock(candidate_id):
            current = self.load(candidate_id)
            if not predicate(deepcopy(current)):
                return current, False
            value = updater(deepcopy(current))
            if not isinstance(value, dict):
                raise BlockRegenerationConflict("Candidate updater returned invalid data")
            value["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._atomic_write(self._path(candidate_id), value)
            return deepcopy(value), True

    def find_latest(
        self,
        course_id: str,
        block_id: str,
        *,
        expected_document_revision: str | None = None,
        expected_block_revision: str | None = None,
    ) -> dict[str, Any] | None:
        matches: list[dict[str, Any]] = []
        for path in self.root_dir.glob("brc_*.json"):
            candidate = self._read(path)
            if candidate.get("course_id") != course_id or candidate.get("block_id") != block_id:
                continue
            if (
                expected_document_revision
                and candidate.get("expected_document_revision") != expected_document_revision
            ):
                continue
            if expected_block_revision and candidate.get("expected_block_revision") != expected_block_revision:
                continue
            matches.append(candidate)
        if not matches:
            return None
        matches.sort(
            key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""),
            reverse=True,
        )
        return deepcopy(matches[0])

    def _path(self, candidate_id: str) -> Path:
        return self.root_dir / f"{candidate_id}.json"

    def _lock(self, candidate_id: str) -> threading.RLock:
        with self._locks_guard:
            return self._locks.setdefault(candidate_id, threading.RLock())

    @staticmethod
    def _validate_id(value: str) -> None:
        if not value or not _SAFE_ID.match(value):
            raise ValueError("Invalid block regeneration candidate identifier")

    @staticmethod
    def _read(path: Path) -> dict[str, Any]:
        with path.open(encoding="utf-8") as handle:
            value = json.load(handle)
        if not isinstance(value, dict):
            raise BlockRegenerationConflict("Block regeneration candidate must contain an object")
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


class BlockRegenerationService:
    def __init__(
        self,
        course_repository: CourseDocumentRepository,
        candidate_repository: BlockRegenerationCandidateRepository,
        *,
        generator: Any | None = None,
    ) -> None:
        self.course_repository = course_repository
        self.candidate_repository = candidate_repository
        self.command_service = CourseCommandService(course_repository)
        self.generator = generator

    async def create_candidate(
        self,
        course_id: str,
        block_id: str,
        *,
        request_id: str,
        expected_document_revision: str,
        expected_block_revision: str,
        instruction: str,
        action_type: str = "rewrite",
        user_id: str,
    ) -> dict[str, Any]:
        candidate_id = self.candidate_repository.candidate_id_for(course_id, block_id, request_id)
        instruction = instruction.strip() or "提升这段内容的准确性、清晰度和教学效果。"
        request_fingerprint = stable_hash(
            {
                "course_id": course_id,
                "block_id": block_id,
                "expected_document_revision": expected_document_revision,
                "expected_block_revision": expected_block_revision,
                "instruction": instruction,
                "action_type": action_type,
                "user_id": user_id,
            },
            prefix="brf_",
        )
        existing = self.candidate_repository.load_optional(candidate_id)
        if existing:
            self._require_matching_request(
                existing,
                request_fingerprint=request_fingerprint,
                instruction=instruction,
                action_type=action_type,
                expected_document_revision=expected_document_revision,
                expected_block_revision=expected_block_revision,
                user_id=user_id,
            )
            return self._recover_interrupted_candidate(existing)

        document, target, _section, _neighbors = self._generation_context(
            course_id,
            block_id,
            expected_document_revision=expected_document_revision,
            expected_block_revision=expected_block_revision,
        )
        original_payload = deepcopy(target.payload)
        now = datetime.now(timezone.utc).isoformat()
        run_id = uuid.uuid4().hex
        placeholder = {
            "schema_version": BLOCK_REGENERATION_SCHEMA,
            "candidate_id": candidate_id,
            "request_id": request_id,
            "course_id": course_id,
            "block_id": block_id,
            "section_id": target.section_id,
            "status": "generating",
            "action_type": action_type,
            "instruction": instruction,
            "request_fingerprint": request_fingerprint,
            "requested_by": user_id,
            "expected_document_revision": expected_document_revision,
            "expected_block_revision": expected_block_revision,
            "original_payload": original_payload,
            "proposed_block": {
                **target.model_dump(mode="json"),
                "payload": deepcopy(original_payload),
            },
            "quality_report": None,
            "attempts": [],
            "generation_owner": BLOCK_REGENERATION_PROCESS_ID,
            "generation_run_id": run_id,
            "generation_started_at": now,
            "generation_completed_at": None,
            "retry_count": 0,
            "retryable": False,
            "failure_code": None,
            "failure_reason": None,
            "created_at": now,
            "updated_at": now,
            "receipt": None,
        }
        candidate, created = self.candidate_repository.create_once(placeholder)
        if not created:
            self._require_matching_request(
                candidate,
                request_fingerprint=request_fingerprint,
                instruction=instruction,
                action_type=action_type,
                expected_document_revision=expected_document_revision,
                expected_block_revision=expected_block_revision,
                user_id=user_id,
            )
            return self._recover_interrupted_candidate(candidate)
        return await self._generate_candidate(candidate, user_id=user_id, run_id=run_id)

    def get_candidate(self, course_id: str, block_id: str, candidate_id: str) -> dict[str, Any]:
        candidate = self.candidate_repository.load(candidate_id)
        self._require_target(candidate, course_id, block_id)
        return self._recover_interrupted_candidate(candidate)

    def get_latest_candidate(
        self,
        course_id: str,
        block_id: str,
        *,
        expected_document_revision: str | None = None,
        expected_block_revision: str | None = None,
    ) -> dict[str, Any]:
        candidate = self.candidate_repository.find_latest(
            course_id,
            block_id,
            expected_document_revision=expected_document_revision,
            expected_block_revision=expected_block_revision,
        )
        if not candidate:
            raise BlockRegenerationNotFound(block_id)
        return self._recover_interrupted_candidate(candidate)

    async def retry_candidate(
        self,
        course_id: str,
        block_id: str,
        candidate_id: str,
        *,
        user_id: str,
    ) -> dict[str, Any]:
        candidate = self.get_candidate(course_id, block_id, candidate_id)
        if candidate.get("status") == "generating":
            return candidate
        if candidate.get("status") != "generation_failed":
            raise BlockRegenerationConflict(
                f"Candidate cannot be retried from status {candidate.get('status')}",
                candidate=candidate,
            )
        try:
            self._generation_context(
                course_id,
                block_id,
                expected_document_revision=str(candidate.get("expected_document_revision") or ""),
                expected_block_revision=str(candidate.get("expected_block_revision") or ""),
            )
        except (BlockRegenerationConflict, BlockRegenerationNotFound) as exc:
            stale = self.candidate_repository.update(candidate_id, lambda current: {
                **current,
                "status": "stale",
                "retryable": False,
                "failure_code": "revision_conflict",
                "failure_reason": str(exc),
            })
            raise BlockRegenerationConflict(str(exc), candidate=stale) from exc

        run_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        claimed, did_claim = self.candidate_repository.update_if(
            candidate_id,
            lambda current: current.get("status") == "generation_failed",
            lambda current: {
                **current,
                "status": "generating",
                "generation_owner": BLOCK_REGENERATION_PROCESS_ID,
                "generation_run_id": run_id,
                "generation_started_at": now,
                "generation_completed_at": None,
                "retry_count": int(current.get("retry_count") or 0) + 1,
                "retryable": False,
                "failure_code": None,
                "failure_reason": None,
            },
        )
        if not did_claim:
            if claimed.get("status") == "generating":
                return claimed
            raise BlockRegenerationConflict(
                f"Candidate cannot be retried from status {claimed.get('status')}",
                candidate=claimed,
            )
        return await self._generate_candidate(claimed, user_id=user_id, run_id=run_id)

    async def _generate_candidate(
        self,
        candidate: dict[str, Any],
        *,
        user_id: str,
        run_id: str,
    ) -> dict[str, Any]:
        candidate_id = str(candidate["candidate_id"])
        try:
            document, target, section, neighbors = self._generation_context(
                str(candidate["course_id"]),
                str(candidate["block_id"]),
                expected_document_revision=str(candidate["expected_document_revision"]),
                expected_block_revision=str(candidate["expected_block_revision"]),
            )
            original_payload = deepcopy(candidate.get("original_payload") or target.payload)
            content_key = self._content_key(original_payload)
            original_content = str(original_payload.get(content_key) or "")
            quality_feedback: list[str] = []
            generator = self.generator
            if generator is None:
                from course_service import get_course_service

                generator = get_course_service()

            latest = candidate
            for attempt_number in range(1, 3):
                content = await generator.generate_course_block_candidate(
                    course_id=str(candidate["course_id"]),
                    document_title=document.title,
                    section=section.model_dump(mode="json"),
                    target_block=target.model_dump(mode="json"),
                    previous_block=neighbors["previous"],
                    next_block=neighbors["next"],
                    instruction=str(candidate.get("instruction") or ""),
                    action_type=str(candidate.get("action_type") or "rewrite"),
                    quality_feedback=quality_feedback,
                    user_id=user_id,
                )
                proposed_payload = deepcopy(original_payload)
                proposed_payload[content_key] = str(content or "").strip()
                proposed_payload["summary"] = summarize_text(proposed_payload[content_key])
                quality_report = evaluate_block_candidate(
                    original_content=original_content,
                    candidate_content=proposed_payload[content_key],
                    original_payload=original_payload,
                    proposed_payload=proposed_payload,
                )

                def persist_attempt(current: dict[str, Any]) -> dict[str, Any]:
                    attempts = list(current.get("attempts") or [])
                    attempts.append({
                        "run_id": run_id,
                        "attempt": attempt_number,
                        "quality_report": quality_report,
                    })
                    return {
                        **current,
                        "proposed_block": {
                            **target.model_dump(mode="json"),
                            "payload": proposed_payload,
                        },
                        "quality_report": quality_report,
                        "attempts": attempts,
                    }

                latest, persisted = self.candidate_repository.update_if(
                    candidate_id,
                    lambda current: (
                        current.get("status") == "generating"
                        and current.get("generation_run_id") == run_id
                    ),
                    persist_attempt,
                )
                if not persisted:
                    return latest
                if quality_report["passed"]:
                    break
                quality_feedback = list(quality_report["issues"])

            terminal_status = "ready" if (latest.get("quality_report") or {}).get("passed") else "quality_failed"
            latest, _persisted = self.candidate_repository.update_if(
                candidate_id,
                lambda current: (
                    current.get("status") == "generating"
                    and current.get("generation_run_id") == run_id
                ),
                lambda current: {
                    **current,
                    "status": terminal_status,
                    "retryable": False,
                    "generation_completed_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            return latest
        except (BlockRegenerationConflict, BlockRegenerationNotFound) as exc:
            stale, _updated = self.candidate_repository.update_if(
                candidate_id,
                lambda current: (
                    current.get("status") == "generating"
                    and current.get("generation_run_id") == run_id
                ),
                lambda current: {
                    **current,
                    "status": "stale",
                    "retryable": False,
                    "failure_code": "revision_conflict",
                    "failure_reason": str(exc),
                    "generation_completed_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            return stale
        except asyncio.CancelledError:
            self._mark_generation_failed(candidate_id, run_id, failure_code="request_cancelled")
            raise
        except Exception:
            return self._mark_generation_failed(candidate_id, run_id, failure_code="provider_error")

    def _mark_generation_failed(
        self,
        candidate_id: str,
        run_id: str,
        *,
        failure_code: str,
    ) -> dict[str, Any]:
        failed, _updated = self.candidate_repository.update_if(
            candidate_id,
            lambda current: (
                current.get("status") == "generating"
                and current.get("generation_run_id") == run_id
            ),
            lambda current: {
                **current,
                "status": "generation_failed",
                "retryable": True,
                "failure_code": failure_code,
                "failure_reason": "AI 生成过程中断，已保留当前候选，可直接重试。",
                "generation_completed_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        return failed

    def _recover_interrupted_candidate(self, candidate: dict[str, Any]) -> dict[str, Any]:
        if (
            candidate.get("status") != "generating"
            or candidate.get("generation_owner") == BLOCK_REGENERATION_PROCESS_ID
        ):
            return candidate
        run_id = str(candidate.get("generation_run_id") or "")
        failed, _updated = self.candidate_repository.update_if(
            str(candidate["candidate_id"]),
            lambda current: (
                current.get("status") == "generating"
                and str(current.get("generation_run_id") or "") == run_id
                and current.get("generation_owner") != BLOCK_REGENERATION_PROCESS_ID
            ),
            lambda current: {
                **current,
                "status": "generation_failed",
                "retryable": True,
                "failure_code": "process_interrupted",
                "failure_reason": "生成服务曾中断，已保留请求，可从这里继续。",
                "generation_completed_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        return failed

    def _generation_context(
        self,
        course_id: str,
        block_id: str,
        *,
        expected_document_revision: str,
        expected_block_revision: str,
    ) -> tuple[Any, CourseBlock, Any, dict[str, dict[str, Any] | None]]:
        document, canonical = self.course_repository.load_document(course_id)
        if not canonical:
            raise BlockRegenerationConflict("Course must be migrated before block regeneration")
        if document.document_revision != expected_document_revision:
            raise BlockRegenerationConflict("Course document revision changed before candidate generation")
        target = next((block for block in document.blocks if block.block_id == block_id), None)
        if not target:
            raise BlockRegenerationNotFound(block_id)
        if target.internal_revision != expected_block_revision:
            raise BlockRegenerationConflict("Course block revision changed before candidate generation")
        section = next((item for item in document.sections if item.section_id == target.section_id), None)
        if not section:
            raise BlockRegenerationConflict("Course block section is missing")
        return document, target, section, self._neighbor_context(document.blocks, target)

    async def apply_candidate(
        self,
        course_id: str,
        block_id: str,
        candidate_id: str,
        *,
        actor: str,
    ) -> dict[str, Any]:
        candidate = self.get_candidate(course_id, block_id, candidate_id)
        if candidate.get("status") == "applied" and candidate.get("receipt"):
            return {
                "candidate": candidate,
                "receipt": deepcopy(candidate["receipt"]),
                "document": self.course_repository.document_envelope(course_id),
            }
        if candidate.get("status") != "ready":
            raise BlockRegenerationConflict(
                f"Candidate cannot be applied from status {candidate.get('status')}",
                candidate=candidate,
            )
        if not (candidate.get("quality_report") or {}).get("passed"):
            raise BlockRegenerationConflict("Candidate did not pass the quality gate", candidate=candidate)

        proposed_block = candidate.get("proposed_block") or {}
        payload = proposed_block.get("payload")
        if not isinstance(payload, dict):
            raise BlockRegenerationConflict("Candidate payload is invalid", candidate=candidate)
        try:
            receipt = await self.command_service.replace_block(
                course_id,
                command_id=f"apply-{candidate_id}",
                expected_document_revision=str(candidate.get("expected_document_revision") or ""),
                expected_block_revision=str(candidate.get("expected_block_revision") or ""),
                block_id=block_id,
                payload=payload,
                reason=str(candidate.get("instruction") or "局部重新生成"),
                actor=actor,
            )
        except CourseDocumentConflict as exc:
            stale = self.candidate_repository.update(candidate_id, lambda current: {
                **current,
                "status": "stale",
                "failure_reason": str(exc),
            })
            raise BlockRegenerationConflict(str(exc), candidate=stale) from exc

        applied = self.candidate_repository.update(candidate_id, lambda current: {
            **current,
            "status": "applied",
            "receipt": receipt,
            "applied_at": datetime.now(timezone.utc).isoformat(),
        })
        return {
            "candidate": applied,
            "receipt": receipt,
            "document": self.course_repository.document_envelope(course_id),
        }

    def reject_candidate(
        self,
        course_id: str,
        block_id: str,
        candidate_id: str,
    ) -> dict[str, Any]:
        candidate = self.get_candidate(course_id, block_id, candidate_id)
        if candidate.get("status") == "applied":
            raise BlockRegenerationConflict("Applied candidate cannot be rejected", candidate=candidate)
        if candidate.get("status") == "rejected":
            return candidate
        rejected, changed = self.candidate_repository.update_if(
            candidate_id,
            lambda current: current.get("status") not in {"applied", "rejected", "generating"},
            lambda current: {
                **current,
                "status": "rejected",
                "rejected_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        if changed or rejected.get("status") == "rejected":
            return rejected
        raise BlockRegenerationConflict(
            "Candidate is being generated and cannot be rejected",
            candidate=rejected,
        )

    @staticmethod
    def _require_target(candidate: dict[str, Any], course_id: str, block_id: str) -> None:
        if candidate.get("course_id") != course_id or candidate.get("block_id") != block_id:
            raise BlockRegenerationNotFound(str(candidate.get("candidate_id") or ""))

    @staticmethod
    def _require_matching_request(
        candidate: dict[str, Any],
        *,
        request_fingerprint: str,
        instruction: str,
        action_type: str,
        expected_document_revision: str,
        expected_block_revision: str,
        user_id: str,
    ) -> None:
        stored_fingerprint = str(candidate.get("request_fingerprint") or "")
        if stored_fingerprint:
            matches = stored_fingerprint == request_fingerprint
        else:
            requested_by = str(candidate.get("requested_by") or "")
            matches = (
                str(candidate.get("instruction") or "") == instruction
                and str(candidate.get("action_type") or "rewrite") == action_type
                and str(candidate.get("expected_document_revision") or "")
                == expected_document_revision
                and str(candidate.get("expected_block_revision") or "")
                == expected_block_revision
                and (not requested_by or requested_by == user_id)
            )
        if not matches:
            raise BlockRegenerationConflict(
                "request_id reused with different payload",
                candidate=candidate,
            )

    @staticmethod
    def _content_key(payload: dict[str, Any]) -> str:
        if "markdown" in payload or "text" not in payload:
            return "markdown"
        return "text"

    @staticmethod
    def _neighbor_context(blocks: list[CourseBlock], target: CourseBlock) -> dict[str, dict[str, Any] | None]:
        siblings = sorted(
            [item for item in blocks if item.section_id == target.section_id and item.status != "retired"],
            key=lambda item: item.position,
        )
        index = next(idx for idx, item in enumerate(siblings) if item.block_id == target.block_id)

        def context(block: CourseBlock | None) -> dict[str, Any] | None:
            if block is None:
                return None
            content = str(block.payload.get("markdown") or block.payload.get("text") or "")
            return {
                "block_id": block.block_id,
                "role": block.role,
                "title": str(block.payload.get("title") or ""),
                "content_summary": summarize_text(content, limit=600),
            }

        return {
            "previous": context(siblings[index - 1] if index > 0 else None),
            "next": context(siblings[index + 1] if index + 1 < len(siblings) else None),
        }


class PersonalizationProposalService:
    """Build a small authoring proposal from one learner-feedback submission."""

    def __init__(
        self,
        course_repository: CourseDocumentRepository,
        candidate_repository: BlockRegenerationCandidateRepository,
        proposal_repository: ChangeProposalRepository,
        *,
        generator: Any | None = None,
        event_recorder: Callable[..., dict[str, Any]] = record_learning_event,
    ) -> None:
        self.course_repository = course_repository
        self.proposal_repository = proposal_repository
        self.regeneration_service = BlockRegenerationService(
            course_repository,
            candidate_repository,
            generator=generator,
        )
        self.event_recorder = event_recorder

    async def create_proposal(
        self,
        course_id: str,
        block_id: str,
        *,
        request_id: str,
        expected_document_revision: str,
        expected_block_revision: str,
        direction: str,
        feedback: str,
        user_id: str,
    ) -> dict[str, Any]:
        proposal_id = self.proposal_repository.proposal_id_for(course_id, request_id)
        feedback_hash = stable_hash({"feedback": feedback.strip()}, prefix="pfh_")
        request_fingerprint = stable_hash(
            {
                "user_id": user_id,
                "block_id": block_id,
                "expected_document_revision": expected_document_revision,
                "expected_block_revision": expected_block_revision,
                "direction": direction,
                "feedback_hash": feedback_hash,
            },
            prefix="ppf_",
        )
        request_key = (str(self.proposal_repository.root_dir.resolve()), proposal_id)
        created = False
        with _PERSONALIZATION_REQUEST_TASKS_GUARD:
            inflight = _PERSONALIZATION_REQUEST_TASKS.get(request_key)
            if inflight is not None:
                inflight_fingerprint, task = inflight
                if inflight_fingerprint != request_fingerprint:
                    raise BlockRegenerationConflict(
                        "Personalization request ID was already used with different inputs"
                    )
            else:
                task = asyncio.create_task(self._create_proposal(
                    course_id,
                    block_id,
                    request_id=request_id,
                    expected_document_revision=expected_document_revision,
                    expected_block_revision=expected_block_revision,
                    direction=direction,
                    feedback=feedback,
                    user_id=user_id,
                    proposal_id=proposal_id,
                    feedback_hash=feedback_hash,
                    request_fingerprint=request_fingerprint,
                ))
                _PERSONALIZATION_REQUEST_TASKS[request_key] = (request_fingerprint, task)
                created = True

        if created:
            def clear_inflight(completed: asyncio.Task[dict[str, Any]]) -> None:
                with _PERSONALIZATION_REQUEST_TASKS_GUARD:
                    current = _PERSONALIZATION_REQUEST_TASKS.get(request_key)
                    if current is not None and current[1] is completed:
                        _PERSONALIZATION_REQUEST_TASKS.pop(request_key, None)

            task.add_done_callback(clear_inflight)
            return await task

        try:
            return await asyncio.wait_for(
                asyncio.shield(task),
                timeout=PERSONALIZATION_IDEMPOTENCY_WAIT_SECONDS,
            )
        except TimeoutError as exc:
            raise PersonalizationGenerationInProgress(
                "Personalization request is still being generated"
            ) from exc

    async def _create_proposal(
        self,
        course_id: str,
        block_id: str,
        *,
        request_id: str,
        expected_document_revision: str,
        expected_block_revision: str,
        direction: str,
        feedback: str,
        user_id: str,
        proposal_id: str,
        feedback_hash: str,
        request_fingerprint: str,
    ) -> dict[str, Any]:
        existing = self.proposal_repository.load_optional(proposal_id)
        if existing is not None:
            existing_fingerprint = str(
                (existing.get("generation_meta") or {}).get("request_fingerprint") or ""
            )
            if existing_fingerprint != request_fingerprint:
                raise BlockRegenerationConflict(
                    "Personalization request ID was already used with different inputs"
                )
            return existing

        document, canonical = self.course_repository.load_document(course_id)
        if not canonical:
            raise BlockRegenerationConflict("Course must be migrated before personalization")
        if document.document_revision != expected_document_revision:
            raise BlockRegenerationConflict("Course document revision changed before personalization")
        target = next((item for item in document.blocks if item.block_id == block_id), None)
        if target is None:
            raise BlockRegenerationNotFound(block_id)
        if target.internal_revision != expected_block_revision:
            raise BlockRegenerationConflict("Course block revision changed before personalization")

        instruction = self._instruction(direction, feedback, related=False)
        target_candidate = await self.regeneration_service.create_candidate(
            course_id,
            block_id,
            request_id=f"{request_id}-{block_id}",
            expected_document_revision=expected_document_revision,
            expected_block_revision=expected_block_revision,
            instruction=instruction,
            action_type=self._action_type(direction),
            user_id=user_id,
        )
        if target_candidate.get("status") != "ready":
            raise BlockRegenerationConflict(
                "Target block personalization could not produce a usable candidate",
                candidate=target_candidate,
            )

        generated: list[tuple[CourseBlock, dict[str, Any]]] = [(target, target_candidate)]

        async def generate_related(
            related: CourseBlock,
        ) -> tuple[CourseBlock, dict[str, Any]] | None:
            try:
                candidate = await asyncio.wait_for(
                    self.regeneration_service.create_candidate(
                        course_id,
                        related.block_id,
                        request_id=f"{request_id}-{related.block_id}",
                        expected_document_revision=expected_document_revision,
                        expected_block_revision=related.internal_revision,
                        instruction=self._instruction(direction, feedback, related=True),
                        action_type=self._action_type(direction),
                        user_id=user_id,
                    ),
                    timeout=PERSONALIZATION_RELATED_TIMEOUT_SECONDS,
                )
            except Exception:
                return None
            if candidate.get("status") == "ready":
                return related, candidate
            return None

        related_results = await asyncio.gather(*(
            generate_related(related)
            for related in self._related_blocks(document.blocks, target, direction)[:2]
        ))
        generated.extend(result for result in related_results if result is not None)

        items = [
            {
                "block_id": block.block_id,
                "before": block.model_dump(mode="json"),
                "after": self._redact_feedback(candidate["proposed_block"], feedback),
                "reason": self._reason(block.block_id == target.block_id, direction),
                "selected": True,
                "expected_block_revision": block.internal_revision,
            }
            for block, candidate in generated
        ]
        target_block_ids = [item["block_id"] for item in items]
        proposal = create_authoring_change(
            self.proposal_repository,
            course_id,
            request_id=request_id,
            scope="section" if len(items) > 1 else "block",
            target_block_ids=target_block_ids,
            items=items,
            source="personalization",
            generation_meta={
                "direction": direction,
                "feedback_hash": feedback_hash,
                "request_fingerprint": request_fingerprint,
                "base_document_revision": expected_document_revision,
                "target_block_id": block_id,
            },
        )
        persisted_fingerprint = str(
            (proposal.get("generation_meta") or {}).get("request_fingerprint") or ""
        )
        if persisted_fingerprint != request_fingerprint:
            raise BlockRegenerationConflict(
                "Personalization request ID was concurrently used with different inputs"
            )
        self.event_recorder(
            event_type="personalization_feedback_submitted",
            actor="learner",
            source="personalization_proposals",
            user_id=user_id,
            course_id=course_id,
            course_version_id=expected_document_revision,
            node_id=block_id,
            objective_id=(target.objective_refs or [None])[0],
            operation_id=proposal["proposal_id"],
            idempotency_key=request_id,
            entity_type="course_block",
            entity_id=block_id,
            entity_revision=expected_block_revision,
            evidence={
                "direction": direction,
                "feedback_summary": summarize_text(feedback, limit=240),
            },
            result={
                "proposal_id": proposal["proposal_id"],
                "changed_block_ids": target_block_ids,
            },
        )
        return proposal

    @staticmethod
    def _action_type(direction: str) -> str:
        return direction if direction in {"simplify", "expand"} else "rewrite"

    @staticmethod
    def _instruction(direction: str, feedback: str, *, related: bool) -> str:
        direction_text = {
            "simplify": "降低理解门槛，用更直观、清楚的表达解释关键概念。",
            "expand": "补充必要的推理、例子或应用，让解释更完整。",
            "custom": "严格根据学生的具体反馈改进正文。",
        }.get(direction, "严格根据学生的具体反馈改进正文。")
        relation_text = (
            "这是与目标块同章节、同学习目标的相关块；只做少量协调改进，避免重复目标块。"
            if related
            else "这是学生当前反馈所指向的目标块，必须对反馈作出明显、直接的响应。"
        )
        return f"{direction_text}\n{relation_text}\n学生反馈：{feedback}"

    @staticmethod
    def _reason(is_target: bool, direction: str) -> str:
        subject = "直接优化反馈所指向的当前块" if is_target else "协调同目标的相关块"
        return f"{subject}；方向：{direction}"

    @staticmethod
    def _redact_feedback(value: Any, feedback: str) -> Any:
        """Keep generated content while avoiding verbatim feedback persistence."""
        needle = feedback.strip()
        if not needle:
            return deepcopy(value)
        if isinstance(value, str):
            return value.replace(needle, "（反馈原文已省略）")
        if isinstance(value, list):
            return [PersonalizationProposalService._redact_feedback(item, needle) for item in value]
        if isinstance(value, dict):
            return {
                key: PersonalizationProposalService._redact_feedback(item, needle)
                for key, item in value.items()
            }
        return deepcopy(value)

    @staticmethod
    def _related_blocks(
        blocks: list[CourseBlock],
        target: CourseBlock,
        direction: str,
    ) -> list[CourseBlock]:
        target_objectives = set(target.objective_refs)
        if not target_objectives:
            return []
        priorities = list(_PERSONALIZATION_ROLE_PRIORITY.get(direction, _PERSONALIZATION_ROLE_PRIORITY["custom"]))
        if direction == "custom" and target.role in priorities:
            priorities.remove(target.role)
            priorities.insert(0, target.role)
        role_rank = {role: index for index, role in enumerate(priorities)}
        related = [
            block
            for block in blocks
            if block.block_id != target.block_id
            and block.section_id == target.section_id
            and block.status != "retired"
            and bool(target_objectives.intersection(block.objective_refs))
        ]
        return sorted(
            related,
            key=lambda block: (
                role_rank.get(block.role, len(role_rank)),
                abs(block.position - target.position),
                block.position,
                block.block_id,
            ),
        )


def evaluate_block_candidate(
    *,
    original_content: str,
    candidate_content: str,
    original_payload: dict[str, Any],
    proposed_payload: dict[str, Any],
) -> dict[str, Any]:
    original = _normalized_text(original_content)
    candidate = _normalized_text(candidate_content)
    lowered = candidate.lower()
    preserved_payload = all(
        proposed_payload.get(key) == value
        for key, value in original_payload.items()
        if key not in _CONTENT_KEYS | {"summary"}
    )
    original_fences = original_content.count("```")
    candidate_fences = candidate_content.count("```")
    gates = [
        _quality_gate("content_present", bool(candidate) and len(candidate) >= 12, "候选正文为空或过短"),
        _quality_gate("content_changed", bool(candidate) and candidate != original, "候选与原文没有实质变化"),
        _quality_gate(
            "generation_clean",
            bool(candidate) and not any(marker in lowered for marker in _ERROR_MARKERS),
            "候选包含生成错误或拒答标记",
        ),
        _quality_gate("safe_length", len(candidate_content) <= 80000, "候选超过单块安全长度"),
        _quality_gate("payload_preserved", preserved_payload, "候选丢失了原块的非正文载荷"),
        _quality_gate(
            "code_fence_preserved",
            original_fences < 2 or (candidate_fences >= 2 and candidate_fences % 2 == 0),
            "原块包含代码围栏，但候选没有保留有效闭合围栏",
        ),
    ]
    issues = [gate["message"] for gate in gates if not gate["passed"]]
    return {
        "passed": not issues,
        "status": "passed" if not issues else "failed",
        "gates": gates,
        "issues": issues,
    }


def _normalized_text(value: str) -> str:
    return " ".join(str(value or "").split()).strip()


def _quality_gate(key: str, passed: bool, message: str) -> dict[str, Any]:
    return {
        "key": key,
        "passed": bool(passed),
        "severity": "critical",
        "message": message,
    }


block_regeneration_candidate_repository = BlockRegenerationCandidateRepository()


__all__ = [
    "BLOCK_REGENERATION_SCHEMA",
    "BlockRegenerationCandidateRepository",
    "BlockRegenerationConflict",
    "BlockRegenerationNotFound",
    "BlockRegenerationService",
    "PersonalizationGenerationInProgress",
    "PersonalizationProposalService",
    "block_regeneration_candidate_repository",
    "evaluate_block_candidate",
]
