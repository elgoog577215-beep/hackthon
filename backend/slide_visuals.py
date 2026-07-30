"""Grounded teaching narrative and visual direction for source-first slide decks."""

from __future__ import annotations

import asyncio
import inspect
import os
import re
from collections import Counter, defaultdict
from collections.abc import Awaitable, Callable
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from course_document import CourseDocument, stable_hash
from slide_rule_diagrams import RULE_DIAGRAM_TEMPLATES, parse_mermaid_rule_diagram
from teaching_storyboard import (
    TEACHING_STORYBOARD_POLICY_VERSION,
    build_teaching_storyboard,
    storyboard_page_index,
)

SLIDE_VISUAL_PLAN_SCHEMA = "slide_visual_plan_v1"
SLIDE_VISUAL_POLICY_VERSION = "visual_director_v5_source_grounded_rules"

VisualKind = Literal[
    "source_image",
    "generated_illustration",
    "rule_diagram",
    "relational_diagram",
    "coordinate_plot",
    "chart",
    "table",
    "formula",
    "code",
    "none",
]
VisualPurpose = Literal[
    "structure",
    "process",
    "comparison",
    "evidence",
    "application",
    "context",
    "exercise",
]
SlideComposition = Literal[
    "statement",
    "figure-first",
    "split-visual",
    "diagram-full",
    "comparison",
    "process",
    "exercise",
    "appendix",
]

_VISUAL_KINDS = {
    "source_image",
    "generated_illustration",
    "rule_diagram",
    "relational_diagram",
    "coordinate_plot",
    "chart",
    "table",
    "formula",
    "code",
    "none",
}
_NAVIGATION_LAYOUTS = {"cover", "roadmap", "section-divider", "summary"}
_NUMBER_RE = re.compile(r"\d+")
_COORDINATE_PAIR_RE = re.compile(
    r"(?P<label>[\(（]\s*(?P<x>-?\d+(?:\.\d+)?)\s*[,，]\s*"
    r"(?P<y>-?\d+(?:\.\d+)?)\s*[\)）])"
)
_RAW_MERMAID_RE = re.compile(
    r"(?im)^\s*(?:graph\s+(?:TD|TB|BT|LR|RL)\b|flowchart\b|"
    r"sequenceDiagram\b|classDiagram\b|stateDiagram(?:-v2)?\b|erDiagram\b)"
)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VisualNodeV1(_StrictModel):
    node_id: str
    label: str = Field(min_length=1, max_length=80)
    source_fragment_ids: list[str] = Field(default_factory=list, min_length=1)
    emphasis: Literal["primary", "secondary", "muted"] = "secondary"


class VisualEdgeV1(_StrictModel):
    source: str
    target: str
    label: str = Field(default="", max_length=40)
    relation: Literal[
        "sequence",
        "supports",
        "contrasts",
        "causes",
        "contains",
        "maps_to",
    ] = "sequence"


class VisualAnchorV1(_StrictModel):
    visual_id: str
    kind: VisualKind
    purpose: VisualPurpose
    source_fragment_ids: list[str] = Field(default_factory=list)
    alt_text: str = Field(default="", max_length=240)
    asset_id: str = ""
    nodes: list[VisualNodeV1] = Field(default_factory=list, max_length=8)
    edges: list[VisualEdgeV1] = Field(default_factory=list, max_length=12)
    parameters: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_shape(self) -> "VisualAnchorV1":
        if self.kind not in _VISUAL_KINDS:
            raise ValueError("unknown visual type")
        if self.kind == "none":
            if self.nodes or self.edges or self.asset_id:
                raise ValueError("A none visual cannot contain rendered payload")
            return self
        if not self.source_fragment_ids:
            raise ValueError("A meaningful visual must bind source fragments")
        if not self.alt_text:
            raise ValueError("A meaningful visual must have alt text")
        if self.kind in {"relational_diagram", "rule_diagram"}:
            if len(self.nodes) < 2 or not self.edges:
                raise ValueError(
                    "A diagram needs at least two nodes and one edge"
                )
            if not self.parameters.get("relation_evidence"):
                raise ValueError(
                    "A diagram needs explicit structural evidence"
                )
        if self.kind == "rule_diagram":
            if self.parameters.get("template") not in RULE_DIAGRAM_TEMPLATES:
                raise ValueError("A rule diagram needs an allow-listed template")
        if self.kind == "coordinate_plot":
            points = self.parameters.get("points") or []
            labels = self.parameters.get("point_labels") or []
            if len(points) < 2 or len(labels) != len(points):
                raise ValueError("A coordinate plot needs at least two labeled source points")
            if not all(
                isinstance(point, list)
                and len(point) == 2
                and all(isinstance(value, (int, float)) for value in point)
                for point in points
            ):
                raise ValueError("Coordinate plot points must be numeric pairs")
        if self.kind == "formula" and not str(self.parameters.get("formula") or "").strip():
            raise ValueError("A formula visual must retain the source formula")
        if self.kind in {"source_image", "generated_illustration"} and not (
            self.asset_id or self.parameters.get("asset_ref") or self.parameters.get("prompt")
        ):
            raise ValueError("An image visual needs an asset reference or prompt")
        return self


class SlideVisualPlanPageV1(_StrictModel):
    page_id: str
    teaching_job: str = Field(min_length=1, max_length=180)
    takeaway: str = Field(min_length=1, max_length=160)
    takeaway_source_fragment_ids: list[str] = Field(default_factory=list)
    transition_from: str = Field(default="", max_length=180)
    composition: SlideComposition
    visual_anchor: VisualAnchorV1
    role_layout_variant: Literal["primary", "alternate", "dense"] = "primary"
    chapter_id: str = ""
    appendix: bool = False
    episode_id: str = ""
    episode_title: str = ""
    learning_question: str = ""
    beat_role: str = ""
    beat_index: int = Field(default=0, ge=0)


class SlideVisualPlanV1(_StrictModel):
    schema_version: Literal["slide_visual_plan_v1"] = SLIDE_VISUAL_PLAN_SCHEMA
    policy_version: str = SLIDE_VISUAL_POLICY_VERSION
    source_document_revision: str
    mode: Literal["full", "teaching", "concise"]
    theme: str
    variant_key: str
    deck_brief: dict[str, Any] = Field(default_factory=dict)
    pages: list[SlideVisualPlanPageV1]

    @model_validator(mode="after")
    def validate_pages(self) -> "SlideVisualPlanV1":
        page_ids = [page.page_id for page in self.pages]
        if len(page_ids) != len(set(page_ids)):
            raise ValueError("Visual plan page IDs must be unique")
        return self


