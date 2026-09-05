from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from agents.llm import stream_chat
from agents.prompt_manager import PromptManager
from agents.question_bank.models import QuestionBankGenerateParams
from agents.resource_access import get_owned_resource
from common.models import BizException, SystemException
from common.utils.logger import get_logger
from infra.db import User
from service.resource import ResourceTypeEnum

logger = get_logger(__name__)


async def stream(
    db: AsyncSession,
    params: QuestionBankGenerateParams,
    actor: User,
) -> AsyncIterator[str]:
    """流式生成习题集的接口。"""
    teaching_plan_content = ""
    previous_content = ""
    if params.resource_id:
        resource = await get_owned_resource(db, params.resource_id, actor.id)
        if resource:
            previous_content = resource.content or ""
    else:
        if not params.source_resource_id:
            raise BizException("生成习题集需要指定当前资源或源资源（教案）")
        source_resource = await get_owned_resource(db, params.source_resource_id, actor.id)
        if not source_resource:
            raise SystemException(f"源资源不存在: {params.source_resource_id}")
        if source_resource.resource_type != ResourceTypeEnum.TEACHING_PLAN:
            raise BizException(f"源资源不是教案: {params.source_resource_id}")
        teaching_plan_content = source_resource.content or ""

    if previous_content:
        task_description = (
            "分析用户提示，定位原习题集中的相关内容，"
            "对原习题集作必要修改（修改内容严格以用户提示为准，禁止过度修改）。"
        )
        reference_content = f"原习题集内容：\n\n{previous_content}"
    else:
        if not teaching_plan_content:
            logger.warning("[question_bank] 教案内容不能为空")
            raise BizException("教案内容不能为空")
        task_description = "根据教案生成高质量习题集。"
        reference_content = f"教案内容：\n\n{teaching_plan_content}"
        if params.question_bank_form:
            form_data = params.question_bank_form.model_dump()
            reference_content += (
                f"\n\n表单要求：\n"
                f"- 题型：{', '.join(form_data.get('question_types') or [])}\n"
                f"- 难度：{form_data.get('difficulty') or '不限'}\n"
                f"- 题目数量：{form_data.get('count') or '不限'}"
            )

    system_prompt = PromptManager.get_prompt(
        "question_bank",
        task_description=task_description,
        reference_content=reference_content,
    )
    user_prompt = params.prompt or ""
    if params.selected_text:
        user_prompt = f"用户选中的文本：{params.selected_text}\n\n{user_prompt}"
    async for chunk in stream_chat(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    ):
        yield chunk
