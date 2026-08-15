import asyncio
import time

import pytest

import slide_ai_planning_v6 as planning_module
from course_document import CourseBlock, CourseDocument, CourseSection, refresh_document_revision
from course_presentation_graph import (
    compile_course_presentation_graph,
    teaching_intent_for_roles,
)
from slide_ai_planning_v6 import (
    AIPlannerInvocationError,
    _grounded_title_candidates,
    build_ai_base_story_planner_v6,
    plan_slide_story_v3,
    plan_slide_visuals_v2,
    repair_slide_visuals_v2,
)
from slide_deck_v6 import (
    SlideStoryBatchV3,
    SlideStoryPageV3,
    SlideStoryPlanV3,
    SlideVisualDecisionV2,
    SlideVisualPlanV2,
    V6BuildError,
    compile_slide_deck_v6,
    validate_slide_story_plan_v3,
)
from template_layout_contract import compile_builtin_template_layout_contract_v1


def test_v6_planners_use_the_dedicated_ppt_provider_profile(monkeypatch):
    profiles: list[str | None] = []

    class CapturingAIBase:
        def __init__(self, *, provider_profile=None):
            profiles.append(provider_profile)

    monkeypatch.setattr(planning_module, "AIBase", CapturingAIBase)

    planning_module.build_ai_base_story_planner_v6()
    planning_module.build_ai_base_visual_planner_v2()

    assert profiles == ["ppt", "ppt"]


@pytest.mark.asyncio
async def test_planner_timeout_is_a_hard_deadline_when_provider_delays_cancellation() -> None:
    """A stuck provider must not keep a durable V6 task running forever."""

    provider_released = asyncio.Event()

    async def cancellation_delayed_planner(_request):
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            await asyncio.sleep(0.08)
            provider_released.set()
            return {}

    started = time.perf_counter()
    with pytest.raises(asyncio.TimeoutError):
        await planning_module._invoke(
            cancellation_delayed_planner,
            {},
            timeout_seconds=0.01,
        )
    elapsed = time.perf_counter() - started

    assert elapsed < 0.05
    await asyncio.wait_for(provider_released.wait(), timeout=0.2)


def _document(*, with_code: bool = False) -> CourseDocument:
    blocks = [
        CourseBlock(
            block_id="concept",
            section_id="chapter-a",
            position=0,
            role="concept",
            payload={"markdown": "一个可靠流程先界定输入，再执行动作，最后核对结果。"},
        ),
        CourseBlock(
            block_id="feedback",
            section_id="chapter-a",
            position=1,
            role="feedback",
            payload={"markdown": "核对时必须同时检查完成条件和异常原因。"},
        ),
    ]
    if with_code:
        blocks.insert(
            1,
            CourseBlock(
                block_id="implementation",
                section_id="chapter-a",
                position=1,
                role="example",
                kind="code",
                payload={"markdown": "def verify(value):\n    return value is not None"},
            ),
        )
        blocks[-1].position = 2
    return refresh_document_revision(
        CourseDocument(
            course_id="generic-course",
            title="可靠工作流",
            sections=[CourseSection(section_id="chapter-a", title="完成闭环", position=0)],
            blocks=blocks,
        )
    )


def _two_unit_document() -> CourseDocument:
    return refresh_document_revision(
        CourseDocument(
            course_id="generic-targeted-story-repair",
            title="Targeted story repair",
            sections=[
                CourseSection(
                    section_id="chapter-a",
                    title="Repair scope",
                    position=0,
                )
            ],
            blocks=[
                CourseBlock(
                    block_id="alpha-concept",
                    section_id="chapter-a",
                    position=0,
                    role="concept",
                    payload={
                        "markdown": (
                            "Alpha collection records every source before review."
                        )
                    },
                ),
                CourseBlock(
                    block_id="alpha-feedback",
                    section_id="chapter-a",
                    position=1,
                    role="feedback",
                    payload={
                        "markdown": (
                            "Alpha review checks the recorded source and final result."
                        )
                    },
                ),
                CourseBlock(
                    block_id="beta-concept",
                    section_id="chapter-a",
                    position=2,
                    role="concept",
                    payload={
                        "markdown": (
                            "Beta verification compares the baseline with the observed result."
                        )
                    },
                ),
                CourseBlock(
                    block_id="beta-feedback",
                    section_id="chapter-a",
                    position=3,
                    role="feedback",
                    payload={
                        "markdown": (
                            "Beta approval records both the decision and its evidence."
                        )
                    },
                ),
            ],
        )
    )


def test_title_candidates_exclude_structural_labels_and_dangling_excerpts() -> None:
    candidates = _grounded_title_candidates(
        "## 项目名称：湿地观察证据链与审核路径\n"
        "湿地观察需要绑定地点、时间、天气和原始证据。",
        max_chars=10,
    )

    assert "项目名称" not in candidates
    assert "湿地观察证据链" in candidates
    assert all(not title.endswith(("与", "和", "及", ":", "：")) for title in candidates)


def _mixed_artifact_document(
    artifact_kind: str,
    artifact_markdown: str,
) -> CourseDocument:
    return refresh_document_revision(
        CourseDocument(
            course_id="generic-mixed-artifact-course",
            title="Evidence and representation",
            sections=[
                CourseSection(
                    section_id="chapter-artifact",
                    title="Evidence workflow",
                    position=0,
                )
            ],
            blocks=[
                CourseBlock(
                    block_id="context",
                    section_id="chapter-artifact",
                    position=0,
                    role="concept",
                    payload={
                        "markdown": (
                            "## Observe the evidence\n"
                            "Explain the surrounding context before applying a representation."
                        )
                    },
                ),
                CourseBlock(
                    block_id="artifact",
                    section_id="chapter-artifact",
                    position=1,
                    role="example",
                    kind=artifact_kind,
                    payload={
                        "markdown": (
                            "## Apply the representation\n"
                            f"{artifact_markdown}"
                        )
                    },
                ),
            ],
        )
    )


def _structured_field_check_document() -> CourseDocument:
    """A non-code, non-math task whose primary expression is a table."""

    return refresh_document_revision(
        CourseDocument(
            course_id="generic-field-check",
            title="Field evidence review",
            sections=[
                CourseSection(
                    section_id="field-check",
                    title="Verify the observation record",
                    position=0,
                )
            ],
            blocks=[
                CourseBlock(
                    block_id="field-task-table",
                    section_id="field-check",
                    position=0,
                    kind="review_checkpoint",
                    role="activity",
                    payload={
                        "markdown": (
                            "| Check | Required evidence |\n"
                            "| --- | --- |\n"
                            "| Time | Recorded |\n"
                            "| Habitat | Described |"
                        )
                    },
                ),
                CourseBlock(
                    block_id="field-feedback",
                    section_id="field-check",
                    position=1,
                    role="feedback",
                    payload={
                        "markdown": (
                            "## Interpret the field record\n"
                            "Compare every observation with the stated evidence requirement."
                        )
                    },
                ),
            ],
        )
    )


def _ordered_field_task_with_table_feedback_document() -> CourseDocument:
    """A generic procedure whose ordered task must not disappear into a table page."""

    return refresh_document_revision(
        CourseDocument(
            course_id="generic-ordered-field-task",
            title="Field sample transfer",
            sections=[
                CourseSection(
                    section_id="sample-transfer",
                    title="Transfer and verify the sample",
                    position=0,
                )
            ],
            blocks=[
                CourseBlock(
                    block_id="transfer-procedure",
                    section_id="sample-transfer",
                    position=0,
                    role="activity",
                    payload={
                        "markdown": (
                            "Follow the procedure in order:\n\n"
                            "1. **Collect the sample**\n"
                            "   - Record the collection time.\n"
                            "2. **Seal the container**\n"
                            "   - Check the lid.\n"
                            "3. **Transfer the package**\n"
                            "   - Obtain the receiver signature."
                        )
                    },
                ),
                CourseBlock(
                    block_id="transfer-errors",
                    section_id="sample-transfer",
                    position=1,
                    role="feedback",
                    payload={
                        "markdown": (
                            "| Symptom | Cause | Correction |\n"
                            "| --- | --- | --- |\n"
                            "| Broken seal | Lid was loose | Reseal the container |\n"
                            "| Missing signature | Handoff was skipped | Repeat the handoff |"
                        )
                    },
                ),
            ],
        )
    )


def _field_misconception_repair_document() -> CourseDocument:
    """A non-code, non-math unit whose three roles must stay together."""

    return refresh_document_revision(
        CourseDocument(
            course_id="generic-field-misconception",
            title="Field specimen labeling",
            sections=[
                CourseSection(
                    section_id="label-repair",
                    title="Diagnose and repair the label",
                    position=0,
                )
            ],
            blocks=[
                CourseBlock(
                    block_id="label-symptom",
                    section_id="label-repair",
                    position=0,
                    role="misconception",
                    payload={
                        "markdown": (
                            "The sealed specimen label remains blank after the "
                            "field record is attached."
                        )
                    },
                ),
                CourseBlock(
                    block_id="label-cause",
                    section_id="label-repair",
                    position=1,
                    role="reasoning",
                    payload={
                        "markdown": (
                            "The label was applied before the container surface "
                            "dried, so the adhesive lost contact."
                        )
                    },
                ),
                CourseBlock(
                    block_id="label-repair",
                    section_id="label-repair",
                    position=2,
                    role="remediation",
                    payload={
                        "markdown": (
                            "Dry the container, apply a new label, and verify that "
                            "the identifier remains readable."
                        )
                    },
                ),
            ],
        )
    )


def _mixed_table_and_code_document() -> CourseDocument:
    """A generic evidence unit that needs separate table and code expressions."""

    return refresh_document_revision(
        CourseDocument(
            course_id="generic-mixed-evidence",
            title="Evidence reproduction workflow",
            sections=[
                CourseSection(
                    section_id="evidence-review",
                    title="Inspect and reproduce the evidence",
                    position=0,
                )
            ],
            blocks=[
                CourseBlock(
                    block_id="observation-record",
                    section_id="evidence-review",
                    position=0,
                    kind="review_checkpoint",
                    role="activity",
                    payload={
                        "markdown": (
                            "| Check | Result |\n"
                            "| --- | --- |\n"
                            "| Signal | Found |"
                        )
                    },
                ),
                CourseBlock(
                    block_id="reproduction-procedure",
                    section_id="evidence-review",
                    position=1,
                    kind="code",
                    role="example",
                    payload={
                        "markdown": (
                            "Reproduce the recorded result with the supplied procedure.\n\n"
                            "```python\n"
                            "def reproduce(record):\n"
                            "    return record['result']\n"
                            "```"
                        )
                    },
                ),
            ],
        )
    )


def _dense_mixed_evidence_document() -> CourseDocument:
    """A field workflow whose safe template expression needs four pages."""

    blocks = [
        CourseBlock(
            block_id="field-context",
            section_id="field-workflow",
            position=0,
            role="concept",
            payload={"markdown": "## Observe the site\nRecord the visible signal."},
        ),
        CourseBlock(
            block_id="field-rationale",
            section_id="field-workflow",
            position=1,
            role="reasoning",
            payload={"markdown": "## Explain the check\nRelate the signal to the protocol."},
        ),
        CourseBlock(
            block_id="collection-procedure",
            section_id="field-workflow",
            position=2,
            kind="code",
            role="example",
            payload={
                "markdown": (
                    "## Run the collection procedure\nUse the supplied command.\n\n"
                    "```python\nrecord = collect(signal)\n```"
                )
            },
        ),
        CourseBlock(
            block_id="learner-check",
            section_id="field-workflow",
            position=3,
            role="activity",
            payload={"markdown": "## Check the sample\nRepeat the observation once."},
        ),
        CourseBlock(
            block_id="observation-table",
            section_id="field-workflow",
            position=4,
            kind="review_checkpoint",
            role="feedback",
            payload={
                "markdown": (
                    "| Evidence | Result |\n"
                    "| --- | --- |\n"
                    "| Signal | Recorded |"
                )
            },
        ),
        CourseBlock(
            block_id="instrument-output",
            section_id="field-workflow",
            position=5,
            kind="code",
            role="feedback",
            payload={
                "markdown": (
                    "## Verify the output\nCompare the returned value with the record.\n\n"
                    "```text\nstatus=recorded\n```"
                )
            },
        ),
    ]
    return refresh_document_revision(
        CourseDocument(
            course_id="generic-field-workflow",
            title="Field evidence workflow",
            sections=[
                CourseSection(
                    section_id="field-workflow",
                    title="Collect and verify evidence",
                    position=0,
                )
            ],
            blocks=blocks,
        )
    )


def _layout_for_request_blocks(unit: dict, block_ids: list[str]) -> str:
    block_metadata = {
        block["block_id"]: block for block in unit["primary_blocks"]
    }
    roles = [block_metadata[block_id]["role"] for block_id in block_ids]
    artifacts = {
        artifact
        for block_id in block_ids
        for artifact in block_metadata[block_id]["artifact_kinds"]
    }
    intent = teaching_intent_for_roles(roles, artifacts)
    return unit["allowed_template_layout_ids_by_page_intent"][intent][0]


def _title_for_request_blocks(unit: dict, block_ids: list[str]) -> str:
    block_metadata = {
        block["block_id"]: block for block in unit["primary_blocks"]
    }
    return next(
        candidate
        for block_id in block_ids
        for candidate in block_metadata[block_id]["title_candidates"]
    )


def test_long_source_heading_offers_semantic_fragments_within_template_capacity() -> None:
    source = "## Field protocol: Observe habitat signals and record the evidence"

    candidates = _grounded_title_candidates(source, max_chars=28)

    assert "Observe habitat signals" in candidates
    assert all(candidate in source and len(candidate) <= 28 for candidate in candidates)


@pytest.mark.asyncio
async def test_story_ai_is_required_and_uses_only_supplied_units_and_layouts() -> None:
    document = _document()
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    calls = []

    async def planner(request):
        calls.append(request)
        unit = request["teaching_units"][0]
        layout = next(item for item in unit["allowed_template_layout_ids"] if item.endswith("/practice-feedback"))
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "provider": "rotating-fixture",
            "model": "generic-model",
            "attempts": 1,
            "pages": [
                {
                    "page_id": "page-a",
                    "teaching_unit_id": unit["teaching_unit_id"],
                    "template_layout_id": layout,
                    "title": _title_for_request_blocks(
                        unit,
                        unit["primary_block_ids"],
                    ),
                    "summary": "",
                    "source_block_ids": unit["primary_block_ids"],
                }
            ],
        }

    story = await plan_slide_story_v3(graph, template, ai_planner=planner)

    assert len(calls) == 1
    supplied_layouts = calls[0]["teaching_units"][0]["allowed_template_layouts"]
    title_candidates = calls[0]["teaching_units"][0]["title_candidates"]
    assert title_candidates
    assert all(
        candidate in calls[0]["teaching_units"][0]["source_text"]
        for candidate in title_candidates
    )
    assert calls[0]["response_contract"]["required_page_fields"] == [
        "page_id",
        "teaching_unit_id",
        "template_layout_id",
        "title",
        "source_block_ids",
    ]
    assert calls[0]["response_contract"]["forbidden_page_fields"] == ["content"]
    assert calls[0]["constraints"]["primary_block_page_ownership"] == "exactly_once"
    assert calls[0]["constraints"]["allow_multiple_primary_blocks_per_page"] is True
    assert calls[0]["constraints"]["canvas_expression"] == (
        "semantic_closure_with_full_source_in_notes"
    )
    assert calls[0]["constraints"]["summary_policy"] == (
        "source_grounded_semantic_closure_for_all_bound_blocks_"
        "complete_sentence_no_markdown"
    )
    assert calls[0]["teaching_units"][0]["summary_max_chars_by_layout_id"]
    assert {item["template_layout_id"] for item in supplied_layouts} == set(
        calls[0]["teaching_units"][0]["allowed_template_layout_ids"]
    )
    assert all(item["slots"] for item in supplied_layouts)
    assert all(
        {"slot_id", "slot_kind", "required", "max_chars", "max_items", "max_lines", "max_rows"}
        <= set(slot)
        for item in supplied_layouts
        for slot in item["slots"]
    )
    assert story.batches[0].provider == "rotating-fixture"
    assert story.batches[0].validation_status == "passed"
    validate_slide_story_plan_v3(story, graph, template)

    with pytest.raises(V6BuildError, match="story_ai_required"):
        await plan_slide_story_v3(graph, template, ai_planner=None)


