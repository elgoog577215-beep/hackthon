from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from infra.db import User


@dataclass
class Context:
    """
    Agent 执行上下文
    """

    # 数据库会话
    db: AsyncSession

    # 会话标识
    session_id: str
    chat_id: str

    # 当前登录用户
    current_user: User

    # 消息列表（OpenAI 标准格式）
    messages: list[dict[str, str]] = field(default_factory=list)

    # 附件原始路径（material_review 工具会把原文件上传到 Coze）
    file_paths: list[str] = field(default_factory=list)

    # ReAct 循环状态
    round: int = 0
    max_rounds: int = 50

    # Plan + ReAct 混合架构状态（仅第一轮输出；None 表示尚未输出 plan）
    plan: str | None = None

    def add_message(self, message: dict[str, str]) -> None:
        self.messages.append(message)
