"""Versioned learning assets and event-backed practice APIs."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from course_learning_availability import project_course_learning_availability
from course_knowledge_map import project_learning_assets_to_knowledge
from dependencies import get_course_or_404
from learner_context import require_user_id
from learning_assets import compile_learning_asset_plan, evaluate_learning_asset_quality
from learning_events import (
    migrate_legacy_learning_state,
    record_learning_event,
)
from learning_progress import build_learning_progress, project_learning_objective_bindings

router = APIRouter(prefix="/courses/{course_id}/learning-assets", tags=["learning_assets"])

INTERNAL_ASSET_TYPES = {"course_knowledge_base", "course_knowledge_map"}


class CriterionConfirmation(BaseModel):
    confirmed: bool = True


@router.get("")
async def get_learning_assets(course_id: str, request: Request, node_id: str | None = None):
    course = project_learning_objective_bindings(await get_course_or_404(course_id))
    user_id = require_user_id(request.headers.get("X-User-Id"))
    migrate_legacy_learning_state(course)
    assets = project_learning_assets_to_knowledge(
        course,
        deepcopy(course.get("learning_assets") or {}),
    )
    quality_report = evaluate_learning_asset_quality(
        course,
        compile_learning_asset_plan(course),
        assets,
    )
    filtered = _public_learning_assets(assets, node_id=node_id)
    filtered["checklist"] = _project_checklist(
        course,
        filtered.get("checklist") or [],
        user_id=user_id,
    )
    return {
        "schema_version": "learning_assets_api_v1",
        "course_id": course_id,
        "course_version_id": course.get("current_course_version_id"),
        "bundle_revision_id": course.get("learning_asset_bundle_revision_id"),
        "plan": course.get("learning_asset_plan") or {},
        "quality_report": quality_report,
        "course_availability": project_course_learning_availability(course),
        "assets": filtered,
    }


@router.get("/practice")
async def get_practice(course_id: str, node_id: str | None = None):
    course = project_learning_objective_bindings(await get_course_or_404(course_id))
    assets = project_learning_assets_to_knowledge(
        course,
        deepcopy(course.get("learning_assets") or {}),
    )
    questions = [
        item for item in assets.get("questions") or []
        if not node_id or item.get("node_id") == node_id
    ]
    return {
        "course_id": course_id,
        "course_version_id": course.get("current_course_version_id"),
        "node_id": node_id,
        "questions": questions,
    }


@router.post("/criteria/{criterion_revision_id}/confirm")
async def confirm_criterion(
    course_id: str,
    criterion_revision_id: str,
    confirmation: CriterionConfirmation,
    request: Request,
):
    course = project_learning_objective_bindings(await get_course_or_404(course_id))
    learning_assets = project_learning_assets_to_knowledge(
        course,
        deepcopy(course.get("learning_assets") or {}),
    )
    criterion = _find_by_revision(
        learning_assets.get("mastery_criteria") or [],
        criterion_revision_id,
    )
    if not criterion:
        raise HTTPException(status_code=404, detail="Mastery criterion revision not found")
    event = record_learning_event(
        event_type="mastery_self_confirmed",
        actor="user",
        source="learning_assets.checklist",
        user_id=require_user_id(request.headers.get("X-User-Id")),
        course_id=course_id,
        course_version_id=course.get("current_course_version_id"),
        node_id=criterion.get("node_id"),
        objective_id=criterion.get("objective_id"),
        objective_revision_id=criterion.get("objective_revision_id"),
        criterion_id=criterion.get("criterion_id"),
        criterion_revision_id=criterion_revision_id,
        concept_ids=criterion.get("concept_ids") or [],
        skill_unit_ids=criterion.get("skill_unit_ids") or [],
        mistake_point_ids=criterion.get("mistake_point_ids") or [],
        evidence={"confirmed": confirmation.confirmed},
        result={"status": "self_confirmed" if confirmation.confirmed else "not_started"},
    )
    return {"status": "recorded", "event_id": event["event_id"]}


def _public_learning_assets(
    assets: dict[str, Any],
    *,
    node_id: str | None,
) -> dict[str, list[dict[str, Any]]]:
    """Expose learning products, not internal compilation and governance models."""
    return {
        asset_type: [
            item for item in values
            if not node_id or not item.get("node_id") or item.get("node_id") == node_id
        ]
        for asset_type, values in assets.items()
        if isinstance(values, list) and asset_type not in INTERNAL_ASSET_TYPES
    }


def _find_by_revision(items: list[dict[str, Any]], revision_id: str) -> dict[str, Any] | None:
    return next((item for item in items if item.get("revision_id") == revision_id), None)


def _project_checklist(
    course: dict[str, Any],
    checklist: list[dict[str, Any]],
    *,
    user_id: str,
) -> list[dict[str, Any]]:
    progress = build_learning_progress(course, user_id=user_id)
    criterion_states = {
        str(state.get("criterion_revision_id") or ""): state
        for node in progress.get("nodes") or []
        for state in node.get("criterion_states") or []
    }
    result = []
    for item in checklist:
        projected = dict(item)
        state = criterion_states.get(str(item.get("criterion_revision_id") or ""))
        if state:
            projected["status"] = state.get("status", projected.get("status", "not_started"))
            projected["latest_score"] = state.get("latest_score")
            projected["evidence_event_id"] = state.get("evidence_event_id")
        result.append(projected)
    return result


__all__ = ["router"]
