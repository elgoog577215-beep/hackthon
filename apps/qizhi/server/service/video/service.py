import json
import os
import random
import time
import base64
import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from hashlib import md5
from pathlib import Path
from typing import Any, AsyncIterator
from zoneinfo import ZoneInfo

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from common.config import settings
from common.models import BizException, SystemException
from common.models.constants import (
    CHAOXING_TRANSCRIPT_URL,
    CHAOXING_UPLOAD_URL,
    NONCE_MAX,
    VIDEO_DOWNLOAD_CHUNK_SIZE,
    VIDEO_DOWNLOAD_TIMEOUT,
    ZHIYUN_COURSE_DETAIL_URL,
    ZHIYUN_COURSE_LIST_URL,
    ZHIYUN_REQTOKEN_URL,
)
from common.utils import HTTPMethodEnum, SseEventEnum, build_sse_response, http_request, run_in_background, stream_bytes
from common.utils.file import extract_video_cover
from infra.db import User, Video, generate_id
from service.video.import_cancel import clear_cancel, is_cancelled
from service.video.converters import video_to_detail, video_to_summary
from service.video.models import (
    VideoBindingParams,
    VideoCreateParams,
    VideoDeleteParams,
    VideoDetail,
    VideoStatusEnum,
    VideoSummary,
    VideoUpdateParams,
    ZhiyunVideoGroup,
    ZhiyunVideoItem,
)
from common.utils.logger import get_logger

logger = get_logger(__name__)


