"""证据范围纠正：证据被记到错误的课程/节点/知识点时的纠正路径。

**不静默改写历史事实。** 原始 `LearningEvent` 记录的是"当时确实发生了什么"——
学习者确实在那一刻提交了那条自述，这个事实本身没有错。错的是它被绑定到的
范围坐标。

所以纠正不是修改原事实，而是**追加一条纠正事实**（`learning_scope_corrected`），
它引用原事实并声明正确的坐标。读取侧在重算投影时应用纠正，得到纠正后的范围；
原事实与纠正事实都留在账本里，构成完整审计痕迹。

这与本域的根本约束一致：`LearningEvent` 保存事实，投影是解释。纠正本身也是一条
事实，而不是对历史的覆写。
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from learning_events import load_learning_events, record_learning_event

SCOPE_CORRECTION_EVENT = "learning_scope_corrected"

# 允许被纠正的范围坐标。刻意不含 `evidence` / `result`：纠正的是"这条证据算在
# 哪里"，不是"当时说了什么"。允许改内容就等于改写历史。
CORRECTABLE_FIELDS = {
    "course_id",
    "node_id",
    "objective_id",
    "objective_revision_id",
    "concept_ids",
    "skill_unit_ids",
}


class ScopeCorrectionError(ValueError):
    pass


def record_scope_correction(
    *,
    user_id: str,
    event_id: str,
    corrections: dict[str, Any],
    reason_code: str = "misattributed_scope",
    actor: str = "user",
) -> dict[str, Any]:
    """追加一条范围纠正事实。

    返回新写入的纠正事件。原事实保持不变——这是刻意的，不是遗漏。
    """
    if not event_id:
        raise ScopeCorrectionError("范围纠正必须指明被纠正的事实")

    unknown = set(corrections) - CORRECTABLE_FIELDS
    if unknown:
        raise ScopeCorrectionError(
            f"这些字段不属于范围坐标，不能通过纠正修改：{sorted(unknown)}"
        )
    if not corrections:
        raise ScopeCorrectionError("范围纠正必须至少修改一个坐标")

    original = _find_event(user_id=user_id, event_id=event_id)
    if original is None:
        raise ScopeCorrectionError("找不到要纠正的事实，或它不属于该学习者")

    previous = {field: original.get(field) for field in corrections}

    return record_learning_event(
        event_type=SCOPE_CORRECTION_EVENT,
        actor=actor,
        source="learning_scope_correction",
        user_id=user_id,
        # 纠正事件本身挂在**纠正后**的课程下，这样按课程加载事实时能一并取到。
        course_id=str(corrections.get("course_id") or original.get("course_id") or "") or None,
        node_id=str(corrections.get("node_id") or original.get("node_id") or "") or None,
        entity_type="learning_event",
        entity_id=event_id,
        entity_revision=original.get("schema_version"),
        operation_id=f"scope-correction:{event_id}",
        result={
            "corrected_event_id": event_id,
            "corrections": deepcopy(corrections),
            "previous": previous,
            "reason_code": reason_code,
        },
        metadata={
            "corrected_event_id": event_id,
            "corrected_event_type": str(original.get("event_type") or ""),
            "reason_code": reason_code,
        },
    )


def _find_event(*, user_id: str, event_id: str) -> dict[str, Any] | None:
    return next(
        (
            item for item in load_learning_events(user_id=user_id)
            if str(item.get("event_id") or "") == event_id
        ),
        None,
    )


def apply_scope_corrections(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """把纠正事实应用到被纠正的事实上，得到纠正后的范围。

    读取侧投影用这个函数重算，而不是去改账本。返回的事实带 ``scope_correction``
    说明它被纠正过、原值是什么、由哪条纠正事实导致——审计痕迹随投影一起可见。

    纠正事件本身保留在结果里：它也是一条事实。
    """
    corrections_by_event: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        if str(event.get("event_type") or "") != SCOPE_CORRECTION_EVENT:
            continue
        result = event.get("result") or {}
        target_id = str(result.get("corrected_event_id") or "")
        if target_id:
            corrections_by_event.setdefault(target_id, []).append(event)

    applied: list[dict[str, Any]] = []
    for event in events:
        event_id = str(event.get("event_id") or "")
        relevant = corrections_by_event.get(event_id)
        if not relevant:
            applied.append(deepcopy(event))
            continue

        corrected = deepcopy(event)
        history: list[dict[str, Any]] = []
        # 按记录顺序依次应用，后一条纠正覆盖前一条。
        for correction in relevant:
            result = correction.get("result") or {}
            changes = result.get("corrections") or {}
            for field, value in changes.items():
                if field in CORRECTABLE_FIELDS:
                    corrected[field] = deepcopy(value)
            history.append({
                "correction_event_id": correction.get("event_id"),
                "corrections": deepcopy(changes),
                "previous": deepcopy(result.get("previous") or {}),
                "reason_code": result.get("reason_code"),
                "corrected_at": correction.get("created_at"),
            })

        corrected["scope_correction"] = {
            "corrected": True,
            "correction_count": len(history),
            "history": history,
        }
        applied.append(corrected)
    return applied


def load_corrected_learning_events(
    *,
    user_id: str | None = None,
    course_id: str | None = None,
) -> list[dict[str, Any]]:
    """加载事实并应用范围纠正。

    注意按课程过滤发生在**应用纠正之后**：一条被纠正到本课程的证据，原本可能
    记在别的课程下，先过滤会把它漏掉。
    """
    events = apply_scope_corrections(load_learning_events(user_id=user_id))
    if course_id is not None:
        events = [item for item in events if item.get("course_id") == course_id]
    return events


__all__ = [
    "CORRECTABLE_FIELDS",
    "SCOPE_CORRECTION_EVENT",
    "ScopeCorrectionError",
    "apply_scope_corrections",
    "load_corrected_learning_events",
    "record_scope_correction",
]
