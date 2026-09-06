"""概念组必须真的分组，而不是每个知识点一个组（需求 B1）。

清单说"校验没门槛"，实测只对了一半：`group_too_small`（每组少于 2 个知识点）
本来就存在并且会逐组触发。真实课程上"31 个概念组各 1 个知识点"因此不是"没有
信号"，而是**31 条分散的 major**——教师看到一屏同样的告警，看不出这是全课
分组失效，只会当成 31 个各自要修的小问题。

所以这里补的是另外两件事：
1. 一个课程级指标 `grouping_ratio`，让"组数≈知识点数"变成一个能一眼判断的数；
2. 上界告警，因为 prompt 现在写了"每组通常 2-4 个"，只有下界会把模型推向另一
   个极端——把所有知识点塞进一个巨组同样通不过教学意义。

两条都是软门槛：分组质量是教学判断，机械刷数（拆得越多越好）本身就是清单
明确禁止的指标，所以不阻断发布。
"""

from __future__ import annotations

from copy import deepcopy

from course_knowledge_base import (
    compile_course_knowledge_base,
    validate_course_knowledge_base,
)


def _points() -> list[dict]:
    """两个真实成立的原子知识点：一条判定规则和它依赖的原理。"""
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
        },
    ]


def _course() -> dict:
    return {
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
                "knowledge_points": _points(),
            }],
            "key_points": ["容量耗尽判定", "动态数组扩容"],
        }],
    }


def _with_groups(groups: list[list[dict]]) -> dict:
    """同一批知识点，按给定切分放进若干概念组。"""
    course = deepcopy(_course())
    section = course["nodes"][0]
    section["knowledge_structure"] = [
        {
            "concept_group": f"概念组{index + 1}",
            "description": "本组作用与边界",
            "knowledge_points": points,
        }
        for index, points in enumerate(groups)
    ]
    return course


def _report(course: dict) -> dict:
    return validate_course_knowledge_base(compile_course_knowledge_base(course))


def _codes(report: dict) -> list[str]:
    return [item["code"] for item in report["issues"]]


def test_one_group_per_point_is_reported_as_a_course_level_ratio() -> None:
    """每个知识点各占一组时，比值必须等于 1 —— 一个数就能看出分组没生效。"""
    points = _points()

    report = _report(_with_groups([[point] for point in points]))

    assert report["metrics"]["grouping_ratio"] == 1.0


def test_real_grouping_lowers_the_ratio() -> None:
    """知识点合进同一组后比值必须下降，否则这个指标没有信息量。"""
    points = _points()

    grouped = _report(_with_groups([points]))
    scattered = _report(_with_groups([[point] for point in points]))

    assert grouped["metrics"]["grouping_ratio"] < scattered["metrics"]["grouping_ratio"]


def test_grouping_ratio_is_absent_of_points_rather_than_crashing() -> None:
    """没有知识点时指标必须存在且为 0，不能让校验抛错。"""
    course = deepcopy(_course())
    course["nodes"][0]["knowledge_structure"] = []

    report = _report(course)

    assert report["metrics"]["grouping_ratio"] == 0.0


def test_single_point_groups_are_counted_not_just_flagged_one_by_one() -> None:
    """单点组要有个总数，教师才知道是全课失效还是个别疏漏。"""
    points = _points()

    report = _report(_with_groups([[point] for point in points]))

    assert report["metrics"]["single_point_group_count"] == len(points)


def test_a_single_oversized_group_is_flagged_too() -> None:
    """只有下界会把模型推向另一个极端：全部塞进一个巨组。"""
    points = _points()
    padded = []
    for index in range(6):
        clone = deepcopy(points[0])
        clone["name"] = f"{clone['name']}变体{index}"
        clone["statement"] = f"{clone['statement']}（变体{index}）"
        padded.append(clone)

    report = _report(_with_groups([[*points, *padded]]))

    assert "group_too_large" in _codes(report)


def test_a_well_sized_group_triggers_neither_bound() -> None:
    """2-4 个知识点的组是目标形态，两个方向都不该告警。"""
    points = _points()

    codes = _codes(_report(_with_groups([points])))

    assert "group_too_small" not in codes
    assert "group_too_large" not in codes


def test_the_batch_prompt_asks_for_grouped_points() -> None:
    """校验只能事后告警；真正决定分组的是 prompt 有没有要求聚合。

    知识库是教案的确定性投影，`concept_group` 完全由模型这一次输出决定，所以
    这条断言和上面的软门槛是同一件事的两端：不写进 prompt，门槛就只会一直响。
    """
    from course_generation.prompts import CoursePromptComposer

    prompt = CoursePromptComposer().build_teaching_plan_batch_v3_prompt(
        course_title="数据结构",
        positioning="能实现并分析基础数据结构",
        batch_spec={"batch_id": "batch-1", "section_ids": ["L2-1-1"]},
        batch_sections=[{
            "node_id": "L2-1-1",
            "title": "线性表与动态数组",
            "learning_objective": "能够实现动态数组扩容",
            "allowed_module_ids": ["core_explanation"],
        }],
        knowledge_registry=[{
            "knowledge_key": "K001",
            "name": "动态数组扩容",
            "statement": "倍增扩容摊还为常数阶。",
            "owner_node_id": "L2-1-1",
        }],
        section_identities=[{
            "node_id": "L2-1-1",
            "owned_knowledge_keys": ["K001"],
            "reused_knowledge_keys": [],
        }],
        module_catalog=[{"module_id": "core_explanation", "label": "核心教学"}],
        skeleton_revision_id="skeleton-1",
    )

    assert "2-4" in prompt
    # 光有数字不够：必须说清是"多个知识点共用同一组名"，否则模型会理解成
    # 要造 2-4 个组。
    assert "共用同一组名" in prompt


def test_grouping_gates_do_not_block_release() -> None:
    """分组质量是教学判断，机械刷数是清单禁止的指标，所以不阻断。"""
    points = _points()

    report = _report(_with_groups([[point] for point in points]))

    assert report["critical_count"] == 0
    assert report["blocking_issues"] == []
