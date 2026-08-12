from pathlib import Path
from types import SimpleNamespace

from pptx import Presentation
from pptx.enum.text import MSO_ANCHOR

from course_document import CourseBlock, CourseDocument, CourseSection, refresh_document_revision
from course_presentation_graph import compile_course_presentation_graph
from representation_compiler import export_slide_deck_pptx
from slide_deck_renderer import audit_exported_pptx
from slide_deck_v6 import (
    SlideStoryBatchV3,
    SlideStoryPageV3,
    SlideStoryPlanV3,
    SlideVisualDecisionV2,
    SlideVisualPlanV2,
    compile_slide_deck_v6,
)
from slide_deck_v6_renderer import adapt_v6_page_to_slide_spec, export_slide_deck_v6_pptx
from template_layout_contract import compile_builtin_template_layout_contract_v1


def _code_deck():
    document = refresh_document_revision(
        CourseDocument(
            course_id="generic-code-render-fixture",
            title="Event-driven interaction",
            sections=[CourseSection(section_id="chapter-1", title="Callbacks", position=0)],
            blocks=[
                CourseBlock(
                    block_id="condition",
                    section_id="chapter-1",
                    position=0,
                    role="concept",
                    payload={"markdown": "The handler runs only after the event is emitted."},
                ),
                CourseBlock(
                    block_id="implementation",
                    section_id="chapter-1",
                    position=1,
                    role="example",
                    kind="code",
                    payload={"markdown": "function onEvent(value) {\n  return validate(value);\n}"},
                ),
                CourseBlock(
                    block_id="result",
                    section_id="chapter-1",
                    position=2,
                    role="feedback",
                    payload={"markdown": "A rejected value remains visible with its validation reason."},
                ),
            ],
        )
    )
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    unit = graph.units[0]
    layout_id = template.layout_id("evidence-code")
    story = SlideStoryPlanV3(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        batches=[SlideStoryBatchV3(
            batch_id="story-1",
            chapter_id="chapter-1",
            provider="fixture-pool",
            model="fixture-story",
            duration_ms=1,
            attempts=1,
            validation_status="passed",
            pages=[SlideStoryPageV3(
                page_id="page-code",
                teaching_unit_id=unit.teaching_unit_id,
                template_layout_id=layout_id,
                title="Connect the event to observable feedback",
                source_block_ids=unit.primary_block_ids,
                page_ordinal=0,
            )],
        )],
    )
    visual = SlideVisualPlanV2(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        decisions=[SlideVisualDecisionV2(
            page_id="page-code",
            decision="code",
            source_block_ids=unit.primary_block_ids,
            resolved_template_layout_id=layout_id,
        )],
    )
    return document, compile_slide_deck_v6(document, graph, story, visual, template)


