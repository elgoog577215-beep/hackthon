from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "cleanup_legacy_teaching_plan_data.py"
)
SPEC = importlib.util.spec_from_file_location(
    "cleanup_legacy_teaching_plan_data",
    SCRIPT_PATH,
)
assert SPEC and SPEC.loader
cleanup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cleanup)


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def test_cleanup_removes_only_retired_workbench_data_after_backup(tmp_path):
    data_root = tmp_path / "runtime-data"
    course_path = data_root / "courses" / "course-1.json"
    snapshot_path = data_root / "courses" / "course-1.v1.json"
    authoring_path = data_root / "teacher_lesson_authoring" / "course-1.json"
    current_plan = {
        "schema_version": "course_teaching_plan_v3",
        "revision_id": "shared-plan-v3",
        "sections": [{"node_id": "section-1"}],
    }
    _write(course_path, {
        "course_id": "course-1",
        "course_teaching_plan": current_plan,
        "teaching_plan_workbench": {"revisions": [{"revision_id": "old-1"}]},
    })
    _write(snapshot_path, {
        "course_id": "course-1",
        "course_teaching_plan": current_plan,
        "teaching_plan_workbench": {"drafts": {"draft-1": {}}},
    })
    _write(authoring_path, {
        "course_id": "course-1",
        "outline_revision_id": "outline-v1",
        "outline_material_drafts": [{
            "revision_id": "outline-candidate-1",
            "confirmation_required": True,
        }],
        "lessons": {
            "lesson-1": {
                "working_revision_id": "legacy-import-1",
                "confirmed_revision_id": "legacy-import-1",
                "script_confirmation": {"confirmed_revision_id": "script-1"},
                "source_state": "current",
                "legacy_plan_import": {"source": "teaching_plan_workbench"},
                "material_drafts": {
                    "lesson_plan": [{
                        "revision_id": "plan-candidate-1",
                        "confirmation_required": True,
                    }],
                },
                "arrangement": {
                    "working_revision_id": "arrangement-v1",
                    "confirmed_revision_id": "arrangement-v1",
                    "revisions": [{
                        "revision_id": "arrangement-v1",
                        "status": "confirmed",
                        "confirmed": True,
                        "confirmed_at": "2026-08-01T00:00:00+00:00",
                    }],
                },
                "revisions": [{
                    "revision_id": "new-plan-1",
                    "source_outline_revision_id": "outline-v1",
                    "source_arrangement_revision_id": "arrangement-v1",
                    "generation_source": "teacher_edit",
                    "status": "confirmed",
                    "confirmed_at": "2026-08-01T00:00:00+00:00",
                    "plan": {"sections": [{"node_id": "section-1"}]},
                }, {
                    "revision_id": "legacy-import-1",
                    "legacy_source_revision_id": "old-1",
                    "generation_source": "legacy_workbench_import",
                    "plan": {"sections": [{"node_id": "section-1"}]},
                }],
            },
        },
    })

    dry_run = cleanup.run_cleanup(
        data_root=data_root,
        backup_root=tmp_path / "backups",
        apply=False,
    )
    assert dry_run["affected_file_count"] == 3
    assert "teaching_plan_workbench" in json.loads(course_path.read_text())

    report = cleanup.run_cleanup(
        data_root=data_root,
        backup_root=tmp_path / "backups",
        apply=True,
    )

    assert report["affected_file_count"] == 3
    assert report["removed_workbench_envelope_count"] == 2
    assert report["removed_legacy_revision_count"] == 1
    assert report["removed_retired_field_count"] == 11
    backup_dir = Path(report["backup_dir"])
    assert (backup_dir / "courses" / course_path.name).exists()
    assert (backup_dir / "courses" / snapshot_path.name).exists()
    assert (backup_dir / "teacher_lesson_authoring" / authoring_path.name).exists()
    course = json.loads(course_path.read_text(encoding="utf-8"))
    assert "teaching_plan_workbench" not in course
    assert course["course_teaching_plan"] == current_plan
    authoring = json.loads(authoring_path.read_text(encoding="utf-8"))
    lesson = authoring["lessons"]["lesson-1"]
    assert "confirmation_required" not in authoring["outline_material_drafts"][0]
    assert "confirmation_required" not in lesson["material_drafts"]["lesson_plan"][0]
    assert "legacy_plan_import" not in lesson
    assert "confirmed_revision_id" not in lesson
    assert "script_confirmation" not in lesson
    assert [item["revision_id"] for item in lesson["revisions"]] == ["new-plan-1"]
    assert "status" not in lesson["revisions"][0]
    assert "confirmed_at" not in lesson["revisions"][0]
    arrangement = lesson["arrangement"]
    assert "confirmed_revision_id" not in arrangement
    assert "status" not in arrangement["revisions"][0]
    assert "confirmed" not in arrangement["revisions"][0]
    assert "confirmed_at" not in arrangement["revisions"][0]
    assert lesson["working_revision_id"] == "new-plan-1"
    assert lesson["source_state"] == "current"


