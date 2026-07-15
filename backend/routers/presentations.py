"""HTTP and SSE surface for the Lingzhi courseware workbench."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse

from presentation_generation import (
    PresentationQualityBlocked,
    PresentationService,
    PresentationServiceError,
)
from presentation_models import (
    ChatPresentationRequest,
    CreatePresentationRequest,
    FinalizePresentationRequest,
    GeneratePresentationRequest,
    RevisionCommand,
)
from presentation_quality import revision_checksum


router = APIRouter(tags=["presentations"])
_service: PresentationService | None = None


def configure_presentation_service(service: PresentationService | None) -> None:
    """Install an explicit service for tests or application composition."""

    global _service
    _service = service


def get_presentation_service() -> PresentationService:
    global _service
    if _service is None:
        from presentation_repository import presentation_repository
        from presentation_source import project_presentation_source, source_packet
        from storage import storage

        _service = PresentationService(
            presentation_repository,
            course_loader=storage.load_course,
            source_projector=project_presentation_source,
            source_packet_builder=source_packet,
        )
    return _service


def _detail(code: str, message: str, details: Any = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        payload["details"] = details
    return payload


def _translate_exception(exc: Exception) -> HTTPException:
    if isinstance(exc, PresentationQualityBlocked):
        return HTTPException(
            status_code=exc.status_code,
            detail=_detail(exc.code, str(exc), exc.report),
        )
    if isinstance(exc, PresentationServiceError):
        return HTTPException(
            status_code=exc.status_code,
            detail=_detail(exc.code, str(exc), exc.details),
        )
    try:
        from presentation_repository import (
            ArtifactAccessError,
            PresentationRepositoryConflict,
            StaleRevisionConflict,
        )

        if isinstance(exc, ArtifactAccessError):
            return HTTPException(status_code=400, detail=_detail("artifact_access_rejected", str(exc)))
        if isinstance(exc, StaleRevisionConflict):
            return HTTPException(status_code=409, detail=_detail("stale_revision", str(exc)))
        if isinstance(exc, PresentationRepositoryConflict):
            code = str(exc).split(":", 1)[0] or "presentation_conflict"
            return HTTPException(status_code=409, detail=_detail(code, str(exc)))
    except ImportError:
        pass
    if isinstance(exc, KeyError):
        return HTTPException(status_code=404, detail=_detail("presentation_not_found", str(exc)))
    if isinstance(exc, (TypeError, ValueError)):
        return HTTPException(status_code=422, detail=_detail("presentation_validation_failed", str(exc)))
    return HTTPException(status_code=500, detail=_detail("presentation_internal_error", "课件服务暂时不可用"))


def _deck_envelope(raw: dict[str, Any]) -> dict[str, Any]:
    if "manifest" in raw:
        revision = raw.get("active_revision")
        return {
            "deck": raw.get("manifest"),
            "revision": revision,
            "revision_checksum": revision_checksum(revision) if isinstance(revision, dict) else None,
            "working": raw.get("working"),
            "quality": raw.get("quality"),
            "artifact": _artifact_urls(raw.get("artifact")),
        }
    return {"deck": raw, "revision": None, "revision_checksum": None, "working": None, "quality": None, "artifact": None}


def _artifact_urls(artifact: Any) -> Any:
    if not isinstance(artifact, dict):
        return artifact
    result = dict(artifact)
    artifact_id = str(result.get("artifact_id") or "")
    if artifact_id:
        result["html_url"] = f"/api/presentation-artifacts/{artifact_id}/html"
        result["pptx_url"] = f"/api/presentation-artifacts/{artifact_id}/pptx"
    return result


def _after_sequence(last_event_id: str | None, fallback: int, expected_generation_id: str) -> int:
    if not last_event_id:
        return max(0, fallback)
    try:
        generation_id, raw_sequence = last_event_id.rsplit(":", 1)
        if generation_id != expected_generation_id:
            return max(0, fallback)
        return max(0, int(raw_sequence))
    except ValueError:
        return max(0, fallback)


def _sse(event: dict[str, Any]) -> str:
    generation_id = str(event.get("generation_id") or "generation")
    sequence = int(event.get("event_seq") or 0)
    event_type = str(event.get("event_type") or "message")
    data = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
    return f"id: {generation_id}:{sequence}\nevent: {event_type}\ndata: {data}\n\n"


async def _stream_events(
    service: PresentationService,
    deck_id: str,
    generation_id: str,
    after_seq: int,
) -> AsyncIterator[str]:
    async for event in service.stream_generation(deck_id, generation_id, after_seq=after_seq):
        yield _sse(event)


@router.post("/courses/{course_id}/presentations", status_code=201)
async def create_presentation(course_id: str, request: CreatePresentationRequest):
    service = get_presentation_service()
    try:
        manifest = await service.create_presentation(course_id, request)
        return _deck_envelope(manifest)
    except Exception as exc:
        raise _translate_exception(exc) from exc


@router.get("/courses/{course_id}/presentations")
async def list_presentations(course_id: str):
    try:
        decks = await get_presentation_service().list_presentations(course_id)
        return {"decks": decks}
    except Exception as exc:
        raise _translate_exception(exc) from exc


@router.get("/presentations/{deck_id}")
async def get_presentation(deck_id: str):
    try:
        return _deck_envelope(await get_presentation_service().get_presentation(deck_id))
    except Exception as exc:
        raise _translate_exception(exc) from exc


@router.post("/presentations/{deck_id}/generate")
async def generate_presentation(
    deck_id: str,
    request: GeneratePresentationRequest,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
):
    service = get_presentation_service()
    try:
        session = await service.prepare_generation(deck_id, request)
        after_seq = _after_sequence(last_event_id, 0, session.generation_id)
        return StreamingResponse(
            _stream_events(service, deck_id, session.generation_id, after_seq),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    except Exception as exc:
        raise _translate_exception(exc) from exc


@router.get("/presentations/{deck_id}/events")
async def replay_presentation_events(
    deck_id: str,
    generation_id: str = Query(min_length=1),
    after_seq: int = Query(default=0, ge=0),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
):
    service = get_presentation_service()
    try:
        sequence = _after_sequence(last_event_id, after_seq, generation_id)
        return StreamingResponse(
            _stream_events(service, deck_id, generation_id, sequence),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    except Exception as exc:
        raise _translate_exception(exc) from exc


@router.post("/presentations/{deck_id}/chat", status_code=201)
async def create_presentation_proposal(deck_id: str, request: ChatPresentationRequest):
    try:
        proposal = await get_presentation_service().create_proposal(deck_id, request)
        return {"proposal": proposal}
    except Exception as exc:
        raise _translate_exception(exc) from exc


@router.post("/presentations/{deck_id}/patches/{proposal_id}/apply")
async def apply_presentation_proposal(deck_id: str, proposal_id: str, command: RevisionCommand):
    service = get_presentation_service()
    try:
        receipt = await service.apply_proposal(deck_id, proposal_id, command)
        state = await service.get_presentation(deck_id)
        result = _deck_envelope(state)
        result["receipt"] = receipt
        return result
    except Exception as exc:
        raise _translate_exception(exc) from exc


@router.post("/presentations/{deck_id}/revisions/{revision_id}/restore")
async def restore_presentation_revision(deck_id: str, revision_id: str, command: RevisionCommand):
    service = get_presentation_service()
    try:
        receipt = await service.restore_revision(deck_id, revision_id, command)
        state = await service.get_presentation(deck_id)
        result = _deck_envelope(state)
        result["receipt"] = receipt
        return result
    except Exception as exc:
        raise _translate_exception(exc) from exc


@router.post("/presentations/{deck_id}/finalize")
async def finalize_presentation(deck_id: str, request: FinalizePresentationRequest):
    service = get_presentation_service()
    try:
        result = await service.finalize_presentation(deck_id, request)
        state = _deck_envelope(await service.get_presentation(deck_id))
        state["artifact"] = _artifact_urls(result.get("artifact") or state.get("artifact"))
        state["quality"] = result.get("quality_report") or state.get("quality")
        state["receipt"] = result.get("command_receipt")
        state["event"] = result.get("event")
        return state
    except Exception as exc:
        raise _translate_exception(exc) from exc


@router.get("/presentation-artifacts/{artifact_id}/html")
async def get_presentation_html(artifact_id: str):
    try:
        path = await get_presentation_service().resolve_artifact(artifact_id, "html")
        return FileResponse(path, media_type="text/html; charset=utf-8", filename="deck.html", content_disposition_type="inline")
    except Exception as exc:
        raise _translate_exception(exc) from exc


@router.get("/presentation-artifacts/{artifact_id}/pptx")
async def get_presentation_pptx(artifact_id: str):
    try:
        path = await get_presentation_service().resolve_artifact(artifact_id, "pptx")
        return FileResponse(
            path,
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            filename="lingzhi-courseware.pptx",
        )
    except Exception as exc:
        raise _translate_exception(exc) from exc


__all__ = ["configure_presentation_service", "get_presentation_service", "router"]
