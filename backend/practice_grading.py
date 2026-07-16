"""Formal-practice grading with deterministic rules and guarded AI rubrics."""

from __future__ import annotations

import json
from typing import Any

from ai_base import AIBase
from practice_attempts import evidence_strength


class PracticeGrader(AIBase):
    async def grade(self, question: dict[str, Any], attempt: dict[str, Any]) -> dict[str, Any]:
        answer_payload = attempt.get("submitted_answer_payload") or attempt.get("answer_payload") or {}
        answer_spec = question.get("answer_spec") or {}
        grading_policy = question.get("grading_policy") or {}
        validation_policy = question.get("validation_policy") or {}
        method = str(grading_policy.get("method") or answer_spec.get("type") or "rubric_ai")
        strength = evidence_strength(attempt)

        if method in {"exact", "choice", "deterministic"}:
            result = self._grade_deterministic(answer_spec, answer_payload)
        else:
            result = await self._grade_rubric(question, answer_payload)
        result["evidence_strength"] = strength
        result["support_level"] = _support_level(attempt)
        result["grading_method"] = result.get("grading_method") or method
        allows_mastery = validation_policy.get("mastery_eligible")
        if allows_mastery is None:
            allows_mastery = question.get("practice_level") in {None, "mastery_check", "final_assessment"}
        max_support = int(validation_policy.get("max_support_level_for_mastery", 1))
        if not allows_mastery or result["support_level"] > max_support or strength in {"scaffolded", "invalid"}:
            result["mastery_eligible"] = False
        else:
            result["mastery_eligible"] = bool(result.get("passed")) and result.get("status") == "graded"
        return result

    @staticmethod
    def _grade_deterministic(answer_spec: dict[str, Any], answer_payload: dict[str, Any]) -> dict[str, Any]:
        expected = answer_spec.get("correct_answer")
        if expected is None:
            expected = answer_spec.get("correct_option_id")
        actual = answer_payload.get("value")
        if actual is None:
            actual = answer_payload.get("selected_option_id")
        if actual is None:
            actual = answer_payload.get("text")
        passed = _normalized(actual) == _normalized(expected)
        return {
            "status": "graded",
            "score": 100 if passed else 0,
            "passed": passed,
            "rubric_results": [{
                "criterion": "答案正确",
                "met": passed,
                "score": 100 if passed else 0,
                "feedback": "答案正确" if passed else "答案未达到本题要求",
            }],
            "feedback": "已达到本题要求" if passed else "请检查关键条件和答案",
            "grading_confidence": 1.0,
            "grading_method": "deterministic",
        }

    async def _grade_rubric(
        self,
        question: dict[str, Any],
        answer_payload: dict[str, Any],
    ) -> dict[str, Any]:
        text = str(answer_payload.get("text") or answer_payload.get("value") or "").strip()
        if not text:
            return {
                "status": "graded",
                "score": 0,
                "passed": False,
                "rubric_results": [],
                "feedback": "答案为空，尚未形成可评阅证据",
                "grading_confidence": 1.0,
                "grading_method": "rubric_validation",
            }
        if not self.client:
            return _pending_review("评分模型当前不可用，答案已保存并等待评阅")

        spec = question.get("answer_spec") or {}
        pass_score = int(spec.get("pass_score") or 70)
        criteria = [str(item) for item in spec.get("criteria") or []]
        expected = [str(item) for item in spec.get("expected_keywords") or []]
        prompt = json.dumps({
            "question": question.get("prompt"),
            "question_type": question.get("question_type"),
            "rubric": criteria,
            "reference_concepts": expected,
            "pass_score": pass_score,
            "student_answer": text,
            "required_output": {
                "score": "0-100 integer",
                "passed": "boolean",
                "confidence": "0-1 number",
                "feedback": "concise Chinese feedback",
                "rubric_results": [{
                    "criterion": "rubric item",
                    "met": "boolean",
                    "score": "0-100 integer",
                    "feedback": "evidence-based feedback",
                }],
            },
        }, ensure_ascii=False)
        response = await self._call_llm(
            prompt,
            system_prompt=(
                "你是严格的课程作答评阅器。只依据题目、量规和学生答案评分。"
                "不要因为出现关键词就判定正确，不得补写学生没有表达的推理。"
                "如果量规不足以可靠判断，将 confidence 设为低值。只输出 JSON。"
            ),
            use_fast_model=False,
            retry_count=2,
            enable_thinking=True,
        )
        parsed = self._extract_json(response or "") if response else None
        if not isinstance(parsed, dict):
            return _pending_review("自动评阅结果不可解析，答案已进入待评阅")
        try:
            score = max(0, min(100, int(round(float(parsed.get("score"))))))
            confidence = max(0.0, min(1.0, float(parsed.get("confidence"))))
        except (TypeError, ValueError):
            return _pending_review("自动评阅缺少可靠分数或置信度，答案已进入待评阅")
        threshold = float((question.get("grading_policy") or {}).get("confidence_threshold") or 0.72)
        if confidence < threshold or abs(score - pass_score) <= 3:
            pending = _pending_review("结果接近通过线或置信度不足，答案已进入待评阅")
            pending.update({
                "provisional_score": score,
                "grading_confidence": confidence,
                "rubric_results": _sanitize_rubric_results(parsed.get("rubric_results")),
            })
            return pending
        passed = score >= pass_score and parsed.get("passed") is not False
        return {
            "status": "graded",
            "score": score,
            "passed": passed,
            "rubric_results": _sanitize_rubric_results(parsed.get("rubric_results")),
            "feedback": str(parsed.get("feedback") or ("已达到本题量规" if passed else "尚未达到本题量规"))[:2000],
            "grading_confidence": confidence,
            "grading_method": "rubric_ai",
        }


def _pending_review(message: str) -> dict[str, Any]:
    return {
        "status": "pending_review",
        "score": None,
        "passed": None,
        "rubric_results": [],
        "feedback": message,
        "grading_confidence": 0.0,
        "grading_method": "rubric_ai",
        "mastery_eligible": False,
    }


def _support_level(attempt: dict[str, Any]) -> int:
    return max([
        0,
        int(attempt.get("ai_support_level") or 0),
        *[int(item) for item in attempt.get("revealed_hint_levels") or []],
        3 if attempt.get("solution_revealed") else 0,
    ])


_NONE_SENTINEL = "\0__none__\0"


def _normalized(value: Any) -> str:
    # `value is None` must be treated distinctly from falsy-but-answered values
    # like 0, 0.0, False, or "" — otherwise an unanswered question (actual=None)
    # can be misjudged as matching a legitimate expected answer of 0/False/"".
    if value is None:
        return _NONE_SENTINEL
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        return str(value)
    text = " ".join(str(value).strip().lower().split())
    if text in ("true", "false"):
        return text
    try:
        num = float(text)
    except ValueError:
        return text
    if num.is_integer():
        return str(int(num))
    return str(num)


def _sanitize_rubric_results(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value[:20]:
        if not isinstance(item, dict):
            continue
        try:
            score = max(0, min(100, int(round(float(item.get("score") or 0)))))
        except (TypeError, ValueError):
            score = 0
        result.append({
            "criterion": str(item.get("criterion") or "评分维度")[:500],
            "met": bool(item.get("met")),
            "score": score,
            "feedback": str(item.get("feedback") or "")[:1000],
        })
    return result


practice_grader = PracticeGrader()


__all__ = ["PracticeGrader", "practice_grader"]
