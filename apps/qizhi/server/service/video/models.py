from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class VideoStatusEnum(str, Enum):
    """视频状态"""
    UNSTARTED = "unstarted" # 未分析
    WAITING = "waiting" # 分析中
    SUCCESS = "success" # 分析成功
    FAILED = "failed" # 分析失败


class VideoSummary(BaseModel):
    """视频概要"""
    id: str = Field(description="ID")
    name: str = Field(description="名称")
    status: VideoStatusEnum = Field(description="状态")
    cover: str | None = Field(description="封面")
    analysis_start_time: str | None = Field(description="分析开始时间")
    related_course_id: str | None = Field(default=None, description="关联课程ID")
    related_resource_id: str | None = Field(default=None, description="关联资源ID（通常为教案版本）")
    create_time: str = Field(description="创建时间")
    estimated_seconds: int | None = Field(
        default=None,
        description="本地分析预估剩余秒数（仅本地分析的「分析中」视频；含排队等待）；云端分析为 null",
    )


class VideoAnalysisResult(BaseModel):
    """视频五维度二次分析结果（V2 新链路）。

    只包含二次分析产出的结构化数据，不包含超星原始数据。
    """

    model_config = ConfigDict(extra="allow")

    # 五维度详细分析
    teaching_expression: dict[str, Any] | None = Field(default=None, description="教学表达")
    teaching_design: dict[str, Any] | None = Field(default=None, description="教学设计")
    knowledge_presentation: dict[str, Any] | None = Field(default=None, description="知识呈现")
    interaction_quality: dict[str, Any] | None = Field(default=None, description="互动质量")
    ideological_integration: dict[str, Any] | None = Field(default=None, description="思政融合")

    # 评分与总览
    scores: dict[str, int] | None = Field(default=None, description="各维度得分")
    radar_data: list[dict[str, Any]] | None = Field(default=None, description="雷达图数据")
    ai_summary: dict[str, Any] | None = Field(default=None, description="AI 总评摘要")


class VideoDetail(BaseModel):
    """视频详情"""
    id: str = Field(description="ID")
    name: str = Field(description="名称")
    path: str = Field(description="路径")
    status: VideoStatusEnum = Field(description="状态")
    analysis_id: str | None = Field(description="超星分析ID")
    analysis_start_time: str | None = Field(description="分析开始时间")
    analysis_result: VideoAnalysisResult | None = Field(description="分析结果")
    related_course_id: str | None = Field(default=None, description="关联课程ID")
    related_resource_id: str | None = Field(default=None, description="关联资源ID（通常为教案版本）")
    create_time: str = Field(description="创建时间")


class ZhiyunVideoItem(BaseModel):
    """智云课堂视频章节条目"""
    sub_id: str = Field(description="章节ID")
    sub_title: str = Field(description="章节标题")
    teacher_name: str = Field(description="教师姓名")
    class_begin: str = Field(description="上课时间")


class ZhiyunVideoGroup(BaseModel):
    """智云课堂按课程分组"""
    course_id: str = Field(description="课程ID")
    course_name: str = Field(description="课程名称")
    items: list[ZhiyunVideoItem] = Field(description="视频列表")


class ZhiyunImportCancelParams(BaseModel):
    """取消智云课堂视频导入参数"""
    import_id: str = Field(description="导入任务标识（客户端发起导入时生成并随导入请求一并传入）")


class VideoCreateParams(BaseModel):
    """创建视频参数"""
    operation: Literal["create"] = Field(description="操作类型")
    name: str = Field(description="名称")
    path: str = Field(description="路径")
    cover: str = Field(description="封面")


class VideoUpdateParams(BaseModel):
    """更新视频参数"""
    operation: Literal["update"] = Field(description="操作类型")
    id: str = Field(description="ID")
    name: str | None = Field(default=None, description="名称")


class VideoDeleteParams(BaseModel):
    """删除视频参数"""
    operation: Literal["delete"] = Field(description="操作类型")
    id: str = Field(description="ID")


VideoOperationParams = Annotated[
    VideoCreateParams | VideoUpdateParams | VideoDeleteParams,
    Field(discriminator="operation"),
]


class VideoBindingParams(BaseModel):
    """视频绑定参数（绑定/解绑课程与教案版本）"""
    id: str = Field(description="视频ID")
    related_course_id: str | None = Field(default=None, description="关联课程ID")
    related_resource_id: str | None = Field(default=None, description="关联资源ID（通常为教案版本）")
    unbind: bool = Field(default=False, description="是否解绑")
