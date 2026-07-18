from copy import deepcopy

import pytest

from question_bank import build_question_bank, evaluate_question_item_quality


def _course_for(
    *,
    mode: str,
    topic: str,
    objective: str,
    key_points: list[str],
    assessment: str,
) -> dict:
    return {
        "course_id": f"course-{mode}",
        "course_name": topic,
        "course_purpose": "systematic",
        "difficulty": "intermediate",
        "generation_request": {
            "course_purpose": "systematic",
            "web_question_enrichment": {"enabled": False},
        },
        "material_bindings": [],
        "evidence_catalog": [],
        "subject_pedagogy_profile": {"primary_mode": mode},
        "nodes": [{
            "node_id": "L2-1-1",
            "node_level": 2,
            "node_name": topic,
            "learning_objective": objective,
            "key_points": key_points,
            "assessment": [assessment],
            "grounding_contract": {"question_evidence_ids": []},
            "difficulty_contract": {"target_level": "intermediate"},
        }],
    }


def _practice_items(course: dict) -> list[dict]:
    return [
        item
        for item in build_question_bank(course)["items"]
        if item["assessment_role"] == "practice"
    ]


def test_graph_questions_use_a_solvable_graph_contract_and_course_evidence():
    course = _course_for(
        mode="programming_engineering",
        topic="5.2 基本图算法",
        objective="编码BFS和DFS并解决简单问题",
        key_points=["BFS实现", "DFS实现"],
        assessment="运行遍历算法并输出访问顺序",
    )
    course["course_document"] = {
        "schema_version": "course_document_v1",
        "blocks": [{
            "block_id": "L2-1-1-checkpoint",
            "section_id": "L2-1-1",
            "role": "checkpoint",
            "kind": "rich_text",
            "payload": {
                "title": "构建测试图并预测遍历顺序",
                "markdown": "给定邻接表，从顶点A开始模拟BFS和DFS。",
            },
        }],
    }

    generated = _practice_items(course)

    assert len(generated) == 3
    assert all(
        item["question_spec"]["adapter_id"]
        == "computer_science.graph_traversal"
        for item in generated
    )
    assert all(
        item["question_spec"]["stimulus"]["kind"] == "graph"
        and item["question_spec"]["stimulus"]["data"]["vertices"]
        and item["question_spec"]["stimulus"]["data"]["edges"]
        and item["question_spec"]["stimulus"]["data"]["start_vertex"]
        and item["question_spec"]["stimulus"]["data"]["neighbor_order"]
        for item in generated
    )
    assert all(
        item["answer_spec"]["canonical_answer"]["bfs_order"]
        and item["answer_spec"]["canonical_answer"]["dfs_order"]
        for item in generated
    )
    assert all(item["domain_validation"]["passed"] for item in generated)
    assert all(item["quality_report"]["passed"] for item in generated)
    assert all(item["lifecycle_status"] == "approved" for item in generated)
    assert all(
        "输入 JSON=" not in item["prompt"]
        and "状态码 200" not in item["prompt"]
        for item in generated
    )
    assert all(
        any(
            source.get("source_type") == "course_document"
            and source.get("block_id") == "L2-1-1-checkpoint"
            for source in item["source_records"]
        )
        for item in generated
    )


