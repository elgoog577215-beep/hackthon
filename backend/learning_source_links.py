"""从一条学习事实回跳到它产生的现场。

一条 `LearningEvent` 记录的是"当时在哪里发生了什么"。课程修订会持续前移，所以
回跳不能假设当时的坐标今天还精确存在——但也不能因为坐标漂移就 404 了事：事实
本身依然成立，学习者有权知道它当时对应哪里、现在对应哪里。

因此回跳总是返回一个**已解析的落点**加一个**解析状态**，由调用方决定怎样提示：

- ``exact``：块与修订都精确命中，可直接跳转。
- ``updated_block``：块还在，但内容已修订——落点有效，需提示"来源已变更"。
- ``fingerprint_remap``：块 ID 已变，按内容指纹唯一命中新位置。
- ``node_fallback`` / ``course_fallback``：具体块已不可考，退到节点或课程层。
- ``unavailable``：连课程都不存在了（例如课程被删除）。

只有 ``unavailable`` 才是真正的"无处可去"，而它返回的仍然是一个带原始坐标的
结构化结果，不是 HTTP 404。
"""

from __future__ import annotations

from typing import Any

from content_blocks import resolve_content_anchor
from learning_events import load_learning_events
from storage import storage

SCHEMA_VERSION = "learning_source_link_v1"

# 解析状态里，落点仍然可用（可以真的跳过去）的那些。
RESOLVABLE_STATUSES = {
    "exact",
    "updated_block",
    "fingerprint_remap",
    "node_fallback",
    "course_fallback",
}


def build_event_source_link(event: dict[str, Any]) -> dict[str, Any]:
    """把一条学习事实解析成可回跳的现场坐标。

    纯函数式读取：不写任何状态，也不修改事实本身。
    """
    course_id = str(event.get("course_id") or "")
    node_id = str(event.get("node_id") or "") or None

    origin = {
        "course_id": course_id,
        "course_version_id": str(event.get("course_version_id") or "") or None,
        "node_id": node_id,
        "objective_id": str(event.get("objective_id") or "") or None,
        "objective_revision_id": str(event.get("objective_revision_id") or "") or None,
        # 回跳到"哪次作答/哪个修订"用的引用
        "attempt_id": str(event.get("attempt_id") or "") or None,
        "record_id": str(event.get("record_id") or "") or None,
        "question_revision_id": str(event.get("question_revision_id") or "") or None,
        "task_revision_id": str(event.get("task_revision_id") or "") or None,
        "diagnostic_case_id": str(event.get("diagnostic_case_id") or "") or None,
    }

    course = storage.load_course(course_id) if course_id else None
    if not course:
        return {
            "schema_version": SCHEMA_VERSION,
            "event_id": event.get("event_id"),
            "event_type": event.get("event_type"),
            "origin": origin,
            "status": "unavailable",
            "reason_code": "course_no_longer_available",
            "source_changed": True,
            "can_navigate": False,
            "target": None,
        }

    # 事实里保留的语义锚点（如果当时记了的话）。没有锚点时按节点回跳，
    # `resolve_content_anchor` 会退到 node_fallback。
    anchor = _anchor_from_event(event)
    resolution = resolve_content_anchor(course, node_id=node_id, anchor=anchor)
    status = str(resolution.get("status") or "unavailable")
    resolved_anchor = resolution.get("resolved_anchor")

    current_version_id = str(resolution.get("current_course_version_id") or "") or None
    recorded_version_id = origin["course_version_id"]
    version_moved = bool(
        recorded_version_id
        and current_version_id
        and recorded_version_id != current_version_id
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "event_id": event.get("event_id"),
        "event_type": event.get("event_type"),
        "origin": origin,
        "status": status,
        "reason_code": _reason_code(status, version_moved=version_moved),
        # 来源是否已经变了：块内容被改，或课程版本已前移。
        "source_changed": bool(resolution.get("content_changed")) or version_moved,
        "can_navigate": status in RESOLVABLE_STATUSES and bool(resolved_anchor),
        "target": {
            "course_id": course_id,
            "course_version_id": current_version_id,
            "node_id": str((resolved_anchor or {}).get("node_id") or "") or None,
            "node_name": str((resolved_anchor or {}).get("node_name") or "") or None,
            "block_id": str((resolved_anchor or {}).get("block_id") or "") or None,
            "block_revision_id": str(
                (resolved_anchor or {}).get("block_revision_id") or ""
            ) or None,
        } if resolved_anchor else None,
    }


def _anchor_from_event(event: dict[str, Any]) -> dict[str, Any] | None:
    """取出事实里记录的语义锚点。

    历史事件的锚点可能记在 `evidence.anchor`，也可能直接摊在 evidence 上；
    两种都支持，取不到就返回 None（由节点级回退兜底）。
    """
    evidence = event.get("evidence") or {}
    anchor = evidence.get("anchor")
    if isinstance(anchor, dict) and anchor:
        return anchor
    fallback = {
        key: evidence.get(key)
        for key in ("block_id", "block_revision_id", "content_fingerprint", "progress")
        if evidence.get(key)
    }
    return fallback or None


def _reason_code(status: str, *, version_moved: bool) -> str:
    if status == "exact":
        return "source_version_moved" if version_moved else "source_unchanged"
    return {
        "updated_block": "source_content_revised",
        "fingerprint_remap": "source_relocated_by_fingerprint",
        "node_fallback": "source_block_retired_using_node",
        "course_fallback": "source_node_retired_using_course",
        "unavailable": "source_no_longer_available",
    }.get(status, "source_resolution_unknown")


def build_source_links_for_learner(
    *,
    user_id: str,
    course_id: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """批量解析该学习者事实的回跳坐标。"""
    events = load_learning_events(
        user_id=user_id,
        course_id=course_id,
        limit=limit,
    )
    return [build_event_source_link(event) for event in events]


__all__ = [
    "RESOLVABLE_STATUSES",
    "SCHEMA_VERSION",
    "build_event_source_link",
    "build_source_links_for_learner",
]
