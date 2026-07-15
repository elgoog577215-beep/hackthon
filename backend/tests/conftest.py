"""Shared pytest fixtures for course-generation-optimization tests.

Provides mock instances of Storage, CourseService, WebSocketService,
a wired TaskManager, and sample course/node data.

Requirements: 16.1, 16.2, 16.3
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from models import NodeStatus


# ---------------------------------------------------------------------------
# Sample data fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_course_data() -> dict:
    """Sample course data dict with L1 and L2 nodes."""
    return {
        "course_id": "course-001",
        "course_name": "机器学习入门",
        "discipline": "natural_science",
        "nodes": [
            {
                "node_id": "L1-1",
                "parent_node_id": "root",
                "node_name": "第1章 概述",
                "node_level": 1,
                "node_content": "",
                "node_type": "original",
                "generation_status": NodeStatus.PENDING.value,
                "generated_chars": 0,
                "error_summary": None,
            },
            {
                "node_id": "L2-1-1",
                "parent_node_id": "L1-1",
                "node_name": "1.1 基本概念",
                "node_level": 2,
                "node_content": "",
                "node_type": "original",
                "generation_status": NodeStatus.PENDING.value,
                "generated_chars": 0,
                "error_summary": None,
            },
            {
                "node_id": "L2-1-2",
                "parent_node_id": "L1-1",
                "node_name": "1.2 发展历程",
                "node_level": 2,
                "node_content": "",
                "node_type": "original",
                "generation_status": NodeStatus.PENDING.value,
                "generated_chars": 0,
                "error_summary": None,
            },
        ],
    }


@pytest.fixture
def sample_node() -> dict:
    """Sample L2 node dict."""
    return {
        "node_id": "L2-1-1",
        "parent_node_id": "L1-1",
        "node_name": "1.1 基本概念",
        "node_level": 2,
        "node_content": "",
        "node_type": "original",
        "generation_status": NodeStatus.PENDING.value,
        "generated_chars": 0,
        "error_summary": None,
    }


# ---------------------------------------------------------------------------
# Mock service fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_storage(sample_course_data: dict) -> MagicMock:
    """Mock Storage instance.

    * ``load_course`` — sync, returns *sample_course_data* by default.
    * ``save_course`` — AsyncMock.
    * ``list_courses`` — sync, returns empty list.
    * ``delete_course`` — sync, returns None.
    * ``validate_all_courses`` — AsyncMock, returns empty list.
    """
    storage = MagicMock()
    storage.load_course = MagicMock(return_value=sample_course_data)
    storage.save_course = AsyncMock()
    storage.list_courses = MagicMock(return_value=[])
    storage.delete_course = MagicMock()
    storage.validate_all_courses = AsyncMock(return_value=[])
    return storage


@pytest.fixture
def mock_course_service() -> MagicMock:
    """Mock CourseService instance.

    * ``generate_node_content_stream`` — AsyncMock returning sample content.
    * ``generate_sub_nodes`` — AsyncMock returning an empty list.
    * ``repair_content`` — AsyncMock returning the original content.
    """
    service = MagicMock()
    service.generate_node_content_stream = AsyncMock(
        return_value="## Test\n\nSample content for the generated node."
    )
    service.generate_sub_nodes = AsyncMock(return_value=[])
    service.repair_content = AsyncMock(side_effect=lambda content, *a, **kw: content)
    return service


@pytest.fixture
def mock_ws_service() -> MagicMock:
    """Mock WebSocketService instance.

    All push methods are AsyncMock.
    """
    ws = MagicMock()
    ws.push_progress_update = AsyncMock()
    ws.push_stream_chunk = AsyncMock()
    ws.push_node_completed = AsyncMock()
    ws.push_node_finalized = AsyncMock()
    ws.push_error = AsyncMock()
    ws.push_task_completed = AsyncMock()
    ws.push_failure_report = AsyncMock()
    return ws


# ---------------------------------------------------------------------------
# Wired TaskManager fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def task_manager(
    mock_storage: MagicMock,
    mock_course_service: MagicMock,
    mock_ws_service: MagicMock,
) -> "TaskManager":  # noqa: F821 — forward ref to avoid import at module level
    """TaskManager instance wired with mock_storage, mock_course_service, mock_ws_service."""
    from task_manager import TaskManager

    tm = TaskManager(
        storage=mock_storage,
        course_service=mock_course_service,
        ws_service=mock_ws_service,
        max_concurrency=5,
    )
    return tm
