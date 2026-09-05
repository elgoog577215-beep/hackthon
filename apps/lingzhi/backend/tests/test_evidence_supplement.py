"""E2 缺资料的知识点单独补搜。

验收（需求清单 E2）：构造单点缺资料场景，确认**检索请求数与范围**符合预期
——只补搜缺来源的那个知识点，不触发全课程重新检索。
"""

from __future__ import annotations

import pytest

from evidence_package import (
    evidence_for_keys,
    freeze_evidence_package,
    knowledge_points_missing_evidence,
    supplement_missing_evidence,
)


def _unit(evidence_id: str, summary: str, keywords: list[str], *, asset_id: str = "a1"):
    return {
        "evidence_id": evidence_id,
        "asset_id": asset_id,
        "document_id": "doc-1",
        "kind": "claim",
        "source_text": summary,
        "summary": summary,
        "keywords": keywords,
        "block_ids": ["b1"],
        "locator": {},
        "content_hash": f"hash-{evidence_id}",
        "purpose": "content_source",
        "priority": "core",
        "authority": "primary",
        "usage_policy": "prefer",
        "factual_allowed": True,
    }


def _package():
    """一门课：特征值有来源，对角化没有。"""
    return freeze_evidence_package(
        course_id="c1",
        evidence=[_unit("e1", "特征值与特征向量的定义", ["特征值", "特征向量"])],
        bindings=[{"asset_id": "a1"}],
    )


class RecordingGateway:
    """记录每次检索的查询，用于验收"请求数与范围"。"""

    def __init__(self, sources=None, raises=False):
        self.calls: list[str] = []
        self.sources = sources if sources is not None else []
        self.raises = raises

    async def retrieve(self, request):
        self.calls.extend(request.queries)
        if self.raises:
            raise RuntimeError("provider down")
        return {
            "schema_version": "retrieval_package_v1",
            "status": "ok",
            "queries": list(request.queries),
            "sources": list(self.sources),
            "rejected_sources": [],
            "errors": [],
            "retrieved_at": "2026-08-10T00:00:00+00:00",
            "package_hash": "pkg",
            "receipt": {"status": "ok"},
        }


FEATURE = {"provider": "searxng", "enabled_for_user": True}


ENABLED = {"retrieval": {"enabled": True}}


# ------------------------------------------------------------ 缺口识别


def test_identifies_only_missing_knowledge_points():
    package = _package()
    missing = knowledge_points_missing_evidence(package, ["特征值", "对角化"])
    assert missing == ["对角化"]


def test_no_missing_when_all_keys_have_evidence():
    package = _package()
    assert knowledge_points_missing_evidence(package, ["特征值"]) == []


def test_empty_keys_yield_no_missing():
    assert knowledge_points_missing_evidence(_package(), []) == []


# -------------------------------------------------- 补搜范围（E2 验收核心）


@pytest.mark.asyncio
async def test_supplement_searches_only_the_missing_point():
    """E2 验收：只对缺来源的知识点发起检索，不扩散到全课程。"""
    package = _package()
    search = RecordingGateway()

    await supplement_missing_evidence(
        package,
        knowledge_keys=["特征值", "对角化"],
        generation_request=ENABLED,
        gateway=search, feature=FEATURE,
    )

    # 有来源的"特征值"不得触发任何检索
    assert search.calls, "缺来源的知识点应当发起检索"
    assert all("对角化" in query for query in search.calls), search.calls


@pytest.mark.asyncio
async def test_no_search_when_nothing_is_missing():
    """全部有来源时一次检索都不该发生。"""
    search = RecordingGateway()
    result = await supplement_missing_evidence(
        _package(), knowledge_keys=["特征值"], generation_request=ENABLED,
        gateway=search, feature=FEATURE,
    )
    assert search.calls == []
    assert result.supplements == []