class VideoService:
    """
    视频服务
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ---------- 公共方法 ----------

    async def get_video_by_id(self, id: str, current_user: User) -> VideoDetail | None:
        """根据 id 查询视频详情。"""
        db_video = (await self.db.execute(
            select(Video)
            .where(
                Video.id == id,
                Video.user_id == current_user.id,
            )
        )).scalars().first()
        if not db_video:
            return None

        return video_to_detail(db_video)

    async def list_videos(
        self,
        current_user: User,
        course_id: str | None = None,
        resource_id: str | None = None,
    ) -> list[VideoSummary]:
        """查询视频列表，可按绑定的课程/资源（教案版本）过滤。"""
        videos = (await self.db.execute(
            select(Video)
            .where(
                Video.user_id == current_user.id,
                Video.related_course_id == course_id if course_id else True,
                Video.related_resource_id == resource_id if resource_id else True,
            )
            .order_by(Video.create_time.desc())
        )).scalars().all()

        summaries = [video_to_summary(v) for v in videos]
        # 本地分析「分析中」的视频：附上"按时长+排队+并发"算出的预估剩余时间（云端不估）
        from service.video.eta import compute_local_eta_map
        eta_map = await compute_local_eta_map(self.db)
        for s in summaries:
            if s is not None and s.id in eta_map:
                s.estimated_seconds = eta_map[s.id]
        return summaries

    async def create_video(self, params: VideoCreateParams, current_user: User) -> str:
        """创建视频记录"""
        db_video = Video(
            name=params.name,
            path=params.path,
            cover=params.cover,
            status=VideoStatusEnum.UNSTARTED,
            source="upload",
            user_id=current_user.id,
        )
        self.db.add(db_video)
        await self.db.commit()
        return db_video.id

    async def update_video(self, params: VideoUpdateParams, current_user: User) -> None:
        """更新视频"""
        db_video = await self._get_video_or_raise(params.id, current_user.id)
        if params.name is not None:
            db_video.name = params.name
            await self.db.commit()

    async def delete_video(self, params: VideoDeleteParams, current_user: User) -> None:
        """删除视频"""
        db_video = await self._get_video_or_raise(params.id, current_user.id)
        # 同时删除该视频的分析任务行：避免删后仍被轮询调度（pending）或残留 failed 任务。
        # 若本地分析正在跑，会因视频文件被删、在下一个检查点自行中止（见 run_local_analysis）。
        from infra.db.models.task_queue import TaskQueue
        await self.db.execute(delete(TaskQueue).where(TaskQueue.business_id == params.id))
        try:
            os.remove(db_video.path)
        except OSError:
            pass  # 文件可能已不存在（如导入中途清理）；不阻断删除
        await self.db.delete(db_video)
        await self.db.commit()

    async def bind_video(self, params: VideoBindingParams, current_user: User) -> None:
        """绑定/解绑视频到课程与教案版本（软绑定，均为可空外键）。"""
        db_video = await self._get_video_or_raise(params.id, current_user.id)

        if params.unbind:
            db_video.related_course_id = None
            db_video.related_resource_id = None
            await self.db.commit()
            return

        if params.related_resource_id:
            from infra.db import Resource
            db_resource = (await self.db.execute(
                select(Resource).where(
                    Resource.id == params.related_resource_id,
                    Resource.creator_id == current_user.id,
                )
            )).scalars().first()
            if not db_resource:
                raise BizException(f"关联资源不存在或无权限: {params.related_resource_id}")
            db_video.related_resource_id = db_resource.id
            # 未显式指定课程时，课程归属与所绑资源强同步（资源无课程则一并置空），
            # 避免改绑后残留旧课程导致两个过滤维度互相矛盾
            if not params.related_course_id:
                db_video.related_course_id = db_resource.related_course_id

        if params.related_course_id:
            from infra.db import Course
            db_course = (await self.db.execute(
                select(Course).where(Course.id == params.related_course_id)
            )).scalars().first()
            if not db_course:
                raise BizException(f"关联课程不存在: {params.related_course_id}")
            db_video.related_course_id = db_course.id

        await self.db.commit()

    async def get_video_source(self, id: str, current_user: User) -> str:
        """读取视频来源（upload / zhiyun），用于驾驶舱埋点；不存在则按 upload 处理。"""
        source = (await self.db.execute(
            select(Video.source).where(Video.id == id).where(Video.user_id == current_user.id)
        )).scalar()
        return source or "upload"

    async def export_analysis_report(self, id: str, current_user: User) -> tuple[str, bytes]:
        """导出视频分析报告为 Word 文档。"""
        db_video = await self._get_video_or_raise(id, current_user.id)
        if db_video.status != VideoStatusEnum.SUCCESS:
            raise BizException("视频分析尚未完成，无法导出报告")

        analysis_result = db_video.analysis_result or {}
        video_name = db_video.name or "未知视频"

        from service.video.export import generate_video_analysis_report
        docx_bytes = await generate_video_analysis_report(video_name, analysis_result)

        safe_name = video_name.replace(" ", "_")
        for ch in r'\/:*?"<>|':
            safe_name = safe_name.replace(ch, "_")
        if len(safe_name) > 80:
            safe_name = safe_name[:77] + "..."

        filename = f"{safe_name}_分析报告.docx"
        return filename, docx_bytes

    async def analyze_video(self, id: str, current_user: User, mode: str = "cloud") -> None:
        """分析视频。

        mode="cloud"（默认）：上传超星后创建异步分析任务（原链路）。
        mode="local"：不依赖超星，直接创建本地分析任务（自建 vLLM 跑 POC 流水线）。
        """
        db_video = await self._get_video_or_raise(id, current_user.id)
        video_path = db_video.path

        # ---- 本地分析：标记 WAITING 后直接落一个本地分析任务（无超星上传/等待）----
        if mode == "local":
            db_video.status = VideoStatusEnum.WAITING
            db_video.analysis_start_time = datetime.now(ZoneInfo("Asia/Shanghai"))
            await self.db.commit()

            from infra.task_queue.framework import AsyncTaskFramework
            from service.video.analysis_task import LocalVideoAnalysisHandler

            framework = AsyncTaskFramework(self.db)
            framework.register(LocalVideoAnalysisHandler())
            await framework.create_task(
                task_type=LocalVideoAnalysisHandler.task_type,
                business_id=id,
                scheduled_at=datetime.now(ZoneInfo("Asia/Shanghai")),
            )
            return

        # 先标记为分析中并记录开始时间，后续 HTTP 请求在后台异步执行
        db_video.status = VideoStatusEnum.WAITING
        db_video.analysis_start_time = datetime.now(ZoneInfo("Asia/Shanghai"))
        await self.db.commit()

        async def _task() -> None:
            from infra.db.database import AsyncSessionLocal
            from infra.task_queue.framework import AsyncTaskFramework
            from service.video.analysis_task import VideoAnalysisHandler

            async with AsyncSessionLocal() as db:
                try:
                    url = CHAOXING_UPLOAD_URL
                    params = {
                        "appid": settings.CHAOXING_APP_ID,
                        "clientip": settings.CHAOXING_CLIENT_IP,
                        "nonce": str(random.randint(1, NONCE_MAX)),
                        "puid": settings.CHAOXING_PUID,
                        "timestamp": str(int(time.time() * 1000)),
                    }
                    params["signature"] = _build_chaoxing_signature(params)

                    with open(video_path, "rb") as f:
                        files = {
                            "file": (os.path.basename(video_path), f, "video/mp4"),
                        }
                        response = await http_request(HTTPMethodEnum.POST, url, params=params, files=files, timeout=3600)
                    object_id = response["objectId"]

                    url = CHAOXING_TRANSCRIPT_URL
                    params = {
                        "objectId": object_id,
                        "fid": settings.CHAOXING_FID,
                    }
                    await http_request(HTTPMethodEnum.GET, url, params=params)

                    video = (await db.execute(select(Video).where(Video.id == id))).scalars().first()
                    if video:
                        video.analysis_id = object_id
                        await db.commit()

                    # 创建异步分析任务（1 小时后开始轮询）
                    framework = AsyncTaskFramework(db)
                    framework.register(VideoAnalysisHandler())
                    await framework.create_task(
                        task_type=VideoAnalysisHandler.task_type,
                        business_id=id,
                        scheduled_at=datetime.now(ZoneInfo("Asia/Shanghai")) + timedelta(hours=1),
                    )
                except Exception:
                    logger.exception("视频上传后台任务失败: %s", id)
                    await db.rollback()
                    video = (await db.execute(select(Video).where(Video.id == id))).scalars().first()
                    if video:
                        video.status = VideoStatusEnum.FAILED
                        await db.commit()

        run_in_background(_task(), name=f"analyze_video:{id}")

    async def import_zhiyun_video(
        self,
        course_id: str,
        sub_id: str,
        current_user: User,
        import_id: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """查询智云课堂课程详情并导入。

        import_id：客户端生成的本次导入标识，用户点击「取消」时据此写取消标记，
        下载循环每个分片轮询一次；命中则停止下载、删除半成品文件、不落库。
        """
        # 阶段 A：调用智云接口获取回放地址
        token = await self._fetch_zhiyun_reqtoken()
        parameter = {
            "appid": settings.ZHIYUN_APP_ID,
            "courseId": str(course_id),
            "subId": str(sub_id),
        }
        code, signature = self._build_zhiyun_code_signature(token, parameter)
        resp = await http_request(
            HTTPMethodEnum.POST,
            ZHIYUN_COURSE_DETAIL_URL,
            data={"code": code, "signature": signature},
        )
        if not isinstance(resp, dict):
            logger.error(f"[service.py] 智云课堂章节详情返回格式异常")
            raise SystemException("智云课堂章节详情返回格式异常")
        if resp.get("result") != "success":
            logger.error(f"[service.py] 获取智云课堂章节详情失败: {resp.get('info')}")
            raise SystemException(f"获取智云课堂章节详情失败: {resp.get('info')}")

        data_block = resp.get("data")
        detail: dict[str, Any] = {}
        if isinstance(data_block, dict):
            ent = data_block.get("entity")
            if isinstance(ent, dict):
                detail = ent

        video_play_url = detail.get("url")
        if not isinstance(video_play_url, str) or not video_play_url:
            logger.error(f"[service.py] 智云课堂未返回教师流回放地址（url）")
            raise SystemException("智云课堂未返回教师流回放地址（url）")

        # 阶段 B：创建本地落盘路径与数据库视频记录
        upload_dir = Path(settings.UPLOAD_DIR) / "videos"
        upload_dir.mkdir(parents=True, exist_ok=True)
        local_path = upload_dir / f"{generate_id()}.mp4"

        # 阶段 C：流式下载，持续回传 loading 进度；期间轮询取消标记
        received = 0
        cancelled = False
        committed = False
        try:
            with open(local_path, "wb") as f:
                async for chunk, total in stream_bytes(
                    HTTPMethodEnum.GET,
                    video_play_url,
                    timeout=VIDEO_DOWNLOAD_TIMEOUT,
                    chunk_size=VIDEO_DOWNLOAD_CHUNK_SIZE,
                ):
                    # 用户点击「取消」：停止下载、不落库（半成品文件在 finally 清理）
                    if is_cancelled(import_id):
                        cancelled = True
                        logger.info(f"[service.py] 智云课堂视频导入已取消: import_id={import_id}")
                        break
                    if total and total > settings.VIDEO_MAX_SIZE:
                        logger.warning(f"[service.py] 视频超过允许大小限制: {total} bytes")
                        raise BizException(f"视频超过允许大小限制: {total} bytes")
                    received += len(chunk)
                    if received > settings.VIDEO_MAX_SIZE:
                        logger.warning(f"[service.py] 视频超过允许大小限制: {received} bytes")
                        raise BizException(f"视频超过允许大小限制: {received} bytes")
                    f.write(chunk)
                    progress = round(received * 100 / total, 2) if total else None
                    yield build_sse_response(
                        SseEventEnum.LOADING,
                        {
                            "progress": progress,
                        },
                    )

            if cancelled:
                # 通知仍在监听的客户端（前端通常已 abort，此事件会被忽略）
                yield build_sse_response(SseEventEnum.ERROR, {"error": "已取消导入"})
                return

            # 阶段 D：下载完成后提取封面、创建记录并落库，立即发 end
            cover = extract_video_cover(str(local_path))
            db_video = Video(
                name=(detail.get("courseName") or "") + " " + (detail.get("subTitle") or ""),
                path=str(local_path),
                cover=cover,
                status=VideoStatusEnum.UNSTARTED,
                source="zhiyun",
                user_id=current_user.id,
            )
            self.db.add(db_video)
            await self.db.commit()
            committed = True
            yield build_sse_response(SseEventEnum.END, {"id": db_video.id})
        finally:
            # 清理取消标记；任何未成功落库（取消/异常/客户端断连）都删除半成品文件
            clear_cancel(import_id)
            if not committed:
                try:
                    if local_path.exists():
                        local_path.unlink()
                except OSError as e:
                    logger.warning(f"[service.py] 清理半成品视频文件失败: {local_path}, err={e}")

    async def list_zhiyun_videos(
        self,
        search_begin_date: str,
        search_end_date: str,
        current_user: User,
    ) -> list[ZhiyunVideoGroup]:
        """查询智云课堂课程列表，按课程分组，课程内按上课时间倒序。"""
        token = await self._fetch_zhiyun_reqtoken()
        parameter = {
            "appid": settings.ZHIYUN_APP_ID,
            "xgh": str(current_user.zju_id or ""),
            "sdate": search_begin_date,
            "edate": search_end_date,
        }
        code, signature = self._build_zhiyun_code_signature(token, parameter)
        resp = await http_request(
            HTTPMethodEnum.POST,
            ZHIYUN_COURSE_LIST_URL,
            data={"code": code, "signature": signature},
        )
        if not isinstance(resp, dict):
            logger.error(f"[service.py] 智云课堂课程列表返回格式异常")
            raise SystemException("智云课堂课程列表返回格式异常")
        if resp.get("result") != "success":
            logger.error(f"[service.py] 获取智云课堂课程列表失败: {resp.get('info')}")
            raise SystemException(f"获取智云课堂课程列表失败: {resp.get('info')}")

        data_block = resp.get("data")
        rows: list[dict[str, Any]] = []
        if isinstance(data_block, dict):
            raw_list = data_block.get("list")
            entity = data_block.get("entity")
            if isinstance(raw_list, list):
                rows = [item for item in raw_list if isinstance(item, dict)]
            elif isinstance(entity, dict):
                rows = [entity]

        rows = [
            row
            for row in rows
            if row.get("courseId") is not None and row.get("subId") is not None
        ]

        # 按 course_name 分组，保持首次出现的顺序
        from collections import OrderedDict
        groups: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
        for row in rows:
            course_name = str(row.get("courseName") or "")
            if course_name not in groups:
                groups[course_name] = []
            groups[course_name].append(row)

        # 每个课程内部按 class_begin 倒序
        result: list[ZhiyunVideoGroup] = []
        for course_name, items in groups.items():
            items.sort(key=lambda r: str(r.get("classBegin") or ""), reverse=True)
            result.append(ZhiyunVideoGroup(
                course_id=str(items[0].get("courseId") or ""),
                course_name=course_name,
                items=[ZhiyunVideoItem(
                    sub_id=str(item.get("subId") or ""),
                    sub_title=str(item.get("subTitle") or ""),
                    teacher_name=str(item.get("teacherName") or ""),
                    class_begin=str(item.get("classBegin") or ""),
                ) for item in items],
            ))

        return result

    # ---------- 私有方法 ----------

    async def _get_video_or_raise(self, video_id: str, user_id: str) -> Video:
        """按 ID 查询视频，不存在或无权限时抛出 SystemException。"""
        db_video = (await self.db.execute(
            select(Video)
            .where(
                Video.id == video_id,
                Video.user_id == user_id,
            )
        )).scalars().first()
        if not db_video:
            logger.error(f"[service.py] 视频不存在或无权限: {video_id}")
            raise SystemException(f"视频不存在或无权限: {video_id}")
        return db_video

    async def _fetch_zhiyun_reqtoken(self) -> str:
        """获取调试授权码。"""
        resp = await http_request(
            HTTPMethodEnum.GET,
            ZHIYUN_REQTOKEN_URL,
            params={"appid": settings.ZHIYUN_APP_ID, "appkey": settings.ZHIYUN_APP_KEY},
        )
        if not isinstance(resp, dict):
            logger.error(f"[service.py] 智云 reqtoken 接口返回异常：{resp}")
            raise SystemException(f"智云 reqtoken 接口返回异常：{resp}")

        data = resp.get("data")
        if isinstance(data, dict):
            return data.get("token")
        logger.error(f"[service.py] 智云 reqtoken 接口返回异常：{resp}")
        raise SystemException(f"智云 reqtoken 接口返回异常：{resp}")

    def _build_zhiyun_code_signature(self, token: str, parameter: dict[str, str]) -> tuple[str, str]:
        """构建智云签名"""
        payload = {"token": token, "parameter": parameter}
        json_str = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        code = base64.b64encode(json_str.encode("utf-8")).decode("ascii")
        sig = hmac.new(
            settings.ZHIYUN_SECRET.encode("utf-8"),
            code.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        signature = base64.b64encode(sig).decode("ascii")
        return code, signature


# ---------------------------------------------------------------------------
# 模块级私有函数（供后台任务与 Handler 复用）
# ---------------------------------------------------------------------------


def _build_chaoxing_signature(params: dict) -> str:
    """构建超星签名"""
    signature = ""
    for k, v in sorted(params.items(), key=lambda x: x[0]):
        signature += f"{k}#{v}#"
    signature += settings.CHAOXING_APP_SECRET
    return md5(signature.encode()).hexdigest()


def _build_chaoxing_enc(object_id: str) -> str:
    """构建超星 enc 参数"""
    day = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d")
    return md5(f"{object_id}{day}{settings.CHAOXING_ENC_KEY}".encode()).hexdigest()
