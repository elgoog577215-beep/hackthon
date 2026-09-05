"""
视频分析异步任务处理器。
"""

import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.config import settings
from common.models import BizException
from common.models.constants import CHAOXING_ANALYZE_URL, CHAOXING_TRANSCRIPT_URL
from common.utils import HTTPMethodEnum, http_request
from common.utils.logger import get_logger
from infra.db.models.task_queue import TaskQueue
from infra.db.models.video import Video
from infra.task_queue.framework import RetryableError, TaskHandler
from service.video.models import VideoStatusEnum
from service.video.service import _build_chaoxing_enc

logger = get_logger(__name__)

# 本地分析并发度：透传给 run_local_analysis 的 workers。
# 流式流水线中各段 ASR 并行 + LLM 并行，12 workers 可充分利用 6×A800。
_LOCAL_ANALYSIS_WORKERS = 12


# 超星分析数据中用到的字段
_REQUIRED_ANALYZE_FIELDS = [
    "teach_db_result",
    "teach_summary",
    "teach_knowledge",
    "teach_question",
    "teach_wh",
    "class_education_summary",
]

# 可能以 JSON 字符串返回的字段
_JSON_STRING_FIELDS = ["teach_knowledge", "teach_summary", "teach_wh", "teach_question"]


class VideoAnalysisHandler(TaskHandler):
    """
    视频分析任务处理器。

    重试策略：
    - 超星数据未就绪（RetryableError）：不限 retry_count，只更新 scheduled_at
    - 其他异常：最多重试 3 次
    """

    task_type = "video_analysis"

    async def execute(self, task: TaskQueue, db: AsyncSession) -> None:
        video_id = task.business_id
        logger.info("[analysis_task] 开始执行视频分析: video_id=%s", video_id)

        # 1. 获取视频
        result = await db.execute(select(Video).where(Video.id == video_id))
        video = result.scalars().first()
        if not video:
            logger.error("[analysis_task] 视频不存在: %s", video_id)
            raise BizException(f"视频不存在: {video_id}")

        if not video.analysis_id:
            logger.info("[analysis_task] analysis_id 尚未生成，等待: %s", video_id)
            raise RetryableError("analysis_id 尚未生成")

        # 2. 获取超星数据
        logger.info("[analysis_task] 获取超星数据: video_id=%s, analysis_id=%s", video_id, video.analysis_id)
        transcript_data = await self._fetch_transcript(video.analysis_id)
        analyze_data = await self._fetch_analyze(video.analysis_id)

        ready = self._is_data_ready(transcript_data, analyze_data)
        if not ready:
            logger.info("[analysis_task] 超星数据未就绪，reschedule: video_id=%s", video_id)
            raise RetryableError("超星数据未就绪")

        logger.info("[analysis_task] 超星数据就绪，开始分析: video_id=%s", video_id)

        # 3. 并行分析
        from service.video.analysis.orchestrator import analyze_video_parallel

        analysis_result = await analyze_video_parallel(transcript_data, analyze_data)

        # 4. 写入 Video 表（只存新结构）
        video.status = VideoStatusEnum.SUCCESS.value
        video.analysis_result = analysis_result
        await db.commit()
        logger.info("[analysis_task] 视频分析完成: video_id=%s", video_id)

    async def should_retry(self, task: TaskQueue, error: Exception) -> bool:
        if isinstance(error, RetryableError):
            # 超星数据未就绪：理论上无限重试（由 scheduled_at 控制节奏）
            # 但设一个绝对上限防止极端情况
            return True
        return task.retry_count < 3

    async def next_schedule_time(
        self,
        task: TaskQueue,
        error: Exception | None = None,
    ) -> datetime:
        return datetime.now(ZoneInfo("Asia/Shanghai")) + timedelta(minutes=10)

    # -------------------------------------------------------------------------
    # 私有：超星数据获取与就绪判断
    # -------------------------------------------------------------------------

    async def _fetch_transcript(self, analysis_id: str) -> dict | None:
        try:
            resp = await http_request(
                HTTPMethodEnum.GET,
                CHAOXING_TRANSCRIPT_URL,
                params={"objectid": analysis_id, "fid": settings.CHAOXING_FID},
            )
            if isinstance(resp, dict) and isinstance(
                data := resp.get("result"), dict
            ):
                return data
        except Exception:
            logger.exception("获取超星转写数据失败: %s", analysis_id)
        return None

    async def _fetch_analyze(self, analysis_id: str) -> dict | None:
        try:
            resp = await http_request(
                HTTPMethodEnum.GET,
                CHAOXING_ANALYZE_URL,
                params={
                    "objectId": analysis_id,
                    "enc": _build_chaoxing_enc(analysis_id),
                },
            )
            if isinstance(resp, dict) and resp.get("success") is True:
                data = resp.get("data", {})
                # 自动解析可能为 JSON 字符串的字段
                for field in _JSON_STRING_FIELDS:
                    val = data.get(field)
                    if isinstance(val, str):
                        try:
                            import json

                            data[field] = json.loads(val)
                        except Exception:
                            pass
                return data
        except Exception:
            logger.exception("获取超星分析数据失败: %s", analysis_id)
        return None

    def _is_data_ready(
        self, transcript_data: dict | None, analyze_data: dict | None
    ) -> bool:
        """
        判断超星数据是否已就绪。

        用到的字段：
        - 转写：transcript（全文）、audioDuration（总时长）
        - 分析：teach_db_result（音量/语速）、teach_summary（教学环节）、
                teach_knowledge（知识点树）、teach_question（互动问题）、
                teach_wh（五何分布）、class_education_summary（思政事件）
        """
        if not transcript_data or not analyze_data:
            return False

        # 转写必须有 transcript（非空列表）
        transcript = transcript_data.get("transcript")
        if not isinstance(transcript, list) or not transcript:
            return False

        # 分析数据核心字段必须存在且内容实质非空
        for field in _REQUIRED_ANALYZE_FIELDS:
            val = analyze_data.get(field)
            if val is None:
                return False
            if isinstance(val, list) and not val:
                return False
            if isinstance(val, dict) and not val:
                return False
            if isinstance(val, str) and not val.strip():
                return False

        return True


