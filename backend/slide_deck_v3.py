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
from slide_deck import SlideBlockSpec, SlideSpec, slide_quality, validate_slide_deck

SLIDE_DECK_V3_SCHEMA = "slide_deck_v3"
SLIDE_DECK_V3_COMPILER_VERSION = "source_first_slide_compiler_v1"

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
    "qizhi-classroom": 560,
    "academic-editorial": 680,
    "grid-notebook": 520,
    "modern-geometric": 430,
    "dark-tech": 500,
}


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ContentFragmentV1(_StrictModel):
    fragment_id: str
    section_id: str
    block_id: str
    kind: Literal["heading", "paragraph", "list_item", "code", "formula", "table"]
    text: str
    ordinal: int = Field(ge=0)
    source_hash: str
    role: str
    source_kind: str
    objective_refs: list[str] = Field(default_factory=list)
    concept_refs: list[str] = Field(default_factory=list)


class DerivedTextV1(_StrictModel):
    text: str = Field(min_length=1, max_length=160)
    purpose: Literal["navigation", "section_label", "continuation", "appendix_label"]
    derived_from: list[str] = Field(default_factory=list)


class PlannedPageV2(_StrictModel):
    page_id: str
    layout: str
    fragment_ids: list[str] = Field(default_factory=list, max_length=8)
    appendix: bool = False
    sequence_id: str = ""
    step_index: int = Field(default=0, ge=0)
    derived_text: list[DerivedTextV1] = Field(default_factory=list, max_length=10)


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
    ordinal = 0
    for block in sorted(document.blocks, key=lambda item: (
        sections.get(item.section_id).position if sections.get(item.section_id) else 10**9,
        item.position,
        item.block_id,
    )):
        if block.status == "retired":
            continue
        units = _fragment_block(block)
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
                objective_refs=list(block.objective_refs),
                concept_refs=list(block.concept_refs),
            ))
            ordinal += 1
    return fragments


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
    return bool(re.search(r"(?:\$\$?|\\\(|\\\[|\\frac|\\sum|\\int|\\sqrt)", value))


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
    pages: list[PlannedPageV2] = [
        PlannedPageV2(
            page_id="slide:title",
            layout="cover",
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
                for section in sorted(document.sections, key=lambda item: item.position)
                if any(fragment.section_id == section.section_id for fragment in included)
            ][:10],
        ),
    ]
    grouped: dict[tuple[str, str], list[ContentFragmentV1]] = {}
    for fragment in included:
        grouped.setdefault((fragment.section_id, fragment.block_id), []).append(fragment)
    for (section_id, block_id), block_fragments in grouped.items():
        appendix = mode == "teaching" and block_fragments[0].role in _APPENDIX_ROLES
        chunks = _paginate_fragments(block_fragments, capacity)
        for chunk_index, chunk in enumerate(chunks):
            page_id = f"slide:{block_id}:{chunk_index + 1}"
            layout = "appendix" if appendix else _layout_for_fragments(chunk)
            derived = []
            if chunk_index:
                derived.append(DerivedTextV1(
                    text="续",
                    purpose="continuation",
                    derived_from=[item.fragment_id for item in chunk],
                ))
            allocated_page = PlannedPageV2(
                page_id=page_id,
                layout=layout,
                fragment_ids=[item.fragment_id for item in chunk],
                appendix=appendix,
                derived_text=derived,
            )
            pages.extend(_expand_reveal_pages(allocated_page, chunk))

    non_appendix = [page for page in pages if not page.appendix]
    appendix_pages = [page for page in pages if page.appendix]
    if appendix_pages:
        appendix_ids = [fragment_id for page in appendix_pages for fragment_id in page.fragment_ids]
        non_appendix.append(PlannedPageV2(
            page_id="slide:appendix-divider",
            layout="section-divider",
            appendix=True,
            derived_text=[DerivedTextV1(
                text="补充材料",
                purpose="appendix_label",
                derived_from=appendix_ids,
            )],
        ))
    pages = non_appendix + appendix_pages
    pages.append(PlannedPageV2(
        page_id="slide:summary",
        layout="summary",
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
) -> list[list[ContentFragmentV1]]:
    pages: list[list[ContentFragmentV1]] = []
    current: list[ContentFragmentV1] = []
    current_size = 0
    for fragment in fragments:
        size = len(fragment.text)
        fragment_capacity = capacity * (2 if fragment.kind == "code" else 1)
        if current and (
            current_size + size > min(capacity, fragment_capacity)
            or len(current) >= 6
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


def _layout_for_fragments(fragments: list[ContentFragmentV1]) -> str:
    kinds = {item.kind for item in fragments}
    role = fragments[0].role if fragments else "concept"
    if "code" in kinds:
        return "code"
    if "formula" in kinds:
        return "formula"
    if role == "objective":
        return "objective-cards"
    if role in {"example", "application"}:
        return "case-study"
    if role == "misconception":
        return "misconception"
    if role in {"checkpoint", "activity"}:
        return "question"
    if role in {"reasoning", "process"} or len([item for item in fragments if item.kind == "list_item"]) >= 3:
        return "process"
    if role == "summary":
        return "summary"
    if len(fragments) >= 4:
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
    ordered = [catalog[fragment_id].ordinal for fragment_id in referenced]
    if ordered != sorted(ordered):
        raise ValueError("Slide allocation changes source fragment order")
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
    sequence_groups: dict[str, list[PlannedPageV2]] = {}
    for page in plan.pages:
        if page.sequence_id:
            sequence_groups.setdefault(page.sequence_id, []).append(page)
    sequence_fragments: dict[str, list[str]] = {}
    for sequence_id, pages in sequence_groups.items():
        ordered = sorted(pages, key=lambda item: item.step_index)
        if [item.step_index for item in ordered] != list(range(1, len(ordered) + 1)):
            raise ValueError(f"Reveal sequence '{sequence_id}' has invalid step indexes")
        positions = sorted(plan.pages.index(item) for item in pages)
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
    for page in plan.pages:
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
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
    resume_slides: list[dict[str, Any]] | None = None,
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
            if progress_callback:
                progress_callback({
                    "event": "slide_upsert",
                    "progress": min(92, 10 + round(((page_index + 1) / max(1, len(plan.pages))) * 82)),
                    "slide": slide.model_dump(mode="json"),
                })
        else:
            slide.position = page_index
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
        "slides": [item.model_dump(mode="json") for item in slides],
        "coverage_report": coverage,
        "exclusions": [item.model_dump(mode="json") for item in plan.exclusions],
        "presentation_overrides": {},
        "override_conflicts": [],
    }
    quality = validate_slide_deck_v3(content, course_data=course_data)
    content["quality_report"] = deepcopy(quality)
    content["quality_summary"] = {
        "passed": quality["passed"],
        "score": quality["score"],
        "semantic_issue_count": len(quality["semantic"]["issues"]),
        "visual_issue_count": len(quality["visual"]["issues"]),
        "coverage_ratio": coverage["visible_coverage_ratio"],
    }
    if progress_callback:
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
        labels = [item.text for item in page.derived_text]
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
        return SlideSpec(
            unit_id=page.page_id,
            position=0,
            layout="recap",
            slide_purpose="course_recap",
            eyebrow="课程回顾",
            title="回到课程目标",
            blocks=[],
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

    first = fragments[0] if fragments else None
    section = sections.get(first.section_id if first else "")
    block = blocks.get(first.block_id if first else "")
    title = str((block.payload or {}).get("title") or (section.title if section else "课程内容"))
    if page.derived_text and any(item.purpose == "continuation" for item in page.derived_text):
        title = f"{title}（续）"
    slide_blocks = _slide_blocks_from_fragments(page, fragments)
    mapped_layout = _renderer_layout(page.layout)
    role = first.role if first else "summary"
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
        },
    )


