from __future__ import annotations

from collections import Counter
from math import ceil

import pytest

import slide_deck_v6 as deck_v6
from course_document import CourseBlock
from course_presentation_graph import block_artifact_kinds
from slide_deck_v6 import (
    V6BuildError,
    _prose_source_text,
    _safe_artifact_page_blocks,
    validate_layout_source_satisfiability,
)
from template_layout_contract import (
    compile_builtin_template_layout_contract_v1,
    template_layout_contract_matrix,
)

_BUILTIN_TEMPLATE = compile_builtin_template_layout_contract_v1(
    "qizhi-classroom"
)
_BUILTIN_LAYOUT_SLUGS = [
    layout.layout_slug
    for layout in _BUILTIN_TEMPLATE.layouts
]


def _block(
    block_id: str,
    *,
    role: str,
    markdown: str,
    kind: str = "rich_text",
    position: int = 0,
) -> CourseBlock:
    return CourseBlock(
        block_id=block_id,
        section_id="layout-audit-section",
        position=position,
        role=role,
        kind=kind,
        payload={"markdown": markdown},
    )


def _valid_layout_source(layout) -> tuple[list[CourseBlock], dict[str, str]]:
    blocks: list[CourseBlock] = []
    source_by_slot: dict[str, str] = {}
    position = 0
    for slot in layout.slots:
        if not slot.required or slot.slot_kind in {"title", "eyebrow", "notes"}:
            continue
        block_id = f"{layout.layout_slug}-{slot.slot_id}"
        role = next(iter(slot.source_roles), "concept")
        if slot.slot_kind == "code":
            block = CourseBlock(
                block_id=block_id,
                section_id="layout-audit-section",
                position=position,
                role=role,
                kind="code",
                payload={"code": "def verify(value):\n    return value is not None"},
            )
        elif slot.slot_kind == "formula":
            block = CourseBlock(
                block_id=block_id,
                section_id="layout-audit-section",
                position=position,
                role=role,
                kind="formula",
                payload={"formula": "score = verified / total"},
            )
        elif slot.slot_kind == "table":
            block = CourseBlock(
                block_id=block_id,
                section_id="layout-audit-section",
                position=position,
                role=role,
                kind="table",
                payload={
                    "markdown": (
                        "| Check | Evidence |\n"
                        "| --- | --- |\n"
                        "| Identity | Verified |"
                    )
                },
            )
        elif slot.slot_kind == "visual":
            visual_kind = (
                "diagram"
                if "diagram" in layout.artifact_kinds
                else "image"
            )
            block = CourseBlock(
                block_id=block_id,
                section_id="layout-audit-section",
                position=position,
                role="orientation",
                kind=visual_kind,
                payload={"markdown": "Source-bound visual evidence."},
                asset_refs=[f"asset-{block_id}"],
            )
        else:
            if slot.slot_kind == "steps":
                markdown = (
                    "1. Verify the frozen input and record the state.\n"
                    "2. Compare the result with the declared criterion."
                )
            elif slot.slot_kind == "items":
                markdown = "- Preserve the input.\n- Verify the result."
            else:
                base = (
                    "This source-backed explanation preserves the teaching claim "
                    "and its verification action. "
                )
                target = max(int(slot.min_chars or 0), min(100, int(slot.max_chars or 100)))
                markdown = (base * max(1, (target // len(base)) + 1))[:target]
            block = _block(
                block_id,
                role=role,
                markdown=markdown,
                position=position,
            )
        blocks.append(block)
        source_by_slot[slot.slot_id] = block_id
        position += 1
    return blocks, source_by_slot


@pytest.mark.parametrize("layout_slug", _BUILTIN_LAYOUT_SLUGS)
def test_every_builtin_layout_has_a_deterministic_satisfiable_source_shape(
    layout_slug: str,
) -> None:
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    layout = template.get_layout(template.layout_id(layout_slug))
    assert layout is not None
    blocks, _source_by_slot = _valid_layout_source(layout)

    first = validate_layout_source_satisfiability(
        page_id=f"all-layouts-{layout_slug}",
        template=template,
        layout=layout,
        source_blocks=blocks,
    )
    second = validate_layout_source_satisfiability(
        page_id=f"all-layouts-{layout_slug}",
        template=template,
        layout=layout,
        source_blocks=blocks,
    )

    def signature(pages):
        return [
            (
                page.layout.layout_slug,
                [block.block_id for block in page.source_blocks],
                [_prose_source_text(block) for block in page.source_blocks],
            )
            for page in pages
        ]

    assert signature(first) == signature(second)


@pytest.mark.parametrize("layout_slug", _BUILTIN_LAYOUT_SLUGS)
def test_every_builtin_required_content_slot_rejects_missing_source(
    layout_slug: str,
) -> None:
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    layout = template.get_layout(template.layout_id(layout_slug))
    assert layout is not None
    blocks, source_by_slot = _valid_layout_source(layout)

    for slot in layout.slots:
        if slot.slot_id not in source_by_slot:
            continue
        if slot.slot_kind == "visual" and "diagram" in layout.artifact_kinds:
            # A diagram may be generated from another frozen explanatory block;
            # deleting one visual-shaped block does not make the slot source-free.
            continue
        without_required_source = [
            block
            for block in blocks
            if block.block_id != source_by_slot[slot.slot_id]
        ]
        with pytest.raises(V6BuildError):
            validate_layout_source_satisfiability(
                page_id=f"missing-{layout_slug}-{slot.slot_id}",
                template=template,
                layout=layout,
                source_blocks=without_required_source,
            )


def test_builtin_layout_contract_matrix_is_complete_and_closed() -> None:
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")

    matrix = template_layout_contract_matrix(template)

    assert {row["layout_slug"] for row in matrix} == {
        layout.layout_slug for layout in template.layouts
    }
    known_slugs = {layout.layout_slug for layout in template.layouts}
    for row in matrix:
        assert row["required_slots"]
        assert set(row["safe_continuation_layout_slugs"]).issubset(known_slugs)
        for slot in row["required_slots"]:
            assert slot["slot_kind"] in {
                "title",
                "body",
                "items",
                "steps",
                "code",
                "formula",
                "table",
                "visual",
                "notes",
            }
            if slot["slot_kind"] not in {"title", "visual", "notes"}:
                assert any(
                    slot[key]
                    for key in ("max_chars", "max_items", "max_lines", "max_rows")
                )

    content_stack = next(row for row in matrix if row["layout_slug"] == "content-stack")
    body_slot = next(
        slot for slot in content_stack["required_slots"] if slot["slot_kind"] == "body"
    )
    evidence_code = next(row for row in matrix if row["layout_slug"] == "evidence-code")
    code_slot = next(
        slot for slot in evidence_code["required_slots"] if slot["slot_kind"] == "code"
    )
    assert body_slot["max_chars"] == 650
    assert body_slot["max_lines"] == 30
    assert code_slot["max_chars"] == 400
    assert code_slot["max_lines"] == 13
    assert code_slot["continuation_max_chars"] == 650
    assert code_slot["continuation_max_lines"] == 13


def test_multi_slot_pagination_never_repeats_a_companion_source_block() -> None:
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    layout = template.get_layout(template.layout_id("practice-prompt"))
    assert layout is not None
    blocks = [
        _block(
            "task-a",
            role="activity",
            position=0,
            markdown="\n".join([
                "1. TASK-A-MARKER：先冻结输入并记录状态。",
                *(
                    f"{index}. 执行第 {index} 个完整操作，并记录足够详细的观察结果。"
                    for index in range(2, 8)
                ),
            ]),
        ),
        _block(
            "task-b",
            role="activity",
            position=1,
            markdown="\n".join(
                f"{index}. TASK-B-{index}：复核另一组完整操作与输出。"
                for index in range(1, 7)
            ),
        ),
        _block(
            "criteria",
            role="feedback",
            position=2,
            markdown="\n".join(
                f"- CRITERIA-{index}：必须能由记录的观察直接判定。"
                for index in range(1, 9)
            ),
        ),
    ]

    materializations = _safe_artifact_page_blocks(
        page_id="multi-slot-replay",
        template=template,
        layout=layout,
        source_blocks=blocks,
    )
    visible = "\n".join(
        _prose_source_text(block)
        for page in materializations
        for block in page.source_blocks
    )

    assert len(materializations) > 1
    assert visible.count("TASK-A-MARKER") == 1
    assert visible.count("TASK-B-1") == 1
    assert visible.count("CRITERIA-1") == 1
    assert all(
        page.layout.layout_slug in {"practice-prompt", "content-stack"}
        for page in materializations
    )


def test_optional_companion_overflow_uses_continuation_capacity_linearly() -> None:
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    layout = template.get_layout(template.layout_id("practice-prompt"))
    continuation = template.get_layout(template.layout_id("content-stack"))
    assert layout is not None
    assert continuation is not None
    feedback = "".join(
        f"验收项 {index}：核对输入、动作、观察和结论。"
        for index in range(1, 42)
    )
    blocks = [
        _block(
            "short-task",
            role="activity",
            position=0,
            markdown="1. 执行一次完整操作。\n2. 记录可复核结果。",
        ),
        _block(
            "long-criteria",
            role="feedback",
            position=1,
            markdown=feedback,
        ),
    ]

    materializations = validate_layout_source_satisfiability(
        page_id="linear-optional-overflow",
        template=template,
        layout=layout,
        source_blocks=blocks,
    )

    continuation_body = next(
        slot for slot in continuation.slots if slot.slot_kind == "body"
    )
    expected_continuations = ceil(
        len(_prose_source_text(blocks[1]))
        / continuation_body.max_chars
    )
    assert len(materializations) <= 1 + expected_continuations + 1
    assert materializations[0].layout.layout_slug == "practice-prompt"
    assert all(
        page.layout.layout_slug == "content-stack"
        for page in materializations[1:]
    )


def test_multi_slot_overflow_preserves_first_source_occurrence_order() -> None:
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    layout = template.get_layout(template.layout_id("practice-prompt"))
    assert layout is not None
    blocks = [
        _block(
            "activity-a",
            role="activity",
            position=0,
            markdown="1. A-" + "保留完整操作与观察。" * 24,
        ),
        _block(
            "activity-b",
            role="activity",
            position=1,
            markdown="1. B-" + "保留另一组操作与观察。" * 24,
        ),
        _block(
            "feedback-c",
            role="feedback",
            position=2,
            markdown="- C-逐项核对证据并给出结论。",
        ),
    ]

    materializations = validate_layout_source_satisfiability(
        page_id="ordered-multi-slot-overflow",
        template=template,
        layout=layout,
        source_blocks=blocks,
    )
    first_occurrences: list[str] = []
    seen: set[str] = set()
    for page in materializations:
        for block in sorted(page.source_blocks, key=lambda item: item.position):
            if block.block_id not in seen:
                seen.add(block.block_id)
                first_occurrences.append(block.block_id)

    assert first_occurrences == [block.block_id for block in blocks]


def test_short_content_never_creates_an_unnecessary_continuation() -> None:
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    layout = template.get_layout(template.layout_id("content-stack"))
    assert layout is not None
    blocks = [
        _block(
            "short-body",
            role="concept",
            markdown="这段完整正文显著低于模板容量，因此不应拆页。" * 4,
        )
    ]

    materializations = validate_layout_source_satisfiability(
        page_id="short-content",
        template=template,
        layout=layout,
        source_blocks=blocks,
    )

    assert len(materializations) == 1


def test_content_stack_paginates_on_readable_line_capacity_without_text_loss() -> None:
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    layout = template.get_layout(template.layout_id("content-stack"))
    assert layout is not None
    body_slot = next(slot for slot in layout.slots if slot.slot_id == "body")
    source = "\n\n".join(
        f"第{index}项观察必须保留条件、原始记录、判断依据与复核结果。"
        for index in range(1, 19)
    )
    block = _block(
        "line-dense-body",
        role="concept",
        markdown=source,
    )

    materializations = validate_layout_source_satisfiability(
        page_id="line-dense-content",
        template=template,
        layout=layout,
        source_blocks=[block],
    )
    rendered_chunks = [
        deck_v6._complete_slot_content(page.source_blocks, "body")
        for page in materializations
    ]

    assert len(source) < body_slot.max_chars
    assert len(materializations) > 1
    assert "\n\n".join(rendered_chunks) == source
    assert all(
        deck_v6._prose_wrapped_line_cost(chunk) <= body_slot.max_lines
        for chunk in rendered_chunks
    )


def test_code_continuations_scale_with_declared_line_capacity_without_duplicates() -> None:
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    layout = template.get_layout(template.layout_id("evidence-code"))
    assert layout is not None
    source = "\n".join(f"value_{index} = {index};" for index in range(51))
    block = _block(
        "linear-code",
        role="example",
        kind="code",
        markdown=source,
    )

    materializations = validate_layout_source_satisfiability(
        page_id="linear-code-pagination",
        template=template,
        layout=layout,
        source_blocks=[block],
    )
    visible = "\n".join(
        deck_v6._complete_slot_content(page.source_blocks, "code")
        for page in materializations
    )

    assert len(materializations) == ceil(51 / 13)
    assert visible == source


def test_table_pagination_keeps_source_prose_once_instead_of_once_per_chunk() -> None:
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    layout = template.get_layout(template.layout_id("evidence-table"))
    assert layout is not None
    rows = "\n".join(
        f"| {index} | value-{index}-with-long-detail | verify-{index} |"
        for index in range(1, 18)
    )
    block = _block(
        "table-with-prose",
        role="reasoning",
        markdown=(
            "TABLE-INTRO-MARKER：下表保留完整的观测与验证关系。\n\n"
            "| id | observed value | verification |\n"
            "| --- | --- | --- |\n"
            f"{rows}"
        ),
    )
    assert "table" in block_artifact_kinds(block)

    materializations = _safe_artifact_page_blocks(
        page_id="table-prose-replay",
        template=template,
        layout=layout,
        source_blocks=[block],
    )
    visible = "\n".join(
        _prose_source_text(fragment)
        for page in materializations
        for fragment in page.source_blocks
    )

    assert len(materializations) > 1
    assert visible.count("TABLE-INTRO-MARKER") == 1


def test_optional_table_interpretation_routes_unmatched_prose_to_safe_continuation() -> None:
    """A table layout may preserve an extra source role without mislabelling it."""

    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    layout = template.get_layout(template.layout_id("evidence-table"))
    assert layout is not None
    blocks = [
        _block(
            "diagnostic-context",
            role="misconception",
            position=0,
            markdown="DIAGNOSTIC-CONTEXT：先记录症状、定位步骤和修正边界。",
        ),
        _block(
            "verification-table",
            role="feedback",
            position=1,
            kind="table",
            markdown=(
                "| Check | Evidence |\n"
                "| --- | --- |\n"
                "| State | Verified |"
            ),
        ),
        _block(
            "verification-result",
            role="feedback",
            position=2,
            markdown="VERIFICATION-RESULT：复核状态变化并记录结论。",
        ),
    ]

    materializations = validate_layout_source_satisfiability(
        page_id="table-with-unmatched-support",
        template=template,
        layout=layout,
        source_blocks=blocks,
    )
    visible = "\n".join(
        _prose_source_text(block)
        for page in materializations
        for block in page.source_blocks
    )

    assert {page.layout.layout_slug for page in materializations} == {
        "content-stack",
        "evidence-table",
    }
    assert visible.count("DIAGNOSTIC-CONTEXT") == 1
    assert visible.count("VERIFICATION-RESULT") == 1


def test_required_artifact_support_routes_nonmatching_prose_losslessly() -> None:
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    layout = template.get_layout(template.layout_id("evidence-formula"))
    assert layout is not None
    blocks = [
        _block(
            "formula-concept",
            role="concept",
            position=0,
            markdown=(
                "FORMULA-CONTEXT：完整说明变量边界与适用条件。" * 28
                + "\n\n$$score = verified / total$$"
            ),
        ),
        _block(
            "formula-derivation",
            role="reasoning",
            position=1,
            markdown="DERIVATION：先确认总量非零，再计算已验证项比例。",
        ),
    ]

    materializations = validate_layout_source_satisfiability(
        page_id="formula-with-concept-support",
        template=template,
        layout=layout,
        source_blocks=blocks,
    )
    visible = "\n".join(
        _prose_source_text(block)
        for page in materializations
        for block in page.source_blocks
    )

    assert materializations[0].layout.layout_slug == "evidence-formula"
    assert any(
        page.layout.layout_slug == "content-stack"
        for page in materializations[1:]
    )
    assert visible.count("FORMULA-CONTEXT") == 28
    assert visible.count("DERIVATION") == 1


def test_inline_math_remains_visible_prose_when_it_is_not_a_formula_artifact() -> None:
    block = _block(
        "inline-math-step",
        role="activity",
        markdown=(
            "1. 设置分辨率为 $1920 \\times 1080$。\n"
            "2. 将偏移量设为 $0$，然后记录结果。"
        ),
    )

    assert block_artifact_kinds(block) == []
    assert "$1920 \\times 1080$" in _prose_source_text(block)
    assert "$0$" in _prose_source_text(block)


def test_ordered_step_fidelity_ignores_rendering_punctuation_but_not_facts() -> None:
    source = (
        "1. 配置输入：\n"
        "   - 分辨率使用 $1920 \\times 1080$；\n"
        "   - 偏移量设为 $0$。\n"
        "2. 运行验证并记录输出。"
    )
    visible = (
        "配置输入。分辨率使用 $1920 \\times 1080$。偏移量设为 $0$；"
        "运行验证并记录输出。"
    )

    assert deck_v6._ordered_step_sequence_visible(source, visible)
    assert not deck_v6._ordered_step_sequence_visible(
        source,
        visible.replace("偏移量设为 $0$", "偏移量保持默认值"),
    )


@pytest.mark.parametrize(
    ("layout_slug", "blocks"),
    [
        (
            "misconception-repair",
            [_block("only-symptom", role="misconception", markdown="一个完整但单一的误区描述。")],
        ),
        (
            "practice-code",
            [_block("only-code", role="example", kind="code", markdown="print('only artifact')")],
        ),
        (
            "course-synthesis",
            [_block("only-synthesis", role="summary", markdown="只提供综合结论，没有迁移动作。")],
        ),
    ],
)
def test_required_slots_fail_before_visual_or_template_materialization(
    layout_slug: str,
    blocks: list[CourseBlock],
) -> None:
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    layout = template.get_layout(template.layout_id(layout_slug))
    assert layout is not None

    with pytest.raises(V6BuildError) as captured:
        validate_layout_source_satisfiability(
            page_id=f"missing-slot-{layout_slug}",
            template=template,
            layout=layout,
            source_blocks=blocks,
        )

    assert captured.value.failure.code == "template_required_slot_unfilled"


def test_every_materialized_continuation_satisfies_its_own_required_slots() -> None:
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    layout = template.get_layout(template.layout_id("practice-feedback"))
    assert layout is not None
    blocks = [
        _block(
            "symptom",
            role="misconception",
            position=0,
            markdown="误区现象：" + "观察结果被误当作原因。" * 35,
        ),
        _block(
            "repair",
            role="feedback",
            position=1,
            markdown="修正反馈：" + "逐项核对状态迁移与证据。" * 45,
        ),
    ]

    materializations = validate_layout_source_satisfiability(
        page_id="continuation-contract-replay",
        template=template,
        layout=layout,
        source_blocks=blocks,
    )

    assert len(materializations) > 1
    counts = Counter(page.layout.layout_slug for page in materializations)
    assert counts["practice-feedback"] == 1
    assert counts["content-stack"] >= 1
