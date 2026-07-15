import asyncio
import json
import logging
import os
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path

from models import ValidationReport

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
COURSES_DIR = os.path.join(DATA_DIR, "courses")
ANNOTATIONS_FILE = os.path.join(DATA_DIR, "annotations.json")
KNOWLEDGE_GRAPH_DIR = os.path.join(DATA_DIR, "knowledge_graphs")
EVIDENCE_DIR = os.path.join(DATA_DIR, "evidence")
CHANGE_SETS_DIR = os.path.join(DATA_DIR, "change_sets")
# Legacy file for migration
LEGACY_COURSE_FILE = os.path.join(DATA_DIR, "course_tree.json")


class Storage:
    """文件系统存储层，支持原子写入、并发锁和版本管理"""

    def __init__(self, data_dir: str = "", max_versions: int = 3) -> None:
        """
        初始化存储层。

        Args:
            data_dir: 数据目录路径。为空字符串时使用默认 DATA_DIR。
            max_versions: 每个课程保留的最大版本快照数量，默认 3。
        """
        self._data_dir = data_dir if data_dir else DATA_DIR
        self._courses_dir = os.path.join(self._data_dir, "courses")
        self._annotations_file = os.path.join(self._data_dir, "annotations.json")
        self._knowledge_graph_dir = os.path.join(self._data_dir, "knowledge_graphs")
        self._evidence_dir = os.path.join(self._data_dir, "evidence")
        self._change_sets_dir = os.path.join(self._data_dir, "change_sets")
        self._max_versions = max_versions

        if not os.path.exists(self._data_dir):
            os.makedirs(self._data_dir)
        if not os.path.exists(self._courses_dir):
            os.makedirs(self._courses_dir)
        if not os.path.exists(self._knowledge_graph_dir):
            os.makedirs(self._knowledge_graph_dir)
        if not os.path.exists(self._evidence_dir):
            os.makedirs(self._evidence_dir)
        if not os.path.exists(self._change_sets_dir):
            os.makedirs(self._change_sets_dir)

        # Initialize Cache
        self.courses_cache: dict[str, dict] = {}
        self.annotations_cache: list[dict] | None = None
        self.knowledge_graph_cache: dict[str, dict] = {}
        self._cache_initialized = False
        # 通用数据缓存，用于load_data/save_data
        self._data_cache: dict[str, any] = {}

        # 按 course_id 的 asyncio.Lock 文件级锁
        self._locks: dict[str, asyncio.Lock] = {}
        self._locks_lock = asyncio.Lock()

        # Migrate legacy course if exists
        legacy_course_file = os.path.join(self._data_dir, "course_tree.json")
        if os.path.exists(legacy_course_file):
            try:
                with open(legacy_course_file, encoding='utf-8') as f:
                    data = json.load(f)
                    if data and "nodes" in data and len(data["nodes"]) > 0:
                        course_id = str(uuid.uuid4())
                        new_path = os.path.join(self._courses_dir, f"{course_id}.json")
                        with open(new_path, 'w', encoding='utf-8') as nf:
                            json.dump(data, nf, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.warning(f"Migration failed: {e}")
            # Rename legacy file to avoid re-migration
            try:
                os.rename(legacy_course_file, legacy_course_file + ".bak")
            except Exception:
                pass

        if not os.path.exists(self._annotations_file):
            with open(self._annotations_file, 'w', encoding='utf-8') as f:
                json.dump([], f)

        # Git Auto-Sync
        self.dirty = False
        self.running = True
        self.sync_thread = threading.Thread(target=self._auto_sync_loop, daemon=True)
        self.sync_thread.start()

    # =========================================================================
    # 锁管理
    # =========================================================================

    async def _get_lock(self, course_id: str) -> asyncio.Lock:
        """获取指定 course_id 的 asyncio.Lock，不存在则创建。

        Args:
            course_id: 课程 ID。

        Returns:
            对应课程的 asyncio.Lock 实例。
        """
        async with self._locks_lock:
            if course_id not in self._locks:
                self._locks[course_id] = asyncio.Lock()
            return self._locks[course_id]

    # =========================================================================
    # 原子写入
    # =========================================================================

    async def _atomic_write(self, filepath: Path, data: dict) -> None:
        """原子写入实现：写入 .tmp 文件后 os.replace。

        先将数据写入临时文件 (filepath.tmp)，写入成功后通过 os.replace
        原子性地替换目标文件。如果写入过程中发生异常，临时文件会被清理，
        原有文件保持不变。

        Args:
            filepath: 目标文件路径。
            data: 要写入的字典数据。

        Raises:
            Exception: 写入或替换失败时抛出原始异常。
        """
        filepath = Path(filepath)
        tmp_path = filepath.with_suffix(filepath.suffix + ".tmp")
        try:
            content = json.dumps(data, ensure_ascii=False, indent=2)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._write_file_sync, str(tmp_path), content)
            await loop.run_in_executor(None, os.replace, str(tmp_path), str(filepath))
        except Exception:
            # 清理临时文件
            if tmp_path.exists():
                try:
                    os.remove(str(tmp_path))
                except OSError:
                    pass
            raise

    @staticmethod
    def _write_file_sync(filepath: str, content: str) -> None:
        """同步写入文件内容。

        Args:
            filepath: 文件路径。
            content: 要写入的字符串内容。
        """
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

    @staticmethod
    def _read_file_sync(filepath: str) -> str:
        """同步读取文件内容。

        Args:
            filepath: 文件路径。

        Returns:
            文件内容字符串。
        """
        with open(filepath, encoding='utf-8') as f:
            return f.read()

    # =========================================================================
    # 版本快照管理
    # =========================================================================

    def _get_snapshot_paths(self, course_id: str) -> list[Path]:
        """获取指定课程的所有快照文件路径，按版本号升序排列。

        Args:
            course_id: 课程 ID。

        Returns:
            按版本号升序排列的快照文件 Path 列表。
        """
        snapshots: list[Path] = []
        courses_dir = Path(self._courses_dir)
        if not courses_dir.exists():
            return snapshots
        for f in courses_dir.iterdir():
            if f.name.startswith(f"{course_id}.v") and f.name.endswith(".json"):
                # 提取版本号
                try:
                    version_str = f.stem.split(".v")[-1]
                    int(version_str)  # 验证是数字
                    snapshots.append(f)
                except (ValueError, IndexError):
                    continue
        # 按版本号排序
        snapshots.sort(key=lambda p: int(p.stem.split(".v")[-1]))
        return snapshots

    def _get_snapshot_version(self, path: Path) -> int:
        """从快照文件路径中提取版本号。

        Args:
            path: 快照文件路径。

        Returns:
            版本号整数。
        """
        return int(path.stem.split(".v")[-1])

    async def _create_snapshot(self, course_id: str) -> None:
        """创建版本快照。

        将当前课程文件复制为版本快照。版本号递增，超过 max_versions 时
        删除最旧的快照。

        Args:
            course_id: 课程 ID。
        """
        current_file = Path(self._courses_dir) / f"{course_id}.json"
        if not current_file.exists():
            return

        # 确定下一个版本号
        existing_snapshots = self._get_snapshot_paths(course_id)
        if existing_snapshots:
            next_version = self._get_snapshot_version(existing_snapshots[-1]) + 1
        else:
            next_version = 1

        # 创建快照
        snapshot_path = Path(self._courses_dir) / f"{course_id}.v{next_version}.json"
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, shutil.copy2, str(current_file), str(snapshot_path)
        )

        # 清理超出上限的旧快照
        existing_snapshots = self._get_snapshot_paths(course_id)
        while len(existing_snapshots) > self._max_versions:
            oldest = existing_snapshots.pop(0)
            try:
                os.remove(str(oldest))
            except OSError as e:
                logger.warning(f"Failed to remove old snapshot {oldest}: {e}")

    # =========================================================================
    # 课程 CRUD（增强版）
    # =========================================================================

    def _ensure_cache(self) -> None:
        """Load all courses into cache if not initialized"""
        if self._cache_initialized:
            return

        if os.path.exists(self._courses_dir):
            for filename in os.listdir(self._courses_dir):
                # 只加载主文件，跳过快照文件 (.v{N}.json)
                if filename.endswith(".json") and ".v" not in filename:
                    course_id = filename.replace(".json", "")
                    filepath = os.path.join(self._courses_dir, filename)
                    try:
                        with open(filepath, encoding='utf-8') as f:
                            data = json.load(f)
                            self.courses_cache[course_id] = data
                    except Exception as e:
                        logger.warning(f"Failed to load course {filename}: {e}")
                        continue
        self._cache_initialized = True

    def list_courses(self) -> list[dict]:
        """列出所有课程的摘要信息。

        Returns:
            课程摘要列表，每项包含 course_id、course_name、node_count。
        """
        self._ensure_cache()
        courses = []
        for course_id, data in self.courses_cache.items():
            courses.append({
                "course_id": course_id,
                "course_name": data.get("course_name", "未命名课程"),
                "node_count": len(data.get("nodes", []))
            })
        return courses

    async def save_course(self, course_id: str, data: dict) -> None:
        """原子写入课程数据，按 course_id 加锁。

        保存前先创建当前版本的快照（如果当前文件存在），然后通过原子写入
        更新课程文件。写入失败时保留上一有效版本。

        Args:
            course_id: 课程 ID。
            data: 课程数据字典。
        """
        lock = await self._get_lock(course_id)
        async with lock:
            filepath = Path(self._courses_dir) / f"{course_id}.json"

            # 如果当前文件存在，先创建快照
            if filepath.exists():
                try:
                    await self._create_snapshot(course_id)
                except Exception as e:
                    logger.warning(f"Failed to create snapshot for {course_id}: {e}")

            # 原子写入
            try:
                await self._atomic_write(filepath, data)
                # 更新缓存
                self._ensure_cache()
                self.courses_cache[course_id] = data
                self._mark_dirty()
            except Exception as e:
                logger.error(f"Failed to save course {course_id}: {e}")
                raise

    def save_course_sync(self, course_id: str, data: dict) -> None:
        """同步版本的课程保存，供尚未迁移到 async 的调用方使用。

        不包含 asyncio.Lock 和版本快照功能，仅做基本的文件写入和缓存更新。
        后续任务会将所有调用方迁移到 async save_course。

        Args:
            course_id: 课程 ID。
            data: 课程数据字典。
        """
        self._ensure_cache()
        self.courses_cache[course_id] = data

        filepath = os.path.join(self._courses_dir, f"{course_id}.json")
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        self._mark_dirty()

    def load_course(self, course_id: str) -> dict:
        """加载课程数据。

        优先从缓存读取，缓存未命中时从磁盘加载。

        Args:
            course_id: 课程 ID。

        Returns:
            课程数据字典，不存在时返回空字典。
        """
        self._ensure_cache()
        return self.courses_cache.get(course_id, {})

    def delete_course(self, course_id: str) -> None:
        """删除课程及其所有快照。

        Args:
            course_id: 课程 ID。
        """
        self._ensure_cache()
        if course_id in self.courses_cache:
            del self.courses_cache[course_id]

        filepath = os.path.join(self._courses_dir, f"{course_id}.json")
        if os.path.exists(filepath):
            os.remove(filepath)

        # 删除所有快照
        for snapshot in self._get_snapshot_paths(course_id):
            try:
                os.remove(str(snapshot))
            except OSError:
                pass

        self._mark_dirty()

    # =========================================================================
    # 回滚
    # =========================================================================

    async def rollback_course(self, course_id: str, version: int) -> dict:
        """回滚到指定版本的快照。

        将指定版本的快照数据恢复为当前版本。回滚前会为当前数据创建快照。

        Args:
            course_id: 课程 ID。
            version: 要回滚到的版本号。

        Returns:
            回滚后的课程数据字典。

        Raises:
            FileNotFoundError: 指定版本的快照不存在。
            json.JSONDecodeError: 快照文件内容不是有效 JSON。
        """
        lock = await self._get_lock(course_id)
        async with lock:
            snapshot_path = Path(self._courses_dir) / f"{course_id}.v{version}.json"
            if not snapshot_path.exists():
                raise FileNotFoundError(
                    f"Snapshot version {version} not found for course {course_id}"
                )

            # 读取快照数据
            loop = asyncio.get_event_loop()
            content = await loop.run_in_executor(
                None, self._read_file_sync, str(snapshot_path)
            )
            snapshot_data = json.loads(content)

            # 为当前版本创建快照（如果存在）
            current_file = Path(self._courses_dir) / f"{course_id}.json"
            if current_file.exists():
                try:
                    await self._create_snapshot(course_id)
                except Exception as e:
                    logger.warning(f"Failed to create snapshot before rollback: {e}")

            # 原子写入回滚数据
            await self._atomic_write(current_file, snapshot_data)

            # 更新缓存
            self._ensure_cache()
            self.courses_cache[course_id] = snapshot_data
            self._mark_dirty()

            return snapshot_data

    # =========================================================================
    # 启动时验证
    # =========================================================================

    async def validate_all_courses(self) -> list[ValidationReport]:
        """启动时验证所有课程 JSON 文件的完整性。

        遍历课程目录中的所有主文件（非快照），验证 JSON 格式是否有效。
        对损坏的文件记录警告并尝试从最新快照恢复。

        Returns:
            验证报告列表，每个课程一份报告。
        """
        reports: list[ValidationReport] = []
        courses_dir = Path(self._courses_dir)
        if not courses_dir.exists():
            return reports

        loop = asyncio.get_event_loop()

        for filepath in sorted(courses_dir.iterdir()):
            # 只验证主文件，跳过快照
            if not filepath.name.endswith(".json") or ".v" in filepath.name:
                continue

            course_id = filepath.stem

            try:
                content = await loop.run_in_executor(
                    None, self._read_file_sync, str(filepath)
                )
                json.loads(content)  # 验证 JSON 有效性
                reports.append(ValidationReport(
                    course_id=course_id,
                    filepath=str(filepath),
                    is_valid=True,
                ))
            except (json.JSONDecodeError, Exception) as e:
                logger.warning(
                    f"Course file {filepath.name} is corrupted: {e}"
                )

                # 尝试从最新快照恢复
                recovered = False
                snapshot_version = None
                snapshots = self._get_snapshot_paths(course_id)
                for snapshot in reversed(snapshots):
                    try:
                        snap_content = await loop.run_in_executor(
                            None, self._read_file_sync, str(snapshot)
                        )
                        snap_data = json.loads(snap_content)
                        # 用快照恢复
                        await self._atomic_write(filepath, snap_data)
                        snapshot_version = self._get_snapshot_version(snapshot)
                        recovered = True
                        logger.info(
                            f"Recovered {course_id} from snapshot v{snapshot_version}"
                        )
                        # 更新缓存
                        self.courses_cache[course_id] = snap_data
                        break
                    except Exception as recovery_err:
                        logger.warning(
                            f"Failed to recover from snapshot {snapshot.name}: {recovery_err}"
                        )
                        continue

                reports.append(ValidationReport(
                    course_id=course_id,
                    filepath=str(filepath),
                    is_valid=False,
                    error_message=str(e),
                    recovered_from_snapshot=recovered,
                    snapshot_version=snapshot_version,
                ))

        return reports

    # =========================================================================
    # Git Auto-Sync（保留原有逻辑）
    # =========================================================================

    def _auto_sync_loop(self) -> None:
        """Background thread to auto-commit data changes"""
        # Only enable git sync if .git exists
        if not os.path.exists(".git"):
            logger.info("Git Auto-Sync disabled: .git directory not found")
            return

        logger.info("Git Auto-Sync started")

        # Configure git user if needed (for cloud environments)
        try:
            res = subprocess.run(["git", "config", "user.email"], capture_output=True, text=True)
            if res.returncode != 0 or not res.stdout.strip():
                logger.info("Configuring temporary git user for auto-sync...")
                subprocess.run(["git", "config", "--local", "user.email", "ai-service@local"], check=False, capture_output=True)
                subprocess.run(["git", "config", "--local", "user.name", "AI Service"], check=False, capture_output=True)
        except Exception as e:
            logger.warning(f"Failed to check/set git config: {e}")

        while self.running:
            time.sleep(30)
            if self.dirty:
                try:
                    logger.info("Auto-saving data to git...")
                    subprocess.run(["git", "add", "backend/data"], check=False, capture_output=True)
                    subprocess.run(["git", "commit", "-m", "Auto-save: update course data"], check=False, capture_output=True)
                    self.dirty = False
                except Exception as e:
                    logger.error(f"Git Auto-Sync failed: {e}")

    def _mark_dirty(self) -> None:
        """标记数据已变更，触发 Git 自动同步。"""
        self.dirty = True

    # =========================================================================
    # 标注管理（保留原有逻辑）
    # =========================================================================

    def save_annotation(self, annotation: dict) -> None:
        annotations = self.load_annotations()

        existing_index = next(
            (i for i, a in enumerate(annotations) if a.get('anno_id') == annotation.get('anno_id')),
            -1,
        )

        if existing_index >= 0:
            annotations[existing_index] = annotation
        else:
            annotations.append(annotation)

        self.annotations_cache = annotations

        with open(self._annotations_file, 'w', encoding='utf-8') as f:
            json.dump(annotations, f, ensure_ascii=False, indent=2)

        self._mark_dirty()

    def load_annotations(self) -> list[dict]:
        if self.annotations_cache is not None:
            return self.annotations_cache

        try:
            with open(self._annotations_file, encoding='utf-8') as f:
                self.annotations_cache = json.load(f)
        except json.JSONDecodeError:
            self.annotations_cache = []

        return self.annotations_cache

    def get_annotations_by_node(self, node_id: str) -> list[dict]:
        annotations = self.load_annotations()
        return [a for a in annotations if a.get('node_id') == node_id]

    def delete_annotation(self, anno_id: str) -> None:
        annotations = self.load_annotations()
        new_annotations = [a for a in annotations if a.get('anno_id') != anno_id]
        self.annotations_cache = new_annotations

        with open(self._annotations_file, 'w', encoding='utf-8') as f:
            json.dump(new_annotations, f, ensure_ascii=False, indent=2)

        self._mark_dirty()

    def update_annotation(self, anno_id: str, content: str) -> None:
        annotations = self.load_annotations()
        updated = False
        for anno in annotations:
            if anno.get('anno_id') == anno_id:
                anno['answer'] = content
                anno['anno_summary'] = content[:50] + '...' if len(content) > 50 else content
                updated = True
                break

        if updated:
            self.annotations_cache = annotations
            with open(self._annotations_file, 'w', encoding='utf-8') as f:
                json.dump(annotations, f, ensure_ascii=False, indent=2)
            self._mark_dirty()

    def update_annotation_field(self, anno_id: str, field: str, value: any) -> bool:
        """Update a specific field of an annotation"""
        annotations = self.load_annotations()
        updated = False
        for anno in annotations:
            if anno.get('anno_id') == anno_id:
                anno[field] = value
                updated = True
                break

        if updated:
            self.annotations_cache = annotations
            with open(self._annotations_file, 'w', encoding='utf-8') as f:
                json.dump(annotations, f, ensure_ascii=False, indent=2)
            self._mark_dirty()

        return updated

    # =========================================================================
    # 知识图谱（保留原有逻辑）
    # =========================================================================

    def save_knowledge_graph(self, course_id: str, graph_data: dict) -> None:
        """Save knowledge graph to disk and cache"""
        self.knowledge_graph_cache[course_id] = graph_data
        filepath = os.path.join(self._knowledge_graph_dir, f"{course_id}.json")
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(graph_data, f, ensure_ascii=False, indent=2)
        self._mark_dirty()

    def load_knowledge_graph(self, course_id: str) -> dict | None:
        """Load knowledge graph from cache or disk"""
        if course_id in self.knowledge_graph_cache:
            return self.knowledge_graph_cache[course_id]

        filepath = os.path.join(self._knowledge_graph_dir, f"{course_id}.json")
        if os.path.exists(filepath):
            try:
                with open(filepath, encoding='utf-8') as f:
                    data = json.load(f)
                    self.knowledge_graph_cache[course_id] = data
                    return data
            except Exception as e:
                logger.warning(f"Failed to load knowledge graph for {course_id}: {e}")
        return None

    # =========================================================================
    # 通用数据存储接口（保留原有逻辑）
    # =========================================================================

    def load_data(self, filename: str) -> any:
        """
        从数据目录加载通用数据文件

        Args:
            filename: 数据文件名（如 'long_term_memories.json'）

        Returns:
            解析后的数据对象，如果文件不存在则返回None
        """
        if filename in self._data_cache:
            return self._data_cache[filename]

        filepath = os.path.join(self._data_dir, filename)
        if not os.path.exists(filepath):
            return None

        try:
            with open(filepath, encoding='utf-8') as f:
                data = json.load(f)
                self._data_cache[filename] = data
                return data
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse JSON from {filename}")
            return None
        except Exception as e:
            logger.error(f"Failed to load data from {filename}: {e}")
            return None

    def save_data(self, filename: str, data: any) -> None:
        """
        保存通用数据到数据目录

        Args:
            filename: 数据文件名
            data: 要保存的数据对象
        """
        self._data_cache[filename] = data

        filepath = os.path.join(self._data_dir, filename)
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self._mark_dirty()
        except Exception as e:
            logger.error(f"Failed to save data to {filename}: {e}")
            raise


    # =========================================================================
    # 学习证据（EvidenceItem）持久化，按 course_id 分文件存储
    # 参照 save_course/load_course 的实现风格：同步 + 异步版本都提供。
    # =========================================================================

    def _evidence_filepath(self, course_id: str) -> str:
        return os.path.join(self._evidence_dir, f"{course_id}.json")

    def load_evidence_items(self, course_id: str) -> list[dict]:
        """加载指定课程的所有 EvidenceItem（字典形式），文件不存在时返回空列表。

        Args:
            course_id: 课程 ID。

        Returns:
            EvidenceItem 字典列表。
        """
        filepath = self._evidence_filepath(course_id)
        if not os.path.exists(filepath):
            return []
        try:
            with open(filepath, encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load evidence items for {course_id}: {e}")
            return []

    def save_evidence_item_sync(self, course_id: str, item: dict) -> None:
        """同步追加保存一条 EvidenceItem。

        Args:
            course_id: 课程 ID。
            item: EvidenceItem 字典（含 id 字段，用于去重覆盖）。
        """
        items = self.load_evidence_items(course_id)
        item_id = item.get("id")
        existing_index = next((i for i, it in enumerate(items) if it.get("id") == item_id), -1)
        if existing_index >= 0:
            items[existing_index] = item
        else:
            items.append(item)

        filepath = self._evidence_filepath(course_id)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
        self._mark_dirty()

    async def save_evidence_item(self, course_id: str, item: dict) -> None:
        """异步追加保存一条 EvidenceItem（原子写入，按 course_id 加锁）。

        Args:
            course_id: 课程 ID。
            item: EvidenceItem 字典（含 id 字段，用于去重覆盖）。
        """
        lock = await self._get_lock(f"evidence:{course_id}")
        async with lock:
            items = self.load_evidence_items(course_id)
            item_id = item.get("id")
            existing_index = next((i for i, it in enumerate(items) if it.get("id") == item_id), -1)
            if existing_index >= 0:
                items[existing_index] = item
            else:
                items.append(item)

            filepath = Path(self._evidence_filepath(course_id))
            await self._atomic_write(filepath, items)
            self._mark_dirty()

    # =========================================================================
    # 课程变更集（CourseChangeSet）持久化，按 course_id 分文件存储
    # =========================================================================

    def _change_sets_filepath(self, course_id: str) -> str:
        return os.path.join(self._change_sets_dir, f"{course_id}.json")

    def load_change_sets(self, course_id: str) -> list[dict]:
        """加载指定课程的所有 CourseChangeSet（字典形式），文件不存在时返回空列表。

        Args:
            course_id: 课程 ID。

        Returns:
            CourseChangeSet 字典列表。
        """
        filepath = self._change_sets_filepath(course_id)
        if not os.path.exists(filepath):
            return []
        try:
            with open(filepath, encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load change sets for {course_id}: {e}")
            return []

    def save_change_set_sync(self, course_id: str, change_set: dict) -> None:
        """同步保存/更新一条 CourseChangeSet（按 id upsert）。

        Args:
            course_id: 课程 ID。
            change_set: CourseChangeSet 字典（含 id 字段）。
        """
        change_sets = self.load_change_sets(course_id)
        cs_id = change_set.get("id")
        existing_index = next((i for i, cs in enumerate(change_sets) if cs.get("id") == cs_id), -1)
        if existing_index >= 0:
            change_sets[existing_index] = change_set
        else:
            change_sets.append(change_set)

        filepath = self._change_sets_filepath(course_id)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(change_sets, f, ensure_ascii=False, indent=2)
        self._mark_dirty()

    async def save_change_set(self, course_id: str, change_set: dict) -> None:
        """异步保存/更新一条 CourseChangeSet（按 id upsert，原子写入，按 course_id 加锁）。

        Args:
            course_id: 课程 ID。
            change_set: CourseChangeSet 字典（含 id 字段）。
        """
        lock = await self._get_lock(f"change_sets:{course_id}")
        async with lock:
            change_sets = self.load_change_sets(course_id)
            cs_id = change_set.get("id")
            existing_index = next((i for i, cs in enumerate(change_sets) if cs.get("id") == cs_id), -1)
            if existing_index >= 0:
                change_sets[existing_index] = change_set
            else:
                change_sets.append(change_set)

            filepath = Path(self._change_sets_filepath(course_id))
            await self._atomic_write(filepath, change_sets)
            self._mark_dirty()


storage = Storage()
