import asyncio
import json
import os
import re
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.ext.asyncio import AsyncSession

from common.config import settings
from common.models import ApiResponse, BizException, SystemException
from common.models.constants import BYTES_PER_GB, VIDEO_MAX_CHUNKS
from common.models.operation_log import FeatureType
from common.utils import safe_sse_stream
from common.utils.file import extract_video_cover
from common.utils.logger import get_logger
from infra.db import User, generate_id, get_db
from service.auth import get_current_teacher
from service.operation_log import log_operation
from service.video import (
    VideoBindingParams,
    VideoCreateParams,
    VideoDeleteParams,
    VideoDetail,
    VideoOperationParams,
    VideoService,
    VideoSummary,
    VideoUpdateParams,
    ZhiyunImportCancelParams,
    ZhiyunVideoGroup,
)
from service.video.import_cancel import request_cancel

logger = get_logger(__name__)

router = APIRouter()


# ---------- 依赖注入 ----------

async def get_video_service(db: AsyncSession = Depends(get_db)) -> VideoService:
    return VideoService(db)


# ---------- API 接口 ----------

@router.get(
    "",
    summary="按 ID 查询视频",
    response_model=ApiResponse[VideoDetail],
)
async def query_video_by_id(
    id: str,
    service: VideoService = Depends(get_video_service),
    current_user: User = Depends(get_current_teacher),
) -> ApiResponse[VideoDetail]:
    """根据视频 ID 返回视频详情。"""
    video = await service.get_video_by_id(id, current_user)
    return ApiResponse.success_response(video)


@router.get(
    "/list",
    summary="查询视频列表",
    response_model=ApiResponse[list[VideoSummary]],
)
async def list_videos(
    course_id: str | None = None,
    resource_id: str | None = None,
    service: VideoService = Depends(get_video_service),
    current_user: User = Depends(get_current_teacher),
) -> ApiResponse[list[VideoSummary]]:
    """返回当前登录用户的视频列表摘要，可按绑定的课程/资源（教案版本）过滤。"""
    videos = await service.list_videos(current_user, course_id=course_id, resource_id=resource_id)
    return ApiResponse.success_response(videos)


@router.post(
    "/operation",
    summary="执行视频操作",
    response_model=ApiResponse[str | None],
)
async def operate_video(
    params: VideoOperationParams,
    service: VideoService = Depends(get_video_service),
    current_user: User = Depends(get_current_teacher),
) -> ApiResponse[str | None]:
    """对视频执行增删改等管理操作，具体行为由 operation 字段决定。"""
    match params:
        case VideoCreateParams():
            id = await service.create_video(params, current_user)
            return ApiResponse.success_response(id)
        case VideoUpdateParams():
            await service.update_video(params, current_user)
            return ApiResponse.success_response(None)
        case VideoDeleteParams():
            await service.delete_video(params, current_user)
            return ApiResponse.success_response(None)


@router.post(
    "/binding",
    summary="绑定或取绑视频",
    response_model=ApiResponse[None],
)
async def bind_video(
    params: VideoBindingParams,
    service: VideoService = Depends(get_video_service),
    current_user: User = Depends(get_current_teacher),
) -> ApiResponse[None]:
    """为视频绑定课程/教案版本，或执行取绑。"""
    await service.bind_video(params, current_user)
    return ApiResponse.success_response(None)


@router.get(
    "/analyze",
    summary="触发视频分析",
    response_model=ApiResponse[None],
)
async def analyze_video(
    id: str,
    mode: str = "cloud",
    service: VideoService = Depends(get_video_service),
    current_user: User = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[None]:
    """根据视频 ID 触发视频分析流程。

    mode="cloud"（默认）走超星链路；mode="local" 走本地自建模型分析链路。
    """
    analyze_mode = "local" if mode == "local" else "cloud"
    source = await service.get_video_source(id, current_user)
    await log_operation(
        db,
        user_id=current_user.id,
        feature_type=FeatureType.VIDEO_ANALYSIS,
        feature_key=source,
        action="analyze",
        extra={"video_id": id, "mode": analyze_mode},
    )
    await service.analyze_video(id, current_user, mode=analyze_mode)
    return ApiResponse.success_response()


@router.get(
    "/export",
    summary="导出视频分析报告",
)
async def export_video_analysis_report(
    id: str,
    service: VideoService = Depends(get_video_service),
    current_user: User = Depends(get_current_teacher),
) -> StreamingResponse:
    """根据视频 ID 导出视频分析报告的 Word 文档。"""
    filename, docx_bytes = await service.export_analysis_report(id, current_user)
    encoded_name = quote(filename)
    return StreamingResponse(
        iter([docx_bytes]),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}"},
    )


