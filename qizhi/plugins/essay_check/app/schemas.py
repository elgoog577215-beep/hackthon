from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


# ── Result schemas (前置，被 TaskResponse 引用) ──

class CheckPointResult(BaseModel):
    name: str
    passed: Optional[bool] = None
    detail: Optional[str] = None


class CheckDomainResult(BaseModel):
    domain: str
    check_points: list[CheckPointResult]


class ReportResponse(BaseModel):
    task_id: UUID
    overall_score: str
    summary: str
    check_domains: list[CheckDomainResult]
    reference_issues: Optional[list] = None
    recommendations: Optional[list[str]] = None


# ── Task schemas ──

class TaskCreate(BaseModel):
    task_id: UUID
    filename: str
    total_pages: int
    status: str = "uploaded"


class PageInfo(BaseModel):
    page_number: int
    status: str
    page_type: Optional[str] = None
    image_url: Optional[str] = None
    check_results: Optional[list] = None
    error_message: Optional[str] = None


class ProgressInfo(BaseModel):
    total_pages: int
    completed_pages: int
    failed_pages: int
    pending_pages: int
    processing_pages: int
    percentage: float


class TaskResponse(BaseModel):
    task_id: UUID
    filename: str
    total_pages: int
    status: str
    current_stage: str
    progress: ProgressInfo
    pages: list[PageInfo]
    created_at: datetime
    updated_at: datetime
    # 审查报告（completed 时有值）
    overall_score: Optional[str] = None
    summary: Optional[str] = None
    check_domains: Optional[list[CheckDomainResult]] = None
    reference_issues: Optional[list] = None
    recommendations: Optional[list[str]] = None

    model_config = {"from_attributes": True}


class TaskPageItem(BaseModel):
    id: UUID
    page_number: int
    image_url: str | None = None
    page_type: str | None = None
    extracted_content: dict | None = None
    check_results: list | None = None
    status: str
    error_message: str | None = None
    retry_count: int
    created_at: datetime
    updated_at: datetime


class TaskPagesResponse(BaseModel):
    total: int
    page: int
    page_size: int
    pages: list[TaskPageItem]


class TaskListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    tasks: list[dict]


class UploadResponse(BaseModel):
    task_id: UUID
    filename: str
    total_pages: int
    status: str
    message: str
