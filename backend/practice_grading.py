"""Formal-practice grading with deterministic rules and guarded AI rubrics."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from ai_base import AIBase
from assessment_validators import validate_candidate_answer
from code_runner_client import (
    CodeRunnerUnavailable,
    code_runner_client,
)
from practice_attempts import evidence_strength


logger = logging.getLogger(__name__)


class PracticeGrader(AIBase):
    async def grade(self, question: dict[str, Any], attempt: dict[str, Any]) -> dict[str, Any]:
        answer_payload = attempt.get("submitted_answer_payload") or attempt.get("answer_payload") or {}
        answer_spec = question.get("answer_spec") or {}
        grading_policy = question.get("grading_policy") or {}
        validation_policy = question.get("validation_policy") or {}
        method = str(grading_policy.get("method") or answer_spec.get("type") or "rubric_ai")
        strength = evidence_strength(attempt)

        if method == "runner":
            result = await self._grade_code_runner(
                question,
                answer_spec,
                answer_payload,
            )
        elif method == "typed_validator":
            result = self._grade_typed(
                question,
                answer_spec,
                answer_payload,
            )
        elif method in {"exact", "choice", "deterministic"}:
            result = self._grade_deterministic(answer_spec, answer_payload)
        else:
            result = await self._grade_rubric(question, answer_payload)
        result["evidence_strength"] = strength
        result["support_level"] = _support_level(attempt)
        result["grading_method"] = result.get("grading_method") or method
        allows_mastery = validation_policy.get("mastery_eligible")
        if allows_mastery is None:
            allows_mastery = question.get("practice_level") in {None, "mastery_check", "final_assessment"}
        compiled_validation = (
            question.get("compiled_contract_validation") or {}
        )
        compiled_hash = str(
            question.get("compiled_contract_hash") or ""
        )
        policy_hash = str(
            validation_policy.get("compiled_contract_hash")
            or ""
        )
        if (
            (
                (question.get("question_spec") or {}).get(
                    "schema_version"
                )
                == "question_spec_v2"
                and compiled_validation.get("passed") is not True
            )
            or (
                compiled_hash
                and policy_hash
                and compiled_hash != policy_hash
            )
        ):
            allows_mastery = False
        max_support = int(validation_policy.get("max_support_level_for_mastery", 1))
        if not allows_mastery or result["support_level"] > max_support or strength in {"scaffolded", "invalid"}:
            result["mastery_eligible"] = False
        else:
            result["mastery_eligible"] = bool(result.get("passed")) and result.get("status") == "graded"
        return result

    @staticmethod
    def _grade_typed(
        question: dict[str, Any],
        answer_spec: dict[str, Any],
        answer_payload: dict[str, Any],
    ) -> dict[str, Any]:
        mode = str(
            question.get("validation_mode")
            or answer_spec.get("validation_mode")
            or ""
        )
        actual: Any = answer_payload
        if mode == "exact_validator":
            input_contract = question.get("input_contract") or {}
            selection = input_contract.get("selection") or {}
            if selection.get("multiple"):
                actual = sorted(
                    str(item)
                    for item in answer_payload.get(
                        "selected_option_ids"
                    ) or []
                )
                expected = answer_spec.get("canonical_answer")
                if isinstance(expected, list):
                    answer_spec = {
                        **answer_spec,
                        "canonical_answer": sorted(
                            str(item) for item in expected
                        ),
                    }
            else:
                actual = (
                    answer_payload.get("selected_option_id")
                    if answer_payload.get("selected_option_id")
                    is not None
                    else answer_payload.get("text")
                )
        elif mode == "symbolic_validator":
            actual = (
                answer_payload.get("conclusion")
                or answer_payload.get("text")
                or answer_payload
            )
        elif mode == "state_trace_validator":
            actual = (
                answer_payload.get("trace")
                or answer_payload.get("selected_option_id")
                or answer_payload
            )
        result = validate_candidate_answer(
            mode,
            answer_spec.get("canonical_answer"),
            actual,
            answer_spec.get("validator_config") or {},
        )
        passed = bool(result.get("passed"))
        return {
            "status": "graded",
            "score": 100 if passed else 0,
            "passed": passed,
            "rubric_results": [],
            "feedback": (
                "已通过确定性验证"
                if passed
                else "答案未通过确定性验证，请检查条件、过程和结果"
            ),
            "grading_confidence": float(
                result.get("confidence") or 1.0
            ),
            "grading_method": mode,
            "validator_result": result,
        }

    async def _grade_code_runner(
        self,
        question: dict[str, Any],
        answer_spec: dict[str, Any],
        answer_payload: dict[str, Any],
    ) -> dict[str, Any]:
        config = answer_spec.get("validator_config") or {}
        bundle_id = str(config.get("test_bundle_id") or "")
        code = str(answer_payload.get("code") or "")
        language = str(
            answer_payload.get("language")
            or (question.get("input_contract") or {}).get(
                "language"
            )
            or "python"
        )
        if not bundle_id or not code:
            return _pending_review(
                "代码或隐藏测试包不可用，答案已保存并等待处理"
            )
        try:
            result = await code_runner_client.judge(
                task_revision_id=str(
                    question.get("task_revision_id")
                    or question.get("revision_id")
                    or ""
                ),
                language=language,
                code=code,
                test_bundle_id=bundle_id,
            )
        except CodeRunnerUnavailable:
            return _pending_review(
                "安全判题服务暂不可用，答案已保存且不会降级到本进程执行"
            )
        passed = bool(result.get("passed"))
        total = int(result.get("total_count") or 0)
        passed_count = int(result.get("passed_count") or 0)
        score = (
            int(round(passed_count * 100 / total))
            if total
            else 0
        )
        return {
            "status": "graded",
            "score": score,
            "passed": passed,
            "rubric_results": [],
            "feedback": (
                f"隐藏测试通过 {passed_count}/{total}"
                if total
                else "隐藏测试未返回有效结果"
            ),
            "grading_confidence": 1.0,
            "grading_method": "isolated_runner",
            "runner_result": {
                key: result.get(key)
                for key in (
                    "status",
                    "passed_count",
                    "total_count",
                    "failure_categories",
                    "resource_usage",
                )
            },
        }

    @staticmethod
    def _grade_deterministic(answer_spec: dict[str, Any], answer_payload: dict[str, Any]) -> dict[str, Any]:
        expected = answer_spec.get("correct_answer")
        if expected is None:
            expected = (
                answer_spec.get("correct_option_ids")
                or answer_spec.get("correct_option_id")
            )
        actual = answer_payload.get("value")
        if actual is None:
            actual = (
                answer_payload.get("selected_option_ids")
                or answer_payload.get("selected_option_id")
            )
        if actual is None:
            actual = answer_payload.get("text")
        if isinstance(expected, list) and isinstance(actual, list):
            expected = sorted(str(item) for item in expected)
            actual = sorted(str(item) for item in actual)
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
        raw_answer = (
            answer_payload.get("text")
            or answer_payload.get("value")
        )
        if raw_answer is None and answer_payload:
            raw_answer = json.dumps(
                answer_payload,
                ensure_ascii=False,
                sort_keys=True,
            )
        text = str(raw_answer or "").strip()
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
            "reference_answer": {
                "canonical_answer": spec.get("canonical_answer"),
                "solution_trace": spec.get("solution_trace")
                or (spec.get("solution_spec") or {}).get("steps")
                or [],
                "result_checks": (
                    (spec.get("solution_spec") or {}).get("checks")
                    or question.get("result_checks")
                    or []
                ),
            },
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
                "reference_answer是隐藏的标准依据，用它核对结果和过程，"
                "但不要要求学生逐字复述，也不要在反馈中泄露完整标准答案。"
                "不要因为出现关键词就判定正确，不得补写学生没有表达的推理。"
                "如果量规不足以可靠判断，将 confidence 设为低值。只输出 JSON。"
                "score 和 rubric_results[].score 必须是 0 到 100 的纯数字，"
                "confidence 必须是 0 到 1 的纯数字，不得添加单位、解释或其他字符。"
            ),
            use_fast_model=False,
            retry_count=2,
            enable_thinking=False,
        )
        parsed = None
        if response:
            # Repair only the explicitly numeric grading fields before the generic
            # JSON-repair fallback runs.  The fallback can otherwise turn a token
            # such as `狂欢76s` into an arbitrary string while still returning a
            # dict, which prevents the guarded numeric recovery below from ever
            # getting a chance to run.
            repaired_response = _repair_numeric_literals(response)
            parsed = self._extract_json(repaired_response)
            if repaired_response != response and isinstance(parsed, dict):
                logger.warning("Recovered rubric grading JSON with malformed numeric literals")
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


_NUMERIC_FIELD_PATTERN = re.compile(
    r'(?P<prefix>"(?P<field>score|confidence)"\s*:\s*)(?P<value>[^,\n}\]]+)'
)


def _repair_numeric_literals(text: str) -> str:
    """Repair one-number scalar noise without inventing a grading judgment."""

    def replace(match: re.Match[str]) -> str:
        raw_value = match.group("value").strip()
        numeric_tokens = re.findall(r"-?\d+(?:\.\d+)?", raw_value)
        if len(numeric_tokens) != 1:
            return match.group(0)
        number = float(numeric_tokens[0])
        field = match.group("field")
        if field == "score":
            if not 0 <= number <= 100:
                return match.group(0)
        elif not 0 <= number <= 1:
            if "%" in raw_value and 0 <= number <= 100:
                number /= 100
            else:
                return match.group(0)
        normalized = str(int(number)) if number.is_integer() else str(number)
        return f"{match.group('prefix')}{normalized}"

    return _NUMERIC_FIELD_PATTERN.sub(replace, text)


practice_grader = PracticeGrader()


__all__ = ["PracticeGrader", "practice_grader"]
