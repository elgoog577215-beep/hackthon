import asyncio
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest
import slide_deck_v6_orchestrator as orchestrator_module

from course_document import CourseBlock, CourseDocument, CourseSection, refresh_document_revision
from representation_compiler import export_slide_deck_pptx
from slide_ai_planning_v6 import AIPlannerInvocationError
from slide_build_progress_v2 import (
    SlideBuildProgressManifestV2,
    SlideBuildProgressRepositoryV2,
    SlideWorkItemV2,
)
from slide_deck_v6 import PptManuscriptV1, V6BuildError
from slide_deck_v6_orchestrator import (
    SlideDeckV6CandidateRepository,
    SlideDeckV6Orchestrator,
)
from teaching_representations import TeachingRepresentationRepository
from template_layout_contract import compile_builtin_template_layout_contract_v1


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


def test_planning_cost_summary_aggregates_model_usage() -> None:
    summary = orchestrator_module._planning_cost_summary([
        {
            "physical_request_count": 2,
            "input_tokens": 1200,
            "output_tokens": 300,
            "tokens_source": "provider",
            "duration_ms": 4500,
            "retry_count": 1,
        },
        {
            "physical_request_count": 1,
            "input_tokens": 800,
            "output_tokens": 200,
            "tokens_source": "estimate",
            "duration_ms": 1500,
            "retry_count": 0,
        },
    ])

    assert summary == {
        "schema_version": "ppt_planning_cost_v1",
        "model_call_count": 3,
        "input_tokens": 2000,
        "output_tokens": 500,
        "tokens_source": "mixed",
        "ai_busy_duration_ms": 6000,
        "retry_count": 1,
    }


