"""Course-planning checkpoint reuse, budgets and evidence projections."""

from __future__ import annotations

from copy import deepcopy
import os
from typing import Any

from course_teaching_plan_v3 import normalize_teaching_plan_skeleton_v3

DEFAULT_COURSE_PLANNING_CONCURRENCY = 4
MAX_COURSE_PLANNING_CONCURRENCY = 8


def _resolve_course_planning_concurrency(value: int | None = None) -> int:
    raw_value: Any = (
        value
        if value is not None
        else os.getenv(
            "COURSE_GENERATION_PLANNING_CONCURRENCY",
            str(DEFAULT_COURSE_PLANNING_CONCURRENCY),
        )
    )
    try:
        parsed = int(raw_value)
    except (TypeError, ValueError):
        parsed = DEFAULT_COURSE_PLANNING_CONCURRENCY
    return max(1, min(MAX_COURSE_PLANNING_CONCURRENCY, parsed))


EVIDENCE_INDEX_FIELDS = (
    "evidence_id",
    "asset_id",
    "document_id",
    "kind",
    "locator",
    "purpose",
    "priority",
    "authority",
    "usage_policy",
    "factual_allowed",
    "confidence",
)


def _compact_evidence_index(catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {key: item[key] for key in EVIDENCE_INDEX_FIELDS if key in item}
        for item in catalog
    ]


