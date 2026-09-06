import asyncio
import random
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select, func

from app.config import MAX_CONCURRENT_PAGES, SCAN_INTERVAL_SECONDS, SUMMARY_TIMEOUT_MINUTES
from app.database import AsyncSessionLocal, init_db
from app.models import Task, TaskPage
from app.services.upload import process_page_stage

from app.logger import get_logger

logger = get_logger(__name__)

# Non-terminal states for pages that need recovery
PAGE_ACTIVE_STATES = ("classifying", "classified")

scheduler = AsyncIOScheduler()
_executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_PAGES)


@asynccontextmanager
async def lifespan(_app):  # noqa: ARG001
    init_db()
    logger.info("Database tables created")

    await _recover_stuck()

    scheduler.add_job(
        scan_and_dispatch,
        "interval",
        seconds=SCAN_INTERVAL_SECONDS,
        id="scan_and_dispatch",
        max_instances=1,
    )
    scheduler.start()
    logger.info("Scheduler started")
    yield
    scheduler.shutdown()
    logger.info("Scheduler stopped")


async def _recover_stuck():
    """Recover any task/page stuck in intermediate states."""
    async with AsyncSessionLocal() as db:
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=5)

        # Recover stuck pages → reset to pending
        result = await db.execute(
            select(TaskPage).where(
                TaskPage.status.in_(PAGE_ACTIVE_STATES),
                TaskPage.updated_at < cutoff,
            )
        )
        stuck_pages = result.scalars().all()
        for page in stuck_pages:
            logger.info(f"Recovering stuck page {page.id} (page {page.page_number})")
            page.status = "pending"
            page.error_message = "处理超时，已重置重试"
        if stuck_pages:
            await db.commit()
            logger.info(f"Recovered {len(stuck_pages)} stuck pages")

        # Recover stuck tasks → reset to processing so they can trigger summary again
        result = await db.execute(
            select(Task).where(
                Task.status.in_(["summarizing"]),
                Task.updated_at < cutoff,
            )
        )
        stuck_tasks = result.scalars().all()
        for task in stuck_tasks:
            logger.info(f"Recovering stuck summarizing task {task.id}")
            task.status = "processing"
            task.current_stage = "汇总超时，等待重新触发"
        if stuck_tasks:
            await db.commit()
            logger.info(f"Recovered {len(stuck_tasks)} stuck tasks")


def _submit_page_task(page_id: uuid.UUID):
    _executor.submit(lambda: process_page_stage(page_id))


