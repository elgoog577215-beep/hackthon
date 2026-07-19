"""Subject-level ontology construction and semantic quality gates."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
import re
from typing import Any

from course_versioning import stable_hash
from subject_knowledge import _normalize_library, validate_subject_library


SUBJECT_LIBRARY_V3 = "knowledge_library_v3"
DATA_STRUCTURES_SUBJECT_ID = "computer_science.data_structures"


_SUBJECT_REGISTRY: tuple[dict[str, Any], ...] = (
    {"subject_id": "math.calculus", "library_id": "math.calculus", "canonical_name": "微积分", "root_name": "数学", "aliases": ("微积分", "calculus")},
    {"subject_id": "math.advanced_algebra", "library_id": "math.advanced_algebra", "canonical_name": "高等代数", "root_name": "数学", "aliases": ("高等代数", "advancedalgebra")},
    {"subject_id": "physics.quantum_mechanics", "library_id": "physics.quantum_mechanics", "canonical_name": "量子力学", "root_name": "物理学", "aliases": ("量子力学", "量子物理", "quantummechanics", "quantumphysics")},
    {"subject_id": "physics.electromagnetism", "library_id": "physics.electromagnetism", "canonical_name": "电磁学", "root_name": "物理学", "aliases": ("电磁学", "电动力学", "electromagnetism")},
    {"subject_id": "physics.thermodynamics_statistical_physics", "library_id": "physics.thermodynamics_statistical_physics", "canonical_name": "热力学与统计物理", "root_name": "物理学", "aliases": ("热力学", "统计物理", "thermodynamics", "statisticalphysics")},
    {"subject_id": "physics.classical_mechanics", "library_id": "physics.classical_mechanics", "canonical_name": "经典力学", "root_name": "物理学", "aliases": ("经典力学", "classicalmechanics")},
    {"subject_id": "computer_science.machine_learning", "library_id": "computer_science.machine_learning", "canonical_name": "机器学习", "root_name": "计算机科学", "aliases": ("机器学习", "machinelearning")},
    {"subject_id": "computer_science.python", "library_id": "computer_science.python", "canonical_name": "Python 程序设计", "root_name": "计算机科学", "aliases": ("python",)},
    {"subject_id": "computer_science.java", "library_id": "computer_science.java", "canonical_name": "Java 程序设计", "root_name": "计算机科学", "aliases": ("java",)},
    {"subject_id": "engineering.control", "library_id": "engineering.control", "canonical_name": "控制科学与工程", "root_name": "工程学", "aliases": ("控制学", "控制理论", "控制系统", "controltheory", "controlsystem")},
    {"subject_id": "humanities.philosophy", "library_id": "humanities.philosophy", "canonical_name": "哲学", "root_name": "人文学科", "aliases": ("哲学", "philosophy")},
    {"subject_id": "social_science.debate", "library_id": "social_science.debate", "canonical_name": "辩论与论证", "root_name": "社会科学", "aliases": ("辩论", "论证", "debate")},
    {"subject_id": "social_science.etiquette", "library_id": "social_science.etiquette", "canonical_name": "礼仪学", "root_name": "社会科学", "aliases": ("礼仪", "etiquette")},
)


def resolve_subject_identity(course: dict[str, Any]) -> dict[str, str]:
    request = course.get("generation_request") or {}
    hint = " ".join(str(item or "") for item in (
        request.get("subject"),
        course.get("subject"),
        course.get("course_name"),
        (course.get("course_blueprint") or {}).get("course_title"),
    ))
    normalized = _normalize(hint)
    if any(term in normalized for term in ("数据结构", "datastructure", "avl", "哈希表", "图算法")):
        return {
            "subject_id": DATA_STRUCTURES_SUBJECT_ID,
            "library_id": "cs.data_structures",
            "canonical_name": "数据结构与算法",
            "root_name": "计算机科学",
        }
    if any(term in normalized for term in ("线性代数", "linearalgebra")):
        return {
            "subject_id": "math.linear_algebra",
            "library_id": "math.linear_algebra.v1",
            "canonical_name": "线性代数",
            "root_name": "数学",
        }
    lowered_hint = hint.casefold()
    if "c++" in lowered_hint or "cplusplus" in normalized or "cpp" in normalized:
        return {
            "subject_id": "computer_science.cpp",
            "library_id": "computer_science.cpp",
            "canonical_name": "C++ 程序设计",
            "root_name": "计算机科学",
        }
    for registration in _SUBJECT_REGISTRY:
        if any(_normalize(alias) in normalized for alias in registration["aliases"]):
            return {
                key: str(registration[key])
                for key in ("subject_id", "library_id", "canonical_name", "root_name")
            }
    subject_name = str(request.get("subject") or course.get("subject") or course.get("course_name") or "通用学科").strip()
    slug = stable_hash({"subject": _normalize(subject_name)})
    return {
        "subject_id": f"generated_subject.{slug}",
        "library_id": f"generated_library.{slug}",
        "canonical_name": subject_name,
        "root_name": subject_name,
    }


def build_subject_ontology(
    course: dict[str, Any],
    *,
    supersedes_revision_id: str | None = None,
    model_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one deterministic candidate; a validated model payload may enrich it later."""
    identity = resolve_subject_identity(course)
    if identity["subject_id"] == DATA_STRUCTURES_SUBJECT_ID:
        raw = _build_data_structures_raw(course, identity)
    else:
        raw = _build_generic_raw(course, identity)
    if model_payload:
        raw = _merge_model_payload(raw, model_payload)
    library = _normalize_library(raw)
    library.update({
        "schema_version": SUBJECT_LIBRARY_V3,
        "lifecycle_status": "candidate",
        "origin": "model_generated" if model_payload else "course_and_domain_generated",
        "source_course_ids": [
            str(course_id)
            for course_id in (
                course.get("source_course_ids")
                or [course.get("course_id")]
            )
            if course_id
        ],
        "supersedes_revision_id": supersedes_revision_id,
        "identity_migrations": [],
        "generation_audit": {
            "generation_calls": 1 if model_payload else 0,
            "review_calls": 0,
            "repair_calls": 0,
            "sources": ["course_source", "material_source", "model_inferred"],
        },
    })
    library["revision_id"] = stable_hash(
        {key: value for key, value in library.items() if key not in {"revision_id", "created_at"}},
        prefix="sklr_",
    )
    return library


