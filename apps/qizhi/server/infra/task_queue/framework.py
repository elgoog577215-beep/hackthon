import asyncio
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from common.utils.logger import get_logger
from infra.db.models.task_queue import TaskQueue

logger = get_logger(__name__)


class RetryableError(Exception):
    """
    业务可重试状态（如第三方数据未就绪）。

    抛出此异常表示任务本身没有出错，只是条件尚未满足，
    框架会重新调度但**不递增 retry_count**。
    """
    pass


class TaskHandler(ABC):
    """
    任务处理器抽象基类（策略模式）。

    子类只需实现：
    - task_type: 任务类型标识
    - execute: 业务逻辑

    可覆盖：
    - should_retry: 自定义重试判断
    - next_schedule_time: 自定义下次调度时间
    """

    @property
    @abstractmethod
    def task_type(self) -> str:
        """任务类型标识，必须唯一。"""
        pass

    @abstractmethod
    async def execute(self, task: TaskQueue, db: AsyncSession) -> None:
        """
        执行业务逻辑。

        Args:
            task: 任务记录
            db: 数据库会话

        Raises:
            Exception: 执行失败时抛出异常，框架会自动处理重试/失败
        """
        pass

    async def should_retry(self, task: TaskQueue, error: Exception) -> bool:
        """
        判断任务失败后是否重试。

        默认不重试，子类可覆盖。
        """
        return False

    async def next_schedule_time(
        self,
        task: TaskQueue,
        error: Exception | None = None,
    ) -> datetime:
        """
        计算下次调度时间。

        默认 10 分钟后，子类可覆盖。
        """
        return datetime.now(ZoneInfo("Asia/Shanghai")) + timedelta(minutes=10)


