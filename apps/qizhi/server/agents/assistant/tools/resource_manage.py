from agents.assistant.context import Context
from agents.assistant.tools.registry import tool_registry
from service.resource.models import ResourceCreateParams, ResourceTypeEnum, ResourceUpdateParams
from service.resource.service import ResourceService
from common.utils.logger import get_logger

logger = get_logger(__name__)


@tool_registry.register(
    description="查询资源列表。当用户想查看自己的资源、搜索资源、列举某课程或章节下的资源时调用。",
    loading_message="正在查询资源列表...",
    parameters={
        "type": "object",
        "properties": {
            "course_id": {
                "type": "string",
                "description": "关联课程 ID，可选",
            },
            "unit_id": {
                "type": "string",
                "description": "关联单元（章节）ID，可选",
            },
            "resource_type": {
                "type": "string",
                "enum": ["outline", "teaching_plan", "ppt", "question_bank"],
                "description": "资源类型过滤，可选",
            },
            "keyword": {
                "type": "string",
                "description": "搜索关键词，可选",
            },
        },
        "required": [],
    },
)
async def list_resources(payload: dict, context: Context) -> str:
    """查询资源列表。"""
    if not context.current_user:
        logger.warning("[resource_manage.py] 未获取到当前用户信息")
        return "未获取到当前用户信息，无法查询资源"

    course_id = payload.get("course_id")
    unit_id = payload.get("unit_id")
    resource_type = payload.get("resource_type")
    keyword = payload.get("keyword")

    if resource_type:
        try:
            resource_type = ResourceTypeEnum(resource_type)
        except ValueError:
            return f"无效的资源类型: {resource_type}，可选值为 outline、teaching_plan、ppt、question_bank"

    service = ResourceService(context.db)
    resources = await service.list_resources(
        course_id=course_id,
        unit_id=unit_id,
        resource_type=resource_type,
        keyword=keyword,
        current_user=context.current_user,
    )

    if not resources:
        return "未找到符合条件的资源"

    lines = [f"共找到 {len(resources)} 个资源："]
    for r in resources:
        course_name = r.related_course.name if r.related_course else "未关联"
        unit_name = r.related_unit.name if r.related_unit else "未关联"
        lines.append(
            f"- 资源 ID: {r.id}"
            f"\n  名称: {r.name}"
            f"\n  类型: {r.resource_type.value}"
            f"\n  字数: {r.word_count}"
            f"\n  可编辑: {'是' if r.editable else '否'}"
            f"\n  关联课程: {course_name}"
            f"\n  关联章节: {unit_name}"
        )
    return "\n".join(lines)


@tool_registry.register(
    description="获取资源详情。当用户需要查看某个资源的具体内容时调用。",
    loading_message="正在获取资源详情...",
    parameters={
        "type": "object",
        "properties": {
            "resource_id": {
                "type": "string",
                "description": "资源 ID，必填",
            },
        },
        "required": ["resource_id"],
    },
)
async def get_resource(payload: dict, context: Context) -> str:
    """获取资源详情。"""
    if not context.current_user:
        logger.warning("[resource_manage.py] 未获取到当前用户信息")
        return "未获取到当前用户信息，无法查询资源"

    resource_id = payload.get("resource_id", "")
    service = ResourceService(context.db)
    resource = await service.get_resource_by_id(resource_id, context.current_user)

    if not resource:
        return f"未找到资源（ID: {resource_id}）或您没有权限查看"

    course_name = resource.related_course.name if resource.related_course else "未关联"
    unit_name = resource.related_unit.name if resource.related_unit else "未关联"
    content_preview = resource.content[:500] + "..." if resource.content and len(resource.content) > 500 else (resource.content or "（无内容）")
    return (
        f"资源详情：\n"
        f"- ID: {resource.id}\n"
        f"- 名称: {resource.name}\n"
        f"- 类型: {resource.resource_type.value}\n"
        f"- 字数: {resource.word_count}\n"
        f"- 可编辑: {'是' if resource.editable else '否'}\n"
        f"- 关联课程: {course_name}\n"
        f"- 关联章节: {unit_name}\n"
        f"- 内容预览: {content_preview}"
    )


@tool_registry.register(
    description="创建可编辑资源（如教学大纲、教案）。当用户需要为课程或章节创建大纲、教案、习题集等资源时调用。创建后的资源内容为空，需要调用 update_resource_content 写入内容。",
    loading_message="正在创建资源...",
    parameters={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "资源名称，必填",
            },
            "resource_type": {
                "type": "string",
                "enum": ["outline", "teaching_plan", "ppt", "question_bank"],
                "description": "资源类型，必填",
            },
            "related_course_id": {
                "type": "string",
                "description": "关联课程 ID，可选",
            },
            "related_unit_id": {
                "type": "string",
                "description": "关联单元（章节）ID，可选",
            },
        },
        "required": ["name", "resource_type"],
    },
)
async def create_resource(payload: dict, context: Context) -> str:
    """创建可编辑资源。"""
    if not context.current_user:
        logger.warning("[resource_manage.py] 未获取到当前用户信息")
        return "未获取到当前用户信息，无法创建资源"

    resource_type = payload.get("resource_type", "")
    try:
        resource_type_enum = ResourceTypeEnum(resource_type)
    except ValueError:
        return f"无效的资源类型: {resource_type}"

    params = ResourceCreateParams(
        operation="create",
        name=payload.get("name"),
        resource_type=resource_type_enum,
        editable=True,
        related_course_id=payload.get("related_course_id"),
        related_unit_id=payload.get("related_unit_id"),
    )

    import json as _json

    service = ResourceService(context.db)
    try:
        resource_id = await service.create_resource(params, context.current_user)
        return _json.dumps(
            {"status": "success", "resource_id": resource_id, "name": params.name},
            ensure_ascii=False,
        )
    except Exception as exc:
        logger.exception("[resource_manage.py] 创建资源失败")
        return f"资源创建失败: {exc}"


@tool_registry.register(
    description="更新可编辑资源的内容。当用户需要写入或修改教案、大纲等资源的文本内容时调用。",
    loading_message="正在更新资源内容...",
    parameters={
        "type": "object",
        "properties": {
            "resource_id": {
                "type": "string",
                "description": "资源 ID，必填",
            },
            "content": {
                "type": "string",
                "description": "资源内容（Markdown 格式），必填",
            },
        },
        "required": ["resource_id", "content"],
    },
)
async def update_resource_content(payload: dict, context: Context) -> str:
    """更新资源内容。"""
    if not context.current_user:
        logger.warning("[resource_manage.py] 未获取到当前用户信息")
        return "未获取到当前用户信息，无法更新资源"

    params = ResourceUpdateParams(
        operation="update",
        id=payload.get("resource_id"),
        content=payload.get("content"),
    )

    service = ResourceService(context.db)
    try:
        await service.update_resource(params, context.current_user)
        return "资源内容更新成功"
    except Exception as exc:
        logger.exception("[resource_manage.py] 更新资源内容失败")
        return f"资源内容更新失败: {exc}"
