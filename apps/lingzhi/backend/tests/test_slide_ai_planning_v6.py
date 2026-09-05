import asyncio
import json
import threading
import time
from pathlib import Path

import pytest

import slide_ai_planning_v6 as planning_module
from ai_base import AIProviderRequestError, AIProviderUnavailable
from course_document import CourseBlock, CourseDocument, CourseSection, refresh_document_revision
from course_presentation_graph import (
    compile_course_presentation_graph,
    teaching_intent_for_roles,
)
from slide_ai_planning_v6 import (
    AIPlannerInvocationError,
    _grounded_title_candidates,
    build_ai_base_story_planner_v6,
    build_ai_base_visual_planner_v2,
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

_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "slide_deck_v6"


def test_v6_planners_use_the_dedicated_ppt_provider_profile(monkeypatch):
    profiles: list[str | None] = []

    class CapturingAIBase:
        def __init__(self, *, provider_profile=None):
            profiles.append(provider_profile)

    monkeypatch.setattr(planning_module, "AIBase", CapturingAIBase)

    planning_module.build_ai_base_story_planner_v6()
    planning_module.build_ai_base_visual_planner_v2()

    assert profiles == ["ppt", "ppt"]


@pytest.mark.parametrize(
    ("provider", "model", "stage"),
    [
        ("teacher-plan-adapter", "provider-selected", "story"),
        ("shared-ai-pool", "source-faithful-deterministic", "story"),
        ("shared-ai-pool", "source-native-deterministic", "visual"),
    ],
)
def test_v6_rejects_retired_deterministic_teacher_planner_provenance(
    provider: str,
    model: str,
    stage: str,
) -> None:
    with pytest.raises(
        V6BuildError,
        match=f"{stage}_deterministic_adapter_forbidden",
    ):
        planning_module._require_ai_planner_provenance(
            provider=provider,
            model=model,
            stage=stage,
        )


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("给出 3 道练习题", "3 道练习题"),
        ("重点突出：三角行列式的值为对角线元素乘积", "三角行列式的值为对角线元素乘积"),
        ("在形式化定义之前建立矩阵运算的直觉感知", "矩阵运算的直觉感知"),
        ("用几何直观建立行列式", "行列式的几何直观"),
        ("选取一个二阶可逆矩阵", "二阶可逆矩阵示例"),
        ("提供一组难度递进的题目", "难度递进练习"),
        ("输出须逐步写出三次数乘、对应分量相加", "三次数乘与对应分量相加"),
        ("标注各对象的维度", "各对象的维度"),
        ("提交完整变换记录", "完整变换记录"),
    ],
)
def test_story_title_projection_removes_production_language(
    source: str,
    expected: str,
) -> None:
    assert planning_module._audience_facing_title_candidate(source) == expected
    assert not planning_module._generic_teaching_page_title(expected)


