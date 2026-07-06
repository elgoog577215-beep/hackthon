# =============================================================================
# AI 辅导路由
# 智能导师问候、学习者画像、学习记录、目标管理
# =============================================================================

from fastapi import APIRouter, HTTPException
from typing import Optional
from datetime import datetime
import logging
import sys, os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from models import (
    RecordLearningRequest, SessionSummaryRequest,
    TutorContextRequest, CreateGoalRequest, UpdateGoalProgressRequest
)
from learner_context import DEFAULT_USER_ID

logger = logging.getLogger(__name__)

# 延迟导入 tutor_service，可能不可用
try:
    from tutor_service import (
        get_tutor_memory, get_proactive_engine,
        tutor_memory, proactive_engine,
        GoalType, GoalStatus
    )
    TUTOR_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Tutor service not available: {e}")
    TUTOR_AVAILABLE = False

router = APIRouter(prefix="/api/tutor", tags=["tutor"])


@router.get("/greeting")
async def get_tutor_greeting(course_id: Optional[str] = None, node_id: Optional[str] = None):
    if not TUTOR_AVAILABLE:
        return {
            "greeting": "👋 你好！我是你的AI学习助手，有什么可以帮助你的吗？",
            "actions": [],
            "stats": {}
        }
    user_id = DEFAULT_USER_ID
    result = proactive_engine.generate_greeting(user_id, course_id, node_id)
    return result


@router.get("/profile")
async def get_tutor_profile():
    if not TUTOR_AVAILABLE:
        raise HTTPException(status_code=503, detail="导师服务未加载")
    user_id = DEFAULT_USER_ID
    profile = tutor_memory.get_or_create_profile(user_id)
    weaknesses = tutor_memory.get_weaknesses(user_id)
    strengths = tutor_memory.get_strengths(user_id)
    return {
        "profile": profile,
        "weaknesses": weaknesses[:5],
        "strengths": strengths[:5],
        "knowledge_count": len(tutor_memory.knowledge_states.get(user_id, {}))
    }


@router.post("/record-learning")
async def record_learning(req: RecordLearningRequest):
    if not TUTOR_AVAILABLE:
        return {"success": False}
    user_id = DEFAULT_USER_ID
    state = tutor_memory.update_knowledge_state(
        user_id=user_id,
        node_id=req.node_id,
        node_title=req.node_title,
        is_correct=req.is_correct,
        time_spent=req.time_spent,
        question_data=req.question_data
    )
    return {
        "success": True,
        "mastery_level": state.mastery_level,
        "confidence": state.confidence,
        "correct_rate": state.correct_rate
    }


@router.post("/session-summary")
async def create_session_summary(req: SessionSummaryRequest):
    if not TUTOR_AVAILABLE:
        return {"summary": "学习完成！", "stats": {}}
    user_id = DEFAULT_USER_ID
    tutor_memory.record_study_session(user_id, req.duration, req.nodes_studied)
    result = proactive_engine.generate_session_summary(user_id, {
        'duration': req.duration,
        'questions_answered': req.questions_answered,
        'correct_count': req.correct_count
    })
    return result


@router.get("/review-items")
async def get_review_items(limit: int = 5):
    if not TUTOR_AVAILABLE:
        return {"review_items": []}
    user_id = DEFAULT_USER_ID
    items = tutor_memory.get_review_items(user_id, limit)
    return {"review_items": items}


@router.get("/wrong-answers")
async def get_wrong_answers(limit: int = 5):
    if not TUTOR_AVAILABLE:
        return {"wrong_answers": []}
    user_id = DEFAULT_USER_ID
    items = tutor_memory.get_wrong_answers_for_review(user_id, limit)
    return {"wrong_answers": items}


@router.post("/suggestion")
async def get_tutor_suggestion(req: TutorContextRequest):
    if not TUTOR_AVAILABLE:
        return {"suggestions": []}
    user_id = DEFAULT_USER_ID
    result = proactive_engine.generate_study_suggestion(user_id, {
        'time_stuck': req.time_stuck,
        'consecutive_wrong': req.consecutive_wrong,
        'current_node_id': req.current_node_id
    })
    return result


@router.get("/goals")
async def get_tutor_goals(status: Optional[str] = None):
    if not TUTOR_AVAILABLE:
        return {"goals": []}
    user_id = DEFAULT_USER_ID
    goals = tutor_memory.goals.get(user_id, [])
    if status:
        goals = [g for g in goals if g.status.value == status]
    return {"goals": [g.to_dict() for g in goals]}


@router.post("/goals")
async def create_tutor_goal(req: CreateGoalRequest):
    if not TUTOR_AVAILABLE:
        raise HTTPException(status_code=503, detail="导师服务未加载")
    user_id = DEFAULT_USER_ID
    try:
        goal_type = GoalType(req.goal_type)
    except ValueError:
        goal_type = GoalType.TASK_ORIENTED

    deadline = None
    if req.deadline:
        try:
            deadline = datetime.fromisoformat(req.deadline.replace('Z', '+00:00'))
        except ValueError:
            try:
                deadline = datetime.strptime(req.deadline, "%Y-%m-%d")
            except ValueError:
                pass

    goal = tutor_memory.create_goal(
        user_id=user_id,
        title=req.title,
        description=req.description,
        goal_type=goal_type,
        target_value=req.target_value,
        unit=req.unit,
        deadline=deadline,
        related_nodes=req.related_nodes,
        priority=req.priority
    )
    return {"success": True, "goal": goal.to_dict()}


@router.put("/goals/{goal_id}/progress")
async def update_tutor_goal_progress(goal_id: str, req: UpdateGoalProgressRequest):
    if not TUTOR_AVAILABLE:
        raise HTTPException(status_code=503, detail="导师服务未加载")
    user_id = DEFAULT_USER_ID
    goal = tutor_memory.update_goal_progress(user_id, goal_id, req.progress_delta)
    if not goal:
        raise HTTPException(status_code=404, detail="目标不存在")
    return {"success": True, "goal": goal.to_dict()}


@router.get("/goal-recommendations")
async def get_goal_recommendations():
    if not TUTOR_AVAILABLE:
        return {"recommendations": []}
    user_id = DEFAULT_USER_ID
    recommendations = tutor_memory.get_goal_recommendations(user_id)
    return {"recommendations": recommendations}
