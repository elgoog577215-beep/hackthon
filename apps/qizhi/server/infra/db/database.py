import os
from datetime import timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base

from common.config import settings
from common.utils.logger import get_logger



logger = get_logger(__name__)


# 创建基类
Base = declarative_base()

# 创建数据库连接和会话（同步，用于建表）
sync_engine = create_engine(
    settings.SYNC_DATABASE_URL,
    echo=False,
)

# 创建数据库连接和会话（异步，用于 CRUD）
async_engine = create_async_engine(
    settings.ASYNC_DATABASE_URL,
    echo=False,
    pool_size=settings.POOL_SIZE,
    max_overflow=settings.MAX_OVERFLOW,
    pool_recycle=settings.POOL_RECYCLE,
    pool_pre_ping=True,
)

# 创建异步会话
AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_ = AsyncSession,
    autoflush = False,
    expire_on_commit = False,
)
# 创建依赖函数（异步）
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


def init_db():
    """初始化数据库表结构 + 启动迁移 + 写入必要的 seed 数据。"""
    Base.metadata.create_all(sync_engine)

    # 给已有表加新列 / 索引（必须在 create_all 之后、bootstrap / seed 之前）
    _apply_startup_migrations()

    # 历史资源版本号回填（仅对从未被版本化逻辑触碰过的分组生效，幂等）
    _backfill_resource_versions()

    # 视频分析 V2 升级迁移：已关闭，无需刷库
    # _migrate_video_analysis_to_v2()

    # 白名单 zju_id 自动升级为 admin（兜底，OAuth 首登时也会再补一次）
    _bootstrap_admin_whitelist()

    # 智能体广场 seed：仅在 agents 表为空时执行
    # 函数内 import 避免循环依赖
    from infra.db.seeds.agent_seed import seed_agents
    seed_agents()

    # 仅本地开发：往空库灌驾驶舱所需的假用户与会话历史
    if os.getenv("ENV") == "LOCAL":
        from infra.db.seeds.dashboard_seed import seed_dashboard
        seed_dashboard()


# 启动时执行的幂等 DDL 迁移：用于给已有表加新列 / 索引。Base.metadata.create_all
# 不会修改已有表，所以新增列要单独 ALTER。这里全部使用 IF NOT EXISTS 保证重启幂等。
_STARTUP_MIGRATIONS: list[tuple[str, str]] = [
    (
        "users.role",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(20) NOT NULL DEFAULT 'student'",
    ),
    (
        "users.role.index",
        "CREATE INDEX IF NOT EXISTS ix_users_role ON users(role)",
    ),
    # 性能优化索引（P0）：列表查询常用过滤列
    ("videos.user_id.index", "CREATE INDEX IF NOT EXISTS ix_videos_user_id ON videos(user_id)"),
    ("videos.create_time.index", "CREATE INDEX IF NOT EXISTS ix_videos_create_time ON videos(create_time DESC)"),
    ("sessions.user_id.index", "CREATE INDEX IF NOT EXISTS ix_sessions_user_id ON sessions(user_id)"),
    ("sessions.create_time.index", "CREATE INDEX IF NOT EXISTS ix_sessions_create_time ON sessions(create_time DESC)"),
    ("resources.creator_id.index", "CREATE INDEX IF NOT EXISTS ix_resources_creator_id ON resources(creator_id)"),
    ("resources.related_course_id.index", "CREATE INDEX IF NOT EXISTS ix_resources_related_course_id ON resources(related_course_id)"),
    ("resources.related_unit_id.index", "CREATE INDEX IF NOT EXISTS ix_resources_related_unit_id ON resources(related_unit_id)"),
    ("resources.create_time.index", "CREATE INDEX IF NOT EXISTS ix_resources_create_time ON resources(create_time DESC)"),
    ("user_essay_task.user_id.index", "CREATE INDEX IF NOT EXISTS ix_user_essay_task_user_id ON user_essay_task(user_id)"),
    ("document_analyses.user_id.index", "CREATE INDEX IF NOT EXISTS ix_document_analyses_user_id ON document_analyses(user_id)"),
    ("document_analyses.create_time.index", "CREATE INDEX IF NOT EXISTS ix_document_analyses_create_time ON document_analyses(create_time DESC)"),
    ("session_histories.session_id.index", "CREATE INDEX IF NOT EXISTS ix_session_histories_session_id ON session_histories(session_id)"),
    # 智能对话附件解析文本：落库一次，历史重建时复用，避免每轮重跑 markitdown
    (
        "session_histories.file_contents",
        "ALTER TABLE session_histories ADD COLUMN IF NOT EXISTS file_contents TEXT",
    ),
    ("courses.creator_id.index", "CREATE INDEX IF NOT EXISTS ix_courses_creator_id ON courses(creator_id)"),
    # 课程展示扩展字段（grade/category/credits/major/offline_hours_ratio/offline_score_ratio）
    (
        "courses.extra_info",
        "ALTER TABLE courses ADD COLUMN IF NOT EXISTS extra_info JSONB",
    ),
    ("course_manager.manager_id.index", "CREATE INDEX IF NOT EXISTS ix_course_manager_manager_id ON course_manager(manager_id)"),
    # 资源版本化层级（课程 → 大纲版本 → 教案版本 → PPT 版本）
    (
        "resources.version_number",
        "ALTER TABLE resources ADD COLUMN IF NOT EXISTS version_number INTEGER NOT NULL DEFAULT 1",
    ),
    (
        "resources.parent_resource_id",
        "ALTER TABLE resources ADD COLUMN IF NOT EXISTS parent_resource_id VARCHAR REFERENCES resources(id) ON DELETE SET NULL",
    ),
    (
        "resources.parent_resource_id.index",
        "CREATE INDEX IF NOT EXISTS ix_resources_parent_resource_id ON resources(parent_resource_id)",
    ),
    # PPT 生成产物地址（落库以便再次进入仍可预览/下载）
    (
        "resources.ppt_html_url",
        "ALTER TABLE resources ADD COLUMN IF NOT EXISTS ppt_html_url VARCHAR",
    ),
    (
        "resources.ppt_pptx_url",
        "ALTER TABLE resources ADD COLUMN IF NOT EXISTS ppt_pptx_url VARCHAR",
    ),
    # 视频软绑定到课程 / 教案版本
    (
        "videos.related_course_id",
        "ALTER TABLE videos ADD COLUMN IF NOT EXISTS related_course_id VARCHAR REFERENCES courses(id) ON DELETE SET NULL",
    ),
    (
        "videos.related_resource_id",
        "ALTER TABLE videos ADD COLUMN IF NOT EXISTS related_resource_id VARCHAR REFERENCES resources(id) ON DELETE SET NULL",
    ),
    (
        "videos.related_course_id.index",
        "CREATE INDEX IF NOT EXISTS ix_videos_related_course_id ON videos(related_course_id)",
    ),
    (
        "videos.related_resource_id.index",
        "CREATE INDEX IF NOT EXISTS ix_videos_related_resource_id ON videos(related_resource_id)",
    ),
]


