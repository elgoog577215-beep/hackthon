from course_quality import evaluate_node_content
from task_manager import fix_latex_content


def _node() -> dict:
    return {
        "node_id": "L2-1-1",
        "node_name": "二叉搜索树",
        "key_points": ["二叉搜索树的退化条件与平衡树选择"],
        "module_plan": [],
        "difficulty_contract": {
            "target_level": "advanced",
            "challenge": {
                "reasoning_depth": 4,
                "transfer_distance": 4,
                "task_complexity": 4,
            },
            "support": {"scaffold_intensity": 3},
            "mastery": {"independence": 4},
            "subject_task": "tradeoff_analysis",
            "required_evidence": ["退化", "树高"],
        },
        "grounding_contract": {},
    }


def _content(extra: str = "") -> str:
    return (
        "## 二叉搜索树的退化条件\n\n"
        "因为有序输入会让树高退化，所以查找会从对数复杂度变为线性复杂度。"
        "在应用场景与取舍判断中，需要根据不同输入、现实约束和局限性选择平衡树。\n\n"
        "## 独立任务\n\n请独立分析一个流式数据案例，写出退化反例并选择数据结构。\n\n"
        "## 检查与反馈\n\n检查是否说明依据、树高变化、边界和结果验证。"
        + extra
    )


def test_transfer_quality_recognizes_real_application_boundaries_and_tradeoffs():
    report = evaluate_node_content(_content(), _node())

    assert report["difficulty_alignment"]["passed"] is True
    assert not any(item["code"] == "difficulty:missing_transfer" for item in report["issues"])
    assert report["passed"] is True


def test_model_self_correction_residue_forces_targeted_repair():
    report = evaluate_node_content(
        _content("\n\n我的计算有误，请重新检查任务。"),
        _node(),
    )

    assert any(item["code"] == "model_self_correction" for item in report["issues"])
    assert report["passed"] is False


def test_inline_revision_marker_forces_targeted_repair():
    report = evaluate_node_content(
        _content("\n\n展开得到 $-2x^2+280x-8000$（更正：最终结果不变）。"),
        _node(),
    )

    assert any(item["code"] == "model_self_correction" for item in report["issues"])
    assert report["passed"] is False


def test_subject_matter_revision_term_is_not_model_self_correction():
    report = evaluate_node_content(
        _content("\n\n直觉必须被定义域修正：实际长度必须大于 0。"),
        _node(),
    )

    assert not any(item["code"] == "model_self_correction" for item in report["issues"])
    assert report["passed"] is True


def test_formula_joined_to_list_forces_markdown_repair():
    report = evaluate_node_content(
        _content("\n\n定义为 $y=ax^2+bx+c$1.  **第一步**：识别系数。"),
        _node(),
    )

    assert any(item["code"] == "markdown_block_join" for item in report["issues"])
    assert report["passed"] is False


def test_latex_cleanup_preserves_markdown_boundaries_after_closing_delimiter():
    content = "定义为 $ y=ax^2+bx+c $\n\n1. 识别系数\n\n$ x=1 $\n\n* 检查结果"

    cleaned = fix_latex_content(content)

    assert "$y=ax^2+bx+c$\n\n1. 识别系数" in cleaned
    assert "$x=1$\n\n* 检查结果" in cleaned


def test_duplicate_node_heading_is_rejected_before_it_becomes_an_empty_intro_block():
    report = evaluate_node_content(
        "## 二叉搜索树\n\n## 本节任务\n\n请分析树高。\n\n## 检查与反馈\n\n检查退化条件。",
        _node(),
    )

    assert any(item["code"] == "duplicate_section_heading" for item in report["issues"])
    assert report["passed"] is False


def test_required_module_labels_must_be_stable_level_two_headings():
    node = _node()
    node["module_plan"] = [{
        "module_id": "lesson_goal",
        "label": "本节任务",
        "required": True,
        "output_contract": "给出可验证目标",
    }]
    report = evaluate_node_content(_content(), node)

    assert any(item["code"] == "missing_module_headings" for item in report["issues"])
    assert report["passed"] is False


def test_long_multi_task_feedback_requires_task_level_headings():
    flat_feedback = "\n".join([
        "**任务1 答案方向**：" + "写出判断依据和结果。" * 20,
        "**任务2 答案方向**：" + "比较边界条件和不确定性。" * 20,
        "**任务3 评价标准**：" + "说明验证方法和下一步行动。" * 20,
    ])
    report = evaluate_node_content(
        _content().replace("检查是否说明依据、树高变化、边界和结果验证。", flat_feedback),
        _node(),
    )

    assert any(item["code"] == "feedback_structure_flat" for item in report["issues"])
    assert report["passed"] is False


def test_feedback_rejects_math_notation_disguised_as_inline_code():
    feedback = (
        "### 任务 1：复杂度判断\n\n"
        "`log_2(4)`、`N^2`、`Θ(N^2)`、`f(N)=N^3`、`N/log N` 都需要核对。"
    )
    report = evaluate_node_content(
        _content().replace("检查是否说明依据、树高变化、边界和结果验证。", feedback),
        _node(),
    )

    assert any(item["code"] == "feedback_math_as_code" for item in report["issues"])
    assert report["passed"] is False


def test_structured_feedback_with_latex_passes_presentation_checks():
    feedback = (
        "### 任务 1：复杂度判断\n\n"
        "**核对标准**：比较 $N^2$ 与 $f(N)$。\n\n"
        "**参考结论**：得到 $\\Theta(N^2 \\log N)$。\n\n"
        "### 任务 2：实验验证\n\n"
        "**核对标准**：说明比值、噪声和下一步行动。"
    )
    report = evaluate_node_content(
        _content().replace("检查是否说明依据、树高变化、边界和结果验证。", feedback),
        _node(),
    )

    assert not any(item["code"].startswith("feedback_") for item in report["issues"])