def deterministic_visual_plan(
    document: CourseDocument,
    allocation_plan: Any,
    fragments: list[Any],
) -> SlideVisualPlanV1:
    """Build a source-grounded visual plan without requiring a model or image API."""
    catalog = {item.fragment_id: item for item in fragments}
    storyboard = build_teaching_storyboard(document, allocation_plan)
    episode_pages = storyboard_page_index(storyboard)
    pages: list[SlideVisualPlanPageV1] = []
    prior_takeaway = ""
    content_index = 0
    for page in allocation_plan.pages:
        page_fragments = [
            catalog[fragment_id]
            for fragment_id in page.fragment_ids
            if fragment_id in catalog
        ]
        is_navigation = page.layout in _NAVIGATION_LAYOUTS and not page_fragments
        takeaway, takeaway_ids = _takeaway(page, page_fragments, document.title)
        teaching_job = _teaching_job(page, takeaway)
        transition = (
            ""
            if not pages
            else _transition_text(page, prior_takeaway, takeaway)
        )
        if page.appendix:
            anchor = _none_anchor(page.page_id, "evidence")
            composition: SlideComposition = "appendix"
        elif is_navigation:
            anchor = _none_anchor(page.page_id, "structure")
            composition = "statement"
        else:
            anchor = _visual_anchor(page, page_fragments, content_index)
            composition = _composition_for(page, anchor, content_index)
            content_index += 1
        episode, beat = episode_pages.get(page.page_id, (None, None))
        pages.append(SlideVisualPlanPageV1(
            page_id=page.page_id,
            teaching_job=teaching_job,
            takeaway=takeaway,
            takeaway_source_fragment_ids=takeaway_ids,
            transition_from=transition,
            composition=composition,
            visual_anchor=anchor,
            role_layout_variant=("primary", "alternate", "dense")[content_index % 3],
            chapter_id=str(getattr(page, "chapter_id", "") or ""),
            appendix=bool(page.appendix),
            episode_id=episode.episode_id if episode else "",
            episode_title=episode.title if episode else "",
            learning_question=episode.learning_question if episode else "",
            beat_role=beat.role if beat else "",
            beat_index=beat.beat_index if beat else 0,
        ))
        prior_takeaway = takeaway
    rebalance_visual_plan_pages(pages, allocation_plan, fragments)
    plan = SlideVisualPlanV1(
        source_document_revision=document.document_revision,
        mode=allocation_plan.mode,
        theme=allocation_plan.theme,
        variant_key=allocation_plan.variant_key,
        deck_brief={
            "communication_job": storyboard.communication_job,
            "audience": storyboard.audience,
            "narrative_arc": [
                "导入",
                "概念",
                "原理",
                "方法",
                "案例",
                "检查",
                "回顾",
            ],
            "content_policy": "source_fragments_only",
            "storyboard_policy_version": TEACHING_STORYBOARD_POLICY_VERSION,
            "storyboard": storyboard.model_dump(mode="json"),
        },
        pages=pages,
    )
    validate_visual_plan(plan, allocation_plan, fragments)
    return plan


def _rebalance_compositions(pages: list[SlideVisualPlanPageV1]) -> None:
    """Keep visual rhythm deterministic even across repeated exercises/formulas."""
    alternatives: list[SlideComposition] = [
        "figure-first",
        "split-visual",
        "diagram-full",
        "comparison",
        "process",
        "exercise",
        "statement",
    ]
    eligible = [
        page
        for page in pages
        if not page.appendix and page.visual_anchor.kind != "none"
    ]
    previous: SlideComposition | str = ""
    run = 0
    for index, page in enumerate(eligible):
        if page.composition == previous:
            run += 1
        else:
            previous = page.composition
            run = 1
        if run <= 2:
            continue
        replacement = next(
            candidate
            for candidate in alternatives
            if candidate != page.composition
            and (index == 0 or candidate != eligible[index - 1].composition)
        )
        page.composition = replacement
        previous = replacement
        run = 1

    chapters: dict[str, list[SlideVisualPlanPageV1]] = defaultdict(list)
    for page in eligible:
        if page.chapter_id:
            chapters[page.chapter_id].append(page)
    for chapter_pages in chapters.values():
        if len(chapter_pages) < 4:
            continue
        maximum = max(1, int(len(chapter_pages) * 0.35))
        while True:
            counts = Counter(page.composition for page in chapter_pages)
            overused = next(
                (
                    composition
                    for composition, count in counts.most_common()
                    if count > maximum
                ),
                None,
            )
            if overused is None:
                break
            changed = False
            for index in range(len(chapter_pages) - 1, -1, -1):
                page = chapter_pages[index]
                if page.composition != overused:
                    continue
                replacement = next(
                    (
                        candidate
                        for candidate in alternatives
                        if (
                            candidate != overused
                            and counts[candidate] < maximum
                            and (
                                index == 0
                                or chapter_pages[index - 1].composition != candidate
                            )
                            and (
                                index == len(chapter_pages) - 1
                                or chapter_pages[index + 1].composition != candidate
                            )
                        )
                    ),
                    None,
                )
                if replacement is None:
                    continue
                page.composition = replacement
                changed = True
                break
            if not changed:
                break

    # The share repair above can create a new three-page run when pages that
    # are outside the gate subset sit between eligible pages. Repair the
    # rendered sequence without pushing any gated composition over 35%.
    eligible_ids = {page.page_id for page in eligible}
    chapter_counts = {
        chapter_id: Counter(page.composition for page in chapter_pages)
        for chapter_id, chapter_pages in chapters.items()
    }
    chapter_maximum = {
        chapter_id: max(1, int(len(chapter_pages) * 0.35))
        for chapter_id, chapter_pages in chapters.items()
    }
    visual_pages = [
        page for page in pages
        if not page.appendix and page.visual_anchor.kind != "none"
    ]
    previous: SlideComposition | str = ""
    run = 0
    for index, page in enumerate(visual_pages):
        if page.composition == previous:
            run += 1
        else:
            previous = page.composition
            run = 1
        if run <= 2:
            continue
        counts = chapter_counts.get(page.chapter_id, Counter())
        maximum = chapter_maximum.get(page.chapter_id, len(visual_pages))
        replacement = next(
            (
                candidate
                for candidate in alternatives
                if (
                    candidate != page.composition
                    and (
                        page.page_id not in eligible_ids
                        or counts[candidate] < maximum
                    )
                    and candidate != visual_pages[index - 1].composition
                    and (
                        index == len(visual_pages) - 1
                        or candidate != visual_pages[index + 1].composition
                    )
                )
            ),
            None,
        )
        if replacement is None:
            continue
        if page.page_id in eligible_ids:
            counts[page.composition] -= 1
            counts[replacement] += 1
        page.composition = replacement
        previous = replacement
        run = 1

    # Chapter-level balancing can create a new local repetition.  Repair the
    # final sequence once more so the rendered rhythm matches the report.
    previous = ""
    run = 0
    for index, page in enumerate(eligible):
        if page.composition == previous:
            run += 1
        else:
            previous = page.composition
            run = 1
        if run <= 2:
            continue
        replacement = next(
            candidate
            for candidate in alternatives
            if (
                candidate != page.composition
                and (index == 0 or candidate != eligible[index - 1].composition)
                and (
                    index == len(eligible) - 1
                    or candidate != eligible[index + 1].composition
                )
            )
        )
        page.composition = replacement
        previous = replacement
        run = 1


def rebalance_visual_plan_pages(
    pages: list[SlideVisualPlanPageV1],
    allocation_plan: Any,
    fragments: list[Any],
) -> None:
    """Reapply rhythm after optional assets degrade into deterministic visuals."""
    _rebalance_visual_kind_runs(pages, allocation_plan, fragments)
    _rebalance_compositions(pages)
    _rebalance_quality_eligible_compositions(
        pages,
        allocation_plan,
        fragments,
    )


