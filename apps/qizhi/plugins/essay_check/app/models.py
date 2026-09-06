import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, Integer, Text, DateTime, ForeignKey, JSON
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.config import ENV
from app.database import Base


def _tbl(name: str) -> str:
    return f"{name}_dev" if ENV == "dev" else name


class Task(Base):
    __tablename__ = _tbl("task")

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename = Column(String(255), nullable=False)
    file_size = Column(Integer, nullable=False)
    total_pages = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default="uploaded")
    current_stage = Column(String(50), default="等待处理")
    result = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    pages = relationship("TaskPage", back_populates="task", order_by="TaskPage.page_number")


class TaskPage(Base):
    __tablename__ = _tbl("task_page")

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id = Column(UUID(as_uuid=True), ForeignKey(f"{_tbl('task')}.id"), nullable=False)
    page_number = Column(Integer, nullable=False)
    image_url = Column(String(500), nullable=True)
    page_type = Column(String(50), nullable=True)
    extracted_content = Column(JSON, nullable=True)
    check_results = Column(JSON, nullable=True)
    status = Column(String(20), nullable=False, default="pending")
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    task = relationship("Task", back_populates="pages")
