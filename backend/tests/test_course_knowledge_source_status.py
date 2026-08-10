"""知识来源状态必须如实计算，不能恒为 `course_source`（需求 D1 第一层）。

原实现在视图投影处把四类记录的 `source_status` 全部硬编码成 `course_source`，
`source_summary` 也直接是 `{"course_source": 点数}`。后果不是"标签不准"这么轻：
教师界面上"有资料依据"和"模型凭通用知识写的"看起来完全一样，来源落地率恒为 0
却无人可见。判据因此是同一门课在"有证据"与"无证据"两种输入下必须给出不同的
状态，且 `source_refs` 必须真的落到视图里，让教师能追到具体证据。

这里只区分两个值：`material_grounded`（有可追溯证据）与 `course_generated`
（没有）。仓库里全部 evidence_id 都由上传文档派生（material_evidence.py），
不存在联网检索来源，所以不造一个永远不会出现的 `web_grounded`。
"""

from __future__ import annotations

from copy import deepcopy

from content_blocks import set_node_content_blocks
from course_knowledge_base import compile_course_knowledge_base
from course_knowledge_map import compile_course_knowledge_map
from learning_assets import compile_learning_assets

# 故意不从 tests.test_course_knowledge_base 借用课程夹具：仓库根目录也有一个名为
# `tests` 的包，且 sys.path 里根目录排在 backend 前面，所以 backend/tests 内的模块
# 无法用 `tests.` 前缀引用同级模块（这也是"两套测试不能混合收集"的同一个成因）。


def _course() -> dict:
    """一门最小但完整的课：概念组 + 两个知识点，带易错点与掌握标准。

    知识库是教案的确定性投影，所以来源状态只能由小节上的证据决定；这里刻意
    不挂任何 evidence，作为"无来源"一侧的输入。
    """
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
                        "misconceptions": [{
                            "name": "把容量当作长度",
                            "observable_error_pattern": "用容量代替长度参与判断，得出提前扩容的结论",
                            "discrimination": "区分已使用长度与已分配容量",
                            "repair_strategy": "在同一个例子里分别标出长度与容量后重新判断",
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
                        "mastery_criteria": [{
                            "name": "扩容实现与分析达标",
                            "observable_performance": "独立实现倍增扩容，并正确说明最坏成本与摊还成本的区别",
                            "verification_method": "运行连续插入测试并提交复杂度推导",
                        }],
                        "misconceptions": [{
                            "name": "把单次复制成本当作每次插入成本",
                            "observable_error_pattern": "看到一次扩容复制 n 个元素，就断言每次插入都是 O(n)",
                            "discrimination": "区分单次操作最坏成本与一系列操作的摊还成本",
                            "repair_strategy": "列出连续插入中的扩容位置与累计复制次数后重新计算平均成本",
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
    """同一门课，但小节挂上可追溯的资料证据。"""
    course = deepcopy(_course())
    section = course["nodes"][0]
    section["evidence_refs"] = ["ev-material-0001"]
    section["grounding_contract"] = {
        "required_evidence_ids": ["ev-material-0001"],
        "optional_evidence_ids": ["ev-material-0002"],
    }
    return course


def _view(course: dict) -> dict:
    return compile_learning_assets(course)["assets"]["knowledge_library"][0]


def _points(view: dict) -> list[dict]:
    return [node for node in view["nodes"] if node["node_type"] == "knowledge_point"]


def test_knowledge_without_evidence_is_reported_as_course_generated() -> None:
    """没有资料证据时必须如实说"这是课程生成的"，不能冒充有来源。"""
    view = _view(_course())

    statuses = {node["source_status"] for node in _points(view)}

    assert statuses == {"course_generated"}


def test_knowledge_with_evidence_is_reported_as_material_grounded() -> None:
    """挂了证据的知识点必须变成另一个状态 —— 否则这个字段没有信息量。"""
    view = _view(_grounded_course())

    statuses = {node["source_status"] for node in _points(view)}

    assert statuses == {"material_grounded"}


def test_source_status_distinguishes_the_two_inputs() -> None:
    """同一门课两种输入必须给出不同结果：这是"如实计算"的最小证据。"""
    plain = {node["name"]: node["source_status"] for node in _points(_view(_course()))}
    grounded = {
        node["name"]: node["source_status"] for node in _points(_view(_grounded_course()))
    }

    assert plain
    assert plain.keys() == grounded.keys()
    assert all(plain[name] != grounded[name] for name in plain)


def test_source_refs_are_projected_so_teachers_can_trace_evidence() -> None:
    """光有状态不够：教师要能看到具体是哪条证据。"""
    view = _view(_grounded_course())

    point = next(node for node in _points(view) if node["name"] == "动态数组扩容")

    assert "ev-material-0001" in point["source_refs"]
    assert all("source_refs" in node for node in _points(view))


def test_source_refs_are_empty_rather_than_absent_when_ungrounded() -> None:
    """无来源时字段必须在且为空，前端才能稳定地渲染"无资料依据"。"""
    point = next(node for node in _points(_view(_course())) if node["name"] == "动态数组扩容")

    assert point["source_refs"] == []


def test_source_summary_counts_actual_statuses() -> None:
    """汇总必须按实际状态分桶，否则落地率永远是 0。"""
    plain = _view(_course())
    grounded = _view(_grounded_course())

    assert plain["source_summary"] == {"course_generated": len(_points(plain))}
    assert grounded["source_summary"] == {"material_grounded": len(_points(grounded))}


def test_skill_units_and_mistake_points_report_their_own_source_status() -> None:
    """能力单元与易错点同样来自知识点所在小节，状态不能各说各话。"""
    view = _view(_grounded_course())

    assert {item["source_status"] for item in view["skill_units"]} == {"material_grounded"}
    assert {item["source_status"] for item in view["mistake_points"]} == {"material_grounded"}


def test_concept_groups_report_source_status_too() -> None:
    """概念组是知识点的父节点，树上不能出现来源标签断层。"""
    view = _view(_grounded_course())

    groups = [node for node in view["nodes"] if node["node_type"] == "concept_group"]

    assert groups
    assert {node["source_status"] for node in groups} == {"material_grounded"}


def test_compiled_base_keeps_source_refs_for_every_point() -> None:
    """编译层本身必须保留 source_refs，视图只是投影。"""
    course = _grounded_course()

    base = compile_course_knowledge_base(
        course, course_map=compile_course_knowledge_map(course),
    )

    assert all(
        "ev-material-0001" in (point.get("source_refs") or [])
        for point in base["knowledge_points"]
    )
