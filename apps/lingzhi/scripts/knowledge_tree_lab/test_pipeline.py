"""Offline regression tests. Run with python -m unittest ...test_pipeline."""
from copy import deepcopy
import unittest
from .pipeline import (Rejected, build_core, apply_intents, digest, compile_teaching,
                       bind_evidence, code_hash, apply_teaching_repairs)
from .compiler import restricted_code


def unit(name="A"):
    return {"path": ["分类"], "name": name, "statement": "rule " + name,
            "conditions": ["C17"], "question": "question " + name, "answer": "answer " + name,
            "source_refs": ["S1"], "coverage_ids": ["T01"], "stop_reason": "one judgment"}


def core():
    return build_core("test", "test", [unit(), unit("B")], {"S1"}, {"T01"})


def teaching(doc):
    refs = [doc["points"][0]["id"]]
    checks = [{"key": str(i), "knowledge_ids": refs, "kind": "runtime", "question": "q",
               "code": 'printf("%d\\n", ' + str(i) + ');', "sample_return_type": "void",
               "predicted_stdout": "wrong\n", "explanation": "principle", "platform_assumptions": []}
              for i in range(3)]
    mis = {"key": "m", "knowledge_ids": refs, "hypothesis_a": "wrong A", "hypothesis_b": "wrong B",
           "symptom_check": "0", "diagnostic_check": "1", "retest_check": "2",
           "symptom_a": "9\n", "symptom_b": "9\n", "diagnostic_a": "1\n", "diagnostic_b": "2\n",
           "repair_a": "fix A", "repair_b": "fix B", "reason_a": "because A", "reason_b": "because B"}
    return {"checks": checks, "misconceptions": [mis], "relations": []}


def receipts(doc):
    return [{"check_id": c["id"], "code_hash": code_hash(c), "status": "executed",
             "returncode": 0, "stdout": str(i) + "\n", "optimization_agrees": True,
             "environment_hash": "test-only"} for i, c in enumerate(doc["checks"])]


