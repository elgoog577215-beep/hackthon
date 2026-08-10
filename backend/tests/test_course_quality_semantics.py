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


def test_unwrapped_display_environment_blocks_release_even_with_even_fence_count():
    """An even `$$` count is not proof the math is well-formed.

    Here the `cases` environment sits entirely between two balanced pairs of
    `$$`, so the old parity check passed it through and the learner saw raw
    LaTeX source.
    """
    content = _content(
        "\n\n$$\nf(x)=\n$$\n"
        "\\begin{cases}x,&x<0\\\\2x,&x\\ge0\\end{cases}\n"
        "$$\ny=1\n$$"
    )

    assert content.count("$$") % 2 == 0
    report = evaluate_node_content(content, _node())

    assert any(
        item["code"] == "unwrapped_display_environment"
        for item in report["issues"]
    )
    assert report["passed"] is False


def test_display_environment_inside_delimiters_is_accepted():
    """The check must not punish correctly wrapped block math."""
    content = _content(
        "\n\n$$\n\\begin{cases}x,&x<0\\\\2x,&x\\ge0\\end{cases}\n$$"
    )

    report = evaluate_node_content(content, _node())

    assert not any(
        item["code"] == "unwrapped_display_environment"
        for item in report["issues"]
    )


def test_display_environment_in_a_code_fence_is_not_flagged():
    """A LaTeX sample shown as code is documentation, not broken math."""
    content = _content(
        "\n\n```latex\n\\begin{cases}x,&x<0\\end{cases}\n```"
    )

    report = evaluate_node_content(content, _node())

    assert not any(
        item["code"] == "unwrapped_display_environment"
        for item in report["issues"]
    )


def test_reported_math_render_failure_blocks_release():
    """L3a: a KaTeX failure reported by the renderer must reach the gate.

    The backend is pure string matching, so without this channel a formula that
    KaTeX refuses to render looks identical to a valid one — the frontend
    degrades to readable source and nothing upstream learns.
    """
    report = evaluate_node_content(
        _content(),
        _node(),
        render_diagnostics={"math_failure_count": 2},
    )

    codes = [item["code"] for item in report["issues"]]
    assert "math_render_failed" in codes
    assert report["passed"] is False


def test_reported_block_render_failure_blocks_release():
    report = evaluate_node_content(
        _content(),
        _node(),
        render_diagnostics={"block_failure_count": 1},
    )

    assert "block_render_failed" in [item["code"] for item in report["issues"]]
    assert report["passed"] is False


def test_clean_render_report_does_not_add_issues():
    report = evaluate_node_content(
        _content(),
        _node(),
        render_diagnostics={"math_failure_count": 0, "block_failure_count": 0},
    )

    assert not any(
        item["code"].endswith("_render_failed") for item in report["issues"]
    )


def test_missing_or_malformed_diagnostics_keep_legacy_behaviour():
    """Every existing caller passes nothing; that must stay a no-op."""
    baseline = evaluate_node_content(_content(), _node())

    for diagnostics in (None, {}, {"math_failure_count": "oops"}, "not-a-dict"):
        report = evaluate_node_content(_content(), _node(), render_diagnostics=diagnostics)
        assert [i["code"] for i in report["issues"]] == [
            i["code"] for i in baseline["issues"]
        ]


def _codes(content: str) -> list[str]:
    return [item["code"] for item in evaluate_node_content(content, _node())["issues"]]


def test_table_without_delimiter_row_is_flagged():
    """L3d: a table with no |---| renders as literal pipes."""
    codes = _codes(_content("\n\n| 结构 | 复杂度 |\n| 数组 | O(n) |"))
    assert "table_missing_delimiter" in codes


def test_well_formed_table_is_accepted():
    codes = _codes(
        _content("\n\n| 结构 | 复杂度 |\n| --- | --- |\n| 数组 | O(n) |")
    )
    assert "table_missing_delimiter" not in codes
    assert "table_delimiter_mismatch" not in codes


def test_table_delimiter_column_mismatch_is_flagged():
    codes = _codes(
        _content("\n\n| 结构 | 复杂度 | 备注 |\n| --- | --- |\n| 数组 | O(n) | 连续 |")
    )
    assert "table_delimiter_mismatch" in codes


def test_table_inside_a_code_fence_is_not_flagged():
    """A Markdown sample shown as code is content, not structure."""
    codes = _codes(
        _content("\n\n```markdown\n| 结构 | 复杂度 |\n| 数组 | O(n) |\n```")
    )
    assert "table_missing_delimiter" not in codes


def test_empty_blockquote_is_flagged():
    codes = _codes(_content("\n\n>\n>"))
    assert "empty_blockquote" in codes


def test_blockquote_with_content_is_accepted():
    codes = _codes(_content("\n\n> 注意：退化后查找复杂度变为线性。"))
    assert "empty_blockquote" not in codes


def test_ordered_list_restarting_midway_is_flagged():
    codes = _codes(_content("\n\n1. 第一步\n2. 第二步\n1. 又从头开始\n2. 继续"))
    assert "list_numbering_restart" in codes


def test_continuous_ordered_list_is_accepted():
    codes = _codes(_content("\n\n1. 第一步\n2. 第二步\n3. 第三步"))
    assert "list_numbering_restart" not in codes


def test_two_lists_separated_by_prose_are_not_flagged():
    """A genuine second list after prose legitimately restarts at 1."""
    codes = _codes(
        _content("\n\n1. 第一步\n2. 第二步\n\n中间说明文字。\n\n1. 另一组\n2. 继续")
    )
    assert "list_numbering_restart" not in codes
