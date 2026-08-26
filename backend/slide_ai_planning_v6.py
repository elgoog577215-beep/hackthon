"""Strict AI story and visual planning for slide-deck V6.

Story planning has no deterministic publication fallback. Visual planning may
degrade only pages that do not carry a required characteristic artifact.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import re
import time
from collections import Counter, defaultdict
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ai_base import (
    AIBase,
    AIProviderRequestError,
    AIProviderUnavailable,
    AIRequestBudgetExceeded,
)
from course_document import stable_hash
from course_presentation_graph import (
    CoursePresentationGraphV1,
    CoursePresentationUnitV1,
    page_artifact_kinds,
    page_teaching_intent,
    teaching_intent_for_roles,
)
from slide_deck_v6 import (
    AIBatchDiagnosticV1,
    AIProviderAttemptDiagnosticV1,
    SlideStoryBatchV3,
    SlideStoryPageV3,
    SlideStoryPlanV3,
    SlideVisualDecisionV2,
    SlideVisualPlanV2,
    V6BuildError,
    _complete_sentence_excerpt,
    _complete_story_source_companion,
    _layout_semantic_fallback_cost,
    _looks_like_markdown_table,
    _presentation_summary_text,
    _protected_tokens,
    _semantic_grounding_ratio,
    _title_is_incomplete,
    _title_protected_tokens,
    _title_semantic_source_text,
    _visible_prose_text,
    graph_page_source_blocks,
    source_required_slot_kinds,
    story_page_count_range,
    story_safe_page_slices,
    story_safe_partition_options,
    validate_layout_source_satisfiability,
    validate_slide_story_plan_v3,
    validate_slide_visual_plan_v2,
    validate_story_template_text_slots,
)
from generation_telemetry import stage as generation_stage
from template_layout_contract import TemplateLayoutPackContractV1

Planner = Callable[[dict[str, Any]], Awaitable[dict[str, Any]] | dict[str, Any]]
BatchLifecycleCallback = Callable[[dict[str, Any]], Awaitable[None] | None]
_MARKDOWN_TITLE_RE = re.compile(
    r"\*\*([^*\n]{4,72})\*\*|^#{1,6}\s+([^\n]{4,72})",
    re.MULTILINE,
)
_STORY_PAGE_CONTRACT_FIELDS = frozenset({
    "page_id",
    "teaching_unit_id",
    "template_layout_id",
    "title",
    "summary",
    "source_block_ids",
})
_STORY_SEMANTIC_MAX_ATTEMPTS = 3
_STORY_MODEL_REQUEST_CHAR_BUDGET = 20000
_STORY_UNIT_REPARTITION_FAILURE_CODES = frozenset({
    "story_course_block_coverage_incomplete",
    "story_duplicate_primary_block",
    "template_layout_artifact_mismatch",
    "template_layout_intent_mismatch",
    "template_layout_semantic_slot_mismatch",
    "template_required_slot_unfilled",
    "template_source_semantic_fidelity_incomplete",
    "template_source_slot_role_mismatch",
    "template_slot_capacity_exceeded",
    "template_slot_underfilled",
    "template_source_slot_coverage_incomplete",
})
_VISUAL_SEMANTIC_MAX_ATTEMPTS = 2
_ELLIPSIS_MARKER_RE = re.compile(r"…|(?<!\.)\.{3}(?!\.)")
_VISUAL_DECISION_CONTRACT_FIELDS = frozenset({
    "page_id",
    "decision",
    "source_block_ids",
    "source_asset_ids",
    "visual_payload",
    "resolved_template_layout_id",
    "provider",
    "model",
    "duration_ms",
    "attempts",
    "degraded",
    "degradation_reason",
})


class AIPlannerInvocationError(RuntimeError):
    """Provider failure with only allow-listed, non-content telemetry attached."""

    def __init__(
        self,
        error: BaseException,
        *,
        telemetry: list[dict[str, Any]] | None = None,
    ) -> None:
        self.original_error = error
        self.telemetry = [
            item.model_dump(mode="json")
            for item in _sanitize_provider_attempts(telemetry or [])
        ]
        super().__init__(str(error) or type(error).__name__)


class _AIPlannerResponse(dict[str, Any]):
    def __init__(
        self,
        value: dict[str, Any],
        *,
        telemetry: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(value)
        self.telemetry = [
            item.model_dump(mode="json")
            for item in _sanitize_provider_attempts(telemetry or [])
        ]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _StoryResponsePage(_StrictModel):
    page_id: str
    teaching_unit_id: str
    template_layout_id: str
    title: str
    summary: str = ""
    source_block_ids: list[str] = Field(min_length=1)


class _StoryBatchResponse(_StrictModel):
    schema_version: str
    chapter_id: str
    provider: str = ""
    model: str = ""
    attempts: int = Field(default=1, ge=1)
    pages: list[_StoryResponsePage] = Field(min_length=1)


class _VisualBatchResponse(_StrictModel):
    schema_version: str
    provider: str = ""
    model: str = ""
    attempts: int = Field(default=1, ge=1)
    decisions: list[SlideVisualDecisionV2] = Field(min_length=1)


_FORBIDDEN_DETERMINISTIC_PLANNER_IDENTITIES = frozenset({
    "teacher-plan-adapter",
    "source-faithful-deterministic",
    "source-native-deterministic",
})
_GENERIC_TEACHING_PAGE_TITLES = frozenset({
    "任务条件",
    "输出要求",
    "参考解法",
    "核对标准",
    "本节任务",
    "核心教学",
    "学习者行动",
    "检查与反馈",
    "直觉入口",
    "多重表征",
    "正式定义",
    "证明与推导",
    "数学论证",
    "例题推演",
    "策略选择",
    "变式练习",
    "在形式化定义之前",
    "从二阶出发",
    "本节要解决的问题是",
    "错误分析",
    "逐行取系数",
    "缺项补0",
    "沿索引读取",
    "核对A、x与b",
})


def _generic_teaching_page_title(value: str) -> bool:
    normalized = re.sub(r"\s+", "", str(value or ""))
    if normalized in {
        re.sub(r"\s+", "", item) for item in _GENERIC_TEACHING_PAGE_TITLES
    }:
        return True
    if re.match(
        r"^(?:再(?:沿|按).{0,12}\d+|继续(?:沿|按).{0,12}\d+|"
        r"[A-Za-z]逐位读取分量)$",
        normalized,
    ):
        return True
    return bool(re.match(
        r"^(?:\u7ed9\u51fa|\u63d0\u4f9b|\u9009\u53d6|\u8f93\u51fa(?:\u987b|\u9700|\u8981\u6c42)?|"
        r"\u63d0\u4ea4|\u6807\u6ce8|\u5199\u51fa|\u9010\u6b65\u5199\u51fa|\u91cd\u70b9\u7a81\u51fa[:\uff1a]?|"
        r"\u5728\u5f62\u5f0f\u5316\u5b9a\u4e49\u4e4b\u524d(?:\u5efa\u7acb)?|\u4e0e\u53d8\u5f0f\u7ec3\u4e60\u5408\u5e76)",
        normalized,
    )) or bool(re.match(r"^\u7528.{2,18}\u5efa\u7acb.{2,24}$", normalized))


def _audience_facing_title_candidate(value: str) -> str:
    """Turn a source-authored production instruction into an on-screen title.

    This only removes or reorders the source phrase; it never adds a teaching
    claim.  The resulting candidate still passes the normal protected-token
    and semantic-grounding gates before it can enter a manuscript.
    """

    source = " ".join(str(value or "").split()).strip("#*` \uff0c\u3002\uff01\uff1f,;:|")
    if not source:
        return ""
    candidate = re.sub(r"^\u91cd\u70b9\u7a81\u51fa\s*[:\uff1a]\s*", "", source).strip()
    candidate = re.sub(
        r"^(?:\u7ed9\u51fa|\u63d0\u4f9b|\u9009\u53d6|\u8f93\u51fa(?:\u987b|\u9700|\u8981\u6c42)?|"
        r"\u63d0\u4ea4|\u6807\u6ce8|\u5199\u51fa|\u9010\u6b65\u5199\u51fa|\u8bb0\u5f55|\u5c55\u793a)\s*[:\uff1a]?\s*",
        "",
        candidate,
    ).strip()
    candidate = re.sub(r"^\u987b\s*", "", candidate).strip()
    candidate = re.sub(
        r"^(?:\u9010\u6b65\u5199\u51fa|\u5199\u51fa|\u6807\u6ce8|\u8bb0\u5f55|\u5c55\u793a|\u63d0\u4ea4)\s*",
        "",
        candidate,
    ).strip()
    candidate = candidate.replace("、对应", "与对应")
    candidate = re.sub(
        r"^\u5728\u5f62\u5f0f\u5316\u5b9a\u4e49\u4e4b\u524d(?:\u5148)?(?:\u5efa\u7acb)?\s*",
        "",
        candidate,
    ).strip()
    candidate = re.sub(
        r"^\u4e0e\u53d8\u5f0f\u7ec3\u4e60\u5408\u5e76\s*[,\uff0c]?\s*(?:\u5b66\u4e60\u8005)?",
        "",
        candidate,
    ).strip()
    geometric = re.fullmatch(r"\u7528(.{2,18})\u5efa\u7acb(.{2,24})", candidate)
    if geometric:
        candidate = f"{geometric.group(2)}\u7684{geometric.group(1)}"
    single_matrix = re.fullmatch(r"\u4e00\u4e2a(.{2,24}\u77e9\u9635)", candidate)
    if single_matrix:
        candidate = f"{single_matrix.group(1)}\u793a\u4f8b"
    if candidate == "\u4e00\u7ec4\u96be\u5ea6\u9012\u8fdb\u7684\u9898\u76ee":
        candidate = "\u96be\u5ea6\u9012\u8fdb\u7ec3\u4e60"
    return candidate if len(candidate) >= 4 and not _title_is_incomplete(candidate) else ""


def _require_ai_planner_provenance(
    *,
    provider: str,
    model: str,
    stage: str,
) -> None:
    """Reject the retired teacher adapter if it is ever wired back in.

    Unit-test fixtures may still use local fake providers, but the known
    deterministic teacher identities can never be published as completed AI
    planning. This protects the single V6 route from regressing into one-page-
    per-block slicing while claiming that story or visual AI ran.
    """

    identities = {
        str(provider or "").strip().casefold(),
        str(model or "").strip().casefold(),
    }
    if identities.intersection(_FORBIDDEN_DETERMINISTIC_PLANNER_IDENTITIES):
        raise V6BuildError(
            stage=stage,
            code=f"{stage}_deterministic_adapter_forbidden",
            message=(
                "The retired deterministic teacher PPT adapter cannot be "
                "reported or published as completed AI planning"
            ),
            retryable=False,
        )


def _normalize_versioned_response(
    raw: dict[str, Any],
    *,
    schema_version: str,
    collection_field: str,
    collection_aliases: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Normalize explicit, lossless provider shapes before strict validation."""

    payload = dict(raw)
    wrapped = payload.get(schema_version)
    if isinstance(wrapped, dict):
        allowed_outer = {
            schema_version,
            "schema_version",
            "provider",
            "model",
            "attempts",
        }
        unknown_outer = set(payload).difference(allowed_outer)
        if unknown_outer:
            raise ValueError(
                "Unexpected fields beside versioned AI response wrapper: "
                + ", ".join(sorted(unknown_outer))
            )
        normalized = dict(wrapped)
        normalized.setdefault("schema_version", schema_version)
        for field in ("provider", "model", "attempts"):
            if field in payload and field not in normalized:
                normalized[field] = payload[field]
        payload = normalized

    for alias in collection_aliases:
        if alias not in payload:
            continue
        alias_value = payload.pop(alias)
        canonical_value = payload.get(collection_field)
        if canonical_value in (None, []):
            payload[collection_field] = alias_value
        elif canonical_value != alias_value:
            raise ValueError(
                f"Conflicting AI response fields: {collection_field} and {alias}"
            )
    return payload


def _request_title_candidates_for_blocks(
    unit: dict[str, Any],
    source_block_ids: list[str],
) -> list[str]:
    block_metadata = {
        str(block.get("block_id") or ""): block
        for block in unit.get("primary_blocks") or []
        if isinstance(block, dict)
    }
    candidates = list(dict.fromkeys(
        _audience_facing_title_candidate(str(candidate)) or str(candidate)
        for block_id in source_block_ids
        for candidate in block_metadata.get(block_id, {}).get(
            "title_candidates",
            [],
        )
        if str(candidate).strip()
        if not _generic_teaching_page_title(str(candidate))
        if not _title_is_incomplete(
            _audience_facing_title_candidate(str(candidate)) or str(candidate)
        )
    ))
    if any(
        str(block_metadata.get(block_id, {}).get("role") or "") == "objective"
        for block_id in source_block_ids
    ):
        section_title = str(unit.get("section_title") or "").strip()
        if section_title:
            candidates.insert(0, section_title)
            candidates = list(dict.fromkeys(candidates))
    return candidates or [
        _audience_facing_title_candidate(str(candidate)) or str(candidate)
        for candidate in unit.get("title_candidates") or []
        if str(candidate).strip()
        if not _generic_teaching_page_title(str(candidate))
        if not _title_is_incomplete(
            _audience_facing_title_candidate(str(candidate)) or str(candidate)
        )
    ]


def _assign_global_story_titles(
    batches: list[SlideStoryBatchV3],
    requests: list[dict[str, Any]],
) -> list[SlideStoryBatchV3]:
    """Choose one distinct, source-grounded title per page across all batches."""

    request_units = {
        str(unit.get("teaching_unit_id") or ""): unit
        for request in requests
        for unit in request.get("teaching_units") or []
        if isinstance(unit, dict) and str(unit.get("teaching_unit_id") or "")
    }
    page_refs = [
        (batch_index, page_index, page)
        for batch_index, batch in enumerate(batches)
        for page_index, page in enumerate(batch.pages)
    ]
    candidate_keys_by_page: list[list[str]] = []
    display_titles_by_page: list[dict[str, str]] = []

    for batch_index, _page_index, page in page_refs:
        unit = request_units.get(page.teaching_unit_id)
        candidates = (
            _request_title_candidates_for_blocks(unit, page.source_block_ids)
            if unit is not None
            else []
        )
        block_metadata = {
            str(block.get("block_id") or ""): block
            for block in (unit or {}).get("primary_blocks") or []
            if isinstance(block, dict)
        }
        page_source_text = "\n".join(
            "\n".join(filter(None, [
                str(block_metadata.get(block_id, {}).get("source_title") or "").strip(),
                str(block_metadata.get(block_id, {}).get("source_text") or "").strip(),
            ]))
            for block_id in page.source_block_ids
            if (
                str(block_metadata.get(block_id, {}).get("source_title") or "").strip()
                or str(block_metadata.get(block_id, {}).get("source_text") or "").strip()
            )
        )
        if any(
            str(block_metadata.get(block_id, {}).get("role") or "") == "objective"
            for block_id in page.source_block_ids
        ):
            page_source_text = "\n".join(filter(None, [
                str(unit.get("section_title") or "").strip(),
                page_source_text,
            ]))
        candidates = [
            candidate
            for candidate in candidates
            if not _generic_teaching_page_title(candidate)
            if not _title_is_incomplete(candidate)
            if not (
                _title_protected_tokens(candidate)
                - _title_protected_tokens(page_source_text)
            )
            and _semantic_grounding_ratio(candidate, page_source_text) >= 0.12
            and _semantic_grounding_ratio(
                candidate,
                _title_semantic_source_text(page_source_text),
            ) >= 0.25
        ]
        display_titles: dict[str, str] = {}
        for candidate in candidates:
            key = re.sub(r"\s+", "", candidate).casefold()
            if key and key not in display_titles:
                display_titles[key] = candidate
        current_key = re.sub(r"\s+", "", page.title).casefold()
        ordered_keys = list(display_titles)
        if current_key in display_titles:
            ordered_keys.remove(current_key)
            ordered_keys.insert(0, current_key)
        if not ordered_keys:
            batch = batches[batch_index]
            raise V6BuildError(
                stage="story",
                code="story_title_assignment_unsatisfiable",
                message=(
                    "Frozen source does not provide a grounded title candidate "
                    "for every planned page"
                ),
                retryable=False,
                chapter_id=batch.chapter_id,
                page_id=page.page_id,
                batch_id=batch.batch_id,
            )
        candidate_keys_by_page.append(ordered_keys)
        display_titles_by_page.append(display_titles)

    title_owner: dict[str, int] = {}

    def assign(page_number: int, visited_titles: set[str]) -> bool:
        for title_key in candidate_keys_by_page[page_number]:
            if title_key in visited_titles:
                continue
            visited_titles.add(title_key)
            previous_owner = title_owner.get(title_key)
            if previous_owner is None or assign(previous_owner, visited_titles):
                title_owner[title_key] = page_number
                return True
        return False

    for page_number, (batch_index, _page_index, page) in enumerate(page_refs):
        if assign(page_number, set()):
            continue
        batch = batches[batch_index]
        raise V6BuildError(
            stage="story",
            code="story_title_assignment_unsatisfiable",
            message=(
                "Frozen source does not provide enough distinct grounded titles "
                "for every planned page"
            ),
            retryable=False,
            chapter_id=batch.chapter_id,
            page_id=page.page_id,
            batch_id=batch.batch_id,
        )

    assigned_key_by_page = {
        page_number: title_key
        for title_key, page_number in title_owner.items()
    }
    pages_by_batch: dict[int, list[SlideStoryPageV3]] = defaultdict(list)
    for page_number, (batch_index, _page_index, page) in enumerate(page_refs):
        title_key = assigned_key_by_page[page_number]
        pages_by_batch[batch_index].append(page.model_copy(update={
            "title": display_titles_by_page[page_number][title_key],
        }))
    return [
        batch.model_copy(update={"pages": pages_by_batch[batch_index]})
        for batch_index, batch in enumerate(batches)
    ]


def _assign_global_story_page_ids(
    batches: list[SlideStoryBatchV3],
) -> list[SlideStoryBatchV3]:
    """Make provider-local page identities unique across story batches."""

    used_page_ids: set[str] = set()
    normalized_batches: list[SlideStoryBatchV3] = []
    global_ordinal = 0
    for batch in batches:
        normalized_pages: list[SlideStoryPageV3] = []
        for page in batch.pages:
            page_id = page.page_id.strip()
            if not page_id or page_id in used_page_ids:
                page_id = stable_hash(
                    {
                        "batch_id": batch.batch_id,
                        "chapter_id": batch.chapter_id,
                        "teaching_unit_id": page.teaching_unit_id,
                        "source_block_ids": page.source_block_ids,
                        "global_ordinal": global_ordinal,
                    },
                    prefix="v6page_",
                )
            used_page_ids.add(page_id)
            normalized_pages.append(page.model_copy(update={"page_id": page_id}))
            global_ordinal += 1
        normalized_batches.append(batch.model_copy(update={"pages": normalized_pages}))
    return normalized_batches


def _required_safe_partition(
    unit: dict[str, Any],
    *,
    observed_page_count: int,
) -> dict[str, Any]:
    options = [
        option
        for option in unit.get("safe_partition_options") or []
        if isinstance(option, dict)
        and isinstance(option.get("pages"), list)
        and option.get("pages")
    ]
    if not options:
        return {}
    classroom_dense_options = [
        option
        for option in options
        if max(
            (
                len(page.get("source_block_ids") or [])
                for page in option.get("pages") or []
                if isinstance(page, dict)
            ),
            default=0,
        ) <= 3
    ]
    candidates = classroom_dense_options or options
    return min(
        enumerate(candidates),
        key=lambda indexed_option: (
            int(indexed_option[1].get("page_count") or 0),
            abs(
                int(indexed_option[1].get("page_count") or 0)
                - observed_page_count
            ),
            indexed_option[0],
        ),
    )[1]


