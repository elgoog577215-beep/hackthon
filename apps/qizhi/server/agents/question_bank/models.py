from pydantic import BaseModel, Field


class QuestionBankForm(BaseModel):
    """
    习题集表单
    """
    question_types: list[str] | None = Field(default=None, description='题型，如 ["选择题", "填空题", "简答题"]')
    difficulty: str | None = Field(default=None, description='难度，如 "简单", "中等", "困难"')
    count: int | None = Field(default=None, description="题目数量")


class QuestionBankGenerateParams(BaseModel):
    prompt: str | None = Field(default=None, description="提示词")
    resource_id: str | None = Field(default=None, description="资源ID")
    selected_text: str | None = Field(default=None, description="选中文本")
    source_resource_id: str | None = Field(default=None, description="源资源ID")
    question_bank_form: QuestionBankForm | None = Field(default=None, description="习题集表单")
