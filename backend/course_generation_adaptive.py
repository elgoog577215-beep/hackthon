"""Adaptive prompt assembly and deterministic course-generation fallbacks.

The hard request budget in :mod:`ai_base` is the final fuse.  Normal course
generation must fit work to that budget before it reaches the provider: remove
repeated optional context, split independent units, then locally compile the
smallest unit when a model call would still be unsafe or unavailable.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from course_versioning import stable_hash

PROMPT_DETAIL_LEVELS = ("full", "compact", "minimal")


def estimate_source_chars(value: Any, *, cap: int = 200_000) -> int:
    """Cheaply estimate raw prompt-source size without serializing it."""
    total = 0
    stack = [value]
    while stack and total < cap:
        current = stack.pop()
        if isinstance(current, dict):
            total += sum(len(str(key)) for key in current)
            stack.extend(current.values())
        elif isinstance(current, (list, tuple, set)):
            stack.extend(current)
        else:
            total += len(str(current or ""))
    return min(total, cap)


def prompt_detail_levels_for_source(
    value: Any,
    *,
    max_input_chars: int,
) -> tuple[str, ...]:
    """Skip knowingly oversized rich variants before allocating them."""
    source_chars = estimate_source_chars(
        value,
        cap=max_input_chars * 5,
    )
    if source_chars > max_input_chars * 4:
        return ("minimal",)
    if source_chars > max_input_chars:
        return ("compact", "minimal")
    return PROMPT_DETAIL_LEVELS


def clip_text(value: Any, max_chars: int) -> str:
    """Keep both the start and conclusion of a long user/domain string."""
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    if max_chars <= 16:
        return text[:max_chars]
    omitted = len(text) - max_chars
    marker = f"…[省略{omitted}字]…"
    remaining = max(2, max_chars - len(marker))
    head = max(1, int(remaining * 0.7))
    tail = max(1, remaining - head)
    return f"{text[:head]}{marker}{text[-tail:]}"


def compact_value(
    value: Any,
    *,
    max_string_chars: int,
    max_list_items: int,
    max_depth: int = 4,
) -> Any:
    """Bound arbitrary persisted metadata without mutating its source."""
    if max_depth <= 0:
        if isinstance(value, (dict, list, tuple)):
            return "[已保留在服务端，当前请求不展开]"
        return clip_text(value, max_string_chars)
    if isinstance(value, dict):
        return {
            str(key): compact_value(
                item,
                max_string_chars=max_string_chars,
                max_list_items=max_list_items,
                max_depth=max_depth - 1,
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        items = [
            compact_value(
                item,
                max_string_chars=max_string_chars,
                max_list_items=max_list_items,
                max_depth=max_depth - 1,
            )
            for item in list(value)[:max_list_items]
        ]
        if len(value) > max_list_items:
            items.append(f"[其余 {len(value) - max_list_items} 项保留在服务端]")
        return items
    if isinstance(value, str):
        return clip_text(value, max_string_chars)
    return value


@dataclass(frozen=True)
class PromptCandidate:
    detail_level: str
    user_prompt: str
    system_prompt: str


@dataclass(frozen=True)
class BudgetedPrompt:
    detail_level: str
    user_prompt: str
    system_prompt: str
    prompt_chars: int
    estimated_input_tokens: int


def select_budgeted_prompt(
    candidates: Iterable[PromptCandidate],
    *,
    max_input_chars: int,
    max_input_tokens: int,
    token_estimator: Callable[[str, str], int],
) -> BudgetedPrompt | None:
    """Select the richest final payload that really fits both input gates."""
    for candidate in candidates:
        chars = len(candidate.user_prompt) + len(candidate.system_prompt)
        tokens = token_estimator(
            candidate.user_prompt,
            candidate.system_prompt,
        )
        if chars <= max_input_chars and tokens <= max_input_tokens:
            return BudgetedPrompt(
                detail_level=candidate.detail_level,
                user_prompt=candidate.user_prompt,
                system_prompt=candidate.system_prompt,
                prompt_chars=chars,
                estimated_input_tokens=tokens,
            )
    return None


def compact_planning_context(
    context: dict[str, Any],
    *,
    detail_level: str,
) -> dict[str, Any]:
    """Preserve planning decisions while progressively removing prompt bulk."""
    if detail_level == "full":
        return deepcopy(context)

    compact = {
        "composition_style": clip_text(context.get("composition_style"), 80),
        "difficulty_baseline": compact_value(
            context.get("difficulty_baseline") or {},
            max_string_chars=80 if detail_level == "compact" else 48,
            max_list_items=8 if detail_level == "compact" else 4,
            max_depth=3,
        ),
    }
    if context.get("new_knowledge_key_start"):
        compact["new_knowledge_key_start"] = int(
            context["new_knowledge_key_start"]
        )
    catalog: list[dict[str, Any]] = []
    for item in context.get("module_catalog") or []:
        if not isinstance(item, dict):
            continue
        module = {
            "module_id": clip_text(item.get("module_id"), 64),
            "label": clip_text(item.get("label"), 80),
            "block_role": clip_text(item.get("block_role"), 40),
            "required": bool(item.get("required", True)),
        }
        if detail_level == "compact":
            module["output_contract"] = clip_text(
                item.get("output_contract"), 180
            )
        catalog.append(module)
    compact["module_catalog"] = catalog

    prior_registry = [
        item
        for item in context.get("prior_knowledge_registry") or []
        if isinstance(item, dict)
    ]
    if prior_registry:
        prior_limit = 40 if detail_level == "compact" else 20
        compact["prior_knowledge_registry"] = [
            {
                "knowledge_key": clip_text(item.get("knowledge_key"), 64),
                "name": clip_text(
                    item.get("name"),
                    120 if detail_level == "compact" else 72,
                ),
                "statement": (
                    clip_text(item.get("statement"), 180)
                    if detail_level == "compact"
                    else ""
                ),
                "owner_node_id": clip_text(item.get("owner_node_id"), 64),
            }
            for item in prior_registry[-prior_limit:]
        ]

    sections: list[dict[str, Any]] = []
    for item in context.get("sections") or []:
        if not isinstance(item, dict):
            continue
        section = {
            "node_id": clip_text(item.get("node_id"), 64),
            "section_number": item.get("section_number"),
            "title": clip_text(
                item.get("title"), 120 if detail_level == "compact" else 72
            ),
            "learning_objective": clip_text(
                item.get("learning_objective"),
                220 if detail_level == "compact" else 120,
            ),
            "scope_boundary": clip_text(
                item.get("scope_boundary"),
                180 if detail_level == "compact" else 96,
            ),
            "lesson_archetype": compact_value(
                item.get("lesson_archetype") or {},
                max_string_chars=(
                    160 if detail_level == "compact" else 88
                ),
                max_list_items=(
                    4 if detail_level == "compact" else 2
                ),
                max_depth=2,
            ),
            "prerequisite_node_ids": list(
                item.get("prerequisite_node_ids") or []
            )[:8],
            "allowed_module_ids": list(
                item.get("allowed_module_ids") or []
            )[:12],
        }
        if detail_level == "compact":
            section["difficulty_delta"] = compact_value(
                item.get("difficulty_delta") or {},
                max_string_chars=64,
                max_list_items=6,
                max_depth=2,
            )
            section["evidence_hints"] = compact_value(
                list(item.get("evidence_hints") or [])[:2],
                max_string_chars=160,
                max_list_items=2,
                max_depth=2,
            )
        sections.append({
            key: value
            for key, value in section.items()
            if value not in ("", None, [], {})
        })
    compact["sections"] = sections
    return compact


def compact_batch_inputs(
    *,
    batch_sections: list[dict[str, Any]],
    knowledge_registry: list[dict[str, Any]],
    section_identities: list[dict[str, Any]],
    module_catalog: list[dict[str, Any]],
    detail_level: str,
) -> dict[str, list[dict[str, Any]]]:
    """Bound one detailed-plan batch without changing stable IDs."""
    if detail_level == "full":
        return {
            "batch_sections": deepcopy(batch_sections),
            "knowledge_registry": deepcopy(knowledge_registry),
            "section_identities": deepcopy(section_identities),
            "module_catalog": deepcopy(module_catalog),
        }
    planning = compact_planning_context(
        {
            "sections": batch_sections,
            "module_catalog": module_catalog,
        },
        detail_level=detail_level,
    )
    registry: list[dict[str, Any]] = []
    for item in knowledge_registry:
        if not isinstance(item, dict):
            continue
        registry.append({
            "knowledge_key": clip_text(item.get("knowledge_key"), 64),
            "name": clip_text(
                item.get("name"), 120 if detail_level == "compact" else 72
            ),
            "statement": clip_text(
                item.get("statement"),
                220 if detail_level == "compact" else 120,
            ),
            "owner_node_id": clip_text(item.get("owner_node_id"), 64),
            "prerequisite_keys": list(item.get("prerequisite_keys") or [])[:8],
            "module_ids": list(item.get("module_ids") or [])[:12],
        })
    identities = [
        {
            "node_id": clip_text(item.get("node_id"), 64),
            "owned_knowledge_keys": list(
                item.get("owned_knowledge_keys") or []
            )[:8],
            "reused_knowledge_keys": list(
                item.get("reused_knowledge_keys") or []
            )[:12],
        }
        for item in section_identities
        if isinstance(item, dict)
    ]
    return {
        "batch_sections": planning["sections"],
        "knowledge_registry": registry,
        "section_identities": identities,
        "module_catalog": planning["module_catalog"],
    }


def compile_fallback_teaching_skeleton(
    sections: list[dict[str, Any]],
    *,
    outline_revision_id: str,
    prior_skeleton: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compile a valid minimal identity skeleton when global AI cannot run.

    This intentionally creates one bounded, explicit knowledge responsibility
    per section.  Detailed batches can still enrich each responsibility.  The
    fallback is recorded by the caller and is preferable to losing an entire
    course because one global request exceeded a provider window.
    """
    prior = prior_skeleton or {}
    registry: list[dict[str, Any]] = [
        deepcopy(item)
        for item in prior.get("knowledge_registry") or []
        if isinstance(item, dict)
    ]
    identities: list[dict[str, Any]] = [
        deepcopy(item)
        for item in prior.get("sections") or []
        if isinstance(item, dict)
    ]
    primary_key_by_node: dict[str, str] = {
        str(item.get("node_id") or ""): str(
            (item.get("owned_knowledge_keys") or [""])[0]
        )
        for item in identities
        if item.get("owned_knowledge_keys")
    }
    for index, section in enumerate(sections, start=len(registry) + 1):
        node_id = str(section.get("node_id") or f"section-{index}")
        key = f"K{index:03d}"
        title = clip_text(
            section.get("title") or section.get("learning_objective") or node_id,
            80,
        )
        objective = clip_text(
            section.get("learning_objective")
            or f"理解并应用{title}",
            160,
        )
        modules = [
            str(item.get("module_id") or "")
            for item in section.get("module_plan") or []
            if isinstance(item, dict) and str(item.get("module_id") or "")
        ]
        module_id = (
            "core_explanation"
            if "core_explanation" in modules
            else (modules[0] if modules else "core_explanation")
        )
        prerequisite_keys = [
            primary_key_by_node[item]
            for item in section.get("prerequisite_node_ids") or []
            if item in primary_key_by_node
        ][:3]
        name = clip_text(f"{title}的核心机制", 96)
        registry.append({
            "knowledge_key": key,
            "name": name,
            "statement": clip_text(
                f"{objective}，并能说明{title}的成立条件与适用边界。",
                200,
            ),
            "owner_node_id": node_id,
            "reused_in_node_ids": [],
            "prerequisite_keys": prerequisite_keys,
            "module_ids": [module_id],
        })
        identities.append({
            "node_id": node_id,
            "owned_knowledge_keys": [key],
            "reused_knowledge_keys": [],
        })
        primary_key_by_node[node_id] = key
    skeleton = {
        "schema_version": "course_teaching_plan_skeleton_v3",
        "source_outline_revision_id": outline_revision_id,
        "knowledge_registry": registry,
        "sections": identities,
    }
    skeleton["revision_id"] = stable_hash(
        skeleton,
        prefix="teaching_skeleton_",
    )
    return skeleton


