from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from course_generation_workflow import (
    build_course_blueprint_from_plan,
    build_course_generation_artifacts,
    normalize_course_outline_contract,
)
from course_prompt_composer import CoursePromptComposer
from course_type_contracts import resolve_course_type
from course_type_contracts import CourseTypeNotEnabled
from course_versioning import build_blueprint_draft
from models import CourseGenerationRequest
from fastapi import HTTPException
from routers.courses import create_course_generation_job
from task_manager import TaskManager


def _project_request(**overrides):
    payload = {
        "subject": "大学生环保保温杯设计",
        "course_type": "project",
        "course_intent": {
            "project_goal": "设计一款适合大学生使用的环保保温杯",
            "expected_deliverable": "产品设计方案与可验证原型",
            "prior_experience": "熟悉产品造型与结构",
            "current_uncertainty": "不了解玻璃材料与隔热工艺",
        },
    }
    payload.update(overrides)
    return CourseGenerationRequest.model_validate(payload)


def test_new_course_type_routes_legacy_fields_without_losing_compatibility():
    project = _project_request()
    exam = CourseGenerationRequest(subject="教师资格考试", course_type="exam")

    assert project.course_purpose == "systematic"
    assert project.composition_style.value == "project_driven"
    assert exam.course_purpose == "exam_sprint"
    assert exam.composition_style.value == "example_driven"


def test_legacy_default_purpose_does_not_hide_project_or_inquiry_composition():
    project = CourseGenerationRequest.model_validate({
        "subject": "旧项目课程",
        "course_purpose": "systematic",
        "composition_style": "project_driven",
    })
    inquiry = CourseGenerationRequest.model_validate({
        "subject": "旧探究课程",
        "course_purpose": "systematic",
        "composition_style": "inquiry_driven",
    })

    assert project.course_type == "project"
    assert project.course_intent.project_goal == "旧项目课程"
    assert inquiry.course_type == "inquiry"
    assert resolve_course_type(
        course_purpose="systematic",
        composition_style="project_driven",
    ) == ("project", "composition_style")


def test_non_default_legacy_purpose_still_has_priority():
    request = CourseGenerationRequest.model_validate({
        "subject": "期末复习",
        "course_purpose": "exam_sprint",
        "composition_style": "project_driven",
    })

    assert request.course_type == "exam"
    assert request.course_purpose == "exam_sprint"


@pytest.mark.asyncio
@pytest.mark.parametrize("course_type", ["inquiry", "exam"])
async def test_unreleased_course_types_are_rejected_before_a_job_is_created(course_type):
    request = CourseGenerationRequest(subject="暂未开放课程", course_type=course_type)

    class FakeTaskManager:
        called = False

        async def create_generation_job(self, _snapshot):
            self.called = True

    manager = FakeTaskManager()
    with pytest.raises(HTTPException) as caught:
        await create_course_generation_job(request, manager)
    assert caught.value.status_code == 422
    assert caught.value.detail["code"] == "course_type_not_enabled"
    assert manager.called is False


@pytest.mark.asyncio
async def test_manager_also_rejects_unreleased_type_before_touching_storage():
    manager = object.__new__(TaskManager)
    with pytest.raises(CourseTypeNotEnabled) as caught:
        await manager._create_generation_job({
            "subject": "考试冲刺",
            "course_type": "exam",
        })
    assert caught.value.code == "course_type_not_enabled"


@pytest.mark.asyncio
async def test_task_summary_persists_course_type_without_exposing_request_snapshot(
    tmp_path,
    monkeypatch,
):
    import task_manager as task_manager_module

    monkeypatch.setattr(task_manager_module, "TASKS_FILE", tmp_path / "tasks.json")
    manager = TaskManager(storage=None, course_service=None, ws_service=None)
    manager.save_tasks = lambda *args, **kwargs: None
    task_id = await manager.create_task(
        "course-project",
        course_name="玻璃杯设计",
        request_snapshot={"course_type": "project", "subject": "玻璃杯设计"},
        enqueue=False,
    )

    summary = manager.get_task_summary(task_id)
    assert summary["course_type"] == "project"
    assert "request_snapshot" not in summary


@pytest.mark.parametrize(
    "intent, expected_message",
    [
        (None, "必须提供 course_intent"),
        ({"project_goal": "做一个杯子"}, "必须提供 expected_deliverable"),
        ({"expected_deliverable": "一个原型"}, "必须提供 project_goal"),
    ],
)
def test_project_requires_goal_and_deliverable(intent, expected_message):
    with pytest.raises(ValidationError, match=expected_message):
        CourseGenerationRequest.model_validate({
            "subject": "项目课程",
            "course_type": "project",
            "course_intent": intent,
        })


