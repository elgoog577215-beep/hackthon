"""Deterministic state and revision rules for the four-step course workflow."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

from course_versioning import stable_hash

GUIDED_WORKFLOW_SCHEMA = "guided_course_generation_v2"
GUIDED_STEP_KEYS = (
    "requirements",
    "outline",
    "content",
    "release",
)

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


def migrate_guided_workflow(
    workflow: dict[str, Any],
    *,
    request: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Collapse persisted v1 knowledge/teaching gates into the v2 content step."""
    keys = [
        str(item.get("key") or "")
        for item in workflow.get("steps") or []
        if isinstance(item, dict)
    ]
    if (
        workflow.get("schema_version") == GUIDED_WORKFLOW_SCHEMA
        and keys == list(GUIDED_STEP_KEYS)
    ):
        return deepcopy(workflow)

    old_by_key = {
        str(item.get("key") or ""): item
        for item in workflow.get("steps") or []
        if isinstance(item, dict)
    }
    migrated = create_guided_workflow(request or {})
    for key in GUIDED_STEP_KEYS:
        old = old_by_key.get(key)
        if not old:
            continue
        target = step_state(migrated, key)
        for field in (
            "status",
            "artifact_revision",
            "confirmed_at",
            "previous_confirmed_revision",
        ):
            if field in old:
                target[field] = deepcopy(old[field])

    old_review = str(workflow.get("review_step") or "")
    old_current = str(workflow.get("current_step") or "")
    if old_review in {"outline", "content", "release"}:
        migrated["review_step"] = old_review
        migrated["current_step"] = old_review
    elif old_review in {"knowledge", "teaching"}:
        migrated["review_step"] = None
        migrated["current_step"] = "content"
        content = step_state(migrated, "content")
        if content.get("status") in {"locked", "needs_regeneration"}:
            content["status"] = "pending"
    elif old_current in {"outline", "content", "release"}:
        migrated["current_step"] = old_current
    elif old_current in {"knowledge", "teaching"}:
        migrated["current_step"] = "content"

    for key in GUIDED_STEP_KEYS:
        item = step_state(migrated, key)
        if item.get("status") in {
            "confirmed",
            "waiting_for_confirmation",
            "in_progress",
        }:
            item["input_revisions"] = expected_input_revisions(
                migrated,
                key,
            )
        else:
            item["input_revisions"] = {}
    migrated["updated_at"] = datetime.now().isoformat()
    return migrated


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


def _outline_revision_payload(course_data: dict[str, Any]) -> dict[str, Any]:
    """Return only the user-approved directory contract.

    Downstream compilation is allowed to add knowledge, module, difficulty and
    evidence fields to the full plan. Those derived fields must not make the
    already-confirmed directory look edited.
    """
    outline = (
        course_data.get("course_outline")
        or course_data.get("course_plan")
        or {}
    )
    chapters: list[dict[str, Any]] = []
    for chapter in outline.get("chapters") or []:
        if not isinstance(chapter, dict):
            continue
        sections: list[dict[str, Any]] = []
        for section in chapter.get("sections") or []:
            if not isinstance(section, dict):
                continue
            sections.append(
                {
                    "section_number": str(
                        section.get("section_number") or ""
                    ),
                    "node_id": str(section.get("node_id") or ""),
                    "title": str(section.get("title") or ""),
                    "learning_objective": str(
                        section.get("learning_objective") or ""
                    ),
                    "scope_boundary": str(
                        section.get("scope_boundary") or ""
                    ),
                    "assessment": deepcopy(
                        section.get("assessment") or []
                    ),
                    "prerequisite_node_ids": [
                        str(item)
                        for item in (
                            section.get("prerequisite_node_ids") or []
                        )
                        if str(item)
                    ],
                }
            )
        chapters.append(
            {
                "chapter_number": str(
                    chapter.get("chapter_number") or ""
                ),
                "title": str(chapter.get("title") or ""),
                "learning_focus": str(
                    chapter.get("learning_focus") or ""
                ),
                "sections": sections,
            }
        )
    return {
        "course_name": str(course_data.get("course_name") or ""),
        "course_title": str(outline.get("course_title") or ""),
        "positioning": str(outline.get("positioning") or ""),
        "learning_objectives": deepcopy(
            outline.get("learning_objectives") or []
        ),
        "prerequisites": deepcopy(outline.get("prerequisites") or []),
        "chapters": chapters,
        "nodes": [
            {
                "node_id": str(node.get("node_id") or ""),
                "parent_node_id": str(
                    node.get("parent_node_id") or ""
                ),
                "node_name": str(node.get("node_name") or ""),
                "node_level": int(node.get("node_level") or 1),
                "learning_objective": str(
                    node.get("learning_objective") or ""
                ),
                "prerequisite_node_ids": [
                    str(item)
                    for item in (
                        node.get("prerequisite_node_ids") or []
                    )
                    if str(item)
                ],
                "scope_boundary": str(
                    node.get("scope_boundary") or ""
                ),
                "assessment": deepcopy(node.get("assessment") or []),
            }
            for node in course_data.get("nodes") or []
            if isinstance(node, dict)
        ],
    }


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
            _outline_revision_payload(course_data),
            prefix="outline_",
        )
    if step == "content":
        return stable_hash(
            {
                "teaching_plan_revision": (
                    course_data.get("course_teaching_plan") or {}
                ).get("revision_id"),
                "knowledge_revision": (
                    course_data.get("course_knowledge_base") or {}
                ).get("revision_id"),
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
    "migrate_guided_workflow",
    "step_state",
]
