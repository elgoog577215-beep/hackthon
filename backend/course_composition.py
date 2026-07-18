"""课程块编排画像与确定性编译器。

教学结构决定一个学科必须有哪些模块；本模块只在其上增加课程级节奏，
并把节级难度契约投影到每个模块实例。这里不调用大模型，也不控制文案语气。
"""

from __future__ import annotations

import re
from collections import Counter
from copy import deepcopy
from dataclasses import asdict, dataclass
from typing import Any, Iterable

from course_pedagogy import MODULES, module_block_role
from shared.prompt_config import CourseCompositionStyle


COMPOSITION_PROFILE_VERSION = "course_composition_v1"


LEGACY_STYLE_MAP: dict[str, CourseCompositionStyle] = {
    "academic": CourseCompositionStyle.THEORY_DRIVEN,
    "industrial": CourseCompositionStyle.EXAMPLE_DRIVEN,
    "socratic": CourseCompositionStyle.INQUIRY_DRIVEN,
    "humorous": CourseCompositionStyle.BALANCED,
}


@dataclass(frozen=True)
class CompositionPreset:
    style: CourseCompositionStyle
    label: str
    summary: str
    rhythm: tuple[str, ...]
    emphasized_roles: tuple[str, ...]
    added_module_ids: tuple[str, ...]

    def to_dict(self, *, resolved_from: str) -> dict[str, Any]:
        payload = asdict(self)
        payload["style"] = self.style.value
        payload["rhythm"] = list(self.rhythm)
        payload["emphasized_roles"] = list(self.emphasized_roles)
        payload["added_module_ids"] = list(self.added_module_ids)
        payload["profile_version"] = COMPOSITION_PROFILE_VERSION
        payload["resolved_from"] = resolved_from
        return payload


PRESETS: dict[CourseCompositionStyle, CompositionPreset] = {
    CourseCompositionStyle.BALANCED: CompositionPreset(
        CourseCompositionStyle.BALANCED,
        "智能均衡",
        "保留学科最佳教学结构，在讲解、示范、行动与反馈之间维持均衡。",
        ("目标", "讲解", "示范或应用", "学习者行动", "检查反馈"),
        ("concept", "example", "application", "activity", "feedback"),
        (),
    ),
    CourseCompositionStyle.THEORY_DRIVEN: CompositionPreset(
        CourseCompositionStyle.THEORY_DRIVEN,
        "理论推导",
        "增加推理链、条件边界和反例检验，让结论能够被逐步解释。",
        ("概念", "深入推演", "边界检验", "例子", "练习反馈"),
        ("concept", "reasoning", "counterexample"),
        ("composition_deep_reasoning", "composition_boundary"),
    ),
    CourseCompositionStyle.EXAMPLE_DRIVEN: CompositionPreset(
        CourseCompositionStyle.EXAMPLE_DRIVEN,
        "案例实战",
        "增加典型案例与真实场景，让抽象知识通过判断过程和使用条件落地。",
        ("讲解", "补充案例", "真实场景", "学习者行动", "检查反馈"),
        ("example", "application", "activity"),
        ("composition_case_extension", "composition_real_application"),
    ),
    CourseCompositionStyle.PROJECT_DRIVEN: CompositionPreset(
        CourseCompositionStyle.PROJECT_DRIVEN,
        "项目驱动",
        "让课程从真实场景逐步进入阶段任务，并在后半程形成可验收成果。",
        ("场景", "必要知识", "项目任务", "执行反馈", "成果迁移"),
        ("application", "activity", "feedback", "transfer"),
        ("composition_real_application", "composition_project_task"),
    ),
    CourseCompositionStyle.INQUIRY_DRIVEN: CompositionPreset(
        CourseCompositionStyle.INQUIRY_DRIVEN,
        "问题探究",
        "用关键问题组织假设、依据、推演和检验，而不是只连续追问。",
        ("关键问题", "假设与概念", "依据推演", "边界检验", "反思反馈"),
        ("reasoning", "counterexample", "activity"),
        ("composition_inquiry", "composition_boundary"),
    ),
}


