"""Compile teacher-owned course files into one auditable preparation bundle.

The compiler is intentionally subject agnostic.  It preserves the parsed
document structure and provenance, resolves course/lesson scope from stable
course nodes or explicit teacher decisions, and never turns a candidate into
a confirmed authoring revision.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from material_models import ParsedDocument


ABSORPTION_SCHEMA_VERSION = "course_material_absorption_v1"
STRUCTURED_DOCUMENT_SCHEMA_VERSION = "structured_material_document_v1"
ABSORBABLE_DOCUMENT_TYPES = ("outline", "lesson_plan", "script", "ppt")
ABSORPTION_ACTIONS = {"absorb", "reference_only", "ignore"}
SOURCE_ROLES = {"primary", "reference"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(value: Any, limit: int = 600) -> str:
    return str(value or "").strip()[:limit]


def _stable_digest(value: Any, length: int = 24) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:length]


def _sequence_number(value: str) -> int | None:
    match = re.search(r"(?:第\s*)?(\d{1,3})\s*(?:讲|课|章|节)", value)
    if match:
        return int(match.group(1))
    chinese = re.search(r"(?:第\s*)?([一二三四五六七八九十百]{1,5})\s*(?:讲|课|章|节)", value)
    if not chinese:
        return None
    digits = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    raw = chinese.group(1)
    if raw == "十":
        return 10
    if "百" in raw:
        left, raw = raw.split("百", 1)
        value = digits.get(left, 1) * 100
    else:
        value = 0
    if "十" in raw:
        left, right = raw.split("十", 1)
        value += digits.get(left, 1) * 10 + digits.get(right, 0)
    else:
        value += digits.get(raw, 0)
    return value or None


def _lesson_nodes(course: dict[str, Any] | None) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    nodes = [item for item in (course or {}).get("nodes") or [] if isinstance(item, dict)]
    by_id = {
        str(item.get("node_id") or ""): item
        for item in nodes
        if str(item.get("node_id") or "")
    }
    lessons = [
        item for item in nodes
        if int(item.get("node_level") or 0) == 1
        and str(item.get("parent_node_id") or "").lower() in {"", "root"}
    ]
    return lessons, by_id


def _lesson_for_node(node_id: str, by_id: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    current = by_id.get(node_id)
    visited: set[str] = set()
    while isinstance(current, dict):
        current_id = str(current.get("node_id") or "")
        if not current_id or current_id in visited:
            return None
        visited.add(current_id)
        if (
            int(current.get("node_level") or 0) == 1
            and str(current.get("parent_node_id") or "").lower() in {"", "root"}
        ):
            return current
        current = by_id.get(str(current.get("parent_node_id") or ""))
    return None


def _resolve_scope(
    asset: dict[str, Any],
    document_type: str,
    lessons: list[dict[str, Any]],
    nodes_by_id: dict[str, dict[str, Any]],
) -> tuple[str, str, str]:
    if document_type == "outline":
        return "course", "课程大纲", "course"
    decision = asset.get("absorption_decision") or {}
    explicit = _text(decision.get("target_scope_id"), 200)
    if explicit:
        if explicit.startswith("import-lesson-"):
            number = _sequence_number(explicit) or explicit.rsplit("-", 1)[-1]
            return explicit, f"第 {number} 讲", "teacher"
        lesson = _lesson_for_node(explicit, nodes_by_id) or nodes_by_id.get(explicit)
        return explicit, _text((lesson or {}).get("node_name"), 180) or explicit, "teacher"
    for match in asset.get("structure_matches") or []:
        if not isinstance(match, dict):
            continue
        lesson = _lesson_for_node(str(match.get("node_id") or ""), nodes_by_id)
        if lesson:
            return (
                str(lesson.get("node_id") or ""),
                _text(lesson.get("node_name"), 180) or "未命名讲次",
                "course_node",
            )
    sequence = _sequence_number(str(asset.get("relative_path") or asset.get("filename") or ""))
    if sequence and sequence <= len(lessons):
        lesson = lessons[sequence - 1]
        return (
            str(lesson.get("node_id") or ""),
            _text(lesson.get("node_name"), 180) or f"第 {sequence} 讲",
            "file_sequence",
        )
    if sequence:
        return f"import-lesson-{sequence}", f"第 {sequence} 讲", "provisional_sequence"
    return "", "", "unresolved"


def _target_identity(document_type: str, scope_id: str) -> tuple[str, str]:
    if document_type == "outline":
        return "managed:outline", "outline"
    prefix = {
        "lesson_plan": "lesson-plan",
        "script": "script",
        "ppt": "ppt-v6",
    }[document_type]
    return f"{prefix}:{scope_id}", document_type


def _default_action(asset: dict[str, Any], document_type: str) -> str:
    decision = asset.get("absorption_decision") or {}
    explicit = str(decision.get("action") or "")
    if explicit in ABSORPTION_ACTIONS:
        return explicit
    if document_type not in ABSORBABLE_DOCUMENT_TYPES:
        return "reference_only"
    if str(asset.get("version_role") or "unknown") in {"older", "reference"}:
        return "reference_only"
    return "absorb"


def _source_score(asset: dict[str, Any]) -> float:
    confidence = float(asset.get("classification_confidence") or 0.5)
    match_confidence = float(((asset.get("structure_matches") or [{}])[0]).get("confidence") or 0.5)
    version_bonus = {"current": 0.22, "unknown": 0.06, "reference": -0.08, "older": -0.22}.get(
        str(asset.get("version_role") or "unknown"), 0.0
    )
    teacher_bonus = 0.2 if str(asset.get("classification_source") or "") == "teacher" else 0.0
    return round(confidence * 0.58 + match_confidence * 0.32 + version_bonus + teacher_bonus, 4)


def _structured_document(
    *,
    target_id: str,
    document_type: str,
    title: str,
    source: dict[str, Any],
    document: ParsedDocument,
    source_role: str = "reference",
) -> dict[str, Any]:
    sections: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    source_asset_id = str(source.get("asset_id") or "")
    for block in sorted(document.blocks, key=lambda item: item.order):
        text = str(block.text or "").strip()
        if not text and block.kind != "picture":
            continue
        slide = block.locator.slide
        starts_section = block.kind in {"title", "heading"}
        if document_type == "ppt" and slide is not None:
            section_key = f"slide-{slide}"
            if current is None or current.get("source_unit") != section_key:
                current = {
                    "section_id": f"smds-{_stable_digest([target_id, source_asset_id, section_key])}",
                    "title": text if starts_section else f"第 {slide} 页",
                    "order": len(sections),
                    "source_unit": section_key,
                    "source_asset_id": source_asset_id,
                    "source_role": source_role,
                    "blocks": [],
                }
                sections.append(current)
        elif starts_section or current is None:
            current = {
                "section_id": f"smds-{_stable_digest([target_id, source_asset_id, block.block_id])}",
                "title": text if starts_section else "正文",
                "order": len(sections),
                "source_unit": str(block.block_id),
                "source_asset_id": source_asset_id,
                "source_role": source_role,
                "blocks": [],
            }
            sections.append(current)
        locator = block.locator.model_dump(mode="json")
        current["blocks"].append({
            "block_id": f"smdb-{_stable_digest([target_id, source_asset_id, block.block_id])}",
            "kind": str(block.kind),
            "text": text,
            "order": len(current["blocks"]),
            "source": {
                "asset_id": source_asset_id,
                "document_id": str(document.document_id),
                "source_block_id": str(block.block_id),
                "locator": locator,
                "role": source_role,
            },
        })
    return {
        "schema_version": STRUCTURED_DOCUMENT_SCHEMA_VERSION,
        "document_type": document_type,
        "target_id": target_id,
        "title": title,
        "source_asset_id": source_asset_id,
        "source_document_id": str(document.document_id),
        "source_role": source_role,
        "parse_status": str(document.parse_status),
        "parse_quality": dict(document.quality or {}),
        "parse_warnings": list(document.warnings or []),
        "sections": sections,
        "content_hash": _stable_digest([
            source_asset_id,
            document.source_sha256,
            [(section["title"], [(block["kind"], block["text"]) for block in section["blocks"]]) for section in sections],
        ], 40),
    }


def compile_material_absorption_plan(
    *,
    package: dict[str, Any],
    documents: dict[str, ParsedDocument] | None = None,
    course: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compile one executable plan from the complete current package."""
    documents = documents or {}
    lessons, nodes_by_id = _lesson_nodes(course)
    targets_by_id: dict[str, dict[str, Any]] = {}
    unresolved: list[dict[str, Any]] = []
    retained: list[dict[str, Any]] = []

    for asset in package.get("assets") or []:
        if not isinstance(asset, dict):
            continue
        asset_id = str(asset.get("asset_id") or "")
        document_type = str(asset.get("document_type") or "other")
        action = _default_action(asset, document_type)
        decision = asset.get("absorption_decision") or {}
        if action == "ignore":
            retained.append({"asset_id": asset_id, "action": "ignore", "reason": "教师明确忽略"})
            continue
        if document_type not in ABSORBABLE_DOCUMENT_TYPES:
            retained.append({"asset_id": asset_id, "action": "reference_only", "reason": "不属于大纲、教案、讲稿或 PPT"})
            continue
        scope_id, scope_label, scope_origin = _resolve_scope(asset, document_type, lessons, nodes_by_id)
        if not scope_id:
            unresolved.append({
                "code": "target_scope_unresolved",
                "asset_id": asset_id,
                "filename": str(asset.get("filename") or ""),
                "message": "无法确定这份材料对应哪一讲，请选择对应讲次。",
            })
            continue
        target_id, target_type = _target_identity(document_type, scope_id)
        target = targets_by_id.setdefault(target_id, {
            "target_id": target_id,
            "target_type": target_type,
            "target_scope_id": scope_id,
            "target_scope_label": scope_label,
            "scope_origin": scope_origin,
            "title": "课程大纲" if target_type == "outline" else f"{scope_label}{ {'lesson_plan': '教案', 'script': '讲稿', 'ppt': 'PPT'}[target_type] }",
            "sources": [],
            "status": "ready",
            "issues": [],
        })
        role = str(decision.get("role") or "")
        if role not in SOURCE_ROLES:
            role = "candidate" if action == "absorb" else "reference"
        target["sources"].append({
            "asset_id": asset_id,
            "filename": str(asset.get("filename") or ""),
            "relative_path": str(asset.get("relative_path") or ""),
            "material_asset_id": str(asset.get("material_asset_id") or ""),
            "action": action,
            "role": role,
            "version_role": str(asset.get("version_role") or "unknown"),
            "score": _source_score(asset),
            "explicit_role": str(decision.get("role") or "") in SOURCE_ROLES,
            "parse_status": str(asset.get("parse_status") or "unknown"),
            "parse_quality": dict(asset.get("parse_quality") or {}),
            "parse_warnings": list(asset.get("parse_warnings") or []),
        })

    targets: list[dict[str, Any]] = []
    for target in targets_by_id.values():
        candidates = [item for item in target["sources"] if item["action"] == "absorb"]
        explicit_primary = [item for item in candidates if item["role"] == "primary" and item["explicit_role"]]
        primary: dict[str, Any] | None = None
        if len(explicit_primary) > 1:
            target["issues"].append({
                "code": "multiple_explicit_primary_sources",
                "message": "同一正式文件只能有一份主来源，请保留一份。",
            })
        elif explicit_primary:
            primary = explicit_primary[0]
        elif candidates:
            ordered = sorted(candidates, key=lambda item: (-float(item["score"]), item["asset_id"]))
            current = [item for item in ordered if item["version_role"] == "current"]
            if len(current) > 1:
                target["issues"].append({
                    "code": "multiple_current_sources",
                    "message": "系统发现多份当前版本，请指定哪一份作为主来源。",
                })
            else:
                primary = current[0] if current else ordered[0]
        if primary:
            for source in target["sources"]:
                source["role"] = "primary" if source["asset_id"] == primary["asset_id"] else "reference"
            primary_document = documents.get(primary["asset_id"])
            if primary_document is None or not primary_document.blocks:
                target["issues"].append({
                    "code": "primary_source_not_parsed",
                    "message": "主来源尚未形成可用正文结构，请重新解析或更换主来源。",
                })
            else:
                source_assets = {
                    str(item.get("asset_id") or ""): item
                    for item in package.get("assets") or []
                    if isinstance(item, dict)
                }
                ordered_sources = sorted(
                    target["sources"],
                    key=lambda item: (item["role"] != "primary", -float(item["score"]), item["asset_id"]),
                )
                source_documents: list[dict[str, Any]] = []
                all_sections: list[dict[str, Any]] = []
                review_items: list[dict[str, Any]] = []
                for source in ordered_sources:
                    document = documents.get(source["asset_id"])
                    if document is None or not document.blocks:
                        if source["role"] == "reference":
                            review_items.append({
                                "code": "reference_source_not_parsed",
                                "asset_id": source["asset_id"],
                                "message": f"{source['filename']} 已保留为参考来源，但正文尚未可用。",
                            })
                        continue
                    structured_source = _structured_document(
                        target_id=target["target_id"],
                        document_type=target["target_type"],
                        title=target["title"],
                        source=source_assets[source["asset_id"]],
                        document=document,
                        source_role=source["role"],
                    )
                    source_documents.append({
                        "asset_id": source["asset_id"],
                        "filename": source["filename"],
                        "role": source["role"],
                        "document_id": structured_source["source_document_id"],
                        "parse_status": structured_source["parse_status"],
                        "parse_quality": structured_source["parse_quality"],
                        "parse_warnings": structured_source["parse_warnings"],
                    })
                    for section in structured_source["sections"]:
                        section = dict(section)
                        section["order"] = len(all_sections)
                        all_sections.append(section)
                    if document.parse_status != "parsed" or document.warnings:
                        review_items.append({
                            "code": "source_parse_review_required",
                            "asset_id": source["asset_id"],
                            "message": f"{source['filename']} 的解析结果需要复核。",
                        })
                target["review_items"] = review_items
                target["structured_draft"] = {
                    "schema_version": STRUCTURED_DOCUMENT_SCHEMA_VERSION,
                    "document_type": target["target_type"],
                    "target_id": target["target_id"],
                    "title": target["title"],
                    "source_documents": source_documents,
                    "sections": all_sections,
                    "content_hash": _stable_digest([
                        target["target_id"],
                        [(item["asset_id"], item["role"], item["document_id"]) for item in source_documents],
                        [(section["section_id"], section["source_role"]) for section in all_sections],
                    ], 40),
                }
        else:
            target["issues"].append({
                "code": "primary_source_missing",
                "message": "这个正式文件还没有可吸收的主来源。",
            })
        if target["issues"]:
            target["status"] = "needs_decision"
            unresolved.extend({
                **issue,
                "target_id": target["target_id"],
                "target_label": target["title"],
            } for issue in target["issues"])
        targets.append(target)

    targets.sort(key=lambda item: (
        ABSORBABLE_DOCUMENT_TYPES.index(item["target_type"]),
        str(item["target_scope_id"]),
    ))
    plan_basis = {
        "package_id": str(package.get("package_id") or ""),
        "course_id": str(package.get("course_id") or ""),
        "understanding_revision": (package.get("material_understanding") or {}).get("analyzed_at", ""),
        "targets": [{
            "target_id": item["target_id"],
            "sources": [(source["asset_id"], source["action"], source["role"]) for source in item["sources"]],
            "content_hash": (item.get("structured_draft") or {}).get("content_hash", ""),
        } for item in targets],
    }
    plan_id = f"cmap-{_stable_digest(plan_basis)}"
    return {
        "schema_version": ABSORPTION_SCHEMA_VERSION,
        "plan_id": plan_id,
        "package_id": str(package.get("package_id") or ""),
        "course_id": str(package.get("course_id") or ""),
        "status": "ready" if targets and not unresolved else "needs_decision",
        "compiled_at": _now(),
        "targets": targets,
        "unresolved_items": unresolved,
        "retained_sources": retained,
        "scope_options": [
            {
                "scope_id": str(lesson.get("node_id") or ""),
                "label": _text(lesson.get("node_name"), 180) or f"第 {index} 讲",
            }
            for index, lesson in enumerate(lessons, start=1)
            if str(lesson.get("node_id") or "")
        ],
        "summary": {
            "target_count": len(targets),
            "working_draft_count": sum(1 for item in targets if item.get("structured_draft")),
            "unresolved_count": len(unresolved),
            "source_count": len(package.get("assets") or []),
        },
    }


