"""Real teacher teaching-calendar endpoints."""

from __future__ import annotations

import hashlib
from datetime import date as calendar_date
from datetime import time as clock_time
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field, model_validator

from dependencies import get_course_or_404, get_task_manager_optional
from learner_context import require_user_id
from teaching_calendar import (
    TeachingCalendarConflict,
    TeachingCalendarError,
    TeachingCalendarValidationError,
    teaching_calendar_repository,
)


router = APIRouter(tags=["teaching_calendar"])


class ClassSessionInput(BaseModel):
    session_id: str | None = None
    lesson_unit_id: str | None = None
    sequence: int = Field(default=1, ge=1)
    date: calendar_date | None = None
    start_time: clock_time | None = None
    end_time: clock_time | None = None
    content_summary: str = Field(min_length=1, max_length=2000)
    requirements: str = Field(default="", max_length=4000)
    location: str = Field(default="", max_length=240)
    teacher_name: str = Field(default="", max_length=240)
    teaching_type: str = Field(default="理论课", max_length=120)
    group_code: str = Field(default="", max_length=120)
    credit_hours: float | None = Field(default=None, ge=0, le=24)
    notes: str = Field(default="", max_length=2000)
    status: Literal["unscheduled", "scheduled", "cancelled"] = "unscheduled"
    source: Literal["manual", "outline", "import"] = "manual"

    @model_validator(mode="after")
    def validate_times(self):
        if (self.start_time is None) != (self.end_time is None):
            raise ValueError("开始时间和结束时间必须同时填写")
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValueError("结束时间必须晚于开始时间")
        if self.date and self.status == "unscheduled":
            self.status = "scheduled"
        if not self.date and self.status == "scheduled":
            raise ValueError("已排课课次必须填写日期")
        return self


class TeachingCalendarUpdate(BaseModel):
    base_revision: int = Field(ge=0)
    course_title: str = Field(default="", max_length=240)
    academic_year: str = Field(default="", max_length=80)
    term: str = Field(default="", max_length=80)
    timezone: str = Field(default="Asia/Shanghai", max_length=80)
    status: Literal["draft", "ready"] = "draft"
    source_outline_revision: str = Field(default="", max_length=240)
    sessions: list[ClassSessionInput] = Field(default_factory=list, max_length=500)


def _identity(request: Request) -> str:
    return require_user_id(request.headers.get("X-User-Id"))


def _course_title(course: dict[str, Any]) -> str:
    return str(course.get("course_name") or course.get("title") or "未命名课程")


def _flatten_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    stack = list(nodes)
    while stack:
        node = stack.pop(0)
        if not isinstance(node, dict):
            continue
        result.append(node)
        children = node.get("children") or []
        if isinstance(children, list):
            stack[0:0] = children
    return result


