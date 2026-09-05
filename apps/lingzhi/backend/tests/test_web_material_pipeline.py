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
        "content_status": "excerpt_fallback",
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
async def test_full_web_document_keeps_structure_in_the_existing_material_chain(repository):
    candidate = _candidate(
        content_status="full_text",
        content_type="text/html",
        document_text=(
            "# 导数\n\n## 定义\n\n导数描述瞬时变化率。\n\n"
            "## 几何意义\n\n导数对应曲线切线的斜率。"
        ),
        document={
            "schema_version": "web_document_v1",
            "author": "示例大学",
            "fetched_at": "2026-08-23T00:00:00+00:00",
            "content_hash": "document-hash",
        },
    )
    result = await prepare_course_materials(
        course_id="course-1",
        material_bindings=[],
        legacy_materials=[],
        repository=repository,
        web_search_report=_report([candidate]),
    )

    assert result["web_search"]["sources"][0]["content_status"] == "full_text"
    evidence = result["evidence_catalog"]
    assert any("瞬时变化率" in item["source_text"] for item in evidence)
    assert any(item["locator"]["section_path"][-1:] == ["定义"] for item in evidence)


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


def test_cross_language_evidence_binds_as_optional():
    """中文小节现在能绑上英文联网资料（作为 optional）。

    2026-08-09 真实生成发现的缺口：attach_evidence_to_plan 用词面重合筛选，
    中文小节与英文证据恒为 0，node_contracts 整体落空。
    修复后跨语种场景补 optional，但**绝不进 required**（required 是质量门）。
    """
    from material_evidence import attach_evidence_to_plan

    evidence = [{
        "evidence_id": "e1", "asset_id": "a1",
        "summary": "Eigenvalues and eigenvectors of a matrix",
        "keywords": ["eigenvalues", "eigenvectors", "matrix"],
        "source_text": "The eigenvalue problem Ax = lambda x",
        "factual_allowed": True, "purpose": "supplement", "kind": "claim",
        "priority": "supporting", "authority": "secondary",
    }]
    bindings = [{"asset_id": "a1", "usage_policy": "optional", "purpose": "supplement"}]

    def contract_for(title: str, objective: str) -> dict:
        plan = {"chapters": [{"sections": [{
            "node_id": "L2-1-1", "title": title,
            "learning_objective": objective, "key_points": [],
        }]}]}
        _, coverage = attach_evidence_to_plan(
            plan, evidence=evidence, bindings=bindings,
        )
        return coverage["node_contracts"]["L2-1-1"]

    english = contract_for("Eigenvalues and eigenvectors", "compute eigenvalues")
    assert len(english["optional_evidence_ids"]) >= 1

    chinese = contract_for("特征值与特征向量：概念与计算", "能够计算矩阵的特征值")
    # 修复目标：中文小节不再是 0
    assert len(chinese["optional_evidence_ids"]) >= 1
    # 安全边界：跨语种兜底绝不进 required（否则质量门会判"未使用必用证据"）
    assert chinese["required_evidence_ids"] == []


def test_same_language_irrelevant_evidence_is_not_bound():
    """同语种下"没有词面重合"是可信的不相关信号，必须仍然不绑。

    这是防止跨语种兜底退化成"什么都绑"的关键守卫。
    """
    from material_evidence import attach_evidence_to_plan

    evidence = [{
        "evidence_id": "e1", "asset_id": "a1",
        "summary": "唐宋八大家的散文风格与流变",
        "keywords": ["唐宋八大家", "散文", "风格"],
        "source_text": "韩愈提倡古文运动。",
        "factual_allowed": True, "purpose": "supplement", "kind": "claim",
        "priority": "supporting", "authority": "secondary",
    }]
    plan = {"chapters": [{"sections": [{
        "node_id": "L2-1-1", "title": "矩阵对角化与特征多项式",
        "learning_objective": "能够判断矩阵是否可对角化", "key_points": [],
    }]}]}
    _, coverage = attach_evidence_to_plan(
        plan, evidence=evidence,
        bindings=[{"asset_id": "a1", "usage_policy": "optional", "purpose": "supplement"}],
    )
    contract = coverage["node_contracts"]["L2-1-1"]
    assert contract["required_evidence_ids"] == []
    assert contract["optional_evidence_ids"] == []


def test_cross_language_fallback_is_capped():
    """兜底有上限，不会把整批证据倒进单个小节。"""
    from material_evidence import CROSS_LANGUAGE_FALLBACK_LIMIT, attach_evidence_to_plan

    evidence = [{
        "evidence_id": f"e{i}", "asset_id": "a1",
        "summary": f"Lecture note {i} on linear algebra",
        "keywords": ["lecture", "linear", "algebra"],
        "source_text": "content", "factual_allowed": True,
        "purpose": "supplement", "kind": "claim",
        "priority": "supporting", "authority": "secondary",
    } for i in range(10)]
    plan = {"chapters": [{"sections": [{
        "node_id": "L2-1-1", "title": "特征值与特征向量",
        "learning_objective": "掌握特征值计算", "key_points": [],
    }]}]}
    _, coverage = attach_evidence_to_plan(
        plan, evidence=evidence,
        bindings=[{"asset_id": "a1", "usage_policy": "optional", "purpose": "supplement"}],
    )
    contract = coverage["node_contracts"]["L2-1-1"]
    assert len(contract["optional_evidence_ids"]) == CROSS_LANGUAGE_FALLBACK_LIMIT
    assert CROSS_LANGUAGE_FALLBACK_LIMIT <= 3


