"""Non-destructive legacy-course upgrade into the teacher lecture model.

The upgrade has two deliberately separate phases:

* ``preview`` only reads the source course and returns a deterministic mapping.
* ``publish`` recompiles in memory, validates the complete candidate, and writes
  the new course once.  The legacy course is never a write target.

The published course itself is the durable idempotency receipt.  A stable
upgrade id derives the new course id, so retries cannot create duplicate
courses or require a second state store.
"""

from __future__ import annotations

import asyncio
import inspect
import threading
from collections.abc import Iterable
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from course_document import (
    CourseDocument,
    course_view_from_document,
    document_from_legacy_course,
    refresh_document_revision,
    stable_hash,
)
from course_repository import CourseDocumentConflict, CourseDocumentRepository

UPGRADE_REPORT_SCHEMA = "teacher_course_upgrade_report_v1"
UPGRADE_SOURCE_FORMAT = "legacy_chapter_section_v1"

_PUBLISH_LOCKS: dict[tuple[int, str], asyncio.Lock] = {}
_PUBLISH_LOCKS_GUARD = threading.Lock()

_SAFE_METADATA_FIELDS = {
    "academic_year",
    "course_profile",
    "discipline",
    "english_name",
    "generation_request",
    "subject",
    "subject_pedagogy_profile",
    "target_audience",
    "term",
}

_LEGACY_HISTORY_FIELDS = {
    "course_document_migration",
    "course_document_publication",
    "course_operation_log",
    "course_revision_vector",
    "current_course_version_id",
    "generation_error",
    "generation_job_id",
    "generation_quality_report",
    "generation_status",
    "lesson_authoring",
    "lesson_plans",
    "ppt_assets",
    "teacher_lesson_authoring",
    "teacher_scripts",
    "teaching_plan",
}


def _upgrade_source_checksum(course_data: dict[str, Any]) -> str:
    """Bind confirmation and idempotency to every candidate-shaping input."""
    source = {
        "course_id": course_data.get("course_id"),
        "course_name": course_data.get("course_name"),
        "owner_id": course_data.get("owner_id"),
        "authoring_surface": course_data.get("authoring_surface"),
        "authoring_structure_version": course_data.get("authoring_structure_version"),
        "course_plan_authoring_structure_version": (
            (course_data.get("course_plan") or {}).get("authoring_structure_version")
        ),
        "course_schema_version": course_data.get("course_schema_version"),
        "course_document_revision": course_data.get("course_document_revision"),
        "nodes": course_data.get("nodes") or [],
        "copied_metadata": {
            key: deepcopy(course_data.get(key))
            for key in sorted(_SAFE_METADATA_FIELDS)
            if key in course_data
        },
    }
    return stable_hash(source, prefix="tcus_")


class TeacherCourseUpgradeError(RuntimeError):
    """Stable, report-carrying failure for a safe retry or correction."""

    def __init__(self, code: str, message: str, *, report: dict[str, Any]) -> None:
        super().__init__(message)
        self.code = code
        self.report = deepcopy(report)


@dataclass(frozen=True)
class _LegacyNode:
    node_id: str
    parent_node_id: str
    position: int
    value: dict[str, Any]


def _iter_nodes(
    nodes: object,
    *,
    inherited_parent_id: str = "root",
) -> Iterable[tuple[dict[str, Any], str]]:
    if not isinstance(nodes, list):
        return
    for item in nodes:
        if not isinstance(item, dict):
            continue
        explicit_parent = str(item.get("parent_node_id") or "").strip()
        parent_id = explicit_parent or inherited_parent_id
        yield item, parent_id
        yield from _iter_nodes(
            item.get("children"),
            inherited_parent_id=str(item.get("node_id") or parent_id),
        )


def _has_visible_content(node: dict[str, Any]) -> bool:
    if str(node.get("node_content") or "").strip():
        return True
    return any(
        isinstance(block, dict)
        and bool(str(block.get("content") or block.get("markdown") or "").strip())
        for block in (node.get("content_blocks") or [])
    )


def _lesson_title(index: int, source_title: str) -> str:
    title = _lesson_subject(index, source_title)
    return f"第{index}讲 {title}".strip()


