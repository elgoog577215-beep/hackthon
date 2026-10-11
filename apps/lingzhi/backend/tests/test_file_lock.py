"""A second process cannot enter a held writer lock on either platform."""
import os
from pathlib import Path
import subprocess
import sys

import file_lock


def test_file_lock_excludes_another_process_and_preserves_position(tmp_path):
    path = tmp_path / "writer.lock"
    child = """
import sys
import file_lock
with open(sys.argv[1], 'a+b') as handle:
    try:
        file_lock.flock(handle, file_lock.LOCK_EX | file_lock.LOCK_NB)
    except OSError:
        sys.exit(7)
    file_lock.flock(handle, file_lock.LOCK_UN)
"""
    env = {**os.environ, "PYTHONPATH": str(Path(file_lock.__file__).parent)}
    with path.open("a+b") as handle:
        handle.write(b"test")
        handle.flush()
        handle.seek(2)
        file_lock.flock(handle, file_lock.LOCK_EX)
        assert handle.tell() == 2
        held = subprocess.run([sys.executable, "-c", child, str(path)], env=env, timeout=10)
        assert held.returncode == 7
        file_lock.flock(handle, file_lock.LOCK_UN)
        assert handle.tell() == 2
    released = subprocess.run([sys.executable, "-c", child, str(path)], env=env, timeout=10)
    assert released.returncode == 0
