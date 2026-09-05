from sqlalchemy import Column, ForeignKey, String, DateTime, func, Text, Integer, ARRAY

from infra.db.sequence import generate_id
from infra.db.database import Base


class Session(Base):
    """
    会话表
    """
    __tablename__ = "sessions"

    id = Column(String, primary_key=True, default=generate_id)
    title = Column(String, nullable=False, comment="会话标题")
    sub_session_id = Column(String, comment="子会话 ID")
    create_time = Column(DateTime(timezone=True), server_default=func.date_trunc("second", func.now()), comment="创建时间")
    update_time = Column(DateTime(timezone=True), server_default=func.date_trunc("second", func.now()), onupdate=func.date_trunc("second", func.now()), comment="更新时间")

    # 关联信息
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, comment="关联用户")


class SessionHistory(Base):
    """
    会话历史表
    """
    __tablename__ = "session_histories"

    id = Column(String, primary_key=True, default=generate_id)
    chat_id = Column(String, comment="对话 ID")
    role = Column(String, comment="角色")
    message_type = Column(String, comment="消息类型")
    message_content = Column(Text, comment="消息内容")
    file_paths = Column(ARRAY(String), comment="附件路径")
    file_contents = Column(Text, comment="附件解析文本（注入对话上下文用，不直接展示给用户）")
    cost_time = Column(Integer, comment="耗时（毫秒）")
    status = Column(String, comment="状态")
    error_message = Column(Text, comment="错误信息")
    create_time = Column(DateTime(timezone=True), server_default=func.date_trunc("second", func.now()), comment="创建时间")

    # 关联信息
    session_id = Column(String, ForeignKey("sessions.id", ondelete="CASCADE"), comment="关联会话")
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), comment="关联用户")