def _stamp_evidence_revision(
    target: dict[str, Any] | None,
    source: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """把证据修订 ID 从 plan 盖到另一个阶段产物上（E1 验收用）。

    教案是独立的 V3 对象而非 plan 的副本，且它的 `revision_id` 由自身内容
    哈希得出——所以不能在组装时塞字段（会改变教案修订），只能在这里补盖。
    """
    if not isinstance(target, dict) or not isinstance(source, dict):
        return target
    revision = str(source.get("evidence_package_revision_id") or "")
    if revision:
        target["evidence_package_revision_id"] = revision
    return target


def _semantic_retry_budget() -> int:
    """How many times the teaching plan may retry its failed units.

    A retry only re-runs the batches that fell back to local compilation, so
    each extra pass is cheap.  One retry was too few: a course fails as a
    whole when any single batch is still non-AI after that pass, and the odds
    of one clean pass drop as the batch count grows, which is why larger
    courses failed far more often than the per-batch success rate suggests.
    """
    try:
        value = int(os.getenv("COURSE_TEACHING_PLAN_SEMANTIC_RETRIES", "3"))
    except (TypeError, ValueError):
        value = 3
    return max(1, min(6, value))


def _changed_scope_section_ids(
    previous_contract: dict[str, Any],
    current_contract: dict[str, Any],
) -> set[str] | None:
    """Return the sections whose own responsibility text changed.

    ``None`` means "cannot tell" -- a different section set, a missing previous
    contract, or a schema change. Callers must treat that as a full rebuild.

    Neighbour fields (``order``, ``previous_section_id``,
    ``next_reserved_section``) are compared separately by the caller: they shift
    for a section whose own responsibility is untouched, so folding them in here
    would spread one edit across the course again.
    """
    if not previous_contract or not current_contract:
        return None
    if previous_contract.get("schema_version") != current_contract.get(
        "schema_version"
    ):
        return None
    for key in ("course_title", "positioning", "learning_objectives", "prerequisites"):
        if previous_contract.get(key) != current_contract.get(key):
            # Course-level intent changed; every section's framing moves with it.
            return None

    def _own_responsibility(item: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in item.items()
            if key not in {"order", "previous_section_id", "next_reserved_section"}
        }

    previous_by_id = {
        str(item.get("node_id") or ""): item
        for item in previous_contract.get("section_responsibilities") or []
        if isinstance(item, dict)
    }
    current_by_id = {
        str(item.get("node_id") or ""): item
        for item in current_contract.get("section_responsibilities") or []
        if isinstance(item, dict)
    }
    if set(previous_by_id) != set(current_by_id):
        # Added, removed, or renumbered sections change the knowledge skeleton's
        # ownership map, which no per-section comparison can rescue.
        return None
    previous_order = [
        str(item.get("node_id") or "")
        for item in previous_contract.get("section_responsibilities") or []
        if isinstance(item, dict)
    ]
    current_order = [
        str(item.get("node_id") or "")
        for item in current_contract.get("section_responsibilities") or []
        if isinstance(item, dict)
    ]
    if previous_order != current_order:
        return None
    return {
        node_id
        for node_id, item in current_by_id.items()
        if _own_responsibility(previous_by_id[node_id]) != _own_responsibility(item)
    }


def _retain_unaffected_teaching_plan_state(
    teaching_stage: dict[str, Any],
    *,
    previous_contract: dict[str, Any],
    current_contract: dict[str, Any],
    outline_revision_id: str,
    skeleton_chunk_size: int,
) -> None:
    """Drop only the teaching-plan work an outline edit actually invalidated.

    The stage is cleared outright when the edit cannot be localized. Otherwise
    the knowledge skeleton is truncated to the sections ahead of the first edit
    and every batch inside that stable range survives.

    Two granularities meet here and must not be conflated:

    * the retained skeleton must end on a **chunk** boundary, because the
      chunk-resume path in ``generate_chunked_skeleton`` only accepts a prefix
      equal to ``chunks[:n]``;
    * a batch may span more sections than a chunk, so batch retention is judged
      against the full stable-section range.

    Conflating them either replans the entire skeleton or discards a batch that a
    chunk boundary merely happens to split.

    The batch reuse gate is deliberately untouched -- it is what makes this
    saving observable, and it keys on ``skeleton_revision_id``, so the retained
    skeleton and batches are re-stamped together.
    """
    changed = _changed_scope_section_ids(previous_contract, current_contract)
    skeleton = teaching_stage.get("skeleton")
    stored_batches = teaching_stage.get("batches")
    if (
        changed is None
        or not isinstance(skeleton, dict)
        or not isinstance(stored_batches, dict)
    ):
        teaching_stage.clear()
        return

    # A changed section keeps its frozen knowledge keys, and the batch validator
    # forces a regenerated batch to expand exactly those keys
    # (course_teaching_plan_v3.py:503). Those keys were named after the old
    # title, so a changed section must surrender its knowledge identity instead
    # of keeping a name derived from a title it no longer has. Everything from
    # the first edit onward is therefore replanned.
    ordered_section_ids = [
        str(item.get("node_id") or "")
        for item in current_contract.get("section_responsibilities") or []
        if isinstance(item, dict)
    ]
    skeleton_section_ids = {
        str(item.get("node_id") or "")
        for item in skeleton.get("sections") or []
        if isinstance(item, dict)
    }
    if changed:
        first_changed_index = min(
            index
            for index, node_id in enumerate(ordered_section_ids)
            if node_id in changed
        )
        stable_section_ids = ordered_section_ids[:first_changed_index]
    else:
        stable_section_ids = list(ordered_section_ids)
    stable_section_ids = [
        node_id for node_id in stable_section_ids if node_id in skeleton_section_ids
    ]

    chunk_size = max(1, int(skeleton_chunk_size))
    preserved_chunk_count = len(stable_section_ids) // chunk_size
    if not preserved_chunk_count:
        # Nothing survives at chunk granularity, so the skeleton would be
        # replanned from the start regardless. Do not pretend otherwise.
        teaching_stage.clear()
        return
    skeleton_prefix_ids = set(
        stable_section_ids[: preserved_chunk_count * chunk_size]
    )
    stable_id_set = set(stable_section_ids)

    retained: dict[str, Any] = {}
    dropped: list[str] = []
    for batch_id, item in stored_batches.items():
        if not isinstance(item, dict):
            continue
        section_ids = {str(value) for value in item.get("section_ids") or []}
        # A batch straddling the edit boundary is regenerated whole: batches are
        # the smallest addressable generation unit.
        if section_ids and section_ids <= stable_id_set:
            retained[str(batch_id)] = deepcopy(item)
        else:
            dropped.append(str(batch_id))
    if not retained:
        teaching_stage.clear()
        return

    # Knowledge keys in the retained prefix keep their numbering, because chunks
    # mint keys from the running registry size in directory order. The retained
    # batches therefore still expand exactly the keys they were generated
    # against. Re-stamp through the normalizer so the revision id is minted by
    # the same rule production uses everywhere else.
    truncated_skeleton = deepcopy(skeleton)
    truncated_skeleton["sections"] = [
        item
        for item in truncated_skeleton.get("sections") or []
        if isinstance(item, dict)
        and str(item.get("node_id") or "") in skeleton_prefix_ids
    ]
    truncated_skeleton["knowledge_registry"] = [
        item
        for item in truncated_skeleton.get("knowledge_registry") or []
        if isinstance(item, dict)
        and str(item.get("owner_node_id") or "") in skeleton_prefix_ids
    ]
    refreshed_skeleton = normalize_teaching_plan_skeleton_v3(
        truncated_skeleton,
        outline_revision_id=outline_revision_id,
    )
    refreshed_revision_id = str(refreshed_skeleton.get("revision_id") or "")
    # The retained batches are NOT re-stamped here on purpose: the skeleton's
    # final revision only exists after the remaining chunks are replanned.
    # `_rekey_retained_batches_to_skeleton` does it at that point.

    preserved_chunk_total = int(teaching_stage.get("skeleton_chunk_count") or 0)
    teaching_stage.clear()
    teaching_stage.update({
        "status": "in_progress",
        "schema_version": "course_teaching_plan_v3",
        "source_outline_revision_id": outline_revision_id,
        "skeleton": refreshed_skeleton,
        "skeleton_revision_id": refreshed_revision_id,
        "skeleton_chunk_count": preserved_chunk_total,
        "completed_skeleton_chunk_count": preserved_chunk_count,
        "batches": retained,
        "outline_edit_scope": {
            "changed_section_ids": sorted(changed),
            "retained_batch_ids": sorted(retained),
            "invalidated_batch_ids": sorted(dropped),
            "awaiting_skeleton_rekey": True,
        },
    })


def _rekey_retained_batches_to_skeleton(
    teaching_stage: dict[str, Any],
    skeleton: dict[str, Any],
) -> None:
    """Point batches retained across an outline edit at the rebuilt skeleton.

    Only runs once per edit, and only for batches whose sections still own the
    same knowledge keys in the rebuilt skeleton. A batch that fails that check is
    left stamped with its old revision so the reuse gate regenerates it -- the
    conservative outcome, and the one that keeps a stale plan out of the course.
    """
    scope = teaching_stage.get("outline_edit_scope")
    if not isinstance(scope, dict) or not scope.get("awaiting_skeleton_rekey"):
        return
    stored_batches = teaching_stage.get("batches")
    if not isinstance(stored_batches, dict):
        return
    revision_id = str(skeleton.get("revision_id") or "")
    owned_by_section = {
        str(item.get("node_id") or ""): list(item.get("owned_knowledge_keys") or [])
        for item in skeleton.get("sections") or []
        if isinstance(item, dict)
    }
    rekeyed: list[str] = []
    for batch_id in list(scope.get("retained_batch_ids") or []):
        item = stored_batches.get(str(batch_id))
        if not isinstance(item, dict):
            continue
        payload = item.get("payload")
        payload_sections = (
            payload.get("sections") if isinstance(payload, dict) else None
        )
        if not isinstance(payload_sections, list):
            continue
        still_matches = True
        for section in payload_sections:
            if not isinstance(section, dict):
                continue
            node_id = str(section.get("node_id") or "")
            planned_keys = [
                str(detail.get("knowledge_key") or "")
                for detail in section.get("knowledge_details") or []
                if isinstance(detail, dict)
            ]
            if planned_keys != owned_by_section.get(node_id, []):
                still_matches = False
                break
        if not still_matches:
            continue
        item["skeleton_revision_id"] = revision_id
        if isinstance(payload, dict):
            payload["skeleton_revision_id"] = revision_id
        rekeyed.append(str(batch_id))
    scope["awaiting_skeleton_rekey"] = False
    scope["rekeyed_batch_ids"] = sorted(rekeyed)

__all__: list[str] = []
