"""教案呈现对象：栏目恒定、时序可派生、对应关系可见、颗粒度可对照。

这四条正是「像模型写出的丰富文本」与「教师拿来就能上课的教案」之间的差别，
所以它们必须由测试钉住，而不是靠前端 `v-if` 碰运气。
"""

from course_lesson_dossier import (
    RUBRIC_KEYS,
    build_lesson_dossier,
    build_lesson_dossier_consistency,
)

MODULE_PLAN = [
    {"module_id": "lesson_goal", "label": "本节任务", "block_role": "objective", "required": True},
    {"module_id": "core_explanation", "label": "核心教学", "block_role": "concept", "required": True},
    {"module_id": "learner_action", "label": "学习者行动", "block_role": "activity", "required": True},
    {"module_id": "feedback_check", "label": "检查与反馈", "block_role": "feedback", "required": True},
]

ARCHETYPE = {
    "archetype_id": "math_intuition_representation",
    "label": "直觉与多重表征",
    "mode": "math_formal",
    "course_stage": "foundation",
    "purpose": "从问题或表征建立直觉，再连接正式定义。",
    "evidence_contract": "学习者能在两种表征之间转换。",
    "guardrails": ["符号必须先有意义再被使用"],
    "module_ids": ["math_intuition", "math_representation"],
}


def _section(**overrides):
    section = {
        "node_id": "L2-1-1",
        "key_points": ["线性组合"],
        "reused_knowledge_names": ["向量加法"],
        "knowledge_relations": [],
        "planned_minutes": 45,
        "key_difficulties": ["系数与分量混淆"],
        "teacher_activities": ["演示向量缩放"],
        "student_activities": ["拖动系数"],
        "in_class_checks": ["用出口题检查线性组合的系数是否正确"],
        "homework": ["完成两个分解练习"],
        "resource_refs": ["坐标纸"],
        "teaching_notes": ["板书保留几何图"],
        "teaching_modules": [
            {
                "module_id": "lesson_goal",
                "teaching_purpose": "说明本节任务",
                "knowledge_names": ["线性组合"],
            },
            {
                "module_id": "core_explanation",
                "teaching_purpose": "讲清线性组合",
                "knowledge_names": ["线性组合"],
            },
            {
                "module_id": "learner_action",
                "teaching_purpose": "让学生动手",
                "knowledge_names": ["线性组合"],
                "planned_minutes": 15,
            },
            {
                "module_id": "feedback_check",
                "teaching_purpose": "核对结果",
                "knowledge_names": [],
            },
        ],
        "knowledge_structure": [{
            "concept_group": "核心机制",
            "knowledge_points": [{
                "knowledge_id": "k-1",
                "name": "线性组合",
                "statement": "向量按标量加权后相加。",
                "knowledge_type": "concept",
                "prerequisite_names": ["向量加法"],
                "capability_points": [{"observable_behavior": "能写出目标向量的系数组合"}],
                "mastery_criteria": [{
                    "observable_performance": "独立完成两组分解",
                    "verification_method": "课堂出口题",
                }],
                "misconceptions": [{
                    "observable_error_pattern": "把系数当作向量分量",
                    "discrimination": "看系数是否随基改变",
                    "repair_strategy": "用几何缩放重新辨析",
                }],
            }],
        }],
    }
    section.update(overrides)
    return section


def _build(section, **kwargs):
    kwargs.setdefault("sequence", 1)
    kwargs.setdefault("node_title", "向量的线性组合")
    kwargs.setdefault("chapter_title", "第一章 向量")
    kwargs.setdefault("learning_objective", "能用线性组合解释生成关系")
    kwargs.setdefault("lesson_archetype", ARCHETYPE)
    kwargs.setdefault("module_plan", MODULE_PLAN)
    return build_lesson_dossier(section, **kwargs)


def _rubric(dossier, key):
    return next(item for item in dossier["rubrics"] if item["key"] == key)