async def scan_and_dispatch():
    """Scan for non-terminal tasks: dispatch pages + check completion."""
    async with AsyncSessionLocal() as db:
        try:
            # Find all tasks that aren't in a terminal state
            result = await db.execute(
                select(Task).where(
                    Task.status.in_(["uploaded", "processing", "summarizing"])
                )
            )
            tasks = result.scalars().all()

            if not tasks:
                return

            # Phase 0: recover pages stuck in intermediate states (>5 min)
            cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=1)
            result = await db.execute(
                select(TaskPage).where(
                    TaskPage.status.in_(PAGE_ACTIVE_STATES),
                    TaskPage.updated_at < cutoff,
                )
            )
            stuck_pages = result.scalars().all()
            for page in stuck_pages:
                logger.info(f"Recovering stuck page {page.id} (page {page.page_number}, status={page.status})")
                page.status = "pending"
                page.error_message = "处理超时，已重置重试"
            if stuck_pages:
                await db.commit()
                logger.info(f"Recovered {len(stuck_pages)} stuck pages")

            # Phase 0b: advance uploaded tasks to processing
            for task in tasks:
                if task.status == "uploaded":
                    task.status = "processing"
                    task.current_stage = "开始处理页面"
                    await db.commit()

            # Phase 1: round-robin dispatch pages across tasks for fairness
            processing_tasks = [t for t in tasks if t.status == "processing"]

            # Collect pending pages per task
            task_work_pages = {}
            for task in processing_tasks:
                result = await db.execute(
                    select(TaskPage).where(
                        TaskPage.task_id == task.id,
                        TaskPage.status.in_(["pending", "classified"]),
                    ).order_by(TaskPage.page_number)
                )
                work_pages = result.scalars().all()
                if work_pages:
                    task_work_pages[task.id] = list(work_pages)

            dispatched = 0
            dispatched_ids: list[uuid.UUID] = []

            async def _dispatch_one_page():
                nonlocal dispatched
                """Dispatch one page from the next eligible task, returns True if dispatched."""
                in_flight = await db.execute(
                    select(func.count()).where(
                        TaskPage.status.in_(("classifying", "classified"))
                    )
                )
                in_flight_count = in_flight.scalar_one()
                available = MAX_CONCURRENT_PAGES - in_flight_count
                if available <= 0:
                    return False
                for tid in list(task_work_pages.keys()):
                    pages = task_work_pages[tid]
                    if not pages:
                        continue
                    page = pages.pop(0)
                    if page.status == "pending":
                        page.status = "classifying"
                    page.error_message = None
                    await db.commit()
                    await asyncio.sleep(random.uniform(0.2, 0.5))
                    _submit_page_task(page.id)
                    dispatched += 1
                    dispatched_ids.append(page.id)
                    return True
                return False

            while await _dispatch_one_page():
                pass

            # Final in-flight count after dispatching
            final_in_flight = await db.execute(
                select(func.count()).where(
                    TaskPage.status.in_(("classifying", "classified"))
                )
            )
            in_flight_count = final_in_flight.scalar_one()

            if dispatched_ids:
                result = await db.execute(
                    select(TaskPage.id, TaskPage.page_number).where(TaskPage.id.in_(dispatched_ids))
                )
                page_numbers = [str(pn) for _, pn in result.all()]
                pages_str = ", ".join(page_numbers)
            else:
                pages_str = "none"

            logger.info(
                f"[scan] in_flight={in_flight_count}/{MAX_CONCURRENT_PAGES}, "
                f"dispatched_this_scan={dispatched} (pages: {pages_str}), "
                f"tasks_processing={len(processing_tasks)}, "
                f"tasks_summarizing={sum(1 for t in tasks if t.status == 'summarizing')}"
            )

            # Phase 2: check completion for ALL non-terminal tasks
            for task in tasks:
                await _check_task_complete(task.id, db)
        except Exception as e:
            logger.error(f"scan_and_dispatch error: {e}")


async def _check_task_complete(task_id, db):
    """Check page completion and task-level finalization."""
    try:
        task = await db.get(Task, task_id)
        if not task or task.status in ("completed", "failed"):
            return

        result = await db.execute(
            select(TaskPage).where(TaskPage.task_id == task_id)
        )
        pages = result.scalars().all()

        if not pages:
            return

        completed = sum(1 for p in pages if p.status == "completed")
        failed = sum(1 for p in pages if p.status == "failed")
        in_progress = sum(1 for p in pages if p.status in ("classifying", "classified"))

        # Update progress indicator
        if in_progress > 0:
            first_in_progress = next(
                (p.page_number for p in pages if p.status in ("classifying", "classified")), 0
            )
            task.current_stage = f"正在处理第 {first_in_progress}/{task.total_pages} 页"
            await db.commit()

        # If still processing pages, not done yet
        if in_progress > 0:
            return

        # Check if ALL pages are terminal (completed or failed)
        if completed + failed < len(pages):
            return

        # If already summarizing, check if it's been running too long
        if task.status == "summarizing":
            if task.updated_at < datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=SUMMARY_TIMEOUT_MINUTES):
                logger.warning(f"Summary timed out for task {task_id}, resetting to processing")
                task.status = "processing"
                task.current_stage = "汇总超时，等待重新生成"
                await db.commit()
            return

        # All pages done → check failure rate
        failure_rate = failed / len(pages)
        if failure_rate > 0.5:
            task.status = "failed"
            task.current_stage = f"失败页面过多 ({failed}/{task.total_pages} 页失败)"
            await db.commit()
            return

        # Trigger summary — mark status immediately to prevent re-trigger on next scan
        task.status = "summarizing"
        task.current_stage = "正在生成汇总报告"
        await db.commit()
        from app.services.summary import run_summary
        asyncio.create_task(run_summary(task_id))
    except Exception as e:
        logger.error(f"_check_task_complete error: {e}")
