from __future__ import annotations

from collections import Counter

import pytest

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
