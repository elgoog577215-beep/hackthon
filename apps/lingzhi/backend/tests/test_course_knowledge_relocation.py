"""候选重定位测试（任务书缺口：候选重定位；OpenSpec 7.3 / 7.8）。

判据不是"能重算"，而是"该重定位的重定位、该冲突的冲突"。一个把所有情况
都重算成功的实现，会静默丢掉别人的改动；一个把所有情况都判冲突的实现，
等于没做重定位。因此每条用例都同时断言 outcome 与原因。
"""

from __future__ import annotations

from copy import deepcopy

from content_blocks import set_node_content_blocks
from course_knowledge_base import compile_course_knowledge_base
from course_knowledge_map import compile_course_knowledge_map
from course_knowledge_point_edits import apply_point_edit
from course_knowledge_relocation import (
    relocate_point_edit_candidate,
    relocation_snapshot,
)


def _knowledge_points() -> list[dict]:
    return [
        {
            "name": "容量耗尽判定",
            "statement": "当元素数量等于当前容量时，下一次插入必须先获得更大的连续存储空间。",
            "knowledge_type": "rule",
            "conditions": ["使用连续存储且不存在可用槽位"],
            "boundaries": ["尚有空闲槽位时不触发扩容"],
            "capability_points": [{
                "name": "判断扩容触发时机",
                "observable_behavior": "给定长度与容量，准确判断下一次插入是否触发扩容",
            }],
            "mastery_criteria": [{
                "name": "扩容触发判断达标",
                "observable_performance": "在不同长度与容量组合中独立判断扩容时机并说明依据",
                "verification_method": "使用至少三个边界案例进行判断并核对结果",
            }],
            "entry_reason": "这是理解动态数组扩容机制的课程入口。",
            "aliases": ["满容量判定"],
            "relations": [{
                "target_name": "动态数组扩容",
                "relation_type": "prerequisite",
                "reason": "必须先识别容量耗尽，才能确定何时执行扩容",
            }],
        },
        {
            "name": "动态数组扩容",
            "statement": "倍增扩容把少数 O(n) 复制成本分摊到一系列插入，使平均单次插入保持常数阶。",
            "knowledge_type": "principle",
            "conditions": ["扩容因子大于 1 且按几何级数增长"],
            "boundaries": ["结论描述摊还成本，不等于每次插入的最坏成本"],
            "capability_points": [{
                "name": "动态数组扩容实现",
                "observable_behavior": "独立实现倍增扩容并用复制次数解释摊还复杂度",
            }],
            "misconceptions": [{
                "name": "把单次复制成本当作每次插入成本",
                "observable_error_pattern": "看到一次扩容需要复制 n 个元素，就断言每次插入都是 O(n)",
                "discrimination": "区分单次操作最坏成本与一系列操作的摊还成本",
                "repair_strategy": "列出连续插入过程中的扩容位置与累计复制次数后重新计算平均成本",
            }],
            "mastery_criteria": [{
                "name": "扩容实现与分析达标",
                "observable_performance": "独立实现倍增扩容，并正确说明最坏成本与摊还成本的区别",
                "verification_method": "运行连续插入测试并提交复杂度推导",
            }],
            "aliases": ["可变长数组"],
        },
    ]


def _course() -> dict:
    course = {
        "course_id": "course-1",
        "course_name": "数据结构",
        "course_purpose": "systematic",
        "nodes": [{
            "node_id": "section-1",
            "node_level": 2,
            "node_name": "线性表与动态数组",
            "learning_objective": "能够实现动态数组扩容并分析摊还复杂度",
            "knowledge_structure": [{
                "concept_group": "动态容量管理",
                "description": "识别扩容触发条件，并解释倍增扩容的摊还成本",
                "knowledge_points": _knowledge_points(),
            }],
            "key_points": ["容量耗尽判定", "动态数组扩容"],
            "content_blocks": [],
            "generation_status": "completed",
            "node_content": (
                "## 容量耗尽判定\n\n根据长度与容量识别扩容触发时机。\n\n"
                "## 动态数组扩容\n\n实现倍增扩容，并区分最坏成本与摊还成本。"
            ),
        }],
    }
    set_node_content_blocks(course["nodes"][0], course["nodes"][0]["node_content"])
    course["course_knowledge_base"] = compile_course_knowledge_base(
        course, course_map=compile_course_knowledge_map(course),
    )
    return course


