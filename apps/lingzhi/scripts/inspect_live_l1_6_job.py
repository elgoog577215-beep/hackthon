"""Read a bounded status summary for the approved production PPT recovery."""

import json
from pathlib import Path


COURSE_ID = "afb29754-6842-437b-af1b-5866bfb53b41"
LESSON_ID = "L1-6"
TASK_ID = "tlj-8cd70ab91a694a5882d7fb213bd20241"
SOURCE_ID = "tlsr-276e30d3240818214466eac4"
AUTHORING_PATH = (
    Path("/opt/lingzhi/state/backend-data/teacher_lesson_authoring")
    / f"{COURSE_ID}.json"
)


def main() -> None:
    payload = json.loads(AUTHORING_PATH.read_text(encoding="utf-8"))
    lesson = payload["lessons"][LESSON_ID]
    state = lesson.get("ppt_manuscript") or {}
    job = payload.get("jobs", {}).get(TASK_ID) or {}
    if lesson.get("working_script_revision_id") != SOURCE_ID:
        raise ValueError("source_revision_changed")
    if state.get("task_id") != TASK_ID:
        raise ValueError("task_identity_changed")

    blocks = list((job.get("bundle_blocks") or {}).values())
    repair_units = [
        unit
        for block in blocks
        for unit in (block.get("ppt_page_repair_units") or [])
    ]
    print(
        json.dumps(
            {
                "event": "target_job",
                "lesson_id": LESSON_ID,
                "task_id": TASK_ID,
                "source_revision": SOURCE_ID,
                "state_status": state.get("status"),
                "has_manuscript": bool(state.get("manuscript")),
                "page_count": (state.get("manuscript") or {}).get("page_count", 0),
                "job_status": job.get("status"),
                "phase": job.get("phase"),
                "attempt": job.get("attempt_number"),
                "progress": job.get("progress"),
                "message": job.get("message"),
                "updated_at": job.get("updated_at"),
                "error_code": (job.get("error") or {}).get("code"),
                "checkpoint_blocks": len(blocks),
                "checkpoint_pages": sum(len(block.get("ppt_pages") or []) for block in blocks),
                "repair_units": len(repair_units),
                "repair_units_with_pages": sum(
                    bool(unit.get("ppt_pages")) for unit in repair_units
                ),
                "repair_units_with_errors": sum(
                    bool(unit.get("ppt_errors")) for unit in repair_units
                ),
            },
            ensure_ascii=True,
        ),
        flush=True,
    )

    protected = []
    for number in range(1, 6):
        lesson_id = f"L1-{number}"
        item = payload["lessons"][lesson_id]
        ppt = item.get("ppt_manuscript") or {}
        protected.append(
            {
                "lesson_id": lesson_id,
                "status": ppt.get("status"),
                "can_export": bool(ppt.get("manuscript")),
                "page_count": (ppt.get("manuscript") or {}).get("page_count", 0),
                "source_revision": item.get("working_script_revision_id"),
            }
        )
    print(json.dumps({"event": "protected_lessons", "lessons": protected}), flush=True)


if __name__ == "__main__":
    main()
