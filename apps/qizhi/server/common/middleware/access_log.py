import json
import time
import uuid
import asyncio

from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from common.utils.http import get_client_ip
from common.utils.logger import log_access, set_request_id

# 不记录 body 的内容类型（文件上传等）
SKIP_BODY_TYPES = {"multipart/form-data", "application/octet-stream"}
MAX_BODY_LEN = 65536  # 最多记录 64KB（流式响应可能较大）

# 不记录日志的路径前缀
SKIP_PATHS = ["/static", "/health", "/docs", "/openapi.json", "/redoc"]


def _safe_decode(raw: bytes) -> str:
    try:
        return raw[:MAX_BODY_LEN].decode("utf-8", errors="replace")
    except Exception:
        return ""


def _extract_sse_fields(chunk: bytes, session_id_buf: list[str], content_buf: list[str]) -> None:
    """从 SSE chunk 中提取 session_id 和 content。"""
    try:
        text = chunk.decode("utf-8", errors="replace")
    except Exception:
        return

    # SSE 格式：data: {"session_id": "xxx"} 或 data: {"content": "xxx"}
    for line in text.split("\n"):
        line = line.strip()
        if not line.startswith("data:"):
            continue
        try:
            obj = json.loads(line[5:].strip())
            if isinstance(obj, dict):
                sid = obj.get("session_id")
                if sid and not session_id_buf:
                    session_id_buf.append(str(sid))
                content = obj.get("content")
                if content:
                    content_buf.append(str(content))
        except (json.JSONDecodeError, ValueError):
            pass


class AccessLogMiddleware:
    """API 访问日志中间件。

    使用原生 ASGI 中间件而非 BaseHTTPMiddleware，
    因为 BaseHTTPMiddleware 的 call_next 会消费整个响应流，
    导致 SSE/流式接口失效。

    对于 SSE 流式响应，逐 chunk 累积响应体，日志只记录截断后的前 64KB。
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)

        # 跳过静态文件和健康检查
        is_skip = any(request.url.path.startswith(p) for p in SKIP_PATHS)

        # 生成 request_id
        request_id = request.headers.get("X-Request-Id", str(uuid.uuid4()))

        # 用 queue 缓冲 receive 消息，避免 consume 冲突
        queue: asyncio.Queue[Message] = asyncio.Queue()
        raw_body = b""
        content_type = request.headers.get("content-type", "")
        skip_body = any(ct in content_type for ct in SKIP_BODY_TYPES)

        # 先 drain 原始 receive，获取全部消息
        while True:
            msg = await receive()
            await queue.put(msg)
            raw_body += msg.get("body", b"")
            if not msg.get("more_body", False):
                break

        body = _safe_decode(raw_body) if raw_body and not skip_body else ""

        # 构造新的 receive：从 queue 取消息
        async def new_receive() -> Message:
            return await queue.get()

        start_time = time.perf_counter()
        token = set_request_id(request_id)

        # 包装 send，拦截响应状态码并注入 X-Request-Id
        status_code = 0
        session_id_parts: list[str] = []
        content_parts: list[str] = []

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 0)
                # 注入 X-Request-Id 响应头
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode()))
                await send({"type": "http.response.start", "status": status_code, "headers": headers})
            elif message["type"] == "http.response.body":
                chunk = message.get("body", b"")
                # 从 SSE chunk 中提取 session_id 和 content
                _extract_sse_fields(chunk, session_id_parts, content_parts)
                await send(message)

        try:
            await self.app(scope, new_receive, send_wrapper)
        finally:
            set_request_id(None, token)

        if is_skip:
            return

        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 1)
        client_ip = get_client_ip(request)
        query_params = str(request.url.query) if request.url.query else ""

        # 拼接：有 session_id 记录 session_id，其余拼接 content
        resp_parts = []
        if session_id_parts:
            resp_parts.append(f"session_id={session_id_parts[0]}")
        if content_parts:
            resp_parts.append("".join(content_parts))
        resp_body = "".join(resp_parts) if resp_parts else _safe_decode(raw_body) if raw_body else ""

        log_access(
            method=request.method,
            path=request.url.path,
            query_params=query_params,
            request_body=body,
            status_code=status_code,
            response_body=resp_body,
            elapsed_ms=elapsed_ms,
            client_ip=client_ip,
            request_id=request_id,
        )
