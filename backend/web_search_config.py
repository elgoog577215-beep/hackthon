"""联网资料搜索的策略与开关。

联网是敏感能力：默认关闭，必须由显式配置或教师请求打开。本模块只负责
"允许不允许、允许到什么程度"，不负责发请求，也不拥有资料真源。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from typing import Any
from urllib.parse import urlparse

# 保守默认值：联网默认关闭；打开后也限制查询数、结果数、超时和重试。
DEFAULT_ENABLED = False
DEFAULT_MAX_QUERIES = 4
DEFAULT_MAX_RESULTS_PER_QUERY = 3
DEFAULT_MAX_SOURCES = 8
DEFAULT_TIMEOUT_SECONDS = 12.0
DEFAULT_MAX_RETRIES = 1
DEFAULT_MIN_REQUEST_INTERVAL_SECONDS = 1.0
DEFAULT_MAX_SOURCE_CHARS = 8000
DEFAULT_RESPECT_ROBOTS = True

# 默认黑名单：登录墙、付费墙、社交平台和明确禁止抓取的站点不作为教学资料来源。
DEFAULT_DENY_DOMAINS = (
    "facebook.com",
    "instagram.com",
    "x.com",
    "twitter.com",
    "linkedin.com",
    "weibo.com",
    "zhihu.com",
    "xiaohongshu.com",
    "douban.com",
    "csdn.net",
    "scholar.google.com",
    "sci-hub.se",
    "chegg.com",
    "coursehero.com",
    "brainly.com",
    "doc88.com",
    "docin.com",
    "wenku.baidu.com",
)

# 明确不作为"事实来源"的低可信域名后缀/站点，仍可作为背景参考。
LOW_TRUST_DOMAINS = (
    "blogspot.com",
    "wordpress.com",
    "medium.com",
    "quora.com",
    "reddit.com",
    "answers.com",
)

# 高可信来源：教育与政府机构、标准组织和公开课平台。
HIGH_TRUST_SUFFIXES = (
    ".edu",
    ".edu.cn",
    ".ac.uk",
    ".ac.jp",
    ".gov",
    ".gov.cn",
    ".int",
)
HIGH_TRUST_DOMAINS = (
    "wikipedia.org",
    "britannica.com",
    "nature.com",
    "science.org",
    "ieee.org",
    "acm.org",
    "arxiv.org",
    "who.int",
    "unesco.org",
    "oercommons.org",
    "openstax.org",
    "khanacademy.org",
    "mit.edu",
    "python.org",
    "developer.mozilla.org",
)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return max(minimum, min(maximum, int(raw.strip())))
    except ValueError:
        return default


def _env_float(name: str, default: float, *, minimum: float, maximum: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return max(minimum, min(maximum, float(raw.strip())))
    except ValueError:
        return default


def _env_domains(name: str) -> tuple[str, ...]:
    raw = os.getenv(name) or ""
    items = [normalize_domain(part) for part in raw.replace(";", ",").split(",")]
    return tuple(item for item in items if item)


def normalize_domain(value: str) -> str:
    """把域名或 URL 归一化为小写 host，去掉端口、用户信息和前导 www."""
    text = str(value or "").strip().lower()
    if not text:
        return ""
    if "//" in text:
        text = urlparse(text).netloc or text.split("//", 1)[1]
    text = text.split("/", 1)[0].split("@")[-1].split(":", 1)[0].strip(". ")
    if text.startswith("www."):
        text = text[4:]
    return text


def domain_matches(host: str, pattern: str) -> bool:
    """host 命中 pattern 本身或其子域。"""
    host = normalize_domain(host)
    pattern = normalize_domain(pattern)
    if not host or not pattern:
        return False
    return host == pattern or host.endswith("." + pattern)


@dataclass(frozen=True)
class WebSearchPolicy:
    """一次联网搜索允许的边界。所有字段都有保守默认值。"""

    enabled: bool = DEFAULT_ENABLED
    max_queries: int = DEFAULT_MAX_QUERIES
    max_results_per_query: int = DEFAULT_MAX_RESULTS_PER_QUERY
    max_sources: int = DEFAULT_MAX_SOURCES
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_retries: int = DEFAULT_MAX_RETRIES
    min_request_interval_seconds: float = DEFAULT_MIN_REQUEST_INTERVAL_SECONDS
    max_source_chars: int = DEFAULT_MAX_SOURCE_CHARS
    respect_robots: bool = DEFAULT_RESPECT_ROBOTS
    allow_domains: tuple[str, ...] = ()
    deny_domains: tuple[str, ...] = field(default=DEFAULT_DENY_DOMAINS)
    # 教师逐条剔除的具体 URL。域名级黑名单太粗，教师常常只想去掉某一条。
    excluded_urls: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        # 无论从环境、请求还是直接构造进来，剔除名单都按同一套归一化存放，
        # 否则末尾斜杠或大小写差异会让教师点掉的那条又回到候选里。
        object.__setattr__(self, "excluded_urls", _coerce_urls(self.excluded_urls))

    @classmethod
    def from_env(cls) -> "WebSearchPolicy":
        deny = _env_domains("WEB_SEARCH_DENY_DOMAINS")
        return cls(
            enabled=_env_bool("WEB_SEARCH_ENABLED", DEFAULT_ENABLED),
            max_queries=_env_int("WEB_SEARCH_MAX_QUERIES", DEFAULT_MAX_QUERIES, minimum=1, maximum=12),
            max_results_per_query=_env_int(
                "WEB_SEARCH_MAX_RESULTS_PER_QUERY",
                DEFAULT_MAX_RESULTS_PER_QUERY,
                minimum=1,
                maximum=8,
            ),
            max_sources=_env_int("WEB_SEARCH_MAX_SOURCES", DEFAULT_MAX_SOURCES, minimum=1, maximum=32),
            timeout_seconds=_env_float(
                "WEB_SEARCH_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS, minimum=1.0, maximum=60.0
            ),
            max_retries=_env_int("WEB_SEARCH_MAX_RETRIES", DEFAULT_MAX_RETRIES, minimum=0, maximum=3),
            min_request_interval_seconds=_env_float(
                "WEB_SEARCH_MIN_REQUEST_INTERVAL_SECONDS",
                DEFAULT_MIN_REQUEST_INTERVAL_SECONDS,
                minimum=0.0,
                maximum=30.0,
            ),
            max_source_chars=_env_int(
                "WEB_SEARCH_MAX_SOURCE_CHARS", DEFAULT_MAX_SOURCE_CHARS, minimum=500, maximum=40000
            ),
            respect_robots=_env_bool("WEB_SEARCH_RESPECT_ROBOTS", DEFAULT_RESPECT_ROBOTS),
            allow_domains=_env_domains("WEB_SEARCH_ALLOW_DOMAINS"),
            deny_domains=deny or DEFAULT_DENY_DOMAINS,
        )

    def domain_verdict(self, url: str) -> tuple[bool, str]:
        """判断 URL 是否允许作为资料来源，返回 (允许, 原因代码)。"""
        parsed = urlparse(str(url or "").strip())
        if parsed.scheme not in {"http", "https"}:
            return False, "unsupported_scheme"
        host = normalize_domain(parsed.netloc)
        if not host or "." not in host:
            return False, "invalid_host"
        if self.excluded_urls and _canonical_url(url) in self.excluded_urls:
            return False, "excluded_by_teacher"
        for pattern in self.deny_domains:
            if domain_matches(host, pattern):
                return False, "denied_domain"
        if self.allow_domains:
            if not any(domain_matches(host, pattern) for pattern in self.allow_domains):
                return False, "not_in_allowlist"
        return True, "allowed"

    def credibility_for(self, url: str, *, open_license: bool = False) -> str:
        """来源可信度标记：high / medium / low。只影响标注与使用建议，不改写内容。"""
        host = normalize_domain(urlparse(str(url or "")).netloc)
        if not host:
            return "low"
        if any(domain_matches(host, pattern) for pattern in LOW_TRUST_DOMAINS):
            return "low"
        if host.endswith(HIGH_TRUST_SUFFIXES) or any(
            domain_matches(host, pattern) for pattern in HIGH_TRUST_DOMAINS
        ):
            return "high"
        if open_license:
            return "medium"
        return "medium" if urlparse(str(url or "")).scheme == "https" else "low"

    def to_dict(self) -> dict[str, Any]:
        """用于任务投影与前端展示的可序列化摘要（不含密钥）。"""
        return {
            "enabled": self.enabled,
            "max_queries": self.max_queries,
            "max_results_per_query": self.max_results_per_query,
            "max_sources": self.max_sources,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "min_request_interval_seconds": self.min_request_interval_seconds,
            "max_source_chars": self.max_source_chars,
            "respect_robots": self.respect_robots,
            "allow_domains": list(self.allow_domains),
            "deny_domains": list(self.deny_domains),
            "excluded_urls": list(self.excluded_urls),
        }


def load_web_search_policy() -> WebSearchPolicy:
    return WebSearchPolicy.from_env()


def _canonical_url(value: Any) -> str:
    """URL 归一化：去空白、去片段、小写 scheme/host，便于逐条剔除时稳定比对。"""
    raw = str(value or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    if not parsed.scheme:
        return raw.rstrip("/").lower()
    host = normalize_domain(parsed.netloc)
    path = parsed.path.rstrip("/")
    canonical = f"{parsed.scheme.lower()}://{host}{path}"
    if parsed.query:
        canonical = f"{canonical}?{parsed.query}"
    return canonical


def _coerce_urls(value: Any) -> tuple[str, ...]:
    if not value:
        return ()
    raw = value.split(",") if isinstance(value, str) else list(value)
    out: list[str] = []
    for item in raw:
        canonical = _canonical_url(item)
        if canonical and canonical not in out:
            out.append(canonical)
    return tuple(out)


def _coerce_domains(value: Any) -> tuple[str, ...]:
    if not value:
        return ()
    if isinstance(value, str):
        raw = value.split(",")
    else:
        raw = list(value)
    out: list[str] = []
    for item in raw:
        normalized = normalize_domain(str(item))
        if normalized and normalized not in out:
            out.append(normalized)
    return tuple(out)


def resolve_web_search_policy(settings: Any | None) -> WebSearchPolicy:
    """把一次请求的联网设置叠加到环境基线上。

    请求只能在环境允许的范围内收紧：环境未开启时请求无法开启，
    数值上限一律取两者较小值，拒绝域名做并集。
    """
    base = WebSearchPolicy.from_env()
    if settings is None:
        return base
    if not isinstance(settings, dict):
        settings = {
            key: getattr(settings, key)
            for key in (
                "enabled",
                "max_queries",
                "max_results",
                "max_sources",
                "allowed_domains",
                "blocked_domains",
                "excluded_urls",
            )
            if hasattr(settings, key)
        }

    requested_enabled = settings.get("enabled")
    enabled = base.enabled and bool(requested_enabled)

    def _tighten(key: str, current: int) -> int:
        value = settings.get(key)
        if value is None:
            return current
        try:
            return max(1, min(int(value), current))
        except (TypeError, ValueError):
            return current

    allow = _coerce_domains(settings.get("allowed_domains")) or base.allow_domains
    deny = tuple(dict.fromkeys(base.deny_domains + _coerce_domains(settings.get("blocked_domains"))))
    excluded = tuple(
        dict.fromkeys(base.excluded_urls + _coerce_urls(settings.get("excluded_urls")))
    )

    # max_results 是教师侧的用词，对应策略里的来源上限。
    max_sources = _tighten("max_sources", base.max_sources)
    max_sources = _tighten("max_results", max_sources)

    return replace(
        base,
        enabled=enabled,
        max_queries=_tighten("max_queries", base.max_queries),
        max_sources=max_sources,
        allow_domains=allow,
        deny_domains=deny,
        excluded_urls=excluded,
    )


__all__ = [
    "DEFAULT_DENY_DOMAINS",
    "DEFAULT_ENABLED",
    "HIGH_TRUST_DOMAINS",
    "HIGH_TRUST_SUFFIXES",
    "LOW_TRUST_DOMAINS",
    "WebSearchPolicy",
    "domain_matches",
    "load_web_search_policy",
    "normalize_domain",
    "resolve_web_search_policy",
]
