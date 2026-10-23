"""Complete lesson cores: compact transport, one explicit combined review."""
from copy import deepcopy
import math

from knowledge_registry_contract import FIELDS, render, validate_point
from knowledge_truth_review import CORE_FIELDS

CONTRACT = 'knowledge_core_v1'
KNOWLEDGE_TYPES = {'definition','rule','method','comparison'}


def group_materials(materials, *, target_chars=1800):
    """Balance complete input units; never truncate or sample the lesson."""
    if not materials:
        raise ValueError('没有可读取的讲义材料')
    total = sum(len(m['text']) for m in materials)
    count = min(8, len(materials), max(1, math.ceil(total / target_chars)))
    groups, current, consumed = [], [], 0
    for index, material in enumerate(materials):
        current.append(deepcopy(material)); consumed += len(material['text'])
        remaining = len(materials)-index-1
        if len(groups)<count-1 and (consumed>=total*(len(groups)+1)/count or remaining==count-len(groups)-1):
            groups.append(current); current=[]
    if current:
        groups.append(current)
    return groups


def _texts(value, label):
    if not isinstance(value, list) or len(value) > 20 or any(not isinstance(s, str) or not s.strip() or len(s) > 1800 for s in value):
        raise ValueError(label + '必须为完整字符串列表')
    return deepcopy(value)