def merge_teaching_skeleton_part(
    prior_skeleton: dict[str, Any],
    part: dict[str, Any],
    *,
    outline_revision_id: str,
) -> dict[str, Any]:
    """Append one model-generated skeleton shard with deterministic keys."""
    prior_registry = [
        deepcopy(item)
        for item in prior_skeleton.get("knowledge_registry") or []
        if isinstance(item, dict)
    ]
    prior_sections = [
        deepcopy(item)
        for item in prior_skeleton.get("sections") or []
        if isinstance(item, dict)
    ]
    prior_keys = {
        str(item.get("knowledge_key") or "")
        for item in prior_registry
    }
    raw_registry = [
        deepcopy(item)
        for item in part.get("knowledge_registry") or []
        if isinstance(item, dict)
    ]
    key_mapping: dict[str, str] = {}
    for offset, item in enumerate(raw_registry, start=len(prior_registry) + 1):
        raw_key = str(item.get("knowledge_key") or f"part-{offset}")
        key_mapping[raw_key] = f"K{offset:03d}"

    def map_key(value: Any, *, prefer_prior: bool = False) -> str:
        key = str(value or "")
        if prefer_prior and key in prior_keys:
            return key
        if key in key_mapping:
            return key_mapping[key]
        return key if key in prior_keys else key

    appended_registry: list[dict[str, Any]] = []
    for item in raw_registry:
        raw_key = str(item.get("knowledge_key") or "")
        normalized = deepcopy(item)
        normalized["knowledge_key"] = key_mapping.get(raw_key, raw_key)
        normalized["prerequisite_keys"] = [
            map_key(key, prefer_prior=True)
            for key in item.get("prerequisite_keys") or []
        ]
        appended_registry.append(normalized)
    appended_sections: list[dict[str, Any]] = []
    for item in part.get("sections") or []:
        if not isinstance(item, dict):
            continue
        appended_sections.append({
            "node_id": str(item.get("node_id") or ""),
            "owned_knowledge_keys": [
                map_key(key)
                for key in item.get("owned_knowledge_keys") or []
            ],
            "reused_knowledge_keys": [
                map_key(key, prefer_prior=True)
                for key in item.get("reused_knowledge_keys") or []
            ],
        })
    combined_sections = [*prior_sections, *appended_sections]
    declared_reuse: dict[str, list[str]] = {}
    for identity in combined_sections:
        node_id = str(identity.get("node_id") or "")
        for key in identity.get("reused_knowledge_keys") or []:
            declared_reuse.setdefault(str(key), []).append(node_id)
    combined_registry = [*prior_registry, *appended_registry]
    for item in combined_registry:
        item["reused_in_node_ids"] = list(dict.fromkeys(
            declared_reuse.get(str(item.get("knowledge_key") or ""), [])
        ))
    merged = {
        "schema_version": "course_teaching_plan_skeleton_v3",
        "source_outline_revision_id": outline_revision_id,
        "knowledge_registry": combined_registry,
        "sections": combined_sections,
    }
    merged["revision_id"] = stable_hash(
        merged,
        prefix="teaching_skeleton_",
    )
    return merged


