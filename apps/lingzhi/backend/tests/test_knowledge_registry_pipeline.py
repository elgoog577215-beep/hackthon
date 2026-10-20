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
async def test_default_flow_never_calls_legacy_source_repair_and_preserves_course(svc,monkeypatch):
    setup_course(svc,monkeypatch)
    raw=deepcopy(svc.repository.load_raw('c-pilot'));calls=[]
    async def call(prompt,**kwargs):
        payload=json.loads(prompt.split('\nINPUT_JSON:\n')[1]);calls.append(payload)
        if payload['stage']=='candidate_extract':
            return json.dumps({'points':[claim()],'context_note':''})
        if payload['stage']=='identity_review':
            return json.dumps({'decisions':{p['key']:{'action':'keep','reason':'完整知识'} for p in payload['candidates']}})
        if payload['stage']=='candidate_names':
            return json.dumps({'names':{p['key']:{'name':'压栈把新元素放到栈顶','meta_question':'压栈怎样改变栈？'} for p in payload['points']}})
        pytest.fail('Unexpected legacy stage '+payload['stage'])
    svc.provider_factory=lambda:SimpleNamespace(_call_llm=call,client=None,model_smart='qwen3.8-27b')
    view=svc.view('c-pilot',source_mode='handouts')
    job,_=svc.start('c-pilot','tree','registry-new',view['knowledge_revision'],view['document_revision'],
        source_mode='handouts',lesson_id='cpu',pipeline='inventory_atomic_v1',
        extraction_mode='single_pass_v1',organize_hierarchy=False,include_relations=False)
    await svc.run('c-pilot',job['id'])
    out=svc.authoring.get_job('c-pilot',job['id'])
    assert out['status']=='completed',out.get('error')
    assert [p['stage'] for p in calls]==['candidate_extract','identity_review','candidate_names']
    tree=out['checkpoint']['candidate']
    assert tree['knowledge_points'][0]['statement']==claim()['statement']
    assert tree['provenance_contract']=='input_material_record_v1'
    assert tree['atomic_assessment']['ready_for_adoption']
    assert svc.repository.load_raw('c-pilot')==raw
