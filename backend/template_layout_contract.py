"""Closed, versioned layout registry for slide-deck V6."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from course_document import stable_hash
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
        "code",
        "formula",
        "table",
        "visual",
        "notes",
    ]
    required: bool = True
    max_chars: int = Field(default=0, ge=0)
    max_items: int = Field(default=0, ge=0)
    max_lines: int = Field(default=0, ge=0)
    max_rows: int = Field(default=0, ge=0)


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
    web_renderer_adapter: str = "template-layout-web-v1"
    pptx_renderer_adapter: str = "template-layout-pptx-v1"


class TemplateLayoutPackContractV1(_StrictModel):
    schema_version: Literal["template_layout_pack_contract_v1"] = (
        "template_layout_pack_contract_v1"
    )
    template_id: str
    template_version: str
    template_digest: str
    theme_id: str
    layouts: list[TemplateLayoutContractV1] = Field(min_length=1)

    def layout_id(self, slug: str) -> str:
        candidate = next((item.template_layout_id for item in self.layouts if item.layout_slug == slug), "")
        if not candidate:
            raise KeyError(slug)
        return candidate

    def get_layout(self, layout_id: str) -> TemplateLayoutContractV1 | None:
        return next((item for item in self.layouts if item.template_layout_id == layout_id), None)


def _slot(
    slot_id: str,
    kind: str,
    *,
    required: bool = True,
    chars: int = 0,
    items: int = 0,
    lines: int = 0,
    rows: int = 0,
) -> dict[str, Any]:
    return {
        "slot_id": slot_id,
        "slot_kind": kind,
        "required": required,
        "max_chars": chars,
        "max_items": items,
        "max_lines": lines,
        "max_rows": rows,
    }


_TITLE = _slot("title", "title", chars=42)
_EYEBROW = _slot("eyebrow", "eyebrow", required=False, chars=24)
_NOTES = _slot("source_notes", "notes", chars=0)


_LAYOUT_SPECS: dict[str, dict[str, Any]] = {
    "cover-minimal": {
        "intents": ["orientation"],
        "slots": [_TITLE, _slot("subtitle", "body", required=False, chars=90), _NOTES],
        "continuations": [],
    },
    "chapter-entry": {
        "intents": ["orientation", "concept_explanation"],
        "slots": [_EYEBROW, _TITLE, _slot("driving_question", "body", chars=120), _NOTES],
        "continuations": ["content-stack"],
    },
    "agenda-path": {
        "intents": ["orientation", "recap"],
        "slots": [_TITLE, _slot("agenda_items", "items", items=6, chars=180), _NOTES],
        "continuations": [],
    },
    "content-stack": {
        "intents": ["concept_explanation", "mechanism", "recap", "worked_example"],
        "slots": [_EYEBROW, _TITLE, _slot("body", "body", chars=520), _NOTES],
        "continuations": ["content-stack"],
    },
    "concept-pair": {
        "intents": ["concept_explanation", "comparison", "misconception_repair"],
        "slots": [_TITLE, _slot("left", "body", chars=240), _slot("right", "body", chars=240), _NOTES],
        "continuations": ["content-stack"],
    },
    "classification-three": {
        "intents": ["concept_explanation", "comparison"],
        "slots": [_TITLE, _slot("items", "items", items=3, chars=330), _NOTES],
        "continuations": ["content-stack"],
    },
    "process-flow": {
        "intents": ["mechanism", "process", "artifact_explanation"],
        "artifact_kinds": ["diagram"],
        "slots": [_TITLE, _slot("steps", "items", items=6, chars=360), _slot("flow", "visual", required=False), _NOTES],
        "continuations": ["process-flow", "content-stack"],
    },
    "worked-example": {
        "intents": ["worked_example", "artifact_explanation"],
        "slots": [_TITLE, _slot("prompt", "body", chars=160), _slot("reasoning", "body", chars=300), _NOTES],
        "continuations": ["worked-example", "content-stack"],
    },
    "practice-prompt": {
        "intents": ["practice_feedback"],
        "slots": [_TITLE, _slot("task", "body", chars=280), _slot("criteria", "items", required=False, items=5, chars=220), _NOTES],
        "continuations": ["practice-prompt", "practice-feedback"],
    },
    "practice-feedback": {
        "intents": ["practice_feedback", "misconception_repair"],
        "slots": [_TITLE, _slot("prompt", "body", chars=220), _slot("feedback", "body", chars=300), _NOTES],
        "continuations": ["practice-feedback"],
    },
    "evidence-code": {
        "intents": ["artifact_explanation", "worked_example", "mechanism"],
        "artifact_kinds": ["code"],
        "slots": [_TITLE, _slot("code", "code", lines=28, chars=1800), _slot("annotation", "body", chars=220), _NOTES],
        "continuations": ["evidence-code"],
    },
    "evidence-formula": {
        "intents": ["artifact_explanation", "mechanism", "worked_example"],
        "artifact_kinds": ["formula"],
        "slots": [_TITLE, _slot("formula", "formula", chars=420), _slot("derivation", "body", chars=360), _NOTES],
        "continuations": ["evidence-formula"],
    },
    "evidence-table": {
        "intents": ["artifact_explanation", "comparison", "worked_example", "misconception_repair"],
        "artifact_kinds": ["table", "data"],
        "slots": [_TITLE, _slot("table", "table", rows=10, chars=900), _slot("interpretation", "body", chars=220), _NOTES],
        "continuations": ["evidence-table"],
    },
    "evidence-figure": {
        "intents": ["artifact_explanation", "worked_example", "concept_explanation"],
        "artifact_kinds": ["image", "experiment", "source_excerpt"],
        "slots": [_TITLE, _slot("visual", "visual"), _slot("interpretation", "body", chars=260), _NOTES],
        "continuations": ["evidence-figure", "content-stack"],
    },
    "evidence-diagram": {
        "intents": ["artifact_explanation", "mechanism", "concept_explanation"],
        "artifact_kinds": ["diagram"],
        "slots": [_TITLE, _slot("diagram", "visual"), _slot("explanation", "body", chars=240), _NOTES],
        "continuations": ["evidence-diagram", "content-stack"],
    },
    "misconception-repair": {
        "intents": ["misconception_repair"],
        "slots": [_TITLE, _slot("symptom", "body", chars=170), _slot("cause", "body", chars=170), _slot("repair", "body", chars=220), _NOTES],
        "continuations": ["misconception-repair"],
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
    prefix = f"{pack_id}@{version}"
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
    return TemplateLayoutPackContractV1(
        template_id=pack_id,
        template_version=str(version),
        template_digest=stable_hash(digest_payload, prefix="tmpl_"),
        theme_id=base_theme,
        layouts=layouts,
    )


__all__ = [
    "TemplateLayoutContractV1",
    "TemplateLayoutContractError",
    "TemplateLayoutPackContractV1",
    "TemplateSlotContractV1",
    "compile_builtin_template_layout_contract_v1",
    "compile_personal_template_layout_contract_v1",
]
