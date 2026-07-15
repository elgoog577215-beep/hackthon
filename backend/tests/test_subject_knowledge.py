from copy import deepcopy

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


def test_two_courses_share_formal_knowledge_but_keep_separate_mappings():
    first = compile_course_knowledge_map(_course("course-a"))
    second = compile_course_knowledge_map(_course("course-b"))
    first_mapping = next(item for item in first["mappings"] if item["local_name"] == "高斯消元法步骤与行简化阶梯形")
    second_mapping = next(item for item in second["mappings"] if item["local_name"] == "高斯消元法步骤与行简化阶梯形")

    assert first_mapping["anchor_knowledge_id"] == "math.la.system.gaussian_elimination"
    assert first_mapping["knowledge_ids"] == second_mapping["knowledge_ids"]
    assert first_mapping["mapping_id"] != second_mapping["mapping_id"]
    assert first["sequence_relations"] == []


def test_course_map_keeps_unknown_local_wording_unresolved_without_fake_id():
    course = _course()
    course["nodes"][0]["knowledge_structure"][0]["knowledge_points"].append({
        "name": "老师自定义的三步观察法",
        "description": "课程局部讲法",
        "capability": "完成局部观察",
    })
    course_map = compile_course_knowledge_map(course)
    unresolved = next(
        item for item in course_map["mappings"]
        if item["local_name"] == "老师自定义的三步观察法"
    )

    assert unresolved["match_status"] == "unmapped"
    assert unresolved["anchor_knowledge_id"] is None
    assert unresolved["knowledge_ids"] == []
    assert course_map["coverage"]["status"] == "partial"
    assert any(item["severity"] == "major" for item in validate_course_knowledge_map(course_map, course))


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
    assert projected["course_knowledge_map"][0]["schema_version"] == "course_knowledge_map_v1"
    assert projected["knowledge_library"][0]["schema_version"] == "knowledge_library_view_v2"
    assert "subject_knowledge" not in projected
    assert "teaching_standards" not in projected
    assert projected["questions"][0]["concept_ids"] == ["math.la.system.gaussian_elimination"]
    assert projected["questions"][0]["skill_unit_ids"]
    assert projected["questions"][0]["mistake_point_ids"]
    assert "improvement_point_ids" in projected["questions"][0]
    assert projected["questions"][0]["knowledge_identity_status"] == "compatibility_projection"
    assert legacy_assets == before


def test_course_map_validator_rejects_unknown_formal_asset_reference():
    course = _course()
    course_map = compile_course_knowledge_map(course)
    issues = validate_course_knowledge_map(
        course_map,
        course,
        {"questions": [{"concept_ids": ["missing-formal-knowledge"]}]},
    )

    assert any(item["severity"] == "critical" and "不存在的正式知识" in item["message"] for item in issues)


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
    assert "mistake.la.row-reduction.partial-row" in parent["mistake_point_ids"]
    assert "mistake.la.row-reduction.ref-rref-confused" in parent["mistake_point_ids"]
    assert "improve.la.row-operation-audit" in parent["improvement_ids"]
