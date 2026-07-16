"""Deterministic course-wide editorial contract and coherence quality checks."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

from course_document import course_view_from_document
from course_knowledge_base import compile_course_knowledge_base
from course_versioning import stable_hash


COURSE_COHERENCE_SCHEMA = "course_coherence_v2"
COURSE_COHERENCE_QUALITY_SCHEMA = "course_coherence_quality_v2"


def compile_course_coherence_contract(course_data: dict[str, Any]) -> dict[str, Any]:
    """Compile one stable editorial contract from the ordered course blueprint."""
    course_view = _course_with_projected_nodes(course_data)
    sections = _sections(course_view)
    knowledge_base = course_view.get("course_knowledge_base") or compile_course_knowledge_base(
        course_view
    )
    knowledge_by_id = {
        str(item.get("node_id") or ""): item
        for item in knowledge_base.get("nodes") or []
    }
    capability_by_id = {
        str(item.get("capability_point_id") or ""): item
        for item in knowledge_base.get("capability_points") or []
    }
    mistake_by_id = {
        str(item.get("mistake_point_id") or ""): item
        for item in knowledge_base.get("mistake_points") or []
    }
    binding_by_section = knowledge_base.get("section_bindings") or {}

    section_rows: list[dict[str, Any]] = []
    for order, section in enumerate(sections):
        section_id = str(section.get("node_id") or "")
        binding = binding_by_section.get(section_id) or {}
        knowledge_items = [
            knowledge_by_id[item_id]
            for item_id in binding.get("knowledge_node_ids") or []
            if item_id in knowledge_by_id
            and knowledge_by_id[item_id].get("node_type") == "knowledge_point"
        ]
        capabilities = [
            capability_by_id[item_id]
            for item_id in binding.get("capability_point_ids") or []
            if item_id in capability_by_id
        ]
        mistakes = [
            mistake_by_id[item_id]
            for item_id in binding.get("mistake_point_ids") or []
            if item_id in mistake_by_id
        ]
        explicit_prerequisites = _unique(section.get("prerequisite_node_ids") or [])
        context_predecessors = list(explicit_prerequisites)
        if not context_predecessors and order:
            context_predecessors = [str(sections[order - 1].get("node_id") or "")]
        section_rows.append({
            "node_id": section_id,
            "order": order,
            "chapter_id": str(section.get("parent_node_id") or ""),
            "title": str(section.get("node_name") or ""),
            "progression_role": _progression_role(order, len(sections)),
            "learning_objective": str(section.get("learning_objective") or "").strip(),
            "scope_boundary": str(section.get("scope_boundary") or "").strip(),
            "assessment": _unique(section.get("assessment") or []),
            "knowledge_names": _unique(
                [item.get("name") for item in knowledge_items]
                or section.get("key_points")
                or []
            ),
            "capability_names": _unique([
                item.get("observable_behavior") or item.get("name")
                for item in capabilities
            ]),
            "mistake_names": _unique([
                item.get("error_pattern") or item.get("name")
                for item in mistakes
            ]),
            "explicit_prerequisite_ids": explicit_prerequisites,
            "context_predecessor_ids": _unique(context_predecessors),
            "difficulty_signature": _difficulty_signature(section),
        })

    rows_by_id = {row["node_id"]: row for row in section_rows}
    for order, row in enumerate(section_rows):
        predecessors = [
            rows_by_id[item_id]
            for item_id in row["context_predecessor_ids"]
            if item_id in rows_by_id
        ]
        row["required_handoff_terms"] = _unique([
            name
            for predecessor in predecessors
            for name in (
                predecessor.get("knowledge_names")
                or predecessor.get("capability_names")
                or []
            )
        ])[:8]
        next_row = section_rows[order + 1] if order + 1 < len(section_rows) else None
        row["next_section_id"] = next_row["node_id"] if next_row else None
        row["next_section_title"] = next_row["title"] if next_row else None
        row["next_learning_objective"] = (
            next_row["learning_objective"] if next_row else None
        )
        current_names = {_normalize_name(item) for item in row["knowledge_names"]}
        row["reserved_for_later"] = [
            item for item in (next_row or {}).get("knowledge_names", [])
            if _normalize_name(item) not in current_names
        ][:8]

    payload = {
        "schema_version": COURSE_COHERENCE_SCHEMA,
        "course_id": str(course_data.get("course_id") or ""),
        "course_name": str(course_data.get("course_name") or ""),
        "knowledge_base_revision_id": knowledge_base.get("revision_id"),
        "ordered_section_ids": [row["node_id"] for row in section_rows],
        "canonical_terms": _canonical_terms(knowledge_base),
        "section_contracts": section_rows,
        "status": "active",
    }
    payload["revision_id"] = stable_hash(payload, prefix="ccr_")
    payload["quality_report"] = validate_course_coherence_contract(
        payload,
        course_data=course_view,
    )
    return payload


def validate_course_coherence_contract(
    contract: dict[str, Any],
    *,
    course_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate order, dependencies and unique section responsibilities."""
    issues: list[dict[str, Any]] = []
    rows = list(contract.get("section_contracts") or [])
    ordered_ids = [str(item.get("node_id") or "") for item in rows]
    if not rows:
        issues.append(_issue(
            "coherence:no_sections",
            "critical",
            "课程一致性契约没有可学习小节",
            blocking=True,
        ))
    if not all(ordered_ids) or len(set(ordered_ids)) != len(ordered_ids):
        issues.append(_issue(
            "coherence:invalid_section_identity",
            "critical",
            "课程一致性契约存在空或重复的小节 ID",
            blocking=True,
        ))

    if course_data is not None:
        expected = [str(item.get("node_id") or "") for item in _sections(course_data)]
        if ordered_ids != expected:
            issues.append(_issue(
                "coherence:section_order_mismatch",
                "critical",
                "课程一致性契约与正式课程小节顺序不一致",
                blocking=True,
            ))

    position = {node_id: index for index, node_id in enumerate(ordered_ids)}
    objective_owners: dict[str, str] = {}
    for row in rows:
        node_id = str(row.get("node_id") or "")
        for prerequisite_id in row.get("explicit_prerequisite_ids") or []:
            if prerequisite_id not in position:
                issues.append(_issue(
                    "coherence:unknown_prerequisite",
                    "critical",
                    f"{node_id} 引用了不存在的前置小节 {prerequisite_id}",
                    node_id=node_id,
                    blocking=True,
                ))
            elif position[prerequisite_id] >= position.get(node_id, -1):
                issues.append(_issue(
                    "coherence:forward_prerequisite",
                    "critical",
                    f"{node_id} 的前置依赖没有出现在它之前",
                    node_id=node_id,
                    related_node_id=prerequisite_id,
                    blocking=True,
                ))
        if not str(row.get("learning_objective") or "").strip():
            issues.append(_issue(
                "coherence:missing_objective",
                "major",
                f"{node_id} 缺少独立学习目标",
                node_id=node_id,
                blocking=True,
            ))
        if not row.get("knowledge_names") or not row.get("capability_names"):
            issues.append(_issue(
                "coherence:missing_responsibility",
                "major",
                f"{node_id} 没有明确知识推进或可观察能力",
                node_id=node_id,
                blocking=True,
            ))
        normalized_objective = _normalize_name(row.get("learning_objective"))
        if normalized_objective and normalized_objective in objective_owners:
            issues.append(_issue(
                "coherence:duplicate_objective",
                "warning",
                f"{node_id} 与前面小节使用了相同学习目标",
                node_id=node_id,
                related_node_id=objective_owners[normalized_objective],
            ))
        elif normalized_objective:
            objective_owners[normalized_objective] = node_id

    alias_owners: dict[str, str] = {}
    for term in contract.get("canonical_terms") or []:
        canonical = str(term.get("canonical_name") or "")
        for alias in term.get("aliases") or []:
            normalized_alias = _normalize_name(alias)
            owner = alias_owners.get(normalized_alias)
            if normalized_alias and owner and owner != canonical:
                issues.append(_issue(
                    "coherence:ambiguous_term",
                    "major",
                    f"术语别名“{alias}”同时指向“{owner}”和“{canonical}”",
                    blocking=True,
                ))
            elif normalized_alias:
                alias_owners[normalized_alias] = canonical

    return _quality_report(issues, section_count=len(rows))


