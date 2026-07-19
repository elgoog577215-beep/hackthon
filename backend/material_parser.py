"""成熟解析器适配与统一 ParsedDocument 归一化。"""

from __future__ import annotations

import asyncio
import hashlib
import importlib.metadata
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from material_models import DocumentBlock, DocumentLocator, MaterialAsset, ParsedDocument
from material_storage import IMAGE_EXTENSIONS, TEXT_EXTENSIONS, MaterialRepository

PARSE_OPTIONS_VERSION = "material_parse_v1"


class DocumentParser(Protocol):
    name: str

    def supports(self, extension: str) -> bool: ...

    def parse(self, asset: MaterialAsset, source_path: Path) -> ParsedDocument: ...


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _options_hash(parser_name: str) -> str:
    return hashlib.sha256(f"{PARSE_OPTIONS_VERSION}:{parser_name}".encode()).hexdigest()[:16]


def _quality(blocks: list[DocumentBlock]) -> dict[str, Any]:
    text_chars = sum(len(block.text) for block in blocks)
    located = sum(
        1
        for block in blocks
        if block.locator.page is not None
        or block.locator.slide is not None
        or block.locator.section_path
    )
    pages = [block.locator.page for block in blocks if block.locator.page]
    slides = [block.locator.slide for block in blocks if block.locator.slide]
    return {
        "block_count": len(blocks),
        "text_chars": text_chars,
        "located_blocks": located,
        "location_coverage": round(located / max(1, len(blocks)), 3),
        "page_count": max(pages, default=0),
        "slide_count": max(slides, default=0),
    }


class TextDocumentParser:
    name = "builtin_text"
    version = "1"

    def supports(self, extension: str) -> bool:
        return extension in TEXT_EXTENSIONS

    def parse(self, asset: MaterialAsset, source_path: Path) -> ParsedDocument:
        text = source_path.read_text(encoding="utf-8")
        blocks = self._to_blocks(text)
        return ParsedDocument(
            document_id=f"doc-{uuid.uuid4().hex}",
            asset_id=asset.asset_id,
            source_sha256=asset.sha256,
            parse_status="parsed" if blocks else "metadata_only",
            parser_name=self.name,
            parser_version=self.version,
            parse_options_hash=_options_hash(self.name),
            blocks=blocks,
            quality=_quality(blocks),
            warnings=[] if blocks else ["文本文件没有可用正文"],
            created_at=_now(),
        )

    @staticmethod
    def _to_blocks(text: str) -> list[DocumentBlock]:
        blocks: list[DocumentBlock] = []
        section_path: list[str] = []
        paragraph: list[str] = []

        def flush() -> None:
            if not paragraph:
                return
            value = "\n".join(paragraph).strip()
            paragraph.clear()
            if not value:
                return
            blocks.append(DocumentBlock(
                block_id=f"blk-{len(blocks) + 1}",
                kind=_detect_block_kind(value),
                text=value,
                order=len(blocks),
                locator=DocumentLocator(section_path=list(section_path)),
            ))

        for raw in text.splitlines():
            line = raw.rstrip()
            heading = re.match(r"^(#{1,6})\s+(.+)$", line)
            if heading:
                flush()
                level = len(heading.group(1))
                title = heading.group(2).strip()
                section_path[:] = section_path[: level - 1]
                section_path.append(title)
                blocks.append(DocumentBlock(
                    block_id=f"blk-{len(blocks) + 1}",
                    kind="title" if level == 1 else "heading",
                    text=title,
                    order=len(blocks),
                    locator=DocumentLocator(section_path=list(section_path)),
                    metadata={"heading_level": level},
                ))
            elif not line.strip():
                flush()
            else:
                paragraph.append(line)
        flush()
        return blocks


