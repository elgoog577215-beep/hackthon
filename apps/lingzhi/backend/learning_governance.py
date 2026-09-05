"""学习事实的导出与删除治理。

`LearningEvent` 与正式领域仓库保存**事实**；`LearnerModel`、学习进度、学习运行时
是可重算的**解释**。本模块只治理事实层，不把任何投影变成第二真源。

删除口径（owner 2026-08-12 裁定）：

1. 硬删内容 + 保留最小回执。事实载荷真删；回执只留坐标与操作痕迹，不留任何学习
   内容原文。
2. 三档粒度（单条 / 单课程 / 全部）共用同一条派生投影失效路径。
3. 回执长期保留，不自动清理（不含学习内容，属审计记录）。
4. 已聚合进正式课程产物的内容不回溯撤销，但断开个人关联标识，回执记明
   「已聚合、未回溯」。

派生投影分两类，删除后的处理方式不同：

- **每次请求重算的**（`LearnerModel`、`learning_progress`、`learning_runtime`）：
  事实消失即自动一致，无需干预。
- **持久化的**（`CourseEvolutionState.evidence_items` 与其支撑的 hypotheses、
  共享 `CourseDocument` 上的 `evidence_refs`）：必须显式失效，否则留下指向已删
  事实的引用空洞。这才是「一致失效」的真正风险面。
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from learning_events import LEARNING_EVENTS_FILE, load_learning_events
from storage import storage

SCHEMA_VERSION = "learning_governance_v1"
DELETION_RECEIPTS_FILE = "learning_deletion_receipts.json"

DELETION_SCOPES = {"event", "course", "learner"}

# 回执允许出现的字段。任何新增字段必须显式加入白名单，防止学习内容原文顺着
# 「多存一点更好排查」的惯性混进审计记录。`_assert_receipt_is_content_free`
# 在写入前强制校验。
_RECEIPT_ALLOWED_KEYS = {
    "receipt_id",
    "schema_version",
    "scope",
    "user_id",
    "course_id",
    "reason_code",
    "requested_by",
    "deleted_at",
    "deleted_event_count",
    "deleted_events",
    "invalidated_projections",
    "aggregated_not_reverted",
}
# 单条被删事实在回执里允许保留的坐标。全部是 ID 与类型，不含任何自由文本。
_RECEIPT_EVENT_ALLOWED_KEYS = {
    "event_id",
    "event_type",
    "course_id",
    "course_version_id",
    "node_id",
    "objective_id",
    "objective_revision_id",
    "record_id",
    "attempt_id",
    "created_at",
}

_governance_lock = threading.RLock()


class DeletionReceiptLeak(AssertionError):
    """回执里出现了白名单之外的字段——可能夹带学习内容，必须停下来。"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------
# 导出
# --------------------------------------------------------------------------

def export_learning_facts(
    *,
    user_id: str,
    course_id: str | None = None,
) -> dict[str, Any]:
    """导出该学习者的学习事实与来源坐标。

    只读：不写任何状态，也不触发投影重算。导出内容包含删除回执，让学习者能看到
    自己删过什么（回执本身不含学习内容）。
    """
    events = load_learning_events(user_id=user_id, course_id=course_id)
    receipts = [
        item for item in load_deletion_receipts(user_id=user_id)
        if course_id is None or item.get("course_id") in {course_id, None}
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "user_id": user_id,
        "course_id": course_id,
        "exported_at": _now(),
        "manifest": {
            "event_count": len(events),
            "course_ids": sorted({
                str(item.get("course_id") or "")
                for item in events
                if item.get("course_id")
            }),
            "event_types": sorted({
                str(item.get("event_type") or "")
                for item in events
                if item.get("event_type")
            }),
            "deletion_receipt_count": len(receipts),
            "fact_source": "LearningEvent",
            # 导出的是事实，不是解释。明确写出来，避免下游把它当成模型快照。
            "excludes_projections": [
                "LearnerModel",
                "learning_progress",
                "learning_runtime",
            ],
        },
        "events": [deepcopy(item) for item in events],
        "deletion_receipts": receipts,
    }


# --------------------------------------------------------------------------
# 删除回执
# --------------------------------------------------------------------------

def _assert_receipt_is_content_free(receipt: dict[str, Any]) -> None:
    """回执不得夹带任何学习内容原文。

    按 owner 口径 3：回执长期保留，因为它只有坐标和操作痕迹。一旦出现白名单外的
    字段就说明设计漏了，必须停下来而不是靠缩短保留期补救。
    """
    unexpected = set(receipt) - _RECEIPT_ALLOWED_KEYS
    if unexpected:
        raise DeletionReceiptLeak(
            f"删除回执出现未授权字段（可能夹带学习内容）：{sorted(unexpected)}"
        )
    for event in receipt.get("deleted_events") or []:
        unexpected_event = set(event) - _RECEIPT_EVENT_ALLOWED_KEYS
        if unexpected_event:
            raise DeletionReceiptLeak(
                f"删除回执的事实坐标出现未授权字段：{sorted(unexpected_event)}"
            )


