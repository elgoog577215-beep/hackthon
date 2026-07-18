from __future__ import annotations

from copy import deepcopy

from question_bank import (
    reconcile_scoped_question_bank,
    recalculate_question_bank_coverage,
)


def _item(
    item_id: str,
    node_id: str,
    *,
    status: str = "approved",
    solution_id: str | None = None,
) -> dict:
    objective_ref = f"objective:{node_id}"
    return {
        "item_id": item_id,
        "revision_id": f"revision:{item_id}",
        "node_id": node_id,
        "node_ids": [node_id],
        "course_objective_refs": [objective_ref],
        "assessment_role": "practice",
        "lifecycle_status": status,
        "review_status": status,
        "review_required": status == "needs_review",
        "quality_report": {"passed": True, "issues": []},
        "solution_revision_id": solution_id or f"solution:{item_id}",
    }


def _bundle(items: list[dict]) -> dict:
    return {
        "schema_version": "question_bank_bundle_v1",
        "course_id": "course-scoped",
        "course_scope": {
            "course_id": "course-scoped",
            "cross_course_access": False,
        },
        "assessment_profile": {"profile_revision_id": "profile:new"},
        "assessment_objectives": [
            {
                "objective_id": "objective:node-a",
                "node_id": "node-a",
            },
            {
                "objective_id": "objective:node-b",
                "node_id": "node-b",
            },
        ],
        "solution_envelopes": {
            str(item["solution_revision_id"]): {
                "solution_revision_id": item["solution_revision_id"],
            }
            for item in items
        },
        "items": deepcopy(items),
        "coverage": {},
        "assessment_blueprint": {},
        "web_enrichment": {},
        "review_queue": {},
    }


def _course() -> dict:
    return {
        "course_id": "course-scoped",
        "nodes": [
            {
                "node_id": "node-a",
                "node_level": 2,
                "node_name": "A",
                "learning_objective": "objective:node-a",
            },
            {
                "node_id": "node-b",
                "node_level": 2,
                "node_name": "B",
                "learning_objective": "objective:node-b",
            },
        ],
    }


def test_scoped_rebuild_preserves_unselected_nodes_and_private_solutions():
    previous = _bundle([
        _item("old-a", "node-a"),
        _item("old-b", "node-b"),
    ])
    rebuilt = _bundle([
        _item("new-a", "node-a", status="needs_review"),
        _item("new-b", "node-b", status="needs_review"),
    ])

    merged = reconcile_scoped_question_bank(
        previous,
        rebuilt,
        node_ids=["node-a"],
        preserve_reviewed=False,
    )

    by_id = {item["item_id"]: item for item in merged["items"]}
    assert set(by_id) == {"new-a", "old-b", "old-a"}
    assert by_id["old-a"]["lifecycle_status"] == "retired"
    assert by_id["old-b"]["lifecycle_status"] == "approved"
    assert by_id["new-a"]["lifecycle_status"] == "needs_review"
    assert set(merged["solution_envelopes"]) == {
        "solution:new-a",
        "solution:old-a",
        "solution:old-b",
    }


def test_incremental_scoped_rebuild_keeps_reviewed_selected_revision():
    old_a = _item("stable-a", "node-a")
    old_a["review_history"] = [{"decision": "approved"}]
    previous = _bundle([old_a, _item("old-b", "node-b")])
    rebuilt = _bundle([
        _item("stable-a", "node-a", status="needs_review"),
        _item("new-b", "node-b", status="needs_review"),
    ])

    merged = reconcile_scoped_question_bank(
        previous,
        rebuilt,
        node_ids=["node-a"],
        preserve_reviewed=True,
    )

    by_id = {item["item_id"]: item for item in merged["items"]}
    assert by_id["stable-a"]["revision_id"] == "revision:stable-a"
    assert by_id["stable-a"]["lifecycle_status"] == "approved"
    assert by_id["old-b"]["lifecycle_status"] == "approved"
    assert "new-b" not in by_id


def test_scoped_rebuild_recalculates_coverage_from_merged_publication_state():
    merged = _bundle([
        _item("approved-a", "node-a"),
        _item("review-b", "node-b", status="needs_review"),
    ])

    refreshed = recalculate_question_bank_coverage(
        _course(),
        merged,
    )

    assert refreshed["coverage"]["required_objective_count"] == 2
    assert refreshed["coverage"]["covered_objective_count"] == 1
    assert refreshed["coverage"]["coverage_ratio"] == 0.5
    assert refreshed["coverage"]["status"] == "blocked"
    assert refreshed["coverage"]["missing_required_objectives"] == [
        {
            "node_id": "node-b",
            "objective": "objective:node-b",
            "knowledge_points": [],
            "difficulty": "medium",
        }
    ]
