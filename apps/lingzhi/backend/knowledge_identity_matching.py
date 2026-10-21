"""Focused semantic comparisons with deterministic equivalence graph resolution."""
from collections import defaultdict
from copy import deepcopy

from knowledge_registry_contract import render
from knowledge_registry_identity import apply_decisions

CONTRACT = 'knowledge_identity_matching_v5'


def placement_prompt(focus,candidates,catalog):
    fields=('key','statement','conditions','knowledge_type')
    return render(
        '这里只决定比较型候选的保存归属，不判断真伪、不合并同义、不改写正文。'
        '逐条判断该候选是否只是某个完整规则已经直接明示的操作检查。'
        '完整公式中的参数代入位置、已有因子的运算连接、适用条件的防漏提醒，不另建知识叶子，必须作为check挂回该完整规则。'
        '仅“说法正确、能检查、常见错误”不是独立知识的充分理由。'
        '新定义、新对象/量关系、逆命题、反例性质及真正独立的概念辨析仍keep。'
        '不能把能推导出的不同定理都归check；只处理从完整规则直接读出的操作提醒。'
        'target从rule_catalog或existing_knowledge选择，不能指向自身或另一个检查候选。'
        '每个candidate key必须一项placements。独立知识只填action=keep,reason。'
        '纯检查填action=check,target,same_scope=true,adds_knowledge=false,operational_only=true,check_intent,reason。'
        'check_intent用简短陈述描述可观察的操作，不声称任何学生已犯错。输出{"placements":{"key":{"action":"keep","reason":"独立知识依据"}}}。',
        {'stage':'candidate_check_placement','contract':'knowledge_check_placement_v1',
         'candidates':[{k:p.get(k) for k in fields} for p in focus],
         'rule_catalog':[{k:p.get(k) for k in fields} for p in candidates
                         if p.get('semantic_review',{}).get('conclusion_role')!='comparison'],
         'existing_knowledge':[{k:p.get(k) for k in fields} for p in catalog]})


def parse_placements(value,focus,candidates,catalog):
    rows=value.get('placements') if isinstance(value,dict) and set(value)=={'placements'} else None
    parsed=parse_matches({'decisions':rows},focus,candidates,catalog)
    roles={p['key']:p.get('semantic_review',{}).get('conclusion_role') for p in candidates}
    for key,row in parsed.items():
        if row['action'] not in {'keep','check'} or row['action']=='check' and roles.get(row['target'])=='comparison':
            raise ValueError(key+'：归属阶段只允许keep或将纯操作检查绑定到完整规则')
    return parsed


def matching_prompt(focus, candidates, catalog):
    fields = ('key','statement','conditions','knowledge_type','symbol_definitions')
    compact = lambda p: {**{k:p.get(k) for k in fields},
                         'independence_group':p.get('semantic_review',{}).get('independence_group'),
                         'conclusion_role':p.get('semantic_review',{}).get('conclusion_role')}
    return render(
        '只为focus_candidates逐一匹配完整知识身份，不改写正文、不分类、不重新判断粒度。'
        '在reference_candidates及existing_knowledge中查找同一完整命题。不同记号、文字/公式、变量代换或重述不形成新知识。'
        '实际对象、量含义或适用范围不同则保留；不能只因条件措辞不同或省略重复说明就把同一规律全部keep。'
        '优先match已有E身份；否则match本轮等价候选key。引用可以指向另一个已匹配候选，程序统一解析等价图。'
        '不能把定义、量的关系、对象表示、不同运算性质或必要/充分条件合并。'
        '共享independence_group的不同子结论不得合并；不能凭名称、同一主题或一起使用判定等价。'
        '没有等价目标才keep；无法判断用uncertain。每个focus key恰好一个决定。'
        '严禁match指向自身；focus候选之间也可以互相比较，自身不是一条参考命中。'
        '另检查纯操作提醒的保存归属：若comparison候选仅复述某个完整规则中的因子、代入位置或操作防漏，'
        '没有新增知识，可用check挂回完整规则，不另占知识叶子。'
        '定义、独立量关系、表示、不同运算性质、逆命题和真实概念辨析必须保留知识，不能降为check。'
        'check只填action,target,same_scope=true,adds_knowledge=false,operational_only=true,check_intent,reason；'
        'check_intent用陈述写出学生可观察的规则应用表现，不声称学生已犯错。target必须是承载完整规则的其他知识。'
        'match只填action,target,same_claim=true,same_scope=true,same_symbols=true,reason；'
        'keep/uncertain只填action,reason。reason一句话说明完整知识和范围。'
        '输出{"decisions":{"focus key":{"action":"keep","reason":"身份依据"}}}。',
        {'stage':'identity_review','contract':CONTRACT,'allowed_actions':['keep','match','check','uncertain'],
         'candidates':[compact(p) for p in focus],
         'reference_candidates':[compact(p) for p in candidates if p['key'] not in {f['key'] for f in focus}],
         'existing_knowledge':[compact(p) for p in catalog]})


