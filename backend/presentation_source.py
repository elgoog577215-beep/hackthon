"""Read-only projection from a Lingzhi course into a presentation snapshot."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

from course_document import CourseDocument, document_from_legacy_course
from course_versioning import blueprint_revision_id
from presentation_models import PresentationScope, SourceRef


SOURCE_SNAPSHOT_SCHEMA = "presentation-source/v1"


def project_presentation_source(
    course_data: dict[str, Any],
    scope: PresentationScope | dict[str, Any],
    *,
    course_id: str | None = None,
) -> tuple[dict[str, Any], SourceRef]:
    """Project one immutable, scoped snapshot without changing ``course_data``.

    Canonical ``course_document_v1`` input remains canonical.  Legacy node
    input is deterministically projected through the existing course document
    adapter so downstream presentation code has one block/section shape.
    """
    if not isinstance(course_data, dict):
        raise TypeError("course_data must be an object")
    original = deepcopy(course_data)
    scope_model = scope if isinstance(scope, PresentationScope) else PresentationScope.model_validate(scope)

    document, source_format = _course_document(original)
    resolved_course_id = str(course_id or document.course_id or original.get("course_id") or "")
    if not resolved_course_id:
        raise ValueError("course_id is required")
    if document.course_id and document.course_id != resolved_course_id:
        raise ValueError("course_id does not match course document")

    sections = [item.model_dump(mode="json") for item in document.sections]
    included_ids = _included_section_ids(sections, scope_model)
    scoped_sections = [item for item in sections if item["section_id"] in included_ids]
    scoped_blocks = [
        item.model_dump(mode="json")
        for item in document.blocks
        if item.section_id in included_ids and item.status != "retired"
    ]

    objective_ids = {
        str(section.get("objective_id") or "")
        for section in scoped_sections
        if section.get("objective_id")
    }
    for block in scoped_blocks:
        objective_ids.update(str(item) for item in block.get("objective_refs") or [] if item)
    objectives = _project_objectives(original, scoped_sections, objective_ids)

    learning_assets = original.get("learning_assets")
    if not isinstance(learning_assets, dict):
        learning_assets = {}
    questions = _filter_scoped_items(
        _list_values(learning_assets, "questions", fallback=original.get("questions")), included_ids
    )
    misconceptions = _filter_scoped_items(
        _list_values(learning_assets, "misconceptions", fallback=original.get("misconceptions")), included_ids
    )
    practices = _filter_scoped_items(
        _list_values(learning_assets, "practices", fallback=original.get("practices")) or questions,
        included_ids,
    )
    assets = _project_assets(learning_assets, included_ids, scoped_blocks)
    course_blueprint = _project_blueprint(original.get("course_blueprint"), included_ids)
    publication = _project_publication(original)

    source_identity = {
        "course_id": resolved_course_id,
        "source_format": source_format,
        "version_id": str(
            original.get("current_course_version_id")
            or original.get("version_id")
            or document.document_revision
            or "unversioned"
        ),
        "document_revision": str(
            original.get("course_document_revision")
            or document.document_revision
            or _short_hash(document.model_dump(mode="json"), "cdr_")
        ),
        "blueprint_revision_id": str(
            original.get("blueprint_revision_id")
            or blueprint_revision_id(original)
        ),
        "asset_bundle_revision_id": str(
            original.get("learning_asset_bundle_revision_id")
            or _short_hash(learning_assets, "lab_")
        ),
    }
    snapshot_body: dict[str, Any] = {
        "schema_version": SOURCE_SNAPSHOT_SCHEMA,
        **source_identity,
        "course_title": str(document.title or original.get("course_name") or "未命名课程"),
        "publication_allowed": publication["publication_allowed"],
        "is_published": publication["publication_allowed"],
        "publication": publication,
        "scope": scope_model.model_dump(mode="json"),
        "course_blueprint": course_blueprint,
        "sections": scoped_sections,
        "blocks": scoped_blocks,
        "objectives": objectives,
        "practices": practices,
        "questions": questions,
        "misconceptions": misconceptions,
        "assets": assets,
    }
    snapshot_id = f"pss_{_full_digest(snapshot_body)[:24]}"
    snapshot = {**snapshot_body, "source_snapshot_id": snapshot_id}
    digest = source_snapshot_sha256(snapshot)
    snapshot["source_snapshot_sha256"] = digest
    source_ref = SourceRef(
        **source_identity,
        source_snapshot_id=snapshot_id,
        source_snapshot_sha256=digest,
    )
    return snapshot, source_ref


def source_packet(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Return an isolated generation packet from a validated source snapshot."""
    validate_source_snapshot(snapshot)
    return deepcopy({
        "source_ref": {
            key: snapshot.get(key)
            for key in (
                "course_id", "source_format", "version_id", "document_revision",
                "blueprint_revision_id", "asset_bundle_revision_id",
                "source_snapshot_id", "source_snapshot_sha256",
            )
        },
        "course_title": snapshot.get("course_title"),
        "publication_allowed": snapshot.get("publication_allowed"),
        "is_published": snapshot.get("is_published"),
        "publication": snapshot.get("publication") or {},
        "scope": snapshot.get("scope"),
        "course_blueprint": snapshot.get("course_blueprint") or {},
        "sections": snapshot.get("sections") or [],
        "blocks": snapshot.get("blocks") or [],
        "objectives": snapshot.get("objectives") or [],
        "practices": snapshot.get("practices") or [],
        "questions": snapshot.get("questions") or [],
        "misconceptions": snapshot.get("misconceptions") or [],
        "assets": snapshot.get("assets") or [],
    })


