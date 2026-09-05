import hashlib
import json
import subprocess
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TASK_CHECKER = ROOT / "scripts" / "check_deploy_task_safety.py"
BACKUP_TOOL = ROOT / "scripts" / "create_verified_data_backup.py"


def _run_task_check(
    path: Path,
    teacher_jobs_dir: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    command = ["python3", str(TASK_CHECKER), str(path)]
    if teacher_jobs_dir is not None:
        command.append(str(teacher_jobs_dir))
    return subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=False,
    )


def test_deploy_task_check_is_read_only_and_blocks_running_or_unknown_tasks(tmp_path):
    task_index = tmp_path / "generation_jobs.json"
    task_index.write_text(json.dumps({
        "done": {"id": "done", "status": "completed"},
        "paused": {"id": "paused", "status": "paused"},
        "active": {"id": "active", "status": "running"},
        "future": {"id": "future", "status": "future_state"},
    }), encoding="utf-8")
    before = task_index.read_bytes()

    result = _run_task_check(task_index)
    payload = json.loads(result.stdout)

    assert result.returncode == 75
    assert payload == {
        "safe_to_stop": False,
        "active_count": 1,
        "unknown_count": 1,
        "task_count": 4,
    }
    assert task_index.read_bytes() == before


def test_deploy_task_check_allows_only_terminal_or_quiescent_tasks(tmp_path):
    task_index = tmp_path / "generation_jobs.json"
    task_index.write_text(json.dumps({
        "done": {"id": "done", "status": "completed"},
        "failed": {"id": "failed", "status": "failed"},
        "paused": {"id": "paused", "status": "waiting_for_review"},
    }), encoding="utf-8")

    result = _run_task_check(task_index)

    assert result.returncode == 0
    assert json.loads(result.stdout)["safe_to_stop"] is True


def test_deploy_task_check_fails_closed_for_unreadable_index(tmp_path):
    task_index = tmp_path / "generation_jobs.json"
    task_index.write_text("{broken", encoding="utf-8")

    result = _run_task_check(task_index)

    assert result.returncode == 75
    assert json.loads(result.stdout)["safe_to_stop"] is False


def test_deploy_task_check_blocks_active_teacher_asset_job_without_writing(tmp_path):
    task_index = tmp_path / "generation_jobs.json"
    task_index.write_text(json.dumps({
        "done": {"id": "done", "status": "completed"},
    }), encoding="utf-8")
    teacher_jobs = tmp_path / "teacher_lesson_authoring"
    teacher_jobs.mkdir()
    authoring = teacher_jobs / "course-1.json"
    authoring.write_text(json.dumps({
        "course_id": "course-1",
        "jobs": {
            "done": {"id": "done", "status": "completed"},
            "active": {"id": "active", "status": "running"},
            "future": {"id": "future", "status": "future_state"},
        },
    }), encoding="utf-8")
    before = authoring.read_bytes()

    result = _run_task_check(task_index, teacher_jobs)
    payload = json.loads(result.stdout)

    assert result.returncode == 75
    assert payload == {
        "safe_to_stop": False,
        "active_count": 1,
        "unknown_count": 1,
        "task_count": 1,
        "teacher_job_active_count": 1,
        "teacher_job_unknown_count": 1,
        "teacher_job_count": 3,
        "teacher_job_file_count": 1,
    }
    assert authoring.read_bytes() == before


def test_deploy_task_check_allows_quiescent_teacher_asset_jobs(tmp_path):
    task_index = tmp_path / "generation_jobs.json"
    task_index.write_text("{}", encoding="utf-8")
    teacher_jobs = tmp_path / "teacher_lesson_authoring"
    teacher_jobs.mkdir()
    (teacher_jobs / "course-1.json").write_text(json.dumps({
        "jobs": [
            {"id": "paused", "status": "paused"},
            {"id": "failed", "status": "failed"},
        ],
    }), encoding="utf-8")

    result = _run_task_check(task_index, teacher_jobs)
    payload = json.loads(result.stdout)

    assert result.returncode == 0
    assert payload["safe_to_stop"] is True
    assert payload["teacher_job_count"] == 2
    assert payload["teacher_job_active_count"] == 0
    assert payload["teacher_job_unknown_count"] == 0


