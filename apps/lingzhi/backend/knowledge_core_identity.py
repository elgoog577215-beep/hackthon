"""A small global identity pass over suspects, never a title-based merger."""
from copy import deepcopy
from difflib import SequenceMatcher
import unicodedata

from knowledge_registry_contract import render
from knowledge_identity_matching import resolve_matches


def _text(value):
    return ''.join(c for c in unicodedata.normalize('NFKC',value).casefold() if c.isalnum())


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
        '若不同用different；无法确认用uncertain。每个EQ键恰好一次，给简短reason。'
        '输出{"pairs":{"EQ键":{"verdict":"same_claim_scope_symbols/different/uncertain","reason":"完整含义依据"}}}。',
        {'stage':'candidate_core_identity','pairs':[{'key':p['key'],'left':compact(p['left']),'right':compact(p['right'])} for p in pairs]})


def pair_schema(keys):
    decision={'type':'object','additionalProperties':False,'required':['verdict','reason'],
        'properties':{'verdict':{'enum':['same_claim_scope_symbols','different','uncertain']},'reason':{'type':'string','minLength':1}}}
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
        if decision['verdict']=='different':continue
        if decision['verdict']=='uncertain':
            updated['registry']['issues'].append({'code':'knowledge_core_identity_pending','severity':'blocking','message':decision['reason']})
            continue
        left,right=anchor(pair['left']),anchor(pair['right'])
        if left==right:continue
        if left in catalog_keys.values() and right in catalog_keys.values():
            updated['registry']['issues'].append({'code':'registered_identity_conflict','severity':'blocking','message':'不能自动合并两个已有知识身份'})
            continue
        source,target=(right,left) if left in catalog_keys.values() else (left,right)
        proposed=deepcopy(decisions);proposed[source]={'action':'match','target':target,
            'same_claim':True,'same_scope':True,'same_symbols':True,'reason':decision['reason']}
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
