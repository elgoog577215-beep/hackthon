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

from course_type_contracts import (
    COVERAGE_STATUS_COMPLETE,
    judge_course_coverage,
)
from course_versioning import stable_hash


def course_coverage_verdict(
    *,
    subject: str,
    brief: dict[str, Any],
    skeleton: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Judge requested size against subject scope during outline planning.

    Called twice per course: once before the skeleton exists, so the size
    verdict can shape the skeleton prompt, and once after, so the verdict can
    name the topics the frozen skeleton actually left out. The verdict is a
    statement about scope only — it never supplies course content.
    """
    classroom = brief.get("teacher_course_brief") or {}
    shape = brief.get("course_shape_constraints") or {}
    planned_topics: list[str] | None = None
    if skeleton is not None:
        planned_topics = _skeleton_topic_text(skeleton)
    return judge_course_coverage(
        subject=subject,
        class_hours=classroom.get("total_class_hours"),
        # Only a real planned size counts. ``minimum_section_count`` is the
        # product floor for an unsized request, not evidence of capacity.
        section_count=(
            shape.get("section_count")
            or _skeleton_section_count(skeleton)
        ),
        planned_topics=planned_topics,
    )


def _skeleton_topic_text(skeleton: dict[str, Any]) -> list[str]:
    """Collect every chapter-level phrase a topic could be named in."""
    values: list[str] = [
        str(skeleton.get("course_title") or ""),
        str(skeleton.get("positioning") or ""),
    ]
    values.extend(
        str(item) for item in skeleton.get("learning_objectives") or []
    )
    for chapter in skeleton.get("chapters") or []:
        if not isinstance(chapter, dict):
            continue
        values.append(str(chapter.get("title") or ""))
        values.append(str(chapter.get("learning_focus") or ""))
    return [item for item in values if item.strip()]


def _skeleton_section_count(skeleton: dict[str, Any] | None) -> int | None:
    if not isinstance(skeleton, dict):
        return None
    total = sum(
        int(item.get("section_count") or 0)
        for item in skeleton.get("chapters") or []
        if isinstance(item, dict)
    )
    return total or None


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
    coverage_verdict: dict[str, Any] | None = None,
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
    issues.extend(_coverage_honesty_issues(skeleton, coverage_verdict))
    return {
        "schema_version": "course_outline_skeleton_validation_v2",
        "passed": not issues,
        "issues": issues,
        "actual": {
            "chapter_count": len(chapters),
            "section_count": actual_sections,
        },
    }


_COMPLETENESS_CLAIMS = (
    "完整课程",
    "完整覆盖",
    "全面覆盖",
    "完整的课程",
    "系统完整",
    "面面俱到",
)

_COMPLETENESS_NEGATION = re.compile(
    r"(?:并不|并非|不追求|不承担|不承诺|不要求|不能|无法|无需|无须|未|非|不).{0,8}$"
)


def _affirmative_completeness_claims(prose: str) -> list[str]:
    """Return completeness claims that are asserted rather than denied.

    The outline prompt explicitly asks a short course to state what it does not
    cover.  A plain substring check therefore treated honest wording such as
    ``不追求学科完整覆盖`` as the exact overclaim it was denying.  Inspect the
    local prefix of every occurrence so a negative scope boundary passes while
    a real promise like ``完整覆盖全部内容`` remains blocked.
    """
    claims: list[str] = []
    for claim in _COMPLETENESS_CLAIMS:
        for match in re.finditer(re.escape(claim), prose):
            prefix = prose[max(0, match.start() - 12):match.start()]
            if _COMPLETENESS_NEGATION.search(prefix):
                continue
            claims.append(claim)
            break
    return claims


def _coverage_honesty_issues(
    skeleton: dict[str, Any],
    coverage_verdict: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Reject a completeness claim the requested course size cannot support.

    This is the honesty gate: a course that cannot cover its subject may still
    be generated, but it may not describe itself as if it had.
    """
    if not coverage_verdict:
        return []
    if coverage_verdict.get("status") == COVERAGE_STATUS_COMPLETE:
        return []
    if coverage_verdict.get("may_claim_complete_subject"):
        return []
    prose = " ".join([
        str(skeleton.get("course_title") or ""),
        str(skeleton.get("positioning") or ""),
    ])
    claims = _affirmative_completeness_claims(prose)
    if not claims:
        return []
    return [_issue(
        "outline_skeleton:unsupported_completeness_claim",
        f"{coverage_verdict.get('scale_label') or '当前课程规格'}不足以完整覆盖"
        f"{coverage_verdict.get('subject') or '本学科'}，"
        f"课程名称或定位不得包含 {claims}；"
        f"应改为「{coverage_verdict.get('required_positioning') or '核心概览课'}」"
        "并显式列出本次不覆盖的知识点",
    )]


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
    for section in sections:
        node_id = str(section.get("node_id") or "")
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
    "course_coverage_verdict",
    "normalize_outline_batch",
    "normalize_outline_skeleton",
    "outline_neighbor_chapters",
    "outline_request_fingerprint",
    "select_chapter_evidence_hints",
    "validate_outline_batch",
    "validate_outline_skeleton",
]
