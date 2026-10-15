from copy import deepcopy

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from assessment_compiler import compile_formal_task_contract
from question_bank import (QuestionBankRepository, finalize_v2_question_bank_item,
                           refresh_question_bank_bundle, review_question_bank_item,
                           approved_formal_tasks, migrate_question_bank_review_policy,
                           load_active_question_bank)
from question_solution_revisions import revise_open_question_solution
from routers import question_bank as api


def _fields():
    answer = "先核对资源约束，再用公开的评价标准比较候选方案；证据不足时保留条件结论。"
    return {
        "canonical_answer": answer,
        "acceptable_answers": [],
        "rubric": ["区分硬约束与可权衡指标，说明评价依据和结论边界"],
        "misconception_rules": [],
        "worked_solution": {"summary": "比较候选方案前先核对资源约束并明确评分口径。",
                            "steps": ["核对每个方案所需的资源和时限，再比较可行方案的目标表现。"],
                            "final_answer": answer, "checks": ["评价依据和结论一致"]},
        "solution_graph": {"schema_version": "solution_graph_v1", "steps": [
            {"step_id": f"step-{i}", "action": action, "check": check}
            for i, action, check in [
                (1, "逐项核对材料中的预算和时间要求", "已知事实与额外假设分别列出"),
                (2, "选取互不重复的指标并解释其作用", "权重有依据且没有重复计入约束"),
                (3, "根据明确的假设比较方案并复核结论", "改变假设后说明结论可能如何变化"),
            ]
        ]},
    }


def _bundle():
    solution = {"schema_version": "solution_envelope_v1", "solution_revision_id": "sol_old",
                "validation_mode": "expert_rubric_validator", "validator_config": {}, **_fields(),
                "independent_solution_record": {"answer_hash": "old-proof"}}
    item = finalize_v2_question_bank_item({
        "item_id": "item-1", "course_id": "course-1", "node_id": "lesson-1",
        "source_type": "generated", "question_type": "scenario_deliverable",
        "prompt": "某团队比较候选方案，请说明评价标准和决策过程。",
        "practice_levels": ["mastery_check"], "course_knowledge_refs": ["decision"],
        "difficulty": "intermediate", "source_records": [{"block_id": "block-1"}],
        "question_spec": {"schema_version": "question_spec_v2", "solution_revision_id": "sol_old",
                          "stimulus": {"rendered_text": "旧材料"}, "task": {"rendered_text": "旧任务"},
                          "input_contract": {"schema_version": "input_contract_v2", "mode": "rich_text",
                                             "required": True}},
        "solution_validation": {"passed": True, "status": "passed", "semantic_confidence": .99},
        "semantic_preflight": {"passed": True},
        "knowledge_binding": {"status": "bound", "knowledge_ids": ["kp-old"],
                              "knowledge_revision_refs": {"kp-old": "kpr-old"}},
    }, solution)
    item.update(lifecycle_status="approved", review_status="approved")
    return refresh_question_bank_bundle({"course_id": "course-1", "items": [item],
                                         "solution_envelopes": {"sol_old": solution}})


def _request():
    return {"expected_solution_revision_id": "sol_old", "stimulus": "团队有预算和时间限制，候选方案尚未完成试验。",
            "task": "说明如何依据资源和目标比较方案，并给出条件结论。", "constraints": ["说明额外假设"],
            "solution_fields": _fields(), "editor_id": "owner", "note": "修正原答案的绝对判断"}


def test_revision_preserves_history_invalidates_old_proof_and_rebinds_hints(tmp_path):
    original = _bundle()
    before = deepcopy(original)
    repository = QuestionBankRepository(tmp_path)
    repository.save_bundle("course-1", original)
    old = original["items"][0]
    changed = revise_open_question_solution(original, old["revision_id"], **_request())
    item = changed["items"][0]
    solution = changed["solution_envelopes"][item["solution_revision_id"]]
    assert original == before
    assert changed["solution_envelopes"]["sol_old"] == original["solution_envelopes"]["sol_old"]
    assert item["revision_id"] != old["revision_id"]
    assert solution["parent_solution_revision_id"] == "sol_old"
    assert "independent_solution_record" not in solution
    assert "semantic_preflight" not in item
    assert not item["solution_validation"]["checks"]["independent_agreement"]
    assert item["review_status"] == "needs_review" and item["review_required"]
    assert item["knowledge_binding"]["status"] == "unbound"
    assert item["hint_contract"]["grounding"]["solution_revision_id"] == item["solution_revision_id"]
    assert item["question_spec"]["task"]["rendered_text"] in item["prompt"]
    assert item["question_spec"]["solution_revision_id"] == item["solution_revision_id"]
    assert not approved_formal_tasks(changed)
    approved = review_question_bank_item(changed, item["revision_id"], decision="approved", reviewer_id="owner")
    assert approved_formal_tasks(approved)
    assert not approved_formal_tasks(approved)[0]["validation_policy"]["mastery_eligible"]
    repository.save_bundle("course-1", changed)
    assert repository.load_bundle("course-1", original["bundle_revision_id"]) == original