def test_cleanup_removes_teacher_guided_workflow_and_normalizes_outline_states(tmp_path):
    data_root = tmp_path / "runtime-data"
    jobs_path = data_root / "generation_jobs.json"
    complete_workspace = data_root / "generation_workspaces" / "job-complete.json"
    framework_workspace = data_root / "generation_workspaces" / "job-framework.json"
    _write(complete_workspace, {
        "course_data": {
            "outline_framework_only": False,
            "generation_stage_artifacts": {
                "outline": {
                    "strategy": "teacher_framework_then_lecture_tasks",
                    "status": "completed",
                    "course_contract_status": "completed",
                    "detail_batches": {"L1": {"status": "completed"}},
                },
            },
            "nodes": [{"node_id": "L1", "node_name": "第一讲"}],
        },
    })
    _write(framework_workspace, {
        "course_data": {
            "outline_framework_only": True,
            "nodes": [{"node_id": "L1", "node_name": "第一讲"}],
        },
    })
    _write(jobs_path, {
        "job-complete": {
            "id": "job-complete",
            "course_id": "course-complete",
            "workspace_id": "job-complete",
            "type": "teacher_outline_generation",
            "status": "waiting_for_review",
            "guided_workflow": {"review_step": "outline"},
            "blueprint_confirmed": True,
            "blueprint_revision_id": "outline-v1",
        },
        "job-framework": {
            "id": "job-framework",
            "course_id": "course-framework",
            "workspace_id": "job-framework",
            "type": "teacher_outline_generation",
            "status": "waiting_for_review",
            "guided_workflow": {"review_step": "outline"},
        },
        "student-job": {
            "id": "student-job",
            "course_id": "student-course",
            "type": "course_generation",
            "status": "waiting_for_review",
            "guided_workflow": {"review_step": "outline"},
        },
    })

    report = cleanup.run_cleanup(
        data_root=data_root,
        backup_root=tmp_path / "backups",
        apply=True,
    )

    assert report["affected_file_count"] == 1
    assert report["normalized_teacher_outline_task_count"] == 2
    assert report["removed_retired_field_count"] == 4
    jobs = json.loads(jobs_path.read_text(encoding="utf-8"))
    completed = jobs["job-complete"]
    assert completed["status"] == "completed"
    assert completed["phase"] == "teacher_outline_ready"
    assert completed["progress"] == 100
    assert "guided_workflow" not in completed
    assert "blueprint_confirmed" not in completed
    assert "blueprint_revision_id" not in completed
    framework = jobs["job-framework"]
    assert framework["status"] == "waiting_for_input"
    assert framework["phase"] == "outline_framework_ready"
    assert "guided_workflow" not in framework
    assert jobs["student-job"]["guided_workflow"]["review_step"] == "outline"
    backup_dir = Path(report["backup_dir"])
    assert (backup_dir / "generation_jobs.json").is_file()
