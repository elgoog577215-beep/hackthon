"""共用下游重建执行链（tasks 6.2–6.6）。

这里守的核心是三条：
1. **失败不覆盖最后可用产物**（6.3）：重建失败时旧正文/练习/PPT 必须继续可读。
2. **逐对象回执**（6.4）：`content_changed` / `source_verified` / `stale` /
   `blocked` / `unchanged` 五态可分辨，教师要能区分「确认没事」与「漏了」。
3. **教案侧与知识侧共用同一个执行器**（不建平行重建机制）：两边的影响报告
   共享 `IMPACT_GROUPS` 形状，重建这一端也必须只有一条路径，否则同一个正文块
   会有两套失败语义和两份「最后可用产物」记录。
"""
from __future__ import annotations

from copy import deepcopy

import pytest

from downstream_rebuild import (
    RECEIPT_OUTCOMES,
    execute_rebuild,
    pipeline_for,
    plan_rebuild,
    rebuild_summary,
)
from teaching_plan_impact import build_downstream_state


def _impact(**groups) -> dict:
    report = {group: [] for group in
              ("changed", "needs_regeneration", "stale", "unchanged", "blocked")}
    report.update(groups)
    report["blocking"] = bool(report.get("blocked"))
    return report


def _downstream(**groups) -> dict:
    return build_downstream_state(_impact(**groups), plan_revision_id="tpr_1")


def _item(item_type: str, item_id: str, reason: str = "变更") -> dict:
    return {"type": item_type, "id": item_id, "reason": reason}


# --- 工作清单 ---------------------------------------------------------------


def test_only_rebuild_required_items_enter_the_worklist() -> None:
    """current / candidate / blocked / lock_conflict 都不该被静默重建。"""
    downstream = build_downstream_state(
        _impact(
            needs_regeneration=[_item("section_content", "s1")],
            changed=[_item("teaching_plan", "overall")],
            blocked=[_item("unknown", "mystery")],
        ),
        plan_revision_id="tpr_1",
        locked_object_ids=["s-locked"],
    )
    downstream["items"].append({
        "type": "slide_deck", "id": "s-locked", "state": "lock_conflict",
        "impact_group": "needs_regeneration", "reason": "其他链路正在写",
    })

    work = plan_rebuild(downstream)
    ids = {entry["id"] for entry in work}
    assert "s1" in ids
    assert "mystery" not in ids, "blocked 必须由人判断，不能静默重建"
    assert "s-locked" not in ids, "锁定冲突不抢锁"
    assert "overall" not in ids, "changed 不需要重建"


def test_worklist_is_deterministic() -> None:
    """同一份影响报告每次产出同样的重建序列，便于复现与幂等。"""
    downstream = _downstream(needs_regeneration=[
        _item("slide_deck", "b"), _item("section_content", "a"), _item("practice", "c"),
    ])
    first = [(e["type"], e["id"]) for e in plan_rebuild(downstream)]
    second = [(e["type"], e["id"]) for e in plan_rebuild(deepcopy(downstream))]
    assert first == second


def test_pipeline_routing_covers_both_plan_and_knowledge_downstream_types() -> None:
    assert pipeline_for("slide_deck") == "representation"
    assert pipeline_for("section_content") == "course_content"
    assert pipeline_for("practice") == "practice"
    # 知识侧的下游类型也要能路由——两边共用同一个执行器。
    assert pipeline_for("knowledge_binding") == "knowledge"
    assert pipeline_for("nonsense") == "unsupported"


# --- 6.3 失败保留最后可用产物 ------------------------------------------------


def test_failed_rebuild_keeps_the_last_usable_artifact_readable() -> None:
    downstream = _downstream(needs_regeneration=[_item("slide_deck", "deck-1")])
    # 假装这份 PPT 之前是可读的
    for item in downstream["items"]:
        if item["id"] == "deck-1":
            item["last_available"] = {
                "type": "slide_deck", "id": "deck-1",
                "revision": "old-rev", "variant_key": "", "readable": True,
            }

    result = execute_rebuild(downstream, runners={
        "representation": lambda entry: {"status": "failed", "error": "模型超时"},
    })

    item = next(i for i in result["downstream"]["items"] if i["id"] == "deck-1")
    assert item["state"] == "rebuild_required", "失败后仍待重建"
    assert item["last_available"]["revision"] == "old-rev", "旧产物不能被失败覆盖"
    assert item["last_available"]["readable"] is True
    assert "模型超时" in item["last_build_error"]
    receipt = next(r for r in result["receipts"] if r["id"] == "deck-1")
    assert receipt["outcome"] == "stale"
    assert receipt["readable_fallback"] is True


