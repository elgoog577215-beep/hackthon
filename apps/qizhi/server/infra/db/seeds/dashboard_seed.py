"""
驾驶舱本地调试 seed：仅在 ENV=LOCAL 且 users 表为空时执行。

灌入 5 个假用户（含一个 zju_id=99999999 的开发管理员）、若干 session_histories，
以及一批 user_operation_logs，让数据驾驶舱的「累计用户 / 日活 / 周活 / 功能使用
排序」全部有数可看。

注意：自 2026-05-17 起 DAU/WAU 改为按 user_operation_logs 算，必须同时灌该表。
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session as SASession

from common.models.constants import TIMEZONE_SHANGHAI
from common.models.operation_log import FeatureType
from common.utils.logger import get_logger
from infra.db.database import sync_engine
from infra.db.models.session import Session, SessionHistory
from infra.db.models.user import User
from infra.db.models.user_operation_log import UserOperationLog
from infra.db.sequence import generate_id


logger = get_logger(__name__)


USER_SEED_DATA: list[dict] = [
    {
        "zju_id": "99999999",
        "name": "开发管理员",
        "department": "启智项目组",
        "phone": "13800000000",
        "email": "dev-admin@example.local",
    },
    {
        "zju_id": "31900001",
        "name": "张三",
        "department": "计算机学院",
        "phone": "13800000001",
        "email": "zhangsan@example.local",
    },
    {
        "zju_id": "31900002",
        "name": "李四",
        "department": "数学学院",
        "phone": "13800000002",
        "email": "lisi@example.local",
    },
    {
        "zju_id": "31900003",
        "name": "王五",
        "department": "物理学院",
        "phone": "13800000003",
        "email": "wangwu@example.local",
    },
    {
        "zju_id": "31900004",
        "name": "赵六",
        "department": "化学学院",
        "phone": "13800000004",
        "email": "zhaoliu@example.local",
    },
]


def seed_dashboard() -> None:
    """若 users 表为空，造一批用户 + 会话历史，让驾驶舱有非零数据。"""
    with SASession(sync_engine) as session:
        existing_users = session.execute(select(func.count(User.id))).scalar() or 0
        if existing_users > 0:
            logger.info(f"users 表已存在 {existing_users} 条数据，跳过 dashboard seed")
            return

        logger.info(f"开始 dashboard seed：{len(USER_SEED_DATA)} 个用户")

        shanghai = ZoneInfo(TIMEZONE_SHANGHAI)
        now_sh = datetime.now(shanghai)
        today_start = now_sh.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today_start - timedelta(days=today_start.weekday())

        # 时间点：今天、本周早些、上周、上月，确保 DAU/WAU/总量都非零
        today_offsets = [timedelta(hours=2), timedelta(hours=9)]
        this_week_offsets = [
            week_start + timedelta(days=1, hours=10) - today_start,
            week_start + timedelta(days=2, hours=15) - today_start,
        ]
        last_week_offsets = [today_start - timedelta(days=8, hours=-3) - today_start]
        last_month_offsets = [today_start - timedelta(days=35) - today_start]

        for user_index, data in enumerate(USER_SEED_DATA):
            user = User(id=generate_id(), **data)
            session.add(user)
            session.flush()

            chat_session = Session(
                id=generate_id(),
                title=f"{data['name']} 的会话",
                user_id=user.id,
            )
            session.add(chat_session)
            session.flush()

            # 不同用户分配不同条数，确保数据看起来不太"齐"
            offsets_for_user: list[timedelta] = []
            offsets_for_user.extend(today_offsets[: 1 + (user_index % 2)])
            offsets_for_user.extend(this_week_offsets[: 1 + (user_index % 2)])
            if user_index % 2 == 0:
                offsets_for_user.extend(last_week_offsets)
            if user_index == 0:
                offsets_for_user.extend(last_month_offsets)

            for h_index, offset in enumerate(offsets_for_user):
                history_time = today_start + offset
                role = "user" if h_index % 2 == 0 else "assistant"
                session.add(SessionHistory(
                    id=generate_id(),
                    chat_id=f"chat-{user_index}-{h_index}",
                    role=role,
                    message_type="text",
                    message_content=f"[seed] {data['name']} 的第 {h_index + 1} 条历史消息",
                    cost_time=120,
                    status="success",
                    create_time=history_time,
                    session_id=chat_session.id,
                    user_id=user.id,
                ))

            # 同时灌一批 user_operation_logs，让常驻功能图表 + DAU/WAU 都看得到数据。
            # 覆盖：chat / resource(outline,ppt) / course=visit / video=upload+zhiyun。
            # 时间锚点：今天 (today_start + 几小时) / 本周早些 (week_start + 偏移)
            # / 上周 (today_start - 几天)，保证所有时间都在「过去」。
            op_seeds: list[tuple[FeatureType, str | None, str, datetime]] = [
                (FeatureType.CHAT, None, "send", today_start + timedelta(hours=3)),
                (FeatureType.RESOURCE, "outline", "generate", today_start + timedelta(hours=4)),
                (FeatureType.COURSE, None, "visit", today_start + timedelta(hours=5)),
            ]
            if user_index % 2 == 0:
                op_seeds.append((FeatureType.RESOURCE, "ppt", "generate", week_start + timedelta(days=1, hours=10)))
                op_seeds.append((FeatureType.VIDEO_ANALYSIS, "upload", "analyze", week_start + timedelta(days=2, hours=15)))
            if user_index % 3 == 0:
                op_seeds.append((FeatureType.VIDEO_ANALYSIS, "zhiyun", "analyze", today_start - timedelta(days=8, hours=-3)))

            for ft, fk, action, ts in op_seeds:
                # 安全网：万一某个锚点算到未来（比如本周还没到周二），跳过该行
                if ts > now_sh:
                    continue
                session.add(UserOperationLog(
                    id=generate_id(),
                    user_id=user.id,
                    feature_type=ft.value,
                    feature_key=fk,
                    action=action,
                    create_time=ts,
                ))

        session.commit()
        logger.info("dashboard seed 完成")