def _rebalance_visual_kind_runs(
    pages: list[SlideVisualPlanPageV1],
    allocation_plan: Any,
    fragments: list[Any],
) -> None:
    """Break visual-kind runs using a deterministic, source-bound alternate."""
    allocation_by_id = {
        page.page_id: page for page in allocation_plan.pages
    }
    fragment_by_id = {
        str(fragment.fragment_id): fragment
        for fragment in fragments
    }
    fragment_text = {
        fragment_id: str(fragment.text or "")
        for fragment_id, fragment in fragment_by_id.items()
    }
    fragment_kind = {
        fragment_id: str(fragment.kind or "")
        for fragment_id, fragment in fragment_by_id.items()
    }
    eligible = [
        page
        for page in pages
        if (
            not page.appendix
            and page.page_id in allocation_by_id
            and allocation_by_id[page.page_id].fragment_ids
            and allocation_by_id[page.page_id].layout != "section-divider"
            and (
                str(getattr(
                    allocation_by_id[page.page_id],
                    "narrative_role",
                    "",
                )) in {"method", "example", "misconception"}
                or page.visual_anchor.kind != "none"
                or any(
                    fragment_kind.get(fragment_id)
                    in {"formula", "code", "table", "image", "diagram"}
                    for fragment_id in allocation_by_id[page.page_id].fragment_ids
                )
            )
            and str(getattr(
                allocation_by_id[page.page_id],
                "narrative_role",
                "",
            )) != "checkpoint"
        )
    ]
    previous_kind = ""
    kind_run = 0
    for page in eligible:
        anchor = page.visual_anchor
        kind = anchor.kind
        if kind == previous_kind:
            kind_run += 1
        else:
            previous_kind = kind
            kind_run = 1
        maximum_kind_run = 5 if kind in {"formula", "code"} else 3
        if kind == "none" or kind_run <= maximum_kind_run:
            continue
        if kind != "table" and anchor.source_fragment_ids:
            labels = [
                node.label
                for node in anchor.nodes
                if str(node.label or "").strip()
            ]
            if not labels:
                labels = [
                    _trim_takeaway(
                        fragment_text.get(fragment_id, ""),
                        60,
                    )
                    for fragment_id in anchor.source_fragment_ids
                    if _trim_takeaway(
                        fragment_text.get(fragment_id, ""),
                        60,
                    )
                ]
            page.visual_anchor = VisualAnchorV1(
                visual_id=stable_hash(
                    {"page_id": page.page_id, "kind": "table"},
                    prefix="sv_",
                ),
                kind="table",
                purpose=anchor.purpose,
                source_fragment_ids=list(anchor.source_fragment_ids),
                alt_text=anchor.alt_text,
                parameters={
                    "headers": ["顺序", "课程原文要点"],
                    "rows": [
                        [str(index + 1), label]
                        for index, label in enumerate(labels[:6])
                    ],
                    "information_gain_score": 0.7,
                    "source_bound": True,
                },
            )
            page.composition = "split-visual"
            previous_kind = "table"
        else:
            page.visual_anchor = _none_anchor(page.page_id, anchor.purpose)
            page.composition = "statement"
            previous_kind = "none"
        kind_run = 1


def _rebalance_quality_eligible_compositions(
    pages: list[SlideVisualPlanPageV1],
    allocation_plan: Any,
    fragments: list[Any],
) -> None:
    """Apply the 35% rhythm contract to the same subset used by the gate."""
    allocation_by_id = {
        page.page_id: page for page in allocation_plan.pages
    }
    fragment_kind = {
        str(fragment.fragment_id): str(fragment.kind)
        for fragment in fragments
    }
    eligible = [
        page
        for page in pages
        if (
            not page.appendix
            and page.page_id in allocation_by_id
            and allocation_by_id[page.page_id].fragment_ids
            and allocation_by_id[page.page_id].layout != "section-divider"
            and (
                str(getattr(
                    allocation_by_id[page.page_id],
                    "narrative_role",
                    "",
                )) in {"method", "example", "misconception"}
                or page.visual_anchor.kind != "none"
                or any(
                    fragment_kind.get(fragment_id)
                    in {"formula", "code", "table", "image", "diagram"}
                    for fragment_id in allocation_by_id[page.page_id].fragment_ids
                )
            )
            and str(getattr(
                allocation_by_id[page.page_id],
                "narrative_role",
                "",
            )) != "checkpoint"
        )
    ]
    alternatives: list[SlideComposition] = [
        "figure-first",
        "split-visual",
        "diagram-full",
        "comparison",
        "process",
        "exercise",
        "statement",
    ]
    chapters: dict[str, list[SlideVisualPlanPageV1]] = defaultdict(list)
    for page in eligible:
        if page.chapter_id:
            chapters[page.chapter_id].append(page)
    for chapter_pages in chapters.values():
        if len(chapter_pages) < 4:
            continue
        maximum = max(1, int(len(chapter_pages) * 0.35))
        for _ in range(len(chapter_pages) * 2):
            counts = Counter(page.composition for page in chapter_pages)
            overused = next(
                (
                    composition
                    for composition, count in counts.most_common()
                    if count > maximum
                ),
                None,
            )
            if overused is None:
                break
            changed = False
            for index in range(len(chapter_pages) - 1, -1, -1):
                page = chapter_pages[index]
                if page.composition != overused:
                    continue
                replacement = next(
                    (
                        candidate
                        for candidate in alternatives
                        if (
                            candidate != overused
                            and counts[candidate] < maximum
                            and (
                                index == 0
                                or chapter_pages[index - 1].composition != candidate
                            )
                            and (
                                index == len(chapter_pages) - 1
                                or chapter_pages[index + 1].composition != candidate
                            )
                        )
                    ),
                    None,
                )
                if replacement is not None:
                    page.composition = replacement
                    changed = True
                    break
            if not changed:
                break


async def plan_slide_visuals(
    document: CourseDocument,
    allocation_plan: Any,
    fragments: list[Any],
    *,
    ai_planner: Callable[
        [dict[str, Any]],
        Awaitable[dict[str, Any]] | dict[str, Any],
    ] | None = None,
    timeout_seconds: float = 12.0,
) -> SlideVisualPlanV1:
    """Accept a strict source-bound AI plan or return the deterministic director."""
    fallback = deterministic_visual_plan(document, allocation_plan, fragments)
    if ai_planner is None:
        fallback.deck_brief["planner"] = "deterministic_fallback"
        fallback.deck_brief["fallback_reason"] = "no_ai_visual_planner"
        return fallback
    raster_generation_enabled = os.getenv(
        "SLIDE_GENERATED_ILLUSTRATIONS_ENABLED",
        "",
    ).strip().lower() in {"1", "true", "yes", "on"}
    allowed_visual_kinds = set(_VISUAL_KINDS)
    if not raster_generation_enabled:
        allowed_visual_kinds.discard("generated_illustration")
    request = {
        "schema_version": "slide_visual_plan_request_v1",
        "source_document_revision": document.document_revision,
        "mode": allocation_plan.mode,
        "theme": allocation_plan.theme,
        "variant_key": allocation_plan.variant_key,
        "rules": {
            "body_text_forbidden": True,
            "unknown_fragment_ids_forbidden": True,
            "takeaway_must_be_source_grounded": True,
            "visual_labels_must_be_source_excerpts": True,
            "arbitrary_drawing_code_forbidden": True,
            "uncertain_visual_must_be_none": True,
            "generated_images_may_not_contain_text_or_logos": True,
            "raster_generation_default": (
                "enabled" if raster_generation_enabled else "disabled"
            ),
        },
        "allowed_visual_kinds": sorted(allowed_visual_kinds),
        "allowed_rule_diagram_templates": sorted(RULE_DIAGRAM_TEMPLATES),
        "pages": [
            {
                "page_id": page.page_id,
                "layout": page.layout,
                "narrative_role": page.narrative_role,
                "appendix": page.appendix,
                "chapter_id": page.chapter_id,
                "fragments": [
                    {
                        "fragment_id": fragment.fragment_id,
                        "kind": fragment.kind,
                        "language": str(getattr(fragment, "language", "") or ""),
                        "text": fragment.text,
                    }
                    for fragment in fragments
                    if fragment.fragment_id in page.fragment_ids
                ],
            }
            for page in allocation_plan.pages
        ],
    }
    try:
        if inspect.iscoroutinefunction(ai_planner):
            raw = await asyncio.wait_for(ai_planner(request), timeout=timeout_seconds)
        else:
            result = await asyncio.wait_for(
                asyncio.to_thread(ai_planner, request),
                timeout=timeout_seconds,
            )
            raw = await result if inspect.isawaitable(result) else result
        candidate = SlideVisualPlanV1.model_validate(raw)
        validate_visual_plan(candidate, allocation_plan, fragments)
        candidate.deck_brief["planner"] = "ai"
        return candidate
    except Exception:
        fallback.deck_brief["planner"] = "deterministic_fallback"
        fallback.deck_brief["fallback_reason"] = "invalid_or_failed_ai_visual_plan"
        return fallback


