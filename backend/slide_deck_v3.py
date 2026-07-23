"""Course-source-first slide deck planning and compilation.

The v3 contract treats course text as immutable input.  A planner may only
allocate fragment identifiers to pages; visible teaching copy is materialized
from the fragment catalog after the plan has passed deterministic validation.
"""

from __future__ import annotations

import asyncio
import inspect
import re
from collections.abc import Awaitable, Callable
from copy import deepcopy
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from course_document import CourseBlock, CourseDocument, CourseSection, stable_hash
from slide_deck import (
    SlideBlockSpec,
    SlideSpec,
    _plain_text,
    slide_quality,
    validate_slide_deck,
)
from slide_asset_repository import (
    SlideAssetRepository,
    finalize_visual_assets,
    resolve_visual_plan_assets,
)
from slide_theme import slide_theme_version
from slide_visuals import (
    SlideVisualPlanV1,
    apply_visual_plan_to_slides,
    build_signature,
    deterministic_visual_plan,
    validate_visual_plan,
    visual_integrity_issues,
    visual_quality_report,
)

SLIDE_DECK_V3_SCHEMA = "slide_deck_v3"
SLIDE_DECK_V3_COMPILER_VERSION = "source_first_slide_compiler_v2_visual_director"

SlideDeckMode = Literal["full", "teaching", "concise"]
SlideDeckTheme = Literal[
    "qizhi-classroom",
    "academic-editorial",
    "grid-notebook",
    "modern-geometric",
    "dark-tech",
]

SLIDE_DECK_MODES: tuple[str, ...] = ("full", "teaching", "concise")
SLIDE_DECK_THEMES: tuple[str, ...] = (
    "qizhi-classroom",
    "academic-editorial",
    "grid-notebook",
    "modern-geometric",
    "dark-tech",
)

LEGACY_THEME_ALIASES = {
    "qingfeng-classroom": "qizhi-classroom",
    "academic-bluegray": "academic-editorial",
}

V3_LAYOUTS: tuple[str, ...] = (
    "cover",
    "roadmap",
    "section-divider",
    "objective-cards",
    "hero-statement",
    "editorial-body",
    "two-column",
    "concept-cards",
    "comparison",
    "process",
    "timeline",
    "cycle",
    "cause-effect",
    "hierarchy",
    "knowledge-map",
    "data-highlight",
    "code",
    "formula",
    "case-study",
    "misconception",
    "question",
    "answer",
    "summary",
    "appendix",
)

_CORE_ROLES = {
    "orientation",
    "objective",
    "concept",
    "reasoning",
    "example",
    "misconception",
    "application",
    "activity",
    "checkpoint",
    "summary",
    "transfer",
}
_APPENDIX_ROLES = {"prerequisite", "counterexample", "feedback", "remediation"}
_CONCISE_ROLES = {
    "objective",
    "concept",
    "reasoning",
    "example",
    "misconception",
    "application",
    "checkpoint",
    "summary",
    "transfer",
}
_THEME_PAGE_CAPACITY = {
    "qizhi-classroom": 360,
    "academic-editorial": 420,
    "grid-notebook": 340,
    "modern-geometric": 300,
    "dark-tech": 340,
}


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ContentFragmentV1(_StrictModel):
    fragment_id: str
    section_id: str
    block_id: str
    kind: Literal[
        "heading",
        "paragraph",
        "list_item",
        "code",
        "formula",
        "table",
        "image",
        "diagram",
    ]
    text: str
    ordinal: int = Field(ge=0)
    source_hash: str
    role: str
    source_kind: str
    asset_refs: list[str] = Field(default_factory=list)
    objective_refs: list[str] = Field(default_factory=list)
    concept_refs: list[str] = Field(default_factory=list)


class DerivedTextV1(_StrictModel):
    text: str = Field(min_length=1, max_length=160)
    purpose: Literal[
        "navigation",
        "section_label",
        "page_title",
        "continuation",
        "appendix_label",
    ]
    derived_from: list[str] = Field(default_factory=list)


class PlannedPageV2(_StrictModel):
    page_id: str
    layout: str
    fragment_ids: list[str] = Field(default_factory=list, max_length=8)
    appendix: bool = False
    sequence_id: str = ""
    step_index: int = Field(default=0, ge=0)
    derived_text: list[DerivedTextV1] = Field(default_factory=list, max_length=10)
    narrative_role: Literal[
        "orientation",
        "concept",
        "reasoning",
        "method",
        "example",
        "misconception",
        "checkpoint",
        "recap",
        "appendix",
    ] = "concept"
    section_id: str = ""
    chapter_id: str = ""


class FragmentExclusionV1(_StrictModel):
    fragment_id: str
    reason: Literal["mode_concise", "duplicate_navigation"]


class SlideAllocationPlanV2(_StrictModel):
    schema_version: Literal["slide_allocation_plan_v2"] = "slide_allocation_plan_v2"
    title: str
    mode: SlideDeckMode
    theme: SlideDeckTheme
    variant_key: str
    source_document_revision: str
    pages: list[PlannedPageV2]
    exclusions: list[FragmentExclusionV1] = Field(default_factory=list)
    planner: Literal["ai", "deterministic_fallback"] = "deterministic_fallback"
    fallback_reason: str = ""
    review: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_variant(self) -> "SlideAllocationPlanV2":
        expected = slide_deck_variant_key(self.mode, self.theme)
        if self.variant_key != expected:
            raise ValueError("Slide allocation variant key does not match mode and theme")
        page_ids = [page.page_id for page in self.pages]
        if len(page_ids) != len(set(page_ids)):
            raise ValueError("Slide allocation page IDs must be unique")
        if not self.pages or self.pages[0].layout != "cover":
            raise ValueError("Slide allocation must start with a cover")
        if any(page.layout not in V3_LAYOUTS for page in self.pages):
            raise ValueError("Slide allocation contains an unknown layout")
        return self


def normalize_slide_deck_theme(theme: str) -> str:
    normalized = LEGACY_THEME_ALIASES.get(str(theme or "").strip(), str(theme or "").strip())
    if normalized not in SLIDE_DECK_THEMES:
        choices = ", ".join(SLIDE_DECK_THEMES)
        raise ValueError(f"Unknown slide theme '{theme}'. Expected one of: {choices}")
    return normalized


def slide_deck_variant_key(mode: str, theme: str) -> str:
    if mode not in SLIDE_DECK_MODES:
        raise ValueError(f"Unknown slide mode '{mode}'")
    return f"{mode}:{normalize_slide_deck_theme(theme)}"


def fragment_course_document(document: CourseDocument) -> list[ContentFragmentV1]:
    """Parse active course blocks into stable, display-ready source fragments."""
    fragments: list[ContentFragmentV1] = []
    sections = {section.section_id: section for section in document.sections}
    section_order = _pedagogical_section_order(document.sections)
    ordinal = 0
    for block in sorted(document.blocks, key=lambda item: (
        section_order.get(item.section_id, 10**9),
        item.position,
        item.block_id,
    )):
        if block.status == "retired":
            continue
        units = _fragment_block(block)
        if not units and block.asset_refs and block.kind in {"image", "diagram"}:
            payload = block.payload or {}
            label = str(
                payload.get("alt")
                or payload.get("caption")
                or payload.get("title")
                or block.asset_refs[0]
            ).strip()
            units = [(block.kind, label)]
        for unit_index, (kind, text) in enumerate(units):
            clean = text.strip()
            if not clean:
                continue
            fragment_id = stable_hash({
                "block_id": block.block_id,
                "unit_index": unit_index,
                "kind": kind,
                "text": clean,
            }, prefix="sfg_")
            fragments.append(ContentFragmentV1(
                fragment_id=fragment_id,
                section_id=block.section_id,
                block_id=block.block_id,
                kind=kind,
                text=clean,
                ordinal=ordinal,
                source_hash=stable_hash(clean, prefix="sfh_"),
                role=block.role,
                source_kind=block.kind,
                asset_refs=list(block.asset_refs),
                objective_refs=list(block.objective_refs),
                concept_refs=list(block.concept_refs),
            ))
            ordinal += 1
    return fragments


