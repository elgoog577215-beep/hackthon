from __future__ import annotations

import pytest

from question_bank_jobs import (
    QUESTION_BANK_REBUILD_STAGES,
    QuestionBankRebuildJobRepository,
)


def test_rebuild_job_is_idempotent_and_freezes_requested_scope(tmp_path):
    repository = QuestionBankRebuildJobRepository(tmp_path / "jobs")

    first, first_created = repository.create_job(
        "course-jobs",
        request_id="request-idempotent",
        scope="nodes",
        node_ids=["node-2", "node-1", "node-2"],
        mode="incremental",
        actor_id="teacher-1",
    )
    second, second_created = repository.create_job(
        "course-jobs",
        request_id="request-idempotent",
        scope="nodes",
        node_ids=["node-1", "node-2"],
        mode="incremental",
        actor_id="teacher-1",
    )

    assert first_created is True
    assert second_created is False
    assert second["job_id"] == first["job_id"]
    assert first["scope"] == "nodes"
    assert first["node_ids"] == ["node-1", "node-2"]
    assert first["mode"] == "incremental"
    assert first["status"] == "queued"
    assert [stage["stage_id"] for stage in first["stages"]] == [
        stage_id for stage_id, _ in QUESTION_BANK_REBUILD_STAGES
    ]


def test_rebuild_job_freezes_item_revision_scope(tmp_path):
    repository = QuestionBankRebuildJobRepository(tmp_path / "jobs")

    job, created = repository.create_job(
        "course-jobs",
        request_id="request-item-rework",
        scope="items",
        node_ids=["node-1"],
        revision_ids=["revision-2", "revision-1"],
        mode="incremental",
        actor_id="teacher-1",
    )

    assert created is True
    assert job["scope"] == "items"
    assert job["node_ids"] == ["node-1"]
    assert job["revision_ids"] == ["revision-1", "revision-2"]


def test_rebuild_job_reports_monotonic_fixed_stage_progress(tmp_path):
    repository = QuestionBankRebuildJobRepository(tmp_path / "jobs")
    job, _ = repository.create_job(
        "course-jobs",
        request_id="request-progress",
        scope="course",
        node_ids=[],
        mode="full",
        actor_id="teacher-1",
    )

    running = repository.start(job["job_id"])
    progressed = repository.advance(
        job["job_id"],
        stage_id="question_generation",
        message="正在生成题目",
    )

    assert running["status"] == "running"
    assert progressed["current_stage"] == "question_generation"
    assert progressed["progress"] > running["progress"]
    assert next(
        stage
        for stage in progressed["stages"]
        if stage["stage_id"] == "question_generation"
    )["status"] == "running"
    assert all(
        stage["status"] == "completed"
        for stage in progressed["stages"][
            : progressed["current_stage_index"]
        ]
    )

    with pytest.raises(ValueError, match="cannot move backwards"):
        repository.advance(
            job["job_id"],
            stage_id="source_retrieval",
        )


def test_rebuild_job_completion_and_failure_are_durable(tmp_path):
    repository = QuestionBankRebuildJobRepository(tmp_path / "jobs")
    completed_job, _ = repository.create_job(
        "course-jobs",
        request_id="request-complete",
        scope="course",
        node_ids=[],
        mode="incremental",
        actor_id="teacher-1",
    )
    repository.start(completed_job["job_id"])
    completed = repository.complete(
        completed_job["job_id"],
        result={
            "bundle_revision_id": "qbb-1",
            "publication_mode": "question_bank_partial",
            "review_queue": {"blocking_count": 2},
        },
    )

    assert completed["status"] == "waiting_review"
    assert completed["progress"] == 100
    assert completed["result"]["bundle_revision_id"] == "qbb-1"
    assert repository.load(
        "course-jobs",
        completed_job["job_id"],
    ) == completed

    failed_job, _ = repository.create_job(
        "course-jobs",
        request_id="request-failed",
        scope="course",
        node_ids=[],
        mode="incremental",
        actor_id="teacher-1",
    )
    failed = repository.fail(
        failed_job["job_id"],
        code="model_unavailable",
        message="模型暂不可用",
        retryable=True,
    )

    assert failed["status"] == "failed"
    assert failed["error"] == {
        "code": "model_unavailable",
        "message": "模型暂不可用",
        "retryable": True,
    }