def _apply_startup_migrations() -> None:
    with sync_engine.begin() as conn:
        for label, sql in _STARTUP_MIGRATIONS:
            try:
                conn.execute(text(sql))
                logger.info(f"[database.py] startup migration ok: {label}")
            except Exception as e:
                # 幂等 DDL 理论上不会失败；失败也不阻塞启动，仅告警。
                logger.warning(f"[database.py] startup migration skipped: {label} ({e})")


def _backfill_resource_versions() -> None:
    """
    历史资源版本号回填（幂等）。

    把同一 (creator_id, related_course_id, resource_type) 分组内的存量「根级」资源
    （parent_resource_id IS NULL，历史数据全是根级）按 create_time 顺序编号为
    v1..vn。只处理「整组 version_number 仍全为默认值 1 且组内多于 1 条」的分组——
    已被版本化逻辑（创建时 max+1）触碰过的分组不再重排，避免覆盖用户删除版本后
    产生的跳号。挂在父资源下的子版本按「父资源」独立作用域编号，绝不能混入本
    分组重排，否则重启会破坏运行期分配的版本号。
    """
    with sync_engine.begin() as conn:
        result = conn.execute(
            text("""
                WITH untouched AS (
                    SELECT creator_id, COALESCE(related_course_id, '') AS course_key, resource_type
                    FROM resources
                    WHERE parent_resource_id IS NULL
                    GROUP BY creator_id, COALESCE(related_course_id, ''), resource_type
                    HAVING COUNT(*) > 1 AND MAX(version_number) = 1
                ),
                ranked AS (
                    SELECT r.id,
                           ROW_NUMBER() OVER (
                               PARTITION BY r.creator_id, COALESCE(r.related_course_id, ''), r.resource_type
                               ORDER BY r.create_time, r.id
                           ) AS rn
                    FROM resources r
                    JOIN untouched u
                      ON u.creator_id = r.creator_id
                     AND u.course_key = COALESCE(r.related_course_id, '')
                     AND u.resource_type = r.resource_type
                    WHERE r.parent_resource_id IS NULL
                )
                UPDATE resources
                SET version_number = ranked.rn
                FROM ranked
                WHERE resources.id = ranked.id AND resources.version_number <> ranked.rn
            """)
        )
        if result.rowcount:
            logger.info(f"[database.py] backfill resource versions: updated {result.rowcount} row(s)")

    # 版本号唯一约束（部分唯一索引）必须在回填之后创建，否则存量重复 v1 会让建索引失败。
    # 每条索引独立事务：建失败（如残留脏数据）只告警，不影响回填结果与启动。
    # 冲突由 service 层捕获 IntegrityError 重算重试。
    for label, sql in [
        (
            "resources.version.uq.child",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_resources_parent_type_version "
            "ON resources(parent_resource_id, resource_type, version_number) "
            "WHERE parent_resource_id IS NOT NULL",
        ),
        (
            "resources.version.uq.root",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_resources_root_scope_version "
            "ON resources(creator_id, COALESCE(related_course_id, ''), resource_type, version_number) "
            "WHERE parent_resource_id IS NULL",
        ),
    ]:
        try:
            with sync_engine.begin() as idx_conn:
                idx_conn.execute(text(sql))
            logger.info(f"[database.py] startup migration ok: {label}")
        except Exception as e:
            logger.warning(f"[database.py] startup migration skipped: {label} ({e})")


