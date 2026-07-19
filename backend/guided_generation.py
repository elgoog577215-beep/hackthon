"""Deterministic state and revision rules for the six-step course workflow."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

from course_versioning import stable_hash


GUIDED_WORKFLOW_SCHEMA = "guided_course_generation_v1"
GUIDED_STEP_KEYS = (
    "requirements",
    "outline",
    "knowledge",
    "teaching",
    "content",
    "release",
)


def _pick(item: dict[str, Any], *keys: str) -> dict[str, Any]:
    return {key: deepcopy(item.get(key)) for key in keys if key in item}


def _knowledge_semantic_payload(knowledge_base: dict[str, Any]) -> dict[str, Any]:
    """Keep the reviewed knowledge meaning stable as downstream bindings are added."""
    return {
        "concept_groups": [
            _pick(
                item,
                "concept_group_id",
                "name",
                "description",
                "learning_purpose",
                "knowledge_point_ids",
            )
            for item in knowledge_base.get("concept_groups") or []
            if isinstance(item, dict)
        ],
        "knowledge_points": [
            _pick(
                item,
                "knowledge_id",
                "name",
                "statement",
                "knowledge_statement",
                "knowledge_type",
                "conditions",
                "boundaries",
                "aliases",
            )
            for item in knowledge_base.get("knowledge_points") or []
            if isinstance(item, dict)
        ],
        "skill_units": [
            _pick(
                item,
                "skill_id",
                "name",
                "observable_behavior",
                "knowledge_ids",
            )
            for item in knowledge_base.get("skill_units") or []
            if isinstance(item, dict)
        ],
        "misconceptions": [
            _pick(
                item,
                "misconception_id",
                "name",
                "description",
                "trigger",
                "correction",
                "primary_knowledge_id",
            )
            for item in knowledge_base.get("misconceptions") or []
            if isinstance(item, dict)
        ],
        "mastery_criteria": [
            _pick(
                item,
                "criterion_id",
                "name",
                "observable_performance",
                "verification_method",
                "knowledge_ids",
            )
            for item in knowledge_base.get("mastery_criteria") or []
            if isinstance(item, dict)
        ],
        "relations": [
            _pick(
                item,
                "source_knowledge_id",
                "target_knowledge_id",
                "source_id",
                "target_id",
                "relation_type",
                "reason",
                "conditions",
                "relation_group_id",
                "group_operator",
            )
            for item in knowledge_base.get("relations") or []
            if isinstance(item, dict)
        ],
    }


def create_guided_workflow(request: dict[str, Any]) -> dict[str, Any]:
    """Create the durable user-facing workflow for a new generation job."""
    now = datetime.now().isoformat()
    requirements_revision = artifact_revision("requirements", {}, request=request)
    steps = []
    for index, key in enumerate(GUIDED_STEP_KEYS, start=1):
        if key == "requirements":
            status = "confirmed"
            confirmed_at = now
            revision = requirements_revision
        elif key == "outline":
            status = "pending"
            confirmed_at = None
            revision = None
        else:
            status = "locked"
            confirmed_at = None
            revision = None
        steps.append(
            {
                "number": index,
                "key": key,
                "status": status,
                "artifact_revision": revision,
                "input_revisions": {},
                "confirmed_at": confirmed_at,
            }
        )
    return {
        "schema_version": GUIDED_WORKFLOW_SCHEMA,
        "current_step": "outline",
        "review_step": None,
        "steps": steps,
        "updated_at": now,
    }


def step_state(workflow: dict[str, Any], step: str) -> dict[str, Any]:
    for item in workflow.get("steps") or []:
        if item.get("key") == step:
            return item
    raise ValueError(f"Unknown guided generation step: {step}")


def is_confirmed(workflow: dict[str, Any] | None, step: str) -> bool:
    if not workflow:
        return False
    return step_state(workflow, step).get("status") == "confirmed"


def mark_running(workflow: dict[str, Any], step: str) -> None:
    current = step_state(workflow, step)
    if current.get("status") != "confirmed":
        current["status"] = "in_progress"
    workflow["current_step"] = step
    workflow["review_step"] = None
    workflow["updated_at"] = datetime.now().isoformat()


def mark_waiting(
    workflow: dict[str, Any],
    step: str,
    *,
    revision: str,
    input_revisions: dict[str, str] | None = None,
) -> None:
    current = step_state(workflow, step)
    current["status"] = "waiting_for_confirmation"
    current["artifact_revision"] = revision
    current["input_revisions"] = deepcopy(
        input_revisions
        if input_revisions is not None
        else expected_input_revisions(workflow, step)
    )
    workflow["current_step"] = step
    workflow["review_step"] = step
    workflow["updated_at"] = datetime.now().isoformat()


def confirm_waiting_step(
    workflow: dict[str, Any],
    step: str,
    *,
    revision: str,
) -> None:
    if workflow.get("review_step") != step:
        raise ValueError(
            f"Current review step is {workflow.get('review_step') or 'none'}, not {step}"
        )
    current = step_state(workflow, step)
    expected_revision = str(current.get("artifact_revision") or "")
    if expected_revision and expected_revision != revision:
        raise ValueError("The reviewed artifact changed; reload it before confirming")
    expected_inputs = expected_input_revisions(workflow, step)
    actual_inputs = {
        str(key): str(value)
        for key, value in (current.get("input_revisions") or {}).items()
        if value
    }
    if actual_inputs != expected_inputs:
        raise ValueError(
            "The reviewed artifact was generated from stale upstream revisions"
        )
    current["status"] = "confirmed"
    current["artifact_revision"] = revision
    current["confirmed_at"] = datetime.now().isoformat()
    next_index = GUIDED_STEP_KEYS.index(step) + 1
    if next_index < len(GUIDED_STEP_KEYS):
        next_step = GUIDED_STEP_KEYS[next_index]
        next_state = step_state(workflow, next_step)
        if next_state.get("status") in {"locked", "needs_regeneration"}:
            next_state["status"] = "pending"
        workflow["current_step"] = next_step
    else:
        workflow["current_step"] = "release"
    workflow["review_step"] = None
    workflow["updated_at"] = datetime.now().isoformat()


def invalidate_after(workflow: dict[str, Any], step: str) -> list[str]:
    """Mark all downstream confirmed/generated artifacts as needing regeneration."""
    changed: list[str] = []
    start = GUIDED_STEP_KEYS.index(step) + 1
    for key in GUIDED_STEP_KEYS[start:]:
        item = step_state(workflow, key)
        item["status"] = "needs_regeneration"
        item["confirmed_at"] = None
        item["artifact_revision"] = None
        item["input_revisions"] = {}
        changed.append(key)
    workflow["current_step"] = GUIDED_STEP_KEYS[start] if start < len(GUIDED_STEP_KEYS) else step
    workflow["review_step"] = None
    workflow["updated_at"] = datetime.now().isoformat()
    return changed


def confirmed_revisions(workflow: dict[str, Any]) -> dict[str, str]:
    return {
        str(item["key"]): str(item["artifact_revision"])
        for item in workflow.get("steps") or []
        if item.get("status") == "confirmed" and item.get("artifact_revision")
    }


def expected_input_revisions(
    workflow: dict[str, Any],
    step: str,
) -> dict[str, str]:
    """Return the exact confirmed upstream revisions a stage is allowed to consume."""
    end = GUIDED_STEP_KEYS.index(step)
    expected: dict[str, str] = {}
    for key in GUIDED_STEP_KEYS[:end]:
        item = step_state(workflow, key)
        revision = str(item.get("artifact_revision") or "")
        if item.get("status") == "confirmed" and revision:
            expected[key] = revision
    return expected


def artifact_revision(
    step: str,
    course_data: dict[str, Any],
    *,
    request: dict[str, Any] | None = None,
) -> str:
    """Compute the stable identity of the product artifact reviewed at one step."""
    if step == "requirements":
        source = request or course_data.get("generation_request") or {}
        payload = {
            key: deepcopy(source.get(key))
            for key in (
                "subject",
                "target_audience",
                "difficulty",
                "composition_style",
                "style",
                "requirements",
                "course_purpose",
                "pedagogy_mode",
                "secondary_mode",
                "secondary_intensity",
                "grounding_strategy",
                "asset_preferences",
                "materials",
                "material_bindings",
            )
        }
        return stable_hash(payload, prefix="req_")
    if step == "outline":
        return stable_hash(
            {
                "course_name": course_data.get("course_name"),
                "course_outline": course_data.get("course_outline") or {},
                "nodes": [
                    {
                        "node_id": node.get("node_id"),
                        "parent_node_id": node.get("parent_node_id"),
                        "node_name": node.get("node_name"),
                        "node_level": node.get("node_level"),
                        "learning_objective": node.get("learning_objective"),
                        "prerequisite_node_ids": node.get("prerequisite_node_ids") or [],
                        "scope_boundary": node.get("scope_boundary"),
                    }
                    for node in course_data.get("nodes") or []
                ],
            },
            prefix="outline_",
        )
    if step == "knowledge":
        knowledge_base = course_data.get("course_knowledge_base") or {}
        return stable_hash(
            _knowledge_semantic_payload(knowledge_base),
            prefix="knowledge_",
        )
    if step == "teaching":
        return stable_hash(
            {
                "knowledge_revision": artifact_revision("knowledge", course_data),
                "course_module_plan": course_data.get("course_module_plan") or {},
                "course_composition_profile": (
                    course_data.get("course_composition_profile") or {}
                ),
                "course_block_distribution": (
                    course_data.get("course_block_distribution") or {}
                ),
                "learning_asset_plan": course_data.get("learning_asset_plan") or {},
                "nodes": [
                    {
                        "node_id": node.get("node_id"),
                        "learning_objective": node.get("learning_objective"),
                        "module_plan": node.get("module_plan") or {},
                        "exercise_plan": node.get("exercise_plan") or {},
                        "examples_plan": node.get("examples_plan") or {},
                    }
                    for node in course_data.get("nodes") or []
                    if int(node.get("node_level") or 1) == 2
                ],
            },
            prefix="teaching_",
        )
    if step == "content":
        return stable_hash(
            {
                "knowledge_revision": artifact_revision("knowledge", course_data),
                "teaching_revision": artifact_revision("teaching", course_data),
                "nodes": [
                    {
                        "node_id": node.get("node_id"),
                        "node_content": node.get("node_content") or "",
                        "grounding_annotations": node.get("grounding_annotations") or [],
                    }
                    for node in course_data.get("nodes") or []
                    if int(node.get("node_level") or 1) == 2
                ],
                "learning_assets": course_data.get("learning_assets") or {},
                "learning_asset_bundle_revision_id": (
                    course_data.get("learning_asset_bundle_revision_id") or ""
                ),
                "course_knowledge_map": course_data.get("course_knowledge_map") or {},
            },
            prefix="content_",
        )
    if step == "release":
        return stable_hash(
            {
                "quality": course_data.get("generation_quality_report") or {},
                "asset_quality": course_data.get("asset_quality_report") or {},
                "coherence_quality": course_data.get("course_coherence_quality_report") or {},
                "source_chain": course_data.get("generation_source_chain_report") or {},
            },
            prefix="release_",
        )
    raise ValueError(f"Unknown guided generation step: {step}")


def build_source_chain_report(
    workflow: dict[str, Any],
    course_data: dict[str, Any],
    *,
    request: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Prove that release artifacts still consume one confirmed revision chain."""
    checks: list[dict[str, Any]] = []
    issues: list[dict[str, str]] = []
    for step in GUIDED_STEP_KEYS[:-1]:
        state = step_state(workflow, step)
        expected = str(state.get("artifact_revision") or "")
        actual = artifact_revision(step, course_data, request=request)
        confirmed = state.get("status") == "confirmed"
        expected_inputs = expected_input_revisions(workflow, step)
        actual_inputs = {
            str(key): str(value)
            for key, value in (state.get("input_revisions") or {}).items()
            if value
        }
        inputs_passed = actual_inputs == expected_inputs
        passed = confirmed and bool(expected) and expected == actual and inputs_passed
        checks.append(
            {
                "step": step,
                "confirmed": confirmed,
                "expected_revision": expected,
                "actual_revision": actual,
                "expected_input_revisions": expected_inputs,
                "actual_input_revisions": actual_inputs,
                "inputs_passed": inputs_passed,
                "passed": passed,
            }
        )
        revision_passed = confirmed and bool(expected) and expected == actual
        if not revision_passed:
            issues.append(
                {
                    "code": f"{step}_revision_mismatch",
                    "step": step,
                    "message": f"{step} is not confirmed or no longer matches its confirmed revision",
                }
            )
        if not inputs_passed:
            issues.append(
                {
                    "code": f"{step}_input_revision_mismatch",
                    "step": step,
                    "message": (
                        f"{step} was not produced from the currently confirmed "
                        "upstream revisions"
                    ),
                }
            )

    knowledge_base = course_data.get("course_knowledge_base") or {}
    knowledge_revision = str(knowledge_base.get("revision_id") or "")
    knowledge_active = knowledge_base.get("lifecycle_status") == "active"
    checks.append(
        {
            "step": "knowledge_binding",
            "knowledge_revision": knowledge_revision,
            "passed": bool(knowledge_revision and knowledge_active),
        }
    )
    if not knowledge_revision or not knowledge_active:
        issues.append(
            {
                "code": "knowledge_base_not_active",
                "step": "knowledge",
                "message": "The current course knowledge blueprint is not active",
            }
        )

    knowledge_map = course_data.get("course_knowledge_map") or {}
    referenced_revision = str(
        knowledge_map.get("course_knowledge_base_revision_id")
        or knowledge_map.get("knowledge_library_revision_id")
        or knowledge_map.get("library_version")
        or ""
    )
    map_passed = not referenced_revision or referenced_revision == knowledge_revision
    checks.append(
        {
            "step": "knowledge_map",
            "knowledge_revision": knowledge_revision,
            "referenced_revision": referenced_revision,
            "passed": map_passed,
        }
    )
    if not map_passed:
        issues.append(
            {
                "code": "knowledge_map_revision_mismatch",
                "step": "content",
                "message": "Course content bindings reference an older knowledge blueprint",
            }
        )

    report = {
        "schema_version": "generation_source_chain_v1",
        "checks": checks,
        "issues": issues,
        "can_publish": not issues,
    }
    report["revision_id"] = stable_hash(report, prefix="gsc_")
    return report


__all__ = [
    "GUIDED_STEP_KEYS",
    "GUIDED_WORKFLOW_SCHEMA",
    "artifact_revision",
    "build_source_chain_report",
    "confirmed_revisions",
    "confirm_waiting_step",
    "create_guided_workflow",
    "expected_input_revisions",
    "invalidate_after",
    "is_confirmed",
    "mark_running",
    "mark_waiting",
    "step_state",
]
