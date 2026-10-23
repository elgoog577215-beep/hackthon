"""Small, read-only task projections. Never copy candidate or teaching bodies."""
from datetime import datetime, timezone

from course_document import stable_hash

KNOWLEDGE_JOBS = {"course_knowledge_tree_generation", "knowledge_first_handout_generation"}
ACTIVE = {"pending", "running"}


def _seconds(start, end):
    try:
        return max(0, int((datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds()))
    except (TypeError, ValueError):
        return None


def job_status(job, server_time):
    value = {key: job[key] for key in (
        "id", "type", "lesson_unit_id", "knowledge_lesson_id", "status", "phase", "progress",
        "created_at", "generation_started_at", "completed_at", "last_content_at", "received_chars",
        "pipeline_stage", "batch_index", "batch_total", "inventory_count", "completed_batches", "relation_count", "model_call_count", "total_model_seconds",
        "failed_stage", "failed_batch_id", "transport_retry_count", "transport_retry_limit", "transport_retry_active_count", "transport_retry_stage",
    ) if key in job}
    value["message"] = str(job.get("message") or "")[:300]
    value["received_chars"] = int(job.get("received_chars") or len(job.get("partial_text") or ""))
    value["elapsed_seconds"] = _seconds(
        job.get("generation_started_at") or job.get("created_at"),
        job.get("completed_at") if job.get("status") not in ACTIVE and job.get("completed_at") else server_time,
    )
    value["activity_age_seconds"] = _seconds(job.get("last_content_at"), server_time)
    return value


def project_status(state, raw, blockers, *, source_mode=""):
    server_time = datetime.now(timezone.utc).isoformat()
    all_jobs = list(state.get("jobs", {}).values())
    active = [job for job in all_jobs if job.get("status") in ACTIVE]
    latest = {}
    for job in all_jobs:
        if job.get("type") in KNOWLEDGE_JOBS:
            latest[(job.get("type"), job.get("knowledge_lesson_id") or job.get("lesson_unit_id"))] = job
    visible_ids = {job["id"] for job in latest.values()} | {job["id"] for job in active}
    # Stream counters and heartbeat revisions deliberately do not invalidate bodies.
    version = stable_hash({
        "document": raw.get("course_document_revision"),
        "knowledge": (raw.get("course_knowledge_base") or {}).get("revision_id"),
        "presentation": (raw.get('knowledge_presentation') or {}).get('revision_id'),
        "inputs": raw.get("knowledge_input_revision"),
        "sources": [(lid, lesson.get("working_revision_id"), lesson.get("working_script_revision_id"))
                    for lid, lesson in state.get("lessons", {}).items()],
        "jobs": [(job["id"], "active" if job.get("status") in ACTIVE else job.get("status")) for job in all_jobs],
    }, prefix="kstatus_")
    return {
        "course_id": raw["course_id"], "server_time": server_time, "result_version": version,
        "jobs": [job_status(job, server_time) for job in all_jobs
                 if job.get("type") in KNOWLEDGE_JOBS and job["id"] in visible_ids],
        "active_jobs": [job_status(job, server_time) for job in active],
        "blocking_job_ids": [job["id"] for job in blockers(state, source_mode=source_mode)],
        "lesson_blocking_job_ids": {
            lid: [job["id"] for job in blockers(state, source_mode=source_mode, lesson_id=lid)]
            for lid in state.get("lessons", {})
        },
    }
