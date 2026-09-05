"""Regressions for teacher decisions, complete search and recoverable candidates."""

import asyncio
from unittest.mock import AsyncMock

from course_document import CourseBlock, CourseDocument, CourseSection, refresh_document_revision
from course_evolution import CourseEvolutionRepository
from course_evolution import teacher_execution as execution
from course_evolution.teacher_planning import (
    _explicit_term_replacement_analysis,
    build_teacher_course_change_context,
    create_teacher_course_change_plan,
    review_teacher_course_change_scope,
)
from question_bank import QuestionBankRepository
from teacher_lesson_authoring import TeacherLessonAuthoringRepository
from teaching_representations import TeachingRepresentationRepository


def document() -> CourseDocument:
    return refresh_document_revision(
        CourseDocument(
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
        )
    )


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
                "revisions": [
                    {
                        "revision_id": "plan-r1",
                        "plan": {
                            "sections": [
                                {
                                    "section_node_id": "section-1",
                                    "section_id": "plan-section-1",
                                    "title": "案例推导",
                                    "content": "解释斜面受力。",
                                }
                            ]
                        },
                    }
                ],
                "working_script_revision_id": "script-r1",
                "script_revisions": [
                    {
                        "revision_id": "script-r1",
                        "sections": [
                            {
                                "section_node_id": "section-1",
                                "title": "牛顿第二定律",
                                "blocks": [
                                    {
                                        "block_id": "script-example",
                                        "title": "斜面案例",
                                        "role": "example",
                                        "content": "展示受力图。",
                                    }
                                ],
                            }
                        ],
                    }
                ],
                "ppt_assets": [
                    {
                        "asset_id": "ppt-1",
                        "source_state": "current",
                        "synthetic_course_id": "teacher-lesson-1",
                        "working_v6_revision_id": "ppt-binding-1",
                        "working_representation_id": "representation-1",
                        "v6_revisions": [
                            {
                                "revision_id": "ppt-binding-1",
                                "spec_id": "spec-1",
                            }
                        ],
                    }
                ],
            },
        },
    }


def representation_registry() -> dict:
    return {
        "course_id": "teacher-lesson-1",
        "specs": [
            {
                "spec_id": "spec-1",
                "revision": "spec-r1",
                "payload": {
                    "content": {
                        "pages": [
                            {
                                "page_id": "page-1",
                                "title": "斜面案例",
                                "source_section_ids": ["section-1"],
                                "regions": [{"content": "斜面受力图与结论"}],
                            }
                        ]
                    }
                },
            }
        ],
    }