def test_rubric_structure_is_identical_for_full_and_empty_sections():
    """同一门课任取三节，栏目结构必须一致——这是本条验收的硬事实。

    内容最丰富的一节和几乎空白的一节放在一起比：栏目键、顺序、数量必须完全相同，
    差别只体现在每栏的 status 上。
    """
    full = _build(_section())
    sparse = _build({"node_id": "L2-1-2", "teaching_modules": []}, sequence=2)

    assert [item["key"] for item in full["rubrics"]] == list(RUBRIC_KEYS)
    assert [item["key"] for item in sparse["rubrics"]] == list(RUBRIC_KEYS)
    assert len(full["rubrics"]) == len(sparse["rubrics"]) == len(RUBRIC_KEYS)
    # 空小节不是“少几栏”，而是“同样的栏目里没有内容”。
    assert _rubric(sparse, "homework")["status"] == "empty"
    assert _rubric(sparse, "homework")["item_count"] == 0
    assert _rubric(full, "homework")["status"] == "filled"


def test_timeline_allocates_declared_minutes_and_marks_derived_entries():
    timeline = _rubric(_build(_section()), "timeline")

    assert timeline["total_minutes"] == 45
    assert timeline["minutes_basis"] == "section_planned"
    assert timeline["continuous"] is True
    # 教师填的 15 分钟不动，其余按课程块角色摊掉剩下的 30 分钟。
    action = next(e for e in timeline["entries"] if e["module_id"] == "learner_action")
    assert (action["minutes"], action["minutes_source"]) == (15, "planned")
    assert timeline["derived_count"] == 3
    assert sum(entry["minutes"] for entry in timeline["entries"]) == 45
    # 起止时刻必须首尾相接，教师照着这一列就能上课。
    assert timeline["entries"][0]["start_minute"] == 0
    assert timeline["entries"][-1]["end_minute"] == 45
    for previous, current in zip(timeline["entries"], timeline["entries"][1:]):
        assert previous["end_minute"] == current["start_minute"]
    # 环节名来自冻结的 module_plan，不是模型自由发挥的标题。
    assert [entry["label"] for entry in timeline["entries"]][:2] == ["本节任务", "核心教学"]


def test_timeline_falls_back_to_course_duration_and_stays_unset_without_any_source():
    section = _section()
    section.pop("planned_minutes")

    fallback = _rubric(
        _build(section, course_lesson_minutes=40, course_minutes_basis="course_median"),
        "timeline",
    )
    assert fallback["minutes_basis"] == "course_median"
    assert sum(entry["minutes"] for entry in fallback["entries"]) == 40

    unset = _rubric(_build(section), "timeline")
    # 没有任何已声明的时长时不编造分钟数，只是把时序留空。
    assert unset["minutes_basis"] == "unset"
    assert unset["continuous"] is False
    assert unset["derived_count"] == 0
    # 教师自己填过的环节时长仍然保留，其余留空而不是补 0。
    assert [entry["minutes"] for entry in unset["entries"]] == [None, None, 15, None]
    assert unset["status"] == "filled"  # 栏目仍在，只是没有分钟


def test_alignment_links_knowledge_to_modules_criteria_and_checks():
    alignment = _rubric(_build(_section()), "alignment")

    row = alignment["rows"][0]
    assert row["name"] == "线性组合"
    assert row["ownership"] == "owned"
    assert [item["label"] for item in row["modules"]] == ["本节任务", "核心教学", "学习者行动"]
    assert row["capabilities"] == ["能写出目标向量的系数组合"]
    assert row["mastery"] == [{
        "performance": "独立完成两组分解",
        "verification": "课堂出口题",
    }]
    # 课堂检查按知识点名称回挂，教师能直接看出哪条检查覆盖哪个知识点。
    assert row["checks"] == ["用出口题检查线性组合的系数是否正确"]
    assert row["gaps"] == []
    assert alignment["gap_count"] == 0


def test_alignment_reports_gaps_instead_of_inventing_evaluation():
    section = _section(
        in_class_checks=[],
        homework=[],
        teaching_modules=[],
    )
    section["knowledge_structure"][0]["knowledge_points"][0]["mastery_criteria"] = []

    alignment = _rubric(_build(section), "alignment")
    row = alignment["rows"][0]

    assert row["mastery"] == []
    assert row["checks"] == []
    # 缺口如实报出来，绝不替模型补一条掌握标准。
    assert set(row["gaps"]) == {"module", "mastery", "evidence"}
    assert alignment["gap_count"] == 1