def _receipt_coordinates(event: dict[str, Any]) -> dict[str, Any]:
    """只取坐标。`evidence` / `result` / `metadata` 等载荷一律不进回执。"""
    return {
        key: event.get(key)
        for key in _RECEIPT_EVENT_ALLOWED_KEYS
        if event.get(key) is not None
    }


def load_deletion_receipts(*, user_id: str | None = None) -> list[dict[str, Any]]:
    stored = storage.load_data(DELETION_RECEIPTS_FILE) or []
    receipts = list(stored) if isinstance(stored, list) else []
    if user_id is not None:
        receipts = [item for item in receipts if item.get("user_id") == user_id]
    return [deepcopy(item) for item in receipts]


def _append_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    _assert_receipt_is_content_free(receipt)

    def append(stored: Any) -> list[dict[str, Any]]:
        receipts = list(stored) if isinstance(stored, list) else []
        receipts.append(receipt)
        return receipts

    _update_ledger(DELETION_RECEIPTS_FILE, append)
    return receipt


def _update_ledger(filename: str, updater):
    """Use Storage's cross-process atomic update with test-double fallback."""
    update_data = getattr(storage, "update_data", None)
    if callable(update_data):
        return update_data(filename, updater)
    current = storage.load_data(filename)
    updated = updater(current)
    storage.save_data(filename, updated)
    return updated


# --------------------------------------------------------------------------
# 删除
# --------------------------------------------------------------------------

def delete_learning_facts(
    *,
    user_id: str,
    scope: str,
    course_id: str | None = None,
    event_id: str | None = None,
    reason_code: str = "learner_requested",
    requested_by: str = "learner",
) -> dict[str, Any]:
    """硬删学习事实，并让持久化的派生投影一致失效。

    三档粒度共用这一条路径（owner 口径 2）：整体删除不另走快路径，否则两条路径
    会在投影失效上出现分歧。
    """
    if scope not in DELETION_SCOPES:
        raise ValueError(f"未知的删除粒度：{scope}")
    if scope == "event" and not event_id:
        raise ValueError("按条删除必须提供 event_id")
    if scope == "course" and not course_id:
        raise ValueError("按课程删除必须提供 course_id")

    with _governance_lock:
        def is_target(item: dict[str, Any]) -> bool:
            if item.get("user_id") != user_id:
                return False
            if scope == "event":
                return str(item.get("event_id") or "") == event_id
            if scope == "course":
                return str(item.get("course_id") or "") == str(course_id)
            return True

        targets: list[dict[str, Any]] = []

        def remove_targets(stored: Any) -> list[dict[str, Any]]:
            nonlocal targets
            events = list(stored) if isinstance(stored, list) else []
            targets = [item for item in events if is_target(item)]
            # 事实载荷真删：写回不含目标事件的完整账本，而不是打标记。
            return [item for item in events if not is_target(item)]

        _update_ledger(LEARNING_EVENTS_FILE, remove_targets)

        affected_course_ids = sorted({
            str(item.get("course_id") or "")
            for item in targets
            if item.get("course_id")
        })

        deleted_event_ids = {str(item.get("event_id") or "") for item in targets}
        invalidated, aggregated = _invalidate_derived_projections(
            user_id=user_id,
            course_ids=affected_course_ids,
            deleted_event_ids=deleted_event_ids,
        )

        receipt = {
            "receipt_id": f"ldr_{uuid.uuid4().hex}",
            "schema_version": SCHEMA_VERSION,
            "scope": scope,
            "user_id": user_id,
            "course_id": course_id,
            "reason_code": reason_code,
            "requested_by": requested_by,
            "deleted_at": _now(),
            "deleted_event_count": len(targets),
            "deleted_events": [_receipt_coordinates(item) for item in targets],
            "invalidated_projections": invalidated,
            "aggregated_not_reverted": aggregated,
        }
        return _append_receipt(receipt)


