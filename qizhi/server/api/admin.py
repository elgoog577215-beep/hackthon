from datetime import datetime, timedelta
from urllib.parse import quote
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from common.models import ApiResponse, BizException
from common.models.constants import TIMEZONE_SHANGHAI, UserRole
from common.utils.http import get_client_ip
from infra.db import User, get_db
from service.admin import (
    AdminAgentDetail,
    AdminAgentService,
    AdminAuditLogService,
    AdminDashboardService,
    AdminFeedbackDetail,
    AdminFeedbackService,
    AdminUserDetail,
    AgentOperationParams,
    AgentReorderParams,
    AgentToggleParams,
    AgentUsageItem,
    AuditLogDetail,
    AuditLogQueryParams,
    AuditReportParams,
    DashboardStats,
    FeatureUsageItem,
    UserRoleUpdateParams,
    get_current_admin,
    is_admin_user,
)
from service.audit import AuditActorType, log_audit
from service.auth import get_current_user
from service.feedback.models import FeedbackRatingType
from sqlalchemy import select


router = APIRouter()


# ---------- 依赖注入 ----------

async def get_admin_agent_service(db: AsyncSession = Depends(get_db)) -> AdminAgentService:
    return AdminAgentService(db)


async def get_admin_feedback_service(db: AsyncSession = Depends(get_db)) -> AdminFeedbackService:
    return AdminFeedbackService(db)


async def get_admin_dashboard_service(db: AsyncSession = Depends(get_db)) -> AdminDashboardService:
    return AdminDashboardService(db)


async def get_admin_audit_log_service(db: AsyncSession = Depends(get_db)) -> AdminAuditLogService:
    return AdminAuditLogService(db)


def _admin_label(admin: User) -> str:
    """admin actor_label 统一拼接为 '姓名/学工号'，缺字段用空串占位。"""
    return f"{admin.name or ''}/{admin.zju_id or ''}"


# ---------- 通用 ----------

@router.get(
    "/check",
    summary="检查当前用户是否为运营管理员",
    response_model=ApiResponse[dict],
)
async def check_admin(
    current_user: User = Depends(get_current_user),
) -> ApiResponse[dict]:
    """非管理员返回 {is_admin: false} 而非 401，便于前端隐藏入口。"""
    return ApiResponse.success_response({"is_admin": is_admin_user(current_user)})


# ---------- 智能体管理 ----------

@router.get(
    "/agents",
    summary="智能体广场后台列表（含未上架）",
    response_model=ApiResponse[list[AdminAgentDetail]],
)
async def list_admin_agents(
    service: AdminAgentService = Depends(get_admin_agent_service),
    current_admin: User = Depends(get_current_admin),
) -> ApiResponse[list[AdminAgentDetail]]:
    agents = await service.list_all()
    return ApiResponse.success_response(agents)


@router.post(
    "/agents/operation",
    summary="智能体增删改",
    response_model=ApiResponse[str | None],
)
async def operate_admin_agent(
    params: AgentOperationParams,
    request: Request,
    db: AsyncSession = Depends(get_db),
    service: AdminAgentService = Depends(get_admin_agent_service),
    current_admin: User = Depends(get_current_admin),
) -> ApiResponse[str | None]:
    result_id = await service.operate(params)
    await log_audit(
        db,
        actor_type=AuditActorType.ADMIN,
        actor_id=current_admin.id,
        actor_label=_admin_label(current_admin),
        action=f"agent.{params.operation.value}",
        target_type="agent",
        target_id=result_id or params.id,
        target_label=params.title,
        payload=params.model_dump(exclude_none=True, exclude={"operation"}),
        result="success",
        request_ip=get_client_ip(request),
        user_agent=request.headers.get("User-Agent"),
    )
    return ApiResponse.success_response(result_id)


@router.post(
    "/agents/toggle",
    summary="上下架智能体",
    response_model=ApiResponse[None],
)
async def toggle_admin_agent(
    params: AgentToggleParams,
    request: Request,
    db: AsyncSession = Depends(get_db),
    service: AdminAgentService = Depends(get_admin_agent_service),
    current_admin: User = Depends(get_current_admin),
) -> ApiResponse[None]:
    await service.toggle(params)
    await log_audit(
        db,
        actor_type=AuditActorType.ADMIN,
        actor_id=current_admin.id,
        actor_label=_admin_label(current_admin),
        action="agent.toggle",
        target_type="agent",
        target_id=params.id,
        payload={"enabled": params.enabled},
        result="success",
        request_ip=get_client_ip(request),
        user_agent=request.headers.get("User-Agent"),
    )
    return ApiResponse.success_response(None)


