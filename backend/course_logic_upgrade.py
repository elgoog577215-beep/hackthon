"""Promote migrated course metadata into the official course-logic contracts."""

from __future__ import annotations

import re
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from course_coherence import compile_course_coherence_contract
from course_generation_workflow import normalize_course_teaching_plan
from course_knowledge_base import (
    bind_course_knowledge_base_to_map,
    compile_course_knowledge_base,
)
from course_knowledge_map import compile_course_knowledge_map
from course_pedagogy import (
    attach_module_plans_to_plan,
    coerce_persisted_profile,
)
from slide_story_plan import course_supports_slide_deck_v4


class CourseLogicUpgradeError(ValueError):
    """Raised when existing course semantics are insufficient for safe promotion."""


def compile_course_logic_upgrade(course_data: dict[str, Any]) -> dict[str, Any]:
    """Compile missing V4 inputs without changing the canonical course document."""
    if course_supports_slide_deck_v4(course_data):
        return {
            "already_ready": True,
            "updates": {},
            "summary": _summary(course_data),
        }

    sections = [
        _normalize_legacy_section_semantics(node)
        for node in course_data.get("nodes") or []
        if int(node.get("node_level") or 1) == 2
    ]
    issues = _promotion_issues(sections)
    if issues:
        raise CourseLogicUpgradeError("; ".join(issues))
    pedagogy_profile = coerce_persisted_profile(course_data)
    pedagogy_plan = attach_module_plans_to_plan(
        {
            "chapters": [{
                "title": str(course_data.get("course_name") or ""),
                "sections": [
                    {
                        **deepcopy(section),
                        "title": str(
                            section.get("title")
                            or section.get("node_name")
                            or ""
                        ),
                        "key_points": _strings(section.get("key_points"))
                        or _knowledge_names(section),
                    }
                    for section in sections
                ],
            }],
        },
        pedagogy_profile,
    )
    sections = pedagogy_plan["chapters"][0]["sections"]
    recovered_section_count = sum(
        bool(section.get("_course_logic_recovered"))
        for section in sections
    )
    strategy = (
        "legacy_content_recovery_v1"
        if recovered_section_count
        else "legacy_content_promotion_v1"
    )

    teaching_plan = normalize_course_teaching_plan({
        "schema_version": "course_teaching_plan_v2",
        "source_outline_revision_id": str(
            course_data.get("course_document_revision")
            or course_data.get("course_revision")
            or ""
        ),
        "sections": [
            {
                "node_id": str(section.get("node_id") or ""),
                "knowledge_structure": deepcopy(
                    section.get("knowledge_structure") or []
                ),
                "key_points": _strings(section.get("key_points"))
                or _knowledge_names(section),
                "reused_knowledge_names": _strings(
                    section.get("reused_knowledge_names")
                ),
                "knowledge_relations": deepcopy(
                    section.get("knowledge_relations") or []
                ),
                "teaching_modules": _teaching_modules(section),
            }
            for section in sections
        ],
    })
    knowledge_point_count = sum(
        len(_knowledge_names(section))
        for section in teaching_plan["sections"]
    )
    teaching_module_count = sum(
        len(section.get("teaching_modules") or [])
        for section in teaching_plan["sections"]
    )

    working = deepcopy(course_data)
    normalized_sections = {
        str(section.get("node_id") or ""): section
        for section in sections
    }
    for node in working.get("nodes") or []:
        normalized = normalized_sections.get(str(node.get("node_id") or ""))
        if normalized is not None:
            node["learning_objective"] = str(
                normalized.get("learning_objective") or ""
            )
            node["knowledge_structure"] = deepcopy(
                normalized.get("knowledge_structure") or []
            )
    working["course_teaching_plan"] = teaching_plan
    working["subject_pedagogy_profile"] = deepcopy(
        pedagogy_plan["subject_pedagogy_profile"]
    )
    working["course_module_plan"] = deepcopy(
        pedagogy_plan["course_module_plan"]
    )
    working["pedagogy_quality_contract"] = deepcopy(
        pedagogy_plan["pedagogy_quality_contract"]
    )
    stage_artifacts = deepcopy(working.get("generation_stage_artifacts") or {})
    stage_artifacts["course_teaching_plan"] = {
        "schema_version": teaching_plan["schema_version"],
        "status": "completed",
        "semantic_status": (
            "legacy_content_recovered"
            if recovered_section_count
            else "legacy_promoted"
        ),
        "strategy": strategy,
        "revision_id": teaching_plan["revision_id"],
        "section_count": len(teaching_plan["sections"]),
        "recovered_section_count": recovered_section_count,
        "knowledge_point_count": knowledge_point_count,
        "teaching_module_count": teaching_module_count,
    }
    working["generation_stage_artifacts"] = stage_artifacts

    course_map = compile_course_knowledge_map(working)
    knowledge_base = compile_course_knowledge_base(
        working,
        course_map=course_map,
    )
    if (
        knowledge_base.get("lifecycle_status") != "active"
        or not (knowledge_base.get("quality_report") or {}).get("passed", False)
    ):
        raise CourseLogicUpgradeError(
            "现有课程内容未通过知识库完整性检查"
        )
    course_map = bind_course_knowledge_base_to_map(course_map, knowledge_base)
    working["course_knowledge_map"] = course_map
    working["course_knowledge_base"] = knowledge_base

    coherence_contract = compile_course_coherence_contract(working)
    if (
        coherence_contract.get("status") != "active"
        or not (coherence_contract.get("quality_report") or {}).get("passed", False)
    ):
        issue_codes = [
            str(item.get("code") or "")
            for item in (
                (coherence_contract.get("quality_report") or {}).get("issues")
                or []
            )
            if item.get("blocking")
        ]
        raise CourseLogicUpgradeError(
            "现有课程结构未通过课程一致性检查"
            + (f": {', '.join(issue_codes)}" if issue_codes else "")
        )
    working["course_coherence_contract"] = coherence_contract
    if not course_supports_slide_deck_v4(working):
        raise CourseLogicUpgradeError(
            "补全后的课程逻辑仍未满足 V4 课件生成条件"
        )

    completed_at = datetime.now(timezone.utc).isoformat()
    stage_artifacts["course_logic_upgrade"] = {
        "schema_version": "course_logic_upgrade_v1",
        "status": "completed",
        "strategy": strategy,
        "completed_at": completed_at,
        "recovered_section_count": recovered_section_count,
        "source_document_revision": str(
            course_data.get("course_document_revision") or ""
        ),
        "teaching_plan_revision_id": teaching_plan["revision_id"],
        "knowledge_base_revision_id": knowledge_base["revision_id"],
        "coherence_contract_revision_id": coherence_contract["revision_id"],
    }
    updates = {
        "subject_pedagogy_profile": deepcopy(
            working["subject_pedagogy_profile"]
        ),
        "course_module_plan": deepcopy(working["course_module_plan"]),
        "pedagogy_quality_contract": deepcopy(
            working["pedagogy_quality_contract"]
        ),
        "course_teaching_plan": teaching_plan,
        "course_knowledge_map": course_map,
        "course_knowledge_base": knowledge_base,
        "course_knowledge_base_quality_report": deepcopy(
            knowledge_base.get("quality_report") or {}
        ),
        "course_coherence_contract": coherence_contract,
        "course_coherence_quality_report": deepcopy(
            coherence_contract.get("quality_report") or {}
        ),
        "generation_stage_artifacts": stage_artifacts,
    }
    return {
        "already_ready": False,
        "updates": updates,
        "summary": _summary({**working, **updates}),
    }


