"""同源题目合同编译与作答后 AI 诊断。

首次课程生成从题目、私有解答合同和课程本地 AssessmentIntent 确定性编译题目分析，
不再调用 AI 预检或返工。学生提交答案后，AI 才按需理解真实作答并映射到允许的课程
知识、能力与易错 ID；映射不替代评分，也不得创造 ID。
"""

from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from typing import Any

from ai_base import AIBase, AIProviderUnavailable
from course_versioning import stable_hash

QUESTION_ANALYSIS_SCHEMA = "question_analysis_v1"
ANSWER_DIAGNOSIS_SCHEMA = "answer_diagnosis_v1"
ASSESSMENT_INTENT_SCHEMA = "assessment_intent_v1"
# 4 (not 8): each analyzed question yields a large structured payload; batches
# of 8 regularly overflowed even a 16k completion budget.
QUESTION_ANALYSIS_BATCH_SIZE = 4


class PracticeAnalysisUnavailable(RuntimeError):
    """The independent analysis stage did not produce a usable result."""


def build_assessment_intent(
    question: dict[str, Any],
    knowledge_base: dict[str, Any],
) -> dict[str, Any]:
    """Compile the claimed assessment target from the course-local truth."""
    point_ids = _ids(question, "course_knowledge_refs", "concept_ids")
    skill_ids = _ids(question, "course_skill_refs", "skill_unit_ids")
    misconception_ids = _ids(
        question,
        "course_misconception_refs",
        "mistake_point_ids",
        "misconception_ids",
    )
    mastery_ids = _ids(question, "course_mastery_refs")

    point_by_id = {
        str(item.get("knowledge_id") or ""): item
        for item in knowledge_base.get("knowledge_points") or []
    }
    skill_by_id = {
        str(item.get("skill_id") or ""): item
        for item in knowledge_base.get("skill_units") or []
    }
    misconception_by_id = {
        str(item.get("misconception_id") or ""): item
        for item in knowledge_base.get("misconceptions") or []
    }
    mastery_by_id = {
        str(item.get("criterion_id") or ""): item
        for item in knowledge_base.get("mastery_criteria") or []
    }

    if not mastery_ids:
        mastery_ids = [
            criterion_id
            for criterion_id, item in mastery_by_id.items()
            if set(_clean_ids(item.get("knowledge_ids"))) & set(point_ids)
        ]

    target_knowledge = [
        {
            "id": point_id,
            "name": str(point_by_id.get(point_id, {}).get("name") or point_id),
            "statement": str(point_by_id.get(point_id, {}).get("statement") or ""),
            "conditions": _strings(point_by_id.get(point_id, {}).get("conditions")),
            "boundaries": _strings(point_by_id.get(point_id, {}).get("boundaries")),
        }
        for point_id in point_ids
    ]
    target_skills = [
        {
            "id": skill_id,
            "name": str(skill_by_id.get(skill_id, {}).get("name") or skill_id),
            "observable_behavior": str(
                skill_by_id.get(skill_id, {}).get("observable_behavior") or ""
            ),
        }
        for skill_id in skill_ids
    ]
    target_misconceptions = [
        {
            "id": misconception_id,
            "name": str(
                misconception_by_id.get(misconception_id, {}).get("name")
                or misconception_id
            ),
            "observable_error_pattern": str(
                misconception_by_id.get(misconception_id, {}).get(
                    "observable_error_pattern"
                )
                or ""
            ),
            "discrimination": str(
                misconception_by_id.get(misconception_id, {}).get(
                    "discrimination"
                )
                or ""
            ),
        }
        for misconception_id in misconception_ids
    ]
    mastery_criteria = [
        {
            "id": criterion_id,
            "name": str(mastery_by_id.get(criterion_id, {}).get("name") or criterion_id),
            "observable_performance": str(
                mastery_by_id.get(criterion_id, {}).get("observable_performance")
                or ""
            ),
            "verification_method": str(
                mastery_by_id.get(criterion_id, {}).get("verification_method") or ""
            ),
        }
        for criterion_id in mastery_ids
    ]

    level = str(question.get("practice_level") or "objective_practice")
    why = {
        "concept_check": "确认学习者能否准确解释核心含义、成立条件和边界。",
        "objective_practice": "确认学习者能否把本节知识迁移到不同于正文的新情境。",
        "mastery_check": "确认学习者能否在较少支架下综合完成本节掌握任务。",
        "final_assessment": "确认学习者能否跨章节整合知识并独立完成综合任务。",
    }.get(level, "确认学习者能否独立完成当前正式学习任务。")
    answer_spec = question.get("answer_spec") or {}
    question_spec = question.get("question_spec") or {}
    response_contract = question_spec.get("response_contract") or {}
    answer_invariants = (
        _strings(answer_spec.get("criteria"))
        or _strings(question.get("result_checks"))
        or _strings(response_contract.get("required_parts"))
    )
    observable_actions = [
        item["observable_behavior"]
        for item in target_skills
        if item["observable_behavior"]
    ] or answer_invariants
    intent = {
        "schema_version": ASSESSMENT_INTENT_SCHEMA,
        "course_id": str(knowledge_base.get("course_id") or ""),
        "question_id": str(question.get("question_id") or question.get("asset_id") or ""),
        "practice_level": level,
        "why_this_question": why,
        "target_knowledge": target_knowledge,
        "target_skills": target_skills,
        "target_misconceptions": target_misconceptions,
        "mastery_criteria": mastery_criteria,
        "observable_actions": observable_actions,
        "answer_invariants": answer_invariants,
        "difficulty_contract": deepcopy(question.get("difficulty_contract") or {}),
    }
    intent["revision_id"] = stable_hash(intent, prefix="air_")
    return intent