class ImageOcrParser:
    name = "rapidocr"
    version = "1"

    def supports(self, extension: str) -> bool:
        return extension in IMAGE_EXTENSIONS

    def parse(self, asset: MaterialAsset, source_path: Path) -> ParsedDocument:
        segments = _ocr_image(source_path)
        blocks: list[DocumentBlock] = []
        confidences: list[float] = []
        for segment in segments:
            text = str(segment.get("text") or "").strip()
            if not text:
                continue
            confidence = max(0.0, min(1.0, float(segment.get("confidence") or 0)))
            confidences.append(confidence)
            blocks.append(DocumentBlock(
                block_id=f"blk-{len(blocks) + 1}",
                kind=_detect_block_kind(text),
                text=text,
                order=len(blocks),
                locator=DocumentLocator(
                    page=max(1, int(segment.get("page") or 1)),
                    bbox=_normalized_bbox(segment.get("bbox")),
                ),
                metadata={
                    "ocr_engine": self.name,
                    "ocr_confidence": round(confidence, 4),
                },
            ))
        if not blocks:
            raise RuntimeError("OCR 没有从图片中提取到可用文字")
        average_confidence = round(sum(confidences) / max(1, len(confidences)), 4)
        quality = {
            **_quality(blocks),
            "ocr_confidence": average_confidence,
            "ocr_engine": self.name,
        }
        degraded = average_confidence < 0.85
        return ParsedDocument(
            document_id=f"doc-{uuid.uuid4().hex}",
            asset_id=asset.asset_id,
            source_sha256=asset.sha256,
            parse_status="degraded" if degraded else "parsed",
            parser_name=self.name,
            parser_version=self.version,
            parse_options_hash=_options_hash(self.name),
            blocks=blocks,
            quality=quality,
            warnings=(
                ["OCR 平均置信度低于 0.85，相关题目必须进入教师审核"]
                if degraded
                else []
            ),
            created_at=_now(),
        )


class DoclingDocumentParser:
    name = "docling"

    @property
    def version(self) -> str:
        for package in ("docling-slim", "docling"):
            try:
                return importlib.metadata.version(package)
            except importlib.metadata.PackageNotFoundError:
                continue
        return "unavailable"

    def supports(self, extension: str) -> bool:
        return extension in {".pdf", ".docx", ".pptx", ".xlsx"}

    def parse(self, asset: MaterialAsset, source_path: Path) -> ParsedDocument:
        try:
            from docling.backend.msexcel_backend import MsExcelDocumentBackend
            from docling.backend.mspowerpoint_backend import MsPowerpointDocumentBackend
            from docling.backend.msword_backend import MsWordDocumentBackend
            from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.document import InputDocument
        except ImportError as exc:
            raise RuntimeError("Docling 未安装") from exc
        formats: dict[str, tuple[Any, Any]] = {
            ".docx": (InputFormat.DOCX, MsWordDocumentBackend),
            ".pptx": (InputFormat.PPTX, MsPowerpointDocumentBackend),
            ".xlsx": (InputFormat.XLSX, MsExcelDocumentBackend),
            ".pdf": (InputFormat.PDF, PyPdfiumDocumentBackend),
        }
        input_format, backend_class = formats[asset.extension]
        input_document = InputDocument(source_path, format=input_format, backend=backend_class)
        if not input_document.valid:
            raise RuntimeError("Docling 文件后端无法打开该资料")
        backend = input_document._backend
        if asset.extension == ".pdf":
            blocks = _blocks_from_pdf_backend(backend)
        else:
            document = backend.convert()
            blocks = _blocks_from_docling(document.export_to_dict(), asset.extension)
        if not blocks:
            raise RuntimeError("Docling 没有提取到可用文本；图片型 PDF 需要另行配置 OCR")
        return ParsedDocument(
            document_id=f"doc-{uuid.uuid4().hex}",
            asset_id=asset.asset_id,
            source_sha256=asset.sha256,
            parse_status="parsed",
            parser_name=self.name,
            parser_version=self.version,
            parse_options_hash=_options_hash(self.name),
            blocks=blocks,
            quality=_quality(blocks),
            created_at=_now(),
        )