def evaluate_course_coherence(course_data: dict[str, Any]) -> dict[str, Any]:
    """Evaluate course-wide continuity without replacing subject-specific checks."""
    course_view = _course_with_projected_nodes(course_data)
    contract = compile_course_coherence_contract(course_view)
    issues = list((contract.get("quality_report") or {}).get("issues") or [])
    sections = _sections(course_view)
    sections_by_id = {str(item.get("node_id") or ""): item for item in sections}
    rows_by_id = {
        str(item.get("node_id") or ""): item
        for item in contract.get("section_contracts") or []
    }

    bridge_count = 0
    for node_id, row in rows_by_id.items():
        content = str((sections_by_id.get(node_id) or {}).get("node_content") or "")
        explicit = list(row.get("explicit_prerequisite_ids") or [])
        if not content or not explicit:
            continue
        predecessor_terms = _unique([
            term
            for predecessor_id in explicit
            for term in (rows_by_id.get(predecessor_id) or {}).get("knowledge_names", [])
        ])
        if predecessor_terms and not _has_predecessor_bridge(content, predecessor_terms):
            bridge_count += 1
            issues.append(_issue(
                "coherence:missing_prerequisite_bridge",
                "warning",
                f"{node_id} 没有明确承接其前置小节的核心知识",
                node_id=node_id,
                related_node_id=explicit[0],
            ))

    duplicate_pairs = _duplicate_paragraph_pairs(sections)
    for duplicate in duplicate_pairs:
        issues.append(_issue(
            "coherence:duplicate_explanation",
            "major",
            (
                f"{duplicate['node_id']} 与 {duplicate['related_node_id']} "
                f"存在近乎重复的实质讲解"
            ),
            node_id=duplicate["node_id"],
            related_node_id=duplicate["related_node_id"],
            blocking=True,
            repairable=True,
            similarity=duplicate["similarity"],
            excerpt=duplicate["excerpt"],
        ))

    incorrect_handoffs = _incorrect_next_section_handoffs(sections, rows_by_id)
    for handoff in incorrect_handoffs:
        issues.append(_issue(
            "coherence:incorrect_next_section_handoff",
            "major",
            (
                f"{handoff['node_id']} 把本节已完成的内容误写成下一节任务，"
                f"实际下一节是 {handoff['next_section_title']}"
            ),
            node_id=handoff["node_id"],
            related_node_id=handoff["next_section_id"],
            blocking=True,
            repairable=True,
            excerpt=handoff["excerpt"],
        ))

    report = _quality_report(issues, section_count=len(sections))
    report.update({
        "contract_revision_id": contract.get("revision_id"),
        "knowledge_base_revision_id": contract.get("knowledge_base_revision_id"),
        "duplicate_pair_count": len(duplicate_pairs),
        "missing_bridge_count": bridge_count,
        "incorrect_handoff_count": len(incorrect_handoffs),
        "repairable_node_ids": _unique([
            item.get("node_id") for item in issues if item.get("repairable")
        ]),
    })
    return report


