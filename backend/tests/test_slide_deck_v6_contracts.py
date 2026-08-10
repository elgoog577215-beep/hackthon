import inspect

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
    compile_ppt_source_contract_v2,
    compile_slide_deck_v6,
    validate_slide_story_plan_v3,
    validate_slide_visual_plan_v2,
)
from template_layout_contract import compile_builtin_template_layout_contract_v1


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
                title=f"第 {index + 1} 个教学任务",
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
                resolved_template_layout_id=template.layout_id("content-stack"),
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
    invalid.decisions[1].resolved_template_layout_id = template.layout_id("content-stack")
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
