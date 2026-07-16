from copy import deepcopy

import pytest

from course_coherence import (
    compile_course_coherence_contract,
    course_coherence_prompt_context,
    evaluate_course_coherence,
    validate_course_coherence_contract,
)
from course_document import document_from_generation_draft
from course_prompt_composer import CoursePromptComposer
from course_quality import build_final_course_quality_report
from course_service import CourseService


def _knowledge(name: str, capability: str) -> list[dict]:
    return [{
        "topic": name,
        "description": f"{name}在当前课程中的作用",
        "knowledge_points": [{
            "name": name,
            "description": f"{name}的对象、条件和边界",
            "capability": capability,
            "capability_points": [{
                "name": capability,
                "observable_behavior": capability,
            }],
            "mistake_points": [{
                "name": f"忽略{name}的条件",
                "description": f"使用{name}时没有检查成立条件",
            }],
            "improvement_points": [{
                "name": f"迁移{name}",
                "learning_goal": f"在新情境中独立使用{name}",
            }],
        }],
    }]


def _node(
    node_id: str,
    name: str,
    knowledge: str,
    capability: str,
    *,
    prerequisites: list[str] | None = None,
    content: str = "",
) -> dict:
    return {
        "node_id": node_id,
        "parent_node_id": "L1-1",
        "node_level": 2,
        "node_name": name,
        "learning_objective": capability,
        "key_points": [knowledge],
        "knowledge_structure": _knowledge(knowledge, capability),
        "prerequisite_node_ids": prerequisites or [],
        "scope_boundary": f"只负责{knowledge}",
        "assessment": [f"完成{knowledge}任务"],
        "misconceptions": [f"忽略{knowledge}的条件"],
        "difficulty_contract": {
            "challenge": {
                "reasoning_depth": 3,
                "transfer_distance": 3,
                "task_complexity": 3,
            },
            "support": {"scaffold_intensity": 3},
            "mastery": {"independence": 3},
            "subject_task": "worked_solution",
        },
        "grounding_contract": {},
        "module_plan": [],
        "generation_status": "completed",
        "node_content": content,
    }


def _course() -> dict:
    first = _node(
        "L2-1-1",
        "1.1 函数表示",
        "函数表示",
        "能够在表格、图像和解析式之间转换",
        content=(
            "## 函数表示\n\n函数可以使用表格、图像和解析式表示，不同表示突出不同信息。"
            "学习者需要根据任务选择表示方式，并说明选择依据和适用边界。\n\n"
            "## 任务\n\n请独立完成三种表示之间的转换，并检查定义域。"
        ),
    )
    second = _node(
        "L2-1-2",
        "1.2 图像性质",
        "函数图像性质",
        "能够从函数图像判断单调性和最值",
        prerequisites=["L2-1-1"],
        content=(
            "## 从表示到图像性质\n\n上一节建立了函数表示，本节利用图像判断单调性和最值。"
            "因为图像记录输入与输出的变化，所以需要结合定义域说明判断边界。\n\n"
            "## 独立任务\n\n请分析一个新图像并写出单调区间与最值。"
        ),
    )
    third = _node(
        "L2-1-3",
        "1.3 实际建模",
        "函数建模",
        "能够把实际关系转化为函数并验证模型",
        prerequisites=["L2-1-2"],
        content=(
            "## 函数建模\n\n利用函数图像性质检查模型是否符合实际约束，再根据变量关系建立函数。"
            "模型必须说明变量、定义域、关系式和结果验证，不能只给出一个公式。\n\n"
            "## 综合任务\n\n请建立一个新模型并解释结果、边界和验证方法。"
        ),
    )
    return {
        "course_id": "coherence-course",
        "course_name": "函数课程",
        "target_audience": "高中生",
        "subject_pedagogy_profile": {
            "primary_mode": "math_formal",
            "secondary_mode": None,
            "secondary_intensity": None,
            "confidence": "high",
            "evidence": [],
            "rationale": "测试",
            "enabled_module_ids": [],
            "user_locked": True,
        },
        "difficulty_profile": {},
        "nodes": [
            {"node_id": "L1-1", "node_level": 1, "node_name": "第一章"},
            first,
            second,
            third,
        ],
        "course_blueprint": {"nodes": []},
    }


def test_contract_assigns_order_handoffs_and_future_boundaries():
    course = _course()
    contract = compile_course_coherence_contract(course)
    rows = contract["section_contracts"]

    assert contract["quality_report"]["passed"] is True
    assert contract["ordered_section_ids"] == ["L2-1-1", "L2-1-2", "L2-1-3"]
    assert rows[1]["explicit_prerequisite_ids"] == ["L2-1-1"]
    assert "函数表示" in rows[1]["required_handoff_terms"]
    assert "函数建模" in rows[1]["reserved_for_later"]


def test_prompt_context_exposes_current_responsibility_without_copying_course():
    course = _course()
    course["course_coherence_contract"] = compile_course_coherence_contract(course)

    context = course_coherence_prompt_context(course, "L2-1-2")
    _, system_prompt = CoursePromptComposer().build_content_prompt(
        course_data=course,
        node=course["nodes"][2],
        context="无资料",
    )

    assert "必须承接：1.1 函数表示" in context
    assert "本节唯一推进：能够从函数图像判断单调性和最值" in context
    assert "留给后续节点展开：函数建模" in context
    assert "本节之后实际进入：1.3 实际建模" in context
    assert "## 全课总编契约" in system_prompt
    assert context in system_prompt


