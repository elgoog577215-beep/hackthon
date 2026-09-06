"""Code-authored classroom layouts adapted from Qizhi's six-layout deck.

The original Qizhi renderer lives in apps/qizhi/server/agents/ppt/pptx_render.py.
We retain its title/body/footer hierarchy, but publish fixed field capacities
and resolve the same scene for the existing Lingzhi editor and native export.
No import from the other application's runtime is needed.
"""
from course_document import stable_hash
from ppt_layout_execution import FONT_PATH, file_digest
from ppt_layout_schema import LayoutExecution
from slide_theme import load_slide_theme_pack

from ppt_classroom_design import VERSION
LEGACY_VERSION = "fixed_classroom_v1"
VERSIONS = {LEGACY_VERSION, VERSION}
COMPONENT_PREFIX = "fixed-classroom/"

# Each entry is both the planner's field contract and the scene's layout key.
LAYOUTS = {
    "cover": ("cover", "封面", 1, 60),
    "agenda": ("agenda", "提纲", 5, 36),
    "section": ("cover", "章节引入", 1, 60),
    "bullets": ("evidence", "要点", 5, 52),
    "summary": ("recap", "小结", 4, 52),
    "question": ("exercise", "问题与答案", 2, 140),
    "comparison": ("comparison", "双对象对比", 3, 48),
    "flow": ("process", "三至四步流程", 4, 38),
    "formula": ("derivation", "公式与解释", 2, 160),
    "figure": ("evidence", "图片与说明", 3, 52),
}
AUTHORED_LAYOUTS = {
    **LAYOUTS,
    "chart": ("chart", "数据比较", 6, 24),
    "code": ("evidence", "代码与解释", 2, 140),
}

FIELD_NAMES = {
    "cover": ["subtitle"], "section": ["subtitle"], "agenda": ["points"],
    "bullets": ["points"], "summary": ["points"], "question": ["question", "answer"],
    "comparison": ["condition", "left_subject", "right_subject", "rows", "conclusion"],
    "flow": ["steps"], "formula": ["formula", "explanation"], "figure": ["image", "caption", "explanation"],
    "chart": ["unit", "points"], "code": ["code", "explanation"],
}


def is_fixed_template(template):
    return template.template_version in VERSIONS


def layout_limits(layout_id):
    slug = fixed_slug(layout_id)
    kind, name, count, chars = AUTHORED_LAYOUTS[slug]
    if f"@{VERSION}/" in layout_id:
        count = min(count, 3) if slug in {"bullets", "summary"} else count
        chars = {"agenda": 32, "flow": 28}.get(slug, chars)
    return kind, name, count, chars


def fixed_slug(layout_id):
    return layout_id.rsplit("/", 1)[-1]


def compile_fixed_template(theme_id, *, version=VERSION):
    from template_layout_contract import TemplateLayoutContractV1, TemplateLayoutPackContractV1, TemplateSlotContractV1
    if version not in VERSIONS:
        raise ValueError("fixed_template_version_missing")
    if theme_id not in load_slide_theme_pack()["themes"]:
        raise KeyError(theme_id)
    font_digest = file_digest(FONT_PATH)
    layouts = []
    for slug in (AUTHORED_LAYOUTS if version == VERSION else LAYOUTS):
        kind, name, count, chars = layout_limits(f"{theme_id}@{version}/{slug}")
        layouts.append(TemplateLayoutContractV1(
            template_layout_id=f"{theme_id}@{version}/{slug}", layout_slug=slug,
            teaching_intents=[kind],
            slots=[TemplateSlotContractV1(slot_id="title", slot_kind="title", max_chars=28),
                   *(TemplateSlotContractV1(slot_id=field, slot_kind="items" if field in {"points", "steps", "rows"} else "body",
                                           max_items=count, max_chars=chars, required=field not in {"conclusion", "explanation"})
                     for field in FIELD_NAMES[slug])],
            web_renderer_adapter="teaching-scene-web-v2", pptx_renderer_adapter="teaching-scene-pptx-v2",
            execution=LayoutExecution(mode="component_render", component_id=COMPONENT_PREFIX + slug,
                component_version=version, expression_kinds=[kind], font_sha256=font_digest,
                font_floor_pt=22, max_subjects=2, max_dimensions=3, max_nodes=4),
        ))
    payload = {"version": version, "theme": theme_id, "layouts": [l.model_dump(mode="json") for l in layouts]}
    return TemplateLayoutPackContractV1(template_id=theme_id, template_version=version,
        template_digest=stable_hash(payload, prefix="tmpl_"), theme_id=theme_id, layouts=layouts)


