"""Validated, resumable impact scans within the existing course-change job."""
from __future__ import annotations

import asyncio
import logging
import re
from copy import deepcopy
from typing import Any, Awaitable, Callable

from course_document import stable_hash
from course_generation_errors import classify_generation_failure

ScanProgress = Callable[[dict[str, Any], dict[str, Any]], Awaitable[None]]
SCAN_CONTRACT = "teacher_semantic_scan_v1"
logger = logging.getLogger(__name__)


def validate_batch(result: Any, items: list[dict[str, Any]]) -> dict[str, Any]:
    """Normalize optional nulls; reject unusable shapes before marking coverage."""
    if not isinstance(result, dict) or not isinstance(result.get("affected_units"), list):
        raise ValueError("影响分析必须返回 affected_units 数组")
    result = deepcopy(result)
    for field in ("signal_kind", "interpreted_goal"):
        if result.get(field) is not None and not isinstance(result[field], str):
            raise ValueError(f"影响分析 {field} 必须是文本")
    known = {item["unit_id"] for item in items}
    for item in result["affected_units"]:
        if not isinstance(item, dict) or item.get("unit_id") not in known:
            raise ValueError("影响分析引用了本批次之外的内容")
        patches = item.get("content_patches")
        if patches is None:
            patches = []
        if not isinstance(patches, list) or any(not isinstance(p, dict) for p in patches):
            raise ValueError("影响分析 content_patches 必须是修改项数组")
        item["content_patches"] = patches
    for field in ("hard_constraints", "soft_preferences", "protected_requirements", "assumptions",
                  "blocking_questions", "clarifications"):
        value = result.get(field)
        if value is None:
            value = []
        if not isinstance(value, list):
            raise ValueError(f"影响分析 {field} 必须是数组")
        result[field] = value
    for question in [*result["clarifications"], *result["blocking_questions"]]:
        if isinstance(question, dict):
            options = question.get("options")
            if options is not None and not isinstance(options, list):
                raise ValueError("澄清问题 options 必须是数组")
    structure = result.get("structure")
    if structure is None:
        structure = {}
    if not isinstance(structure, dict):
        raise ValueError("影响分析 structure 必须是对象")
    if structure.get("required") is not None and not isinstance(structure["required"], bool):
        raise ValueError("课程结构 required 必须是布尔值")
    for field in ("affected_node_ids", "retire_node_ids", "proposed_outline"):
        value = structure.get(field)
        if value is None:
            value = []
        if not isinstance(value, list):
            raise ValueError(f"课程结构 {field} 必须是数组")
        structure[field] = value
    for node in structure["proposed_outline"]:
        if not isinstance(node, dict) or not isinstance(node.get("source_node_ids", []), list):
            raise ValueError("课程结构必须包含有效的讲次与来源数组")
    result["structure"] = structure
    return result


def safe_failure_message(error: Exception) -> str:
    message = " ".join(str(error).split())[:400]
    message = re.sub(r"(?i)\b(api[_-]?key|authorization|token)\b\s*[:=]\s*\S+", r"\1=<redacted>", message)
    return re.sub(r"(?i)\bbearer\s+\S+", "Bearer <redacted>", message)


