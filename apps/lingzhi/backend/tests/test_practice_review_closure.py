from routers.practice import _pending_review_attempts, _attempt_summary
from practice_attempts import PracticeAttemptRepository
from routers.practice import _knowledge_revision_pairs


def test_correct_concept_practice_is_not_a_wrong_answer():
    attempt = {"attempt_id": "concept", "status": "graded", "result": {"passed": True, "mastery_eligible": False}}
    assert _pending_review_attempts([attempt]) == []
    assert _attempt_summary([attempt])["needs_review"] == 0


def test_targeted_retry_closes_pending_review_and_keeps_history():
    original = {"attempt_id": "original", "status": "graded", "result": {"passed": False}}
    retry = {
        "attempt_id": "retry",
        "origin_attempt_id": "original",
        "practice_intent": "targeted_retry",
        "status": "graded",
        "result": {"passed": True, "mastery_eligible": False},
    }
    attempts = [original, retry]
    assert _pending_review_attempts(attempts) == []
    assert _attempt_summary(attempts)["total"] == 2
    assert original["result"]["passed"] is False
    retry["result"]["passed"] = False
    assert _pending_review_attempts(attempts) == [retry]


def test_unfinished_retry_does_not_erase_original_mistake():
    original = {"attempt_id": "original", "status": "graded", "result": {"passed": False}}
    retry = {
        "attempt_id": "retry",
        "origin_attempt_id": "original",
        "practice_intent": "targeted_retry",
        "status": "in_progress",
    }
    assert _pending_review_attempts([original, retry]) == [original]


def test_fresh_attempt_cannot_reset_seen_solution_evidence(tmp_path):
    repository = PracticeAttemptRepository(tmp_path)
    first, _ = repository.create_once("student", "course", {"task_revision_id": "q1"})
    repository.reveal_solution("student", "course", first["attempt_id"], expected_revision=first["revision"])
    second, _ = repository.create_once("student", "course", {"task_revision_id": "q1", "resume": False})
    assert second["solution_revealed"] is True
    assert second["solution_exposure_origin_attempt_id"] == first["attempt_id"]
    third, _ = repository.create_once("student", "course", {"task_revision_id": "q2", "resume": False})
    assert third["solution_revealed"] is False


def test_targeted_retry_matches_exact_knowledge_revisions_in_saved_mapping():
    assert _knowledge_revision_pairs({"knowledge_revision_refs": {"vector": "v1"}}) == {("vector", "v1")}
    assert not _knowledge_revision_pairs({"knowledge_revision_refs": {"vector": "v1"}}).intersection(
        _knowledge_revision_pairs({"knowledge_revision_refs": {"vector": "v2"}})
    )
