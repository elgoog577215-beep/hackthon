from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, UploadFile, File
from fastapi.responses import Response
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Task, TaskPage
from app.schemas import (
    UploadResponse, TaskResponse, TaskListResponse,
    CheckDomainResult, CheckPointResult, ProgressInfo, PageInfo,
    TaskPageItem, TaskPagesResponse,
)
from app.services.upload import handle_upload
from app.services.oss import delete_task_images, get_image_url, get_image_data, image_to_base64, verify_local_image_token, use_local_storage

from app.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["tasks"])


class ActorContext:
    """主进程透传的调用者身份。插件侧后续回调 /audit/report 时塞进 on_behalf_of_*。"""

    __slots__ = ("user_id", "role", "zju_id")

    def __init__(self, user_id: str | None, role: str | None, zju_id: str | None):
        self.user_id = user_id
        self.role = role
        self.zju_id = zju_id

    @property
    def is_present(self) -> bool:
        return bool(self.user_id or self.zju_id)


def read_actor(
    x_actor_id: str | None = Header(default=None),
    x_actor_role: str | None = Header(default=None),
    x_actor_zju_id: str | None = Header(default=None),
) -> ActorContext:
    """从 X-Actor-* 头读取主进程透传的调用者身份。缺失时返回空 ActorContext。"""
    return ActorContext(
        user_id=x_actor_id or None,
        role=x_actor_role or None,
        zju_id=x_actor_zju_id or None,
    )


@router.post("/tasks/upload", response_model=UploadResponse, status_code=202)
async def upload_task(
    file: UploadFile = File(...),
    actor: ActorContext = Depends(read_actor),
):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="只支持PDF文件")

    content = await file.read()
    try:
        result = await handle_upload(content, file.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if actor.is_present:
        logger.info(
            "upload_task actor=%s role=%s zju_id=%s task=%s",
            actor.user_id, actor.role, actor.zju_id, result["task_id"],
        )

    return UploadResponse(
        task_id=result["task_id"],
        filename=result["filename"],
        total_pages=result["total_pages"],
        status=result["status"],
        message="文件已接收，正在处理中",
    )


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: UUID, db: AsyncSession = Depends(get_db)):
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    result = await db.execute(
        select(TaskPage)
        .where(TaskPage.task_id == task_id)
        .order_by(TaskPage.page_number)
    )
    pages = result.scalars().all()

    completed = sum(1 for p in pages if p.status == "completed")
    failed = sum(1 for p in pages if p.status == "failed")
    pending = sum(1 for p in pages if p.status == "pending")
    processing = sum(1 for p in pages if p.status not in ("completed", "failed", "pending"))
    total = len(pages) or 1

    # 报告数据（completed 时注入）
    overall_score = None
    summary = None
    check_domains = None
    reference_issues = None
    recommendations = None
    if task.status == "completed" and task.result:
        result_data = task.result
        overall_score = result_data.get("overall_score", "未知")
        summary = result_data.get("summary", "")
        check_domains = [
            CheckDomainResult(
                domain=d.get("domain", ""),
                check_points=[
                    CheckPointResult(**cp) for cp in d.get("check_points", [])
                ],
            )
            for d in result_data.get("check_domains", [])
        ]
        reference_issues = result_data.get("reference_issues")
        recommendations = result_data.get("recommendations")

    return TaskResponse(
        task_id=task.id,
        filename=task.filename,
        total_pages=task.total_pages,
        status=task.status,
        current_stage=task.current_stage,
        progress=ProgressInfo(
            total_pages=task.total_pages,
            completed_pages=completed,
            failed_pages=failed,
            pending_pages=pending,
            processing_pages=processing,
            percentage=round(completed / total * 100, 1),
        ),
        pages=[
            PageInfo(
                page_number=p.page_number,
                status=p.status,
                page_type=p.page_type,
                check_results=p.check_results,
                error_message=p.error_message,
                image_url=get_image_url(p.image_url) if p.image_url else None,
            )
            for p in pages
        ],
        created_at=task.created_at,
        updated_at=task.updated_at,
        overall_score=overall_score,
        summary=summary,
        check_domains=check_domains,
        reference_issues=reference_issues,
        recommendations=recommendations,
    )


