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
from common.models.operation_log import FeatureType
from common.utils import safe_sse_stream
from infra.db import User, generate_id, get_db
from service.analytics.lifecycle import instrument_stream
from service.auth import get_current_user
from service.operation_log import log_operation_isolated

router = APIRouter()


def _tracked_stream(stream, *, user_id: str, feature: str, feature_key: str | None, action: str):
    async def record_legacy_success() -> None:
        await log_operation_isolated(
            user_id=user_id,
            feature_type=FeatureType.CHAT if feature == "chat" else FeatureType.RESOURCE,
            feature_key=feature_key,
            action=action,
        )

    return safe_sse_stream(instrument_stream(
        stream,
        user_id=user_id,
        feature=feature,
        workflow_id=generate_id(),
        on_success=record_legacy_success,
    ))


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
    stream = assistant_agent.stream(db, request, current_user)
    return EventSourceResponse(_tracked_stream(stream, user_id=current_user.id, feature="chat", feature_key=None, action="send"))


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
    stream = outline_agent.stream(db, params, current_user)
    return EventSourceResponse(_tracked_stream(stream, user_id=current_user.id, feature="outline", feature_key="outline", action="generate"))


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
    stream = teaching_plan_agent.stream(db, params, current_user)
    return EventSourceResponse(_tracked_stream(stream, user_id=current_user.id, feature="teaching_plan", feature_key="teaching_plan", action="generate"))


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
    stream = question_bank_agent.stream(db, params, current_user)
    return EventSourceResponse(_tracked_stream(stream, user_id=current_user.id, feature="question_bank", feature_key="question_bank", action="generate"))


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
    stream = ppt_agent.stream(db, params, current_user)
    return EventSourceResponse(_tracked_stream(stream, user_id=current_user.id, feature="ppt", feature_key="ppt", action="generate"))
