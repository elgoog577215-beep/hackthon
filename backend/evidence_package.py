"""证据包冻结（E1）与知识点级补搜（E2）。

目标（需求清单 E1）：上传解析与联网研究并行 -> 切分 -> **冻结证据包** ->
之后目录、知识图谱、教案、正文、练习全部引用同一份证据修订。

设计要点：
- `package_revision_id` 由内容哈希得出，内容不变则 ID 不变，是各阶段
  对齐的唯一凭据。
- 冻结后 `units` 不可变；E2 的补搜结果以 `supplements` 追加，
  因此各阶段已经引用的修订 ID 不会漂移。
- 本模块不碰 `course_knowledge_base.py`（归 lz-knowledge），
  只对外提供 `load_frozen_package()` 与 `evidence_for_keys()` 两个入口。
"""

from __future__ import annotations

import re
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from course_versioning import stable_hash
from material_models import (
    EvidencePackage,
    EvidenceSourceRef,
    EvidenceSupplement,
    EvidenceUnit,
)

# 知识点级绑定默认返回条数，避免单个知识点挂一长串来源。
DEFAULT_KEY_MATCH_LIMIT = 3


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return {}


def build_source_index(
    units: list[dict[str, Any]],
    bindings: list[dict[str, Any]],
) -> dict[str, EvidenceSourceRef]:
    """把证据单元与其资料绑定的来源元数据对上。

    联网资料的 `source_metadata.origin == "web_search"`（见
    `web_material_search.candidate_to_binding`），教师上传的没有该标记。
    """
    binding_map = {str(item.get("asset_id") or ""): item for item in bindings}
    index: dict[str, EvidenceSourceRef] = {}
    for unit in units:
        evidence_id = str(unit.get("evidence_id") or "")
        asset_id = str(unit.get("asset_id") or "")
        if not evidence_id:
            continue
        binding = binding_map.get(asset_id) or {}
        metadata = binding.get("source_metadata") or {}
        origin = "web_search" if str(metadata.get("origin") or "") == "web_search" else "material"
        credibility = str(metadata.get("credibility") or "")
        index[evidence_id] = EvidenceSourceRef(
            evidence_id=evidence_id,
            asset_id=asset_id,
            origin=origin,
            url=str(metadata.get("url") or ""),
            retrieved_at=str(metadata.get("retrieved_at") or ""),
            credibility=credibility if credibility in {"high", "medium", "low"} else "",
            reuse_policy=str(binding.get("reuse_policy") or ""),
            rights_basis=str(binding.get("rights_basis") or ""),
        )
    return index


def _coverage(units: list[dict[str, Any]], index: dict[str, EvidenceSourceRef]) -> dict[str, Any]:
    assets = {str(unit.get("asset_id") or "") for unit in units if unit.get("asset_id")}
    web = sum(1 for ref in index.values() if ref.origin == "web_search")
    return {
        "evidence_count": len(units),
        "asset_count": len(assets),
        "web_count": web,
        "material_count": len(index) - web,
    }


def freeze_evidence_package(
    *,
    course_id: str,
    evidence: list[dict[str, Any]] | None,
    bindings: list[dict[str, Any]] | None,
    frozen_at: str | None = None,
) -> EvidencePackage:
    """把当前资料证据冻结成一份带修订 ID 的证据包。

    修订 ID 只由**内容**决定（course_id + 证据身份 + 来源），不含时间戳，
    所以同一批资料重复冻结得到同一个 ID —— 这正是各阶段能对齐的原因。
    """
    units = [_as_dict(item) for item in (evidence or [])]
    units = [item for item in units if item.get("evidence_id")]
    binding_dicts = [_as_dict(item) for item in (bindings or [])]
    index = build_source_index(units, binding_dicts)

    revision_id = stable_hash(
        {
            "course_id": course_id,
            "units": sorted(
                (str(item.get("evidence_id")), str(item.get("content_hash") or ""))
                for item in units
            ),
            "sources": sorted(
                (ref.evidence_id, ref.asset_id, ref.origin) for ref in index.values()
            ),
        },
        prefix="evp_",
    )
    return EvidencePackage(
        package_revision_id=revision_id,
        course_id=course_id,
        frozen_at=frozen_at or _now(),
        status="frozen",
        units=[EvidenceUnit.model_validate(item) for item in units],
        source_index=index,
        supplements=[],
        coverage=_coverage(units, index),
    )


