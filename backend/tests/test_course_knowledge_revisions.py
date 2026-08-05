"""知识独立修订与稳定身份保护测试（需求 9：知识库构建）。

这里刻意不断言 revision_id 的具体值：它是内容哈希，任何无关字段调整都会让
写死的哈希失败，制造假回归。断言集中在"哪个知识对象进入哪一组"、
"身份是否被直接改写"这类真正的行为契约上。
"""

from __future__ import annotations

from copy import deepcopy

from content_blocks import set_node_content_blocks
from course_knowledge_base import compile_course_knowledge_base
from course_knowledge_revisions import (
    changed_knowledge_ids,
    check_knowledge_identity,
    knowledge_revision_event,
    knowledge_revision_snapshot,
    knowledge_revision_vector,
)


def _course() -> dict:
    course = {
        "course_id": "course-data-structures",
        "course_name": "数据结构",
        "course_purpose": "systematic",
        "nodes": [{
            "node_id": "L2-1-1",
            "node_level": 2,
            "node_name": "线性表与动态数组",
            "learning_objective": "能够实现动态数组扩容并分析摊还复杂度",
            "objective_id": "obj-1",
            "knowledge_structure": [{
                "concept_group": "动态容量管理",
                "description": "识别扩容触发条件，并解释倍增扩容的摊还成本",
                "knowledge_points": [{
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
                }, {
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
                }],
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
    return course


def _knowledge_base() -> dict:
    return compile_course_knowledge_base(_course())


def _point_id(knowledge_base: dict, name: str) -> str:
    for point in knowledge_base["knowledge_points"]:
        if point.get("name") == name:
            return point["knowledge_id"]
    raise AssertionError(f"知识点 {name} 不存在")


def test_revision_vector_addresses_every_knowledge_entity_kind():
    """知识库不再只有一个不透明修订号：每个实体都可单独寻址。"""
    knowledge_base = _knowledge_base()
    vector = knowledge_revision_vector(knowledge_base)

    assert vector.course_id == "course-data-structures"
    assert vector.knowledge_base_revision_id == knowledge_base["revision_id"]
    assert vector.lifecycle_status == knowledge_base["lifecycle_status"]

    prefixes = {key.partition(":")[0] for key in vector.revisions}
    assert {
        "concept_group", "point", "skill", "misconception",
        "criterion", "relation", "binding",
    } <= prefixes
    assert "course_knowledge_base" in vector.revisions

    capacity_id = _point_id(knowledge_base, "容量耗尽判定")
    assert f"point:{capacity_id}" in vector.revisions


def test_unchanged_knowledge_base_produces_empty_revision_event():
    """未修改的知识库不得报出任何变化，否则每次读取都会触发下游重建。"""
    knowledge_base = _knowledge_base()
    event = knowledge_revision_event(knowledge_base, deepcopy(knowledge_base))

    assert event.changed_source_keys == []
    assert event.added_source_keys == []
    assert event.removed_source_keys == []
    assert event.identity_preserved
    assert changed_knowledge_ids(event) == []


def test_editing_one_statement_localizes_impact_to_that_point():
    """改一个知识点的陈述，只有该点（与整库汇总键）进入变化集。"""
    before = _knowledge_base()
    after = deepcopy(before)
    target_id = _point_id(after, "容量耗尽判定")
    other_id = _point_id(after, "动态数组扩容")
    for point in after["knowledge_points"]:
        if point["knowledge_id"] == target_id:
            point["statement"] = "容量与长度相等时，插入前必须先扩容。"
            point["revision_id"] = "ckpr_edited"
    after["revision_id"] = "ckbr_edited"

    event = knowledge_revision_event(before, after, operation="update_statement")

    assert f"point:{target_id}" in event.changed_source_keys
    assert f"point:{other_id}" not in event.changed_source_keys
    assert changed_knowledge_ids(event) == [target_id]
    assert event.identity_preserved


def test_split_without_identity_map_is_reported_as_dropped_identity():
    """拆分知识点却不给旧新映射，历史作答会失去指向，必须报出违规。"""
    before = _knowledge_base()
    after = deepcopy(before)
    removed_id = _point_id(after, "动态数组扩容")
    after["knowledge_points"] = [
        point for point in after["knowledge_points"]
        if point["knowledge_id"] != removed_id
    ]

    event = knowledge_revision_event(before, after, operation="split_point")

    assert not event.identity_preserved
    codes = [item.code for item in event.identity_violations]
    assert "knowledge_identity_dropped" in codes
    assert f"point:{removed_id}" in event.removed_source_keys


def test_split_with_identity_map_preserves_history_and_reports_both_ids():
    """带映射的拆分是合法演进：旧 ID 仍可解释，新旧 ID 都进入影响面。"""
    before = _knowledge_base()
    after = deepcopy(before)
    old_id = _point_id(after, "动态数组扩容")
    kept = [
        point for point in after["knowledge_points"]
        if point["knowledge_id"] != old_id
    ]
    source = next(
        point for point in before["knowledge_points"]
        if point["knowledge_id"] == old_id
    )
    new_points = []
    for suffix in ("a", "b"):
        clone = deepcopy(source)
        clone["knowledge_id"] = f"{old_id}-{suffix}"
        clone["revision_id"] = f"ckpr_{suffix}"
        new_points.append(clone)
    after["knowledge_points"] = kept + new_points

    event = knowledge_revision_event(
        before,
        after,
        operation="split_point",
        identity_map={old_id: [f"{old_id}-a", f"{old_id}-b"]},
    )

    assert event.identity_preserved
    assert event.identity_map == {old_id: [f"{old_id}-a", f"{old_id}-b"]}
    assert set(changed_knowledge_ids(event)) == {
        old_id, f"{old_id}-a", f"{old_id}-b",
    }


def test_identity_map_pointing_at_missing_target_is_rejected():
    """映射目标不存在等于没有映射，不能靠写一条映射就宣称身份已迁移。"""
    before = _knowledge_base()
    after = deepcopy(before)
    old_id = _point_id(after, "动态数组扩容")
    after["knowledge_points"] = [
        point for point in after["knowledge_points"]
        if point["knowledge_id"] != old_id
    ]

    event = knowledge_revision_event(
        before, after, identity_map={old_id: ["ckp_not_in_base"]},
    )

    assert not event.identity_preserved
    assert "knowledge_identity_map_unresolved" in [
        item.code for item in event.identity_violations
    ]


def test_rewriting_concept_group_anchor_in_place_is_a_violation():
    """稳定身份锚点只能通过映射迁移，不得原地改写。"""
    before = _knowledge_base()
    after = deepcopy(before)
    target_id = _point_id(after, "容量耗尽判定")
    for point in after["knowledge_points"]:
        if point["knowledge_id"] == target_id:
            point["primary_concept_group_id"] = "ckg_somewhere_else"

    violations = check_knowledge_identity(before, after)

    assert [item.code for item in violations] == ["knowledge_anchor_rewritten"]
    assert violations[0].entity_id == target_id


def test_dropping_source_binding_on_active_point_is_a_violation():
    """来源绑定被直接删掉会让知识点失去课程位置，必须报出。"""
    before = _knowledge_base()
    after = deepcopy(before)
    target_id = _point_id(after, "容量耗尽判定")
    for point in after["knowledge_points"]:
        if point["knowledge_id"] == target_id:
            point["section_refs"] = []

    violations = check_knowledge_identity(before, after)

    assert [item.code for item in violations] == ["knowledge_source_binding_dropped"]


def test_retired_point_may_release_its_source_binding():
    """已退役的知识点释放来源绑定是正常生命周期，不该误报。"""
    before = _knowledge_base()
    after = deepcopy(before)
    target_id = _point_id(after, "容量耗尽判定")
    for point in after["knowledge_points"]:
        if point["knowledge_id"] == target_id:
            point["status"] = "retired"
            point["section_refs"] = []

    assert check_knowledge_identity(before, after) == []


def test_relation_change_is_addressable_without_touching_points():
    """关系变化独立可见：改一条前置依赖不应把知识点也标成已变。"""
    before = _knowledge_base()
    after = deepcopy(before)
    assert after["relations"], "测试前提：编译结果里应有六类关系中的边"
    after["relations"][0]["reason"] = "补充更精确的前置理由"
    after["relations"][0]["revision_id"] = "ckrelr_edited"

    event = knowledge_revision_event(before, after, operation="update_relation")

    changed_prefixes = {key.partition(":")[0] for key in event.changed_source_keys}
    assert "relation" in changed_prefixes
    assert "point" not in changed_prefixes
    assert changed_knowledge_ids(event) == []


def test_revision_snapshot_is_stable_and_readable():
    """快照只保留分组与受影响 ID，不 dump 整棵对象树。"""
    before = _knowledge_base()
    after = deepcopy(before)
    target_id = _point_id(after, "容量耗尽判定")
    for point in after["knowledge_points"]:
        if point["knowledge_id"] == target_id:
            point["statement"] = "改写后的陈述。"
            point["revision_id"] = "ckpr_edited"
    after["revision_id"] = "ckbr_edited"

    snapshot = knowledge_revision_snapshot(
        knowledge_revision_event(before, after, operation="update_statement"),
    )

    assert snapshot == {
        "operation": "update_statement",
        "changed": {
            "course_knowledge_base": ["course_knowledge_base"],
            "point": [target_id],
        },
        "added": {},
        "removed": {},
        "identity_map": {},
        "identity_violations": [],
    }


def test_revision_event_refuses_to_span_two_courses():
    """一次知识修订事件不得横跨两门课程的知识库。"""
    before = _knowledge_base()
    after = deepcopy(before)
    after["course_id"] = "course-other"

    try:
        knowledge_revision_event(before, after)
    except ValueError as error:
        assert "multiple courses" in str(error)
    else:
        raise AssertionError("跨课程知识修订事件必须被拒绝")
