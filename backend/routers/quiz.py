# =============================================================================
# 测验路由
# 测验生成、聊天摘要
# =============================================================================

import logging
from fastapi import APIRouter
import sys, os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from models import GenerateQuizRequest, SummarizeChatRequest, AskQuestionRequest, SimilarQuizRequest
from ai_service import ai_service
from fastapi.responses import StreamingResponse
from adaptive_models import EvidenceItem
from storage import storage

logger = logging.getLogger(__name__)

router = APIRouter(tags=["quiz"])

# 重解释/追问请求的关键词（与 ai_qa_service._analyze_user_intent 的 explanation_request
# 意图判断保持一致的词表，用于学习证据采集，不影响该函数本身）。
_REASK_KEYWORDS = ("详细", "再讲", "还是不懂", "没听懂", "再解释", "展开讲", "举例", "看不懂", "不明白")


def _maybe_record_dialogue_reask_evidence(req: AskQuestionRequest) -> None:
    """学习证据采集钩子：学生要求更详细解释/重新解释时，持久化一条 EvidenceItem。

    对应规格文档 §4 "学习证据 MUST 驱动个体化课程演化" Requirement。
    仅在 course_id 存在时落盘（EvidenceItem 按 course_id 分文件存储）；
    不阻塞主问答流程，失败只记录日志。
    """
    if not req.course_id or not req.node_id:
        return
    question_text = req.question or ""
    if not any(kw in question_text for kw in _REASK_KEYWORDS):
        return
    try:
        return EvidenceItem(
            node_id=req.node_id,
            evidence_type="dialogue_reask",
            strength=0.5,
            strength_label="medium",
            content=question_text[:500],
            course_id=req.course_id,
        )
    except Exception as e:
        logger.warning(f"Failed to build dialogue_reask evidence: {e}")
        return None


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
async def ask_question(req: AskQuestionRequest):
    evidence = _maybe_record_dialogue_reask_evidence(req)
    if evidence is not None:
        try:
            await storage.save_evidence_item(req.course_id, evidence.model_dump(mode="json"))
        except Exception as e:
            logger.warning(f"Failed to save dialogue_reask evidence: {e}")
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
