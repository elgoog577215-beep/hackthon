from course_knowledge_base import (
    bind_course_knowledge_base_to_map,
    build_course_knowledge_library_view,
    compile_course_knowledge_base,
    course_knowledge_base_prompt_context,
    knowledge_binding_for_section,
    validate_course_knowledge_base,
)
from course_knowledge_map import (
    compile_course_knowledge_map,
    project_learning_assets_to_knowledge,
)
from content_blocks import set_node_content_blocks
from learning_assets import (
    compile_learning_asset_plan,
    compile_learning_assets,
    evaluate_learning_asset_quality,
)


def _course() -> dict:
    course = {
        "course_id": "course-data-structures",
        "course_name": "数据结构",
        "course_purpose": "systematic",
        "subject_pedagogy_profile": {
            "primary_mode": "programming_engineering",
            "secondary_mode": None,
            "secondary_intensity": None,
            "confidence": "high",
            "evidence": [],
            "rationale": "测试",
            "enabled_module_ids": [],
            "user_locked": True,
        },
        "nodes": [{
            "node_id": "L2-1-1",
            "node_level": 2,
            "node_name": "线性表与动态数组",
            "learning_objective": "能够实现动态数组扩容并分析摊还复杂度",
            "knowledge_structure": [{
                "topic": "线性表",
                "description": "顺序存储与动态容量管理",
                "knowledge_points": [{
                    "name": "动态数组扩容",
                    "description": "容量耗尽时按倍数扩容，并分析复制成本",
                    "capability": "实现扩容并解释摊还复杂度",
                    "capability_points": [{
                        "name": "动态数组扩容实现",
                        "observable_behavior": "独立实现扩容并说明不变量",
                    }],
                    "mistake_points": [{
                        "name": "把单次复制成本当作每次插入成本",
                        "description": "忽略扩容只在少数插入时发生",
                    }],
                    "improvement_points": [{
                        "name": "比较不同扩容因子",
                        "learning_goal": "在时间和空间约束下选择扩容因子",
                    }],
                    "aliases": ["可变长数组"],
                    "prerequisite_names": [],
                }],
            }],
            "key_points": ["动态数组扩容"],
            "misconceptions": ["忽略扩容复制成本"],
            "assessment": ["在不同扩容因子下比较摊还成本"],
            "difficulty_contract": {
                "challenge": {"reasoning_depth": 3, "transfer_distance": 3},
                "support": {"scaffold_intensity": 3},
                "mastery": {"independence": 3},
                "subject_task": "implementation_task",
            },
            "grounding_contract": {},
            "content_blocks": [],
            "generation_status": "completed",
            "node_content": (
                "## 动态数组扩容\n\n解释扩容不变量与摊还成本。\n\n"
                "## 任务\n\n请实现扩容并在不同约束下比较结果。\n\n"
                "## 检查\n\n检查复制次数、容量和复杂度是否一致。"
            ),
        }],
    }
    set_node_content_blocks(
        course["nodes"][0],
        course["nodes"][0]["node_content"],
    )
    return course


def test_course_knowledge_base_keeps_local_hierarchy_without_formal_subject_pack():
    course = _course()
    course_map = compile_course_knowledge_map(course)
    knowledge_base = compile_course_knowledge_base(course, course_map=course_map)
    course_map = bind_course_knowledge_base_to_map(course_map, knowledge_base)

    assert course_map["coverage"]["mapped_count"] == 0
    assert course_map["coverage"]["course_local_knowledge_point_count"] == 1
    assert course_map["section_course_knowledge_ids"]["L2-1-1"]
    assert all(item["course_knowledge_node_ids"] for item in course_map["mappings"])
    assert knowledge_base["quality_report"]["passed"] is True
    assert knowledge_base["quality_report"]["coverage"]["knowledge_point_count"] == 1
    assert knowledge_base["capability_points"]
    assert knowledge_base["mistake_points"]
    assert knowledge_base["improvement_points"]
    capability_id = knowledge_base["capability_points"][0]["capability_point_id"]
    assert knowledge_base["mistake_points"][0]["capability_point_id"] == capability_id
    assert knowledge_base["improvement_points"][0]["capability_point_id"] == capability_id
    assert validate_course_knowledge_base(knowledge_base, course_data=course)["passed"] is True


def test_course_knowledge_contract_drives_prompt_and_asset_references():
    course = _course()
    bundle = compile_learning_assets(course)
    knowledge_base = bundle["assets"]["course_knowledge_base"][0]
    binding = knowledge_binding_for_section(knowledge_base, "L2-1-1")
    question = bundle["assets"]["questions"][0]
    context = course_knowledge_base_prompt_context(knowledge_base, "L2-1-1")

    assert binding["course_knowledge_refs"]
    assert question["course_knowledge_refs"] == binding["course_knowledge_refs"]
    assert question["course_capability_refs"] == binding["course_capability_refs"]
    assert "知识点：动态数组扩容" in context
    assert "能力点：独立实现扩容并说明不变量" in context
    assert "易错点：忽略扩容只在少数插入时发生" in context
    assert bundle["quality_report"]["passed"] is True


def test_course_local_knowledge_projects_to_existing_student_library_view():
    course = _course()
    bundle = compile_learning_assets(course)
    view = bundle["assets"]["knowledge_library"][0]

    assert view["schema_version"] == "knowledge_library_view_v2"
    assert view["status"] == "active"
    assert view["identity_scope"] == "course_local"
    assert any(node["name"] == "动态数组扩容" for node in view["nodes"])
    assert view["skill_units"]
    assert view["mistake_points"]
    assert view["improvement_points"]


def test_legacy_asset_bundle_gets_current_course_knowledge_projection():
    course = _course()
    legacy_bundle = compile_learning_assets(course)
    legacy_assets = legacy_bundle["assets"]
    legacy_assets.pop("course_knowledge_base", None)
    legacy_assets["knowledge_library"] = [{
        "schema_version": "knowledge_library_view_v2",
        "status": "unavailable",
        "nodes": [],
        "skill_units": [],
        "mistake_points": [],
        "improvement_points": [],
    }]

    projected = project_learning_assets_to_knowledge(course, legacy_assets)
    knowledge_base = projected["course_knowledge_base"][0]
    view = projected["knowledge_library"][0]
    question = projected["questions"][0]
    quality = evaluate_learning_asset_quality(
        course,
        compile_learning_asset_plan(course),
        projected,
    )

    assert knowledge_base["quality_report"]["passed"] is True
    assert view["status"] == "active"
    assert view["identity_scope"] == "course_local"
    assert question["course_knowledge_refs"]
    assert question["course_capability_refs"]
    assert quality["passed"] is True
    assert not any("课程局部知识待归一" in item["message"] for item in quality["issues"])


def test_course_knowledge_validator_rejects_missing_capability_parent():
    course = _course()
    knowledge_base = compile_course_knowledge_base(course)
    knowledge_base["capability_points"] = []

    report = validate_course_knowledge_base(knowledge_base, course_data=course)

    assert report["passed"] is False
    assert any(item["gate"] == "standards" for item in report["issues"])
