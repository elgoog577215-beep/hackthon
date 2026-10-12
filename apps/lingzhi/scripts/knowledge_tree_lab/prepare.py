"""Deterministic stages, separate from paid model calls."""
import argparse
from pathlib import Path
from .pipeline import (read, save, digest, build_core, apply_intents, compile_teaching,
                       bind_evidence, apply_teaching_repairs)
from .compiler import run_checks


def prepare(root, stage, topic, gcc):
    fixtures = read(root / "fixtures.json")
    evaluation = read(root / "eval_definition.json")
    source_ids = [s["id"] for s in topic["sources"]]
    criteria = [c[0] for c in evaluation["coverage_criteria"][topic["id"]]]
    folder = root / topic["id"]
    if stage == "core":
        data = read(folder / "core.parsed.json")
        doc = build_core(root.name + ":" + topic["id"], topic["name"], data["units"], source_ids, criteria)
        save(folder / "core.json", doc)
        return {"points": len(doc["points"]), "model_gaps": data.get("gaps", [])}
    if stage == "atomize":
        base = read(folder / "core.json")
        doc, receipt = apply_intents(base, read(folder / "atomize.parsed.json"),
                                    {p["id"] for p in base["points"]}, source_ids, criteria)
        save(folder / "atomic.json", doc)
        save(folder / "atomize.receipt.json", receipt)
        return {"points": len(doc["points"]), "items": receipt["items"]}
    payload = read(folder / "teach.parsed.json")
    if stage == "repair":
        payload = apply_teaching_repairs(payload, read(folder / "repair.parsed.json"), read(folder / "repair-scope.json"))
        save(folder / "repaired-teaching.json", payload)
    elif stage == "final":
        payload = read(folder / "repaired-teaching.json")
    doc, receipt = compile_teaching(read(folder / "atomic.json"), payload)
    prefix = "initial" if stage == "teach" else "final"
    save(folder / (prefix + ".unverified.json"), doc)
    save(folder / (prefix + ".structure.json"), receipt)
    approvals_file = folder / "execution-approvals.json"
    approvals = read(approvals_file)["approved_hashes"] if approvals_file.exists() else []
    evidence = run_checks(doc, gcc, folder / (prefix + "-code"), approvals, read(root / "compiler-environment.json"))
    bound = bind_evidence(doc, evidence)
    save(folder / (prefix + ".json"), bound)
    feedback = {"structure": [r for r in receipt if r["status"] == "rejected"], "code": evidence,
                "diagnostics": [{"key": m["key"], "gate": m["diagnostic_gate"], "problems": m["gate_problems"],
                                 "answers": m.get("answers")} for m in bound["misconceptions"]],
                "missing_checks": bound["pending_checks"]}
    if approvals_file.exists():
        feedback["execution_eligibility"] = read(approvals_file)
    save(folder / ("local-feedback.json" if stage == "teach" else "final-feedback.json"), feedback)
    if stage == "teach":
        linked_keys = {m.get(field) for m in payload.get("misconceptions", []) if isinstance(m, dict)
                       for field in ("symptom_check", "diagnostic_check", "retest_check")}
        failed_keys = {r["key"] for r in receipt if r["collection"] == "checks" and r["status"] == "rejected"}
        failed_keys |= {r["key"] for r in evidence if r["status"] not in ("executed", "static_review_required") or r.get("model_prediction_matches") is False}
        scope = {"checks": sorted((linked_keys | failed_keys) - {None}),
                 "misconceptions": [m["key"] for m in payload.get("misconceptions", []) if isinstance(m, dict) and isinstance(m.get("key"), str)],
                 "relations": [r["key"] for r in payload.get("relations", []) if isinstance(r, dict) and isinstance(r.get("key"), str)]}
        save(folder / "repair-scope.json", scope)
    return {"points": len(doc["points"]), "checks": len(doc["checks"]),
            "rejected": feedback["structure"], "missing_checks": bound["pending_checks"],
            "diagnostics": feedback["diagnostics"],
            "code": [{"key": r["key"], "status": r["status"], "prediction_matches": r.get("model_prediction_matches")} for r in evidence]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("stage", choices=("core", "atomize", "teach", "repair", "final"))
    parser.add_argument("--topic", default="all")
    parser.add_argument("--gcc", required=True)
    args = parser.parse_args()
    for topic in read(args.root / "fixtures.json")["topics"]:
        if args.topic in ("all", topic["id"]):
            print(topic["id"], prepare(args.root, args.stage, topic, args.gcc))
