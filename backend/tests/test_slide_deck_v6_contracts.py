import inspect
import re

import pytest

from course_document import CourseBlock, CourseDocument, CourseSection, refresh_document_revision
from course_presentation_graph import (
    block_artifact_kinds,
    block_source_text,
    compile_course_presentation_graph,
)
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
    _protected_tokens,
    build_signature_v6,
    compile_ppt_source_contract_v2,
    compile_shadow_chapter_document,
    compile_slide_deck_v6,
    story_page_count_range,
    story_safe_page_slices,
    validate_slide_story_plan_v3,
    validate_slide_visual_plan_v2,
)
from slide_deck_v6_renderer import adapt_v6_page_to_slide_spec
from template_layout_contract import compile_builtin_template_layout_contract_v1


def test_sentence_excerpt_never_exceeds_its_template_budget():
    source = "A source sentence with no early punctuation and several additional words"

    excerpt = _complete_sentence_excerpt(source, 35)

    assert len(excerpt) <= 35
    assert excerpt.endswith("…")
    assert excerpt[:-1] in source


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

    assert baseline["compiler_version"] == "slide_deck_v6_compiler_v5"
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
    story.batches[0].pages[0].summary = "采用量子纠缠协议完成远程身份认证。"

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


def test_single_body_page_keeps_complete_source_instead_of_substituting_story_summary() -> None:
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

    assert body == source


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
    assert regions["annotation"].content == (
        "Explain why the guard must run before the action."
    )
    assert "def execute(value):" not in regions["annotation"].content
    visible_prose = "\n".join(
        region.content
        for compiled_page in deck.pages
        for region in compiled_page.regions
        if region.content_kind == "body"
    )
    assert "A missing value stops execution" in visible_prose
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

    assert len(deck.pages) == 3
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
    assert "Read the evidence in source order" in visible_prose
    assert "check the stated condition and result" in visible_prose


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
    assert len(deck.pages) == 2
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
        "Inspect the complete evidence",
        "Inspect the complete evidence",
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
