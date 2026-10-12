"""Program-owned identities, semantic edits and evidence-bound answers.

This is an experimental candidate format, not the runtime course KB schema.
All functions return copies. Structural validity is not semantic acceptance.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import uuid


class Rejected(ValueError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def identity(scope, kind, key):
    return kind + "_" + uuid.uuid5(uuid.NAMESPACE_URL, scope + ":" + key).hex[:20]


def require_text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise Rejected("missing_text:" + field)


UNIT_FIELDS = {"path", "name", "statement", "conditions", "question", "answer",
               "source_refs", "coverage_ids", "stop_reason"}


def validate_unit(unit, sources, criteria):
    if not isinstance(unit, dict) or set(unit) != UNIT_FIELDS:
        raise Rejected("unit_fields")
    for key in ("name", "statement", "question", "answer", "stop_reason"):
        require_text(unit[key], key)
    for key in ("path", "conditions", "source_refs", "coverage_ids"):
        if not isinstance(unit[key], list) or not unit[key]:
            raise Rejected("unit_list:" + key)
        for item in unit[key]:
            require_text(item, key)
        if len(set(unit[key])) != len(unit[key]):
            raise Rejected("duplicate_unit_list:" + key)
    if not set(unit["source_refs"]) <= set(sources):
        raise Rejected("unknown_source")
    if not set(unit["coverage_ids"]) <= set(criteria):
        raise Rejected("unknown_coverage")


def add_unit(doc, unit, point_id):
    parent = doc["root_id"]
    for depth in range(len(unit["path"])):
        path = unit["path"][:depth + 1]
        cid = identity(doc["scope"], "cat", json.dumps(path, ensure_ascii=False))
        if not any(c["id"] == cid for c in doc["categories"]):
            doc["categories"].append({"id": cid, "parent_id": parent, "name": path[-1]})
        parent = cid
    point = {"id": point_id, "parent_id": parent,
             **{k: deepcopy(v) for k, v in unit.items() if k != "path"},
             "semantic_status": "needs_review"}
    doc["points"].append(point)
    return point


def build_core(scope, title, units, sources, criteria):
    if not isinstance(units, list) or not units:
        raise Rejected("empty_core")
    root = identity(scope, "cat", "root")
    doc = {"schema": "knowledge_tree_lab_v3", "scope": scope, "title": title,
           "root_id": root, "categories": [{"id": root, "parent_id": None, "name": title}],
           "points": [], "checks": [], "relations": [], "misconceptions": [],
           "history": [], "invalidated": [], "state": "candidate"}
    seen = set()
    for unit in units:
        validate_unit(unit, sources, criteria)
        fingerprint = digest(unit)
        if fingerprint in seen:
            raise Rejected("duplicate_unit")
        seen.add(fingerprint)
        add_unit(doc, unit, identity(scope, "kp", fingerprint))
    return doc


def apply_intents(base, intent, allowed_ids, sources, criteria):
    """Each source point is its own transaction; one bad proposal cannot erase peers.

    Split references are invalidated, never fanned out as if semantically equivalent.
    A one-to-one edit keeps identity but invalidates dependent evidence as well.
    """
    if intent.get("base_hash") != digest(base):
        raise Rejected("stale_revision")
    if set(intent) - {"base_hash", "revisions", "additions", "coverage", "notes"}:
        raise Rejected("intent_fields")
    doc = deepcopy(base)
    receipts = []
    revisions = intent.get("revisions", [])
    additions = intent.get("additions", [])
    if not isinstance(revisions, list) or not isinstance(additions, list):
        raise Rejected("intent_arrays")
    targets = [r.get("point_id") for r in revisions if isinstance(r, dict)]
    if len(set(targets)) != len(targets):
        raise Rejected("duplicate_target")
    for revision in revisions:
        old_id = revision.get("point_id") if isinstance(revision, dict) else None
        try:
            if set(revision) != {"point_id", "reason", "units"}:
                raise Rejected("revision_fields")
            if old_id not in allowed_ids:
                raise Rejected("out_of_scope")
            require_text(revision["reason"], "reason")
            old = next((p for p in doc["points"] if p["id"] == old_id), None)
            if old is None:
                raise Rejected("unknown_point")
            units = revision["units"]
            if not isinstance(units, list) or not units:
                raise Rejected("empty_replacement")
            for unit in units:
                validate_unit(unit, sources, criteria)
            if len({digest(u) for u in units}) != len(units):
                raise Rejected("duplicate_children")
            trial = deepcopy(doc)
            trial["points"] = [p for p in trial["points"] if p["id"] != old_id]
            new_ids = []
            for unit in units:
                pid = old_id if len(units) == 1 else identity(old_id, "kp", digest(unit))
                if any(p["id"] == pid for p in trial["points"]):
                    raise Rejected("identity_collision")
                add_unit(trial, unit, pid)
                new_ids.append(pid)
            invalidated_check_ids = set()
            for collection in ("checks", "relations", "misconceptions"):
                kept = []
                for entity in trial[collection]:
                    refs = entity.get("knowledge_ids", []) + [entity.get("source_id"), entity.get("target_id")]
                    linked_checks = [entity.get(k) for k in ("symptom_check_id", "diagnostic_check_id", "retest_check_id")]
                    if old_id in refs or set(linked_checks) & invalidated_check_ids:
                        trial["invalidated"].append({"collection": collection, "entity": entity,
                            "reason": "knowledge_revision_requires_rebinding", "replacements": new_ids})
                        if collection == "checks":
                            invalidated_check_ids.add(entity["id"])
                    else:
                        kept.append(entity)
                trial[collection] = kept
            trial["history"].append({"previous": old, "replacement_ids": new_ids,
                                     "reason": revision["reason"]})
            doc = trial
            receipts.append({"point_id": old_id, "status": "applied", "new_ids": new_ids})
        except (Rejected, TypeError) as exc:
            receipts.append({"point_id": old_id, "status": "rejected", "reason": str(exc)})
    for index, unit in enumerate(additions):
        try:
            validate_unit(unit, sources, criteria)
            pid = identity(doc["scope"], "kp", digest(unit))
            if any(p["id"] == pid for p in doc["points"]):
                raise Rejected("duplicate_addition")
            add_unit(doc, unit, pid)
            receipts.append({"addition": index, "status": "applied", "new_ids": [pid]})
        except Rejected as exc:
            receipts.append({"addition": index, "status": "rejected", "reason": str(exc)})
    # Remove only empty taxonomy branches, preserving every populated path and ID.
    needed = {doc["root_id"]} | {p["parent_id"] for p in doc["points"]}
    parents = {c["id"]: c["parent_id"] for c in doc["categories"]}
    for cid in list(needed):
        while parents.get(cid):
            cid = parents[cid]
            needed.add(cid)
    doc["categories"] = [c for c in doc["categories"] if c["id"] in needed]
    return doc, {"base_hash": digest(base), "result_hash": digest(doc), "items": receipts,
                 "pending_check_ids": [p["id"] for p in doc["points"] if not any(
                     p["id"] in c["knowledge_ids"] for c in doc["checks"])]}


CHECK_FIELDS = {"key", "knowledge_ids", "kind", "question", "code", "sample_return_type",
                "predicted_stdout", "explanation", "platform_assumptions"}
MIS_FIELDS = {"key", "knowledge_ids", "hypothesis_a", "hypothesis_b", "symptom_check",
              "diagnostic_check", "retest_check", "symptom_a", "symptom_b",
              "diagnostic_a", "diagnostic_b", "repair_a", "repair_b", "reason_a", "reason_b"}
REL_FIELDS = {"key", "source_id", "target_id", "type", "necessity", "strength",
              "reason", "context", "distinction", "derivation_steps"}


def compile_teaching(core, payload):
    """Keep rejected model proposals in receipts; publish only valid structure."""
    doc = deepcopy(core)
    points = {p["id"] for p in doc["points"]}
    receipts = []
    check_keys = {}
    for collection, fields in (("checks", CHECK_FIELDS), ("relations", REL_FIELDS), ("misconceptions", MIS_FIELDS)):
        doc[collection] = []
        items = payload.get(collection, [])
        if not isinstance(items, list):
            raise Rejected("teaching_array:" + collection)
        seen = set()
        for raw in items:
            key = raw.get("key") if isinstance(raw, dict) else None
            try:
                if not isinstance(raw, dict) or set(raw) != fields:
                    raise Rejected("entity_fields")
                require_text(key, "key")
                if key in seen:
                    raise Rejected("duplicate_key")
                seen.add(key)
                item = deepcopy(raw)
                item["id"] = identity(doc["scope"], collection[:-1], key)
                if collection != "relations":
                    refs = item["knowledge_ids"]
                    if not isinstance(refs, list) or not refs or not set(refs) <= points:
                        raise Rejected("unknown_knowledge")
                if collection == "checks":
                    if item["kind"] not in ("runtime", "static"):
                        raise Rejected("check_kind")
                    if item["sample_return_type"] not in ("void", "int"):
                        raise Rejected("return_type")
                    require_text(item["question"], "question")
                    require_text(item["explanation"], "explanation")
                    if not isinstance(item["platform_assumptions"], list):
                        raise Rejected("platform_assumptions")
                    if item["kind"] == "runtime":
                        require_text(item["code"], "code")
                        if not isinstance(item["predicted_stdout"], str):
                            raise Rejected("stdout_type")
                    else:
                        if item["code"] or item["predicted_stdout"] is not None:
                            raise Rejected("static_contract")
                    check_keys[key] = item["id"]
                elif collection == "relations":
                    if item["source_id"] not in points or item["target_id"] not in points or item["source_id"] == item["target_id"]:
                        raise Rejected("relation_endpoint")
                    if item["type"] not in ("prerequisite", "contrasts_with", "applies_to", "derives"):
                        raise Rejected("relation_type")
                    if item["strength"] not in (None, 0.3, 0.6, 1.0):
                        raise Rejected("relation_strength")
                    if item["type"] == "prerequisite":
                        if item["necessity"] not in ("required", "recommended"):
                            raise Rejected("necessity")
                        edges = [(r["source_id"], r["target_id"]) for r in doc[collection] if r["type"] == "prerequisite"]
                        edges.append((item["source_id"], item["target_id"]))
                        reachable = {item["target_id"]}
                        for _ in points:
                            reachable |= {b for a, b in edges if a in reachable}
                        if item["source_id"] in reachable:
                            raise Rejected("prerequisite_cycle")
                    elif item["necessity"] is not None:
                        raise Rejected("non_prerequisite_necessity")
                    for field in ("reason", "context"):
                        require_text(item[field], field)
                    if item["type"] == "contrasts_with":
                        require_text(item["distinction"], "distinction")
                        item["source_id"], item["target_id"] = sorted([item["source_id"], item["target_id"]])
                    if item["type"] == "derives" and (not isinstance(item["derivation_steps"], list) or not item["derivation_steps"]):
                        raise Rejected("missing_derivation")
                    signature = (item["type"], item["source_id"], item["target_id"])
                    if any((r["type"], r["source_id"], r["target_id"]) == signature for r in doc[collection]):
                        raise Rejected("duplicate_relation")
                    item["confidence"] = None
                else:
                    for field in MIS_FIELDS - {"knowledge_ids", "key"}:
                        require_text(item[field], field) if field not in ("symptom_a", "symptom_b", "diagnostic_a", "diagnostic_b") else None
                    for field in ("symptom_a", "symptom_b", "diagnostic_a", "diagnostic_b"):
                        if not isinstance(item[field], str):
                            raise Rejected("prediction_type")
                    for field in ("symptom_check", "diagnostic_check", "retest_check"):
                        if item[field] not in check_keys:
                            raise Rejected("unknown_check")
                        item[field + "_id"] = check_keys[item[field]]
                    item["origin"] = "model_hypothesis"
                item["semantic_status"] = "needs_review"
                doc[collection].append(item)
                receipts.append({"collection": collection, "key": key, "status": "compiled"})
            except (Rejected, TypeError) as exc:
                receipts.append({"collection": collection, "key": key, "status": "rejected", "reason": str(exc)})
    return doc, receipts


def apply_teaching_repairs(payload, delta, scope):
    if delta.get("base_hash") != digest(payload):
        raise Rejected("stale_revision")
    if not {"base_hash", "replacements"} <= set(delta) or set(delta) - {"base_hash", "replacements", "unresolved"}:
        raise Rejected("repair_fields")
    if not isinstance(delta["replacements"], list):
        raise Rejected("repair_array")
    changed = deepcopy(payload)
    seen = set()
    for proposal in delta["replacements"]:
        if set(proposal) != {"collection", "key", "value"}:
            raise Rejected("repair_item_fields")
        coll, key, value = proposal["collection"], proposal["key"], proposal["value"]
        if coll not in scope or key not in scope[coll]:
            raise Rejected("repair_out_of_scope")
        if (coll, key) in seen:
            raise Rejected("repair_duplicate")
        seen.add((coll, key))
        if value.get("key") != key:
            raise Rejected("repair_identity_change")
        index = next((i for i, entity in enumerate(changed[coll]) if isinstance(entity, dict) and entity.get("key") == key), None)
        if index is None:
            raise Rejected("repair_unknown_target")
        changed[coll][index] = deepcopy(value)
    return changed


def code_hash(check):
    return digest({"code": check["code"], "return_type": check["sample_return_type"],
                   "kind": check["kind"], "platform_assumptions": check["platform_assumptions"]})


def bind_evidence(doc, evidence):
    """Answers derive from successful exact-code receipts; never from model text.

    Receipt files are trusted local compiler output. No correctness claim is made
    about explanations, predicates outside the sample, or misconception causality.
    """
    result = deepcopy(doc)
    receipts = {r["check_id"]: r for r in evidence}
    checks = {c["id"]: c for c in result["checks"]}
    for check in checks.values():
        check.pop("verified_answer", None)
        check.pop("answer_ref", None)
        check.pop("model_prediction_matches", None)
        check["evidence_status"] = "not_verified"
        receipt = receipts.get(check["id"])
        if receipt and receipt.get("code_hash") == code_hash(check) and receipt.get("status") == "executed" and receipt.get("returncode") == 0 and receipt.get("optimization_agrees") is True:
            check["verified_answer"] = {"kind": "stdout", "value": receipt["stdout"]}
            check["answer_ref"] = {"check_id": check["id"], "code_hash": code_hash(check),
                                   "receipt_hash": digest(receipt)}
            check["evidence_status"] = "sample_verified"
            check["model_prediction_matches"] = check["predicted_stdout"] == receipt["stdout"]
    for item in result["misconceptions"]:
        for field in ("answers", "answer_refs"):
            item.pop(field, None)
        item["diagnostic_gate"] = "needs_review"
        problems = []
        linked = {role: checks.get(item[role + "_check_id"]) for role in ("symptom", "diagnostic", "retest")}
        # Formatting differences alone are not evidence for a different misconception.
        item["observation_equivalence"] = "whitespace_separated_tokens"
        same = lambda a, b: a.split() == b.split()
        if any(c and c["kind"] != "runtime" for c in linked.values()):
            problems.append("diagnostic_requires_runtime_checks")
        if len({c["id"] for c in linked.values() if c}) < 3:
            problems.append("retest_or_probe_reuses_same_check")
        if not same(item["symptom_a"], item["symptom_b"]):
            problems.append("not_a_shared_symptom")
        if same(item["diagnostic_a"], item["diagnostic_b"]):
            problems.append("hypotheses_not_distinguished")
        if not all(c and c["evidence_status"] == "sample_verified" for c in linked.values()):
            problems.append("unverified_or_stale_check")
        else:
            answers = {role: check["verified_answer"] for role, check in linked.items()}
            item["answers"] = answers
            item["answer_refs"] = {role: check["answer_ref"] for role, check in linked.items()}
            if same(item["symptom_a"], answers["symptom"]["value"]) or same(item["symptom_b"], answers["symptom"]["value"]):
                problems.append("shared_symptom_is_correct")
        item["gate_problems"] = problems
        if not problems:
            item["diagnostic_gate"] = "numeric_contract_passed_semantics_pending"
    result["pending_checks"] = [p["id"] for p in result["points"] if not any(
        p["id"] in c["knowledge_ids"] for c in checks.values())]
    return result
