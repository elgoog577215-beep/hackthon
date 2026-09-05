"""Generate a real-course golden chapter with the production slide compiler.

The script intentionally uses the same allocation, storyboard, visual planning,
asset repository, quality gate, and PPTX renderer as the application.  It only
filters appendix slides from the review copy so humans can inspect the teaching
mainline without paging through the source archive.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from course_document import (  # noqa: E402
    CourseDocument,
    CourseSection,
    refresh_document_revision,
)
from slide_asset_repository import SlideAssetRepository  # noqa: E402
from slide_deck_renderer import export_structured_slide_deck  # noqa: E402
from slide_deck_v3 import fragment_course_document  # noqa: E402
from slide_deck_v4 import allocation_from_story_plan_v2  # noqa: E402
from slide_deck_v5 import compile_slide_deck_v5  # noqa: E402
from slide_story_plan import compile_slide_story_plan_v2  # noqa: E402
from slide_visuals import deterministic_visual_plan  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--course", type=Path, required=True)
    parser.add_argument("--chapter", default="1")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--theme", default="qizhi-classroom")
    parser.add_argument(
        "--no-images",
        action="store_true",
        help="Exercise the production deterministic-visual fallback without network images.",
    )
    args = parser.parse_args()
    load_dotenv(ROOT / ".env", override=False)
    if args.no_images:
        for name in (
            "SLIDE_IMAGE_API_BASE",
            "SLIDE_IMAGE_API_KEY",
            "SLIDE_IMAGE_MODEL",
            "AI_API_BASE",
            "AI_API_KEY",
        ):
            os.environ[name] = ""

    course_path = args.course.resolve()
    output_path = args.output.resolve()
    course = json.loads(course_path.read_text(encoding="utf-8"))
    document = CourseDocument.model_validate(course["course_document"])
    chapter = _select_chapter(document, str(args.chapter))
    chapter_document = _chapter_document(document, chapter)
    fragments = fragment_course_document(chapter_document)
    chapter_course = {
        **course,
        "course_name": chapter_document.title,
        "course_id": chapter_document.course_id,
        "course_document": chapter_document.model_dump(mode="json"),
        "course_document_revision": chapter_document.document_revision,
        "course_document_authoritative": True,
    }
    story_plan = compile_slide_story_plan_v2(
        chapter_document,
        chapter_course,
        fragments,
        mode="teaching",
        theme=args.theme,
    )
    allocation, _page_beats = allocation_from_story_plan_v2(
        chapter_document,
        fragments,
        story_plan,
    )
    visual_plan = deterministic_visual_plan(
        chapter_document,
        allocation,
        fragments,
    )

    asset_root = output_path.parent / ".golden-slide-assets"
    repository = SlideAssetRepository(asset_root)
    content = compile_slide_deck_v5(
        chapter_document,
        chapter_course,
        story_plan=story_plan,
        allocation_plan=allocation,
        visual_plan=visual_plan,
        asset_repository=repository,
    )
    if not content["quality_report"]["passed"]:
        print(json.dumps(content["quality_report"], ensure_ascii=False, indent=2))
        return 2

    review_content = _mainline_review_copy(content)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    export_structured_slide_deck(
        review_content,
        output_path,
        theme=args.theme,
        asset_repository=repository,
    )
    audit_path = output_path.with_suffix(".audit.json")
    audit_path.write_text(
        json.dumps(
            {
                "course_id": chapter_document.course_id,
                "chapter_id": chapter.section_id,
                "chapter_title": chapter.title,
                "compiler_version": content["build_signature"]["compiler_version"],
                "story_engine_version": content["build_signature"]["story_engine_version"],
                "layout_registry_version": content["build_signature"]["layout_registry_version"],
                "teaching_plan_revision": content["build_signature"]["teaching_plan_revision"],
                "source_fragment_count": len(fragments),
                "full_build_slide_count": len(content["slides"]),
                "review_slide_count": len(review_content["slides"]),
                "visual_quality_report": content["visual_quality_report"],
                "pedagogical_quality_report": content["pedagogical_quality_report"],
                "presentation_quality_report": content["presentation_quality_report"],
                "render_review": content["render_review"],
                "coverage_report": content["coverage_report"],
                "illustration_asset_count": len(content["visual_asset_manifest"]),
                "review_scope": "teaching_mainline_only",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(output_path)
    print(audit_path)
    return 0


def _select_chapter(document: CourseDocument, selector: str) -> CourseSection:
    chapters = [
        section
        for section in sorted(document.sections, key=lambda item: item.position)
        if section.level == 1
    ]
    for index, chapter in enumerate(chapters, start=1):
        if selector in {str(index), chapter.section_id, chapter.title}:
            return chapter
    raise ValueError(f"Unknown chapter selector: {selector}")


def _chapter_document(
    document: CourseDocument,
    chapter: CourseSection,
) -> CourseDocument:
    section_ids = {chapter.section_id}
    while True:
        before = len(section_ids)
        section_ids.update(
            section.section_id
            for section in document.sections
            if section.parent_section_id in section_ids
        )
        if len(section_ids) == before:
            break
    return refresh_document_revision(document.model_copy(update={
        "title": f"{document.title}｜{chapter.title}·黄金样板",
        "sections": [
            section
            for section in document.sections
            if section.section_id in section_ids
        ],
        "blocks": [
            block
            for block in document.blocks
            if block.section_id in section_ids
        ],
    }))


def _mainline_review_copy(content: dict[str, Any]) -> dict[str, Any]:
    review = deepcopy(content)
    review["slides"] = [
        slide
        for slide in review["slides"]
        if (
            str(slide.get("slide_purpose") or "") != "appendix"
            and not bool((slide.get("quality") or {}).get("appendix"))
        )
    ]
    for index, slide in enumerate(review["slides"]):
        slide["position"] = index
    review["title"] = f"{review['title']}｜授课主线"
    return review


if __name__ == "__main__":
    raise SystemExit(main())
