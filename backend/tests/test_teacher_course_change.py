from __future__ import annotations

import asyncio
from copy import deepcopy

import pytest

from course_document import CourseBlock, CourseDocument, CourseSection, refresh_document_revision
from course_evolution import CourseEvolutionRepository, accept_change_set, undo_change_set
from course_repository import CourseDocumentRepository
from teacher_course_change import (
    build_teacher_course_change_context,
    context_view,
    create_teacher_course_change_plan,
    rank_change_units,
    review_teacher_course_change_scope,
)


def document() -> CourseDocument:
    return refresh_document_revision(CourseDocument(
        course_id="course-1",
        title="大学物理",
        sections=[
            CourseSection(section_id="chapter-1", title="第一章 力与运动", position=0),
            CourseSection(
                section_id="section-1",
                parent_section_id="chapter-1",
                title="1.1 牛顿第二定律",
                position=1,
                level=2,
            ),
        ],
        blocks=[
            CourseBlock(
                block_id="block-example",
                section_id="section-1",
                position=0,
                role="example",
                payload={"title": "斜面案例", "markdown": "先给出受力图，再列方程。"},
            ),
        ],
    ))


def authoring() -> dict:
    return {
        "course_id": "course-1",
        "revision": 8,
        "outline_revision_id": "outline-r8",
        "lessons": {
            "chapter-1": {
                "lesson_unit_id": "chapter-1",
                "working_revision_id": "plan-r1",
                "source_state": "current",
                "revisions": [{
                    "revision_id": "plan-r1",
                    "plan": {"sections": [{
                        "section_node_id": "section-1",
                        "section_id": "plan-section-1",
                        "title": "案例推导",
                        "content": "解释斜面受力。",
                    }]},
                }],
                "working_script_revision_id": "script-r1",
                "script_confirmation": {"source_state": "current"},
                "script_revisions": [{
                    "revision_id": "script-r1",
                    "sections": [{
                        "section_node_id": "section-1",
                        "title": "牛顿第二定律",
                        "blocks": [{
                            "block_id": "script-example",
                            "title": "斜面案例",
                            "role": "example",
                            "content": "展示受力图。",
                        }],
                    }],
                }],
                "ppt_assets": [{
                    "asset_id": "ppt-1",
                    "source_state": "current",
                    "synthetic_course_id": "teacher-lesson-1",
                    "working_v6_revision_id": "ppt-binding-1",
                    "working_representation_id": "representation-1",
                    "v6_revisions": [{
                        "revision_id": "ppt-binding-1",
                        "spec_id": "spec-1",
                    }],
                }],
            },
        },
    }


def representation_registry() -> dict:
    return {
        "course_id": "teacher-lesson-1",
        "specs": [{
            "spec_id": "spec-1",
            "revision": "spec-r1",
            "payload": {"content": {"pages": [{
                "page_id": "page-1",
                "title": "斜面案例",
                "source_section_ids": ["section-1"],
                "regions": [{"content": "斜面受力图与结论"}],
            }]}},
        }],
    }


def question_bank() -> dict:
    return {
        "course_id": "course-1",
        "bundle_revision_id": "questions-r1",
        "items": [{
            "item_id": "question-1",
            "section_id": "section-1",
            "stem": "斜面上的物体受到哪些力？",
            "answer": "重力、支持力与摩擦力。",
        }],
    }


def context():
    return build_teacher_course_change_context(
        course_id="course-1",
        document=document(),
        preview=None,
        authoring=authoring(),
        question_bank=question_bank(),
        representation_registries=[representation_registry()],
    )


class MemoryCourseStorage:
    def __init__(self, course: dict):
        self.course = deepcopy(course)

    def load_course(self, course_id: str):
        if course_id != self.course["course_id"]:
            return None
        return deepcopy(self.course)

    async def save_course(self, course_id: str, course: dict):
        assert course_id == self.course["course_id"]
        self.course = deepcopy(course)