BASE_ROLE_ORDER = (
    "objective",
    "prerequisite",
    "orientation",
    "concept",
    "reasoning",
    "example",
    "counterexample",
    "application",
    "activity",
    "misconception",
    "feedback",
    "checkpoint",
    "remediation",
    "summary",
    "transfer",
)


ROLE_ORDER: dict[CourseCompositionStyle, tuple[str, ...]] = {
    CourseCompositionStyle.BALANCED: BASE_ROLE_ORDER,
    CourseCompositionStyle.THEORY_DRIVEN: (
        "objective", "prerequisite", "orientation", "concept", "reasoning",
        "counterexample", "example", "application", "activity", "misconception",
        "feedback", "checkpoint", "summary", "transfer", "remediation",
    ),
    CourseCompositionStyle.EXAMPLE_DRIVEN: (
        "objective", "orientation", "prerequisite", "concept", "example",
        "reasoning", "counterexample", "application", "activity", "misconception",
        "feedback", "checkpoint", "summary", "transfer", "remediation",
    ),
    CourseCompositionStyle.PROJECT_DRIVEN: (
        "objective", "orientation", "prerequisite", "concept", "example",
        "application", "activity", "reasoning", "misconception", "feedback",
        "checkpoint", "summary", "transfer", "remediation",
    ),
    CourseCompositionStyle.INQUIRY_DRIVEN: (
        "objective", "orientation", "prerequisite", "reasoning", "concept",
        "example", "counterexample", "application", "activity", "misconception",
        "feedback", "checkpoint", "summary", "transfer", "remediation",
    ),
}


FOCUS_BY_ROLE = {
    "orientation": "readiness",
    "prerequisite": "readiness",
    "objective": "goal_clarity",
    "concept": "abstraction",
    "reasoning": "reasoning_depth",
    "example": "worked_application",
    "counterexample": "boundary_reasoning",
    "application": "application",
    "activity": "independent_execution",
    "feedback": "feedback_and_correction",
    "misconception": "error_diagnosis",
    "checkpoint": "mastery_evidence",
    "remediation": "targeted_support",
    "summary": "integration",
    "transfer": "transfer",
}


def normalize_composition_style(
    value: Any = None,
    *,
    legacy_style: Any = None,
) -> tuple[CourseCompositionStyle, str]:
    raw = str(getattr(value, "value", value) or "").strip().lower()
    if raw:
        try:
            return CourseCompositionStyle(raw), "composition_style"
        except ValueError as exc:
            raise ValueError(f"Unsupported course composition style: {raw}") from exc

    legacy = str(getattr(legacy_style, "value", legacy_style) or "").strip().lower()
    if legacy in LEGACY_STYLE_MAP:
        return LEGACY_STYLE_MAP[legacy], f"legacy_style:{legacy}"
    return CourseCompositionStyle.BALANCED, "default"


def compile_composition_profile(
    value: Any = None,
    *,
    legacy_style: Any = None,
) -> dict[str, Any]:
    style, resolved_from = normalize_composition_style(value, legacy_style=legacy_style)
    return PRESETS[style].to_dict(resolved_from=resolved_from)