def course_coherence_prompt_context(
    course_data: dict[str, Any],
    node_id: str,
) -> str:
    """Render the minimum course-wide context needed for one section."""
    course_data = _course_with_projected_nodes(course_data)
    contract = course_data.get("course_coherence_contract")
    expected_ids = [str(item.get("node_id") or "") for item in _sections(course_data)]
    knowledge_base = course_data.get("course_knowledge_base") or {}
    expected_knowledge_revision = knowledge_base.get("revision_id")
    if (
        not isinstance(contract, dict)
        or contract.get("schema_version") != COURSE_COHERENCE_SCHEMA
        or contract.get("ordered_section_ids") != expected_ids
        or (
            expected_knowledge_revision
            and contract.get("knowledge_base_revision_id") != expected_knowledge_revision
        )
    ):
        contract = compile_course_coherence_contract(course_data)
    rows = list(contract.get("section_contracts") or [])
    row = next((item for item in rows if item.get("node_id") == node_id), None)
    if not row:
        return "当前节点不在课程一致性契约中；只履行当前蓝图，不扩写其他章节。"
    rows_by_id = {str(item.get("node_id") or ""): item for item in rows}
    predecessors = [
        rows_by_id[item_id]
        for item_id in row.get("context_predecessor_ids") or []
        if item_id in rows_by_id
    ]
    predecessor_text = "；".join(
        f"{item.get('title')} -> {item.get('learning_objective')}"
        for item in predecessors
    ) or "无"
    current_terms = set(row.get("knowledge_names") or [])
    canonical = [
        item for item in contract.get("canonical_terms") or []
        if item.get("canonical_name") in current_terms
    ]
    terminology = "；".join(
        f"{item.get('canonical_name')}（别名：{'、'.join(item.get('aliases') or []) or '无'}）"
        for item in canonical[:12]
    ) or "沿用当前课程知识库中的规范名称"
    if row.get("next_section_id"):
        next_section = (
            f"{row.get('next_section_title')} -> "
            f"{row.get('next_learning_objective') or '后续小节学习目标'}"
        )
    else:
        next_section = "无，本节是全课收束"
    return "\n".join([
        f"- 课程位置：第 {int(row.get('order') or 0) + 1}/{len(rows)} 节；角色：{row.get('progression_role')}",
        f"- 必须承接：{predecessor_text}",
        f"- 本节唯一推进：{row.get('learning_objective') or '当前节点学习目标'}",
        f"- 本节知识责任：{'；'.join(row.get('knowledge_names') or []) or '无'}",
        f"- 本节能力产出：{'；'.join(row.get('capability_names') or []) or '无'}",
        f"- 允许简短回顾但不得重新讲成另一节：{'；'.join(row.get('required_handoff_terms') or []) or '无'}",
        f"- 留给后续节点展开：{'；'.join(row.get('reserved_for_later') or []) or '无'}",
        f"- 本节之后实际进入：{next_section}",
        f"- 术语口径：{terminology}",
        "- 写作要求：先建立与前置输出的关系，再推进本节新能力；不得复制前节实质段落，不得提前完成后续小节的主要任务，也不得把本节已经讲完的内容误写成下一节任务。",
    ])


