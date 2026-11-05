from copy import deepcopy
import json

import pytest

from study.service import concept_source, has_concepts, reading_tool_states, reading_tools_complete, validate_plans


def sample(section_id="s", revision_id="r"):
    section = {"id": section_id, "title": "导数与极值", "complete": True, "blocks": [
        {"block_id": "definition", "content_type": "definition", "content": "导数描述变化率。"},
        {"block_id": "method", "content_type": "method", "content": "先检查可导性。可导时求导，不可导时用定义。<details>隐藏解答</details>"},
        {"block_id": "answer", "content_type": "answer", "content": "自测答案。"},
        {"block_id": "linked", "content_type": "example", "answer_to": "q", "content": "关联答案。"},
        {"block_id": "question", "content_type": "exercise", "content": "请独立求解。"},
    ]}
    source = concept_source({"id": revision_id}, section)
    refs = [{"evidence_id": "method", "quote": "不应保存模型引文", "revision_id": "fake"}]
    plan = {"node_id": section_id,
            "knowledge_structure": [{"knowledge_points": [{"name": "导数", "statement": "变化率", "source_refs": refs}]}],
            "knowledge_relations": [], "learning_paths": [{"title": "怎样选择求导方法", "kind": "method", "steps": [
                {"id": "start", "parent_id": "", "stage": "start", "text": "检查可导性", "source_refs": refs},
                {"id": "yes", "parent_id": "start", "stage": "step", "condition": "可导", "text": "使用求导规则", "reason": "满足求导条件", "source_refs": refs},
                {"id": "no", "parent_id": "start", "stage": "step", "condition": "不可导或待判断", "text": "回到定义", "reason": "不能直接用求导规则", "source_refs": refs},
            ]}]}
    return section, source, plan


def validate(plan, source, prior=None):
    return validate_plans(json.dumps({"sections": [plan]}), [source], reading=True, prior=prior)[0]


def test_paths_bind_every_step_to_saved_passages_without_answer_sources():
    _, source, plan = sample()
    assert [b["block_id"] for b in source["blocks"]] == ["definition", "method"]
    assert "隐藏解答" not in source["blocks"][1]["text"]
    result = validate(plan, source)
    assert result["reading_schema_version"] == "study_reading_v1"
    refs = result["learning_paths"][0]["steps"][1]["source_refs"]
    assert refs[0]["revision_id"] == "r" and refs[0]["block_id"] == "method"
    assert "quote" not in refs[0]
    assert result == validate(plan, source)


def test_parallel_explanations_do_not_require_invented_selection_conditions():
    _, source, plan = sample()
    steps = plan["learning_paths"][0]["steps"]
    for step in steps[1:]:
        step["condition"] = ""
    result = validate(plan, source)
    assert [step["condition"] for step in result["learning_paths"][0]["steps"]] == ["", "", ""]
    assert [step["parent_id"] for step in result["learning_paths"][0]["steps"]] == ["", "start", "start"]


def test_explicit_choice_still_requires_a_condition_on_each_alternative():
    _, source, plan = sample()
    steps = plan["learning_paths"][0]["steps"]
    choice = {"id": "choose", "parent_id": "start", "stage": "choice", "text": "根据可导性选择方法",
              "reason": "方法有不同的成立条件", "source_refs": [{"evidence_id": "method"}]}
    for step in steps[1:]:
        step.update(parent_id="choose", condition="")
    steps.insert(1, choice)
    with pytest.raises(ValueError, match="分支缺少选择条件"):
        validate(plan, source)


@pytest.mark.parametrize("bad", ["answer", "foreign", "cycle", "branch", "reason", "stage"])
def test_invalid_sources_and_ambiguous_paths_are_rejected_without_repair(bad):
    _, source, plan = sample()
    step = plan["learning_paths"][0]["steps"][1]
    if bad in {"answer", "foreign"}:
        step["source_refs"] = [{"evidence_id": bad}]
    elif bad == "cycle":
        step["parent_id"] = step["id"]
    elif bad == "branch":
        step["condition"] = ""
    elif bad == "reason":
        step["reason"] = ""
    else:
        step["stage"] = "invented"
    with pytest.raises(ValueError):
        validate(plan, source)


def test_cross_lecture_links_require_an_exact_known_identity():
    _, source, plan = sample()
    first = validate(plan, source)["knowledge_structure"][0]["knowledge_points"][0]
    _, other_source, other = sample("s2")
    # Identical names in two lectures still have distinct identities.
    second = validate(other, other_source)["knowledge_structure"][0]["knowledge_points"][0]
    assert first["knowledge_id"] != second["knowledge_id"]
    other["knowledge_relations"] = [{"source_knowledge_id": first["knowledge_id"], "target_name": "导数",
        "relation_type": "generalizes", "reason": "本讲扩展前讲定义", "conditions": ["沿用同一极限定义"],
        "source_refs": [{"evidence_id": "method"}]}]
    result = validate(other, other_source, [first])
    assert result["knowledge_relations"][0]["source_knowledge_id"] == first["knowledge_id"]
    with pytest.raises(ValueError, match="概念"):
        validate(other, other_source, [])


def test_reading_status_distinguishes_legacy_missing_and_stale_text_or_revision():
    section, source, plan = sample()
    material = {"revisions": [{"id": "r", "sections": [section]}], "plans": []}
    assert reading_tool_states(material) == {"s": "missing"}
    material["plans"] = [plan]
    assert reading_tool_states(material) == {"s": "legacy"}
    saved = {**validate(plan, source), "handout_revision_id": "r", "handout_sha256": source["source_sha256"],
             "reading_source_sha256": source["reading_source_sha256"]}
    material["plans"] = [saved]
    assert reading_tool_states(material) == {"s": "ready"}
    changed = deepcopy(material)
    changed["revisions"][0]["sections"][0]["blocks"][0]["content"] += "补充条件"
    assert reading_tool_states(changed) == {"s": "stale"}
    changed = deepcopy(material)
    changed["revisions"][0]["id"] = "new-revision"
    assert reading_tool_states(changed) == {"s": "stale"}


@pytest.mark.parametrize("metadata", [{"content_type": "answer"}, {"answer_to": "question"}, {"content_type": "theorem"}])
def test_reading_fingerprint_detects_metadata_changes_without_changing_legacy_digest(metadata):
    section, source, plan = sample()
    saved = {**validate(plan, source), "handout_revision_id": "r", "handout_sha256": source["source_sha256"],
             "reading_source_sha256": source["reading_source_sha256"]}
    changed = deepcopy(section)
    changed["blocks"][1].update(metadata)
    new_source = concept_source({"id": "r"}, changed)
    assert source["source_sha256"] == new_source["source_sha256"]
    assert source["reading_source_sha256"] != new_source["reading_source_sha256"]
    assert not has_concepts(saved, changed, {"id": "r"})
    material = {"revisions": [{"id": "r", "sections": [changed]}], "plans": [saved]}
    assert reading_tool_states(material) == {"s": "stale"}


def test_empty_extraction_is_complete_and_old_unbound_aids_stay_legacy():
    section, source, plan = sample()
    plan.update(knowledge_structure=[], knowledge_relations=[], learning_paths=[])
    saved = {**validate(plan, source), "handout_revision_id": "r", "handout_sha256": source["source_sha256"],
             "reading_source_sha256": source["reading_source_sha256"]}
    material = {"revisions": [{"id": "r", "sections": [section]}], "plans": [saved], "request": {}}
    assert reading_tools_complete(material)
    saved.pop("reading_source_sha256")
    assert reading_tool_states(material) == {"s": "legacy"}
    assert not reading_tools_complete(material)
