from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from common.models.constants import UserRole


# ---------- 智能体 ----------

class PublicAgentDetail(BaseModel):
    """提供给前端首页（HomeView）使用的智能体卡片信息。"""
    id: str
    card_key: str | None = None
    title: str
    description: str
    tags: list[str] = []
    popular: bool = False
    badge_bg: str
    badge_fg: str
    icon_path: str
    href: str | None = None
    route_to: str | None = None
    sort_order: int = 0


class AdminAgentDetail(PublicAgentDetail):
    """运营后台使用的智能体详情，包含上架状态与时间。"""
    enabled: bool
    create_time: str | None = None
    update_time: str | None = None


class AgentOperationParams(BaseModel):
    """智能体操作参数（CREATE/UPDATE/DELETE）。"""
    operation: str
    id: str | None = None
    card_key: str | None = None
    title: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    popular: bool | None = None
    badge_bg: str | None = None
    badge_fg: str | None = None
    icon_path: str | None = None
    href: str | None = None
    route_to: str | None = None
    enabled: bool | None = None
    sort_order: int | None = None


class AgentToggleParams(BaseModel):
    """上下架快捷开关参数。"""
    id: str
    enabled: bool


class AgentReorderParams(BaseModel):
    """智能体批量排序参数。前端把列表完整新顺序的 id 列表发上来，
    后端按 idx*10 + 10 重置 sort_order。

    注意：发上来的 id_list 必须覆盖当前所有智能体，否则会拒绝（避免漏掉的行
    残留旧 sort_order 与新值冲突）。
    """
    id_list: list[str] = Field(..., description="新的完整顺序，从前到后")


# ---------- 反馈 ----------

class AdminFeedbackDetail(BaseModel):
    """运营后台使用的反馈详情，JOIN 了用户信息。"""
    id: str
    user_id: str | None = None
    user_name: str | None = None
    user_zju_id: str | None = None
    user_department: str | None = None
    star: int
    content: str
    image_paths: list[str] | None = None
    create_time: str


# ---------- 用户 / 驾驶舱 ----------

class AdminUserDetail(BaseModel):
    """运营后台使用的用户明细。"""
    id: str
    zju_id: str | None = None
    name: str | None = None
    department: str | None = None
    phone: str | None = None
    email: str | None = None
    role: str = UserRole.STUDENT.value
    create_time: str | None = None


class UserRoleUpdateParams(BaseModel):
    """修改用户角色请求体。"""
    role: UserRole


class DashboardStats(BaseModel):
    """驾驶舱统计指标。"""
    total_users: int = Field(..., description="累计用户数")
    dau: int = Field(..., description="日活：当日在 user_operation_logs 留下任意一条记录的去重用户数")
    wau: int = Field(..., description="周活：本周（周一起）在 user_operation_logs 留下任意一条记录的去重用户数")
    as_of: str = Field(..., description="统计快照时间（Asia/Shanghai 可读字符串）")


class FeatureUsageItem(BaseModel):
    """单个功能维度的使用聚合。"""
    feature_type: str = Field(..., description="功能类型 key，含常驻功能 + 智能体 (=agent)")
    feature_key: str | None = Field(None, description=(
        "智能体取 agent_id；resource 取子类（outline/ppt/teaching_plan/question_bank）；"
        "video_analysis 取来源（upload/zhiyun）；其他常驻为 None。"
    ))
    label: str = Field(..., description="展示名（常驻功能取 FEATURE_DISPLAY；智能体取标题）")
    count: int = Field(..., description="操作总次数")
    unique_users: int = Field(..., description="去重用户数")
    pending: bool = Field(False, description="是否为待上线功能（前端会加「(待上线)」后缀）")


class AgentUsageItem(BaseModel):
    """智能体使用 Top N。"""
    agent_id: str
    title: str
    count: int
    unique_users: int


# ---------- 审计日志 ----------

class AuditReportParams(BaseModel):
    """通用审计上报请求体。`/admin/audit/report` 与 `/audit/report` 共用同一份 schema。

    路由层会根据鉴权强制覆盖 `actor_type`（admin JWT → admin；service-token → agent），
    请求方在 body 里传任何 actor_type 都会被忽略，避免伪装他人。
    """
    action: str = Field(..., min_length=1, max_length=100, description="<service>.<verb>，例：essay_check.delete")
    actor_id: str | None = Field(None, description="责任主体 ID（agent 端点必传，admin 端点会被覆盖）")
    actor_label: str | None = Field(None, description="可读标识（agent 端点建议填，admin 端点会被覆盖）")
    target_type: str | None = Field(None, max_length=50)
    target_id: str | None = None
    target_label: str | None = Field(None, max_length=200)
    payload: dict[str, Any] | None = None
    result: str | None = Field(None, max_length=20)
    extra: dict[str, Any] | None = None
    idempotency_key: str | None = Field(None, max_length=128)
    # 外置 agent 代表谁做的：从 X-Actor-* 头读取并透传，便于审计追溯实际触发者
    on_behalf_of_user_id: str | None = Field(None, description="外置 agent 代表的真实用户 ID")
    on_behalf_of_role: str | None = Field(None, max_length=20, description="代表用户的角色：admin/teacher/student")
    on_behalf_of_label: str | None = Field(None, max_length=200, description="代表用户的可读标识，例：姓名/学工号")


class AuditLogDetail(BaseModel):
    """单条审计日志的 API 输出。"""
    id: str
    actor_type: str
    actor_id: str | None = None
    actor_label: str | None = None
    action: str
    target_type: str | None = None
    target_id: str | None = None
    target_label: str | None = None
    payload: dict[str, Any] | None = None
    result: str | None = None
    request_ip: str | None = None
    user_agent: str | None = None
    extra: dict[str, Any] | None = None
    create_time: str


class AuditLogQueryParams(BaseModel):
    """审计日志查询过滤参数。"""
    actor_type: str | None = None
    actor_id: str | None = None
    action: str | None = None
    target_type: str | None = None
    target_id: str | None = None
    time_from: datetime | None = None
    time_to: datetime | None = None
    limit: int = Field(100, ge=1, le=1000)
    offset: int = Field(0, ge=0)
