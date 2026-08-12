"""能力包覆盖率必须可见，静默丢弃必须变成 waiting_review（需求 C1）。

原实现里，能力单元/易错点/掌握标准三类记录只要字段不全就被 `continue` 掉，
既不计数也不留痕。后果有两层：

1. 教师看到的是一个干净的知识点，无法区分"没生成"和"生成了但不合格"——
   这两种情况的处理方式相反（前者要补生成，后者要改内容）。
2. 覆盖率恒等于"已存在记录数"，缺口永远不会出现在任何报告里。

所以判据是：同一门课，字段不全的输入必须 (a) 仍然不进正式集合（不合格的
易错点无法驱动补救），(b) 出现在 `generation_audit.waiting_review_entries`
里并带上缺失字段名，(c) 在覆盖率报告里体现为缺口。
"""

from __future__ import annotations

from copy import deepcopy

from course_knowledge_base import (
    compile_capability_coverage_report,
    compile_course_knowledge_base,
    validate_course_knowledge_base,
)
from course_knowledge_map import compile_course_knowledge_map


def _course() -> dict:
    """一门最小课程：两个知识点，能力包字段完整。"""
    return {
        "course_id": "course-c1",
        "course_name": "数据结构",
        "nodes": [{
            "node_id": "section-1",
            "node_level": 2,
            "node_name": "线性表与动态数组",
            "learning_objective": "能够实现动态数组扩容并分析摊还复杂度",
            "knowledge_structure": [{
                "concept_group": "动态容量管理",
                "description": "识别扩容触发条件并解释摊还成本",
                "knowledge_points": [
                    {
                        "name": "容量耗尽判定",
                        "statement": "当元素数量等于当前容量时，下一次插入必须先扩容。",
                        "knowledge_type": "rule",
                        "capability_points": [{
                            "name": "判断扩容触发时机",
                            "observable_behavior": "给定长度与容量判断是否触发扩容",
                        }],
                        "misconceptions": [{
                            "name": "把容量当长度",
                            "observable_error_pattern": "用 capacity 当元素个数参与判断",
                            "discrimination": "区分已用槽位数与总槽位数",
                            "repair_strategy": "画出槽位图并逐个标注已用与空闲",
                        }],
                        "mastery_criteria": [{
                            "name": "扩容触发判断达标",
                            "observable_performance": "在三个边界案例中独立判断扩容时机",
                            "verification_method": "核对三个边界案例的判断结果",
                        }],
                    },
                    {
                        "name": "动态数组扩容",
                        "statement": "倍增扩容把复制成本分摊到一系列插入。",
                        "knowledge_type": "principle",
                        "capability_points": [{
                            "name": "动态数组扩容实现",
                            "observable_behavior": "独立实现倍增扩容并解释摊还复杂度",
                        }],
                        "misconceptions": [{
                            "name": "把单次复制成本当每次插入成本",
                            "observable_error_pattern": "断言每次插入都是 O(n)",
                            "discrimination": "区分单次最坏成本与摊还成本",
                            "repair_strategy": "列出扩容位置与累计复制次数后重新平均",
                        }],
                        "mastery_criteria": [{
                            "name": "扩容实现与分析达标",
                            "observable_performance": "独立实现倍增扩容并说明两种成本的区别",
                            "verification_method": "运行连续插入测试并提交复杂度推导",
                        }],
                    },
                ],
            }],
            "key_points": ["容量耗尽判定", "动态数组扩容"],
        }],
    }


def _compile(course: dict) -> dict:
    return compile_course_knowledge_base(
        course, course_map=compile_course_knowledge_map(course),
    )


def _incomplete_course() -> dict:
    """第二个知识点的三类能力包各缺一个必填字段。"""
    course = deepcopy(_course())
    points = course["nodes"][0]["knowledge_structure"][0]["knowledge_points"]
    points[1]["capability_points"][0].pop("observable_behavior")
    points[1]["misconceptions"][0].pop("repair_strategy")
    points[1]["mastery_criteria"][0].pop("verification_method")
    return course


# --- 覆盖率报告 -------------------------------------------------------------


def test_complete_course_reports_full_coverage() -> None:
    """字段齐全时三类覆盖率都是 1.0，且没有缺口知识点。"""
    report = _compile(_course())["capability_coverage_report"]

    assert report["total_knowledge_points"] == 2
    assert report["coverage_rate"] == {
        "skill_unit": 1.0, "misconception": 1.0, "mastery_criterion": 1.0,
    }
    assert report["points_missing_any"] == []


def test_report_names_the_points_missing_each_kind() -> None:
    """缺口必须落到具体知识点与具体类别，而不只是一个总数。"""
    report = _compile(_incomplete_course())["capability_coverage_report"]

    gap = next(item for item in report["per_point"] if item["name"] == "动态数组扩容")

    assert gap["has_skill_unit"] is False
    assert gap["has_misconception"] is False
    assert gap["has_mastery_criterion"] is False
    assert sorted(gap["missing_kinds"]) == [
        "mastery_criterion", "misconception", "skill_unit",
    ]
    assert report["points_missing_any"] == [gap["knowledge_id"]]


