from __future__ import annotations

import pytest

from course_material_absorption import (
    compile_material_absorption_plan,
    material_absorption_bundle,
)
from material_models import DocumentBlock, DocumentLocator, ParsedDocument


def _document(asset_id: str, *texts: str, degraded: bool = False) -> ParsedDocument:
    return ParsedDocument(
        document_id=f"doc-{asset_id}",
        asset_id=f"material-{asset_id}",
        source_sha256=f"sha-{asset_id}",
        parse_status="degraded" if degraded else "parsed",
        parser_name="test",
        parser_version="1",
        parse_options_hash="test",
        blocks=[
            DocumentBlock(
                block_id=f"{asset_id}-block-{index}",
                kind="heading" if index == 1 else "paragraph",
                text=text,
                order=index - 1,
                locator=DocumentLocator(page=index, slide=index if asset_id == "ppt" else None),
            )
            for index, text in enumerate(texts, start=1)
        ],
        quality={"block_count": len(texts)},
        warnings=["需复核"] if degraded else [],
        created_at="2026-08-30T00:00:00Z",
    )


def _course() -> dict:
    return {
        "course_id": "course-1",
        "nodes": [
            {"node_id": "lesson-1", "parent_node_id": "root", "node_level": 1, "node_name": "第一讲"},
            {"node_id": "section-1", "parent_node_id": "lesson-1", "node_level": 2, "node_name": "核心问题"},
        ],
    }


def _package() -> dict:
    return {
        "package_id": "package-1",
        "course_id": "course-1",
        "assets": [
            {
                "asset_id": "outline",
                "filename": "课程大纲.docx",
                "relative_path": "课程大纲.docx",
                "document_type": "outline",
                "version_role": "current",
            },
            {
                "asset_id": "plan",
                "filename": "第一讲教案.docx",
                "relative_path": "第一讲教案.docx",
                "document_type": "lesson_plan",
                "version_role": "current",
                "structure_matches": [{"node_id": "section-1", "confidence": .96}],
            },
            {
                "asset_id": "script",
                "filename": "第一讲讲稿.pdf",
                "relative_path": "第一讲讲稿.pdf",
                "document_type": "script",
                "version_role": "current",
                "structure_matches": [{"node_id": "lesson-1", "confidence": .94}],
            },
            {
                "asset_id": "ppt",
                "filename": "第一讲课件.pptx",
                "relative_path": "第一讲课件.pptx",
                "document_type": "ppt",
                "version_role": "current",
                "structure_matches": [{"node_id": "lesson-1", "confidence": .92}],
            },
        ],
    }


def test_compiler_builds_subject_agnostic_linked_working_drafts() -> None:
    package = _package()
    documents = {
        "outline": _document("outline", "课程目标", "知识结构"),
        "plan": _document("plan", "教学目标", "教学流程"),
        "script": _document("script", "导入", "核心讲解"),
        "ppt": _document("ppt", "封面", "核心概念", degraded=True),
    }

    plan = compile_material_absorption_plan(
        package=package,
        documents=documents,
        course=_course(),
    )

    assert plan["status"] == "ready"
    assert {item["target_id"] for item in plan["targets"]} == {
        "managed:outline",
        "lesson-plan:lesson-1",
        "script:lesson-1",
        "ppt-v6:lesson-1",
    }
    ppt = next(item for item in plan["targets"] if item["target_type"] == "ppt")
    assert ppt["review_items"][0]["code"] == "source_parse_review_required"
    assert ppt["structured_draft"]["sections"][0]["source_asset_id"] == "ppt"
    assert ppt["structured_draft"]["sections"][0]["blocks"][0]["source"]["locator"]["slide"] == 1
    assert plan["scope_options"] == [{"scope_id": "lesson-1", "label": "第一讲"}]

    bundle = material_absorption_bundle(plan)
    assert bundle["status"] == "working_drafts_created"
    assert len(bundle["targets"]) == 4


def test_multiple_current_versions_require_teacher_primary_choice() -> None:
    package = _package()
    second = {
        **package["assets"][1],
        "asset_id": "plan-new",
        "filename": "第一讲教案-修订.docx",
    }
    package["assets"].append(second)
    documents = {
        item["asset_id"]: _document(item["asset_id"], item["filename"])
        for item in package["assets"]
    }

    unresolved = compile_material_absorption_plan(
        package=package,
        documents=documents,
        course=_course(),
    )

    assert unresolved["status"] == "needs_decision"
    assert any(item["code"] == "multiple_current_sources" for item in unresolved["unresolved_items"])
    with pytest.raises(ValueError, match="material_absorption_plan_unresolved"):
        material_absorption_bundle(unresolved)

    second["absorption_decision"] = {"role": "primary"}
    resolved = compile_material_absorption_plan(
        package=package,
        documents=documents,
        course=_course(),
    )
    lesson_plan = next(item for item in resolved["targets"] if item["target_type"] == "lesson_plan")
    assert resolved["status"] == "ready"
    assert next(item for item in lesson_plan["sources"] if item["asset_id"] == "plan-new")["role"] == "primary"
    assert len(lesson_plan["structured_draft"]["source_documents"]) == 2


def test_lesson_material_without_scope_stays_unresolved_instead_of_guessing() -> None:
    package = _package()
    package["assets"] = [{
        "asset_id": "notes",
        "filename": "课程讲义.docx",
        "relative_path": "课程讲义.docx",
        "document_type": "script",
        "version_role": "unknown",
    }]

    plan = compile_material_absorption_plan(
        package=package,
        documents={"notes": _document("notes", "讲解内容")},
        course=_course(),
    )

    assert plan["targets"] == []
    assert plan["unresolved_items"][0]["code"] == "target_scope_unresolved"
