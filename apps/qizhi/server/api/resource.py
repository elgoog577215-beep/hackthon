from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from common.config import settings
from common.models import ApiResponse, BizException, SystemException
from common.utils import FileFormatEnum, convert_markdown_to_word
from infra.db import User, generate_id, get_db
from service.auth import get_current_teacher
from service.resource import (
    ResourceBindingParams,
    ResourceCopyParams,
    ResourceCreateParams,
    ResourceDeleteParams,
    ResourceDetail,
    ResourceOperationParams,
    ResourceService,
    ResourceSummary,
    ResourceTypeEnum,
    ResourceUpdateParams,
)
from common.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


# ---------- 依赖注入 ----------

async def get_resource_service(db: AsyncSession = Depends(get_db)) -> ResourceService:
    return ResourceService(db)


# ---------- API 接口 ----------

@router.get(
    "",
    summary="按 ID 查询资源",
    response_model=ApiResponse[ResourceDetail],
)
async def query_resource_by_id(
    id: str,
    service: ResourceService = Depends(get_resource_service),
    current_user: User = Depends(get_current_teacher),
) -> ApiResponse[ResourceDetail]:
    """根据资源 ID 返回资源详情。"""
    resource = await service.get_resource_by_id(id, current_user)
    return ApiResponse.success_response(resource)


@router.get(
    "/list",
    summary="按条件筛选资源列表",
    response_model=ApiResponse[list[ResourceSummary]],
)
async def list_resources(
    course_id: str | None = None,
    unit_id: str | None = None,
    resource_type: ResourceTypeEnum | None = None,
    keyword: str | None = None,
    parent_resource_id: str | None = None,
    root_only: bool = False,
    service: ResourceService = Depends(get_resource_service),
    current_user: User = Depends(get_current_teacher),
) -> ApiResponse[list[ResourceSummary]]:
    """按课程、单元、类型、关键词、父资源组合筛选当前用户的资源列表。

    parent_resource_id：层级下钻，仅返回挂在该父资源下的子版本。
    root_only=true：仅返回根级资源（无父资源），课程页大纲版本列表用。
    """
    resources = await service.list_resources(
        course_id,
        unit_id,
        resource_type,
        keyword,
        current_user,
        parent_resource_id=parent_resource_id,
        root_only=root_only,
    )
    return ApiResponse.success_response(resources)


@router.post(
    "/operation",
    summary="执行资源操作",
    response_model=ApiResponse[str | None],
)
async def operate_resource(
    params: ResourceOperationParams,
    service: ResourceService = Depends(get_resource_service),
    current_user: User = Depends(get_current_teacher),
) -> ApiResponse[str | None]:
    """对资源执行增删改等操作，具体行为由 operation 字段决定。"""
    match params:
        case ResourceCreateParams():
            id = await service.create_resource(params, current_user)
            return ApiResponse.success_response(id)
        case ResourceUpdateParams():
            await service.update_resource(params, current_user)
            return ApiResponse.success_response(None)
        case ResourceDeleteParams():
            await service.delete_resource(params, current_user)
            return ApiResponse.success_response(None)
        case ResourceCopyParams():
            id = await service.copy_resource(params, current_user)
            return ApiResponse.success_response(id)


@router.post(
    "/binding",
    summary="绑定或取绑资源",
    response_model=ApiResponse[None],
)
async def bind_resource(
    params: ResourceBindingParams,
    service: ResourceService = Depends(get_resource_service),
    current_user: User = Depends(get_current_teacher),
) -> ApiResponse[None]:
    """为资源绑定课程/单元，或执行取绑。"""
    await service.bind_resource(params, current_user)
    return ApiResponse.success_response(None)


@router.post(
    "/upload",
    summary="上传资源文件",
    response_model=ApiResponse[str],
)
async def upload_resource(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_teacher),
) -> ApiResponse[str]:
    """上传资源文件。"""
    content = await file.read()
    if len(content) > settings.UPLOAD_MAX_SIZE:
        logger.warning(f"[resource.py] 资源文件过大: {len(content)} > {settings.UPLOAD_MAX_SIZE}")
        raise BizException(f"文件过大: {len(content)}")

    suffix = Path(file.filename).suffix.lower()
    allowed = {".pdf", ".pptx"}
    if suffix not in allowed:
        logger.warning(f"[resource.py] 不支持的资源文件格式: {suffix}")
        raise BizException(f"不支持的文件格式，仅允许 PDF、PPTX")

    upload_dir = Path(settings.UPLOAD_DIR) / "resources"
    upload_dir.mkdir(parents=True, exist_ok=True)

    new_name = f"{generate_id()}{suffix}"
    save_path = upload_dir / new_name
    save_path.write_bytes(content)

    return ApiResponse.success_response(str(save_path))


@router.get(
    "/download",
    summary="下载资源文件",
)
async def download_resource(
    id: str,
    format: FileFormatEnum,
    service: ResourceService = Depends(get_resource_service),
    current_user: User = Depends(get_current_teacher),
) -> Response:
    """按指定格式下载资源内容，返回 attachment 响应。"""
    resource = await service.get_resource_by_id(id, current_user)
    if not resource:
        logger.error(f"[resource.py] 资源不存在: {id}")
        raise SystemException(f"资源不存在: {id}")

    # 只读资源（editable=False）直接从 path 下载原文件
    if not resource.editable:
        if not resource.path:
            logger.error(f"[resource.py] 只读资源缺少文件路径: {id}")
            raise SystemException(f"只读资源缺少文件路径: {id}")
        from pathlib import Path as _Path
        target = _Path(resource.path)
        if not target.exists():
            logger.error(f"[resource.py] 文件不存在: {target}")
            raise SystemException(f"文件不存在: {target}")
        return Response(
            content=target.read_bytes(),
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{target.name}"},
        )

    if not resource.content:
        logger.error(f"[resource.py] 资源内容为空: {id}")
        raise SystemException(f"资源内容为空: {id}")

    if format == FileFormatEnum.WORD:
        file_bytes = convert_markdown_to_word(resource.content)
        return Response(
            content=file_bytes,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": "attachment"},
        )
    elif format == FileFormatEnum.MARKDOWN:
        file_bytes = resource.content.encode("utf-8")
        return Response(
            content=file_bytes,
            media_type="text/markdown",
            headers={"Content-Disposition": "attachment"},
        )
    else:
        logger.warning(f"[resource.py] 不支持的文件格式: {format}")
        raise BizException(f"不支持的文件格式: {format}")