def _pedagogical_section_order(
    sections: list[CourseSection],
) -> dict[str, int]:
    children: dict[str | None, list[CourseSection]] = {}
    section_ids = {section.section_id for section in sections}
    for section in sections:
        parent_id = (
            section.parent_section_id
            if section.parent_section_id in section_ids
            else None
        )
        children.setdefault(parent_id, []).append(section)
    ordered_ids: list[str] = []
    visited: set[str] = set()

    def visit(section: CourseSection) -> None:
        if section.section_id in visited:
            return
        visited.add(section.section_id)
        ordered_ids.append(section.section_id)
        for child in sorted(
            children.get(section.section_id, []),
            key=lambda item: item.position,
        ):
            visit(child)

    for root in sorted(children.get(None, []), key=lambda item: item.position):
        visit(root)
    for section in sorted(sections, key=lambda item: item.position):
        visit(section)
    return {
        section_id: index
        for index, section_id in enumerate(ordered_ids)
    }


def _fragment_block(block: CourseBlock) -> list[tuple[str, str]]:
    payload = block.payload or {}
    raw = str(
        payload.get("markdown")
        or payload.get("text")
        or payload.get("content")
        or payload.get("value")
        or ""
    ).strip()
    if not raw:
        structured = payload.get("items") or payload.get("steps") or []
        if isinstance(structured, list):
            return [
                ("list_item", str(item.get("text") if isinstance(item, dict) else item))
                for item in structured
                if str(item.get("text") if isinstance(item, dict) else item).strip()
            ]
        return []
    # Course authoring markers are control metadata, not visible teaching copy.
    # Removing them here prevents empty placeholder pages while leaving all
    # audience-visible source text untouched.
    raw = re.sub(r"<!--[\s\S]*?-->", "", raw).strip()
    if not raw:
        return []

    result: list[tuple[str, str]] = []
    cursor = 0
    for match in re.finditer(r"```[\w+.-]*\s*\n(.*?)```", raw, flags=re.S):
        result.extend(_fragment_prose(raw[cursor:match.start()], block))
        result.append(("code", match.group(1).rstrip()))
        cursor = match.end()
    result.extend(_fragment_prose(raw[cursor:], block))
    return result