def test_deploy_task_check_fails_closed_for_corrupt_teacher_job_file(tmp_path):
    task_index = tmp_path / "generation_jobs.json"
    task_index.write_text("{}", encoding="utf-8")
    teacher_jobs = tmp_path / "teacher_lesson_authoring"
    teacher_jobs.mkdir()
    (teacher_jobs / "course-1.json").write_text("{broken", encoding="utf-8")

    result = _run_task_check(task_index, teacher_jobs)

    assert result.returncode == 75
    assert json.loads(result.stdout)["safe_to_stop"] is False


def test_data_backup_contains_manifest_checksums_and_is_restore_verified(tmp_path):
    source = tmp_path / "production-data"
    courses = source / "courses"
    courses.mkdir(parents=True)
    (courses / "course-1.json").write_text(
        json.dumps({"course_id": "course-1", "nodes": []}),
        encoding="utf-8",
    )
    (source / "generation_jobs.json").write_text(
        json.dumps({"task-1": {"id": "task-1", "status": "completed"}}),
        encoding="utf-8",
    )
    (source / "teaching-export.pptx").write_bytes(b"binary-last-good")
    before = {
        path.relative_to(source).as_posix(): path.read_bytes()
        for path in source.rglob("*")
        if path.is_file()
    }
    output = tmp_path / "backups" / "data-test.tgz"

    created = subprocess.run(
        [
            "python3",
            str(BACKUP_TOOL),
            "create",
            "--source",
            str(source),
            "--output",
            str(output),
            "--release-version",
            "a" * 40,
        ],
        text=True,
        capture_output=True,
        check=True,
    )
    result = json.loads(created.stdout)

    assert result["schema_version"] == "lingzhi_data_backup_v1"
    assert result["source_release_version"] == "a" * 40
    assert result["file_count"] == 3
    assert result["json_files_checked"] == 2
    assert result["verified_in_isolation"] is True
    checksum_file = output.with_name(f"{output.name}.sha256")
    assert checksum_file.is_file()
    assert checksum_file.read_text().split()[0] == hashlib.sha256(output.read_bytes()).hexdigest()
    with tarfile.open(output, "r:gz") as archive:
        manifest = json.load(archive.extractfile("backup-manifest.json"))
    assert manifest["schema_version"] == "lingzhi_data_backup_v1"
    assert manifest["source_release_version"] == "a" * 40
    assert manifest["file_count"] == 3
    assert {item["path"] for item in manifest["files"]} == {
        "courses/course-1.json",
        "generation_jobs.json",
        "teaching-export.pptx",
    }
    assert before == {
        path.relative_to(source).as_posix(): path.read_bytes()
        for path in source.rglob("*")
        if path.is_file()
    }
    assert not list(output.parent.glob("lingzhi-backup-restore-check-*"))

    verified = subprocess.run(
        ["python3", str(BACKUP_TOOL), "verify", "--archive", str(output)],
        text=True,
        capture_output=True,
        check=True,
    )
    assert json.loads(verified.stdout)["verified_in_isolation"] is True


def test_backup_verify_rejects_tampered_archive_without_touching_source(tmp_path):
    source = tmp_path / "production-data"
    source.mkdir()
    source_file = source / "generation_jobs.json"
    source_file.write_text(json.dumps({}), encoding="utf-8")
    output = tmp_path / "backups" / "data-test.tgz"
    subprocess.run(
        [
            "python3",
            str(BACKUP_TOOL),
            "create",
            "--source",
            str(source),
            "--output",
            str(output),
            "--release-version",
            "legacy-test",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    source_before = source_file.read_bytes()
    with output.open("ab") as handle:
        handle.write(b"tampered")

    verified = subprocess.run(
        ["python3", str(BACKUP_TOOL), "verify", "--archive", str(output)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert verified.returncode != 0
    assert "backup_archive_checksum_mismatch" in verified.stderr
    assert source_file.read_bytes() == source_before


def test_backup_creation_rejects_unreadable_json_without_leaving_artifacts(tmp_path):
    source = tmp_path / "production-data"
    source.mkdir()
    broken = source / "generation_jobs.json"
    broken.write_text("{broken", encoding="utf-8")
    output = tmp_path / "backups" / "data-test.tgz"

    created = subprocess.run(
        [
            "python3",
            str(BACKUP_TOOL),
            "create",
            "--source",
            str(source),
            "--output",
            str(output),
            "--release-version",
            "legacy-test",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert created.returncode != 0
    assert not output.exists()
    assert not output.with_name(f"{output.name}.sha256").exists()
    assert broken.read_text(encoding="utf-8") == "{broken"
