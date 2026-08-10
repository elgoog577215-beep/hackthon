"""从统一文档编译可追溯证据、覆盖计划和节点接地契约。"""

from __future__ import annotations

import hashlib
import re
import uuid
from collections import defaultdict
from typing import Any

from material_models import (
    CoverageGap,
    EvidenceConflict,
    EvidenceCoveragePlan,
    EvidenceUnit,
    MaterialBinding,
    NodeGroundingContract,
    ParsedDocument,
)


def build_evidence_units(
    document: ParsedDocument,
    binding: MaterialBinding,
) -> list[EvidenceUnit]:
    if document.parse_status not in {"parsed", "degraded"}:
        return []
    units: list[EvidenceUnit] = []
    for block in document.blocks:
        if block.kind in {"title", "heading", "picture"} or not block.text.strip():
            continue
        for part_index, source_text in enumerate(_split_source(block.text)):
            digest = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
            evidence_id = f"ev-{hashlib.sha256(f'{document.asset_id}:{block.block_id}:{part_index}:{digest}'.encode()).hexdigest()[:20]}"
            style_only = binding.purpose in {"style_reference", "weak_context"} or binding.usage_policy == "style_only"
            units.append(EvidenceUnit(
                evidence_id=evidence_id,
                asset_id=document.asset_id,
                document_id=document.document_id,
                kind="style_sample" if style_only else _evidence_kind(source_text, block.kind),
                source_text=source_text,
                summary=_clip(source_text, 220),
                keywords=_keywords(source_text),
                block_ids=[block.block_id],
                locator=block.locator,
                content_hash=digest,
                purpose=binding.purpose,
                priority=binding.priority,
                authority=binding.authority,
                usage_policy=binding.usage_policy,
                factual_allowed=not style_only,
                confidence="low" if document.parse_status == "degraded" else "high",
            ))
    return units


def build_evidence_catalog_summary(
    evidence: list[dict[str, Any]],
    max_items: int = 80,
    *,
    max_chars: int | None = None,
) -> str:
    if not evidence:
        return "- 没有可用资料证据。"
    lines: list[str] = []
    for item in _sample_evidence_for_summary(evidence, max_items):
        locator = item.get("locator") or {}
        location = ""
        if locator.get("page"):
            location = f"p.{locator['page']}"
        elif locator.get("slide"):
            location = f"slide {locator['slide']}"
        elif locator.get("section_path"):
            location = " / ".join(locator["section_path"][-2:])
        line = (
            f"- [{item.get('evidence_id')}] {item.get('kind')} {location}："
            f"{_clip(str(item.get('summary') or ''), 180)}"
        )
        if (
            max_chars is not None
            and lines
            and len("\n".join([*lines, line])) > max_chars
        ):
            break
        lines.append(line)
    if len(lines) < min(len(evidence), max_items):
        lines.append(
            f"- 其余证据保留在服务端索引中，目录阶段未展开 "
            f"{len(evidence) - len(lines)} 条。"
        )
    return "\n".join(lines)


def _sample_evidence_for_summary(
    evidence: list[dict[str, Any]], max_items: int
) -> list[dict[str, Any]]:
    """Select up to ``max_items`` evidence entries with even coverage across assets.

    A plain ``evidence[:max_items]`` truncation was systematically biased
    towards whichever asset happened to be uploaded/parsed first, since
    evidence blocks are appended in upload order. When many assets are
    bound (e.g. 20 years of exam papers), the earliest ones alone could
    fill the entire summary and later materials would never be visible to
    the outline-planning stage. Instead, group by asset (``asset_id``) and
    round-robin across groups, so every bound asset contributes at least
    one representative entry before any asset contributes a second. Within
    each asset's group, prefer higher priority/authority evidence first.
    """
    if max_items <= 0:
        return []
    if len(evidence) <= max_items:
        return list(evidence)

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    asset_order: list[str] = []
    for item in evidence:
        asset_id = str(item.get("asset_id") or item.get("source_id") or "")
        if asset_id not in groups:
            asset_order.append(asset_id)
        groups[asset_id].append(item)

    priority_rank = {"core": 2, "supporting": 1}
    authority_rank = {"primary": 2, "secondary": 1, "context_only": 0}

    def sort_key(entry: dict[str, Any]) -> tuple[int, int]:
        return (
            -priority_rank.get(str(entry.get("priority")), 0),
            -authority_rank.get(str(entry.get("authority")), 0),
        )

    for asset_id in asset_order:
        groups[asset_id].sort(key=sort_key)

    selected: list[dict[str, Any]] = []
    cursors = {asset_id: 0 for asset_id in asset_order}
    while len(selected) < max_items:
        progressed = False
        for asset_id in asset_order:
            if len(selected) >= max_items:
                break
            cursor = cursors[asset_id]
            bucket = groups[asset_id]
            if cursor < len(bucket):
                selected.append(bucket[cursor])
                cursors[asset_id] = cursor + 1
                progressed = True
        if not progressed:
            break
    return selected


