"""Shared disclosed-course projection for preview and authorized learners."""

from copy import deepcopy
from course_document import CourseDocument, course_view_from_document, document_from_legacy_course
from course_teaching_plan_projection import project_course_teaching_plan


def public_document(raw: dict) -> dict:
    doc = (
        CourseDocument.model_validate(raw["course_document"])
        if raw.get("course_document")
        else document_from_legacy_course(raw)
    )
    # Unknown conditional disclosure rules are private until supported. Never
    # pass authoring metadata, candidates or source snapshots to this surface.
    blocks = []
    for b in doc.blocks:
        if b.status != "final" or (
            b.visibility_rule and b.visibility_rule not in ({"audience": "student"}, {"audience": "all"})
        ):
            continue
        blocks.append(
            {
                "block_id": b.block_id,
                "section_id": b.section_id,
                "position": b.position,
                "role": b.role,
                "kind": b.kind,
                "internal_revision": b.internal_revision,
                "concept_refs": list(b.concept_refs),
                "payload": {
                    key: deepcopy(b.payload[key])
                    for key in (
                        "title",
                        "markdown",
                        "summary",
                        "feedback_structure",
                        "content_type",
                        "type_label",
                        "answer_to",
                        "knowledge_refs",
                        "source_knowledge_revision",
                        "source_terminology_revision",
                    )
                    if key in b.payload
                },
            }
        )
    visible_ids = {b["block_id"] for b in blocks}
    for block in blocks:
        if block["payload"].get("answer_to") not in visible_ids:
            block["payload"].pop("answer_to", None)
    return {
        "course_id": doc.course_id,
        "title": doc.title,
        "document_revision": doc.document_revision,
        "sections": [
            s.model_dump(
                include={
                    "section_id",
                    "parent_section_id",
                    "title",
                    "position",
                    "level",
                    "learning_objective",
                    "objective_id",
                    "objective_revision_id",
                }
            )
            for s in doc.sections
        ],
        "blocks": blocks,
    }


def public_handout_plan(raw: dict, document: dict) -> dict:
    """Expose concept data for disclosed sections, without teacher instructions."""
    # Coverage and anchors must be computed from the disclosed body, never from
    # private blocks that happen to share its section.
    plan = project_course_teaching_plan({**raw, "course_document": document})
    visible_sections = {b["section_id"] for b in document["blocks"]}
    section_keys = (
        "node_id",
        "knowledge_structure",
        "key_points",
        "reused_knowledge_names",
        "knowledge_relations",
        "source_knowledge_revision",
        "source_terminology_revision",
        "knowledge_source_status",
        "knowledge_coverage",
    )
    sections = [
        {**{key: deepcopy(s[key]) for key in section_keys if key in s}, "teaching_modules": []}
        for s in plan["sections"]
        if s["node_id"] in visible_sections
    ]
    names = {
        point["name"]
        for section in sections
        for group in section["knowledge_structure"]
        for point in group["knowledge_points"]
    }
    identities = {
        identity
        for section in sections
        for group in section["knowledge_structure"]
        for point in group["knowledge_points"]
        for identity in [point["name"], point["knowledge_id"], *point["aliases"]]
        if identity
    }
    visible_ids = {
        point["knowledge_id"]
        for section in sections
        for group in section["knowledge_structure"]
        for point in group["knowledge_points"]
        if point.get("knowledge_id")
    }

    def endpoint_visible(relation, side):
        identity = relation.get(side + "_knowledge_id")
        return identity in visible_ids if identity else relation.get(side + "_name") in identities

    for section in sections:
        section["knowledge_relations"] = [
            r for r in section["knowledge_relations"] if endpoint_visible(r, "source") and endpoint_visible(r, "target")
        ]
        for group in section["knowledge_structure"]:
            for point in group["knowledge_points"]:
                point["relations"] = [r for r in point["relations"] if endpoint_visible(r, "target")]
    return {
        "schema_version": plan["schema_version"],
        "status": plan["status"],
        "revision_id": plan["revision_id"],
        "strategy": plan["strategy"],
        "section_count": len(sections),
        "knowledge_point_count": len(names),
        "teaching_module_count": 0,
        "sections": sections,
    }


def public_course(raw: dict) -> dict:
    document = public_document(raw)
    plan = public_handout_plan(raw, document)
    base = {
        "course_id": raw["course_id"],
        "course_name": document["title"],
        "current_course_version_id": raw.get("current_course_version_id") or document["document_revision"],
        "course_document": document,
        "course_teaching_plan": plan,
        "authoring_surface": raw.get("authoring_surface"),
        "generation_status": "completed",
        "course_status": "learning",
    }
    result = course_view_from_document(base, document)
    if raw.get("authoring_surface") == "exchange" and raw.get("exchange_origin"):
        from assessment_contracts import project_public_question

        result["exchange_origin"] = deepcopy(raw["exchange_origin"])
        assets = deepcopy(raw.get("learning_assets") or {})
        for kind in ("questions", "final_assessment"):
            assets[kind] = [
                {
                    **project_public_question(q),
                    "grading_authority": "publisher",
                    "task_purpose": "course_practice",
                    "task_source": "published_course",
                }
                for q in assets.get(kind) or []
            ]
        result["learning_assets"] = assets
        result["course_creation_intent"] = raw.get("course_creation_intent")
        result["course_knowledge_base"] = deepcopy(raw.get("course_knowledge_base") or {})
        result["published_ppts"] = deepcopy(raw.get("published_ppts") or [])
    plans = {s["node_id"]: s for s in plan["sections"]}
    for node in result["nodes"]:
        p = plans.get(node["node_id"], {})
        for key in ("knowledge_structure", "key_points", "reused_knowledge_names", "knowledge_relations"):
            node[key] = deepcopy(p.get(key) or [])
    return result


def public_envelope(raw: dict) -> dict:
    document = public_document(raw)
    return {
        "course_id": raw["course_id"],
        "course_name": document["title"],
        "current_course_version_id": raw.get("current_course_version_id") or document["document_revision"],
        "course_document_revision": document["document_revision"],
        "source_format": "canonical",
        "migration": {"required": False},
        "document": document,
        "teaching_plan": public_handout_plan(raw, document),
    }
