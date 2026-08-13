"""L3b wiring: the browser's render verdict must reach the publication gate.

Before this the capability existed on both sides but nothing connected them:
`validateRenderedContent` had no caller and `evaluate_node_content`'s
`render_diagnostics` parameter was never passed by any of its call sites.
"""

import pytest

import task_manager as task_manager_module
from task_manager import TaskManager


class _Storage:
    def __init__(self, course):
        self.course = course

    def load_course(self, _course_id):
        return self.course

    async def save_course(self, _course_id, course):
        self.course = course


def _course():
    return {
        "course_id": "c1",
        "course_name": "量子力学",
        "nodes": [{
            "node_id": "L2-1-1",
            "node_name": "波函数",
            "node_level": 2,
            "node_content": "## 波函数\n\n这一节解释波函数的物理意义与归一化条件。",
            "key_points": [],
            "module_plan": [],
            "difficulty_contract": {},
        }],
    }


async def _manager(tmp_path, monkeypatch):
    monkeypatch.setattr(
        task_manager_module, "TASKS_FILE", tmp_path / "generation_jobs.json"
    )
    storage = _Storage(_course())
    manager = TaskManager(storage=storage, course_service=None, ws_service=None)
    task_id = await manager.create_task("c1", course_name="量子力学", enqueue=False)
    return manager, storage, task_id


@pytest.mark.asyncio
async def test_reported_failure_reaches_the_node_quality_report(tmp_path, monkeypatch):
    manager, storage, task_id = await _manager(tmp_path, monkeypatch)

    await manager.record_node_render_diagnostics(
        task_id, "L2-1-1", {"math_failure_count": 2, "block_failure_count": 0}
    )

    node = storage.course["nodes"][0]
    assert node["render_diagnostics"]["math_failure_count"] == 2
    codes = [i["code"] for i in node["generation_quality"]["issues"]]
    assert "math_render_failed" in codes
    assert node["generation_quality"]["passed"] is False
    # L3e: it must be scored as a render defect. The minimal fixture body also
    # fails content checks on its own merits (too short, no difficulty
    # contract), so the meaningful assertion is attribution, not that content
    # happens to pass.
    quality = node["generation_quality"]
    assert quality["render_quality"]["passed"] is False
    assert any(
        i["code"] == "math_render_failed" for i in quality["render_quality"]["issues"]
    )
    assert all(
        i["code"] != "math_render_failed" for i in quality["content_quality"]["issues"]
    )


@pytest.mark.asyncio
async def test_a_clean_report_lets_a_fixed_node_clear_its_issues(tmp_path, monkeypatch):
    """Re-validation must overwrite, or a repaired node stays blocked forever."""
    manager, storage, task_id = await _manager(tmp_path, monkeypatch)

    await manager.record_node_render_diagnostics(
        task_id, "L2-1-1", {"math_failure_count": 3, "block_failure_count": 1}
    )
    await manager.record_node_render_diagnostics(
        task_id, "L2-1-1", {"math_failure_count": 0, "block_failure_count": 0}
    )

    node = storage.course["nodes"][0]
    assert node["render_diagnostics"]["math_failure_count"] == 0
    codes = [i["code"] for i in node["generation_quality"]["issues"]]
    assert "math_render_failed" not in codes
    assert "block_render_failed" not in codes


@pytest.mark.asyncio
async def test_negative_and_garbage_counts_are_clamped(tmp_path, monkeypatch):
    manager, storage, task_id = await _manager(tmp_path, monkeypatch)

    await manager.record_node_render_diagnostics(
        task_id, "L2-1-1", {"math_failure_count": -5, "block_failure_count": 2}
    )

    stored = storage.course["nodes"][0]["render_diagnostics"]
    assert stored["math_failure_count"] == 0
    assert stored["block_failure_count"] == 2


@pytest.mark.asyncio
async def test_reporting_an_unknown_node_does_not_corrupt_the_course(
    tmp_path, monkeypatch
):
    manager, storage, task_id = await _manager(tmp_path, monkeypatch)

    await manager.record_node_render_diagnostics(
        task_id, "does-not-exist", {"math_failure_count": 9}
    )

    assert "render_diagnostics" not in storage.course["nodes"][0]
