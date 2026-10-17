"""Compact model contracts; coverage is derived only from explicit, validated bindings."""
from copy import deepcopy
from generic_knowledge import require, text, sources

INVENTORY = 'knowledge_inventory_compact_v2'
ATOMIC = 'knowledge_atomic_compact_v2'
PASSAGES = 'knowledge_inventory_passages_v3'
BINDINGS = 'knowledge_atomic_bindings_v3'


def passage_catalog(context, keys):
    """Lossless slices of every source, with stable code-point offsets."""
    available = sources(context); result = []
    for source_key in keys:
        content = available[source_key]['source_text']; start = 0; number = 0
        while start < len(content):
            end = min(start+600,len(content))
            if end < len(content):
                boundary = max(content.rfind(c,start+180,end) for c in ('\n','。','！','？','；'))
                if boundary >= 0:end = boundary+1
            number += 1
            result.append({'key':f'{source_key}.{number}','source_key':source_key,'start':start,'end':end,'text':content[start:end]})
            start = end
    return result


def passage_schema(stage, passage_keys, item_keys):
    result = schema(stage,['placeholder'],item_keys)
    if stage == 'inventory':
        result['properties']['response_contract']['const'] = PASSAGES
        entry = result['properties']['items']['items']; entry['properties'].pop('sources');entry['required'].remove('sources')
        entry['properties']['source_passage_keys'] = array({'type':'string','enum':list(passage_keys)},12,1);entry['required'].append('source_passage_keys')
        result['properties'].pop('source_notes');result['required'].remove('source_notes')
        result['properties']['unassigned_passages'] = array(obj({'passage_key':{'type':'string','enum':list(passage_keys)},
            'handling':{'type':'string','enum':['context','out_of_scope']},'reason':string(1000)}),len(passage_keys))
        result['required'].append('unassigned_passages')
        issue = result['properties']['source_issues']['items'];issue['properties'].pop('source_key');issue['properties'].pop('quote')
        issue['properties']['passage_key'] = {'type':'string','enum':list(passage_keys)};issue['required']=['passage_key','kind','detail']
    else:
        result['properties']['response_contract']['const'] = BINDINGS
        point = result['properties']['points']['items'];point['properties'].pop('sources');point['required'].remove('sources')
    return result


def expand_passage_inventory(response, context, keys):
    passages = {p['key']:p for p in passage_catalog(context,keys)}
    value = deepcopy(response); items = value.get('items')
    require(isinstance(items,list) and all(isinstance(i,dict) for i in items),'知识清单结构无效')
    used = {key:[] for key in passages}
    for item in items:
        refs = item.get('source_passage_keys')
        require(isinstance(refs,list) and refs and len(refs) <= 12 and all(isinstance(k,str) and k in passages for k in refs),'知识清单引用未知或缺失原文片段')
        item['sources'] = []
        for key in dict.fromkeys(refs):
            p = passages[key];used[key].append(item.get('key'))
            item['sources'].append({'key':p['source_key'],'quote':p['text'],'passage_key':key,'source_start':p['start'],'source_end':p['end']})
    notes = value.get('unassigned_passages')
    require(isinstance(notes,list) and all(isinstance(n,dict) for n in notes),'原文片段去向记录无效')
    unassigned = {}
    for note in notes:
        key = note.get('passage_key')
        require(key in passages and key not in unassigned and not used[key] and note.get('handling') in {'context','out_of_scope'},'原文片段去向重复、冲突或越界')
        unassigned[key] = {**note,'reason':text(note.get('reason'),'原文片段去向理由')}
    require(all(used[key] or key in unassigned for key in passages),'部分原文片段没有清单承载或明确的背景去向')
    rows = []
    for source_key in keys:
        part_keys = [k for k,p in passages.items() if p['source_key'] == source_key]
        refs = list(dict.fromkeys(i for k in part_keys for i in used[k]))
        rows.append({'source_key':source_key,'item_keys':refs,'handling':'items' if refs else 'context',
            'reason':'逐片段显式绑定对照，非独立语义覆盖验收','mapping_origin':'program_validated_bindings',
            'passage_keys':part_keys,'passage_coverage':[{'passage_key':k,'item_keys':used[k],
                'handling':'items' if used[k] else unassigned[k]['handling'],
                'reason':'显式片段引用' if used[k] else unassigned[k]['reason']} for k in part_keys]})
    value['source_coverage'] = rows
    return value


def bind_inventory_sources(response, items):
    value = deepcopy(response); catalog = {item['key']:item for item in items}
    for point in value.get('points',[]):
        refs = point.get('inventory_keys')
        require(isinstance(refs,list) and refs and all(isinstance(k,str) and k in catalog for k in refs),'知识点缺少有效清单来源')
        require('sources' not in point,'绑定合同不接受模型另行改写引文')
        quotes = []
        for key in refs:
            for source in catalog[key]['sources']:
                if source not in quotes:quotes.append(deepcopy(source))
        point['sources'] = quotes
    return value


def remap_coverage_keys(pipeline, aliases):
    for group in pipeline['inventory_batches']:
        for row in group['source_coverage']:
            row['item_keys'] = list(dict.fromkeys(aliases.get(k,k) for k in row['item_keys']))
            for part in row.get('passage_coverage',[]):
                part['item_keys'] = list(dict.fromkeys(aliases.get(k,k) for k in part['item_keys']))


