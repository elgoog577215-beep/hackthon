from copy import deepcopy

from knowledge_mastery import build_knowledge_profile, freeze_knowledge_refs


def base():
    return {"lifecycle_status": "active", "revision_id": "kb1", "concept_groups": [{"concept_group_id": "g", "name": "基础"}], "knowledge_points": [
        {"knowledge_id": f"k{i}", "revision_id": f"r{i}", "name": f"知识{i}", "primary_concept_group_id": "g", "granularity_status": "atomic", "status": "active"}
        for i in range(1, 11)
    ]}


def attempt(number=1, passed=True, **extra):
    return {"attempt_id": f"a{number}", "user_id": "u", "course_id": "c", "course_version_id": "cv1", "task_revision_id": f"q{number}", "concept_ids": ["k1"], "knowledge_revision_refs": {"k1": "r1"}, "status": "graded", "updated_at": f"2026-10-11T10:{number:02}:00Z", "result": {"passed": passed, "grading_confidence": .95, "support_level": 0}, **extra}


def project(attempts=None, events=None, kb=None):
    return build_knowledge_profile(kb or base(), course_id="c", course_version_id="cv1", user_id="u", attempts=attempts or [], events=events or [])


def test_unknown_is_not_zero_mastery_and_activities_do_not_score():
    events = [{"event_id": "e", "user_id": "u", "course_id": "c", "course_version_id": "cv1", "concept_ids": ["k1"], "event_type": "learner_self_reported"}]
    model = project(events=events)
    assert model["nodes"][0]["mastery"] is None
    assert model["nodes"][0]["activity_count"] == 1
    assert model["summary"]["verified_progress"] == 0
    assert model["summary"]["assessed_average"] is None


def test_independent_evidence_increases_and_new_failure_decreases():
    first = project([attempt()])["nodes"][0]["mastery"]
    second = project([attempt(), attempt(2)])["nodes"][0]["mastery"]
    third = project([attempt(), attempt(2), attempt(3, False)])["nodes"][0]["mastery"]
    assert first < second and third < second
    assert project([attempt(), attempt(2), attempt(3)])["nodes"][0]["status"] == "supported_mastery"


def test_same_question_latest_result_replaces_instead_of_farming():
    a = attempt()
    b = attempt(2, task_revision_id="q1")
    assert project([a, b, a])["nodes"][0]["mastery"] == project([a])["nodes"][0]["mastery"]
    assert project([a, b])["nodes"][0]["assessment_count"] == 1


def test_feedback_after_full_answer_preserves_previous_valid_mastery():
    original = attempt()
    feedback = attempt(2, task_revision_id="q1", solution_revealed=True)
    node = project([original, feedback])["nodes"][0]
    assert node["mastery"] == project([original])["nodes"][0]["mastery"]
    assert node["assessment_count"] == 1
    assert node["independent_count"] == 1
    assert any(e["support"] == "solution_seen" and not e["counted"] for e in node["evidence"])


def test_assisted_and_revealed_answers_do_not_claim_independent_mastery():
    assisted = attempt(result={"passed": True, "grading_confidence": .95, "support_level": 2})
    assert project([assisted])["nodes"][0]["mastery"] < project([attempt()])["nodes"][0]["mastery"]
    assert project([assisted])["nodes"][0]["confidence"] == "limited"
    revealed = attempt(solution_revealed=True)
    assert project([revealed])["nodes"][0]["mastery"] is None


def test_user_course_revision_and_low_quality_isolation():
    for change in ({"user_id": "other"}, {"course_id": "other"}, {"course_version_id": "old"}, {"knowledge_revision_refs": {"k1": "old"}}, {"knowledge_revision_refs": {}}, {"status": "grading"}, {"result": {"passed": True, "grading_confidence": .2}}):
        assert project([attempt(**change)])["nodes"][0]["mastery"] is None


def test_composite_score_is_not_copied_to_each_point():
    result = project([attempt(concept_ids=["k1", "k2"], knowledge_revision_refs={"k1": "r1", "k2": "r2"})])
    assert result["summary"]["assessed_count"] == 0
    assert result["nodes"][0]["pending_attribution_count"] == 1


def test_unique_leaf_denominator_and_no_mutation():
    kb = base()
    kb["knowledge_points"].append(deepcopy(kb["knowledge_points"][0]))
    before = deepcopy(kb)
    result = project([attempt()], kb=kb)
    assert result["summary"]["total_count"] == 10
    assert result["summary"]["coverage"] == 10
    assert result["summary"]["verified_progress"] == 6.7
    assert result["branches"][0]["summary"] == result["summary"]
    assert kb == before


def test_candidate_tree_is_not_a_formal_profile():
    kb = base()
    kb["lifecycle_status"] = "candidate"
    assert project(kb=kb)["availability"] == "tree_unavailable"


def test_freeze_uses_only_exact_server_task_ids():
    assert freeze_knowledge_refs(base(), {"concept_ids": ["k1", "unknown"], "course_knowledge_refs": ["k2"]}) == {"k1": "r1"}


def test_ineligible_passes_cannot_claim_independent_mastery():
    rows = [attempt(i, result={"passed": True, "grading_confidence": .99, "support_level": 0, "mastery_eligible": False}) for i in range(1, 5)]
    node = project(rows)["nodes"][0]
    assert node["independent_count"] == 0
    assert node["status"] != "supported_mastery"
    assert node["evidence"][0]["support"] == "practice_only"


def test_bound_note_and_ai_events_count_activity_not_mastery():
    kb = base()
    kb["knowledge_points"][0]["course_block_refs"] = ["b1"]
    common = {"user_id": "u", "course_id": "c", "course_version_id": "cv1"}
    events = [{**common, "event_id": "n", "event_type": "learning_record_created", "record_id": "note", "evidence": {"anchor": {"block_id": "b1"}}},
              {**common, "event_id": "n2", "event_type": "learning_record_updated", "record_id": "note", "evidence": {"anchor": {"block_id": "b1"}}},
              {**common, "event_id": "ai", "event_type": "assistant_question_submitted", "metadata": {"block_id": "b1"}}]
    node = project(events=events, kb=kb)["nodes"][0]
    assert node["activity_count"] == 2
    assert node["mastery"] is None


def test_frozen_knowledge_revision_survives_attempt_storage(tmp_path):
    from practice_attempts import PracticeAttemptRepository
    repository = PracticeAttemptRepository(tmp_path)
    saved, created = repository.create_once("u", "c", {
        "task_revision_id": "q1", "course_version_id": "cv1", "concept_ids": ["k1"],
        "knowledge_revision_refs": freeze_knowledge_refs(base(), {"concept_ids": ["k1"]}),
    })
    assert created
    assert repository.get("u", "c", saved["attempt_id"])["knowledge_revision_refs"] == {"k1": "r1"}
    assert repository.list("other", "c") == []
