"""Short navigation names cached by frozen meaning, independently of local keys."""
from copy import deepcopy

from course_document import stable_hash
from knowledge_registry_contract import FIELDS, names_prompt, parse_names

CONTRACT = 'knowledge_preview_names_v1'


def meaning_key(point):
    return stable_hash({key: point.get(key) for key in FIELDS}, prefix='kname_')


def cached_name(pipeline, point):
    return pipeline.get('short_names', {}).get('labels', {}).get(meaning_key(point))


async def ensure_names(pipeline, points, request):
    state = pipeline.setdefault('short_names', {'contract': CONTRACT, 'labels': {}, 'requests': {}})
    missing = {}
    for point in points:
        if not point.get('_registered_point') and not cached_name(pipeline, point):
            missing.setdefault(meaning_key(point), point)
    pending = list(missing.values())
    for start in range(0, len(pending), 12):
        batch = pending[start:start + 12]
        signature = stable_hash([{'key': p['key'], 'meaning': meaning_key(p)} for p in batch], prefix='knreq_')
        record = state['requests'].setdefault(signature, {})
        names = await request(names_prompt(batch), 'candidate_names', record, lambda value: parse_names(value, batch))
        for point in batch:
            state['labels'][meaning_key(point)] = deepcopy(names[point['key']])
    return {point['key']: deepcopy(cached_name(pipeline, point)) for point in points
            if not point.get('_registered_point')}
