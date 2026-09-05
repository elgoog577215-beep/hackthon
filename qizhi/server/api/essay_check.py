from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.ext.asyncio import AsyncSession
from urllib.parse import quote

from common.models import ApiResponse, BizException
from common.models.operation_log import FeatureType
from common.utils.http import get_client_ip
from infra.db import User, get_db
from service.audit import AuditActorType, log_audit
from service.auth import get_current_user
from service.essay_check import EssayCheckService, EssayTaskItem
from service.essay_check.models import EssayOverview, ReportExportRequest
from service.operation_log import log_operation
from common.utils.logger import get_logger

logger = get_logger(__name__)


router = APIRouter()


async def get_essay_service(db = Depends(get_db)) -> EssayCheckService:
    return EssayCheckService(db)


def _user_label(user: User) -> str:
    """essay_check 审计日志的 actor_label，统一拼为 '姓名/学工号'。"""
    return f"{user.name or ''}/{user.zju_id or ''}"


@router.post(
    "/upload",
    summary="上传论文并发起审查",
    response_model=ApiResponse[str],
)
async def upload_essay(
    request: Request,
    file: UploadFile = File(...),
    service: EssayCheckService = Depends(get_essay_service),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[str]:
    """上传PDF论文文件，提交到微服务并创建任务记录，返回本地任务ID。"""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        logger.warning(f"[essay_check.py] 只支持PDF文件")
        raise BizException("只支持PDF文件")

    await log_operation(db, user_id=current_user.id, feature_type=FeatureType.ESSAY_CHECK, action="submit")
    file_bytes = await file.read()
    task_id = await service.submit_essay(file_bytes, file.filename, current_user)
    await log_audit(
        db,
        actor_type=AuditActorType.USER,
        actor_id=current_user.id,
        actor_label=_user_label(current_user),
        action="essay_check.submit",
        target_type="essay_task",
        target_id=task_id,
        target_label=file.filename,
        payload={"size_bytes": len(file_bytes)},
        result="success",
        request_ip=get_client_ip(request),
        user_agent=request.headers.get("User-Agent"),
    )
    return ApiResponse.success_response(task_id)


@router.get(
    "/list",
    summary="查询当前用户的论文任务列表",
    response_model=ApiResponse[list[EssayTaskItem]],
)
async def list_essay_tasks(
    service: EssayCheckService = Depends(get_essay_service),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[list[EssayTaskItem]]:
    """返回当前用户提交的所有论文任务，按创建时间倒序。"""
    tasks = await service.list_user_essays(current_user)
    return ApiResponse.success_response(tasks)


@router.get(
    "/overview",
    summary="论文审查总体报告（仅已完成）",
    response_model=ApiResponse[EssayOverview],
)
async def get_essay_overview(
    service: EssayCheckService = Depends(get_essay_service),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[EssayOverview]:
    """汇总当前用户全部历史中已完成论文的结论分布与高频问题检查域。"""
    overview = await service.get_overview(current_user)
    return ApiResponse.success_response(overview)


@router.get(
    "/status/{task_id}",
    summary="查询论文任务详情（进度+报告）",
    response_model=ApiResponse[dict],
)
async def get_essay_status(
    task_id: str,
    service: EssayCheckService = Depends(get_essay_service),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[dict]:
    """从微服务获取指定任务的完整信息：处理进度、页面状态、审查报告（已完成时）。"""
    status = await service.get_essay_status(task_id, current_user)
    return ApiResponse.success_response(status)


@router.delete(
    "/{task_id}",
    summary="删除论文任务",
    response_model=ApiResponse[None],
)
async def delete_essay(
    request: Request,
    task_id: str,
    service: EssayCheckService = Depends(get_essay_service),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[None]:
    """删除指定论文任务记录，同时尝试清理微服务侧数据。"""
    await service.delete_essay(task_id, current_user)
    await log_audit(
        db,
        actor_type=AuditActorType.USER,
        actor_id=current_user.id,
        actor_label=_user_label(current_user),
        action="essay_check.delete",
        target_type="essay_task",
        target_id=task_id,
        result="success",
        request_ip=get_client_ip(request),
        user_agent=request.headers.get("User-Agent"),
    )
    return ApiResponse.success_response(None)


@router.post(
    "/export/stream",
    summary="流式导出论文审查报告（SSE 进度）",
)
async def export_reports_stream(
    request: Request,
    req: ReportExportRequest,
    service: EssayCheckService = Depends(get_essay_service),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """以 SSE 流方式导出，前端实时展示进度，完成后通过 token 下载。"""
    from common.utils.sse import safe_sse_stream

    await log_audit(
        db,
        actor_type=AuditActorType.USER,
        actor_id=current_user.id,
        actor_label=_user_label(current_user),
        action="essay_check.export",
        target_type="essay_task",
        payload={
            "task_ids": list(req.task_ids or []),
            "count": len(req.task_ids or []),
            "export_scope": req.export_scope,
        },
        result="success",
        request_ip=get_client_ip(request),
        user_agent=request.headers.get("User-Agent"),
    )
    async_stream = service.stream_export_reports(req.task_ids, current_user, export_scope=req.export_scope)
    return EventSourceResponse(safe_sse_stream(async_stream))


@router.get(
    "/export/download/{token}",
    summary="下载导出文件（通过 SSE 返回的 token）",
)
async def download_export_file(
    token: str,
    service: EssayCheckService = Depends(get_essay_service),
    current_user: User = Depends(get_current_user),
):
    """根据 SSE 返回的 token 下载生成的文件。"""
    from service.essay_check.service import export_job_manager

    job = export_job_manager.get(token)
    if not job:
        raise BizException("文件已过期或不存在，请重新导出")

    encoded_name = quote(job.filename)
    return StreamingResponse(
        iter([job.content]),
        media_type=job.content_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}"},
    )
