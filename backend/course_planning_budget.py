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
    return max(1, math.ceil(len(serialized) / 3.2))


@dataclass(frozen=True)
class CoursePlanningBudget:
    mode: str = "auto"
    compact_max_sections: int = 3
    batch_max_sections: int = 3
    batch_max_knowledge: int = 15
    max_input_tokens: int = 8000
    max_output_tokens: int = 10000
    concurrency: int = 2
    batch_timeout_seconds: int = 300

    @classmethod
    def from_env(cls) -> "CoursePlanningBudget":
        mode = os.getenv("COURSE_TEACHING_PLAN_MODE", "auto").strip().lower()
        if mode not in {"auto", "compact", "batched"}:
            mode = "auto"
        return cls(
            mode=mode,
            compact_max_sections=_env_int(
                "COURSE_TEACHING_PLAN_COMPACT_MAX_SECTIONS", 3,
                minimum=1, maximum=8,
            ),
            batch_max_sections=_env_int(
                "COURSE_TEACHING_PLAN_BATCH_MAX_SECTIONS", 3,
                minimum=1, maximum=6,
            ),
            batch_max_knowledge=_env_int(
                "COURSE_TEACHING_PLAN_BATCH_MAX_KNOWLEDGE", 15,
                minimum=2, maximum=30,
            ),
            max_input_tokens=_env_int(
                "COURSE_TEACHING_PLAN_MAX_INPUT_TOKENS", 8000,
                minimum=2000, maximum=64000,
            ),
            max_output_tokens=_env_int(
                "COURSE_TEACHING_PLAN_MAX_OUTPUT_TOKENS", 10000,
                minimum=2000, maximum=64000,
            ),
            concurrency=_env_int(
                "COURSE_TEACHING_PLAN_CONCURRENCY", 2,
                minimum=1, maximum=4,
            ),
            batch_timeout_seconds=_env_int(
                "COURSE_TEACHING_PLAN_BATCH_TIMEOUT_SECONDS", 300,
                minimum=30, maximum=1800,
            ),
        )

    def choose_mode(
        self,
        *,
        sections: list[dict[str, Any]],
        compact_input_tokens: int,
    ) -> str:
        if self.mode != "auto":
            return self.mode
        estimated_output_tokens = len(sections) * 2600
        if (
            len(sections) <= self.compact_max_sections
            and compact_input_tokens <= self.max_input_tokens
            and estimated_output_tokens <= self.max_output_tokens
        ):
            return "compact"
        return "batched"


def build_compact_planning_context(
    sections: list[dict[str, Any]],
    *,
    composition_style: str,
) -> dict[str, Any]:
    """Deduplicate difficulty and module contracts shared by many sections."""
    difficulty_baseline = dict(
        (sections[0].get("difficulty_contract") or {}) if sections else {}
    )
    module_catalog: dict[str, dict[str, Any]] = {}
    compact_sections: list[dict[str, Any]] = []
    for section in sections:
        difficulty = dict(section.get("difficulty_contract") or {})
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
        compact_sections.append({
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
        })
    return {
        "composition_style": composition_style,
        "difficulty_baseline": difficulty_baseline,
        "module_catalog": list(module_catalog.values()),
        "sections": compact_sections,
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
    registry_input_tokens = estimate_json_tokens(
        skeleton.get("knowledge_registry") or []
    )
    current_input_tokens = registry_input_tokens + 1200
    current_output_tokens = 0
    current_chapter = ""

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
        current_input_tokens = registry_input_tokens + 1200
        current_output_tokens = 0
        current_chapter = ""

    for section in sections:
        node_id = str(section.get("node_id") or "")
        chapter_id = str(section.get("chapter_id") or "")
        identity = skeleton_by_id.get(node_id) or {}
        knowledge_count = len(identity.get("owned_knowledge_keys") or [])
        section_input_tokens = estimate_json_tokens({
            "section": section,
            "identity": identity,
        })
        section_output_tokens = 400 + knowledge_count * 650
        crosses_chapter = bool(
            current and current_chapter and chapter_id and chapter_id != current_chapter
        )
        exceeds_limit = bool(
            current
            and (
                len(current) >= budget.batch_max_sections
                or current_knowledge + knowledge_count > budget.batch_max_knowledge
                or current_input_tokens + section_input_tokens > budget.max_input_tokens
                or current_output_tokens + section_output_tokens > budget.max_output_tokens
            )
        )
        if crosses_chapter or exceeds_limit:
            flush()
        current.append(section)
        current_knowledge += knowledge_count
        current_input_tokens += section_input_tokens
        current_output_tokens += section_output_tokens
        current_chapter = chapter_id or current_chapter
    flush()
    return batches
