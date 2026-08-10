"""测试期运行数据必须落在临时目录，不能污染受版本控制的 `backend/data`。

回归保护：`pytest backend/tests` 曾经把测试事件追加进
`backend/data/learning_events.json`，让工作区在每次跑测试后变脏。
"""

from __future__ import annotations

import os
from pathlib import Path

import learning_events
import storage as storage_module
from learning_records import learning_record_repository
from practice_attempts import practice_attempt_repository


REPO_DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def test_data_dir_is_redirected_away_from_the_repository():
    assert os.environ.get("LINGZHI_DATA_DIR", "").strip()
    assert Path(storage_module.DATA_DIR).resolve() != REPO_DATA_DIR.resolve()
    assert Path(storage_module.storage._data_dir).resolve() != REPO_DATA_DIR.resolve()


def test_derived_repositories_follow_the_redirected_data_dir():
    for root in (learning_record_repository.root, practice_attempt_repository.root):
        assert Path(root).resolve().is_relative_to(Path(storage_module.DATA_DIR).resolve())


def test_recording_an_event_never_touches_the_versioned_ledger():
    versioned = REPO_DATA_DIR / learning_events.LEARNING_EVENTS_FILE
    before = versioned.read_bytes() if versioned.exists() else None

    learning_events.record_learning_event(
        event_type="learner_self_reported",
        user_id="isolation-probe",
        course_id="isolation-course",
        evidence={"statement": "测试隔离探针"},
    )

    after = versioned.read_bytes() if versioned.exists() else None
    assert after == before

    written = Path(storage_module.DATA_DIR) / learning_events.LEARNING_EVENTS_FILE
    assert written.exists()
    assert any(
        event.get("user_id") == "isolation-probe"
        for event in learning_events.load_learning_events(user_id="isolation-probe")
    )
