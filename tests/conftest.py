"""
共享测试 fixtures
提供 FastAPI TestClient、mock storage、mock AI service 等。
"""

import sys
import os
import pytest
import json
import uuid
from unittest.mock import MagicMock, AsyncMock, patch
from copy import deepcopy

# 确保 backend 目录在 sys.path 中
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))

from httpx import AsyncClient, ASGITransport


# ---------------------------------------------------------------------------
# Mock Storage
# ---------------------------------------------------------------------------

class MockStorage:
    """内存中的 mock storage，替代文件系统"""

    def __init__(self):
        self.courses: dict[str, dict] = {}
        self.annotations: list[dict] = []
        self.knowledge_graphs: dict[str, dict] = {}
        self.data: dict[str, object] = {}

    def reset(self):
        self.courses.clear()
        self.annotations.clear()
        self.knowledge_graphs.clear()

    # --- Course ---
    def list_courses(self):
        return [
            {"course_id": cid, "course_name": d.get("course_name", ""), "node_count": len(d.get("nodes", []))}
            for cid, d in self.courses.items()
        ]

    def save_course(self, course_id: str, tree: dict):
        self.courses[course_id] = tree

    def load_course(self, course_id: str):
        return deepcopy(self.courses.get(course_id))

    def delete_course(self, course_id: str):
        self.courses.pop(course_id, None)
        self.knowledge_graphs.pop(course_id, None)

    # --- Annotations ---
    def save_annotation(self, annotation: dict):
        self.annotations.append(annotation)

    def load_annotations(self):
        return list(self.annotations)

    def get_annotations_by_node(self, node_id: str):
        return [a for a in self.annotations if a.get("node_id") == node_id]

    def delete_annotation(self, anno_id: str):
        self.annotations = [a for a in self.annotations if a.get("anno_id") != anno_id]

    def update_annotation(self, anno_id: str, content: str):
        for a in self.annotations:
            if a.get("anno_id") == anno_id:
                a["answer"] = content
                return True
        return False

    def update_annotation_field(self, anno_id: str, field: str, value):
        for a in self.annotations:
            if a.get("anno_id") == anno_id:
                a[field] = value
                return True
        return False

    # --- Knowledge Graph ---
    def save_knowledge_graph(self, course_id: str, graph_data: dict):
        self.knowledge_graphs[course_id] = graph_data

    def load_knowledge_graph(self, course_id: str):
        return deepcopy(self.knowledge_graphs.get(course_id))

    # --- Generic ---
    def load_data(self, filename: str):
        return deepcopy(self.data.get(filename))

    def save_data(self, filename: str, data):
        self.data[filename] = deepcopy(data)


# ---------------------------------------------------------------------------
# Sample Data Factories
# ---------------------------------------------------------------------------

def make_course(course_id: str = None, course_name: str = "测试课程", num_nodes: int = 3) -> dict:
    """创建一个测试用课程数据"""
    cid = course_id or str(uuid.uuid4())
    nodes = []
    root_ids = []
    for i in range(num_nodes):
        nid = str(uuid.uuid4())
        root_ids.append(nid)
        nodes.append({
            "node_id": nid,
            "parent_node_id": "root",
            "node_name": f"第{i+1}章 测试章节",
            "node_level": 1,
            "node_content": f"这是第{i+1}章的内容。",
            "node_type": "original",
        })
    return {
        "course_id": cid,
        "course_name": course_name,
        "nodes": nodes,
    }


def make_annotation(node_id: str, anno_id: str = None, content: str = "测试笔记") -> dict:
    """创建一个测试用标注"""
    return {
        "anno_id": anno_id or f"anno_{uuid.uuid4().hex[:8]}",
        "node_id": node_id,
        "course_id": "test-course",
        "question": "User Note",
        "answer": content,
        "anno_summary": content[:50],
        "source_type": "user",
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_storage():
    """提供一个干净的 MockStorage 实例"""
    return MockStorage()


@pytest.fixture
def sample_course():
    """提供一个预构建的测试课程"""
    return make_course()


@pytest.fixture
def app_with_mock_storage(mock_storage):
    """
    创建一个使用 mock storage 的 FastAPI app 实例。
    通过 monkey-patch storage 模块级单例来实现。
    """
    import storage as storage_module
    import dependencies as deps_module

    original_storage = storage_module.storage

    # Patch storage singleton
    storage_module.storage = mock_storage
    deps_module.storage = mock_storage

    # Re-import app (it uses module-level storage)
    from main import app
    yield app

    # Restore
    storage_module.storage = original_storage
    deps_module.storage = original_storage


@pytest.fixture
async def client(app_with_mock_storage):
    """提供一个异步 HTTP 测试客户端"""
    transport = ASGITransport(app=app_with_mock_storage)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
