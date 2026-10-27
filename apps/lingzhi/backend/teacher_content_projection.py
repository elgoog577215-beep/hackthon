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
    from dependencies import get_teacher_lesson_authoring_repository
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
    nodes = [{**deepcopy(n), "node_content": "", "content_blocks": []} for n in source.get("nodes") or []]
    by_id = {n["node_id"]: n for n in nodes}
    handouts = {}
    original_blocks = {}
    plan_sections = []
    for lid, lesson in (authoring.get("lessons") or {}).items():
        revision = next((r for r in lesson.get("script_revisions") or []
                         if r.get("revision_id") == lesson.get("working_script_revision_id")), None)
        if not revision or not revision.get("publication_eligible") or lesson.get("source_state", "current") != "current":
            continue
        if revision.get("source_lesson_plan_revision_id") != lesson.get("working_revision_id"):
            continue
        plan_revision = next((r for r in lesson.get("revisions") or []
                              if r.get("revision_id") == lesson.get("working_revision_id")), {})
        planned = {s["node_id"]: s for s in (plan_revision.get("plan") or {}).get("sections") or [] if s.get("node_id")}
        for section in revision.get("sections") or []:
            node = by_id.get(section["section_node_id"])
            if node is None:
                from teacher_lesson_authoring import TeacherLessonAuthoringError
                raise TeacherLessonAuthoringError("lesson_source_changed", "讲义与当前大纲范围不一致。")
            if section["section_node_id"] in planned:
                section_plan = planned[section["section_node_id"]]
                plan_sections.append(section_plan)
                for key in ("knowledge_structure", "key_points", "reused_knowledge_names", "knowledge_relations"):
                    node[key] = deepcopy(section_plan.get(key) or [])
            node["content_blocks"] = [{
                "block_id": b["block_id"], "type": b.get("role", "concept"),
                "title": b.get("title", ""), "content": b.get("content", ""),
                "metadata": {"concept_refs": deepcopy(b.get("knowledge_names") or []), **{key: deepcopy(b[key]) for key in ("module_id", "knowledge_names", "planned_minutes", "content_type", "type_label", "answer_to", "knowledge_refs", "source_knowledge_revision", "source_terminology_revision", "answer_refs", "source_context_revision", "source_evidence_package_revision", "source_scope_revision") if key in b}},
            } for b in section.get("blocks") or []]
            original_blocks.update({b["block_id"]: b for b in section.get("blocks") or []})
        handouts[lid] = {"revision_id": revision["revision_id"],
                         "source_lesson_plan_revision_id": revision.get("source_lesson_plan_revision_id"),
                         "source_outline_revision_id": authoring.get("outline_revision_id", ""),
                         **{key: revision[key] for key in ("source_knowledge_revision", "source_terminology_revision", "source_document_revision", "source_context_revision", "source_evidence_package_revision", "source_scope_revision") if key in revision}}
    document = document_from_legacy_course({**source, "nodes": nodes})
    for block in document.blocks:
        original = original_blocks[block.block_id]
        block.visibility_rule = deepcopy(original.get("visibility_rule") or {})
        block.status = original.get("status", "final")
        block.payload["knowledge_names"] = deepcopy(original.get("knowledge_names") or [])
        if "knowledge_refs" in original:
            block.concept_refs = [r["knowledge_id"] for r in original["knowledge_refs"]]
            block.payload.setdefault("content_type", {"concept": "explanation", "reasoning": "derivation",
                "checkpoint": "exercise", "orientation": "introduction", "transfer": "example"}.get(block.role, block.role))
            for key in ("knowledge_refs", "source_knowledge_revision", "source_terminology_revision", "answer_refs"):
                block.payload[key] = deepcopy(original.get(key))
            for key in ("source_context_revision", "source_evidence_package_revision", "source_scope_revision"):
                if key in original:
                    block.payload[key] = original[key]
    document = refresh_document_revision(document)
    result = {**raw, "course_document": document.model_dump(mode="json"),
              "course_teaching_plan": overlay_lesson_plan_sections(source, plan_sections),
              "course_document_revision": document.document_revision,
              "current_course_version_id": document.document_revision,
              "teacher_handouts": handouts}
    logger.info("teacher_timing phase=projection elapsed_ms=%.3f", (time.monotonic() - started) * 1000)
    return course_view_from_document(result, document)