def attach_evidence_to_plan(
    plan: dict[str, Any],
    *,
    evidence: list[dict[str, Any]],
    bindings: list[dict[str, Any]],
    strategy: str = "material_first",
) -> tuple[dict[str, Any], dict[str, Any]]:
    binding_map = {str(item.get("asset_id")): item for item in bindings}
    factual = [item for item in evidence if item.get("factual_allowed")]
    style_assets = [
        asset_id for asset_id, binding in binding_map.items()
        if binding.get("purpose") == "style_reference" or binding.get("usage_policy") == "style_only"
    ]
    sections: list[dict[str, Any]] = [
        section
        for chapter in plan.get("chapters") or []
        for section in chapter.get("sections") or []
    ]
    assigned_by_asset: dict[str, list[str]] = defaultdict(list)
    node_contracts: dict[str, NodeGroundingContract] = {}

    for section_index, section in enumerate(sections, start=1):
        node_id = str(section.get("node_id") or f"L2-auto-{section_index}")
        query = " ".join([
            str(section.get("title") or ""),
            str(section.get("learning_objective") or ""),
            " ".join(str(item) for item in section.get("key_points") or []),
            " ".join(str(item) for item in section.get("assessment") or []),
        ])
        ranked = sorted(
            ((item, _relevance(query, item)) for item in factual),
            key=lambda pair: pair[1],
            reverse=True,
        )
        selected = [item for item, score in ranked if score > 0][:4]
        required = [
            item["evidence_id"]
            for item in selected
            if (binding_map.get(str(item.get("asset_id"))) or {}).get("usage_policy") == "must_use"
        ]
        optional = [item["evidence_id"] for item in selected if item["evidence_id"] not in required]
        # 跨语种兜底：中文小节配英文资料（或反之）时词面重合恒为 0，
        # 逐节证据契约会整体落空。仅在"确实是语种不同"时补一小批 optional，
        # 绝不进 required —— required 是质量门（未被引用即判 major），
        # 误入会造成假失败；optional 只是"允许引用"，不引用无代价。
        if not selected:
            fallback = _cross_language_fallback(query, factual)
            optional = [item["evidence_id"] for item in fallback]
        questions = [
            item["evidence_id"] for item in selected if item.get("purpose") == "question_source" or item.get("kind") == "question"
        ]
        contract = NodeGroundingContract(
            required_evidence_ids=required,
            optional_evidence_ids=optional,
            question_evidence_ids=questions,
            style_asset_ids=style_assets,
            allow_general_knowledge=strategy != "strict_grounded",
        )
        section["grounding_contract"] = contract.model_dump(mode="json")
        section["evidence_refs"] = required + optional
        section.pop("material_refs", None)
        node_contracts[node_id] = contract
        for item in selected:
            assigned_by_asset[str(item.get("asset_id"))].append(node_id)

    _ensure_must_use_assignment(sections, factual, binding_map, assigned_by_asset, node_contracts)
    conflicts = _detect_conflicts(factual)
    gaps: list[CoverageGap] = []
    if sections and not factual:
        for section in sections:
            objective = str(section.get("learning_objective") or section.get("title") or "课程目标")
            gaps.append(CoverageGap(
                gap_id=f"gap-{uuid.uuid4().hex[:12]}",
                objective=objective,
                reason="没有可用资料证据",
                strategy="blocked" if strategy == "strict_grounded" else "general_knowledge",
            ))

    asset_coverage: list[dict[str, Any]] = []
    for asset_id, binding in binding_map.items():
        asset_evidence = [item for item in evidence if item.get("asset_id") == asset_id]
        nodes = sorted(set(assigned_by_asset.get(asset_id, [])))
        asset_coverage.append({
            "asset_id": asset_id,
            "purpose": binding.get("purpose"),
            "usage_policy": binding.get("usage_policy"),
            "evidence_count": len(asset_evidence),
            "assigned_nodes": nodes,
            "coverage_level": "planned" if nodes else ("unparsed" if not asset_evidence else "unused"),
        })

    coverage = EvidenceCoveragePlan(
        strategy=strategy if strategy in {"strict_grounded", "material_first", "general_assisted"} else "material_first",
        evidence_count=len(evidence),
        asset_coverage=asset_coverage,
        conflicts=conflicts,
        gaps=gaps,
        node_contracts=node_contracts,
    )
    return plan, coverage.model_dump(mode="json")