def _point_id(course: dict, name: str) -> str:
    for point in course["course_knowledge_base"]["knowledge_points"]:
        if point["name"] == name:
            return point["knowledge_id"]
    raise AssertionError(f"知识点 {name} 不存在")


def _pending(course: dict, name: str = "容量耗尽判定") -> dict:
    """一个待确认候选的最小描述（教师填好但还没确认）。"""
    return {
        "knowledge_id": _point_id(course, name),
        "operation": "revise_knowledge_point",
        "value": "长度等于容量时，插入前必须先扩容。",
        "reason": "表述更精确",
        "base_knowledge_revision_id": course["course_knowledge_base"]["revision_id"],
    }


def test_unchanged_base_keeps_the_candidate_valid() -> None:
    """知识库没动时不该谎称重定位过。"""
    course = _course()

    result = relocate_point_edit_candidate(course, **_pending(course))

    assert result["outcome"] == "unchanged"
    assert result["reason"] == "base_revision_unchanged"
    assert result["candidate"]["confirmable"] is True


def test_unrelated_edit_relocates_instead_of_discarding() -> None:
    """别人改了另一个知识点，我的候选应被重定位而不是作废。

    这正是"过期即拒"最伤人的场景：教师的工作因为同事先保存而消失。
    """
    course = _course()
    pending = _pending(course)
    before = deepcopy(course["course_knowledge_base"])

    # 他人修改了另一个知识点，整库修订号随之变化。
    course["course_knowledge_base"] = apply_point_edit(
        before,
        knowledge_id=_point_id(course, "动态数组扩容"),
        operation="revise_knowledge_point",
        value="倍增扩容把复制成本摊还到一系列插入。",
    )
    assert course["course_knowledge_base"]["revision_id"] != pending["base_knowledge_revision_id"]

    result = relocate_point_edit_candidate(
        course, previous_knowledge_base=before, **pending,
    )

    assert result["outcome"] == "relocated"
    assert result["reason"] == "recomputed_on_new_base"
    assert result["candidate"]["confirmable"] is True
    # 重定位后的候选钉在新基线上，确认时才不会再次被判过期。
    assert result["candidate"]["base_knowledge_revision_id"] == (
        course["course_knowledge_base"]["revision_id"]
    )
    assert result["previous_base_knowledge_revision_id"] == pending["base_knowledge_revision_id"]


def test_same_field_edited_by_someone_else_is_a_conflict() -> None:
    """同一字段被他人改过时必须报冲突——重算会静默丢掉对方的改动。"""
    course = _course()
    pending = _pending(course)
    before = deepcopy(course["course_knowledge_base"])

    course["course_knowledge_base"] = apply_point_edit(
        before,
        knowledge_id=pending["knowledge_id"],
        operation="revise_knowledge_point",
        value="他人已经改写过的陈述。",
    )

    result = relocate_point_edit_candidate(
        course, previous_knowledge_base=before, **pending,
    )

    assert result["outcome"] == "conflict"
    assert result["reason"] == "target_field_changed"
    assert result["candidate"] is None
    assert result["current_value"] == "他人已经改写过的陈述。"
    assert result["field"] == "statement"