def build_subject_ontology_from_proposal(
    course: dict[str, Any],
    proposal: dict[str, Any],
    *,
    supersedes_revision_id: str | None = None,
) -> dict[str, Any]:
    """Compile a model-authored ontology proposal into backend-owned identities."""
    if not isinstance(proposal, dict) or not isinstance(proposal.get("domains"), list):
        raise ValueError("Ontology proposal must contain domains")
    identity = resolve_subject_identity(course)
    course_point_names = {
        _normalize(item["name"])
        for item in _course_points(course)
        if item.get("name")
    }
    root = {
        "knowledge_id": f"subject.{stable_hash(identity['root_name'])}",
        "node_type": "subject",
        "name": identity["root_name"],
        "description": f"{identity['canonical_name']}所属学科。",
        **_source("model_inferred", 0.9),
        "children": [],
    }
    for domain_order, domain_value in enumerate(proposal.get("domains") or []):
        if not isinstance(domain_value, dict):
            continue
        domain_name = str(domain_value.get("name") or "").strip()
        if not domain_name:
            continue
        domain = {
            "knowledge_id": f"{identity['subject_id']}.domain.{stable_hash(_normalize(domain_name))}",
            "node_type": "domain",
            "name": domain_name,
            "description": str(domain_value.get("description") or f"{domain_name}的主要知识领域"),
            "sort_order": domain_order,
            **_proposal_source(domain_value, default="model_inferred", confidence=0.85),
            "children": [],
        }
        for topic_order, topic_value in enumerate(domain_value.get("topics") or []):
            if not isinstance(topic_value, dict):
                continue
            topic_name = str(topic_value.get("name") or "").strip()
            if not topic_name:
                continue
            topic = {
                "knowledge_id": f"{identity['subject_id']}.topic.{stable_hash([_normalize(domain_name), _normalize(topic_name)])}",
                "node_type": "topic",
                "name": topic_name,
                "description": str(topic_value.get("description") or f"{topic_name}的概念体系"),
                "sort_order": topic_order,
                **_proposal_source(topic_value, default="model_inferred", confidence=0.85),
                "children": [],
            }
            for concept_order, concept_value in enumerate(topic_value.get("concepts") or []):
                if not isinstance(concept_value, dict):
                    continue
                concept_name = str(concept_value.get("name") or "").strip()
                if not concept_name:
                    continue
                concept = {
                    "knowledge_id": f"{identity['subject_id']}.concept.{stable_hash([_normalize(domain_name), _normalize(topic_name), _normalize(concept_name)])}",
                    "node_type": "concept",
                    "name": concept_name,
                    "aliases": _strings(concept_value.get("aliases")),
                    "description": str(concept_value.get("description") or f"{concept_name}的定义、机制和应用边界"),
                    "sort_order": concept_order,
                    **_proposal_source(concept_value, default="model_inferred", confidence=0.85),
                    "children": [],
                }
                for point_order, point_value in enumerate(concept_value.get("knowledge_points") or []):
                    normalized_point = _proposal_point(point_value)
                    if not normalized_point:
                        continue
                    point_name = normalized_point["name"]
                    source_type = normalized_point.get("source_type") or (
                        "course_source" if _normalize(point_name) in course_point_names else "model_inferred"
                    )
                    concept["children"].append({
                        "knowledge_id": f"{identity['subject_id']}.point.{stable_hash(_normalize(point_name))}",
                        "node_type": "knowledge_point",
                        "name": point_name,
                        "aliases": normalized_point["aliases"],
                        "description": normalized_point["description"],
                        "learning_actions": [normalized_point["learning_action"]],
                        "typical_problems": normalized_point["typical_problems"],
                        "sort_order": point_order,
                        **_source(source_type, float(normalized_point.get("confidence") or (1.0 if source_type == "course_source" else 0.8))),
                    })
                if concept["children"]:
                    topic["children"].append(concept)
            if topic["children"]:
                domain["children"].append(topic)
        if domain["children"]:
            root["children"].append(domain)
    if not root["children"]:
        raise ValueError("Ontology proposal contains no usable domains")

    _attach_explicit_course_aliases(root, proposal)
    _attach_course_structure_aliases(root, course)

    raw = {
        "schema_version": SUBJECT_LIBRARY_V3,
        "library_id": identity["library_id"],
        "subject_id": identity["subject_id"],
        "version": "3.0.0-candidate",
        "title": f"{identity['canonical_name']}候选知识库",
        "match_terms": [identity["canonical_name"], str(course.get("course_name") or "")],
        "source_refs": _source_refs(course),
        "tree": root,
        "relations": [],
        "skill_units": [],
        "mistake_points": [],
        "improvement_points": [],
        "skill_relations": [],
    }
    library = _normalize_library(raw)
    name_index = _unique_name_index(library.get("nodes") or [])
    library["relations"] = _compile_proposal_relations(identity["subject_id"], proposal, name_index)
    skills, skill_name_index = _compile_proposal_skills(identity["subject_id"], proposal, name_index)
    mistakes, mistake_name_index = _compile_proposal_mistakes(
        identity["subject_id"], proposal, name_index, skill_name_index,
    )
    improvements = _compile_proposal_improvements(
        identity["subject_id"], proposal, name_index, skill_name_index, mistake_name_index,
    )
    _sanitize_material_sources(
        course,
        library,
        library["relations"],
        skills,
        mistakes,
        improvements,
    )
    library.update({
        "schema_version": SUBJECT_LIBRARY_V3,
        "lifecycle_status": "candidate",
        "origin": "model_generated",
        "source_course_ids": [
            str(course_id)
            for course_id in (course.get("source_course_ids") or [course.get("course_id")])
            if course_id
        ],
        "supersedes_revision_id": supersedes_revision_id,
        "identity_migrations": [],
        "relations": library["relations"],
        "skill_units": skills,
        "mistake_points": mistakes,
        "improvement_points": improvements,
        "skill_relations": [],
        "generation_audit": {
            "generation_calls": 1,
            "review_calls": 0,
            "repair_calls": 0,
            "sources": _actual_source_types(course, library),
        },
    })
    library["revision_id"] = stable_hash(
        {key: value for key, value in library.items() if key not in {"revision_id", "created_at"}},
        prefix="sklr_",
    )
    return library


def apply_model_enrichment(
    library: dict[str, Any],
    payload: dict[str, Any] | None,
) -> dict[str, Any]:
    """Apply only name/ID selections from the existing backend-owned identity space."""
    if not isinstance(payload, dict):
        return deepcopy(library)
    value = deepcopy(library)
    known_ids = {str(item.get("knowledge_id")) for item in value.get("nodes") or []}
    relations = list(value.get("relations") or [])
    existing = {
        (str(item.get("source_knowledge_id")), str(item.get("target_knowledge_id")), str(item.get("relation_type")))
        for item in relations
    }
    for suggestion in payload.get("relations") or []:
        if not isinstance(suggestion, dict):
            continue
        source_id = str(suggestion.get("source_knowledge_id") or "")
        target_id = str(suggestion.get("target_knowledge_id") or "")
        relation_type = str(suggestion.get("relation_type") or "related")
        key = (source_id, target_id, relation_type)
        if source_id not in known_ids or target_id not in known_ids or source_id == target_id or key in existing:
            continue
        if relation_type not in {"prerequisite", "application", "related", "confusable", "derives"}:
            continue
        relations.append(_relation(
            str(value.get("subject_id") or "subject"),
            source_id,
            target_id,
            relation_type,
            str(suggestion.get("reason") or "模型建议的学科关系"),
        ))
        existing.add(key)
    value["relations"] = relations
    value["origin"] = "model_generated"
    return value


