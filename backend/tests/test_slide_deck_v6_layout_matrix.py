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
from slide_layout_geometry import (
    BALANCED_TWO_COLUMN_BODY_V1,
    CLASSIFICATION_THREE_CARDS_V1,
    HORIZONTAL_PROCESS_CARDS_V1,
    balanced_two_column_body_metrics,
    capacity_profile_text_fits,
    classification_three_card_metrics,
    diagram_node_layout_metrics,
    horizontal_process_card_metrics,
    wrapped_line_count,
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


def test_required_steps_slot_rejects_unstructured_prose() -> None:
    """A prose paragraph cannot silently collapse into a generated step summary."""

    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    layout = template.get_layout(template.layout_id("process-flow"))
    assert layout is not None
    source = _block(
        "unstructured-process-source",
        role="concept",
        markdown=(
            "The runtime inspector exposes current values while the console records "
            "diagnostic output. Serialized fields remain visible during play mode, "
            "and the developer compares observations before changing the script."
        ),
    )

    with pytest.raises(V6BuildError) as error:
        validate_layout_source_satisfiability(
            page_id="unstructured-process",
            template=template,
            layout=layout,
            source_blocks=[source],
        )

    assert error.value.failure.code == "template_required_slot_unfilled"


def test_required_steps_slot_rejects_numbered_concept_sections() -> None:
    """Numbered exposition is not automatically a procedural source role."""

    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    layout = template.get_layout(template.layout_id("process-flow"))
    assert layout is not None
    source = _block(
        "numbered-concept-sections",
        role="concept",
        markdown=(
            "The comparison distinguishes two runtime observation tools.\n"
            "1. Inspector values\n"
            "- Serialized fields expose the current runtime state.\n"
            "2. Diagnostic logs\n"
            "- Log records support later investigation."
        ),
    )

    with pytest.raises(V6BuildError) as error:
        validate_layout_source_satisfiability(
            page_id="numbered-concept-sections",
            template=template,
            layout=layout,
            source_blocks=[source],
        )

    assert error.value.failure.code == "template_required_slot_unfilled"


def test_process_flow_rejects_a_reasoning_outline_that_drops_visible_source() -> None:
    """Numbered headings cannot make an incomplete step projection lossless."""

    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    layout = template.get_layout(template.layout_id("process-flow"))
    assert layout is not None
    source = _block(
        "numbered-reasoning-specification",
        role="reasoning",
        markdown=(
            "Turn the repair request into explicit engineering acceptance criteria.\n\n"
            "### 1. Required inputs\n"
            "- A runnable packaged build.\n"
            "- A release checklist containing known defects.\n\n"
            "### 2. Required outputs\n"
            "- A structured defect report.\n"
            "  - Exact reproduction steps.\n"
            "  - Root-cause evidence.\n\n"
            "### 3. Acceptance criteria\n"
            "- Every regression test passes."
        ),
    )

    with pytest.raises(V6BuildError) as error:
        validate_layout_source_satisfiability(
            page_id="numbered-reasoning-specification",
            template=template,
            layout=layout,
            source_blocks=[source],
        )

    assert (
        error.value.failure.code
        == "template_source_semantic_fidelity_incomplete"
    )

    fallback = template.get_layout(template.layout_id("content-stack"))
    assert fallback is not None
    materializations = validate_layout_source_satisfiability(
        page_id="numbered-reasoning-specification-fallback",
        template=template,
        layout=fallback,
        source_blocks=[source],
    )
    assert materializations
    assert all(page.layout.layout_slug == "content-stack" for page in materializations)


def test_content_stack_is_a_lossless_fallback_for_structured_activity_prose() -> None:
    """A body continuation may preserve steps when card projection loses context."""

    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    fallback = template.get_layout(template.layout_id("content-stack"))
    assert fallback is not None
    source = _block(
        "structured-activity-with-context",
        role="activity",
        markdown=(
            "Record the baseline before changing the runtime configuration.\n"
            "1. Capture every current value.\n"
            "2. Apply the new configuration.\n"
            "3. Compare the observed result with the acceptance criterion."
        ),
    )

    materializations = validate_layout_source_satisfiability(
        page_id="structured-activity-with-context",
        template=template,
        layout=fallback,
        source_blocks=[source],
    )

    assert materializations
    assert all(page.layout.layout_slug == "content-stack" for page in materializations)


def test_process_flow_distinguishes_scaffolding_from_a_critical_prerequisite() -> None:
    """A factual warning before identical steps cannot disappear as a lead-in."""

    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    process = template.get_layout(template.layout_id("process-flow"))
    fallback = template.get_layout(template.layout_id("content-stack"))
    assert process is not None
    assert fallback is not None
    plain = _block(
        "plain-two-step-process",
        role="reasoning",
        markdown=(
            "按以下步骤操作：\n"
            "1. 保存当前状态。\n"
            "2. 核对执行结果。"
        ),
    )
    guarded = _block(
        "guarded-two-step-process",
        role="reasoning",
        markdown=(
            "仅当校验失败时才继续，且不可逆操作前必须备份当前配置。\n"
            "1. 保存当前状态。\n"
            "2. 核对执行结果。"
        ),
    )

    assert validate_layout_source_satisfiability(
        page_id="plain-two-step-process",
        template=template,
        layout=process,
        source_blocks=[plain],
    )
    with pytest.raises(V6BuildError) as error:
        validate_layout_source_satisfiability(
            page_id="guarded-two-step-process",
            template=template,
            layout=process,
            source_blocks=[guarded],
        )
    assert error.value.failure.code == "template_source_semantic_fidelity_incomplete"
    assert validate_layout_source_satisfiability(
        page_id="guarded-two-step-process-fallback",
        template=template,
        layout=fallback,
        source_blocks=[guarded],
    )


def test_required_steps_slot_accepts_a_single_complete_step_after_pagination() -> None:
    """Capacity pagination may leave one real ordered step on a legal page."""

    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    layout = template.get_layout(template.layout_id("practice-prompt"))
    assert layout is not None
    source = _block(
        "long-ordered-process",
        role="activity",
        markdown=(
            "1. Capture the complete baseline configuration before execution.\n"
            "   - Record every visible field and preserve the original values.\n"
            "   - Attach the observation timestamp and environment identifier."
        ),
    )

    materializations = validate_layout_source_satisfiability(
        page_id="long-ordered-process",
        template=template,
        layout=layout,
        source_blocks=[source],
    )

    assert len(materializations) == 1
    assert materializations[0].layout.layout_slug == "practice-prompt"


def test_process_flow_capacity_matches_the_horizontal_card_renderer() -> None:
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    layout = template.get_layout(template.layout_id("process-flow"))
    assert layout is not None
    steps = next(slot for slot in layout.slots if slot.slot_id == "steps")

    assert steps.max_items == 5
    assert steps.max_chars == 360
    assert steps.capacity_profile == HORIZONTAL_PROCESS_CARDS_V1


def test_classification_contract_measures_each_fixed_card_independently() -> None:
    layout = _BUILTIN_TEMPLATE.get_layout(
        _BUILTIN_TEMPLATE.layout_id("classification-three")
    )
    assert layout is not None
    items_slot = next(slot for slot in layout.slots if slot.slot_id == "items")
    safe = classification_three_card_metrics([
        "Freeze the source state",
        "Run the bounded check",
        "Record the complete result",
    ])
    unsafe = classification_three_card_metrics([
        "Freeze the source state",
        "Run the bounded check",
        "LongIdentifierWithoutBreaks_" * 10,
    ])

    assert items_slot.capacity_profile == CLASSIFICATION_THREE_CARDS_V1
    assert safe["fits"]
    assert not unsafe["fits"]
    assert unsafe["required_heights_pt"][-1] > unsafe["available_height_pt"]


@pytest.mark.parametrize("item_count", range(1, 6))
def test_process_flow_keeps_one_to_five_short_items_on_one_page(
    item_count: int,
) -> None:
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    layout = template.get_layout(template.layout_id("process-flow"))
    assert layout is not None
    steps = [
        "Capture baseline",
        "配置 PlayerController",
        "Run the scene",
        "Compare OnCollisionEnter",
        "保存核验记录",
    ][:item_count]
    source = _block(
        f"short-process-{item_count}",
        role="activity",
        markdown="\n".join(
            f"{index}. {step}" for index, step in enumerate(steps, start=1)
        ),
    )

    materializations = validate_layout_source_satisfiability(
        page_id=f"short-process-{item_count}",
        template=template,
        layout=layout,
        source_blocks=[source],
    )

    assert len(materializations) == 1
    assert horizontal_process_card_metrics(steps)["fits"] is True


def test_process_flow_splits_only_when_real_wrapping_requires_it() -> None:
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    layout = template.get_layout(template.layout_id("process-flow"))
    assert layout is not None
    long_identifier_step = (
        "核验 List<Action<CollisionListener>> 与 "
        "OnCollisionEnter_PlayerController 的调用结果并保存完整诊断记录和环境标识。"
    ) * 2
    steps = [
        "记录基线",
        "Configure PlayerController",
        "运行场景",
        long_identifier_step,
    ]
    source = _block(
        "mixed-process",
        role="activity",
        markdown="\n".join(
            f"{index}. {step}" for index, step in enumerate(steps, start=1)
        ),
    )

    materializations = validate_layout_source_satisfiability(
        page_id="mixed-process",
        template=template,
        layout=layout,
        source_blocks=[source],
    )

    assert len(materializations) == 2
    assert horizontal_process_card_metrics(steps)["fits"] is False
    assert horizontal_process_card_metrics([long_identifier_step])["fits"] is True
    visible = "\n".join(
        _prose_source_text(block)
        for page in materializations
        for block in page.source_blocks
    )
    assert visible.count("List<Action<CollisionListener>>") == 2
    assert all(step in visible for step in steps[:3])


def test_diagram_geometry_preserves_complete_technical_identifiers() -> None:
    labels = [
        "JsonUtility.ToJson",
        "JsonUtility.FromJson<T>",
        "File.WriteAllText",
        "Application.persistentDataPath",
        "PlayerData",
        "SaveGame/LoadGame",
    ]

    metrics = diagram_node_layout_metrics(labels, direction="vertical")

    assert metrics["fits"] is True
    assert metrics["node_count"] == len(labels)
    assert len(metrics["node_boxes"]) == len(labels)
    assert all(metrics["label_fits"])


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
    assert "".join("\n\n".join(rendered_chunks).split()) == "".join(source.split())
    assert all(
        deck_v6._prose_wrapped_line_cost(chunk) <= body_slot.max_lines
        for chunk in rendered_chunks
    )


def test_content_stack_uses_shared_two_column_geometry_at_the_overflow_edge() -> None:
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    layout = template.get_layout(template.layout_id("content-stack"))
    assert layout is not None
    body_slot = next(slot for slot in layout.slots if slot.slot_id == "body")
    source = "\n".join([
        "核对标准",
        "- 层级正确性：界面必须显示清晰的父子缩进关系，父级变化时子级应整体跟随。",
        "- 代码规范性：必须保留 localPosition、transform.position = sourceValue 与完整校验条件。",
        "- 现象一致性：",
        "  - 静止条件下，局部运动轨迹与世界运动轨迹应保持一致。",
        "  - 旋转条件下，世界坐标变化应保留完整曲线特征和复核依据。",
        "  - 每次执行都要保留 timestamp、source_record_identifier 与人工复验签名。",
        "  - 中英文混排不能吞掉 operationBoundary 或省略失败条件与恢复路径。",
        "参考结论",
        "- 正确现象：输入旋转后，原本沿局部 Y 轴运动的节点应沿新的轴向运动。",
        "如果父级持续旋转，子级在世界空间中将形成圆弧，并保留所有观测记录。",
        "- 错误现象：若子级停在原地或只绕自身中心旋转，应检查 local 与 world 的使用边界。",
        "推导依据",
        "- 数学原理：$P_world = P_parent + R_parent × P_child_local$，其中 R 为旋转矩阵。",
        "- 引擎机制：运行时会持续重新计算所有子节点的世界矩阵，并记录最终校验结果。",
        "- 审计要求：逐项比较输入、状态转换、输出、异常日志与签字证据。",
        "- 发布要求：只有完整来源、公式和长标识符都可见时才允许交付。",
        "- 恢复要求：保存点重放必须得到相同页面与相同视觉映射。",
    ])

    metrics = balanced_two_column_body_metrics(source)
    materializations = validate_layout_source_satisfiability(
        page_id="two-column-overflow-edge",
        template=template,
        layout=layout,
        source_blocks=[_block(
            "mixed-geometry-body",
            role="concept",
            markdown=source,
        )],
    )
    rendered_chunks = [
        deck_v6._complete_slot_content(page.source_blocks, "body")
        for page in materializations
    ]

    assert body_slot.capacity_profile == BALANCED_TWO_COLUMN_BODY_V1
    assert metrics["mode"] == "two-column"
    assert max(metrics["wrapped_lines"]) > metrics["maximum_safe_lines"]
    assert not capacity_profile_text_fits(body_slot.capacity_profile, source)
    safe_metrics = balanced_two_column_body_metrics(source.rsplit("\n", 1)[0])
    assert safe_metrics["wrapped_lines"] == [15, 15]
    assert safe_metrics["fits"]
    assert len(materializations) > 1
    assert "".join("\n\n".join(rendered_chunks).split()) == "".join(source.split())
    assert all(
        capacity_profile_text_fits(body_slot.capacity_profile, chunk)
        for chunk in rendered_chunks
    )


def test_portable_wrapping_reserves_for_substitute_font_variance() -> None:
    class ArtificiallyNarrowFont:
        def getlength(self, character: str) -> float:
            return 1.0

    source = "\n".join([
        "*   触发器模式 (Is Trigger = true)：",
        "    *   行为：物体之间可以相互穿透，不产生物理阻挡力。主要用于检测“进入”、“停留”或“离开”某个区域。",
        "    *   前置条件：参与交互的两个物体中，至少有一个必须挂载 Rigidbody 组件（可以是 Kinematic 模式）。如果双方都没有 Rigidbody，即使勾选了 Is Trigger，也不会触发任何事件。",
        "    *   事件路由：调用 OnTriggerEnter(Collider other)、OnTriggerStay 和 OnTriggerExit 系列方法。参数 other 仅包含被触发的 Collider 引用，不包含物理接触细节。",
        "",
        '> 注意：若未满足 Rigidbody 的前置条件，Unity Console 可能会抛出警告 "Trigger collision without rigidbody"，导致逻辑失效。',
        "碰撞回调事件的封装与分层处理模式",
        "直接在 MonoBehaviour 的 OnCollisionEnter 中编写具体业务逻辑（如播放音效、扣除血量、增加分数）会导致代码耦合度高、难以复用和维护。应采用事件驱动解耦架构进行封装。",
    ])

    assert wrapped_line_count(
        source,
        width_pt=10.75 * 72,
        font_size_pt=16,
        font_loader=lambda _: ArtificiallyNarrowFont(),
    ) == 13


def test_wrapped_line_measurement_reuses_identical_geometry_work() -> None:
    class CountingFont:
        def __init__(self) -> None:
            self.calls = 0

        def getlength(self, character: str) -> float:
            self.calls += 1
            return 8.0

    font = CountingFont()

    def load_font(_font_size_px: int):
        return font

    wrapped_line_count.cache_clear()
    first = wrapped_line_count(
        "相同正文 repeated identifier_2026",
        width_pt=220,
        font_size_pt=16,
        font_loader=load_font,
    )
    calls_after_first = font.calls
    second = wrapped_line_count(
        "相同正文 repeated identifier_2026",
        width_pt=220,
        font_size_pt=16,
        font_loader=load_font,
    )

    assert first == second
    assert calls_after_first > 0
    assert font.calls == calls_after_first
    wrapped_line_count.cache_clear()


def test_balanced_body_geometry_uses_the_text_frame_inner_width() -> None:
    metrics = balanced_two_column_body_metrics(
        "完整来源正文用于验证可编辑文本框的真实内边距。"
    )

    assert metrics["mode"] == "single-column"
    assert metrics["text_width_pt"] == pytest.approx((10.75 - 0.02) * 72)


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
