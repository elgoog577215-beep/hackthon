# =============================================================================
# 轻量级内存速率限制器
# 基于滑动窗口算法，无外部依赖。
# 适用于单进程部署（Uvicorn 单 worker）。
# =============================================================================

import time
import threading
import logging
import re
from collections import defaultdict
from typing import Dict, Tuple
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response, JSONResponse

logger = logging.getLogger(__name__)


class SlidingWindowCounter:
    """滑动窗口计数器"""

    def __init__(self):
        self._lock = threading.Lock()
        # key -> (window_start, count)
        self._windows: Dict[str, Tuple[float, int]] = {}

    def is_allowed(self, key: str, max_requests: int, window_seconds: int) -> bool:
        now = time.time()
        with self._lock:
            if key in self._windows:
                window_start, count = self._windows[key]
                if now - window_start < window_seconds:
                    if count >= max_requests:
                        return False
                    self._windows[key] = (window_start, count + 1)
                    return True
                else:
                    # 窗口过期，重置
                    self._windows[key] = (now, 1)
                    return True
            else:
                self._windows[key] = (now, 1)
                return True

    def cleanup(self, max_age: int = 300):
        """清理过期条目，防止内存泄漏"""
        now = time.time()
        with self._lock:
            expired = [k for k, (t, _) in self._windows.items() if now - t > max_age]
            for k in expired:
                del self._windows[k]


# 全局计数器实例
_counter = SlidingWindowCounter()

# 速率限制配置：路径前缀 -> (max_requests, window_seconds)
# AI 相关端点更严格，普通读取端点更宽松
RATE_LIMITS = {
    # AI 生成类（昂贵操作）
    "/api/course-generation/generate": (3, 60),
    "/api/execute": (10, 60),
    "/api/ask_events": (20, 60),
    "/api/diagram": (10, 60),
    "/api/courses/": (30, 60),     # 课程 CRUD
    # 默认
    "_default": (60, 60),
}
QUESTION_BANK_REBUILD_STATUS_RE = re.compile(
    r"^/api/courses/[^/]+/question-bank/rebuilds/[^/]+$"
)


def _get_client_ip(request: Request) -> str:
    """获取客户端 IP，支持反向代理"""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _match_rate_limit(
    path: str,
    method: str = "",
) -> Tuple[int, int]:
    """根据路径匹配速率限制规则"""
    if (
        method.upper() == "GET"
        and QUESTION_BANK_REBUILD_STATUS_RE.fullmatch(path)
    ):
        return 120, 60
    # 实时审阅工作台只读取已经落盘的生成检查点。它需要短间隔轮询，
    # 但不会触发 AI 生成或写入正式课程，因此与课程 CRUD 分开限流。
    if path.startswith("/api/courses/") and path.endswith("/evolution/progress"):
        return 120, 60
    for prefix, limits in RATE_LIMITS.items():
        if prefix.startswith("/") and path.startswith(prefix):
            return limits
    return RATE_LIMITS["_default"]


class RateLimitMiddleware(BaseHTTPMiddleware):
    """速率限制中间件"""

    _cleanup_counter = 0

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # 跳过健康检查和静态资源
        path = request.url.path
        if path in ("/health", "/api/health") or not path.startswith("/api"):
            return await call_next(request)

        client_ip = _get_client_ip(request)
        max_requests, window = _match_rate_limit(
            path,
            request.method,
        )
        key = f"{client_ip}:{path}"

        if not _counter.is_allowed(key, max_requests, window):
            logger.warning(f"Rate limit exceeded: {client_ip} on {path}")
            return JSONResponse(
                status_code=429,
                content={"detail": "请求过于频繁，请稍后再试"},
                headers={"Retry-After": str(window)},
            )

        # 定期清理（每 100 次请求）
        RateLimitMiddleware._cleanup_counter += 1
        if RateLimitMiddleware._cleanup_counter % 100 == 0:
            _counter.cleanup()

        return await call_next(request)
