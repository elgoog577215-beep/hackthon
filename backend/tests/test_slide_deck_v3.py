from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from copy import deepcopy

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pptx import Presentation

from course_document import COURSE_DOCUMENT_SCHEMA, document_from_legacy_course
from course_repository import CourseDocumentRepository
from representation_compiler import (
    compile_core_representations,
    export_slide_deck_pptx,
    rebuild_slide_deck_variant_safely,
)
from slide_deck_v3 import (
    SLIDE_DECK_THEMES,
    SlideAllocationPlanV2,
    compile_slide_deck_v3,
    deterministic_slide_allocation,
    fragment_course_document,
    plan_slide_deck_v3,
)
from teaching_representations import TeachingRepresentationRepository


class MemoryStorage:
    def __init__(self, course: dict) -> None:
        self.course = deepcopy(course)

    def load_course(self, _course_id: str) -> dict:
        return deepcopy(self.course)

    async def save_course(self, _course_id: str, data: dict) -> None:
        self.course = deepcopy(data)


def source_course() -> dict:
    return {
        "course_id": "source-first-course",
        "course_name": "正文驱动课件",
        "nodes": [
            {
                "node_id": "section-core",
                "parent_node_id": "root",
                "node_name": "第一章 核心内容",
                "node_level": 1,
                "learning_objective": "理解正文驱动的课件生成",
                "objective_id": "objective-core",
                "content_blocks": [
                    {
                        "block_id": "block-core",
                        "title": "核心概念",
                        "content": (
                            "课程正文是唯一内容源。\n\n"
                            "- 页面只能引用原文片段\n"
                            "- 模型不能重写教学正文\n\n"
                            "页面过长时应当在安全边界继续分页。"
                        ),
                        "metadata": {"role": "concept"},
                    },
                    {
                        "block_id": "block-check",
                        "title": "理解检查",
                        "content": "为什么页面计划只能保存 fragment_id？",
                        "metadata": {"role": "checkpoint"},
                    },
                    {
                        "block_id": "block-supplement",
                        "title": "补充说明",
                        "content": "失败版本不能覆盖上一份可用课件。",
                        "metadata": {"role": "remediation"},
                    },
                ],
            },
        ],
    }


@pytest.mark.parametrize("mode", ["full", "teaching"])
def test_full_coverage_modes_materialize_every_source_fragment(mode: str) -> None:
    course = source_course()
    document = document_from_legacy_course(course)
    fragments = fragment_course_document(document)
    plan = deterministic_slide_allocation(
        document,
        fragments,
        mode=mode,
        theme="qizhi-classroom",
    )
    content = compile_slide_deck_v3(
        document,
        course,
        mode=mode,
        theme="qizhi-classroom",
        allocation_plan=plan,
    )

    assert content["schema_version"] == "slide_deck_v3"
    assert content["coverage_report"]["visible_coverage_ratio"] == 1.0
    assert content["coverage_report"]["hash_integrity_passed"] is True
    assert content["quality_summary"]["passed"] is True
    referenced = {
        fragment_id
        for page in content["allocation_plan"]["pages"]
        for fragment_id in page["fragment_ids"]
    }
    assert referenced == {item.fragment_id for item in fragments}
    if mode == "teaching":
        appendix_pages = [
            item for item in content["allocation_plan"]["pages"]
            if item["appendix"] and item["fragment_ids"]
        ]
        assert appendix_pages


def test_concise_mode_records_every_omitted_fragment() -> None:
    course = source_course()
    document = document_from_legacy_course(course)
    fragments = fragment_course_document(document)
    plan = deterministic_slide_allocation(
        document,
        fragments,
        mode="concise",
        theme="modern-geometric",
    )
    content = compile_slide_deck_v3(
        document,
        course,
        mode="concise",
        theme="modern-geometric",
        allocation_plan=plan,
    )

    included = set(content["coverage_report"]["included_fragment_ids"])
    excluded = set(content["coverage_report"]["excluded_fragment_ids"])
    assert included.isdisjoint(excluded)
    assert included | excluded == {item.fragment_id for item in fragments}
    assert content["coverage_report"]["decision_coverage_ratio"] == 1.0
    assert all(item["reason"] == "mode_concise" for item in content["exclusions"])


