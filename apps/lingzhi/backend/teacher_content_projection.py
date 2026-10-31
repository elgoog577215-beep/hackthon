"""Read-only presentation of the teacher-owned body. Never saves course data."""
from __future__ import annotations

from copy import deepcopy
import logging
from pathlib import Path
import time

from course_document import course_view_from_document, document_from_legacy_course, refresh_document_revision
from course_teaching_plan_projection import overlay_lesson_plan_sections

logger = logging.getLogger(__name__)


def _working_authoring_source(value):
    """Copy only revisions consumed by this read-only body projection."""
    lessons={}
    for lid,lesson in (value.get('lessons')or{}).items():
        if not isinstance(lesson,dict):continue
        current={key:deepcopy(lesson[key])for key in ('source_state','working_revision_id','working_script_revision_id')if key in lesson}
        for collection,identity in (('script_revisions','working_script_revision_id'),('revisions','working_revision_id')):
            revision=next((r for r in lesson.get(collection)or[] if r.get('revision_id')==lesson.get(identity)),None)
            current[collection]=[deepcopy(revision)]if revision else []
        lessons[lid]=current
    return {'outline_revision_id':value.get('outline_revision_id',''),'lessons':lessons}


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
        repository=authoring_repository(storage)
        authoring=repository.read_projection(str(raw['course_id']),_working_authoring_source)
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
    result=project_view(raw,authoring=authoring,source=source)
    logger.info("teacher_timing phase=projection elapsed_ms=%.3f", (time.monotonic() - started) * 1000)
    return result
