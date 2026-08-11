from pathlib import Path
from types import SimpleNamespace

from pptx import Presentation

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
            "| **Observe** | Record the `site`, time, weather, and observer before "
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


def test_evidence_table_renders_the_table_once_and_keeps_interpretation_in_its_own_frame(
    tmp_path: Path,
) -> None:
    deck = _dense_table_deck()
    assert len(deck.pages) == 3
    split_slide = adapt_v6_page_to_slide_spec(deck.pages[0])
    continuation_slide = adapt_v6_page_to_slide_spec(deck.pages[1])

    table_row_counts = []
    for page in deck.pages:
        table_region = next(region for region in page.regions if region.content_kind == "table")
        table_row_counts.append(
            len([line for line in table_region.content.splitlines() if line.strip()]) - 2
        )

    assert split_slide.quality["v6_layout_variant"] == "table-with-interpretation"
    assert split_slide.quality["v6_artifact_support_mode"] == "split"
    assert continuation_slide.quality["v6_layout_variant"] == "table-continuation"
    assert continuation_slide.quality["v6_artifact_support_mode"] == "full"
    assert table_row_counts == [2, 4, 2]

    output = export_slide_deck_v6_pptx(
        deck,
        tmp_path / "v6-dense-table.pptx",
    )
    report = audit_exported_pptx(output, expected_slide_count=len(deck.pages))

    assert report["passed"], report["blockers"]


def test_wide_markdown_table_uses_llm_summary_and_exports_template_safe_cells(
    tmp_path: Path,
) -> None:
    deck, template, summary = _wide_markdown_table_deck()
    page = deck.pages[0]
    regions = {region.slot_id: region for region in page.regions}

    assert regions["interpretation"].content == summary

    output = export_slide_deck_v6_pptx(deck, tmp_path / "wide-table.pptx")
    report = audit_exported_pptx(output, expected_slide_count=1)
    assert report["passed"], report["blockers"]

    presentation = Presentation(output)
    table_shape = next(shape for shape in presentation.slides[0].shapes if shape.has_table)
    rendered_rows = [[cell.text for cell in row.cells] for row in table_shape.table.rows]
    rendered_text = "\n".join(cell for row in rendered_rows for cell in row)
    assert len(rendered_rows) == 3
    assert not any(marker in rendered_text for marker in ("**", "`", "<br>"))
    assert not any(set(cell.replace(" ", "")) <= {":", "-"} for cell in rendered_rows[1])

    layout = template.get_layout(template.layout_id("evidence-table"))
    assert layout is not None
    table_slot = next(slot for slot in layout.slots if slot.slot_kind == "table")
    assert max(len(cell) for row in rendered_rows[1:] for cell in row) <= (
        table_slot.split_column_chars * 2
    )


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
