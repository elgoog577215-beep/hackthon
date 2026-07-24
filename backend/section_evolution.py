"""One section-growth chain for learner requests and learning evidence."""

from __future__ import annotations

import asyncio
import re
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Literal

from block_regeneration import (
    BlockRegenerationCandidateRepository,
    BlockRegenerationService,
    block_regeneration_candidate_repository,
    evaluate_block_candidate,
)
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
COURSE_ADJUSTMENT_DIRECTIONS = {"simplify", "expand", "custom"}


def _explicit_roles(instruction: str) -> list[str]:
    text = str(instruction or "").strip()
    roles = [
        role
        for role, pattern in ROLE_PATTERNS.items()
        if pattern.search(text)
    ]
    if "application" in roles and "案例" in text and "举例" not in text:
        roles = [role for role in roles if role != "example"]
    return list(dict.fromkeys(roles))


def _difficulty_delta(direction: str, roles: list[str]) -> dict[str, int]:
    return {
        "reasoning_depth": 2 if direction == "challenge" or "reasoning" in roles else 1,
        "transfer_distance": 2 if "application" in roles else 0,
        "task_complexity": 1 if "checkpoint" in roles or direction == "challenge" else 0,
        "learner_support": -1 if direction == "challenge" else 1 if direction == "remediation" else 0,
    }


def analyze_section_request(instruction: str) -> dict[str, Any]:
    """Deterministic fallback when semantic scene analysis is unavailable."""
    text = str(instruction or "").strip()
    roles = _explicit_roles(text)
    direction = (
        "challenge"
        if CHALLENGE_PATTERN.search(text)
        else "remediation"
        if REMEDIATION_PATTERN.search(text)
        else "author_directed"
    )
    if not roles:
        roles = ["reasoning", "application"] if direction == "challenge" else ["concept", "example"]
    normalized_roles = list(dict.fromkeys(roles))
    difficulty_delta = _difficulty_delta(direction, normalized_roles)
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


async def generate_course_adjustment_plan(
    course_data: dict[str, Any],
    *,
    user_id: str,
    section_id: str,
    instruction: str,
    request_id: str,
    scope_selection: Literal[
        "current_block",
        "current_section",
        "whole_course",
    ] = "current_section",
    block_id: str = "",
    expected_document_revision: str = "",
    expected_block_revision: str = "",
    direction: Literal["simplify", "expand", "custom"] = "custom",
    anchor_role: str | None = None,
    repository: CourseEvolutionRepository,
    document_repository: CourseDocumentRepository,
    candidate_repository: BlockRegenerationCandidateRepository | None = None,
    generator: Any | None = None,
    existing_change_set_id: str = "",
) -> CourseEvolutionState:
    """Create every learner-requested course adjustment in one plan model."""
    if scope_selection == "current_block":
        if existing_change_set_id:
            raise ValueError("A current-content adjustment must be regenerated as a new request")
        return await generate_block_evolution_plan(
            course_data,
            user_id=user_id,
            section_id=section_id,
            block_id=block_id,
            instruction=instruction,
            request_id=request_id,
            expected_document_revision=expected_document_revision,
            expected_block_revision=expected_block_revision,
            direction=direction,
            repository=repository,
            document_repository=document_repository,
            candidate_repository=candidate_repository,
            generator=generator,
        )
    return await generate_section_evolution_plan(
        course_data,
        user_id=user_id,
        section_id=section_id,
        instruction=instruction,
        request_id=request_id,
        scope_selection=scope_selection,
        anchor_role=anchor_role,
        repository=repository,
        document_repository=document_repository,
        generator=generator,
        existing_change_set_id=existing_change_set_id,
    )