def test_process_content_uses_cumulative_reveal_pages_without_double_counting_coverage() -> None:
    course = source_course()
    course["nodes"][0]["content_blocks"].insert(1, {
        "block_id": "block-process",
        "title": "生成流程",
        "content": (
            "- 切分课程正文\n"
            "- 分配页面内容\n"
            "- 检查页面容量\n"
            "- 发布可用版本"
        ),
        "metadata": {"role": "reasoning"},
    })
    document = document_from_legacy_course(course)
    fragments = fragment_course_document(document)
    plan = deterministic_slide_allocation(
        document,
        fragments,
        mode="full",
        theme="qizhi-classroom",
    )
    sequence_pages = [page for page in plan.pages if page.sequence_id]

    assert len(sequence_pages) == 4
    assert [page.step_index for page in sequence_pages] == [1, 2, 3, 4]
    final_fragment_ids = sequence_pages[-1].fragment_ids
    assert [
        page.fragment_ids for page in sequence_pages
    ] == [
        final_fragment_ids[:1],
        final_fragment_ids[:2],
        final_fragment_ids[:3],
        final_fragment_ids[:4],
    ]

    content = compile_slide_deck_v3(
        document,
        course,
        mode="full",
        theme="qizhi-classroom",
        allocation_plan=plan,
    )

    assert content["coverage_report"]["visible_coverage_ratio"] == 1.0
    assert content["coverage_report"]["included_fragment_count"] == len(fragments)
    built_sequence = [
        slide for slide in content["slides"]
        if slide["quality"].get("sequence_id") == sequence_pages[0].sequence_id
    ]
    assert [slide["quality"]["step_index"] for slide in built_sequence] == [1, 2, 3, 4]


def test_inline_math_stays_in_prose_and_visible_text_contains_no_markup() -> None:
    course = source_course()
    course["nodes"][0]["content_blocks"][0].update({
        "title": "正文",
        "content": (
            "常见向量空间包括 $\\mathbb{R}^n$ 和矩阵空间。\n\n"
            "<!-- BODY_START -->\n"
            "**向量空间**需要满足封闭性。"
        ),
    })
    document = document_from_legacy_course(course)
    fragments = fragment_course_document(document)

    assert all(item.kind != "formula" for item in fragments if "常见向量空间" in item.text)

    plan = deterministic_slide_allocation(
        document,
        fragments,
        mode="full",
        theme="qizhi-classroom",
    )
    content = compile_slide_deck_v3(
        document,
        course,
        mode="full",
        theme="qizhi-classroom",
        allocation_plan=plan,
    )
    visible = "\n".join(
        value
        for slide in content["slides"]
        for block in slide["blocks"]
        for value in [block.get("content", ""), *(block.get("items") or [])]
    )

    assert "\\mathbb" not in visible
    assert "<!--" not in visible
    assert "**" not in visible
    assert "ℝⁿ" in visible


def test_placeholder_block_title_uses_semantic_section_title() -> None:
    course = source_course()
    course["nodes"][0]["content_blocks"][0]["title"] = "正文"
    document = document_from_legacy_course(course)
    fragments = fragment_course_document(document)
    plan = deterministic_slide_allocation(
        document,
        fragments,
        mode="full",
        theme="qizhi-classroom",
    )
    content = compile_slide_deck_v3(
        document,
        course,
        mode="full",
        theme="qizhi-classroom",
        allocation_plan=plan,
    )
    teaching_slides = [
        slide for slide in content["slides"]
        if slide.get("source_block_ids") == ["block-core"]
    ]

    assert teaching_slides
    assert all(slide["title"] != "正文" for slide in teaching_slides)
    assert teaching_slides[0]["title"] == "第一章 核心内容"


def test_deterministic_pages_respect_materialized_layout_capacity() -> None:
    course = source_course()
    course["nodes"][0]["content_blocks"][0]["content"] = "\n\n".join(
        f"第 {index} 个概念用于验证页面容量。"
        for index in range(1, 8)
    )
    document = document_from_legacy_course(course)
    fragments = fragment_course_document(document)
    plan = deterministic_slide_allocation(
        document,
        fragments,
        mode="full",
        theme="qizhi-classroom",
    )
    content = compile_slide_deck_v3(
        document,
        course,
        mode="full",
        theme="qizhi-classroom",
        allocation_plan=plan,
    )

    concept_slides = [
        slide for slide in content["slides"]
        if slide["layout"] == "concept"
    ]
    assert concept_slides
    assert all(len(slide["blocks"]) <= 3 for slide in concept_slides)
    assert not {
        issue["code"]
        for issue in content["quality_report"]["blockers"]
    } & {"slide_block_overflow", "concept_card_overflow"}


@pytest.mark.asyncio
async def test_ai_planner_cannot_inject_teaching_body_text() -> None:
    course = source_course()
    document = document_from_legacy_course(course)

    async def invalid_planner(_request):
        return {
            "schema_version": "slide_allocation_plan_v2",
            "title": document.title,
            "mode": "teaching",
            "theme": "qizhi-classroom",
            "variant_key": "teaching:qizhi-classroom",
            "source_document_revision": document.document_revision,
            "pages": [{
                "page_id": "slide:title",
                "layout": "cover",
                "fragment_ids": [],
                "appendix": False,
                "sequence_id": "",
                "step_index": 0,
                "derived_text": [],
                "body": "模型擅自生成的教学正文",
            }],
            "exclusions": [],
            "planner": "ai",
            "fallback_reason": "",
            "review": {},
        }

    plan = await plan_slide_deck_v3(
        document,
        course,
        mode="teaching",
        theme="qizhi-classroom",
        ai_planner=invalid_planner,
    )

    assert isinstance(plan, SlideAllocationPlanV2)
    assert plan.planner == "deterministic_fallback"
    assert plan.fallback_reason == "invalid_or_failed_ai_plan"