def _two_chapter_document() -> CourseDocument:
    return refresh_document_revision(
        CourseDocument(
            course_id="course-v6-restart-fixture",
            title="跨章节现场观察",
            sections=[
                CourseSection(section_id="chapter-1", title="记录", position=0),
                CourseSection(section_id="chapter-2", title="核对", position=1),
            ],
            blocks=[
                CourseBlock(
                    block_id="record",
                    section_id="chapter-1",
                    position=0,
                    role="concept",
                    payload={"markdown": "记录对象、时间与环境。"},
                ),
                CourseBlock(
                    block_id="verify",
                    section_id="chapter-2",
                    position=0,
                    role="concept",
                    payload={"markdown": "核对事实、解释与结论。"},
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
async def test_build_rejects_checkpoint_from_previous_build_contract(tmp_path: Path) -> None:
    document = _document()
    orchestrator, _representations, candidates = _orchestrator(tmp_path)
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    task_id = "task-v6-stale-contract"
    candidates.save_checkpoint(task_id, {
        "schema_version": "slide_deck_v6_checkpoint_v1",
        "task_id": task_id,
        "course_id": document.course_id,
        "course_document_revision": document.document_revision,
        "template_digest": template.template_digest,
        "mode": "teaching",
        "theme": "qizhi-classroom",
        "story_batches": [],
        "visual_decisions": [],
    })
    planner_calls = 0

    async def planner_must_not_run(_request):
        nonlocal planner_calls
        planner_calls += 1
        raise AssertionError("stale checkpoints must fail before AI planning")

    with pytest.raises(V6BuildError) as captured:
        await orchestrator.build(
            task_id=task_id,
            document=document,
            course_data={},
            mode="teaching",
            theme="qizhi-classroom",
            story_planner=planner_must_not_run,
            visual_planner=planner_must_not_run,
            source_revision_provider=lambda: document.document_revision,
            template_contract=template,
        )

    assert captured.value.failure.code == "v6_recovery_contract_mismatch"
    assert captured.value.failure.retryable is False
    assert planner_calls == 0


@pytest.mark.asyncio
async def test_build_rejects_v4_checkpoint_after_story_contract_upgrade(
    tmp_path: Path,
) -> None:
    document = _document()
    orchestrator, _representations, candidates = _orchestrator(tmp_path)
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    task_id = "task-v6-v4-story-contract"
    candidates.save_checkpoint(task_id, {
        "schema_version": "slide_deck_v6_checkpoint_v1",
        "build_contract_version": "slide_deck_v6_build_contract_v4",
        "task_id": task_id,
        "course_id": document.course_id,
        "course_document_revision": document.document_revision,
        "template_digest": template.template_digest,
        "mode": "teaching",
        "theme": "qizhi-classroom",
        "story_batches": [],
        "visual_decisions": [],
    })
    planner_calls = 0

    async def planner_must_not_run(_request):
        nonlocal planner_calls
        planner_calls += 1
        raise AssertionError("v4 story checkpoints must be rejected before planning")

    with pytest.raises(V6BuildError) as captured:
        await orchestrator.build(
            task_id=task_id,
            document=document,
            course_data={},
            mode="teaching",
            theme="qizhi-classroom",
            story_planner=planner_must_not_run,
            visual_planner=planner_must_not_run,
            source_revision_provider=lambda: document.document_revision,
            template_contract=template,
        )

    assert captured.value.failure.code == "v6_recovery_contract_mismatch"
    assert captured.value.failure.retryable is False
    assert planner_calls == 0


@pytest.mark.asyncio
async def test_build_rejects_v5_checkpoint_after_grounding_repair_upgrade(
    tmp_path: Path,
) -> None:
    document = _document()
    orchestrator, _representations, candidates = _orchestrator(tmp_path)
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    task_id = "task-v6-v5-grounding-contract"
    candidates.save_checkpoint(task_id, {
        "schema_version": "slide_deck_v6_checkpoint_v1",
        "build_contract_version": "slide_deck_v6_build_contract_v5",
        "task_id": task_id,
        "course_id": document.course_id,
        "course_document_revision": document.document_revision,
        "template_digest": template.template_digest,
        "mode": "teaching",
        "theme": "qizhi-classroom",
        "story_batches": [],
        "visual_decisions": [],
    })
    planner_calls = 0

    async def planner_must_not_run(_request):
        nonlocal planner_calls
        planner_calls += 1
        raise AssertionError("v5 story checkpoints must be rejected before planning")

    with pytest.raises(V6BuildError) as captured:
        await orchestrator.build(
            task_id=task_id,
            document=document,
            course_data={},
            mode="teaching",
            theme="qizhi-classroom",
            story_planner=planner_must_not_run,
            visual_planner=planner_must_not_run,
            source_revision_provider=lambda: document.document_revision,
            template_contract=template,
        )

    assert captured.value.failure.code == "v6_recovery_contract_mismatch"
    assert captured.value.failure.retryable is False
    assert planner_calls == 0


@pytest.mark.asyncio
async def test_build_rejects_v6_checkpoint_after_visual_fallback_upgrade(
    tmp_path: Path,
) -> None:
    document = _document()
    orchestrator, _representations, candidates = _orchestrator(tmp_path)
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    task_id = "task-v6-v6-visual-fallback-contract"
    candidates.save_checkpoint(task_id, {
        "schema_version": "slide_deck_v6_checkpoint_v1",
        "build_contract_version": "slide_deck_v6_build_contract_v6",
        "task_id": task_id,
        "course_id": document.course_id,
        "course_document_revision": document.document_revision,
        "template_digest": template.template_digest,
        "mode": "teaching",
        "theme": "qizhi-classroom",
        "story_batches": [],
        "visual_decisions": [],
    })
    planner_calls = 0

    async def planner_must_not_run(_request):
        nonlocal planner_calls
        planner_calls += 1
        raise AssertionError("v6 visual checkpoints must be rejected before planning")

    with pytest.raises(V6BuildError) as captured:
        await orchestrator.build(
            task_id=task_id,
            document=document,
            course_data={},
            mode="teaching",
            theme="qizhi-classroom",
            story_planner=planner_must_not_run,
            visual_planner=planner_must_not_run,
            source_revision_provider=lambda: document.document_revision,
            template_contract=template,
        )

    assert captured.value.failure.code == "v6_recovery_contract_mismatch"
    assert captured.value.failure.retryable is False
    assert planner_calls == 0


@pytest.mark.asyncio
async def test_build_rejects_v7_checkpoint_after_artifact_source_upgrade(
    tmp_path: Path,
) -> None:
    document = _document()
    orchestrator, _representations, candidates = _orchestrator(tmp_path)
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    task_id = "task-v6-v7-artifact-source-contract"
    candidates.save_checkpoint(task_id, {
        "schema_version": "slide_deck_v6_checkpoint_v1",
        "build_contract_version": "slide_deck_v6_build_contract_v7",
        "task_id": task_id,
        "course_id": document.course_id,
        "course_document_revision": document.document_revision,
        "template_digest": template.template_digest,
        "mode": "teaching",
        "theme": "qizhi-classroom",
        "story_batches": [],
        "visual_decisions": [],
    })
    planner_calls = 0

    async def planner_must_not_run(_request):
        nonlocal planner_calls
        planner_calls += 1
        raise AssertionError("v7 artifact checkpoints must be rejected before planning")

    with pytest.raises(V6BuildError) as captured:
        await orchestrator.build(
            task_id=task_id,
            document=document,
            course_data={},
            mode="teaching",
            theme="qizhi-classroom",
            story_planner=planner_must_not_run,
            visual_planner=planner_must_not_run,
            source_revision_provider=lambda: document.document_revision,
            template_contract=template,
        )

    assert captured.value.failure.code == "v6_recovery_contract_mismatch"
    assert captured.value.failure.retryable is False
    assert planner_calls == 0


@pytest.mark.asyncio
async def test_build_rejects_v8_checkpoint_after_rich_text_artifact_pagination_upgrade(
    tmp_path: Path,
) -> None:
    document = _document()
    orchestrator, _representations, candidates = _orchestrator(tmp_path)
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    task_id = "task-v6-v8-rich-text-artifact-pagination-contract"
    candidates.save_checkpoint(task_id, {
        "schema_version": "slide_deck_v6_checkpoint_v1",
        "build_contract_version": "slide_deck_v6_build_contract_v8",
        "task_id": task_id,
        "course_id": document.course_id,
        "course_document_revision": document.document_revision,
        "template_digest": template.template_digest,
        "mode": "teaching",
        "theme": "qizhi-classroom",
        "story_batches": [],
        "visual_decisions": [],
    })
    planner_calls = 0

    async def planner_must_not_run(_request):
        nonlocal planner_calls
        planner_calls += 1
        raise AssertionError("v8 pagination checkpoints must be rejected before planning")

    with pytest.raises(V6BuildError) as captured:
        await orchestrator.build(
            task_id=task_id,
            document=document,
            course_data={},
            mode="teaching",
            theme="qizhi-classroom",
            story_planner=planner_must_not_run,
            visual_planner=planner_must_not_run,
            source_revision_provider=lambda: document.document_revision,
            template_contract=template,
        )

    assert captured.value.failure.code == "v6_recovery_contract_mismatch"
    assert captured.value.failure.retryable is False
    assert planner_calls == 0


@pytest.mark.asyncio
async def test_build_rejects_v9_checkpoint_after_support_density_upgrade(
    tmp_path: Path,
) -> None:
    document = _document()
    orchestrator, _representations, candidates = _orchestrator(tmp_path)
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    task_id = "task-v6-v9-support-density-contract"
    candidates.save_checkpoint(task_id, {
        "schema_version": "slide_deck_v6_checkpoint_v1",
        "build_contract_version": "slide_deck_v6_build_contract_v9",
        "task_id": task_id,
        "course_id": document.course_id,
        "course_document_revision": document.document_revision,
        "template_digest": template.template_digest,
        "mode": "teaching",
        "theme": "qizhi-classroom",
        "story_batches": [],
        "visual_decisions": [],
    })
    planner_calls = 0

    async def planner_must_not_run(_request):
        nonlocal planner_calls
        planner_calls += 1
        raise AssertionError("v9 support checkpoints must be rejected before planning")

    with pytest.raises(V6BuildError) as captured:
        await orchestrator.build(
            task_id=task_id,
            document=document,
            course_data={},
            mode="teaching",
            theme="qizhi-classroom",
            story_planner=planner_must_not_run,
            visual_planner=planner_must_not_run,
            source_revision_provider=lambda: document.document_revision,
            template_contract=template,
        )

    assert captured.value.failure.code == "v6_recovery_contract_mismatch"
    assert captured.value.failure.retryable is False
    assert planner_calls == 0


@pytest.mark.asyncio
async def test_build_rejects_v10_checkpoint_after_global_page_identity_upgrade(
    tmp_path: Path,
) -> None:
    document = _document()
    orchestrator, _representations, candidates = _orchestrator(tmp_path)
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    task_id = "task-v6-v10-global-page-identity-contract"
    candidates.save_checkpoint(task_id, {
        "schema_version": "slide_deck_v6_checkpoint_v1",
        "build_contract_version": "slide_deck_v6_build_contract_v10",
        "task_id": task_id,
        "course_id": document.course_id,
        "course_document_revision": document.document_revision,
        "template_digest": template.template_digest,
        "mode": "teaching",
        "theme": "qizhi-classroom",
        "story_batches": [],
        "visual_decisions": [],
    })
    planner_calls = 0

    async def planner_must_not_run(_request):
        nonlocal planner_calls
        planner_calls += 1
        raise AssertionError("v10 page identity checkpoints must be rejected before planning")

    with pytest.raises(V6BuildError) as captured:
        await orchestrator.build(
            task_id=task_id,
            document=document,
            course_data={},
            mode="teaching",
            theme="qizhi-classroom",
            story_planner=planner_must_not_run,
            visual_planner=planner_must_not_run,
            source_revision_provider=lambda: document.document_revision,
            template_contract=template,
        )

    assert captured.value.failure.code == "v6_recovery_contract_mismatch"
    assert captured.value.failure.retryable is False
    assert planner_calls == 0


@pytest.mark.asyncio
async def test_build_rejects_v13_checkpoint_after_template_pagination_upgrade(
    tmp_path: Path,
) -> None:
    document = _document()
    orchestrator, _representations, candidates = _orchestrator(tmp_path)
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    task_id = "task-v6-v13-template-pagination-contract"
    candidates.save_checkpoint(task_id, {
        "schema_version": "slide_deck_v6_checkpoint_v1",
        "build_contract_version": "slide_deck_v6_build_contract_v13",
        "task_id": task_id,
        "course_id": document.course_id,
        "course_document_revision": document.document_revision,
        "template_digest": template.template_digest,
        "mode": "teaching",
        "theme": "qizhi-classroom",
        "story_batches": [],
        "visual_decisions": [],
    })
    planner_calls = 0

    async def planner_must_not_run(_request):
        nonlocal planner_calls
        planner_calls += 1
        raise AssertionError("v13 pagination checkpoints must be rejected before planning")

    with pytest.raises(V6BuildError) as captured:
        await orchestrator.build(
            task_id=task_id,
            document=document,
            course_data={},
            mode="teaching",
            theme="qizhi-classroom",
            story_planner=planner_must_not_run,
            visual_planner=planner_must_not_run,
            source_revision_provider=lambda: document.document_revision,
            template_contract=template,
        )

    assert captured.value.failure.code == "v6_recovery_contract_mismatch"
    assert captured.value.failure.retryable is False
    assert planner_calls == 0


@pytest.mark.asyncio
async def test_build_rejects_v19_checkpoint_after_semantic_layout_upgrade(
    tmp_path: Path,
) -> None:
    document = _document()
    orchestrator, _representations, candidates = _orchestrator(tmp_path)
    template = compile_builtin_template_layout_contract_v1("qizhi-classroom")
    task_id = "task-v6-v19-semantic-layout-contract"
    candidates.save_checkpoint(task_id, {
        "schema_version": "slide_deck_v6_checkpoint_v1",
        "build_contract_version": "slide_deck_v6_build_contract_v19",
        "task_id": task_id,
        "course_id": document.course_id,
        "course_document_revision": document.document_revision,
        "template_digest": template.template_digest,
        "mode": "teaching",
        "theme": "qizhi-classroom",
        "story_batches": [],
        "visual_decisions": [],
    })
    planner_calls = 0

    async def planner_must_not_run(_request):
        nonlocal planner_calls
        planner_calls += 1
        raise AssertionError("v19 semantic checkpoints must be rejected before planning")

    with pytest.raises(V6BuildError) as captured:
        await orchestrator.build(
            task_id=task_id,
            document=document,
            course_data={},
            mode="teaching",
            theme="qizhi-classroom",
            story_planner=planner_must_not_run,
            visual_planner=planner_must_not_run,
            source_revision_provider=lambda: document.document_revision,
            template_contract=template,
        )

    assert captured.value.failure.code == "v6_recovery_contract_mismatch"
    assert captured.value.failure.retryable is False
    assert planner_calls == 0


def test_candidate_metrics_report_v6_outcomes_degradation_and_stage_time(tmp_path: Path) -> None:
    candidates = SlideDeckV6CandidateRepository(tmp_path / "candidates")
    progress_root = tmp_path / "progress"
    common = {"schema_version": "slide_deck_v6_candidate_v1", "course_id": "generic-course"}
    candidates.save("ready", {
        **common,
        "task_id": "ready",
        "status": "v6_ready",
        "visual_plan": {"decisions": [{"degraded": False}, {"degraded": False}]},
        "ai_batch_diagnostics": [{
            "physical_request_count": 2,
            "input_tokens": 4000,
            "output_tokens": 800,
            "duration_ms": 5000,
            "retry_count": 1,
        }],
        "failure": None,
    })
    candidates.save("manual", {
        **common,
        "task_id": "manual",
        "status": "v6_needs_manual_edit",
        "visual_plan": {"decisions": [{"degraded": True}, {"degraded": False}]},
        "failure": None,
    })
    candidates.save("story-failed", {
        **common,
        "task_id": "story-failed",
        "status": "v6_failed",
        "failure": {"stage": "story", "code": "story_ai_batch_timeout"},
    })
    candidates.save("template-failed", {
        **common,
        "task_id": "template-failed",
        "status": "v6_failed",
        "failure": {"stage": "template", "code": "template_layout_unavailable"},
    })
    now = datetime.now(timezone.utc).isoformat()
    SlideBuildProgressRepositoryV2(progress_root).save(SlideBuildProgressManifestV2(
        task_id="ready",
        status="completed",
        items=[SlideWorkItemV2(
            item_id="source",
            kind="local",
            stage="source",
            label="Freeze source",
            status="completed",
            discovered_at=now,
            started_at="2026-01-01T00:00:00+00:00",
            completed_at="2026-01-01T00:00:02+00:00",
        )],
        started_at=now,
        updated_at=now,
        last_event_at=now,
    ))

    metrics = candidates.summarize(
        course_id="generic-course",
        progress_root=progress_root,
    )

    assert metrics["total_builds"] == 4
    assert metrics["success_rate"] == 0.5
    assert metrics["story_ai_failure_rate"] == 0.25
    assert metrics["visual_degradation_rate"] == 0.25
    assert metrics["manual_edit_rate"] == 0.25
    assert metrics["template_conflict_rate"] == 0.25
    assert metrics["average_stage_duration_ms"] == {"source": 2000}
    assert metrics["planning_cost"] == {
        "schema_version": "ppt_planning_cost_metrics_v1",
        "measured_build_count": 1,
        "model_call_count": 2,
        "input_tokens": 4000,
        "output_tokens": 800,
        "ai_busy_duration_ms": 5000,
        "retry_count": 1,
    }


@pytest.mark.asyncio
async def test_orchestrator_publishes_v6_atomically_with_ai_diagnostics(tmp_path: Path) -> None:
    document = _document()
    document.blocks[0].evidence_refs = ["ev-observation-checklist"]
    document = refresh_document_revision(document)
    orchestrator, representations, candidates = _orchestrator(tmp_path)

    result = await orchestrator.build(
        task_id="task-v6-success",
        document=document,
        course_data={
            "course_teaching_plan": {"revision": "plan-r1"},
            "course_knowledge_base": {"revision": "knowledge-r1"},
            "evidence_catalog": [{
                "evidence_id": "ev-observation-checklist",
                "summary": "现场观察记录应包含对象、时间和环境条件。",
            }],
            "teacher_lesson_source": {
                "lesson_plan_revision_id": "plan-r1",
                "script_revision_id": "script-r1",
                "material_bindings": [{
                    "material_asset_id": "mat-observation",
                    "source_asset_id": "tca-observation",
                    "source_label": "现场观察手册.pdf",
                    "role": "primary",
                }],
            },
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
    assert [item["kind"] for item in candidate["ai_batch_diagnostics"]] == [
        "story",
        "visual",
    ]
    assert all(
        item["validation_status"] == "passed"
        for item in candidate["ai_batch_diagnostics"]
    )
    registry = representations.load(document.course_id)
    representation = next(item for item in registry.representations if item.variant_key == "teaching:qizhi-classroom")
    spec = next(item for item in registry.specs if item.spec_id == representation.spec_id)
    assert spec.payload["content"]["schema_version"] == "slide_deck_v6"
    assert spec.payload["content"]["status"] == "v6_ready"
    assert spec.payload["content"]["planning_status"] == {
        "story_ai": {
            "status": "completed",
            "batch_count": 1,
            "providers": ["fixture-pool"],
        },
        "visual_ai": {
            "status": "completed",
            "page_count": 1,
            "degraded_page_count": 0,
            "providers": ["fixture-pool"],
        },
        "cost": {
            "schema_version": "ppt_planning_cost_v1",
            "model_call_count": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "tokens_source": "unknown",
            "ai_busy_duration_ms": sum(
                item["duration_ms"]
                for item in candidate["ai_batch_diagnostics"]
            ),
            "retry_count": 0,
        },
    }
    storyboard = spec.payload["content"]["storyboard"]
    assert storyboard["schema_version"] == "teacher_ppt_storyboard_v1"
    assert storyboard["page_count"] == 1
    assert storyboard["teaching_unit_count"] == 1
    assert storyboard["layout_count"] == 1
    assert storyboard["multi_source_page_count"] == 1
    assert storyboard["pages"][0]["title"] == spec.payload["content"]["pages"][0]["title"]
    assert storyboard["pages"][0]["title"]
    assert storyboard["pages"][0]["source_block_count"] == 2
    manuscript = spec.payload["content"]["ppt_manuscript"]
    assert manuscript["schema_version"] == "ppt_manuscript_v1"
    assert manuscript["quality_status"] == "passed"
    assert manuscript["page_count"] == len(spec.payload["content"]["pages"])
    assert manuscript["manuscript_revision"].startswith("pptman_")
    assert manuscript["pages"][0]["title"] == spec.payload["content"]["pages"][0]["title"]
    assert manuscript["pages"][0]["visible_copy"]
    assert manuscript["pages"][0]["layout_id"]
    assert manuscript["pages"][0]["composition_notes"]
    assert manuscript["pages"][0]["source_script_block_ids"] == (
        spec.payload["content"]["pages"][0]["source_block_ids"]
    )
    assert manuscript["material_bindings"] == [{
        "material_asset_id": "mat-observation",
        "source_asset_id": "tca-observation",
        "source_label": "现场观察手册.pdf",
        "role": "primary",
    }]
    assert manuscript["pages"][0]["source_material_evidence_ids"] == [
        "ev-observation-checklist"
    ]
    assert spec.payload["content"]["build_signature"]["signature"].startswith(
        "slidebuildv6_"
    )
    exported = export_slide_deck_pptx(
        spec,
        tmp_path / "published-v6-with-storyboard.pptx",
    )
    assert exported.is_file()


@pytest.mark.asyncio
async def test_deterministic_story_fallback_is_saved_as_blocked_manuscript(
    tmp_path: Path,
) -> None:
    document = _document()
    orchestrator, representations, candidates = _orchestrator(tmp_path)

    async def fallback_story(request):
        payload = await _story_planner(request)
        payload["provider"] = "codex-structured-fallback"
        payload["model"] = "deterministic-safe-partition"
        return payload

    with pytest.raises(V6BuildError, match="ppt_manuscript_ai_story_unavailable") as blocked:
        await orchestrator.build(
            task_id="task-v6-fallback-manuscript",
            document=document,
            course_data={},
            mode="teaching",
            theme="qizhi-classroom",
            story_planner=fallback_story,
            visual_planner=_visual_planner,
            source_revision_provider=lambda: document.document_revision,
        )

    assert blocked.value.failure.retryable is True
    candidate = candidates.load("task-v6-fallback-manuscript")
    assert candidate["status"] == "v6_failed"
    assert candidate["published"] is False
    assert candidate["deck"] is None
    assert candidate["ppt_manuscript"]["quality_status"] == "blocked"
    assert candidate["failure"]["stage"] == "manuscript"
    assert candidate["failure"]["retryable"] is True
    assert representations.load(document.course_id).representations == []


@pytest.mark.asyncio
async def test_manuscript_only_then_confirmed_build_are_two_distinct_tasks(
    tmp_path: Path,
) -> None:
    document = _document()
    orchestrator, representations, candidates = _orchestrator(tmp_path)

    manuscript_result = await orchestrator.build(
        task_id="task-v6-manuscript-only",
        document=document,
        course_data={},
        mode="teaching",
        theme="qizhi-classroom",
        story_planner=_story_planner,
        visual_planner=_visual_planner,
        source_revision_provider=lambda: document.document_revision,
        publish_result=False,
        manuscript_only=True,
    )

    assert manuscript_result["status"] == "manuscript_ready"
    assert manuscript_result["published"] is False
    assert representations.load(document.course_id).representations == []
    candidate = candidates.load("task-v6-manuscript-only")
    assert candidate["deck"] is None
    assert candidate["ppt_manuscript"]["quality_status"] == "passed"

    candidates.clone_checkpoint(
        "task-v6-manuscript-only", "task-v6-confirmed-deck"
    )

    async def planner_must_not_run(_request):
        raise AssertionError("confirmed manuscript build must reuse frozen planning")

    confirmed = PptManuscriptV1.model_validate(
        manuscript_result["ppt_manuscript"]
    )
    deck_result = await orchestrator.build(
        task_id="task-v6-confirmed-deck",
        document=document,
        course_data={},
        mode="teaching",
        theme="qizhi-classroom",
        story_planner=planner_must_not_run,
        visual_planner=planner_must_not_run,
        source_revision_provider=lambda: document.document_revision,
        confirmed_manuscript=confirmed,
    )

    assert deck_result["published"] is True
    published = representations.load(document.course_id)
    representation = published.representations[0]
    spec = next(item for item in published.specs if item.spec_id == representation.spec_id)
    assert (
        spec.payload["content"]["ppt_manuscript"]["manuscript_revision"]
        == confirmed.manuscript_revision
    )


@pytest.mark.asyncio
async def test_materialization_keeps_the_event_loop_responsive(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """A large synchronous deck compile must not stall task/status APIs."""

    document = _document()
    orchestrator, _representations, _candidates = _orchestrator(tmp_path)
    real_compile = orchestrator_module.compile_ppt_manuscript_v1
    entered = threading.Event()
    release = threading.Event()
    exited = threading.Event()
    ticks = 0

    def slow_compile(*args, **kwargs):
        entered.set()
        release.wait(timeout=2)
        try:
            return real_compile(*args, **kwargs)
        finally:
            exited.set()

    monkeypatch.setattr(
        orchestrator_module,
        "compile_ppt_manuscript_v1",
        slow_compile,
    )

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
            orchestrator.build(
                task_id="task-v6-responsive-materialization",
                document=document,
                course_data={},
                mode="teaching",
                theme="qizhi-classroom",
                story_planner=_story_planner,
                visual_planner=_visual_planner,
                source_revision_provider=lambda: document.document_revision,
            ),
            event_loop_probe(),
        )
    finally:
        release.set()
        timer.cancel()

    assert ticks >= 5


@pytest.mark.asyncio
async def test_progress_discovers_known_ai_and_render_work_before_reporting_99(
    tmp_path: Path,
) -> None:
    document = _document()
    orchestrator, _representations, _candidates = _orchestrator(tmp_path)
    events: list[dict] = []

    await orchestrator.build(
        task_id="task-v6-progress-discovery",
        document=document,
        course_data={},
        mode="teaching",
        theme="qizhi-classroom",
        story_planner=_story_planner,
        visual_planner=_visual_planner,
        source_revision_provider=lambda: document.document_revision,
        progress_callback=lambda event: events.append(event),
    )

    assert all(
        event["percent"] < 99
        for event in events
        if event["stage"] in {"source", "course_graph", "story", "visual"}
    )
    assert [event["percent"] for event in events] == sorted(
        event["percent"] for event in events
    )
    assert events[-1]["percent"] == 100
    assert events[-1]["finalized"] is True


@pytest.mark.asyncio
async def test_shadow_candidate_runs_all_gates_without_replacing_the_public_registry(tmp_path: Path) -> None:
    document = _document()
    orchestrator, representations, candidates = _orchestrator(tmp_path)

    result = await orchestrator.build(
        task_id="task-v6-shadow",
        document=document,
        course_data={},
        mode="teaching",
        theme="qizhi-classroom",
        story_planner=_story_planner,
        visual_planner=_visual_planner,
        source_revision_provider=lambda: document.document_revision,
        publish_result=False,
        shadow_context={
            "chapter_id": "chapter-1",
            "source_course_document_revision": "source-course-revision",
        },
    )

    assert result["status"] == "v6_ready"
    assert result["published"] is False
    assert result["registry"] == {}
    assert result["progress"]["percent"] == 100
    assert result["progress"]["finalized"] is True
    assert result["progress"]["published"] is False
    assert representations.load(document.course_id).representations == []
    candidate = candidates.load("task-v6-shadow")
    assert candidate["shadow_context"]["chapter_id"] == "chapter-1"
    assert candidate["published"] is False


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
async def test_failed_v6_candidate_persists_sanitized_ai_batch_diagnostics(
    tmp_path: Path,
) -> None:
    document = _document()
    orchestrator, _representations, candidates = _orchestrator(tmp_path)

    async def failed_story(_request):
        raise AIPlannerInvocationError(
            RuntimeError("provider quota unavailable"),
            telemetry=[{
                "provider_route": "shared-fallback",
                "model_id": "generic-model",
                "provider_attempt": 2,
                "status": "failed",
                "error_code": "QuotaError",
                "duration_ms": 75,
                "queue_wait_ms": 4,
                "api_key": "must-not-be-persisted",
            }],
        )

    with pytest.raises(V6BuildError, match="story_ai_batch_balance_unavailable"):
        await orchestrator.build(
            task_id="task-v6-failed-diagnostics",
            document=document,
            course_data={},
            mode="teaching",
            theme="qizhi-classroom",
            story_planner=failed_story,
            visual_planner=_visual_planner,
            source_revision_provider=lambda: document.document_revision,
        )

    candidate = candidates.load("task-v6-failed-diagnostics")
    assert candidate["status"] == "v6_failed"
    assert candidate["ai_batch_diagnostics"][0]["failure_category"] == (
        "story_ai_batch_balance_unavailable"
    )
    assert candidate["ai_batch_diagnostics"][0]["provider"] == "shared-fallback"
    assert candidate["ai_batch_diagnostics"][0]["model"] == "generic-model"
    assert "api_key" not in str(candidate["ai_batch_diagnostics"])


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


@pytest.mark.asyncio
async def test_restart_reuses_persisted_story_batches_instead_of_calling_ai_again(
    tmp_path: Path,
) -> None:
    document = _two_chapter_document()
    orchestrator, _representations, _candidates = _orchestrator(tmp_path)
    calls: list[str] = []
    interrupted = True

    async def restartable_story(request):
        nonlocal interrupted
        chapter_id = request["chapter_id"]
        calls.append(chapter_id)
        if chapter_id == "chapter-2" and interrupted:
            interrupted = False
            raise asyncio.CancelledError()
        unit = request["teaching_units"][0]
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": chapter_id,
            "provider": "fixture-pool",
            "model": "fixture-story",
            "attempts": 1,
            "pages": [{
                "page_id": f"page-{chapter_id}",
                "teaching_unit_id": unit["teaching_unit_id"],
                "template_layout_id": next(
                    item for item in unit["allowed_template_layout_ids"]
                    if item.endswith("/content-stack")
                ),
                "title": unit["primary_blocks"][0]["source_text"][:40],
                "summary": "",
                "source_block_ids": unit["primary_block_ids"],
            }],
        }

    with pytest.raises(asyncio.CancelledError):
        await orchestrator.build(
            task_id="task-v6-restart",
            document=document,
            course_data={},
            mode="teaching",
            theme="qizhi-classroom",
            story_planner=restartable_story,
            visual_planner=_visual_planner,
            source_revision_provider=lambda: document.document_revision,
        )

    result = await orchestrator.build(
        task_id="task-v6-restart",
        document=document,
        course_data={},
        mode="teaching",
        theme="qizhi-classroom",
        story_planner=restartable_story,
        visual_planner=_visual_planner,
        source_revision_provider=lambda: document.document_revision,
    )

    assert result["status"] == "v6_ready"
    assert calls.count("chapter-1") == 1
    assert calls.count("chapter-2") == 2


@pytest.mark.asyncio
async def test_retryable_story_failure_resumes_same_task_and_reuses_finished_batches(
    tmp_path: Path,
) -> None:
    document = _two_chapter_document()
    orchestrator, _representations, _candidates = _orchestrator(tmp_path)
    calls: list[str] = []
    failed_once = False

    async def retryable_story(request):
        nonlocal failed_once
        chapter_id = request["chapter_id"]
        calls.append(chapter_id)
        if chapter_id == "chapter-2" and not failed_once:
            failed_once = True
            raise TimeoutError("provider timeout")
        unit = request["teaching_units"][0]
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": chapter_id,
            "provider": "fixture-pool",
            "model": "fixture-story",
            "attempts": 1,
            "pages": [{
                "page_id": f"page-{chapter_id}",
                "teaching_unit_id": unit["teaching_unit_id"],
                "template_layout_id": next(
                    item for item in unit["allowed_template_layout_ids"]
                    if item.endswith("/content-stack")
                ),
                "title": unit["title_candidates"][0],
                "summary": "",
                "source_block_ids": unit["primary_block_ids"],
            }],
        }

    with pytest.raises(V6BuildError, match="story_ai_batch_timeout"):
        await orchestrator.build(
            task_id="task-v6-retryable",
            document=document,
            course_data={},
            mode="teaching",
            theme="qizhi-classroom",
            story_planner=retryable_story,
            visual_planner=_visual_planner,
            source_revision_provider=lambda: document.document_revision,
        )

    result = await orchestrator.build(
        task_id="task-v6-retryable",
        document=document,
        course_data={},
        mode="teaching",
        theme="qizhi-classroom",
        story_planner=retryable_story,
        visual_planner=_visual_planner,
        source_revision_provider=lambda: document.document_revision,
    )

    assert result["status"] == "v6_ready"
    assert calls.count("chapter-1") == 1
    assert calls.count("chapter-2") == 2


async def _publish_degraded_visual_fixture(
    orchestrator: SlideDeckV6Orchestrator,
    document: CourseDocument,
) -> dict:
    async def unavailable_visual(_request):
        raise TimeoutError("shared provider temporarily unavailable")

    return await orchestrator.build(
        task_id="task-v6-degraded-base",
        document=document,
        course_data={},
        mode="teaching",
        theme="qizhi-classroom",
        story_planner=_story_planner,
        visual_planner=unavailable_visual,
        source_revision_provider=lambda: document.document_revision,
    )


@pytest.mark.asyncio
async def test_visual_repair_reuses_published_story_and_atomically_replaces_only_degradation(
    tmp_path: Path,
) -> None:
    document = _document()
    orchestrator, representations, candidates = _orchestrator(tmp_path)
    base = await _publish_degraded_visual_fixture(orchestrator, document)
    assert base["status"] == "v6_needs_manual_edit"
    before_registry = representations.load(document.course_id)
    before_representation = next(
        item for item in before_registry.representations
        if item.representation_id == base["representation_id"]
    )
    before_spec = next(
        item for item in before_registry.specs
        if item.spec_id == before_representation.spec_id
    )
    assert before_spec.payload["content"]["planning_status"]["visual_ai"][
        "degraded_pages"
    ] == [{
        "page_id": "page-1",
        "reason": "visual_ai_batch_timeout",
    }]
    story_before = before_spec.payload["content"]["story_plan"]
    visual_requests = []

    async def story_must_not_run(_request):
        raise AssertionError("visual repair must reuse the published story plan")

    async def repaired_visual(request):
        visual_requests.append([page["page_id"] for page in request["pages"]])
        return await _visual_planner(request)

    repaired = await orchestrator.repair_visuals(
        task_id="task-v6-visual-repair",
        document=document,
        course_data={},
        representation_id=base["representation_id"],
        mode="teaching",
        theme="qizhi-classroom",
        story_planner=story_must_not_run,
        visual_planner=repaired_visual,
        source_revision_provider=lambda: document.document_revision,
    )

    assert repaired["status"] == "v6_ready"
    assert visual_requests == [["page-1"]]
    after_registry = representations.load(document.course_id)
    after_representation = next(
        item for item in after_registry.representations
        if item.representation_id == base["representation_id"]
    )
    assert after_representation.spec_id != before_representation.spec_id
    after_spec = next(
        item for item in after_registry.specs
        if item.spec_id == after_representation.spec_id
    )
    assert after_spec.payload["content"]["story_plan"] == story_before
    assert after_spec.payload["content"]["visual_plan"]["decisions"][0]["degraded"] is False
    repair_candidate = candidates.load("task-v6-visual-repair")
    assert repair_candidate["visual_repair"]["base_spec_id"] == before_spec.spec_id
    assert repair_candidate["visual_repair"]["target_page_ids"] == ["page-1"]


@pytest.mark.asyncio
async def test_failed_visual_repair_keeps_the_published_v6_revision(
    tmp_path: Path,
) -> None:
    document = _document()
    orchestrator, representations, candidates = _orchestrator(tmp_path)
    base = await _publish_degraded_visual_fixture(orchestrator, document)
    before = next(
        item for item in representations.load(document.course_id).representations
        if item.representation_id == base["representation_id"]
    )

    async def unavailable(_request):
        raise TimeoutError("shared provider remains unavailable")

    with pytest.raises(V6BuildError) as captured:
        await orchestrator.repair_visuals(
            task_id="task-v6-visual-repair-failed",
            document=document,
            course_data={},
            representation_id=base["representation_id"],
            mode="teaching",
            theme="qizhi-classroom",
            story_planner=_story_planner,
            visual_planner=unavailable,
            source_revision_provider=lambda: document.document_revision,
        )

    assert captured.value.failure.code == "visual_repair_incomplete"
    after = next(
        item for item in representations.load(document.course_id).representations
        if item.representation_id == base["representation_id"]
    )
    assert after.spec_id == before.spec_id
    failed_candidate = candidates.load("task-v6-visual-repair-failed")
    assert failed_candidate["published"] is False
    assert failed_candidate["failure"]["stage"] == "visual_repair"
