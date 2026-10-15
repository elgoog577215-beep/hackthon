"""Versioned owner edits of historical open answers, without inherited AI proof."""

from copy import deepcopy
from datetime import datetime, timezone
import json
from typing import Any

from assessment_solution_protocol import OPEN_VALIDATORS, SOLUTION_PROTOCOL
from assessment_validators import validate_solution_envelope
from course_versioning import stable_hash
from question_bank import finalize_v2_question_bank_item, refresh_question_bank_bundle
from solution_contracts import worked_solution_is_complete


REVISION_SCHEMA = "teacher_solution_revision_v1"
_SOLUTION_FIELDS = {
    "canonical_answer", "worked_solution", "rubric", "acceptable_answers",
    "solution_graph", "misconception_rules",
}


def revise_open_question_solution(
    bundle: dict[str, Any], revision_id: str, *,
    expected_solution_revision_id: str, stimulus: str, task: str,
    constraints: list[str], solution_fields: dict[str, Any],
    editor_id: str, note: str,
) -> dict[str, Any]:
    """Create a reviewable revision; old bundles and private solutions stay intact.

    Current protocol questions require their existing final-solution review flow.
    This bounded edit supports historical open questions only, and never creates
    an independent-solver attestation or mastery evidence from an owner's edit.
    """
    if not editor_id.strip() or not note.strip():
        raise ValueError("editor_id and revision note are required")
    if not stimulus.strip() or not task.strip():
        raise ValueError("stimulus and task are required")
    if max(len(stimulus), len(task)) > 12_000 or len(note) > 2000:
        raise ValueError("question wording or revision note is too large")
    if len(json.dumps(solution_fields, ensure_ascii=False).encode("utf-8")) > 100_000:
        raise ValueError("private solution revision is too large")
    if set(solution_fields) != _SOLUTION_FIELDS:
        raise ValueError("supply the complete supported private solution fields")
    if not isinstance(constraints, list) or len(constraints) > 30 or any(
        not isinstance(value, str) or not value.strip() or len(value) > 2000
        for value in constraints
    ):
        raise ValueError("invalid question constraints")

    result = deepcopy(bundle)
    index = next((i for i, item in enumerate(result.get("items") or [])
                  if item.get("revision_id") == revision_id), None)
    if index is None:
        raise KeyError("question item revision not found")
    item = result["items"][index]
    spec = item.get("question_spec") or {}
    old_id = str(item.get("solution_revision_id") or "")
    old_solution = (result.get("solution_envelopes") or {}).get(old_id)
    if old_id != expected_solution_revision_id or spec.get("solution_revision_id") != old_id:
        raise ValueError("private solution revision conflict")
    if not old_solution or spec.get("schema_version") != "question_spec_v2":
        raise ValueError("a V2 private solution is required")
    if item.get("assessment_binding_schema"):
        raise ValueError("use knowledge-bound regeneration for atomic assessments")
    if old_solution.get("validation_mode") not in OPEN_VALIDATORS or (
        spec.get("input_contract") or {}
    ).get("mode") not in {"rich_text", "structured_fields", "language_response", "structured_text"}:
        raise ValueError("only open rubric answers support this revision")
    protocol = item.get("solution_protocol") or old_solution.get("final_solution_review") or {}
    if protocol.get("schema_version") == SOLUTION_PROTOCOL:
        raise ValueError("use the final-solution review flow for protocol questions")

    # Preserve only the grading configuration, never an old review or solver proof.
    solution = {
        "schema_version": "solution_envelope_v1",
        "validation_mode": old_solution["validation_mode"],
        "validator_config": deepcopy(old_solution.get("validator_config") or {}),
        **deepcopy(solution_fields),
        "parent_solution_revision_id": old_id,
        "revision_provenance": {"schema_version": REVISION_SCHEMA,
                                "editor_id": editor_id, "note": note},
    }
    if not isinstance(solution.get("solution_graph"), dict):
        raise ValueError("solution graph must be an object")
    if not worked_solution_is_complete(solution) or not solution.get("rubric"):
        raise ValueError("a complete consistent worked solution and rubric are required")
    graph = solution.get("solution_graph") or {}
    steps = graph.get("steps") or []
    if graph.get("schema_version") != "solution_graph_v1" or len(steps) < 3 or any(
        not isinstance(step, dict) or any(not str(step.get(key) or "").strip()
                                         for key in ("step_id", "action", "check"))
        for step in steps
    ) or len({step["step_id"] for step in steps}) != len(steps):
        raise ValueError("solution graph requires distinct complete steps")
    if not isinstance(solution["rubric"], list) or not all(
        isinstance(value, str) and value.strip() for value in solution["rubric"]
    ):
        raise ValueError("rubric criteria must be nonempty strings")

    spec["stimulus"] = {**spec.get("stimulus", {}), "rendered_text": stimulus.strip()}
    spec["task"] = {**spec.get("task", {}), "rendered_text": task.strip()}
    spec["constraints"] = deepcopy(constraints)
    solution["solution_revision_id"] = stable_hash(
        {"question": {k: v for k, v in spec.items() if k != "solution_revision_id"},
         "solution": solution}, prefix="sol_",
    )
    spec["solution_revision_id"] = solution["solution_revision_id"]
    item.update(
        prompt=f"{stimulus.strip()}\n\n{task.strip()}", constraints=deepcopy(constraints),
        input_materials=[stimulus.strip()], subquestions=[], explanation="",
        parent_revision_id=revision_id, edited_by=editor_id,
        edited_at=datetime.now(timezone.utc).isoformat(),
        review_required=True, generation_status="review_required",
        review_history=[],
        revision_provenance=deepcopy(solution["revision_provenance"]),
    )
    # Old knowledge bindings describe the old task; retain their history only.
    if item.get("knowledge_binding"):
        item["knowledge_binding"] = {**item["knowledge_binding"], "status": "unbound",
                                     "knowledge_ids": [], "knowledge_revision_refs": {}}
        for key in ("course_knowledge_refs", "course_skill_refs", "course_misconception_refs", "course_mastery_refs"):
            item[key] = []
    for key in ("semantic_preflight", "semantic_reviewer_trigger", "generation_audit_summary"):
        item.pop(key, None)
    validation = validate_solution_envelope(spec, solution)
    validation.update(independent_solution_present=False, independent_review_invalidated=True)
    validation["checks"]["independent_agreement"] = False
    item["solution_validation"] = validation
    item["domain_validation"] = deepcopy(validation)
    item = finalize_v2_question_bank_item(item, solution)
    item.update(lifecycle_status="needs_review", review_status="needs_review", review_required=True)
    if not item["quality_report"].get("passed"):
        raise ValueError("revised question failed its structural or final-contract gates")
    result["items"][index] = item
    result["solution_envelopes"][solution["solution_revision_id"]] = solution
    return refresh_question_bank_bundle(result)
