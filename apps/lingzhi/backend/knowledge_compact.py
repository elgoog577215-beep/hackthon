"""Compact model contracts; coverage is derived only from explicit, validated bindings."""
from copy import deepcopy
import re
import unicodedata
import json
from generic_knowledge import require, text, sources

INVENTORY = 'knowledge_inventory_compact_v2'
ATOMIC = 'knowledge_atomic_compact_v2'
PASSAGES = 'knowledge_inventory_passages_v3'
BINDINGS = 'knowledge_atomic_bindings_v3'
LEAVES = 'knowledge_leaf_claims_v4'


def parse_complete_json(raw):
    """Escape literal string characters only; never repair structure or fill data."""
    from knowledge_first import parse_response
    try:return parse_response(raw,handout_sources=True)
    except json.JSONDecodeError:
        out=[];inside=False;index=0;notes=set()
        while index < len(raw):
            char=raw[index]
            if char=='"':inside=not inside;out.append(char);index+=1;continue
            if inside and ord(char)<32:
                out.append(json.dumps(char)[1:-1]);notes.add('literal_controls_escaped');index+=1;continue
            if inside and char=='\\' and index+1<len(raw):
                nxt=raw[index+1]
                valid=nxt in '"\\/bfnrt' or nxt=='u' and bool(re.fullmatch(r'[0-9a-fA-F]{4}',raw[index+2:index+6]))
                if valid:out.extend([char,nxt]);index+=2;continue
                out.append('\\\\');notes.add('invalid_backslashes_preserved');index+=1;continue
            out.append(char);index+=1
        if not notes:raise
        value=parse_response(''.join(out),handout_sources=True)
        value['_format_normalizations']=sorted(set(value.get('_format_normalizations',[]))|notes)
        return value


def has_suspicious_controls(value):
    if isinstance(value,str):
        return bool(re.search(r'[\x00-\x08\x0b\x0c\x0e-\x1f]',value) or re.search(r'\$[^$]*\t[^$]*\$',value))
    if isinstance(value,list):return any(has_suspicious_controls(v) for v in value)
    return False


def focus_matches(term, content):
    def visible(value):
        value = unicodedata.normalize('NFKC',value)
        value = re.sub(r'\\(?:text|mathrm|operatorname)\{([^{}]*)\}',r'\1',value)
        value = re.sub(r'_\{([^{}]*)\}',r'_\1',value)
        for command,symbol in [(r'\Phi','Φ'),(r'\phi','φ'),(r'\times','×'),(r'\to','→'),(r'\geq','≥'),(r'\leq','≤')]:value=value.replace(command,symbol)
        return re.sub(r'[\s`*$]+','',value).casefold()
    anchor = visible(term)
    return bool(anchor) and anchor in visible(content)


def source_literal(subject, content):
    """Locate unchanged wording through inline math/code delimiters and layout.

    Keep Latin word boundaries and every operator/letter; this is not alias or
    semantic matching. Return raw offsets so normalization stays auditable.
    """
    if not isinstance(subject, str) or not subject.strip(): return None
    start = content.find(subject)
    if start >= 0: return {'start': start, 'end': start + len(subject), 'normalization': 'exact'}
    def visible(value):
        delimiters = {delimiter for delimiter in '$`' if value.count(delimiter) % 2 == 0}
        tokens = [(c, i) for i, c in enumerate(value) if c not in delimiters]; out = []; positions = []
        following = [''] * len(tokens); next_char = ''
        for index in range(len(tokens)-1, -1, -1):
            following[index] = next_char
            if not tokens[index][0].isspace(): next_char = tokens[index][0]
        for index, (char, position) in enumerate(tokens):
            if char.isspace():
                if out and re.fullmatch(r'[A-Za-z0-9_]', out[-1]) and re.fullmatch(r'[A-Za-z0-9_]', following[index]):
                    out.append(' '); positions.append(position)
                continue
            out.append(char); positions.append(position)
        return ''.join(out), positions
    needle, _ = visible(subject); text, positions = visible(content)
    if not needle: return None
    start = text.find(needle)
    if start < 0: return None
    return {'start': positions[start], 'end': positions[start+len(needle)-1]+1,
            'normalization': 'inline_math_and_whitespace_v1'}


def passage_catalog(context, keys):
    """Lossless slices of every source, with stable code-point offsets."""
    available = sources(context); result = []
    for source_key in keys:
        content = available[source_key]['source_text']; start = 0; number = 0
        if context.get('knowledge_passage_mode') == 'source_blocks_v1':
            result.append({'key': f'{source_key}.1', 'source_key': source_key,
                           'start': 0, 'end': len(content), 'text': content})
            continue
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


