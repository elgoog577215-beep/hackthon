from pathlib import Path

import pytest

from course_document import CourseBlock, CourseDocument, CourseSection, refresh_document_revision
from slide_deck_v6 import V6BuildError
from slide_deck_v6_orchestrator import (
    SlideDeckV6CandidateRepository,
    SlideDeckV6Orchestrator,
)
from teaching_representations import TeachingRepresentationRepository


def _document() -> CourseDocument:
    return refresh_document_revision(
        CourseDocument(
            course_id="course-v6-fixture",
            title="证据驱动的现场观察",
            sections=[CourseSection(section_id="chapter-1", title="观察闭环", position=0)],
            blocks=[
                CourseBlock(
                    block_id="concept",
                    section_id="chapter-1",
                    position=0,
                    role="concept",
                    payload={"markdown": "观察记录必须包含对象、时间和环境条件。"},
                ),
                CourseBlock(
                    block_id="feedback",
                    section_id="chapter-1",
                    position=1,
                    role="feedback",
                    payload={"markdown": "核对时区分观察事实与后续解释。"},
                ),
            ],
        )
    )


async def _story_planner(request):
    unit = request["teaching_units"][0]
    return {
        "schema_version": "slide_story_batch_response_v3",
        "chapter_id": request["chapter_id"],
        "provider": "fixture-pool",
        "model": "fixture-story",
        "attempts": 1,
        "pages": [{
            "page_id": "page-1",
            "teaching_unit_id": unit["teaching_unit_id"],
            "template_layout_id": next(
                item
                for item in unit["allowed_template_layout_ids"]
                if item.endswith("/practice-feedback")
            ),
            "title": "完成观察与核对闭环",
            "summary": "",
            "source_block_ids": unit["primary_block_ids"],
        }],
    }


async def _visual_planner(request):
    return {
        "schema_version": "slide_visual_batch_response_v2",
        "provider": "fixture-pool",
        "model": "fixture-visual",
        "attempts": 1,
        "decisions": [{
            "page_id": page["page_id"],
            "decision": "text_native",
            "source_block_ids": page["source_block_ids"],
            "resolved_template_layout_id": page["template_layout_id"],
        } for page in request["pages"]],
    }


def _orchestrator(tmp_path: Path) -> tuple[SlideDeckV6Orchestrator, TeachingRepresentationRepository, SlideDeckV6CandidateRepository]:
    representations = TeachingRepresentationRepository(tmp_path / "representations")
    candidates = SlideDeckV6CandidateRepository(tmp_path / "candidates")
    orchestrator = SlideDeckV6Orchestrator(
        representation_repository=representations,
        candidate_repository=candidates,
        progress_root=tmp_path / "progress",
    )
    return orchestrator, representations, candidates


@pytest.mark.asyncio
async def test_orchestrator_publishes_v6_atomically_with_ai_diagnostics(tmp_path: Path) -> None:
    document = _document()
    orchestrator, representations, candidates = _orchestrator(tmp_path)

    result = await orchestrator.build(
        task_id="task-v6-success",
        document=document,
        course_data={
            "course_teaching_plan": {"revision": "plan-r1"},
            "course_knowledge_base": {"revision": "knowledge-r1"},
        },
        mode="teaching",
        theme="qizhi-classroom",
        story_planner=_story_planner,
        visual_planner=_visual_planner,
        source_revision_provider=lambda: document.document_revision,
    )

    assert result["status"] == "v6_ready"
    assert result["progress"]["percent"] == 100
    assert result["progress"]["published"] is True
    candidate = candidates.load("task-v6-success")
    assert candidate["status"] == "v6_ready"
    assert candidate["story_plan"]["batches"][0]["provider"] == "fixture-pool"
    registry = representations.load(document.course_id)
    representation = next(item for item in registry.representations if item.variant_key == "teaching:qizhi-classroom")
    spec = next(item for item in registry.specs if item.spec_id == representation.spec_id)
    assert spec.payload["content"]["schema_version"] == "slide_deck_v6"
    assert spec.payload["content"]["status"] == "v6_ready"


@pytest.mark.asyncio
async def test_failed_v6_candidate_keeps_last_published_representation(tmp_path: Path) -> None:
    document = _document()
    orchestrator, representations, candidates = _orchestrator(tmp_path)
    await orchestrator.build(
        task_id="task-v6-first",
        document=document,
        course_data={},
        mode="teaching",
        theme="qizhi-classroom",
        story_planner=_story_planner,
        visual_planner=_visual_planner,
        source_revision_provider=lambda: document.document_revision,
    )
    before = next(
        item for item in representations.load(document.course_id).representations
        if item.variant_key == "teaching:qizhi-classroom"
    )

    async def failed_story(_request):
        raise TimeoutError("provider timeout")

    with pytest.raises(V6BuildError, match="story_ai_batch_timeout"):
        await orchestrator.build(
            task_id="task-v6-failed",
            document=document,
            course_data={},
            mode="teaching",
            theme="qizhi-classroom",
            story_planner=failed_story,
            visual_planner=_visual_planner,
            source_revision_provider=lambda: document.document_revision,
        )

    after = next(
        item for item in representations.load(document.course_id).representations
        if item.variant_key == "teaching:qizhi-classroom"
    )
    assert after.spec_id == before.spec_id
    assert candidates.load("task-v6-failed")["status"] == "v6_failed"


@pytest.mark.asyncio
async def test_source_revision_drift_fails_before_registry_publish(tmp_path: Path) -> None:
    document = _document()
    orchestrator, representations, candidates = _orchestrator(tmp_path)

    with pytest.raises(V6BuildError, match="source_revision_changed"):
        await orchestrator.build(
            task_id="task-v6-drift",
            document=document,
            course_data={},
            mode="teaching",
            theme="qizhi-classroom",
            story_planner=_story_planner,
            visual_planner=_visual_planner,
            source_revision_provider=lambda: "newer-revision",
        )

    assert not representations.load(document.course_id).representations
    failure = candidates.load("task-v6-drift")["failure"]
    assert failure["stage"] == "publish"
    assert failure["retryable"] is True


@pytest.mark.asyncio
async def test_render_audit_failure_keeps_the_previous_published_deck(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import slide_deck_v6_orchestrator as orchestrator_module

    document = _document()
    orchestrator, representations, candidates = _orchestrator(tmp_path)
    await orchestrator.build(
        task_id="task-v6-render-baseline",
        document=document,
        course_data={},
        mode="teaching",
        theme="qizhi-classroom",
        story_planner=_story_planner,
        visual_planner=_visual_planner,
        source_revision_provider=lambda: document.document_revision,
    )
    before = next(item for item in representations.load(document.course_id).representations)
    monkeypatch.setattr(orchestrator_module, "audit_exported_pptx", lambda *_args, **_kwargs: {
        "schema_version": "slide_render_review_v1",
        "passed": False,
        "issues": [{"severity": "critical", "code": "exported_text_frame_overflow", "page": 1}],
        "blockers": [{"severity": "critical", "code": "exported_text_frame_overflow", "page": 1}],
    })

    with pytest.raises(V6BuildError, match="render_quality_gate_failed"):
        await orchestrator.build(
            task_id="task-v6-render-failed",
            document=document,
            course_data={},
            mode="teaching",
            theme="qizhi-classroom",
            story_planner=_story_planner,
            visual_planner=_visual_planner,
            source_revision_provider=lambda: document.document_revision,
        )

    after = next(item for item in representations.load(document.course_id).representations)
    assert after.spec_id == before.spec_id
    assert candidates.load("task-v6-render-failed")["failure"]["stage"] == "render"
