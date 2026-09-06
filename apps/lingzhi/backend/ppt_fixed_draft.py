"""Small layout-specific model forms lowered into the existing manuscript.

Source IDs, reveal bookkeeping and geometry stay in code. Model requests carry
only the chosen form, source excerpts and teacher context, never layout code.
"""
from copy import deepcopy
from pydantic import Field, create_model

from ppt_draft_common import QuoteChoice
from ppt_teaching_content import Contract
from ppt_fixed_templates import LAYOUTS, VERSION, fixed_slug, layout_limits


class TextField(Contract):
    text: str = Field(min_length=1, max_length=140)
    sources: list[QuoteChoice] = Field(min_length=1)


class ExactField(Contract):
    sources: list[QuoteChoice] = Field(min_length=1, max_length=1)


class ExplainedPoint(TextField):
    text: str = Field(min_length=1, max_length=52)
    heading: str = Field(default="", max_length=18)


class FixedDraft(Contract):
    title: str = Field(min_length=1, max_length=28)
    notes: str = Field(min_length=1, max_length=500)
    split_reason: str = ""


class ComparisonRow(Contract):
    dimension: TextField
    left: TextField
    right: TextField


def form_type(slug, *, authored=False):
    def required(kind):
        return (kind, ...)
    def text_type(limit):
        return create_model(f"TextUpTo{limit}", __base__=TextField, text=(str, Field(min_length=1, max_length=limit))) if authored else TextField
    if slug == "comparison":
        row_type = create_model("AlignedRow", dimension=required(text_type(12)), left=required(text_type(28)),
                                right=required(text_type(28)), __base__=Contract) if authored else ComparisonRow
        fields = {"condition": required(text_type(38)), "left_subject": required(text_type(12)), "right_subject": required(text_type(12)),
                  "rows": (list[row_type], Field(min_length=1, max_length=3)),
                  "conclusion": (text_type(32) | None, None)}
    elif slug == "question":
        fields = {"question": required(text_type(112)), "answer": required(TextField)}
    elif slug == "formula":
        fields = {"formula": required(ExactField), "explanation": (TextField | None, None)}
    elif slug == "code":
        fields = {"code": required(ExactField), "explanation": (text_type(60) | None, None)}
    elif slug in {"chart", "chart_explanation"}:
        point_type = create_model("ChartField", label=required(text_type(6)), value=required(ExactField), __base__=Contract)
        fields = {"unit": required(ExactField), "points": (list[point_type], Field(min_length=2, max_length=6))}
        if slug == "chart_explanation":
            fields["explanation"] = (text_type(44) | None, None)
    elif slug == "radial":
        satellite_type = create_model("RadialSatellite", text=(str, Field(min_length=1, max_length=36)), sources=(list[QuoteChoice], Field(min_length=1)), __base__=Contract)
        fields = {"center": required(text_type(36)), "satellites": (list[satellite_type], Field(min_length=3, max_length=3))}
    elif slug == "figure":
        fields = {"asset_id": required(str), "caption": required(text_type(30)),
                  "explanation": (TextField | None, None)}
    elif slug in {"cover", "section"}:
        fields = {"subtitle": required(TextField)}
    else:
        point = ExplainedPoint if authored and slug in {"bullets", "summary"} else text_type(28 if slug == "flow" else 32)
        count = min(3, LAYOUTS[slug][2]) if authored and slug in {"bullets", "summary"} else layout_limits(f"x@{VERSION}/{slug}")[2]
        if slug == "flow6":
            minimum = 5
        else:
            minimum = 3 if slug == "flow" else 1
        fields = {"steps" if slug in {"flow", "flow6"} else "points": (list[point],
                    Field(min_length=minimum, max_length=count))}
    return create_model("Fixed" + slug.title(), __base__=FixedDraft, **fields)


