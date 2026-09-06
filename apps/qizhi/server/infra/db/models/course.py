from sqlalchemy import ARRAY, Column, Integer, String, DateTime, ForeignKey, Table, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from infra.db.sequence import generate_id
from infra.db.database import Base


# 课程管理员关联表
course_manager = Table(
    "course_manager",
    Base.metadata,
    Column("course_id", ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True),
    Column("manager_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
)


class Course(Base):
    """
    课程表
    """
    __tablename__ = "courses"

    id = Column(String, primary_key=True, default=generate_id)
    name = Column(String, nullable=False, comment="课程名称")
    lesson_count = Column(Integer, nullable=False, comment="课时数")
    description = Column(String, nullable=False, comment="课程简介")
    labels = Column(ARRAY(String), nullable=False, comment="课程标签")
    # 课程展示用的扩展字段（grade/category/credits/major/offline_hours_ratio/offline_score_ratio 等），
    # 列名必须用 extra_info：metadata 是 SQLAlchemy Declarative 保留名，会与 Base.metadata 冲突。
    extra_info = Column(JSONB, nullable=True, comment="课程展示扩展信息(JSON)")
    create_time = Column(DateTime(timezone=True), server_default=func.date_trunc("second", func.now()), comment="创建时间")
    update_time = Column(DateTime(timezone=True), server_default=func.date_trunc("second", func.now()), onupdate=func.date_trunc("second", func.now()), comment="更新时间")

    # 关联信息
    creator_id = Column(String, ForeignKey("users.id"), nullable=False, comment="创建者")

    creator = relationship("User", foreign_keys=[creator_id])
    managers = relationship("User", secondary=course_manager)


class CourseUnit(Base):
    """
    单元表
    """
    __tablename__ = "course_units"

    id = Column(String, primary_key=True, default=generate_id)
    name = Column(String, nullable=False, comment="单元名称")
    description = Column(String, nullable=False, comment="单元简介")
    create_time = Column(DateTime(timezone=True), server_default=func.date_trunc("second", func.now()), comment="创建时间")
    update_time = Column(DateTime(timezone=True), server_default=func.date_trunc("second", func.now()), onupdate=func.date_trunc("second", func.now()), comment="更新时间")

    # 树结构
    parent_unit_id = Column(String, ForeignKey("course_units.id"), comment="父节点")
    next_unit_id = Column(String, ForeignKey("course_units.id"), comment="下一个节点")
    level = Column(Integer, nullable=False, comment="层级")

    # 关联信息
    course_id = Column(String, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, comment="对应课程")

    course = relationship("Course", foreign_keys=[course_id])
