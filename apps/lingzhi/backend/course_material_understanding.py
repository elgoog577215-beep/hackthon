"""AI-assisted understanding for teacher-imported course material batches.

The service keeps deterministic signals as the safety floor and uses one
bounded model call to understand ambiguous document types, course placement,
version roles, cross-file relations, and package gaps.  Model failure never
blocks import and is surfaced as an explicit rule fallback.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ai_base import AIBase, AIProviderRequestError, AIProviderUnavailable
from material_models import ParsedDocument
from teacher_course_space import DOCUMENT_TYPES, classify_document_type

UNDERSTANDING_SCHEMA_VERSION = "course_material_understanding_v1"
UNDERSTANDING_ENGINE_VERSION = "hybrid_classifier_v1"
EXPECTED_PREPARATION_TYPES = ("outline", "lesson_plan", "script", "ppt", "question_bank")
VERSION_ROLES = {"current", "older", "reference", "unknown"}
COURSE_MATCHES = {"matched", "uncertain", "mismatched"}
RELATION_TYPES = {"same_lesson", "same_series", "supersedes", "supports"}

_OLDER_MARKERS = ("旧版", "老版", "历史", "归档", "往年", "原版", "old", "archive", "backup")
_REFERENCE_MARKERS = ("参考", "案例", "素材", "样例", "模板", "reference", "sample", "template")
_CURRENT_MARKERS = ("最新版", "最终版", "终稿", "定稿", "current", "latest", "final")
_GENERIC_STEM_WORDS = (
    "教学大纲", "课程大纲", "大纲", "教案", "教学设计", "教学方案", "逐字稿", "讲义", "授课稿",
    "课件", "ppt", "题库", "试题", "试卷", "考卷", "真题", "最新版", "最终版", "终稿", "定稿",
    "旧版", "老版", "历史", "归档", "参考", "素材", "样例", "模板",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bounded_text(value: Any, limit: int = 300) -> str:
    return str(value or "").strip()[:limit]


def _bounded_confidence(value: Any, default: float) -> float:
    try:
        return max(0.0, min(1.0, round(float(value), 3)))
    except (TypeError, ValueError):
        return default


def _rule_confidence(reason: str, document_type: str) -> float:
    if document_type == "ppt" and "PowerPoint" in reason:
        return 0.99
    if document_type != "other":
        return 0.88
    return 0.32


def _content_document_type(excerpt: str) -> tuple[str, str, float] | None:
    """Recognize high-signal document structures before asking the model."""
    normalized = re.sub(r"\s+", "", excerpt).casefold()
    if not normalized:
        return None
    lesson_plan_signals = ("教学目标", "教学重点", "教学难点", "教学过程", "教学活动", "教学评价")
    outline_signals = ("课程目标", "课程内容", "学时分配", "考核方式", "课程性质", "先修课程")
    script_signals = ("逐字稿", "授课稿", "教师讲解", "教师提问", "同学们", "课堂讲授")
    question_signals = ("选择题", "填空题", "判断题", "参考答案", "答案解析", "本题分值")
    school_signals = ("教学日历", "考场记录", "学生签到", "成绩登记", "材料自查", "归档清单")
    scored = [
        ("lesson_plan", sum(signal in normalized for signal in lesson_plan_signals), lesson_plan_signals),
        ("outline", sum(signal in normalized for signal in outline_signals), outline_signals),
        ("script", sum(signal in normalized for signal in script_signals), script_signals),
        ("question_bank", sum(signal in normalized for signal in question_signals), question_signals),
        ("school_material", sum(signal in normalized for signal in school_signals), school_signals),
    ]
    document_type, score, signals = max(scored, key=lambda item: item[1])
    if score < 2:
        return None
    matched = [signal for signal in signals if signal in normalized][:3]
    confidence = min(0.97, 0.86 + score * 0.025)
    return document_type, f"正文结构包含{'、'.join(matched)}", confidence


def _sequence_number(value: str) -> int | None:
    match = re.search(r"(?:第\s*)?(\d{1,3})\s*(?:讲|课|章|节)", value)
    if match:
        return int(match.group(1))
    chinese = re.search(r"(?:第\s*)?([一二三四五六七八九十百]{1,5})\s*(?:讲|课|章|节)", value)
    if not chinese:
        return None
    digits = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    text = chinese.group(1)
    if text == "十":
        return 10
    if text == "百":
        return 100
    if "百" in text:
        left, right = text.split("百", 1)
        value = digits.get(left, 1) * 100
        text = right
    else:
        value = 0
    if "十" in text:
        left, right = text.split("十", 1)
        value += digits.get(left, 1) * 10 + digits.get(right, 0)
    else:
        value += digits.get(text, 0)
    return value or None


def _version_role(value: str) -> tuple[str, str]:
    lowered = value.casefold()
    for marker in _OLDER_MARKERS:
        if marker.casefold() in lowered:
            return "older", f"文件名或路径包含“{marker}”"
    for marker in _REFERENCE_MARKERS:
        if marker.casefold() in lowered:
            return "reference", f"文件名或路径包含“{marker}”"
    for marker in _CURRENT_MARKERS:
        if marker.casefold() in lowered:
            return "current", f"文件名或路径包含“{marker}”"
    return "unknown", "未发现明确的版本或资料角色信号"


def _relationship_stem(value: str) -> str:
    stem = Path(value).stem.casefold()
    for word in _GENERIC_STEM_WORDS:
        stem = stem.replace(word.casefold(), "")
    stem = re.sub(r"(?:v|ver|版本)?\s*\d+(?:\.\d+)*", "", stem)
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", stem)


def _document_excerpt(document: ParsedDocument | None, limit: int = 4200) -> str:
    if document is None:
        return ""
    parts: list[str] = []
    length = 0
    for block in document.blocks:
        text = str(block.text or "").strip()
        if not text:
            continue
        locator = block.locator
        prefix = ""
        if locator.slide:
            prefix = f"[第{locator.slide}页] "
        elif locator.page:
            prefix = f"[第{locator.page}页] "
        value = f"{prefix}{text}"
        remaining = limit - length
        if remaining <= 0:
            break
        parts.append(value[:remaining])
        length += len(parts[-1]) + 1
    return "\n".join(parts)


def _course_nodes(course: dict[str, Any] | None) -> list[dict[str, Any]]:
    nodes = []
    for index, raw in enumerate((course or {}).get("nodes") or []):
        if not isinstance(raw, dict):
            continue
        title = _bounded_text(raw.get("node_name") or raw.get("title"), 160)
        if not title:
            continue
        nodes.append({
            "node_id": _bounded_text(raw.get("node_id") or f"node-{index + 1}", 180),
            "title": title,
            "level": max(1, min(12, int(raw.get("node_level") or 1))),
            "sequence": index + 1,
        })
        if len(nodes) >= 120:
            break
    return nodes


def _structure_matches(asset: dict[str, Any], excerpt: str, nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    haystack = f"{asset.get('relative_path', '')}\n{excerpt}".casefold()
    sequence = _sequence_number(str(asset.get("relative_path") or asset.get("filename") or ""))
    matches: list[dict[str, Any]] = []
    for node in nodes:
        title = str(node["title"])
        confidence = 0.0
        reason = ""
        if len(title) >= 3 and title.casefold() in haystack:
            confidence, reason = 0.91, "文件内容或路径出现课程结构标题"
        elif sequence and sequence == _sequence_number(title):
            confidence, reason = 0.78, "讲次编号与课程结构一致"
        elif sequence and sequence == node.get("sequence") and int(node.get("level") or 1) <= 2:
            confidence, reason = 0.62, "讲次编号与课程结构顺序一致"
        if confidence:
            matches.append({
                "node_id": node["node_id"],
                "title": title,
                "level": node["level"],
                "confidence": confidence,
                "reason": reason,
            })
    return sorted(matches, key=lambda item: item["confidence"], reverse=True)[:3]


def _course_alignment(
    package: dict[str, Any],
    asset: dict[str, Any],
    excerpt: str,
) -> dict[str, Any]:
    title = _bounded_text(package.get("course_name"), 160)
    haystack = f"{asset.get('relative_path', '')}\n{excerpt}".casefold()
    if title and title.casefold() in haystack:
        return {
            "course_id": _bounded_text(package.get("course_id"), 180),
            "course_title": title,
            "match": "matched",
            "confidence": 0.94,
            "reason": "文件内容或路径出现当前课程名称",
        }
    return {
        "course_id": _bounded_text(package.get("course_id"), 180),
        "course_title": title,
        "match": "uncertain",
        "confidence": 0.5 if package.get("course_id") else 0.35,
        "reason": "文件位于当前课程空间，但正文未出现明确课程名称",
    }


def _deterministic_assets(
    package: dict[str, Any],
    assets: list[dict[str, Any]],
    documents: dict[str, ParsedDocument],
    nodes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    results = []
    for asset in assets:
        relative_path = str(asset.get("relative_path") or asset.get("filename") or "")
        document_type, reason = classify_document_type(relative_path)
        excerpt = _document_excerpt(documents.get(str(asset.get("asset_id") or "")))
        confidence = _rule_confidence(reason, document_type)
        content_type = _content_document_type(excerpt)
        if content_type is not None and (document_type == "other" or content_type[2] > confidence):
            document_type, reason, confidence = content_type
        version_role, version_reason = _version_role(relative_path)
        results.append({
            "asset_id": str(asset.get("asset_id") or ""),
            "document_type": document_type,
            "confidence": confidence,
            "reason": reason,
            "analysis_source": "rule",
            "course_alignment": _course_alignment(package, asset, excerpt),
            "structure_matches": _structure_matches(asset, excerpt, nodes),
            "version_role": version_role,
            "version_reason": version_reason,
            "related_asset_ids": [],
        })
    return results


def _deterministic_relationships(
    assets: list[dict[str, Any]],
    results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_id = {str(item.get("asset_id") or ""): item for item in results}
    relationships: list[dict[str, Any]] = []
    for index, source in enumerate(assets):
        source_id = str(source.get("asset_id") or "")
        source_result = by_id.get(source_id, {})
        source_node = ((source_result.get("structure_matches") or [{}])[0]).get("node_id")
        source_sequence = _sequence_number(str(source.get("relative_path") or source.get("filename") or ""))
        source_stem = _relationship_stem(str(source.get("filename") or ""))
        for target in assets[index + 1:]:
            target_id = str(target.get("asset_id") or "")
            target_result = by_id.get(target_id, {})
            target_node = ((target_result.get("structure_matches") or [{}])[0]).get("node_id")
            target_sequence = _sequence_number(str(target.get("relative_path") or target.get("filename") or ""))
            target_stem = _relationship_stem(str(target.get("filename") or ""))
            relation, confidence, reason = "", 0.0, ""
            if source_node and source_node == target_node:
                relation, confidence, reason = "same_lesson", 0.9, "共同匹配同一课程结构节点"
            elif source_sequence and source_sequence == target_sequence:
                relation, confidence, reason = "same_lesson", 0.82, "文件名包含相同讲次编号"
            elif source_stem and source_stem == target_stem:
                relation, confidence, reason = "same_series", 0.74, "去除类型与版本词后文件主题一致"
            if not relation:
                continue
            relationships.append({
                "source_asset_id": source_id,
                "target_asset_id": target_id,
                "relation": relation,
                "confidence": confidence,
                "reason": reason,
                "analysis_source": "rule",
            })
    return relationships


def _valid_type(value: Any, default: str) -> str:
    normalized = str(value or "").strip()
    return normalized if normalized in DOCUMENT_TYPES else default


def _valid_structure_matches(value: Any, nodes_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    results = []
    for raw in value if isinstance(value, list) else []:
        if not isinstance(raw, dict):
            continue
        node_id = str(raw.get("node_id") or "")
        node = nodes_by_id.get(node_id)
        if node is None:
            continue
        results.append({
            "node_id": node_id,
            "title": node["title"],
            "level": node["level"],
            "confidence": _bounded_confidence(raw.get("confidence"), 0.55),
            "reason": _bounded_text(raw.get("reason"), 240) or "AI 根据正文与课程结构判断",
        })
    return sorted(results, key=lambda item: item["confidence"], reverse=True)[:3]


def _valid_course_alignment(raw: Any, fallback: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return fallback
    match = str(raw.get("match") or "")
    if match not in COURSE_MATCHES:
        match = str(fallback.get("match") or "uncertain")
    return {
        "course_id": fallback.get("course_id", ""),
        "course_title": fallback.get("course_title", ""),
        "match": match,
        "confidence": _bounded_confidence(raw.get("confidence"), float(fallback.get("confidence") or 0.5)),
        "reason": _bounded_text(raw.get("reason"), 260) or fallback.get("reason", ""),
    }


def _provider_failure_code(exc: Exception) -> str:
    reason = str(getattr(exc, "reason", "") or "").strip()
    if reason:
        return reason[:120]
    if isinstance(exc, AIProviderUnavailable):
        return "provider_unavailable"
    if isinstance(exc, AIProviderRequestError):
        return "provider_request_failed"
    return "analysis_failed"


class CourseMaterialUnderstandingModel(AIBase):
    async def analyze(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = await self._call_llm(
            json.dumps(payload, ensure_ascii=False),
            system_prompt=(
                "你是课程资料整理专家。只输出JSON，不解释。必须逐个使用输入asset_id，不得创造文件或课程节点。"
                "从四个维度判断：document_type；course_alignment与structure_matches；version_role；"
                "relationships。document_type只能是outline,lesson_plan,script,ppt,question_bank,"
                "school_material,other。version_role只能是current,older,reference,unknown。"
                "relationships.relation只能是same_lesson,same_series,supersedes,supports。"
                "输出格式为{assets:[{asset_id,document_type,confidence,reason,course_alignment:{match,confidence,reason},"
                "structure_matches:[{node_id,confidence,reason}],version_role,version_reason,related_asset_ids:[]}],"
                "relationships:[{source_asset_id,target_asset_id,relation,confidence,reason}],summary:''}。"
            ),
            use_fast_model=True,
            retry_count=1,
            enable_thinking=False,
            max_tokens=5000,
            max_input_chars=60000,
            raise_on_failure=True,
            json_mode=True,
            model_role="fast",
        )
        value = self._extract_json(response or "")
        if not isinstance(value, dict):
            raise AIProviderRequestError("invalid_material_understanding_json")
        return value


class CourseMaterialUnderstandingService:
    def __init__(
        self,
        *,
        model: CourseMaterialUnderstandingModel | None = None,
        use_model: bool = True,
    ) -> None:
        self.model = model or CourseMaterialUnderstandingModel()
        self.use_model = use_model

    async def analyze_batch(
        self,
        *,
        package: dict[str, Any],
        assets: list[dict[str, Any]],
        documents: dict[str, ParsedDocument] | None = None,
        course: dict[str, Any] | None = None,
        batch_id: str = "",
    ) -> dict[str, Any]:
        documents = documents or {}
        nodes = _course_nodes(course)
        fallback_assets = _deterministic_assets(package, assets, documents, nodes)
        fallback_relationships = _deterministic_relationships(assets, fallback_assets)
        payload = self._payload(package, assets, documents, nodes)
        model_result: dict[str, Any] | None = None
        failure_code = ""
        if self.use_model and assets:
            try:
                model_result = await self.model.analyze(payload)
            except (AIProviderRequestError, AIProviderUnavailable, ValueError, TypeError) as exc:
                failure_code = _provider_failure_code(exc)

        merged_assets = self._merge_assets(fallback_assets, model_result, assets, nodes)
        relationships = self._merge_relationships(fallback_relationships, model_result, merged_assets)
        related: dict[str, set[str]] = {str(item.get("asset_id") or ""): set() for item in merged_assets}
        for relation in relationships:
            source_id, target_id = relation["source_asset_id"], relation["target_asset_id"]
            related.setdefault(source_id, set()).add(target_id)
            related.setdefault(target_id, set()).add(source_id)
        for item in merged_assets:
            item["related_asset_ids"] = sorted(related.get(str(item.get("asset_id") or ""), set()))

        existing_types = {
            str(item.get("document_type") or "")
            for item in package.get("assets") or []
            if str(item.get("asset_id") or "") not in {str(asset.get("asset_id") or "") for asset in assets}
        }
        existing_types.update(str(item.get("document_type") or "") for item in merged_assets)
        missing = [value for value in EXPECTED_PREPARATION_TYPES if value not in existing_types]
        low_confidence = [
            str(item.get("asset_id") or "")
            for item in merged_assets
            if float(item.get("confidence") or 0) < 0.68
            or float((item.get("course_alignment") or {}).get("confidence") or 0) < 0.55
        ]
        ai_count = sum(1 for item in merged_assets if item.get("analysis_source") in {"ai", "hybrid"})
        status = "ai_completed" if model_result is not None and ai_count == len(merged_assets) else "hybrid_completed" if model_result is not None else "rule_fallback"
        return {
            "schema_version": UNDERSTANDING_SCHEMA_VERSION,
            "engine_version": UNDERSTANDING_ENGINE_VERSION,
            "status": status,
            "batch_id": batch_id,
            "analyzed_at": _now(),
            "failure_code": failure_code,
            "summary": _bounded_text((model_result or {}).get("summary"), 500),
            "assets": merged_assets,
            "relationships": relationships,
            "missing_document_types": missing,
            "low_confidence_asset_ids": sorted(set(low_confidence)),
            "dimensions": ["document_type", "course_structure", "version_role", "file_relationships"],
        }

    def _payload(
        self,
        package: dict[str, Any],
        assets: list[dict[str, Any]],
        documents: dict[str, ParsedDocument],
        nodes: list[dict[str, Any]],
    ) -> dict[str, Any]:
        # Keep one batch request useful for both a handful of documents and a
        # mature teacher package.  A fixed per-file excerpt would exceed the
        # provider input budget as soon as the package grows.
        excerpt_limit = max(240, min(4200, 32_000 // max(1, len(assets))))
        return {
            "course": {
                "course_id": _bounded_text(package.get("course_id"), 180),
                "course_name": _bounded_text(package.get("course_name"), 160),
                "academic_year": _bounded_text(package.get("academic_year"), 60),
                "term": _bounded_text(package.get("term"), 60),
                "nodes": nodes,
            },
            "assets": [
                {
                    "asset_id": str(asset.get("asset_id") or ""),
                    "filename": _bounded_text(asset.get("filename"), 260),
                    "relative_path": _bounded_text(asset.get("relative_path"), 600),
                    "extension": _bounded_text(asset.get("extension"), 20),
                    "text_excerpt": _document_excerpt(
                        documents.get(str(asset.get("asset_id") or "")),
                        limit=excerpt_limit,
                    ),
                }
                for asset in assets
            ],
        }

    def _merge_assets(
        self,
        fallback_assets: list[dict[str, Any]],
        model_result: dict[str, Any] | None,
        source_assets: list[dict[str, Any]],
        nodes: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        valid_ids = {str(item.get("asset_id") or "") for item in source_assets}
        nodes_by_id = {str(item["node_id"]): item for item in nodes}
        ai_by_id = {
            str(item.get("asset_id") or ""): item
            for item in (model_result or {}).get("assets") or []
            if isinstance(item, dict) and str(item.get("asset_id") or "") in valid_ids
        }
        source_by_id = {str(item.get("asset_id") or ""): item for item in source_assets}
        merged = []
        for fallback in fallback_assets:
            asset_id = str(fallback["asset_id"])
            raw = ai_by_id.get(asset_id)
            source = source_by_id.get(asset_id, {})
            teacher_confirmed = source.get("classification_source") == "teacher" or source.get("document_type_reason") == "教师确认"
            if raw is None:
                item = dict(fallback)
            else:
                ai_confidence = _bounded_confidence(raw.get("confidence"), 0.5)
                rule_confidence = float(fallback.get("confidence") or 0)
                rule_type = str(fallback.get("document_type") or "other")
                ai_type = _valid_type(raw.get("document_type"), rule_type)
                keep_rule_type = rule_type != "other" and rule_confidence >= 0.88
                item = {
                    **fallback,
                    "document_type": rule_type if keep_rule_type else ai_type,
                    "confidence": rule_confidence if keep_rule_type else ai_confidence,
                    "reason": fallback.get("reason") if keep_rule_type else (_bounded_text(raw.get("reason"), 320) or fallback.get("reason")),
                    "analysis_source": "hybrid" if keep_rule_type else "ai",
                    "course_alignment": _valid_course_alignment(raw.get("course_alignment"), fallback["course_alignment"]),
                    "structure_matches": _valid_structure_matches(raw.get("structure_matches"), nodes_by_id) or fallback["structure_matches"],
                    "version_role": str(raw.get("version_role")) if str(raw.get("version_role")) in VERSION_ROLES else fallback["version_role"],
                    "version_reason": _bounded_text(raw.get("version_reason"), 260) or fallback["version_reason"],
                }
            if teacher_confirmed:
                item.update({
                    "document_type": _valid_type(source.get("document_type"), item["document_type"]),
                    "confidence": 1.0,
                    "reason": "教师确认",
                    "analysis_source": "teacher",
                })
            merged.append(item)
        return merged

    def _merge_relationships(
        self,
        fallback: list[dict[str, Any]],
        model_result: dict[str, Any] | None,
        assets: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        valid_ids = {str(item.get("asset_id") or "") for item in assets}
        merged: dict[tuple[str, str, str], dict[str, Any]] = {}
        for item in fallback:
            key = tuple(sorted((item["source_asset_id"], item["target_asset_id"]))) + (item["relation"],)
            merged[key] = item
        for raw in (model_result or {}).get("relationships") or []:
            if not isinstance(raw, dict):
                continue
            source_id = str(raw.get("source_asset_id") or "")
            target_id = str(raw.get("target_asset_id") or "")
            relation = str(raw.get("relation") or "")
            if source_id not in valid_ids or target_id not in valid_ids or source_id == target_id or relation not in RELATION_TYPES:
                continue
            key = tuple(sorted((source_id, target_id))) + (relation,)
            merged[key] = {
                "source_asset_id": source_id,
                "target_asset_id": target_id,
                "relation": relation,
                "confidence": _bounded_confidence(raw.get("confidence"), 0.6),
                "reason": _bounded_text(raw.get("reason"), 280) or "AI 根据整批资料判断",
                "analysis_source": "ai",
            }
        return sorted(merged.values(), key=lambda item: (-float(item.get("confidence") or 0), item["source_asset_id"], item["target_asset_id"]))


course_material_understanding_service = CourseMaterialUnderstandingService()


__all__ = [
    "CourseMaterialUnderstandingModel",
    "CourseMaterialUnderstandingService",
    "EXPECTED_PREPARATION_TYPES",
    "UNDERSTANDING_ENGINE_VERSION",
    "UNDERSTANDING_SCHEMA_VERSION",
    "course_material_understanding_service",
]
