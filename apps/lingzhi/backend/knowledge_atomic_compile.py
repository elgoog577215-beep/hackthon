"""Pure compilation of legacy inventory and atomic batch payloads."""
import re
from copy import deepcopy
from generic_knowledge import compile_tree, normalized, records, require, sources, text

KNOWLEDGE_KINDS={"definition","rule","method","comparison"}
KINDS=KNOWLEDGE_KINDS|{"condition","boundary","example"}

def compile_inventory(response, context, keys, group_index):
    from knowledge_compact import PASSAGES, expand_passage_inventory, focus_matches
    if response.get('response_contract') == PASSAGES:response = expand_passage_inventory(response,context,keys)
    available = sources(context)
    items, aliases = [], {}
    raw_items = response.get('items')
    require(isinstance(raw_items, list) and len(raw_items) <= 160 and all(isinstance(v, dict) for v in raw_items), '知识清单结构无效或超出本次容量')
    for item in raw_items:
        old_key = text(item.get('key'), '清单短键', 80)
        require(old_key not in aliases, '清单短键重复')
        kind = item.get('kind'); require(kind in KINDS, '清单类型无效')
        refs = []
        for source in records(item.get('sources'), '清单来源', 20):
            key = source.get('key'); require(key in keys, '清单引用了本批之外的来源')
            quote = text(source.get('quote'), '清单引文', 6000)
            require(quote in available[key]['source_text'], '清单引文不在来源中')
            refs.append({**{k:source[k] for k in ('passage_key','source_start','source_end') if k in source},'key': key, 'quote': quote})
        name, claim = text(item.get('name'), '清单名称', 200), text(item.get('claim'), '清单命题', 2000)
        focus = item.get('focus_terms') or [name]
        require(isinstance(focus, list) and 0 < len(focus) <= 8 and all(isinstance(f, str) and f.strip() and len(f) <= 100 for f in focus), '清单检查对象无效')
        unconfirmed_focus = []
        if response.get('response_contract') == PASSAGES:
            unconfirmed_focus = [f for f in focus if not any(focus_matches(f,r['quote']) for r in refs)]
            focus = [f for f in focus if f not in unconfirmed_focus]
        require((focus or kind not in KNOWLEDGE_KINDS or response.get('response_contract') == PASSAGES) and all(any(focus_matches(f,r['quote']) for r in refs) for f in focus), '清单检查对象缺少原文依据')
        conditions = item.get('conditions', [])
        require(isinstance(conditions, list) and all(isinstance(c, str) for c in conditions), '清单条件无效')
        key = f'I{group_index}_{old_key}'; aliases[old_key] = key
        items.append({'key': key, 'name': name, 'claim': claim, 'kind': kind, 'sources': refs,
            'focus_terms': focus, 'unconfirmed_focus_terms':unconfirmed_focus, 'conditions': conditions})
        from knowledge_compact import has_suspicious_controls
        if not focus and kind in KNOWLEDGE_KINDS:items[-1]['source_focus_pending']=True
        if has_suspicious_controls([claim,*conditions]):items[-1]['text_integrity_pending']=True
    from knowledge_compact import INVENTORY, inventory_coverage
    rows = inventory_coverage(response,raw_items,keys) if response.get('response_contract') == INVENTORY else records(response.get('source_coverage'), '来源承载记录', len(keys))
    require({r.get('source_key') for r in rows} == set(keys) and len(rows) == len(keys), '部分来源缺少清单去向')
    mapped = []
    for row in rows:
        refs = row.get('item_keys', []); handling = row.get('handling')
        require(isinstance(refs, list) and all(k in aliases for k in refs), '来源承载引用未知清单')
        require(handling in ({'items','context','out_of_scope','pending'} if response.get('response_contract') == PASSAGES else {'items','context','out_of_scope'}), '来源承载类型无效')
        require(handling != 'items' or refs, '来源尚无知识清单承载')
        require(all(any(s['key'] == row['source_key'] for s in next(i for i in items if i['key'] == aliases[k])['sources']) for k in refs), '来源与清单引文不一致')
        mapped.append({**row, 'reason': text(row.get('reason'), '来源承载理由'), 'item_keys': [aliases[k] for k in refs],
            **({'passage_coverage':[{**part,'item_keys':[aliases[k] for k in part['item_keys']]} for part in row['passage_coverage']]} if 'passage_coverage' in row else {})})
    return items, mapped