def test_runner_exception_is_contained_and_does_not_abort_the_batch() -> None:
    """一个对象炸了不能让整批停下——否则一次失败就卡住所有下游。"""
    downstream = _downstream(needs_regeneration=[
        _item("slide_deck", "deck-1"), _item("slide_deck", "deck-2"),
    ])

    def runner(entry):
        if entry["id"] == "deck-1":
            raise RuntimeError("渲染器崩溃")
        return {"status": "succeeded", "revision": "new-rev"}

    result = execute_rebuild(downstream, runners={"representation": runner})
    states = {i["id"]: i["state"] for i in result["downstream"]["items"]}
    assert states["deck-1"] == "rebuild_required"
    assert states["deck-2"] == "current", "另一个对象仍然重建成功"


def test_repeated_failures_never_downgrade_the_preserved_version() -> None:
    downstream = _downstream(needs_regeneration=[_item("practice", "p1")])
    for item in downstream["items"]:
        if item["id"] == "p1":
            item["last_available"] = {
                "type": "practice", "id": "p1", "revision": "v1",
                "variant_key": "", "readable": True,
            }

    for _ in range(3):
        downstream = execute_rebuild(downstream, runners={
            "practice": lambda entry: {"status": "failed", "error": "失败"},
        })["downstream"]

    item = next(i for i in downstream["items"] if i["id"] == "p1")
    assert item["last_available"]["revision"] == "v1"


# --- 6.4 逐对象回执 ----------------------------------------------------------


def test_receipts_distinguish_all_five_outcomes() -> None:
    downstream = build_downstream_state(
        _impact(
            needs_regeneration=[
                _item("section_content", "changed-one"),
                _item("practice", "verified-one"),
                _item("slide_deck", "failed-one"),
            ],
            unchanged=[_item("section_content", "untouched-one")],
            blocked=[_item("unknown", "blocked-one")],
        ),
        plan_revision_id="tpr_1",
    )

    def content(entry):
        return {"status": "succeeded", "revision": "rev-new"}

    def practice(entry):
        return {"status": "unchanged"}

    def representation(entry):
        return {"status": "failed", "error": "配图缺失"}

    result = execute_rebuild(downstream, runners={
        "course_content": content, "practice": practice, "representation": representation,
    })
    by_id = {r["id"]: r["outcome"] for r in result["receipts"]}

    assert by_id["changed-one"] == "content_changed"
    assert by_id["verified-one"] == "source_verified", "核对后无需变化不是失败"
    assert by_id["failed-one"] == "stale"
    assert by_id["untouched-one"] == "unchanged", "不受影响的对象也要出现在回执里"
    assert by_id["blocked-one"] == "blocked"
    # 五态都用上了，counts 能对上
    assert set(result["counts"]) == set(RECEIPT_OUTCOMES)
    assert result["counts"]["content_changed"] == 1
    assert result["counts"]["source_verified"] == 1


def test_unaffected_objects_appear_so_teachers_can_tell_safe_from_missed() -> None:
    downstream = _downstream(
        needs_regeneration=[_item("section_content", "s1")],
        unchanged=[_item("section_content", "s2"), _item("practice", "p9")],
    )
    result = execute_rebuild(downstream, runners={
        "course_content": lambda entry: {"status": "succeeded", "revision": "r"},
    })
    ids = {r["id"] for r in result["receipts"]}
    assert {"s1", "s2", "p9"} <= ids


# --- 6.5 冲突与并发边界 ------------------------------------------------------


def test_locked_objects_are_skipped_without_rebuilding() -> None:
    """另一条链路正在写同一对象时不抢锁——抢锁会让两边互相覆盖。"""
    downstream = _downstream(needs_regeneration=[
        _item("section_content", "s1"), _item("section_content", "s2"),
    ])
    calls: list[str] = []

    def runner(entry):
        calls.append(entry["id"])
        return {"status": "succeeded", "revision": "r"}

    result = execute_rebuild(
        downstream, runners={"course_content": runner}, locked_object_ids=["s1"],
    )
    assert calls == ["s2"], "被锁对象不能被调用重建"
    receipt = next(r for r in result["receipts"] if r["id"] == "s1")
    assert receipt["outcome"] == "stale"
    assert "其他链路" in receipt["detail"]


