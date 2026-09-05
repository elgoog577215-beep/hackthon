from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class FeedbackRatingType(str, Enum):
    """
    评价类型枚举
    """
    POSITIVE = "positive"   # 好评：4-5星
    NEUTRAL = "neutral"     # 中评：3星
    NEGATIVE = "negative"   # 差评：1-2星


class FeedbackDetail(BaseModel):
    """
    反馈详情
    """
    id: str = Field(description="ID")
    user_id: str = Field(description="用户ID")
    star: int = Field(description="星级")
    content: str = Field(description="内容")
    image_paths: list[str] | None = Field(description="图片路径列表")
    create_time: str = Field(description="创建时间")


class SubmitFeedbackParams(BaseModel):
    """
    提交反馈参数
    """
    star: int = Field(..., ge=1, le=5, description="星级，1-5")
    content: str = Field(..., min_length=1, description="评价文案")
    image_paths: list[str] | None = Field(default=None, description="图片路径列表")


class RatingStatistics(BaseModel):
    """
    单类评价统计
    """
    count: int = Field(description="数量")
    percentage: float = Field(description="占比")


class FeedbackStatistics(BaseModel):
    """
    反馈统计
    """
    average_score: float = Field(description="平均分")
    positive: RatingStatistics = Field(description="好评统计")
    neutral: RatingStatistics = Field(description="中评统计")
    negative: RatingStatistics = Field(description="差评统计")