def _lesson_nodes(course: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = _flatten_nodes(list(course.get("nodes") or []))
    parent_ids = {str(node.get("parent_node_id") or "") for node in nodes if node.get("parent_node_id")}
    leaves = [node for node in nodes if str(node.get("node_id") or "") not in parent_ids and not node.get("children")]
    if leaves:
        return leaves
    max_level = max((int(node.get("node_level") or 0) for node in nodes), default=0)
    return [node for node in nodes if int(node.get("node_level") or 0) == max_level]


def _expected_session_count(course: dict[str, Any]) -> int | None:
    request = course.get("generation_request") or {}
    brief = request.get("teacher_course_brief") or course.get("teacher_course_brief") or {}
    explicit = brief.get("expected_session_count") or brief.get("session_count")
    if explicit:
        try:
            value = int(explicit)
            return value if value > 0 else None
        except (TypeError, ValueError):
            return None

    # A Chinese university credit hour is normally 45 minutes.  The creation
    # form already collects total class hours and lesson duration, so retain
    # that intent even when an older generation request did not persist the
    # explicit expected-session field.
    try:
        total_class_hours = float(brief.get("total_class_hours") or 0)
        lesson_duration_minutes = float(brief.get("lesson_duration_minutes") or 0)
    except (TypeError, ValueError):
        return None
    if total_class_hours <= 0 or lesson_duration_minutes <= 0:
        return None
    value = round(total_class_hours * 45 / lesson_duration_minutes)
    return value if value > 0 else None


def _calendar_units(course: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = _flatten_nodes(list(course.get("nodes") or []))
    expected_count = _expected_session_count(course)
    top_level = [
        node
        for node in nodes
        if int(node.get("node_level") or 0) == 1
        and str(node.get("parent_node_id") or "root") in {"", "root"}
    ]
    # One generated chapter can contain several knowledge sections while still
    # representing one class meeting.  Prefer the chapter projection only when
    # it exactly matches the teacher's requested meeting count; otherwise keep
    # the historical leaf-node behavior.
    if expected_count and len(top_level) == expected_count:
        return top_level
    return _lesson_nodes(course)


def _unit_requirements(course: dict[str, Any], node: dict[str, Any]) -> str:
    direct = str(node.get("learning_objective") or "").strip()
    if direct:
        return direct
    node_id = str(node.get("node_id") or "")
    children = [
        child
        for child in _flatten_nodes(list(course.get("nodes") or []))
        if str(child.get("parent_node_id") or "") == node_id
    ]
    objectives = [
        str(child.get("learning_objective") or child.get("node_name") or "").strip()
        for child in children
    ]
    return "；".join(value for value in objectives if value)[:4000]


def _outline_source(course_id: str, course: dict[str, Any]) -> dict[str, Any]:
    """Prefer the active AI-generation projection until the course is published."""
    manager = get_task_manager_optional()
    if manager is None:
        return course
    try:
        preview = manager.get_generation_preview(course_id)
    except Exception:
        return course
    if not isinstance(preview, dict) or not preview.get("nodes"):
        return course
    if len(_flatten_nodes(list(preview.get("nodes") or []))) <= len(
        _flatten_nodes(list(course.get("nodes") or []))
    ):
        return course
    return {
        **course,
        **preview,
        "generation_request": course.get("generation_request") or preview.get("generation_request") or {},
    }


def _calendar_metadata(course: dict[str, Any]) -> tuple[str, str]:
    request = course.get("generation_request") or {}
    brief = request.get("teacher_course_brief") or course.get("teacher_course_brief") or {}
    academic_term = str(brief.get("academic_term") or "").strip()
    if not academic_term:
        return "", ""
    parts = academic_term.replace("—", "-").replace("–", "-").split(maxsplit=1)
    if len(parts) == 1:
        if "-" in parts[0]:
            return parts[0], ""
        return "", parts[0]
    return parts[0], parts[1]


def _apply_calendar_defaults(calendar: dict[str, Any], course: dict[str, Any]) -> dict[str, Any]:
    result = dict(calendar)
    academic_year, term = _calendar_metadata(course)
    result["course_title"] = result.get("course_title") or _course_title(course)
    result["academic_year"] = result.get("academic_year") or academic_year
    result["term"] = result.get("term") or term
    return result


def _outline_revision(course: dict[str, Any]) -> str:
    return str(
        course.get("document_revision")
        or course.get("current_course_version_id")
        or course.get("updated_at")
        or ""
    )


@router.get("/courses/{course_id}/teaching-calendar")
async def get_teaching_calendar(course_id: str, request: Request):
    course = await get_course_or_404(course_id)
    try:
        return _apply_calendar_defaults(
            teaching_calendar_repository.load(_identity(request), course_id, _course_title(course)),
            course,
        )
    except (TeachingCalendarError, TeachingCalendarValidationError) as exc:
        raise HTTPException(status_code=500, detail={"code": "teaching_calendar_read_failed", "message": str(exc)}) from exc


@router.put("/courses/{course_id}/teaching-calendar")
async def update_teaching_calendar(course_id: str, body: TeachingCalendarUpdate, request: Request):
    course = await get_course_or_404(course_id)
    payload = body.model_dump(mode="json", exclude={"base_revision"})
    payload["course_title"] = body.course_title or _course_title(course)
    try:
        return teaching_calendar_repository.save(_identity(request), course_id, payload, body.base_revision)
    except TeachingCalendarConflict as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "teaching_calendar_revision_conflict",
                "message": str(exc),
                "current_revision": exc.current_revision,
            },
        ) from exc
    except (TeachingCalendarError, TeachingCalendarValidationError) as exc:
        raise HTTPException(status_code=500, detail={"code": "teaching_calendar_save_failed", "message": str(exc)}) from exc