def _lesson_subject(index: int, source_title: str) -> str:
    title = str(source_title or "").strip() or f"历史内容 {index}"
    prefixes = (
        f"第{index}章",
        f"第 {index} 章",
        f"第{index}讲",
        f"第 {index} 讲",
    )
    for prefix in prefixes:
        if title.startswith(prefix):
            title = title[len(prefix):].lstrip(" ：:-—")
            break
    return title


def _section_node(
    source: _LegacyNode,
    *,
    lesson_index: int,
    section_index: int,
    lesson_id: str,
) -> dict[str, Any]:
    section_id = f"L2-{lesson_index}-{section_index}"
    value = source.value
    blocks: list[dict[str, Any]] = []
    for block_index, block in enumerate(value.get("content_blocks") or [], start=1):
        if not isinstance(block, dict):
            continue
        copied = deepcopy(block)
        copied["block_id"] = f"{section_id}-block-{block_index}"
        copied.pop("parent_block_id", None)
        blocks.append(copied)
    return {
        "node_id": section_id,
        "parent_node_id": lesson_id,
        "node_name": str(value.get("node_name") or value.get("title") or "未命名小节"),
        "node_level": 2,
        "node_content": str(value.get("node_content") or ""),
        "content_blocks": blocks,
        "node_type": "imported_legacy_content",
        "learning_objective": str(value.get("learning_objective") or ""),
        "objective_id": str(value.get("objective_id") or ""),
        "objective_revision_id": str(value.get("objective_revision_id") or ""),
        "generation_status": "completed" if _has_visible_content(value) else "pending",
        "generated_chars": len(str(value.get("node_content") or "")),
        "error_summary": None,
        "legacy_source_node_id": source.node_id,
    }


def _report_core(
    *,
    source_course_id: str,
    source_checksum: str,
    target_owner_id: str,
    upgrade_key: str,
    proposed_course_id: str,
    mappings: list[dict[str, Any]],
    blockers: list[dict[str, str]],
    warnings: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "schema_version": UPGRADE_REPORT_SCHEMA,
        "source_format": UPGRADE_SOURCE_FORMAT,
        "source_course_id": source_course_id,
        "source_checksum": source_checksum,
        "target_owner_id": target_owner_id,
        "upgrade_key": upgrade_key,
        "proposed_course_id": proposed_course_id,
        "eligible": not blockers,
        "lesson_mappings": mappings,
        "blockers": blockers,
        "warnings": warnings,
    }