def test_context_indexes_every_existing_truth_without_copying_a_second_course():
    value = context()
    counts = {item.asset_type: item.count for item in value.assets}

    assert value.ready is True
    assert value.source_mode == "mixed"
    assert counts == {
        "outline": 2,
        "course_content": 1,
        "lesson_plan": 1,
        "script": 1,
        "ppt": 1,
        "question_bank": 1,
    }
    assert value.base_revision_vector["course_document"] == document().document_revision
    assert value.base_revision_vector["teacher_lesson_authoring"] == "8"
    projection = context_view(value)
    assert projection["summary"]["indexed_units"] == 7
    assert all(len(item["text"]) <= 320 for item in projection["units"])


def test_rank_uses_roles_and_keeps_a_cross_asset_sample_for_imprecise_language():
    ranked = rank_change_units(context(), "以后所有例子都讲得详细一点")

    assert ranked[0]["role"] == "example"
    assert {item["asset_type"] for item in ranked} == {
        "outline", "course_content", "lesson_plan", "script", "ppt", "question_bank",
    }


def test_rank_reserves_each_asset_when_a_broad_request_fills_the_limit():
    value = context()
    seed = value.units[0]
    value.units = [
        seed.model_copy(update={
            "unit_id": f"{asset_type}:{index}",
            "asset_type": asset_type,
            "title": f"{asset_type} {index}",
        })
        for asset_type in ("outline", "lesson_plan", "script", "ppt", "question_bank")
        for index in range(40)
    ]

    ranked = rank_change_units(value, "整个课程全部统一更新", limit=20)

    assert len(ranked) == 20
    assert {item["asset_type"] for item in ranked} == {
        "outline", "lesson_plan", "script", "ppt", "question_bank",
    }


def test_course_plan_uses_ai_judgement_and_is_idempotent(tmp_path):
    repository = CourseEvolutionRepository(tmp_path)
    value = context()

    async def analyzer(_overview, candidates, _instruction):
        script = next(item for item in candidates if item["asset_type"] == "script")
        slide = next(item for item in candidates if item["asset_type"] == "ppt")
        return {
            "interpreted_goal": "补全课程案例的推导，并同步讲稿与 PPT",
            "signal_kind": "semantic",
            "signal_confidence": .93,
            "protected_requirements": ["保留原始资料"],
            "affected_units": [
                {"unit_id": script["unit_id"], "disposition": "rewrite_partial", "reason": "讲稿案例需要展开", "confidence": .91},
                {"unit_id": slide["unit_id"], "disposition": "regenerate", "reason": "PPT 需同步可见推导", "confidence": .88},
            ],
            "structure": {"required": False},
        }

    first = asyncio.run(create_teacher_course_change_plan(
        context=value,
        user_id="teacher-1",
        request_id="request-1",
        instruction="所有例子都讲详细一点",
        repository=repository,
        analyzer=analyzer,
    ))
    second = asyncio.run(create_teacher_course_change_plan(
        context=value,
        user_id="teacher-1",
        request_id="request-1",
        instruction="所有例子都讲详细一点",
        repository=repository,
        analyzer=analyzer,
    ))

    assert len(first.change_sets) == 1
    assert len(second.change_sets) == 1
    plan = second.change_sets[0]
    assert plan.target_section_id == ""
    assert plan.scope_selection == "whole_course"
    assert plan.teacher_change_planning.status == "impact_ready"
    assert plan.impact_summary["analysis_mode"] == "ai_ranked"
    assert plan.impact_summary["formal_content_changed"] is False
    assert plan.impact_summary["coverage"]["affected_units"] == 2


