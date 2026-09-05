from typing import Any, AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from agents.refine_pipeline import PipelineConfig, run as run_pipeline
from agents.resource_access import get_owned_resource
from agents.teaching_plan.models import TeachingPlanGenerateParams
from common.models import BizException, SystemException
from common.utils.logger import get_logger
from infra.db import User
from service.resource import ResourceTypeEnum

logger = get_logger(__name__)

# 教案 4 步流水线配置（分析 → 生成 → 事实核查 → 再优化）
TEACHING_PLAN_PIPELINE = PipelineConfig(doc_type="教案", generate_prompt_key="teaching_plan")


async def stream(
    db: AsyncSession,
    params: TeachingPlanGenerateParams,
    actor: User,
) -> AsyncIterator[Any]:
    """流式生成教案的接口。"""
    outline_content = ""
    previous_content = ""
    if params.resource_id:
        resource = await get_owned_resource(db, params.resource_id, actor.id)
        if resource:
            previous_content = resource.content or ""
    else:
        if not params.source_resource_id:
            raise BizException("生成教案需要指定当前资源或源资源（教学大纲）")
        source_resource = await get_owned_resource(db, params.source_resource_id, actor.id)
        if not source_resource:
            raise SystemException(f"源资源不存在: {params.source_resource_id}")
        if source_resource.resource_type != ResourceTypeEnum.OUTLINE:
            raise BizException(f"源资源不是教学大纲: {params.source_resource_id}")
        outline_content = source_resource.content or ""

    if previous_content:
        task_description = (
            "分析用户提示，定位原教案中的相关内容，"
            "对原教案作必要修改（修改内容严格以用户提示为准，禁止过度修改）。"
        )
        reference_content = f"原教案内容：\n\n{previous_content}"
    else:
        if not outline_content:
            logger.warning("[teaching_plan] 教学大纲内容不能为空")
            raise BizException("教学大纲内容不能为空")
        task_description = "根据教学大纲生成高质量教案。"
        reference_content = f"教学大纲：\n\n{outline_content}"
        if params.teaching_plan_form:
            form_data = params.teaching_plan_form.model_dump()
            reference_content += (
                f"\n\n表单要求：\n"
                f"- 章节名：{form_data.get('chapter_name')}\n"
                f"- 课时：{form_data.get('class_hours')}\n"
                f"- 补充描述：{form_data.get('supplementary_description') or '无'}"
            )

    user_prompt = params.prompt or ""
    if params.selected_text:
        user_prompt = f"用户选中的文本：{params.selected_text}\n\n{user_prompt}"
    async for event in run_pipeline(
        TEACHING_PLAN_PIPELINE,
        task_description=task_description,
        reference_content=reference_content,
        user_prompt=user_prompt,
    ):
        yield event
