"""F-1c：内容正确性与视觉正确性必须是两份能独立读懂的报告。

这些测试盯住一件事——两份报告各自成立，不需要读者去翻另一份才能理解结论。
以及 F-1b/B：真实渲染器的判决必须能阻断发布，因为后端文本层在 8 门真实课程
上实测漏掉 72% 真正渲染失败的节点。
"""

from course_quality import (
    build_content_quality_report,
    build_final_course_quality_report,
    build_visual_quality_report,
)


def _course() -> dict:
    # Long enough to clear `content_too_short`, and carrying a difficulty
    # contract, so the content report is clean for the right reason — the point
    # of these tests is that the two verdicts can differ, which only means
    # something if the content side is genuinely passing.
    body = (
        "## 概念\n\n"
        "因为向量组线性无关，所以齐次方程组只有零解。这一依据来自秩与自由变量的关系，"
        "推导过程说明了为什么主元列的数量决定了解空间的维度。\n\n"
        "## 独立任务\n\n"
        "请独立完成下面的判定任务：给定一个新的矩阵，自行选择方法判断其列向量是否线性无关，"
        "并在不同输入规模下比较方法的适用边界与局限性。\n\n"
        "## 检查与反馈\n\n"
        "检查答案是否与参考结论一致，验证秩的计算是否正确，注意常见的易错点。\n"
    )
    return {
        "course_id": "c-1",
        "nodes": [
            {
                "node_id": "L2-1",
                "node_name": "线性无关",
                "node_level": 2,
                "node_content": body,
                "module_plan": [],
                "key_points": [],
                "grounding_contract": {},
                "difficulty_contract": {
                    "target_level": "intermediate",
                    "challenge": {
                        "reasoning_depth": 3,
                        "transfer_distance": 3,
                        "task_complexity": 3,
                    },
                    "support": {"scaffold_intensity": 3},
                    "mastery": {"independence": 3},
                    "subject_task": "rank_judgement",
                    "required_evidence": [],
                },
            }
        ],
    }


def _gate(passed: bool) -> dict:
    return {
        "contract_version": "render_gate_v1",
        "renderer": "frontend/src/utils/markdown.ts (markdown-it + KaTeX + DOMPurify)",
        "checked_nodes": 1,
        "passed": passed,
        "nodes": [
            {
                "node_id": "L2-1",
                "node_name": "线性无关",
                "passed": passed,
                "leaked_source": not passed,
                "render_diagnostics": {
                    "math_failure_count": 0 if passed else 2,
                    "block_failure_count": 0,
                },
                "samples": [] if passed else [
                    {"kind": "math_fallback", "detail": "\\omega^0^2"}
                ],
            }
        ],
    }


def test_visual_report_states_its_own_subject_and_basis():
    """A reader must learn what was judged, and by what, from this dict alone."""
    report = build_visual_quality_report(_course(), _gate(True))

    assert report["dimension"] == "visual"
    assert report["question"]
    assert report["basis"] == "real_render"
    assert report["authoritative"] is True
    assert "markdown" in report["basis_note"]
    assert report["passed"] is True


def test_visual_report_without_a_real_render_admits_it_is_not_authoritative():
    """The weaker basis must be visible, not silently equivalent.

    A caller reading `passed: true` off the pattern tier alone is reading a
    verdict that misses 72% of real failures. The report has to say so.
    """
    report = build_visual_quality_report(_course(), None)

    assert report["basis"] == "backend_pattern_only"
    assert report["authoritative"] is False
    assert "72%" in report["basis_note"]


def test_visual_report_names_the_failing_nodes_and_what_the_learner_sees():
    report = build_visual_quality_report(_course(), _gate(False))

    assert report["passed"] is False
    assert report["failing_node_ids"] == ["L2-1"]
    failure = report["failures"][0]
    assert failure["node_name"] == "线性无关"
    assert failure["math_failure_count"] == 2
    assert failure["reading"]


def test_content_report_excludes_render_questions_entirely():
    """Whether a formula displays is the other report's job."""
    report = build_content_quality_report(_course())

    assert report["dimension"] == "content"
    assert report["question"]
    for issue in report["issues"]:
        assert not str(issue.get("code", "")).startswith("render_gate")
        assert issue.get("code") not in {
            "unwrapped_display_environment",
            "unclosed_math_fence",
            "math_render_failed",
        }


def test_a_visually_broken_course_can_still_be_content_clean():
    """The whole point of splitting: these two verdicts must be able to differ."""
    course = _course()
    visual = build_visual_quality_report(course, _gate(False))
    content = build_content_quality_report(course)

    assert visual["passed"] is False
    assert content["passed"] is True


def test_render_gate_failure_blocks_publication():
    """F-1b/B: the real renderer's verdict is a release blocker."""
    report = build_final_course_quality_report(
        _course(), job_id="job-1", render_gate=_gate(False)
    )

    assert report["publication_allowed"] is False
    assert any(
        issue["code"] == "render_gate:failed"
        for issue in report["blocking_issues"]
    )


def test_a_clean_render_gate_does_not_block():
    report = build_final_course_quality_report(
        _course(), job_id="job-1", render_gate=_gate(True)
    )

    assert not any(
        issue["code"] == "render_gate:failed"
        for issue in report["blocking_issues"]
    )


def test_final_report_carries_both_reports_separately():
    report = build_final_course_quality_report(
        _course(), job_id="job-1", render_gate=_gate(False)
    )

    assert report["visual_quality_report"]["dimension"] == "visual"
    assert report["content_quality_report"]["dimension"] == "content"


def test_omitting_the_render_gate_keeps_every_existing_caller_working():
    """The gate is optional: callers that never ran it must behave as before."""
    report = build_final_course_quality_report(_course(), job_id="job-1")

    assert report["visual_quality_report"]["authoritative"] is False
    assert not any(
        issue["code"] == "render_gate:failed"
        for issue in report["blocking_issues"]
    )