def test_exact_content_candidate_applies_as_one_teacher_command_and_undoes(tmp_path):
    evolution_repository = CourseEvolutionRepository(tmp_path / "evolution")
    value = context()
    target = next(item for item in value.units if item.asset_type == "course_content")

    async def analyzer(_overview, _candidates, _instruction):
        return {
            "interpreted_goal": "把斜面案例中的受力图统一改为自由体图",
            "signal_kind": "semantic",
            "signal_confidence": .97,
            "affected_units": [{
                "unit_id": target.unit_id,
                "disposition": "rewrite_partial",
                "reason": "术语统一",
                "confidence": .98,
                "content_patches": [{
                    "field": "markdown",
                    "before": "受力图",
                    "after": "自由体图",
                    "replace_all": True,
                }],
            }],
            "structure": {"required": False},
        }

    state = asyncio.run(create_teacher_course_change_plan(
        context=value,
        user_id="teacher-1",
        request_id="exact-request-1",
        instruction="把受力图永远替换成自由体图",
        repository=evolution_repository,
        analyzer=analyzer,
    ))
    plan = state.change_sets[0]
    affected = plan.impact_summary["affected_units"][0]
    assert plan.teacher_change_planning.status == "candidate_ready"
    assert plan.impact_summary["application_capability"] == "course_document_operation_group"
    assert affected["before_preview"] != affected["after_preview"]
    assert affected["change_count"] == 1

    current_document = document()
    raw_course = {
        "course_id": current_document.course_id,
        "course_name": current_document.title,
        "course_schema_version": "course_document_v1",
        "course_document": current_document.model_dump(mode="json"),
        "course_document_revision": current_document.document_revision,
        "course_document_authoritative": True,
        "course_operation_log": [],
    }
    document_repository = CourseDocumentRepository(MemoryCourseStorage(raw_course))
    applied = accept_change_set(
        raw_course,
        user_id="teacher-1",
        change_set_id=plan.change_set_id,
        selected_scope="current",
        selected_operation_ids=[affected["operation_id"]],
        repository=evolution_repository,
        document_repository=document_repository,
    )

    updated_document, _ = document_repository.load_document("course-1")
    assert updated_document.blocks[0].payload["markdown"] == "先给出自由体图，再列方程。"
    receipt = applied.change_sets[0].application_receipt
    assert receipt["applied_count"] == 1
    assert receipt["failed_count"] == 0
    assert receipt["items"][0]["status"] == "applied"

    undo_change_set(
        user_id="teacher-1",
        course_id="course-1",
        change_set_id=plan.change_set_id,
        repository=evolution_repository,
        document_repository=document_repository,
    )
    restored_document, _ = document_repository.load_document("course-1")
    assert restored_document.blocks[0].payload["markdown"] == "先给出受力图，再列方程。"


def test_explicit_term_replacement_compiles_without_model_availability(tmp_path):
    repository = CourseEvolutionRepository(tmp_path)

    async def unavailable_analyzer(*_args):
        raise AssertionError("精确替换不应调用模型")

    state = asyncio.run(create_teacher_course_change_plan(
        context=context(),
        user_id="teacher-1",
        request_id="deterministic-replace-1",
        instruction="把“受力图”统一替换为“自由体图”，不改变课程结构",
        repository=repository,
        analyzer=unavailable_analyzer,
    ))

    plan = state.change_sets[0]
    affected = plan.impact_summary["affected_units"]
    assert plan.impact_summary["analysis_mode"] == (
        "deterministic_exact_replace"
    )
    assert plan.teacher_change_planning.status == "candidate_ready"
    assert len(plan.operations) == 1
    assert affected[0]["change_count"] == 1
    assert "自由体图" in affected[0]["after_preview"]


def test_explicit_term_replacement_reports_zero_formal_hits(tmp_path):
    repository = CourseEvolutionRepository(tmp_path)
    state = asyncio.run(create_teacher_course_change_plan(
        context=context(),
        user_id="teacher-1",
        request_id="deterministic-replace-missing",
        instruction="把“不存在的术语”替换为“新术语”",
        repository=repository,
        analyzer=None,
    ))

    plan = state.change_sets[0]
    assert plan.impact_summary["analysis_mode"] == (
        "deterministic_exact_replace"
    )
    assert plan.teacher_change_planning.status == "needs_clarification"
    assert plan.operations == []
    assert "未找到" in plan.teacher_change_planning.intent.blocking_questions[0]


