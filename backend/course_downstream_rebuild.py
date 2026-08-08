"""The knowledge side's entry into the shared downstream rebuild chain.

`teaching_plan_impact.build_downstream_state` decides *what* needs rebuilding.
`downstream_rebuild.execute_rebuild` (contributed by the teaching-plan side)
决定 *how* — it walks the work list, calls the owning pipeline for each object,
and folds every result back through `record_rebuild_outcome`.

This module is the knowledge side's adapter onto that shared executor. It does
not implement rebuilding: a second executor would give the same course block
two rebuild paths, two failure semantics and two "last usable artifact"
records, which is exactly what both sides agreed to avoid.

What stays here:

- `plan_rebuild`: a read-only preview grouped by owning pipeline, so the
  teacher can see what a rebuild would touch before pressing anything.
- Runner construction for the knowledge chain, reusing the same pipelines the
  teaching-plan side uses.
- The honest `executor_unavailable` path, kept for the case where the shared
  executor is not importable — a button that silently does nothing is worse
  than one that says why.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

REBUILD_PLAN_SCHEMA = "course_downstream_rebuild_plan_v1"

# Downstream item types that a rebuild can target, mapped to the pipeline that
# owns them. Kept aligned with `downstream_rebuild.pipeline_for` — the shared
# executor is the authority; this table only drives the preview grouping.
REBUILD_OWNERS = {
    "section_content": "course_content",
    "course_document": "course_content",
    "block": "course_content",
    "practice": "practice",
    "question": "practice",
    "mastery_criterion": "practice",
    "slide_deck": "representation",
    "lecture": "representation",
    "handout": "representation",
    "lesson_plan": "representation",
    "teaching_representation": "representation",
    "knowledge_binding": "knowledge",
    "knowledge_point": "knowledge",
}

# Only these states are worth acting on. `current` needs nothing; `blocked`
# must not be rebuilt silently (impact could not be determined); a
# `lock_conflict` object is already being written by another chain.
REBUILDABLE_STATES = {"rebuild_required", "candidate"}


@runtime_checkable
class DownstreamRebuildExecutor(Protocol):
    """What the rebuild pipeline must offer for the knowledge UI to drive it.

    Kept intentionally narrow: the caller supplies the course, the objects, and
    who asked. Everything else — batching, concurrency, retry, and folding
    results back through `record_rebuild_outcome` — belongs to the executor.
    """

    async def rebuild_downstream(
        self,
        course_id: str,
        *,
        items: list[dict[str, Any]],
        actor: str,
        request_id: str,
    ) -> dict[str, Any]:
        ...


_executor: DownstreamRebuildExecutor | None = None


def register_downstream_rebuild_executor(executor: DownstreamRebuildExecutor | None) -> None:
    """Plug in the real rebuild pipeline (or clear it, which tests rely on)."""
    global _executor
    _executor = executor


def current_executor() -> DownstreamRebuildExecutor | None:
    return _executor


def _text(value: Any) -> str:
    return str(value or "").strip()


def plan_rebuild(
    downstream: dict[str, Any],
    *,
    object_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Read-only: which downstream objects a rebuild would touch, and who owns them.

    `object_ids` narrows the plan to a teacher's selection. An id that is not
    rebuildable (already current, or blocked) is reported as skipped with the
    reason rather than dropped, so a partial selection never looks like it was
    fully accepted.
    """
    selected = {_text(item) for item in object_ids or [] if _text(item)}
    targets: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for item in (downstream or {}).get("items") or []:
        if not isinstance(item, dict):
            continue
        item_id = _text(item.get("id"))
        item_type = _text(item.get("type"))
        state = _text(item.get("state"))
        if selected and item_id not in selected:
            continue
        row = {
            "type": item_type,
            "id": item_id,
            "state": state,
            "owner": REBUILD_OWNERS.get(item_type, "unassigned"),
        }
        if state not in REBUILDABLE_STATES:
            row["skip_reason"] = (
                "already_current" if state == "current" else state
            )
            skipped.append(row)
            continue
        if row["owner"] == "unassigned":
            # No pipeline claims this type. Saying so beats pretending it was
            # queued and leaving the teacher waiting for a rebuild that will
            # never happen.
            row["skip_reason"] = "no_owning_pipeline"
            skipped.append(row)
            continue
        targets.append(row)

    by_owner: dict[str, int] = {}
    for row in targets:
        by_owner[row["owner"]] = by_owner.get(row["owner"], 0) + 1

    return {
        "schema_version": REBUILD_PLAN_SCHEMA,
        "targets": targets,
        "skipped": skipped,
        "counts": {
            "targets": len(targets),
            "skipped": len(skipped),
            "by_owner": dict(sorted(by_owner.items())),
        },
        "executor_available": _executor is not None,
    }


