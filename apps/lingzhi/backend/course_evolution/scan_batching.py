"""Pack complete scan fragments against the same input budget as inference."""
from __future__ import annotations

import json
from typing import Any

from .scan_prompt import SCAN_INPUT_TOKEN_LIMIT, SCAN_SYSTEM_PROMPT, build_scan_prompt

TOKEN_BATCH_POLICY = 'prompt_budget_v1'
LEGACY_BATCH_POLICY = 'legacy_chars_v1'


def pack_scan_batches(
    fragments: list[dict[str, Any]], *, overview: dict[str, Any], instruction: str,
    legacy: bool = False,
) -> list[list[dict[str, Any]]]:
    # Use the inference gate's conservative mixed-language counter. Count the
    # complete prompt, including the outline, metadata and editing instructions.
    from ai_base import AIBase

    batches: list[list[dict[str, Any]]] = []
    batch: list[dict[str, Any]] = []
    for fragment in fragments:
        proposed = [*batch, fragment]
        if legacy:
            full = (len(proposed) > 12
                    or sum(len(json.dumps(item, ensure_ascii=False)) for item in proposed) > 4500
                    or sum(len(item['content']) for item in proposed) > 2400)
        else:
            full = (len(proposed) > 8 or AIBase.estimate_request_tokens(
                build_scan_prompt(overview, proposed, instruction), SCAN_SYSTEM_PROMPT,
            ) > SCAN_INPUT_TOKEN_LIMIT)
        if batch and full:
            batches.append(batch)
            batch = []
        batch.append(fragment)
    if batch:
        batches.append(batch)
    return batches
