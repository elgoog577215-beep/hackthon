import inspect
import re

import pytest

from course_document import (
    CourseBlock,
    CourseDocument,
    CourseSection,
    refresh_document_revision,
    stable_hash,
)
from course_presentation_graph import (
    block_artifact_kinds,
    block_presentation_text,
    block_source_text,
    compile_course_presentation_graph,
    teaching_intent_for_roles,
)
from slide_deck_v6 import (
    SlideNarrativeBriefV1,
    SlideStoryBatchV3,
    SlideStoryPageV3,
    SlideStoryPlanV3,
    SlideVisualDecisionV2,
    SlideVisualPlanV2,
    V6BuildError,
    _audience_ready_title_fragment,
    _artifact_free_prose_text,
    _bounded_slot_content,
    _bounded_source_title_windows,
    _compile_course_agenda_pages,
    _complete_sentence_excerpt,
    _continuation_title_candidates,
    _display_excerpt,
    _ellipsis_maps_to_frozen_source,
    _formula_visual_line_count,
    _formula_candidates,
    _formula_canvas_text,
    _formula_like_title,
    _ppt_manuscript_quality_issues,
    _protected_tokens,
    _split_artifact_block,
    _title_is_incomplete,
    _title_is_generic_or_stub,
    affected_ppt_manuscript_page_ids,
    build_signature_v6,
    classify_v6_failure,
    compile_ppt_manuscript_v1,
    compile_ppt_source_contract_v2,
    compile_shadow_chapter_document,
    compile_slide_deck_v6,
    compile_slide_deck_v6_from_manuscript,
    prepare_story_plan_for_final_compilation,
    rebase_ppt_manuscript_source_blocks_v1,
    revise_ppt_manuscript_v1,
    story_page_count_range,
    story_safe_page_slices,
    validate_slide_story_plan_v3,
    validate_slide_visual_plan_v2,
    validate_deck_matches_ppt_manuscript_v1,
)
from slide_ai_planning_v6 import regenerate_ppt_manuscript_pages_v1
from slide_deck_renderer import audit_exported_pptx
from slide_deck_v6_renderer import adapt_v6_page_to_slide_spec, export_slide_deck_v6_pptx
from slide_layout_geometry import capacity_profile_text_fits
from template_layout_contract import compile_builtin_template_layout_contract_v1


@pytest.mark.parametrize(
    ("stage", "code", "root_cause"),
    [
        ("story", "story_duplicate_page_id", "page_identity"),
        ("visual", "visual_page_coverage_incomplete", "visual_page_mapping"),
        ("visual", "visual_page_duplicate", "visual_page_mapping"),
        ("visual", "visual_page_duplicate_conflict", "visual_page_mapping"),
        ("visual", "visual_page_unknown", "visual_page_mapping"),
        ("template", "template_slot_capacity_exceeded", "pagination_capacity"),
        ("quality", "continuation_title_unavailable", "source_slot_binding"),
        ("quality", "duplicate_final_page_title", "source_fidelity"),
        ("story", "story_unsupported_teaching_content", "source_fidelity"),
        (
            "manuscript",
            "ppt_manuscript_teaching_content_untraceable",
            "source_fidelity",
        ),
        ("recovery", "v6_recovery_contract_mismatch", "checkpoint_contract"),
    ],
)
def test_v6_failure_codes_have_stable_stage_and_root_cause_mapping(
    stage: str,
    code: str,
    root_cause: str,
) -> None:
    contract = classify_v6_failure(stage, code)

    assert contract["owner_stage"] == stage
    assert contract["root_cause"] == root_cause
    assert contract["stage_contract"]


def test_sentence_excerpt_never_exceeds_its_template_budget():
    source = "A source sentence with no early punctuation and several additional words"

    excerpt = _complete_sentence_excerpt(source, 35)

    assert len(excerpt) <= 35
    assert excerpt.endswith("…")
    assert excerpt[:-1] in source


def test_continuation_title_projection_removes_production_language() -> None:
    assert _audience_ready_title_fragment("提供一组难度递进的题目") == "难度递进练习"
    assert _audience_ready_title_fragment("用几何直观建立行列式") == "行列式的几何直观"
    assert _audience_ready_title_fragment("选取一个二阶可逆矩阵") == "二阶可逆矩阵示例"


def test_continuation_title_candidates_exclude_internal_structure_labels() -> None:
    block = _block(
        "vector-task",
        "lesson-1",
        0,
        role="activity",
        text=(
            "任务条件：已知两个同维向量，逐分量完成加法。"
            "维数不同的向量不能相加。"
        ),
    )

    candidates = _continuation_title_candidates([block], capacity=36)

    assert "任务条件" not in candidates
    assert "维数不同的向量不能相加" in candidates


@pytest.mark.parametrize(
    "title",
    [
        "已知三维向量 mathbf u=(2",
        "与 (-1",
        "将增广矩阵",
        "表示‘把第二行的 -frac32 倍加到第三行’",
        "因此 Ax=b 等价于对每个 i=1,2,3 都有",
        "虽然包含相同的三个数",
        "以核验行序、列序、零系数、负号和常数",
        "b 均为 3×1",
        "列序一旦确定",
        "其中主元 a=2，倍加系数由 b+ca=0 得",
        "却表示不同的向量",
        "且 Ax=b",
        "未知数列序改为 z",
        "其中 A 为 3×3",
        "必须是第 i 个方程中第 j",
        "因此 Ax=b 等价于对每个 i=1,2,3",
        "1，零元素较多也不能单独证明矩阵已成行阶梯形",
        "必须是第 i 个方程中第",
        "(ine j).",
        "独立写成",
        "右端常数均",
        "只有每一行的系数、未知数列序、负号",
        "当前列若主元位置为零而下方有非零元",
        "一个 n",
        "设主元为 ane0",
        "原函数定义域为 mathbb R",
    ],
)
def test_title_quality_rejects_truncated_or_raw_math_fragments(title: str) -> None:
    assert _title_is_incomplete(title)


@pytest.mark.parametrize(
    "title",
    [
        "将增广矩阵化为行阶梯形",
        "把第二行的负三分之二倍加到第三行",
        "维数不同的向量不能相加",
    ],
)
def test_title_quality_keeps_complete_audience_ready_claims(title: str) -> None:
    assert not _title_is_incomplete(title)


@pytest.mark.parametrize(
    "title",
    [
        "dt→ f(x).",
        "固定 a∈ I",
        "对每个 x∈ I",
        "对任意 varepsilon>0",
        "都存在 delta>0",
        "其中 h≠0",
        "那么 A'(x)=f(x)",
        "(s(3)-s(1))/(3-1)=(15-3)/(2)=6 米/秒",
        "=(1+0-1-2)×1=-2 立方米.",
        "f | 递增 | 递减 | 递增",
        "立方米.",
    ],
)
def test_title_quality_rejects_formula_fragments_with_thin_discourse_prefix(
    title: str,
) -> None:
    assert _formula_like_title(title)


def test_title_quality_does_not_treat_behavior_as_a_dangling_connector() -> None:
    assert not _title_is_incomplete("第2章 极限：用趋近刻画局部行为")
    assert not _title_is_incomplete("连续性条件满足")


def test_title_quality_rejects_a_bare_acceptance_label() -> None:
    assert _title_is_generic_or_stub("验收标准")
    assert _title_is_generic_or_stub("参考结论")


@pytest.mark.parametrize(
    "title",
    ["使得定义域中的 x 只要满足", "由此使得", "完整临界点集合是"],
)
def test_title_quality_rejects_dangling_condition_clauses(title: str) -> None:
    assert _title_is_incomplete(title)


def test_artifact_free_prose_uses_frozen_formula_fences_not_projection() -> None:
    block = CourseBlock(
        block_id="matrix-task",
        section_id="section-a",
        position=0,
        role="activity",
        kind="rich_text",
        payload={
            "markdown": (
                "任务条件：给定增广矩阵。\n\n"
                "$$\n\\begin{bmatrix}1&2\\\\0&1\\end{bmatrix}\n$$\n\n"
                "输出要求：标出主元位置。"
            ),
            "slide_visible_text": (
                "任务条件：给定增广矩阵。\n"
                "\\begin{bmatrix}1&2\\\\0&1\\end{bmatrix}\n"
                "输出要求：标出主元位置。"
            ),
        },
    )

    prose = _artifact_free_prose_text(block)

    assert "任务条件：给定增广矩阵。" in prose
    assert "输出要求：标出主元位置。" in prose
    assert "begin{bmatrix}" not in prose
    assert "$$" not in prose


def test_formula_canvas_uses_presentation_text_while_notes_keep_full_source() -> None:
    block = CourseBlock(
        block_id="three-matrices",
        section_id="section-a",
        position=0,
        role="activity",
        kind="rich_text",
        payload={
            "markdown": (
                "$$A=\\begin{bmatrix}1&0\\\\0&1\\end{bmatrix}$$\n"
                "$$B=\\begin{bmatrix}2&0\\\\0&2\\end{bmatrix}$$\n"
                "$$C=\\begin{bmatrix}3&0\\\\0&3\\end{bmatrix}$$"
            ),
            "slide_visible_text": (
                "$$A=\\begin{bmatrix}1&0\\\\0&1\\end{bmatrix}$$"
            ),
        },
    )

    chunks = _split_artifact_block(
        block,
        slot_kind="formula",
        max_chars=240,
        max_lines=8,
        max_rows=0,
    )

    assert len(chunks) == 1
    assert "A=" in block_source_text(chunks[0])
    assert "B=" not in block_source_text(chunks[0])
    assert "B=" in block_source_text(block)


def test_formula_canvas_restores_first_frozen_display_when_projection_is_prose() -> None:
    block = CourseBlock(
        block_id="objective-with-formula",
        section_id="section-a",
        position=0,
        role="objective",
        kind="rich_text",
        payload={
            "markdown": "目标是识别结构。\n$$A=1$$\n$$B=2$$",
            "slide_visible_text": "目标是识别结构。",
        },
    )

    canvas = _formula_canvas_text(block)

    assert canvas == "$$A=1$$"
    assert "B=2" not in canvas
    assert "B=2" in block_source_text(block)


def test_formula_canvas_keeps_every_display_in_a_compiler_fragment() -> None:
    source = (
        "$$\n"
        "A\\mathbf{v}=\\text{diag}(2, 1/2)"
        "\\begin{pmatrix}x \\\\ y\\end{pmatrix}\n"
        "$$\n\n"
        "$$\n"
        "=\\begin{pmatrix}2x \\\\ \\frac{1}{2}y\\end{pmatrix}\n"
        "$$"
    )
    fragment = CourseBlock(
        block_id="packed-formula-fragment",
        section_id="section-a",
        position=0,
        role="reasoning",
        kind="rich_text",
        payload={
            "markdown": source,
            "artifact_kind": "formula",
            "_v6_artifact_only": True,
        },
    )

    assert _formula_canvas_text(fragment) == source
    assert len(_formula_candidates(_formula_canvas_text(fragment))) == 2


def test_continuation_title_compacts_a_long_formula_chain() -> None:
    block = _block(
        "force-x",
        "lesson-1",
        0,
        role="concept",
        kind="formula",
        text=(
            r"$F_x = -15\cos 45^\circ \approx -10.61\,\text{N}$"
        ),
    )

    candidates = _continuation_title_candidates([block], capacity=36)

    assert r"$F_x \approx -10.61\,\text{N}$" in candidates


def test_continuation_title_uses_source_relation_term_when_chain_is_too_long() -> None:
    block = _block(
        "improper-integral",
        "lesson-1",
        0,
        role="example",
        kind="formula",
        text=(
            r"$\int_1^{\infty}1/x\,dx="
            r"\lim_{b\to\infty}\ln b$"
        ),
    )

    candidates = _continuation_title_candidates([block], capacity=42)

    assert r"$\int_1^{\infty}1/x\,dx$" in candidates


def test_continuation_title_extracts_complete_windows_from_a_long_step() -> None:
    candidates = _bounded_source_title_windows(
        "1. Record the final pass condition together with the evidence needed for another learner to verify it.",
        42,
    )

    assert candidates
    assert all(len(candidate) <= 42 for candidate in candidates)
    assert candidates[0] == "Record the final pass condition together"


def test_sentence_excerpt_never_invents_a_partial_protected_source_token():
    source = (
        "Field observers call SpecimenRegistry.ResolveObservation and record "
        "a 75% confidence threshold before accepting the evidence."
    )
    capacity = source.index("SpecimenRegistry") + len("SpecimenRegis") + 1

    excerpt = _complete_sentence_excerpt(source, capacity)

    assert len(excerpt) <= capacity
    assert excerpt.endswith("…")
    assert "SpecimenRegis" not in excerpt
    assert _protected_tokens(excerpt).issubset(_protected_tokens(source))


def test_sentence_excerpt_preserves_dotted_identifiers_and_decimal_tokens():
    first_sentence = (
        "MonoBehaviour 继承自 UnityEngine.Object，ObjectPool 调用 "
        "GameObject.Instantiate()，并将 Scale 设置为 0.5x。"
    )
    source = (
        f"{first_sentence}"
        "随后继续记录对象状态、内存分配和回归测试结果，确保摘要需要截取。"
    )

    excerpt = _complete_sentence_excerpt(source, len(first_sentence) + 5)

    assert "UnityEngine.Object" in excerpt
    assert "GameObject.Instantiate" in excerpt
    assert "0.5x" in excerpt
    assert _protected_tokens(excerpt).issubset(_protected_tokens(source))


def test_visible_prose_removes_markdown_and_never_ends_on_a_bare_list_marker():
    block = _block(
        "chapter-objective",
        "chapter",
        0,
        role="objective",
        text=(
            "本节规范名称：**现场调查记录规范**。\n"
            "学习者需完成以下目标：\n"
            "1. 在 `Observation Log` 中记录对象、时间与环境条件。\n"
            "2. 对照证据检查记录并说明结论。\n"
            "3. 修正第一处不一致。"
        ),
    )

    content = _bounded_slot_content(
        [block],
        slot_kind="body",
        max_chars=100,
        max_items=0,
        max_lines=0,
        max_rows=0,
    )

    assert not any(marker in content for marker in ("**", "`", "<br>"))
    assert not re.search(r"(?:^|\s)\d+[.)]$", content)
    assert content.endswith(("。", "！", "？", ".", "!", "?", "…"))


def test_display_excerpt_never_cuts_an_ascii_word_in_half():
    source = "Record the site, time, weather, and observer before sampling begins"

    excerpt = _display_excerpt(source, 22)

    assert excerpt.endswith("…")
    assert excerpt[:-1].rstrip(" ,;:").endswith(("site", "time", "weather", "observer"))


def test_visible_prose_preserves_source_identifiers_with_underscores():
    block = _block(
        "source-identifiers",
        "generic-section",
        0,
        role="concept",
        text=(
            "Compare sensor_input with expected_value and preserve the condition "
            "lower_bound < measured_value > upper_bound before publishing the result."
        ),
    )

    content = _bounded_slot_content(
        [block],
        slot_kind="body",
        max_chars=220,
        max_items=0,
        max_lines=0,
        max_rows=0,
    )

    assert "sensor_input" in content
    assert "expected_value" in content
    assert "lower_bound < measured_value > upper_bound" in content


def test_body_slot_preserves_semantic_paragraph_boundaries() -> None:
    block = _block(
        "field-explanation",
        "generic-section",
        0,
        role="concept",
        text=(
            "先记录现场条件，并明确本次观察要回答的问题。\n\n"
            "随后将观察事实与研究者解释分开，避免把推断写成原始证据。\n\n"
            "最后依据验收标准复核结论，并记录需要返工的项目。"
        ),
    )

    content = _bounded_slot_content(
        [block],
        slot_kind="body",
        max_chars=240,
        max_items=0,
        max_lines=0,
        max_rows=0,
    )

    assert content.split("\n\n") == [
        "先记录现场条件，并明确本次观察要回答的问题。",
        "随后将观察事实与研究者解释分开，避免把推断写成原始证据。",
        "最后依据验收标准复核结论，并记录需要返工的项目。",
    ]


def test_item_slot_rejects_lossy_excerpt_instead_of_silently_dropping_items():
    block = _block(
        "field-checks",
        "field-section",
        0,
        role="feedback",
        text="\n".join(
            f"- Evidence check {index} includes a detailed source-grounded explanation"
            for index in range(1, 9)
        ),
    )

    with pytest.raises(ValueError, match="template_slot_capacity_exceeded"):
        _bounded_slot_content(
            [block],
            slot_kind="items",
            max_chars=90,
            max_items=3,
            max_lines=0,
            max_rows=0,
        )


def _block(
    block_id: str,
    section_id: str,
    position: int,
    *,
    role: str,
    text: str,
    kind: str = "rich_text",
) -> CourseBlock:
    return CourseBlock(
        block_id=block_id,
        section_id=section_id,
        position=position,
        role=role,
        kind=kind,
        payload={"title": block_id, "markdown": text},
    )


