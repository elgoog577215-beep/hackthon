"""Read-only, version-bound knowledge mastery projection; no provider or storage I/O."""
from __future__ import annotations

import math
from typing import Any

from course_versioning import stable_hash
from knowledge_assessment import frozen_assessment_refs, normalize_adopted_baseline

RULE_VERSION = "knowledge_mastery_v2"


def freeze_knowledge_refs(base: dict, task: dict) -> dict[str, str]:
    """Only exact task references qualify; never infer from a whole section."""
    if task.get("knowledge_binding_schema") == "question_knowledge_binding_v2":
        refs = task.get("knowledge_revision_refs") or {}
        ids = task.get("concept_ids") or []
        if task.get("knowledge_binding_status") != "bound" or not ids or set(refs) != set(ids):
            return {}
        return {str(k): str(v) for k, v in refs.items() if v}
    authored = frozen_assessment_refs(base, task)
    if authored is not None:
        return authored
    base = normalize_adopted_baseline(base)
    if base.get("lifecycle_status") != "active":
        return {}
    ids = set(task.get("concept_ids") or [])
    return {str(p["knowledge_id"]): str(p["revision_id"])
            for p in base.get("knowledge_points") or []
            if p.get("knowledge_id") in ids and p.get("revision_id")
            and p.get("status") == "active" and p.get("granularity_status") == "atomic"}


def _summary(nodes: list[dict]) -> dict:
    assessed = [p for p in nodes if p["mastery"] is not None]
    total = len(nodes)
    value = sum(p["mastery"] for p in assessed)
    return {
        "total_count": total, "assessed_count": len(assessed), "unknown_count": total - len(assessed),
        "verified_progress": round(value / total, 1) if total else 0,
        "coverage": round(100 * len(assessed) / total, 1) if total else 0,
        "assessed_average": round(value / len(assessed), 1) if assessed else None,
        "mastered_count": sum(p["status"] == "supported_mastery" for p in nodes),
        "attention_count": sum(p["status"] == "needs_review" for p in nodes),
    }


def _number(value: Any) -> float:
    try:
        value = float(value)
        return value if math.isfinite(value) else 0
    except (ValueError, TypeError):
        return 0


