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

    # 刻意不断言事件落在哪个临时路径——那取决于当时生效的隔离机制，属于实现细节。
    # 仓库里有两套隔离，叠加而非互斥：
    #   - 本文件配套的 `LINGZHI_DATA_DIR` 重定向（整棵数据树，进程级）；
    #   - `backend/tests/conftest.py` 的 autouse fixture（把 learning_events.storage
    #     换成 tmp_path 实现，用例级；因此写入实际落在 tmp_path，而非 LINGZHI_DATA_DIR）。
    # 真正要守住的是下面两条：探针事件没有进入受版本控制的账本，且事件仍能读回。
    assert b"isolation-probe" not in (after or b"")
    assert any(
        event.get("user_id") == "isolation-probe"
        for event in learning_events.load_learning_events(user_id="isolation-probe")
    )