async def generate_block_evolution_plan(
    course_data: dict[str, Any],
    *,
    user_id: str,
    section_id: str,
    block_id: str,
    instruction: str,
    request_id: str,
    expected_document_revision: str,
    expected_block_revision: str,
    direction: Literal["simplify", "expand", "custom"],
    repository: CourseEvolutionRepository,
    document_repository: CourseDocumentRepository,
    candidate_repository: BlockRegenerationCandidateRepository | None = None,
    generator: Any | None = None,
) -> CourseEvolutionState:
    """Wrap the mature block generator in the canonical course-plan workflow."""
    if direction not in COURSE_ADJUSTMENT_DIRECTIONS:
        raise ValueError("Unsupported course adjustment direction")
    if not block_id or not expected_document_revision or not expected_block_revision:
        raise ValueError("Current-content adjustment requires its block and revision")
    course_id = str(course_data.get("course_id") or "")
    document, canonical = document_repository.load_document(course_id)
    if not canonical:
        raise ValueError("Course must be migrated before course adjustment can be generated")
    if document.document_revision != expected_document_revision:
        raise ValueError("Course changed before this adjustment could be generated")
    target = next(
        (
            block for block in document.blocks
            if block.block_id == block_id and block.status != "retired"
        ),
        None,
    )
    if target is None:
        raise ValueError("Course content was not found")
    if target.section_id != section_id:
        raise ValueError("Current-content adjustment crossed its section boundary")
    if target.internal_revision != expected_block_revision:
        raise ValueError("Course content changed before this adjustment could be generated")
    section = next(
        (item for item in document.sections if item.section_id == section_id),
        None,
    )
    if section is None:
        raise ValueError("Course section not found")

    request_text = instruction.strip()
    if not request_text:
        raise ValueError("Describe how the course should be adjusted")
    change_set_id = stable_hash(
        {
            "course_id": course_id,
            "user_id": user_id,
            "request_id": request_id,
            "scope_selection": "current_block",
        },
        prefix="ces_",
    )
    request_fingerprint = stable_hash(
        {
            "course_id": course_id,
            "user_id": user_id,
            "section_id": section_id,
            "block_id": block_id,
            "expected_document_revision": expected_document_revision,
            "expected_block_revision": expected_block_revision,
            "direction": direction,
            "instruction": request_text,
        },
        prefix="caf_",
    )
    hypothesis_id = stable_hash(
        {
            "change_set_id": change_set_id,
            "kind": "manual_course_adjustment",
        },
        prefix="ahp_",
    )
    now = _now()
    created = False

    def claim(current: CourseEvolutionState) -> CourseEvolutionState:
        nonlocal created
        existing = next(
            (
                item for item in current.change_sets
                if item.change_set_id == change_set_id
            ),
            None,
        )
        if existing is not None:
            existing_fingerprint = str(
                existing.impact_summary.get("request_fingerprint") or ""
            )
            if existing_fingerprint != request_fingerprint:
                raise ValueError("Course adjustment request was reused with different inputs")
            return current
        hypothesis = AdaptationHypothesis(
            hypothesis_id=hypothesis_id,
            user_id=user_id,
            course_id=course_id,
            problem_type="manual_course_adjustment",
            claim=f"学习者希望调整当前内容：{request_text}",
            target_block_id=block_id,
            confidence=1.0,
            confidence_reasons=["用户主动指定当前内容和调整要求"],
            evidence_assessment={
                "actionable": True,
                "maturity": "explicit_scoped_request",
                "explicit_scope": "current",
                "gate_reason": "用户明确选择当前内容；生成候选后仍需用户确认。",
            },
            recommended_scope="current",
            affected_block_ids=[block_id],
            temporary_support="正式课程在确认前保持不变。",
            validation_plan="应用后使用同知识点的新任务或后续反馈验证调整效果。",
            status="candidate_created",
            created_at=now,
            updated_at=now,
        )
        plan = CourseEvolutionPlan(
            change_set_id=change_set_id,
            user_id=user_id,
            course_id=course_id,
            hypothesis_id=hypothesis_id,
            source_kind="manual_request",
            target_section_id=section_id,
            request_text=request_text,
            growth_direction=(
                "remediation"
                if direction == "simplify"
                else "challenge"
                if direction == "expand"
                else "author_directed"
            ),
            generation_status="generating",
            requested_roles=[target.role] if target.role else [],
            base_revision_vector=_block_revision_vector(document, target),
            scope_selection="current_block",
            allowed_scopes=["current"],
            impact_summary={
                "diagnosis": f"根据你的要求调整“{str(target.payload.get('title') or section.title)}”。",
                "scope_selection": "current_block",
                "request_id": request_id,
                "request_fingerprint": request_fingerprint,
                "anchor_block_id": block_id,
                "anchor_role": target.role,
                "target_roles": [target.role] if target.role else [],
                "target_role_labels": [
                    ROLE_TITLES.get(target.role, target.role)
                ] if target.role else [],
                "matched_block_count": 1,
                "matched_targets": [{
                    "section_id": section_id,
                    "section_title": section.title,
                    "block_id": block_id,
                    "block_title": str(target.payload.get("title") or ""),
                    "role": target.role,
                    "action": "REPLACE",
                }],
                "affected_section_ids": [section_id],
                "direct_block_ids": [block_id],
                "dependent_block_ids": [],
                "protected": [
                    "当前内容之外的全部课程内容",
                    "其他课程",
                    "历史作答与掌握记录",
                    "笔记原文",
                    "课程知识定义",
                ],
                "matching_policy": "只生成当前正文块的一项替换候选，不扩展到相邻内容。",
                "scene_analysis": {
                    "analysis_source": "direct_block_request",
                    "direction": direction,
                    "scene_summary": request_text,
                    "rationale": "用户明确指定当前内容，因此系统不允许 AI 扩大范围。",
                },
                "validation_plan": "应用后使用后续反馈或同知识点独立任务验证效果。",
            },
            expected_effect=_block_expected_effect(direction),
            created_at=now,
            updated_at=now,
        )
        current.hypotheses.append(hypothesis)
        current.change_sets.append(plan)
        created = True
        return current

    state = repository.update(user_id, course_id, claim)
    if not created:
        return state

    candidate_repository = (
        candidate_repository or block_regeneration_candidate_repository
    )
    service = BlockRegenerationService(
        document_repository,
        candidate_repository,
        generator=generator,
    )
    candidate_id = candidate_repository.candidate_id_for(
        course_id,
        block_id,
        f"{request_id}-{block_id}",
    )
    _update_block_plan(
        repository,
        user_id=user_id,
        course_id=course_id,
        change_set_id=change_set_id,
        update=lambda plan: plan.impact_summary.update({
            "candidate_id": candidate_id,
        }),
    )
    try:
        candidate = await service.create_candidate(
            course_id,
            block_id,
            request_id=f"{request_id}-{block_id}",
            expected_document_revision=expected_document_revision,
            expected_block_revision=expected_block_revision,
            instruction=_block_generation_instruction(direction, request_text),
            action_type=direction if direction in {"simplify", "expand"} else "rewrite",
            user_id=user_id,
        )
        candidate_status = str(candidate.get("status") or "")
        if candidate_status != "ready":
            message = str(
                candidate.get("failure_reason")
                or (candidate.get("quality_report") or {}).get("issues")
                or "Current-content candidate did not pass generation checks"
            )
            _fail_block_plan(
                repository,
                user_id=user_id,
                course_id=course_id,
                change_set_id=change_set_id,
                message=message,
                candidate_status=candidate_status,
            )
            raise ValueError(message)

        proposed_block = _redact_exact_text(
            candidate.get("proposed_block") or {},
            request_text,
        )
        before_block = target.model_dump(mode="json")
        operation = CourseEvolutionOperation(
            operation_id=stable_hash(
                {
                    "change_set_id": change_set_id,
                    "block_id": block_id,
                    "kind": "replace",
                },
                prefix="ceo_",
            ),
            operation_type="REPLACE_COURSE_BLOCK",
            target_block_id=block_id,
            target_section_id=section_id,
            reason="直接响应你对当前内容提出的调整要求。",
            payload={
                "action": "REPLACE",
                "role": target.role,
                "target_section_title": section.title,
                "before_block": before_block,
                "before_preview": summarize_text(
                    str(target.payload.get("markdown") or target.payload.get("text") or ""),
                    limit=900,
                ),
                "proposed_block": proposed_block,
                "after_preview": summarize_text(
                    str(
                        (proposed_block.get("payload") or {}).get("markdown")
                        or (proposed_block.get("payload") or {}).get("text")
                        or ""
                    ),
                    limit=900,
                ),
                "expected_block_revision": expected_block_revision,
                "candidate_id": candidate_id,
                "candidate_status": "ready",
                "quality_report": deepcopy(candidate.get("quality_report") or {}),
            },
        )

        def finalize(plan: CourseEvolutionPlan) -> None:
            plan.operations = [operation]
            plan.generation_status = "ready"
            plan.updated_at = _now()
            plan.impact_summary = {
                **deepcopy(plan.impact_summary),
                "quality_report": deepcopy(candidate.get("quality_report") or {}),
            }

        return _update_block_plan(
            repository,
            user_id=user_id,
            course_id=course_id,
            change_set_id=change_set_id,
            update=finalize,
        )
    except asyncio.CancelledError:
        _fail_block_plan(
            repository,
            user_id=user_id,
            course_id=course_id,
            change_set_id=change_set_id,
            message="Course adjustment generation was interrupted",
            candidate_status="generation_failed",
        )
        raise
    except ValueError:
        raise
    except Exception as exc:
        _fail_block_plan(
            repository,
            user_id=user_id,
            course_id=course_id,
            change_set_id=change_set_id,
            message=str(exc),
            candidate_status="generation_failed",
        )
        raise ValueError(str(exc)) from exc


