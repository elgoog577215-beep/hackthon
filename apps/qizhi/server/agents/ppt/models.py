from pydantic import BaseModel, Field


class PptGenerateParams(BaseModel):
    """PPT 本地生成参数。

    与前端 ResourceGenerateParams 对齐（多余字段如 operation/resource_type/outline_form 会被忽略）。
    source_resource_id 指向作为依据的教案/大纲资源；prompt 为用户额外要求。
    """
    prompt: str | None = Field(default=None, description="用户额外要求/提示词")
    resource_id: str | None = Field(default=None, description="当前 PPT 资源 ID（可空）")
    source_resource_id: str | None = Field(default=None, description="作为依据的教案/大纲资源 ID")
    previous_content: str | None = Field(default=None, description="上一次生成的内容（再次生成时可传）")
    min_slides: int = Field(default=12, ge=4, le=40, description="最少页数")
    max_slides: int = Field(default=24, ge=6, le=60, description="最多页数")