@router.get(
    "/zhiyun/import",
    summary="导入智云课堂视频",
)
async def import_zhiyun_video(
    course_id: str,
    sub_id: str,
    import_id: str | None = None,
    service: VideoService = Depends(get_video_service),
    current_user: User = Depends(get_current_teacher),
) -> EventSourceResponse:
    """导入智云课堂视频，流式返回视频信息和导入进度（需列表返回的 course_id + sub_id）。

    import_id：客户端生成的本次导入标识，用于配合 /zhiyun/import/cancel 中途取消。
    """
    stream = service.import_zhiyun_video(course_id, sub_id, current_user, import_id)
    return EventSourceResponse(safe_sse_stream(stream))


@router.post(
    "/zhiyun/import/cancel",
    summary="取消导入智云课堂视频",
    response_model=ApiResponse[None],
)
async def cancel_import_zhiyun_video(
    params: ZhiyunImportCancelParams,
    current_user: User = Depends(get_current_teacher),
) -> ApiResponse[None]:
    """取消正在进行的智云课堂视频导入：写入取消标记，导入侧在下个分片处停止并清理。"""
    if not request_cancel(params.import_id):
        raise BizException("无效的导入任务标识")
    return ApiResponse.success_response(None)


@router.get(
    "/zhiyun/list",
    summary="查询智云课堂课程列表",
    response_model=ApiResponse[list[ZhiyunVideoGroup]],
)
async def list_zhiyun_videos(
    search_begin_date: str,
    search_end_date: str,
    service: VideoService = Depends(get_video_service),
    current_user: User = Depends(get_current_teacher),
) -> ApiResponse[list[ZhiyunVideoGroup]]:
    """查询智云课堂视频列表，按课程分组，仅支持时间范围筛选。"""
    rows = await service.list_zhiyun_videos(
        search_begin_date,
        search_end_date,
        current_user,
    )
    return ApiResponse.success_response(rows)


# ---------- 视频上传 ----------
#
# 分片上传任务的状态以「文件系统」为准，而不是进程内字典：
#   uploads/videos/<upload_id>/meta.json   —— 任务元数据（总分片数、已收大小、归属用户）
#   uploads/videos/<upload_id>/chunk_<i>   —— 各分片
# 这样可跨进程（多 worker / 多副本）共享、并在进程重启后依旧有效，
# 避免「上传任务不存在或已过期」误报（旧实现把任务存在单进程内存里，换 worker 或重启即丢失）。

# upload_id 仅允许数字/字母（generate_id 产出雪花数字串），用于过滤非法值并防止路径穿越
_UPLOAD_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_UPLOAD_META_FILE = "meta.json"


def _video_upload_root() -> Path:
    return Path(settings.UPLOAD_DIR) / "videos"


def _resolve_upload_dir(upload_id: str) -> Path | None:
    """由 upload_id 推出分片目录；非法 id 返回 None（防路径穿越）。"""
    if not upload_id or not _UPLOAD_ID_RE.match(upload_id):
        return None
    root = _video_upload_root().resolve()
    upload_dir = (root / upload_id).resolve()
    if upload_dir.parent != root:
        return None
    return upload_dir


def _load_upload_task(upload_id: str) -> tuple[Path, dict] | None:
    """读取有效的上传任务（目录 + meta）；不存在/损坏返回 None。"""
    upload_dir = _resolve_upload_dir(upload_id)
    if upload_dir is None:
        return None
    meta_path = upload_dir / _UPLOAD_META_FILE
    if not meta_path.exists():
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
    if not isinstance(meta, dict) or "total_chunks" not in meta:
        return None
    return upload_dir, meta


def _write_upload_meta(upload_dir: Path, meta: dict) -> None:
    (upload_dir / _UPLOAD_META_FILE).write_text(
        json.dumps(meta, ensure_ascii=False), encoding="utf-8"
    )


@router.post(
    "/init",
    summary="初始化视频分片上传",
    response_model=ApiResponse[str],
)
async def upload_video_init(
    chunks: int = Form(...),
    current_user: User = Depends(get_current_teacher),
) -> ApiResponse[str]:
    """创建视频分片上传任务并返回 upload_id（任务状态落盘）。"""
    if chunks < 1 or chunks > VIDEO_MAX_CHUNKS:
        logger.warning(f"[video.py] 分片数非法: {chunks}")
        raise BizException(f"分片数必须在 1～{VIDEO_MAX_CHUNKS} 之间")

    upload_id = generate_id()
    upload_dir = _video_upload_root() / upload_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    _write_upload_meta(upload_dir, {
        "total_chunks": chunks,
        "received_chunks": 0,
        "received_size": 0,
        "owner_id": str(current_user.id),
    })
    return ApiResponse.success_response(upload_id)


