import asyncio

from infra.db.database import AsyncSessionLocal
from infra.task_queue.framework import AsyncTaskFramework, TaskHandler
from common.utils.logger import get_logger

logger = get_logger(__name__)


def _normalize_handlers(
    handlers: list[tuple],
) -> list[tuple[TaskHandler, int, int]]:
    """把 (handler, interval) 或 (handler, interval, max_concurrency) 统一成三元组。

    省略 max_concurrency 时默认 1（串行），兼容旧的二元组写法。
    """
    normalized: list[tuple[TaskHandler, int, int]] = []
    for item in handlers:
        if len(item) >= 3:
            handler, interval, concurrency = item[0], item[1], item[2]
        else:
            handler, interval, concurrency = item[0], item[1], 1
        normalized.append((handler, interval, max(1, int(concurrency))))
    return normalized


async def start_task_worker(handlers: list[tuple]) -> None:
    """
    启动任务队列 worker，支持多 Handler 按不同周期独立轮询。

    每个 Handler 运行在独立的 asyncio 循环中，互不干扰。
    高频任务（如 5 秒）与低频任务（如 10 分钟）可共存。

    Args:
        handlers: [(handler, poll_interval_seconds[, max_concurrency]), ...]
                  max_concurrency 省略=1（串行）；>1 时该类型任务并发执行（每个任务
                  独立 DB 会话，并发度受信号量限制）。
                  例：[(VideoAnalysisHandler(), 600), (LocalVideoAnalysisHandler(), 15, 4)]
    """
    handlers = _normalize_handlers(handlers)

    # 启动恢复：把上次进程残留的 processing 任务重置为 pending，让被重启/崩溃打断的任务
    # 在下一轮轮询自动续跑（也能救回卡在「分析中」的视频）。单 worker 部署下安全。
    recover_types = [h.task_type for h, _, _ in handlers]
    try:
        async with AsyncSessionLocal() as db:
            framework = AsyncTaskFramework(db)
            recovered = await framework.recover_processing_tasks(recover_types)
            if recovered:
                logger.warning("[worker] 启动恢复：%d 个残留 processing 任务已重置为 pending", recovered)
            else:
                logger.info("[worker] 启动恢复：无残留 processing 任务")
    except Exception:
        logger.exception("[worker] 启动恢复失败（不影响后续轮询）")

    async def _loop(handler: TaskHandler, interval: int, concurrency: int) -> None:
        logger.info(
            "[worker] %s worker 启动，轮询间隔 %ds，最大并发 %d",
            handler.task_type,
            interval,
            concurrency,
        )
        while True:
            logger.info("[worker] %s 开始轮询...", handler.task_type)
            try:
                async with AsyncSessionLocal() as db:
                    framework = AsyncTaskFramework(db)
                    framework.register(handler)
                    await framework.poll_and_execute(
                        task_types=[handler.task_type],
                        batch_size=10,
                        max_concurrency=concurrency,
                    )
            except Exception:
                logger.exception("[worker] 任务轮询异常: %s", handler.task_type)
            logger.info("[worker] %s 轮询结束，休眠 %ds", handler.task_type, interval)
            await asyncio.sleep(interval)

    # 为每个 Handler 启动独立循环
    tasks = [
        asyncio.create_task(_loop(h, interval, concurrency), name=f"worker:{h.task_type}")
        for h, interval, concurrency in handlers
    ]
    await asyncio.gather(*tasks)
