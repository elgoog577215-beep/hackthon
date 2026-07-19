from content_blocks import set_node_content_blocks
from course_knowledge_base import (
    bind_course_knowledge_base_to_map,
    compile_course_knowledge_base,
    course_knowledge_base_prompt_context,
    knowledge_binding_for_section,
    validate_course_knowledge_base,
)
from course_knowledge_map import (
    compile_course_knowledge_map,
    project_learning_assets_to_knowledge,
)
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
                "concept_group": "动态容量管理",
                "description": "识别扩容触发条件，并解释倍增扩容的摊还成本",
                "knowledge_points": [{
                    "name": "容量耗尽判定",
                    "statement": "当元素数量等于当前容量时，下一次插入必须先获得更大的连续存储空间。",
                    "knowledge_type": "rule",
                    "conditions": ["使用连续存储且不存在可用槽位"],
                    "boundaries": ["尚有空闲槽位时不触发扩容"],
                    "capability_points": [{
                        "name": "判断扩容触发时机",
                        "observable_behavior": "给定长度与容量，准确判断下一次插入是否触发扩容",
                    }],
                    "mastery_criteria": [{
                        "name": "扩容触发判断达标",
                        "observable_performance": "在不同长度与容量组合中独立判断扩容时机并说明依据",
                        "verification_method": "使用至少三个边界案例进行判断并核对结果",
                    }],
                    "entry_reason": "这是理解动态数组扩容机制的课程入口。",
                    "aliases": ["满容量判定"],
                    "relations": [{
                        "target_name": "动态数组扩容",
                        "relation_type": "prerequisite",
                        "reason": "必须先识别容量耗尽，才能确定何时执行扩容",
                    }],
                }, {
                    "name": "动态数组扩容",
                    "statement": "倍增扩容把少数 O(n) 复制成本分摊到一系列插入，使平均单次插入保持常数阶。",
                    "knowledge_type": "principle",
                    "conditions": ["扩容因子大于 1 且按几何级数增长"],
                    "boundaries": ["结论描述摊还成本，不等于每次插入的最坏成本"],
                    "capability_points": [{
                        "name": "动态数组扩容实现",
                        "observable_behavior": "独立实现倍增扩容并用复制次数解释摊还复杂度",
                    }],
                    "misconceptions": [{
                        "name": "把单次复制成本当作每次插入成本",
                        "observable_error_pattern": "看到一次扩容需要复制 n 个元素，就断言每次插入都是 O(n)",
                        "discrimination": "区分单次操作最坏成本与一系列操作的摊还成本",
                        "repair_strategy": "列出连续插入过程中的扩容位置与累计复制次数后重新计算平均成本",
                    }],
                    "mastery_criteria": [{
                        "name": "扩容实现与分析达标",
                        "observable_performance": "独立实现倍增扩容，并正确说明最坏成本与摊还成本的区别",
                        "verification_method": "运行连续插入测试并提交复杂度推导",
                    }],
                    "aliases": ["可变长数组"],
                }],
            }],
            "key_points": ["容量耗尽判定", "动态数组扩容"],
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
                "## 容量耗尽判定\n\n根据长度与容量识别扩容触发时机。\n\n"
                "## 动态数组扩容\n\n实现倍增扩容，并区分最坏成本与摊还成本。"
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

    knowledge_mappings = [
        item
        for item in course_map["mappings"]
        if item.get("mapping_scope") == "knowledge"
    ]
    assert course_map["coverage"]["mapped_count"] == len(knowledge_mappings)
    assert course_map["coverage"]["mapped_ratio"] == 1.0
    assert course_map["coverage"]["course_local_knowledge_point_count"] == 2
    assert course_map["section_course_knowledge_ids"]["L2-1-1"]
    assert all(item["course_knowledge_node_ids"] for item in course_map["mappings"])
    assert knowledge_base["quality_report"]["passed"] is True
    assert knowledge_base["quality_report"]["coverage"]["knowledge_point_count"] == 2
    assert knowledge_base["skill_units"]
    assert knowledge_base["misconceptions"]
    assert knowledge_base["mastery_criteria"]
    assert knowledge_base["relations"][0]["relation_type"] == "prerequisite"
    assert knowledge_base["improvement_points"] == []
    assert validate_course_knowledge_base(knowledge_base, course_data=course)["passed"] is True


