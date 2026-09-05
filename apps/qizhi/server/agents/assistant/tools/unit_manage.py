from agents.assistant.context import Context
from agents.assistant.tools.registry import tool_registry
from common.models import BizException
from service.course.unit_models import UnitCreateParams, UnitDeleteParams, UnitUpdateParams
from service.course.unit_service import UnitService
from common.utils.logger import get_logger

logger = get_logger(__name__)


@tool_registry.register(
    description="查询某门课程的单元（章节）树结构。当用户想查看课程有哪些章节、了解课程结构时调用。",
    loading_message="正在查询课程章节结构...",
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
async def list_units(payload: dict, context: Context) -> str:
    """查询课程的单元树结构。"""
    if not context.current_user:
        logger.warning("[unit_manage.py] 未获取到当前用户信息")
        return "未获取到当前用户信息，无法查询章节"

    course_id = payload.get("course_id", "")
    service = UnitService(context.db)
    try:
        units = await service.list_units(course_id, context.current_user)
    except Exception as exc:
        return f"查询章节失败: {exc}"

    if not units:
        return "该课程暂无章节"

    def format_tree(nodes, level=0):
        lines = []
        indent = "  " * level
        for node in nodes:
            detail = node.detail
            lines.append(
                f"{indent}- 章节 ID: {detail.id}"
                f"\n{indent}  名称: {detail.name}"
                f"\n{indent}  描述: {detail.description}"
            )
            if node.children:
                lines.extend(format_tree(node.children, level + 1))
        return lines

    return "课程章节结构：\n" + "\n".join(format_tree(units))


@tool_registry.register(
    description="""创建课程单元（章节）。当用户需要为课程添加新章节、新单元时调用。

参数说明：
- course_id（必填）：所属课程 ID
- name（必填）：章节名称
- parent_unit_id（可选）：父章节 ID。用于确定层级，创建子章节时必须传入父章节的 unit_id；不填则为顶级章节
- previous_unit_id（可选）：前一章节 ID。用于确定同层级内的排列顺序，传入同一层级中前一个章节的 unit_id；不填则插入到该层级的最前面
- description（可选）：章节描述

重要：创建多个同层级章节时，第一个章节可以不传 previous_unit_id，但后续章节必须传入前一章节的 unit_id，否则章节会倒序排列。""",
    loading_message="正在创建章节...",
    parameters={
        "type": "object",
        "properties": {
            "course_id": {
                "type": "string",
                "description": "所属课程 ID，必填",
            },
            "name": {
                "type": "string",
                "description": "章节名称，必填",
            },
            "description": {
                "type": "string",
                "description": "章节描述，可选",
            },
            "parent_unit_id": {
                "type": "string",
                "description": "父单元 ID，可选。用于确定层级，如创建子章节时传入父章节的 unit_id；不填则为顶级章节",
            },
            "previous_unit_id": {
                "type": "string",
                "description": "前一单元 ID，可选。用于确定同层级内的排列顺序，传入同一层级中前一个章节的 unit_id；不填则插入到该层级的最前面",
            },
        },
        "required": ["course_id", "name"],
    },
)
async def create_unit(payload: dict, context: Context) -> str:
    """创建课程单元/章节。"""
    if not context.current_user:
        logger.warning("[unit_manage.py] 未获取到当前用户信息")
        return "未获取到当前用户信息，无法创建章节"

    params = UnitCreateParams(
        operation="create",
        name=payload.get("name"),
        course_id=payload.get("course_id"),
        description=payload.get("description") or "无",
        parent_unit_id=payload.get("parent_unit_id"),
        previous_unit_id=payload.get("previous_unit_id"),
    )

    import json as _json

    service = UnitService(context.db)
    try:
        unit_id = await service.create_unit(params, context.current_user)
        return _json.dumps(
            {"status": "success", "unit_id": unit_id, "name": params.name},
            ensure_ascii=False,
        )
    except Exception as exc:
        logger.exception("[unit_manage.py] 创建章节失败")
        return f"章节创建失败: {exc}"


@tool_registry.register(
    description="更新课程单元（章节）信息。当用户需要修改章节名称、描述时调用。",
    loading_message="正在更新章节信息...",
    parameters={
        "type": "object",
        "properties": {
            "unit_id": {
                "type": "string",
                "description": "章节 ID，必填",
            },
            "name": {
                "type": "string",
                "description": "新的章节名称，可选",
            },
            "description": {
                "type": "string",
                "description": "新的章节描述，可选",
            },
        },
        "required": ["unit_id"],
    },
)
async def update_unit(payload: dict, context: Context) -> str:
    """更新单元信息。"""
    if not context.current_user:
        logger.warning("[unit_manage.py] 未获取到当前用户信息")
        return "未获取到当前用户信息，无法更新章节"

    params = UnitUpdateParams(
        operation="update",
        id=payload.get("unit_id"),
        name=payload.get("name"),
        description=payload.get("description"),
    )

    service = UnitService(context.db)
    try:
        await service.update_unit(params, context.current_user)
        return "章节更新成功"
    except Exception as exc:
        logger.exception("[unit_manage.py] 更新章节失败")
        return f"章节更新失败: {exc}"


@tool_registry.register(
    description="删除课程单元（章节）。当用户需要删除某章节时调用，会同时删除其子章节。",
    loading_message="正在删除章节...",
    parameters={
        "type": "object",
        "properties": {
            "unit_id": {
                "type": "string",
                "description": "章节 ID，必填",
            },
        },
        "required": ["unit_id"],
    },
)
async def delete_unit(payload: dict, context: Context) -> str:
    """删除单元。"""
    if not context.current_user:
        logger.warning("[unit_manage.py] 未获取到当前用户信息")
        return "未获取到当前用户信息，无法删除章节"

    params = UnitDeleteParams(
        operation="delete",
        id=payload.get("unit_id"),
    )

    service = UnitService(context.db)
    try:
        await service.delete_unit(params, context.current_user)
        return "章节删除成功"
    except Exception as exc:
        logger.exception("[unit_manage.py] 删除章节失败")
        return f"章节删除失败: {exc}"
