"""Versioned, teacher-visible material parsing quality projection."""

from __future__ import annotations

from collections import Counter
from typing import Any

from material_models import MaterialAsset, ParsedDocument

QUALITY_SCHEMA_VERSION = "parsed_document_quality_v2"


def compile_parsed_document_quality(
    document: ParsedDocument,
    asset: MaterialAsset,
) -> dict[str, Any]:
    kinds = Counter(str(block.kind or "other") for block in document.blocks)
    block_count = len(document.blocks)
    located_count = sum(
        1
        for block in document.blocks
        if block.locator.page is not None
        or block.locator.slide is not None
        or block.locator.section_path
    )
    ocr_blocks = [
        block for block in document.blocks
        if block.metadata.get("ocr_engine")
    ]
    ocr_confidences = [
        float(block.metadata.get("ocr_confidence") or 0)
        for block in ocr_blocks
    ]
    issues: list[dict[str, Any]] = []
    capabilities_missing: list[str] = []

    if document.parse_status == "failed" or block_count == 0:
        issues.append({
            "code": "no_usable_content",
            "severity": "blocking",
            "message": "没有解析出可用于课程生成的内容。",
        })
    if document.parser_name == "markitdown":
        capabilities_missing.extend([
            "reading_order",
            "page_or_slide_locator",
            "layout",
            "speaker_notes",
        ])
        issues.append({
            "code": "fallback_text_only",
            "severity": "warning",
            "message": "当前仅完成文本降级提取，版面和来源定位可能缺失。",
        })
    if document.parser_name == "pdf_page_ocr":
        capabilities_missing.extend([
            "table_structure",
            "formula_structure",
            "image_caption_binding",
        ])
        issues.append({
            "code": "ocr_semantics_limited",
            "severity": "warning",
            "message": "扫描 PDF 已逐页 OCR，但表格、公式和图文关系需要人工复核。",
        })
    average_ocr_confidence = (
        round(sum(ocr_confidences) / len(ocr_confidences), 4)
        if ocr_confidences else 0.0
    )
    if ocr_confidences and average_ocr_confidence < 0.85:
        issues.append({
            "code": "low_ocr_confidence",
            "severity": "warning",
            "message": "OCR 平均置信度偏低，事实和题目必须核对原页。",
        })
    if document.warnings:
        issues.append({
            "code": "parser_reported_warnings",
            "severity": "warning",
            "message": "解析器报告了需要注意的降级信息。",
        })

    if any(item["severity"] == "blocking" for item in issues):
        status = "failed"
        suitability = "manual_review"
        summary = "未形成可用证据，请重新上传或改用可读取版本。"
    elif issues or document.parse_status == "degraded":
        status = "needs_review"
        suitability = "teaching_reference"
        summary = "可以作为教学参考，但关键事实应结合原文件复核。"
    else:
        status = "ready"
        suitability = "factual_basis"
        summary = "解析结构和来源定位可用于课程事实依据。"

    report = {
        "schema_version": QUALITY_SCHEMA_VERSION,
        "status": status,
        "suitability": suitability,
        "summary": summary,
        "coverage": {
            "block_count": block_count,
            "text_chars": sum(len(block.text) for block in document.blocks),
            "located_blocks": located_count,
            "location_coverage": round(located_count / max(1, block_count), 3),
            "page_count": int(document.quality.get("page_count") or 0),
            "slide_count": int(document.quality.get("slide_count") or 0),
            "ocr_block_count": len(ocr_blocks),
            "ocr_confidence": average_ocr_confidence,
        },
        "observed_structure": {
            "titles": kinds["title"],
            "headings": kinds["heading"],
            "tables": kinds["table"],
            "formulas": kinds["formula"],
            "pictures": kinds["picture"],
            "questions": kinds["question"],
            "code_blocks": kinds["code"],
        },
        "capabilities_missing": list(dict.fromkeys(capabilities_missing)),
        "issues": issues,
        "parser": {
            "name": document.parser_name,
            "version": document.parser_version,
            "status": document.parse_status,
        },
        "asset": {
            "asset_id": asset.asset_id,
            "filename": asset.filename,
            "extension": asset.extension,
        },
    }
    return report


def parsed_document_preview(
    document: ParsedDocument,
    *,
    limit: int = 12,
) -> list[dict[str, Any]]:
    return [
        {
            "block_id": block.block_id,
            "kind": block.kind,
            "text": " ".join(block.text.split())[:500],
            "locator": block.locator.model_dump(mode="json"),
        }
        for block in document.blocks[: max(1, min(30, limit))]
    ]


__all__ = [
    "QUALITY_SCHEMA_VERSION",
    "compile_parsed_document_quality",
    "parsed_document_preview",
]
