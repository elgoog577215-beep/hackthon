"""教师可控：搜了什么可见、采用了哪些可见、不想要的能逐条剔除。"""

import pytest

from web_material_search import discover_web_materials
from web_search_config import WebSearchPolicy, resolve_web_search_policy


def _policy(**overrides) -> WebSearchPolicy:
    base = {
        "enabled": True,
        "max_queries": 2,
        "max_results_per_query": 5,
        "max_sources": 8,
        "respect_robots": False,
    }
    base.update(overrides)
    return WebSearchPolicy(**base)


def _fake_search(pages):
    async def _search(query, num_results=5):
        return list(pages)[:num_results]

    return _search


PAGES = [
    {
        "url": "https://openstax.org/derivative-intro",
        "title": "导数的直观引入",
        "text": "导数刻画瞬时变化率。" * 40,
    },
    {
        "url": "https://mit.edu/ocw/limits",
        "title": "极限与导数",
        "text": "极限是导数定义的基础。" * 40,
    },
]


@pytest.mark.asyncio
async def test_report_shows_queries_and_adopted_sources():
    """教师能看到搜了什么、采用了哪些。"""
    report = await discover_web_materials(
        topic="导数",
        requirements="希望学生掌握导数的几何意义",
        policy=_policy(),
        search=_fake_search(PAGES),
        now="2026-08-05T00:00:00Z",
    )

    assert report["status"] == "ready"
    assert report["queries"], "必须回传实际使用的检索词"
    adopted = {item["url"] for item in report["candidates"]}
    assert adopted == {p["url"] for p in PAGES}
    for candidate in report["candidates"]:
        assert candidate["retrieved_at"] == "2026-08-05T00:00:00Z"
        assert candidate["credibility"] in {"high", "medium", "low"}


@pytest.mark.asyncio
async def test_teacher_can_exclude_a_single_url():
    """逐条剔除：只去掉一条，不影响同域其他资料。"""
    report = await discover_web_materials(
        topic="导数",
        requirements="希望学生掌握导数的几何意义",
        policy=_policy(excluded_urls=("https://mit.edu/ocw/limits",)),
        search=_fake_search(PAGES),
    )

    urls = {item["url"] for item in report["candidates"]}
    assert urls == {"https://openstax.org/derivative-intro"}
    reasons = {item["url"]: item["reason"] for item in report["rejected"]}
    assert reasons["https://mit.edu/ocw/limits"] == "excluded_by_teacher"


@pytest.mark.asyncio
async def test_exclusion_ignores_trailing_slash_and_case():
    """剔除比对要归一化，否则教师点掉的那条会因为末尾斜杠又回来。"""
    report = await discover_web_materials(
        topic="导数",
        requirements="希望学生掌握导数的几何意义",
        policy=_policy(excluded_urls=("HTTPS://MIT.EDU/ocw/limits/",)),
        search=_fake_search(PAGES),
    )

    urls = {item["url"] for item in report["candidates"]}
    assert "https://mit.edu/ocw/limits" not in urls


def test_request_exclusions_merge_with_env_baseline():
    base = WebSearchPolicy.from_env()
    resolved = resolve_web_search_policy(
        {"enabled": True, "excluded_urls": "https://a.edu/x, https://b.edu/y"}
    )
    assert set(resolved.excluded_urls) >= {"https://a.edu/x", "https://b.edu/y"}
    assert set(resolved.deny_domains) >= set(base.deny_domains)


def test_max_results_is_treated_as_a_tightening_bound():
    resolved = resolve_web_search_policy({"enabled": True, "max_results": 2})
    assert resolved.max_sources <= 2


def test_excluded_urls_visible_in_policy_summary():
    policy = _policy(excluded_urls=("https://a.edu/x",))
    assert policy.to_dict()["excluded_urls"] == ["https://a.edu/x"]
