from sqlalchemy import Column, String, DateTime, func, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB

from infra.db.sequence import generate_id
from infra.db.database import Base


class Video(Base):
    """
    视频表
    """
    __tablename__ = "videos"

    id = Column(String, primary_key=True, default=generate_id)
    name = Column(String, nullable=False, comment="视频名称")
    path = Column(String, nullable=False, comment="视频文件路径")
    cover = Column(String, nullable=False, comment="封面图路径")
    analysis_id = Column(String, comment="分析任务 ID")
    analysis_start_time = Column(DateTime(timezone=True), comment="开始分析时间")
    analysis_result = Column(JSONB, comment="分析结果")
    status = Column(String, nullable=False, comment="状态")
    source = Column(String, nullable=False, comment="视频来源：upload / zhiyun")
    create_time = Column(DateTime(timezone=True), server_default=func.date_trunc("second", func.now()), comment="创建时间")
    update_time = Column(DateTime(timezone=True), server_default=func.date_trunc("second", func.now()), onupdate=func.date_trunc("second", func.now()), comment="更新时间")

    # 关联信息
    user_id = Column(String, ForeignKey("users.id"), nullable=False, comment="关联用户")
    related_course_id = Column(String, ForeignKey("courses.id", ondelete="SET NULL"), comment="关联课程")
    related_resource_id = Column(String, ForeignKey("resources.id", ondelete="SET NULL"), comment="关联资源（通常为教案版本）")