@pytest.mark.asyncio
async def test_story_assigns_unique_page_ids_across_ai_batches() -> None:
    document = refresh_document_revision(CourseDocument(
        course_id="generic-cross-batch-page-identities",
        title="Cross-batch page identities",
        sections=[
            CourseSection(section_id="chapter-a", title="First concept", position=0),
            CourseSection(section_id="chapter-b", title="Second concept", position=1),
        ],
        blocks=[
            CourseBlock(
                block_id="first-concept",
                section_id="chapter-a",
                position=0,
                role="concept",
                payload={
                    "markdown": (
                        "First concept records the input boundary, observable action, "
                        "verification evidence, exception path, and acceptance decision."
                    )
                },
            ),
            CourseBlock(
                block_id="second-concept",
                section_id="chapter-b",
                position=0,
                role="concept",
                payload={
                    "markdown": (
                        "Second concept preserves the source condition, execution order, "
                        "review evidence, correction path, and final acceptance record."
                    )
                },
            ),
        ],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")

    async def planner(request):
        unit = request["teaching_units"][0]
        block_ids = unit["primary_block_ids"]
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "pages": [{
                "page_id": "page_0001",
                "teaching_unit_id": unit["teaching_unit_id"],
                "template_layout_id": _layout_for_request_blocks(unit, block_ids),
                "title": _title_for_request_blocks(unit, block_ids),
                "summary": "",
                "source_block_ids": block_ids,
            }],
        }

    story = await plan_slide_story_v3(graph, template, ai_planner=planner)

    assert len(story.pages) == 2
    assert len({page.page_id for page in story.pages}) == 2
    assert story.pages[0].page_id == "page_0001"


@pytest.mark.asyncio
async def test_story_assigns_unique_page_ids_within_an_ai_batch() -> None:
    document = _two_unit_document()
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")

    async def planner(request):
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "pages": [
                {
                    "page_id": "L2-6-2-page-1",
                    "teaching_unit_id": unit["teaching_unit_id"],
                    "template_layout_id": _layout_for_request_blocks(
                        unit,
                        unit["primary_block_ids"],
                    ),
                    "title": _title_for_request_blocks(
                        unit,
                        unit["primary_block_ids"],
                    ),
                    "summary": "",
                    "source_block_ids": unit["primary_block_ids"],
                }
                for unit in request["teaching_units"]
            ],
        }

    story = await plan_slide_story_v3(graph, template, ai_planner=planner)

    assert len(story.pages) == 2
    assert len({page.page_id for page in story.pages}) == 2
    assert story.pages[0].page_id == "L2-6-2-page-1"


@pytest.mark.asyncio
async def test_story_resume_normalizes_duplicate_page_ids_before_validation() -> None:
    document = _two_unit_document()
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")

    async def initial_planner(request):
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "pages": [
                {
                    "page_id": f"saved-page-{index}",
                    "teaching_unit_id": unit["teaching_unit_id"],
                    "template_layout_id": _layout_for_request_blocks(
                        unit,
                        unit["primary_block_ids"],
                    ),
                    "title": _title_for_request_blocks(
                        unit,
                        unit["primary_block_ids"],
                    ),
                    "summary": "",
                    "source_block_ids": unit["primary_block_ids"],
                }
                for index, unit in enumerate(request["teaching_units"])
            ],
        }

    initial = await plan_slide_story_v3(
        graph,
        template,
        ai_planner=initial_planner,
    )
    duplicate_id = initial.pages[0].page_id
    saved_batch = initial.batches[0].model_copy(update={
        "pages": [
            page.model_copy(update={"page_id": duplicate_id})
            for page in initial.batches[0].pages
        ]
    })

    async def planner_must_not_run(_request):
        raise AssertionError("valid saved story content should be resumed")

    resumed = await plan_slide_story_v3(
        graph,
        template,
        ai_planner=planner_must_not_run,
        resume_batches=[saved_batch],
    )

    assert len({page.page_id for page in resumed.pages}) == len(resumed.pages)
    assert resumed.pages[0].page_id == duplicate_id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response_shape",
    ["version_wrapper", "slides_alias", "derivable_page_fields"],
)
async def test_story_ai_accepts_lossless_versioned_response_shapes(
    response_shape: str,
) -> None:
    """Provider JSON shape drift must not bypass the strict V6 semantic gates."""

    document = _document()
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")

    async def planner(request):
        unit = request["teaching_units"][0]
        page = {
            "page_id": "page-generic",
            "teaching_unit_id": unit["teaching_unit_id"],
            "template_layout_id": next(
                item
                for item in unit["allowed_template_layout_ids"]
                if item.endswith("/practice-feedback")
            ),
            "title": unit["source_text"][:24],
            "summary": "",
            "source_block_ids": unit["primary_block_ids"],
        }
        payload = {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "pages": [page],
        }
        if response_shape == "version_wrapper":
            return {
                "slide_story_batch_response_v3": payload,
                "provider": "rotating-fixture",
                "model": "generic-model",
                "attempts": 2,
            }
        if response_shape == "derivable_page_fields":
            return {
                "schema_version": "slide_story_batch_response_v3",
                "chapter_id": request["chapter_id"],
                "provider": "rotating-fixture",
                "model": "generic-model",
                "attempts": 1,
                "pages": [{
                    "teaching_unit_id": unit["teaching_unit_id"],
                    "template_layout_id": page["template_layout_id"],
                    "content": {"title": unit["source_text"][:24]},
                }],
            }
        return {
            **payload,
            "provider": "rotating-fixture",
            "model": "generic-model",
            "attempts": 1,
            "slides": payload["pages"],
            "pages": None,
        }

    story = await plan_slide_story_v3(graph, template, ai_planner=planner)

    assert story.batches[0].provider == "rotating-fixture"
    assert story.batches[0].pages[0].source_block_ids == ["concept", "feedback"]
    if response_shape == "derivable_page_fields":
        assert story.batches[0].pages[0].page_id.startswith("v6page_")
    validate_slide_story_plan_v3(story, graph, template)


@pytest.mark.asyncio
async def test_story_ai_discards_unconsumed_page_drafts_before_strict_validation() -> None:
    """Cross-subject provider over-answering must not become ungrounded deck content."""

    document = _document()
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    calls = 0

    async def planner(request):
        nonlocal calls
        calls += 1
        unit = request["teaching_units"][0]
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "pages": [{
                "page_id": "page-over-answer",
                "teaching_unit_id": unit["teaching_unit_id"],
                "template_layout_id": unit["allowed_template_layout_ids"][0],
                "title": unit["title_candidates"][0],
                "summary": "",
                "source_block_ids": unit["primary_block_ids"],
                "code": "invented_output_that_must_not_be_consumed()",
                "annotation": "provider-only draft instruction",
                "visual_direction": {"kind": "diagram"},
            }],
        }

    story = await plan_slide_story_v3(graph, template, ai_planner=planner)

    assert calls == 1
    page_payload = story.batches[0].pages[0].model_dump(mode="json")
    assert "code" not in page_payload
    assert "annotation" not in page_payload
    assert "visual_direction" not in page_payload
    validate_slide_story_plan_v3(story, graph, template)


@pytest.mark.asyncio
async def test_one_story_batch_failure_fails_the_candidate_without_fallback() -> None:
    document = _document()
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")

    async def planner(_request):
        raise TimeoutError("provider timed out")

    with pytest.raises(V6BuildError, match="story_ai_batch_timeout") as captured:
        await plan_slide_story_v3(graph, template, ai_planner=planner, timeout_seconds=0.2)

    assert captured.value.failure.retryable is True
    assert captured.value.failure.chapter_id == "chapter-a"


@pytest.mark.asyncio
async def test_story_balance_failure_is_not_misreported_as_rate_limiting() -> None:
    document = _document()
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")

    async def planner(_request):
        raise RuntimeError("Error code: 429 - insufficient balance")

    with pytest.raises(V6BuildError) as captured:
        await plan_slide_story_v3(graph, template, ai_planner=planner)

    assert captured.value.failure.code == "story_ai_batch_balance_unavailable"
    assert captured.value.failure.retryable is False


@pytest.mark.asyncio
async def test_failed_story_batch_reports_sanitized_provider_attempt_diagnostics() -> None:
    document = _document()
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    events: list[dict] = []

    async def planner(_request):
        raise AIPlannerInvocationError(
            RuntimeError("Error code: 429 - insufficient balance"),
            telemetry=[
                {
                    "provider_route": "primary_pool",
                    "model_id": "generic-primary-model",
                    "provider_attempt": 1,
                    "status": "failed",
                    "error_code": "RateLimitError",
                    "duration_ms": 120,
                    "queue_wait_ms": 5,
                    "api_key": "must-not-be-persisted",
                    "prompt": "must-not-be-persisted",
                },
                {
                    "provider_route": "modelscope_fallback",
                    "model_id": "generic-fallback-model",
                    "provider_attempt": 1,
                    "status": "failed",
                    "error_code": "BalanceError",
                    "duration_ms": 240,
                    "queue_wait_ms": 8,
                },
            ],
        )

    with pytest.raises(V6BuildError) as captured:
        await plan_slide_story_v3(
            graph,
            template,
            ai_planner=planner,
            batch_callback=lambda event: events.append(event),
        )

    assert captured.value.failure.code == "story_ai_batch_balance_unavailable"
    failed = next(event for event in events if event["phase"] == "failed")
    diagnostic = failed["diagnostic"].model_dump(mode="json")
    assert diagnostic["validation_status"] == "failed"
    assert diagnostic["failure_category"] == "story_ai_batch_balance_unavailable"
    assert diagnostic["provider"] == "modelscope_fallback"
    assert diagnostic["model"] == "generic-fallback-model"
    assert diagnostic["attempts"] == 2
    assert diagnostic["retry_count"] == 1
    assert diagnostic["attempt_records"] == [
        {
            "provider": "primary_pool",
            "model": "generic-primary-model",
            "attempt": 1,
            "status": "failed",
            "duration_ms": 120,
            "queue_wait_ms": 5,
            "error_code": "RateLimitError",
        },
        {
            "provider": "modelscope_fallback",
            "model": "generic-fallback-model",
            "attempt": 1,
            "status": "failed",
            "duration_ms": 240,
            "queue_wait_ms": 8,
            "error_code": "BalanceError",
        },
    ]
    assert "api_key" not in str(diagnostic)
    assert "prompt" not in str(diagnostic)


@pytest.mark.asyncio
async def test_shared_ai_story_planner_preserves_safe_failure_telemetry(monkeypatch) -> None:
    class FailedSharedAI:
        def __init__(self, *, provider_profile=None):
            assert provider_profile == "ppt"

        async def _call_llm(self, *_args, telemetry_sink, **_kwargs):
            telemetry_sink({
                "provider_route": "rotating-pool",
                "model_id": "generic-provider-model",
                "provider_attempt": 3,
                "status": "failed",
                "error_code": "QuotaError",
                "duration_ms": 90,
                "queue_wait_ms": 7,
                "api_key": "must-not-leave-provider-boundary",
            })
            raise RuntimeError("insufficient quota")

    monkeypatch.setattr(planning_module, "AIBase", FailedSharedAI)
    planner = build_ai_base_story_planner_v6()

    with pytest.raises(AIPlannerInvocationError) as captured:
        await planner({"schema_version": "generic-request"})

    assert str(captured.value) == "insufficient quota"
    assert captured.value.telemetry == [{
        "provider": "rotating-pool",
        "model": "generic-provider-model",
        "attempt": 3,
        "status": "failed",
        "duration_ms": 90,
        "queue_wait_ms": 7,
        "error_code": "QuotaError",
    }]
    assert "api_key" not in str(captured.value.telemetry)


@pytest.mark.asyncio
async def test_story_batch_retries_a_template_contract_violation_before_failing() -> None:
    document = _document()
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    calls = []

    async def planner(request):
        calls.append(request)
        unit = request["teaching_units"][0]
        layout = (
            "template-layout-not-in-contract"
            if len(calls) == 1
            else unit["allowed_template_layout_ids"][0]
        )
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "provider": "rotating-fixture",
            "model": "generic-model",
            "attempts": 1,
            "pages": [{
                "page_id": f"page-{len(calls)}",
                "teaching_unit_id": unit["teaching_unit_id"],
                "template_layout_id": layout,
                "title": unit["source_text"][:24],
                "summary": "",
                "source_block_ids": unit["primary_block_ids"],
            }],
        }

    story = await plan_slide_story_v3(graph, template, ai_planner=planner)

    assert len(calls) == 2
    repair_target = calls[1]["repair_feedback"]["repair_targets"][0]
    assert "bind multiple related block IDs to the same page" in (
        calls[1]["repair_feedback"]["instruction"]
    )
    assert repair_target["page_id"] == "page-1"
    assert repair_target["teaching_unit_id"] == calls[0]["teaching_units"][0]["teaching_unit_id"]
    assert repair_target["allowed_page_count_range"] == (
        calls[0]["teaching_units"][0]["allowed_page_count_range"]
    )
    assert repair_target["observed_unit_page_ids"] == ["page-1"]
    assert repair_target["page_intent"] == calls[0]["teaching_units"][0]["teaching_intent"]
    assert repair_target["allowed_template_layout_ids"] == (
        calls[0]["teaching_units"][0]["allowed_template_layout_ids_by_page_intent"]
        [repair_target["page_intent"]]
    )
    assert repair_target["required_source_block_ids"] == calls[0]["teaching_units"][0]["primary_block_ids"]
    assert repair_target["missing_source_block_ids"] == []
    assert repair_target["duplicate_source_block_ids"] == []
    assert repair_target["duplicate_page_ids"] == []
    assert repair_target["allowed_title_candidates"] == calls[0]["teaching_units"][0]["title_candidates"]
    assert repair_target["available_title_candidates"] == calls[0]["teaching_units"][0]["title_candidates"]
    assert repair_target["duplicate_title"] == ""
    assert repair_target["conflicting_page_ids"] == []
    assert repair_target["current_summary"] == ""
    assert repair_target["summary_policy"] == (
        "source_grounded_semantic_closure_for_all_bound_blocks_"
        "complete_sentence_no_markdown"
    )
    assert story.batches[0].attempts == 2


@pytest.mark.asyncio
async def test_story_repair_scopes_the_retry_and_preserves_unaffected_units() -> None:
    document = _two_unit_document()
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    calls = []

    async def planner(request):
        calls.append(request)
        pages = []
        for index, unit in enumerate(request["teaching_units"]):
            layout = next(
                layout_id
                for layout_id in unit["allowed_template_layout_ids"]
                if layout_id.endswith("/practice-feedback")
            )
            if len(calls) == 1 and index == 0:
                layout = "template-layout-not-in-contract"
            title_candidates = unit["title_candidates"]
            pages.append({
                "page_id": f"{'initial' if len(calls) == 1 else 'repaired'}-{index}",
                "teaching_unit_id": unit["teaching_unit_id"],
                "template_layout_id": layout,
                "title": (
                    title_candidates[-1]
                    if len(calls) > 1 and index > 0
                    else title_candidates[0]
                ),
                "summary": "",
                "source_block_ids": unit["primary_block_ids"],
            })
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "pages": pages,
        }

    story = await plan_slide_story_v3(graph, template, ai_planner=planner)

    assert len(calls) == 2
    assert len(calls[0]["teaching_units"]) == 2
    assert [
        unit["teaching_unit_id"] for unit in calls[1]["teaching_units"]
    ] == [calls[0]["teaching_units"][0]["teaching_unit_id"]]
    assert [
        target["teaching_unit_id"]
        for target in calls[1]["repair_feedback"]["repair_targets"]
    ] == [calls[0]["teaching_units"][0]["teaching_unit_id"]]
    assert story.pages[0].page_id == "repaired-0"
    assert story.pages[1].page_id == "initial-1"
    assert story.pages[1].title == calls[0]["teaching_units"][1]["title_candidates"][0]


