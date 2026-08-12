"""Bounded, resumable planning primitives for large course outlines.

The product contract is one ordered ``CourseOutlineRevision``.  The execution
contract is intentionally smaller:

1. one light chapter skeleton freezes course-level progression;
2. independent chapters expand concurrently;
3. a chapter with many sections expands in bounded sequential batches;
4. local code assembles the only official outline.

No function in this module calls a model.  Total course size is not a product
limit; only the amount of work assigned to one model request is bounded.
"""

from __future__ import annotations

import math
import os
import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from course_versioning import stable_hash


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _clip(value: Any, max_chars: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= max_chars:
        return text
    return text[: max(1, max_chars - 1)] + "…"


def _planning_stages(value: Any) -> list[str]:
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, (list, tuple)):
        values = value
    else:
        values = []
    result: list[str] = []
    for item in values:
        stage = _clip(item, 80)
        if stage and stage not in result:
            result.append(stage)
    return result


@dataclass(frozen=True)
class CourseOutlinePlanningBudget:
    """Per-unit outline execution settings, never a total-course ceiling."""

    batch_max_sections: int = 6
    # Legacy names retained for callers. There is no whole-outline deadline;
    # the per-unit value means continuous stream inactivity.
    batch_timeout_seconds: int = 90
    total_timeout_seconds: int = 0

    @classmethod
    def from_env(cls) -> CourseOutlinePlanningBudget:
        return cls(
            batch_max_sections=_env_int(
                "COURSE_OUTLINE_BATCH_MAX_SECTIONS",
                6,
                minimum=2,
                maximum=8,
            ),
            batch_timeout_seconds=_env_int(
                "COURSE_OUTLINE_INACTIVITY_TIMEOUT_SECONDS",
                90,
                minimum=30,
                maximum=600,
            ),
            total_timeout_seconds=0,
        )


def outline_request_fingerprint(
    *,
    topic: str,
    audience: str,
    brief: dict[str, Any],
    difficulty_profile: dict[str, Any],
) -> str:
    """Identify whether a persisted outline checkpoint still matches the request."""
    # ``brief_id`` identifies one compilation event and is intentionally
    # regenerated. It must not invalidate semantically identical outline
    # checkpoints during resume.
    stable_brief = {
        key: value
        for key, value in brief.items()
        if key != "brief_id"
    }
    return stable_hash(
        {
            "topic": topic,
            "audience": audience,
            "brief": stable_brief,
            "difficulty_profile": difficulty_profile,
        },
        prefix="outline_request_",
    )


