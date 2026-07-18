"""Material-backed course generation workflow helpers.

This module is deliberately deterministic. It does not call an LLM; it turns
raw user input into stable intermediate objects that CourseService can pass to
LLM stages and save with the course.
"""

from __future__ import annotations

import re
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from course_difficulty import (
    AdaptationDecision,
    DifficultyGapAssessment,
    DifficultyProfile,
    format_difficulty_profile,
    format_node_difficulty_contract,
)
from course_knowledge_map import normalize_knowledge_structure
from course_pedagogy import SubjectPedagogyProfile
from course_versioning import stable_hash
from material_evidence import build_evidence_catalog_summary, evidence_bundle_for_node

PIPELINE_VERSION = "course_generation_v7"

COURSE_RELATION_TYPES = {
    "prerequisite",
    "derives",
    "equivalent_to",
    "contrasts_with",
    "applies_to",
    "generalizes",
}
SYMMETRIC_COURSE_RELATION_TYPES = {"equivalent_to", "contrasts_with"}
ACYCLIC_COURSE_RELATION_TYPES = {"prerequisite", "generalizes"}

MATERIAL_USAGE_LABELS = {
    "content_source": "正文依据",
    "style_reference": "讲法参考",
    "question_source": "题目来源",
    "supplement": "补充材料",
    "weak_context": "弱背景",
}

MATERIAL_IMPORTANCE_LABELS = {
    "core": "核心资料",
    "supporting": "辅助资料",
    "weak": "弱参考",
}


def build_course_generation_artifacts(
    *,
    course_id: str,
    topic: str,
    difficulty: str,
    style: str,
    requirements: str = "",
    target_audience: str = "大学生",
    materials: list[Any] | None = None,
    learner_profile_summary: str = "",
    prepared_materials: dict[str, Any] | None = None,
    grounding_strategy: str = "material_first",
) -> dict[str, Any]:
    """Build persisted brief and material artifacts without a second task."""
    prepared = prepared_materials or {}
    cards = prepared.get("material_cards") or [
        _build_material_card(index, raw) for index, raw in enumerate(materials or [], start=1)
    ]
    brief = _build_brief(
        topic=topic,
        difficulty=difficulty,
        style=style,
        requirements=requirements,
        target_audience=target_audience,
        material_cards=cards,
        learner_profile_summary=learner_profile_summary,
    )
    artifacts = {
        "pipeline_version": PIPELINE_VERSION,
        "material_cards": cards,
        "course_generation_brief": brief,
        "material_assets": prepared.get("material_assets") or [],
        "material_bindings": prepared.get("material_bindings") or [],
        "parsed_documents": prepared.get("parsed_documents") or [],
        "evidence_catalog": prepared.get("evidence_catalog") or [],
        "evidence_coverage_plan": {
            "plan_version": "evidence_coverage_v1",
            "strategy": grounding_strategy,
            "evidence_count": len(prepared.get("evidence_catalog") or []),
            "asset_coverage": [],
            "conflicts": [],
            "gaps": [],
            "node_contracts": {},
        },
        "artifact_created_at": _utc_now(),
    }
    return artifacts


def attach_pedagogy_profile(
    artifacts: dict[str, Any], profile: SubjectPedagogyProfile
) -> dict[str, Any]:
    artifacts["subject_pedagogy_profile"] = profile.to_dict()
    return artifacts


def attach_difficulty_artifacts(
    artifacts: dict[str, Any],
    *,
    profile: DifficultyProfile,
    gap_assessment: DifficultyGapAssessment,
    adaptation_decision: AdaptationDecision,
) -> dict[str, Any]:
    """将难度编译结果放入同一份持久化生成上下文。"""
    artifacts["difficulty_profile"] = profile.to_dict()
    artifacts["difficulty_gap_assessment"] = gap_assessment.to_dict()
    artifacts["adaptation_decision"] = adaptation_decision.to_dict()
    return artifacts


def normalize_course_outline_contract(plan: dict[str, Any]) -> dict[str, Any]:
    """Normalize the lightweight, user-reviewable course outline.

    Knowledge packages are deliberately absent here.  Later AI stages may enrich
    a section but may not add, remove, or reorder outline sections.
    """
    section_records: list[tuple[dict[str, Any], str, str, int]] = []
    aliases: dict[str, str] = {}
    for chapter_index, chapter in enumerate(plan.get("chapters") or [], start=1):
        chapter["chapter_number"] = chapter_index
        chapter.setdefault("title", f"第{chapter_index}章")
        chapter.setdefault("learning_focus", chapter.get("title", ""))
        for section_index, section in enumerate(chapter.get("sections") or [], start=1):
            raw_number = str(section.get("section_number") or "").strip()
            raw_id = str(section.get("id") or section.get("node_id") or "").strip()
            section_number = f"{chapter_index}.{section_index}"
            canonical = f"L2-{chapter_index}-{section_index}"
            section["section_number"] = section_number
            section["node_id"] = canonical
            section_records.append((section, canonical, section_number, len(section_records)))
            for alias in (
                canonical,
                raw_number,
                raw_id,
                section_number,
                f"L{chapter_index}-{section_index}",
            ):
                if alias:
                    aliases[alias] = canonical

    earlier_ids: set[str] = set()
    for section, canonical, section_number, _index in section_records:
        normalized_dependencies: list[str] = []
        for dependency in section.get("prerequisite_node_ids") or []:
            mapped = aliases.get(str(dependency).strip())
            if mapped and mapped in earlier_ids and mapped not in normalized_dependencies:
                normalized_dependencies.append(mapped)
        section["prerequisite_node_ids"] = normalized_dependencies
        section.setdefault("title", f"小节 {section_number}")
        section["learning_objective"] = str(
            section.get("learning_objective")
            or f"能解释并应用「{section.get('title')}」的核心内容"
        )
        section["assessment"] = section.get("assessment") or [
            f"完成一项可检查的「{section.get('title')}」学习任务"
        ]
        section.setdefault("key_points", [])
        section.setdefault("knowledge_structure", [])
        section.setdefault("reused_knowledge_names", [])
        section.setdefault("misconceptions", [])
        section.setdefault("scope_boundary", f"只覆盖「{section.get('title')}」必需的知识与行动")
        section.setdefault("suggested_module_ids", [])
        section.pop("complexity", None)
        earlier_ids.add(canonical)
    plan.setdefault("knowledge_relations", [])
    plan["outline_schema_version"] = "course_outline_v1"
    return plan


def build_course_knowledge_scope_contract(plan: dict[str, Any]) -> dict[str, Any]:
    """Freeze the whole-course responsibility map before local knowledge packages.

    This contract is deliberately smaller than the final CourseKnowledgeBase.  Its
    job is to make every local generation unit aware of the complete course path,
    including later responsibilities it must not steal.
    """
    sections = [
        {
            "node_id": str(section.get("node_id") or ""),
            "section_number": str(section.get("section_number") or ""),
            "title": str(section.get("title") or ""),
            "learning_objective": str(section.get("learning_objective") or ""),
            "scope_boundary": str(section.get("scope_boundary") or ""),
            "prerequisite_node_ids": list(section.get("prerequisite_node_ids") or []),
        }
        for chapter in plan.get("chapters") or []
        if isinstance(chapter, dict)
        for section in chapter.get("sections") or []
        if isinstance(section, dict)
    ]
    responsibilities = []
    for index, section in enumerate(sections):
        responsibilities.append(
            {
                **deepcopy(section),
                "earlier_section_ids": [
                    item["node_id"] for item in sections[:index] if item["node_id"]
                ],
                "later_reserved_sections": [
                    {
                        "node_id": item["node_id"],
                        "title": item["title"],
                        "learning_objective": item["learning_objective"],
                        "scope_boundary": item["scope_boundary"],
                    }
                    for item in sections[index + 1 :]
                ],
            }
        )
    payload = {
        "schema_version": "course_knowledge_scope_v1",
        "course_title": str(plan.get("course_title") or ""),
        "positioning": str(plan.get("positioning") or ""),
        "learning_objectives": list(plan.get("learning_objectives") or []),
        "prerequisites": list(plan.get("prerequisites") or []),
        "section_responsibilities": responsibilities,
    }
    payload["revision_id"] = stable_hash(payload, prefix="kscope_")
    return payload


def build_section_knowledge_scope_slice(
    contract: dict[str, Any],
    section_id: str,
) -> dict[str, Any]:
    """Return the O(n) context one section needs instead of the O(n²) contract."""
    responsibilities = [
        item
        for item in contract.get("section_responsibilities") or []
        if isinstance(item, dict)
    ]
    current = next(
        (
            deepcopy(item)
            for item in responsibilities
            if str(item.get("node_id") or "") == section_id
        ),
        {},
    )
    course_path = [
        {
            "node_id": str(item.get("node_id") or ""),
            "title": str(item.get("title") or ""),
            "learning_objective": str(item.get("learning_objective") or ""),
            "scope_boundary": str(item.get("scope_boundary") or ""),
            "prerequisite_node_ids": list(
                item.get("prerequisite_node_ids") or []
            ),
        }
        for item in responsibilities
    ]
    payload = {
        "schema_version": "section_knowledge_scope_slice_v1",
        "course_title": str(contract.get("course_title") or ""),
        "positioning": str(contract.get("positioning") or ""),
        "learning_objectives": list(
            contract.get("learning_objectives") or []
        ),
        "current_section_responsibility": current,
        "course_path": course_path,
        "source_contract_revision_id": str(
            contract.get("revision_id") or ""
        ),
    }
    payload["revision_id"] = stable_hash(payload, prefix="kslice_")
    return payload


