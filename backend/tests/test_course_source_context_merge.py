"""正文来源上下文：资料链与联网链合流为同一份证据视图。

改动前 `build_course_source_context` 只读 `retrieval_package`，
于是**教师上传的资料在正文这一步拿不到任何来源上下文**——
实测只有 `evidence_catalog` 时返回 0 字符 / 0 引用。
这组用例把该行为钉住，防止再退回单链。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from course_retrieval import build_course_source_context  # noqa: E402


def _material(evidence_id: str, summary: str = "导数是瞬时变化率") -> dict:
    return {
        "evidence_id": evidence_id,
        "asset_id": "asset-1",
        "document_id": "doc-1",
        "kind": "definition",
        "summary": summary,
        "source_text": "完整原文：导数刻画函数在一点处的瞬时变化率。",
        "content_hash": f"hash-{evidence_id}",
    }


def _web(source_id: str) -> dict:
    return {
        "source_id": source_id,
        "trust_tier": "tier_a",
        "title": "导数的直观引入",
        "excerpt": "导数是切线斜率。",
        "url": "https://openstax.org/derivative",
        "domain": "openstax.org",
    }


def test_material_only_course_now_gets_source_context():
    """回归核心：只有上传资料时，正文也必须拿到可引用来源。"""
    context, citation_map, cards = build_course_source_context(
        {"evidence_catalog": [_material("ev1")]}
    )
    assert context, "只有资料证据时不应再返回空上下文"
    assert citation_map == {"S1": "ev1"}
    assert cards[0]["origin"] == "material"
    assert "导数是瞬时变化率" in context


def test_web_only_course_keeps_previous_behaviour():
    context, citation_map, cards = build_course_source_context(
        {"retrieval_package": {"sources": [_web("s1")]}}
    )
    assert citation_map == {"S1": "s1"}
    assert cards[0]["origin"] == "web_search"
    assert "导数是切线斜率" in context


def test_both_chains_merge_with_web_first():
    """两条链共存时合成一份视图，编号连续不重复。"""
    _, citation_map, cards = build_course_source_context({
        "retrieval_package": {"sources": [_web("s1")]},
        "evidence_catalog": [_material("ev1")],
    })
    assert citation_map == {"S1": "s1", "S2": "ev1"}
    assert [card["origin"] for card in cards] == ["web_search", "material"]


def test_no_sources_still_returns_empty():
    """两条链都空时仍返回空，调用方据此跳过来源段落。"""
    assert build_course_source_context({}) == ("", {}, [])


def test_evidence_without_text_is_skipped():
    """没有摘要也没有原文的证据没有可引用内容，不应占用编号。"""
    empty = _material("ev_empty")
    empty["summary"] = ""
    empty["source_text"] = ""
    _, citation_map, _ = build_course_source_context({
        "evidence_catalog": [empty, _material("ev_ok")],
    })
    assert citation_map == {"S1": "ev_ok"}


def test_falls_back_to_source_text_when_summary_missing():
    unit = _material("ev1")
    unit["summary"] = ""
    context, citation_map, _ = build_course_source_context(
        {"evidence_catalog": [unit]}
    )
    assert citation_map == {"S1": "ev1"}
    assert "完整原文" in context


def test_total_sources_stay_capped_at_24():
    """合流不得突破既有 24 条上限，否则正文 prompt 会被证据挤爆。"""
    _, citation_map, _ = build_course_source_context({
        "retrieval_package": {
            "sources": [_web(f"s{i}") for i in range(20)]
        },
        "evidence_catalog": [_material(f"ev{i}") for i in range(20)],
    })
    assert len(citation_map) == 24
    # 联网来源优先占位，资料证据补足余量
    assert sum(1 for v in citation_map.values() if v.startswith("s")) == 20
    assert sum(1 for v in citation_map.values() if v.startswith("ev")) == 4


def test_malformed_catalog_is_ignored():
    for bad in ("not-a-list", None, [None, 123, {}]):
        context, citation_map, _ = build_course_source_context(
            {"evidence_catalog": bad}
        )
        assert citation_map == {}
        assert context == ""
