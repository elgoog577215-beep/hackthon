# =============================================================================
# 共享依赖模块
# 提供路由处理器共用的辅助函数，避免在 main.py 中重复定义。
# =============================================================================

from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from storage import storage


# 模块级引用，由 main.py 在初始化后通过 init_task_manager() / init_ws_service() 设置
_task_manager = None
_ws_service = None


def init_task_manager(tm):
    """由 main.py 调用，注入 TaskManager 实例"""
    global _task_manager
    _task_manager = tm


def require_task_manager():
    """依赖注入：确保Task Manager已初始化"""
    if not _task_manager:
        raise HTTPException(status_code=500, detail="Task Manager not initialized")
    return _task_manager


def init_ws_service(ws):
    """由 main.py 调用，注入 WebSocketService 实例"""
    global _ws_service
    _ws_service = ws


def require_ws_service():
    """依赖注入：确保 WebSocketService 已初始化"""
    if not _ws_service:
        raise HTTPException(status_code=500, detail="WebSocket Service not initialized")
    return _ws_service


async def get_course_or_404(course_id: str) -> dict:
    """获取课程数据，如果不存在则抛出404"""
    data = await run_in_threadpool(storage.load_course, course_id)
    if not data:
        raise HTTPException(status_code=404, detail="Course not found")
    return data


def get_node_or_404(tree_data: dict, node_id: str) -> dict:
    """从课程树中获取节点，如果不存在则抛出404"""
    nodes = tree_data.get("nodes", [])
    node = next((n for n in nodes if n.get("node_id") == node_id), None)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    return node


def build_course_outline(tree_data: dict, max_content_length: int = 50) -> str:
    """构建课程大纲字符串，用于AI上下文"""
    nodes = tree_data.get("nodes", [])
    l1_nodes = [n for n in nodes if n.get("node_level", 1) == 1]
    outline_parts = []
    for i, node in enumerate(l1_nodes):
        content_preview = node.get("node_content", "")[:max_content_length]
        outline_parts.append(f"{i+1}. {node.get('node_name', '')}: {content_preview}...")
    return "\n".join(outline_parts)


def get_node_content(tree_data: dict, node_id: str) -> str:
    """获取指定节点的内容"""
    nodes = tree_data.get("nodes", [])
    node = next((n for n in nodes if n.get("node_id") == node_id), None)
    return node.get("node_content", "") if node else ""
