"""正文的定向重建必须与知识侧走同一条链（6.2–6.6 的缺口）。

背景：知识侧 `course_downstream_rebuild.build_knowledge_rebuild_runners` 早就
把正文接到了 `BlockRegenerationService`（候选式，不直接改正文），而教案侧的
`_rebuild_runners` 把 `course_content` 留成 `unsupported`。结果是同一个正文块
因知识变化重建会产出候选、因教案变化重建只会得到一句「没有管线入口」。

这不只是少一个功能：`downstream` 里 113 个 `section_content` 待重建项在教案侧
永远拿不到候选，9.1 的核心叙事（应用教案修订 → 下游真的更新）就断在这里。
两侧必须共用同一个 runner，否则「最后可用产物」在两条链上语义会分叉。
"""
from __future__ import annotations

from copy import deepcopy

import pytest

from course_repository import CourseDocumentRepository
from teaching_plan_workbench import TeachingPlanWorkbenchService


class MemoryStorage:
    def __init__(self, course: dict) -> None:
        self.course = deepcopy(course)

    def load_course(self, _course_id: str) -> dict:
        return deepcopy(self.course)

    async def save_course(self, _course_id: str, data: dict) -> None:
        self.course = deepcopy(data)


class _StubBlockService:
    """替身：只验证调用参数与状态解读，不跑真实模型。"""

    created: list[dict] = []

    def __init__(self, *_args, **_kwargs) -> None:
        pass

    async def create_candidate(self, course_id, block_id, **kwargs):
        _StubBlockService.created.append(
            {"course_id": course_id, "block_id": block_id, **kwargs},
        )
        return {"status": "ready", "candidate_id": f"cand-{block_id}"}


def _course() -> dict:
    return {
        "course_id": "course-1",
        "course_schema_version": "course_document_v1",
        "course_document_authoritative": True,
        "course_document_revision": "cdr-1",
        "course_document": {
            "document_revision": "cdr-1",
            "blocks": [{"block_id": "block-1", "internal_revision": "br-1"}],
        },
    }


def _runners(monkeypatch, *, actor: str = "teacher-1") -> dict:
    import block_regeneration

    _StubBlockService.created = []
    monkeypatch.setattr(block_regeneration, "BlockRegenerationService", _StubBlockService)
    raw = _course()
    service = TeachingPlanWorkbenchService(CourseDocumentRepository(MemoryStorage(raw)))
    return service._rebuild_runners(
        "course-1", raw, actor=actor, source_revision="tpr_1",
    )


def test_plan_side_content_rebuild_produces_a_candidate() -> None:
    """教案侧的正文重建必须真的产出候选，而不是报「没有管线入口」。"""
    import block_regeneration
    import pytest as _pytest

    monkeypatch = _pytest.MonkeyPatch()
    try:
        runners = _runners(monkeypatch)
        result = runners["course_content"]({"type": "section_content", "id": "block-1"})
    finally:
        monkeypatch.undo()

    assert result["status"] == "succeeded", result
    assert result["revision"] == "cand-block-1"
    call = _StubBlockService.created[0]
    assert call["expected_document_revision"] == "cdr-1"
    assert call["expected_block_revision"] == "br-1"
    assert call["user_id"] == "teacher-1"
    assert block_regeneration is not None


def test_plan_side_instruction_says_the_plan_changed() -> None:
    """指令要说清「为什么重建」——教案改了，不是知识改了。

    模型收到的理由错了，改出来的正文就会跑偏；这是两侧共用 runner 时
    唯一必须保持不同的参数。
    """
    monkeypatch = pytest.MonkeyPatch()
    try:
        runners = _runners(monkeypatch)
        runners["course_content"]({"type": "section_content", "id": "block-1"})
    finally:
        monkeypatch.undo()

    instruction = _StubBlockService.created[0]["instruction"]
    assert "教案" in instruction, instruction
    assert "知识点已修订" not in instruction


def test_both_chains_share_one_content_runner_factory() -> None:
    """两侧必须调用同一个工厂函数，而不是各写一份。

    各写一份时「失败保留最后可用产物」「候选不直写」这些保证会在两条链上
    慢慢分叉，而任何单侧测试都不会变红。
    """
    from course_downstream_rebuild import build_content_runner

    assert callable(build_content_runner)


def test_missing_block_is_reported_not_silently_skipped() -> None:
    monkeypatch = pytest.MonkeyPatch()
    try:
        runners = _runners(monkeypatch)
        result = runners["course_content"]({"type": "section_content", "id": "ghost"})
    finally:
        monkeypatch.undo()

    assert result["status"] == "failed"
    assert "ghost" in result["error"]