@pytest.mark.parametrize(
    ("artifact_kind", "artifact_source", "expected_layout_slug"),
    [
        (
            "code",
            "```python\nfor sample in samples:\n    verify(sample)\n```",
            "practice-code",
        ),
        (
            "formula",
            "$$R = accepted / inspected$$",
            "practice-formula",
        ),
        (
            "table",
            "| Sample | Result |\n| --- | --- |\n| A | accepted |\n| B | review |",
            "practice-table",
        ),
    ],
)
def test_template_safe_story_budget_supports_steps_with_characteristic_artifacts(
    artifact_kind: str,
    artifact_source: str,
    expected_layout_slug: str,
) -> None:
    document = refresh_document_revision(CourseDocument(
        course_id=f"generic-field-practice-{artifact_kind}",
        title="Field verification practice",
        sections=[CourseSection(section_id="field", title="Field work", position=0)],
        blocks=[_block(
            "field-practice",
            "field",
            0,
            role="activity",
            text=(
                "Complete the verification task in source order.\n"
                "1. Collect the specimen and record its identifier.\n"
                "2. Apply the declared acceptance rule.\n"
                "3. Preserve the result for independent review.\n\n"
                f"{artifact_source}"
            ),
        )],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    unit = graph.units[0]

    safe_slices = story_safe_page_slices(unit, template)
    complete_slice = next(
        item for item in safe_slices
        if item["source_block_ids"] == unit.primary_block_ids
    )

    assert story_page_count_range(unit, template) == [1, 1]
    assert template.layout_id(expected_layout_slug) in complete_slice["template_layout_ids"]
    assert complete_slice["required_slot_kinds"] == ["steps"]

    layout_id = template.layout_id(expected_layout_slug)
    story = SlideStoryPlanV3(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        batches=[SlideStoryBatchV3(
            batch_id=f"story-{artifact_kind}",
            chapter_id="field",
            provider="fixture-pool",
            model="fixture-story",
            duration_ms=1,
            attempts=1,
            validation_status="passed",
            pages=[SlideStoryPageV3(
                page_id=f"practice-{artifact_kind}-page",
                teaching_unit_id=unit.teaching_unit_id,
                template_layout_id=layout_id,
                title="Verify the field result",
                source_block_ids=unit.primary_block_ids,
                page_ordinal=0,
            )],
        )],
    )
    visual = SlideVisualPlanV2(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        decisions=[SlideVisualDecisionV2(
            page_id=f"practice-{artifact_kind}-page",
            decision=artifact_kind,
            source_block_ids=unit.primary_block_ids,
            resolved_template_layout_id=layout_id,
        )],
    )

    deck = compile_slide_deck_v6(document, graph, story, visual, template)

    assert {region.content_kind for region in deck.pages[0].regions} == {
        "steps",
        artifact_kind,
    }


def test_story_and_visual_contract_accept_one_atomic_table_formula_block(tmp_path) -> None:
    document = refresh_document_revision(CourseDocument(
        course_id="linear-algebra-mixed-artifact",
        title="线性代数",
        sections=[CourseSection(
            section_id="vectors",
            title="向量的表示",
            position=0,
        )],
        blocks=[_block(
            "vector-representations",
            "vectors",
            0,
            role="concept",
            text=(
                "索引表与公式描述同一向量，核验时必须保持维数、索引和分量逐项对应。\n\n"
                "| 索引 $i$ | 1 | 2 | 3 |\n"
                "|---|---:|---:|---:|\n"
                "| 分量 $x_i$ | 2 | -1 | 4 |\n\n"
                "$$y_1=-1,\\quad y_2=1,\\quad y_3=3,\\quad y_4=5$$"
            ),
        )],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    unit = graph.units[0]
    safe_slices = story_safe_page_slices(unit, template)
    complete_slice = next(
        item for item in safe_slices
        if item["source_block_ids"] == unit.primary_block_ids
    )
    layout_id = template.layout_id("evidence-table")

    assert story_page_count_range(unit, template) == [1, 1]
    assert layout_id in complete_slice["template_layout_ids"]

    story = SlideStoryPlanV3(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        batches=[SlideStoryBatchV3(
            batch_id="story-mixed-artifact",
            chapter_id="vectors",
            provider="fixture-pool",
            model="fixture-story",
            duration_ms=1,
            attempts=1,
            validation_status="passed",
            pages=[SlideStoryPageV3(
                page_id="vector-representations-page",
                teaching_unit_id=unit.teaching_unit_id,
                template_layout_id=layout_id,
                title="索引与分量逐项对应",
                source_block_ids=unit.primary_block_ids,
                page_ordinal=0,
            )],
        )],
    )
    visual = SlideVisualPlanV2(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        decisions=[SlideVisualDecisionV2(
            page_id="vector-representations-page",
            decision="table",
            source_block_ids=unit.primary_block_ids,
            resolved_template_layout_id=layout_id,
        )],
    )

    validate_slide_story_plan_v3(story, graph, template)
    validate_slide_visual_plan_v2(visual, story, graph, template)
    deck = compile_slide_deck_v6(document, graph, story, visual, template)

    assert [page.resolved_layout.rsplit("/", 1)[-1] for page in deck.pages] == [
        "evidence-table",
        "evidence-formula",
    ]
    assert [
        region.content_kind
        for page in deck.pages
        for region in page.regions
        if region.content_kind in {"table", "formula"}
    ] == ["table", "formula"]
    assert [page.visual_decision.decision for page in deck.pages] == [
        "table",
        "formula",
    ]
    output = export_slide_deck_v6_pptx(
        deck,
        tmp_path / "mixed-table-formula.pptx",
    )
    render_review = audit_exported_pptx(
        output,
        expected_slide_count=len(deck.pages),
    )
    assert render_review["passed"], render_review["blockers"]


def test_multiline_matrix_uses_rendered_rows_for_template_safe_pagination() -> None:
    formula = (
        "$$\n"
        "\\begin{bmatrix}\n"
        "2 & 3 & -1 \\\\n"
        "1 & -1 & 0 \\\\n"
        "0 & 4 & 5\n"
        "\\end{bmatrix}\n"
        "$$"
    )
    document = refresh_document_revision(CourseDocument(
        course_id="matrix-rendered-row-budget",
        title="矩阵公式分页",
        sections=[CourseSection(
            section_id="matrix",
            title="矩阵表示",
            position=0,
        )],
        blocks=[_block(
            "matrix-formula",
            "matrix",
            0,
            role="concept",
            text=f"三元方程组的系数矩阵如下。\n\n{formula}",
        )],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")

    assert _formula_visual_line_count(formula) == 3
    assert story_page_count_range(graph.units[0], template) == [1, 1]
    assert story_safe_page_slices(graph.units[0], template)


def test_multiple_named_matrices_split_only_at_matrix_boundaries() -> None:
    formula = (
        "$$\n"
        "A=\\begin{bmatrix}1&0&2\\\\0&1&3\\end{bmatrix},\\quad\n"
        "B=\\begin{bmatrix}1&2&4\\\\0&0&5\\end{bmatrix},\\quad\n"
        "C=\\begin{bmatrix}2&1&0\\\\0&3&6\\end{bmatrix}\n"
        "$$"
    )

    candidates = _formula_candidates(formula)

    assert len(candidates) == 3
    assert all(candidate.count("\\begin{bmatrix}") == 1 for candidate in candidates)
    assert [label in candidate for label, candidate in zip("ABC", candidates)] == [
        True,
        True,
        True,
    ]


def test_symbolic_four_row_augmented_matrix_fits_formula_template() -> None:
    formula = (
        "$$\n\\left[\n\\begin{array}{cccc|c}\n"
        "a_{11} & a_{12} & \\cdots & a_{1n} & b_1 \\\\n"
        "a_{21} & a_{22} & \\cdots & a_{2n} & b_2 \\\\n"
        "\\vdots & \\vdots & \\ddots & \\vdots & \\vdots \\\\n"
        "a_{m1} & a_{m2} & \\cdots & a_{mn} & b_m\n"
        "\\end{array}\n\\right]\n$$"
    )
    document = refresh_document_revision(CourseDocument(
        course_id="symbolic-augmented-matrix-budget",
        title="符号增广矩阵",
        sections=[CourseSection(
            section_id="matrix",
            title="一般形式",
            position=0,
        )],
        blocks=[_block(
            "symbolic-matrix",
            "matrix",
            0,
            role="concept",
            text=f"增广矩阵的一般形式如下。\n\n{formula}",
        )],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")

    assert _formula_visual_line_count(formula) == 4
    assert story_page_count_range(graph.units[0], template) == [1, 1]


@pytest.mark.parametrize(
    (
        "layout_slug",
        "visual_decision",
        "source_asset_ids",
        "visual_payload",
        "rendered_visual_kind",
    ),
    [
        (
            "evidence-diagram",
            "diagram",
            [],
            {
                "nodes": [
                    {
                        "node_id": "collect",
                        "label": "Collect the field sample",
                        "source_block_ids": ["observation-flow"],
                    },
                    {
                        "node_id": "compare",
                        "label": "Compare the observation",
                        "source_block_ids": ["observation-flow"],
                    },
                ],
                "edges": [{"source": "collect", "target": "compare"}],
            },
            "rule_diagram",
        ),
        ("evidence-figure", "image", ["field-photo"], {}, "source_image"),
    ],
)
def test_visual_decision_fills_required_visual_slot_during_final_compilation(
    layout_slug: str,
    visual_decision: str,
    source_asset_ids: list[str],
    visual_payload: dict,
    rendered_visual_kind: str,
) -> None:
    document = refresh_document_revision(CourseDocument(
        course_id=f"generic-visual-slot-{visual_decision}",
        title="Field evidence",
        sections=[CourseSection(section_id="field", title="Field review", position=0)],
        blocks=[CourseBlock(
            block_id="observation-flow",
            section_id="field",
            position=0,
            role="concept",
            kind="rich_text",
            payload={
                "markdown": (
                    "Collect the field sample, compare the observation, and record "
                    "the verified result."
                )
            },
            asset_refs=source_asset_ids,
        )],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    unit = graph.units[0]
    page_id = f"visual-slot-{visual_decision}"
    layout_id = template.layout_id(layout_slug)
    story = SlideStoryPlanV3(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        batches=[SlideStoryBatchV3(
            batch_id="story-visual-slot",
            chapter_id="field",
            provider="fixture-pool",
            model="fixture-story",
            duration_ms=1,
            attempts=1,
            validation_status="passed",
            pages=[SlideStoryPageV3(
                page_id=page_id,
                teaching_unit_id=unit.teaching_unit_id,
                template_layout_id=layout_id,
                title="Collect and compare field evidence",
                source_block_ids=unit.primary_block_ids,
                page_ordinal=0,
            )],
        )],
    )
    visual = SlideVisualPlanV2(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        decisions=[SlideVisualDecisionV2(
            page_id=page_id,
            decision=visual_decision,
            source_block_ids=unit.primary_block_ids,
            source_asset_ids=source_asset_ids,
            visual_payload=visual_payload,
            resolved_template_layout_id=layout_id,
        )],
    )

    deck = compile_slide_deck_v6(document, graph, story, visual, template)
    rendered_page = adapt_v6_page_to_slide_spec(deck.pages[0])

    assert [region.content_kind for region in deck.pages[0].regions] == ["body"]
    assert deck.pages[0].visual_decision.decision == visual_decision
    assert [item["kind"] for item in rendered_page.visuals] == [rendered_visual_kind]


def test_code_block_source_text_reads_the_canonical_code_payload() -> None:
    block = CourseBlock(
        block_id="source-code",
        section_id="source",
        position=0,
        role="example",
        kind="code",
        payload={"language": "csharp", "code": "void Start() { Debug.Log(\"ready\"); }"},
    )

    assert block_source_text(block) == 'void Start() { Debug.Log("ready"); }'
    assert block_artifact_kinds(block) == ["code"]


def test_empty_code_block_does_not_claim_a_renderable_code_artifact() -> None:
    block = CourseBlock(
        block_id="empty-code",
        section_id="source",
        position=0,
        role="example",
        kind="code",
        payload={"language": "csharp", "code": ""},
    )

    assert block_source_text(block) == ""
    assert block_artifact_kinds(block) == []


def test_teacher_script_projection_keeps_screen_signals_and_drops_delivery_cues() -> None:
    source = (
        "同学们，现在请看黑板。【板书】牛顿第二定律：$\\vec F=m\\vec a$。"
        "【提问】如果合力向左，加速度方向如何？【等待回应】"
        "结论：加速度方向与合力方向一致。"
    )
    block = CourseBlock(
        block_id="teacher-script",
        section_id="source",
        position=0,
        role="concept",
        payload={
            "markdown": source,
            "module_id": "science_model",
            "module_instance_id": "teacher-script",
        },
    )

    projected = block_presentation_text(block)

    assert "$\\vec F=m\\vec a$" in projected
    assert "结论：加速度方向与合力方向一致。" in projected
    assert "同学们" not in projected
    assert "【板书】" not in projected
    assert "【等待回应】" not in projected
    assert block_source_text(block) == source


def test_teacher_script_projection_removes_spoken_setup_but_keeps_direct_task() -> None:
    source = (
        "这节课，我们要先来看一个真实情境。"
        "拿出练习本，独立完成受力图并标明方向。"
        "展示标准解答。"
        "结论：合力方向就是加速度方向。"
    )
    block = CourseBlock(
        block_id="teacher-script-classroom-copy",
        section_id="source",
        position=0,
        role="activity",
        payload={
            "markdown": source,
            "module_id": "learner_action",
            "module_instance_id": "teacher-script-classroom-copy",
        },
    )

    projected = block_presentation_text(block)

    assert "独立完成受力图并标明方向。" in projected
    assert "结论：合力方向就是加速度方向。" in projected
    assert "这节课" not in projected
    assert "我们要" not in projected
    assert "拿出练习本" not in projected
    assert "展示标准解答" not in projected


def test_teacher_script_projection_turns_production_copy_into_learner_copy() -> None:
    source = (
        "用具体任务而非抽象描述呈现目标，例如'课结束前你能正确计算矩阵乘法'。"
        "给出 3 道练习题，覆盖加法、数乘和乘法。"
        "请 2 名学习者上台写答案，逐题点评。"
    )
    block = CourseBlock(
        block_id="learner-ready-copy",
        section_id="source",
        position=0,
        role="activity",
        payload={
            "markdown": source,
            "module_id": "learner_action",
        },
    )

    projected = block_presentation_text(block)

    assert "课结束前你能正确计算矩阵乘法" in projected
    assert "3 道练习题，覆盖加法、数乘和乘法" in projected
    assert "用具体任务" not in projected
    assert "给出" not in projected
    assert "2 名学习者" not in projected


def test_source_authored_ellipsis_survives_noncontiguous_classroom_projection() -> None:
    source = (
        "教师补充一段只进入讲者备注的说明。"
        "学习目标：能够判断能否建模，因为……。"
        "教师再补充一个课堂动作。结论：模型边界必须明确。"
    )
    projection = "学习目标：能够判断能否建模，因为……。\n结论：模型边界必须明确。"

    assert _ellipsis_maps_to_frozen_source(projection, source) is True
    assert _ellipsis_maps_to_frozen_source("学习目标：能够判断能否建模…", source) is False


def test_teacher_script_projection_accepts_explicit_slide_copy_without_rewriting_source() -> None:
    block = CourseBlock(
        block_id="teacher-script-explicit",
        section_id="source",
        position=0,
        role="activity",
        payload={
            "markdown": "请大家先分组，然后按我的口头说明完成任务。",
            "slide_visible_text": "任务：独立画出受力图，并标注所有力的方向。",
            "module_id": "learner_action",
        },
    )

    assert block_presentation_text(block) == "任务：独立画出受力图，并标注所有力的方向。"
    assert block_source_text(block).startswith("请大家")


def test_teacher_script_projection_preserves_matrix_rows_inside_semicolons() -> None:
    source = (
        "展开过程：板书例2：A=[1,2,3;0,1,4;5,6,0]，"
        "构造增广矩阵 [A|I]，逐步进行初等行变换，完成验算。"
        "任务与检验：抄录例2，跟随讲解过程计算。"
    )
    block = CourseBlock(
        block_id="matrix-example",
        section_id="source",
        position=0,
        role="example",
        payload={
            "markdown": source,
            "module_id": "math_worked_example",
        },
    )

    projected = block_presentation_text(block)

    assert "A=[1,2,3;0,1,4;5,6,0]" in projected
    assert "展开过程" not in projected
    assert "板书" not in projected
    assert "抄录例2" not in projected


def test_inline_formula_teacher_block_is_a_formula_artifact() -> None:
    block = CourseBlock(
        block_id="teacher-inline-formula",
        section_id="source",
        position=0,
        role="concept",
        payload={
            "markdown": "分解公式：$F_x=F\\cos\\theta$，$F_y=F\\sin\\theta$。",
            "module_id": "science_model",
        },
    )

    assert block_artifact_kinds(block) == ["formula"]


def test_objective_role_uses_orientation_page_intent() -> None:
    assert teaching_intent_for_roles(["objective"]) == "orientation"


def test_story_preflight_rejects_a_code_template_for_an_empty_code_block() -> None:
    document = refresh_document_revision(CourseDocument(
        course_id="empty-code-template",
        title="Empty code template",
        sections=[CourseSection(section_id="source", title="Source", position=0)],
        blocks=[
            CourseBlock(
                block_id="empty-code",
                section_id="source",
                position=0,
                role="activity",
                kind="code",
                payload={"language": "csharp", "code": ""},
            ),
            _block(
                "practice-steps",
                "source",
                1,
                role="activity",
                text="1. 创建脚本。\n2. 挂载组件。\n3. 运行并检查控制台。",
            ),
        ],
    ))
    graph = compile_course_presentation_graph(document)
    unit = graph.units[0]
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    story = SlideStoryPlanV3(
        source_document_revision=graph.source_document_revision,
        template_digest=template.template_digest,
        batches=[SlideStoryBatchV3(
            batch_id="story-source",
            chapter_id="source",
            provider="test",
            model="test",
            duration_ms=1,
            attempts=1,
            validation_status="passed",
            pages=[SlideStoryPageV3(
                page_id="empty-code-page",
                teaching_unit_id=unit.teaching_unit_id,
                template_layout_id=template.layout_id("practice-code"),
                title="创建脚本并检查控制台",
                summary="",
                source_block_ids=list(unit.primary_block_ids),
                page_ordinal=0,
            )],
        )],
    )

    with pytest.raises(V6BuildError, match="template_required_slot_unfilled"):
        validate_slide_story_plan_v3(story, graph, template)


def _cross_subject_document() -> CourseDocument:
    long_definition = "生态承载力描述环境在不发生不可逆退化时可持续支持的活动规模。" * 12
    return refresh_document_revision(
        CourseDocument(
            course_id="course-generic-ecology",
            title="城市生态调查方法",
            sections=[
                CourseSection(section_id="s1", title="界定调查问题", position=0),
                CourseSection(section_id="s2", title="现场证据与解释", position=1),
            ],
            blocks=[
                _block("b1", "s1", 0, role="concept", text=long_definition),
                _block("b2", "s1", 1, role="reasoning", text="先确定空间范围，再记录时间窗口和观察条件。"),
                _block("b3", "s1", 2, role="activity", text="选择一个街区，完成一次定点观察。"),
                _block("b4", "s1", 3, role="feedback", text="检查记录是否包含地点、时间、天气和观察对象。"),
                _block("b5", "s2", 0, role="concept", text="证据解释必须区分观察、推断和结论。"),
                _block("b6", "s2", 1, role="example", text="样方 A 的鸟类数量记录如下。", kind="table"),
                _block("b7", "s2", 2, role="reasoning", text="数量变化只有结合采样条件才能解释。"),
            ],
        )
    )


def test_course_graph_preserves_long_semantic_unit_and_covers_every_block() -> None:
    document = _cross_subject_document()
    graph = compile_course_presentation_graph(document, teaching_plan={})

    assert graph.schema_version == "course_presentation_graph_v1"
    assert graph.source_document_revision == document.document_revision
    assert graph.primary_block_coverage == 1.0
    assert [block_id for unit in graph.units for block_id in unit.primary_block_ids] == [
        "b1", "b2", "b3", "b4", "b5", "b6", "b7",
    ]
    first = graph.units[0]
    assert first.primary_block_ids == ["b1", "b2", "b3", "b4"]
    assert len(first.source_text) > 230
    assert all(unit.section_id in {"s1", "s2"} for unit in graph.units)
    assert not any({"b4", "b5"}.issubset(set(unit.primary_block_ids)) for unit in graph.units)


def test_story_page_count_range_keeps_every_template_safe_partition_available() -> None:
    document = refresh_document_revision(CourseDocument(
        course_id="generic-unbounded-story-pages",
        title="Source-complete lesson",
        sections=[CourseSection(
            section_id="lesson",
            title="Preserve each teaching claim",
            position=0,
        )],
        blocks=[
            _block(
                f"claim-{index}",
                "lesson",
                index,
                role="concept" if index == 0 else "reasoning",
                text=(
                    f"Claim {index + 1} preserves its complete source-backed explanation "
                    "and remains independently teachable."
                ),
            )
            for index in range(5)
        ],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")

    assert len(graph.units) == 1
    assert graph.units[0].primary_block_ids == [f"claim-{index}" for index in range(5)]
    assert story_page_count_range(graph.units[0], template) == [1, 5]


def test_story_visible_copy_rejects_narrow_formula_panel_overflow_before_render() -> None:
    visible_copy = (
        "主对角线元素相乘得到行列式，非对角元素不改变该结构判断。"
        * 8
    )
    document = refresh_document_revision(CourseDocument(
        course_id="formula-story-capacity",
        title="三角矩阵",
        sections=[CourseSection(
            section_id="formula",
            title="三角矩阵的行列式",
            position=0,
        )],
        blocks=[_block(
            "triangular-determinant",
            "formula",
            0,
            role="reasoning",
            text=(
                f"三角矩阵的行列式可以直接计算。{visible_copy}\n\n"
                "$$\\det(A)=a_{11}a_{22}a_{33}$$"
            ),
        )],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    layout = template.get_layout(template.layout_id("evidence-formula"))
    assert layout is not None
    body_slot = next(slot for slot in layout.slots if slot.slot_kind == "body")
    assert len(visible_copy) < body_slot.max_chars
    assert not capacity_profile_text_fits(
        body_slot.capacity_profile,
        visible_copy,
    )
    unit = graph.units[0]
    story = SlideStoryPlanV3(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        batches=[SlideStoryBatchV3(
            batch_id="formula-capacity",
            chapter_id="formula",
            provider="fixture-provider",
            model="fixture-model",
            duration_ms=1,
            attempts=1,
            validation_status="passed",
            pages=[SlideStoryPageV3(
                page_id="formula-capacity-page",
                teaching_unit_id=unit.teaching_unit_id,
                template_layout_id=layout.template_layout_id,
                title="三角矩阵的行列式",
                visible_copy=[visible_copy],
                source_block_ids=unit.primary_block_ids,
                page_ordinal=0,
            )],
        )],
    )

    with pytest.raises(V6BuildError) as captured:
        validate_slide_story_plan_v3(story, graph, template)

    assert captured.value.failure.code == "story_visible_copy_capacity_exceeded"
    assert captured.value.failure.page_id == "formula-capacity-page"


def test_shadow_chapter_freezes_only_the_selected_section_subtree() -> None:
    document = refresh_document_revision(CourseDocument(
        course_id="generic-shadow-course",
        title="Generic field methods",
        sections=[
            CourseSection(section_id="chapter-a", title="Observe", position=0, level=1),
            CourseSection(section_id="lesson-a", title="Record", position=1, level=2, parent_section_id="chapter-a"),
            CourseSection(section_id="chapter-b", title="Explain", position=2, level=1),
        ],
        blocks=[
            _block("a-root", "chapter-a", 0, role="concept", text="Define the observation scope."),
            _block("a-child", "lesson-a", 0, role="activity", text="Record one field observation."),
            _block("b-root", "chapter-b", 0, role="concept", text="Explain the evidence."),
        ],
    ))

    chapter = compile_shadow_chapter_document(document, "chapter-a")

    assert [section.section_id for section in chapter.sections] == ["chapter-a", "lesson-a"]
    assert [block.block_id for block in chapter.blocks] == ["a-root", "a-child"]
    assert chapter.document_revision != document.document_revision
    assert len(document.sections) == 3

    with pytest.raises(V6BuildError, match="shadow_chapter_not_found"):
        compile_shadow_chapter_document(document, "missing")


def test_course_graph_keeps_characteristic_artifact_with_context_and_result() -> None:
    document = refresh_document_revision(
        CourseDocument(
            course_id="course-generic-systems",
            title="交互系统设计",
            sections=[CourseSection(section_id="s1", title="事件响应", position=0)],
            blocks=[
                _block("condition", "s1", 0, role="concept", text="按钮仅在表单有效时提交。"),
                _block("implementation", "s1", 1, role="example", text="function submit() { return validate(); }", kind="code"),
                _block("result", "s1", 2, role="feedback", text="验证失败时保持当前输入并显示原因。"),
            ],
        )
    )

    graph = compile_course_presentation_graph(document, teaching_plan={})

    assert len(graph.units) == 1
    assert graph.units[0].primary_block_ids == ["condition", "implementation", "result"]
    assert graph.units[0].artifact_kinds == ["code"]


def test_course_graph_carries_formal_teaching_plan_context_without_rewriting_source() -> None:
    document = _cross_subject_document()
    graph = compile_course_presentation_graph(document, teaching_plan={
        "sections": [{
            "node_id": "s1",
            "key_points": ["调查边界"],
            "teaching_modules": [{
                "module_id": "evidence-loop",
                "teaching_purpose": "建立观察与核对闭环",
                "knowledge_names": ["观察条件", "核对标准"],
            }],
        }],
    })

    first = graph.units[0]
    assert first.teaching_plan_context["module_ids"] == ["evidence-loop"]
    assert first.teaching_plan_context["teaching_purposes"] == ["建立观察与核对闭环"]
    assert first.teaching_plan_context["knowledge_names"] == ["观察条件", "核对标准"]
    assert "建立观察与核对闭环" not in first.source_text


def test_source_contract_freezes_course_and_template_digests() -> None:
    document = _cross_subject_document()
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")

    source = compile_ppt_source_contract_v2(
        document,
        teaching_plan={"revision_id": "plan-r7"},
        knowledge_snapshot={"revision_id": "knowledge-r2"},
        coherence_contract={"revision_id": "coherence-r4"},
        template_contract=template,
        locale="zh-CN",
    )

    assert source.schema_version == "ppt_source_contract_v2"
    assert source.course_document_revision == document.document_revision
    assert source.active_block_ids == ["b1", "b2", "b3", "b4", "b5", "b6", "b7"]
    assert source.teaching_plan_revision == "plan-r7"
    assert source.knowledge_revision == "knowledge-r2"
    assert source.coherence_revision == "coherence-r4"
    assert source.template_digest == template.template_digest
    assert source.source_digest.startswith("pptsrc_")


def test_v6_build_signature_tracks_full_source_and_frozen_template() -> None:
    document = _cross_subject_document()
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    course_data = {
        "language": "en",
        "course_teaching_plan": {"revision_id": "plan-1", "sections": []},
        "course_knowledge_base": {"revision_id": "knowledge-1"},
        "course_coherence_contract": {"revision_id": "coherence-1"},
    }

    baseline = build_signature_v6(
        document=document,
        course_data=course_data,
        mode="teaching",
        theme="qizhi-classroom",
        template_contract=template,
    )
    changed_source = build_signature_v6(
        document=document,
        course_data={
            **course_data,
            "course_teaching_plan": {
                "revision_id": "plan-1",
                "sections": [{"teaching_purpose": "A newly frozen purpose"}],
            },
        },
        mode="teaching",
        theme="qizhi-classroom",
        template_contract=template,
    )
    changed_template = build_signature_v6(
        document=document,
        course_data=course_data,
        mode="teaching",
        theme="qizhi-classroom",
        template_contract=template.model_copy(
            update={"template_digest": "tmpl_changed"}
        ),
    )
    changed_materials = build_signature_v6(
        document=document,
        course_data={
            **course_data,
            "teacher_lesson_source": {
                "material_bindings": [{
                    "material_asset_id": "mat-1",
                    "source_label": "reference.pdf",
                    "role": "reference",
                }],
            },
        },
        mode="teaching",
        theme="qizhi-classroom",
        template_contract=template,
    )

    assert baseline["compiler_version"] == "slide_deck_v6_compiler_v17"
    assert baseline["signature"] != changed_source["signature"]
    assert baseline["signature"] != changed_template["signature"]
    assert baseline["signature"] != changed_materials["signature"]


def test_course_presentation_graph_exposes_only_bound_reference_evidence() -> None:
    document = _cross_subject_document()
    document.blocks[0].evidence_refs = ["ev-ecology"]
    document = refresh_document_revision(document)

    graph = compile_course_presentation_graph(
        document,
        evidence_catalog=[{
            "evidence_id": "ev-ecology",
            "summary": "样方调查要记录空间范围和时间窗口。",
        }],
    )

    unit = graph.units[0]
    assert unit.primary_block_evidence_refs["b1"] == ["ev-ecology"]
    assert unit.primary_block_evidence_summaries["b1"] == [
        "样方调查要记录空间范围和时间窗口。"
    ]
    assert unit.primary_block_evidence_refs["b2"] == []


def _valid_story(document: CourseDocument):
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    pages = []
    for index, unit in enumerate(graph.units):
        layout_slug = (
            "evidence-table"
            if "table" in unit.artifact_kinds
            else "content-stack"
        )
        pages.append(
            SlideStoryPageV3(
                page_id=f"p{index + 1}",
                teaching_unit_id=unit.teaching_unit_id,
                template_layout_id=template.layout_id(layout_slug),
                title=unit.source_text[:40],
                summary="",
                source_block_ids=unit.primary_block_ids,
                page_ordinal=index,
            )
        )
    story = SlideStoryPlanV3(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        batches=[
            SlideStoryBatchV3(
                batch_id="batch-synthetic",
                chapter_id="synthetic",
                provider="fixture-provider",
                model="fixture-model",
                duration_ms=12,
                attempts=1,
                validation_status="passed",
                pages=pages,
            )
        ],
    )
    return graph, template, story


def _strict_manuscript_fixture(document: CourseDocument):
    graph, template, story = _valid_story(document)
    visual = SlideVisualPlanV2(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        decisions=[SlideVisualDecisionV2(
            page_id=page.page_id,
            decision=(
                "table"
                if page.template_layout_id.endswith("/evidence-table")
                else "text_native"
            ),
            source_block_ids=page.source_block_ids,
            resolved_template_layout_id=page.template_layout_id,
        ) for page in story.pages],
    )
    legacy = compile_ppt_manuscript_v1(
        document,
        graph,
        story,
        visual,
        template,
    )
    source_ids = list(dict.fromkeys(
        block_id
        for page in legacy.pages
        for block_id in page.source_script_block_ids
    ))
    seed = legacy.model_copy(update={
        "teaching_content_contract_version": "page_teaching_v1",
        "narrative_brief": SlideNarrativeBriefV1(
            central_question=f"怎样理解{document.title}的核心关系？",
            learning_path=[page.title for page in legacy.pages],
            observable_checkpoints=["能用页面结论核对讲义中的条件与结果"],
            time_budget_minutes=max(1, len(legacy.pages) * 5),
            must_include_source_block_ids=source_ids,
        ),
    })
    updates = []
    for index, page in enumerate(seed.pages):
        source_text = next(
            (
                note.full_text.strip()
                for note in (page.speaker_notes.source_blocks if page.speaker_notes else [])
                if note.full_text.strip()
            ),
            page.title,
        )
        claim = page.primary_claim.strip()
        if not claim or re.sub(r"\W+", "", claim).casefold() == re.sub(
            r"\W+", "", page.title
        ).casefold():
            claim = f"本页结论：{source_text}"[:320]
        updates.append({
            "page_id": page.page_id,
            "page_goal": page.page_goal or f"理解{page.title}",
            "primary_claim": claim,
            "audience_action": (
                "完成本页讲义给出的任务" if page.page_type == "practice" else ""
            ),
            "expected_response": (
                claim if page.page_type == "practice" else ""
            ),
            "transition": (
                f"从课程主题进入{page.title}"
                if index == 0
                else f"把上一页结论用于理解{page.title}"
            ),
            "reveal_steps": page.reveal_steps or [source_text[:96]],
            "composition_notes": page.composition_notes or "按来源顺序呈现结论与证据",
        })
    manuscript = revise_ppt_manuscript_v1(seed, updates)
    assert manuscript.quality_status == "passed", [
        item.code for item in manuscript.quality_issues
    ]
    return graph, template, story, visual, manuscript


def _regenerated_page_response(page, *, question_ids=None, visual_ids=None):
    return {
        "schema_version": "slide_story_batch_response_v3",
        "chapter_id": f"targeted-{page.page_id}",
        "narrative_brief": {
            "schema_version": "slide_narrative_brief_v1",
            "central_question": "",
            "learning_path": [],
            "observable_checkpoints": [],
            "time_budget_minutes": 0,
            "must_include_source_block_ids": [],
        },
        "pages": [{
            "page_id": page.page_id,
            "teaching_unit_id": f"target:{page.page_id}",
            "template_layout_id": page.layout_id,
            "title": page.title,
            "summary": "",
            "visible_copy": list(page.visible_copy),
            "page_goal": page.page_goal,
            "primary_claim": page.primary_claim,
            "audience_question": page.audience_question,
            "audience_action": page.audience_action,
            "expected_response": page.expected_response,
            "observable_evidence": page.observable_evidence,
            "transition": page.transition,
            "reveal_steps": list(page.reveal_steps),
            "composition_notes": f"{page.composition_notes}，局部重生成后复核",
            "question_bank_item_ids": list(question_ids or []),
            "shared_visual_expression_ids": list(visual_ids or []),
            "source_block_ids": list(page.source_script_block_ids),
        }],
    }


def test_strict_manuscript_blocks_missing_ai_narrative_and_page_teaching_fields() -> None:
    document = _cross_subject_document()
    graph, template, story = _valid_story(document)
    visual = SlideVisualPlanV2(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        decisions=[SlideVisualDecisionV2(
            page_id=page.page_id,
            decision=(
                "table"
                if page.template_layout_id.endswith("/evidence-table")
                else "text_native"
            ),
            source_block_ids=page.source_block_ids,
            resolved_template_layout_id=page.template_layout_id,
        ) for page in story.pages],
    )

    manuscript = compile_ppt_manuscript_v1(
        document,
        graph,
        story,
        visual,
        template,
        require_ai_teaching_content=True,
    )

    codes = {item.code for item in manuscript.quality_issues}
    assert manuscript.teaching_content_contract_version == "page_teaching_v1"
    assert manuscript.quality_status == "blocked"
    assert "ppt_manuscript_narrative_brief_incomplete" in codes
    assert "ppt_manuscript_narrative_job_missing" in codes
    assert "ppt_manuscript_reveal_sequence_not_semantic" in codes
    assert "ppt_manuscript_composition_notes_missing" in codes
    assert "ppt_manuscript_ai_visible_copy_missing" in codes


def test_strict_manuscript_rejects_slot_reveals_and_generic_transitions() -> None:
    document = _cross_subject_document()
    _graph, _template, _story, _visual, manuscript = (
        _strict_manuscript_fixture(document)
    )
    assert len(manuscript.pages) >= 2
    page = manuscript.pages[1]
    slot_id = next(
        region.slot_id for region in page.regions if region.slot_id
    )
    invalid_pages = [item.model_copy(deep=True) for item in manuscript.pages]
    invalid_pages[1].reveal_steps = [slot_id]
    invalid_pages[1].transition = "承接上一页并推进到下一教学判断"

    issues = _ppt_manuscript_quality_issues(
        invalid_pages,
        require_teaching_content=True,
        narrative_brief=manuscript.narrative_brief,
    )

    codes = {item.code for item in issues if item.page_id == page.page_id}
    assert "ppt_manuscript_reveal_sequence_not_semantic" in codes
    assert "ppt_manuscript_transition_not_specific" in codes


def test_strict_manuscript_reports_untraceable_teaching_tokens() -> None:
    document = _cross_subject_document()
    _graph, _template, _story, _visual, manuscript = (
        _strict_manuscript_fixture(document)
    )
    invalid_pages = [item.model_copy(deep=True) for item in manuscript.pages]
    invalid_pages[0].page_goal = "解释 fabricatedMetric9001 的作用"

    issues = _ppt_manuscript_quality_issues(
        invalid_pages,
        require_teaching_content=True,
        narrative_brief=manuscript.narrative_brief,
    )

    issue = next(
        item
        for item in issues
        if item.code == "ppt_manuscript_teaching_content_untraceable"
    )
    assert issue.page_id == invalid_pages[0].page_id
    assert "teaching=fabricatedmetric9001" in issue.message


def test_teacher_manuscript_edit_syncs_visible_regions_and_preserves_frozen_contracts() -> None:
    document = _cross_subject_document()
    _graph, _template, _story, _visual, manuscript = (
        _strict_manuscript_fixture(document)
    )
    page = next(
        item
        for item in manuscript.pages
        if item.source_script_block_ids
        and item.speaker_notes
        and item.speaker_notes.source_blocks
        and len(item.visible_copy) == len([
            region for region in item.regions if region.content_kind != "notes"
        ])
    )
    revised_copy = list(page.visible_copy)
    revised_copy[-1] = next(
        note.full_text for note in page.speaker_notes.source_blocks
        if note.full_text
    )

    revised = revise_ppt_manuscript_v1(manuscript, [{
        "page_id": page.page_id,
        "visible_copy": revised_copy,
        "teacher_locked": True,
    }])
    revised_page = next(item for item in revised.pages if item.page_id == page.page_id)

    assert revised.manuscript_revision != manuscript.manuscript_revision
    assert revised_page.visible_copy == [
        region.content.strip()
        for region in revised_page.regions
        if region.content_kind != "notes" and region.content.strip()
    ]
    assert revised_page.visible_copy[-1] == revised_copy[-1]
    assert revised_page.teacher_locked is True
    assert revised_page.lock_source_document_revision == manuscript.source_document_revision
    assert revised_page.layout_id == page.layout_id
    assert revised_page.source_script_block_ids == page.source_script_block_ids
    assert revised_page.web_renderer_adapter == page.web_renderer_adapter
    assert revised_page.pptx_renderer_adapter == page.pptx_renderer_adapter

    with pytest.raises(V6BuildError, match="ppt_manuscript_field_not_editable"):
        revise_ppt_manuscript_v1(manuscript, [{
            "page_id": page.page_id,
            "layout_id": "another-layout",
        }])
    with pytest.raises(V6BuildError, match="ppt_manuscript_field_not_editable"):
        revise_ppt_manuscript_v1(manuscript, [{
            "page_id": page.page_id,
            "question_bank_item_ids": ["teacher-injected-question"],
        }])


def test_manuscript_quality_rejects_visible_prose_cut_inside_a_source_phrase() -> None:
    document = _cross_subject_document()
    _graph, _template, _story, _visual, manuscript = (
        _strict_manuscript_fixture(document)
    )
    target = next(
        page for page in manuscript.pages
        if any(region.content_kind == "body" for region in page.regions)
        and page.speaker_notes
        and page.speaker_notes.source_blocks
    ).model_copy(deep=True)
    body = next(region for region in target.regions if region.content_kind == "body")
    body.content = "结论：主对角线元素相"
    target.visible_copy = [
        region.content.strip()
        for region in target.regions
        if region.content_kind != "notes" and region.content.strip()
    ]
    target.speaker_notes.source_blocks[0].full_text = (
        "主对角线元素相等时，矩阵表示等比缩放。"
    )

    issues = _ppt_manuscript_quality_issues([target])

    assert "ppt_manuscript_visible_copy_incomplete" in {
        issue.code for issue in issues
    }


def test_source_impact_keeps_unbound_pages_and_exposes_locked_conflicts() -> None:
    document = _cross_subject_document()
    _graph, _template, _story, _visual, manuscript = (
        _strict_manuscript_fixture(document)
    )
    target = next(
        page for page in manuscript.pages if page.source_script_block_ids
    )
    locked = revise_ppt_manuscript_v1(manuscript, [{
        "page_id": target.page_id,
        "teacher_locked": True,
    }])

    affected = affected_ppt_manuscript_page_ids(
        locked,
        [target.source_script_block_ids[0]],
    )

    assert target.page_id in affected
    assert next(page for page in locked.pages if page.page_id == target.page_id).teacher_locked
    assert [
        page.page_id for page in locked.pages
        if page.page_id not in affected
    ] == [
        page.page_id for page in manuscript.pages
        if page.page_id not in affected
    ]


@pytest.mark.asyncio
async def test_source_rebase_uses_current_notes_and_preserves_unaffected_pages() -> None:
    document = _cross_subject_document()
    _graph, template, _story, _visual, manuscript = (
        _strict_manuscript_fixture(document)
    )
    current = document.model_copy(deep=True)
    changed_block = next(block for block in current.blocks if block.block_id == "b5")
    changed_block.payload["markdown"] = (
        "证据解释必须分开记录到的现象、基于现象的推断和可检验的结论。"
    )
    current = refresh_document_revision(current)
    before_pages = {
        page.page_id: page.model_dump(mode="json") for page in manuscript.pages
    }

    rebased, affected, locked = rebase_ppt_manuscript_source_blocks_v1(
        manuscript,
        current,
        source_script_revision_id="script-r2",
    )

    assert affected == ["p2"]
    assert locked == []
    assert rebased.source_document_revision == current.document_revision
    assert rebased.source_script_revision_id == "script-r2"
    assert rebased.manuscript_revision != manuscript.manuscript_revision
    assert rebased.manuscript_revision == stable_hash(
        rebased.model_dump(
            mode="json", exclude={"schema_version", "manuscript_revision"}
        ),
        prefix="pptman_",
    )
    assert [
        page.model_dump(mode="json") for page in rebased.pages
        if page.page_id not in affected
    ] == [
        before_pages[page.page_id] for page in manuscript.pages
        if page.page_id not in affected
    ]
    target = next(page for page in rebased.pages if page.page_id == "p2")
    current_note = next(
        note for note in target.speaker_notes.source_blocks
        if note.block_id == "b5"
    )
    assert current_note.full_text == changed_block.payload["markdown"]
    assert current_note.block_revision == changed_block.internal_revision

    requests = []
    response_target = target.model_copy(deep=True)
    response_target.visible_copy[1] = "\n\n".join([
        str(changed_block.payload["markdown"]),
        next(
            block_source_text(block)
            for block in current.blocks if block.block_id == "b7"
        ),
    ])

    async def planner(request):
        requests.append(request)
        return _regenerated_page_response(response_target)

    revised = await regenerate_ppt_manuscript_pages_v1(
        rebased,
        target_page_ids=affected,
        ai_planner=planner,
    )
    b5_request = next(
        item for item in requests[0]["teaching_units"][0]["primary_blocks"]
        if item["block_id"] == "b5"
    )
    assert b5_request["source_title"] == "b5"
    assert b5_request["source_text"] == changed_block.payload["markdown"]
    deck = compile_slide_deck_v6_from_manuscript(
        current,
        compile_course_presentation_graph(current, teaching_plan={}),
        revised,
        template,
    )
    assert deck.source_document_revision == current.document_revision
    assert next(page for page in deck.pages if page.page_id == "p2").regions[
        1
    ].content == response_target.visible_copy[1]

    teacher_locked = revise_ppt_manuscript_v1(manuscript, [{
        "page_id": "p2",
        "teacher_locked": True,
    }])
    _locked_rebase, locked_affected, locked_conflicts = (
        rebase_ppt_manuscript_source_blocks_v1(
            teacher_locked,
            current,
            source_script_revision_id="script-r2",
        )
    )
    assert locked_affected == ["p2"]
    assert locked_conflicts == ["p2"]


def test_source_rebase_requires_full_rebuild_for_structural_or_artifact_drift() -> None:
    document = _cross_subject_document()
    _graph, _template, _story, _visual, manuscript = (
        _strict_manuscript_fixture(document)
    )

    added = document.model_copy(deep=True)
    added.blocks.append(_block(
        "b8", "s2", 3, role="summary", text="用证据链复核调查结论。"
    ))
    with pytest.raises(V6BuildError, match="ppt_manuscript_source_structure_changed"):
        rebase_ppt_manuscript_source_blocks_v1(
            manuscript,
            refresh_document_revision(added),
            source_script_revision_id="script-added",
        )

    removed = document.model_copy(deep=True)
    removed.blocks = [block for block in removed.blocks if block.block_id != "b7"]
    with pytest.raises(V6BuildError, match="ppt_manuscript_source_structure_changed"):
        rebase_ppt_manuscript_source_blocks_v1(
            manuscript,
            refresh_document_revision(removed),
            source_script_revision_id="script-removed",
        )

    reordered = document.model_copy(deep=True)
    next(block for block in reordered.blocks if block.block_id == "b5").position = 2
    next(block for block in reordered.blocks if block.block_id == "b7").position = 0
    with pytest.raises(V6BuildError, match="ppt_manuscript_source_structure_changed"):
        rebase_ppt_manuscript_source_blocks_v1(
            manuscript,
            refresh_document_revision(reordered),
            source_script_revision_id="script-reordered",
        )

    role_changed = document.model_copy(deep=True)
    next(block for block in role_changed.blocks if block.block_id == "b5").role = "summary"
    with pytest.raises(V6BuildError, match="ppt_manuscript_source_structure_changed"):
        rebase_ppt_manuscript_source_blocks_v1(
            manuscript,
            refresh_document_revision(role_changed),
            source_script_revision_id="script-role",
        )

    artifact_changed = document.model_copy(deep=True)
    next(block for block in artifact_changed.blocks if block.block_id == "b6").kind = "code"
    with pytest.raises(V6BuildError, match="ppt_manuscript_source_artifact_changed"):
        rebase_ppt_manuscript_source_blocks_v1(
            manuscript,
            refresh_document_revision(artifact_changed),
            source_script_revision_id="script-artifact",
        )

    continued = manuscript.model_copy(deep=True)
    next(page for page in continued.pages if page.page_id == "p2").continuation_of_page_id = (
        "p2-story-root"
    )
    content_changed = document.model_copy(deep=True)
    next(block for block in content_changed.blocks if block.block_id == "b5").payload[
        "markdown"
    ] = "证据解释要先标出观察，再区分推断与结论。"
    with pytest.raises(V6BuildError, match="ppt_manuscript_source_pagination_changed"):
        rebase_ppt_manuscript_source_blocks_v1(
            continued,
            refresh_document_revision(content_changed),
            source_script_revision_id="script-pagination",
        )


@pytest.mark.asyncio
async def test_targeted_manuscript_regeneration_preserves_other_pages_and_records_accepted_assets() -> None:
    document = _cross_subject_document()
    _graph, _template, _story, _visual, manuscript = (
        _strict_manuscript_fixture(document)
    )
    eligible = [
        page for page in manuscript.pages
        if page.page_type not in {"cover", "agenda", "summary"}
        and not page.continuation_of_page_id
        and len(page.visible_copy) == len([
            region for region in page.regions if region.content_kind != "notes"
        ])
    ]
    target = eligible[0]
    before = manuscript.model_dump(mode="json")
    requests = []

    async def planner(request):
        requests.append(request)
        return _regenerated_page_response(
            target,
            question_ids=["q-approved"],
            visual_ids=["visual-accepted"],
        )

    revised = await regenerate_ppt_manuscript_pages_v1(
        manuscript,
        target_page_ids=[target.page_id],
        ai_planner=planner,
        accepted_question_bank_items=[{"question_id": "q-approved"}],
        accepted_visual_expressions=[{"representation_id": "visual-accepted"}],
    )

    assert manuscript.model_dump(mode="json") == before
    assert len(requests) == 1
    assert requests[0]["constraints"]["target_page_id"] == target.page_id
    revised_target = next(page for page in revised.pages if page.page_id == target.page_id)
    assert revised_target.question_bank_item_ids == ["q-approved"]
    assert revised_target.shared_visual_expression_ids == ["visual-accepted"]
    assert revised_target.composition_notes.endswith("局部重生成后复核")
    assert [
        page.model_dump(mode="json") for page in revised.pages
        if page.page_id != target.page_id
    ] == [
        page.model_dump(mode="json") for page in manuscript.pages
        if page.page_id != target.page_id
    ]


@pytest.mark.asyncio
async def test_targeted_regeneration_normalizes_provider_brief_and_preserves_artifact_regions() -> None:
    document = _cross_subject_document()
    _graph, _template, _story, _visual, manuscript = (
        _strict_manuscript_fixture(document)
    )
    target = next(
        page for page in manuscript.pages
        if any(region.content_kind == "table" for region in page.regions)
        and sum(region.content_kind == "body" for region in page.regions) == 1
    )
    original_table = next(
        region.content for region in target.regions if region.content_kind == "table"
    )
    original_body = next(
        region.content for region in target.regions if region.content_kind == "body"
    )
    body_parts = original_body.split("\n\n")
    requests = []

    async def planner(request):
        requests.append(request)
        response = _regenerated_page_response(target)
        response["narrative_brief"] = {
            "schema_version": "slide_narrative_brief_v1",
            "central_question": "怎样依据现场证据形成结论？",
            "learning_path": [
                {"step": 1, "content": "先区分观察与推断"},
                {"step": 2, "content": "再核对采样条件"},
            ],
            "observable_checkpoints": [
                {"checkpoint": "能够指出记录中的观察事实"},
            ],
            "chapter_time_budget_minutes": 20,
            "must_include_source_block_ids": list(target.source_script_block_ids),
        }
        response["pages"][0]["visible_copy"] = body_parts
        return response

    revised = await regenerate_ppt_manuscript_pages_v1(
        manuscript,
        target_page_ids=[target.page_id],
        ai_planner=planner,
    )

    revised_target = next(
        page for page in revised.pages if page.page_id == target.page_id
    )
    assert requests[0]["constraints"]["editable_visible_region_count"] == 1
    assert next(
        region.content
        for region in revised_target.regions
        if region.content_kind == "table"
    ) == original_table
    assert next(
        region.content
        for region in revised_target.regions
        if region.content_kind == "body"
    ) == "\n\n".join(body_parts)


@pytest.mark.asyncio
async def test_targeted_manuscript_regeneration_is_atomic_and_rejects_unconfirmed_assets() -> None:
    document = _cross_subject_document()
    _graph, _template, _story, _visual, manuscript = (
        _strict_manuscript_fixture(document)
    )
    eligible = [
        page for page in manuscript.pages
        if page.page_type not in {"cover", "agenda", "summary"}
        and not page.continuation_of_page_id
        and len(page.visible_copy) == len([
            region for region in page.regions if region.content_kind != "notes"
        ])
    ]
    assert len(eligible) >= 2
    targets = eligible[:2]
    before = manuscript.model_dump(mode="json")

    async def planner(request):
        page_id = request["constraints"]["target_page_id"]
        page = next(item for item in targets if item.page_id == page_id)
        return _regenerated_page_response(
            page,
            question_ids=(
                ["q-approved"] if page is targets[0] else ["q-unconfirmed"]
            ),
        )

    with pytest.raises(
        V6BuildError,
        match="ppt_manuscript_question_binding_unconfirmed",
    ):
        await regenerate_ppt_manuscript_pages_v1(
            manuscript,
            target_page_ids=[page.page_id for page in targets],
            ai_planner=planner,
            accepted_question_bank_items=[{"question_id": "q-approved"}],
        )

    assert manuscript.model_dump(mode="json") == before

    locked = revise_ppt_manuscript_v1(manuscript, [{
        "page_id": targets[0].page_id,
        "teacher_locked": True,
    }])
    with pytest.raises(V6BuildError, match="ppt_manuscript_target_locked"):
        await regenerate_ppt_manuscript_pages_v1(
            locked,
            target_page_ids=[targets[0].page_id],
            ai_planner=planner,
        )


def test_manuscript_is_frozen_before_deck_compilation() -> None:
    document = _cross_subject_document()
    graph, template, story = _valid_story(document)
    visual = SlideVisualPlanV2(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        decisions=[SlideVisualDecisionV2(
            page_id=page.page_id,
            decision="table" if page.template_layout_id.endswith("/evidence-table") else "text_native",
            source_block_ids=page.source_block_ids,
            resolved_template_layout_id=page.template_layout_id,
        ) for page in story.pages],
    )

    manuscript = compile_ppt_manuscript_v1(
        document,
        graph,
        story,
        visual,
        template,
        source_lesson_plan_revision_id="plan-r1",
        source_script_revision_id="script-r1",
    )

    assert manuscript.quality_status == "passed"
    assert all(page.page_goal and page.primary_claim for page in manuscript.pages)
    assert all(page.regions and page.speaker_notes for page in manuscript.pages)
    deck = compile_slide_deck_v6_from_manuscript(
        document,
        graph,
        manuscript,
        template,
    )
    assert validate_deck_matches_ppt_manuscript_v1(deck, manuscript)
    assert [page.title for page in deck.pages] == [
        page.title for page in manuscript.pages
    ]


def test_manuscript_quality_rejects_teacher_delivery_cues_on_canvas() -> None:
    document = _cross_subject_document()
    graph, template, story = _valid_story(document)
    visual = SlideVisualPlanV2(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        decisions=[SlideVisualDecisionV2(
            page_id=page.page_id,
            decision="table" if page.template_layout_id.endswith("/evidence-table") else "text_native",
            source_block_ids=page.source_block_ids,
            resolved_template_layout_id=page.template_layout_id,
        ) for page in story.pages],
    )
    manuscript = compile_ppt_manuscript_v1(
        document,
        graph,
        story,
        visual,
        template,
    )
    manuscript.pages[0].visible_copy = ["板书并等待学习者回答。"]

    issues = _ppt_manuscript_quality_issues(manuscript.pages)

    assert any(
        issue.code == "ppt_manuscript_delivery_cue_visible"
        for issue in issues
    )


def test_manuscript_quality_rejects_production_instructions_as_titles() -> None:
    document = _cross_subject_document()
    graph, template, story = _valid_story(document)
    visual = SlideVisualPlanV2(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        decisions=[SlideVisualDecisionV2(
            page_id=page.page_id,
            decision="table" if page.template_layout_id.endswith("/evidence-table") else "text_native",
            source_block_ids=page.source_block_ids,
            resolved_template_layout_id=page.template_layout_id,
        ) for page in story.pages],
    )
    manuscript = compile_ppt_manuscript_v1(
        document,
        graph,
        story,
        visual,
        template,
    )
    manuscript.pages[0].title = "给出 3 道练习题"

    issues = _ppt_manuscript_quality_issues(manuscript.pages)

    assert any(
        issue.code == "ppt_manuscript_title_not_audience_ready"
        for issue in issues
    )


def test_manuscript_quality_allows_progressive_matrices_in_one_continuation_family() -> None:
    document = _cross_subject_document()
    graph, template, story = _valid_story(document)
    visual = SlideVisualPlanV2(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        decisions=[SlideVisualDecisionV2(
            page_id=page.page_id,
            decision="table" if page.template_layout_id.endswith("/evidence-table") else "text_native",
            source_block_ids=page.source_block_ids,
            resolved_template_layout_id=page.template_layout_id,
        ) for page in story.pages],
    )
    manuscript = compile_ppt_manuscript_v1(
        document,
        graph,
        story,
        visual,
        template,
    )
    base = manuscript.pages[0]
    first_formula = "$$\\begin{bmatrix}1&-1&2\\\\0&2&4\\\\0&4&8\\end{bmatrix}$$"
    next_formula = "$$\\begin{bmatrix}1&-1&2\\\\0&2&4\\\\0&0&0\\end{bmatrix}$$"
    formula_region = base.regions[0].model_copy(update={
        "content_kind": "formula",
        "content": first_formula,
    })
    body_region = base.regions[0].model_copy(update={
        "slot_id": "body",
        "content_kind": "body",
        "content": "第二行主元保持不变，只消去第三行对应元素。",
    })
    previous = base.model_copy(update={
        "page_id": "derivation",
        "visible_copy": [first_formula, body_region.content],
        "regions": [formula_region, body_region],
        "continuation_count": 2,
    })
    current = base.model_copy(update={
        "page_id": "derivation--continuation-2",
        "visible_copy": [next_formula],
        "regions": [formula_region.model_copy(update={"content": next_formula})],
        "continuation_of_page_id": "",
        "continuation_index": 2,
        "continuation_count": 2,
    })

    issues = _ppt_manuscript_quality_issues([previous, current])

    assert not any(
        issue.code == "ppt_manuscript_adjacent_content_repeated"
        for issue in issues
    )

    duplicated = current.model_copy(update={
        "visible_copy": [first_formula],
        "regions": [formula_region],
    })
    duplicate_issues = _ppt_manuscript_quality_issues([previous, duplicated])
    assert any(
        issue.code == "ppt_manuscript_adjacent_content_repeated"
        for issue in duplicate_issues
    )


def test_manuscript_quality_allows_formula_prompt_followed_by_explanation() -> None:
    document = _cross_subject_document()
    graph, template, story = _valid_story(document)
    visual = SlideVisualPlanV2(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        decisions=[SlideVisualDecisionV2(
            page_id=page.page_id,
            decision="table" if page.template_layout_id.endswith("/evidence-table") else "text_native",
            source_block_ids=page.source_block_ids,
            resolved_template_layout_id=page.template_layout_id,
        ) for page in story.pages],
    )
    manuscript = compile_ppt_manuscript_v1(
        document,
        graph,
        story,
        visual,
        template,
    )
    base = manuscript.pages[0]
    formula = "$$\\begin{bmatrix}0&3&-2\\\\2&-1&4\\\\0&6&-4\\end{bmatrix}$$"
    formula_region = base.regions[0].model_copy(update={
        "content_kind": "formula",
        "content": formula,
    })
    explanation = (
        "首列主元为零时必须先交换行，使首行获得非零主元，"
        "再按主元从左至右的顺序消去下方元素并复核阶梯结构。"
    )
    body_region = base.regions[0].model_copy(update={
        "slot_id": "body",
        "content_kind": "body",
        "content": explanation,
    })
    prompt = base.model_copy(update={
        "page_id": "prompt",
        "visible_copy": [formula],
        "regions": [formula_region],
    })
    feedback = base.model_copy(update={
        "page_id": "feedback",
        "visible_copy": [formula, explanation],
        "regions": [formula_region, body_region],
    })

    issues = _ppt_manuscript_quality_issues([prompt, feedback])

    assert not any(
        issue.code == "ppt_manuscript_adjacent_content_repeated"
        for issue in issues
    )


def test_deck_compilation_rejects_a_manuscript_changed_after_freeze() -> None:
    document = _cross_subject_document()
    graph, template, story = _valid_story(document)
    visual = SlideVisualPlanV2(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        decisions=[SlideVisualDecisionV2(
            page_id=page.page_id,
            decision="table" if page.template_layout_id.endswith("/evidence-table") else "text_native",
            source_block_ids=page.source_block_ids,
            resolved_template_layout_id=page.template_layout_id,
        ) for page in story.pages],
    )
    manuscript = compile_ppt_manuscript_v1(
        document,
        graph,
        story,
        visual,
        template,
    )
    manuscript.pages[0].title = "未冻结的临时改写"

    with pytest.raises(V6BuildError, match="ppt_manuscript_revision_mismatch"):
        compile_slide_deck_v6_from_manuscript(
            document,
            graph,
            manuscript,
            template,
        )


def test_story_plan_rejects_missing_blocks_unknown_sources_and_legacy_layouts() -> None:
    document = _cross_subject_document()
    graph, template, story = _valid_story(document)

    validate_slide_story_plan_v3(story, graph, template)

    missing = story.model_copy(deep=True)
    missing.batches[0].pages[0].source_block_ids.remove("b2")
    with pytest.raises(V6BuildError, match="story_course_block_coverage_incomplete"):
        validate_slide_story_plan_v3(missing, graph, template)

    unknown = story.model_copy(deep=True)
    unknown.batches[0].pages[0].source_block_ids.append("unknown-block")
    with pytest.raises(V6BuildError, match="story_unknown_source_id"):
        validate_slide_story_plan_v3(unknown, graph, template)

    legacy = story.model_copy(deep=True)
    legacy.batches[0].pages[0].template_layout_id = "two-column"
    with pytest.raises(V6BuildError, match="template_layout_unavailable"):
        validate_slide_story_plan_v3(legacy, graph, template)


def test_final_compilation_uses_formal_section_title_for_objective_opening() -> None:
    document = refresh_document_revision(CourseDocument(
        course_id="teacher-physics-title",
        title="牛顿第二定律",
        sections=[CourseSection(
            section_id="lesson-1",
            title="1.1 力、质量与加速度的关系",
            position=0,
        )],
        blocks=[_block(
            "lesson-objective",
            "lesson-1",
            0,
            role="objective",
            text="能够判断力、质量和加速度之间的定量关系。",
        )],
    ))
    graph, template, story = _valid_story(document)
    story.batches[0].pages[0].title = "能够判断力、质量"

    prepared = prepare_story_plan_for_final_compilation(story, graph, template)

    assert prepared.pages[0].title == "1.1 力、质量与加速度的关系"


def test_story_plan_rejects_untraceable_factual_tokens() -> None:
    document = _cross_subject_document()
    graph, template, story = _valid_story(document)
    story.batches[0].pages[0].summary = "调查准确率达到 99.9%。" * 12

    with pytest.raises(V6BuildError, match="story_unsupported_fact"):
        validate_slide_story_plan_v3(story, graph, template)


def test_story_plan_accepts_a_source_file_identifier_without_its_extension() -> None:
    document = refresh_document_revision(CourseDocument(
        course_id="generic-field-automation",
        title="Field evidence automation",
        sections=[CourseSection(section_id="field", title="Audit records", position=0)],
        blocks=[_block(
            "runner-source",
            "field",
            0,
            role="example",
            text=(
                "Save FieldAuditRunner.py before the audit. "
                "FieldAuditRunner.py checks every source row and reports missing evidence."
            ),
        )],
    ))
    graph, template, story = _valid_story(document)
    story.batches[0].pages[0].title = "FieldAuditRunner checks every source row"
    story.batches[0].pages[0].summary = (
        "Save FieldAuditRunner before the audit. FieldAuditRunner checks every "
        "source row and reports missing evidence before the audit."
    )

    validate_slide_story_plan_v3(story, graph, template)


def test_story_plan_rejects_ungrounded_semantic_claim_without_numbers() -> None:
    document = _cross_subject_document()
    graph, template, story = _valid_story(document)
    story.batches[0].pages[0].summary = "采用量子纠缠协议完成远程身份认证。" * 10

    with pytest.raises(V6BuildError, match="story_unsupported_semantic_claim"):
        validate_slide_story_plan_v3(story, graph, template)


def test_story_plan_rejects_an_ungrounded_visible_title() -> None:
    document = _cross_subject_document()
    graph, template, story = _valid_story(document)
    story.batches[0].pages[0].title = "Quantum credential exchange"

    with pytest.raises(V6BuildError, match="story_unsupported_title"):
        validate_slide_story_plan_v3(story, graph, template)


def test_story_plan_rejects_an_empty_visible_title() -> None:
    document = _cross_subject_document()
    graph, template, story = _valid_story(document)
    story.batches[0].pages[0].title = "   "

    with pytest.raises(V6BuildError, match="story_title_missing"):
        validate_slide_story_plan_v3(story, graph, template)


def test_story_plan_rejects_a_title_that_ends_on_a_dangling_connector() -> None:
    document = _cross_subject_document()
    graph, template, story = _valid_story(document)
    story.batches[0].pages[0].title = "生态承载力与"

    with pytest.raises(V6BuildError, match="story_title_incomplete"):
        validate_slide_story_plan_v3(story, graph, template)


def test_story_plan_rejects_a_title_that_ends_mid_enumeration() -> None:
    document = _cross_subject_document()
    graph, template, story = _valid_story(document)
    story.batches[0].pages[0].title = "依次给出二阶、三阶"

    with pytest.raises(V6BuildError, match="story_title_incomplete"):
        validate_slide_story_plan_v3(story, graph, template)


def test_story_plan_rejects_a_structural_label_instead_of_a_specific_title() -> None:
    document = refresh_document_revision(CourseDocument(
        course_id="generic-field-title-specificity",
        title="Field evidence",
        sections=[CourseSection(section_id="field", title="Field", position=0)],
        blocks=[_block(
            "field-evidence",
            "field",
            0,
            role="concept",
            text=(
                "## 项目名称：湿地观察证据链\n"
                "湿地观察必须记录地点、时间、天气和观察者，并把结论绑定到原始证据。"
            ),
        )],
    ))
    graph, template, story = _valid_story(document)
    story.batches[0].pages[0].title = "项目名称"

    with pytest.raises(V6BuildError, match="story_title_lacks_specificity"):
        validate_slide_story_plan_v3(story, graph, template)


def test_story_plan_rejects_an_internal_lesson_module_label_as_title() -> None:
    document = _cross_subject_document()
    graph, template, story = _valid_story(document)
    story.batches[0].pages[0].title = "核心教学"

    with pytest.raises(V6BuildError, match="story_title_lacks_specificity"):
        validate_slide_story_plan_v3(story, graph, template)


def test_story_plan_rejects_a_production_instruction_as_title() -> None:
    document = _cross_subject_document()
    graph, template, story = _valid_story(document)
    story.batches[0].pages[0].title = "给出 3 道练习题"

    with pytest.raises(V6BuildError, match="story_title_lacks_specificity"):
        validate_slide_story_plan_v3(story, graph, template)


def test_story_plan_rejects_an_underfilled_editorial_body_when_source_is_rich() -> None:
    document = refresh_document_revision(CourseDocument(
        course_id="generic-field-density",
        title="Field evidence",
        sections=[CourseSection(section_id="field", title="Field", position=0)],
        blocks=[_block(
            "field-evidence",
            "field",
            0,
            role="concept",
            text=(
                "## 湿地观察证据链\n"
                "观察前先冻结地点、时间、天气、观察者和采样批次；记录后逐项核对原始证据、"
                "验收标准、审核修订和异常原因，确保结论没有用解释替代事实。"
            ) * 3,
        )],
    ))
    graph, template, story = _valid_story(document)
    story.batches[0].pages[0].title = "湿地观察证据链"
    story.batches[0].pages[0].summary = "记录地点、时间和天气。"

    with pytest.raises(V6BuildError, match="story_page_underfilled"):
        validate_slide_story_plan_v3(story, graph, template)


def test_final_compiler_uses_frozen_source_when_editorial_summary_underfills() -> None:
    source = (
        "Before a wetland survey begins, observers freeze the location, time, "
        "weather, instrument calibration, sampling window, and evidence owner. "
        "After collection, the team compares every record with the acceptance "
        "criterion, documents anomalies, and keeps interpretation separate from "
        "the signed field evidence."
    )
    document = refresh_document_revision(CourseDocument(
        course_id="generic-field-final-density",
        title="Field evidence",
        sections=[CourseSection(
            section_id="field",
            title="Wetland evidence review",
            position=0,
        )],
        blocks=[_block(
            "field-evidence",
            "field",
            0,
            role="concept",
            text=source,
        )],
    ))
    graph, template, story = _valid_story(document)
    page = story.batches[0].pages[0]
    page.title = "Wetland evidence review"
    page.summary = "Record the evidence."
    visual = SlideVisualPlanV2(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        decisions=[SlideVisualDecisionV2(
            page_id=page.page_id,
            decision="text_native",
            source_block_ids=page.source_block_ids,
            resolved_template_layout_id=page.template_layout_id,
        )],
    )
    deck = compile_slide_deck_v6(document, graph, story, visual, template)

    compiled_page = next(item for item in deck.pages if item.page_id == page.page_id)
    body = next(
        region.content
        for region in compiled_page.regions
        if region.slot_id == "body"
    )
    body_slot = next(
        slot
        for slot in template.get_layout(page.template_layout_id).slots
        if slot.slot_id == "body"
    )
    assert body != "Record the evidence."
    assert len(body) >= body_slot.min_chars
    assert body in source


def test_story_plan_rejects_title_over_selected_template_capacity() -> None:
    document = _cross_subject_document()
    graph, template, story = _valid_story(document)
    page = story.batches[0].pages[0]
    layout = template.get_layout(page.template_layout_id)
    assert layout is not None
    title_capacity = next(
        slot.max_chars for slot in layout.slots if slot.slot_kind == "title"
    )
    source_text = graph.units[0].source_text
    page.title = source_text[: title_capacity + 1]
    assert len(page.title) > title_capacity

    with pytest.raises(V6BuildError, match="story_title_capacity_exceeded"):
        validate_slide_story_plan_v3(story, graph, template)


def test_story_plan_rejects_a_layout_before_its_required_text_slot_materializes_empty() -> None:
    document = refresh_document_revision(
        CourseDocument(
            course_id="generic-observation-check",
            title="Observation check",
            sections=[
                CourseSection(
                    section_id="check",
                    title="Check the record",
                    position=0,
                )
            ],
            blocks=[
                _block(
                    "check-rows",
                    "check",
                    0,
                    role="activity",
                    kind="review_checkpoint",
                    text="| Time | Recorded |\n| Habitat | Described |",
                )
            ],
        )
    )
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    unit = graph.units[0]
    story = SlideStoryPlanV3(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        batches=[
            SlideStoryBatchV3(
                batch_id="generic-slot-check",
                chapter_id="check",
                provider="fixture-provider",
                model="fixture-model",
                duration_ms=1,
                attempts=1,
                validation_status="passed",
                pages=[
                    SlideStoryPageV3(
                        page_id="empty-task-slot",
                        teaching_unit_id=unit.teaching_unit_id,
                        template_layout_id=template.layout_id("practice-prompt"),
                        title="Check the record",
                        summary="",
                        source_block_ids=unit.primary_block_ids,
                        page_ordinal=0,
                    )
                ],
            )
        ],
    )

    with pytest.raises(V6BuildError, match="template_required_slot_unfilled"):
        validate_slide_story_plan_v3(story, graph, template)


def test_practice_layout_rejects_unrelated_concept_and_misconception_blocks() -> None:
    document = refresh_document_revision(CourseDocument(
        course_id="generic-field-practice-boundary",
        title="Field evidence review",
        sections=[CourseSection(section_id="field", title="Inspect evidence", position=0)],
        blocks=[
            _block("concept", "field", 0, role="concept", text="A signed record preserves the observation context."),
            _block("reasoning", "field", 1, role="reasoning", text="Separate the observation from its interpretation."),
            _block("activity", "field", 2, role="activity", text="1. Inspect the record.\n2. Verify the signature."),
            _block("misconception", "field", 3, role="misconception", text="Do not replace missing evidence with an assumption."),
        ],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    unit = graph.units[0]
    page = SlideStoryPageV3(
        page_id="overloaded-practice",
        teaching_unit_id=unit.teaching_unit_id,
        template_layout_id=template.layout_id("practice-prompt"),
        title="Inspect the record",
        source_block_ids=unit.primary_block_ids,
        page_ordinal=0,
    )
    story = SlideStoryPlanV3(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        batches=[SlideStoryBatchV3(
            batch_id="story-field",
            chapter_id="field",
            provider="fixture",
            model="fixture",
            duration_ms=1,
            attempts=1,
            validation_status="passed",
            pages=[page],
        )],
    )

    with pytest.raises(V6BuildError, match="template_source_slot_role_mismatch"):
        validate_slide_story_plan_v3(story, graph, template)


def test_ordered_activity_materializes_as_distinct_source_bound_steps() -> None:
    document = refresh_document_revision(CourseDocument(
        course_id="generic-field-procedure",
        title="Field sample handling",
        sections=[CourseSection(
            section_id="field-procedure",
            title="Preserve the sample chain",
            position=0,
        )],
        blocks=[CourseBlock(
            block_id="handling-steps",
            section_id="field-procedure",
            position=0,
            role="activity",
            payload={"markdown": (
                "**Procedure record**\n\n"
                "Follow these operations in order:\n\n"
                "1. **Collect the sample**\n"
                "   - Record the collection time.\n"
                "2. **Seal the container**\n"
                "   - Check that the lid is secure.\n"
                "3. **Label the evidence**\n"
                "   - Copy the sample identifier exactly.\n"
                "4. **Transfer the package**\n"
                "   - Obtain the receiver signature."
            )},
        )],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    unit = graph.units[0]
    page = SlideStoryPageV3(
        page_id="field-procedure-page",
        teaching_unit_id=unit.teaching_unit_id,
        template_layout_id=template.layout_id("practice-prompt"),
        title="Preserve the sample chain",
        source_block_ids=unit.primary_block_ids,
        page_ordinal=0,
    )
    story = SlideStoryPlanV3(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        batches=[SlideStoryBatchV3(
            batch_id="story-field-procedure",
            chapter_id="field-procedure",
            provider="fixture",
            model="fixture",
            duration_ms=1,
            attempts=1,
            validation_status="passed",
            pages=[page],
        )],
    )
    visual = SlideVisualPlanV2(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        decisions=[SlideVisualDecisionV2(
            page_id=page.page_id,
            decision="text_native",
            source_block_ids=page.source_block_ids,
            resolved_template_layout_id=page.template_layout_id,
        )],
    )

    deck = compile_slide_deck_v6(document, graph, story, visual, template)
    region = next(
        region
        for region in deck.pages[0].regions
        if region.slot_id == "task"
    )
    steps = region.content.splitlines()

    assert region.content_kind == "steps"
    assert len(steps) == 4
    assert [step.split(":", 1)[0] for step in steps] == [
        "Collect the sample",
        "Seal the container",
        "Label the evidence",
        "Transfer the package",
    ]
    assert "Procedure record" not in region.content
    assert "Follow these operations" not in region.content


def test_ordered_activity_keeps_complete_source_details_without_ellipsis() -> None:
    document = refresh_document_revision(CourseDocument(
        course_id="generic-field-procedure-density",
        title="Field specimen workflow",
        sections=[CourseSection(
            section_id="field-procedure",
            title="Preserve the specimen chain",
            position=0,
        )],
        blocks=[CourseBlock(
            block_id="specimen-steps",
            section_id="field-procedure",
            position=0,
            role="activity",
            payload={"markdown": (
                "Follow these operations in order:\n\n"
                "1. **Prepare the station**\n"
                "   - Record the site.\n"
                "   - Confirm the clean surface.\n"
                "2. **Collect the sample**\n"
                "   - Match the field label to the signed source record before collection begins.\n"
                "   - Preserve the original sequence while transferring the sample.\n"
                "3. **Seal the container**\n"
                "   - Check the lid, tamper mark, temperature and current custody condition.\n"
                "   - Stop the transfer if any required field is missing.\n"
                "4. **Label the evidence**\n"
                "   - Copy the complete specimen identifier and collection window exactly.\n"
                "   - Keep the source form beside the package for independent review.\n"
                "5. **Transfer the package**\n"
                "   - Record the receiver, handoff time, route and storage condition.\n"
                "   - Obtain the receiver signature before releasing custody."
            )},
        )],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    unit = graph.units[0]
    page = SlideStoryPageV3(
        page_id="field-procedure-density-page",
        teaching_unit_id=unit.teaching_unit_id,
        template_layout_id=template.layout_id("practice-prompt"),
        title="Preserve the specimen chain",
        source_block_ids=unit.primary_block_ids,
        page_ordinal=0,
    )
    story = SlideStoryPlanV3(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        batches=[SlideStoryBatchV3(
            batch_id="story-field-procedure-density",
            chapter_id="field-procedure",
            provider="fixture",
            model="fixture",
            duration_ms=1,
            attempts=1,
            validation_status="passed",
            pages=[page],
        )],
    )
    visual = SlideVisualPlanV2(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        decisions=[SlideVisualDecisionV2(
            page_id=page.page_id,
            decision="text_native",
            source_block_ids=page.source_block_ids,
            resolved_template_layout_id=page.template_layout_id,
        )],
    )

    deck = compile_slide_deck_v6(document, graph, story, visual, template)
    task_regions = [
        region.content
        for compiled_page in deck.pages
        for region in compiled_page.regions
        if region.slot_id == "task"
    ]
    visible_steps = "\n".join(task_regions)

    assert len(deck.pages) > 1
    assert sum(len(content.splitlines()) for content in task_regions) == 5
    assert "…" not in visible_steps
    assert ".;" not in visible_steps
    assert "。；" not in visible_steps
    assert all(
        not line.rstrip().endswith((";", "；", ":", "："))
        for content in task_regions
        for line in content.splitlines()
    )
    for source_detail in (
        "Record the site",
        "Confirm the clean surface",
        "Match the field label to the signed source record before collection begins",
        "Preserve the original sequence while transferring the sample",
        "Check the lid, tamper mark, temperature and current custody condition",
        "Stop the transfer if any required field is missing",
        "Copy the complete specimen identifier and collection window exactly",
        "Keep the source form beside the package for independent review",
        "Record the receiver, handoff time, route and storage condition",
        "Obtain the receiver signature before releasing custody",
    ):
        assert source_detail in visible_steps


def test_visual_plan_degrades_only_optional_visuals() -> None:
    document = _cross_subject_document()
    graph, template, story = _valid_story(document)
    plan = SlideVisualPlanV2(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        decisions=[
            SlideVisualDecisionV2(
                page_id="p1",
                decision="text_native",
                source_block_ids=["b1", "b2", "b3", "b4"],
                resolved_template_layout_id=story.pages[0].template_layout_id,
                degraded=True,
                degradation_reason="visual_provider_unavailable",
            ),
            SlideVisualDecisionV2(
                page_id="p2",
                decision="table",
                source_block_ids=["b5", "b6", "b7"],
                resolved_template_layout_id=template.layout_id("evidence-table"),
            ),
        ],
    )

    result = validate_slide_visual_plan_v2(plan, story, graph, template)
    assert result == "v6_needs_manual_edit"

    invalid = plan.model_copy(deep=True)
    invalid.decisions[1].decision = "text_native"
    with pytest.raises(V6BuildError, match="required_subject_representation_missing"):
        validate_slide_visual_plan_v2(invalid, story, graph, template)


def test_final_deck_has_full_notes_and_template_native_layout_ids() -> None:
    document = _cross_subject_document()
    graph, template, story = _valid_story(document)
    visual = SlideVisualPlanV2(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        decisions=[
            SlideVisualDecisionV2(
                page_id=page.page_id,
                decision="table" if page.page_id == "p2" else "text_native",
                source_block_ids=page.source_block_ids,
                resolved_template_layout_id=page.template_layout_id,
            )
            for page in story.pages
        ],
    )

    deck = compile_slide_deck_v6(document, graph, story, visual, template)

    assert deck.status == "v6_ready"
    assert deck.quality.formal_block_visible_coverage == 1.0
    assert deck.quality.full_text_note_binding == 1.0
    assert all(page.resolved_layout.startswith("qizhi-classroom-v2@") for page in deck.pages)
    assert all(
        page.speaker_notes.source_blocks or page.speaker_notes.source_section_ids
        for page in deck.pages
    )
    assert {item.block_id for page in deck.pages for item in page.speaker_notes.source_blocks} == {
        "b1", "b2", "b3", "b4", "b5", "b6", "b7",
    }
    table_note = next(
        item
        for page in deck.pages
        for item in page.speaker_notes.source_blocks
        if item.block_id == "b6"
    )
    assert table_note.source_kind == "table"
    assert table_note.source_payload == next(
        block.payload for block in document.blocks if block.block_id == "b6"
    )


def test_visible_slot_content_expresses_every_bound_source_block() -> None:
    document = refresh_document_revision(
        CourseDocument(
            course_id="generic-dense-source",
            title="现场记录",
            sections=[CourseSection(section_id="section", title="证据", position=0)],
            blocks=[
                _block(
                    "long-context", "section", 0, role="concept",
                    text="观察前先冻结对象与时间范围，避免记录口径变化。" * 24,
                ),
                _block(
                    "required-conclusion", "section", 1, role="reasoning",
                    text="最终结论必须保留：区分观察事实与解释。",
                ),
            ],
        )
    )
    graph, template, story = _valid_story(document)
    visual = SlideVisualPlanV2(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        decisions=[SlideVisualDecisionV2(
            page_id=story.pages[0].page_id,
            decision="text_native",
            source_block_ids=story.pages[0].source_block_ids,
            resolved_template_layout_id=story.pages[0].template_layout_id,
        )],
    )

    deck = compile_slide_deck_v6(document, graph, story, visual, template)
    visible = "\n".join(
        region.content
        for page in deck.pages
        for region in page.regions
    )

    assert "区分观察事实与解释" in visible
    assert deck.quality.formal_block_visible_coverage == 1.0


def test_story_plan_rejects_duplicate_page_titles() -> None:
    document = _cross_subject_document()
    graph, template, story = _valid_story(document)
    story.batches[0].pages[1].title = story.batches[0].pages[0].title

    with pytest.raises(V6BuildError, match="duplicate_slide_title"):
        validate_slide_story_plan_v3(story, graph, template)


def test_story_plan_rejects_duplicate_page_ids() -> None:
    document = _cross_subject_document()
    graph, template, story = _valid_story(document)
    story.batches[0].pages[1].page_id = story.batches[0].pages[0].page_id

    with pytest.raises(V6BuildError, match="story_duplicate_page_id"):
        validate_slide_story_plan_v3(story, graph, template)


def test_visual_image_requires_a_source_asset_reference() -> None:
    document = refresh_document_revision(
        CourseDocument(
            course_id="generic-field-image",
            title="现场证据",
            sections=[CourseSection(section_id="section", title="记录", position=0)],
            blocks=[CourseBlock(
                block_id="field-photo",
                section_id="section",
                position=0,
                role="example",
                kind="image",
                payload={"markdown": "河岸样方的现场照片。"},
                asset_refs=[],
            )],
        )
    )
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    page = SlideStoryPageV3(
        page_id="image-page",
        teaching_unit_id=graph.units[0].teaching_unit_id,
        template_layout_id=template.layout_id("evidence-figure"),
        title="现场照片证据",
        source_block_ids=["field-photo"],
        page_ordinal=0,
    )
    story = SlideStoryPlanV3(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        batches=[SlideStoryBatchV3(
            batch_id="story-1", chapter_id="section", provider="fixture", model="fixture",
            duration_ms=1, attempts=1, validation_status="passed", pages=[page],
        )],
    )
    visual = SlideVisualPlanV2(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        decisions=[SlideVisualDecisionV2(
            page_id="image-page",
            decision="image",
            source_block_ids=["field-photo"],
            resolved_template_layout_id=page.template_layout_id,
        )],
    )

    with pytest.raises(V6BuildError, match="visual_source_asset_missing"):
        validate_slide_visual_plan_v2(visual, story, graph, template)


def test_diagram_decision_requires_source_bound_nodes_and_edges() -> None:
    document = refresh_document_revision(
        CourseDocument(
            course_id="generic-process-diagram",
            title="样本核验流程",
            sections=[CourseSection(section_id="section", title="核验", position=0)],
            blocks=[_block(
                "flow", "section", 0, role="reasoning", kind="diagram",
                text="先采集样本，再核对时间与地点，最后形成结论。",
            )],
        )
    )
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    page = SlideStoryPageV3(
        page_id="diagram-page",
        teaching_unit_id=graph.units[0].teaching_unit_id,
        template_layout_id=template.layout_id("evidence-diagram"),
        title="样本核验流程",
        source_block_ids=["flow"],
        page_ordinal=0,
    )
    story = SlideStoryPlanV3(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        batches=[SlideStoryBatchV3(
            batch_id="story-1", chapter_id="section", provider="fixture", model="fixture",
            duration_ms=1, attempts=1, validation_status="passed", pages=[page],
        )],
    )
    missing = SlideVisualPlanV2(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        decisions=[SlideVisualDecisionV2(
            page_id="diagram-page", decision="diagram", source_block_ids=["flow"],
            resolved_template_layout_id=page.template_layout_id,
        )],
    )

    with pytest.raises(V6BuildError, match="visual_diagram_payload_missing"):
        validate_slide_visual_plan_v2(missing, story, graph, template)

    valid = missing.model_copy(deep=True)
    valid.decisions[0].visual_payload = {
        "nodes": [
            {"node_id": "collect", "label": "采集样本", "source_block_ids": ["flow"]},
            {"node_id": "verify", "label": "核对时间与地点", "source_block_ids": ["flow"]},
            {"node_id": "conclude", "label": "形成结论", "source_block_ids": ["flow"]},
        ],
        "edges": [
            {"source": "collect", "target": "verify", "label": "再"},
            {"source": "verify", "target": "conclude", "label": "最后"},
        ],
        "direction": "horizontal",
    }
    assert validate_slide_visual_plan_v2(valid, story, graph, template) == "v6_ready"

    generated_ellipsis = valid.model_copy(deep=True)
    generated_ellipsis.decisions[0].visual_payload["nodes"][0]["label"] = "采集样本…"
    with pytest.raises(V6BuildError, match="visual_diagram_label_unsupported"):
        validate_slide_visual_plan_v2(
            generated_ellipsis,
            story,
            graph,
            template,
        )


def test_diagram_labels_allow_anchored_paraphrase_within_the_bound_source_block() -> None:
    document = refresh_document_revision(
        CourseDocument(
            course_id="generic-editorial-diagram",
            title="Editorial evidence flow",
            sections=[CourseSection(section_id="section", title="Review", position=0)],
            blocks=[
                _block(
                    "review",
                    "section",
                    0,
                    role="concept",
                    text=(
                        "The operator checks the evidence record before publishing the result."
                    ),
                ),
                _block(
                    "archive",
                    "section",
                    1,
                    role="feedback",
                    text="The approved observation is archived after review.",
                ),
            ],
        )
    )
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    unit = graph.units[0]
    page = SlideStoryPageV3(
        page_id="diagram-page",
        teaching_unit_id=unit.teaching_unit_id,
        template_layout_id=template.layout_id("evidence-diagram"),
        title="Editorial evidence flow",
        source_block_ids=["review", "archive"],
        page_ordinal=0,
    )
    story = SlideStoryPlanV3(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        batches=[SlideStoryBatchV3(
            batch_id="story-1",
            chapter_id="section",
            provider="fixture",
            model="fixture",
            duration_ms=1,
            attempts=1,
            validation_status="passed",
            pages=[page],
        )],
    )
    visual = SlideVisualPlanV2(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        decisions=[SlideVisualDecisionV2(
            page_id=page.page_id,
            decision="diagram",
            source_block_ids=page.source_block_ids,
            resolved_template_layout_id=page.template_layout_id,
            visual_payload={
                "nodes": [
                    {
                        "node_id": "verify",
                        "label": "Verify the record",
                        "source_block_ids": ["review"],
                    },
                    {
                        "node_id": "publish",
                        "label": "Publish the result",
                        "source_block_ids": ["review"],
                    },
                ],
                "edges": [{"source": "verify", "target": "publish"}],
            },
        )],
    )

    assert validate_slide_visual_plan_v2(visual, story, graph, template) == "v6_ready"


def test_diagram_label_cannot_borrow_grounding_from_an_unbound_sibling_block() -> None:
    document = refresh_document_revision(
        CourseDocument(
            course_id="generic-source-bound-diagram",
            title="Observation handling",
            sections=[CourseSection(section_id="section", title="Handling", position=0)],
            blocks=[
                _block(
                    "collect",
                    "section",
                    0,
                    role="concept",
                    text="Collect the field sample and record its intake time.",
                ),
                _block(
                    "archive",
                    "section",
                    1,
                    role="feedback",
                    text="Archive the approved observation after review.",
                ),
            ],
        )
    )
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    unit = graph.units[0]
    page = SlideStoryPageV3(
        page_id="diagram-page",
        teaching_unit_id=unit.teaching_unit_id,
        template_layout_id=template.layout_id("evidence-diagram"),
        title="Observation handling",
        source_block_ids=["collect", "archive"],
        page_ordinal=0,
    )
    story = SlideStoryPlanV3(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        batches=[SlideStoryBatchV3(
            batch_id="story-1",
            chapter_id="section",
            provider="fixture",
            model="fixture",
            duration_ms=1,
            attempts=1,
            validation_status="passed",
            pages=[page],
        )],
    )
    visual = SlideVisualPlanV2(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        decisions=[SlideVisualDecisionV2(
            page_id=page.page_id,
            decision="diagram",
            source_block_ids=page.source_block_ids,
            resolved_template_layout_id=page.template_layout_id,
            visual_payload={
                "nodes": [
                    {
                        "node_id": "collect",
                        "label": "Archive the approved observation",
                        "source_block_ids": ["collect"],
                    },
                    {
                        "node_id": "archive",
                        "label": "Archive the approved observation",
                        "source_block_ids": ["archive"],
                    },
                ],
                "edges": [{"source": "collect", "target": "archive"}],
            },
        )],
    )

    with pytest.raises(V6BuildError, match="visual_diagram_label_unsupported"):
        validate_slide_visual_plan_v2(visual, story, graph, template)


def test_diagram_label_keeps_numbers_and_code_identifiers_strict() -> None:
    document = refresh_document_revision(
        CourseDocument(
            course_id="generic-identifier-diagram",
            title="Build review",
            sections=[CourseSection(section_id="section", title="Build", position=0)],
            blocks=[
                _block(
                    "build",
                    "section",
                    0,
                    role="concept",
                    text="Run the build pipeline and inspect the result.",
                )
            ],
        )
    )
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    unit = graph.units[0]
    page = SlideStoryPageV3(
        page_id="diagram-page",
        teaching_unit_id=unit.teaching_unit_id,
        template_layout_id=template.layout_id("evidence-diagram"),
        title="Build review",
        source_block_ids=["build"],
        page_ordinal=0,
    )
    story = SlideStoryPlanV3(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        batches=[SlideStoryBatchV3(
            batch_id="story-1",
            chapter_id="section",
            provider="fixture",
            model="fixture",
            duration_ms=1,
            attempts=1,
            validation_status="passed",
            pages=[page],
        )],
    )
    visual = SlideVisualPlanV2(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        decisions=[SlideVisualDecisionV2(
            page_id=page.page_id,
            decision="diagram",
            source_block_ids=page.source_block_ids,
            resolved_template_layout_id=page.template_layout_id,
            visual_payload={
                "nodes": [
                    {
                        "node_id": "run",
                        "label": "Run BuildPipelineV7",
                        "source_block_ids": ["build"],
                    },
                    {
                        "node_id": "inspect",
                        "label": "Inspect the result",
                        "source_block_ids": ["build"],
                    },
                ],
                "edges": [{"source": "run", "target": "inspect"}],
            },
        )],
    )

    with pytest.raises(V6BuildError, match="visual_diagram_label_unsupported"):
        validate_slide_visual_plan_v2(visual, story, graph, template)


def _artifact_deck_fixture(
    *,
    artifact_kind: str,
    artifact_text: str,
    block_kind: str | None = None,
) -> tuple[CourseDocument, object, object, SlideStoryPlanV3, SlideVisualPlanV2]:
    document = refresh_document_revision(
        CourseDocument(
            course_id=f"generic-{artifact_kind}-pagination",
            title="Generic evidence workflow",
            sections=[CourseSection(section_id="section", title="Evidence", position=0)],
            blocks=[
                _block(
                    "context",
                    "section",
                    0,
                    role="concept",
                    text="Read the evidence in source order and explain its observable result.",
                ),
                _block(
                    "artifact",
                    "section",
                    1,
                    role="example",
                    kind=block_kind or artifact_kind,
                    text=artifact_text,
                ),
                _block(
                    "interpretation",
                    "section",
                    2,
                    role="reasoning",
                    text="Use the displayed evidence to check the stated condition and result.",
                ),
            ],
        )
    )
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    layout_slug = "evidence-code" if artifact_kind == "code" else "evidence-table"
    page = SlideStoryPageV3(
        page_id="evidence-page",
        teaching_unit_id=graph.units[0].teaching_unit_id,
        template_layout_id=template.layout_id(layout_slug),
        title="Inspect the complete evidence",
        summary="Use the displayed evidence to check the stated condition and result.",
        source_block_ids=graph.units[0].primary_block_ids,
        page_ordinal=0,
    )
    story = SlideStoryPlanV3(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        batches=[SlideStoryBatchV3(
            batch_id="story-1",
            chapter_id="section",
            provider="fixture",
            model="fixture",
            duration_ms=1,
            attempts=1,
            validation_status="passed",
            pages=[page],
        )],
    )
    visual = SlideVisualPlanV2(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        decisions=[SlideVisualDecisionV2(
            page_id=page.page_id,
            decision=artifact_kind,
            source_block_ids=page.source_block_ids,
            resolved_template_layout_id=page.template_layout_id,
        )],
    )
    return document, graph, template, story, visual


def test_long_prose_paginates_complete_semantic_groups_without_silent_omission() -> None:
    paragraphs = [
        (
            f"Preserve complete source paragraph {index}: record the observable condition, "
            "explain the evidence boundary, and retain the stated verification result."
        )
        for index in range(1, 9)
    ]
    source = "\n\n".join(paragraphs)
    document = refresh_document_revision(CourseDocument(
        course_id="generic-prose-pagination",
        title="Source-complete explanation",
        sections=[CourseSection(
            section_id="section",
            title="Preserve complete source paragraphs",
            position=0,
        )],
        blocks=[_block(
            "complete-prose",
            "section",
            0,
            role="concept",
            text=source,
        )],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    page = SlideStoryPageV3(
        page_id="complete-prose-page",
        teaching_unit_id=graph.units[0].teaching_unit_id,
        template_layout_id=template.layout_id("content-stack"),
        title="Preserve complete source paragraphs",
        source_block_ids=["complete-prose"],
        page_ordinal=0,
    )
    story = SlideStoryPlanV3(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        batches=[SlideStoryBatchV3(
            batch_id="story-prose",
            chapter_id="section",
            provider="fixture",
            model="fixture",
            duration_ms=1,
            attempts=1,
            validation_status="passed",
            pages=[page],
        )],
    )
    visual = SlideVisualPlanV2(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        decisions=[SlideVisualDecisionV2(
            page_id=page.page_id,
            decision="text_native",
            source_block_ids=page.source_block_ids,
            resolved_template_layout_id=page.template_layout_id,
        )],
    )

    deck = compile_slide_deck_v6(document, graph, story, visual, template)
    visible_body = "\n\n".join(
        region.content
        for compiled_page in deck.pages
        for region in compiled_page.regions
        if region.content_kind == "body"
    )

    assert len(deck.pages) > 1
    assert "…" not in visible_body
    assert all(visible_body.count(paragraph) == 1 for paragraph in paragraphs)


def test_single_body_page_uses_validated_story_summary_and_keeps_source_in_notes() -> None:
    paragraphs = [
        (
            "Preserve the complete observation context, including the declared scope, "
            "recording condition, evidence boundary, and verification result."
        ),
        (
            "Separate the observable record from later interpretation so the learner can "
            "identify which statement is evidence and which statement is a conclusion."
        ),
        (
            "Finish by checking every stated acceptance condition and retaining the complete "
            "repair action for any missing or inconsistent field."
        ),
    ]
    source = "\n\n".join(paragraphs)
    document = refresh_document_revision(CourseDocument(
        course_id="generic-single-body-fidelity",
        title="Complete source projection",
        sections=[CourseSection(
            section_id="section",
            title="Preserve the complete observation context",
            position=0,
        )],
        blocks=[_block(
            "complete-body",
            "section",
            0,
            role="concept",
            text=source,
        )],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    page = SlideStoryPageV3(
        page_id="complete-body-page",
        teaching_unit_id=graph.units[0].teaching_unit_id,
        template_layout_id=template.layout_id("content-stack"),
        title="Preserve the complete observation context",
        summary=paragraphs[0],
        source_block_ids=["complete-body"],
        page_ordinal=0,
    )
    story = SlideStoryPlanV3(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        batches=[SlideStoryBatchV3(
            batch_id="story-complete-body",
            chapter_id="section",
            provider="fixture",
            model="fixture",
            duration_ms=1,
            attempts=1,
            validation_status="passed",
            pages=[page],
        )],
    )
    visual = SlideVisualPlanV2(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        decisions=[SlideVisualDecisionV2(
            page_id=page.page_id,
            decision="text_native",
            source_block_ids=page.source_block_ids,
            resolved_template_layout_id=page.template_layout_id,
        )],
    )

    deck = compile_slide_deck_v6(document, graph, story, visual, template)
    body = next(
        region.content
        for region in deck.pages[0].regions
        if region.content_kind == "body"
    )

    assert body == paragraphs[0]
    assert deck.pages[0].regions[0].metadata["story_projection"] == "validated"
    assert deck.pages[0].speaker_notes.source_blocks[0].full_text == source


def test_visual_summary_is_visible_while_full_source_remains_in_notes() -> None:
    paragraphs = [
        (
            "Collect field evidence and record the intake timestamp before any "
            "interpretation is added to the observation."
        ),
        (
            "Verify the timestamp, location, operator identity, and acceptance "
            "conditions while the original evidence remains visible."
        ),
        (
            "Compare the recorded result with the declared boundary, retain every "
            "exception, and describe the repair action without shortening it."
        ),
        (
            "Publish the result only after the complete source record can be traced "
            "through the diagram and every continuation page."
        ),
    ]
    source = "\n\n".join(paragraphs)
    document = refresh_document_revision(CourseDocument(
        course_id="generic-visual-summary-fidelity",
        title="Source-complete visual explanation",
        sections=[CourseSection(
            section_id="section",
            title="Evidence handling",
            position=0,
        )],
        blocks=[_block(
            "evidence-record",
            "section",
            0,
            role="concept",
            text=source,
        )],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    page = SlideStoryPageV3(
        page_id="visual-summary-page",
        teaching_unit_id=graph.units[0].teaching_unit_id,
        template_layout_id=template.layout_id("evidence-diagram"),
        title="Evidence handling flow",
        summary="Collect field evidence, verify the timestamp, and publish the result.",
        source_block_ids=["evidence-record"],
        page_ordinal=0,
    )
    story = SlideStoryPlanV3(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        batches=[SlideStoryBatchV3(
            batch_id="story-visual-summary",
            chapter_id="section",
            provider="fixture",
            model="fixture",
            duration_ms=1,
            attempts=1,
            validation_status="passed",
            pages=[page],
        )],
    )
    visual = SlideVisualPlanV2(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        decisions=[SlideVisualDecisionV2(
            page_id=page.page_id,
            decision="diagram",
            source_block_ids=page.source_block_ids,
            resolved_template_layout_id=page.template_layout_id,
            visual_payload={
                "nodes": [
                    {
                        "node_id": "collect",
                        "label": "Collect field evidence",
                        "source_block_ids": ["evidence-record"],
                    },
                    {
                        "node_id": "verify",
                        "label": "Verify the timestamp",
                        "source_block_ids": ["evidence-record"],
                    },
                    {
                        "node_id": "publish",
                        "label": "Publish the result",
                        "source_block_ids": ["evidence-record"],
                    },
                ],
                "edges": [
                    {"source": "collect", "target": "verify"},
                    {"source": "verify", "target": "publish"},
                ],
            },
        )],
    )

    deck = compile_slide_deck_v6(document, graph, story, visual, template)
    visible = "\n".join(
        region.content
        for compiled_page in deck.pages
        for region in compiled_page.regions
        if region.content_kind in {"body", "items", "steps"}
        and "evidence-record" in region.source_block_ids
    )

    assert page.summary in visible
    assert deck.pages[0].speaker_notes.source_blocks[0].full_text == source
    assert deck.quality.source_prose_visible_fidelity == 1.0


def test_code_overflow_paginates_every_source_line_and_keeps_full_code_in_notes() -> None:
    code = "\n".join(f"step_{index} = observe({index})" for index in range(55))
    document, graph, template, story, visual = _artifact_deck_fixture(
        artifact_kind="code",
        artifact_text=code,
    )

    deck = compile_slide_deck_v6(document, graph, story, visual, template)

    assert len(deck.pages) > 1
    assert [page.continuation_index for page in deck.pages] == list(
        range(1, len(deck.pages) + 1)
    )
    assert all(page.continuation_count == len(deck.pages) for page in deck.pages)
    rendered_code_lines = [
        line
        for page in deck.pages
        for region in page.regions
        if region.content_kind == "code"
        for line in region.content.splitlines()
    ]
    assert rendered_code_lines == code.splitlines()
    assert all(
        any(note.block_id == "artifact" and note.full_text == code for note in page.speaker_notes.source_blocks)
        for page in deck.pages
    )
    assert deck.quality.source_artifact_visible_fidelity == 1.0
    assert deck.quality.ordered_step_visible_fidelity == 1.0
    assert deck.quality.generated_ellipsis_free is True


def test_fenced_code_in_rich_text_keeps_code_slot_during_pagination() -> None:
    code = "\n".join(
        f"Debug.Log(\"frame {index}\");"
        for index in range(36)
    )
    document, graph, template, story, visual = _artifact_deck_fixture(
        artifact_kind="code",
        artifact_text=f"```csharp\n{code}\n```",
        block_kind="rich_text",
    )

    deck = compile_slide_deck_v6(document, graph, story, visual, template)

    rendered_code_lines = [
        line
        for rendered_page in deck.pages
        for region in rendered_page.regions
        if region.content_kind == "code"
        for line in region.content.splitlines()
    ]
    assert len(deck.pages) > 1
    assert rendered_code_lines == code.splitlines()


def test_short_rich_text_code_annotation_does_not_underfill_support_continuation() -> None:
    annotation = "Minimal runnable script."
    code = "\n".join(
        f'Debug.Log("frame {index}");'
        for index in range(36)
    )
    document = refresh_document_revision(CourseDocument(
        course_id="generic-short-rich-text-code-annotation",
        title="Minimal runnable script",
        sections=[CourseSection(section_id="section", title="Script", position=0)],
        blocks=[_block(
            "fenced-code",
            "section",
            0,
            role="example",
            kind="rich_text",
            text=f"{annotation}\n\n```csharp\n{code}\n```",
        )],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    page = SlideStoryPageV3(
        page_id="short-code-page",
        teaching_unit_id=graph.units[0].teaching_unit_id,
        template_layout_id=template.layout_id("evidence-code"),
        title="Minimal runnable script",
        summary=annotation,
        source_block_ids=["fenced-code"],
        page_ordinal=0,
    )
    story = SlideStoryPlanV3(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        batches=[SlideStoryBatchV3(
            batch_id="story-1",
            chapter_id="section",
            provider="fixture",
            model="fixture",
            duration_ms=1,
            attempts=1,
            validation_status="passed",
            pages=[page],
        )],
    )
    visual = SlideVisualPlanV2(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        decisions=[SlideVisualDecisionV2(
            page_id=page.page_id,
            decision="code",
            source_block_ids=page.source_block_ids,
            resolved_template_layout_id=page.template_layout_id,
        )],
    )

    deck = compile_slide_deck_v6(document, graph, story, visual, template)

    rendered_code_lines = [
        line
        for rendered_page in deck.pages
        for region in rendered_page.regions
        if region.content_kind == "code"
        for line in region.content.splitlines()
    ]
    rendered_body = [
        region.content
        for rendered_page in deck.pages
        for region in rendered_page.regions
        if region.content_kind == "body"
    ]
    assert rendered_code_lines == code.splitlines()
    assert rendered_body == [annotation]


def test_story_preflight_rejects_mixed_prose_roles_in_paginated_practice_code() -> None:
    code = "\n".join(f"Debug.Log(\"frame {index}\");" for index in range(36))
    document = refresh_document_revision(CourseDocument(
        course_id="generic-mixed-practice-code",
        title="Mixed practice code workflow",
        sections=[CourseSection(section_id="section", title="Run script", position=0)],
        blocks=[
            _block("concept", "section", 0, role="concept", text="Explain the execution boundary."),
            _block("reasoning", "section", 1, role="reasoning", text="Compare the observed sequence."),
            _block(
                "fenced-code",
                "section",
                2,
                role="example",
                kind="rich_text",
                text=f"Example source.\n\n```csharp\n{code}\n```",
            ),
            _block(
                "activity",
                "section",
                3,
                role="activity",
                text="1. Attach the script.\n2. Run the scene.\n3. Verify every frame.",
            ),
        ],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    page = SlideStoryPageV3(
        page_id="mixed-practice-code-page",
        teaching_unit_id=graph.units[0].teaching_unit_id,
        template_layout_id=template.layout_id("practice-code"),
        title="Run the complete script",
        source_block_ids=graph.units[0].primary_block_ids,
        page_ordinal=0,
    )
    story = SlideStoryPlanV3(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        batches=[SlideStoryBatchV3(
            batch_id="story-1",
            chapter_id="section",
            provider="fixture",
            model="fixture",
            duration_ms=1,
            attempts=1,
            validation_status="passed",
            pages=[page],
        )],
    )

    with pytest.raises(V6BuildError, match="template_source_slot_role_mismatch"):
        validate_slide_story_plan_v3(story, graph, template)


def test_one_source_block_can_fill_code_and_annotation_without_invented_copy() -> None:
    source = (
        "Explain why the guard must run before the action.\n\n"
        "A missing value stops execution before any downstream action is attempted.\n\n"
        "```python\n"
        "def execute(value):\n"
        "    if value is None:\n"
        "        return False\n"
        "    return True\n"
        "```"
    )
    document = refresh_document_revision(CourseDocument(
        course_id="generic-code-explanation",
        title="Guarded execution",
        sections=[CourseSection(
            section_id="section",
            title="Explain and execute",
            position=0,
        )],
        blocks=[_block(
            "explained-code",
            "section",
            0,
            role="reasoning",
            text=source,
        )],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    page = SlideStoryPageV3(
        page_id="explained-code-page",
        teaching_unit_id=graph.units[0].teaching_unit_id,
        template_layout_id=template.layout_id("evidence-code"),
        title="guard must run",
        summary="Explain why the guard must run before the action.",
        source_block_ids=["explained-code"],
        page_ordinal=0,
    )
    story = SlideStoryPlanV3(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        batches=[SlideStoryBatchV3(
            batch_id="story-1",
            chapter_id="section",
            provider="fixture",
            model="fixture",
            duration_ms=1,
            attempts=1,
            validation_status="passed",
            pages=[page],
        )],
    )
    visual = SlideVisualPlanV2(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        decisions=[SlideVisualDecisionV2(
            page_id=page.page_id,
            decision="code",
            source_block_ids=page.source_block_ids,
            resolved_template_layout_id=page.template_layout_id,
        )],
    )

    deck = compile_slide_deck_v6(document, graph, story, visual, template)

    regions = {region.slot_id: region for region in deck.pages[0].regions}
    assert "def execute(value):" in regions["code"].content
    assert "Explain why the guard" not in regions["code"].content
    assert regions["annotation"].content == page.summary
    assert "def execute(value):" not in regions["annotation"].content
    visible_prose = "\n".join(
        region.content
        for compiled_page in deck.pages
        for region in compiled_page.regions
        if region.content_kind == "body"
    )
    assert page.summary in visible_prose
    assert deck.quality.source_prose_visible_fidelity == 1.0
    assert deck.pages[0].speaker_notes.source_blocks[0].full_text == source


def test_source_only_code_page_does_not_require_an_invented_annotation() -> None:
    """A frozen code artifact remains renderable when no prose annotation exists."""

    source = (
        "```python\n"
        "def normalize(reading):\n"
        "    return max(0, min(100, reading))\n"
        "```"
    )
    document = refresh_document_revision(CourseDocument(
        course_id="generic-source-only-code",
        title="Source-bound automation",
        sections=[CourseSection(
            section_id="section",
            title="Normalize a reading",
            position=0,
        )],
        blocks=[_block(
            "normalization-code",
            "section",
            0,
            role="example",
            kind="code",
            text=source,
        )],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    layout = template.get_layout(template.layout_id("evidence-code"))
    assert layout is not None
    annotation = next(slot for slot in layout.slots if slot.slot_id == "annotation")
    page = SlideStoryPageV3(
        page_id="source-only-code-page",
        teaching_unit_id=graph.units[0].teaching_unit_id,
        template_layout_id=layout.template_layout_id,
        title="normalize",
        summary="",
        source_block_ids=["normalization-code"],
        page_ordinal=0,
    )
    story = SlideStoryPlanV3(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        batches=[SlideStoryBatchV3(
            batch_id="story-1",
            chapter_id="section",
            provider="fixture",
            model="fixture",
            duration_ms=1,
            attempts=1,
            validation_status="passed",
            pages=[page],
        )],
    )
    visual = SlideVisualPlanV2(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        decisions=[SlideVisualDecisionV2(
            page_id=page.page_id,
            decision="code",
            source_block_ids=page.source_block_ids,
            resolved_template_layout_id=page.template_layout_id,
        )],
    )

    deck = compile_slide_deck_v6(document, graph, story, visual, template)

    assert annotation.required is False
    assert [region.slot_id for region in deck.pages[0].regions] == ["code"]
    assert deck.pages[0].regions[0].content == (
        "def normalize(reading):\n"
        "    return max(0, min(100, reading))"
    )
    assert deck.pages[0].speaker_notes.source_blocks[0].full_text == source


def test_non_technical_table_overflow_uses_header_preserving_safe_pages() -> None:
    header = "| Habitat | Observation |\n|---|---|"
    rows = "\n".join(f"| Zone {index} | Record {index} |" for index in range(17))
    table = f"{header}\n{rows}"
    document, graph, template, story, visual = _artifact_deck_fixture(
        artifact_kind="table",
        artifact_text=table,
    )

    deck = compile_slide_deck_v6(document, graph, story, visual, template)

    assert len(deck.pages) == 2
    assert deck.quality.source_prose_visible_fidelity == 1.0
    table_regions = [
        region.content
        for page in deck.pages
        for region in page.regions
        if region.content_kind == "table"
    ]
    assert all(
        region.splitlines()[:2]
        == ["| Habitat | Observation |", "| --- | --- |"]
        for region in table_regions
    )
    assert sum(region.count("| Zone ") for region in table_regions) == 17
    visible_prose = "\n".join(
        region.content
        for page in deck.pages
        for region in page.regions
        if region.content_kind == "body"
    )
    assert "check the stated condition and result" in visible_prose
    assert any(
        "Read the evidence in source order" in note.full_text
        for page in deck.pages
        for note in page.speaker_notes.source_blocks
    )


def test_single_oversized_table_row_reaches_the_declared_detail_layout() -> None:
    headers = "| Stage | Standard | Evidence | Basis | Repair |\n|---|---|---|---|---|"
    row = (
        "| Observe | " + "Preserve the complete signed field record before analysis begins. " * 3
        + "| " + "Retain the place, time, observer, instrument, and sampling window. " * 3
        + "| " + "Compare the record against the declared acceptance condition. " * 3
        + "| " + "Keep the evidence separate from the interpretation and restore every "
        "missing source field before the conclusion is published. " * 3 + "|"
    )
    document, graph, template, story, visual = _artifact_deck_fixture(
        artifact_kind="table",
        artifact_text=f"{headers}\n{row}",
    )

    deck = compile_slide_deck_v6(document, graph, story, visual, template)

    table_regions = [
        region.content
        for page in deck.pages
        for region in page.regions
        if region.content_kind == "table"
    ]
    assert len(deck.pages) == 1
    assert len(table_regions) == 1
    assert "restore every missing source field" in table_regions[0]
    assert "…" not in table_regions[0]


def test_template_safe_table_continuations_do_not_consume_the_story_page_budget() -> None:
    headers = "| Stage | Standard | Evidence | Basis | Repair |\n|---|---|---|---|---|"
    rows = "\n".join(
        (
            f"| Stage {index} | "
            + "Preserve the complete signed field record before analysis begins. " * 2
            + "| Retain place, time, observer, instrument, and sampling window. " * 2
            + "| Compare the record against the declared acceptance condition. " * 2
            + "| Keep evidence separate from interpretation and restore every missing field. " * 2
            + "|"
        )
        for index in range(1, 4)
    )
    document, graph, template, _story, _visual = _artifact_deck_fixture(
        artifact_kind="table",
        artifact_text=f"{headers}\n{rows}",
    )
    unit = graph.units[0]
    pages = [
        SlideStoryPageV3(
            page_id="context-page",
            teaching_unit_id=unit.teaching_unit_id,
            template_layout_id=template.layout_id("content-stack"),
            title="Read the evidence",
            source_block_ids=["context"],
            page_ordinal=0,
        ),
        SlideStoryPageV3(
            page_id="table-page",
            teaching_unit_id=unit.teaching_unit_id,
            template_layout_id=template.layout_id("evidence-table"),
            title="Inspect the complete evidence",
            source_block_ids=["artifact"],
            page_ordinal=1,
        ),
        SlideStoryPageV3(
            page_id="interpretation-page",
            teaching_unit_id=unit.teaching_unit_id,
            template_layout_id=template.layout_id("content-stack"),
            title="Check the stated condition",
            source_block_ids=["interpretation"],
            page_ordinal=2,
        ),
    ]
    story = SlideStoryPlanV3(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        batches=[SlideStoryBatchV3(
            batch_id="story-1",
            chapter_id="section",
            provider="fixture",
            model="fixture",
            duration_ms=1,
            attempts=1,
            validation_status="passed",
            pages=pages,
        )],
    )
    visual = SlideVisualPlanV2(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        decisions=[
            SlideVisualDecisionV2(
                page_id=page.page_id,
                decision="table" if page.page_id == "table-page" else "text_native",
                source_block_ids=page.source_block_ids,
                resolved_template_layout_id=page.template_layout_id,
            )
            for page in pages
        ],
    )

    deck = compile_slide_deck_v6(document, graph, story, visual, template)

    table_pages = [page for page in deck.pages if page.page_id.startswith("table-page")]
    assert len(deck.pages) == 5
    assert len(table_pages) == 3
    assert all(page.continuation_count == 3 for page in table_pages)
    assert [page.title for page in table_pages] == [
        "Inspect the complete evidence",
        "Stage 2",
        "Stage 3",
    ]
    assert all("/3)" not in page.title for page in table_pages)


def test_full_course_compilation_inserts_a_source_bound_cover_before_the_agenda() -> None:
    document = refresh_document_revision(CourseDocument(
        course_id="generic-community-research",
        title="Community research methods",
        sections=[
            CourseSection(section_id="observe", title="观察与记录", position=0),
            CourseSection(section_id="explain", title="解释与复核", position=1),
        ],
        blocks=[
            _block(
                "observe-source",
                "observe",
                0,
                role="concept",
                text="记录地点、时间、参与者与观察事实，并保持原始证据可追溯。",
            ),
            _block(
                "explain-source",
                "explain",
                0,
                role="reasoning",
                text="区分事实与解释，再根据验收标准复核结论并记录修订。",
            ),
        ],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    story_pages = []
    visual_decisions = []
    for ordinal, unit in enumerate(graph.units):
        page_id = f"content-{ordinal + 1}"
        layout_id = template.layout_id("content-stack")
        story_pages.append(SlideStoryPageV3(
            page_id=page_id,
            teaching_unit_id=unit.teaching_unit_id,
            template_layout_id=layout_id,
            title=("记录可追溯的观察事实" if ordinal == 0 else "依据标准复核研究结论"),
            source_block_ids=unit.primary_block_ids,
            page_ordinal=ordinal,
        ))
        visual_decisions.append(SlideVisualDecisionV2(
            page_id=page_id,
            decision="text_native",
            source_block_ids=unit.primary_block_ids,
            resolved_template_layout_id=layout_id,
        ))
    story = SlideStoryPlanV3(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        batches=[SlideStoryBatchV3(
            batch_id="story-course",
            chapter_id="course",
            provider="fixture-pool",
            model="fixture-story",
            duration_ms=1,
            attempts=1,
            validation_status="passed",
            pages=story_pages,
        )],
    )
    visual = SlideVisualPlanV2(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        decisions=visual_decisions,
    )

    deck = compile_slide_deck_v6(document, graph, story, visual, template)

    cover = deck.pages[0]
    assert cover.resolved_layout == template.layout_id("cover-minimal")
    assert cover.title == document.title
    assert cover.source_block_ids == []
    assert cover.source_section_ids == ["observe", "explain"]
    assert cover.speaker_notes.source_blocks == []
    assert cover.speaker_notes.source_section_ids == ["observe", "explain"]
    assert [(region.slot_id, region.content) for region in cover.regions] == [
        ("title", document.title),
    ]

    agenda = deck.pages[1]
    assert agenda.resolved_layout == template.layout_id("agenda-path")
    assert agenda.source_block_ids == []
    assert agenda.source_section_ids == ["observe", "explain"]
    assert agenda.speaker_notes.source_blocks == []
    assert agenda.speaker_notes.source_section_ids == ["observe", "explain"]
    assert agenda.regions[0].content.splitlines() == ["观察与记录", "解释与复核"]
    assert [page.page_ordinal for page in deck.pages] == list(range(len(deck.pages)))
    assert deck.quality.formal_block_visible_coverage == 1.0
    assert deck.quality.source_order_preserved is True


def test_teacher_lesson_compilation_has_cover_path_and_recap() -> None:
    document = refresh_document_revision(CourseDocument(
        course_id="teacher-lesson-linear-algebra",
        title="第1章 向量与线性方程组",
        sections=[
            CourseSection(section_id="lesson", title="第1章", position=0),
            CourseSection(
                section_id="vectors",
                parent_section_id="lesson",
                title="1.1 向量的代数定义与基本运算",
                position=1,
            ),
            CourseSection(
                section_id="elimination",
                parent_section_id="lesson",
                title="1.2 高斯消元法的标准流程",
                position=2,
            ),
        ],
        blocks=[
            _block(
                "vector-source",
                "vectors",
                0,
                role="concept",
                text="同维向量按对应分量相加，异维向量的加法未定义。",
            ),
            _block(
                "elimination-source",
                "elimination",
                0,
                role="reasoning",
                text="主元为零时交换两行，再用倍加变换逐列消元。",
            ),
        ],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("academic-editorial")
    story_pages: list[SlideStoryPageV3] = []
    visual_decisions: list[SlideVisualDecisionV2] = []
    titles = ["同维向量按对应分量相加", "主元为零时交换两行"]
    for ordinal, unit in enumerate(graph.units):
        page_id = f"lesson-page-{ordinal + 1}"
        layout_id = template.layout_id("content-stack")
        story_pages.append(SlideStoryPageV3(
            page_id=page_id,
            teaching_unit_id=unit.teaching_unit_id,
            template_layout_id=layout_id,
            title=titles[ordinal],
            source_block_ids=unit.primary_block_ids,
            page_ordinal=ordinal,
        ))
        visual_decisions.append(SlideVisualDecisionV2(
            page_id=page_id,
            decision="text_native",
            source_block_ids=unit.primary_block_ids,
            resolved_template_layout_id=layout_id,
        ))
    story = SlideStoryPlanV3(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        batches=[SlideStoryBatchV3(
            batch_id="teacher-lesson-story",
            chapter_id="lesson",
            provider="fixture",
            model="fixture",
            duration_ms=1,
            attempts=1,
            validation_status="passed",
            pages=story_pages,
        )],
    )
    visual = SlideVisualPlanV2(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        decisions=visual_decisions,
    )

    deck = compile_slide_deck_v6(document, graph, story, visual, template)

    assert deck.pages[0].resolved_layout.endswith("/cover-minimal")
    assert deck.pages[1].resolved_layout.endswith("/agenda-path")
    assert deck.pages[-1].resolved_layout.endswith("/chapter-recap")
    assert [
        value
        for value in deck.pages[-1].regions[0].content.splitlines()
        if value
    ] == [
        "1.1 向量的代数定义与基本运算",
        "1.2 高斯消元法的标准流程",
    ]


def test_single_section_teacher_lesson_derives_path_from_confirmed_script_groups() -> None:
    document = refresh_document_revision(CourseDocument(
        course_id="teacher-lesson-calculus",
        title="第6章 微积分基本定理：连接变化与累积",
        sections=[
            CourseSection(section_id="lesson", title="第6章", position=0),
            CourseSection(
                section_id="fundamental-theorem",
                parent_section_id="lesson",
                title="6.1 微积分基本定理：从变化率到累计量",
                position=1,
            ),
        ],
        blocks=[
            CourseBlock(
                block_id="objective",
                section_id="fundamental-theorem",
                parent_group_id="opening",
                position=0,
                role="concept",
                payload={"title": "本节任务", "text": "辨认固定起点与变动终点。"},
            ),
            CourseBlock(
                block_id="definition",
                section_id="fundamental-theorem",
                parent_group_id="core",
                position=1,
                role="concept",
                payload={"title": "正式定义", "text": "定义变上限积分函数。"},
            ),
            CourseBlock(
                block_id="derivation",
                section_id="fundamental-theorem",
                parent_group_id="core",
                position=2,
                role="reasoning",
                payload={"title": "证明与推导", "text": "由积分中值定理完成推导。"},
            ),
            CourseBlock(
                block_id="feedback",
                section_id="fundamental-theorem",
                parent_group_id="practice",
                position=3,
                role="concept",
                payload={"title": "检查与反馈", "text": "检查公式适用条件。"},
            ),
        ],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("academic-editorial")
    story_pages: list[SlideStoryPageV3] = []
    visual_decisions: list[SlideVisualDecisionV2] = []
    grounded_titles = [
        "辨认固定起点与变动终点",
        "由积分中值定理完成推导",
        "检查公式适用条件",
    ]
    for ordinal, unit in enumerate(graph.units):
        page_id = f"lesson-page-{ordinal + 1}"
        layout_id = template.layout_id("content-stack")
        story_pages.append(SlideStoryPageV3(
            page_id=page_id,
            teaching_unit_id=unit.teaching_unit_id,
            template_layout_id=layout_id,
            title=grounded_titles[ordinal],
            source_block_ids=unit.primary_block_ids,
            page_ordinal=ordinal,
        ))
        visual_decisions.append(SlideVisualDecisionV2(
            page_id=page_id,
            decision="text_native",
            source_block_ids=unit.primary_block_ids,
            resolved_template_layout_id=layout_id,
        ))
    story = SlideStoryPlanV3(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        batches=[SlideStoryBatchV3(
            batch_id="teacher-lesson-story",
            chapter_id="fundamental-theorem",
            provider="fixture",
            model="fixture",
            duration_ms=1,
            attempts=1,
            validation_status="passed",
            pages=story_pages,
        )],
    )
    visual = SlideVisualPlanV2(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        decisions=visual_decisions,
    )

    manuscript = compile_ppt_manuscript_v1(
        document,
        graph,
        story,
        visual,
        template,
    )

    assert manuscript.quality_status == "passed"
    assert manuscript.pages[0].layout_id.endswith("/cover-minimal")
    path = manuscript.pages[1]
    assert path.layout_id.endswith("/agenda-path")
    assert path.visible_copy == [
        "本节任务\n正式定义 → 证明与推导\n检查与反馈"
    ]
    assert path.source_script_block_ids == [
        "objective", "definition", "derivation", "feedback",
    ]
    assert manuscript.pages[-1].layout_id.endswith("/chapter-recap")


def test_course_agenda_uses_source_descriptions_and_sample_backed_page_density() -> None:
    descriptions = [
        "先验证环境与语言基线，再进入可运行项目。",
        "用生命周期实验建立场景对象的状态模型。",
        "把交互输入连接到物理反馈与可观察结果。",
        "用界面与持久化证据验证运行时数据流。",
        "通过性能与架构复核形成可交付工程。",
    ]
    document = refresh_document_revision(CourseDocument(
        course_id="generic-agenda-hierarchy",
        title="工程学习路径",
        sections=[
            CourseSection(
                section_id=f"chapter-{index}",
                title=f"第{index}章 完整章节标题 {index}",
                position=index - 1,
                attributes={"path_reason": descriptions[index - 1]},
            )
            for index in range(1, 6)
        ],
        blocks=[
            _block(
                f"chapter-{index}-source",
                f"chapter-{index}",
                0,
                role="concept",
                text=f"第{index}章的正式来源正文。",
            )
            for index in range(1, 6)
        ],
    ))
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")

    pages = _compile_course_agenda_pages(document, template)

    assert [len(page.regions[0].metadata["agenda_entries"]) for page in pages] == [3, 2]
    assert [
        entry["title"]
        for page in pages
        for entry in page.regions[0].metadata["agenda_entries"]
    ] == [section.title for section in document.sections]
    assert [
        entry["description"]
        for page in pages
        for entry in page.regions[0].metadata["agenda_entries"]
    ] == descriptions
    assert all(
        entry["description"] != entry["title"]
        for page in pages
        for entry in page.regions[0].metadata["agenda_entries"]
    )


def test_story_summary_rejects_raw_markdown_table_content() -> None:
    document = _cross_subject_document()
    graph, template, story = _valid_story(document)
    story.batches[0].pages[0].summary = (
        "| 任务环节 | 核对标准 | 参考结论 | 推导依据 | 典型错误与修正 |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| 观察 | 记录地点时间天气 | 保留原始证据 | 依据验收标准复核 | 区分事实与解释 |"
    )

    with pytest.raises(V6BuildError, match="story_summary_markdown_invalid"):
        validate_slide_story_plan_v3(story, graph, template)


def test_very_large_code_can_expand_beyond_three_pages_without_source_loss() -> None:
    code = "\n".join(f"step_{index} = observe({index})" for index in range(90))
    document, graph, template, story, visual = _artifact_deck_fixture(
        artifact_kind="code",
        artifact_text=code,
    )

    deck = compile_slide_deck_v6(document, graph, story, visual, template)

    assert len(deck.pages) > 3
    rendered_code_lines = [
        line
        for page in deck.pages
        for region in page.regions
        if region.content_kind == "code"
        for line in region.content.splitlines()
    ]
    assert rendered_code_lines == code.splitlines()
    assert all(
        any(
            note.block_id == "artifact" and note.full_text == code
            for note in page.speaker_notes.source_blocks
        )
        for page in deck.pages
    )


def test_diagram_visual_does_not_duplicate_or_truncate_its_bound_source() -> None:
    source = "".join([
        "完整核验流程先采集原始记录并保留 checkpoint_identifier_alpha_2026。",
        "随后核对时间、地点、操作者与 acceptance_boundary_identifier_beta。",
        "如果日志不一致，记录完整差异并执行 the deterministic recovery step。",
        "修复后重新运行回归验证，确认每一条 source-bound observation 仍然可追溯。",
        "发布前保存兼容检查点并复核 visual mapping does not cross page boundaries。",
        "最后形成结论，且所有原文必须在正文或安全续页中完整可见。",
    ])
    document = refresh_document_revision(CourseDocument(
        course_id="generic-source-complete-diagram",
        title="完整核验流程",
        sections=[CourseSection(section_id="section", title="核验", position=0)],
        blocks=[_block(
            "flow",
            "section",
            0,
            role="reasoning",
            kind="diagram",
            text=source,
        )],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    page = SlideStoryPageV3(
        page_id="source-complete-diagram-page",
        teaching_unit_id=graph.units[0].teaching_unit_id,
        template_layout_id=template.layout_id("evidence-diagram"),
        title="完整核验流程",
        source_block_ids=["flow"],
        page_ordinal=0,
    )
    story = SlideStoryPlanV3(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        batches=[SlideStoryBatchV3(
            batch_id="story-diagram",
            chapter_id="section",
            provider="fixture",
            model="fixture",
            duration_ms=1,
            attempts=1,
            validation_status="passed",
            pages=[page],
        )],
    )
    visual = SlideVisualPlanV2(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        decisions=[SlideVisualDecisionV2(
            page_id=page.page_id,
            decision="diagram",
            source_block_ids=page.source_block_ids,
            resolved_template_layout_id=page.template_layout_id,
            visual_payload={
                "nodes": [
                    {
                        "node_id": "collect",
                        "label": "采集原始记录",
                        "source_block_ids": ["flow"],
                    },
                    {
                        "node_id": "verify",
                        "label": "核对时间、地点与操作者",
                        "source_block_ids": ["flow"],
                    },
                    {
                        "node_id": "publish",
                        "label": "发布前保存兼容检查点",
                        "source_block_ids": ["flow"],
                    },
                ],
                "edges": [
                    {"source": "collect", "target": "verify"},
                    {"source": "verify", "target": "publish"},
                ],
            },
        )],
    )

    deck = compile_slide_deck_v6(document, graph, story, visual, template)
    visible = "\n".join(
        region.content
        for rendered_page in deck.pages
        for region in rendered_page.regions
        if region.content_kind in {"body", "items", "steps"}
        and "flow" in region.source_block_ids
    )
    diagram_page = next(
        rendered_page
        for rendered_page in deck.pages
        if rendered_page.visual_decision.decision == "diagram"
    )
    renderer_slide = adapt_v6_page_to_slide_spec(diagram_page)

    assert "".join(source.split()) in "".join(visible.split())
    assert all(
        region.content_kind != "visual"
        for rendered_page in deck.pages
        for region in rendered_page.regions
    )
    assert len(renderer_slide.visuals) == 1
    assert all(
        block.metadata.get("v6_slot_id") != "diagram"
        for block in renderer_slide.blocks
    )
    assert deck.quality.formal_block_visible_coverage == 1.0
    assert deck.quality.source_prose_visible_fidelity == 1.0
    assert deck.quality.generated_ellipsis_free is True


def test_v6_modules_do_not_hardcode_course_identity_or_fixed_artifacts() -> None:
    import course_presentation_graph
    import slide_deck_v6
    import template_layout_contract

    source = "\n".join(
        inspect.getsource(module)
        for module in (course_presentation_graph, slide_deck_v6, template_layout_contract)
    ).lower()
    for forbidden in (
        "unity 游戏编程进阶实战",
        "线性代数：理论与应用",
        "机器学习：原理",
        "course-generic-ecology",
        "playercontroller.cs",
    ):
        assert forbidden.lower() not in source