def validate_visual_plan(
    visual_plan: SlideVisualPlanV1,
    allocation_plan: Any,
    fragments: list[Any],
) -> dict[str, Any]:
    """Reject unknown bindings, fabricated numbers, and invalid visual topology."""
    fragment_ids = {item.fragment_id for item in fragments}
    fragment_text = {item.fragment_id: str(item.text) for item in fragments}
    allocation_pages = {page.page_id: page for page in allocation_plan.pages}
    if visual_plan.source_document_revision != allocation_plan.source_document_revision:
        raise ValueError("Visual plan source revision is stale")
    if visual_plan.variant_key != allocation_plan.variant_key:
        raise ValueError("Visual plan variant does not match allocation")
    if set(page.page_id for page in visual_plan.pages) != set(allocation_pages):
        raise ValueError("Visual plan pages do not match allocation pages")

    for page in visual_plan.pages:
        allocated = set(allocation_pages[page.page_id].fragment_ids)
        referenced = set(page.takeaway_source_fragment_ids)
        referenced.update(page.visual_anchor.source_fragment_ids)
        for node in page.visual_anchor.nodes:
            referenced.update(node.source_fragment_ids)
        unknown = referenced - fragment_ids
        if unknown:
            raise ValueError(f"Visual plan references unknown fragment: {sorted(unknown)[0]}")
        escaped = referenced - allocated
        if escaped:
            raise ValueError(
                f"Visual plan references a fragment outside page allocation: {sorted(escaped)[0]}"
            )
        if page.takeaway_source_fragment_ids:
            grounded = "\n".join(
                fragment_text[item]
                for item in page.takeaway_source_fragment_ids
            )
            source_numbers = set(_NUMBER_RE.findall(grounded))
            invented = set(_NUMBER_RE.findall(page.takeaway)) - source_numbers
            if invented:
                raise ValueError(f"Visual plan contains ungrounded number: {sorted(invented)[0]}")
            normalized_takeaway = _normalized_grounding_text(page.takeaway).rstrip("…")
            normalized_grounded = _normalized_grounding_text(grounded)
            if normalized_takeaway and normalized_takeaway not in normalized_grounded:
                raise ValueError(
                    f"Visual plan takeaway is not a source excerpt: {page.page_id}"
                )
        node_ids = {node.node_id for node in page.visual_anchor.nodes}
        if len(node_ids) != len(page.visual_anchor.nodes):
            raise ValueError("Visual diagram node IDs must be unique")
        if any(edge.source not in node_ids or edge.target not in node_ids for edge in page.visual_anchor.edges):
            raise ValueError("Visual diagram edge references an unknown node")
        for node in page.visual_anchor.nodes:
            node_grounded = "\n".join(
                fragment_text[item]
                for item in node.source_fragment_ids
            )
            normalized_label = _normalized_grounding_text(node.label).rstrip("…")
            if normalized_label and normalized_label not in _normalized_grounding_text(node_grounded):
                raise ValueError("Visual diagram label is not a source excerpt")
        source_text = "\n".join(
            fragment_text[item]
            for item in page.visual_anchor.source_fragment_ids
        )
        if page.visual_anchor.kind == "table":
            for row in page.visual_anchor.parameters.get("rows") or []:
                excerpt = str(row[-1] if isinstance(row, list) and row else row).rstrip("…")
                if excerpt and _normalized_grounding_text(excerpt) not in _normalized_grounding_text(source_text):
                    raise ValueError("Visual table row is not a source excerpt")
        if page.visual_anchor.kind == "coordinate_plot":
            labels = page.visual_anchor.parameters.get("point_labels") or []
            for label in labels:
                excerpt = str(label).rstrip("…")
                if excerpt and _normalized_grounding_text(excerpt) not in _normalized_grounding_text(source_text):
                    raise ValueError("Coordinate label is not a source excerpt")
        if page.visual_anchor.kind == "formula":
            formula = str(page.visual_anchor.parameters.get("formula") or "")
            if (
                formula
                and _normalized_grounding_text(formula)
                not in _normalized_grounding_text(source_text)
            ):
                raise ValueError("Formula visual is not a source excerpt")
    return {"passed": True, "page_count": len(visual_plan.pages)}


def apply_visual_plan_to_slides(
    slides: list[dict[str, Any]],
    visual_plan: SlideVisualPlanV1,
) -> list[dict[str, Any]]:
    by_page = {page.page_id: page for page in visual_plan.pages}
    result: list[dict[str, Any]] = []
    for slide in slides:
        page = by_page.get(str(slide.get("unit_id") or ""))
        if not page:
            result.append(slide)
            continue
        updated = dict(slide)
        updated["teaching_job"] = page.teaching_job
        updated["takeaway"] = page.takeaway
        updated["transition_from"] = page.transition_from
        updated["composition"] = page.composition
        updated["visuals"] = (
            []
            if page.visual_anchor.kind == "none"
            else [page.visual_anchor.model_dump(mode="json")]
        )
        quality = dict(updated.get("quality") or {})
        quality["visual_plan_page_id"] = page.page_id
        quality["visual_kind"] = page.visual_anchor.kind
        quality["composition"] = page.composition
        updated["quality"] = quality
        result.append(updated)
    return result


