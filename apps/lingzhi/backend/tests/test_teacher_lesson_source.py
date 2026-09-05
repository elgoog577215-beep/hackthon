from __future__ import annotations

from material_models import DocumentBlock, DocumentLocator, ParsedDocument
from teacher_lesson_source import compile_original_lesson_plan_evidence


def _document(blocks: list[DocumentBlock]) -> ParsedDocument:
    return ParsedDocument(
        document_id="doc-1",
        asset_id="mat-1",
        source_sha256="a" * 64,
        parse_status="parsed",
        parser_name="test",
        parser_version="1",
        parse_options_hash="test",
        blocks=blocks,
        created_at="2026-08-24T00:00:00+00:00",
    )


def test_original_lesson_plan_preserves_blocks_order_and_locators():
    document = _document([
        DocumentBlock(
            block_id="b1",
            kind="heading",
            text="概念导入",
            order=0,
            locator=DocumentLocator(page=1, section_path=["概念导入"]),
        ),
        DocumentBlock(
            block_id="b2",
            kind="paragraph",
            text="教师先展示真实案例。",
            order=1,
            locator=DocumentLocator(page=1, section_path=["概念导入"]),
        ),
        DocumentBlock(
            block_id="b3",
            kind="heading",
            text="实践操作",
            order=2,
            locator=DocumentLocator(page=2, section_path=["实践操作"]),
        ),
        DocumentBlock(
            block_id="b4",
            kind="table",
            text="步骤 | 学生活动 | 教师反馈",
            order=3,
            locator=DocumentLocator(page=2, section_path=["实践操作"]),
        ),
    ])

    evidence = compile_original_lesson_plan_evidence(
        document,
        asset_id="mat-1",
        filename="原教案.docx",
        sections=[
            {"node_id": "L2-1", "node_name": "概念导入"},
            {"node_id": "L2-2", "node_name": "实践操作"},
        ],
    )

    assert [item["section_node_id"] for item in evidence] == ["L2-1", "L2-2"]
    assert evidence[0]["block_ids"] == ["b1", "b2"]
    assert evidence[1]["block_ids"] == ["b3", "b4"]
    assert evidence[1]["source_blocks"][1]["kind"] == "table"
    assert evidence[1]["source_blocks"][1]["locator"]["page"] == 2
    assert evidence[0]["fidelity_contract"] == "preserve_structure_fill_missing_only"


def test_unmatched_original_plan_is_contiguously_partitioned_not_round_robin():
    document = _document([
        DocumentBlock(block_id=f"b{index}", text=f"原文 {index}", order=index)
        for index in range(6)
    ])

    evidence = compile_original_lesson_plan_evidence(
        document,
        asset_id="mat-1",
        filename="原教案.pdf",
        sections=[
            {"node_id": "S1", "node_name": "甲"},
            {"node_id": "S2", "node_name": "乙"},
        ],
    )

    assert evidence[0]["block_ids"] == ["b0", "b1", "b2"]
    assert evidence[1]["block_ids"] == ["b3", "b4", "b5"]
