"""Classify representation edits and keep semantic ownership in the course."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import re
from typing import Any, Literal

from course_document import stable_hash
from slide_deck import validate_slide_deck
from teaching_representations import (
    TeachingRepresentation,
    TeachingRepresentationRegistry,
    TeachingRepresentationRepository,
    TeachingRepresentationSpec,
)

EditClassification = Literal["presentation", "equivalent_semantic", "semantic", "ambiguous"]


def classify_representation_edit(
    *,
    field: str,
    before: Any,
    after: Any,
    semantic_intent: bool | None = None,
) -> dict[str, Any]:
    before_text = str(before or "").strip()
    after_text = str(after or "").strip()
    if before_text == after_text:
        return {"classification": "equivalent_semantic", "reason": "内容没有发生语义变化"}
    if field in {"theme", "layout", "color", "font_size", "animation_speed", "position"}:
        return {"classification": "presentation", "reason": "修改只涉及视觉或播放表现"}
    if semantic_intent is True:
        return {"classification": "semantic", "reason": "用户明确要求改变课程含义"}
    if semantic_intent is False:
        return {"classification": "equivalent_semantic", "reason": "用户明确要求只调整当前表达"}
    normalized_before = _normalize(before_text)
    normalized_after = _normalize(after_text)
    if normalized_before == normalized_after:
        return {"classification": "equivalent_semantic", "reason": "仅标点、空白或格式发生变化"}
    if field == "title" and _token_overlap(normalized_before, normalized_after) >= 0.72:
        return {"classification": "equivalent_semantic", "reason": "标题保持同一核心概念"}
    if field in {"bullets", "speaker_notes", "body", "example", "prompt", "title", "key_message", "subtitle"}:
        return {"classification": "ambiguous", "reason": "该字段承载教学含义，需要用户决定是否联动课程"}
    return {"classification": "ambiguous", "reason": "无法仅靠确定性规则确认语义边界"}


def representation_edit_impact(
    registry: TeachingRepresentationRegistry,
    spec: TeachingRepresentationSpec,
    *,
    unit_id: str,
) -> dict[str, Any]:
    bindings = spec.unit_bindings.get(unit_id) or []
    source_keys = sorted({key for binding in bindings for key in binding.source_revisions})
    block_ids = sorted({binding.block_id for binding in bindings if binding.block_id})
    section_ids = sorted({binding.section_id for binding in bindings if binding.section_id})
    affected: list[dict[str, Any]] = []
    for representation in registry.representations:
        representation_spec = next((
            item for item in registry.specs if item.spec_id == representation.spec_id
        ), None)
        if representation_spec is None:
            continue
        unit_ids = sorted({
            candidate_unit_id
            for candidate_unit_id, candidate_bindings in representation_spec.unit_bindings.items()
            if any(
                set(binding.source_revisions).intersection(source_keys)
                for binding in candidate_bindings
            )
        })
        if unit_ids:
            affected.append({
                "representation_id": representation.representation_id,
                "representation_type": representation.representation_type,
                "unit_ids": unit_ids,
            })
    return {
        "source_keys": source_keys,
        "block_ids": block_ids,
        "section_ids": section_ids,
        "affected_representations": affected,
        "protected": ["无来源关系的课程块", "其他课程", "历史作答", "个人笔记原文"],
    }


def apply_representation_only_edit(
    repository: TeachingRepresentationRepository,
    registry: TeachingRepresentationRegistry,
    representation: TeachingRepresentation,
    spec: TeachingRepresentationSpec,
    *,
    unit_id: str,
    field: str,
    after: Any,
) -> TeachingRepresentationRegistry:
    payload = deepcopy(spec.payload)
    content = payload.get("content") or {}
    units_key = next((key for key in ("units", "slides", "sections") if isinstance(content.get(key), list)), "")
    if not units_key:
        raise ValueError("Teaching representation does not contain editable units")
    unit = next((item for item in content[units_key] if str(item.get("unit_id") or "") == unit_id), None)
    if unit is None:
        raise KeyError(unit_id)
    before = deepcopy(unit.get(field))
    unit[field] = deepcopy(after)
    if spec.representation_type == "slide_deck":
        overrides = content.setdefault("presentation_overrides", {})
        unit_overrides = overrides.setdefault(unit_id, {})
        existing = unit_overrides.get(field) if isinstance(unit_overrides.get(field), dict) else {}
        base_value = existing.get("base_value", before)
        if after == base_value:
            unit_overrides.pop(field, None)
            if not unit_overrides:
                overrides.pop(unit_id, None)
        else:
            unit_overrides[field] = {
                "value": deepcopy(after),
                "base_value": deepcopy(base_value),
                "source_revision_vector": {
                    source_key: revision
                    for binding in spec.unit_bindings.get(unit_id) or []
                    for source_key, revision in binding.source_revisions.items()
                },
            }
        quality = validate_slide_deck(content)
        if not quality["passed"]:
            codes = ", ".join(
                issue["code"] for issue in quality["issues"]
                if issue["severity"] == "critical"
            )
            raise ValueError(f"Slide edit violates the quality gate: {codes}")
        content["quality_summary"] = {
            "passed": quality["passed"],
            "score": quality["score"],
            "semantic_issue_count": len(quality["semantic"]["issues"]),
            "visual_issue_count": len(quality["visual"]["issues"]),
        }
    now = datetime.now(timezone.utc).isoformat()
    spec_revision = stable_hash(payload, prefix="tsr_")
    edited_spec = TeachingRepresentationSpec(
        spec_id=stable_hash({
            "course_id": spec.course_id,
            "representation_type": spec.representation_type,
            "source_bindings": [item.model_dump(mode="json") for item in spec.source_bindings],
            "payload": payload,
        }, prefix="trs_"),
        course_id=spec.course_id,
        representation_type=spec.representation_type,
        source_bindings=spec.source_bindings,
        unit_bindings=spec.unit_bindings,
        payload=payload,
        revision=spec_revision,
        created_at=now,
        updated_at=now,
    )
    repository.register_spec(edited_spec)
    edited_representation = representation.model_copy(deep=True)
    edited_representation.spec_id = edited_spec.spec_id
    edited_representation.semantic_fingerprint = stable_hash(content, prefix="sem_")
    edited_representation.render_fingerprint = stable_hash({
        "spec_revision": spec_revision,
        "renderer": "structured_json_v2",
    }, prefix="rnd_")
    edited_representation.revision = stable_hash({
        "spec_revision": spec_revision,
        "source_revision_vector": edited_representation.source_revision_vector,
    }, prefix="rpr_")
    edited_representation.updated_at = now
    return repository.register_representation(edited_representation)


def _normalize(value: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", value).lower()


def _token_overlap(before: str, after: str) -> float:
    before_tokens = set(re.findall(r"[\u4e00-\u9fff]{2,}|[a-z0-9]+", before))
    after_tokens = set(re.findall(r"[\u4e00-\u9fff]{2,}|[a-z0-9]+", after))
    if not before_tokens or not after_tokens:
        return 0.0
    return len(before_tokens & after_tokens) / len(before_tokens | after_tokens)


__all__ = [
    "apply_representation_only_edit",
    "classify_representation_edit",
    "representation_edit_impact",
]