def build_knowledge_profile(base: dict, *, course_id: str, course_version_id: str,
                            user_id: str, attempts: list[dict], events: list[dict]) -> dict:
    base = normalize_adopted_baseline(base)
    points: dict[str, dict] = {}
    if base.get("lifecycle_status") == "active":
        for point in base.get("knowledge_points") or []:
            if (point.get("knowledge_id") and point.get("revision_id") and point.get("status") == "active"
                    and point.get("granularity_status") == "atomic"
                    and point.get("scope_role", "required") not in {"prerequisite", "extension"}):
                points.setdefault(str(point["knowledge_id"]), point)
    groups = {str(g.get("category_id") or g.get("concept_group_id") or g.get("id")): g
              for g in [*(base.get("categories") or []), *(base.get("concept_groups") or [])]}
    current_attempts = [a for a in attempts if user_id and a.get("user_id") == user_id and a.get("course_id") == course_id]
    current_events = [e for e in events if user_id and e.get("user_id") == user_id
                      and e.get("course_id") == course_id and e.get("course_version_id") == course_version_id]
    # Explicit, server-evaluated explanations share the same reference rule as
    # practice; saving or discussing notes still contributes only activity.
    for event in current_events:
        if event.get("event_type") != "note_understanding_checked" or event.get("source") != "study_dialogue_check_v1":
            continue
        current_attempts.append({
            "attempt_id": event.get("event_id"), "user_id": user_id, "course_id": course_id,
            "course_version_id": course_version_id, "concept_ids": event.get("concept_ids") or [],
            "knowledge_revision_refs": (event.get("metadata") or {}).get("knowledge_revision_refs") or {},
            "task_revision_id": event.get("task_revision_id"), "status": "graded", "result": event.get("result") or {},
            "support_level": (event.get("result") or {}).get("support_level", 0), "created_at": event.get("created_at"),
            "solution_revealed": bool((event.get("result") or {}).get("solution_revealed")),
        })
    nodes = []
    for kid, point in points.items():
        block_ids = set(point.get("course_block_refs") or [])
        block_ids.update(b.get("target_id") for b in base.get("bindings") or []
                         if b.get("target_type") == "course_block" and kid in (b.get("knowledge_ids") or []))
        latest: dict[str, dict] = {}
        feedback_only: dict[str, dict] = {}
        historical: set[str] = set()
        pending: set[str] = set()
        # Upgrade old attempts only when a server-frozen key for this exact
        # question revision is present in this learner's current knowledge scope.
        # Do not invent cross-revision equivalence for unkeyed historical data.
        revision_keys: dict[str, set[str]] = {}
        for row in current_attempts:
            revision = str(row.get("task_revision_id") or row.get("question_revision_id") or "")
            key = str(row.get("assessment_evidence_key") or "")
            if (revision and key and row.get("course_version_id") == course_version_id
                    and row.get("concept_ids") == [kid]
                    and (row.get("knowledge_revision_refs") or {}).get(kid) == point["revision_id"]):
                revision_keys.setdefault(revision, set()).add(key)
        for a in sorted(current_attempts, key=lambda item: (str(item.get("updated_at") or item.get("created_at") or ""), str(item.get("attempt_id") or ""))):
            ids = list(dict.fromkeys(a.get("concept_ids") or []))
            aid = str(a.get("attempt_id") or "")
            if kid not in ids or not aid:
                continue
            if a.get("course_version_id") != course_version_id or (a.get("knowledge_revision_refs") or {}).get(kid) != point["revision_id"]:
                historical.add(aid)
                continue
            # Multi-point tasks require a real per-point rubric. V1 does not invent one.
            if len(ids) != 1:
                pending.add(aid)
                continue
            qid = str(a.get("task_revision_id") or a.get("question_revision_id") or "")
            result = a.get("result") or {}
            if (not qid or a.get("status") != "graded" or result.get("status") == "pending_review"
                    or result.get("historical_only") or not isinstance(result.get("passed"), bool)
                    or _number(result.get("grading_confidence")) < .72):
                continue
            keys = revision_keys.get(qid, set())
            qid = next(iter(keys)) if len(keys) == 1 else qid
            # Feedback after revealing an answer cannot erase an earlier valid
            # check for the same question. Keep it visible without scoring it.
            if a.get("solution_revealed") or result.get("evidence_strength") == "invalid":
                feedback_only[qid] = a
                continue
            latest[qid] = a
            feedback_only.pop(qid, None)
        evidence = []
        positive = negative = 0.0
        independent_passed = independent_failed = 0
        for qid, a in latest.items():
            result = a["result"]
            revealed = bool(a.get("solution_revealed"))
            assistance = max(_number(a.get("ai_support_level")), _number(a.get("support_level")),
                             _number(result.get("support_level")), 1 if a.get("revealed_hint_levels") else 0)
            passed = result["passed"]
            invalid = result.get("evidence_strength") == "invalid"
            practice_only = passed and (result.get("mastery_eligible") is False or result.get("evidence_strength") == "scaffolded")
            independent = assistance == 0 and not revealed and not invalid and not practice_only
            weight = 0 if revealed or invalid else 1 if independent else .25
            positive += weight if passed else 0
            negative += weight if not passed else 0
            independent_passed += int(independent and passed)
            independent_failed += int(independent and not passed)
            evidence.append({"source_id": a["attempt_id"], "question_revision_id": a.get("task_revision_id") or a.get("question_revision_id") or qid,
                             "assessment_evidence_key": qid,
                             "outcome": "passed" if passed else "not_passed",
                             "support": "solution_seen" if revealed else "invalid" if invalid else "assisted" if assistance else "practice_only" if practice_only else "independent",
                             "counted": weight > 0, "weight": weight,
                             "observed_at": a.get("updated_at") or a.get("created_at")})
        for qid, a in feedback_only.items():
            evidence.append({"source_id": a["attempt_id"], "question_revision_id": a.get("task_revision_id") or a.get("question_revision_id") or qid,
                             "assessment_evidence_key": qid,
                             "outcome": "passed" if a["result"]["passed"] else "not_passed",
                             "support": "solution_seen" if a.get("solution_revealed") else "invalid",
                             "counted": False, "weight": 0,
                             "observed_at": a.get("updated_at") or a.get("created_at")})
        count = sum(e["counted"] for e in evidence)
        mastery = round(100 * (1 + positive) / (2 + positive + negative), 1) if count else None
        independent_count = independent_passed + independent_failed
        confidence = "none" if not count else "strong" if independent_count >= 3 else "moderate" if independent_count >= 2 else "limited"
        status = ("unassessed" if mastery is None else "supported_mastery" if mastery >= 80 and independent_passed >= 3
                  else "needs_review" if mastery < 50 and independent_failed >= 2 else "checking")
        activities = set()
        for event in current_events:
            if not event.get("event_id") or event.get("event_type") not in {"learner_self_reported", "assistant_question_submitted", "learning_record_created", "learning_record_updated", "node_learning_completed"}:
                continue
            metadata = event.get("metadata") or {}
            anchor = (event.get("evidence") or {}).get("anchor") or metadata.get("content_anchor") or (metadata.get("context_ref") or {}).get("content_anchor") or {}
            block = metadata.get("block_id") or anchor.get("block_id")
            anchors = [(event.get("evidence") or {}).get("anchor"), metadata.get("content_anchor"),
                       (metadata.get("context_ref") or {}).get("content_anchor")]
            exact_context = any(isinstance(a, dict) and kid in (a.get("concept_ids") or [])
                                and (a.get("knowledge_revision_refs") or {}).get(kid) == point["revision_id"] for a in anchors)
            if kid in (event.get("concept_ids") or []) or exact_context or (block and block in block_ids):
                activities.add(str(event.get("record_id") or event["event_id"]))
        nodes.append({"knowledge_id": kid, "knowledge_revision_id": point["revision_id"],
                      "name": str(point.get("name") or ""), "statement": str(point.get("statement") or ""),
                      "parent_id": str(point.get("parent_id") or point.get("primary_concept_group_id") or "ungrouped"),
                      "section_refs": list(point.get("section_refs") or []), "mastery": mastery, "confidence": confidence,
                      "status": status, "assessment_count": count, "independent_count": independent_count,
                      "activity_count": len(activities), "historical_count": len(historical), "pending_attribution_count": len(pending),
                      "evidence": evidence, "next_action": "verify" if mastery is None else "review" if status == "needs_review" else "transfer" if status == "supported_mastery" else "variant"})
    # Group ancestors aggregate unique leaves, never child percentages or relation strengths.
    branch_members: dict[str, dict[str, dict]] = {}
    for node in nodes:
        gid = node["parent_id"]
        seen = set()
        while gid and gid not in seen:
            seen.add(gid)
            branch_members.setdefault(gid, {})[node["knowledge_id"]] = node
            gid = str((groups.get(gid) or {}).get("parent_id") or "")
    branches = [{"id": gid, "parent_id": str((groups.get(gid) or {}).get("parent_id") or ""),
                 "name": str((groups.get(gid) or {}).get("name") or gid),
                 "knowledge_ids": list(members), "summary": _summary(list(members.values()))}
                for gid, members in branch_members.items()]
    result = {"rule_version": RULE_VERSION, "baseline_revision": base.get("revision_id"),
              "course_id": course_id, "course_version_id": course_version_id,
              "availability": "ready" if nodes else "tree_unavailable", "summary": _summary(nodes),
              "nodes": nodes, "branches": branches,
              "policy": {"calibrated_probability": False, "unknown_is_zero_ability": False, "equal_leaf_weights": True}}
    result["revision_id"] = stable_hash(result, prefix="kmp_")
    return result
