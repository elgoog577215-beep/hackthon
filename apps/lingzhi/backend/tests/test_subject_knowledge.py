from copy import deepcopy

from course_knowledge_base import (
    bind_course_knowledge_base_to_map,
    compile_course_knowledge_base,
)
from course_knowledge_map import (
    compile_course_knowledge_map,
    project_learning_assets_to_knowledge,
    validate_course_knowledge_map,
)
from subject_knowledge import (
    build_knowledge_library_view,
    knowledge_library_slice,
    load_subject_library,
    resolve_subject_library,
    validate_subject_library,
)


def _course(course_id: str = "course-linear") -> dict:
    return {
        "course_id": course_id,
        "course_name": "线性代数基础",
        "nodes": [{
            "node_id": "L2-1-1",
            "node_level": 2,
            "node_name": "高斯消元",
            "learning_objective": "能够使用高斯消元判断解的结构",
            "knowledge_structure": [{
                "topic": "线性方程组与解结构",
                "description": "从增广矩阵到解分类",
                "knowledge_points": [{
                    "name": "高斯消元法步骤与行简化阶梯形",
                    "description": "通过合法行变换获得阶梯形",
                    "capability": "完成消元并解释每一步",
                    "aliases": [],
                    "prerequisite_names": [],
                }],
            }],
            "key_points": ["高斯消元法步骤与行简化阶梯形"],
            "content_blocks": [{
                "block_id": "block-1",
                "title": "高斯消元法",
                "content": "使用高斯消元法步骤与行简化阶梯形求解。",
                "metadata": {},
            }],
            "grounding_contract": {},
            "prerequisite_node_ids": [],
        }],
    }


def _uncovered_course(course_id: str = "course-data-structures") -> dict:
    return {
        "course_id": course_id,
        "course_name": "高级数据结构入门：可运行实现与应用",
        "subject": "数据结构",
        "nodes": [{
            "node_id": "L2-1-1",
            "node_level": 2,
            "node_name": "线性表与链表",
            "learning_objective": "实现链表操作并分析复杂度",
            "knowledge_structure": [{
                "topic": "链表核心机制",
                "description": "理解链式存储与节点操作",
                "knowledge_points": [{
                    "name": "单链表插入与删除",
                    "description": "维护前驱、后继与头尾边界",
                    "capability": "实现插入和删除并验证边界条件",
                    "aliases": ["单向链表操作"],
                    "prerequisite_names": [],
                }, {
                    "name": "链表操作复杂度",
                    "description": "分析查找、插入和删除的复杂度",
                    "capability": "根据操作位置说明时间复杂度",
                    "aliases": [],
                    "prerequisite_names": ["单链表插入与删除"],
                }],
            }],
            "key_points": ["单链表插入与删除", "链表操作复杂度"],
            "misconceptions": ["忽略头节点和尾节点的边界条件"],
            "content_blocks": [],
            "grounding_contract": {},
            "prerequisite_node_ids": [],
        }],
    }


def test_subject_library_is_independent_fine_grained_and_valid():
    library = load_subject_library("math.linear_algebra.v1")

    assert validate_subject_library(library) == []
    assert library["root_node_id"] == "math"
    assert len(library["nodes"]) >= 80
    assert all("course-linear" not in item["knowledge_id"] for item in library["nodes"])
    leaves = [item for item in library["nodes"] if item["node_type"] == "knowledge_point"]
    assert leaves
    assert "math.la.matrix.row_reduction.solution_preservation" in {
        item["knowledge_id"] for item in leaves
    }


def test_uncovered_course_does_not_generate_a_library_during_read():
    course = _uncovered_course()

    library = resolve_subject_library(course)
    course_map = compile_course_knowledge_map(deepcopy(course), library)

    assert library["library_id"] == "unresolved"
    assert library["nodes"] == []
    assert library["status"] == "unavailable"
    assert course_map["status"] == "awaiting_course_binding"
    assert course_map["coverage"]["mapped_count"] == 0


def test_subject_hint_without_course_structure_remains_unavailable():
    library = resolve_subject_library("一个尚未建设的新学科")

    assert library["library_id"] == "unresolved"
    assert library["nodes"] == []
    assert library["status"] == "unavailable"