def extract_grounding_annotations(
    content: str,
    allowed_ids: set[str],
) -> tuple[str, list[dict[str, Any]], list[str]]:
    pattern = re.compile(r"\[\[evidence:(ev-[a-zA-Z0-9-]+)\]\]")
    annotations: list[dict[str, Any]] = []
    invalid: list[str] = []
    for match in pattern.finditer(content):
        evidence_id = match.group(1)
        if evidence_id not in allowed_ids:
            invalid.append(evidence_id)
            continue
        annotations.append({
            "evidence_id": evidence_id,
            "marker_start": match.start(),
            "marker_end": match.end(),
        })
    visible = pattern.sub("", content)
    visible = re.sub(r"[ \t]+\n", "\n", visible)
    return visible, annotations, sorted(set(invalid))


def evidence_bundle_for_node(course_data: dict[str, Any], node: dict[str, Any]) -> list[dict[str, Any]]:
    contract = node.get("grounding_contract") or {}
    ids = set(contract.get("required_evidence_ids") or []) | set(contract.get("optional_evidence_ids") or [])
    catalog = course_data.get("evidence_catalog") or []
    return [item for item in catalog if item.get("evidence_id") in ids]


def _ensure_must_use_assignment(
    sections: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    binding_map: dict[str, dict[str, Any]],
    assigned_by_asset: dict[str, list[str]],
    node_contracts: dict[str, NodeGroundingContract],
) -> None:
    if not sections:
        return
    for asset_id, binding in binding_map.items():
        if binding.get("usage_policy") != "must_use" or assigned_by_asset.get(asset_id):
            continue
        candidates = [item for item in evidence if item.get("asset_id") == asset_id]
        if not candidates:
            continue
        best_section = max(
            sections,
            key=lambda section: max(
                (_relevance(str(section.get("title") or ""), item) for item in candidates),
                default=0,
            ),
        )
        node_id = str(best_section.get("node_id") or "")
        evidence_id = candidates[0]["evidence_id"]
        contract_data = best_section.get("grounding_contract") or {}
        required = list(contract_data.get("required_evidence_ids") or [])
        if evidence_id not in required:
            required.append(evidence_id)
        contract_data["required_evidence_ids"] = required
        best_section["grounding_contract"] = contract_data
        best_section["evidence_refs"] = list(dict.fromkeys(required + list(contract_data.get("optional_evidence_ids") or [])))
        if node_id and node_id in node_contracts:
            node_contracts[node_id] = NodeGroundingContract.model_validate(contract_data)
        assigned_by_asset[asset_id].append(node_id)