def _update_block_plan(
    repository: CourseEvolutionRepository,
    *,
    user_id: str,
    course_id: str,
    change_set_id: str,
    update: Any,
) -> CourseEvolutionState:
    def apply(current: CourseEvolutionState) -> CourseEvolutionState:
        plan = next(
            (
                item for item in current.change_sets
                if item.change_set_id == change_set_id
            ),
            None,
        )
        if plan is None:
            raise KeyError(change_set_id)
        update(plan)
        return current

    return repository.update(user_id, course_id, apply)


def _fail_block_plan(
    repository: CourseEvolutionRepository,
    *,
    user_id: str,
    course_id: str,
    change_set_id: str,
    message: str,
    candidate_status: str,
) -> CourseEvolutionState:
    def fail(plan: CourseEvolutionPlan) -> None:
        plan.generation_status = "failed"
        plan.updated_at = _now()
        plan.impact_summary = {
            **deepcopy(plan.impact_summary),
            "generation_error": message,
            "candidate_status": candidate_status,
        }

    return _update_block_plan(
        repository,
        user_id=user_id,
        course_id=course_id,
        change_set_id=change_set_id,
        update=fail,
    )


def _block_revision_vector(
    document: CourseDocument,
    target: CourseBlock,
) -> dict[str, str]:
    vector = revision_vector_for_document(document).revisions
    allowed = {
        f"section:{target.section_id}",
        f"block:{target.block_id}",
    }
    return {key: value for key, value in vector.items() if key in allowed}