class AsyncTaskFramework:
    """
    通用异步任务框架（模板方法模式）。

    职责：
    - 任务注册（按类型绑定 Handler）
    - 任务创建
    - 轮询调度（加锁、执行、状态流转）
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self._handlers: dict[str, TaskHandler] = {}

    def register(self, handler: TaskHandler) -> None:
        """注册任务处理器。"""
        if handler.task_type in self._handlers:
            logger.warning("任务类型 %s 已被注册，将覆盖", handler.task_type)
        self._handlers[handler.task_type] = handler
        logger.info("注册任务处理器: %s", handler.task_type)

    async def create_task(
        self,
        task_type: str,
        business_id: str,
        scheduled_at: datetime | None = None,
    ) -> TaskQueue:
        """创建异步任务。"""
        if scheduled_at is None:
            scheduled_at = datetime.now(ZoneInfo("Asia/Shanghai"))

        task = TaskQueue(
            task_type=task_type,
            business_id=business_id,
            status="pending",
            scheduled_at=scheduled_at,
        )
        self.db.add(task)
        await self.db.commit()
        await self.db.refresh(task)
        logger.info(
            "创建任务: %s (type=%s, business_id=%s)",
            task.id,
            task_type,
            business_id,
        )
        return task

    async def recover_processing_tasks(self, task_types: list[str] | None = None) -> int:
        """启动恢复：把残留的 processing 任务重置为 pending，使其被重新轮询执行。

        背景：worker 只轮询 pending 任务。若进程在某任务 processing 期间退出（重启/崩溃），
        该任务会永久滞留 processing、不再被执行（表现为对应视频一直卡在「分析中」）。进程
        启动时存在的 processing 任务必然属于已退出的旧进程，可安全重置为 pending 重新执行。

        返回重置的任务数。仅适用于单 worker 部署（本项目部署即单 worker）；多 worker 下本
        方法可能重置另一活跃 worker 正在执行的任务、导致重复执行。
        """
        query = (
            update(TaskQueue)
            .where(TaskQueue.status == "processing")
            .values(status="pending", error_message="进程重启，自动恢复待重试")
        )
        if task_types is not None:
            query = query.where(TaskQueue.task_type.in_(task_types))
        result = await self.db.execute(query)
        await self.db.commit()
        return result.rowcount

    async def poll_and_execute(
        self,
        batch_size: int = 10,
        task_types: list[str] | None = None,
        max_concurrency: int = 1,
    ) -> None:
        """
        轮询并执行任务。

        Args:
            batch_size: 每轮最大处理任务数
            task_types: 只处理指定类型的任务；None 表示处理全部已注册类型
            max_concurrency: 最大并发执行数。1=串行（默认，行为与改造前一致）；
                >1 时多个任务并发执行，并发度由信号量限到该值。并发模式下每个任务
                使用独立 DB 会话——AsyncSession 不可并发共享，必须各自新建。

        流程：
        1. 查询已到调度时间的 pending 任务
        2. 加锁（CAS 更新 status=pending → processing）
        3. 找到对应 Handler 执行
        4. 成功 → success；失败 → 根据 should_retry 决定重试或 failed
        """
        now = datetime.now(ZoneInfo("Asia/Shanghai"))
        logger.info(
            "[framework] 轮询条件: status=pending, scheduled_at<=%s, task_types=%s",
            now.isoformat(),
            task_types or list(self._handlers.keys()),
        )

        query = (
            select(TaskQueue)
            .where(TaskQueue.status == "pending")
            .where(TaskQueue.scheduled_at <= now)
        )
        if task_types is not None:
            query = query.where(TaskQueue.task_type.in_(task_types))
        else:
            # 未指定时只查已注册类型的任务，避免未知类型空跑
            registered = list(self._handlers.keys())
            if registered:
                query = query.where(TaskQueue.task_type.in_(registered))

        result = await self.db.execute(
            query.order_by(TaskQueue.scheduled_at).limit(batch_size)
        )
        tasks = result.scalars().all()

        if not tasks:
            logger.info("[framework] 本轮无待执行任务")
            return

        logger.info("[framework] 本轮轮询到 %d 个任务", len(tasks))

        concurrency = max(1, max_concurrency)
        task_ids = [t.id for t in tasks]

        if concurrency == 1:
            # 串行：复用本轮轮询会话逐个执行（默认，与改造前行为一致）
            for task_id in task_ids:
                await self._run_task(task_id, self.db)
            return

        # 并发：每个任务独立会话，信号量限流到 max_concurrency（对应可用 GPU 槽位数）。
        # 共享同一 AsyncSession 并发执行会冲突，故必须各自新建会话。
        from infra.db.database import AsyncSessionLocal

        sem = asyncio.Semaphore(concurrency)

        async def _runner(task_id: str) -> None:
            async with sem:
                async with AsyncSessionLocal() as task_db:
                    await self._run_task(task_id, task_db)

        # _run_task 内部已捕获并落库异常；return_exceptions 仅作兜底，避免单个任务
        # 的意外异常中断整批。
        await asyncio.gather(
            *(_runner(tid) for tid in task_ids), return_exceptions=True
        )

    async def _run_task(self, task_id: str, db: AsyncSession) -> None:
        """对单个任务：加锁 → 取任务 → 执行 → 状态流转。

        使用传入的会话，支持并发隔离（每个并发任务一个会话）。
        """
        locked = await self._lock_task(db, task_id)
        if not locked:
            logger.debug("任务 %s 未抢到锁（已被其他执行抢先或已处理）", task_id)
            return

        task = (
            await db.execute(select(TaskQueue).where(TaskQueue.id == task_id))
        ).scalars().first()
        if task is None:
            logger.error("加锁后未找到任务: %s", task_id)
            return

        handler = self._handlers.get(task.task_type)
        if not handler:
            logger.error("未找到任务类型 %s 的处理器", task.task_type)
            await self._mark_failed(db, task_id, f"未找到处理器: {task.task_type}")
            return

        try:
            await handler.execute(task, db)
            await self._mark_success(db, task_id)
            logger.info("任务执行成功: %s", task_id)
        except Exception as e:
            logger.exception("任务执行失败: %s", task_id)
            should_retry = await handler.should_retry(task, e)
            if should_retry:
                next_time = await handler.next_schedule_time(task, e)
                if isinstance(e, RetryableError):
                    # 业务可重试状态：不递增 retry_count，仅更新调度时间
                    await self._mark_reschedule(db, task_id, str(e), next_time)
                    logger.info("任务 reschedule: %s", task_id)
                else:
                    await self._mark_retry(db, task_id, str(e), next_time)
                    logger.info(
                        "任务标记为重试: %s, retry_count=%d",
                        task_id,
                        task.retry_count + 1,
                    )
            else:
                await self._mark_failed(db, task_id, str(e))
                logger.info("任务标记为失败: %s", task_id)

    async def _lock_task(self, db: AsyncSession, task_id: str) -> bool:
        """CAS 加锁：pending → processing"""
        result = await db.execute(
            update(TaskQueue)
            .where(TaskQueue.id == task_id)
            .where(TaskQueue.status == "pending")
            .values(status="processing")
        )
        await db.commit()
        return result.rowcount > 0

    async def _mark_success(self, db: AsyncSession, task_id: str) -> None:
        await db.execute(
            update(TaskQueue)
            .where(TaskQueue.id == task_id)
            .values(
                status="success",
                completed_at=datetime.now(ZoneInfo("Asia/Shanghai")),
            )
        )
        await db.commit()

    async def _mark_reschedule(
        self,
        db: AsyncSession,
        task_id: str,
        error_message: str,
        scheduled_at: datetime,
    ) -> None:
        """业务可重试状态：不递增 retry_count，仅更新调度时间与错误说明。"""
        await db.execute(
            update(TaskQueue)
            .where(TaskQueue.id == task_id)
            .values(
                status="pending",
                error_message=error_message,
                scheduled_at=scheduled_at,
            )
        )
        await db.commit()

    async def _mark_retry(
        self,
        db: AsyncSession,
        task_id: str,
        error_message: str,
        scheduled_at: datetime,
    ) -> None:
        await db.execute(
            update(TaskQueue)
            .where(TaskQueue.id == task_id)
            .values(
                status="pending",
                retry_count=TaskQueue.retry_count + 1,
                error_message=error_message,
                scheduled_at=scheduled_at,
            )
        )
        await db.commit()

    async def _mark_failed(self, db: AsyncSession, task_id: str, error_message: str) -> None:
        await db.execute(
            update(TaskQueue)
            .where(TaskQueue.id == task_id)
            .values(
                status="failed",
                error_message=error_message,
            )
        )
        await db.commit()
