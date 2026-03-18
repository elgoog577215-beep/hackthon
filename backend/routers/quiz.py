# =============================================================================
# 测验路由
# 测验生成、聊天摘要
# =============================================================================

from fastapi import APIRouter
import sys, os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from models import GenerateQuizRequest, SummarizeChatRequest, AskQuestionRequest, SimilarQuizRequest
from ai_service import ai_service
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