def test_subject_alias_cannot_invent_course_points_for_legacy_section():
    course = {
        "course_id": "legacy-linear",
        "course_name": "Legacy linear algebra",
        "nodes": [{
            "node_id": "section-row-reduction",
            "node_level": 2,
            "node_name": "Legacy row-reduction wording",
            "node_content": "A complete explanation of row reduction.",
        }],
    }
    library = deepcopy(load_subject_library("math.linear_algebra.v1"))
    concept = next(
        item for item in library["nodes"]
        if item["knowledge_id"] == "math.la.matrix.row_reduction"
    )
    concept["aliases"] = [*concept.get("aliases", []), "Legacy row-reduction wording"]

    course_map = compile_course_knowledge_map(course, library)

    assert course_map["coverage"]["mapping_count"] == 0
    assert course_map["coverage"]["mapped_count"] == 0
    assert course_map["coverage"]["mapped_ratio"] == 0.0
    assert course_map["mappings"] == []
    assert course["nodes"][0]["knowledge_structure"] == []
    assert course["nodes"][0]["knowledge_structure_status"] == "needs_enrichment"


def test_pedagogical_project_scaffolding_is_excluded_from_mapping_denominator():
    course = _uncovered_course()
    course["nodes"].append({
        "node_id": "project",
        "node_level": 2,
        "node_name": "6.1 项目设计与架构",
        "knowledge_structure": [{
            "topic": "系统设计",
            "knowledge_points": ["需求定义", "架构选择"],
        }],
        "content_blocks": [],
    })

    course_map = compile_course_knowledge_map(course, resolve_subject_library(course))

    assert course_map["coverage"]["excluded_pedagogical_count"] == 3
    assert course_map["coverage"]["mapping_count"] == 3
    assert all(
        mapping["mapping_scope"] == "pedagogical"
        for mapping in course_map["mappings"]
        if mapping["section_id"] == "project"
    )


def test_two_courses_with_same_wording_keep_separate_knowledge_identity():
    first_course = _course("course-a")
    second_course = _course("course-b")
    first = bind_course_knowledge_base_to_map(
        compile_course_knowledge_map(first_course),
        compile_course_knowledge_base(first_course),
    )
    second = bind_course_knowledge_base_to_map(
        compile_course_knowledge_map(second_course),
        compile_course_knowledge_base(second_course),
    )
    first_mapping = next(item for item in first["mappings"] if item["local_name"] == "高斯消元法步骤与行简化阶梯形")
    second_mapping = next(item for item in second["mappings"] if item["local_name"] == "高斯消元法步骤与行简化阶梯形")

    assert first_mapping["anchor_knowledge_id"].startswith("ckp_")
    assert second_mapping["anchor_knowledge_id"].startswith("ckp_")
    assert first_mapping["knowledge_ids"] != second_mapping["knowledge_ids"]
    assert first_mapping["mapping_id"] != second_mapping["mapping_id"]
    assert first["sequence_relations"] == []


def test_course_map_assigns_custom_wording_a_course_local_id():
    course = _course()
    course["nodes"][0]["knowledge_structure"][0]["knowledge_points"].append({
        "name": "老师自定义的三步观察法",
        "description": "课程局部讲法",
        "capability": "完成局部观察",
    })
    course_map = bind_course_knowledge_base_to_map(
        compile_course_knowledge_map(course),
        compile_course_knowledge_base(course),
    )
    custom = next(
        item for item in course_map["mappings"]
        if item["local_name"] == "老师自定义的三步观察法"
    )

    assert custom["match_status"] == "course_local"
    assert custom["anchor_knowledge_id"].startswith("ckp_")
    assert custom["knowledge_ids"] == [custom["anchor_knowledge_id"]]
    assert course_map["coverage"]["status"] == "mapped"


