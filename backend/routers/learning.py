# =============================================================================
# 学习路径路由
# 学习路径生成、知识掌握度、学习统计
# =============================================================================

from fastapi import APIRouter
import sys, os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from models import LearningPathRequest, LearningPathResponse
from ai_service import ai_service
from dependencies import get_course_or_404

router = APIRouter(tags=["learning"])


@router.post("/courses/{course_id}/learning_path", response_model=LearningPathResponse)
async def generate_learning_path(course_id: str, req: LearningPathRequest):
    course_data = await get_course_or_404(course_id)
    all_nodes = course_data.get("nodes", [])

    result = await ai_service.generate_learning_path(
        course_id=course_id,
        progress_data=[p.dict() for p in req.progress_data],
        wrong_answer_nodes=req.wrong_answer_nodes,
        target_goal=req.target_goal or "系统学习",
        available_time=req.available_time_minutes or 30,
        all_nodes=all_nodes
    )

    return LearningPathResponse(**result)


@router.get("/courses/{course_id}/knowledge_mastery")
async def get_knowledge_mastery(course_id: str):
    course_data = await get_course_or_404(course_id)
    all_nodes = course_data.get("nodes", [])

    progress_data = []
    for node in all_nodes:
        progress_data.append({
            "node_id": node.get("node_id"),
            "node_name": node.get("node_name"),
            "is_read": node.get("is_read", False),
            "read_time_minutes": node.get("read_time_minutes", 0),
            "quiz_score": node.get("quiz_score"),
            "last_accessed": node.get("last_accessed"),
            "notes_count": node.get("notes_count", 0)
        })

    mastery_data = await ai_service.analyze_knowledge_mastery(
        course_id=course_id,
        progress_data=progress_data,
        quiz_history=[],
        all_nodes=all_nodes
    )

    return mastery_data


@router.get("/courses/{course_id}/learning_stats")
async def get_learning_stats(course_id: str):
    course_data = await get_course_or_404(course_id)
    nodes = course_data.get("nodes", [])

    total_nodes = len(nodes)
    completed_nodes = sum(1 for n in nodes if n.get("is_read", False))
    nodes_with_quiz = [n for n in nodes if n.get("quiz_score") is not None]

    avg_quiz_score = 0
    if nodes_with_quiz:
        avg_quiz_score = sum(n.get("quiz_score", 0) for n in nodes_with_quiz) / len(nodes_with_quiz)

    total_reading_time = sum(n.get("read_time_minutes", 0) for n in nodes)

    weak_areas = [
        {
            "node_id": n.get("node_id"),
            "node_name": n.get("node_name"),
            "quiz_score": n.get("quiz_score"),
            "reason": "测验成绩较低，需要复习"
        }
        for n in nodes_with_quiz if n.get("quiz_score", 100) < 60
    ]

    return {
        "course_id": course_id,
        "course_name": course_data.get("course_name", "Unknown"),
        "total_nodes": total_nodes,
        "completed_nodes": completed_nodes,
        "completion_percentage": round(completed_nodes / total_nodes * 100, 1) if total_nodes > 0 else 0,
        "total_reading_time_minutes": total_reading_time,
        "quizzes_taken": len(nodes_with_quiz),
        "average_quiz_score": round(avg_quiz_score, 1),
        "weak_areas": weak_areas,
        "strong_areas": [
            {
                "node_id": n.get("node_id"),
                "node_name": n.get("node_name"),
                "quiz_score": n.get("quiz_score"),
                "reason": "掌握良好"
            }
            for n in nodes_with_quiz if n.get("quiz_score", 0) >= 80
        ]
    }