@pytest.mark.asyncio
async def test_story_batch_repairs_a_title_over_the_selected_layout_capacity() -> None:
    document = refresh_document_revision(CourseDocument(
        course_id="generic-title-capacity",
        title="Field observation",
        sections=[CourseSection(
            section_id="chapter-a",
            title="Observation protocol",
            position=0,
        )],
        blocks=[CourseBlock(
            block_id="objective",
            section_id="chapter-a",
            position=0,
            role="objective",
            payload={
                "markdown": (
                    "A source-grounded operational heading that deliberately exceeds "
                    "the declared template title capacity."
                ),
            },
        )],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    calls = []

    async def planner(request):
        calls.append(request)
        unit = request["teaching_units"][0]
        if len(calls) == 1:
            title = unit["source_text"][: min(72, unit["title_max_chars"] + 1)]
        else:
            repair_target = request["repair_feedback"]["repair_targets"][0]
            title = repair_target["available_title_candidates"][0]
        selected_layout = next(
            layout["template_layout_id"]
            for layout in unit["allowed_template_layouts"]
            if any(
                slot["slot_kind"] == "title"
                and slot["max_chars"] == unit["title_max_chars"]
                for slot in layout["slots"]
            )
        )
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "pages": [{
                "page_id": "generic-capacity-page",
                "teaching_unit_id": unit["teaching_unit_id"],
                "template_layout_id": selected_layout,
                "title": title,
                "summary": "",
                "source_block_ids": unit["primary_block_ids"],
            }],
        }

    story = await plan_slide_story_v3(graph, template, ai_planner=planner)

    assert len(calls) == 2
    repair_feedback = calls[1]["repair_feedback"]
    repair_target = repair_feedback["repair_targets"][0]
    assert repair_feedback["code"] == "story_title_capacity_exceeded"
    assert repair_target["current_title"]
    assert repair_target["title_max_chars"] > 0
    assert all(
        len(candidate) <= repair_target["title_max_chars"]
        for candidate in repair_target["available_title_candidates"]
    )
    assert len(story.pages[0].title) <= repair_target["title_max_chars"]


@pytest.mark.asyncio
async def test_story_batch_requires_an_exact_source_title_during_repair() -> None:
    document = _document()
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    calls = []

    async def planner(request):
        calls.append(request)
        unit = request["teaching_units"][0]
        title = "Quantum credential exchange"
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "pages": [{
                "page_id": f"generic-grounded-title-{len(calls)}",
                "teaching_unit_id": unit["teaching_unit_id"],
                "template_layout_id": unit["allowed_template_layout_ids"][0],
                "title": title,
                "summary": "",
                "source_block_ids": unit["primary_block_ids"],
            }],
        }

    story = await plan_slide_story_v3(graph, template, ai_planner=planner)

    assert len(calls) == 2
    repair_feedback = calls[1]["repair_feedback"]
    target = repair_feedback["repair_targets"][0]
    assert repair_feedback["code"] == "story_unsupported_title"
    assert target["required_title"] in target["available_title_candidates"]
    assert story.pages[0].title == target["required_title"]


