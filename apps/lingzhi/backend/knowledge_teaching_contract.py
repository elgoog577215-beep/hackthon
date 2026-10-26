"""Typed teaching design over frozen knowledge; no student facts or source gates."""
from copy import deepcopy
from jsonschema import Draft202012Validator
from knowledge_registry_contract import render

CONTRACT='knowledge_teaching_structures_v1'
PROMPT_REVISION='teaching_design_20261026_2'


def text(limit=300,empty=False):
    return {'type':'string','minLength':0 if empty else 1,'maxLength':limit,'pattern':r'^[^\u0000-\u001f]*$'}


def obj(properties):
    return {'type':'object','additionalProperties':False,'required':list(properties),'properties':properties}


def array(items,maximum=6,minimum=0):
    return {'type':'array','minItems':minimum,'maxItems':maximum,'items':items}


def response_schema(focus_keys,catalog_keys):
    refs=array({'enum':catalog_keys},len(catalog_keys),1)
    criterion=obj({'name':text(80),'dimension':{'enum':['understanding','application','boundary','transfer']},
        'observable_performance':text(),'verification_method':text(),'controlled_conditions':array(text(180),4),
        'checkpoints':array(obj({'label':text(80),'pass_condition':text(200)}),4,1),
        'mistake_keys':array(text(20),6)})
    point=obj({'status':{'enum':['ready','needs_core_review']},'note':text(300,True),
        'criteria':array(criterion,3),'no_mistakes':text(180,True),'no_extensions':text(180,True)})
    mistake=obj({'key':text(20),'name':text(80),'observable_error_pattern':text(),'hypothesis':text(),
        'alternative_explanations':array(text(180),3,1),'scope':text(200),'discrimination':text(),
        'repair_strategy':text(),'retest':text(),'knowledge_keys':refs})
    extension=obj({'key':text(20),'name':text(80),'kind':{'enum':['optional_knowledge','application','comparison']},
        'knowledge_keys':refs,'goal':text(),'explanation':text(600),'prerequisite_keys':array({'enum':catalog_keys},len(catalog_keys)),
        'prerequisite_notes':text(200,True),'task':text(),'success_criteria':array(text(200),4,1)})
    return obj({'points':obj({key:point for key in focus_keys}),'mistakes':array(mistake,6),'extensions':array(extension,3)})


def prompt(tree,focus):
    return render('把已有知识及教学提示整理为结构化教学设计，不修改知识、ID、类别、条件或分类，也不生成学生画像或掌握分。'
        'points恰好覆盖focus。每点给1到3项可独立观察的检查标准，不固定凑理解/操作/迁移三套；每项1到4条能判定是否满足的具体条件。'
        'name与observable_performance用简短陈述句。verification_method是具体检查任务提纲，controlled_conditions说明提供哪些前提以减少其他知识干扰。'
        'checkpoints每条label简短，pass_condition明确什么表现算满足，不写“基本掌握”“理解正确”这类空话，不自定分数或阈值。'
        '发现核心条件矛盾、结论不严谨或同义重复时标needs_core_review并在note说明，检查标准保持待核对；不能偷偷改知识。'
        'mistakes保存一个具体错误假设，给可见错误、可能原因、其他可能解释、区分性检查、补救及独立复测；同一错误可关联多个知识key。'
        '不要把一个错误段落直接切分成已确认诊断，不声称学生已犯错或错误高频。局部key用M1、M2等，检查标准的mistake_keys只引用本批真实key。'
        '这里生成的是供教学使用的潜在错误假设，不是某位学生的诊断；不需要已有学生作答。主动利用kc_skill_profile和知识条件设计可辨别的错误假设。'
        '缺少学生证据、尚未采用候选、当前处于基础阶段，都不是省略易错设计的理由；学生是否犯错由未来真实作答判断。'
        'extensions是选学拓展：说明新知识/应用/对比的实际内容、目标、前置、具体学习任务和完成依据。'
        '仅增加数值难度、提高阶数、换复杂函数属于变式，不当作拓展。不要虚构资源链接、知识ID或题目ID。'
        'mistakes和extensions可为空，但对应点需用no_mistakes/no_extensions说明合理原因；不能为数量强凑。'
        '主动寻找有内容的应用、条件对比或概念联系。基础知识也可以拓展；只有确实没有合适的本点拓展才说明具体原因，不以当前阶段无需为理由。'
        'knowledge_keys可关联catalog的多个知识，但每个新对象至少关联一个focus。'
        '每字段一两句，最多300字符；拓展explanation最多600字符。公式引用已有形式，不展开长推导。只返回一个JSON对象，顶层仅points、mistakes、extensions；结束后停止输出。',
        {'stage':'candidate_teaching_structures','contract':CONTRACT,
         'output_schema':response_schema([p['key']for p in focus],[p['key']for p in tree['knowledge_points']]),
         'focus':[{k:deepcopy(p.get(k))for k in ('key','name','statement','conditions','symbol_definitions','check_intents','kc_skill_profile')}for p in focus],
         'catalog':[{k:deepcopy(p.get(k))for k in ('key','name','statement','conditions')}for p in tree['knowledge_points']]})


def compile_batch(value,focus,catalog,batch_id):
    errors=list(Draft202012Validator(response_schema([p['key']for p in focus],[p['key']for p in catalog])).iter_errors(value))
    if errors:raise ValueError('教学结构响应不符合字段或引用范围：'+errors[0].message)
    focus_keys={p['key']for p in focus};result=deepcopy(value)
    for collection in ('mistakes','extensions'):
        rows=result[collection]
        if len({r['key']for r in rows})!=len(rows):raise ValueError('教学对象临时键重复')
        if any(not focus_keys.intersection(r['knowledge_keys']) for r in rows):raise ValueError('不能修改无关知识的教学对象')
    mistakes={r['key']:r for r in result['mistakes']}
    for key,row in result['points'].items():
        if row['status']=='ready' and not row['criteria']:raise ValueError('可用知识必须有明确检查标准')
        if row['status']=='needs_core_review' and not row['note'].strip():raise ValueError('待核对知识须说明具体问题')
        for c in row['criteria']:
            if any(m not in mistakes or key not in mistakes[m]['knowledge_keys']for m in c['mistake_keys']):
                raise ValueError('检查标准引用了未关联到该知识的错误对象')
        if not any(key in m['knowledge_keys']for m in result['mistakes']) and not row['no_mistakes'].strip():raise ValueError('没有易错对象时须说明原因')
        if not any(key in x['knowledge_keys']for x in result['extensions']) and not row['no_extensions'].strip():raise ValueError('没有拓展时须说明原因')
    result['batch_id']=batch_id
    return result


def output_limits(schema,path=()):
    limits={}
    if schema.get('type')=='string' and schema.get('maxLength'):limits[path]=schema['maxLength']
    for key,value in schema.get('properties',{}).items():limits.update(output_limits(value,(*path,key)))
    if isinstance(schema.get('items'),dict):limits.update(output_limits(schema['items'],(*path,'*')))
    return limits