def _name(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 40 or value.rstrip().endswith(('?', '？', '。')):
        raise ValueError('知识名须简短明确，不能用问句或完整长句代替')
    return value.strip()


def _path(value):
    result = _texts(value, '分类路径')
    if not result or len(result) > 8 or any(len(s) > 80 for s in result):
        raise ValueError('分类须给出非空主题路径，不固定层数')
    return result


def parse_row(row, *, allow_draft_types=False):
    if not isinstance(row, list) or len(row) != 7:
        raise ValueError('知识行须依次给名称、完整知识、类型、条件、符号、分类路径和检查角度')
    name, statement, kind, conditions, symbols, path, checks = row
    unresolved = kind not in KNOWLEDGE_TYPES if isinstance(kind,str) else True
    if unresolved and (not allow_draft_types or not isinstance(kind,str) or not kind.strip() or len(kind)>40):
        raise ValueError('知识类型尚未归入正式分类')
    point = validate_point(dict(statement=statement, knowledge_type='rule' if unresolved else kind,
        conditions=conditions, symbol_definitions=symbols, teaching_context=[], examples=[]))
    if unresolved:
        point.update(knowledge_type=kind,unresolved_type=True)
    return {**point, 'short_name': _name(name), 'branch_path': _path(path),
            'check_intents': _texts(checks, '检查角度'), 'profile_focus': ''}


def parse_extraction(value, batch_id, material_keys):
    if not isinstance(value, dict) or set(value) != {'points', 'context_note'}:
        raise ValueError('提取须给出points和context_note')
    rows = value['points']
    if not isinstance(rows, list) or len(rows) > 160 or not isinstance(value['context_note'], str):
        raise ValueError('知识候选格式或容量无效')
    if not rows and not value['context_note'].strip():
        raise ValueError('无知识的材料也须说明其背景作用')
    return [{**parse_row(row,allow_draft_types=True), 'key': f'{batch_id}P{i}', 'input_material_keys': list(material_keys),
             'coverage_unit_ids': [f'{batch_id}P{i}']} for i, row in enumerate(rows, 1)]


def extraction_prompt(raw, context, materials):
    return render(
        '逐句读取本批完整讲义，提取可独立讲解、判断和补学的全部知识，不挑代表点或按主题只留一条。'
        '逐一分辨不同对象的定义、每一种记号的含义、每一种运算的独立性质、量之间的关系、表示方程和各个退化条件。'
        '同属某体系、同一组法则或同一段落，不代表只能保留一条；学生可能会前一条却不会后一条时，应分别保留完整结论。'
        '定义、独立运算规律、对象的斜率/方程/特殊情形分别完整保留；同一个完整公式内部不拆因子。'
        '同义表述、换符号、具体算例步骤不重复算知识。必要条件不能省略；不要把常见错误当独立规律。'
        '同时写简短知识名和主题分类路径，名称用学生能懂的概念或规律名，不用问句或完整长句。'
        '检查角度附在知识上，不写学生已犯错或已掌握。不生成关系、题目和教学档案。'
        '直接返回紧凑JSON，无过程解释。points每行依次为'
        '[短名称,完整陈述,definition/rule/method/comparison,条件数组,符号说明数组,主题路径数组,检查角度数组]。'
        '路径可有多级，不固定深度；同义主题统一命名。数组不能缺位，空字段用[]。'
        '输出{"points":[["名称","含公式及限定的完整知识","rule",[],[],["主题"],[]]],"context_note":""}。'
        '数量由独立知识决定，不为提速压缩或合并不同结论。公式须正确JSON转义。',
        {'stage': 'candidate_core_extract', 'contract': CONTRACT, 'course_title': raw.get('course_name',''),
         'lesson_title': context['handout_lessons'][0]['title'], 'materials': materials})


def review_prompt(raw, context, materials, points, catalog, *, references=(), coverage_materials=None):
    if coverage_materials is None:coverage_materials=materials
    return render(
        '一次集中核对全部知识的独立性、正确性、必要条件、同义身份和讲义覆盖。'
        '逐项主动尝试边界或反例，test简短记录实际检验的边界和结果，特别核对充分/必要、零值、定义域、方向及奇偶结论。'
        'decisions只且恰好包含每个候选key，材料S键只能出现在coverage，已有目录E键只能作为匹配目标。'
        '每个决定含type、action、test；type必须是definition/rule/method/comparison，不得沿用输入中其他类型名。'
        '正确且独立者keep；correct只改statement、conditions、symbol_definitions三个核心字段，其他字段冻结；'
        'correct额外给core对象。混合的独立知识用split，额外给points七列知识行数组；拆开的独立子结论不能再合并。'
        '不同对象的定义、多个记号的各自含义、多种运算的各自性质、关系/方程/退化情况不能只因同属体系而混成一条。'
        '同义知识match，只有完整命题、范围及符号含义一致才允许，须明确same_claim/same_scope/same_symbols均true，'
        'target为本轮其他候选或冻结已有目录E键，不能只因同主题或一起使用而合并；已有目录正文不可修改。'
        '纯操作失误comparison用check，额外给target、intent、same_scope:true、adds_knowledge:false、operational_only:true；'
        '真实概念辨析保留知识。纯算例或背景归context，给理由；不确定归uncertain并给理由。'
        '对照全部materials检查是否漏掉独立规则，缺失项通过add补齐，不用减少知识数掩盖遗漏。'
        '每个决定的name/path可选，仅在需要调整显示名称或分类路径时填写，其他名称和路径保留。'
        'reference_candidates用于全讲同义匹配，不给它们做决定。coverage只且恰好覆盖coverage_materials中的材料key，'
        '其他材料只是本批核对背景，不重复补充知识。值为[complete/context/gap,核对理由]，有未补齐知识时填gap。'
        '不要复述无问题的知识或输出核对过程。只输出紧凑JSON：'
        '{"decisions":{"候选key":{"type":"rule","action":"keep","test":"明确的边界检验及结果"}},"add":[],"coverage":{}}。'
        'split的points和add的point使用完整对象{name,statement,knowledge_type,conditions,symbol_definitions,path,checks}；'
        'knowledge_type同样只用四种正式类别。add每项另给sources，且只能补充coverage_materials中的独立知识。',
        {'stage': 'candidate_core_review', 'contract': CONTRACT, 'course_title':raw.get('course_name',''),
         'lesson_title':context['handout_lessons'][0]['title'], 'materials':materials,
         'coverage_materials':coverage_materials,
         'points': [{k:deepcopy(p[k]) for k in ('key',*FIELDS,'short_name','branch_path','check_intents')} for p in points],
         'reference_candidates':[{k:deepcopy(p[k]) for k in ('key','statement','conditions','symbol_definitions')} for p in references],
         'existing_knowledge': [{k:deepcopy(p.get(k)) for k in ('key','name',*FIELDS)} for p in catalog]})


def review_schema(points, materials, catalog=(), references=()):
    """A shallow grammar closes namespaces and categories, not domain wording."""
    from knowledge_registry_contract import point_schema
    text={'type':'string','minLength':1}
    row={'type':'object','additionalProperties':False,'required':['name','statement','knowledge_type','conditions','symbol_definitions','path','checks'],
        'properties':{'name':text,'statement':text,'knowledge_type':{'enum':sorted(KNOWLEDGE_TYPES)},
            **{k:{'type':'array','items':text} for k in ('conditions','symbol_definitions','path','checks')}}}
    core=point_schema();core['required']=list(CORE_FIELDS)
    core['properties']={k:v for k,v in core['properties'].items() if k in CORE_FIELDS}
    keys=[p['key'] for p in points];targets=[*keys,*[p['key'] for p in references],*[p['key'] for p in catalog]]
    decisions={}
    for key in keys:
        properties={'type':{'enum':sorted(KNOWLEDGE_TYPES)},'action':{'enum':['keep','correct','split','match','check','context','uncertain']},
            'test':text,'core':core,'points':{'type':'array','minItems':2,'maxItems':8,'items':row},
            'same_claim':{'const':True},'same_scope':{'const':True},'same_symbols':{'const':True},
            'adds_knowledge':{'const':False},'operational_only':{'const':True},'intent':text,'name':text,
            'path':{'type':'array','minItems':1,'items':text}}
        if any(k!=key for k in targets):properties['target']={'enum':[k for k in targets if k!=key]}
        branches=[]
        for actions,fields in [(['keep','context','uncertain'],[]),(['correct'],['core']),(['split'],['points']),
            (['match'],['target','same_claim','same_scope','same_symbols']),(['check'],['target','same_scope','adds_knowledge','operational_only','intent'])]:
            if 'target' in fields and 'target' not in properties:continue
            allowed={'type','action','test','name','path',*fields}
            branches.append({'type':'object','additionalProperties':False,'required':['type','action','test',*fields],
                'properties':{**{k:v for k,v in properties.items() if k in allowed},'action':{'enum':actions}}})
        decisions[key]={'anyOf':branches,'properties':properties}
    material_keys=[m['key'] for m in materials]
    result={'type':'object','additionalProperties':False,'required':['decisions','add','coverage'],'properties':{
        'decisions':{'type':'object','additionalProperties':False,'required':keys,'properties':decisions},
        'add':{'type':'array',**({'maxItems':0} if not material_keys else {}),'items':{'type':'object','additionalProperties':False,'required':['sources','point'],
            'properties':{'sources':{'type':'array','minItems':1,'items':{'enum':material_keys}},'point':row}}},
        'coverage':{'type':'object','additionalProperties':False,'required':material_keys,
            'properties':{k:{'type':'array','minItems':2,'maxItems':2,'items':{'type':'string'}} for k in material_keys}}}}
    if not material_keys:result['properties']['add']={'type':'array','maxItems':0}
    return result


def _review_row(row):
    if isinstance(row,list):return row
    if not isinstance(row,dict) or set(row)!={'name','statement','knowledge_type','conditions','symbol_definitions','path','checks'}:
        raise ValueError('新知识字段不完整')
    return [row[k] for k in ('name','statement','knowledge_type','conditions','symbol_definitions','path','checks')]


def _decisions(value, originals):
    keys={p['key'] for p in originals}
    if set(value)!={'decisions','add','coverage'} or not isinstance(value['decisions'],dict) or set(value['decisions'])!=keys:
        raise ValueError('集中核对必须且只能逐项决定本轮候选，不能混用材料身份')
    result={k:{} for k in ('correct','split','match','checks','context','uncertain','names','paths','types')}
    additions=value['add']
    if not isinstance(additions,list):raise ValueError('补充须为列表')
    result.update(keep=[],add=[{**a,'point':_review_row(a['point'])} for a in additions],coverage=value['coverage'])
    tests={}
    for key,decision in value['decisions'].items():
        if (not isinstance(decision,dict) or not {'type','action','test'}<=set(decision)
            or not isinstance(decision['test'],str) or not decision['test'].strip()):
            raise ValueError('每条知识须明确类别、决定与边界检验')
        action=decision['action'];extra={'name','path'}&set(decision)
        required={'keep':set(),'correct':{'core'},'split':{'points'},'match':{'target','same_claim','same_scope','same_symbols'},
            'check':{'target','same_scope','adds_knowledge','operational_only','intent'},'context':set(),'uncertain':set()}.get(action)
        if required is None or set(decision)!={'type','action','test',*extra,*required}:raise ValueError('决定与字段不一致')
        result['types'][key]=decision['type'];tests[key]=decision['test']
        if 'name' in decision:result['names'][key]=decision['name']
        if 'path' in decision:result['paths'][key]=decision['path']
        if action=='keep':result['keep'].append(key)
        elif action=='correct':result['correct'][key]=decision['core']
        elif action=='split':result['split'][key]=[_review_row(row) for row in decision['points']]
        elif action in {'context','uncertain'}:result[action][key]=decision['test']
        else:result['checks' if action=='check' else 'match'][key]={**{k:decision[k] for k in required},'reason':decision['test']}
    return result,tests


def compile_fragment(value, points, materials, catalog, references):
    from jsonschema import Draft202012Validator
    errors=list(Draft202012Validator(review_schema(points,materials,catalog,references)).iter_errors(value))
    if errors:raise ValueError('核对响应结构无效：'+'；'.join(e.message for e in errors[:3]))
    normalized,tests=_decisions(value,points)
    return {'response':deepcopy(value),'normalized':normalized,'tests':tests}


def compile_review(value, originals, catalog, materials):
    from knowledge_identity_matching import resolve_matches
    tests={}
    if isinstance(value,dict) and 'decisions' in value:value,tests=_decisions(value,originals)
    required = {'keep','correct','split','match','checks','context','uncertain','add','names','paths','types','coverage'}
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError('集中核对字段不完整')
    by_key = {p['key']:deepcopy(p) for p in originals}
    if not isinstance(value['types'],dict) or not set(value['types'])<=set(by_key):
        raise ValueError('类别确认不能更换候选身份')
    for key,kind in value['types'].items():
        if not isinstance(kind,str) or kind not in KNOWLEDGE_TYPES:raise ValueError('类别必须属于正式知识分类')
        by_key[key]['knowledge_type']=kind;by_key[key].pop('unresolved_type',None)
    if any(p['knowledge_type'] not in KNOWLEDGE_TYPES for p in by_key.values()):
        raise ValueError('仍有未确认的知识类别，不能发布基础树')
    keep = value['keep']
    if not isinstance(keep,list) or any(not isinstance(k,str) for k in keep):
        raise ValueError('keep须列出候选key')
    handled = list(keep)
    for action in ('correct','split','match','checks','context','uncertain'):
        if not isinstance(value[action],dict):
            raise ValueError(action+'必须按候选key组织')
        handled.extend(value[action])
    if len(handled) != len(set(handled)) or set(handled) != set(by_key):
        raise ValueError('每个知识候选必须且只能核对一次')
    for kind in ('names','paths'):
        if not isinstance(value[kind],dict) or not set(value[kind]) <= set(by_key):
            raise ValueError('显示调整不能更换知识身份')
    for key, name in value['names'].items(): by_key[key]['short_name'] = _name(name)
    for key, path in value['paths'].items(): by_key[key]['branch_path'] = _path(path)
    for key, patch in value['correct'].items():
        if not isinstance(patch,dict) or set(patch) != set(CORE_FIELDS):
            raise ValueError('真值修正只能包含三个知识核心字段')
        by_key[key].update(validate_point({**{k:by_key[key][k] for k in FIELDS},**patch}))
        by_key[key]['truth_review']={'contract':CONTRACT,'verdict':'corrected','semantics_verified':False,'test_case':tests.get(key,'')}
    points, decisions, dispositions = [], {}, []
    for key, point in by_key.items():
        if key in value['context']:
            reason=value['context'][key]
            if not isinstance(reason,str) or not reason.strip():raise ValueError('背景处理须说明理由')
            dispositions.append({'coverage_unit_ids':[key],'disposition':'context','reason':reason})
            continue
        if key in value['split']:
            rows=value['split'][key]
            if not isinstance(rows,list) or not 2<=len(rows)<=8:raise ValueError('拆分须给出独立完整知识')
            for i,row in enumerate(rows,1):
                child={**deepcopy(point),**parse_row(row),'key':f'{key}_{i}',
                    'semantic_review':{'contract':CONTRACT,'independence_group':key}}
                points.append(child);decisions[child['key']]={'action':'keep','reason':'已核对独立子结论'}
            continue
        point.setdefault('truth_review',{'contract':CONTRACT,'verdict':'reviewed','semantics_verified':False,'test_case':tests.get(key,'')})
        points.append(point)
        if key in value['match']:
            decision=value['match'][key]
            if (not isinstance(decision,dict) or set(decision)!={'target','same_claim','same_scope','same_symbols','reason'}
                or not all(decision.get(f) is True for f in ('same_claim','same_scope','same_symbols'))
                or not isinstance(decision['reason'],str) or not decision['reason'].strip()):
                raise ValueError('合并须明确核对完整命题、范围及符号含义')
            decisions[key]={'action':'match',**deepcopy(decision)}
        elif key in value['checks']:
            record=value['checks'][key]
            if (not isinstance(record,dict) or set(record)!={'target','intent','reason','same_scope','adds_knowledge','operational_only'}
                or point['knowledge_type']!='comparison'
                or record['same_scope'] is not True or record['adds_knowledge'] is not False or record['operational_only'] is not True
                or any(not isinstance(record[f],str) or not record[f].strip() for f in ('target','intent','reason'))):
                raise ValueError('检查项须绑定目标并给出检查角度与理由')
            point['semantic_review']={'contract':CONTRACT,'conclusion_role':'comparison'}
            decisions[key]={'action':'check','target':record['target'],'check_intent':record['intent'],'reason':record['reason'],
                **{k:record[k] for k in ('same_scope','adds_knowledge','operational_only')}}
        elif key in value['uncertain']:
            reason=value['uncertain'][key]
            if not isinstance(reason,str) or not reason.strip():raise ValueError('待确认知识须说明原因')
            decisions[key]={'action':'uncertain','reason':reason}
        else:
            decisions[key]={'action':'keep','reason':'集中核对已检查独立结论与必要条件'}
    if not isinstance(value['add'],list) or len(value['add'])>80:raise ValueError('覆盖补充格式无效')
    material_keys={m['key'] for m in materials}
    for i, added in enumerate(value['add'],1):
        if (not isinstance(added,dict) or set(added)!={'sources','point'} or not isinstance(added['sources'],list)
            or not added['sources'] or not all(isinstance(k,str) and k in material_keys for k in added['sources'])):
            raise ValueError('补充须记录本次读取的材料编号')
        key=f'AP{i}';point={**parse_row(added['point']),'key':key,'input_material_keys':added['sources'],'coverage_unit_ids':[key]}
        by_key[key]=deepcopy(point);points.append(point);decisions[key]={'action':'keep','reason':'覆盖核对补充的独立知识'}
    coverage=value['coverage']
    if not isinstance(coverage,dict) or set(coverage)!=material_keys:raise ValueError('必须核对全部输入材料的覆盖')
    for row in coverage.values():
        if (not isinstance(row,list) or len(row)!=2 or row[0] not in {'complete','context','gap'}
            or not isinstance(row[1],str) or not row[1].strip()):raise ValueError('覆盖结论须有状态和理由')
    registry=resolve_matches(points,catalog,decisions)
    if any(v[0]=='gap' for v in coverage.values()):
        registry['issues'].append({'code':'knowledge_core_coverage_gap','severity':'blocking','message':'完整讲义仍有待补齐知识'})
    names,paths=presentation_for(registry)
    units=[{'key':p['key'],'statement':p['statement'],'branch':' / '.join(p['branch_path']),
            'knowledge_type':p['knowledge_type'],'profile_focus':'','check_intent':next(iter(p['check_intents']),'独立解释该知识')}
           for p in by_key.values()]
    return {'registry':registry,'names':names,'paths':paths,'frozen_units':units,'reviewed_candidates':points,
            'identity_decisions':deepcopy(decisions),'extraction_resolutions':dispositions,'coverage':deepcopy(coverage)}


def presentation_for(registry):
    names,paths={},{}
    for point in registry['points']:
        member=next(iter(point.get('identity_members') or []),point)
        names[point['key']]={'name':member.get('short_name',point.get('name','')),
                            'meta_question':'请解释：'+point['statement']}
        paths[point['key']]=deepcopy(member.get('branch_path') or ['本讲知识'])
    return names,paths
