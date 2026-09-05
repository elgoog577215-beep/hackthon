from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from infra.db import Feedback, User
from service.feedback.models import (
    FeedbackDetail,
    FeedbackRatingType,
    FeedbackStatistics,
    RatingStatistics,
    SubmitFeedbackParams,
)


# 评价类型对应的星级范围
RATING_STAR_RANGES = {
    FeedbackRatingType.POSITIVE: (4, 5),
    FeedbackRatingType.NEUTRAL: (3, 3),
    FeedbackRatingType.NEGATIVE: (1, 2),
}


class FeedbackService:
    """
    反馈服务
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ---------- 公共方法 ----------

    async def submit_feedback(self, params: SubmitFeedbackParams, current_user: User) -> str:
        """提交用户反馈"""
        feedback = Feedback(
            user_id=current_user.id,
            star=params.star,
            content=params.content,
            image_paths=params.image_paths,
        )
        self.db.add(feedback)
        await self.db.commit()
        return feedback.id

    async def list_feedbacks(
        self,
        rating_type: FeedbackRatingType | None,
        min_length: int | None,
    ) -> list[FeedbackDetail]:
        """按评价类型和最小字数查询反馈列表，按时间倒序"""
        conditions = []
        if rating_type is not None:
            star_min, star_max = RATING_STAR_RANGES[rating_type]
            conditions.append(Feedback.star >= star_min)
            conditions.append(Feedback.star <= star_max)
        if min_length is not None:
            conditions.append(func.length(Feedback.content) >= min_length)

        results = (await self.db.execute(
            select(Feedback)
            .where(*conditions if conditions else True)
            .order_by(Feedback.create_time.desc())
        )).scalars().all()

        return [_feedback_to_detail(f) for f in results]

    async def get_statistics(self) -> FeedbackStatistics:
        """实时统计反馈数据：平均分、各类评价数量和占比"""
        rows = (await self.db.execute(
            select(Feedback.star)
        )).scalars().all()

        total = len(rows)
        if total == 0:
            return FeedbackStatistics(
                average_score=0.0,
                positive=RatingStatistics(count=0, percentage=0.0),
                neutral=RatingStatistics(count=0, percentage=0.0),
                negative=RatingStatistics(count=0, percentage=0.0),
            )

        positive_count = sum(1 for s in rows if 4 <= s <= 5)
        neutral_count = sum(1 for s in rows if s == 3)
        negative_count = sum(1 for s in rows if 1 <= s <= 2)
        average = sum(rows) / total

        def _pct(count: int) -> float:
            return round(count / total * 100, 2)

        return FeedbackStatistics(
            average_score=round(average, 2),
            positive=RatingStatistics(count=positive_count, percentage=_pct(positive_count)),
            neutral=RatingStatistics(count=neutral_count, percentage=_pct(neutral_count)),
            negative=RatingStatistics(count=negative_count, percentage=_pct(negative_count)),
        )


# ---------- 私有方法 ----------

def _feedback_to_detail(feedback: Feedback) -> FeedbackDetail:
    """将 Feedback 实体转换为 FeedbackDetail"""
    return FeedbackDetail(
        id=feedback.id,
        user_id=feedback.user_id,
        star=feedback.star,
        content=feedback.content,
        image_paths=feedback.image_paths,
        create_time=feedback.create_time.isoformat() if feedback.create_time else "",
    )