@router.post("/courses/{course_id}/teaching-calendar/derive-from-outline")
async def derive_teaching_calendar(course_id: str, request: Request):
    course = await get_course_or_404(course_id)
    outline_course = _outline_source(course_id, course)
    owner_id = _identity(request)
    current = _apply_calendar_defaults(
        teaching_calendar_repository.load(owner_id, course_id, _course_title(course)),
        outline_course,
    )
    existing_sessions = [dict(item) for item in current.get("sessions") or [] if isinstance(item, dict)]
    existing_lesson_ids = {
        str(item.get("lesson_unit_id"))
        for item in existing_sessions
        if item.get("lesson_unit_id")
    }
    # Derivation is an additive proposal. Existing rows—including manual
    # sessions, repeated A/B/C groups and rows whose old outline node no longer
    # exists—must remain byte-for-byte visible to the teacher. A dict keyed by
    # lesson ID would collapse repeated groups and silently drop unbound rows.
    candidate_sessions: list[dict[str, Any]] = list(existing_sessions)
    retained_count = len(existing_sessions)
    for index, node in enumerate(_calendar_units(outline_course)):
        node_id = str(node.get("node_id") or "")
        if not node_id or node_id in existing_lesson_ids:
            continue
        content = str(node.get("node_name") or node.get("title") or f"第{index + 1}讲")
        objective = _unit_requirements(outline_course, node)
        candidate_sessions.append({
            "session_id": f"candidate-{hashlib.sha256(f'{course_id}:{node_id}'.encode('utf-8')).hexdigest()[:16]}",
            "lesson_unit_id": node_id,
            "sequence": index + 1,
            "date": None,
            "start_time": None,
            "end_time": None,
            "content_summary": content,
            "requirements": objective,
            "location": "",
            "teacher_name": "",
            "teaching_type": "理论课",
            "group_code": "",
            "credit_hours": None,
            "notes": "",
            "status": "unscheduled",
            "source": "outline",
        })
        existing_lesson_ids.add(node_id)
    for sequence, item in enumerate(candidate_sessions, start=1):
        item["sequence"] = sequence
    candidate = {
        **current,
        "course_title": current.get("course_title") or _course_title(outline_course),
        "source_outline_revision": _outline_revision(outline_course),
        "sessions": candidate_sessions,
    }
    return {
        "candidate": candidate,
        "candidate_count": len(candidate_sessions),
        "retained_count": retained_count,
        "new_count": len(candidate_sessions) - retained_count,
        "current_revision": int(current.get("revision") or 0),
    }


@router.get("/teachers/me/teaching-calendar")
async def get_teacher_calendar(
    request: Request,
    date_from: calendar_date | None = Query(default=None),
    date_to: calendar_date | None = Query(default=None),
):
    if date_from and date_to and date_to < date_from:
        raise HTTPException(status_code=422, detail={"code": "invalid_date_range", "message": "结束日期不能早于开始日期"})
    try:
        sessions = teaching_calendar_repository.list_sessions(_identity(request), date_from, date_to)
    except (TeachingCalendarError, TeachingCalendarValidationError) as exc:
        raise HTTPException(status_code=500, detail={"code": "teacher_calendar_read_failed", "message": str(exc)}) from exc
    return {"date_from": date_from, "date_to": date_to, "count": len(sessions), "sessions": sessions}