def normalize_outline_skeleton(
    payload: dict[str, Any],
    *,
    topic: str,
    request_fingerprint: str,
) -> dict[str, Any]:
    chapters: list[dict[str, Any]] = []
    for index, raw in enumerate(payload.get("chapters") or [], start=1):
        if not isinstance(raw, dict):
            continue
        section_count = _positive_int(raw.get("section_count"))
        chapters.append({
            "chapter_number": index,
            "title": _clip(raw.get("title") or f"第 {index} 章", 120),
            "planning_stages": _planning_stages(
                raw.get("planning_stages") or raw.get("planning_stage")
            ),
            "learning_focus": _clip(
                raw.get("learning_focus")
                or f"完成{topic}的第 {index} 阶段学习任务",
                220,
            ),
            "learning_path_role": _learning_path_role(
                raw.get("learning_path_role")
            ),
            "path_reason": _clip(
                raw.get("path_reason") or "课程主路径",
                240,
            ),
            "section_count": section_count or 0,
        })
    raw_spine = payload.get("course_spine")
    raw_spine = raw_spine if isinstance(raw_spine, dict) else {}
    spine_mode = str(raw_spine.get("mode") or "connected_examples").strip()
    if spine_mode not in {
        "shared_anchor", "connected_examples", "independent_sections",
    }:
        spine_mode = "connected_examples"
    course_spine = {
        "mode": spine_mode,
        "title": _clip(
            raw_spine.get("title") or f"{topic}的全课核心问题",
            160,
        ),
        "central_question": _clip(
            raw_spine.get("central_question")
            or f"学习者怎样逐步形成并验证对{topic}的完整理解？",
            280,
        ),
        "fixed_facts": [
            _clip(item, 220)
            for item in raw_spine.get("fixed_facts") or []
            if str(item or "").strip()
        ][:16],
        "allowed_variations": [
            _clip(item, 220)
            for item in raw_spine.get("allowed_variations") or []
            if str(item or "").strip()
        ][:12],
        "final_artifact": _clip(
            raw_spine.get("final_artifact")
            or payload.get("positioning")
            or f"一份可检查的{topic}学习成果",
            240,
        ),
        "continuity_rule": _clip(
            raw_spine.get("continuity_rule")
            or "围绕同一核心问题递进；每节若使用新例子必须明确说明，不得伪造共享数据。",
            280,
        ),
        "required_closures": [
            {
                "closure_id": _clip(
                    item.get("closure_id") or f"CLOSURE-{index}",
                    64,
                ),
                "requirement": _clip(item.get("requirement"), 240),
                "target_node_id": _clip(item.get("target_node_id"), 64),
                "evidence": _clip(item.get("evidence"), 240),
            }
            for index, item in enumerate(
                raw_spine.get("required_closures") or [],
                start=1,
            )
            if isinstance(item, dict)
            and str(item.get("requirement") or "").strip()
        ][:16],
    }
    skeleton = {
        "schema_version": "course_outline_skeleton_v2",
        "request_fingerprint": request_fingerprint,
        "course_title": _clip(payload.get("course_title") or topic, 160),
        "positioning": _clip(
            payload.get("positioning")
            or f"系统学习{topic}并完成可检查成果",
            280,
        ),
        "learning_objectives": [
            _clip(item, 220)
            for item in payload.get("learning_objectives") or []
            if str(item or "").strip()
        ][:16],
        "prerequisites": [
            _clip(item, 160)
            for item in payload.get("prerequisites") or []
            if str(item or "").strip()
        ][:16],
        "course_spine": course_spine,
        "chapters": chapters,
    }
    if not skeleton["learning_objectives"]:
        skeleton["learning_objectives"] = [
            f"能够解释并应用{topic}的核心方法",
        ]
    skeleton["revision_id"] = stable_hash(
        skeleton,
        prefix="outline_skeleton_",
    )
    return skeleton