@pytest.mark.asyncio
async def test_story_batch_repairs_an_underfilled_editorial_summary() -> None:
    source_sentence = (
        "湿地观察必须记录地点、时间、天气、观察者和采样批次，并逐项核对原始证据、"
        "验收标准、审核修订和异常原因，确保结论没有用解释替代事实。"
    )
    document = refresh_document_revision(CourseDocument(
        course_id="generic-field-density-repair",
        title="Field evidence",
        sections=[CourseSection(section_id="chapter-a", title="Field", position=0)],
        blocks=[CourseBlock(
            block_id="field-evidence",
            section_id="chapter-a",
            position=0,
            role="concept",
            payload={"markdown": f"## 湿地观察证据链\n{source_sentence * 3}"},
        )],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    calls = []

    async def planner(request):
        calls.append(request)
        unit = request["teaching_units"][0]
        summary = (
            "记录地点、时间和天气。"
            if len(calls) == 1
            else request["repair_feedback"]["repair_targets"][0]["required_summary"]
        )
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "pages": [{
                "page_id": "field-density-page",
                "teaching_unit_id": unit["teaching_unit_id"],
                "template_layout_id": next(
                    layout_id
                    for layout_id in unit["allowed_template_layout_ids"]
                    if layout_id.endswith("/content-stack")
                ),
                "title": "湿地观察证据链",
                "summary": summary,
                "source_block_ids": unit["primary_block_ids"],
            }],
        }

    story = await plan_slide_story_v3(graph, template, ai_planner=planner)

    assert len(calls) == 1
    assert len(story.pages[0].summary) >= 120
    assert len(story.pages[0].summary) <= 200
    assert "湿地观察" in story.pages[0].summary


@pytest.mark.asyncio
async def test_story_resume_replans_an_underfilled_saved_batch() -> None:
    source_sentence = (
        "湿地观察必须记录地点、时间、天气、观察者和采样批次，并逐项核对原始证据、"
        "验收标准、审核修订和异常原因，确保结论没有用解释替代事实。"
    )
    document = refresh_document_revision(CourseDocument(
        course_id="generic-field-density-resume",
        title="Field evidence",
        sections=[CourseSection(
            section_id="chapter-a",
            title="Field",
            position=0,
        )],
        blocks=[CourseBlock(
            block_id="field-evidence",
            section_id="chapter-a",
            position=0,
            role="concept",
            payload={"markdown": f"## 湿地观察证据链\n{source_sentence * 3}"},
        )],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    unit = graph.units[0]
    layout_id = next(
        layout.template_layout_id
        for layout in template.layouts
        if layout.template_layout_id.endswith("/content-stack")
    )
    saved_batch = SlideStoryBatchV3(
        batch_id="story-1",
        chapter_id="chapter-a",
        provider="saved-provider",
        model="saved-model",
        duration_ms=1,
        attempts=1,
        validation_status="passed",
        pages=[SlideStoryPageV3(
            page_id="field-density-page",
            teaching_unit_id=unit.teaching_unit_id,
            template_layout_id=layout_id,
            title="湿地观察证据链",
            summary="记录地点、时间和天气。",
            source_block_ids=unit.primary_block_ids,
            page_ordinal=0,
        )],
    )
    calls = []
    events = []

    async def planner(request):
        calls.append(request)
        requested_unit = request["teaching_units"][0]
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "provider": "fresh-provider",
            "model": "fresh-model",
            "pages": [{
                "page_id": "field-density-page",
                "teaching_unit_id": requested_unit["teaching_unit_id"],
                "template_layout_id": layout_id,
                "title": "湿地观察证据链",
                "summary": "",
                "source_block_ids": requested_unit["primary_block_ids"],
            }],
        }

    story = await plan_slide_story_v3(
        graph,
        template,
        ai_planner=planner,
        resume_batches=[saved_batch],
        batch_callback=lambda event: events.append(event),
    )

    assert len(calls) == 1
    assert story.pages[0].summary == ""
    assert story.batches[0].provider == "fresh-provider"
    assert any(event["phase"] == "started" for event in events)
    assert not any(
        event["phase"] == "completed" and event.get("resumed") is True
        for event in events
    )


def test_story_capacity_error_uses_the_frozen_source_summary_repair() -> None:
    source_sentence = (
        "The field team records the habitat boundary, observation time, weather, "
        "instrument calibration, signed evidence identifier, acceptance criterion, "
        "review decision, and follow-up owner before publishing the survey result. "
    )
    document = refresh_document_revision(CourseDocument(
        course_id="generic-field-summary-capacity",
        title="Field survey review",
        sections=[CourseSection(
            section_id="chapter-a",
            title="Evidence protocol",
            position=0,
        )],
        blocks=[CourseBlock(
            block_id="field-evidence",
            section_id="chapter-a",
            position=0,
            role="concept",
            payload={"markdown": source_sentence * 5},
        )],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    request = planning_module._story_requests(graph, template)[0]
    unit = request["teaching_units"][0]
    layout_id = next(
        layout_id
        for layout_id in unit["allowed_template_layout_ids"]
        if layout_id.endswith("/chapter-entry")
    )
    page = {
        "page_id": "field-summary-capacity-page",
        "teaching_unit_id": unit["teaching_unit_id"],
        "template_layout_id": layout_id,
        "title": unit["title_candidates"][0],
        "summary": unit["source_text"][:650],
        "source_block_ids": unit["primary_block_ids"],
    }
    payload = {
        "schema_version": "slide_story_batch_response_v3",
        "chapter_id": request["chapter_id"],
        "pages": [page],
    }
    error = V6BuildError(
        stage="story",
        code="story_summary_capacity_exceeded",
        message="Story summary exceeds the selected template support slot",
        page_id=page["page_id"],
    )

    repaired = planning_module._apply_grounded_story_repairs(
        payload,
        request,
        error,
    )
    repaired_summary = repaired["pages"][0]["summary"]
    maximum = unit["summary_max_chars_by_layout_id"][layout_id]

    assert repaired is not payload
    assert repaired_summary
    assert len(repaired_summary) <= maximum
    assert repaired_summary.rstrip("…") in unit["source_text"]


def test_story_markdown_repair_compiles_block_markup_into_plain_summary() -> None:
    source = (
        "## Field evidence review\n\n"
        "- Record the habitat boundary, observation time, weather, instrument "
        "calibration, and signed evidence identifier.\n"
        "> Verify the acceptance criterion, review decision, exception reason, "
        "and follow-up owner before publication.\n"
        "1. Compare the observation with the approved field protocol.\n"
        "2. Preserve the reviewed evidence and the final decision."
    )
    document = refresh_document_revision(CourseDocument(
        course_id="generic-field-markdown-repair",
        title="Field evidence",
        sections=[CourseSection(
            section_id="chapter-a",
            title="Evidence review",
            position=0,
        )],
        blocks=[CourseBlock(
            block_id="field-evidence",
            section_id="chapter-a",
            position=0,
            role="concept",
            payload={"markdown": source},
        )],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    request = planning_module._story_requests(graph, template)[0]
    unit = request["teaching_units"][0]
    layout_id = next(
        layout_id
        for layout_id in unit["allowed_template_layout_ids"]
        if layout_id.endswith("/chapter-entry")
    )
    page = {
        "page_id": "field-markdown-page",
        "teaching_unit_id": unit["teaching_unit_id"],
        "template_layout_id": layout_id,
        "title": unit["title_candidates"][0],
        "summary": source,
        "source_block_ids": unit["primary_block_ids"],
    }
    payload = {
        "schema_version": "slide_story_batch_response_v3",
        "chapter_id": request["chapter_id"],
        "pages": [page],
    }
    error = V6BuildError(
        stage="story",
        code="story_summary_markdown_invalid",
        message="Story summary must be presentation-ready text without Markdown",
        page_id=page["page_id"],
    )

    repaired = planning_module._apply_grounded_story_repairs(
        payload,
        request,
        error,
    )
    repaired_summary = repaired["pages"][0]["summary"]

    assert planning_module._visible_prose_text(repaired_summary) == repaired_summary
    assert not planning_module._looks_like_markdown_table(repaired_summary)
    assert all(marker not in repaired_summary for marker in ("> ", "- ", "1. ", "2. "))
    assert "Field evidence review" in repaired_summary
    assert "observation time" in repaired_summary


def test_story_markdown_repair_converges_all_invalid_pages_in_one_pass() -> None:
    source = (
        "## Field evidence review\n\n"
        "- Record the habitat boundary, observation time, weather, and signed "
        "evidence identifier.\n"
        "> Verify the acceptance criterion and review decision before publication."
    )
    document = refresh_document_revision(CourseDocument(
        course_id="generic-field-batch-markdown",
        title="Field evidence",
        sections=[CourseSection(
            section_id="chapter-a",
            title="Evidence review",
            position=0,
        )],
        blocks=[CourseBlock(
            block_id="field-evidence",
            section_id="chapter-a",
            position=0,
            role="concept",
            payload={"markdown": source},
        )],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    request = planning_module._story_requests(graph, template)[0]
    unit = request["teaching_units"][0]
    layout_id = next(
        layout_id
        for layout_id in unit["allowed_template_layout_ids"]
        if layout_id.endswith("/chapter-entry")
    )
    pages = [
        {
            "page_id": f"field-markdown-page-{index}",
            "teaching_unit_id": unit["teaching_unit_id"],
            "template_layout_id": layout_id,
            "title": unit["title_candidates"][0],
            "summary": f"**Review {index}.**\n- Preserve the evidence record.",
            "source_block_ids": unit["primary_block_ids"],
        }
        for index in range(4)
    ]
    payload = {
        "schema_version": "slide_story_batch_response_v3",
        "chapter_id": request["chapter_id"],
        "pages": pages,
    }
    error = V6BuildError(
        stage="story",
        code="story_summary_markdown_invalid",
        message="Story summary must be presentation-ready text without Markdown",
        page_id=pages[-1]["page_id"],
    )

    repaired = planning_module._apply_grounded_story_repairs(
        payload,
        request,
        error,
    )

    assert repaired is not payload
    assert len(repaired["pages"]) == 4
    assert all(
        planning_module._presentation_summary_text(page["summary"])
        == page["summary"].strip()
        and not planning_module._looks_like_markdown_table(page["summary"])
        for page in repaired["pages"]
    )


@pytest.mark.asyncio
async def test_story_batch_normalizes_four_markdown_summaries_without_ai_retry() -> None:
    document = refresh_document_revision(CourseDocument(
        course_id="generic-field-batch-markdown-integration",
        title="Field evidence workflow",
        sections=[CourseSection(
            section_id="chapter-a",
            title="Evidence review",
            position=0,
        )],
        blocks=[
            CourseBlock(
                block_id=f"field-evidence-{index}",
                section_id="chapter-a",
                position=index,
                role="concept",
                payload={
                    "markdown": (
                        f"## Evidence checkpoint {index + 1}\n"
                        "Record the habitat boundary, observation time, weather, "
                        "instrument calibration, signed evidence identifier, "
                        "acceptance criterion, review decision, and follow-up owner."
                    ),
                },
            )
            for index in range(4)
        ],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    calls: list[dict] = []

    async def planner(request):
        calls.append(request)
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "pages": [
                {
                    "page_id": f"field-markdown-page-{index}",
                    "teaching_unit_id": unit["teaching_unit_id"],
                    "template_layout_id": next(
                        layout_id
                        for layout_id in unit["allowed_template_layout_ids"]
                        if layout_id.endswith("/chapter-entry")
                    ),
                    "title": unit["title_candidates"][0],
                    "summary": (
                        f"**Evidence checkpoint {index + 1}.**\n"
                        "- Preserve the reviewed field record."
                    ),
                    "source_block_ids": unit["primary_block_ids"],
                }
                for index, unit in enumerate(request["teaching_units"])
            ],
        }

    story = await plan_slide_story_v3(graph, template, ai_planner=planner)

    assert len(calls) == 1
    assert len(story.pages) == 4
    assert all(
        planning_module._presentation_summary_text(page.summary)
        == page.summary.strip()
        and not planning_module._looks_like_markdown_table(page.summary)
        for page in story.pages
    )


@pytest.mark.parametrize(
    "failure_code",
    ["story_unsupported_fact", "story_unsupported_semantic_claim"],
)
def test_story_grounding_repair_converges_all_invalid_pages_in_one_pass(
    failure_code: str,
) -> None:
    source = (
        "Evidence review records the habitat boundary, observation time, weather, "
        "instrument calibration, acceptance criterion, review decision, and owner."
    )
    document = refresh_document_revision(CourseDocument(
        course_id="generic-field-batch-grounding",
        title="Field evidence",
        sections=[CourseSection(
            section_id="chapter-a",
            title="Evidence review",
            position=0,
        )],
        blocks=[CourseBlock(
            block_id="field-evidence",
            section_id="chapter-a",
            position=0,
            role="concept",
            payload={"markdown": source},
        )],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    request = planning_module._story_requests(graph, template)[0]
    unit = request["teaching_units"][0]
    layout_id = next(
        layout_id
        for layout_id in unit["allowed_template_layout_ids"]
        if layout_id.endswith("/chapter-entry")
    )
    pages = [
        {
            "page_id": f"field-grounding-page-{index}",
            "teaching_unit_id": unit["teaching_unit_id"],
            "template_layout_id": layout_id,
            "title": unit["title_candidates"][0],
            "summary": (
                "Ceramic glazing develops tactile studio composition."
                if failure_code == "story_unsupported_semantic_claim"
                else (
                    "Evidence review records the habitat boundary and weather. "
                    f"fabricatedMetric{9000 + index}."
                )
            ),
            "source_block_ids": unit["primary_block_ids"],
        }
        for index in range(4)
    ]
    payload = {
        "schema_version": "slide_story_batch_response_v3",
        "chapter_id": request["chapter_id"],
        "pages": pages,
    }
    error = V6BuildError(
        stage="story",
        code=failure_code,
        message="Story summary is not grounded in its frozen source unit",
        page_id=pages[0]["page_id"],
    )

    repaired = planning_module._apply_grounded_story_repairs(
        payload,
        request,
        error,
    )

    assert repaired is not payload
    assert len(repaired["pages"]) == 4
    assert all(
        planning_module._protected_tokens(page["summary"])
        <= planning_module._protected_tokens(unit["source_text"])
        for page in repaired["pages"]
    )


@pytest.mark.asyncio
async def test_story_batch_repairs_four_unsupported_facts_without_ai_retry() -> None:
    document = refresh_document_revision(CourseDocument(
        course_id="generic-field-batch-unsupported-facts",
        title="Field evidence workflow",
        sections=[CourseSection(
            section_id="chapter-a",
            title="Evidence review",
            position=0,
        )],
        blocks=[
            CourseBlock(
                block_id=f"field-evidence-{index}",
                section_id="chapter-a",
                position=index,
                role="concept",
                payload={
                    "markdown": (
                        f"Evidence checkpoint {index + 1} records habitat boundary, "
                        "weather, calibration, review decision, and follow-up owner."
                    ),
                },
            )
            for index in range(4)
        ],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    calls: list[dict] = []

    async def planner(request):
        calls.append(request)
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "pages": [
                {
                    "page_id": f"field-unsupported-fact-page-{index}",
                    "teaching_unit_id": unit["teaching_unit_id"],
                    "template_layout_id": next(
                        layout_id
                        for layout_id in unit["allowed_template_layout_ids"]
                        if layout_id.endswith("/chapter-entry")
                    ),
                    "title": unit["title_candidates"][0],
                    "summary": (
                        f"Evidence checkpoint {index + 1} records habitat boundary, "
                        "weather, calibration, and review decision. "
                        f"fabricatedMetric{9000 + index}."
                    ),
                    "source_block_ids": unit["primary_block_ids"],
                }
                for index, unit in enumerate(request["teaching_units"])
            ],
        }

    story = await plan_slide_story_v3(graph, template, ai_planner=planner)

    assert len(calls) == 1
    assert len(story.pages) == 4
    assert all(
        planning_module._protected_tokens(page.summary)
        <= planning_module._protected_tokens(
            next(
                unit.source_text
                for unit in graph.units
                if unit.teaching_unit_id == page.teaching_unit_id
            )
        )
        for page in story.pages
    )


def test_visible_prose_compiles_fenced_code_and_markdown_table_without_markers() -> None:
    source = (
        "```text\nreview_status = accepted\n```\n\n"
        "| Check | Result |\n"
        "| --- | --- |\n"
        "| Calibration | Passed |"
    )

    visible = planning_module._visible_prose_text(source)

    assert all(marker not in visible for marker in ("```", "|", "---"))
    assert "review_status = accepted" in visible
    assert "Check Result" in visible
    assert "Calibration Passed" in visible


def test_story_capacity_repair_converges_all_overflow_pages_in_one_pass() -> None:
    source_sentence = (
        "Before publishing a wetland survey, the field team records the habitat "
        "boundary, observation time, weather, instrument calibration, acceptance "
        "criterion, review decision, and follow-up owner. "
    )
    document = refresh_document_revision(CourseDocument(
        course_id="generic-field-batch-capacity",
        title="Wetland field review",
        sections=[CourseSection(
            section_id="chapter-a",
            title="Evidence workflow",
            position=0,
        )],
        blocks=[CourseBlock(
            block_id="field-evidence",
            section_id="chapter-a",
            position=0,
            role="concept",
            payload={"markdown": source_sentence * 5},
        )],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    request = planning_module._story_requests(graph, template)[0]
    unit = request["teaching_units"][0]
    layout_id = next(
        layout_id
        for layout_id in unit["allowed_template_layout_ids"]
        if layout_id.endswith("/chapter-entry")
    )
    maximum = unit["summary_max_chars_by_layout_id"][layout_id]
    pages = [
        {
            "page_id": f"field-capacity-page-{index}",
            "teaching_unit_id": unit["teaching_unit_id"],
            "template_layout_id": layout_id,
            "title": unit["title_candidates"][0],
            "summary": source_sentence * 4,
            "source_block_ids": unit["primary_block_ids"],
        }
        for index in range(4)
    ]
    payload = {
        "schema_version": "slide_story_batch_response_v3",
        "chapter_id": request["chapter_id"],
        "pages": pages,
    }
    error = V6BuildError(
        stage="story",
        code="story_summary_capacity_exceeded",
        message="Story summary exceeds the selected template support slot",
        page_id=pages[-1]["page_id"],
    )

    repaired = planning_module._apply_grounded_story_repairs(
        payload,
        request,
        error,
    )

    assert repaired is not payload
    assert len(repaired["pages"]) == 4
    assert all(
        page["summary"] and len(page["summary"]) <= maximum
        for page in repaired["pages"]
    )


def test_rich_text_table_with_explanation_keeps_a_table_safe_partition() -> None:
    source = (
        "Field teams compare the evidence before approving a survey.\n\n"
        "| Check | Evidence | Decision |\n"
        "| --- | --- | --- |\n"
        "| Weather | Log entry | Continue |\n"
        "| Calibration | Signed record | Accept |\n\n"
        "The reviewer records any exception separately from the signed evidence."
    )
    document = refresh_document_revision(CourseDocument(
        course_id="generic-field-table",
        title="Field evidence review",
        sections=[CourseSection(
            section_id="chapter-a",
            title="Evidence checks",
            position=0,
        )],
        blocks=[CourseBlock(
            block_id="field-table",
            section_id="chapter-a",
            position=0,
            kind="rich_text",
            role="concept",
            payload={"markdown": source},
        )],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    unit = planning_module._story_requests(graph, template)[0]["teaching_units"][0]

    assert unit["artifact_kinds"] == ["table"]
    assert unit["primary_blocks"][0]["artifact_kinds"] == ["table"]
    assert unit["safe_partition_options"]
    assert all(
        any(
            "table" in template.get_layout(layout_id).artifact_kinds
            for layout_id in page["template_layout_ids"]
        )
        for option in unit["safe_partition_options"]
        for page in option["pages"]
    )


@pytest.mark.asyncio
async def test_story_batch_repairs_density_when_a_short_intro_precedes_a_long_sentence() -> None:
    """A long grounded sentence must not strand a repair below its slot minimum."""

    long_observation_clause = (
        "The observer records habitat boundaries, weather conditions, sampling "
        "intervals, instrument calibration, evidence identifiers, review status, "
        "unexpected disturbances, follow-up ownership, and the acceptance decision "
        "in one continuous field statement without inventing any measurement"
    )
    long_observation = f"{' and '.join([long_observation_clause] * 3)}."
    document = refresh_document_revision(CourseDocument(
        course_id="generic-long-field-sentence",
        title="Field observation review",
        sections=[
            CourseSection(
                section_id="field-review",
                title="Review the observation",
                position=0,
            )
        ],
        blocks=[CourseBlock(
            block_id="observation-record",
            section_id="field-review",
            position=0,
            role="concept",
            payload={
                    "markdown": (
                        "## Evidence record\n"
                        "Record the context."
                        f"{long_observation}"
                    )
            },
        )],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    calls = []

    async def planner(request):
        calls.append(request)
        if len(calls) > 1:
            raise AssertionError(
                "A source-grounded density repair must not spend another provider call"
            )
        unit = request["teaching_units"][0]
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "pages": [{
                "page_id": "field-long-sentence-page",
                "teaching_unit_id": unit["teaching_unit_id"],
                "template_layout_id": next(
                    layout_id
                    for layout_id in unit["allowed_template_layout_ids"]
                    if layout_id.endswith("/content-stack")
                ),
                "title": "Evidence record",
                "summary": "Record the context.",
                "source_block_ids": unit["primary_block_ids"],
            }],
        }

    story = await plan_slide_story_v3(graph, template, ai_planner=planner)

    assert len(calls) == 1
    assert len(story.pages[0].summary) >= 120
    assert "habitat boundaries" in story.pages[0].summary


@pytest.mark.asyncio
async def test_story_clears_markdown_summary_when_layout_has_no_summary_slot() -> None:
    document = refresh_document_revision(CourseDocument(
        course_id="generic-field-practice",
        title="Field sampling practice",
        sections=[
            CourseSection(
                section_id="field-practice",
                title="Collect the sample",
                position=0,
            )
        ],
        blocks=[CourseBlock(
            block_id="field-activity",
            section_id="field-practice",
            position=0,
            role="activity",
            payload={
                "markdown": (
                    "## Sampling task\n"
                    "1. Mark the observation boundary.\n"
                    "2. Record the sampling time.\n"
                    "3. Bind the evidence identifier."
                )
            },
        )],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    calls = []

    async def planner(request):
        calls.append(request)
        if len(calls) > 1:
            raise AssertionError("An empty grounded repair must be applied locally")
        unit = request["teaching_units"][0]
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "pages": [{
                "page_id": "field-practice-page",
                "teaching_unit_id": unit["teaching_unit_id"],
                "template_layout_id": next(
                    layout_id
                    for layout_id in unit["allowed_template_layout_ids"]
                    if layout_id.endswith("/practice-prompt")
                ),
                "title": "Sampling task",
                "summary": "**Complete the field record.**",
                "source_block_ids": unit["primary_block_ids"],
            }],
        }

    story = await plan_slide_story_v3(graph, template, ai_planner=planner)

    assert len(calls) == 1
    assert story.pages[0].summary == ""


@pytest.mark.asyncio
async def test_story_batch_repairs_all_underfilled_pages_in_one_retry() -> None:
    source_a = (
        "潮间带记录必须包含样区、潮位、时间、观察者和原始编号，并说明记录条件。"
        "审核时逐项核对签名、仪器、天气和异常说明，不能用推测替代缺失证据。"
    )
    source_b = (
        "林缘样方记录必须保留位置、时段、观察者、物种和数量，并绑定原始表单。"
        "复核时比较采样条件、签名、修订记录和异常原因，确保结论可以回溯。"
    )
    document = refresh_document_revision(CourseDocument(
        course_id="generic-multi-page-density-repair",
        title="Field evidence review",
        sections=[CourseSection(section_id="field", title="Review evidence", position=0)],
        blocks=[
            CourseBlock(
                block_id="shore-record",
                section_id="field",
                position=0,
                role="concept",
                payload={"markdown": f"## 潮间带证据记录\n{source_a * 3}"},
            ),
            CourseBlock(
                block_id="forest-record",
                section_id="field",
                position=1,
                role="reasoning",
                payload={"markdown": f"## 林缘样方复核\n{source_b * 3}"},
            ),
        ],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    calls = []

    async def planner(request):
        calls.append(request)
        unit = request["teaching_units"][0]
        layout_id = next(
            layout_id
            for layout_id in unit["allowed_template_layout_ids"]
            if layout_id.endswith("/content-stack")
        )
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "pages": [
                {
                    "page_id": "shore-page",
                    "teaching_unit_id": unit["teaching_unit_id"],
                    "template_layout_id": layout_id,
                    "title": "潮间带证据记录",
                    "summary": "记录潮位和时间。",
                    "source_block_ids": ["shore-record"],
                },
                {
                    "page_id": "forest-page",
                    "teaching_unit_id": unit["teaching_unit_id"],
                    "template_layout_id": layout_id,
                    "title": "林缘样方复核",
                    "summary": "复核样方记录。",
                    "source_block_ids": ["forest-record"],
                },
            ],
        }

    story = await plan_slide_story_v3(graph, template, ai_planner=planner)

    assert len(calls) == 1
    assert {page.page_id for page in story.pages} == {
        "shore-page",
        "forest-page",
    }
    assert all(len(page.summary) >= 120 for page in story.pages)


@pytest.mark.asyncio
async def test_story_batch_resolves_known_layout_from_page_level_source_intent() -> None:
    document = _document()
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    calls = []

    async def planner(request):
        calls.append(request)
        unit = request["teaching_units"][0]
        concept_id, feedback_id = unit["primary_block_ids"]
        concept_layout = next(
            layout_id
            for layout_id in unit["allowed_template_layout_ids"]
            if layout_id.endswith("/practice-feedback")
        )
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "pages": [
                {
                    "page_id": f"generic-concept-page-{len(calls)}",
                    "teaching_unit_id": unit["teaching_unit_id"],
                    "template_layout_id": concept_layout,
                    "title": _title_for_request_blocks(
                        unit,
                        [concept_id],
                    ),
                    "summary": "",
                    "source_block_ids": [concept_id],
                },
                {
                    "page_id": "generic-feedback-page",
                    "teaching_unit_id": unit["teaching_unit_id"],
                    "template_layout_id": _layout_for_request_blocks(
                        unit,
                        [feedback_id],
                    ),
                    "title": _title_for_request_blocks(unit, [feedback_id]),
                    "summary": "",
                    "source_block_ids": [feedback_id],
                },
            ],
        }

    story = await plan_slide_story_v3(graph, template, ai_planner=planner)

    assert len(calls) == 1
    assert story.pages[0].template_layout_id.endswith("/content-stack")
    assert not story.pages[0].template_layout_id.endswith("/practice-feedback")


@pytest.mark.asyncio
async def test_story_resolves_known_but_off_contract_layout_to_page_compatible_layout() -> None:
    """A provider may name another layout in the same template pack.

    Keep the closed template registry, but adapt that known selection to the
    frozen page sources instead of spending repair attempts on a mismatch.
    This field-work fixture is deliberately neither mathematical nor code-led.
    """

    document = _document()
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    calls = []

    async def planner(request):
        calls.append(request)
        unit = request["teaching_units"][0]
        concept_id, feedback_id = unit["primary_block_ids"]
        known_but_off_contract = next(
            layout.template_layout_id
            for layout in template.layouts
            if layout.layout_slug == "evidence-code"
        )
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "pages": [
                {
                    "page_id": "field-concept-off-contract",
                    "teaching_unit_id": unit["teaching_unit_id"],
                    "template_layout_id": known_but_off_contract,
                    "title": _title_for_request_blocks(unit, [concept_id]),
                    "summary": "",
                    "source_block_ids": [concept_id],
                },
                {
                    "page_id": "field-feedback-compatible",
                    "teaching_unit_id": unit["teaching_unit_id"],
                    "template_layout_id": _layout_for_request_blocks(
                        unit,
                        [feedback_id],
                    ),
                    "title": _title_for_request_blocks(unit, [feedback_id]),
                    "summary": "",
                    "source_block_ids": [feedback_id],
                },
            ],
        }

    story = await plan_slide_story_v3(graph, template, ai_planner=planner)

    assert len(calls) == 1
    concept_page = next(
        page for page in story.pages if page.page_id == "field-concept-off-contract"
    )
    assert concept_page.template_layout_id.endswith("/content-stack")


@pytest.mark.asyncio
async def test_story_keeps_source_only_code_without_forced_unit_repartition() -> None:
    """A complete code artifact is safe without unrelated prose annotation."""

    document = _document(with_code=True)
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    calls = []

    async def planner(request):
        calls.append(request)
        unit = request["teaching_units"][0]
        concept_id, code_id, feedback_id = unit["primary_block_ids"]
        repair_targets = (request.get("repair_feedback") or {}).get(
            "repair_targets"
        ) or []
        repair_target = repair_targets[0] if repair_targets else {}
        should_repartition = bool(
            repair_targets
            and repair_target.get("repartition_required") is True
            and any(
                layout_id.endswith("/evidence-code")
                for layout_id in (
                    repair_target.get("artifact_layout_ids_by_kind") or {}
                ).get("code") or []
            )
            and all(
                str(block.get("source_text") or "").strip()
                for block in repair_target.get("primary_blocks") or []
            )
        )
        if should_repartition:
            pages = [
                {
                    "page_id": "llm-code-with-context",
                    "teaching_unit_id": unit["teaching_unit_id"],
                    "template_layout_id": next(
                        layout_id
                        for layout_id in unit["allowed_template_layout_ids"]
                        if layout_id.endswith("/evidence-code")
                    ),
                    "title": _title_for_request_blocks(
                        unit,
                        [concept_id, code_id],
                    ),
                    "summary": "",
                    "source_block_ids": [concept_id, code_id],
                },
                {
                    "page_id": "llm-feedback-after-code",
                    "teaching_unit_id": unit["teaching_unit_id"],
                    "template_layout_id": _layout_for_request_blocks(
                        unit,
                        [feedback_id],
                    ),
                    "title": _title_for_request_blocks(unit, [feedback_id]),
                    "summary": "",
                    "source_block_ids": [feedback_id],
                },
            ]
        else:
            pages = [
                {
                    "page_id": "llm-concept-alone",
                    "teaching_unit_id": unit["teaching_unit_id"],
                    "template_layout_id": _layout_for_request_blocks(
                        unit,
                        [concept_id],
                    ),
                    "title": _title_for_request_blocks(unit, [concept_id]),
                    "summary": "",
                    "source_block_ids": [concept_id],
                },
                {
                    "page_id": "llm-code-without-annotation",
                    "teaching_unit_id": unit["teaching_unit_id"],
                    "template_layout_id": next(
                        layout_id
                        for layout_id in unit["allowed_template_layout_ids"]
                        if layout_id.endswith("/content-stack")
                    ),
                    "title": _title_for_request_blocks(unit, [code_id]),
                    "summary": "",
                    "source_block_ids": [code_id],
                },
                {
                    "page_id": "llm-feedback-alone",
                    "teaching_unit_id": unit["teaching_unit_id"],
                    "template_layout_id": _layout_for_request_blocks(
                        unit,
                        [feedback_id],
                    ),
                    "title": _title_for_request_blocks(unit, [feedback_id]),
                    "summary": "",
                    "source_block_ids": [feedback_id],
                },
            ]
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "provider": "rotating-fixture",
            "model": "generic-model",
            "attempts": 1,
            "pages": pages,
        }

    story = await plan_slide_story_v3(graph, template, ai_planner=planner)

    assert len(calls) == 1
    unit = calls[0]["teaching_units"][0]
    assert [page.page_id for page in story.pages] == [
        "llm-concept-alone",
        "llm-code-without-annotation",
        "llm-feedback-alone",
    ]
    assert [page.source_block_ids for page in story.pages] == [
        unit["primary_block_ids"][:1],
        unit["primary_block_ids"][1:2],
        unit["primary_block_ids"][2:],
    ]
    assert story.pages[1].template_layout_id.endswith("/evidence-code")


@pytest.mark.asyncio
async def test_story_repartitions_page_when_layout_covers_only_one_required_artifact() -> None:
    """A mixed-artifact page is invalid until every artifact has a safe layout."""

    document = _mixed_table_and_code_document()
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    calls = []

    async def planner(request):
        calls.append(request)
        unit = request["teaching_units"][0]
        table_id, code_id = unit["primary_block_ids"]
        table_layout = next(
            layout_id
            for layout_id in unit["allowed_template_layout_ids"]
            if layout_id.endswith("/evidence-table")
        )
        code_layout = next(
            layout_id
            for layout_id in unit["allowed_template_layout_ids"]
            if layout_id.endswith("/evidence-code")
        )
        repair_targets = (request.get("repair_feedback") or {}).get(
            "repair_targets"
        ) or []
        if repair_targets:
            pages = [
                {
                    "page_id": "record-table",
                    "teaching_unit_id": unit["teaching_unit_id"],
                    "template_layout_id": table_layout,
                    "title": unit["title_candidates"][0],
                    "summary": "",
                    "source_block_ids": [table_id],
                },
                {
                    "page_id": "reproduction-code",
                    "teaching_unit_id": unit["teaching_unit_id"],
                    "template_layout_id": code_layout,
                    "title": unit["title_candidates"][1],
                    "summary": "",
                    "source_block_ids": [code_id],
                },
            ]
        else:
            pages = [
                {
                    "page_id": "mixed-evidence",
                    "teaching_unit_id": unit["teaching_unit_id"],
                    "template_layout_id": table_layout,
                    "title": unit["title_candidates"][0],
                    "summary": "",
                    "source_block_ids": [table_id, code_id],
                }
            ]
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "provider": "rotating-fixture",
            "model": "generic-model",
            "attempts": 1,
            "pages": pages,
        }

    story = await plan_slide_story_v3(graph, template, ai_planner=planner)

    assert len(calls) == 2
    repair_target = calls[1]["repair_feedback"]["repair_targets"][0]
    assert repair_target["repartition_required"] is True
    assert repair_target["required_artifact_kinds"] == ["code", "table"]
    assert repair_target["current_layout_artifact_kinds"] == ["data", "table"]
    assert repair_target["missing_artifact_kinds"] == ["code"]
    assert repair_target["artifact_source_block_ids_by_kind"] == {
        "code": ["reproduction-procedure"],
        "table": ["observation-record"],
    }
    assert repair_target["source_block_order"] == [
        "observation-record",
        "reproduction-procedure",
    ]
    assert [page.source_block_ids for page in story.pages] == [
        ["observation-record"],
        ["reproduction-procedure"],
    ]
    assert story.pages[0].template_layout_id.endswith("/evidence-table")
    assert story.pages[1].template_layout_id.endswith("/evidence-code")


@pytest.mark.parametrize(
    ("invalid_layout_slug", "failure_code"),
    [
        ("evidence-table", "template_layout_artifact_mismatch"),
        ("content-stack", "template_layout_intent_mismatch"),
    ],
)
@pytest.mark.asyncio
async def test_story_contract_projects_repeated_invalid_grouping_to_one_safe_partition(
    invalid_layout_slug: str,
    failure_code: str,
) -> None:
    """A retry remains AI-authored but its source grouping is contract constrained."""

    document = _mixed_table_and_code_document()
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    calls = []

    async def planner(request):
        calls.append(request)
        unit = request["teaching_units"][0]
        invalid_layout = next(
            layout.template_layout_id
            for layout in template.layouts
            if layout.layout_slug == invalid_layout_slug
        )
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "provider": "rotating-fixture",
            "model": "generic-model",
            "attempts": 1,
            "pages": [{
                "page_id": f"invalid-mixed-page-{len(calls)}",
                "teaching_unit_id": unit["teaching_unit_id"],
                "template_layout_id": invalid_layout,
                "title": unit["title_candidates"][0],
                "summary": "",
                "source_block_ids": unit["primary_block_ids"],
            }],
        }

    story = await plan_slide_story_v3(graph, template, ai_planner=planner)

    assert len(calls) == 2
    repair = calls[1]["repair_feedback"]
    assert repair["code"] == failure_code
    target = repair["repair_targets"][0]
    assert target["repartition_required"] is True
    assert target["required_safe_partition"]["partition_id"]
    assert target["required_safe_partition"]["pages"]
    assert [page.source_block_ids for page in story.pages] == [
        ["observation-record"],
        ["reproduction-procedure"],
    ]
    assert story.pages[0].template_layout_id.endswith("/evidence-table")
    assert story.pages[1].template_layout_id.endswith("/evidence-code")


@pytest.mark.asyncio
async def test_story_repartitions_when_required_template_slots_lack_source_roles() -> None:
    """A role-complete template cannot be used for isolated semantic fragments."""

    document = _field_misconception_repair_document()
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    calls = []

    async def planner(request):
        calls.append(request)
        unit = request["teaching_units"][0]
        layout_id = next(
            layout.template_layout_id
            for layout in template.layouts
            if layout.layout_slug == "misconception-repair"
        )
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "pages": [
                {
                    "page_id": f"isolated-role-{index + 1}",
                    "teaching_unit_id": unit["teaching_unit_id"],
                    "template_layout_id": layout_id,
                    "title": _title_for_request_blocks(unit, [block_id]),
                    "summary": "",
                    "source_block_ids": [block_id],
                }
                for index, block_id in enumerate(unit["primary_block_ids"])
            ],
        }

    story = await plan_slide_story_v3(graph, template, ai_planner=planner)

    assert len(calls) == 2
    repair = calls[1]["repair_feedback"]
    assert repair["code"] == "template_required_slot_unfilled"
    target = repair["repair_targets"][0]
    assert target["repartition_required"] is True
    assert target["required_safe_partition"]["pages"]
    assert [page.source_block_ids for page in story.pages] == [[
        "label-symptom",
        "label-cause",
        "label-repair",
    ]]
    assert story.pages[0].template_layout_id.endswith("/misconception-repair")


@pytest.mark.asyncio
async def test_story_contract_keeps_ordered_task_out_of_table_only_layout() -> None:
    """Ordered source steps remain a visible sequence across non-code subjects."""

    document = _ordered_field_task_with_table_feedback_document()
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    calls = []

    async def planner(request):
        calls.append(request)
        unit = request["teaching_units"][0]
        table_layout = next(
            layout_id
            for layout_id in unit["allowed_template_layout_ids"]
            if layout_id.endswith("/evidence-table")
        )
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "provider": "rotating-fixture",
            "model": "generic-model",
            "attempts": 1,
            "pages": [{
                "page_id": f"collapsed-procedure-{len(calls)}",
                "teaching_unit_id": unit["teaching_unit_id"],
                "template_layout_id": table_layout,
                "title": _title_for_request_blocks(
                    unit,
                    unit["primary_block_ids"],
                ),
                "summary": "",
                "source_block_ids": unit["primary_block_ids"],
            }],
        }

    story = await plan_slide_story_v3(graph, template, ai_planner=planner)

    assert len(calls) == 2
    repair = calls[1]["repair_feedback"]
    assert repair["code"] == "template_layout_semantic_slot_mismatch"
    target = repair["repair_targets"][0]
    assert target["repartition_required"] is True
    assert [page.source_block_ids for page in story.pages] == [
        ["transfer-procedure"],
        ["transfer-errors"],
    ]
    assert story.pages[0].template_layout_id.endswith("/practice-prompt")
    assert story.pages[1].template_layout_id.endswith("/evidence-table")


@pytest.mark.asyncio
async def test_story_contract_restores_source_order_for_complete_repair_pages() -> None:
    """A complete AI retry may be reordered, but cannot omit or duplicate source."""

    document = _mixed_table_and_code_document()
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    calls = []

    async def planner(request):
        calls.append(request)
        unit = request["teaching_units"][0]
        table_id, code_id = unit["primary_block_ids"]
        table_layout = next(
            layout_id
            for layout_id in unit["allowed_template_layout_ids"]
            if layout_id.endswith("/evidence-table")
        )
        code_layout = next(
            layout_id
            for layout_id in unit["allowed_template_layout_ids"]
            if layout_id.endswith("/evidence-code")
        )
        pages = (
            [{
                "page_id": "invalid-combined-evidence",
                "teaching_unit_id": unit["teaching_unit_id"],
                "template_layout_id": table_layout,
                "title": unit["title_candidates"][0],
                "summary": "",
                "source_block_ids": [table_id, code_id],
            }]
            if len(calls) == 1
            else [
                {
                    "page_id": "code-returned-first",
                    "teaching_unit_id": unit["teaching_unit_id"],
                    "template_layout_id": code_layout,
                    "title": _title_for_request_blocks(unit, [code_id]),
                    "summary": "",
                    "source_block_ids": [code_id],
                },
                {
                    "page_id": "table-returned-second",
                    "teaching_unit_id": unit["teaching_unit_id"],
                    "template_layout_id": table_layout,
                    "title": _title_for_request_blocks(unit, [table_id]),
                    "summary": "",
                    "source_block_ids": [table_id],
                },
            ]
        )
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "pages": pages,
        }

    story = await plan_slide_story_v3(graph, template, ai_planner=planner)

    assert len(calls) == 2
    assert [page.source_block_ids for page in story.pages] == [
        ["observation-record"],
        ["reproduction-procedure"],
    ]
    assert story.pages[0].template_layout_id.endswith("/evidence-table")
    assert story.pages[1].template_layout_id.endswith("/evidence-code")


@pytest.mark.asyncio
async def test_story_contract_uses_verified_initial_coverage_during_layout_repair() -> None:
    """A layout-only repair cannot lose coverage already verified in the AI plan."""

    document = _mixed_table_and_code_document()
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    calls = []

    async def planner(request):
        calls.append(request)
        unit = request["teaching_units"][0]
        table_id, code_id = unit["primary_block_ids"]
        table_layout = next(
            layout_id
            for layout_id in unit["allowed_template_layout_ids"]
            if layout_id.endswith("/evidence-table")
        )
        source_block_ids = (
            [table_id, code_id]
            if len(calls) == 1
            else [code_id]
        )
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "pages": [{
                "page_id": f"layout-repair-page-{len(calls)}",
                "teaching_unit_id": unit["teaching_unit_id"],
                "template_layout_id": table_layout,
                "title": _title_for_request_blocks(unit, source_block_ids),
                "summary": "",
                "source_block_ids": source_block_ids,
            }],
        }

    story = await plan_slide_story_v3(graph, template, ai_planner=planner)

    assert len(calls) == 2
    target = calls[1]["repair_feedback"]["repair_targets"][0]
    assert target["source_coverage_verified"] is True
    assert [page.source_block_ids for page in story.pages] == [
        ["observation-record"],
        ["reproduction-procedure"],
    ]


@pytest.mark.asyncio
async def test_story_uses_dynamic_template_safe_page_budget_for_dense_unit() -> None:
    document = _dense_mixed_evidence_document()
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    calls = []

    async def planner(request):
        calls.append(request)
        unit = request["teaching_units"][0]
        assert unit["allowed_page_count_range"] == [3, 6]
        option = next(
            option
            for option in unit["safe_partition_options"]
            if len(option["pages"]) == 4
        )
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "provider": "rotating-fixture",
            "model": "generic-model",
            "attempts": 1,
            "pages": [
                {
                    "page_id": f"field-page-{index + 1}",
                    "teaching_unit_id": unit["teaching_unit_id"],
                    "template_layout_id": page["template_layout_ids"][0],
                    "title": _title_for_request_blocks(
                        unit,
                        page["source_block_ids"],
                    ),
                    "summary": "",
                    "source_block_ids": page["source_block_ids"],
                }
                for index, page in enumerate(option["pages"])
            ],
        }

    story = await plan_slide_story_v3(graph, template, ai_planner=planner)

    assert len(calls) == 1
    assert len(story.pages) == 4
    assert [block_id for page in story.pages for block_id in page.source_block_ids] == [
        block.block_id for block in document.blocks
    ]


@pytest.mark.asyncio
async def test_story_resolves_feedback_only_page_to_a_single_source_layout() -> None:
    document = _document()
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    calls = []

    async def planner(request):
        calls.append(request)
        unit = request["teaching_units"][0]
        concept_id, feedback_id = unit["primary_block_ids"]
        feedback_layout = next(
            layout_id
            for layout_id in unit["allowed_template_layout_ids"]
            if layout_id.endswith("/practice-feedback")
        )
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "pages": [
                {
                    "page_id": "field-concept",
                    "teaching_unit_id": unit["teaching_unit_id"],
                    "template_layout_id": _layout_for_request_blocks(
                        unit,
                        [concept_id],
                    ),
                    "title": _title_for_request_blocks(unit, [concept_id]),
                    "summary": "",
                    "source_block_ids": [concept_id],
                },
                {
                    "page_id": "field-feedback",
                    "teaching_unit_id": unit["teaching_unit_id"],
                    "template_layout_id": feedback_layout,
                    "title": _title_for_request_blocks(unit, [feedback_id]),
                    "summary": "",
                    "source_block_ids": [feedback_id],
                },
            ],
        }

    story = await plan_slide_story_v3(graph, template, ai_planner=planner)

    assert len(calls) == 1
    feedback_page = next(page for page in story.pages if page.page_id == "field-feedback")
    assert feedback_page.template_layout_id.endswith("/content-stack")


@pytest.mark.asyncio
async def test_structured_task_table_uses_table_layout_and_materializes_all_required_slots() -> None:
    document = _structured_field_check_document()
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")

    async def planner(request):
        unit = request["teaching_units"][0]
        layout = next(
            (
                layout_id
                for layout_id in unit["allowed_template_layout_ids"]
                if layout_id.endswith("/practice-prompt")
            ),
            "",
        )
        if not layout:
            layout = next(
                layout_id
                for layout_id in unit["allowed_template_layout_ids"]
                if layout_id.endswith("/evidence-table")
            )
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "provider": "rotating-fixture",
            "model": "generic-model",
            "attempts": 1,
            "pages": [{
                "page_id": "field-check-page",
                "teaching_unit_id": unit["teaching_unit_id"],
                "template_layout_id": layout,
                "title": "Interpret the field record",
                "summary": "",
                "source_block_ids": unit["primary_block_ids"],
            }],
        }

    story = await plan_slide_story_v3(graph, template, ai_planner=planner)
    page = story.pages[0]
    assert page.template_layout_id.endswith("/evidence-table")

    visual = SlideVisualPlanV2(
        source_document_revision=graph.source_document_revision,
        template_digest=template.template_digest,
        decisions=[
            SlideVisualDecisionV2(
                page_id=page.page_id,
                decision="table",
                source_block_ids=page.source_block_ids,
                resolved_template_layout_id=page.template_layout_id,
            )
        ],
    )
    deck = compile_slide_deck_v6(document, graph, story, visual, template)

    assert deck.status == "v6_ready"
    assert {region.slot_id for region in deck.pages[0].regions} == {
        "table",
        "interpretation",
    }


@pytest.mark.asyncio
async def test_self_explanatory_table_does_not_require_fabricated_interpretation() -> None:
    """A source-complete table may use the full table variant without prose."""

    document = _structured_field_check_document()
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    calls = []

    async def planner(request):
        calls.append(request)
        unit = request["teaching_units"][0]
        table_id, feedback_id = unit["primary_block_ids"]
        known_but_incompatible = next(
            layout.template_layout_id
            for layout in template.layouts
            if layout.layout_slug == "evidence-code"
        )
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "provider": "rotating-fixture",
            "model": "generic-model",
            "attempts": 1,
            "pages": [
                {
                    "page_id": "field-table-only",
                    "teaching_unit_id": unit["teaching_unit_id"],
                    "template_layout_id": known_but_incompatible,
                    "title": _title_for_request_blocks(unit, [table_id]),
                    "summary": "",
                    "source_block_ids": [table_id],
                },
                {
                    "page_id": "field-table-feedback",
                    "teaching_unit_id": unit["teaching_unit_id"],
                    "template_layout_id": _layout_for_request_blocks(
                        unit,
                        [feedback_id],
                    ),
                    "title": _title_for_request_blocks(unit, [feedback_id]),
                    "summary": "",
                    "source_block_ids": [feedback_id],
                },
            ],
        }

    story = await plan_slide_story_v3(graph, template, ai_planner=planner)

    assert len(calls) == 1
    table_page = next(page for page in story.pages if page.page_id == "field-table-only")
    assert table_page.template_layout_id.endswith("/evidence-table")
    table_layout = template.get_layout(table_page.template_layout_id)
    assert table_layout is not None
    interpretation = next(
        slot for slot in table_layout.slots if slot.slot_id == "interpretation"
    )
    assert interpretation.required is False


@pytest.mark.asyncio
async def test_story_repair_names_missing_blocks_without_weakening_coverage() -> None:
    document = _document()
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    calls = []

    async def planner(request):
        calls.append(request)
        unit = request["teaching_units"][0]
        source_ids = (
            unit["primary_block_ids"][:1]
            if len(calls) == 1
            else unit["primary_block_ids"]
        )
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "pages": [{
                "page_id": f"coverage-{len(calls)}",
                "teaching_unit_id": unit["teaching_unit_id"],
                "template_layout_id": _layout_for_request_blocks(unit, source_ids),
                "title": unit["title_candidates"][0],
                "summary": "",
                "source_block_ids": source_ids,
            }],
        }

    story = await plan_slide_story_v3(graph, template, ai_planner=planner)

    assert len(calls) == 2
    repair_target = calls[1]["repair_feedback"]["repair_targets"][0]
    assert repair_target["teaching_unit_id"] == calls[0]["teaching_units"][0]["teaching_unit_id"]
    assert repair_target["missing_source_block_ids"] == ["feedback"]
    assert repair_target["duplicate_source_block_ids"] == []
    assert repair_target["required_source_block_ids"] == ["concept", "feedback"]
    validate_slide_story_plan_v3(story, graph, template)


@pytest.mark.asyncio
async def test_story_repair_clears_an_unsupported_summary_fact() -> None:
    document = _document()
    document = refresh_document_revision(document.model_copy(update={
        "blocks": [
            block.model_copy(update={
                "payload": {
                    "markdown": (
                        f"{block.payload.get('markdown', '')}\n\n"
                        "Field observers use SpecimenRegistry.ResolveObservation "
                        "to verify the frozen observation record."
                    )
                }
            }) if index == 0 else block
            for index, block in enumerate(document.blocks)
        ]
    }))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    calls = []

    async def planner(request):
        calls.append(request)
        unit = request["teaching_units"][0]
        summary = "UnsupportedIdentifier_999" if len(calls) == 1 else ""
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "pages": [{
                "page_id": "summary-repair",
                "teaching_unit_id": unit["teaching_unit_id"],
                "template_layout_id": unit["allowed_template_layout_ids"][0],
                "title": unit["title_candidates"][0],
                "summary": summary,
                "source_block_ids": unit["primary_block_ids"],
            }],
        }

    story = await plan_slide_story_v3(graph, template, ai_planner=planner)

    assert len(calls) == 1
    unit = calls[0]["teaching_units"][0]
    assert unit["allowed_protected_tokens"]
    assert all(
        "allowed_protected_tokens" in block
        for block in unit["primary_blocks"]
    )
    assert any(
        block["allowed_protected_tokens"]
        for block in unit["primary_blocks"]
    )
    assert "UnsupportedIdentifier_999" not in story.pages[0].summary
    assert "SpecimenRegistry.ResolveObservation" in story.pages[0].summary
    validate_slide_story_plan_v3(story, graph, template)


@pytest.mark.asyncio
async def test_story_normalizes_duplicate_titles_from_unused_source_candidates() -> None:
    document = _document(with_code=True)
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    calls = []

    async def planner(request):
        calls.append(request)
        unit = request["teaching_units"][0]
        source_ids = unit["primary_block_ids"]
        first_title = unit["title_candidates"][0]
        second_title = first_title
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "pages": [
                    {
                    "page_id": "title-owner",
                    "teaching_unit_id": unit["teaching_unit_id"],
                        "template_layout_id": _layout_for_request_blocks(
                            unit,
                            source_ids[:1],
                        ),
                    "title": first_title,
                    "summary": "",
                    "source_block_ids": source_ids[:1],
                },
                {
                    "page_id": "title-conflict",
                    "teaching_unit_id": unit["teaching_unit_id"],
                        "template_layout_id": _layout_for_request_blocks(
                            unit,
                            source_ids[1:],
                        ),
                    "title": second_title,
                    "summary": "",
                    "source_block_ids": source_ids[1:],
                },
            ],
        }

    story = await plan_slide_story_v3(graph, template, ai_planner=planner)

    assert len(calls) == 1
    assert story.pages[0].title == calls[0]["teaching_units"][0]["title_candidates"][0]
    assert story.pages[1].title == calls[0]["teaching_units"][0]["title_candidates"][1]
    validate_slide_story_plan_v3(story, graph, template)


@pytest.mark.asyncio
async def test_story_matches_batch_titles_when_greedy_replacement_would_dead_end() -> None:
    document = refresh_document_revision(CourseDocument(
        course_id="batch-title-matching",
        title="Batch title matching",
        sections=[
            CourseSection(section_id="chapter-a", title="Evidence", position=0),
        ],
        blocks=[
            CourseBlock(
                block_id="broad-title-source",
                section_id="chapter-a",
                position=0,
                role="concept",
                payload={"markdown": "## Shared checkpoint\n## Alpha evidence"},
            ),
            CourseBlock(
                block_id="narrow-title-source",
                section_id="chapter-a",
                position=1,
                role="feedback",
                payload={"markdown": "## Shared checkpoint"},
            ),
        ],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    calls = []

    async def planner(request):
        calls.append(request)
        unit = request["teaching_units"][0]
        source_ids = unit["primary_block_ids"]
        shared_title = unit["title_candidates"][0]
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "pages": [
                {
                    "page_id": "broad-title-page",
                    "teaching_unit_id": unit["teaching_unit_id"],
                    "template_layout_id": _layout_for_request_blocks(
                        unit,
                        source_ids[:1],
                    ),
                    "title": shared_title,
                    "summary": "UnsupportedIdentifier_999",
                    "source_block_ids": source_ids[:1],
                },
                {
                    "page_id": "narrow-title-page",
                    "teaching_unit_id": unit["teaching_unit_id"],
                    "template_layout_id": _layout_for_request_blocks(
                        unit,
                        source_ids[1:],
                    ),
                    "title": shared_title,
                    "summary": "",
                    "source_block_ids": source_ids[1:],
                },
            ],
        }

    story = await plan_slide_story_v3(graph, template, ai_planner=planner)

    assert len(calls) == 1
    assert [page.title for page in story.pages] == [
        "Alpha evidence",
        "Shared checkpoint",
    ]
    assert "UnsupportedIdentifier_999" not in story.pages[0].summary
    validate_slide_story_plan_v3(story, graph, template)


@pytest.mark.asyncio
async def test_story_globally_reassigns_titles_when_later_chapter_has_only_shared_candidate() -> None:
    document = refresh_document_revision(CourseDocument(
        course_id="generic-title-reservation",
        title="Shared observation course",
        sections=[
            CourseSection(section_id="phase-a", title="Phase A", position=0),
            CourseSection(section_id="phase-b", title="Phase B", position=1),
        ],
        blocks=[
            CourseBlock(
                block_id="observation-a",
                section_id="phase-a",
                position=0,
                role="concept",
                payload={"markdown": "## Shared checkpoint\n## Alpha evidence"},
            ),
            CourseBlock(
                block_id="observation-b",
                section_id="phase-b",
                position=0,
                role="concept",
                payload={"markdown": "## Shared checkpoint"},
            ),
        ],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    calls = []

    async def planner(request):
        calls.append(request)
        unit = request["teaching_units"][0]
        title = unit["title_candidates"][0]
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "pages": [{
                "page_id": f"page-{request['chapter_id']}",
                "teaching_unit_id": unit["teaching_unit_id"],
                "template_layout_id": unit["allowed_template_layout_ids"][0],
                "title": title,
                "summary": "",
                "source_block_ids": unit["primary_block_ids"],
            }],
        }

    story = await plan_slide_story_v3(graph, template, ai_planner=planner)

    assert len(calls) == 2
    assert calls[0]["constraints"]["forbidden_titles"] == []
    assert calls[1]["constraints"]["forbidden_titles"] == []
    assert [page.title for page in story.pages] == [
        "Alpha evidence",
        "Shared checkpoint",
    ]
    validate_slide_story_plan_v3(story, graph, template)


@pytest.mark.asyncio
async def test_story_reports_nonretryable_failure_when_global_title_assignment_is_impossible() -> None:
    document = refresh_document_revision(CourseDocument(
        course_id="generic-title-capacity",
        title="Shared observation course",
        sections=[
            CourseSection(section_id="phase-a", title="Phase A", position=0),
            CourseSection(section_id="phase-b", title="Phase B", position=1),
        ],
        blocks=[
            CourseBlock(
                block_id="observation-a",
                section_id="phase-a",
                position=0,
                role="concept",
                payload={"markdown": "## Shared checkpoint"},
            ),
            CourseBlock(
                block_id="observation-b",
                section_id="phase-b",
                position=0,
                role="concept",
                payload={"markdown": "## Shared checkpoint"},
            ),
        ],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")

    async def planner(request):
        unit = request["teaching_units"][0]
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "pages": [{
                "page_id": f"page-{request['chapter_id']}",
                "teaching_unit_id": unit["teaching_unit_id"],
                "template_layout_id": unit["allowed_template_layout_ids"][0],
                "title": unit["title_candidates"][0],
                "summary": "",
                "source_block_ids": unit["primary_block_ids"],
            }],
        }

    with pytest.raises(V6BuildError) as captured:
        await plan_slide_story_v3(graph, template, ai_planner=planner)

    assert captured.value.failure.code == "story_title_assignment_unsatisfiable"
    assert captured.value.failure.retryable is False


@pytest.mark.asyncio
async def test_story_global_assignment_rejects_code_fence_language_as_title() -> None:
    document = refresh_document_revision(CourseDocument(
        course_id="generic-title-code-fence",
        title="Shared observation course",
        sections=[
            CourseSection(section_id="phase-a", title="Phase A", position=0),
            CourseSection(section_id="phase-b", title="Phase B", position=1),
        ],
        blocks=[
            CourseBlock(
                block_id="observation-a",
                section_id="phase-a",
                position=0,
                role="concept",
                payload={
                        "markdown": (
                            "## Shared checkpoint\n\n"
                            "```csharp\nx\n```"
                        ),
                },
            ),
            CourseBlock(
                block_id="observation-b",
                section_id="phase-b",
                position=0,
                role="concept",
                payload={"markdown": "## Shared checkpoint"},
            ),
        ],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")

    async def planner(request):
        unit = request["teaching_units"][0]
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "pages": [{
                "page_id": f"page-{request['chapter_id']}",
                "teaching_unit_id": unit["teaching_unit_id"],
                "template_layout_id": unit["allowed_template_layout_ids"][0],
                "title": "Shared checkpoint",
                "summary": "",
                "source_block_ids": unit["primary_block_ids"],
            }],
        }

    with pytest.raises(V6BuildError) as captured:
        await plan_slide_story_v3(graph, template, ai_planner=planner)

    assert captured.value.failure.code == "story_title_assignment_unsatisfiable"
    assert captured.value.failure.retryable is False


@pytest.mark.asyncio
async def test_story_coalesces_repeated_pages_without_another_ai_call() -> None:
    document = refresh_document_revision(CourseDocument(
        course_id="generic-page-limit",
        title="Observable workflow",
        sections=[CourseSection(
            section_id="chapter-limit",
            title="Workflow checkpoints",
            position=0,
        )],
        blocks=[CourseBlock(
            block_id="workflow",
            section_id="chapter-limit",
            position=0,
            role="concept",
            payload={
                "markdown": (
                    "## Alpha checkpoint verifies input\n"
                    "## Beta checkpoint executes action\n"
                    "## Gamma checkpoint checks output\n"
                    "## Delta checkpoint reports result"
                ),
            },
        )],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    calls = []

    async def planner(request):
        calls.append(request)
        unit = request["teaching_units"][0]
        layout = unit["allowed_template_layout_ids"][0]
        if len(calls) == 1:
            pages = [{
                "page_id": f"too-many-{index}",
                "teaching_unit_id": unit["teaching_unit_id"],
                "template_layout_id": layout,
                "title": unit["title_candidates"][index - 1],
                "summary": "",
                "source_block_ids": unit["primary_block_ids"],
            } for index in range(1, 5)]
        else:
            pages = [{
                "page_id": "within-limit",
                "teaching_unit_id": unit["teaching_unit_id"],
                "template_layout_id": layout,
                "title": unit["title_candidates"][0],
                "summary": "",
                "source_block_ids": unit["primary_block_ids"],
            }]
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "pages": pages,
        }

    story = await plan_slide_story_v3(graph, template, ai_planner=planner)

    assert len(calls) == 1
    assert [page.page_id for page in story.pages] == ["too-many-1"]
    assert story.pages[0].source_block_ids == ["workflow"]
    validate_slide_story_plan_v3(story, graph, template)


@pytest.mark.asyncio
async def test_story_preserves_safe_source_driven_pages_and_source_order() -> None:
    document = refresh_document_revision(CourseDocument(
        course_id="generic-editorial-workflow",
        title="Editorial evidence workflow",
        sections=[CourseSection(
            section_id="chapter-review",
            title="Review workflow",
            position=0,
        )],
        blocks=[
            CourseBlock(
                block_id="observe",
                section_id="chapter-review",
                position=0,
                role="concept",
                payload={"markdown": "## Observe the submitted evidence"},
            ),
            CourseBlock(
                block_id="compare",
                section_id="chapter-review",
                position=1,
                role="reasoning",
                payload={"markdown": "## Compare the record with the review criteria"},
            ),
            CourseBlock(
                block_id="decide",
                section_id="chapter-review",
                position=2,
                role="example",
                payload={"markdown": "## Decide whether the evidence is complete"},
            ),
            CourseBlock(
                block_id="report",
                section_id="chapter-review",
                position=3,
                role="feedback",
                payload={"markdown": "## Report the verified finding"},
            ),
            CourseBlock(
                block_id="archive",
                section_id="chapter-review",
                position=4,
                role="concept",
                payload={"markdown": "## Archive the approved observation"},
            ),
            CourseBlock(
                block_id="confirm",
                section_id="chapter-review",
                position=5,
                role="feedback",
                payload={"markdown": "## Confirm the retention record"},
            ),
        ],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    calls = []

    async def planner(request):
        calls.append(request)
        first, second = request["teaching_units"]
        pages = [
            {
                "page_id": f"review-{index + 1}",
                "teaching_unit_id": first["teaching_unit_id"],
                "template_layout_id": _layout_for_request_blocks(
                    first,
                    [block_id],
                ),
                "title": first["title_candidates"][index],
                "summary": "",
                "source_block_ids": [block_id],
            }
            for index, block_id in enumerate(first["primary_block_ids"])
        ]
        pages.append({
            "page_id": "archive-page",
            "teaching_unit_id": second["teaching_unit_id"],
            "template_layout_id": _layout_for_request_blocks(
                second,
                second["primary_block_ids"],
            ),
            "title": second["title_candidates"][0],
            "summary": "",
            "source_block_ids": second["primary_block_ids"],
        })
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "pages": pages,
        }

    story = await plan_slide_story_v3(
        graph,
        template,
        ai_planner=planner,
    )

    assert len(calls) == 1
    first_unit, second_unit = graph.units
    first_pages = [
        page for page in story.pages
        if page.teaching_unit_id == first_unit.teaching_unit_id
    ]
    second_pages = [
        page for page in story.pages
        if page.teaching_unit_id == second_unit.teaching_unit_id
    ]
    assert len(first_pages) == len(first_unit.primary_block_ids)
    assert [
        block_id for page in first_pages for block_id in page.source_block_ids
    ] == first_unit.primary_block_ids
    assert [page.page_id for page in second_pages] == ["archive-page"]
    assert second_pages[0].source_block_ids == second_unit.primary_block_ids
    assert [
        block_id for page in story.pages for block_id in page.source_block_ids
    ] == graph.formal_block_ids
    validate_slide_story_plan_v3(story, graph, template)


@pytest.mark.asyncio
async def test_story_repair_names_duplicate_block_page_owners() -> None:
    document = _document()
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    calls = []

    async def planner(request):
        calls.append(request)
        unit = request["teaching_units"][0]
        layout = unit["allowed_template_layout_ids"][0]
        if len(calls) == 1:
            pages = [
                {
                    "page_id": f"duplicate-{index}",
                    "teaching_unit_id": unit["teaching_unit_id"],
                    "template_layout_id": layout,
                    "title": candidate,
                    "summary": "",
                    "source_block_ids": unit["primary_block_ids"],
                }
                for index, candidate in enumerate(unit["title_candidates"][:2], start=1)
            ]
        else:
            pages = [{
                "page_id": "deduplicated",
                "teaching_unit_id": unit["teaching_unit_id"],
                "template_layout_id": layout,
                "title": unit["title_candidates"][0],
                "summary": "",
                "source_block_ids": unit["primary_block_ids"],
            }]
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "pages": pages,
        }

    story = await plan_slide_story_v3(graph, template, ai_planner=planner)

    assert len(calls) == 2
    repair_target = calls[1]["repair_feedback"]["repair_targets"][0]
    assert repair_target["duplicate_source_block_ids"] == ["concept", "feedback"]
    assert repair_target["duplicate_page_ids"] == ["duplicate-1", "duplicate-2"]
    assert repair_target["missing_source_block_ids"] == []
    validate_slide_story_plan_v3(story, graph, template)


@pytest.mark.asyncio
async def test_story_batch_reports_the_exact_contract_error_after_bounded_repair() -> None:
    document = _document()
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    calls = 0

    async def planner(request):
        nonlocal calls
        calls += 1
        unit = request["teaching_units"][0]
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "pages": [{
                "page_id": f"invalid-{calls}",
                "teaching_unit_id": unit["teaching_unit_id"],
                "template_layout_id": "template-layout-not-in-contract",
                "title": unit["source_text"][:24],
                "summary": "",
                "source_block_ids": unit["primary_block_ids"],
            }],
        }

    with pytest.raises(V6BuildError) as captured:
        await plan_slide_story_v3(graph, template, ai_planner=planner)

    assert calls == 3
    assert captured.value.failure.code == "template_layout_unavailable"
    assert captured.value.failure.chapter_id == "chapter-a"
    assert captured.value.failure.batch_id == "story-1"


@pytest.mark.asyncio
async def test_visual_ai_failure_degrades_optional_page_but_not_required_code() -> None:
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")

    async def story_planner(request):
        unit = request["teaching_units"][0]
        if "code" in unit["artifact_kinds"]:
            slug = "/evidence-code"
        else:
            slug = "/practice-feedback"
        layout = next(item for item in unit["allowed_template_layout_ids"] if item.endswith(slug))
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "provider": "fixture",
            "model": "fixture",
            "attempts": 1,
            "pages": [{
                "page_id": f"page-{unit['teaching_unit_id']}",
                "teaching_unit_id": unit["teaching_unit_id"],
                "template_layout_id": layout,
                "title": "可靠闭环",
                "summary": "",
                "source_block_ids": unit["primary_block_ids"],
            }],
        }

    async def unavailable(_request):
        raise TimeoutError("visual planner unavailable")

    prose_document = _document()
    prose_graph = compile_course_presentation_graph(prose_document, teaching_plan={})
    prose_story = await plan_slide_story_v3(prose_graph, template, ai_planner=story_planner)
    prose_events: list[dict] = []
    degraded = await plan_slide_visuals_v2(
        prose_story,
        prose_graph,
        template,
        ai_planner=unavailable,
        batch_callback=lambda event: prose_events.append(event),
    )
    assert degraded.decisions[0].degraded is True
    assert degraded.decisions[0].decision == "text_native"
    degraded_diagnostic = next(
        event["diagnostic"]
        for event in prose_events
        if event["phase"] == "completed"
    )
    assert degraded_diagnostic.validation_status == "degraded"
    assert degraded_diagnostic.failure_category == "visual_ai_batch_timeout"

    code_document = _document(with_code=True)
    code_graph = compile_course_presentation_graph(code_document, teaching_plan={})
    code_story = await plan_slide_story_v3(code_graph, template, ai_planner=story_planner)
    code_events: list[dict] = []
    with pytest.raises(V6BuildError, match="visual_ai_required_artifact_failed"):
        await plan_slide_visuals_v2(
            code_story,
            code_graph,
            template,
            ai_planner=unavailable,
            batch_callback=lambda event: code_events.append(event),
        )
    failed_diagnostic = next(
        event["diagnostic"]
        for event in code_events
        if event["phase"] == "failed"
    )
    assert failed_diagnostic.validation_status == "failed"
    assert failed_diagnostic.failure_category == "visual_ai_required_artifact_failed"


@pytest.mark.asyncio
async def test_visual_failure_degrades_soft_page_without_discarding_required_table() -> None:
    """A soft diagram failure must not poison valid hard-artifact pages."""

    document = _structured_field_check_document()
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")

    async def story_planner(request):
        unit = request["teaching_units"][0]
        table_id, feedback_id = unit["primary_block_ids"]
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "pages": [
                {
                    "page_id": "field-required-table",
                    "teaching_unit_id": unit["teaching_unit_id"],
                    "template_layout_id": next(
                        layout_id
                        for layout_id in unit["allowed_template_layout_ids"]
                        if layout_id.endswith("/evidence-table")
                    ),
                    "title": unit["title_candidates"][0],
                    "summary": "",
                    "source_block_ids": [table_id],
                },
                {
                    "page_id": "field-soft-explanation",
                    "teaching_unit_id": unit["teaching_unit_id"],
                    "template_layout_id": _layout_for_request_blocks(
                        unit,
                        [feedback_id],
                    ),
                    "title": unit["title_candidates"][1],
                    "summary": "",
                    "source_block_ids": [feedback_id],
                },
            ],
        }

    story = await plan_slide_story_v3(
        graph,
        template,
        ai_planner=story_planner,
    )
    events: list[dict] = []

    async def visual_planner(request):
        decisions = []
        for page in request["pages"]:
            if page["page_id"] == "field-required-table":
                decisions.append({
                    "page_id": page["page_id"],
                    "decision": "table",
                    "source_block_ids": page["source_block_ids"],
                    "resolved_template_layout_id": page["template_layout_id"],
                })
                continue
            decisions.append({
                "page_id": page["page_id"],
                "decision": "diagram",
                "source_block_ids": page["source_block_ids"],
                "resolved_template_layout_id": page["template_layout_id"],
                "visual_payload": {
                    "nodes": [
                        {
                            "node_id": "invented",
                            "label": "Invented diagnostic stage",
                            "source_block_ids": page["source_block_ids"],
                        },
                        {
                            "node_id": "compare",
                            "label": "Compare every observation",
                            "source_block_ids": page["source_block_ids"],
                        },
                    ],
                    "edges": [{"source": "invented", "target": "compare"}],
                },
            })
        return {
            "schema_version": "slide_visual_batch_response_v2",
            "decisions": decisions,
        }

    visual = await plan_slide_visuals_v2(
        story,
        graph,
        template,
        ai_planner=visual_planner,
        batch_callback=lambda event: events.append(event),
    )

    decisions = {decision.page_id: decision for decision in visual.decisions}
    assert decisions["field-required-table"].decision == "table"
    assert decisions["field-required-table"].degraded is False
    assert decisions["field-soft-explanation"].decision == "text_native"
    assert decisions["field-soft-explanation"].degraded is True
    assert (
        decisions["field-soft-explanation"].degradation_reason
        == "visual_diagram_label_unsupported"
    )
    diagnostic = next(
        event["diagnostic"]
        for event in events
        if event["phase"] == "completed"
    )
    assert diagnostic.validation_status == "degraded"
    assert diagnostic.failure_category == "visual_diagram_label_unsupported"


@pytest.mark.asyncio
async def test_visual_ai_projects_source_bound_aliases_and_discards_draft_code() -> None:
    document = _document(with_code=True)
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")

    async def story_planner(request):
        unit = request["teaching_units"][0]
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "pages": [{
                "page_id": "generic-code-page",
                "teaching_unit_id": unit["teaching_unit_id"],
                "template_layout_id": next(
                    layout_id
                    for layout_id in unit["allowed_template_layout_ids"]
                    if layout_id.endswith("/evidence-code")
                ),
                "title": unit["title_candidates"][0],
                "summary": "",
                "source_block_ids": unit["primary_block_ids"],
            }],
        }

    story = await plan_slide_story_v3(graph, template, ai_planner=story_planner)
    requests = []

    async def visual_planner(request):
        requests.append(request)
        page = request["pages"][0]
        return {
            "schema_version": "slide_visual_batch_response_v2",
            "decisions": [{
                "page_id": page["page_id"],
                "decision_type": "code",
                "source_block_ids": ["provider-must-not-rebind-source"],
                "resolved_template_layout_id": "provider-must-not-rebind-layout",
                "code_payload": {
                    "language": "python",
                    "code": "invented_code_must_not_be_consumed()",
                },
            }],
        }

    visual = await plan_slide_visuals_v2(
        story,
        graph,
        template,
        ai_planner=visual_planner,
    )

    decision = visual.decisions[0]
    assert requests[0]["response_contract"]["forbidden_decision_fields"] == [
        "decision_type",
        "code_payload",
    ]
    assert decision.decision == "code"
    assert decision.source_block_ids == story.pages[0].source_block_ids
    assert decision.resolved_template_layout_id == story.pages[0].template_layout_id
    assert decision.visual_payload == {}


@pytest.mark.asyncio
async def test_visual_ai_repairs_required_subject_representation_per_batch() -> None:
    document = _document(with_code=True)
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")

    async def story_planner(request):
        unit = request["teaching_units"][0]
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "pages": [{
                "page_id": "generic-required-code",
                "teaching_unit_id": unit["teaching_unit_id"],
                "template_layout_id": next(
                    layout_id
                    for layout_id in unit["allowed_template_layout_ids"]
                    if layout_id.endswith("/evidence-code")
                ),
                "title": unit["title_candidates"][0],
                "summary": "",
                "source_block_ids": unit["primary_block_ids"],
            }],
        }

    story = await plan_slide_story_v3(graph, template, ai_planner=story_planner)
    calls = []

    async def visual_planner(request):
        calls.append(request)
        page = request["pages"][0]
        return {
            "schema_version": "slide_visual_batch_response_v2",
            "decisions": [{
                "page_id": page["page_id"],
                "decision": "table" if len(calls) == 1 else "code",
                "source_block_ids": page["source_block_ids"],
                "resolved_template_layout_id": page["template_layout_id"],
            }],
        }

    visual = await plan_slide_visuals_v2(
        story,
        graph,
        template,
        ai_planner=visual_planner,
    )

    assert len(calls) == 2
    repair_target = calls[1]["repair_feedback"]["repair_targets"][0]
    assert repair_target["page_id"] == "generic-required-code"
    assert repair_target["required_artifact_kinds"] == ["code"]
    assert repair_target["allowed_decisions"] == ["code"]
    assert repair_target["required_template_layout_id"] == story.pages[0].template_layout_id
    assert visual.decisions[0].decision == "code"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    (
        "artifact_kind",
        "artifact_markdown",
        "visual_decision",
        "allowed_decisions",
    ),
    [
        ("code", "```python\nprint('evidence')\n```", "code", ["code"]),
        ("formula", "$$E = mc^2$$", "formula", ["formula"]),
        (
            "table",
            "| Input | Result |\n|---|---|\n| A | Pass |",
            "table",
            ["data", "table"],
        ),
    ],
)
async def test_visual_artifact_contract_is_scoped_to_page_source_blocks(
    artifact_kind: str,
    artifact_markdown: str,
    visual_decision: str,
    allowed_decisions: list[str],
) -> None:
    document = _mixed_artifact_document(artifact_kind, artifact_markdown)
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")

    async def story_planner(request):
        unit = request["teaching_units"][0]
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "pages": [
                {
                    "page_id": "context-page",
                    "teaching_unit_id": unit["teaching_unit_id"],
                    "template_layout_id": _layout_for_request_blocks(
                        unit,
                        ["context"],
                    ),
                    "title": "Observe the evidence",
                    "summary": "",
                    "source_block_ids": ["context"],
                },
                {
                    "page_id": "artifact-page",
                    "teaching_unit_id": unit["teaching_unit_id"],
                    "template_layout_id": _layout_for_request_blocks(
                        unit,
                        ["artifact"],
                    ),
                    "title": "Apply the representation",
                    "summary": "",
                    "source_block_ids": ["artifact"],
                },
            ],
        }

    story = await plan_slide_story_v3(
        graph,
        template,
        ai_planner=story_planner,
    )
    requests = []

    async def visual_planner(request):
        requests.append(request)
        pages = {page["page_id"]: page for page in request["pages"]}
        return {
            "schema_version": "slide_visual_batch_response_v2",
            "decisions": [
                {
                    "page_id": "context-page",
                    "decision": "text_native",
                    "source_block_ids": pages["context-page"]["source_block_ids"],
                    "resolved_template_layout_id": pages["context-page"][
                        "template_layout_id"
                    ],
                },
                {
                    "page_id": "artifact-page",
                    "decision": visual_decision,
                    "source_block_ids": pages["artifact-page"]["source_block_ids"],
                    "resolved_template_layout_id": pages["artifact-page"][
                        "template_layout_id"
                    ],
                },
            ],
        }

    visual = await plan_slide_visuals_v2(
        story,
        graph,
        template,
        ai_planner=visual_planner,
    )

    requested_pages = {
        page["page_id"]: page for page in requests[0]["pages"]
    }
    assert requested_pages["context-page"]["artifact_kinds"] == []
    assert requested_pages["context-page"]["allowed_decisions"] == [
        "diagram",
        "text_native",
    ]
    assert requested_pages["artifact-page"]["artifact_kinds"] == [
        artifact_kind
    ]
    assert requested_pages["artifact-page"]["allowed_decisions"] == (
        allowed_decisions
    )
    assert visual.decisions[0].decision == "text_native"
    assert visual.decisions[1].decision == visual_decision


@pytest.mark.asyncio
async def test_non_artifact_course_keeps_text_native_as_a_valid_visual_language() -> None:
    document = _document()
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")

    async def story_planner(request):
        unit = request["teaching_units"][0]
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "pages": [{
                "page_id": "generic-prose-page",
                "teaching_unit_id": unit["teaching_unit_id"],
                "template_layout_id": _layout_for_request_blocks(
                    unit,
                    unit["primary_block_ids"],
                ),
                "title": unit["title_candidates"][0],
                "summary": "",
                "source_block_ids": unit["primary_block_ids"],
            }],
        }

    story = await plan_slide_story_v3(
        graph,
        template,
        ai_planner=story_planner,
    )
    requests = []

    async def visual_planner(request):
        requests.append(request)
        page = request["pages"][0]
        return {
            "schema_version": "slide_visual_batch_response_v2",
            "decisions": [{
                "page_id": page["page_id"],
                "decision": "text_native",
                "source_block_ids": page["source_block_ids"],
                "resolved_template_layout_id": page["template_layout_id"],
            }],
        }

    visual = await plan_slide_visuals_v2(
        story,
        graph,
        template,
        ai_planner=visual_planner,
    )

    assert requests[0]["pages"][0]["artifact_kinds"] == []
    assert requests[0]["pages"][0]["allowed_decisions"] == [
        "diagram",
        "text_native",
    ]
    assert visual.decisions[0].decision == "text_native"


