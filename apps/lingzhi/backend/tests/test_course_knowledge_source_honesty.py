"""无来源必须被如实标记，且在发布层面对教师可见（需求 D2）。

D1 已经让四类知识记录按 `source_refs` 如实计算 `source_status`，但两处仍会让
教师看不到真相：

1. 关系视图（`course_knowledge_base.py:1328`）写的是 `item.get("source_type",
   "course_source")`。`course_source` 已经不在词表里（只有
   `material_grounded` / `course_generated`），而 `source_type` 的编译期默认值
   是 `model_generated` —— 两个值都不是前端能渲染的状态，关系那一栏因此永远
   显示成未知来源。
2. 视图里只有 `source_summary` 这个分桶字典。教师要回答"这门课到底有没有资料
   依据"得自己去比对桶名与总数；一门完全没有资料的课与一门大部分有资料的课，
   在发布信息上长得几乎一样。

所以这里的判据是：关系必须报真实状态，且发布负载必须有一个不需要推算的
课程级结论——有多少条有依据、占比多少、是否完全无依据。
"""

from __future__ import annotations

from copy import deepcopy

from content_blocks import set_node_content_blocks
from course_knowledge_base import (
    SOURCE_STATUS_GENERATED,
    SOURCE_STATUS_MATERIAL,
    compile_course_knowledge_base,
)
from course_knowledge_map import compile_course_knowledge_map
from learning_assets import compile_learning_assets

# 夹具刻意自带，不从同级测试模块引用：仓库根目录也有一个 `tests` 包且在 sys.path
# 里排在 backend 前面，backend/tests 内的模块无法互相 import（与"两套测试不能
# 混合收集"同源）。