def validate_outline_skeleton(
    skeleton: dict[str, Any],
    *,
    shape_constraints: dict[str, Any],
    request_fingerprint: str,
    course_type_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    chapters = [
        item
        for item in skeleton.get("chapters") or []
        if isinstance(item, dict)
    ]
    if skeleton.get("request_fingerprint") != request_fingerprint:
        issues.append(_issue(
            "outline_skeleton:stale_request",
            "章节骨架不属于当前课程需求修订",
        ))
    if not chapters:
        issues.append(_issue(
            "outline_skeleton:missing_chapters",
            "章节骨架没有返回可扩展章节",
        ))
    invalid_counts = [
        int(item.get("chapter_number") or index)
        for index, item in enumerate(chapters, start=1)
        if not _positive_int(item.get("section_count"))
    ]
    if invalid_counts:
        issues.append(_issue(
            "outline_skeleton:invalid_section_counts",
            f"章节 {invalid_counts} 没有合法的小节数量",
        ))
    course_spine = skeleton.get("course_spine") or {}
    if (
        course_spine.get("mode") == "shared_anchor"
        and not course_spine.get("fixed_facts")
    ):
        issues.append(_issue(
            "outline_skeleton:shared_anchor_without_fixed_facts",
            "共享案例主轴没有冻结任何事实，后续并行小节会产生数据漂移",
        ))
    valid_section_ids = {
        f"L2-{chapter_index}-{section_index}"
        for chapter_index, chapter in enumerate(chapters, start=1)
        for section_index in range(
            1,
            int(chapter.get("section_count") or 0) + 1,
        )
    }
    closures = [
        item
        for item in course_spine.get("required_closures") or []
        if isinstance(item, dict)
    ]
    closure_ids = [
        str(item.get("closure_id") or "").strip()
        for item in closures
    ]
    if len(set(closure_ids)) != len(closure_ids):
        issues.append(_issue(
            "outline_skeleton:duplicate_closure_id",
            "全课必须闭环的义务使用了重复 ID",
        ))
    invalid_closures = [
        str(item.get("closure_id") or "未命名闭环")
        for item in closures
        if (
            not str(item.get("evidence") or "").strip()
            or str(item.get("target_node_id") or "").strip()
            not in valid_section_ids
        )
    ]
    if invalid_closures:
        issues.append(_issue(
            "outline_skeleton:invalid_closure_target",
            f"全课闭环缺少证据或目标小节无效：{invalid_closures}",
        ))
    expected_chapters = _positive_int(shape_constraints.get("chapter_count"))
    expected_sections = _positive_int(shape_constraints.get("section_count"))
    minimum_chapters = _positive_int(
        shape_constraints.get("minimum_chapter_count")
    )
    minimum_sections = _positive_int(
        shape_constraints.get("minimum_section_count")
    )
    actual_sections = sum(
        int(item.get("section_count") or 0)
        for item in chapters
    )
    if expected_chapters is not None and len(chapters) != expected_chapters:
        issues.append(_issue(
            "outline_skeleton:chapter_count_mismatch",
            f"用户要求 {expected_chapters} 章，骨架实际为 {len(chapters)} 章",
        ))
    if expected_sections is not None and actual_sections != expected_sections:
        issues.append(_issue(
            "outline_skeleton:section_count_mismatch",
            f"用户要求 {expected_sections} 节，骨架实际分配 {actual_sections} 节",
        ))
    if expected_chapters is None and minimum_chapters is not None and len(chapters) < minimum_chapters:
        issues.append(_issue(
            "outline_skeleton:below_complete_chapter_minimum",
            f"完整课程至少需要 {minimum_chapters} 章，骨架实际为 {len(chapters)} 章",
        ))
    if expected_sections is None and minimum_sections is not None and actual_sections < minimum_sections:
        issues.append(_issue(
            "outline_skeleton:below_complete_section_minimum",
            f"完整课程至少需要 {minimum_sections} 节，骨架实际分配 {actual_sections} 节",
        ))
    if (
        expected_chapters is not None
        and expected_sections is not None
        and expected_sections < expected_chapters
    ):
        issues.append(_issue(
            "outline_skeleton:inconsistent_shape",
            "小节总数少于章节数，无法保证每章至少包含一个可学习小节",
        ))
    required_stages = [
        str(item.get("id") or "").strip()
        for item in (course_type_contract or {}).get("required_planning_stages") or []
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    ]
    if required_stages and chapters:
        chapter_stages = [
            _planning_stages(
                item.get("planning_stages") or item.get("planning_stage")
            )
            for item in chapters
        ]
        actual_stages = [
            stage
            for stages in chapter_stages
            for stage in stages
        ]
        missing_stages = [
            stage for stage in required_stages if stage not in actual_stages
        ]
        unknown_stages = [
            stage for stage in actual_stages
            if stage and stage not in required_stages
        ]
        if any(not stages for stages in chapter_stages):
            issues.append(_issue(
                "outline_skeleton:missing_planning_stage",
                "专用课程规划器要求每章声明 planning_stages",
            ))
        if missing_stages:
            issues.append(_issue(
                "outline_skeleton:incomplete_planning_stages",
                f"课程骨架缺少必要规划阶段：{missing_stages}",
            ))
        if unknown_stages:
            issues.append(_issue(
                "outline_skeleton:unknown_planning_stage",
                f"课程骨架包含未知规划阶段：{unknown_stages}",
            ))
        known_positions = [
            required_stages.index(stage)
            for stage in actual_stages
            if stage in required_stages
        ]
        if known_positions != sorted(known_positions):
            issues.append(_issue(
                "outline_skeleton:planning_stage_order_mismatch",
                "课程骨架的规划阶段顺序不符合课程类型合同",
            ))
    return {
        "schema_version": "course_outline_skeleton_validation_v2",
        "passed": not issues,
        "issues": issues,
        "actual": {
            "chapter_count": len(chapters),
            "section_count": actual_sections,
        },
    }


def build_outline_batch_specs(
    skeleton: dict[str, Any],
    budget: CourseOutlinePlanningBudget,
) -> list[dict[str, Any]]:
    """Split each chapter into ordered units while allowing chapters to run in parallel."""
    chapters = [
        item
        for item in skeleton.get("chapters") or []
        if isinstance(item, dict)
    ]
    specs: list[dict[str, Any]] = []
    for chapter_index, chapter in enumerate(chapters, start=1):
        count = max(0, int(chapter.get("section_count") or 0))
        batch_count = math.ceil(count / budget.batch_max_sections) if count else 0
        previous_chapter_count = (
            int(chapters[chapter_index - 2].get("section_count") or 0)
            if chapter_index > 1
            else 0
        )
        for batch_index, start in enumerate(
            range(1, count + 1, budget.batch_max_sections),
            start=1,
        ):
            end = min(count, start + budget.batch_max_sections - 1)
            specs.append({
                "batch_id": (
                    f"OUT-C{chapter_index:03d}-B{batch_index:03d}"
                ),
                "chapter_number": chapter_index,
                "chapter_batch_index": batch_index,
                "chapter_batch_count": batch_count,
                "start_section_index": start,
                "end_section_index": end,
                "section_count": end - start + 1,
                "chapter_section_count": count,
                "expected_node_ids": [
                    f"L2-{chapter_index}-{section_index}"
                    for section_index in range(start, end + 1)
                ],
                "previous_chapter_anchor_id": (
                    f"L2-{chapter_index - 1}-{previous_chapter_count}"
                    if previous_chapter_count
                    else None
                ),
                "required_closure_ids": [
                    str(item.get("closure_id") or "")
                    for item in (
                        (skeleton.get("course_spine") or {}).get(
                            "required_closures"
                        ) or []
                    )
                    if isinstance(item, dict)
                    and str(item.get("target_node_id") or "") in {
                        f"L2-{chapter_index}-{section_index}"
                        for section_index in range(start, end + 1)
                    }
                    and str(item.get("closure_id") or "")
                ],
                "required_closure_targets": {
                    str(item.get("closure_id") or ""): str(
                        item.get("target_node_id") or ""
                    )
                    for item in (
                        (skeleton.get("course_spine") or {}).get(
                            "required_closures"
                        ) or []
                    )
                    if isinstance(item, dict)
                    and str(item.get("target_node_id") or "") in {
                        f"L2-{chapter_index}-{section_index}"
                        for section_index in range(start, end + 1)
                    }
                    and str(item.get("closure_id") or "")
                },
            })
    return specs


def normalize_outline_batch(
    payload: dict[str, Any],
    *,
    spec: dict[str, Any],
    skeleton_revision_id: str,
) -> dict[str, Any]:
    chapter_number = int(spec.get("chapter_number") or 1)
    start_index = int(spec.get("start_section_index") or 1)
    sections: list[dict[str, Any]] = []
    for offset, raw in enumerate(payload.get("sections") or []):
        if not isinstance(raw, dict):
            continue
        section_index = start_index + offset
        raw_progression = raw.get("spine_progression")
        raw_progression = (
            raw_progression if isinstance(raw_progression, dict) else {}
        )
        sections.append({
            "node_id": f"L2-{chapter_number}-{section_index}",
            "section_number": f"{chapter_number}.{section_index}",
            "title": _clip(
                raw.get("title")
                or f"学习任务 {chapter_number}.{section_index}",
                140,
            ),
            "learning_objective": _clip(
                raw.get("learning_objective")
                or f"完成第 {chapter_number}.{section_index} 节的可检查任务",
                240,
            ),
            "prerequisite_node_ids": [
                str(item)
                for item in raw.get("prerequisite_node_ids") or []
                if str(item or "").strip()
            ][:8],
            "assessment": [
                _clip(item, 180)
                for item in raw.get("assessment") or []
                if str(item or "").strip()
            ][:8],
            "scope_boundary": _clip(
                raw.get("scope_boundary")
                or "只覆盖当前小节的学习责任，不提前展开后续内容",
                240,
            ),
            "learning_path_role": _learning_path_role(
                raw.get("learning_path_role")
            ),
            "path_reason": _clip(
                raw.get("path_reason") or "课程主路径",
                240,
            ),
            "spine_progression": {
                "role": _clip(
                    raw_progression.get("role") or "advance",
                    48,
                ),
                "action": _clip(
                    raw_progression.get("action")
                    or raw.get("learning_objective")
                    or f"完成第 {chapter_number}.{section_index} 节的主轴推进",
                    240,
                ),
                "student_artifact": _clip(
                    raw_progression.get("student_artifact")
                    or next(iter(raw.get("assessment") or []), ""),
                    220,
                ),
                "handoff": _clip(
                    raw_progression.get("handoff")
                    or "只交付本节已经明确完成的结论或学习成果",
                    240,
                ),
                "variation": _clip(raw_progression.get("variation"), 220),
                "closure_ids": [
                    _clip(item, 64)
                    for item in raw_progression.get("closure_ids") or []
                    if str(item or "").strip()
                ][:12],
            },
        })
    for section in sections:
        if not section["assessment"]:
            section["assessment"] = [
                f"完成一项可检查的「{section['title']}」学习任务",
            ]
    batch = {
        "schema_version": "course_outline_batch_v2",
        "batch_id": str(spec.get("batch_id") or ""),
        "skeleton_revision_id": skeleton_revision_id,
        "chapter_number": chapter_number,
        "sections": sections,
    }
    batch["revision_id"] = stable_hash(batch, prefix="outline_batch_")
    return batch


def validate_outline_batch(
    batch: dict[str, Any],
    *,
    spec: dict[str, Any],
    skeleton_revision_id: str,
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    sections = [
        item
        for item in batch.get("sections") or []
        if isinstance(item, dict)
    ]
    expected_ids = list(spec.get("expected_node_ids") or [])
    actual_ids = [str(item.get("node_id") or "") for item in sections]
    if batch.get("skeleton_revision_id") != skeleton_revision_id:
        issues.append(_issue(
            "outline_batch:stale_skeleton",
            "目录批次引用了旧章节骨架",
        ))
    if actual_ids != expected_ids:
        issues.append(_issue(
            "outline_batch:section_order_mismatch",
            f"目录批次应返回 {expected_ids}，实际为 {actual_ids}",
        ))
    position = {
        node_id: index
        for index, node_id in enumerate(expected_ids)
    }
    previous_anchor = str(
        spec.get("previous_chapter_anchor_id") or ""
    )
    expected_closure_ids = {
        str(item)
        for item in spec.get("required_closure_ids") or []
        if str(item or "").strip()
    }
    actual_closure_ids: set[str] = set()
    actual_closure_targets: dict[str, list[str]] = {}
    for section in sections:
        node_id = str(section.get("node_id") or "")
        actual_closure_ids.update(
            str(item)
            for item in (
                (section.get("spine_progression") or {}).get("closure_ids")
                or []
            )
            if str(item or "").strip()
        )
        for closure_id in (
            (section.get("spine_progression") or {}).get("closure_ids")
            or []
        ):
            closure_id = str(closure_id or "").strip()
            if closure_id:
                actual_closure_targets.setdefault(closure_id, []).append(
                    node_id
                )
        if not str(section.get("title") or "").strip():
            issues.append(_issue(
                "outline_batch:missing_title",
                f"{node_id} 缺少小节名称",
            ))
        if not str(section.get("learning_objective") or "").strip():
            issues.append(_issue(
                "outline_batch:missing_objective",
                f"{node_id} 缺少可观察学习目标",
            ))
        for dependency in section.get("prerequisite_node_ids") or []:
            dependency = str(dependency)
            local_is_earlier = (
                dependency in position
                and position[dependency] < position.get(node_id, -1)
            )
            prior_batch_pattern = (
                dependency.startswith(
                    f"L2-{int(spec.get('chapter_number') or 1)}-"
                )
                and _section_index(dependency)
                < _section_index(node_id)
            )
            if not (
                local_is_earlier
                or prior_batch_pattern
                or (previous_anchor and dependency == previous_anchor)
            ):
                issues.append(_issue(
                    "outline_batch:invalid_prerequisite",
                    f"{node_id} 引用了当前批次不可用的前置小节 {dependency}",
                ))
    if actual_closure_ids != expected_closure_ids:
        issues.append(_issue(
            "outline_batch:closure_assignment_mismatch",
            (
                f"当前批次必须闭环 {sorted(expected_closure_ids)}，"
                f"实际声明 {sorted(actual_closure_ids)}"
            ),
        ))
    expected_closure_targets = {
        str(closure_id): str(target_id)
        for closure_id, target_id in (
            spec.get("required_closure_targets") or {}
        ).items()
    }
    target_mismatches = [
        closure_id
        for closure_id, target_id in expected_closure_targets.items()
        if actual_closure_targets.get(closure_id) != [target_id]
    ]
    if target_mismatches:
        issues.append(_issue(
            "outline_batch:closure_target_mismatch",
            f"全课闭环没有分配给指定小节：{target_mismatches}",
        ))
    return {
        "schema_version": "course_outline_batch_validation_v2",
        "passed": not issues,
        "issues": issues,
        "actual": {"section_count": len(sections)},
    }


def compile_fallback_outline_batch(
    *,
    spec: dict[str, Any],
    chapter: dict[str, Any],
    skeleton_revision_id: str,
) -> dict[str, Any]:
    start = int(spec.get("start_section_index") or 1)
    end = int(spec.get("end_section_index") or start)
    chapter_number = int(spec.get("chapter_number") or 1)
    title = str(chapter.get("title") or f"第 {chapter_number} 章")
    focus = str(chapter.get("learning_focus") or title)
    previous_anchor = str(spec.get("previous_chapter_anchor_id") or "")
    sections: list[dict[str, Any]] = []
    for section_index in range(start, end + 1):
        node_id = f"L2-{chapter_number}-{section_index}"
        dependency = ""
        if section_index > 1:
            dependency = f"L2-{chapter_number}-{section_index - 1}"
        elif previous_anchor:
            dependency = previous_anchor
        sections.append({
            "node_id": node_id,
            "section_number": f"{chapter_number}.{section_index}",
            "title": f"{title}：学习任务 {section_index}",
            "learning_objective": (
                f"围绕“{focus}”完成第 {section_index} 个可观察学习任务"
            ),
            "prerequisite_node_ids": [dependency] if dependency else [],
            "assessment": [
                f"提交并说明第 {chapter_number}.{section_index} 节的应用结果",
            ],
            "scope_boundary": (
                f"只完成“{focus}”在第 {section_index} 个任务中的责任，"
                "不提前替代后续小节"
            ),
            "learning_path_role": _learning_path_role(
                chapter.get("learning_path_role")
            ),
            "path_reason": str(
                chapter.get("path_reason") or "课程主路径"
            ),
            "spine_progression": {
                "role": "advance",
                "action": f"完成第 {chapter_number}.{section_index} 节的主轴推进",
                "student_artifact": (
                    f"第 {chapter_number}.{section_index} 节可检查结果"
                ),
                "handoff": "只交付本节已经完成的结论或未决项",
                "variation": "",
                "closure_ids": [
                    str(item)
                    for item in spec.get("required_closure_ids") or []
                    if str(
                        (spec.get("required_closure_targets") or {}).get(item)
                        or ""
                    ) == node_id
                ],
            },
        })
    return normalize_outline_batch(
        {"sections": sections},
        spec=spec,
        skeleton_revision_id=skeleton_revision_id,
    )


def assemble_course_outline(
    *,
    skeleton: dict[str, Any],
    batch_specs: list[dict[str, Any]],
    batches: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    specs_by_chapter: dict[int, list[dict[str, Any]]] = {}
    for spec in batch_specs:
        specs_by_chapter.setdefault(
            int(spec.get("chapter_number") or 0),
            [],
        ).append(spec)
    chapters: list[dict[str, Any]] = []
    for chapter in skeleton.get("chapters") or []:
        if not isinstance(chapter, dict):
            continue
        chapter_number = int(chapter.get("chapter_number") or len(chapters) + 1)
        sections: list[dict[str, Any]] = []
        for spec in sorted(
            specs_by_chapter.get(chapter_number, []),
            key=lambda item: int(item.get("start_section_index") or 0),
        ):
            batch = batches.get(str(spec.get("batch_id") or "")) or {}
            sections.extend(
                deepcopy(item)
                for item in batch.get("sections") or []
                if isinstance(item, dict)
            )
        chapters.append({
            "chapter_number": chapter_number,
            "title": str(chapter.get("title") or f"第 {chapter_number} 章"),
            "planning_stages": _planning_stages(
                chapter.get("planning_stages") or chapter.get("planning_stage")
            ),
            "learning_focus": str(
                chapter.get("learning_focus") or chapter.get("title") or ""
            ),
            "learning_path_role": _learning_path_role(
                chapter.get("learning_path_role")
            ),
            "path_reason": str(
                chapter.get("path_reason") or "课程主路径"
            ),
            "sections": sections,
        })
    return {
        "course_title": str(skeleton.get("course_title") or ""),
        "positioning": str(skeleton.get("positioning") or ""),
        "learning_objectives": list(
            skeleton.get("learning_objectives") or []
        ),
        "prerequisites": list(skeleton.get("prerequisites") or []),
        "course_spine": deepcopy(skeleton.get("course_spine") or {}),
        "chapters": chapters,
    }


def outline_neighbor_chapters(
    skeleton: dict[str, Any],
    chapter_number: int,
) -> list[dict[str, Any]]:
    """Expose only the adjacent chapter contracts, not the whole course payload."""
    return [
        deepcopy(item)
        for item in skeleton.get("chapters") or []
        if isinstance(item, dict)
        and abs(int(item.get("chapter_number") or 0) - chapter_number) <= 1
    ]


def select_chapter_evidence_hints(
    artifacts: dict[str, Any],
    chapter: dict[str, Any],
    *,
    max_items: int = 4,
) -> list[dict[str, str]]:
    """Select a tiny chapter-local evidence index without rebroadcasting files."""
    query = " ".join([
        str(chapter.get("title") or ""),
        str(chapter.get("learning_focus") or ""),
    ])
    query_tokens = set(_keywords(query))
    ranked: list[tuple[float, dict[str, Any]]] = []
    for item in artifacts.get("evidence_catalog") or []:
        if not isinstance(item, dict):
            continue
        item_tokens = {
            str(token).lower()
            for token in item.get("keywords") or []
        }
        overlap = len(query_tokens & item_tokens)
        score = float(overlap)
        if item.get("priority") == "core":
            score += 0.4
        if item.get("authority") == "primary":
            score += 0.2
        if score > 0:
            ranked.append((score, item))
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    return [
        {
            "evidence_id": str(item.get("evidence_id") or ""),
            "kind": str(item.get("kind") or ""),
            "summary": _clip(
                item.get("summary") or item.get("source_text") or "",
                180,
            ),
        }
        for _score, item in ranked[:max_items]
    ]


def _keywords(text: str) -> list[str]:
    english = re.findall(r"[A-Za-z][A-Za-z0-9_+-]{1,30}", text.lower())
    chinese_groups = re.findall(r"[\u4e00-\u9fff]{2,20}", text)
    chinese: list[str] = []
    for group in chinese_groups:
        chinese.append(group)
        for width in (2, 3, 4):
            chinese.extend(
                group[index:index + width]
                for index in range(max(0, len(group) - width + 1))
            )
    return list(dict.fromkeys([*english, *chinese]))[:32]


def _section_index(node_id: str) -> int:
    try:
        return int(str(node_id).rsplit("-", 1)[-1])
    except (TypeError, ValueError):
        return -1


def _learning_path_role(value: Any) -> str:
    role = str(value or "").strip()
    if role in {
        "focus",
        "standard",
        "compressed",
        "verify_in_project",
        "milestone",
    }:
        return role
    return "standard"


def _issue(code: str, message: str) -> dict[str, str]:
    return {
        "code": code,
        "severity": "critical",
        "message": message,
    }


__all__ = [
    "CourseOutlinePlanningBudget",
    "assemble_course_outline",
    "build_outline_batch_specs",
    "compile_fallback_outline_batch",
    "normalize_outline_batch",
    "normalize_outline_skeleton",
    "outline_neighbor_chapters",
    "outline_request_fingerprint",
    "select_chapter_evidence_hints",
    "validate_outline_batch",
    "validate_outline_skeleton",
]
