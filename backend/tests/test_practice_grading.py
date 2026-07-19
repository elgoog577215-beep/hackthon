import pytest

from practice_grading import PracticeGrader, _normalized, _repair_numeric_literals


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


def test_numeric_literal_repair_is_scoped_and_rejects_ambiguous_values():
    original = (
        '{"score": "between 70 and 80", "confidence": 80%, '
        '"feedback": "score: 狂欢76s"}'
    )

    repaired = _repair_numeric_literals(original)

    assert '"score": "between 70 and 80"' in repaired
    assert '"confidence": 0.8' in repaired
    assert '"feedback": "score: 狂欢76s"' in repaired


@pytest.mark.asyncio
async def test_rubric_grading_recovers_single_numeric_literal_noise(monkeypatch):
    grader = PracticeGrader()
    grader.client = object()

    async def fake_call(*_args, **_kwargs):
        return """{
          "score": 狂欢76s,
          "passed": true,
          "confidence": 0.8,
          "feedback": "计算和复合顺序解释正确。",
          "rubric_results": [
            {
              "criterion": "比较 AB 与 BA 并解释原因",
              "met": true,
              "score": 76分,
              "feedback": "给出了可检查的计算与解释。"
            }
          ]
        }"""

    monkeypatch.setattr(grader, "_call_llm", fake_call)
    question = {
        "prompt": "计算 AB 和 BA，并解释为什么通常不相等。",
        "question_type": "derivation",
        "practice_level": "mastery_check",
        "answer_spec": {
            "type": "rubric",
            "criteria": ["比较 AB 与 BA 并解释原因"],
            "expected_keywords": ["线性映射复合", "不可交换"],
            "pass_score": 70,
        },
        "grading_policy": {
            "method": "rubric_ai",
            "confidence_threshold": 0.72,
        },
        "validation_policy": {
            "mastery_eligible": True,
            "max_support_level_for_mastery": 1,
        },
    }
    result = await grader.grade(question, {
        "status": "submitted",
        "submitted_answer_payload": {"text": "给出完整计算与结果检查"},
        "revealed_hint_levels": [],
    })

    assert result["status"] == "graded"
    assert result["score"] == 76
    assert result["passed"] is True
    assert result["grading_confidence"] == 0.8
    assert result["rubric_results"][0]["score"] == 76


@pytest.mark.asyncio
async def test_rubric_grading_receives_hidden_canonical_answer_and_solution_trace(
    monkeypatch,
):
    grader = PracticeGrader()
    grader.client = object()
    captured = {}

    async def fake_call(prompt, **_kwargs):
        captured["prompt"] = prompt
        return """{
          "score": 85,
          "passed": true,
          "confidence": 0.9,
          "feedback": "旋转和遍历结果正确。",
          "rubric_results": [
            {
              "criterion": "旋转判断正确",
              "met": true,
              "score": 85,
              "feedback": "与标准过程一致。"
            }
          ]
        }"""

    monkeypatch.setattr(grader, "_call_llm", fake_call)
    question = {
        "prompt": "向AVL树插入给定键并说明旋转。",
        "question_type": "worked_solution",
        "practice_level": "mastery_check",
        "answer_spec": {
            "criteria": ["旋转判断正确"],
            "canonical_answer": {
                "preorder": [30, 20, 10, 25, 40, 50],
                "rotations": ["在30执行LL右旋", "在20执行RR左旋"],
            },
            "solution_trace": [
                "插入10后在30执行LL右旋",
                "插入50后在20执行RR左旋",
            ],
            "pass_score": 70,
        },
        "grading_policy": {
            "method": "rubric_ai_with_reference",
            "confidence_threshold": 0.72,
        },
        "validation_policy": {
            "mastery_eligible": True,
            "max_support_level_for_mastery": 1,
        },
    }

    result = await grader.grade(question, {
        "status": "submitted",
        "submitted_answer_payload": {
            "text": "两次旋转后先序为30,20,10,25,40,50。",
        },
        "revealed_hint_levels": [],
    })

    prompt = captured["prompt"]
    assert '"canonical_answer"' in prompt
    assert "在30执行LL右旋" in prompt
    assert '"solution_trace"' in prompt
    assert result["passed"] is True
