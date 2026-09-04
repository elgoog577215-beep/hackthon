"""课程联网来源的产品级冻结边界。

实现代码和历史数据继续保留，但当前产品不暴露入口、不执行检索，
也不让历史联网来源进入新的课程生成上下文。
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable


COURSE_WEB_RESEARCH_ENABLED = False
COURSE_WEB_RESEARCH_FROZEN_DETAIL = {
    "code": "course_web_research_frozen",
    "message": "课程联网来源当前未开放",
}


def is_course_web_source(value: Any) -> bool:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    if not isinstance(value, dict):
        return False
    metadata = value.get("source_metadata") or {}
    return (
        str(value.get("origin") or "") == "web_search"
        or str(metadata.get("origin") or "") == "web_search"
    )


def without_course_web_sources(values: Iterable[Any] | None) -> list[Any]:
    """保留原对象形态，只从活动生成输入中排除联网来源。"""

    return [value for value in values or [] if not is_course_web_source(value)]


def historical_web_course_asset_ids(course_data: dict[str, Any] | None) -> set[str]:
    """从兼容数据中找出过去登记到课程文件空间的联网资产。"""

    state = (course_data or {}).get("web_research") or {}
    return {
        str(reference.get("asset_id") or "")
        for session in state.get("sessions") or []
        if isinstance(session, dict)
        for reference in session.get("accepted_references") or []
        if isinstance(reference, dict) and str(reference.get("asset_id") or "")
    }


def course_generation_view(course_data: dict[str, Any]) -> dict[str, Any]:
    """返回不含历史联网来源的课程生成视图，不改写持久数据。"""

    result = deepcopy(course_data)
    bindings = list(result.get("material_bindings") or [])
    web_asset_ids = {
        str(item.get("asset_id") or "")
        for item in bindings
        if isinstance(item, dict) and is_course_web_source(item)
    }
    result["material_bindings"] = without_course_web_sources(bindings)
    result["evidence_catalog"] = [
        item
        for item in result.get("evidence_catalog") or []
        if not (
            isinstance(item, dict)
            and str(item.get("asset_id") or "") in web_asset_ids
        )
    ]
    result.pop("retrieval_package", None)
    result.pop("retrieval_acceptance", None)
    result.pop("outline_research", None)
    artifacts = result.get("generation_stage_artifacts")
    if isinstance(artifacts, dict):
        artifacts.pop("web_retrieval", None)
        artifacts.pop("assessment_retrieval", None)
    return result


def frozen_web_search_report() -> dict[str, Any]:
    return {
        "enabled": False,
        "status": "disabled",
        "degraded": False,
        "candidates": [],
        "queries": [],
        "rejected": [],
        "message_code": "course_web_research_frozen",
    }
