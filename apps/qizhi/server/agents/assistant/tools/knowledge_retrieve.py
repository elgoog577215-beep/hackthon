from __future__ import annotations

import logging

from alibabacloud_bailian20231229 import models as bailian_models
from alibabacloud_bailian20231229.client import Client as BailianClient
from alibabacloud_credentials.models import Config as CredentialConfig
from alibabacloud_credentials.client import Client as CredentialClient
from alibabacloud_tea_openapi import models as open_api_models
from darabonba.runtime import RuntimeOptions

from agents.assistant.context import Context
from agents.assistant.tools.registry import tool_registry
from common.config import settings
from common.models import BizException
from common.utils.logger import get_logger

logger = get_logger(__name__)


def _create_bailian_client() -> BailianClient:
    """创建百炼客户端"""
    credential = CredentialClient(CredentialConfig(
        access_key_id=settings.ALIBABA_CLOUD_ACCESS_KEY_ID,
        access_key_secret=settings.ALIBABA_CLOUD_ACCESS_KEY_SECRET,
        type="access_key",
    ))
    config = open_api_models.Config(
        credential=credential,
        endpoint="bailian.cn-beijing.aliyuncs.com",
    )
    return BailianClient(config)


@tool_registry.register(
    description="检索知识库，获取相关文档内容。用于查询全国高校青年教师教学竞赛(青教赛)或全国高校教师教学创新大赛(教创赛)的相关赛事信息，为用户提供备赛咨询。",
    loading_message="正在检索知识库...",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "检索查询文本",
            }
        },
        "required": ["query"],
    },
)
async def knowledge_retrieve(payload: dict, context: Context) -> str:
    """调用阿里云百炼知识库检索，返回相关文档内容。"""

    query = payload.get("query", "").strip()
    if not query:
        logger.warning(f"[knowledge_retrieve.py] 知识库检索缺少 query 参数")
        raise BizException("知识库检索缺少 query 参数")

    try:
        client = _create_bailian_client()

        request = bailian_models.RetrieveRequest(
            index_id=settings.KNOWLEDGEBASE_ID,
            query=query,
            rerank_min_score=0.4
        )


        response = client.retrieve_with_options(settings.WORKSPACE_ID, request, {}, RuntimeOptions())

        if response.status_code != 200 or not response.body:
            print("bailian retrieve failed: ", response)
            logger.warning(f"[knowledge_retrieve.py] 知识库检索失败")
            raise BizException("知识库检索失败")

        results = response.body.data.nodes or []
        if not results:
            return "未找到相关内容"

        texts = []
        for node in results:
            if node.text:
                texts.append(node.text)

        return "\n\n".join(texts)

    except Exception as e:
        logger.error("bailian retrieve error: %s", str(e))
        logger.warning(f"[knowledge_retrieve.py] 知识库检索异常: {str(e)}")
        raise BizException(f"知识库检索异常: {str(e)}")