def validate_source_snapshot(snapshot: dict[str, Any]) -> None:
    if not isinstance(snapshot, dict):
        raise ValueError("source snapshot must be an object")
    if snapshot.get("schema_version") != SOURCE_SNAPSHOT_SCHEMA:
        raise ValueError("unknown source snapshot schema")
    if snapshot.get("source_snapshot_sha256") != source_snapshot_sha256(snapshot):
        raise ValueError("source snapshot digest mismatch")
    section_ids = {
        str(item.get("section_id") or "")
        for item in snapshot.get("sections") or []
        if isinstance(item, dict)
    }
    for block in snapshot.get("blocks") or []:
        if not isinstance(block, dict) or str(block.get("section_id") or "") not in section_ids:
            raise ValueError("source snapshot contains an out-of-scope block")


def source_snapshot_sha256(snapshot: dict[str, Any]) -> str:
    payload = deepcopy(snapshot)
    payload.pop("source_snapshot_sha256", None)
    return f"sha256:{_full_digest(payload)}"


def _course_document(course: dict[str, Any]) -> tuple[CourseDocument, str]:
    direct = course if course.get("schema_version") == "course_document_v1" else None
    embedded = course.get("course_document") if isinstance(course.get("course_document"), dict) else None
    if direct or embedded:
        document = CourseDocument.model_validate(direct or embedded)
        return document, "canonical"
    return document_from_legacy_course(course), "legacy_snapshot"


def _included_section_ids(
    sections: list[dict[str, Any]], scope: PresentationScope
) -> set[str]:
    all_ids = {str(item.get("section_id") or "") for item in sections}
    if scope.type == "course":
        return all_ids
    requested = {str(item) for item in scope.section_ids if item}
    if not requested:
        raise ValueError("chapter scope requires section_ids")
    unknown = requested - all_ids
    if unknown:
        raise ValueError(f"unknown section ids: {', '.join(sorted(unknown))}")
    included = set(requested)
    changed = True
    while changed:
        changed = False
        for section in sections:
            section_id = str(section.get("section_id") or "")
            parent_id = str(section.get("parent_section_id") or "")
            if parent_id in included and section_id not in included:
                included.add(section_id)
                changed = True
    return included


def _project_objectives(
    course: dict[str, Any],
    sections: list[dict[str, Any]],
    objective_ids: set[str],
) -> list[dict[str, Any]]:
    objectives: list[dict[str, Any]] = []
    seen: set[str] = set()
    for section in sections:
        text = str(section.get("learning_objective") or "").strip()
        objective_id = str(section.get("objective_id") or "").strip()
        if text or objective_id:
            key = objective_id or f"section:{section['section_id']}"
            seen.add(key)
            objectives.append({
                "objective_id": key,
                "objective_revision_id": str(section.get("objective_revision_id") or ""),
                "section_id": section["section_id"],
                "text": text,
            })
    blueprint = course.get("course_blueprint") if isinstance(course.get("course_blueprint"), dict) else {}
    candidates: list[Any] = []
    for key in ("learning_objectives", "objectives"):
        value = blueprint.get(key)
        if isinstance(value, list):
            candidates.extend(value)
    for index, item in enumerate(candidates):
        if isinstance(item, dict):
            objective_id = str(item.get("objective_id") or item.get("id") or f"blueprint:{index}")
            section_id = str(item.get("section_id") or item.get("node_id") or "")
            if section_id and section_id not in {s["section_id"] for s in sections}:
                continue
            if objective_ids and objective_id not in objective_ids and not section_id:
                continue
            if objective_id not in seen:
                objectives.append(deepcopy(item))
                seen.add(objective_id)
        elif isinstance(item, str) and item.strip():
            objective_id = f"blueprint:{index}"
            if objective_id not in seen:
                objectives.append({"objective_id": objective_id, "section_id": "", "text": item.strip()})
                seen.add(objective_id)
    return objectives


