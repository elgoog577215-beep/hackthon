from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import and_, distinct, func, not_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.constants import TIMEZONE_SHANGHAI
from common.models.operation_log import (
    FEATURE_DISPLAY,
    PENDING_FEATURE_SLOTS,
    RESIDENT_FEATURE_SLOTS,
    FeatureType,
)
from common.utils.datetime import format_datetime
from infra.db import User
from infra.db.models.agent import Agent
from infra.db.models.user_operation_log import UserOperationLog
from service.admin.excel import build_workbook
from service.admin.models import (
    AdminUserDetail,
    AgentUsageItem,
    DashboardStats,
    FeatureUsageItem,
)


# 旧数据：升级前 resource / video_analysis 都没写 feature_key，
# 新图表里把这种行从聚合里排掉（数据仍在表里，只是不展示在图表）。
_LEGACY_NO_FEATURE_KEY_TYPES: set[str] = {
    FeatureType.RESOURCE.value,
    FeatureType.VIDEO_ANALYSIS.value,
}


class AdminDashboardService:
    """运营后台的数据驾驶舱服务。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_stats(self) -> DashboardStats:
        shanghai = ZoneInfo(TIMEZONE_SHANGHAI)
        now_sh = datetime.now(shanghai)
        today_start = now_sh.replace(hour=0, minute=0, second=0, microsecond=0)
        # 周一为一周起点
        week_start = today_start - timedelta(days=today_start.weekday())

        total_users = (await self.db.execute(
            select(func.count(User.id))
        )).scalar() or 0

        # DAU/WAU 口径：user_operation_logs 表里今日/本周有任意一条记录的去重用户。
        # 等价于「至少使用或访问过一个功能的用户」，覆盖资源生成 / 视频分析 / 我的课程
        # 访问 / 智能体点击 / 智能对话 等所有埋点入口。
        dau = (await self.db.execute(
            select(func.count(distinct(UserOperationLog.user_id)))
            .where(UserOperationLog.user_id.is_not(None))
            .where(UserOperationLog.create_time >= today_start)
        )).scalar() or 0

        wau = (await self.db.execute(
            select(func.count(distinct(UserOperationLog.user_id)))
            .where(UserOperationLog.user_id.is_not(None))
            .where(UserOperationLog.create_time >= week_start)
        )).scalar() or 0

        return DashboardStats(
            total_users=int(total_users),
            dau=int(dau),
            wau=int(wau),
            as_of=format_datetime(now_sh) or "",
        )

    async def list_users(
        self,
        keyword: str | None,
        limit: int,
        offset: int,
        role: str | None = None,
    ) -> list[AdminUserDetail]:
        stmt = select(User).order_by(User.create_time.desc())
        if keyword and keyword.strip():
            pattern = f"%{keyword.strip()}%"
            stmt = stmt.where(or_(
                User.name.ilike(pattern),
                User.zju_id.ilike(pattern),
                User.department.ilike(pattern),
                User.phone.ilike(pattern),
                User.email.ilike(pattern),
            ))
        if role:
            stmt = stmt.where(User.role == role)
        stmt = stmt.limit(limit).offset(offset)
        rows = (await self.db.execute(stmt)).scalars().all()
        return [_user_to_detail(u) for u in rows]

    async def build_users_xlsx(self, keyword: str | None, role: str | None = None) -> bytes:
        # 全量导出（不分页）；如未来量大可在此追加 limit
        stmt = select(User).order_by(User.create_time.desc())
        if keyword and keyword.strip():
            pattern = f"%{keyword.strip()}%"
            stmt = stmt.where(or_(
                User.name.ilike(pattern),
                User.zju_id.ilike(pattern),
                User.department.ilike(pattern),
                User.phone.ilike(pattern),
                User.email.ilike(pattern),
            ))
        if role:
            stmt = stmt.where(User.role == role)
        users = (await self.db.execute(stmt)).scalars().all()

        headers = ["序号", "用户ID", "姓名", "学工号", "学院", "角色", "手机号", "邮箱", "注册时间"]
        body: list[list] = []
        for index, u in enumerate(users, start=1):
            body.append([
                index,
                u.id,
                u.name or "",
                u.zju_id or "",
                u.department or "",
                u.role or "",
                u.phone or "",
                u.email or "",
                format_datetime(u.create_time) or "",
            ])
        return build_workbook("用户列表", headers, body)

    async def list_feature_usage(
        self,
        start: datetime | None,
        end: datetime | None,
    ) -> list[FeatureUsageItem]:
        """常驻功能 + 上架智能体合并的使用排行。

        - 常驻 12 个 slot（4 资源 + 我的课程 + 智能对话 + 智云课堂 + 上传视频
          + 文本分析 + PPT 分析 + 论文审查 + 反馈提交）始终全量返回，缺数据补 0；
          顺序：非待上线按 count 倒序，待上线钉在最后（前端 BarChart 二次排序
          也能保证 0 计数自然落底）。
        - 升级前 feature_type='resource'/'video_analysis' 且 feature_key IS NULL
          的旧数据从聚合中排除，不污染新图表。
        - 智能体行按 count 倒序追加。
        """
        # 1) 常驻功能聚合：按 (feature_type, feature_key) 分组
        resident_stmt = (
            select(
                UserOperationLog.feature_type,
                UserOperationLog.feature_key,
                func.count(UserOperationLog.id).label("c"),
                func.count(distinct(UserOperationLog.user_id)).label("uu"),
            )
            .where(UserOperationLog.feature_type != FeatureType.AGENT.value)
            .where(not_(and_(
                UserOperationLog.feature_type.in_(_LEGACY_NO_FEATURE_KEY_TYPES),
                UserOperationLog.feature_key.is_(None),
            )))
            .group_by(UserOperationLog.feature_type, UserOperationLog.feature_key)
        )
        resident_stmt = _apply_time_range(resident_stmt, start, end)
        resident_rows = (await self.db.execute(resident_stmt)).all()

        # 装进 dict 以便按 slot 零填充
        agg: dict[tuple[str, str | None], tuple[int, int]] = {
            (ft, fk): (int(cnt or 0), int(uu or 0))
            for ft, fk, cnt, uu in resident_rows
        }

        slot_items: list[FeatureUsageItem] = []
        for slot in RESIDENT_FEATURE_SLOTS:
            cnt, uu = agg.get(slot, (0, 0))
            ft, fk = slot
            slot_items.append(FeatureUsageItem(
                feature_type=ft,
                feature_key=fk,
                label=FEATURE_DISPLAY.get(slot, ft),
                count=cnt,
                unique_users=uu,
                pending=slot in PENDING_FEATURE_SLOTS,
            ))

        # 非待上线按 count 倒序；待上线钉到最后
        active = [it for it in slot_items if not it.pending]
        pending = [it for it in slot_items if it.pending]
        active.sort(key=lambda x: x.count, reverse=True)
        items: list[FeatureUsageItem] = active + pending

        # 2) 上架智能体聚合（feature_type='agent' AND agents.enabled=true）
        agent_stmt = (
            select(
                Agent.id,
                Agent.title,
                func.count(UserOperationLog.id).label("c"),
                func.count(distinct(UserOperationLog.user_id)).label("uu"),
            )
            .join(UserOperationLog, UserOperationLog.feature_key == Agent.id)
            .where(UserOperationLog.feature_type == FeatureType.AGENT.value)
            .where(Agent.enabled.is_(True))
            .group_by(Agent.id, Agent.title)
            .order_by(func.count(UserOperationLog.id).desc())
        )
        agent_stmt = _apply_time_range(agent_stmt, start, end)
        agent_rows = (await self.db.execute(agent_stmt)).all()

        for aid, title, cnt, uu in agent_rows:
            items.append(FeatureUsageItem(
                feature_type=FeatureType.AGENT.value,
                feature_key=aid,
                label=title or "(未命名智能体)",
                count=int(cnt or 0),
                unique_users=int(uu or 0),
            ))

        return items

    async def list_agent_usage(
        self,
        start: datetime | None,
        end: datetime | None,
        limit: int,
    ) -> list[AgentUsageItem]:
        """智能体使用 Top N（仅 enabled=true）。"""
        stmt = (
            select(
                Agent.id,
                Agent.title,
                func.count(UserOperationLog.id).label("c"),
                func.count(distinct(UserOperationLog.user_id)).label("uu"),
            )
            .join(UserOperationLog, UserOperationLog.feature_key == Agent.id)
            .where(UserOperationLog.feature_type == FeatureType.AGENT.value)
            .where(Agent.enabled.is_(True))
            .group_by(Agent.id, Agent.title)
            .order_by(func.count(UserOperationLog.id).desc())
            .limit(limit)
        )
        stmt = _apply_time_range(stmt, start, end)
        rows = (await self.db.execute(stmt)).all()
        return [
            AgentUsageItem(
                agent_id=aid,
                title=title or "(未命名智能体)",
                count=int(cnt or 0),
                unique_users=int(uu or 0),
            )
            for aid, title, cnt, uu in rows
        ]


def _user_to_detail(u: User) -> AdminUserDetail:
    return AdminUserDetail(
        id=u.id,
        zju_id=u.zju_id,
        name=u.name,
        department=u.department,
        phone=u.phone,
        email=u.email,
        role=u.role or "student",
        create_time=format_datetime(u.create_time),
    )


def _apply_time_range(stmt, start: datetime | None, end: datetime | None):
    if start is not None:
        stmt = stmt.where(UserOperationLog.create_time >= start)
    if end is not None:
        stmt = stmt.where(UserOperationLog.create_time < end)
    return stmt
