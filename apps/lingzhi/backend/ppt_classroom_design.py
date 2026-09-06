"""Authored classroom compositions, derived from Qizhi's complete slide designs.

All coordinates are slide points on the shared 960 x 540 canvas. Choosing among
the finite item-count variants happens before confirmation, never during export.
"""
from ppt_layout_execution import validate_text_frame

VERSION = "fixed_classroom_v2"


def colors(theme_id):
    # Preserve Qizhi's blue cover / purple divider / dark body hierarchy.
    return ({"accent": "305AC7", "cover": "203C66", "section": "305AC7", "pale": "EEF3FB"}
            if theme_id == "academic-editorial" else
            {"accent": "4E4376", "cover": "2B5876", "section": "4E4376", "pale": "EEF0FB"})


def layout_fields(content, execution, theme_id, place, positions, slots, styles):
    slug = execution.component_id.rsplit("/", 1)[-1]
    palette = colors(theme_id)
    expression = content.expression
    elements = {e.element_id: e for e in content.elements}
    background = palette["cover"] if slug == "cover" else palette["section"] if slug == "section" else "FFFFFF"
    title = dict(frame=(64, 30, 848, 96), font_size=32, color="1F2733", fill=background)
    if slug in {"cover", "section"}:
        title.update(frame=(72, 174, 808, 148), font_size=44, color="FFFFFF")
        if slug == "section":
            title["frame"] = (72, 296, 808, 130)

    def put(key, frame, slot, *, size=22, bold=False, fill=None, color="2B3445", align="left", valign="top"):
        place([key], frame, slot, bold=bold, fill=fill or background)
        slots[key] = slot
        styles[key].update(font_size=size, color=color, stroke=fill or background,
                           text_align=align, vertical_align=valign)

    if slug == "comparison":
        if len(expression.subjects) != 2 or not 1 <= len(expression.dimensions) <= 3:
            raise ValueError("fixed_comparison_requires_two_subjects_and_up_to_three_dimensions")
        if len(expression.condition_element_ids) != 1 or len(expression.conclusion_element_ids) > 1 or expression.prompt_element_ids:
            raise ValueError("fixed_comparison_context_capacity_exceeded")
        put(expression.condition_element_ids[0], (64, 130, 832, 40), "condition", size=20, color="677185")
        for j, subject in enumerate(expression.subjects):
            put(subject.label_element_id, (228 + j * 342, 176, 326, 52), f"subject.{j}",
                size=24, bold=True, color="FFFFFF", fill=palette["accent"] if j == 0 else palette["cover"], valign="middle")
        count = len(expression.dimensions)
        row_height = {1: 174, 2: 96, 3: 72}[count]
        for i, dimension in enumerate(expression.dimensions):
            y = 242 + i * (row_height + 8)
            put(dimension.label_element_id, (64, y, 148, row_height), f"dimension.{i}",
                size=22, bold=True, color=palette["accent"], valign="middle")
            for j, subject in enumerate(expression.subjects):
                cell = next(c for c in expression.cells if c.subject_id == subject.subject_id and c.dimension_id == dimension.dimension_id)
                if len(cell.element_ids) != 1:
                    raise ValueError("fixed_comparison_one_element_per_cell")
                put(cell.element_ids[0], (228 + j * 342, y, 326, row_height), f"cell.{i}.{j}",
                    size=22, fill=palette["pale"] if i % 2 == 0 else "F7F8FA", valign="middle")
        if expression.conclusion_element_ids:
            put(expression.conclusion_element_ids[0], (64, 480, 748, 38), "conclusion", size=20, bold=True)
    elif slug == "flow":
        ids = expression.node_element_ids
        expected = {(a, b) for a, b in zip(ids, ids[1:])}
        if not 3 <= len(ids) <= 4 or expression.condition_element_ids or expression.conclusion_element_ids:
            raise ValueError("fixed_flow_requires_three_or_four_steps")
        if len(expression.relations) != len(expected) or {(r.source_id, r.target_id) for r in expression.relations} != expected or any(r.kind != "sequence" or r.label for r in expression.relations):
            raise ValueError("fixed_flow_requires_ordered_sequence")
        width, gap = (248, 44) if len(ids) == 3 else (184, 32)
        for i, key in enumerate(ids):
            put(key, (64 + i * (width + gap), 258, width, 156), f"step.{i}", size=24 if len(ids) == 3 else 22,
                bold=True, fill=palette["pale"], align="center", valign="middle")
    elif slug == "chart":
        from ppt_teaching_content import chart_number
        values = [chart_number(elements[p.value_element_id].text) for p in expression.points]
        put(expression.unit_element_id, (64, 130, 832, 42), "chart.unit", size=20, color="677185")
        count = len(values)
        pitch = {2: 138, 3: 94, 4: 72, 5: 58, 6: 48}[count]
        for i, point in enumerate(expression.points):
            y = 184 + i * pitch
            put(point.label_element_id, (64, y, 176, pitch - 4), f"chart.label.{i}", size=22, valign="middle")
            put(point.value_element_id, (820, y, 76, pitch - 4), f"chart.value.{i}", size=22, bold=True, valign="middle")
    else:
        ids = expression.ordered_element_ids
        if slug in {"cover", "section"}:
            if len(ids) != 1:
                raise ValueError("fixed_cover_requires_one_subtitle")
            put(ids[0], (76, 340, 804, 90) if slug == "cover" else (76, 434, 804, 68),
                "subtitle", size=24 if slug == "cover" else 20, color="DFE5FF")
        elif slug == "question":
            if len(ids) != 2 or elements[ids[0]].role != "question" or elements[ids[1]].role != "answer":
                raise ValueError("fixed_question_requires_question_and_answer")
            put(ids[0], (96, 156, 800, 174), "question", size=28, bold=True)
            put(ids[1], (96, 352, 800, 140), "answer", fill=palette["pale"], valign="middle")
        elif slug in {"formula", "code"}:
            if not 1 <= len(ids) <= 2 or elements[ids[0]].kind != slug:
                raise ValueError(f"fixed_{slug}_requires_exact_{slug}")
            put(ids[0], (64, 162, 832, 188 if slug == "formula" else 262), slug,
                size=30 if slug == "formula" else 22, fill=palette["pale"],
                align="center" if slug == "formula" else "left", valign="middle")
            if len(ids) == 2:
                put(ids[1], (64, 386 if slug == "formula" else 444, 752, 100 if slug == "formula" else 70), "explanation", size=22)
        elif slug == "figure":
            if not 2 <= len(ids) <= 3 or elements[ids[0]].kind != "image":
                raise ValueError("fixed_figure_requires_adopted_image")
            put(ids[0], (64, 146, 516, 344), "image")
            put(ids[1], (620, 156, 276, 128), "caption.0", size=24, bold=True)
            if len(ids) == 3:
                put(ids[2], (620, 306, 276, 174), "caption.1", size=22, color="677185")
        else:
            # Optional heading/body pairs remain separate editable content objects.
            groups = []
            for key in ids:
                if key.endswith("-heading"):
                    if key.removesuffix("-heading") not in ids:
                        raise ValueError("fixed_heading_without_body")
                    continue
                heading = key + "-heading" if key + "-heading" in ids else None
                groups.append((heading, key))
            maximum = 5 if slug == "agenda" else 3
            if not 1 <= len(groups) <= maximum:
                raise ValueError("fixed_field_count_exceeded")
            count = len(groups)
            pitch = {1: 256, 2: 158, 3: 122, 4: 88, 5: 70}[count]
            start = {1: 174, 2: 160, 3: 132, 4: 138, 5: 138}[count]
            for i, (heading, key) in enumerate(groups):
                y = start + i * pitch
                if heading:
                    put(heading, (144, y, 752, 48 if count <= 3 else 38), f"heading.{i}",
                        size=26 if count <= 3 else 22, bold=True, color=palette["accent"])
                    put(key, (144, y + (50 if count <= 3 else 38), 752, pitch - (52 if count <= 3 else 40)),
                        f"point.{i}", size=22 if count <= 3 else 20)
                else:
                    put(key, (144, y, 752, pitch - 12), f"point.{i}",
                        size=28 if count <= 3 else 24 if count == 4 else 22, valign="middle" if count <= 3 else "top")
    if set(positions) != set(elements):
        raise ValueError("fixed_unbound_content_field")
    return title, background