def test_scope_review_persists_selected_and_excluded_units_without_applying(tmp_path):
    repository = CourseEvolutionRepository(tmp_path)

    async def analyzer(_overview, candidates, _instruction):
        selected = candidates[:2]
        return {
            "interpreted_goal": "调整课程",
            "signal_kind": "semantic",
            "affected_units": [
                {"unit_id": item["unit_id"], "disposition": "rewrite_partial", "reason": "相关", "confidence": .8}
                for item in selected
            ],
            "structure": {"required": False},
        }

    state = asyncio.run(create_teacher_course_change_plan(
        context=context(),
        user_id="teacher-1",
        request_id="request-1",
        instruction="调整课程",
        repository=repository,
        analyzer=analyzer,
    ))
    plan = state.change_sets[0]
    migration_ids = [item.migration_id for item in plan.teacher_change_planning.unit_migrations]
    reviewed = review_teacher_course_change_scope(
        repository=repository,
        user_id="teacher-1",
        course_id="course-1",
        change_set_id=plan.change_set_id,
        selected_migration_ids=[migration_ids[0]],
    )

    updated = reviewed.change_sets[0]
    assert updated.status == "pending"
    assert updated.impact_summary["scope_review"]["selected_migration_ids"] == [migration_ids[0]]
    assert updated.impact_summary["scope_review"]["excluded_migration_ids"] == [migration_ids[1]]
    assert updated.impact_summary["scope_review"]["formal_content_changed"] is False


def test_scope_review_rejects_foreign_migrations(tmp_path):
    repository = CourseEvolutionRepository(tmp_path)
    with pytest.raises(KeyError):
        review_teacher_course_change_scope(
            repository=repository,
            user_id="teacher-1",
            course_id="course-1",
            change_set_id="missing",
            selected_migration_ids=["foreign"],
        )


def test_structure_review_confirms_proposed_tree_without_writing_course_content(tmp_path):
    repository = CourseEvolutionRepository(tmp_path)

    async def analyzer(_overview, candidates, _instruction):
        return {
            "interpreted_goal": "拆分原理与项目实践章节",
            "signal_kind": "structural",
            "signal_confidence": .91,
            "affected_units": [{
                "unit_id": candidates[0]["unit_id"],
                "disposition": "reuse_rebind",
                "reason": "迁移到拆分后的章节",
                "confidence": .88,
            }],
            "structure": {
                "required": True,
                "reason": "章节职责需要拆分",
                "affected_node_ids": ["chapter-1"],
                "proposed_outline": [
                    {"provisional_id": "new-1", "title": "第一章 原理", "parent_ref": "root", "source_node_ids": ["chapter-1"]},
                    {"provisional_id": "new-2", "title": "第二章 项目实践", "parent_ref": "root", "source_node_ids": ["chapter-1"]},
                ],
            },
        }

    state = asyncio.run(create_teacher_course_change_plan(
        context=context(),
        user_id="teacher-1",
        request_id="structure-request-1",
        instruction="把第一章拆成原理与项目实践",
        repository=repository,
        analyzer=analyzer,
    ))
    plan = state.change_sets[0]
    migration_ids = [item.migration_id for item in plan.teacher_change_planning.unit_migrations]

    reviewed = review_teacher_course_change_scope(
        repository=repository,
        user_id="teacher-1",
        course_id="course-1",
        change_set_id=plan.change_set_id,
        selected_migration_ids=migration_ids,
        confirm_structure=True,
    )

    updated = reviewed.change_sets[0]
    assert updated.teacher_change_planning.structure_review_status == "confirmed"
    assert updated.impact_summary["structure_review"]["status"] == "confirmed"
    assert updated.impact_summary["structure_review"]["formal_content_changed"] is False


