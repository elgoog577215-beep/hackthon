"""Resolve one immutable scene for preflight, browser preview and native PPTX."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from course_document import stable_hash
from ppt_layout_execution import LayoutExecution, tool_identity, validate_text_frame
from ppt_teaching_content import ChartExpression, ComparisonExpression, Contract, GraphExpression, PageTeachingV2, chart_number, relation_is_directed


def display_element_text(element):
    if element.kind == "formula":
        from ppt_formula_projection import project_matrix
        matrix = project_matrix(element.text)
        if matrix is not None:
            return matrix
        from slide_deck_renderer import _format_formula_text
        text = _format_formula_text(element.text)
        if "\\" in text or "$" in text:
            raise ValueError(f"teaching_formula_not_supported:{element.element_id}")
        return text
    if element.kind == "text":
        from slide_deck_renderer import _display_text
        return _display_text(element.text)
    return element.text


class SceneObject(Contract):
    object_id: str
    element_id: str = ""
    slot_id: str
    kind: Literal["text", "image", "shape"] = "text"
    text: str
    lines: list[str]
    x: float
    y: float
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    font_size: float
    bold: bool = False
    color: str = "17243B"
    fill: str = "FFFFFF"
    stroke: str = "FFFFFF"
    asset_id: str = ""
    asset_digest: str = ""
    asset_course_id: str = ""
    asset_representation_id: str = ""
    subject_id: str = ""
    dimension_id: str = ""
    editability: Literal["text", "image_object", "formula_source_text", "native_shape"] = "text"


class SceneEdge(Contract):
    relation_id: str
    source_id: str
    target_id: str
    kind: str
    label: str
    x1: float
    y1: float
    x2: float
    y2: float
    start_site: int = 3
    end_site: int = 1
    label_object: SceneObject | None = None


def _overlaps(a, b, padding=0):
    return (a.x < b.x + b.width + padding and a.x + a.width + padding > b.x
            and a.y < b.y + b.height + padding and a.y + a.height + padding > b.y)


def _relation_label(relation, anchors, objects, execution):
    """Freeze the same measured label box for browser, native render and audit."""
    if not relation.label:
        return None
    x1, y1, x2, y2 = anchors[:4]
    size = execution.font_floor_pt
    width = min(240, max(70, len(relation.label) * size + 16))
    height = size * 1.3 + 12
    try:
        lines = validate_text_frame(relation.label, width, height, size, execution.font_sha256)
    except ValueError as exc:
        raise ValueError(f"relation_label_capacity_exceeded:{relation.relation_id}") from exc
    for dy in (-height - 5, 5, -height / 2):
        label = SceneObject(object_id=f"relation-label:{relation.relation_id}", slot_id="relation-label",
            text=relation.label, lines=lines, x=(x1 + x2 - width) / 2, y=(y1 + y2) / 2 + dy,
            width=width, height=height, font_size=size, color="305AC7")
        if label.x >= 0 and label.y >= 0 and label.x + width <= 960 and label.y + height <= 540 and not any(_overlaps(label, o, 3) for o in objects):
            return label
    raise ValueError(f"relation_label_overlap:{relation.relation_id}")


def relation_anchors(source, target):
    """PowerPoint rectangle connection sites: top, left, bottom, right."""
    sx, sy, sw, sh = source
    tx, ty, tw, th = target
    dx, dy = tx + tw / 2 - sx - sw / 2, ty + th / 2 - sy - sh / 2
    if abs(dx) / max(1, (sw + tw) / 2) >= abs(dy) / max(1, (sh + th) / 2):
        return (sx + sw, sy + sh / 2, tx, ty + th / 2, 3, 1) if dx >= 0 else (sx, sy + sh / 2, tx + tw, ty + th / 2, 1, 3)
    return (sx + sw / 2, sy + sh, tx + tw / 2, ty, 2, 0) if dy >= 0 else (sx + sw / 2, sy, tx + tw / 2, ty + th, 0, 2)


class ResolvedPageScene(Contract):
    schema_version: Literal["resolved_page_scene_v2"] = "resolved_page_scene_v2"
    logical_page_id: str
    state_id: str
    layout_id: str
    template_digest: str
    source_document_revision: str
    width: float = 960
    height: float = 540
    background: str = "FFFFFF"
    accent_color: str = "305AC7"
    objects: list[SceneObject]
    edges: list[SceneEdge]
    emphasized_element_ids: list[str]
    execution: LayoutExecution
    tools: dict[str, Any]
    scene_digest: str


def _graph_positions(ids: list[str], relations, frame):
    """Layer a DAG using declared edges; cycles retain explicit circular order."""
    from math import cos, pi, sin
    x, y, w, h = frame
    parents = {n: {r.source_id for r in relations if r.target_id == n} for n in ids}
    remaining = set(ids)
    layers = []
    while remaining:
        ready = [n for n in ids if n in remaining and not (parents[n] & remaining)]
        if not ready:
            node_w, node_h = min(180, w / 3), min(90, h / 3)
            return {n: (x + w / 2 + (w - node_w) / 2 * cos(2 * pi * i / len(ids)) - node_w / 2,
                        y + h / 2 + (h - node_h) / 2 * sin(2 * pi * i / len(ids)) - node_h / 2,
                        node_w, node_h) for i, n in enumerate(ids)}
        layers.append(ready)
        remaining.difference_update(ready)
    node_w = min(210, (w - 42 * (len(layers) - 1)) / len(layers))
    result = {}
    for column, layer in enumerate(layers):
        node_h = min(108, (h - 20 * (len(layer) - 1)) / len(layer))
        for row, node in enumerate(layer):
            result[node] = (x + column * (w - node_w) / max(1, len(layers) - 1),
                            y + (h - len(layer) * node_h - (len(layer) - 1) * 20) / 2 + row * (node_h + 20), node_w, node_h)
    return result


def resolve_page_scenes(*, page_id: str, title: str, content: PageTeachingV2, layout, template,
                        source_document_revision: str) -> list[ResolvedPageScene]:
    execution = layout.execution
    if execution is None or content.expression.kind not in execution.expression_kinds:
        raise ValueError("teaching_layout_incompatible")
    tools = tool_identity()
    if execution.font_sha256 != tools["font_sha256"]:
        raise ValueError("teaching_font_changed")
    elements = {e.element_id: e for e in content.elements}
    positions = {}
    slots = {}
    styles = {}
    expression = content.expression
    palette = ({"accent": "305AC7", "condition": "EFF3FB", "header": "E5EDFA", "cell": "F3F6FB", "node": "EDF2FC"}
        if template.theme_id == "academic-editorial" else
        {"accent": "4C479C", "condition": "F2F0FA", "header": "E7E3F5", "cell": "F7F5FC", "node": "EEEAF9"})
    accent = palette["accent"]
    chart_bars = []

    def minimum_height(key, width):
        from ppt_layout_execution import wrap_text
        item = elements[key]
        return (160 if item.kind == "image" else
                len(wrap_text(display_element_text(item), width - 16, execution.font_floor_pt,
                              font_digest=execution.font_sha256)) * execution.font_floor_pt * 1.3 + 12)

    def place(ids, frame, prefix, *, fill="FFFFFF", bold=False, measured=False):
        if not ids:
            return
        x, y, w, h = frame
        heights = [h / len(ids)] * len(ids)
        if measured and execution.mode != "native_fill":
            minimums = [minimum_height(key, w) for key in ids]
            extra = max(0, h - sum(minimums)) / len(ids)
            heights = [minimum + extra for minimum in minimums]
        offset = 0
        for i, element_id in enumerate(ids):
            if element_id in positions:
                raise ValueError("teaching_element_placed_twice")
            positions[element_id] = (x, y + offset, w, heights[i])
            offset += heights[i]
            slots[element_id] = f"{prefix}.{i}"
            styles[element_id] = {"fill": fill, "bold": bold}

    if isinstance(expression, ComparisonExpression):
        if len(expression.subjects) > execution.max_subjects or len(expression.dimensions) > execution.max_dimensions:
            raise ValueError("comparison_layout_capacity_exceeded")
        if execution.component_id == "compare-visual" and not expression.relations and not any(e.kind in {"image", "formula"} for e in content.elements):
            raise ValueError("comparison_visual_evidence_missing")
        prompt = bool(expression.prompt_element_ids)
        place(expression.prompt_element_ids, (42, 87, 876, 44), "prompt", bold=True)
        place(expression.condition_element_ids, (42, 133 if prompt else 87, 876, 56 if prompt else 66), "condition", fill=palette["condition"])
        n, m = len(expression.subjects), len(expression.dimensions)
        label_w = 150
        col_w = (876 - label_w) / n
        available = 210 if prompt else 240
        row_heights = [available / m] * m
        if execution.component_id == "compare-matrix" and execution.mode != "native_fill":
            minimums = [max(
                minimum_height(d.label_element_id, label_w - 4),
                *(sum(minimum_height(key, col_w - 4) for key in c.element_ids)
                  for c in expression.cells if c.dimension_id == d.dimension_id),
            ) + 4 for d in expression.dimensions]
            if sum(minimums) > available:
                raise ValueError(f"teaching_text_capacity_exceeded:comparison_rows: needs={sum(minimums):g}pt, "
                    f"available={available}pt; minimum_heights={dict(zip((d.dimension_id for d in expression.dimensions), minimums))}; "
                    "split comparison dimensions across pages, retaining subject labels and conditions")
            extra = (available - sum(minimums)) / m
            row_heights = [minimum + extra for minimum in minimums]
        for j, subject in enumerate(expression.subjects):
            place([subject.label_element_id], (42 + label_w + j * col_w, 194 if prompt else 160, col_w - 4, 48 if prompt else 55), f"subject.{j}", fill=palette["header"], bold=True)
        row_y = 246 if prompt else 219
        for i, dimension in enumerate(expression.dimensions):
            row_h = row_heights[i]
            place([dimension.label_element_id], (42, row_y, label_w - 4, row_h - 4), f"dimension.{i}", fill="F3F5F9", bold=True)
            for j, subject in enumerate(expression.subjects):
                cell = next(c for c in expression.cells if c.subject_id == subject.subject_id and c.dimension_id == dimension.dimension_id)
                frame = (42 + label_w + j * col_w, row_y, col_w - 4, row_h - 4)
                if execution.component_id == "compare-visual" and len(cell.element_ids) > 1:
                    relations = [r for r in expression.relations if r.source_id in cell.element_ids and r.target_id in cell.element_ids]
                    cell_positions = _graph_positions(cell.element_ids, relations, frame)
                    for k, element_id in enumerate(cell.element_ids):
                        place([element_id], cell_positions[element_id], f"cell.{i}.{j}.{k}", fill=palette["cell"])
                else:
                    place(cell.element_ids, frame, f"cell.{i}.{j}", fill=palette["cell"], measured=True)
            row_y += row_h
        place(expression.conclusion_element_ids, (42, 468, 876, 56), "conclusion", bold=True)
    elif isinstance(expression, GraphExpression):
        if len(expression.node_element_ids) > execution.max_nodes:
            raise ValueError("graph_layout_capacity_exceeded")
        place(expression.condition_element_ids, (42, 87, 876, 66), "condition", fill=palette["condition"])
        for i, (element_id, frame) in enumerate(_graph_positions(expression.node_element_ids, expression.relations, (50, 171, 860, 276)).items()):
            place([element_id], frame, f"node.{i}", fill=palette["node"], bold=True)
        place(expression.conclusion_element_ids, (42, 466, 876, 58), "conclusion", bold=True)
    elif isinstance(expression, ChartExpression):
        if execution.mode != "component_render":
            raise ValueError("native_chart_binding_not_supported")
        place([expression.unit_element_id], (48, 87, 864, 56), "chart.unit", bold=True)
        values = [chart_number(elements[p.value_element_id].text) for p in expression.points]
        maximum = max(values) or 1
        row_height = 282 / len(expression.points)
        for index, (point, value) in enumerate(zip(expression.points, values, strict=True)):
            y = 165 + index * row_height
            place([point.label_element_id], (48, y, 200, row_height - 6), f"chart.label.{index}")
            place([point.value_element_id], (786, y, 126, row_height - 6), f"chart.value.{index}", bold=True)
            if value:
                chart_bars.append(SceneObject(object_id=f"chart-bar:{point.value_element_id}", element_id=point.value_element_id,
                    slot_id=f"chart.bar.{index}", kind="shape", text="", lines=[], x=262, y=y + 12,
                    width=float(value / maximum * 500), height=18, font_size=20, fill=accent, stroke=accent,
                    editability="native_shape"))
    else:
        # Measure all states together: short labels do not consume formula
        # height, and revealing an answer never shifts earlier objects.
        from ppt_layout_execution import wrap_text
        ids = expression.ordered_element_ids
        minimums = []
        for key in ids:
            item = elements[key]
            minimums.append(160 if item.kind == "image" else
                len(wrap_text(display_element_text(item), 864 - 16, execution.font_floor_pt,
                              font_digest=execution.font_sha256)) * execution.font_floor_pt * 1.3 + 12)
        gap = 8
        required = sum(minimums) + gap * (len(ids) - 1)
        if required > 396 and execution.mode != "native_fill":
            raise ValueError(f"teaching_linear_capacity_exceeded: needs={required:g}pt, available=396pt; "
                             f"minimum_heights={dict(zip(ids, minimums))}; "
                             "split this task into pages or select a comparison layout for aligned alternatives")
        extra = max(0, 396 - required) / len(ids)
        y = 112
        for index, (key, minimum) in enumerate(zip(ids, minimums, strict=True)):
            height = minimum + extra
            place([key], (48, y, 864, height), "item")
            slots[key] = f"item.{index}"
            y += height + gap
    if set(positions) != set(elements):
        raise ValueError("teaching_element_layout_binding_incomplete")
    title_frame = (42, 10, 876, 76)
    if execution.mode == "native_fill":
        for key, slot in {"title": "title", **slots}.items():
            target = execution.targets.get(slot)
            if target is None or target.geometry_pt is None:
                raise ValueError("native_template_target_geometry_missing")
            if key == "title":
                title_frame = target.geometry_pt
            else:
                positions[key] = target.geometry_pt
        for relation in getattr(expression, "relations", []):
            if any(execution.targets[slots[key]].row is not None for key in (relation.source_id, relation.target_id)):
                raise ValueError("native_cell_connector_unsupported")
    all_objects = []
    tx, ty, tw, th = title_frame
    title_lines = validate_text_frame(title, tw, th, 30, execution.font_sha256)
    all_objects.append(SceneObject(object_id="title", slot_id="title", text=title, lines=title_lines,
                                   x=tx, y=ty, width=tw, height=th, font_size=30, bold=True, color=accent))
    capacity_errors = []
    for element_id, element in elements.items():
        x, y, width, height = positions[element_id]
        if min(x, y) < 0 or x + width > 960 or y + height > 540:
            raise ValueError("teaching_geometry_out_of_bounds")
        try:
            displayed_text = display_element_text(element)
            lines = [] if element.kind == "image" else validate_text_frame(displayed_text, width, height, execution.font_floor_pt, execution.font_sha256)
        except ValueError as exc:
            capacity_errors.append(f"{exc}:{element_id}: frame={width:g}x{height:g}pt, font={execution.font_floor_pt:g}pt")
            continue
        adopted = next((a for a in content.adopted_assets if a.asset_id == element.asset_id), None)
        all_objects.append(SceneObject(
            object_id=element_id, element_id=element_id, slot_id=slots[element_id],
            kind="image" if element.kind == "image" else "text", text=displayed_text, lines=lines,
            x=x, y=y, width=width, height=height, font_size=execution.font_floor_pt,
            asset_id=element.asset_id, asset_digest=element.asset_digest,
            asset_course_id=adopted.course_id if adopted else "",
            asset_representation_id=adopted.representation_id if adopted else "",
            subject_id=element.subject_id, dimension_id=element.dimension_id,
            editability="image_object" if element.kind == "image" else "formula_source_text" if element.kind == "formula" else "text",
            **styles[element_id],
        ))
    if capacity_errors:
        raise ValueError("; ".join(capacity_errors) + "; revise the draft: concise conditions and fewer dimensions; preserve selected artifacts exactly")
    if isinstance(expression, ChartExpression):
        all_objects.extend(chart_bars)
        all_objects.append(SceneObject(object_id="chart-zero", slot_id="chart.zero", text="0", lines=["0"],
            x=250, y=462, width=40, height=40, font_size=20))
        all_objects.append(SceneObject(object_id="chart-baseline", slot_id="chart.baseline", kind="shape", text="", lines=[],
            x=260, y=165, width=1, height=282, font_size=20, fill=accent, stroke=accent, editability="native_shape"))
    if execution.mode == "native_fill":
        if not execution.source_sha256 or execution.source_slide_number < 1:
            raise ValueError("native_template_source_missing")
        if any(o.slot_id not in execution.targets for o in all_objects):
            raise ValueError("native_template_target_missing")
    objects = {o.object_id: o for o in all_objects}
    if any(_overlaps(a, b) for i, a in enumerate(all_objects) for b in all_objects[i + 1:]):
        raise ValueError("teaching_objects_overlap")
    relations = getattr(expression, "relations", [])
    scenes = []
    for state in content.states:
        visible = set(state.visible_element_ids)
        edges = []
        label_obstacles = list(all_objects)
        for relation in relations:
            if not {relation.source_id, relation.target_id} <= visible:
                continue
            if not set(relation.condition_element_ids) <= visible:
                raise ValueError("visible_relation_condition_hidden")
            left, right = objects[relation.source_id], objects[relation.target_id]
            x1, y1, x2, y2, start_site, end_site = relation_anchors(
                (left.x, left.y, left.width, left.height), (right.x, right.y, right.width, right.height))
            if execution.mode == "native_fill":
                binding = execution.connections.get(f"{left.slot_id}->{right.slot_id}")
                if binding is None:
                    raise ValueError(f"native_relation_binding_missing:{relation.relation_id}")
                if binding.directed != relation_is_directed(relation.kind):
                    raise ValueError("native_relation_direction_incompatible")
                x1, y1, x2, y2 = binding.geometry_pt
                start_site, end_site = binding.start_site, binding.end_site
                label = None
                if relation.label:
                    target = execution.targets.get(binding.label_slot)
                    if target is None or target.geometry_pt is None or target.group_path or target.row is not None:
                        raise ValueError("native_relation_label_binding_missing")
                    x, y, w, h = target.geometry_pt
                    label = SceneObject(object_id=f"relation-label:{relation.relation_id}", slot_id=binding.label_slot,
                        text=relation.label, lines=validate_text_frame(relation.label, w, h, execution.font_floor_pt, execution.font_sha256),
                        x=x, y=y, width=w, height=h, font_size=execution.font_floor_pt, color="305AC7")
                    if any(_overlaps(label, o) for o in label_obstacles):
                        raise ValueError("native_relation_label_overlap")
            else:
                label = _relation_label(relation, (x1, y1, x2, y2), label_obstacles, execution)
            if label:
                label.color = accent
                label_obstacles.append(label)
            edges.append(SceneEdge(relation_id=relation.relation_id, source_id=relation.source_id, target_id=relation.target_id,
                kind=relation.kind, label=relation.label, label_object=label,
                x1=x1, y1=y1, x2=x2, y2=y2, start_site=start_site, end_site=end_site))
        payload = dict(logical_page_id=page_id, state_id=state.state_id, layout_id=layout.template_layout_id,
            template_digest=template.template_digest, source_document_revision=source_document_revision,
            accent_color=accent,
            objects=[o.model_dump(mode="json") for o in all_objects if not o.element_id or o.element_id in visible],
            edges=[e.model_dump(mode="json") for e in edges], emphasized_element_ids=state.emphasized_element_ids,
            execution=execution.model_dump(mode="json"), tools=tools)
        scene = ResolvedPageScene(scene_digest="", **payload)
        scene.scene_digest = stable_hash(scene.model_dump(mode="json", exclude={"scene_digest"}), prefix="scene_")
        scenes.append(scene)
    return scenes


def verify_scene(scene: ResolvedPageScene) -> None:
    if scene.scene_digest != stable_hash(scene.model_dump(mode="json", exclude={"scene_digest"}), prefix="scene_"):
        raise ValueError("teaching_scene_digest_mismatch")
    if scene.tools != tool_identity():
        raise ValueError("teaching_execution_environment_changed")
    for obj in scene.objects:
        if obj.kind == "text" and obj.lines != validate_text_frame(obj.text, obj.width, obj.height, obj.font_size, scene.execution.font_sha256):
            raise ValueError("teaching_scene_text_measurement_changed")
    for edge in scene.edges:
        label = edge.label_object
        if bool(edge.label) != bool(label) or (label and label.text != edge.label):
            raise ValueError("teaching_scene_relation_label_missing")
        if label and label.lines != validate_text_frame(label.text, label.width, label.height, label.font_size, scene.execution.font_sha256):
            raise ValueError("teaching_scene_text_measurement_changed")
