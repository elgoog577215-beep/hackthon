from __future__ import annotations

from assessment_diversity import (
    build_diversity_signature,
    compare_diversity_signatures,
    compile_diversity_plan,
    evaluate_question_diversity,
    historical_questions_for_node,
)


def _question(
    material: str,
    task: str,
    *,
    family: str = "general",
    question_type: str = "structured_application",
) -> dict:
    return {
        "question_type": question_type,
        "assessment_slot": {
            "discipline_family": family,
        },
        "question_spec": {
            "stimulus": {"rendered_text": material},
            "task": {"rendered_text": task},
        },
        "prompt": f"{material}\n{task}",
        "solution_envelope": {
            "canonical_answer": "否",
            "solution_graph": {
                "steps": [{
                    "action": "检查单位元公理",
                    "check": "1·v 不等于 v",
                }],
            },
        },
    }


def test_math_same_instance_across_question_types_is_rejected():
    choice = _question(
        (
            "集合 V={(x,y)|x,y∈R}，加法为 "
            "(x1,y1)+(x2,y2)=(x1+x2,y1+y2)，"
            "数乘为 k·(x,y)=(kx,0)。"
        ),
        "请选择该结构是否构成向量空间。",
        family="math_formal",
        question_type="selected_response",
    )
    structured = _question(
        (
            "设 V={(x,y)|x,y∈R}，定义 "
            "(x1,y1)+(x2,y2)=(x1+x2,y1+y2)，"
            "k·(x,y)=(kx,0)。"
        ),
        "判断是否为向量空间，并指出违反的公理。",
        family="math_formal",
    )

    report = evaluate_question_diversity(
        structured,
        existing_questions=[choice],
        discipline_family="math_formal",
    )

    assert report["passed"] is False
    assert "shared_subject_anchors" in report["reasons"]


def test_same_vector_set_and_plane_is_rejected_despite_longer_task():
    first = _question(
        (
            "在 R^3 中给定 S={(1,0,0),(0,1,0),(1,1,0)}，"
            "span(S) 是 xy 平面。"
        ),
        "判断 S 是否为最小生成集。",
        family="math_formal",
    )
    second = _question(
        (
            "考虑三维空间中的集合 "
            "S={(1,0,0),(0,1,0),(1,1,0)}。"
            "它生成 xy 平面且包含冗余向量。"
        ),
        "移除冗余向量，并证明剩余集合仍生成同一平面。",
        family="math_formal",
    )

    comparison = compare_diversity_signatures(
        build_diversity_signature(first),
        build_diversity_signature(second),
    )

    assert comparison["duplicate"] is True
    assert (
        comparison["signals"]["shared_subject_anchor_count"]
        >= 3
    )


def test_same_objective_with_new_instance_and_action_is_allowed():
    classification = _question(
        "集合 V={(x,y)∈R²|x≥0} 使用标准加法与数乘。",
        "判断 V 是否为向量空间。",
        family="math_formal",
    )
    design = _question(
        "在 R² 上定义 u⊕v=u+v-(1,1)。",
        "设计一个与该加法匹配的零元，并验证逆元性质。",
        family="math_formal",
    )

    comparison = compare_diversity_signatures(
        build_diversity_signature(classification),
        build_diversity_signature(design),
    )

    assert comparison["duplicate"] is False


def test_plugins_extract_programming_and_humanities_anchors():
    programming = _question(
        "```python\ndef parse(value):\n    return int(value)\n```",
        "定位 ValueError 的触发条件并修复。",
        family="programming_engineering",
    )
    humanities = _question(
        "材料一：“政策需要兼顾效率与公平。”材料二给出 1948 年数据。",
        "比较两份材料的立场与证据。",
        family="humanities_social",
    )

    programming_signature = build_diversity_signature(programming)
    humanities_signature = build_diversity_signature(humanities)

    assert programming_signature["plugin_id"] == "programming_v1"
    assert any(
        anchor.startswith("code:")
        for anchor in programming_signature["anchors"]
    )
    assert humanities_signature["plugin_id"] == "humanities_v1"
    assert any(
        anchor.startswith(("date:", "quote:", "source:"))
        for anchor in humanities_signature["anchors"]
    )


def test_diversity_plan_has_distinct_cognitive_progression():
    plans = [
        compile_diversity_plan(
            discipline_family="general",
            practice_level=level,
            variant_index=index,
            objective={
                "objective": "解释并应用核心概念",
                "misconceptions": ["只记定义", "忽略边界"],
            },
        )
        for index, level in enumerate([
            "concept_check",
            "objective_practice",
            "mastery_check",
        ])
    ]

    assert len({
        plan["cognitive_action"]
        for plan in plans
    }) == 3
    assert len({
        plan["reasoning_route"]
        for plan in plans
    }) == 3
    assert all(plan["hard_rules"] for plan in plans)


def test_historical_questions_are_scoped_and_deduplicated_by_revision():
    course = {
        "learning_assets": {
            "questions": [
                {
                    "node_id": "node-1",
                    "revision_id": "rev-1",
                    "prompt": "historical question one",
                },
                {
                    "node_id": "node-2",
                    "revision_id": "rev-2",
                    "prompt": "other objective",
                },
            ],
        },
        "question_bank": {
            "items": [
                {
                    "node_id": "node-1",
                    "revision_id": "rev-1",
                    "prompt": "same frozen revision",
                },
                {
                    "node_id": "node-1",
                    "revision_id": "rev-3",
                    "prompt": "historical question two",
                },
            ],
        },
    }

    history = historical_questions_for_node(
        course,
        node_id="node-1",
    )

    assert [item["revision_id"] for item in history] == [
        "rev-1",
        "rev-3",
    ]


def test_subject_plugin_threshold_can_override_global(monkeypatch):
    question = _question(
        "Given vectors u=(1,2) and v=(3,4).",
        "Compute their dot product.",
        family="math_formal",
    )
    signature = build_diversity_signature(question)
    monkeypatch.setenv(
        "ASSESSMENT_DIVERSITY_THRESHOLD_STEM",
        "0.81",
    )

    comparison = compare_diversity_signatures(
        signature,
        signature,
    )

    assert comparison["threshold"] == 0.81
