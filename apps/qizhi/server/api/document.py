"""文档分析 API 路由。"""

import asyncio
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from common.config import settings
from common.models import BizException
from common.models.operation_log import FeatureType
from common.utils import safe_sse_stream
from common.utils.logger import get_logger
from common.utils.sse import SseEventEnum, SseResponse, build_sse_response
from infra.db import User, DocumentAnalysis, generate_id, get_db
from service.auth import get_current_user
from service.document.analyzer import analyze_document
from service.operation_log import log_operation

logger = get_logger(__name__)

router = APIRouter()

_ALLOWED_EXTENSIONS = {"docx", "pptx"}
_MAX_FILE_SIZE = settings.UPLOAD_MAX_SIZE  # 100 MB


def _doc_upload_dir() -> Path:
    """文档上传目录。"""
    p = Path(settings.UPLOAD_DIR) / "documents"
    p.mkdir(parents=True, exist_ok=True)
    return p


@router.post(
    "/analyze",
    summary="上传并分析教学文档",
)
async def analyze_doc(
    file: UploadFile = File(...),
    course_name: str = Form(default=""),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EventSourceResponse:
    """上传 .docx 或 .pptx 文件并进行 LLM 多维度教学分析。

    返回 SSE 流：
    - loading 事件：进度更新
    - end 事件：最终分析结果
    - error 事件：错误信息
    """
    # 校验文件类型
    original_name = file.filename or "unknown"
    ext = original_name.rsplit(".", 1)[-1].lower() if "." in original_name else ""
    if ext not in _ALLOWED_EXTENSIONS:
        raise BizException(f"不支持的文件类型：.{ext}，仅支持 .docx 和 .pptx")

    # 读取文件内容
    content = await file.read()
    if len(content) > _MAX_FILE_SIZE:
        raise BizException(f"文件大小超过限制（最大 {_MAX_FILE_SIZE // (1024 * 1024)} MB）")
    if not content:
        raise BizException("上传文件为空")

    # 保存到磁盘
    file_id = generate_id()
    save_path = _doc_upload_dir() / f"{file_id}.{ext}"
    await asyncio.to_thread(save_path.write_bytes, content)
    logger.info("[doc-api] 文件已保存：%s (%d bytes)", save_path, len(content))

    # 记录操作日志
    feature_type = FeatureType.PPT_ANALYSIS if ext == "pptx" else FeatureType.TEXT_ANALYSIS
    await log_operation(
        db,
        user_id=current_user.id,
        feature_type=feature_type,
        action="analyze",
        extra={"file_name": original_name, "file_type": ext},
    )

    # 返回 SSE 流
    stream = _analysis_stream(str(save_path), ext, original_name)
    return EventSourceResponse(safe_sse_stream(stream))


async def _analysis_stream(
    file_path: str,
    file_type: str,
    original_name: str,
) -> AsyncIterator[SseResponse]:
    """生成 SSE 流：进度事件 + 最终结果。"""
    loop = asyncio.get_running_loop()

    # 用 asyncio.Queue 桥接同步 progress_callback 与异步 SSE
    progress_queue: asyncio.Queue[dict | None] = asyncio.Queue()

    def progress_callback(current: int, total: int, message: str) -> None:
        # 从线程池线程安全地投递进度到事件循环
        loop.call_soon_threadsafe(
            progress_queue.put_nowait,
            {"current": current, "total": total, "message": message},
        )

    yield build_sse_response(SseEventEnum.LOADING, {
        "message": f"开始分析文档：{original_name}",
        "progress": 0,
    })

    # 在线程池中运行同步分析
    analysis_task = loop.run_in_executor(
        None,
        lambda: analyze_document(file_path, file_type, progress_callback=progress_callback),
    )

    # 边等结果边读进度
    while not analysis_task.done():
        try:
            progress = await asyncio.wait_for(
                progress_queue.get(),
                timeout=0.5,
            )
            if progress:
                yield build_sse_response(SseEventEnum.LOADING, {
                    "message": progress["message"],
                    "progress": progress["current"],
                })
        except asyncio.TimeoutError:
            continue

    # 获取最终结果（或抛出异常）
    result = analysis_task.result()

    # 排空剩余进度消息
    while not progress_queue.empty():
        try:
            progress = progress_queue.get_nowait()
            if progress:
                yield build_sse_response(SseEventEnum.LOADING, {
                    "message": progress["message"],
                    "progress": progress["current"],
                })
        except asyncio.QueueEmpty:
            break

    # 发送最终结果
    yield build_sse_response(SseEventEnum.END, result.model_dump())

    # 清理临时文件
    try:
        await asyncio.to_thread(os.remove, file_path)
    except OSError:
        logger.warning("[doc-api] 清理临时文件失败：%s", file_path)


# ---------------------------------------------------------------------------
# 文档分析结果持久化 API
# ---------------------------------------------------------------------------


class SaveResultRequest(BaseModel):
    result: dict[str, Any]


@router.post("/save-result", summary="保存文档分析结果")
async def save_result(
    body: SaveResultRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    r = body.result
    record = DocumentAnalysis(
        id=generate_id(),
        user_id=current_user.id,
        file_name=r.get("file_name", "unknown"),
        file_type=r.get("file_type", ""),
        overall_score=r.get("overall_score", 0),
        analysis_result=r,
    )
    db.add(record)
    await db.commit()
    return {"id": record.id}


@router.get("/history", summary="获取文档分析历史列表")
async def list_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    stmt = (
        select(DocumentAnalysis)
        .where(DocumentAnalysis.user_id == current_user.id)
        .order_by(desc(DocumentAnalysis.create_time))
        .limit(50)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [
        {
            "id": row.id,
            "file_name": row.file_name,
            "file_type": row.file_type,
            "overall_score": row.overall_score,
            "create_time": row.create_time.isoformat() if row.create_time else "",
        }
        for row in rows
    ]


@router.get("/history/{record_id}", summary="获取单条文档分析详情")
async def get_history_detail(
    record_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    stmt = select(DocumentAnalysis).where(
        DocumentAnalysis.id == record_id,
        DocumentAnalysis.user_id == current_user.id,
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if not row:
        raise BizException("记录不存在")
    return row.analysis_result


@router.delete("/history/{record_id}", summary="删除文档分析记录")
async def delete_history(
    record_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    stmt = select(DocumentAnalysis).where(
        DocumentAnalysis.id == record_id,
        DocumentAnalysis.user_id == current_user.id,
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if not row:
        raise BizException("记录不存在")
    await db.delete(row)
    await db.commit()
    return {"message": "已删除"}
