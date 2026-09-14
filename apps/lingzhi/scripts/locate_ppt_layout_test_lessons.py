"""Locate the two approved production lesson records without printing content."""

import json
from pathlib import Path


ROOT = Path("/opt/lingzhi/state/backend-data")
TARGET_BLOCK_ID = "tsb-bb41e5392a8b"
TARGET_TITLES = {
    "设计思维框架与问题定义",
    "原型设计与快速验证",
}


def current_blocks(lesson: dict) -> list[dict]:
    revision_id = str(lesson.get("working_script_revision_id") or "")
    revision = next(
        (
            item
            for item in lesson.get("script_revisions", [])
            if str(item.get("revision_id") or "") == revision_id
        ),
        {},
    )
    return [
        block
        for section in revision.get("sections", [])
        for block in section.get("blocks", [])
    ]


def main() -> None:
    matches = []
    root = ROOT / "teacher_lesson_authoring"
    for path in root.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        course_id = path.stem
        for lesson_id, lesson in payload.get("lessons", {}).items():
            title = str(lesson.get("node_name") or lesson.get("title") or "")
            blocks = current_blocks(lesson)
            if title not in TARGET_TITLES and not any(
                str(block.get("block_id") or "") == TARGET_BLOCK_ID for block in blocks
            ):
                continue
            state = lesson.get("ppt_manuscript") or {}
            task_id = str(state.get("task_id") or "")
            job = payload.get("jobs", {}).get(task_id) or {}
            matches.append(
                {
                    "course_id": course_id,
                    "lesson_id": lesson_id,
                    "title": title,
                    "source_script_revision_id": lesson.get("working_script_revision_id"),
                    "source_lesson_plan_revision_id": lesson.get("working_revision_id"),
                    "ppt_status": state.get("status"),
                    "ppt_task_id": task_id,
                    "job_status": job.get("status"),
                    "job_phase": job.get("phase"),
                    "attempt": job.get("attempt_number"),
                    "error_code": (job.get("error") or {}).get("code"),
                    "failed_block_present": any(
                        str(block.get("block_id") or "") == TARGET_BLOCK_ID
                        for block in blocks
                    ),
                }
            )
    print(json.dumps({"event": "ppt_test_lessons", "matches": matches}, ensure_ascii=True))


if __name__ == "__main__":
    main()