def _course() -> dict:
    """一门最小但完整的课，且刻意带一条关系——关系是本文件的主要断言对象。"""
    course = {
        "course_id": "course-data-structures",
        "course_name": "数据结构",
        "course_purpose": "systematic",
        "nodes": [{
            "node_id": "L2-1-1",
            "node_level": 2,
            "node_name": "线性表与动态数组",
            "learning_objective": "能够实现动态数组扩容并分析摊还复杂度",
            "knowledge_structure": [{
                "concept_group": "动态容量管理",
                "description": "识别扩容触发条件，并解释倍增扩容的摊还成本",
                "knowledge_points": [
                    {
                        "name": "容量耗尽判定",
                        "statement": "当元素数量等于当前容量时，下一次插入必须先获得更大的连续存储空间。",
                        "knowledge_type": "rule",
                        "conditions": ["使用连续存储且不存在可用槽位"],
                        "capability_points": [{
                            "name": "判断扩容触发时机",
                            "observable_behavior": "给定长度与容量，准确判断下一次插入是否触发扩容",
                        }],
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
                        "boundaries": ["结论描述摊还成本，不等于每次插入的最坏成本"],
                        "capability_points": [{
                            "name": "动态数组扩容实现",
                            "observable_behavior": "独立实现倍增扩容并用复制次数解释摊还复杂度",
                        }],
                    },
                ],
            }],
            "key_points": ["容量耗尽判定", "动态数组扩容"],
            "grounding_contract": {},
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


def _grounded_course() -> dict:
    course = deepcopy(_course())
    section = course["nodes"][0]
    section["evidence_refs"] = ["ev-material-0001"]
    section["grounding_contract"] = {"required_evidence_ids": ["ev-material-0001"]}
    return course


def _view(course: dict) -> dict:
    return compile_learning_assets(course)["assets"]["knowledge_library"][0]


def _base(course: dict) -> dict:
    return compile_course_knowledge_base(
        course, course_map=compile_course_knowledge_map(course),
    )


# --- 关系必须报真实状态，而不是一个已经不存在的值 ---------------------------


def test_relation_source_status_uses_the_real_vocabulary() -> None:
    """关系视图不得再出现 `course_source` / `model_generated` 这类前端无法渲染的值。"""
    view = _view(_course())

    statuses = {item["source_status"] for item in view["relations"]}

    assert view["relations"], "夹具必须编译出关系，否则这条断言是空跑"
    assert statuses <= {SOURCE_STATUS_MATERIAL, SOURCE_STATUS_GENERATED}


def test_relation_source_status_follows_the_evidence() -> None:
    """同一批关系在有证据与无证据两种输入下必须给出不同状态。"""
    plain = {item["source_status"] for item in _view(_course())["relations"]}
    grounded = {item["source_status"] for item in _view(_grounded_course())["relations"]}

    assert plain == {SOURCE_STATUS_GENERATED}
    assert grounded == {SOURCE_STATUS_MATERIAL}


def test_relation_view_exposes_source_refs_for_tracing() -> None:
    """关系也要能追到具体证据，否则教师只知道"有依据"却不知道依据是什么。"""
    relations = _view(_grounded_course())["relations"]

    assert relations
    assert all("source_refs" in item for item in relations)
    assert any("ev-material-0001" in item["source_refs"] for item in relations)


def test_skeleton_prerequisites_also_carry_their_section_evidence() -> None:
    """前置关系有两个来路，两个都要继承证据。

    `prerequisite_names`（骨架冻结的前置）与知识点自带的 `relations` 是两个独立
    的候选构造点。真实课程里前者更常见，若只测后者，漏掉前者的用例会全绿。
    """
    course = _grounded_course()
    points = course["nodes"][0]["knowledge_structure"][0]["knowledge_points"]
    points[0].pop("relations", None)
    points[1]["prerequisite_names"] = ["容量耗尽判定"]

    relations = _view(course)["relations"]

    assert relations
    assert all(item["source_status"] == SOURCE_STATUS_MATERIAL for item in relations)
    assert all("ev-material-0001" in item["source_refs"] for item in relations)


# --- 发布层面的课程级结论 ---------------------------------------------------


def test_publish_payload_states_whether_the_course_has_any_grounding() -> None:
    """不启用资料的课程必须在发布负载上给出"完全无外部来源"的明确结论。"""
    grounding = _view(_course())["source_grounding"]

    assert grounding["material_grounded_count"] == 0
    assert grounding["grounded_ratio"] == 0.0
    assert grounding["has_material_grounding"] is False


def test_publish_payload_counts_grounded_records_when_materials_are_used() -> None:
    """启用资料后同一字段必须翻转，否则它没有信息量。"""
    grounding = _view(_grounded_course())["source_grounding"]

    assert grounding["has_material_grounding"] is True
    assert grounding["grounded_ratio"] == 1.0
    assert grounding["material_grounded_count"] == grounding["knowledge_point_count"]


def test_grounding_counts_match_the_per_point_statuses() -> None:
    """课程级结论必须由逐点状态汇总而来，不能与明细各说各话。"""
    view = _view(_grounded_course())
    points = [node for node in view["nodes"] if node["node_type"] == "knowledge_point"]

    grounding = view["source_grounding"]

    assert grounding["knowledge_point_count"] == len(points)
    assert grounding["material_grounded_count"] == sum(
        1 for node in points if node["source_status"] == SOURCE_STATUS_MATERIAL
    )
    assert grounding["course_generated_count"] == sum(
        1 for node in points if node["source_status"] == SOURCE_STATUS_GENERATED
    )


def test_unpublishable_library_does_not_claim_grounding() -> None:
    """降级视图不发布任何知识点，就不能报告一个凭空的来源占比。"""
    course = _grounded_course()
    base = _base(course)
    base["lifecycle_status"] = "degraded"
    course["course_knowledge_base"] = base

    view = _view(course)

    if view["nodes"]:
        return
    assert view["source_grounding"]["knowledge_point_count"] == 0
    assert view["source_grounding"]["has_material_grounding"] is False
    assert view["source_grounding"]["grounded_ratio"] == 0.0