def leaf_schema(knowledge_keys, attachment_keys):
    attachments = array({'type':'string','enum':list(attachment_keys)},20) if attachment_keys else array({'type':'string'},0)
    return obj({'response_contract':{'type':'string','const':LEAVES},
        'categories':array(obj({'key':string(40),'name':string(160),'parent_key':{'type':['string','null']}}),60,1),
        'points':array(obj({'inventory_key':{'type':'string','enum':list(knowledge_keys)},'attachment_keys':attachments,
            'category_key':string(40),'name':string(200),'claims':array(string(),8,1),
            'meta_question':string(),'meta_answer':string(),
            'extraction_method':{'type':'string','enum':['direct_statement','summary','derived']},'derivation_note':{'type':'string','maxLength':2000}}),160,1),
        'context_items':array(obj({'inventory_key':{'type':'string','enum':list(knowledge_keys)+list(attachment_keys)},'reason':string(1000)})),
        'gaps':array(string(),50)})


def assemble_leaf_claims(response, items):
    value = deepcopy(response);catalog = {item['key']:item for item in items}
    points = value.get('points')
    require(isinstance(points,list) and points and all(isinstance(p,dict) for p in points),'元知识叶子输出无效')
    for index,point in enumerate(points,1):
        key = point.get('inventory_key'); item = catalog.get(key)
        require(item is not None and item['kind'] in {'definition','rule','method','comparison'},'例题、条件和边界不能作为知识叶子')
        attachments = point.get('attachment_keys',[])
        require(isinstance(attachments,list) and all(isinstance(k,str) and k in catalog and catalog[k]['kind'] in {'condition','boundary','example'} for k in attachments),'知识叶子的附件引用无效')
        claims = point.get('claims')
        require(isinstance(claims,list) and claims and len(claims) <= 8 and all(isinstance(c,str) and c.strip() for c in claims),'知识叶子缺少明确结论')
        point.update(key=f'K{index}',inventory_keys=list(dict.fromkeys([key,*attachments])),
            statement='\n'.join(claims),independent_claims=deepcopy(claims),conditions=deepcopy(item['conditions']))
    return value


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
        require(key in passages and note.get('handling') in {'context','out_of_scope'},'原文片段去向重复或越界')
        require(not used[key] or note['handling']=='context',f'原文片段{key}已被清单引用，不能同时声明为范围外')
        reason = text(note.get('reason'),'原文片段去向理由')
        existing = unassigned.get(key)
        if existing:
            require(existing['handling'] == note['handling'], f'原文片段{key}去向冲突')
            context_notes = [*existing.get('context_notes', [existing['reason']]), reason]
            existing['context_notes'] = list(dict.fromkeys(context_notes))
            existing['reason'] = '；'.join(existing['context_notes'])
        else:
            unassigned[key] = {**note,'reason':reason,'context_notes':[reason]}
    rows = []
    for source_key in keys:
        part_keys = [k for k,p in passages.items() if p['source_key'] == source_key]
        refs = list(dict.fromkeys(i for k in part_keys for i in used[k]))
        missing = [k for k in part_keys if not used[k] and k not in unassigned]
        rows.append({'source_key':source_key,'item_keys':refs,'handling':'items' if refs else 'pending' if missing else 'context',
            'reason':'逐片段显式绑定对照，非独立语义覆盖验收','mapping_origin':'program_validated_bindings',
            'passage_keys':part_keys,'uncovered_passage_keys':missing,
            'passage_coverage':[{'passage_key':k,'item_keys':used[k],
                'handling':'items' if used[k] else unassigned.get(k,{}).get('handling','pending'),
                'reason':'显式片段引用' if used[k] else unassigned.get(k,{}).get('reason','未承载且未说明去向，需补充'),
                **({'context_note':unassigned[k]['reason'],'context_notes':unassigned[k].get('context_notes',[])} if used[k] and k in unassigned else {})} for k in part_keys]})
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


def consolidate_exact_claims(response):
    """Merge identical assertions before coverage/identity checks, retaining every binding.

    Only the structured v9 compiler opts in. Different conditions or answers
    remain separate; this is not semantic/fuzzy deduplication.
    """
    from generic_knowledge import normalized
    value = deepcopy(response); unique = {}; points = []; merges = []
    for point in value['points']:
        identity = (normalized(point['statement']), tuple(sorted(normalized(c) for c in point['conditions'])))
        prior = unique.get(identity)
        if prior is None:
            unique[identity] = point; points.append(point)
            continue
        require(normalized(prior['meta_answer']) == normalized(point['meta_answer']), '相同命题的答案冲突')
        for field in ('inventory_keys', 'sources'):
            prior[field].extend(v for v in point[field] if v not in prior[field])
        merges.append({'point_key': prior['key'], 'duplicate_key': point['key'], 'inventory_keys': deepcopy(point['inventory_keys'])})
    value['points'] = points
    return value, merges


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
        require(key in by_item and key not in context,'清单背景说明重复或引用越界')
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
