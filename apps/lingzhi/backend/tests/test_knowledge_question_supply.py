import pytest

from knowledge_question_supply import knowledge_question_supply, select_knowledge_slots


def test_exact_selection_never_falls_back_to_whole_lecture():
    blueprint = {"nodes": [{"node_id": "n", "slots": [
        {"generation_key": "s1", "primary_knowledge_ids": ["k1"]},
        {"generation_key": "s2", "primary_knowledge_ids": ["k2"]},
    ]}]}
    assert select_knowledge_slots(blueprint, ["k2"], ["n"]) == {"n": ["s2"]}
    for ids, nodes in [(["missing"], ["n"]), (["k1"], ["other"]), (["k1"], ["n", "other"]), ([], ["n"])]:
        with pytest.raises(ValueError):
            select_knowledge_slots(blueprint, ids, nodes)


def test_supply_separates_sources_review_and_stale_revisions():
    base = {"knowledge_points": [{"knowledge_id": "k", "revision_id": "v1"}]}
    def task(rev, source="generated", point_revision="v1", **extra):
        return {"revision_id": rev, "primary_knowledge_ids": ["k"], "knowledge_revision_refs": {"k": point_revision}, "source_type": source, **extra}
    tasks = [task("a"), task("a"), task("b", "imported"), task("c", origin="adopted_authored_check"), task("old", point_revision="v0")]
    rows = knowledge_question_supply(base, tasks, [task("pending", lifecycle_status="needs_review"), task("retired", lifecycle_status="retired")])
    assert rows == [{"knowledge_id": "k", "revision_id": "v1", "available_count": 3, "pending_count": 1,
                     "sources": {"generated": 1, "imported": 1, "authored": 1}}]


def test_empty_bank_reports_zero_without_inventing_questions():
    rows = knowledge_question_supply({"knowledge_points": [{"knowledge_id": "k", "revision_id": "v"}]}, [], [])
    assert rows[0]["available_count"] == rows[0]["pending_count"] == 0


def test_historical_approval_rejected_by_current_checks_requires_review():
    base = {"knowledge_points": [{"knowledge_id": "k", "revision_id": "v"}]}
    item = {"revision_id": "old", "primary_knowledge_ids": ["k"], "knowledge_revision_refs": {"k": "v"}, "lifecycle_status": "approved"}
    row = knowledge_question_supply(base, [], [item])[0]
    assert row["available_count"] == 0 and row["pending_count"] == 1


def test_request_requires_frozen_baseline_and_cannot_expand_to_full_rebuild():
    from routers.question_bank import QuestionBankRebuildRequest, _selected_knowledge_slots
    from fastapi import HTTPException
    payload = dict(scope="nodes", node_ids=["n"], knowledge_ids=["k"], knowledge_baseline_revision="kb")
    request = QuestionBankRebuildRequest(**payload)
    course = {"course_knowledge_base": {"status": "accepted", "tree_schema": "atomic", "revision_id": "kb",
        "knowledge_points": [{"knowledge_id": "k", "granularity_status": "atomic", "meta_question": "检查本知识", "section_refs": ["n"]}]}}
    blueprint = {"nodes": [{"node_id": "n", "slots": [{"generation_key": "only-k", "primary_knowledge_ids": ["k"]}]}]}
    assert _selected_knowledge_slots(course, request, blueprint) == {"n": ["only-k"]}
    course["course_knowledge_base"]["revision_id"] = "new"
    with pytest.raises(HTTPException) as error:
        _selected_knowledge_slots(course, request, blueprint)
    assert error.value.status_code == 409
    for patch in [{"scope": "course"}, {"mode": "full"}, {"knowledge_baseline_revision": ""}, {"knowledge_ids": [" "]}]:
        with pytest.raises(ValueError):
            QuestionBankRebuildRequest(**{**payload, **patch})


def test_job_identity_includes_selected_knowledge_and_baseline(tmp_path):
    from question_bank_jobs import QuestionBankRebuildJobRepository
    jobs = QuestionBankRebuildJobRepository(tmp_path)
    args = dict(request_id="request-one", scope="nodes", node_ids=["n"], mode="incremental", actor_id="teacher", knowledge_baseline_revision="kb")
    first, created = jobs.create_job("course", knowledge_ids=["k1"], **args)
    same, repeated = jobs.create_job("course", knowledge_ids=["k1"], **args)
    other, other_created = jobs.create_job("course", knowledge_ids=["k2"], **args)
    assert created and not repeated and other_created
    assert first["job_id"] == same["job_id"] != other["job_id"]
    assert jobs.load("course", first["job_id"])["knowledge_ids"] == ["k1"]


def test_existing_unscoped_job_id_remains_compatible(tmp_path):
    from question_bank_jobs import QuestionBankRebuildJobRepository
    from course_versioning import stable_hash
    jobs = QuestionBankRebuildJobRepository(tmp_path)
    job, _ = jobs.create_job("course", request_id="previous-request", scope="nodes", node_ids=["n"], mode="incremental", actor_id="teacher")
    legacy_payload = {"course_id": "course", "request_id": "previous-request", "scope": "nodes", "node_ids": ["n"], "revision_ids": [], "material_asset_ids": [], "material_scope_explicit": False, "mode": "incremental", "retrieval_enabled": False, "assessment_generation_profile": "complete", "teacher_instruction": ""}
    assert job["job_id"] == stable_hash(legacy_payload, prefix="qbr_")


def test_student_assets_drop_rejected_bank_snapshots_and_preserve_material(monkeypatch):
    import question_bank
    import knowledge_practice
    from knowledge_question_supply import current_question_assets
    authored = {"revision_id": "material", "origin": "adopted_authored_check"}
    current = {"revision_id": "current", "assessment_role": "practice"}
    final = {"revision_id": "final", "assessment_role": "coverage_task"}
    monkeypatch.setattr(question_bank, "approved_formal_tasks", lambda bank: [current, final])
    monkeypatch.setattr(knowledge_practice, "adopted_knowledge_checks", lambda course: [authored])
    stale = {"questions": [{"revision_id": "rejected-old"}], "checklist": [{"id": "keep"}]}
    result = current_question_assets({}, stale, {"items": []})
    assert result["questions"] == [current, authored]
    assert result["final_assessment"] == [final]
    assert stale["questions"][0]["revision_id"] == "rejected-old"
    assert result["checklist"] == stale["checklist"]
    assert current_question_assets({}, stale, None) == stale


def test_formal_practice_uses_revalidated_task_and_keeps_authored_source(monkeypatch):
    from routers import practice
    import knowledge_practice
    authored = {"revision_id": "material", "origin": "adopted_authored_check"}
    fresh = {"revision_id": "q", "question_bank_item_revision_id": "item", "node_id": "n", "practice_level": "concept_check", "evidence_admission": {"current": True}}
    stale = {**fresh, "evidence_admission": {"current": False}}
    monkeypatch.setattr(knowledge_practice, "adopted_knowledge_checks", lambda course: [authored])
    monkeypatch.setattr(practice, "_question_bank_practice_tasks", lambda course: [fresh])
    monkeypatch.setattr(practice, "_has_active_question_bank", lambda course: True)
    assert practice._question_bank_practice_overlay({}, [stale]) == [fresh, authored]
    monkeypatch.setattr(practice, "_question_bank_practice_tasks", lambda course: [])
    assert practice._question_bank_practice_overlay({}, [stale]) == [authored]
