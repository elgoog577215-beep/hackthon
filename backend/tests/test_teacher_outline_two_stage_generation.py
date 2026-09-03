from __future__ import annotations

import asyncio
import json
import re
from copy import deepcopy

import pytest

from ai_base import AIProviderRequestError
from course_generation.outline import CourseOutlinePlanningBudget
from course_generation.outline import merge_teacher_outline_course_contract
from course_generation.outline import merge_teacher_outline_detail
from course_generation.outline import normalize_outline_skeleton
from course_generation.outline import normalize_teacher_outline_course_contract
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
                    "content_summary": f"第 {number} 讲主要介绍主题 {number}。",
                }
                for number in range(1, lecture_count + 1)
            ],
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


def _teacher_course_contract_payload(system_prompt: str) -> str:
    revision_match = re.search(
        r"## 轻量方案修订\n([^\n]+)",
        system_prompt,
    )
    lectures_match = re.search(
        r"## 教师当前讲次方案\n(\[.*?\])\n\n## 教师课程信息",
        system_prompt,
        re.S,
    )
    assert revision_match and lectures_match, system_prompt
    lecture_numbers = [
        int(item["lecture_number"])
        for item in json.loads(lectures_match.group(1))
    ]
    return json.dumps(
        {
            "schema_version": "teacher_outline_course_contract_v1",
            "skeleton_revision_id": revision_match.group(1).strip(),
            "course_intro_zh": "介绍人工智能的基本问题、方法与应用边界。",
            "course_intro_en": "An introduction to AI problems, methods, and boundaries.",
            "positioning": "面向本科生建立人工智能方法与应用判断能力。",
            "learning_objectives": ["能够解释并选择人工智能基本方法"],
            "prerequisites": ["具备基础编程能力"],
            "education_objectives": ["形成负责任使用人工智能的意识"],
            "measurable_outcomes": ["能够完成一个小型人工智能问题分析"],
            "outcome_alignment": [{
                "outcome_number": 1,
                "objective_refs": ["能够解释并选择人工智能基本方法"],
                "lecture_numbers": lecture_numbers,
                "assessment_evidence": ["课程项目分析报告"],
                "coverage_scope": "全课程方法选择与应用判断",
            }],
            "teaching_methods": ["讲授与案例研讨"],
            "assessment_methods": ["过程任务与课程项目"],
            "assessment_plan": [
                {
                    "item": "过程任务",
                    "category": "formative",
                    "weight_percent": 40,
                    "criteria": "按方法理解与证据质量评分",
                    "outcome_numbers": [1],
                },
                {
                    "item": "课程项目",
                    "category": "summative",
                    "weight_percent": 60,
                    "criteria": "按问题分析与方案论证评分",
                    "outcome_numbers": [1],
                },
            ],
            "course_modules": [{
                "module_id": "M1",
                "title": "人工智能方法与应用",
                "lecture_numbers": lecture_numbers,
            }],
            "ideology_cases": [],
            "reference_books": ["《人工智能：一种现代的方法》"],
            "reference_websites": ["https://example.edu/ai"],
            "course_website": "https://example.edu/ai-course",
        },
        ensure_ascii=False,
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
                    # The frozen title is deliberately hostile: the detail
                    # normalizer must ignore it rather than rename the lecture.
                    "title": f"被详情篡改的主题 {number}",
                    "learning_objective": f"能够完成主题 {number} 的可观察任务",
                    "scope_boundary": f"只覆盖主题 {number} 的本讲内容",
                    "hour_breakdown": {
                        "classroom_lecture": 1,
                        "classroom_practice": 0,
                        "online_instruction": 0,
                    },
                    "key_points": [f"重点 {number}"],
                    "key_difficulties": [f"难点 {number}"],
                    "activities": [f"活动 {number}"],
                    "homework": [f"任务 {number}"],
                    "application_anchors": [f"案例 {number}"],
                    "extension_resources": [
                        {
                            "resource_type": "book",
                            "title": "人工智能基础阅读",
                            "edition": "",
                            "locator": "",
                            "source_ref": "《人工智能：一种现代的方法》",
                            "verification_status": "verified",
                        }
                    ],
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


def test_teacher_light_plan_prompt_only_requests_titles_and_summaries():
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

    assert prompt.startswith("## 轻量讲次方案 V1")
    assert "这是课程大纲生成的第一轮" in prompt
    assert "按课程推进顺序返回每讲的标题和内容简介" in prompt
    assert "不生成完整大纲" not in prompt
    assert "不输出课程目标" not in prompt
    assert '"content_summary"' in prompt
    assert '"learning_objectives"' not in prompt
    assert '"course_modules"' not in prompt
    assert '"hour_breakdown"' not in prompt
    assert '"key_points"' not in prompt
    assert '"assessment"' not in prompt
    assert '"course_intro_zh"' not in prompt
    assert prompt.index('"title"') < prompt.index('"content_summary"')


def test_teacher_light_plan_normalization_keeps_summary_without_fake_objectives():
    payload = json.loads(_teacher_framework_payload(2))
    payload.update({
        "positioning": "模型越界返回的课程定位",
        "learning_objectives": ["模型越界返回的课程目标"],
        "assessment_plan": [{"item": "模型越界返回的考核"}],
        "course_modules": [{"module_id": "M1", "lecture_numbers": [1, 2]}],
        "reference_books": ["模型越界返回的参考书"],
    })
    payload["lectures"][0].update({
        "learning_objective": "模型越界返回的本讲目标",
        "hour_breakdown": {"classroom_lecture": 2},
        "key_points": ["模型越界返回的重点"],
        "external_mentor": {"name": "模型越界返回的导师"},
    })
    skeleton = normalize_outline_skeleton(
        payload,
        topic="人工智能导论",
        request_fingerprint="outline-request-light",
        teacher_light_plan_only=True,
    )

    assert skeleton["learning_objectives"] == []
    assert skeleton["course_modules"] == []
    assert skeleton["assessment_plan"] == []
    assert skeleton["reference_books"] == []
    assert skeleton["total_hours"] == 0
    assert skeleton["chapters"][0]["content_summary"] == "第 1 讲主要介绍主题 1。"
    assert skeleton["chapters"][0]["learning_focus"] == ""
    assert skeleton["chapters"][0]["learning_objective"] == ""
    assert skeleton["chapters"][0]["key_points"] == []
    assert skeleton["chapters"][0]["external_mentor"] == {}


def test_course_contract_prompt_uses_the_teacher_edited_light_plan():
    skeleton = normalize_outline_skeleton(
        json.loads(_teacher_framework_payload(2)),
        topic="人工智能导论",
        request_fingerprint="outline-request-contract",
        teacher_light_plan_only=True,
    )
    skeleton["chapters"][0]["title"] = "教师改后的第一讲"
    skeleton["chapters"][0]["content_summary"] = "教师改后的内容简介。"
    skeleton["revision_id"] = "outline_skeleton_teacher_edited"

    prompt = CoursePromptComposer().build_teacher_outline_course_contract_v1_prompt(
        skeleton=skeleton,
        brief={"teacher_course_brief": _teacher_brief()},
        material_context="",
    )

    assert prompt.startswith("## 课程级完整大纲合同 V1")
    assert "这是完整大纲生成的第二轮" in prompt
    assert '"title": "教师改后的第一讲"' in prompt
    assert '"content_summary": "教师改后的内容简介。"' in prompt
    assert '"learning_objectives"' in prompt
    assert '"course_modules"' in prompt
    assert "不输出 lectures" not in prompt


def test_teacher_detail_prompt_freezes_light_plan_and_generates_formal_fields():
    skeleton = normalize_outline_skeleton(
        json.loads(_teacher_framework_payload(2)),
        topic="人工智能导论",
        request_fingerprint="outline-request-detail",
        teacher_light_plan_only=True,
    )
    spec = {
        "batch_id": "OUT-TD-001",
        "skeleton_revision_id": skeleton["revision_id"],
        "lecture_numbers": [1],
    }

    course_contract_prompt = (
        CoursePromptComposer().build_teacher_outline_course_contract_v1_prompt(
            skeleton=skeleton,
            brief={"teacher_course_brief": _teacher_brief()},
            material_context="",
        )
    )
    contract = normalize_teacher_outline_course_contract(
        json.loads(_teacher_course_contract_payload(course_contract_prompt)),
        skeleton=skeleton,
    )
    assembly_skeleton = merge_teacher_outline_course_contract(skeleton, contract)
    prompt = CoursePromptComposer().build_teacher_outline_detail_batch_v1_prompt(
        skeleton=assembly_skeleton,
        batch_spec=spec,
        brief={"teacher_course_brief": _teacher_brief()},
        material_context="",
    )

    assert "这是完整大纲第二轮的逐讲生成任务" in prompt
    assert '"content_summary": "第 1 讲主要介绍主题 1。"' in prompt
    assert "面向本科生建立人工智能方法与应用判断能力" in prompt
    assert '"learning_objective"' in prompt
    assert '"scope_boundary"' in prompt
    assert '"hour_breakdown"' in prompt
    schema = prompt.split("## JSON Schema", 1)[1]
    assert '"content_summary"' not in schema


def test_teacher_authored_detail_is_not_overwritten_by_generated_detail():
    merged = merge_teacher_outline_detail(
        {
            "lecture_number": 1,
            "content_summary": "教师已写的内容摘要",
            "key_points": ["教师已写重点"],
            "activities": [],
        },
        {
            "content_summary": "模型摘要",
            "key_points": ["模型重点"],
            "activities": ["模型补全活动"],
        },
    )

    assert merged["content_summary"] == "教师已写的内容摘要"
    assert merged["key_points"] == ["教师已写重点"]
    assert merged["activities"] == ["模型补全活动"]


def test_teacher_framework_normalization_is_idempotent_for_restart_recovery():
    first = normalize_outline_skeleton(
        json.loads(_teacher_framework_payload()),
        topic="人工智能导论",
        request_fingerprint="outline-request-1",
        teacher_light_plan_only=True,
    )
    restored = normalize_outline_skeleton(
        deepcopy(first),
        topic="人工智能导论",
        request_fingerprint="outline-request-1",
        teacher_light_plan_only=True,
    )

    assert restored == first


@pytest.mark.asyncio
async def test_sixteen_lecture_outline_runs_one_task_per_lecture_and_assembles_in_order(
    monkeypatch,
):
    service = CourseService(planning_concurrency=4)
    service._outline_budget = CourseOutlinePlanningBudget(
        teacher_detail_batch_size=4,
        teacher_detail_concurrency=2,
    )
    calls: list[str] = []
    growth_states: list[str] = []
    detail_events: list[dict[str, object]] = []
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
        if phase_detail.get("lesson_id"):
            detail_events.append(deepcopy(phase_detail))

    async def fake_call(_prompt, system_prompt="", **_kwargs):
        nonlocal active_details, peak_details
        calls.append(system_prompt)
        if system_prompt.startswith("## 轻量讲次方案 V1"):
            return _teacher_framework_payload()
        if system_prompt.startswith("## 课程级完整大纲合同 V1"):
            return _teacher_course_contract_payload(system_prompt)
        if system_prompt.startswith("## 单讲完整大纲 V2"):
            _batch_id, _revision_id, lecture_numbers = _detail_identity(
                system_prompt
            )
            active_details += 1
            peak_details = max(peak_details, active_details)
            # Later lectures finish first inside each active group. The final
            # outline must still be assembled in the teacher's lecture order.
            await asyncio.sleep(0.002 * (5 - ((lecture_numbers[0] - 1) % 4)))
            active_details -= 1
            payload = _teacher_detail_payload(system_prompt)
            on_content_delta = _kwargs.get("on_content_delta")
            if on_content_delta:
                split_at = payload.index('"activities"')
                await on_content_delta(payload[:split_at])
                await asyncio.sleep(0)
                await on_content_delta(payload[split_at:])
            return payload
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
        item for item in calls if item.startswith("## 单讲完整大纲 V2")
    ]
    assert len(calls) == 18
    assert sum(
        item.startswith("## 课程级完整大纲合同 V1") for item in calls
    ) == 1
    assert len(detail_calls) == 16
    assert sorted(_detail_identity(item)[2][0] for item in detail_calls) == list(
        range(1, 17)
    )
    assert peak_details == 4

    stage = result["generation_stage_artifacts"]["outline"]
    assert stage["strategy"] == "teacher_framework_then_lecture_tasks"
    assert stage["course_contract_status"] == "completed"
    assert stage["detail_batch_count"] == 16
    assert stage["detail_completed_batch_count"] == 16
    assert stage["observed_peak_detail_concurrency"] == 4
    assert set(stage["lesson_statuses"]) == {
        f"L1-{number}" for number in range(1, 17)
    }
    assert all(
        item["status"] == "completed"
        and item["stage"] == "outline_detail_completed"
        and item["progress"] == 100
        and item["stream_preview"]
        for item in stage["lesson_statuses"].values()
    )
    assert {
        key: value["lesson_id"]
        for key, value in stage["detail_batches"].items()
    } == {
        f"OUT-TD-{number:03d}": f"L1-{number}"
        for number in range(1, 17)
    }
    assert growth_states.index("framework_ready") < growth_states.index(
        "detailing"
    )
    visible_stream_events = [
        item for item in detail_events if item.get("stream_preview")
    ]
    assert any(
        "能够完成主题 1 的可观察任务" in str(item["stream_preview"])
        for item in visible_stream_events
    )
    assert all(
        {
            "lesson_id",
            "status",
            "stage",
            "message",
            "progress",
            "stream_preview",
        }.issubset(item)
        for item in visible_stream_events
    )
    assert any(
        len(item.get("lesson_statuses") or {}) > 1
        for item in visible_stream_events
    )

    outline = result["course_outline"]
    assert len(outline["chapters"]) == 16
    assert [item["lecture_number"] for item in outline["chapters"]] == list(
        range(1, 17)
    )
    assert outline["chapters"][0]["title"] == "主题 1"
    assert outline["chapters"][0]["sections"][0]["content_summary"] == (
        "第 1 讲主要介绍主题 1。"
    )
    assert outline["chapters"][0]["sections"][0]["learning_objective"] == (
        "能够完成主题 1 的可观察任务"
    )
    assert outline["chapters"][0]["sections"][0]["planned_hours"] == 1
    assert outline["positioning"] == "面向本科生建立人工智能方法与应用判断能力。"
    assert outline["learning_objectives"] == ["能够解释并选择人工智能基本方法"]
    assert outline["course_modules"][0]["lecture_numbers"] == list(range(1, 17))
    assert sum(
        item["weight_percent"] for item in outline["assessment_plan"]
    ) == 100
    assert outline["reference_books"] == ["《人工智能：一种现代的方法》"]


