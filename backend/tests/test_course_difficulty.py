import pytest

from course_difficulty import (
    SUBJECT_ADAPTERS,
    assess_readiness,
    attach_difficulty_contracts_to_plan,
    compile_course_difficulty_curve,
    compile_difficulty_profile,
    decide_adaptation,
    ensure_course_difficulty_contracts,
)
from course_pedagogy import PedagogyMode
from course_quality import (
    evaluate_difficulty_alignment,
    validate_difficulty_blueprint,
)


def _average(values):
    numeric = [value for value in values.values() if isinstance(value, (int, float))]
    return sum(numeric) / len(numeric)


@pytest.mark.parametrize("mode", list(PedagogyMode))
def test_all_subject_modes_compile_three_monotonic_difficulty_contracts(mode):
    profiles = [
        compile_difficulty_profile(level, primary_mode=mode)
        for level in ("beginner", "intermediate", "advanced")
    ]

    challenge = [_average(profile.to_dict()["challenge_profile"]) for profile in profiles]
    support = [_average({
        key: value
        for key, value in profile.to_dict()["support_profile"].items()
        if isinstance(value, (int, float))
    }) for profile in profiles]
    independence = [profile.mastery_contract.independence for profile in profiles]

    assert challenge[0] < challenge[1] < challenge[2]
    assert support[0] > support[1] > support[2]
    assert independence[0] < independence[1] < independence[2]
    assert all(profile.subject_adapter["primary_mode"] == mode.value for profile in profiles)
    assert len({profile.subject_adapter["performance_task"] for profile in profiles}) == 3


def test_subject_adapters_cover_exactly_the_eight_pedagogy_modes():
    assert set(SUBJECT_ADAPTERS) == {mode.value for mode in PedagogyMode}


def test_unknown_readiness_preserves_target_and_requires_diagnostic():
    profile = compile_difficulty_profile("advanced", primary_mode="math_formal")
    assessment = assess_readiness(profile)
    decision = decide_adaptation(assessment)

    assert assessment.readiness_status == "unknown"
    assert assessment.gap is None
    assert decision.strategy == "diagnostic_required"
    assert decision.preserve_target is True


def test_explicit_readiness_gap_adds_bridge_without_downgrading():
    profile = compile_difficulty_profile("advanced", primary_mode="programming_engineering")
    assessment = assess_readiness(profile, "beginner")
    decision = decide_adaptation(assessment)

    assert assessment.gap == 1
    assert decision.strategy == "inline_bridge"
    assert decision.preserve_target is True


def test_curve_is_sawtooth_and_ends_in_integrated_performance():
    profile = compile_difficulty_profile("intermediate", primary_mode="natural_science")
    adaptation = decide_adaptation(assess_readiness(profile))
    nodes = [
        {"node_id": f"L2-1-{index}", "section_number": f"1.{index}"}
        for index in range(1, 13)
    ]
    curve = compile_course_difficulty_curve(
        profile=profile,
        nodes=nodes,
        adaptation=adaptation,
    ).to_dict()
    roles = [item["node_role"] for item in curve["node_contracts"]]

    assert curve["shape"] == "sawtooth"
    assert roles[0] == "checkpoint"
    assert roles[-3:] == ["integration", "transfer", "capstone"]
    assert roles.count("foundation") >= 1
    assert all(item["subject_task"] for item in curve["node_contracts"])

    blueprint = {
        "difficulty_profile": profile.to_dict(),
        "course_difficulty_curve": curve,
        "nodes": [
            {**node, "difficulty_contract": {
                key: value
                for key, value in contract.items()
                if key not in {"node_id", "section_number"}
            }}
            for node, contract in zip(nodes, curve["node_contracts"])
        ],
    }
    assert validate_difficulty_blueprint(blueprint)["passed"] is True


def test_plan_compiler_removes_free_complexity_and_attaches_contracts():
    profile = compile_difficulty_profile("beginner", primary_mode="general")
    plan = {
        "chapters": [{
            "chapter_number": 1,
            "sections": [{
                "node_id": "L2-1-1",
                "section_number": "1.1",
                "complexity": "complex",
            }],
        }],
    }

    attach_difficulty_contracts_to_plan(
        plan,
        profile=profile,
        adaptation=decide_adaptation(assess_readiness(profile)),
    )
    section = plan["chapters"][0]["sections"][0]

    assert "complexity" not in section
    assert section["difficulty_contract"]["target_level"] == "beginner"
    assert plan["course_difficulty_curve"]["node_contracts"]


def test_old_course_adapter_ignores_legacy_complexity_and_recovers_contracts():
    course = {
        "difficulty": "advanced",
        "generation_request": {"difficulty": "advanced"},
        "nodes": [{
            "node_id": "L2-1-1",
            "node_name": "1.1 旧节点",
            "node_level": 2,
            "complexity": "simple",
        }],
        "course_blueprint": {
            "nodes": [{
                "node_id": "L2-1-1",
                "section_number": "1.1",
                "complexity": "simple",
            }],
        },
    }

    ensure_course_difficulty_contracts(course, primary_mode="humanities_social")

    node = course["nodes"][0]
    assert "complexity" not in node
    assert node["difficulty_contract"]["target_level"] == "advanced"
    assert course["difficulty_profile"]["subject_adapter"]["primary_mode"] == "humanities_social"
    assert course["course_blueprint"]["difficulty_profile"]


def test_advanced_long_text_without_reasoning_or_transfer_is_pseudo_difficulty():
    profile = compile_difficulty_profile("advanced", primary_mode="general")
    curve = compile_course_difficulty_curve(
        profile=profile,
        nodes=[{"node_id": "L2-1-1", "section_number": "1.1"}],
        adaptation=decide_adaptation(assess_readiness(profile)),
    ).to_dict()
    contract = {
        key: value
        for key, value in curve["node_contracts"][0].items()
        if key not in {"node_id", "section_number"}
    }
    node = {"node_id": "L2-1-1", "difficulty_contract": contract}
    content = "## 概念\n\n" + "这是一段术语密集但没有学习任务的说明。" * 45

    report = evaluate_difficulty_alignment(content, node)

    assert report["passed"] is False
    assert report["pseudo_difficulty_risk"] is True
    assert any(item["code"] == "difficulty:pseudo_difficulty" for item in report["issues"])


def test_advanced_math_content_can_satisfy_reasoning_independence_and_transfer():
    profile = compile_difficulty_profile("advanced", primary_mode="math_formal")
    curve = compile_course_difficulty_curve(
        profile=profile,
        nodes=[{"node_id": "L2-1-1", "section_number": "1.1"}],
        adaptation=decide_adaptation(assess_readiness(profile)),
    ).to_dict()
    contract = {
        key: value
        for key, value in curve["node_contracts"][0].items()
        if key not in {"node_id", "section_number"}
    }
    node = {"node_id": "L2-1-1", "difficulty_contract": contract}
    content = """## 定义与条件

先写出定义与假设，再根据条件完成推导。因为每一步都依赖前一个结论，所以需要逐步检查逻辑。

## 独立证明

请独立选择定理完成证明，然后构造反例说明该条件的边界。不要照抄示例，要说明选择依据。

## 迁移与建模

改变条件后，将同一推理迁移到新情境，比较两种建模方案并论证取舍。最后用检查清单验证证明、反例和边界是否一致。
"""

    report = evaluate_difficulty_alignment(content, node)

    assert report["passed"] is True
    assert report["pseudo_difficulty_risk"] is False
