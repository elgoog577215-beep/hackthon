"""Short navigation names cached by frozen meaning, independently of local keys."""
from copy import deepcopy
from collections import Counter
import json

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


async def resolve_name_collisions(pipeline, points, names, request):
    labels = {p['key']: p['_registered_point']['name'] if p.get('_registered_point') else names[p['key']]['name'] for p in points}
    counts = Counter(labels.values())
    targets = [p for p in points if counts[labels[p['key']]] > 1 and not p.get('_registered_point')]
    if not targets:
        return deepcopy(names)
    keys = {p['key'] for p in targets}
    frozen = {key: name for key, name in labels.items() if key not in keys}
    instruction, payload_text = names_prompt(targets).split('\nINPUT_JSON:\n', 1)
    payload = json.loads(payload_text)
    payload.update(previous_names={key: labels[key] for key in keys}, frozen_names=frozen)
    instruction = ('这些不同知识点暂用了同名标题。只为points中的知识生成能相互区分的短名称，'
                   '读完整知识与条件后说明必要范围；不能只添加序号，不能与frozen_names重复，不能改正文或合并知识。' + instruction)
    state = pipeline.setdefault('name_disambiguation', {'contract': 'knowledge_name_disambiguation_v1', 'requests': {}})
    signature = stable_hash(payload, prefix='kndis_')
    record = state['requests'].setdefault(signature, {})
    def compile_result(value):
        result = parse_names(value, targets)
        result_names = [row['name'].strip() for row in result.values()]
        if len(set(result_names)) != len(result_names) or set(result_names) & set(frozen.values()):
            raise ValueError('短名称仍有同名，须按完整知识与条件区分，不得改动其他名称')
        return result
    try:
        changed = await request(instruction + '\nINPUT_JSON:\n' + json.dumps(payload, ensure_ascii=False, separators=(',', ':')),
                                'candidate_names', record, compile_result)
    except ValueError:
        state['review_required'] = True  # Preserve the existing explicit review path after bounded attempts.
        return deepcopy(names)
    state['review_required'] = False
    for point in targets:
        pipeline.setdefault('short_names', {}).setdefault('labels', {})[meaning_key(point)] = deepcopy(changed[point['key']])
    return {**deepcopy(names), **changed}