def test_avl_implementation_target_emits_code_tests_domain_hints_and_solution():
    course = _course_for(
        mode="programming_engineering",
        topic="3.3 AVL树实现与测试",
        objective="构建可运行AVL树并验证平衡",
        key_points=["AVL插入实现", "旋转操作", "性能测试"],
        assessment="提交AVL实现并运行正确性与性能测试",
    )

    generated = _practice_items(course)

    assert len(generated) == 3
    assert all(
        item["question_spec"]["archetype_id"]
        == "avl_implementation_validation"
        for item in generated
    )
    assert all(
        item["question_spec"]["stimulus"]["data"]["case_kind"]
        == "avl_implementation"
        and "def rebalance" in item["question_spec"]["stimulus"]["data"]["code_skeleton"]
        and item["question_spec"]["stimulus"]["data"]["test_cases"]
        for item in generated
    )
    assert all(
        "实现" in item["question_spec"]["task"]["rendered_text"]
        and "测试" in item["question_spec"]["task"]["rendered_text"]
        and "性能" in item["question_spec"]["task"]["rendered_text"]
        for item in generated
    )
    assert all(
        item["domain_validation"]["checks"]["semantic_alignment"] is True
        and item["domain_validation"]["passed"] is True
        for item in generated
    )
    assert all(
        item["answer_spec"]["solution_spec"]["schema_version"]
        == "solution_spec_v1"
        and item["answer_spec"]["solution_spec"]["steps"]
        and item["answer_spec"]["solution_spec"]["checks"]
        and item["answer_spec"]["solution_spec"]["representation"]["kind"]
        == "code"
        for item in generated
    )

    first_hints = generated[0]["hint_contract"]["levels"]
    assert "30、20、10" in first_hints[0]["content"]
    assert "BST定位" in first_hints[1]["content"]
    assert "[50, 30, 40]" in first_hints[2]["content"]
    assert "LR" in first_hints[2]["content"]
    assert generated[0]["hint_contract"]["leakage_check"]["passed"] is True


@pytest.mark.parametrize(
    ("mode", "topic", "objective", "key_points", "assessment", "stimulus_kind"),
    [
        (
            "math_formal",
            "二元线性方程组",
            "使用消元法求解并检查方程组",
            ["高斯消元", "回代"],
            "求解方程组并验证",
            "quantitative_problem",
        ),
        (
            "programming_engineering",
            "数据清洗函数",
            "实现可测试的数据清洗函数",
            ["空值处理", "重复值处理"],
            "实现函数并运行测试",
            "programming_case",
        ),
        (
            "natural_science",
            "温度与反应速率",
            "根据对照实验解释温度的影响",
            ["控制变量", "实验误差"],
            "分析实验数据并解释结论",
            "controlled_experiment",
        ),
        (
            "life_medical",
            "血糖调节机制",
            "根据案例解释血糖调节机制",
            ["胰岛素", "稳态调节"],
            "解释案例中的调节过程",
            "mechanism_case",
        ),
        (
            "humanities_social",
            "工业革命史料分析",
            "使用史料论证工业革命的社会影响",
            ["史料证据", "因果论证"],
            "形成有证据支持的历史论证",
            "source_set",
        ),
        (
            "language_learning",
            "过去完成时的语境表达",
            "在真实语境中正确使用过去完成时",
            ["过去完成时", "时间顺序"],
            "根据语境完成英文表达",
            "language_context",
        ),
        (
            "business_career",
            "项目方案决策",
            "在预算和周期约束下选择项目方案",
            ["成本收益", "风险权衡"],
            "比较方案并提出建议",
            "decision_case",
        ),
    ],
)
def test_supported_subject_families_emit_validated_structured_specs(
    mode: str,
    topic: str,
    objective: str,
    key_points: list[str],
    assessment: str,
    stimulus_kind: str,
):
    course = _course_for(
        mode=mode,
        topic=topic,
        objective=objective,
        key_points=key_points,
        assessment=assessment,
    )

    generated = _practice_items(course)

    assert len(generated) == 3
    assert all(
        item["question_spec"]["schema_version"] == "question_spec_v1"
        and item["question_spec"]["subject_family"] == mode
        and item["question_spec"]["stimulus"]["kind"] == stimulus_kind
        and item["question_spec"]["target"]["objective"] == objective
        for item in generated
    )
    assert all(item["domain_validation"]["passed"] for item in generated)
    assert all(item["answer_spec"]["criteria"] for item in generated)
    assert all(item["quality_report"]["checks"]["domain_validation"] for item in generated)
    if mode == "life_medical":
        assert all(item["lifecycle_status"] == "needs_review" for item in generated)
        assert all("high_stakes_domain" in item["risk_flags"] for item in generated)
    else:
        assert all(item["lifecycle_status"] == "approved" for item in generated)


