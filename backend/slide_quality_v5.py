"""Canonical semantic repair and quality gates for universal PPT V5 decks."""

from __future__ import annotations

import re
from copy import deepcopy
from difflib import SequenceMatcher
from typing import Any

SLIDE_DECK_QUALITY_V5_SCHEMA = "slide_deck_quality_v5"

QUALITY_DIMENSION_WEIGHTS = {
    "source_integrity": 25,
    "teaching_closure": 25,
    "pagination_narrative": 15,
    "layout_export": 15,
    "visual_effectiveness": 15,
    "attribution_accessibility": 5,
}

_SPARSE_EXEMPT_LAYOUTS = {
    "cover",
    "roadmap",
    "chapter",
    "chapter-entry",
    "cover-minimal",
    "cover-editorial",
    "agenda-linear",
    "formula-explanation",
    "figure-text",
    "diagram-full",
    "question-prompt",
    "classification-3",
    "chapter-recap",
    "course-synthesis",
}
_SPARSE_EXEMPT_SCENES = {"chapter_entry", "transition"}
_INTERNAL_LABEL_RE = re.compile(
    r"(?:知识规范名称|知识规范\s*[:：]|source[_ ]?fragment[_ ]?id|answer[_ ]?summary|"
    r"continuation_of|internal[_ ]?label|raw[_ ]?source)",
    re.IGNORECASE,
)
_INTERNAL_PREFIX_RE = re.compile(
    r"(?m)(^|\n)\s*(?:(?:本节|本页)(?:核心)?\s*)?"
    r"知识规范(?:名称)?(?:为)?\s*[:：]\s*",
    re.IGNORECASE,
)
_DANGLING_END_RE = re.compile(r"(?:[：:，,、；;]|(?:以及|并且|包括|如下))\s*$")
_QUESTION_MARK_RE = re.compile(r"[?？]")
_CLOSED_QUESTION_HINT_RE = re.compile(r"(?:选择|判断|哪一|哪个|是否|正确|错误|计算|求出)")
_CONCLUSION_HINT_RE = re.compile(
    r"(?:参考结论|推导依据|判定依据|分析结论|结论|结果|产出|输出|最终|"
    r"因此|由此|所以|才能(?:判定|判断|得到|形成))"
)


def _clean_text(value: object) -> str:
    return " ".join(str(value or "").split())


def _normalize_visible(value: object) -> str:
    return re.sub(r"[^0-9a-zA-Z\u3400-\u9fff]+", "", _clean_text(value)).lower()


def _block_text(block: dict[str, Any]) -> str:
    return " ".join(
        part
        for part in [
            _clean_text(block.get("title")),
            _clean_text(block.get("content")),
            *[_clean_text(item) for item in block.get("items") or []],
        ]
        if part
    )


def visible_slide_text(slide: dict[str, Any], *, include_title: bool = False) -> str:
    parts = []
    if include_title:
        parts.extend([
            _clean_text(slide.get("eyebrow")),
            _clean_text(slide.get("title")),
            _clean_text(slide.get("subtitle")),
        ])
    parts.extend([
        _clean_text(slide.get("key_message")),
        *[_block_text(block) for block in slide.get("blocks") or []],
    ])
    return " ".join(part for part in parts if part)


def _issue(
    code: str,
    page_id: str,
    *,
    severity: str = "critical",
    dimension: str = "teaching_closure",
    message: str = "",
    **details: Any,
) -> dict[str, Any]:
    return {
        "severity": severity,
        "code": code,
        "page_id": page_id,
        "dimension": dimension,
        "message": message or code.replace("_", " "),
        **details,
    }


def _semantic_atom_ids(slide: dict[str, Any]) -> set[str]:
    ids = {
        _clean_text((block.get("metadata") or {}).get("semantic_atom_id"))
        for block in slide.get("blocks") or []
    }
    explicit = _clean_text((slide.get("quality") or {}).get("semantic_atom_id"))
    if explicit:
        ids.add(explicit)
    ids.update(
        _clean_text(item)
        for item in (slide.get("quality") or {}).get("semantic_atom_ids") or []
        if _clean_text(item)
    )
    return {item for item in ids if item}


def _is_exempt_sparse_page(slide: dict[str, Any]) -> bool:
    quality = slide.get("quality") or {}
    layout = _clean_text(
        quality.get("resolved_layout")
        or quality.get("requested_layout")
        or slide.get("layout")
    )
    source_layout = _clean_text(slide.get("layout"))
    return bool(
        layout in _SPARSE_EXEMPT_LAYOUTS
        or source_layout in _SPARSE_EXEMPT_LAYOUTS
        or _clean_text(slide.get("scene_kind")) in _SPARSE_EXEMPT_SCENES
        or slide.get("visuals")
        or quality.get("sparse_exempt")
        or quality.get("interactive_page")
        or quality.get("formula_primary")
    )


def _question_mode(slide: dict[str, Any], block: dict[str, Any]) -> str:
    metadata = block.get("metadata") or {}
    quality = slide.get("quality") or {}
    explicit = _clean_text(
        metadata.get("question_mode") or quality.get("question_mode")
    )
    if explicit:
        return explicit
    text = _block_text(block)
    if "开放讨论" in text or "开放讨论" in _clean_text(slide.get("key_message")):
        return "open_discussion"
    if block.get("type") == "exercise" and (
        _QUESTION_MARK_RE.search(text) or _CLOSED_QUESTION_HINT_RE.search(text)
    ):
        return "closed"
    return ""


