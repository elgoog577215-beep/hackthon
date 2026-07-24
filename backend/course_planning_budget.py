"""Deterministic budget and batching rules for course teaching plans.

The planner keeps global semantic decisions serial, expands bounded batches in
parallel, and leaves final assembly to local code.  It never calls a model.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from typing import Any


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def estimate_json_tokens(value: Any) -> int:
    """Return a conservative provider-independent JSON token estimate."""
    serialized = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    ascii_chars = sum(character.isascii() for character in serialized)
    non_ascii_chars = len(serialized) - ascii_chars
    return max(
        1,
        math.ceil(
            ascii_chars / 3.2
            + non_ascii_chars * 1.2
        ),
    )


@dataclass(frozen=True)
class CoursePlanningBudget:
    # Every course uses the same skeleton -> bounded details -> local assembly
    # path. These limits only bound one model request; they never classify or
    # shrink a course into a separate small-course product mode.
    skeleton_max_sections: int = 2
    batch_max_sections: int = 1
    batch_max_knowledge: int = 15
    max_input_tokens: int = 7000
    max_output_tokens: int = 8000
    concurrency: int = 4
    # Legacy field name retained for callers: this is a continuous stream
    # inactivity window, not a wall-clock request deadline.
    batch_timeout_seconds: int = 90
    total_timeout_seconds: int = 0

    @classmethod
    def from_env(cls) -> CoursePlanningBudget:
        return cls(
            skeleton_max_sections=_env_int(
                "COURSE_TEACHING_PLAN_SKELETON_MAX_SECTIONS", 2,
                minimum=2, maximum=8,
            ),
            batch_max_sections=_env_int(
                "COURSE_TEACHING_PLAN_BATCH_MAX_SECTIONS", 1,
                minimum=1, maximum=6,
            ),
            batch_max_knowledge=_env_int(
                "COURSE_TEACHING_PLAN_BATCH_MAX_KNOWLEDGE", 15,
                minimum=2, maximum=30,
            ),
            max_input_tokens=_env_int(
                "COURSE_TEACHING_PLAN_MAX_INPUT_TOKENS", 7000,
                minimum=2000, maximum=8000,
            ),
            max_output_tokens=_env_int(
                "COURSE_TEACHING_PLAN_MAX_OUTPUT_TOKENS", 8000,
                minimum=2000, maximum=12000,
            ),
            concurrency=_env_int(
                "COURSE_TEACHING_PLAN_CONCURRENCY", 4,
                minimum=1, maximum=4,
            ),
            batch_timeout_seconds=_env_int(
                "COURSE_TEACHING_PLAN_INACTIVITY_TIMEOUT_SECONDS", 90,
                minimum=30, maximum=600,
            ),
            total_timeout_seconds=0,
        )


def build_compact_planning_context(
    sections: list[dict[str, Any]],
    *,
    composition_style: str,
) -> dict[str, Any]:
    """Deduplicate difficulty and module contracts shared by many sections."""
    difficulty_baseline = _compact_difficulty_contract(
        (sections[0].get("difficulty_contract") or {}) if sections else {}
    )
    module_catalog: dict[str, dict[str, Any]] = {}
    compact_sections: list[dict[str, Any]] = []
    for section in sections:
        difficulty = _compact_difficulty_contract(
            section.get("difficulty_contract") or {}
        )
        difficulty_delta = {
            key: value
            for key, value in difficulty.items()
            if difficulty_baseline.get(key) != value
        }
        module_ids: list[str] = []
        for module in section.get("module_plan") or []:
            if not isinstance(module, dict):
                continue
            module_id = str(module.get("module_id") or "").strip()
            if not module_id:
                continue
            module_ids.append(module_id)
            module_catalog.setdefault(module_id, {
                "module_id": module_id,
                "label": str(module.get("label") or module_id),
                "block_role": str(module.get("block_role") or ""),
                "required": bool(module.get("required", True)),
                "output_contract": str(module.get("output_contract") or ""),
            })
        compact_section = {
            "node_id": str(section.get("node_id") or ""),
            "chapter_id": str(section.get("chapter_id") or ""),
            "section_number": section.get("section_number"),
            "title": str(section.get("title") or ""),
            "learning_objective": str(section.get("learning_objective") or ""),
            "scope_boundary": str(section.get("scope_boundary") or ""),
            "prerequisite_node_ids": list(
                section.get("prerequisite_node_ids") or []
            ),
            "difficulty_delta": difficulty_delta,
            "allowed_module_ids": module_ids,
            "evidence_hints": list(section.get("evidence_hints") or [])[:4],
        }
        lesson_archetype = _compact_lesson_archetype(
            section.get("lesson_archetype") or {}
        )
        if lesson_archetype:
            compact_section["lesson_archetype"] = lesson_archetype
        compact_sections.append(compact_section)
    return {
        "composition_style": composition_style,
        "difficulty_baseline": difficulty_baseline,
        "module_catalog": list(module_catalog.values()),
        "sections": compact_sections,
    }


def _compact_lesson_archetype(
    archetype: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(archetype, dict):
        return {}
    return {
        key: archetype.get(key)
        for key in (
            "archetype_id",
            "label",
            "purpose",
            "course_stage",
            "evidence_contract",
            "guardrails",
        )
        if archetype.get(key) not in (None, "", [], {})
    }


def _compact_difficulty_contract(
    contract: dict[str, Any],
) -> dict[str, Any]:
    """Keep only generation decisions, excluding repeated prose explanations."""
    challenge = contract.get("challenge") or {}
    support = contract.get("support") or {}
    mastery = contract.get("mastery") or {}
    exercise = contract.get("exercise_contract") or {}
    compact = {
        "target_level": contract.get("target_level"),
        "node_role": contract.get("node_role"),
        "new_concept_load": contract.get("new_concept_load"),
        "challenge": {
            key: challenge.get(key)
            for key in (
                "reasoning_depth",
                "abstraction",
                "transfer_distance",
                "integration_scope",
                "task_complexity",
                "prerequisite_load",
            )
            if challenge.get(key) is not None
        },
        "support": {
            key: support.get(key)
            for key in (
                "scaffold_intensity",
                "pacing_granularity",
                "feedback_frequency",
            )
            if support.get(key) is not None
        },
        "mastery": {
            key: mastery.get(key)
            for key in (
                "accuracy",
                "execution",
                "explanation",
                "independence",
                "transfer",
            )
            if mastery.get(key) is not None
        },
        "exercise": {
            key: exercise.get(key)
            for key in (
                "autonomy",
                "reasoning_steps",
                "transfer_distance",
                "feedback_timing",
            )
            if exercise.get(key) is not None
        },
    }
    return {
        key: value
        for key, value in compact.items()
        if value not in (None, "", {}, [])
    }


def build_teaching_plan_batches(
    sections: list[dict[str, Any]],
    skeleton: dict[str, Any],
    budget: CoursePlanningBudget,
) -> list[dict[str, Any]]:
    """Split in directory order, preferring chapter boundaries."""
    skeleton_by_id = {
        str(item.get("node_id") or ""): item
        for item in skeleton.get("sections") or []
        if isinstance(item, dict)
    }
    batches: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    current_knowledge = 0
    current_input_tokens = 0
    current_output_tokens = 0
    current_chapter = ""

    def estimate_batch_input(batch_sections: list[dict[str, Any]]) -> int:
        section_ids = [
            str(item.get("node_id") or "")
            for item in batch_sections
        ]
        identities = [
            skeleton_by_id.get(node_id) or {}
            for node_id in section_ids
        ]
        scoped_registry = select_batch_knowledge_registry(
            skeleton,
            section_ids,
        )
        return 1400 + estimate_json_tokens({
            "sections": batch_sections,
            "section_identities": identities,
            "knowledge_registry": scoped_registry,
        })

    def flush() -> None:
        nonlocal current, current_knowledge, current_chapter
        nonlocal current_input_tokens, current_output_tokens
        if not current:
            return
        batches.append({
            "batch_id": f"TP-B{len(batches) + 1:02d}",
            "section_ids": [str(item.get("node_id") or "") for item in current],
            "knowledge_count": current_knowledge,
            "estimated_input_tokens": current_input_tokens,
            "estimated_output_tokens": current_output_tokens,
        })
        current = []
        current_knowledge = 0
        current_input_tokens = 0
        current_output_tokens = 0
        current_chapter = ""

    for section in sections:
        node_id = str(section.get("node_id") or "")
        chapter_id = str(section.get("chapter_id") or "")
        identity = skeleton_by_id.get(node_id) or {}
        knowledge_count = len(identity.get("owned_knowledge_keys") or [])
        section_output_tokens = 400 + knowledge_count * 650
        crosses_chapter = bool(
            current and current_chapter and chapter_id and chapter_id != current_chapter
        )
        exceeds_limit = bool(
            current
            and (
                len(current) >= budget.batch_max_sections
                or current_knowledge + knowledge_count > budget.batch_max_knowledge
                or estimate_batch_input([*current, section]) > budget.max_input_tokens
                or current_output_tokens + section_output_tokens > budget.max_output_tokens
            )
        )
        if crosses_chapter or exceeds_limit:
            flush()
        current.append(section)
        current_knowledge += knowledge_count
        current_input_tokens = estimate_batch_input(current)
        current_output_tokens += section_output_tokens
        current_chapter = chapter_id or current_chapter
        # A single logical section cannot be split by this coarse estimator.
        # Keep it as a one-section unit and let the final-payload assembler
        # compact its optional context (or locally compile that unit) instead
        # of turning a budget estimate into a whole-course failure.
        if (
            current_input_tokens > budget.max_input_tokens
            or current_output_tokens > budget.max_output_tokens
        ):
            flush()
            batches[-1]["requires_adaptive_compaction"] = True
    flush()
    return batches


class CoursePlanningBudgetExceeded(RuntimeError):
    """Legacy compatibility error; normal batching no longer raises it."""

    retryable = False
    code = "course_planning_budget_exceeded"


def select_batch_knowledge_registry(
    skeleton: dict[str, Any],
    section_ids: list[str],
) -> list[dict[str, Any]]:
    """Return only current knowledge plus direct prerequisite/reuse references."""
    registry = [
        item
        for item in skeleton.get("knowledge_registry") or []
        if isinstance(item, dict)
    ]
    registry_by_key = {
        str(item.get("knowledge_key") or ""): item
        for item in registry
    }
    section_id_set = set(section_ids)
    selected_keys: set[str] = set()
    for identity in skeleton.get("sections") or []:
        if (
            not isinstance(identity, dict)
            or str(identity.get("node_id") or "") not in section_id_set
        ):
            continue
        selected_keys.update(
            str(key)
            for key in (
                list(identity.get("owned_knowledge_keys") or [])
                + list(identity.get("reused_knowledge_keys") or [])
            )
            if str(key)
        )
    direct_prerequisites = {
        str(key)
        for selected_key in list(selected_keys)
        for key in (
            registry_by_key.get(selected_key, {}).get("prerequisite_keys")
            or []
        )
        if str(key)
    }
    selected_keys.update(direct_prerequisites)
    return [
        item
        for item in registry
        if str(item.get("knowledge_key") or "") in selected_keys
    ]