def _slide_blocks_from_fragments(
    page: PlannedPageV2,
    fragments: list[ContentFragmentV1],
) -> list[SlideBlockSpec]:
    result: list[SlideBlockSpec] = []
    pending_items: list[ContentFragmentV1] = []

    def flush_items() -> None:
        if not pending_items:
            return
        result.append(SlideBlockSpec(
            block_id=f"{page.page_id}:items:{len(result) + 1}",
            type="process" if page.layout in {"process", "timeline", "cycle"} else "bullets",
            items=[item.text for item in pending_items],
            metadata={
                "fragment_ids": [item.fragment_id for item in pending_items],
                "source_hashes": {item.fragment_id: item.source_hash for item in pending_items},
            },
        ))
        pending_items.clear()

    for fragment in fragments:
        if fragment.kind == "list_item":
            pending_items.append(fragment)
            continue
        flush_items()
        block_type = "code" if fragment.kind == "code" else "statement"
        result.append(SlideBlockSpec(
            block_id=f"{page.page_id}:fragment:{fragment.fragment_id}",
            type=block_type,
            content=fragment.text,
            metadata={
                "fragment_ids": [fragment.fragment_id],
                "source_hashes": {fragment.fragment_id: fragment.source_hash},
                "fragment_kind": fragment.kind,
                "formula": fragment.kind == "formula",
            },
        ))
    flush_items()
    return result[:6]


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
        "appendix": "concept",
    }
    return mapping.get(layout, layout)


def _role_label(role: str) -> str:
    return {
        "objective": "学习目标",
        "concept": "核心概念",
        "reasoning": "推理过程",
        "example": "案例",
        "misconception": "常见误区",
        "application": "应用",
        "activity": "课堂活动",
        "checkpoint": "理解检查",
        "summary": "本节小结",
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
    semantic_issues = [
        item for item in issues
        if str(item.get("code") or "").startswith(("fragment_", "source_", "concise_"))
    ]
    visual_issues = [item for item in issues if item not in semantic_issues]
    passed = not any(item.get("severity") == "critical" for item in issues)
    return {
        **report,
        "passed": passed,
        "score": max(0, 100 - sum(20 if item.get("severity") == "critical" else 5 for item in issues)),
        "issues": issues,
        "blockers": [item for item in issues if item.get("severity") == "critical"],
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
