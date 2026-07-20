"""Asynchronous, replay-safe reconciliation of teaching-representation state."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from teaching_representations import TeachingRepresentationRepository

logger = logging.getLogger(__name__)


class RepresentationReconciliationService:
    """Consume course revision notifications; operation logs remain the durable ledger."""

    def __init__(self, course_repository: Any, representation_repository: TeachingRepresentationRepository) -> None:
        self.course_repository = course_repository
        self.representation_repository = representation_repository
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._pending: set[str] = set()
        self._worker: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._worker and not self._worker.done():
            return
        self._worker = asyncio.create_task(self._run())
        list_courses = getattr(self.course_repository.storage, "list_courses", None)
        if callable(list_courses):
            for course in await asyncio.to_thread(list_courses):
                self.enqueue(str(course.get("course_id") or ""), {})

    async def shutdown(self) -> None:
        worker = self._worker
        self._worker = None
        if worker and not worker.done():
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)

    def enqueue(self, course_id: str, _receipt: dict[str, Any] | None = None) -> None:
        course_id = str(course_id or "")
        if not course_id or course_id in self._pending:
            return
        self._pending.add(course_id)
        self._queue.put_nowait(course_id)

    async def reconcile_now(self, course_id: str) -> dict[str, Any]:
        def reconcile() -> dict[str, Any]:
            raw = self.course_repository.load_raw(course_id)
            registry = self.representation_repository.reconcile_course_operation_log(
                course_id,
                list(raw.get("course_operation_log") or []),
            )
            return registry.model_dump(mode="json")

        return await asyncio.to_thread(reconcile)

    async def _run(self) -> None:
        try:
            while True:
                course_id = await self._queue.get()
                try:
                    await self.reconcile_now(course_id)
                except Exception as exc:
                    logger.warning("Representation reconciliation failed for %s: %s", course_id, exc)
                finally:
                    self._pending.discard(course_id)
                    self._queue.task_done()
        except asyncio.CancelledError:
            return


__all__ = ["RepresentationReconciliationService"]