def normalize_question_analysis(
    question: dict[str, Any],
    free_analysis: dict[str, Any],
    mapped_analysis: dict[str, Any],
) -> dict[str, Any]:
    """Validate an AI analysis against the same-source assessment intent."""
    intent = question.get("assessment_intent") or {}
    allowed = {
        "knowledge_ids": _intent_ids(intent, "target_knowledge"),
        "skill_ids": _intent_ids(intent, "target_skills"),
        "misconception_ids": _intent_ids(intent, "target_misconceptions"),
    }
    mapping = mapped_analysis.get("mapping") or {}
    issues = _normalize_quality_issues(
        (mapped_analysis.get("quality") or {}).get("issues")
    )
    normalized_mapping: dict[str, list[str]] = {}
    unknown_ids: list[str] = []
    for field, valid_ids in allowed.items():
        requested = _clean_ids(mapping.get(field))
        unknown_ids.extend(item for item in requested if item not in valid_ids)
        normalized_mapping[field] = [item for item in requested if item in valid_ids]
    if unknown_ids:
        issues.append({
            "gate": "same_source_scope",
            "severity": "critical",
            "message": f"题目解析返回了当前课程范围外的 ID：{sorted(set(unknown_ids))}",
        })

    task_goal = str(free_analysis.get("task_goal") or "").strip()
    required_actions = _strings(free_analysis.get("required_actions"))
    answer_invariants = _strings(free_analysis.get("answer_invariants"))
    if not task_goal:
        issues.append({
            "gate": "question_understanding",
            "severity": "critical",
            "message": "题目解析没有说明这道题要求学习者完成什么。",
        })
    if not required_actions:
        issues.append({
            "gate": "observable_skill",
            "severity": "critical",
            "message": "题目解析没有识别可观察的作答动作。",
        })
    if not answer_invariants:
        issues.append({
            "gate": "answerability",
            "severity": "critical",
            "message": "题目解析没有形成可验证的答案成立条件。",
        })

    library_fit = _library_fit(allowed, normalized_mapping)
    if library_fit == "MISS":
        issues.append({
            "gate": "target_alignment",
            "severity": "critical",
            "message": "独立题目解析未证明题目实际考查了声明的知识或能力。",
        })
    raw_quality = mapped_analysis.get("quality") or {}
    quality_passed = bool(raw_quality.get("passed")) and not any(
        item.get("severity") == "critical" for item in issues
    )
    analysis = {
        "schema_version": QUESTION_ANALYSIS_SCHEMA,
        "status": "passed" if quality_passed else "blocked",
        "analysis_source": "ai_independent",
        "assessment_intent_revision_id": intent.get("revision_id"),
        "question_understanding": {
            "task_goal": task_goal,
            "required_actions": required_actions,
            "key_conditions": _strings(free_analysis.get("key_conditions")),
            "answer_invariants": answer_invariants,
            "acceptable_variations": _strings(
                free_analysis.get("acceptable_variations")
            ),
            "likely_wrong_paths": _strings(free_analysis.get("likely_wrong_paths")),
        },
        "mapping": {
            **normalized_mapping,
            "library_fit": library_fit,
            "reason": str(mapping.get("reason") or ""),
        },
        "quality": {
            "passed": quality_passed,
            "difficulty_fit": str(raw_quality.get("difficulty_fit") or ""),
            "rubric_fit": str(raw_quality.get("rubric_fit") or ""),
            "ambiguity": str(raw_quality.get("ambiguity") or ""),
            "issues": issues,
        },
        "reference_solution": _normalize_reference_solution(
            mapped_analysis.get("reference_solution")
        ),
    }
    analysis["analysis_revision_id"] = stable_hash(analysis, prefix="qar_")
    return analysis


