"""资料资产、解析文档和证据目录的单任务编排。"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Any

from material_evidence import build_evidence_units
from material_models import MaterialBinding
from material_parser import parse_material_asset
from material_storage import MaterialRepository, MaterialStorageError, material_repository

MaterialProgressCallback = Callable[[dict[str, Any]], Awaitable[None] | None]


async def ingest_legacy_material_inputs(
    materials: list[Any] | None,
    *,
    repository: MaterialRepository = material_repository,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """把旧请求的内联正文迁移为资产，返回新增绑定和仅元数据兼容项。"""
    bindings: list[dict[str, Any]] = []
    metadata_only: list[dict[str, Any]] = []
    for index, raw in enumerate(materials or [], start=1):
        data = _as_dict(raw)
        content = str(data.pop("content", "") or data.pop("text", "") or "").strip()
        if not content:
            metadata_only.append(data)
            continue
        asset = await repository.create_text_asset(
            filename=str(data.get("filename") or f"legacy-material-{index}.md"),
            content=content,
        )
        binding = _normalize_binding({
            "asset_id": asset.asset_id,
            "purpose": data.get("usage"),
            "priority": data.get("importance"),
            "user_description": data.get("user_description"),
            "source_label": data.get("source_label"),
        })
        bindings.append(binding.model_dump(mode="json"))
    return bindings, metadata_only


async def prepare_course_materials(
    *,
    course_id: str,
    material_bindings: list[Any] | None,
    legacy_materials: list[Any] | None,
    repository: MaterialRepository = material_repository,
    on_progress: MaterialProgressCallback | None = None,
) -> dict[str, Any]:
    bindings = [_normalize_binding(item) for item in material_bindings or []]
    legacy_metadata: list[dict[str, Any]] = []
    for index, raw in enumerate(legacy_materials or [], start=1):
        data = _as_dict(raw)
        content = str(data.get("content") or data.get("text") or "").strip()
        if not content:
            legacy_metadata.append(_legacy_metadata_card(index, data))
            continue
        asset = await repository.create_text_asset(
            filename=str(data.get("filename") or f"legacy-material-{index}.md"),
            content=content,
            upload_batch_id=f"legacy-{course_id}",
        )
        binding = _normalize_binding({
            "asset_id": asset.asset_id,
            "purpose": data.get("usage"),
            "priority": data.get("importance"),
            "user_description": data.get("user_description"),
            "source_label": data.get("source_label"),
        })
        if all(existing.asset_id != binding.asset_id for existing in bindings):
            bindings.append(binding)

    assets: list[dict[str, Any]] = []
    parsed_summaries: list[dict[str, Any]] = []
    evidence_catalog: list[dict[str, Any]] = []
    cards: list[dict[str, Any]] = []
    total = len(bindings)

    for index, binding in enumerate(bindings, start=1):
        asset = repository.bind_asset(binding.asset_id, course_id)
        await _notify(on_progress, {
            "asset_id": asset.asset_id,
            "filename": asset.filename,
            "item_index": index,
            "item_total": total,
            "status": "parsing",
            "message": f"正在解析 {asset.filename}",
        })
        document = await parse_material_asset(repository, asset)
        units = build_evidence_units(document, binding)
        repository.save_evidence(asset.asset_id, [item.model_dump(mode="json") for item in units])
        refreshed = repository.get_asset(asset.asset_id) or asset
        public_asset = repository.public_asset(refreshed)
        assets.append(public_asset)
        evidence_data = [item.model_dump(mode="json") for item in units]
        evidence_catalog.extend(evidence_data)
        parsed_summaries.append({
            "document_id": document.document_id,
            "asset_id": document.asset_id,
            "parse_status": document.parse_status,
            "parser_name": document.parser_name,
            "parser_version": document.parser_version,
            "quality": document.quality,
            "warnings": document.warnings,
            "error": document.error,
        })
        cards.append(_card_from_asset(public_asset, binding))
        await _notify(on_progress, {
            "asset_id": asset.asset_id,
            "filename": asset.filename,
            "item_index": index,
            "item_total": total,
            "status": document.parse_status,
            "message": (
                f"已解析 {asset.filename}"
                if document.parse_status == "parsed"
                else f"{asset.filename}：{document.parse_status}"
            ),
            "page_count": document.quality.get("page_count", 0),
            "block_count": document.quality.get("block_count", 0),
        })

    cards.extend(legacy_metadata)
    return {
        "material_assets": assets,
        "material_bindings": [item.model_dump(mode="json") for item in bindings],
        "parsed_documents": parsed_summaries,
        "evidence_catalog": evidence_catalog,
        "material_cards": cards,
    }


async def _notify(callback: MaterialProgressCallback | None, detail: dict[str, Any]) -> None:
    if not callback:
        return
    result = callback(detail)
    if inspect.isawaitable(result):
        await result


def _normalize_binding(raw: Any) -> MaterialBinding:
    data = _as_dict(raw)
    purpose = str(data.get("purpose") or data.get("usage") or "content_source")
    priority = str(data.get("priority") or data.get("importance") or "core")
    authority = str(data.get("authority") or "")
    usage_policy = str(data.get("usage_policy") or "")
    if not authority:
        authority = "context_only" if purpose in {"style_reference", "weak_context"} else (
            "primary" if priority == "core" else "secondary"
        )
    if not usage_policy:
        if purpose == "style_reference":
            usage_policy = "style_only"
        elif priority == "core":
            usage_policy = "must_use"
        elif priority == "supporting":
            usage_policy = "prefer"
        else:
            usage_policy = "optional"
    return MaterialBinding.model_validate({
        "asset_id": str(data.get("asset_id") or ""),
        "purpose": purpose,
        "priority": priority,
        "authority": authority,
        "usage_policy": usage_policy,
        "user_description": str(data.get("user_description") or ""),
        "source_label": str(data.get("source_label") or ""),
    })


def _card_from_asset(asset: dict[str, Any], binding: MaterialBinding) -> dict[str, Any]:
    return {
        "material_id": binding.asset_id,
        "asset_id": binding.asset_id,
        "filename": asset.get("filename", ""),
        "file_type": str(asset.get("extension") or "").lstrip("."),
        "user_description": binding.user_description,
        "source_label": binding.source_label,
        "usage": binding.purpose,
        "importance": binding.priority,
        "authority": binding.authority,
        "usage_policy": binding.usage_policy,
        "parse_status": asset.get("status", "uploaded"),
        "evidence_state": "verified" if asset.get("status") == "parsed" else asset.get("status"),
    }


def _legacy_metadata_card(index: int, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "material_id": str(data.get("material_id") or f"legacy-metadata-{index}"),
        "filename": str(data.get("filename") or f"旧资料 {index}"),
        "file_type": str(data.get("file_type") or "unknown"),
        "user_description": str(data.get("user_description") or ""),
        "source_label": str(data.get("source_label") or ""),
        "usage": str(data.get("usage") or "weak_context"),
        "importance": str(data.get("importance") or "weak"),
        "authority": "context_only",
        "usage_policy": "optional",
        "parse_status": "metadata_only",
        "evidence_state": "legacy_unverified",
    }


def _as_dict(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    if hasattr(raw, "model_dump"):
        return raw.model_dump(mode="json")
    if hasattr(raw, "dict"):
        return raw.dict()
    raise MaterialStorageError("资料绑定格式无效")


__all__ = ["ingest_legacy_material_inputs", "prepare_course_materials"]
