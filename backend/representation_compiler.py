"""Deterministic course projections into same-source teaching representations."""

from __future__ import annotations

import re
import tempfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Callable
from typing import Any

from course_document import CourseBlock, CourseDocument, stable_hash
from course_revisions import revision_vector_for_document
from diagram_spec import DIAGRAM_COMPILER_VERSION, compile_diagram_spec, validate_diagram_spec
from slide_deck import (
    SLIDE_DECK_COMPILER_VERSION,
    SlideDeckPlanV1,
    compile_slide_deck,
    validate_slide_deck,
)
from slide_deck_renderer import export_structured_slide_deck
from teaching_representations import (
    RepresentationPlan,
    SourceBinding,
    TeachingRepresentation,
    TeachingRepresentationRepository,
    TeachingRepresentationSpec,
    source_binding_for_document,
)

REPRESENTATION_COMPILER_VERSION = "same_source_compiler_v4"
HANDOUT_COMPILER_VERSION = "block_units_v1"
CORE_TYPES = ("outline", "lesson_plan", "handout", "practice_sheet", "slide_deck", "diagram")


def compile_core_representations(
    document: CourseDocument,
    course_data: dict[str, Any],
    repository: TeachingRepresentationRepository,
    *,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
    presentation_overrides: dict[str, dict[str, dict[str, Any]]] | None = None,
    baseline_registry: Any | None = None,
    deck_plan: SlideDeckPlanV1 | dict[str, Any] | None = None,
    resume_slides: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    vector = revision_vector_for_document(document).revisions
    baseline = baseline_registry or repository.load(document.course_id)
    existing_by_type = {
        item.representation_type: item
        for item in baseline.representations
    }
    existing_specs_by_type = {
        item.representation_type: next(
            (spec for spec in baseline.specs if spec.spec_id == item.spec_id),
            None,
        )
        for item in baseline.representations
    }
    plan = RepresentationPlan(
        plan_id=stable_hash({
            "course_id": document.course_id,
            "revision": document.document_revision,
            "types": CORE_TYPES,
        }, prefix="rpl_"),
        course_id=document.course_id,
        source_revision_vector=vector,
        target_scope={"kind": "course"},
        requested_representations=list(CORE_TYPES),
        knowledge_refs=_course_knowledge_refs(document, course_data),
        pedagogical_reasons=[
            "为学习者、课程维护者和课堂展示提供同一课程语义的不同用途表达",
            "保持大纲、讲义、教案、正式题目和幻灯之间的来源与修订一致",
        ],
        cost_class="medium",
        accessibility_requirements=["阅读顺序", "替代文本", "可导出文本"],
        quality_requirements=["来源完整", "跨产物术语一致", "正式题目只引用不复制所有权"],
        fallback_chain=["handout", "outline"],
        status="ready",
    )
    repository.register_plan(plan)

    if progress_callback:
        progress_callback({"event": "representation_stage", "progress": 2, "stage": "planning"})
    payloads = {
        "outline": _outline_spec(document),
        "lesson_plan": _lesson_plan_spec(document, course_data),
        "handout": _handout_spec(document),
        "practice_sheet": _practice_sheet_spec(document, course_data),
        "slide_deck": compile_slide_deck(
            document,
            course_data,
            progress_callback=progress_callback,
            presentation_overrides=presentation_overrides,
            deck_plan=deck_plan,
            resume_slides=resume_slides,
        ),
        "diagram": compile_diagram_spec(document),
    }
    built: list[dict[str, Any]] = []
    for representation_type, payload in payloads.items():
        existing = existing_by_type.get(representation_type)
        existing_spec = existing_specs_by_type.get(representation_type)
        compiler_version = _compiler_version_for(representation_type)
        payload, reused_unit_ids = _reuse_unchanged_units(
            payload,
            (existing_spec.payload.get("content") if existing_spec else None) or {},
            stale_unit_ids=(
                list(existing.stale_unit_ids)
                if existing and existing.status == "stale"
                else []
            ),
            reuse_all=bool(
                existing
                and existing.status == "ready"
                and existing_spec
                and existing_spec.payload.get("compiler_version") == compiler_version
            ),
        )
        unit_bindings = _unit_bindings_for_payload(document, payload)
        bindings = _dedupe_bindings([
            binding
            for values in unit_bindings.values()
            for binding in values
        ])
        unit_count = len(payload.get("units") or payload.get("slides") or payload.get("sections") or [])
        payload_quality = (
            validate_slide_deck(payload, course_data=course_data)
            if representation_type == "slide_deck"
            else validate_diagram_spec(payload)
            if representation_type == "diagram"
            else {"passed": bool(unit_count), "issues": []}
        )
        if representation_type in {"slide_deck", "diagram"}:
            payload["quality_report"] = deepcopy(payload_quality)
        spec_payload = {
            "compiler_version": compiler_version,
            "representation_type": representation_type,
            "content": payload,
            **(
                {"quality_report": deepcopy(payload_quality)}
                if representation_type in {"slide_deck", "diagram"}
                else {}
            ),
        }
        spec_id = stable_hash({
            "course_id": document.course_id,
            "type": representation_type,
            "source_revision_vector": _combined_revisions(bindings),
            "payload": spec_payload,
        }, prefix="trs_")
        spec_revision = stable_hash(spec_payload, prefix="tsr_")
        representation_status = "ready" if unit_count and payload_quality["passed"] else "failed"
        spec = TeachingRepresentationSpec(
            spec_id=spec_id,
            course_id=document.course_id,
            representation_type=representation_type,
            source_bindings=bindings,
            unit_bindings=unit_bindings,
            payload=spec_payload,
            revision=spec_revision,
            created_at=now,
            updated_at=now,
        )
        repository.register_spec(spec)
        representation_id = stable_hash({
            "course_id": document.course_id,
            "type": representation_type,
        }, prefix="trp_")
        representation = TeachingRepresentation(
            representation_id=representation_id,
            course_id=document.course_id,
            representation_type=representation_type,
            source_bindings=bindings,
            source_revision_vector=_combined_revisions(bindings),
            spec_id=spec_id,
            semantic_fingerprint=stable_hash(payload, prefix="sem_"),
            render_fingerprint=stable_hash({
                "spec_revision": spec_revision,
                "renderer": (
                    f"pptx:{SLIDE_DECK_COMPILER_VERSION}"
                    if representation_type == "slide_deck"
                    else "structured_json_v2"
                ),
            }, prefix="rnd_"),
            quality_report_id=stable_hash({
                "spec_revision": spec_revision,
                "quality": payload_quality,
            }, prefix="rqr_"),
            revision=stable_hash({
                "spec_revision": spec_revision,
                "source_revision_vector": _combined_revisions(bindings),
            }, prefix="rpr_"),
            status=representation_status,
            stale_unit_ids=[],
            stale_reasons=(
                []
                if representation_status == "ready"
                else [
                    str(issue.get("code") or "representation_quality_failed")
                    for issue in payload_quality.get("issues") or []
                    if issue.get("severity") == "critical"
                ] or ["empty_representation"]
            ),
            created_at=now,
            updated_at=now,
        )
        repository.register_representation(representation)
        built.append({
            "representation_id": representation_id,
            "representation_type": representation_type,
            "spec_id": spec_id,
            "status": representation_status,
            "unit_count": unit_count,
            "rebuilt_unit_ids": sorted(
                str(item.get("unit_id") or "")
                for item in (
                    payload.get("units")
                    or payload.get("slides")
                    or payload.get("sections")
                    or []
                )
                if item.get("unit_id") and str(item.get("unit_id")) not in set(reused_unit_ids)
            ),
            "reused_unit_ids": reused_unit_ids,
        })
        if progress_callback and representation_type != "slide_deck":
            progress_callback({
                "event": "representation_stage",
                "progress": min(99, 94 + len(built)),
                "stage": f"compiled:{representation_type}",
            })
    return {"plan_id": plan.plan_id, "representations": built}


def _compiler_version_for(representation_type: str) -> str:
    if representation_type == "slide_deck":
        return f"{REPRESENTATION_COMPILER_VERSION}:{SLIDE_DECK_COMPILER_VERSION}"
    if representation_type == "diagram":
        return f"{REPRESENTATION_COMPILER_VERSION}:{DIAGRAM_COMPILER_VERSION}"
    if representation_type == "handout":
        return f"{REPRESENTATION_COMPILER_VERSION}:{HANDOUT_COMPILER_VERSION}"
    return REPRESENTATION_COMPILER_VERSION


def rebuild_core_representations_safely(
    document: CourseDocument,
    course_data: dict[str, Any],
    repository: TeachingRepresentationRepository,
    *,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
    deck_plan: SlideDeckPlanV1 | dict[str, Any] | None = None,
    resume_slides: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Compile in isolation and publish only a complete, quality-passing set.

    The active registry remains available in its stale state when compilation
    or validation fails. This keeps the last usable lesson plan, handout,
    practice sheet and slide deck accessible without pretending they match the
    latest course revision.
    """
    previous = repository.load(document.course_id)
    stale_before = [
        {
            "representation_id": item.representation_id,
            "representation_type": item.representation_type,
            "spec_id": item.spec_id,
            "stale_unit_ids": list(item.stale_unit_ids),
            "stale_reasons": list(item.stale_reasons),
        }
        for item in previous.representations
        if item.status == "stale"
    ]
    presentation_overrides = _current_slide_overrides(previous)
    try:
        with tempfile.TemporaryDirectory(prefix="lingzhi-representation-build-") as temp_dir:
            shadow = TeachingRepresentationRepository(temp_dir)
            build = compile_core_representations(
                document,
                course_data,
                shadow,
                progress_callback=progress_callback,
                presentation_overrides=presentation_overrides,
                baseline_registry=previous,
                deck_plan=deck_plan,
                resume_slides=resume_slides,
            )
            candidate = shadow.load(document.course_id)
            current_spec_ids = {item.spec_id for item in candidate.representations}
            current_specs = [
                item for item in candidate.specs if item.spec_id in current_spec_ids
            ]
            quality = validate_compiled_representations(current_specs)
            if not quality["passed"]:
                if progress_callback:
                    progress_callback({"event": "build_blocked", "progress": 100, "quality": quality})
                return {
                    "status": "failed_using_last_available",
                    "quality": quality,
                    "stale_before": stale_before,
                    "last_available": [
                        {
                            "representation_id": item.representation_id,
                            "representation_type": item.representation_type,
                            "spec_id": item.spec_id,
                            "status": item.status,
                        }
                        for item in previous.representations
                    ],
                }
            candidate.applied_revision_event_ids = list(previous.applied_revision_event_ids)
            committed = repository.save(candidate)
            stale_by_type = {
                item["representation_type"]: item["stale_unit_ids"]
                for item in stale_before
            }
            changes = _describe_representation_changes(
                previous,
                candidate,
                stale_by_type,
            )
            result = {
                "status": "synchronized",
                "quality": quality,
                "stale_before": stale_before,
                "rebuilt": [
                    {
                        **item,
                        "rebuilt_unit_ids": stale_by_type.get(item["representation_type"], []),
                    }
                    for item in build["representations"]
                ],
                "rebuilt_unit_count": sum(
                    len(stale_by_type.get(item["representation_type"], []))
                    for item in build["representations"]
                ),
                "reused_unit_count": sum(
                    len(item.get("reused_unit_ids") or [])
                    for item in build["representations"]
                ),
                "changes": changes,
                "changed_unit_count": sum(
                    1
                    for item in changes
                    for unit in item["units"]
                    if unit["change_kind"] == "content_changed"
                ),
                "verified_unit_count": sum(
                    1
                    for item in changes
                    for unit in item["units"]
                    if unit["change_kind"] == "source_verified"
                ),
                "registry_revision": committed.registry_revision,
            }
            if progress_callback:
                progress_callback({"event": "build_published", "progress": 100, "quality": quality})
            return result
    except Exception as exc:
        if progress_callback:
            progress_callback({
                "event": "build_failed",
                "progress": 100,
                "message": str(exc),
            })
        return {
            "status": "failed_using_last_available",
            "quality": {
                "passed": False,
                "issues": [{
                    "severity": "critical",
                    "code": "representation_rebuild_failed",
                    "message": str(exc),
                }],
            },
            "stale_before": stale_before,
            "last_available": [
                {
                    "representation_id": item.representation_id,
                    "representation_type": item.representation_type,
                    "spec_id": item.spec_id,
                    "status": item.status,
                }
                for item in previous.representations
            ],
        }


def export_slide_deck_pptx(
    spec: TeachingRepresentationSpec,
    output_path: str | Path,
    *,
    theme: str = "qingfeng-classroom",
) -> Path:
    if spec.representation_type != "slide_deck":
        raise ValueError("Only slide deck specs can be exported to pptx")
    content = spec.payload.get("content") or {}
    return export_structured_slide_deck(content, output_path, theme=theme)


def validate_compiled_representations(specs: list[TeachingRepresentationSpec]) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    required = set(CORE_TYPES)
    present = {spec.representation_type for spec in specs}
    for missing in sorted(required - present):
        issues.append({"severity": "critical", "code": "missing_representation", "target": missing})
    for spec in specs:
        content = spec.payload.get("content") or {}
        units = content.get("units") or content.get("slides") or content.get("sections") or []
        if not units:
            issues.append({
                "severity": "critical",
                "code": "empty_representation",
                "target": spec.representation_type,
            })
        for unit in units:
            unit_id = str(unit.get("unit_id") or "")
            if not unit_id or not spec.unit_bindings.get(unit_id):
                issues.append({
                    "severity": "critical",
                    "code": "missing_source_binding",
                    "target": unit_id or spec.representation_type,
                })
        if spec.representation_type == "slide_deck":
            slide_report = validate_slide_deck(content)
            issues.extend({**issue, "representation_type": "slide_deck"} for issue in slide_report["issues"])
        if spec.representation_type == "diagram":
            diagram_report = validate_diagram_spec(content)
            issues.extend({**issue, "representation_type": "diagram"} for issue in diagram_report["issues"])
    cross_product = _validate_cross_product_consistency(specs)
    issues.extend(cross_product["issues"])
    return {
        "passed": not any(issue["severity"] == "critical" for issue in issues),
        "issues": issues,
        "representation_count": len(specs),
        "cross_product": cross_product,
    }


def _validate_cross_product_consistency(
    specs: list[TeachingRepresentationSpec],
) -> dict[str, Any]:
    """Verify every section keeps one objective and compatible knowledge refs."""
    profiles: dict[str, dict[str, dict[str, set[str]]]] = {}
    for spec in specs:
        content = spec.payload.get("content") or {}
        units = content.get("units") or content.get("slides") or content.get("sections") or []
        for unit in units:
            unit_id = str(unit.get("unit_id") or "")
            bindings = spec.unit_bindings.get(unit_id) or []
            section_id = str(unit.get("section_id") or "")
            if not section_id:
                continue
            profile = profiles.setdefault(section_id, {}).setdefault(
                spec.representation_type,
                {"objectives": set(), "knowledge": set(), "practices": set()},
            )
            profile["knowledge"].update(str(value) for value in unit.get("knowledge_refs") or [] if value)
            for binding in bindings:
                profile["objectives"].update(
                    key for key in binding.source_revisions if key.startswith("objective:")
                )
                profile["knowledge"].update(binding.knowledge_node_ids)
                profile["practices"].update(binding.practice_task_ids)

    issues: list[dict[str, Any]] = []
    # The slide deck is a demo-sized projection: ``compile_slide_deck`` caps a
    # course at 12-18 pages, so a large course intentionally teaches only a
    # subset of sections on slides. Requiring per-section slide coverage would
    # contradict that compression, so it is reported as a warning instead.
    required_section_types = {"lesson_plan", "handout", "practice_sheet", "diagram"}
    compressible_section_types = {"slide_deck"}
    checked_sections = 0
    for section_id, by_type in profiles.items():
        if "lesson_plan" not in by_type:
            continue
        checked_sections += 1
        missing = sorted(required_section_types - set(by_type))
        if missing:
            issues.append({
                "severity": "critical",
                "code": "cross_product_section_missing",
                "target": section_id,
                "missing_representations": missing,
            })
        compressed = sorted(compressible_section_types - set(by_type))
        if compressed:
            issues.append({
                "severity": "warning",
                "code": "cross_product_section_compressed",
                "target": section_id,
                "missing_representations": compressed,
            })
        objective_sets = {
            tuple(sorted(profile["objectives"]))
            for profile in by_type.values()
            if profile["objectives"]
        }
        if len(objective_sets) > 1:
            issues.append({
                "severity": "critical",
                "code": "cross_product_objective_mismatch",
                "target": section_id,
                "objective_sets": [list(value) for value in sorted(objective_sets)],
            })
        knowledge_sets = {
            representation_type: profile["knowledge"]
            for representation_type, profile in by_type.items()
            if profile["knowledge"]
        }
        if knowledge_sets:
            canonical = set().union(*knowledge_sets.values())
            for representation_type, values in knowledge_sets.items():
                if values != canonical:
                    issues.append({
                        "severity": "warning",
                        "code": "cross_product_partial_knowledge",
                        "target": f"{section_id}:{representation_type}",
                        "missing_knowledge_refs": sorted(canonical - values),
                    })
    return {
        "passed": not any(item["severity"] == "critical" for item in issues),
        "issues": issues,
        "checked_section_count": checked_sections,
    }


def _reuse_unchanged_units(
    candidate: dict[str, Any],
    previous: dict[str, Any],
    *,
    stale_unit_ids: list[str],
    reuse_all: bool,
) -> tuple[dict[str, Any], list[str]]:
    """Publish changed units while preserving byte-identical unaffected units.

    A full candidate is still compiled and quality-checked in isolation. When
    topology changes, stable units may still be reused only if the newly
    compiled value is exactly equal to the previous value. This preserves
    positions and bindings while making additions observable as new units.
    """
    candidate_key = next(
        (key for key in ("units", "slides", "sections") if isinstance(candidate.get(key), list)),
        "",
    )
    previous_key = next(
        (key for key in ("units", "slides", "sections") if isinstance(previous.get(key), list)),
        "",
    )
    if not candidate_key or candidate_key != previous_key:
        return candidate, []
    candidate_units = candidate[candidate_key]
    previous_units = previous[previous_key]
    candidate_ids = [str(item.get("unit_id") or "") for item in candidate_units]
    previous_by_id = {
        str(item.get("unit_id") or ""): item
        for item in previous_units
        if item.get("unit_id")
    }
    if not all(candidate_ids):
        return candidate, []
    topology_unchanged = set(candidate_ids) == set(previous_by_id)
    stale = set(stale_unit_ids)
    if not reuse_all and not stale and topology_unchanged:
        return candidate, []
    candidates = set(candidate_ids) & set(previous_by_id)
    if not reuse_all:
        candidates -= stale
    reusable = {
        unit_id
        for unit_id, item in zip(candidate_ids, candidate_units, strict=True)
        if unit_id in candidates and previous_by_id[unit_id] == item
    }
    merged = deepcopy(candidate)
    merged[candidate_key] = [
        deepcopy(previous_by_id[unit_id]) if unit_id in reusable else item
        for unit_id, item in zip(candidate_ids, candidate_units, strict=True)
    ]
    return merged, sorted(reusable)


def _describe_representation_changes(
    previous: Any,
    candidate: Any,
    stale_by_type: dict[str, list[str]],
) -> list[dict[str, Any]]:
    previous_specs = _active_specs_by_type(previous)
    candidate_specs = _active_specs_by_type(candidate)
    changes: list[dict[str, Any]] = []
    for representation_type, stale_unit_ids in stale_by_type.items():
        if not stale_unit_ids:
            continue
        before_units = _spec_units_by_id(previous_specs.get(representation_type))
        after_units = _spec_units_by_id(candidate_specs.get(representation_type))
        unit_changes = []
        for unit_id in stale_unit_ids:
            before = before_units.get(unit_id) or {}
            after = after_units.get(unit_id) or {}
            field, before_text, after_text = _first_visible_unit_change(
                representation_type,
                before,
                after,
            )
            unit_changes.append({
                "unit_id": unit_id,
                "section_id": str(after.get("section_id") or before.get("section_id") or ""),
                "label": _change_unit_label(representation_type, after or before, unit_id),
                "field": field,
                "before": before_text,
                "after": after_text,
                "change_kind": (
                    "content_changed"
                    if before_text != after_text
                    else "source_verified"
                ),
            })
        changes.append({
            "representation_type": representation_type,
            "units": unit_changes,
        })
    return changes


def _active_specs_by_type(registry: Any) -> dict[str, Any]:
    specs_by_id = {item.spec_id: item for item in registry.specs}
    return {
        item.representation_type: specs_by_id.get(item.spec_id)
        for item in registry.representations
        if specs_by_id.get(item.spec_id) is not None
    }


def _spec_units_by_id(spec: Any | None) -> dict[str, dict[str, Any]]:
    if spec is None:
        return {}
    content = spec.payload.get("content") or {}
    units = content.get("units") or content.get("slides") or content.get("sections") or []
    return {
        str(item.get("unit_id") or ""): item
        for item in units
        if isinstance(item, dict) and item.get("unit_id")
    }


def _first_visible_unit_change(
    representation_type: str,
    before: dict[str, Any],
    after: dict[str, Any],
) -> tuple[str, str, str]:
    fields_by_type = {
        "outline": ("learning_objective", "title"),
        "lesson_plan": ("teaching_focus", "learning_objective", "activities"),
        # A local handout edit changes the visible block markdown while the
        # section-level prompt and objective may remain byte-identical.  Keep
        # blocks first so the synchronization receipt exposes the real text
        # diff instead of incorrectly classifying the rebuilt unit as a
        # source-only verification.
        "handout": ("blocks", "learning_prompt", "learning_objective"),
        "practice_sheet": ("prompt",),
        "diagram": ("nodes", "mermaid", "title"),
        "slide_deck": ("key_message", "speaker_notes", "blocks"),
    }
    for field in fields_by_type.get(representation_type, ("title", "content")):
        before_text = _visible_change_text(before.get(field))
        after_text = _visible_change_text(after.get(field))
        if before_text != after_text:
            return field, _trim_change_text(before_text), _trim_change_text(after_text)
    fallback = _visible_change_text(after.get("title") or before.get("title"))
    return "source_revision", _trim_change_text(fallback), _trim_change_text(fallback)


def _visible_change_text(value: Any) -> str:
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, list):
        values = []
        for item in value:
            if isinstance(item, dict):
                values.extend(
                    str(item.get(key) or "").strip()
                    for key in ("phase", "prompt", "title", "content", "markdown")
                    if item.get(key)
                )
                values.extend(str(entry).strip() for entry in item.get("items") or [])
            elif str(item).strip():
                values.append(str(item).strip())
        return " · ".join(values)
    if isinstance(value, dict):
        return " · ".join(
            str(value.get(key) or "").strip()
            for key in ("title", "content", "summary")
            if value.get(key)
        )
    return str(value or "").strip()


def _trim_change_text(value: str, limit: int = 150) -> str:
    value = " ".join(str(value or "").split())
    return value if len(value) <= limit else f"{value[: limit - 1].rstrip()}…"


def _change_unit_label(
    representation_type: str,
    unit: dict[str, Any],
    unit_id: str,
) -> str:
    prefix = {
        "outline": "课程大纲",
        "lesson_plan": "教案重点",
        "handout": "讲义解释",
        "practice_sheet": "理解检查",
        "diagram": "知识图解",
        "slide_deck": {
            "learning_objective": "PPT 学习目标",
            "concept_and_reasoning": "PPT 核心讲解",
            "mastery_check": "PPT 理解检查",
            "example": "PPT 例题",
            "application": "PPT 应用",
            "reasoning": "PPT 推理",
        }.get(str(unit.get("slide_purpose") or ""), "PPT 页面"),
    }.get(representation_type, representation_type)
    title = str(
        unit.get("title")
        or unit.get("section_title")
        or unit.get("learning_objective")
        or unit_id
    ).strip()
    return f"{prefix} · {title[:34]}"


def _outline_spec(document: CourseDocument) -> dict[str, Any]:
    blocks_by_section = _blocks_by_section(document)
    sections = []
    for section in sorted(document.sections, key=lambda item: item.position):
        blocks = blocks_by_section.get(section.section_id, [])
        sections.append({
            "unit_id": f"outline:{section.section_id}",
            "section_id": section.section_id,
            "parent_section_id": section.parent_section_id,
            "title": section.title,
            "level": section.level,
            "position": section.position,
            "learning_objective": section.learning_objective,
            "objective_id": section.objective_id,
            "source_section_ids": [section.section_id],
            "source_keys": (
                [f"objective:{section.objective_id}"]
                if section.objective_id
                else []
            ),
            "source_block_ids": [block.block_id for block in blocks],
            "block_roles": [block.role for block in blocks],
            "knowledge_refs": _knowledge_refs_for_blocks(blocks),
        })
    return {"title": document.title, "sections": sections}


def _lesson_plan_spec(document: CourseDocument, course_data: dict[str, Any]) -> dict[str, Any]:
    blocks_by_section = _blocks_by_section(document)
    units = []
    for section in _learning_sections(document):
        blocks = blocks_by_section.get(section.section_id, [])
        minutes = max(12, min(45, 6 + len(blocks) * 4))
        units.append({
            "unit_id": f"lesson:{section.section_id}",
            "section_id": section.section_id,
            "title": section.title,
            "learning_objective": section.learning_objective,
            "duration_minutes": minutes,
            "teaching_focus": _objective_teaching_focus(section.learning_objective),
            "source_section_ids": [section.section_id],
            "source_block_ids": [block.block_id for block in blocks],
            "source_keys": (
                [f"objective:{section.objective_id}"]
                if section.objective_id
                else []
            ),
            "activities": [
                {"phase": "导入", "minutes": max(2, minutes // 8), "prompt": f"从已有经验进入“{section.title}”"},
                {
                    "phase": "建构",
                    "minutes": max(6, minutes // 2),
                    "prompt": (
                        f"{_objective_teaching_focus(section.learning_objective)}："
                        f"{_section_summary(blocks)}"
                    ),
                },
                {
                    "phase": "检查",
                    "minutes": max(4, minutes // 4),
                    "prompt": _objective_check_prompt(
                        section.learning_objective or section.title,
                    ),
                },
            ],
            "misconceptions": _section_misconceptions(course_data, section.section_id),
            "practice_task_ids": _section_question_ids(course_data, section.section_id),
            "knowledge_refs": _knowledge_refs_for_blocks(blocks),
        })
    return {"title": f"{document.title} 教案", "units": units}


def _handout_spec(document: CourseDocument) -> dict[str, Any]:
    blocks_by_section = _blocks_by_section(document)
    units = []
    for section in _learning_sections(document):
        blocks = [
            block for block in blocks_by_section.get(section.section_id, [])
            if block.status != "retired"
        ]
        for block in blocks:
            # A single-block legacy handout used ``handout:<section_id>``. Keep
            # that identifier so stored specs, presentation edits and API
            # callers remain valid. Multi-block sections use the authoritative
            # block id, which makes additions/reordering independent of text.
            unit_id = (
                f"handout:{section.section_id}"
                if len(blocks) == 1
                else f"handout:{section.section_id}:block:{block.block_id}"
            )
            units.append({
                "unit_id": unit_id,
                "section_id": section.section_id,
                "block_id": block.block_id,
                "title": str(block.payload.get("title") or section.title),
                "section_title": section.title,
                "block_role": block.role,
                "learning_objective": section.learning_objective,
                "learning_prompt": _objective_learning_prompt(
                    section.learning_objective or section.title,
                ),
                # Do not bind the aggregate section revision here: it includes
                # every sibling block and would turn a paragraph edit back into
                # a whole-section rebuild. section_structure tracks title,
                # order and objective without depending on sibling contents.
                "source_block_ids": [block.block_id],
                "source_keys": _unique([
                    f"section_structure:{section.section_id}",
                    *(
                        [f"objective:{section.objective_id}"]
                        if section.objective_id
                        else []
                    ),
                ]),
                "knowledge_refs": list(block.concept_refs),
                "blocks": [{
                    "block_id": block.block_id,
                    "role": block.role,
                    "title": str(block.payload.get("title") or ""),
                    "markdown": str(block.payload.get("markdown") or block.payload.get("text") or ""),
                    "knowledge_refs": list(block.concept_refs),
                }],
            })
    return {"title": f"{document.title} 讲义", "units": units}


def _practice_sheet_spec(document: CourseDocument, course_data: dict[str, Any]) -> dict[str, Any]:
    questions = list((course_data.get("learning_assets") or {}).get("questions") or [])
    units = []
    by_section = {section.section_id: section for section in document.sections}
    for question in questions:
        section_id = str(question.get("node_id") or "")
        section = by_section.get(section_id)
        source_blocks = [block.block_id for block in document.blocks if block.section_id == section_id]
        units.append({
            "unit_id": f"practice:{question.get('revision_id') or question.get('question_id')}",
            "section_id": section_id,
            "section_title": section.title if section else section_id,
            "source_section_ids": [section_id] if section else [],
            "source_block_ids": source_blocks,
            "source_keys": (
                [f"objective:{section.objective_id}"]
                if section and section.objective_id
                else []
            ),
            "practice_task_id": question.get("question_id") or question.get("asset_id"),
            "practice_revision_id": question.get("revision_id"),
            "prompt": question.get("prompt"),
            "practice_level": question.get("practice_level"),
            "knowledge_refs": _unique([
                *(question.get("course_knowledge_refs") or []),
                *(question.get("concept_ids") or []),
                *[
                    knowledge_id
                    for block in document.blocks
                    if block.section_id == section_id
                    for knowledge_id in block.concept_refs
                ],
            ]),
            "answer_policy": "separate_answer_key",
        })
    blocks_by_section = _blocks_by_section(document)
    for section in _learning_sections(document):
        if not section.learning_objective:
            continue
        blocks = blocks_by_section.get(section.section_id, [])
        units.append({
            "unit_id": f"practice:objective:{section.section_id}",
            "section_id": section.section_id,
            "section_title": section.title,
            "source_section_ids": [section.section_id],
            "source_block_ids": [block.block_id for block in blocks],
            "source_keys": (
                [f"objective:{section.objective_id}"]
                if section.objective_id
                else []
            ),
            "prompt": (
                "请不用复述步骤，说明你将如何证明自己已经达到本节目标："
                f"{section.learning_objective}"
            ),
            "practice_level": "objective_understanding_check",
            "knowledge_refs": _knowledge_refs_for_blocks(blocks),
            "answer_policy": "derived_understanding_check",
            "derived_from_course_objective": True,
        })
    return {"title": f"{document.title} 练习", "units": units}


def _unit_bindings_for_payload(
    document: CourseDocument,
    payload: dict[str, Any],
) -> dict[str, list[SourceBinding]]:
    vector = revision_vector_for_document(document).revisions
    blocks_by_id = {block.block_id: block for block in document.blocks}
    result: dict[str, list[SourceBinding]] = {}
    units = payload.get("units") or payload.get("slides") or payload.get("sections") or []
    for unit in units:
        unit_id = str(unit.get("unit_id") or "")
        if not unit_id:
            continue
        bindings: list[SourceBinding] = []
        objective_ids = _unique(unit.get("learning_objective_ids") or [])
        for block_id in unit.get("source_block_ids") or []:
            block = blocks_by_id.get(str(block_id))
            bindings.append(source_binding_for_document(
                document,
                section_id=str(unit.get("section_id") or "") or None,
                block_id=str(block_id),
                knowledge_node_ids=list(block.concept_refs) if block else [],
                learning_objective_ids=objective_ids,
            ))
        for section_id in unit.get("source_section_ids") or []:
            bindings.append(source_binding_for_document(
                document,
                section_id=str(section_id),
                knowledge_node_ids=_unique(unit.get("knowledge_refs") or []),
                learning_objective_ids=objective_ids,
            ))
        if objective_ids and not bindings:
            bindings.append(source_binding_for_document(
                document,
                learning_objective_ids=objective_ids,
            ))
        practice_revisions = unit.get("practice_source_revisions") or {}
        for practice_task_id, practice_revision_id in practice_revisions.items():
            if not str(practice_task_id).strip() or not str(practice_revision_id).strip():
                continue
            bindings.append(SourceBinding(
                course_id=document.course_id,
                section_id=str(unit.get("section_id") or "") or None,
                knowledge_node_ids=_unique(unit.get("knowledge_refs") or []),
                practice_task_ids=[str(practice_task_id)],
                source_revisions={f"practice:{practice_task_id}": str(practice_revision_id)},
            ))
        source_keys = [
            str(source_key) for source_key in unit.get("source_keys") or []
            if str(source_key) in vector
        ]
        if source_keys:
            bindings.append(SourceBinding(
                course_id=document.course_id,
                source_revisions={key: vector[key] for key in source_keys},
            ))
        practice_task_id = str(unit.get("practice_task_id") or "")
        practice_revision_id = str(unit.get("practice_revision_id") or "")
        if practice_task_id and practice_revision_id:
            bindings.append(SourceBinding(
                course_id=document.course_id,
                section_id=str(unit.get("section_id") or "") or None,
                knowledge_node_ids=_unique(unit.get("knowledge_refs") or []),
                practice_task_ids=[practice_task_id],
                source_revisions={f"practice:{practice_task_id}": practice_revision_id},
            ))
        result[unit_id] = _dedupe_bindings(bindings or [source_binding_for_document(document)])
    if not result:
        result["__whole__"] = [source_binding_for_document(document)]
    return result


def _dedupe_bindings(bindings: list[SourceBinding]) -> list[SourceBinding]:
    result: list[SourceBinding] = []
    seen: set[str] = set()
    for binding in bindings:
        key = stable_hash(binding.model_dump(mode="json"), prefix="sbd_")
        if key in seen:
            continue
        seen.add(key)
        result.append(binding)
    return result


def _combined_revisions(bindings: list[SourceBinding]) -> dict[str, str]:
    return {
        key: revision
        for binding in bindings
        for key, revision in binding.source_revisions.items()
    }


def _blocks_by_section(document: CourseDocument) -> dict[str, list[CourseBlock]]:
    result: dict[str, list[CourseBlock]] = {}
    for block in sorted(document.blocks, key=lambda item: (item.section_id, item.position)):
        result.setdefault(block.section_id, []).append(block)
    return result


def _learning_sections(document: CourseDocument):
    active_section_ids = {
        block.section_id for block in document.blocks if block.status != "retired"
    }
    return [
        section
        for section in sorted(document.sections, key=lambda item: item.position)
        if section.section_id in active_section_ids
    ]


def _plain_text(markdown: str) -> str:
    text = re.sub(r"```.*?```", "", markdown, flags=re.S)
    text = re.sub(r"[`*_#>\[\]()]", " ", text)
    return " ".join(text.split())


def _section_summary(blocks: list[CourseBlock]) -> str:
    for block in blocks:
        text = _plain_text(str(block.payload.get("summary") or block.payload.get("markdown") or ""))
        if text:
            return text[:180]
    return "围绕本节目标进行概念建构、推导和应用。"


def _objective_dimension(value: str) -> str:
    normalized = str(value or "").lower()
    if any(marker in normalized for marker in ("理解", "解释", "为什么", "含义", "原理", "关系", "本质", "explain", "why")):
        return "conceptual"
    if any(marker in normalized for marker in ("应用", "迁移", "建模", "新情境", "apply", "transfer", "model")):
        return "transfer"
    if any(marker in normalized for marker in ("评价", "比较方案", "设计", "证明", "创造", "evaluate", "design", "prove")):
        return "evaluation"
    return "procedural"


def _objective_teaching_focus(objective: str) -> str:
    return {
        "conceptual": "教学重点放在概念含义、关系与为什么成立",
        "transfer": "教学重点放在适用条件、情境判断与迁移",
        "evaluation": "教学重点放在方案比较、论证与创造",
        "procedural": "教学重点放在规则、步骤与过程校验",
    }[_objective_dimension(objective)]


def _objective_check_prompt(objective: str) -> str:
    dimension = _objective_dimension(objective)
    if dimension == "conceptual":
        return f"让学生脱离步骤说明为什么，并用依据解释：{objective}"
    if dimension == "transfer":
        return f"提供一个新情境，让学生选择方法并解释适用性：{objective}"
    if dimension == "evaluation":
        return f"让学生比较或设计方案，并说明判断标准：{objective}"
    return f"让学生独立完成并校验关键步骤：{objective}"


def _objective_learning_prompt(objective: str) -> str:
    dimension = _objective_dimension(objective)
    if dimension == "conceptual":
        return "阅读时持续追问：它表示什么、为什么成立、与哪些概念相连？"
    if dimension == "transfer":
        return "阅读时持续判断：它适用于什么情境，换一个条件还能否成立？"
    if dimension == "evaluation":
        return "阅读时持续比较：还有哪些方案，判断优劣需要什么标准？"
    return "阅读时持续检查：规则是什么、步骤为何这样排列、怎样验证结果？"


def _section_question_ids(course_data: dict[str, Any], section_id: str) -> list[str]:
    return [
        str(item.get("question_id") or item.get("asset_id") or "")
        for item in ((course_data.get("learning_assets") or {}).get("questions") or [])
        if str(item.get("node_id") or "") == section_id
    ]


def _section_misconceptions(course_data: dict[str, Any], section_id: str) -> list[str]:
    return [
        str(item.get("error_pattern") or "")
        for item in ((course_data.get("learning_assets") or {}).get("misconceptions") or [])
        if str(item.get("node_id") or "") == section_id and item.get("error_pattern")
    ]


def _knowledge_refs_for_blocks(blocks: list[CourseBlock]) -> list[str]:
    return _unique([
        knowledge_id
        for block in blocks
        for knowledge_id in block.concept_refs
    ])


def _course_knowledge_refs(
    document: CourseDocument,
    course_data: dict[str, Any],
) -> list[str]:
    asset_refs = [
        knowledge_id
        for values in (course_data.get("learning_assets") or {}).values()
        if isinstance(values, list)
        for item in values
        if isinstance(item, dict)
        for knowledge_id in item.get("course_knowledge_refs") or []
    ]
    return _unique([
        *[knowledge_id for block in document.blocks for knowledge_id in block.concept_refs],
        *asset_refs,
    ])


def _current_slide_overrides(registry: Any) -> dict[str, dict[str, dict[str, Any]]]:
    representation = next((
        item for item in registry.representations
        if item.representation_type == "slide_deck"
    ), None)
    if representation is None:
        return {}
    spec = next((item for item in registry.specs if item.spec_id == representation.spec_id), None)
    if spec is None:
        return {}
    content = spec.payload.get("content") or {}
    value = content.get("presentation_overrides") or {}
    return deepcopy(value) if isinstance(value, dict) else {}


def _unique(values: list[Any]) -> list[str]:
    return list(dict.fromkeys(
        str(value).strip() for value in values if str(value).strip()
    ))