@pytest.mark.asyncio
async def test_two_missing_points_are_searched_independently():
    """两个缺口分别检索，不合并成一次全课程检索。"""
    package = _package()
    search = RecordingGateway()

    result = await supplement_missing_evidence(
        package,
        knowledge_keys=["对角化", "若尔当标准形"],
        generation_request=ENABLED,
        gateway=search, feature=FEATURE,
    )
    keys = {item.knowledge_key for item in result.supplements}
    assert keys == {"对角化", "若尔当标准形"}


# --------------------------------------------- 冻结不变性（与 E1 的关系）


@pytest.mark.asyncio
async def test_supplement_does_not_change_package_revision_id():
    """补搜以 supplements 追加，已引用该修订的各阶段不会失配。"""
    search = RecordingGateway()
    package = _package()
    before = package.package_revision_id

    result = await supplement_missing_evidence(
        package, knowledge_keys=["对角化"], generation_request=ENABLED,
        gateway=search, feature=FEATURE,
    )
    assert result.package_revision_id == before


@pytest.mark.asyncio
async def test_supplement_does_not_mutate_original_package():
    """补搜返回新对象，不就地修改传入的冻结包。"""
    search = RecordingGateway()
    package = _package()
    original_supplements = len(package.supplements)

    await supplement_missing_evidence(
        package, knowledge_keys=["对角化"], generation_request=ENABLED,
        gateway=search, feature=FEATURE,
    )
    assert len(package.supplements) == original_supplements


@pytest.mark.asyncio
async def test_existing_evidence_units_are_preserved():
    package = _package()
    search = RecordingGateway()
    result = await supplement_missing_evidence(
        package, knowledge_keys=["对角化"], generation_request=ENABLED,
        gateway=search, feature=FEATURE,
    )
    assert {unit.evidence_id for unit in result.units} >= {"e1"}


# ------------------------------------------------------------ 失败与降级


@pytest.mark.asyncio
async def test_no_results_is_recorded_not_silently_dropped():
    """补搜无结果要留痕，便于 D2 诚实标记"这个知识点确实没有来源"。"""
    search = RecordingGateway()
    result = await supplement_missing_evidence(
        _package(), knowledge_keys=["对角化"], generation_request=ENABLED,
        gateway=RecordingGateway(), feature=FEATURE,
    )
    assert len(result.supplements) == 1
    assert result.supplements[0].knowledge_key == "对角化"
    assert result.supplements[0].status in {"no_results", "unavailable"}


@pytest.mark.asyncio
async def test_search_failure_degrades_without_raising():
    """单点补搜失败不得打断流程，也不得影响其他知识点。"""
    result = await supplement_missing_evidence(
        _package(), knowledge_keys=["对角化"], generation_request=ENABLED,
        gateway=RecordingGateway(raises=True), feature=FEATURE,
    )
    assert len(result.supplements) == 1
    assert result.supplements[0].status in {"no_results", "unavailable"}
    # 既有证据不受影响
    assert {unit.evidence_id for unit in result.units} >= {"e1"}


@pytest.mark.asyncio
async def test_retrieval_disabled_still_records_attempt():
    """未授权联网时不发起检索，但仍记录该知识点缺来源。"""
    search = RecordingGateway()
    result = await supplement_missing_evidence(
        _package(), knowledge_keys=["对角化"],
        generation_request={"retrieval": {"enabled": False}},
        gateway=search, feature=FEATURE,
    )
    assert search.calls == []
    assert len(result.supplements) == 1


@pytest.mark.asyncio
async def test_repeated_supplement_is_idempotent():
    """同一知识点重复补搜不产生重复记录。"""
    search = RecordingGateway()
    package = _package()
    once = await supplement_missing_evidence(
        package, knowledge_keys=["对角化"], generation_request=ENABLED,
        gateway=search, feature=FEATURE,
    )
    twice = await supplement_missing_evidence(
        once, knowledge_keys=["对角化"], generation_request=ENABLED,
        gateway=search, feature=FEATURE,
    )
    ids = [item.supplement_id for item in twice.supplements]
    assert len(ids) == len(set(ids))
    assert len(twice.supplements) == len(once.supplements)