def test_template_contract_exposes_module_conformance_for_future_top_level_contract():
    section = _section()
    section["teaching_modules"] = [
        {"module_id": "core_explanation", "teaching_purpose": "讲清"},
        {"module_id": "surprise_module", "teaching_purpose": "模型自己加的"},
    ]

    template = _build(section)["template"]

    assert template["schema_version"] == "lesson_template_contract_v1"
    assert template["contract_state"] == "projected_from_archetype"
    assert template["template_id"] == "math_intuition_representation"
    assert template["evidence_contract"] == "学习者能在两种表征之间转换。"
    assert template["guardrails"] == ["符号必须先有意义再被使用"]
    # 顶层合同还没落地，版本位留空但字段先在——将来只补值，不改结构。
    assert template["template_version"] == ""
    conformance = template["module_conformance"]
    assert conformance["missing_required"] == ["lesson_goal", "learner_action", "feedback_check"]
    assert conformance["unplanned"] == ["surprise_module"]
    assert conformance["matched"] == 1


def test_template_contract_degrades_when_section_has_no_archetype():
    template = _build(_section(), lesson_archetype=None)["template"]

    assert template["contract_state"] == "unbound"
    assert template["template_id"] == ""
    # 没有课型的旧课程仍然要有完整栏目，不能整块消失。
    assert template["planned_module_ids"] == [item["module_id"] for item in MODULE_PLAN]


def test_objectives_carry_source_so_teachers_can_tell_outline_from_capability():
    objectives = _rubric(_build(_section()), "objectives")

    assert objectives["items"][0] == {
        "text": "能用线性组合解释生成关系",
        "source": "outline",
        "knowledge_name": "",
    }
    assert objectives["items"][1] == {
        "text": "能写出目标向量的系数组合",
        "source": "capability",
        "knowledge_name": "线性组合",
    }


def test_consistency_reports_uniform_structure_and_only_real_outliers():
    def _bulky(count: int) -> dict:
        section = _section(node_id="L2-1-4", key_points=[f"知识{index}" for index in range(count)])
        section["knowledge_structure"][0]["knowledge_points"] = [
            {"name": f"知识{index}", "statement": "说明"} for index in range(count)
        ]
        return section

    dossiers = [
        _build(_section(), sequence=1),
        _build(
            _section(node_id="L2-1-2", in_class_checks=[], homework=[]),
            sequence=2,
            node_title="张成空间",
        ),
        _build(
            _section(node_id="L2-1-3", in_class_checks=[], homework=[]),
            sequence=3,
            node_title="基与维数",
        ),
        _build(_bulky(9), sequence=4, node_title="综合应用"),
    ]

    report = build_lesson_dossier_consistency(dossiers)

    assert report["uniform_rubric_structure"] is True
    assert report["rubric_keys"] == list(RUBRIC_KEYS)
    assert report["section_count"] == 4
    coverage = {item["key"]: item for item in report["rubric_coverage"]}
    assert coverage["timeline"]["filled_sections"] == 4
    assert coverage["homework"]["filled_sections"] == 2
    # 前三节颗粒度一致，只有堆了 9 个知识点的那一节被点名。
    assert report["outlier_node_ids"] == ["L2-1-4"]
    bulky = next(item for item in report["sections"] if item["node_id"] == "L2-1-4")
    assert "knowledge_point_count_above_band" in bulky["flags"]


def test_consistency_does_not_flag_metrics_nobody_filled():
    dossiers = [
        _build(_section(in_class_checks=[]), sequence=index + 1)
        for index in range(3)
    ]

    report = build_lesson_dossier_consistency(dossiers)

    assert report["bands"]["check_count"]["filled_sections"] == 0
    # 全课都没写课堂检查是整体缺失，不能变成每一节各挂一个“偏低”。
    assert all(
        "check_count_below_band" not in item["flags"]
        for item in report["sections"]
    )
    assert report["outlier_node_ids"] == []