def test_legacy_graph_is_only_migration_input_and_is_not_returned():
    course = _course()
    legacy_assets = {
        "knowledge_graph": [{
            "concepts": [{
                "concept_id": "legacy-gaussian",
                "label": "高斯消元法",
                "node_ids": ["L2-1-1"],
            }],
        }],
        "questions": [{
            "asset_id": "question-1",
            "question_id": "question-1",
            "concept_ids": ["legacy-gaussian"],
        }],
    }
    before = deepcopy(legacy_assets)

    projected = project_learning_assets_to_knowledge(course, legacy_assets)

    assert "knowledge_graph" not in projected
    assert projected["course_knowledge_map"][0]["schema_version"] == "course_knowledge_map_v2"
    assert projected["knowledge_library"][0]["schema_version"] == "knowledge_library_view_v3"
    assert "subject_knowledge" not in projected
    assert "teaching_standards" not in projected
    assert projected["questions"][0]["concept_ids"] == ["legacy-gaussian"]
    assert not any(
        str(item).startswith("math.")
        for item in projected["questions"][0]["concept_ids"]
    )
    assert projected["knowledge_library"][0]["identity_scope"] == "course_local"
    assert legacy_assets == before


def test_read_projection_ignores_a_legacy_pinned_subject_library():
    library = load_subject_library("math.linear_algebra.v1")
    course = _course()
    course["knowledge_library_binding"] = {
        "library_id": library["library_id"],
        "revision_id": library["revision_id"],
        "binding_status": "pinned",
    }

    projected = project_learning_assets_to_knowledge(course, {})

    assert projected["course_knowledge_base"][0]["schema_version"] == "course_knowledge_base_v2"
    assert projected["knowledge_library"][0]["library_id"].startswith("ckb_")
    assert projected["knowledge_library"][0]["library_id"] != library["library_id"]
    assert projected["knowledge_library"][0]["identity_scope"] == "course_local"


def test_course_map_validator_rejects_unknown_formal_asset_reference():
    course = _course()
    course_map = compile_course_knowledge_map(course)
    issues = validate_course_knowledge_map(
        course_map,
        course,
        {"questions": [{"concept_ids": ["missing-formal-knowledge"]}]},
    )

    assert any(item["severity"] == "critical" and "不存在的正式知识或课程知识" in item["message"] for item in issues)


def test_unified_library_nests_skills_mistakes_and_improvements():
    library = resolve_subject_library(_course())
    selected = knowledge_library_slice(
        library,
        ["math.la.matrix.row_reduction.operations"],
    )

    assert validate_subject_library(library) == []
    assert selected["skill_units"]
    assert selected["mistake_points"]
    assert selected["improvement_points"]
    assert selected["usage_policy"]["ai_must_judge_independently"] is True
    assert selected["usage_policy"]["allowed_fit"] == ["hit", "partial", "miss"]
    skill_ids = {item["skill_unit_id"] for item in selected["skill_units"]}
    assert all(item["skill_unit_id"] in skill_ids for item in selected["mistake_points"])
    assert all(item["skill_unit_id"] in skill_ids for item in selected["improvement_points"])


def test_knowledge_view_projects_skill_children_to_the_parent_knowledge_node():
    library = resolve_subject_library(_course())
    view = build_knowledge_library_view(
        library,
        {
            "revision_id": "map-row-reduction",
            "mappings": [{
                "section_id": "L2-1-1",
                "anchor_knowledge_id": "math.la.matrix.row_reduction",
                "knowledge_ids": ["math.la.matrix.row_reduction.operations"],
                "block_ids": [],
                "objective_ids": [],
            }],
            "coverage": {},
            "unresolved_candidates": [],
        },
        {},
    )
    parent = next(
        item for item in view["nodes"]
        if item["knowledge_id"] == "math.la.matrix.row_reduction"
    )

    assert "skill.la.matrix.row.reduction" in parent["skill_unit_ids"]
    root = next(item for item in view["nodes"] if item["knowledge_id"] == "math")
    assert "skill.la.matrix.row.reduction" in root["skill_unit_ids"]
    assert root["mistake_point_ids"]
    assert root["improvement_ids"]
    assert "mistake.la.row-reduction.partial-row" in parent["mistake_point_ids"]
    assert "mistake.la.row-reduction.ref-rref-confused" in parent["mistake_point_ids"]
    assert "improve.la.row-operation-audit" in parent["improvement_ids"]
