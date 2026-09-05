"""Gemini 结构化输出的 pydantic 模型。

约定：字段名全部用 ASCII（与用户给的字段规范一致），避免 SDK 把中文别名
转成 JSON Schema 时出问题。中文维度名只出现在最终组装的 report.json 顶层键。
知识点树用固定 3 层（非递归），因为 Gemini 结构化输出对递归 $ref 支持不稳。
"""
from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# 维度 2：字幕 / 转写
# ---------------------------------------------------------------------------

class TranscriptSegment(BaseModel):
    start_sec: float = Field(description="片段开始时间，单位秒，相对于所提供视频片段的开头（从 0 计）")
    end_sec: float = Field(description="片段结束时间，单位秒，相对于所提供视频片段的开头")
    text: str = Field(description="该时间段内说话人逐字转写文本（简体中文）")


# ---------------------------------------------------------------------------
# 维度 3：课堂环节
# ---------------------------------------------------------------------------

class KeyPoint(BaseModel):
    name: str
    start_time: str = Field(description="HH:MM:SS")
    end_time: str = Field(description="HH:MM:SS")


class ClassSegment(BaseModel):
    start_time: str = Field(description="HH:MM:SS")
    end_time: str = Field(description="HH:MM:SS")
    type: str = Field(description="环节类型，如：课程回顾/课程导入/知识讲授/课堂提问/课堂活动/布置作业/总结")
    sub_type: str = Field(default="", description="子类型，可为空")
    content: str = Field(description="该环节发生了什么的简述")
    keypoint: List[KeyPoint] = Field(default_factory=list)


class ChapterGroup(BaseModel):
    summary: str = Field(description="该阶段（若干连续环节）的整体小结")
    file_structure: List[ClassSegment]


class PhaseAnalysis(BaseModel):
    """课程导入环节 / 总结环节 的专项分析。"""
    exists: bool = Field(description="课程中是否存在该环节")
    start_time: str = Field(default="", description="HH:MM:SS，不存在则空")
    end_time: str = Field(default="", description="HH:MM:SS，不存在则空")
    content: str = Field(default="", description="该环节的内容描述")
    evaluation: str = Field(default="", description="对该环节质量的评价与建议")


class StructureResult(BaseModel):
    chapters: List[ChapterGroup] = Field(description="按时间顺序分组的课堂环节")
    intro_analysis: PhaseAnalysis = Field(description="课程导入环节分析")
    summary_analysis: PhaseAnalysis = Field(description="总结环节分析")


# ---------------------------------------------------------------------------
# 维度 4：知识点分布（固定 3 层）
# ---------------------------------------------------------------------------

class KnowledgeL3(BaseModel):
    id: str = Field(description='形如 "1.1.1"')
    title: str
    start_time: str = Field(description="HH:MM:SS")
    end_time: str = Field(description="HH:MM:SS")


class KnowledgeL2(BaseModel):
    id: str = Field(description='形如 "1.1"')
    title: str
    start_time: str
    end_time: str
    children: List[KnowledgeL3] = Field(default_factory=list)


class KnowledgeL1(BaseModel):
    id: str = Field(description='形如 "1"')
    title: str
    start_time: str
    end_time: str
    children: List[KnowledgeL2] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 维度 5：互动事件
# ---------------------------------------------------------------------------

CognitiveType = Literal["记忆型", "理解型", "应用型", "分析型", "评价型", "创造型"]
WuheType = Literal["是何", "为何", "如何", "若何", "由何"]


class InteractionEvent(BaseModel):
    text: str = Field(description="互动/提问的规范化表述")
    type: CognitiveType = Field(description="认知层次类型（布鲁姆）")
    segment: str = Field(description="原始语段（教师的实际表述）")
    start_time: str = Field(description="HH:MM:SS")
    end_time: str = Field(description="HH:MM:SS")
    wuhe: WuheType = Field(description="五何分类：是何/为何/如何/若何/由何")


# ---------------------------------------------------------------------------
# 维度 6：思政事件
# ---------------------------------------------------------------------------

class IdeologyBody(BaseModel):
    status: int = Field(description="融入程度等级：0=无 1=隐性 2=显性")
    title: str = Field(description="思政点标题")
    content: str = Field(description="思政融入的具体描述")
    naturalness: int = Field(ge=1, le=5, description="融入自然度评分 1-5")


class IdeologyEvent(BaseModel):
    start_time: str = Field(description="HH:MM:SS，取自字幕中最接近的片段时间")
    end_time: str = Field(description="HH:MM:SS")
    result: IdeologyBody


# ---------------------------------------------------------------------------
# 维度 1：总评 / 雷达（课程名等不由模型填，由 CLI 注入）
# ---------------------------------------------------------------------------

RadarName = Literal["教学表达", "教学设计", "知识呈现", "互动质量", "思政融合"]


class RadarDim(BaseModel):
    name: RadarName
    score: float = Field(ge=0, le=100, description="该维度得分 0-100")
    comment: str = Field(description="该维度评语")


class OverviewResult(BaseModel):
    summary: str = Field(description="AI 总评摘要（200 字左右）")
    radar: List[RadarDim] = Field(description="教学表达/教学设计/知识呈现/互动质量/思政融合 五个维度，各一条")
    overall_score: float = Field(ge=0, le=100, description="综合得分 0-100")
    suggestions: List[str] = Field(description="面向教师的总体改进建议，3-6 条")
    capability_summary: str = Field(
        default="",
        description="能力概述：一段 100-200 字的总体能力评价，概括教师在各维度的表现水平与突出特点",
    )
    improvement_suggestions: List[str] = Field(
        default_factory=list,
        description="改进建议：3-5 条针对性的、可操作的教学改进建议，每条 20-50 字",
    )
