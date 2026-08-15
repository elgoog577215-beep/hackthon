"""仓库级 pytest 引导：把测试期的运行数据写入临时目录。

`backend/storage.py` 在导入期就把 `DATA_DIR` 固化进模块单例，并且
`learning_records`、`practice_attempts`、`learning_snapshots`、`course_evolution`
等派生仓库也在导入期从同一个常量取根路径。所以数据隔离必须发生在任何 backend
模块被导入之前，也就是这个 rootdir 级 conftest 的导入期。

不这样做的话，`pytest backend/tests` 会把测试事件追加进受版本控制的
`backend/data/learning_events.json`，让工作区在每次跑测试后变脏。

`LINGZHI_DATA_DIR` 已经显式设置时保持不变，便于需要检查真实数据目录的场景。
"""

from __future__ import annotations

import atexit
import os
import shutil
import tempfile

if not os.environ.get("LINGZHI_DATA_DIR", "").strip():
    _test_data_dir = tempfile.mkdtemp(prefix="lingzhi-test-data-")
    os.environ["LINGZHI_DATA_DIR"] = _test_data_dir
    atexit.register(shutil.rmtree, _test_data_dir, ignore_errors=True)