def test_mode_theme_variants_are_cached_independently_and_do_not_replace_core_specs() -> None:
    course = source_course()
    document = document_from_legacy_course(course)
    with TemporaryDirectory() as temp_dir:
        repository = TeachingRepresentationRepository(temp_dir)
        compile_core_representations(document, course, repository)
        before = repository.load(document.course_id)
        core_ids = {
            item.representation_type: item.representation_id
            for item in before.representations
        }
        for mode in ("full", "teaching", "concise"):
            for theme in SLIDE_DECK_THEMES:
                fragments = fragment_course_document(document)
                plan = deterministic_slide_allocation(
                    document,
                    fragments,
                    mode=mode,
                    theme=theme,
                )
                result = rebuild_slide_deck_variant_safely(
                    document,
                    course,
                    repository,
                    mode=mode,
                    theme=theme,
                    allocation_plan=plan,
                )
                assert result["status"] == "synchronized"

        registry = repository.load(document.course_id)
        variants = [
            item for item in registry.representations
            if item.representation_type == "slide_deck" and item.variant_key
        ]
        assert len(variants) == 15
        assert len({item.representation_id for item in variants}) == 15
        for representation_type, representation_id in core_ids.items():
            assert any(
                item.representation_type == representation_type
                and item.representation_id == representation_id
                for item in registry.representations
            )


def test_v3_export_is_editable_widescreen_and_uses_variant_theme(tmp_path: Path) -> None:
    course = source_course()
    document = document_from_legacy_course(course)
    repository = TeachingRepresentationRepository(tmp_path / "registry")
    plan = deterministic_slide_allocation(
        document,
        fragment_course_document(document),
        mode="teaching",
        theme="dark-tech",
    )
    result = rebuild_slide_deck_variant_safely(
        document,
        course,
        repository,
        mode="teaching",
        theme="dark-tech",
        allocation_plan=plan,
    )
    assert result["status"] == "synchronized"
    registry = repository.load(document.course_id)
    representation = next(
        item for item in registry.representations
        if item.variant_key == "teaching:dark-tech"
    )
    spec = next(item for item in registry.specs if item.spec_id == representation.spec_id)
    path = export_slide_deck_pptx(spec, tmp_path / "source-first.pptx")
    presentation = Presentation(path)

    assert presentation.slide_width / presentation.slide_height == pytest.approx(16 / 9, rel=0.01)
    assert len(presentation.slides) == len(spec.payload["content"]["slides"])
    assert any(
        shape.has_text_frame and shape.text.strip()
        for slide in presentation.slides
        for shape in slide.shapes
    )


def test_variant_stream_endpoint_builds_only_requested_combination(tmp_path: Path, monkeypatch) -> None:
    from routers import teaching_representations as representation_router

    course = source_course()
    document = document_from_legacy_course(course)
    canonical = {
        **course,
        "course_schema_version": COURSE_DOCUMENT_SCHEMA,
        "course_document": document.model_dump(mode="json"),
        "course_document_authoritative": True,
        "course_operation_log": [],
    }
    course_repository = CourseDocumentRepository(MemoryStorage(canonical))
    representation_repository = TeachingRepresentationRepository(tmp_path / "registry")
    monkeypatch.setattr(
        representation_router,
        "get_course_document_repository",
        lambda: course_repository,
    )
    monkeypatch.setattr(
        representation_router,
        "get_teaching_representation_repository",
        lambda: representation_repository,
    )
    monkeypatch.setattr(representation_router, "get_task_manager_optional", lambda: None)

    async def existing_course(_course_id: str):
        return course_repository.load_course_view(document.course_id)

    monkeypatch.setattr(representation_router, "get_course_or_404", existing_course)
    app = FastAPI()
    app.include_router(representation_router.router, prefix="/api")
    client = TestClient(app)

    with client.stream(
        "POST",
        f"/api/courses/{document.course_id}/teaching-representations/slide-decks/build/stream",
        headers={"X-User-Id": "teacher-1"},
        json={
            "mode": "teaching",
            "theme": "grid-notebook",
            "force_rebuild": False,
        },
    ) as response:
        stream = "".join(response.iter_text())

    assert response.status_code == 200
    assert "event: slide_upsert" in stream
    assert "event: build_complete" in stream
    registry = representation_repository.load(document.course_id)
    assert [
        (item.representation_type, item.variant_key)
        for item in registry.representations
    ] == [("slide_deck", "teaching:grid-notebook")]
