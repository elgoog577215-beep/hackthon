from copy import deepcopy
from pathlib import Path
import pytest
from .pipeline import read
from .teaching_round import assess, UNITS
from .teaching_review import FINDINGS

ARTIFACT = Path(__file__).resolve().parents[2] / "docs/研究/知识树教学能力补全"


def test_all_frozen_points_have_observable_criteria_and_stable_references():
    tree = read(ARTIFACT / "知识树教学补全候选.json")
    assert len(tree["skill_units"]) == 15
    ids = {p["knowledge_id"] for p in tree["knowledge_points"]}
    assert len(ids) == 49
    assert {i for s in tree["skill_units"] for i in s["knowledge_ids"]} == ids
    assert len(tree["mastery_criteria"]) == 49
    assert {i for c in tree["mastery_criteria"] for i in c["knowledge_ids"]} == ids
    assert len(tree["diagnostic_sets"]) == len(tree["practice_units"]) == 15
    assert len(tree["remediation_units"]) == 45
    assert not tree["teaching_assessment"]["ready_for_adoption"]
    assert len(FINDINGS) == len(UNITS) == 15
    assert all(not d["diagnostic_validated"] for d in tree["diagnostic_sets"])


@pytest.mark.parametrize("mutation", ["missing", "foreign_probe", "repeated", "foreign_point"])
def test_source_coverage_guards_reject_bad_framework(mutation):
    row = read(ARTIFACT / "千问原始教学候选.json")[0]
    doc = deepcopy(row["generated"])
    if mutation == "missing": doc["criteria"].pop()
    if mutation == "foreign_probe": doc["criteria"][0]["probe_key"] = "Q-F01"
    if mutation == "repeated": doc["criteria"][1] = deepcopy(doc["criteria"][0])
    if mutation == "foreign_point": doc["mistakes"][0]["point_keys"] = ["K-F01"]
    assert not assess(row["input"], doc)["structure_passed"]


def test_frozen_answers_are_not_model_predictions():
    tree = read(ARTIFACT / "知识树教学补全候选.json")
    assert next(c for c in tree["mastery_criteria"] if c["point_key"] == "K-T07")["probe"]["answer"] == "-3"
    assert next(p for p in tree["practice_units"] if p["retest"]["question"].startswith("设 int a=9"))["retest"]["answer"].endswith("值为9。")


def test_different_ids_do_not_make_duplicate_questions_independent_evidence():
    row = next(r for r in read(ARTIFACT / "千问原始教学候选.json") if r["unit_key"] == "I2")
    assert "duplicate_probe_content" in assess(row["input"], row["generated"])["warnings"]


def test_unknown_prediction_is_not_an_observed_difference():
    row = read(ARTIFACT / "千问原始教学候选.json")[0]
    report = assess(row["input"], row["generated"])
    assert any(w.startswith("no_demonstrated_pair_separation") for w in report["warnings"])