def _detect_conflicts(evidence: list[dict[str, Any]]) -> list[EvidenceConflict]:
    definitions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in evidence:
        if item.get("kind") != "definition":
            continue
        text = str(item.get("source_text") or "")
        match = re.match(r"\s*([^：:。]{2,24})[：:]", text)
        if match:
            definitions[match.group(1).strip()].append(item)
    conflicts: list[EvidenceConflict] = []
    authority_rank = {"primary": 3, "secondary": 2, "context_only": 1}
    for topic, items in definitions.items():
        unique = {re.sub(r"\s+", "", str(item.get("source_text") or "")) for item in items}
        if len(items) < 2 or len(unique) < 2:
            continue
        ranked = sorted(items, key=lambda item: authority_rank.get(str(item.get("authority")), 0), reverse=True)
        selected = ranked[0] if authority_rank.get(str(ranked[0].get("authority")), 0) > authority_rank.get(str(ranked[1].get("authority")), 0) else None
        conflicts.append(EvidenceConflict(
            conflict_id=f"conflict-{uuid.uuid4().hex[:12]}",
            topic=topic,
            evidence_ids=[str(item.get("evidence_id")) for item in items],
            resolution="authority_selected" if selected else "preserve_multiple",
            selected_evidence_id=str(selected.get("evidence_id")) if selected else None,
            message=(
                f"「{topic}」存在不同表述，已按权威等级选择主证据。"
                if selected else f"「{topic}」存在无法自动消解的不同表述。"
            ),
        ))
    return conflicts


def _relevance(query: str, item: dict[str, Any]) -> float:
    query_terms = set(_keywords(query))
    evidence_terms = set(str(value).lower() for value in item.get("keywords") or [])
    if not query_terms or not evidence_terms:
        return 0.0
    overlap = len(query_terms & evidence_terms)
    if overlap == 0:
        return 0.0
    score = overlap / max(1, len(query_terms))
    if item.get("priority") == "core":
        score += 0.15
    if item.get("authority") == "primary":
        score += 0.1
    if item.get("purpose") == "question_source" and any(marker in query for marker in ("练习", "题", "应用", "验收")):
        score += 0.2
    return score


# 跨语种兜底每节最多补的证据条数。刻意压得很小：这批证据无法用词面证明
# 与本节相关，只是"允许引用"，多了会稀释真正相关的证据。
CROSS_LANGUAGE_FALLBACK_LIMIT = 2


# 联网资料落地时会加中文出处头（来源 URL / 抓取时间 / 可信度等）。
# 那是元数据不是课程内容，却会被 _keywords 抽成中文词，
# 让"英文资料"看起来像"中英混排"，进而误判为同语种。
# 判断语种时剔除这些固定词面，元数据本身仍完整保留在
# binding.source_metadata 与 Markdown 正文里，可追溯性不受影响。
_PROVENANCE_MARKERS = (
    "本文为联网检索得到的外部参考资料摘录",
    "非平台原创内容",
    "来源", "域名", "抓取时间", "可信度标记", "检索来源标识",
    "发布时间", "许可信息", "复用策略", "摘录正文", "未知", "未标注",
)


def _strip_provenance(text: str) -> str:
    for marker in _PROVENANCE_MARKERS:
        text = text.replace(marker, " ")
    return text


def _script_profile(text: str) -> set[str]:
    """粗判文本用的书写系统，用于识别"语种不同"而非"内容无关"。"""
    profile: set[str] = set()
    if re.search(r"[\u4e00-\u9fff]", text):
        profile.add("cjk")
    if re.search(r"[A-Za-z]", text):
        profile.add("latin")
    return profile


