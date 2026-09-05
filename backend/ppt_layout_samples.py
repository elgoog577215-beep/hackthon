"""Synthetic certification specimens. These are never course content."""
from ppt_teaching_content import PageTeachingV2


def matrix_boundary_sample(subject_count=4, dimension_count=4):
    """Capacity specimen with unambiguous row/column identity labels."""
    text = "比较相同条件下各对象的各项观察结果。"
    source = {"block_id": "sample-source", "block_revision": "sample-v1", "start": 0, "end": len(text), "quote": text}
    elements = [{"element_id": "condition", "text": "相同条件", "role": "condition", "sources": [source]}]
    subjects = [{"subject_id": f"s{i}", "label_element_id": f"s{i}"} for i in range(subject_count)]
    dimensions = [{"dimension_id": f"d{i}", "label_element_id": f"d{i}"} for i in range(dimension_count)]
    for i, s in enumerate(subjects):
        elements.append({"element_id": s["subject_id"], "text": f"对象{i + 1}", "role": "label", "subject_id": s["subject_id"], "sources": [source]})
    for i, d in enumerate(dimensions):
        elements.append({"element_id": d["dimension_id"], "text": f"维度{i + 1}", "role": "label", "dimension_id": d["dimension_id"], "sources": [source]})
    cells = []
    for i, s in enumerate(subjects):
        for j, d in enumerate(dimensions):
            key = f"cell-{i}-{j}"
            elements.append({"element_id": key, "text": f"观察{i + 1}／{j + 1}", "subject_id": s["subject_id"], "dimension_id": d["dimension_id"], "sources": [source]})
            cells.append({"subject_id": s["subject_id"], "dimension_id": d["dimension_id"], "element_ids": [key]})
    ids = [e["element_id"] for e in elements]
    return PageTeachingV2.model_validate({"elements": elements,
        "expression": {"kind": "comparison", "subjects": subjects, "dimensions": dimensions, "cells": cells, "condition_element_ids": ["condition"]},
        "must_show": ids, "source_dispositions": [{"block_id": "sample-source", "purpose": "screen", "element_ids": ids, "reason": "边界容量测试"}],
        "states": [{"state_id": "all", "visible_element_ids": ids, "teaching_note": "核对行列身份与容量"}]})


def layout_sample(slug: str, *, length="normal") -> PageTeachingV2:
    if slug == "data-bars":
        return chart_sample(length=length)
    source_text = "同一任务可以串行或并行。串行先完成观察再记录结果；并行把独立的观察和记录分配到两个任务。先观察条件，再判断路径，最后核对结果。条件不足时继续观察。"
    source = {"block_id": "sample-source", "block_revision": "sample-v1", "start": 0, "end": len(source_text), "quote": source_text}
    elements = []
    def add(key, text, **kwargs):
        if length == "long" and key == "condition":
            text *= 100
        elements.append({"element_id": key, "text": text, "sources": [source], **kwargs})
        return key
    if slug.startswith("compare-"):
        add("condition", "同一任务与相同条件", role="condition")
        add("serial", "串行", subject_id="serial", role="label")
        add("parallel", "并行", subject_id="parallel", role="label")
        add("mode", "执行关系", dimension_id="mode", role="label")
        add("s1", "观察", subject_id="serial", dimension_id="mode")
        add("s2", "记录", subject_id="serial", dimension_id="mode")
        add("p1", "独立观察", subject_id="parallel", dimension_id="mode")
        add("p2", "独立记录", subject_id="parallel", dimension_id="mode")
        expression = {"kind": "comparison", "subjects": [{"subject_id": x, "label_element_id": x} for x in ["serial", "parallel"]],
            "dimensions": [{"dimension_id": "mode", "label_element_id": "mode"}],
            "cells": [{"subject_id": "serial", "dimension_id": "mode", "element_ids": ["s1", "s2"]},
                      {"subject_id": "parallel", "dimension_id": "mode", "element_ids": ["p1", "p2"]}],
            "condition_element_ids": ["condition"],
            "relations": [{"relation_id": "serial-order", "source_id": "s1", "target_id": "s2", "kind": "sequence", "sources": [source]}]}
    elif slug in {"concept-map", "relation-flow", "hierarchy-map"}:
        add("condition", "先核对任务条件", role="condition")
        add("observe", "观察条件")
        add("choose", "判断路径")
        add("record", "记录结果")
        kind = {"concept-map": "concept", "relation-flow": "process", "hierarchy-map": "hierarchy"}[slug]
        relation_kind = {"concept": "association", "process": "sequence", "hierarchy": "parent_child"}[kind]
        expression = {"kind": kind, "node_element_ids": ["observe", "choose", "record"], "condition_element_ids": ["condition"],
            "relations": [{"relation_id": "r1", "source_id": "observe", "target_id": "choose", "kind": relation_kind, "sources": [source]},
                          {"relation_id": "r2", "source_id": "observe", "target_id": "record", "kind": relation_kind, "sources": [source]}]}
    else:
        kind = {"problem-focus": "problem", "step-derivation": "derivation", "exercise-states": "exercise", "lesson-recap": "recap",
                "lesson-cover": "cover", "lesson-agenda": "agenda", "source-evidence": "evidence"}[slug]
        add("condition", "相同任务下，观察和记录怎样组织？", role="question" if kind in {"problem", "exercise"} else "condition")
        add("answer", "先判断工作是否相互依赖，再选择执行方式。", role="answer" if kind in {"problem", "exercise"} else "claim")
        expression = {"kind": kind, "ordered_element_ids": ["condition", "answer"]}
    if length == "short":
        for element in elements:
            if element["element_id"] == "condition":
                element["text"] = "观察条件"
    ids = [e["element_id"] for e in elements]
    states = [{"state_id": "complete", "visible_element_ids": ids, "teaching_note": "检查完整教学关系"}]
    if expression["kind"] in {"problem", "exercise", "derivation"}:
        states.insert(0, {"state_id": "question", "visible_element_ids": ["condition"], "teaching_note": "先观察问题"})
    return PageTeachingV2.model_validate({"elements": elements, "expression": expression, "must_show": ids,
        "source_dispositions": [{"block_id": "sample-source", "purpose": "screen", "element_ids": ids, "reason": "模板测试样本完整保留"}], "states": states})


def chart_sample(*, length="normal"):
    texts = ["时间（分钟）", "观察", "记录", "12.5", "25"]
    if length == "short":
        texts[0] = "分钟"
    if length == "long":
        texts[0] *= 100
    source = "；".join(texts)
    elements = []
    for key, text, kind in zip(["unit", "a", "b", "av", "bv"], texts, ["quote", "text", "text", "data", "data"], strict=True):
        start = source.index(text)
        elements.append({"element_id": key, "text": text, "kind": kind,
            "sources": [{"block_id": "sample-source", "block_revision": "sample-v1", "start": start, "end": start + len(text), "quote": text}]})
    ids = [e["element_id"] for e in elements]
    return PageTeachingV2.model_validate({"elements": elements,
        "expression": {"kind": "chart", "unit_element_id": "unit", "points": [
            {"label_element_id": "a", "value_element_id": "av"}, {"label_element_id": "b", "value_element_id": "bv"}]},
        "must_show": ids, "source_dispositions": [{"block_id": "sample-source", "purpose": "screen", "element_ids": ids, "reason": "相同单位和零基线的图表边界样本"}],
        "states": [{"state_id": "first", "visible_element_ids": ["unit", "a", "b", "av"], "teaching_note": "先观察第一个数据"},
                   {"state_id": "all", "visible_element_ids": ids, "teaching_note": "按相同比例比较数据"}]})
