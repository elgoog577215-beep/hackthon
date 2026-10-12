"""Regression tests for bounded misconception programs and complete check intake."""
import unittest
from copy import deepcopy
from .diagnostic_templates import validate_parameters,build_diagnostic,grade_diagnostic
from .pipeline import Rejected,code_hash
from .round4_prepare import intake_checks
from .round4_prepare import apply_repairs
from .pipeline import digest
from .acceptance import sample_gate


class DiagnosticTests(unittest.TestCase):
    def gate_fixture(self):
        topics={};reviews={};criteria={}
        for t in ("types","if","for"):
            point={"id":"p","parent_id":"root"};check={"point_id":"p","answer":"a"}
            topics[t]={"core":{"root_id":"root","categories":[{"id":"root","parent_id":None}],"points":[point]},
                "primary_checks":[check],"relations":[],"diagnostic":{"plan":{},"grade":{"numeric_contract_passed":True}}}
            reviews[t]={"points":{"p":{"status":"accepted","hash":digest(point)}},
                "checks":{"p":{"status":"accepted","hash":digest(check)}},"relations":{},
                "coverage":{"c":{"status":"covered","refs":["p"]}},
                "source_facts":[{"status":"covered","refs":["p"]}],
                "diagnostic_plan_hash":digest({}),"diagnostic_semantics_accepted":True}
            criteria[t]=["c"]
        return topics,reviews,criteria

    def test_gate_requires_all_checks_current_review_and_source_coverage(self):
        topics,reviews,criteria=self.gate_fixture()
        self.assertTrue(sample_gate(topics,reviews,criteria)["passed"])
        topics["types"]["primary_checks"][0]["answer"]="changed"
        self.assertFalse(sample_gate(topics,reviews,criteria)["passed"])
        topics,reviews,criteria=self.gate_fixture()
        topics["if"]["primary_checks"]=[]
        self.assertFalse(sample_gate(topics,reviews,criteria)["passed"])
        topics,reviews,criteria=self.gate_fixture()
        reviews["for"]["source_facts"]=[]
        self.assertFalse(sample_gate(topics,reviews,criteria)["passed"])

    def test_gate_rejects_dangling_tree_even_with_positive_review(self):
        topics,reviews,criteria=self.gate_fixture()
        topics["types"]["core"]["points"][0]["parent_id"]="missing"
        reviews["types"]["points"]["p"]["hash"]=digest(topics["types"]["core"]["points"][0])
        self.assertFalse(sample_gate(topics,reviews,criteria)["passed"])

    def test_repair_can_fill_only_explicitly_missing_check(self):
        base={"primary_checks":[],"core":{"points":[{"id":"p"}]},"check_intake_errors":[{"reason":"missing_check"}],"relations":[]}
        value={"point_id":"p","question":"q","answer":"a","rationale":"r","tests_target":"t"}
        proposal={"base_hash":digest(base),"checks":[value],"relations":[],"unresolved":[]}
        scope={"point_ids":["p"],"relations":False,"relation_keys":[]}
        changed=apply_repairs(base,proposal,scope)
        self.assertEqual(changed["primary_checks"],[value])
        self.assertEqual(changed["check_intake_errors"],[])
        self.assertEqual(base["primary_checks"],[])
        proposal["checks"][0]["point_id"]="neighbor"
        with self.assertRaises(Rejected):apply_repairs(base,proposal,scope)

    def test_intake_does_not_count_duplicates_or_unrequested_points(self):
        def item(pid):return {"point_id":pid,"question":"q","answer":"a","rationale":"r","tests_target":"t"}
        accepted,errors=intake_checks(["p1","p2"],{"items":[item("p1"),item("p1"),item("other")]})
        self.assertEqual(accepted,{})
        self.assertEqual({e['point_id'] for e in errors if e['reason']=='missing_check'},{"p1","p2"})

    def test_rejects_parameters_that_hide_misconceptions(self):
        for topic,params in [
            ("types",{"n":6,"d":2,"retest_n":7,"retest_d":2}),
            ("types",{"n":5,"d":0,"retest_n":7,"retest_d":2}),
            ("types",{"n":5,"d":2,"retest_n":5,"retest_d":2}),
            ("if",{"initial":1,"then_value":1,"else_value":2,"retest_initial":3}),
            ("for",{"limit":3,"trigger":3,"retest_limit":4}),
            ("for",{"limit":3,"trigger":True,"retest_limit":4}),
            ("for",{"limit":30000000,"trigger":1,"retest_limit":30000001})]:
            with self.assertRaises(Rejected):validate_parameters(topic,params)

    def test_wrong_rule_codes_and_source_are_separate(self):
        p=build_diagnostic("for",{"limit":3,"trigger":1,"retest_limit":4},["p"],"test")
        self.assertEqual(len(p["checks"]),9)
        self.assertEqual(len({c["id"] for c in p["checks"]}),9)
        self.assertEqual(sum(c["counterfactual"] for c in p["checks"]),6)
        self.assertTrue(all("goto" not in c["code"] for c in p["checks"]))

    def test_predictions_require_all_exact_receipts(self):
        p=build_diagnostic("for",{"limit":3,"trigger":1,"retest_limit":4},["p"],"test")
        values={"symptom":{"correct":"4 2\n","a":"3 2\n","b":"3 2\n"},
                "diagnostic":{"correct":"3 2\n","a":"2 2\n","b":"3 3\n"},
                "retest":{"correct":"5 2\n","a":"4 2\n","b":"4 2\n"}}
        by_id={c["id"]:c for c in p["checks"]}
        receipts=[{"check_id":cid,"code_hash":code_hash(by_id[cid]),"status":"executed","returncode":0,
            "optimization_agrees":True,"stdout":values[role][belief]} for role,variants in p["roles"].items() for belief,cid in variants.items()]
        self.assertTrue(grade_diagnostic(p,receipts)["numeric_contract_passed"])
        self.assertFalse(grade_diagnostic(p,receipts[:-1])["numeric_contract_passed"])
        altered=deepcopy(receipts);altered[0]["code_hash"]="old"
        self.assertFalse(grade_diagnostic(p,altered)["numeric_contract_passed"])
        altered=deepcopy(receipts);altered[0]["stdout"]="3 2\n"
        self.assertIn("not_shared_wrong_prediction",grade_diagnostic(p,altered)["problems"])


if __name__=="__main__":unittest.main()
