from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.utils.datetime import format_datetime
from infra.db import Feedback, User
from service.admin.excel import build_workbook
from service.admin.models import AdminFeedbackDetail
from service.feedback.models import FeedbackRatingType


# 与 service/feedback/service.py 保持一致
RATING_STAR_RANGES = {
    FeedbackRatingType.POSITIVE: (4, 5),
    FeedbackRatingType.NEUTRAL: (3, 3),
    FeedbackRatingType.NEGATIVE: (1, 2),
}


class AdminFeedbackService:
    """运营后台的反馈管理服务。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_with_users(
        self,
        rating_type: FeedbackRatingType | None,
        min_length: int | None,
    ) -> list[AdminFeedbackDetail]:
        rows = await self._query(rating_type, min_length)
        return [_row_to_detail(f, u) for f, u in rows]

    async def build_export_xlsx(
        self,
        rating_type: FeedbackRatingType | None,
        min_length: int | None,
    ) -> bytes:
        rows = await self._query(rating_type, min_length)
        headers = [
            "序号", "反馈ID", "用户姓名", "学工号", "学院",
            "星级", "评价文案", "图片路径", "提交时间",
        ]
        body: list[list] = []
        for index, (f, u) in enumerate(rows, start=1):
            body.append([
                index,
                f.id,
                (u.name if u else "") or "",
                (u.zju_id if u else "") or "",
                (u.department if u else "") or "",
                f.star,
                f.content or "",
                ";".join(f.image_paths or []),
                format_datetime(f.create_time) or "",
            ])
        return build_workbook("用户反馈", headers, body)

    # ---------- 私有 ----------

    async def _query(
        self,
        rating_type: FeedbackRatingType | None,
        min_length: int | None,
    ) -> list[tuple[Feedback, User | None]]:
        conditions = []
        if rating_type is not None:
            star_min, star_max = RATING_STAR_RANGES[rating_type]
            conditions.append(Feedback.star >= star_min)
            conditions.append(Feedback.star <= star_max)
        if min_length is not None:
            conditions.append(func.length(Feedback.content) >= min_length)

        stmt = (
            select(Feedback, User)
            .join(User, User.id == Feedback.user_id, isouter=True)
        )
        if conditions:
            stmt = stmt.where(*conditions)
        stmt = stmt.order_by(Feedback.create_time.desc())
        result = await self.db.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]


def _row_to_detail(f: Feedback, u: User | None) -> AdminFeedbackDetail:
    return AdminFeedbackDetail(
        id=f.id,
        user_id=f.user_id,
        user_name=(u.name if u else None),
        user_zju_id=(u.zju_id if u else None),
        user_department=(u.department if u else None),
        star=f.star,
        content=f.content or "",
        image_paths=list(f.image_paths or []),
        create_time=format_datetime(f.create_time) or "",
    )
