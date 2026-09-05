from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from common.models import ApiResponse
from common.models.operation_log import FeatureType
from infra.db import User, get_db
from service.auth import get_current_user
from service.feedback import FeedbackService, SubmitFeedbackParams, FeedbackDetail, FeedbackStatistics
from service.feedback.models import FeedbackRatingType
from service.operation_log import log_operation


router = APIRouter()


# ---------- 依赖注入 ----------

async def get_feedback_service(db: AsyncSession = Depends(get_db)) -> FeedbackService:
    return FeedbackService(db)


# ---------- API 接口 ----------

@router.post(
    "",
    summary="提交用户反馈",
    response_model=ApiResponse[str],
)
async def submit_feedback(
    params: SubmitFeedbackParams,
    service: FeedbackService = Depends(get_feedback_service),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[str]:
    """用户提交星级和评价文案反馈。"""
    feedback_id = await service.submit_feedback(params, current_user)
    await log_operation(db, user_id=current_user.id, feature_type=FeatureType.FEEDBACK, action="submit")
    return ApiResponse.success_response(feedback_id)


@router.get(
    "/list",
    summary="查询反馈列表",
    response_model=ApiResponse[list[FeedbackDetail]],
)
async def list_feedbacks(
    rating_type: FeedbackRatingType | None = None,
    min_length: int | None = None,
    service: FeedbackService = Depends(get_feedback_service),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[list[FeedbackDetail]]:
    """按评价类型（好评/中评/差评）和最小字数筛选反馈列表，按时间倒序返回。"""
    feedbacks = await service.list_feedbacks(rating_type, min_length)
    return ApiResponse.success_response(feedbacks)


@router.get(
    "/statistics",
    summary="反馈统计",
    response_model=ApiResponse[FeedbackStatistics],
)
async def get_feedback_statistics(
    service: FeedbackService = Depends(get_feedback_service),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[FeedbackStatistics]:
    """实时统计平均分、各类评价数量及占比。"""
    statistics = await service.get_statistics()
    return ApiResponse.success_response(statistics)