def compile_fallback_teaching_batch(
    *,
    batch_spec: dict[str, Any],
    skeleton: dict[str, Any],
    sections: list[dict[str, Any]],
) -> dict[str, Any]:
    """Locally expand the smallest failed plan unit into a valid V3 batch."""
    section_ids = list(batch_spec.get("section_ids") or [])
    section_by_id = {
        str(item.get("node_id") or ""): item
        for item in sections
        if isinstance(item, dict)
    }
    identity_by_id = {
        str(item.get("node_id") or ""): item
        for item in skeleton.get("sections") or []
        if isinstance(item, dict)
    }
    registry = {
        str(item.get("knowledge_key") or ""): item
        for item in skeleton.get("knowledge_registry") or []
        if isinstance(item, dict)
    }
    expanded_sections: list[dict[str, Any]] = []
    for node_id in section_ids:
        section = section_by_id.get(node_id) or {}
        identity = identity_by_id.get(node_id) or {}
        owned = list(identity.get("owned_knowledge_keys") or [])
        details = []
        for key in owned:
            item = registry.get(key) or {}
            name = clip_text(item.get("name") or key, 96)
            statement = clip_text(item.get("statement") or name, 180)
            details.append({
                "knowledge_key": key,
                "concept_group": clip_text(
                    section.get("title") or "核心机制", 96
                ),
                "group_description": clip_text(
                    section.get("scope_boundary")
                    or "围绕当前小节目标解释条件、边界与应用。",
                    180,
                ),
                "knowledge_type": "concept",
                "conditions": [f"在“{statement}”描述的条件下"],
                "boundaries": [
                    clip_text(
                        section.get("scope_boundary")
                        or "不替代后续小节保留的教学责任。",
                        180,
                    )
                ],
                "counterexamples": [],
                "capability_points": [{
                    "name": clip_text(f"解释并应用{name}", 96),
                    "observable_behavior": clip_text(
                        f"能独立说明{name}的条件，并在一个新任务中正确应用。",
                        180,
                    ),
                    "required_evidence_types": ["practice_attempt"],
                }],
                "misconceptions": [{
                    "name": clip_text(f"忽略{name}的适用条件", 96),
                    "observable_error_pattern": (
                        "只复述结论，面对条件变化时仍机械套用。"
                    ),
                    "confused_with": "表面相似但条件不同的情形",
                    "discrimination": clip_text(
                        f"逐项核对“{statement}”中的条件和边界。",
                        180,
                    ),
                    "repair_strategy": (
                        "先写出成立条件，再用一个反例重新完成判断。"
                    ),
                }],
                "mastery_criteria": [{
                    "name": clip_text(f"掌握{name}", 96),
                    "observable_performance": clip_text(
                        f"无需提示即可解释{name}并完成一次变式应用。",
                        180,
                    ),
                    "required_independence": "independent",
                    "required_transfer": "variation",
                    "verification_method": (
                        "使用解释题与变式任务核对条件、过程和结论。"
                    ),
                    "required_evidence_types": ["practice_attempt"],
                }],
                "aliases": [],
            })
        allowed_modules = [
            str(item.get("module_id") or "")
            for item in section.get("module_plan") or []
            if isinstance(item, dict) and str(item.get("module_id") or "")
        ]
        skeleton_modules = list(dict.fromkeys(
            module_id
            for key in owned
            for module_id in (registry.get(key) or {}).get("module_ids") or []
            if module_id in allowed_modules
        ))
        if not skeleton_modules and allowed_modules:
            skeleton_modules = [allowed_modules[0]]
        modules = [{
            "module_id": module_id,
            "teaching_purpose": clip_text(
                f"讲清本节负责的知识条件、边界与应用："
                f"{'、'.join((registry.get(key) or {}).get('name', key) for key in owned)}",
                220,
            ),
            "knowledge_keys": owned,
            "teaching_guidance": (
                "先给出明确陈述和成立条件，再用例子、反例与可检查任务完成教学。"
            ),
        } for module_id in skeleton_modules]
        expanded_sections.append({
            "node_id": node_id,
            "knowledge_details": details,
            "knowledge_relations": [],
            "teaching_modules": modules,
        })
    batch = {
        "schema_version": "course_teaching_plan_batch_v3",
        "batch_id": str(batch_spec.get("batch_id") or ""),
        "skeleton_revision_id": str(skeleton.get("revision_id") or ""),
        "sections": expanded_sections,
    }
    batch["revision_id"] = stable_hash(batch, prefix="teaching_batch_")
    return batch


