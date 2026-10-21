"""The default lesson pipeline uses knowledge identity, not literal provenance."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from backend.tests.test_knowledge_first import svc
from backend.tests.test_knowledge_atomic import setup_course


def claim(statement='压栈把新元素放到栈顶', **values):
    return dict(statement=statement, knowledge_type='rule', conditions=[],
                symbol_definitions=[], teaching_context=[], examples=[], **values)


def discovery_reply(payload):
    return json.dumps({'points':[{**claim(),'branch':'栈','profile_focus':next(iter(payload['teaching_focus']),''),'check_intents':['独立描述入栈']}],'context_note':''})


def atomic_reply(payload):
    return json.dumps({'items':{p['key']:{'disposition':'knowledge','reason':'一条完整规则',
        'points':[{k:v for k,v in p.items() if k in {'statement','knowledge_type','conditions','check_intents'}}]} for p in payload['candidates']}})


def semantic_reply(payload):
    from knowledge_registry_contract import FIELDS
    return json.dumps({'reviews':{p['key']:{'disposition':'knowledge','reason':'一条完整结论',
        'challenge':{'case':'改变栈中已有元素的数量','result':'consistent','explanation':'入栈位置仍为栈顶'},
        'conclusions':[{**{k:p[k] for k in FIELDS},'check':p.get('check_intents',['解释知识'])[0],'role':'operation'}]}
        for p in payload['points']}})


def test_extraction_accepts_paraphrase_without_source_binding():
    from knowledge_registry_contract import parse_candidates, extraction_prompt
    context={'scope_lesson_id':'L1', 'evidence_package':{'units':[]}}
    prompt=extraction_prompt({'course_name':'测试'},context,[{'key':'S1','text':'入栈。'}],[])
    for old in ['focus_options','source_literal','必须逐字','只能来自当前','bind_relation']:
        assert old not in prompt
    points=parse_candidates({'points':[claim()],'context_note':''},'B1',['S1'])
    assert points[0]['statement']=='压栈把新元素放到栈顶'
    assert points[0]['input_material_keys']==['S1']
    assert 'source_span' not in points[0]


def test_identity_reuses_registered_id_and_keeps_original_semantics():
    from knowledge_registry_identity import apply_decisions
    old={**claim('入栈将元素插入栈顶。'),'key':'E1','knowledge_id':'stable-id',
         'revision_id':'old-rev','name':'入栈把元素加入栈顶','meta_question':'入栈有什么作用？',
         'meta_answer':'入栈将元素插入栈顶。'}
    new={**claim(),'key':'P1','input_material_keys':['S1']}
    before=deepcopy(old)
    result=apply_decisions([new],[old],{'P1':{'action':'reuse','target':'E1',
        'same_claim':True,'same_scope':True,'same_symbols':True,'reason':'命题、范围与量的含义相同'}})
    assert result['points'][0]['knowledge_id']=='stable-id'
    assert result['points'][0]['statement']==old['statement'] and old==before
    assert result['points'][0]['identity_members'][0]['statement']==new['statement']


def test_equivalence_is_explicit_and_symbol_descriptions_are_separate_from_scope():
    from knowledge_registry_identity import apply_decisions
    a={**claim("加速度等于速度对时间的导数"),'symbol_definitions':['v(t)表示速度函数'],
       'key':'P1','input_material_keys':['S1']}
    b={**a,'key':'P2','symbol_definitions':['v(t)表示速度'],'input_material_keys':['S2']}
    decision={'P1':{'action':'keep','reason':'完整知识'},'P2':{'action':'merge','target':'P1',
        'same_claim':True,'same_scope':True,'same_symbols':True,'reason':'两种量说明含义相同'}}
    result=apply_decisions([a,b],[],decision)
    assert len(result['points'])==1
    assert len(result['points'][0]['identity_members'])==2
    different={**b,'conditions':['仅匀加速运动']}
    kept=apply_decisions([a,different],[],{k:{'action':'keep','reason':'范围不同'} for k in ['P1','P2']})
    assert len(kept['points'])==2
    decision['P2']['same_scope']=False
    with pytest.raises(ValueError,match='范围'):
        apply_decisions([a,different],[],decision)


def test_uncertain_is_a_visible_candidate_and_merge_cycles_are_rejected():
    from knowledge_registry_identity import apply_decisions
    candidates=[{**claim(),'key':key,'input_material_keys':['S1']} for key in ['P1','P2']]
    result=apply_decisions(candidates,[],{k:{'action':'uncertain','reason':'需要确认适用范围'} for k in ['P1','P2']})
    assert len(result['points'])==2 and len(result['issues'])==2
    with pytest.raises(ValueError):
        apply_decisions(candidates,[],{k:{'action':'merge','target':other,'same_claim':True,
            'same_scope':True,'same_symbols':True,'reason':'相同'} for k,other in [('P1','P2'),('P2','P1')]})


@pytest.mark.asyncio
@pytest.mark.parametrize('full',[False,True])
@pytest.mark.parametrize('teaching',[False,True])
@pytest.mark.parametrize('provided',[False,True])
async def test_default_flow_never_calls_legacy_source_repair_and_preserves_course(svc,monkeypatch,full,teaching,provided):
    setup_course(svc,monkeypatch)
    raw=deepcopy(svc.repository.load_raw('c-pilot'));calls=[]
    async def call(prompt,**kwargs):
        payload=json.loads(prompt.split('\nINPUT_JSON:\n')[1]);calls.append(payload)
        if payload['stage']=='knowledge_discovery':return discovery_reply(payload)
        if payload['stage']=='knowledge_atomize':return atomic_reply(payload)
        if payload['stage']=='candidate_semantic_review':return semantic_reply(payload)
        if payload['stage']=='coverage_extract':
            return json.dumps({'points':{u['key']:[claim()] for u in payload['units']}})
        if payload['stage']=='identity_review':
            return json.dumps({'decisions':{p['key']:{'action':'keep','reason':'完整知识'} for p in payload['candidates']}})
        if payload['stage']=='candidate_names':
            return json.dumps({'names':{p['key']:{'name':'压栈把新元素放到栈顶','meta_question':'压栈怎样改变栈？'} for p in payload['points']}})
        if payload['stage']=='hierarchy_partition':
            return json.dumps({'response_contract':'knowledge_partition_v1','groups':[],
                'point_groups':{p['key']:'__direct__' for p in payload['points']},'stop_reason':'同一范围内并列'})
        if payload['stage']=='candidate_relations':
            return json.dumps({'reviews':{key:'没有额外关系' for key in payload['focus_keys']},'edges':[]})
        if payload['stage']=='kc_profiles':
            from third_party.learningmap.kc import KCSkill
            return json.dumps({'profiles':{p['key']:{field:'教学说明' for field in KCSkill.model_fields} for p in payload['profiles']}})
        pytest.fail('Unexpected legacy stage '+payload['stage'])
    svc.provider_factory=lambda:SimpleNamespace(_call_llm=call,client=None,model_smart='qwen3.8-27b')
    view=svc.view('c-pilot',source_mode='handouts')
    job,_=svc.start('c-pilot','tree','registry-new',view['knowledge_revision'],view['document_revision'],
        source_mode='handouts',lesson_id='cpu',pipeline='inventory_atomic_v1',
        extraction_mode='single_pass_v1',organize_hierarchy=full,include_relations=full,teaching_focus=['线性法则'] if teaching else [],coverage_units=[{'statement':claim()['statement'],'branch':'栈','knowledge_type':'rule','profile_focus':'线性法则' if teaching else '','check_intent':'独立描述入栈'}] if provided else [])
    await svc.run('c-pilot',job['id'])
    out=svc.authoring.get_job('c-pilot',job['id'])
    assert out['status']=='completed',out.get('error')
    assert [p['stage'] for p in calls]==(['coverage_extract'] if provided else ['knowledge_discovery','knowledge_atomize'])+['candidate_semantic_review','identity_review','candidate_names']+(['candidate_relations'] if full else [])+(['kc_profiles'] if teaching else [])
    if full:
        assert out['checkpoint']['atomic_pipeline']['hierarchy']['status']=='completed'
    tree=out['checkpoint']['candidate']
    assert tree['knowledge_points'][0]['statement']==claim()['statement']
    assert tree['knowledge_coverage']['missing_unit_ids']==[]
    assert tree['knowledge_coverage']['plan_origin']==('provided_coverage_plan' if provided else 'material_discovery')
    if teaching:
        profile=tree['knowledge_points'][0]['kc_skill_profile']
        assert profile['knowledge_revision']==tree['knowledge_points'][0]['revision_id']
        assert profile['basis']=='knowledge_draft' and not profile['learner_evidence']
    assert tree['provenance_contract']=='input_material_record_v1'
    assert tree['atomic_assessment']['ready_for_adoption']
    assert svc.repository.load_raw('c-pilot')==raw
    svc.adopt('c-pilot',job['id'],view['knowledge_revision'],view['document_revision'],confirm_relations=full)
    assert svc.repository.load_raw('c-pilot')['course_knowledge_base']['knowledge_points'][0]['statement']==claim()['statement']


@pytest.mark.parametrize('raw', ['{"x":1,"x":2}', '{"x":', '{"x":"\\frac{1}{2}"}'])
def test_json_errors_cannot_be_salvaged_into_valid_knowledge(raw):
    from knowledge_registry_contract import parse_json
    with pytest.raises(ValueError):
        parse_json(raw)


def test_same_name_is_reviewable_without_merging_different_conditions(svc,monkeypatch):
    from knowledge_registry_projection import build_tree
    from knowledge_registry_identity import apply_decisions
    setup_course(svc,monkeypatch)
    raw=svc.repository.load_raw('c-pilot');context=svc._context(raw,'handouts','cpu')
    first={**claim(),'key':'P1','conditions':['条件甲'],'input_material_keys':['S1']}
    second={**claim(),'key':'P2','conditions':['条件乙'],'input_material_keys':['S1']}
    registry=apply_decisions([first,second],[],{k:{'action':'keep','reason':'不同范围'} for k in ['P1','P2']})
    pipeline={'registry':registry,'names':{'result':{k:{'name':'相同名称','meta_question':'说明此知识'} for k in ['P1','P2']}}}
    tree=build_tree(raw,context,pipeline,'job')
    assert len({p['knowledge_id'] for p in tree['knowledge_points']})==2
    assert tree['atomic_assessment']['ready_for_adoption']
    assert tree['atomic_assessment']['issues'][0]['code']=='display_name_collision'


@pytest.mark.parametrize('action', ['missing','unknown','empty_replace','merge_unknown','reuse_unknown','extra'])
def test_invalid_identity_actions_are_rejected(action):
    from knowledge_registry_identity import apply_decisions
    rows=[{**claim(),'key':'P1','input_material_keys':['S1']}]
    decision={'P1':{'action':'keep','reason':'完整'}}
    if action=='missing':decision={}
    if action=='unknown':decision['P1']['action']='delete'
    if action=='empty_replace':decision['P1'].update(action='replace',points=[])
    if action in {'merge_unknown','reuse_unknown'}:
        decision['P1'].update(action=action.split('_')[0],target='missing',same_claim=True,same_scope=True,same_symbols=True)
    if action=='extra':decision['P1']['statement']='越界改写'
    with pytest.raises(ValueError):apply_decisions(rows,[],decision)


def test_replacement_and_context_keep_the_original_decisions():
    from knowledge_registry_identity import apply_decisions
    rows=[{**claim(),'key':key,'input_material_keys':['S1']} for key in ['P1','P2']]
    result=apply_decisions(rows,[],{'P1':{'action':'replace','points':[claim('规则甲成立'),claim('规则乙成立')],'reason':'两条独立规则'},
        'P2':{'action':'context','reason':'仅是教学安排'}})
    assert len(result['points'])==2 and result['points'][0]['key']=='P1_1'
    assert result['context_records'][0]['original']==rows[1]


@pytest.mark.asyncio
async def test_failed_names_continue_reuses_candidates_and_identity_and_old_job_is_unchanged(svc,monkeypatch):
    setup_course(svc,monkeypatch);calls=[];broken=True
    async def call(prompt,**kwargs):
        payload=json.loads(prompt.split('\nINPUT_JSON:\n')[1]);calls.append(payload['stage'])
        if payload['stage']=='knowledge_discovery':return discovery_reply(payload)
        if payload['stage']=='knowledge_atomize':return atomic_reply(payload)
        if payload['stage']=='candidate_semantic_review':return semantic_reply(payload)
        if payload['stage']=='coverage_extract':return json.dumps({'points':{u['key']:[claim()] for u in payload['units']}})
        if payload['stage']=='identity_review':return json.dumps({'decisions':{p['key']:{'action':'keep','reason':'完整'} for p in payload['candidates']}})
        if payload['stage']=='candidate_names':
            return json.dumps({'names':{} if broken else {p['key']:{'name':'压栈把新元素放到栈顶','meta_question':'压栈有什么作用'} for p in payload['points']}})
        raise AssertionError(payload['stage'])
    svc.provider_factory=lambda:SimpleNamespace(_call_llm=call,client=None,model_smart='qwen3.8-27b')
    view=svc.view('c-pilot',source_mode='handouts')
    def start(rid,**kw):
        return svc.start('c-pilot','tree',rid,view['knowledge_revision'],view['document_revision'],
            source_mode='handouts',lesson_id='cpu',pipeline='inventory_atomic_v1',extraction_mode='single_pass_v1',
            organize_hierarchy=False,include_relations=False,**kw)[0]
    job=start('first');await svc.run('c-pilot',job['id'])
    before=deepcopy(svc.authoring.get_job('c-pilot',job['id']))
    assert before['status']=='failed'
    from knowledge_atomic import project_preview
    assert project_preview(before,'c-pilot')['knowledge_points']
    assert calls==['knowledge_discovery','knowledge_atomize','candidate_semantic_review','identity_review','candidate_names','candidate_names']
    broken=False;calls.clear()
    resumed=start('second',resume_job_id=job['id']);await svc.run('c-pilot',resumed['id'])
    assert svc.authoring.get_job('c-pilot',resumed['id'])['status']=='completed'
    assert calls==['candidate_names']
    assert svc.authoring.get_job('c-pilot',job['id'])==before


def test_relation_proposals_use_ids_and_keep_cyclic_proposals_visible():
    from knowledge_registry_relations import compile_edges,attach,prompt
    points=[{'key':f'K{i}','knowledge_id':f'kp{i}','revision_id':'r','name':'名称',
             'statement':'完整知识','conditions':[],'section_refs':['L1']} for i in range(1,3)]
    tree={'knowledge_points':points,'relations':[],'atomic_assessment':{}}
    payload={'reviews':{'K1':'建议先学'},'edges':[{'source':'K1','target':'K2','type':'prerequisite',
        'necessity':'recommended','reason':'理解甲有助于理解乙','context':'学习顺序','conditions':[],'steps':[]}]}
    edges=compile_edges(payload,tree,['K1'],'L1')
    assert edges[0]['source_id']=='kp1'
    assert 'sq' not in prompt(tree,['K1']) and '逐字' not in prompt(tree,['K1'])
    reverse=deepcopy(payload);reverse['edges'][0].update(source='K2',target='K1')
    result=attach(tree,[{'focus_keys':['K1'],'result':edges+compile_edges(reverse,tree,['K1'],'L1')}])
    assert len(result['relations'])==1
    assert result['relation_assessment']['excluded_relations']
    bad=deepcopy(payload);bad['edges'][0]['target']='missing'
    with pytest.raises(ValueError):compile_edges(bad,tree,['K1'],'L1')


def test_composite_repetition_can_map_to_multiple_registered_claims_without_new_leaves():
    from knowledge_registry_identity import apply_decisions
    rows=[{**claim(statement),'key':key,'input_material_keys':[material]} for key,statement,material in [
        ('P1','速度是位移对时间的导数','S1'),('P2','加速度是速度对时间的导数','S2'),
        ('P3','速度是位移对时间的导数，加速度是速度对时间的导数','S3')]]
    decisions={key:{'action':'keep','reason':'独立完整规则'} for key in ['P1','P2']}
    decisions['P3']={'action':'covered','reason':'组合重复，没有新增关系',
        'complete_coverage':True,'adds_knowledge':False,'same_scope':True,
        'parts':[{'target':'P1','claim':'速度定义'},{'target':'P2','claim':'加速度定义'}]}
    result=apply_decisions(rows,[],decisions)
    assert len(result['points'])==2 and not result['issues']
    assert all('S3' in p['input_material_keys'] for p in result['points'])
    assert all(p['identity_members'][-1]['statement']==rows[2]['statement'] for p in result['points'])
    decisions['P3']['adds_knowledge']=True
    with pytest.raises(ValueError):apply_decisions(rows,[],decisions)


def test_relation_review_errors_identify_the_exact_missing_and_extra_keys():
    from knowledge_registry_relations import compile_edges
    with pytest.raises(ValueError) as exc:
        compile_edges({'reviews':{'K2':'错误范围'},'edges':[]},{'knowledge_points':[]},['K1'],'L1')
    assert 'K1' in str(exc.value) and 'K2' in str(exc.value)


def test_relation_bucket_is_not_a_second_knowledge_boundary():
    from knowledge_registry_relations import compile_edges
    points=[{'key':f'K{i}','knowledge_id':f'kp{i}','revision_id':'r','name':'名称',
             'statement':'完整知识','conditions':[],'section_refs':['L1']} for i in range(1,4)]
    value={'reviews':{'K1':'没有直接关系'},'edges':[{'source':'K2','target':'K3','type':'prerequisite',
        'necessity':'recommended','reason':'先学有助于理解','context':'同讲学习','conditions':[],'steps':[]}]}
    assert len(compile_edges(value,{'knowledge_points':points},['K1'],'L1'))==1
    for p in points[1:]:p['section_refs']=['L2']
    with pytest.raises(ValueError,match='讲次'):
        compile_edges(value,{'knowledge_points':points},['K1'],'L1')


@pytest.mark.parametrize('action',['match','reuse'])
def test_identity_target_namespace_determines_reuse_or_current_merge(action):
    from knowledge_registry_identity import apply_decisions
    rows=[{**claim(),'key':key,'input_material_keys':['S1']} for key in ['P1','P2']]
    result=apply_decisions(rows,[],{'P1':{'action':'keep','reason':'规范点'},
        'P2':{'action':action,'target':'P1','same_claim':True,'same_scope':True,'same_symbols':True,'reason':'同一知识'}})
    assert len(result['points'])==1 and len(result['points'][0]['identity_members'])==2


def test_replay_revalidates_complete_saved_response_without_mutating_history():
    from knowledge_registry_pipeline import replay_saved
    record={'status':'failed','attempts':[{'raw_response':'{"names":{"K1":{"name":"规则成立","meta_question":"说明规则"}}}'}]}
    before=deepcopy(record)
    from knowledge_registry_contract import parse_names
    value,result=replay_saved(record,lambda v:parse_names(v,[{'key':'K1'}]))
    assert result['K1']['name']=='规则成立' and record==before
    assert replay_saved(record,lambda v:parse_names(v,[{'key':'K2'}])) is None


@pytest.mark.asyncio
async def test_profile_failure_resumes_only_profile_and_keeps_frozen_identity(svc,monkeypatch):
    setup_course(svc,monkeypatch);broken=True;calls=[]
    async def call(prompt,**kwargs):
        payload=json.loads(prompt.split('\nINPUT_JSON:\n')[1]);stage=payload['stage'];calls.append(stage)
        if stage=='knowledge_discovery':return discovery_reply(payload)
        if stage=='knowledge_atomize':return atomic_reply(payload)
        if stage=='candidate_semantic_review':return semantic_reply(payload)
        if stage=='coverage_extract':return json.dumps({'points':{'U1':[claim()]}})
        if stage=='identity_review':return json.dumps({'decisions':{p['key']:{'action':'keep','reason':'完整'} for p in payload['candidates']}})
        if stage=='candidate_names':return json.dumps({'names':{p['key']:{'name':'压栈把新元素放到栈顶','meta_question':'描述压栈'} for p in payload['points']}})
        if stage=='kc_profiles':
            from third_party.learningmap.kc import KCSkill
            return json.dumps({'profiles':{} if broken else {p['key']:{field:'教学说明' for field in KCSkill.model_fields} for p in payload['profiles']}})
        raise AssertionError(stage)
    svc.provider_factory=lambda:SimpleNamespace(_call_llm=call,client=None,model_smart='qwen3.8-27b')
    view=svc.view('c-pilot',source_mode='handouts')
    def start(request,**kw):return svc.start('c-pilot','tree',request,view['knowledge_revision'],view['document_revision'],source_mode='handouts',lesson_id='cpu',pipeline='inventory_atomic_v1',extraction_mode='single_pass_v1',organize_hierarchy=False,include_relations=False,**kw)[0]
    job=start('profile-first',teaching_focus=['基础操作']);await svc.run('c-pilot',job['id'])
    old=deepcopy(svc.authoring.get_job('c-pilot',job['id']))
    assert old['status']=='failed'
    frozen=old['checkpoint']['atomic_pipeline']['preview_tree']['knowledge_points'][0]
    broken=False;calls.clear()
    new=start('profile-resume',resume_job_id=job['id']);await svc.run('c-pilot',new['id'])
    out=svc.authoring.get_job('c-pilot',new['id'])
    assert out['status']=='completed',out.get('error')
    assert calls==['kc_profiles']
    point=out['checkpoint']['candidate']['knowledge_points'][0]
    assert point['knowledge_id']==frozen['knowledge_id'] and point['revision_id']==frozen['revision_id']
    assert point['kc_skill_profile']['knowledge_id']==point['knowledge_id']
    assert svc.authoring.get_job('c-pilot',job['id'])==old


def test_relation_review_can_include_other_valid_catalog_points_without_retry():
    from knowledge_registry_relations import compile_edges
    tree={'knowledge_points':[{'key':'K1'},{'key':'K2'}]}
    assert compile_edges({'reviews':{'K1':'无需额外关系','K2':'额外有效说明'},'edges':[]},tree,['K1'],'L1')==[]
    with pytest.raises(ValueError):compile_edges({'reviews':{'K2':'遗漏焦点'},'edges':[]},tree,['K1'],'L1')
    with pytest.raises(ValueError):compile_edges({'reviews':{'K1':'说明','UNKNOWN':'未知ID'},'edges':[]},tree,['K1'],'L1')


def test_fresh_generation_does_not_silently_inherit_a_supplied_plan(svc,monkeypatch):
    setup_course(svc,monkeypatch)
    view=svc.view('c-pilot',source_mode='handouts')
    units=[{'statement':claim()['statement'],'branch':'栈','knowledge_type':'rule','profile_focus':'','check_intent':'独立描述入栈'}]
    def start(rid,**kw):return svc.start('c-pilot','tree',rid,view['knowledge_revision'],view['document_revision'],source_mode='handouts',lesson_id='cpu',pipeline='inventory_atomic_v1',extraction_mode='single_pass_v1',**kw)[0]
    first=start('supplied',coverage_units=units);svc.authoring.update_job('c-pilot',first['id'],status='completed')
    inherited=start('inherited');assert inherited['coverage_units']==[]
    svc.authoring.update_job('c-pilot',inherited['id'],status='cancelled')
    cleared=start('cleared',coverage_units=[]);assert cleared['coverage_units']==[]
    svc.authoring.update_job('c-pilot',cleared['id'],status='completed')
    after_clear=start('after-clear');assert after_clear['coverage_units']==[]
    svc.authoring.update_job('c-pilot',after_clear['id'],status='cancelled')
    provided_again=start('provided-again',coverage_units=units)
    svc.authoring.update_job('c-pilot',provided_again['id'],status='completed')
    original=svc._context
    def changed(*args,**kwargs):
        context=deepcopy(original(*args,**kwargs));context['evidence_package']['package_revision_id']='new-materials';return context
    monkeypatch.setattr(svc,'_context',changed)
    fresh=start('new-materials');assert fresh['coverage_units']==[]
    assert svc.authoring.get_job('c-pilot',first['id'])['coverage_units']==units


@pytest.mark.asyncio
async def test_atomization_resume_reuses_discovery_and_completed_single_claim(svc,monkeypatch):
    setup_course(svc,monkeypatch);broken=True;calls=[]
    async def call(prompt,**kwargs):
        payload=json.loads(prompt.split('\nINPUT_JSON:\n')[1]);stage=payload['stage'];calls.append(stage)
        if stage=='knowledge_discovery':
            value=json.loads(discovery_reply(payload));value['points'].append({**value['points'][0],'statement':'出栈移走栈顶元素'});return json.dumps(value)
        if stage=='knowledge_atomize':
            assert len(payload['candidates'])==1
            value=json.loads(atomic_reply(payload));key=payload['candidates'][0]['key']
            if broken and key.endswith('P2'):value['items'][key]['points']=[]
            return json.dumps(value)
        if stage=='candidate_semantic_review':return semantic_reply(payload)
        if stage=='identity_review':return json.dumps({'decisions':{p['key']:{'action':'keep','reason':'独立'} for p in payload['candidates']}})
        if stage=='candidate_names':return json.dumps({'names':{p['key']:{'name':p['statement'],'meta_question':'解释该规则'} for p in payload['points']}})
        raise AssertionError(stage)
    svc.provider_factory=lambda:SimpleNamespace(_call_llm=call,client=None,model_smart='qwen3.8-27b')
    view=svc.view('c-pilot',source_mode='handouts')
    def start(rid,**kw):return svc.start('c-pilot','tree',rid,view['knowledge_revision'],view['document_revision'],source_mode='handouts',lesson_id='cpu',pipeline='inventory_atomic_v1',extraction_mode='single_pass_v1',**kw)[0]
    job=start('first-single');await svc.run('c-pilot',job['id']);old=deepcopy(svc.authoring.get_job('c-pilot',job['id']))
    assert old['status']=='failed';batch=old['checkpoint']['atomic_pipeline']['inventory_batches'][0]
    assert batch['atomization_batches'][0]['status']=='completed'
    broken=False;calls.clear();resumed=start('resume-single',resume_job_id=job['id']);await svc.run('c-pilot',resumed['id'])
    out=svc.authoring.get_job('c-pilot',resumed['id']);assert out['status']=='completed',out.get('error')
    assert calls==['knowledge_atomize','candidate_semantic_review','identity_review','candidate_names']
    assert out['checkpoint']['atomic_pipeline']['inventory_batches'][0]['atomization_batches'][0]==batch['atomization_batches'][0]
    assert svc.authoring.get_job('c-pilot',job['id'])==old
