# =============================================================================
# Task Manager - 课程生成任务管理器
# =============================================================================
#
# 架构说明：
# 本模块负责管理课程生成的异步任务队列，采用生产者-消费者模式。
# 支持批量并行处理，最大并发数可配置。
#
# 生成流程：
# 1. 接收生成任务 → 2. 分析课程结构 → 3. 批量处理节点 → 4. 更新进度
#
# 节点处理顺序（两层结构）：
# L1(章节/Chapter) → L2(子章节+正文/Section+Content)
#
# 两阶段生成：
# 阶段1: L1 生成 L2 子章节结构
# 阶段2: L2 生成详细正文内容
# =============================================================================

import json
import os
import sys
import uuid
import time
import threading
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any, Coroutine
import logging
from pathlib import Path

# Add parent directory to path to import shared config
sys.path.insert(0, str(Path(__file__).parent.parent))
from shared.prompt_config import DIFFICULTY_LEVELS, TEACHING_STYLES

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TASKS_FILE = "tasks.json"

# 批量处理配置
MAX_CONCURRENT = 5  # 最大并发任务数
BATCH_SIZE = 3      # 每批处理节点数

# 内容完整性阈值（字符数）
CONTENT_COMPLETE_THRESHOLD = 600


class TaskManager:
    """课程生成任务管理器
    
    职责：
    1. 管理任务生命周期（创建、执行、暂停、恢复、删除）
    2. 批量并行处理课程节点生成
    3. 持久化任务状态
    """
    
    def __init__(self, storage_module, ai_service_module):
        self.storage = storage_module
        self.ai_service = ai_service_module
        self.tasks: Dict[str, Dict] = {}
        self.lock = threading.Lock()
        self.worker_thread = None
        self.running = False
        self.load_tasks()

    # -------------------------------------------------------------------------
    # Task Lifecycle Management - 任务生命周期管理
    # -------------------------------------------------------------------------
    
    def create_task(self, course_id: str, task_type: str = "auto_generate") -> str:
        """创建新任务"""
        task_id = str(uuid.uuid4())
        task = {
            "id": task_id,
            "course_id": course_id,
            "type": task_type,
            "status": "pending",
            "progress": 0,
            "total": 0,
            "current_node_name": "",
            "message": "Waiting to start...",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "error": None,
            "retry_count": 0
        }
        with self.lock:
            self.tasks[task_id] = task
            self.save_tasks()
        return task_id

    def get_task(self, task_id: str) -> Optional[Dict]:
        """获取任务信息"""
        return self.tasks.get(task_id)

    def get_all_tasks(self, limit: int = 100) -> List[Dict]:
        """获取所有任务，按状态优先级和时间排序"""
        status_priority = {
            "running": 0,
            "pending": 1,
            "paused": 2,
            "failed": 3,
            "completed": 4
        }
        
        with self.lock:
            tasks_list = list(self.tasks.values())
        
        # 先按更新时间降序（最新的在前）
        tasks_list.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        # 再按状态优先级升序（运行中 > 待处理 > 暂停 > 失败 > 完成）
        tasks_list.sort(key=lambda x: status_priority.get(x.get("status", ""), 5))
        
        return tasks_list[:limit]

    def get_tasks_by_course(self, course_id: str) -> List[Dict]:
        """获取指定课程的所有任务"""
        return [t for t in self.tasks.values() if t["course_id"] == course_id]

    def pause_task(self, task_id: str):
        """暂停任务"""
        with self.lock:
            if task_id in self.tasks:
                if self.tasks[task_id]["status"] in ["pending", "running"]:
                    self.tasks[task_id]["status"] = "paused"
                    self.tasks[task_id]["message"] = "Paused by user"
                    self.save_tasks()

    def resume_task(self, task_id: str):
        """恢复任务"""
        with self.lock:
            if task_id in self.tasks:
                if self.tasks[task_id]["status"] == "paused":
                    self.tasks[task_id]["status"] = "pending"
                    self.tasks[task_id]["message"] = "Resuming..."
                    self.save_tasks()

    def delete_task(self, task_id: str):
        """删除任务"""
        with self.lock:
            if task_id in self.tasks:
                del self.tasks[task_id]
                self.save_tasks()

    def clear_failed_tasks(self) -> int:
        """清理失败任务，返回清理数量"""
        with self.lock:
            initial_count = len(self.tasks)
            self.tasks = {tid: t for tid, t in self.tasks.items() 
                         if t.get("status") != "failed"}
            if len(self.tasks) < initial_count:
                self.save_tasks()
            return initial_count - len(self.tasks)

    # -------------------------------------------------------------------------
    # Persistence - 持久化
    # -------------------------------------------------------------------------
    
    def load_tasks(self):
        """从文件加载任务"""
        if os.path.exists(TASKS_FILE):
            try:
                with open(TASKS_FILE, "r", encoding="utf-8") as f:
                    self.tasks = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load tasks: {e}")
                self.tasks = {}

    def save_tasks(self):
        """保存任务到文件"""
        try:
            with open(TASKS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.tasks, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save tasks: {e}")

    # -------------------------------------------------------------------------
    # Worker Management - 工作线程管理
    # -------------------------------------------------------------------------
    
    def start_worker(self):
        """启动工作线程"""
        if not self.running:
            self.running = True
            self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
            self.worker_thread.start()
            logger.info("Task worker started")

    def stop_worker(self):
        """停止工作线程"""
        self.running = False
        if self.worker_thread:
            self.worker_thread.join(timeout=5)

    def _worker_loop(self):
        """工作线程主循环"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._async_manager())

    # -------------------------------------------------------------------------
    # Async Task Processing - 异步任务处理
    # -------------------------------------------------------------------------
    
    async def _async_manager(self):
        """异步任务管理器"""
        running_tasks: Dict[str, asyncio.Task] = {}
        logger.info(f"Async worker manager started. Max concurrent: {MAX_CONCURRENT}")

        while self.running:
            # 1. 清理已完成的任务
            done_ids = []
            for tid, task in running_tasks.items():
                if task.done():
                    done_ids.append(tid)
                    try:
                        await task
                    except Exception as e:
                        logger.error(f"Task {tid} raised exception: {e}")
                        self._update_task_status(tid, "failed", error=str(e))
            
            for tid in done_ids:
                del running_tasks[tid]

            # 2. 填充空闲槽位
            free_slots = MAX_CONCURRENT - len(running_tasks)
            if free_slots > 0:
                candidates = self._get_pending_tasks(running_tasks.keys())
                for i in range(min(free_slots, len(candidates))):
                    tid = candidates[i]
                    future = asyncio.create_task(self._process_task(tid))
                    running_tasks[tid] = future
                    logger.info(f"Started task chunk: {tid}")
            
            await asyncio.sleep(0.1)

    def _get_pending_tasks(self, exclude_ids: set) -> List[str]:
        """获取待处理的任务ID列表"""
        with self.lock:
            candidates = [
                tid for tid, t in self.tasks.items()
                if t["status"] in ["pending", "running"]
                and tid not in exclude_ids
                and t.get("status") != "paused"
            ]
            # 按更新时间升序（最早的优先）
            candidates.sort(key=lambda x: self.tasks[x].get("updated_at", ""))
            return candidates

    def _update_task_status(self, task_id: str, status: str, 
                           message: str = None, error: str = None):
        """更新任务状态"""
        with self.lock:
            if task_id in self.tasks:
                self.tasks[task_id]["status"] = status
                if message:
                    self.tasks[task_id]["message"] = message
                if error:
                    self.tasks[task_id]["error"] = error
                self.tasks[task_id]["updated_at"] = datetime.now().isoformat()
                self.save_tasks()

    # -------------------------------------------------------------------------
    # Core Processing Logic - 核心处理逻辑
    # -------------------------------------------------------------------------
    
    async def _process_task(self, task_id: str):
        """处理单个任务"""
        task = self.tasks.get(task_id)
        if not task or task["status"] == "paused":
            return

        course_id = task["course_id"]
        
        # 标记为运行中
        if task["status"] != "running":
            self._update_task_status(task_id, "running")

        # 加载课程数据
        course_data = self.storage.load_course(course_id)
        if not course_data:
            self._update_task_status(task_id, "failed", error="Course not found")
            return

        # 分析下一步操作
        actions, progress_info = self._analyze_course_structure(course_data)
        
        if not actions:
            # 全部完成
            self._update_task_status(
                task_id, "completed", 
                message="All steps completed"
            )
            with self.lock:
                self.tasks[task_id]["progress"] = 100
                self.save_tasks()
            return

        # 检查是否暂停
        if self.tasks[task_id]["status"] == "paused":
            return

        # 执行批量操作
        try:
            await self._execute_batch_actions(
                task_id, course_id, actions, progress_info
            )
        except Exception as e:
            logger.error(f"Error in task batch: {e}")
            self._handle_task_error(task_id, str(e))

    def _analyze_course_structure(self, course_data: Dict) -> Tuple[List[Tuple], Dict]:
        """分析课程结构，确定下一步操作
        
        流程：L1(章节) → L2(子章节+正文)
        
        Returns:
            actions: 操作列表 [(action_type, node), ...]
            progress_info: 进度信息 {"completed": int, "total": int}
        """
        nodes = course_data.get("nodes", [])
        l1_nodes = [n for n in nodes if n.get("node_level", 1) == 1]
        l2_nodes = [n for n in nodes if n.get("node_level", 1) == 2]
        
        actions = []
        
        # ========== 阶段 1: 为 L1 生成 L2 子章节 ==========
        for l1 in l1_nodes:
            l1_children = [n for n in nodes if n.get("parent_node_id") == l1["node_id"]]
            
            if not l1_children:
                # L1 还没有子章节，需要生成 L2
                actions.append(("subnodes", l1))
                if len(actions) >= BATCH_SIZE:
                    break
        
        if actions:
            # 还有 L2 需要生成，先处理完
            progress_info = {"completed": 0, "total": len(l1_nodes), "phase": "generating_l2"}
            return actions, progress_info
        
        # ========== 阶段 2: 为 L2 生成正文内容 ==========
        incomplete_l2 = [n for n in l2_nodes if not self._is_content_complete(n)]
        
        for l2 in incomplete_l2[:BATCH_SIZE]:
            actions.append(("content", l2))
        
        # 统计完成进度
        completed_l2 = len(l2_nodes) - len(incomplete_l2)
        total_nodes = len(l1_nodes) + len(l2_nodes)
        completed = len(l1_nodes) + completed_l2
        
        progress_info = {
            "completed": completed,
            "total": total_nodes,
            "phase": "generating_content" if incomplete_l2 else "completed"
        }
        return actions, progress_info

    def _is_content_complete(self, node: Dict) -> bool:
        """检查节点内容是否完整"""
        content = node.get("node_content", "")
        return len(content) > CONTENT_COMPLETE_THRESHOLD

    async def _execute_batch_actions(self, task_id: str, course_id: str,
                                    actions: List[Tuple], progress_info: Dict):
        """执行批量操作"""
        task = self.tasks[task_id]
        course_data = self.storage.load_course(course_id)
        
        # 更新任务消息
        task["message"] = self._format_action_message(actions, progress_info)
        task["progress"] = min(95, int(progress_info["completed"] / max(1, progress_info["total"]) * 100))
        task["updated_at"] = datetime.now().isoformat()
        self.save_tasks()
        
        # 准备协程
        coroutines = []
        for action_type, target_node in actions:
            coro = self._create_action_coroutine(
                action_type, target_node, course_data
            )
            coroutines.append((action_type, target_node["node_id"], coro))
        
        # 并行执行
        results = await asyncio.gather(
            *[c[2] for c in coroutines], 
            return_exceptions=True
        )
        
        # 应用结果
        self._apply_results(course_id, coroutines, results)

    def _create_action_coroutine(self, action_type: str, target_node: Dict,
                                 course_data: Dict) -> Coroutine:
        """创建操作协程"""
        difficulty = course_data.get("difficulty", DIFFICULTY_LEVELS["INTERMEDIATE"]).lower()
        style = course_data.get("style", TEACHING_STYLES["ACADEMIC"]).lower()
        
        if action_type == "subnodes":
            # 构建上下文
            nodes = course_data.get("nodes", [])
            l1_nodes = [n for n in nodes if n.get("node_level", 1) == 1]
            course_outline = "\n".join(
                f"{i+1}. {node.get('node_name', '')}" 
                for i, node in enumerate(l1_nodes)
            )
            
            return self.ai_service.generate_sub_nodes(
                target_node["node_name"],
                target_node["node_level"],
                target_node["node_id"],
                course_data.get("course_name", ""),
                target_node.get("node_content", ""),
                course_outline,
                difficulty,
                style
            )
        
        elif action_type == "content":
            return self.ai_service.generate_node_content(
                target_node["node_name"],
                target_node.get("node_context", ""),
                target_node["node_id"],
                course_data.get("course_name", ""),
                difficulty=difficulty,
                style=style
            )

    def _apply_results(self, course_id: str, coroutines: List[Tuple], 
                      results: List[Any]):
        """应用处理结果到课程数据"""
        # 重新加载最新数据
        fresh_data = self.storage.load_course(course_id)
        if not fresh_data:
            logger.error(f"Course {course_id} disappeared during generation")
            return
        
        fresh_nodes = fresh_data.get("nodes", [])
        modified = False
        
        for i, result in enumerate(results):
            action_type, node_id, _ = coroutines[i]
            
            if isinstance(result, Exception):
                logger.error(f"Error processing {node_id}: {result}")
                continue
            
            if action_type == "subnodes":
                # 添加新节点
                fresh_nodes.extend(result)
                modified = True
            
            elif action_type == "content":
                # 更新节点内容
                for n in fresh_nodes:
                    if n["node_id"] == node_id:
                        n["node_content"] = result
                        modified = True
                        break
        
        if modified:
            fresh_data["nodes"] = fresh_nodes
            self.storage.save_course(course_id, fresh_data)

    def _format_action_message(self, actions: List[Tuple], progress_info: Dict = None) -> str:
        """格式化操作消息，显示当前正在生成的章节或正文"""
        if not actions:
            return "等待中..."
        
        # 根据阶段确定前缀和详细描述
        phase = progress_info.get("phase", "") if progress_info else ""
        completed = progress_info.get("completed", 0) if progress_info else 0
        total = progress_info.get("total", 1) if progress_info else 1
        
        if phase == "generating_l2":
            prefix = "📚 生成子章节"
            detail_suffix = "的子章节"
        elif phase == "generating_content":
            prefix = "📝 生成正文"
            detail_suffix = "的正文"
        elif phase == "completed":
            return "✅ 课程生成完成"
        else:
            prefix = "⏳ 处理中"
            detail_suffix = ""
        
        # 构建进度信息
        progress_percent = int(completed / max(1, total) * 100)
        progress_info_str = f"[{completed}/{total} {progress_percent}%]"
        
        # 构建节点名称列表
        msg_parts = []
        for action_type, target_node in actions:
            node_name = target_node.get("node_name", "Unknown")
            # 截断长名称
            if len(node_name) > 20:
                node_name = node_name[:17] + "..."
            msg_parts.append(node_name)
        
        # 组合消息
        if len(actions) == 1:
            # 单个任务：显示详细进度
            node_name = msg_parts[0]
            message = f"{prefix}: {node_name}{detail_suffix} {progress_info_str}"
        else:
            # 多个任务：显示批量进度
            nodes_str = " | ".join(msg_parts)
            message = f"{prefix}: {nodes_str} {progress_info_str}"
        
        # 确保消息长度合理
        if len(message) > 80:
            message = message[:77] + "..."
        
        return message

    def _handle_task_error(self, task_id: str, error_msg: str):
        """处理任务错误"""
        with self.lock:
            task = self.tasks[task_id]
            task["retry_count"] = task.get("retry_count", 0) + 1
            
            if task["retry_count"] > 3:
                task["status"] = "failed"
                task["message"] = f"Failed after 3 retries: {error_msg}"
            else:
                task["message"] = f"Error (Retry {task['retry_count']}/3): {error_msg}"
            
            self.save_tasks()