def visual_quality_report(
    visual_plan: SlideVisualPlanV1,
    allocation_plan: Any,
    fragments: list[Any] | None = None,
) -> dict[str, Any]:
    """Measure explanatory gain instead of merely counting rendered objects."""
    allocation_by_id = {page.page_id: page for page in allocation_plan.pages}
    fragment_text = {
        str(item.fragment_id): str(item.text or "")
        for item in fragments or []
    }
    fragment_kind = {
        str(item.fragment_id): str(item.kind or "")
        for item in fragments or []
    }
    content_pages = [
        page
        for page in visual_plan.pages
        if (
            not page.appendix
            and allocation_by_id[page.page_id].fragment_ids
            and allocation_by_id[page.page_id].layout not in {"section-divider"}
        )
    ]
    eligible = [
        page
        for page in content_pages
        if (
            str(getattr(allocation_by_id[page.page_id], "narrative_role", ""))
            in {"method", "example", "misconception"}
            or page.visual_anchor.kind != "none"
            or any(
                fragment_kind.get(fragment_id)
                in {"formula", "code", "table", "image", "diagram"}
                for fragment_id in allocation_by_id[page.page_id].fragment_ids
            )
        )
        and str(
            getattr(allocation_by_id[page.page_id], "narrative_role", "")
        ) not in {"checkpoint"}
    ]
    scores = {
        page.page_id: _visual_information_gain(page.visual_anchor, fragment_text)
        for page in eligible
    }
    visual_pages = [page for page in eligible if scores[page.page_id] >= 0.5]
    ratio = 1.0 if not eligible else len(visual_pages) / len(eligible)
    required = {"teaching": 0.70, "concise": 0.80, "full": 0.40}[visual_plan.mode]
    strict_visual_gate = len(eligible) >= 8
    issues: list[dict[str, Any]] = []
    if ratio + 1e-9 < required:
        issues.append({
            "severity": "critical" if strict_visual_gate else "minor",
            "code": "visual_coverage_below_threshold",
            "message": f"Effective visual coverage {ratio:.1%} is below {required:.0%}.",
        })
    one_node_diagrams = [
        page
        for page in eligible
        if (
            page.visual_anchor.kind in {"relational_diagram", "rule_diagram"}
            and len(page.visual_anchor.nodes) < 2
        )
    ]
    if one_node_diagrams:
        issues.append({
            "severity": "critical",
            "code": "single_node_diagram_is_not_visual",
            "page_id": one_node_diagrams[0].page_id,
            "count": len(one_node_diagrams),
        })

    chapter_pages: dict[str, list[SlideVisualPlanPageV1]] = defaultdict(list)
    for page in eligible:
        if page.chapter_id:
            chapter_pages[page.chapter_id].append(page)
    for chapter_id, pages in chapter_pages.items():
        if not any(scores[page.page_id] >= 0.5 for page in pages):
            issues.append({
                "severity": "critical" if len(pages) >= 6 else "minor",
                "code": "chapter_explanatory_visual_missing",
                "chapter_id": chapter_id,
            })
        compositions = Counter(page.composition for page in pages)
        if len(pages) >= 4 and any(count / len(pages) > 0.35 for count in compositions.values()):
            issues.append({
                "severity": "major",
                "code": "chapter_composition_overused",
                "chapter_id": chapter_id,
            })
        meaningful_kinds = {
            page.visual_anchor.kind
            for page in pages
            if scores[page.page_id] >= 0.5
        }
        if len(pages) >= 8 and len(meaningful_kinds) < 2:
            issues.append({
                "severity": "major",
                "code": "chapter_visual_vocabulary_too_narrow",
                "chapter_id": chapter_id,
            })

    previous = ""
    run = 0
    for page in content_pages:
        if page.visual_anchor.kind == "none":
            previous = ""
            run = 0
            continue
        if page.composition == previous:
            run += 1
        else:
            previous = page.composition
            run = 1
        if strict_visual_gate and run > 2:
            issues.append({
                "severity": "critical",
                "code": "composition_repeated_more_than_twice",
                "page_id": page.page_id,
            })
            break
    previous_kind = ""
    kind_run = 0
    for page in eligible:
        kind = (
            page.visual_anchor.kind
            if scores[page.page_id] >= 0.5
            else "none"
        )
        if kind == previous_kind:
            kind_run += 1
        else:
            previous_kind = kind
            kind_run = 1
        maximum_kind_run = 5 if kind in {"formula", "code"} else 3
        if (
            strict_visual_gate
            and kind != "none"
            and kind_run > maximum_kind_run
        ):
            issues.append({
                "severity": "critical",
                "code": "visual_kind_repeated_more_than_three_times",
                "page_id": page.page_id,
                "visual_kind": kind,
            })
            break
    episode_warnings = []
    storyboard = visual_plan.deck_brief.get("storyboard") or {}
    for episode in storyboard.get("episodes") or []:
        score = float(episode.get("progression_score") or 0)
        missing = list(episode.get("missing_roles") or [])
        beat_count = len(episode.get("beats") or [])
        if score < 0.65 or missing:
            episode_warnings.append({
                "severity": "major" if beat_count >= 4 else "minor",
                "code": "teaching_episode_incomplete",
                "episode_id": str(episode.get("episode_id") or ""),
                "topic_id": str(episode.get("topic_id") or ""),
                "progression_score": score,
                "missing_roles": missing,
            })
    issues.extend(episode_warnings[:20])
    image_count = sum(
        page.visual_anchor.kind in {"source_image", "generated_illustration"}
        and scores[page.page_id] >= 0.5
        for page in eligible
    )
    if len(eligible) >= 12 and image_count == 0:
        issues.append({
            "severity": "minor",
            "code": "teaching_deck_has_no_image_assets",
        })
    passed = not any(item["severity"] == "critical" for item in issues)
    return {
        "passed": passed,
        "effective_visual_coverage_ratio": round(ratio, 6),
        "required_visual_coverage_ratio": required,
        "eligible_page_count": len(eligible),
        "visual_page_count": len(visual_pages),
        "image_visual_count": image_count,
        "mean_information_gain": round(
            sum(scores.values()) / max(1, len(scores)),
            6,
        ),
        "page_information_gain": {
            page_id: round(score, 6)
            for page_id, score in scores.items()
        },
        "visual_kind_counts": dict(Counter(
            page.visual_anchor.kind for page in visual_pages
        )),
        "composition_counts": dict(Counter(
            page.composition for page in eligible
        )),
        "issues": issues,
        "blockers": [item for item in issues if item["severity"] == "critical"],
        "warnings": [item for item in issues if item["severity"] != "critical"],
        "render_contract": "shared_slide_spec_v1",
    }


def _visual_information_gain(
    anchor: VisualAnchorV1,
    fragment_text: dict[str, str],
) -> float:
    if anchor.kind == "none":
        return 0.0
    declared = anchor.parameters.get("information_gain_score")
    if isinstance(declared, (int, float)):
        score = float(declared)
    else:
        score = {
            "source_image": 1.0,
            "generated_illustration": 0.9,
            "coordinate_plot": 1.0,
            "chart": 1.0,
            "table": 0.7,
            "formula": 0.78,
            "code": 0.8,
            "rule_diagram": 0.88,
            "relational_diagram": 0.0,
        }.get(anchor.kind, 0.0)
    if anchor.kind in {"relational_diagram", "rule_diagram"}:
        if (
            len(anchor.nodes) < 2
            or not anchor.edges
            or not anchor.parameters.get("relation_evidence")
        ):
            return 0.0
        source = _normalized_grounding_text(" ".join(
            fragment_text.get(fragment_id, "")
            for fragment_id in anchor.source_fragment_ids
        ))
        labels = _normalized_grounding_text(" ".join(
            node.label for node in anchor.nodes
        ))
        duplication = (
            len(labels) / len(source)
            if source
            else float(anchor.parameters.get("source_text_duplication_ratio") or 0)
        )
        if not isinstance(declared, (int, float)) and duplication > 0.8:
            score -= 0.22
        if all(len(_clean_source_text(node.label)) > 34 for node in anchor.nodes):
            score -= 0.12
    return min(1.0, max(0.0, score))


def _formula_has_adjacent_explanation(
    formula_fragments: list[dict[str, Any]],
    all_fragments: list[dict[str, Any]],
    allocation_by_fragment: dict[str, str],
    slide_id: str,
) -> bool:
    explanatory_kinds = {"heading", "paragraph", "list_item"}
    for formula in formula_fragments:
        formula_ordinal = int(formula.get("ordinal") or 0)
        for candidate in all_fragments:
            if candidate.get("block_id") != formula.get("block_id"):
                continue
            if str(candidate.get("kind") or "") not in explanatory_kinds:
                continue
            if abs(int(candidate.get("ordinal") or 0) - formula_ordinal) != 1:
                continue
            candidate_id = str(candidate.get("fragment_id") or "")
            if allocation_by_fragment.get(candidate_id) not in {"", slide_id, None}:
                return True
    return False


