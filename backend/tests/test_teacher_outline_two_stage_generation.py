from __future__ import annotations

import asyncio
import json
import re
from copy import deepcopy

import pytest

from ai_base import AIProviderRequestError
from course_generation.outline import CourseOutlinePlanningBudget
from course_generation.prompts import CoursePromptComposer
from course_generation.service import CourseService
from course_pedagogy import resolve_pedagogy_profile


def _teacher_framework_payload(lecture_count: int = 16) -> str:
    return json.dumps(
        {
            "course_title": "人工智能导论",
            "lectures": [
                {
                    "lecture_number": number,
                    "title": f"主题 {number}",
                    "learning_objective": f"能够完成第 {number} 讲任务",
                    "scope_boundary": (
                        f"只处理第 {number} 讲范围，不提前展开后续内容"
                    ),
                    "hour_breakdown": {
                        "classroom_lecture": 1,
                        "classroom_practice": 0,
                        "online_instruction": 0,
                    },
                    "learning_path_role": "standard",
                    "path_reason": "课程主路径",
                }
                for number in range(1, lecture_count + 1)
            ],
            "course_intro_zh": "建立人工智能的核心概念与应用判断。",
            "course_intro_en": "Build core AI concepts and application judgement.",
            "positioning": "面向本科生的人工智能核心概览课",
            "learning_objectives": ["能够解释并应用人工智能核心方法"],
            "education_objectives": [],
            "measurable_outcomes": ["能够完成一个可检查的人工智能分析任务"],
            "outcome_alignment": [
                {
                    "outcome_number": 1,
                    "objective_refs": ["学习目标1"],
                    "lecture_numbers": list(range(1, lecture_count + 1)),
                    "assessment_evidence": ["课程分析任务"],
                    "coverage_scope": "课程核心内容",
                }
            ],
            "teaching_methods": ["讲授与练习结合"],
            "assessment_methods": ["过程任务与期末项目"],
            "assessment_plan": [
                {
                    "name": "过程任务",
                    "weight": 40,
                    "criteria": ["结论正确且依据清楚"],
                    "outcome_numbers": [1],
                },
                {
                    "name": "期末项目",
                    "weight": 60,
                    "criteria": ["能够综合应用课程方法"],
                    "outcome_numbers": [1],
                },
            ],
            "course_modules": [],
            "ideology_cases": [],
            "reference_books": [],
            "reference_websites": [],
            "course_website": "",
        },
        ensure_ascii=False,
    )


def _detail_identity(system_prompt: str) -> tuple[str, str, list[int]]:
    batch_match = re.search(r"^- 批次：([^\n]+)$", system_prompt, re.M)
    revision_match = re.search(r"^- 框架修订：([^\n]+)$", system_prompt, re.M)
    lecture_match = re.search(r"^- 讲次：(\[[^\n]+\])$", system_prompt, re.M)
    assert batch_match and revision_match and lecture_match, system_prompt
    return (
        batch_match.group(1).strip(),
        revision_match.group(1).strip(),
        [int(item) for item in json.loads(lecture_match.group(1))],
    )


def _teacher_detail_payload(system_prompt: str) -> str:
    batch_id, revision_id, lecture_numbers = _detail_identity(system_prompt)
    return json.dumps(
        {
            "batch_id": batch_id,
            "skeleton_revision_id": revision_id,
            "lectures": [
                {
                    "lecture_number": number,
                    # Framework fields are deliberately hostile: the detail
                    # normalizer must ignore them rather than rename a lecture.
                    "title": f"被详情篡改的主题 {number}",
                    "scope_boundary": "被详情篡改的边界",
                    "content_summary": f"第 {number} 讲的具体教学内容。",
                    "key_points": [f"重点 {number}"],
                    "key_difficulties": [f"难点 {number}"],
                    "activities": [f"活动 {number}"],
                    "homework": [f"任务 {number}"],
                    "application_anchors": [f"案例 {number}"],
                    "extension_resources": [],
                    "learning_tasks": [
                        {
                            "mode": "offline",
                            "stage": "after_class",
                            "task": f"完成任务 {number}",
                            "evidence": f"提交结果 {number}",
                            "estimated_hours": 1,
                        }
                    ],
                    "education_objective_refs": [],
                    "ideology_implementation": "",
                    "external_mentor": {},
                    "assessment": [f"提交结果 {number} 且判断正确"],
                }
                for number in lecture_numbers
            ],
        },
        ensure_ascii=False,
    )


def _teacher_brief() -> dict[str, object]:
    return {
        "lecture_count": 16,
        "total_class_hours": 16,
        "course_period_minutes": 45,
        "target_audience": "本科生",
        "teaching_context": "线下课堂",
    }


def test_teacher_framework_prompt_excludes_per_lecture_details():
    prompt = CoursePromptComposer().build_outline_skeleton_v2_prompt(
        subject="人工智能导论",
        audience="本科生",
        brief={
            "course_shape_constraints": {
                "teacher_lecture_mode": True,
                "chapter_count": 16,
                "section_count": 16,
            },
            "teacher_course_brief": _teacher_brief(),
        },
        profile=resolve_pedagogy_profile(subject="人工智能导论"),
        difficulty_profile={},
        gap_assessment={},
        adaptation_decision={},
        material_context="",
        detail_level="full",
        coverage_verdict={},
    )

    assert "本请求只形成可立即展示和审阅的全课框架" in prompt
    assert '"content_summary"' not in prompt
    assert '"key_points"' not in prompt
    assert '"assessment"' not in prompt
    assert prompt.index('"lectures"') < prompt.index('"course_intro_zh"')


