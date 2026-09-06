"""共用的下游重建执行链：把影响报告变成真实重建，并把结果折回下游状态。

## 为什么是共用服务而不是教案专用

`teaching_plan_impact.build_downstream_state` 已经产出了一份完整的重建工作
清单，`record_rebuild_outcome` 已经定义了结果回写的契约，`locked_object_ids`
也已经为跨链路互斥预留好——**唯独中间的执行器没有人写**。教案侧应用修订后，
下游只是被标成 `rebuild_required`，正文/练习/PPT 内容还是旧的。

知识侧（`course_knowledge_impact`）刻意复用了同一套 `IMPACT_GROUPS` 分组，
理由写在那个模块里：知识改动与教案改动落到同一个正文块时必须给出一致结论，
两套实现保证不了。重建这一端同理——如果教案侧和知识侧各写一个执行器，
同一个正文块会有两条重建路径、两套失败语义、两份"最后可用产物"记录。

所以这个模块只认 `IMPACT_GROUPS` 形状的影响报告，不认"谁触发的"。教案侧
传教案影响报告，知识侧传知识影响报告，走同一个执行器、同一套回执。

## 边界

- **只编排，不自己生成内容**。真正的重建仍由既有管线完成
  （`representation_compiler.rebuild_core_representations_safely` 等），
  本模块只决定"重建哪些、按什么顺序、失败了怎么记"。
- **失败不覆盖最后可用产物**。这是 6.3 的硬要求：重建失败时旧正文、练习、
  PPT 必须继续可读。执行器本身不碰产物，靠的是既有管线的
  shadow-then-publish + `record_rebuild_outcome("failed")` 保留
  `last_available`。
- **锁定冲突不重复重建**。同一对象已被其他链路占用时跳过，标 `lock_conflict`，
  不排队也不抢锁——抢锁会让两条链路互相覆盖。
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Callable

from teaching_plan_impact import (
    DOWNSTREAM_STATES,
    record_rebuild_outcome,
)

REBUILD_RECEIPT_SCHEMA = "downstream_rebuild_receipt_v1"

# 逐对象同步回执的状态（tasks 6.4）。与 DOWNSTREAM_STATES 是两个命名空间：
# 前者说"这次重建这个对象发生了什么"，后者说"这个对象现在处于什么生命周期"。
RECEIPT_OUTCOMES = (
    "content_changed",   # 真的重建了，内容变了
    "source_verified",   # 来源已核对，内容无需变化
    "stale",             # 仍待重建（本轮没轮到或被跳过）
    "blocked",           # 影响不可判定，禁止静默重建
    "unchanged",         # 不在影响范围内
)

# 哪些下游类型由哪条既有管线负责。执行器不自己实现任何一条。
_REPRESENTATION_TYPES = {
    "teaching_representation", "slide_deck", "lecture", "handout", "lesson_plan",
}
_CONTENT_TYPES = {"section_content", "course_document", "block"}
_PRACTICE_TYPES = {"practice", "question", "mastery_criterion"}
_LESSON_PLAN_TYPES = {"lesson_plan_section"}
_SCRIPT_TYPES = {"script_block"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(value: Any) -> str:
    return str(value or "").strip()


def plan_rebuild(
    downstream: dict[str, Any],
    *,
    only_types: list[str] | None = None,
    only_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    """从下游状态里挑出本轮真正要重建的对象。

    只挑 `rebuild_required`：`current` 无需动，`candidate` 在等教师确认，
    `lock_conflict` 归别的链路，`blocked` 必须先由人判断——静默重建一个
    影响不可判定的对象，正是 spec 要禁止的。
    """
    selected: list[dict[str, Any]] = []
    for item in (downstream or {}).get("items") or []:
        if not isinstance(item, dict):
            continue
        if _text(item.get("state")) != "rebuild_required":
            continue
        item_type = _text(item.get("type"))
        item_id = _text(item.get("id"))
        if only_types and item_type not in only_types:
            continue
        if only_ids and item_id not in only_ids:
            continue
        selected.append({
            "type": item_type,
            "id": item_id,
            "section_id": _text(item.get("section_id")),
            "reason": _text(item.get("reason")),
            "impact_group": _text(item.get("impact_group")),
            "pipeline": pipeline_for(item_type),
            "has_readable_fallback": isinstance(item.get("last_available"), dict),
        })
    # 稳定顺序：同一份影响报告每次都产出同样的重建序列，便于复现与幂等。
    selected.sort(key=lambda entry: (entry["pipeline"], entry["type"], entry["id"]))
    return selected


def pipeline_for(object_type: str) -> str:
    """对象类型 -> 负责重建它的既有管线名。"""
    normalized = _text(object_type)
    if normalized in _REPRESENTATION_TYPES:
        return "representation"
    if normalized in _CONTENT_TYPES:
        return "course_content"
    if normalized in _PRACTICE_TYPES:
        return "practice"
    if normalized in _LESSON_PLAN_TYPES:
        return "lesson_plan"
    if normalized in _SCRIPT_TYPES:
        return "script"
    if normalized in {"knowledge_binding", "knowledge_point"}:
        return "knowledge"
    return "unsupported"


def _receipt(
    entry: dict[str, Any],
    outcome: str,
    *,
    detail: str = "",
    revision: str = "",
) -> dict[str, Any]:
    return {
        "type": entry["type"],
        "id": entry["id"],
        "pipeline": entry["pipeline"],
        "outcome": outcome,
        "detail": detail,
        "revision": revision,
        "readable_fallback": bool(entry.get("has_readable_fallback")),
    }


def execute_rebuild(
    downstream: dict[str, Any],
    *,
    runners: dict[str, Callable[[dict[str, Any]], dict[str, Any]]],
    locked_object_ids: list[str] | None = None,
    only_types: list[str] | None = None,
    only_ids: list[str] | None = None,
    candidate_only: bool = False,
) -> dict[str, Any]:
    """按下游状态逐对象重建，返回新的下游状态 + 逐对象回执。

    `runners` 按管线名注入真正的重建函数（`representation` / `course_content`
    / `practice` / `knowledge`），每个接收一条工作项、返回
    `{"status": "succeeded"|"candidate_ready"|"failed", "revision": ..., "error": ...}`。
    注入而不是直接 import，是因为这些管线各自需要课程文档、仓库、任务管理器等
    不同上下文；执行器不该知道这些，也不该成为它们的耦合点。

    `candidate_only=True` 时，成功的重建记为 `candidate`（等教师确认）而不是
    直接 `current`——对应 6.2 的"定向重建候选"。
    """
    state = deepcopy(downstream or {})
    locked = {_text(item) for item in (locked_object_ids or []) if _text(item)}
    work = plan_rebuild(state, only_types=only_types, only_ids=only_ids)
    receipts: list[dict[str, Any]] = []

    for entry in work:
        if entry["id"] in locked:
            # 锁定冲突不抢锁：另一条链路正在写同一个对象，两边都重建会互相覆盖。
            receipts.append(_receipt(entry, "stale", detail="其他链路正在写入该对象，本轮跳过。"))
            continue
        runner = runners.get(entry["pipeline"])
        if runner is None:
            receipts.append(_receipt(
                entry, "blocked",
                detail=f"没有可用于 {entry['type']} 的重建管线，禁止静默跳过。",
            ))
            continue
        try:
            result = runner(dict(entry)) or {}
        except Exception as error:  # noqa: BLE001 - 单个对象失败不能中断整批
            state = record_rebuild_outcome(
                state,
                object_type=entry["type"],
                object_id=entry["id"],
                outcome="failed",
                error=str(error),
            )
            receipts.append(_receipt(entry, "stale", detail=f"重建失败：{error}"))
            continue

        status = _text(result.get("status"))
        revision = _text(result.get("revision"))
        if status == "succeeded":
            outcome = "candidate_ready" if candidate_only else "succeeded"
            state = record_rebuild_outcome(
                state,
                object_type=entry["type"],
                object_id=entry["id"],
                outcome=outcome,
                revision=revision,
            )
            receipts.append(_receipt(
                entry,
                "content_changed" if not candidate_only else "stale",
                detail="已生成重建候选，等待教师确认。" if candidate_only else "已按当前来源重建。",
                revision=revision,
            ))
        elif status == "candidate_ready":
            state = record_rebuild_outcome(
                state,
                object_type=entry["type"],
                object_id=entry["id"],
                outcome="candidate_ready",
                revision=revision,
            )
            receipts.append(_receipt(
                entry, "stale", detail="已生成重建候选，等待教师确认。", revision=revision,
            ))
        elif status == "unchanged":
            # 来源核对后确认无需变化：这不是失败，也不该继续挂 rebuild_required。
            state = record_rebuild_outcome(
                state,
                object_type=entry["type"],
                object_id=entry["id"],
                outcome="succeeded",
                revision=revision,
            )
            receipts.append(_receipt(entry, "source_verified", detail="来源已核对，内容无需变化。"))
        else:
            error = _text(result.get("error")) or "重建失败"
            state = record_rebuild_outcome(
                state,
                object_type=entry["type"],
                object_id=entry["id"],
                outcome="failed",
                error=error,
            )
            receipts.append(_receipt(entry, "stale", detail=f"重建失败：{error}"))

    # 影响报告说"不受影响"的对象也要出现在回执里，否则教师无法区分
    # "确认没事" 与 "漏了"。
    touched = {(item["type"], item["id"]) for item in receipts}
    for item in state.get("items") or []:
        if not isinstance(item, dict):
            continue
        key = (_text(item.get("type")), _text(item.get("id")))
        if key in touched:
            continue
        item_state = _text(item.get("state"))
        if item_state == "blocked":
            receipts.append({
                "type": key[0], "id": key[1],
                "pipeline": pipeline_for(key[0]),
                "outcome": "blocked",
                "detail": _text(item.get("reason")),
                "revision": "",
                "readable_fallback": isinstance(item.get("last_available"), dict),
            })
        elif item_state == "lock_conflict":
            receipts.append({
                "type": key[0], "id": key[1],
                "pipeline": pipeline_for(key[0]),
                "outcome": "stale",
                "detail": _text(item.get("reason")),
                "revision": "",
                "readable_fallback": isinstance(item.get("last_available"), dict),
            })
        elif item_state in {"current", "candidate"}:
            receipts.append({
                "type": key[0], "id": key[1],
                "pipeline": pipeline_for(key[0]),
                "outcome": "unchanged" if item_state == "current" else "stale",
                "detail": _text(item.get("reason")),
                "revision": "",
                "readable_fallback": isinstance(item.get("last_available"), dict),
            })

    receipts.sort(key=lambda entry: (entry["type"], entry["id"]))
    return {
        "schema_version": REBUILD_RECEIPT_SCHEMA,
        "downstream": state,
        "receipts": receipts,
        "counts": {
            outcome: sum(1 for item in receipts if item["outcome"] == outcome)
            for outcome in RECEIPT_OUTCOMES
        },
        "readable_fallback_count": state.get("readable_fallback_count", 0),
        "updated_at": _now(),
    }


def rebuild_summary(result: dict[str, Any]) -> dict[str, Any]:
    """给测试与前端用的紧凑快照。"""
    downstream = result.get("downstream") or {}
    return {
        "counts": dict(result.get("counts") or {}),
        "downstream_counts": {
            key: value
            for key, value in (downstream.get("counts") or {}).items()
            if key in DOWNSTREAM_STATES
        },
        "readable_fallback_count": result.get("readable_fallback_count", 0),
    }


__all__ = [
    "REBUILD_RECEIPT_SCHEMA",
    "RECEIPT_OUTCOMES",
    "execute_rebuild",
    "pipeline_for",
    "plan_rebuild",
    "rebuild_summary",
]
