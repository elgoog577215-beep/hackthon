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
from adaptive_models import EvidenceItem

router = APIRouter(prefix="/courses/{course_id}/review", tags=["review"])

# SM-2 quality < 3 视为"没记住/答错"（SM-2 标准约定），据此回流为 wrong_answer 证据；
# 所有提交的复习结果同时作为 comprehension_check 类证据入档（理解检查结果）。
_SM2_FAIL_QUALITY_THRESHOLD = 3


async def _record_review_evidence(course_id: str, results: list) -> None:
    """学习证据采集钩子：复习提交（理解检查）结果回流为 EvidenceItem。

    对应规格文档 §4 "学习证据 MUST 驱动个体化课程演化" Requirement：
    综合理解检查结果判断学生当前理解状态。不阻塞主复习提交流程，失败只记录日志。
    """
    for r in results:
        try:
            quality = r.get("quality", 3) if isinstance(r, dict) else getattr(r, "quality", 3)
            node_id = r.get("node_id") if isinstance(r, dict) else getattr(r, "node_id", None)
            if not node_id:
                continue
            is_wrong = quality < _SM2_FAIL_QUALITY_THRESHOLD
            evidence = EvidenceItem(
                node_id=node_id,
                evidence_type="wrong_answer" if is_wrong else "comprehension_check",
                strength=0.7 if is_wrong else 0.3,
                strength_label="high" if is_wrong else "low",
                content=f"复习理解检查提交：quality={quality}（SM-2 0-5 评分）",
                course_id=course_id,
                metadata={"quality": quality},
            )
            await storage.save_evidence_item(course_id, evidence.model_dump(mode="json"))
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to record review evidence: {e}")


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
    results_dicts = [r.dict() for r in req.results]
    result = await ai_service.submit_review_results(
        course_id=course_id,
        course_data=course_data,
        results=results_dicts
    )
    await run_in_threadpool(storage.save_course, course_id, course_data)
    await _record_review_evidence(course_id, results_dicts)
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