def compile_fallback_node_content(node: dict[str, Any]) -> str:
    """Create a small, honest Markdown scaffold for one unavailable AI unit."""
    title = clip_text(node.get("node_name") or "当前小节", 96)
    objective = clip_text(
        node.get("learning_objective") or f"理解并应用{title}",
        180,
    )
    scope = clip_text(
        node.get("scope_boundary") or "只完成当前小节的教学责任。",
        180,
    )
    names = [
        clip_text(item, 80)
        for item in node.get("key_points") or []
        if str(item or "").strip()
    ][:8]
    knowledge_text = "、".join(names) or title
    modules = [
        item
        for item in node.get("module_plan") or []
        if isinstance(item, dict)
    ]
    if not modules:
        modules = [{
            "label": "核心教学",
            "output_contract": "解释核心知识并给出可检查任务",
        }]
    blocks: list[str] = []
    for index, module in enumerate(modules, start=1):
        label = clip_text(
            module.get("label") or module.get("module_id") or f"教学模块 {index}",
            64,
        )
        contract = clip_text(
            module.get("output_contract")
            or module.get("teaching_guidance")
            or "完成本模块的教学责任。",
            180,
        )
        blocks.append(
            f"## {label}\n\n"
            f"本模块围绕知识规范“{knowledge_text}”展开。学习目标是：{objective}\n\n"
            f"当前范围边界：{scope}\n\n"
            f"学习任务：依据“{contract}”完成一次可检查的解释或应用，并记录"
            "仍不确定的条件。"
        )
    return "\n\n".join(blocks).strip() + "\n"


__all__ = [
    "BudgetedPrompt",
    "PROMPT_DETAIL_LEVELS",
    "PromptCandidate",
    "clip_text",
    "compact_batch_inputs",
    "compact_planning_context",
    "compact_value",
    "compile_fallback_teaching_batch",
    "compile_fallback_teaching_skeleton",
    "compile_fallback_node_content",
    "merge_teaching_skeleton_part",
    "estimate_source_chars",
    "prompt_detail_levels_for_source",
    "select_budgeted_prompt",
]
