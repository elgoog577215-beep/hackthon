"""Deterministic quality gates for presentation drafts and exports.

The MVP deliberately keeps the blocking authority deterministic.  An LLM may
later attach advisory comments, but it cannot turn a failing deck into a
downloadable artifact.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import Any
from uuid import uuid4

from presentation_models import (
    DeckRevision,
    PresentationDeck,
    QualityIssue,
    QualityReport,
    Slide,
)
from presentation_templates import get_layout, validate_slide_capacity


def revision_checksum(revision: DeckRevision | Mapping[str, Any]) -> str:
    """Return a stable digest used to bind browser render measurements."""

    payload = revision.model_dump(mode="json") if isinstance(revision, DeckRevision) else dict(revision)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _iter_records(snapshot: Mapping[str, Any], *keys: str) -> list[Mapping[str, Any]]:
    for key in keys:
        value = snapshot.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, Mapping)]
        if isinstance(value, Mapping):
            nested = value.get("items")
            if isinstance(nested, list):
                return [item for item in nested if isinstance(item, Mapping)]
    return []


def _ids(records: Iterable[Mapping[str, Any]], *keys: str) -> set[str]:
    result: set[str] = set()
    for record in records:
        for key in keys:
            value = record.get(key)
            if value is not None and str(value).strip():
                result.add(str(value))
                break
    return result


def _publication_allowed(snapshot: Mapping[str, Any]) -> bool | None:
    for container in (snapshot, snapshot.get("publication"), snapshot.get("quality"), snapshot.get("course")):
        if isinstance(container, Mapping) and "publication_allowed" in container:
            return bool(container.get("publication_allowed"))
    if "is_published" in snapshot:
        return bool(snapshot.get("is_published"))
    return None


def _issue(
    code: str,
    message: str,
    *,
    target_type: str = "deck",
    target_id: str = "",
    fix_action: str = "",
    severity: str = "blocking",
) -> QualityIssue:
    return QualityIssue(
        code=code,
        severity=severity,
        message=message,
        target_type=target_type,
        target_id=target_id,
        fix_action=fix_action,
    )


def _slide_text(slide: Slide) -> str:
    return "\n".join(
        [slide.title, slide.subtitle, slide.key_message]
        + [block.title + block.content + "".join(block.items) for block in slide.blocks]
    )


def evaluate_presentation_quality(
    deck: PresentationDeck | Mapping[str, Any],
    revision: DeckRevision | Mapping[str, Any],
    source_snapshot: Mapping[str, Any],
    *,
    render_measurement: Mapping[str, Any] | None = None,
    require_publication: bool = False,
    require_render_measurement: bool = False,
) -> QualityReport:
    """Evaluate the complete deterministic MVP quality contract.

    Draft generation calls this without publication/render requirements.  The
    finalize path enables both and therefore cannot be bypassed by a fallback
    generator or by a stale browser measurement.
    """

    deck_model = deck if isinstance(deck, PresentationDeck) else PresentationDeck.model_validate(deck)
    revision_model = revision if isinstance(revision, DeckRevision) else DeckRevision.model_validate(revision)
    issues: list[QualityIssue] = []

    section_ids = _ids(_iter_records(source_snapshot, "sections", "nodes"), "section_id", "node_id", "id")
    block_ids = _ids(_iter_records(source_snapshot, "blocks", "content_blocks"), "block_id", "id")
    block_revision_ids = _ids(
        _iter_records(source_snapshot, "blocks", "content_blocks"),
        "block_revision_id",
        "internal_revision",
        "revision_id",
    )
    objective_ids = _ids(
        _iter_records(source_snapshot, "objectives", "learning_objectives"),
        "objective_id",
        "id",
    )
    asset_ids = _ids(_iter_records(source_snapshot, "assets", "asset_refs"), "asset_id", "id")
    misconceptions = _iter_records(source_snapshot, "misconceptions", "common_misconceptions")
    practices = _iter_records(source_snapshot, "practices", "exercises", "questions")

    if not revision_model.slides:
        issues.append(_issue("deck_empty", "课件没有任何页面。", fix_action="先生成课件页面"))

    covered_objectives: set[str] = set()
    layouts: set[str] = set()
    for slide in revision_model.slides:
        layouts.add(slide.layout_id)
        root_issues = list(slide.quality.issues)
        issues.extend(root_issues)
        has_blocking_root_issue = any(issue.severity == "blocking" for issue in root_issues)
        if slide.status != "ready" and not has_blocking_root_issue:
            issues.append(_issue(
                "slide_not_ready" if slide.status != "failed" else "slide_generation_failed",
                f"第 {slide.position + 1} 页“{slide.title or slide.slide_id}”尚未就绪。",
                target_type="slide",
                target_id=slide.slide_id,
                fix_action="重新生成或修复该页后再完成课件",
            ))
        try:
            layout = get_layout(slide.layout_id)
        except ValueError:
            issues.append(_issue(
                "unknown_layout",
                f"页面使用了未注册版式 {slide.layout_id}。",
                target_type="slide",
                target_id=slide.slide_id,
                fix_action="选择已注册的课件版式",
            ))
            continue
        if slide.status != "failed":
            missing_slots: list[str] = []
            if "title" in layout.required_slots and not slide.title.strip():
                missing_slots.append("title")
            if "blocks" in layout.required_slots and not slide.blocks:
                missing_slots.append("blocks")
            if missing_slots:
                issues.append(_issue(
                    "layout_required_slot_missing",
                    f"版式 {slide.layout_id} 缺少必填内容槽：{', '.join(missing_slots)}。",
                    target_type="slide",
                    target_id=slide.slide_id,
                    fix_action="补齐本页必填内容后重新检查",
                ))
        if "blocks" in layout.required_slots and slide.blocks and not any(
            block.content.strip() or block.items or any(str(value).strip() for value in block.metadata.values())
            for block in slide.blocks
        ):
            issues.append(_issue(
                "slide_content_missing",
                "页面虽然包含内容块，但没有可讲授的正文、要点或结构化内容。",
                target_type="slide",
                target_id=slide.slide_id,
                fix_action="补充解释、示例或课堂要点",
            ))
        capacity_errors = validate_slide_capacity(
            slide.layout_id,
            [block.model_dump(mode="json") for block in slide.blocks],
            _slide_text(slide),
        )
        for message in capacity_errors:
            issues.append(_issue(
                "slide_capacity_exceeded",
                message,
                target_type="slide",
                target_id=slide.slide_id,
                fix_action="精简本页或拆分为两页",
            ))

        refs = slide.source_refs
        has_trace = bool(
            refs.section_ids or refs.block_ids or refs.objective_ids or refs.asset_ids
        )
        if not has_trace:
            issues.append(_issue(
                "source_refs_missing",
                "页面没有课程来源锚点。",
                target_type="slide",
                target_id=slide.slide_id,
                fix_action="为本页选择课程章节或内容块来源",
            ))
        for value, known, code, label in (
            (refs.section_ids, section_ids, "unknown_section_ref", "章节"),
            (refs.block_ids, block_ids, "unknown_block_ref", "内容块"),
            (refs.objective_ids, objective_ids, "unknown_objective_ref", "学习目标"),
            (refs.asset_ids, asset_ids, "unknown_asset_ref", "素材"),
        ):
            for ref in value:
                if ref not in known:
                    issues.append(_issue(
                        code,
                        f"页面引用的{label} {ref} 不在冻结来源中。",
                        target_type="slide",
                        target_id=slide.slide_id,
                        fix_action="重新选择冻结来源中的内容",
                    ))
        for ref in refs.block_revision_ids:
            if ref not in block_revision_ids:
                issues.append(_issue(
                    "unknown_block_revision_ref",
                    f"页面引用的内容块版本 {ref} 不在冻结来源中。",
                    target_type="slide",
                    target_id=slide.slide_id,
                    fix_action="重新绑定当前冻结来源版本",
                ))
        covered_objectives.update(ref for ref in refs.objective_ids if not objective_ids or ref in objective_ids)

    for objective_id in sorted(objective_ids - covered_objectives):
        issues.append(_issue(
            "objective_not_covered",
            f"学习目标 {objective_id} 尚未被任何页面覆盖。",
            target_type="source",
            target_id=objective_id,
            fix_action="增加或修改一页以覆盖该学习目标",
        ))
    if misconceptions and "L08" not in layouts:
        issues.append(_issue(
            "misconception_slide_required",
            "课程包含常见误区，但课件缺少“常见误区”页面。",
            fix_action="加入一页常见误区（L08）",
        ))
    if practices and "L09" not in layouts:
        issues.append(_issue(
            "practice_slide_required",
            "课程包含练习资产，但课件缺少课堂练习页面。",
            fix_action="加入一页课堂练习（L09）",
        ))

    if require_publication:
        publication = _publication_allowed(source_snapshot)
        if publication is not True:
            issues.append(_issue(
                "source_publication_blocked" if publication is False else "source_publication_unknown",
                "该课件绑定的课程版本尚未通过正式发布质量门。",
                target_type="source",
                target_id=deck_model.source_ref.source_snapshot_id,
                fix_action="先按课程质量报告修复并发布绑定版本",
            ))
        fallback_slides = [
            slide for slide in revision_model.slides
            if any(issue.code == "deterministic_fallback_used" for issue in slide.quality.issues)
        ]
        if fallback_slides:
            issues.append(_issue(
                "deterministic_fallback_export_blocked",
                f"{len(fallback_slides)} 页使用了离线兜底草稿，不能作为正式课件导出。",
                target_type="deck",
                target_id=deck_model.deck_id,
                fix_action="恢复 LLM 连通性后重新生成这些页面",
            ))

    measurement = dict(render_measurement or {})
    if require_render_measurement:
        if not measurement:
            issues.append(_issue(
                "render_measurement_missing",
                "尚未收到浏览器真实渲染测量。",
                target_type="artifact",
                fix_action="打开预览并等待页面完成排版检查",
            ))
        else:
            required_fields = {"revision_checksum", "slide_count", "overflow", "collision"}
            missing_fields = sorted(required_fields - set(measurement))
            valid_types = (
                isinstance(measurement.get("revision_checksum"), str)
                and isinstance(measurement.get("slide_count"), int)
                and not isinstance(measurement.get("slide_count"), bool)
                and isinstance(measurement.get("overflow"), bool)
                and isinstance(measurement.get("collision"), bool)
            )
            if missing_fields or not valid_types:
                issues.append(_issue(
                    "render_measurement_incomplete",
                    "浏览器排版检查缺少完整的版本、页数、溢出或重叠结果。",
                    target_type="artifact",
                    fix_action="等待当前版本预览完成排版检查后重试",
                ))
            expected_checksum = revision_checksum(revision_model)
            actual_checksum = str(measurement.get("revision_checksum") or "")
            if actual_checksum != expected_checksum:
                issues.append(_issue(
                    "render_measurement_stale",
                    "浏览器排版检查不属于当前课件版本。",
                    target_type="artifact",
                    fix_action="刷新预览后重新完成课件",
                ))
            slide_by_id = {slide.slide_id: slide for slide in revision_model.slides}
            overflow_ids = [
                str(slide_id) for slide_id in measurement.get("overflow_slide_ids", [])
                if str(slide_id) in slide_by_id
            ] if isinstance(measurement.get("overflow_slide_ids", []), list) else []
            collision_ids = [
                str(slide_id) for slide_id in measurement.get("collision_slide_ids", [])
                if str(slide_id) in slide_by_id
            ] if isinstance(measurement.get("collision_slide_ids", []), list) else []
            if bool(measurement.get("overflow")) or overflow_ids:
                targets = overflow_ids or [""]
                for slide_id in targets:
                    slide = slide_by_id.get(slide_id)
                    issues.append(_issue(
                        "render_overflow",
                        f"第 {slide.position + 1} 页“{slide.title}”检测到文字溢出。" if slide else "预览检测到文字溢出。",
                        target_type="slide" if slide else "artifact",
                        target_id=slide_id,
                        fix_action="精简本页内容、拆分页，或更换容量更合适的版式",
                    ))
            if bool(measurement.get("collision")) or collision_ids:
                targets = collision_ids or [""]
                for slide_id in targets:
                    slide = slide_by_id.get(slide_id)
                    issues.append(_issue(
                        "render_collision",
                        f"第 {slide.position + 1} 页“{slide.title}”检测到内容重叠。" if slide else "预览检测到内容重叠。",
                        target_type="slide" if slide else "artifact",
                        target_id=slide_id,
                        fix_action="减少本页内容、调整版式，或拆分成两页后重新检查",
                    ))
            measured_count = measurement.get("slide_count")
            if isinstance(measured_count, int) and not isinstance(measured_count, bool) and measured_count != len(revision_model.slides):
                issues.append(_issue(
                    "render_page_count_mismatch",
                    "预览页数与当前课件版本不一致。",
                    target_type="artifact",
                    fix_action="刷新预览并重新检查",
                ))

    return QualityReport(
        report_id=f"qr_{uuid4().hex}",
        deck_id=deck_model.deck_id,
        revision_id=revision_model.revision_id,
        source_snapshot_id=deck_model.source_ref.source_snapshot_id,
        status="blocked" if any(issue.severity == "blocking" for issue in issues) else "passed",
        issues=issues,
        render_measurement=measurement,
    )


__all__ = ["evaluate_presentation_quality", "revision_checksum"]
