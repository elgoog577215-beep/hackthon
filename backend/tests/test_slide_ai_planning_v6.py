import asyncio

import pytest

from course_document import CourseBlock, CourseDocument, CourseSection, refresh_document_revision
from course_presentation_graph import (
    compile_course_presentation_graph,
    teaching_intent_for_roles,
)
from slide_ai_planning_v6 import plan_slide_story_v3, plan_slide_visuals_v2
from slide_deck_v6 import V6BuildError, validate_slide_story_plan_v3
from template_layout_contract import compile_builtin_template_layout_contract_v1


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
                    "title": "完成一次可靠闭环",
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
    assert repair_target["allowed_page_count_range"] == [1, 3]
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
    assert repair_target["summary_policy"] == "exact_source_excerpt_or_empty"
    assert story.batches[0].attempts == 2


@pytest.mark.asyncio
async def test_story_batch_repairs_a_title_over_the_selected_layout_capacity() -> None:
    document = _document()
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    calls = []

    async def planner(request):
        calls.append(request)
        unit = request["teaching_units"][0]
        if len(calls) == 1:
            title = unit["source_text"][: unit["title_max_chars"] + 1]
        else:
            repair_target = request["repair_feedback"]["repair_targets"][0]
            title = repair_target["available_title_candidates"][0]
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "pages": [{
                "page_id": "generic-capacity-page",
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
                    "title": unit["title_candidates"][0],
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
                    "title": unit["title_candidates"][1],
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
                    "title": unit["title_candidates"][0],
                    "summary": "",
                    "source_block_ids": [concept_id],
                },
                {
                    "page_id": "field-feedback",
                    "teaching_unit_id": unit["teaching_unit_id"],
                    "template_layout_id": feedback_layout,
                    "title": unit["title_candidates"][1],
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

    assert len(calls) == 2
    target = calls[1]["repair_feedback"]["repair_targets"][0]
    assert target["current_summary"] == "UnsupportedIdentifier_999"
    assert target["summary_policy"] == "exact_source_excerpt_or_empty"
    assert story.pages[0].summary == ""
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
async def test_story_batches_reserve_titles_accepted_by_prior_chapters() -> None:
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
                payload={"markdown": "## Shared checkpoint\n## Beta evidence"},
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
    assert calls[1]["constraints"]["forbidden_titles"] == ["Shared checkpoint"]
    assert [page.title for page in story.pages] == [
        "Shared checkpoint",
        "Beta evidence",
    ]
    validate_slide_story_plan_v3(story, graph, template)


@pytest.mark.asyncio
async def test_story_repair_names_all_pages_when_unit_exceeds_page_limit() -> None:
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

    assert len(calls) == 2
    repair_target = calls[1]["repair_feedback"]["repair_targets"][0]
    assert repair_target["allowed_page_count_range"] == [1, 3]
    assert repair_target["observed_unit_page_ids"] == [
        "too-many-1",
        "too-many-2",
        "too-many-3",
        "too-many-4",
    ]
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
    degraded = await plan_slide_visuals_v2(
        prose_story,
        prose_graph,
        template,
        ai_planner=unavailable,
    )
    assert degraded.decisions[0].degraded is True
    assert degraded.decisions[0].decision == "text_native"

    code_document = _document(with_code=True)
    code_graph = compile_course_presentation_graph(code_document, teaching_plan={})
    code_story = await plan_slide_story_v3(code_graph, template, ai_planner=story_planner)
    with pytest.raises(V6BuildError, match="visual_ai_required_artifact_failed"):
        await plan_slide_visuals_v2(code_story, code_graph, template, ai_planner=unavailable)


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
