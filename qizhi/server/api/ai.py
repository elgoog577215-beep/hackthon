from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from agents.assistant import agent as assistant_agent
from agents.assistant.models import ChatRequest
from agents.outline import agent as outline_agent
from agents.outline.models import OutlineGenerateParams
from agents.ppt import agent as ppt_agent
from agents.ppt.models import PptGenerateParams
from agents.question_bank import agent as question_bank_agent
from agents.question_bank.models import QuestionBankGenerateParams
from agents.teaching_plan import agent as teaching_plan_agent
from agents.teaching_plan.models import TeachingPlanGenerateParams
from common.models import BizException
from common.models.operation_log import FeatureType
from common.utils import safe_sse_stream
from infra.db import User, get_db
from service.auth import get_current_user
from service.operation_log import log_operation

router = APIRouter()


@router.post(
    "/chat",
    summary="发送消息并流式返回回复",
)
async def chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EventSourceResponse:
    """提交一条用户消息，并通过 SSE 持续返回 AI 回复及执行事件。"""
    await log_operation(db, user_id=current_user.id, feature_type=FeatureType.CHAT, action="send")
    stream = assistant_agent.stream(db, request, current_user)
    return EventSourceResponse(safe_sse_stream(stream))


@router.post(
    "/outline",
    summary="流式生成教学大纲",
)
async def generate_outline(
    params: OutlineGenerateParams,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EventSourceResponse:
    """根据表单数据流式生成教学大纲。"""
    await log_operation(
        db,
        user_id=current_user.id,
        feature_type=FeatureType.RESOURCE,
        feature_key="outline",
        action="generate",
    )
    stream = outline_agent.stream(db, params, current_user)
    return EventSourceResponse(safe_sse_stream(stream))


@router.post(
    "/teaching_plan",
    summary="流式生成教案",
)
async def generate_teaching_plan(
    params: TeachingPlanGenerateParams,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EventSourceResponse:
    """基于教学大纲流式生成教案。"""
    await log_operation(
        db,
        user_id=current_user.id,
        feature_type=FeatureType.RESOURCE,
        feature_key="teaching_plan",
        action="generate",
    )
    stream = teaching_plan_agent.stream(db, params, current_user)
    return EventSourceResponse(safe_sse_stream(stream))


@router.post(
    "/question_bank",
    summary="流式生成题库",
)
async def generate_question_bank(
    params: QuestionBankGenerateParams,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EventSourceResponse:
    """基于教案流式生成题库。"""
    await log_operation(
        db,
        user_id=current_user.id,
        feature_type=FeatureType.RESOURCE,
        feature_key="question_bank",
        action="generate",
    )
    stream = question_bank_agent.stream(db, params, current_user)
    return EventSourceResponse(safe_sse_stream(stream))


@router.post(
    "/ppt",
    summary="流式本地生成 PPT（教案/大纲 → 可交互 HTML + 可下载 .pptx）",
)
async def generate_ppt(
    params: PptGenerateParams,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EventSourceResponse:
    """以教案/大纲为依据，用自建 vLLM Qwen 本地生成 PPT。

    SSE 事件：loading（进度）→ end（{html_url, pptx_url, title, slides}）。
    """
    await log_operation(
        db,
        user_id=current_user.id,
        feature_type=FeatureType.RESOURCE,
        feature_key="ppt",
        action="generate",
    )
    stream = ppt_agent.stream(db, params, current_user)
    return EventSourceResponse(safe_sse_stream(stream))