class MarkItDownFallbackParser:
    name = "markitdown"

    @property
    def version(self) -> str:
        try:
            return importlib.metadata.version("markitdown")
        except importlib.metadata.PackageNotFoundError:
            return "unavailable"

    def supports(self, extension: str) -> bool:
        return extension in {".pdf", ".docx", ".pptx", ".xlsx"}

    def parse(self, asset: MaterialAsset, source_path: Path) -> ParsedDocument:
        try:
            from markitdown import MarkItDown
        except ImportError as exc:
            raise RuntimeError("MarkItDown 未安装") from exc
        result = MarkItDown().convert(str(source_path))
        text = str(getattr(result, "text_content", "") or "").strip()
        blocks = TextDocumentParser._to_blocks(text)
        if not blocks:
            raise RuntimeError("降级解析器没有提取到可用内容")
        return ParsedDocument(
            document_id=f"doc-{uuid.uuid4().hex}",
            asset_id=asset.asset_id,
            source_sha256=asset.sha256,
            parse_status="degraded",
            parser_name=self.name,
            parser_version=self.version,
            parse_options_hash=_options_hash(self.name),
            blocks=blocks,
            quality=_quality(blocks),
            warnings=["当前资料仅完成文本降级提取，页码、布局或 OCR 来源可能不完整"],
            created_at=_now(),
        )


async def parse_material_asset(
    repository: MaterialRepository,
    asset: MaterialAsset,
) -> ParsedDocument:
    cached = repository.load_parsed_document(asset.asset_id)
    if cached and cached.source_sha256 == asset.sha256 and cached.parse_status in {"parsed", "degraded"}:
        return cached

    repository.update_status(asset.asset_id, "parsing")
    source = repository.source_path(asset)
    parsers: list[DocumentParser]
    if asset.extension in TEXT_EXTENSIONS:
        parsers = [TextDocumentParser()]
    elif asset.extension in IMAGE_EXTENSIONS:
        parsers = [ImageOcrParser()]
    else:
        parsers = [DoclingDocumentParser(), MarkItDownFallbackParser()]

    errors: list[str] = []
    for parser in parsers:
        if not parser.supports(asset.extension):
            continue
        try:
            document = await asyncio.to_thread(parser.parse, asset, source)
            repository.save_parsed_document(document)
            repository.update_status(
                asset.asset_id,
                document.parse_status,
                warnings=document.warnings,
                parser_name=document.parser_name,
                parser_version=document.parser_version,
                parse_options_hash=document.parse_options_hash,
                parse_quality=document.quality,
            )
            return document
        except Exception as exc:
            errors.append(f"{parser.name}: {exc}")

    message = "；".join(errors) or "没有可用解析器"
    failed = ParsedDocument(
        document_id=f"doc-{uuid.uuid4().hex}",
        asset_id=asset.asset_id,
        source_sha256=asset.sha256,
        parse_status="failed",
        parser_name="none",
        parser_version="",
        parse_options_hash=_options_hash("none"),
        blocks=[],
        quality=_quality([]),
        error=message,
        created_at=_now(),
    )
    repository.save_parsed_document(failed)
    repository.update_status(asset.asset_id, "failed", error=message)
    return failed


def _blocks_from_docling(data: dict[str, Any], extension: str) -> list[DocumentBlock]:
    blocks: list[DocumentBlock] = []
    visited: set[str] = set()
    section_path: list[str] = []

    def resolve(ref: str) -> dict[str, Any] | None:
        if not ref.startswith("#/"):
            return None
        value: Any = data
        try:
            for part in ref[2:].split("/"):
                value = value[int(part)] if isinstance(value, list) else value[part]
            return value if isinstance(value, dict) else None
        except (KeyError, IndexError, ValueError, TypeError):
            return None

    def visit(item: dict[str, Any]) -> None:
        ref = str(item.get("self_ref") or "")
        if ref and ref in visited:
            return
        if ref:
            visited.add(ref)
        label = str(item.get("label") or "text")
        text = str(item.get("text") or item.get("orig") or "").strip()
        if not text and label == "table":
            cells = (item.get("data") or {}).get("table_cells") or []
            text = " | ".join(str(cell.get("text") or "").strip() for cell in cells if str(cell.get("text") or "").strip())
        if text:
            kind = _docling_kind(label, text)
            if kind in {"title", "heading"}:
                level = int(item.get("level") or (1 if kind == "title" else 2))
                section_path[:] = section_path[: max(0, level - 1)]
                section_path.append(text[:200])
            provenance = item.get("prov") or []
            first = provenance[0] if provenance else {}
            page_no = first.get("page_no")
            locator = DocumentLocator(
                page=int(page_no) if page_no else None,
                slide=int(page_no) if page_no and extension == ".pptx" else None,
                section_path=list(section_path),
                bbox=_normalized_bbox(first.get("bbox")),
            )
            blocks.append(DocumentBlock(
                block_id=f"blk-{len(blocks) + 1}",
                kind=kind,
                text=text,
                order=len(blocks),
                locator=locator,
                metadata={"docling_label": label, "source_ref": ref},
            ))
        for child in item.get("children") or []:
            child_item = resolve(str(child.get("$ref") or "")) if isinstance(child, dict) else None
            if child_item:
                visit(child_item)

    root = data.get("body") or {}
    visit(root)
    if not blocks:
        for collection in ("texts", "tables", "pictures"):
            for item in data.get(collection) or []:
                visit(item)
    return blocks


