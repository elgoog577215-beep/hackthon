from sqlalchemy import Column, String, DateTime, func

from common.models.constants import UserRole
from infra.db.sequence import generate_id
from infra.db.database import Base


class User(Base):
    """
    用户表
    """
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=generate_id)
    zju_id = Column(String, unique=True, index=True, nullable=False, comment="浙大统一认证学工号")
    name = Column(String, nullable=False, comment="姓名")
    department = Column(String, nullable=False, comment="所属机构")
    phone = Column(String, unique=True, comment="手机号")
    email = Column(String, unique=True, comment="邮箱")
    role = Column(
        String(20),
        nullable=False,
        index=True,
        server_default=UserRole.STUDENT.value,
        comment="用户角色：admin / teacher / student",
    )
    create_time = Column(DateTime(timezone=True), server_default=func.date_trunc("second", func.now()), comment="创建时间")
    update_time = Column(DateTime(timezone=True), server_default=func.date_trunc("second", func.now()), onupdate=func.date_trunc("second", func.now()), comment="更新时间")