def attach_composition_to_plan(
    plan: dict[str, Any],
    composition_style: Any = None,
    *,
    legacy_style: Any = None,
) -> dict[str, Any]:
    """扩展并实例化课时模块，返回编排画像与全课分布。"""
    profile = compile_composition_profile(
        composition_style,
        legacy_style=legacy_style,
    )
    style = CourseCompositionStyle(profile["style"])
    sections = [
        section
        for chapter in plan.get("chapters") or []
        for section in chapter.get("sections") or []
    ]
    role_counts: Counter[str] = Counter()
    added_counts: Counter[str] = Counter()
    section_summaries: list[dict[str, Any]] = []

    for index, section in enumerate(sections):
        base_plan = [deepcopy(item) for item in section.get("module_plan") or []]
        for item in base_plan:
            item["composition_source"] = (
                "subject_required" if item.get("required", True) else "subject_optional"
            )
        for module_id in _extra_module_ids(
            style,
            index=index,
            count=len(sections),
            difficulty_contract=section.get("difficulty_contract") or {},
        ):
            spec = MODULES[module_id]
            base_plan.append(
                spec.to_dict(
                    source_mode=f"composition:{style.value}",
                    required=True,
                )
                | {"composition_source": "composition_style"}
            )
            added_counts[module_block_role(module_id)] += 1

        ordered = _order_modules(base_plan, style)
        section_key = _section_key(section, index)
        ordinal_by_module: Counter[str] = Counter()
        for item in ordered:
            module_id = str(item.get("module_id") or "")
            ordinal_by_module[module_id] += 1
            item["module_instance_id"] = (
                f"{section_key}:{module_id}:{ordinal_by_module[module_id]}"
            )
            item["composition_style"] = style.value
            item["block_role"] = str(
                item.get("block_role") or module_block_role(module_id)
            )
            item["block_difficulty_contract"] = project_block_difficulty(
                section.get("difficulty_contract") or {},
                item["block_role"],
            )
            role_counts[item["block_role"]] += 1

        section["module_plan"] = ordered
        section["composition_summary"] = {
            "style": style.value,
            "style_label": profile["label"],
            "total_blocks": len(ordered),
            "added_blocks": sum(
                1
                for item in ordered
                if item.get("composition_source") == "composition_style"
            ),
            "role_sequence": [item["block_role"] for item in ordered],
        }
        section_summaries.append(
            {
                "section_number": str(section.get("section_number") or ""),
                "node_id": str(section.get("node_id") or ""),
                **section["composition_summary"],
            }
        )

    distribution = {
        "profile_version": COMPOSITION_PROFILE_VERSION,
        "style": style.value,
        "style_label": profile["label"],
        "total_blocks": sum(role_counts.values()),
        "composition_added_blocks": sum(added_counts.values()),
        "role_counts": dict(sorted(role_counts.items())),
        "added_role_counts": dict(sorted(added_counts.items())),
        "sections": section_summaries,
    }
    plan["course_composition_profile"] = profile
    plan["course_block_distribution"] = distribution
    return {
        "course_composition_profile": profile,
        "course_block_distribution": distribution,
    }


def project_block_difficulty(
    node_contract: dict[str, Any],
    block_role: str,
) -> dict[str, Any]:
    """将节点难度变成块可执行契约，而不是原样复制。"""
    role = str(block_role or "concept")
    support = node_contract.get("support") or {}
    challenge = node_contract.get("challenge") or {}
    exercise = node_contract.get("exercise_contract") or {}
    scaffold_level = _bounded_int(support.get("scaffold_intensity"), 3)
    autonomy_level = _bounded_int(exercise.get("autonomy"), 3)
    transfer_level = _bounded_int(
        exercise.get("transfer_distance", challenge.get("transfer_distance")),
        2,
    )

    if role in {"orientation", "prerequisite", "objective", "concept", "remediation"}:
        scaffold_level = min(5, scaffold_level + 1)
        autonomy_level = max(1, autonomy_level - 1)
    elif role in {"activity", "application", "transfer"}:
        autonomy_level = min(5, autonomy_level + 1)
        if role == "transfer":
            transfer_level = min(5, transfer_level + 1)
    elif role == "example":
        autonomy_level = max(1, autonomy_level - 1)
    elif role in {"feedback", "checkpoint"}:
        scaffold_level = max(2, scaffold_level)

    feedback_timing = str(exercise.get("feedback_timing") or "after_attempt")
    if role in {"orientation", "prerequisite", "concept", "example", "remediation"}:
        feedback_timing = "inline"
    elif role in {"feedback", "checkpoint"}:
        feedback_timing = "immediate"

    reasoning_level = _bounded_int(challenge.get("reasoning_depth"), 3)
    task_level = _bounded_int(challenge.get("task_complexity"), 3)
    return {
        "contract_version": COMPOSITION_PROFILE_VERSION,
        "source": "node_contract" if node_contract else "fallback",
        "target_level": str(node_contract.get("target_level") or "intermediate"),
        "node_role": str(node_contract.get("node_role") or "foundation"),
        "block_role": role,
        "focus_dimension": FOCUS_BY_ROLE.get(role, "understanding"),
        "challenge_level": max(
            reasoning_level if role in {"reasoning", "counterexample"} else 1,
            task_level if role in {"application", "activity", "transfer"} else 1,
            2,
        ),
        "scaffold_level": scaffold_level,
        "scaffold_intensity": _level_label(scaffold_level),
        "autonomy_level": autonomy_level,
        "learner_autonomy": _autonomy_label(autonomy_level),
        "transfer_level": transfer_level,
        "transfer_distance": _transfer_label(transfer_level),
        "feedback_timing": feedback_timing,
    }


