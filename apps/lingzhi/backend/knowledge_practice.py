"""Expose reviewed, adopted knowledge-first checks through formal practice.

This is a read-only projection of the course's authored material, not sample
questions or an alternate question repository. Revisions freeze the material,
the question and its exact knowledge-point revision.
"""
from __future__ import annotations

from copy import deepcopy
import re

from course_document import stable_hash as source_hash
from course_versioning import stable_hash


def adopted_knowledge_checks(course: dict) -> list[dict]:
    base = course.get("course_knowledge_base") or {}
    if base.get("tree_schema") != "knowledge_first_c17_v1" or base.get("status") != "accepted":
        return []
    from knowledge_first import material
    package = material()
    if base.get("material_revision") != source_hash(package, prefix="mat_"):
        return []  # Changed source answers must be explicitly adopted again.
    points = {p.get("key"): p for p in base.get("knowledge_points") or []}
    sections = {str(n.get("node_id")) for n in course.get("nodes") or []}
    tasks = []
    for topic, bundle in package.get("bundles", {}).items():
        if topic not in sections:
            continue
        source_points = {p["key"]: p for p in bundle.get("points") or []}
        for check in bundle.get("exercise_bank") or []:
            keys = check.get("knowledge_keys") or []
            if len(keys) != 1:
                continue  # Composite checks need explicit per-point assessment.
            point, source = points.get(keys[0]), source_points.get(keys[0])
            if not point or not source or not point.get("revision_id"):
                continue
            if point.get("statement") != source.get("statement") or point.get("conditions") != source.get("conditions"):
                continue
            kid, rev = point["knowledge_id"], point["revision_id"]
            answer = str(check.get("answer") or "").strip()
            if not answer or not check.get("question"):
                continue
            literal = bool(re.fullmatch(r"[+-]?\d+(?:\.\d+)?|(?:(?:unsigned|signed|long) )*(?:int|short|long|char|float|double)", answer))
            revision = stable_hash({"course": course.get("course_id"), "material": base["material_revision"],
                "check": check, "knowledge": {kid: rev}}, prefix="kqr_")
            task = {
                "asset_id": stable_hash({"course": course.get("course_id"), "check": check["key"]}, prefix="kq_"),
                "question_id": check["key"], "revision_id": revision, "task_revision_id": revision,
                "node_id": topic, "node_ids": [topic], "question_type": "fill_blank" if literal else "short_answer",
                "practice_level": "mastery_check", "prompt": check["question"],
                "learning_objective": point["statement"], "concept_ids": [kid], "primary_knowledge_ids": [kid],
                "prerequisite_knowledge_ids": [], "assessment_binding_schema": "atomic_assessment_v1",
                "assessment_purpose": "atomic_check", "knowledge_revision_refs": {kid: rev},
                "knowledge_baseline_revision": base["revision_id"], "course_knowledge_refs": [kid],
                "source_status": "material_grounded", "source_refs": deepcopy(point.get("source_refs") or []),
                "review_status": "approved", "quality_status": "passed", "origin": "adopted_authored_check",
                "input_contract": {"mode": "short_text" if literal else "rich_text", "required": True, "supports_attachments": False},
                "answer_spec": {"type": "exact" if literal else "rubric_ai", "canonical_answer": answer,
                    "criteria": [check["rationale"]], "solution_steps": [check["rationale"]], "pass_score": 70},
                "grading_policy": {"method": "deterministic" if literal else "rubric_ai", "pass_score": 70,
                    "confidence_threshold": .72, "near_threshold_review_margin": 3},
                "validation_policy": {"mastery_eligible": True, "max_support_level_for_mastery": 0},
            }
            if literal:
                task["answer_spec"]["correct_answer"] = answer
            tasks.append(task)
    return tasks