@router.post(
    "/agents/reorder",
    summary="智能体批量重排（拖拽后提交完整新顺序）",
    response_model=ApiResponse[None],
)
async def reorder_admin_agents(
    params: AgentReorderParams,
    request: Request,
    db: AsyncSession = Depends(get_db),
    service: AdminAgentService = Depends(get_admin_agent_service),
    current_admin: User = Depends(get_current_admin),
) -> ApiResponse[None]:
    await service.reorder(params)
    await log_audit(
        db,
        actor_type=AuditActorType.ADMIN,
        actor_id=current_admin.id,
        actor_label=_admin_label(current_admin),
        action="agent.reorder",
        payload={"count": len(params.id_list)},
        result="success",
        request_ip=get_client_ip(request),
        user_agent=request.headers.get("User-Agent"),
    )
    return ApiResponse.success_response(None)


# ---------- 用户反馈 ----------

@router.get(
    "/feedbacks",
    summary="后台反馈列表",
    response_model=ApiResponse[list[AdminFeedbackDetail]],
)
async def list_admin_feedbacks(
    rating_type: FeedbackRatingType | None = None,
    min_length: int | None = None,
    service: AdminFeedbackService = Depends(get_admin_feedback_service),
    current_admin: User = Depends(get_current_admin),
) -> ApiResponse[list[AdminFeedbackDetail]]:
    feedbacks = await service.list_with_users(rating_type, min_length)
    return ApiResponse.success_response(feedbacks)


@router.get(
    "/feedbacks/export",
    summary="导出用户反馈 Excel",
)
async def export_admin_feedbacks(
    request: Request,
    rating_type: FeedbackRatingType | None = None,
    min_length: int | None = None,
    db: AsyncSession = Depends(get_db),
    service: AdminFeedbackService = Depends(get_admin_feedback_service),
    current_admin: User = Depends(get_current_admin),
) -> Response:
    file_bytes = await service.build_export_xlsx(rating_type, min_length)
    now_sh = datetime.now(ZoneInfo(TIMEZONE_SHANGHAI))
    filename = f"用户反馈_{now_sh.strftime('%Y%m%d_%H%M%S')}.xlsx"
    await log_audit(
        db,
        actor_type=AuditActorType.ADMIN,
        actor_id=current_admin.id,
        actor_label=_admin_label(current_admin),
        action="feedback.export",
        target_label=filename,
        payload={
            "rating_type": rating_type.value if rating_type else None,
            "min_length": min_length,
            "size_bytes": len(file_bytes),
        },
        result="success",
        request_ip=get_client_ip(request),
        user_agent=request.headers.get("User-Agent"),
    )
    return Response(
        content=file_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
        },
    )


# ---------- 数据驾驶舱 ----------

@router.get(
    "/dashboard/stats",
    summary="驾驶舱指标：累计用户 / 日活 / 周活",
    response_model=ApiResponse[DashboardStats],
)
async def get_dashboard_stats(
    service: AdminDashboardService = Depends(get_admin_dashboard_service),
    current_admin: User = Depends(get_current_admin),
) -> ApiResponse[DashboardStats]:
    stats = await service.get_stats()
    return ApiResponse.success_response(stats)


@router.get(
    "/dashboard/users",
    summary="后台用户列表（含分页与关键词筛选；支持按角色过滤）",
    response_model=ApiResponse[list[AdminUserDetail]],
)
async def list_admin_users(
    keyword: str | None = None,
    role: UserRole | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    service: AdminDashboardService = Depends(get_admin_dashboard_service),
    current_admin: User = Depends(get_current_admin),
) -> ApiResponse[list[AdminUserDetail]]:
    users = await service.list_users(keyword, limit, offset, role=role.value if role else None)
    return ApiResponse.success_response(users)


@router.patch(
    "/users/{user_id}/role",
    summary="修改用户角色（管理员/教师/学生）",
    response_model=ApiResponse[None],
)
async def update_user_role(
    user_id: str,
    params: UserRoleUpdateParams,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
) -> ApiResponse[None]:
    """管理员修改任意用户的角色。"""
    target = (await db.execute(select(User).where(User.id == user_id))).scalars().first()
    if not target:
        raise BizException("用户不存在")
    # 防自降级：admin 不能把自己改成非 admin，避免误把自己锁出后台
    if target.id == current_admin.id and params.role != UserRole.ADMIN:
        raise BizException("不能降级自己")
    old_role = target.role
    if old_role == params.role.value:
        return ApiResponse.success_response(None)
    target.role = params.role.value
    await db.commit()
    await log_audit(
        db,
        actor_type=AuditActorType.ADMIN,
        actor_id=current_admin.id,
        actor_label=_admin_label(current_admin),
        action="user.role_update",
        target_type="user",
        target_id=user_id,
        target_label=target.name,
        payload={"from": old_role, "to": params.role.value},
        result="success",
        request_ip=get_client_ip(request),
        user_agent=request.headers.get("User-Agent"),
    )
    return ApiResponse.success_response(None)


