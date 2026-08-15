"""六类结构性关系错误必须逐类被拦截，且重做范围不得放大（需求 A4）。

合同写的是"未知 ID / 自环 / 重复 / 非法类型 / 遗漏决定 / 环路 → 只重做当前关系
邻域"。清单说"是否完整实现本轮未逐条确认"，所以这里逐类注入一次，判据分两层：

1. **拦截**：每类错误必须产出对应 issue code，且不能被降级成"通过"。
   只断言 `passed is False` 是不够的——任何一条 critical 都能让它变 False，
   注入自环却因为别的原因失败，看起来一样绿。所以逐条断言 code。
2. **重做范围**：纠正轮只能重做失败的那一个批次。这一层容易被忽略：拦截住了
   但整门课重做，等于把一条坏关系的代价放大到全课。

关于"关系邻域"这个粒度：代码里不存在，实际最小重做单位是批次（见
`course_service.py:2236-2262`，`validate_teaching_plan_batch_v3` 只对失败的
`batch_id` 发一次纠正）。批次是生成协议里能寻址的最小单元——模型输出的是整节
教案，没有"只重发一条关系"的通道。因此这里锁的是"不超过一个批次"，
而不是假装邻域粒度存在。差异已记在 NOTES A4。
"""

from __future__ import annotations

from copy import deepcopy

import pytest

from course_knowledge_base import (
    compile_course_knowledge_base,
    validate_course_knowledge_base,
)
from course_prompt_composer import CoursePromptComposer


def _course() -> dict:
    """两个知识点、一条合法前置关系的最小课程。"""
    return {
        "course_id": "course-1",
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
                        "statement": "元素数量等于容量时，下一次插入必须先扩容。",
                        "knowledge_type": "rule",
                        "capability_points": [{
                            "name": "判断扩容触发时机",
                            "observable_behavior": "给定长度与容量判断是否触发扩容",
                        }],
                        "mastery_criteria": [{
                            "name": "扩容触发判断达标",
                            "observable_performance": "在多组长度与容量中独立判断并说明依据",
                            "verification_method": "用至少三个边界案例核对结果",
                        }],
                    },
                    {
                        "name": "动态数组扩容",
                        "statement": "倍增扩容把复制成本摊到一系列插入上。",
                        "knowledge_type": "principle",
                        "prerequisite_names": ["容量耗尽判定"],
                        "capability_points": [{
                            "name": "动态数组扩容实现",
                            "observable_behavior": "独立实现倍增扩容并解释摊还复杂度",
                        }],
                        "mastery_criteria": [{
                            "name": "扩容实现与分析达标",
                            "observable_performance": "独立实现并说明最坏与摊还成本的区别",
                            "verification_method": "运行连续插入测试并提交推导",
                        }],
                    },
                ],
            }],
            "key_points": ["容量耗尽判定", "动态数组扩容"],
            "node_content": "## 容量耗尽判定\n\n判定。\n\n## 动态数组扩容\n\n扩容。",
            "generation_status": "completed",
        }],
    }


def _compiled() -> tuple[dict, dict]:
    course = _course()
    return compile_course_knowledge_base(course), course


def _codes(base: dict, course: dict) -> set[str]:
    report = validate_course_knowledge_base(base, course_data=course)
    assert report["passed"] is False, "注入结构错误后不得判为通过"
    return {str(item.get("code") or "") for item in report["issues"]}


def test_the_baseline_course_passes_so_failures_are_attributable() -> None:
    """基线必须先通过，否则后面每条注入用例都可能是在测别的毛病。"""
    base, course = _compiled()

    report = validate_course_knowledge_base(base, course_data=course)

    assert report["passed"] is True, report["issues"]
    assert base["relations"], "基线必须真的带一条关系"


# --- 六类结构错误逐类注入 ---------------------------------------------------


def test_unknown_endpoint_is_intercepted() -> None:
    """端点指向不存在的知识 ID。"""
    base, course = _compiled()
    base["relations"][0]["target_knowledge_id"] = "ckp_does_not_exist"

    assert "invalid_relation_endpoint" in _codes(base, course)


def test_self_loop_is_intercepted() -> None:
    """自环：source 与 target 相同。"""
    base, course = _compiled()
    base["relations"][0]["target_knowledge_id"] = base["relations"][0]["source_knowledge_id"]

    assert "invalid_relation_endpoint" in _codes(base, course)


def test_unknown_endpoint_and_self_loop_share_one_code() -> None:
    """如实锁住现状：两类错误共用一个 code。

    合同把它们列为两类。代码在 `:837` 用同一分支处理，产出同一个 code。
    这不影响拦截（两者都被拦住），但影响可诊断性：教师或日志看到
    `invalid_relation_endpoint` 无法区分"引用了不存在的知识点"和"自己指向
    自己"。锁在这里，是为了让将来拆分 code 时这条用例主动提醒改测试，
    而不是让差异悄悄留在文档与代码之间。
    """
    base, course = _compiled()
    unknown = deepcopy(base)
    unknown["relations"][0]["target_knowledge_id"] = "ckp_does_not_exist"
    loop = deepcopy(base)
    loop["relations"][0]["target_knowledge_id"] = loop["relations"][0]["source_knowledge_id"]

    assert "invalid_relation_endpoint" in _codes(unknown, course)
    assert "invalid_relation_endpoint" in _codes(loop, course)


def test_illegal_relation_type_is_intercepted() -> None:
    """非法类型：六类白名单之外。"""
    base, course = _compiled()
    base["relations"][0]["relation_type"] = "related"

    assert "invalid_relation_type" in _codes(base, course)