def parse_matches(value, focus, candidates, catalog):
    decisions = value.get('decisions') if isinstance(value,dict) and set(value)=={'decisions'} else None
    if not isinstance(decisions,dict) or set(decisions)!={p['key'] for p in focus}:
        raise ValueError('身份匹配必须恰好处理本批focus keys')
    keys = {p['key'] for p in candidates+catalog}
    by_key={p['key']:p for p in candidates}
    for key,row in decisions.items():
        if not isinstance(row,dict) or not isinstance(row.get('reason'),str) or not row['reason'].strip():
            raise ValueError(key+'：身份匹配须有理由')
        if row.get('action') in {'keep','uncertain'} and set(row)=={'action','reason'}:
            continue
        if row.get('action')=='check':
            if (set(row)!={'action','target','same_scope','adds_knowledge','operational_only','check_intent','reason'}
                    or by_key[key].get('semantic_review',{}).get('conclusion_role')!='comparison'
                    or row['target'] not in keys or row['target']==key
                    or row['same_scope'] is not True or row['adds_knowledge'] is not False or row['operational_only'] is not True
                    or not isinstance(row['check_intent'],str) or not row['check_intent'].strip() or len(row['check_intent'])>1200):
                raise ValueError(key+'：check必须是同范围、无新增知识的纯操作检查，且明确引用完整知识')
            continue
        if row.get('action')=='match' and row.get('target')==key:
            raise ValueError(key+'.target不得指向自身；请比较其他候选，没有其他等价知识时用keep')
        if (row.get('action')!='match' or set(row)!={'action','reason','target','same_claim','same_scope','same_symbols'}
                or row['target'] not in keys or row['target']==key
                or not all(row[k] is True for k in ('same_claim','same_scope','same_symbols'))):
            raise ValueError(key+'：只允许明确同命题、同范围、同量含义的match或keep/uncertain')
    return deepcopy(decisions)


def resolve_matches(candidates, catalog, decisions):
    parse_matches({'decisions':decisions},candidates,candidates,catalog)
    by_key={p['key']:p for p in candidates+catalog};parents={key:key for key in by_key}
    check_keys={key for key,row in decisions.items() if row['action']=='check'}
    def find(key):
        while parents[key]!=key:
            parents[key]=parents[parents[key]];key=parents[key]
        return key
    for key,row in decisions.items():
        if row['action'] in {'match','check'} and row['target'] in check_keys:
            raise ValueError(key+'：不能把检查项作为知识身份或另一检查项的目标')
        if row['action']=='match':
            parents[find(key)]=find(row['target'])
    groups=defaultdict(list)
    for key in by_key:groups[find(key)].append(key)
    registered={p['key'] for p in catalog};normalized={}
    for members in groups.values():
        local=[key for key in members if key in decisions and key not in check_keys]
        if not local:continue
        stored=[key for key in members if key in registered]
        if len(stored)>1:
            raise ValueError('身份匹配不能自动合并多个已有知识ID')
        independence=[by_key[key].get('semantic_review',{}).get('independence_group') for key in local]
        nonempty=[g for g in independence if g]
        if len(nonempty)!=len(set(nonempty)):
            raise ValueError('身份匹配不能折叠同组独立结论')
        uncertain=any(decisions[key]['action']=='uncertain' for key in local)
        root=stored[0] if stored else local[0]
        for key in local:
            reason=decisions[key]['reason']
            if uncertain:normalized[key]={'action':'uncertain','reason':reason}
            elif key==root:normalized[key]={'action':'keep','reason':reason}
            else:normalized[key]={'action':'match','target':root,'same_claim':True,'same_scope':True,'same_symbols':True,'reason':reason}
    knowledge_candidates=[p for p in candidates if p['key'] not in check_keys]
    result=apply_decisions(knowledge_candidates,catalog,normalized) if knowledge_candidates else {'points':[],'issues':[],'context_records':[]}
    roots={}
    for members in groups.values():
        stored=[key for key in members if key in registered]
        local=[key for key in members if key in normalized]
        root=stored[0] if stored else local[0] if local else members[0]
        roots.update({key:root for key in members})
    result['check_resolutions']=[]
    for key in (p['key'] for p in candidates if p['key'] in check_keys):
        row=decisions[key];target=roots[row['target']]
        if decisions.get(target,{}).get('action')=='uncertain':
            raise ValueError(key+'：检查不能绑定待确认知识')
        if target in registered:
            stored=by_key[target]
            point=next((p for p in result['points'] if p.get('knowledge_id')==stored['knowledge_id']),None)
            if point is None:
                point={**deepcopy(stored),'key':target,'_registered_point':deepcopy(stored),
                    'input_material_keys':[],'coverage_unit_ids':[],'identity_members':[],'identity_decisions':[]}
                result['points'].append(point)
        else:
            point=next(p for p in result['points'] if p['key']==target)
        original=by_key[key]
        record={'candidate_key':key,'coverage_unit_ids':deepcopy(original.get('coverage_unit_ids',[])),
            'disposition':'check','target_key':point['key'],'reason':row['reason'],
            'check_intent':row['check_intent'],'original':deepcopy(original)}
        point['check_intents']=list(dict.fromkeys([*point.get('check_intents',[]),row['check_intent']]))
        point['input_material_keys']=list(dict.fromkeys([*point.get('input_material_keys',[]),*original['input_material_keys']]))
        point.setdefault('check_records',[]).append(deepcopy(record))
        result['check_resolutions'].append(record)
    result['equivalence_trace']={'contract':CONTRACT,'model_decisions':deepcopy(decisions),'resolved_decisions':normalized}
    return result