def preview_legacy_course_upgrade(
    course_data: dict[str, Any],
    *,
    owner_id: str = "",
    upgrade_key: str = "default",
) -> dict[str, Any]:
    """Return a deterministic, side-effect-free upgrade report."""
    source = deepcopy(course_data)
    source_course_id = str(source.get("course_id") or "").strip()
    source_checksum = _upgrade_source_checksum(source)
    target_owner_id = str(owner_id or source.get("owner_id") or "").strip()
    normalized_key = str(upgrade_key or "default").strip() or "default"
    upgrade_id = stable_hash(
        {
            "source_course_id": source_course_id,
            "source_checksum": source_checksum,
            "target_owner_id": target_owner_id,
            "upgrade_key": normalized_key,
        },
        prefix="tcu_",
    )
    proposed_course_id = stable_hash(upgrade_id, prefix="course_")
    blockers: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    if not source_course_id:
        blockers.append({"code": "source_course_id_missing", "message": "历史课程缺少课程 ID。"})
    if not target_owner_id:
        blockers.append({"code": "target_owner_id_missing", "message": "复制升级需要明确的新课程教师身份。"})
    if (
        source.get("authoring_structure_version") == "lecture_v1"
        or (source.get("course_plan") or {}).get("authoring_structure_version") == "lecture_v1"
    ):
        blockers.append({"code": "source_already_lecture_v1", "message": "当前课程已经是讲次式课程。"})
    flattened = list(_iter_nodes(source.get("nodes") or []))
    seen: set[str] = set()
    ordered: list[_LegacyNode] = []
    for position, (node, parent_id) in enumerate(flattened):
        node_id = str(node.get("node_id") or "").strip()
        if not node_id:
            blockers.append({"code": "source_node_id_missing", "message": f"第 {position + 1} 个历史节点缺少 ID。"})
            continue
        if node_id in seen:
            blockers.append({"code": "source_node_id_duplicate", "message": f"历史节点 ID 重复：{node_id}"})
            continue
        seen.add(node_id)
        ordered.append(_LegacyNode(node_id, parent_id, position, deepcopy(node)))

    known_ids = {item.node_id for item in ordered}
    for item in ordered:
        if item.parent_node_id not in {"", "root", "None"} and item.parent_node_id not in known_ids:
            blockers.append({
                "code": "source_parent_missing",
                "message": f"历史节点 {item.node_id} 的父节点不存在：{item.parent_node_id}",
            })

    children: dict[str, list[_LegacyNode]] = {}
    for item in ordered:
        children.setdefault(item.parent_node_id, []).append(item)

    def descendants(root: _LegacyNode) -> list[_LegacyNode]:
        result: list[_LegacyNode] = []
        visiting: set[str] = set()

        def visit(item: _LegacyNode) -> None:
            if item.node_id in visiting:
                blockers.append({"code": "source_cycle", "message": f"历史节点形成循环：{item.node_id}"})
                return
            visiting.add(item.node_id)
            for child in children.get(item.node_id, []):
                result.append(child)
                visit(child)
            visiting.remove(item.node_id)

        visit(root)
        return result

    parent_by_id = {item.node_id: item.parent_node_id for item in ordered}
    for item in ordered:
        path: set[str] = set()
        current_id = item.node_id
        while current_id in parent_by_id:
            if current_id in path:
                blockers.append({
                    "code": "source_cycle",
                    "message": f"历史节点形成循环：{current_id}",
                })
                break
            path.add(current_id)
            parent_id = parent_by_id[current_id]
            if parent_id in {"", "root", "None"}:
                break
            current_id = parent_id

    roots = [item for item in ordered if item.parent_node_id in {"", "root", "None"}]
    if not roots:
        blockers.append({"code": "source_lessons_empty", "message": "历史课程没有可映射的顶层章节。"})

    mappings: list[dict[str, Any]] = []
    visible_content_count = 0
    for lesson_index, root in enumerate(roots, start=1):
        source_sections = descendants(root)
        if _has_visible_content(root.value):
            source_sections.insert(0, root)
        if not source_sections:
            source_sections = [root]
        if not any(_has_visible_content(item.value) for item in source_sections):
            blockers.append({
                "code": "source_lesson_content_empty",
                "message": f"{root.value.get('node_name') or root.node_id} 没有正文，请先补全后再升级。",
            })
        visible_content_count += sum(_has_visible_content(item.value) for item in source_sections)
        lesson_id = f"L1-{lesson_index}"
        source_title = str(root.value.get("node_name") or root.value.get("title") or "")
        mappings.append({
            "lesson_unit_id": lesson_id,
            "title": _lesson_subject(lesson_index, source_title),
            "lesson_title": _lesson_title(lesson_index, source_title),
            "learning_objective": str(root.value.get("learning_objective") or ""),
            "position": lesson_index - 1,
            "source_node_ids": [item.node_id for item in source_sections],
            "sections": [
                {
                    "section_id": f"L2-{lesson_index}-{section_index}",
                    "source_node_id": item.node_id,
                    "title": str(item.value.get("node_name") or item.value.get("title") or "未命名小节"),
                    "position": section_index - 1,
                }
                for section_index, item in enumerate(source_sections, start=1)
            ],
        })
    if roots and visible_content_count == 0:
        blockers.append({"code": "source_content_empty", "message": "历史课程没有可发布的正文内容。"})

    core = _report_core(
        source_course_id=source_course_id,
        source_checksum=source_checksum,
        target_owner_id=target_owner_id,
        upgrade_key=normalized_key,
        proposed_course_id=proposed_course_id,
        mappings=mappings,
        blockers=blockers,
        warnings=warnings,
    )
    core["upgrade_id"] = upgrade_id
    core["report_id"] = stable_hash(core, prefix="tcur_")
    return core


