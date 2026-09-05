from sqlalchemy import Column, String, Integer, DateTime, func, ForeignKey, Text

from infra.db.database import Base
from infra.db.sequence import generate_id


class UserEssayTask(Base):
    """
    用户论文审查任务表
    """
    __tablename__ = "user_essay_task"

    id = Column(String, primary_key=True, default=generate_id)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, comment="用户ID")
    filename = Column(String(255), nullable=False, comment="原始文件名")
    task_id = Column(String(36), nullable=False, unique=True, comment="微服务返回的task UUID")
    status = Column(String(50), nullable=False, default="uploaded", comment="任务状态")
    total_pages = Column(Integer, nullable=True, comment="论文总页数")
    result = Column(Text, nullable=True, comment="审查报告JSON")
    create_time = Column(DateTime(timezone=True), server_default=func.date_trunc("second", func.now()), comment="创建时间")
    update_time = Column(DateTime(timezone=True), server_default=func.date_trunc("second", func.now()), onupdate=func.date_trunc("second", func.now()), comment="更新时间")