def test_story_title_candidates_add_the_confirmed_section_subject_to_practice() -> None:
    document = refresh_document_revision(CourseDocument(
        course_id="math-practice-title",
        title="线性代数",
        sections=[CourseSection(
            section_id="matrix",
            title="1.1 矩阵的基本概念与运算",
            position=0,
        )],
        blocks=[CourseBlock(
            block_id="matrix-practice",
            section_id="matrix",
            position=0,
            role="activity",
            payload={
                "title": "给出 3 道练习题",
                "markdown": "给出 3 道练习题，覆盖矩阵加法、数乘和乘法。",
            },
        )],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")

    request_unit = planning_module._story_unit_request(graph.units[0], template)

    assert (
        "矩阵的基本概念与运算练习"
        in request_unit["primary_blocks"][0]["title_candidates"]
    )


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


def test_text_native_fallback_rebinds_unstructured_process_to_body_layout() -> None:
    """Visual degradation must validate the original layout before retaining it."""

    document = refresh_document_revision(
        CourseDocument(
            course_id="generic-unstructured-process",
            title="Runtime observation",
            sections=[
                CourseSection(
                    section_id="chapter-a",
                    title="Observe and explain",
                    position=0,
                )
            ],
            blocks=[
                CourseBlock(
                    block_id="runtime-observation",
                    section_id="chapter-a",
                    position=0,
                    role="concept",
                    payload={
                        "markdown": (
                            "The runtime inspector exposes current values while the "
                            "console records diagnostic output. Serialized fields "
                            "remain visible during play mode, and the developer "
                            "compares observations before changing the script."
                        )
                    },
                )
            ],
        )
    )
    graph = compile_course_presentation_graph(
        document,
        teaching_plan={},
    )
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    unit = graph.units[0].model_copy(update={
        "primary_block_roles": {"runtime-observation": "reasoning"},
        "teaching_intent": "mechanism",
    })
    process_layout_id = template.layout_id("process-flow")
    page = SlideStoryPageV3(
        page_id="runtime-process",
        teaching_unit_id=unit.teaching_unit_id,
        template_layout_id=process_layout_id,
        title="Runtime observation",
        summary="Observe values and compare the recorded evidence.",
        source_block_ids=unit.primary_block_ids,
        page_ordinal=0,
    )

    fallback_layout_id = planning_module._safe_text_native_fallback_layout_id(
        page,
        unit,
        template,
    )

    assert fallback_layout_id == template.layout_id("content-stack")


def test_text_native_fallback_rebinds_an_unrenderable_single_process_item() -> None:
    """One very long step stays complete by using a safe body layout."""

    long_identifier = (
        "CollisionListener_OnCollisionEnter_PlayerController_" * 12
    )
    document = refresh_document_revision(CourseDocument(
        course_id="generic-long-process-item",
        title="Runtime verification",
        sections=[CourseSection(
            section_id="chapter-a",
            title="Verify the callback",
            position=0,
        )],
        blocks=[CourseBlock(
            block_id="long-process-item",
            section_id="chapter-a",
            position=0,
            role="activity",
            payload={
                "markdown": (
                    "1. Verify List<Action<CollisionListener>> using "
                    f"{long_identifier} and preserve the complete result."
                )
            },
        )],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    unit = graph.units[0]
    page = SlideStoryPageV3(
        page_id="long-process-page",
        teaching_unit_id=unit.teaching_unit_id,
        template_layout_id=template.layout_id("process-flow"),
        title="Verify the callback",
        summary="",
        source_block_ids=unit.primary_block_ids,
        page_ordinal=0,
    )

    fallback_layout_id = planning_module._safe_text_native_fallback_layout_id(
        page,
        unit,
        template,
    )

    assert fallback_layout_id == template.layout_id("content-stack")
    assert (
        "List<Action<CollisionListener>>"
        in planning_module._visible_prose_text(unit.source_text)
    )


@pytest.mark.asyncio
async def test_story_normalization_rebinds_each_page_by_its_own_source_shape() -> None:
    """A layout valid for the whole unit must not mask an invalid page slice."""

    document = refresh_document_revision(
        CourseDocument(
            course_id="generic-page-local-layout",
            title="Runtime observation",
            sections=[
                CourseSection(
                    section_id="chapter-a",
                    title="Observe and verify",
                    position=0,
                )
            ],
            blocks=[
                CourseBlock(
                    block_id="observation",
                    section_id="chapter-a",
                    position=0,
                    role="reasoning",
                    payload={
                        "markdown": (
                            "The runtime inspector exposes current values while the "
                            "console records diagnostic output. Serialized fields remain "
                            "visible during play mode so observations can be compared."
                        )
                    },
                ),
                CourseBlock(
                    block_id="verification-steps",
                    section_id="chapter-a",
                    position=1,
                    role="activity",
                    payload={
                        "markdown": (
                            "1. Capture the current inspector values.\n"
                            "2. Run the scene and record the console output.\n"
                            "3. Compare both records before editing the script."
                        )
                    },
                ),
            ],
        )
    )
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    process_layout_id = template.layout_id("process-flow")
    content_layout_id = template.layout_id("content-stack")
    practice_layout_id = template.layout_id("practice-prompt")
    planner_invocations = 0

    async def planner(request):
        nonlocal planner_invocations
        planner_invocations += 1
        unit = request["teaching_units"][0]
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "provider": "fixture",
            "model": "fixture",
            "attempts": 1,
            "pages": [
                {
                    "page_id": "observation-page",
                    "teaching_unit_id": unit["teaching_unit_id"],
                    "template_layout_id": process_layout_id,
                    "title": "Runtime inspector values",
                    "summary": "",
                    "source_block_ids": ["observation"],
                },
                {
                    "page_id": "verification-page",
                    "teaching_unit_id": unit["teaching_unit_id"],
                    "template_layout_id": practice_layout_id,
                    "title": "Capture and compare records",
                    "summary": "",
                    "source_block_ids": ["verification-steps"],
                },
            ],
        }

    story = await plan_slide_story_v3(
        graph,
        template,
        ai_planner=planner,
    )

    assert planner_invocations == 1
    assert story.pages[0].template_layout_id == content_layout_id
    assert story.pages[0].source_block_ids == ["observation"]
    assert story.pages[1].template_layout_id == practice_layout_id
    assert story.pages[1].source_block_ids == ["verification-steps"]


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


def _request_unit_source_text(unit: dict) -> str:
    return "\n\n".join(
        str(block.get("source_text") or "")
        for block in unit.get("primary_blocks") or []
    )


def test_long_source_heading_offers_semantic_fragments_within_template_capacity() -> None:
    source = "## Field protocol: Observe habitat signals and record the evidence"

    candidates = _grounded_title_candidates(source, max_chars=28)

    assert "Observe habitat signals" in candidates
    assert all(candidate in source and len(candidate) <= 28 for candidate in candidates)


def test_title_candidates_skip_formula_fragments_and_keep_later_complete_claims() -> None:
    source = (
        "设三阶增广矩阵的第 $i$ 行为 $R_i$。"
        "$R_i\\leftrightarrow R_j\\ (i\\ne j)$。"
        "每次运算都必须包含增广列；倍加时 $R_j$ 保持不变。"
        "行决定方程，列决定未知数，末列记录右端常数。"
    )

    candidates = _grounded_title_candidates(source, max_chars=22)

    assert "行决定方程，列决定未知数，末列记录右端常数" in candidates
    assert all("$" not in candidate and "ine j" not in candidate for candidate in candidates)


def test_story_unit_request_reuses_precomputed_template_partitions(
    monkeypatch,
) -> None:
    document = _document()
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    prepared_slices = [{"start_index": 0, "end_index": 1}]
    prepared_range = [1, 1]
    prepared_options = [{"partition_id": "prepared", "pages": []}]
    calls = {"slices": 0, "range": 0, "options": 0}

    def safe_slices(_unit, _template):
        calls["slices"] += 1
        return prepared_slices

    def page_count_range(_unit, _template, *, safe_slices=None):
        calls["range"] += 1
        assert safe_slices is prepared_slices
        return prepared_range

    def partition_options(
        _unit,
        _template,
        *,
        safe_slices=None,
        allowed_page_count_range=None,
    ):
        calls["options"] += 1
        assert safe_slices is prepared_slices
        assert allowed_page_count_range is prepared_range
        return prepared_options

    monkeypatch.setattr(planning_module, "story_safe_page_slices", safe_slices)
    monkeypatch.setattr(
        planning_module,
        "story_page_count_range",
        page_count_range,
    )
    monkeypatch.setattr(
        planning_module,
        "story_safe_partition_options",
        partition_options,
    )

    request = planning_module._story_unit_request(graph.units[0], template)

    assert calls == {"slices": 1, "range": 1, "options": 1}
    assert request["safe_page_slices"] is prepared_slices
    assert request["allowed_page_count_range"] is prepared_range
    assert request["safe_partition_options"] is prepared_options


@pytest.mark.asyncio
async def test_objective_page_may_use_the_frozen_section_title() -> None:
    document = refresh_document_revision(CourseDocument(
        course_id="classroom-opening",
        title="Newton's laws",
        sections=[CourseSection(
            section_id="lesson-1",
            title="从真实运动情境建立受力模型",
            position=0,
        )],
        blocks=[CourseBlock(
            block_id="lesson-objective",
            section_id="lesson-1",
            position=0,
            role="objective",
            payload={
                "markdown": "下课前能够识别研究对象，并说明受力分析的判断依据。"
            },
        )],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")

    async def planner(request):
        unit = request["teaching_units"][0]
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "provider": "fixture-provider",
            "model": "fixture-model",
            "attempts": 1,
            "pages": [{
                "page_id": "lesson-opening",
                "teaching_unit_id": unit["teaching_unit_id"],
                "template_layout_id": unit[
                    "allowed_template_layout_ids_by_page_intent"
                ]["orientation"][0],
                "title": unit["section_title"],
                "summary": "",
                "source_block_ids": unit["primary_block_ids"],
            }],
        }

    story = await plan_slide_story_v3(graph, template, ai_planner=planner)

    assert graph.units[0].section_title == "从真实运动情境建立受力模型"
    assert story.pages[0].title == graph.units[0].section_title


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
    supplied_layout_ids = calls[0]["teaching_units"][0]["allowed_template_layout_ids"]
    title_candidates = calls[0]["teaching_units"][0]["title_candidates"]
    assert title_candidates
    assert all(
        any(
            candidate in block["source_text"]
            for block in calls[0]["teaching_units"][0]["primary_blocks"]
        )
        for candidate in title_candidates
    )
    assert calls[0]["response_contract"]["required_page_fields"] == [
        "page_id",
        "teaching_unit_id",
        "template_layout_id",
        "title",
        "summary",
        "visible_copy",
        "page_goal",
        "primary_claim",
        "audience_question",
        "audience_action",
        "expected_response",
        "observable_evidence",
        "transition",
        "reveal_steps",
        "composition_notes",
        "question_bank_item_ids",
        "shared_visual_expression_ids",
        "source_block_ids",
    ]
    assert "narrative_brief" in calls[0]["response_contract"][
        "required_top_level_fields"
    ]
    assert calls[0]["response_contract"]["forbidden_page_fields"] == ["content"]
    assert calls[0]["constraints"]["primary_block_page_ownership"] == "exactly_once"
    assert calls[0]["constraints"]["allow_multiple_primary_blocks_per_page"] is True
    assert calls[0]["constraints"]["canvas_expression"] == (
        "semantic_closure_with_full_source_in_notes"
    )
    assert calls[0]["constraints"]["audience"] == "learners_during_live_teaching"
    assert calls[0]["constraints"]["speaker_notes_policy"] == (
        "complete_teacher_script_notes_only"
    )
    assert calls[0]["constraints"]["one_page_one_teaching_point"] is True
    assert calls[0]["constraints"]["summary_policy"] == (
        "source_grounded_semantic_closure_for_all_bound_blocks_"
        "complete_sentence_no_markdown"
    )
    assert calls[0]["teaching_units"][0]["summary_max_chars_by_layout_id"]
    assert supplied_layout_ids
    assert "allowed_template_layouts" not in calls[0]["teaching_units"][0]
    assert "safe_page_slices" not in calls[0]["teaching_units"][0]
    assert story.batches[0].provider == "rotating-fixture"
    assert story.batches[0].validation_status == "passed"
    validate_slide_story_plan_v3(story, graph, template)

    with pytest.raises(V6BuildError, match="story_ai_required"):
        await plan_slide_story_v3(graph, template, ai_planner=None)


@pytest.mark.asyncio
async def test_story_normalizes_single_text_items_without_rewriting_content() -> None:
    document = _document()
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    visible_copy = "一个可靠流程先界定输入，再执行动作，最后核对结果。"
    reveal_step = "核对完成条件和异常原因"

    async def planner(request):
        unit = request["teaching_units"][0]
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "provider": "fixture-provider",
            "model": "fixture-model",
            "attempts": 1,
            "pages": [{
                "page_id": "single-text-shape",
                "teaching_unit_id": unit["teaching_unit_id"],
                "template_layout_id": next(
                    item
                    for item in unit["allowed_template_layout_ids"]
                    if item.endswith("/practice-feedback")
                ),
                "title": _title_for_request_blocks(
                    unit,
                    unit["primary_block_ids"],
                ),
                "summary": "",
                "visible_copy": visible_copy,
                "reveal_steps": reveal_step,
                "source_block_ids": unit["primary_block_ids"],
            }],
        }

    story = await plan_slide_story_v3(graph, template, ai_planner=planner)

    assert story.pages[0].visible_copy == [visible_copy]
    assert story.pages[0].reveal_steps == [reveal_step]
    request = planning_module._story_requests(graph, template)[0]
    assert request["response_contract"]["page_field_types"]["visible_copy"] == (
        "array[string]"
    )


def test_story_model_request_removes_repeated_layout_and_source_contracts() -> None:
    document = _document(with_code=True)
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    full_request = planning_module._story_requests(graph, template)[0]

    model_request = planning_module._story_model_request(full_request)

    full_chars = len(json.dumps(full_request, ensure_ascii=False))
    model_chars = len(json.dumps(model_request, ensure_ascii=False))
    assert model_chars < full_chars * 0.6
    assert model_request["response_contract"] == full_request["response_contract"]
    assert model_request["teaching_units"][0]["primary_blocks"]
    assert model_request["teaching_units"][0]["safe_partition_options"]
    assert "allowed_template_layouts" not in model_request["teaching_units"][0]
    assert "source_text" not in model_request["teaching_units"][0]


def test_story_model_request_preflight_compacts_oversized_chapter_without_losing_blocks() -> None:
    document = _document(with_code=True)
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    full_request = planning_module._story_requests(graph, template)[0]
    unit = full_request["teaching_units"][0]
    original_block_ids = list(unit["primary_block_ids"])
    for block in unit["primary_blocks"]:
        block["presentation_text"] = (
            "这是用于课堂展示的完整来源句。" * 1200
        )
        block["reference_evidence_summaries"] = ["重复证据摘要" * 800]
    full_request["repair_feedback"] = {
        "attempt": 2,
        "code": "story_title_not_grounded",
        "message": "标题需要修复",
        "repair_targets": [],
        "instruction": "重复修复说明" * 5000,
    }
    assert len(json.dumps(full_request, ensure_ascii=False)) > 45000

    model_request = planning_module._story_model_request(full_request)
    model_unit = model_request["teaching_units"][0]

    assert len(json.dumps(model_request, ensure_ascii=False)) <= 20000
    assert model_unit["primary_block_ids"] == original_block_ids
    assert [
        block["block_id"] for block in model_unit["primary_blocks"]
    ] == original_block_ids
    assert all(
        "reference_evidence_summaries" not in block
        for block in model_unit["primary_blocks"]
    )
    assert len(model_unit["safe_partition_options"]) <= 2
    assert len(model_request["repair_feedback"]["instruction"]) < 320


def test_story_model_request_compacts_large_repair_diagnostics_to_provider_budget() -> None:
    document = _document(with_code=True)
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    full_request = planning_module._story_requests(graph, template)[0]
    unit = full_request["teaching_units"][0]
    full_request["repair_feedback"] = {
        "attempt": 2,
        "code": "story_title_incomplete",
        "message": "标题被截断",
        "repair_targets": [{
            "page_id": "page-1",
            "teaching_unit_id": unit["teaching_unit_id"],
            "required_title": unit["title_candidates"][0],
            "available_title_candidates": unit["title_candidates"],
            "primary_blocks": [
                {"source_text": "重复完整讲稿" * 8000}
            ],
            "safe_page_slices": [{"source_text": "重复切分页" * 6000}],
            "safe_partition_options": unit["safe_partition_options"] * 100,
            "allowed_protected_tokens": [f"token{index}" for index in range(8000)],
        }],
        "instruction": "重复修复说明" * 5000,
    }

    model_request = planning_module._story_model_request(full_request)
    repair_target = model_request["repair_feedback"]["repair_targets"][0]

    assert len(json.dumps(model_request, ensure_ascii=False)) <= 20000
    assert repair_target["required_title"] == unit["title_candidates"][0]
    assert "primary_blocks" not in repair_target
    assert "safe_page_slices" not in repair_target
    assert "safe_partition_options" not in repair_target
    assert "allowed_protected_tokens" not in repair_target


def test_story_model_request_keeps_balanced_partition_for_each_page_count() -> None:
    document = _document()
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    full_request = planning_module._story_requests(graph, template)[0]
    unit = full_request["teaching_units"][0]
    layout_id = unit["allowed_template_layout_ids"][0]

    def option(partition_id: str, groups: list[list[str]]) -> dict:
        return {
            "partition_id": partition_id,
            "page_count": len(groups),
            "pages": [
                {
                    "source_block_ids": group,
                    "template_layout_ids": [layout_id],
                }
                for group in groups
            ],
        }

    unit["safe_partition_options"] = [
        option("two-pages", [["b1"], ["b2", "b3", "b4", "b5", "b6", "b7"]]),
        option("three-unbalanced", [["b1"], ["b2", "b3", "b4", "b5", "b6"], ["b7"]]),
        option("three-balanced", [["b1"], ["b2", "b3", "b4"], ["b5", "b6", "b7"]]),
    ]

    model_request = planning_module._story_model_request(full_request)
    retained = model_request["teaching_units"][0]["safe_partition_options"]

    assert [item["partition_id"] for item in retained] == [
        "two-pages",
        "three-balanced",
    ]


def test_story_title_candidates_use_confirmed_script_block_titles() -> None:
    document = refresh_document_revision(CourseDocument(
        course_id="script-title-source",
        title="线性代数",
        sections=[CourseSection(
            section_id="determinant",
            title="行列式",
            position=0,
        )],
        blocks=[
            CourseBlock(
                block_id="det-definition",
                section_id="determinant",
                position=0,
                role="concept",
                payload={
                    "title": "二阶行列式的定义",
                    "markdown": "本页给出定义、条件与计算边界。",
                },
            ),
            CourseBlock(
                block_id="det-expansion",
                section_id="determinant",
                position=1,
                role="reasoning",
                payload={
                    "title": "按行展开的符号规律",
                    "markdown": "本页给出定义、条件与计算边界。",
                },
            ),
        ],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    request = planning_module._story_requests(graph, template)[0]
    primary_blocks = [
        block
        for unit in request["teaching_units"]
        for block in unit["primary_blocks"]
    ]

    assert [block["source_title"] for block in primary_blocks] == [
        "二阶行列式的定义",
        "按行展开的符号规律",
    ]
    assert [block["title_candidates"][0] for block in primary_blocks] == [
        "二阶行列式的定义",
        "按行展开的符号规律",
    ]


def test_story_model_request_uses_slide_projection_instead_of_teacher_transcript() -> None:
    teacher_source = (
        "同学们，请大家先看我演示。【板书】"
        "定义：牛顿第二定律是 $\\vec F=m\\vec a$。"
        "【等待回应】接下来我会继续讲解。"
    )
    document = refresh_document_revision(CourseDocument(
        course_id="teacher-projection",
        title="Teacher projection",
        sections=[CourseSection(section_id="chapter", title="Chapter", position=0)],
        blocks=[CourseBlock(
            block_id="teacher-block",
            section_id="chapter",
            position=0,
            role="concept",
            payload={
                "markdown": teacher_source,
                "module_id": "core_explanation",
                "module_instance_id": "teacher-block",
            },
        )],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")

    full_request = planning_module._story_requests(graph, template)[0]
    model_request = planning_module._story_model_request(full_request)
    model_block = model_request["teaching_units"][0]["primary_blocks"][0]

    assert model_block["source_text"] == graph.units[0].primary_block_presentation_texts[
        "teacher-block"
    ]
    assert "同学们" not in model_block["source_text"]
    assert "【板书】" not in model_block["source_text"]
    assert teacher_source == full_request["teaching_units"][0]["primary_blocks"][0][
        "source_text"
    ]


@pytest.mark.asyncio
async def test_story_request_preparation_keeps_event_loop_responsive(
    monkeypatch,
) -> None:
    """Large deterministic request preparation must not stall task/status APIs."""

    document = _document()
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    real_story_requests = planning_module._story_requests
    entered = threading.Event()
    release = threading.Event()
    exited = threading.Event()
    ticks = 0

    def slow_story_requests(*args, **kwargs):
        entered.set()
        release.wait(timeout=2)
        try:
            return real_story_requests(*args, **kwargs)
        finally:
            exited.set()

    monkeypatch.setattr(planning_module, "_story_requests", slow_story_requests)

    async def planner(request):
        unit = request["teaching_units"][0]
        layout = next(
            item
            for item in unit["allowed_template_layout_ids"]
            if item.endswith("/practice-feedback")
        )
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "pages": [{
                "page_id": "responsive-story-page",
                "teaching_unit_id": unit["teaching_unit_id"],
                "template_layout_id": layout,
                "title": _title_for_request_blocks(
                    unit,
                    unit["primary_block_ids"],
                ),
                "summary": "",
                "source_block_ids": unit["primary_block_ids"],
            }],
        }

    async def event_loop_probe() -> None:
        nonlocal ticks
        assert await asyncio.to_thread(entered.wait, 1)
        while not exited.is_set():
            ticks += 1
            await asyncio.sleep(0.01)

    timer = threading.Timer(0.25, release.set)
    timer.start()
    try:
        await asyncio.gather(
            plan_slide_story_v3(graph, template, ai_planner=planner),
            event_loop_probe(),
        )
    finally:
        release.set()
        timer.cancel()

    assert ticks >= 5


@pytest.mark.asyncio
async def test_visual_request_preparation_keeps_event_loop_responsive(
    monkeypatch,
) -> None:
    """Visual request validation and geometry must not block other API work."""

    document = _document()
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")

    async def story_planner(request):
        unit = request["teaching_units"][0]
        layout = next(
            item
            for item in unit["allowed_template_layout_ids"]
            if item.endswith("/practice-feedback")
        )
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "pages": [{
                "page_id": "responsive-visual-page",
                "teaching_unit_id": unit["teaching_unit_id"],
                "template_layout_id": layout,
                "title": _title_for_request_blocks(
                    unit,
                    unit["primary_block_ids"],
                ),
                "summary": "",
                "source_block_ids": unit["primary_block_ids"],
            }],
        }

    story = await plan_slide_story_v3(
        graph,
        template,
        ai_planner=story_planner,
    )
    real_visual_request = planning_module._visual_request
    entered = threading.Event()
    release = threading.Event()
    exited = threading.Event()
    ticks = 0

    def slow_visual_request(*args, **kwargs):
        entered.set()
        release.wait(timeout=2)
        try:
            return real_visual_request(*args, **kwargs)
        finally:
            exited.set()

    monkeypatch.setattr(planning_module, "_visual_request", slow_visual_request)

    async def visual_planner(request):
        return {
            "schema_version": "slide_visual_batch_response_v2",
            "decisions": [{
                "page_id": page["page_id"],
                "decision": page["allowed_decisions"][0],
                "source_block_ids": page["source_block_ids"],
                "resolved_template_layout_id": page["template_layout_id"],
            } for page in request["pages"]],
        }

    async def event_loop_probe() -> None:
        nonlocal ticks
        assert await asyncio.to_thread(entered.wait, 1)
        while not exited.is_set():
            ticks += 1
            await asyncio.sleep(0.01)

    timer = threading.Timer(0.25, release.set)
    timer.start()
    try:
        await asyncio.gather(
            plan_slide_visuals_v2(
                story,
                graph,
                template,
                ai_planner=visual_planner,
                concurrency=1,
            ),
            event_loop_probe(),
        )
    finally:
        release.set()
        timer.cancel()

    assert ticks >= 5


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
async def test_story_resume_replans_and_restores_missing_source_ownership() -> None:
    document = _document()
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    request = planning_module._story_requests(graph, template)[0]
    unit_request = request["teaching_units"][0]
    unit = graph.units[0]
    source_ids = unit.primary_block_ids[:1]
    saved_batch = SlideStoryBatchV3(
        batch_id="story-1",
        chapter_id="chapter-a",
        provider="saved-provider",
        model="saved-model",
        duration_ms=1,
        attempts=1,
        validation_status="passed",
        pages=[SlideStoryPageV3(
            page_id="saved-incomplete-owner",
            teaching_unit_id=unit.teaching_unit_id,
            template_layout_id=_layout_for_request_blocks(
                unit_request,
                source_ids,
            ),
            title=_title_for_request_blocks(unit_request, source_ids),
            summary="",
            source_block_ids=source_ids,
            page_ordinal=0,
        )],
    )
    calls = []

    async def planner(repair_request):
        calls.append(repair_request)
        requested_unit = repair_request["teaching_units"][0]
        repeated_ids = requested_unit["primary_block_ids"][:1]
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": repair_request["chapter_id"],
            "pages": [{
                "page_id": "replanned-incomplete-owner",
                "teaching_unit_id": requested_unit["teaching_unit_id"],
                "template_layout_id": _layout_for_request_blocks(
                    requested_unit,
                    repeated_ids,
                ),
                "title": _title_for_request_blocks(
                    requested_unit,
                    repeated_ids,
                ),
                "summary": "",
                "source_block_ids": repeated_ids,
            }],
        }

    resumed = await plan_slide_story_v3(
        graph,
        template,
        ai_planner=planner,
        resume_batches=[saved_batch],
    )

    assert len(calls) == 1
    assert [
        block_id
        for page in resumed.pages
        for block_id in page.source_block_ids
    ] == ["concept", "feedback"]
    validate_slide_story_plan_v3(resumed, graph, template)


def _activity_code_overflow_replay() -> tuple[dict, CourseDocument, str]:
    fixture = json.loads(
        (_FIXTURE_DIR / "activity_rich_text_code_overflow.json").read_text(
            encoding="utf-8"
        )
    )
    steps = "\n".join(
        f"{index}. {item}"
        for index, item in enumerate(fixture["steps"], start=1)
    )
    code = "\n".join(fixture["code_lines"])
    markdown = (
        f"## {fixture['page_title']}\n\n"
        f"{steps}\n\n"
        f"```csharp\n{code}\n```"
    )
    document = refresh_document_revision(CourseDocument(
        course_id=fixture["course_id"],
        title=fixture["course_title"],
        sections=[CourseSection(
            section_id=fixture["section_id"],
            title=fixture["section_title"],
            position=0,
        )],
        blocks=[CourseBlock(
            block_id=fixture["block_id"],
            section_id=fixture["section_id"],
            position=0,
            role=fixture["block_role"],
            kind=fixture["block_kind"],
            payload={"markdown": markdown},
        )],
    ))
    return fixture, document, markdown


@pytest.mark.asyncio
async def test_real_shape_activity_code_replay_is_lossless_through_resume_and_quality() -> None:
    """Replay the production-shaped multi-slot page without course-specific data."""

    fixture, document, markdown = _activity_code_overflow_replay()
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")

    async def story_planner(request):
        unit = request["teaching_units"][0]
        response = fixture["story_response"]
        return {
            "schema_version": response["schema_version"],
            "chapter_id": request["chapter_id"],
            "pages": [{
                "page_id": response["page_id"],
                "teaching_unit_id": unit["teaching_unit_id"],
                "template_layout_id": template.layout_id(response["layout_slug"]),
                "title": fixture["page_title"],
                "summary": response["summary"],
                "source_block_ids": unit["primary_block_ids"],
            }],
        }

    first_story = await plan_slide_story_v3(
        graph,
        template,
        ai_planner=story_planner,
    )
    second_story = await plan_slide_story_v3(
        graph,
        template,
        ai_planner=story_planner,
    )
    assert [page.page_id for page in first_story.pages] == [
        page.page_id for page in second_story.pages
    ]

    async def planner_must_not_run(_request):
        raise AssertionError("compatible replay checkpoints must be reused")

    resumed_story = await plan_slide_story_v3(
        graph,
        template,
        ai_planner=planner_must_not_run,
        resume_batches=first_story.batches,
    )

    async def visual_planner(request):
        response = fixture["visual_response"]
        return {
            "schema_version": response["schema_version"],
            "decisions": [{
                "page_id": page["page_id"],
                "decision": response["decision"],
                "source_block_ids": page["source_block_ids"],
                "resolved_template_layout_id": page["template_layout_id"],
            } for page in request["pages"]],
        }

    first_visual = await plan_slide_visuals_v2(
        resumed_story,
        graph,
        template,
        ai_planner=visual_planner,
    )
    resumed_visual = await plan_slide_visuals_v2(
        resumed_story,
        graph,
        template,
        ai_planner=planner_must_not_run,
        resume_decisions=first_visual.decisions,
    )
    deck = compile_slide_deck_v6(
        document,
        graph,
        resumed_story,
        resumed_visual,
        template,
    )

    rendered_code = "\n".join(
        region.content
        for page in deck.pages
        for region in page.regions
        if region.content_kind == "code"
    ).splitlines()
    rendered_steps = [
        line
        for page in deck.pages
        for region in page.regions
        if region.content_kind == "steps"
        for line in region.content.splitlines()
    ]
    page_ids = [page.page_id for page in deck.pages]

    assert len(deck.pages) > 1
    assert len(page_ids) == len(set(page_ids))
    assert rendered_code == fixture["code_lines"]
    assert rendered_steps == fixture["steps"]
    assert [page.visual_decision.page_id for page in deck.pages] == page_ids
    assert all(
        page.visual_decision.source_block_ids == page.source_block_ids
        for page in deck.pages
    )
    assert all(
        any(
            note.block_id == fixture["block_id"]
            and note.full_text == markdown
            and note.source_payload == {"markdown": markdown}
            for note in page.speaker_notes.source_blocks
        )
        for page in deck.pages
    )
    assert deck.quality.passed is True
    assert deck.quality.source_artifact_visible_fidelity == 1.0
    assert deck.quality.ordered_step_visible_fidelity == 1.0


def _single_misconception_overflow_replay() -> tuple[dict, CourseDocument, str]:
    fixture = json.loads(
        (_FIXTURE_DIR / "single_misconception_prose_overflow.json").read_text(
            encoding="utf-8"
        )
    )
    markdown = (
        f"## {fixture['page_title']}\n\n"
        + "\n\n".join(fixture["paragraphs"])
    )
    document = refresh_document_revision(CourseDocument(
        course_id=fixture["course_id"],
        title=fixture["course_title"],
        sections=[CourseSection(
            section_id=fixture["section_id"],
            title=fixture["section_title"],
            position=0,
        )],
        blocks=[CourseBlock(
            block_id=fixture["block_id"],
            section_id=fixture["section_id"],
            position=0,
            role=fixture["block_role"],
            kind=fixture["block_kind"],
            payload={"markdown": markdown},
        )],
    ))
    return fixture, document, markdown


@pytest.mark.asyncio
async def test_real_shape_single_misconception_replay_uses_lossless_prose_continuations() -> None:
    """One prose block cannot impersonate three distinct required semantic slots."""

    fixture, document, markdown = _single_misconception_overflow_replay()
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")

    async def story_planner(request):
        unit = request["teaching_units"][0]
        response = fixture["story_response"]
        return {
            "schema_version": response["schema_version"],
            "chapter_id": request["chapter_id"],
            "pages": [{
                "page_id": response["page_id"],
                "teaching_unit_id": unit["teaching_unit_id"],
                "template_layout_id": template.layout_id(response["layout_slug"]),
                "title": fixture["page_title"],
                "summary": response["summary"],
                "source_block_ids": unit["primary_block_ids"],
            }],
        }

    story = await plan_slide_story_v3(
        graph,
        template,
        ai_planner=story_planner,
    )
    assert story.pages[0].template_layout_id.endswith("/content-stack")

    async def visual_planner(request):
        response = fixture["visual_response"]
        return {
            "schema_version": response["schema_version"],
            "decisions": [{
                "page_id": page["page_id"],
                "decision": response["decision"],
                "source_block_ids": page["source_block_ids"],
                "resolved_template_layout_id": page["template_layout_id"],
            } for page in request["pages"]],
        }

    visual = await plan_slide_visuals_v2(
        story,
        graph,
        template,
        ai_planner=visual_planner,
    )
    deck = compile_slide_deck_v6(
        document,
        graph,
        story,
        visual,
        template,
    )

    rendered_body = "\n\n".join(
        region.content
        for page in deck.pages
        for region in page.regions
        if region.content_kind == "body"
    )
    expected_body = "\n\n".join([
        fixture["page_title"],
        *fixture["paragraphs"],
    ])
    page_ids = [page.page_id for page in deck.pages]

    assert len(deck.pages) == 2
    assert len(page_ids) == len(set(page_ids))
    assert rendered_body == expected_body
    assert [page.visual_decision.page_id for page in deck.pages] == page_ids
    assert all(
        page.resolved_layout.endswith("/content-stack")
        for page in deck.pages
    )
    assert all(
        any(
            note.block_id == fixture["block_id"]
            and note.full_text == markdown
            and note.source_payload == {"markdown": markdown}
            for note in page.speaker_notes.source_blocks
        )
        for page in deck.pages
    )
    assert deck.quality.passed is True
    assert deck.quality.source_prose_visible_fidelity == 1.0


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
            "title": _request_unit_source_text(unit)[:24],
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
                    "content": {"title": _request_unit_source_text(unit)[:24]},
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
async def test_story_primary_rate_limit_is_not_masked_by_fallback_authentication() -> None:
    document = _document()
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")

    async def planner(_request):
        raise AIPlannerInvocationError(
            AIProviderUnavailable("authentication_failed"),
            telemetry=[
                {
                    "provider_route": "shared-ai-pool",
                    "model_id": "generic-primary-model",
                    "provider_attempt": 1,
                    "status": "failed",
                    "error_code": "RateLimitError",
                },
                {
                    "provider_route": "modelscope_fallback",
                    "model_id": "generic-fallback-model",
                    "provider_attempt": 1,
                    "status": "failed",
                    "error_code": "AuthenticationError",
                },
            ],
        )

    with pytest.raises(V6BuildError) as captured:
        await plan_slide_story_v3(graph, template, ai_planner=planner)

    assert captured.value.failure.code == "story_ai_batch_rate_limited"
    assert captured.value.failure.retryable is True
    assert "last published deck was preserved" in captured.value.failure.message


@pytest.mark.asyncio
async def test_story_primary_balance_is_not_masked_by_fallback_authentication() -> None:
    document = _document()
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")

    async def planner(_request):
        raise AIPlannerInvocationError(
            AIProviderUnavailable("authentication_failed"),
            telemetry=[
                {
                    "provider_route": "shared-ai-pool",
                    "model_id": "generic-primary-model",
                    "provider_attempt": 1,
                    "status": "failed",
                    "error_code": "RateLimitError",
                    "failure_kind": "quota_exhausted",
                },
                {
                    "provider_route": "modelscope_fallback",
                    "model_id": "generic-fallback-model",
                    "provider_attempt": 1,
                    "status": "failed",
                    "error_code": "AuthenticationError",
                    "failure_kind": "transient",
                },
            ],
        )

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
            "physical_request_count": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "tokens_source": "unknown",
            "failure_kind": "",
            "error_code": "RateLimitError",
        },
        {
            "provider": "modelscope_fallback",
            "model": "generic-fallback-model",
            "attempt": 1,
            "status": "failed",
            "duration_ms": 240,
            "queue_wait_ms": 8,
            "physical_request_count": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "tokens_source": "unknown",
            "failure_kind": "",
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
        "physical_request_count": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "tokens_source": "unknown",
        "failure_kind": "",
        "error_code": "QuotaError",
    }]
    assert "api_key" not in str(captured.value.telemetry)


@pytest.mark.asyncio
async def test_shared_ai_visual_planner_compiles_degraded_source_bound_decisions_on_balance_failure(
    monkeypatch,
) -> None:
    class FailedSharedAI:
        def __init__(self, *, provider_profile=None):
            assert provider_profile == "ppt"

        async def _call_llm(self, *_args, telemetry_sink, **_kwargs):
            telemetry_sink({
                "provider_route": "rotating-pool",
                "model_id": "generic-provider-model",
                "provider_attempt": 1,
                "status": "failed",
                "error_code": "BalanceError",
                "failure_kind": "quota_exhausted",
            })
            raise RuntimeError("insufficient balance")

    monkeypatch.setattr(planning_module, "AIBase", FailedSharedAI)
    planner = build_ai_base_visual_planner_v2()
    response = await planner({
        "schema_version": "slide_visual_batch_request_v2",
        "chapter_id": "chapter-a",
        "pages": [
            {
                "page_id": "page-text",
                "template_layout_id": "layout-text",
                "source_block_ids": ["block-text"],
                "allowed_decisions": ["diagram", "text_native"],
                "source_asset_ids": [],
            },
            {
                "page_id": "page-formula",
                "template_layout_id": "layout-formula",
                "source_block_ids": ["block-formula"],
                "allowed_decisions": ["formula"],
                "source_asset_ids": [],
            },
        ],
    })

    assert response["provider"] == "codex-structured-fallback"
    assert response["model"] == "deterministic-source-bound-visual"
    assert [item["decision"] for item in response["decisions"]] == [
        "text_native",
        "formula",
    ]
    assert all(item["degraded"] for item in response["decisions"])
    assert all(
        item["degradation_reason"] == "visual_ai_batch_balance_unavailable"
        for item in response["decisions"]
    )
    assert response.telemetry[0]["failure_kind"] == "quota_exhausted"


@pytest.mark.asyncio
async def test_shared_ai_visual_planner_uses_smart_pool_when_fast_models_unavailable(
    monkeypatch,
) -> None:
    calls: list[bool] = []

    class RecoveringSharedAI:
        def __init__(self, *, provider_profile=None):
            assert provider_profile == "ppt"

        async def _call_llm(
            self,
            *_args,
            use_fast_model,
            telemetry_sink,
            **_kwargs,
        ):
            calls.append(use_fast_model)
            if use_fast_model:
                raise AIProviderRequestError(
                    "Model id : retired-fast-model , has no provider supported"
                )
            telemetry_sink({
                "provider_route": "smart-pool",
                "model_id": "smart-visual-model",
                "provider_attempt": 1,
                "status": "completed",
            })
            return json.dumps({
                "schema_version": "slide_visual_batch_response_v2",
                "decisions": [{
                    "page_id": "page-formula",
                    "decision": "formula",
                    "source_block_ids": ["block-formula"],
                    "resolved_template_layout_id": "layout-formula",
                }],
            })

        @staticmethod
        def _extract_json(value):
            return json.loads(value)

    monkeypatch.setattr(planning_module, "AIBase", RecoveringSharedAI)
    planner = build_ai_base_visual_planner_v2()

    response = await planner({
        "schema_version": "slide_visual_batch_request_v2",
        "chapter_id": "chapter-a",
        "pages": [{
            "page_id": "page-formula",
            "template_layout_id": "layout-formula",
            "source_block_ids": ["block-formula"],
            "allowed_decisions": ["formula"],
            "source_asset_ids": [],
        }],
    })

    assert calls == [True, False]
    assert response["model"] == "smart-visual-model"
    assert response["decisions"][0]["decision"] == "formula"


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
                "title": _request_unit_source_text(unit)[:24],
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
    oversized_unbreakable_token = "BuildArtifactIdentity_" + "x" * 64
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
                    f"{oversized_unbreakable_token}; "
                    "Validate the frozen build artifact before observation."
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
            title = oversized_unbreakable_token
        else:
            repair_target = request["repair_feedback"]["repair_targets"][0]
            title = repair_target["available_title_candidates"][0]
        selected_layout = unit["allowed_template_layout_ids"][0]
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


def test_story_title_repair_never_requires_internal_module_label() -> None:
    document = refresh_document_revision(CourseDocument(
        course_id="matrix-title-repair",
        title="线性代数",
        sections=[CourseSection(
            section_id="matrix",
            title="增广矩阵与解的类型",
            position=0,
        )],
        blocks=[CourseBlock(
            block_id="matrix-task",
            section_id="matrix",
            position=0,
            kind="rich_text",
            role="activity",
            payload={
                "title": "学习者行动",
                "markdown": (
                    "任务条件：根据增广矩阵圈出主元并判断线性方程组解的类型。"
                    "参考解法：先检查矛盾行，再比较主元数与未知数个数。"
                ),
            },
        )],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    request = planning_module._story_requests(graph, template)[0]
    unit = request["teaching_units"][0]
    payload = {
        "schema_version": "slide_story_batch_response_v3",
        "chapter_id": request["chapter_id"],
        "pages": [{
            "page_id": "generic-module-title",
            "teaching_unit_id": unit["teaching_unit_id"],
            "template_layout_id": unit["allowed_template_layout_ids"][0],
            "title": "学习者行动",
            "summary": "",
            "source_block_ids": unit["primary_block_ids"],
        }],
    }
    error = V6BuildError(
        stage="story",
        code="story_title_lacks_specificity",
        message="module label is not a teaching subject",
        page_id="generic-module-title",
    )

    targets = planning_module._story_repair_targets(request, payload, error)

    assert targets[0]["required_title"] != "学习者行动"
    assert "学习者行动" not in targets[0]["available_title_candidates"]
    assert "增广矩阵" in targets[0]["required_title"]


@pytest.mark.asyncio
async def test_story_normalization_projects_generic_module_title_to_source_subject() -> None:
    document = refresh_document_revision(CourseDocument(
        course_id="matrix-title-projection",
        title="线性代数",
        sections=[CourseSection(
            section_id="matrix",
            title="增广矩阵与解的类型",
            position=0,
        )],
        blocks=[CourseBlock(
            block_id="matrix-feedback",
            section_id="matrix",
            position=0,
            kind="rich_text",
            role="feedback",
            payload={
                "title": "检查与反馈",
                "markdown": (
                    "核对标准：检查缺失变量是否以零占位。"
                    "典型错误：省略零系数会破坏增广矩阵的列对应关系。"
                    "修正原因：每一列必须对应固定变量。"
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
        partition_page = unit["safe_partition_options"][0]["pages"][0]
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "pages": [{
                "page_id": "generic-feedback-title",
                "teaching_unit_id": unit["teaching_unit_id"],
                "template_layout_id": partition_page["template_layout_ids"][0],
                "title": "检查与反馈",
                "summary": "",
                "source_block_ids": partition_page["source_block_ids"],
            }],
        }

    story = await plan_slide_story_v3(graph, template, ai_planner=planner)

    assert len(calls) == 1
    assert story.pages[0].title != "检查与反馈"
    assert any(term in story.pages[0].title for term in ("缺失变量", "零占位", "零系数"))


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
    selected_layout = template.get_layout(story.pages[0].template_layout_id)
    assert selected_layout is not None
    body_slot = next(
        slot for slot in selected_layout.slots if slot.slot_kind == "body"
    )
    assert len(story.pages[0].summary) <= body_slot.max_chars
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
    assert repaired_summary == ""
    assert len(repaired_summary) <= maximum


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
    assert repaired_summary == ""


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
        page["summary"] == "" and len(page["summary"]) <= maximum
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
    """A long sentence must fall back to source pagination, not a clipped summary."""

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
    assert story.pages[0].summary == ""


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
async def test_story_clears_generated_ellipsis_companion_without_hiding_source() -> None:
    source = (
        "发布前必须核对 build_pipeline_checkpoint_identifier_2026、构建日志和回归结果。"
        "When the identifier is complete, verify the saved checkpoint before publishing."
    )
    document = refresh_document_revision(CourseDocument(
        course_id="generic-generated-ellipsis-companion",
        title="发布核对",
        sections=[CourseSection(section_id="release", title="发布", position=0)],
        blocks=[CourseBlock(
            block_id="release-check",
            section_id="release",
            position=0,
            role="concept",
            payload={"markdown": source},
        )],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")

    async def planner(request):
        unit = request["teaching_units"][0]
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "pages": [{
                "page_id": "release-check-page",
                "teaching_unit_id": unit["teaching_unit_id"],
                "template_layout_id": next(
                    layout_id
                    for layout_id in unit["allowed_template_layout_ids"]
                    if layout_id.endswith("/content-stack")
                ),
                "title": "发布前核对",
                "summary": "发布前必须核对 build_pipeline_checkpoint_identifier_2026…",
                "source_block_ids": unit["primary_block_ids"],
            }],
        }

    first = await plan_slide_story_v3(graph, template, ai_planner=planner)
    second = await plan_slide_story_v3(graph, template, ai_planner=planner)

    assert first.pages[0].summary == source
    assert [
        page.model_dump(mode="json") for page in second.pages
    ] == [
        page.model_dump(mode="json") for page in first.pages
    ]

    visual = SlideVisualPlanV2(
        source_document_revision=graph.source_document_revision,
        template_digest=template.template_digest,
        decisions=[SlideVisualDecisionV2(
            page_id=first.pages[0].page_id,
            decision="text_native",
            source_block_ids=list(first.pages[0].source_block_ids),
            resolved_template_layout_id=first.pages[0].template_layout_id,
        )],
    )
    deck = compile_slide_deck_v6(document, graph, first, visual, template)
    visible = "\n".join(
        region.content
        for page in deck.pages
        for region in page.regions
        if "release-check" in region.source_block_ids
    )

    assert source in visible
    assert "build_pipeline_checkpoint_identifier_2026" in visible
    assert deck.quality.source_prose_visible_fidelity == 1.0
    assert deck.quality.generated_ellipsis_free is True


@pytest.mark.asyncio
async def test_story_preserves_an_ellipsis_that_exists_in_frozen_source() -> None:
    source = "等待……再继续，是该实验记录中明确写出的观察状态。"
    document = refresh_document_revision(CourseDocument(
        course_id="generic-source-ellipsis",
        title="观察记录",
        sections=[CourseSection(section_id="observation", title="观察", position=0)],
        blocks=[CourseBlock(
            block_id="observation-state",
            section_id="observation",
            position=0,
            role="concept",
            payload={"markdown": source},
        )],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")

    async def planner(request):
        unit = request["teaching_units"][0]
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "pages": [{
                "page_id": "observation-state-page",
                "teaching_unit_id": unit["teaching_unit_id"],
                "template_layout_id": next(
                    layout_id
                    for layout_id in unit["allowed_template_layout_ids"]
                    if layout_id.endswith("/content-stack")
                ),
                "title": "等待后继续",
                "summary": source,
                "source_block_ids": unit["primary_block_ids"],
            }],
        }

    story = await plan_slide_story_v3(graph, template, ai_planner=planner)

    assert story.pages[0].summary == source


@pytest.mark.asyncio
async def test_story_does_not_accept_a_new_ellipsis_by_matching_source_count() -> None:
    source = "观察记录写明等待……再继续。随后必须核对完整日志并保存结果。"
    document = refresh_document_revision(CourseDocument(
        course_id="generic-moved-ellipsis",
        title="观察记录",
        sections=[CourseSection(section_id="observation", title="观察", position=0)],
        blocks=[CourseBlock(
            block_id="observation-state",
            section_id="observation",
            position=0,
            role="concept",
            payload={"markdown": source},
        )],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")

    async def planner(request):
        unit = request["teaching_units"][0]
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "pages": [{
                "page_id": "observation-state-page",
                "teaching_unit_id": unit["teaching_unit_id"],
                "template_layout_id": next(
                    layout_id
                    for layout_id in unit["allowed_template_layout_ids"]
                    if layout_id.endswith("/content-stack")
                ),
                "title": "观察后核对",
                "summary": "观察记录写明等待后继续，随后必须核对……",
                "source_block_ids": unit["primary_block_ids"],
            }],
        }

    story = await plan_slide_story_v3(graph, template, ai_planner=planner)

    assert story.pages[0].summary == source
    assert not story.pages[0].summary.endswith("……")


@pytest.mark.asyncio
async def test_story_clears_generated_ellipsis_when_complete_source_needs_pagination() -> None:
    sentences = [
        (
            f"阶段 {index} 必须完整核对 "
            f"checkpoint_identifier_with_a_long_suffix_{index:02d} 与对应英文记录 "
            "before the next publishing action is allowed."
        )
        for index in range(1, 13)
    ]
    source = "".join(sentences)
    document = refresh_document_revision(CourseDocument(
        course_id="generic-long-generated-ellipsis-companion",
        title="长文发布核对",
        sections=[CourseSection(section_id="release", title="核对", position=0)],
        blocks=[CourseBlock(
            block_id="long-release-check",
            section_id="release",
            position=0,
            role="concept",
            payload={"markdown": source},
        )],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")

    async def planner(request):
        unit = request["teaching_units"][0]
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "pages": [{
                "page_id": "long-release-check-page",
                "teaching_unit_id": unit["teaching_unit_id"],
                "template_layout_id": next(
                    layout_id
                    for layout_id in unit["allowed_template_layout_ids"]
                    if layout_id.endswith("/content-stack")
                ),
                "title": "长文发布核对",
                "summary": "阶段 1 必须完整核对 checkpoint_identifier_with_a_long_suffix_01…",
                "source_block_ids": unit["primary_block_ids"],
            }],
        }

    first = await plan_slide_story_v3(graph, template, ai_planner=planner)
    second = await plan_slide_story_v3(graph, template, ai_planner=planner)

    assert first.pages[0].summary == ""
    assert [
        page.model_dump(mode="json") for page in second.pages
    ] == [
        page.model_dump(mode="json") for page in first.pages
    ]

    visual = SlideVisualPlanV2(
        source_document_revision=graph.source_document_revision,
        template_digest=template.template_digest,
        decisions=[SlideVisualDecisionV2(
            page_id=first.pages[0].page_id,
            decision="text_native",
            source_block_ids=list(first.pages[0].source_block_ids),
            resolved_template_layout_id=first.pages[0].template_layout_id,
        )],
    )
    first_deck = compile_slide_deck_v6(document, graph, first, visual, template)
    second_deck = compile_slide_deck_v6(document, graph, second, visual, template)
    visible = "\n".join(
        region.content
        for page in first_deck.pages
        for region in page.regions
        if region.content_kind in {"body", "items", "steps"}
        and "long-release-check" in region.source_block_ids
    )

    assert len(first_deck.pages) > 1
    assert "".join(source.split()) in "".join(visible.split())
    assert "checkpoint_identifier_with_a_long_suffix_12" in visible
    assert first_deck.quality.source_prose_visible_fidelity == 1.0
    assert first_deck.quality.generated_ellipsis_free is True
    assert second_deck.model_dump(mode="json") == first_deck.model_dump(mode="json")


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
async def test_story_projects_an_overdense_valid_partition_to_classroom_density() -> None:
    document = refresh_document_revision(CourseDocument(
        course_id="dense-story-course",
        title="可靠流程",
        sections=[CourseSection(
            section_id="dense-section",
            title="从输入到校验",
            position=0,
        )],
        blocks=[
            CourseBlock(
                block_id=f"dense-block-{index}",
                section_id="dense-section",
                position=index,
                role="concept",
                payload={"markdown": f"流程要点{index + 1}必须在执行后保留可检查结果。"},
            )
            for index in range(7)
        ],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")

    async def planner(request):
        unit = request["teaching_units"][0]
        source_ids = list(unit["primary_block_ids"])
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "provider": "density-fixture",
            "model": "generic-model",
            "attempts": 1,
            "pages": [{
                "page_id": "overdense-but-template-safe",
                "teaching_unit_id": unit["teaching_unit_id"],
                "template_layout_id": _layout_for_request_blocks(unit, source_ids),
                "title": _title_for_request_blocks(unit, source_ids),
                "summary": "",
                "source_block_ids": source_ids,
            }],
        }

    story = await plan_slide_story_v3(graph, template, ai_planner=planner)

    assert [
        block_id
        for page in story.pages
        for block_id in page.source_block_ids
    ] == [f"dense-block-{index}" for index in range(7)]
    assert max(len(page.source_block_ids) for page in story.pages) <= 3
    assert len(story.pages) >= 3


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
async def test_story_repartitions_a_lossy_process_outline_to_lossless_body() -> None:
    """Structured prose must repair to a layout that preserves every source token."""

    source = (
        "本节先说明验收背景，再按顺序完成配置与核对。\n\n"
        "1. 准备运行环境\n"
        "- 保留项目现有输入配置。\n"
        "  - 记录初始状态和负责人。\n\n"
        "2. 执行验收检查\n"
        "- 对照结果、异常日志与完成条件。\n"
        "  - 任一条件不满足时停止发布并记录原因。"
    )
    document = refresh_document_revision(CourseDocument(
        course_id="generic-structured-reasoning",
        title="发布验收",
        sections=[CourseSection(
            section_id="release-check",
            title="验收流程",
            position=0,
        )],
        blocks=[CourseBlock(
            block_id="release-reasoning",
            section_id="release-check",
            position=0,
            kind="rich_text",
            role="reasoning",
            payload={"markdown": source},
        )],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    calls = []

    async def planner(request):
        calls.append(request)
        unit = request["teaching_units"][0]
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "pages": [{
                "page_id": f"lossy-process-{len(calls)}",
                "teaching_unit_id": unit["teaching_unit_id"],
                "template_layout_id": template.layout_id("process-flow"),
                "title": unit["title_candidates"][0],
                "summary": "",
                "source_block_ids": unit["primary_block_ids"],
            }],
        }

    story = await plan_slide_story_v3(graph, template, ai_planner=planner)

    # The provider chose process-flow, but deterministic normalization at the
    # AI boundary projects it to the first source-complete safe layout without
    # spending another provider call.
    assert len(calls) == 1
    assert story.pages[0].source_block_ids == ["release-reasoning"]
    assert story.pages[0].template_layout_id.endswith("/content-stack")

    visual = SlideVisualPlanV2(
        source_document_revision=graph.source_document_revision,
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
        if "release-reasoning" in region.source_block_ids
    )

    assert deck.quality.passed is True
    assert deck.quality.source_prose_visible_fidelity == 1.0
    assert visible.index("验收背景") < visible.index("准备运行环境")
    assert visible.index("准备运行环境") < visible.index("执行验收检查")
    assert "任一条件不满足时停止发布并记录原因" in visible


def test_semantic_fidelity_failure_requires_a_safe_unit_repartition() -> None:
    """A late semantic-fidelity failure must enter the bounded repair path."""

    document = refresh_document_revision(CourseDocument(
        course_id="generic-late-semantic-repair",
        title="发布验收",
        sections=[CourseSection(
            section_id="release-check",
            title="验收流程",
            position=0,
        )],
        blocks=[CourseBlock(
            block_id="release-reasoning",
            section_id="release-check",
            position=0,
            kind="rich_text",
            role="reasoning",
            payload={
                "markdown": (
                    "先说明验收背景。\n\n"
                    "1. 准备环境\n- 保留输入配置。\n\n"
                    "2. 核对结果\n- 检查异常日志和完成条件。"
                )
            },
        )],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    request = planning_module._story_requests(graph, template)[0]
    unit = request["teaching_units"][0]
    payload = {
        "schema_version": "slide_story_batch_response_v3",
        "chapter_id": request["chapter_id"],
        "pages": [{
            "page_id": "late-lossy-process",
            "teaching_unit_id": unit["teaching_unit_id"],
            "template_layout_id": template.layout_id("process-flow"),
            "title": unit["title_candidates"][0],
            "summary": "",
            "source_block_ids": unit["primary_block_ids"],
        }],
    }
    error = V6BuildError(
        stage="template",
        code="template_source_semantic_fidelity_incomplete",
        message="Template text regions omit frozen source prose",
        page_id="late-lossy-process",
    )

    targets = planning_module._story_repair_targets(request, payload, error)

    assert len(targets) == 1
    target = targets[0]
    assert target["repartition_required"] is True
    assert target["repartition_scope"] == "teaching_unit"
    assert target["source_projection_safe"] is True
    assert target["force_required_partition"] is True
    assert target["clear_provider_summary"] is True
    assert target["required_safe_partition"]["pages"]
    assert all(
        any(
            layout_id.endswith("/content-stack")
            for layout_id in page["template_layout_ids"]
        )
        for page in target["required_safe_partition"]["pages"]
    )


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

    assert len(calls) == 1
    assert [page.source_block_ids for page in story.pages] == [[
        "transfer-procedure",
        "transfer-errors",
    ]]
    assert story.pages[0].template_layout_id.endswith("/practice-table")


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
async def test_story_boundary_restores_missing_blocks_without_weakening_coverage() -> None:
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

    assert len(calls) == 1
    assert [
        block_id
        for page in story.pages
        for block_id in page.source_block_ids
    ] == ["concept", "feedback"]
    validate_slide_story_plan_v3(story, graph, template)


@pytest.mark.asyncio
async def test_story_boundary_restores_a_block_omitted_on_every_ai_attempt() -> None:
    document = _document()
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    calls = []

    async def planner(request):
        calls.append(request)
        unit = request["teaching_units"][0]
        source_ids = unit["primary_block_ids"][:1]
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "pages": [{
                "page_id": f"repeated-omission-{len(calls)}",
                "teaching_unit_id": unit["teaching_unit_id"],
                "template_layout_id": _layout_for_request_blocks(unit, source_ids),
                "title": _title_for_request_blocks(unit, source_ids),
                "summary": "",
                "source_block_ids": source_ids,
            }],
        }

    story = await plan_slide_story_v3(graph, template, ai_planner=planner)

    assert len(calls) == 1
    assert [
        block_id
        for page in story.pages
        for block_id in page.source_block_ids
    ] == ["concept", "feedback"]
    validate_slide_story_plan_v3(story, graph, template)


@pytest.mark.asyncio
async def test_story_boundary_removes_repeated_primary_ownership_deterministically() -> None:
    document = _document()
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")

    async def run_once():
        calls = []

        async def planner(request):
            calls.append(request)
            unit = request["teaching_units"][0]
            concept_id, feedback_id = unit["primary_block_ids"]
            return {
                "schema_version": "slide_story_batch_response_v3",
                "chapter_id": request["chapter_id"],
                "pages": [
                    {
                        "page_id": "duplicate-owner-a",
                        "teaching_unit_id": unit["teaching_unit_id"],
                        "template_layout_id": _layout_for_request_blocks(
                            unit,
                            [concept_id, feedback_id],
                        ),
                        "title": _title_for_request_blocks(
                            unit,
                            [concept_id, feedback_id],
                        ),
                        "summary": "",
                        "source_block_ids": [concept_id, feedback_id],
                    },
                    {
                        "page_id": "duplicate-owner-b",
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

        story = await plan_slide_story_v3(
            graph,
            template,
            ai_planner=planner,
        )
        return calls, story

    first_calls, first = await run_once()
    second_calls, second = await run_once()

    assert len(first_calls) == len(second_calls) == 1
    assert [
        (page.page_id, page.template_layout_id, page.source_block_ids)
        for page in first.pages
    ] == [
        (page.page_id, page.template_layout_id, page.source_block_ids)
        for page in second.pages
    ]
    assert [
        block_id
        for page in first.pages
        for block_id in page.source_block_ids
    ] == ["concept", "feedback"]
    validate_slide_story_plan_v3(first, graph, template)


@pytest.mark.asyncio
async def test_story_boundary_restores_an_entire_omitted_teaching_unit() -> None:
    document = _document()
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    calls = []

    async def planner(request):
        calls.append(request)
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "pages": [],
        }

    story = await plan_slide_story_v3(graph, template, ai_planner=planner)

    assert len(calls) == 1
    assert [
        block_id
        for page in story.pages
        for block_id in page.source_block_ids
    ] == ["concept", "feedback"]
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
async def test_story_boundary_normalizes_duplicate_block_page_owners() -> None:
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

    assert len(calls) == 1
    assert [
        block_id
        for page in story.pages
        for block_id in page.source_block_ids
    ] == ["concept", "feedback"]
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
                "title": _request_unit_source_text(unit)[:24],
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
async def test_story_repairs_untraceable_teaching_tokens_before_manuscript() -> None:
    document = _document()
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    calls: list[dict] = []

    async def planner(request):
        calls.append(request)
        unit = request["teaching_units"][0]
        invalid = len(calls) == 1
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "pages": [{
                "page_id": "teaching-token-page",
                "teaching_unit_id": unit["teaching_unit_id"],
                "template_layout_id": _layout_for_request_blocks(
                    unit,
                    unit["primary_block_ids"],
                ),
                "title": unit["title_candidates"][0],
                "summary": "",
                "visible_copy": ["先界定输入，再执行动作，最后核对结果。"],
                "page_goal": (
                    "解释 fabricatedMetric9001 的作用"
                    if invalid
                    else "解释可靠流程怎样形成闭环"
                ),
                "primary_claim": "可靠流程必须核对完成条件和异常原因。",
                "audience_question": "怎样判断流程已经完成？",
                "audience_action": "",
                "expected_response": "同时检查完成条件和异常原因。",
                "observable_evidence": "",
                "transition": "从输入条件进入执行与核对。",
                "reveal_steps": ["界定输入", "执行动作", "核对结果"],
                "composition_notes": "按流程顺序呈现",
                "question_bank_item_ids": [],
                "shared_visual_expression_ids": [],
                "source_block_ids": unit["primary_block_ids"],
            }],
        }

    story = await plan_slide_story_v3(
        graph,
        template,
        ai_planner=planner,
    )

    assert len(calls) == 2
    repair_target = calls[1]["repair_feedback"]["repair_targets"][0]
    assert repair_target["unsupported_protected_tokens"] == [
        "fabricatedmetric9001"
    ]
    assert repair_target["current_teaching_fields"]["page_goal"] == (
        "解释 fabricatedMetric9001 的作用"
    )
    assert story.pages[0].page_goal == "解释可靠流程怎样形成闭环"


@pytest.mark.asyncio
async def test_live_story_response_repairs_missing_teaching_contract_before_manuscript() -> None:
    document = _document()
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    calls: list[dict] = []

    async def planner(request):
        calls.append(request)
        unit = request["teaching_units"][0]
        repaired = len(calls) > 1
        payload = {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "provider": "shared-ai-pool",
            "model": "qwen3.8-27b",
            "attempts": 1,
            "narrative_brief": {
                "schema_version": "slide_narrative_brief_v1",
                "central_question": "怎样形成可靠工作流？",
                "learning_path": ["界定输入", "执行动作", "核对结果"],
                "observable_checkpoints": ["能说明完成条件和异常原因"],
                "time_budget_minutes": 15,
                "must_include_source_block_ids": unit["primary_block_ids"],
            },
            "pages": [{
                "page_id": "live-teaching-contract",
                "teaching_unit_id": unit["teaching_unit_id"],
                "template_layout_id": _layout_for_request_blocks(
                    unit,
                    unit["primary_block_ids"],
                ),
                "title": unit["title_candidates"][0],
                "summary": "",
                "visible_copy": (
                    ["先界定输入，再执行动作，最后核对结果。"]
                    if repaired else []
                ),
                "page_goal": "解释可靠流程怎样形成闭环" if repaired else "",
                "primary_claim": (
                    "可靠流程必须完成输入、动作与结果核对。"
                    if repaired else ""
                ),
                "audience_question": "怎样判断流程已经完成？" if repaired else "",
                "audience_action": "",
                "expected_response": (
                    "同时检查完成条件和异常原因。" if repaired else ""
                ),
                "observable_evidence": "",
                "transition": "从界定输入推进到结果核对。" if repaired else "",
                "reveal_steps": (
                    ["界定输入", "执行动作", "核对结果"] if repaired else []
                ),
                "composition_notes": "按工作顺序呈现三个动作" if repaired else "",
                "question_bank_item_ids": [],
                "shared_visual_expression_ids": [],
                "source_block_ids": unit["primary_block_ids"],
            }],
        }
        return planning_module._AIPlannerResponse(payload)

    story = await plan_slide_story_v3(
        graph,
        template,
        ai_planner=planner,
    )

    assert len(calls) == 2
    assert calls[1]["repair_feedback"]["code"] == (
        "story_teaching_contract_incomplete"
    )
    assert story.pages[0].visible_copy
    assert story.pages[0].page_goal == "解释可靠流程怎样形成闭环"
    assert story.pages[0].primary_claim
    assert story.pages[0].reveal_steps
    assert story.pages[0].composition_notes


@pytest.mark.asyncio
async def test_live_story_repairs_visible_copy_that_overflows_formula_panel() -> None:
    long_copy = (
        "主对角线元素相乘得到行列式，非对角元素不改变该结构判断。"
        * 8
    )
    short_copy = "三角矩阵的行列式等于主对角线元素的乘积。"
    document = refresh_document_revision(CourseDocument(
        course_id="formula-live-capacity",
        title="三角矩阵",
        sections=[CourseSection(
            section_id="formula",
            title="三角矩阵的行列式",
            position=0,
        )],
        blocks=[CourseBlock(
            block_id="triangular-determinant",
            section_id="formula",
            position=0,
            role="reasoning",
            payload={
                "title": "三角矩阵的行列式",
                "markdown": (
                    f"三角矩阵的行列式可以直接计算。{long_copy}\n\n"
                    "$$\\det(A)=a_{11}a_{22}a_{33}$$"
                ),
            },
        )],
    ))
    graph = compile_course_presentation_graph(document, teaching_plan={})
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    calls: list[dict] = []

    async def planner(request):
        calls.append(request)
        unit = request["teaching_units"][0]
        repaired = len(calls) > 1
        layout = next(
            layout_id
            for layout_id in unit["allowed_template_layout_ids"]
            if layout_id.endswith("/evidence-formula")
        )
        return planning_module._AIPlannerResponse({
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "provider": "shared-ai-pool",
            "model": "qwen3.8-27b",
            "attempts": 1,
            "narrative_brief": {
                "schema_version": "slide_narrative_brief_v1",
                "central_question": "怎样直接计算三角矩阵的行列式？",
                "learning_path": ["识别三角结构", "读取主对角线元素"],
                "observable_checkpoints": ["能写出主对角线元素的乘积"],
                "time_budget_minutes": 8,
                "must_include_source_block_ids": unit["primary_block_ids"],
            },
            "pages": [{
                "page_id": "formula-live-page",
                "teaching_unit_id": unit["teaching_unit_id"],
                "template_layout_id": layout,
                "title": _title_for_request_blocks(
                    unit,
                    unit["primary_block_ids"],
                ),
                "summary": "",
                "visible_copy": [short_copy if repaired else long_copy],
                "page_goal": "说明三角矩阵的行列式计算规则",
                "primary_claim": short_copy,
                "audience_question": "行列式由哪些元素决定？",
                "audience_action": "",
                "expected_response": "主对角线元素的乘积。",
                "observable_evidence": "",
                "transition": "从三角结构进入行列式计算。",
                "reveal_steps": ["识别三角结构", "读取主对角线", "计算元素乘积"],
                "composition_notes": "公式与简短解释并列",
                "question_bank_item_ids": [],
                "shared_visual_expression_ids": [],
                "source_block_ids": unit["primary_block_ids"],
            }],
        })

    story = await plan_slide_story_v3(
        graph,
        template,
        ai_planner=planner,
    )

    assert len(calls) == 2
    assert calls[1]["repair_feedback"]["code"] == (
        "story_visible_copy_capacity_exceeded"
    )
    repair_target = calls[1]["repair_feedback"]["repair_targets"][0]
    assert repair_target["visible_copy_capacity"]["max_chars"] == 360
    assert repair_target["visible_copy_capacity"]["capacity_profile"] == (
        "formula-source-panel-v1"
    )
    assert story.pages[0].visible_copy == [short_copy]


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
        if layout.template_layout_id.endswith("/content-stack")
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
        resume_decisions=[healthy_table, healthy_table.model_copy(deep=True)],
    )

    assert requested_page_ids == [["field-feedback"]]
    assert resumed.decisions[0] is healthy_table
    assert [decision.page_id for decision in resumed.decisions] == [
        "field-table",
        "field-feedback",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("checkpoint_problem", ["unknown", "conflict"])
async def test_visual_planning_rejects_incompatible_checkpoint_page_identity(
    checkpoint_problem: str,
) -> None:
    graph, template, story, visual = _field_visual_repair_fixture()
    healthy_table = visual.decisions[0]
    incompatible = healthy_table.model_copy(deep=True)
    if checkpoint_problem == "unknown":
        incompatible.page_id = "cross-batch-page"
    else:
        incompatible.decision = "data"
    planner_calls = 0

    async def planner(_request):
        nonlocal planner_calls
        planner_calls += 1
        raise AssertionError("An incompatible checkpoint must fail before AI planning")

    with pytest.raises(V6BuildError) as captured:
        await plan_slide_visuals_v2(
            story,
            graph,
            template,
            ai_planner=planner,
            resume_decisions=[healthy_table, incompatible],
        )

    assert planner_calls == 0
    assert captured.value.failure.stage == "recovery"
    assert captured.value.failure.code == "v6_recovery_contract_mismatch"
    assert captured.value.failure.page_id == (
        "cross-batch-page" if checkpoint_problem == "unknown" else "field-table"
    )


def _visual_decision_for_request_page(
    page: dict,
    *,
    decision: str | None = None,
) -> dict:
    resolved_decision = decision or (
        "table" if "table" in page["allowed_decisions"] else "text_native"
    )
    return {
        "page_id": page["page_id"],
        "decision": resolved_decision,
        "source_block_ids": page["source_block_ids"],
        "resolved_template_layout_id": page["template_layout_id"],
    }


@pytest.mark.asyncio
async def test_visual_missing_page_is_repaired_without_reasking_valid_pages() -> None:
    """A missing decision is appended to preserved valid work in Story order."""

    graph, template, story, _visual = _field_visual_repair_fixture()
    requests: list[dict] = []

    async def planner(request):
        requests.append(request)
        pages = {page["page_id"]: page for page in request["pages"]}
        if len(requests) == 1:
            decisions = [_visual_decision_for_request_page(pages["field-table"])]
        else:
            decisions = [_visual_decision_for_request_page(pages["field-feedback"])]
        return {
            "schema_version": "slide_visual_batch_response_v2",
            "provider": "fixture",
            "model": "fixture",
            "decisions": decisions,
        }

    visual = await plan_slide_visuals_v2(
        story,
        graph,
        template,
        ai_planner=planner,
    )

    assert [[page["page_id"] for page in request["pages"]] for request in requests] == [
        ["field-table", "field-feedback"],
        ["field-feedback"],
    ]
    assert [decision.page_id for decision in visual.decisions] == [
        "field-table",
        "field-feedback",
    ]
    assert visual.decisions[0].decision == "table"
    assert visual.decisions[1].decision == "text_native"


@pytest.mark.asyncio
async def test_visual_conflicting_duplicate_repairs_only_the_conflicted_page() -> None:
    graph, template, story, _visual = _field_visual_repair_fixture()
    requests: list[dict] = []

    async def planner(request):
        requests.append(request)
        pages = {page["page_id"]: page for page in request["pages"]}
        if len(requests) == 1:
            feedback = _visual_decision_for_request_page(pages["field-feedback"])
            conflicting = {
                **feedback,
                "decision": "diagram",
                "visual_payload": {
                    "nodes": [
                        {
                            "node_id": "observe",
                            "label": "Interpret the observation record",
                            "source_block_ids": feedback["source_block_ids"],
                        },
                        {
                            "node_id": "report",
                            "label": "Report the verified finding",
                            "source_block_ids": feedback["source_block_ids"],
                        },
                    ],
                    "edges": [{"source": "observe", "target": "report"}],
                },
            }
            decisions = [
                _visual_decision_for_request_page(pages["field-table"]),
                feedback,
                conflicting,
            ]
        else:
            decisions = [_visual_decision_for_request_page(pages["field-feedback"])]
        return {
            "schema_version": "slide_visual_batch_response_v2",
            "provider": "fixture",
            "model": "fixture",
            "decisions": decisions,
        }

    visual = await plan_slide_visuals_v2(
        story,
        graph,
        template,
        ai_planner=planner,
    )

    assert [[page["page_id"] for page in request["pages"]] for request in requests] == [
        ["field-table", "field-feedback"],
        ["field-feedback"],
    ]
    assert [decision.page_id for decision in visual.decisions] == [
        "field-table",
        "field-feedback",
    ]
    assert visual.decisions[1].decision == "text_native"


@pytest.mark.asyncio
async def test_visual_equivalent_duplicate_is_deduplicated_without_repair() -> None:
    graph, template, story, _visual = _field_visual_repair_fixture()
    requests: list[dict] = []

    async def planner(request):
        requests.append(request)
        decisions = [
            _visual_decision_for_request_page(page)
            for page in reversed(request["pages"])
        ]
        decisions.append(dict(decisions[0]))
        return {
            "schema_version": "slide_visual_batch_response_v2",
            "provider": "fixture",
            "model": "fixture",
            "decisions": decisions,
        }

    visual = await plan_slide_visuals_v2(
        story,
        graph,
        template,
        ai_planner=planner,
    )

    assert len(requests) == 1
    assert [decision.page_id for decision in visual.decisions] == [
        "field-table",
        "field-feedback",
    ]


@pytest.mark.asyncio
async def test_visual_unknown_page_is_never_silently_discarded() -> None:
    graph, template, story, _visual = _field_visual_repair_fixture()
    calls = 0

    async def planner(request):
        nonlocal calls
        calls += 1
        decisions = [
            _visual_decision_for_request_page(page) for page in request["pages"]
        ]
        decisions.append({
            **decisions[0],
            "page_id": "cross-batch-page",
        })
        return {
            "schema_version": "slide_visual_batch_response_v2",
            "provider": "fixture",
            "model": "fixture",
            "decisions": decisions,
        }

    with pytest.raises(V6BuildError) as captured:
        await plan_slide_visuals_v2(
            story,
            graph,
            template,
            ai_planner=planner,
        )

    assert calls == 2
    assert captured.value.failure.code == "visual_page_unknown"
    assert captured.value.failure.page_id == "cross-batch-page"


@pytest.mark.asyncio
async def test_visual_missing_page_repair_stays_bounded_and_reports_the_page() -> None:
    graph, template, story, _visual = _field_visual_repair_fixture()
    requests: list[dict] = []

    async def planner(request):
        requests.append(request)
        table = next(
            (page for page in request["pages"] if page["page_id"] == "field-table"),
            None,
        )
        decisions = [_visual_decision_for_request_page(table)] if table else [{
            **_visual_decision_for_request_page(request["pages"][0]),
            "page_id": "cross-batch-page",
        }]
        return {
            "schema_version": "slide_visual_batch_response_v2",
            "provider": "fixture",
            "model": "fixture",
            "decisions": decisions,
        }

    with pytest.raises(V6BuildError) as captured:
        await plan_slide_visuals_v2(
            story,
            graph,
            template,
            ai_planner=planner,
        )

    assert len(requests) == 2
    assert [page["page_id"] for page in requests[1]["pages"]] == ["field-feedback"]
    assert captured.value.failure.code == "visual_page_unknown"
    assert captured.value.failure.page_id == "cross-batch-page"