@pytest.mark.parametrize("kind", ["stale", "unknown", "mismatch", "graph", "protocol", "atomic", "exact", "note"])
def test_invalid_edits_do_not_mutate_bundle(kind):
    bundle = _bundle()
    req = _request()
    item = bundle["items"][0]
    if kind == "stale": req["expected_solution_revision_id"] = "sol_stale"
    if kind == "unknown": req["solution_fields"]["independent_solution_record"] = {"passed": True}
    if kind == "mismatch": req["solution_fields"]["worked_solution"]["final_answer"] = "contradiction"
    if kind == "graph": req["solution_fields"]["solution_graph"]["steps"][0].pop("step_id")
    if kind == "protocol": bundle["solution_envelopes"]["sol_old"]["final_solution_review"] = {"schema_version": "assessment_solution_protocol_v1", "accepted": True}
    if kind == "atomic": item["assessment_binding_schema"] = "atomic_assessment_v1"
    if kind == "exact": bundle["solution_envelopes"]["sol_old"]["validation_mode"] = "exact_validator"
    if kind == "note": req["note"] = " "
    before = deepcopy(bundle)
    with pytest.raises(ValueError):
        revise_open_question_solution(bundle, item["revision_id"], **req)
    assert bundle == before


def test_invalidated_answer_changes_contract_hash_and_excludes_mastery():
    item = _bundle()["items"][0]
    before = compile_formal_task_contract(item, _bundle()["solution_envelopes"]["sol_old"])
    item["solution_validation"]["independent_review_invalidated"] = True
    after = compile_formal_task_contract(item, _bundle()["solution_envelopes"]["sol_old"])
    assert before["validation_policy"]["mastery_eligible"]
    assert not after["validation_policy"]["mastery_eligible"]
    assert after["compiled_contract_hash"] != before["compiled_contract_hash"]


def test_old_approval_does_not_publish_changed_answer_during_policy_migration():
    bundle = _bundle()
    bundle["items"][0]["review_history"] = [{"decision": "approved", "item_revision_id": "older"}]
    changed = revise_open_question_solution(bundle, bundle["items"][0]["revision_id"], **_request())
    migrated = migrate_question_bank_review_policy({"course_id": "course-1"}, changed)
    assert migrated["items"][0]["review_status"] == "needs_review"
    assert not approved_formal_tasks(migrated)


def test_private_revision_requires_owner_current_bundle_and_idle_generation(monkeypatch, tmp_path):
    bundle = _bundle()
    repo = QuestionBankRepository(tmp_path)
    repo.save_bundle("course-1", bundle)
    course_data = {"course_id": "course-1", "owner_id": "owner", "authoring_surface": "teacher"}
    active = load_active_question_bank(course_data, repository=repo)
    async def course(_): return deepcopy(course_data)
    monkeypatch.setattr(api, "get_course_or_404", course)
    monkeypatch.setattr(api, "question_bank_repository", repo)
    monkeypatch.setattr(api.question_bank_rebuild_job_repository, "active_for_course", lambda _: None)
    app = FastAPI()
    app.include_router(api.router, prefix="/api")
    client = TestClient(app)
    path = f'/api/courses/course-1/question-bank/items/{active["items"][0]["revision_id"]}/solution-revisions'
    req = _request()
    req.pop("editor_id")
    req["expected_bundle_revision_id"] = active["bundle_revision_id"]
    assert client.post(path, headers={"X-User-Id": "student"}, json=req).status_code == 404
    stale = {**req, "expected_bundle_revision_id": "qbb_stale"}
    assert client.post(path, headers={"X-User-Id": "owner"}, json=stale).status_code == 409
    monkeypatch.setattr(api.question_bank_rebuild_job_repository, "active_for_course", lambda _: {"status": "running"})
    assert client.post(path, headers={"X-User-Id": "owner"}, json=req).status_code == 409
    monkeypatch.setattr(api.question_bank_rebuild_job_repository, "active_for_course", lambda _: None)
    response = client.post(path, headers={"X-User-Id": "owner"}, json=req)
    assert response.status_code == 201, response.text
    assert response.json()["review_status"] == "needs_review"
    assert "canonical_answer" not in response.text
    assert repo.load_bundle("course-1", bundle["bundle_revision_id"]) == bundle
    assert client.post(path, headers={"X-User-Id": "owner"}, json=req).status_code == 409