def _project_required_safe_partitions(
    pages: list[Any],
    units: dict[str, dict[str, Any]],
    repair_targets: list[dict[str, Any]],
    *,
    chapter_id: str,
) -> list[Any]:
    """Snap incomplete AI ownership to one frozen, source-safe partition."""

    targets_by_unit = {
        str(target.get("teaching_unit_id") or ""): target
        for target in repair_targets
        if target.get("repartition_required") is True
        and target.get("source_projection_safe") is True
        and isinstance(target.get("required_safe_partition"), dict)
    }
    if not targets_by_unit:
        return pages

    pages_by_unit: dict[str, list[dict[str, Any]]] = defaultdict(list)
    unscoped_pages: list[Any] = []
    for value in pages:
        if not isinstance(value, dict):
            unscoped_pages.append(value)
            continue
        unit_id = str(value.get("teaching_unit_id") or "")
        if unit_id not in units:
            unscoped_pages.append(value)
            continue
        pages_by_unit[unit_id].append(value)

    projected: list[Any] = []
    used_page_ids: set[str] = set()
    for unit_id, unit in units.items():
        target = targets_by_unit.get(unit_id)
        provider_pages = pages_by_unit.get(unit_id, [])
        if target is None:
            projected.extend(provider_pages)
            used_page_ids.update(
                str(page.get("page_id") or "") for page in provider_pages
            )
            continue
        provider_source_order = [
            str(block_id)
            for page in provider_pages
            for block_id in page.get("source_block_ids") or []
        ]
        expected_source_order = [
            str(block_id) for block_id in unit.get("primary_block_ids") or []
        ]
        if any(
            block_id not in set(expected_source_order)
            for block_id in provider_source_order
        ):
            projected.extend(provider_pages)
            continue
        provider_partition = [
            [str(block_id) for block_id in page.get("source_block_ids") or []]
            for page in provider_pages
        ]
        provider_layout_partition = [
            str(page.get("template_layout_id") or "")
            for page in provider_pages
        ]
        provider_partition_is_safe = any(
            provider_partition == [
                [
                    str(block_id)
                    for block_id in page.get("source_block_ids") or []
                ]
                for page in option.get("pages") or []
                if isinstance(page, dict)
            ]
            and all(
                layout_id in [
                    str(candidate)
                    for candidate in page.get("template_layout_ids") or []
                ]
                for layout_id, page in zip(
                    provider_layout_partition,
                    option.get("pages") or [],
                )
            )
            for option in unit.get("safe_partition_options") or []
            if isinstance(option, dict)
        )
        if target.get("classroom_density_required") is True:
            provider_partition_is_safe = bool(
                provider_partition_is_safe
                and max(
                    (len(source_ids) for source_ids in provider_partition),
                    default=0,
                ) <= 3
            )
        if (
            provider_partition_is_safe
            and target.get("force_required_partition") is not True
        ):
            projected.extend(provider_pages)
            continue
        partition = target["required_safe_partition"]
        partition_pages = partition.get("pages") or []
        if not isinstance(partition_pages, list) or not partition_pages:
            projected.extend(provider_pages)
            continue
        for index, required in enumerate(partition_pages):
            if not isinstance(required, dict):
                continue
            provider_page = (
                provider_pages[index]
                if index < len(provider_pages)
                else {}
            )
            source_block_ids = [
                str(block_id)
                for block_id in required.get("source_block_ids") or []
                if str(block_id)
            ]
            allowed_layout_ids = [
                str(layout_id)
                for layout_id in required.get("template_layout_ids") or []
                if str(layout_id)
            ]
            selected_layout_id = str(
                provider_page.get("template_layout_id") or ""
            )
            if selected_layout_id not in allowed_layout_ids:
                selected_layout_id = allowed_layout_ids[0] if allowed_layout_ids else ""
            title_candidates = _request_title_candidates_for_blocks(
                unit,
                source_block_ids,
            )
            selected_title = str(provider_page.get("title") or "").strip()
            if selected_title not in title_candidates and title_candidates:
                selected_title = title_candidates[0]
            selected_page_id = str(provider_page.get("page_id") or "").strip()
            if not selected_page_id or selected_page_id in used_page_ids:
                selected_page_id = stable_hash(
                    {
                        "chapter_id": chapter_id,
                        "teaching_unit_id": unit_id,
                        "partition_id": partition.get("partition_id"),
                        "page_index": index,
                    },
                    prefix="v6repair_",
                )
            used_page_ids.add(selected_page_id)
            provider_source_ids = [
                str(block_id)
                for block_id in provider_page.get("source_block_ids") or []
            ]
            projected.append({
                "page_id": selected_page_id,
                "teaching_unit_id": unit_id,
                "template_layout_id": selected_layout_id,
                "title": selected_title,
                "summary": (
                    ""
                    if target.get("clear_provider_summary") is True
                    else str(provider_page.get("summary") or "")
                    if provider_source_ids == source_block_ids
                    else ""
                ),
                "source_block_ids": source_block_ids,
            })
    projected.extend(unscoped_pages)
    return projected


def _normalize_generated_ellipsis_companions(
    pages: list[Any],
    units: dict[str, dict[str, Any]],
    graph_units: dict[str, CoursePresentationUnitV1],
    template: TemplateLayoutPackContractV1,
) -> list[Any]:
    """Remove only provider-added ellipsis by proving a complete replacement.

    Any ellipsis-bearing companion is projected to the complete bound source
    when that source fits shared template geometry; otherwise it is cleared so
    source-driven pagination renders the full material later. This also keeps a
    real source ellipsis in its original context instead of trusting marker count.
    """

    normalized: list[Any] = []
    for value in pages:
        if not isinstance(value, dict):
            normalized.append(value)
            continue
        page = dict(value)
        summary = str(page.get("summary") or "")
        unit_id = str(page.get("teaching_unit_id") or "")
        unit = units.get(unit_id)
        graph_unit = graph_units.get(unit_id)
        if not summary or unit is None or graph_unit is None:
            normalized.append(page)
            continue
        if _ELLIPSIS_MARKER_RE.search(summary):
            layout = template.get_layout(str(page.get("template_layout_id") or ""))
            page["summary"] = (
                _complete_story_source_companion(
                    graph_unit,
                    [str(value) for value in page.get("source_block_ids") or []],
                    layout,
                )
                if layout is not None
                else ""
            )
        normalized.append(page)
    return normalized


def _normalize_story_batch_response(
    raw: dict[str, Any],
    request: dict[str, Any],
    graph: CoursePresentationGraphV1,
    template: TemplateLayoutPackContractV1,
) -> dict[str, Any]:
    payload = _normalize_versioned_response(
        raw,
        schema_version="slide_story_batch_response_v3",
        collection_field="pages",
        collection_aliases=("slides",),
    )
    units = {
        str(unit.get("teaching_unit_id") or ""): unit
        for unit in request.get("teaching_units") or []
        if isinstance(unit, dict)
    }
    graph_units = {
        unit.teaching_unit_id: unit
        for unit in graph.units
    }
    pages = payload.get("pages")
    if not isinstance(pages, list):
        return payload
    used_titles = {
        re.sub(r"\s+", "", str(title)).casefold()
        for title in request.get("constraints", {}).get("forbidden_titles") or []
        if str(title).strip()
    }
    repair_targets = [
        target
        for target in (request.get("repair_feedback") or {}).get("repair_targets") or []
        if isinstance(target, dict)
    ]
    repair_targets_by_page = {
        str(target.get("page_id") or ""): target
        for target in repair_targets
        if str(target.get("page_id") or "")
    }
    def repair_target_for(page: dict[str, Any]) -> dict[str, Any] | None:
        exact = repair_targets_by_page.get(str(page.get("page_id") or ""))
        if exact is not None:
            return exact
        unit_id = str(page.get("teaching_unit_id") or "")
        source_ids = {
            str(block_id) for block_id in page.get("source_block_ids") or []
        }
        matching = [
            target
            for target in repair_targets
            if str(target.get("teaching_unit_id") or "") == unit_id
            and {
                str(block_id)
                for block_id in target.get("current_source_block_ids") or []
            }
            == source_ids
        ]
        return matching[0] if len(matching) == 1 else None

    def allowed_layout_ids_for_page(
        unit: dict[str, Any],
        page: dict[str, Any],
    ) -> list[str]:
        block_metadata = {
            str(block.get("block_id") or ""): block
            for block in unit.get("primary_blocks") or []
            if isinstance(block, dict)
        }
        source_ids = [
            str(block_id) for block_id in page.get("source_block_ids") or []
        ]
        roles = [
            str(block_metadata.get(block_id, {}).get("role") or "")
            for block_id in source_ids
            if str(block_metadata.get(block_id, {}).get("role") or "")
        ]
        artifacts = {
            str(artifact)
            for block_id in source_ids
            for artifact in block_metadata.get(block_id, {}).get("artifact_kinds") or []
            if str(artifact)
        }
        page_intent = (
            teaching_intent_for_roles(roles, artifacts)
            if roles or artifacts
            else str(unit.get("teaching_intent") or "")
        )
        result: list[str] = []
        for layout in unit.get("allowed_template_layouts") or []:
            if not isinstance(layout, dict):
                continue
            layout_id = str(layout.get("template_layout_id") or "")
            if not layout_id or page_intent not in (layout.get("teaching_intents") or []):
                continue
            if artifacts and not artifacts.issubset(
                set(layout.get("artifact_kinds") or [])
            ):
                continue
            source_decisions = set(_allowed_visual_decisions(
                artifacts,
                list(unit.get("source_asset_ids") or []),
            ))
            if (
                _layout_requires_artifact_decision(layout)
                and not source_decisions.intersection(
                    set(layout.get("artifact_kinds") or [])
                )
            ):
                continue
            if roles and not artifacts:
                remaining_roles = list(roles)
                required_text_slots = [
                    slot
                    for slot in layout.get("slots") or []
                    if isinstance(slot, dict)
                    and bool(slot.get("required"))
                    and slot.get("slot_kind") in {"body", "items", "steps"}
                ]
                satisfiable = True
                for slot in required_text_slots:
                    source_roles = set(slot.get("source_roles") or [])
                    matching_index = next(
                        (
                            index
                            for index, role in enumerate(remaining_roles)
                            if not source_roles or role in source_roles
                        ),
                        None,
                    )
                    if matching_index is None:
                        satisfiable = False
                        break
                    remaining_roles.pop(matching_index)
                if not satisfiable:
                    continue
            graph_unit = graph_units.get(
                str(unit.get("teaching_unit_id") or "")
            )
            layout_contract = template.get_layout(layout_id)
            if graph_unit is None or layout_contract is None:
                continue
            try:
                validate_story_template_text_slots(
                    page_id=str(page.get("page_id") or "story-preflight"),
                    template=template,
                    layout=layout_contract,
                    source_blocks=graph_page_source_blocks(
                        graph_unit,
                        source_ids,
                    ),
                    story_summary=str(page.get("summary") or ""),
                    enforce_min_chars=False,
                )
            except V6BuildError:
                continue
            result.append(layout_id)
        graph_unit = graph_units.get(
            str(unit.get("teaching_unit_id") or "")
        )
        if graph_unit is not None:
            source_blocks = graph_page_source_blocks(
                graph_unit,
                [str(block_id) for block_id in page.get("source_block_ids") or []],
            )
            result.sort(key=lambda layout_id: (
                _layout_semantic_fallback_cost(
                    template.get_layout(layout_id),
                    source_blocks,
                ),
            ))
        return result
    normalized_pages: list[Any] = []
    for ordinal, value in enumerate(pages):
        if not isinstance(value, dict):
            normalized_pages.append(value)
            continue
        page = dict(value)
        content = page.pop("content", None)
        if isinstance(content, dict):
            if not str(page.get("title") or "").strip():
                page["title"] = str(
                    content.get("title") or content.get("eyebrow") or ""
                ).strip()
            if "summary" not in page:
                summary = content.get("summary") or content.get("lead") or ""
                page["summary"] = summary if isinstance(summary, str) else ""
        unit_id = str(page.get("teaching_unit_id") or "")
        unit = units.get(unit_id)
        if unit is not None and not page.get("source_block_ids"):
            page["source_block_ids"] = list(unit.get("primary_block_ids") or [])
        if not str(page.get("page_id") or "").strip():
            page["page_id"] = stable_hash(
                {
                    "chapter_id": request.get("chapter_id"),
                    "ordinal": ordinal,
                    "teaching_unit_id": unit_id,
                    "template_layout_id": page.get("template_layout_id"),
                },
                prefix="v6page_",
            )
        if unit is not None:
            selected_layout_id = str(page.get("template_layout_id") or "")
            page_layout_ids = allowed_layout_ids_for_page(unit, page)
            selected_layout = template.get_layout(selected_layout_id)
            required_text_slots = [
                slot
                for slot in (selected_layout.slots if selected_layout else [])
                if slot.required
                and slot.slot_kind in {"body", "items", "steps"}
            ]
            owns_complete_unit = [
                str(block_id)
                for block_id in page.get("source_block_ids") or []
            ] == [
                str(block_id)
                for block_id in unit.get("primary_block_ids") or []
            ]
            requires_composite_repartition = bool(
                len(required_text_slots) >= 3
                and not owns_complete_unit
            )
            graph_unit = graph_units.get(unit_id)
            source_blocks = (
                graph_page_source_blocks(
                    graph_unit,
                    [
                        str(block_id)
                        for block_id in page.get("source_block_ids") or []
                    ],
                )
                if graph_unit is not None
                else []
            )
            preferred_layout = template.get_layout(
                page_layout_ids[0] if page_layout_ids else ""
            )
            selected_uses_avoidable_body_fallback = bool(
                selected_layout is not None
                and preferred_layout is not None
                and _layout_semantic_fallback_cost(
                    selected_layout,
                    source_blocks,
                )
                > _layout_semantic_fallback_cost(
                    preferred_layout,
                    source_blocks,
                )
            )
            if (
                selected_layout is not None
                and not requires_composite_repartition
                and (
                    selected_layout_id not in page_layout_ids
                    or selected_uses_avoidable_body_fallback
                )
                and page_layout_ids
            ):
                page["template_layout_id"] = page_layout_ids[0]
        repair_target = repair_target_for(page)
        if repair_target is not None:
            required_title = str(repair_target.get("required_title") or "").strip()
            required_layout_id = str(
                repair_target.get("required_template_layout_id") or ""
            ).strip()
            required_summary = str(
                repair_target.get("required_summary") or ""
            ).strip()
            if required_title:
                page["title"] = required_title
            if required_layout_id:
                page["template_layout_id"] = required_layout_id
            if required_summary:
                page["summary"] = required_summary
        page_title_candidates = (
            [
                str(candidate)
                for candidate in _request_title_candidates_for_blocks(
                    unit,
                    [
                        str(block_id)
                        for block_id in page.get("source_block_ids") or []
                    ],
                )
                if not _generic_teaching_page_title(str(candidate))
                and (
                    not int(unit.get("title_max_chars") or 0)
                    or len(str(candidate)) <= int(unit.get("title_max_chars") or 0)
                )
            ]
            if unit is not None
            else []
        )
        if _generic_teaching_page_title(str(page.get("title") or "")):
            specific_title = next(
                (
                    candidate
                    for candidate in page_title_candidates
                    if re.sub(r"\s+", "", candidate).casefold() not in used_titles
                ),
                "",
            )
            if specific_title:
                page["title"] = specific_title
        normalized_title = re.sub(
            r"\s+",
            "",
            str(page.get("title") or ""),
        ).casefold()
        if unit is not None and normalized_title in used_titles:
            replacement = next(
                (
                    candidate
                    for candidate in page_title_candidates
                    if re.sub(r"\s+", "", candidate).casefold() not in used_titles
                ),
                "",
            )
            if replacement:
                page["title"] = replacement
                normalized_title = re.sub(r"\s+", "", replacement).casefold()
        if normalized_title:
            used_titles.add(normalized_title)
        # Providers sometimes over-answer the story request with draft code,
        # annotations, or visual instructions. Those fields are not part of the
        # story contract and must never leak into the compiled deck. Project the
        # response onto the declared contract, then let the strict source/layout
        # validators below decide whether the usable story fields are valid.
        normalized_pages.append({
            field: page[field]
            for field in _STORY_PAGE_CONTRACT_FIELDS
            if field in page
        })
    explicit_repair_units = {
        str(target.get("teaching_unit_id") or "")
        for target in repair_targets
        if str(target.get("teaching_unit_id") or "")
    }
    observed_by_unit: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for page in normalized_pages:
        if not isinstance(page, dict):
            continue
        unit_id = str(page.get("teaching_unit_id") or "")
        if unit_id in units:
            observed_by_unit[unit_id].append(page)
    source_partition_repairs: list[dict[str, Any]] = []
    for unit_id, unit in units.items():
        if unit_id in explicit_repair_units:
            continue
        observed_pages = observed_by_unit.get(unit_id, [])
        observed_source_ids = [
            str(block_id)
            for page in observed_pages
            for block_id in page.get("source_block_ids") or []
        ]
        expected_source_ids = [
            str(block_id) for block_id in unit.get("primary_block_ids") or []
        ]
        source_projection_safe = bool(
            expected_source_ids
            and all(
                block_id in set(expected_source_ids)
                for block_id in observed_source_ids
            )
        )
        classroom_density_required = any(
            len(page.get("source_block_ids") or []) > 3
            for page in observed_pages
        )
        if (
            (
                Counter(observed_source_ids) == Counter(expected_source_ids)
                and not classroom_density_required
            )
            or not source_projection_safe
        ):
            continue
        partition = _required_safe_partition(
            unit,
            observed_page_count=len(observed_pages),
        )
        if partition:
            source_partition_repairs.append({
                "teaching_unit_id": unit_id,
                "repartition_required": True,
                "source_projection_safe": True,
                "classroom_density_required": classroom_density_required,
                "force_required_partition": classroom_density_required,
                "required_safe_partition": partition,
            })
    projected_pages = _project_required_safe_partitions(
        normalized_pages,
        units,
        [*source_partition_repairs, *repair_targets],
        chapter_id=str(request.get("chapter_id") or ""),
    )
    payload["pages"] = _normalize_generated_ellipsis_companions(
        projected_pages,
        units,
        graph_units,
        template,
    )
    return payload


def _normalize_visual_batch_response(
    raw: dict[str, Any],
    request: dict[str, Any],
) -> dict[str, Any]:
    """Project provider output onto source-bound visual decisions."""

    payload = _normalize_versioned_response(
        raw,
        schema_version="slide_visual_batch_response_v2",
        collection_field="decisions",
    )
    pages = {
        str(page.get("page_id") or ""): page
        for page in request.get("pages") or []
        if isinstance(page, dict)
    }
    decisions = payload.get("decisions")
    if not isinstance(decisions, list):
        return payload
    normalized: list[Any] = []
    for value in decisions:
        if not isinstance(value, dict):
            normalized.append(value)
            continue
        decision = dict(value)
        if "decision" not in decision and "decision_type" in decision:
            decision["decision"] = decision.pop("decision_type")
        else:
            decision.pop("decision_type", None)
        page = pages.get(str(decision.get("page_id") or ""))
        if page is not None:
            decision["source_block_ids"] = list(
                page.get("source_block_ids") or []
            )
            decision["resolved_template_layout_id"] = str(
                page.get("template_layout_id") or ""
            )
        normalized.append({
            field: decision[field]
            for field in _VISUAL_DECISION_CONTRACT_FIELDS
            if field in decision
        })
    payload["decisions"] = normalized
    return payload