def compile_question_analysis_from_contract(
    question: dict[str, Any],
) -> dict[str, Any]:
    """Compile answer-diagnosis context from the same-source question contract.

    Generation no longer asks another model to rediscover targets that were
    already frozen in ``AssessmentIntent`` and ``QuestionSpec``.
    """
    intent = question.get("assessment_intent") or {}
    knowledge_ids = _intent_ids(intent, "target_knowledge")
    skill_ids = _intent_ids(intent, "target_skills")
    misconception_ids = _intent_ids(
        intent,
        "target_misconceptions",
    )
    required_actions = _strings(intent.get("observable_actions"))
    answer_invariants = _strings(intent.get("answer_invariants"))
    question_spec = question.get("question_spec") or {}
    response_contract = question_spec.get("response_contract") or {}
    prompt = str(question.get("prompt") or "").strip()
    answer_spec = question.get("answer_spec") or {}

    issues: list[dict[str, str]] = []
    required_contracts = (
        (prompt, "question_understanding", "题目缺少可执行题干"),
        (
            knowledge_ids,
            "target_alignment",
            "题目没有绑定课程知识 ID",
        ),
        (
            skill_ids,
            "observable_skill",
            "题目没有绑定可观察能力 ID",
        ),
        (
            required_actions,
            "observable_skill",
            "题目没有可观察作答动作",
        ),
        (
            answer_invariants,
            "answerability",
            "题目没有可判定答案成立条件",
        ),
    )
    for value, gate, message in required_contracts:
        if value:
            continue
        issues.append({
            "gate": gate,
            "severity": "critical",
            "message": message,
        })
    if not (
        _strings(answer_spec.get("criteria"))
        or _strings(answer_spec.get("expected_keywords"))
        or _strings(response_contract.get("required_parts"))
    ):
        issues.append({
            "gate": "answerability",
            "severity": "critical",
            "message": "题目缺少私有解答或响应判定合同",
        })

    allowed = {
        "knowledge_ids": knowledge_ids,
        "skill_ids": skill_ids,
        "misconception_ids": misconception_ids,
    }
    mapping = {
        **deepcopy(allowed),
        "library_fit": _library_fit(allowed, allowed),
        "reason": "由 AssessmentIntent 与 QuestionSpec 同源编译",
    }
    key_conditions = _strings(response_contract.get("required_parts"))
    for item in intent.get("target_knowledge") or []:
        if not isinstance(item, dict):
            continue
        key_conditions.extend(_strings(item.get("conditions")))
        key_conditions.extend(_strings(item.get("boundaries")))
    likely_wrong_paths = [
        "；".join(
            part
            for part in (
                str(item.get("name") or "").strip(),
                str(item.get("observable_error_pattern") or "").strip(),
                str(item.get("discrimination") or "").strip(),
            )
            if part
        )
        for item in intent.get("target_misconceptions") or []
        if isinstance(item, dict)
    ]
    passed = not issues and mapping["library_fit"] == "HIT"
    analysis = {
        "schema_version": QUESTION_ANALYSIS_SCHEMA,
        "status": "passed" if passed else "blocked",
        "analysis_source": "compiled_contract",
        "assessment_intent_revision_id": intent.get("revision_id"),
        "question_understanding": {
            "task_goal": str(
                intent.get("why_this_question")
                or prompt
            ),
            "required_actions": required_actions,
            "key_conditions": list(dict.fromkeys(key_conditions)),
            "answer_invariants": answer_invariants,
            "acceptable_variations": _strings(
                response_contract.get("acceptable_variations")
            ),
            "likely_wrong_paths": [
                item for item in likely_wrong_paths if item
            ],
        },
        "mapping": mapping,
        "quality": {
            "passed": passed,
            "difficulty_fit": "contract_bound",
            "rubric_fit": (
                "contract_bound" if not any(
                    item.get("gate") == "answerability"
                    for item in issues
                )
                else "blocked"
            ),
            "ambiguity": "contract_checked",
            "issues": issues,
        },
        "reference_solution": {
            "approach": str(
                answer_spec.get("approach")
                or intent.get("why_this_question")
                or ""
            ),
            "key_steps": (
                _strings(answer_spec.get("criteria"))
                or _strings(answer_spec.get("expected_keywords"))
                or answer_invariants
            ),
            "self_check": "；".join(answer_invariants),
        },
    }
    analysis["analysis_revision_id"] = stable_hash(
        analysis,
        prefix="qar_",
    )
    return analysis