def _sections(course_data: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item for item in course_data.get("nodes") or []
        if int(item.get("node_level") or 1) == 2
    ]


def _course_with_projected_nodes(course_data: dict[str, Any]) -> dict[str, Any]:
    if course_data.get("nodes") or not isinstance(course_data.get("course_document"), dict):
        return course_data
    return course_view_from_document(course_data, course_data["course_document"])


def _canonical_terms(knowledge_base: dict[str, Any]) -> list[dict[str, Any]]:
    registry: dict[str, dict[str, Any]] = {}
    for node in knowledge_base.get("nodes") or []:
        if node.get("node_type") != "knowledge_point":
            continue
        name = str(node.get("name") or "").strip()
        if not name:
            continue
        key = _normalize_name(name)
        item = registry.setdefault(key, {
            "canonical_name": name,
            "aliases": [],
            "section_ids": [],
        })
        item["aliases"] = _unique([*item["aliases"], *(node.get("aliases") or [])])
        item["section_ids"] = _unique([*item["section_ids"], *(node.get("section_refs") or [])])
    return list(registry.values())


def _difficulty_signature(section: dict[str, Any]) -> dict[str, Any]:
    contract = section.get("difficulty_contract") or {}
    challenge = contract.get("challenge") or {}
    support = contract.get("support") or {}
    mastery = contract.get("mastery") or {}
    return {
        "reasoning_depth": challenge.get("reasoning_depth"),
        "transfer_distance": challenge.get("transfer_distance"),
        "task_complexity": challenge.get("task_complexity"),
        "scaffold_intensity": support.get("scaffold_intensity"),
        "independence": mastery.get("independence"),
        "subject_task": contract.get("subject_task"),
    }


def _progression_role(order: int, total: int) -> str:
    if order == 0:
        return "foundation"
    if order == total - 1:
        return "synthesis"
    return "development"


