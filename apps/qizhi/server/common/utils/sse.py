import json
from collections.abc import AsyncIterator
from enum import Enum
from typing import Any, TypedDict

from common.models import BizException


def build_sse_response(event: SseEventEnum, data: str | dict[str, Any] | None = None) -> SseResponse:
    if data is None:
        data = {}
    return SseResponse(
        event=event,
        data=data if isinstance(data, str) else json.dumps(data, ensure_ascii=False),
    )

async def safe_sse_stream(stream: AsyncIterator[SseResponse]) -> AsyncIterator[SseResponse]:
    """捕获异常并 yield 错误事件"""
    try:
        async for chunk in stream:
            yield chunk
    except BizException as e:
        yield build_sse_response(SseEventEnum.ERROR, {"error": e.error})
    except Exception as e:
        yield build_sse_response(SseEventEnum.ERROR, {"error": str(e)})


class SseEventEnum(str, Enum):
    """
    SSE 事件枚举
    """
    START = "start"
    END = "end"
    LOADING = "loading"
    THINKING = "thinking"
    MESSAGE = "message"
    PLAN = "plan"
    CARD = "card"
    ERROR = "error"
    # 导出进度
    EXPORT_PROGRESS = "export_progress"
    EXPORT_GENERATING = "export_generating"
    EXPORT_COMPLETE = "export_complete"


class SseResponse(TypedDict):
    """
    SSE 响应
    """
    event: SseEventEnum
    data: str