def test_course_knowledge_base_compiles_relation_endpoints_from_stable_ids():
    course = _course()
    points = course["nodes"][0]["knowledge_structure"][0][
        "knowledge_points"
    ]
    points[0].pop("relations", None)
    points[0].pop("entry_reason", None)
    registry = compile_course_knowledge_base(course)
    point_by_name = {
        item["name"]: item for item in registry["knowledge_points"]
    }
    source_id = point_by_name["容量耗尽判定"]["knowledge_id"]
    target_id = point_by_name["动态数组扩容"]["knowledge_id"]
    course["knowledge_relation_schema_version"] = (
        "course_relation_plan_v1"
    )
    course["knowledge_relation_decisions"] = [{
        "knowledge_id": source_id,
        "decision": "course_entry",
        "reason": "这是动态容量管理的课程入口",
    }, {
        "knowledge_id": target_id,
        "decision": "connected",
        "reason": "需要先判断容量是否耗尽",
    }]
    course["knowledge_relations"] = [{
        "source_knowledge_id": source_id,
        "target_knowledge_id": target_id,
        "relation_type": "prerequisite",
        "reason": "必须先识别容量耗尽，才能确定何时执行扩容",
    }]

    knowledge_base = compile_course_knowledge_base(course)

    assert knowledge_base["relations"][0][
        "source_knowledge_id"
    ] == source_id
    assert knowledge_base["relations"][0][
        "target_knowledge_id"
    ] == target_id
    assert knowledge_base["generation_audit"][
        "unresolved_relation_candidates"
    ] == []
    assert {
        item["knowledge_id"]: item["decision"]
        for item in knowledge_base["relation_decisions"]
    } == {
        source_id: "course_entry",
        target_id: "connected",
    }
    entry = next(
        item
        for item in knowledge_base["knowledge_points"]
        if item["knowledge_id"] == source_id
    )
    assert entry["entry_reason"] == "这是动态容量管理的课程入口"


def test_course_knowledge_contract_drives_prompt_and_asset_references():
    course = _course()
    bundle = compile_learning_assets(course)
    knowledge_base = bundle["assets"]["course_knowledge_base"][0]
    binding = knowledge_binding_for_section(knowledge_base, "L2-1-1")
    question = bundle["assets"]["questions"][0]
    mastery_question = bundle["assets"]["questions"][2]
    context = course_knowledge_base_prompt_context(knowledge_base, "L2-1-1")

    assert binding["course_knowledge_refs"]
    assert question["course_knowledge_refs"] == binding["course_knowledge_refs"][:1]
    assert mastery_question["course_knowledge_refs"] == binding["course_knowledge_refs"]
    assert question["course_skill_refs"]
    assert "知识点：动态数组扩容" in context
    assert "能力点：独立实现倍增扩容并用复制次数解释摊还复杂度" in context
    assert "易错点：看到一次扩容需要复制 n 个元素" in context
    assert "掌握标准：独立实现倍增扩容" in context
    assert bundle["quality_report"]["passed"] is True


def test_course_local_knowledge_projects_to_existing_student_library_view():
    course = _course()
    bundle = compile_learning_assets(course)
    view = bundle["assets"]["knowledge_library"][0]

    assert view["schema_version"] == "knowledge_library_view_v3"
    assert view["status"] == "active"
    assert view["identity_scope"] == "course_local"
    assert any(node["name"] == "动态数组扩容" for node in view["nodes"])
    assert view["skill_units"]
    assert view["mistake_points"]
    assert view["mastery_criteria"]
    assert view["improvement_points"] == []
    assert {"course", "section", "concept_group", "knowledge_point"}.issubset(
        {node["node_type"] for node in view["nodes"]}
    )