def _answer_blocks(slide: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for block in slide.get("blocks") or []:
        metadata = block.get("metadata") or {}
        title = _clean_text(block.get("title"))
        if metadata.get("answer_for") or title in {"答案", "参考答案", "反馈", "解析"}:
            result.append(block)
    return result


def _longest_duplicate_length(left: str, right: str) -> int:
    if not left or not right:
        return 0
    return SequenceMatcher(None, left, right, autojunk=False).find_longest_match(
        0,
        len(left),
        0,
        len(right),
    ).size


def collect_v5_quality_issues(
    slides: list[dict[str, Any]],
    *,
    render_review: dict[str, Any] | None = None,
    visual_asset_manifest: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Evaluate only the final slide list; no historical scores are consulted."""
    issues: list[dict[str, Any]] = []
    atom_pages: dict[str, list[str]] = {}
    title_pages: dict[str, list[str]] = {}
    deck_answers: dict[str, list[dict[str, Any]]] = {}
    slide_by_id = {
        _clean_text(candidate.get("unit_id")): candidate for candidate in slides
    }
    continuation_children: dict[str, list[dict[str, Any]]] = {}
    for candidate in slides:
        parent = _clean_text((candidate.get("quality") or {}).get("continuation_of"))
        if parent:
            continuation_children.setdefault(parent, []).append(candidate)
    for candidate_slide in slides:
        for answer in _answer_blocks(candidate_slide):
            answer_for = _clean_text((answer.get("metadata") or {}).get("answer_for"))
            if answer_for:
                deck_answers.setdefault(answer_for, []).append(answer)

    for slide in slides:
        page_id = _clean_text(slide.get("unit_id"))
        quality = slide.get("quality") or {}
        blocks = list(slide.get("blocks") or [])
        body = visible_slide_text(slide)
        normalized_body = _normalize_visible(body)
        title = _clean_text(slide.get("title"))
        normalized_title = _normalize_visible(title)

        if not page_id.startswith("slide:v5:"):
            issues.append(_issue(
                "legacy_slide_id",
                page_id,
                dimension="pagination_narrative",
                message="V5 成品包含非 V5 页面 ID。",
            ))
        continuation_of = _clean_text(quality.get("continuation_of"))
        try:
            continuation_index = int(quality.get("continuation_index") or 0)
            continuation_total = int(quality.get("continuation_total") or 0)
        except (TypeError, ValueError):
            continuation_index = 0
            continuation_total = 0
        if continuation_index > 1 and not continuation_of:
            issues.append(_issue(
                "continuation_parent_missing",
                page_id,
                dimension="pagination_narrative",
                message="续页缺少 continuation_of 父页映射。",
            ))
        if continuation_of and (
            continuation_index < 2
            or continuation_total < continuation_index
            or f"{continuation_index}/{continuation_total}" not in title
        ):
            issues.append(_issue(
                "continuation_sequence_missing",
                page_id,
                dimension="pagination_narrative",
                message="续页缺少完整标题或明确序号。",
            ))
        for atom_id in _semantic_atom_ids(slide):
            atom_pages.setdefault(atom_id, []).append(page_id)
        if normalized_title:
            title_pages.setdefault(normalized_title, []).append(page_id)
        if _INTERNAL_LABEL_RE.search(" ".join([title, body])):
            issues.append(_issue(
                "raw_internal_label_visible",
                page_id,
                dimension="source_integrity",
                message="页面暴露了内部生产字段或标签。",
            ))
        if body and _DANGLING_END_RE.search(body):
            issues.append(_issue(
                "dangling_fragment",
                page_id,
                dimension="teaching_closure",
                message="页面以未完成的残句结束。",
            ))
        if not _is_exempt_sparse_page(slide) and len(normalized_body) < 18:
            issues.append(_issue(
                "sparse_non_exempt_page",
                page_id,
                dimension="layout_export",
                message="非豁免页面只有残句或单句，且没有有效视觉支撑。",
            ))

        questions = [block for block in blocks if block.get("type") == "exercise"]
        answers = _answer_blocks(slide)
        mapped_question_answers: list[dict[str, Any]] = []
        for answer in answers:
            if not _normalize_visible(_block_text(answer)) or (
                _normalize_visible(_block_text(answer))
                == _normalize_visible(answer.get("title"))
            ):
                issues.append(_issue(
                    "empty_answer",
                    page_id,
                    message="答案或反馈区域为空。",
                    block_id=_clean_text(answer.get("block_id")),
                ))
        for question in questions:
            if _question_mode(slide, question) != "closed":
                continue
            metadata = question.get("metadata") or {}
            question_id = _clean_text(metadata.get("question_id"))
            mapped = (
                deck_answers.get(question_id, [])
                if question_id
                else answers
            )
            mapped_question_answers.extend(mapped)
            if not mapped:
                issues.append(_issue(
                    "answer_mapping_missing",
                    page_id,
                    message="封闭问题没有一一对应的答案与反馈。",
                ))
            source_answer = _clean_text(metadata.get("source_answer"))
            supported_feedback = any(
                _clean_text((answer.get("metadata") or {}).get("source_fragment_id"))
                or (answer.get("metadata") or {}).get("source_fragment_ids")
                or _clean_text((answer.get("metadata") or {}).get("source_answer"))
                for answer in mapped
            )
            if not source_answer and not supported_feedback:
                issues.append(_issue(
                    "unsupported_closed_question",
                    page_id,
                    dimension="source_integrity",
                    message="封闭问题缺少来源支持的答案或反馈。",
                ))

        scene = _clean_text(slide.get("scene_kind"))
        metadata_values = [block.get("metadata") or {} for block in blocks]
        contract_text = " ".join([
            title,
            body,
            _clean_text(slide.get("takeaway")),
        ])
        if scene == "worked_example":
            continuation_root = _clean_text(quality.get("continuation_of")) or page_id
            family_slides = [
                slide_by_id.get(continuation_root, slide),
                *continuation_children.get(continuation_root, []),
            ]
            family_blocks = [
                block
                for family_slide in family_slides
                for block in family_slide.get("blocks") or []
            ]
            has_conclusion = bool(
                quality.get("worked_example_conclusion")
                or any(meta.get("conclusion") for meta in metadata_values)
                or any(
                    _normalize_visible(_block_text(answer))
                    and (
                        _clean_text((answer.get("metadata") or {}).get("source_fragment_id"))
                        or (answer.get("metadata") or {}).get("source_fragment_ids")
                        or _clean_text((answer.get("metadata") or {}).get("source_answer"))
                    )
                    for answer in mapped_question_answers
                )
                or any(
                    _clean_text(block.get("title")) in {"结论", "结果", "验证"}
                    and _normalize_visible(_block_text(block))
                    != _normalize_visible(block.get("title"))
                    for block in blocks
                )
                or any(
                    _CONCLUSION_HINT_RE.search(_block_text(block))
                    and bool(
                        (block.get("metadata") or {}).get("fragment_ids")
                        or _clean_text(
                            (block.get("metadata") or {}).get("source_fragment_id")
                        )
                    )
                    for block in family_blocks
                )
            )
            if not has_conclusion:
                issues.append(_issue(
                    "worked_example_conclusion_missing",
                    page_id,
                    message="例题没有来源支持的结论。",
                ))
        if scene == "comparison" and not (
            quality.get("comparison_dimension")
            or any(meta.get("comparison_dimension") for meta in metadata_values)
        ):
            issues.append(_issue(
                "comparison_dimension_missing",
                page_id,
                message="比较页没有统一比较维度。",
            ))
        if scene in {"process", "method"} and not (
            quality.get("process_result")
            or any(meta.get("process_result") for meta in metadata_values)
            or any(_clean_text(block.get("title")) in {"结果", "产出", "结论"} for block in blocks)
            or _CONCLUSION_HINT_RE.search(contract_text)
        ):
            issues.append(_issue(
                "process_result_missing",
                page_id,
                message="过程页缺少明确结果。",
            ))
        if quality.get("need_visual") and not slide.get("visuals"):
            issues.append(_issue(
                "required_visual_missing",
                page_id,
                dimension="visual_effectiveness",
                message="页面声明需要视觉，但没有有效视觉。",
            ))
        for visual in slide.get("visuals") or []:
            if visual.get("kind") != "none" and not _clean_text(visual.get("alt_text")):
                issues.append(_issue(
                    "visual_alt_text_missing",
                    page_id,
                    dimension="attribution_accessibility",
                    message="有效视觉缺少替代文本。",
                ))

    for atom_id, pages in atom_pages.items():
        unique_pages = list(dict.fromkeys(pages))
        if len(unique_pages) > 1:
            for page_id in unique_pages:
                issues.append(_issue(
                    "semantic_atom_split",
                    page_id,
                    dimension="pagination_narrative",
                    message="同一个语义原子被拆到多个页面。",
                    semantic_atom_id=atom_id,
                ))
    for pages in title_pages.values():
        if len(pages) > 1:
            for page_id in pages:
                issues.append(_issue(
                    "duplicate_title",
                    page_id,
                    dimension="pagination_narrative",
                    message="标题没有表达本页独立判断。",
                ))
    for left, right in zip(slides, slides[1:]):
        left_text = _normalize_visible(visible_slide_text(left))
        right_text = _normalize_visible(visible_slide_text(right))
        duplicate_length = _longest_duplicate_length(left_text, right_text)
        if duplicate_length > 20:
            issues.append(_issue(
                "duplicate_visible_content",
                _clean_text(right.get("unit_id")),
                dimension="pagination_narrative",
                message="相邻页面出现超过 20 个标准化字符的重复正文。",
                duplicate_character_count=duplicate_length,
                previous_page_id=_clean_text(left.get("unit_id")),
            ))

    for raw in (render_review or {}).get("issues") or []:
        issue = deepcopy(raw)
        issue.setdefault("severity", "critical")
        issue.setdefault("code", "render_audit_failed")
        issue.setdefault("page_id", str(issue.get("page") or "deck"))
        issue["dimension"] = "layout_export"
        issues.append(issue)

    retrieved_hash_pages: dict[str, list[str]] = {}
    slide_by_id = {
        _clean_text(slide.get("unit_id")): slide for slide in slides
    }
    for asset in visual_asset_manifest or []:
        if asset.get("kind") != "retrieved_image":
            continue
        asset_page_id = _clean_text(asset.get("page_id") or "deck")
        digest = _clean_text(asset.get("sha256"))
        if digest:
            retrieved_hash_pages.setdefault(digest, []).append(asset_page_id)
        if not asset.get("source_page_url") or not asset.get("license"):
            issues.append(_issue(
                "image_attribution_missing",
                _clean_text(asset.get("page_id") or "deck"),
                dimension="attribution_accessibility",
                message="外部图片缺少来源页或许可证。",
            ))
        if not asset.get("license_allowed", True):
            issues.append(_issue(
                "image_license_not_allowed",
                _clean_text(asset.get("page_id") or "deck"),
                dimension="attribution_accessibility",
                message="外部图片许可证不在服务器允许范围内。",
            ))
        if not all(
            asset.get(field)
            for field in ("mime_type", "width", "height", "byte_size", "sha256")
        ):
            issues.append(_issue(
                "retrieved_image_validation_missing",
                asset_page_id,
                dimension="visual_effectiveness",
                message="外部图片缺少 MIME、尺寸、大小或哈希验证结果。",
            ))
        slide = slide_by_id.get(asset_page_id)
        if slide is not None and "[Sources]" not in _clean_text(slide.get("speaker_notes")):
            issues.append(_issue(
                "image_source_note_missing",
                asset_page_id,
                dimension="attribution_accessibility",
                message="外部图片没有写入完整 [Sources] 讲者备注。",
            ))
    for digest, pages in retrieved_hash_pages.items():
        if len(pages) > 1:
            for page_id in pages:
                issues.append(_issue(
                    "duplicate_external_image",
                    page_id,
                    dimension="visual_effectiveness",
                    message="同一外部图片被重复用于多个页面。",
                    sha256=digest,
                ))

    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for issue in issues:
        identity = (
            _clean_text(issue.get("code")),
            _clean_text(issue.get("page_id")),
            _clean_text(issue.get("block_id")),
        )
        if identity in seen:
            continue
        seen.add(identity)
        deduped.append(issue)
    return deduped


def _planning_warning(planner: str, fallback_reason: str) -> dict[str, Any] | None:
    if planner == "ai" and not fallback_reason:
        return None
    code = {
        "invalid_or_failed_ai_story_plan": "ai_story_planner_fallback",
        "partial_ai_story_plan": "ai_story_planner_partial_fallback",
    }.get(fallback_reason, "ai_story_planner_unavailable")
    return _issue(
        code,
        "deck",
        severity="warning",
        dimension="source_integrity",
        message="AI 规划不可用或部分失败，已使用同一套确定性 V5 规划器。",
        planner=planner,
        fallback_reason=fallback_reason,
    )


def build_slide_deck_quality_v5(
    slides: list[dict[str, Any]],
    *,
    planner: str = "ai",
    fallback_reason: str = "",
    planning_diagnostics: dict[str, Any] | None = None,
    render_review: dict[str, Any] | None = None,
    visual_asset_manifest: list[dict[str, Any]] | None = None,
    repair_history: list[dict[str, Any]] | None = None,
    image_target: int = 0,
    legacy_quality: dict[str, Any] | None = None,
    extra_issues: list[dict[str, Any]] | None = None,
    coverage_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the only persisted V5 score from final artifacts and hard gates."""
    del legacy_quality
    issues = collect_v5_quality_issues(
        slides,
        render_review=render_review,
        visual_asset_manifest=visual_asset_manifest,
    )
    for raw in extra_issues or []:
        issue = deepcopy(raw)
        issue.setdefault("severity", "critical")
        issue.setdefault("page_id", str(issue.get("target") or "deck"))
        issue.setdefault("dimension", "source_integrity")
        issues.append(issue)
    coverage = coverage_report or {}
    if coverage and float(coverage.get("decision_coverage_ratio") or 0) < 1.0:
        issues.append(_issue(
            "source_accounting_incomplete",
            "deck",
            dimension="source_integrity",
            message="来源片段未全部进入主线、备注、附录或排除清单。",
        ))
    if coverage and coverage.get("hash_integrity_passed") is False:
        issues.append(_issue(
            "source_hash_integrity_failed",
            "deck",
            dimension="source_integrity",
            message="来源片段哈希校验失败。",
        ))
    planning_warning = _planning_warning(planner, fallback_reason)
    if planning_warning:
        issues.append(planning_warning)
    deduped_issues: list[dict[str, Any]] = []
    seen_issues: set[tuple[str, str, str]] = set()
    for issue in issues:
        identity = (
            _clean_text(issue.get("code")),
            _clean_text(issue.get("page_id") or issue.get("slide_id") or issue.get("target")),
            _clean_text(issue.get("block_id") or issue.get("shape_name")),
        )
        if identity in seen_issues:
            continue
        seen_issues.add(identity)
        deduped_issues.append(issue)
    issues = deduped_issues
    blockers = [issue for issue in issues if issue.get("severity") == "critical"]
    warnings = [issue for issue in issues if issue.get("severity") != "critical"]
    dimensions: dict[str, dict[str, Any]] = {}
    for dimension, max_score in QUALITY_DIMENSION_WEIGHTS.items():
        dimension_issues = [issue for issue in issues if issue.get("dimension") == dimension]
        deductions = sum(
            10 if issue.get("severity") == "critical" else 2
            for issue in dimension_issues
        )
        score = max(0, max_score - deductions)
        dimensions[dimension] = {
            "score": score,
            "max_score": max_score,
            "passed": not any(
                issue.get("severity") == "critical" for issue in dimension_issues
            ),
            "issue_count": len(dimension_issues),
        }
    score = sum(item["score"] for item in dimensions.values())
    passed = not blockers and score >= 80
    history = deepcopy(repair_history or [])
    retrieved_count = sum(
        1 for asset in visual_asset_manifest or []
        if asset.get("kind") == "retrieved_image"
    )
    actual_image_count = sum(
        1 for asset in visual_asset_manifest or []
        if asset.get("kind") in {
            "source_image",
            "retrieved_image",
            "generated_illustration",
        }
    )
    image_target_met = image_target <= 0 or actual_image_count >= image_target
    status = "blocked" if not passed else "repaired" if history else "passed"
    return {
        "schema_version": SLIDE_DECK_QUALITY_V5_SCHEMA,
        "status": status,
        "passed": passed,
        "score": score,
        "slide_count": len(slides),
        "dimensions": dimensions,
        "issues": issues,
        "blockers": blockers,
        "warnings": warnings,
        "repair_history": history,
        "metrics": {
            "total_slide_count": len(slides),
            "main_slide_count": sum(
                1 for slide in slides
                if not bool((slide.get("quality") or {}).get("appendix"))
                and slide.get("layout") != "appendix"
            ),
            "appendix_slide_count": sum(
                1 for slide in slides
                if bool((slide.get("quality") or {}).get("appendix"))
                or slide.get("layout") == "appendix"
            ),
            "retrieved_image_count": retrieved_count,
            "actual_image_count": actual_image_count,
            "image_target": image_target,
        },
        "image_target_met": image_target_met,
        "planning": {
            "planner": planner,
            "fallback_reason": fallback_reason,
            "diagnostics": deepcopy(planning_diagnostics or {}),
        },
    }


def _open_discussion_repair(slide: dict[str, Any]) -> bool:
    questions = [
        block for block in slide.get("blocks") or []
        if block.get("type") == "exercise"
    ]
    empty_answers = [
        block for block in _answer_blocks(slide)
        if not _normalize_visible(_block_text(block))
        or _normalize_visible(_block_text(block)) == _normalize_visible(block.get("title"))
    ]
    unsupported = any(
        _question_mode(slide, block) == "closed"
        and not _clean_text((block.get("metadata") or {}).get("source_answer"))
        for block in questions
    )
    if not questions or not (empty_answers or unsupported):
        return False
    source_answer = next(
        (
            _clean_text((question.get("metadata") or {}).get("source_answer"))
            for question in questions
            if _clean_text((question.get("metadata") or {}).get("source_answer"))
        ),
        "",
    )
    if source_answer and empty_answers:
        empty_answers[0]["content"] = source_answer
        empty_answers[0].setdefault("metadata", {})["source_answer"] = source_answer
        return True
    slide["blocks"] = [
        block for block in slide.get("blocks") or [] if block not in empty_answers
    ]
    for question in questions:
        question.setdefault("metadata", {})["question_mode"] = "open_discussion"
    slide["quality"] = {
        **(slide.get("quality") or {}),
        "question_mode": "open_discussion",
    }
    current = _clean_text(slide.get("key_message"))
    if "开放讨论" not in current:
        slide["key_message"] = f"开放讨论：{current or '请依据课程材料说明你的判断。'}"
    return True


def _strip_internal_prefix(value: object) -> str:
    cleaned = _INTERNAL_PREFIX_RE.sub(r"\1", str(value or ""))
    return cleaned.strip()


def _repair_internal_labels(slide: dict[str, Any]) -> bool:
    changed = False
    for field in ("title", "key_message", "takeaway"):
        original = str(slide.get(field) or "")
        updated = _strip_internal_prefix(original)
        if updated != original:
            slide[field] = updated
            changed = True
    for block in slide.get("blocks") or []:
        for field in ("title", "content"):
            original = str(block.get(field) or "")
            updated = _strip_internal_prefix(original)
            if updated != original:
                block[field] = updated
                changed = True
        items = list(block.get("items") or [])
        updated_items = [_strip_internal_prefix(item) for item in items]
        if updated_items != items:
            block["items"] = updated_items
            changed = True
    return changed


def _merge_split_atoms(slides: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    repaired = list(slides)
    history: list[dict[str, Any]] = []
    index = 0
    while index < len(repaired) - 1:
        left = repaired[index]
        right = repaired[index + 1]
        shared = _semantic_atom_ids(left) & _semantic_atom_ids(right)
        same_episode = _clean_text(left.get("episode_id")) == _clean_text(right.get("episode_id"))
        same_chapter = bool(
            _clean_text(left.get("chapter_id"))
            and _clean_text(left.get("chapter_id"))
            == _clean_text(right.get("chapter_id"))
        )
        combined_length = len(_normalize_visible(visible_slide_text(left))) + len(
            _normalize_visible(visible_slide_text(right))
        )
        if shared and (same_episode or same_chapter) and combined_length <= 620:
            existing_ids = {
                _clean_text(block.get("block_id")) for block in left.get("blocks") or []
            }
            left.setdefault("blocks", []).extend(
                deepcopy(block)
                for block in right.get("blocks") or []
                if _clean_text(block.get("block_id")) not in existing_ids
            )
            if not _clean_text(left.get("key_message")):
                left["key_message"] = _clean_text(right.get("key_message"))
            history.append({
                "round": 1,
                "action": "merge_semantic_atom",
                "page_id": _clean_text(right.get("unit_id")),
                "target_page_id": _clean_text(left.get("unit_id")),
                "semantic_atom_ids": sorted(shared),
            })
            repaired.pop(index + 1)
            continue
        index += 1
    return repaired, history


def _merge_sparse_episode_pages(
    slides: list[dict[str, Any]],
    *,
    round_index: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    repaired = list(slides)
    history: list[dict[str, Any]] = []
    index = 1
    while index < len(repaired):
        slide = repaired[index]
        previous = repaired[index - 1]
        body = visible_slide_text(slide)
        sparse = (
            not _is_exempt_sparse_page(slide)
            and len(_normalize_visible(body)) < 18
        )
        dangling = bool(body and _DANGLING_END_RE.search(body))
        same_episode = bool(
            _clean_text(slide.get("episode_id"))
            and _clean_text(slide.get("episode_id"))
            == _clean_text(previous.get("episode_id"))
        )
        same_sparse_context = bool(
            _clean_text(slide.get("chapter_id"))
            and _clean_text(slide.get("chapter_id"))
            == _clean_text(previous.get("chapter_id"))
            and _clean_text(slide.get("scene_kind"))
            and _clean_text(slide.get("scene_kind"))
            == _clean_text(previous.get("scene_kind"))
        )
        combined_length = len(_normalize_visible(visible_slide_text(previous))) + len(
            _normalize_visible(body)
        )
        if not (
            (same_episode or same_sparse_context)
            and (sparse or dangling)
            and combined_length <= 620
        ):
            index += 1
            continue
        existing_ids = {
            _clean_text(block.get("block_id")) for block in previous.get("blocks") or []
        }
        previous.setdefault("blocks", []).extend(
            deepcopy(block)
            for block in slide.get("blocks") or []
            if _clean_text(block.get("block_id")) not in existing_ids
        )
        previous_quality = previous.get("quality") or {}
        slide_quality = slide.get("quality") or {}
        previous["quality"] = {
            **previous_quality,
            "semantic_atom_ids": list(dict.fromkeys([
                *(previous_quality.get("semantic_atom_ids") or []),
                *(slide_quality.get("semantic_atom_ids") or []),
            ])),
            "fragment_ids": list(dict.fromkeys([
                *(previous_quality.get("fragment_ids") or []),
                *(slide_quality.get("fragment_ids") or []),
            ])),
        }
        history.append({
            "round": round_index,
            "action": "merge_sparse_or_dangling_page",
            "page_id": _clean_text(slide.get("unit_id")),
            "target_page_id": _clean_text(previous.get("unit_id")),
        })
        repaired.pop(index)
    return repaired, history


def repair_semantic_slides_v5(
    slides: list[dict[str, Any]],
    *,
    max_rounds: int = 2,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Apply deterministic, page-targeted repairs without adding source facts."""
    repaired = deepcopy(slides)
    history: list[dict[str, Any]] = []
    for round_index in range(1, max(0, min(max_rounds, 2)) + 1):
        changed = False
        repaired, sparse_history = _merge_sparse_episode_pages(
            repaired,
            round_index=round_index,
        )
        if sparse_history:
            history.extend(sparse_history)
            changed = True
        merged, merge_history = _merge_split_atoms(repaired)
        if merge_history:
            repaired = merged
            for item in merge_history:
                item["round"] = round_index
            history.extend(merge_history)
            changed = True
        for slide in repaired:
            page_id = _clean_text(slide.get("unit_id"))
            if _open_discussion_repair(slide):
                history.append({
                    "round": round_index,
                    "action": "bind_answer_or_open_discussion",
                    "page_id": page_id,
                })
                changed = True
            if _repair_internal_labels(slide):
                history.append({
                    "round": round_index,
                    "action": "replace_internal_label",
                    "page_id": page_id,
                })
                changed = True
            key_message = _normalize_visible(slide.get("key_message"))
            block_body = _normalize_visible(" ".join(
                _block_text(block) for block in slide.get("blocks") or []
            ))
            if key_message and key_message in block_body:
                slide["key_message"] = ""
                history.append({
                    "round": round_index,
                    "action": "remove_redundant_key_message",
                    "page_id": page_id,
                })
                changed = True
            quality = slide.get("quality") or {}
            try:
                title_budget = int(quality.get("title_character_budget") or 0)
            except (TypeError, ValueError):
                title_budget = 0
            is_continuation = bool(_clean_text(quality.get("continuation_of")))
            current_title = _clean_text(slide.get("title"))
            current_normalized = _normalize_visible(current_title)
            full_copy_candidates = [
                _clean_text(slide.get("takeaway")),
                _clean_text((slide.get("primary_claim_source") or {}).get("text")),
                *[
                    _clean_text(value)
                    for block in slide.get("blocks") or []
                    for value in [block.get("content"), *(block.get("items") or [])]
                    if _clean_text(value)
                ],
            ]
            source_completion = next(
                (
                    candidate
                    for candidate in full_copy_candidates
                    if current_normalized
                    and len(candidate) > len(current_title)
                    and _normalize_visible(candidate).startswith(current_normalized)
                ),
                "",
            )
            if not is_continuation and title_budget and source_completion:
                completed_title = _concise_existing_title(
                    source_completion,
                    maximum=max(12, title_budget),
                )
                if completed_title and completed_title != current_title:
                    slide["title"] = completed_title
                    current_title = completed_title
                    history.append({
                        "round": round_index,
                        "action": "complete_title_from_existing_copy",
                        "page_id": page_id,
                    })
                    changed = True
            unbalanced = any(
                current_title.count(left) > current_title.count(right)
                for left, right in (("（", "）"), ("(", ")"), ("“", "”"))
            )
            if not is_continuation and unbalanced:
                balanced_title = re.split(
                    r"[（(“]",
                    current_title,
                    maxsplit=1,
                )[0].rstrip()
                balanced_title = _concise_existing_title(
                    balanced_title,
                    maximum=max(12, title_budget or 24),
                )
                if balanced_title and balanced_title != current_title:
                    slide["title"] = balanced_title
                    history.append({
                        "round": round_index,
                        "action": "remove_unbalanced_title_fragment",
                        "page_id": page_id,
                    })
                    changed = True
            if (
                not is_continuation
                and title_budget
                and len(_clean_text(slide.get("title"))) > title_budget
            ):
                concise = _concise_existing_title(
                    str(slide.get("title") or ""),
                    maximum=max(12, title_budget),
                )
                if concise and concise != slide.get("title"):
                    slide["title"] = concise
                    history.append({
                        "round": round_index,
                        "action": "shorten_title_from_existing_copy",
                        "page_id": page_id,
                    })
                    changed = True
            if (
                not _is_exempt_sparse_page(slide)
                and slide.get("scene_kind") not in {"navigation", "chapter"}
                and quality.get("major_region_count", 1)
                > quality.get("occupied_major_region_count", 1)
                and not slide.get("visuals")
            ):
                slide["quality"] = {
                    **quality,
                    "requested_layout": "editorial-body",
                    "resolved_layout": "editorial-body",
                    "major_region_count": 1,
                    "occupied_major_region_count": 1,
                }
                history.append({
                    "round": round_index,
                    "action": "switch_to_single_column",
                    "page_id": page_id,
                })
                changed = True
        seen_titles: dict[str, str] = {}
        for slide in repaired:
            page_id = _clean_text(slide.get("unit_id"))
            normalized_title = _normalize_visible(slide.get("title"))
            if normalized_title and normalized_title in seen_titles:
                candidate = next(
                    (
                        _clean_text(value)
                        for value in [
                            slide.get("takeaway"),
                            slide.get("key_message"),
                            *[_block_text(block) for block in slide.get("blocks") or []],
                        ]
                        if _clean_text(value)
                        and _normalize_visible(value) != normalized_title
                    ),
                    "",
                )
                if candidate:
                    slide["title"] = _concise_existing_title(candidate, maximum=32)
                    history.append({
                        "round": round_index,
                        "action": "derive_independent_title",
                        "page_id": page_id,
                        "duplicate_of": seen_titles[normalized_title],
                    })
                    changed = True
            seen_titles.setdefault(normalized_title, page_id)
        for previous, slide in zip(repaired, repaired[1:]):
            previous_text = _normalize_visible(visible_slide_text(previous))
            current_text = _normalize_visible(visible_slide_text(slide))
            if _longest_duplicate_length(previous_text, current_text) <= 20:
                continue
            if _clean_text(previous.get("scene_kind")) == "chapter_entry":
                previous["key_message"] = ""
                history.append({
                    "round": round_index,
                    "action": "remove_redundant_navigation_copy",
                    "page_id": _clean_text(previous.get("unit_id")),
                    "next_page_id": _clean_text(slide.get("unit_id")),
                })
                changed = True
                continue
            unique_blocks = [
                block
                for block in slide.get("blocks") or []
                if _normalize_visible(_block_text(block))
                and _normalize_visible(_block_text(block)) not in previous_text
            ]
            if len(unique_blocks) == len(slide.get("blocks") or []):
                continue
            slide["blocks"] = unique_blocks
            if _normalize_visible(slide.get("key_message")) in previous_text:
                slide["key_message"] = ""
            history.append({
                "round": round_index,
                "action": "remove_duplicate_visible_content",
                "page_id": _clean_text(slide.get("unit_id")),
                "previous_page_id": _clean_text(previous.get("unit_id")),
            })
            changed = True
        if not changed:
            break
    for position, slide in enumerate(repaired):
        slide["position"] = position
    return repaired, history


def _concise_existing_title(title: str, maximum: int = 24) -> str:
    cleaned = _clean_text(title)
    cleaned = re.sub(
        r"\s*[（(]+\s*续(?:页)?(?:\s*\d+/\d+)?\s*[）)]+\s*$",
        "",
        cleaned,
    )
    cleaned = re.sub(r"\*{1,2}|_{1,2}", "", cleaned)
    cleaned = re.sub(
        r"^(?:本节课的核心目标是|本节(?:的)?核心任务是|"
        r"本节(?:课)?旨在|本节点的学习目标是|本模块围绕知识规范|"
        r"本模块(?:的)?(?:核心任务是|旨在))",
        "",
        cleaned,
    )
    cleaned = re.sub(r"^(?:建立|掌握|理解|达成|聚焦于)\s*", "", cleaned)
    cleaned = re.sub(r"[（(][^）)]{1,96}[）)]", "", cleaned)
    paired_role = re.search(
        r"^(.{2,12}?)作为“[^”]+”与(.{2,12}?)作为“[^”]+”的"
        r"([^，。]{2,12}(?:关系|对应))",
        cleaned,
    )
    if paired_role:
        cleaned = "与".join(paired_role.group(1, 2)) + "的" + paired_role.group(3)
    else:
        quoted_relation = re.search(
            r"“([^”]{2,18})”([^，。]{0,12}(?:关系|逻辑|方法|结构|机制))",
            cleaned,
        )
        if quoted_relation:
            relation = "".join(quoted_relation.groups())
            prefix = cleaned[: quoted_relation.start()].rstrip("的")
            contextual = f"{prefix}的{relation}" if prefix else relation
            cleaned = contextual if len(contextual) <= maximum else relation
    cleaned = cleaned.replace("“", "").replace("”", "").replace("‘", "").replace("’", "")
    cleaned = _clean_text(cleaned).rstrip("，。；：,;:")
    if len(cleaned) <= maximum:
        return cleaned
    for marker in ("。", "；", "，", ";", ",", "：", ":"):
        index = cleaned.find(marker, 8, maximum + 1)
        if index >= 0:
            return cleaned[:index].strip()
    concise = cleaned[:maximum].rstrip("，。；：,;:以及和与并的（(")
    if concise and concise[-1].isascii() and concise[-1].isalnum():
        concise = re.sub(r"[A-Za-z0-9]+$", "", concise).rstrip()
    return concise or cleaned[:maximum]


def repair_render_slides_v5(
    slides: list[dict[str, Any]],
    render_review: dict[str, Any],
    *,
    round_index: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Repair only pages named by the exported-object audit."""
    repaired = deepcopy(slides)
    issues_by_page: dict[int, set[str]] = {}
    for issue in render_review.get("issues") or []:
        if issue.get("severity") != "critical":
            continue
        try:
            page = int(issue.get("page") or 0)
        except (TypeError, ValueError):
            continue
        if page > 0:
            issues_by_page.setdefault(page, set()).add(str(issue.get("code") or ""))
    history: list[dict[str, Any]] = []
    for page, codes in issues_by_page.items():
        if page > len(repaired):
            continue
        slide = repaired[page - 1]
        actions: list[str] = []
        blocks: list[dict[str, Any]] = []
        seen_text: set[str] = set()
        for block in slide.get("blocks") or []:
            normalized = _normalize_visible(_block_text(block))
            if normalized and normalized in seen_text:
                actions.append("remove_duplicate_text")
                continue
            if normalized:
                seen_text.add(normalized)
            blocks.append(block)
        slide["blocks"] = blocks
        if "exported_title_unexpected_wrap" in codes:
            quality = slide.get("quality") or {}
            try:
                title_budget = int(quality.get("title_character_budget") or 20)
            except (TypeError, ValueError):
                title_budget = 20
            concise = _concise_existing_title(
                str(slide.get("title") or ""),
                maximum=max(12, min(20, title_budget)),
            )
            if concise and concise != slide.get("title"):
                slide["title"] = concise
                actions.append("shorten_title_from_existing_copy")
        if codes & {
            "exported_text_frame_overflow",
            "exported_body_font_below_16pt",
            "exported_ocr_text_missing_or_clipped",
            "exported_object_out_of_bounds",
            "exported_text_overlap",
            "exported_footer_overlap",
        }:
            quality = slide.get("quality") or {}
            slide["quality"] = {
                **quality,
                "requested_layout": "editorial-body",
                "resolved_layout": "editorial-body",
                "major_region_count": 1,
                "occupied_major_region_count": 1,
            }
            slide["composition"] = "statement"
            actions.append("switch_layout")
        if actions:
            history.append({
                "round": max(1, min(2, round_index)),
                "action": "render_repair",
                "actions": list(dict.fromkeys(actions)),
                "page_id": _clean_text(slide.get("unit_id")),
                "issue_codes": sorted(codes),
            })
    return repaired, history
