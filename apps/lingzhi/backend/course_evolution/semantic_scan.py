"""Validated, resumable impact scans within the existing course-change job."""
from __future__ import annotations

import asyncio
import re
from copy import deepcopy
from typing import Any, Awaitable, Callable

from httpx import ConnectError, ConnectTimeout

from course_document import stable_hash
from course_generation_errors import classify_generation_failure

ScanProgress = Callable[[dict[str, Any], dict[str, Any]], Awaitable[None]]
SCAN_CONTRACT = "teacher_semantic_scan_v2"


class ScanConnectionUnavailable(RuntimeError):
    code = 'provider_unavailable'


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
    source_context_fingerprint: str = "",
    deprioritized_unit_ids: set[str] | None = None,
) -> tuple[list[dict[str, Any]], set[str], set[str], list[dict[str, Any]], int]:
    # Include the complete input, not only revision labels: legacy revisions may
    # remain unchanged when content changes. Never reuse another request/context.
    signature = stable_hash({"contract": SCAN_CONTRACT, "overview": overview,
        "batches": source_context_fingerprint or batches, "instruction": instruction, "revisions": revisions}, prefix="scan-")
    legacy_signature = stable_hash({"contract": SCAN_CONTRACT, "overview": overview,
        "batches": batches, "instruction": instruction, "revisions": revisions}, prefix="scan-")
    saved = {"signature": signature, "results": {}}
    if isinstance(checkpoint, dict) and checkpoint.get("signature") in {signature, legacy_signature}:
        if isinstance(checkpoint.get("results"), dict):
            saved["results"] = deepcopy(checkpoint["results"])
    # Reorder complete request envelopes, not their contents: successful batch
    # keys and legacy checkpoint signatures remain valid. Untouched units get a
    # chance before a fragment which repeatedly failed in the previous run.
    postponed = deprioritized_unit_ids or set()
    batches = sorted(batches, key=lambda batch: any(item["unit_id"] in postponed for item in batch))
    analyses, failures = [], []
    scanned, unscanned = set(), set()
    retried = 0
    detail = {"completed_parts": 0, "total_parts": sum(map(len, batches)),
              "reused_parts": 0, "failed_parts": 0, "deferred_parts": 0}
    isolated: dict[str, Exception] = {}
    consecutive_failed_units: set[str] = set()
    provider_stop: Exception | None = None

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

    async def attempt(items: list[dict[str, Any]], feedback: Exception | None = None) -> tuple[dict[str, Any], bool]:
        reused = cached(items)
        if reused is not None:
            return reused, True
        request_overview = overview
        if isinstance(feedback, ValueError):
            request_overview = {**overview, 'analysis_validation_feedback': {
                'message': safe_failure_message(feedback),
                'allowed_unit_ids': list(dict.fromkeys(i['unit_id'] for i in items)),
                'required_response': 'affected_units must be an array; use only these unit IDs',
            }}
        try:
            result = await analyzer(request_overview, items, instruction)
        except Exception as error:
            cause, visited = error, set()
            while cause is not None and id(cause) not in visited:
                visited.add(id(cause))
                if isinstance(cause, (ConnectError, ConnectTimeout)):
                    # The provider never accepted this request. Repartitioning
                    # course content cannot repair a transport outage.
                    raise ScanConnectionUnavailable('AI 服务暂时无法连接，请稍后补查') from error
                cause = cause.__cause__ or cause.__context__
            raise
        return validate_batch(result, items), False

    async def accept(items: list[dict[str, Any]], result: dict[str, Any], reused: bool) -> None:
        saved["results"][key(items)] = deepcopy(result)
        analyses.append(result)
        scanned.update(item["unit_id"] for item in items)
        detail["completed_parts"] += len(items)
        if reused:
            detail["reused_parts"] += len(items)
        else:
            # A cache hit says nothing about the provider's current health.
            consecutive_failed_units.clear()
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
        detail["retrying_provider"] = True
        await report()
        try:
            return await attempt(items), None
        except Exception as error:  # noqa: BLE001 - caller classifies the final retry
            return None, error
        finally:
            detail.pop("retrying_provider", None)

    async def defer_provider_work(
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
            "failed_unit_ids": [],
        })
        detail["deferred_parts"] += len(items)
        await report()

    async def record_failure(items: list[dict[str, Any]], error: Exception,
                             batch_index: int, part_index: int) -> None:
        nonlocal provider_stop
        ids = list(dict.fromkeys(item["unit_id"] for item in items))
        unscanned.update(ids)
        failure = classify_generation_failure(error)
        failures.append({"batch_index": batch_index, "part_index": part_index,
            "unit_ids": ids, "failed_unit_ids": ids, "error_type": type(error).__name__,
            **failure, "message": safe_failure_message(error),
            "technical_detail": safe_failure_message(error)})
        detail["failed_parts"] += len(items)
        if failure["code"] in {"provider_unavailable", "provider_timeout"} and len(ids) == 1:
            # Repeated fragments of one unit are not independent outage evidence.
            isolated[ids[0]] = error
            consecutive_failed_units.add(ids[0])
            if len(consecutive_failed_units) >= 3:
                provider_stop = error
                detail["provider_recovery_failed"] = True
        await report()

    async def skip_unavailable(items: list[dict[str, Any]], batch_index: int, part_index: int) -> bool:
        # Reuse exact successful envelopes even during an outage. Do not count
        # never-issued requests as failures or lose their pending coverage.
        result = cached(items)
        if result is not None:
            await accept(items, result, True)
            return True
        error = provider_stop or next((isolated[i["unit_id"]] for i in items
                                       if i["unit_id"] in isolated), None)
        if error is None:
            return False
        await defer_provider_work(error, batch_index=batch_index,
            part_index=part_index, items=items)
        return True

    def subdivisions(items: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
        if len(items) > 1:
            midpoint = len(items) // 2
            return [items[:midpoint], items[midpoint:]]
        if not items[0].get('recovery_part') and len(str(items[0].get('content') or '')) > 600:
            text = str(items[0]['content'])
            chunks = [text[i:i+600] for i in range(0, len(text), 550)]
            return [[{**items[0], 'content': chunk, 'recovery_part': i + 1,
                          'recovery_parts': len(chunks)}] for i, chunk in enumerate(chunks)]
        return []

    def has_cached_descendant(items: list[dict[str, Any]]) -> bool:
        return any(cached(child) is not None or has_cached_descendant(child)
                   for child in subdivisions(items))

    async def inspect_part(items: list[dict[str, Any]], batch_index: int, part_index: int,
                           *, refined: bool = False) -> None:
        nonlocal retried
        children = subdivisions(items) if not refined else []
        if cached(items) is None and (has_cached_descendant(items) or
                len(items) > 1 and any(i['unit_id'] in isolated for i in items)):
            if len(items) == 1:
                detail['total_parts'] += len(children) - 1
            for child in children:
                await inspect_part(child, batch_index, part_index, refined=len(items) == 1)
            return
        if await skip_unavailable(items, batch_index, part_index):
            return
        try:
            result, reused = await attempt(items)
        except Exception as caught:
            error = caught
        else:
            await accept(items, result, reused)
            return
        if isinstance(error, ValueError):
            retried += 1
            try:
                result, reused = await attempt(items, error)
            except Exception as caught:
                error = caught
            else:
                await accept(items, result, reused)
                return
        if len(items) > 1 and classify_generation_failure(error)['code'] in {'provider_timeout', 'provider_unavailable'}:
            retried += 1
            for item in items:
                await inspect_part([item], batch_index, part_index)
            return
        if classify_generation_failure(error)["code"] == "provider_unavailable":
            retried += 1
            recovered, retry_error = await retry_after_provider_recovery(items)
            if recovered is not None:
                await accept(items, *recovered)
                return
            error = retry_error or error
        if classify_generation_failure(error)["code"] == "provider_timeout" and children:
            detail["total_parts"] += len(children) - 1
            retried += 1
            for child in children:
                await inspect_part(child, batch_index, part_index, refined=True)
            return
        await record_failure(items, error, batch_index, part_index)

    await report()
    for batch_index, batch in enumerate(batches):
        detail["batch_index"] = batch_index + 1
        detail["total_batches"] = len(batches)
        await report()
        # Keep original envelopes for checkpoint compatibility. Split mixed
        # batches when one unit is isolated so its healthy neighbours still run.
        result = cached(batch)
        if result is not None:
            await accept(batch, result, True)
            continue
        midpoint = max(1, len(batch) // 2)
        parts = [batch] if len(batch) == 1 else [batch[:midpoint], batch[midpoint:]]
        split_cached = has_cached_descendant(batch)
        if provider_stop or any(item["unit_id"] in isolated for item in batch):
            # Preserve successful descendants before isolating uncached leaves.
            for part_index, part in enumerate(parts):
                await inspect_part(part, batch_index, part_index)
            continue
        if len(batch) == 1:
            await inspect_part(batch, batch_index, 0)
            continue
        if not split_cached:
            try:
                result, reused = await attempt(batch)
            except Exception as error:
                retried += 1
                # Test different inputs before concluding that a failed shared
                # request proves a provider-wide outage.
                if classify_generation_failure(error)["code"] == "provider_unavailable":
                    parts = [[item] for item in batch]
            else:
                await accept(batch, result, reused)
                continue
        for part_index, part in enumerate(parts):
            await inspect_part(part, batch_index, part_index)
    scanned.difference_update(unscanned)
    return analyses, scanned, unscanned, failures, retried