def test_repository_returns_latest_course_job(tmp_path):
    repository = QuestionBankRebuildJobRepository(tmp_path / "jobs")
    repository.create_job(
        "course-jobs",
        request_id="request-first",
        scope="course",
        node_ids=[],
        mode="incremental",
        actor_id="teacher-1",
    )
    second, _ = repository.create_job(
        "course-jobs",
        request_id="request-second",
        scope="nodes",
        node_ids=["node-1"],
        mode="incremental",
        actor_id="teacher-1",
    )

    latest = repository.latest_for_course("course-jobs")

    assert latest is not None
    assert latest["job_id"] == second["job_id"]
    assert repository.latest_for_course("missing-course") is None


def test_repository_returns_latest_active_course_job(tmp_path):
    repository = QuestionBankRebuildJobRepository(tmp_path / "jobs")
    older_active, _ = repository.create_job(
        "course-jobs",
        request_id="request-active",
        scope="course",
        node_ids=[],
        mode="full",
        actor_id="teacher-1",
    )
    completed, _ = repository.create_job(
        "course-jobs",
        request_id="request-completed",
        scope="nodes",
        node_ids=["node-1"],
        mode="incremental",
        actor_id="teacher-1",
    )
    repository.complete(
        completed["job_id"],
        result={
            "review_queue": {"blocking_count": 0},
            "publication_mode": "question_bank_overlay",
        },
    )

    active = repository.active_for_course("course-jobs")

    assert active is not None
    assert active["job_id"] == older_active["job_id"]
    repository.fail(
        older_active["job_id"],
        code="cancelled",
        message="已终止",
        retryable=True,
    )
    assert repository.active_for_course("course-jobs") is None
    assert repository.active_for_course("missing-course") is None


def test_rebuild_job_heartbeat_reports_progress_inside_a_stage(tmp_path):
    repository = QuestionBankRebuildJobRepository(tmp_path / "jobs")
    job, _ = repository.create_job(
        "course-jobs",
        request_id="request-heartbeat",
        scope="nodes",
        node_ids=["node-1"],
        mode="incremental",
        actor_id="teacher-1",
        worker_id="worker-1",
    )
    repository.start(job["job_id"])
    repository.advance(
        job["job_id"],
        stage_id="question_generation",
        message="正在生成题目",
    )

    heartbeat = repository.heartbeat(
        job["job_id"],
        stage_id="question_generation",
        progress=56,
        message="正在生成第 2/3 道候选题",
        details={"completed_items": 2, "total_items": 3},
    )

    assert heartbeat["progress"] == 56
    assert heartbeat["message"] == "正在生成第 2/3 道候选题"
    assert heartbeat["stage_details"] == {
        "completed_items": 2,
        "total_items": 3,
    }
    assert heartbeat["current_stage"] == "question_generation"


def test_rebuild_job_reuses_active_scope_and_replaces_old_worker(tmp_path):
    repository = QuestionBankRebuildJobRepository(tmp_path / "jobs")
    first, created = repository.create_job(
        "course-jobs",
        request_id="request-worker-1",
        scope="nodes",
        node_ids=["node-1"],
        mode="incremental",
        actor_id="teacher-1",
        worker_id="worker-1",
    )
    repository.start(first["job_id"])

    reused, reused_created = repository.create_job(
        "course-jobs",
        request_id="request-worker-2",
        scope="nodes",
        node_ids=["node-1"],
        mode="incremental",
        actor_id="teacher-1",
        worker_id="worker-1",
    )
    replacement, replacement_created = repository.create_job(
        "course-jobs",
        request_id="request-worker-3",
        scope="nodes",
        node_ids=["node-1"],
        mode="incremental",
        actor_id="teacher-1",
        worker_id="worker-2",
    )

    assert created is True
    assert reused_created is False
    assert reused["job_id"] == first["job_id"]
    assert replacement_created is True
    assert replacement["job_id"] != first["job_id"]
    interrupted = repository.load("course-jobs", first["job_id"])
    assert interrupted["status"] == "failed"
    assert interrupted["error"]["code"] == "rebuild_worker_restarted"
