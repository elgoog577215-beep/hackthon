from copy import deepcopy
from pathlib import Path

import pytest

from course_document import (
    COURSE_DOCUMENT_SCHEMA,
    CourseBlock,
    CourseDocument,
    CourseSection,
    refresh_document_revision,
)
from course_repository import CourseDocumentRepository
from teaching_representations import TeachingRepresentationRepository


class MemoryStorage:
    def __init__(self, course: dict, root: Path) -> None:
        self.course = deepcopy(course)
        self._data_dir = root

    def load_course(self, _course_id: str) -> dict:
        return deepcopy(self.course)

    async def save_course(self, _course_id: str, data: dict) -> None:
        self.course = deepcopy(data)


def _canonical_course() -> dict:
    document = refresh_document_revision(
        CourseDocument(
            course_id="generic-task-v6",
            title="Field observation methods",
            sections=[CourseSection(section_id="chapter-1", title="Evidence", position=0)],
            blocks=[
                CourseBlock(
                    block_id="observation",
                    section_id="chapter-1",
                    position=0,
                    role="concept",
                    payload={"markdown": "Record the object, time, context, and observation."},
                ),
            ],
        )
    )
    return {
        "course_id": document.course_id,
        "course_name": document.title,
        "course_revision": document.document_revision,
        "course_schema_version": COURSE_DOCUMENT_SCHEMA,
        "course_document": document.model_dump(mode="json"),
        "course_document_authoritative": True,
        "course_operation_log": [],
        "generation_stage_artifacts": {
            "course_teaching_plan": {"status": "completed", "section_count": 1},
        },
        "course_teaching_plan": {
            "revision_id": "plan-rev-1",
            "sections": [{"node_id": "chapter-1", "teaching_modules": []}],
        },
        "course_knowledge_base": {
            "revision_id": "kb-rev-1",
            "lifecycle_status": "active",
        },
        "course_coherence_contract": {
            "revision_id": "coherence-rev-1",
            "status": "active",
            "quality_report": {"passed": True},
        },
    }


def _legacy_course() -> dict:
    return {
        "course_id": "generic-legacy-v6-shadow",
        "course_name": "Legacy field methods",
        "current_course_version_id": "legacy-v1",
        "nodes": [
            {
                "node_id": "chapter-1",
                "parent_node_id": "root",
                "node_name": "Observation",
                "node_level": 1,
                "node_content": "Define the observation scope.",
            },
            {
                "node_id": "lesson-1",
                "parent_node_id": "chapter-1",
                "node_name": "Record evidence",
                "node_level": 2,
                "node_content": "Record the object, time, context, and result.",
            },
        ],
        "generation_stage_artifacts": {
            "course_teaching_plan": {"status": "completed", "section_count": 1},
        },
        "course_teaching_plan": {
            "revision_id": "legacy-plan-1",
            "sections": [{"node_id": "chapter-1", "teaching_modules": []}],
        },
        "course_knowledge_base": {"revision_id": "legacy-kb-1", "lifecycle_status": "active"},
        "course_coherence_contract": {
            "revision_id": "legacy-coherence-1",
            "status": "active",
            "quality_report": {"passed": True},
        },
    }


@pytest.mark.asyncio
async def test_failed_v6_progress_event_atomically_terminates_the_outer_task(
    tmp_path,
    monkeypatch,
) -> None:
    import task_manager as task_manager_module
    from task_manager import TaskManager

    course = _canonical_course()
    storage = MemoryStorage(course, tmp_path)
    monkeypatch.setattr(task_manager_module, "TASKS_FILE", tmp_path / "jobs.json")
    manager = TaskManager(
        storage,
        course_service=None,
        ws_service=None,
        document_repository=CourseDocumentRepository(storage),
    )
    task_id = await manager.create_task(
        course["course_id"],
        "slide_deck_variant_build",
        enqueue=False,
        request_snapshot={"target_schema": "slide_deck_v6"},
    )
    await manager._update_task_status(task_id, "running")

    failure = {
        "stage": "story",
        "code": "story_ai_batch_failed",
        "message": "Provider response failed validation",
        "retryable": True,
        "chapter_id": "chapter-1",
        "page_id": "",
        "batch_id": "story-1",
    }
    progress = {
        "schema_version": "slide_build_progress_v2",
        "status": "failed",
        "percent": 41,
        "stage": "story",
        "failure": failure,
    }
    await manager._record_representation_event(task_id, {
        "event": "slide_build_progress_v2",
        "progress": 41,
        "stage": "story",
        "message": "V6 build failed",
        "slide_build_progress_v2": progress,
    })

    task = manager.get_task(task_id)
    assert task["status"] == "failed"
    assert task["slide_build_progress_v2"] == progress
    assert task["error_detail"] == failure
    assert task["error"] == failure["message"]