@pytest.mark.asyncio
async def test_required_diagram_layout_restricts_visual_ai_to_diagram() -> None:
    document = refresh_document_revision(
        CourseDocument(
            course_id="generic-observation-flow",
            title="Observation flow",
            sections=[CourseSection(section_id="field", title="Field review", position=0)],
            blocks=[CourseBlock(
                block_id="flow",
                section_id="field",
                position=0,
                role="concept",
                payload={
                    "markdown": (
                        "## Review the observation flow\n"
                        "Collect the field sample, compare the observation, "
                        "and record the verified result."
                    )
                },
            )],
        )
    )
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")

    async def story_planner(request):
        unit = request["teaching_units"][0]
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "pages": [{
                "page_id": "observation-flow",
                "teaching_unit_id": unit["teaching_unit_id"],
                "template_layout_id": next(
                    layout_id
                    for layout_id in unit["allowed_template_layout_ids"]
                    if layout_id.endswith("/evidence-diagram")
                ),
                "title": unit["title_candidates"][0],
                "summary": "",
                "source_block_ids": unit["primary_block_ids"],
            }],
        }

    story = await plan_slide_story_v3(
        graph,
        template,
        ai_planner=story_planner,
    )
    calls = []

    async def visual_planner(request):
        calls.append(request)
        page = request["pages"][0]
        decision = "text_native" if len(calls) == 1 else "diagram"
        payload = {}
        if decision == "diagram":
            payload = {
                "nodes": [
                    {
                        "node_id": "collect",
                        "label": "Collect the field sample",
                        "source_block_ids": ["flow"],
                    },
                    {
                        "node_id": "compare",
                        "label": "Compare the observation",
                        "source_block_ids": ["flow"],
                    },
                    {
                        "node_id": "record",
                        "label": "Record the verified result",
                        "source_block_ids": ["flow"],
                    },
                ],
                "edges": [
                    {"source": "collect", "target": "compare"},
                    {"source": "compare", "target": "record"},
                ],
            }
        return {
            "schema_version": "slide_visual_batch_response_v2",
            "decisions": [{
                "page_id": page["page_id"],
                "decision": decision,
                "source_block_ids": page["source_block_ids"],
                "resolved_template_layout_id": page["template_layout_id"],
                "visual_payload": payload,
            }],
        }

    visual = await plan_slide_visuals_v2(
        story,
        graph,
        template,
        ai_planner=visual_planner,
    )

    assert len(calls) == 2
    assert calls[0]["pages"][0]["layout_artifact_kinds"] == ["diagram"]
    assert calls[0]["pages"][0]["layout_requires_artifact"] is True
    assert calls[0]["pages"][0]["allowed_decisions"] == ["diagram"]
    repair_target = calls[1]["repair_feedback"]["repair_targets"][0]
    assert repair_target["allowed_decisions"] == ["diagram"]
    assert visual.decisions[0].decision == "diagram"