def compile_batch(raw, context, items, response):
    from knowledge_compact import BINDINGS, LEAVES, assemble_leaf_claims, bind_inventory_sources
    leaves = response.get('response_contract') == LEAVES
    if leaves:response = assemble_leaf_claims(response,items)
    bound = leaves or response.get('response_contract') == BINDINGS
    if bound:response = bind_inventory_sources(response,items)
    consolidations = []
    if context.get('exact_claim_consolidation') == 'v1':
        from knowledge_compact import consolidate_exact_claims
        response, consolidations = consolidate_exact_claims(response)
    points = records(response.get('points'), '元知识候选', 160)
    item_by_key = {item['key']: item for item in items}
    point_by_key = {p.get('key'): p for p in points}
    require(len(point_by_key) == len(points), '候选知识短键重复')
    issues = []
    def issue(code, **values): issues.append({'code': code, 'severity': 'blocking', **values})
    from knowledge_compact import ATOMIC, atomic_coverage, focus_matches
    compact = bound or response.get('response_contract') == ATOMIC
    derived_rows, derived_checks = atomic_coverage(response,items,points) if compact else (None,None)
    rows = derived_rows if compact else response.get('coverage', [])
    require(isinstance(rows, list) and all(isinstance(r, dict) for r in rows), '清单覆盖记录无效')
    mapped = {}
    for row in rows:
        key = row.get('inventory_key')
        require(key in item_by_key and key not in mapped, '覆盖记录含未知或重复清单')
        refs = row.get('point_keys', [])
        require(isinstance(refs, list) and all(k in point_by_key for k in refs), '覆盖记录引用未知知识点')
        require(row.get('handling') in {'point', 'condition', 'boundary', 'example', 'context'}, '清单去向类型无效')
        mapped[key] = row
        if item_by_key[key]['kind'] in KNOWLEDGE_KINDS and (row.get('handling') != 'point' or not refs):
            issue('uncovered_inventory', inventory_key=key)
    for key in item_by_key:
        if key not in mapped: issue('uncovered_inventory', inventory_key=key)
    checks = derived_checks if compact else response.get('question_coverage', [])
    require(isinstance(checks, list) and all(isinstance(c, dict) for c in checks), '元问题覆盖记录无效')
    pairs = {}
    for check in checks:
        pair = (check.get('inventory_key'), check.get('point_key'))
        require(pair[0] in item_by_key and pair[1] in point_by_key and pair not in pairs, '元问题覆盖引用无效或重复')
        pairs[pair] = check
    question_owners = {}
    for key, point in point_by_key.items():
        from knowledge_compact import has_suspicious_controls
        if has_suspicious_controls([point.get('statement',''),point.get('meta_question',''),point.get('meta_answer','')]):issue('text_integrity_pending',point_key=key)
        refs = point.get('inventory_keys')
        require(isinstance(refs, list) and refs and len(refs) == len(set(refs)) and all(k in item_by_key for k in refs), '知识点缺少有效清单来源')
        knowledge = [k for k in refs if item_by_key[k]['kind'] in KNOWLEDGE_KINDS]
        if not knowledge: issue('nonknowledge_leaf', point_key=key)
        equivalent = context.get('exact_claim_consolidation') == 'v1' and len({
            (normalized(item_by_key[k]['claim']), tuple(sorted(normalized(c) for c in item_by_key[k]['conditions'])))
            for k in knowledge}) == 1
        if len(knowledge) > 1 and not equivalent: issue('multiple_independent_items', point_key=key)
        claims = point.get('independent_claims')
        if not isinstance(claims, list) or len(claims) != 1 or not isinstance(claims[0], str) or not claims[0].strip() or normalized(claims[0]) not in normalized(point.get('statement', '')):
            issue('multiple_or_unbound_claims', point_key=key)
        question = text(point.get('meta_question'), '元问题'); answer = text(point.get('meta_answer'), '元问题回答')
        if normalized(question) in question_owners: issue('duplicate_meta_question', point_key=key)
        question_owners[normalized(question)] = key
        for inventory_key in refs:
            if key not in mapped.get(inventory_key, {}).get('point_keys', []): issue('coverage_mapping_mismatch', point_key=key, inventory_key=inventory_key)
        for inventory_key in knowledge:
            check = pairs.get((inventory_key, key), {})
            q, a = check.get('question_quote'), check.get('answer_quote')
            if not isinstance(q, str) or not q.strip() or q not in question or not isinstance(a, str) or not a.strip() or a not in answer:
                issue('question_coverage_missing', point_key=key, inventory_key=inventory_key)
            if not any(focus_matches(f,question) for f in item_by_key[inventory_key]['focus_terms']):
                issue('question_focus_missing', point_key=key, inventory_key=inventory_key)
            if any(normalized(c) not in {normalized(v) for v in point.get('conditions', []) if isinstance(v, str)} for c in item_by_key[inventory_key]['conditions']):
                issue('condition_coverage_missing', point_key=key, inventory_key=inventory_key)
        if re.search(r'[、;；]|(?:^|\s)[12][.、]', point.get('name', '') + point.get('statement', '')) or re.search(r'[与和及]', point.get('name', '')):
            issues.append({'code': 'compound_review', 'severity': 'review', 'point_key': key})
    for inventory_key, row in mapped.items():
        for key in row.get('point_keys', []):
            if inventory_key not in point_by_key[key]['inventory_keys']: issue('coverage_mapping_mismatch', point_key=key, inventory_key=inventory_key)
    local_context = deepcopy(context); local_context.update(cross_lesson_alignment_contract='', reference_knowledge=[])
    lecture = local_context['handout_lessons'][0]
    payload = {**response, 'relations': [], 'lessons': [{'key': lecture['key'], 'title': lecture['title'], 'knowledge_keys': list(point_by_key)}]}
    tree = compile_tree(raw, local_context, payload)
    for p, original in zip(tree['knowledge_points'], points):
        p['inventory_keys'] = original['inventory_keys']
        if bound:p['source_binding_origin'] = 'frozen_inventory_passage'
        p['inventory_attachments'] = [deepcopy(item_by_key[k]) for k in original['inventory_keys'] if item_by_key[k]['kind'] not in KNOWLEDGE_KINDS]
    normalizations = [n for n in response.get('_format_normalizations',[]) if n in {'literal_controls_escaped','invalid_backslashes_preserved'}]
    if normalizations:issues.append({'code':'response_format_review','severity':'review'})
    return tree, {'ready_for_adoption': not any(i['severity'] == 'blocking' for i in issues),
        'semantics_verified': False, 'checked_items': len(items), 'issues': issues, 'coverage': deepcopy(rows),
        'question_coverage':deepcopy(checks),'format_normalizations':normalizations,
        'exact_duplicate_consolidations':consolidations,'mapping_origin':'program_validated_bindings' if compact else 'model_declared'}
