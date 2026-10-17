"""Compact model contracts; coverage is derived only from explicit, validated bindings."""
from generic_knowledge import require, text

INVENTORY = 'knowledge_inventory_compact_v2'
ATOMIC = 'knowledge_atomic_compact_v2'


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
        require(not owners or key not in context,'附件不能同时绑定知识点和标为背景')
        handling = 'point' if item['kind'] in {'definition','rule','method','comparison'} else item['kind']
        if not owners and key in context: handling = 'context'
        if not owners and key not in context and handling != 'point': continue
        rows.append({'inventory_key':key,'point_keys':[p['key'] for p in owners],'handling':handling,
            'reason':context.get(key,'依据知识点显式引用建立对照，未作独立语义核验'),'mapping_origin':'program_validated_bindings'})
        if handling == 'point':
            checks.extend({'inventory_key':key,'point_key':p['key'],'question_quote':p.get('meta_question'),
                'answer_quote':p.get('meta_answer'),'mapping_origin':'program_validated_bindings'} for p in owners)
    return rows,checks


def source_issues(response, available, keys):
    issues = response.get('source_issues',[])
    require(isinstance(issues,list) and len(issues) <= 30 and all(isinstance(i,dict) for i in issues),'来源疑点记录无效')
    result = []
    for issue in issues:
        key = issue.get('source_key'); quote = text(issue.get('quote'),'来源疑点引文',6000)
        require(key in keys and quote in available[key]['source_text'] and issue.get('kind') in {'contradiction','suspected_error'},'来源疑点引用缺失、越界或不匹配')
        result.append({'source_key':key,'evidence_id':available[key]['evidence_id'],'quote':quote,'kind':issue['kind'],
            'detail':text(issue.get('detail'),'来源疑点说明',1500),'verification_status':'model_flagged_unverified'})
    return result
