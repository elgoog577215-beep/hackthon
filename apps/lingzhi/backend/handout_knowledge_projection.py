"""Read-only knowledge slices pinned to the handout's source, never a second tree.

Coverage counts explicit, revision-matched references. It is not a claim that
the prose teaches the point correctly or that an exercise measures mastery.
"""
from copy import deepcopy


def _records(value):
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def _text(value):
    return str(value or "").strip()


def _blocks(course):
    document = course.get("course_document") or {}
    if isinstance(document, dict) and "blocks" in document:
        return _records(document["blocks"])
    return [{"block_id": b.get("block_id"), "section_id": n.get("node_id"),
             "role": b.get("type"), "status": b.get("status", "final"),
             "concept_refs": (b.get("metadata") or {}).get("concept_refs", []),
             "payload": {**(b.get("metadata") or {}), "markdown": b.get("content", "")}}
            for n in _records(course.get("nodes")) for b in _records(n.get("content_blocks"))]


def _source(course, revision):
    current = course.get("course_knowledge_base") or {}
    if current.get("revision_id") == revision:
        return current, "current"
    historical = (course.get("knowledge_first_history") or {}).get(revision) or {}
    if historical.get("revision_id") == revision:
        return historical, "historical"
    return {}, "unavailable"


def reference_coverage(points, blocks, revision, *, status, scope_known):
    rows = {p["knowledge_id"]: {"knowledge_id": p["knowledge_id"], "name": p.get("name", ""),
        "revision_id": p.get("revision_id", ""), "block_ids": [], "explanation_block_ids": [],
        "example_block_ids": [], "exercise_block_ids": []} for p in points if p.get("knowledge_id")}
    invalid = []
    categories = {"definition": "explanation_block_ids", "explanation": "explanation_block_ids",
        "theorem": "explanation_block_ids", "derivation": "explanation_block_ids", "comparison": "explanation_block_ids",
        "example": "example_block_ids", "exercise": "exercise_block_ids", "checkpoint": "exercise_block_ids"}
    roles = {"concept": "explanation", "reasoning": "derivation", "checkpoint": "exercise"}
    for block in blocks:
        payload = block.get("payload") or {}
        if block.get("status", "final") != "final" or not _text(payload.get("markdown")):
            continue
        for ref in _records(payload.get("knowledge_refs")):
            kid = _text(ref.get("knowledge_id"))
            row = rows.get(kid)
            reason = ""
            if not row:
                reason = "unknown_knowledge"
            elif payload.get("source_knowledge_revision") != revision:
                reason = "source_revision_mismatch"
            elif not ref.get("revision_id") or ref["revision_id"] != row["revision_id"]:
                reason = "revision_mismatch"
            if reason:
                invalid.append({"block_id": block["block_id"], "knowledge_id": kid, "reason": reason})
                continue
            bid = block["block_id"]
            if bid not in row["block_ids"]:
                row["block_ids"].append(bid)
            kind = payload.get("content_type") or roles.get(block.get("role"), block.get("role"))
            category = categories.get(kind)
            if category and bid not in row[category]:
                row[category].append(bid)
    return {"status": status, "scope_known": scope_known, "semantics_verified": False,
            "source_knowledge_revision": revision, "rows": list(rows.values()), "invalid_refs": invalid}


def project_handout_knowledge(course, sections):
    """Enrich reading sections, including knowledge-first courses with no plan.

    An explicit missing or conflicting source never falls back to today's tree.
    Legacy unversioned plans remain readable, without claiming pinned coverage.
    """
    result = deepcopy(sections)
    by_id = {s["node_id"]: s for s in result}
    blocks = _blocks(course)
    by_section = {}
    for block in blocks:
        by_section.setdefault(block.get("section_id"), []).append(block)
    document = course.get("course_document") or {}
    handouts = course.get("teacher_handouts") or {}
    section_ids = list(dict.fromkeys([s.get("section_id") for s in _records(document.get("sections"))] + list(by_section)))
    for sid in section_ids:
        body = by_section.get(sid, [])
        revisions = {_text((b.get("payload") or {}).get("source_knowledge_revision")) for b in body} - {""}
        # The block reference is authoritative for multi-section lessons; metadata
        # supplies the revision for an empty/partially generated section.
        if (handouts.get(sid) or {}).get("source_knowledge_revision"):
            revisions.add(handouts[sid]["source_knowledge_revision"])
        if not revisions:
            continue
        revision = next(iter(revisions)) if len(revisions) == 1 else ""
        tree, status = _source(course, revision) if revision else ({}, "conflict")
        section = by_id.get(sid)
        if section is None:
            section = {"node_id": sid, "key_points": [], "reused_knowledge_names": [], "teaching_modules": []}
            result.append(section)
            by_id[sid] = section
        all_points = _records(tree.get("knowledge_points"))
        scoped = [p for p in all_points if sid in (p.get("section_refs") or []) or p.get("topic") == sid]
        referenced = {_text(r.get("knowledge_id")) for b in body for r in _records((b.get("payload") or {}).get("knowledge_refs"))}
        points = [p for p in all_points if p in scoped or p.get("knowledge_id") in referenced]
        ids = {p["knowledge_id"] for p in points}
        names = {p["knowledge_id"]: p.get("name", "") for p in all_points if p.get("knowledge_id")}
        # Whitelist the public point contract; no teaching notes or private model
        # context is introduced by reading a historical knowledge snapshot.
        fields = ("knowledge_id", "revision_id", "name", "statement", "description", "knowledge_type",
                  "conditions", "boundaries", "aliases", "source_refs", "section_refs")
        public_points = [{**{k: deepcopy(p[k]) for k in fields if k in p}, "aliases": deepcopy(p.get("aliases") or []),
                          "relations": [], "knowledge_status": "bound"} for p in points]
        edges = []
        for edge in _records(tree.get("relations")):
            source = _text(edge.get("source_knowledge_id") or edge.get("source_id"))
            target = _text(edge.get("target_knowledge_id") or edge.get("target_id"))
            if source not in names or target not in names or not ({source, target} & ids):
                continue
            fields = ("relation_id", "reason", "conditions", "distinction", "derivation_steps", "source_refs",
                      "relation_group_id", "group_operator", "necessity", "strength", "confidence")
            edges.append({**{k: deepcopy(edge[k]) for k in fields if k in edge},
                "source_knowledge_id": source, "target_knowledge_id": target,
                "source_name": names[source], "target_name": names[target],
                "relation_type": edge.get("relation_type") or edge.get("type", "")})
        section.update(knowledge_structure=[{"concept_group": "", "knowledge_points": public_points}] if public_points else [],
            knowledge_relations=edges, reused_knowledge_names=[], source_knowledge_revision=revision,
            source_terminology_revision=tree.get("terminology_revision", ""), knowledge_source_status=status,
            knowledge_coverage=reference_coverage(points, body, revision, status=status, scope_known=bool(scoped)))
    return result