@pytest.mark.asyncio
async def test_teacher_outline_failure_keeps_successes_and_retries_only_failed_lecture(
    monkeypatch,
):
    first_service = CourseService(planning_concurrency=4)
    first_service._outline_budget = CourseOutlinePlanningBudget(
        teacher_detail_batch_size=4,
        teacher_detail_concurrency=2,
    )

    first_calls: list[str] = []
    checkpoints: list[dict[str, object]] = []

    async def capture_checkpoint(checkpoint):
        checkpoints.append(deepcopy(checkpoint))

    async def first_call(_prompt, system_prompt="", **_kwargs):
        first_calls.append(system_prompt)
        if system_prompt.startswith("## 轻量讲次方案 V1"):
            return _teacher_framework_payload()
        if system_prompt.startswith("## 课程级完整大纲合同 V1"):
            return _teacher_course_contract_payload(system_prompt)
        if system_prompt.startswith("## 单讲完整大纲 V2"):
            batch_id, _revision_id, _numbers = _detail_identity(system_prompt)
            if batch_id == "OUT-TD-005":
                raise AIProviderRequestError("temporary provider failure")
            return _teacher_detail_payload(system_prompt)
        raise AssertionError(system_prompt)

    monkeypatch.setattr(first_service, "_call_llm", first_call)
    with pytest.raises(AIProviderRequestError, match="1 个讲次生成失败"):
        await first_service.build_course_draft(
            course_id="teacher-outline-detail-resume",
            topic="人工智能导论",
            requirements="形成十六讲正式课程大纲",
            teacher_course_brief=_teacher_brief(),
            stop_after_outline=True,
            on_checkpoint=capture_checkpoint,
        )

    assert len([
        item for item in first_calls
        if item.startswith("## 单讲完整大纲 V2")
    ]) == 16
    partial = checkpoints[-1]
    first_stage = partial["generation_stage_artifacts"]["outline"]
    assert first_stage["status"] == "detail_failed"
    assert first_stage["detail_batches"]["OUT-TD-005"]["status"] == (
        "retry_required"
    )
    assert sum(
        item["status"] == "completed"
        for item in first_stage["detail_batches"].values()
    ) == 15

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
        assert system_prompt.startswith("## 单讲完整大纲 V2")
        return _teacher_detail_payload(system_prompt)

    monkeypatch.setattr(resumed_service, "_call_llm", resumed_call)
    resumed = await resumed_service.build_course_draft(
        course_id="teacher-outline-detail-resume",
        topic="人工智能导论",
        requirements="形成十六讲正式课程大纲",
        teacher_course_brief=_teacher_brief(),
        existing_course_data=deepcopy(partial),
        stop_after_outline=True,
    )

    assert len(resumed_calls) == 1
    assert _detail_identity(resumed_calls[0])[0] == "OUT-TD-005"
    resumed_stage = resumed["generation_stage_artifacts"]["outline"]
    assert resumed_stage["detail_batches"]["OUT-TD-005"]["status"] == (
        "completed"
    )
    assert resumed_stage["fallback_units"] == []
    assert resumed_stage["status"] == "completed"