def _practice_code_deck():
    document = refresh_document_revision(CourseDocument(
        course_id="generic-practice-code-render-fixture",
        title="Sensor verification",
        sections=[CourseSection(section_id="practice", title="Verify", position=0)],
        blocks=[CourseBlock(
            block_id="verification-task",
            section_id="practice",
            position=0,
            role="activity",
            payload={"markdown": (
                "1. Capture the sensor reading.\n"
                "2. Compare it with the declared threshold.\n"
                "3. Record the decision and evidence.\n\n"
                "4. Repeat the check with a boundary value.\n"
                "5. Preserve the original reading.\n"
                "6. Explain any rejected result.\n"
                "7. Submit the signed verification record.\n\n"
                "```python\n"
                "def accept(reading, threshold):\n"
                "    return reading <= threshold\n"
                "```"
            )},
        )],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    unit = graph.units[0]
    layout_id = template.layout_id("practice-code")
    story = SlideStoryPlanV3(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        batches=[SlideStoryBatchV3(
            batch_id="story-practice-code",
            chapter_id="practice",
            provider="fixture-pool",
            model="fixture-story",
            duration_ms=1,
            attempts=1,
            validation_status="passed",
            pages=[SlideStoryPageV3(
                page_id="practice-code-page",
                teaching_unit_id=unit.teaching_unit_id,
                template_layout_id=layout_id,
                title="Verify the reading before accepting it",
                source_block_ids=unit.primary_block_ids,
                page_ordinal=0,
            )],
        )],
    )
    visual = SlideVisualPlanV2(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        decisions=[SlideVisualDecisionV2(
            page_id="practice-code-page",
            decision="code",
            source_block_ids=unit.primary_block_ids,
            resolved_template_layout_id=layout_id,
        )],
    )
    return compile_slide_deck_v6(document, graph, story, visual, template)


def _dense_table_deck():
    table = "\n".join([
        "| Check | Required evidence | Result |",
        "| --- | --- | --- |",
        *(
            f"| Field item {index} | Record the observation condition and supporting evidence {index} | Verified |"
            for index in range(1, 9)
        ),
    ])
    document = refresh_document_revision(
        CourseDocument(
            course_id="generic-field-table-render-fixture",
            title="Field evidence review",
            sections=[
                CourseSection(
                    section_id="field-review",
                    title="Review the evidence",
                    position=0,
                )
            ],
            blocks=[
                CourseBlock(
                    block_id="interpretation",
                    section_id="field-review",
                    position=0,
                    role="activity",
                    payload={
                        "markdown": (
                            "Compare every recorded condition with the required evidence, "
                            "then identify the first unsupported observation before publishing "
                            "the field result. "
                        ) * 3,
                    },
                ),
                CourseBlock(
                    block_id="evidence-table",
                    section_id="field-review",
                    position=1,
                    kind="review_checkpoint",
                    role="feedback",
                    payload={"markdown": table},
                ),
            ],
        )
    )
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    unit = graph.units[0]
    layout_id = template.layout_id("evidence-table")
    story = SlideStoryPlanV3(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        batches=[
            SlideStoryBatchV3(
                batch_id="story-table",
                chapter_id="field-review",
                provider="fixture-pool",
                model="fixture-story",
                duration_ms=1,
                attempts=1,
                validation_status="passed",
                pages=[
                    SlideStoryPageV3(
                        page_id="field-table-page",
                        teaching_unit_id=unit.teaching_unit_id,
                        template_layout_id=layout_id,
                        title="Review the evidence",
                        source_block_ids=unit.primary_block_ids,
                        page_ordinal=0,
                    )
                ],
            )
        ],
    )
    visual = SlideVisualPlanV2(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        decisions=[
            SlideVisualDecisionV2(
                page_id="field-table-page",
                decision="table",
                source_block_ids=unit.primary_block_ids,
                resolved_template_layout_id=layout_id,
            )
        ],
    )
    return compile_slide_deck_v6(document, graph, story, visual, template)


def _wide_markdown_table_deck():
    table = "\n".join([
        "| Stage | Standard | Evidence | Basis | Repair |",
        "| :--- | :--- | :--- | :--- :--- |",
        (
            "| **Observe** | Record the `site` \\| time, weather, and observer before "
            "sampling begins | The log preserves the original field condition | "
            "A stable context makes later comparisons meaningful | **Error**: context "
            "is missing.<br>**Repair**: restore it from the signed field note |"
        ),
        (
            "| **Compare** | Check every observation against the declared criterion | "
            "The first mismatch remains visible | Evidence must precede interpretation | "
            "**Error**: a conclusion replaces the observation.<br>**Repair**: separate them |"
        ),
    ])
    support = (
        "The full audit record remains available for traceability and later review. "
        "Compare each field observation with its declared evidence before publishing."
    )
    summary = "Compare each field observation with its declared evidence before publishing."
    document = refresh_document_revision(CourseDocument(
        course_id="generic-field-audit",
        title="Field audit",
        sections=[CourseSection(section_id="audit", title="Audit", position=0)],
        blocks=[
            CourseBlock(
                block_id="audit-table",
                section_id="audit",
                position=0,
                role="feedback",
                kind="table",
                payload={"markdown": table},
            ),
            CourseBlock(
                block_id="audit-interpretation",
                section_id="audit",
                position=1,
                role="reasoning",
                payload={"markdown": support},
            ),
        ],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    layout_id = template.layout_id("evidence-table")
    unit = graph.units[0]
    story = SlideStoryPlanV3(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        batches=[SlideStoryBatchV3(
            batch_id="story-wide-table",
            chapter_id="audit",
            provider="fixture-pool",
            model="fixture-story",
            duration_ms=1,
            attempts=1,
            validation_status="passed",
            pages=[SlideStoryPageV3(
                page_id="wide-table-page",
                teaching_unit_id=unit.teaching_unit_id,
                template_layout_id=layout_id,
                title="Compare the field evidence",
                summary=summary,
                source_block_ids=unit.primary_block_ids,
                page_ordinal=0,
            )],
        )],
    )
    visual = SlideVisualPlanV2(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        decisions=[SlideVisualDecisionV2(
            page_id="wide-table-page",
            decision="table",
            source_block_ids=unit.primary_block_ids,
            resolved_template_layout_id=layout_id,
        )],
    )
    return (
        compile_slide_deck_v6(document, graph, story, visual, template),
        template,
        summary,
    )


def _long_cell_table_deck():
    table = "\n".join([
        "| 观察现象 | 判断依据 | 修正动作 |",
        "| --- | --- | --- |",
        (
            "| The declared field observation and its acceptance criterion could not be reconciled | 原始记录必须同时保留地点、时间、天气、观察者和采样批次，"
            "才能支持后续复核 | 从签字确认的现场记录恢复全部环境字段后再发布结论 |"
        ),
        (
            "| 对照结论缺少证据 | 每项结论都必须指向对应观察条件、验收标准和原始测量值，"
            "不能用解释代替证据 | 分离观察事实与研究者解释并重新执行逐项对照 |"
        ),
        (
            "| 审核过程无法追溯 | 审核者身份、证据修订号和最终决定必须在同一记录中保持可见，"
            "以便复查 | 重新打开审核并补齐缺失的来源信息后才能批准 |"
        ),
        (
            "| 重复测量结果冲突 | 多次测量必须使用相同单位、采样窗口和校准基准，"
            "否则不能直接比较 | 统一记录口径并在审核轨迹中解释每个排除值 |"
        ),
    ])
    document = refresh_document_revision(CourseDocument(
        course_id="generic-field-review-with-long-table-cells",
        title="Field evidence review",
        sections=[CourseSection(section_id="review", title="Review", position=0)],
        blocks=[CourseBlock(
            block_id="review-table",
            section_id="review",
            position=0,
            role="feedback",
            kind="review_checkpoint",
            payload={"markdown": table},
        )],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    layout_id = template.layout_id("evidence-table")
    unit = graph.units[0]
    story = SlideStoryPlanV3(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        batches=[SlideStoryBatchV3(
            batch_id="story-long-table",
            chapter_id="review",
            provider="fixture-pool",
            model="fixture-story",
            duration_ms=1,
            attempts=1,
            validation_status="passed",
            pages=[SlideStoryPageV3(
                page_id="long-table-page",
                teaching_unit_id=unit.teaching_unit_id,
                template_layout_id=layout_id,
                title="对照结论缺少证据",
                summary=(
                    "核对每项观察的环境条件、原始证据和验收标准；若结论缺少来源、审核轨迹"
                    "或统一测量口径，应先补齐记录并重新执行逐项对照，再决定是否发布。"
                ),
                source_block_ids=unit.primary_block_ids,
                page_ordinal=0,
            )],
        )],
    )
    visual = SlideVisualPlanV2(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        decisions=[SlideVisualDecisionV2(
            page_id="long-table-page",
            decision="table",
            source_block_ids=unit.primary_block_ids,
            resolved_template_layout_id=layout_id,
        )],
    )
    return compile_slide_deck_v6(document, graph, story, visual, template)


def _chapter_entry_at_contract_capacity_deck():
    driving_question = (
        "开展实地观察前，怎样确认地点、时间、天气、观察者与采样批次均已记录，"
        "并且每项结论都能追溯到原始证据、验收标准和审核修订，从而避免用解释替代事实？"
        "若任一字段缺失，应先停止发布并返回现场记录补齐来源，之后重新核对。"
    )
    document = refresh_document_revision(CourseDocument(
        course_id="generic-field-orientation",
        title="Field observation",
        sections=[CourseSection(section_id="orientation", title="Orientation", position=0)],
        blocks=[CourseBlock(
            block_id="orientation-question",
            section_id="orientation",
            position=0,
            role="objective",
            payload={"markdown": driving_question},
        )],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    layout_id = template.layout_id("chapter-entry")
    unit = graph.units[0]
    story = SlideStoryPlanV3(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        batches=[SlideStoryBatchV3(
            batch_id="story-orientation",
            chapter_id="orientation",
            provider="fixture-pool",
            model="fixture-story",
            duration_ms=1,
            attempts=1,
            validation_status="passed",
            pages=[SlideStoryPageV3(
                page_id="orientation-page",
                teaching_unit_id=unit.teaching_unit_id,
                template_layout_id=layout_id,
                title="开展实地观察前",
                source_block_ids=unit.primary_block_ids,
                page_ordinal=0,
            )],
        )],
    )
    visual = SlideVisualPlanV2(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        decisions=[SlideVisualDecisionV2(
            page_id="orientation-page",
            decision="text_native",
            source_block_ids=unit.primary_block_ids,
            resolved_template_layout_id=layout_id,
            degraded=True,
            degradation_reason="visual_text_native",
        )],
    )
    return compile_slide_deck_v6(document, graph, story, visual, template)


def _ordered_step_deck():
    document = refresh_document_revision(CourseDocument(
        course_id="generic-lab-transfer",
        title="Laboratory transfer",
        sections=[CourseSection(
            section_id="transfer",
            title="Transfer the specimen",
            position=0,
        )],
        blocks=[CourseBlock(
            block_id="transfer-steps",
            section_id="transfer",
            position=0,
            role="activity",
            payload={"markdown": (
                "Complete the transfer in order:\n\n"
                "1. **Verify the specimen**\n"
                "   - Match the identifier to the record.\n"
                "2. **Close the container**\n"
                "   - Confirm the seal is intact.\n"
                "3. **Record the handoff**\n"
                "   - Capture the receiver name."
            )},
        )],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    unit = graph.units[0]
    layout_id = template.layout_id("practice-prompt")
    story = SlideStoryPlanV3(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        batches=[SlideStoryBatchV3(
            batch_id="story-transfer",
            chapter_id="transfer",
            provider="fixture-pool",
            model="fixture-story",
            duration_ms=1,
            attempts=1,
            validation_status="passed",
            pages=[SlideStoryPageV3(
                page_id="transfer-page",
                teaching_unit_id=unit.teaching_unit_id,
                template_layout_id=layout_id,
                title="Transfer the specimen",
                source_block_ids=unit.primary_block_ids,
                page_ordinal=0,
            )],
        )],
    )
    visual = SlideVisualPlanV2(
        source_document_revision=document.document_revision,
        template_digest=template.template_digest,
        decisions=[SlideVisualDecisionV2(
            page_id="transfer-page",
            decision="text_native",
            source_block_ids=unit.primary_block_ids,
            resolved_template_layout_id=layout_id,
        )],
    )
    return compile_slide_deck_v6(document, graph, story, visual, template)


def test_v6_ordered_steps_render_as_numbered_lines_in_pptx(tmp_path: Path) -> None:
    deck = _ordered_step_deck()
    spec = adapt_v6_page_to_slide_spec(deck.pages[0])
    process = next(block for block in spec.blocks if block.type == "process")

    assert spec.quality["resolved_layout"] == "practice-sequence"
    assert process.items == [
        "Verify the specimen: Match the identifier to the record.",
        "Close the container: Confirm the seal is intact.",
        "Record the handoff: Capture the receiver name.",
    ]

    output = export_slide_deck_v6_pptx(deck, tmp_path / "ordered-steps.pptx")
    presentation = Presentation(output)
    visible_text = "\n".join(
        shape.text
        for shape in presentation.slides[0].shapes
        if hasattr(shape, "text_frame") and shape.text.strip()
    )

    assert "01\nVerify the specimen" in visible_text
    assert "02\nClose the container" in visible_text
    assert "03\nRecord the handoff" in visible_text


def test_v6_ordered_steps_separate_action_titles_from_explanations(tmp_path: Path) -> None:
    deck = _ordered_step_deck()

    output = export_slide_deck_v6_pptx(deck, tmp_path / "ordered-step-path.pptx")
    presentation = Presentation(output)
    text_shapes = [
        shape.text.strip()
        for shape in presentation.slides[0].shapes
        if hasattr(shape, "text_frame") and shape.text.strip()
    ]

    assert "Verify the specimen" in text_shapes
    assert "Match the identifier to the record." in text_shapes
    assert "Close the container" in text_shapes
    assert "Confirm the seal is intact." in text_shapes
    assert "Record the handoff" in text_shapes
    assert "Capture the receiver name." in text_shapes


def test_v6_dense_ordered_steps_pass_the_export_frame_audit(tmp_path: Path) -> None:
    deck = _ordered_step_deck()
    task = next(region for region in deck.pages[0].regions if region.slot_id == "task")
    task.content = "\n".join([
        "采集样本：在指定样区的观测窗口内记录采集时间、地点、观察者和完整的仪器编号。",
        "密封容器：检查盖体是否牢固，并确认防拆标记在整个交接过程里保持清晰可见。",
        "标注证据：逐字复制完整样本标识、采样窗口和现场记录编号，不能省略来源字段。",
        "转移包裹：在放行前记录接收人、交接时间、运输路线和当前保管条件。",
        "异常证据模拟与交接记录修正（可选核验）：把签字回执与原始记录逐项比较，并在发布结论前补齐所有缺失字段。",
    ])

    output = export_slide_deck_v6_pptx(deck, tmp_path / "ordered-step-dense.pptx")
    report = audit_exported_pptx(output, expected_slide_count=1)

    assert report["passed"], report["blockers"]


def test_v6_materializes_typed_template_slots_without_mixing_code_and_explanation() -> None:
    _document, deck = _code_deck()
    page = deck.pages[0]
    regions = {region.slot_id: region for region in page.regions}

    assert page.resolved_layout.endswith("/evidence-code")
    assert regions["code"].content_kind == "code"
    assert "function onEvent" in regions["code"].content
    assert regions["code"].source_block_ids == ["implementation"]
    assert regions["annotation"].content_kind == "body"
    assert "event is emitted" in regions["annotation"].content
    assert "validation reason" in regions["annotation"].content
    assert set(regions["annotation"].source_block_ids) == {"condition", "result"}


def test_v6_web_and_pptx_adapters_resolve_the_same_template_page(tmp_path: Path) -> None:
    document, deck = _code_deck()
    page = deck.pages[0]
    renderer_slide = adapt_v6_page_to_slide_spec(page)

    assert renderer_slide.quality["v6_template_layout_id"] == page.resolved_layout
    assert renderer_slide.quality["v6_layout_slug"] == "evidence-code"
    assert renderer_slide.quality["resolved_layout"] == "code"
    assert renderer_slide.source_block_ids == page.source_block_ids

    output = export_slide_deck_v6_pptx(
        deck.model_dump(mode="json"),
        tmp_path / "v6-code.pptx",
    )
    presentation = Presentation(output)
    assert len(presentation.slides) == 1
    assert "function onEvent" in "\n".join(
        shape.text for shape in presentation.slides[0].shapes if hasattr(shape, "text")
    )
    notes = presentation.slides[0].notes_slide.notes_text_frame.text
    assert document.document_revision in notes
    assert "The handler runs only after the event is emitted." in notes
    assert "A rejected value remains visible" in notes


def test_evidence_code_contract_capacity_survives_pptx_frame_audit(tmp_path: Path) -> None:
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    layout = template.get_layout(template.layout_id("evidence-code"))
    assert layout is not None
    slots = {slot.slot_id: slot for slot in layout.slots}
    code_slot = slots["code"]
    annotation_slot = slots["annotation"]
    code_line_width = max(1, code_slot.max_chars // code_slot.max_lines)
    code_samples = {
        "logical-lines": "\n".join(
            f"stage_{index:02d}: " + "validate(input);".ljust(code_line_width - 10, " ")
            for index in range(code_slot.max_lines)
        )[: code_slot.max_chars],
        "wide-literal": ("const label = \"" + "状态" * code_slot.max_chars)[: code_slot.max_chars],
    }
    for sample_name, code in code_samples.items():
        _document, deck = _code_deck()
        regions = {region.slot_id: region for region in deck.pages[0].regions}
        regions["code"].content = code
        regions["annotation"].content = "验证输入事件、保留结果并说明失败边界。" * 20
        regions["annotation"].content = regions["annotation"].content[: annotation_slot.max_chars]

        output = export_slide_deck_v6_pptx(
            deck,
            tmp_path / f"v6-code-capacity-{sample_name}.pptx",
        )
        report = audit_exported_pptx(output, expected_slide_count=1)

        assert report["passed"], report["blockers"]


def test_evidence_table_renders_the_table_once_and_keeps_interpretation_in_a_summary_band(
    tmp_path: Path,
) -> None:
    deck = _dense_table_deck()
    assert 1 <= len(deck.pages) <= 3
    split_slide = adapt_v6_page_to_slide_spec(deck.pages[0])

    table_row_counts = []
    for page in deck.pages:
        table_region = next(region for region in page.regions if region.content_kind == "table")
        table_row_counts.append(
            len([line for line in table_region.content.splitlines() if line.strip()]) - 2
        )

    assert split_slide.quality["v6_layout_variant"] == "table-wide-with-summary"
    assert split_slide.quality["v6_artifact_support_mode"] == "band"
    for page in deck.pages[1:]:
        continuation_slide = adapt_v6_page_to_slide_spec(page)
        assert continuation_slide.quality["v6_layout_variant"] == "table-continuation"
        assert continuation_slide.quality["v6_artifact_support_mode"] == "full"
    assert sum(table_row_counts) == 8

    output = export_slide_deck_v6_pptx(
        deck,
        tmp_path / "v6-dense-table.pptx",
    )
    report = audit_exported_pptx(output, expected_slide_count=len(deck.pages))

    assert report["passed"], report["blockers"]
    presentation = Presentation(output)
    for slide in presentation.slides:
        table = next(shape.table for shape in slide.shapes if shape.has_table)
        assert all(
            cell.vertical_anchor == MSO_ANCHOR.MIDDLE
            for row in table.rows
            for cell in row.cells
        )


def test_wide_table_summary_band_fits_three_lines_at_readable_size(tmp_path: Path) -> None:
    deck = _dense_table_deck()
    interpretation = next(
        region
        for region in deck.pages[0].regions
        if region.slot_id == "interpretation"
    )
    interpretation.content = ((
        "核对观察条件、原始记录、推导依据与异常修订，确认每个结论都能回溯到签字证据；"
        "同时保留地点、时间、观察者、仪器与采样窗口，避免把解释误写成事实。"
    ) * 2)[:120]

    output = export_slide_deck_v6_pptx(deck, tmp_path / "wide-table-summary-band.pptx")
    report = audit_exported_pptx(output, expected_slide_count=len(deck.pages))

    assert report["passed"], report["blockers"]


def test_wide_markdown_table_uses_llm_summary_and_exports_template_safe_cells(
    tmp_path: Path,
) -> None:
    deck, template, summary = _wide_markdown_table_deck()
    page = deck.pages[0]
    regions = {region.slot_id: region for region in page.regions}

    assert regions["interpretation"].content == summary
    adapted = adapt_v6_page_to_slide_spec(page)
    assert adapted.quality["v6_layout_variant"] == "table-wide-with-summary"
    assert adapted.quality["v6_artifact_support_mode"] == "band"
    assert len(deck.pages) == 2
    continuation = adapt_v6_page_to_slide_spec(deck.pages[1])
    assert continuation.quality["v6_layout_variant"] == "table-row-detail"

    compiled_table_text = "\n".join(
        region.content
        for compiled_page in deck.pages
        for region in compiled_page.regions
        if region.content_kind == "table"
    )
    assert (
        "Record the site \\| time, weather, and observer before sampling begins"
        in compiled_table_text
    )
    assert "restore it from the signed field note" in compiled_table_text
    assert "separate them" in compiled_table_text

    output = export_slide_deck_v6_pptx(deck, tmp_path / "wide-table.pptx")
    report = audit_exported_pptx(output, expected_slide_count=len(deck.pages))
    assert report["passed"], report["blockers"]

    presentation = Presentation(output)
    table_shape = next(shape for shape in presentation.slides[0].shapes if shape.has_table)
    rendered_rows = [[cell.text for cell in row.cells] for row in table_shape.table.rows]
    rendered_text = "\n".join(
        shape.text
        for slide in presentation.slides
        for shape in slide.shapes
        if hasattr(shape, "text")
    )
    rendered_text += "\n" + "\n".join(cell for row in rendered_rows for cell in row)
    assert len(rendered_rows) == 2
    assert len(rendered_rows[0]) == 5
    assert "site | time" in rendered_text
    assert not any(marker in rendered_text for marker in ("**", "`", "<br>"))
    assert "Record the site | time, weather, and observer before sampling begins" in rendered_text
    assert "restore it from the signed field note" in rendered_text
    assert "…" not in rendered_text
    assert not any(set(cell.replace(" ", "")) <= {":", "-"} for cell in rendered_rows[1])


def test_three_column_table_with_long_cells_is_split_before_export_overflow(
    tmp_path: Path,
) -> None:
    deck = _long_cell_table_deck()

    assert len(deck.pages) == 2
    assert deck.pages[1].continuation_of_page_id == deck.pages[0].page_id
    adapted = [adapt_v6_page_to_slide_spec(page) for page in deck.pages]
    assert adapted[0].quality["v6_layout_variant"] == "table-wide-with-summary"
    assert adapted[1].quality["v6_layout_variant"] == "table-row-detail"
    table_content = "\n".join(
        region.content
        for page in deck.pages
        for region in page.regions
        if region.content_kind == "table"
    )
    assert "The declared field observation and its acceptance criterion could not be reconciled" in table_content
    assert "原始记录必须同时保留地点、时间、天气、观察者和采样批次，才能支持后续复核" in table_content
    assert "重新打开审核并补齐缺失的来源信息后才能批准" in table_content
    assert "…" not in table_content

    output = export_slide_deck_v6_pptx(deck, tmp_path / "long-cell-table.pptx")
    report = audit_exported_pptx(output, expected_slide_count=len(deck.pages))

    assert report["passed"], report["blockers"]


def test_chapter_entry_renderer_honors_declared_driving_question_capacity(
    tmp_path: Path,
) -> None:
    deck = _chapter_entry_at_contract_capacity_deck()

    output = export_slide_deck_v6_pptx(deck, tmp_path / "chapter-entry-capacity.pptx")
    report = audit_exported_pptx(output, expected_slide_count=1)

    assert report["passed"], report["blockers"]


def test_code_excerpt_ends_at_a_complete_source_unit_instead_of_a_trailing_comment() -> None:
    source = "\n".join([
        "using Example.Runtime;",
        "",
        "public class AuditRunner",
        "{",
        "    void FirstCheck()",
        "    {",
        "        VerifyContext();",
        "    }",
        "",
        "    // The second check runs after the first result is visible",
        "    void SecondCheck()",
        "    {",
        "        VerifyEvidence();",
        "    }",
        "}",
    ])
    block = CourseBlock(
        block_id="generic-code",
        section_id="audit",
        position=0,
        role="example",
        kind="code",
        payload={"markdown": source},
    )

    from slide_deck_v6 import _bounded_slot_content

    excerpt = _bounded_slot_content(
        [block],
        slot_kind="code",
        max_chars=300,
        max_items=0,
        max_lines=10,
        max_rows=0,
    )

    assert not excerpt.rstrip().splitlines()[-1].lstrip().startswith("//")
    assert excerpt.count("{") == excerpt.count("}")
    assert all(line in source.splitlines() for line in excerpt.splitlines())


def test_code_excerpt_ignores_braces_inside_strings_and_comments() -> None:
    source = "\n".join([
        "public class Formatter",
        "{",
        "    void Render()",
        "    {",
        '        var label = "{pending}";',
        "        Publish(label); // unmatched } belongs to the comment",
        "    }",
        "",
        "    void Archive()",
        "    {",
        "        Save();",
        "    }",
        "}",
    ])
    block = CourseBlock(
        block_id="generic-brace-code",
        section_id="generic-section",
        position=0,
        role="example",
        kind="code",
        payload={"markdown": source},
    )

    from slide_deck_v6 import _bounded_slot_content

    excerpt = _bounded_slot_content(
        [block],
        slot_kind="code",
        max_chars=220,
        max_items=0,
        max_lines=8,
        max_rows=0,
    )

    assert "void Render()" in excerpt
    assert excerpt.rstrip().endswith("}")
    assert all(line in source.splitlines() for line in excerpt.splitlines())


def test_chapter_entry_title_contract_allows_only_declared_safe_wrapping(
    tmp_path: Path,
) -> None:
    _document, deck = _code_deck()
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    layout = template.get_layout(template.layout_id("chapter-entry"))
    assert layout is not None
    title_slot = next(slot for slot in layout.slots if slot.slot_kind == "title")
    page = deck.pages[0]
    page.title = ("教学单元逻辑顺序与来源证据" * 4)[: title_slot.max_chars]
    page.title_max_lines = title_slot.max_lines
    page.resolved_layout = layout.template_layout_id
    page.visual_decision.resolved_template_layout_id = layout.template_layout_id

    output = export_slide_deck_v6_pptx(deck, tmp_path / "v6-chapter-title.pptx")
    report = audit_exported_pptx(output, expected_slide_count=1)

    assert report["passed"], report["blockers"]
    title_shapes = [
        shape
        for shape in Presentation(output).slides[0].shapes
        if getattr(shape, "has_text_frame", False)
        and str(shape.text or "").strip() == page.title
    ]
    assert len(title_shapes) == 1
    assert f"[v6-title-max-lines={title_slot.max_lines}]" in title_shapes[0].name


def test_official_representation_export_dispatches_v6_without_legacy_schema_coercion(
    tmp_path: Path,
) -> None:
    _document, deck = _code_deck()
    spec = SimpleNamespace(
        representation_type="slide_deck",
        payload={"content": deck.model_dump(mode="json")},
    )

    output = export_slide_deck_pptx(spec, tmp_path / "official-v6.pptx")

    assert output.is_file()
    assert len(Presentation(output).slides) == len(deck.pages)


def test_practice_code_layout_exports_numbered_steps_and_readable_code(
    tmp_path: Path,
) -> None:
    deck = _practice_code_deck()
    page = deck.pages[0]

    assert page.resolved_layout.endswith("/practice-code")
    assert {region.content_kind for region in page.regions} == {"steps", "code"}
    renderer_slide = adapt_v6_page_to_slide_spec(page)
    assert renderer_slide.quality["resolved_layout"] == "practice-artifact"
    assert [block.type for block in renderer_slide.blocks] == ["code", "process"]

    output = export_slide_deck_v6_pptx(deck, tmp_path / "practice-code.pptx")
    report = audit_exported_pptx(output, expected_slide_count=1)

    assert report["passed"], report["blockers"]
    visible_text = "\n".join(
        str(shape.text or "")
        for shape in Presentation(output).slides[0].shapes
        if getattr(shape, "has_text_frame", False)
    )
    assert "01" in visible_text
    assert "02" in visible_text
    assert "07" in visible_text
    assert "def accept" in visible_text


def test_pptx_renderer_applies_the_frozen_template_theme_overrides(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import slide_deck_v6_renderer as renderer

    _document, deck = _code_deck()
    deck.template_theme_overrides = {
        "accent": "315E7D",
        "title_font": "Noto Serif SC",
    }
    observed: dict[str, str] = {}
    original = renderer._render_slide

    def capture(slide, unit, page_number, page_count, theme, assets):
        observed.update(theme)
        return original(slide, unit, page_number, page_count, theme, assets)

    monkeypatch.setattr(renderer, "_render_slide", capture)
    renderer.export_slide_deck_v6_pptx(deck, tmp_path / "personal-theme.pptx")

    assert observed["accent"] == "315E7D"
    assert observed["title_font"] == "Noto Serif SC"
