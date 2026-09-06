"""Small layout-specific model forms lowered into the existing manuscript.

Source IDs, reveal bookkeeping and geometry stay in code. Model requests carry
only the chosen form, source excerpts and teacher context, never layout code.
"""
from copy import deepcopy
from typing import Literal

from pydantic import Field, create_model

from ppt_draft_common import QuoteChoice
from ppt_teaching_content import Contract
from ppt_fixed_templates import LAYOUTS, fixed_slug


class TextField(Contract):
    text: str = Field(min_length=1, max_length=140)
    sources: list[QuoteChoice] = Field(min_length=1)


class ExactField(Contract):
    sources: list[QuoteChoice] = Field(min_length=1, max_length=1)


class FixedDraft(Contract):
    title: str = Field(min_length=1, max_length=28)
    notes: str = Field(min_length=1, max_length=500)
    split_reason: str = ""


class ComparisonRow(Contract):
    dimension: TextField
    left: TextField
    right: TextField


def form_type(slug):
    def required(kind):
        return (kind, ...)
    if slug == "comparison":
        fields = {"condition": required(TextField), "left_subject": required(TextField), "right_subject": required(TextField),
                  "rows": (list[ComparisonRow], Field(min_length=1, max_length=3)),
                  "conclusion": (TextField | None, None)}
    elif slug == "question":
        fields = {"question": required(TextField), "answer": required(TextField)}
    elif slug == "formula":
        fields = {"formula": required(ExactField), "explanation": (TextField | None, None)}
    elif slug == "figure":
        fields = {"asset_id": required(str), "caption": required(TextField),
                  "explanation": (TextField | None, None)}
    elif slug in {"cover", "section"}:
        fields = {"subtitle": required(TextField)}
    else:
        fields = {"steps" if slug == "flow" else "points": (list[TextField],
                    Field(min_length=3 if slug == "flow" else 1, max_length=LAYOUTS[slug][2]))}
    return create_model("Fixed" + slug.title(), __base__=FixedDraft, **fields)


def form_schema(layout_id):
    form = form_type(fixed_slug(layout_id))
    # A capacity repair may split only this task, in the same authored layout.
    group = create_model("FixedPageGroup", pages=(list[form], Field(min_length=1, max_length=4)))
    from pydantic import TypeAdapter
    return TypeAdapter(form | group).json_schema()


def lower_fixed_response(response, plan, assets=()):
    slug = fixed_slug(plan["layout_id"])
    if isinstance(response, dict) and set(response) == {"pages"}:
        parts = response["pages"]
        if not isinstance(parts, list) or not 1 <= len(parts) <= 4:
            raise ValueError("fixed_page_group_invalid")
        if len(parts) > 1 and any(not str(p.get("split_reason") or "").strip() for p in parts):
            raise ValueError("fixed_page_split_reason_required")
        return {"pages": [lower_fixed_response(p, plan, assets) for p in parts]}
    data = form_type(slug).model_validate(response).model_dump(mode="json")
    base = {"title": data["title"], "layout_id": plan["layout_id"],
            "page_goal": plan["page_goal"], "split_reason": data["split_reason"],
            "reveal_notes": [data["notes"]], "presentation": {"mode": "complete"}}

    def element(value, key, *, role="evidence", kind="text", stage=1):
        if kind == "text" and len(value["text"]) > LAYOUTS[slug][3]:
            raise ValueError(f"fixed_field_text_too_long:{key}:maximum={LAYOUTS[slug][3]}")
        return {**value, "key": key, "role": role, "kind": kind, "show_from": stage}

    if slug == "comparison":
        rows = data["rows"]
        return {**base, "expression_kind": "comparison",
            "conditions": [element(data["condition"], "condition")],
            "subjects": [element(data["left_subject"], "left"), element(data["right_subject"], "right")],
            "dimensions": [element(r["dimension"], f"dim-{i}") for i, r in enumerate(rows)],
            "cells": [{"subject_key": side, "dimension_key": f"dim-{i}", "content": [element(r[side], f"{side}-{i}")]}
                      for i, r in enumerate(rows) for side in ("left", "right")],
            "conclusion": element(data["conclusion"], "conclusion") if data["conclusion"] else None}
    kind = LAYOUTS[slug][0]
    relations = []
    if slug == "question":
        question = element(data["question"], "question", role="question")
        answer = element(data["answer"], "answer", role="answer", stage=2)
        answer["answers_question_id"] = "question"
        elements = [question, answer]
        base.update(presentation={"mode": "question_answer"}, reveal_notes=[data["notes"], data["notes"]])
    elif slug == "formula":
        elements = [{**element(data["formula"], "formula", kind="formula"), "use_source_text": True}]
        if data["explanation"]:
            elements.append(element(data["explanation"], "explanation"))
    elif slug == "figure":
        asset = next((a for entry in assets if entry.get("kind") == "image"
                      for a in entry.get("assets", []) if a.get("asset_id") == data["asset_id"]), None)
        if asset is None:
            raise ValueError("fixed_figure_asset_unavailable")
        elements = [{**element(data["caption"], "image", kind="image"), "asset_id": asset["asset_id"],
                     "asset_digest": asset.get("sha256", asset.get("asset_digest", ""))},
                    element(data["caption"], "caption")]
        if data["explanation"]:
            elements.append(element(data["explanation"], "explanation"))
    elif slug in {"cover", "section"}:
        elements = [element(data["subtitle"], "subtitle")]
    else:
        values = data["steps" if slug == "flow" else "points"]
        elements = [element(v, f"item-{i}") for i, v in enumerate(values)]
        if slug == "flow":
            relations = [{"source_key": a["key"], "target_key": b["key"], "kind": "sequence",
                          "sources": a["sources"] + b["sources"]} for a, b in zip(elements, elements[1:])]
    return {**base, "expression_kind": kind, "elements": elements, "relations": relations}


async def invoke_fixed_form(planner, request):
    """Adapter within the existing planner, also used by selected-page retries."""
    plan = request.get("page") or request.get("current_page")
    if not plan:
        return await planner(request)
    slug = fixed_slug(plan["layout_id"])
    compact = {"teaching_request": "fixed_fields", "page": {k: plan[k] for k in ("title", "page_goal", "layout_id")},
        "response_contract": form_schema(plan["layout_id"]),
        "field_limits": {"text_max_chars": LAYOUTS[slug][3], "title_max_chars": 28},
        "literal_source_ranges": request.get("literal_source_ranges", []),
        "accepted_visual_expressions": request.get("accepted_visual_expressions", []),
        "validation_error": request.get("validation_error", ""),
        "instruction": "Fill only this predesigned layout. Cite supplied quote_id for each field. "
            "Keep ordinary text concise, full explanations in notes. Never return geometry, fonts or a different layout. "
            "A flow lists actual sequential steps, not unrelated concepts. A comparison aligns both objects by common dimensions. "
            "For formula select one exact quote; never rewrite it. If this task cannot fit, return pages of the same form, "
            "each with a split_reason; preserve complete questions and do not omit essential content."}
    response = await planner(compact)
    try:
        lowered = lower_fixed_response(dict(response), plan, compact["accepted_visual_expressions"])
    except ValueError as exc:
        lowered = {"_fixed_form_error": str(exc)}
    # Keep provider telemetry on the dict subclass consumed by the existing task.
    result = deepcopy(response)
    result.clear()
    result.update(lowered)
    return result
