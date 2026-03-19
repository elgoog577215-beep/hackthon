# =============================================================================
# 测验路由
# 测验生成、聊天摘要
# =============================================================================

from fastapi import APIRouter
import sys, os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from models import GenerateQuizRequest, SummarizeChatRequest, AskQuestionRequest, SimilarQuizRequest, RecordQuizAnswerRequest
from ai_service import ai_service
from learning_record import record_quiz_answer, get_learner_weakness
from fastapi.responses import StreamingResponse

router = APIRouter(tags=["quiz"])


@router.post("/generate_quiz")
async def generate_quiz(req: GenerateQuizRequest):
    return await ai_service.generate_quiz(
        req.node_content,
        node_name=req.node_name,
        difficulty=req.difficulty,
        style=req.style,
        user_persona=req.user_persona,
        question_count=req.question_count,
        discipline_type=req.discipline_type
    )


@router.post("/similar_quiz")
async def similar_quiz(req: SimilarQuizRequest):
    return await ai_service.generate_similar_quiz(
        question=req.question,
        options=req.options,
        correct_index=req.correct_index,
        explanation=req.explanation,
        node_name=req.node_name,
        question_count=req.question_count,
    )



@router.post("/summarize_chat")
async def summarize_chat(req: SummarizeChatRequest):
    return await ai_service.summarize_chat(req.history, req.course_context, req.user_persona)


@router.post("/ask")
def ask_question(req: AskQuestionRequest):
    return StreamingResponse(
        ai_service.answer_question_stream(
            req.question,
            req.node_content,
            req.history,
            req.selection,
            req.user_persona,
            req.course_id,
            req.node_id,
            req.user_notes,
            req.session_metrics,
            req.enable_long_term_memory
        ),
        media_type="text/plain"
    )


@router.post("/record_quiz_answer")
async def record_quiz_answer_api(req: RecordQuizAnswerRequest):
    """记录测验答题结果（P1 新增）"""
    record_quiz_answer(
        course_id=req.course_id,
        course_name=req.course_name,
        node_name=req.node_name,
        question_id=req.question_id,
        knowledge_point=req.knowledge_point,
        user_answer=req.user_answer,
        correct_answer=req.correct_answer,
        time_spent_seconds=req.time_spent_seconds,
        hint_used=req.hint_used
    )
    return {"status": "success", "message": "答题结果已记录"}


@router.get("/get_weak_points/{course_id}")
async def get_weak_points_api(course_id: str, dependencies: str = ""):
    """获取学习者薄弱点（P1 新增）
    
    Args:
        course_id: 课程 ID
        dependencies: 可选，以逗号分隔的前置依赖章节名称列表
    """
    dep_list = dependencies.split(",") if dependencies else None
    weak_points = get_learner_weakness(course_id, dep_list)
    return {"course_id": course_id, "weak_points": weak_points}


@router.get("/get_prerequisite_weak_points/{course_id}")
async def get_prerequisite_weak_points_api(course_id: str, node_dependencies: str):
    """获取前置依赖章节的薄弱知识点（P1 新增）
    
    Args:
        course_id: 课程 ID
        node_dependencies: 以逗号分隔的前置依赖章节名称列表
    """
    dep_list = node_dependencies.split(",") if node_dependencies else []
    weak_points = get_learner_weakness(course_id, dep_list)
    return {"course_id": course_id, "dependencies": dep_list, "weak_points": weak_points}
