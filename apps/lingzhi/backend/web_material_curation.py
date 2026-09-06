"""教师对联网来源的**持久**剔除名单（按课程存，跨生成轮次有效）。

原来剔除只存在前端组件的 `ref` 里，刷新即失效，而且从未随生成请求发出。
这里把它落到课程元数据上：读回来后与本次请求的临时剔除合并，
再交给 `web_material_search` 现成的过滤逻辑执行——过滤本身不重写。
"""

from __future__ import annotations

from typing import Any

from web_material_search import canonical_source_url

CURATION_METADATA_KEY = "web_material_curation"

_MAX_ENTRIES = 500


def _clean_ids(values: Any) -> list[str]:
    seen: list[str] = []
    for value in values or []:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.append(text)
    return seen[:_MAX_ENTRIES]


def _clean_urls(values: Any) -> list[str]:
    seen: list[str] = []
    for value in values or []:
        text = canonical_source_url(value)
        if text and text not in seen:
            seen.append(text)
    return seen[:_MAX_ENTRIES]


def normalize_exclusions(payload: dict[str, Any] | None) -> dict[str, Any]:
    """把任意入参规整成可持久化的剔除名单。"""
    source = payload or {}
    return {
        "excluded_source_ids": _clean_ids(source.get("excluded_source_ids")),
        "excluded_urls": _clean_urls(source.get("excluded_urls")),
    }


def load_course_exclusions(raw_course: dict[str, Any] | None) -> dict[str, Any]:
    """从课程元数据读回剔除名单；没有记录时返回空名单而不是 None。"""
    stored = (raw_course or {}).get(CURATION_METADATA_KEY)
    if not isinstance(stored, dict):
        return normalize_exclusions(None)
    return normalize_exclusions(stored)


def merge_ingest_exclusions(
    ingest_settings: dict[str, Any] | None,
    stored: dict[str, Any] | None,
) -> dict[str, Any]:
    """把持久名单并进本次生成的 ingest_settings。

    两者是并集：课程级名单长期生效，请求级名单只作用于本次；
    任一处剔除过的来源都不再进入本轮资料。
    """
    merged = dict(ingest_settings or {})
    persisted = normalize_exclusions(stored)
    merged["excluded_source_ids"] = _clean_ids(
        list(merged.get("excluded_source_ids") or [])
        + persisted["excluded_source_ids"]
    )
    merged["excluded_urls"] = _clean_urls(
        list(merged.get("excluded_urls") or []) + persisted["excluded_urls"]
    )
    return merged


__all__ = [
    "CURATION_METADATA_KEY",
    "load_course_exclusions",
    "merge_ingest_exclusions",
    "normalize_exclusions",
]