def page_furniture(content, execution, theme_id, title, positions, slots, *, make_object, page_number=0):
    """Template-only furniture. Never contains model-authored teaching claims."""
    palette = colors(theme_id)
    slug = execution.component_id.rsplit("/", 1)[-1]
    dark = slug in {"cover", "section"}
    bg = palette["cover"] if slug == "cover" else palette["section"] if dark else "FFFFFF"
    result = []
    def shape(name, frame, color):
        x, y, w, h = frame
        result.append(make_object(object_id=name, slot_id="decoration", kind="shape", text="", lines=[],
            x=x, y=y, width=w, height=h, font_size=12, fill=color, stroke=color, editability="native_shape"))
    def label(name, value, frame, size, color, *, align="left", visible_with=""):
        x, y, w, h = frame
        result.append(make_object(object_id=name, slot_id="decoration", text=value,
            lines=validate_text_frame(value, w, h, size, execution.font_sha256), x=x, y=y, width=w, height=h,
            font_size=size, color=color, fill=bg, stroke=bg, bold=True, text_align=align, visible_with=visible_with))
    if dark:
        shape("cover-rail", (0, 0, 24, 540), palette["accent"] if slug == "cover" else palette["cover"])
        shape("cover-rule", (80, 126 if slug == "cover" else 274, 72, 5), "AEB8E6")
        if slug == "section" and page_number:
            label("section-page-marker", f"{page_number:02d}", (72, 72, 340, 188), 128, "8278A4")
    else:
        shape("header-rule", (43, 40, 8, 48), palette["accent"])
        shape("footer-rule", (64, 520, 752, 1), "E7EAF2")
    if page_number:
        label("page-number", f"{page_number:02d}", (840, 512, 56, 26), 10,
              "DFE5FF" if dark else "8A93A2", align="right")
    if slug in {"agenda", "bullets", "summary"}:
        for key, slot in slots.items():
            if not slot.startswith("point."):
                continue
            index = int(slot.split(".")[1])
            heading_key = next((k for k, s in slots.items() if s == f"heading.{index}"), key)
            _, y, _, height = positions[heading_key]
            label(f"ordinal-{index}", f"{index + 1:02d}", (64, y, 64, max(48, min(height, 66))), 26, palette["accent"])
    elif slug == "flow":
        for i, key in enumerate(content.expression.node_element_ids):
            x, _, w, _ = positions[key]
            label(f"step-number-{i}", f"{i + 1:02d}", (x, 194, w, 54), 30, palette["accent"], align="center")
    elif slug == "question":
        question, answer = content.expression.ordered_element_ids
        label("question-label", "Q", (56, 160, 40, 46), 22, palette["accent"])
        # The answer marker is absent from the question-only canvas.
        label("answer-label", "A", (56, 360, 40, 46), 22, palette["accent"], visible_with=answer)
    elif slug == "chart":
        from ppt_teaching_content import chart_number
        elements = {e.element_id: e for e in content.elements}
        values = [chart_number(elements[p.value_element_id].text) for p in content.expression.points]
        maximum = max(values) or 1
        for i, (point, value) in enumerate(zip(content.expression.points, values, strict=True)):
            _, y, _, height = positions[point.value_element_id]
            if value:
                shape(f"chart-bar-{i}", (260, y + (height - 28) / 2, float(value / maximum * 536), 28), palette["accent"])
                result[-1].visible_with = point.value_element_id
        shape("chart-baseline", (252, 180, 1, 296), "8A93A2")
        label("chart-zero", "0", (238, 478, 32, 32), 14, "677185")
    return result
