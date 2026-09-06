from sqlalchemy import Column, String, Integer, DateTime, func, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB

from infra.db.sequence import generate_id
from infra.db.database import Base


class DocumentAnalysis(Base):
    __tablename__ = "document_analyses"

    id = Column(String, primary_key=True, default=generate_id)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, comment="关联用户")
    file_name = Column(String, nullable=False, comment="原始文件名")
    file_type = Column(String, nullable=False, comment="文件类型 docx/pptx")
    overall_score = Column(Integer, nullable=False, comment="总分 0-100")
    analysis_result = Column(JSONB, nullable=False, comment="完整分析结果")
    create_time = Column(
        DateTime(timezone=True),
        server_default=func.date_trunc("second", func.now()),
        comment="创建时间",
    )
