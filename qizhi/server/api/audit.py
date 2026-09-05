from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from common.models import ApiResponse
from common.utils.http import get_client_ip
from infra.db import get_db
from service.admin import AuditReportParams
from service.audit import AuditActorType, log_audit
from service.audit.auth import require_audit_service_token


router = APIRouter()


@router.post(
    "/report",
    summary="外置 agent 上报一条审计事件（X-Audit-Service-Token 鉴权）",
    response_model=ApiResponse[None],
    dependencies=[Depends(require_audit_service_token)],
)
async def report_audit_agent(
    params: AuditReportParams,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[None]:
    """供外置 agent / 独立服务上报。

    `actor_type` 路由层强制覆盖为 AGENT，请求体里的 actor_type 字段忽略；
    `actor_id` / `actor_label` 由请求方提供（例：`actor_id="essay_check"`、
    `actor_label="论文检测服务"`），用于在审计列表中标识来源。

    `on_behalf_of_*` 用于记录"agent 代表哪个用户做的"，会合并写入 extra.on_behalf_of。
    """
    extra = dict(params.extra or {})
    if params.on_behalf_of_user_id or params.on_behalf_of_role or params.on_behalf_of_label:
        extra["on_behalf_of"] = {
            "user_id": params.on_behalf_of_user_id,
            "role": params.on_behalf_of_role,
            "label": params.on_behalf_of_label,
        }
    await log_audit(
        db,
        actor_type=AuditActorType.AGENT,
        actor_id=params.actor_id,
        actor_label=params.actor_label,
        action=params.action,
        target_type=params.target_type,
        target_id=params.target_id,
        target_label=params.target_label,
        payload=params.payload,
        result=params.result,
        request_ip=get_client_ip(request),
        user_agent=request.headers.get("User-Agent"),
        extra=extra or None,
        idempotency_key=params.idempotency_key,
    )
    return ApiResponse.success_response(None)
