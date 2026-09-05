import asyncio
import os

from pathlib import Path
from sqlalchemy import select

from app.config import SUMMARY_BATCH_PAGE_SIZE, SUMMARY_SINGLE_PASS_MAX_PAGES
from app.database import AsyncSessionLocal
from app.models import Task, TaskPage
from app.services.classifier import (
    analyze_data_consistency,
    compact_pages_for_summary,
    generate_batch_summary,
    generate_summary_single,
    merge_batch_summaries,
)
from app.services.oss import get_data_dir, use_local_storage

from app.logger import get_logger

logger = get_logger(__name__)


async def _set_task_stage(task_id, stage: str):
    async with AsyncSessionLocal() as db:
        task = await db.get(Task, task_id)
        if task:
            task.current_stage = stage
            await db.commit()


async def _run_summary_llm(compact_pages: list[dict], task_id) -> tuple[dict | None, str | None]:
    """按页数选择单次或分批+合并汇总。"""
    if len(compact_pages) <= SUMMARY_SINGLE_PASS_MAX_PAGES:
        await _set_task_stage(task_id, "正在生成汇总报告")
        try:
            result = await asyncio.to_thread(generate_summary_single, compact_pages)
            return (result, None) if result else (None, "汇总报告生成失败")
        except Exception as e:
            return None, str(e)

    batches = [
        compact_pages[i:i + SUMMARY_BATCH_PAGE_SIZE]
        for i in range(0, len(compact_pages), SUMMARY_BATCH_PAGE_SIZE)
    ]
    logger.info(
        f"Task {task_id}: batched summary {len(compact_pages)} pages -> {len(batches)} batches"
    )
    batch_results: list[dict] = []
    for idx, batch in enumerate(batches):
        page_range = f"{batch[0]['page_number']}-{batch[-1]['page_number']}"
        await _set_task_stage(task_id, f"正在分批汇总 ({idx + 1}/{len(batches)} 批，页 {page_range})")
        try:
            result = await asyncio.to_thread(
                generate_batch_summary, batch, idx + 1, len(batches), page_range
            )
        except Exception as e:
            return None, f"第 {idx + 1}/{len(batches)} 批汇总异常: {e}"
        if not result:
            return None, f"第 {idx + 1}/{len(batches)} 批汇总失败（页 {page_range}）"
        batch_results.append(result)

    await _set_task_stage(task_id, "正在合并汇总报告")
    try:
        merged = await asyncio.to_thread(
            merge_batch_summaries, batch_results, len(compact_pages)
        )
    except Exception as e:
        return None, f"合并汇总报告异常: {e}"
    if not merged:
        return None, "合并汇总报告失败"
    return merged, None


async def run_summary(task_id):
    """Gather all page results, call LLM for final report, update task.

    DB session is only held during read/write. LLM call runs in a thread pool
    to avoid blocking the event loop.
    """
    logger.info(f"Starting summary for task {task_id}")

    # Phase 1: fetch data from DB
    async with AsyncSessionLocal() as db:
        task = await db.get(Task, task_id)
        if not task:
            return

        result = await db.execute(
            select(TaskPage).where(
                TaskPage.task_id == task_id
            ).order_by(TaskPage.page_number)
        )
        pages = result.scalars().all()

        pages_data = []
        for p in pages:
            pages_data.append({
                "page_number": p.page_number,
                "page_type": p.page_type,
                "status": p.status,
                "extracted_content": p.extracted_content,
                "check_results": p.check_results,
                "error_message": p.error_message,
            })

    compact_pages = compact_pages_for_summary(pages_data)

    # Phase 1.5: 读取所有页面数据提取信息，进行数据一致性分析
    data_analysis_result = await _analyze_task_data(task_id)

    # Phase 2: 单次或分批汇总 + 二次合并
    summary_result, error_msg = await _run_summary_llm(compact_pages, task_id)

    # Phase 2.5: 将数据分析结果融合到 check_domains 中，作为新域
    if summary_result and data_analysis_result:
        check_domains = summary_result.get("check_domains") or []
        check_domains.append(_build_data_analysis_domain(data_analysis_result))
        summary_result["check_domains"] = check_domains

    # Phase 3: write result back to DB
    async with AsyncSessionLocal() as db:
        task = await db.get(Task, task_id)
        if not task:
            return

        if summary_result:
            task.result = summary_result
            task.status = "completed"
            task.current_stage = "审查完成"
            logger.info(f"Summary completed for task {task_id}")
        else:
            task.status = "failed"
            task.current_stage = f"汇总报告生成失败: {error_msg}" if error_msg else "汇总报告生成失败"
            logger.error(f"Summary generation failed for task {task_id}: {error_msg}")

        await db.commit()


async def _analyze_task_data(task_id) -> dict | None:
    """读取某篇论文所有页面的数据提取 txt，进行数据一致性分析。"""
    try:
        if use_local_storage():
            data_dir = get_data_dir(task_id)
        else:
            # DEV 环境：数据存储在 LOCAL_IMAGE_DIR 下的 essay_data 目录
            data_dir = Path(os.environ.get("LOCAL_IMAGE_DIR", "/tmp/essay_data")) / "essay_data" / str(task_id)

        if not data_dir.exists():
            logger.info(f"No data files found for task {task_id}")
            return None

        # 读取所有 txt 文件，按页号排序
        txt_files = sorted(data_dir.glob("page_*_data.txt"))
        if not txt_files:
            logger.info(f"No data txt files found for task {task_id}")
            return None

        all_data_texts = ""
        for f in txt_files:
            content = f.read_text(encoding="utf-8")
            all_data_texts += content + "\n\n"

        if not all_data_texts.strip():
            return None

        # 调用 LLM 进行数据一致性分析
        return await asyncio.to_thread(analyze_data_consistency, all_data_texts)
    except Exception as e:
        logger.warning(f"Data analysis for task {task_id} failed: {e}")
        return None


def _build_data_analysis_domain(data: dict) -> dict:
    """将数据分析结果转换为 check_domain 格式，供导出报告使用。"""
    check_points = []

    for item in data.get("inconsistencies", []):
        check_points.append({
            "name": f"数据不一致：{item}",
            "passed": False,
            "detail": item,
        })
    for item in data.get("fabrication_suspicions", []):
        check_points.append({
            "name": f"数据造假嫌疑：{item}",
            "passed": False,
            "detail": item,
        })
    for item in data.get("data_quality_issues", []):
        check_points.append({
            "name": f"数据质量问题：{item}",
            "passed": False,
            "detail": item,
        })
    for item in data.get("statistical_concerns", []):
        check_points.append({
            "name": f"统计方法关注：{item}",
            "passed": False,
            "detail": item,
        })
    for item in data.get("citation_mismatch", []):
        check_points.append({
            "name": f"引用数据不一致：{item}",
            "passed": False,
            "detail": item,
        })

    if not check_points:
        check_points.append({
            "name": "数据一致性与质量",
            "passed": True,
            "detail": f"总体评估：{data.get('overall_assessment', '未发现明显问题')}。{data.get('summary', '')}",
        })

    return {
        "domain": "数据一致性与质量",
        "check_points": check_points,
    }