async def scan_batches(
    *, overview: dict[str, Any], batches: list[list[dict[str, Any]]], instruction: str,
    revisions: dict[str, str], analyzer: Callable[..., Awaitable[Any]],
    checkpoint: dict[str, Any] | None = None, on_progress: ScanProgress | None = None,
    provider_recovery_delay_seconds: float = 31.0,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> tuple[list[dict[str, Any]], set[str], set[str], list[dict[str, Any]], int]:
    # Include the complete input, not only revision labels: legacy revisions may
    # remain unchanged when content changes. Never reuse another request/context.
    signature = stable_hash({"contract": SCAN_CONTRACT, "overview": overview,
        "batches": batches, "instruction": instruction, "revisions": revisions}, prefix="scan-")
    saved = {"signature": signature, "results": {}}
    if isinstance(checkpoint, dict) and checkpoint.get("signature") == signature:
        if isinstance(checkpoint.get("results"), dict):
            saved["results"] = deepcopy(checkpoint["results"])
    analyses, failures = [], []
    scanned, unscanned = set(), set()
    retried = 0
    detail = {"completed_parts": 0, "total_parts": sum(map(len, batches)),
              "reused_parts": 0, "failed_parts": 0}

    async def report() -> None:
        if on_progress:
            await on_progress(deepcopy(detail), deepcopy(saved))

    def key(items: list[dict[str, Any]]) -> str:
        return stable_hash(items, prefix="batch-")

    def cached(items: list[dict[str, Any]]) -> dict[str, Any] | None:
        value = saved["results"].get(key(items))
        if value is None:
            return None
        try:
            return validate_batch(value, items)
        except (ValueError, TypeError):
            saved["results"].pop(key(items), None)
            return None

    async def attempt(items: list[dict[str, Any]]) -> tuple[dict[str, Any], bool]:
        reused = cached(items)
        if reused is not None:
            return reused, True
        return validate_batch(await analyzer(overview, items, instruction), items), False

    async def accept(items: list[dict[str, Any]], result: dict[str, Any], reused: bool) -> None:
        saved["results"][key(items)] = deepcopy(result)
        analyses.append(result)
        scanned.update(item["unit_id"] for item in items)
        detail["completed_parts"] += len(items)
        if reused:
            detail["reused_parts"] += len(items)
        # Persistence errors must propagate; they are not model failures and
        # must never trigger another model call or discard a successful result.
        await report()

    async def retry_after_provider_recovery(
        items: list[dict[str, Any]],
    ) -> tuple[tuple[dict[str, Any], bool] | None, Exception | None]:
        detail["waiting_for_provider"] = True
        detail["retry_after_seconds"] = provider_recovery_delay_seconds
        await report()
        await sleep(provider_recovery_delay_seconds)
        detail.pop("waiting_for_provider", None)
        detail.pop("retry_after_seconds", None)
        try:
            return await attempt(items), None
        except Exception as error:  # noqa: BLE001 - caller classifies the final retry
            return None, error

    async def defer_remaining_provider_work(
        error: Exception,
        *,
        batch_index: int,
        part_index: int,
        items: list[dict[str, Any]],
    ) -> None:
        ids = list(dict.fromkeys(str(item["unit_id"]) for item in items))
        unscanned.update(ids)
        failure = classify_generation_failure(error)
        failures.append({
            "batch_index": batch_index,
            "part_index": part_index,
            "unit_ids": ids,
            "error_type": type(error).__name__,
            **failure,
            "message": safe_failure_message(error),
            "technical_detail": safe_failure_message(error),
            "deferred_parts": len(items),
        })
        detail["failed_parts"] += len(items)
        detail["provider_recovery_failed"] = True
        await report()

    await report()
    abort_scan = False
    for batch_index, batch in enumerate(batches):
        detail["batch_index"] = batch_index + 1
        detail["total_batches"] = len(batches)
        await report()
        midpoint = max(1, len(batch) // 2)
        parts = [batch] if len(batch) == 1 else [batch[:midpoint], batch[midpoint:]]
        # A previous split may have succeeded halfway. Resume its failed half
        # without reissuing the original parent request.
        split_cached = len(parts) > 1 and any(cached(part) is not None for part in parts)
        if not split_cached or cached(batch) is not None:
            try:
                result, reused = await attempt(batch)
            except Exception as error:
                retried += 1
                if classify_generation_failure(error).get("code") == "provider_unavailable":
                    recovered, retry_error = await retry_after_provider_recovery(batch)
                    if recovered is not None:
                        await accept(batch, *recovered)
                        continue
                    if (
                        retry_error is not None
                        and classify_generation_failure(retry_error).get("code")
                        == "provider_unavailable"
                    ):
                        remaining = [
                            item
                            for pending in batches[batch_index:]
                            for item in pending
                        ]
                        await defer_remaining_provider_work(
                            retry_error,
                            batch_index=batch_index,
                            part_index=0,
                            items=remaining,
                        )
                        abort_scan = True
                        break
            else:
                await accept(batch, result, reused)
                continue
        if abort_scan:
            break
        for part_index, part in enumerate(parts):
            try:
                result, reused = await attempt(part)
            except Exception as error:
                if classify_generation_failure(error).get("code") == "provider_unavailable":
                    recovered, retry_error = await retry_after_provider_recovery(part)
                    if recovered is not None:
                        await accept(part, *recovered)
                        continue
                    if (
                        retry_error is not None
                        and classify_generation_failure(retry_error).get("code")
                        == "provider_unavailable"
                    ):
                        remaining = [
                            *[
                                item
                                for pending in parts[part_index:]
                                for item in pending
                            ],
                            *[
                                item
                                for pending in batches[batch_index + 1:]
                                for item in pending
                            ],
                        ]
                        await defer_remaining_provider_work(
                            retry_error,
                            batch_index=batch_index,
                            part_index=part_index,
                            items=remaining,
                        )
                        abort_scan = True
                        break
                    if retry_error is not None:
                        error = retry_error
                logger.warning("Whole-course scan batch=%s part=%s failed", batch_index, part_index, exc_info=True)
                ids = [item["unit_id"] for item in part]
                unscanned.update(ids)
                failure = classify_generation_failure(error)
                failures.append({"batch_index": batch_index, "part_index": part_index,
                    "unit_ids": ids, "error_type": type(error).__name__,
                    **failure, "message": safe_failure_message(error),
                    "technical_detail": safe_failure_message(error)})
                detail["failed_parts"] += len(part)
                await report()
            else:
                await accept(part, result, reused)
        if abort_scan:
            break
    scanned.difference_update(unscanned)
    return analyses, scanned, unscanned, failures, retried