def build_knowledge_rebuild_runners(
    course_data: dict[str, Any],
    *,
    representation_repository: Any = None,
) -> dict[str, Any]:
    """Wrap the existing pipelines in the shape the shared executor expects.

    Same pipelines the teaching-plan side wires, for the same reason: a course
    block rebuilt because its knowledge changed and one rebuilt because its
    plan changed must go through identical code, or "last usable artifact"
    stops meaning one thing.

    Content and practice have no targeted rebuild entry point yet, so their
    runners fail loudly. The executor turns that into a per-object receipt the
    teacher can read, which beats reporting a rebuild that never happened.
    """

    def representation(_entry: dict[str, Any]) -> dict[str, Any]:
        if representation_repository is None:
            return {"status": "failed", "error": "表达注册表不可用"}
        try:
            from course_document import CourseDocument
            from representation_compiler import rebuild_core_representations_safely

            document = CourseDocument.model_validate(course_data["course_document"])
            outcome = rebuild_core_representations_safely(
                document, course_data, representation_repository,
            )
            return {
                "status": "succeeded",
                "revision": str((outcome or {}).get("registry_revision") or ""),
            }
        except Exception as error:  # noqa: BLE001 - one object must not abort the batch
            logger.warning("Representation rebuild failed: %s", error)
            return {"status": "failed", "error": str(error)}

    def unsupported(entry: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": "failed",
            "error": f"{entry.get('type')} 目前没有可用于定向重建的管线入口",
        }

    return {
        "representation": representation,
        "course_content": unsupported,
        "practice": unsupported,
        "knowledge": unsupported,
    }


async def request_rebuild(
    course_id: str,
    downstream: dict[str, Any],
    *,
    actor: str,
    request_id: str,
    object_ids: list[str] | None = None,
    course_data: dict[str, Any] | None = None,
    representation_repository: Any = None,
    candidate_only: bool = True,
) -> dict[str, Any]:
    """Run the shared executor over the objects this knowledge edit invalidated.

    Defaults to `candidate_only=True`: a rebuild produces candidates for the
    teacher to confirm rather than overwriting published artifacts outright.
    That keeps the knowledge chain consistent with the rest of the product —
    AI- or command-driven changes are proposed, never silently applied.
    """
    plan = plan_rebuild(downstream, object_ids=object_ids)

    if _executor is not None:
        receipt = await _executor.rebuild_downstream(
            course_id, items=plan["targets"], actor=actor, request_id=request_id,
        )
        return {**plan, "status": "requested", "receipt": receipt}

    try:
        from downstream_rebuild import execute_rebuild, rebuild_summary
    except ImportError as error:  # pragma: no cover - shared chain always present
        logger.warning("Shared rebuild chain unavailable: %s", error)
        return {
            **plan,
            "status": "executor_unavailable",
            "message": "下游重建管线尚未接入，本次未触发重建；以上为将要重建的对象清单。",
        }

    if not plan["targets"]:
        return {
            **plan,
            "status": "nothing_to_rebuild",
            "message": "当前没有需要重建的下游对象。",
        }

    result = execute_rebuild(
        downstream,
        runners=build_knowledge_rebuild_runners(
            course_data or {}, representation_repository=representation_repository,
        ),
        only_ids=[row["id"] for row in plan["targets"]],
        candidate_only=candidate_only,
    )
    return {
        **plan,
        "status": "executed",
        "receipts": result["receipts"],
        "rebuild_counts": result["counts"],
        "summary": rebuild_summary(result),
        "downstream": result["downstream"],
    }


def rebuild_plan_snapshot(plan: dict[str, Any]) -> dict[str, Any]:
    """Compact, stable projection for regression snapshots."""
    return {
        "status": _text(plan.get("status")),
        "counts": dict(sorted((plan.get("counts") or {}).items(), key=lambda kv: kv[0])),
        "targets": sorted(
            f"{_text(row.get('type'))}:{_text(row.get('id'))}"
            for row in plan.get("targets") or []
        ),
        "skipped": sorted(
            f"{_text(row.get('type'))}:{_text(row.get('id'))}:{_text(row.get('skip_reason'))}"
            for row in plan.get("skipped") or []
        ),
    }


__all__ = [
    "REBUILDABLE_STATES",
    "REBUILD_OWNERS",
    "REBUILD_PLAN_SCHEMA",
    "DownstreamRebuildExecutor",
    "current_executor",
    "plan_rebuild",
    "rebuild_plan_snapshot",
    "register_downstream_rebuild_executor",
    "request_rebuild",
]