def _invalidate_derived_projections(
    *,
    user_id: str,
    course_ids: list[str],
    deleted_event_ids: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """让持久化投影一致失效，并记录已聚合但不回溯的部分。

    每次请求重算的投影（`LearnerModel` / 进度 / 运行时）不在这里处理——它们下次
    构建时自然不再看到被删事实。这里只处理会留下引用空洞的持久化对象。
    """
    invalidated: list[dict[str, Any]] = []
    aggregated: list[dict[str, Any]] = []

    for course_id in course_ids:
        state_result = _invalidate_course_evolution_state(
            user_id=user_id,
            course_id=course_id,
            deleted_event_ids=deleted_event_ids,
        )
        if state_result:
            invalidated.append(state_result)

        aggregated.extend(
            _detach_aggregated_course_products(
                user_id=user_id,
                course_id=course_id,
                deleted_event_ids=deleted_event_ids,
            )
        )

    return invalidated, aggregated


def _invalidate_course_evolution_state(
    *,
    user_id: str,
    course_id: str,
    deleted_event_ids: set[str],
) -> dict[str, Any] | None:
    """丢弃引用已删事实的 `EvidenceItem`，并把失去支撑的假设标记为过期。

    不就地改写历史结论的语义：假设不是被"改成别的结论"，而是被标为 `expired`
    并记录原因——它赖以成立的事实已经不存在了。
    """
    from course_evolution import course_evolution_repository

    try:
        state = course_evolution_repository.load(user_id, course_id)
    except Exception:
        return None

    stale_evidence_ids = {
        item.evidence_id
        for item in state.evidence_items
        if item.source_type == "learning_event" and item.source_id in deleted_event_ids
    }
    if not stale_evidence_ids:
        return None

    def _updater(current):
        current.evidence_items = [
            item for item in current.evidence_items
            if item.evidence_id not in stale_evidence_ids
        ]
        for hypothesis in current.hypotheses:
            before = len(hypothesis.support_evidence_ids)
            hypothesis.support_evidence_ids = [
                value for value in hypothesis.support_evidence_ids
                if value not in stale_evidence_ids
            ]
            hypothesis.counterevidence_ids = [
                value for value in hypothesis.counterevidence_ids
                if value not in stale_evidence_ids
            ]
            if len(hypothesis.support_evidence_ids) != before:
                # 失去全部支撑事实的假设不能继续驱动行为。
                if not hypothesis.support_evidence_ids:
                    hypothesis.status = "expired"
                    hypothesis.confidence = 0.0
                    hypothesis.confidence_reasons = ["supporting_evidence_deleted"]
        for plan in current.change_sets:
            plan.evidence_ids = [
                value for value in plan.evidence_ids
                if value not in stale_evidence_ids
            ]
            if not plan.evidence_ids and plan.status == "pending":
                plan.status = "stale"
        return current

    updated = course_evolution_repository.update(user_id, course_id, _updater)
    return {
        "projection": "course_evolution_state",
        "course_id": course_id,
        "dropped_evidence_count": len(stale_evidence_ids),
        "state_revision": updated.revision,
    }


def _detach_aggregated_course_products(
    *,
    user_id: str,
    course_id: str,
    deleted_event_ids: set[str],
) -> list[dict[str, Any]]:
    """断开共享课程产物上指向已删事实的个人关联标识。

    按 owner 口径 4：课程产物是教研资产，已经教师确认进入正式课程，不回溯撤销；
    但个人可识别的关联必须断。这里只清 `evidence_refs` 里的关联 ID，不改正文。

    已知边界（见 NOTES_TO_OWNER.md 第三节）：存在一条把学习者自述**原文**拼进
    课程正文的聚合路径。那种情况下关联无法仅靠清 ID 断开，回执用
    `content_not_detachable` 标出，等待 owner 裁决，不在本模块自行处置。
    """
    from course_repository import CourseDocumentNotFound, CourseDocumentRepository

    detached: list[dict[str, Any]] = []
    try:
        repository = CourseDocumentRepository(storage)
        document, _ = repository.load_document(course_id)
    except (CourseDocumentNotFound, Exception):
        return detached

    from course_evolution import course_evolution_repository

    try:
        state = course_evolution_repository.load(user_id, course_id)
    except Exception:
        return detached

    # 事件 -> evidence_id 的映射，用于在课程块上定位个人关联。
    stale_evidence_ids = {
        item.evidence_id
        for item in state.evidence_items
        if item.source_type == "learning_event" and item.source_id in deleted_event_ids
    }
    if not stale_evidence_ids:
        return detached

    for block in document.blocks:
        linked = [ref for ref in block.evidence_refs if ref in stale_evidence_ids]
        if not linked:
            continue
        detached.append({
            "course_id": course_id,
            "block_id": block.block_id,
            "detached_evidence_refs": linked,
            "reverted": False,
            "note": "aggregated_not_reverted",
        })
    return detached


__all__ = [
    "DELETION_RECEIPTS_FILE",
    "DELETION_SCOPES",
    "DeletionReceiptLeak",
    "SCHEMA_VERSION",
    "delete_learning_facts",
    "export_learning_facts",
    "load_deletion_receipts",
]