def load_frozen_package(course_data: dict[str, Any]) -> EvidencePackage | None:
    """各阶段统一从这里取冻结包，保证引用同一修订。"""
    raw = (course_data or {}).get("evidence_package")
    if not isinstance(raw, dict) or not raw.get("package_revision_id"):
        return None
    try:
        return EvidencePackage.model_validate(raw)
    except ValueError:
        return None


def package_revision_id(course_data: dict[str, Any]) -> str:
    """取当前课程的证据修订 ID；没有冻结包时返回空串。"""
    package = load_frozen_package(course_data)
    return package.package_revision_id if package else ""


def _normalize_key(value: str) -> str:
    return re.sub(r"[\W_]+", "", str(value or "")).lower()


def _match_score(keys: list[str], unit: EvidenceUnit) -> float:
    """知识点关键词与证据的匹配度。

    只做词面包含判断，不做语义推断——宁可少绑，也不制造看不出依据的绑定。
    """
    haystack = " ".join([
        " ".join(unit.keywords or []),
        unit.summary or "",
    ]).lower()
    compact = _normalize_key(haystack)
    if not compact:
        return 0.0
    hits = 0
    for key in keys:
        normalized = _normalize_key(key)
        if not normalized:
            continue
        if normalized in compact or normalized in haystack:
            hits += 1
    if not hits:
        return 0.0
    score = hits / max(1, len([key for key in keys if _normalize_key(key)]))
    # 同分时更权威、更可复用的证据优先。
    if unit.authority == "primary":
        score += 0.1
    if unit.priority == "core":
        score += 0.05
    return score


def evidence_for_keys(
    package: EvidencePackage | None,
    *,
    keys: list[str],
    limit: int = DEFAULT_KEY_MATCH_LIMIT,
    include_supplements: bool = True,
) -> list[dict[str, Any]]:
    """按知识点关键词取来源引用（D1 第二层用）。

    返回的是**可引用**来源，调用方应放进可选集合而非必用集合：
    `required` 是质量门（`course_quality.evaluate_node_grounding` 未引用
    即判 major），知识点级推断出来的来源进 required 会制造假失败。
    """
    if package is None or not keys:
        return []
    supplement_ids: set[str] = set()
    if include_supplements:
        for item in package.supplements:
            supplement_ids.update(item.unit_ids)

    scored: list[tuple[float, int, EvidenceUnit]] = []
    for order, unit in enumerate(package.units):
        if not unit.factual_allowed:
            continue
        score = _match_score(keys, unit)
        if score <= 0:
            continue
        # 为该知识点补搜回来的证据优先。
        if unit.evidence_id in supplement_ids:
            score += 0.5
        scored.append((score, order, unit))
    scored.sort(key=lambda triple: (-triple[0], triple[1]))

    results: list[dict[str, Any]] = []
    for _, _, unit in scored[: max(0, int(limit))]:
        ref = package.source_index.get(unit.evidence_id)
        results.append({
            "evidence_id": unit.evidence_id,
            "asset_id": unit.asset_id,
            "origin": ref.origin if ref else "material",
            "url": ref.url if ref else "",
            "retrieved_at": ref.retrieved_at if ref else "",
            "credibility": ref.credibility if ref else "",
        })
    return results


def source_status_for_refs(refs: list[dict[str, Any]]) -> str:
    """把来源引用映射为 D1 第一层需要的 source_status。

    无来源时返回 `course_generated`——这是 D2 要求的诚实标记，
    不允许把模型常识伪装成有来源。
    """
    if not refs:
        return "course_generated"
    if any(str(ref.get("origin") or "") == "material" for ref in refs):
        return "material_grounded"
    return "web_grounded"


__all__ = [
    "DEFAULT_KEY_MATCH_LIMIT",
    "build_source_index",
    "evidence_for_keys",
    "freeze_evidence_package",
    "load_frozen_package",
    "package_revision_id",
    "source_status_for_refs",
]
