"""Closed, versioned layout registry for slide-deck V6."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_serializer

from ppt_layout_schema import LayoutExecution

from course_document import stable_hash
from slide_layout_geometry import (
    BALANCED_TWO_COLUMN_BODY_V1,
    CLASSIFICATION_THREE_CARDS_V1,
    DIAGRAM_SOURCE_PANEL_V1,
    FIGURE_SOURCE_PANEL_V1,
    FORMULA_SOURCE_PANEL_V1,
    HORIZONTAL_PROCESS_CARDS_V1,
    TABLE_SUPPORT_BAND_V1,
)
from slide_theme import load_slide_theme_pack


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TemplateLayoutContractError(ValueError):
    """Raised when a template cannot satisfy the closed V6 layout registry."""


class TemplateSlotContractV1(_StrictModel):
    slot_id: str
    slot_kind: Literal[
        "title",
        "eyebrow",
        "body",
        "items",
        "steps",
        "code",
        "formula",
        "table",
        "visual",
        "notes",
    ]
    required: bool = True
    min_chars: int = Field(default=0, ge=0)
    max_chars: int = Field(default=0, ge=0)
    max_items: int = Field(default=0, ge=0)
    max_lines: int = Field(default=0, ge=0)
    max_rows: int = Field(default=0, ge=0)
    continuation_max_chars: int = Field(default=0, ge=0)
    continuation_max_lines: int = Field(default=0, ge=0)
    split_wrapped_lines: int = Field(default=0, ge=0)
    full_wrapped_lines: int = Field(default=0, ge=0)
    split_column_chars: int = Field(default=0, ge=0)
    full_column_chars: int = Field(default=0, ge=0)
    wide_min_columns: int = Field(default=0, ge=0)
    capacity_profile: str = ""
    source_roles: list[str] = Field(default_factory=list)


class TemplateFrameContractV1(_StrictModel):
    """Normalized, source-derived placement facts for one fillable region."""

    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)
    source: Literal["slide", "layout", "adaptive"] = "slide"


class TemplateLayoutContractV1(_StrictModel):
    schema_version: Literal["template_layout_contract_v1"] = (
        "template_layout_contract_v1"
    )
    template_layout_id: str
    layout_slug: str
    teaching_intents: list[str] = Field(min_length=1)
    artifact_kinds: list[str] = Field(default_factory=list)
    slots: list[TemplateSlotContractV1] = Field(min_length=1)
    safe_continuation_layout_slugs: list[str] = Field(default_factory=list)
    base_layout_id: str = ""
    construction_role: str = ""
    source_slide_number: int = Field(default=0, ge=0)
    source_layout_name: str = ""
    source_layout_hint: str = ""
    fill_strategy: Literal[
        "renderer_adapter",
        "source_geometry",
        "adaptive_overlay",
    ] = "renderer_adapter"
    slot_frames: dict[str, TemplateFrameContractV1] = Field(default_factory=dict)
    web_renderer_adapter: str = "template-layout-web-v1"
    pptx_renderer_adapter: str = "template-layout-pptx-v1"
    execution: LayoutExecution | None = None

    @model_serializer(mode="wrap")
    def serialize_compatible(self, handler):
        payload = handler(self)
        if self.execution is None:
            payload.pop("execution", None)
        return payload


class TemplateLayoutPackContractV1(_StrictModel):
    schema_version: Literal["template_layout_pack_contract_v1"] = (
        "template_layout_pack_contract_v1"
    )
    template_id: str
    template_version: str
    template_digest: str
    theme_id: str
    render_theme_overrides: dict[str, str] = Field(default_factory=dict)
    layouts: list[TemplateLayoutContractV1] = Field(min_length=1)

    def layout_id(self, slug: str) -> str:
        candidate = next((item.template_layout_id for item in self.layouts if item.layout_slug == slug), "")
        if not candidate:
            raise KeyError(slug)
        return candidate

    def get_layout(self, layout_id: str) -> TemplateLayoutContractV1 | None:
        return next((item for item in self.layouts if item.template_layout_id == layout_id), None)


def template_layout_contract_matrix(
    template: TemplateLayoutPackContractV1,
) -> list[dict[str, Any]]:
    """Expose the closed layout/slot/capacity/continuation contract for audits."""

    return [
        {
            "template_layout_id": layout.template_layout_id,
            "layout_slug": layout.layout_slug,
            "teaching_intents": list(layout.teaching_intents),
            "artifact_kinds": list(layout.artifact_kinds),
            "construction_role": layout.construction_role,
            "source_slide_number": layout.source_slide_number,
            "source_layout_name": layout.source_layout_name,
            "source_layout_hint": layout.source_layout_hint,
            "fill_strategy": layout.fill_strategy,
            "slot_frames": {
                slot_id: frame.model_dump(mode="json")
                for slot_id, frame in layout.slot_frames.items()
            },
            "required_slots": [
                {
                    "slot_id": slot.slot_id,
                    "slot_kind": slot.slot_kind,
                    "source_roles": list(slot.source_roles),
                    "min_chars": slot.min_chars,
                    "max_chars": slot.max_chars,
                    "max_items": slot.max_items,
                    "max_lines": slot.max_lines,
                    "max_rows": slot.max_rows,
                    "continuation_max_chars": slot.continuation_max_chars,
                    "continuation_max_lines": slot.continuation_max_lines,
                    "split_wrapped_lines": slot.split_wrapped_lines,
                    "full_wrapped_lines": slot.full_wrapped_lines,
                    "split_column_chars": slot.split_column_chars,
                    "full_column_chars": slot.full_column_chars,
                    "wide_min_columns": slot.wide_min_columns,
                    "capacity_profile": slot.capacity_profile,
                }
                for slot in layout.slots
                if slot.required
            ],
            "optional_slots": [
                {
                    "slot_id": slot.slot_id,
                    "slot_kind": slot.slot_kind,
                    "source_roles": list(slot.source_roles),
                    "min_chars": slot.min_chars,
                    "max_chars": slot.max_chars,
                    "max_items": slot.max_items,
                    "max_lines": slot.max_lines,
                    "max_rows": slot.max_rows,
                    "continuation_max_chars": slot.continuation_max_chars,
                    "continuation_max_lines": slot.continuation_max_lines,
                    "split_wrapped_lines": slot.split_wrapped_lines,
                    "full_wrapped_lines": slot.full_wrapped_lines,
                    "split_column_chars": slot.split_column_chars,
                    "full_column_chars": slot.full_column_chars,
                    "wide_min_columns": slot.wide_min_columns,
                    "capacity_profile": slot.capacity_profile,
                }
                for slot in layout.slots
                if not slot.required
            ],
            "safe_continuation_layout_slugs": list(
                layout.safe_continuation_layout_slugs
            ),
        }
        for layout in template.layouts
    ]


_SLOT_SOURCE_ROLES: dict[str, set[str]] = {
    "driving_question": {"orientation", "objective", "checkpoint", "activity"},
    "steps": {
        "activity",
        "application",
        "checkpoint",
        "example",
        "orientation",
        "reasoning",
        "transfer",
    },
    "task": {"activity", "checkpoint", "orientation"},
    "prompt": {
        "activity",
        "checkpoint",
        "orientation",
        "example",
        "misconception",
        "counterexample",
    },
    "criteria": {"feedback", "summary", "objective"},
    "feedback": {"feedback", "remediation"},
    "annotation": {"concept", "reasoning", "feedback", "remediation"},
    "derivation": {"concept", "reasoning", "example", "application"},
    "reasoning": {"reasoning", "example"},
    "interpretation": {
        "activity",
        "checkpoint",
        "concept",
        "example",
        "reasoning",
        "feedback",
        "summary",
    },
    "explanation": {"concept", "reasoning", "feedback"},
    "symptom": {"misconception", "counterexample"},
    "cause": {"reasoning", "misconception"},
    "repair": {"remediation", "feedback"},
    "next_action": {"transfer", "application", "activity"},
}


def _slot(
    slot_id: str,
    kind: str,
    *,
    required: bool = True,
    min_chars: int = 0,
    chars: int = 0,
    items: int = 0,
    lines: int = 0,
    rows: int = 0,
    continuation_chars: int = 0,
    continuation_lines: int = 0,
    split_wrapped_lines: int = 0,
    full_wrapped_lines: int = 0,
    split_column_chars: int = 0,
    full_column_chars: int = 0,
    wide_min_columns: int = 0,
    capacity_profile: str = "",
) -> dict[str, Any]:
    return {
        "slot_id": slot_id,
        "slot_kind": kind,
        "required": required,
        "min_chars": min_chars,
        "max_chars": chars,
        "max_items": items,
        "max_lines": lines,
        "max_rows": rows,
        "continuation_max_chars": continuation_chars,
        "continuation_max_lines": continuation_lines,
        "split_wrapped_lines": split_wrapped_lines,
        "full_wrapped_lines": full_wrapped_lines,
        "split_column_chars": split_column_chars,
        "full_column_chars": full_column_chars,
        "wide_min_columns": wide_min_columns,
        "capacity_profile": capacity_profile,
        "source_roles": sorted(_SLOT_SOURCE_ROLES.get(slot_id, set())),
    }


_TITLE = _slot("title", "title", chars=42, lines=2)
_COVER_TITLE = _slot("title", "title", chars=42, lines=3)
_CHAPTER_TITLE = _slot("title", "title", chars=28, lines=2)
_EYEBROW = _slot("eyebrow", "eyebrow", required=False, chars=24)
_NOTES = _slot("source_notes", "notes", chars=0)


_LAYOUT_SPECS: dict[str, dict[str, Any]] = {
    "cover-minimal": {
        "intents": ["orientation"],
        "slots": [_COVER_TITLE, _slot("subtitle", "body", required=False, chars=90), _NOTES],
        "continuations": [],
    },
    "chapter-entry": {
        "intents": ["orientation", "concept_explanation"],
        "slots": [_EYEBROW, _CHAPTER_TITLE, _slot("driving_question", "body", chars=120), _NOTES],
        "continuations": ["content-stack"],
    },
    "agenda-path": {
        "intents": ["orientation", "recap"],
        "slots": [_TITLE, _slot("agenda_items", "items", items=4, chars=520), _NOTES],
        "continuations": [],
    },
    "content-stack": {
        "intents": [
            "concept_explanation",
            "mechanism",
            "practice_feedback",
            "recap",
            "worked_example",
            "misconception_repair",
        ],
        "slots": [
            _EYEBROW,
            _TITLE,
            # Static characters/lines are last guards. The shared profile
            # measures the renderer's actual single/two-column geometry and
            # reserves a full bottom line against Office/font drift.
            _slot(
                "body",
                "body",
                min_chars=120,
                chars=650,
                lines=30,
                capacity_profile=BALANCED_TWO_COLUMN_BODY_V1,
            ),
            _NOTES,
        ],
        "continuations": ["content-stack"],
    },
    "concept-pair": {
        "intents": ["concept_explanation", "comparison", "misconception_repair"],
        "slots": [_TITLE, _slot("left", "body", chars=240), _slot("right", "body", chars=240), _NOTES],
        "continuations": ["content-stack"],
    },
    "classification-three": {
        "intents": ["concept_explanation", "comparison"],
        "slots": [
            _TITLE,
            _slot(
                "items",
                "items",
                items=3,
                chars=330,
                capacity_profile=CLASSIFICATION_THREE_CARDS_V1,
            ),
            _NOTES,
        ],
        "continuations": ["content-stack"],
    },
    "process-flow": {
        "intents": ["mechanism", "process", "artifact_explanation"],
        "artifact_kinds": ["diagram"],
        # Static bounds are only a last guard. The profile below measures each
        # 1-5 card combination with the renderer's real width/font/height cost.
        "slots": [
            _TITLE,
            _slot(
                "steps",
                "steps",
                items=5,
                chars=360,
                capacity_profile=HORIZONTAL_PROCESS_CARDS_V1,
            ),
            _slot("flow", "visual", required=False),
            _NOTES,
        ],
        "continuations": ["process-flow", "content-stack"],
    },
    "worked-example": {
        "intents": ["worked_example", "artifact_explanation"],
        "slots": [_TITLE, _slot("prompt", "body", chars=160), _slot("reasoning", "body", chars=300), _NOTES],
        "continuations": ["worked-example", "content-stack"],
    },
    "practice-prompt": {
        "intents": ["practice_feedback"],
        "slots": [_TITLE, _slot("task", "steps", items=5, chars=420, lines=12), _slot("criteria", "items", required=False, items=5, chars=220), _NOTES],
        "continuations": [
            "practice-prompt",
            "practice-feedback",
            "content-stack",
        ],
    },
    "practice-code": {
        "intents": ["artifact_explanation", "practice_feedback", "mechanism"],
        "artifact_kinds": ["code"],
        "slots": [
            _TITLE,
            _slot("code", "code", lines=12, chars=380),
            _slot("task", "steps", items=7, chars=294, lines=12),
            _NOTES,
        ],
        "continuations": [
            "practice-code", "practice-prompt", "evidence-code",
            "evidence-formula", "evidence-table",
        ],
        "base_layout": "practice-prompt",
    },
    "practice-formula": {
        "intents": ["artifact_explanation", "practice_feedback", "mechanism"],
        "artifact_kinds": ["formula"],
        "slots": [
            _TITLE,
            _slot("formula", "formula", chars=130, lines=5),
            _slot("task", "steps", items=7, chars=294, lines=12),
            _NOTES,
        ],
        "continuations": [
            "practice-formula", "practice-prompt", "evidence-formula",
            "evidence-code", "evidence-table",
        ],
        "base_layout": "practice-prompt",
    },
    "practice-table": {
        "intents": ["artifact_explanation", "practice_feedback", "comparison"],
        "artifact_kinds": ["table"],
        "slots": [
            _TITLE,
            _slot(
                "table",
                "table",
                rows=5,
                chars=560,
                split_wrapped_lines=7,
                full_wrapped_lines=7,
                split_column_chars=14,
                full_column_chars=20,
                wide_min_columns=3,
            ),
            _slot("task", "steps", items=7, chars=294, lines=12),
            _NOTES,
        ],
        "continuations": [
            "practice-table", "practice-prompt", "evidence-table",
            "evidence-code", "evidence-formula",
        ],
        "base_layout": "practice-prompt",
    },
    "practice-feedback": {
        "intents": ["practice_feedback", "misconception_repair"],
        "slots": [_TITLE, _slot("prompt", "body", chars=220, lines=12), _slot("feedback", "body", chars=300, lines=12), _NOTES],
        "continuations": ["practice-feedback", "content-stack"],
    },
    "evidence-code": {
        "intents": ["artifact_explanation", "worked_example", "mechanism"],
        "artifact_kinds": ["code"],
        "slots": [
            _TITLE,
            _slot(
                "code",
                "code",
                lines=13,
                chars=400,
                continuation_lines=13,
                continuation_chars=650,
            ),
            _slot("annotation", "body", required=False, chars=160),
            _NOTES,
        ],
        "continuations": [
            "evidence-code", "evidence-formula", "evidence-table", "content-stack",
        ],
    },
    "evidence-formula": {
        "intents": ["artifact_explanation", "mechanism", "worked_example"],
        "artifact_kinds": ["formula"],
        "slots": [
            _TITLE,
            _slot("formula", "formula", chars=150, lines=5),
            _slot(
                "derivation",
                "body",
                required=False,
                chars=360,
                capacity_profile=FORMULA_SOURCE_PANEL_V1,
            ),
            _NOTES,
        ],
        "continuations": [
            "evidence-formula", "evidence-code", "evidence-table", "content-stack",
        ],
    },
    "evidence-table": {
        "intents": ["artifact_explanation", "comparison", "worked_example", "misconception_repair"],
        "artifact_kinds": ["table", "data"],
        "slots": [
            _TITLE,
            _slot(
                "table",
                "table",
                rows=10,
                chars=900,
                split_wrapped_lines=9,
                full_wrapped_lines=8,
                split_column_chars=18,
                full_column_chars=36,
                wide_min_columns=3,
            ),
            _slot(
                "interpretation",
                "body",
                required=False,
                chars=220,
                capacity_profile=TABLE_SUPPORT_BAND_V1,
            ),
            _NOTES,
        ],
        "continuations": [
            "evidence-table", "evidence-code", "evidence-formula", "content-stack",
        ],
    },
    "evidence-figure": {
        "intents": ["artifact_explanation", "worked_example", "concept_explanation"],
        "artifact_kinds": ["image", "experiment", "source_excerpt"],
        "slots": [
            _TITLE,
            _slot("visual", "visual"),
            _slot(
                "interpretation",
                "body",
                chars=260,
                capacity_profile=FIGURE_SOURCE_PANEL_V1,
            ),
            _NOTES,
        ],
        "continuations": ["evidence-figure", "content-stack"],
    },
    "evidence-diagram": {
        "intents": ["artifact_explanation", "mechanism", "concept_explanation"],
        "artifact_kinds": ["diagram"],
        "slots": [
            _TITLE,
            _slot("diagram", "visual"),
            _slot(
                "explanation",
                "body",
                chars=240,
                capacity_profile=DIAGRAM_SOURCE_PANEL_V1,
            ),
            _NOTES,
        ],
        "continuations": ["evidence-diagram", "content-stack"],
    },
    "misconception-repair": {
        "intents": ["misconception_repair"],
        "slots": [_TITLE, _slot("symptom", "body", chars=170), _slot("cause", "body", chars=170), _slot("repair", "body", chars=220), _NOTES],
        "continuations": ["misconception-repair", "content-stack"],
    },
    "chapter-recap": {
        "intents": ["recap"],
        "slots": [_TITLE, _slot("takeaways", "items", items=6, chars=420), _NOTES],
        "continuations": [],
    },
    "course-synthesis": {
        "intents": ["recap", "transfer"],
        "slots": [_TITLE, _slot("synthesis", "body", chars=360), _slot("next_action", "body", chars=140), _NOTES],
        "continuations": [],
    },
}


def compile_builtin_template_layout_contract_v1(theme_id: str) -> TemplateLayoutPackContractV1:
    pack = load_slide_theme_pack()
    themes = pack.get("themes") or {}
    theme = themes.get(theme_id)
    if not isinstance(theme, dict):
        raise KeyError(theme_id)
    template = theme.get("template") or {}
    template_id = str(template.get("template_id") or theme_id)
    template_version = str(template.get("template_version") or pack.get("version") or "")
    prefix = f"{template_id}@{template_version}"
    layouts = [
        TemplateLayoutContractV1(
            template_layout_id=f"{prefix}/{slug}",
            layout_slug=slug,
            teaching_intents=list(spec["intents"]),
            artifact_kinds=list(spec.get("artifact_kinds") or []),
            slots=[TemplateSlotContractV1.model_validate(item) for item in spec["slots"]],
            safe_continuation_layout_slugs=list(spec.get("continuations") or []),
            base_layout_id=(
                f"{prefix}/{spec['base_layout']}"
                if spec.get("base_layout")
                else ""
            ),
        )
        for slug, spec in _LAYOUT_SPECS.items()
    ]
    digest_payload = {
        "theme_id": theme_id,
        "template_id": template_id,
        "template_version": template_version,
        "template_manifest": theme,
        "layouts": [layout.model_dump(mode="json") for layout in layouts],
    }
    return TemplateLayoutPackContractV1(
        template_id=template_id,
        template_version=template_version,
        template_digest=stable_hash(digest_payload, prefix="tmpl_"),
        theme_id=theme_id,
        layouts=layouts,
    )


def compile_personal_template_layout_contract_v1(
    manifest: dict[str, Any],
) -> TemplateLayoutPackContractV1:
    """Bind a confirmed personal template version to an explicit base contract."""

    pack_id = str(manifest.get("pack_id") or "").strip()
    version = int(manifest.get("version") or 0)
    if not pack_id or version < 1:
        raise TemplateLayoutContractError("personal_template_version_missing")
    if manifest.get("teaching_layouts"):
        from ppt_runtime_identity import tool_identity
        from ppt_layout_schema import LAYOUT_VERSION
        tools = tool_identity()
        reference = next((a for a in manifest.get("assets", []) if a.get("role") == "reference_pptx"), {})
        layouts = []
        for slug, item in manifest["teaching_layouts"].items():
            execution = LayoutExecution.model_validate(item.get("execution"))
            certificate = execution.certification
            if (not item.get("maintainer_reviewed") or execution.mode != "native_fill"
                    or execution.source_sha256 != reference.get("sha256")
                    or not execution.static_artwork_data
                    or certificate.get("status") != "passed" or certificate.get("tools") != tools
                    or certificate.get("component_version") != LAYOUT_VERSION
                    or not all(certificate.get("checks", {}).get(k) is True for k in ("short", "normal", "long", "relations", "render"))):
                raise TemplateLayoutContractError(f"personal_teaching_layout_uncertified:{slug}")
            layouts.append(TemplateLayoutContractV1(template_layout_id=f"{pack_id}@{version}/{slug}",
                layout_slug=slug, teaching_intents=execution.expression_kinds,
                slots=[TemplateSlotContractV1(slot_id="scene", slot_kind="visual")],
                web_renderer_adapter="teaching-scene-web-v2", pptx_renderer_adapter="teaching-scene-pptx-v2",
                execution=execution))
        return TemplateLayoutPackContractV1(template_id=pack_id, template_version=str(version),
            template_digest=stable_hash({"pack_id": pack_id, "version": version, "layouts": [l.model_dump(mode="json") for l in layouts]}, prefix="tmpl_"),
            theme_id=str(manifest.get("base_theme") or "academic-editorial"), layouts=layouts)
    representative_pages = manifest.get("representative_pages") or []
    by_role = {
        str(item.get("role") or ""): item
        for item in representative_pages
        if isinstance(item, dict)
    }
    required_roles = {"cover", "chapter", "content", "practice", "evidence", "recap"}
    if set(by_role) != required_roles or not all(
        bool(by_role[role].get("confirmed")) for role in required_roles
    ):
        raise TemplateLayoutContractError("representative_page_mapping_incomplete")
    extracted = manifest.get("extracted_style") or {}
    if str(extracted.get("aspect_ratio") or "") != "16:9" or bool(
        extracted.get("requires_widescreen_confirmation")
    ):
        raise TemplateLayoutContractError("template_aspect_ratio_unconfirmed")
    if len(manifest.get("text_box_styles") or {}) < 10:
        raise TemplateLayoutContractError("template_text_box_contract_incomplete")
    if len(manifest.get("semantic_page_mappings") or {}) < 18:
        raise TemplateLayoutContractError("template_required_layout_coverage_incomplete")
    base_theme = str(manifest.get("base_theme") or "")
    try:
        base = compile_builtin_template_layout_contract_v1(base_theme)
    except KeyError as exc:
        raise TemplateLayoutContractError("template_base_theme_unavailable") from exc
    has_construction_contract = "layout_constructions" in manifest
    constructions = {
        int(item.get("source_slide_number") or 0): item
        for item in manifest.get("layout_constructions") or []
        if isinstance(item, dict) and int(item.get("source_slide_number") or 0) > 0
    }
    if has_construction_contract and not constructions:
        raise TemplateLayoutContractError("template_layout_constructions_missing")

    def construction_role(layout: TemplateLayoutContractV1) -> str:
        slug = layout.layout_slug
        if slug == "cover-minimal":
            return "cover"
        if slug in {"chapter-entry", "agenda-path"}:
            return "chapter"
        if slug.startswith("practice-"):
            return "practice"
        if slug.startswith("evidence-"):
            return "evidence"
        if slug in {"chapter-recap", "course-synthesis"}:
            return "recap"
        return "content"

    prefix = f"{pack_id}@{version}"
    layouts: list[TemplateLayoutContractV1] = []
    if not has_construction_contract:
        # Preserve immutable versions published before the bidirectional
        # compiler existed.  New drafts always contain the construction key,
        # so they can never enter this compatibility branch silently.
        layouts = [
            layout.model_copy(
                update={
                    "template_layout_id": f"{prefix}/{layout.layout_slug}",
                    "base_layout_id": layout.template_layout_id,
                },
                deep=True,
            )
            for layout in base.layouts
        ]
    else:
        for layout in base.layouts:
            role = construction_role(layout)
            representative = by_role[role]
            slide_number = int(representative.get("slide_number") or 0)
            construction = constructions.get(slide_number)
            if construction is None:
                raise TemplateLayoutContractError(
                    f"template_representative_construction_missing:{role}:{slide_number}"
                )
            raw_frames = construction.get("slot_frames") or {}
            slot_frames = {
                str(slot_id): TemplateFrameContractV1.model_validate(frame)
                for slot_id, frame in raw_frames.items()
                if isinstance(frame, dict)
            }
            fitted_slots: list[TemplateSlotContractV1] = []
            for slot in layout.slots:
                frame = slot_frames.get(slot.slot_id)
                if frame is None or slot.slot_kind in {"notes", "visual"}:
                    fitted_slots.append(slot.model_copy(deep=True))
                    continue
                area = frame.width * frame.height
                estimated_lines = max(1, int(frame.height * 25))
                # A title is constrained mainly by horizontal line length,
                # not by total box area.  The previous area-only estimate let
                # a one-line 10-inch title claim 42 CJK characters even though
                # PowerPoint wrapped it at roughly 22–24.  Feed the realistic
                # capacity back into story planning so the model selects a
                # concise, source-grounded title before the render gate.
                estimated_chars = max(
                    slot.min_chars,
                    int(
                        frame.width
                        * (28 if slot.slot_kind == "title" else 1_550 * frame.height)
                        * (estimated_lines if slot.slot_kind == "title" else 1)
                    ),
                )
                estimated_items = max(1, int(frame.height * 10))
                fitted_slots.append(
                    slot.model_copy(
                        update={
                            "max_chars": (
                                min(slot.max_chars, estimated_chars)
                                if slot.max_chars
                                else 0
                            ),
                            "max_lines": (
                                min(slot.max_lines, estimated_lines)
                                if slot.max_lines
                                else 0
                            ),
                            "max_items": (
                                min(slot.max_items, estimated_items)
                                if slot.max_items
                                else 0
                            ),
                        },
                        deep=True,
                    )
                )
            source_layout_id = str(
                construction.get("construction_id") or f"source-slide-{slide_number}"
            )
            layouts.append(
                layout.model_copy(
                    update={
                        "template_layout_id": f"{prefix}/{layout.layout_slug}",
                        "base_layout_id": source_layout_id,
                        "construction_role": role,
                        "source_slide_number": slide_number,
                        "source_layout_name": str(
                            construction.get("source_layout_name") or ""
                        ),
                        "source_layout_hint": str(
                            construction.get("layout_hint") or ""
                        ),
                        "fill_strategy": str(
                            construction.get("fill_strategy") or "adaptive_overlay"
                        ),
                        "slot_frames": slot_frames,
                        "slots": fitted_slots,
                        "web_renderer_adapter": "personal-template-geometry-web-v1",
                        "pptx_renderer_adapter": "personal-template-geometry-pptx-v1",
                    },
                    deep=True,
                )
            )
    digest_payload = {
        "pack_id": pack_id,
        "version": version,
        "base_digest": base.template_digest,
        "representative_pages": representative_pages,
        "extracted_style": extracted,
        "text_box_styles": manifest.get("text_box_styles") or {},
        "semantic_page_mappings": manifest.get("semantic_page_mappings") or {},
        "asset_digests": [
            str(item.get("sha256") or "")
            for item in manifest.get("assets") or []
            if isinstance(item, dict)
        ],
    }
    if has_construction_contract:
        digest_payload["layout_constructions"] = (
            manifest.get("layout_constructions") or []
        )
    compiled_theme = manifest.get("compiled_theme") or {}
    colors = {
        str(key): str(value).strip().lstrip("#").upper()
        for key, value in (extracted.get("colors") or {}).items()
        if isinstance(value, str)
        and len(str(value).strip().lstrip("#")) == 6
        and all(character in "0123456789ABCDEFabcdef" for character in str(value).strip().lstrip("#"))
    }
    color_mapping = {
        "accent1": "accent",
        "accent2": "green",
        "accent3": "amber",
        "dk1": "title",
        "dk2": "ink",
        "lt1": "surface",
        "lt2": "canvas",
    }
    render_theme_overrides = {
        destination: colors[source]
        for source, destination in color_mapping.items()
        if source in colors
    }
    # Brand choices are the teacher-confirmed output contract.  Extracted
    # source fonts/colors are useful fallbacks, but must not overwrite the
    # compiled brand with Calibri or the base theme after publication.
    for destination in (
        "surface",
        "canvas",
        "chart_bg",
        "title",
        "ink",
        "muted",
        "accent",
        "accent_soft",
        "green",
        "green_soft",
        "amber",
        "amber_soft",
        "red",
        "red_soft",
        "code",
    ):
        value = str(compiled_theme.get(destination) or "").strip().lstrip("#")
        if len(value) == 6 and all(character in "0123456789ABCDEFabcdef" for character in value):
            render_theme_overrides[destination] = value.upper()
    for source, destination in (("title_font", "title_font"), ("body_font", "body_font")):
        value = str(compiled_theme.get(source) or extracted.get(source) or "").strip()
        if value and len(value) <= 120 and not any(ord(character) < 32 for character in value):
            render_theme_overrides[destination] = value
    return TemplateLayoutPackContractV1(
        template_id=pack_id,
        template_version=str(version),
        template_digest=stable_hash(digest_payload, prefix="tmpl_"),
        theme_id=base_theme,
        render_theme_overrides=render_theme_overrides,
        layouts=layouts,
    )


__all__ = [
    "TemplateLayoutContractV1",
    "TemplateLayoutContractError",
    "TemplateFrameContractV1",
    "TemplateLayoutPackContractV1",
    "TemplateSlotContractV1",
    "compile_builtin_template_layout_contract_v1",
    "compile_personal_template_layout_contract_v1",
    "template_layout_contract_matrix",
]
