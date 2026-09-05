from agents.assistant.context import Context
from agents.assistant.tools.registry import tool_registry
from service.course.service import CourseService
from common.utils.logger import get_logger

logger = get_logger(__name__)


@tool_registry.register(
    description="查询当前用户的课程列表。当用户想查看自己的课程、搜索课程、列举课程时调用。",
    loading_message="正在查询课程列表...",
    parameters={
        "type": "object",
        "properties": {
            "keyword": {
                "type": "string",
                "description": "搜索关键词，可选。用于按课程名称或标签过滤。",
            },
        },
        "required": [],
    },
)
async def list_courses(payload: dict, context: Context) -> str:
    """查询课程列表，返回格式化的课程信息。"""
    if not context.current_user:
        logger.warning("[course_query.py] 未获取到当前用户信息")
        return "未获取到当前用户信息，无法查询课程"

    keyword = payload.get("keyword")
    service = CourseService(context.db)
    courses = await service.list_courses(keyword, context.current_user)

    if not courses:
        return "暂无课程记录" if not keyword else f"未找到包含「{keyword}」的课程"

    lines = [f"共找到 {len(courses)} 门课程："]
    for c in courses:
        managers = "、".join([m.name for m in c.managers]) if c.managers else "无"
        labels = "、".join(c.labels) if c.labels else "无"
        lines.append(
            f"- 课程 ID: {c.id}"
            f"\n  名称: {c.name}"
            f"\n  课时数: {c.lesson_count}"
            f"\n  描述: {c.description}"
            f"\n  标签: {labels}"
            f"\n  负责人: {managers}"
        )
    return "\n".join(lines)


@tool_registry.register(
    description="根据课程 ID 获取课程详情。当用户需要查看某门课程的具体信息时调用。",
    loading_message="正在获取课程详情...",
    parameters={
        "type": "object",
        "properties": {
            "course_id": {
                "type": "string",
                "description": "课程 ID，必填",
            },
        },
        "required": ["course_id"],
    },
)
async def get_course(payload: dict, context: Context) -> str:
    """获取单门课程详情。"""
    if not context.current_user:
        logger.warning("[course_query.py] 未获取到当前用户信息")
        return "未获取到当前用户信息，无法查询课程"

    course_id = payload.get("course_id", "")
    service = CourseService(context.db)
    course = await service.get_course_by_id(course_id, context.current_user)

    if not course:
        return f"未找到课程（ID: {course_id}）或您没有权限查看该课程"

    managers = "、".join([m.name for m in course.managers]) if course.managers else "无"
    labels = "、".join(course.labels) if course.labels else "无"
    return (
        f"课程详情：\n"
        f"- ID: {course.id}\n"
        f"- 名称: {course.name}\n"
        f"- 课时数: {course.lesson_count}\n"
        f"- 描述: {course.description}\n"
        f"- 标签: {labels}\n"
        f"- 负责人: {managers}\n"
        f"- 创建时间: {course.create_time}"
    )