class PipelineTests(unittest.TestCase):
    def test_ids_stable_on_replay_and_root_single(self):
        self.assertEqual(core(), core())
        self.assertEqual(sum(c["parent_id"] is None for c in core()["categories"]), 1)

    def test_split_preserves_neighbor_and_invalidates_dependents(self):
        base = core()
        base, _ = compile_teaching(base, teaching(base))
        old = deepcopy(base)
        target = base["points"][0]["id"]
        intent = {"base_hash": digest(base), "revisions": [{"point_id": target,
                  "reason": "independent targets", "units": [unit("A1"), unit("A2")]}]}
        result, receipt = apply_intents(base, intent, {target}, {"S1"}, {"T01"})
        self.assertEqual(base, old)
        self.assertIn(base["points"][1], result["points"])
        self.assertEqual(len(result["points"]), 3)
        self.assertEqual(result["history"][0]["previous"], base["points"][0])
        self.assertEqual(len(result["history"][0]["replacement_ids"]), 2)
        self.assertEqual(result["checks"], [])
        self.assertEqual(result["misconceptions"], [])
        self.assertEqual(len(result["invalidated"]), 4)
        self.assertEqual(len(receipt["pending_check_ids"]), 3)

    def test_invalidated_cross_point_diagnostic(self):
        base = core()
        payload = teaching(base)
        payload["misconceptions"][0]["knowledge_ids"] = [base["points"][1]["id"]]
        base, _ = compile_teaching(base, payload)
        target = base["points"][0]["id"]
        result, _ = apply_intents(base, {"base_hash": digest(base), "revisions": [
            {"point_id": target, "reason": "revision", "units": [unit("edited")]}]}, {target}, {"S1"}, {"T01"})
        self.assertEqual(result["misconceptions"], [])
        self.assertIn(target, {p["id"] for p in result["points"]})

    def test_bad_item_does_not_erase_valid_neighbor_edit(self):
        base = core()
        revisions = [{"point_id": p["id"], "reason": "split", "units": [unit("new" + str(i))]}
                     for i, p in enumerate(base["points"])]
        revisions[0]["units"][0]["source_refs"] = ["fake"]
        result, receipt = apply_intents(base, {"base_hash": digest(base), "revisions": revisions},
            {p["id"] for p in base["points"]}, {"S1"}, {"T01"})
        self.assertIn(base["points"][0], result["points"])
        self.assertEqual([i["status"] for i in receipt["items"]], ["rejected", "applied"])

    def test_stale_and_duplicate_target_rejected(self):
        base = core()
        with self.assertRaisesRegex(Rejected, "stale"):
            apply_intents(base, {"base_hash": "old"}, set(), {"S1"}, {"T01"})
        revision = {"point_id": base["points"][0]["id"], "reason": "r", "units": [unit()]}
        with self.assertRaisesRegex(Rejected, "duplicate_target"):
            apply_intents(base, {"base_hash": digest(base), "revisions": [revision, revision]}, set(), {"S1"}, {"T01"})

    def test_scope_escape_preserves_original(self):
        base = core()
        result, receipt = apply_intents(base, {"base_hash": digest(base), "revisions": [
            {"point_id": base["points"][0]["id"], "reason": "r", "units": [unit("changed")]}]}, set(), {"S1"}, {"T01"})
        self.assertEqual(base, result)
        self.assertEqual(receipt["items"][0]["reason"], "out_of_scope")

    def test_answer_comes_from_receipt_not_model(self):
        base = core()
        doc, _ = compile_teaching(base, teaching(base))
        result = bind_evidence(doc, receipts(doc))
        self.assertEqual(result["checks"][0]["verified_answer"]["value"], "0\n")
        self.assertFalse(result["checks"][0]["model_prediction_matches"])
        self.assertEqual(result["misconceptions"][0]["answers"]["retest"]["value"], "2\n")
        self.assertEqual(result["misconceptions"][0]["semantic_status"], "needs_review")

    def test_stale_changed_code_does_not_reuse_answer(self):
        base = core()
        doc, _ = compile_teaching(base, teaching(base))
        evidence = receipts(doc)
        doc = bind_evidence(doc, evidence)
        doc["checks"][0]["code"] = 'puts("changed");'
        result = bind_evidence(doc, evidence)
        self.assertNotIn("verified_answer", result["checks"][0])
        self.assertNotIn("answers", result["misconceptions"][0])

    def test_failed_or_disagreeing_execution_not_truth(self):
        base = core()
        doc, _ = compile_teaching(base, teaching(base))
        for change in ({"returncode": 1}, {"optimization_agrees": False}, {"status": "timeout"}):
            evidence = receipts(doc)
            evidence[0].update(change)
            result = bind_evidence(doc, evidence)
            self.assertNotIn("verified_answer", result["checks"][0])

    def test_nondiscriminating_prediction_stays_pending(self):
        base = core()
        payload = teaching(base)
        payload["misconceptions"][0]["diagnostic_b"] = "1\n"
        doc, _ = compile_teaching(base, payload)
        result = bind_evidence(doc, receipts(doc))
        self.assertIn("hypotheses_not_distinguished", result["misconceptions"][0]["gate_problems"])

    def test_correct_or_different_symptoms_rejected(self):
        for a, b, expected in (("0\n", "0\n", "shared_symptom_is_correct"), ("4\n", "5\n", "not_a_shared_symptom")):
            base = core()
            payload = teaching(base)
            payload["misconceptions"][0].update(symptom_a=a, symptom_b=b)
            doc, _ = compile_teaching(base, payload)
            self.assertIn(expected, bind_evidence(doc, receipts(doc))["misconceptions"][0]["gate_problems"])

    def test_whitespace_alone_does_not_diagnose_a_misconception(self):
        base = core()
        payload = teaching(base)
        payload["misconceptions"][0].update(symptom_a="0", symptom_b="0 ", diagnostic_a="1", diagnostic_b="1\n")
        doc, _ = compile_teaching(base, payload)
        problems = bind_evidence(doc, receipts(doc))["misconceptions"][0]["gate_problems"]
        self.assertIn("shared_symptom_is_correct", problems)
        self.assertIn("hypotheses_not_distinguished", problems)

    def test_missing_check_is_reported(self):
        doc = bind_evidence(core(), [])
        self.assertEqual(len(doc["pending_checks"]), 2)

    def test_invalid_relation_kept_in_receipt(self):
        base = core()
        payload = teaching(base)
        payload["relations"] = [{"key": "r", "source_id": base["points"][0]["id"],
            "target_id": base["points"][1]["id"], "type": "contrasts_with", "necessity": None,
            "strength": .8, "reason": "r", "context": "c", "distinction": "d", "derivation_steps": []}]
        doc, receipt = compile_teaching(base, payload)
        self.assertEqual(doc["relations"], [])
        self.assertTrue(any(r.get("reason") == "relation_strength" for r in receipt))

    def test_prerequisite_cycle_rejected(self):
        base = core()
        a, b = [p["id"] for p in base["points"]]
        payload = teaching(base)
        payload["relations"] = [{"key": str(i), "source_id": src, "target_id": dst,
            "type": "prerequisite", "necessity": "recommended", "strength": .6,
            "reason": "r", "context": "c", "distinction": "", "derivation_steps": []}
            for i, (src, dst) in enumerate(((a, b), (b, a)))]
        doc, receipt = compile_teaching(base, payload)
        self.assertEqual(len(doc["relations"]), 1)
        self.assertTrue(any(r.get("reason") == "prerequisite_cycle" for r in receipt))

    def test_teaching_repair_scope_and_source_immutable(self):
        payload = teaching(core())
        old = deepcopy(payload)
        value = deepcopy(payload["checks"][0])
        value["predicted_stdout"] = "0\n"
        delta = {"base_hash": digest(payload), "replacements": [{"collection": "checks", "key": "0", "value": value}], "unresolved": []}
        result = apply_teaching_repairs(payload, delta, {"checks": ["0"]})
        self.assertEqual(payload, old)
        self.assertEqual(result["checks"][1:], payload["checks"][1:])
        with self.assertRaisesRegex(Rejected, "out_of_scope"):
            apply_teaching_repairs(payload, delta, {"checks": []})
        delta["replacements"][0]["value"]["key"] = "new"
        with self.assertRaisesRegex(Rejected, "identity_change"):
            apply_teaching_repairs(payload, delta, {"checks": ["0"]})

    def test_optional_unresolved_does_not_block_valid_edit(self):
        payload = teaching(core())
        self.assertEqual(payload, apply_teaching_repairs(payload,
            {"base_hash": digest(payload), "replacements": []}, {}))
        with self.assertRaisesRegex(Rejected, "repair_fields"):
            apply_teaching_repairs(payload, {"base_hash": digest(payload), "replacements": [], "children": []}, {})

    def test_malformed_model_array_members_are_rejected_individually(self):
        payload = teaching(core())
        payload["misconceptions"].append("trailing model prose")
        doc, receipt = compile_teaching(core(), payload)
        self.assertEqual(len(doc["misconceptions"]), 1)
        self.assertEqual(receipt[-1]["status"], "rejected")

    def test_subset_rejects_external_calls_and_nonterminating_constructs(self):
        for code in ('system("x");', "while(1){}", '#include "x"', "int a[4];", 'printf("%n", 0);'):
            self.assertIsNotNone(restricted_code(code))
        self.assertIsNone(restricted_code('for(int i=0;i<3;i++) printf("%d",i);'))


if __name__ == "__main__":
    unittest.main()