def _migrate_video_analysis_to_v2() -> None:
    """
    视频分析 V2 升级迁移（幂等）。

    旧结构的 analysis_result 已不兼容新链路，需要：
    1. 将 status='success' 且 analysis_id 存在的视频重置为 waiting，清空 analysis_result
    2. 为 waiting + analysis_id 存在、但尚未有 task_queue 记录的视频补创建异步任务
    """
    from datetime import datetime, timedelta
    from infra.db.sequence import generate_id

    with sync_engine.begin() as conn:
        # Step 1a: 清理旧结构数据（status='success' 且 analysis_id 存在）
        result = conn.execute(
            text("""
                UPDATE videos
                SET status = 'waiting', analysis_result = NULL
                WHERE status = 'success' AND analysis_id IS NOT NULL
            """)
        )
        if result.rowcount:
            logger.info(
                "[database.py] migrate v2: reset %d video(s) from success to waiting",
                result.rowcount,
            )

        # Step 0: 修复测试环境特定视频的 analysis_id
        result_fix = conn.execute(
            text("""
                UPDATE videos
                SET analysis_id = '565369f8f3217c90d8fa42abaaaa0e5c',
                    status = 'waiting',
                    analysis_result = NULL
                WHERE id = '7460170052021522432'
            """)
        )
        if result_fix.rowcount:
            logger.info(
                "[database.py] migrate v2: fixed analysis_id for video 7460170052021522432"
            )

        # Step 1b: 清理已跑过但结果为空的数据
        # 检测 analysis_result 为 NULL，或核心字段（transcript/teach_db_result 等）缺失/为 JSON null
        result_empty = conn.execute(
            text("""
                UPDATE videos
                SET status = 'waiting', analysis_result = NULL
                WHERE status = 'success' AND analysis_id IS NOT NULL
                AND (
                    analysis_result IS NULL
                    OR analysis_result ->> 'transcript' IS NULL
                    OR analysis_result ->> 'teach_db_result' IS NULL
                )
            """)
        )
        if result_empty.rowcount:
            logger.info(
                "[database.py] migrate v2: reset %d empty-result video(s)",
                result_empty.rowcount,
            )

        # Step 2: 重置已有 video_analysis 任务（success/failed → pending）
        result_reset = conn.execute(
            text("""
                UPDATE task_queue
                SET status = 'pending',
                    scheduled_at = :now,
                    completed_at = NULL,
                    error_message = NULL,
                    retry_count = 0
                WHERE task_type = 'video_analysis'
                  AND status <> 'pending'
            """),
            {"now": datetime.now(ZoneInfo("Asia/Shanghai")) - timedelta(seconds=5)},
        )
        if result_reset.rowcount:
            logger.info(
                "[database.py] migrate v2: reset %d task_queue record(s) to pending",
                result_reset.rowcount,
            )

        # Step 3: 幂等补录 task_queue（只补没有对应记录的视频）
        rows = conn.execute(
            text("""
                SELECT id FROM videos
                WHERE status = 'waiting' AND analysis_id IS NOT NULL
                AND NOT EXISTS (
                    SELECT 1 FROM task_queue
                    WHERE business_id = videos.id AND task_type = 'video_analysis'
                )
            """)
        ).fetchall()

        for row in rows:
            video_id = row[0]
            task_id = generate_id()
            # 旧视频超星数据早已就绪，直接设为当前时间，Worker 启动后第一次轮询即可执行
            scheduled_at = datetime.now(ZoneInfo("Asia/Shanghai")) - timedelta(seconds=5)
            conn.execute(
                text("""
                    INSERT INTO task_queue (id, task_type, business_id, status, scheduled_at)
                    VALUES (:id, 'video_analysis', :business_id, 'pending', :scheduled_at)
                """),
                {
                    "id": task_id,
                    "business_id": video_id,
                    "scheduled_at": scheduled_at,
                },
            )
            logger.info(
                "[database.py] migrate v2: created task %s for video %s",
                task_id,
                video_id,
            )

        if rows:
            logger.info(
                "[database.py] migrate v2: created %d task_queue record(s)",
                len(rows),
            )


def _bootstrap_admin_whitelist() -> None:
    """把 settings.ADMIN_ZJU_IDS 里的用户 role 写为 admin（环境变量是兜底真值源）。"""
    ids = list(settings.ADMIN_ZJU_IDS)
    if not ids:
        return
    with sync_engine.begin() as conn:
        result = conn.execute(
            text("UPDATE users SET role = 'admin' WHERE zju_id = ANY(:ids) AND role <> 'admin'"),
            {"ids": ids},
        )
        if result.rowcount:
            logger.info(f"[database.py] bootstrap admin whitelist: promoted {result.rowcount} user(s)")