def visual_integrity_issues(content: dict[str, Any]) -> list[dict[str, Any]]:
    """Validate source bindings and immutable assets in a materialized deck."""
    fragments = {
        str(item.get("fragment_id") or ""): item
        for item in content.get("fragment_manifest") or []
    }
    assets = {
        str(item.get("asset_id") or ""): item
        for item in content.get("visual_asset_manifest") or []
    }
    issues: list[dict[str, Any]] = []
    allocation_by_fragment = {
        str(fragment_id): str(slide.get("unit_id") or "")
        for slide in content.get("slides") or []
        for fragment_id in (slide.get("quality") or {}).get("fragment_ids") or []
    }
    fragment_list = list(fragments.values())
    for slide in content.get("slides") or []:
        slide_id = str(slide.get("unit_id") or "")
        allocated = set((slide.get("quality") or {}).get("fragment_ids") or [])
        visible_text = "\n".join(
            [
                str(block.get("content") or "")
                for block in slide.get("blocks") or []
            ]
            + [
                str(item)
                for block in slide.get("blocks") or []
                for item in block.get("items") or []
            ]
        )
        if _RAW_MERMAID_RE.search(visible_text):
            issues.append({
                "severity": "critical",
                "code": "raw_mermaid_visible",
                "slide_id": slide_id,
            })
        allocated_fragments = [
            fragments[fragment_id]
            for fragment_id in allocated
            if fragment_id in fragments
        ]
        if (
            allocated_fragments
            and {str(item.get("kind") or "") for item in allocated_fragments}
            == {"formula"}
            and _formula_has_adjacent_explanation(
                allocated_fragments,
                fragment_list,
                allocation_by_fragment,
                slide_id,
            )
        ):
            issues.append({
                "severity": "critical",
                "code": "orphan_formula_without_context",
                "slide_id": slide_id,
            })
        for visual in slide.get("visuals") or []:
            kind = str(visual.get("kind") or "")
            source_ids = set(visual.get("source_fragment_ids") or [])
            if source_ids - allocated:
                issues.append({
                    "severity": "critical",
                    "code": "visual_source_binding_invalid",
                    "slide_id": slide_id,
                })
            if source_ids - set(fragments):
                issues.append({
                    "severity": "critical",
                    "code": "visual_unknown_fragment",
                    "slide_id": slide_id,
                })
            source_text = "\n".join(
                str(fragments[fragment_id].get("text") or "")
                for fragment_id in source_ids
                if fragment_id in fragments
            )
            for node in visual.get("nodes") or []:
                node_sources = node.get("source_fragment_ids") or []
                node_text = "\n".join(
                    str(fragments[fragment_id].get("text") or "")
                    for fragment_id in node_sources
                    if fragment_id in fragments
                )
                label = str(node.get("label") or "").rstrip("…")
                if label and _normalized_grounding_text(label) not in _normalized_grounding_text(node_text):
                    issues.append({
                        "severity": "critical",
                        "code": "diagram_label_not_source_bound",
                        "slide_id": slide_id,
                    })
            if kind == "rule_diagram":
                parameters = visual.get("parameters") or {}
                if (
                    parameters.get("template") not in RULE_DIAGRAM_TEMPLATES
                    or len(visual.get("nodes") or []) < 2
                    or not visual.get("edges")
                    or not parameters.get("relation_evidence")
                ):
                    issues.append({
                        "severity": "critical",
                        "code": "rule_diagram_invalid",
                        "slide_id": slide_id,
                    })
            if kind in {"source_image", "generated_illustration"}:
                asset_id = str(visual.get("asset_id") or "")
                asset = assets.get(asset_id)
                if (
                    not asset
                    or not str(asset.get("sha256") or "")
                    or not str(asset.get("alt_text") or "")
                ):
                    issues.append({
                        "severity": "critical",
                        "code": "visual_asset_missing_or_unbound",
                        "slide_id": slide_id,
                        "asset_id": asset_id,
                    })
            if kind == "chart":
                parameters = visual.get("parameters") or {}
                values = [
                    value
                    for series in parameters.get("series") or []
                    for value in series.get("values") or []
                ]
                if not values or not all(isinstance(value, (int, float)) for value in values):
                    issues.append({
                        "severity": "critical",
                        "code": "chart_data_invalid",
                        "slide_id": slide_id,
                    })
                elif any(str(value) not in source_text for value in values):
                    issues.append({
                        "severity": "critical",
                        "code": "chart_data_not_source_bound",
                        "slide_id": slide_id,
                    })
            if kind == "coordinate_plot":
                parameters = visual.get("parameters") or {}
                points = parameters.get("points") or []
                labels = parameters.get("point_labels") or []
                if len(points) < 2 or len(labels) != len(points):
                    issues.append({
                        "severity": "critical",
                        "code": "coordinate_data_invalid",
                        "slide_id": slide_id,
                    })
                elif any(
                    _normalized_grounding_text(str(label).rstrip("…"))
                    not in _normalized_grounding_text(source_text)
                    for label in labels
                ):
                    issues.append({
                        "severity": "critical",
                        "code": "coordinate_data_not_source_bound",
                        "slide_id": slide_id,
                    })
            if kind == "formula":
                formula = str((visual.get("parameters") or {}).get("formula") or "")
                if not formula:
                    issues.append({
                        "severity": "critical",
                        "code": "formula_source_missing",
                        "slide_id": slide_id,
                    })
                elif (
                    _normalized_grounding_text(formula)
                    not in _normalized_grounding_text(source_text)
                ):
                    issues.append({
                        "severity": "critical",
                        "code": "formula_not_source_bound",
                        "slide_id": slide_id,
                    })
    if content.get("visual_plan") and (
        (content.get("visual_quality_report") or {}).get("render_contract")
        != "shared_slide_spec_v1"
    ):
        issues.append({
            "severity": "critical",
            "code": "preview_export_render_contract_mismatch",
            "target": "deck",
        })
    return issues


def build_signature(
    *,
    source_document_revision: str,
    mode: str,
    theme: str,
    compiler_version: str,
    theme_version: str,
) -> dict[str, str]:
    payload = {
        "source_document_revision": source_document_revision,
        "mode": mode,
        "theme": theme,
        "compiler_version": compiler_version,
        "theme_version": theme_version,
        "visual_policy_version": SLIDE_VISUAL_POLICY_VERSION,
    }
    return {**payload, "signature": stable_hash(payload, prefix="sbs_")}


def _takeaway(page: Any, fragments: list[Any], deck_title: str) -> tuple[str, list[str]]:
    if fragments:
        candidates: list[tuple[int, int, Any, str]] = []
        kind_priority = {
            "paragraph": 4,
            "heading": 3,
            "list_item": 2,
            "table": 2,
            "formula": 1,
            "code": 1,
        }
        for source_index, source in enumerate(fragments):
            text = _clean_source_text(source.text)
            sentence = re.split(
                r"(?:[。！？!?]+|\.(?=\s|$))\s*",
                text,
                maxsplit=1,
            )[0].strip()
            if source.kind == "list_item":
                label, separator, _remainder = sentence.partition("：")
                if not separator:
                    label, separator, _remainder = sentence.partition(":")
                if separator and 2 <= len(label) <= 30:
                    sentence = label
            if not sentence:
                continue
            generic = _is_generic_source_label(sentence)
            meaningful = len(re.sub(r"[\W_]+", "", sentence)) >= 5
            score = kind_priority.get(source.kind, 0) - (6 if generic else 0)
            candidates.append((score, -source_index, source, sentence if meaningful else text))
        if candidates:
            _score, _source_index, source, sentence = max(candidates, key=lambda item: (item[0], item[1]))
            return _trim_takeaway(sentence), [source.fragment_id]
    derived = [
        str(item.text).strip()
        for item in getattr(page, "derived_text", [])
        if str(item.text).strip()
    ]
    if page.layout == "cover":
        return deck_title, []
    if page.layout == "roadmap":
        return "课程将沿章节问题逐步展开", []
    if page.page_id == "slide:summary":
        return "回到课程主问题，连接概念、方法与应用", []
    if page.page_id == "slide:appendix-divider":
        return "补充材料保留完整课程来源", []
    return _trim_takeaway(derived[0] if derived else deck_title), []


def _teaching_job(page: Any, takeaway: str) -> str:
    role = str(getattr(page, "narrative_role", "") or "concept")
    prefix = {
        "orientation": "建立本段学习方向",
        "concept": "解释核心概念",
        "reasoning": "说明结论为何成立",
        "method": "展示可复用的方法",
        "example": "用具体情境验证概念",
        "misconception": "识别并纠正常见误区",
        "checkpoint": "检查是否真正理解",
        "recap": "连接本章知识链",
        "appendix": "保留补充来源",
    }.get(role, "推进课程理解")
    return f"{prefix}：{takeaway}"


def _transition_text(page: Any, previous: str, current: str) -> str:
    role = str(getattr(page, "narrative_role", "") or "")
    connector = {
        "reasoning": "在上一结论基础上追问原因",
        "method": "把原理转化为可执行步骤",
        "example": "把抽象规则放入具体情境",
        "checkpoint": "暂停推进并检查理解",
        "recap": "收束前面的概念与方法",
        "appendix": "转入补充来源",
    }.get(role, "继续推进同一知识链")
    return f"{connector}：{_trim_takeaway(previous, 34)} → {_trim_takeaway(current, 34)}"


