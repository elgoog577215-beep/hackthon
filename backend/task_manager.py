# =============================================================================
# Task Manager - 课程生成任务管理器（纯 asyncio 架构）
# =============================================================================
#
# 架构说明：
# 本模块负责管理课程生成的异步任务队列，采用纯 asyncio 生产者-消费者模式。
# 使用 asyncio.Queue 调度任务，asyncio.Semaphore 控制并发上限。
#
# 生成流程：
# 1. 接收生成任务 → 2. 分析课程结构 → 3. 按层级优先调度节点 → 4. 流式生成 → 5. 推送进度
#
# 节点处理顺序（两层结构）：
# L1(章节/Chapter) → L2(子章节+正文/Section+Content)
#
# 两阶段生成：
# 阶段1: L1 生成 L2 子章节结构
# 阶段2: L2 生成详细正文内容（按层级优先调度）
#
# Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 10.1, 10.2, 10.3, 10.4,
#               6.5, 7.1, 7.2, 7.5, 13.1, 13.2, 13.4, 13.5
# =============================================================================

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import uuid
from datetime import datetime
from typing import Any

from models import (
    NodeGenerationConfig,
    NodeStatus,
    TaskLogEntry,
)

logger = logging.getLogger(__name__)

TASKS_FILE = "tasks.json"

# 内容完整性阈值（字符数）
CONTENT_COMPLETE_THRESHOLD = 600

# 重试上限
MAX_RETRIES = 2

# 指数退避参数
BACKOFF_BASE = 2
BACKOFF_MAX = 60


def fix_latex_content(content: str) -> str:
    """修复 LaTeX 公式格式问题"""
    if not content:
        return content
    
    def fix_aligned_env(match):
        env_name = match.group(1)
        inner = match.group(2) if match.lastindex and match.lastindex >= 2 else ''
        
        inner = re.sub(r'\$\s*$', '', inner)
        inner = re.sub(r'^\s*\$', '', inner)
        inner = re.sub(r'\$\$', '', inner)
        inner = re.sub(r'\\\$', r'\\', inner)
        inner = re.sub(r'\\\s*$', r'\\', inner, flags=re.MULTILINE)
        inner = re.sub(r'\\\s*\n', r'\\\n', inner)
        
        return f'$$\n\\begin{{{env_name}}}\n{inner}\n\\end{{{env_name}}}\n$$'
    
    content = re.sub(
        r'\\begin\{(aligned|matrix|pmatrix|bmatrix|vmatrix|cases|eqnarray|gather|split)\}(.*?)(?:\\end\{\1\}|$)',
        fix_aligned_env,
        content,
        flags=re.DOTALL
    )
    
    content = re.sub(r'\\\[(.+?)\\\]', r'\n$$\n\1\n$$\n', content, flags=re.DOTALL)
    content = re.sub(r'\\\((.+?)\\\)', r'$\1$', content, flags=re.DOTALL)
    
    content = re.sub(r'\$\s+', '$', content)
    content = re.sub(r'\s+\$', '$', content)
    
    return content


