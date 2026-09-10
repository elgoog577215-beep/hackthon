"""Reuse compatible observations, never historical review or apply authority."""
from __future__ import annotations

from typing import Any

from course_document import stable_hash

from .partial_review import retained_analysis
from .semantic_scan import SCAN_CONTRACT, validate_batch


def unit_fingerprint(unit: Any) -> str:
    return stable_hash({**unit.model_dump(mode="json"), "full_text_fields": unit.full_text_fields},
                       prefix="scan-unit-")


def historical_scan_results(
    *, plans: list[Any], source: Any, context: Any, model_identity: str,
    excluded_ids: set[str],
) -> tuple[set[str], list[dict[str, Any]], list[dict[str, Any]]]:
    """Newest matching observation wins; changed requirements or sources fail closed.

    Legacy v2 plans predate explicit contract/content hashes. They require an
    exact course revision vector plus each unit's source revision. New records
    additionally verify the complete indexed unit, including its full text.
    """
    retained, analyses, origins = set(), [], []
    expected = source.impact_summary
    outline = [{k: v for k, v in node.items() if k != "section_snapshot"} for node in context.outline]
    outline_ids = {f"outline:{node['node_id']}" for node in outline}
    fingerprints = {u.unit_id: unit_fingerprint(u) for u in context.units}
    for plan in reversed(plans):
        summary = plan.impact_summary
        if (plan.change_set_id == source.change_set_id
                or plan.user_id != source.user_id or plan.course_id != source.course_id
                or plan.source_kind != "manual_request" or plan.teacher_change_planning is None
                or plan.status not in {"pending", "rejected"}
                or plan.generation_status == "generating"
                or plan.request_text != source.request_text
                or plan.base_revision_vector != context.base_revision_vector
                or summary.get("current_outline") != outline
                or summary.get("source_mode") != context.source_mode
                or summary.get("scan_model_identity") != model_identity
                or summary.get("scan_contract", "teacher_semantic_scan_v2") != SCAN_CONTRACT
                or summary.get("analysis_mode") != "ai_ranked"
                or set(summary.get("request_asset_types") or []) != set(expected.get("request_asset_types") or [])
                or summary.get("clarification_answer_digest", "") != expected.get("clarification_answer_digest", "")
                or plan.teacher_change_planning.intent.clarification_answer_snapshot
                    != source.teacher_change_planning.intent.clarification_answer_snapshot
                or bool(summary.get("clarification_confirmation")) != bool(expected.get("clarification_confirmation"))):
            continue
        coverage = summary.get("coverage") or {}
        revisions = coverage.get("source_revisions") or {}
        hashes = coverage.get("source_fingerprints")
        missing = set(coverage.get("unscanned_unit_ids") or [])
        ids = {u.unit_id for u in context.units
               if u.unit_id not in excluded_ids | retained | missing
               and u.unit_id in revisions and revisions[u.unit_id] == u.source_revision
               # Old outline projections have no per-node revision. The exact
               # tree and course baseline checked above cover their complete
               # input (title, objective, parent and order). Other unversioned
               # legacy sources still cannot be reused without a content hash.
               and (u.source_revision or hashes is not None
                    or (u.asset_type == "outline" and u.unit_id in outline_ids))
               and (hashes is None or hashes.get(u.unit_id) == fingerprints[u.unit_id])}
        if not ids:
            continue
        try:
            analysis = validate_batch(retained_analysis(plan, ids), [{"unit_id": uid} for uid in ids])
        except (TypeError, ValueError):
            continue
        retained.update(ids)
        analyses.append(analysis)
        origins.append({"plan_id": plan.change_set_id, "unit_ids": sorted(ids)})
    return retained, analyses, origins


def directly_failed_units(plan: Any) -> set[str]:
    """Deferred siblings were never tried; only postpone actual failed sources."""
    failures = (plan.impact_summary.get("coverage") or {}).get("failed_batches") or []
    units: set[str] = set()
    for failure in failures:
        ids = failure.get("failed_unit_ids")
        if ids is None:
            # Legacy aggregate outages list the failing request first, followed
            # by deferred work. Do not mistake every deferred unit for a failure.
            ids = (failure.get("unit_ids") or [])[:1] if failure.get("deferred_parts") else failure.get("unit_ids") or []
        units.update(ids)
    return units