def _block_generation_instruction(direction: str, request_text: str) -> str:
    direction_text = {
        "simplify": "降低理解门槛，用更直观、清楚的表达解释关键概念。",
        "expand": "补充必要的推理、例子或应用，让解释更完整。",
        "custom": "严格根据学生的具体要求调整正文。",
    }[direction]
    return (
        f"{direction_text}\n"
        "这是学生明确指定的当前正文块，不得扩展到其他内容。\n"
        f"学生调整要求：{request_text}"
    )


def _block_expected_effect(direction: str) -> str:
    return {
        "simplify": "当前内容更容易理解，同时保持原知识边界不变。",
        "expand": "当前内容的推理、例子或应用更完整。",
        "custom": "当前内容按学生的明确要求完成调整。",
    }[direction]


def _redact_exact_text(value: Any, text: str) -> Any:
    needle = text.strip()
    if not needle:
        return deepcopy(value)
    if isinstance(value, str):
        return value.replace(needle, "（学生调整要求原文已省略）")
    if isinstance(value, list):
        return [_redact_exact_text(item, needle) for item in value]
    if isinstance(value, dict):
        return {
            key: _redact_exact_text(item, needle)
            for key, item in value.items()
        }
    return deepcopy(value)


async def generate_section_evolution_plan(
    course_data: dict[str, Any],
    *,
    user_id: str,
    section_id: str,
    instruction: str,
    request_id: str,
    scope_selection: Literal["current_section", "whole_course"] = "current_section",
    anchor_role: str | None = None,
    repository: CourseEvolutionRepository,
    document_repository: CourseDocumentRepository,
    generator: Any | None = None,
    existing_change_set_id: str = "",
) -> CourseEvolutionState:
    """Generate and checkpoint a reviewable section change without mutating the course."""
    if scope_selection not in {"current_section", "whole_course"}:
        raise ValueError("Unsupported course evolution scope")
    if anchor_role is not None and anchor_role not in ROLE_TITLES:
        raise ValueError("Unsupported course evolution anchor role")
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
        scope_selection = plan.scope_selection
        stored_anchor_role = str(plan.impact_summary.get("anchor_role") or "")
        if anchor_role is None and stored_anchor_role in ROLE_TITLES:
            anchor_role = stored_anchor_role

    fallback = analyze_section_request(effective_instruction)
    if (
        scope_selection == "whole_course"
        and anchor_role is not None
    ):
        fallback["roles"] = [anchor_role]
        fallback["difficulty_delta"] = _difficulty_delta(
            fallback["growth_direction"],
            fallback["roles"],
        )
        fallback["rationale"] = (
            f"本次请求从正文块发起，系统沿用当前内容的"
            f"“{ROLE_TITLES[anchor_role]}”定位匹配全课程同类内容。"
        )
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
    if (
        scope_selection == "whole_course"
        and anchor_role is not None
    ):
        analysis["roles"] = [anchor_role]
        analysis["difficulty_delta"] = _difficulty_delta(
            analysis["growth_direction"],
            analysis["roles"],
        )
        analysis["rationale"] = (
            f"本次请求从正文块发起，系统沿用当前内容的"
            f"“{ROLE_TITLES[anchor_role]}”定位，匹配全课程同类内容。"
        )
        analysis["role_resolution"] = "current_block_anchor"
    analysis["anchor_role"] = anchor_role

    sections_by_id = {
        item.section_id: item
        for item in document.sections
    }
    section_order = {
        item.section_id: index
        for index, item in enumerate(document.sections)
    }
    active_blocks_by_section = {
        item.section_id: sorted(
            (
                block
                for block in document.blocks
                if block.section_id == item.section_id and block.status != "retired"
            ),
            key=lambda block: (block.position, block.block_id),
        )
        for item in document.sections
    }
    generation_targets: list[dict[str, Any]] = []
    knowledge_refs_by_section: dict[str, list[str]] = {}
    if scope_selection == "whole_course":
        matched_blocks = sorted(
            (
                block
                for block in document.blocks
                if block.status != "retired" and block.role in analysis["roles"]
            ),
            key=lambda block: (
                section_order.get(block.section_id, len(section_order)),
                block.position,
                block.block_id,
            ),
        )
        if not matched_blocks:
            labels = "、".join(
                ROLE_TITLES.get(role, role)
                for role in analysis["roles"]
            )
            raise ValueError(f"当前课程中没有可匹配的“{labels}”教学节点")
        missing_contract_sections: list[str] = []
        for target in matched_blocks:
            target_section = sections_by_id.get(target.section_id)
            if target_section is None:
                continue
            target_binding = knowledge_binding_for_section(
                knowledge_base,
                target.section_id,
            )
            target_knowledge_refs = list(target_binding["course_knowledge_refs"])
            if not target_knowledge_refs:
                missing_contract_sections.append(target_section.title)
                continue
            knowledge_refs_by_section[target.section_id] = target_knowledge_refs
            generation_targets.append({
                "role": target.role,
                "target": target,
                "section": target_section,
                "active_blocks": active_blocks_by_section[target.section_id],
                "binding": target_binding,
                "knowledge_refs": target_knowledge_refs,
                "knowledge_context": course_knowledge_base_prompt_context(
                    knowledge_base,
                    target.section_id,
                ),
            })
        if missing_contract_sections:
            raise ValueError(
                "以下小节缺少课程知识契约，不能生成全课程候选："
                + "、".join(dict.fromkeys(missing_contract_sections))
            )
    else:
        knowledge_refs_by_section[section_id] = knowledge_refs
        for role in analysis["roles"]:
            matching_blocks = [
                block
                for block in active_blocks
                if block.role == role
            ]
            for target in matching_blocks or [None]:
                generation_targets.append({
                    "role": role,
                    "target": target,
                    "section": section,
                    "active_blocks": active_blocks,
                    "binding": binding,
                    "knowledge_refs": knowledge_refs,
                    "knowledge_context": knowledge_context,
                })

    affected_section_ids = list(dict.fromkeys(
        item["section"].section_id
        for item in generation_targets
    ))
    affected_block_ids = list(dict.fromkeys(
        (
            item["target"].block_id
            if item["target"] is not None
            else _insertion_anchor(item["active_blocks"], item["role"]).block_id
        )
        for item in generation_targets
    ))

    if plan is not None:
        plan.request_text = analysis["instruction"]
        plan.requested_roles = analysis["roles"]
        plan.growth_direction = analysis["growth_direction"]
        plan.scope_selection = scope_selection
        plan.expected_effect = _expected_effect(analysis["growth_direction"])
        plan.operations = []
    else:
        change_set_id = stable_hash(
            {
                "course_id": course_id,
                "user_id": user_id,
                "section_id": section_id,
                "request_id": request_id,
                "scope_selection": scope_selection,
                "anchor_role": anchor_role,
            },
            prefix="ces_",
        )
        existing = next(
            (item for item in state.change_sets if item.change_set_id == change_set_id),
            None,
        )
        if existing is not None:
            return state
        target = generation_targets[0]["target"] or active_blocks[0]
        hypothesis_id = stable_hash(
            {
                "course_id": course_id,
                "user_id": user_id,
                "section_id": section_id,
                "request_id": request_id,
                "kind": "manual_section_growth",
                "scope_selection": scope_selection,
                "anchor_role": anchor_role,
            },
            prefix="ahp_",
        )
        scope_label = "当前全课程" if scope_selection == "whole_course" else "当前小节"
        hypothesis = AdaptationHypothesis(
            hypothesis_id=hypothesis_id,
            user_id=user_id,
            course_id=course_id,
            problem_type="section_growth_request",
            claim=f"学习者希望在{scope_label}内调整内容：{analysis['instruction']}",
            target_block_id=target.block_id,
            confidence=1.0,
            confidence_reasons=["用户明确提出本小节调整要求"],
            evidence_assessment={
                "actionable": True,
                "maturity": "explicit_section_request",
                "gate_reason": (
                    "用户明确选择当前全课程；系统只匹配自然语言点名的教学作用并等待逐项确认"
                    if scope_selection == "whole_course"
                    else "用户主动发起，仅在当前小节生成候选并等待确认"
                ),
            },
            recommended_scope="current",
            affected_block_ids=affected_block_ids,
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
            base_revision_vector=_sections_revision_vector(
                document,
                affected_section_ids,
            ),
            scope_selection=scope_selection,
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
    plan.scope_selection = scope_selection
    plan.base_revision_vector = _sections_revision_vector(
        document,
        affected_section_ids,
    )
    all_knowledge_refs = list(dict.fromkeys(
        value
        for item in generation_targets
        for value in item["binding"]["course_knowledge_refs"]
    ))
    all_skill_refs = list(dict.fromkeys(
        value
        for item in generation_targets
        for value in item["binding"]["course_skill_refs"]
    ))
    all_misconception_refs = list(dict.fromkeys(
        value
        for item in generation_targets
        for value in item["binding"]["course_misconception_refs"]
    ))
    all_mastery_refs = list(dict.fromkeys(
        value
        for item in generation_targets
        for value in item["binding"]["course_mastery_refs"]
    ))
    matched_targets = [
        {
            "section_id": item["section"].section_id,
            "section_title": item["section"].title,
            "block_id": (
                item["target"].block_id
                if item["target"] is not None
                else _insertion_anchor(item["active_blocks"], item["role"]).block_id
            ),
            "block_title": (
                str(item["target"].payload.get("title") or "")
                if item["target"] is not None
                else ROLE_TITLES.get(item["role"], item["role"])
            ),
            "role": item["role"],
            "action": "REPLACE" if item["target"] is not None else "INSERT",
        }
        for item in generation_targets
    ]
    plan.impact_summary = {
        **deepcopy(plan.impact_summary),
        "diagnosis": _plan_diagnosis(
            section.title,
            analysis,
            scope_selection=scope_selection,
            matched_count=len(generation_targets),
        ),
        "scope_selection": scope_selection,
        "anchor_role": anchor_role,
        "search_domain": "current_course" if scope_selection == "whole_course" else "current_section",
        "target_roles": list(analysis["roles"]),
        "target_role_labels": [
            ROLE_TITLES.get(role, role)
            for role in analysis["roles"]
        ],
        "matched_block_count": len(generation_targets),
        "matched_targets": matched_targets,
        "affected_section_ids": affected_section_ids,
        "direct_block_ids": affected_block_ids,
        "dependent_block_ids": [],
        "protected": [
            "未匹配用户语义目标的教学块",
            (
                "当前课程之外的全部内容"
                if scope_selection == "whole_course"
                else "当前小节之外的课程内容"
            ),
            "其他课程",
            "历史作答与掌握记录",
            "笔记原文",
            "课程知识定义",
        ],
        "matching_policy": (
            "只升级当前课程中已存在且教学作用匹配的块，不向每个小节机械补块"
            if scope_selection == "whole_course"
            else "已有教学作用保留块身份升级，缺失教学作用在当前小节新增"
        ),
        "difficulty_delta": analysis["difficulty_delta"],
        "scene_analysis": {
            key: deepcopy(value)
            for key, value in analysis.items()
            if key != "instruction"
        },
        "knowledge_node_ids": all_knowledge_refs,
        "ability_point_ids": all_skill_refs,
        "misconception_point_ids": all_misconception_refs,
        "mastery_criterion_ids": all_mastery_refs,
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
    first_generation_target = generation_targets[0]
    difficulty_anchor = (
        first_generation_target["target"]
        or _insertion_anchor(
            first_generation_target["active_blocks"],
            first_generation_target["role"],
        )
    )
    difficulty_operation = CourseEvolutionOperation(
        operation_id=stable_hash(
            {"change_set_id": plan.change_set_id, "kind": "difficulty"},
            prefix="ceo_",
        ),
        operation_type="ADJUST_COURSE_DIFFICULTY",
        target_block_id=difficulty_anchor.block_id,
        target_section_id=first_generation_target["section"].section_id,
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
        for generation_target in generation_targets:
            role = generation_target["role"]
            target = generation_target["target"]
            target_section = generation_target["section"]
            target_section_id = target_section.section_id
            target_active_blocks = generation_target["active_blocks"]
            target_knowledge_refs = generation_target["knowledge_refs"]
            target_knowledge_context = generation_target["knowledge_context"]
            if target is not None:
                operation = _replacement_placeholder(plan, target, role)
            else:
                anchor = _insertion_anchor(target_active_blocks, role)
                operation = _insertion_placeholder(
                    plan,
                    target_section_id,
                    anchor,
                    role,
                )
            operation.payload.update({
                "target_section_title": target_section.title,
                "target_block_title": (
                    str(target.payload.get("title") or "")
                    if target is not None
                    else ROLE_TITLES.get(role, role)
                ),
            })
            plan.operations.append(operation)
            repository.save(state)

            operation_anchor = target or _block_for_anchor(
                target_active_blocks,
                operation,
            )
            previous_block, next_block = _neighbors(
                target_active_blocks,
                operation_anchor,
            )
            feedback: list[str] = []
            quality_report: dict[str, Any] = {}
            proposed: CourseBlock | None = None
            for attempt in range(2):
                if target is not None:
                    content = await generator.generate_course_block_candidate(
                        course_id=course_id,
                        document_title=document.title,
                        section=target_section.model_dump(mode="json"),
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
                        section=target_section.model_dump(mode="json"),
                        desired_role=role,
                        instruction=analysis["instruction"],
                        previous_block=previous_block,
                        next_block=next_block,
                        knowledge_context=target_knowledge_context,
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
                                "section_id": target_section_id,
                                "role": role,
                            },
                            prefix="ceb_",
                        ),
                        section_id=target_section_id,
                        position=operation_anchor.position + 1,
                        kind=default_block_kind_for_role(role),
                        role=role,
                        payload={"title": ROLE_TITLES.get(role, "新增教学块"), "markdown": ""},
                        objective_refs=(
                            [target_section.objective_id]
                            if target_section.objective_id
                            else []
                        ),
                        concept_refs=target_knowledge_refs,
                        evidence_refs=list(plan.evidence_ids),
                        status="final",
                    )
                    original_payload = deepcopy(proposed.payload)
                content = str(content or "").strip()
                proposed.payload["markdown"] = content
                proposed.payload["summary"] = summarize_text(content)
                proposed.concept_refs = target_knowledge_refs
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
                    section_id=target_section_id,
                    knowledge_refs=target_knowledge_refs,
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
                raise ValueError(
                    f"“{target_section.title}”的"
                    f"{ROLE_TITLES.get(role, role)}候选未通过质量检查"
                )
            generated_contents.append(_normalize(str(proposed.payload.get("markdown") or "")))

        path_operations = _challenge_path_operations(
            plan,
            document=document,
            evidence_count=len(plan.evidence_ids),
        )
        if path_operations:
            plan.operations.extend(path_operations)
            plan.impact_summary["personal_path_actions"] = [
                {
                    "operation_id": operation.operation_id,
                    "operation_type": operation.operation_type,
                    "block_id": operation.target_block_id,
                    "section_id": operation.target_section_id,
                    "reason": operation.reason,
                }
                for operation in path_operations
            ]
            plan.impact_summary["direct_block_ids"] = list(dict.fromkeys([
                *plan.impact_summary.get("direct_block_ids", []),
                *(operation.target_block_id for operation in path_operations),
            ]))

        plan_quality = _plan_quality(
            plan,
            section_id=section_id,
            knowledge_refs_by_section=knowledge_refs_by_section,
        )
        plan.impact_summary["quality_report"] = plan_quality
        plan.impact_summary["operation_summary"] = [
            {
                "operation_id": operation.operation_id,
                "action": str(operation.payload.get("action") or "ADJUST"),
                "role": str(operation.payload.get("desired_role") or ""),
                "block_id": operation.target_block_id,
                "section_id": operation.target_section_id,
                "section_title": str(
                    operation.payload.get("target_section_title") or ""
                ),
                "candidate_status": str(operation.payload.get("candidate_status") or ""),
            }
            for operation in plan.operations
        ]
        plan.generation_status = "ready" if plan_quality["passed"] else "failed"
        if not plan_quality["passed"]:
            raise ValueError("课程调整方案未通过结构化同源检查")
    except Exception as exc:
        plan.generation_status = "failed"
        plan.impact_summary["generation_error"] = str(exc)
        plan.updated_at = _now()
        repository.save(state)
        raise

    plan.updated_at = _now()
    return repository.save(state)


def _challenge_path_operations(
    plan: CourseEvolutionPlan,
    *,
    document: CourseDocument,
    evidence_count: int,
) -> list[CourseEvolutionOperation]:
    """Turn stable success into reviewable subtraction and path reorganization.

    These operations are proposed only for evidence-triggered challenge growth.
    They never run merely because a learner typed "make it harder", and still
    require the same explicit plan confirmation as every other course change.
    """
    if (
        plan.source_kind != "learning_evidence"
        or plan.growth_direction != "challenge"
        or evidence_count < 2
    ):
        return []
    section_blocks = sorted(
        (
            block
            for block in document.blocks
            if block.section_id == plan.target_section_id
            and block.status != "retired"
        ),
        key=lambda block: (block.position, block.block_id),
    )
    if len(section_blocks) < 2:
        return []
    replaced_ids = {
        operation.target_block_id
        for operation in plan.operations
        if operation.operation_type == "REPLACE_COURSE_BLOCK"
    }
    operations: list[CourseEvolutionOperation] = []
    fold_target = next(
        (
            block
            for block in section_blocks
            if block.role in {"orientation", "example"}
            and block.block_id not in replaced_ids
        ),
        None,
    )
    if fold_target is not None:
        operations.append(CourseEvolutionOperation(
            operation_id=stable_hash({
                "change_set_id": plan.change_set_id,
                "target_block_id": fold_target.block_id,
                "kind": "fold_mastered_scaffold",
            }, prefix="ceo_"),
            operation_type="FOLD_COURSE_BLOCK",
            target_block_id=fold_target.block_id,
            target_section_id=fold_target.section_id,
            reason="多次独立正式通过表明这段基础支架已会，可从默认路径折叠；历史内容与证据继续保留。",
            payload={
                "action": "FOLD",
                "candidate_status": "ready",
                "desired_role": fold_target.role,
                "target_section_title": str(
                    next(
                        (
                            section.title
                            for section in document.sections
                            if section.section_id == fold_target.section_id
                        ),
                        "",
                    )
                ),
                "target_block_title": str(fold_target.payload.get("title") or ""),
                "before_preview": summarize_text(
                    str(
                        fold_target.payload.get("markdown")
                        or fold_target.payload.get("text")
                        or ""
                    ),
                    limit=600,
                ),
                "after_preview": "默认学习路径中折叠；需要复习时仍可从课程历史与学习地图找回。",
            },
        ))

    application = next(
        (
            block
            for block in section_blocks
            if block.role == "application"
            and block.block_id not in replaced_ids
        ),
        None,
    )
    anchor = next(
        (
            block
            for block in reversed(section_blocks)
            if block.role in {"reasoning", "concept"}
            and block.block_id != getattr(application, "block_id", "")
        ),
        None,
    )
    if application is not None and anchor is not None:
        current_index = section_blocks.index(application)
        anchor_index = section_blocks.index(anchor)
        current_previous = section_blocks[current_index - 1] if current_index > 0 else None
        if anchor_index < current_index and getattr(current_previous, "block_id", "") != anchor.block_id:
            operations.append(CourseEvolutionOperation(
                operation_id=stable_hash({
                    "change_set_id": plan.change_set_id,
                    "target_block_id": application.block_id,
                    "after_block_id": anchor.block_id,
                    "kind": "advance_transfer_challenge",
                }, prefix="ceo_"),
                operation_type="REORDER_COURSE_BLOCK",
                target_block_id=application.block_id,
                target_section_id=application.section_id,
                reason="基础任务已稳定通过，把迁移应用提前到核心解释之后，让个人路径更快进入高阶任务。",
                payload={
                    "action": "REORDER",
                    "candidate_status": "ready",
                    "desired_role": application.role,
                    "after_block_id": anchor.block_id,
                    "target_block_title": str(application.payload.get("title") or ""),
                    "before_preview": (
                        f"位于“{str(current_previous.payload.get('title') or '')}”之后"
                        if current_previous is not None
                        else "位于本节开头"
                    ),
                    "after_preview": f"移动到“{str(anchor.payload.get('title') or '')}”之后",
                },
            ))
    return operations


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
            {
                "change_set_id": plan.change_set_id,
                "target_block_id": target.block_id,
                "role": role,
                "action": "replace",
            },
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
            {
                "change_set_id": plan.change_set_id,
                "section_id": section_id,
                "anchor_block_id": anchor.block_id,
                "role": role,
                "action": "insert",
            },
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
    knowledge_refs_by_section: dict[str, list[str]],
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
    expected_roles = (
        {
            str(item.get("role") or "")
            for item in plan.impact_summary.get("matched_targets") or []
            if str(item.get("role") or "")
        }
        if plan.scope_selection == "whole_course"
        else set(plan.requested_roles)
    )
    proposed_blocks = [
        item.payload.get("proposed_block")
        for item in content_operations
        if isinstance(item.payload.get("proposed_block"), dict)
    ]
    proposed_section_ids = {
        str(item.get("section_id") or "")
        for item in proposed_blocks
    }
    expected_section_ids = set(
        plan.impact_summary.get("affected_section_ids") or [section_id]
    )
    scope_boundary_passed = (
        proposed_section_ids == {section_id}
        if plan.scope_selection == "current_section"
        else bool(proposed_section_ids)
        and proposed_section_ids <= expected_section_ids
    )
    gates = [
        _gate(
            "requested_roles_realized",
            expected_roles <= realized_roles,
            "并非所有用户要求的教学作用都已形成候选",
        ),
        _gate(
            "all_candidates_ready",
            bool(content_operations)
            and all(item.payload.get("candidate_status") == "ready" for item in content_operations),
            "仍有教学块候选未通过质量检查",
        ),
        _gate(
            "scope_boundary",
            scope_boundary_passed,
            (
                "方案中的候选超出了用户选择的课程范围"
                if plan.scope_selection == "whole_course"
                else "方案中的候选没有保持在当前小节"
            ),
        ),
        _gate(
            "same_source",
            bool(knowledge_refs_by_section)
            and all(
                bool(item.get("concept_refs"))
                and not (
                    set(item.get("concept_refs") or [])
                    - set(
                        knowledge_refs_by_section.get(
                            str(item.get("section_id") or ""),
                            [],
                        )
                    )
                )
                for item in proposed_blocks
            ),
            "方案中的教学块没有全部绑定各自小节的课程知识来源",
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
    return _sections_revision_vector(document, [section_id])


def _sections_revision_vector(
    document: CourseDocument,
    section_ids: list[str],
) -> dict[str, str]:
    vector = revision_vector_for_document(document).revisions
    selected_section_ids = set(section_ids)
    allowed = {
        f"section:{section_id}"
        for section_id in selected_section_ids
    }
    allowed.update(
        f"block:{block.block_id}"
        for block in document.blocks
        if block.section_id in selected_section_ids and block.status != "retired"
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


def _plan_diagnosis(
    section_title: str,
    analysis: dict[str, Any],
    *,
    scope_selection: Literal["current_section", "whole_course"],
    matched_count: int,
) -> str:
    labels = "、".join(ROLE_TITLES.get(role, role) for role in analysis["roles"])
    action = "提高挑战" if analysis["growth_direction"] == "challenge" else "按要求调整"
    if scope_selection == "whole_course":
        return (
            f"你限定了当前全课程；AI 将“{analysis['instruction']}”解释为"
            f"{action}{labels}，共匹配 {matched_count} 个现有教学节点。"
        )
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
    "generate_block_evolution_plan",
    "generate_course_adjustment_plan",
    "generate_section_evolution_plan",
]