class TaskManager:
    """异步任务管理器，使用 asyncio 原生调度。

    通过 asyncio.Queue 实现生产者-消费者模式，asyncio.Semaphore 控制并发上限。
    集成 WebSocketService 进行实时推送，集成 CourseService 的流式生成方法。

    Attributes:
        storage: 存储层实例
        course_service: 课程生成服务实例
        ws_service: WebSocket 服务实例
        max_concurrency: 最大并发数
    """

    def __init__(
        self,
        storage: Any,
        course_service: Any,
        ws_service: Any,
        max_concurrency: int = 5,
    ) -> None:
        self.storage = storage
        self.course_service = course_service
        self.ws_service = ws_service
        self.max_concurrency = max_concurrency

        # Task state
        self.tasks: dict[str, dict[str, Any]] = {}
        self._lock: asyncio.Lock = asyncio.Lock()

        # asyncio.Queue for producer-consumer pattern
        self._task_queue: asyncio.Queue[str] = asyncio.Queue()

        # Semaphore for concurrency control
        self._semaphore: asyncio.Semaphore = asyncio.Semaphore(max_concurrency)

        # Consumer loop task
        self._consumer_task: asyncio.Task[None] | None = None
        self._running: bool = False

        # Track running node tasks for cancellation
        # task_id -> {node_id -> asyncio.Task}
        self._running_node_tasks: dict[str, dict[str, asyncio.Task[Any]]] = {}

        # Task execution logs: task_id -> list[TaskLogEntry]
        self._task_logs: dict[str, list[TaskLogEntry]] = {}

        # Node retry counts: task_id -> {node_id -> count}
        self._node_retries: dict[str, dict[str, int]] = {}

        # Callback for legacy node update (backward compat)
        self.on_node_update: Any | None = None

        self.load_tasks()

    # -------------------------------------------------------------------------
    # Lifecycle: start / shutdown
    # -------------------------------------------------------------------------

    async def start(self) -> None:
        """通过 FastAPI lifespan 启动，创建消费者协程。

        **Validates: Requirements 10.1, 10.3**
        """
        if self._running:
            return
        self._running = True
        self._consumer_task = asyncio.create_task(self._consumer_loop())
        logger.info("TaskManager started (max_concurrency=%d)", self.max_concurrency)

    async def shutdown(self, timeout: float = 30.0) -> None:
        """优雅关闭，等待正在执行的任务完成（最长 timeout 秒）。

        **Validates: Requirements 10.4**

        Args:
            timeout: 最长等待时间（秒），默认 30。
        """
        logger.info("TaskManager shutting down (timeout=%.1fs)...", timeout)
        self._running = False

        # Cancel the consumer loop
        if self._consumer_task and not self._consumer_task.done():
            self._consumer_task.cancel()
            try:
                await asyncio.wait_for(
                    asyncio.shield(self._consumer_task), timeout=2.0
                )
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        # Gather all running node tasks
        all_node_tasks: list[asyncio.Task[Any]] = []
        for node_tasks in self._running_node_tasks.values():
            all_node_tasks.extend(node_tasks.values())

        if all_node_tasks:
            logger.info("Waiting for %d running node tasks...", len(all_node_tasks))
            done, pending = await asyncio.wait(
                all_node_tasks, timeout=timeout
            )
            if pending:
                logger.warning(
                    "Force-cancelling %d tasks after %.1fs timeout",
                    len(pending), timeout,
                )
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)

        self.save_tasks()
        logger.info("TaskManager shutdown complete")

    # -------------------------------------------------------------------------
    # Task Lifecycle Management
    # -------------------------------------------------------------------------

    async def create_task(
        self, course_id: str, task_type: str = "auto_generate"
    ) -> str:
        """创建任务并放入 asyncio.Queue。

        **Validates: Requirements 10.2**

        Args:
            course_id: 课程 ID
            task_type: 任务类型

        Returns:
            新创建的 task_id
        """
        task_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        task: dict[str, Any] = {
            "id": task_id,
            "course_id": course_id,
            "type": task_type,
            "status": "pending",
            "progress": 0,
            "total": 0,
            "completed_nodes": 0,
            "total_nodes": 0,
            "current_node_name": "",
            "current_phase": "",
            "phase_progress": "",
            "current_nodes": [],
            "message": "等待开始...",
            "created_at": now,
            "updated_at": now,
            "error": None,
            "retry_count": 0,
            "logs": [],
        }
        async with self._lock:
            self.tasks[task_id] = task
            self._task_logs[task_id] = []
            self._node_retries[task_id] = {}
            self.save_tasks()

        await self._task_queue.put(task_id)
        logger.info("Created task %s for course %s", task_id, course_id)
        return task_id

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        """获取任务信息。"""
        return self.tasks.get(task_id)

    def get_all_tasks(self, limit: int = 100) -> list[dict[str, Any]]:
        """获取所有任务，按状态优先级和时间排序。"""
        status_priority = {
            "running": 0,
            "pending": 1,
            "paused": 2,
            "failed": 3,
            "completed": 4,
        }
        tasks_list = list(self.tasks.values())
        tasks_list.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        tasks_list.sort(
            key=lambda x: status_priority.get(x.get("status", ""), 5)
        )
        return tasks_list[:limit]

    def get_tasks_by_course(self, course_id: str) -> list[dict[str, Any]]:
        """获取指定课程的所有任务。"""
        return [t for t in self.tasks.values() if t["course_id"] == course_id]

    async def pause_task(self, task_id: str) -> None:
        """暂停任务。"""
        async with self._lock:
            if task_id in self.tasks:
                if self.tasks[task_id]["status"] in ["pending", "running"]:
                    self.tasks[task_id]["status"] = "paused"
                    self.tasks[task_id]["message"] = "Paused by user"
                    self.save_tasks()

    async def resume_task(self, task_id: str) -> None:
        """恢复任务。"""
        async with self._lock:
            if task_id in self.tasks:
                if self.tasks[task_id]["status"] == "paused":
                    self.tasks[task_id]["status"] = "pending"
                    self.tasks[task_id]["message"] = "Resuming..."
                    self.save_tasks()
        await self._task_queue.put(task_id)

    async def delete_task(self, task_id: str) -> None:
        """删除任务。"""
        async with self._lock:
            if task_id in self.tasks:
                del self.tasks[task_id]
                self.save_tasks()
        # Cancel any running node tasks
        node_tasks = self._running_node_tasks.pop(task_id, {})
        for t in node_tasks.values():
            t.cancel()

    def clear_failed_tasks(self) -> int:
        """清理失败任务，返回清理数量。"""
        initial_count = len(self.tasks)
        self.tasks = {
            tid: t for tid, t in self.tasks.items() if t.get("status") != "failed"
        }
        if len(self.tasks) < initial_count:
            self.save_tasks()
        return initial_count - len(self.tasks)

    # -------------------------------------------------------------------------
    # Single-node control: skip, retry, stop, retry_all_failed
    # -------------------------------------------------------------------------

    async def skip_node(self, task_id: str, node_id: str) -> None:
        """跳过指定节点，将其标记为 skipped 状态。

        **Validates: Requirements 7.1**

        Args:
            task_id: 任务 ID
            node_id: 节点 ID
        """
        task = self.tasks.get(task_id)
        if not task:
            logger.warning("skip_node: task %s not found", task_id)
            return

        course_id = task["course_id"]
        course_data = self.storage.load_course(course_id)
        if not course_data:
            return

        for node in course_data.get("nodes", []):
            if node.get("node_id") == node_id:
                node["generation_status"] = NodeStatus.SKIPPED.value
                break

        await self.storage.save_course(course_id, course_data)

        # Cancel running task for this node if any
        node_tasks = self._running_node_tasks.get(task_id, {})
        running = node_tasks.pop(node_id, None)
        if running and not running.done():
            running.cancel()

        self._add_log_entry(
            task_id, node_id,
            node_name=self._find_node_name(course_data, node_id),
            event="skip", message=f"Node {node_id} skipped by user",
        )
        await self._update_progress(task_id, course_data)
        logger.info("Skipped node %s in task %s", node_id, task_id)

    async def retry_node(self, task_id: str, node_id: str) -> None:
        """重试指定节点（error 或 completed 状态）。

        **Validates: Requirements 7.2**

        Args:
            task_id: 任务 ID
            node_id: 节点 ID
        """
        task = self.tasks.get(task_id)
        if not task:
            logger.warning("retry_node: task %s not found", task_id)
            return

        course_id = task["course_id"]
        course_data = self.storage.load_course(course_id)
        if not course_data:
            return

        target_node: dict[str, Any] | None = None
        for node in course_data.get("nodes", []):
            if node.get("node_id") == node_id:
                node["generation_status"] = NodeStatus.PENDING.value
                node["error_summary"] = None
                target_node = node
                break

        if not target_node:
            logger.warning("retry_node: node %s not found", node_id)
            return

        await self.storage.save_course(course_id, course_data)

        # Reset retry count for this node
        retries = self._node_retries.setdefault(task_id, {})
        retries[node_id] = 0

        self._add_log_entry(
            task_id, node_id,
            node_name=target_node.get("node_name", ""),
            event="retry", message=f"Node {node_id} retry requested by user",
        )

        # Schedule the node for processing
        asyncio.create_task(self._process_node(task_id, target_node))
        logger.info("Retry scheduled for node %s in task %s", node_id, task_id)

    async def stop_node(self, task_id: str, node_id: str) -> None:
        """停止正在生成的节点，保留已生成内容。

        **Validates: Requirements 7.5**

        Args:
            task_id: 任务 ID
            node_id: 节点 ID
        """
        node_tasks = self._running_node_tasks.get(task_id, {})
        running = node_tasks.pop(node_id, None)
        if running and not running.done():
            running.cancel()
            logger.info("Stopped generation for node %s in task %s", node_id, task_id)

        # Mark node as completed with partial content
        task = self.tasks.get(task_id)
        if task:
            course_id = task["course_id"]
            course_data = self.storage.load_course(course_id)
            if course_data:
                for node in course_data.get("nodes", []):
                    if node.get("node_id") == node_id:
                        # Keep whatever content was generated
                        if node.get("generation_status") == NodeStatus.GENERATING.value:
                            node["generation_status"] = NodeStatus.COMPLETED.value
                        break
                await self.storage.save_course(course_id, course_data)

        self._add_log_entry(
            task_id, node_id,
            node_name="",
            event="complete",
            message=f"Node {node_id} stopped by user, partial content retained",
        )

    async def retry_all_failed(self, task_id: str) -> None:
        """批量重试所有失败节点。

        **Validates: Requirements 13.3**

        Args:
            task_id: 任务 ID
        """
        task = self.tasks.get(task_id)
        if not task:
            logger.warning("retry_all_failed: task %s not found", task_id)
            return

        course_id = task["course_id"]
        course_data = self.storage.load_course(course_id)
        if not course_data:
            return

        failed_nodes: list[dict[str, Any]] = []
        for node in course_data.get("nodes", []):
            if node.get("generation_status") == NodeStatus.ERROR.value:
                node["generation_status"] = NodeStatus.PENDING.value
                node["error_summary"] = None
                failed_nodes.append(node)

        if not failed_nodes:
            logger.info("retry_all_failed: no failed nodes in task %s", task_id)
            return

        await self.storage.save_course(course_id, course_data)

        # Reset retry counts
        retries = self._node_retries.setdefault(task_id, {})
        for node in failed_nodes:
            retries[node["node_id"]] = 0

        logger.info(
            "Retrying %d failed nodes in task %s", len(failed_nodes), task_id
        )

        # Schedule all failed nodes
        await self._schedule_nodes(task_id, failed_nodes)

    # -------------------------------------------------------------------------
    # Outline update
    # -------------------------------------------------------------------------

    async def update_outline(
        self, task_id: str, new_outline: list[dict]
    ) -> None:
        """更新大纲，取消受影响的待执行任务并重新调度。

        **Validates: Requirements 6.5**

        Args:
            task_id: 任务 ID
            new_outline: 新的大纲节点列表
        """
        task = self.tasks.get(task_id)
        if not task:
            logger.warning("update_outline: task %s not found", task_id)
            return

        course_id = task["course_id"]
        course_data = self.storage.load_course(course_id)
        if not course_data:
            return

        old_nodes = course_data.get("nodes", [])
        old_ids = {n.get("node_id") for n in old_nodes}
        new_ids = {n.get("node_id") for n in new_outline if n.get("node_id")}

        # Cancel tasks for removed/modified nodes
        removed_ids = old_ids - new_ids
        node_tasks = self._running_node_tasks.get(task_id, {})
        for nid in removed_ids:
            running = node_tasks.pop(nid, None)
            if running and not running.done():
                running.cancel()

        # Update course data with new outline
        course_data["nodes"] = new_outline
        await self.storage.save_course(course_id, course_data)

        # Schedule new nodes that need generation
        new_nodes = [
            n for n in new_outline
            if n.get("node_id") not in old_ids
            or n.get("generation_status", NodeStatus.PENDING.value) == NodeStatus.PENDING.value
        ]
        pending_nodes = [
            n for n in new_nodes
            if n.get("generation_status", NodeStatus.PENDING.value) == NodeStatus.PENDING.value
            and not self._is_content_complete(n)
        ]

        if pending_nodes:
            await self._schedule_nodes(task_id, pending_nodes)

        await self._update_progress(task_id, course_data)
        logger.info(
            "Outline updated for task %s: removed %d, new pending %d",
            task_id, len(removed_ids), len(pending_nodes),
        )

    # -------------------------------------------------------------------------
    # Consumer loop & scheduling
    # -------------------------------------------------------------------------

    async def _consumer_loop(self) -> None:
        """消费者循环，从 asyncio.Queue 取任务执行。

        **Validates: Requirements 3.1, 10.1, 10.2**
        """
        logger.info("Consumer loop started")
        try:
            while self._running:
                try:
                    task_id = await asyncio.wait_for(
                        self._task_queue.get(), timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue

                task = self.tasks.get(task_id)
                if not task or task["status"] not in ("pending", "running"):
                    continue

                try:
                    await self._process_task(task_id)
                except Exception as e:
                    logger.error("Error processing task %s: %s", task_id, e, exc_info=True)
                    await self._update_task_status(
                        task_id, "failed", error=str(e)
                    )
        except asyncio.CancelledError:
            logger.info("Consumer loop cancelled")

    async def _schedule_nodes(
        self, task_id: str, nodes: list[dict]
    ) -> None:
        """按层级优先策略调度节点生成。

        level 1 > level 2 > level 3，同层级按原始顺序。

        **Validates: Requirements 3.3, 3.4**

        Args:
            task_id: 任务 ID
            nodes: 待调度的节点列表
        """
        # Sort by level first, then by original order (index in list)
        sorted_nodes = sorted(
            nodes, key=lambda n: (n.get("node_level", 1), nodes.index(n))
        )

        tasks: list[asyncio.Task[Any]] = []
        for node in sorted_nodes:
            node_id = node.get("node_id", "")
            task = asyncio.create_task(self._process_node(task_id, node))
            # Track running node tasks
            self._running_node_tasks.setdefault(task_id, {})[node_id] = task
            tasks.append(task)

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _process_task(self, task_id: str) -> None:
        """处理单个任务：分析课程结构并调度节点。

        Args:
            task_id: 任务 ID
        """
        task = self.tasks.get(task_id)
        if not task:
            return

        if task["status"] == "paused":
            return

        course_id = task["course_id"]
        await self._update_task_status(task_id, "running", message="正在处理...")

        course_data = self.storage.load_course(course_id)
        if not course_data:
            await self._update_task_status(
                task_id, "failed", error="Course not found"
            )
            return

        nodes = course_data.get("nodes", [])
        l1_nodes = [n for n in nodes if n.get("node_level", 1) == 1]
        l2_nodes = [n for n in nodes if n.get("node_level", 1) == 2]

        # ========== Phase 1: Generate L2 sub-nodes for L1 ==========
        l1_needing_children = []
        for l1 in l1_nodes:
            children = [n for n in nodes if n.get("parent_node_id") == l1["node_id"]]
            if not children:
                l1_needing_children.append(l1)

        if l1_needing_children:
            await self._update_task_status(
                task_id, "running",
                message="📚 生成章节结构...",
                total_nodes=len(l1_nodes) + len(l2_nodes),
            )
            # Generate sub-nodes for each L1 (using semaphore for concurrency)
            for l1 in l1_needing_children:
                async with self._semaphore:
                    if not self._running:
                        break
                    try:
                        await self._generate_sub_nodes(task_id, course_id, l1, course_data)
                    except Exception as e:
                        logger.error(
                            "Error generating sub-nodes for %s: %s",
                            l1.get("node_id"), e,
                        )

            # Reload course data after sub-node generation
            course_data = self.storage.load_course(course_id)
            if not course_data:
                return
            nodes = course_data.get("nodes", [])
            l2_nodes = [n for n in nodes if n.get("node_level", 1) == 2]

        # ========== Phase 2: Generate content for L2 nodes ==========
        incomplete_l2 = [n for n in l2_nodes if not self._is_content_complete(n)]

        if not incomplete_l2:
            # All done
            await self._complete_task(task_id, course_data)
            return

        total = len(l1_nodes) + len(l2_nodes)
        completed = len(l1_nodes) + (len(l2_nodes) - len(incomplete_l2))
        await self._update_task_status(
            task_id, "running",
            message="📝 生成正文内容...",
            completed_nodes=completed,
            total_nodes=total,
        )

        # Schedule all incomplete L2 nodes with level-priority
        await self._schedule_nodes(task_id, incomplete_l2)

        # After all nodes processed, check for completion
        course_data = self.storage.load_course(course_id)
        if course_data:
            await self._complete_task(task_id, course_data)

    async def _generate_sub_nodes(
        self,
        task_id: str,
        course_id: str,
        l1_node: dict,
        course_data: dict,
    ) -> None:
        """Generate L2 sub-nodes for an L1 node.

        Args:
            task_id: 任务 ID
            course_id: 课程 ID
            l1_node: L1 节点
            course_data: 课程数据
        """
        node_name = l1_node.get("node_name", "")
        node_id = l1_node.get("node_id", "")

        self._add_log_entry(
            task_id, node_id, node_name=node_name,
            event="start", message=f"Generating sub-nodes for {node_name}",
        )

        try:
            sub_nodes = await self.course_service.generate_sub_nodes(
                node_name=node_name,
                node_level=l1_node.get("node_level", 1),
                node_id=node_id,
                course_name=course_data.get("course_name", ""),
            )

            # Add sub-nodes to course data
            fresh_data = self.storage.load_course(course_id)
            if fresh_data:
                fresh_data.setdefault("nodes", []).extend(sub_nodes)
                await self.storage.save_course(course_id, fresh_data)

            self._add_log_entry(
                task_id, node_id, node_name=node_name,
                event="complete",
                message=f"Generated {len(sub_nodes)} sub-nodes for {node_name}",
            )

            # Push progress
            await self._push_progress(task_id)

        except Exception as e:
            self._add_log_entry(
                task_id, node_id, node_name=node_name,
                event="error", message=f"Failed to generate sub-nodes: {e}",
            )
            raise

    async def _process_node(self, task_id: str, node: dict) -> None:
        """处理单个节点，包含重试和错误恢复。

        使用 asyncio.Semaphore 控制并发，指数退避重试。

        **Validates: Requirements 3.2, 3.5, 13.1, 13.4**

        Args:
            task_id: 任务 ID
            node: 节点字典
        """
        node_id = node.get("node_id", "")
        node_name = node.get("node_name", "")
        task = self.tasks.get(task_id)
        if not task:
            return

        course_id = task["course_id"]
        retries = self._node_retries.setdefault(task_id, {})
        retry_count = retries.get(node_id, 0)

        async with self._semaphore:
            if not self._running:
                return

            start_time = datetime.now()

            async with self._lock:
                node_info = {
                    "node_id": node_id,
                    "node_name": node_name,
                    "action": "生成中",
                    "type": "content" if node.get("node_level", 1) == 2 else "structure",
                }
                current_nodes = task.get("current_nodes", [])
                current_nodes.append(node_info)
                task["current_nodes"] = current_nodes
                if current_nodes:
                    task["current_node_name"] = current_nodes[0].get("node_name", "")
                self.save_tasks()

            self._add_log_entry(
                task_id, node_id, node_name=node_name,
                event="start", message=f"Starting generation for {node_name}",
            )

            await self._push_progress(task_id)

            try:
                await self._set_node_status(
                    course_id, node_id, NodeStatus.GENERATING
                )

                while retry_count <= MAX_RETRIES:
                    try:
                        config = self._build_node_config(node)

                        accumulated: list[str] = []

                        async def on_chunk(chunk: str) -> None:
                            accumulated.append(chunk)
                            if self.ws_service:
                                await self.ws_service.push_stream_chunk(
                                    course_id, node_id, chunk
                                )

                        content = await self.course_service.generate_node_content_stream(
                            course_id=course_id,
                            node=node,
                            config=config,
                            on_chunk=on_chunk,
                        )

                        end_time = datetime.now()
                        duration_ms = (end_time - start_time).total_seconds() * 1000
                        
                        fixed_content = fix_latex_content(content)
                        generated_chars = len(fixed_content) if fixed_content else 0

                        fresh_data = self.storage.load_course(course_id)
                        if fresh_data:
                            for n in fresh_data.get("nodes", []):
                                if n.get("node_id") == node_id:
                                    n["node_content"] = fixed_content
                                    n["generation_status"] = NodeStatus.COMPLETED.value
                                    n["generated_chars"] = generated_chars
                                    n["error_summary"] = None
                                    break
                            await self.storage.save_course(course_id, fresh_data)

                        self._add_log_entry(
                            task_id, node_id, node_name=node_name,
                            event="complete",
                            message=f"Completed {node_name} ({generated_chars} chars)",
                            retry_count=retry_count,
                            generated_chars=generated_chars,
                            duration_ms=duration_ms,
                        )

                        if self.ws_service:
                            await self.ws_service.push_node_completed(
                                course_id,
                                {
                                    "task_id": task_id,
                                    "node_id": node_id,
                                    "node_name": node_name,
                                    "generated_chars": generated_chars,
                                },
                            )

                        await self._push_progress(task_id)

                        if self.on_node_update and fresh_data:
                            try:
                                self.on_node_update(course_id, fresh_data.get("nodes", []))
                            except Exception:
                                pass

                        return

                    except asyncio.CancelledError:
                        logger.info("Node %s generation cancelled", node_id)
                        return

                    except Exception as e:
                        retry_count += 1
                        retries[node_id] = retry_count
                        error_msg = str(e)

                        if retry_count <= MAX_RETRIES:
                            delay = min(
                                (2 ** retry_count) * BACKOFF_BASE, BACKOFF_MAX
                            )
                            self._add_log_entry(
                                task_id, node_id, node_name=node_name,
                                event="retry",
                                message=f"Retry {retry_count}/{MAX_RETRIES}: {error_msg[:100]}",
                                retry_count=retry_count,
                            )
                            logger.warning(
                                "Node %s failed (retry %d/%d), backoff %.1fs: %s",
                                node_id, retry_count, MAX_RETRIES, delay, error_msg[:100],
                            )
                            await asyncio.sleep(delay)
                        else:
                            end_time = datetime.now()
                            duration_ms = (end_time - start_time).total_seconds() * 1000

                            await self._set_node_status(
                                course_id, node_id, NodeStatus.ERROR,
                                error_summary=error_msg[:200],
                            )

                            self._add_log_entry(
                                task_id, node_id, node_name=node_name,
                                event="error",
                                message=f"Failed after {MAX_RETRIES} retries: {error_msg[:200]}",
                                retry_count=retry_count,
                                duration_ms=duration_ms,
                            )

                            if self.ws_service:
                                await self.ws_service.push_error(
                                    course_id,
                                    {
                                        "task_id": task_id,
                                        "node_id": node_id,
                                        "node_name": node_name,
                                        "error": error_msg[:200],
                                        "retry_count": retry_count,
                                    },
                                )

                            await self._push_progress(task_id)
                            return

            finally:
                async with self._lock:
                    current_nodes = task.get("current_nodes", [])
                    task["current_nodes"] = [
                        n for n in current_nodes if n.get("node_id") != node_id
                    ]
                    if task["current_nodes"]:
                        task["current_node_name"] = task["current_nodes"][0].get("node_name", "")
                    else:
                        task["current_node_name"] = ""
                    self.save_tasks()
                await self._push_progress(task_id)

        node_tasks = self._running_node_tasks.get(task_id, {})
        node_tasks.pop(node_id, None)

    # -------------------------------------------------------------------------
    # Command handler (for WebSocketService integration)
    # -------------------------------------------------------------------------

    async def handle_command(self, cmd_type: str, data: dict) -> None:
        """Handle commands from WebSocketService.

        This method is passed as the command_handler callback to WebSocketService.

        Args:
            cmd_type: Command type string
            data: Command data dict with course_id, node_id, payload
        """
        course_id = data.get("course_id", "")
        node_id = data.get("node_id", "")
        payload = data.get("payload") or {}

        # Find the active task for this course
        task_id = self._find_active_task(course_id)
        if not task_id:
            logger.warning(
                "handle_command: no active task for course %s", course_id
            )
            return

        if cmd_type == "skip_node":
            await self.skip_node(task_id, node_id)
        elif cmd_type == "retry_node":
            await self.retry_node(task_id, node_id)
        elif cmd_type == "stop_node":
            await self.stop_node(task_id, node_id)
        elif cmd_type == "retry_all_failed":
            await self.retry_all_failed(task_id)
        elif cmd_type == "custom_instruction":
            # Store custom instruction on the node config
            instruction = payload.get("instruction", "")
            await self._set_custom_instruction(
                course_id, node_id, instruction
            )
        else:
            logger.warning("handle_command: unknown command %s", cmd_type)

    # -------------------------------------------------------------------------
    # Persistence
    # -------------------------------------------------------------------------

    def load_tasks(self) -> None:
        """从文件加载任务。"""
        if os.path.exists(TASKS_FILE):
            try:
                with open(TASKS_FILE, encoding="utf-8") as f:
                    self.tasks = json.load(f)
            except Exception as e:
                logger.error("Failed to load tasks: %s", e)
                self.tasks = {}

    def save_tasks(self) -> None:
        """保存任务到文件。"""
        try:
            with open(TASKS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.tasks, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error("Failed to save tasks: %s", e)

    # -------------------------------------------------------------------------
    # Task logging
    # -------------------------------------------------------------------------

    def _add_log_entry(
        self,
        task_id: str,
        node_id: str,
        node_name: str = "",
        event: str = "start",
        message: str = "",
        retry_count: int = 0,
        generated_chars: int = 0,
        duration_ms: float = 0.0,
    ) -> None:
        """添加任务执行日志条目。

        **Validates: Requirements 13.5**

        Args:
            task_id: 任务 ID
            node_id: 节点 ID
            node_name: 节点名称
            event: 事件类型
            message: 日志消息
            retry_count: 重试次数
            generated_chars: 生成字符数
            duration_ms: 耗时（毫秒）
        """
        entry = TaskLogEntry(
            timestamp=datetime.now(),
            node_id=node_id,
            node_name=node_name,
            event=event,
            message=message,
            retry_count=retry_count,
            generated_chars=generated_chars,
            duration_ms=duration_ms if duration_ms else None,
        )
        self._task_logs.setdefault(task_id, []).append(entry)

        # Also add to the task dict for backward compat
        task = self.tasks.get(task_id)
        if task:
            if "logs" not in task:
                task["logs"] = []
            timestamp = datetime.now().strftime("%H:%M:%S")
            task["logs"].append(f"[{timestamp}] {message}")
            if len(task["logs"]) > 50:
                task["logs"] = task["logs"][-50:]

    def _get_task_log(self, task_id: str) -> list[TaskLogEntry]:
        """获取任务执行日志。

        Args:
            task_id: 任务 ID

        Returns:
            TaskLogEntry 列表
        """
        return self._task_logs.get(task_id, [])

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    async def _update_task_status(
        self,
        task_id: str,
        status: str,
        message: str | None = None,
        error: str | None = None,
        completed_nodes: int | None = None,
        total_nodes: int | None = None,
    ) -> None:
        """更新任务状态。"""
        async with self._lock:
            task = self.tasks.get(task_id)
            if not task:
                return
            task["status"] = status
            if message is not None:
                task["message"] = message
            if error is not None:
                task["error"] = error
            if completed_nodes is not None:
                task["completed_nodes"] = completed_nodes
            if total_nodes is not None:
                task["total_nodes"] = total_nodes
            task["updated_at"] = datetime.now().isoformat()
            self.save_tasks()

    async def _update_progress(
        self, task_id: str, course_data: dict | None = None
    ) -> None:
        """Recalculate and update task progress from course data.

        **Validates: Requirements 8.4**
        """
        task = self.tasks.get(task_id)
        if not task:
            return

        if course_data is None:
            course_data = self.storage.load_course(task["course_id"])
        if not course_data:
            return

        nodes = course_data.get("nodes", [])
        l1_nodes = [n for n in nodes if n.get("node_level", 1) == 1]
        l2_nodes = [n for n in nodes if n.get("node_level", 1) == 2]

        completed_l2 = sum(
            1 for n in l2_nodes if self._is_content_complete(n)
            or n.get("generation_status") in (
                NodeStatus.COMPLETED.value, NodeStatus.SKIPPED.value
            )
        )
        total = len(l1_nodes) + len(l2_nodes)
        completed = len(l1_nodes) + completed_l2

        progress = int(completed / max(1, total) * 100) if total > 0 else 0

        async with self._lock:
            task["completed_nodes"] = completed
            task["total_nodes"] = total
            task["progress"] = min(progress, 100)
            task["updated_at"] = datetime.now().isoformat()
            self.save_tasks()

    async def _push_progress(self, task_id: str) -> None:
        """Push progress update via WebSocket."""
        task = self.tasks.get(task_id)
        if not task or not self.ws_service:
            return

        course_id = task["course_id"]
        await self.ws_service.push_progress_update(
            course_id,
            {
                "task_id": task_id,
                "course_id": course_id,
                "status": task.get("status", ""),
                "progress": task.get("progress", 0),
                "current_node_name": task.get("current_node_name", ""),
                "current_nodes": task.get("current_nodes", []),
                "completed_nodes": task.get("completed_nodes", 0),
                "total_nodes": task.get("total_nodes", 0),
                "estimated_time_remaining": 0,
            },
        )

    async def _complete_task(
        self, task_id: str, course_data: dict
    ) -> None:
        """Mark task as completed and send failure report if needed.

        **Validates: Requirements 13.2**
        """
        nodes = course_data.get("nodes", [])
        failed_nodes = [
            n for n in nodes
            if n.get("generation_status") == NodeStatus.ERROR.value
        ]

        await self._update_progress(task_id, course_data)

        if failed_nodes:
            # Generate failure report
            task = self.tasks.get(task_id)
            course_id = task["course_id"] if task else ""

            report = {
                "task_id": task_id,
                "course_id": course_id,
                "failed_nodes": [
                    {
                        "node_id": n.get("node_id", ""),
                        "node_name": n.get("node_name", ""),
                        "error": n.get("error_summary", "Unknown error"),
                        "retry_count": self._node_retries.get(
                            task_id, {}
                        ).get(n.get("node_id", ""), 0),
                    }
                    for n in failed_nodes
                ],
                "total_failed": len(failed_nodes),
            }

            if self.ws_service:
                await self.ws_service.push_failure_report(course_id, report)

            await self._update_task_status(
                task_id, "completed",
                message=f"完成（{len(failed_nodes)} 个节点失败）",
            )
        else:
            await self._update_task_status(
                task_id, "completed",
                message="✅ 课程生成完成",
            )

        # Push task completed
        task = self.tasks.get(task_id)
        if task and self.ws_service:
            await self.ws_service.push_task_completed(
                task["course_id"],
                {"task_id": task_id, "status": "completed"},
            )

        async with self._lock:
            if task:
                task["progress"] = 100
            self.save_tasks()

    async def _set_node_status(
        self,
        course_id: str,
        node_id: str,
        status: NodeStatus,
        error_summary: str | None = None,
    ) -> None:
        """Update a node's generation_status in course data."""
        course_data = self.storage.load_course(course_id)
        if not course_data:
            return
        for node in course_data.get("nodes", []):
            if node.get("node_id") == node_id:
                node["generation_status"] = status.value
                if error_summary is not None:
                    node["error_summary"] = error_summary
                break
        await self.storage.save_course(course_id, course_data)

    async def _set_custom_instruction(
        self, course_id: str, node_id: str, instruction: str
    ) -> None:
        """Store a custom instruction on a node's generation_config."""
        course_data = self.storage.load_course(course_id)
        if not course_data:
            return
        for node in course_data.get("nodes", []):
            if node.get("node_id") == node_id:
                config = node.get("generation_config") or {}
                config["custom_instruction"] = instruction
                node["generation_config"] = config
                break
        await self.storage.save_course(course_id, course_data)

    def _find_active_task(self, course_id: str) -> str | None:
        """Find the most recent active task for a course."""
        candidates = [
            t for t in self.tasks.values()
            if t["course_id"] == course_id
            and t["status"] in ("pending", "running")
        ]
        if not candidates:
            # Fall back to any task for this course
            candidates = [
                t for t in self.tasks.values()
                if t["course_id"] == course_id
            ]
        if candidates:
            candidates.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
            return candidates[0]["id"]
        return None

    @staticmethod
    def _find_node_name(course_data: dict, node_id: str) -> str:
        """Find a node's name from course data."""
        for node in course_data.get("nodes", []):
            if node.get("node_id") == node_id:
                return node.get("node_name", "")
        return ""

    @staticmethod
    def _is_content_complete(node: dict) -> bool:
        """检查节点内容是否完整。"""
        content = node.get("node_content", "")
        status = node.get("generation_status", "")
        if status in (NodeStatus.COMPLETED.value, NodeStatus.SKIPPED.value):
            return True
        return len(content) > CONTENT_COMPLETE_THRESHOLD

    @staticmethod
    def _build_node_config(node: dict) -> NodeGenerationConfig:
        """Build NodeGenerationConfig from node dict."""
        config_data = node.get("generation_config") or {}
        kwargs: dict[str, Any] = {}
        if config_data.get("difficulty"):
            kwargs["difficulty"] = config_data["difficulty"]
        if config_data.get("style"):
            kwargs["style"] = config_data["style"]
        if config_data.get("custom_instruction"):
            kwargs["custom_instruction"] = config_data["custom_instruction"]
        if config_data.get("target_word_range"):
            kwargs["target_word_range"] = tuple(config_data["target_word_range"])
        if "include_code_examples" in config_data:
            kwargs["include_code_examples"] = config_data["include_code_examples"]
        if "include_exercises" in config_data:
            kwargs["include_exercises"] = config_data["include_exercises"]
        return NodeGenerationConfig(**kwargs)
