# =============================================================================
# 学习者画像路由
# =============================================================================

from fastapi import APIRouter
import sys, os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from models import GenerateProfileRequest, ProfileResponse
from ai_service import ai_service
from learner_context import save_profile_snapshot

router = APIRouter(tags=["profile"])


@router.post("/profile/generate", response_model=ProfileResponse)
async def generate_profile(req: GenerateProfileRequest):
    """生成或增量更新学习者画像"""
    # 检查是否有足够数据
    if req.mode == "full" and not req.wrong_answers and not req.notes and not req.chat_summary:
        return ProfileResponse(
            ai_profile="",
            agent_commentary="",
            persona_summary="",
        )

    # 生成 AI 画像
    ai_profile = await ai_service.generate_profile(
        wrong_answers=req.wrong_answers,
        notes=req.notes,
        chat_summary=req.chat_summary,
        self_evaluation=req.self_evaluation,
        current_profile=req.current_profile,
        mode=req.mode,
        new_content=req.new_content,
    )
    if not ai_profile:
        return ProfileResponse(
            ai_profile="画像生成失败，请稍后重试",
            agent_commentary="",
            persona_summary="",
        )

    # 生成 Agent 评论
    commentary = await ai_service.generate_commentary(ai_profile)

    # 生成精简版画像摘要
    persona = await ai_service.generate_persona_summary(ai_profile, req.self_evaluation)
    save_profile_snapshot(
        ai_profile=ai_profile,
        persona_summary=persona or "",
        self_evaluation=req.self_evaluation,
    )

    return ProfileResponse(
        ai_profile=ai_profile,
        agent_commentary=commentary or "",
        persona_summary=persona or "",
    )
