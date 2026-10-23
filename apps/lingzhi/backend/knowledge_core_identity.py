"""A small global identity pass over suspects, never a title-based merger."""
from copy import deepcopy
from difflib import SequenceMatcher
import unicodedata

from knowledge_registry_contract import render
from knowledge_identity_matching import resolve_matches


def _text(value):
    return ''.join(c for c in unicodedata.normalize('NFKC',value).casefold() if c.isalnum())


def catalog_prompt(result):
    return render('比较本讲全部已核对知识的完整命题、适用范围及符号含义。不要改写、拆分或丢弃知识。'
        'identities恰好为每个key给出一个身份目标：独立知识指向自己；完整命题、范围、符号含义全部相同的知识指向同一个代表key。'
        '指向他者明确声明上述三个条件全部一致。允许公式/文字、换符号等价，不能只按名称判断。'
        '不同量、定义/关系/表示、不同运算规律及不同条件不能合并；同一independence_group的不同独立子结论不能合并。'
        '不能确认用uncertain。每个等价组优先保留有registered_identity的代表，不能合并两个已有身份。'
        '只输出{"identities":{"每个key":"自身或等价代表key或uncertain"}}，不复述正文。',
        {'stage':'candidate_core_identity_catalog','points':[
            {**{k:deepcopy(p.get(k)) for k in ('key','statement','conditions','symbol_definitions')},
             'name':result['names'][p['key']]['name'],
             'independence_group':p.get('semantic_review',{}).get('independence_group'),
             'registered_identity':p.get('knowledge_id') if p.get('_registered_point') else None}
            for p in result['registry']['points']]})


def catalog_schema(keys):
    return {'type':'object','additionalProperties':False,'required':['identities'],'properties':{
        'identities':{'type':'object','additionalProperties':False,'required':keys,
            'properties':{key:{'enum':[*keys,'uncertain']} for key in keys}}}}


def apply_catalog(result,value,catalog):
    from jsonschema import Draft202012Validator
    keys=[p['key'] for p in result['registry']['points']]
    if list(Draft202012Validator(catalog_schema(keys)).iter_errors(value)):
        raise ValueError('全讲同义核对必须恰好覆盖全部完整知识')
    pairs=[];decisions={}
    for key,target in value['identities'].items():
        if key==target:continue
        pair_key=f'EQ{len(pairs)+1}'
        pairs.append({'key':pair_key,'left':key,'right':key if target=='uncertain' else target})
        decisions[pair_key]='uncertain' if target=='uncertain' else 'same_claim_scope_symbols'
    return apply_pairs(result,pairs,{'pairs':decisions},catalog)


def candidate_pairs(result):
    points=result['registry']['points'];pairs=[]
    for i,left in enumerate(points):
        for right in points[i+1:]:
            if left.get('review_pending') or right.get('review_pending'):continue
            group=left.get('semantic_review',{}).get('independence_group')
            if group and group==right.get('semantic_review',{}).get('independence_group'):continue
            names=[_text(result['names'][p['key']]['name']) for p in (left,right)]
            name_score=SequenceMatcher(None,*names).ratio()
            statement_score=SequenceMatcher(None,*[_text(p['statement']) for p in (left,right)]).ratio()
            if name_score<.65 and statement_score<.82:continue
            pairs.append({'left':left['key'],'right':right['key'],'score':max(name_score,statement_score)})
    pairs.sort(key=lambda p:-p['score'])
    return [{'key':f'EQ{i}',**p} for i,p in enumerate(pairs[:40],1)]


def pair_prompt(result,pairs):
    points={p['key']:p for p in result['registry']['points']}
    def compact(key):
        point=points[key]
        return {'key':key,'name':result['names'][key]['name'],
                **{k:deepcopy(point.get(k)) for k in ('statement','conditions','symbol_definitions','knowledge_type')}}
    return render('只核对以下疑似同义知识对，不改写、不拆分或删除知识。'
        '名字相近只是线索，完整命题、适用范围和符号含义全部相同才给same_claim_scope_symbols。'
        '公式与口头解释、换符号以及相同范围内的等价表示应合并；不同量、运算、定义/斜率/方程不能因为相关而合并。'
        '若不同用different；无法确认用uncertain。每个EQ键恰好一次，直接给判断码，不展开解释或复述知识。'
        'same_claim_scope_symbols明确同时声明三个条件全部一致，不是名称相似。'
        '输出{"pairs":{"EQ键":"same_claim_scope_symbols/different/uncertain"}}。',
        {'stage':'candidate_core_identity','pairs':[{'key':p['key'],'left':compact(p['left']),'right':compact(p['right'])} for p in pairs]})


def pair_schema(keys):
    decision={'enum':['same_claim_scope_symbols','different','uncertain']}
    return {'type':'object','additionalProperties':False,'required':['pairs'],'properties':{
        'pairs':{'type':'object','additionalProperties':False,'required':keys,'properties':{k:decision for k in keys}}}}


def apply_pairs(result,pairs,value,catalog):
    from jsonschema import Draft202012Validator
    from knowledge_core_contract import presentation_for
    errors=list(Draft202012Validator(pair_schema([p['key'] for p in pairs])).iter_errors(value))
    if errors:raise ValueError('同义核对必须逐对给出完整决定')
    updated=deepcopy(result);decisions=updated['identity_decisions'];points=updated['reviewed_candidates']
    catalog_keys={p['knowledge_id']:p['key'] for p in catalog}
    registry_points={p['key']:p for p in result['registry']['points']}
    def anchor(key):
        point=registry_points[key]
        return catalog_keys[point['knowledge_id']] if point.get('_registered_point') else key
    for pair in pairs:
        decision=value['pairs'][pair['key']]
        if decision=='different':continue
        if decision=='uncertain':
            updated['registry']['issues'].append({'code':'knowledge_core_identity_pending','severity':'blocking','message':'模型未确认完整知识等价，保留原知识'})
            continue
        left,right=anchor(pair['left']),anchor(pair['right'])
        if left==right:continue
        if left in catalog_keys.values() and right in catalog_keys.values():
            updated['registry']['issues'].append({'code':'registered_identity_conflict','severity':'blocking','message':'不能自动合并两个已有知识身份'})
            continue
        source,target=(right,left) if left in catalog_keys.values() else (left,right)
        proposed=deepcopy(decisions);proposed[source]={'action':'match','target':target,
            'same_claim':True,'same_scope':True,'same_symbols':True,
            'reason':'全讲同义核对明确判定完整命题、适用范围及符号含义全部相同：'+pair['key']}
        try:registry=resolve_matches(points,catalog,proposed)
        except ValueError:
            updated['registry']['issues'].append({'code':'knowledge_core_identity_conflict','severity':'blocking','message':'同义决定与已冻结独立结论冲突'})
            continue
        registry['issues'].extend(deepcopy(updated['registry']['issues']))
        decisions={**registry['equivalence_trace']['resolved_decisions'],
            **{k:v for k,v in proposed.items() if v['action']=='check'}}
        updated['identity_decisions']=decisions;updated['registry']=registry
    updated['names'],updated['paths']=presentation_for(updated['registry'])
    return updated
