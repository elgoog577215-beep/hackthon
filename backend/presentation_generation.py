"""Presentation application service and bounded asynchronous generation.

Repository methods are synchronous and atomic; this service always calls them
through ``asyncio.to_thread`` so the FastAPI event loop remains responsive.
The service owns orchestration only: course data stays read-only and every
deck mutation is delegated to the append-only presentation repository.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from ai_base import AIBase
from presentation_models import (
    ArtifactReceipt,
    ChatPresentationRequest,
    CreatePresentationRequest,
    DeckProposal,
    DeckRevision,
    FinalizePresentationRequest,
    GeneratePresentationRequest,
    GenerationWorkingSnapshot,
    PresentationDeck,
    PresentationEvent,
    QualityIssue,
    RevisionCommand,
    Slide,
    SlideBlock,
    SlideQuality,
    SlideSourceRefs,
    SourceRef,
    utc_now,
)
from presentation_quality import evaluate_presentation_quality, revision_checksum
from presentation_render import render_artifacts, speaker_notes_digest, title_digest
from presentation_repository import StaleRevisionConflict
from presentation_templates import get_layout, validate_slide_capacity


logger = logging.getLogger(__name__)


class PresentationServiceError(RuntimeError):
    code = "presentation_service_error"
    status_code = 400

    def __init__(self, message: str = "课件操作失败", *, details: Any = None):
        super().__init__(message)
        self.details = details


class PresentationServiceConflict(PresentationServiceError):
    status_code = 409

    def __init__(self, code: str, message: str, *, details: Any = None):
        self.code = code
        super().__init__(message, details=details)


class PresentationQualityBlocked(PresentationServiceError):
    code = "presentation_quality_blocked"
    status_code = 422

    def __init__(self, report: Mapping[str, Any]):
        self.report = dict(report)
        super().__init__("课件质量检查未通过", details=self.report)


@dataclass
class GenerationSession:
    deck_id: str
    course_id: str
    generation_id: str
    request: GeneratePresentationRequest
    source_snapshot: dict[str, Any]
    working: GenerationWorkingSnapshot
    outline: list[dict[str, Any]]


def _records(source: Mapping[str, Any], *keys: str) -> list[dict[str, Any]]:
    for key in keys:
        value = source.get(key)
        if isinstance(value, list):
            return [dict(item) for item in value if isinstance(item, Mapping)]
        if isinstance(value, Mapping) and isinstance(value.get("items"), list):
            return [dict(item) for item in value["items"] if isinstance(item, Mapping)]
    return []


def _record_id(record: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = record.get(key)
        if value is not None and str(value).strip():
            return str(value)
    return ""


def _record_text(record: Mapping[str, Any]) -> str:
    for key in ("content", "text", "prompt", "node_content", "description", "summary", "title", "name"):
        value = record.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    payload = record.get("payload")
    if isinstance(payload, Mapping):
        for key in ("content", "markdown", "text", "summary", "title"):
            value = payload.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
    return ""


def _trim(text: str, limit: int = 520) -> str:
    compact = re.sub(r"\s+", " ", str(text or "")).strip()
    return compact if len(compact) <= limit else compact[: limit - 1].rstrip() + "…"


_MODEL_ITEM_FIELDS: tuple[tuple[str, str], ...] = (
    ("error", "错误"),
    ("correction", "纠正"),
    ("text", ""),
    ("content", ""),
    ("title", ""),
    ("prompt", "问题"),
    ("answer", "答案"),
    ("explanation", "解释"),
    ("hint", "提示"),
)
_MODEL_METADATA_FIELDS = {
    "left", "right", "language", "answer", "hint", "generation_mode",
}


def _model_scalar(value: Any, limit: int) -> str:
    if value is None or not isinstance(value, (str, int, float, bool)):
        return ""
    return _trim(str(value), limit)


def _model_content(value: Any, limit: int = 6000) -> str:
    """Normalize scalar block content without destroying code formatting."""
    if value is None or not isinstance(value, (str, int, float, bool)):
        return ""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _normalize_model_item(value: Any) -> str:
    scalar = _model_scalar(value, 1000)
    if scalar:
        return scalar
    if not isinstance(value, Mapping):
        return ""
    parts: list[str] = []
    for key, label in _MODEL_ITEM_FIELDS:
        text = _model_scalar(value.get(key), 700)
        if text:
            parts.append(f"{label}：{text}" if label else text)
    return "；".join(parts)


def _normalize_model_metadata(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    normalized: dict[str, str] = {}
    for key in sorted(_MODEL_METADATA_FIELDS):
        if key not in value:
            continue
        text = _model_scalar(value.get(key), 1000)
        if text:
            normalized[key] = text
    return normalized


def _normalize_model_block(slide_id: str, index: int, value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"blocks[{index}] must be an object")
    block_id = _model_scalar(value.get("block_id"), 200) or f"{slide_id}-model-block-{index + 1}"
    raw_items = value.get("items")
    if raw_items is None:
        item_values: list[Any] = []
    elif isinstance(raw_items, list):
        item_values = raw_items
    elif isinstance(raw_items, (str, int, float, bool, Mapping)):
        item_values = [raw_items]
    else:
        raise ValueError(f"blocks[{index}].items must be a list or readable value")
    return {
        "block_id": block_id,
        "type": _model_scalar(value.get("type"), 50).lower() or "text",
        "title": _model_scalar(value.get("title"), 300),
        "content": _model_content(value.get("content")),
        "items": [text for item in item_values if (text := _normalize_model_item(item))],
        "metadata": _normalize_model_metadata(value.get("metadata")),
    }


def _normalize_model_blocks(slide_id: str, value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("blocks must be a list")
    return [_normalize_model_block(slide_id, index, item) for index, item in enumerate(value)]


class PresentationService:
    """Application boundary used by the HTTP router and focused tests."""

    def __init__(
        self,
        repository: Any,
        *,
        course_loader: Callable[[str], Mapping[str, Any]] | None = None,
        source_projector: Callable[..., tuple[dict[str, Any], SourceRef]] | None = None,
        source_packet_builder: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
        ai_factory: Callable[[], Any] | None = AIBase,
        renderer: Callable[[DeckRevision, str, str | Path], Mapping[str, Any]] = render_artifacts,
        max_page_concurrency: int = 3,
    ) -> None:
        self.repository = repository
        self.course_loader = course_loader
        self.source_projector = source_projector
        self.source_packet_builder = source_packet_builder
        self.ai_factory = ai_factory
        self.renderer = renderer
        self.max_page_concurrency = max(1, min(int(max_page_concurrency), 3))
        self._patch_semaphore = asyncio.Semaphore(self.max_page_concurrency)
        self._tasks: dict[tuple[str, str], asyncio.Task[None]] = {}
        self._conditions: dict[tuple[str, str], asyncio.Condition] = {}
        self._prepare_locks: dict[str, asyncio.Lock] = {}

    async def _repo(self, method: str, *args: Any, **kwargs: Any) -> Any:
        function = getattr(self.repository, method)
        return await asyncio.to_thread(function, *args, **kwargs)

    async def create_presentation(self, course_id: str, request: CreatePresentationRequest) -> dict[str, Any]:
        if self.course_loader is None or self.source_projector is None:
            raise PresentationServiceError("课件来源投影器未配置")
        course = await asyncio.to_thread(self.course_loader, course_id)
        if not isinstance(course, Mapping) or not course:
            raise KeyError(course_id)
        snapshot, source_ref = await asyncio.to_thread(
            self.source_projector,
            dict(course),
            request.scope,
            course_id=course_id,
        )
        deck = PresentationDeck(
            deck_id=f"deck_{uuid4().hex}",
            course_id=course_id,
            title=request.title,
            source_ref=source_ref,
            scope=request.scope,
            purpose=request.purpose,
            template_id=request.template_id,
        )
        create_intent = {
            "course_id": course_id,
            **request.model_dump(mode="json", exclude={"request_id"}),
            "source_snapshot_sha256": source_ref.source_snapshot_sha256,
        }
        return await self._repo(
            "create_deck",
            deck,
            snapshot,
            request_id=request.request_id,
            operation="create_presentation",
            fingerprint_payload=create_intent,
        )

    async def list_presentations(self, course_id: str) -> list[dict[str, Any]]:
        decks = await self._repo("list_decks", course_id)
        current_version_id = await self._current_course_version_id(course_id)
        return [self._annotate_source_freshness(deck, current_version_id) for deck in decks]

    async def get_presentation(self, deck_id: str) -> dict[str, Any]:
        aggregate = await self._repo("get_deck", deck_id)
        manifest = dict(aggregate["manifest"])
        current_version_id = await self._current_course_version_id(str(manifest["course_id"]))
        annotated = self._annotate_source_freshness(manifest, current_version_id)
        result = dict(aggregate)
        result["manifest"] = annotated
        result["source_outdated"] = annotated["source_outdated"]
        result["current_course_version_id"] = annotated["current_course_version_id"]
        return result

    async def _current_course_version_id(self, course_id: str) -> str | None:
        if self.course_loader is None:
            return None
        try:
            course = await asyncio.to_thread(self.course_loader, course_id)
        except (KeyError, FileNotFoundError):
            return None
        if not isinstance(course, Mapping):
            return None
        embedded = course.get("course_document")
        embedded_revision = embedded.get("document_revision") if isinstance(embedded, Mapping) else None
        value = (
            course.get("current_course_version_id")
            or course.get("version_id")
            or course.get("course_document_revision")
            or course.get("document_revision")
            or embedded_revision
        )
        return str(value) if value is not None and str(value).strip() else None

    @staticmethod
    def _annotate_source_freshness(
        manifest: Mapping[str, Any], current_version_id: str | None
    ) -> dict[str, Any]:
        result = dict(manifest)
        source_ref = result.get("source_ref")
        source_version_id = str(source_ref.get("version_id") or "") if isinstance(source_ref, Mapping) else ""
        result["current_course_version_id"] = current_version_id
        result["source_outdated"] = bool(
            current_version_id and source_version_id and current_version_id != source_version_id
        )
        return result

    async def _manifest(self, deck_id: str) -> PresentationDeck:
        return PresentationDeck.model_validate(await self._repo("load_manifest", deck_id))

    @staticmethod
    def _check_expected(manifest: PresentationDeck, expected_revision_id: str | None) -> None:
        if manifest.active_revision_id is not None and expected_revision_id is None:
            raise PresentationServiceConflict(
                "expected_revision_required",
                "当前课件已有版本，请携带 expected_revision_id。",
                details={"active_revision_id": manifest.active_revision_id},
            )
        if expected_revision_id is not None and manifest.active_revision_id != expected_revision_id:
            raise PresentationServiceConflict(
                "stale_revision",
                "课件版本已变化，请刷新后重试。",
                details={"expected_revision_id": expected_revision_id, "active_revision_id": manifest.active_revision_id},
            )

    @staticmethod
    def _check_generation_idle(manifest: PresentationDeck) -> None:
        if manifest.active_generation_id:
            raise PresentationServiceConflict(
                "generation_in_progress",
                "课件正在生成，请等待本轮生成完成后再修改或导出。",
                details={"generation_id": manifest.active_generation_id},
            )

    @staticmethod
    def _command_reused(command_id: str, operation: str) -> PresentationServiceConflict:
        return PresentationServiceConflict(
            "command_id_reused",
            "该 command_id 已用于其他课件操作，请为本次操作生成新的 command_id。",
            details={"command_id": command_id, "operation": operation},
        )

    def _packet(self, snapshot: Mapping[str, Any]) -> dict[str, Any]:
        if self.source_packet_builder is None:
            return dict(snapshot)
        return dict(self.source_packet_builder(snapshot))

    @staticmethod
    def _source_refs(
        packet: Mapping[str, Any],
        index: int = 0,
        preferred_section_id: str = "",
    ) -> SlideSourceRefs:
        sections = _records(packet, "sections", "nodes")
        blocks = _records(packet, "blocks", "content_blocks")
        objectives = _records(packet, "objectives", "learning_objectives")
        assets = _records(packet, "assets", "asset_refs")

        def by_section(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
            if not preferred_section_id:
                return records
            matched = [
                record for record in records
                if _record_id(record, "section_id", "node_id", "parent_section_id") == preferred_section_id
            ]
            return matched or records

        candidate_blocks = by_section(blocks)
        candidate_objectives = by_section(objectives)
        block = candidate_blocks[index % len(candidate_blocks)] if candidate_blocks else {}
        objective = candidate_objectives[index % len(candidate_objectives)] if candidate_objectives else {}
        resolved_section_id = preferred_section_id or _record_id(
            objective, "section_id", "node_id", "parent_section_id"
        ) or _record_id(block, "section_id", "node_id", "parent_section_id")
        section = next(
            (
                record for record in sections
                if _record_id(record, "section_id", "node_id", "id") == resolved_section_id
            ),
            sections[index % len(sections)] if sections else {},
        )
        asset = assets[index % len(assets)] if assets else {}
        return SlideSourceRefs(
            section_ids=[value for value in [_record_id(section, "section_id", "node_id", "id")] if value],
            block_ids=[value for value in [_record_id(block, "block_id", "id")] if value],
            block_revision_ids=[value for value in [_record_id(block, "block_revision_id", "internal_revision", "revision_id")] if value],
            objective_ids=[value for value in [_record_id(objective, "objective_id", "id")] if value],
            asset_ids=[value for value in [_record_id(asset, "asset_id", "id")] if value],
        )

    @staticmethod
    def _page_packet(slide: Slide, packet: Mapping[str, Any]) -> dict[str, Any]:
        """Limit one page filler to records referenced by that page."""

        refs = slide.source_refs
        section_ids = set(refs.section_ids)
        block_ids = set(refs.block_ids)
        objective_ids = set(refs.objective_ids)
        asset_ids = set(refs.asset_ids)

        def relevant(record: Mapping[str, Any], direct_ids: set[str], *id_keys: str) -> bool:
            record_id = _record_id(record, *id_keys)
            record_section = _record_id(record, "section_id", "node_id", "parent_section_id")
            return (bool(record_id) and record_id in direct_ids) or (
                bool(record_section) and record_section in section_ids
            )

        page_packet = dict(packet)
        page_packet["sections"] = [
            record for record in _records(packet, "sections", "nodes")
            if _record_id(record, "section_id", "node_id", "id") in section_ids
        ]
        page_packet["blocks"] = [
            record for record in _records(packet, "blocks", "content_blocks")
            if relevant(record, block_ids, "block_id", "id")
        ]
        page_packet["objectives"] = [
            record for record in _records(packet, "objectives", "learning_objectives")
            if relevant(record, objective_ids, "objective_id", "id")
        ]
        page_packet["assets"] = [
            record for record in _records(packet, "assets", "asset_refs")
            if relevant(record, asset_ids, "asset_id", "id")
        ]
        for key, aliases in (
            ("misconceptions", ("misconceptions", "common_misconceptions")),
            ("practices", ("practices", "exercises", "questions")),
            ("questions", ("questions",)),
        ):
            page_packet[key] = [
                record for record in _records(packet, *aliases)
                if relevant(record, set(), "id")
            ]
        return page_packet

    def _curate(self, packet: Mapping[str, Any], page_budget: int, deck_title: str) -> list[dict[str, Any]]:
        sections = _records(packet, "sections", "nodes")
        blocks = _records(packet, "blocks", "content_blocks")
        objectives = _records(packet, "objectives", "learning_objectives")
        misconceptions = _records(packet, "misconceptions", "common_misconceptions")
        practices = _records(packet, "practices", "exercises", "questions")
        title = str(packet.get("title") or packet.get("course_name") or deck_title or "灵知课件")

        concept_records = objectives or sections or blocks
        desired_concepts = max(1, page_budget - 3 - int(bool(misconceptions)) - int(bool(practices)))
        briefs: list[dict[str, Any]] = [
            {"layout_id": "L01", "title": title, "key_message": "从课程目标出发建立本节知识主线", "source_index": 0,
             "source_section_id": _record_id((objectives or blocks or sections or [{}])[0], "section_id", "node_id")},
            {"layout_id": "L02", "title": "课程路线", "key_message": "先看目标，再理解概念，最后练习与回顾", "source_index": 0,
             "source_section_id": _record_id((objectives or blocks or sections or [{}])[0], "section_id", "node_id")},
        ]
        for index in range(desired_concepts):
            record = concept_records[index % len(concept_records)] if concept_records else {}
            heading = _record_text(record) or f"核心概念 {index + 1}"
            briefs.append({
                "layout_id": "L04",
                "title": _trim(heading, 70),
                "key_message": _trim(_record_text(record), 180) or "用课程原文解释核心知识并联系具体情境",
                "source_index": index,
                "source_section_id": _record_id(record, "section_id", "node_id"),
            })
        if misconceptions:
            briefs.append({
                "layout_id": "L08",
                "title": "常见误区",
                "key_message": "区分容易混淆的说法，并解释错误产生的原因",
                "source_index": 0,
                "source_section_id": _record_id(misconceptions[0], "section_id", "node_id"),
            })
        if practices:
            briefs.append({
                "layout_id": "L09",
                "title": "课堂练习",
                "key_message": "用一个可回答的问题检查是否真正理解",
                "source_index": 0,
                "source_section_id": _record_id(practices[0], "section_id", "node_id"),
            })
        briefs.append({
            "layout_id": "L10",
            "title": "小结与学习路径",
            "key_message": "回扣学习目标并指出下一步",
            "source_index": max(0, len(concept_records) - 1),
            "source_section_id": _record_id((concept_records or [{}])[-1], "section_id", "node_id"),
        })
        return briefs[:30]

    def _planned_slides(self, generation_id: str, briefs: list[dict[str, Any]], packet: Mapping[str, Any]) -> list[Slide]:
        slides: list[Slide] = []
        for index, brief in enumerate(briefs):
            refs = self._source_refs(
                packet,
                int(brief.get("source_index", index)),
                str(brief.get("source_section_id") or ""),
            )
            issues: list[QualityIssue] = []
            if not (refs.section_ids or refs.block_ids or refs.objective_ids or refs.asset_ids):
                issues.append(QualityIssue(
                    code="source_material_missing",
                    severity="blocking",
                    message="冻结来源中没有可绑定到该页的课程内容。",
                    target_type="slide",
                    target_id=f"{generation_id}-slide-{index + 1}",
                    fix_action="返回课程补充内容后重新创建课件",
                ))
            slides.append(Slide(
                slide_id=f"{generation_id}-slide-{index + 1}",
                position=index,
                layout_id=brief["layout_id"],
                status="planned",
                title=brief["title"],
                key_message=brief["key_message"],
                source_refs=refs,
                quality=SlideQuality(issues=issues),
            ))
        return slides

    async def prepare_generation(self, deck_id: str, request: GeneratePresentationRequest) -> GenerationSession:
        lock = self._prepare_locks.setdefault(deck_id, asyncio.Lock())
        async with lock:
            manifest = await self._manifest(deck_id)
            request_intent = {"deck_id": deck_id, "request": request.model_dump(mode="json")}
            receipt = await self._repo(
                "get_request_receipt",
                deck_id,
                request.request_id,
                operation="generate_presentation",
                fingerprint_payload=request_intent,
            )
            if receipt:
                generation_id = str(receipt.get("generation_id") or "")
                working_raw = await self._repo("load_working", deck_id, generation_id)
                if not generation_id or not working_raw:
                    raise PresentationServiceConflict("generation_receipt_invalid", "生成请求记录已损坏。")
                source = await self._repo("load_source_snapshot", deck_id)
                working = GenerationWorkingSnapshot.model_validate(working_raw)
                outline = [slide.model_dump(mode="json") for slide in working.slides]
                return GenerationSession(deck_id, manifest.course_id, generation_id, request, source, working, outline)

            self._check_expected(manifest, request.expected_revision_id)
            if manifest.active_generation_id:
                raise PresentationServiceConflict(
                    "generation_already_active",
                    "该课件已有正在进行的生成任务。",
                    details={"generation_id": manifest.active_generation_id},
                )
            source = await self._repo("load_source_snapshot", deck_id)
            packet = self._packet(source)
            generation_id = f"gen_{uuid4().hex}"
            briefs = self._curate(packet, request.page_budget, manifest.title)
            slides = self._planned_slides(generation_id, briefs, packet)
            working = GenerationWorkingSnapshot(
                generation_id=generation_id,
                deck_id=deck_id,
                slide_order=[slide.slide_id for slide in slides],
                slides=slides,
            )
            session = GenerationSession(deck_id, manifest.course_id, generation_id, request, source, working, briefs)
            await self._persist_event(session, "deck_outline", {
                "slide_order": [slide.slide_id for slide in slides],
                "slides": [slide.model_dump(mode="json") for slide in slides],
                "page_count": len(slides),
            })
            await self._repo("save_request_receipt", deck_id, request.request_id, {
                "request_id": request.request_id,
                "kind": "generation",
                "generation_id": generation_id,
                "created_at": utc_now(),
            }, operation="generate_presentation", fingerprint_payload=request_intent)
            key = (deck_id, generation_id)
            self._conditions.setdefault(key, asyncio.Condition())
            self._tasks[key] = asyncio.create_task(self._run_generation(session), name=f"presentation:{deck_id}:{generation_id}")
            return session

    async def _notify(self, deck_id: str, generation_id: str) -> None:
        condition = self._conditions.setdefault((deck_id, generation_id), asyncio.Condition())
        async with condition:
            condition.notify_all()

    async def _persist_event(
        self,
        session: GenerationSession,
        event_type: str,
        payload: Mapping[str, Any],
        *,
        revision_id: str | None = None,
        expected_revision_id: str | None = None,
        activate_quality_report: Any | None = None,
    ) -> PresentationEvent:
        # Callers may already have updated slide content.  The rollback image
        # therefore captures that content while retaining the last committed
        # sequence, so an event-log failure never creates a replay gap or loses
        # the generated page payload.
        previous_working = session.working.model_copy(deep=True)
        session.working.event_seq += 1
        session.working.updated_at = utc_now()
        try:
            await self._repo(
                "save_working",
                session.deck_id,
                session.working,
                expected_revision_id=expected_revision_id,
            )
        except Exception:
            # A failed precondition must not consume an in-memory sequence.  A
            # recovery error event can then reuse the next contiguous value.
            session.working = previous_working
            raise
        event = PresentationEvent(
            event_type=event_type,
            deck_id=session.deck_id,
            generation_id=session.generation_id,
            event_seq=session.working.event_seq,
            outline_revision=session.working.outline_revision,
            revision_id=revision_id,
            payload=dict(payload),
        )
        try:
            await self._repo("append_event", session.deck_id, event)
        except Exception:
            # save_working intentionally precedes append_event so subscribers
            # never observe an event whose slide content is not durable.  If
            # the append fails, restore the same content at the prior sequence
            # and let a retry reuse the contiguous event id.
            session.working = previous_working
            await self._repo(
                "save_working",
                session.deck_id,
                previous_working,
                expected_revision_id=expected_revision_id,
            )
            raise
        if activate_quality_report is not None:
            # Terminal visibility is a contract: by the time subscribers are
            # notified, the manifest must already point at the final quality
            # report and expose its quality_blocked/editing state.
            await self._repo(
                "save_quality",
                session.deck_id,
                activate_quality_report,
                expected_revision_id=expected_revision_id,
                activate=True,
            )
        await self._notify(session.deck_id, session.generation_id)
        return event

    async def replay_events(self, deck_id: str, generation_id: str, after_seq: int = 0) -> list[dict[str, Any]]:
        return await self._repo("replay_events", deck_id, generation_id, after_seq)

    async def stream_generation(
        self,
        deck_id: str,
        generation_id: str,
        *,
        after_seq: int = 0,
    ) -> AsyncIterator[dict[str, Any]]:
        last = max(0, int(after_seq))
        condition = self._conditions.setdefault((deck_id, generation_id), asyncio.Condition())
        terminal = {"generation_complete", "error"}
        while True:
            events = await self.replay_events(deck_id, generation_id, last)
            for event in events:
                sequence = int(event.get("event_seq") or 0)
                if sequence <= last:
                    continue
                last = sequence
                yield event
                if event.get("event_type") in terminal:
                    return
            task = self._tasks.get((deck_id, generation_id))
            if task is None and not events:
                return
            async with condition:
                try:
                    await asyncio.wait_for(condition.wait(), timeout=15.0)
                except TimeoutError:
                    continue

    async def _run_generation(self, session: GenerationSession) -> None:
        expected = session.request.expected_revision_id
        try:
            packet = self._packet(session.source_snapshot)
            ai = self.ai_factory() if self.ai_factory is not None else None
            semaphore = asyncio.Semaphore(self.max_page_concurrency)
            jobs = [self._fill_slide(slide, packet, ai, semaphore) for slide in session.working.slides]
            completed = 0
            fallback_count = 0
            for future in asyncio.as_completed(jobs):
                slide, used_fallback = await future
                latest_raw = await self._repo("load_working", session.deck_id, session.generation_id)
                if latest_raw:
                    session.working = GenerationWorkingSnapshot.model_validate(latest_raw)
                if slide.slide_id in session.working.cancelled_slot_ids:
                    continue
                replacements = {item.slide_id: item for item in session.working.slides}
                replacements[slide.slide_id] = slide
                session.working.slides = [replacements[slide_id] for slide_id in session.working.slide_order if slide_id in replacements]
                completed += 1
                fallback_count += int(used_fallback)
                await self._persist_event(
                    session,
                    "slide_upsert",
                    {"slide": slide.model_dump(mode="json"), "generation_mode": "deterministic_fallback" if used_fallback else "llm"},
                    expected_revision_id=expected,
                )
                await self._persist_event(
                    session,
                    "progress",
                    {"completed": completed, "total": len(jobs), "percent": round(completed / max(1, len(jobs)) * 100)},
                    expected_revision_id=expected,
                )

            latest_raw = await self._repo("load_working", session.deck_id, session.generation_id)
            if latest_raw:
                session.working = GenerationWorkingSnapshot.model_validate(latest_raw)
            slides = [slide for slide in session.working.slides if slide.slide_id not in session.working.cancelled_slot_ids]
            revision = DeckRevision(
                revision_id=f"rev_{uuid4().hex}",
                parent_revision_id=expected,
                deck_id=session.deck_id,
                reason="initial_generation",
                source_snapshot_id=(await self._manifest(session.deck_id)).source_ref.source_snapshot_id,
                slide_order=[slide.slide_id for slide in slides],
                slides=[slide.model_copy(update={"position": index}) for index, slide in enumerate(slides)],
            )
            manifest = await self._manifest(session.deck_id)
            report = evaluate_presentation_quality(manifest, revision, session.source_snapshot)
            await self._repo("append_revision", session.deck_id, revision, expected_revision_id=expected)
            expected = revision.revision_id
            await self._repo(
                "save_quality",
                session.deck_id,
                report,
                expected_revision_id=expected,
                activate=False,
            )
            await self._persist_event(
                session,
                "quality_report",
                {"report": report.model_dump(mode="json")},
                revision_id=revision.revision_id,
                expected_revision_id=expected,
            )
            await self._persist_event(
                session,
                "generation_complete",
                {
                    "revision_id": revision.revision_id,
                    "revision": revision.model_dump(mode="json"),
                    "revision_checksum": revision_checksum(revision),
                    "quality_status": report.status,
                    "fallback_page_count": fallback_count,
                    "page_count": len(revision.slides),
                },
                revision_id=revision.revision_id,
                expected_revision_id=expected,
                activate_quality_report=report,
            )
        except Exception as exc:  # the stream must end with a persisted domain error
            logger.exception("Presentation generation failed: %s", session.deck_id)
            try:
                error_payload = {"code": getattr(exc, "code", "generation_failed"), "message": str(exc)}
                try:
                    await self._persist_event(
                        session,
                        "error",
                        error_payload,
                        expected_revision_id=expected,
                    )
                except StaleRevisionConflict:
                    # A concurrent revision may invalidate the original
                    # precondition.  Persist the terminal error against the
                    # already-owned generation without changing active revision.
                    await self._persist_event(session, "error", error_payload)
            finally:
                clear = getattr(self.repository, "clear_active_generation", None)
                if clear is not None:
                    try:
                        manifest = await self._manifest(session.deck_id)
                        if manifest.active_generation_id == session.generation_id:
                            status = "editing" if manifest.active_revision_id else "failed"
                            await asyncio.to_thread(clear, session.deck_id, session.generation_id, status=status)
                    except Exception:
                        logger.exception("Failed to clear presentation generation: %s", session.deck_id)
        finally:
            self._tasks.pop((session.deck_id, session.generation_id), None)
            await self._notify(session.deck_id, session.generation_id)

    async def _fill_slide(
        self,
        slide: Slide,
        packet: Mapping[str, Any],
        ai: Any,
        semaphore: asyncio.Semaphore,
    ) -> tuple[Slide, bool]:
        if any(issue.severity == "blocking" for issue in slide.quality.issues):
            return slide.model_copy(update={"status": "failed"}), False
        page_packet = self._page_packet(slide, packet)
        if ai is None:
            return self._fallback_slide(slide, page_packet), True

        prompt = self._page_prompt(slide, page_packet)
        try:
            async with semaphore:
                response = await ai._call_llm(
                    prompt,
                    system_prompt=(
                        "你是灵知课件页面内容专家。只返回 JSON，不生成 CSS 或坐标；"
                        "内容必须基于给定来源，保持简洁、可讲授。"
                    ),
                    use_fast_model=True,
                    retry_count=1,
                    raise_on_error=True,
                )
        except Exception as exc:
            return self._failed_slide(slide, "model_unavailable", f"模型调用失败：{exc}"), False
        if response is None:
            return self._failed_slide(slide, "model_unavailable", "模型未返回页面内容，请检查当前 LLM 配置后重试。"), False
        parsed = ai._extract_json(response) if hasattr(ai, "_extract_json") else None
        if not isinstance(parsed, Mapping):
            try:
                parsed = json.loads(response)
            except (TypeError, json.JSONDecodeError):
                return self._failed_slide(slide, "invalid_model_payload", "模型未返回合法页面 JSON。"), False
        try:
            blocks = [
                SlideBlock.model_validate(item)
                for item in _normalize_model_blocks(slide.slide_id, parsed.get("blocks", []))
            ]
            candidate = slide.model_copy(update={
                "status": "ready",
                "title": _trim(str(parsed.get("title") or slide.title), 300),
                "subtitle": _trim(str(parsed.get("subtitle") or ""), 500),
                "key_message": _trim(str(parsed.get("key_message") or slide.key_message), 1000),
                "blocks": blocks,
                "speaker_notes": _trim(str(parsed.get("speaker_notes") or ""), 4000),
                "quality": SlideQuality(),
            })
            errors = validate_slide_capacity(
                candidate.layout_id,
                [block.model_dump(mode="json") for block in candidate.blocks],
                "\n".join([candidate.title, candidate.subtitle, candidate.key_message] + [block.content for block in candidate.blocks]),
            )
            if errors:
                return self._failed_slide(slide, "invalid_model_payload", "; ".join(errors)), False
            return candidate, False
        except Exception as exc:
            return self._failed_slide(slide, "invalid_model_payload", f"页面 JSON 不符合版式合同：{exc}"), False

    def _page_prompt(self, slide: Slide, packet: Mapping[str, Any]) -> str:
        blocks = _records(packet, "blocks", "content_blocks")
        objectives = _records(packet, "objectives", "learning_objectives")
        source_excerpt = "\n".join(_trim(_record_text(item), 700) for item in (blocks[:4] + objectives[:3]) if _record_text(item))
        layout = get_layout(slide.layout_id)
        return (
            f"页面版式：{slide.layout_id} {layout.label}\n"
            f"标题：{slide.title}\n核心信息：{slide.key_message}\n"
            f"允许 block type：{', '.join(layout.allowed_block_types)}；最多 {layout.max_blocks} 个 block。\n"
            f"课程来源：\n{source_excerpt}\n"
            "返回对象字段：title, subtitle, key_message, blocks, speaker_notes。"
            "每个 blocks 项字段为 block_id,type,title,content,items,metadata。"
        )

    @staticmethod
    def _failed_slide(slide: Slide, code: str, message: str) -> Slide:
        issue = QualityIssue(
            code=code,
            severity="blocking",
            message=message,
            target_type="slide",
            target_id=slide.slide_id,
            fix_action="检查模型配置后重新生成该页",
        )
        return slide.model_copy(update={"status": "failed", "blocks": [], "quality": SlideQuality(issues=[issue])})

    def _fallback_slide(self, slide: Slide, packet: Mapping[str, Any]) -> Slide:
        blocks = _records(packet, "blocks", "content_blocks")
        misconceptions = _records(packet, "misconceptions", "common_misconceptions")
        practices = _records(packet, "practices", "exercises", "questions")
        excerpts = [_trim(_record_text(item), 220) for item in blocks[:4] if _record_text(item)]
        excerpts = excerpts or [slide.key_message]
        block_list: list[SlideBlock] = []
        if slide.layout_id == "L01":
            block_list = []
        elif slide.layout_id in {"L02", "L04", "L06", "L10"}:
            block_list = [SlideBlock(
                block_id=f"{slide.slide_id}-fallback-1",
                type="bullets",
                title="关键内容",
                items=excerpts[:4],
                metadata={"generation_mode": "deterministic_fallback"},
            )]
        elif slide.layout_id == "L08":
            misconception = _record_text(misconceptions[0]) if misconceptions else "容易混淆的说法"
            block_list = [SlideBlock(
                block_id=f"{slide.slide_id}-fallback-1",
                type="comparison",
                title="辨析",
                content=_trim(misconception, 260),
                metadata={
                    "left": f"误区：{_trim(misconception, 180)}",
                    "right": f"正确理解：{_trim(excerpts[0], 180)}",
                    "generation_mode": "deterministic_fallback",
                },
            )]
        elif slide.layout_id == "L09":
            practice = _record_text(practices[0]) if practices else "请用自己的话解释本页核心概念。"
            block_list = [SlideBlock(
                block_id=f"{slide.slide_id}-fallback-1",
                type="exercise",
                title="课堂练习",
                content=_trim(practice, 320),
                items=[_trim(practice, 240)],
                metadata={"generation_mode": "deterministic_fallback"},
            )]
        else:
            allowed = get_layout(slide.layout_id).allowed_block_types
            block_list = [SlideBlock(
                block_id=f"{slide.slide_id}-fallback-1",
                type=allowed[0],
                title="课程要点",
                content=excerpts[0],
                metadata={"generation_mode": "deterministic_fallback"},
            )]
        warning = QualityIssue(
            code="deterministic_fallback_used",
            severity="warning",
            message="当前页由冻结课程来源确定性整理，未伪装为模型生成。",
            target_type="slide",
            target_id=slide.slide_id,
            fix_action="可在模型恢复后请求 AI 优化本页",
        )
        return slide.model_copy(update={
            "status": "ready",
            "blocks": block_list,
            "speaker_notes": f"本页依据冻结课程来源整理。讲授重点：{slide.key_message}",
            "quality": SlideQuality(issues=[warning]),
        })

    async def create_proposal(self, deck_id: str, request: ChatPresentationRequest) -> dict[str, Any]:
        manifest = await self._manifest(deck_id)
        self._check_expected(manifest, request.expected_revision_id)
        revision = DeckRevision.model_validate(await self._repo("get_revision", deck_id, request.expected_revision_id))
        slide_ids = request.slide_ids or (list(revision.slide_order) if request.scope == "deck" else [])
        if request.scope == "slide" and len(slide_ids) != 1:
            raise PresentationServiceError("当前页修改必须且只能选择一页")
        known = {slide.slide_id: slide for slide in revision.slides}
        if any(slide_id not in known for slide_id in slide_ids):
            raise PresentationServiceError("修改范围包含不存在的页面")
        ai = self.ai_factory() if self.ai_factory is not None else None
        patch_results = await asyncio.gather(*[
            self._proposal_patch_with_ai(known[slide_id], request.prompt, ai)
            for slide_id in slide_ids
        ])
        patches = [item[0] for item in patch_results]
        fallback_count = sum(int(item[1]) for item in patch_results)
        proposal = DeckProposal(
            proposal_id=f"proposal_{uuid4().hex}",
            request_id=request.request_id,
            deck_id=deck_id,
            base_revision_id=revision.revision_id,
            scope=request.scope,
            slide_ids=slide_ids,
            prompt=request.prompt,
            patches=patches,
            summary=(
                f"建议修改 {len(patches)} 页；课程来源锚点保持不变。"
                + (f" 其中 {fallback_count} 页使用确定性建议。" if fallback_count else "")
            ),
            risks=["应用后旧导出文件会变为过期，需要重新完成课件。"],
        )
        return await self._repo("save_proposal", deck_id, proposal)

    async def _proposal_patch_with_ai(self, slide: Slide, prompt: str, ai: Any) -> tuple[dict[str, Any], bool]:
        if ai is None:
            return self._proposal_patch(slide, prompt), True
        request_payload = {
            "slide": slide.model_dump(mode="json", exclude={"source_refs", "quality"}),
            "instruction": prompt,
            "allowed_fields": ["title", "subtitle", "key_message", "blocks", "speaker_notes", "layout_id"],
        }
        try:
            async with self._patch_semaphore:
                response = await ai._call_llm(
                    json.dumps(request_payload, ensure_ascii=False),
                    system_prompt=(
                        "你是灵知课件修改专家。只返回 JSON：{changes:{...}}。"
                        "不得修改 slide_id、position、课程来源、模板或其他页面。"
                    ),
                    use_fast_model=True,
                    retry_count=1,
                )
        except Exception:
            response = None
        if response:
            parsed = ai._extract_json(response) if hasattr(ai, "_extract_json") else None
            if isinstance(parsed, Mapping):
                raw_changes = parsed.get("changes", parsed)
                allowed = {"title", "subtitle", "key_message", "blocks", "speaker_notes", "layout_id"}
                if isinstance(raw_changes, Mapping) and raw_changes and not (set(raw_changes) - allowed):
                    changes = dict(raw_changes)
                    try:
                        candidate_raw = slide.model_dump(mode="json")
                        candidate_raw.update(changes)
                        candidate_raw["slide_id"] = slide.slide_id
                        candidate_raw["position"] = slide.position
                        candidate_raw["source_refs"] = slide.source_refs.model_dump(mode="json")
                        candidate = Slide.model_validate(candidate_raw)
                        errors = validate_slide_capacity(
                            candidate.layout_id,
                            [block.model_dump(mode="json") for block in candidate.blocks],
                            "\n".join(
                                [candidate.title, candidate.subtitle, candidate.key_message]
                                + [block.content for block in candidate.blocks]
                            ),
                        )
                        if not errors:
                            return {"slide_id": slide.slide_id, "changes": changes}, False
                    except Exception:
                        pass
        return self._proposal_patch(slide, prompt), True

    @staticmethod
    def _proposal_patch(slide: Slide, prompt: str) -> dict[str, Any]:
        changes: dict[str, Any] = {}
        if "精简" in prompt:
            changes["blocks"] = [
                block.model_copy(update={
                    "content": _trim(block.content, 260),
                    "items": block.items[:4],
                }).model_dump(mode="json")
                for block in slide.blocks[:2]
            ]
            changes["key_message"] = _trim(slide.key_message, 120)
        elif "误区" in prompt or "易错" in prompt:
            changes["layout_id"] = "L08"
            changes["blocks"] = [SlideBlock(
                block_id=f"{slide.slide_id}-proposal-misconception",
                type="comparison",
                title="易错点辨析",
                content=prompt,
                metadata={"left": "常见误解", "right": "正确理解与原因"},
            ).model_dump(mode="json")]
        elif "练习" in prompt or "互动" in prompt:
            changes["layout_id"] = "L09"
            changes["blocks"] = [SlideBlock(
                block_id=f"{slide.slide_id}-proposal-practice",
                type="exercise",
                title="课堂练习",
                content=prompt,
                items=["先独立判断", "再说明依据", "最后核对课程来源"],
            ).model_dump(mode="json")]
        else:
            layout = get_layout(slide.layout_id)
            block_type = "callout" if "callout" in layout.allowed_block_types else layout.allowed_block_types[0]
            existing = [block.model_dump(mode="json") for block in slide.blocks]
            if len(existing) >= layout.max_blocks:
                existing = existing[: max(0, layout.max_blocks - 1)]
            existing.append(SlideBlock(
                block_id=f"{slide.slide_id}-proposal-{uuid4().hex[:8]}",
                type=block_type,
                title="补充说明" if "例" not in prompt else "补充例子",
                content=_trim(prompt, 360),
            ).model_dump(mode="json"))
            changes["blocks"] = existing
        changes["speaker_notes"] = _trim((slide.speaker_notes + "\n修改意图：" + prompt).strip(), 4000)
        return {"slide_id": slide.slide_id, "changes": changes}

    async def apply_proposal(self, deck_id: str, proposal_id: str, command: RevisionCommand) -> dict[str, Any]:
        prior = await self._repo("get_command_receipt", deck_id, command.command_id)
        if prior:
            if (
                prior.get("operation") != "apply_proposal"
                or prior.get("proposal_id") != proposal_id
                or prior.get("expected_revision_id") != command.expected_revision_id
            ):
                raise self._command_reused(command.command_id, "apply_proposal")
            return prior
        manifest = await self._manifest(deck_id)
        self._check_expected(manifest, command.expected_revision_id)
        self._check_generation_idle(manifest)
        proposal = DeckProposal.model_validate(await self._repo("get_proposal", deck_id, proposal_id))
        if proposal.base_revision_id != command.expected_revision_id:
            raise PresentationServiceConflict("stale_proposal", "该修改建议基于旧版本，请重新生成建议。")
        revision = DeckRevision.model_validate(await self._repo("get_revision", deck_id, command.expected_revision_id))
        allowed = {"title", "subtitle", "key_message", "blocks", "speaker_notes", "layout_id"}
        patches: dict[str, dict[str, Any]] = {}
        for patch in proposal.patches:
            slide_id = str(patch.get("slide_id") or "")
            changes = patch.get("changes")
            if slide_id not in proposal.slide_ids or not isinstance(changes, Mapping) or set(changes) - allowed:
                raise PresentationServiceError("修改建议包含越权字段")
            patches[slide_id] = dict(changes)
        new_slides: list[Slide] = []
        for slide in revision.slides:
            if slide.slide_id not in patches:
                new_slides.append(slide)
                continue
            data = slide.model_dump(mode="json")
            data.update(patches[slide.slide_id])
            data["slide_id"] = slide.slide_id
            data["position"] = slide.position
            data["source_refs"] = slide.source_refs.model_dump(mode="json")
            candidate = Slide.model_validate(data)
            errors = validate_slide_capacity(
                candidate.layout_id,
                [block.model_dump(mode="json") for block in candidate.blocks],
                "\n".join([candidate.title, candidate.subtitle, candidate.key_message] + [block.content for block in candidate.blocks]),
            )
            if errors:
                raise PresentationServiceError("修改后页面超过版式容量", details=errors)
            new_slides.append(candidate)
        updated = DeckRevision(
            revision_id=f"rev_{uuid4().hex}",
            parent_revision_id=revision.revision_id,
            deck_id=deck_id,
            reason="chat_patch",
            source_snapshot_id=revision.source_snapshot_id,
            slide_order=revision.slide_order,
            slides=new_slides,
        )
        receipt = await self._repo(
            "append_revision",
            deck_id,
            updated,
            expected_revision_id=command.expected_revision_id,
            command_id=command.command_id,
            command_operation="apply_proposal",
            command_metadata={
                "proposal_id": proposal_id,
                "expected_revision_id": command.expected_revision_id,
            },
        )
        update_status = getattr(self.repository, "update_proposal_status", None)
        if update_status is not None:
            await asyncio.to_thread(update_status, deck_id, proposal_id, "applied")
        return receipt

    async def restore_revision(self, deck_id: str, source_revision_id: str, command: RevisionCommand) -> dict[str, Any]:
        prior = await self._repo("get_command_receipt", deck_id, command.command_id)
        if prior:
            if (
                prior.get("operation") != "restore_revision"
                or prior.get("restored_from_revision_id") != source_revision_id
                or prior.get("expected_revision_id") != command.expected_revision_id
            ):
                raise self._command_reused(command.command_id, "restore_revision")
            return prior
        manifest = await self._manifest(deck_id)
        self._check_expected(manifest, command.expected_revision_id)
        self._check_generation_idle(manifest)
        return await self._repo(
            "restore_revision",
            deck_id,
            source_revision_id,
            expected_revision_id=command.expected_revision_id,
            command_id=command.command_id,
        )

    async def finalize_presentation(self, deck_id: str, request: FinalizePresentationRequest) -> dict[str, Any]:
        prior = await self._repo("get_command_receipt", deck_id, request.command_id)
        if prior:
            artifact_id = str(prior.get("artifact_id") or "")
            if artifact_id:
                if prior.get("revision_id") != request.expected_revision_id:
                    raise self._command_reused(request.command_id, "finalize_presentation")
                return {"artifact": await self._repo("get_artifact", artifact_id), "command_receipt": prior}
            raise self._command_reused(request.command_id, "finalize_presentation")
        manifest = await self._manifest(deck_id)
        self._check_expected(manifest, request.expected_revision_id)
        self._check_generation_idle(manifest)
        revision = DeckRevision.model_validate(await self._repo("get_revision", deck_id, request.expected_revision_id))
        source = await self._repo("load_source_snapshot", deck_id)
        report = evaluate_presentation_quality(
            manifest,
            revision,
            source,
            render_measurement=request.render_measurement,
            require_publication=True,
            require_render_measurement=True,
        )
        await self._repo(
            "save_quality",
            deck_id,
            report,
            expected_revision_id=request.expected_revision_id,
        )
        if report.status == "blocked":
            raise PresentationQualityBlocked(report.model_dump(mode="json"))

        artifact_id = f"artifact_{uuid4().hex}"
        artifact_dir = await self._repo("artifact_directory", deck_id, artifact_id)
        try:
            rendered = await asyncio.to_thread(self.renderer, revision, manifest.template_id, artifact_dir)
            expected_page_count = len(revision.slides)
            expected_title_digest = title_digest(revision.slides)
            expected_notes_digest = speaker_notes_digest(revision.slides)
            if int(rendered.get("page_count") or 0) != expected_page_count:
                raise ValueError("artifact_page_count_mismatch")
            if str(rendered.get("title_digest") or "") != expected_title_digest:
                raise ValueError("artifact_title_digest_mismatch")
            if str(rendered.get("speaker_notes_digest") or "") != expected_notes_digest:
                raise ValueError("artifact_speaker_notes_digest_mismatch")
            receipt = ArtifactReceipt(
                artifact_id=artifact_id,
                deck_id=deck_id,
                revision_id=revision.revision_id,
                source_snapshot_id=revision.source_snapshot_id,
                template_id=manifest.template_id,
                template_version=str(rendered["template_version"]),
                layout_registry_version=str(rendered["layout_registry_version"]),
                html_path=str(rendered["html_path"]),
                html_sha256=str(rendered["html_sha256"]),
                pptx_path=str(rendered["pptx_path"]),
                pptx_sha256=str(rendered["pptx_sha256"]),
                page_count=int(rendered["page_count"]),
                title_digest=str(rendered["title_digest"]),
                speaker_notes_digest=str(rendered["speaker_notes_digest"]),
                quality_report_id=report.report_id,
            )
            command_receipt = await self._repo(
                "save_artifact",
                deck_id,
                receipt,
                expected_revision_id=request.expected_revision_id,
                command_id=request.command_id,
            )
            command_receipt = {
                **command_receipt,
                "operation": "finalize_presentation",
                "expected_revision_id": request.expected_revision_id,
            }
            await self._repo(
                "save_command_receipt",
                deck_id,
                request.command_id,
                command_receipt,
                overwrite=True,
            )
            stored = await self._repo("get_artifact", artifact_id)
        except StaleRevisionConflict:
            raise
        except Exception as exc:
            render_issue = QualityIssue(
                code="artifact_render_failed",
                severity="blocking",
                message=f"HTML/PPTX 产物生成或对账失败：{exc}",
                target_type="artifact",
                fix_action="检查字体与渲染依赖后重试完成课件",
            )
            blocked = report.model_copy(update={
                "report_id": f"qr_{uuid4().hex}",
                "status": "blocked",
                "issues": report.issues + [render_issue],
                "checked_at": utc_now(),
            })
            await self._repo(
                "save_quality",
                deck_id,
                blocked,
                expected_revision_id=request.expected_revision_id,
            )
            raise PresentationQualityBlocked(blocked.model_dump(mode="json")) from exc

        working_raw = await self._repo("load_working", deck_id)
        generation_id = f"finalize_{artifact_id}"
        sequence = 1
        outline_revision = 1
        if working_raw:
            working = GenerationWorkingSnapshot.model_validate(working_raw)
            generation_id = working.generation_id
            sequence = working.event_seq + 1
            outline_revision = working.outline_revision
        event = PresentationEvent(
            event_type="export_ready",
            deck_id=deck_id,
            generation_id=generation_id,
            event_seq=sequence,
            outline_revision=outline_revision,
            revision_id=revision.revision_id,
            payload={"artifact": stored},
        )
        await self._repo("append_event", deck_id, event)
        return {
            "artifact": stored,
            "quality_report": report.model_dump(mode="json"),
            "command_receipt": command_receipt,
            "event": event.model_dump(mode="json"),
        }

    async def resolve_artifact(self, artifact_id: str, kind: str) -> Path:
        if kind not in {"html", "pptx"}:
            raise PresentationServiceError("不支持的课件产物类型")
        return Path(await self._repo("resolve_artifact_file", artifact_id, kind))


__all__ = [
    "GenerationSession",
    "PresentationQualityBlocked",
    "PresentationService",
    "PresentationServiceConflict",
    "PresentationServiceError",
]
