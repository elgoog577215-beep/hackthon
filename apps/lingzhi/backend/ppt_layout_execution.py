"""Versioned, measured teaching layout capabilities; no content generation."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Literal

from PIL import ImageFont, features
from pydantic import Field

from ppt_teaching_content import Contract

ASSET_ROOT = Path(__file__).resolve().parents[1] / "frontend/public/presentation-assets"
FONT_PATH = ASSET_ROOT / "fonts/NotoSansCJKsc-Regular.otf"
from ppt_layout_schema import (FONT_FAMILY, COMPILER_VERSION, RENDERER_VERSION, QUALITY_VERSION, LAYOUT_VERSION, PLANNER_VERSION, NativeTarget, LayoutExecution)


from ppt_runtime_identity import file_digest, tool_identity


@lru_cache(maxsize=48)
def _font(size: int, digest: str):
    return ImageFont.truetype(str(FONT_PATH), size)


def wrap_text(text: str, width: float, size: float, *, font_digest: str) -> list[str]:
    """Resolve line breaks once, in slide points, for preview and PowerPoint."""
    if file_digest(FONT_PATH) != font_digest:
        raise ValueError("teaching_font_changed")
    font = _font(round(size * 4), font_digest)
    lines = []
    for paragraph in text.split("\n"):
        line = ""
        for character in paragraph:
            if font.getlength(character) / 4 > width:
                raise ValueError("teaching_text_capacity_exceeded")
            candidate = line + character
            if line and font.getlength(candidate) / 4 > width:
                lines.append(line)
                line = character
            else:
                line = candidate
        lines.append(line)
    return lines


def validate_text_frame(text: str, width: float, height: float, size: float, font_digest: str) -> list[str]:
    lines = wrap_text(text, width - 16, size, font_digest=font_digest)
    if len(lines) * size * 1.3 + 12 > height:
        raise ValueError("teaching_text_capacity_exceeded")
    return lines


_LAYOUTS = {
    "compare-visual": ["comparison"],
    "compare-matrix": ["comparison"],
    "problem-focus": ["problem"],
    "concept-map": ["concept"],
    "relation-flow": ["process", "causal"],
    "step-derivation": ["derivation"],
    "exercise-states": ["exercise"],
    "lesson-recap": ["recap"],
    "lesson-cover": ["cover"],
    "lesson-agenda": ["agenda"],
    "hierarchy-map": ["hierarchy"],
    "source-evidence": ["evidence"],
    "data-bars": ["chart"],
}


def certification_version(manifest: dict) -> str:
    digest = hashlib.sha256(json.dumps(manifest, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]
    return f"{LAYOUT_VERSION}-{digest}"


def compile_teaching_template(theme_id: str, *, certification_required: bool = True, version: str = ""):
    """Produce another immutable version in the existing template contract."""
    from course_document import stable_hash
    from template_layout_contract import TemplateLayoutContractV1, TemplateLayoutPackContractV1, TemplateSlotContractV1
    if theme_id not in {"academic-editorial", "qizhi-classroom"}:
        raise ValueError("teaching_theme_uncertified")
    manifest_path = ASSET_ROOT / "teaching-layouts" / (f"versions/{theme_id}--{version}.json" if version else f"{theme_id}.json")
    manifest = json.loads(manifest_path.read_text()) if manifest_path.is_file() else {}
    tools = tool_identity()
    layouts = []
    template_version = certification_version(manifest)
    if version and version != template_version:
        raise ValueError("teaching_template_version_missing")
    prefix = f"{theme_id}@{template_version}"
    for slug, kinds in _LAYOUTS.items():
        certification = manifest.get("layouts", {}).get(slug, {})
        certified = (
            certification.get("status") == "passed"
            and certification.get("tools") == tools
            and certification.get("component_version") == LAYOUT_VERSION
            and all(certification.get("checks", {}).get(k) is True for k in ("short", "normal", "long", "relations", "render"))
        )
        if certification_required and not certified:
            continue
        execution = LayoutExecution(
            mode="component_render", component_id=slug, expression_kinds=kinds,
            max_subjects=4 if slug == "compare-matrix" else 2,
            font_sha256=tools["font_sha256"], certification=certification,
        )
        layouts.append(TemplateLayoutContractV1(
            template_layout_id=f"{prefix}/{slug}", layout_slug=slug,
            teaching_intents=kinds, artifact_kinds=[],
            slots=[TemplateSlotContractV1(slot_id="scene", slot_kind="visual")],
            web_renderer_adapter="teaching-scene-web-v2",
            pptx_renderer_adapter="teaching-scene-pptx-v2",
            execution=execution,
        ))
    if not layouts:
        raise ValueError("teaching_template_certification_missing")
    payload = {"theme_id": theme_id, "version": LAYOUT_VERSION, "layouts": [x.model_dump(mode="json") for x in layouts]}
    return TemplateLayoutPackContractV1(
        template_id=theme_id, template_version=template_version,
        template_digest=stable_hash(payload, prefix="tmpl_"), theme_id=theme_id,
        layouts=layouts,
    )


def capability_summary(template) -> list[dict]:
    return [{
        "layout_id": l.template_layout_id,
        "expression_kinds": l.execution.expression_kinds,
        "max_subjects": l.execution.max_subjects,
        "max_dimensions": l.execution.max_dimensions,
        "max_nodes": l.execution.max_nodes,
        "font_floor_pt": l.execution.font_floor_pt,
        "composition_guidance": (
            "Common conditions and the optional question each use one short line. The conclusion uses one short line. "
            "Subject column headers also fit only ONE short line: use a concise identity label, not a complete explanation. "
            "All cells remain in their fixed subject-column and dimension-row. Four dimensions permit only short cell labels; "
            "Rows share the available height according to measured text/formula height; complex comparisons need fewer dimensions. "
            "A multiline formula, code or diagram normally needs ONE dimension and few elements per cell. "
            "For a question comparing several formula options, use compare-matrix: each option is one subject, "
            "a single shared dimension contains its formula, and the screen question remains above the matrix. "
            "Do not stack multiple option labels and formulas as separate full-width linear rows. "
            "Do not place a multiline equation in the common-condition strip. Keep each dimension semantically consistent: "
            "if the dimension asks for a count, a matrix row is not an answer. Do not invent numeric counts to fill cells. "
            "Relations join elements within the SAME subject; they never connect the compared subject labels."
            if l.layout_slug.startswith("compare-") else
            "Horizontal data bars require 2-6 source-exact nonnegative decimal values and a source-exact shared unit. "
            "Keep category labels short. Values share one zero baseline and fixed scale across reveal states. "
            "No negative values, percentages embedded in values, mixed units, logarithmic scales or invented statistics. "
            if l.layout_slug == "data-bars" else
            "Graph pages normally use 2-5 concise nodes, each one or two short lines, with explicit source-backed edges. "
            "Graph nodes are at most 210x108pt and become smaller as more layers/nodes are added. "
            "Complete definitions, explanations and background remain in the already preserved speaker notes. "
            "Show only information necessary for THIS page goal, not every idea from the source block. "
            "Linear pages allocate height from measured text/formula lines, keeping every reveal state in the same position. "
            "Each added element reduces room for others; use a separate page for a large formula or code."
        ),
    } for l in template.layouts if l.execution is not None]