def test_legacy_linear_algebra_course_without_profile_infers_math_adapter():
    course = _course_for(
        mode="general",
        topic="1.5 线性组合与生成集",
        objective="判断给定向量是否属于一组向量的生成空间",
        key_points=["线性组合", "生成集", "Span"],
        assessment="求解组合系数并代回检查",
    )
    course["course_id"] = "legacy-linear-algebra"
    course["course_name"] = "《线性代数：理论与应用》"
    course.pop("subject_pedagogy_profile")

    bundle = build_question_bank(course)
    generated = [
        item for item in bundle["items"]
        if item["assessment_role"] == "practice"
    ]

    assert generated
    assert all(
        item["question_spec"]["subject_family"] == "math_formal"
        and item["question_spec"]["adapter_id"] == "math.quantitative_reasoning"
        and item["domain_validation"]["passed"]
        and item["lifecycle_status"] == "approved"
        for item in generated
    )
    assert all("尚无可验证的专属题型契约" not in item["prompt"] for item in generated)
    assert bundle["coverage"]["coverage_ratio"] == 1


def test_math_student_prompt_is_concise_while_internal_contract_stays_complete():
    course = _course_for(
        mode="math_formal",
        topic="1.1 向量空间的公理化定义",
        objective="依据向量空间定义完成计算并检查结论",
        key_points=["向量空间", "封闭性", "运算公理"],
        assessment="完成当前任务",
    )

    generated = _practice_items(course)

    assert generated
    for item in generated:
        prompt = item["prompt"]
        spec = item["question_spec"]

        assert len(prompt) <= 160
        assert spec["stimulus"]["rendered_text"] in prompt
        assert spec["task"]["rendered_text"] in prompt
        assert all(
            marker not in prompt
            for marker in (
                "评分检查点",
                "完成目标任务",
                "完成当前任务",
                "输入材料：",
                "限制条件：",
                "输出要求：",
                "概念辨析｜",
                "情境应用｜",
                "独立达标｜",
            )
        )
        assert spec["answer_spec"]["criteria"]
        assert spec["constraints"]
        assert spec["result_checks"]


def test_programming_student_prompt_omits_rubric_boilerplate():
    course = _course_for(
        mode="programming_engineering",
        topic="Python 标准输出与返回值",
        objective="区分 print 的标准输出副作用和返回值",
        key_points=["标准输出", "print 返回值"],
        assessment="运行代码并解释输出与返回值的区别",
    )

    generated = _practice_items(course)

    assert generated
    assert all("评分检查点" not in item["prompt"] for item in generated)
    assert all("完成目标任务" not in item["prompt"] for item in generated)
    assert all("限制条件：" not in item["prompt"] for item in generated)
    assert all(
        item["question_spec"]["answer_spec"]["criteria"]
        and item["question_spec"]["constraints"]
        for item in generated
    )


def test_unknown_subject_adapter_never_auto_publishes_or_counts_as_coverage():
    course = _course_for(
        mode="general",
        topic="未知跨领域主题X",
        objective="完成尚未定义的跨领域任务",
        key_points=["未知能力A", "未知能力B"],
        assessment="提交成果",
    )

    bundle = build_question_bank(course)
    generated = [
        item for item in bundle["items"]
        if item["assessment_role"] == "practice"
    ]

    assert generated
    assert all(
        item["question_spec"]["adapter_id"] == "fallback.teacher_review"
        for item in generated
    )
    assert all(item["review_required"] for item in generated)
    assert all(item["lifecycle_status"] == "needs_review" for item in generated)
    assert all("adapter_unavailable" in item["risk_flags"] for item in generated)
    assert bundle["coverage"]["coverage_ratio"] == 0
    assert bundle["coverage"]["status"] == "blocked"


def test_quality_gate_recomputes_domain_compatibility_instead_of_trusting_flags():
    course = _course_for(
        mode="programming_engineering",
        topic="图的广度优先与深度优先遍历",
        objective="执行BFS和DFS并比较访问顺序",
        key_points=["BFS", "DFS"],
        assessment="输出两种遍历顺序",
    )
    item = deepcopy(_practice_items(course)[0])
    item["question_spec"]["stimulus"] = {
        "kind": "record_batch",
        "data": {"records": [2, 4, 4, None]},
    }
    item["domain_validation"] = {"passed": True, "issues": []}

    report = evaluate_question_item_quality(item)

    assert report["passed"] is False
    assert report["checks"]["domain_validation"] is False
    assert any(
        issue["code"] == "question:input_task_incompatible"
        and issue["severity"] == "critical"
        for issue in report["issues"]
    )