@pytest.mark.asyncio
async def test_invalid_diagram_edges_degrade_to_safe_text_layout_and_compile() -> None:
    document = refresh_document_revision(
        CourseDocument(
            course_id="generic-observation-edge-fallback",
            title="Observation verification flow",
            sections=[CourseSection(
                section_id="field",
                title="Field verification",
                position=0,
            )],
            blocks=[CourseBlock(
                block_id="flow",
                section_id="field",
                position=0,
                role="concept",
                payload={
                    "markdown": (
                        "## Review the observation flow\n"
                        "Collect the field sample and record its location, time, and "
                        "environment. Compare the observation against the expected "
                        "criteria, retain the original evidence, and record the verified "
                        "result together with any exception that still needs review."
                    )
                },
            )],
        )
    )
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")

    async def story_planner(request):
        unit = request["teaching_units"][0]
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "pages": [{
                "page_id": "observation-flow",
                "teaching_unit_id": unit["teaching_unit_id"],
                "template_layout_id": next(
                    layout_id
                    for layout_id in unit["allowed_template_layout_ids"]
                    if layout_id.endswith("/evidence-diagram")
                ),
                "title": "Review the observation flow",
                "summary": "",
                "source_block_ids": unit["primary_block_ids"],
            }],
        }

    story = await plan_slide_story_v3(
        graph,
        template,
        ai_planner=story_planner,
    )
    calls = []

    async def visual_planner(request):
        calls.append(request)
        page = request["pages"][0]
        return {
            "schema_version": "slide_visual_batch_response_v2",
            "decisions": [{
                "page_id": page["page_id"],
                "decision": "diagram",
                "source_block_ids": page["source_block_ids"],
                "resolved_template_layout_id": page["template_layout_id"],
                "visual_payload": {
                    "nodes": [
                        {
                            "node_id": "collect",
                            "label": "Collect the field sample",
                            "source_block_ids": ["flow"],
                        },
                        {
                            "node_id": "compare",
                            "label": "Compare the observation",
                            "source_block_ids": ["flow"],
                        },
                        {
                            "node_id": "record",
                            "label": "Record the verified result",
                            "source_block_ids": ["flow"],
                        },
                    ],
                    "edges": [
                        {"source": "collect", "target": "missing-node"},
                    ],
                },
            }],
        }

    visual = await plan_slide_visuals_v2(
        story,
        graph,
        template,
        ai_planner=visual_planner,
    )

    assert len(calls) == 2
    repair_target = calls[1]["repair_feedback"]["repair_targets"][0]
    assert repair_target["declared_node_ids"] == ["collect", "compare", "record"]
    assert repair_target["invalid_edges"] == [
        {"source": "collect", "target": "missing-node"},
    ]
    decision = visual.decisions[0]
    assert decision.decision == "text_native"
    assert decision.degraded is True
    assert decision.degradation_reason == "visual_diagram_edge_invalid"
    assert decision.resolved_template_layout_id.endswith("/content-stack")

    deck = compile_slide_deck_v6(document, graph, story, visual, template)

    assert deck.status == "v6_needs_manual_edit"
    assert deck.pages[0].resolved_layout.endswith("/content-stack")
    assert "missing-node" not in str(deck.model_dump(mode="json"))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("asset_refs", "figure_layout_allowed"),
    [([], False), (["source-photo"], True)],
)
async def test_story_layout_registry_requires_source_support_for_mandatory_figures(
    asset_refs: list[str],
    figure_layout_allowed: bool,
) -> None:
    document = refresh_document_revision(
        CourseDocument(
            course_id="generic-habitat-observation",
            title="Habitat observation",
            sections=[CourseSection(section_id="habitat", title="Habitat", position=0)],
            blocks=[CourseBlock(
                block_id="observation",
                section_id="habitat",
                position=0,
                role="concept",
                payload={"markdown": "## Observe habitat evidence and explain the finding"},
                asset_refs=asset_refs,
            )],
        )
    )
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    requests = []

    async def story_planner(request):
        requests.append(request)
        unit = request["teaching_units"][0]
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "pages": [{
                "page_id": "habitat-page",
                "teaching_unit_id": unit["teaching_unit_id"],
                "template_layout_id": next(
                    layout_id
                    for layout_id in unit["allowed_template_layout_ids"]
                    if layout_id.endswith("/content-stack")
                ),
                "title": unit["title_candidates"][0],
                "summary": "",
                "source_block_ids": unit["primary_block_ids"],
            }],
        }

    await plan_slide_story_v3(graph, template, ai_planner=story_planner)

    allowed_layouts = requests[0]["teaching_units"][0]["allowed_template_layout_ids"]
    assert any(layout_id.endswith("/evidence-diagram") for layout_id in allowed_layouts)
    assert any(layout_id.endswith("/evidence-figure") for layout_id in allowed_layouts) is figure_layout_allowed


