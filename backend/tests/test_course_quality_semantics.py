from course_quality import evaluate_node_content


def test_learner_visible_generator_language_is_a_repairable_failure():
    node = {
        "node_id": "L2-1-1",
        "node_name": "变量关系",
        "key_points": ["变量关系"],
        "module_plan": [],
        "difficulty_contract": {},
        "grounding_contract": {},
    }
    content = (
        "## 核心教学\n\n变量关系描述两个量怎样共同变化。" * 12
        + "\n\n## 学习者行动\n\n请完成一个判断任务。"
        + "\n\n## 检查与反馈\n\n作答质量标准：写出判断依据。"
    )

    report = evaluate_node_content(content, node)

    assert report["passed"] is False
    assert {item["code"] for item in report["issues"]} >= {
        "learner_visible_generator_language",
    }
from task_manager import fix_latex_content, normalize_generated_course_syntax


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


def test_legacy_single_dollar_display_delimiter_blocks_release():
    report = evaluate_node_content(
        _content("\n\n$\n\\begin{bmatrix}a \\\\ b\\end{bmatrix}\n$"),
        _node(),
    )

    assert any(item["code"] == "legacy_math_delimiter" for item in report["issues"])
    assert report["passed"] is False


def test_stream_finalizer_normalizes_legacy_display_math_delimiters():
    cleaned = fix_latex_content(_content("\n\n$\nx^2 + y^2\n$"))
    report = evaluate_node_content(cleaned, _node())

    assert "\n\n$$\nx^2 + y^2\n$$" in cleaned
    assert not any(
        item["code"] == "legacy_math_delimiter"
        for item in report["issues"]
    )


def test_stream_finalizer_is_idempotent_for_wrapped_aligned_environment():
    content = _content(
        "\n\n$$\n\\begin{aligned}\n"
        "x&=1 \\\\ y&=2\n"
        "\\end{aligned}\n$$"
    )

    cleaned = fix_latex_content(content)

    assert cleaned == fix_latex_content(cleaned)
    assert "$$\n$$" not in cleaned
    assert cleaned.count("$$") % 2 == 0


def test_stream_finalizer_merges_list_display_with_cases_environment():
    content = _content(
        "\n\n1. $$\n"
        "   \\lim_{x\\to0}\n"
        "$$\n\\begin{cases}x,&x<0\\\\2x,&x\\ge0\\end{cases}\n$$"
    )

    cleaned = fix_latex_content(content)

    assert "1. $$" not in cleaned
    assert cleaned.count("$$") % 2 == 0
    assert "\\lim_{x\\to0}\n\\begin{cases}" in cleaned


def test_stream_finalizer_merges_display_prefix_with_cases_environment():
    content = _content(
        "\n\n$$\nf(x)=\n$$\n"
        "\\begin{cases}\n"
        "x,&x<0\\\\\n2x,&x\\ge0\n"
        "\\end{cases}\n$$"
    )

    cleaned = fix_latex_content(content)

    assert "$$\nf(x)=\n\\begin{cases}" in cleaned
    assert "\\end{cases}\n$$" in cleaned
    assert cleaned == fix_latex_content(cleaned)
    assert evaluate_node_content(cleaned, _node())["passed"] is True


def test_stream_finalizer_preserves_prose_between_separate_display_formulas():
    content = _content(
        "\n\n$$\nx=1\n$$\n"
        "在闭区间上比较端点与临界点。\n"
        "$$\n\\begin{aligned}\n"
        "f(0)&=0\\\\\nf(1)&=1\n"
        "\\end{aligned}\n$$"
    )

    cleaned = fix_latex_content(content)

    assert (
        "$$\nx=1\n$$\n在闭区间上比较端点与临界点。\n"
        "$$\n\\begin{aligned}"
    ) in cleaned
    assert cleaned == fix_latex_content(cleaned)
    assert evaluate_node_content(cleaned, _node())["passed"] is True


def test_unwrapped_display_environment_blocks_release_even_with_even_fence_count():
    content = _content(
        "\n\n$$\nf(x)=\n$$\n"
        "\\begin{cases}x,&x<0\\\\2x,&x\\ge0\\end{cases}\n"
        "$$\ny=1\n$$"
    )

    report = evaluate_node_content(content, _node())

    assert any(
        item["code"] == "unwrapped_display_environment"
        for item in report["issues"]
    )
    assert report["passed"] is False


def test_course_syntax_normalizer_rebuilds_stale_content_blocks():
    course = {
        "nodes": [{
            **_node(),
            "node_level": 2,
            "node_content": (
                _content("\n\n$$\n$$\n\\begin{cases}"
                         "x,&x<0\\\\2x,&x\\ge0"
                         "\\end{cases}\n$$\n$$")
            ),
            "content_blocks": [{
                "block_id": "stale",
                "type": "custom",
                "title": "旧内容",
                "content": "旧内容",
                "order": 0,
            }],
        }],
    }

    normalized = normalize_generated_course_syntax(course)
    content = course["nodes"][0]["node_content"]

    assert normalized == ["L2-1-1"]
    assert "$$\n$$" not in content
    assert "旧内容" not in content
    assert course["nodes"][0]["generation_quality"]["passed"] is True


def test_unclosed_display_math_fence_blocks_release():
    report = evaluate_node_content(_content("\n\n$$\nx^2 + y^2"), _node())

    assert any(item["code"] == "unclosed_math_fence" for item in report["issues"])
    assert report["passed"] is False


def test_stream_finalizer_closes_display_math_before_node_completion():
    cleaned = fix_latex_content(_content("\n\n$$\nx^2 + y^2"))
    report = evaluate_node_content(cleaned, _node())

    assert cleaned.rstrip().endswith("$$")
    assert not any(
        item["code"] == "unclosed_math_fence"
        for item in report["issues"]
    )


def test_stream_finalizer_does_not_count_dollars_inside_code_fence():
    content = _content("\n\n```python\nprice = '$$'\n```\n")

    assert fix_latex_content(content).rstrip().endswith("```")


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
