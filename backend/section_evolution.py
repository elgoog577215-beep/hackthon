"""One section-growth chain for learner requests and learning evidence."""

from __future__ import annotations

import re
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from block_regeneration import evaluate_block_candidate
from course_document import CourseBlock, CourseDocument, stable_hash
from course_evolution import (
    AdaptationHypothesis,
    CourseEvolutionOperation,
    CourseEvolutionPlan,
    CourseEvolutionRepository,
    CourseEvolutionState,
)
from course_feedback import default_block_kind_for_role
from course_knowledge_base import (
    compile_course_knowledge_base,
    course_knowledge_base_prompt_context,
    knowledge_binding_for_section,
)
from course_repository import CourseDocumentRepository
from course_revisions import revision_vector_for_document
from learning_events import summarize_text

ROLE_TITLES = {
    "reasoning": "理论推导",
    "application": "实战应用",
    "example": "例子讲解",
    "checkpoint": "理解检查",
    "concept": "核心概念",
}
ROLE_PATTERNS = {
    "reasoning": re.compile(r"理论|推导|原理|证明|机制|为什么"),
    "application": re.compile(r"实战|实践|项目|工程|应用|落地|行业"),
    "example": re.compile(r"例子|举例|示例|案例"),
    "checkpoint": re.compile(r"练习|题目|训练|自测|检查"),
    "concept": re.compile(r"概念|定义|基础解释"),
}
CHALLENGE_PATTERN = re.compile(r"太简单|加强|强化|深入|提高难度|高级|复杂|挑战")
REMEDIATION_PATTERN = re.compile(r"太难|没懂|不理解|讲清楚|简化|基础|补充解释")
CURRENT_SOURCE_PATTERN = re.compile(r"前沿|最新|近期|当下|当前行业|真实行业|行业现状|20\d{2}")
ALLOWED_GROWTH_DIRECTIONS = {"challenge", "remediation", "author_directed"}
ALLOWED_SOURCE_REQUIREMENTS = {
    "course_only",
    "verified_materials",
    "verified_current_sources",
}
DIFFICULTY_KEYS = {
    "reasoning_depth",
    "transfer_distance",
    "task_complexity",
    "learner_support",
}


def analyze_section_request(instruction: str) -> dict[str, Any]:
    """Deterministic fallback when semantic scene analysis is unavailable."""
    text = str(instruction or "").strip()
    roles = [
        role
        for role, pattern in ROLE_PATTERNS.items()
        if pattern.search(text)
    ]
    # “实战案例” is an application request, not a request to duplicate another
    # generic example block.
    if "application" in roles and "案例" in text and "举例" not in text:
        roles = [role for role in roles if role != "example"]
    direction = (
        "challenge"
        if CHALLENGE_PATTERN.search(text)
        else "remediation"
        if REMEDIATION_PATTERN.search(text)
        else "author_directed"
    )
    if not roles:
        roles = ["reasoning", "application"] if direction == "challenge" else ["concept", "example"]
    difficulty_delta = {
        "reasoning_depth": 2 if direction == "challenge" or "reasoning" in roles else 1,
        "transfer_distance": 2 if "application" in roles else 0,
        "task_complexity": 1 if "checkpoint" in roles or direction == "challenge" else 0,
        "learner_support": -1 if direction == "challenge" else 1 if direction == "remediation" else 0,
    }
    normalized_roles = list(dict.fromkeys(roles))
    source_requirement = (
        "verified_current_sources"
        if CURRENT_SOURCE_PATTERN.search(text)
        else "course_only"
    )
    return {
        "instruction": text or "调整本小节，使内容更完整、更适合当前学习需要。",
        "roles": normalized_roles,
        "growth_direction": direction,
        "difficulty_delta": difficulty_delta,
        "schema_version": "section_growth_scene_v1",
        "analysis_source": "deterministic_fallback",
        "scene_summary": _fallback_scene_summary(direction, normalized_roles),
        "rationale": "根据用户明确提到的教学作用、难度和理解信号进行规则判断。",
        "source_requirement": source_requirement,
        "source_reason": (
            "用户要求涉及最新、前沿或当前行业事实，需要另行提供并核验可信资料。"
            if source_requirement == "verified_current_sources"
            else "本次调整可在当前课程知识契约内完成。"
        ),
        "confidence": "fallback",
        "fallback_reason": "",
    }


