"""文档分析数据模型。"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class DocumentFileType(str, Enum):
    """支持的文档类型。"""
    DOCX = "docx"
    PPTX = "pptx"


# ---------------------------------------------------------------------------
# LLM 返回结构（供 JSON schema hint + pydantic 校验）
# ---------------------------------------------------------------------------

class DimensionEvaluation(BaseModel):
    """单维度 LLM 评价结果。"""
    dimension: str = Field(description="维度名称")
    score: int = Field(ge=0, le=100, description="得分 (0-100)")
    strengths: list[str] = Field(default_factory=list, description="优点列表")
    weaknesses: list[str] = Field(default_factory=list, description="不足列表")
    suggestions: list[str] = Field(default_factory=list, description="改进建议")


class SegmentAnalysisResult(BaseModel):
    """单段 LLM 分析结果（包含 6 个维度）。"""
    dimensions: list[DimensionEvaluation] = Field(description="各维度评价")


# ---------------------------------------------------------------------------
# API 请求 / 响应
# ---------------------------------------------------------------------------

class DimensionScore(BaseModel):
    """维度得分摘要（用于前端展示）。"""
    dimension: str = Field(description="维度名称")
    score: int = Field(ge=0, le=100, description="得分 (0-100)")
    comments: str = Field(default="", description="综合评语")
    suggestions: list[str] = Field(default_factory=list, description="改进建议")


class SegmentDetail(BaseModel):
    """单段分析明细。"""
    segment_index: int = Field(description="段序号（从 1 开始）")
    segment_title: str = Field(default="", description="段标题")
    dimensions: list[DimensionEvaluation] = Field(description="各维度评价")


class DocumentAnalysisResult(BaseModel):
    """文档分析最终结果。"""
    file_name: str = Field(description="文件名")
    file_type: str = Field(description="文件类型")
    total_segments: int = Field(description="分段数")
    dimension_scores: list[DimensionScore] = Field(description="各维度综合得分")
    overall_score: int = Field(ge=0, le=100, description="总分")
    radar_data: list[dict[str, Any]] = Field(description="雷达图数据")
    capability_summary: str = Field(default="", description="能力概述")
    improvement_suggestions: list[str] = Field(default_factory=list, description="整体改进建议")
    segment_details: list[SegmentDetail] = Field(default_factory=list, description="分段详情")
