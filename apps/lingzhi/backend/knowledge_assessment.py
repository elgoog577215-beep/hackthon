"""Pure adapters for assessment against an adopted atomic knowledge baseline.

Slot identity is independent of practice level and knowledge revision. Course
nodes remain real lecture IDs; these adapters never create knowledge identities.
"""

from copy import deepcopy

from course_versioning import stable_hash

ATOMIC_ASSESSMENT_SCHEMA = "atomic_assessment_v1"


def atomic_baseline(course: dict) -> dict | None:
    base = course.get("course_knowledge_base") or {}
    adopted = base.get("lifecycle_status") == "active" or base.get("status") == "accepted"
    atomic = base.get("tree_schema") or any(
        p.get("granularity_status") == "atomic" and p.get("meta_question") for p in base.get("knowledge_points") or []
    )
    return base if adopted and atomic and base.get("revision_id") else None


def normalize_adopted_baseline(base: dict) -> dict:
    """The pilot stores adoption on the tree; inherit it only for this schema."""
    if base.get("tree_schema") != "knowledge_first_c17_v1" or base.get("status") != "accepted":
        return base
    result = deepcopy(base)
    result["lifecycle_status"] = "active"
    for point in result.get("knowledge_points") or []:
        point.setdefault("status", "active")
        point.setdefault("granularity_status", "atomic")
    return result


def slot_key(slot: dict) -> str:
    return str(slot.get("generation_key") or slot.get("practice_level") or "")


def slots_for_node(blueprint: dict, node_id: str) -> list[dict]:
    return next(
        (n.get("slots") or [] for n in blueprint.get("nodes") or [] if str(n.get("node_id") or "") == str(node_id)), []
    )


def slot_keys_by_node(blueprint: dict) -> dict[str, list[str]]:
    return {str(n["node_id"]): [slot_key(s) for s in n.get("slots") or []] for n in blueprint.get("nodes") or []}


def item_slot_keys(item: dict) -> list[str]:
    if item.get("generation_key"):
        return [str(item["generation_key"])]
    return [str(v) for v in item.get("practice_levels") or [item.get("practice_level")] if v]


def source_index(course: dict, base: dict) -> dict[str, dict]:
    sources = base.get("sources") or []
    if isinstance(sources, dict):
        sources = [s for t in sources.get("topics") or [] for s in t.get("sources") or []]
    package = (
        course.get("evidence_package") or (course.get("generation_stage_artifacts") or {}).get("evidence_package") or {}
    )
    records = [*sources, *(course.get("evidence_catalog") or []), *(package.get("units") or [])]
    return {str(s.get("source_id") or s.get("id") or s.get("evidence_id")): s for s in records if isinstance(s, dict)}