@pytest.mark.asyncio
async def test_visual_ai_repairs_only_the_failed_diagram_node_with_bound_sources() -> None:
    document = refresh_document_revision(
        CourseDocument(
            course_id="generic-field-review",
            title="Field evidence review",
            sections=[CourseSection(section_id="field", title="Review", position=0)],
            blocks=[CourseBlock(
                block_id="flow",
                section_id="field",
                position=0,
                role="reasoning",
                kind="diagram",
                payload={
                    "markdown": (
                        "Collect the field sample, review the evidence record, "
                        "and publish the verified finding."
                    )
                },
            )],
        )
    )
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")

    async def story_planner(request):
        unit = request["teaching_units"][0]
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "pages": [{
                "page_id": "field-flow",
                "teaching_unit_id": unit["teaching_unit_id"],
                "template_layout_id": next(
                    layout_id
                    for layout_id in unit["allowed_template_layout_ids"]
                    if layout_id.endswith("/evidence-diagram")
                ),
                "title": unit["title_candidates"][0],
                "summary": "",
                "source_block_ids": ["flow"],
            }],
        }

    story = await plan_slide_story_v3(
        graph,
        template,
        ai_planner=story_planner,
    )
    calls = []

    async def visual_planner(request):
        calls.append(request)
        page = request["pages"][0]
        first_attempt = len(calls) == 1
        return {
            "schema_version": "slide_visual_batch_response_v2",
            "decisions": [{
                "page_id": page["page_id"],
                "decision": "diagram",
                "source_block_ids": page["source_block_ids"],
                "resolved_template_layout_id": page["template_layout_id"],
                "visual_payload": {
                    "nodes": [
                        {
                            "node_id": "collect",
                            "label": (
                                "Invented diagnostic stage"
                                if first_attempt
                                else "Collect the field sample"
                            ),
                            "source_block_ids": ["flow"],
                        },
                        {
                            "node_id": "review",
                            "label": (
                                "Review the evidence record"
                                if first_attempt
                                else "Publish the verified finding"
                            ),
                            "source_block_ids": ["flow"],
                        },
                    ],
                    "edges": [{"source": "collect", "target": "review"}],
                },
            }],
        }

    visual = await plan_slide_visuals_v2(
        story,
        graph,
        template,
        ai_planner=visual_planner,
    )

    assert len(calls) == 2
    first_page = calls[0]["pages"][0]
    assert first_page["source_text"] == document.blocks[0].payload["markdown"]
    assert first_page["source_blocks"] == [{
        "block_id": "flow",
        "source_text": document.blocks[0].payload["markdown"],
    }]
    repair_target = calls[1]["repair_feedback"]["repair_targets"][0]
    assert repair_target["failed_node_ids"] == ["collect"]
    assert [node["node_id"] for node in repair_target["locked_nodes"]] == ["review"]
    assert repair_target["source_blocks"] == first_page["source_blocks"]
    nodes = {
        node["node_id"]: node
        for node in visual.decisions[0].visual_payload["nodes"]
    }
    assert nodes["collect"]["label"] == "Collect the field sample"
    assert nodes["review"]["label"] == "Review the evidence record"


