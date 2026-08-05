"""联网资料搜索的 provider 与合规抓取门。

沿用仓库既有的 Exa provider（`question_search.ExaQuestionSearch` 已在题库链使用），
不引入第二家搜索服务。本模块只负责"取回候选并判定能不能用"，
不生成资料真源——落库统一走 `material_pipeline`。
"""

from __future__ import annotations

import asyncio
import hashlib
import html
import re
import time
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from web_search_config import WebSearchPolicy

SearchCallable = Callable[..., Awaitable[list[dict[str, Any]]]]

# 与 question_search 一致的注入防护：抓来的正文是不可信数据，不是指令。
_UNTRUSTED_INSTRUCTION_PATTERNS = (
    re.compile(r"ignore\s+(?:all\s+)?previous\s+instructions?[^。.!?\n]*[。.!?]?", re.IGNORECASE),
    re.compile(r"(?:system|developer)\s+message\s*:[^\n]*", re.IGNORECASE),
    re.compile(r"(?:new|updated)\s+instructions?\s*:[^\n]*", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(?:a|an)\s+[^\n。.!?]{0,80}[。.!?]?", re.IGNORECASE),
    re.compile(r"忽略(?:此前|之前|以上|全部)?(?:的)?指令[^。！？\n]*[。！？]?", re.IGNORECASE),
    re.compile(r"(?:以下|下列)(?:是)?新(?:的)?(?:系统)?指令[^。！？\n]*[。！？]?", re.IGNORECASE),
)

# 付费墙 / 登录墙信号：命中则不采用，避免绕过鉴权取内容。
_PAYWALL_PATTERNS = (
    re.compile(r"\b(?:subscribe|subscription)\s+to\s+(?:read|continue|view)\b", re.IGNORECASE),
    re.compile(r"\bsign\s+in\s+to\s+(?:read|continue|view)\b", re.IGNORECASE),
    re.compile(r"\b(?:members?|paid\s+subscribers?)\s+only\b", re.IGNORECASE),
    re.compile(r"\bthis\s+(?:article|content)\s+is\s+for\s+subscribers\b", re.IGNORECASE),
    re.compile(r"(?:登录|注册|订阅|开通会员|付费)后(?:才能|方可|即可)?(?:继续)?(?:阅读|查看|观看)"),
    re.compile(r"(?:仅|只)(?:限|供)(?:会员|订阅用户|付费用户)"),
)

_OPEN_LICENSE_PATTERN = re.compile(
    r"\b(?:cc[- ]?by(?:[- ]?sa|[- ]?nc)?|creative\s+commons|public\s+domain|"
    r"cc0|oer|open\s+educational|gfdl|mit\s+license|apache\s+license)\b",
    re.IGNORECASE,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sanitize_untrusted_text(value: str, *, max_chars: int) -> str:
    """把抓来的正文降级为纯数据：去标签、去注入话术、去不可打印字符。"""
    text = html.unescape(str(value or ""))
    text = re.sub(r"(?is)<(script|style|iframe|object|template|noscript)[^>]*>.*?</\1>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    for pattern in _UNTRUSTED_INSTRUCTION_PATTERNS:
        text = pattern.sub(" ", text)
    text = "".join(ch for ch in text if ch.isprintable() or ch in "\n\t")
    return re.sub(r"[ \t]+", " ", text).strip()[: max(0, int(max_chars))]


def looks_paywalled(text: str) -> bool:
    return any(pattern.search(text or "") for pattern in _PAYWALL_PATTERNS)


def detect_open_license(*values: str) -> bool:
    return bool(_OPEN_LICENSE_PATTERN.search(" ".join(str(v or "") for v in values)))


def safe_query_term(value: str) -> str:
    """查询词只保留安全字符，避免把用户/模型文本原样拼进外部请求。"""
    text = re.sub(r"[\r\n\t]+", " ", str(value or ""))
    text = re.sub(r"[^\w㐀-鿿 .,+\-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()[:200]


class RobotsGate:
    """按域缓存 robots.txt 判定。取不到 robots 时按站点未禁止处理。"""

    def __init__(
        self,
        *,
        timeout_seconds: float = 6.0,
        user_agent: str = "LingzhiCourseBot",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent
        self._client = client
        self._cache: dict[str, RobotFileParser | None] = {}

    async def allows(self, url: str) -> tuple[bool, str]:
        parsed = urlparse(str(url or ""))
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return False, "invalid_url"
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self._cache:
            self._cache[origin] = await self._load(origin)
        parser = self._cache[origin]
        if parser is None:
            # robots 不可达或不存在：不视为禁止，但也不提升可信度。
            return True, "robots_unavailable"
        try:
            allowed = parser.can_fetch(self.user_agent, url)
        except Exception:
            return True, "robots_unparsed"
        return (True, "robots_allowed") if allowed else (False, "robots_disallowed")

    async def _load(self, origin: str) -> RobotFileParser | None:
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self.timeout_seconds)
        try:
            response = await client.get(
                f"{origin}/robots.txt",
                headers={"user-agent": self.user_agent},
            )
        except httpx.HTTPError:
            return None
        finally:
            if owns_client:
                await client.aclose()
        if response.status_code >= 400:
            return None
        parser = RobotFileParser()
        try:
            parser.parse(response.text.splitlines())
        except Exception:
            return None
        return parser


class RateLimiter:
    """同一进程内的最小请求间隔，避免高频抓取目标站点。"""

    def __init__(self, min_interval_seconds: float, *, sleep: Callable[[float], Awaitable[None]] | None = None) -> None:
        self.min_interval_seconds = max(0.0, float(min_interval_seconds))
        self._sleep = sleep or asyncio.sleep
        self._last_at: float | None = None

    async def wait(self, *, now: Callable[[], float] = time.monotonic) -> None:
        if self.min_interval_seconds <= 0:
            return
        current = now()
        if self._last_at is not None:
            remaining = self.min_interval_seconds - (current - self._last_at)
            if remaining > 0:
                await self._sleep(remaining)
                current = now()
        self._last_at = current


class WebMaterialSearch:
    """联网资料候选检索。

    复用既有 Exa provider；未配置 key 时 `configured` 为 False，
    调用方据此走降级路径，而不是伪造结果。
    """

    def __init__(
        self,
        *,
        policy: WebSearchPolicy,
        search: SearchCallable | None = None,
        robots_gate: RobotsGate | None = None,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        self.policy = policy
        self._injected_search = search
        self._provider = None
        if search is None:
            from question_search import ExaQuestionSearch

            self._provider = ExaQuestionSearch(timeout_seconds=policy.timeout_seconds)
        self._robots = robots_gate if robots_gate is not None else (
            RobotsGate(timeout_seconds=min(6.0, policy.timeout_seconds))
            if policy.respect_robots
            else None
        )
        self._limiter = rate_limiter or RateLimiter(policy.min_request_interval_seconds)

    @property
    def configured(self) -> bool:
        if self._injected_search is not None:
            return True
        return bool(self._provider and self._provider.configured)

    async def _search_once(self, query: str) -> list[dict[str, Any]]:
        search_fn = self._injected_search or (self._provider.search if self._provider else None)
        if search_fn is None:
            return []
        results = await search_fn(query, num_results=self.policy.max_results_per_query)
        return [item for item in results or [] if isinstance(item, dict)]

    async def search(self, query: str) -> list[dict[str, Any]]:
        """单条查询，带有界重试。任何异常都降级为空结果，不向上抛断生成流程。"""
        attempts = self.policy.max_retries + 1
        for attempt in range(attempts):
            await self._limiter.wait()
            try:
                return await self._search_once(query)
            except (httpx.HTTPError, ValueError, asyncio.TimeoutError):
                if attempt >= attempts - 1:
                    return []
            except Exception:
                return []
        return []

    async def candidate_verdict(self, url: str, text: str) -> tuple[bool, str]:
        """域名 + robots + 付费墙三道门，返回 (可用, 原因代码)。"""
        allowed, reason = self.policy.domain_verdict(url)
        if not allowed:
            return False, reason
        if looks_paywalled(text):
            return False, "paywalled_or_login_required"
        if self._robots is not None:
            robots_ok, robots_reason = await self._robots.allows(url)
            if not robots_ok:
                return False, robots_reason
        return True, "accepted"


def content_hash(text: str) -> str:
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()


__all__ = [
    "RateLimiter",
    "RobotsGate",
    "SearchCallable",
    "WebMaterialSearch",
    "content_hash",
    "detect_open_license",
    "looks_paywalled",
    "safe_query_term",
    "sanitize_untrusted_text",
]