def question_bank() -> dict:
    return {
        "course_id": "course-1",
        "bundle_revision_id": "questions-r1",
        "items": [
            {
                "item_id": "question-1",
                "section_id": "section-1",
                "stem": "斜面上的物体受到哪些力？",
                "answer": "重力、支持力与摩擦力。",
            }
        ],
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


def test_literal_replace_reads_nested_lesson_body():
    value = authoring()
    value["lessons"]["chapter-1"]["revisions"][0]["plan"]["sections"] = [
        {
            "node_id": "section-1",
            "title": "教学实施",
            "teaching_modules": [{"teacher_activity": "本讲使用旧术语说明原理。"}],
        }
    ]
    ctx = build_teacher_course_change_context(
        course_id="course-1",
        document=document(),
        preview=None,
        authoring=value,
        question_bank=None,
        representation_registries=[],
    )
    result = _explicit_term_replacement_analysis(ctx, "把“旧术语”替换为“新术语”")
    assert any(item["unit_id"].startswith("lesson_plan:") for item in result["affected_units"]), result


def test_literal_replace_reads_beyond_summary_limit():
    value = authoring()
    value["lessons"]["chapter-1"]["revisions"][0]["plan"]["sections"] = [
        {"node_id": "section-1", "title": "教学实施", "content": "内容" * 700 + "旧术语"}
    ]
    ctx = build_teacher_course_change_context(
        course_id="course-1",
        document=document(),
        preview=None,
        authoring=value,
        question_bank=None,
        representation_registries=[],
    )
    result = _explicit_term_replacement_analysis(ctx, "把“旧术语”替换为“新术语”")
    assert any(item["unit_id"].startswith("lesson_plan:") for item in result["affected_units"]), result


def prepared(tmp_path):
    repo = CourseEvolutionRepository(tmp_path / "evolution")
    ctx = context()
    target = next(u for u in ctx.units if u.asset_type == "lesson_plan")

    async def analyze(*args):
        return {
            "interpreted_goal": "完善教案案例",
            "signal_kind": "semantic",
            "affected_units": [
                {"unit_id": target.unit_id, "disposition": "rewrite_partial", "reason": "完善案例", "confidence": 0.9}
            ],
            "structure": {"required": False},
        }

    state = asyncio.run(
        create_teacher_course_change_plan(
            context=ctx,
            user_id="teacher",
            request_id="audit",
            instruction="完善教案案例",
            repository=repo,
            analyzer=analyze,
        )
    )
    p = state.change_sets[0]
    state = review_teacher_course_change_scope(
        repository=repo,
        user_id="teacher",
        course_id="course-1",
        change_set_id=p.change_set_id,
        selected_migration_ids=[m.migration_id for m in p.teacher_change_planning.unit_migrations],
    )
    return repo, state


def run_generate(tmp_path, repo, p):
    return asyncio.run(
        execution.generate_teacher_course_change_candidates(
            course_data={"course_id": "course-1"},
            user_id="teacher",
            change_set_id=p.change_set_id,
            repository=repo,
            authoring_repository=TeacherLessonAuthoringRepository(tmp_path / "authoring"),
            representation_repository=TeachingRepresentationRepository(tmp_path / "representations"),
            question_bank_repository=QuestionBankRepository(tmp_path / "questions"),
            course_service=object(),
        )
    )


def test_candidate_retry_preserves_successful_domain_operation(tmp_path, monkeypatch):
    repo, state = prepared(tmp_path)
    p = state.change_sets[0]
    op = execution._operation(
        plan=p,
        domain="lesson_plan",
        migrations=p.teacher_change_planning.unit_migrations,
        payload={"candidate_id": "successful-candidate"},
    )
    p.operations = [op]
    repo.save(state)
    monkeypatch.setattr(
        execution, "_generate_teacher_asset_candidates_through_shared_executor", AsyncMock(return_value=([], {}))
    )
    monkeypatch.setattr(execution, "_generate_ppt_candidates", AsyncMock(return_value=[]))
    monkeypatch.setattr(execution, "_generate_question_bank_candidate", AsyncMock(return_value=[]))
    result = run_generate(tmp_path, repo, p).change_sets[0]
    assert op.operation_id in [item.operation_id for item in result.operations], result.model_dump()


def test_completed_generation_must_not_revive_rejected_plan(tmp_path, monkeypatch):
    repo, state = prepared(tmp_path)
    p = state.change_sets[0]

    async def generation(**kwargs):
        def reject(latest):
            latest.change_sets[0].status = "rejected"
            return latest

        repo.update("teacher", "course-1", reject)
        return [], {}

    monkeypatch.setattr(execution, "_generate_teacher_asset_candidates_through_shared_executor", generation)
    monkeypatch.setattr(execution, "_generate_ppt_candidates", AsyncMock(return_value=[]))
    monkeypatch.setattr(execution, "_generate_question_bank_candidate", AsyncMock(return_value=[]))
    try:
        run_generate(tmp_path, repo, p)
    except ValueError:
        pass  # Rejecting an obsolete result is also valid.
    assert repo.load("teacher", "course-1").change_sets[0].status == "rejected"


def test_reject_route_matches_application_service_signature(tmp_path, monkeypatch):
    from starlette.requests import Request

    from course_evolution import application
    from routers import course_evolution as route

    repo, state = prepared(tmp_path)
    plan_id = state.change_sets[0].change_set_id
    reject = application.reject_change_set
    monkeypatch.setattr(application, "reject_change_set", lambda **kwargs: reject(repository=repo, **kwargs))
    service = application.CourseEvolutionApplicationService(
        evolution_repository=repo,
        document_repository=None,
        authoring_repository=None,
        representation_repository=None,
        question_bank_repository=None,
        course_service=None,
    )
    monkeypatch.setattr(route, "get_course_or_404", AsyncMock(return_value={"course_id": "course-1"}))
    monkeypatch.setattr(route, "get_course_document_repository", lambda: None)
    monkeypatch.setattr(route, "_course_evolution_service", lambda: service)
    request = Request({"type": "http", "headers": [(b"x-user-id", b"teacher")]})
    asyncio.run(
        route.reject_course_evolution_change_set(
            "course-1",
            plan_id,
            route.RejectCourseEvolutionRequest(reason="放弃"),
            request,
        )
    )
    assert repo.load("teacher", "course-1").change_sets[0].status == "rejected"


def test_lesson_length_advice_does_not_force_checkpoint_regeneration():
    from teacher_lesson_authoring import _teacher_script_retry_block_ids
    from teacher_script import SCRIPT_PIPELINE_VERSION, SCRIPT_QUALITY_VERSION, validate_teacher_script_revision

    sections = [
        {
            "section_node_id": "s",
            "quality_report": {
                "schema_version": SCRIPT_QUALITY_VERSION,
                "pipeline_version": SCRIPT_PIPELINE_VERSION,
                "blocking_issues": [],
            },
            "blocks": [
                {"block_id": str(i), "planned_minutes": 10, "content": text}
                for i, text in enumerate(
                    [
                        "函数在闭区间上的连续性是本节的讨论前提。",
                        "请先画出圆周运动的轨迹，比较速度方向。",
                        "取样完成后记录仪器精度，检查实验误差。",
                        "讨论不同方案的资源成本，再解释你的选择。",
                    ]
                )
            ],
        }
    ]
    report = validate_teacher_script_revision(sections, generation_source="model_block_pipeline")
    assert report["passed"]
    assert any(i["code"] == "teacher_script:lesson_too_shallow" for i in report["review_issues"])
    assert not _teacher_script_retry_block_ids(report, {str(i): i for i in range(4)}), report