def normalize_course_knowledge_skeleton(
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Normalize the compact identity plan that makes section calls independent."""
    sections = []
    for item in payload.get("sections") or []:
        if not isinstance(item, dict):
            continue
        sections.append({
            "node_id": str(item.get("node_id") or "").strip(),
            "owned_knowledge_names": _unique_strings(
                item.get("owned_knowledge_names") or []
            ),
            "reused_knowledge_names": _unique_strings(
                item.get("reused_knowledge_names") or []
            ),
        })
    normalized = {
        "schema_version": "course_knowledge_skeleton_v1",
        "source_scope_revision_id": str(
            payload.get("source_scope_revision_id") or ""
        ),
        "sections": sections,
    }
    normalized["revision_id"] = stable_hash(
        normalized,
        prefix="kskeleton_",
    )
    return normalized


def validate_course_knowledge_skeleton(
    payload: dict[str, Any],
    *,
    sections: list[dict[str, Any]],
    locked_knowledge_names_by_section: dict[str, list[str]] | None = None,
    expected_scope_revision_id: str | None = None,
) -> dict[str, Any]:
    """Protect canonical identity before bounded-parallel detail generation."""
    skeleton = normalize_course_knowledge_skeleton(payload)
    expected_ids = [
        str(section.get("node_id") or "")
        for section in sections
        if str(section.get("node_id") or "")
    ]
    expected_positions = {
        section_id: index
        for index, section_id in enumerate(expected_ids)
    }
    actual_ids = [
        str(item.get("node_id") or "")
        for item in skeleton["sections"]
    ]
    issues: list[dict[str, Any]] = []
    if (
        expected_scope_revision_id is not None
        and skeleton.get("source_scope_revision_id")
        != expected_scope_revision_id
    ):
        issues.append(_plan_issue(
            "knowledge_skeleton:stale_scope_revision",
            "知识身份骨架对应的目录责任版本已经过期，必须重新规划",
        ))
    if actual_ids != expected_ids:
        issues.append(_plan_issue(
            "knowledge_skeleton:section_order_mismatch",
            "知识身份骨架必须按目录顺序完整覆盖所有小节",
        ))
    if len(set(actual_ids)) != len(actual_ids):
        issues.append(_plan_issue(
            "knowledge_skeleton:duplicate_section",
            "知识身份骨架包含重复小节",
        ))
    unexpected = sorted(set(actual_ids) - set(expected_ids))
    if unexpected:
        issues.append(_plan_issue(
            "knowledge_skeleton:unknown_section",
            "知识身份骨架引用了目录中不存在的小节",
        ))

    by_section = {
        str(item.get("node_id") or ""): item
        for item in skeleton["sections"]
    }
    owner_by_name: dict[str, str] = {}
    for section_id in expected_ids:
        item = by_section.get(section_id) or {}
        owned = list(item.get("owned_knowledge_names") or [])
        if not owned:
            issues.append(_plan_issue(
                "knowledge_skeleton:missing_owned_knowledge",
                f"小节 {section_id} 没有首次负责的规范知识名称",
            ))
        if len(owned) > 8:
            issues.append(_plan_issue(
                "knowledge_skeleton:too_many_owned_knowledge",
                f"小节 {section_id} 的规范知识名称超过 8 个",
            ))
        for name in owned:
            normalized_name = _normalize_knowledge_name(name)
            if not normalized_name:
                issues.append(_plan_issue(
                    "knowledge_skeleton:blank_knowledge_name",
                    f"小节 {section_id} 包含空知识名称",
                ))
                continue
            existing_owner = owner_by_name.get(normalized_name)
            if existing_owner and existing_owner != section_id:
                issues.append(_plan_issue(
                    "knowledge_skeleton:duplicate_owner",
                    f"规范知识名称「{name}」被多个小节重复首次负责",
                ))
            else:
                owner_by_name[normalized_name] = section_id

    for section_id in expected_ids:
        item = by_section.get(section_id) or {}
        owned = {
            _normalize_knowledge_name(name)
            for name in item.get("owned_knowledge_names") or []
            if _normalize_knowledge_name(name)
        }
        for name in item.get("reused_knowledge_names") or []:
            normalized_name = _normalize_knowledge_name(name)
            owner = owner_by_name.get(normalized_name)
            if normalized_name in owned:
                issues.append(_plan_issue(
                    "knowledge_skeleton:owned_and_reused",
                    f"小节 {section_id} 不能同时首次负责和复用「{name}」",
                ))
            elif not owner:
                issues.append(_plan_issue(
                    "knowledge_skeleton:unknown_reuse",
                    f"小节 {section_id} 复用了尚未定义的「{name}」",
                ))
            elif expected_positions.get(owner, -1) >= expected_positions.get(
                section_id, -1
            ):
                issues.append(_plan_issue(
                    "knowledge_skeleton:future_reuse",
                    f"小节 {section_id} 不能复用后续小节才首次负责的「{name}」",
                ))

    for section_id, locked_names in (
        locked_knowledge_names_by_section or {}
    ).items():
        expected_locked = {
            str(name).strip()
            for name in locked_names
            if str(name).strip()
        }
        actual_locked = {
            str(name).strip()
            for name in (
                by_section.get(section_id) or {}
            ).get("owned_knowledge_names") or []
            if str(name).strip()
        }
        if expected_locked and actual_locked != expected_locked:
            issues.append(_plan_issue(
                "knowledge_skeleton:locked_identity_changed",
                f"小节 {section_id} 已完成知识包的规范名称不得在恢复时改变",
            ))

    return _constraint_report(
        schema_version="course_knowledge_skeleton_validation_v1",
        actual={
            "section_count": len(actual_ids),
            "owned_knowledge_count": sum(
                len(item.get("owned_knowledge_names") or [])
                for item in skeleton["sections"]
            ),
            "reused_knowledge_count": sum(
                len(item.get("reused_knowledge_names") or [])
                for item in skeleton["sections"]
            ),
        },
        expected={"section_ids": expected_ids},
        issues=issues,
    )


def build_section_knowledge_material_context(
    artifacts: dict[str, Any],
    section: dict[str, Any],
) -> str:
    """Keep section knowledge prompts grounded without repeating all materials."""
    evidence = evidence_bundle_for_node(artifacts, section)
    brief = artifacts.get("course_generation_brief") or {}
    strategy = (
        artifacts.get("evidence_coverage_plan") or {}
    ).get("strategy", "material_first")
    parts = [
        f"- 生成目标：{brief.get('goal') or '电子课程资料'}",
        f"- 证据策略：{strategy}",
    ]
    if evidence:
        parts.extend([
            "- 只依据下面与本节绑定的证据规划知识边界：",
            _format_evidence_bundle(evidence),
        ])
    else:
        parts.append(
            "- 当前小节没有绑定可引用证据；不得伪装已读取资料。"
        )
    return "\n".join(parts)


def build_section_knowledge_skeleton_evidence_hints(
    artifacts: dict[str, Any],
    section: dict[str, Any],
) -> list[dict[str, str]]:
    """Give the identity planner compact evidence without rebroadcasting files."""
    return [
        {
            "evidence_id": str(item.get("evidence_id") or ""),
            "kind": str(item.get("kind") or ""),
            "summary": _clip(
                str(item.get("source_text") or ""),
                237,
            ),
        }
        for item in evidence_bundle_for_node(artifacts, section)[:4]
    ]


def normalize_course_plan_contract(plan: dict[str, Any]) -> dict[str, Any]:
    """Normalize a fully enriched plan after all section packages are ready."""
    plan = normalize_course_outline_contract(plan)
    for chapter in plan.get("chapters") or []:
        for section in chapter.get("sections") or []:
            normalize_knowledge_structure(section)
    plan["knowledge_relations"] = _deduplicate_knowledge_relations([
        deepcopy(relation)
        for relation in plan.get("knowledge_relations") or []
        if isinstance(relation, dict)
    ] + [
        deepcopy(relation)
        for chapter in plan.get("chapters") or []
        for section in chapter.get("sections") or []
        for relation in section.get("knowledge_relations") or []
        if isinstance(relation, dict)
    ])
    return plan


def normalize_course_relation_batch(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize one graph-planning batch over a frozen course registry."""
    return {
        "schema_version": "course_relation_batch_v1",
        "node_decisions": [
            {
                "knowledge_id": str(item.get("knowledge_id") or "").strip(),
                "decision": str(item.get("decision") or "").strip(),
                "reason": str(item.get("reason") or "").strip(),
            }
            for item in payload.get("node_decisions") or []
            if isinstance(item, dict)
        ],
        "relations": [
            {
                **deepcopy(item),
                "source_knowledge_id": str(
                    item.get("source_knowledge_id") or ""
                ).strip(),
                "target_knowledge_id": str(
                    item.get("target_knowledge_id") or ""
                ).strip(),
                "relation_type": str(item.get("relation_type") or "").strip(),
                "reason": str(item.get("reason") or "").strip(),
                "conditions": _unique_strings(item.get("conditions") or []),
                "derivation_steps": _unique_strings(
                    item.get("derivation_steps") or []
                ),
            }
            for item in payload.get("relations") or []
            if isinstance(item, dict)
        ],
    }


def validate_course_relation_batch(
    payload: dict[str, Any],
    *,
    target_knowledge_ids: list[str],
    allowed_knowledge_ids: list[str],
) -> dict[str, Any]:
    """Validate graph structure without grading semantic richness.

    Every target node must receive an explicit compiler decision. The model may
    connect it through one of the six formal relations or mark it as a genuine
    course entry, but it may not silently omit the node.
    """
    batch = normalize_course_relation_batch(payload)
    targets = {str(item) for item in target_knowledge_ids if str(item)}
    allowed = {str(item) for item in allowed_knowledge_ids if str(item)}
    issues: list[dict[str, Any]] = []
    decisions: dict[str, dict[str, Any]] = {}

    for decision in batch["node_decisions"]:
        knowledge_id = decision["knowledge_id"]
        if knowledge_id not in targets:
            issues.append(_plan_issue(
                "course_relations:invalid_decision_target",
                "关系规划决定引用了当前批次之外的知识点 ID",
            ))
            continue
        if knowledge_id in decisions:
            issues.append(_plan_issue(
                "course_relations:duplicate_decision",
                f"知识点 {knowledge_id} 出现了重复关系规划决定",
            ))
            continue
        if decision["decision"] not in {"connected", "course_entry"}:
            issues.append(_plan_issue(
                "course_relations:invalid_decision",
                f"知识点 {knowledge_id} 的关系规划决定不合法",
            ))
        if not decision["reason"]:
            issues.append(_plan_issue(
                "course_relations:decision_missing_reason",
                f"知识点 {knowledge_id} 的关系规划决定缺少理由",
            ))
        decisions[knowledge_id] = decision

    for knowledge_id in sorted(targets - set(decisions)):
        issues.append(_plan_issue(
            "course_relations:missing_decision",
            f"知识点 {knowledge_id} 没有被关系规划批次处理",
        ))

    inbound: set[str] = set()
    signatures: set[tuple[str, str, str]] = set()
    valid_relations: list[dict[str, Any]] = []
    for relation in batch["relations"]:
        source_id = relation["source_knowledge_id"]
        target_id = relation["target_knowledge_id"]
        relation_type = relation["relation_type"]
        if relation_type not in COURSE_RELATION_TYPES:
            issues.append(_plan_issue(
                "course_relations:invalid_relation_type",
                f"知识关系类型「{relation_type or '空'}」不在六类正式关系中",
            ))
            continue
        if (
            source_id not in allowed
            or target_id not in allowed
            or source_id == target_id
        ):
            issues.append(_plan_issue(
                "course_relations:invalid_relation_endpoint",
                "知识关系端点必须引用当前批次允许的两个不同知识点 ID",
            ))
            continue
        if target_id not in targets:
            issues.append(_plan_issue(
                "course_relations:relation_outside_target",
                "关系批次只能为本批次负责的目标知识点建立入边",
            ))
            continue
        if not relation["reason"]:
            issues.append(_plan_issue(
                "course_relations:relation_missing_reason",
                "知识关系缺少具体语义理由",
            ))
        if (
            relation_type == "derives"
            and not relation.get("derivation_steps")
        ):
            issues.append(_plan_issue(
                "course_relations:derivation_missing_steps",
                "推导关系缺少关键推导步骤",
            ))
        if (
            relation_type == "contrasts_with"
            and not str(relation.get("distinction") or "").strip()
        ):
            issues.append(_plan_issue(
                "course_relations:contrast_missing_distinction",
                "对比关系缺少具体判别维度",
            ))
        signature = (source_id, target_id, relation_type)
        if relation_type in SYMMETRIC_COURSE_RELATION_TYPES:
            signature = (*sorted((source_id, target_id)), relation_type)
        if signature in signatures:
            issues.append(_plan_issue(
                "course_relations:duplicate_relation",
                "关系批次包含重复的知识关系",
            ))
            continue
        signatures.add(signature)
        valid_relations.append(relation)
        inbound.add(target_id)
        if relation_type in SYMMETRIC_COURSE_RELATION_TYPES:
            inbound.add(source_id)

    for knowledge_id, decision in decisions.items():
        if decision["decision"] == "connected" and knowledge_id not in inbound:
            issues.append(_plan_issue(
                "course_relations:connected_without_relation",
                f"知识点 {knowledge_id} 被标记为已连接，但没有对应关系入边",
            ))

    for relation_type in ACYCLIC_COURSE_RELATION_TYPES:
        cycle = _find_course_relation_cycle(valid_relations, relation_type)
        if cycle:
            issues.append(_plan_issue(
                "course_relations:cycle",
                f"{relation_type} 关系形成循环：{' -> '.join(cycle)}",
            ))

    return {
        "schema_version": "course_relation_batch_validation_v1",
        "passed": not issues,
        "issues": issues,
        "actual": {
            "target_count": len(targets),
            "decision_count": len(decisions),
            "relation_count": len(batch["relations"]),
        },
    }


def merge_course_relation_batches(
    batches: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Merge validated batches into one whole-course graph artifact."""
    decisions: list[dict[str, Any]] = []
    relations: list[dict[str, Any]] = []
    seen_decisions: set[str] = set()
    seen_relations: set[tuple[str, str, str]] = set()
    for raw_batch in batches:
        batch = normalize_course_relation_batch(raw_batch)
        for decision in batch["node_decisions"]:
            knowledge_id = decision["knowledge_id"]
            if knowledge_id and knowledge_id not in seen_decisions:
                seen_decisions.add(knowledge_id)
                decisions.append(deepcopy(decision))
        for relation in batch["relations"]:
            source_id = relation["source_knowledge_id"]
            target_id = relation["target_knowledge_id"]
            relation_type = relation["relation_type"]
            identity = (source_id, target_id, relation_type)
            if relation_type in SYMMETRIC_COURSE_RELATION_TYPES:
                left, right = sorted((source_id, target_id))
                identity = (left, right, relation_type)
                relation["source_knowledge_id"] = left
                relation["target_knowledge_id"] = right
            if not all(identity) or identity in seen_relations:
                continue
            seen_relations.add(identity)
            relations.append(deepcopy(relation))
    return decisions, relations


def attach_course_relation_plan(
    plan: dict[str, Any],
    *,
    knowledge_points: list[dict[str, Any]],
    node_decisions: list[dict[str, Any]],
    relations: list[dict[str, Any]],
) -> dict[str, Any]:
    """Attach system IDs and the completed graph plan to the frozen nodes."""
    plan = deepcopy(plan)
    point_by_name = {
        _normalize_knowledge_name(item.get("name")): item
        for item in knowledge_points
        if isinstance(item, dict)
        and _normalize_knowledge_name(item.get("name"))
    }
    decision_by_id = {
        str(item.get("knowledge_id") or ""): item
        for item in node_decisions
        if isinstance(item, dict) and str(item.get("knowledge_id") or "")
    }
    for chapter in plan.get("chapters") or []:
        for section in chapter.get("sections") or []:
            section["knowledge_relations"] = []
            for group in section.get("knowledge_structure") or []:
                if not isinstance(group, dict):
                    continue
                for point in group.get("knowledge_points") or []:
                    if not isinstance(point, dict):
                        continue
                    registry_point = point_by_name.get(
                        _normalize_knowledge_name(point.get("name"))
                    )
                    if not registry_point:
                        continue
                    knowledge_id = str(
                        registry_point.get("knowledge_id") or ""
                    )
                    point["knowledge_id"] = knowledge_id
                    decision = decision_by_id.get(knowledge_id) or {}
                    point["relation_state"] = str(
                        decision.get("decision") or ""
                    )
                    point["relation_decision_reason"] = str(
                        decision.get("reason") or ""
                    )
                    if decision.get("decision") == "course_entry":
                        point["entry_reason"] = str(
                            decision.get("reason") or ""
                        )
                    else:
                        point.pop("entry_reason", None)
                    point.pop("prerequisite_names", None)
                    point.pop("relations", None)
    plan["knowledge_relation_decisions"] = deepcopy(node_decisions)
    plan["knowledge_relations"] = deepcopy(relations)
    plan["knowledge_relation_schema_version"] = "course_relation_plan_v1"
    return plan


def validate_course_outline_constraints(
    plan: dict[str, Any],
    brief: dict[str, Any],
) -> dict[str, Any]:
    """Block only an unusable outline shape or an explicit size mismatch.

    Reviewable quality differences such as omitted objectives, omitted scope
    boundaries, or repeated wording are normalized or left for the outline
    review step. They must not turn a usable first draft into a failed job.
    """
    chapters = plan.get("chapters") if isinstance(plan, dict) else None
    chapters = chapters if isinstance(chapters, list) else []
    constraints = brief.get("course_shape_constraints") or {}
    issues: list[dict[str, Any]] = []
    if not chapters:
        issues.append(_plan_issue("outline:missing_chapters", "模型没有返回可用的课程章节 JSON"))
    malformed_chapters = [
        index for index, chapter in enumerate(chapters, start=1)
        if not isinstance(chapter, dict)
    ]
    if malformed_chapters:
        issues.append(_plan_issue("outline:malformed_chapters", f"课程目录第 {malformed_chapters} 章不是合法对象"))
    valid_chapters = [chapter for chapter in chapters if isinstance(chapter, dict)]
    section_count = 0
    for chapter_index, chapter in enumerate(valid_chapters, start=1):
        sections = chapter.get("sections")
        if not isinstance(sections, list):
            issues.append(_plan_issue("outline:malformed_section_lists", f"课程目录第 {chapter_index} 章缺少合法小节列表"))
            continue
        for section_index, section in enumerate(sections, start=1):
            section_count += 1
            if not isinstance(section, dict):
                issues.append(_plan_issue(
                    "outline:malformed_section",
                    f"课程目录小节 {chapter_index}.{section_index} 不是合法对象",
                ))
    if chapters and not section_count:
        issues.append(_plan_issue("outline:missing_sections", "课程目录没有可生成的小节"))
    expected_chapters = constraints.get("chapter_count")
    if expected_chapters and len(chapters) != int(expected_chapters):
        issues.append(_plan_issue(
            "outline:chapter_count_mismatch",
            f"用户明确要求 {expected_chapters} 章，目录实际为 {len(chapters)} 章",
        ))
    expected_sections = constraints.get("section_count")
    if expected_sections and section_count != int(expected_sections):
        issues.append(_plan_issue(
            "outline:section_count_mismatch",
            f"用户明确要求 {expected_sections} 个小节，目录实际为 {section_count} 个",
        ))
    return {
        "schema_version": "course_outline_constraints_v1",
        "passed": not issues,
        "expected": constraints,
        "actual": {
            "chapter_count": len(chapters),
            "section_count": section_count,
        },
        "issues": issues,
    }


def normalize_section_knowledge_package(package: dict[str, Any]) -> dict[str, Any]:
    """Normalize one section package without changing the frozen outline."""
    section = {
        "key_points": list(package.get("key_points") or []),
        "knowledge_structure": deepcopy(package.get("knowledge_structure") or []),
    }
    normalize_knowledge_structure(section)
    return {
        "schema_version": "section_knowledge_package_v1",
        "knowledge_structure": section.get("knowledge_structure") or [],
        "key_points": section.get("key_points") or [],
        "reused_knowledge_names": _unique_strings(package.get("reused_knowledge_names") or []),
        "knowledge_relations": [
            deepcopy(item) for item in package.get("knowledge_relations") or []
            if isinstance(item, dict)
        ],
    }


def normalize_section_knowledge_node_package(
    package: dict[str, Any],
) -> dict[str, Any]:
    """Keep only frozen nodes and leaf teaching contracts for graph planning."""
    normalized = normalize_section_knowledge_package(package)
    for group in normalized.get("knowledge_structure") or []:
        if not isinstance(group, dict):
            continue
        for point in group.get("knowledge_points") or []:
            if not isinstance(point, dict):
                continue
            point.pop("entry_reason", None)
            point.pop("prerequisite_names", None)
            point.pop("relations", None)
            point.pop("relation_state", None)
            point.pop("relation_decision_reason", None)
            point.pop("knowledge_id", None)
    normalized["schema_version"] = "section_knowledge_nodes_v2"
    normalized["knowledge_relations"] = []
    return normalized


def validate_section_knowledge_package(
    package: dict[str, Any],
    *,
    section_title: str,
    available_knowledge_names: list[str],
    required_knowledge_names: list[str] | None = None,
    required_reused_knowledge_names: list[str] | None = None,
    validate_relations: bool = True,
) -> dict[str, Any]:
    """Validate the smallest retryable knowledge unit.

    A section is blocked only when it cannot provide a usable teaching
    skeleton. Optional enrichment defects remain internal diagnostics and do
    not trigger another model call or turn the whole course into a failed task.
    """
    issues: list[dict[str, Any]] = []
    structures = package.get("knowledge_structure") or []
    available = {
        _normalize_knowledge_name(name): str(name)
        for name in available_knowledge_names
        if _normalize_knowledge_name(name)
    }
    local_names: dict[str, str] = {}
    usable_point_count = 0
    inbound_names: set[str] = set()
    title_identity = _normalize_knowledge_name(section_title)
    if not structures:
        issues.append(_plan_issue("section_knowledge:missing_structure", f"小节「{section_title}」没有返回知识包"))
    for raw_group in structures:
        if not isinstance(raw_group, dict):
            issues.append(_plan_issue(
                "section_knowledge:malformed_group",
                f"小节「{section_title}」存在无法使用的概念组，系统将忽略该组",
                blocking=False,
            ))
            continue
        group_name = str(raw_group.get("concept_group") or raw_group.get("topic") or "").strip()
        points = [item for item in raw_group.get("knowledge_points") or [] if isinstance(item, dict)]
        if not group_name:
            issues.append(_plan_issue(
                "section_knowledge:group_missing_name",
                f"小节「{section_title}」存在未命名概念组，无法建立稳定知识归属",
            ))
        elif _normalize_knowledge_name(group_name) == title_identity:
            issues.append(_plan_issue(
                "section_knowledge:group_mirrors_section",
                f"小节「{section_title}」的概念组名称复制了小节标题，可在确认时继续优化",
                blocking=False,
            ))
        if len(points) < 2:
            issues.append(_plan_issue(
                "section_knowledge:group_too_small",
                f"概念组「{group_name or '未命名'}」当前只有一个原子知识点，不影响继续生成",
                blocking=False,
            ))
        for point in points:
            name = str(point.get("name") or "").strip()
            normalized = _normalize_knowledge_name(name)
            if not name:
                issues.append(_plan_issue(
                    "section_knowledge:point_missing_name",
                    f"小节「{section_title}」存在未命名知识点，系统将忽略该条",
                    blocking=False,
                ))
                continue
            if normalized == title_identity:
                issues.append(_plan_issue(
                    "section_knowledge:point_mirrors_section",
                    f"知识点「{name}」复制了小节标题，但已有具体内容，可在确认时优化名称",
                    blocking=False,
                ))
            if normalized in local_names or normalized in available:
                issues.append(_plan_issue(
                    "section_knowledge:duplicate_identity",
                    f"知识点「{name}」已经存在，系统将复用同一课程知识身份",
                    blocking=False,
                ))
            local_names[normalized] = name
            statement = str(point.get("statement") or point.get("description") or "").strip()
            if not statement:
                issues.append(_plan_issue("section_knowledge:missing_statement", f"知识点「{name}」缺少独立知识陈述"))
            else:
                usable_point_count += 1
            if not point.get("conditions") and not point.get("boundaries"):
                issues.append(_plan_issue("section_knowledge:missing_boundary", f"知识点「{name}」缺少成立条件或适用边界"))
            skills = point.get("capability_points") or point.get("capabilities") or []
            if not skills or any(
                not isinstance(item, dict)
                or not str(item.get("observable_behavior") or "").strip()
                for item in skills
            ):
                issues.append(_plan_issue("section_knowledge:missing_skill", f"知识点「{name}」缺少可观察能力"))
            mastery = point.get("mastery_criteria") or []
            if not mastery or any(
                not isinstance(item, dict)
                or not str(item.get("observable_performance") or "").strip()
                or not str(item.get("verification_method") or "").strip()
                for item in mastery
            ):
                issues.append(_plan_issue("section_knowledge:missing_mastery", f"知识点「{name}」缺少可验证掌握标准"))
            for mistake in point.get("misconceptions") or []:
                if not isinstance(mistake, dict) or any(
                    not str(mistake.get(field) or "").strip()
                    for field in ("observable_error_pattern", "discrimination", "repair_strategy")
                ):
                    issues.append(_plan_issue(
                        "section_knowledge:template_misconception",
                        f"知识点「{name}」存在不完整易错点，系统不会把它作为正式诊断依据",
                        blocking=False,
                    ))

    if structures and usable_point_count == 0:
        issues.append(_plan_issue(
            "section_knowledge:no_usable_points",
            f"小节「{section_title}」没有可用于教学的具名知识陈述",
        ))

    required_local = {
        _normalize_knowledge_name(name): str(name)
        for name in required_knowledge_names or []
        if _normalize_knowledge_name(name)
    }
    missing_required = [
        original
        for normalized, original in required_local.items()
        if normalized not in local_names
    ]
    unexpected_local = [
        original
        for normalized, original in local_names.items()
        if required_knowledge_names is not None
        and normalized not in required_local
    ]
    renamed_local = [
        f"{actual}（应为 {required_local[normalized]}）"
        for normalized, actual in local_names.items()
        if normalized in required_local
        and actual != required_local[normalized]
    ]
    if missing_required:
        issues.append(_plan_issue(
            "section_knowledge:missing_skeleton_identity",
            "知识包缺少全课身份骨架已冻结的知识点："
            f"{'、'.join(missing_required)}",
        ))
    if unexpected_local:
        issues.append(_plan_issue(
            "section_knowledge:unexpected_skeleton_identity",
            "知识包新增了全课身份骨架之外的知识点："
            f"{'、'.join(unexpected_local)}",
        ))
    if renamed_local:
        issues.append(_plan_issue(
            "section_knowledge:renamed_skeleton_identity",
            "知识包必须逐字沿用全课身份骨架中的规范名称："
            f"{'、'.join(renamed_local)}",
        ))

    all_names = {**available, **local_names}
    relations = [
        item for item in package.get("knowledge_relations") or []
        if validate_relations and isinstance(item, dict)
    ]
    allowed_relations = {
        "prerequisite",
        "derives",
        "equivalent_to",
        "contrasts_with",
        "applies_to",
        "generalizes",
    }
    for relation in relations:
        relation_type = str(relation.get("relation_type") or "").strip()
        source = _normalize_knowledge_name(relation.get("source_name"))
        target = _normalize_knowledge_name(relation.get("target_name"))
        if relation_type not in allowed_relations:
            issues.append(_plan_issue(
                "section_knowledge:invalid_relation_type",
                f"知识关系类型「{relation_type or '空'}」不在白名单，系统将忽略该关系",
                blocking=False,
            ))
            continue
        if source not in all_names or target not in all_names or source == target:
            issues.append(_plan_issue(
                "section_knowledge:invalid_relation_endpoint",
                "知识关系未能连接当前课程中的两个不同知识点，系统将忽略该关系",
                blocking=False,
            ))
            continue
        if not str(relation.get("reason") or "").strip():
            issues.append(_plan_issue(
                "section_knowledge:relation_missing_reason",
                "知识关系缺少具体理由，系统将忽略该关系",
                blocking=False,
            ))
        if relation_type == "derives" and not relation.get("derivation_steps"):
            issues.append(_plan_issue(
                "section_knowledge:derivation_missing_steps",
                "推导关系缺少关键步骤，系统将忽略该关系",
                blocking=False,
            ))
        if relation_type == "contrasts_with" and not str(relation.get("distinction") or "").strip():
            issues.append(_plan_issue(
                "section_knowledge:contrast_missing_distinction",
                "对比关系缺少判别维度，系统将忽略该关系",
                blocking=False,
            ))
        inbound_names.add(target)
        if relation_type in {"equivalent_to", "contrasts_with"}:
            inbound_names.add(source)

    if validate_relations:
        for raw_group in structures:
            if not isinstance(raw_group, dict):
                continue
            for point in raw_group.get("knowledge_points") or []:
                if not isinstance(point, dict):
                    continue
                normalized = _normalize_knowledge_name(point.get("name"))
                if (
                    normalized
                    and normalized not in inbound_names
                    and not str(point.get("entry_reason") or "").strip()
                ):
                    issues.append(_plan_issue(
                        "section_knowledge:entry_reason_missing",
                        f"知识点「{point.get('name')}」尚未说明为何从这里开始学习",
                        blocking=False,
                    ))

    reused = {
        _normalize_knowledge_name(name)
        for name in package.get("reused_knowledge_names") or []
        if _normalize_knowledge_name(name)
    }
    required_reused = {
        _normalize_knowledge_name(name): str(name)
        for name in required_reused_knowledge_names or []
        if _normalize_knowledge_name(name)
    }
    if required_reused_knowledge_names is not None:
        missing_reused = [
            original
            for normalized, original in required_reused.items()
            if normalized not in reused
        ]
        unexpected_reused = [
            str(name)
            for name in package.get("reused_knowledge_names") or []
            if _normalize_knowledge_name(name) not in required_reused
        ]
        renamed_reused = [
            f"{str(name).strip()}（应为 "
            f"{required_reused[_normalize_knowledge_name(name)]}）"
            for name in package.get("reused_knowledge_names") or []
            if _normalize_knowledge_name(name) in required_reused
            and str(name).strip()
            != required_reused[_normalize_knowledge_name(name)]
        ]
        if missing_reused or unexpected_reused or renamed_reused:
            details = []
            if missing_reused:
                details.append(f"缺少：{'、'.join(missing_reused)}")
            if unexpected_reused:
                details.append(f"多出：{'、'.join(unexpected_reused)}")
            if renamed_reused:
                details.append(f"改名：{'、'.join(renamed_reused)}")
            issues.append(_plan_issue(
                "section_knowledge:reuse_contract_mismatch",
                "复用知识必须与全课身份骨架一致（"
                f"{'；'.join(details)}）",
            ))
    invalid_reused = [
        name for name in package.get("reused_knowledge_names") or []
        if _normalize_knowledge_name(name) not in available
    ]
    if invalid_reused:
        issues.append(_plan_issue(
            "section_knowledge:invalid_reuse",
            f"尚未找到准备复用的知识点：{'、'.join(str(item) for item in invalid_reused)}",
            blocking=False,
        ))
    if reused & set(local_names):
        issues.append(_plan_issue(
            "section_knowledge:reuse_redefined",
            "同一知识点同时被复用和重新创建，系统将按同一课程知识身份合并",
            blocking=False,
        ))
    return _constraint_report(
        schema_version="section_knowledge_constraints_v1",
        actual={
            "concept_group_count": len(structures),
            "knowledge_point_count": len(local_names),
            "usable_knowledge_point_count": usable_point_count,
            "relation_count": len(relations),
            "required_knowledge_point_count": len(required_local),
            "required_reused_knowledge_count": len(required_reused),
        },
        issues=issues,
    )


def apply_section_knowledge_package(
    plan: dict[str, Any],
    node_id: str,
    package: dict[str, Any],
) -> dict[str, Any]:
    """Attach a validated package to one frozen outline section."""
    for chapter in plan.get("chapters") or []:
        for section in chapter.get("sections") or []:
            if str(section.get("node_id") or "") != str(node_id):
                continue
            section["knowledge_structure"] = deepcopy(package.get("knowledge_structure") or [])
            section["key_points"] = list(package.get("key_points") or [])
            section["reused_knowledge_names"] = list(package.get("reused_knowledge_names") or [])
            section["knowledge_relations"] = deepcopy(package.get("knowledge_relations") or [])
            section["knowledge_package_status"] = "completed"
            return plan
    raise KeyError(node_id)


def _unique_strings(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _deduplicate_knowledge_relations(
    relations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for relation in relations:
        relation_type = str(relation.get("relation_type") or "").strip()
        source_id = str(relation.get("source_knowledge_id") or "").strip()
        target_id = str(relation.get("target_knowledge_id") or "").strip()
        if source_id or target_id:
            identity = (source_id, target_id, relation_type)
            if relation_type in SYMMETRIC_COURSE_RELATION_TYPES:
                left, right = sorted((source_id, target_id))
                identity = (left, right, relation_type)
                relation["source_knowledge_id"] = left
                relation["target_knowledge_id"] = right
        else:
            identity = (
                _normalize_knowledge_name(relation.get("source_name")),
                _normalize_knowledge_name(relation.get("target_name")),
                relation_type,
            )
        if not all(identity) or identity in seen:
            continue
        seen.add(identity)
        result.append(relation)
    return result


def _find_course_relation_cycle(
    relations: list[dict[str, Any]],
    relation_type: str,
) -> list[str]:
    graph: dict[str, list[str]] = {}
    for relation in relations:
        if relation.get("relation_type") != relation_type:
            continue
        source_id = str(relation.get("source_knowledge_id") or "")
        target_id = str(relation.get("target_knowledge_id") or "")
        if source_id and target_id:
            graph.setdefault(source_id, []).append(target_id)

    visiting: list[str] = []
    visited: set[str] = set()

    def visit(node_id: str) -> list[str]:
        if node_id in visiting:
            start = visiting.index(node_id)
            return [*visiting[start:], node_id]
        if node_id in visited:
            return []
        visiting.append(node_id)
        for target_id in graph.get(node_id, []):
            cycle = visit(target_id)
            if cycle:
                return cycle
        visiting.pop()
        visited.add(node_id)
        return []

    for node_id in graph:
        cycle = visit(node_id)
        if cycle:
            return cycle
    return []


def validate_course_plan_constraints(
    plan: dict[str, Any],
    brief: dict[str, Any],
) -> dict[str, Any]:
    """Validate explicit user-owned course shape before content generation."""
    chapters = plan.get("chapters") if isinstance(plan, dict) else None
    chapters = chapters if isinstance(chapters, list) else []
    malformed_chapter_indexes = [
        index
        for index, chapter in enumerate(chapters, start=1)
        if not isinstance(chapter, dict)
    ]
    malformed_section_chapters = [
        index
        for index, chapter in enumerate(chapters, start=1)
        if isinstance(chapter, dict) and not isinstance(chapter.get("sections"), list)
    ]
    malformed_sections = [
        f"{chapter_index}.{section_index}"
        for chapter_index, chapter in enumerate(chapters, start=1)
        if isinstance(chapter, dict) and isinstance(chapter.get("sections"), list)
        for section_index, section in enumerate(chapter.get("sections") or [], start=1)
        if not isinstance(section, dict)
    ]
    section_count = sum(
        len(chapter.get("sections") or [])
        for chapter in chapters
        if isinstance(chapter, dict) and isinstance(chapter.get("sections"), list)
    )
    constraints = brief.get("course_shape_constraints") or {}
    issues: list[dict[str, Any]] = []
    if not chapters:
        issues.append({
            "code": "plan:missing_chapters",
            "message": "模型没有返回可用的课程章节 JSON",
            "blocking": True,
        })
    if malformed_chapter_indexes:
        issues.append({
            "code": "plan:malformed_chapters",
            "message": f"课程蓝图第 {malformed_chapter_indexes} 章不是合法对象",
            "blocking": True,
        })
    if malformed_section_chapters:
        issues.append({
            "code": "plan:malformed_section_lists",
            "message": f"课程蓝图第 {malformed_section_chapters} 章缺少合法小节列表",
            "blocking": True,
        })
    if malformed_sections:
        issues.append({
            "code": "plan:malformed_sections",
            "message": f"课程蓝图小节 {malformed_sections} 不是合法对象",
            "blocking": True,
        })
    if chapters and not section_count:
        issues.append({
            "code": "plan:missing_sections",
            "message": "课程蓝图没有可生成的小节",
            "blocking": True,
        })
    expected_chapters = constraints.get("chapter_count")
    if expected_chapters and len(chapters) != int(expected_chapters):
        issues.append({
            "code": "plan:chapter_count_mismatch",
            "message": f"用户明确要求 {expected_chapters} 章，蓝图实际为 {len(chapters)} 章",
            "blocking": True,
        })
    expected_sections = constraints.get("section_count")
    if expected_sections and section_count != int(expected_sections):
        issues.append({
            "code": "plan:section_count_mismatch",
            "message": f"用户明确要求 {expected_sections} 个小节，蓝图实际为 {section_count} 个",
            "blocking": True,
        })
    issues.extend(_knowledge_contract_issues(plan, chapters))
    return _constraint_report(
        schema_version="course_plan_constraints_v2",
        expected=constraints,
        actual={
            "chapter_count": len(chapters),
            "section_count": section_count,
        },
        issues=issues,
    )


def _knowledge_contract_issues(
    plan: dict[str, Any],
    chapters: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Reject chapter-title indexes before any expensive content generation."""
    issues: list[dict[str, Any]] = []
    point_names: dict[str, str] = {}
    point_ids: dict[str, str] = {}
    inbound_names: set[str] = set()
    entry_names: set[str] = set()
    relation_candidates: list[dict[str, Any]] = [
        deepcopy(item) for item in plan.get("knowledge_relations") or []
        if isinstance(item, dict)
    ]
    allowed_relations = {
        "prerequisite",
        "derives",
        "equivalent_to",
        "contrasts_with",
        "applies_to",
        "generalizes",
    }

    for chapter in chapters:
        if not isinstance(chapter, dict):
            continue
        for section in chapter.get("sections") or []:
            if not isinstance(section, dict):
                continue
            section_label = str(section.get("section_number") or section.get("node_id") or "未知小节")
            section_title = _normalize_knowledge_name(section.get("title"))
            prior_point_names = set(point_names)
            section_usable_point_count = 0
            structures = section.get("knowledge_structure") or []
            if not structures:
                issues.append(_plan_issue(
                    "plan:missing_knowledge_structure",
                    f"小节 {section_label} 没有课程知识蓝图",
                ))
                continue
            for raw_group in structures:
                if not isinstance(raw_group, dict):
                    issues.append(_plan_issue(
                        "plan:malformed_concept_group",
                        f"小节 {section_label} 存在无法使用的概念组，系统将忽略该组",
                    ))
                    continue
                group_name = str(
                    raw_group.get("concept_group")
                    or raw_group.get("topic")
                    or raw_group.get("name")
                    or ""
                ).strip()
                points = [item for item in raw_group.get("knowledge_points") or [] if isinstance(item, dict)]
                if not group_name:
                    issues.append(_plan_issue(
                        "plan:concept_group_missing_name",
                        f"小节 {section_label} 存在未命名概念组，无法建立稳定知识归属",
                    ))
                elif _normalize_knowledge_name(group_name) == section_title:
                    issues.append(_plan_issue(
                        "plan:concept_group_mirrors_section",
                        f"小节 {section_label} 的概念组复制了小节标题，可在确认时继续优化",
                    ))
                if len(points) < 2:
                    issues.append(_plan_issue(
                        "plan:concept_group_too_small",
                        f"小节 {section_label} 的概念组「{group_name or '未命名'}」少于两个原子知识点",
                    ))
                for point in points:
                    name = str(point.get("name") or "").strip()
                    normalized = _normalize_knowledge_name(name)
                    if not name:
                        issues.append(_plan_issue(
                            "plan:knowledge_point_missing_name",
                            f"小节 {section_label} 存在未命名知识点，系统将忽略该条",
                        ))
                        continue
                    knowledge_id = str(point.get("knowledge_id") or "").strip()
                    if knowledge_id:
                        point_ids[knowledge_id] = name
                    if normalized == section_title:
                        issues.append(_plan_issue(
                            "plan:knowledge_point_mirrors_section",
                            f"知识点「{name}」复制了小节标题，但已有具体内容，可在确认时优化名称",
                        ))
                    if normalized in point_names:
                        issues.append(_plan_issue(
                            "plan:duplicate_knowledge_identity",
                            f"知识点「{name}」在全课重复创建，应复用同一课程知识身份",
                        ))
                    point_names[normalized] = name
                    statement = str(point.get("statement") or point.get("description") or "").strip()
                    if not statement:
                        issues.append(_plan_issue(
                            "plan:knowledge_point_missing_statement",
                            f"知识点「{name}」只有名称，没有独立知识陈述",
                        ))
                    else:
                        section_usable_point_count += 1
                    if not point.get("conditions") and not point.get("boundaries"):
                        issues.append(_plan_issue(
                            "plan:knowledge_point_missing_boundary",
                            f"知识点「{name}」没有成立条件或适用边界",
                        ))
                    skills = point.get("capability_points") or point.get("capabilities") or []
                    if not skills or any(
                        not isinstance(item, dict)
                        or not str(item.get("observable_behavior") or "").strip()
                        for item in skills
                    ):
                        issues.append(_plan_issue(
                            "plan:knowledge_point_missing_skill",
                            f"知识点「{name}」缺少可观察能力点",
                        ))
                    mastery = point.get("mastery_criteria") or []
                    if not mastery or any(
                        not isinstance(item, dict)
                        or not str(item.get("observable_performance") or "").strip()
                        or not str(item.get("verification_method") or "").strip()
                        for item in mastery
                    ):
                        issues.append(_plan_issue(
                            "plan:knowledge_point_missing_mastery",
                            f"知识点「{name}」缺少可验证掌握标准",
                        ))
                    for mistake in point.get("misconceptions") or []:
                        if not isinstance(mistake, dict) or any(
                            not str(mistake.get(field) or "").strip()
                            for field in ("observable_error_pattern", "discrimination", "repair_strategy")
                        ):
                            issues.append(_plan_issue(
                                "plan:misconception_is_template",
                                f"知识点「{name}」存在无法观察、辨别或修复的模板易错点",
                            ))
                    if str(point.get("entry_reason") or "").strip():
                        entry_names.add(normalized)
                    for prerequisite in point.get("prerequisite_names") or []:
                        relation_candidates.append({
                            "source_name": str(prerequisite),
                            "target_name": name,
                            "relation_type": "prerequisite",
                            "reason": "蓝图声明的必要前置",
                        })
                    for relation in point.get("relations") or []:
                        if isinstance(relation, dict):
                            relation_candidates.append({**deepcopy(relation), "source_name": name})
            if section_usable_point_count == 0:
                issues.append(_plan_issue(
                    "plan:no_usable_knowledge_points",
                    f"小节 {section_label} 没有可用于教学的具名知识陈述",
                ))
            for reused_name in section.get("reused_knowledge_names") or []:
                if _normalize_knowledge_name(reused_name) not in prior_point_names:
                    issues.append(_plan_issue(
                        "plan:invalid_reused_knowledge",
                        f"小节 {section_label} 复用了尚未在前序小节定义的知识点「{reused_name}」",
                    ))

    id_relations = [
        relation
        for relation in relation_candidates
        if str(relation.get("source_knowledge_id") or "").strip()
        or str(relation.get("target_knowledge_id") or "").strip()
    ]
    relation_decisions = [
        item
        for item in plan.get("knowledge_relation_decisions") or []
        if isinstance(item, dict)
    ]
    if id_relations or relation_decisions:
        relation_report = validate_course_relation_batch(
            {
                "node_decisions": relation_decisions,
                "relations": id_relations,
            },
            target_knowledge_ids=list(point_ids),
            allowed_knowledge_ids=list(point_ids),
        )
        issues.extend(deepcopy(relation_report.get("issues") or []))
        return issues

    for relation in relation_candidates:
        relation_type = str(relation.get("relation_type") or "").strip()
        source_name = _normalize_knowledge_name(relation.get("source_name"))
        target_name = _normalize_knowledge_name(relation.get("target_name"))
        if relation_type not in allowed_relations:
            issues.append(_plan_issue(
                "plan:invalid_knowledge_relation",
                f"知识关系只允许六类正式关系，收到「{relation_type or '空'}」",
            ))
            continue
        if source_name not in point_names or target_name not in point_names or source_name == target_name:
            issues.append(_plan_issue(
                "plan:invalid_relation_endpoint",
                "知识关系端点必须引用当前课程内两个不同的原子知识点规范名称",
            ))
            continue
        if not str(relation.get("reason") or "").strip():
            issues.append(_plan_issue("plan:relation_missing_reason", "知识关系缺少具体判定理由"))
        if relation_type == "derives" and not relation.get("derivation_steps"):
            issues.append(_plan_issue("plan:derivation_missing_steps", "推导关系缺少关键步骤"))
        if relation_type == "contrasts_with" and not str(relation.get("distinction") or "").strip():
            issues.append(_plan_issue("plan:contrast_missing_distinction", "对比关系缺少具体判别维度"))
        inbound_names.add(target_name)
        if relation_type in {"equivalent_to", "contrasts_with"}:
            inbound_names.add(source_name)

    for normalized, name in point_names.items():
        if normalized not in inbound_names and normalized not in entry_names:
            issues.append(_plan_issue(
                "plan:knowledge_entry_reason_missing",
                f"知识点「{name}」既无关系入边，也没有入口理由",
            ))
    return issues


def _normalize_knowledge_name(value: Any) -> str:
    text = re.sub(r"^\d+(?:\.\d+)*\s*", "", str(value or "").strip())
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", text.lower())


_ADVISORY_CONSTRAINT_CODES = {
    "section_knowledge:malformed_group",
    "section_knowledge:group_mirrors_section",
    "section_knowledge:group_too_small",
    "section_knowledge:point_missing_name",
    "section_knowledge:point_mirrors_section",
    "section_knowledge:duplicate_identity",
    "section_knowledge:missing_statement",
    "section_knowledge:missing_boundary",
    "section_knowledge:missing_skill",
    "section_knowledge:missing_mastery",
    "section_knowledge:template_misconception",
    "section_knowledge:invalid_relation_type",
    "section_knowledge:invalid_relation_endpoint",
    "section_knowledge:relation_missing_reason",
    "section_knowledge:derivation_missing_steps",
    "section_knowledge:contrast_missing_distinction",
    "section_knowledge:entry_reason_missing",
    "section_knowledge:invalid_reuse",
    "section_knowledge:reuse_redefined",
    "plan:malformed_concept_group",
    "plan:concept_group_mirrors_section",
    "plan:concept_group_too_small",
    "plan:knowledge_point_missing_name",
    "plan:knowledge_point_mirrors_section",
    "plan:duplicate_knowledge_identity",
    "plan:knowledge_point_missing_statement",
    "plan:knowledge_point_missing_boundary",
    "plan:knowledge_point_missing_skill",
    "plan:knowledge_point_missing_mastery",
    "plan:misconception_is_template",
    "plan:invalid_reused_knowledge",
    "plan:invalid_knowledge_relation",
    "plan:invalid_relation_endpoint",
    "plan:relation_missing_reason",
    "plan:derivation_missing_steps",
    "plan:contrast_missing_distinction",
    "plan:knowledge_entry_reason_missing",
}


def _plan_issue(
    code: str,
    message: str,
    *,
    blocking: bool | None = None,
) -> dict[str, Any]:
    is_blocking = code not in _ADVISORY_CONSTRAINT_CODES if blocking is None else blocking
    return {
        "code": code,
        "message": message,
        "blocking": is_blocking,
        "severity": "critical" if is_blocking else "advisory",
    }


def _constraint_report(
    *,
    schema_version: str,
    actual: dict[str, Any],
    issues: list[dict[str, Any]],
    expected: dict[str, Any] | None = None,
) -> dict[str, Any]:
    blocking_issues = [item for item in issues if item.get("blocking", True)]
    advisory_issues = [item for item in issues if not item.get("blocking", True)]
    report = {
        "schema_version": schema_version,
        "passed": not blocking_issues,
        "strict_passed": not issues,
        "status": (
            "blocked"
            if blocking_issues
            else "passed_with_advisories"
            if advisory_issues
            else "passed"
        ),
        "actual": actual,
        "issues": issues,
        "blocking_issues": blocking_issues,
        "advisory_issues": advisory_issues,
    }
    if expected is not None:
        report["expected"] = expected
    return report


def build_course_blueprint_from_plan(plan: dict[str, Any], artifacts: dict[str, Any]) -> dict[str, Any]:
    """Wrap an LLM outline plan as a CourseBlueprint contract."""
    nodes = []
    for chapter in plan.get("chapters", []):
        chapter_number = chapter.get("chapter_number", len(nodes) + 1)
        for section in chapter.get("sections", []):
            section_number = section.get("section_number", f"{chapter_number}.1")
            nodes.append({
                "node_id": f"L2-{str(section_number).replace('.', '-')}",
                "section_number": section_number,
                "title": section.get("title", ""),
                "learning_objective": section.get("learning_objective", ""),
                "evidence_refs": section.get("evidence_refs", []),
                "grounding_contract": section.get("grounding_contract", {}),
                "knowledge_points": section.get("key_points", []),
                "knowledge_structure": section.get("knowledge_structure", []),
                "reused_knowledge_names": section.get("reused_knowledge_names", []),
                "example_plan": section.get("examples_plan") or _example_plan_for_refs(section.get("evidence_refs", []), artifacts),
                "exercise_plan": section.get("exercise_plan") or _exercise_plan_for_refs(section.get("evidence_refs", []), artifacts),
                "misconceptions": section.get("misconceptions", []),
                "scope_boundary": section.get("scope_boundary", ""),
                "assessment": section.get("assessment", []),
                "prerequisite_node_ids": section.get("prerequisite_node_ids", []),
                "module_plan": section.get("module_plan", []),
                "difficulty_contract": section.get("difficulty_contract", {}),
            })

    return {
        "blueprint_id": f"cbp-{uuid.uuid4()}",
        "schema_version": PIPELINE_VERSION,
        "course_title": plan.get("course_title") or artifacts.get("course_generation_brief", {}).get("subject", ""),
        "positioning": plan.get("positioning") or artifacts.get("course_generation_brief", {}).get("goal", "电子课程资料"),
        "learning_objectives": plan.get("learning_objectives", []),
        "prerequisites": plan.get("prerequisites", []),
        "knowledge_relation_schema_version": plan.get(
            "knowledge_relation_schema_version"
        ),
        "knowledge_relation_decisions": deepcopy(
            plan.get("knowledge_relation_decisions") or []
        ),
        "knowledge_relations": deepcopy(plan.get("knowledge_relations") or []),
        "subject_pedagogy_profile": artifacts.get("subject_pedagogy_profile") or plan.get("subject_pedagogy_profile") or {},
        "course_composition_profile": artifacts.get("course_composition_profile") or plan.get("course_composition_profile") or {},
        "course_block_distribution": plan.get("course_block_distribution") or {},
        "difficulty_profile": artifacts.get("difficulty_profile") or plan.get("difficulty_profile") or {},
        "difficulty_gap_assessment": artifacts.get("difficulty_gap_assessment") or {},
        "adaptation_decision": artifacts.get("adaptation_decision") or {},
        "course_difficulty_curve": plan.get("course_difficulty_curve") or {},
        "course_module_plan": plan.get("course_module_plan", []),
        "sections": plan.get("chapters", []),
        "nodes": nodes,
        "appendices_plan": [
            "核心概念与方法总览",
            "实践与练习索引",
            "易错点与边界总表",
            "学习检查清单",
        ],
        "coverage_plan": artifacts.get("evidence_coverage_plan") or {},
    }


def build_outline_generation_context(artifacts: dict[str, Any]) -> str:
    """Prompt section injected into outline generation."""
    brief = artifacts.get("course_generation_brief", {})
    cards = artifacts.get("material_cards", [])
    profile = artifacts.get("subject_pedagogy_profile", {})
    return "\n".join([
        "## 资料增强课程生成 brief",
        _format_brief(brief),
        "",
        "## 上传资料卡",
        _format_material_cards(cards),
        "",
        "## 可用证据目录",
        build_evidence_catalog_summary(artifacts.get("evidence_catalog") or []),
        "",
        "## 证据使用策略",
        f"- {(artifacts.get('evidence_coverage_plan') or {}).get('strategy', 'material_first')}",
        "",
        "## 教学画像",
        _format_pedagogy_profile(profile),
        "",
        "## 难度能力契约",
        format_difficulty_profile(artifacts.get("difficulty_profile") or {}),
        "",
        "## 入口差距与适配决策",
        _format_adaptation(
            artifacts.get("difficulty_gap_assessment") or {},
            artifacts.get("adaptation_decision") or {},
        ),
        "",
        "## 电子课程资料硬标准",
        "- 统一产物是一本适合自学的电子课程资料，不拆考试导向或普通学习方向。",
        "- 必须覆盖完整、结构清晰、少废话、适合自学。",
        "- 必须遵守教学画像和模块计划，不能把所有学科压成同一正文结构。",
        "- 关键知识点要规划学习者行动、反馈、误区和验收标准。",
        "- 未上传资料不得伪装成已读依据。",
    ])


def build_node_generation_context(
    *,
    course_metadata: dict[str, Any] | None,
    node: dict[str, Any],
) -> str:
    """Prompt section for node-level content generation."""
    metadata = course_metadata or {}
    brief = metadata.get("course_generation_brief") or {}
    blueprint = metadata.get("course_blueprint") or {}
    node_blueprint = _find_blueprint_node(blueprint, node)
    evidence_bundle = evidence_bundle_for_node(metadata, {**node_blueprint, **node})

    parts = [
        "## 资料增强生成上下文",
        f"- 生成目标：{brief.get('goal', '电子课程资料')}",
        f"- 讲法要求：{'；'.join(brief.get('style_requirements', [])) or '少废话、适合自学、讲清底层原理'}",
        f"- 避免风格：{'；'.join(brief.get('avoid_styles', [])) or '晦涩堆定义；空泛打比方'}",
        "",
        "## 当前节点蓝图",
        _format_node_blueprint(node_blueprint),
    ]
    if evidence_bundle:
        parts.extend([
            "",
            "## 当前节点限定证据包",
            _format_evidence_bundle(evidence_bundle),
            "",
            "资料事实后必须追加对应的 `[[evidence:ev-id]]` 标记；只能使用上面列出的证据 ID。",
        ])
    else:
        parts.extend(["", "## 当前节点资料依据", "- 当前节点没有可引用的资料证据，不得伪装引用资料。"])
    parts.extend(["", "## 当前节点模块要求", _format_module_plan(node_blueprint.get("module_plan", []))])
    parts.extend([
        "",
        "## 当前节点难度契约",
        format_node_difficulty_contract(
            node.get("difficulty_contract")
            or node_blueprint.get("difficulty_contract")
            or {}
        ),
    ])
    return "\n".join(parts)


def attach_generation_artifacts_to_plan(
    plan: dict[str, Any],
    artifacts: dict[str, Any],
) -> dict[str, Any]:
    """Add evidence-backed generation contracts to the outline plan."""
    for chapter in plan.get("chapters", []):
        for section in chapter.get("sections", []):
            refs = section.get("evidence_refs", [])
            section.setdefault("examples_plan", _example_plan_for_refs(refs, artifacts))
            section.setdefault("exercise_plan", _exercise_plan_for_refs(refs, artifacts))
    plan["generation_pipeline_version"] = PIPELINE_VERSION
    return plan


def _build_material_card(index: int, raw: Any) -> dict[str, Any]:
    data = _as_dict(raw)
    filename = str(data.get("filename") or data.get("name") or f"资料 {index}").strip()
    user_description = str(data.get("user_description") or data.get("description") or "").strip()
    usage = _normalize_choice(
        str(data.get("usage") or "content_source"),
        set(MATERIAL_USAGE_LABELS),
        "content_source",
    )
    importance = _normalize_choice(
        str(data.get("importance") or "core"),
        set(MATERIAL_IMPORTANCE_LABELS),
        "core",
    )
    file_type = str(data.get("file_type") or _infer_file_type(filename)).strip().lower()
    return {
        "material_id": str(data.get("material_id") or f"mat-{index}-{uuid.uuid4().hex[:8]}"),
        "filename": filename,
        "file_type": file_type,
        "user_description": user_description,
        "source_label": str(data.get("source_label") or "").strip(),
        "usage": usage,
        "usage_label": MATERIAL_USAGE_LABELS[usage],
        "importance": importance,
        "importance_label": MATERIAL_IMPORTANCE_LABELS[importance],
        "parse_status": "metadata_only",
        "evidence_state": "legacy_unverified",
    }


def _build_brief(
    *,
    topic: str,
    difficulty: str,
    style: str,
    requirements: str,
    target_audience: str,
    material_cards: list[dict[str, Any]],
    learner_profile_summary: str,
) -> dict[str, Any]:
    lowered = requirements.lower()
    shape_constraints = _extract_course_shape_constraints(requirements)
    unprovided = _extract_unprovided_references(requirements, material_cards)
    style_requirements = [
        "覆盖完整",
        "少废话",
        "适合自学",
        "讲清底层原理",
        "关键知识点配例题和练习",
    ]
    hard_constraints = [
        "用户上传资料优先于模型常识",
        "用户未上传资料不得作为强依据",
        "生成正文前必须先形成课程蓝图",
    ]
    if "不要" in requirements or "不能" in requirements or "avoid" in lowered:
        hard_constraints.append("遵守用户备注中的禁止项")
    if shape_constraints.get("chapter_count"):
        hard_constraints.append(
            f"课程必须恰好包含 {shape_constraints['chapter_count']} 章"
        )
    if shape_constraints.get("section_count"):
        hard_constraints.append(
            f"课程必须恰好包含 {shape_constraints['section_count']} 个小节"
        )
    return {
        "brief_id": f"brief-{uuid.uuid4().hex[:10]}",
        "goal": "生成一本高质量电子课程资料",
        "subject": topic,
        "audience": target_audience,
        "scope": "以用户上传资料和主题要求为主；无资料时按通用自学资料降级",
        "style_requirements": style_requirements,
        "difficulty": difficulty,
        "length": "章节完整、节点适中，优先保证可学性而不是堆长文",
        "example_density": "每个关键知识点至少规划例题或检查题",
        "material_usage_strategy": _material_usage_strategy(material_cards),
        "avoid_styles": [
            "晦涩教材式堆定义",
            "低质量入门式空泛比喻",
            "没有依据地伪装参考了未上传资料",
        ],
        "output_format": ["软件内课程", "Markdown 正文", "可导出 PDF 的结构"],
        "learner_profile_summary": learner_profile_summary,
        "hard_constraints": hard_constraints,
        "course_shape_constraints": shape_constraints,
        "unprovided_references": unprovided,
        "raw_requirement": requirements,
        "desired_outcomes": _extract_desired_outcomes(requirements, topic),
        "dominant_learning_actions": _extract_learning_actions(requirements),
        "expected_deliverables": _extract_deliverables(requirements),
    }


def _extract_desired_outcomes(requirements: str, topic: str) -> list[str]:
    text = str(requirements or "").strip()
    if not text:
        return [f"理解并能够应用{topic}"]
    sentences = [item.strip() for item in re.split(r"[。；;\n]", text) if item.strip()]
    markers = ("能够", "掌握", "完成", "实现", "学会", "理解", "用于")
    outcomes = [item for item in sentences if any(marker in item for marker in markers)]
    return outcomes[:6] or [f"按用户要求学习{topic}"]


def _extract_learning_actions(requirements: str) -> list[str]:
    text = str(requirements or "")
    return _dedupe([
        action for action in (
            "计算", "证明", "推导", "编写", "实现", "运行", "调试", "实验", "观察",
            "分析", "比较", "论证", "听", "说", "读", "写", "决策", "交付",
        )
        if action in text
    ])[:8]


def _extract_deliverables(requirements: str) -> list[str]:
    text = str(requirements or "")
    return _dedupe([
        item for item in (
            "项目", "程序", "证明", "实验报告", "论文", "演讲", "方案", "分析报告", "作品",
        )
        if item in text
    ])[:6]


def _extract_course_shape_constraints(requirements: str) -> dict[str, int]:
    text = str(requirements or "")
    chapter_match = re.search(
        r"(?<!第)([0-9一二两三四五六七八九十]+)\s*(?:个\s*)?章(?:节)?",
        text,
    )
    section_match = re.search(
        r"(?<!第)([0-9一二两三四五六七八九十]+)\s*(?:个\s*)?(?:递进\s*)?(?:小节|节)",
        text,
    )
    result: dict[str, int] = {}
    if chapter_match:
        value = _parse_count(chapter_match.group(1))
        if value:
            result["chapter_count"] = value
    if section_match:
        value = _parse_count(section_match.group(1))
        if value:
            result["section_count"] = value
    return result


def _parse_count(value: str) -> int | None:
    if value.isdigit():
        number = int(value)
        return number if 0 < number <= 100 else None
    digits = {
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
    }
    if value == "十":
        return 10
    if "十" in value:
        left, right = value.split("十", 1)
        tens = digits.get(left, 1) if left else 1
        ones = digits.get(right, 0) if right else 0
        return (tens * 10) + ones
    return digits.get(value)


def _format_brief(brief: dict[str, Any]) -> str:
    shape = brief.get("course_shape_constraints") or {}
    shape_text = "；".join(
        item for item in (
            f"章数：{shape.get('chapter_count')}" if shape.get("chapter_count") else "",
            f"小节数：{shape.get('section_count')}" if shape.get("section_count") else "",
        )
        if item
    ) or "未指定，由教学设计决定"
    return "\n".join([
        f"- 生成目标：{brief.get('goal', '')}",
        f"- 学科/主题：{brief.get('subject', '')}",
        f"- 学习对象：{brief.get('audience', '')}",
        f"- 难度：{brief.get('difficulty', '')}",
        f"- 讲法要求：{'；'.join(brief.get('style_requirements', []))}",
        f"- 资料使用策略：{brief.get('material_usage_strategy', '')}",
        f"- 必须避免：{'；'.join(brief.get('avoid_styles', []))}",
        f"- 用户原始备注：{brief.get('raw_requirement', '') or '无'}",
        f"- 用户明确课程形状：{shape_text}",
        f"- 期望学习成果：{'；'.join(brief.get('desired_outcomes', [])) or '理解并应用课程主题'}",
        f"- 主要学习行为：{'；'.join(brief.get('dominant_learning_actions', [])) or '由教学画像决定'}",
        f"- 预期交付物：{'；'.join(brief.get('expected_deliverables', [])) or '课程综合任务'}",
    ])


def _format_material_cards(cards: list[dict[str, Any]]) -> str:
    if not cards:
        return "- 未上传资料；本次只能按通用自学资料策略生成，并在报告中说明依据不足。"
    lines = []
    for card in cards:
        lines.append(
            f"- [{card.get('material_id')}] {card.get('filename')} "
            f"({card.get('file_type')}, {card.get('usage_label')}, {card.get('importance_label')}, {card.get('parse_status')})"
        )
        desc = card.get("user_description")
        if desc:
            lines.append(f"  - 用户说明：{desc}")
    return "\n".join(lines)


def _format_evidence_bundle(evidence: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for item in evidence:
        locator = item.get("locator") or {}
        if locator.get("page"):
            location = f"第 {locator['page']} 页"
        elif locator.get("slide"):
            location = f"第 {locator['slide']} 张幻灯片"
        else:
            location = " / ".join(locator.get("section_path") or []) or "位置未提供"
        lines.append(
            f"- [{item.get('evidence_id')}] {item.get('kind')}，{location}，"
            f"权威={item.get('authority')}：{_clip(str(item.get('source_text') or ''), 900)}"
        )
    return "\n".join(lines)


def _format_node_blueprint(node_blueprint: dict[str, Any]) -> str:
    if not node_blueprint:
        return "- 未找到节点级蓝图；按课程账本和节点字段生成。"
    return "\n".join([
        f"- 小节：{node_blueprint.get('section_number', '')} {node_blueprint.get('title', '')}",
        f"- 学习目标：{node_blueprint.get('learning_objective', '')}",
        f"- 核心知识点：{'；'.join(node_blueprint.get('knowledge_points', []))}",
        f"- 复用前序知识：{'；'.join(node_blueprint.get('reused_knowledge_names', [])) or '无'}",
        f"- 易错点：{'；'.join(node_blueprint.get('misconceptions', []))}",
        f"- 范围边界：{node_blueprint.get('scope_boundary', '')}",
        f"- 例题计划：{'；'.join(node_blueprint.get('example_plan', []))}",
        f"- 练习计划：{'；'.join(node_blueprint.get('exercise_plan', []))}",
        f"- 验收标准：{'；'.join(node_blueprint.get('assessment', []))}",
        f"- 教学模块：{'；'.join(item.get('label', '') for item in node_blueprint.get('module_plan', []))}",
        f"- 难度角色：{(node_blueprint.get('difficulty_contract') or {}).get('node_role', '')}",
    ])


def _format_pedagogy_profile(profile: dict[str, Any]) -> str:
    if not profile:
        return "- 尚未形成教学画像。"
    return "\n".join([
        f"- 主模式：{profile.get('primary_mode', '')}",
        f"- 辅模式：{profile.get('secondary_mode') or '无'}",
        f"- 辅助强度：{profile.get('secondary_intensity') or '无'}",
        f"- 置信度：{profile.get('confidence', '')}",
        f"- 判断依据：{'；'.join(profile.get('evidence', []))}",
        f"- 组合理由：{profile.get('rationale', '')}",
    ])


def _format_module_plan(modules: list[dict[str, Any]]) -> str:
    if not modules:
        return "- 使用通用本节任务、核心教学、学习者行动和反馈检查。"
    return "\n".join(
        f"- [{item.get('module_id')}] {item.get('label')}：{item.get('output_contract')}"
        for item in modules
    )


def _format_adaptation(
    assessment: dict[str, Any],
    decision: dict[str, Any],
) -> str:
    if not assessment or not decision:
        return "- 尚未形成入口适配决策。"
    return "\n".join([
        f"- 当前就绪度：{assessment.get('current_readiness') or '未知'}",
        f"- 差距：{assessment.get('gap') if assessment.get('gap') is not None else '待诊断'}",
        f"- 适配策略：{decision.get('strategy', '')}",
        f"- 保留目标难度：{'是' if decision.get('preserve_target', True) else '否'}",
        f"- 必要动作：{'；'.join(decision.get('actions', []))}",
    ])


def _find_blueprint_node(blueprint: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    node_id = str(node.get("node_id") or "")
    node_name = str(node.get("node_name") or "")
    for item in blueprint.get("nodes", []):
        section_number = str(item.get("section_number") or "")
        if item.get("node_id") == node_id or (section_number and section_number in node_name):
            return item
    return {}


def _example_plan_for_refs(refs: list[str], artifacts: dict[str, Any]) -> list[str]:
    evidence = artifacts.get("evidence_catalog", [])
    has_questions = any(
        item.get("purpose") == "question_source" or item.get("kind") == "question"
        for item in evidence if item.get("evidence_id") in refs
    )
    if has_questions:
        return ["从题目资料中抽取典型题", "为核心概念补一题同类练习"]
    return ["为核心知识点配置典型例题", "必要时补一个反例或边界例子"]


def _exercise_plan_for_refs(refs: list[str], artifacts: dict[str, Any]) -> list[str]:
    evidence = artifacts.get("evidence_catalog", [])
    if any(
        item.get("purpose") == "question_source" or item.get("kind") == "question"
        for item in evidence if item.get("evidence_id") in refs
    ):
        return ["把题目资料中的同类题改写为检查题", "给出关键步骤解析"]
    return ["设置 1-2 个自测问题", "用简短解析检查是否真正理解"]


def _material_usage_strategy(cards: list[dict[str, Any]]) -> str:
    if not cards:
        return "无上传资料；使用通用电子课程资料模板，并明确说明依据不足。"
    grouped: dict[str, list[str]] = {}
    for card in cards:
        grouped.setdefault(card.get("usage_label", "资料"), []).append(card.get("filename", "未命名资料"))
    return "；".join(f"{usage}：{', '.join(names[:4])}" for usage, names in grouped.items())


def _extract_unprovided_references(requirements: str, cards: list[dict[str, Any]]) -> list[str]:
    if not requirements:
        return []
    uploaded_text = " ".join([card.get("filename", "") + " " + card.get("user_description", "") for card in cards])
    candidates = []
    patterns = [
        r"([^，。；\n]{1,20}(?:老师|教材|课本|讲义|资料|PPT|试卷|真题))",
        r"参考([^，。；\n]{1,24})",
    ]
    for pattern in patterns:
        for match in re.findall(pattern, requirements):
            text = _normalize_reference_candidate(str(match))
            if text and not _reference_is_covered(text, uploaded_text) and text not in candidates:
                candidates.append(text)
    return candidates[:8]


def _normalize_reference_candidate(text: str) -> str:
    text = re.sub(r"\s+", "", text.strip(" ：:，。；;"))
    text = re.sub(r"^(参考|根据|依据|按照|按|结合|使用|用|把|将|拿)", "", text)
    text = re.sub(r"(但未上传|没有上传|未上传|来生成|作为依据|当参考)$", "", text)
    return text.strip(" ：:，。；;")


def _reference_is_covered(reference: str, uploaded_text: str) -> bool:
    if not reference:
        return True
    uploaded = re.sub(r"\s+", "", uploaded_text)
    if reference in uploaded:
        return True
    markers = ["真题", "试卷", "题库", "PPT", "ppt", "课件", "教材", "课本", "讲义", "资料"]
    return any(marker in reference and marker in uploaded for marker in markers)


def _infer_file_type(filename: str) -> str:
    suffix = Path(filename).suffix.lower().lstrip(".")
    return suffix or "text"


def _normalize_choice(value: str, allowed: set[str], fallback: str) -> str:
    value = value.strip()
    if value in allowed:
        return value
    reverse_usage = {label: key for key, label in MATERIAL_USAGE_LABELS.items()}
    reverse_importance = {label: key for key, label in MATERIAL_IMPORTANCE_LABELS.items()}
    return reverse_usage.get(value) or reverse_importance.get(value) or fallback


def _clip(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _dedupe(items: list[str]) -> list[str]:
    result = []
    seen = set()
    for item in items:
        if item and item not in seen:
            result.append(item)
            seen.add(item)
    return result


def _as_dict(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if hasattr(raw, "model_dump"):
        return raw.model_dump()
    if hasattr(raw, "dict"):
        return raw.dict()
    return {"description": str(raw)}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
