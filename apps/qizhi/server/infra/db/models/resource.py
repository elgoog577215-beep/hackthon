from sqlalchemy import Column, Integer, ForeignKey, String, Boolean, DateTime, func
from sqlalchemy.orm import relationship

from infra.db.sequence import generate_id
from infra.db.database import Base


class Resource(Base):
    """
    资源表
    """
    __tablename__ = "resources"

    id = Column(String, primary_key=True, default=generate_id)
    name = Column(String, nullable=False, comment="资源名称")
    path = Column(String, comment="资源文件路径")
    resource_type = Column(String, nullable=False, comment="资源类型")
    content = Column(String, comment="内容")
    word_count = Column(Integer, comment="字数")
    ppt_html_url = Column(String, comment="PPT 在线预览(html)地址")
    ppt_pptx_url = Column(String, comment="PPT 下载(pptx)地址")
    editable = Column(Boolean, nullable=False, comment="是否可编辑")
    version_number = Column(Integer, nullable=False, server_default="1", comment="版本号（同作用域内自增）")
    create_time = Column(DateTime(timezone=True), server_default=func.date_trunc("second", func.now()), comment="创建时间")
    update_time = Column(DateTime(timezone=True), server_default=func.date_trunc("second", func.now()), onupdate=func.date_trunc("second", func.now()), comment="更新时间")

    # 关联信息
    creator_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, comment="创建者")
    related_course_id = Column(String, ForeignKey("courses.id", ondelete="SET NULL"), comment="关联课程")
    related_unit_id = Column(String, ForeignKey("course_units.id", ondelete="SET NULL"), comment="关联单元")
    parent_resource_id = Column(String, ForeignKey("resources.id", ondelete="SET NULL"), comment="父资源（教案→大纲版本，PPT→教案版本）")

    creator = relationship("User", foreign_keys=[creator_id])
    related_course = relationship("Course", foreign_keys=[related_course_id])
    related_unit = relationship("CourseUnit", foreign_keys=[related_unit_id])
    parent_resource = relationship("Resource", foreign_keys=[parent_resource_id], remote_side=[id])