def test_project_brief_compiles_personal_starting_point_and_contract():
    request = _project_request()
    artifacts = build_course_generation_artifacts(
        course_id="course-project",
        topic=request.subject,
        difficulty="intermediate",
        style=None,
        composition_style=request.composition_style.value,
        requirements="面向真实使用情境验证保温与环保表现",
        learner_profile_summary="设计专业学生",
        course_type=request.course_type,
        course_intent=request.course_intent,
        learner_starting_profile=request.learner_starting_profile,
        course_purpose=request.course_purpose,
    )
    brief = artifacts["course_generation_brief"]
    starting = brief["learner_starting_profile"]

    assert brief["course_type"] == "project"
    assert brief["course_type_label"] == "项目实战"
    assert brief["course_intent"]["schema_version"] == "course_intent_v1"
    assert brief["course_intent"]["expected_deliverable"] == "产品设计方案与可验证原型"
    assert "熟悉产品造型与结构" in starting["self_reported_strengths"]
    assert "不了解玻璃材料与隔热工艺" in starting["focus_areas"]
    assert starting["status"] == "tentative"
    assert starting["evidence_basis"] == "self_reported"
    assert any("项目里程碑" in item for item in brief["course_type_contract"]["planning_sequence"])
    assert "产品设计方案与可验证原型" in brief["expected_deliverables"]
    assert any("项目里程碑" in item for item in brief["hard_constraints"])


def test_project_with_no_starting_evidence_is_explicitly_insufficient():
    artifacts = build_course_generation_artifacts(
        course_id="course-project-empty-profile",
        topic="完成一个环境监测项目",
        difficulty="intermediate",
        style=None,
        composition_style="project_driven",
        course_type="project",
        course_intent={
            "type": "project",
            "project_goal": "完成一个环境监测项目",
            "expected_deliverable": "监测报告与演示原型",
        },
    )
    brief = artifacts["course_generation_brief"]

    assert brief["learner_starting_profile"]["status"] == "insufficient"
    assert any(
        "verify_in_project" in item
        for item in brief["personalization_rationale"]
    )


def test_outline_prompt_and_blueprint_expose_type_and_path_reason():
    brief = build_course_generation_artifacts(
        course_id="course-project-prompt",
        topic="玻璃杯设计",
        difficulty="intermediate",
        style=None,
        composition_style="project_driven",
        course_type="project",
        course_intent={
            "type": "project",
            "project_goal": "设计环保保温玻璃杯",
            "expected_deliverable": "设计方案和原型",
        },
    )["course_generation_brief"]
    prompt = CoursePromptComposer().build_outline_skeleton_v2_prompt(
        subject="玻璃杯设计",
        audience="大学生",
        brief=brief,
        profile=SimpleNamespace(to_dict=lambda: {"primary_mode": "general"}),
        difficulty_profile={},
        gap_assessment={},
        adaptation_decision={},
        material_context="",
    )
    assert "课程类型：项目实战" in prompt
    assert "verify_in_project" in prompt
    assert "项目里程碑" in prompt

    plan = normalize_course_outline_contract({
        "course_title": "玻璃杯设计",
        "chapters": [{
            "chapter_number": 1,
            "title": "材料方案验证",
            "learning_path_role": "focus",
            "path_reason": "学习者不熟悉玻璃材料",
            "sections": [{
                "title": "比较候选玻璃材料",
                "learning_path_role": "verify_in_project",
                "path_reason": "在材料选择任务中验证理解",
            }],
        }],
    })
    blueprint = build_course_blueprint_from_plan(
        plan,
        {"course_generation_brief": brief},
    )
    assert blueprint["course_type"] == "project"
    assert blueprint["course_intent"]["expected_deliverable"] == "设计方案和原型"
    assert blueprint["nodes"][0]["learning_path_role"] == "verify_in_project"
    assert blueprint["nodes"][0]["path_reason"] == "在材料选择任务中验证理解"

    draft = build_blueprint_draft({
        "course_id": "course-project-prompt",
        "course_type": "project",
        "course_intent": blueprint["course_intent"],
        "learner_starting_profile": blueprint["learner_starting_profile"],
        "nodes": [{
            "node_id": "L2-1-1",
            "learning_path_role": "verify_in_project",
            "path_reason": "在项目中验证",
        }],
    })
    assert draft["course_type"] == "project"
    assert draft["nodes"][0]["learning_path_role"] == "verify_in_project"
