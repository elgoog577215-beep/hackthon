from sqlalchemy import Column, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB

from infra.db.database import Base
from infra.db.sequence import generate_id


class UserOperationLog(Base):
    """
    用户操作日志：记录用户每次触发的关键业务动作，供驾驶舱图表聚合。

    - feature_type：枚举见 common/models/operation_log.FeatureType
    - feature_key：feature_type=agent 时存 agent_id；其他类型存子路由或 None
    - action：动作语义，如 submit / view / generate / visit
    - extra：可选 JSON，存写入时刻的轻量上下文（不存大数据）
    """
    __tablename__ = "user_operation_logs"

    id = Column(String, primary_key=True, default=generate_id)
    user_id = Column(String, ForeignKey("users.id"), index=True, comment="用户ID")
    feature_type = Column(String, index=True, nullable=False, comment="功能类型")
    feature_key = Column(String, nullable=True, index=True, comment="二级标识（如 agent_id）")
    action = Column(String, nullable=True, comment="动作 submit/view/generate/visit")
    extra = Column(JSONB, nullable=True, comment="附加上下文")
    create_time = Column(
        DateTime(timezone=True),
        server_default=func.date_trunc("second", func.now()),
        index=True,
        comment="创建时间",
    )
