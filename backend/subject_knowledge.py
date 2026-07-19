"""Versioned knowledge libraries shared by courses, practice, models, and AI."""

from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path
import re
from typing import Any

from course_versioning import stable_hash


SUBJECT_LIBRARY_SCHEMA = "knowledge_library_v2"
SUBJECT_VIEW_SCHEMA = "knowledge_library_view_v3"
KNOWLEDGE_SLICE_SCHEMA = "knowledge_library_slice_v2"
CATALOG_DIR = Path(__file__).resolve().parent / "catalogs" / "subject_knowledge"
NODE_TYPES = ("subject", "domain", "topic", "concept", "knowledge_point")


@lru_cache(maxsize=16)
def load_subject_library(library_id: str) -> dict[str, Any]:
    """Load and validate one curated library by stable library ID."""
    for path in sorted(CATALOG_DIR.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        if str(raw.get("library_id") or "") != library_id:
            continue
        library = _normalize_library(raw)
        issues = validate_subject_library(library)
        if issues:
            raise ValueError(f"Invalid subject library {library_id}: {'; '.join(issues)}")
        return library
    raise KeyError(f"Unknown subject library: {library_id}")


@lru_cache(maxsize=1)
def available_subject_libraries() -> tuple[dict[str, Any], ...]:
    summaries: list[dict[str, Any]] = []
    for path in sorted(CATALOG_DIR.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        summaries.append({
            "library_id": str(raw.get("library_id") or ""),
            "subject_id": str(raw.get("subject_id") or ""),
            "version": str(raw.get("version") or ""),
            "match_terms": [str(item) for item in raw.get("match_terms") or []],
        })
    return tuple(summaries)


def resolve_subject_library(source: str | dict[str, Any]) -> dict[str, Any]:
    """Resolve only a pinned revision or a curated library; reads never generate one."""
    if isinstance(source, dict) and source.get("knowledge_library_binding"):
        try:
            from subject_library_repository import subject_library_repository

            bound = subject_library_repository.resolve_for_course(source)
            if bound is not None:
                return bound
        except (KeyError, ValueError):
            pass
    hint = _subject_hint(source)
    normalized_hint = _normalize_text(hint)
    best: tuple[int, str] | None = None
    for summary in available_subject_libraries():
        score = 0
        for term in summary.get("match_terms") or []:
            normalized_term = _normalize_text(term)
            if normalized_term and normalized_term in normalized_hint:
                score = max(score, len(normalized_term))
        if score and (best is None or score > best[0]):
            best = (score, str(summary["library_id"]))
    if best:
        return deepcopy(load_subject_library(best[1]))
    return {
        "schema_version": SUBJECT_LIBRARY_SCHEMA,
        "library_id": "unresolved",
        "subject_id": "unresolved",
        "version": "0",
        "title": hint or "未识别学科",
        "root_node_id": None,
        "match_terms": [],
        "nodes": [],
        "relations": [],
        "skill_units": [],
        "mistake_points": [],
        "improvement_points": [],
        "usage_policy": _usage_policy(),
        "status": "unavailable",
        "revision_id": stable_hash({"subject_hint": hint, "status": "unavailable"}, prefix="skl_"),
    }


def _build_course_derived_library(course_data: dict[str, Any]) -> dict[str, Any] | None:
    """Build a deterministic provisional library when no curated subject catalog exists.

    Generated IDs are owned by this compiler rather than the language model. The
    resulting library is stored in the course learning assets and can later be
    replaced by a curated subject catalog without changing the course outline.
    """
    topics = _course_topics(course_data)
    if not topics:
        return None

    course_id = str(course_data.get("course_id") or "").strip()
    title = str(course_data.get("subject") or course_data.get("course_name") or "课程知识库").strip()
    # Keep the namespace stable across normal course evolution. Individual
    # topic/point IDs are derived from their canonical names below, while the
    # library revision still changes whenever the generated content changes.
    identity_seed = (
        {"course_id": course_id}
        if course_id
        else {"title": _normalize_text(title)}
    )
    identity = stable_hash(identity_seed)
    namespace = f"generated.{identity}"
    root_id = f"{namespace}.subject"
    domain_id = f"{namespace}.course"
    source_ref = f"course:{course_id or identity}"

    point_ids: dict[str, str] = {}
    topic_children: list[dict[str, Any]] = []
    for topic_order, topic in enumerate(topics):
        topic_id = f"{namespace}.topic.{stable_hash({'name': topic['name']})}"
        point_children: list[dict[str, Any]] = []
        for point_order, point in enumerate(topic["points"]):
            normalized_name = _normalize_text(point["name"])
            point_id = point_ids.setdefault(
                normalized_name,
                f"{namespace}.kp.{stable_hash({'name': normalized_name})}",
            )
            point_children.append({
                "knowledge_id": point_id,
                "node_type": "knowledge_point",
                "name": point["name"],
                "aliases": point["aliases"],
                "description": point["description"],
                "learning_actions": [point["capability"]] if point["capability"] else [],
                "typical_problems": [],
                "source_refs": [source_ref],
                "source_status": "course_generated",
                "status": "provisional",
                "sort_order": point_order,
            })
        topic_children.append({
            "knowledge_id": topic_id,
            "node_type": "concept",
            "name": topic["name"],
            "description": topic["description"],
            "learning_actions": [],
            "source_refs": [source_ref],
            "source_status": "course_generated",
            "status": "provisional",
            "sort_order": topic_order,
            "children": point_children,
        })

    raw_library = {
        "schema_version": SUBJECT_LIBRARY_SCHEMA,
        "library_id": namespace,
        "subject_id": namespace,
        "version": "1.0.0-provisional",
        "title": f"{title}·课程派生知识库",
        "match_terms": [title, str(course_data.get("course_name") or "")],
        "source_refs": [source_ref],
        "tree": {
            "knowledge_id": root_id,
            "node_type": "subject",
            "name": title,
            "description": "根据新课程结构自动建立、等待后续学科治理的知识体系。",
            "source_status": "course_generated",
            "status": "provisional",
            "children": [{
                "knowledge_id": domain_id,
                "node_type": "domain",
                "name": str(course_data.get("course_name") or title),
                "description": "本课程覆盖的知识主题、知识点与能力要求。",
                "source_status": "course_generated",
                "status": "provisional",
                "children": topic_children,
            }],
        },
        "relations": _generated_knowledge_relations(namespace, topics, point_ids),
        **_generated_teaching_standards(namespace, topics, point_ids),
        "skill_relations": [],
    }
    library = _normalize_library(raw_library)
    library.update({
        "status": "provisional",
        "origin": "course_generation",
        "generated_from_course_id": course_id,
        "governance_status": "pending_curation",
    })
    library["revision_id"] = stable_hash(library, prefix="skl_")
    return library


def _course_topics(course_data: dict[str, Any]) -> list[dict[str, Any]]:
    topics_by_name: dict[str, dict[str, Any]] = {}
    point_owner: dict[str, str] = {}
    for section in course_data.get("nodes") or []:
        if int(section.get("node_level") or 1) != 2:
            continue
        structures = [item for item in section.get("knowledge_structure") or [] if isinstance(item, dict)]
        if not structures:
            structures = [{
                "topic": section.get("node_name") or section.get("title") or "课程知识",
                "description": section.get("learning_objective") or "",
                "knowledge_points": section.get("key_points") or [section.get("node_name")],
            }]
        for structure in structures:
            topic_name = str(structure.get("topic") or structure.get("name") or "").strip()
            if not topic_name:
                continue
            topic_key = _normalize_text(topic_name)
            topic = topics_by_name.setdefault(topic_key, {
                "name": topic_name,
                "description": str(structure.get("description") or "").strip(),
                "points": [],
            })
            for raw_point in structure.get("knowledge_points") or []:
                point = _course_point(raw_point)
                if point is None:
                    continue
                point_key = _normalize_text(point["name"])
                if not point_key or point_key in point_owner:
                    continue
                point_owner[point_key] = topic_key
                topic["points"].append(point)
    return [topic for topic in topics_by_name.values() if topic["points"]]


def _course_point(raw_point: Any) -> dict[str, Any] | None:
    if isinstance(raw_point, str):
        name = raw_point.strip()
        source: dict[str, Any] = {}
    elif isinstance(raw_point, dict):
        source = raw_point
        name = str(source.get("name") or source.get("knowledge_point") or "").strip()
    else:
        return None
    if not name:
        return None
    capability = str(source.get("capability") or f"能够解释并应用{name}").strip()
    return {
        "name": name,
        "description": str(source.get("description") or "").strip(),
        "capability": capability,
        "aliases": list(dict.fromkeys(
            str(item).strip() for item in source.get("aliases") or [] if str(item).strip()
        )),
        "prerequisite_names": list(dict.fromkeys(
            str(item).strip()
            for item in source.get("prerequisite_names") or []
            if str(item).strip()
        )),
    }


def _generated_knowledge_relations(
    namespace: str,
    topics: list[dict[str, Any]],
    point_ids: dict[str, str],
) -> list[dict[str, Any]]:
    relations: list[dict[str, Any]] = []
    for topic in topics:
        for point in topic["points"]:
            target_id = point_ids.get(_normalize_text(point["name"]))
            for prerequisite_name in point["prerequisite_names"]:
                source_id = point_ids.get(_normalize_text(prerequisite_name))
                if not source_id or not target_id or source_id == target_id:
                    continue
                relations.append({
                    "relation_id": f"{namespace}.relation.{stable_hash({'source': source_id, 'target': target_id})}",
                    "source_knowledge_id": source_id,
                    "target_knowledge_id": target_id,
                    "relation_type": "prerequisite",
                    "reason": f"课程将“{prerequisite_name}”列为“{point['name']}”的前置知识。",
                    "source_status": "course_generated",
                    "status": "candidate",
                })
    return relations


def _generated_teaching_standards(
    namespace: str,
    topics: list[dict[str, Any]],
    point_ids: dict[str, str],
) -> dict[str, list[dict[str, Any]]]:
    skills: list[dict[str, Any]] = []
    mistakes: list[dict[str, Any]] = []
    improvements: list[dict[str, Any]] = []
    for topic in topics:
        for point in topic["points"]:
            point_id = point_ids[_normalize_text(point["name"])]
            suffix = stable_hash({"point": point_id})
            skill_id = f"skill.generated.{suffix}"
            mistake_id = f"mistake.generated.{suffix}"
            improvement_id = f"improve.generated.{suffix}"
            skills.append({
                "skill_unit_id": skill_id,
                "name": point["capability"],
                "description": point["description"] or point["capability"],
                "learning_goal": point["capability"],
                "primary_knowledge_id": point_id,
                "knowledge_ids": [point_id],
                "source_status": "course_generated",
            })
            mistakes.append({
                "mistake_point_id": mistake_id,
                "skill_unit_id": skill_id,
                "name": f"{point['name']}：忽略适用条件或边界",
                "description": "只记结论或步骤，没有检查定义、适用条件和边界情况。",
                "misconception": "把局部示例当成无条件成立的通用规则。",
                "symptom": "答案缺少条件说明、过程验证或边界检查。",
                "repair_strategy": "回到定义，按条件、过程、结果检查三步重新作答。",
                "severity": "medium",
                "primary_knowledge_id": point_id,
                "knowledge_ids": [point_id],
                "source_status": "course_generated",
            })
            improvements.append({
                "improvement_point_id": improvement_id,
                "skill_unit_id": skill_id,
                "name": f"建立{point['name']}的可检查解题流程",
                "description": "把知识点转化为可执行、可复核的学习步骤。",
                "improvement_goal": point["capability"],
                "practice_strategy": "先说明适用条件，再执行关键步骤，最后用边界或反例检查结果。",
                "student_benefit": "减少只会复述概念、不会在新情境中应用的问题。",
                "primary_knowledge_id": point_id,
                "knowledge_ids": [point_id],
                "related_mistake_ids": [mistake_id],
                "source_status": "course_generated",
            })
    return {
        "skill_units": skills,
        "mistake_points": mistakes,
        "improvement_points": improvements,
    }


def validate_subject_library(library: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if library.get("schema_version") not in {SUBJECT_LIBRARY_SCHEMA, "knowledge_library_v3"}:
        issues.append("schema_version 不正确")
    nodes = list(library.get("nodes") or [])
    ids = [str(node.get("knowledge_id") or "") for node in nodes]
    if not nodes or not all(ids) or len(ids) != len(set(ids)):
        issues.append("知识节点必须存在且 ID 唯一")
        return issues
    by_id = {str(node["knowledge_id"]): node for node in nodes}
    roots = [node for node in nodes if not node.get("parent_id")]
    if len(roots) != 1 or roots[0].get("node_type") != "subject":
        issues.append("学科库必须恰有一个 subject 根节点")
    if library.get("root_node_id") not in by_id:
        issues.append("root_node_id 不存在")
    children: dict[str, list[str]] = {node_id: [] for node_id in by_id}
    for node in nodes:
        node_id = str(node["knowledge_id"])
        parent_id = str(node.get("parent_id") or "")
        if node.get("node_type") not in NODE_TYPES:
            issues.append(f"节点 {node_id} 类型无效")
        if parent_id:
            if parent_id not in by_id:
                issues.append(f"节点 {node_id} 父级不存在")
            else:
                children[parent_id].append(node_id)
        if not node.get("path_ids") or node.get("path_ids")[-1] != node_id:
            issues.append(f"节点 {node_id} 路径不完整")
    for node_id, child_ids in children.items():
        node = by_id[node_id]
        if not child_ids and node.get("node_type") != "knowledge_point":
            issues.append(f"非 knowledge_point 节点 {node_id} 不能成为叶子")
        if child_ids and node.get("node_type") == "knowledge_point":
            issues.append(f"knowledge_point 节点 {node_id} 不能拥有子节点")
    for node_id in by_id:
        seen: set[str] = set()
        current = node_id
        while current:
            if current in seen:
                issues.append(f"知识结构存在环：{node_id}")
                break
            seen.add(current)
            current = str((by_id.get(current) or {}).get("parent_id") or "")
    relation_ids: set[str] = set()
    for relation in library.get("relations") or []:
        relation_id = str(relation.get("relation_id") or "")
        if not relation_id or relation_id in relation_ids:
            issues.append("知识关系 ID 必须唯一")
        relation_ids.add(relation_id)
        if relation.get("source_knowledge_id") not in by_id or relation.get("target_knowledge_id") not in by_id:
            issues.append(f"知识关系 {relation_id} 端点不存在")

    skills = list(library.get("skill_units") or [])
    mistakes = list(library.get("mistake_points") or [])
    improvements = list(library.get("improvement_points") or [])
    skill_ids = [str(item.get("skill_unit_id") or "") for item in skills]
    mistake_ids = [str(item.get("mistake_point_id") or "") for item in mistakes]
    improvement_ids = [str(item.get("improvement_point_id") or "") for item in improvements]
    if not all(skill_ids) or len(skill_ids) != len(set(skill_ids)):
        issues.append("能力点 ID 必须非空且唯一")
    if not all(mistake_ids) or len(mistake_ids) != len(set(mistake_ids)):
        issues.append("易错点 ID 必须非空且唯一")
    if not all(improvement_ids) or len(improvement_ids) != len(set(improvement_ids)):
        issues.append("提升点 ID 必须非空且唯一")
    skill_id_set = set(skill_ids)
    mistake_id_set = set(mistake_ids)
    for skill in skills:
        parent_id = str(skill.get("primary_knowledge_id") or "")
        parent = by_id.get(parent_id)
        if not parent or parent.get("node_type") not in {"concept", "knowledge_point"}:
            issues.append(f"能力点 {skill.get('skill_unit_id')} 缺少合法知识父级")
        refs = [parent_id, *(skill.get("knowledge_ids") or [])]
        if any(ref not in by_id for ref in refs if ref):
            issues.append(f"能力点 {skill.get('skill_unit_id')} 引用了不存在的知识节点")
    for mistake in mistakes:
        if mistake.get("skill_unit_id") not in skill_id_set:
            issues.append(f"易错点 {mistake.get('mistake_point_id')} 缺少合法能力父级")
        if any(ref not in by_id for ref in mistake.get("knowledge_ids") or []):
            issues.append(f"易错点 {mistake.get('mistake_point_id')} 引用了不存在的知识节点")
    for improvement in improvements:
        if improvement.get("skill_unit_id") not in skill_id_set:
            issues.append(f"提升点 {improvement.get('improvement_point_id')} 缺少合法能力父级")
        if any(ref not in by_id for ref in improvement.get("knowledge_ids") or []):
            issues.append(f"提升点 {improvement.get('improvement_point_id')} 引用了不存在的知识节点")
        if any(ref not in mistake_id_set for ref in improvement.get("related_mistake_ids") or []):
            issues.append(f"提升点 {improvement.get('improvement_point_id')} 易错点引用无效")
    for relation in library.get("skill_relations") or []:
        if relation.get("source_id") not in skill_id_set or relation.get("target_id") not in skill_id_set:
            issues.append(f"能力关系 {relation.get('relation_id')} 端点不存在")
    return list(dict.fromkeys(issues))


def knowledge_index(library: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(node.get("knowledge_id") or ""): node
        for node in library.get("nodes") or []
        if node.get("knowledge_id")
    }


def match_subject_knowledge(library: dict[str, Any], value: Any) -> dict[str, Any] | None:
    """Return only exact canonical/alias matches as formal mappings."""
    query = _normalize_text(value)
    if not query:
        return None
    for node in library.get("nodes") or []:
        names = [node.get("knowledge_id"), node.get("code"), node.get("name"), *(node.get("aliases") or [])]
        for index, name in enumerate(names):
            if query == _normalize_text(name):
                covered = _descendant_points(library, str(node["knowledge_id"]))
                return {
                    "anchor_knowledge_id": str(node["knowledge_id"]),
                    "knowledge_ids": covered or [str(node["knowledge_id"])],
                    "match_status": "exact_name" if index in {0, 1, 2} else "exact_alias",
                    "confidence": 1.0 if index in {0, 1, 2} else 0.98,
                }
    return None


def suggest_subject_knowledge(
    library: dict[str, Any],
    value: Any,
    *,
    limit: int = 3,
) -> list[dict[str, Any]]:
    """Return non-binding suggestions for governance; never promotes a mapping."""
    query = _normalize_text(value)
    if len(query) < 2:
        return []
    scored: list[tuple[float, dict[str, Any]]] = []
    query_pairs = _bigrams(query)
    for node in library.get("nodes") or []:
        if node.get("node_type") not in {"concept", "knowledge_point"}:
            continue
        candidates = [node.get("name"), *(node.get("aliases") or [])]
        score = max((_similarity(query_pairs, _bigrams(_normalize_text(item))) for item in candidates), default=0.0)
        if score >= 0.32:
            scored.append((score, node))
    scored.sort(key=lambda item: (-item[0], len(str(item[1].get("name") or ""))))
    return [
        {
            "knowledge_id": node["knowledge_id"],
            "name": node["name"],
            "path_names": list(node.get("path_names") or []),
            "confidence": round(score, 3),
        }
        for score, node in scored[:limit]
    ]


def propose_content_linkage_from_kb_change(
    course_data: dict[str, Any],
    kg_node_id: str,
    updated_definition: dict[str, Any],
    *,
    repository: Any,
    request_id: str,
    library: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Retired compatibility entry point.

    A legacy cross-course subject node can never drive current-course content.
    Knowledge changes must originate from the current course maintenance
    surface and use current-course IDs.
    """
    del course_data, kg_node_id, updated_definition, repository, request_id, library
    return None


def knowledge_library_slice(
    library: dict[str, Any],
    knowledge_ids: list[str] | set[str],
) -> dict[str, Any]:
    """Return one hierarchy-preserving slice from the unified library."""
    selected = {str(item) for item in knowledge_ids if item}
    skills = [
        deepcopy(item) for item in library.get("skill_units") or []
        if _knowledge_intersects(item, selected)
    ]
    skill_ids = {str(item.get("skill_unit_id") or "") for item in skills}
    mistakes = [
        deepcopy(item) for item in library.get("mistake_points") or []
        if item.get("skill_unit_id") in skill_ids
    ]
    improvements = [
        deepcopy(item) for item in library.get("improvement_points") or []
        if item.get("skill_unit_id") in skill_ids
    ]
    payload = {
        "schema_version": KNOWLEDGE_SLICE_SCHEMA,
        "library_id": library.get("library_id"),
        "library_version": library.get("version"),
        "library_revision_id": library.get("revision_id"),
        "knowledge_ids": sorted(selected),
        "skill_units": skills,
        "mistake_points": mistakes,
        "improvement_points": improvements,
        "skill_relations": [
            deepcopy(item) for item in library.get("skill_relations") or []
            if item.get("source_id") in skill_ids and item.get("target_id") in skill_ids
        ],
        "usage_policy": deepcopy(library.get("usage_policy") or _usage_policy()),
        "status": "active" if skills else "empty",
    }
    payload["revision_id"] = stable_hash(payload, prefix="klsr_")
    return payload


def match_mistake_standard(
    library_slice: dict[str, Any],
    value: Any,
    knowledge_ids: list[str] | set[str] | None = None,
) -> dict[str, Any] | None:
    """Match only a formal mistake attached to a skill in the current slice."""
    query = _normalize_text(value)
    selected = {str(item) for item in knowledge_ids or [] if item}
    if not query:
        return None
    for item in library_slice.get("mistake_points") or []:
        refs = {str(value) for value in item.get("knowledge_ids") or [] if value}
        if item.get("primary_knowledge_id"):
            refs.add(str(item["primary_knowledge_id"]))
        if selected and refs and not refs.intersection(selected):
            continue
        candidates = [item.get("mistake_point_id"), item.get("name"), *(item.get("aliases") or [])]
        if any(
            normalized and (query == normalized or normalized in query or query in normalized)
            for candidate in candidates
            if (normalized := _normalize_text(candidate))
        ):
            return deepcopy(item)
        patterns = [item.get("error_pattern"), item.get("discrimination")]
        if any(query and query in _normalize_text(pattern) for pattern in patterns if pattern):
            return deepcopy(item)
    return None


def knowledge_library_slice_prompt_context(
    library_slice: dict[str, Any],
    *,
    limit: int = 24,
) -> str:
    if not library_slice.get("skill_units"):
        return "当前知识没有正式能力、易错或提升条目；请依据课程内容独立解释，不得伪造正式 ID。"
    mistakes_by_skill: dict[str, list[dict[str, Any]]] = {}
    improvements_by_skill: dict[str, list[dict[str, Any]]] = {}
    for item in library_slice.get("mistake_points") or []:
        mistakes_by_skill.setdefault(str(item.get("skill_unit_id") or ""), []).append(item)
    for item in library_slice.get("improvement_points") or []:
        improvements_by_skill.setdefault(str(item.get("skill_unit_id") or ""), []).append(item)
    rows: list[str] = []
    for skill in library_slice.get("skill_units") or []:
        skill_id = str(skill.get("skill_unit_id") or "")
        rows.append(f"- 能力：{skill.get('name')}；目标：{skill.get('learning_goal')}")
        for mistake in mistakes_by_skill.get(skill_id, [])[:3]:
            rows.append(f"  - 易错：{mistake.get('name')}；辨析：{mistake.get('repair_strategy')}")
        for improvement in improvements_by_skill.get(skill_id, [])[:2]:
            rows.append(f"  - 提升：{improvement.get('name')}；练习：{improvement.get('practice_strategy')}")
        if len(rows) >= limit:
            break
    return "\n".join([
        "以下条目属于同一知识库，只用于统一术语和颗粒度；必须先根据当前内容与证据独立判断：",
        *rows[:limit],
    ])


def knowledge_library_prompt_context(source: str | dict[str, Any], *, limit: int = 80) -> str:
    library = resolve_subject_library(source)
    if not library.get("nodes"):
        return "当前主题尚无正式学科知识包；模型只能提出课程局部知识要求，不得自造正式知识 ID。"
    rows = []
    for node in library.get("nodes") or []:
        if node.get("node_type") not in {"concept", "knowledge_point"}:
            continue
        aliases = "、".join(node.get("aliases") or [])
        row = " / ".join(node.get("path_names") or [])
        if aliases:
            row += f"（别名：{aliases}）"
        rows.append(row)
        if len(rows) >= limit:
            break
    standards = knowledge_library_slice(
        library,
        {str(node.get("knowledge_id")) for node in library.get("nodes") or []},
    )
    standard_rows = knowledge_library_slice_prompt_context(standards, limit=18)
    return "\n".join([
        f"正式学科包：{library.get('title')}，版本 {library.get('version')}。",
        "知识、能力、易错和提升来自同一版本库。以下名称用于统一术语，不是课程目录；模型不得编造列表外的正式 ID：",
        *[f"- {row}" for row in rows],
        standard_rows,
    ])


def build_knowledge_library_view(
    library: dict[str, Any],
    course_map: dict[str, Any],
    assets: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """Project a course-scoped read view without copying course hierarchy into the library."""
    by_id = knowledge_index(library)
    selected: set[str] = set(by_id)
    bindings: dict[str, dict[str, set[str]]] = {}

    def binding(node_id: str) -> dict[str, set[str]]:
        return bindings.setdefault(node_id, {
            "section_ids": set(),
            "block_ids": set(),
            "objective_ids": set(),
            "question_ids": set(),
            "criterion_ids": set(),
            "misconception_ids": set(),
            "skill_unit_ids": set(),
            "mistake_point_ids": set(),
            "improvement_ids": set(),
        })

    for mapping in course_map.get("mappings") or []:
        mapped_ids = [
            str(item) for item in [mapping.get("anchor_knowledge_id"), *(mapping.get("knowledge_ids") or [])]
            if item in by_id
        ]
        for node_id in mapped_ids:
            selected.add(node_id)
            entry = binding(node_id)
            entry["section_ids"].add(str(mapping.get("section_id") or ""))
            entry["block_ids"].update(str(item) for item in mapping.get("block_ids") or [] if item)
            entry["objective_ids"].update(str(item) for item in mapping.get("objective_ids") or [] if item)

    directly_bound = [node_id for node_id, entry in bindings.items() if entry["section_ids"]]
    for node_id in directly_bound:
        current = by_id.get(node_id)
        source_binding = binding(node_id)
        while current:
            current_id = str(current["knowledge_id"])
            ancestor_binding = binding(current_id)
            ancestor_binding["section_ids"].update(source_binding["section_ids"])
            ancestor_binding["block_ids"].update(source_binding["block_ids"])
            ancestor_binding["objective_ids"].update(source_binding["objective_ids"])
            parent_id = str(current.get("parent_id") or "")
            current = by_id.get(parent_id) if parent_id else None

    for asset_type, id_key, binding_key in (
        ("questions", "question_id", "question_ids"),
        ("mastery_criteria", "criterion_id", "criterion_ids"),
        ("misconceptions", "misconception_id", "misconception_ids"),
    ):
        for asset in assets.get(asset_type) or []:
            asset_id = str(asset.get(id_key) or asset.get("asset_id") or "")
            for node_id in asset.get("concept_ids") or []:
                if node_id in by_id and asset_id:
                    binding(str(node_id))[binding_key].add(asset_id)

    skill_by_id = {
        str(item.get("skill_unit_id") or ""): item
        for item in library.get("skill_units") or []
        if item.get("skill_unit_id")
    }
    for item_type, id_key, binding_key in (
        ("skill_units", "skill_unit_id", "skill_unit_ids"),
        ("mistake_points", "mistake_point_id", "mistake_point_ids"),
        ("improvement_points", "improvement_point_id", "improvement_ids"),
    ):
        for item in library.get(item_type) or []:
            item_id = str(item.get(id_key) or "")
            parent_skill = skill_by_id.get(str(item.get("skill_unit_id") or ""), {})
            node_ids = [item.get("primary_knowledge_id"), *(item.get("knowledge_ids") or [])]
            if item_type != "skill_units":
                node_ids.extend([
                    parent_skill.get("primary_knowledge_id"),
                    *(parent_skill.get("knowledge_ids") or []),
                ])
            for node_id in node_ids:
                if node_id in by_id and item_id:
                    binding(str(node_id))[binding_key].add(item_id)

    direct_binding_snapshots = [
        (node_id, {key: set(values) for key, values in entry.items()})
        for node_id, entry in bindings.items()
    ]
    for node_id, source_binding in direct_binding_snapshots:
        parent_id = str((by_id.get(node_id) or {}).get("parent_id") or "")
        while parent_id and parent_id in by_id:
            ancestor_binding = binding(parent_id)
            for key, values in source_binding.items():
                ancestor_binding[key].update(values)
            parent_id = str((by_id.get(parent_id) or {}).get("parent_id") or "")

    view_nodes: list[dict[str, Any]] = []
    for node in library.get("nodes") or []:
        node_id = str(node["knowledge_id"])
        if node_id not in selected:
            continue
        projected = deepcopy(node)
        entry = binding(node_id)
        for key, values in entry.items():
            projected[key] = sorted(value for value in values if value)
        projected["covered_by_course"] = bool(projected["section_ids"])
        view_nodes.append(projected)

    selected_ids = {str(node["knowledge_id"]) for node in view_nodes}
    relations = [
        deepcopy(relation)
        for relation in library.get("relations") or []
        if relation.get("source_knowledge_id") in selected_ids
        and relation.get("target_knowledge_id") in selected_ids
    ]
    source_summary: dict[str, int] = {}
    for collection in (
        view_nodes,
        relations,
        library.get("skill_units") or [],
        library.get("mistake_points") or [],
        library.get("improvement_points") or [],
    ):
        for item in collection:
            source_type = str(item.get("source_type") or item.get("source_status") or "unknown")
            source_summary[source_type] = source_summary.get(source_type, 0) + 1
    payload = {
        "schema_version": SUBJECT_VIEW_SCHEMA,
        "library_id": library.get("library_id"),
        "subject_id": library.get("subject_id"),
        "identity_scope": "subject_shared",
        "library_version": library.get("version"),
        "binding_revision_id": course_map.get("binding_revision_id") or library.get("revision_id"),
        "lifecycle_status": library.get("lifecycle_status", "accepted" if library.get("status") == "active" else "degraded"),
        "origin": library.get("origin", "curated" if library.get("status") == "active" else "course_index"),
        "quality_report": deepcopy(library.get("quality_report") or {}),
        "generation_audit": deepcopy(library.get("generation_audit") or {}),
        "source_summary": source_summary,
        "root_node_id": library.get("root_node_id"),
        "nodes": view_nodes,
        "relations": relations,
        "skill_units": deepcopy(library.get("skill_units") or []),
        "mistake_points": deepcopy(library.get("mistake_points") or []),
        "improvement_points": deepcopy(library.get("improvement_points") or []),
        "skill_relations": deepcopy(library.get("skill_relations") or []),
        "usage_policy": deepcopy(library.get("usage_policy") or _usage_policy()),
        "course_map_revision_id": course_map.get("revision_id"),
        "coverage": deepcopy(course_map.get("coverage") or {}),
        "unresolved_mappings": deepcopy(course_map.get("unresolved_candidates") or []),
        "status": (
            "active"
            if view_nodes and library.get("lifecycle_status", "accepted" if library.get("status") == "active" else "degraded") in {"accepted", "candidate"}
            else "degraded" if view_nodes else "unavailable"
        ),
    }
    payload["asset_id"] = stable_hash({
        "library": library.get("library_id"),
        "course_map": course_map.get("revision_id"),
    }, prefix="skv_")
    payload["revision_id"] = stable_hash(payload, prefix="skvr_")
    return payload


def _normalize_library(raw: dict[str, Any]) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []

    def walk(source: dict[str, Any], parent: dict[str, Any] | None, order: int) -> None:
        node_id = str(source.get("knowledge_id") or "").strip()
        node_type = str(source.get("node_type") or "").strip()
        name = str(source.get("name") or "").strip()
        path_ids = [*((parent or {}).get("path_ids") or []), node_id]
        path_names = [*((parent or {}).get("path_names") or []), name]
        node = {
            "knowledge_id": node_id,
            "code": str(source.get("code") or node_id),
            "parent_id": (parent or {}).get("knowledge_id"),
            "node_type": node_type,
            "name": name,
            "description": str(source.get("description") or ""),
            "depth": len(path_ids) - 1,
            "sort_order": int(source.get("sort_order") if source.get("sort_order") is not None else order),
            "path_ids": path_ids,
            "path_names": path_names,
            "aliases": list(dict.fromkeys(str(item).strip() for item in source.get("aliases") or [] if str(item).strip())),
            "alias_sources": deepcopy(source.get("alias_sources") or []),
            "learning_actions": [str(item).strip() for item in source.get("learning_actions") or [] if str(item).strip()],
            "typical_problems": [str(item).strip() for item in source.get("typical_problems") or [] if str(item).strip()],
            "source_refs": [str(item).strip() for item in source.get("source_refs") or raw.get("source_refs") or [] if str(item).strip()],
            "source_status": str(source.get("source_status") or "curated"),
            "source_type": str(source.get("source_type") or source.get("source_status") or "curated"),
            "confidence": float(source.get("confidence") if source.get("confidence") is not None else 1.0),
            "status": str(source.get("status") or "active"),
            "library_version": str(raw.get("version") or ""),
        }
        node["revision_id"] = stable_hash(node, prefix="knr_")
        nodes.append(node)
        for child_order, child in enumerate(source.get("children") or []):
            walk(child, node, child_order)

    walk(raw.get("tree") or {}, None, 0)
    relations = []
    for relation in raw.get("relations") or []:
        normalized = {
            "relation_id": str(relation.get("relation_id") or stable_hash(relation, prefix="kr_")),
            "source_knowledge_id": str(relation.get("source_knowledge_id") or ""),
            "target_knowledge_id": str(relation.get("target_knowledge_id") or ""),
            "relation_type": str(relation.get("relation_type") or "related"),
            "reason": str(relation.get("reason") or ""),
            "source_status": str(relation.get("source_status") or "curated"),
            "source_type": str(relation.get("source_type") or relation.get("source_status") or "curated"),
            "confidence": float(relation.get("confidence") if relation.get("confidence") is not None else 1.0),
            "status": str(relation.get("status") or "accepted"),
        }
        normalized["revision_id"] = stable_hash(normalized, prefix="krr_")
        relations.append(normalized)
    teaching_items: dict[str, list[dict[str, Any]]] = {
        "skill_units": [],
        "mistake_points": [],
        "improvement_points": [],
    }
    for collection, id_key, prefix in (
        ("skill_units", "skill_unit_id", "sur_"),
        ("mistake_points", "mistake_point_id", "mpr_"),
        ("improvement_points", "improvement_point_id", "ipr_"),
    ):
        for source in raw.get(collection) or []:
            item = deepcopy(source)
            item[id_key] = str(item.get(id_key) or "")
            item["primary_knowledge_id"] = str(item.get("primary_knowledge_id") or "")
            item["knowledge_ids"] = list(dict.fromkeys(
                str(value) for value in item.get("knowledge_ids") or [] if value
            ))
            item["aliases"] = list(dict.fromkeys(
                str(value).strip() for value in item.get("aliases") or [] if str(value).strip()
            ))
            item["library_version"] = str(raw.get("version") or "")
            item["status"] = str(item.get("status") or "active")
            item["revision_id"] = stable_hash(item, prefix=prefix)
            teaching_items[collection].append(item)
    skill_relations = []
    for source in raw.get("skill_relations") or []:
        relation = deepcopy(source)
        relation["relation_id"] = str(relation.get("relation_id") or stable_hash(relation, prefix="ksr_"))
        relation["revision_id"] = stable_hash(relation, prefix="ksrr_")
        skill_relations.append(relation)
    library = {
        "schema_version": SUBJECT_LIBRARY_SCHEMA,
        "library_id": str(raw.get("library_id") or ""),
        "subject_id": str(raw.get("subject_id") or ""),
        "version": str(raw.get("version") or ""),
        "title": str(raw.get("title") or ""),
        "root_node_id": str((raw.get("tree") or {}).get("knowledge_id") or ""),
        "match_terms": [str(item) for item in raw.get("match_terms") or []],
        "nodes": nodes,
        "relations": relations,
        **teaching_items,
        "skill_relations": skill_relations,
        "usage_policy": _usage_policy(),
        "status": "active",
    }
    library["revision_id"] = stable_hash(library, prefix="skl_")
    return library


def _descendant_points(library: dict[str, Any], node_id: str) -> list[str]:
    by_parent: dict[str, list[dict[str, Any]]] = {}
    by_id = knowledge_index(library)
    for node in library.get("nodes") or []:
        by_parent.setdefault(str(node.get("parent_id") or ""), []).append(node)
    start = by_id.get(node_id)
    if not start:
        return []
    if start.get("node_type") == "knowledge_point":
        return [node_id]
    result: list[str] = []
    queue = list(by_parent.get(node_id) or [])
    while queue:
        current = queue.pop(0)
        if current.get("node_type") == "knowledge_point":
            result.append(str(current["knowledge_id"]))
        else:
            queue.extend(by_parent.get(str(current["knowledge_id"])) or [])
    return result


def _subject_hint(source: str | dict[str, Any]) -> str:
    if isinstance(source, str):
        return source
    request = source.get("generation_request") or {}
    blueprint = source.get("course_blueprint") or {}
    brief = source.get("course_generation_brief") or {}
    return " ".join(str(item or "") for item in (
        source.get("subject"),
        request.get("subject"),
        request.get("topic"),
        brief.get("subject"),
        source.get("course_name"),
        blueprint.get("course_title"),
    ))


def _normalize_text(value: Any) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", str(value or "").lower())


def _knowledge_intersects(item: dict[str, Any], selected: set[str]) -> bool:
    refs = {
        str(item.get("primary_knowledge_id") or ""),
        *[str(value) for value in item.get("knowledge_ids") or []],
    }
    refs.discard("")
    return bool(refs.intersection(selected))


def _usage_policy() -> dict[str, Any]:
    return {
        "ai_must_judge_independently": True,
        "allowed_fit": ["hit", "partial", "miss"],
        "may_invent_formal_ids": False,
        "personal_state_can_modify_library": False,
    }


def _bigrams(value: str) -> set[str]:
    if len(value) < 2:
        return {value} if value else set()
    return {value[index:index + 2] for index in range(len(value) - 1)}


def _similarity(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


__all__ = [
    "KNOWLEDGE_SLICE_SCHEMA",
    "SUBJECT_LIBRARY_SCHEMA",
    "SUBJECT_VIEW_SCHEMA",
    "available_subject_libraries",
    "build_knowledge_library_view",
    "knowledge_index",
    "knowledge_library_slice",
    "knowledge_library_slice_prompt_context",
    "load_subject_library",
    "match_subject_knowledge",
    "match_mistake_standard",
    "resolve_subject_library",
    "knowledge_library_prompt_context",
    "propose_content_linkage_from_kb_change",
    "suggest_subject_knowledge",
    "validate_subject_library",
]