@pytest.mark.asyncio
async def test_visual_batches_honor_shared_concurrency_limit() -> None:
    document = refresh_document_revision(
        CourseDocument(
            course_id="generic-many-chapters",
            title="观察与解释",
            sections=[CourseSection(section_id=f"s{i}", title=f"阶段 {i}", position=i) for i in range(6)],
            blocks=[
                CourseBlock(
                    block_id=f"b{i}",
                    section_id=f"s{i}",
                    position=0,
                    role="concept",
                    payload={"markdown": f"第 {i} 阶段先记录观察，再解释证据。"},
                )
                for i in range(6)
            ],
        )
    )
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")

    async def story_planner(request):
        unit = request["teaching_units"][0]
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "provider": "fixture",
            "model": "fixture",
            "attempts": 1,
            "pages": [{
                "page_id": f"page-{request['chapter_id']}",
                "teaching_unit_id": unit["teaching_unit_id"],
                "template_layout_id": next(item for item in unit["allowed_template_layout_ids"] if item.endswith("/content-stack")),
                "title": request["chapter_id"],
                "summary": "",
                "source_block_ids": unit["primary_block_ids"],
            }],
        }

    story = await plan_slide_story_v3(graph, template, ai_planner=story_planner)
    active = 0
    peak = 0

    async def visual_planner(request):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1
        return {
            "schema_version": "slide_visual_batch_response_v2",
            "provider": "fixture",
            "model": "fixture",
            "attempts": 1,
            "decisions": [{
                "page_id": page["page_id"],
                "decision": "text_native",
                "source_block_ids": page["source_block_ids"],
                "resolved_template_layout_id": page["template_layout_id"],
            } for page in request["pages"]],
        }

    visual = await plan_slide_visuals_v2(story, graph, template, ai_planner=visual_planner, concurrency=3)

    assert len(visual.decisions) == 6
    assert peak == 3


def _field_visual_repair_fixture():
    document = _structured_field_check_document()
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    unit = graph.units[0]
    table_layout = next(
        layout.template_layout_id
        for layout in template.layouts
        if layout.template_layout_id.endswith("/evidence-table")
    )
    feedback_layout = next(
        layout.template_layout_id
        for layout in template.layouts
        if layout.template_layout_id.endswith("/practice-feedback")
    )
    story = SlideStoryPlanV3(
        source_document_revision=graph.source_document_revision,
        template_digest=template.template_digest,
        batches=[SlideStoryBatchV3(
            batch_id="story-field-check",
            chapter_id="field-check",
            provider="fixture",
            model="fixture",
            duration_ms=1,
            attempts=1,
            validation_status="passed",
            pages=[
                SlideStoryPageV3(
                    page_id="field-table",
                    teaching_unit_id=unit.teaching_unit_id,
                    template_layout_id=table_layout,
                    title="Observation evidence",
                    summary="",
                    source_block_ids=["field-task-table"],
                    page_ordinal=0,
                ),
                SlideStoryPageV3(
                    page_id="field-feedback",
                    teaching_unit_id=unit.teaching_unit_id,
                    template_layout_id=feedback_layout,
                    title="Interpret the record",
                    summary="",
                    source_block_ids=["field-feedback"],
                    page_ordinal=1,
                ),
            ],
        )],
    )
    visual = SlideVisualPlanV2(
        source_document_revision=graph.source_document_revision,
        template_digest=template.template_digest,
        decisions=[
            SlideVisualDecisionV2(
                page_id="field-table",
                decision="table",
                source_block_ids=["field-task-table"],
                resolved_template_layout_id=table_layout,
                provider="fixture",
                model="fixture",
            ),
            SlideVisualDecisionV2(
                page_id="field-feedback",
                decision="text_native",
                source_block_ids=["field-feedback"],
                resolved_template_layout_id=feedback_layout,
                degraded=True,
                degradation_reason="visual_ai_batch_failed",
            ),
        ],
    )
    return graph, template, story, visual


@pytest.mark.asyncio
async def test_visual_repair_replans_only_degraded_pages_and_preserves_healthy_decisions() -> None:
    """Selective repair must be independent of course subject and keep good work intact."""

    graph, template, story, visual = _field_visual_repair_fixture()
    requests = []

    async def planner(request):
        requests.append(request)
        page = request["pages"][0]
        return {
            "schema_version": "slide_visual_batch_response_v2",
            "provider": "fixture",
            "model": "fixture",
            "decisions": [{
                "page_id": page["page_id"],
                "decision": "text_native",
                "source_block_ids": page["source_block_ids"],
                "resolved_template_layout_id": page["template_layout_id"],
            }],
        }

    repaired = await repair_slide_visuals_v2(
        story,
        graph,
        template,
        visual,
        ai_planner=planner,
    )

    assert [[page["page_id"] for page in request["pages"]] for request in requests] == [
        ["field-feedback"]
    ]
    assert repaired.decisions[0] is visual.decisions[0]
    assert repaired.decisions[0].model_dump() == visual.decisions[0].model_dump()
    assert repaired.decisions[1].degraded is False
    assert repaired.decisions[1].provider == "fixture"
    assert all(not decision.degraded for decision in repaired.decisions)


@pytest.mark.asyncio
async def test_visual_repair_rejects_an_incomplete_retry_without_mutating_the_prior_plan() -> None:
    graph, template, story, visual = _field_visual_repair_fixture()
    original = visual.model_dump(mode="json")

    async def unavailable(_request):
        raise TimeoutError("temporary shared provider outage")

    with pytest.raises(V6BuildError) as captured:
        await repair_slide_visuals_v2(
            story,
            graph,
            template,
            visual,
            ai_planner=unavailable,
        )

    assert captured.value.failure.code == "visual_repair_incomplete"
    assert captured.value.failure.page_id == "field-feedback"
    assert visual.model_dump(mode="json") == original


@pytest.mark.asyncio
async def test_visual_planning_resume_requests_only_missing_pages_in_a_partial_batch() -> None:
    """A repair checkpoint may preserve healthy pages inside a degraded chapter batch."""

    graph, template, story, visual = _field_visual_repair_fixture()
    healthy_table = visual.decisions[0]
    requested_page_ids = []

    async def planner(request):
        requested_page_ids.append([page["page_id"] for page in request["pages"]])
        page = request["pages"][0]
        return {
            "schema_version": "slide_visual_batch_response_v2",
            "provider": "fixture",
            "model": "fixture",
            "decisions": [{
                "page_id": page["page_id"],
                "decision": "text_native",
                "source_block_ids": page["source_block_ids"],
                "resolved_template_layout_id": page["template_layout_id"],
            }],
        }

    resumed = await plan_slide_visuals_v2(
        story,
        graph,
        template,
        ai_planner=planner,
        resume_decisions=[healthy_table],
    )

    assert requested_page_ids == [["field-feedback"]]
    assert resumed.decisions[0] is healthy_table
    assert [decision.page_id for decision in resumed.decisions] == [
        "field-table",
        "field-feedback",
    ]
