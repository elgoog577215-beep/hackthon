"""下游重建接线测试。

重建执行链已由 lz-lesson-plan 提供（downstream_rebuild.execute_rebuild），
本模块只是知识侧的适配器。要测的是：计划挑对了对象、真的委派给了共用
执行器、以及没有可用管线时如实报告失败而不是假装重建过。
"""

from __future__ import annotations

import pytest

from course_downstream_rebuild import (
    REBUILD_OWNERS,
    current_executor,
    plan_rebuild,
    rebuild_plan_snapshot,
    register_downstream_rebuild_executor,
    request_rebuild,
)


@pytest.fixture(autouse=True)
def _clear_executor():
    """执行器是模块级单例，测试之间必须互不影响。"""
    register_downstream_rebuild_executor(None)
    yield
    register_downstream_rebuild_executor(None)


def _downstream() -> dict:
    return {
        "items": [
            {"type": "section_content", "id": "block-1", "state": "rebuild_required"},
            {"type": "practice", "id": "q-1", "state": "rebuild_required"},
            {"type": "slide_deck", "id": "deck-1", "state": "candidate"},
            {"type": "section_content", "id": "block-2", "state": "current"},
            {"type": "practice", "id": "q-2", "state": "blocked"},
            {"type": "mastery_criterion", "id": "c-1", "state": "rebuild_required"},
        ],
    }


class _RecordingExecutor:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def rebuild_downstream(self, course_id, *, items, actor, request_id):
        self.calls.append({
            "course_id": course_id, "items": items, "actor": actor, "request_id": request_id,
        })
        return {"job_id": "job-1", "accepted": len(items)}


def test_plan_selects_only_rebuildable_states() -> None:
    """current 不用重建，blocked 不能静默重建。"""
    plan = plan_rebuild(_downstream())

    targets = {(row["type"], row["id"]) for row in plan["targets"]}
    assert ("section_content", "block-1") in targets
    assert ("practice", "q-1") in targets
    assert ("slide_deck", "deck-1") in targets
    assert ("section_content", "block-2") not in targets
    assert ("practice", "q-2") not in targets

    skipped = {row["id"]: row["skip_reason"] for row in plan["skipped"]}
    assert skipped["block-2"] == "already_current"
    assert skipped["q-2"] == "blocked"


def test_type_without_owning_pipeline_is_skipped_with_reason() -> None:
    """没有管线认领的类型要说出来，不能假装排进了队列。"""
    downstream = _downstream()
    downstream["items"].append(
        {"type": "totally_unknown", "id": "x-1", "state": "rebuild_required"},
    )
    plan = plan_rebuild(downstream)
    assert {row["id"]: row["skip_reason"] for row in plan["skipped"]}["x-1"] == (
        "no_owning_pipeline"
    )

    plan = plan_rebuild(_downstream())

    skipped = {row["id"]: row["skip_reason"] for row in plan["skipped"]}
    # mastery_criterion 由 practice 管线负责（与共用执行器的 pipeline_for 对齐）
    assert REBUILD_OWNERS["mastery_criterion"] == "practice"
    assert "c-1" not in skipped


def test_selection_narrows_the_plan() -> None:
    """教师只勾选部分对象时，只重建这部分。"""
    plan = plan_rebuild(_downstream(), object_ids=["block-1"])

    assert [row["id"] for row in plan["targets"]] == ["block-1"]
    assert plan["counts"]["targets"] == 1


def test_plan_groups_targets_by_owning_pipeline() -> None:
    """按管线分组，便于分派与显示。"""
    plan = plan_rebuild(_downstream())

    assert plan["counts"]["by_owner"] == {
        "course_content": 1,
        "practice": 2,      # q-1 与 mastery_criterion c-1
        "representation": 1,
    }


async def test_delegates_to_the_shared_executor_and_reports_per_object() -> None:
    """默认走共用执行链，逐对象回执，不再返回"管线未接入"。"""
    assert current_executor() is None

    result = await request_rebuild(
        "course-1", _downstream(), actor="teacher-1", request_id="r-1",
        course_data={"course_document": {}},
    )

    assert result["status"] == "executed"
    assert result["receipts"], "共用执行器必须给出逐对象回执"
    # 没有可用管线的对象记为失败/阻断，而不是被悄悄跳过。
    outcomes = {row["id"]: row["outcome"] for row in result["receipts"]}
    assert outcomes["block-1"] in {"stale", "blocked"}
    assert "summary" in result


async def test_nothing_to_rebuild_is_stated_not_faked() -> None:
    """没有可重建对象时明说，不返回像执行过一样的结果。"""
    result = await request_rebuild(
        "course-1",
        {"items": [{"type": "section_content", "id": "b", "state": "current"}]},
        actor="teacher-1", request_id="r-1", course_data={},
    )

    assert result["status"] == "nothing_to_rebuild"
    assert result["counts"]["targets"] == 0


async def test_registered_executor_receives_only_planned_targets() -> None:
    """接入执行器后，只把可重建的对象交给它，跳过项不外泄。"""
    executor = _RecordingExecutor()
    register_downstream_rebuild_executor(executor)

    result = await request_rebuild(
        "course-1", _downstream(), actor="teacher-1", request_id="r-1",
    )

    assert result["status"] == "requested"
    assert result["receipt"]["accepted"] == 4
    assert len(executor.calls) == 1
    call = executor.calls[0]
    assert call["course_id"] == "course-1"
    assert call["actor"] == "teacher-1"
    assert {row["id"] for row in call["items"]} == {"block-1", "q-1", "deck-1", "c-1"}


def test_snapshot_is_stable() -> None:
    """快照只保留结论与对象清单。"""
    plan = plan_rebuild(_downstream())

    snapshot = rebuild_plan_snapshot(plan)

    assert snapshot["targets"] == sorted(snapshot["targets"])
    assert "practice:q-2:blocked" in snapshot["skipped"]
    assert rebuild_plan_snapshot(plan) == snapshot
