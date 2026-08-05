"""联网搜索策略层测试：默认保守、白/黑名单生效、可信度标记稳定。

这些测试只验证纯策略判断，不发任何真实网络请求。
"""

from __future__ import annotations

import pytest

from web_search_config import (
    DEFAULT_DENY_DOMAINS,
    WebSearchPolicy,
    domain_matches,
    load_web_search_policy,
    normalize_domain,
)


def test_default_policy_is_disabled_and_conservative():
    policy = WebSearchPolicy()
    assert policy.enabled is False
    assert policy.respect_robots is True
    assert policy.max_queries <= 4
    assert policy.max_sources <= 8
    assert policy.max_retries <= 1
    assert policy.timeout_seconds <= 12.0
    assert policy.allow_domains == ()
    assert policy.deny_domains == DEFAULT_DENY_DOMAINS


def test_env_policy_defaults_to_disabled_without_env(monkeypatch):
    for name in (
        "WEB_SEARCH_ENABLED",
        "WEB_SEARCH_MAX_QUERIES",
        "WEB_SEARCH_ALLOW_DOMAINS",
        "WEB_SEARCH_DENY_DOMAINS",
    ):
        monkeypatch.delenv(name, raising=False)
    assert load_web_search_policy().enabled is False


def test_env_overrides_are_clamped(monkeypatch):
    monkeypatch.setenv("WEB_SEARCH_ENABLED", "true")
    monkeypatch.setenv("WEB_SEARCH_MAX_QUERIES", "9999")
    monkeypatch.setenv("WEB_SEARCH_MAX_RETRIES", "77")
    monkeypatch.setenv("WEB_SEARCH_TIMEOUT_SECONDS", "0.01")
    policy = load_web_search_policy()
    assert policy.enabled is True
    assert policy.max_queries == 12
    assert policy.max_retries == 3
    assert policy.timeout_seconds == 1.0


def test_invalid_env_values_fall_back_to_defaults(monkeypatch):
    monkeypatch.setenv("WEB_SEARCH_MAX_QUERIES", "not-a-number")
    monkeypatch.setenv("WEB_SEARCH_TIMEOUT_SECONDS", "")
    policy = load_web_search_policy()
    assert policy.max_queries == 4
    assert policy.timeout_seconds == 12.0


@pytest.mark.parametrize(
    "value,expected",
    [
        ("https://WWW.Example.COM/path?q=1", "example.com"),
        ("http://sub.example.com:8080", "sub.example.com"),
        ("user@example.com", "example.com"),
        ("  Example.com.  ", "example.com"),
        ("", ""),
    ],
)
def test_normalize_domain(value, expected):
    assert normalize_domain(value) == expected


def test_domain_matches_covers_subdomains_only():
    assert domain_matches("docs.python.org", "python.org") is True
    assert domain_matches("python.org", "python.org") is True
    # 后缀相似但不是子域，必须不命中，否则黑名单可被绕过。
    assert domain_matches("notpython.org", "python.org") is False
    assert domain_matches("python.org.evil.com", "python.org") is False


@pytest.mark.parametrize(
    "url,reason",
    [
        ("ftp://example.com/a", "unsupported_scheme"),
        ("javascript:alert(1)", "unsupported_scheme"),
        ("https://localhost", "invalid_host"),
        ("https://wenku.baidu.com/view/1", "denied_domain"),
        ("https://m.zhihu.com/question/1", "denied_domain"),
    ],
)
def test_domain_verdict_rejects_unsafe_sources(url, reason):
    allowed, code = WebSearchPolicy().domain_verdict(url)
    assert allowed is False
    assert code == reason


def test_domain_verdict_allows_plain_public_source():
    allowed, code = WebSearchPolicy().domain_verdict("https://openstax.org/books/calculus")
    assert allowed is True
    assert code == "allowed"


def test_allowlist_excludes_everything_else():
    policy = WebSearchPolicy(allow_domains=("openstax.org",))
    assert policy.domain_verdict("https://openstax.org/x")[0] is True
    assert policy.domain_verdict("https://sub.openstax.org/x")[0] is True
    allowed, code = policy.domain_verdict("https://example.com/x")
    assert allowed is False
    assert code == "not_in_allowlist"


def test_denylist_wins_over_allowlist():
    policy = WebSearchPolicy(
        allow_domains=("wenku.baidu.com",),
        deny_domains=("wenku.baidu.com",),
    )
    assert policy.domain_verdict("https://wenku.baidu.com/view/1")[1] == "denied_domain"


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://ocw.mit.edu/courses/x", "high"),
        ("https://en.wikipedia.org/wiki/Derivative", "high"),
        ("https://www.who.int/news", "high"),
        ("https://someschool.edu.cn/page", "high"),
        ("https://example.com/article", "medium"),
        ("http://example.com/article", "low"),
        ("https://someone.medium.com/post", "low"),
        ("", "low"),
    ],
)
def test_credibility_marks(url, expected):
    assert WebSearchPolicy().credibility_for(url) == expected


def test_open_license_lifts_plain_http_to_medium():
    policy = WebSearchPolicy()
    assert policy.credibility_for("http://example.com/a", open_license=True) == "medium"


def test_policy_dict_carries_no_secrets():
    data = WebSearchPolicy().to_dict()
    assert data["enabled"] is False
    serialized = repr(data).lower()
    assert "api_key" not in serialized and "key" not in data
