"""Read-only presentation of the teacher-owned body. Never saves course data."""
from __future__ import annotations

from copy import deepcopy
import logging
from pathlib import Path
import time

from course_document import course_view_from_document, document_from_legacy_course, refresh_document_revision

logger = logging.getLogger(__name__)


def authoring_repository(storage):
    from teacher_lesson_authoring import TeacherLessonAuthoringRepository
    courses_dir = getattr(storage, "_courses_dir", None)
    if courses_dir is None:
        from dependencies import get_teacher_lesson_authoring_repository
        return get_teacher_lesson_authoring_repository()
    return TeacherLessonAuthoringRepository(Path(courses_dir).parent / "teacher_lesson_authoring", canonical_storage=storage)


def project_teacher_content(raw, *, storage=None, authoring=None):
    if raw.get("authoring_surface") != "teacher":
        return raw
    started = time.monotonic()
    if authoring is None:
        if storage is None:
            from storage import storage
        authoring = authoring_repository(storage).load(str(raw["course_id"]))
    source = course_view_from_document(raw, raw["course_document"]) if raw.get("course_document") else raw
    if not source.get("nodes") and raw.get("generation_job_id") and isinstance(getattr(storage, "_courses_dir", None), (str, Path)):
        from generation_workspace import GenerationWorkspaceRepository, GenerationWorkspaceNotFound
        from teacher_outline_source import has_complete_teacher_outline
        workspace_root = Path(storage._courses_dir).parent / "generation_workspaces"
        if workspace_root.exists():
            try:
                candidate = GenerationWorkspaceRepository(workspace_root).load_course(str(raw["generation_job_id"]))
            except GenerationWorkspaceNotFound:
                candidate = {}
            if candidate.get("course_id") == raw["course_id"] and has_complete_teacher_outline(candidate):
                source = candidate
    nodes = [{**deepcopy(n), "node_content": "", "content_blocks": []} for n in source.get("nodes") or []]
    by_id = {n["node_id"]: n for n in nodes}
    handouts = {}
    original_blocks = {}
    for lid, lesson in (authoring.get("lessons") or {}).items():
        revision = next((r for r in lesson.get("script_revisions") or []
                         if r.get("revision_id") == lesson.get("working_script_revision_id")), None)
        if not revision or not revision.get("publication_eligible") or lesson.get("source_state", "current") != "current":
            continue
        if revision.get("source_lesson_plan_revision_id") != lesson.get("working_revision_id"):
            continue
        for section in revision.get("sections") or []:
            node = by_id.get(section["section_node_id"])
            if node is None:
                from teacher_lesson_authoring import TeacherLessonAuthoringError
                raise TeacherLessonAuthoringError("lesson_source_changed", "讲义与当前大纲范围不一致。")
            node["content_blocks"] = [{
                "block_id": b["block_id"], "type": b.get("role", "concept"),
                "title": b.get("title", ""), "content": b.get("content", ""),
                "metadata": {key: deepcopy(b[key]) for key in ("module_id", "knowledge_names", "planned_minutes") if key in b},
            } for b in section.get("blocks") or []]
            original_blocks.update({b["block_id"]: b for b in section.get("blocks") or []})
        handouts[lid] = {"revision_id": revision["revision_id"],
                         "source_lesson_plan_revision_id": revision.get("source_lesson_plan_revision_id"),
                         "source_outline_revision_id": authoring.get("outline_revision_id", "")}
    document = document_from_legacy_course({**source, "nodes": nodes})
    for block in document.blocks:
        original = original_blocks[block.block_id]
        block.visibility_rule = deepcopy(original.get("visibility_rule") or {})
        block.status = original.get("status", "final")
        block.payload["knowledge_names"] = deepcopy(original.get("knowledge_names") or [])
    document = refresh_document_revision(document)
    result = {**raw, "course_document": document.model_dump(mode="json"),
              "course_document_revision": document.document_revision,
              "current_course_version_id": document.document_revision,
              "teacher_handouts": handouts}
    logger.info("teacher_timing phase=projection elapsed_ms=%.3f", (time.monotonic() - started) * 1000)
    return course_view_from_document(result, document)