def _duplicate_paragraph_pairs(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    paragraph_sets = {
        str(section.get("node_id") or ""): _substantive_paragraphs(
            str(section.get("node_content") or "")
        )
        for section in sections
    }
    duplicates: list[dict[str, Any]] = []
    ordered_ids = list(paragraph_sets)
    for current_index in range(1, len(ordered_ids)):
        current_id = ordered_ids[current_index]
        best: dict[str, Any] | None = None
        for previous_id in ordered_ids[:current_index]:
            for current in paragraph_sets[current_id]:
                for previous in paragraph_sets[previous_id]:
                    ratio = SequenceMatcher(None, current, previous, autojunk=False).ratio()
                    if ratio < 0.92:
                        continue
                    candidate = {
                        "node_id": current_id,
                        "related_node_id": previous_id,
                        "similarity": round(ratio, 3),
                        "excerpt": current[:180],
                    }
                    if best is None or candidate["similarity"] > best["similarity"]:
                        best = candidate
        if best:
            duplicates.append(best)
    return duplicates


def _substantive_paragraphs(content: str) -> list[str]:
    paragraphs: list[str] = []
    for raw in re.split(r"\n\s*\n", content):
        if raw.lstrip().startswith(("#", "```", "|", ">")):
            continue
        text = re.sub(r"\[\[evidence:[^\]]+\]\]", "", raw)
        text = re.sub(r"[`*_>#\[\]()]", "", text)
        text = re.sub(r"\s+", "", text).strip()
        if len(text) < 120 or len(text) > 1200:
            continue
        if any(marker in text[:30] for marker in ("请完成", "请尝试", "检查是否", "学习目标")):
            continue
        paragraphs.append(text)
    return paragraphs


def _incorrect_next_section_handoffs(
    sections: list[dict[str, Any]],
    rows_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for section in sections:
        node_id = str(section.get("node_id") or "")
        row = rows_by_id.get(node_id) or {}
        next_section_id = str(row.get("next_section_id") or "")
        next_row = rows_by_id.get(next_section_id) or {}
        if not next_row:
            continue
        current_terms = [
            *(row.get("knowledge_names") or []),
            *(row.get("capability_names") or []),
        ]
        expected_terms = [
            next_row.get("title"),
            next_row.get("learning_objective"),
            *(next_row.get("knowledge_names") or []),
            *(next_row.get("capability_names") or []),
        ]
        for claim in _next_section_claims(str(section.get("node_content") or "")):
            if _claim_matches_terms(claim, expected_terms):
                continue
            if not _claim_matches_terms(claim, current_terms):
                continue
            issues.append({
                "node_id": node_id,
                "next_section_id": next_section_id,
                "next_section_title": str(next_row.get("title") or next_section_id),
                "excerpt": claim[:220],
            })
            break
    return issues


def _next_section_claims(content: str) -> list[str]:
    plain = re.sub(r"[`*_>#\[\]()]", "", content)
    return _unique(
        match.group(0).strip()
        for match in re.finditer(
            r"[^。！？\n]{0,80}下一节[^。！？\n]{0,120}[。！？]?",
            plain,
        )
    )


def _claim_matches_terms(claim: str, terms: list[Any]) -> bool:
    return any(
        _concept_mentioned(claim, str(term or ""))
        or _shares_concept_bigrams(claim, str(term or ""))
        for term in terms
        if str(term or "").strip()
    )


def _shares_concept_bigrams(text: str, concept: str) -> bool:
    normalized_text = _normalize_name(text)
    normalized_concept = _normalize_name(concept)
    if len(normalized_concept) < 4:
        return False
    text_bigrams = {
        normalized_text[index:index + 2]
        for index in range(max(0, len(normalized_text) - 1))
    }
    concept_bigrams = {
        normalized_concept[index:index + 2]
        for index in range(len(normalized_concept) - 1)
    }
    return len(text_bigrams & concept_bigrams) >= 2


def _concept_mentioned(content: str, concept: str) -> bool:
    compact_content = _normalize_name(content)
    compact_concept = _normalize_name(concept)
    if compact_concept and compact_concept in compact_content:
        return True
    fragments = [
        item for item in re.split(r"[与和及、，,:：;；/（）()\s]+", str(concept or ""))
        if len(_normalize_name(item)) >= 2
    ]
    return bool(fragments) and sum(
        _normalize_name(item) in compact_content for item in fragments
    ) >= max(1, (len(fragments) + 1) // 2)


def _has_predecessor_bridge(content: str, terms: list[str]) -> bool:
    if any(_concept_mentioned(content, term) for term in terms):
        return True
    opening = content[:1200]
    return any(marker in opening for marker in (
        "上一节",
        "前一节",
        "前面已经",
        "此前",
        "已经掌握",
        "已经学习",
        "已经建立",
        "在此基础",
        "在前面的",
        "回顾前置",
    ))


def _normalize_name(value: Any) -> str:
    return re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "", str(value or "").lower())


def _unique(values: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _issue(
    code: str,
    severity: str,
    message: str,
    *,
    node_id: str = "",
    related_node_id: str = "",
    blocking: bool = False,
    repairable: bool = False,
    **details: Any,
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "node_id": node_id,
        "related_node_id": related_node_id,
        "blocking": blocking,
        "repairable": repairable,
        **details,
    }


def _quality_report(issues: list[dict[str, Any]], *, section_count: int) -> dict[str, Any]:
    blocking = [item for item in issues if item.get("blocking")]
    strict_issues = [
        item for item in issues if item.get("severity") in {"critical", "major", "warning"}
    ]
    return {
        "schema_version": COURSE_COHERENCE_QUALITY_SCHEMA,
        "passed": not blocking,
        "strict_passed": not strict_issues,
        "section_count": section_count,
        "blocking_count": len(blocking),
        "warning_count": sum(item.get("severity") == "warning" for item in issues),
        "issues": issues,
        "blocking_issues": blocking,
    }


__all__ = [
    "COURSE_COHERENCE_SCHEMA",
    "COURSE_COHERENCE_QUALITY_SCHEMA",
    "compile_course_coherence_contract",
    "validate_course_coherence_contract",
    "evaluate_course_coherence",
    "course_coherence_prompt_context",
]
