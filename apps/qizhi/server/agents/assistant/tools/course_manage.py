import json

from agents.assistant.context import Context
from agents.assistant.tools.registry import tool_registry
from common.models import BizException
from service.course.models import CourseCreateParams
from service.course.service import CourseService
from common.utils.logger import get_logger

logger = get_logger(__name__)


@tool_registry.register(
    description="创建一门新课程。当用户明确要求新增课程、创建课程、添加课程时调用。",
    loading_message="正在创建课程...",
    parameters={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "课程名称，必填",
            },
            "description": {
                "type": "string",
                "description": "课程描述，可选",
            },
            "lesson_count": {
                "type": "integer",
                "description": "课时数量，可选，默认为 0",
            },
            "labels": {
                "type": "array",
                "items": {"type": "string"},
                "description": "课程标签列表，可选",
            },
            "manager_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "负责人用户 ID 列表，可选；若未提供，默认当前用户为负责人",
            },
        },
        "required": ["name"],
    },
)
async def add_course(payload: dict, context: Context) -> str:
    """创建课程，返回课程 ID 或提示信息。"""
    if not context.current_user:
        logger.warning(f"[course_manage.py] 未获取到当前用户信息，无法创建课程")
        raise BizException("未获取到当前用户信息，无法创建课程")

    manager_ids = payload.get("manager_ids") or []
    if not manager_ids:
        manager_ids = [context.current_user.id]

    params = CourseCreateParams(
        operation="create",
        name=payload.get("name"),
        description=payload.get("description") or "无",
        lesson_count=payload.get("lesson_count") if payload.get("lesson_count") is not None else 0,
        labels=payload.get("labels") or [],
        manager_ids=manager_ids,
    )

    service = CourseService(context.db)
    course_id = await service.create_course(params, context.current_user)
    return json.dumps(
        {"status": "success", "course_id": course_id, "name": params.name},
        ensure_ascii=False,
    )
