from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: str | None = Field(default=None, description="会话ID")
    query: str = Field(description="查询内容")
    file_paths: list[str] | None = Field(default=None, description="文件路径列表")
    extra_params: dict[str, Any] | None = Field(default=None, description="额外参数")
