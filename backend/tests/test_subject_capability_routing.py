from copy import deepcopy

from question_bank import build_question_bank
from question_generation import validate_question_spec


def _legacy_course(
    *,
    course_id: str,
    course_name: str,
    node_name: str,
    node_content: str,
) -> dict:
    return {
        "course_id": course_id,
        "course_name": course_name,
        "course_purpose": "systematic",
        "difficulty": "intermediate",
        "generation_request": {
            "course_purpose": "systematic",
            "web_question_enrichment": {"enabled": False},
        },
        "material_bindings": [],
        "evidence_catalog": [],
        "nodes": [{
            "node_id": "L2-1-1",
            "node_level": 2,
            "node_name": node_name,
            "node_content": node_content,
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


def test_legacy_calculus_routes_to_a_solvable_derivative_capability():
    course = _legacy_course(
        course_id="legacy-calculus",
        course_name="微积分：从极限到多元积分",
        node_name="2.2 导数的定义与计算",
        node_content=(
            "本节解释导数的极限定义、幂函数求导法则与切线斜率。"
            "正文还会回顾线性近似、方程和矩阵记号，但考查目标是导数。"
        ),
    )

    generated = _practice_items(course)

    assert len(generated) == 3
    assert all(
        item["question_spec"]["adapter_id"] == "math.calculus"
        and item["question_spec"]["capability_id"] == "calculus.derivative"
        and item["question_spec"]["stimulus"]["data"]["case_kind"]
        == "polynomial_derivative"
        and item["answer_spec"]["canonical_answer"]["derivative"]
        and item["domain_validation"]["passed"]
        and item["lifecycle_status"] == "approved"
        for item in generated
    )
    assert all(
        "矩阵" not in item["prompt"]
        and "骰子" not in item["prompt"]
        and "案例值" not in item["prompt"]
        for item in generated
    )


def test_legacy_thermodynamics_routes_to_first_law_energy_balance():
    course = _legacy_course(
        course_id="legacy-thermodynamics",
        course_name="工程热力学",
        node_name="2.1 热力学第一定律",
        node_content=(
            "研究封闭系统能量守恒，约定系统吸热Q为正、对外做功W为正，"
            "并用状态方程与积分描述准静态过程。"
        ),
    )

    generated = _practice_items(course)

    assert len(generated) == 3
    assert all(
        item["question_spec"]["subject_family"] == "natural_science"
        and item["question_spec"]["adapter_id"] == "physics.thermodynamics"
        and item["question_spec"]["capability_id"]
        == "thermodynamics.first_law"
        and item["question_spec"]["stimulus"]["data"]["case_kind"]
        == "closed_system_energy_balance"
        and {"heat_kj", "work_kj"} <= set(
            item["question_spec"]["stimulus"]["data"]
        )
        and "internal_energy_change_kj"
        in item["answer_spec"]["canonical_answer"]
        and item["domain_validation"]["passed"]
        and item["lifecycle_status"] == "approved"
        for item in generated
    )
    assert all(
        "对照组读数" not in item["prompt"]
        and "线性映射" not in item["prompt"]
        and "骰子" not in item["prompt"]
        for item in generated
    )


def test_java_inner_class_target_uses_java_code_instead_of_record_cleaning():
    course = _legacy_course(
        course_id="legacy-java",
        course_name="Java 面向对象程序设计",
        node_name="2.3 内部类与匿名类",
        node_content=(
            "理解成员内部类、局部内部类和匿名类的使用边界，"
            "能够解释变量捕获规则并编写可运行示例。"
        ),
    )

    generated = _practice_items(course)

    assert len(generated) == 3
    assert all(
        item["question_spec"]["adapter_id"]
        == "programming.java_object_model"
        and item["question_spec"]["capability_id"]
        == "java.inner_and_anonymous_class"
        and "new Runnable()" in (
            item["question_spec"]["stimulus"]["data"]["code"]
        )
        and "effectively final" in (
            item["question_spec"]["stimulus"]["data"]["rule"]
        )
        and item["domain_validation"]["passed"]
        and item["lifecycle_status"] == "approved"
        for item in generated
    )
    assert all(
        "case_id" not in item["prompt"]
        and "records" not in item["prompt"]
        for item in generated
    )


def test_unregistered_natural_science_topic_is_not_auto_approved_as_experiment():
    course = _legacy_course(
        course_id="legacy-physics-unregistered",
        course_name="现代物理专题",
        node_name="7.4 拓扑缺陷的分类",
        node_content="比较不同拓扑缺陷的定义、守恒量和适用边界。",
    )

    generated = _practice_items(course)

    assert generated
    assert all(
        item["question_spec"]["adapter_id"] == "fallback.teacher_review"
        and item["question_spec"]["capability_id"] == "unregistered"
        and item["lifecycle_status"] == "needs_review"
        for item in generated
    )
    assert all("对照组读数" not in item["prompt"] for item in generated)


def test_capability_identity_mismatch_fails_semantic_validation():
    course = _legacy_course(
        course_id="legacy-calculus-semantic-check",
        course_name="微积分",
        node_name="2.2 导数的定义与计算",
        node_content="使用导数定义和求导法则计算多项式导数。",
    )
    spec = deepcopy(_practice_items(course)[0]["question_spec"])
    spec["capability_id"] = "thermodynamics.first_law"

    validation = validate_question_spec(spec)

    assert validation["passed"] is False
    assert validation["checks"]["semantic_alignment"] is False
    assert any(
        issue["code"] == "question:capability_contract_mismatch"
        and issue["severity"] == "critical"
        for issue in validation["issues"]
    )
