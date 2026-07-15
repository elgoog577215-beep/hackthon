"""Event-backed review scheduling without course.review_history writes."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Request

from dependencies import get_course_or_404
from learner_context import require_user_id
from learning_events import (
    load_learning_events,
    migrate_legacy_learning_state,
    record_learning_event,
    summarize_text,
)
from models import SubmitReviewRequest


router = APIRouter(prefix="/courses/{course_id}/review", tags=["review"])


@router.get("/schedule")
async def get_review_schedule(course_id: str, request: Request, max_items: int = 20, focus_on_weak: bool = True):
    course = await get_course_or_404(course_id)
    migrate_legacy_learning_state(course)
    user_id = require_user_id(request.headers.get("X-User-Id"))
    states = _review_states(course_id, user_id)
    items = []
    for node in course.get("nodes") or []:
        if int(node.get("node_level") or 1) != 2:
            continue
        state = states.get(str(node.get("node_id") or ""), {})
        priority = "high" if state.get("last_passed") is False else "medium"
        if focus_on_weak and priority != "high" and state.get("review_count", 0):
            priority = "low"
        items.append({
            "node_id": node.get("node_id"),
            "node_name": node.get("node_name"),
            "node_content": node.get("node_content", ""),
            "next_review": state.get("next_review") or datetime.now().isoformat(),
            "review_count": state.get("review_count", 0),
            "interval_days": state.get("interval_days", 1),
            "ease_factor": state.get("ease_factor", 2.5),
            "priority": priority,
            "status": "due",
        })
    items.sort(key=lambda item: ({"high": 0, "medium": 1, "low": 2}[item["priority"]], item["review_count"]))
    return {"course_id": course_id, "items": items[:max_items], "source": "LearningEvent"}


@router.post("/submit")
async def submit_review_results(course_id: str, req: SubmitReviewRequest, request: Request):
    course = await get_course_or_404(course_id)
    user_id = require_user_id(request.headers.get("X-User-Id"))
    states = _review_states(course_id, user_id)
    node_names = {str(node.get("node_id") or ""): str(node.get("node_name") or "") for node in course.get("nodes") or []}
    passed_count = 0
    for result in req.results:
        previous = states.get(result.node_id, {})
        passed = result.quality >= 3
        passed_count += int(passed)
        previous_interval = int(previous.get("interval_days") or 1)
        interval = max(1, round(previous_interval * (1.8 if passed else 0.5)))
        ease = max(1.3, min(3.0, float(previous.get("ease_factor") or 2.5) + (0.1 if passed else -0.2)))
        record_learning_event(
            event_type="review_result_submitted",
            actor="user",
            source="review.submit",
            user_id=user_id,
            course_id=course_id,
            course_version_id=course.get("current_course_version_id"),
            node_id=result.node_id,
            node_name=node_names.get(result.node_id, ""),
            evidence={
                "quality": result.quality,
                "is_correct": passed,
                "time_spent_seconds": result.time_spent_seconds,
                "notes": summarize_text(result.notes or "", limit=240),
            },
            result={
                "review_count": int(previous.get("review_count") or 0) + 1,
                "ease_factor": ease,
                "interval_days": interval,
                "next_review": (datetime.now() + timedelta(days=interval)).isoformat(),
                "passed": passed,
            },
        )
    total = len(req.results)
    return {
        "status": "recorded",
        "updated_count": total,
        "accuracy": round(passed_count / total, 3) if total else 0,
        "source": "LearningEvent",
    }


@router.get("/progress")
async def get_review_progress(course_id: str, request: Request):
    course = await get_course_or_404(course_id)
    user_id = require_user_id(request.headers.get("X-User-Id"))
    states = _review_states(course_id, user_id)
    total = len([node for node in course.get("nodes") or [] if int(node.get("node_level") or 1) == 2])
    reviewed = len(states)
    return {
        "course_id": course_id,
        "total_items": total,
        "reviewed_items": reviewed,
        "progress_percentage": round(reviewed / total * 100, 1) if total else 0,
        "node_states": states,
        "source": "LearningEvent",
    }


@router.get("/stats")
async def get_review_stats(course_id: str, request: Request):
    course = await get_course_or_404(course_id)
    user_id = require_user_id(request.headers.get("X-User-Id"))
    states = _review_states(course_id, user_id)
    today = datetime.now().date()
    events = _review_events_after_reset(course_id, user_id)
    completed_today = sum(
        1 for event in events
        if _event_date(event) == today
    )
    passed = sum(1 for event in events if (event.get("result") or {}).get("passed") is True)
    return {
        "course_id": course_id,
        "total_items": len([node for node in course.get("nodes") or [] if int(node.get("node_level") or 1) == 2]),
        "due_today": sum(1 for state in states.values() if _iso_date(state.get("next_review")) == today),
        "overdue": sum(1 for state in states.values() if _iso_date(state.get("next_review")) < today),
        "completed_today": completed_today,
        "streak_days": _streak_days(events),
        "retention_rate": round(passed / len(events), 3) if events else 0,
        "source": "LearningEvent",
    }


@router.post("/reset")
async def reset_review_history(course_id: str, request: Request):
    course = await get_course_or_404(course_id)
    record_learning_event(
        event_type="review_reset",
        actor="user",
        source="review.reset",
        user_id=require_user_id(request.headers.get("X-User-Id")),
        course_id=course_id,
        course_version_id=course.get("current_course_version_id"),
        result={"status": "reset"},
    )
    return {"status": "success", "message": "复习统计已从当前时间重新开始"}


def _review_events_after_reset(course_id: str, user_id: str) -> list[dict]:
    events = load_learning_events(user_id=user_id, course_id=course_id)
    reset_index = max((index for index, event in enumerate(events) if event.get("event_type") == "review_reset"), default=-1)
    return [event for event in events[reset_index + 1:] if event.get("event_type") == "review_result_submitted"]


def _review_states(course_id: str, user_id: str) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for event in _review_events_after_reset(course_id, user_id):
        node_id = str(event.get("node_id") or "")
        payload = dict(event.get("result") or {})
        payload["last_passed"] = payload.get("passed")
        payload["last_reviewed"] = event.get("created_at")
        result[node_id] = payload
    return result


def _event_date(event: dict):
    try:
        return datetime.fromisoformat(str(event.get("created_at") or "")).date()
    except ValueError:
        return datetime.min.date()


def _iso_date(value):
    try:
        return datetime.fromisoformat(str(value or "")).date()
    except ValueError:
        return datetime.min.date()


def _streak_days(events: list[dict]) -> int:
    dates = sorted({_event_date(event) for event in events}, reverse=True)
    if not dates:
        return 0
    streak = 1
    for previous, current in zip(dates, dates[1:]):
        if (previous - current).days != 1:
            break
        streak += 1
    return streak


__all__ = ["router"]
