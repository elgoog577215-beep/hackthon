"""Canonical handout commits; authoring revisions become read-only references.

No model calls and no learner writes. Historical snapshots are immutable and
only used to resolve an old authoring revision or compensate a change.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from course_document import CourseDocument, document_from_generation_draft, document_from_legacy_course, refresh_document_revision
from course_repository import CourseDocumentConflict, _publish_course_revision
from course_revisions import revision_event_for_documents

SCHEMA = "unified_teacher_v1"


def unified(course: dict) -> bool:
    return course.get("teacher_production_schema") == SCHEMA


def _record_commit(raw: dict, old: CourseDocument, document: CourseDocument, command: str, affected: list[str]) -> None:
    document = refresh_document_revision(document)
    stamp = datetime.now(timezone.utc).isoformat()
    event = revision_event_for_documents(old, document, command_id=command,
        operation="commit_teacher_content", affected_block_ids=affected, created_at=stamp)
    receipt = {"command_id": command, "operation": "commit_teacher_content",
        "previous_revision": old.document_revision, "document_revision": document.document_revision,
        "affected_block_ids": affected, "committed_at": stamp,
        "revision_change": event.model_dump(mode="json")}
    raw.update(course_document=document.model_dump(mode="json"),
        course_document_revision=document.document_revision,
        current_course_version_id=document.document_revision,
        course_revision_vector=event.current.model_dump(mode="json"),
        course_document_authoritative=True, course_schema_version="course_document_v1")
    raw.pop("nodes", None)
    raw["course_operation_log"] = [*(raw.get("course_operation_log") or []),
        {"command_id": command, "operation": "commit_teacher_content", "receipt": receipt}][-200:]


def commit_outline(storage: Any, source: dict) -> dict:
    """Commit completed outline metadata and navigation, never model prose."""
    course_id = str(source["course_id"])
    def update(raw: dict) -> dict:
        if not unified(raw):
            return raw
        old = CourseDocument.model_validate(raw["course_document"])
        navigation = document_from_generation_draft({**source, "nodes": [
            {**n, "node_content": "", "content_blocks": []} for n in source.get("nodes") or []]})
        active = {s.section_id for s in navigation.sections}
        removed = {b.section_id for b in old.blocks if b.status != "retired"} - active
        if removed:
            raise CourseDocumentConflict("大纲移除了已有正文，请通过课程调整处理身份映射。")
        navigation.blocks = old.blocks
        navigation = refresh_document_revision(navigation)
        keys = ("course_plan", "course_outline", "course_teaching_plan", "course_knowledge_base",
            "course_knowledge_map", "course_knowledge_scope_contract", "course_coherence_contract",
            "subject_pedagogy_profile", "difficulty_profile", "course_composition_profile",
            "generation_request", "blueprint_revision_id", "course_outline_quality_report",
            "generation_stage_artifacts")
        for key in keys:
            if key in source:
                raw[key] = deepcopy(source[key])
        raw.update(outline_lifecycle_status="current", outline_generation_status="completed",
            outline_framework_only=False, generation_status="teacher_outline_ready")
        if navigation.model_dump() != old.model_dump() or not raw.get("teacher_outline_committed"):
            _record_commit(raw, old, navigation, "teacher-outline:" + str(source.get("blueprint_revision_id") or navigation.document_revision), [])
        raw["teacher_outline_committed"] = True
        return raw
    return storage.update_course_data(course_id, update)


def _sections(raw: dict, binding: dict) -> list[dict]:
    blocks = {b["block_id"]: b for b in (raw.get("course_document") or {}).get("blocks") or []}
    result = []
    for section in binding.get("sections") or []:
        item = deepcopy(section)
        item["blocks"] = []
        for block_id in item.pop("block_ids", []):
            block = blocks.get(block_id)
            if not block or block.get("status") == "retired":
                raise CourseDocumentConflict("讲义正文引用缺失")
            payload = block.get("payload") or {}
            item["blocks"].append({"block_id": block_id, "module_id": payload.get("module_id", ""),
                "role": block.get("role", "concept"), "title": payload.get("title", ""),
                "content": payload.get("markdown", ""), "knowledge_names": payload.get("knowledge_names") or [],
                "planned_minutes": payload.get("planned_minutes")})
        from teacher_script import teacher_script_blocks_to_markdown
        item["content"] = teacher_script_blocks_to_markdown(item["blocks"])
        result.append(item)
    return result


def hydrate_authoring(raw: dict, value: dict) -> dict:
    """Resolve references and repair projections after a post-commit interruption."""
    value = deepcopy(value)
    baselines = {}
    for lesson_id, binding in (raw.get("teacher_handouts") or {}).items():
        baselines[lesson_id] = binding["revision_id"]
        lesson = (value.get("lessons") or {}).get(lesson_id)
        if lesson is None:
            continue
        revisions = lesson.setdefault("script_revisions", [])
        for revision in revisions:
            if revision.get("canonical_ref"):
                rid = revision["revision_id"]
                if rid == binding["revision_id"]:
                    revision["sections"] = _sections(raw, binding)
                else:
                    historical = (raw.get("teacher_handout_history") or {}).get(lesson_id, {}).get(rid)
                    if historical is None:
                        raise CourseDocumentConflict("讲义历史引用缺失")
                    revision["sections"] = deepcopy(historical["sections"])
        current = next((r for r in revisions if r.get("revision_id") == binding["revision_id"]), None)
        if current is None:
            current = deepcopy(binding["revision_metadata"])
            current["sections"] = _sections(raw, binding)
            current["canonical_ref"] = True
            revisions.append(current)
        # Keep an explicitly saved invalid edit. Otherwise canonical is authority.
        draft = next((r for r in revisions if r.get("revision_id") == lesson.get("working_script_revision_id")), {})
        if not draft or (draft.get("publication_eligible") and not draft.get("commit_conflict")):
            lesson["working_script_revision_id"] = binding["revision_id"]
        lesson["current_content_revision_id"] = binding["revision_id"]
        lesson["document_revision"] = raw.get("course_document_revision", "")
    value["_canonical_baselines"] = baselines
    return value


def commit_authoring(storage: Any, value: dict) -> dict:
    """One shared save boundary for generation, edits, imports and candidate use."""
    course_id = value["course_id"]
    updates = []
    for lesson_id, lesson in (value.get("lessons") or {}).items():
        revision = next((r for r in lesson.get("script_revisions") or []
            if r.get("revision_id") == lesson.get("working_script_revision_id")), None)
        if not revision or not revision.get("publication_eligible") or revision.get("commit_conflict"):
            continue
        if revision.get("source_lesson_plan_revision_id") != lesson.get("working_revision_id") or lesson.get("source_state", "current") != "current":
            continue
        updates.append((lesson_id, revision))
    receipts = []
    def update(raw: dict) -> dict:
        if not unified(raw):
            return raw
        old = CourseDocument.model_validate(raw["course_document"])
        doc = old.model_copy(deep=True)
        bindings = raw.setdefault("teacher_handouts", {})
        affected = []
        committed = []
        for lesson_id, revision in updates:
            previous = bindings.get(lesson_id) or {}
            if previous.get("revision_id") == revision["revision_id"]:
                continue
            expected = (value.get("_canonical_baselines") or {}).get(lesson_id, "")
            if str(previous.get("revision_id") or "") != expected:
                raise CourseDocumentConflict("本讲正文已变化，请刷新后重试。")
            section_ids = {s.section_id for s in doc.sections if s.parent_section_id == lesson_id}
            given_ids = {str(s.get("section_node_id") or "") for s in revision["sections"]}
            if not section_ids or section_ids != given_ids:
                raise CourseDocumentConflict("讲义与正式大纲的讲次范围不一致")
            if previous:
                raw.setdefault("teacher_handout_history", {}).setdefault(lesson_id, {})[previous["revision_id"]] = {
                    "sections": _sections(raw, previous), "binding": deepcopy(previous)}
            nodes = []
            metadata_sections = []
            for section in revision["sections"]:
                source = next(s for s in doc.sections if s.section_id == section["section_node_id"])
                converted = []
                for b in section["blocks"]:
                    converted.append({"block_id": b["block_id"], "type": b.get("role", "concept"),
                        "title": b.get("title", ""), "content": b["content"], "metadata": {
                            "module_id": b.get("module_id"), "planned_minutes": b.get("planned_minutes"),
                            "role": b.get("role", "concept"), "objective_refs": [source.objective_id] if source.objective_id else [],
                            "evidence_refs": revision.get("material_asset_ids") or []}})
                nodes.append({"node_id": source.section_id, "node_name": source.title, "node_level": source.level,
                    "parent_node_id": lesson_id, "learning_objective": source.learning_objective,
                    "content_blocks": converted})
                metadata_sections.append({**{k: deepcopy(v) for k, v in section.items() if k not in {"content", "blocks"}},
                    "block_ids": [b["block_id"] for b in section["blocks"]]})
            fresh = document_from_legacy_course({"course_id": course_id, "course_name": doc.title, "nodes": nodes})
            ids = [b.block_id for b in fresh.blocks]
            foreign_ids = {b.block_id for b in doc.blocks if b.section_id not in section_ids}
            if len(ids) != len(set(ids)) or set(ids) & foreign_ids:
                raise CourseDocumentConflict("正文块标识重复或属于另一讲")
            if not previous and any(b.section_id in section_ids and b.status != "retired" and b.payload.get("markdown") for b in doc.blocks):
                old_content = [(b.block_id, b.payload.get("markdown")) for b in doc.blocks if b.section_id in section_ids and b.status != "retired"]
                if old_content != [(b.block_id, b.payload.get("markdown")) for b in fresh.blocks]:
                    raise CourseDocumentConflict("教师讲义与已有正式正文不同，需要处理迁移冲突")
            names = {b["block_id"]: b.get("knowledge_names") or [] for s in revision["sections"] for b in s["blocks"]}
            for b in fresh.blocks:
                b.payload["knowledge_names"] = names[b.block_id]
            removed = [b.model_copy(deep=True) for b in doc.blocks if b.section_id in section_ids and b.block_id not in ids]
            for b in removed:
                b.status = "retired"
            before_blocks = {b.block_id: b for b in doc.blocks if b.section_id in section_ids}
            fresh = refresh_document_revision(fresh)
            after_blocks = {b.block_id: b for b in fresh.blocks}
            affected.extend(bid for bid in before_blocks.keys() | after_blocks.keys()
                if bid not in before_blocks or bid not in after_blocks or before_blocks[bid].internal_revision != after_blocks[bid].internal_revision)
            doc.blocks = [b for b in doc.blocks if b.section_id not in section_ids] + fresh.blocks + removed
            bindings[lesson_id] = {"revision_id": revision["revision_id"],
                "source_lesson_plan_revision_id": revision["source_lesson_plan_revision_id"],
                "source_outline_revision_id": value.get("outline_revision_id", ""),
                "sections": metadata_sections,
                "revision_metadata": {k: deepcopy(v) for k, v in revision.items() if k not in {"sections", "canonical_ref"}}}
            committed.append(revision["revision_id"])
        if committed:
            # Reuse the course-local knowledge compiler with teacher plans and
            # canonical blocks. Only actual compiler identities become refs.
            from course_document import course_view_from_document
            from course_knowledge_base import compile_course_knowledge_base
            view = course_view_from_document(raw, doc)
            plans = {}
            for lesson in (value.get("lessons") or {}).values():
                plan = next((r.get("plan") or {} for r in lesson.get("revisions") or []
                    if r.get("revision_id") == lesson.get("working_revision_id")), {})
                plans.update({str(s.get("node_id") or ""): s for s in plan.get("sections") or []})
            for node in view.get("nodes") or []:
                plan_section = plans.get(node["node_id"])
                if plan_section:
                    for key in ("knowledge_structure", "knowledge_relations", "reused_knowledge_names"):
                        node[key] = deepcopy(plan_section.get(key) or [])
            knowledge = compile_course_knowledge_base(view)
            raw["course_knowledge_base"] = knowledge
            points = {p["name"]: p["knowledge_id"] for p in knowledge.get("knowledge_points") or []}
            for block in doc.blocks:
                if block.status == "retired":
                    continue
                refs = sorted({points[n] for n in block.payload.get("knowledge_names") or [] if n in points})
                if refs != block.concept_refs:
                    affected.append(block.block_id)
                    block.concept_refs = refs
            _record_commit(raw, old, doc, "teacher-handout:" + ":".join(committed), sorted(set(affected)))
            receipts.append(raw["course_operation_log"][-1]["receipt"])
        return raw
    result = storage.update_course_data(course_id, update)
    if getattr(storage, "emit_course_events", True):
        for receipt in receipts:
            _publish_course_revision(course_id, receipt)
    if not unified(result):
        return value
    compact = deepcopy(value)
    compact.pop("_canonical_baselines", None)
    for lesson_id, lesson in (compact.get("lessons") or {}).items():
        binding = (result.get("teacher_handouts") or {}).get(lesson_id) or {}
        for revision in lesson.get("script_revisions") or []:
            if revision.get("revision_id") == binding.get("revision_id") or revision.get("canonical_ref"):
                revision.pop("sections", None)
                revision["canonical_ref"] = True
    return compact
