from sqlalchemy import Column, DateTime, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB

from infra.db.database import Base
from infra.db.sequence import generate_id


class AuditLog(Base):
    """审计日志（forensics-grade）。

    与 user_operation_logs 的差异：
    - user_operation_logs 是埋点/分析口径，按 (feature_type, feature_key) 聚合次数算 DAU/WAU。
    - audit_logs 是取证口径：按行查「谁在什么时间从哪改了哪条数据」，保留 IP / UA / payload / 幂等键。

    actor_type 由路由层强制覆盖（admin 端点写 ADMIN，service-token 端点写 AGENT），
    避免请求体内 actor_type 字段绕过鉴权伪装他人。

    保留策略：v1 永久保存，无自动清理；如需清理请走 DB 手动 SQL。
    """
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_actor", "actor_type", "actor_id", "create_time"),
        Index("ix_audit_action", "action", "create_time"),
        Index("ix_audit_create_time", "create_time"),
        Index("ix_audit_target", "target_type", "target_id"),
        Index(
            "ix_audit_idem",
            "actor_type",
            "idempotency_key",
            unique=True,
            postgresql_where="idempotency_key IS NOT NULL",
        ),
    )

    id = Column(String, primary_key=True, default=generate_id)

    actor_type = Column(String(20), nullable=False, comment="admin/user/agent/system")
    actor_id = Column(String, nullable=True, comment="责任主体 ID：admin → users.id；agent → 服务名")
    actor_label = Column(String(200), nullable=True, comment="可读标识，例 张三/0010759")

    action = Column(String(100), nullable=False, comment="<service>.<verb>，例 agent.update / essay_check.delete")

    target_type = Column(String(50), nullable=True, comment="目标资源类型，例 agent/feedback/essay_task")
    target_id = Column(String, nullable=True, comment="目标资源 ID")
    target_label = Column(String(200), nullable=True, comment="目标可读名（如 agent title、文件名）")

    payload = Column(JSONB, nullable=True, comment="动作上下文，写入前 8KiB 截断 + PII 关键字脱敏")
    result = Column(String(20), nullable=True, comment="success/failure/partial")

    request_ip = Column(String(64), nullable=True, comment="X-Forwarded-For 首段或 socket 对端")
    user_agent = Column(String(500), nullable=True, comment="HTTP UA")

    extra = Column(JSONB, nullable=True, comment="未来扩展位")
    idempotency_key = Column(String(128), nullable=True, comment="agent 重试幂等键；冲突视为成功")

    create_time = Column(
        DateTime(timezone=True),
        server_default=func.date_trunc("second", func.now()),
        nullable=False,
        comment="创建时间",
    )
