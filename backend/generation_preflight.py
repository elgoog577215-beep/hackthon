"""课程长任务创建前的能力预检。"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from course_versioning import stable_hash
from material_storage import MaterialRepository
from web_retrieval import retrieval_feature_state

PREFLIGHT_SCHEMA_VERSION = "generation_preflight_v1"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _issue(
    code: str,
    *,
    severity: str,
    scope: str,
    message: str,
    action: str,
    item_id: str = "",
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "scope": scope,
        "message": message,
        "action": action,
        "item_id": item_id,
    }


def _material_preflight(
    request: dict[str, Any],
    repository: MaterialRepository,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    issues: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []
    for binding in request.get("material_bindings") or []:
        if not isinstance(binding, dict):
            continue
        asset_id = str(binding.get("asset_id") or "")
        asset = repository.get_asset(asset_id) if asset_id else None
        if asset is None:
            issues.append(_issue(
                "material_missing",
                severity="blocking",
                scope="materials",
                message="引用的资料不存在或已经失效。",
                action="移除该资料后重新上传。",
                item_id=asset_id,
            ))
            items.append({"asset_id": asset_id, "status": "missing", "readable": False})
            continue
        readable = True
        try:
            repository.source_path(asset)
        except Exception:
            readable = False
        item = {
            "asset_id": asset.asset_id,
            "filename": asset.filename,
            "status": asset.status,
            "readable": readable,
            "parser_name": asset.parser_name,
            "quality_state": str(
                (asset.parse_quality or {}).get("quality_state")
                or ("needs_review" if asset.status == "degraded" else "ready")
            ),
        }
        items.append(item)
        if not readable:
            issues.append(_issue(
                "material_source_unreadable",
                severity="blocking",
                scope="materials",
                message=f"资料“{asset.filename}”的原文件不可读。",
                action="移除后重新上传这份资料。",
                item_id=asset.asset_id,
            ))
        elif asset.status == "failed":
            severity = (
                "blocking"
                if str(binding.get("usage_policy") or "") == "must_use"
                else "warning"
            )
            issues.append(_issue(
                "material_parse_failed",
                severity=severity,
                scope="materials",
                message=f"资料“{asset.filename}”没有解析出可用内容。",
                action=(
                    "重新上传可读取版本，或把它改为非必用资料。"
                    if severity == "blocking"
                    else "课程可继续，但这份资料不会作为事实依据。"
                ),
                item_id=asset.asset_id,
            ))
        elif asset.status == "degraded":
            issues.append(_issue(
                "material_parse_degraded",
                severity="warning",
                scope="materials",
                message=f"资料“{asset.filename}”仅完成降级解析。",
                action="查看解析预览，确认缺失的页码、布局或 OCR 不影响课程。",
                item_id=asset.asset_id,
            ))
    return {
        "count": len(items),
        "readable": sum(bool(item.get("readable")) for item in items),
        "estimated_work_units": max(1, len(items)) if items else 0,
        "items": items,
    }, issues


def _retrieval_preflight(
    request: dict[str, Any],
    actor_id: str | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    requested = bool((request.get("retrieval") or {}).get("enabled"))
    feature = retrieval_feature_state(actor_id)
    available = bool(
        feature.get("enabled_for_user") and feature.get("provider_configured")
    )
    issues: list[dict[str, Any]] = []
    if requested and not feature.get("enabled_for_user"):
        issues.append(_issue(
            "retrieval_not_enabled",
            severity="blocking",
            scope="retrieval",
            message="当前账号尚未启用课程联网研究。",
            action="关闭联网研究，或由管理员开启 WEB_RETRIEVAL_V2。",
        ))
    elif requested and not feature.get("provider_configured"):
        issues.append(_issue(
            "retrieval_not_configured",
            severity="blocking",
            scope="retrieval",
            message="联网研究已开启，但搜索服务尚未配置。",
            action="关闭联网研究，或先完成搜索服务配置。",
        ))
    return {
        "requested": requested,
        "available": available if requested else False,
        "status": "ready" if requested and available else ("blocked" if requested else "disabled"),
        "provider": str(feature.get("provider") or ""),
        "mode": str(feature.get("mode") or "off"),
    }, issues


def _capacity_preflight(
    request: dict[str, Any],
    provider: dict[str, Any],
) -> dict[str, Any]:
    brief = request.get("teacher_course_brief") or {}
    sections = int(brief.get("section_count") or 0)
    if sections <= 0:
        total_hours = max(1, int(brief.get("total_class_hours") or 16))
        lesson_minutes = max(20, int(brief.get("lesson_duration_minutes") or 45))
        sections = max(4, min(24, round(total_hours * 60 / lesson_minutes)))
    capacity = provider.get("capacity") or {}
    limit = max(1, int(capacity.get("limit") or 1))
    recommended = max(1, min(3, limit, sections))
    # 目录、知识骨架和全课终检必须串行；知识详情、教案与正文按节有界并行。
    estimated_calls = 3 + sections * 3
    return {
        "recommended_concurrency": recommended,
        "estimated_calls": estimated_calls,
        "estimated_sections": sections,
        "provider_limit": limit,
        "in_flight": max(0, int(capacity.get("in_flight") or 0)),
    }


async def build_generation_preflight(
    request: dict[str, Any],
    *,
    ai_service: Any,
    repository: MaterialRepository,
    actor_id: str | None = None,
    live_probe: bool = True,
) -> dict[str, Any]:
    """返回不含密钥和资料正文的稳定预检投影。"""

    if hasattr(ai_service, "generation_provider_preflight"):
        provider = await ai_service.generation_provider_preflight(
            live_probe=live_probe
        )
    else:
        provider = {
            "status": "ready",
            "probe_status": "not_supported",
            "routes": [],
            "capacity": {},
            "issues": [],
        }
    materials, material_issues = _material_preflight(request, repository)
    retrieval, retrieval_issues = _retrieval_preflight(request, actor_id)
    issues = [
        *deepcopy(provider.get("issues") or []),
        *material_issues,
        *retrieval_issues,
    ]
    status = (
        "blocked"
        if any(item.get("severity") == "blocking" for item in issues)
        else "degraded"
        if any(item.get("severity") == "warning" for item in issues)
        else "ready"
    )
    capacity = _capacity_preflight(request, provider)
    fingerprint = {
        "subject": str(request.get("subject") or "").strip(),
        "course_type": str(request.get("course_type") or "systematic"),
        "material_ids": [
            str(item.get("asset_id") or "")
            for item in request.get("material_bindings") or []
            if isinstance(item, dict)
        ],
        "retrieval_requested": retrieval["requested"],
        "provider_status": provider.get("status"),
        "provider_route": provider.get("active_route"),
        "issue_codes": [str(item.get("code") or "") for item in issues],
    }
    return {
        "schema_version": PREFLIGHT_SCHEMA_VERSION,
        "preflight_id": stable_hash(fingerprint, prefix="gpf_"),
        "status": status,
        "checked_at": _now(),
        "provider_pool": deepcopy(provider.get("routes") or []),
        "provider": {
            key: deepcopy(provider.get(key))
            for key in ("status", "probe_status", "active_route", "duration_ms")
        },
        "retrieval": retrieval,
        "materials": materials,
        "capacity": capacity,
        "issues": issues,
        "acceptance_required": status == "degraded",
    }


__all__ = ["PREFLIGHT_SCHEMA_VERSION", "build_generation_preflight"]
