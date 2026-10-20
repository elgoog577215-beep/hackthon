"""Explicit identity decisions; titles and material wording never determine identity."""
from copy import deepcopy

from knowledge_registry_contract import FIELDS, validate_point


def existing_catalog(raw):
    result = []
    seen = set()
    for point in (raw.get('course_knowledge_base') or {}).get('knowledge_points', []):
        if not point.get('knowledge_id') or not point.get('statement'):
            continue
        seen.add(point['knowledge_id'])
        result.append({**deepcopy(point), 'key': f'E{len(result)+1}', '_registered_point': deepcopy(point)})
    if raw.get('knowledge_library_binding'):
        from subject_knowledge import resolve_subject_library
        library = resolve_subject_library(raw)
        for point in library.get('nodes', []):
            kid = point.get('knowledge_id') or point.get('id')
            if kid in seen or not point.get('statement') or not kid:
                continue
            seen.add(kid)
            record = {**deepcopy(point), 'knowledge_id': kid}
            result.append({**record, 'key': f'E{len(result)+1}', '_registered_point': record})
    return result


def apply_decisions(candidates, catalog, decisions):
    by_key = {p['key']: p for p in candidates}
    existing = {p['key']: p for p in catalog}
    if len(by_key) != len(candidates) or not isinstance(decisions, dict) or set(decisions) != set(by_key):
        raise ValueError('身份决定必须恰好覆盖全部候选')
    canonical = {}
    issues, records = [], []
    for key, decision in decisions.items():
        if not isinstance(decision, dict):
            raise ValueError(key + '：身份决定必须为对象')
        action = decision.get('action')
        fields = {'action', 'reason'}
        if action == 'replace':
            fields.add('points')
        elif action in {'merge', 'reuse'}:
            fields.update(('target', 'same_claim', 'same_scope', 'same_symbols'))
        elif action not in {'keep', 'uncertain', 'context'}:
            raise ValueError(key + '：未知身份动作')
        if set(decision) != fields or not isinstance(decision['reason'], str) or not decision['reason'].strip():
            raise ValueError(key + '：动作与字段不一致')
        if action in {'merge', 'reuse'}:
            if not all(decision[field] is True for field in ('same_claim', 'same_scope', 'same_symbols')):
                raise ValueError(key + '：命题、范围及符号含义须明确一致，否则保留待确认')
            continue
        original = by_key[key]
        if action == 'context':
            records.append({'candidate_key': key, 'decision': deepcopy(decision), 'original': deepcopy(original)})
            canonical[key] = []
            continue
        rows = decision.get('points', [{k: deepcopy(original[k]) for k in FIELDS}])
        if not isinstance(rows, list) or not 1 <= len(rows) <= 8:
            raise ValueError(key + '：replace必须给非空完整知识点')
        canonical[key] = []
        for i, row in enumerate(rows, 1):
            point = {**validate_point(row), 'key': key if len(rows) == 1 else f'{key}_{i}',
                     'input_material_keys': deepcopy(original['input_material_keys']),
                     'identity_members': [deepcopy(original)], 'identity_decisions': [deepcopy(decision)]}
            if action == 'uncertain':
                point['review_pending'] = True
                issues.append({'code': 'knowledge_identity_pending', 'severity': 'blocking',
                               'point_key': point['key'], 'message': decision['reason']})
            canonical[key].append(point)
    reused = {}
    for key, decision in decisions.items():
        action = decision['action']
        if action not in {'merge', 'reuse'}:
            continue
        target = decision['target']
        if action == 'merge':
            if (target == key or target not in canonical or len(canonical[target]) != 1
                    or decisions[target]['action'] not in {'keep', 'replace'}):
                raise ValueError(key + '：合并不能成链、环或指向空/待确认/拆分目标')
            point = canonical[target][0]
        else:
            if target not in existing:
                raise ValueError(key + '：复用了未知知识')
            if target not in reused:
                old = existing[target]
                point = {**deepcopy(old), 'key': key, 'input_material_keys': [], 'identity_members': [],
                         'identity_decisions': [], '_registered_point': deepcopy(old.get('_registered_point', old))}
                for field in FIELDS[2:]:
                    point.setdefault(field, [])
                point.setdefault('knowledge_type', 'rule')
                reused[target] = point
            point = reused[target]
        original = by_key[key]
        point['input_material_keys'] = list(dict.fromkeys([*point['input_material_keys'], *original['input_material_keys']]))
        point['identity_members'].append(deepcopy(original))
        point['identity_decisions'].append(deepcopy(decision))
    points = [point for rows in canonical.values() for point in rows] + list(reused.values())
    if not points:
        raise ValueError('本讲没有可保存的知识候选')
    if len(points) > 160:
        raise ValueError('本讲候选超过160点预算')
    return {'points': points, 'issues': issues, 'context_records': records}