def test_reviewed_merge_retire_and_reorder_use_one_outline_command_and_undo(tmp_path):
    structural_document = refresh_document_revision(CourseDocument(
        course_id="course-structure",
        title="结构课",
        sections=[
            CourseSection(section_id=value, title=f"章节 {value.upper()}", position=index)
            for index, value in enumerate(("a", "b", "c", "d"))
        ],
        blocks=[
            CourseBlock(
                block_id=f"block-{value}",
                section_id=value,
                position=0,
                payload={"markdown": f"内容 {value.upper()}"},
            )
            for value in ("a", "b", "c", "d")
        ],
    ))
    value = build_teacher_course_change_context(
        course_id="course-structure",
        document=structural_document,
        preview=None,
        authoring={},
        question_bank={},
        representation_registries=[],
    )
    evolution_repository = CourseEvolutionRepository(tmp_path / "evolution")

    async def analyzer(_overview, _candidates, _instruction):
        return {
            "interpreted_goal": "合并 A/B，删除 C，并把 D 放到最前",
            "signal_kind": "structural",
            "signal_confidence": .96,
            "affected_units": [{
                "unit_id": "course_content:block-c",
                "disposition": "retire",
                "reason": "章节 C 被明确删除",
                "confidence": .99,
            }],
            "structure": {
                "required": True,
                "reason": "按老师确认的合并、删除与换序执行",
                "affected_node_ids": ["a", "b", "c", "d"],
                "retire_node_ids": ["c"],
                "proposed_outline": [
                    {"provisional_id": "new-d", "title": "章节 D", "parent_ref": "root", "source_node_ids": ["d"]},
                    {"provisional_id": "merge-ab", "title": "章节 A/B", "parent_ref": "root", "source_node_ids": ["a", "b"]},
                ],
            },
        }

    state = asyncio.run(create_teacher_course_change_plan(
        context=value,
        user_id="teacher-1",
        request_id="structure-merge-1",
        instruction="合并 A/B，删除 C，并把 D 放到最前",
        repository=evolution_repository,
        analyzer=analyzer,
    ))
    plan = state.change_sets[0]
    assert [item.operation_type for item in plan.operations] == ["REBUILD_COURSE_OUTLINE"]
    migration_ids = [item.migration_id for item in plan.teacher_change_planning.unit_migrations]
    reviewed = review_teacher_course_change_scope(
        repository=evolution_repository,
        user_id="teacher-1",
        course_id="course-structure",
        change_set_id=plan.change_set_id,
        selected_migration_ids=migration_ids,
        confirm_structure=True,
    )
    selected_operation_ids = reviewed.change_sets[0].selected_operation_ids

    raw_course = {
        "course_id": structural_document.course_id,
        "course_name": structural_document.title,
        "course_schema_version": "course_document_v1",
        "course_document": structural_document.model_dump(mode="json"),
        "course_document_revision": structural_document.document_revision,
        "course_document_authoritative": True,
        "course_operation_log": [],
    }
    document_repository = CourseDocumentRepository(MemoryCourseStorage(raw_course))
    accept_change_set(
        raw_course,
        user_id="teacher-1",
        change_set_id=plan.change_set_id,
        selected_scope="current",
        selected_operation_ids=selected_operation_ids,
        repository=evolution_repository,
        document_repository=document_repository,
    )
    updated, _ = document_repository.load_document("course-structure")
    assert [(item.section_id, item.title) for item in updated.sections] == [
        ("d", "章节 D"),
        ("a", "章节 A/B"),
    ]
    assert next(item for item in updated.blocks if item.block_id == "block-b").section_id == "a"
    assert next(item for item in updated.blocks if item.block_id == "block-c").status == "retired"

    undo_change_set(
        user_id="teacher-1",
        course_id="course-structure",
        change_set_id=plan.change_set_id,
        repository=evolution_repository,
        document_repository=document_repository,
    )
    restored, _ = document_repository.load_document("course-structure")
    assert [item.section_id for item in restored.sections] == ["a", "b", "c", "d"]
    assert next(item for item in restored.blocks if item.block_id == "block-b").section_id == "b"
    assert next(item for item in restored.blocks if item.block_id == "block-c").status == "final"
