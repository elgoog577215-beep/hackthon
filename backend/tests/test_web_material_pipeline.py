"""联网资料接入既有资料链的集成测试。

用真实的 MaterialRepository（临时目录）跑 prepare_course_materials，
验证联网资料确实变成资产、进解析与证据目录，且不建立平行真源。
"""

from __future__ import annotations

import pytest

from material_pipeline import prepare_course_materials
from material_storage import MaterialRepository


@pytest.fixture()
def repository(tmp_path) -> MaterialRepository:
    return MaterialRepository(root=tmp_path / "materials")


def _candidate(url: str = "https://ocw.mit.edu/calc", **overrides) -> dict:
    base = {
        "url": url,
        "domain": "ocw.mit.edu",
        "title": "微积分讲义",
        "text": "导数刻画瞬时变化率，是微积分的核心概念。" * 12,
        "author": "MIT",
        "published_date": "2024-03-01",
        "license": "",
        "open_license": False,
        "credibility": "high",
        "content_hash": "hash-a",
        "retrieved_at": "2026-08-05T00:00:00+00:00",
        "query": "微积分 教程",
    }
    base.update(overrides)
    return base


def _report(candidates: list[dict], **overrides) -> dict:
    base = {
        "enabled": True,
        "status": "ready",
        "degraded": False,
        "queries": ["微积分 教程"],
        "candidates": candidates,
        "rejected": [],
        "message_code": "web_search_ready",
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_web_candidate_becomes_parsed_asset_with_evidence(repository):
    result = await prepare_course_materials(
        course_id="course-1",
        material_bindings=[],
        legacy_materials=[],
        repository=repository,
        web_search_report=_report([_candidate()]),
    )

    assert result["web_search"]["ingested_count"] == 1
    assert result["web_search"]["status"] == "ready"

    # 走的是同一条资产链：有资产、有解析文档、有证据单元。
    assert len(result["material_assets"]) == 1
    assert len(result["parsed_documents"]) == 1
    assert result["parsed_documents"][0]["parse_status"] == "parsed"
    assert result["evidence_catalog"], "联网资料必须进入证据目录才能被引用"

    asset_id = result["web_search"]["sources"][0]["asset_id"]
    assert result["material_assets"][0]["asset_id"] == asset_id
    binding = result["material_bindings"][0]
    assert binding["asset_id"] == asset_id
    assert binding["source_metadata"]["origin"] == "web_search"


@pytest.mark.asyncio
async def test_asset_content_retains_source_url(repository):
    result = await prepare_course_materials(
        course_id="course-1",
        material_bindings=[],
        legacy_materials=[],
        repository=repository,
        web_search_report=_report([_candidate()]),
    )
    asset_id = result["web_search"]["sources"][0]["asset_id"]
    stored = repository.read_asset_text(asset_id) if hasattr(repository, "read_asset_text") else None
    text = stored if stored is not None else result["evidence_catalog"][0].get("text", "")
    # 出处必须留在内容里，生成结果才能回溯到原始网页。
    assert "ocw.mit.edu" in str(text) or "ocw.mit.edu" in str(result["material_assets"][0])


@pytest.mark.asyncio
async def test_web_binding_never_outranks_teacher_material(repository):
    result = await prepare_course_materials(
        course_id="course-1",
        material_bindings=[],
        legacy_materials=[
            {"filename": "teacher.md", "content": "教师导入的权威讲义内容。" * 10, "importance": "core"}
        ],
        repository=repository,
        web_search_report=_report([_candidate()]),
    )
    by_origin = {
        (item["source_metadata"] or {}).get("origin", "teacher"): item
        for item in result["material_bindings"]
    }
    assert by_origin["teacher"]["authority"] == "primary"
    assert by_origin["web_search"]["authority"] != "primary"


@pytest.mark.asyncio
async def test_disabled_report_changes_nothing(repository):
    result = await prepare_course_materials(
        course_id="course-1",
        material_bindings=[],
        legacy_materials=[],
        repository=repository,
        web_search_report={"enabled": False, "status": "disabled", "degraded": True, "candidates": []},
    )
    assert result["material_assets"] == []
    assert result["material_bindings"] == []
    assert result["web_search"]["ingested_count"] == 0
    assert result["web_search"]["status"] == "disabled"


@pytest.mark.asyncio
async def test_missing_report_keeps_legacy_behaviour(repository):
    result = await prepare_course_materials(
        course_id="course-1",
        material_bindings=[],
        legacy_materials=[],
        repository=repository,
    )
    assert result["web_search"]["enabled"] is False
    assert result["web_search"]["ingested_count"] == 0
    assert result["material_assets"] == []


def test_cross_language_evidence_binding_gap_is_documented():
    """跨语言证据绑定为 0：中文小节配英文联网资料时绑不上。

    2026-08-09 真实生成（DeepSeek + SearXNG）发现：联网采用 8 条、
    evidence_catalog 24 条，但 node_contracts 的 required/optional 全为 0。
    根因是 attach_evidence_to_plan 用 _relevance(小节文本, 证据) > 0 筛选，
    而中文小节标题与英文证据摘要词面零重合。

    本用例把现状钉住：同证据下英文小节能绑上、中文小节绑不上。
    修复（加跨语言映射或翻译层）后本用例应改为两者都能绑上。
    """
    from material_evidence import attach_evidence_to_plan

    evidence = [{
        "evidence_id": "e1", "asset_id": "a1",
        "summary": "Eigenvalues and eigenvectors of a matrix",
        "keywords": ["eigenvalues", "eigenvectors", "matrix"],
        "source_text": "The eigenvalue problem Ax = lambda x",
        "factual_allowed": True, "purpose": "supplement", "kind": "claim",
    }]
    bindings = [{"asset_id": "a1", "usage_policy": "optional", "purpose": "supplement"}]

    def bound(title: str, objective: str) -> int:
        plan = {"chapters": [{"sections": [{
            "node_id": "L2-1-1", "title": title,
            "learning_objective": objective, "key_points": [],
        }]}]}
        _, coverage = attach_evidence_to_plan(
            plan, evidence=evidence, bindings=bindings,
        )
        contract = coverage["node_contracts"]["L2-1-1"]
        return len(contract["required_evidence_ids"]) + len(contract["optional_evidence_ids"])

    assert bound("Eigenvalues and eigenvectors", "compute eigenvalues") >= 1
    # 当前缺口：中文小节绑不上英文证据。修复后这一行应改为 >= 1。
    assert bound("特征值与特征向量：概念与计算", "能够计算矩阵的特征值") == 0
