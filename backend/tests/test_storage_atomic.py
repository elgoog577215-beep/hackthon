"""
Storage 原子写入、并发锁和版本管理单元测试。
覆盖 task 2.1 的所有功能点。
"""

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio

# 将 backend 目录和项目根目录加入 sys.path
_backend_dir = os.path.join(os.path.dirname(__file__), "..")
_project_root = os.path.join(_backend_dir, "..")
sys.path.insert(0, _backend_dir)
sys.path.insert(0, _project_root)

from storage import Storage
from models import ValidationReport


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def tmp_storage(tmp_path: Path) -> Storage:
    """创建使用临时目录的 Storage 实例。"""
    s = Storage(data_dir=str(tmp_path), max_versions=3)
    return s


def _course_data(name: str = "测试课程", nodes: int = 1) -> dict:
    """生成简单的课程数据字典。"""
    return {
        "course_id": "c1",
        "course_name": name,
        "nodes": [{"node_id": f"n{i}", "node_name": f"Node {i}"} for i in range(nodes)],
    }


# ---------------------------------------------------------------------------
# _atomic_write 测试
# ---------------------------------------------------------------------------

class TestAtomicWrite:
    """测试原子写入方法。"""

    @pytest.mark.asyncio
    async def test_atomic_write_creates_file(self, tmp_storage: Storage, tmp_path: Path):
        """原子写入应创建目标文件。"""
        filepath = tmp_path / "courses" / "test.json"
        data = {"key": "value"}
        await tmp_storage._atomic_write(filepath, data)

        assert filepath.exists()
        with open(filepath, "r", encoding="utf-8") as f:
            assert json.load(f) == data

    @pytest.mark.asyncio
    async def test_atomic_write_no_tmp_left_on_success(self, tmp_storage: Storage, tmp_path: Path):
        """成功写入后不应留下 .tmp 文件。"""
        filepath = tmp_path / "courses" / "test.json"
        await tmp_storage._atomic_write(filepath, {"a": 1})

        tmp_file = filepath.with_suffix(".json.tmp")
        assert not tmp_file.exists()

    @pytest.mark.asyncio
    async def test_atomic_write_preserves_old_on_failure(self, tmp_storage: Storage, tmp_path: Path):
        """写入失败时应保留原有文件内容。"""
        filepath = tmp_path / "courses" / "original.json"
        original_data = {"version": "original"}
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(original_data, f)

        # 模拟 os.replace 失败
        with patch("os.replace", side_effect=OSError("disk full")):
            with pytest.raises(OSError):
                await tmp_storage._atomic_write(filepath, {"version": "new"})

        # 原文件应保持不变
        with open(filepath, "r", encoding="utf-8") as f:
            assert json.load(f) == original_data

    @pytest.mark.asyncio
    async def test_atomic_write_cleans_tmp_on_failure(self, tmp_storage: Storage, tmp_path: Path):
        """写入失败时应清理 .tmp 文件。"""
        filepath = tmp_path / "courses" / "clean.json"

        with patch("os.replace", side_effect=OSError("fail")):
            with pytest.raises(OSError):
                await tmp_storage._atomic_write(filepath, {"data": True})

        tmp_file = filepath.with_suffix(".json.tmp")
        assert not tmp_file.exists()


# ---------------------------------------------------------------------------
# 并发锁测试
# ---------------------------------------------------------------------------

class TestConcurrencyLock:
    """测试按 course_id 的 asyncio.Lock 文件级锁。"""

    @pytest.mark.asyncio
    async def test_same_course_gets_same_lock(self, tmp_storage: Storage):
        """同一 course_id 应返回同一把锁。"""
        lock1 = await tmp_storage._get_lock("course_a")
        lock2 = await tmp_storage._get_lock("course_a")
        assert lock1 is lock2

    @pytest.mark.asyncio
    async def test_different_courses_get_different_locks(self, tmp_storage: Storage):
        """不同 course_id 应返回不同的锁。"""
        lock1 = await tmp_storage._get_lock("course_a")
        lock2 = await tmp_storage._get_lock("course_b")
        assert lock1 is not lock2

    @pytest.mark.asyncio
    async def test_concurrent_writes_serialized(self, tmp_storage: Storage):
        """同一课程的并发写入应串行执行（不会交错）。"""
        order: list[str] = []

        async def write_with_tracking(course_id: str, label: str):
            await tmp_storage.save_course(course_id, _course_data(name=label))
            order.append(label)

        # 并发写入同一课程
        await asyncio.gather(
            write_with_tracking("c1", "write_1"),
            write_with_tracking("c1", "write_2"),
        )

        # 两次写入都应完成
        assert len(order) == 2
        # 最终文件应是有效 JSON
        filepath = Path(tmp_storage._courses_dir) / "c1.json"
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["course_name"] in ("write_1", "write_2")