def test_duplicate_relation_is_intercepted() -> None:
    """重复：同一 (source, target, type) 出现两次。"""
    base, course = _compiled()
    base["relations"].append(deepcopy(base["relations"][0]))

    assert "duplicate_relation" in _codes(base, course)


def test_missing_relation_decision_is_intercepted() -> None:
    """遗漏决定：声明了关系规划但没给全每个知识点的决定。"""
    base, course = _compiled()
    base["relation_plan_schema_version"] = "course_relation_plan_v1"
    base["relation_decisions"] = []

    codes = _codes(base, course)

    assert "incomplete_relation_decisions" in codes


def test_invalid_relation_decision_is_intercepted() -> None:
    """决定本身非法：未知 ID、重复项或缺理由。"""
    base, course = _compiled()
    base["relation_plan_schema_version"] = "course_relation_plan_v1"
    base["relation_decisions"] = [
        {"knowledge_id": "ckp_does_not_exist", "decision": "connected", "reason": "无"},
    ]

    assert "invalid_relation_decision" in _codes(base, course)


def test_relation_cycle_is_intercepted() -> None:
    """环路：prerequisite 成环意味着学习顺序无法排。"""
    base, course = _compiled()
    first, second = (item["knowledge_id"] for item in base["knowledge_points"][:2])
    base["relations"].append({
        **deepcopy(base["relations"][0]),
        "relation_id": "ckr_reverse",
        "source_knowledge_id": second,
        "target_knowledge_id": first,
        "relation_type": "prerequisite",
        "reason": "反向前置，构造环路",
    })

    report = validate_course_knowledge_base(base, course_data=course)
    codes = {str(item.get("code") or "") for item in report["issues"]}

    assert "prerequisite_cycle" in codes


def test_cycle_blocks_publication() -> None:
    """前置成环必须阻断发布（D4，2026-08-12 升级）。

    此前是 `major`，也就是带环课程仍可 `passed is True` 发布。升 critical 的
    依据是实测：`scripts/measure_relation_cycles.py` 扫遍 `~/lingzhi` 全部真实
    课程（11 门、其中 6 门有编译知识库），**成环 0 门**——升级不会卡住任何
    现存课程，风险已被证据消掉。

    语义上也应当阻断：前置成环意味着"学 A 要先学 B、学 B 要先学 A"，学习顺序
    根本排不出来，这是结构错误而非质量瑕疵。
    """
    base, course = _compiled()
    first, second = (item["knowledge_id"] for item in base["knowledge_points"][:2])
    base["relations"].append({
        **deepcopy(base["relations"][0]),
        "relation_id": "ckr_reverse",
        "source_knowledge_id": second,
        "target_knowledge_id": first,
        "relation_type": "prerequisite",
        "reason": "反向前置，构造环路",
    })

    report = validate_course_knowledge_base(base, course_data=course)
    cycle = next(item for item in report["issues"] if item["code"] == "prerequisite_cycle")

    assert cycle["severity"] == "critical"
    assert report["passed"] is False
    assert cycle in report["blocking_issues"]


def test_acyclic_course_still_passes() -> None:
    """反向断言：无环课程不受影响，否则升级就变成了误伤。"""
    base, course = _compiled()

    report = validate_course_knowledge_base(base, course_data=course)

    assert report["passed"] is True
    assert not [i for i in report["issues"] if i["code"].endswith("_cycle")]


@pytest.mark.parametrize("mutate,expected", [
    (lambda base: base["relations"][0].update(target_knowledge_id="ckp_missing"),
     "invalid_relation_endpoint"),
    (lambda base: base["relations"][0].update(relation_type="related"),
     "invalid_relation_type"),
    (lambda base: base["relations"].append(deepcopy(base["relations"][0])),
     "duplicate_relation"),
])
def test_each_structural_error_is_critical_enough_to_block(mutate, expected) -> None:
    """拦截不能只是"记一笔"：这几类必须是 critical，否则会带病发布。"""
    base, course = _compiled()
    mutate(base)

    report = validate_course_knowledge_base(base, course_data=course)
    issue = next(item for item in report["issues"] if item["code"] == expected)

    assert issue["severity"] == "critical"
    assert report["passed"] is False


# --- 重做范围不得放大 -------------------------------------------------------


def test_correction_round_redoes_only_the_failing_batch() -> None:
    """纠正 prompt 必须把范围限定在当前批次，且明说其他批次不变。

    这是 A4 的第二层判据。拦截住却整门课重做，等于把一条坏关系的代价放大
    到全课；反过来，如果纠正 prompt 允许改骨架或知识键，修一条关系就可能顺手
    改掉已冻结的身份，后续批次全部失配。
    """
    correction = CoursePromptComposer().build_teaching_plan_batch_v3_correction_prompt(
        original_prompt="## 详细教案批次 V3\n（原批次 prompt）",
        issues=[{"message": "知识关系存在无效端点或自环"}],
    )

    assert "只重新输出当前批次" in correction
    assert "其他\n已完成批次保持不变" in correction or "已完成批次保持不变" in correction
    assert "骨架修订、知识键、目录和批次范围不得改变" in correction


def test_correction_round_carries_the_actual_structural_issues() -> None:
    """错误必须逐条进纠正 prompt，否则模型不知道要修什么。"""
    correction = CoursePromptComposer().build_teaching_plan_batch_v3_correction_prompt(
        original_prompt="（原批次 prompt）",
        issues=[
            {"message": "知识关系存在无效端点或自环"},
            {"message": "不允许关系类型 related"},
            {"message": "知识关系语义签名重复"},
        ],
    )

    assert "无效端点或自环" in correction
    assert "不允许关系类型 related" in correction
    assert "语义签名重复" in correction