def unavailable_answer_diagnosis(reason: str) -> dict[str, Any]:
    return {
        "schema_version": ANSWER_DIAGNOSIS_SCHEMA,
        "status": "unavailable",
        "reason": reason,
    }


class PracticeAnalysisService(AIBase):
    """作答后 AI 诊断；旧题目预检方法仅保留历史数据兼容，不接入生成主链。"""

    async def analyze_questions(
        self,
        questions: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not questions:
            return []
        if not self.client:
            raise PracticeAnalysisUnavailable("question analysis model is not configured")
        chunks = [
            [
                deepcopy(item)
                for item in questions[start:start + QUESTION_ANALYSIS_BATCH_SIZE]
            ]
            for start in range(0, len(questions), QUESTION_ANALYSIS_BATCH_SIZE)
        ]
        analyzed_chunks = await asyncio.gather(*[
            self._analyze_question_chunk(chunk)
            for chunk in chunks
        ])
        return [
            question
            for chunk in analyzed_chunks
            for question in chunk
        ]

    async def repair_blocked_questions(
        self,
        questions: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Rewrite only blocked prompts while preserving their formal intent."""
        blocked = [
            deepcopy(item)
            for item in questions
            if (item.get("question_analysis") or {}).get("status") == "blocked"
        ]
        if not blocked:
            return [deepcopy(item) for item in questions]
        if not self.client:
            raise PracticeAnalysisUnavailable("question repair model is not configured")
        chunks = [
            blocked[start:start + QUESTION_ANALYSIS_BATCH_SIZE]
            for start in range(0, len(blocked), QUESTION_ANALYSIS_BATCH_SIZE)
        ]
        repaired_chunks = await asyncio.gather(*[
            self._repair_question_chunk(chunk)
            for chunk in chunks
        ])
        repaired_by_source = {
            str((item.get("question_repair") or {}).get("source_revision_id") or ""): item
            for chunk in repaired_chunks
            for item in chunk
        }
        return [
            repaired_by_source.get(str(item.get("revision_id") or ""), deepcopy(item))
            for item in questions
        ]

    async def _repair_question_chunk(
        self,
        chunk: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        result = await self._call_json(
            {
                "questions": [
                    {
                        "question_revision_id": item.get("revision_id"),
                        "prompt": item.get("prompt"),
                        "question_type": item.get("question_type"),
                        "practice_level": item.get("practice_level"),
                        "answer_spec": item.get("answer_spec"),
                        "assessment_intent": item.get("assessment_intent"),
                        "question_analysis": item.get("question_analysis"),
                    }
                    for item in chunk
                ]
            },
            system_prompt=_QUESTION_REPAIR_SYSTEM_PROMPT,
        )
        values = result.get("repairs") if isinstance(result, dict) else None
        repair_by_revision = _by_revision(
            values if isinstance(values, list) else [],
            "question_revision_id",
        )
        repaired: list[dict[str, Any]] = []
        for question in chunk:
            source_revision_id = str(question.get("revision_id") or "")
            repair = repair_by_revision.get(source_revision_id) or {}
            prompt = str(repair.get("prompt") or "").strip()
            if not prompt or prompt == str(question.get("prompt") or "").strip():
                raise PracticeAnalysisUnavailable(
                    f"question repair missing changed prompt for {source_revision_id}"
                )
            revised = deepcopy(question)
            revised["prompt"] = prompt
            revised.pop("question_analysis", None)
            revised["question_repair"] = {
                "source_revision_id": source_revision_id,
                "attempt": 1,
                "reason": str(repair.get("repair_summary") or "根据题目解析问题定点重写题干"),
            }
            revised["revision_id"] = stable_hash(
                {
                    key: value
                    for key, value in revised.items()
                    if key not in {"revision_id", "question_analysis"}
                },
                prefix="qrr_",
            )
            repaired.append(revised)
        return repaired

    async def _analyze_question_chunk(
        self,
        chunk: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        free = await self._free_question_analysis(chunk)
        mapped = await self._map_question_analysis(chunk, free)
        free_by_id = _by_revision(free, "question_revision_id")
        mapped_by_id = _by_revision(mapped, "question_revision_id")
        missing = [
            question
            for question in chunk
            if str(question.get("revision_id") or "") not in free_by_id
            or str(question.get("revision_id") or "") not in mapped_by_id
        ]
        if missing:
            # The model sometimes silently drops a question from its response.
            # Re-ask once for just the dropped subset before degrading.
            retry_free = await self._free_question_analysis(missing)
            retry_mapped = await self._map_question_analysis(missing, retry_free)
            free_by_id.update(_by_revision(retry_free, "question_revision_id"))
            mapped_by_id.update(
                _by_revision(retry_mapped, "question_revision_id")
            )
        analyzed: list[dict[str, Any]] = []
        for question in chunk:
            revision_id = str(question.get("revision_id") or "")
            if revision_id not in free_by_id or revision_id not in mapped_by_id:
                # A single unanalyzed question must not fail the whole course:
                # mark it blocked so the existing repair/review path owns it.
                question["question_analysis"] = normalize_question_analysis(
                    question,
                    {},
                    {},
                )
                analyzed.append(question)
                continue
            question["question_analysis"] = normalize_question_analysis(
                question,
                free_by_id[revision_id],
                mapped_by_id[revision_id],
            )
            analyzed.append(question)
        return analyzed

    async def diagnose_answer(
        self,
        question: dict[str, Any],
        attempt: dict[str, Any],
    ) -> dict[str, Any]:
        preflight = question.get("question_analysis") or {}
        if preflight.get("status") != "passed":
            return unavailable_answer_diagnosis("question_not_preflighted")
        if not self.client:
            return unavailable_answer_diagnosis("analysis_model_not_configured")
        answer = deepcopy(
            attempt.get("submitted_answer_payload")
            or attempt.get("answer_payload")
            or {}
        )
        if question.get("question_type") == "single_choice":
            selected_option_id = str(
                (answer or {}).get("selected_option_id") or ""
            )
            selected_option = next(
                (
                    item
                    for item in question.get("options") or []
                    if str(
                        item.get("option_id")
                        or item.get("id")
                        or item.get("value")
                        or ""
                    )
                    == selected_option_id
                ),
                {},
            )
            answer = {
                "selected_option_id": selected_option_id,
                "selected_option_text": str(
                    selected_option.get("text")
                    or selected_option.get("label")
                    or selected_option.get("value")
                    or ""
                ),
                "evidence_scope": "selected_option_only",
            }
        try:
            free = await self._call_json(
                {
                    "question": {
                        "prompt": question.get("prompt"),
                        "question_type": question.get("question_type"),
                        "practice_level": question.get("practice_level"),
                        "options": deepcopy(question.get("options") or []),
                        "question_understanding": preflight.get(
                            "question_understanding"
                        ),
                    },
                    "student_answer": answer,
                    "support": {
                        "revealed_hint_levels": attempt.get(
                            "revealed_hint_levels"
                        )
                        or [],
                        "ai_support_level": int(
                            attempt.get("ai_support_level") or 0
                        ),
                        "active_seconds": int(attempt.get("active_seconds") or 0),
                    },
                },
                system_prompt=_ANSWER_FREE_SYSTEM_PROMPT,
            )
            mapped = await self._call_json(
                {
                    "free_diagnosis": free,
                    "assessment_intent": question.get("assessment_intent") or {},
                },
                system_prompt=_ANSWER_MAPPING_SYSTEM_PROMPT,
            )
        except (PracticeAnalysisUnavailable, AIProviderUnavailable):
            return unavailable_answer_diagnosis("analysis_model_failed")
        return _normalize_answer_diagnosis(question, free, mapped)

    async def _free_question_analysis(
        self,
        questions: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        payload = {
            "questions": [
                {
                    "question_revision_id": item.get("revision_id"),
                    "prompt": item.get("prompt"),
                    "question_type": item.get("question_type"),
                    "practice_level": item.get("practice_level"),
                    "answer_spec": item.get("answer_spec"),
                    "difficulty_contract": item.get("difficulty_contract"),
                }
                for item in questions
            ]
        }
        result = await self._call_json(
            payload,
            system_prompt=_QUESTION_FREE_SYSTEM_PROMPT,
        )
        values = result.get("analyses") if isinstance(result, dict) else None
        if not isinstance(values, list):
            raise PracticeAnalysisUnavailable("free question analysis is incomplete")
        return values

    async def _map_question_analysis(
        self,
        questions: list[dict[str, Any]],
        free_analyses: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        payload = {
            "questions": [
                {
                    "question_revision_id": item.get("revision_id"),
                    "prompt": item.get("prompt"),
                    "answer_spec": item.get("answer_spec"),
                    "assessment_intent": item.get("assessment_intent"),
                    "free_analysis": next(
                        (
                            analysis
                            for analysis in free_analyses
                            if str(analysis.get("question_revision_id") or "")
                            == str(item.get("revision_id") or "")
                        ),
                        {},
                    ),
                }
                for item in questions
            ]
        }
        result = await self._call_json(
            payload,
            system_prompt=_QUESTION_MAPPING_SYSTEM_PROMPT,
        )
        values = result.get("analyses") if isinstance(result, dict) else None
        if not isinstance(values, list):
            raise PracticeAnalysisUnavailable("mapped question analysis is incomplete")
        return values

    async def _call_json(
        self,
        payload: dict[str, Any],
        *,
        system_prompt: str,
    ) -> dict[str, Any]:
        parsed: Any = None
        # Thinking is deliberately OFF here: with reasoning enabled the model
        # regularly burned the entire completion budget on reasoning tokens
        # (truncated responses with 0 content chars) for these large
        # structured-JSON outputs. Two parse attempts with a big budget.
        for _attempt in range(2):
            response = await self._call_llm(
                json.dumps(payload, ensure_ascii=False),
                system_prompt=system_prompt,
                use_fast_model=False,
                retry_count=2,
                enable_thinking=False,
                max_tokens=16000,
                raise_on_failure=True,
            )
            parsed = self._extract_json(response or "")
            if isinstance(parsed, dict):
                break
        if not isinstance(parsed, dict):
            raise PracticeAnalysisUnavailable("analysis output is not valid JSON")
        return parsed


def _normalize_answer_diagnosis(
    question: dict[str, Any],
    free: dict[str, Any],
    mapped: dict[str, Any],
) -> dict[str, Any]:
    intent = question.get("assessment_intent") or {}
    allowed = {
        "knowledge_ids": _intent_ids(intent, "target_knowledge"),
        "skill_ids": _intent_ids(intent, "target_skills"),
        "misconception_ids": _intent_ids(intent, "target_misconceptions"),
    }
    mapping = mapped.get("mapping") or {}
    normalized = {
        field: [
            item for item in _clean_ids(mapping.get(field))
            if item in valid_ids
        ]
        for field, valid_ids in allowed.items()
    }
    student_feedback = mapped.get("student_feedback") or {}
    summary = str(student_feedback.get("summary") or free.get("behavior_gap") or "").strip()
    next_action = str(
        student_feedback.get("next_action") or free.get("next_action") or ""
    ).strip()
    if not summary or not next_action:
        return unavailable_answer_diagnosis("diagnosis_output_incomplete")

    issue_mappings = {
        str(item.get("issue_id") or ""): item
        for item in mapped.get("issue_mappings") or []
        if isinstance(item, dict)
    }
    issue_candidates = []
    for index, raw in enumerate(free.get("issues") or []):
        if not isinstance(raw, dict):
            continue
        issue_id = str(raw.get("issue_id") or f"issue-{index + 1}")
        match = issue_mappings.get(issue_id, {})
        issue_candidates.append({
            "issue_id": issue_id,
            "title": str(raw.get("title") or "当前作答差距"),
            "what_happened": str(raw.get("what_happened") or ""),
            "why_it_matters": str(raw.get("why_it_matters") or ""),
            "evidence": _strings(raw.get("evidence")),
            "confidence": _bounded_float(raw.get("confidence")),
            "knowledge_ids": _allowed_ids(
                match.get("knowledge_ids"),
                allowed["knowledge_ids"],
            ),
            "skill_ids": _allowed_ids(
                match.get("skill_ids"),
                allowed["skill_ids"],
            ),
            "misconception_ids": _allowed_ids(
                match.get("misconception_ids"),
                allowed["misconception_ids"],
            ),
        })

    result = {
        "schema_version": ANSWER_DIAGNOSIS_SCHEMA,
        "status": "completed",
        "analysis_source": "ai_independent_then_same_source_mapping",
        "question_understanding": {
            "task_goal": str(free.get("task_goal") or ""),
            "required_actions": _strings(free.get("required_actions")),
            "key_conditions": _strings(free.get("key_conditions")),
        },
        "student_response": {
            "approach": str(free.get("student_approach") or ""),
            "correct_parts": _strings(free.get("correct_parts")),
            "behavior_gap": str(free.get("behavior_gap") or ""),
        },
        "diagnosis": {
            **normalized,
            "library_fit": _library_fit(allowed, normalized),
            "reason": str(mapping.get("reason") or ""),
            "knowledge": _named_matches(
                intent.get("target_knowledge"),
                normalized["knowledge_ids"],
            ),
            "skills": _named_matches(
                intent.get("target_skills"),
                normalized["skill_ids"],
            ),
            "misconceptions": _named_matches(
                intent.get("target_misconceptions"),
                normalized["misconception_ids"],
            ),
            "issues": issue_candidates,
            "uncertainty": str(free.get("uncertainty") or ""),
        },
        "student_feedback": {
            "summary": summary,
            "next_action": next_action,
        },
    }
    result["diagnosis_revision_id"] = stable_hash(result, prefix="adr_")
    return result


def _library_fit(
    expected: dict[str, list[str]],
    actual: dict[str, list[str]],
) -> str:
    expected_nonempty = {
        key: set(values) for key, values in expected.items() if values
    }
    if not expected_nonempty:
        return "MISS"
    matched = {
        key: set(actual.get(key) or []) & values
        for key, values in expected_nonempty.items()
    }
    if all(values and values <= set(actual.get(key) or []) for key, values in expected_nonempty.items()):
        return "HIT"
    if any(values for values in matched.values()):
        return "PARTIAL"
    return "MISS"


def _normalize_quality_issues(value: Any) -> list[dict[str, str]]:
    result = []
    for item in value if isinstance(value, list) else []:
        if not isinstance(item, dict):
            continue
        severity = str(item.get("severity") or "major").lower()
        result.append({
            "gate": str(item.get("gate") or "semantic")[:100],
            "severity": severity if severity in {"critical", "major", "minor"} else "major",
            "message": str(item.get("message") or "题目质量问题")[:1000],
        })
    return result


def _normalize_reference_solution(value: Any) -> dict[str, Any]:
    item = value if isinstance(value, dict) else {}
    return {
        "approach": str(item.get("approach") or ""),
        "key_steps": _strings(item.get("key_steps")),
        "self_check": str(item.get("self_check") or ""),
    }


def _by_revision(
    items: list[dict[str, Any]],
    field: str,
) -> dict[str, dict[str, Any]]:
    return {
        str(item.get(field) or ""): item
        for item in items
        if isinstance(item, dict) and item.get(field)
    }


def _intent_ids(intent: dict[str, Any], field: str) -> list[str]:
    return [
        str(item.get("id") or "")
        for item in intent.get(field) or []
        if isinstance(item, dict) and item.get("id")
    ]


def _ids(item: dict[str, Any], *fields: str) -> list[str]:
    for field in fields:
        values = _clean_ids(item.get(field))
        if values:
            return values
    return []


def _clean_ids(value: Any) -> list[str]:
    return list(dict.fromkeys(
        str(item).strip()
        for item in (value if isinstance(value, list) else [])
        if str(item).strip()
    ))


def _strings(value: Any) -> list[str]:
    return [
        str(item).strip()
        for item in (value if isinstance(value, list) else [])
        if str(item).strip()
    ]


def _allowed_ids(value: Any, allowed: list[str]) -> list[str]:
    allowed_set = set(allowed)
    return [item for item in _clean_ids(value) if item in allowed_set]


def _named_matches(value: Any, ids: list[str]) -> list[dict[str, str]]:
    allowed = set(ids)
    return [
        {"id": str(item.get("id") or ""), "name": str(item.get("name") or "")}
        for item in (value if isinstance(value, list) else [])
        if isinstance(item, dict) and str(item.get("id") or "") in allowed
    ]


def _bounded_float(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


_QUESTION_FREE_SYSTEM_PROMPT = """
你是正式课程的独立题目解析员。你看不到课程知识 ID，也不能相信题目声明自己在考什么。
先只依据题干、题型、答案量规和难度要求，逐题说明它实际上要求学习者完成什么。
只返回严格 JSON：{"analyses":[{"question_revision_id":"原值","task_goal":"一句话",
"required_actions":["可观察动作"],"key_conditions":["条件或边界"],
"answer_invariants":["正确答案必须满足的条件"],"acceptable_variations":["合理变体"],
"likely_wrong_paths":["题目可能暴露的真实错误"]}]}。
不得给学生可直接复制的完整答案，不得创造题目中不存在的条件。
""".strip()


_QUESTION_MAPPING_SYSTEM_PROMPT = """
你是正式课程的题目质量审查员。输入同时包含独立题目解析和课程声明的 assessment_intent。
先比较二者，再把独立解析映射到 assessment_intent 中允许的课程本地 ID。
标准库只负责统一命名和范围，不能覆盖独立解析。只返回严格 JSON：
{"analyses":[{"question_revision_id":"原值","mapping":{"knowledge_ids":[],
"skill_ids":[],"misconception_ids":[],"reason":"为何命中或不命中"},
"quality":{"passed":true,"difficulty_fit":"是否匹配","rubric_fit":"是否匹配",
"ambiguity":"是否歧义","issues":[{"gate":"门名","severity":"critical|major|minor",
"message":"问题"}]},"reference_solution":{"approach":"解题方向","key_steps":["关键步骤"],
"self_check":"结果检查"}}]}。
ID 只能从当前 assessment_intent 选择。若题目只挂了 ID、实际没有测到，必须判为不通过。
隐藏评分要求、缺条件、答案不可判定、能力不可观察、难度虚标都属于质量问题。
""".strip()


_QUESTION_REPAIR_SYSTEM_PROMPT = """
你是正式课程的题目编辑。输入中的题目已经经过独立解析且未通过质量门。
你的任务不是从头重做课程，也不能改变 assessment_intent、题型、难度层级或答案量规；
只重写题干，让任务条件、交付形式、可观察动作和判定边界清楚地呈现在学习者面前。
吸收 question_analysis.quality.issues，但不要把参考答案、评分答案或完整解题步骤泄露给学生。
只返回严格 JSON：
{"repairs":[{"question_revision_id":"原值","prompt":"修正后的完整题干",
"repair_summary":"本次解决了什么问题"}]}。
每一道被阻断的题都必须返回，prompt 必须发生实质变化，不得新增课程范围外的知识要求。
""".strip()


_ANSWER_FREE_SYSTEM_PROMPT = """
你是课程正式练习的独立作答诊断员。只依据题目、题目解析、学生实际答案和已用支持，
先理解学生采取了什么思路，再比较题目要求与作答证据。不要读取或猜测课程知识 ID。
只返回严格 JSON：{"task_goal":"题目实际目标","required_actions":[],
"key_conditions":[],"student_approach":"学生实际思路","correct_parts":[],
"behavior_gap":"最关键差距","issues":[{"issue_id":"I1","title":"问题名",
"what_happened":"发生了什么","why_it_matters":"为什么影响达标",
"evidence":["学生答案中的可见证据"],"confidence":0.0}],
"next_action":"一个立即可做的检查动作","uncertainty":"证据不足之处"}。
不得补写学生没有表达的推理，不得给完整答案或可直接复制的成品。
若 question_type 为 single_choice，选项和 selected_option 是唯一的作答证据：
student_approach 只能描述“学习者选择了哪一种判断”，不得声称其使用了某个计算步骤、
概念或推理方法；无法由选项直接证明的原因必须写入 uncertainty。
""".strip()


_ANSWER_MAPPING_SYSTEM_PROMPT = """
你是课程作答诊断的同源映射员。自由诊断已经完成；assessment_intent 只用于统一命名和范围。
把真实差距映射到允许的课程本地知识、能力和易错 ID，允许命中、部分命中或未命中，
不得为了填 ID 强行套库。只返回严格 JSON：
{"mapping":{"knowledge_ids":[],"skill_ids":[],"misconception_ids":[],"reason":"映射依据"},
"issue_mappings":[{"issue_id":"I1","knowledge_ids":[],"skill_ids":[],
"misconception_ids":[]}],"student_feedback":{"summary":"自然、具体的完整反馈",
"next_action":"学生下一步只做一个动作"}}。
ID 只能来自 assessment_intent。反馈要说清题目要求、学生当前思路和具体差距，但不能泄露完整答案。
""".strip()


practice_analysis_service = PracticeAnalysisService()


__all__ = [
    "ANSWER_DIAGNOSIS_SCHEMA",
    "ASSESSMENT_INTENT_SCHEMA",
    "PracticeAnalysisService",
    "PracticeAnalysisUnavailable",
    "QUESTION_ANALYSIS_SCHEMA",
    "build_assessment_intent",
    "compile_question_analysis_from_contract",
    "normalize_question_analysis",
    "practice_analysis_service",
    "unavailable_answer_diagnosis",
]
