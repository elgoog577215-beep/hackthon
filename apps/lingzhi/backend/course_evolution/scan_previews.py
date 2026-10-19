"""Bounded read-only diffs compiled with the final plan's exact patch validator."""
from copy import deepcopy
from .content_patches import compile_patches


def content_previews(context, checkpoint, complete_ids):
    by_id = {u.unit_id:u for u in context.units if u.asset_type == 'course_content' and u.unit_id in complete_ids}
    patches = {}
    for result in (checkpoint.get('results') or {}).values():
        for item in result.get('affected_units') or []:
            uid = item.get('unit_id')
            if uid in by_id:
                patches.setdefault(uid, []).extend(deepcopy(item.get('content_patches') or []))
    previews = {}
    for uid, edits in patches.items():
        if not edits:
            continue
        unit = by_id[uid]
        payload = (unit.metadata.get('course_block') or {}).get('payload')
        if not isinstance(payload, dict):
            continue
        try:
            _, applied, _ = compile_patches(payload, edits)
        except (ValueError, TypeError, KeyError):
            # Overlapping fragments must await the existing reconciliation step.
            continue
        if not applied:
            continue
        change = applied[0]
        before, after = str(change.get('before') or ''), str(change.get('after') or '')
        previews[uid] = {'before':before[:900], 'after':after[:900],
                         'truncated':len(before)>900 or len(after)>900 or len(applied)>1,
                         'change_count':len(applied)}
        if len(previews) == 8:
            break
    return previews