@router.get(
    "/dashboard/feature-usage",
    summary="驾驶舱：常驻功能 + 上架智能体使用排序",
    response_model=ApiResponse[list[FeatureUsageItem]],
)
async def list_feature_usage(
    days: int = Query(default=7, ge=1, le=365, description="统计最近 N 天，默认 7"),
    service: AdminDashboardService = Depends(get_admin_dashboard_service),
    current_admin: User = Depends(get_current_admin),
) -> ApiResponse[list[FeatureUsageItem]]:
    now_sh = datetime.now(ZoneInfo(TIMEZONE_SHANGHAI))
    start = now_sh - timedelta(days=days)
    items = await service.list_feature_usage(start=start, end=now_sh)
    return ApiResponse.success_response(items)


@router.get(
    "/dashboard/agent-usage",
    summary="驾驶舱：智能体使用 Top N",
    response_model=ApiResponse[list[AgentUsageItem]],
)
async def list_agent_usage(
    days: int = Query(default=7, ge=1, le=365),
    limit: int = Query(default=10, ge=1, le=100),
    service: AdminDashboardService = Depends(get_admin_dashboard_service),
    current_admin: User = Depends(get_current_admin),
) -> ApiResponse[list[AgentUsageItem]]:
    now_sh = datetime.now(ZoneInfo(TIMEZONE_SHANGHAI))
    start = now_sh - timedelta(days=days)
    items = await service.list_agent_usage(start=start, end=now_sh, limit=limit)
    return ApiResponse.success_response(items)


@router.get(
    "/dashboard/users/export",
    summary="导出用户明细 Excel",
)
async def export_admin_users(
    request: Request,
    keyword: str | None = None,
    role: UserRole | None = None,
    db: AsyncSession = Depends(get_db),
    service: AdminDashboardService = Depends(get_admin_dashboard_service),
    current_admin: User = Depends(get_current_admin),
) -> Response:
    file_bytes = await service.build_users_xlsx(keyword, role=role.value if role else None)
    now_sh = datetime.now(ZoneInfo(TIMEZONE_SHANGHAI))
    filename = f"用户明细_{now_sh.strftime('%Y%m%d_%H%M%S')}.xlsx"
    await log_audit(
        db,
        actor_type=AuditActorType.ADMIN,
        actor_id=current_admin.id,
        actor_label=_admin_label(current_admin),
        action="user.export",
        target_label=filename,
        payload={
            "keyword": keyword,
            "role": role.value if role else None,
            "size_bytes": len(file_bytes),
        },
        result="success",
        request_ip=get_client_ip(request),
        user_agent=request.headers.get("User-Agent"),
    )
    return Response(
        content=file_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
        },
    )


# ---------- 审计日志 ----------

@router.post(
    "/audit/report",
    summary="管理员手动补录一条审计事件",
    response_model=ApiResponse[None],
)
async def report_audit_admin(
    params: AuditReportParams,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
) -> ApiResponse[None]:
    """`actor_type` / `actor_id` / `actor_label` 全部由路由层从当前 admin 强制覆盖。"""
    await log_audit(
        db,
        actor_type=AuditActorType.ADMIN,
        actor_id=current_admin.id,
        actor_label=_admin_label(current_admin),
        action=params.action,
        target_type=params.target_type,
        target_id=params.target_id,
        target_label=params.target_label,
        payload=params.payload,
        result=params.result,
        request_ip=get_client_ip(request),
        user_agent=request.headers.get("User-Agent"),
        extra=params.extra,
        idempotency_key=params.idempotency_key,
    )
    return ApiResponse.success_response(None)


@router.get(
    "/audit-logs",
    summary="审计日志查询",
    response_model=ApiResponse[list[AuditLogDetail]],
)
async def list_audit_logs(
    actor_type: str | None = None,
    actor_id: str | None = None,
    action: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    time_from: datetime | None = None,
    time_to: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    service: AdminAuditLogService = Depends(get_admin_audit_log_service),
    current_admin: User = Depends(get_current_admin),
) -> ApiResponse[list[AuditLogDetail]]:
    items = await service.list_logs(AuditLogQueryParams(
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        time_from=time_from,
        time_to=time_to,
        limit=limit,
        offset=offset,
    ))
    return ApiResponse.success_response(items)


@router.get(
    "/audit-logs/export",
    summary="审计日志导出 Excel",
)
async def export_audit_logs(
    actor_type: str | None = None,
    actor_id: str | None = None,
    action: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    time_from: datetime | None = None,
    time_to: datetime | None = None,
    service: AdminAuditLogService = Depends(get_admin_audit_log_service),
    current_admin: User = Depends(get_current_admin),
) -> Response:
    file_bytes = await service.build_export_xlsx(AuditLogQueryParams(
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        time_from=time_from,
        time_to=time_to,
    ))
    now_sh = datetime.now(ZoneInfo(TIMEZONE_SHANGHAI))
    filename = f"审计日志_{now_sh.strftime('%Y%m%d_%H%M%S')}.xlsx"
    return Response(
        content=file_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
        },
    )