def _blocks_from_pdf_backend(backend: Any) -> list[DocumentBlock]:
    blocks: list[DocumentBlock] = []
    try:
        for page_number, page in enumerate(backend.iter_pages(), start=1):
            try:
                text = "\n".join(
                    re.sub(r"\s+", " ", str(cell.text or "")).strip()
                    for cell in page.get_text_cells()
                    if str(cell.text or "").strip()
                ).strip()
                if text:
                    blocks.append(DocumentBlock(
                        block_id=f"blk-{len(blocks) + 1}",
                        kind=_detect_block_kind(text),
                        text=text,
                        order=len(blocks),
                        locator=DocumentLocator(page=page_number),
                    ))
            finally:
                page.unload()
    finally:
        backend.unload()
    return blocks


def _docling_kind(label: str, text: str) -> str:
    mapping = {
        "title": "title",
        "section_header": "heading",
        "list_item": "list_item",
        "table": "table",
        "formula": "formula",
        "code": "code",
        "picture": "picture",
    }
    return mapping.get(label, _detect_block_kind(text))


def _detect_block_kind(text: str) -> str:
    stripped = text.strip()
    if re.search(r"(^|\n)(题目|问题|练习|思考)[：:]", stripped) or stripped.endswith(("?", "？")):
        return "question"
    if "```" in stripped:
        return "code"
    if re.search(r"\$[^$]+\$|\\\([^)]*\\\)|\\\[[^]]*\\\]", stripped):
        return "formula"
    if stripped.startswith(("- ", "* ", "1. ")):
        return "list_item"
    return "paragraph"


def _normalized_bbox(raw: Any) -> dict[str, float] | None:
    if not isinstance(raw, dict):
        return None
    result: dict[str, float] = {}
    for key in ("l", "t", "r", "b", "x", "y", "width", "height"):
        if isinstance(raw.get(key), (int, float)):
            result[key] = float(raw[key])
    return result or None


def _ocr_image(path: Path) -> list[dict[str, Any]]:
    """Run optional local OCR without sending course material to a third party."""
    try:
        from PIL import Image
        from rapidocr_onnxruntime import RapidOCR
    except ImportError as exc:
        raise RuntimeError(
            "图片 OCR 组件未安装；请安装 rapidocr-onnxruntime 后重试"
        ) from exc

    engine = RapidOCR()
    raw_result, _elapsed = engine(str(path))
    if not raw_result:
        return []
    with Image.open(path) as image:
        width, height = image.size
    result: list[dict[str, Any]] = []
    for raw in raw_result:
        if not isinstance(raw, (list, tuple)) or len(raw) < 3:
            continue
        points, text, confidence = raw[0], raw[1], raw[2]
        xs = [float(point[0]) for point in points or [] if len(point) >= 2]
        ys = [float(point[1]) for point in points or [] if len(point) >= 2]
        bbox = None
        if xs and ys and width > 0 and height > 0:
            left, right = min(xs), max(xs)
            top, bottom = min(ys), max(ys)
            bbox = {
                "x": round(left / width, 6),
                "y": round(top / height, 6),
                "width": round((right - left) / width, 6),
                "height": round((bottom - top) / height, 6),
            }
        result.append({
            "text": str(text or ""),
            "confidence": float(confidence or 0),
            "bbox": bbox,
            "page": 1,
        })
    return result


__all__ = [
    "DoclingDocumentParser",
    "DocumentParser",
    "MarkItDownFallbackParser",
    "ImageOcrParser",
    "TextDocumentParser",
    "parse_material_asset",
]