def test_exact_lexical_match_is_not_displaced_by_fallback():
    """有词面匹配时走原路径，兜底不介入、不稀释。"""
    from material_evidence import attach_evidence_to_plan

    evidence = [
        {"evidence_id": "exact", "asset_id": "a1",
         "summary": "特征值与特征向量的定义",
         "keywords": ["特征值", "特征向量", "定义"],
         "source_text": "特征值定义", "factual_allowed": True,
         "purpose": "content_source", "kind": "definition",
         "priority": "core", "authority": "primary"},
        {"evidence_id": "foreign", "asset_id": "a2",
         "summary": "Eigenvalues lecture note",
         "keywords": ["eigenvalues", "lecture"],
         "source_text": "eigen", "factual_allowed": True,
         "purpose": "supplement", "kind": "claim",
         "priority": "supporting", "authority": "secondary"},
    ]
    plan = {"chapters": [{"sections": [{
        "node_id": "L2-1-1", "title": "特征值与特征向量",
        "learning_objective": "掌握特征值的定义", "key_points": [],
    }]}]}
    _, coverage = attach_evidence_to_plan(
        plan, evidence=evidence,
        bindings=[
            {"asset_id": "a1", "usage_policy": "must_use", "purpose": "content_source"},
            {"asset_id": "a2", "usage_policy": "optional", "purpose": "supplement"},
        ],
    )
    contract = coverage["node_contracts"]["L2-1-1"]
    bound = set(contract["required_evidence_ids"]) | set(contract["optional_evidence_ids"])
    assert "exact" in bound
    # 词面已命中，跨语种兜底不应再塞入无关语种证据
    assert "foreign" not in contract["optional_evidence_ids"]


def test_provenance_header_does_not_defeat_cross_language_fallback():
    """落地的中文出处头不得让英文资料被误判为"同语种"。

    web 资料落地 Markdown 带中文出处头（来源 URL/抓取时间/可信度），
    _keywords 会把它切成中文碎片，导致"英文资料"看起来中英混排，
    跨语种兜底因而不触发。判语种必须从原文剥离出处头后再做。
    """
    from material_evidence import _keywords, attach_evidence_to_plan

    landed = (
        "> 本文为联网检索得到的外部参考资料摘录，非平台原创内容。\n"
        "- 来源 URL：https://ocw.mit.edu/courses/18-06\n"
        "- 抓取时间：2026-08-09T00:00:00+00:00\n"
        "- 可信度标记：high（tier_a）\n"
        "> Eigenvalues and eigenvectors of a matrix."
    )
    evidence = [{
        "evidence_id": "e1", "asset_id": "a1",
        "summary": landed[:200], "keywords": _keywords(landed),
        "source_text": landed, "factual_allowed": True,
        "purpose": "supplement", "kind": "claim",
        "priority": "supporting", "authority": "secondary",
    }]
    plan = {"chapters": [{"sections": [{
        "node_id": "L2-1-1", "title": "特征值与特征向量：概念与计算",
        "learning_objective": "能够计算矩阵的特征值", "key_points": [],
    }]}]}
    _, coverage = attach_evidence_to_plan(
        plan, evidence=evidence,
        bindings=[{"asset_id": "a1", "usage_policy": "optional", "purpose": "supplement"}],
    )
    contract = coverage["node_contracts"]["L2-1-1"]
    assert len(contract["optional_evidence_ids"]) >= 1
    assert contract["required_evidence_ids"] == []


def test_mixed_script_chinese_section_still_triggers_fallback():
    """中文小节夹带公式/编号（2x2、det(A)）不得被误判为"同语种"。

    真实生成的中文小节常含拉丁编号与公式，若按"脚本有交集就算同语种"
    判断，纯英文证据会被当成同语种而不兜底——这正是 2026-08-09 首次
    修复后真跑仍为 0 的原因。判据应为"证据是否含小节主体语种的内容"。
    """
    from material_evidence import _keywords, attach_evidence_to_plan

    english = "Eigenvectors Determinants, eigenvalues, diagonalization"
    evidence = [{
        "evidence_id": "e1", "asset_id": "a1",
        "summary": english, "keywords": _keywords(english),
        "source_text": english, "factual_allowed": True,
        "purpose": "supplement", "kind": "claim",
        "priority": "supporting", "authority": "secondary",
    }]
    plan = {"chapters": [{"sections": [{
        "node_id": "L2-1-1", "title": "特征值与特征向量的概念与求解",
        "learning_objective": "能够根据定义写出特征方程并求解特征值",
        "key_points": ["特征方程的建立与求解"],
        "assessment": ["给定一个2x2矩阵，能正确写出特征多项式"],
    }]}]}
    _, coverage = attach_evidence_to_plan(
        plan, evidence=evidence,
        bindings=[{"asset_id": "a1", "usage_policy": "optional", "purpose": "supplement"}],
    )
    contract = coverage["node_contracts"]["L2-1-1"]
    assert len(contract["optional_evidence_ids"]) >= 1
    assert contract["required_evidence_ids"] == []