def test_legacy_asset_bundle_gets_current_course_knowledge_projection():
    course = _course()
    legacy_bundle = compile_learning_assets(course)
    legacy_assets = legacy_bundle["assets"]
    legacy_assets.pop("course_knowledge_base", None)
    legacy_assets["knowledge_library"] = [{
        "schema_version": "knowledge_library_view_v3",
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


def test_course_knowledge_validator_reports_missing_capability_without_blocking():
    course = _course()
    knowledge_base = compile_course_knowledge_base(course)
    knowledge_base["skill_units"] = []

    report = validate_course_knowledge_base(knowledge_base, course_data=course)

    assert report["passed"] is True
    assert report["strict_passed"] is False
    assert any(
        item["code"] == "point_missing_skill"
        and item["severity"] == "major"
        for item in report["issues"]
    )


def test_empty_knowledge_blueprint_reports_compact_actionable_issues():
    section_ids = [
        "01787b5b-f521-4a1a-97d0-e0755676fda9",
        "02c85c15-f7a5-43e8-bc00-70d9ce9d8900",
    ]
    course = {
        "nodes": [
            {"node_id": section_id, "node_level": 2, "node_name": f"Section {index}"}
            for index, section_id in enumerate(section_ids, start=1)
        ],
    }
    knowledge_base = {
        "schema_version": "course_knowledge_base_v2",
        "concept_groups": [],
        "knowledge_points": [],
        "skill_units": [],
        "misconceptions": [],
        "mastery_criteria": [],
        "relations": [],
        "bindings": [],
        "generation_audit": {},
    }

    report = validate_course_knowledge_base(knowledge_base, course_data=course)
    issue_codes = {item["code"] for item in report["issues"]}
    messages = " ".join(item["message"] for item in report["issues"])

    assert "knowledge_blueprint_missing" in issue_codes
    assert not any(code.startswith("invalid_") for code in issue_codes)
    assert "2" in next(
        item["message"] for item in report["issues"]
        if item["code"] == "missing_section_bindings"
    )
    assert not any(section_id in messages for section_id in section_ids)


def test_title_only_legacy_course_is_degraded_instead_of_fabricating_knowledge():
    course = _course()
    section = course["nodes"][0]
    section.pop("knowledge_structure", None)
    section["key_points"] = [section["node_name"]]

    knowledge_base = compile_course_knowledge_base(course)

    assert knowledge_base["lifecycle_status"] == "degraded"
    assert knowledge_base["quality_report"]["strict_passed"] is False
    assert knowledge_base["generation_audit"]["title_fallback_used"] is False
    assert any(
        item["code"] in {"knowledge_blueprint_missing", "missing_section_bindings"}
        for item in knowledge_base["quality_report"]["blocking_issues"]
    )


def test_relation_whitelist_rejects_ambiguous_related_edge():
    course = _course()
    course["nodes"][0]["knowledge_structure"][0]["knowledge_points"][0]["relations"] = [{
        "target_name": "动态数组扩容",
        "relation_type": "related",
        "reason": "两者有关",
    }]

    knowledge_base = compile_course_knowledge_base(course)

    assert knowledge_base["lifecycle_status"] == "active"
    assert knowledge_base["quality_report"]["passed"] is True
    assert knowledge_base["quality_report"]["strict_passed"] is False
    assert knowledge_base["generation_audit"]["invalid_relation_candidates"]
    assert any(
        item["code"] == "invalid_relation_candidates"
        and item["severity"] == "major"
        for item in knowledge_base["quality_report"]["issues"]
    )


def test_later_section_reuses_one_course_knowledge_identity_through_bindings():
    course = _course()
    second = {
        "node_id": "L2-1-2",
        "node_level": 2,
        "node_name": "扩容后的状态保持",
        "learning_objective": "能够迁移元素并检查扩容后的数组状态",
        "reused_knowledge_names": ["容量耗尽判定"],
        "knowledge_structure": [{
            "concept_group": "扩容后状态一致性",
            "description": "在获得新存储空间后保持元素与长度状态一致",
            "knowledge_points": [{
                "name": "扩容后的元素迁移",
                "statement": "扩容后必须按原有逻辑顺序把元素迁移到新的连续存储空间。",
                "knowledge_type": "procedure",
                "conditions": ["已经分配容量更大的连续存储空间"],
                "boundaries": ["尚未完成迁移时不能释放旧存储空间"],
                "capability_points": [{
                    "name": "迁移扩容元素",
                    "observable_behavior": "独立实现元素迁移并保持原有顺序",
                }],
                "mastery_criteria": [{
                    "name": "元素迁移达标",
                    "observable_performance": "独立迁移元素并验证顺序不变",
                    "verification_method": "使用扩容前后数组快照核对",
                }],
                "entry_reason": "这是本节新增知识的入口。",
                "relations": [{
                    "target_name": "扩容后状态校验",
                    "relation_type": "prerequisite",
                    "reason": "完成元素迁移后才能校验扩容后的完整状态",
                }],
            }, {
                "name": "扩容后状态校验",
                "statement": "扩容完成后，元素顺序与长度保持不变，容量更新为新值。",
                "knowledge_type": "rule",
                "conditions": ["元素迁移已经完成"],
                "boundaries": ["容量变化不能被误记为长度变化"],
                "capability_points": [{
                    "name": "校验扩容状态",
                    "observable_behavior": "比较扩容前后快照并指出长度、容量与元素顺序",
                }],
                "mastery_criteria": [{
                    "name": "状态校验达标",
                    "observable_performance": "独立发现长度、容量或顺序中的状态错误",
                    "verification_method": "检查一个含故障的扩容实现",
                }],
            }],
        }],
        "key_points": ["扩容后的元素迁移", "扩容后状态校验"],
        "assessment": ["检查一个扩容实现的状态一致性"],
        "difficulty_contract": {
            "challenge": {"reasoning_depth": 3, "transfer_distance": 3},
            "support": {"scaffold_intensity": 3},
            "mastery": {"independence": 3},
            "subject_task": "implementation_task",
        },
        "grounding_contract": {},
        "content_blocks": [],
        "node_content": (
            "## 容量耗尽判定复查\n\n容量耗尽判定决定是否进入本节的扩容流程。\n\n"
            "## 扩容后的元素迁移\n\n扩容后的元素迁移必须保持原有顺序。\n\n"
            "## 扩容后状态校验\n\n扩容后状态校验分别核对长度、容量和元素顺序。"
        ),
    }
    set_node_content_blocks(second, second["node_content"])
    course["nodes"].append(second)

    bundle = compile_learning_assets(course)
    knowledge_base = bundle["assets"]["course_knowledge_base"][0]
    points = {
        item["name"]: item
        for item in knowledge_base["knowledge_points"]
    }
    second_binding = knowledge_binding_for_section(knowledge_base, "L2-1-2")

    assert knowledge_base["lifecycle_status"] == "active"
    assert set(points["容量耗尽判定"]["section_refs"]) == {"L2-1-1", "L2-1-2"}
    assert points["容量耗尽判定"]["knowledge_id"] in second_binding["course_knowledge_refs"]
    assert len([item for item in knowledge_base["knowledge_points"] if item["name"] == "容量耗尽判定"]) == 1
    projected = [
        item for item in bundle["assets"]["knowledge_library"][0]["nodes"]
        if item["name"] == "容量耗尽判定"
    ]
    assert len(projected) == 1
    assert set(projected[0]["section_ids"]) == {"L2-1-1", "L2-1-2"}

    course["course_knowledge_base"] = knowledge_base
    course["nodes"][1].pop("reused_knowledge_names")
    recompiled = compile_course_knowledge_base(course)
    assert recompiled["lifecycle_status"] == "active"
    assert course["nodes"][1]["reused_knowledge_names"] == ["容量耗尽判定"]