def atomic_slots(course: dict, objective: dict, recipe: dict) -> list[dict] | None:
    base = atomic_baseline(course)
    if base is None:
        return None
    node_id = str(objective.get("node_id") or "")
    sources = source_index(course, base)
    node_ids = {str(n.get("node_id")) for n in course.get("nodes") or [] if int(n.get("node_level") or 1) == 2}
    result = []
    seen = set()
    for point in base.get("knowledge_points") or []:
        kid = str(point.get("knowledge_id") or "")
        refs = list(point.get("section_refs") or ([point["topic"]] if point.get("topic") else []))
        # Cross-lecture knowledge owns one initial check, at its first real lecture.
        owner = next((str(r) for r in refs if str(r) in node_ids), None)
        if owner != node_id or kid in seen:
            continue
        seen.add(kid)
        if (
            not kid
            or not point.get("revision_id")
            or point.get("status", "active" if base.get("status") == "accepted" else "") != "active"
            or point.get("granularity_status", "atomic" if base.get("tree_schema") else "") != "atomic"
            or point.get("scope_role", "required") in {"prerequisite", "extension"}
            or not point.get("statement")
            or not point.get("meta_question")
            or not point.get("source_refs")
        ):
            continue
        source_refs = point["source_refs"]
        if any(not isinstance(ref, str) or ref not in sources for ref in source_refs):
            continue
        evidence = [
            {
                "reference_id": ref,
                "source_type": "course_material",
                "reference_excerpt": str(
                    sources[ref].get("text") or sources[ref].get("source_text") or sources[ref].get("excerpt") or ""
                ),
                "reuse_policy": "course_grounding",
            }
            for ref in source_refs
        ]
        if not all(e["reference_excerpt"].strip() for e in evidence):
            continue
        target = deepcopy(objective)
        target.update(
            objective=point["meta_question"],
            knowledge=[point["statement"]],
            skills=[point["meta_question"]],
            misconceptions=[],
            observable_evidence=[point["meta_question"]],
            source_refs=deepcopy(point["source_refs"]),
            source_excerpt=str(point["statement"])
            + "\n"
            + str(point.get("conditions") or "")
            + "\n"
            + "\n".join(e["reference_excerpt"] for e in evidence),
            source_sufficiency="sufficient",
            generation_status="ready",
        )
        key = stable_hash(
            {"course": course.get("course_id"), "knowledge": kid, "purpose": "atomic_check"}, prefix="aks_"
        )
        known = {str(p.get("knowledge_id")) for p in base.get("knowledge_points") or []}
        prerequisite_ids = [str(v) for v in point.get("prerequisite_ids") or [] if str(v) != kid and str(v) in known]
        result.append(
            {
                **deepcopy(recipe),
                "slot_id": key,
                "generation_key": key,
                "assessment_binding_schema": ATOMIC_ASSESSMENT_SCHEMA,
                "assessment_purpose": "atomic_check",
                "primary_knowledge_ids": [kid],
                "prerequisite_knowledge_ids": prerequisite_ids,
                "knowledge_revision_refs": {kid: str(point["revision_id"])},
                "knowledge_baseline_revision": base["revision_id"],
                "target_objective": target,
                "knowledge": [point["statement"]],
                "skills": [point["meta_question"]],
                "misconceptions": [],
                "source_refs": deepcopy(point["source_refs"]),
                "conditions": deepcopy(point.get("conditions") or []),
                "target_content_evidence": evidence,
                "learning_scope": deepcopy((base.get("sources") or {}).get("course_context") or {}) if isinstance(base.get("sources"), dict) else {},
            }
        )
    from assessment_variants import expand_atomic_variants
    return expand_atomic_variants(result, course.get("assessment_variant_count", 3))


def target_reference_summary(slot: dict, summary: dict) -> dict:
    if not slot.get("assessment_binding_schema"):
        return summary
    evidence = slot.get("target_content_evidence") or []
    return {
        **summary,
        "content_covered": bool(evidence),
        "content_reference_count": len(evidence),
        "content_fact_basis": [e["reference_excerpt"] for e in evidence],
    }


def assessment_binding(slot: dict) -> dict:
    quantity = {key: deepcopy(slot[key]) for key in ('generation_key','variant_index','quantity_schema','quantity_batch_id')
                if key in slot} if slot.get('quantity_schema') else {}
    if slot.get("assessment_binding_schema") != ATOMIC_ASSESSMENT_SCHEMA:
        return quantity
    return {
        key: deepcopy(slot.get(key))
        for key in (
            "assessment_binding_schema",
            "assessment_purpose",
            "generation_key",
            "variant_index",
            "variant_role",
            "assessment_evidence_key",
            "primary_knowledge_ids",
            "prerequisite_knowledge_ids",
            "knowledge_revision_refs",
            "knowledge_baseline_revision",
            *quantity,
        )
    }


def frozen_assessment_refs(base: dict, task: dict) -> dict[str, str] | None:
    """Return authored revisions, never relabel an old question with today's tree.

    None means legacy task; an empty mapping means a malformed explicit binding.
    """
    if task.get("assessment_binding_schema") != ATOMIC_ASSESSMENT_SCHEMA:
        return None
    ids = task.get("primary_knowledge_ids") or []
    refs = task.get("knowledge_revision_refs") or {}
    if (
        len(ids) != 1
        or set(ids) != set(task.get("concept_ids") or [])
        or set(refs) != set(ids)
        or not all(refs.values())
    ):
        return {}
    return deepcopy(refs)
