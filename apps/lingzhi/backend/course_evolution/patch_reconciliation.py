"""One bounded, whole-source repair of unusable or duplicate fragment proposals."""
import asyncio
from collections.abc import Awaitable, Callable
from copy import deepcopy
from typing import Any

from .content_patches import compile_patches, readable_body
from .semantic_scan import validate_batch


async def reconcile_fragment_patches(analysis: dict[str, Any], context: Any,
                                     analyzer: Callable[..., Awaitable[Any]] | None, instruction: str,
                                     *, eligible_ids: set[str], on_progress: Callable[..., Awaitable[None]] | None = None) -> None:
    if analyzer is None or analysis.get('analysis_mode') == 'deterministic_exact_replace':
        return
    units = {u.unit_id: u for u in context.units}
    # This is part of the original task, not another retry loop. A provider
    # outage must not turn the completed scan into an unbounded repair job.
    deadline = asyncio.get_running_loop().time() + 90
    for item in analysis.get('affected_units') or []:
        unit = units.get(item.get('unit_id'))
        if not unit or unit.unit_id not in eligible_ids or unit.asset_type != 'course_content':
            continue
        payload = (unit.metadata.get('course_block') or {}).get('payload') or {}
        patches = item.get('content_patches') or []
        if not patches:
            continue
        try:
            _, _, warnings = compile_patches(payload, patches)
            issues = [w for w in warnings if '重复设置' in w]
        except ValueError as error:
            issues = [str(error)]
        if not issues:
            continue
        body = readable_body({k: v for k, v in payload.items() if isinstance(v, str)})
        field = next((k for k in ('markdown', 'text', 'content') if payload.get(k) == body), '')
        remaining = deadline - asyncio.get_running_loop().time()
        if not field or len(body) > 24_000 or remaining <= 0:
            continue
        candidate = {'unit_id': unit.unit_id, 'asset_type': unit.asset_type,
                     'title': unit.title, 'block_title': payload.get('title', ''),
                     'content_field': field, 'content': body, 'part': 1, 'parts': 1,
                     'editable_fields': {field: body}}
        if on_progress:
            await on_progress(unit.title)
        try:
            async with asyncio.timeout(remaining):
                result = await analyzer({'patch_repair': {'issues': issues, 'proposals': patches}},
                                        [candidate], instruction)
            result = validate_batch(result, [candidate])
            repaired = next((r for r in result['affected_units'] if r['unit_id'] == unit.unit_id), {})
            replacement = repaired.get('content_patches') or []
            if not replacement or any(p.get('field') != field for p in replacement):
                continue
            _, applied, warnings = compile_patches(payload, replacement)
            if not applied or any('重复设置' in w for w in warnings):
                continue
        except (ValueError, TypeError):
            continue
        except Exception:
            # Preserve the analysis and its actionable validation error. Do not
            # misclassify a repair transport failure as failed scan coverage.
            break
        item['content_patches'] = deepcopy(replacement)
        item['patch_reconciled'] = True
