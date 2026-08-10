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
