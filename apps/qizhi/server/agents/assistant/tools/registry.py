from dataclasses import dataclass
from typing import Any, AsyncIterator, Awaitable, Callable

from common.models import SystemException
from agents.assistant.context import Context


ToolHandler = Callable[[dict[str, Any], Context], Awaitable[Any | AsyncIterator[Any]]]


@dataclass
class RegisteredTool:
    """
    已注册工具的封装，包含工具配置与实际可调用对象
    """

    name: str
    description: str
    is_enabled: bool  # 是否启用
    parameters: dict[str, Any]  # 参数定义（JSON Schema 风格）
    handler: ToolHandler
    loading_message: str | None = None  # 工具调用开始时的 loading 文案


class ToolRegistry:
    """
    工具注册中心，用于注册和管理工具
    """

    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    def register(
        self,
        name: str | None = None,
        description: str = "",
        *,
        is_enabled: bool = True,
        parameters: dict[str, Any] | None = None,
        loading_message: str | None = None,
    ):
        """装饰器，注册工具。

        维护说明：
        - 工具定义在 import 时注册，因此文件底部的工具导入顺序会影响可用工具集合。
        - parameters 建议保持 JSON Schema 风格，便于模型稳定生成参数。
        """

        def decorator(func: ToolHandler):
            tool_name = name or func.__name__
            self._tools[tool_name] = RegisteredTool(
                name=tool_name,
                description=description or (func.__doc__ or "").strip(),
                is_enabled=is_enabled,
                parameters=parameters or {"type": "object", "properties": {}, "required": []},
                handler=func,
                loading_message=loading_message,
            )
            return func

        return decorator

    def get(self, name: str) -> RegisteredTool | None:
        return self._tools.get(name)

    def list_enabled(self) -> list[RegisteredTool]:
        return [tool for tool in self._tools.values() if tool.is_enabled]

    def planner_specs(self) -> list[dict[str, Any]]:
        """返回给模型的工具规格列表。"""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            }
            for tool in self.list_enabled()
        ]

    async def execute(self, name: str, payload: dict[str, Any], context: Context) -> Any:
        """执行工具。"""
        tool = self.get(name)
        if not tool or not tool.is_enabled:
            logger.error(f"[registry.py] 未找到可用的工具: {name}")
            raise SystemException(f"未找到可用的工具: {name}")

        return await tool.handler(payload, context)


tool_registry = ToolRegistry()


# 触发注册副作用：导入模块后装饰器才会执行
from agents.assistant.tools.course_manage import add_course
from agents.assistant.tools.course_query import list_courses, get_course
from agents.assistant.tools.unit_manage import list_units, create_unit, update_unit, delete_unit
from agents.assistant.tools.resource_manage import list_resources, create_resource, update_resource_content, get_resource
from agents.assistant.tools.video_analysis import video_analysis
from agents.assistant.tools.knowledge_retrieve import knowledge_retrieve
from agents.assistant.tools.material_review import material_review

from common.utils.logger import get_logger

logger = get_logger(__name__)