@router.get("/tasks", response_model=TaskListResponse)
async def list_tasks(
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(Task)
    if status:
        query = query.where(Task.status == status)

    count_query = select(func.count()).select_from(Task)
    if status:
        count_query = count_query.where(Task.status == status)
    count_result = await db.execute(count_query)
    total = count_result.scalar_one()

    query = query.order_by(Task.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    tasks = result.scalars().all()

    return TaskListResponse(
        total=total,
        page=page,
        page_size=page_size,
        tasks=[
            {
                "task_id": str(t.id),
                "filename": t.filename,
                "total_pages": t.total_pages,
                "status": t.status,
                "current_stage": t.current_stage,
                "created_at": t.created_at.isoformat(),
            }
            for t in tasks
        ],
    )


@router.get("/tasks/{task_id}/pages", response_model=TaskPagesResponse)
async def get_task_pages(
    task_id: UUID,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Paginated query of task pages, sorted by page_number."""
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    query = select(TaskPage).where(TaskPage.task_id == task_id)
    if status:
        query = query.where(TaskPage.status == status)

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar_one()

    query = query.order_by(TaskPage.page_number).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    pages = result.scalars().all()

    return TaskPagesResponse(
        total=total,
        page=page,
        page_size=page_size,
        pages=[
            TaskPageItem(
                id=p.id,
                page_number=p.page_number,
                image_url=get_image_url(p.image_url) if p.image_url else None,
                page_type=p.page_type,
                extracted_content=p.extracted_content,
                check_results=p.check_results,
                status=p.status,
                error_message=p.error_message,
                retry_count=p.retry_count,
                created_at=p.created_at,
                updated_at=p.updated_at,
            )
            for p in pages
        ],
    )


@router.get("/tasks/{task_id}/page/{page_number}/image-url")
async def get_page_image_url(task_id: UUID, page_number: int, db: AsyncSession = Depends(get_db)):
    """Get a signed URL for a specific task page image."""
    result = await db.execute(
        select(TaskPage).where(
            TaskPage.task_id == task_id,
            TaskPage.page_number == page_number,
        )
    )
    page = result.scalars().first()
    if not page:
        raise HTTPException(status_code=404, detail="页面不存在")
    if not page.image_url:
        raise HTTPException(status_code=404, detail="页面图片未上传")
    return {"url": get_image_url(page.image_url)}


@router.delete("/tasks/{task_id}", status_code=204)
async def delete_task(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    actor: ActorContext = Depends(read_actor),
):
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if actor.is_present:
        logger.info(
            "delete_task actor=%s role=%s zju_id=%s task=%s",
            actor.user_id, actor.role, actor.zju_id, task_id,
        )

    try:
        delete_task_images(task_id)
    except Exception as e:
        logger.error(f"Failed to delete OSS images for task {task_id}: {e}")

    result = await db.execute(
        select(TaskPage).where(TaskPage.task_id == task_id)
    )
    pages = result.scalars().all()
    for p in pages:
        await db.delete(p)
    await db.delete(task)
    await db.commit()


@router.get("/images/{object_key:path}")
async def serve_image(
    object_key: str,
    t: int | None = Query(default=None, description="expiry timestamp"),
    s: str | None = Query(default=None, description="HMAC signature"),
):
    """Serve image data. PROD validates timestamp + HMAC signature; DEV fetches from OSS."""
    if use_local_storage() and t is not None and s is not None:
        err = verify_local_image_token(t, s, object_key)
        if err:
            raise HTTPException(status_code=403, detail=err)
    data = get_image_data(object_key)
    if data is None:
        raise HTTPException(status_code=404, detail="图片不存在")
    return Response(content=data, media_type="image/png")


@router.get("/tasks/{task_id}/page/{page_number}/image-base64")
async def get_page_image_base64(task_id: UUID, page_number: int, db: AsyncSession = Depends(get_db)):
    """Get base64-encoded image data for a specific task page."""
    result = await db.execute(
        select(TaskPage).where(
            TaskPage.task_id == task_id,
            TaskPage.page_number == page_number,
        )
    )
    page = result.scalars().first()
    if not page:
        raise HTTPException(status_code=404, detail="页面不存在")
    if not page.image_url:
        raise HTTPException(status_code=404, detail="页面图片未上传")
    b64 = image_to_base64(page.image_url)
    if b64 is None:
        raise HTTPException(status_code=404, detail="图片数据不存在")
    return {"image_base64": b64}
