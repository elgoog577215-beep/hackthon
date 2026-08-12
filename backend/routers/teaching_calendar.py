"""Real teacher teaching-calendar endpoints."""

from __future__ import annotations

import hashlib
from datetime import date as calendar_date
from datetime import time as clock_time
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field, model_validator

from dependencies import get_course_or_404
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
    source: Literal["manual", "outline"] = "manual"

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
        return teaching_calendar_repository.load(_identity(request), course_id, _course_title(course))
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
    owner_id = _identity(request)
    current = teaching_calendar_repository.load(owner_id, course_id, _course_title(course))
    existing_by_lesson = {
        str(item.get("lesson_unit_id")): item
        for item in current.get("sessions") or []
        if item.get("lesson_unit_id")
    }
    candidate_sessions: list[dict[str, Any]] = []
    retained_count = 0
    for index, node in enumerate(_lesson_nodes(course)):
        node_id = str(node.get("node_id") or "")
        existing = existing_by_lesson.get(node_id)
        if existing:
            candidate_sessions.append(existing)
            retained_count += 1
            continue
        content = str(node.get("node_name") or node.get("title") or f"第{index + 1}讲")
        objective = str(node.get("learning_objective") or "")
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
    candidate = {
        **current,
        "course_title": current.get("course_title") or _course_title(course),
        "source_outline_revision": _outline_revision(course),
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
