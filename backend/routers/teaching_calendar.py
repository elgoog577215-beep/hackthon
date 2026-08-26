"""Real teacher teaching-calendar endpoints."""

from __future__ import annotations

import hashlib
from datetime import date as calendar_date
from datetime import time as clock_time
from typing import Any, Literal
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field, model_validator

from dependencies import get_course_or_404, get_task_manager_optional
from learner_context import require_user_id
from teaching_calendar import (
    TeachingCalendarConflict,
    TeachingCalendarError,
    TeachingCalendarValidationError,
    teaching_calendar_repository,
)
from teaching_calendar_export import EXPORTERS, build_csv


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
        if self.status != "cancelled":
            complete_schedule = bool(self.date and self.start_time and self.end_time)
            self.status = "scheduled" if complete_schedule else "unscheduled"
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


async def _filter_available_course_sessions(
    owner_id: str,
    sessions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Keep calendar rows only while their formal course still exists."""
    available_course_ids: set[str] = set()
    for course_id in sorted({str(item.get("course_id") or "") for item in sessions} - {""}):
        try:
            course = await get_course_or_404(course_id)
        except HTTPException as exc:
            if exc.status_code == 404:
                continue
            raise
        course_owner_id = str(course.get("owner_id") or "").strip()
        if course_owner_id and course_owner_id != owner_id:
            continue
        available_course_ids.add(course_id)
    return [
        item for item in sessions
        if str(item.get("course_id") or "") in available_course_ids
    ]


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
    top_level = [
        node
        for node in nodes
        if int(node.get("node_level") or 0) == 1
        and str(node.get("parent_node_id") or "root") in {"", "root"}
    ]
    # A chapter is the stable teacher-facing LessonUnit. It may contain several
    # generated knowledge/content nodes and may later map to several A/B/C
    # ClassSession rows. Never turn those descendants into extra lectures just
    # because an older generation request persisted a different count.
    if top_level:
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
    candidate_sessions: list[dict[str, Any]] = []
    retained_count = len(existing_sessions)
    calendar_units = _calendar_units(outline_course)
    units_by_id = {
        str(node.get("node_id") or ""): node
        for node in calendar_units
        if str(node.get("node_id") or "")
    }
    diff_items: list[dict[str, Any]] = []

    for raw in existing_sessions:
        item = dict(raw)
        lesson_unit_id = str(item.get("lesson_unit_id") or "")
        unit = units_by_id.get(lesson_unit_id)
        if not lesson_unit_id:
            candidate_sessions.append(item)
            diff_items.append({
                "kind": "keep",
                "session_id": item.get("session_id"),
                "lesson_unit_id": None,
                "title": str(item.get("content_summary") or "未命名课次"),
                "reason": "手动课次未绑定教学大纲，保持不变",
                "changes": {},
            })
            continue
        if unit is None:
            candidate_sessions.append(item)
            diff_items.append({
                "kind": "stale",
                "session_id": item.get("session_id"),
                "lesson_unit_id": lesson_unit_id,
                "title": str(item.get("content_summary") or "未命名课次"),
                "reason": "关联讲次已不在当前大纲中；保留课次，等待教师处理",
                "changes": {},
            })
            continue

        generated_content = str(unit.get("node_name") or unit.get("title") or "未命名讲次")
        generated_requirements = _unit_requirements(outline_course, unit)
        changes: dict[str, dict[str, Any]] = {}
        if str(item.get("source") or "") == "outline":
            if str(item.get("content_summary") or "") != generated_content:
                changes["content_summary"] = {
                    "before": str(item.get("content_summary") or ""),
                    "after": generated_content,
                }
                item["content_summary"] = generated_content
            if str(item.get("requirements") or "") != generated_requirements:
                changes["requirements"] = {
                    "before": str(item.get("requirements") or ""),
                    "after": generated_requirements,
                }
                item["requirements"] = generated_requirements
        candidate_sessions.append(item)
        diff_items.append({
            "kind": "update" if changes else "keep",
            "session_id": item.get("session_id"),
            "lesson_unit_id": lesson_unit_id,
            "title": generated_content,
            "reason": "仅更新大纲生成的教学内容与教学要求；日期、时间、地点、教师和小组保持不变" if changes else "已与当前大纲一致",
            "changes": changes,
        })

    for index, node in enumerate(calendar_units):
        node_id = str(node.get("node_id") or "")
        if not node_id or node_id in existing_lesson_ids:
            continue
        content = str(node.get("node_name") or node.get("title") or f"第{index + 1}讲")
        objective = _unit_requirements(outline_course, node)
        candidate_session = {
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
        }
        candidate_sessions.append(candidate_session)
        diff_items.append({
            "kind": "add",
            "session_id": candidate_session["session_id"],
            "lesson_unit_id": node_id,
            "title": content,
            "reason": "当前日历尚无该讲次，新增未排期候选",
            "changes": {},
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
        "diff": {
            "items": diff_items,
            "add_count": sum(1 for item in diff_items if item["kind"] == "add"),
            "update_count": sum(1 for item in diff_items if item["kind"] == "update"),
            "keep_count": sum(1 for item in diff_items if item["kind"] == "keep"),
            "stale_count": sum(1 for item in diff_items if item["kind"] == "stale"),
        },
        "projection": {
            "mode": "outline_chapters" if any(int(node.get("node_level") or 0) == 1 for node in calendar_units) else "legacy_roots",
            "lesson_unit_count": len(calendar_units),
            "requested_session_count": _expected_session_count(outline_course),
        },
    }


@router.get("/courses/{course_id}/teaching-calendar/export")
async def export_teaching_calendar(
    course_id: str,
    request: Request,
    format: Literal["docx", "pdf", "xlsx", "csv"] = Query(default="docx"),
    revision: int | None = Query(default=None, ge=0),
):
    course = await get_course_or_404(course_id)
    calendar = _apply_calendar_defaults(
        teaching_calendar_repository.load(_identity(request), course_id, _course_title(course)),
        course,
    )
    current_revision = int(calendar.get("revision") or 0)
    if revision is not None and revision != current_revision:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "teaching_calendar_export_revision_conflict",
                "message": f"请求导出的修订 {revision} 已不是最新修订；当前为 {current_revision}",
                "current_revision": current_revision,
            },
        )
    if not calendar.get("sessions"):
        raise HTTPException(
            status_code=422,
            detail={"code": "teaching_calendar_export_empty", "message": "教学日历还没有课次，无法导出"},
        )
    try:
        if format == "csv":
            payload = build_csv(calendar)
        else:
            payload = EXPORTERS[format](calendar, course)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={"code": "teaching_calendar_export_failed", "message": f"{format.upper()} 导出失败：{exc}"},
        ) from exc
    media_types = {
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "pdf": "application/pdf",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "csv": "text/csv; charset=utf-8",
    }
    safe_title = "".join(char if char not in '\\/:*?\"<>|' else "_" for char in str(calendar.get("course_title") or "教学日历"))
    filename = quote(f"{safe_title}_教学日历_r{current_revision}.{format}")
    return Response(
        content=payload,
        media_type=media_types[format],
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


@router.get("/teachers/me/teaching-calendar")
async def get_teacher_calendar(
    request: Request,
    date_from: calendar_date | None = Query(default=None),
    date_to: calendar_date | None = Query(default=None),
    include_incomplete: bool = Query(default=False),
):
    if date_from and date_to and date_to < date_from:
        raise HTTPException(status_code=422, detail={"code": "invalid_date_range", "message": "结束日期不能早于开始日期"})
    owner_id = _identity(request)
    try:
        sessions = teaching_calendar_repository.list_sessions(
            owner_id,
            date_from,
            date_to,
            include_incomplete=include_incomplete,
        )
        sessions = await _filter_available_course_sessions(owner_id, sessions)
    except (TeachingCalendarError, TeachingCalendarValidationError) as exc:
        raise HTTPException(status_code=500, detail={"code": "teacher_calendar_read_failed", "message": str(exc)}) from exc
    return {"date_from": date_from, "date_to": date_to, "count": len(sessions), "sessions": sessions}