def test_coverage_rate_actually_drops_when_entries_are_rejected() -> None:
    """判据：同一门课两种输入必须给出不同覆盖率，否则报告没有信息量。"""
    complete = _compile(_course())["capability_coverage_report"]
    incomplete = _compile(_incomplete_course())["capability_coverage_report"]

    assert complete["coverage_rate"]["mastery_criterion"] == 1.0
    assert incomplete["coverage_rate"]["mastery_criterion"] == 0.5
    assert incomplete["covered"]["misconception"] == 1


# --- waiting_review：丢弃不再静默 -------------------------------------------


def test_rejected_entries_are_recorded_with_their_missing_fields() -> None:
    """被门拦下的记录必须留痕，并说清缺哪个字段。"""
    audit = _compile(_incomplete_course())["generation_audit"]

    entries = audit["waiting_review_entries"]
    reasons = {item["entry_type"]: item["missing_fields"] for item in entries}

    assert reasons["skill_unit"] == ["observable_behavior"]
    assert reasons["misconception"] == ["repair_strategy"]
    assert reasons["mastery_criterion"] == ["verification_method"]
    assert all(item["status"] == "waiting_review" for item in entries)


def test_waiting_review_entries_carry_their_owning_knowledge_point() -> None:
    """必须能追到是哪个知识点的哪条记录，否则教师无从下手。"""
    audit = _compile(_incomplete_course())["generation_audit"]

    entry = next(
        item for item in audit["waiting_review_entries"]
        if item["entry_type"] == "misconception"
    )

    assert entry["knowledge_name"] == "动态数组扩容"
    assert entry["section_ref"] == "section-1"
    assert entry["name"] == "把单次复制成本当每次插入成本"
    # 原文必须保留，教师才能判断是补字段还是整条重写。
    assert entry["payload"]["observable_error_pattern"] == "断言每次插入都是 O(n)"


def test_rejected_entries_still_stay_out_of_the_official_collections() -> None:
    """可见不等于放行：不合格的记录不得进入正式集合。"""
    base = _compile(_incomplete_course())

    assert [item["name"] for item in base["mastery_criteria"]] == ["扩容触发判断达标"]
    assert len(base["misconceptions"]) == 1
    assert len(base["skill_units"]) == 1


def test_complete_course_records_no_waiting_review_entries() -> None:
    """没有丢弃时列表必须为空而不是缺字段，前端才能稳定渲染。"""
    audit = _compile(_course())["generation_audit"]

    assert audit["waiting_review_entries"] == []


def test_report_links_waiting_review_back_to_the_point() -> None:
    """报告里要区分"没生成"和"生成了但不合格"。"""
    report = _compile(_incomplete_course())["capability_coverage_report"]

    gap = next(item for item in report["per_point"] if item["name"] == "动态数组扩容")

    assert gap["waiting_review_kinds"] == [
        "mastery_criterion", "misconception", "skill_unit",
    ]
    assert report["waiting_review_count"] == 3


def test_validation_surfaces_waiting_review_as_a_visible_issue() -> None:
    """审计字段不够：教师看的是校验结果，丢弃必须出现在那里。"""
    base = _compile(_incomplete_course())

    codes = {item["code"] for item in validate_course_knowledge_base(base)["issues"]}

    assert "knowledge_entries_waiting_review" in codes


# --- 内容阶段前的覆盖率门 ---------------------------------------------------


def test_missing_mastery_criteria_blocks_the_content_stage() -> None:
    """没有掌握标准就无法判定学会没学会，不能进内容阶段。"""
    report = _compile(_incomplete_course())["capability_coverage_report"]

    assert report["ready_for_content"] is False
    assert "missing_mastery_criterion" in report["blocking_reasons"]


def test_fully_covered_course_passes_the_gate() -> None:
    """齐全的课程必须放行，否则这道门会挡住所有课程。"""
    report = _compile(_course())["capability_coverage_report"]

    assert report["ready_for_content"] is True
    assert report["blocking_reasons"] == []


def test_waiting_review_alone_does_not_block_the_content_stage() -> None:
    """待复核是软信号：有待复核但覆盖齐全时不该拦住生成。"""
    course = deepcopy(_course())
    point = course["nodes"][0]["knowledge_structure"][0]["knowledge_points"][1]
    # 追加一条不合格的易错点：该点自身仍有一条合格的，覆盖率不缺。
    point["misconceptions"].append({"name": "缺字段的易错点"})

    report = _compile(course)["capability_coverage_report"]

    assert report["waiting_review_count"] == 1
    assert report["ready_for_content"] is True
    assert report["blocking_reasons"] == []


def test_report_is_computable_from_a_persisted_payload() -> None:
    """报告是纯投影：存量知识库不必重编译也能算出覆盖率。"""
    base = _compile(_incomplete_course())

    recomputed = compile_capability_coverage_report(base)

    assert recomputed == base["capability_coverage_report"]
