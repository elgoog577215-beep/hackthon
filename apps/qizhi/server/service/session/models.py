from pydantic import BaseModel, Field


class SessionHistoryMessage(BaseModel):
    """会话历史消息"""
    role: str = Field(description="角色")
    type: str = Field(description="类型")
    content: str = Field(description="内容")
    session_id: str = Field(description="会话ID")
    file_paths: list[str] = Field(description="文件路径列表")
    cost_time: int = Field(description="耗时(毫秒)")
    status: str = Field(description="状态")
    error_message: str | None = Field(description="错误信息")


class SessionSummary(BaseModel):
    """
    会话摘要
    """
    id: str = Field(description="ID")
    title: str = Field(description="标题")
    create_time: str = Field(description="创建时间")
    update_time: str = Field(description="更新时间")


class SessionDetail(BaseModel):
    """
    会话详情
    """
    id: str = Field(description="ID")
    title: str = Field(description="标题")
    create_time: str = Field(description="创建时间")
    update_time: str = Field(description="更新时间")
    messages: list[SessionHistoryMessage] = Field(description="消息列表")