def test_split_target_reports_identity_migration_with_successors() -> None:
    """目标被拆分时报身份迁移，并给出后继 ID，教师才知道改到哪去。

    后继来自已确认知识命令写下的 course_knowledge_revision_log。区分
    "被拆分成这两个"和"没了"很重要：前者教师能接着改，后者只能放弃。
    """
    course = _course()
    pending = _pending(course)
    before = deepcopy(course["course_knowledge_base"])

    old_id = pending["knowledge_id"]
    source = next(
        item for item in before["knowledge_points"] if item["knowledge_id"] == old_id
    )
    after = deepcopy(before)
    after["knowledge_points"] = [
        item for item in after["knowledge_points"] if item["knowledge_id"] != old_id
    ]
    for suffix in ("a", "b"):
        clone = deepcopy(source)
        clone["knowledge_id"] = f"{old_id}-{suffix}"
        clone["revision_id"] = f"ckpr_{suffix}"
        after["knowledge_points"].append(clone)
    after["revision_id"] = "ckbr_split"
    course["course_knowledge_base"] = after
    # 拆分是通过已确认的知识命令发生的，映射留在修订日志里。
    course["course_knowledge_revision_log"] = [{
        "operation": "split_knowledge_point",
        "identity_map": {old_id: [f"{old_id}-a", f"{old_id}-b"]},
    }]

    result = relocate_point_edit_candidate(
        course, previous_knowledge_base=before, **pending,
    )

    assert result["outcome"] == "conflict"
    assert result["reason"] == "target_identity_moved"
    assert result["successor_knowledge_ids"] == [f"{old_id}-a", f"{old_id}-b"]
    assert result["candidate"] is None


def test_missing_target_without_mapping_is_plain_disappearance() -> None:
    """没有映射记录时只能报"已不存在"，不能编造后继。"""
    course = _course()
    pending = _pending(course)
    before = deepcopy(course["course_knowledge_base"])
    after = deepcopy(before)
    after["knowledge_points"] = [
        item for item in after["knowledge_points"]
        if item["knowledge_id"] != pending["knowledge_id"]
    ]
    after["revision_id"] = "ckbr_gone"
    course["course_knowledge_base"] = after

    result = relocate_point_edit_candidate(
        course, previous_knowledge_base=before, **pending,
    )

    assert result["reason"] == "target_missing"
    assert "successor_knowledge_ids" not in result


def test_retired_target_is_reported_as_missing() -> None:
    """目标被删除后不能假装还能改。"""
    course = _course()
    pending = _pending(course)
    before = deepcopy(course["course_knowledge_base"])
    after = deepcopy(before)
    after["knowledge_points"] = [
        item for item in after["knowledge_points"]
        if item["knowledge_id"] != pending["knowledge_id"]
    ]
    after["revision_id"] = "ckbr_removed"
    course["course_knowledge_base"] = after

    result = relocate_point_edit_candidate(
        course, previous_knowledge_base=before, **pending,
    )

    assert result["outcome"] == "conflict"
    assert result["reason"] == "target_missing"
    assert result["knowledge_id"] == pending["knowledge_id"]


def test_relocation_never_applies_anything() -> None:
    """重定位只产出待确认候选，绝不落盘。"""
    course = _course()
    pending = _pending(course)
    before = deepcopy(course["course_knowledge_base"])
    course["course_knowledge_base"] = apply_point_edit(
        before,
        knowledge_id=_point_id(course, "动态数组扩容"),
        operation="revise_knowledge_point",
        value="改写另一个知识点。",
    )
    snapshot = deepcopy(course["course_knowledge_base"])

    result = relocate_point_edit_candidate(
        course, previous_knowledge_base=before, **pending,
    )

    assert result["outcome"] == "relocated"
    # 活动知识库一个字节都不该变。
    assert course["course_knowledge_base"] == snapshot
    # 候选仍需确认，重定位不等于已应用。
    assert result["candidate"]["confirmable"] is True


def test_unsupported_operation_is_refused() -> None:
    """不支持重定位的操作要说清楚，不能装作重定位成功。"""
    course = _course()
    pending = _pending(course)
    pending["operation"] = "split_knowledge_point"

    result = relocate_point_edit_candidate(course, **pending)

    assert result["outcome"] == "conflict"
    assert result["reason"] == "operation_unsupported"


def test_relocation_snapshot_is_stable() -> None:
    """快照只保留结论，不 dump 整棵候选树。"""
    course = _course()
    result = relocate_point_edit_candidate(course, **_pending(course))

    snapshot = relocation_snapshot(result)

    assert snapshot == {
        "outcome": "unchanged",
        "reason": "base_revision_unchanged",
        "confirmable": True,
    }
    assert relocation_snapshot(result) == snapshot
