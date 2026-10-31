"""Semantic accounting for explicitly supplied knowledge requirements, not quotations."""
from copy import deepcopy

from course_document import stable_hash
from generic_knowledge import require
from knowledge_registry_contract import render


def schema(unit_keys,knowledge_ids):
    row={'type':'object','additionalProperties':False,'required':['status','knowledge_ids','reason'],
         'properties':{'status':{'enum':['covered','missing']},
            'knowledge_ids':{'type':'array','uniqueItems':True,'items':{'enum':knowledge_ids}},
            'reason':{'type':'string','minLength':1,'maxLength':500}}}
    return {'type':'object','additionalProperties':False,'required':['coverage'],'properties':{
        'coverage':{'type':'object','additionalProperties':False,'required':unit_keys,'properties':{k:row for k in unit_keys}}}}


def compile_result(value,units,points):
    from jsonschema import Draft202012Validator
    require(not list(Draft202012Validator(schema([u['key']for u in units],[p['knowledge_id']for p in points])).iter_errors(value)),
            '指定清单必须逐项核对并引用现有知识身份')
    missing=[]
    for key,row in value['coverage'].items():
        require(bool(row['knowledge_ids'])==(row['status']=='covered'),'覆盖结论与知识引用不一致')
        if row['status']=='missing':missing.append(key)
    return {'decisions':deepcopy(value['coverage']),'missing_unit_ids':missing}


async def check(tree,requirements,pipeline,request,save):
    from knowledge_coverage import parse_plan
    units=parse_plan({'units':requirements},pipeline.get('teaching_focus',[]))
    points=tree['knowledge_points']
    signature=stable_hash({'units':units,'points':[{k:p.get(k)for k in ('knowledge_id','revision_id','statement','conditions','symbol_definitions')}for p in points]},prefix='krequired_')
    existing=tree.get('required_coverage',{})
    if existing.get('input_signature')==signature and not existing.get('missing_unit_ids'):return
    state=pipeline.get('required_coverage',{})
    if state.get('input_signature')!=signature:
        state={'input_signature':signature,'status':'pending','request':{}};pipeline['required_coverage']=state
    prompt=render('逐项核对指定知识清单是否被当前完整知识承载。按完整命题、适用条件和符号含义比较，不做字面来源校验。'
        '每个清单项恰好给covered或missing。covered须引用实际承载该独立结论的knowledge_ids；missing引用空数组。'
        '统摄名称、主题相关或局部因子不能冒充完整覆盖。不要修改知识或编造引用，只报告覆盖与缺口。'
        '输出{"coverage":{"清单key":{"status":"covered","knowledge_ids":["实际知识ID"],"reason":"覆盖依据"}}}。',
        {'stage':'candidate_required_coverage','units':units,'points':[
            {k:p.get(k)for k in ('knowledge_id','name','statement','conditions','symbol_definitions')}for p in points]})
    state['result']=await request(prompt,'candidate_required_coverage',state['request'],lambda value:compile_result(value,units,points))
    state['status']='completed'
    tree['required_coverage']={'input_signature':signature,**deepcopy(state['result'])}
    if state['result']['missing_unit_ids']:
        tree['atomic_assessment']['ready_for_adoption']=False
        tree['atomic_assessment'].setdefault('issues',[]).append({'code':'required_knowledge_missing','severity':'blocking','message':'指定知识清单仍有未承载项'})
    pipeline['core_tree']=deepcopy(tree);await save()
    if state['result']['missing_unit_ids']:
        from course_errors import CourseDocumentConflict
        error=CourseDocumentConflict('指定知识清单仍有缺口，保留主体等待补齐，不生成配套内容')
        error.code='required_knowledge_missing'
        raise error