def fixed_capabilities(template, selected_id=""):
    entries = []
    for layout in template.layouts:
        slug = fixed_slug(layout.template_layout_id)
        kind, name, count, chars = layout_limits(layout.template_layout_id)
        entries.append({"layout_id": layout.template_layout_id, "name": name, "expression_kinds": [kind],
                        "max_items": count, "max_text_chars": chars, "title_max_chars": 28})
    return {"available_layouts": entries,
            "selected_layout": next((e for e in entries if e["layout_id"] == selected_id), None)}


def place_fixed_fields(content, execution, place, positions, slots, styles):
    """Assign named fields to authored frames; never shrink, split or guess."""
    slug = execution.component_id.removeprefix(COMPONENT_PREFIX)
    elements = {e.element_id: e for e in content.elements}
    expression = content.expression

    def put(key, frame, slot, *, bold=False, fill="FFFFFF", size=22):
        place([key], frame, slot, bold=bold, fill=fill)
        slots[key] = slot
        styles[key]["font_size"] = size

    if slug == "comparison":
        if len(expression.subjects) != 2 or not 1 <= len(expression.dimensions) <= 3:
            raise ValueError("fixed_comparison_requires_two_subjects_and_up_to_three_dimensions")
        if len(expression.condition_element_ids) != 1 or len(expression.conclusion_element_ids) > 1 or expression.prompt_element_ids:
            raise ValueError("fixed_comparison_context_capacity_exceeded")
        put(expression.condition_element_ids[0], (48, 98, 864, 48), "condition")
        for j, subject in enumerate(expression.subjects):
            put(subject.label_element_id, (240 + j * 340, 154, 328, 48), f"subject.{j}", bold=True, fill="EEF0FB")
        for i, dimension in enumerate(expression.dimensions):
            y = 216 + i * 80
            put(dimension.label_element_id, (48, y, 180, 72), f"dimension.{i}", bold=True)
            for j, subject in enumerate(expression.subjects):
                cell = next(c for c in expression.cells if c.subject_id == subject.subject_id and c.dimension_id == dimension.dimension_id)
                if len(cell.element_ids) != 1:
                    raise ValueError("fixed_comparison_one_element_per_cell")
                put(cell.element_ids[0], (240 + j * 340, y, 328, 72), f"cell.{i}.{j}", fill="F5F6FA")
        if expression.conclusion_element_ids:
            put(expression.conclusion_element_ids[0], (48, 466, 864, 54), "conclusion", bold=True)
    elif slug == "flow":
        ids = expression.node_element_ids
        if not 3 <= len(ids) <= 4 or expression.condition_element_ids or expression.conclusion_element_ids:
            raise ValueError("fixed_flow_requires_three_or_four_steps")
        expected = {(a, b) for a, b in zip(ids, ids[1:])}
        if len(expression.relations) != len(expected) or {(r.source_id, r.target_id) for r in expression.relations} != expected or any(r.kind != "sequence" or r.label for r in expression.relations):
            raise ValueError("fixed_flow_requires_ordered_sequence")
        width = 252 if len(ids) == 3 else 186
        gap = 54 if len(ids) == 3 else 40
        for i, key in enumerate(ids):
            put(key, (48 + i * (width + gap), 212, width, 166), f"step.{i}", bold=True, fill="EEF0FB")
    else:
        ids = expression.ordered_element_ids
        limit = LAYOUTS[slug][2]
        if not 1 <= len(ids) <= limit:
            raise ValueError(f"fixed_field_count_exceeded:{slug}:maximum={limit}")
        if slug in {"cover", "section"}:
            put(ids[0], (68, 285, 824, 120), "subtitle", size=26)
        elif slug == "question":
            if elements[ids[0]].role != "question" or len(ids) != 2 or elements[ids[1]].role != "answer":
                raise ValueError("fixed_question_requires_question_and_answer")
            put(ids[0], (48, 126, 864, 158), "question", bold=True, size=26)
            put(ids[1], (48, 322, 864, 174), "answer", fill="F5F6FA")
        elif slug == "formula":
            if elements[ids[0]].kind != "formula":
                raise ValueError("fixed_formula_requires_exact_formula")
            put(ids[0], (48, 126, 864, 230), "formula", size=26)
            if len(ids) == 2:
                put(ids[1], (48, 392, 864, 104), "explanation")
        elif slug == "figure":
            if elements[ids[0]].kind != "image":
                raise ValueError("fixed_figure_requires_adopted_image")
            put(ids[0], (48, 126, 530, 368), "image")
            for i, key in enumerate(ids[1:]):
                put(key, (614, 144 + i * 170, 298, 150), f"caption.{i}")
        else:
            # Qizhi's stable single-column body: equal rows, no auto-columns.
            for i, key in enumerate(ids):
                put(key, (68, 126 + i * 76, 824, 75), f"point.{i}", size=24)
    if set(positions) != set(elements):
        raise ValueError("fixed_unbound_content_field")
    return (60, 140, 840, 124) if slug in {"cover", "section"} else (48, 24, 864, 72)