def _normalize_scene_analysis(
    candidate: Any,
    fallback: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(candidate, dict):
        return {**fallback, "fallback_reason": "analyzer_returned_invalid_payload"}

    raw_roles = candidate.get("requested_roles")
    roles = [
        str(role)
        for role in raw_roles
        if str(role) in ROLE_TITLES
    ] if isinstance(raw_roles, list) else []
    roles = list(dict.fromkeys(roles))
    direction = str(candidate.get("growth_direction") or "")
    source_requirement = str(candidate.get("source_requirement") or "")
    raw_delta = candidate.get("difficulty_delta")
    difficulty_delta: dict[str, int] = {}
    invalid_fields: list[str] = []
    if isinstance(raw_delta, dict):
        for key in DIFFICULTY_KEYS:
            value = raw_delta.get(key)
            if isinstance(value, bool):
                invalid_fields.append(key)
                continue
            try:
                difficulty_delta[key] = max(-2, min(2, int(value)))
            except (TypeError, ValueError):
                invalid_fields.append(key)

    required_fields_valid = (
        bool(roles)
        and direction in ALLOWED_GROWTH_DIRECTIONS
        and source_requirement in ALLOWED_SOURCE_REQUIREMENTS
        and set(difficulty_delta) == DIFFICULTY_KEYS
    )
    if not required_fields_valid:
        return {
            **fallback,
            "fallback_reason": "analyzer_output_failed_contract",
            "invalid_fields": invalid_fields,
        }

    return {
        **fallback,
        "analysis_source": "ai_semantic",
        "scene_summary": _clip_scene_text(
            candidate.get("scene_summary"),
            fallback["scene_summary"],
        ),
        "rationale": _clip_scene_text(
            candidate.get("rationale"),
            fallback["rationale"],
        ),
        "roles": roles,
        "growth_direction": direction,
        "difficulty_delta": difficulty_delta,
        "source_requirement": source_requirement,
        "source_reason": _clip_scene_text(
            candidate.get("source_reason"),
            fallback["source_reason"],
        ),
        "confidence": "semantic",
        "fallback_reason": "",
    }


async def _resolve_scene_analysis(
    generator: Any,
    *,
    fallback: dict[str, Any],
    course_id: str,
    document_title: str,
    section: dict[str, Any],
    active_blocks: list[dict[str, Any]],
    instruction: str,
    knowledge_context: str,
    evidence_context: list[dict[str, Any]],
    available_sources: list[dict[str, Any]],
    user_id: str,
) -> dict[str, Any]:
    analyzer = getattr(generator, "analyze_section_growth_scenario", None)
    if not callable(analyzer):
        return {**fallback, "fallback_reason": "analyzer_unavailable"}
    try:
        candidate = await analyzer(
            course_id=course_id,
            document_title=document_title,
            section=section,
            active_blocks=active_blocks,
            instruction=instruction,
            knowledge_context=knowledge_context,
            evidence_context=evidence_context,
            available_sources=available_sources,
            user_id=user_id,
        )
    except Exception:
        return {**fallback, "fallback_reason": "analyzer_failed"}
    return _normalize_scene_analysis(candidate, fallback)


async def generate_section_evolution_plan(
    course_data: dict[str, Any],
    *,
    user_id: str,
    section_id: str,
    instruction: str,
    request_id: str,
    repository: CourseEvolutionRepository,
    document_repository: CourseDocumentRepository,
    generator: Any | None = None,
    existing_change_set_id: str = "",
) -> CourseEvolutionState:
    """Generate and checkpoint a reviewable section change without mutating the course."""
    course_id = str(course_data.get("course_id") or "")
    document, canonical = document_repository.load_document(course_id)
    if not canonical:
        raise ValueError("Course must be migrated before section growth can be generated")
    section = next((item for item in document.sections if item.section_id == section_id), None)
    if section is None:
        raise ValueError("Course section not found")
    active_blocks = sorted(
        (
            block for block in document.blocks
            if block.section_id == section_id and block.status != "retired"
        ),
        key=lambda item: (item.position, item.block_id),
    )
    if not active_blocks:
        raise ValueError("Course section has no content anchor")

    knowledge_base = compile_course_knowledge_base(deepcopy(course_data))
    binding = knowledge_binding_for_section(knowledge_base, section_id)
    knowledge_refs = list(binding["course_knowledge_refs"])
    if not knowledge_refs:
        raise ValueError("当前小节还没有课程知识契约，不能生成无法追溯来源的课程内容")
    knowledge_context = course_knowledge_base_prompt_context(knowledge_base, section_id)
    state = repository.load(user_id, course_id)
    now = _now()

    if generator is None:
        from course_service import get_course_service

        generator = get_course_service()

    plan: CourseEvolutionPlan | None = None
    effective_instruction = instruction
    if existing_change_set_id:
        plan = next(
            (item for item in state.change_sets if item.change_set_id == existing_change_set_id),
            None,
        )
        if plan is None:
            raise KeyError(existing_change_set_id)
        if plan.status != "pending" or plan.generation_status not in {"suggested", "failed"}:
            raise ValueError("Course section plan cannot be generated from its current status")
        effective_instruction = plan.request_text or instruction

    fallback = analyze_section_request(effective_instruction)
    evidence_context = [
        {
            "evidence_kind": item.evidence_kind,
            "summary": item.summary,
            "strength": item.strength,
        }
        for item in state.evidence_items
        if item.anchor.section_id == section_id
    ][:12]
    available_sources = [
        {
            "evidence_id": str(item.get("evidence_id") or ""),
            "kind": str(item.get("kind") or ""),
            "summary": str(item.get("summary") or ""),
            "authority": str(item.get("authority") or ""),
            "confidence": str(item.get("confidence") or ""),
        }
        for item in (
            course_data.get("evidence_catalog")
            or course_data.get("evidence_index")
            or []
        )
        if isinstance(item, dict) and item.get("factual_allowed", True)
    ][:24]
    analysis = await _resolve_scene_analysis(
        generator,
        fallback=fallback,
        course_id=course_id,
        document_title=document.title,
        section=section.model_dump(mode="json"),
        active_blocks=[
            {
                "role": block.role,
                "kind": block.kind,
                "title": str(block.payload.get("title") or ""),
                "summary": str(
                    block.payload.get("summary")
                    or summarize_text(str(block.payload.get("markdown") or ""))
                ),
            }
            for block in active_blocks
        ],
        instruction=fallback["instruction"],
        knowledge_context=knowledge_context,
        evidence_context=evidence_context,
        available_sources=available_sources,
        user_id=user_id,
    )
    analysis["source_status"] = _source_status(
        analysis["source_requirement"],
        available_sources,
    )
    analysis["available_source_count"] = len(available_sources)

    if plan is not None:
        plan.request_text = analysis["instruction"]
        plan.requested_roles = analysis["roles"]
        plan.growth_direction = analysis["growth_direction"]
        plan.expected_effect = _expected_effect(analysis["growth_direction"])
        plan.operations = []
    else:
        change_set_id = stable_hash(
            {
                "course_id": course_id,
                "user_id": user_id,
                "section_id": section_id,
                "request_id": request_id,
            },
            prefix="ces_",
        )
        existing = next(
            (item for item in state.change_sets if item.change_set_id == change_set_id),
            None,
        )
        if existing is not None:
            return state
        target = active_blocks[0]
        hypothesis_id = stable_hash(
            {
                "course_id": course_id,
                "user_id": user_id,
                "section_id": section_id,
                "request_id": request_id,
                "kind": "manual_section_growth",
            },
            prefix="ahp_",
        )
        hypothesis = AdaptationHypothesis(
            hypothesis_id=hypothesis_id,
            user_id=user_id,
            course_id=course_id,
            problem_type="section_growth_request",
            claim=f"学习者希望调整“{section.title}”：{analysis['instruction']}",
            target_block_id=target.block_id,
            confidence=1.0,
            confidence_reasons=["用户明确提出本小节调整要求"],
            evidence_assessment={
                "actionable": True,
                "maturity": "explicit_section_request",
                "gate_reason": "用户主动发起，仅在当前小节生成候选并等待确认",
            },
            recommended_scope="current",
            affected_block_ids=[block.block_id for block in active_blocks],
            temporary_support="正式课程在确认前保持不变。",
            validation_plan="应用后使用同知识点、更高要求的独立任务验证效果。",
            status="candidate_created",
            created_at=now,
            updated_at=now,
        )
        state.hypotheses.append(hypothesis)
        plan = CourseEvolutionPlan(
            change_set_id=change_set_id,
            user_id=user_id,
            course_id=course_id,
            hypothesis_id=hypothesis_id,
            source_kind="manual_section_request",
            target_section_id=section_id,
            request_text=analysis["instruction"],
            growth_direction=analysis["growth_direction"],
            generation_status="generating",
            requested_roles=analysis["roles"],
            base_revision_vector=_section_revision_vector(document, section_id),
            allowed_scopes=["current"],
            impact_summary={},
            expected_effect=_expected_effect(analysis["growth_direction"]),
            created_at=now,
            updated_at=now,
        )
        state.change_sets.append(plan)

    assert plan is not None
    plan.generation_status = "generating"
    plan.updated_at = now
    plan.base_revision_vector = _section_revision_vector(document, section_id)
    plan.impact_summary = {
        **deepcopy(plan.impact_summary),
        "diagnosis": _plan_diagnosis(section.title, analysis),
        "affected_section_ids": [section_id],
        "direct_block_ids": [block.block_id for block in active_blocks],
        "dependent_block_ids": [],
        "protected": [
            "当前小节中未被点名的教学块",
            "范围外课程内容",
            "其他课程",
            "历史作答与掌握记录",
            "笔记原文",
            "课程知识定义",
        ],
        "difficulty_delta": analysis["difficulty_delta"],
        "scene_analysis": {
            key: deepcopy(value)
            for key, value in analysis.items()
            if key != "instruction"
        },
        "knowledge_node_ids": knowledge_refs,
        "ability_point_ids": list(binding["course_skill_refs"]),
        "misconception_point_ids": list(binding["course_misconception_refs"]),
        "mastery_criterion_ids": list(binding["course_mastery_refs"]),
        "validation_plan": (
            "保留旧难度的已掌握记录；应用后生成同知识点、更高认知要求的独立任务，"
            "验证理论解释和跨情境应用是否真正提升。"
        ),
        "mastery_transition": {
            "previous_status": "mastered_at_base_difficulty"
            if plan.growth_direction == "challenge"
            else "preserved",
            "current_status": "awaiting_higher_challenge"
            if plan.growth_direction == "challenge"
            else "awaiting_validation",
        },
    }
    difficulty_operation = CourseEvolutionOperation(
        operation_id=stable_hash(
            {"change_set_id": plan.change_set_id, "kind": "difficulty"},
            prefix="ceo_",
        ),
        operation_type="ADJUST_COURSE_DIFFICULTY",
        target_block_id=active_blocks[0].block_id,
        target_section_id=section_id,
        reason="把本次内容变化与难度变化放在同一个方案中记录和复验。",
        payload={
            "action": "ADJUST",
            "candidate_status": "ready",
            "difficulty_delta": analysis["difficulty_delta"],
        },
    )
    plan.operations = [difficulty_operation]
    repository.save(state)

    try:
        generated_contents: list[str] = []
        for role in plan.requested_roles:
            target = next((block for block in active_blocks if block.role == role), None)
            if target is not None:
                operation = _replacement_placeholder(plan, target, role)
            else:
                anchor = _insertion_anchor(active_blocks, role)
                operation = _insertion_placeholder(plan, section_id, anchor, role)
            plan.operations.append(operation)
            repository.save(state)

            previous_block, next_block = _neighbors(active_blocks, target or _block_for_anchor(active_blocks, operation))
            feedback: list[str] = []
            quality_report: dict[str, Any] = {}
            proposed: CourseBlock | None = None
            for attempt in range(2):
                if target is not None:
                    content = await generator.generate_course_block_candidate(
                        course_id=course_id,
                        document_title=document.title,
                        section=section.model_dump(mode="json"),
                        target_block=target.model_dump(mode="json"),
                        previous_block=previous_block,
                        next_block=next_block,
                        instruction=analysis["instruction"],
                        action_type="expand" if plan.growth_direction == "challenge" else "rewrite",
                        scene_analysis=analysis,
                        quality_feedback=feedback,
                        user_id=user_id,
                    )
                    proposed = target.model_copy(deep=True)
                    original_payload = deepcopy(target.payload)
                else:
                    content = await generator.generate_new_course_block_candidate(
                        course_id=course_id,
                        document_title=document.title,
                        section=section.model_dump(mode="json"),
                        desired_role=role,
                        instruction=analysis["instruction"],
                        previous_block=previous_block,
                        next_block=next_block,
                        knowledge_context=knowledge_context,
                        difficulty_delta=analysis["difficulty_delta"],
                        scene_analysis=analysis,
                        quality_feedback=feedback,
                        user_id=user_id,
                    )
                    proposed = CourseBlock(
                        block_id=stable_hash(
                            {
                                "course_id": course_id,
                                "change_set_id": plan.change_set_id,
                                "role": role,
                            },
                            prefix="ceb_",
                        ),
                        section_id=section_id,
                        position=(target.position + 1) if target else len(active_blocks),
                        kind=default_block_kind_for_role(role),
                        role=role,
                        payload={"title": ROLE_TITLES.get(role, "新增教学块"), "markdown": ""},
                        objective_refs=[section.objective_id] if section.objective_id else [],
                        concept_refs=knowledge_refs,
                        evidence_refs=list(plan.evidence_ids),
                        status="final",
                    )
                    original_payload = deepcopy(proposed.payload)
                content = str(content or "").strip()
                proposed.payload["markdown"] = content
                proposed.payload["summary"] = summarize_text(content)
                proposed.concept_refs = knowledge_refs
                proposed.evidence_refs = list(dict.fromkeys([
                    *proposed.evidence_refs,
                    *plan.evidence_ids,
                ]))
                quality_report = evaluate_block_candidate(
                    original_content=str(
                        (target.payload if target else {}).get("markdown")
                        or (target.payload if target else {}).get("text")
                        or ""
                    ),
                    candidate_content=content,
                    original_payload=original_payload,
                    proposed_payload=proposed.payload,
                )
                quality_report = _extend_candidate_quality(
                    quality_report,
                    proposed=proposed,
                    role=role,
                    section_id=section_id,
                    knowledge_refs=knowledge_refs,
                    generated_contents=generated_contents,
                )
                operation.payload.update({
                    "proposed_block": proposed.model_dump(mode="json"),
                    "quality_report": quality_report,
                    "candidate_status": "ready" if quality_report["passed"] else "quality_failed",
                    "attempt": attempt + 1,
                    "after_preview": content[:600],
                })
                plan.updated_at = _now()
                repository.save(state)
                if quality_report["passed"]:
                    break
                feedback = list(quality_report["issues"])
            if not proposed or not quality_report.get("passed"):
                raise ValueError(f"{ROLE_TITLES.get(role, role)}候选未通过质量检查")
            generated_contents.append(_normalize(str(proposed.payload.get("markdown") or "")))

        plan_quality = _plan_quality(plan, section_id=section_id, knowledge_refs=knowledge_refs)
        plan.impact_summary["quality_report"] = plan_quality
        plan.impact_summary["operation_summary"] = [
            {
                "action": str(operation.payload.get("action") or "ADJUST"),
                "role": str(operation.payload.get("desired_role") or ""),
                "block_id": operation.target_block_id,
                "candidate_status": str(operation.payload.get("candidate_status") or ""),
            }
            for operation in plan.operations
        ]
        plan.generation_status = "ready" if plan_quality["passed"] else "failed"
        if not plan_quality["passed"]:
            raise ValueError("本节方案未通过结构化同源检查")
    except Exception as exc:
        plan.generation_status = "failed"
        plan.impact_summary["generation_error"] = str(exc)
        plan.updated_at = _now()
        repository.save(state)
        raise

    plan.updated_at = _now()
    return repository.save(state)


def ensure_challenge_suggestions(
    state: CourseEvolutionState,
    document: CourseDocument,
) -> None:
    """Treat repeated success as readiness for growth without creating a deficit."""
    by_section: dict[str, list[Any]] = {}
    for evidence in state.evidence_items:
        if evidence.evidence_kind != "formal_success" or not evidence.anchor.section_id:
            continue
        by_section.setdefault(evidence.anchor.section_id, []).append(evidence)
    for section_id, evidence in by_section.items():
        unique_attempts = {
            item.source_id for item in evidence if item.source_id
        }
        if len(unique_attempts) < 2:
            continue
        evidence_ids = sorted(item.evidence_id for item in evidence)
        signature = stable_hash(evidence_ids, prefix="esg_")
        if any(
            plan.source_kind == "learning_evidence"
            and plan.growth_direction == "challenge"
            and plan.target_section_id == section_id
            and plan.evidence_ids == evidence_ids
            and plan.status in {"pending", "applied"}
            for plan in state.change_sets
        ):
            continue
        section_blocks = sorted(
            (
                block for block in document.blocks
                if block.section_id == section_id and block.status != "retired"
            ),
            key=lambda item: (item.position, item.block_id),
        )
        if not section_blocks:
            continue
        target = section_blocks[0]
        hypothesis_id = stable_hash(
            {
                "user_id": state.user_id,
                "course_id": state.course_id,
                "section_id": section_id,
                "problem_type": "challenge_readiness",
            },
            prefix="ahp_",
        )
        now = _now()
        hypothesis = next(
            (item for item in state.hypotheses if item.hypothesis_id == hypothesis_id),
            None,
        )
        if hypothesis is None:
            hypothesis = AdaptationHypothesis(
                hypothesis_id=hypothesis_id,
                user_id=state.user_id,
                course_id=state.course_id,
                problem_type="challenge_readiness",
                claim="当前小节的正式任务已稳定通过，可以提升理论深度和迁移距离。",
                target_block_id=target.block_id,
                created_at=now,
                updated_at=now,
            )
            state.hypotheses.append(hypothesis)
        hypothesis.support_evidence_ids = evidence_ids
        hypothesis.counterevidence_ids = []
        hypothesis.confidence = min(0.98, 0.72 + 0.08 * len(unique_attempts))
        hypothesis.confidence_reasons = ["同一小节出现多次独立正式通过"]
        hypothesis.evidence_assessment = {
            "evidence_count": len(evidence),
            "independent_source_count": 1,
            "formal_success_count": len(unique_attempts),
            "has_formal_evidence": True,
            "counterevidence_count": 0,
            "actionable": True,
            "maturity": "challenge_ready",
            "gate_reason": "旧难度已稳定通过，建议进入更高挑战；这不是知识缺口判断",
        }
        hypothesis.recommended_scope = "current"
        hypothesis.affected_block_ids = [block.block_id for block in section_blocks]
        hypothesis.validation_plan = "用同知识点、更高认知要求的独立任务验证挑战升级。"
        hypothesis.status = "candidate_created"
        hypothesis.updated_at = now
        state.change_sets.append(CourseEvolutionPlan(
            change_set_id=stable_hash(
                {
                    "user_id": state.user_id,
                    "course_id": state.course_id,
                    "section_id": section_id,
                    "evidence_signature": signature,
                    "kind": "challenge_growth",
                },
                prefix="ces_",
            ),
            user_id=state.user_id,
            course_id=state.course_id,
            hypothesis_id=hypothesis_id,
            source_kind="learning_evidence",
            target_section_id=section_id,
            request_text="当前正式任务持续通过，请强化理论推导与实战应用。",
            growth_direction="challenge",
            generation_status="suggested",
            requested_roles=["reasoning", "application"],
            base_revision_vector=_section_revision_vector(document, section_id),
            evidence_ids=evidence_ids,
            allowed_scopes=["current"],
            impact_summary={
                "diagnosis": hypothesis.claim,
                "evidence_assessment": deepcopy(hypothesis.evidence_assessment),
                "affected_section_ids": [section_id],
                "direct_block_ids": [block.block_id for block in section_blocks],
                "protected": ["旧难度掌握记录", "历史作答", "范围外课程内容", "课程知识定义"],
                "mastery_transition": {
                    "previous_status": "mastered_at_base_difficulty",
                    "current_status": "ready_for_higher_challenge",
                },
                "validation_plan": hypothesis.validation_plan,
            },
            expected_effect="在保留原有掌握事实的前提下，提高理论解释和跨情境应用能力。",
            created_at=now,
            updated_at=now,
        ))


def _replacement_placeholder(
    plan: CourseEvolutionPlan,
    target: CourseBlock,
    role: str,
) -> CourseEvolutionOperation:
    return CourseEvolutionOperation(
        operation_id=stable_hash(
            {"change_set_id": plan.change_set_id, "role": role, "action": "replace"},
            prefix="ceo_",
        ),
        operation_type="REPLACE_COURSE_BLOCK",
        target_block_id=target.block_id,
        target_section_id=target.section_id,
        reason=f"本节已有“{ROLE_TITLES.get(role, role)}”，保留块身份并升级块内内容。",
        payload={
            "action": "REPLACE",
            "desired_role": role,
            "candidate_status": "generating",
            "expected_block_revision": target.internal_revision,
            "before_block": target.model_dump(mode="json"),
            "before_preview": str(target.payload.get("markdown") or target.payload.get("text") or "")[:600],
        },
    )


def _insertion_placeholder(
    plan: CourseEvolutionPlan,
    section_id: str,
    anchor: CourseBlock,
    role: str,
) -> CourseEvolutionOperation:
    return CourseEvolutionOperation(
        operation_id=stable_hash(
            {"change_set_id": plan.change_set_id, "role": role, "action": "insert"},
            prefix="ceo_",
        ),
        operation_type="INSERT_COURSE_BLOCK",
        target_block_id=anchor.block_id,
        target_section_id=section_id,
        reason=f"本节缺少“{ROLE_TITLES.get(role, role)}”，在现有结构中新增对应教学块。",
        payload={
            "action": "INSERT",
            "desired_role": role,
            "candidate_status": "generating",
            "after_block_id": anchor.block_id,
            "before_block": None,
            "before_preview": "",
        },
    )


def _extend_candidate_quality(
    report: dict[str, Any],
    *,
    proposed: CourseBlock,
    role: str,
    section_id: str,
    knowledge_refs: list[str],
    generated_contents: list[str],
) -> dict[str, Any]:
    gates = list(report.get("gates") or [])
    candidate = _normalize(str(proposed.payload.get("markdown") or ""))
    extra = [
        _gate("role_contract", proposed.role == role, "候选没有满足目标教学作用"),
        _gate("section_boundary", proposed.section_id == section_id, "候选跨出了当前小节"),
        _gate(
            "same_source_binding",
            bool(proposed.concept_refs)
            and not (set(proposed.concept_refs) - set(knowledge_refs)),
            "候选没有绑定本节课程知识来源",
        ),
        _gate(
            "not_duplicate",
            bool(candidate) and candidate not in generated_contents,
            "候选与本方案其他教学块重复",
        ),
    ]
    gates.extend(extra)
    issues = [str(item["message"]) for item in gates if not item.get("passed")]
    return {
        "passed": not issues,
        "status": "passed" if not issues else "failed",
        "gates": gates,
        "issues": issues,
    }


def _plan_quality(
    plan: CourseEvolutionPlan,
    *,
    section_id: str,
    knowledge_refs: list[str],
) -> dict[str, Any]:
    content_operations = [
        item for item in plan.operations
        if item.operation_type in {"REPLACE_COURSE_BLOCK", "INSERT_COURSE_BLOCK"}
    ]
    realized_roles = {
        str(item.payload.get("desired_role") or "")
        for item in content_operations
        if item.payload.get("candidate_status") == "ready"
    }
    proposed_blocks = [
        item.payload.get("proposed_block")
        for item in content_operations
        if isinstance(item.payload.get("proposed_block"), dict)
    ]
    gates = [
        _gate(
            "requested_roles_realized",
            set(plan.requested_roles) <= realized_roles,
            "并非所有用户要求的教学作用都已形成候选",
        ),
        _gate(
            "all_candidates_ready",
            bool(content_operations)
            and all(item.payload.get("candidate_status") == "ready" for item in content_operations),
            "仍有教学块候选未通过质量检查",
        ),
        _gate(
            "single_section",
            all(str(item.get("section_id") or "") == section_id for item in proposed_blocks),
            "方案中的候选没有保持在同一小节",
        ),
        _gate(
            "same_source",
            bool(knowledge_refs)
            and all(
                bool(item.get("concept_refs"))
                and not (set(item.get("concept_refs") or []) - set(knowledge_refs))
                for item in proposed_blocks
            ),
            "方案中的教学块没有全部绑定本节课程知识来源",
        ),
    ]
    issues = [str(item["message"]) for item in gates if not item.get("passed")]
    return {
        "passed": not issues,
        "status": "passed" if not issues else "failed",
        "gates": gates,
        "issues": issues,
    }


def _section_revision_vector(document: CourseDocument, section_id: str) -> dict[str, str]:
    vector = revision_vector_for_document(document).revisions
    allowed = {f"section:{section_id}"}
    allowed.update(
        f"block:{block.block_id}"
        for block in document.blocks
        if block.section_id == section_id and block.status != "retired"
    )
    return {key: value for key, value in vector.items() if key in allowed}


def _insertion_anchor(blocks: list[CourseBlock], role: str) -> CourseBlock:
    if role == "application":
        for preferred in ("reasoning", "example", "concept"):
            candidates = [block for block in blocks if block.role == preferred]
            if candidates:
                return candidates[-1]
    if role == "checkpoint":
        return blocks[-1]
    return blocks[-1]


def _block_for_anchor(
    blocks: list[CourseBlock],
    operation: CourseEvolutionOperation,
) -> CourseBlock:
    return next(
        (block for block in blocks if block.block_id == operation.target_block_id),
        blocks[-1],
    )


def _neighbors(
    blocks: list[CourseBlock],
    target: CourseBlock,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    index = next(
        (idx for idx, block in enumerate(blocks) if block.block_id == target.block_id),
        len(blocks) - 1,
    )

    def compact(block: CourseBlock) -> dict[str, Any]:
        return {
            "block_id": block.block_id,
            "title": str(block.payload.get("title") or ""),
            "role": block.role,
            "content_summary": str(
                block.payload.get("summary")
                or summarize_text(str(block.payload.get("markdown") or ""))
            ),
        }

    previous = compact(blocks[index - 1]) if index > 0 else None
    next_block = compact(blocks[index + 1]) if index + 1 < len(blocks) else None
    return previous, next_block


def _plan_diagnosis(section_title: str, analysis: dict[str, Any]) -> str:
    labels = "、".join(ROLE_TITLES.get(role, role) for role in analysis["roles"])
    action = "提高挑战" if analysis["growth_direction"] == "challenge" else "按要求调整"
    return f"本次只在“{section_title}”中{action}：{labels}；其余内容保持不变。"


def _fallback_scene_summary(direction: str, roles: list[str]) -> str:
    labels = "、".join(ROLE_TITLES.get(role, role) for role in roles)
    if direction == "challenge":
        return f"学习者希望保留当前知识范围，同时提高{labels}的深度和迁移要求。"
    if direction == "remediation":
        return f"学习者当前存在理解阻力，需要通过{labels}降低断点。"
    return f"学习者明确希望调整本节的{labels}。"


def _clip_scene_text(value: Any, fallback: str, limit: int = 240) -> str:
    text = " ".join(str(value or "").split()).strip()
    return text[:limit] if text else fallback


def _source_status(
    source_requirement: str,
    available_sources: list[dict[str, Any]],
) -> str:
    if source_requirement == "course_only":
        return "course_grounded"
    if source_requirement == "verified_materials" and available_sources:
        return "available_materials"
    # “Current/frontier” needs an explicit recency verification contract. A
    # generic bound material is not silently upgraded into current evidence.
    return "verification_required"


def _expected_effect(direction: str) -> str:
    if direction == "challenge":
        return "保留原有掌握事实，同时提高理论解释深度和跨情境实战迁移。"
    if direction == "remediation":
        return "在不改变本节知识来源的前提下，降低理解断点并通过独立任务复验。"
    return "让本节内容更符合用户明确要求，并保持课程结构、知识来源和验证链一致。"


def _gate(key: str, passed: bool, message: str) -> dict[str, Any]:
    return {
        "key": key,
        "passed": bool(passed),
        "severity": "critical",
        "message": message,
    }


def _normalize(value: str) -> str:
    return " ".join(str(value or "").split()).strip().lower()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "analyze_section_request",
    "ensure_challenge_suggestions",
    "generate_section_evolution_plan",
]