def _visual_anchor(page: Any, fragments: list[Any], index: int) -> VisualAnchorV1:
    ids = [item.fragment_id for item in fragments]
    kinds = {item.kind for item in fragments}
    role = str(getattr(page, "narrative_role", "") or "")
    visual_id = stable_hash(
        {"page_id": page.page_id, "fragment_ids": ids, "policy": SLIDE_VISUAL_POLICY_VERSION},
        prefix="sv_",
    )
    source_image = next(
        (
            item
            for item in fragments
            if item.source_kind == "image" and item.asset_refs
        ),
        None,
    )
    if source_image is not None:
        return VisualAnchorV1(
            visual_id=visual_id,
            kind="source_image",
            purpose="evidence",
            source_fragment_ids=ids,
            alt_text=_trim_takeaway(source_image.text, 120),
            parameters={
                "asset_ref": source_image.asset_refs[0],
                "information_gain_score": 1.0,
            },
        )
    diagram_fragment = next(
        (item for item in fragments if item.kind == "diagram"),
        None,
    )
    if diagram_fragment is not None:
        program = parse_mermaid_rule_diagram(
            str(diagram_fragment.text or ""),
            fragment_id=diagram_fragment.fragment_id,
        )
        if program is None:
            return _none_anchor(page.page_id, "structure")
        return VisualAnchorV1(
            visual_id=visual_id,
            kind="rule_diagram",
            purpose="process",
            source_fragment_ids=program.source_fragment_ids,
            alt_text="Source-grounded rule diagram",
            nodes=[
                VisualNodeV1(
                    node_id=node.node_id,
                    label=node.label,
                    source_fragment_ids=node.source_fragment_ids,
                    emphasis="primary" if node_index == 0 else "secondary",
                )
                for node_index, node in enumerate(program.nodes)
            ],
            edges=[
                VisualEdgeV1(
                    source=edge.source,
                    target=edge.target,
                    label=edge.label,
                    relation=edge.relation,
                )
                for edge in program.edges
            ],
            parameters={
                "schema_version": program.schema_version,
                "template": program.template,
                "direction": program.direction,
                "relation_evidence": program.relation_evidence,
                "information_gain_score": 0.88,
            },
        )
    if "code" in kinds:
        return VisualAnchorV1(
            visual_id=visual_id,
            kind="code",
            purpose="evidence",
            source_fragment_ids=ids,
            alt_text="代码示例与阅读重点",
            parameters={
                "language": "code",
                "information_gain_score": 0.8,
            },
        )
    embedded_formula = _source_formula(fragments)
    if "formula" in kinds or embedded_formula:
        formula = embedded_formula or next(
            str(item.text)
            for item in fragments
            if item.kind == "formula"
        )
        return VisualAnchorV1(
            visual_id=visual_id,
            kind="formula",
            purpose="evidence",
            source_fragment_ids=ids,
            alt_text="关键公式",
            parameters={
                "source_bound": True,
                "formula": formula,
                "information_gain_score": 0.78,
            },
        )
    if "table" in kinds:
        return VisualAnchorV1(
            visual_id=visual_id,
            kind="table",
            purpose="comparison",
            source_fragment_ids=ids,
            alt_text="结构化对照",
            parameters={
                "text": "\n".join(item.text for item in fragments),
                "source_bound": True,
                "information_gain_score": 0.82,
            },
        )

    clauses = _source_clauses(fragments)
    list_clauses = [
        (_trim_takeaway(_clean_source_text(item.text), 72), item.fragment_id)
        for item in fragments
        if item.kind == "list_item" and _clean_source_text(item.text)
    ]
    if (
        (role == "misconception" or str(getattr(page, "layout", "") or "") == "comparison")
        and len(clauses) >= 2
    ):
        rows = [
            [str(row_index + 1).zfill(2), label]
            for row_index, (label, _fragment_id) in enumerate((list_clauses or clauses)[:6])
        ]
        return VisualAnchorV1(
            visual_id=visual_id,
            kind="table",
            purpose="comparison" if role == "misconception" else "structure",
            source_fragment_ids=ids,
            alt_text="关键要点对照",
            parameters={
                "headers": ["序号", "关键要点"],
                "rows": rows,
                "source_bound": True,
                "information_gain_score": 0.68,
            },
        )
    coordinate_parameters = _coordinate_parameters(fragments)
    if coordinate_parameters:
        return VisualAnchorV1(
            visual_id=visual_id,
            kind="coordinate_plot",
            purpose="application",
            source_fragment_ids=ids,
            alt_text="二维坐标关系",
            parameters={
                **coordinate_parameters,
                "information_gain_score": 1.0,
            },
        )
    relation = _semantic_relation_spec(page, fragments, clauses, list_clauses)
    if relation is not None:
        relation_kind, diagram_type, relation_clauses, evidence = relation
        nodes = [
            VisualNodeV1(
                node_id=f"n{node_index + 1}",
                label=label,
                source_fragment_ids=[fragment_id],
                emphasis="primary" if node_index == 0 else "secondary",
            )
            for node_index, (label, fragment_id) in enumerate(relation_clauses[:5])
        ]
        edges = _relation_edges(nodes, relation_kind, diagram_type)
        source_length = max(
            1,
            len(_normalized_grounding_text(
                " ".join(str(item.text or "") for item in fragments)
            )),
        )
        label_length = sum(
            len(_normalized_grounding_text(node.label))
            for node in nodes
        )
        duplication_ratio = min(1.0, label_length / source_length)
        score = 0.8 if diagram_type in {"process", "cause-effect", "comparison"} else 0.72
        if duplication_ratio > 0.8:
            score -= 0.22
        purpose: VisualPurpose = {
            "example": "application",
            "misconception": "comparison",
            "reasoning": "structure",
            "method": "process",
        }.get(role, "structure")  # type: ignore[assignment]
        diagram_label = {
            "process": "步骤关系",
            "cause-effect": "因果关系",
            "comparison": "对比关系",
            "mapping": "映射关系",
            "hierarchy": "概念层级",
            "reasoning": "推理关系",
        }.get(diagram_type, "概念关系")
        return VisualAnchorV1(
            visual_id=visual_id,
            kind="relational_diagram",
            purpose=purpose,
            source_fragment_ids=ids,
            alt_text=diagram_label,
            nodes=nodes,
            edges=edges,
            parameters={
                "direction": "horizontal" if index % 2 == 0 else "vertical",
                "diagram_type": diagram_type,
                "relation_evidence": evidence,
                "source_text_duplication_ratio": round(duplication_ratio, 6),
                "information_gain_score": round(max(0.0, score), 6),
            },
        )
    source_text = " ".join(
        _clean_source_text(item.text)
        for item in fragments
        if _clean_source_text(item.text)
    )
    if role == "example" and len(source_text) >= 20:
        return VisualAnchorV1(
            visual_id=visual_id,
            kind="generated_illustration",
            purpose="application",
            source_fragment_ids=ids,
            alt_text=_trim_takeaway(source_text, 120),
            parameters={
                "prompt": (
                    "Create a clear educational illustration for this source concept. "
                    "Use one dominant scene, no written words, no letters, no numbers, "
                    f"no logo. Source concept: {source_text[:600]}"
                ),
                "size": "1536x1024",
                "generation_seed": stable_hash(
                    {"page_id": page.page_id, "source": source_text},
                    prefix="seed_",
                )[-16:],
                "information_gain_score": 0.9,
            },
        )
    return _none_anchor(page.page_id, "structure")


def _composition_for(
    page: Any,
    anchor: VisualAnchorV1,
    index: int,
) -> SlideComposition:
    role = str(getattr(page, "narrative_role", "") or "")
    if role == "checkpoint":
        return "exercise"
    if role == "misconception":
        return "comparison"
    if anchor.kind == "none":
        return "statement"
    if anchor.kind in {"formula", "code", "table", "chart"}:
        return ("split-visual", "figure-first", "diagram-full")[index % 3]
    # Rotate silhouettes so a deck cannot degrade into a repeated card grid.
    return ("figure-first", "split-visual", "diagram-full")[index % 3]


def _none_anchor(page_id: str, purpose: VisualPurpose) -> VisualAnchorV1:
    return VisualAnchorV1(
        visual_id=stable_hash({"page_id": page_id, "kind": "none"}, prefix="sv_"),
        kind="none",
        purpose=purpose,
    )


def _source_clauses(fragments: list[Any]) -> list[tuple[str, str]]:
    values: list[tuple[str, str]] = []
    for fragment in fragments:
        clean = _clean_source_text(fragment.text)
        for value in re.split(r"(?:[。！？；;]\s*|\n+)", clean):
            label = _trim_takeaway(value.strip(), 26)
            if label and label not in {item[0] for item in values}:
                values.append((label, fragment.fragment_id))
    return values