def obj(properties):
    return {'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}


def string(limit=2000):
    return {'type':'string','minLength':1,'maxLength':limit}


def array(item, maximum=160, minimum=0):
    return {'type':'array','items':item,'minItems':minimum,'maxItems':maximum}


def schema(stage, source_keys, item_keys=()):
    reference = obj({'key':{'type':'string','enum':list(source_keys)},'quote':string(6000)})
    conditions = array(string(1000),20)
    if stage == 'inventory':
        return obj({'response_contract':{'type':'string','const':INVENTORY},
            'items':array(obj({'key':string(80),'name':string(200),
                'kind':{'type':'string','enum':['definition','rule','method','comparison','condition','boundary','example']},
                'claim':string(),'focus_terms':array(string(100),8,1),'conditions':conditions,'sources':array(reference,20,1)})),
            'source_notes':array(obj({'source_key':{'type':'string','enum':list(source_keys)},
                'handling':{'type':'string','enum':['context','out_of_scope']},'reason':string(1000)}),len(source_keys)),
            'source_issues':array(obj({'source_key':{'type':'string','enum':list(source_keys)},
                'kind':{'type':'string','enum':['contradiction','suspected_error']},'quote':string(6000),'detail':string(1500)}),30)})
    return obj({'response_contract':{'type':'string','const':ATOMIC},
        'categories':array(obj({'key':string(40),'name':string(160),'parent_key':{'type':['string','null']}}),60,1),
        'points':array(obj({'key':string(40),'category_key':string(40),'name':string(200),'statement':string(),
            'conditions':conditions,'meta_question':string(),'meta_answer':string(),
            'inventory_keys':array({'type':'string','enum':list(item_keys)},20,1),
            'independent_claims':array(string(),8,1),'sources':array(reference,20,1),
            'extraction_method':{'type':'string','enum':['direct_statement','summary','derived']},
            'derivation_note':{'type':'string','maxLength':2000}}),160,1),
        'context_items':array(obj({'inventory_key':{'type':'string','enum':list(item_keys)},'reason':string(1000)})),
        'gaps':array(string(),50)})


def inventory_coverage(response, items, keys):
    notes = response.get('source_notes')
    require(isinstance(notes,list) and all(isinstance(n,dict) for n in notes),'非知识来源去向记录无效')
    by_source = {}
    for note in notes:
        key = note.get('source_key')
        require(key in keys and key not in by_source and note.get('handling') in {'context','out_of_scope'},'来源去向重复或越界')
        by_source[key] = {**note,'reason':text(note.get('reason'),'非知识来源去向理由')}
    rows = []
    for key in keys:
        refs = [item['key'] for item in items if any(s['key'] == key for s in item['sources'])]
        require(not refs or key not in by_source,'同一来源不能同时标为已承载与无知识内容')
        require(refs or key in by_source,f'来源{key}尚无知识清单承载，也未说明背景或范围外去向')
        row = {'source_key':key,'item_keys':refs,'handling':'items','reason':'依据已校验的逐字引文与清单引用建立对照'} if refs else {**by_source[key],'item_keys':[]}
        rows.append({**row,'mapping_origin':'program_validated_bindings'})
    return rows


def atomic_coverage(response, items, points):
    by_item = {item['key']:item for item in items}
    notes = response.get('context_items')
    require(isinstance(notes,list) and all(isinstance(n,dict) for n in notes),'条件、边界与例题去向记录无效')
    context = {}
    for note in notes:
        key = note.get('inventory_key')
        require(key in by_item and key not in context and by_item[key]['kind'] in {'condition','boundary','example'},'独立知识不能转为背景，或附件去向重复、越界')
        context[key] = text(note.get('reason'),'附件背景理由')
    for point in points:
        refs = point.get('inventory_keys')
        require(isinstance(refs,list) and refs and all(isinstance(k,str) and k in by_item for k in refs),'知识点缺少有效清单来源')
    rows, checks = [], []
    for key,item in by_item.items():
        owners = [p for p in points if key in p['inventory_keys']]
        handling = 'point' if item['kind'] in {'definition','rule','method','comparison'} else item['kind']
        if not owners and key in context: handling = 'context'
        if not owners and key not in context and handling != 'point': continue
        rows.append({'inventory_key':key,'point_keys':[p['key'] for p in owners],'handling':handling,
            'reason':context.get(key,'依据知识点显式引用建立对照，未作独立语义核验'),'mapping_origin':'program_validated_bindings',
            **({'context_note':context[key]} if owners and key in context else {})})
        if handling == 'point':
            checks.extend({'inventory_key':key,'point_key':p['key'],'question_quote':p.get('meta_question'),
                'answer_quote':p.get('meta_answer'),'mapping_origin':'program_validated_bindings'} for p in owners)
    return rows,checks


def source_issues(response, available, keys, context=None):
    issues = response.get('source_issues',[])
    require(isinstance(issues,list) and len(issues) <= 30 and all(isinstance(i,dict) for i in issues),'来源疑点记录无效')
    result = []
    passages = {p['key']:p for p in passage_catalog(context,keys)} if context and response.get('response_contract') == PASSAGES else {}
    for issue in issues:
        if passages:
            passage = passages.get(issue.get('passage_key'));require(passage is not None,'来源疑点引用未知片段')
            issue = {**issue,'source_key':passage['source_key'],'quote':passage['text']}
        key = issue.get('source_key'); quote = text(issue.get('quote'),'来源疑点引文',6000)
        require(key in keys and quote in available[key]['source_text'] and issue.get('kind') in {'contradiction','suspected_error'},'来源疑点引用缺失、越界或不匹配')
        result.append({'source_key':key,'evidence_id':available[key]['evidence_id'],'quote':quote,'kind':issue['kind'],
            'detail':text(issue.get('detail'),'来源疑点说明',1500),'verification_status':'model_flagged_unverified'})
    return result