@pytest.mark.asyncio
async def test_restart_recovers_only_the_newest_equivalent_v6_build(
    tmp_path,
    monkeypatch,
) -> None:
    import task_manager as task_manager_module
    from task_manager import TaskManager

    course = _canonical_course()
    storage = MemoryStorage(course, tmp_path)
    monkeypatch.setattr(task_manager_module, "TASKS_FILE", tmp_path / "jobs.json")
    manager = TaskManager(
        storage,
        course_service=None,
        ws_service=None,
        document_repository=CourseDocumentRepository(storage),
    )
    request = {
        "mode": "teaching",
        "theme": "qizhi-classroom",
        "target_schema": "slide_deck_v6",
        "template_selector": {"pack_id": "", "version": None},
    }
    old_id = await manager.create_task(
        course["course_id"],
        "slide_deck_variant_build",
        enqueue=False,
        request_snapshot=request,
    )
    new_id = await manager.create_task(
        course["course_id"],
        "slide_deck_variant_build",
        enqueue=False,
        request_snapshot=request,
    )
    manager.tasks[old_id]["status"] = "running"
    manager.tasks[new_id]["status"] = "running"

    assert await manager._reconcile_task_after_restart(old_id) is False
    assert manager.tasks[old_id]["status"] == "cancelled"
    assert manager.tasks[old_id]["error_detail"]["code"] == (
        "superseded_build_not_recovered"
    )
    assert await manager._reconcile_task_after_restart(new_id) is True
    assert manager.tasks[new_id]["status"] == "pending"


@pytest.mark.asyncio
async def test_v6_task_routes_to_the_single_v6_orchestrator_without_v5_fragmentation(
    tmp_path,
    monkeypatch,
) -> None:
    import task_manager as task_manager_module
    from task_manager import TaskManager

    course = _canonical_course()
    storage = MemoryStorage(course, tmp_path)
    monkeypatch.setattr(task_manager_module, "TASKS_FILE", tmp_path / "jobs.json")
    manager = TaskManager(
        storage,
        course_service=None,
        ws_service=None,
        document_repository=CourseDocumentRepository(storage),
    )
    task_id = await manager.create_task(
        course["course_id"],
        "slide_deck_variant_build",
        enqueue=False,
        request_snapshot={
            "mode": "teaching",
            "theme": "qizhi-classroom",
            "target_schema": "slide_deck_v6",
        },
    )
    captured: dict[str, object] = {}

    async def v6_runner(**kwargs) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(manager, "_process_slide_deck_variant_v6", v6_runner, raising=False)
    monkeypatch.setattr(
        task_manager_module,
        "fragment_course_document",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("V6 entered the legacy fragmentation path")
        ),
    )

    await manager._process_slide_deck_variant_task(task_id)

    assert captured["task_id"] == task_id
    assert captured["document"].course_id == course["course_id"]
    assert captured["course_view"]["course_teaching_plan"]["revision_id"] == "plan-rev-1"
    assert not any(
        event.get("event") == "fragmenting"
        for event in manager.tasks[task_id].get("event_history") or []
    )


