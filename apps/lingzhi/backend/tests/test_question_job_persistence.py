import json
from pathlib import Path

import pytest

from question_bank_jobs import QuestionBankRebuildJobRepository


def test_transient_windows_file_sharing_does_not_fail_generation(tmp_path, monkeypatch):
    path = tmp_path / "job.json"
    repository = QuestionBankRebuildJobRepository(tmp_path)
    repository._write(path, {"version": 1})
    replace = Path.replace
    attempts = []

    def briefly_locked(source, destination):
        attempts.append(source)
        if len(attempts) < 3:
            error = PermissionError("reader temporarily holds destination")
            error.winerror = 5
            raise error
        return replace(source, destination)

    monkeypatch.setattr(Path, "replace", briefly_locked)
    repository._write(path, {"version": 2})
    assert json.loads(path.read_text()) == {"version": 2}
    assert len(attempts) == 3
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize("windows_error", [5, 32, 33, None])
def test_persistent_write_error_preserves_previous_job_and_cleans_temp(tmp_path, monkeypatch, windows_error):
    path = tmp_path / "job.json"
    repository = QuestionBankRebuildJobRepository(tmp_path)
    repository._write(path, {"version": 1})
    attempts = []

    def denied(source, destination):
        attempts.append(source)
        error = OSError("cannot replace")
        if windows_error:
            error.winerror = windows_error
        raise error

    monkeypatch.setattr(Path, "replace", denied)
    with pytest.raises(OSError, match="cannot replace"):
        repository._write(path, {"version": 2})
    assert json.loads(path.read_text()) == {"version": 1}
    assert len(attempts) <= 6
    if windows_error is None:
        assert len(attempts) == 1
    assert not list(tmp_path.glob("*.tmp"))


def test_poll_reads_share_the_writer_lock(tmp_path, monkeypatch):
    repository = QuestionBankRebuildJobRepository(tmp_path)
    path = tmp_path / "job.json"
    repository._write(path, {"version": 1})
    original_open = Path.open
    class TrackingLock:
        held = False
        def __enter__(self):
            self.held = True
        def __exit__(self, *args):
            self.held = False
    lock = TrackingLock()
    repository._lock = lock
    def locked_open(self, *args, **kwargs):
        assert lock.held, "polling must not hold a Windows read handle during replacement"
        return original_open(self, *args, **kwargs)
    monkeypatch.setattr(Path, "open", locked_open)
    assert repository._read(path)["version"] == 1
