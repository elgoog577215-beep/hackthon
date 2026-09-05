from sqlalchemy import Column, String, Text, Boolean, Integer, DateTime, func, ARRAY

from infra.db.database import Base
from infra.db.sequence import generate_id


class Agent(Base):
    """
    智能体广场表
    """
    __tablename__ = "agents"

    id = Column(String, primary_key=True, default=generate_id)
    card_key = Column(String, unique=True, comment="稳定标识，用于 seed 幂等；后台新建可为空")
    title = Column(String, comment="标题")
    description = Column(Text, comment="描述")
    tags = Column(ARRAY(String), comment="标签")
    popular = Column(Boolean, default=False, server_default="false", comment="是否热门")
    badge_bg = Column(String, comment="标签底色")
    badge_fg = Column(String, comment="标签前景色")
    icon_path = Column(Text, comment="SVG path d 属性")
    href = Column(String, comment="外链 URL")
    route_to = Column(String, comment="内部 Vue 路由")
    enabled = Column(Boolean, default=True, server_default="true", comment="是否上架")
    sort_order = Column(Integer, default=0, server_default="0", comment="排序，升序展示")
    create_time = Column(DateTime(timezone=True), server_default=func.date_trunc("second", func.now()), comment="创建时间")
    update_time = Column(DateTime(timezone=True), server_default=func.date_trunc("second", func.now()), onupdate=func.date_trunc("second", func.now()), comment="更新时间")