def form_schema(layout_id):
    form = form_type(fixed_slug(layout_id), authored=f"@{VERSION}/" in layout_id)
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
    data = form_type(slug, authored=f"@{VERSION}/" in plan["layout_id"]).model_validate(response).model_dump(mode="json")
    base = {"title": data["title"], "layout_id": plan["layout_id"],
            "page_goal": plan["page_goal"], "split_reason": data["split_reason"],
            "reveal_notes": [data["notes"]], "presentation": {"mode": "complete"}}

    def element(value, key, *, role="evidence", kind="text", stage=1):
        if kind == "text" and len(value["text"]) > layout_limits(plan["layout_id"])[3]:
            raise ValueError(f"fixed_field_text_too_long:{key}:maximum={layout_limits(plan['layout_id'])[3]}")
        return {**value, "key": key, "role": role, "kind": kind, "show_from": stage}

    if slug == "radial":
        center = element(data["center"], "center", role="claim")
        satellites = [element(item, f"satellite-{i}") for i, item in enumerate(data["satellites"])]
        elements = [center, *satellites]
        relations = [{"source_key": "center", "target_key": f"satellite-{i}",
                      "kind": "association", "sources": center["sources"] + satellites[i]["sources"]}
                     for i in range(3)]
        return {**base, "expression_kind": "concept", "elements": elements, "relations": relations}
    if slug == "comparison":
        rows = data["rows"]
        return {**base, "expression_kind": "comparison",
            "conditions": [element(data["condition"], "condition")],
            "subjects": [element(data["left_subject"], "left"), element(data["right_subject"], "right")],
            "dimensions": [element(r["dimension"], f"dim-{i}") for i, r in enumerate(rows)],
            "cells": [{"subject_key": side, "dimension_key": f"dim-{i}", "content": [element(r[side], f"{side}-{i}")]}
                      for i, r in enumerate(rows) for side in ("left", "right")],
            "conclusion": element(data["conclusion"], "conclusion") if data["conclusion"] else None}
    kind = layout_limits(plan["layout_id"])[0]
    relations = []
    if slug in {"chart", "chart_explanation"}:
        elements = [{**element(data["unit"], "unit", kind="quote"), "use_source_text": True}]
        points = []
        for i, point in enumerate(data["points"]):
            label, value = f"label-{i}", f"value-{i}"
            elements.extend([element(point["label"], label), {**element(point["value"], value, kind="data"), "use_source_text": True}])
            points.append({"label_element_id": label, "value_element_id": value})
        if slug == "chart_explanation" and data.get("explanation"):
            elements.append(element(data["explanation"], "explanation", role="claim"))
        return {**base, "expression_kind": "chart", "elements": elements, "chart_points": points,
                "chart_unit_key": "unit", "chart_explanation_key": "explanation" if slug == "chart_explanation" and data.get("explanation") else ""}
    elif slug == "question":
        question = element(data["question"], "question", role="question")
        answer = element(data["answer"], "answer", role="answer", stage=2)
        answer["answers_question_id"] = "question"
        elements = [question, answer]
        base.update(presentation={"mode": "question_answer"}, reveal_notes=[data["notes"], data["notes"]])
    elif slug in {"formula", "code"}:
        elements = [{**element(data[slug], slug, kind=slug), "use_source_text": True}]
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
        values = data["steps" if slug in {"flow", "flow6"} else "points"]
        elements = []
        for i, value in enumerate(values):
            value = dict(value)
            heading = value.pop("heading", "")
            if heading:
                elements.append(element({"text": heading, "sources": value["sources"]}, f"item-{i}-heading"))
            elements.append(element(value, f"item-{i}"))
        if slug in {"flow", "flow6"}:
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
        "field_limits": {"text_max_chars": layout_limits(plan["layout_id"])[3], "title_max_chars": 28},
        "literal_source_ranges": request.get("literal_source_ranges", []),
        "accepted_visual_expressions": request.get("accepted_visual_expressions", []),
        "accepted_question_bank_items": request.get("accepted_question_bank_items", []),
        "lesson_context": request.get("narrative_brief", {}),
        "page_sequence": request.get("page_sequence", []),
        "physical_page_budget": request.get("physical_page_budget"),
        "validation_error": request.get("validation_error", ""),
        "instruction": "Fill only this predesigned layout. Cite supplied quote_id for each field. "
            "Keep ordinary text concise, full explanations in notes. Every page must add a distinct teaching point, example, "
            "decision or explanation, rather than repeat the agenda. Use optional short headings to separate a point's name "
            "from its explanation; never repeat the heading in its body. Do not reduce substantive source material to generic slogans. "
            "A short list of topic names belongs on an agenda, not a standalone explanation page. "
            "Never return geometry, fonts or a different layout. "
            "A flow lists actual sequential steps, not unrelated concepts. flow6 is reserved for five or six real steps. "
            "four_stage contains four related phases; triad and mechanism_stack contain three parallel scenes or mechanisms; radial contains one center and three connected concepts. "
            "A comparison aligns both objects by common dimensions. "
            "For formula, code, chart values and units select exact source quotes; never rewrite them. "
            "Charts support only nonnegative decimal values in one common unit; never invent data or labels. "
            "Code preserves indentation and has room for a short excerpt, not an entire program. "
            "If this task cannot fit, return pages of the same form, "
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
