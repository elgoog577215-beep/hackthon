from starlette.types import ASGIApp, Message, Receive, Scope, Send


class CORSMiddleware:
    """轻量 CORS 中间件，使用原始 ASGI 不阻塞流式响应。

    替代 fastapi.middleware.cors.CORSMiddleware（基于 BaseHTTPMiddleware，
    其 call_next 会缓冲整个 SSE 流导致流式接口失效）。

    当前配置：允许所有来源（allow_origins=["*"]）。
    """

    CORS_HEADERS = [
        (b"access-control-allow-origin", b"*"),
        (b"access-control-allow-credentials", b"false"),
        (b"access-control-allow-methods", b"*"),
        (b"access-control-allow-headers", b"*"),
        (b"access-control-expose-headers", b"*"),
    ]

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # 处理 CORS 预检请求
        if scope.get("method") == "OPTIONS":
            await send({"type": "http.response.start", "status": 200, "headers": self.CORS_HEADERS})
            await send({"type": "http.response.body", "body": b""})
            return

        # 正常请求：包装 send 添加 CORS 头
        async def send_with_cors(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend(self.CORS_HEADERS)
                await send({"type": "http.response.start", "status": message.get("status", 200), "headers": headers})
            else:
                await send(message)

        await self.app(scope, receive, send_with_cors)
