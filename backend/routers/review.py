# =============================================================================
# 复习调度路由
# SM-2 复习计划、复习提交、进度、统计、重置
# =============================================================================

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
from datetime import datetime
import sys, os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from models import SubmitReviewRequest
from storage import storage
from ai_service import ai_service
from dependencies import get_course_or_404

router = APIRouter(prefix="/courses/{course_id}/review", tags=["review"])


def _get_today_date() -> datetime:
    return datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)


def _parse_iso_date(date_str: str) -> datetime:
    return datetime.fromisoformat(date_str)


@router.get("/schedule")
async def get_review_schedule(course_id: str, max_items: int = 20, focus_on_weak: bool = True):
    course_data = await get_course_or_404(course_id)
    result = await ai_service.generate_review_schedule(
        course_id=course_id,
        course_data=course_data,
        max_items=max_items,
        focus_on_weak=focus_on_weak
    )
    return result


@router.post("/submit")
async def submit_review_results(course_id: str, req: SubmitReviewRequest):
    course_data = await get_course_or_404(course_id)
    result = await ai_service.submit_review_results(
        course_id=course_id,
        course_data=course_data,
        results=[r.dict() for r in req.results]
    )
    await run_in_threadpool(storage.save_course, course_id, course_data)
    return result


@router.get("/progress")
async def get_review_progress(course_id: str):
    course_data = await get_course_or_404(course_id)
    result = await ai_service.get_review_progress(
        course_id=course_id,
        course_data=course_data
    )
    return result


@router.get("/stats")
async def get_review_stats(course_id: str):
    course_data = await get_course_or_404(course_id)
    review_history = course_data.get("review_history", {})
    nodes = course_data.get("nodes", [])
    today = _get_today_date()

    due_today = 0
    overdue = 0
    completed_today = 0
    total_reviewed = 0
    total_correct = 0

    for node in nodes:
        node_id = node.get("node_id")
        node_review = review_history.get(node_id, {})

        if node_review.get("next_review"):
            next_review = _parse_iso_date(node_review["next_review"])
            if next_review.date() < today.date():
                overdue += 1
            elif next_review.date() == today.date():
                due_today += 1

        if node_review.get("last_reviewed"):
            last_reviewed = _parse_iso_date(node_review["last_reviewed"])
            if last_reviewed.date() == today.date():
                completed_today += 1

        # 根据复习历史计算实际保留率
        review_count = node_review.get("review_count", 0)
        if review_count > 0:
            total_reviewed += review_count
            # quality >= 3 视为"记住了"，ease_factor 越高说明掌握越好
            ease = node_review.get("ease_factor", 2.5)
            # 用 ease_factor 估算正确率：ease >= 2.5 表示大部分正确
            estimated_correct = review_count * min(ease / 3.0, 1.0)
            total_correct += estimated_correct

    # 计算实际保留率，无数据时返回 0
    retention_rate = round(total_correct / total_reviewed, 2) if total_reviewed > 0 else 0.0

    return {
        "course_id": course_id,
        "total_items": len(nodes),
        "due_today": due_today,
        "overdue": overdue,
        "completed_today": completed_today,
        "streak_days": course_data.get("learning_streak", 0),
        "retention_rate": retention_rate,
        "last_review_date": course_data.get("last_review_date")
    }


@router.post("/reset")
async def reset_review_history(course_id: str):
    course_data = await get_course_or_404(course_id)
    course_data["review_history"] = {}
    course_data["learning_streak"] = 0
    course_data["last_review_date"] = None
    course_data["last_study_date"] = None
    await run_in_threadpool(storage.save_course, course_id, course_data)
    return {"status": "success", "message": "复习历史已重置"}
