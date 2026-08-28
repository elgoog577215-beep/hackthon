"""四种课程类型的目录规划规则必须真的不同。

背景：四种生成模式补齐后，差异化完全落在 `_course_type_planning_rules`
的三条分支上——project 走专属路径角色、inquiry/exam 走必经阶段、
systematic 走兜底。其中 project 与 systematic 的 `required_planning_stages`
都是空的，两者只靠这个函数里的分支区分，**此前没有任何测试钉住**，
改动时极容易把两者悄悄合并成同一套规则而不被发现。

这组测试就是钉这一条：改坏了要当场红，而不是等到生成出一门
「把探究任务伪装成项目里程碑」的课才被人看出来。
"""

from course_prompt_composer import _course_planning_rules, _course_type_planning_rules
from course_type_contracts import (
    COURSE_TYPE_CONTRACTS,
    ENABLED_COURSE_TYPES,
    course_purpose_for_type,
)


def _brief(course_type: str) -> dict:
    return {
        "course_type": course_type,
        "course_type_contract": COURSE_TYPE_CONTRACTS[course_type],
    }


def test_four_types_are_all_enabled():
    """四种类型都要开放——任何一种掉出 ENABLED，前端那一格就变回灰色。"""
    assert ENABLED_COURSE_TYPES == {"systematic", "project", "inquiry", "exam"}


def test_project_rules_are_milestone_shaped_not_stage_shaped():
    rules = _course_type_planning_rules(_brief("project"))
    assert "verify_in_project" in rules
    assert "milestone" in rules
    # 项目实战靠里程碑表达进度，不靠必经阶段；这一条写反了会让目录变成流水账
    assert "`planning_stages` 使用空数组" in rules


def test_systematic_rules_forbid_project_only_roles():
    rules = _course_type_planning_rules(_brief("systematic"))
    assert "知识先修关系" in rules
    assert "不得出现项目专属角色" in rules
    # systematic 与 project 的 required_planning_stages 都是空，
    # 若分支被合并，systematic 会拿到 verify_in_project/milestone 规则
    assert "verify_in_project" not in rules
    assert "milestone" not in rules


def test_project_and_systematic_do_not_collapse_into_one_rule_set():
    """两者阶段数都为 0，但规则文本必须不同——这正是最容易被合并掉的一对。"""
    assert _course_type_planning_rules(_brief("project")) != _course_type_planning_rules(
        _brief("systematic")
    )


def test_inquiry_and_exam_pin_their_own_ordered_stages():
    expected = {
        "inquiry": [
            "define_question",
            "decompose_questions",
            "gather_evidence",
            "test_explanations",
            "form_conclusion",
        ],
        "exam": [
            "scope_diagnosis",
            "priority_review",
            "targeted_practice",
            "mock_assessment",
            "final_consolidation",
        ],
    }
    for course_type, stage_ids in expected.items():
        rules = _course_type_planning_rules(_brief(course_type))
        for stage_id in stage_ids:
            assert stage_id in rules, f"{course_type} 缺少必经阶段 {stage_id}"
        # 顺序是硬要求：倒序推进会让探究课先下结论再找证据
        assert "不得倒序" in rules
        assert "每章必须填写 `planning_stages`" in rules


def test_exam_is_the_only_type_with_its_own_purpose():
    """只有冲刺计划的教学目的不是 systematic，说明它在下游也有独立组织方式。"""
    purposes = {
        course_type: course_purpose_for_type(course_type)
        for course_type in sorted(ENABLED_COURSE_TYPES)
    }
    assert purposes["exam"] == "exam_sprint"
    assert {purposes["systematic"], purposes["project"], purposes["inquiry"]} == {"systematic"}


def test_current_product_classifications_override_legacy_course_type_rules():
    rules = _course_planning_rules({
        "learning_purpose": "systematic",
        "course_teaching_type": "seminar",
        "course_type": "inquiry",
        "course_type_contract": COURSE_TYPE_CONTRACTS["inquiry"],
    })

    assert "define_question" not in rules
    assert "整课怎样教由课程教学类型决定" in rules


def test_current_exam_purpose_keeps_the_ordered_revision_tasks():
    rules = _course_planning_rules({
        "learning_purpose": "exam",
        "course_teaching_type": "comprehensive",
        "course_type": "systematic",
    })

    assert "scope_diagnosis" in rules
    assert "final_consolidation" in rules
    assert "不得倒序" in rules