def _source_formula(fragments: list[Any]) -> str:
    """Extract an existing display expression without rewriting it."""
    source = "\n".join(str(item.text or "") for item in fragments)
    display = re.search(
        r"(\$\$.*?\$\$|\\\[.*?\\\])",
        source,
        re.DOTALL,
    )
    if display:
        formula = display.group(1).strip()
        body = re.sub(r"^(?:\$\$|\\\[)|(?:\$\$|\\\])$", "", formula).strip()
        if len(body) > 220:
            return ""
        if len(re.findall(r"[\u4e00-\u9fff]", body)) > 36:
            return ""
        if len(re.findall(r"[。！？；]", body)) > 2:
            return ""
        if not re.search(
            r"(?:[=<>≤≥∈⊆∩∪+\-*/^_]|\\(?:frac|sum|prod|int|dim|begin))",
            body,
        ):
            return ""
        return formula
    return ""


def _semantic_relation_spec(
    page: Any,
    fragments: list[Any],
    clauses: list[tuple[str, str]],
    list_clauses: list[tuple[str, str]],
) -> tuple[str, str, list[tuple[str, str]], str] | None:
    """Infer a diagram only when the source exposes an actual relationship."""
    role = str(getattr(page, "narrative_role", "") or "")
    source = " ".join(_clean_source_text(item.text) for item in fragments)
    if role == "method" and len(list_clauses) >= 2:
        return "sequence", "process", list_clauses, "method_role_with_ordered_items"
    if role == "misconception" and len(clauses) >= 2:
        return "contrasts", "comparison", clauses, "misconception_role"
    if (
        len(list_clauses) >= 2
        and any(item.kind == "heading" for item in fragments)
    ):
        heading = next(
            (
                (_trim_takeaway(_clean_source_text(item.text), 26), item.fragment_id)
                for item in fragments
                if item.kind == "heading" and _clean_source_text(item.text)
            ),
            None,
        )
        if heading:
            return (
                "contains",
                "hierarchy",
                [heading, *list_clauses[:4]],
                "heading_with_source_list",
            )
    relation_rules = (
        (
            "causes",
            "cause-effect",
            r"(?:因为|由于|因此|所以|导致|使得|从而|because|therefore|causes?|leads?\s+to)",
            "explicit_causal_connector",
        ),
        (
            "contrasts",
            "comparison",
            r"(?:相比|区别|不同|相反|但是|而非|versus|\bvs\.?\b|whereas|unlike)",
            "explicit_comparison_connector",
        ),
        (
            "maps_to",
            "mapping",
            r"(?:映射为|变换为|转化为|输入.+输出|maps?\s+to|transforms?\s+into)",
            "explicit_mapping_connector",
        ),
        (
            "sequence",
            "process",
            r"(?:首先|然后|随后|最后|第一步|第二步|流程|first|then|finally|step\s+\d+)",
            "explicit_sequence_connector",
        ),
        (
            "supports",
            "reasoning",
            r"(?:说明|表明|推出|可得|证明|意味着|implies|shows?|proves?|hence)",
            "explicit_reasoning_connector",
        ),
    )
    if len(clauses) >= 2:
        for relation, diagram_type, pattern, evidence in relation_rules:
            if re.search(pattern, source, re.IGNORECASE):
                return relation, diagram_type, clauses, evidence
    return None


def _relation_edges(
    nodes: list[VisualNodeV1],
    relation: str,
    diagram_type: str,
) -> list[VisualEdgeV1]:
    relation_value = relation if relation in {
        "sequence",
        "supports",
        "contrasts",
        "causes",
        "contains",
        "maps_to",
    } else "supports"
    if diagram_type == "hierarchy":
        return [
            VisualEdgeV1(
                source=nodes[0].node_id,
                target=node.node_id,
                relation="contains",
            )
            for node in nodes[1:]
        ]
    return [
        VisualEdgeV1(
            source=nodes[index].node_id,
            target=nodes[index + 1].node_id,
            relation=relation_value,  # type: ignore[arg-type]
        )
        for index in range(len(nodes) - 1)
    ]


def _coordinate_parameters(fragments: list[Any]) -> dict[str, Any] | None:
    source = " ".join(str(item.text or "") for item in fragments)
    matches = list(_COORDINATE_PAIR_RE.finditer(source))
    if len(matches) < 2:
        return None
    points: list[list[float]] = []
    labels: list[str] = []
    for match in matches[:6]:
        point = [float(match.group("x")), float(match.group("y"))]
        if point in points:
            continue
        points.append(point)
        labels.append(match.group("label"))
    if len(points) < 2:
        return None
    return {
        "points": points,
        "point_labels": labels,
        "connect_points": bool(re.search(r"(?:映射|变换|旋转|→|->|maps?\s+to)", source, re.I)),
        "axis_labels": ["x", "y"],
        "source_bound": True,
    }


def _clean_source_text(value: str) -> str:
    clean = str(value or "")
    clean = re.sub(r"^#{1,6}\s*", "", clean)
    clean = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", clean)
    clean = re.sub(r"\*\*(.+?)\*\*", r"\1", clean)
    clean = re.sub(r"__(.+?)__", r"\1", clean)
    clean = re.sub(r"(?<!\*)\*([^*\n]+?)\*(?!\*)", r"\1", clean)
    clean = re.sub(r"`([^`\n]+)`", r"\1", clean)
    clean = clean.replace("$$", "")
    clean = re.sub(r"(?<!\\)\$", "", clean)
    clean = re.sub(r"\\(?:mathbf|mathrm|mathit|text)\{([^{}]+)\}", r"\1", clean)
    clean = re.sub(r"\\mathbb\{([A-Za-z])\}", r"\1", clean)
    clean = clean.replace(r"\subseteq", "⊆")
    clean = re.sub(r"\\in(?![A-Za-z])", "∈", clean)
    clean = clean.replace(r"\cdots", "…")
    clean = clean.replace(r"\times", "×")
    clean = re.sub(r"\\to(?![A-Za-z])", "→", clean)
    return re.sub(r"\s+", " ", clean).strip()


def _is_generic_source_label(value: str) -> bool:
    normalized = re.sub(r"[\W_]+", "", value).lower()
    return normalized in {
        "核心概念与背景",
        "深度原理底层机制",
        "技术实现方法论",
        "思考与挑战",
        "实战案例行业应用",
        "学习目标",
        "正文",
    }


def _normalized_grounding_text(value: str) -> str:
    return re.sub(r"\s+", "", _clean_source_text(value))


def _trim_takeaway(value: str, limit: int = 48) -> str:
    clean = _clean_source_text(value)
    if len(clean) <= limit:
        return clean
    excerpt = clean[:limit]
    opening = max(excerpt.rfind("（"), excerpt.rfind("("))
    closing = max(excerpt.rfind("）"), excerpt.rfind(")"))
    if opening > closing and opening >= max(8, limit // 2):
        excerpt = excerpt[:opening]
    else:
        punctuation = max(
            excerpt.rfind("，"),
            excerpt.rfind(","),
            excerpt.rfind("；"),
            excerpt.rfind(";"),
            excerpt.rfind("："),
            excerpt.rfind(":"),
            excerpt.rfind("）"),
            excerpt.rfind(")"),
        )
        if punctuation >= max(8, limit // 2):
            excerpt = excerpt[:punctuation + (1 if excerpt[punctuation] in "）)" else 0)]
        else:
            space = excerpt.rfind(" ")
            if space >= max(8, limit // 2):
                excerpt = excerpt[:space]
    return excerpt.rstrip("，,；;：:、 ")


__all__ = [
    "SLIDE_VISUAL_PLAN_SCHEMA",
    "SLIDE_VISUAL_POLICY_VERSION",
    "SlideVisualPlanPageV1",
    "SlideVisualPlanV1",
    "VisualAnchorV1",
    "VisualEdgeV1",
    "VisualNodeV1",
    "apply_visual_plan_to_slides",
    "build_signature",
    "deterministic_visual_plan",
    "plan_slide_visuals",
    "rebalance_visual_plan_pages",
    "validate_visual_plan",
    "visual_quality_report",
    "visual_integrity_issues",
]