class TeacherCourseUpgradeService:
    def __init__(self, storage_obj: Any) -> None:
        self.storage = storage_obj
        self.repository = CourseDocumentRepository(storage_obj)

    def _load_source(self, source_course_id: str) -> dict[str, Any]:
        # Canonical chapter-style courses no longer persist legacy ``nodes``.
        # Rebuild the compatibility view in memory so they can still be copied
        # into the lecture model without mutating their authoritative document.
        # Retired blocks are intentionally excluded so deleted content can
        # never be revived by the compatibility projection.
        source = self.repository.load_raw(source_course_id)
        if self.repository.is_canonical(source):
            document = CourseDocument.model_validate(source["course_document"])
            active_document = document.model_copy(deep=True)
            active_document.blocks = [
                block for block in active_document.blocks
                if block.status != "retired"
            ]
            source = course_view_from_document(source, active_document)
        # The oldest one-file migration assigned identity through the filename
        # without backfilling ``course_id`` inside JSON.  Use that stable
        # repository identity for compilation without writing it to the source.
        source.setdefault("course_id", source_course_id)
        return source

    def preview(
        self,
        source_course_id: str,
        *,
        owner_id: str,
        upgrade_key: str = "default",
    ) -> dict[str, Any]:
        source = self._load_source(source_course_id)
        return preview_legacy_course_upgrade(
            source,
            owner_id=owner_id,
            upgrade_key=upgrade_key,
        )

    def _compile_candidate(
        self,
        source: dict[str, Any],
        report: dict[str, Any],
        *,
        owner_id: str,
    ) -> dict[str, Any]:
        if _upgrade_source_checksum(source) != report["source_checksum"]:
            raise TeacherCourseUpgradeError(
                "source_checksum_changed",
                "历史课程在预检后发生变化，请重新预检。",
                report=report,
            )
        if not report.get("eligible"):
            raise TeacherCourseUpgradeError(
                "upgrade_preflight_blocked",
                "历史课程未通过升级预检。",
                report=report,
            )

        source_nodes = {
            item.node_id: item
            for item in (
                _LegacyNode(
                    str(node.get("node_id") or ""),
                    parent_id,
                    position,
                    deepcopy(node),
                )
                for position, (node, parent_id) in enumerate(_iter_nodes(source.get("nodes") or []))
            )
            if item.node_id
        }
        new_nodes: list[dict[str, Any]] = []
        chapters: list[dict[str, Any]] = []
        for mapping in report.get("lesson_mappings") or []:
            lesson_id = str(mapping.get("lesson_unit_id") or "")
            lesson_title = str(mapping.get("lesson_title") or "")
            lesson_position = int(mapping.get("position") or 0)
            new_nodes.append({
                "node_id": lesson_id,
                "parent_node_id": "root",
                "node_name": lesson_title,
                "node_level": 1,
                "node_content": "",
                "content_blocks": [],
                "node_type": "imported_legacy_lesson",
                "generation_status": "completed",
                "generated_chars": 0,
                "error_summary": None,
            })
            chapter_sections: list[dict[str, Any]] = []
            for section_index, section in enumerate(mapping.get("sections") or [], start=1):
                source_node_id = str(section.get("source_node_id") or "")
                source_node = source_nodes.get(source_node_id)
                if source_node is None:
                    raise TeacherCourseUpgradeError(
                        "mapping_source_missing",
                        f"迁移映射引用了不存在的历史节点：{source_node_id}",
                        report=report,
                    )
                compiled = _section_node(
                    source_node,
                    lesson_index=lesson_position + 1,
                    section_index=section_index,
                    lesson_id=lesson_id,
                )
                new_nodes.append(compiled)
                chapter_sections.append({
                    "section_number": f"{lesson_position + 1}.{section_index}",
                    "node_id": compiled["node_id"],
                    "title": compiled["node_name"],
                    "content_summary": str(source_node.value.get("content_summary") or ""),
                    "learning_objective": compiled["learning_objective"],
                })
            chapters.append({
                "chapter_number": lesson_position + 1,
                "lesson_unit_id": lesson_id,
                "title": str(mapping.get("title") or lesson_title),
                "learning_objective": str(mapping.get("learning_objective") or ""),
                "sections": chapter_sections,
            })

        course_id = str(report["proposed_course_id"])
        course_name = str(source.get("course_name") or "未命名课程")
        draft = {
            "course_id": course_id,
            "course_name": course_name,
            "nodes": new_nodes,
        }
        document = refresh_document_revision(document_from_legacy_course(draft))
        self._validate_candidate(document, new_nodes, report)

        metadata = {
            key: deepcopy(value)
            for key, value in source.items()
            if key in _SAFE_METADATA_FIELDS and key not in _LEGACY_HISTORY_FIELDS
        }
        now = datetime.now(timezone.utc).isoformat()
        metadata.update({
            "course_id": course_id,
            "course_name": course_name,
            "owner_id": owner_id,
            "authoring_surface": "teacher",
            "authoring_structure_version": "lecture_v1",
            "course_status": "ready",
            "generation_job_id": "",
            "generation_status": "passed",
            "created_at": now,
            "updated_at": now,
            "course_plan": {
                "schema_version": "course_plan_v1",
                "authoring_structure_version": "lecture_v1",
                "course_title": course_name,
                "chapters": chapters,
            },
            "course_outline": {
                "schema_version": "course_plan_v1",
                "authoring_structure_version": "lecture_v1",
                "course_title": course_name,
                "chapters": deepcopy(chapters),
            },
            "course_upgrade": deepcopy(report),
            "course_document_publication": {
                "source_format": UPGRADE_SOURCE_FORMAT,
                "source_course_id": report["source_course_id"],
                "source_checksum": report["source_checksum"],
                "upgrade_id": report["upgrade_id"],
                "section_count": len(document.sections),
                "block_count": len(document.blocks),
                "published_at": now,
            },
        })
        return self.repository._canonical_storage_envelope(metadata, document)

    @staticmethod
    def _validate_candidate(
        document: CourseDocument,
        nodes: list[dict[str, Any]],
        report: dict[str, Any],
    ) -> None:
        validated = CourseDocument.model_validate(document.model_dump(mode="json"))
        if validated.course_id != report.get("proposed_course_id"):
            raise TeacherCourseUpgradeError(
                "candidate_course_id_mismatch",
                "新课程身份校验失败。",
                report=report,
            )
        node_ids = [str(node.get("node_id") or "") for node in nodes]
        if len(node_ids) != len(set(node_ids)):
            raise TeacherCourseUpgradeError(
                "candidate_node_id_duplicate",
                "新课程讲次或小节 ID 重复。",
                report=report,
            )
        lesson_ids = {
            str(node.get("node_id") or "")
            for node in nodes
            if int(node.get("node_level") or 0) == 1
            and str(node.get("parent_node_id") or "root") in {"", "root"}
        }
        if not lesson_ids:
            raise TeacherCourseUpgradeError(
                "candidate_lessons_empty",
                "新课程没有合法讲次。",
                report=report,
            )
        for lesson_id in lesson_ids:
            sections = [
                node for node in nodes
                if int(node.get("node_level") or 0) == 2
                and str(node.get("parent_node_id") or "") == lesson_id
            ]
            if not sections:
                raise TeacherCourseUpgradeError(
                    "candidate_lesson_sections_empty",
                    f"讲次 {lesson_id} 没有合法小节。",
                    report=report,
                )
            section_ids = {str(node.get("node_id") or "") for node in sections}
            visible_blocks = [
                block
                for block in validated.blocks
                if block.section_id in section_ids
                and block.status != "retired"
                and bool(str(block.payload.get("markdown") or block.payload.get("text") or "").strip())
            ]
            if not visible_blocks:
                raise TeacherCourseUpgradeError(
                    "candidate_lesson_content_empty",
                    f"讲次 {lesson_id} 没有可发布的正文内容。",
                    report=report,
                )
        if not validated.blocks:
            raise TeacherCourseUpgradeError(
                "candidate_content_empty",
                "新课程没有可发布的正文内容。",
                report=report,
            )
        block_ids = [block.block_id for block in validated.blocks]
        if len(block_ids) != len(set(block_ids)):
            raise TeacherCourseUpgradeError(
                "candidate_block_id_duplicate",
                "新课程正文块 ID 重复。",
                report=report,
            )

    async def publish(
        self,
        source_course_id: str,
        *,
        expected_source_checksum: str,
        owner_id: str,
        upgrade_key: str = "default",
    ) -> dict[str, Any]:
        report = self.preview(
            source_course_id,
            owner_id=owner_id,
            upgrade_key=upgrade_key,
        )
        if report["source_checksum"] != expected_source_checksum:
            raise TeacherCourseUpgradeError(
                "source_checksum_changed",
                "历史课程与已确认的预检版本不一致，请重新预检。",
                report=report,
            )
        lock = await self._publish_lock(str(report["upgrade_id"]))
        async with lock:
            source = self._load_source(source_course_id)
            existing = self.storage.load_course(str(report["proposed_course_id"]))
            if existing:
                return self._idempotent_result(existing, report)
            candidate = self._compile_candidate(source, report, owner_id=owner_id)
            course_id = str(report["proposed_course_id"])
            try:
                create_if_absent = getattr(self.storage, "create_course_if_absent", None)
                if create_if_absent is None:
                    raise RuntimeError("Storage does not support atomic course creation")
                result = create_if_absent(course_id, candidate)
                if inspect.isawaitable(result):
                    result = await result
                if result is False:
                    persisted = self.storage.load_course(course_id)
                    return self._idempotent_result(persisted, report)
            except Exception as exc:
                persisted = self.storage.load_course(course_id)
                if persisted:
                    try:
                        return self._idempotent_result(persisted, report)
                    except CourseDocumentConflict:
                        if str((persisted.get("course_upgrade") or {}).get("upgrade_id") or "") == report["upgrade_id"]:
                            try:
                                self.storage.delete_course(course_id)
                            except Exception as cleanup_exc:
                                raise TeacherCourseUpgradeError(
                                    "upgrade_cleanup_failed",
                                    "升级发布失败，未发布工作区清理失败；请联系管理员后重试。",
                                    report=report,
                                ) from cleanup_exc
                raise TeacherCourseUpgradeError(
                    "upgrade_publish_failed",
                    "升级未发布，旧课程保持不变；可以使用同一预检报告安全重试。",
                    report=report,
                ) from exc
            return self._success_result(candidate, report, idempotent=False)

    @staticmethod
    def _success_result(
        course: dict[str, Any],
        report: dict[str, Any],
        *,
        idempotent: bool,
    ) -> dict[str, Any]:
        return {
            "status": "published",
            "course_id": str(course.get("course_id") or report["proposed_course_id"]),
            "source_course_id": report["source_course_id"],
            "source_checksum": report["source_checksum"],
            "document_revision": str(course.get("course_document_revision") or ""),
            "idempotent": idempotent,
            "migration_report": deepcopy(report),
        }

    def _idempotent_result(
        self,
        existing: dict[str, Any],
        report: dict[str, Any],
    ) -> dict[str, Any]:
        upgrade = existing.get("course_upgrade") or {}
        if (
            str(upgrade.get("upgrade_id") or "") != report["upgrade_id"]
            or str(upgrade.get("source_checksum") or "") != report["source_checksum"]
            or str(existing.get("course_id") or "") != report["proposed_course_id"]
            or str(existing.get("owner_id") or "") != report["target_owner_id"]
            or str(existing.get("authoring_structure_version") or "") != "lecture_v1"
        ):
            raise CourseDocumentConflict("Upgrade course ID is already occupied")
        try:
            CourseDocument.model_validate(existing.get("course_document"))
        except Exception as exc:
            raise CourseDocumentConflict("Existing upgrade result is invalid") from exc
        return self._success_result(existing, report, idempotent=True)

    async def _publish_lock(self, upgrade_id: str) -> asyncio.Lock:
        key = (id(self.storage), upgrade_id)
        with _PUBLISH_LOCKS_GUARD:
            return _PUBLISH_LOCKS.setdefault(key, asyncio.Lock())


__all__ = [
    "TeacherCourseUpgradeError",
    "TeacherCourseUpgradeService",
    "preview_legacy_course_upgrade",
]
