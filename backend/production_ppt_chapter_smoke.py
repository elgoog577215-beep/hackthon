"""Read-only production smoke for one source-backed V5 chapter deck.

The smoke deliberately uses the deployed compiler, provider configuration, and
published course data.  It never persists a representation or modifies course
content; the only writes are diagnostic artifacts under the requested output
directory.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import traceback
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from course_document import (
    CourseDocument,
    course_view_from_document,
    refresh_document_revision,
)

PROGRAMMING_MODES = frozenset({
    "programming_engineering",
    "engineering_programming",
})
CODE_BLOCK_KINDS = frozenset({"code", "code_lab"})
SOURCE_LOOP_ROLES = frozenset({
    "concept",
    "reasoning",
    "example",
    "application",
    "activity",
    "checkpoint",
    "feedback",
    "misconception",
    "summary",
    "transfer",
})


class SmokeFailure(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}


@dataclass(frozen=True)
class ChapterCandidate:
    chapter_id: str
    section_ids: tuple[str, ...]
    source_role_count: int
    code_character_count: int
    source_block_count: int

    @property
    def rank(self) -> tuple[int, int, int, int]:
        return (
            self.source_role_count,
            min(self.code_character_count, 6000),
            len(self.section_ids),
            -self.source_block_count,
        )


@dataclass
class SelectedProductionChapter:
    course_id: str
    chapter: ChapterCandidate
    document: CourseDocument
    course_view: dict[str, Any]
    source_digest: str
    baseline_story: Any
    fragments: list[Any] = field(default_factory=list)
    rejected_candidate_codes: list[str] = field(default_factory=list)


def _chapter_root_id(
    section_id: str,
    parent_by_id: dict[str, str | None],
) -> str:
    current = section_id
    seen: set[str] = set()
    while current not in seen:
        seen.add(current)
        parent = parent_by_id.get(current)
        if not parent or parent not in parent_by_id:
            return current
        current = parent
    raise SmokeFailure(
        "production_course_section_cycle",
        "The selected production course contains a cyclic section hierarchy.",
    )


def _code_lines_from_markdown(markdown: str) -> list[str]:
    fenced = re.findall(r"```[^\n]*\n(.*?)```", markdown, flags=re.DOTALL)
    sources = fenced or [markdown]
    return [
        line.rstrip()
        for source in sources
        for line in source.splitlines()
        if line.strip() and not line.strip().startswith("```")
    ]


def extract_source_code_lines(document: CourseDocument) -> list[str]:
    lines: list[str] = []
    for block in sorted(document.blocks, key=lambda item: item.position):
        markdown = str(
            block.payload.get("markdown")
            or block.payload.get("text")
            or block.payload.get("content")
            or ""
        )
        if block.kind not in CODE_BLOCK_KINDS and "```" not in markdown:
            continue
        lines.extend(_code_lines_from_markdown(markdown))
    return lines


def rank_programming_chapter_candidates(
    document: CourseDocument,
    *,
    requested_chapter_id: str = "",
) -> list[ChapterCandidate]:
    parent_by_id = {
        section.section_id: section.parent_section_id
        for section in document.sections
    }
    root_by_section = {
        section_id: _chapter_root_id(section_id, parent_by_id)
        for section_id in parent_by_id
    }
    root_ids = {
        root_by_section[section_id]
        for section_id in parent_by_id
    }
    if requested_chapter_id and requested_chapter_id not in root_ids:
        raise SmokeFailure(
            "production_chapter_not_found",
            "The requested production chapter is not a chapter root.",
        )

    candidates: list[ChapterCandidate] = []
    roots = [requested_chapter_id] if requested_chapter_id else sorted(root_ids)
    for root_id in roots:
        section_ids = tuple(
            section.section_id
            for section in sorted(document.sections, key=lambda item: item.position)
            if root_by_section.get(section.section_id) == root_id
        )
        section_id_set = set(section_ids)
        blocks = [
            block
            for block in document.blocks
            if block.section_id in section_id_set and block.status != "retired"
        ]
        chapter_document = document.model_copy(
            deep=True,
            update={
                "sections": [
                    section
                    for section in document.sections
                    if section.section_id in section_id_set
                ],
                "blocks": blocks,
            },
        )
        code_lines = extract_source_code_lines(chapter_document)
        if not code_lines:
            continue
        roles = {
            str(block.role)
            for block in blocks
            if str(block.role) in SOURCE_LOOP_ROLES
        }
        candidates.append(ChapterCandidate(
            chapter_id=root_id,
            section_ids=section_ids,
            source_role_count=len(roles),
            code_character_count=sum(len(line) for line in code_lines),
            source_block_count=len(blocks),
        ))

    if not candidates:
        if requested_chapter_id:
            raise SmokeFailure(
                "production_chapter_has_no_code_source",
                "The requested production chapter has no source-backed code artifact.",
            )
        raise SmokeFailure(
            "production_programming_chapter_not_found",
            "No production programming chapter with source-backed code was found.",
        )
    return sorted(candidates, key=lambda item: item.rank, reverse=True)


def build_chapter_document(
    document: CourseDocument,
    chapter_id: str,
) -> CourseDocument:
    parent_by_id = {
        section.section_id: section.parent_section_id
        for section in document.sections
    }
    section_ids = {
        section_id
        for section_id in parent_by_id
        if _chapter_root_id(section_id, parent_by_id) == chapter_id
    }
    if chapter_id not in section_ids:
        raise SmokeFailure(
            "production_chapter_not_found",
            "The requested production chapter is not present in the course document.",
        )
    chapter_document = CourseDocument.model_validate({
        **document.model_dump(mode="json"),
        "document_revision": "",
        "sections": [
            section.model_dump(mode="json")
            for section in sorted(document.sections, key=lambda item: item.position)
            if section.section_id in section_ids
        ],
        "blocks": [
            block.model_dump(mode="json")
            for block in sorted(
                document.blocks,
                key=lambda item: (item.section_id, item.position),
            )
            if block.section_id in section_ids and block.status != "retired"
        ],
    })
    return refresh_document_revision(chapter_document)


def _stable_digest(value: Any) -> str:
    serialized = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _private_id(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _release_commit(application_root: Path) -> str:
    release_file = application_root / ".release-commit"
    if not release_file.is_file():
        raise SmokeFailure(
            "production_release_identity_missing",
            "The active production release does not expose .release-commit.",
        )
    return release_file.read_text(encoding="utf-8").strip()


def _issue_summary(items: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "severity": str(item.get("severity") or ""),
            "code": str(item.get("code") or "unknown"),
            **(
                {"page": int(item["page"])}
                if isinstance(item, dict) and isinstance(item.get("page"), int)
                else {}
            ),
        }
        for item in items
        if isinstance(item, dict)
    ]


def _source_scene_requirements(document: CourseDocument) -> set[str]:
    roles = {str(block.role) for block in document.blocks}
    requirements: set[str] = set()
    if "concept" in roles:
        requirements.add("concept")
    if "reasoning" in roles:
        requirements.add("reasoning")
    if "example" in roles:
        requirements.add("worked_example")
    if roles & {"activity", "checkpoint", "feedback"}:
        requirements.add("practice_feedback")
    if roles & {"application", "transfer"}:
        requirements.add("application")
    if "misconception" in roles:
        requirements.add("misconception")
    return requirements


def _visible_code_text(slides: list[dict[str, Any]]) -> str:
    values: list[str] = []
    for slide in slides:
        artifact_kinds = {
            str(item)
            for item in (slide.get("quality") or {}).get(
                "subject_artifact_kinds",
                [],
            )
        }
        for block in slide.get("blocks") or []:
            if str(block.get("type") or "") != "code" and "code" not in artifact_kinds:
                continue
            values.extend([
                str(block.get("content") or ""),
                *[str(item) for item in block.get("items") or []],
            ])
    return "\n".join(values)


def _pptx_text(path: Path) -> str:
    from pptx import Presentation

    presentation = Presentation(path)
    return "\n".join(
        str(shape.text or "")
        for slide in presentation.slides
        for shape in slide.shapes
        if getattr(shape, "has_text_frame", False)
    )


def _render_artifacts(pptx_path: Path, output_dir: Path) -> dict[str, Any]:
    from PIL import Image, ImageDraw

    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    pdftoppm = shutil.which("pdftoppm")
    missing = [
        name
        for name, executable in (
            ("libreoffice", soffice),
            ("pdftoppm", pdftoppm),
        )
        if not executable
    ]
    if missing:
        raise SmokeFailure(
            "production_render_tools_missing",
            "Production render QA tools are unavailable.",
            details={"missing": missing},
        )
    render_dir = output_dir / "rendered"
    render_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            str(soffice),
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(output_dir),
            str(pptx_path),
        ],
        check=True,
        capture_output=True,
        timeout=120,
    )
    pdf_path = output_dir / f"{pptx_path.stem}.pdf"
    if not pdf_path.is_file():
        raise SmokeFailure(
            "production_pdf_render_missing",
            "LibreOffice did not produce the expected PDF artifact.",
        )
    subprocess.run(
        [
            str(pdftoppm),
            "-png",
            "-r",
            "120",
            str(pdf_path),
            str(render_dir / "page"),
        ],
        check=True,
        capture_output=True,
        timeout=120,
    )
    images = sorted(
        render_dir.glob("page-*.png"),
        key=lambda item: int(item.stem.rsplit("-", 1)[-1]),
    )
    if not images:
        raise SmokeFailure(
            "production_slide_images_missing",
            "The deployed export could not be rasterized into slide images.",
        )

    columns = 3
    thumb_width = 480
    margin = 24
    thumbs: list[Image.Image] = []
    for image_path in images:
        with Image.open(image_path) as source:
            thumb = source.convert("RGB")
            thumb.thumbnail((thumb_width, round(thumb_width * 9 / 16)))
            thumbs.append(thumb.copy())
    cell_height = max(image.height for image in thumbs) + 42
    rows = (len(thumbs) + columns - 1) // columns
    sheet = Image.new(
        "RGB",
        (
            columns * thumb_width + (columns + 1) * margin,
            rows * cell_height + (rows + 1) * margin,
        ),
        "white",
    )
    draw = ImageDraw.Draw(sheet)
    for index, thumb in enumerate(thumbs):
        row, column = divmod(index, columns)
        x = margin + column * (thumb_width + margin)
        y = margin + row * (cell_height + margin)
        sheet.paste(thumb, (x, y))
        draw.text((x, y + thumb.height + 8), str(index + 1), fill="black")
    contact_sheet = output_dir / "contact-sheet.png"
    sheet.save(contact_sheet)
    return {
        "pdf_bytes": pdf_path.stat().st_size,
        "rendered_page_count": len(images),
        "contact_sheet_bytes": contact_sheet.stat().st_size,
    }


def _select_production_chapter(
    *,
    requested_course_id: str,
    requested_chapter_id: str,
) -> SelectedProductionChapter:
    from course_repository import CourseDocumentRepository
    from slide_deck_v3 import fragment_course_document
    from slide_deck_v5 import compact_story_plan_v5
    from slide_semantics import (
        compile_ppt_semantic_units,
        compile_subject_presentation_contract_v1,
    )
    from slide_story_plan import (
        compile_slide_story_plan_v2,
        resolve_slide_deck_schema,
    )
    from storage import storage

    repository = CourseDocumentRepository(storage)
    summaries = {
        str(item.get("course_id") or ""): item
        for item in storage.list_courses()
        if item.get("course_id")
    }
    if requested_course_id:
        course_ids = [requested_course_id]
    else:
        course_ids = sorted(summaries)
    if not course_ids:
        raise SmokeFailure(
            "production_course_catalog_empty",
            "Production has no courses available for a chapter smoke.",
        )

    accepted: list[SelectedProductionChapter] = []
    rejected_codes: list[str] = []
    for course_id in course_ids:
        try:
            summary = summaries.get(course_id) or {}
            if not summary or not bool(summary.get("is_published")):
                raise SmokeFailure(
                    "production_course_not_published",
                    "The production course is not published.",
                )
            raw_before = repository.load_raw(course_id)
            document, canonical = repository.load_document(course_id)
            if not canonical:
                raise SmokeFailure(
                    "production_course_not_canonical",
                    "The production course is not on the canonical course-document chain.",
                )
            course_view = repository.load_course_view(course_id)
            primary_mode = str(
                (course_view.get("subject_pedagogy_profile") or {}).get(
                    "primary_mode",
                )
                or ""
            )
            if primary_mode not in PROGRAMMING_MODES:
                raise SmokeFailure(
                    "production_course_not_programming",
                    "The production course is not classified as programming engineering.",
                )
            if resolve_slide_deck_schema(
                course_view,
                story_engine_enabled=True,
                v5_enabled=True,
            ) != "slide_deck_v5":
                raise SmokeFailure(
                    "production_course_not_v5_eligible",
                    "The production course did not resolve to the V5 chain.",
                )
            candidates = rank_programming_chapter_candidates(
                document,
                requested_chapter_id=requested_chapter_id,
            )
            for candidate in candidates:
                chapter_document = build_chapter_document(
                    document,
                    candidate.chapter_id,
                )
                chapter_view = course_view_from_document(
                    course_view,
                    chapter_document,
                )
                if resolve_slide_deck_schema(
                    chapter_view,
                    story_engine_enabled=True,
                    v5_enabled=True,
                ) != "slide_deck_v5":
                    raise SmokeFailure(
                        "production_chapter_not_v5_eligible",
                        "The selected production chapter did not resolve to V5.",
                    )
                fragments = fragment_course_document(chapter_document)
                semantic_units = compile_ppt_semantic_units(
                    chapter_document,
                    fragments,
                )
                subject_contract = compile_subject_presentation_contract_v1(
                    chapter_document,
                    chapter_view,
                    semantic_units,
                    fragments,
                )
                if "code" not in subject_contract.required_representation_kinds:
                    raise SmokeFailure(
                        "production_programming_contract_missing_code",
                        "The programming chapter did not compile a required code contract.",
                    )
                baseline = compact_story_plan_v5(
                    chapter_document,
                    compile_slide_story_plan_v2(
                        chapter_document,
                        chapter_view,
                        fragments,
                        mode="teaching",
                        theme="qizhi-classroom",
                    ),
                    fragments,
                )
                accepted.append(SelectedProductionChapter(
                    course_id=course_id,
                    chapter=candidate,
                    document=chapter_document,
                    course_view=chapter_view,
                    source_digest=_stable_digest(raw_before),
                    baseline_story=baseline,
                    fragments=fragments,
                ))
        except SmokeFailure as exc:
            rejected_codes.append(exc.code)
            if requested_course_id:
                raise
        except Exception as exc:
            rejected_codes.append(type(exc).__name__)
            if requested_course_id:
                raise SmokeFailure(
                    "production_course_selection_failed",
                    "The requested production course could not compile a V5 chapter baseline.",
                    details={"exception_type": type(exc).__name__},
                ) from exc

    if not accepted:
        raise SmokeFailure(
            "production_programming_sample_unavailable",
            "No published canonical programming chapter passed V5 prerequisites.",
            details={
                "rejection_counts": dict(Counter(rejected_codes)),
                "course_count": len(course_ids),
            },
        )
    selected = max(accepted, key=lambda item: item.chapter.rank)
    selected.rejected_candidate_codes = rejected_codes
    return selected


async def run_production_smoke(
    *,
    application_root: Path,
    output_dir: Path,
    expected_release_commit: str,
    requested_course_id: str = "",
    requested_chapter_id: str = "",
) -> dict[str, Any]:
    from course_repository import CourseDocumentRepository
    from slide_deck_renderer import audit_exported_pptx, export_structured_slide_deck
    from slide_deck_v5 import (
        allocation_from_story_plan_v5,
        compile_slide_deck_v5,
    )
    from slide_story_plan import plan_slide_story_v2
    from slide_visuals import plan_slide_visuals
    from storage import storage
    from task_manager import (
        _source_first_slide_visual_ai_worker,
        _source_first_story_ai_worker,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    release_commit = _release_commit(application_root)
    if expected_release_commit and release_commit != expected_release_commit:
        raise SmokeFailure(
            "production_release_commit_mismatch",
            "The active production release is not the workflow commit under test.",
            details={
                "expected": expected_release_commit,
                "actual": release_commit,
            },
        )

    selected = _select_production_chapter(
        requested_course_id=requested_course_id,
        requested_chapter_id=requested_chapter_id,
    )
    os.environ["SLIDE_WEB_IMAGE_RETRIEVAL_ENABLED"] = "false"
    os.environ["SLIDE_GENERATED_ILLUSTRATIONS_ENABLED"] = "false"
    os.environ["SLIDE_LIBREOFFICE_AUDIT_ENABLED"] = "true"

    story_worker = _source_first_story_ai_worker()
    visual_worker = _source_first_slide_visual_ai_worker()
    story = await plan_slide_story_v2(
        selected.document,
        selected.course_view,
        selected.fragments,
        mode="teaching",
        theme="qizhi-classroom",
        baseline=selected.baseline_story,
        ai_planner=story_worker,
    )
    allocation, _ = allocation_from_story_plan_v5(
        selected.document,
        selected.fragments,
        story,
    )
    visual_plan = await plan_slide_visuals(
        selected.document,
        allocation,
        selected.fragments,
        ai_planner=visual_worker,
    )
    content = compile_slide_deck_v5(
        selected.document,
        selected.course_view,
        story_plan=story,
        allocation_plan=allocation,
        visual_plan=visual_plan,
    )
    slides = list(content.get("slides") or [])
    quality = dict(content.get("quality_report") or {})
    issue_codes = {
        str(item.get("code") or "")
        for item in quality.get("issues") or []
        if isinstance(item, dict)
    }
    required_subject_kinds = set(
        (
            story.planning_diagnostics.get("subject_presentation_contract")
            or {}
        ).get("required_representation_kinds")
        or []
    )
    code_slides = [
        slide
        for slide in slides
        if "code" in {
            str(item)
            for item in (slide.get("quality") or {}).get(
                "subject_artifact_kinds",
                [],
            )
        }
        or any(
            str(block.get("type") or "") == "code"
            for block in slide.get("blocks") or []
        )
    ]
    artifact_editorial_fallbacks = [
        str(slide.get("unit_id") or "")
        for slide in code_slides
        if str((slide.get("quality") or {}).get("resolved_layout") or "")
        == "editorial-body"
    ]
    normalized_titles = [
        " ".join(str(slide.get("title") or "").lower().split())
        for slide in slides
        if str(slide.get("title") or "").strip()
    ]
    duplicate_titles = sorted(
        title
        for title, count in Counter(normalized_titles).items()
        if count > 1
    )
    source_code_lines = extract_source_code_lines(selected.document)
    source_code_anchors = [
        source_code_lines[0] if source_code_lines else "",
        source_code_lines[-1] if source_code_lines else "",
    ]
    visible_code = _visible_code_text(slides)
    scene_kinds = {
        str(slide.get("scene_kind") or "")
        for slide in slides
        if str(slide.get("scene_kind") or "")
    }
    required_scenes = _source_scene_requirements(selected.document)
    gates: dict[str, bool] = {
        "release_commit_matches": (
            not expected_release_commit
            or release_commit == expected_release_commit
        ),
        "v5_schema": content.get("schema_version") == "slide_deck_v5",
        "v5_candidate_status": content.get("candidate_status") in {
            "v5_ready",
            "v5_needs_manual_edit",
        },
        "quality_gate": bool(quality.get("passed")),
        "subject_contract_requires_code": "code" in required_subject_kinds,
        "code_page_count": 1 <= len(code_slides) <= 3,
        "code_not_editorial_fallback": not artifact_editorial_fallbacks,
        "code_source_anchors_preserved": all(
            anchor and anchor in visible_code
            for anchor in source_code_anchors
        ),
        "section_flow_preserved": (
            {"chapter_entry", "chapter_recap"} <= scene_kinds
            and required_scenes <= scene_kinds
        ),
        "titles_unique": not duplicate_titles,
        "no_sparse_page_blocker": "sparse_non_exempt_page" not in issue_codes,
        "no_density_overflow": not bool(
            issue_codes
            & {
                "body_density_overflow",
                "visible_item_overflow",
                "slide_title_overflow",
            }
        ),
    }

    report: dict[str, Any] = {
        "schema_version": "production_ppt_chapter_smoke_v1",
        "status": "running",
        "release_commit": release_commit,
        "source": {
            "course_id_hash": _private_id(selected.course_id),
            "chapter_id_hash": _private_id(selected.chapter.chapter_id),
            "primary_mode": str(
                (selected.course_view.get("subject_pedagogy_profile") or {}).get(
                    "primary_mode",
                )
                or ""
            ),
            "section_count": len(selected.document.sections),
            "block_count": len(selected.document.blocks),
            "source_role_count": selected.chapter.source_role_count,
            "source_code_line_count": len(source_code_lines),
            "source_code_character_count": selected.chapter.code_character_count,
            "read_only_digest": selected.source_digest,
        },
        "chain": {
            "schema": content.get("schema_version"),
            "candidate_status": content.get("candidate_status"),
            "story_planner_available": story_worker is not None,
            "story_planner": story.planner,
            "story_fallback_reason": story.fallback_reason,
            "visual_planner_available": visual_worker is not None,
            "visual_planner": str(
                (visual_plan.deck_brief or {}).get("planner") or ""
            ),
            "visual_fallback_reason": str(
                (visual_plan.deck_brief or {}).get("fallback_reason") or ""
            ),
        },
        "deck": {
            "slide_count": len(slides),
            "code_page_count": len(code_slides),
            "resolved_layout_counts": dict(Counter(
                str((slide.get("quality") or {}).get("resolved_layout") or "")
                for slide in slides
            )),
            "scene_counts": dict(Counter(
                str(slide.get("scene_kind") or "")
                for slide in slides
            )),
            "required_source_scenes": sorted(required_scenes),
            "duplicate_title_count": len(duplicate_titles),
            "artifact_editorial_fallback_count": len(
                artifact_editorial_fallbacks
            ),
        },
        "quality": {
            "passed": bool(quality.get("passed")),
            "score": int(quality.get("score") or 0),
            "blockers": _issue_summary(list(quality.get("blockers") or [])),
            "warnings": _issue_summary(list(quality.get("warnings") or [])),
        },
        "gates": gates,
    }
    failed_before_export = [name for name, passed in gates.items() if not passed]
    if failed_before_export:
        report["status"] = "failed"
        report["failure"] = {
            "code": "production_v5_semantic_gate_failed",
            "failed_gates": failed_before_export,
        }
        return report

    pptx_path = output_dir / "chapter-smoke.pptx"
    export_structured_slide_deck(
        content,
        pptx_path,
        require_quality=True,
        theme=str(content.get("theme") or "qizhi-classroom"),
        course_data=selected.course_view,
    )
    export_audit = audit_exported_pptx(
        pptx_path,
        expected_slide_count=len(slides),
    )
    pptx_text = _pptx_text(pptx_path)
    export_anchors_preserved = all(
        anchor and anchor in pptx_text
        for anchor in source_code_anchors
    )
    render_artifacts = _render_artifacts(pptx_path, output_dir)

    repository = CourseDocumentRepository(storage)
    source_after = _stable_digest(repository.load_raw(selected.course_id))
    export_gates = {
        "pptx_created": pptx_path.is_file() and pptx_path.stat().st_size > 0,
        "pptx_audit": bool(export_audit.get("passed")),
        "pptx_code_anchors_preserved": export_anchors_preserved,
        "rendered_page_count_matches": (
            int(render_artifacts["rendered_page_count"]) == len(slides)
        ),
        "production_course_unchanged": source_after == selected.source_digest,
    }
    report["gates"].update(export_gates)
    report["export"] = {
        "pptx_bytes": pptx_path.stat().st_size,
        "audit_schema": export_audit.get("schema_version"),
        "audit_reviewer": export_audit.get("reviewer"),
        "passed": bool(export_audit.get("passed")),
        "issues": _issue_summary(list(export_audit.get("issues") or [])),
        **render_artifacts,
    }
    failed = [
        name
        for name, passed in report["gates"].items()
        if not passed
    ]
    if failed:
        report["status"] = "failed"
        report["failure"] = {
            "code": "production_v5_export_gate_failed",
            "failed_gates": failed,
        }
        return report
    report["status"] = (
        "passed_with_manual_edit"
        if content.get("candidate_status") == "v5_needs_manual_edit"
        else "passed"
    )
    return report


def _write_report(output_dir: Path, report: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--application-root", default="")
    parser.add_argument("--expected-release-commit", default="")
    parser.add_argument("--course-id", default="")
    parser.add_argument("--chapter-id", default="")
    args = parser.parse_args(argv)

    output_dir = Path(args.output_dir).resolve()
    application_root = (
        Path(args.application_root).resolve()
        if args.application_root
        else Path(__file__).resolve().parent.parent
    )
    try:
        report = asyncio.run(run_production_smoke(
            application_root=application_root,
            output_dir=output_dir,
            expected_release_commit=str(args.expected_release_commit or ""),
            requested_course_id=str(args.course_id or ""),
            requested_chapter_id=str(args.chapter_id or ""),
        ))
    except SmokeFailure as exc:
        report = {
            "schema_version": "production_ppt_chapter_smoke_v1",
            "status": "failed",
            "failure": {
                "code": exc.code,
                "message": str(exc),
                "details": deepcopy(exc.details),
            },
        }
    except Exception as exc:
        trace = [
            {
                "file": Path(frame.filename).name,
                "line": frame.lineno,
                "function": frame.name,
            }
            for frame in traceback.extract_tb(exc.__traceback__)[-8:]
        ]
        report = {
            "schema_version": "production_ppt_chapter_smoke_v1",
            "status": "failed",
            "failure": {
                "code": "production_ppt_chapter_smoke_unhandled",
                "message": "The production chapter smoke raised an unhandled error.",
                "exception_type": type(exc).__name__,
                "details": {
                    "error": str(exc)[:500],
                    "trace": trace,
                },
            },
        }
    _write_report(output_dir, report)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if str(report.get("status") or "").startswith("passed") else 1


if __name__ == "__main__":
    sys.exit(main())