def _sanitize_provider_attempts(
    telemetry: list[dict[str, Any]],
) -> list[AIProviderAttemptDiagnosticV1]:
    """Keep operational routing data while dropping prompts, keys, and responses."""

    records: list[AIProviderAttemptDiagnosticV1] = []
    for ordinal, raw in enumerate(telemetry, start=1):
        if not isinstance(raw, dict):
            continue
        provider = str(
            raw.get("provider")
            or raw.get("provider_route")
            or "shared-ai-pool"
        )
        model = str(
            raw.get("model")
            or raw.get("model_id")
            or "provider-selected"
        )
        try:
            attempt = max(1, int(raw.get("provider_attempt") or raw.get("attempt") or ordinal))
        except (TypeError, ValueError):
            attempt = ordinal
        try:
            duration_ms = max(0, int(raw.get("duration_ms") or 0))
        except (TypeError, ValueError):
            duration_ms = 0
        try:
            queue_wait_ms = max(0, int(raw.get("queue_wait_ms") or 0))
        except (TypeError, ValueError):
            queue_wait_ms = 0
        try:
            physical_request_count = max(
                0,
                int(raw.get("physical_request_count") or 0),
            )
        except (TypeError, ValueError):
            physical_request_count = 0
        try:
            input_tokens = max(0, int(
                raw.get("input_tokens")
                or raw.get("estimated_input_tokens")
                or 0
            ))
        except (TypeError, ValueError):
            input_tokens = 0
        try:
            output_tokens = max(0, int(
                raw.get("output_tokens")
                or raw.get("estimated_output_tokens")
                or 0
            ))
        except (TypeError, ValueError):
            output_tokens = 0
        tokens_source = str(raw.get("tokens_source") or "unknown")
        if tokens_source not in {"provider", "estimate", "unknown"}:
            tokens_source = "unknown"
        records.append(AIProviderAttemptDiagnosticV1(
            provider=provider,
            model=model,
            attempt=attempt,
            status=str(raw.get("status") or "unknown"),
            duration_ms=duration_ms,
            queue_wait_ms=queue_wait_ms,
            physical_request_count=physical_request_count,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            tokens_source=tokens_source,
            failure_kind=str(raw.get("failure_kind") or ""),
            error_code=str(raw.get("error_code") or ""),
        ))
    return records


def _provider_attempts_from(value: Any) -> list[AIProviderAttemptDiagnosticV1]:
    telemetry = getattr(value, "telemetry", [])
    return _sanitize_provider_attempts(telemetry if isinstance(telemetry, list) else [])


def _batch_diagnostic(
    *,
    kind: str,
    batch_id: str,
    chapter_id: str,
    duration_ms: int,
    validation_status: str,
    failure_category: str = "",
    provider: str = "",
    model: str = "",
    attempts: int = 1,
    attempt_records: list[AIProviderAttemptDiagnosticV1] | None = None,
) -> AIBatchDiagnosticV1:
    records = list(attempt_records or [])
    last = records[-1] if records else None
    actual_attempts = max(1, attempts, len(records))
    token_sources = {
        record.tokens_source
        for record in records
        if record.tokens_source != "unknown"
    }
    return AIBatchDiagnosticV1(
        kind=kind,
        batch_id=batch_id,
        chapter_id=chapter_id,
        provider=provider or (last.provider if last else "shared-ai-pool"),
        model=model or (last.model if last else "provider-selected"),
        duration_ms=max(0, duration_ms),
        attempts=actual_attempts,
        retry_count=max(0, actual_attempts - 1),
        physical_request_count=sum(
            record.physical_request_count for record in records
        ),
        input_tokens=sum(record.input_tokens for record in records),
        output_tokens=sum(record.output_tokens for record in records),
        tokens_source=(
            next(iter(token_sources))
            if len(token_sources) == 1
            else "mixed"
            if token_sources
            else "unknown"
        ),
        validation_status=validation_status,
        failure_category=failure_category,
        attempt_records=records,
    )


def _failure_category(error: BaseException, *, prefix: str) -> tuple[str, bool]:
    original = (
        error.original_error
        if isinstance(error, AIPlannerInvocationError)
        else error
    )
    message = str(original).lower()
    attempt_records = (
        list(error.telemetry)
        if isinstance(error, AIPlannerInvocationError)
        else []
    )
    primary_rate_limited = any(
        "ratelimit" in str(record.get("error_code") or "").casefold()
        and str(record.get("provider") or "").casefold()
        != "modelscope_fallback"
        for record in attempt_records
        if isinstance(record, dict)
    )
    primary_quota_exhausted = any(
        str(record.get("failure_kind") or "").casefold()
        == "quota_exhausted"
        and str(record.get("provider_route") or record.get("provider") or "").casefold()
        != "modelscope_fallback"
        for record in attempt_records
        if isinstance(record, dict)
    )
    if isinstance(original, AIRequestBudgetExceeded):
        return f"{prefix}_request_budget_exceeded", True
    if isinstance(original, (TimeoutError, asyncio.TimeoutError)) or "timeout" in message:
        return f"{prefix}_timeout", True
    if primary_quota_exhausted:
        return f"{prefix}_balance_unavailable", False
    if any(token in message for token in ("401", "403", "authentication", "api key")):
        # A broken last-resort credential must not turn a temporary primary
        # pool rate limit into a permanent, non-retryable story failure. Keep
        # both attempts in diagnostics, but classify the user-facing recovery
        # path by the still-valid primary route.
        if primary_rate_limited:
            return f"{prefix}_rate_limited", True
        return f"{prefix}_authentication", False
    if any(token in message for token in ("balance", "quota", "credit")):
        return f"{prefix}_balance_unavailable", False
    if any(token in message for token in ("429", "rate limit", "too many requests")):
        return f"{prefix}_rate_limited", True
    return f"{prefix}_failed", True


