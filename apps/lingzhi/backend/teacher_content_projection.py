"""Read-only presentation of the teacher-owned body. Never saves course data."""
from __future__ import annotations

import logging
from pathlib import Path
import time

from course_document import course_view_from_document

logger = logging.getLogger(__name__)


def authoring_repository(storage):
    from teacher_lesson_authoring import TeacherLessonAuthoringRepository
    from teacher_authoring_provider import get_teacher_lesson_authoring_repository
    registered = get_teacher_lesson_authoring_repository()
    if getattr(registered, "canonical_storage", None) is storage:
        return registered
    courses_dir = getattr(storage, "_courses_dir", None)
    if courses_dir is None:
        return registered
    return TeacherLessonAuthoringRepository(Path(courses_dir).parent / "teacher_lesson_authoring", canonical_storage=storage)


def project_teacher_content(raw, *, storage=None, authoring=None):
    if raw.get("authoring_surface") != "teacher" and raw.get("knowledge_first_workflow") not in {"knowledge_first_c17_v1", "knowledge_first_generic_v1"}:
        return raw
    started = time.monotonic()
    if authoring is None:
        if storage is None:
            from storage import storage
        # The owner keeps every plan, handout and PPT recovery snapshot. Reading
        # the current body must not deepcopy that entire history on every GET.
        # The projector only reads owner state and builds independent output.
        return authoring_repository(storage).read_projection(
            str(raw["course_id"]),
            lambda state: project_teacher_content(raw, storage=storage, authoring=state),
        )
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
    from teacher_content_view import project_teacher_content as project_view
    result = project_view(raw, authoring=authoring, source=source)
    logger.info("teacher_timing phase=projection elapsed_ms=%.3f", (time.monotonic() - started) * 1000)
    return result