def _fragment_prose(raw: str, block: CourseBlock) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    paragraph_lines: list[str] = []

    def flush_paragraph() -> None:
        if not paragraph_lines:
            return
        value = " ".join(line.strip() for line in paragraph_lines if line.strip()).strip()
        paragraph_lines.clear()
        if not value:
            return
        value = re.sub(r"^#{1,6}\s+", "", value)
        kind = "formula" if block.kind == "formula" or _looks_like_formula(value) else "paragraph"
        if kind == "formula" or len(value) <= 280:
            result.append((kind, value))
            return
        # Long prose is split only at sentence boundaries.  The sentence text
        # itself is never summarized or rewritten.
        sentences = [
            item for item in re.findall(r".+?(?:[。！？!?](?:[”’\"']*)|$)", value)
            if item
        ] or [value]
        chunk = ""
        for sentence in sentences:
            if chunk and len(chunk) + len(sentence) > 280:
                result.append(("paragraph", chunk))
                chunk = ""
            chunk += sentence
        if chunk:
            result.append(("paragraph", chunk))

    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            continue
        heading_match = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", stripped)
        if heading_match:
            flush_paragraph()
            result.append(("heading", heading_match.group(1).strip()))
            continue
        if re.fullmatch(r"(?:-{3,}|_{3,}|\*{3,})", stripped):
            flush_paragraph()
            continue
        if re.match(r"^\s*(?:[-*+]|\d+[.)])\s+", line):
            flush_paragraph()
            result.append(("list_item", re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", line).strip()))
            continue
        if stripped.startswith("|") and stripped.endswith("|"):
            flush_paragraph()
            if not re.match(r"^\|?\s*:?-{3,}", stripped):
                result.append(("table", stripped.strip("|").strip()))
            continue
        paragraph_lines.append(stripped)
    flush_paragraph()
    return result


def _looks_like_formula(value: str) -> bool:
    # Inline math belongs to its surrounding prose.  Only a standalone display
    # expression becomes a formula fragment/page.
    return bool(re.fullmatch(
        r"\s*(?:\$\$[\s\S]+?\$\$|\\\[[\s\S]+?\\\])\s*",
        value,
    ))


async def plan_slide_deck_v3(
    document: CourseDocument,
    course_data: dict[str, Any],
    *,
    mode: SlideDeckMode = "teaching",
    theme: SlideDeckTheme = "qizhi-classroom",
    ai_planner: Callable[[dict[str, Any]], Awaitable[dict[str, Any]] | dict[str, Any]] | None = None,
    ai_reviewer: Callable[[dict[str, Any]], Awaitable[dict[str, Any]] | dict[str, Any]] | None = None,
    timeout_seconds: float = 10.0,
) -> SlideAllocationPlanV2:
    """Return an ID-only AI allocation or a deterministic source-preserving plan."""
    fragments = fragment_course_document(document)
    fallback = deterministic_slide_allocation(document, fragments, mode=mode, theme=theme)
    if ai_planner is None:
        fallback.fallback_reason = "no_ai_planner"
        return fallback
    request = {
        "schema_version": "slide_allocation_request_v2",
        "title": document.title,
        "mode": mode,
        "theme": theme,
        "variant_key": slide_deck_variant_key(mode, theme),
        "source_document_revision": document.document_revision,
        "allowed_layouts": list(V3_LAYOUTS),
        "rules": {
            "body_text_forbidden": True,
            "preserve_fragment_order": True,
            "full_coverage_required": mode in {"full", "teaching"},
            "concise_exclusions_required": mode == "concise",
        },
        "fragments": [
            {
                "fragment_id": item.fragment_id,
                "section_id": item.section_id,
                "block_id": item.block_id,
                "kind": item.kind,
                "role": item.role,
                "text": item.text,
                "ordinal": item.ordinal,
            }
            for item in fragments
        ],
    }
    try:
        raw = await asyncio.wait_for(_invoke(ai_planner, request), timeout=timeout_seconds)
        candidate = SlideAllocationPlanV2.model_validate(raw)
        candidate.planner = "ai"
        candidate.fallback_reason = ""
        validate_allocation_plan(candidate, fragments)
        if ai_reviewer is not None:
            review_request = {
                "schema_version": "slide_allocation_review_v1",
                "allowed_actions": ["keep", "replan"],
                "body_text_forbidden": True,
                "plan": candidate.model_dump(mode="json"),
                "fragment_ids": [item.fragment_id for item in fragments],
            }
            review = await asyncio.wait_for(_invoke(ai_reviewer, review_request), timeout=timeout_seconds)
            candidate.review = _validated_review(review, candidate)
            if candidate.review.get("action") == "replan":
                fallback.fallback_reason = "review_requested_replan"
                fallback.review = candidate.review
                return fallback
        return candidate
    except Exception:
        fallback.fallback_reason = "invalid_or_failed_ai_plan"
        return fallback


async def _invoke(planner: Callable[[dict[str, Any]], Any], request: dict[str, Any]) -> Any:
    if inspect.iscoroutinefunction(planner):
        return await planner(request)
    result = await asyncio.to_thread(planner, request)
    return await result if inspect.isawaitable(result) else result


def _validated_review(raw: Any, plan: SlideAllocationPlanV2) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("Slide allocation review must be an object")
    action = str(raw.get("action") or "")
    if action not in {"keep", "replan"}:
        raise ValueError("Slide allocation review action is invalid")
    page_ids = {page.page_id for page in plan.pages}
    issues: list[dict[str, str]] = []
    for issue in raw.get("issues") or []:
        if not isinstance(issue, dict):
            raise ValueError("Slide allocation review issue is invalid")
        page_id = str(issue.get("page_id") or "")
        if page_id and page_id not in page_ids:
            raise ValueError("Slide allocation review references an unknown page")
        issues.append({
            "code": str(issue.get("code") or "review_issue"),
            "page_id": page_id,
            "suggested_action": str(issue.get("suggested_action") or "reallocate"),
        })
    return {"action": action, "issues": issues[:20]}


def deterministic_slide_allocation(
    document: CourseDocument,
    fragments: list[ContentFragmentV1],
    *,
    mode: SlideDeckMode,
    theme: SlideDeckTheme,
) -> SlideAllocationPlanV2:
    theme = normalize_slide_deck_theme(theme)  # type: ignore[assignment]
    included, excluded = _select_fragments_for_mode(fragments, mode)
    section_index = {section.section_id: section for section in document.sections}
    capacity = _THEME_PAGE_CAPACITY[theme]
    chapters = [
        section
        for section in sorted(document.sections, key=lambda item: item.position)
        if section.level == 1
    ]
    chapter_ids = {
        _chapter_id_for_section(fragment.section_id, section_index)
        for fragment in included
    }
    pages: list[PlannedPageV2] = [
        PlannedPageV2(
            page_id="slide:title",
            layout="cover",
            narrative_role="orientation",
            derived_text=[DerivedTextV1(
                text=document.title,
                purpose="navigation",
            )],
        ),
        PlannedPageV2(
            page_id="slide:roadmap",
            layout="roadmap",
            derived_text=[
                DerivedTextV1(
                    text=section.title,
                    purpose="section_label",
                )
                for section in chapters
                if section.section_id in chapter_ids
            ][:10],
            narrative_role="orientation",
        ),
    ]

    grouped: dict[tuple[str, str], list[ContentFragmentV1]] = {}
    for fragment in included:
        grouped.setdefault((fragment.section_id, fragment.block_id), []).append(fragment)

    source_runs: list[dict[str, Any]] = []
    for (section_id, block_id), block_fragments in grouped.items():
        for run_index, run_fragments in enumerate(_semantic_fragment_runs(block_fragments), start=1):
            section = section_index.get(section_id)
            source_runs.append({
                "run_id": f"{block_id}:{run_index}",
                "section_id": section_id,
                "block_id": block_id,
                "chapter_id": _chapter_id_for_section(section_id, section_index),
                "topic_id": _topic_id_for_section(section_id, section_index),
                "section_level": section.level if section else 1,
                "fragments": run_fragments,
                "narrative_role": _narrative_role_for_run(run_fragments),
                "source_role": run_fragments[0].role,
                "has_heading": any(
                    fragment.kind == "heading"
                    for fragment in run_fragments
                ),
            })

    mainline_run_ids = _select_mainline_run_ids(source_runs, mode)
    appendix_pages: list[PlannedPageV2] = []
    chapter_order = [
        chapter.section_id for chapter in chapters
        if chapter.section_id in chapter_ids
    ]
    chapter_order.extend([
        chapter_id
        for chapter_id in dict.fromkeys(run["chapter_id"] for run in source_runs)
        if chapter_id not in chapter_order
    ])

    for chapter_number, chapter_id in enumerate(chapter_order, start=1):
        chapter = section_index.get(chapter_id)
        chapter_runs = [
            run for run in source_runs
            if run["chapter_id"] == chapter_id
        ]
        mainline_runs = [
            run for run in chapter_runs
            if run["run_id"] in mainline_run_ids
        ]
        if not mainline_runs:
            for run in chapter_runs:
                appendix_pages.extend(_allocate_run_pages(
                    run,
                    capacity=capacity,
                    appendix=True,
                ))
            continue

        chapter_title = chapter.title if chapter else f"第 {chapter_number} 章"
        has_topic_sections = any(
            section.level == 2
            and _chapter_id_for_section(section.section_id, section_index) == chapter_id
            for section in document.sections
        )
        chapter_intro_runs = [
            run
            for run in mainline_runs
            if run["section_level"] == 1
            and (run["source_role"] == "orientation" or has_topic_sections)
            and not _has_atomic_fragment(run["fragments"])
        ][:1]
        chapter_intro_fragments = [
            fragment
            for run in chapter_intro_runs
            for fragment in run["fragments"]
        ]
        if (
            len(chapter_intro_fragments) > 8
            or sum(len(fragment.text) for fragment in chapter_intro_fragments) > 90
        ):
            chapter_intro_runs = []
            chapter_intro_fragments = []
        chapter_intro_run_ids = {
            run["run_id"] for run in chapter_intro_runs
        }
        topic_sections = [
            section
            for section in sorted(document.sections, key=lambda item: item.position)
            if section.level == 2
            and _chapter_id_for_section(section.section_id, section_index) == chapter_id
        ]
        pages.append(PlannedPageV2(
            page_id=f"slide:chapter:{chapter_id}",
            layout="section-divider",
            fragment_ids=[
                fragment.fragment_id
                for fragment in chapter_intro_fragments
            ],
            narrative_role="orientation",
            section_id=chapter_id,
            chapter_id=chapter_id,
            derived_text=[
                DerivedTextV1(
                    text=chapter_title,
                    purpose="section_label",
                ),
                *[
                    DerivedTextV1(
                        text=section.title,
                        purpose="navigation",
                    )
                    for section in topic_sections[:6]
                ],
            ],
        ))
        for run in mainline_runs:
            if run["run_id"] in chapter_intro_run_ids:
                continue
            pages.extend(_allocate_run_pages(
                run,
                capacity=capacity,
                appendix=False,
            ))
        pages.append(PlannedPageV2(
            page_id=f"slide:chapter-recap:{chapter_id}",
            layout="summary",
            narrative_role="recap",
            section_id=chapter_id,
            chapter_id=chapter_id,
            derived_text=[
                DerivedTextV1(
                    text=chapter_title,
                    purpose="section_label",
                ),
                *[
                    DerivedTextV1(
                        text=section.title,
                        purpose="navigation",
                    )
                    for section in topic_sections[:8]
                ],
            ],
        ))
        for run in chapter_runs:
            if run["run_id"] not in mainline_run_ids:
                appendix_pages.extend(_allocate_run_pages(
                    run,
                    capacity=capacity,
                    appendix=True,
                ))

    if appendix_pages:
        appendix_ids = [fragment_id for page in appendix_pages for fragment_id in page.fragment_ids]
        pages.append(PlannedPageV2(
            page_id="slide:appendix-divider",
            layout="section-divider",
            appendix=True,
            narrative_role="appendix",
            derived_text=[DerivedTextV1(
                text="补充材料",
                purpose="appendix_label",
                derived_from=appendix_ids,
            )],
        ))
    pages.extend(appendix_pages)
    pages.append(PlannedPageV2(
        page_id="slide:summary",
        layout="summary",
        narrative_role="recap",
        derived_text=[DerivedTextV1(text="课程回顾", purpose="navigation")],
    ))
    plan = SlideAllocationPlanV2(
        title=document.title,
        mode=mode,
        theme=theme,
        variant_key=slide_deck_variant_key(mode, theme),
        source_document_revision=document.document_revision,
        pages=pages,
        exclusions=[
            FragmentExclusionV1(fragment_id=item.fragment_id, reason="mode_concise")
            for item in excluded
        ],
        planner="deterministic_fallback",
    )
    validate_allocation_plan(plan, fragments)
    return plan


def _chapter_id_for_section(
    section_id: str,
    sections: dict[str, CourseSection],
) -> str:
    section = sections.get(section_id)
    if not section:
        return section_id
    visited: set[str] = set()
    while section.parent_section_id and section.parent_section_id not in visited:
        visited.add(section.section_id)
        parent = sections.get(section.parent_section_id)
        if not parent:
            break
        section = parent
    return section.section_id


def _topic_id_for_section(
    section_id: str,
    sections: dict[str, CourseSection],
) -> str:
    section = sections.get(section_id)
    if not section:
        return section_id
    visited: set[str] = set()
    while section.level > 2 and section.parent_section_id not in visited:
        visited.add(section.section_id)
        parent = sections.get(section.parent_section_id or "")
        if not parent:
            break
        section = parent
    return section.section_id


def _semantic_fragment_runs(
    fragments: list[ContentFragmentV1],
) -> list[list[ContentFragmentV1]]:
    runs: list[list[ContentFragmentV1]] = []
    current: list[ContentFragmentV1] = []
    for fragment in fragments:
        if (
            fragment.kind == "heading"
            and current
            and any(item.kind != "heading" for item in current)
        ):
            runs.append(current)
            current = []
        current.append(fragment)
    if current:
        runs.append(current)
    return runs


def _narrative_role_for_run(
    fragments: list[ContentFragmentV1],
) -> str:
    heading = next(
        (fragment.text for fragment in fragments if fragment.kind == "heading"),
        "",
    )
    normalized = re.sub(r"\s+", "", heading).lower()
    keyword_roles = (
        ("checkpoint", ("思考", "挑战", "问题", "练习", "检查", "question", "challenge", "practice", "check")),
        ("misconception", ("误区", "易错", "反例", "misconception", "pitfall", "counterexample")),
        ("example", ("案例", "应用", "示例", "实战", "example", "application", "case")),
        ("method", ("方法", "步骤", "实现", "技术", "算法", "method", "implementation", "algorithm", "procedure")),
        ("reasoning", ("原理", "机制", "推导", "证明", "深度", "principle", "mechanism", "derivation", "proof", "deep")),
        ("recap", ("总结", "小结", "回顾", "summary", "recap")),
        ("concept", ("核心", "概念", "背景", "定义", "引入", "core", "concept", "background", "definition", "idea")),
    )
    for role, keywords in keyword_roles:
        if any(keyword in normalized for keyword in keywords):
            return role
    source_role = fragments[0].role if fragments else "concept"
    return {
        "orientation": "orientation",
        "objective": "orientation",
        "reasoning": "reasoning",
        "example": "example",
        "application": "example",
        "misconception": "misconception",
        "checkpoint": "checkpoint",
        "activity": "checkpoint",
        "summary": "recap",
        "transfer": "example",
    }.get(source_role, "concept" if not heading else "appendix")


def _select_mainline_run_ids(
    runs: list[dict[str, Any]],
    mode: SlideDeckMode,
) -> set[str]:
    if mode != "teaching":
        return {run["run_id"] for run in runs}

    selected: set[str] = set()
    detailed_by_topic: dict[str, list[dict[str, Any]]] = {}
    for run in runs:
        if run["source_role"] in _APPENDIX_ROLES:
            continue
        if run["section_level"] <= 2:
            selected.add(run["run_id"])
            continue
        detailed_by_topic.setdefault(run["topic_id"], []).append(run)

    # A teaching topic follows a compact learning arc.  One source run per
    # narrative job is promoted; all remaining verbatim detail stays available
    # in the appendix.
    teachable_roles = {
        "orientation",
        "concept",
        "reasoning",
        "method",
        "example",
        "misconception",
        "checkpoint",
        "recap",
    }
    for topic_runs in detailed_by_topic.values():
        used_roles: set[str] = set()
        for run in topic_runs:
            role = run["narrative_role"]
            if not run["has_heading"] and run["source_role"] == "concept":
                continue
            if role in teachable_roles and role not in used_roles:
                selected.add(run["run_id"])
                used_roles.add(role)
    return selected


def _allocate_run_pages(
    run: dict[str, Any],
    *,
    capacity: int,
    appendix: bool,
) -> list[PlannedPageV2]:
    fragments: list[ContentFragmentV1] = run["fragments"]
    heading = fragments[0] if fragments and fragments[0].kind == "heading" else None
    body_fragments = fragments[1:] if heading else fragments
    raw_chunks = _paginate_fragments(
        body_fragments,
        capacity,
        appendix=appendix,
    ) or [[]]
    maximum_body_fragments = (
        4
        if not appendix and run["narrative_role"] == "misconception"
        else 7
        if heading
        else 8
    )
    chunks = [
        fragment_slice
        for chunk in raw_chunks
        for fragment_slice in (
            [
                chunk[index:index + maximum_body_fragments]
                for index in range(0, len(chunk), maximum_body_fragments)
            ]
            if len(chunk) > maximum_body_fragments
            else [chunk]
        )
    ]
    allocated: list[PlannedPageV2] = []
    for chunk_index, body_chunk in enumerate(chunks, start=1):
        chunk = [
            *([heading] if heading and chunk_index == 1 else []),
            *body_chunk,
        ]
        derived: list[DerivedTextV1] = []
        if heading:
            derived.append(DerivedTextV1(
                text=heading.text,
                purpose="page_title",
                derived_from=[heading.fragment_id],
            ))
        if chunk_index > 1:
            derived.append(DerivedTextV1(
                text="续",
                purpose="continuation",
                derived_from=[item.fragment_id for item in chunk],
            ))
        narrative_role = (
            "appendix" if appendix else run["narrative_role"]
        )
        source_layout = _layout_for_fragments(
            chunk,
            narrative_role=narrative_role,
        )
        layout = (
            source_layout
            if appendix and _has_atomic_fragment(chunk)
            else "appendix"
            if appendix
            else source_layout
        )
        page = PlannedPageV2(
            page_id=(
                f"slide:{run['block_id']}:run:{run['run_id'].rsplit(':', 1)[-1]}"
                f":page:{chunk_index}"
            ),
            layout=layout,
            fragment_ids=[item.fragment_id for item in chunk],
            appendix=appendix,
            derived_text=derived,
            narrative_role=narrative_role,
            section_id=run["section_id"],
            chapter_id=run["chapter_id"],
        )
        allocated.extend(_expand_reveal_pages(page, chunk))
    return allocated


def _select_fragments_for_mode(
    fragments: list[ContentFragmentV1],
    mode: SlideDeckMode,
) -> tuple[list[ContentFragmentV1], list[ContentFragmentV1]]:
    if mode != "concise":
        return list(fragments), []
    included = [item for item in fragments if item.role in _CONCISE_ROLES]
    if not included and fragments:
        included = list(fragments[: min(8, len(fragments))])
    included_ids = {item.fragment_id for item in included}
    return included, [item for item in fragments if item.fragment_id not in included_ids]


def _paginate_fragments(
    fragments: list[ContentFragmentV1],
    capacity: int,
    *,
    appendix: bool = False,
) -> list[list[ContentFragmentV1]]:
    pages: list[list[ContentFragmentV1]] = []
    current: list[ContentFragmentV1] = []
    current_size = 0
    for fragment in fragments:
        size = len(fragment.text)
        candidate = [*current, fragment]
        page_limit = (
            8 if appendix and not _has_atomic_fragment(candidate)
            else _fragment_page_limit(candidate)
        )
        text_capacity = (
            max(capacity, 820)
            if appendix
            else _materialized_text_capacity(candidate, capacity)
        )
        if current and (
            current_size + size > text_capacity
            or len(current) >= page_limit
            or (
                not appendix
                and _estimated_materialized_block_count(candidate) > 2
            )
            or (not appendix and not _fits_materialized_layout(candidate))
            or (fragment.kind == "code" and current)
        ):
            pages.append(current)
            current = []
            current_size = 0
        current.append(fragment)
        current_size += size
        if fragment.kind == "code" or current_size >= capacity:
            pages.append(current)
            current = []
            current_size = 0
    if current:
        pages.append(current)
    return pages


def _has_atomic_fragment(fragments: list[ContentFragmentV1]) -> bool:
    return bool({item.kind for item in fragments} & {"code", "formula", "table"})


def _materialized_text_capacity(
    fragments: list[ContentFragmentV1],
    theme_capacity: int,
) -> int:
    kinds = {item.kind for item in fragments}
    if kinds <= {"heading", "paragraph"}:
        return min(theme_capacity, 280)
    if kinds == {"list_item"}:
        return min(theme_capacity, 360)
    if kinds & {"code", "formula", "table"}:
        return theme_capacity
    return min(theme_capacity, 280)


def _fragment_page_limit(fragments: list[ContentFragmentV1]) -> int:
    kinds = {item.kind for item in fragments}
    if kinds & {"code", "formula", "table"}:
        return 1
    if kinds == {"list_item"}:
        return 5
    return 8


def _estimated_materialized_block_count(
    fragments: list[ContentFragmentV1],
) -> int:
    """Count the visual blocks produced by contiguous fragment runs."""
    return len(_visual_fragment_groups(fragments))


def _visual_fragment_groups(
    fragments: list[ContentFragmentV1],
) -> list[tuple[str, list[ContentFragmentV1]]]:
    groups: list[tuple[str, list[ContentFragmentV1]]] = []
    for fragment in fragments:
        if fragment.kind in {"heading", "paragraph"}:
            group = "prose"
        elif fragment.kind == "list_item" and len(_display_text(fragment.text)) <= 72:
            group = "list"
        elif fragment.kind == "list_item":
            group = "long-list"
        else:
            group = fragment.kind
        if groups and group in {"prose", "list"} and groups[-1][0] == group:
            groups[-1][1].append(fragment)
        else:
            groups.append((group, [fragment]))
    return groups


def _fits_materialized_layout(fragments: list[ContentFragmentV1]) -> bool:
    groups = _visual_fragment_groups(fragments)
    visible_count = max(1, len(groups))
    content_limit = {1: 280, 2: 150}.get(visible_count, 96)
    item_limit = {1: 72, 2: 48}.get(visible_count, 32)
    item_count_limit = 6 if visible_count == 1 else 3
    for group, items in groups:
        values = [_display_text(item.text) for item in items]
        if group == "list":
            if len(values) > item_count_limit or any(
                len(value) > item_limit for value in values
            ):
                return False
        elif group in {"prose", "long-list", "formula", "table"}:
            if len("\n\n".join(values)) > content_limit:
                return False
    return True


def _layout_for_fragments(
    fragments: list[ContentFragmentV1],
    *,
    narrative_role: str = "",
) -> str:
    kinds = {item.kind for item in fragments}
    role = narrative_role or (fragments[0].role if fragments else "concept")
    if "code" in kinds:
        return "code"
    if "formula" in kinds:
        return "formula"
    if role in {"orientation", "objective"}:
        return "objective-cards"
    if role in {"example", "application"}:
        return "case-study"
    if role == "misconception":
        return "misconception"
    if role in {"checkpoint", "activity"}:
        return "question"
    list_items = [item for item in fragments if item.kind == "list_item"]
    if (
        role in {"method", "process"} or len(list_items) >= 3
    ) and (
        kinds <= {"heading", "list_item"}
        and sum(item.kind == "heading" for item in fragments) <= 1
        and list_items
        and all(len(item.text) <= 48 for item in list_items)
    ):
        return "process"
    if role == "reasoning":
        return "two-column" if len(fragments) >= 2 else "editorial-body"
    if role in {"summary", "recap"}:
        return "summary"
    if role == "concept" and len(fragments) <= 2:
        return "hero-statement"
    if kinds == {"list_item"} and len(fragments) >= 4:
        return "concept-cards"
    if len(fragments) == 2:
        return "two-column"
    return "editorial-body"


def _expand_reveal_pages(
    page: PlannedPageV2,
    fragments: list[ContentFragmentV1],
) -> list[PlannedPageV2]:
    """Turn process pages into cumulative, PowerPoint-compatible reveal steps."""
    if page.appendix or page.layout not in {"process", "timeline", "cycle"}:
        return [page]
    if any(fragment.kind != "list_item" for fragment in fragments):
        return [page]
    if len(fragments) < 3 or len(fragments) > 5:
        return [page]
    sequence_id = f"sequence:{page.page_id}"
    return [
        page.model_copy(update={
            "page_id": f"{page.page_id}:step:{step_index}",
            "fragment_ids": list(page.fragment_ids[:step_index]),
            "sequence_id": sequence_id,
            "step_index": step_index,
            "derived_text": [
                *page.derived_text,
                DerivedTextV1(
                    text=f"步骤 {step_index}/{len(fragments)}",
                    purpose="navigation",
                    derived_from=list(page.fragment_ids[:step_index]),
                ),
            ],
        })
        for step_index in range(1, len(fragments) + 1)
    ]


def validate_allocation_plan(
    plan: SlideAllocationPlanV2,
    fragments: list[ContentFragmentV1],
) -> None:
    catalog = {item.fragment_id: item for item in fragments}
    referenced = _allocated_fragment_ids(plan)
    excluded = [item.fragment_id for item in plan.exclusions]
    unknown = (set(referenced) | set(excluded)) - set(catalog)
    if unknown:
        raise ValueError("Slide allocation references unknown source fragments")
    if len(excluded) != len(set(excluded)):
        raise ValueError("Slide allocation duplicates excluded fragments")
    if catalog and not referenced:
        raise ValueError("Slide allocation must include at least one source fragment")
    page_groups = (
        [
            [page for page in plan.pages if not page.appendix],
            [page for page in plan.pages if page.appendix],
        ]
        if plan.mode == "teaching"
        else [plan.pages]
    )
    for pages in page_groups:
        ordered = [
            catalog[fragment_id].ordinal
            for fragment_id in _allocated_fragment_ids_from_pages(pages)
        ]
        if ordered != sorted(ordered):
            inversion = next(
                (
                    (ordered[index - 1], ordered[index])
                    for index in range(1, len(ordered))
                    if ordered[index] < ordered[index - 1]
                ),
                ("?", "?"),
            )
            raise ValueError(
                "Slide allocation changes source fragment order "
                f"({inversion[0]} before {inversion[1]})"
            )
    if plan.mode in {"full", "teaching"}:
        if set(referenced) != set(catalog) or excluded:
            raise ValueError("Full and teaching modes require complete source coverage")
    else:
        if set(referenced) & set(excluded):
            raise ValueError("Concise fragments cannot be both included and excluded")
        if set(referenced) | set(excluded) != set(catalog):
            raise ValueError("Concise mode requires an explicit decision for every fragment")


def _allocated_fragment_ids(plan: SlideAllocationPlanV2) -> list[str]:
    """Return each allocated source fragment once, validating reveal sequences."""
    return _allocated_fragment_ids_from_pages(plan.pages)


def _allocated_fragment_ids_from_pages(
    plan_pages: list[PlannedPageV2],
) -> list[str]:
    sequence_groups: dict[str, list[PlannedPageV2]] = {}
    for page in plan_pages:
        if page.sequence_id:
            sequence_groups.setdefault(page.sequence_id, []).append(page)
    sequence_fragments: dict[str, list[str]] = {}
    for sequence_id, sequence_pages in sequence_groups.items():
        ordered = sorted(sequence_pages, key=lambda item: item.step_index)
        if [item.step_index for item in ordered] != list(range(1, len(ordered) + 1)):
            raise ValueError(f"Reveal sequence '{sequence_id}' has invalid step indexes")
        positions = sorted(plan_pages.index(item) for item in sequence_pages)
        if positions != list(range(positions[0], positions[0] + len(positions))):
            raise ValueError(f"Reveal sequence '{sequence_id}' pages must be contiguous")
        final_ids = ordered[-1].fragment_ids
        if any(page.fragment_ids != final_ids[: len(page.fragment_ids)] for page in ordered):
            raise ValueError(f"Reveal sequence '{sequence_id}' must use cumulative prefixes")
        if [len(page.fragment_ids) for page in ordered] != list(range(1, len(final_ids) + 1)):
            raise ValueError(f"Reveal sequence '{sequence_id}' must reveal one fragment per step")
        sequence_fragments[sequence_id] = final_ids

    allocated: list[str] = []
    emitted_sequences: set[str] = set()
    for page in plan_pages:
        if not page.sequence_id:
            allocated.extend(page.fragment_ids)
            continue
        if page.sequence_id in emitted_sequences:
            continue
        allocated.extend(sequence_fragments[page.sequence_id])
        emitted_sequences.add(page.sequence_id)
    if len(allocated) != len(set(allocated)):
        raise ValueError("Slide allocation duplicates source fragments outside one reveal sequence")
    return allocated


def compile_slide_deck_v3(
    document: CourseDocument,
    course_data: dict[str, Any],
    *,
    mode: SlideDeckMode = "teaching",
    theme: SlideDeckTheme = "qizhi-classroom",
    allocation_plan: SlideAllocationPlanV2 | dict[str, Any] | None = None,
    visual_plan: SlideVisualPlanV1 | dict[str, Any] | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
    resume_slides: list[dict[str, Any]] | None = None,
    asset_repository: SlideAssetRepository | None = None,
) -> dict[str, Any]:
    fragments = fragment_course_document(document)
    if allocation_plan is None:
        plan = deterministic_slide_allocation(document, fragments, mode=mode, theme=theme)
        plan.fallback_reason = "no_precomputed_plan"
    else:
        plan = (
            allocation_plan
            if isinstance(allocation_plan, SlideAllocationPlanV2)
            else SlideAllocationPlanV2.model_validate(allocation_plan)
        )
        if plan.source_document_revision != document.document_revision:
            raise ValueError("Slide allocation source revision is stale")
        validate_allocation_plan(plan, fragments)
    resolved_visual_plan = (
        deterministic_visual_plan(document, plan, fragments)
        if visual_plan is None
        else (
            visual_plan
            if isinstance(visual_plan, SlideVisualPlanV1)
            else SlideVisualPlanV1.model_validate(visual_plan)
        )
    )
    validate_visual_plan(resolved_visual_plan, plan, fragments)
    if progress_callback:
        progress_callback({
            "event": "visual_plan",
            "progress": 10,
            "stage": "visual_plan",
            "visual_plan": resolved_visual_plan.model_dump(mode="json"),
        })
        progress_callback({
            "event": "asset_progress",
            "progress": 12,
            "stage": "asset_compilation",
            "completed": 0,
            "total": 0,
        })
    resolved_visual_plan, visual_asset_manifest = resolve_visual_plan_assets(
        resolved_visual_plan,
        fragments,
        course_id=document.course_id,
        repository=asset_repository,
        progress_callback=progress_callback,
    )
    validate_visual_plan(resolved_visual_plan, plan, fragments)
    catalog = {item.fragment_id: item for item in fragments}
    sections = {item.section_id: item for item in document.sections}
    blocks = {item.block_id: item for item in document.blocks}
    resumed: dict[str, SlideSpec] = {}
    for raw in resume_slides or []:
        try:
            slide = SlideSpec.model_validate(raw)
        except (TypeError, ValueError):
            continue
        resumed[slide.unit_id] = slide

    slides: list[SlideSpec] = []
    for page_index, page in enumerate(plan.pages):
        slide = resumed.get(page.page_id)
        newly_materialized = slide is None
        if slide is None:
            slide = _materialize_page(
                document,
                page,
                [catalog[fragment_id] for fragment_id in page.fragment_ids],
                sections,
                blocks,
            )
            slide.position = page_index
            source_quality = deepcopy(slide.quality)
            slide.quality = {**slide_quality(slide), **source_quality}
        else:
            slide.position = page_index
        slide = SlideSpec.model_validate(
            apply_visual_plan_to_slides(
                [slide.model_dump(mode="json")],
                resolved_visual_plan,
            )[0]
        )
        if progress_callback and newly_materialized:
            progress_callback({
                "event": "slide_upsert",
                "progress": min(92, 14 + round(((page_index + 1) / max(1, len(plan.pages))) * 78)),
                "slide": slide.model_dump(mode="json"),
            })
        slides.append(slide)

    referenced = _allocated_fragment_ids(plan)
    excluded = [item.fragment_id for item in plan.exclusions]
    coverage = {
        "source_fragment_count": len(fragments),
        "included_fragment_count": len(referenced),
        "excluded_fragment_count": len(excluded),
        "included_fragment_ids": referenced,
        "excluded_fragment_ids": excluded,
        "visible_coverage_ratio": (
            1.0 if not fragments else round(len(referenced) / len(fragments), 6)
        ),
        "decision_coverage_ratio": (
            1.0 if not fragments else round(len(set(referenced) | set(excluded)) / len(fragments), 6)
        ),
        "hash_integrity_passed": all(
            catalog[fragment_id].source_hash == stable_hash(catalog[fragment_id].text, prefix="sfh_")
            for fragment_id in referenced
        ),
    }
    visual_quality = visual_quality_report(resolved_visual_plan, plan)
    signature = build_signature(
        source_document_revision=document.document_revision,
        mode=plan.mode,
        theme=plan.theme,
        compiler_version=SLIDE_DECK_V3_COMPILER_VERSION,
        theme_version=slide_theme_version(),
    )
    content = {
        "schema_version": SLIDE_DECK_V3_SCHEMA,
        "title": document.title,
        "theme": plan.theme,
        "mode": plan.mode,
        "variant_key": plan.variant_key,
        "source_document_revision": document.document_revision,
        "aspect_ratio": "16:9",
        "fragment_manifest": [item.model_dump(mode="json") for item in fragments],
        "allocation_plan": plan.model_dump(mode="json"),
        "deck_brief": resolved_visual_plan.deck_brief,
        "visual_plan": resolved_visual_plan.model_dump(mode="json"),
        "visual_asset_manifest": visual_asset_manifest,
        "build_signature": signature,
        "visual_quality_report": visual_quality,
        "slides": [item.model_dump(mode="json") for item in slides],
        "coverage_report": coverage,
        "exclusions": [item.model_dump(mode="json") for item in plan.exclusions],
        "presentation_overrides": {},
        "override_conflicts": [],
    }
    quality = validate_slide_deck_v3(content, course_data=course_data)
    finalized_assets = finalize_visual_assets(
        visual_asset_manifest,
        repository=asset_repository,
        publish=bool(quality["passed"]),
    )
    content["visual_asset_manifest"] = finalized_assets
    content["quality_report"] = deepcopy(quality)
    content["quality_summary"] = {
        "passed": quality["passed"],
        "score": quality["score"],
        "semantic_issue_count": len(quality["semantic"]["issues"]),
        "visual_issue_count": len(quality["visual"]["issues"]),
        "coverage_ratio": coverage["visible_coverage_ratio"],
        "main_slide_count": sum(
            1 for page in plan.pages if not page.appendix
        ),
        "appendix_slide_count": sum(
            1 for page in plan.pages if page.appendix
        ),
        "large_deck_warning": len(plan.pages) > 120,
        "split_recommended": len(plan.pages) > 300,
    }
    if progress_callback:
        progress_callback({
            "event": "visual_quality",
            "progress": 96,
            "stage": "visual_quality",
            "quality": visual_quality,
        })
        progress_callback({"event": "slide_quality", "progress": 97, "quality": quality})
    return content


def _materialize_page(
    document: CourseDocument,
    page: PlannedPageV2,
    fragments: list[ContentFragmentV1],
    sections: dict[str, CourseSection],
    blocks: dict[str, CourseBlock],
) -> SlideSpec:
    if page.layout == "cover":
        return SlideSpec(
            unit_id=page.page_id,
            position=0,
            layout="cover",
            slide_purpose="orientation",
            eyebrow="课程演示",
            title=document.title,
            subtitle="课程正文智能分页课件",
            key_message="内容来自课程正文，页面由系统进行分配与排版。",
            blocks=[],
            source_keys=["course_title"],
        )
    if page.layout == "roadmap":
        labels = [_display_text(item.text) for item in page.derived_text]
        return SlideSpec(
            unit_id=page.page_id,
            position=0,
            layout="roadmap",
            slide_purpose="course_route",
            eyebrow="课程路线",
            title="本次课程内容",
            blocks=[SlideBlockSpec(
                block_id=f"{page.page_id}:route",
                type="process",
                items=labels[:8],
                metadata={"derived_text": True},
            )],
            source_section_ids=[
                item.section_id
                for item in sorted(sections.values(), key=lambda value: value.position)
                if item.title in labels
            ],
        )
    if page.page_id == "slide:summary" and not fragments:
        recap_sections = [
            section
            for section in sorted(sections.values(), key=lambda item: item.position)
            if section.level == 1
        ][:6]
        if not recap_sections:
            recap_sections = sorted(
                sections.values(), key=lambda item: item.position
            )[:6]
        return SlideSpec(
            unit_id=page.page_id,
            position=0,
            layout="recap",
            slide_purpose="course_recap",
            eyebrow="课程回顾",
            title="回到课程目标",
            blocks=[SlideBlockSpec(
                block_id=f"{page.page_id}:recap",
                type="bullets",
                title="课程内容回顾",
                items=[_display_text(section.title) for section in recap_sections],
                metadata={
                    "derived_text": True,
                    "source_section_ids": [
                        section.section_id for section in recap_sections
                    ],
                },
            )],
            source_section_ids=[
                section.section_id for section in recap_sections
            ],
            source_keys=["course_title"],
        )
    if page.page_id == "slide:appendix-divider":
        return SlideSpec(
            unit_id=page.page_id,
            position=0,
            layout="chapter",
            slide_purpose="appendix",
            eyebrow="补充材料",
            title="课程补充内容",
            key_message="以下页面保留授课主线之外的课程原文。",
            blocks=[],
            source_keys=["course_document"],
        )
    if page.page_id.startswith("slide:chapter:"):
        labels = [
            _display_text(item.text)
            for item in page.derived_text
            if item.purpose == "navigation"
        ]
        title = next(
            (
                _display_text(item.text)
                for item in page.derived_text
                if item.purpose == "section_label"
            ),
            "课程章节",
        )
        return SlideSpec(
            unit_id=page.page_id,
            position=0,
            layout="chapter",
            slide_purpose="chapter_open",
            eyebrow="章节导入",
            title=title,
            key_message=(
                " ".join(_display_text(fragment.text) for fragment in fragments)
                if fragments
                else
                " → ".join(labels[:4])
                if labels
                else "本章将从核心问题出发逐步展开。"
            ),
            blocks=[],
            section_id=fragments[0].section_id if fragments else None,
            source_section_ids=(
                list(dict.fromkeys(fragment.section_id for fragment in fragments))
                if fragments
                else [page.section_id] if page.section_id else []
            ),
            source_block_ids=list(dict.fromkeys(
                fragment.block_id for fragment in fragments
            )),
            source_keys=(
                [f"block:{fragment.block_id}" for fragment in fragments]
                if fragments
                else ["course_document"]
            ),
            quality={
                "fragment_ids": [
                    fragment.fragment_id for fragment in fragments
                ],
                "source_hashes": {
                    fragment.fragment_id: fragment.source_hash
                    for fragment in fragments
                },
                "requested_layout": page.layout,
                "narrative_role": page.narrative_role,
                "chapter_id": page.chapter_id,
            },
        )
    if page.page_id.startswith("slide:chapter-recap:") and not fragments:
        labels = [
            _display_text(item.text)
            for item in page.derived_text
            if item.purpose == "navigation"
        ]
        chapter_title = next(
            (
                _display_text(item.text)
                for item in page.derived_text
                if item.purpose == "section_label"
            ),
            "本章",
        )
        return SlideSpec(
            unit_id=page.page_id,
            position=0,
            layout="recap",
            slide_purpose="chapter_recap",
            eyebrow="本章回顾",
            title=f"{chapter_title}：知识链回顾",
            key_message="回看本章各主题之间的递进关系。",
            blocks=[SlideBlockSpec(
                block_id=f"{page.page_id}:recap",
                type="process",
                items=labels or [chapter_title],
                metadata={"derived_text": True},
            )],
            section_id=None,
            source_section_ids=[page.section_id] if page.section_id else [],
            source_keys=["course_document"],
        )

    first = fragments[0] if fragments else None
    section = sections.get(first.section_id if first else "")
    block = blocks.get(first.block_id if first else "")
    block_title = _display_text(
        str((block.payload or {}).get("title") or "").strip()
    )
    title = (
        _display_text(section.title)
        if section and _is_placeholder_title(block_title)
        else block_title or (
            _display_text(section.title) if section else "课程内容"
        )
    )
    source_page_title = next(
        (
            _display_text(item.text)
            for item in page.derived_text
            if item.purpose == "page_title"
        ),
        "",
    )
    if source_page_title:
        title = source_page_title
    if page.derived_text and any(item.purpose == "continuation" for item in page.derived_text):
        title = f"{title}（续）"
    body_fragments = list(fragments)
    if (
        source_page_title
        and body_fragments
        and body_fragments[0].kind == "heading"
        and _display_text(body_fragments[0].text) == source_page_title
    ):
        body_fragments = body_fragments[1:]
    slide_blocks = _slide_blocks_from_fragments(page, body_fragments)
    mapped_layout = _renderer_layout(page.layout)
    role = page.narrative_role or (first.role if first else "summary")
    return SlideSpec(
        unit_id=page.page_id,
        position=0,
        layout=mapped_layout,
        slide_purpose="appendix" if page.appendix else role,
        eyebrow="补充材料" if page.appendix else _role_label(role),
        title=title,
        key_message="",
        blocks=slide_blocks,
        speaker_notes="",
        section_id=first.section_id if first else None,
        source_section_ids=list(dict.fromkeys(item.section_id for item in fragments)),
        source_block_ids=list(dict.fromkeys(item.block_id for item in fragments)),
        source_keys=[f"block:{item.block_id}" for item in fragments],
        learning_objective_ids=list(dict.fromkeys(
            ref for item in fragments for ref in item.objective_refs
        )),
        knowledge_refs=list(dict.fromkeys(
            ref for item in fragments for ref in item.concept_refs
        )),
        quality={
            "fragment_ids": [item.fragment_id for item in fragments],
            "source_hashes": {item.fragment_id: item.source_hash for item in fragments},
            "appendix": page.appendix,
            "sequence_id": page.sequence_id,
            "step_index": page.step_index,
            "requested_layout": page.layout,
            "narrative_role": page.narrative_role,
            "chapter_id": page.chapter_id,
        },
    )


def _slide_blocks_from_fragments(
    page: PlannedPageV2,
    fragments: list[ContentFragmentV1],
) -> list[SlideBlockSpec]:
    if page.layout == "appendix":
        return [SlideBlockSpec(
            block_id=f"{page.page_id}:appendix-body",
            type="statement",
            content="\n\n".join(
                (
                    f"• {_display_text(fragment.text)}"
                    if fragment.kind == "list_item"
                    else _display_text(fragment.text)
                )
                for fragment in fragments
            ),
            metadata={
                "fragment_ids": [
                    fragment.fragment_id for fragment in fragments
                ],
                "source_hashes": {
                    fragment.fragment_id: fragment.source_hash
                    for fragment in fragments
                },
                "fragment_kind": "appendix_body",
            },
        )]
    result: list[SlideBlockSpec] = []
    pending_items: list[ContentFragmentV1] = []
    pending_prose: list[ContentFragmentV1] = []

    def flush_items() -> None:
        if not pending_items:
            return
        result.append(SlideBlockSpec(
            block_id=f"{page.page_id}:items:{len(result) + 1}",
            type="process" if page.layout in {"process", "timeline", "cycle"} else "bullets",
            items=[_display_text(item.text) for item in pending_items],
            metadata={
                "fragment_ids": [item.fragment_id for item in pending_items],
                "source_hashes": {item.fragment_id: item.source_hash for item in pending_items},
            },
        ))
        pending_items.clear()

    def flush_prose() -> None:
        if not pending_prose:
            return
        result.append(SlideBlockSpec(
            block_id=f"{page.page_id}:prose:{len(result) + 1}",
            type="statement",
            content="\n\n".join(
                _display_text(item.text) for item in pending_prose
            ),
            metadata={
                "fragment_ids": [item.fragment_id for item in pending_prose],
                "source_hashes": {
                    item.fragment_id: item.source_hash for item in pending_prose
                },
                "fragment_kind": "paragraph",
            },
        ))
        pending_prose.clear()

    for fragment in fragments:
        if fragment.kind == "list_item":
            flush_prose()
            if len(_display_text(fragment.text)) <= 72:
                pending_items.append(fragment)
            else:
                flush_items()
                pending_prose.append(fragment)
            continue
        flush_items()
        if fragment.kind in {"heading", "paragraph"}:
            pending_prose.append(fragment)
            continue
        flush_prose()
        block_type = "code" if fragment.kind == "code" else "statement"
        result.append(SlideBlockSpec(
            block_id=f"{page.page_id}:fragment:{fragment.fragment_id}",
            type=block_type,
            content=(
                fragment.text
                if fragment.kind == "code"
                else _display_text(fragment.text)
            ),
            metadata={
                "fragment_ids": [fragment.fragment_id],
                "source_hashes": {fragment.fragment_id: fragment.source_hash},
                "fragment_kind": fragment.kind,
                "formula": fragment.kind == "formula",
            },
        ))
    flush_items()
    flush_prose()
    return result[:6]


def _is_placeholder_title(value: str) -> bool:
    normalized = re.sub(r"[\s:：_-]+", "", value).lower()
    return normalized in {"正文", "内容", "课程内容", "未命名", "body", "content"}


_SUPERSCRIPTS = str.maketrans("0123456789+-=()nijk", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱʲᵏ")
_MATHBB = {
    "R": "ℝ",
    "C": "ℂ",
    "Z": "ℤ",
    "Q": "ℚ",
    "N": "ℕ",
}
_LATEX_SYMBOLS = {
    r"\notin": "∉",
    r"\in": "∈",
    r"\subseteq": "⊆",
    r"\subset": "⊂",
    r"\cup": "∪",
    r"\cap": "∩",
    r"\times": "×",
    r"\cdot": "·",
    r"\leq": "≤",
    r"\geq": "≥",
    r"\neq": "≠",
    r"\rightarrow": "→",
    r"\to": "→",
    r"\forall": "∀",
    r"\exists": "∃",
}


def _display_text(value: str) -> str:
    """Convert source markup to editable audience-facing text without rewriting it."""
    return _plain_text(str(value or ""))


def _renderer_layout(layout: str) -> str:
    mapping = {
        "section-divider": "chapter",
        "objective-cards": "objective",
        "hero-statement": "concept",
        "editorial-body": "concept",
        "two-column": "concept",
        "concept-cards": "concept",
        "timeline": "process",
        "cycle": "process",
        "cause-effect": "process",
        "hierarchy": "concept",
        "knowledge-map": "process",
        "data-highlight": "concept",
        "formula": "concept",
        "case-study": "concept",
        "question": "practice",
        "answer": "practice",
        "summary": "recap",
        "appendix": "appendix",
    }
    return mapping.get(layout, layout)


def _role_label(role: str) -> str:
    return {
        "orientation": "问题导入",
        "objective": "学习目标",
        "concept": "核心概念",
        "reasoning": "推理过程",
        "method": "方法步骤",
        "example": "案例",
        "misconception": "常见误区",
        "application": "应用",
        "activity": "课堂活动",
        "checkpoint": "理解检查",
        "summary": "本节小结",
        "recap": "知识回顾",
        "transfer": "迁移应用",
        "prerequisite": "前置知识",
        "counterexample": "反例",
        "feedback": "反馈",
        "remediation": "补救学习",
    }.get(role, "课程正文")


def validate_slide_deck_v3(
    content: dict[str, Any],
    *,
    course_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base_payload = {
        **content,
        "schema_version": "slide_deck_v3",
    }
    report = validate_slide_deck(base_payload, course_data=course_data)
    issues = list(report.get("issues") or [])
    knowledge_binding_issues = [
        item for item in issues
        if item.get("code") == "knowledge_binding_missing"
    ]
    if knowledge_binding_issues:
        issues = [
            item for item in issues
            if item.get("code") != "knowledge_binding_missing"
        ]
        issues.append({
            "severity": "minor",
            "code": "knowledge_binding_missing",
            "message": (
                f"{len(knowledge_binding_issues)} 页尚未绑定正式知识 ID；"
                "课程块来源已保留，不影响正文覆盖与导出。"
            ),
            "target": "deck",
            "slide_id": "deck",
            "layout": "deck",
            "count": len(knowledge_binding_issues),
            "affected_slide_ids": [
                str(item.get("slide_id") or item.get("target") or "")
                for item in knowledge_binding_issues[:50]
            ],
        })
    for issue in issues:
        if issue.get("code") == "formal_practice_not_represented":
            issue["message"] = (
                f"{int(issue.get('count') or 0)} 个小节的正式题目尚未进入"
                "当前授课主线。"
            )
            issue["suggestion"] = (
                "可按章节拆分课件并补充练习页；正文覆盖与当前导出不受影响。"
            )
    coverage = content.get("coverage_report") or {}
    mode = str(content.get("mode") or "")
    if not coverage.get("hash_integrity_passed"):
        issues.append({
            "severity": "critical",
            "code": "fragment_hash_mismatch",
            "message": "页面正文与课程源片段哈希不一致。",
            "target": "deck",
        })
    required_ratio = (
        float(coverage.get("visible_coverage_ratio") or 0)
        if mode in {"full", "teaching"}
        else float(coverage.get("decision_coverage_ratio") or 0)
    )
    if required_ratio != 1.0:
        issues.append({
            "severity": "critical",
            "code": "source_coverage_incomplete",
            "message": "课程正文片段尚未全部分配或明确排除。",
            "target": "deck",
        })
    if mode == "concise" and int(coverage.get("excluded_fragment_count") or 0) != len(content.get("exclusions") or []):
        issues.append({
            "severity": "critical",
            "code": "concise_exclusion_manifest_incomplete",
            "message": "精简模式的排除清单不完整。",
            "target": "deck",
        })
    visual_gate = content.get("visual_quality_report") or {}
    if content.get("visual_plan"):
        issues.extend(
            item
            for item in visual_gate.get("issues") or []
            if item not in issues
        )
        for slide in content.get("slides") or []:
            if not str(slide.get("teaching_job") or "").strip():
                issues.append({
                    "severity": "critical",
                    "code": "teaching_job_missing",
                    "slide_id": str(slide.get("unit_id") or ""),
                })
            if not str(slide.get("takeaway") or "").strip():
                issues.append({
                    "severity": "critical",
                    "code": "takeaway_missing",
                    "slide_id": str(slide.get("unit_id") or ""),
                })
        issues.extend(visual_integrity_issues(content))
    semantic_codes = {
        str(item.get("code") or "")
        for item in report.get("semantic", {}).get("issues", [])
    }
    semantic_codes.add("knowledge_binding_missing")
    semantic_issues = [
        item for item in issues
        if (
            str(item.get("code") or "") in semantic_codes
            or str(item.get("code") or "").startswith(
                ("fragment_", "source_", "concise_")
            )
        )
    ]
    visual_issues = [item for item in issues if item not in semantic_issues]
    passed = not any(item.get("severity") == "critical" for item in issues)
    score = max(0, 100 - sum(
        {"critical": 20, "major": 5, "minor": 1}.get(
            str(item.get("severity") or ""),
            1,
        )
        for item in issues
    ))
    return {
        **report,
        "passed": passed,
        "score": score,
        "issues": issues,
        "blockers": [item for item in issues if item.get("severity") == "critical"],
        "warnings": [item for item in issues if item.get("severity") != "critical"],
        "semantic": {"passed": not any(item.get("severity") == "critical" for item in semantic_issues), "issues": semantic_issues},
        "visual": {"passed": not any(item.get("severity") == "critical" for item in visual_issues), "issues": visual_issues},
        "coverage": coverage,
    }


__all__ = [
    "ContentFragmentV1",
    "LEGACY_THEME_ALIASES",
    "SLIDE_DECK_MODES",
    "SLIDE_DECK_THEMES",
    "SLIDE_DECK_V3_COMPILER_VERSION",
    "SLIDE_DECK_V3_SCHEMA",
    "SlideAllocationPlanV2",
    "SlideDeckMode",
    "SlideDeckTheme",
    "V3_LAYOUTS",
    "compile_slide_deck_v3",
    "deterministic_slide_allocation",
    "fragment_course_document",
    "normalize_slide_deck_theme",
    "plan_slide_deck_v3",
    "slide_deck_variant_key",
    "validate_allocation_plan",
    "validate_slide_deck_v3",
]