def _cross_language_fallback(
    query: str,
    evidence: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """词面匹配为空时，仅在跨语种场景下补少量可引用证据。

    为什么这不会引入误绑定：

    1. **只在语种确实不同时触发**。同语种下"没有词面重合"是可信的
       "不相关"信号，此时仍然一条都不补。只有小节文本与证据关键词
       分属不同书写系统（无法用词面判断相关性）时才兜底。
    2. **只进 optional，永不进 required**。required 是质量门——被列为
       必用却未被正文引用会判 major 问题；optional 只扩大"允许引用"集合，
       不引用没有任何代价，因此不会制造假失败，也不会逼模型硬凑引用。
    3. **有上限**（每节 2 条），不会淹没真正相关的证据。
    4. **范围本就属于本课程**：evidence 来自本课程 course_id 下的资料绑定，
       不是全库检索，所以补进来的至少是"为这门课取回的资料"。
    5. 联网资料本身还带 authority=secondary/context_only 与
       reuse_policy=reference_only，即使被引用也标注为参考而非权威。
    """
    # 判据必须与 _relevance 实际比对的 token 一致：它只比 keywords，
    # 不比 summary。落地的联网资料带中文出处头，summary 里混着中文，
    # 若按 summary 判断会误认为"同语种"而不兜底。
    query_scripts = _script_profile(" ".join(_keywords(query)))
    if not query_scripts:
        return []
    # 小节的主体语种：有中文即以中文为主体（中文小节夹带公式/编号很常见）。
    primary_script = "cjk" if "cjk" in query_scripts else "latin"
    candidates: list[tuple[float, int, dict[str, Any]]] = []
    for index, item in enumerate(evidence):
        # 从原文（而非已切好的 n-gram 关键词）剥离出处头再判语种：
        # keywords 里中文已被切成"本文/文为/为联"这类碎片，字符串替换去不掉。
        item_scripts = _script_profile(_strip_provenance(
            str(item.get("source_text") or item.get("summary") or "")
        ))
        if not item_scripts:
            continue
        # 判据：证据里是否含"小节主体语种"的内容。
        # 不能用"两边脚本有交集就算同语种"——中文小节常夹带公式与编号
        # （如 2x2、det(A)），会带上 latin，与纯英文证据被误判为同语种。
        # 只有证据中**存在小节主体语种的内容**时，词面零重合才是可信的
        # "不相关"信号；证据完全不含该语种时，词面无从比对，才兜底。
        if primary_script in item_scripts:
            continue
        priority = {"core": 0, "supporting": 1}.get(str(item.get("priority") or ""), 2)
        authority = {"primary": 0, "secondary": 1}.get(str(item.get("authority") or ""), 2)
        # 排序稳定且与语言无关：优先级 -> 权威度 -> 原始顺序。
        candidates.append((priority + authority / 10, index, item))
    candidates.sort(key=lambda triple: (triple[0], triple[1]))
    return [item for _, _, item in candidates[:CROSS_LANGUAGE_FALLBACK_LIMIT]]


def _evidence_kind(text: str, block_kind: str) -> str:
    if block_kind == "question" or text.rstrip().endswith(("?", "？")):
        return "question"
    if block_kind == "formula":
        return "formula"
    if block_kind == "table":
        return "table"
    if re.search(r"(^|\n)(定义|概念|术语)[：:]|是指|定义为", text):
        return "definition"
    if re.search(r"(^|\n)(步骤|流程|方法|做法)[：:]|第一步|首先", text):
        return "procedure"
    if re.search(r"(^|\n)(例题|示例|案例)[：:]", text):
        return "example"
    return "claim"


def _split_source(text: str, limit: int = 1200) -> list[str]:
    value = text.strip()
    if len(value) <= limit:
        return [value] if value else []
    sentences = re.split(r"(?<=[。！？!?])\s*|\n{2,}", value)
    parts: list[str] = []
    current = ""
    for sentence in sentences:
        if not sentence:
            continue
        if current and len(current) + len(sentence) > limit:
            parts.append(current)
            current = sentence
        else:
            current += sentence
    if current:
        parts.append(current)
    return parts


def _keywords(text: str) -> list[str]:
    english = re.findall(r"[A-Za-z][A-Za-z0-9_+-]{1,30}", text.lower())
    chinese_groups = re.findall(r"[\u4e00-\u9fff]{2,20}", text)
    chinese: list[str] = []
    for group in chinese_groups:
        chinese.append(group)
        for width in (2, 3, 4):
            chinese.extend(group[index:index + width] for index in range(max(0, len(group) - width + 1)))
    compact: list[str] = []
    for token in english + chinese:
        if token not in compact:
            compact.append(token)
    return compact[:24]


def _clip(text: str, limit: int) -> str:
    value = re.sub(r"\s+", " ", text).strip()
    return value if len(value) <= limit else value[: limit - 1] + "…"


__all__ = [
    "attach_evidence_to_plan",
    "build_evidence_catalog_summary",
    "build_evidence_units",
    "evidence_bundle_for_node",
    "extract_grounding_annotations",
]