def test_missing_pipeline_is_blocked_not_silently_skipped() -> None:
    downstream = _downstream(needs_regeneration=[_item("weird_type", "x1")])
    result = execute_rebuild(downstream, runners={})
    receipt = next(r for r in result["receipts"] if r["id"] == "x1")
    assert receipt["outcome"] == "blocked"
    assert "禁止静默跳过" in receipt["detail"]


# --- 6.2 定向重建候选 --------------------------------------------------------


def test_candidate_only_mode_waits_for_teacher_confirmation() -> None:
    """6.2：生成定向重建候选而不是直接改正式产物。"""
    downstream = _downstream(needs_regeneration=[_item("section_content", "s1")])
    result = execute_rebuild(
        downstream,
        runners={"course_content": lambda entry: {"status": "succeeded", "revision": "cand-1"}},
        candidate_only=True,
    )
    item = next(i for i in result["downstream"]["items"] if i["id"] == "s1")
    assert item["state"] == "candidate"
    assert item["candidate_revision"] == "cand-1"


def test_only_types_and_only_ids_scope_the_rebuild() -> None:
    """定向重建：未受影响对象复用原修订，不做无谓重建。"""
    downstream = _downstream(needs_regeneration=[
        _item("section_content", "s1"), _item("slide_deck", "d1"),
    ])
    calls: list[str] = []

    def runner(entry):
        calls.append(entry["id"])
        return {"status": "succeeded", "revision": "r"}

    execute_rebuild(
        downstream,
        runners={"course_content": runner, "representation": runner},
        only_types=["section_content"],
    )
    assert calls == ["s1"]


# --- 6.6 重复应用与幂等 ------------------------------------------------------


def test_rebuilding_an_already_current_object_is_a_no_op() -> None:
    """重复应用不该反复重建：第一轮成功后对象已是 current，第二轮不再入列。"""
    downstream = _downstream(needs_regeneration=[_item("section_content", "s1")])
    calls: list[str] = []

    def runner(entry):
        calls.append(entry["id"])
        return {"status": "succeeded", "revision": "r"}

    first = execute_rebuild(downstream, runners={"course_content": runner})
    second = execute_rebuild(first["downstream"], runners={"course_content": runner})

    assert calls == ["s1"], "第二轮不应再次重建"
    assert rebuild_summary(second)["downstream_counts"]["current"] >= 1


def test_summary_reports_both_receipt_and_lifecycle_counts() -> None:
    downstream = _downstream(needs_regeneration=[_item("section_content", "s1")])
    result = execute_rebuild(downstream, runners={
        "course_content": lambda entry: {"status": "succeeded", "revision": "r"},
    })
    summary = rebuild_summary(result)
    assert summary["counts"]["content_changed"] == 1
    assert "current" in summary["downstream_counts"]


# --- 共用性：知识侧影响报告走同一条执行链 -------------------------------------


def test_knowledge_side_impact_uses_the_same_executor() -> None:
    """知识侧与教案侧共用同一个执行器，不建平行重建机制。

    两边的影响报告共享 IMPACT_GROUPS 形状，所以这里直接用「知识变化」
    形态的报告喂同一个执行器，结果语义必须与教案侧完全一致。
    """
    knowledge_impact = _impact(
        needs_regeneration=[
            {"type": "section_content", "id": "s1", "reason": "知识陈述变化"},
            {"type": "knowledge_binding", "id": "kb-1", "reason": "绑定需重编译"},
        ],
        unchanged=[{"type": "practice", "id": "p-untouched", "reason": "未引用该知识"}],
    )
    downstream = build_downstream_state(knowledge_impact, plan_revision_id="kr_1")

    result = execute_rebuild(downstream, runners={
        "course_content": lambda entry: {"status": "succeeded", "revision": "r1"},
        "knowledge": lambda entry: {"status": "succeeded", "revision": "r2"},
    })
    by_id = {r["id"]: r["outcome"] for r in result["receipts"]}
    assert by_id["s1"] == "content_changed"
    assert by_id["kb-1"] == "content_changed"
    assert by_id["p-untouched"] == "unchanged"
    # 回执 schema 与教案侧同一份，前端只需实现一套渲染。
    assert result["schema_version"] == "downstream_rebuild_receipt_v1"
