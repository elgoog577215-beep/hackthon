from __future__ import annotations

import asyncio

from course_document import CourseDocument, CourseSection, refresh_document_revision
from course_evolution.core import CourseEvolutionRepository
from course_evolution.teacher_execution import generate_teacher_course_change_candidates
from course_evolution.teacher_planning import (
    build_teacher_course_change_context,
    create_teacher_course_change_plan,
    review_teacher_course_change_scope,
)
from question_bank import QuestionBankRepository
from teacher_lesson_authoring import TeacherLessonAuthoringRepository
from teaching_representations import TeachingRepresentationRepository


def _document() -> CourseDocument:
    return refresh_document_revision(CourseDocument(
        course_id="course-targeted",
        title="定向重建课程",
        sections=[
            CourseSection(
                section_id="lesson-1",
                title="第一讲",
                position=0,
            ),
            CourseSection(
                section_id="section-target",
                parent_section_id="lesson-1",
                title="目标小节",
                position=1,
                level=2,
            ),
            CourseSection(
                section_id="section-safe",
                parent_section_id="lesson-1",
                title="保留小节",
                position=2,
                level=2,
            ),
        ],
    ))


def _authoring_state() -> dict:
    return {
        "course_id": "course-targeted",
        "revision": 1,
        "outline_revision_id": "outline-1",
        "lessons": {
            "lesson-1": {
                "lesson_unit_id": "lesson-1",
                "working_revision_id": "plan-last-good",
                "source_state": "current",
                "revisions": [{
                    "revision_id": "plan-last-good",
                    "plan": {
                        "sections": [
                            {
                                "section_node_id": "section-target",
                                "title": "目标小节",
                                "content": "这里讲解旧词。",
                            },
                            {
                                "section_node_id": "section-safe",
                                "title": "保留小节",
                                "content": "这里必须保持原样。",
                            },
                        ],
                    },
                }],
                "working_script_revision_id": "script-last-good",
                "script_revisions": [{
                    "revision_id": "script-last-good",
                    "source_lesson_plan_revision_id": "plan-last-good",
                    "sections": [{
                        "section_node_id": "section-target",
                        "title": "目标小节",
                        "blocks": [
                            {
                                "block_id": "script-target",
                                "module_id": "core_explanation",
                                "role": "explanation",
                                "title": "目标讲义块",
                                "content": "教师讲述旧词。",
                            },
                            {
                                "block_id": "script-safe",
                                "module_id": "example",
                                "role": "example",
                                "title": "保留讲义块",
                                "content": "这段必须保持原样。",
                            },
                        ],
                    }],
                }],
                "ppt_assets": [],
            },
        },
    }


def _course_data() -> dict:
    document = _document()
    return {
        "course_id": document.course_id,
        "course_name": document.title,
        "course_document": document.model_dump(mode="json"),
        "course_document_revision": document.document_revision,
        "nodes": [
            {
                "node_id": "lesson-1",
                "node_level": 1,
                "node_name": "第一讲",
            },
            {
                "node_id": "section-target",
                "parent_node_id": "lesson-1",
                "node_level": 2,
                "node_name": "目标小节",
            },
            {
                "node_id": "section-safe",
                "parent_node_id": "lesson-1",
                "node_level": 2,
                "node_name": "保留小节",
            },
        ],
    }


