from typing import Any

from pydantic import BaseModel, Field


class OutlineForm(BaseModel):
    """
    教学大纲表单
    """
    course_name: str = Field(description="课程名称")
    course_nature: str = Field(description="课程性质")
    course_category: str = Field(description="课程类别")
    credits: int = Field(description="学分")
    hours: int = Field(description="学时")
    target_major: str = Field(description="授课对象专业")
    target_grade: str = Field(description="授课对象年级")
    teaching_method: str = Field(description="授课方式")
    offline_hours_ratio: int = Field(description="线下学时占比")
    offline_score_ratio: int = Field(description="线下成绩占比")
    prerequisites: str = Field(description="预修要求")
    course_introduction: str = Field(description="课程介绍")
    teaching_objectives: str = Field(description="教学目标")
    ideological_political: str | None = Field(default=None, description="思政内容")
    chapter_structure: Any | None = Field(default=None, description="课程章节结构")


class OutlineGenerateParams(BaseModel):
    prompt: str | None = Field(default=None, description="提示词")
    previous_content: str | None = Field(default=None, description="已有正文（文档转写或编辑后大纲）")
    resource_id: str | None = Field(default=None, description="资源ID（兼容：从库读取正文）")
    selected_text: str | None = Field(default=None, description="选中文本")
    outline_form: OutlineForm | None = Field(default=None, description="大纲表单")
