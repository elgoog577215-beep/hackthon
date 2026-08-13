"""恢复投影必须和即将运行的作业说同一个阶段。"""

import pytest

from task_manager import TaskManager


@pytest.fixture
def manager() -> TaskManager:
    return TaskManager.__new__(TaskManager)


def _resuming_task(step: str) -> dict:
    return {
        "phase": "resuming",
        "current_phase": "resuming",
        "guided_workflow": {
            "current_step": step,
            "steps": [{"key": step, "status": "confirmed"}],
        },
    }


def test_恢复中的任务报出将要回到的阶段而不是resuming(manager):
    # 点了恢复之后，任务列表如果只显示"resuming"，用户看不出会从哪继续
    task = _resuming_task("content")
    assert manager._effective_phase(task) == "content_generation"


def test_推导结果与作业自己用的推导一致(manager):
    # _process_task 用 _processing_handoff 盖阶段；投影必须给同一个答案，
    # 否则列表和跑起来之后显示的阶段对不上
    task = _resuming_task("teaching")
    derived, _ = manager._processing_handoff(task)
    assert manager._effective_phase(task) == derived == "course_teaching_plan"


def test_已经落定的阶段原样返回不被二次猜测(manager):
    task = {"phase": "content_generation", "guided_workflow": {"current_step": "outline"}}
    # 存下来的阶段是权威的：这里只补瞬时态的空档，不去改写作业自己的判断
    assert manager._effective_phase(task) == "content_generation"


def test_质量修复不是瞬时态不应被改写(manager):
    task = {"phase": "quality_repair", "guided_workflow": {"current_step": "content"}}
    assert manager._effective_phase(task) == "quality_repair"


def test_没有阶段也没有工作流时不炸(manager):
    assert manager._effective_phase({}) == "requirement_analysis"