class LocalVideoAnalysisHandler(TaskHandler):
    """
    本地视频分析任务处理器（不依赖超星）。

    直接在本地用自建 vLLM 跑通 video-analyze POC 流水线，产出 v2 analysis_result。
    整条流水线是阻塞式的，用 asyncio.to_thread 卸载到线程，避免阻塞事件循环。
    失败不自动重试（已显式置为 failed，用户可在前端重新发起）。
    """

    task_type = "local_video_analysis"

    async def execute(self, task: TaskQueue, db: AsyncSession) -> None:
        from service.video.local_analysis.adapter import map_report_to_v2
        from service.video.local_analysis.runner import AnalysisCancelled, run_local_analysis

        video_id = task.business_id
        logger.info("[local_analysis_task] 开始执行本地视频分析: video_id=%s", video_id)

        video = (await db.execute(select(Video).where(Video.id == video_id))).scalars().first()
        if not video:
            logger.error("[local_analysis_task] 视频不存在: %s", video_id)
            raise BizException(f"视频不存在: {video_id}")

        max_secs = settings.LOCAL_ANALYSIS_MAX_SECONDS
        rng = (0.0, float(max_secs)) if max_secs and max_secs > 0 else None

        try:
            report = await asyncio.to_thread(
                run_local_analysis,
                video.path,
                range=rng,
                text_base_url=settings.LOCAL_ANALYSIS_TEXT_BASE_URL,
                asr_base_url=settings.LOCAL_ANALYSIS_ASR_BASE_URL,
                model=settings.LOCAL_ANALYSIS_MODEL,
                asr_model=settings.LOCAL_ANALYSIS_ASR_MODEL,
                api_key=settings.LOCAL_ANALYSIS_API_KEY,
                course_name=video.name or "",
                workers=_LOCAL_ANALYSIS_WORKERS,
                log=logger,
            )
            analysis_result = map_report_to_v2(report)
        except AnalysisCancelled:
            # 视频在分析过程中被删除：属正常取消，不算失败；视频/任务已被删除，无需更新
            logger.info("[local_analysis_task] 视频已删除，本地分析取消: video_id=%s", video_id)
            await db.rollback()
            return
        except Exception as exc:
            import traceback as _tb
            err_detail = f"{type(exc).__name__}: {exc}"
            err_tb = _tb.format_exc()[-500:]
            logger.exception("[local_analysis_task] 本地分析失败: video_id=%s", video_id)
            await db.rollback()
            fresh = (await db.execute(select(Video).where(Video.id == video_id))).scalars().first()
            if fresh:
                fresh.status = VideoStatusEnum.FAILED.value
                fresh.analysis_result = {"error": err_detail, "traceback": err_tb}
                await db.commit()
            raise

        # 写回结果前再确认视频仍存在：分析期间（尤其 LLM 阶段）可能已被删除，
        # 此时丢弃结果即可，避免对已删行 UPDATE 触发 StaleDataError。
        fresh = (await db.execute(select(Video).where(Video.id == video_id))).scalars().first()
        if not fresh:
            logger.info("[local_analysis_task] 视频已删除，丢弃分析结果: video_id=%s", video_id)
            return
        fresh.status = VideoStatusEnum.SUCCESS.value
        fresh.analysis_result = analysis_result
        await db.commit()
        logger.info("[local_analysis_task] 本地视频分析完成: video_id=%s", video_id)

    async def should_retry(self, task: TaskQueue, error: Exception) -> bool:
        # 本地分析失败不自动重试：已置 failed，用户可重新发起。
        return False

    async def next_schedule_time(
        self,
        task: TaskQueue,
        error: Exception | None = None,
    ) -> datetime:
        return datetime.now(ZoneInfo("Asia/Shanghai")) + timedelta(minutes=10)
