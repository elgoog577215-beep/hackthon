from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.utils.datetime import format_datetime
from infra.db import AuditLog
from service.admin.excel import build_workbook
from service.admin.models import AuditLogDetail, AuditLogQueryParams


EXPORT_HARD_LIMIT = 10000


class AdminAuditLogService:
    """运营后台的审计日志查询与导出服务。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_logs(self, params: AuditLogQueryParams) -> list[AuditLogDetail]:
        rows = await self._query(params)
        return [_row_to_detail(r) for r in rows]

    async def build_export_xlsx(self, params: AuditLogQueryParams) -> bytes:
        export_params = params.model_copy(update={"limit": EXPORT_HARD_LIMIT, "offset": 0})
        rows = await self._query(export_params)
        headers = [
            "序号", "ID", "执行者类型", "执行者ID", "执行者",
            "动作", "目标类型", "目标ID", "目标",
            "结果", "请求IP", "User-Agent", "时间",
        ]
        body: list[list] = []
        for index, r in enumerate(rows, start=1):
            body.append([
                index,
                r.id,
                r.actor_type,
                r.actor_id or "",
                r.actor_label or "",
                r.action,
                r.target_type or "",
                r.target_id or "",
                r.target_label or "",
                r.result or "",
                r.request_ip or "",
                r.user_agent or "",
                format_datetime(r.create_time) or "",
            ])
        return build_workbook("审计日志", headers, body)

    async def _query(self, p: AuditLogQueryParams) -> list[AuditLog]:
        stmt = select(AuditLog)
        if p.actor_type:
            stmt = stmt.where(AuditLog.actor_type == p.actor_type)
        if p.actor_id:
            stmt = stmt.where(AuditLog.actor_id == p.actor_id)
        if p.action:
            stmt = stmt.where(AuditLog.action == p.action)
        if p.target_type:
            stmt = stmt.where(AuditLog.target_type == p.target_type)
        if p.target_id:
            stmt = stmt.where(AuditLog.target_id == p.target_id)
        if p.time_from is not None:
            stmt = stmt.where(AuditLog.create_time >= p.time_from)
        if p.time_to is not None:
            stmt = stmt.where(AuditLog.create_time < p.time_to)
        stmt = stmt.order_by(AuditLog.create_time.desc()).limit(p.limit).offset(p.offset)
        rows = (await self.db.execute(stmt)).scalars().all()
        return list(rows)


def _row_to_detail(r: AuditLog) -> AuditLogDetail:
    return AuditLogDetail(
        id=r.id,
        actor_type=r.actor_type,
        actor_id=r.actor_id,
        actor_label=r.actor_label,
        action=r.action,
        target_type=r.target_type,
        target_id=r.target_id,
        target_label=r.target_label,
        payload=dict(r.payload) if r.payload else None,
        result=r.result,
        request_ip=r.request_ip,
        user_agent=r.user_agent,
        extra=dict(r.extra) if r.extra else None,
        create_time=format_datetime(r.create_time) or "",
    )
