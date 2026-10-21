"""Focused semantic comparisons with deterministic equivalence graph resolution."""
from collections import defaultdict
from copy import deepcopy

from knowledge_registry_contract import render
from knowledge_registry_identity import apply_decisions

CONTRACT = 'knowledge_identity_matching_v2'


def matching_prompt(focus, candidates, catalog):
    fields = ('key','statement','conditions','knowledge_type','symbol_definitions')
    compact = lambda p: {**{k:p.get(k) for k in fields},
                         'independence_group':p.get('semantic_review',{}).get('independence_group')}
    return render(
        '只为focus_candidates逐一匹配完整知识身份，不改写正文、不分类、不重新判断粒度。'
        '在reference_candidates及existing_knowledge中查找同一完整命题。不同记号、文字/公式、变量代换或重述不形成新知识。'
        '实际对象、量含义或适用范围不同则保留；不能只因条件措辞不同或省略重复说明就把同一规律全部keep。'
        '优先match已有E身份；否则match本轮等价候选key。引用可以指向另一个已匹配候选，程序统一解析等价图。'
        '不能把定义、量的关系、对象表示、不同运算性质或必要/充分条件合并。'
        '共享independence_group的不同子结论不得合并；不能凭名称、同一主题或一起使用判定等价。'
        '没有等价目标才keep；无法判断用uncertain。每个focus key恰好一个决定。'
        'match只填action,target,same_claim=true,same_scope=true,same_symbols=true,reason；'
        'keep/uncertain只填action,reason。reason一句话说明完整知识和范围。'
        '输出{"decisions":{"focus key":{"action":"keep","reason":"身份依据"}}}。',
        {'stage':'identity_review','contract':CONTRACT,'allowed_actions':['keep','match','uncertain'],
         'candidates':[compact(p) for p in focus], 'reference_candidates':[compact(p) for p in candidates],
         'existing_knowledge':[compact(p) for p in catalog]})


def parse_matches(value, focus, candidates, catalog):
    decisions = value.get('decisions') if isinstance(value,dict) and set(value)=={'decisions'} else None
    if not isinstance(decisions,dict) or set(decisions)!={p['key'] for p in focus}:
        raise ValueError('身份匹配必须恰好处理本批focus keys')
    keys = {p['key'] for p in candidates+catalog}
    for key,row in decisions.items():
        if not isinstance(row,dict) or not isinstance(row.get('reason'),str) or not row['reason'].strip():
            raise ValueError(key+'：身份匹配须有理由')
        if row.get('action') in {'keep','uncertain'} and set(row)=={'action','reason'}:
            continue
        if (row.get('action')!='match' or set(row)!={'action','reason','target','same_claim','same_scope','same_symbols'}
                or row['target'] not in keys or row['target']==key
                or not all(row[k] is True for k in ('same_claim','same_scope','same_symbols'))):
            raise ValueError(key+'：只允许明确同命题、同范围、同量含义的match或keep/uncertain')
    return deepcopy(decisions)


def resolve_matches(candidates, catalog, decisions):
    parse_matches({'decisions':decisions},candidates,candidates,catalog)
    by_key={p['key']:p for p in candidates+catalog};parents={key:key for key in by_key}
    def find(key):
        while parents[key]!=key:
            parents[key]=parents[parents[key]];key=parents[key]
        return key
    for key,row in decisions.items():
        if row['action']=='match':
            parents[find(key)]=find(row['target'])
    groups=defaultdict(list)
    for key in by_key:groups[find(key)].append(key)
    registered={p['key'] for p in catalog};normalized={}
    for members in groups.values():
        local=[key for key in members if key in decisions]
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
    result=apply_decisions(candidates,catalog,normalized)
    result['equivalence_trace']={'contract':CONTRACT,'model_decisions':deepcopy(decisions),'resolved_decisions':normalized}
    return result
