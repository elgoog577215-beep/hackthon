import json
import logging
from collections.abc import AsyncIterator
from enum import Enum
from typing import TYPE_CHECKING, Any

import httpx
from starlette.requests import Request

from common.models import BizException, SystemException
from common.models.constants import (
    ACTOR_HEADER_ID,
    ACTOR_HEADER_ROLE,
    ACTOR_HEADER_ZJU_ID,
    DEFAULT_HTTP_CHUNK_SIZE,
    DEFAULT_HTTP_TIMEOUT,
)
from common.utils.logger import get_logger

if TYPE_CHECKING:  # 避免运行时循环依赖；仅类型注解需要
    from infra.db import User

logger = get_logger(__name__)


def actor_headers(user: "User | None") -> dict[str, str]:
    """生成调用外部插件 / 智能体时透传的身份头。

    协议参考 docs/audit-reporting.md：插件侧收到这些头即可识别"代表哪个用户做的"，
    在回调 /audit/report 时把这组值塞进 on_behalf_of_* 字段。

    注意：只透传 ASCII 安全的字段（id / role / zju_id）。姓名等可能含中文的可读标识
    不放进 HTTP 头（头值须 Latin-1 编码，中文会抛 UnicodeEncodeError），审计端按 id 反查即可。
    """
    if user is None:
        return {}
    return {
        ACTOR_HEADER_ID: user.id,
        ACTOR_HEADER_ROLE: user.role or "",
        ACTOR_HEADER_ZJU_ID: user.zju_id or "",
    }


def get_client_ip(request: Request) -> str:
    """提取请求方真实 IP。

    顺序：X-Forwarded-For 首段 → X-Real-IP → socket 对端 → "unknown"。
    生产部署一层反代，不做信任链多跳校验。
    """
    xff = request.headers.get("X-Forwarded-For") or request.headers.get("x-forwarded-for")
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first
    real_ip = request.headers.get("X-Real-IP") or request.headers.get("x-real-ip")
    if real_ip:
        stripped = real_ip.strip()
        if stripped:
            return stripped
    return request.client.host if request.client else "unknown"


async def http_request(
    method: HTTPMethodEnum,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    files: dict[str, Any] | None = None,
    timeout: float = DEFAULT_HTTP_TIMEOUT,
) -> dict[str, Any] | list[Any]:
    """
    发送 HTTP 请求，返回响应 JSON
    """
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            kwargs: dict[str, Any] = {"headers": headers or {}}
            if params:
                kwargs["params"] = params
            if body:
                kwargs["json"] = body
            if data:
                kwargs["data"] = data
            if files:
                kwargs["files"] = files
            response = await client.request(method.value, url, **kwargs)
            response.raise_for_status()
            return response.json()
    except httpx.TimeoutException:
        logger.error(f"[http.py] 请求超时: {url}")
        raise SystemException(f"请求超时: {url}")
    except Exception as e:
        logger.error(f"[http.py] 请求异常: {url} - {e}")
        raise SystemException(f"请求异常: {url} - {e}")


async def stream_sse(
    method: HTTPMethodEnum,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    files: dict[str, Any] | None = None,
    timeout: float = DEFAULT_HTTP_TIMEOUT,
) -> AsyncIterator[tuple[str | None, Any]]:
    """
    发送 HTTP 请求，流式读取 SSE 响应，按 (event, data) 逐条 yield
    """
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            kwargs: dict[str, Any] = {"headers": headers or {}}
            if params:
                kwargs["params"] = params
            if body:
                kwargs["json"] = body
            if data:
                kwargs["data"] = data
            if files:
                kwargs["files"] = files
            async with client.stream(method.value, url, **kwargs) as response:
                response.raise_for_status()
                event = None
                async for line in response.aiter_lines():
                    line = line.strip()

                    # 处理事件
                    if line.startswith("event:"):
                        event = line[6:].strip() or None
                        continue

                    # 处理数据
                    if line.startswith("data:"):
                        data = json.loads(line[5:].strip())
                        yield event, data
                        event = None

    except httpx.TimeoutException:
        logger.error(f"[http.py] 请求超时: {url}")
        raise SystemException(f"请求超时: {url}")
    except Exception as e:
        logger.error(f"[http.py] 请求异常: {url} - {e}")
        raise SystemException(f"请求异常: {url} - {e}")


async def stream_bytes(
    method: HTTPMethodEnum,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    files: dict[str, Any] | None = None,
    timeout: float = DEFAULT_HTTP_TIMEOUT,
    chunk_size: int = DEFAULT_HTTP_CHUNK_SIZE,
) -> AsyncIterator[tuple[bytes, int | None]]:
    """
    发送 HTTP 请求，按字节块流式返回响应体。

    每次 yield: (chunk, total_size)
    - chunk: 当前分片字节内容
    - total_size: 响应头 content-length（若无则为 None）
    """
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            kwargs: dict[str, Any] = {"headers": headers or {}}
            if params:
                kwargs["params"] = params
            if body:
                kwargs["json"] = body
            if data:
                kwargs["data"] = data
            if files:
                kwargs["files"] = files
            async with client.stream(method.value, url, follow_redirects=True, **kwargs) as response:
                response.raise_for_status()
                total: int | None = None
                content_length = response.headers.get("content-length")
                if content_length and content_length.isdigit():
                    total = int(content_length)

                async for chunk in response.aiter_bytes(chunk_size):
                    if chunk:
                        yield chunk, total
    except httpx.TimeoutException:
        logger.error(f"[http.py] 请求超时: {url}")
        raise SystemException(f"请求超时: {url}")
    except Exception as e:
        logger.error(f"[http.py] 请求异常: {url} - {e}")
        raise SystemException(f"请求异常: {url} - {e}")


class HTTPMethodEnum(str, Enum):
    """
    HTTP 方法枚举
    """
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
