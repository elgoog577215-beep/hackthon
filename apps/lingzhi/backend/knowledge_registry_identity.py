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
        elif action in {'match', 'merge', 'reuse'}:
            fields.update(('target', 'same_claim', 'same_scope', 'same_symbols'))
        elif action == 'covered':
            fields.update(('parts', 'complete_coverage', 'adds_knowledge', 'same_scope'))
        elif action not in {'keep', 'uncertain', 'context'}:
            raise ValueError(key + '：未知身份动作')
        if set(decision) != fields or not isinstance(decision['reason'], str) or not decision['reason'].strip():
            raise ValueError(key + '：动作与字段不一致')
        if action in {'match', 'merge', 'reuse'}:
            if not all(decision[field] is True for field in ('same_claim', 'same_scope', 'same_symbols')):
                raise ValueError(key + '：命题、范围及符号含义须明确一致，否则保留待确认')
            continue
        if action == 'covered':
            if decision['complete_coverage'] is not True or decision['adds_knowledge'] is not False or decision['same_scope'] is not True:
                raise ValueError(key + '：组合重复须完全覆盖、不新增知识且适用范围相同')
            parts = decision['parts']
            if (not isinstance(parts, list) or not 2 <= len(parts) <= 8
                    or any(not isinstance(p, dict) or set(p) != {'target', 'claim'}
                           or not isinstance(p['target'], str) or not isinstance(p['claim'], str) or not p['claim'].strip() for p in parts)
                    or len({p['target'] for p in parts}) != len(parts)):
                raise ValueError(key + '：covered至少需要两个不同目标；同一知识的单目标对应请用match')
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
            for field in ('coverage_unit_ids','profile_focus','check_intents'):
                if field in original:
                    point[field]=deepcopy(original[field])
            if action == 'uncertain':
                point['review_pending'] = True
                issues.append({'code': 'knowledge_identity_pending', 'severity': 'blocking',
                               'point_key': point['key'], 'message': decision['reason']})
            canonical[key].append(point)
    reused = {}
    def registered(target, key):
        if target not in existing:
            raise ValueError(key + '：复用了未知知识')
        if target not in reused:
            old = existing[target]
            point = {**deepcopy(old), 'key': key, 'input_material_keys': [], 'identity_members': [],
                     'identity_decisions': [], '_registered_point': deepcopy(old.get('_registered_point', old))}
            # Coverage IDs belong to this generation, not the registered semantic identity.
            for field in ('coverage_unit_ids','profile_focus','check_intents'):
                point.pop(field,None)
            for field in FIELDS[2:]:
                point.setdefault(field, [])
            point.setdefault('knowledge_type', 'rule')
            reused[target] = point
        return reused[target]

    def retained(target, key):
        if (target == key or target not in canonical or len(canonical[target]) != 1
                or decisions[target]['action'] not in {'keep', 'replace'}):
            raise ValueError(key + '：合并不能成链、环或指向空/待确认/拆分目标')
        return canonical[target][0]

    def bind(point, key, decision):
        original = by_key[key]
        for field in ('coverage_unit_ids','check_intents'):
            if field in original:
                point[field]=list(dict.fromkeys([*point.get(field,[]),*original[field]]))
        if original.get('profile_focus'):
            point['profile_focus']=original['profile_focus']
        point['input_material_keys'] = list(dict.fromkeys([*point['input_material_keys'], *original['input_material_keys']]))
        point['identity_members'].append(deepcopy(original))
        point['identity_decisions'].append(deepcopy(decision))

    for key, decision in decisions.items():
        action = decision['action']
        if action == 'covered':
            for part in decision['parts']:
                target = part['target']
                point = registered(target, key + '_' + target) if target in existing else retained(target, key)
                bind(point, key, {**decision, 'covered_part': deepcopy(part)})
            continue
        if action not in {'match', 'merge', 'reuse'}:
            continue
        target = decision['target']
        # The target's frozen namespace owns the operation. A model's synonym
        # for "reuse" must not override a valid, explicit identity reference.
        point = registered(target, key) if target in existing else retained(target, key)
        bind(point, key, decision)
    points = [point for rows in canonical.values() for point in rows] + list(reused.values())
    if not points:
        raise ValueError('本讲没有可保存的知识候选')
    if len(points) > 160:
        raise ValueError('本讲候选超过160点预算')
    return {'points': points, 'issues': issues, 'context_records': records}