@pytest.mark.asyncio
async def test_sixteen_lecture_outline_uses_four_bounded_detail_batches(
    monkeypatch,
):
    service = CourseService(planning_concurrency=4)
    service._outline_budget = CourseOutlinePlanningBudget(
        teacher_detail_batch_size=4,
        teacher_detail_concurrency=2,
    )
    calls: list[str] = []
    growth_states: list[str] = []
    active_details = 0
    peak_details = 0

    async def capture_phase(
        _phase,
        _progress,
        _message,
        _phase_progress,
        phase_detail,
    ):
        growth = phase_detail.get("outline_growth") or {}
        if growth.get("state"):
            growth_states.append(str(growth["state"]))

    async def fake_call(_prompt, system_prompt="", **_kwargs):
        nonlocal active_details, peak_details
        calls.append(system_prompt)
        if system_prompt.startswith("## 全课讲次大纲"):
            return _teacher_framework_payload()
        if system_prompt.startswith("## 讲次详情批次 V1"):
            active_details += 1
            peak_details = max(peak_details, active_details)
            await asyncio.sleep(0.01)
            active_details -= 1
            return _teacher_detail_payload(system_prompt)
        raise AssertionError(system_prompt)

    monkeypatch.setattr(service, "_call_llm", fake_call)
    result = await service.build_course_draft(
        course_id="teacher-outline-two-stage",
        topic="人工智能导论",
        requirements="形成十六讲正式课程大纲",
        teacher_course_brief=_teacher_brief(),
        stop_after_outline=True,
        on_phase=capture_phase,
    )

    detail_calls = [
        item for item in calls if item.startswith("## 讲次详情批次 V1")
    ]
    assert len(calls) == 5
    assert len(detail_calls) == 4
    assert [_detail_identity(item)[2] for item in detail_calls] == [
        [1, 2, 3, 4],
        [5, 6, 7, 8],
        [9, 10, 11, 12],
        [13, 14, 15, 16],
    ]
    assert peak_details == 2

    stage = result["generation_stage_artifacts"]["outline"]
    assert stage["strategy"] == "teacher_framework_then_detail_batches"
    assert stage["detail_batch_count"] == 4
    assert stage["detail_completed_batch_count"] == 4
    assert stage["observed_peak_detail_concurrency"] == 2
    assert growth_states.index("framework_ready") < growth_states.index(
        "detailing"
    )

    outline = result["course_outline"]
    assert len(outline["chapters"]) == 16
    assert outline["chapters"][0]["title"] == "主题 1"
    assert outline["chapters"][0]["sections"][0]["content_summary"] == (
        "第 1 讲的具体教学内容。"
    )


@pytest.mark.asyncio
async def test_teacher_outline_resume_retries_only_failed_detail_batch(
    monkeypatch,
):
    first_service = CourseService(planning_concurrency=4)
    first_service._outline_budget = CourseOutlinePlanningBudget(
        teacher_detail_batch_size=4,
        teacher_detail_concurrency=2,
    )

    async def first_call(_prompt, system_prompt="", **_kwargs):
        if system_prompt.startswith("## 全课讲次大纲"):
            return _teacher_framework_payload()
        if system_prompt.startswith("## 讲次详情批次 V1"):
            batch_id, _revision_id, _numbers = _detail_identity(system_prompt)
            if batch_id == "OUT-TD-005-008":
                raise AIProviderRequestError("temporary provider failure")
            return _teacher_detail_payload(system_prompt)
        raise AssertionError(system_prompt)

    monkeypatch.setattr(first_service, "_call_llm", first_call)
    first = await first_service.build_course_draft(
        course_id="teacher-outline-detail-resume",
        topic="人工智能导论",
        requirements="形成十六讲正式课程大纲",
        teacher_course_brief=_teacher_brief(),
        stop_after_outline=True,
    )
    first_stage = first["generation_stage_artifacts"]["outline"]
    assert first_stage["detail_batches"]["OUT-TD-005-008"]["status"] == (
        "retry_required"
    )
    assert first_stage["status"] == "completed_with_warnings"

    resumed_calls: list[str] = []
    resumed_service = CourseService(planning_concurrency=4)
    resumed_service._outline_budget = CourseOutlinePlanningBudget(
        # A deployment setting may change between attempts. The checkpointed
        # batch identity must still win for this in-flight outline.
        teacher_detail_batch_size=2,
        teacher_detail_concurrency=2,
    )

    async def resumed_call(_prompt, system_prompt="", **_kwargs):
        resumed_calls.append(system_prompt)
        assert system_prompt.startswith("## 讲次详情批次 V1")
        return _teacher_detail_payload(system_prompt)

    monkeypatch.setattr(resumed_service, "_call_llm", resumed_call)
    resumed = await resumed_service.build_course_draft(
        course_id="teacher-outline-detail-resume",
        topic="人工智能导论",
        requirements="形成十六讲正式课程大纲",
        teacher_course_brief=_teacher_brief(),
        existing_course_data=deepcopy(first),
        stop_after_outline=True,
    )

    assert len(resumed_calls) == 1
    assert _detail_identity(resumed_calls[0])[0] == "OUT-TD-005-008"
    resumed_stage = resumed["generation_stage_artifacts"]["outline"]
    assert resumed_stage["detail_batches"]["OUT-TD-005-008"]["status"] == (
        "completed"
    )
    assert resumed_stage["fallback_units"] == []
    assert resumed_stage["status"] == "completed"
