"""下游重建命令接口测试。

这里刻意不测"重建成功"，因为重建执行链还不存在（lz-lesson-plan 分支上
record_rebuild_outcome 至今没有生产调用方）。要测的是：接口约定成立、
计划正确、执行器缺席时诚实报告而不是假装成功。
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
    plan = plan_rebuild(_downstream())

    skipped = {row["id"]: row["skip_reason"] for row in plan["skipped"]}
    assert skipped["c-1"] == "no_owning_pipeline"
    assert "mastery_criterion" not in REBUILD_OWNERS


def test_selection_narrows_the_plan() -> None:
    """教师只勾选部分对象时，只重建这部分。"""
    plan = plan_rebuild(_downstream(), object_ids=["block-1"])

    assert [row["id"] for row in plan["targets"]] == ["block-1"]
    assert plan["counts"]["targets"] == 1


def test_plan_groups_targets_by_owning_pipeline() -> None:
    """按管线分组，便于分派与显示。"""
    plan = plan_rebuild(_downstream())

    assert plan["counts"]["by_owner"] == {
        "block_regeneration": 1,
        "question_bank_rebuild": 1,
        "representation_compiler": 1,
    }


async def test_missing_executor_reports_honestly_instead_of_succeeding() -> None:
    """执行器未接入时必须明说，绝不能返回像成功一样的结果。"""
    assert current_executor() is None

    result = await request_rebuild(
        "course-1", _downstream(), actor="teacher-1", request_id="r-1",
    )

    assert result["status"] == "executor_unavailable"
    assert result["counts"]["targets"] == 3
    assert "尚未接入" in result["message"]
    assert result["executor_available"] is False
    # 仍然给出完整清单：教师至少知道将会重建什么。
    assert result["targets"]


async def test_registered_executor_receives_only_planned_targets() -> None:
    """接入执行器后，只把可重建的对象交给它，跳过项不外泄。"""
    executor = _RecordingExecutor()
    register_downstream_rebuild_executor(executor)

    result = await request_rebuild(
        "course-1", _downstream(), actor="teacher-1", request_id="r-1",
    )

    assert result["status"] == "requested"
    assert result["receipt"]["accepted"] == 3
    assert len(executor.calls) == 1
    call = executor.calls[0]
    assert call["course_id"] == "course-1"
    assert call["actor"] == "teacher-1"
    assert {row["id"] for row in call["items"]} == {"block-1", "q-1", "deck-1"}


def test_snapshot_is_stable() -> None:
    """快照只保留结论与对象清单。"""
    plan = plan_rebuild(_downstream())

    snapshot = rebuild_plan_snapshot(plan)

    assert snapshot["targets"] == sorted(snapshot["targets"])
    assert "practice:q-2:blocked" in snapshot["skipped"]
    assert rebuild_plan_snapshot(plan) == snapshot
