from routers.courses import _resume_summary


def test_resume_summary_projects_only_snapshot_facts():
    summary = _resume_summary({
        "node_id": "node-2",
        "node_name": "矩阵乘法",
        "activity_at": "2026-07-13T10:00:00+00:00",
        "task_state": {
            "kind": "practice",
            "status": "active",
            "object_id": "attempt-1",
        },
    })

    assert summary == {
        "kind": "practice",
        "status": "active",
        "node_id": "node-2",
        "node_name": "矩阵乘法",
        "activity_at": "2026-07-13T10:00:00+00:00",
    }


def test_resume_summary_ignores_snapshot_without_node():
    assert _resume_summary({"task_state": {"kind": "reading", "status": "active"}}) is None
