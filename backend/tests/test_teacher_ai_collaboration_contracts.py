from __future__ import annotations

import asyncio
import json

from assessment_orchestrator import _authoring_quality_directive, _generation_context
from course_service import CourseService
from question_bank_jobs import QuestionBankRebuildJobRepository
from routers.teacher_lesson_authoring import (
    _apply_v6_page_expression,
    _v6_page_expression,
)
from teacher_lesson_authoring import TeacherLessonAuthoringRepository


def _lesson_plan() -> dict:
    return {
        "schema_version": "course_teaching_plan_v3",
        "sections": [{
            "node_id": "section-1",
            "learning_objective": "能够解释核心概念。",
            "teaching_modules": [],
        }],
    }


def test_script_and_v6_candidates_survive_repository_reload(tmp_path):
    repository = TeacherLessonAuthoringRepository(tmp_path)
    lesson = repository.save_plan_revision(
        "course-1",
        "lesson-1",
        _lesson_plan(),
        source_outline_revision_id="outline-1",
    )
    plan_revision_id = lesson["working_revision_id"]
    repository.confirm_plan_revision(
        "course-1",
        "lesson-1",
        plan_revision_id,
        quality_report={"passed": True, "blocking_issues": []},
    )
    lesson = repository.save_script_revision(
        "course-1",
        "lesson-1",
        [{
            "section_node_id": "section-1",
            "title": "核心概念",
            "content": "这是当前讲稿正文。",
        }],
        source_lesson_plan_revision_id=plan_revision_id,
    )
    script_revision_id = lesson["working_script_revision_id"]
    script_candidate = repository.save_script_ai_candidate(
        "course-1",
        "lesson-1",
        base_revision_id=script_revision_id,
        section_node_id="section-1",
        instruction="改成课堂化表达",
        replacement_text="请先观察这个现象，再归纳核心概念。",
        source_lesson_plan_revision_id=plan_revision_id,
        material_asset_ids=["material-2", "material-1", "material-2"],
    )
    repository.bind_v6_ppt_revision(
        "course-1",
        "lesson-1",
        source_lesson_plan_revision_id=plan_revision_id,
        source_script_revision_id=script_revision_id,
        synthetic_course_id="teacher-lesson-1",
        representation_id="representation-1",
        spec_id="spec-1",
        candidate_status="v6_ready",
    )
    ppt_candidate = repository.save_v6_ppt_ai_candidate(
        "course-1",
        "lesson-1",
        representation_id="representation-1",
        base_spec_id="spec-1",
        base_spec_revision="spec-revision-1",
        page_id="page-1",
        instruction="聚焦标题",
        candidate_page={"page_id": "page-1", "title": "更聚焦的标题"},
        changed_fields=["title"],
    )

    reloaded = TeacherLessonAuthoringRepository(tmp_path)
    assert reloaded.script_ai_candidate(
        "course-1", "lesson-1", script_candidate["candidate_id"]
    )["material_asset_ids"] == ["material-2", "material-1"]
    assert reloaded.pending_v6_ppt_ai_candidate(
        "course-1",
        "lesson-1",
        representation_id="representation-1",
        spec_id="spec-1",
        spec_revision="spec-revision-1",
    )["candidate_id"] == ppt_candidate["candidate_id"]


def test_v6_expression_candidate_updates_bound_regions_without_extra_page_fields():
    page = {
        "page_id": "page-1",
        "title": "原标题",
        "regions": [
            {"region_id": "region-subtitle", "slot_id": "subtitle", "content": "原副标题"},
            {"region_id": "region-body", "slot_id": "body", "content": "原关键内容"},
        ],
    }

    expression = _v6_page_expression(page)
    _apply_v6_page_expression(page, field="subtitle", value="新副标题")
    _apply_v6_page_expression(
        page,
        field="key_message",
        value="新关键内容",
        target_region_id=expression["key_region_id"],
    )

    assert set(page) == {"page_id", "title", "regions"}
    assert page["regions"][0]["content"] == "新副标题"
    assert page["regions"][1]["content"] == "新关键内容"


def test_v6_optimizer_returns_exact_region_bindings():
    class FakeOptimizer:
        async def _call_llm(self, prompt, **_kwargs):
            assert "region-body" not in prompt
            return json.dumps({
                "page_id": "page-1",
                "title": "聚焦后的标题",
                "subtitle": "原副标题",
                "key_message": "压缩后的关键内容",
            }, ensure_ascii=False)

        @staticmethod
        def _extract_json(value):
            return json.loads(value)

    result = asyncio.run(CourseService.optimize_teacher_lesson_v6_page(
        FakeOptimizer(),
        page={
            "page_id": "page-1",
            "title": "原标题",
            "resolved_layout": "builtin/qizhi-classroom/concept",
            "source_block_ids": ["source-1"],
            "speaker_notes": {"source_blocks": []},
            "regions": [
                {"region_id": "region-subtitle", "slot_id": "subtitle", "content": "原副标题"},
                {"region_id": "region-body", "slot_id": "body", "content": "原关键内容"},
            ],
        },
        instruction="聚焦标题和关键内容",
    ))

    assert result["changed_fields"] == ["title", "key_message"]
    assert result["page"]["subtitle_region_id"] == "region-subtitle"
    assert result["page"]["key_region_id"] == "region-body"


def test_question_bank_instruction_is_frozen_and_part_of_active_scope(tmp_path):
    repository = QuestionBankRebuildJobRepository(tmp_path / "jobs")
    first, _ = repository.create_job(
        "course-1",
        request_id="request-1",
        scope="nodes",
        node_ids=["section-1"],
        mode="incremental",
        actor_id="teacher-1",
        teacher_instruction="  增加应用题   ",
    )
    same, same_created = repository.create_job(
        "course-1",
        request_id="request-2",
        scope="nodes",
        node_ids=["section-1"],
        mode="incremental",
        actor_id="teacher-1",
        teacher_instruction="增加应用题",
    )
    changed, changed_created = repository.create_job(
        "course-1",
        request_id="request-3",
        scope="nodes",
        node_ids=["section-1"],
        mode="incremental",
        actor_id="teacher-1",
        teacher_instruction="降低起步难度",
    )

    assert first["teacher_instruction"] == "增加应用题"
    assert same_created is False
    assert same["job_id"] == first["job_id"]
    assert changed_created is True
    assert changed["job_id"] != first["job_id"]


def test_teacher_question_instruction_cannot_override_quality_gates():
    context = _generation_context(
        profile={},
        objective={"objective_id": "objective-1"},
        slot={"input_mode": "single_choice"},
        references=[],
        practice_level="medium",
        variant_index=0,
        teacher_instruction="  增加应用情境   ",
    )
    directive = _authoring_quality_directive()

    assert context["teacher_authoring_instruction"] == "增加应用情境"
    assert "cannot change the answer fact" in directive
    assert "cannot" in directive and "lower validation" in directive