def test_content_prompt_exposes_stable_module_heading_and_role_contract():
    course = _course()
    node = course["nodes"][2]
    node["module_plan"] = [{
        "module_id": "lesson_goal",
        "label": "本节任务",
        "block_role": "objective",
        "required": True,
        "output_contract": "给出可验证学习目标",
        "prompt_instruction": "说明学习者完成后能做什么",
    }]

    _, system_prompt = CoursePromptComposer().build_content_prompt(
        course_data=course,
        node=node,
        context="无资料",
    )

    assert "必需模块 `## 本节任务` [角色=objective]" in system_prompt
    assert "当前节点名称已经由页面显示" in system_prompt
    assert "`###` 及更深标题只用于模块内部" in system_prompt


def test_forward_prerequisite_is_a_blocking_contract_error():
    course = _course()
    course["nodes"][1]["prerequisite_node_ids"] = ["L2-1-2"]
    contract = compile_course_coherence_contract(course)
    report = validate_course_coherence_contract(contract, course_data=course)

    assert report["passed"] is False
    assert any(item["code"] == "coherence:forward_prerequisite" for item in report["issues"])


def test_duplicate_substantive_explanation_blocks_course_publication():
    course = _course()
    duplicate = (
        "函数图像把每一个输入与对应输出放在坐标平面中，因此观察图像时必须同时检查定义域、"
        "变化方向和边界位置。只有把这些条件一起说明，单调区间与最值结论才有明确意义，"
        "也才能在新的函数情境中稳定复用这套判断方法。具体分析时先确定自变量允许取值，"
        "再按照从左到右的方向比较函数值变化，最后结合端点是否能取到来表述区间和最值。"
        "这三步不能被拆成彼此无关的零散结论，否则学生虽然记住了术语，却不能解释结论的来源。"
    )
    course["nodes"][1]["node_content"] += f"\n\n{duplicate}"
    course["nodes"][2]["node_content"] += f"\n\n{duplicate}"

    coherence = evaluate_course_coherence(course)
    final = build_final_course_quality_report(course, job_id="coherence-test")

    assert coherence["passed"] is False
    assert coherence["duplicate_pair_count"] == 1
    assert any(item["code"] == "coherence:duplicate_explanation" for item in coherence["issues"])
    assert final["publication_allowed"] is False
    assert any(item["code"] == "coherence:duplicate_explanation" for item in final["blocking_issues"])


def test_short_prerequisite_recap_is_allowed_and_not_treated_as_duplication():
    course = deepcopy(_course())
    report = evaluate_course_coherence(course)

    assert report["passed"] is True
    assert report["duplicate_pair_count"] == 0
    assert report["missing_bridge_count"] == 0


def test_explicit_previous_section_recap_counts_as_a_valid_bridge():
    course = _course()
    course["nodes"][1]["knowledge_structure"] = _knowledge(
        "抽象映射规范",
        "能够识别抽象映射规范",
    )
    report = evaluate_course_coherence(course)

    assert report["passed"] is True
    assert report["missing_bridge_count"] == 0


def test_current_topic_cannot_be_mislabeled_as_the_next_section():
    course = _course()
    course["nodes"][2]["node_content"] += "\n\n这正好是下一节的函数图像性质。"

    report = evaluate_course_coherence(course)

    assert report["passed"] is False
    assert report["incorrect_handoff_count"] == 1
    assert any(
        item["code"] == "coherence:incorrect_next_section_handoff"
        for item in report["blocking_issues"]
    )


def test_next_section_preview_is_valid_when_it_matches_the_actual_next_goal():
    course = _course()
    course["nodes"][2]["node_content"] += "\n\n下一节将学习如何完成函数建模。"

    report = evaluate_course_coherence(course)

    assert report["passed"] is True
    assert report["incorrect_handoff_count"] == 0


def test_authoritative_course_document_can_be_projected_for_historical_replay():
    course = _course()
    document = document_from_generation_draft(course)
    persisted = {
        key: deepcopy(value)
        for key, value in course.items()
        if key != "nodes"
    }
    persisted["course_document"] = document.model_dump(mode="json")
    persisted["course_document_revision"] = document.document_revision

    contract = compile_course_coherence_contract(persisted)
    report = evaluate_course_coherence(persisted)

    assert contract["ordered_section_ids"] == ["L2-1-1", "L2-1-2", "L2-1-3"]
    assert report["section_count"] == 3
    assert report["passed"] is True


@pytest.mark.asyncio
async def test_coherence_repair_only_accepts_a_candidate_that_removes_blocking_issue(
    monkeypatch,
):
    course = _course()
    duplicate = (
        "函数图像把每一个输入与对应输出放在坐标平面中，因此观察图像时必须同时检查定义域、"
        "变化方向和边界位置。只有把这些条件一起说明，单调区间与最值结论才有明确意义，"
        "也才能在新的函数情境中稳定复用这套判断方法。具体分析时先确定自变量允许取值，"
        "再按照从左到右的方向比较函数值变化，最后结合端点是否能取到来表述区间和最值。"
        "这三步不能被拆成彼此无关的零散结论，否则学生虽然记住了术语，却不能解释结论的来源。"
    )
    original_third = course["nodes"][3]["node_content"]
    course["nodes"][1]["node_content"] += f"\n\n{duplicate}"
    course["nodes"][3]["node_content"] += f"\n\n{duplicate}"
    initial_report = evaluate_course_coherence(course)
    service = CourseService()

    async def fake_call_llm(*_args, **_kwargs):
        return original_third

    monkeypatch.setattr(service, "_call_llm", fake_call_llm)
    repaired, final_report = await service.repair_course_coherence(course, initial_report)

    assert initial_report["blocking_count"] == 1
    assert final_report["blocking_count"] == 0
    assert final_report["passed"] is True
    assert repaired["nodes"][1]["node_content"].endswith(duplicate)
    assert duplicate not in repaired["nodes"][3]["node_content"]
