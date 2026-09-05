import asyncio
from typing import Any, Coroutine

from common.utils.logger import get_logger

logger = get_logger(__name__)


def run_in_background(
    coro: Coroutine[Any, Any, Any],
    *,
    name: str | None = None,
) -> asyncio.Task[Any]:
    """
    将协程提交到后台执行，立即返回，不阻塞当前调用。

    用法：
        run_in_background(some_async_func(arg1, arg2), name="my_task")

    Args:
        coro: 要后台执行的协程
        name: 任务名称，方便排查日志

    Returns:
        asyncio.Task 对象
    """
    return _task_manager.create_task(coro, name=name)


class BackgroundTaskManager:
    """
    后台任务管理器（单例）

    自动追踪已创建的任务，防止被垃圾回收，并在完成后自动清理。
    """

    _instance: "BackgroundTaskManager | None" = None
    _tasks: set[asyncio.Task[Any]]

    def __new__(cls) -> "BackgroundTaskManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._tasks = set()
        return cls._instance

    def create_task(
        self,
        coro: Coroutine[Any, Any, Any],
        *,
        name: str | None = None,
    ) -> asyncio.Task[Any]:
        """
        创建一个后台任务，立即返回 Task 对象，不等待执行完成。

        Args:
            coro: 要执行的协程
            name: 任务名称，用于日志标识

        Returns:
            asyncio.Task 对象，可用于后续取消或等待
        """
        task = asyncio.create_task(coro, name=name)
        self._tasks.add(task)
        task.add_done_callback(self._on_task_done)
        return task

    def _on_task_done(self, task: asyncio.Task[Any]) -> None:
        """任务完成回调，清理引用并记录异常。"""
        self._tasks.discard(task)
        if task.cancelled():
            logger.warning("后台任务被取消: %s", task.get_name())
            return

        exc = task.exception()
        if exc is not None:
            logger.exception("后台任务执行异常: %s", task.get_name(), exc_info=exc)


# 全局单例
_task_manager = BackgroundTaskManager()
