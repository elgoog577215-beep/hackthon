"""Resolve impact-report entries into something a teacher can actually read.

The impact report is addressed by stable ids — `section-1-2-custom`, `q_9f3a…`,
`ckp_7b0f…`. That is correct for the domain and useless in a UI: "52 objects
need review" tells a teacher nothing they can act on, and neither does a list of
opaque hashes. Before they can decide whether a knowledge edit is worth it, they
need to see *which section*, *which question*, *which slide*.

This module is a pure read-side projection over the course envelope. It adds no
state and changes no verdicts: the group an object is in, and why, are decided
by `course_knowledge_impact`. All this does is attach a title, a location and a
short excerpt so the list can be opened and understood.

Deliberately excerpt rather than full body: the detail view is for orientation
("is this the paragraph I care about?"), not for reading the course inside a
side panel. Sending whole blocks would also make a 150-object impact list
megabytes wide for no benefit.
"""

from __future__ import annotations

from typing import Any

IMPACT_DETAIL_SCHEMA = "course_knowledge_impact_detail_v1"

EXCERPT_LENGTH = 120

# Impact `type` -> the label group a teacher recognises. These are the object
# families the product promises to keep readable, so they are also the families
# worth naming individually in the UI.
_TYPE_LABELS = {
    "section_content": "正文块",
    "practice": "练习题",
    "slide_deck": "课件",
    "lecture": "讲义",
    "handout": "讲义",
    "practice_sheet": "练习册",
    "lesson_plan": "教案",
    "outline": "目录",
    "mastery_criterion": "掌握标准",
    "learning_objective": "学习目标",
    "knowledge_binding": "知识绑定",
    "knowledge_point": "知识点",
    "teaching_representation": "教学表达",
    "course_knowledge_base": "课程知识库",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _excerpt(value: str, limit: int = EXCERPT_LENGTH) -> str:
    cleaned = " ".join(_text(value).split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1] + "…"


def _document_index(course_data: dict[str, Any] | None) -> dict[str, Any]:
    """section_id -> section, block_id -> (block, owning section)."""
    document = (course_data or {}).get("course_document")
    sections: dict[str, dict[str, Any]] = {}
    blocks: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    if not isinstance(document, dict):
        return {"sections": sections, "blocks": blocks, "objectives": {}}
    for section in document.get("sections") or []:
        if isinstance(section, dict) and _text(section.get("section_id")):
            sections[_text(section.get("section_id"))] = section
    for block in document.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        block_id = _text(block.get("block_id"))
        if block_id:
            blocks[block_id] = (block, sections.get(_text(block.get("section_id")), {}))
    # objective_id -> owning section. Objectives are section properties, not
    # knowledge-base records, so without this an impacted objective renders as
    # a bare `lo_…` hash.
    objectives: dict[str, dict[str, Any]] = {}
    for section in sections.values():
        objective_id = _text(section.get("objective_id"))
        if objective_id:
            objectives[objective_id] = section
    return {"sections": sections, "blocks": blocks, "objectives": objectives}


def _question_index(course_data: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """question_id -> question, across both asset envelope shapes.

    Real courses in this repo keep questions at ``learning_assets.questions``;
    the generation-time bundle nests them under ``learning_assets.assets``.
    Reading only one shape silently produces an impact list where every
    practice row is "missing", so both are indexed.
    """
    assets = (course_data or {}).get("learning_assets")
    if not isinstance(assets, dict):
        return {}
    buckets: list[Any] = [assets.get("questions")]
    nested = assets.get("assets")
    if isinstance(nested, dict):
        buckets.append(nested.get("questions"))
    index: dict[str, dict[str, Any]] = {}
    for bucket in buckets:
        if not isinstance(bucket, list):
            continue
        for question in bucket:
            if not isinstance(question, dict):
                continue
            question_id = _text(question.get("question_id") or question.get("asset_id"))
            if question_id:
                index.setdefault(question_id, question)
    return index


def _knowledge_index(knowledge_base: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for collection, id_field in (
        ("knowledge_points", "knowledge_id"),
        ("mastery_criteria", "criterion_id"),
        ("skill_units", "skill_id"),
        ("misconceptions", "misconception_id"),
    ):
        for item in (knowledge_base or {}).get(collection) or []:
            if isinstance(item, dict) and _text(item.get(id_field)):
                index[_text(item.get(id_field))] = item
    return index


def describe_impact_item(
    item: dict[str, Any],
    *,
    documents: dict[str, Any],
    questions: dict[str, dict[str, Any]],
    knowledge: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Attach title / location / excerpt to one impact entry."""
    item_type = _text(item.get("type"))
    item_id = _text(item.get("id"))
    detail: dict[str, Any] = {
        "type": item_type,
        "id": item_id,
        "type_label": _TYPE_LABELS.get(item_type, item_type),
        "title": "",
        "location": "",
        "excerpt": "",
        "reason": _text(item.get("reason")),
    }
    for passthrough in ("knowledge_id", "resolution", "relation_type", "relation_depth"):
        if item.get(passthrough) not in (None, ""):
            detail[passthrough] = item[passthrough]

    if item_type == "section_content":
        found = documents["blocks"].get(item_id)
        if found:
            block, section = found
            payload = block.get("payload") or {}
            detail["title"] = _text(section.get("title")) or _text(block.get("section_id"))
            detail["location"] = _text(section.get("title"))
            detail["excerpt"] = _excerpt(
                payload.get("markdown") or payload.get("text") or payload.get("content") or "",
            )
            detail["role"] = _text(block.get("role"))
            detail["section_id"] = _text(block.get("section_id"))
        else:
            # A referenced block that is no longer in the document is itself
            # worth surfacing rather than hiding behind a blank row.
            detail["title"] = item_id
            detail["missing"] = True
    elif item_type == "practice":
        question = questions.get(item_id)
        if question:
            detail["title"] = _excerpt(
                question.get("prompt") or question.get("stem") or question.get("title") or "", 60,
            ) or item_id
            section_id = _text(question.get("node_id"))
            detail["location"] = _text(
                (documents["sections"].get(section_id) or {}).get("title"),
            ) or section_id
            detail["section_id"] = section_id
        else:
            detail["title"] = item_id
            detail["missing"] = True
    elif item_type == "learning_objective":
        section = documents["objectives"].get(item_id)
        if section:
            detail["title"] = _text(section.get("learning_objective")) or item_id
            detail["location"] = _text(section.get("title"))
            detail["section_id"] = _text(section.get("section_id"))
        else:
            record = knowledge.get(item_id)
            detail["title"] = _text((record or {}).get("name")) or item_id
    elif item_type in {"mastery_criterion", "knowledge_point"}:
        record = knowledge.get(item_id)
        if record:
            detail["title"] = _text(record.get("name")) or item_id
            detail["excerpt"] = _excerpt(
                record.get("statement") or record.get("observable_performance") or "",
            )
        else:
            detail["title"] = item_id
    elif item_type == "knowledge_binding":
        # A binding is addressed by the section it binds, so the id *is* a
        # section id. Showing the raw `L2-1-1` where a title exists would make
        # the row unreadable for the exact object the teacher navigates by.
        section = documents["sections"].get(item_id)
        detail["title"] = _text((section or {}).get("title")) or item_id
        detail["location"] = _text((section or {}).get("title"))
        detail["section_id"] = item_id
        if section is None:
            detail["missing"] = True
    else:
        # Representations and anything else: the id is the best handle we have,
        # and a wrong invented title would be worse than none.
        detail["title"] = item_id
        if item.get("section_id"):
            section_id = _text(item.get("section_id"))
            detail["location"] = _text(
                (documents["sections"].get(section_id) or {}).get("title"),
            ) or section_id
            detail["section_id"] = section_id
    return detail


def build_impact_detail(
    impact_report: dict[str, Any],
    *,
    course_data: dict[str, Any] | None = None,
    knowledge_base: dict[str, Any] | None = None,
    groups: tuple[str, ...] = ("needs_regeneration", "stale", "blocked", "changed"),
    limit_per_group: int = 200,
) -> dict[str, Any]:
    """Expand an impact report into per-object, teacher-readable rows.

    `limit_per_group` bounds the payload; when it truncates, the response says
    so explicitly rather than silently showing a short list that reads as the
    whole picture.
    """
    base = knowledge_base
    if base is None:
        base = (course_data or {}).get("course_knowledge_base")
    documents = _document_index(course_data)
    questions = _question_index(course_data)
    knowledge = _knowledge_index(base)

    result: dict[str, Any] = {
        "schema_version": IMPACT_DETAIL_SCHEMA,
        "groups": {},
        "counts": {},
        "truncated": {},
    }
    for group in groups:
        entries = [item for item in impact_report.get(group) or [] if isinstance(item, dict)]
        result["counts"][group] = len(entries)
        visible = entries[:limit_per_group]
        result["truncated"][group] = len(entries) > len(visible)
        result["groups"][group] = [
            describe_impact_item(
                item, documents=documents, questions=questions, knowledge=knowledge,
            )
            for item in visible
        ]
    return result


def impact_detail_snapshot(detail: dict[str, Any]) -> dict[str, Any]:
    """Compact, stable projection for regression snapshots."""
    return {
        "counts": dict(sorted((detail.get("counts") or {}).items())),
        "truncated": sorted(
            group for group, flag in (detail.get("truncated") or {}).items() if flag
        ),
        "groups": {
            group: sorted(f"{_text(row.get('type'))}:{_text(row.get('id'))}" for row in rows)
            for group, rows in sorted((detail.get("groups") or {}).items())
            if rows
        },
    }


__all__ = [
    "EXCERPT_LENGTH",
    "IMPACT_DETAIL_SCHEMA",
    "build_impact_detail",
    "describe_impact_item",
    "impact_detail_snapshot",
]