def _promotion_issues(sections: list[dict[str, Any]]) -> list[str]:
    if not sections:
        return ["课程没有可恢复的二级小节"]
    issues: list[str] = []
    for section in sections:
        label = str(
            section.get("node_name")
            or section.get("node_id")
            or "未知小节"
        )
        if not str(section.get("learning_objective") or "").strip():
            issues.append(f"小节“{label}”缺少学习目标")
        if not _knowledge_names(section):
            issues.append(
                f"小节“{label}”既没有结构化知识点，也没有可恢复的课程正文"
            )
    return issues


def _normalize_legacy_section_semantics(
    raw_section: dict[str, Any],
) -> dict[str, Any]:
    section = deepcopy(raw_section)
    if not str(section.get("learning_objective") or "").strip():
        recovered_objective = _recover_learning_objective(section)
        if recovered_objective:
            section["learning_objective"] = recovered_objective
            section["_course_logic_recovered"] = True
    for group in section.get("knowledge_structure") or []:
        if not isinstance(group, dict):
            continue
        for point in group.get("knowledge_points") or []:
            if not isinstance(point, dict):
                continue
            capabilities = point.get("capability_points") or []
            if not isinstance(capabilities, list):
                capabilities = [capabilities]
            normalized_capabilities = []
            for capability in capabilities:
                if not isinstance(capability, dict):
                    capability = {"name": str(capability or "")}
                item = deepcopy(capability)
                fallback = str(
                    item.get("observable_behavior")
                    or item.get("capability")
                    or item.get("statement")
                    or item.get("description")
                    or item.get("name")
                    or ""
                ).strip()
                if fallback:
                    item.setdefault("name", fallback)
                    item.setdefault("observable_behavior", fallback)
                    normalized_capabilities.append(item)
            if normalized_capabilities:
                point["capability_points"] = normalized_capabilities
    if not _knowledge_names(section):
        recovered = _recover_knowledge_structure(section)
        if recovered:
            section["knowledge_structure"] = recovered
            section["key_points"] = _knowledge_names(section)
            section["_course_logic_recovered"] = True
    return section