@router.post(
    "/upload",
    summary="上传视频分片",
    response_model=ApiResponse[None],
)
async def upload_video_chunk(
    upload_id: str = Form(...),
    index: int = Form(...),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_teacher),
) -> ApiResponse[None]:
    """上传单个视频分片，要求按顺序上传并通过大小校验。"""
    loaded = _load_upload_task(upload_id)
    if loaded is None:
        logger.warning(f"[video.py] 上传任务不存在: {upload_id}")
        raise BizException(f"上传任务不存在或已过期: {upload_id}")
    upload_dir, meta = loaded

    total_chunks = int(meta.get("total_chunks", 0))
    received_chunks = int(meta.get("received_chunks", 0))
    received_size = int(meta.get("received_size", 0))

    chunk_path = upload_dir / f"chunk_{index}"

    # 幂等：重试已落盘的分片直接成功，避免网络重传被误判为「顺序错误」
    if index < received_chunks and chunk_path.exists():
        return ApiResponse.success_response()

    if received_chunks >= total_chunks:
        logger.warning(f"[video.py] 分片已传齐: {upload_id}")
        raise BizException(f"分片已传齐: {upload_id}")

    if index != received_chunks:
        logger.warning(f"[video.py] 分片顺序错误: upload_id={upload_id}, 期望={received_chunks}, 收到={index}")
        raise BizException(f"分片顺序错误: 期望索引 {received_chunks}，收到 {index}")

    content = await file.read()

    # 校验分片大小
    if len(content) > settings.VIDEO_MAX_SIZE:
        logger.warning(f"[video.py] 分片大小超过限制: {len(content)} > {settings.VIDEO_MAX_SIZE}")
        raise BizException(f"分片大小超过限制: {len(content)}，不超过 {settings.VIDEO_MAX_SIZE // BYTES_PER_GB}GB")

    # 校验视频总大小
    new_total = received_size + len(content)
    if new_total > settings.VIDEO_MAX_SIZE:
        logger.warning(f"[video.py] 视频总大小超过限制: {new_total} > {settings.VIDEO_MAX_SIZE}")
        raise BizException(f"视频总大小超过限制: {new_total}，不超过 {settings.VIDEO_MAX_SIZE // BYTES_PER_GB}GB")

    # 落盘卸载到线程：大分片同步写盘会阻塞事件循环，导致并发上传/页面接口卡顿
    # （尤其有视频分析进行、单进程更吃紧时）。
    await asyncio.to_thread(chunk_path.write_bytes, content)

    meta["received_chunks"] = received_chunks + 1
    meta["received_size"] = new_total
    await asyncio.to_thread(_write_upload_meta, upload_dir, meta)

    return ApiResponse.success_response()


def _merge_chunks_and_extract_cover(
    upload_dir: Path, merged_path: Path, total_chunks: int
) -> str:
    """合并分片为单文件并提取封面，返回封面路径。

    纯阻塞 I/O（大文件读写 + ffmpeg 子进程），由调用方用 asyncio.to_thread 卸载，
    避免在异步路由里阻塞事件循环（合并数 GB 视频时尤为明显）。
    """
    with open(merged_path, "wb") as out:
        for i in range(total_chunks):
            chunk_path = upload_dir / f"chunk_{i}"
            if not chunk_path.exists():
                logger.error(f"[video.py] 分片文件缺失: chunk={i}")
                raise SystemException(f"分片文件缺失: chunk_{i}")
            out.write(chunk_path.read_bytes())
            os.remove(chunk_path)
    return extract_video_cover(str(merged_path))


@router.post(
    "/finish",
    summary="完成视频上传",
    response_model=ApiResponse[dict[str, str]],
)
async def upload_video_finish(
    upload_id: str = Form(...),
    current_user: User = Depends(get_current_teacher),
) -> ApiResponse[dict[str, str]]:
    """合并分片、提取封面并返回视频路径和封面路径。"""
    loaded = _load_upload_task(upload_id)
    if loaded is None:
        logger.warning(f"[video.py] 上传任务不存在: {upload_id}")
        raise BizException(f"上传任务不存在或已过期: {upload_id}")
    upload_dir, meta = loaded

    total_chunks = int(meta.get("total_chunks", 0))
    received_chunks = int(meta.get("received_chunks", 0))
    if received_chunks != total_chunks:
        logger.warning(
            f"[video.py] 分片未传齐: upload_id={upload_id}, "
            f"需要={total_chunks}, 已收到={received_chunks}"
        )
        raise BizException(f"分片未传齐: 需要 {total_chunks} 片，已收到 {received_chunks} 片")

    merged_path = upload_dir / f"{generate_id()}.mp4"

    try:
        # 合并 + 封面提取是纯阻塞 I/O，卸载到线程，避免阻塞事件循环（拖慢其它上传/接口）
        cover_path = await asyncio.to_thread(
            _merge_chunks_and_extract_cover, upload_dir, merged_path, total_chunks
        )
    except Exception as e:
        logger.error(f"[video.py] 合并/封面提取失败: upload_id={upload_id}, error={e}")
        if merged_path.exists():
            os.remove(merged_path)
        raise SystemException(f"合并文件失败: {e}")
    finally:
        # 合并完成后任务元数据不再需要；分片已在循环中删除，保留目录存放合并文件与封面
        try:
            (upload_dir / _UPLOAD_META_FILE).unlink(missing_ok=True)
        except OSError as cleanup_err:
            logger.warning(f"[video.py] 清理 meta 失败: upload_id={upload_id}, error={cleanup_err}")

    return ApiResponse.success_response({
        "path": str(merged_path),
        "cover_path": cover_path,
    })