class TestCourseSummary:
    """课程库摘要只统计真正可学习的二级课节。"""

    @pytest.mark.asyncio
    async def test_canonical_summary_excludes_chapter_sections(self, tmp_storage: Storage):
        await tmp_storage.save_course("canonical", {
            "course_id": "canonical",
            "course_name": "正式课程",
            "course_document": {
                "sections": [
                    {"section_id": "c1", "level": 1},
                    {"section_id": "l1", "level": 2},
                    {"section_id": "l2", "level": 2},
                ],
            },
        })

        summary = next(item for item in tmp_storage.list_courses() if item["course_id"] == "canonical")
        assert summary["node_count"] == 2
        assert summary["is_published"] is True

    @pytest.mark.asyncio
    async def test_legacy_summary_excludes_chapter_nodes(self, tmp_storage: Storage):
        await tmp_storage.save_course("legacy", {
            "course_id": "legacy",
            "course_name": "旧课程",
            "nodes": [
                {"node_id": "c1", "node_level": 1},
                {"node_id": "l1", "node_level": 2},
            ],
        })

        summary = next(item for item in tmp_storage.list_courses() if item["course_id"] == "legacy")
        assert summary["node_count"] == 1

    @pytest.mark.asyncio
    async def test_summary_survives_malformed_section_level(self, tmp_storage: Storage):
        await tmp_storage.save_course("malformed", {
            "course_id": "malformed",
            "course_name": "层级异常课程",
            "course_document": {
                "sections": [
                    {"section_id": "bad", "level": "lesson"},
                    {"section_id": "l1", "level": 2},
                ],
            },
        })

        summary = next(item for item in tmp_storage.list_courses() if item["course_id"] == "malformed")
        assert summary["node_count"] == 1

    @pytest.mark.asyncio
    async def test_summary_exposes_unpublished_generation_shell(self, tmp_storage: Storage):
        await tmp_storage.save_course("shell", {
            "course_id": "shell",
            "course_name": "生成占位",
            "generation_job_id": "job-shell",
            "generation_status": "queued",
            "course_document": {"sections": []},
        })

        summary = next(item for item in tmp_storage.list_courses() if item["course_id"] == "shell")
        assert summary["generation_job_id"] == "job-shell"
        assert summary["generation_status"] == "queued"
        assert summary["is_published"] is False


# ---------------------------------------------------------------------------
# 版本快照测试
# ---------------------------------------------------------------------------

class TestSnapshot:
    """测试版本快照创建和管理。"""

    @pytest.mark.asyncio
    async def test_save_creates_snapshot(self, tmp_storage: Storage):
        """第二次保存应创建第一个版本的快照。"""
        await tmp_storage.save_course("c1", _course_data(name="v1"))
        await tmp_storage.save_course("c1", _course_data(name="v2"))

        snapshots = tmp_storage._get_snapshot_paths("c1")
        assert len(snapshots) == 1
        # 快照应包含 v1 的数据
        with open(snapshots[0], "r", encoding="utf-8") as f:
            snap_data = json.load(f)
        assert snap_data["course_name"] == "v1"

    @pytest.mark.asyncio
    async def test_snapshot_limit_enforced(self, tmp_storage: Storage):
        """快照数量不应超过 max_versions (3)。"""
        for i in range(6):
            await tmp_storage.save_course("c1", _course_data(name=f"v{i}"))

        snapshots = tmp_storage._get_snapshot_paths("c1")
        assert len(snapshots) <= 3

    @pytest.mark.asyncio
    async def test_oldest_snapshot_deleted(self, tmp_storage: Storage):
        """超出上限时应删除最旧的快照。"""
        for i in range(5):
            await tmp_storage.save_course("c1", _course_data(name=f"v{i}"))

        snapshots = tmp_storage._get_snapshot_paths("c1")
        versions = [tmp_storage._get_snapshot_version(s) for s in snapshots]
        # 最旧的版本应已被删除
        assert 1 not in versions

    @pytest.mark.asyncio
    async def test_snapshot_naming_convention(self, tmp_storage: Storage):
        """快照文件应遵循 {course_id}.v{N}.json 命名。"""
        await tmp_storage.save_course("c1", _course_data(name="v1"))
        await tmp_storage.save_course("c1", _course_data(name="v2"))

        snapshots = tmp_storage._get_snapshot_paths("c1")
        assert len(snapshots) == 1
        assert snapshots[0].name == "c1.v1.json"


# ---------------------------------------------------------------------------
# 回滚测试
# ---------------------------------------------------------------------------

