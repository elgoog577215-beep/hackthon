from pydantic import BaseModel, Field


class TeachingPlanForm(BaseModel):
    """
    教案表单
    """
    chapter_name: str = Field(description="章节名")
    supplementary_description: str | None = Field(default=None, description="补充描述")
    class_hours: int | None = Field(default=None, description="课时")


class TeachingPlanGenerateParams(BaseModel):
    prompt: str | None = Field(default=None, description="提示词")
    resource_id: str | None = Field(default=None, description="资源ID")
    selected_text: str | None = Field(default=None, description="选中文本")
    source_resource_id: str | None = Field(default=None, description="源资源ID")
    teaching_plan_form: TeachingPlanForm | None = Field(default=None, description="教案表单")
