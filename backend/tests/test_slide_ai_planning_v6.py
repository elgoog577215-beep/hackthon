import asyncio

import pytest

from course_document import CourseBlock, CourseDocument, CourseSection, refresh_document_revision
from course_presentation_graph import compile_course_presentation_graph
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
    assert calls[0]["response_contract"]["required_page_fields"] == [
        "page_id",
        "teaching_unit_id",
        "template_layout_id",
        "title",
        "source_block_ids",
    ]
    assert calls[0]["response_contract"]["forbidden_page_fields"] == ["content"]
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
    calls = 0

    async def planner(request):
        nonlocal calls
        calls += 1
        unit = request["teaching_units"][0]
        layout = (
            "template-layout-not-in-contract"
            if calls == 1
            else unit["allowed_template_layout_ids"][0]
        )
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "provider": "rotating-fixture",
            "model": "generic-model",
            "attempts": 1,
            "pages": [{
                "page_id": f"page-{calls}",
                "teaching_unit_id": unit["teaching_unit_id"],
                "template_layout_id": layout,
                "title": unit["source_text"][:24],
                "summary": "",
                "source_block_ids": unit["primary_block_ids"],
            }],
        }

    story = await plan_slide_story_v3(graph, template, ai_planner=planner)

    assert calls == 2
    assert story.batches[0].attempts == 2


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

    assert calls == 2
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
