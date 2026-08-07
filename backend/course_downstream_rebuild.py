"""The seam between "this needs rebuilding" and "rebuild it".

`teaching_plan_impact.build_downstream_state` decides *what* needs rebuilding
and `record_rebuild_outcome` folds a result back in. The executor between them
does not exist yet: as of this writing `record_rebuild_outcome` has no
production caller on any branch, and the lesson-plan branch states in
`teaching_plan_workbench` that "rebuilds stay with their own pipelines".

So this module defines the command interface and nothing else. It deliberately
does **not** dispatch to `BlockRegenerationService`, the question-bank rebuild
job, or `rebuild_core_representations_safely`. Writing that fan-out here would
mean inventing a second rebuild mechanism next to the one the lesson-plan owner
is building, and would unilaterally fix the write-back contract for a state
machine we share. A button that quietly does its own thing is worse than a
button that says the pipeline is not ready.

What this does provide:

- `DownstreamRebuildExecutor`: the protocol an executor implements.
- `register_downstream_rebuild_executor`: how the real one gets plugged in.
- `plan_rebuild`: the read-only plan — exactly which objects would be rebuilt,
  grouped by type, derived from the downstream state rather than re-derived.
- An explicit `executor_unavailable` result so the UI can say "not yet wired"
  instead of appearing to succeed.

When the executor lands, the only change here should be that
`request_rebuild` finds a registered implementation and returns its receipt.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

REBUILD_PLAN_SCHEMA = "course_downstream_rebuild_plan_v1"

# Downstream item types that a rebuild can target, mapped to the pipeline that
# owns them. The mapping is documentation of the agreed division of labour, not
# a dispatch table — this module never calls any of them.
REBUILD_OWNERS = {
    "section_content": "block_regeneration",
    "practice": "question_bank_rebuild",
    "slide_deck": "representation_compiler",
    "lesson_plan": "representation_compiler",
    "handout": "representation_compiler",
    "practice_sheet": "representation_compiler",
    "outline": "representation_compiler",
    "diagram": "representation_compiler",
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


async def request_rebuild(
    course_id: str,
    downstream: dict[str, Any],
    *,
    actor: str,
    request_id: str,
    object_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Ask the rebuild pipeline to rebuild the planned objects.

    With no executor registered this returns the plan plus
    `status="executor_unavailable"`. That is the honest answer today: the
    teacher sees exactly what would be rebuilt and that the pipeline is not
    connected, rather than a success message for work nobody performed.
    """
    plan = plan_rebuild(downstream, object_ids=object_ids)
    if _executor is None:
        return {
            **plan,
            "status": "executor_unavailable",
            "message": (
                "下游重建管线尚未接入，本次未触发重建；"
                "以上为将要重建的对象清单。"
            ),
        }
    receipt = await _executor.rebuild_downstream(
        course_id,
        items=plan["targets"],
        actor=actor,
        request_id=request_id,
    )
    return {**plan, "status": "requested", "receipt": receipt}


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