def material_absorption_bundle(plan: dict[str, Any]) -> dict[str, Any]:
    if str(plan.get("status") or "") != "ready" or plan.get("unresolved_items"):
        raise ValueError("material_absorption_plan_unresolved")
    targets = []
    for item in plan.get("targets") or []:
        draft = item.get("structured_draft")
        if not isinstance(draft, dict):
            raise ValueError("material_absorption_draft_missing")
        targets.append({
            "target_id": str(item.get("target_id") or ""),
            "target_type": str(item.get("target_type") or ""),
            "target_scope_id": str(item.get("target_scope_id") or ""),
            "target_scope_label": str(item.get("target_scope_label") or ""),
            "title": str(item.get("title") or ""),
            "structured_document": draft,
            "sources": [dict(source) for source in item.get("sources") or []],
        })
    return {
        "schema_version": "teacher_material_absorption_bundle_v1",
        "bundle_id": f"tmab-{_stable_digest([plan.get('plan_id'), [(item['target_id'], item['structured_document'].get('content_hash')) for item in targets]])}",
        "plan_id": str(plan.get("plan_id") or ""),
        "package_id": str(plan.get("package_id") or ""),
        "course_id": str(plan.get("course_id") or ""),
        "status": "working_drafts_created",
        "created_at": _now(),
        "targets": targets,
    }


__all__ = [
    "ABSORPTION_ACTIONS",
    "ABSORPTION_SCHEMA_VERSION",
    "ABSORBABLE_DOCUMENT_TYPES",
    "SOURCE_ROLES",
    "STRUCTURED_DOCUMENT_SCHEMA_VERSION",
    "compile_material_absorption_plan",
    "material_absorption_bundle",
]
