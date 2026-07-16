from practice_grading import PracticeGrader, _normalized


def _deterministic(expected, actual):
    answer_spec = {"type": "exact", "correct_answer": expected}
    answer_payload = {"value": actual}
    return PracticeGrader._grade_deterministic(answer_spec, answer_payload)


def test_normalized_none_is_not_zero():
    assert _normalized(None) != _normalized(0)


def test_normalized_none_is_not_false():
    assert _normalized(None) != _normalized(False)


def test_normalized_none_is_not_empty_string():
    assert _normalized(None) != _normalized("")


def test_unanswered_question_with_correct_answer_zero_is_not_graded_correct():
    result = _deterministic(expected=0, actual=None)
    assert result["passed"] is False
    assert result["score"] == 0


def test_unanswered_question_with_correct_answer_false_is_not_graded_correct():
    result = _deterministic(expected=False, actual=None)
    assert result["passed"] is False
    assert result["score"] == 0


def test_answer_zero_matches_expected_zero():
    result = _deterministic(expected=0, actual=0)
    assert result["passed"] is True
    assert result["score"] == 100


def test_answer_zero_string_matches_expected_zero_int():
    result = _deterministic(expected=0, actual="0")
    assert result["passed"] is True


def test_answer_false_matches_expected_false():
    result = _deterministic(expected=False, actual=False)
    assert result["passed"] is True
    assert result["score"] == 100


def test_answer_false_string_matches_expected_false_bool():
    result = _deterministic(expected=False, actual="false")
    assert result["passed"] is True


def test_answer_false_string_case_insensitive_matches():
    result = _deterministic(expected="False", actual=False)
    assert result["passed"] is True


def test_normal_string_answer_correct():
    result = _deterministic(expected="北京", actual="北京")
    assert result["passed"] is True
    assert result["score"] == 100


def test_normal_string_answer_incorrect():
    result = _deterministic(expected="北京", actual="上海")
    assert result["passed"] is False
    assert result["score"] == 0


def test_unanswered_normal_string_question_is_not_graded_correct():
    result = _deterministic(expected="北京", actual=None)
    assert result["passed"] is False