def format_composition_profile(profile: dict[str, Any]) -> str:
    if not profile:
        return "- 课程编排偏好：智能均衡"
    return "\n".join(
        [
            f"- 课程编排偏好：{profile.get('label', '')} ({profile.get('style', '')})",
            f"- 编排目的：{profile.get('summary', '')}",
            f"- 教学节奏：{' → '.join(profile.get('rhythm') or [])}",
            f"- 强调角色：{', '.join(profile.get('emphasized_roles') or [])}",
        ]
    )


def format_block_difficulty(contract: dict[str, Any]) -> str:
    if not contract:
        return "使用节点难度"
    return (
        f"{contract.get('target_level', '')} · "
        f"{contract.get('learner_autonomy', '')} · "
        f"{contract.get('scaffold_intensity', '')}支架 · "
        f"{contract.get('transfer_distance', '')}迁移"
    )


def _extra_module_ids(
    style: CourseCompositionStyle,
    *,
    index: int,
    count: int,
    difficulty_contract: dict[str, Any],
) -> list[str]:
    if style == CourseCompositionStyle.BALANCED:
        return []
    progress = (index + 1) / max(count, 1)
    node_role = str(difficulty_contract.get("node_role") or "")
    later_role = node_role in {
        "independent_task", "integration", "transfer", "capstone"
    }
    advanced = str(difficulty_contract.get("target_level") or "") == "advanced"

    if style == CourseCompositionStyle.THEORY_DRIVEN:
        result = ["composition_deep_reasoning"]
        if progress >= 0.5 or later_role or advanced:
            result.append("composition_boundary")
        return result
    if style == CourseCompositionStyle.EXAMPLE_DRIVEN:
        result = ["composition_case_extension"]
        if progress >= 0.4 or later_role:
            result.append("composition_real_application")
        return result
    if style == CourseCompositionStyle.PROJECT_DRIVEN:
        if progress >= 0.45 or later_role:
            return ["composition_project_task"]
        return ["composition_real_application"]
    if style == CourseCompositionStyle.INQUIRY_DRIVEN:
        result = ["composition_inquiry"]
        if progress >= 0.5 or later_role or advanced:
            result.append("composition_boundary")
        return result
    return []


def _order_modules(
    modules: Iterable[dict[str, Any]],
    style: CourseCompositionStyle,
) -> list[dict[str, Any]]:
    ranking = {role: index for index, role in enumerate(ROLE_ORDER[style])}
    indexed = list(enumerate(modules))
    indexed.sort(
        key=lambda pair: (
            ranking.get(
                str(
                    pair[1].get("block_role")
                    or module_block_role(str(pair[1].get("module_id") or ""))
                ),
                len(ranking),
            ),
            pair[0],
        )
    )
    return [item for _index, item in indexed]


def _section_key(section: dict[str, Any], index: int) -> str:
    raw = str(
        section.get("node_id")
        or section.get("section_number")
        or f"section-{index + 1}"
    )
    normalized = re.sub(r"[^0-9A-Za-z_.-]+", "-", raw).strip("-")
    return normalized or f"section-{index + 1}"


def _bounded_int(value: Any, fallback: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = fallback
    return max(1, min(5, parsed))


def _level_label(level: int) -> str:
    return "high" if level >= 4 else "low" if level <= 2 else "medium"


def _autonomy_label(level: int) -> str:
    return "independent" if level >= 4 else "guided" if level <= 2 else "shared"


def _transfer_label(level: int) -> str:
    return "far" if level >= 4 else "near" if level <= 2 else "adjacent"


__all__ = [
    "COMPOSITION_PROFILE_VERSION",
    "CourseCompositionStyle",
    "LEGACY_STYLE_MAP",
    "PRESETS",
    "normalize_composition_style",
    "compile_composition_profile",
    "attach_composition_to_plan",
    "project_block_difficulty",
    "format_composition_profile",
    "format_block_difficulty",
]
