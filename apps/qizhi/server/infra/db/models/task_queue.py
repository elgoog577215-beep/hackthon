from sqlalchemy import Column, String, Integer, DateTime, Text
from sqlalchemy.sql import func

from infra.db.database import Base
from infra.db.sequence import generate_id


class TaskQueue(Base):
    """
    通用异步任务队列。

    设计原则：
    - 只做调度，不存业务结果（结果存在业务表）
    - 不同任务类型由各自的 Handler 决定重试策略与调度时间
    """
    __tablename__ = "task_queue"

    id = Column(String, primary_key=True, default=generate_id)
    task_type = Column(String, nullable=False, index=True, comment="任务类型")
    business_id = Column(String, nullable=False, index=True, comment="业务模型ID")
    status = Column(
        String,
        nullable=False,
        default="pending",
        index=True,
        comment="状态：pending / processing / success / failed",
    )
    retry_count = Column(Integer, default=0, comment="已重试次数")
    error_message = Column(Text, comment="失败原因")
    scheduled_at = Column(DateTime(timezone=True), comment="下次可执行时间")
    completed_at = Column(DateTime(timezone=True), comment="完成时间")
    create_time = Column(
        DateTime(timezone=True),
        server_default=func.date_trunc("second", func.now()),
        comment="创建时间",
    )