class TestRollback:
    """测试课程回滚功能。"""

    @pytest.mark.asyncio
    async def test_rollback_restores_data(self, tmp_storage: Storage):
        """回滚应恢复指定版本的数据。"""
        await tmp_storage.save_course("c1", _course_data(name="v1"))
        await tmp_storage.save_course("c1", _course_data(name="v2"))

        # 回滚到 v1
        result = await tmp_storage.rollback_course("c1", version=1)
        assert result["course_name"] == "v1"

        # 缓存也应更新
        loaded = tmp_storage.load_course("c1")
        assert loaded["course_name"] == "v1"

    @pytest.mark.asyncio
    async def test_rollback_nonexistent_version_raises(self, tmp_storage: Storage):
        """回滚到不存在的版本应抛出 FileNotFoundError。"""
        await tmp_storage.save_course("c1", _course_data(name="v1"))

        with pytest.raises(FileNotFoundError):
            await tmp_storage.rollback_course("c1", version=999)

    @pytest.mark.asyncio
    async def test_rollback_creates_snapshot_of_current(self, tmp_storage: Storage):
        """回滚前应为当前版本创建快照。"""
        await tmp_storage.save_course("c1", _course_data(name="v1"))
        await tmp_storage.save_course("c1", _course_data(name="v2"))

        snapshots_before = len(tmp_storage._get_snapshot_paths("c1"))
        await tmp_storage.rollback_course("c1", version=1)
        snapshots_after = len(tmp_storage._get_snapshot_paths("c1"))

        assert snapshots_after > snapshots_before


# ---------------------------------------------------------------------------
# 启动验证测试
# ---------------------------------------------------------------------------

class TestValidateAllCourses:
    """测试启动时 JSON 完整性验证。"""

    @pytest.mark.asyncio
    async def test_valid_courses_pass(self, tmp_storage: Storage):
        """有效的课程文件应通过验证。"""
        await tmp_storage.save_course("c1", _course_data(name="valid"))

        reports = await tmp_storage.validate_all_courses()
        assert len(reports) == 1
        assert reports[0].is_valid is True
        assert reports[0].course_id == "c1"

    @pytest.mark.asyncio
    async def test_corrupted_file_detected(self, tmp_storage: Storage):
        """损坏的 JSON 文件应被检测到。"""
        # 直接写入无效 JSON
        filepath = Path(tmp_storage._courses_dir) / "bad.json"
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("{invalid json content")

        reports = await tmp_storage.validate_all_courses()
        bad_report = next(r for r in reports if r.course_id == "bad")
        assert bad_report.is_valid is False
        assert bad_report.error_message is not None

    @pytest.mark.asyncio
    async def test_corrupted_file_recovered_from_snapshot(self, tmp_storage: Storage):
        """损坏文件应尝试从快照恢复。"""
        # 先正常保存两次以创建快照
        await tmp_storage.save_course("c1", _course_data(name="good_v1"))
        await tmp_storage.save_course("c1", _course_data(name="good_v2"))

        # 手动损坏主文件
        filepath = Path(tmp_storage._courses_dir) / "c1.json"
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("CORRUPTED!!!")

        reports = await tmp_storage.validate_all_courses()
        report = next(r for r in reports if r.course_id == "c1")
        assert report.is_valid is False
        assert report.recovered_from_snapshot is True
        assert report.snapshot_version is not None

    @pytest.mark.asyncio
    async def test_empty_directory_returns_empty(self, tmp_storage: Storage):
        """空目录应返回空报告列表。"""
        reports = await tmp_storage.validate_all_courses()
        assert reports == []

    @pytest.mark.asyncio
    async def test_snapshots_not_validated(self, tmp_storage: Storage):
        """快照文件不应被当作主文件验证。"""
        await tmp_storage.save_course("c1", _course_data(name="v1"))
        await tmp_storage.save_course("c1", _course_data(name="v2"))

        reports = await tmp_storage.validate_all_courses()
        # 只应有一个报告（主文件），不包含快照
        course_ids = [r.course_id for r in reports]
        assert course_ids.count("c1") == 1


# ---------------------------------------------------------------------------
# save_course_sync 向后兼容测试
# ---------------------------------------------------------------------------

class TestSaveCourseSync:
    """测试同步版本的课程保存。"""

    def test_sync_save_and_load(self, tmp_storage: Storage):
        """同步保存应能正常写入和读取。"""
        data = _course_data(name="sync_test")
        tmp_storage.save_course_sync("c1", data)

        loaded = tmp_storage.load_course("c1")
        assert loaded["course_name"] == "sync_test"

    def test_sync_save_writes_to_disk(self, tmp_storage: Storage):
        """同步保存应写入磁盘文件。"""
        data = _course_data(name="disk_test")
        tmp_storage.save_course_sync("c1", data)

        filepath = Path(tmp_storage._courses_dir) / "c1.json"
        assert filepath.exists()
        with open(filepath, "r", encoding="utf-8") as f:
            assert json.load(f)["course_name"] == "disk_test"


# ---------------------------------------------------------------------------
# delete_course 测试（含快照清理）
# ---------------------------------------------------------------------------

class TestDeleteCourse:
    """测试课程删除（含快照清理）。"""

    @pytest.mark.asyncio
    async def test_delete_removes_snapshots(self, tmp_storage: Storage):
        """删除课程应同时删除所有快照。"""
        await tmp_storage.save_course("c1", _course_data(name="v1"))
        await tmp_storage.save_course("c1", _course_data(name="v2"))
        await tmp_storage.save_course("c1", _course_data(name="v3"))

        tmp_storage.delete_course("c1")

        # 主文件和快照都应被删除
        assert not (Path(tmp_storage._courses_dir) / "c1.json").exists()
        assert len(tmp_storage._get_snapshot_paths("c1")) == 0