@pytest.mark.asyncio
async def test_v6_shadow_task_can_read_a_legacy_projection_without_publishing(tmp_path, monkeypatch) -> None:
    import task_manager as task_manager_module
    from task_manager import TaskManager

    course = _legacy_course()
    storage = MemoryStorage(course, tmp_path)
    monkeypatch.setattr(task_manager_module, "TASKS_FILE", tmp_path / "jobs.json")
    manager = TaskManager(
        storage,
        course_service=None,
        ws_service=None,
        document_repository=CourseDocumentRepository(storage),
    )
    task_id = await manager.create_task(
        course["course_id"],
        "slide_deck_variant_build",
        enqueue=False,
        request_snapshot={
            "mode": "teaching",
            "theme": "qizhi-classroom",
            "target_schema": "slide_deck_v6",
            "shadow_only": True,
            "chapter_id": "chapter-1",
        },
    )
    captured: dict[str, object] = {}

    async def v6_runner(**kwargs) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(manager, "_process_slide_deck_variant_v6", v6_runner, raising=False)

    await manager._process_slide_deck_variant_task(task_id)

    assert captured["publish_result"] is False
    assert captured["shadow_context"]["source_format"] == "legacy_projection"
    assert captured["shadow_context"]["chapter_id"] == "chapter-1"
    assert {section.section_id for section in captured["document"].sections} == {
        "chapter-1",
        "lesson-1",
    }


@pytest.mark.asyncio
async def test_v6_task_uses_shared_ai_planners_and_publishes_the_v6_contract(
    tmp_path,
    monkeypatch,
) -> None:
    import task_manager as task_manager_module
    from task_manager import TaskManager

    course = _canonical_course()
    storage = MemoryStorage(course, tmp_path)
    representations = TeachingRepresentationRepository(tmp_path / "representations")
    monkeypatch.setattr(task_manager_module, "TASKS_FILE", tmp_path / "jobs.json")
    monkeypatch.setattr(
        task_manager_module,
        "teaching_representation_repository",
        representations,
    )

    async def story_planner(request: dict) -> dict:
        pages = []
        for index, unit in enumerate(request["teaching_units"], start=1):
            pages.append({
                "page_id": f"page-{index}",
                "teaching_unit_id": unit["teaching_unit_id"],
                "template_layout_id": unit["allowed_template_layout_ids"][0],
                "title": "Record a complete observation",
                "summary": "",
                "source_block_ids": unit["primary_block_ids"],
            })
        return {
            "schema_version": "slide_story_batch_response_v3",
            "chapter_id": request["chapter_id"],
            "provider": "shared-pool-fixture",
            "model": "story-fixture",
            "attempts": 1,
            "pages": pages,
        }

    async def visual_planner(request: dict) -> dict:
        return {
            "schema_version": "slide_visual_batch_response_v2",
            "provider": "shared-pool-fixture",
            "model": "visual-fixture",
            "attempts": 1,
            "decisions": [{
                "page_id": page["page_id"],
                "decision": "text_native",
                "source_block_ids": page["source_block_ids"],
                "resolved_template_layout_id": page["template_layout_id"],
            } for page in request["pages"]],
        }

    monkeypatch.setattr(
        task_manager_module,
        "build_ai_base_story_planner_v6",
        lambda: story_planner,
    )
    monkeypatch.setattr(
        task_manager_module,
        "build_ai_base_visual_planner_v2",
        lambda: visual_planner,
    )
    manager = TaskManager(
        storage,
        course_service=None,
        ws_service=None,
        document_repository=CourseDocumentRepository(storage),
    )
    task_id = await manager.create_task(
        course["course_id"],
        "slide_deck_variant_build",
        enqueue=False,
        request_snapshot={
            "mode": "teaching",
            "theme": "qizhi-classroom",
            "target_schema": "slide_deck_v6",
        },
    )

    await manager._run_job(task_id)

    task = manager.get_task(task_id)
    assert task["status"] == "completed"
    assert task["slide_build_progress_v2"]["published"] is True
    assert task["result"]["build"]["candidate_status"] == "v6_ready"
    registry = representations.load(course["course_id"])
    representation = next(item for item in registry.representations if item.variant_key == "teaching:qizhi-classroom")
    spec = next(item for item in registry.specs if item.spec_id == representation.spec_id)
    assert spec.payload["content"]["schema_version"] == "slide_deck_v6"
    assert spec.payload["content"]["story_plan"]["batches"][0]["provider"] == "shared-pool-fixture"