async def _invoke(planner: Planner, request: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
    if inspect.iscoroutinefunction(planner):
        result = planner(request)
    else:
        result = await asyncio.to_thread(planner, request)
    if inspect.isawaitable(result):
        task = asyncio.ensure_future(result)
        done, _pending = await asyncio.wait(
            {task},
            timeout=timeout_seconds,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if task not in done:
            task.cancel()
            # The provider SDK may delay or suppress cancellation while a
            # stream is wedged.  Observe its eventual result without making
            # the durable slide task wait past the V6 batch deadline.
            task.add_done_callback(
                lambda finished: (
                    None
                    if finished.cancelled()
                    else finished.exception()
                )
            )
            raise asyncio.TimeoutError
        result = task.result()
    if not isinstance(result, dict):
        raise TypeError("AI planner response must be a JSON object")
    return result


async def _notify_batch(
    callback: BatchLifecycleCallback | None,
    payload: dict[str, Any],
) -> None:
    if callback is None:
        return
    result = callback(payload)
    if inspect.isawaitable(result):
        await result


def _allowed_layout_ids_for(
    teaching_intent: str,
    required_artifacts: set[str],
    source_asset_ids: list[str],
    template: TemplateLayoutPackContractV1,
    *,
    teaching_unit_id: str,
) -> list[str]:
    result = []
    source_decisions = set(_allowed_visual_decisions(
        required_artifacts,
        source_asset_ids,
    ))
    for layout in template.layouts:
        if teaching_intent not in layout.teaching_intents:
            continue
        if required_artifacts and not required_artifacts.intersection(layout.artifact_kinds):
            continue
        if (
            _layout_requires_artifact_decision(layout)
            and not source_decisions.intersection(set(layout.artifact_kinds))
        ):
            continue
        result.append(layout.template_layout_id)
    if not result:
        raise V6BuildError(
            stage="template",
            code="template_layout_unavailable",
            message=f"No template layout supports teaching unit {teaching_unit_id}",
        )
    return result


def _layout_prompt_contract(
    layout_id: str,
    template: TemplateLayoutPackContractV1,
) -> dict[str, Any]:
    layout = template.get_layout(layout_id)
    if layout is None:  # pragma: no cover - guarded by the closed registry
        raise V6BuildError(
            stage="template",
            code="template_layout_unavailable",
            message=f"Unknown template layout: {layout_id}",
        )
    return {
        "template_layout_id": layout.template_layout_id,
        "layout_slug": layout.layout_slug,
        "teaching_intents": layout.teaching_intents,
        "artifact_kinds": layout.artifact_kinds,
        "slots": [slot.model_dump(mode="json") for slot in layout.slots],
        "safe_continuation_layout_slugs": layout.safe_continuation_layout_slugs,
    }


def _grounded_title_candidates(
    source_text: str,
    *,
    max_chars: int = 72,
) -> list[str]:
    capacity = max(4, max_chars)
    candidates: list[str] = []

    def add_candidate(value: str) -> None:
        source_candidate = " ".join(str(value or "").split()).strip("#*` ，。！？,;:|")
        candidate = _audience_facing_title_candidate(source_candidate) or source_candidate
        if (
            4 <= len(candidate) <= capacity
            and source_candidate in source_text
            and not _title_is_incomplete(candidate)
            and candidate not in candidates
        ):
            candidates.append(candidate)

    def add_complete_fragments(value: str) -> None:
        clean = " ".join(str(value or "").split()).strip("#*` ")
        if not clean:
            return
        if len(clean) <= capacity:
            add_candidate(clean)
            return
        fragments = re.split(
            r"(?:[，。！？；;：:｜|]|\s+[—–-]\s+|与|及|和|"
            r"\s+(?:and|or|versus|vs\.?)\s+)",
            clean,
            flags=re.IGNORECASE,
        )
        for fragment in fragments:
            stripped = fragment.strip()
            if len(stripped) <= capacity:
                add_candidate(stripped)
                continue
            if re.search(r"\s", stripped):
                words: list[str] = []
                for word in stripped.split():
                    candidate = " ".join([*words, word])
                    if len(candidate) > capacity:
                        break
                    words.append(word)
                add_candidate(" ".join(words))

    for match in _MARKDOWN_TITLE_RE.finditer(source_text):
        full_title = str(match.group(1) or match.group(2) or "").strip()
        specific_title = re.split(r"[：:]", full_title, maxsplit=1)[-1].strip()
        add_complete_fragments(specific_title)
    heading_lines = {
        match.group(0).strip()
        for match in _MARKDOWN_TITLE_RE.finditer(source_text)
    }
    for raw_segment in re.split(r"[\n。！？!?；;]", source_text):
        if raw_segment.strip() in heading_lines:
            continue
        add_complete_fragments(raw_segment)
        if len(candidates) >= 6:
            break
    return candidates[:6]


def _story_unit_request(
    unit: CoursePresentationUnitV1,
    template: TemplateLayoutPackContractV1,
) -> dict[str, Any]:
    page_intents = {
        page_teaching_intent(unit, [block_id])
        for block_id in unit.primary_block_ids
    }
    page_intents.add(unit.teaching_intent)
    ordered_page_intents = [
        unit.teaching_intent,
        *sorted(page_intents - {unit.teaching_intent}),
    ]
    allowed_layout_ids_by_page_intent = {
        page_intent: _allowed_layout_ids_for(
            page_intent,
            (
                set(unit.artifact_kinds)
                if page_intent == "artifact_explanation"
                else set()
            ),
            unit.source_asset_refs,
            template,
            teaching_unit_id=unit.teaching_unit_id,
        )
        for page_intent in ordered_page_intents
    }
    allowed_layout_ids = list(dict.fromkeys(
        layout_id
        for page_intent in ordered_page_intents
        for layout_id in allowed_layout_ids_by_page_intent[page_intent]
    ))
    allowed_layouts = [
        _layout_prompt_contract(layout_id, template)
        for layout_id in allowed_layout_ids
    ]
    title_capacities = [
        int(slot.get("max_chars") or 0)
        for layout in allowed_layouts
        for slot in layout["slots"]
        if slot.get("slot_kind") == "title" and int(slot.get("max_chars") or 0) > 0
    ]
    title_max_chars = min(title_capacities) if title_capacities else 72
    summary_max_chars_by_layout_id = {}
    summary_min_chars_by_layout_id = {}
    for layout in allowed_layouts:
        body_slots = [
            slot
            for slot in layout["slots"]
            if slot.get("slot_kind") == "body"
        ]
        summary_max_chars_by_layout_id[layout["template_layout_id"]] = (
            int(body_slots[0].get("max_chars") or 0)
            if len(body_slots) == 1
            else 0
        )
        summary_min_chars_by_layout_id[layout["template_layout_id"]] = (
            int(body_slots[0].get("min_chars") or 0)
            if len(body_slots) == 1
            else 0
        )
    safe_page_slices = story_safe_page_slices(unit, template)
    allowed_page_count_range = story_page_count_range(
        unit,
        template,
        safe_slices=safe_page_slices,
    )
    safe_partition_options = story_safe_partition_options(
        unit,
        template,
        safe_slices=safe_page_slices,
        allowed_page_count_range=allowed_page_count_range,
    )

    def block_compatible_layout_ids(block_id: str) -> list[str]:
        block_intent = page_teaching_intent(unit, [block_id])
        block_artifacts = set(
            unit.primary_block_artifacts.get(block_id, [])
        )
        required_slot_kinds = source_required_slot_kinds(
            graph_page_source_blocks(unit, [block_id])
        )
        candidates = allowed_layout_ids_by_page_intent.get(block_intent, [])
        return [
            layout_id
            for layout_id in candidates
            if (
                (layout := template.get_layout(layout_id)) is not None
                and (
                    not block_artifacts
                    or block_artifacts.issubset(set(layout.artifact_kinds))
                )
                and required_slot_kinds.issubset(
                    {slot.slot_kind for slot in layout.slots}
                )
            )
        ]

    def contextualize_title(candidate: str) -> str:
        subject = re.sub(
            r"^\s*\d+(?:\.\d+)*\s*",
            "",
            str(unit.section_title or ""),
        ).strip()
        if subject and re.fullmatch(r"\d+\s*\u9053\u7ec3\u4e60\u9898", candidate):
            return f"{subject}\u7ec3\u4e60"
        if subject and candidate in {"\u4e00\u7ec4\u96be\u5ea6\u9012\u8fdb\u7684\u9898\u76ee", "\u96be\u5ea6\u9012\u8fdb\u7ec3\u4e60"}:
            return f"{subject}\u8fdb\u9636\u7ec3\u4e60"
        return candidate

    def audience_title(block_id: str) -> str:
        return contextualize_title(_audience_facing_title_candidate(
            unit.primary_block_titles.get(block_id, "")
        ))

    def valid_title_candidates(values: list[str]) -> list[str]:
        return list(dict.fromkeys(
            candidate
            for value in values
            if str(value).strip()
            for candidate in [
                contextualize_title(
                    _audience_facing_title_candidate(str(value)) or str(value).strip()
                )
            ]
            if 4 <= len(candidate) <= title_max_chars
            if not _generic_teaching_page_title(candidate)
            if not _title_is_incomplete(candidate)
        ))

    return {
        "teaching_unit_id": unit.teaching_unit_id,
        "section_title": unit.section_title,
        "source_ordinal": unit.source_ordinal,
        "primary_block_ids": unit.primary_block_ids,
        "primary_blocks": [
            {
                "block_id": block_id,
                "source_title": unit.primary_block_titles.get(block_id, ""),
                "role": unit.primary_block_roles.get(block_id, ""),
                "artifact_kinds": unit.primary_block_artifacts.get(block_id, []),
                "required_slot_kinds": sorted(source_required_slot_kinds(
                    graph_page_source_blocks(unit, [block_id])
                )),
                "page_intent": page_teaching_intent(unit, [block_id]),
                "source_text": unit.primary_block_texts.get(block_id, ""),
                "reference_evidence_ids": unit.primary_block_evidence_refs.get(
                    block_id, []
                ),
                "reference_evidence_summaries": (
                    unit.primary_block_evidence_summaries.get(block_id, [])
                ),
                "presentation_text": unit.primary_block_presentation_texts.get(
                    block_id,
                    unit.primary_block_texts.get(block_id, ""),
                ),
                "allowed_protected_tokens": sorted(_protected_tokens(
                    unit.primary_block_texts.get(block_id, "")
                )),
                "title_candidates": valid_title_candidates([
                    *(
                        [audience_title(block_id)]
                        if audience_title(block_id)
                        and len(audience_title(block_id)) <= title_max_chars
                        else []
                    ),
                    *(
                        [unit.primary_block_titles.get(block_id, "")]
                        if unit.primary_block_titles.get(block_id, "")
                        and len(unit.primary_block_titles.get(block_id, ""))
                        <= title_max_chars
                        else []
                    ),
                    *(
                        [unit.section_title]
                        if unit.section_title
                        and unit.primary_block_roles.get(block_id) == "objective"
                        and len(unit.section_title) <= title_max_chars
                        else []
                    ),
                    *(
                        contextualize_title(candidate)
                        for candidate in _grounded_title_candidates(
                            "\n".join(filter(None, [
                                unit.primary_block_titles.get(block_id, ""),
                                unit.primary_block_presentation_texts.get(
                                    block_id,
                                    unit.primary_block_texts.get(block_id, ""),
                                ),
                            ])),
                            max_chars=title_max_chars,
                        )
                    ),
                ]),
                "compatible_template_layout_ids": (
                    block_compatible_layout_ids(block_id)
                ),
            }
            for block_id in unit.primary_block_ids
        ],
        "teaching_intent": unit.teaching_intent,
        "artifact_kinds": unit.artifact_kinds,
        "source_asset_ids": unit.source_asset_refs,
        "teaching_plan_context": unit.teaching_plan_context,
        "prerequisite_unit_ids": unit.prerequisite_unit_ids,
        "source_text": unit.source_text,
        "presentation_text": unit.presentation_text or unit.source_text,
        "allowed_protected_tokens": sorted(_protected_tokens(unit.source_text)),
        "title_max_chars": title_max_chars,
        "title_policy": (
            "copy_a_complete_specific_candidate_grounded_in_bound_blocks"
        ),
        "title_candidates": valid_title_candidates([
            *(
                [unit.section_title]
                if unit.section_title
                and any(
                    role == "objective"
                    for role in unit.primary_block_roles.values()
                )
                and len(unit.section_title) <= title_max_chars
                else []
            ),
            *_grounded_title_candidates(
                unit.presentation_text or unit.source_text,
                max_chars=title_max_chars,
            ),
        ]),
        "summary_max_chars_by_layout_id": summary_max_chars_by_layout_id,
        "summary_min_chars_by_layout_id": summary_min_chars_by_layout_id,
        "allowed_page_count_range": allowed_page_count_range,
        "safe_page_slices": safe_page_slices,
        "safe_partition_options": safe_partition_options,
        "allowed_template_layout_ids": allowed_layout_ids,
        "allowed_template_layout_ids_by_page_intent": (
            allowed_layout_ids_by_page_intent
        ),
        "allowed_template_layouts": allowed_layouts,
    }


def _story_requests(
    graph: CoursePresentationGraphV1,
    template: TemplateLayoutPackContractV1,
) -> list[dict[str, Any]]:
    by_section: dict[str, list[CoursePresentationUnitV1]] = defaultdict(list)
    section_order: list[str] = []
    for unit in graph.units:
        if unit.section_id not in by_section:
            section_order.append(unit.section_id)
        by_section[unit.section_id].append(unit)
    return [
        {
            "schema_version": "slide_story_batch_request_v3",
            "chapter_id": section_id,
            "source_document_revision": graph.source_document_revision,
            "template_digest": template.template_digest,
            "constraints": {
                "preserve_unit_order": True,
                "cover_every_primary_block": True,
                "primary_block_page_ownership": "exactly_once",
                "allow_multiple_primary_blocks_per_page": True,
                "maximum_primary_blocks_per_page": 3,
                "canvas_expression": "semantic_closure_with_full_source_in_notes",
                "audience": "learners_during_live_teaching",
                "speaker_notes_policy": "complete_teacher_script_notes_only",
                "presentation_text_policy": (
                    "show_only_definition_theorem_formula_derivation_evidence_"
                    "example_task_feedback_boundary_or_recap_signals"
                ),
                "one_page_one_teaching_point": True,
                "summary_policy": (
                    "source_grounded_semantic_closure_for_all_bound_blocks_"
                    "complete_sentence_no_markdown"
                ),
                "page_count_policy": (
                    "use_each_teaching_unit_allowed_page_count_range"
                ),
                "allow_new_facts": False,
                "allow_unknown_ids": False,
                "protected_token_policy": (
                    "copy_identifiers_and_numbers_exactly_from_each_unit_or_"
                    "bound_block_allowed_protected_tokens"
                ),
                "forbidden_titles": [],
            },
            "response_contract": {
                "schema_version": "slide_story_batch_response_v3",
                "required_top_level_fields": [
                    "schema_version",
                    "chapter_id",
                    "pages",
                ],
                "required_page_fields": [
                    "page_id",
                    "teaching_unit_id",
                    "template_layout_id",
                    "title",
                    "source_block_ids",
                ],
                "optional_page_fields": ["summary"],
                "forbidden_page_fields": ["content"],
            },
            "teaching_units": [
                _story_unit_request(unit, template)
                for unit in by_section[section_id]
            ],
        }
        for section_id in section_order
    ]


def _story_model_request(request: dict[str, Any]) -> dict[str, Any]:
    """Project the strict story contract into a smaller model-facing request.

    The full request remains the validator's source of truth.  The model does
    not need a copy of every layout slot contract for every teaching unit, nor
    the unit-level source text that is already present in ``primary_blocks``.
    Removing those duplicates keeps retries and provider failover from
    repeatedly billing tens of thousands of irrelevant input tokens.
    """

    unit_fields = (
        "teaching_unit_id",
        "section_title",
        "source_ordinal",
        "primary_block_ids",
        "primary_blocks",
        "teaching_intent",
        "artifact_kinds",
        "prerequisite_unit_ids",
        "allowed_protected_tokens",
        "title_max_chars",
        "title_candidates",
        "summary_max_chars_by_layout_id",
        "summary_min_chars_by_layout_id",
        "allowed_page_count_range",
        "safe_partition_options",
        "allowed_template_layout_ids",
        "allowed_template_layout_ids_by_page_intent",
    )
    def representative_partition_options(
        unit: dict[str, Any],
    ) -> list[dict[str, Any]]:
        options = [
            option
            for option in unit.get("safe_partition_options") or []
            if isinstance(option, dict)
            and isinstance(option.get("pages"), list)
            and option.get("pages")
        ]
        if not options:
            return []
        # Retain the most compact option plus the first classroom-dense option.
        # Keeping only the two smallest page counts can hide the first
        # partition whose pages each own at most three script blocks, leaving
        # the model no way to obey the live-teaching density contract.
        by_page_count: dict[int, dict[str, Any]] = {}
        for option in options:
            page_count = int(
                option.get("page_count") or len(option.get("pages") or [])
            )
            current = by_page_count.get(page_count)

            def balance_key(value: dict[str, Any]) -> tuple[int, int, str]:
                group_sizes = [
                    len(page.get("source_block_ids") or [])
                    for page in value.get("pages") or []
                    if isinstance(page, dict)
                ]
                return (
                    max(group_sizes, default=0),
                    sum(size * size for size in group_sizes),
                    str(value.get("partition_id") or ""),
                )

            if current is None or balance_key(option) < balance_key(current):
                by_page_count[page_count] = option
        ordered = [
            by_page_count[page_count]
            for page_count in sorted(by_page_count)
        ]
        selected = ordered[:1]
        classroom_dense = next(
            (
                option
                for option in ordered
                if max(
                    (
                        len(page.get("source_block_ids") or [])
                        for page in option.get("pages") or []
                        if isinstance(page, dict)
                    ),
                    default=0,
                ) <= 3
            ),
            None,
        )
        if classroom_dense is not None and classroom_dense not in selected:
            selected.append(classroom_dense)
        elif len(ordered) > 1:
            selected.append(ordered[1])
        return selected

    def partition_layout_ids(options: list[dict[str, Any]]) -> set[str]:
        return {
            str(layout_id)
            for option in options
            for page in option.get("pages") or []
            if isinstance(page, dict)
            for layout_id in page.get("template_layout_ids") or []
            if str(layout_id)
        }

    def compact_candidates(values: Any, *, limit: int = 4) -> list[str]:
        return list(dict.fromkeys(
            str(value).strip()
            for value in values or []
            if str(value).strip()
        ))[:limit]

    def model_primary_blocks(
        unit: dict[str, Any],
        *,
        retained_layout_ids: set[str],
        source_char_limit: int | None = None,
    ) -> list[dict[str, Any]]:
        blocks: list[dict[str, Any]] = []
        for block in unit.get("primary_blocks") or []:
            if not isinstance(block, dict):
                continue
            source_text = str(
                block.get("presentation_text")
                or block.get("source_text")
                or ""
            )
            if source_char_limit is not None and len(source_text) > source_char_limit:
                source_text = _complete_sentence_excerpt(
                    source_text,
                    source_char_limit,
                )
            compatible_layout_ids = [
                str(layout_id)
                for layout_id in block.get("compatible_template_layout_ids") or []
                if str(layout_id) in retained_layout_ids
            ]
            blocks.append({
                "block_id": str(block.get("block_id") or ""),
                "source_title": str(block.get("source_title") or ""),
                "role": str(block.get("role") or ""),
                "artifact_kinds": list(block.get("artifact_kinds") or []),
                "required_slot_kinds": list(
                    block.get("required_slot_kinds") or []
                ),
                "page_intent": str(block.get("page_intent") or ""),
                "source_text": source_text,
                "allowed_protected_tokens": list(
                    block.get("allowed_protected_tokens") or []
                ),
                "title_candidates": compact_candidates(
                    block.get("title_candidates")
                ),
                "compatible_template_layout_ids": compatible_layout_ids,
            })
        return blocks

    def model_unit(
        unit: dict[str, Any],
        *,
        source_char_limit: int | None = None,
    ) -> dict[str, Any]:
        partitions = representative_partition_options(unit)
        retained_layout_ids = {
            str(layout_id)
            for layout_id in unit.get("allowed_template_layout_ids") or []
            if str(layout_id)
        }
        if not retained_layout_ids:
            retained_layout_ids = partition_layout_ids(partitions)
        allowed_by_intent = {
            str(intent): [
                str(layout_id)
                for layout_id in layout_ids or []
                if str(layout_id) in retained_layout_ids
            ]
            for intent, layout_ids in (
                unit.get("allowed_template_layout_ids_by_page_intent") or {}
            ).items()
        }
        allowed_by_intent = {
            intent: layout_ids
            for intent, layout_ids in allowed_by_intent.items()
            if layout_ids
        }
        compacted = {
            key: unit[key]
            for key in unit_fields
            if key in unit
        }
        compacted.update({
            "primary_blocks": model_primary_blocks(
                unit,
                retained_layout_ids=retained_layout_ids,
                source_char_limit=source_char_limit,
            ),
            "title_candidates": compact_candidates(unit.get("title_candidates")),
            "safe_partition_options": partitions,
            "allowed_template_layout_ids": sorted(retained_layout_ids),
            "allowed_template_layout_ids_by_page_intent": allowed_by_intent,
            "summary_max_chars_by_layout_id": {
                str(layout_id): value
                for layout_id, value in (
                    unit.get("summary_max_chars_by_layout_id") or {}
                ).items()
                if str(layout_id) in retained_layout_ids
            },
            "summary_min_chars_by_layout_id": {
                str(layout_id): value
                for layout_id, value in (
                    unit.get("summary_min_chars_by_layout_id") or {}
                ).items()
                if str(layout_id) in retained_layout_ids
            },
        })
        return compacted

    def model_repair_feedback(value: Any) -> dict[str, Any] | None:
        if not isinstance(value, dict):
            return None

        def compact_partition(partition: Any) -> dict[str, Any]:
            if not isinstance(partition, dict):
                return {}
            return {
                key: partition[key]
                for key in ("partition_id", "page_count")
                if key in partition
            } | {
                "pages": [
                    {
                        key: page[key]
                        for key in (
                            "source_block_ids",
                            "template_layout_ids",
                        )
                        if key in page
                    }
                    for page in partition.get("pages") or []
                    if isinstance(page, dict)
                ],
            }

        target_fields = (
            "page_id",
            "teaching_unit_id",
            "allowed_page_count_range",
            "source_coverage_verified",
            "source_projection_safe",
            "observed_unit_page_ids",
            "repartition_required",
            "force_required_partition",
            "clear_provider_summary",
            "repartition_scope",
            "source_block_order",
            "replace_page_ids",
            "current_partition",
            "artifact_layout_ids_by_kind",
            "page_intent",
            "allowed_template_layout_ids",
            "required_template_layout_id",
            "required_artifact_kinds",
            "current_layout_artifact_kinds",
            "missing_artifact_kinds",
            "artifact_source_block_ids_by_kind",
            "required_source_block_ids",
            "current_source_block_ids",
            "missing_source_block_ids",
            "duplicate_source_block_ids",
            "duplicate_page_ids",
            "allowed_title_candidates",
            "available_title_candidates",
            "required_title",
            "title_max_chars",
            "current_title",
            "duplicate_title",
            "conflicting_page_ids",
            "forbidden_titles",
            "current_summary",
            "unsupported_protected_tokens",
            "summary_min_chars",
            "summary_max_chars",
            "required_summary",
            "clear_summary",
            "summary_policy",
        )

        def compact_target(target: Any) -> dict[str, Any]:
            if not isinstance(target, dict):
                return {}
            compacted = {
                key: target[key]
                for key in target_fields
                if key in target
            }
            if target.get("required_safe_partition"):
                compacted["required_safe_partition"] = compact_partition(
                    target.get("required_safe_partition")
                )
            return compacted

        return {
            key: value[key]
            for key in (
                "attempt",
                "code",
                "message",
            )
            if key in value
        } | {
            "repair_targets": [
                compact_target(target)
                for target in value.get("repair_targets") or []
                if isinstance(target, dict)
            ],
            "instruction": (
                "Only repair the listed teaching units. Choose one complete "
                "safe_partition_options entry; bind multiple related block IDs "
                "to the same page when that entry requires it. Copy every "
                "source_block_ids list exactly, choose one listed layout, and "
                "prefer a title candidate from the bound blocks."
            )
        }

    def build(source_char_limit: int | None) -> dict[str, Any]:
        top_level = {
            key: value
            for key, value in request.items()
            if key not in {"teaching_units", "repair_feedback"}
        }
        repair_feedback = model_repair_feedback(request.get("repair_feedback"))
        if repair_feedback:
            top_level["repair_feedback"] = repair_feedback
        return {
            **top_level,
            "teaching_units": [
                model_unit(unit, source_char_limit=source_char_limit)
                for unit in request.get("teaching_units") or []
                if isinstance(unit, dict)
            ],
        }

    model_request = build(None)
    for source_char_limit in (640, 420, 280, 180, 120, 80):
        if len(json.dumps(model_request, ensure_ascii=False)) <= _STORY_MODEL_REQUEST_CHAR_BUDGET:
            break
        model_request = build(source_char_limit)

    return model_request


def _validate_story_batch_candidate(
    *,
    graph: CoursePresentationGraphV1,
    template: TemplateLayoutPackContractV1,
    request: dict[str, Any],
    batch: SlideStoryBatchV3,
) -> None:
    reserved_titles = {
        re.sub(r"\s+", "", str(title)).casefold()
        for title in request.get("constraints", {}).get("forbidden_titles") or []
        if str(title).strip()
    }
    reused = next(
        (
            page for page in batch.pages
            if re.sub(r"\s+", "", page.title).casefold() in reserved_titles
        ),
        None,
    )
    if reused is not None:
        raise V6BuildError(
            stage="story",
            code="duplicate_slide_title",
            message="Each V6 page must have a distinct teaching title",
            page_id=reused.page_id,
        )
    requested_unit_ids = {
        str(unit.get("teaching_unit_id") or "")
        for unit in request.get("teaching_units") or []
        if isinstance(unit, dict)
    }
    units = [
        unit for unit in graph.units
        if unit.teaching_unit_id in requested_unit_ids
    ]
    scoped_graph = graph.model_copy(update={
        "units": units,
        "formal_block_ids": [
            block_id
            for unit in units
            for block_id in unit.primary_block_ids
        ],
        "primary_block_coverage": 1.0,
        "diagnostics": [],
    })
    validate_slide_story_plan_v3(
        SlideStoryPlanV3(
            source_document_revision=graph.source_document_revision,
            template_digest=template.template_digest,
            batches=[batch],
        ),
        scoped_graph,
        template,
    )


def _story_repair_targets(
    request: dict[str, Any],
    response_payload: dict[str, Any] | None,
    error: Exception | None,
) -> list[dict[str, Any]]:
    """Describe a rejected page using only its frozen request constraints."""

    if response_payload is None or not isinstance(error, V6BuildError):
        return []
    pages = response_payload.get("pages")
    if not isinstance(pages, list):
        return []
    units = {
        str(item.get("teaching_unit_id") or ""): item
        for item in request.get("teaching_units") or []
        if isinstance(item, dict)
    }

    def grounded_density_excerpt(
        source: str,
        *,
        minimum: int,
        maximum: int,
    ) -> str:
        """Return only a complete source-mapped companion within its slot."""

        normalized = " ".join(_presentation_summary_text(source).split())
        if not normalized or maximum <= 0:
            return ""
        preferred_capacity = min(
            maximum,
            max(minimum, minimum + 80),
        )
        if len(normalized) <= preferred_capacity:
            return normalized
        required = min(minimum, len(normalized))
        for capacity in dict.fromkeys((preferred_capacity, maximum)):
            candidate = _complete_sentence_excerpt(normalized, capacity)
            if (
                candidate
                and len(candidate) >= required
                and candidate in normalized
            ):
                return candidate
        return ""

    def target_for(
        unit: dict[str, Any],
        *,
        page_id: str = "",
        missing_source_block_ids: list[str] | None = None,
        duplicate_source_block_ids: list[str] | None = None,
        duplicate_page_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        unit_id = str(unit.get("teaching_unit_id") or "")
        current_page = next(
            (
                page for page in pages
                if isinstance(page, dict)
                and str(page.get("page_id") or "") == page_id
            ),
            None,
        )
        repartition_required = (
            error.failure.code in _STORY_UNIT_REPARTITION_FAILURE_CODES
        )
        observed_unit_pages = [
            page
            for page in pages
            if isinstance(page, dict)
            and str(page.get("teaching_unit_id") or "") == unit_id
        ]
        replaced_page_ids = {
            str(page.get("page_id") or "")
            for page in observed_unit_pages
            if str(page.get("page_id") or "")
        } if repartition_required else set()
        current_title = str((current_page or {}).get("title") or "")
        current_summary = str((current_page or {}).get("summary") or "")
        normalized_current_title = re.sub(r"\s+", "", current_title).casefold()
        conflicting_page_ids = [
            str(page.get("page_id") or "")
            for page in pages
            if isinstance(page, dict)
            and str(page.get("page_id") or "") != page_id
            and str(page.get("page_id") or "") not in replaced_page_ids
            and re.sub(r"\s+", "", str(page.get("title") or "")).casefold()
            == normalized_current_title
        ] if normalized_current_title else []
        forbidden_titles = list(dict.fromkeys([
            *(
                str(title)
                for title in request.get("constraints", {}).get("forbidden_titles") or []
                if str(title).strip()
            ),
            *(
                str(page.get("title") or "")
                for page in pages
                if isinstance(page, dict)
                and str(page.get("page_id") or "") != page_id
                and str(page.get("page_id") or "") not in replaced_page_ids
                and str(page.get("title") or "").strip()
            ),
        ]))
        normalized_forbidden_titles = {
            re.sub(r"\s+", "", title).casefold()
            for title in forbidden_titles
        }
        title_max_chars = int(unit.get("title_max_chars") or 0)
        current_source_block_ids = [
            str(block_id)
            for block_id in (current_page or {}).get("source_block_ids") or []
        ]
        block_metadata = {
            str(block.get("block_id") or ""): block
            for block in unit.get("primary_blocks") or []
            if isinstance(block, dict)
        }
        allowed_title_candidates = _request_title_candidates_for_blocks(
            unit,
            current_source_block_ids,
        )
        title_source_text = "\n".join(
            "\n".join(filter(None, [
                str(block_metadata.get(block_id, {}).get("source_title") or "").strip(),
                str(block_metadata.get(block_id, {}).get("source_text") or "").strip(),
            ]))
            for block_id in current_source_block_ids
        )
        if any(
            str(block_metadata.get(block_id, {}).get("role") or "") == "objective"
            for block_id in current_source_block_ids
        ):
            title_source_text = "\n".join(filter(None, [
                str(unit.get("section_title") or "").strip(),
                title_source_text,
            ]))
        current_roles = [
            str(block_metadata.get(block_id, {}).get("role") or "")
            for block_id in current_source_block_ids
            if str(block_metadata.get(block_id, {}).get("role") or "")
        ]
        current_artifacts = {
            str(artifact)
            for block_id in current_source_block_ids
            for artifact in block_metadata.get(block_id, {}).get("artifact_kinds") or []
            if str(artifact)
        }
        layout_artifact_kinds_by_id = {
            str(layout.get("template_layout_id") or ""): {
                str(artifact)
                for artifact in layout.get("artifact_kinds") or []
                if str(artifact)
            }
            for layout in unit.get("allowed_template_layouts") or []
            if isinstance(layout, dict)
            and str(layout.get("template_layout_id") or "")
        }
        current_layout_id = str(
            (current_page or {}).get("template_layout_id") or ""
        )
        current_layout_artifacts = layout_artifact_kinds_by_id.get(
            current_layout_id,
            set(),
        )
        artifact_source_block_ids_by_kind = {
            artifact: [
                block_id
                for block_id in current_source_block_ids
                if artifact in set(
                    block_metadata.get(block_id, {}).get("artifact_kinds") or []
                )
            ]
            for artifact in sorted(current_artifacts)
        }
        page_intent = (
            teaching_intent_for_roles(current_roles, current_artifacts)
            if current_roles or current_artifacts
            else str(unit.get("teaching_intent") or "")
        )
        page_allowed_layout_ids = list(
            (unit.get("allowed_template_layout_ids_by_page_intent") or {}).get(
                page_intent,
                unit.get("allowed_template_layout_ids") or [],
            )
        )
        available_title_candidates = [
            title
            for title in allowed_title_candidates
            if not _generic_teaching_page_title(str(title))
            if not _title_is_incomplete(str(title))
            if (not title_max_chars or len(str(title)) <= title_max_chars)
            and re.sub(r"\s+", "", str(title)).casefold()
            not in normalized_forbidden_titles
            and not (
                _title_protected_tokens(str(title))
                - _title_protected_tokens(title_source_text)
            )
            and _semantic_grounding_ratio(str(title), title_source_text) >= 0.12
            and _semantic_grounding_ratio(
                str(title),
                _title_semantic_source_text(title_source_text),
            ) >= 0.25
        ]
        artifact_layout_ids_by_kind: dict[str, list[str]] = defaultdict(list)
        for layout in unit.get("allowed_template_layouts") or []:
            if not isinstance(layout, dict):
                continue
            layout_id = str(layout.get("template_layout_id") or "")
            if not layout_id:
                continue
            for artifact_kind in layout.get("artifact_kinds") or []:
                artifact = str(artifact_kind or "")
                if artifact and layout_id not in artifact_layout_ids_by_kind[artifact]:
                    artifact_layout_ids_by_kind[artifact].append(layout_id)
        title_repair_required = error.failure.code in {
            "duplicate_slide_title",
            "story_title_capacity_exceeded",
            "story_unsupported_title",
            "story_title_incomplete",
            "story_title_lacks_specificity",
        }
        summary_min_chars = int(
            (unit.get("summary_min_chars_by_layout_id") or {}).get(
                current_layout_id,
                0,
            )
            or 0
        )
        summary_max_chars = int(
            (unit.get("summary_max_chars_by_layout_id") or {}).get(
                current_layout_id,
                0,
            )
            or 0
        )
        summary_repair_required = error.failure.code in {
            "story_page_underfilled",
            "story_summary_capacity_exceeded",
            "story_summary_markdown_invalid",
            "story_unsupported_fact",
            "story_unsupported_semantic_claim",
        }
        allowed_protected_tokens = sorted({
            str(token)
            for block_id in current_source_block_ids
            for token in block_metadata.get(block_id, {}).get(
                "allowed_protected_tokens",
                [],
            )
            if str(token)
        })
        unsupported_protected_tokens = sorted(
            _protected_tokens(current_summary) - set(allowed_protected_tokens)
        )
        required_summary = ""
        if summary_repair_required and (summary_min_chars or summary_max_chars):
            grounded_source = _presentation_summary_text("\n\n".join(
                str(block_metadata.get(block_id, {}).get("source_text") or "")
                for block_id in current_source_block_ids
            ))
            repair_source = grounded_source
            if (
                error.failure.code == "story_summary_capacity_exceeded"
                and current_summary
                and _presentation_summary_text(current_summary) == current_summary.strip()
                and not _looks_like_markdown_table(current_summary)
            ):
                repair_source = current_summary.strip()
            effective_max = summary_max_chars or len(repair_source)
            required_summary = grounded_density_excerpt(
                repair_source,
                minimum=summary_min_chars,
                maximum=effective_max,
            )
        clear_summary = bool(
            summary_repair_required
            and (summary_max_chars <= 0 or not required_summary)
        )
        safe_partition_options = [
            option
            for option in unit.get("safe_partition_options") or []
            if isinstance(option, dict)
            and isinstance(option.get("pages"), list)
            and option.get("pages")
        ]
        observed_page_count = len(observed_unit_pages)
        observed_source_ids = [
            str(block_id)
            for page in observed_unit_pages
            for block_id in page.get("source_block_ids") or []
        ]
        expected_source_ids = [
            str(block_id) for block_id in unit.get("primary_block_ids") or []
        ]
        source_coverage_verified = (
            Counter(observed_source_ids) == Counter(expected_source_ids)
        )
        source_projection_safe = bool(
            expected_source_ids
            and safe_partition_options
            and all(
                block_id in set(expected_source_ids)
                for block_id in observed_source_ids
            )
        )
        required_safe_partition = (
            _required_safe_partition(
                unit,
                observed_page_count=observed_page_count,
            )
            if repartition_required and source_projection_safe
            else {}
        )
        return {
            "page_id": page_id,
            "teaching_unit_id": unit_id,
            "allowed_page_count_range": list(
                unit.get("allowed_page_count_range")
                or [1, max(1, len(unit.get("primary_block_ids") or []))]
            ),
            "safe_page_slices": list(unit.get("safe_page_slices") or []),
            "safe_partition_options": list(
                unit.get("safe_partition_options") or []
            ),
            "required_safe_partition": required_safe_partition,
            "source_coverage_verified": source_coverage_verified,
            "source_projection_safe": source_projection_safe,
            "observed_unit_page_ids": [
                str(page.get("page_id") or "")
                for page in observed_unit_pages
                if str(page.get("page_id") or "")
            ],
            "repartition_required": repartition_required,
            "force_required_partition": bool(
                repartition_required
                and error.failure.code
                in {
                    "template_source_semantic_fidelity_incomplete",
                    "template_source_slot_coverage_incomplete",
                }
            ),
            "clear_provider_summary": bool(
                repartition_required
                and error.failure.code
                in {
                    "template_source_semantic_fidelity_incomplete",
                    "template_source_slot_coverage_incomplete",
                }
            ),
            "repartition_scope": (
                "teaching_unit" if repartition_required else "page"
            ),
            "source_block_order": list(unit.get("primary_block_ids") or []),
            "replace_page_ids": [
                str(page.get("page_id") or "")
                for page in observed_unit_pages
                if str(page.get("page_id") or "")
            ] if repartition_required else [],
            "current_partition": [
                {
                    "page_id": str(page.get("page_id") or ""),
                    "template_layout_id": str(
                        page.get("template_layout_id") or ""
                    ),
                    "source_block_ids": [
                        str(block_id)
                        for block_id in page.get("source_block_ids") or []
                    ],
                }
                for page in observed_unit_pages
            ],
            "allowed_template_layout_ids_by_page_intent": dict(
                unit.get("allowed_template_layout_ids_by_page_intent") or {}
            ),
            "artifact_layout_ids_by_kind": dict(artifact_layout_ids_by_kind),
            "primary_blocks": list(unit.get("primary_blocks") or []),
            "page_intent": page_intent,
            "allowed_template_layout_ids": page_allowed_layout_ids,
            "required_template_layout_id": (
                current_layout_id if summary_repair_required else ""
            ),
            "required_artifact_kinds": sorted(current_artifacts),
            "current_layout_artifact_kinds": sorted(current_layout_artifacts),
            "missing_artifact_kinds": sorted(
                current_artifacts - current_layout_artifacts
            ),
            "artifact_source_block_ids_by_kind": (
                artifact_source_block_ids_by_kind
            ),
            "required_source_block_ids": list(unit.get("primary_block_ids") or []),
            "current_source_block_ids": current_source_block_ids,
            "missing_source_block_ids": list(missing_source_block_ids or []),
            "duplicate_source_block_ids": list(duplicate_source_block_ids or []),
            "duplicate_page_ids": list(duplicate_page_ids or []),
            "allowed_title_candidates": allowed_title_candidates,
            "available_title_candidates": available_title_candidates,
            "required_title": (
                str(available_title_candidates[0])
                if title_repair_required and available_title_candidates
                else ""
            ),
            "title_max_chars": title_max_chars,
            "current_title": current_title,
            "duplicate_title": current_title if conflicting_page_ids else "",
            "conflicting_page_ids": conflicting_page_ids,
            "forbidden_titles": forbidden_titles,
            "current_summary": current_summary,
            "allowed_protected_tokens": allowed_protected_tokens,
            "unsupported_protected_tokens": unsupported_protected_tokens,
            "summary_min_chars": summary_min_chars,
            "summary_max_chars": summary_max_chars,
            "required_summary": required_summary,
            "clear_summary": clear_summary,
            "summary_policy": (
                "source_grounded_semantic_closure_for_all_bound_blocks_"
                "complete_sentence_no_markdown"
            ),
        }

    if error.failure.code in {
        "story_page_underfilled",
        "story_summary_capacity_exceeded",
    }:
        capacity_exceeded = error.failure.code == "story_summary_capacity_exceeded"
        underfilled_targets: list[dict[str, Any]] = []
        for page in pages:
            if not isinstance(page, dict):
                continue
            page_id = str(page.get("page_id") or "")
            unit = units.get(str(page.get("teaching_unit_id") or ""))
            if not page_id or unit is None:
                continue
            target = target_for(unit, page_id=page_id)
            minimum = int(target.get("summary_min_chars") or 0)
            maximum = int(target.get("summary_max_chars") or 0)
            current = _visible_prose_text(str(page.get("summary") or ""))
            needs_repair = (
                maximum > 0 and len(current) > maximum
                if capacity_exceeded
                else minimum > 0 and len(current) < minimum
            )
            if needs_repair and (
                target.get("required_summary") or target.get("clear_summary")
            ):
                underfilled_targets.append(target)
        if underfilled_targets:
            return underfilled_targets

    if error.failure.code == "story_summary_markdown_invalid":
        markdown_targets: list[dict[str, Any]] = []
        for page in pages:
            if not isinstance(page, dict):
                continue
            page_id = str(page.get("page_id") or "")
            unit = units.get(str(page.get("teaching_unit_id") or ""))
            summary = str(page.get("summary") or "")
            if not page_id or unit is None or not summary:
                continue
            if (
                _presentation_summary_text(summary) == summary.strip()
                and not _looks_like_markdown_table(summary)
            ):
                continue
            target = target_for(unit, page_id=page_id)
            if target.get("required_summary") or target.get("clear_summary"):
                markdown_targets.append(target)
        if markdown_targets:
            return markdown_targets

    if error.failure.code in {
        "story_unsupported_fact",
        "story_unsupported_semantic_claim",
    }:
        grounding_targets: list[dict[str, Any]] = []
        for page in pages:
            if not isinstance(page, dict):
                continue
            page_id = str(page.get("page_id") or "")
            unit = units.get(str(page.get("teaching_unit_id") or ""))
            summary = str(page.get("summary") or "")
            if not page_id or unit is None or not summary:
                continue
            unit_source_text = str(unit.get("source_text") or "")
            needs_repair = (
                bool(
                    _protected_tokens(summary)
                    - _protected_tokens(unit_source_text)
                )
                if error.failure.code == "story_unsupported_fact"
                else _semantic_grounding_ratio(summary, unit_source_text) < 0.12
            )
            if not needs_repair:
                continue
            target = target_for(unit, page_id=page_id)
            if target.get("required_summary") or target.get("clear_summary"):
                grounding_targets.append(target)
        if grounding_targets:
            return grounding_targets

    failed_page_id = str(error.failure.page_id or "")
    if not failed_page_id:
        block_page_ids: dict[str, list[str]] = defaultdict(list)
        for page in pages:
            if not isinstance(page, dict):
                continue
            page_id = str(page.get("page_id") or "")
            for block_id in page.get("source_block_ids") or []:
                block_page_ids[str(block_id)].append(page_id)
        covered = set(block_page_ids)
        missing_targets = []
        for unit in units.values():
            primary_ids = [
                str(block_id)
                for block_id in unit.get("primary_block_ids") or []
            ]
            missing = [block_id for block_id in primary_ids if block_id not in covered]
            duplicates = [
                block_id
                for block_id in primary_ids
                if len(block_page_ids.get(block_id) or []) > 1
            ]
            if missing or duplicates:
                duplicate_pages = list(dict.fromkeys(
                    page_id
                    for block_id in duplicates
                    for page_id in block_page_ids.get(block_id) or []
                    if page_id
                ))
                missing_targets.append(target_for(
                    unit,
                    missing_source_block_ids=missing,
                    duplicate_source_block_ids=duplicates,
                    duplicate_page_ids=duplicate_pages,
                ))
        return missing_targets
    failed_page = next(
        (
            page for page in pages
            if isinstance(page, dict)
            and str(page.get("page_id") or "") == failed_page_id
        ),
        None,
    )
    if failed_page is None:
        return []
    unit_id = str(failed_page.get("teaching_unit_id") or "")
    unit = units.get(unit_id)
    if unit is None:
        return []
    return [target_for(unit, page_id=failed_page_id)]


def _story_request_page_intent(
    unit: dict[str, Any],
    source_block_ids: list[str],
) -> str:
    block_metadata = {
        str(block.get("block_id") or ""): block
        for block in unit.get("primary_blocks") or []
        if isinstance(block, dict)
    }
    roles = [
        str(block_metadata.get(block_id, {}).get("role") or "")
        for block_id in source_block_ids
        if str(block_metadata.get(block_id, {}).get("role") or "")
    ]
    artifacts = {
        str(artifact)
        for block_id in source_block_ids
        for artifact in block_metadata.get(block_id, {}).get("artifact_kinds") or []
        if str(artifact)
    }
    return (
        teaching_intent_for_roles(roles, artifacts)
        if roles or artifacts
        else str(unit.get("teaching_intent") or "")
    )


def _coalesce_oversplit_story_unit(
    response_payload: dict[str, Any],
    request: dict[str, Any],
    error: V6BuildError,
) -> dict[str, Any]:
    """Deterministically cap one coherent unit without rewriting its batch."""

    if error.failure.code != "teaching_unit_page_limit_exceeded":
        return response_payload
    pages = response_payload.get("pages")
    if not isinstance(pages, list):
        return response_payload
    failed_page = next(
        (
            page for page in pages
            if isinstance(page, dict)
            and str(page.get("page_id") or "") == str(error.failure.page_id or "")
        ),
        None,
    )
    if failed_page is None:
        return response_payload
    unit_id = str(failed_page.get("teaching_unit_id") or "")
    unit = next(
        (
            item for item in request.get("teaching_units") or []
            if isinstance(item, dict)
            and str(item.get("teaching_unit_id") or "") == unit_id
        ),
        None,
    )
    unit_pages = [
        page for page in pages
        if isinstance(page, dict)
        and str(page.get("teaching_unit_id") or "") == unit_id
    ]
    page_count_range = (
        list(
            unit.get("allowed_page_count_range")
            or [1, max(1, len(unit.get("primary_block_ids") or []))]
        )
        if unit is not None
        else [1, 1]
    )
    maximum_pages = int(page_count_range[-1])
    if unit is None or len(unit_pages) <= maximum_pages:
        return response_payload

    primary_ids = [
        str(block_id) for block_id in unit.get("primary_block_ids") or []
    ]
    seen: set[str] = set()
    owner_pages: list[dict[str, Any]] = []
    for page in unit_pages:
        page_ids = {
            str(block_id) for block_id in page.get("source_block_ids") or []
        }
        fresh_ids = [
            block_id for block_id in primary_ids
            if block_id in page_ids and block_id not in seen
        ]
        if fresh_ids:
            owner_pages.append(page)
            seen.update(fresh_ids)
    observed_ids = [block_id for block_id in primary_ids if block_id in seen]
    if not observed_ids or not owner_pages:
        return response_payload

    target_count = min(maximum_pages, len(owner_pages), len(observed_ids))
    base_size, remainder = divmod(len(observed_ids), target_count)
    chunks: list[list[str]] = []
    cursor = 0
    for index in range(target_count):
        size = base_size + (1 if index < remainder else 0)
        chunks.append(observed_ids[cursor:cursor + size])
        cursor += size

    replacements: list[dict[str, Any]] = []
    used_titles = {
        re.sub(r"\s+", "", str(page.get("title") or "")).casefold()
        for page in pages
        if isinstance(page, dict)
        and str(page.get("teaching_unit_id") or "") != unit_id
        and str(page.get("title") or "").strip()
    }
    for index, source_ids in enumerate(chunks):
        page = dict(owner_pages[index])
        page["source_block_ids"] = source_ids
        page["summary"] = ""
        replacement_title = next(
            (
                candidate
                for candidate in _request_title_candidates_for_blocks(
                    unit,
                    source_ids,
                )
                if re.sub(r"\s+", "", candidate).casefold() not in used_titles
            ),
            "",
        )
        if replacement_title:
            page["title"] = replacement_title
            used_titles.add(
                re.sub(r"\s+", "", replacement_title).casefold()
            )
        page_intent = _story_request_page_intent(unit, source_ids)
        allowed_layout_ids = list(
            (unit.get("allowed_template_layout_ids_by_page_intent") or {}).get(
                page_intent,
                unit.get("allowed_template_layout_ids") or [],
            )
        )
        if (
            allowed_layout_ids
            and str(page.get("template_layout_id") or "") not in allowed_layout_ids
        ):
            page["template_layout_id"] = str(allowed_layout_ids[0])
        replacements.append(page)

    rebuilt_pages: list[Any] = []
    emitted = False
    for page in pages:
        if (
            isinstance(page, dict)
            and str(page.get("teaching_unit_id") or "") == unit_id
        ):
            if not emitted:
                rebuilt_pages.extend(replacements)
                emitted = True
            continue
        rebuilt_pages.append(page)
    return {**response_payload, "pages": rebuilt_pages}


def _apply_grounded_story_repairs(
    response_payload: dict[str, Any],
    request: dict[str, Any],
    error: V6BuildError,
) -> dict[str, Any]:
    """Apply repairs whose exact visible text is already frozen in the request."""

    if error.failure.code not in {
        "story_page_underfilled",
        "story_summary_capacity_exceeded",
        "story_summary_markdown_invalid",
        "story_unsupported_fact",
        "story_unsupported_semantic_claim",
    }:
        return response_payload
    pages = response_payload.get("pages")
    if not isinstance(pages, list):
        return response_payload
    targets = _story_repair_targets(request, response_payload, error)
    replacements = {
        str(target.get("page_id") or ""): (
            ""
            if target.get("clear_summary") is True
            else str(target.get("required_summary") or "").strip()
        )
        for target in targets
        if str(target.get("page_id") or "")
        and (
            target.get("clear_summary") is True
            or str(target.get("required_summary") or "").strip()
        )
    }
    if not replacements:
        return response_payload
    repaired = []
    changed = False
    for value in pages:
        if not isinstance(value, dict):
            repaired.append(value)
            continue
        page = dict(value)
        page_id = str(page.get("page_id") or "")
        if page_id in replacements:
            page["summary"] = replacements[page_id]
            changed = True
        repaired.append(page)
    return {**response_payload, "pages": repaired} if changed else response_payload


def _merge_story_repair_response(
    previous_payload: dict[str, Any],
    repaired_payload: dict[str, Any],
    request: dict[str, Any],
    repair_unit_ids: list[str],
) -> dict[str, Any]:
    """Replace repaired teaching units while keeping every other page stable."""

    repair_set = set(repair_unit_ids)
    previous_pages = [
        page
        for page in previous_payload.get("pages") or []
        if isinstance(page, dict)
    ]
    repaired_pages = [
        page
        for page in repaired_payload.get("pages") or []
        if isinstance(page, dict)
        and str(page.get("teaching_unit_id") or "") in repair_set
    ]
    previous_by_unit: dict[str, list[dict[str, Any]]] = defaultdict(list)
    repaired_by_unit: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for page in previous_pages:
        previous_by_unit[str(page.get("teaching_unit_id") or "")].append(page)
    for page in repaired_pages:
        repaired_by_unit[str(page.get("teaching_unit_id") or "")].append(page)

    ordered_unit_ids = [
        str(unit.get("teaching_unit_id") or "")
        for unit in request.get("teaching_units") or []
        if isinstance(unit, dict) and str(unit.get("teaching_unit_id") or "")
    ]
    merged_pages: list[dict[str, Any]] = []
    for unit_id in ordered_unit_ids:
        merged_pages.extend(
            repaired_by_unit.get(unit_id, [])
            if unit_id in repair_set
            else previous_by_unit.get(unit_id, [])
        )
    known_unit_ids = set(ordered_unit_ids)
    merged_pages.extend(
        page
        for page in previous_pages
        if str(page.get("teaching_unit_id") or "") not in known_unit_ids
    )
    return {
        **previous_payload,
        **repaired_payload,
        "pages": merged_pages,
    }


async def plan_slide_story_v3(
    graph: CoursePresentationGraphV1,
    template: TemplateLayoutPackContractV1,
    *,
    ai_planner: Planner | None,
    timeout_seconds: float = 180.0,
    batch_callback: BatchLifecycleCallback | None = None,
    resume_batches: list[SlideStoryBatchV3] | None = None,
) -> SlideStoryPlanV3:
    if ai_planner is None:
        raise V6BuildError(
            stage="story",
            code="story_ai_required",
            message="V6 requires the shared AI story planner",
            retryable=True,
        )
    batches: list[SlideStoryBatchV3] = []
    resumed_by_chapter = {
        batch.chapter_id: batch
        for batch in (resume_batches or [])
        if batch.validation_status == "passed"
    }
    page_ordinal = 0
    story_requests = await asyncio.to_thread(_story_requests, graph, template)
    for batch_index, request in enumerate(story_requests):
        batch_id = f"story-{batch_index + 1}"
        resumed = resumed_by_chapter.get(str(request["chapter_id"]))
        if resumed is not None:
            pages = [
                page.model_copy(update={"page_ordinal": page_ordinal + index})
                for index, page in enumerate(resumed.pages)
            ]
            batch = resumed.model_copy(update={"batch_id": batch_id, "pages": pages})
            batch = _assign_global_story_page_ids([batch])[0]
            pages = list(batch.pages)
            try:
                _validate_story_batch_candidate(
                    graph=graph,
                    template=template,
                    request=request,
                    batch=batch,
                )
            except V6BuildError:
                # A checkpoint is only a cache. Revalidate it against the
                # current frozen graph/template before declaring the batch
                # completed; stale or partially repaired pages must be
                # replanned instead of failing only after all chapters finish.
                resumed = None
            else:
                page_ordinal += len(pages)
                batches.append(batch)
                await _notify_batch(batch_callback, {
                    "phase": "completed",
                    "kind": "story",
                    "batch_index": batch_index,
                    "batch_id": batch_id,
                    "chapter_id": batch.chapter_id,
                    "resumed": True,
                    "batch": batch,
                })
                continue
        await _notify_batch(batch_callback, {
            "phase": "started",
            "kind": "story",
            "batch_index": batch_index,
            "batch_id": batch_id,
            "chapter_id": str(request["chapter_id"]),
            "resumed": False,
        })
        started = time.perf_counter()
        attempt_records: list[AIProviderAttemptDiagnosticV1] = []
        reported_provider = ""
        reported_model = ""
        reported_attempts = 1
        planner_invocations = 0
        try:
            contract_error: Exception | None = None
            previous_response_payload: dict[str, Any] | None = None
            for validation_attempt in range(_STORY_SEMANTIC_MAX_ATTEMPTS):
                attempt_request = request
                repair_targets: list[dict[str, Any]] = []
                repair_unit_ids: list[str] = []
                if validation_attempt:
                    repair_targets = _story_repair_targets(
                        request,
                        previous_response_payload,
                        contract_error,
                    )
                    repair_unit_ids = list(dict.fromkeys(
                        str(target.get("teaching_unit_id") or "")
                        for target in repair_targets
                        if str(target.get("teaching_unit_id") or "")
                    ))
                    repair_unit_set = set(repair_unit_ids)
                    repair_units = [
                        unit
                        for unit in request.get("teaching_units") or []
                        if str(unit.get("teaching_unit_id") or "")
                        in repair_unit_set
                    ]
                    attempt_request = {
                        **request,
                        "teaching_units": (
                            repair_units
                            if repair_units
                            else list(request.get("teaching_units") or [])
                        ),
                        "repair_feedback": {
                            "attempt": validation_attempt + 1,
                            "code": (
                                contract_error.failure.code
                                if isinstance(contract_error, V6BuildError)
                                else "story_response_contract_invalid"
                            ),
                            "message": str(contract_error or ""),
                            "repair_targets": repair_targets,
                            "instruction": (
                                "Return only pages for the teaching_units present in this repair "
                                "request; all other teaching units are locked and will be merged "
                                "from the accepted first response. Return a fresh response that "
                                "exactly follows response_contract, "
                                "derives each page's intent from its bound primary_blocks and uses "
                                "only that intent's allowed_template_layout_ids_by_page_intent, and "
                                "contains only source IDs supplied for that unit. Partition every "
                                "unit's primary_block_ids by choosing exactly one complete entry from "
                                "that unit's safe_partition_options. Copy every option page's "
                                "source_block_ids exactly and choose one of its template_layout_ids: bind multiple "
                                "related block IDs to the same page instead of creating one page per "
                                "block. Full source remains available in speaker notes downstream. "
                                "Copy each title verbatim from that unit's title_candidates and keep "
                                "it within that unit's title_max_chars. Titles must name the bound "
                                "page's specific teaching subject and must not end with a connector, "
                                "delimiter, or incomplete phrase. Prefer candidates supplied on the "
                                "bound primary_blocks. Set "
                                "a repair target's title exactly to required_title when provided. Set "
                                "its template_layout_id exactly to required_template_layout_id when "
                                "provided. When a repair target has repartition_required=true, "
                                "replace every page listed in replace_page_ids with a fresh LLM-authored "
                                "partition of source_block_order by choosing exactly one complete entry from "
                                "safe_partition_options. Copy its page source_block_ids exactly and select one "
                                "listed template_layout_id per page. Do not retain "
                                "the failed source grouping. Each new page must bind a non-empty contiguous "
                                "slice of source_block_order, preserve the complete order exactly once, and "
                                "select its layout from allowed_template_layout_ids_by_page_intent. If a "
                                "repair target supplies required_safe_partition, copy that partition's pages "
                                "exactly, including every source_block_ids list, and choose each layout only "
                                "from that page's template_layout_ids. "
                                "If a "
                                "page contains any primary block with artifact_kinds, its layout must also "
                                "appear in that block's compatible_template_layout_ids. The union of "
                                "artifact_kinds for all blocks bound to a page must be a subset of the "
                                "selected layout's artifact kinds. Use required_artifact_kinds, "
                                "current_layout_artifact_kinds, missing_artifact_kinds, and "
                                "artifact_source_block_ids_by_kind to repair the failed grouping. If no "
                                "single layout appears in artifact_layout_ids_by_kind for every required "
                                "artifact, split those source blocks across separate pages. Never assign "
                                "an artifact-bearing page to a text-only layout. The "
                                "validator will reject the result instead of generating replacement story "
                                "pages. Set "
                                    "summary to one complete, Markdown-free, source-grounded sentence "
                                "that expresses the semantic closure of every bound source_block_id "
                                "whose length remains between summary_min_chars_by_layout_id and "
                                "summary_max_chars_by_layout_id for the selected layout when the frozen "
                                    "source is long enough. Use an empty summary only when the maximum is zero or "
                                    "no faithful synthesis is possible; never add identifiers or facts. Copy "
                                    "identifiers and numbers only from allowed_protected_tokens and preserve "
                                    "their exact spelling; remove every unsupported_protected_token rather "
                                    "than abbreviating or autocorrecting it. Set a "
                                    "repair target's summary exactly to required_summary when provided."
                            ),
                        },
                    }
                    await _notify_batch(batch_callback, {
                        "phase": "started",
                        "kind": "story",
                        "batch_index": batch_index,
                        "batch_id": batch_id,
                        "chapter_id": str(request["chapter_id"]),
                        "resumed": False,
                        "retry_attempt": validation_attempt,
                    })
                try:
                    planner_invocations += 1
                    raw = await _invoke(
                        ai_planner,
                        _story_model_request(attempt_request),
                        timeout_seconds,
                    )
                    attempt_records.extend(_provider_attempts_from(raw))
                    normalized_response_payload = _normalize_story_batch_response(
                        raw,
                        attempt_request,
                        graph,
                        template,
                    )
                    if (
                        validation_attempt
                        and previous_response_payload is not None
                        and repair_unit_ids
                    ):
                        previous_response_payload = _merge_story_repair_response(
                            previous_response_payload,
                            normalized_response_payload,
                            request,
                            repair_unit_ids,
                        )
                    else:
                        previous_response_payload = normalized_response_payload
                    response = _StoryBatchResponse.model_validate(
                        previous_response_payload
                    )
                    _require_ai_planner_provenance(
                        provider=response.provider,
                        model=response.model,
                        stage="story",
                    )
                    reported_provider = response.provider or reported_provider
                    reported_model = response.model or reported_model
                    reported_attempts = max(
                        reported_attempts,
                        response.attempts + validation_attempt,
                        len(attempt_records),
                        planner_invocations,
                    )
                    if response.schema_version != "slide_story_batch_response_v3":
                        raise ValueError("Unexpected story response schema")
                    if response.chapter_id != request["chapter_id"]:
                        raise ValueError("Story response chapter does not match its request")
                    local_pages = [
                        SlideStoryPageV3(
                            **item.model_dump(mode="json"),
                            page_ordinal=index,
                        )
                        for index, item in enumerate(response.pages)
                    ]
                    candidate_batch = SlideStoryBatchV3(
                        batch_id=batch_id,
                        chapter_id=response.chapter_id,
                        provider=response.provider or "shared-ai-pool",
                        model=response.model or "provider-selected",
                        duration_ms=max(0, round((time.perf_counter() - started) * 1000)),
                        attempts=reported_attempts,
                        validation_status="passed",
                        pages=local_pages,
                    )
                    candidate_batch = _assign_global_story_page_ids(
                        [candidate_batch]
                    )[0]
                    local_pages = list(candidate_batch.pages)
                    try:
                        _validate_story_batch_candidate(
                            graph=graph,
                            template=template,
                            request=request,
                            batch=candidate_batch,
                        )
                    except V6BuildError as validation_error:
                        if validation_error.failure.code == "duplicate_slide_title":
                            candidate_batch = _assign_global_story_titles(
                                [candidate_batch],
                                [request],
                            )[0]
                            candidate_batch = _assign_global_story_page_ids(
                                [candidate_batch]
                            )[0]
                            local_pages = list(candidate_batch.pages)
                            try:
                                _validate_story_batch_candidate(
                                    graph=graph,
                                    template=template,
                                    request=request,
                                    batch=candidate_batch,
                                )
                            except V6BuildError as reassigned_validation_error:
                                validation_error = reassigned_validation_error
                            else:
                                validation_error = None
                        if validation_error is not None:
                            repaired_payload = _apply_grounded_story_repairs(
                                previous_response_payload,
                                request,
                                validation_error,
                            )
                            if repaired_payload is previous_response_payload:
                                repaired_payload = _coalesce_oversplit_story_unit(
                                    previous_response_payload,
                                    request,
                                    validation_error,
                                )
                            if repaired_payload is previous_response_payload:
                                raise validation_error
                            previous_response_payload = repaired_payload
                            response = _StoryBatchResponse.model_validate(
                                previous_response_payload
                            )
                            local_pages = [
                                SlideStoryPageV3(
                                    **item.model_dump(mode="json"),
                                    page_ordinal=index,
                                )
                                for index, item in enumerate(response.pages)
                            ]
                            candidate_batch = candidate_batch.model_copy(
                                update={"pages": local_pages}
                            )
                            candidate_batch = _assign_global_story_titles(
                                [candidate_batch],
                                [request],
                            )[0]
                            candidate_batch = _assign_global_story_page_ids(
                                [candidate_batch]
                            )[0]
                            local_pages = list(candidate_batch.pages)
                            _validate_story_batch_candidate(
                                graph=graph,
                                template=template,
                                request=request,
                                batch=candidate_batch,
                            )
                    pages = [
                        page.model_copy(update={"page_ordinal": page_ordinal + index})
                        for index, page in enumerate(local_pages)
                    ]
                    page_ordinal += len(pages)
                    batch = candidate_batch.model_copy(update={"pages": pages})
                    break
                except (ValidationError, ValueError, V6BuildError) as error:
                    contract_error = error
                    if validation_attempt < _STORY_SEMANTIC_MAX_ATTEMPTS - 1:
                        continue
                    if isinstance(error, V6BuildError):
                        raise V6BuildError(
                            stage=error.failure.stage,
                            code=error.failure.code,
                            message=error.failure.message,
                            retryable=True,
                            chapter_id=str(request["chapter_id"]),
                            page_id=error.failure.page_id,
                            batch_id=batch_id,
                        ) from error
                    raise
                else:  # pragma: no cover - the bounded loop either succeeds or raises
                    raise RuntimeError("Story response repair loop exited unexpectedly")
            batch = SlideStoryBatchV3(
                    batch_id=batch_id,
                    chapter_id=batch.chapter_id,
                    provider=batch.provider,
                    model=batch.model,
                    duration_ms=max(batch.duration_ms, round((time.perf_counter() - started) * 1000)),
                    attempts=batch.attempts,
                    validation_status="passed",
                    pages=batch.pages,
            )
            batches.append(batch)
        except V6BuildError as error:
            await _notify_batch(batch_callback, {
                "phase": "failed",
                "kind": "story",
                "batch_index": batch_index,
                "batch_id": batch_id,
                "chapter_id": str(request["chapter_id"]),
                "resumed": False,
                "diagnostic": _batch_diagnostic(
                    kind="story",
                    batch_id=batch_id,
                    chapter_id=str(request["chapter_id"]),
                    duration_ms=round((time.perf_counter() - started) * 1000),
                    validation_status="failed",
                    failure_category=error.failure.code,
                    provider=reported_provider,
                    model=reported_model,
                    attempts=max(reported_attempts, planner_invocations),
                    attempt_records=attempt_records,
                ),
            })
            raise
        except Exception as error:
            attempt_records.extend(_provider_attempts_from(error))
            code, retryable = _failure_category(error, prefix="story_ai_batch")
            await _notify_batch(batch_callback, {
                "phase": "failed",
                "kind": "story",
                "batch_index": batch_index,
                "batch_id": batch_id,
                "chapter_id": str(request["chapter_id"]),
                "resumed": False,
                "diagnostic": _batch_diagnostic(
                    kind="story",
                    batch_id=batch_id,
                    chapter_id=str(request["chapter_id"]),
                    duration_ms=round((time.perf_counter() - started) * 1000),
                    validation_status="failed",
                    failure_category=code,
                    provider=reported_provider,
                    model=reported_model,
                    attempts=max(reported_attempts, planner_invocations),
                    attempt_records=attempt_records,
                ),
            })
            raise V6BuildError(
                stage="story",
                code=code,
                message=(
                    "PPT planning models are temporarily rate limited; the "
                    "last published deck was preserved and this build can be retried"
                    if code == "story_ai_batch_rate_limited"
                    else "PPT planning provider balance is unavailable; the last "
                    "published deck was preserved and no automatic retry was started"
                    if code == "story_ai_batch_balance_unavailable"
                    else str(error) or "Story AI batch failed"
                ),
                retryable=retryable,
                chapter_id=str(request["chapter_id"]),
                batch_id=batch_id,
            ) from error
        await _notify_batch(batch_callback, {
            "phase": "completed",
            "kind": "story",
            "batch_index": batch_index,
            "batch_id": batch_id,
            "chapter_id": batch.chapter_id,
            "resumed": False,
            "batch": batch,
            "diagnostic": _batch_diagnostic(
                kind="story",
                batch_id=batch_id,
                chapter_id=batch.chapter_id,
                duration_ms=batch.duration_ms,
                validation_status="passed",
                provider=batch.provider,
                model=batch.model,
                attempts=batch.attempts,
                attempt_records=attempt_records,
            ),
        })
    batches = _assign_global_story_titles(batches, story_requests)
    batches = _assign_global_story_page_ids(batches)
    plan = SlideStoryPlanV3(
        source_document_revision=graph.source_document_revision,
        template_digest=template.template_digest,
        batches=batches,
    )
    validate_slide_story_plan_v3(plan, graph, template)
    return plan


def _visual_request(
    batch: SlideStoryBatchV3,
    graph: CoursePresentationGraphV1,
    template: TemplateLayoutPackContractV1,
) -> dict[str, Any]:
    units = {unit.teaching_unit_id: unit for unit in graph.units}
    def page_source_blocks(page: SlideStoryPageV3) -> list[dict[str, str]]:
        unit = units[page.teaching_unit_id]
        blocks = [
            {
                "block_id": block_id,
                "source_text": str(
                    unit.primary_block_presentation_texts.get(block_id)
                    or unit.primary_block_texts.get(block_id)
                    or ""
                ).strip(),
            }
            for block_id in page.source_block_ids
        ]
        if len(blocks) == 1 and not blocks[0]["source_text"]:
            blocks[0]["source_text"] = unit.presentation_text or unit.source_text
        return blocks

    def page_request(page: SlideStoryPageV3) -> dict[str, Any]:
        unit = units[page.teaching_unit_id]
        layout = template.get_layout(page.template_layout_id)
        if layout is None:
            raise V6BuildError(
                stage="template",
                code="template_layout_unavailable",
                message="Visual planning requires a published template layout",
                page_id=page.page_id,
            )
        validate_layout_source_satisfiability(
            page_id=page.page_id,
            template=template,
            layout=layout,
            source_blocks=graph_page_source_blocks(
                unit,
                page.source_block_ids,
            ),
            story_summary=page.summary,
        )
        source_blocks = page_source_blocks(page)
        artifact_kinds = page_artifact_kinds(unit, page.source_block_ids)
        source_decisions = _allowed_visual_decisions(
            artifact_kinds,
            unit.source_asset_refs,
        )
        layout_requires_artifact = _layout_requires_artifact_decision(layout)
        allowed_decisions = _decisions_allowed_by_layout(
            source_decisions,
            layout_artifact_kinds=set(layout.artifact_kinds),
            layout_requires_artifact=layout_requires_artifact,
        )
        if not allowed_decisions:
            raise V6BuildError(
                stage="template",
                code="template_layout_unavailable",
                message="Template layout has no source-supported visual decision",
                page_id=page.page_id,
            )
        return {
            "page_id": page.page_id,
            "teaching_unit_id": page.teaching_unit_id,
            "template_layout_id": page.template_layout_id,
            "source_block_ids": page.source_block_ids,
            "source_text": "\n\n".join(
                block["source_text"] for block in source_blocks
                if block["source_text"]
            ) or unit.presentation_text or unit.source_text,
            "source_blocks": source_blocks,
            "artifact_kinds": sorted(artifact_kinds),
            "layout_artifact_kinds": list(layout.artifact_kinds),
            "layout_requires_artifact": layout_requires_artifact,
            "allowed_decisions": allowed_decisions,
            "source_asset_ids": unit.source_asset_refs,
        }

    return {
        "schema_version": "slide_visual_batch_request_v2",
        "chapter_id": batch.chapter_id,
        "source_document_revision": graph.source_document_revision,
        "template_digest": template.template_digest,
        "constraints": {
            "source_bound_only": True,
            "prefer_text_native_when_visual_is_not_meaningful": True,
            "preserve_required_artifacts": True,
        },
        "response_contract": {
            "schema_version": "slide_visual_batch_response_v2",
            "required_top_level_fields": ["schema_version", "decisions"],
            "required_decision_fields": [
                "page_id",
                "decision",
                "source_block_ids",
                "resolved_template_layout_id",
            ],
            "optional_decision_fields": ["source_asset_ids", "visual_payload"],
            "forbidden_decision_fields": ["decision_type", "code_payload"],
            "diagram_node_fields": ["node_id", "label", "source_block_ids"],
            "diagram_edge_fields": ["source", "target"],
            "diagram_edge_rule": (
                "Every source and target must exactly equal a node_id declared "
                "in the same visual_payload."
            ),
            "diagram_label_rule": (
                "Use complete source-grounded labels. Never end or shorten a node "
                "or edge label with ... or … unless that exact marked phrase occurs "
                "in the bound frozen source."
            ),
        },
        "pages": [page_request(page) for page in batch.pages],
    }


_HARD_VISUAL_ARTIFACTS = {
    "code",
    "formula",
    "table",
    "data",
    "diagram",
    "experiment",
    "source_excerpt",
}
_VISUAL_DECISIONS_BY_ARTIFACT: dict[str, set[str]] = {
    "code": {"code"},
    "formula": {"formula"},
    "table": {"table", "data"},
    "data": {"data", "table"},
    "diagram": {"diagram"},
    "experiment": {"experiment", "image", "data"},
    "source_excerpt": {"source_excerpt", "image"},
}


def _layout_requires_artifact_decision(layout: Any) -> bool:
    slots = layout.slots if hasattr(layout, "slots") else layout.get("slots") or []
    return any(
        (slot.required if hasattr(slot, "required") else bool(slot.get("required")))
        and (
            slot.slot_kind if hasattr(slot, "slot_kind") else str(slot.get("slot_kind") or "")
        ) in {"code", "formula", "table", "visual"}
        for slot in slots
    )


def _decisions_allowed_by_layout(
    source_decisions: list[str],
    *,
    layout_artifact_kinds: set[str],
    layout_requires_artifact: bool,
) -> list[str]:
    if not layout_requires_artifact:
        return list(source_decisions)
    return [
        decision for decision in source_decisions
        if decision in layout_artifact_kinds
    ]


def _allowed_visual_decisions(
    artifact_kinds: set[str],
    source_asset_ids: list[str],
) -> list[str]:
    required_artifacts = artifact_kinds.intersection(_HARD_VISUAL_ARTIFACTS)
    if required_artifacts:
        decisions = {
            decision
            for artifact in required_artifacts
            for decision in _VISUAL_DECISIONS_BY_ARTIFACT.get(artifact, set())
        }
        if not source_asset_ids:
            decisions.difference_update({"image", "experiment"})
        return sorted(decisions)
    decisions = {"diagram", "text_native"}
    if source_asset_ids:
        decisions.add("image")
    return sorted(decisions)


def _safe_text_native_fallback_layout_id(
    page: SlideStoryPageV3,
    unit: CoursePresentationUnitV1,
    template: TemplateLayoutPackContractV1,
) -> str:
    """Resolve a source-safe prose layout for an optional visual failure."""

    original_layout = template.get_layout(page.template_layout_id)
    if original_layout is None:
        return ""
    source_blocks = graph_page_source_blocks(unit, page.source_block_ids)
    teaching_intent = page_teaching_intent(unit, page.source_block_ids)
    required_artifacts = page_artifact_kinds(unit, page.source_block_ids)
    required_slot_kinds = source_required_slot_kinds(source_blocks)
    candidate_slugs = list(dict.fromkeys([
        original_layout.layout_slug,
        *original_layout.safe_continuation_layout_slugs,
    ]))
    for slug in candidate_slugs:
        try:
            candidate = template.get_layout(template.layout_id(slug))
        except KeyError:
            continue
        if candidate is None:
            continue
        if any(
            slot.required
            and slot.slot_kind in {"code", "formula", "table", "visual"}
            for slot in candidate.slots
        ):
            continue
        if teaching_intent not in candidate.teaching_intents:
            continue
        if required_artifacts and not required_artifacts.issubset(
            set(candidate.artifact_kinds)
        ):
            continue
        if not required_slot_kinds.issubset(
            {slot.slot_kind for slot in candidate.slots}
        ):
            continue
        try:
            validate_story_template_text_slots(
                page_id=page.page_id,
                template=template,
                layout=candidate,
                source_blocks=source_blocks,
                story_summary=page.summary,
            )
        except V6BuildError:
            continue
        return candidate.template_layout_id
    return ""


def _degraded_text_native_decision(
    page: SlideStoryPageV3,
    unit: CoursePresentationUnitV1,
    template: TemplateLayoutPackContractV1,
    *,
    reason: str,
    duration_ms: int,
) -> SlideVisualDecisionV2 | None:
    fallback_layout_id = _safe_text_native_fallback_layout_id(
        page,
        unit,
        template,
    )
    if not fallback_layout_id:
        return None
    return SlideVisualDecisionV2(
        page_id=page.page_id,
        decision="text_native",
        source_block_ids=page.source_block_ids,
        resolved_template_layout_id=fallback_layout_id,
        degraded=True,
        degradation_reason=reason,
        duration_ms=duration_ms,
    )


def _validate_visual_batch_candidate(
    *,
    story: SlideStoryPlanV3,
    graph: CoursePresentationGraphV1,
    template: TemplateLayoutPackContractV1,
    batch: SlideStoryBatchV3,
    decisions: list[SlideVisualDecisionV2],
) -> None:
    unit_ids = {page.teaching_unit_id for page in batch.pages}
    scoped_story = story.model_copy(update={"batches": [batch]})
    scoped_graph = graph.model_copy(update={
        "units": [unit for unit in graph.units if unit.teaching_unit_id in unit_ids],
        "formal_block_ids": [
            block_id
            for page in batch.pages
            for block_id in page.source_block_ids
        ],
        "primary_block_coverage": 1.0,
        "diagnostics": [],
    })
    validate_slide_visual_plan_v2(
        SlideVisualPlanV2(
            source_document_revision=graph.source_document_revision,
            template_digest=template.template_digest,
            decisions=decisions,
        ),
        scoped_story,
        scoped_graph,
        template,
    )


_VISUAL_DECISION_TELEMETRY_FIELDS = {
    "provider",
    "model",
    "duration_ms",
    "attempts",
}


def _visual_decisions_are_equivalent(
    left: SlideVisualDecisionV2,
    right: SlideVisualDecisionV2,
) -> bool:
    """Return whether duplicate decisions carry the same semantic contract."""

    return left.model_dump(
        mode="json",
        exclude=_VISUAL_DECISION_TELEMETRY_FIELDS,
    ) == right.model_dump(
        mode="json",
        exclude=_VISUAL_DECISION_TELEMETRY_FIELDS,
    )


def _classify_visual_batch_decisions(
    decisions: list[SlideVisualDecisionV2],
    expected_pages: list[SlideStoryPageV3],
    *,
    allow_missing: bool = False,
) -> tuple[list[SlideVisualDecisionV2], V6BuildError | None]:
    """Canonicalize exact duplicates and classify every coverage violation.

    Conflicting duplicates are excluded so a repair can replace them without
    selecting an arbitrary provider answer. Unknown page IDs remain a hard
    contract error and are never silently discarded.
    """

    expected_page_ids = [page.page_id for page in expected_pages]
    expected_page_id_set = set(expected_page_ids)
    unknown_page_ids = [
        decision.page_id
        for decision in decisions
        if decision.page_id not in expected_page_id_set
    ]
    grouped: dict[str, list[SlideVisualDecisionV2]] = defaultdict(list)
    for decision in decisions:
        if decision.page_id in expected_page_id_set:
            grouped[decision.page_id].append(decision)

    canonical: list[SlideVisualDecisionV2] = []
    conflict_page_ids: list[str] = []
    missing_page_ids: list[str] = []
    for page_id in expected_page_ids:
        candidates = grouped.get(page_id, [])
        if not candidates:
            missing_page_ids.append(page_id)
            continue
        first = candidates[0]
        if any(
            not _visual_decisions_are_equivalent(first, candidate)
            for candidate in candidates[1:]
        ):
            conflict_page_ids.append(page_id)
            continue
        canonical.append(first)

    if unknown_page_ids:
        return canonical, V6BuildError(
            stage="visual",
            code="visual_page_unknown",
            message="Visual response contains a page outside the requested batch",
            page_id=unknown_page_ids[0],
        )
    if conflict_page_ids:
        error = V6BuildError(
            stage="visual",
            code="visual_page_duplicate_conflict",
            message="Visual response contains conflicting decisions for one Story page",
            page_id=conflict_page_ids[0],
        )
        error.repair_page_ids = tuple(conflict_page_ids)
        return canonical, error
    if missing_page_ids and not allow_missing:
        error = V6BuildError(
            stage="visual",
            code="visual_page_coverage_incomplete",
            message="Visual response is missing a decision for a requested Story page",
            page_id=missing_page_ids[0],
        )
        error.repair_page_ids = tuple(missing_page_ids)
        return canonical, error
    return canonical, None


def _order_visual_decisions_for_batch(
    batch: SlideStoryBatchV3,
    decisions: list[SlideVisualDecisionV2],
) -> list[SlideVisualDecisionV2]:
    decisions_by_page = {decision.page_id: decision for decision in decisions}
    return [
        decisions_by_page[page.page_id]
        for page in batch.pages
        if page.page_id in decisions_by_page
    ]


def _visual_repair_targets(
    request: dict[str, Any],
    error: Exception | None,
    decisions: list[SlideVisualDecisionV2] | None = None,
) -> list[dict[str, Any]]:
    failed_page_ids = {
        str(page_id)
        for page_id in getattr(error, "repair_page_ids", ())
        if str(page_id)
    }
    if isinstance(error, V6BuildError) and error.failure.page_id:
        failed_page_ids.add(str(error.failure.page_id))
    pages = [
        page
        for page in request.get("pages") or []
        if isinstance(page, dict)
        and (
            not failed_page_ids
            or str(page.get("page_id") or "") in failed_page_ids
        )
    ]
    decisions_by_page = {
        decision.page_id: decision for decision in (decisions or [])
    }
    targets: list[dict[str, Any]] = []
    for page in pages:
        page_id = str(page.get("page_id") or "")
        decision = decisions_by_page.get(page_id)
        failed_node_id = (
            str(getattr(error, "node_id", "") or "")
            if isinstance(error, V6BuildError)
            else ""
        )
        nodes = (
            decision.visual_payload.get("nodes") or []
            if decision is not None
            else []
        )
        edges = (
            decision.visual_payload.get("edges") or []
            if decision is not None
            else []
        )
        declared_node_ids = [
            str(node.get("node_id") or "")
            for node in nodes
            if isinstance(node, dict) and str(node.get("node_id") or "")
        ]
        declared_node_id_set = set(declared_node_ids)
        invalid_edges = [
            edge for edge in edges
            if not isinstance(edge, dict)
            or str(edge.get("source") or "") not in declared_node_id_set
            or str(edge.get("target") or "") not in declared_node_id_set
        ]
        targets.append({
            "page_id": page_id,
            "required_artifact_kinds": list(page.get("artifact_kinds") or []),
            "allowed_decisions": list(page.get("allowed_decisions") or []),
            "required_source_block_ids": list(page.get("source_block_ids") or []),
            "required_template_layout_id": str(page.get("template_layout_id") or ""),
            "allowed_source_asset_ids": list(page.get("source_asset_ids") or []),
            "source_blocks": list(page.get("source_blocks") or []),
            "failed_node_ids": [failed_node_id] if failed_node_id else [],
            "locked_nodes": [
                node for node in nodes
                if isinstance(node, dict)
                and str(node.get("node_id") or "") != failed_node_id
            ] if failed_node_id else [],
            "declared_node_ids": declared_node_ids,
            "invalid_edges": invalid_edges,
        })
    return targets


def _merge_visual_repair_decisions(
    previous: list[SlideVisualDecisionV2],
    repaired: list[SlideVisualDecisionV2],
    error: Exception | None,
) -> list[SlideVisualDecisionV2]:
    repaired_by_page = {decision.page_id: decision for decision in repaired}
    failed_page_id = (
        str(error.failure.page_id or "")
        if isinstance(error, V6BuildError)
        else ""
    )
    failed_node_id = (
        str(getattr(error, "node_id", "") or "")
        if isinstance(error, V6BuildError)
        else ""
    )
    merged: list[SlideVisualDecisionV2] = []
    observed_page_ids: set[str] = set()
    for prior in previous:
        replacement = repaired_by_page.get(prior.page_id)
        if replacement is None:
            merged.append(prior)
            observed_page_ids.add(prior.page_id)
            continue
        if (
            prior.page_id == failed_page_id
            and failed_node_id
            and prior.decision == "diagram"
            and replacement.decision == "diagram"
        ):
            replacement_nodes = {
                str(node.get("node_id") or ""): node
                for node in replacement.visual_payload.get("nodes") or []
                if isinstance(node, dict)
            }
            prior_payload = dict(prior.visual_payload)
            prior_payload["nodes"] = [
                replacement_nodes[failed_node_id]
                if isinstance(node, dict)
                and str(node.get("node_id") or "") == failed_node_id
                and failed_node_id in replacement_nodes
                else node
                for node in prior.visual_payload.get("nodes") or []
            ]
            merged.append(prior.model_copy(update={
                "visual_payload": prior_payload,
                "provider": replacement.provider or prior.provider,
                "model": replacement.model or prior.model,
                "duration_ms": max(prior.duration_ms, replacement.duration_ms),
                "attempts": max(prior.attempts, replacement.attempts),
            }))
            observed_page_ids.add(prior.page_id)
            continue
        merged.append(replacement)
        observed_page_ids.add(prior.page_id)
    merged.extend(
        decision
        for decision in repaired
        if decision.page_id not in observed_page_ids
    )
    return merged


async def plan_slide_visuals_v2(
    story: SlideStoryPlanV3,
    graph: CoursePresentationGraphV1,
    template: TemplateLayoutPackContractV1,
    *,
    ai_planner: Planner | None,
    concurrency: int = 3,
    timeout_seconds: float = 180.0,
    batch_callback: BatchLifecycleCallback | None = None,
    resume_decisions: list[SlideVisualDecisionV2] | None = None,
) -> SlideVisualPlanV2:
    if ai_planner is None:
        raise V6BuildError(
            stage="visual",
            code="visual_ai_required",
            message="V6 requires a visual planning attempt",
            retryable=True,
        )
    limit = max(2, min(4, concurrency))
    semaphore = asyncio.Semaphore(limit)
    units = {unit.teaching_unit_id: unit for unit in graph.units}
    canonical_resumed, resume_contract_error = _classify_visual_batch_decisions(
        list(resume_decisions or []),
        story.pages,
        allow_missing=True,
    )
    if resume_contract_error is not None:
        raise V6BuildError(
            stage="recovery",
            code="v6_recovery_contract_mismatch",
            message=(
                "Saved visual decisions do not match the frozen Story page identity "
                f"contract: {resume_contract_error.failure.code}"
            ),
            retryable=False,
            page_id=resume_contract_error.failure.page_id,
        ) from resume_contract_error
    resumed_by_page = {
        decision.page_id: decision for decision in canonical_resumed
    }

    async def plan_batch(
        batch_index: int,
        batch: SlideStoryBatchV3,
    ) -> list[SlideVisualDecisionV2]:
        batch_id = f"visual-{batch_index + 1}"
        resumed = [
            resumed_by_page[page.page_id]
            for page in batch.pages
            if page.page_id in resumed_by_page
        ]
        if len(resumed) == len(batch.pages):
            await _notify_batch(batch_callback, {
                "phase": "completed",
                "kind": "visual",
                "batch_index": batch_index,
                "batch_id": batch_id,
                "chapter_id": batch.chapter_id,
                "resumed": True,
                "decisions": resumed,
            })
            return resumed
        pending_pages = [
            page for page in batch.pages if page.page_id not in resumed_by_page
        ]
        planning_batch = batch.model_copy(update={"pages": pending_pages})
        await _notify_batch(batch_callback, {
            "phase": "started",
            "kind": "visual",
            "batch_index": batch_index,
            "batch_id": batch_id,
            "chapter_id": batch.chapter_id,
            "resumed": False,
        })
        request = await asyncio.to_thread(
            _visual_request,
            planning_batch,
            graph,
            template,
        )
        started = time.perf_counter()
        attempt_records: list[AIProviderAttemptDiagnosticV1] = []
        reported_provider = ""
        reported_model = ""
        reported_attempts = 1
        planner_invocations = 0
        batch_validation_status = "passed"
        batch_failure_category = ""
        try:
            contract_error: Exception | None = None
            previous_decisions: list[SlideVisualDecisionV2] = []
            for validation_attempt in range(_VISUAL_SEMANTIC_MAX_ATTEMPTS):
                attempt_request = request
                if validation_attempt:
                    repair_targets = _visual_repair_targets(
                        request,
                        contract_error,
                        previous_decisions,
                    )
                    repair_page_ids = {
                        str(target.get("page_id") or "") for target in repair_targets
                    }
                    attempt_request = {
                        **request,
                        "pages": [
                            page for page in request.get("pages") or []
                            if str(page.get("page_id") or "") in repair_page_ids
                        ] or list(request.get("pages") or []),
                        "repair_feedback": {
                            "attempt": validation_attempt + 1,
                            "code": (
                                contract_error.failure.code
                                if isinstance(contract_error, V6BuildError)
                                else "visual_response_contract_invalid"
                            ),
                            "message": str(contract_error or ""),
                            "repair_targets": repair_targets,
                            "instruction": (
                                "Return decisions only for the pages in this repair request. For a "
                                "failed diagram node, keep its node_id, bind it only to supplied "
                                "source_blocks, prefer an extractive short label, preserve every "
                                "locked_node unchanged, and keep exact numbers and code identifiers. "
                                "For a failed diagram edge, replace every invalid_edges item and use "
                                "only declared_node_ids as source and target. "
                                "Choose only an allowed_decision and never invent artifact payloads."
                            ),
                        },
                    }
                    await _notify_batch(batch_callback, {
                        "phase": "started",
                        "kind": "visual",
                        "batch_index": batch_index,
                        "batch_id": batch_id,
                        "chapter_id": batch.chapter_id,
                        "resumed": False,
                        "retry_attempt": validation_attempt,
                    })
                try:
                    async with semaphore:
                        planner_invocations += 1
                        raw = await _invoke(ai_planner, attempt_request, timeout_seconds)
                    attempt_records.extend(_provider_attempts_from(raw))
                    response = _VisualBatchResponse.model_validate(
                        _normalize_visual_batch_response(raw, attempt_request)
                    )
                    _require_ai_planner_provenance(
                        provider=response.provider,
                        model=response.model,
                        stage="visual",
                    )
                    reported_provider = response.provider or reported_provider
                    reported_model = response.model or reported_model
                    reported_attempts = max(
                        reported_attempts,
                        response.attempts + validation_attempt,
                        len(attempt_records),
                        planner_invocations,
                    )
                    if response.schema_version != "slide_visual_batch_response_v2":
                        raise ValueError("Unexpected visual response schema")
                    duration_ms = max(0, round((time.perf_counter() - started) * 1000))
                    response_decisions = [
                        decision.model_copy(
                            update={
                                "provider": decision.provider or response.provider or "shared-ai-pool",
                                "model": decision.model or response.model or "provider-selected",
                                "attempts": max(
                                    decision.attempts,
                                    reported_attempts,
                                ),
                                "duration_ms": max(decision.duration_ms, duration_ms),
                            }
                        )
                        for decision in response.decisions
                    ]
                    attempt_page_ids = {
                        str(page.get("page_id") or "")
                        for page in attempt_request.get("pages") or []
                    }
                    attempt_pages = [
                        page for page in batch.pages
                        if page.page_id in attempt_page_ids
                    ]
                    decisions, collection_error = _classify_visual_batch_decisions(
                        response_decisions,
                        attempt_pages,
                    )
                    if resumed:
                        decisions_by_page = {
                            decision.page_id: decision
                            for decision in [*resumed, *decisions]
                        }
                        decisions = [
                            decisions_by_page[page.page_id]
                            for page in batch.pages
                            if page.page_id in decisions_by_page
                        ]
                    if validation_attempt and previous_decisions:
                        decisions = _merge_visual_repair_decisions(
                            previous_decisions,
                            decisions,
                            contract_error,
                        )
                    decisions = _order_visual_decisions_for_batch(batch, decisions)
                    if collection_error is not None:
                        raise collection_error
                    _validate_visual_batch_candidate(
                        story=story,
                        graph=graph,
                        template=template,
                        batch=batch,
                        decisions=decisions,
                    )
                    break
                except (ValidationError, ValueError, V6BuildError) as error:
                    contract_error = error
                    if "decisions" in locals():
                        previous_decisions = decisions
                    if validation_attempt < _VISUAL_SEMANTIC_MAX_ATTEMPTS - 1:
                        continue
                    raise
            else:  # pragma: no cover - the bounded loop either succeeds or raises
                raise RuntimeError("Visual response repair loop exited unexpectedly")
        except Exception as error:
            attempt_records.extend(_provider_attempts_from(error))
            required_pages = [
                page
                for page in planning_batch.pages
                if page_artifact_kinds(
                    units[page.teaching_unit_id],
                    page.source_block_ids,
                ).intersection(_HARD_VISUAL_ARTIFACTS)
            ]
            required_page_ids = {page.page_id for page in required_pages}
            degraded_soft_failure = False
            first_failure_category = (
                error.failure.code
                if isinstance(error, V6BuildError)
                else _failure_category(error, prefix="visual_ai_batch")[0]
            )
            if isinstance(error, V6BuildError) and previous_decisions:
                fallback_by_page = {
                    decision.page_id: decision
                    for decision in previous_decisions
                }
                fallback_error: V6BuildError = error
                for _ in range(len(batch.pages)):
                    failed_page_id = str(fallback_error.failure.page_id or "")
                    if (
                        not failed_page_id
                        or failed_page_id in required_page_ids
                        or failed_page_id not in fallback_by_page
                    ):
                        break
                    failed_page = next(
                        (
                            page for page in batch.pages
                            if page.page_id == failed_page_id
                        ),
                        None,
                    )
                    if failed_page is None:
                        break
                    fallback_decision = _degraded_text_native_decision(
                        failed_page,
                        units[failed_page.teaching_unit_id],
                        template,
                        reason=first_failure_category,
                        duration_ms=max(
                            0,
                            round((time.perf_counter() - started) * 1000),
                        ),
                    )
                    if fallback_decision is None:
                        break
                    fallback_by_page[failed_page_id] = fallback_decision
                    fallback_decisions = [
                        fallback_by_page[page.page_id]
                        for page in batch.pages
                        if page.page_id in fallback_by_page
                    ]
                    try:
                        _validate_visual_batch_candidate(
                            story=story,
                            graph=graph,
                            template=template,
                            batch=batch,
                            decisions=fallback_decisions,
                        )
                    except V6BuildError as next_error:
                        fallback_error = next_error
                        continue
                    decisions = fallback_decisions
                    batch_validation_status = "degraded"
                    batch_failure_category = first_failure_category
                    degraded_soft_failure = True
                    break
                if not degraded_soft_failure:
                    error = fallback_error
            if required_pages and not degraded_soft_failure:
                failure_category = (
                    error.failure.code
                    if isinstance(error, V6BuildError)
                    else "visual_ai_required_artifact_failed"
                )
                await _notify_batch(batch_callback, {
                    "phase": "failed",
                    "kind": "visual",
                    "batch_index": batch_index,
                    "batch_id": batch_id,
                    "chapter_id": batch.chapter_id,
                    "resumed": False,
                    "diagnostic": _batch_diagnostic(
                        kind="visual",
                        batch_id=batch_id,
                        chapter_id=batch.chapter_id,
                        duration_ms=round((time.perf_counter() - started) * 1000),
                        validation_status="failed",
                        failure_category=failure_category,
                        provider=reported_provider,
                        model=reported_model,
                        attempts=max(reported_attempts, planner_invocations),
                        attempt_records=attempt_records,
                    ),
                })
                if isinstance(error, V6BuildError):
                    raise V6BuildError(
                        stage=error.failure.stage,
                        code=error.failure.code,
                        message=error.failure.message,
                        retryable=True,
                        chapter_id=batch.chapter_id,
                        page_id=error.failure.page_id or required_pages[0].page_id,
                        batch_id=batch_id,
                    ) from error
                raise V6BuildError(
                    stage="visual",
                    code="visual_ai_required_artifact_failed",
                    message=str(error) or "Visual AI failed for a required artifact page",
                    retryable=True,
                    chapter_id=batch.chapter_id,
                    page_id=required_pages[0].page_id,
                    batch_id=batch_id,
                ) from error
            if not degraded_soft_failure:
                category = first_failure_category
                batch_validation_status = "degraded"
                batch_failure_category = category
                fallback_by_page = {
                    decision.page_id: decision for decision in resumed
                }
                duration_ms = max(
                    0,
                    round((time.perf_counter() - started) * 1000),
                )
                for page in planning_batch.pages:
                    fallback_decision = _degraded_text_native_decision(
                        page,
                        units[page.teaching_unit_id],
                        template,
                        reason=category,
                        duration_ms=duration_ms,
                    )
                    if fallback_decision is None:
                        if isinstance(error, V6BuildError):
                            raise error
                        raise V6BuildError(
                            stage="visual",
                            code=category,
                            message=(
                                "Visual AI failed and no source-safe text layout "
                                "was available"
                            ),
                            retryable=True,
                            chapter_id=batch.chapter_id,
                            page_id=page.page_id,
                            batch_id=batch_id,
                        ) from error
                    fallback_by_page[page.page_id] = fallback_decision
                decisions = [
                    fallback_by_page[page.page_id]
                    for page in batch.pages
                    if page.page_id in fallback_by_page
                ]
        await _notify_batch(batch_callback, {
            "phase": "completed",
            "kind": "visual",
            "batch_index": batch_index,
            "batch_id": batch_id,
            "chapter_id": batch.chapter_id,
            "resumed": False,
            "decisions": decisions,
            "diagnostic": _batch_diagnostic(
                kind="visual",
                batch_id=batch_id,
                chapter_id=batch.chapter_id,
                duration_ms=round((time.perf_counter() - started) * 1000),
                validation_status=batch_validation_status,
                failure_category=batch_failure_category,
                provider=reported_provider,
                model=reported_model,
                attempts=max(reported_attempts, planner_invocations),
                attempt_records=attempt_records,
            ),
        })
        return decisions

    nested = await asyncio.gather(*(
        plan_batch(index, batch) for index, batch in enumerate(story.batches)
    ))
    plan = SlideVisualPlanV2(
        source_document_revision=graph.source_document_revision,
        template_digest=template.template_digest,
        decisions=[decision for group in nested for decision in group],
    )
    validate_slide_visual_plan_v2(plan, story, graph, template)
    return plan


async def repair_slide_visuals_v2(
    story: SlideStoryPlanV3,
    graph: CoursePresentationGraphV1,
    template: TemplateLayoutPackContractV1,
    prior_plan: SlideVisualPlanV2,
    *,
    ai_planner: Planner | None,
    target_page_ids: list[str] | None = None,
    concurrency: int = 3,
    timeout_seconds: float = 180.0,
    batch_callback: BatchLifecycleCallback | None = None,
) -> SlideVisualPlanV2:
    """Replan degraded visual decisions without rebuilding story or healthy pages.

    The function is intentionally pure with respect to ``prior_plan``: a failed
    retry raises before a replacement plan is returned, so callers can keep the
    currently published V6 revision unchanged.
    """

    validate_slide_visual_plan_v2(prior_plan, story, graph, template)
    story_page_ids = {page.page_id for page in story.pages}
    degraded_page_ids = {
        decision.page_id for decision in prior_plan.decisions if decision.degraded
    }
    requested_page_ids = list(dict.fromkeys(target_page_ids or degraded_page_ids))
    requested_set = set(requested_page_ids)
    unknown_page_ids = requested_set - story_page_ids
    if unknown_page_ids:
        page_id = sorted(unknown_page_ids)[0]
        raise V6BuildError(
            stage="visual_repair",
            code="visual_repair_page_unknown",
            message="Visual repair can target only pages in the frozen V6 story plan",
            retryable=False,
            page_id=page_id,
        )
    healthy_page_ids = requested_set - degraded_page_ids
    if healthy_page_ids:
        page_id = sorted(healthy_page_ids)[0]
        raise V6BuildError(
            stage="visual_repair",
            code="visual_repair_target_not_degraded",
            message="Visual repair cannot replace a healthy published decision",
            retryable=False,
            page_id=page_id,
        )
    if not requested_set:
        return prior_plan

    repair_batches = []
    for batch in story.batches:
        pages = [page for page in batch.pages if page.page_id in requested_set]
        if pages:
            repair_batches.append(batch.model_copy(update={"pages": pages}))
    repair_story = story.model_copy(update={"batches": repair_batches})
    repaired_subset = await plan_slide_visuals_v2(
        repair_story,
        graph,
        template,
        ai_planner=ai_planner,
        concurrency=concurrency,
        timeout_seconds=timeout_seconds,
        batch_callback=batch_callback,
    )
    repaired_by_page = {
        decision.page_id: decision for decision in repaired_subset.decisions
    }
    incomplete = [
        page_id
        for page_id in requested_page_ids
        if page_id not in repaired_by_page or repaired_by_page[page_id].degraded
    ]
    if incomplete:
        page_id = incomplete[0]
        failed_decision = repaired_by_page.get(page_id)
        reason = (
            failed_decision.degradation_reason
            if failed_decision is not None
            else "visual_repair_page_missing"
        )
        raise V6BuildError(
            stage="visual_repair",
            code="visual_repair_incomplete",
            message=f"Visual repair did not produce a publishable decision: {reason}",
            retryable=True,
            page_id=page_id,
        )

    repaired_plan = SlideVisualPlanV2(
        source_document_revision=prior_plan.source_document_revision,
        template_digest=prior_plan.template_digest,
        decisions=[
            repaired_by_page.get(decision.page_id, decision)
            for decision in prior_plan.decisions
        ],
    )
    validate_slide_visual_plan_v2(repaired_plan, story, graph, template)
    return repaired_plan


def _deterministic_safe_partition_story_response(
    request: dict[str, Any],
) -> dict[str, Any]:
    """Compile a classroom-dense, source-bound story when planning is unavailable.

    This path makes no semantic planning claim: it selects one complete
    template-safe partition already compiled by the deterministic engine,
    copies stable block identities and confirmed titles, and leaves visible
    copy materialization to the normal manuscript compiler.  The provider/model
    markers keep the fallback observable and the orchestrator permits it only
    for an explicitly reviewable manuscript, never for direct publication.
    """

    pages: list[dict[str, Any]] = []
    for unit_index, unit in enumerate(request.get("teaching_units") or []):
        if not isinstance(unit, dict):
            continue
        options = [
            item
            for item in unit.get("safe_partition_options") or []
            if isinstance(item, dict) and item.get("pages")
        ]
        if not options:
            raise ValueError("story_safe_partition_unavailable")
        classroom_safe_options = [
            item
            for item in options
            if max(
                (
                    len(page.get("source_block_ids") or [])
                    for page in item.get("pages") or []
                    if isinstance(page, dict)
                ),
                default=0,
            ) <= 3
        ]
        # The fewest-page partition previously packed six complete script
        # blocks onto one canvas.  The compiler then had to split that single
        # story page into five continuations (22 slides for a 45-minute
        # lesson).  Keep the deterministic path classroom-dense: no more than
        # three confirmed script blocks per story page, then choose the
        # smallest complete partition within that bound.
        option = min(
            classroom_safe_options or options,
            key=lambda item: (
                int(item.get("page_count") or len(item.get("pages") or [])),
                str(item.get("partition_id") or ""),
            ),
        )
        blocks = {
            str(item.get("block_id") or ""): item
            for item in unit.get("primary_blocks") or []
            if isinstance(item, dict) and item.get("block_id")
        }
        for local_index, page in enumerate(option.get("pages") or []):
            source_ids = [
                str(item) for item in page.get("source_block_ids") or []
                if str(item)
            ]
            bound = [blocks.get(block_id) or {} for block_id in source_ids]
            title_candidates = [
                str(candidate).strip()
                for block in bound
                for candidate in (
                    [block.get("source_title")]
                    + list(block.get("title_candidates") or [])
                )
                if str(candidate or "").strip()
                and not _generic_teaching_page_title(str(candidate))
            ]
            unit_candidates = [
                str(candidate).strip()
                for candidate in unit.get("title_candidates") or []
                if str(candidate or "").strip()
                and not _generic_teaching_page_title(str(candidate))
            ]
            title = next(
                iter(dict.fromkeys([*title_candidates, *unit_candidates])),
                str(unit.get("section_title") or "教学要点"),
            )
            layout_ids = [
                str(item)
                for item in page.get("template_layout_ids") or []
                if str(item)
            ]
            if not layout_ids:
                raise ValueError("story_safe_partition_layout_unavailable")
            pages.append({
                "page_id": (
                    f"safe-{request.get('chapter_id')}-{unit_index + 1}-"
                    f"{local_index + 1}"
                ),
                "teaching_unit_id": str(unit.get("teaching_unit_id") or ""),
                "template_layout_id": layout_ids[0],
                "title": title,
                "summary": "",
                "source_block_ids": source_ids,
            })
    if not pages:
        raise ValueError("story_safe_partition_pages_unavailable")
    return {
        "schema_version": "slide_story_batch_response_v3",
        "chapter_id": str(request.get("chapter_id") or ""),
        "provider": "codex-structured-fallback",
        "model": "deterministic-safe-partition-v2",
        "attempts": 1,
        "pages": pages,
    }


def _deterministic_source_bound_visual_response(
    request: dict[str, Any],
    *,
    reason: str,
) -> dict[str, Any]:
    """Compile observable, source-bound visual decisions for manuscript review.

    The visual provider does not own slide copy or source artifacts.  When its
    route is unavailable, the request already contains the frozen page/layout
    identity and the exact source-supported decision set.  Choosing from that
    set preserves formulas, code, tables and other native artifacts without
    inventing a diagram.  Every decision remains explicitly degraded so a
    teacher confirmation, rather than an AI-success claim, is the publication
    authority.
    """

    decisions: list[dict[str, Any]] = []
    for page in request.get("pages") or []:
        if not isinstance(page, dict):
            continue
        allowed = [
            str(item) for item in page.get("allowed_decisions") or []
            if str(item)
        ]
        if not allowed:
            raise ValueError("visual_source_bound_decision_unavailable")
        preferred = next(
            (
                item for item in (
                    "text_native",
                    "formula",
                    "code",
                    "table",
                    "data",
                    "source_excerpt",
                    "image",
                    "experiment",
                )
                if item in allowed
            ),
            "",
        )
        if not preferred:
            # A diagram requires provider-authored, source-grounded nodes and
            # edges.  Never fabricate those just to make a failed call green.
            raise ValueError("visual_source_bound_payload_required")
        decision = {
            "page_id": str(page.get("page_id") or ""),
            "decision": preferred,
            "source_block_ids": [
                str(item) for item in page.get("source_block_ids") or []
                if str(item)
            ],
            "resolved_template_layout_id": str(
                page.get("template_layout_id") or ""
            ),
            "provider": "codex-structured-fallback",
            "model": "deterministic-source-bound-visual",
            "degraded": True,
            "degradation_reason": reason,
        }
        if preferred in {"image", "experiment"}:
            decision["source_asset_ids"] = [
                str(item) for item in page.get("source_asset_ids") or []
                if str(item)
            ]
        decisions.append(decision)
    if not decisions:
        raise ValueError("visual_source_bound_pages_unavailable")
    return {
        "schema_version": "slide_visual_batch_response_v2",
        "provider": "codex-structured-fallback",
        "model": "deterministic-source-bound-visual",
        "attempts": 1,
        "decisions": decisions,
    }


def build_ai_base_story_planner_v6() -> Planner:
    provider = AIBase(provider_profile="ppt")

    async def planner(request: dict[str, Any]) -> dict[str, Any]:
        telemetry: list[dict[str, Any]] = []
        try:
            with generation_stage(
                "ppt_story",
                section=str(request.get("chapter_id") or ""),
                purpose="plan_slide_story",
            ):
                response = await provider._call_llm(
                    json.dumps(request, ensure_ascii=False),
                    system_prompt=(
                "Return only slide_story_batch_response_v3 JSON. You are a course-faithful "
                "presentation planner. Use every supplied primary_block_id exactly once, keep "
                "teaching units and prerequisites in order, and use only supplied teaching_unit_id. "
                "Derive each page intent from the roles and artifacts of its bound primary_blocks, "
                "then select a layout from allowed_template_layout_ids_by_page_intent for that intent. "
                "For each teaching unit, choose exactly one complete safe_partition_options entry. "
                "Choose an entry with no more than three primary blocks on any page whenever one is supplied. "
                "Copy each option page's source_block_ids exactly and choose one of that page's listed "
                "template_layout_ids. Do not create "
                "one page per primary block: partition the unit's block IDs across its pages and "
                "bind multiple related blocks to one page when needed. The downstream compiler keeps "
                "the complete teacher script in speaker notes. The canvas is for learners during live "
                "teaching: never copy greetings, teacher moves, waiting cues, narration, or transcript "
                "prose onto slides. Show only the definition, theorem, formula, derivation step, "
                "evidence, worked example, learner task, feedback, boundary, or recap needed at that "
                "moment. Treat each page as one teaching point and use page_intent plus compatible "
                "layouts to choose a real classroom composition, not a generic text page. Prefer "
                "chapter-entry for a lesson objective, formula layouts for equations and derivations, "
                "process layouts for ordered mechanisms, worked-example for a prompt plus reasoning, "
                "practice layouts for tasks and checks, and repair layouts for misconceptions when "
                "those choices are supplied. Titles, "
                "summaries, transitions, facts, numbers, formulas and identifiers must be supported "
                "by that unit's source_text. Reference evidence summaries may guide example choice, "
                "emphasis and layout only; they are supporting context, not a second content source, "
                "and must not introduce visible claims absent from the bound source_text. Copy every "
                "identifier and number exactly from the "
                "allowed_protected_tokens of its bound primary_blocks; never shorten, approximate, "
                "autocorrect or synthesize a protected token. Every page must contain exactly page_id, "
                "teaching_unit_id, template_layout_id, title, summary and source_block_ids at the "
                 "page level; never emit a nested content object. Copy a complete title from candidates "
                 "supplied by the primary_blocks bound to that page, keep it within title_max_chars, "
                 "and never end it with a connector or delimiter. Keep each summary compact and "
                 "screen-worthy; it must express the semantic closure of every source_block_id bound "
                 "to that page without reintroducing teacher speech. Never invent teaching content."
                    ),
                    use_fast_model=False,
                    retry_count=1,
                    max_attempts=3,
                    max_tokens=4096,
                    max_input_tokens=16000,
                    max_input_chars=40000,
                    reject_truncated=True,
                    raise_on_failure=True,
                    json_mode=True,
                    model_role="ppt_story",
                    telemetry_sink=telemetry.append,
                )
        except Exception as error:
            invocation_error = AIPlannerInvocationError(
                error,
                telemetry=telemetry,
            )
            code, _retryable = _failure_category(
                invocation_error,
                prefix="story_ai_batch",
            )
            if code in {
                "story_ai_batch_authentication",
                "story_ai_batch_balance_unavailable",
                "story_ai_batch_rate_limited",
            }:
                try:
                    value = _deterministic_safe_partition_story_response(request)
                except ValueError:
                    raise invocation_error from error
                return _AIPlannerResponse(value, telemetry=telemetry)
            raise invocation_error from error
        value = provider._extract_json(response or "") or {}
        records = _sanitize_provider_attempts(telemetry)
        if records:
            value.setdefault("provider", records[-1].provider)
            value.setdefault("model", records[-1].model)
            value.setdefault("attempts", len(records))
        return _AIPlannerResponse(value, telemetry=telemetry)

    return planner


def build_ai_base_visual_planner_v2() -> Planner:
    provider = AIBase(provider_profile="ppt")

    async def planner(request: dict[str, Any]) -> dict[str, Any]:
        telemetry: list[dict[str, Any]] = []
        try:
            with generation_stage(
                "ppt_visual",
                section=str(request.get("chapter_id") or ""),
                purpose="plan_slide_visuals",
            ):
                prompt = json.dumps(request, ensure_ascii=False)
                system_prompt = (
                "Return only slide_visual_batch_response_v2 JSON with exactly one decision per "
                "page_id and follow response_contract exactly. Use decision, never decision_type. "
                "Use only supplied source_block_ids and template_layout_id values. Preserve "
                "required code, formula, table, data, experiment and source evidence. Choose "
                "each page's decision only from its allowed_decisions. Choose text_native when no "
                "meaningful visual is source-supported. Do not write slide copy "
                "or invent labels, facts, data, code_payload, or other artifact payloads. The compiler "
                "reads code, formulas and tables from frozen source blocks. For diagram decisions "
                "include visual_payload with "
                "two to six source-grounded nodes, source_block_ids per node, and valid edges. Bind "
                "each node only to page source_blocks that support it. Prefer short labels extracted "
                "from those blocks; faithful paraphrases must retain a source term, while numbers and "
                "code identifiers must remain exact. During repair, change only failed_node_ids and "
                "preserve locked_nodes. For "
                "image or experiment decisions choose only supplied source_asset_ids."
                )
                call_options = {
                    "retry_count": 1,
                    "max_attempts": 3,
                    "max_tokens": 3072,
                    "max_input_tokens": 12000,
                    "max_input_chars": 32000,
                    "reject_truncated": True,
                    "raise_on_failure": True,
                    "json_mode": True,
                    "model_role": "ppt_visual",
                    "telemetry_sink": telemetry.append,
                }
                try:
                    response = await provider._call_llm(
                        prompt,
                        system_prompt=system_prompt,
                        use_fast_model=True,
                        **call_options,
                    )
                except (AIProviderRequestError, AIProviderUnavailable):
                    # Fast visual SKUs are volatile marketplace routes.  A
                    # rate-limited or delisted fast pool must be able to use
                    # the already validated smart-model pool before the whole
                    # PPT manuscript fails; this still remains AI planning,
                    # not a deterministic replacement.
                    response = await provider._call_llm(
                        prompt,
                        system_prompt=system_prompt,
                        use_fast_model=False,
                        **call_options,
                    )
        except Exception as error:
            invocation_error = AIPlannerInvocationError(
                error,
                telemetry=telemetry,
            )
            code, _retryable = _failure_category(
                invocation_error,
                prefix="visual_ai_batch",
            )
            if code in {
                "visual_ai_batch_authentication",
                "visual_ai_batch_balance_unavailable",
                "visual_ai_batch_rate_limited",
            }:
                try:
                    value = _deterministic_source_bound_visual_response(
                        request,
                        reason=code,
                    )
                except ValueError:
                    raise invocation_error from error
                return _AIPlannerResponse(value, telemetry=telemetry)
            raise invocation_error from error
        value = provider._extract_json(response or "") or {}
        records = _sanitize_provider_attempts(telemetry)
        if records:
            value.setdefault("provider", records[-1].provider)
            value.setdefault("model", records[-1].model)
            value.setdefault("attempts", len(records))
        return _AIPlannerResponse(value, telemetry=telemetry)

    return planner


__all__ = [
    "AIPlannerInvocationError",
    "build_ai_base_story_planner_v6",
    "build_ai_base_visual_planner_v2",
    "plan_slide_story_v3",
    "plan_slide_visuals_v2",
    "repair_slide_visuals_v2",
]