def _filter_scoped_items(items: list[dict[str, Any]], section_ids: set[str]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in items:
        refs = _section_refs(item)
        if not refs or refs.intersection(section_ids):
            result.append(deepcopy(item))
    return result


def _project_assets(
    learning_assets: dict[str, Any],
    section_ids: set[str],
    blocks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    referenced = {
        str(asset_id)
        for block in blocks
        for asset_id in block.get("asset_refs") or []
        if asset_id
    }
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for asset_type, values in learning_assets.items():
        if asset_type in {"questions", "misconceptions", "practices"} or not isinstance(values, list):
            continue
        for index, value in enumerate(values):
            if not isinstance(value, dict):
                continue
            asset_id = str(
                value.get("asset_id") or value.get("id") or value.get("graph_id")
                or value.get("criterion_id") or f"{asset_type}:{index}"
            )
            refs = _section_refs(value)
            if refs and not refs.intersection(section_ids) and asset_id not in referenced:
                continue
            key = (str(asset_type), asset_id)
            if key in seen:
                continue
            result.append({"asset_type": str(asset_type), "asset_id": asset_id, "data": deepcopy(value)})
            seen.add(key)
    return result


def _project_publication(course: dict[str, Any]) -> dict[str, Any]:
    quality = course.get("generation_quality_report")
    if not isinstance(quality, dict):
        quality = course.get("quality") if isinstance(course.get("quality"), dict) else {}
    publication_receipt = (
        course.get("course_document_publication")
        if isinstance(course.get("course_document_publication"), dict)
        else {}
    )
    explicit = course.get("publication_allowed")
    if explicit is None:
        explicit = quality.get("publication_allowed")
    if explicit is None and "is_published" in course:
        explicit = course.get("is_published")
    if explicit is None and publication_receipt:
        explicit = True
    if explicit is None:
        generation_job_id = str(course.get("generation_job_id") or "")
        if generation_job_id:
            explicit = str(course.get("generation_status") or "") == "passed"
        else:
            # Existing imported courses without a generation job are treated as
            # published by Storage.list_courses; preserve that compatibility.
            explicit = True
    blocking = quality.get("blocking_issues")
    if not isinstance(blocking, list):
        blocking = []
    return {
        "publication_allowed": bool(explicit),
        "blocking_issues": deepcopy(blocking),
        "quality_status": str(quality.get("final_status") or quality.get("status") or ""),
        "publication_receipt": deepcopy(publication_receipt),
    }


def _project_blueprint(value: Any, section_ids: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    result = deepcopy(value)
    nodes = result.get("nodes")
    if isinstance(nodes, list):
        result["nodes"] = [
            item for item in nodes
            if isinstance(item, dict)
            and str(item.get("section_id") or item.get("node_id") or "") in section_ids
        ]
    return result


def _list_values(mapping: dict[str, Any], key: str, *, fallback: Any = None) -> list[dict[str, Any]]:
    value = mapping.get(key)
    if not isinstance(value, list):
        value = fallback if isinstance(fallback, list) else []
    return [deepcopy(item) for item in value if isinstance(item, dict)]


def _section_refs(item: dict[str, Any]) -> set[str]:
    refs: set[str] = set()
    for key in ("section_id", "node_id", "source_node_id"):
        value = item.get(key)
        if value:
            refs.add(str(value))
    for key in ("section_ids", "node_ids", "source_node_ids"):
        values = item.get(key)
        if isinstance(values, list):
            refs.update(str(value) for value in values if value)
    return refs


def _short_hash(value: Any, prefix: str) -> str:
    return f"{prefix}{_full_digest(value)[:24]}"


def _full_digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = [
    "SOURCE_SNAPSHOT_SCHEMA",
    "project_presentation_source",
    "source_packet",
    "source_snapshot_sha256",
    "validate_source_snapshot",
]
