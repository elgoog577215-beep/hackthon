import inspect
import re

import pytest

from course_document import CourseBlock, CourseDocument, CourseSection, refresh_document_revision
from course_presentation_graph import compile_course_presentation_graph
from slide_deck_v6 import (
    SlideStoryBatchV3,
    SlideStoryPageV3,
    SlideStoryPlanV3,
    SlideVisualDecisionV2,
    SlideVisualPlanV2,
    V6BuildError,
    _bounded_slot_content,
    _complete_sentence_excerpt,
    _display_excerpt,
    build_signature_v6,
    compile_shadow_chapter_document,
    compile_ppt_source_contract_v2,
    compile_slide_deck_v6,
    validate_slide_story_plan_v3,
    validate_slide_visual_plan_v2,
)
from template_layout_contract import compile_builtin_template_layout_contract_v1


def test_sentence_excerpt_never_exceeds_its_template_budget():
    source = "A source sentence with no early punctuation and several additional words"

    excerpt = _complete_sentence_excerpt(source, 35)

    assert len(excerpt) <= 35
    assert excerpt.endswith("…")
    assert excerpt[:-1] in source


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


def test_item_slot_uses_source_excerpts_within_template_limits():
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

    content = _bounded_slot_content(
        [block],
        slot_kind="items",
        max_chars=90,
        max_items=3,
        max_lines=0,
        max_rows=0,
    )

    assert len(content) <= 90
    assert len(content.splitlines()) <= 3
    assert all(line.rstrip("…") in block.payload["markdown"] for line in content.splitlines())


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

    assert baseline["compiler_version"] == "slide_deck_v6_compiler_v1"
    assert baseline["signature"] != changed_source["signature"]
    assert baseline["signature"] != changed_template["signature"]


def _valid_story(document: CourseDocument):
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    pages = []
    for index, unit in enumerate(graph.units):
        layout_slug = (
            "evidence-table"
            if "table" in unit.artifact_kinds
            else "practice-feedback"
            if unit.teaching_intent == "practice_feedback"
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


def test_story_plan_rejects_untraceable_factual_tokens() -> None:
    document = _cross_subject_document()
    graph, template, story = _valid_story(document)
    story.batches[0].pages[0].summary = "调查准确率达到 99.9%。"

    with pytest.raises(V6BuildError, match="story_unsupported_fact"):
        validate_slide_story_plan_v3(story, graph, template)


def test_story_plan_rejects_ungrounded_semantic_claim_without_numbers() -> None:
    document = _cross_subject_document()
    graph, template, story = _valid_story(document)
    story.batches[0].pages[0].summary = "采用量子纠缠协议完成远程身份认证。"

    with pytest.raises(V6BuildError, match="story_unsupported_semantic_claim"):
        validate_slide_story_plan_v3(story, graph, template)


def test_story_plan_rejects_an_ungrounded_visible_title() -> None:
    document = _cross_subject_document()
    graph, template, story = _valid_story(document)
    story.batches[0].pages[0].title = "Quantum credential exchange"

    with pytest.raises(V6BuildError, match="story_unsupported_title"):
        validate_slide_story_plan_v3(story, graph, template)


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
                        title="",
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
    assert all(page.speaker_notes.source_blocks for page in deck.pages)
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
    visible = "\n".join(region.content for region in deck.pages[0].regions)

    assert "区分观察事实与解释" in visible
    assert deck.quality.formal_block_visible_coverage == 1.0


def test_story_plan_rejects_duplicate_page_titles() -> None:
    document = _cross_subject_document()
    graph, template, story = _valid_story(document)
    story.batches[0].pages[1].title = story.batches[0].pages[0].title

    with pytest.raises(V6BuildError, match="duplicate_slide_title"):
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
                    kind=artifact_kind,
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


def test_code_overflow_uses_a_source_excerpt_and_keeps_full_code_in_notes() -> None:
    code = "\n".join(f"step_{index} = observe({index})" for index in range(55))
    document, graph, template, story, visual = _artifact_deck_fixture(
        artifact_kind="code",
        artifact_text=code,
    )

    deck = compile_slide_deck_v6(document, graph, story, visual, template)

    assert len(deck.pages) == 1
    assert deck.pages[0].continuation_index == 1
    assert deck.pages[0].continuation_count == 1
    rendered_code = "\n".join(
        region.content
        for page in deck.pages
        for region in page.regions
        if region.content_kind == "code"
    )
    assert rendered_code != code
    assert rendered_code
    assert all(line in code.splitlines() for line in rendered_code.splitlines())
    assert all(
        any(note.block_id == "artifact" and note.full_text == code for note in page.speaker_notes.source_blocks)
        for page in deck.pages
    )


def test_one_source_block_can_fill_code_and_annotation_without_invented_copy() -> None:
    source = (
        "Explain why the guard must run before the action.\n\n"
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
        summary="",
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
    assert regions["annotation"].content == (
        "Explain why the guard must run before the action."
    )
    assert "def execute(value):" not in regions["annotation"].content
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


def test_very_large_code_still_respects_page_limit_with_full_notes() -> None:
    code = "\n".join(f"step_{index} = observe({index})" for index in range(90))
    document, graph, template, story, visual = _artifact_deck_fixture(
        artifact_kind="code",
        artifact_text=code,
    )

    deck = compile_slide_deck_v6(document, graph, story, visual, template)

    assert len(deck.pages) == 1
    code_region = next(
        region
        for region in deck.pages[0].regions
        if region.content_kind == "code"
    )
    assert len(code_region.content.splitlines()) < len(code.splitlines())
    assert any(
        note.block_id == "artifact" and note.full_text == code
        for note in deck.pages[0].speaker_notes.source_blocks
    )


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
