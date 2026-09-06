from typing import Any, AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from agents.outline.models import OutlineGenerateParams
from agents.refine_pipeline import PipelineConfig, run as run_pipeline
from agents.resource_access import get_owned_resource
from common.models import BizException
from common.utils.logger import get_logger
from infra.db import User

logger = get_logger(__name__)

# 大纲 4 步流水线配置（分析 → 生成 → 事实核查 → 再优化）
OUTLINE_PIPELINE = PipelineConfig(doc_type="教学大纲", generate_prompt_key="outline")


async def stream(
    db: AsyncSession,
    params: OutlineGenerateParams,
    actor: User,
) -> AsyncIterator[Any]:
    """流式生成教学大纲的接口。"""
    previous_content = (params.previous_content or "").strip()
    if not previous_content and params.resource_id:
        resource = await get_owned_resource(db, params.resource_id, actor.id)
        if resource:
            previous_content = (resource.content or "").strip()

    if previous_content:
        task_description = (
            "分析用户提示，定位原教学大纲中的相关内容，"
            "对原教学大纲作必要修改（修改内容严格以用户提示为准，禁止过度修改）。"
        )
        reference_content = f"原教学大纲内容：\n\n{previous_content}"
    else:
        if not params.outline_form:
            logger.warning("[outline] 表单数据不能为空")
            raise BizException("表单数据不能为空")
        data = params.outline_form.model_dump()
        task_description = (
            "根据表单数据生成高质量教学大纲。"
            "你必须使用以下真实字段值进行写作，"
            "禁止输出任何花括号占位符（如 {{course_name}}、{{hours}}、{{100 - offline_score_ratio}}）。"
        )
        reference_content = (
            f"- 课程名称：{data.get('course_name')}\n"
            f"- 课程性质：{data.get('course_nature')}\n"
            f"- 课程类别：{data.get('course_category')}\n"
            f"- 学分：{data.get('credits')}\n"
            f"- 学时：{data.get('hours')}\n"
            f"- 授课对象专业：{data.get('target_major')}\n"
            f"- 授课对象年级：{data.get('target_grade')}\n"
            f"- 授课方式：{data.get('teaching_method')}\n"
            f"- 线下学时占比：{data.get('offline_hours_ratio')}%\n"
            f"- 线下成绩占比：{data.get('offline_score_ratio')}%\n"
            f"- 线上成绩占比：{100 - int(data.get('offline_score_ratio') or 0)}%\n"
            f"- 预修要求：{data.get('prerequisites')}\n"
            f"- 课程介绍：{data.get('course_introduction')}\n"
            f"- 教学目标：{data.get('teaching_objectives')}\n"
            f"- 思政内容：{data.get('ideological_political')}\n"
            f"- 章节结构：{data.get('chapter_structure')}"
        )

    user_prompt = params.prompt or ""
    if params.selected_text:
        user_prompt = f"用户选中的文本：{params.selected_text}\n\n{user_prompt}"
    async for event in run_pipeline(
        OUTLINE_PIPELINE,
        task_description=task_description,
        reference_content=reference_content,
        user_prompt=user_prompt,
    ):
        yield event