def _recover_learning_objective(section: dict[str, Any]) -> str:
    """Recover an objective from existing summary language or a sourced title."""
    markdown = str(section.get("node_content") or "")
    text = re.sub(r"```[\s\S]*?```", " ", markdown)
    text = re.sub(r"!\[[^\]]*]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]+)]\([^)]*\)", r"\1", text)
    text = re.sub(r"[`*_>#|]", "", text)
    text = re.sub(r"\s+", "", text)
    patterns = (
        r"本节(?:主要)?介绍了(?P<object>[^。！？]{4,100})",
        r"本节(?:主要)?讲解了(?P<object>[^。！？]{4,100})",
        r"通过本节(?:的)?学习[^，。！？]*[，,](?:学习者|你)?"
        r"(?:将)?(?:能够|可以)(?P<object>[^。！？]{4,100})",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        recovered = match.group("object").strip("，,；;：: ")
        recovered = re.split(
            r"[，,](?:为|并为|从而为|这为|有助于|是后续)",
            recovered,
            maxsplit=1,
        )[0].strip()
        if recovered:
            return f"能够说明{recovered}"[:160]
    title = re.sub(
        r"^\s*(?:第[一二三四五六七八九十百]+[章节]\s*)?"
        r"\d+(?:\.\d+)*[\s、.．:：-]*",
        "",
        str(section.get("node_name") or "").strip(),
    ).strip()
    if title and _first_substantive_sentence(markdown):
        return (
            f"能够解释“{title}”的核心概念，并依据本节正文分析相关问题"
        )[:160]
    return ""


def _recover_knowledge_structure(
    section: dict[str, Any],
) -> list[dict[str, Any]]:
    objective = str(section.get("learning_objective") or "").strip()
    statement = _first_substantive_sentence(
        str(section.get("node_content") or "")
    )
    title = re.sub(
        r"^\s*(?:第[一二三四五六七八九十百]+[章节]\s*)?"
        r"\d+(?:\.\d+)*[\s、.．:：-]*",
        "",
        str(section.get("node_name") or "").strip(),
    ).strip()
    if not objective or not statement or not title:
        return []
    return [{
        "concept_group": title,
        "description": f"依据本节现有正文恢复的课程知识结构：{title}",
        "knowledge_points": [{
            "name": title,
            "statement": statement,
            "knowledge_type": "principle",
            "conditions": [f"适用于本节“{title}”所界定的课程范围"],
            "boundaries": ["以现有课程正文和学习目标为语义边界"],
            "entry_reason": "由旧课程正文与学习目标恢复",
            "capability": objective,
            "capability_points": [{
                "name": objective,
                "observable_behavior": objective,
            }],
            "mastery_criteria": [{
                "name": f"掌握{title}",
                "observable_performance": objective,
                "required_independence": "independent",
                "required_transfer": "variation",
                "verification_method": "根据课程正文完成解释或应用任务",
            }],
        }],
    }]


def _first_substantive_sentence(markdown: str) -> str:
    text = re.sub(r"```[\s\S]*?```", " ", markdown)
    text = re.sub(r"!\[[^\]]*]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]+)]\([^)]*\)", r"\1", text)
    candidates = []
    for raw_line in text.splitlines():
        if re.match(r"^\s{0,3}#{1,6}\s+", raw_line):
            continue
        if raw_line.lstrip().startswith(("|", ">")):
            continue
        line = re.sub(r"^\s{0,3}#{1,6}\s*", "", raw_line)
        line = re.sub(r"^\s*(?:[-*+]|\d+[.)、])\s*", "", line)
        line = re.sub(r"[`*_>|]", "", line).strip()
        if len(line) >= 12:
            candidates.extend(
                item.strip()
                for item in re.split(r"(?<=[。！？.!?])\s*", line)
                if len(item.strip()) >= 12
            )
    return candidates[0][:320] if candidates else ""


def _teaching_modules(section: dict[str, Any]) -> list[dict[str, Any]]:
    knowledge_names = _knowledge_names(section)
    modules = []
    for index, raw_module in enumerate(section.get("module_plan") or []):
        if not isinstance(raw_module, dict):
            continue
        module_id = str(
            raw_module.get("module_id")
            or raw_module.get("block_id")
            or f"module-{index + 1}"
        ).strip()
        purpose = str(
            raw_module.get("teaching_purpose")
            or raw_module.get("purpose")
            or raw_module.get("output_contract")
            or raw_module.get("label")
            or module_id
        ).strip()
        guidance = str(
            raw_module.get("teaching_guidance")
            or raw_module.get("guidance")
            or raw_module.get("prompt_instruction")
            or raw_module.get("output_contract")
            or purpose
        ).strip()
        modules.append({
            "module_id": module_id,
            "teaching_purpose": purpose,
            "knowledge_names": _strings(raw_module.get("knowledge_names"))
            or knowledge_names,
            "teaching_guidance": guidance,
        })
    if modules:
        return modules
    return [{
        "module_id": "core_explanation",
        "teaching_purpose": str(
            section.get("learning_objective") or "讲解本节核心知识"
        ).strip(),
        "knowledge_names": knowledge_names,
        "teaching_guidance": "依据现有课程正文讲解核心知识并检查理解。",
    }]


def _knowledge_names(section: dict[str, Any]) -> list[str]:
    return _strings([
        point.get("name")
        for group in section.get("knowledge_structure") or []
        if isinstance(group, dict)
        for point in group.get("knowledge_points") or []
        if isinstance(point, dict)
        and str(point.get("name") or "").strip()
        and str(
            point.get("statement")
            or point.get("description")
            or ""
        ).strip()
    ])


def _strings(values: Any) -> list[str]:
    if not isinstance(values, (list, tuple, set)):
        return []
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _summary(course_data: dict[str, Any]) -> dict[str, Any]:
    teaching_plan = course_data.get("course_teaching_plan") or {}
    knowledge_base = course_data.get("course_knowledge_base") or {}
    coherence = course_data.get("course_coherence_contract") or {}
    upgrade_stage = (
        (course_data.get("generation_stage_artifacts") or {})
        .get("course_logic_upgrade")
        or {}
    )
    return {
        "section_count": len(teaching_plan.get("sections") or []),
        "recovered_section_count": int(
            upgrade_stage.get("recovered_section_count") or 0
        ),
        "teaching_plan_revision_id": str(
            teaching_plan.get("revision_id") or ""
        ),
        "knowledge_base_revision_id": str(
            knowledge_base.get("revision_id") or ""
        ),
        "coherence_contract_revision_id": str(
            coherence.get("revision_id") or ""
        ),
    }