def test_teacher_plan_and_script_blocks_use_shared_candidate_executor(tmp_path):
    authoring_repository = TeacherLessonAuthoringRepository(tmp_path / "authoring")
    authoring_repository._save(_authoring_state())
    course_data = _course_data()
    context = build_teacher_course_change_context(
        course_id="course-targeted",
        document=_document(),
        preview=None,
        authoring=authoring_repository.view("course-targeted"),
        question_bank=None,
        representation_registries=[],
    )
    plan_unit = next(
        item
        for item in context.units
        if item.asset_type == "lesson_plan"
        and item.unit_id.endswith(":section-target")
    )
    script_unit = next(
        item
        for item in context.units
        if item.asset_type == "script"
        and item.unit_id.endswith(":script-target")
    )

    async def analyzer(_overview, _candidates, _instruction):
        return {
            "analysis_mode": "deterministic_exact_replace",
            "interpreted_goal": "只把目标块中的旧词改成新词",
            "signal_kind": "semantic",
            "affected_units": [
                {
                    "unit_id": unit.unit_id,
                    "disposition": "rewrite_partial",
                    "reason": "目标块需要同步",
                    "confidence": 1,
                    "literal_replacement": {
                        "before": "旧词",
                        "after": "新词",
                    },
                }
                for unit in (plan_unit, script_unit)
            ],
            "structure": {"required": False},
        }

    evolution_repository = CourseEvolutionRepository(tmp_path / "evolution")
    created = asyncio.run(create_teacher_course_change_plan(
        context=context,
        user_id="teacher-1",
        request_id="targeted-rebuild-1",
        instruction="只更新目标教案段落和目标讲义块中的指定术语",
        repository=evolution_repository,
        analyzer=analyzer,
    ))
    plan = created.change_sets[0]
    migration_ids = [
        item.migration_id for item in plan.teacher_change_planning.unit_migrations
    ]
    reviewed = review_teacher_course_change_scope(
        repository=evolution_repository,
        user_id="teacher-1",
        course_id="course-targeted",
        change_set_id=plan.change_set_id,
        selected_migration_ids=migration_ids,
    )
    assert reviewed.change_sets[0].impact_summary["scope_review"][
        "selected_migration_ids"
    ] == migration_ids
    assert evolution_repository.load(
        "teacher-1",
        "course-targeted",
    ).change_sets[0].impact_summary["scope_review"]["selected_migration_ids"] == (
        migration_ids
    )

    before = authoring_repository.lesson("course-targeted", "lesson-1")
    generated = asyncio.run(generate_teacher_course_change_candidates(
        course_data=course_data,
        user_id="teacher-1",
        change_set_id=plan.change_set_id,
        repository=evolution_repository,
        authoring_repository=authoring_repository,
        representation_repository=TeachingRepresentationRepository(
            tmp_path / "representations"
        ),
        question_bank_repository=QuestionBankRepository(tmp_path / "question-bank"),
        course_service=object(),
    )).change_sets[0]
    after = authoring_repository.lesson("course-targeted", "lesson-1")

    assert after["working_revision_id"] == "plan-last-good"
    assert after["working_script_revision_id"] == "script-last-good"
    assert after["revisions"] == before["revisions"]
    assert after["script_revisions"] == before["script_revisions"]

    plan_candidate = after["ai_candidates"][-1]
    candidate_sections = {
        item["section_node_id"]: item
        for item in plan_candidate["plan"]["sections"]
    }
    assert "新词" in candidate_sections["section-target"]["content"]
    assert candidate_sections["section-safe"]["content"] == "这里必须保持原样。"

    script_candidate = after["script_ai_candidates"][-1]
    assert set(script_candidate["block_replacements"]) == {"script-target"}
    assert "新词" in script_candidate["block_replacements"]["script-target"]["content"]
    assert "script-safe" not in script_candidate["block_replacements"]

    rebuild = generated.impact_summary["teacher_asset_targeted_rebuild"]
    assert rebuild["schema_version"] == "downstream_rebuild_receipt_v1"
    assert rebuild["downstream"]["readable_fallback_count"] == 2
    rebuilt_items = {
        item["type"]: item
        for item in rebuild["downstream"]["items"]
    }
    assert rebuilt_items["lesson_plan_section"]["state"] == "candidate"
    assert rebuilt_items["lesson_plan_section"]["last_available"]["revision"] == (
        "plan-last-good"
    )
    assert rebuilt_items["script_block"]["state"] == "candidate"
    assert rebuilt_items["script_block"]["last_available"]["revision"] == (
        "script-last-good"
    )
    assert {
        item["type"] for item in rebuild["receipts"]
    } == {"lesson_plan_section", "script_block"}
    assert all(item["outcome"] == "stale" for item in rebuild["receipts"])
    assert all(item["readable_fallback"] for item in rebuild["receipts"])