def evaluate_subject_ontology_quality(
    library: dict[str, Any],
    course: dict[str, Any],
    course_map: dict[str, Any],
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []

    compatible = deepcopy(library)
    compatible["schema_version"] = "knowledge_library_v2"
    for message in validate_subject_library(compatible):
        issues.append(_issue("invalid_structure", "critical", message))

    node_types = {str(item.get("node_type") or "") for item in library.get("nodes") or []}
    if "topic" not in node_types or not {"subject", "domain", "concept", "knowledge_point"}.issubset(node_types):
        issues.append(_issue("incomplete_subject_hierarchy", "critical", "知识库缺少学科五级逻辑中的必要层级"))

    mapped_ratio = float((course_map.get("coverage") or {}).get("mapped_ratio") or 0.0)
    if mapped_ratio < 0.85:
        issues.append(_issue("insufficient_course_mapping", "critical", f"课程知识映射率仅为 {mapped_ratio:.0%}"))

    concepts = {
        str(item.get("knowledge_id")): item
        for item in library.get("nodes") or []
        if item.get("node_type") == "concept"
    }
    relations = list(library.get("relations") or [])
    if len(concepts) >= 4 and not relations:
        issues.append(_issue("missing_cross_concept_relations", "critical", "概念达到4个但没有知识关系"))

    by_id = {str(item.get("knowledge_id")): item for item in library.get("nodes") or []}
    mapped_concepts: set[str] = set()
    section_concepts: dict[str, set[str]] = {}
    for mapping in course_map.get("mappings") or []:
        anchor = str(mapping.get("anchor_knowledge_id") or "")
        concept_id = _ancestor_of_type(anchor, "concept", by_id)
        if concept_id:
            mapped_concepts.add(concept_id)
            section_concepts.setdefault(str(mapping.get("section_id") or ""), set()).add(concept_id)
    participating = {
        concept_id
        for relation in relations
        for concept_id in (
            _ancestor_of_type(str(relation.get("source_knowledge_id") or ""), "concept", by_id),
            _ancestor_of_type(str(relation.get("target_knowledge_id") or ""), "concept", by_id),
        )
        if concept_id in mapped_concepts
    }
    relation_coverage = len(participating) / len(mapped_concepts) if mapped_concepts else 0.0
    if mapped_concepts and relation_coverage < 0.5:
        issues.append(_issue("insufficient_relation_coverage", "critical", f"仅 {relation_coverage:.0%} 的课程概念参与知识关系"))

    section_ids = {
        str(item.get("node_id") or "")
        for item in course.get("nodes") or []
        if int(item.get("node_level") or 1) == 2
    }
    one_concept_each = (
        section_ids
        and section_ids == set(section_concepts)
        and all(len(values) == 1 for values in section_concepts.values())
        and len({next(iter(values)) for values in section_concepts.values()}) == len(section_ids)
    )
    mirrored_concepts = 0
    for concept in concepts.values():
        parent = by_id.get(str(concept.get("parent_id") or "")) or {}
        concept_name = _strip_outline_number(concept.get("name"))
        parent_name = _strip_outline_number(parent.get("name"))
        if concept_name and concept_name == parent_name:
            mirrored_concepts += 1
    mirror_ratio = mirrored_concepts / len(concepts) if concepts else 0.0
    cross_section_relation = any(
        _relation_crosses_sections(relation, section_concepts, by_id)
        for relation in relations
    )
    if mirror_ratio >= 0.7 or (one_concept_each and not cross_section_relation):
        issues.append(_issue("course_outline_mirror", "critical", "知识概念与课程小节一一对应且没有跨小节关系"))

    if _has_prerequisite_cycle(relations):
        issues.append(_issue("prerequisite_cycle", "critical", "前置知识关系存在循环依赖"))

    invalid_relation_count = sum(
        not str(relation.get("reason") or "").strip()
        or relation.get("source_type") not in {"course_source", "material_source", "model_inferred", "curated"}
        or relation.get("status") not in {"candidate", "accepted"}
        or not isinstance(relation.get("confidence"), (int, float))
        or not 0 <= float(relation.get("confidence") or 0) <= 1
        for relation in relations
    )
    if invalid_relation_count:
        issues.append(_issue(
            "invalid_relation_metadata",
            "critical",
            f"{invalid_relation_count} 条知识关系缺少原因、来源、置信度或候选状态",
        ))

    for collection, fields, code in (
        (library.get("mistake_points") or [], ("description", "misconception", "repair_strategy"), "repeated_mistake_templates"),
        (library.get("improvement_points") or [], ("description", "practice_strategy", "student_benefit"), "repeated_improvement_templates"),
    ):
        if len(collection) < 5:
            continue
        fingerprints = [
            _semantic_template_fingerprint(item, fields, by_id)
            for item in collection
        ]
        highest = max(Counter(fingerprints).values(), default=0) / len(fingerprints)
        if highest > 0.3:
            issues.append(_issue(code, "critical", f"同一语义模板占比 {highest:.0%}，超过30%"))

    skills = list(library.get("skill_units") or [])
    cross_skill_ratio = (
        sum(len(item.get("knowledge_ids") or []) > 1 for item in skills) / len(skills)
        if skills else 0.0
    )
    if len(skills) >= 4 and cross_skill_ratio < 0.3:
        issues.append(_issue("skills_not_aggregated", "critical", "跨知识点能力不足30%"))

    blocking = [item for item in issues if item["severity"] == "critical"]
    return {
        "schema_version": "subject_ontology_quality_v1",
        "passed": not blocking,
        "score": max(0, 100 - 15 * len(blocking) - 5 * (len(issues) - len(blocking))),
        "metrics": {
            "node_count": len(library.get("nodes") or []),
            "concept_count": len(concepts),
            "relation_count": len(relations),
            "mapped_ratio": mapped_ratio,
            "relation_coverage": round(relation_coverage, 4),
            "cross_skill_ratio": round(cross_skill_ratio, 4),
            "course_outline_mirror_ratio": round(mirror_ratio, 4),
        },
        "issues": issues,
        "blocking_issues": blocking,
    }


def _build_data_structures_raw(course: dict[str, Any], identity: dict[str, str]) -> dict[str, Any]:
    subject_id = identity["subject_id"]
    point_groups: dict[str, list[dict[str, Any]]] = {
        "sequential": [
            _point(subject_id, "数组随机访问", "通过连续存储和下标计算实现常数时间访问"),
            _point(subject_id, "动态数组摊销分析", "通过容量倍增分析追加操作的摊销复杂度"),
            _point(subject_id, "链表实现", "使用节点引用维护链式存储和边界"),
        ],
        "heap": [
            _point(subject_id, "堆序性质", "父子节点满足一致的偏序约束"),
            _point(subject_id, "完全二叉树表示", "用数组紧凑表示完全二叉树"),
            _point(subject_id, "上浮操作", "插入后沿祖先路径恢复堆序"),
            _point(subject_id, "下沉操作", "删除堆顶后沿子树路径恢复堆序"),
        ],
        "avl": [
            _point(subject_id, "平衡因子", "用左右子树高度差描述局部平衡"),
            _point(subject_id, "AVL旋转", "通过单旋或双旋恢复搜索树平衡"),
            _point(subject_id, "AVL高度更新", "旋转和插入后按依赖顺序更新节点高度"),
        ],
        "hash": [
            _point(subject_id, "哈希冲突", "不同键映射到相同槽位时选择冲突策略"),
            _point(subject_id, "开放寻址删除标记", "使用墓碑标记保持探测链连续"),
            _point(subject_id, "负载因子", "用占用比例控制扩容和性能退化"),
        ],
        "graph_representation": [
            _point(subject_id, "邻接矩阵", "用二维矩阵表示顶点之间的边"),
            _point(subject_id, "邻接表", "按顶点保存相邻边以适配稀疏图"),
        ],
        "graph_traversal": [
            _point(subject_id, "广度优先搜索", "使用队列按距离层次访问图"),
            _point(subject_id, "深度优先搜索", "使用递归或栈沿路径深入访问图"),
            _point(subject_id, "图遍历访问标记", "在发现顶点时及时标记避免重复访问"),
        ],
    }
    known_point_names = {
        _normalize(item["name"])
        for items in point_groups.values()
        for item in items
    }
    for point in _course_points(course):
        group = _data_structure_group(point["name"])
        normalized_name = _normalize(point["name"])
        if normalized_name not in known_point_names:
            point_groups[group].append(_point(
                subject_id,
                point["name"],
                point["description"],
                aliases=point["aliases"],
                learning_action=point["capability"],
                source_type="course_source",
                confidence=1.0,
            ))
            known_point_names.add(normalized_name)

    concepts = {
        "sequential": _concept(subject_id, "sequential", "线性结构", ["核心基础回顾", "数组与链表"], point_groups["sequential"]),
        "heap": _concept(subject_id, "heap", "二叉堆", ["堆", "堆基础", "堆操作"], point_groups["heap"]),
        "avl": _concept(subject_id, "avl", "AVL平衡搜索树", ["AVL树", "AVL旋转", "BST基础"], point_groups["avl"]),
        "hash": _concept(subject_id, "hash", "哈希表", ["哈希基础", "哈希实现"], point_groups["hash"]),
        "graph_representation": _concept(subject_id, "graph_representation", "图的表示", ["图存储"], point_groups["graph_representation"]),
        "graph_traversal": _concept(subject_id, "graph_traversal", "图遍历", ["图算法"], point_groups["graph_traversal"]),
    }
    tree = {
        "knowledge_id": "computer_science",
        "node_type": "subject",
        "name": "计算机科学",
        "description": "研究计算、信息表示、算法与计算系统的学科。",
        **_source("model_inferred", 0.98),
        "children": [{
            "knowledge_id": subject_id,
            "node_type": "domain",
            "name": "数据结构与算法",
            "aliases": ["高级数据结构", "Data Structures and Algorithms"],
            "description": "组织数据并设计可验证、高效操作方法的知识领域。",
            **_source("model_inferred", 0.98),
            "children": [
                _topic(subject_id, "foundations", "基础结构与复杂度", [concepts["sequential"]]),
                _topic(subject_id, "priority", "优先结构", [concepts["heap"]]),
                _topic(subject_id, "search", "搜索树与平衡", [concepts["avl"]]),
                _topic(subject_id, "hashing", "散列结构", [concepts["hash"]]),
                _topic(subject_id, "graphs", "图结构与算法", [concepts["graph_representation"], concepts["graph_traversal"]]),
            ],
        }],
    }
    nodes = {item["name"]: item["knowledge_id"] for item in _walk_tree(tree)}
    relations = [
        _relation(subject_id, nodes["完全二叉树表示"], nodes["堆序性质"], "application", "完全二叉树为堆序操作提供紧凑结构"),
        _relation(subject_id, nodes["堆序性质"], nodes["上浮操作"], "prerequisite", "上浮依据堆序判断交换是否结束"),
        _relation(subject_id, nodes["堆序性质"], nodes["下沉操作"], "prerequisite", "下沉依据堆序选择需要交换的子节点"),
        _relation(subject_id, nodes["平衡因子"], nodes["AVL旋转"], "prerequisite", "旋转类型由失衡方向和平衡因子决定"),
        _relation(subject_id, nodes["AVL旋转"], nodes["AVL高度更新"], "application", "旋转后必须按新拓扑更新高度"),
        _relation(subject_id, nodes["哈希冲突"], nodes["开放寻址删除标记"], "derives", "开放寻址删除必须保持冲突探测链"),
        _relation(subject_id, nodes["邻接矩阵"], nodes["邻接表"], "confusable", "两种图表示在空间和邻接查询成本上取舍不同"),
        _relation(subject_id, nodes["邻接表"], nodes["广度优先搜索"], "application", "邻接表用于枚举BFS的相邻顶点"),
        _relation(subject_id, nodes["广度优先搜索"], nodes["深度优先搜索"], "confusable", "二者的容器、访问顺序和典型用途不同"),
        _relation(subject_id, nodes["图遍历访问标记"], nodes["广度优先搜索"], "prerequisite", "BFS需要访问标记避免重复入队"),
    ]
    skills, mistakes, improvements, skill_relations = _data_structure_standards(subject_id, nodes)
    return {
        "schema_version": SUBJECT_LIBRARY_V3,
        "library_id": identity["library_id"],
        "subject_id": subject_id,
        "version": "3.0.0-candidate",
        "title": "计算机科学·数据结构与算法知识库",
        "match_terms": ["数据结构", "高级数据结构", "算法", "AVL", "哈希表", "图算法", "data structures"],
        "source_refs": [f"course:{course.get('course_id')}", "model:domain-knowledge"],
        "tree": tree,
        "relations": relations,
        "skill_units": skills,
        "mistake_points": mistakes,
        "improvement_points": improvements,
        "skill_relations": skill_relations,
    }


def _build_generic_raw(course: dict[str, Any], identity: dict[str, str]) -> dict[str, Any]:
    topic_rows: list[dict[str, Any]] = []
    for index, section in enumerate(_sections(course)):
        structures = [item for item in section.get("knowledge_structure") or [] if isinstance(item, dict)]
        if not structures:
            structures = [{
                "topic": section.get("node_name") or f"主题{index + 1}",
                "description": section.get("learning_objective") or "",
                "knowledge_points": section.get("key_points") or [section.get("node_name")],
            }]
        for structure in structures:
            name = str(structure.get("topic") or section.get("node_name") or f"主题{index + 1}").strip()
            points = [
                _point(
                    identity["subject_id"],
                    point["name"],
                    point["description"],
                    aliases=point["aliases"],
                    learning_action=point["capability"],
                    source_type="course_source",
                    confidence=1.0,
                )
                for point in (_coerce_point(item) for item in structure.get("knowledge_points") or [])
                if point
            ]
            if points:
                concept = _concept(identity["subject_id"], stable_hash(name), name, [], points)
                topic_rows.append(_topic(identity["subject_id"], stable_hash([name, index]), f"{name}主题", [concept]))
    if not topic_rows:
        fallback = _point(identity["subject_id"], identity["canonical_name"], "课程覆盖的核心知识")
        topic_rows = [_topic(identity["subject_id"], "core", "核心知识", [
            _concept(identity["subject_id"], "core", identity["canonical_name"], [], [fallback])
        ])]
    tree = {
        "knowledge_id": f"subject.{stable_hash(identity['root_name'])}",
        "node_type": "subject",
        "name": identity["root_name"],
        "description": f"{identity['canonical_name']}所属学科。",
        **_source("model_inferred", 0.75),
        "children": [{
            "knowledge_id": identity["subject_id"],
            "node_type": "domain",
            "name": identity["canonical_name"],
            "description": "根据课程资料与模型通识形成的候选学科骨架。",
            **_source("model_inferred", 0.7),
            "children": topic_rows,
        }],
    }
    nodes = {item["name"]: item["knowledge_id"] for item in _walk_tree(tree)}
    point_ids = [item["knowledge_id"] for item in _walk_tree(tree) if item["node_type"] == "knowledge_point"]
    skills = []
    mistakes = []
    improvements = []
    point_rows = [item for item in _walk_tree(tree) if item["node_type"] == "knowledge_point"]
    for index in range(0, len(point_rows), 2):
        group = point_rows[index:index + 3]
        point_id = group[0]["knowledge_id"]
        names = [item["name"] for item in group]
        name = "、".join(names)
        knowledge_ids = [item["knowledge_id"] for item in group]
        skill_id = f"skill.{identity['subject_id']}.{stable_hash(names)}"
        mistake_id = f"mistake.{identity['subject_id']}.{stable_hash(names)}"
        skills.append({"skill_unit_id": skill_id, "name": f"综合解释并应用{name}", "description": f"建立{name}之间的条件、机制与应用联系", "learning_goal": f"能够比较并联合使用{name}", "primary_knowledge_id": point_id, "knowledge_ids": knowledge_ids, **_source("course_source", 0.8)})
        mistakes.append({"mistake_point_id": mistake_id, "skill_unit_id": skill_id, "name": f"混淆{name}的适用边界", "description": f"没有区分{name}各自的对象和成立条件", "misconception": f"认为{name}可以无条件互换", "symptom": f"回答{name}时缺少条件或比较依据", "repair_strategy": f"分别列出{name}的定义、条件和验证方法后再比较", "severity": "medium", "primary_knowledge_id": point_id, "knowledge_ids": knowledge_ids, **_source("model_inferred", 0.6)})
        improvements.append({"improvement_point_id": f"improve.{identity['subject_id']}.{stable_hash(names)}", "skill_unit_id": skill_id, "name": f"迁移应用{name}", "description": f"比较{name}在不同情境中的使用方式", "improvement_goal": f"稳定掌握{name}之间的联系", "practice_strategy": f"完成一个同时涉及{name}的综合任务并解释选择依据", "student_benefit": f"能够在新情境中选择{name}中的合适方法", "primary_knowledge_id": point_id, "knowledge_ids": knowledge_ids, "related_mistake_ids": [mistake_id], **_source("model_inferred", 0.6)})
    return {
        "schema_version": SUBJECT_LIBRARY_V3,
        "library_id": identity["library_id"],
        "subject_id": identity["subject_id"],
        "version": "3.0.0-candidate",
        "title": f"{identity['canonical_name']}候选知识库",
        "match_terms": [identity["canonical_name"], str(course.get("course_name") or "")],
        "source_refs": [f"course:{course.get('course_id')}", "model:domain-knowledge"],
        "tree": tree,
        "relations": [],
        "skill_units": skills,
        "mistake_points": mistakes,
        "improvement_points": improvements,
        "skill_relations": [],
    }


def _data_structure_standards(subject_id: str, nodes: dict[str, str]):
    specs = [
        ("heap_restore", "实现并验证堆序恢复", ["堆序性质", "上浮操作", "下沉操作"], "删除堆顶后遗漏下沉", "把根替换为末尾元素后直接结束，破坏父子堆序。", "替换根后比较两个子节点并持续下沉到堆序恢复。", "对上浮和下沉分别建立循环不变量与边界测试。"),
        ("avl_rotation", "根据失衡路径选择AVL旋转", ["平衡因子", "AVL旋转", "AVL高度更新"], "AVL旋转后高度更新顺序错误", "先更新新根高度，读取了尚未更新的旧根高度。", "先更新下沉节点，再更新上升为根的节点。", "为LL、RR、LR、RL四类旋转记录拓扑和高度变化。"),
        ("hash_probe", "维护开放寻址探测链", ["哈希冲突", "开放寻址删除标记", "负载因子"], "开放寻址删除时直接清空槽位", "直接写为空会让后续查找误判探测链已经结束。", "使用墓碑标记，并在扩容重建时清理墓碑。", "分别测试命中、未命中、删除后查找和高负载场景。"),
        ("graph_choice", "选择图表示并实现遍历", ["邻接矩阵", "邻接表", "广度优先搜索", "深度优先搜索"], "稀疏图仍无条件使用邻接矩阵", "忽略顶点数、边数和邻接查询需求，造成空间浪费。", "先比较V、E及主要操作，再选择矩阵或邻接表。", "同一张图分别用两种结构实现并比较复杂度。"),
        ("bfs_visit", "正确维护图遍历访问状态", ["广度优先搜索", "图遍历访问标记"], "BFS出队后才标记访问", "同一顶点可能在出队前被多个前驱重复加入队列。", "顶点入队时立即标记已发现。", "构造含环和共享邻居的图，记录每个顶点入队次数。"),
    ]
    skills = []
    mistakes = []
    improvements = []
    for key, skill_name, knowledge_names, mistake_name, description, repair, practice in specs:
        knowledge_ids = [nodes[name] for name in knowledge_names]
        skill_id = f"skill.{subject_id}.{key}"
        mistake_id = f"mistake.{subject_id}.{key}"
        skills.append({"skill_unit_id": skill_id, "name": skill_name, "description": skill_name, "learning_goal": skill_name, "primary_knowledge_id": knowledge_ids[0], "knowledge_ids": knowledge_ids, **_source("model_inferred", 0.9)})
        mistakes.append({"mistake_point_id": mistake_id, "skill_unit_id": skill_id, "name": mistake_name, "description": description, "misconception": description, "symptom": mistake_name, "trigger": f"执行{skill_name}时", "repair_strategy": repair, "severity": "high", "primary_knowledge_id": knowledge_ids[0], "knowledge_ids": knowledge_ids, **_source("model_inferred", 0.9)})
        improvements.append({"improvement_point_id": f"improve.{subject_id}.{key}", "skill_unit_id": skill_id, "name": f"强化：{skill_name}", "description": practice, "improvement_goal": skill_name, "practice_strategy": practice, "student_benefit": f"能够独立定位并修复“{mistake_name}”", "primary_knowledge_id": knowledge_ids[0], "knowledge_ids": knowledge_ids, "related_mistake_ids": [mistake_id], **_source("model_inferred", 0.9)})
    skill_relations = [
        {"relation_id": f"skillrel.{subject_id}.representation-traversal", "source_id": f"skill.{subject_id}.graph_choice", "target_id": f"skill.{subject_id}.bfs_visit", "relation_type": "supports", "reason": "正确的图表示是可靠遍历实现的基础", "status": "candidate", **_source("model_inferred", 0.9)},
    ]
    return skills, mistakes, improvements, skill_relations


def _topic(subject_id: str, key: str, name: str, concepts: list[dict[str, Any]]) -> dict[str, Any]:
    return {"knowledge_id": f"{subject_id}.topic.{key}", "node_type": "topic", "name": name, "description": f"{name}的核心概念、机制和应用。", **_source("model_inferred", 0.95), "children": concepts}


def _concept(subject_id: str, key: str, name: str, aliases: list[str], points: list[dict[str, Any]]) -> dict[str, Any]:
    return {"knowledge_id": f"{subject_id}.concept.{key}", "node_type": "concept", "name": name, "aliases": aliases, "description": f"{name}的结构、不变量、操作与复杂度。", **_source("model_inferred", 0.95), "children": points}


def _point(subject_id: str, name: str, description: str, *, aliases=(), learning_action="", source_type="model_inferred", confidence=0.9):
    return {"knowledge_id": f"{subject_id}.point.{stable_hash(_normalize(name))}", "node_type": "knowledge_point", "name": name, "aliases": list(aliases), "description": description, "learning_actions": [learning_action or f"解释并应用{name}"], "typical_problems": [], **_source(source_type, confidence)}


def _relation(subject_id: str, source: str, target: str, relation_type: str, reason: str) -> dict[str, Any]:
    return {"relation_id": f"relation.{subject_id}.{stable_hash([source, target, relation_type])}", "source_knowledge_id": source, "target_knowledge_id": target, "relation_type": relation_type, "reason": reason, "status": "candidate", **_source("model_inferred", 0.9)}


def _source(source_type: str, confidence: float) -> dict[str, Any]:
    return {"source_type": source_type, "source_status": source_type, "confidence": confidence}


def _course_points(course: dict[str, Any]) -> list[dict[str, Any]]:
    points = []
    for section in _sections(course):
        for structure in section.get("knowledge_structure") or []:
            if not isinstance(structure, dict):
                continue
            for raw in structure.get("knowledge_points") or []:
                point = _coerce_point(raw)
                if point:
                    points.append(point)
    return points


def _coerce_point(raw: Any) -> dict[str, Any] | None:
    if isinstance(raw, str):
        name = raw.strip()
        raw = {}
    elif isinstance(raw, dict):
        name = str(raw.get("name") or raw.get("knowledge_point") or "").strip()
    else:
        return None
    if not name:
        return None
    return {"name": name, "description": str(raw.get("description") or f"{name}的定义、机制与适用边界"), "capability": str(raw.get("capability") or f"能够解释并应用{name}"), "aliases": [str(item) for item in raw.get("aliases") or []]}


def _data_structure_group(name: str) -> str:
    value = _normalize(name)
    if any(term in value for term in ("堆", "上浮", "下沉", "优先队列", "完全二叉树")):
        return "heap"
    if any(term in value for term in ("avl", "平衡因子", "旋转", "bst", "搜索树")):
        return "avl"
    if any(term in value for term in ("哈希", "散列", "冲突", "负载因子", "开放寻址")):
        return "hash"
    if any(term in value for term in ("邻接", "图存储", "图表示")):
        return "graph_representation"
    if any(term in value for term in ("bfs", "dfs", "广度优先", "深度优先", "图遍历", "图算法")):
        return "graph_traversal"
    return "sequential"


def _sections(course: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in course.get("nodes") or [] if int(item.get("node_level") or 1) == 2]


def _walk_tree(root: dict[str, Any]) -> list[dict[str, Any]]:
    result = [root]
    for child in root.get("children") or []:
        result.extend(_walk_tree(child))
    return result


def _ancestor_of_type(node_id: str, node_type: str, by_id: dict[str, dict[str, Any]]) -> str | None:
    current = by_id.get(node_id)
    while current:
        if current.get("node_type") == node_type:
            return str(current["knowledge_id"])
        current = by_id.get(str(current.get("parent_id") or ""))
    return None


def _merge_model_payload(raw: dict[str, Any], model_payload: dict[str, Any]) -> dict[str, Any]:
    # V1 accepts only explicit enrichment collections. The deterministic tree
    # remains the identity authority; model output cannot mint formal IDs.
    merged = deepcopy(raw)
    for key in ("relations", "skill_units", "mistake_points", "improvement_points", "skill_relations"):
        if isinstance(model_payload.get(key), list):
            merged[key] = deepcopy(model_payload[key])
    return merged


def _strings(value: Any) -> list[str]:
    return list(dict.fromkeys(
        str(item).strip()
        for item in (value or [])
        if str(item).strip()
    ))


def _proposal_source(
    value: dict[str, Any],
    *,
    default: str,
    confidence: float,
) -> dict[str, Any]:
    source_type = str(value.get("source_type") or default)
    if source_type not in {"course_source", "material_source", "model_inferred", "curated"}:
        source_type = default
    return _source(source_type, float(value.get("confidence") or confidence))


def _proposal_point(value: Any) -> dict[str, Any] | None:
    if isinstance(value, str):
        name = value.strip()
        raw: dict[str, Any] = {}
    elif isinstance(value, dict):
        raw = value
        name = str(raw.get("name") or "").strip()
    else:
        return None
    if not name:
        return None
    return {
        "name": name,
        "description": str(raw.get("description") or f"{name}的定义、机制和应用边界"),
        "aliases": _strings(raw.get("aliases")),
        "learning_action": str(raw.get("learning_action") or raw.get("capability") or f"解释并应用{name}"),
        "typical_problems": _strings(raw.get("typical_problems")),
        "source_type": str(raw.get("source_type") or ""),
        "confidence": raw.get("confidence"),
    }


def _attach_course_structure_aliases(root: dict[str, Any], course: dict[str, Any]) -> None:
    """Bind pedagogical topic labels to the narrowest subject subtree that covers them."""
    candidates = [
        node for node in _walk_tree(root)
        if node.get("node_type") in {"domain", "topic", "concept"}
    ]
    descendant_names: dict[str, set[str]] = {}
    depth = {"domain": 1, "topic": 2, "concept": 3}
    for node in candidates:
        descendant_names[str(node["knowledge_id"])] = {
            _normalize(item.get("name"))
            for item in _walk_tree(node)
            if item.get("node_type") == "knowledge_point" and _normalize(item.get("name"))
        }

    for section in _sections(course):
        for structure in section.get("knowledge_structure") or []:
            if not isinstance(structure, dict):
                continue
            alias = str(structure.get("topic") or "").strip()
            local_names = {
                _normalize(point["name"])
                for point in (_coerce_point(value) for value in structure.get("knowledge_points") or [])
                if point and _normalize(point["name"])
            }
            if not alias or not local_names:
                continue
            covering = [
                node for node in candidates
                if local_names.issubset(descendant_names.get(str(node["knowledge_id"]), set()))
            ]
            if not covering:
                continue
            target = max(
                covering,
                key=lambda node: (
                    depth.get(str(node.get("node_type")), 0),
                    -len(descendant_names.get(str(node["knowledge_id"]), set())),
                ),
            )
            aliases = _strings(target.get("aliases"))
            if _normalize(alias) != _normalize(target.get("name")) and alias not in aliases:
                target["aliases"] = [*aliases, alias]


def _attach_explicit_course_aliases(root: dict[str, Any], proposal: dict[str, Any]) -> None:
    candidates: dict[str, list[dict[str, Any]]] = {}
    for node in _walk_tree(root):
        normalized_name = _normalize(node.get("name"))
        if normalized_name:
            candidates.setdefault(normalized_name, []).append(node)
    for value in proposal.get("course_mappings") or []:
        if not isinstance(value, dict):
            continue
        course_name = str(value.get("course_name") or value.get("local_name") or "").strip()
        knowledge_name = _normalize(value.get("knowledge_name") or value.get("target_name"))
        matches = candidates.get(knowledge_name) or []
        if not course_name or len(matches) != 1:
            continue
        target = matches[0]
        aliases = _strings(target.get("aliases"))
        if _normalize(course_name) != _normalize(target.get("name")) and course_name not in aliases:
            target["aliases"] = [*aliases, course_name]
        sources = list(target.get("alias_sources") or [])
        sources.append({
            "alias": course_name,
            "source_type": "course_source",
            "reason": str(value.get("reason") or "课程局部表述映射到学科规范名称"),
            "confidence": min(1.0, max(0.0, float(value.get("confidence") or 0.8))),
        })
        target["alias_sources"] = sources


def _unique_name_index(nodes: list[dict[str, Any]]) -> dict[str, str]:
    candidates: dict[str, list[str]] = {}
    for node in nodes:
        for name in [node.get("name"), *(node.get("aliases") or [])]:
            normalized = _normalize(name)
            if normalized:
                candidates.setdefault(normalized, []).append(str(node.get("knowledge_id") or ""))
    return {
        name: ids[0]
        for name, ids in candidates.items()
        if len(set(ids)) == 1 and ids[0]
    }


def _resolve_proposal_names(values: Any, name_index: dict[str, str]) -> list[str]:
    resolved = []
    for value in values or []:
        knowledge_id = name_index.get(_normalize(value))
        if knowledge_id and knowledge_id not in resolved:
            resolved.append(knowledge_id)
    return resolved[:5]


def _compile_proposal_relations(
    subject_id: str,
    proposal: dict[str, Any],
    name_index: dict[str, str],
) -> list[dict[str, Any]]:
    relations = []
    seen = set()
    for value in proposal.get("relations") or []:
        if not isinstance(value, dict):
            continue
        source_id = name_index.get(_normalize(value.get("source_name")))
        target_id = name_index.get(_normalize(value.get("target_name")))
        relation_type = str(value.get("relation_type") or "related")
        key = (source_id, target_id, relation_type)
        if (
            not source_id or not target_id or source_id == target_id
            or relation_type not in {"prerequisite", "application", "related", "confusable", "derives"}
            or key in seen
        ):
            continue
        seen.add(key)
        relation = _relation(
            subject_id,
            source_id,
            target_id,
            relation_type,
            str(value.get("reason") or "模型推断的学科关系"),
        )
        relation.update(_proposal_source(value, default="model_inferred", confidence=0.8))
        relations.append(relation)
    return relations


def _compile_proposal_skills(
    subject_id: str,
    proposal: dict[str, Any],
    name_index: dict[str, str],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    skills = []
    by_name = {}
    for value in proposal.get("skills") or []:
        if not isinstance(value, dict):
            continue
        name = str(value.get("name") or "").strip()
        knowledge_ids = _resolve_proposal_names(value.get("knowledge_names"), name_index)
        if not name or not knowledge_ids:
            continue
        skill_id = f"skill.{subject_id}.{stable_hash(_normalize(name))}"
        skills.append({
            "skill_unit_id": skill_id,
            "name": name,
            "description": str(value.get("description") or name),
            "learning_goal": str(value.get("learning_goal") or value.get("description") or name),
            "primary_knowledge_id": knowledge_ids[0],
            "knowledge_ids": knowledge_ids,
            **_proposal_source(value, default="model_inferred", confidence=0.8),
        })
        by_name[_normalize(name)] = skill_id
    return skills, by_name


def _compile_proposal_mistakes(
    subject_id: str,
    proposal: dict[str, Any],
    name_index: dict[str, str],
    skill_name_index: dict[str, str],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    mistakes = []
    by_name = {}
    for value in proposal.get("mistakes") or []:
        if not isinstance(value, dict):
            continue
        name = str(value.get("name") or "").strip()
        knowledge_ids = _resolve_proposal_names(value.get("knowledge_names"), name_index)
        skill_id = skill_name_index.get(_normalize(value.get("skill_name")))
        required = ("description", "misconception", "trigger", "symptom", "repair_strategy")
        if not name or not knowledge_ids or not skill_id or any(not str(value.get(field) or "").strip() for field in required):
            continue
        mistake_id = f"mistake.{subject_id}.{stable_hash(_normalize(name))}"
        mistakes.append({
            "mistake_point_id": mistake_id,
            "skill_unit_id": skill_id,
            "name": name,
            "description": str(value["description"]),
            "misconception": str(value["misconception"]),
            "trigger": str(value["trigger"]),
            "symptom": str(value["symptom"]),
            "repair_strategy": str(value["repair_strategy"]),
            "severity": str(value.get("severity") or "medium"),
            "primary_knowledge_id": knowledge_ids[0],
            "knowledge_ids": knowledge_ids,
            **_proposal_source(value, default="model_inferred", confidence=0.8),
        })
        by_name[_normalize(name)] = mistake_id
    return mistakes, by_name


def _compile_proposal_improvements(
    subject_id: str,
    proposal: dict[str, Any],
    name_index: dict[str, str],
    skill_name_index: dict[str, str],
    mistake_name_index: dict[str, str],
) -> list[dict[str, Any]]:
    improvements = []
    for value in proposal.get("improvements") or []:
        if not isinstance(value, dict):
            continue
        name = str(value.get("name") or "").strip()
        knowledge_ids = _resolve_proposal_names(value.get("knowledge_names"), name_index)
        skill_id = skill_name_index.get(_normalize(value.get("skill_name")))
        related = [
            mistake_name_index[_normalize(item)]
            for item in value.get("related_mistake_names") or []
            if _normalize(item) in mistake_name_index
        ]
        if not name or not knowledge_ids or not skill_id:
            continue
        improvements.append({
            "improvement_point_id": f"improve.{subject_id}.{stable_hash(_normalize(name))}",
            "skill_unit_id": skill_id,
            "name": name,
            "description": str(value.get("description") or name),
            "improvement_goal": str(value.get("improvement_goal") or value.get("description") or name),
            "practice_strategy": str(value.get("practice_strategy") or "完成针对性练习并解释依据"),
            "student_benefit": str(value.get("student_benefit") or "提高迁移应用与自检能力"),
            "primary_knowledge_id": knowledge_ids[0],
            "knowledge_ids": knowledge_ids,
            "related_mistake_ids": list(dict.fromkeys(related)),
            **_proposal_source(value, default="model_inferred", confidence=0.8),
        })
    return improvements


def _source_refs(course: dict[str, Any]) -> list[str]:
    refs = [f"course:{course.get('course_id')}"] if course.get("course_id") else []
    for collection_name in ("uploaded_materials", "source_materials", "materials"):
        for item in course.get(collection_name) or []:
            if isinstance(item, dict):
                material_id = item.get("material_id") or item.get("id") or item.get("name")
            else:
                material_id = item
            if material_id:
                refs.append(f"material:{material_id}")
    return list(dict.fromkeys(refs))


def _actual_source_types(course: dict[str, Any], library: dict[str, Any]) -> list[str]:
    sources = {
        str(item.get("source_type"))
        for collection in ("nodes", "relations", "skill_units", "mistake_points", "improvement_points")
        for item in library.get(collection) or []
        if item.get("source_type")
    }
    if not any(course.get(name) for name in ("uploaded_materials", "source_materials", "materials")):
        sources.discard("material_source")
    return sorted(sources)


def _has_course_materials(course: dict[str, Any]) -> bool:
    return any(course.get(name) for name in ("uploaded_materials", "source_materials", "materials"))


def _sanitize_material_sources(
    course: dict[str, Any],
    library: dict[str, Any],
    *collections: list[dict[str, Any]],
) -> None:
    if _has_course_materials(course):
        return
    for collection in [library.get("nodes") or [], *collections]:
        for item in collection:
            if item.get("source_type") == "material_source":
                item.update(_source("model_inferred", min(float(item.get("confidence") or 0.8), 0.8)))


def _semantic_template_fingerprint(
    item: dict[str, Any],
    fields: tuple[str, ...],
    by_id: dict[str, dict[str, Any]],
) -> str:
    text = " ".join(str(item.get(field) or "") for field in fields).casefold()
    replaceable_names = {
        _normalize((by_id.get(str(knowledge_id)) or {}).get("name"))
        for knowledge_id in [item.get("primary_knowledge_id"), *(item.get("knowledge_ids") or [])]
    }
    normalized = _normalize(text)
    for name in sorted((name for name in replaceable_names if len(name) >= 2), key=len, reverse=True):
        normalized = normalized.replace(name, "知识项")
    normalized = re.sub(r"\d+", "#", normalized)
    return stable_hash(normalized)


def _strip_outline_number(value: Any) -> str:
    text = re.sub(r"^\s*(?:第[一二三四五六七八九十百0-9]+[章节篇部]\s*|[0-9]+(?:\.[0-9]+)*\s*)", "", str(value or ""))
    return _normalize(re.sub(r"(?:主题|概念|知识点)$", "", text))


def _relation_crosses_sections(
    relation: dict[str, Any],
    section_concepts: dict[str, set[str]],
    by_id: dict[str, dict[str, Any]],
) -> bool:
    source_concept = _ancestor_of_type(str(relation.get("source_knowledge_id") or ""), "concept", by_id)
    target_concept = _ancestor_of_type(str(relation.get("target_knowledge_id") or ""), "concept", by_id)
    if not source_concept or not target_concept or source_concept == target_concept:
        return False
    source_sections = {section for section, values in section_concepts.items() if source_concept in values}
    target_sections = {section for section, values in section_concepts.items() if target_concept in values}
    return bool(source_sections and target_sections and source_sections.isdisjoint(target_sections))


def _has_prerequisite_cycle(relations: list[dict[str, Any]]) -> bool:
    graph: dict[str, set[str]] = {}
    for relation in relations:
        if relation.get("relation_type") != "prerequisite":
            continue
        source = str(relation.get("source_knowledge_id") or "")
        target = str(relation.get("target_knowledge_id") or "")
        if source and target:
            graph.setdefault(source, set()).add(target)
            graph.setdefault(target, set())
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> bool:
        if node_id in visiting:
            return True
        if node_id in visited:
            return False
        visiting.add(node_id)
        if any(visit(target) for target in graph.get(node_id) or set()):
            return True
        visiting.remove(node_id)
        visited.add(node_id)
        return False

    return any(visit(node_id) for node_id in graph)


def _issue(code: str, severity: str, message: str) -> dict[str, Any]:
    return {"code": code, "severity": severity, "message": message}


def _normalize(value: Any) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", str(value or "").lower())


__all__ = [
    "SUBJECT_LIBRARY_V3",
    "apply_model_enrichment",
    "build_subject_ontology",
    "build_subject_ontology_from_proposal",
    "evaluate_subject_ontology_quality",
    "resolve_subject_identity",
]
