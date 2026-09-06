from sqlalchemy import Column, ForeignKey, Integer, String, DateTime, func, ARRAY
from infra.db.database import Base
from infra.db.sequence import generate_id


class Feedback(Base):
    """
    反馈表
    """
    __tablename__ = "feedbacks"

    id = Column(String, primary_key=True, default=generate_id)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, comment="用户ID")
    star = Column(Integer, nullable=False, comment="星级")
    content = Column(String, nullable=False, comment="评价文案")
    image_paths = Column(ARRAY(String), nullable=False, comment="图片路径")
    create_time = Column(DateTime(timezone=True), server_default=func.date_trunc("second", func.now()), comment="创建时间")
    update_time = Column(DateTime(timezone=True), server_default=func.date_trunc("second", func.now()), onupdate=func.date_trunc("second", func.now()), comment="更新时间")
