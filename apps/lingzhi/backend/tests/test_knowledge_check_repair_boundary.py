from copy import deepcopy
import json
import pytest

from backend.tests.test_knowledge_first import svc
from backend.tests.test_knowledge_validation_pipeline import context_for
from backend.tests.test_knowledge_correction_protocol import bound_response
from backend.tests.test_knowledge_extraction_repair import point


@pytest.mark.parametrize('label',['与极值点关系','与极值点的关系','与极值点的逻辑关系','与极值点之间的必要条件关系','逻辑关系'])
def test_relation_wording_does_not_change_explicit_object_grounding(label):
    from knowledge_relation_binding import seal_binding, CONTRACT
    from knowledge_semantic_contract import quality_point
    p=point('静止点',property=label,value='未必是极值点')
    source='静止点未必是极值点。';before=deepcopy(p)
    binding=seal_binding(p,source,{'kind':'relation','target':'极值点','relation_type':'必要条件关系'})
    _,audit=quality_point(p,source,semantic_roles=True,relation_binding_contract=CONTRACT,relation_binding=binding)
    assert audit['relation_binding']['target']=='极值点'
    assert source[audit['relation_binding']['source_span']['start']:audit['relation_binding']['source_span']['end']]=='极值点'
    assert p==before


def test_unresolved_binding_is_not_missing_source_and_explicit_absence_is_diagnosable():
    from knowledge_relation_binding import seal_binding,CONTRACT
    from knowledge_semantic_contract import quality_point
    from knowledge_correction_plan import KnowledgePointValidationError
    p=point('静止点',property='与极值点的逻辑关系',value='未必是极值点');source='静止点未必是极值点。'
    with pytest.raises(KnowledgePointValidationError) as exc:quality_point(p,source,semantic_roles=True,relation_binding_contract=CONTRACT)
    assert [d['code'] for d in exc.value.diagnostics]==['relation_binding_required']
    p={**p,'property':'与不存在的对象的关系'}
    binding=seal_binding(p,source,{'kind':'relation','target':'不存在的对象','relation_type':'逻辑关系'})
    with pytest.raises(KnowledgePointValidationError) as exc:quality_point(p,source,semantic_roles=True,relation_binding_contract=CONTRACT,relation_binding=binding)
    assert exc.value.diagnostics[0]['code']=='relation_source_missing'
    assert exc.value.diagnostics[0]['actual']=='不存在的对象'
    assert exc.value.diagnostics[0]['field']=='relation_binding.target'


def test_binding_cannot_pick_the_subject_or_an_unmentioned_source_word():
    from knowledge_relation_binding import seal_binding,CONTRACT
    from knowledge_semantic_contract import quality_point
    from knowledge_correction_plan import KnowledgePointValidationError
    p=point('静止点',property='与极值点的逻辑关系',value='未必是极值点');source='静止点未必是极值点。此处另提到连续。'
    for target,code in [('静止点','relation_binding_self_target'),('连续','relation_target_unresolved')]:
        b=seal_binding(p,source,{'kind':'relation','target':target,'relation_type':'逻辑关系'})
        with pytest.raises(KnowledgePointValidationError) as exc:quality_point(p,source,semantic_roles=True,relation_binding_contract=CONTRACT,relation_binding=b)
        assert exc.value.diagnostics[0]['code']==code


@pytest.mark.asyncio
async def test_no_effect_repair_stops_without_repeating_an_identical_request(svc,monkeypatch):
    from knowledge_extraction_repair import correct_points,KnowledgeRepairNoProgress
    from knowledge_extract import compile_extraction
    raw,context=context_for(svc,monkeypatch);context['knowledge_correction_contract']='knowledge_correction_plan_v5'
    original=bound_response(context);calls=[];record={}
    async def call(*args):
        calls.append(1)
        return json.dumps({'repairs':{'S1.1:0':{'handling':'patch','patch':{'subject':'虚构主体'},'reason':'已经修正'}},'short_statements':{'S1.1:0':['入栈把元素加入栈顶']},'source_issues':[]})
    monkeypatch.setattr('knowledge_atomic.call_stage',call)
    with pytest.raises(KnowledgeRepairNoProgress):
        await correct_points(svc,'c-pilot','j',None,raw,context,['S1'],1,original,record,
            compile_result=lambda r:compile_extraction(raw,context,['S1'],1,r),validate_source=lambda:None,max_attempts=2)
    assert calls==[1] and len(record['attempts'])==1
    assert record['validation_error']['diagnostics'][0]['code']=='repair_no_effect'
    assert original['passages']['S1.1']['points'][0]['subject']=='虚构主体'


@pytest.mark.asyncio
async def test_alignment_repairs_metadata_without_rewording_a_valid_fact(svc,monkeypatch):
    from knowledge_relation_binding import CONTRACT,with_bindings
    from knowledge_extraction_repair import correct_points
    from knowledge_expression import bind_name
    from knowledge_extract import compile_extraction
    from backend.tests.test_knowledge_extraction_repair import value
    raw,context=context_for(svc,monkeypatch)
    context.update(knowledge_correction_contract='knowledge_correction_plan_v5',relation_binding_contract=CONTRACT)
    source='入栈与栈顶的逻辑关系是把元素加入栈顶。'
    passages=[{'key':'S1.1','source_key':'S1','start':0,'end':len(source),'text':source}]
    for module in ['knowledge_extraction_repair','knowledge_semantic_contract']:
        monkeypatch.setattr(module+'.passage_catalog',lambda *args,**kw:deepcopy(passages))
    p=point(property='与栈顶的逻辑关系');name='入栈把元素加入栈顶'
    original=value([p]);original['_expression_contract']='knowledge_expression_v1'
    original['_content_review_trace']=[{'expression':bind_name(name,p,source)}];before=deepcopy(original)
    async def call(*args):
        data=json.loads(args[-2].split('\nINPUT_JSON:\n')[1]);plan=data['targets']['S1.1:0']['correction_plan']
        assert plan['binding_only'] and plan['editable_fields']==[]
        return json.dumps({'repairs':{'S1.1:0':{'handling':'bind_relation','bindings':[{'kind':'relation','target':'栈顶','relation_type':'操作作用'}],'reason':'对象有原文位置'}},'short_statements':{'S1.1:0':[name]},'source_issues':[]})
    monkeypatch.setattr('knowledge_atomic.call_stage',call)
    from knowledge_semantic_contract import quality_point
    def compile_bound(response):
        binding=response['_content_review_trace'][0]['relation_binding']
        return quality_point(response['passages']['S1.1']['points'][0],source,semantic_roles=True,relation_binding_contract=CONTRACT,relation_binding=binding)
    output,result=await correct_points(svc,'c-pilot','j',None,raw,context,['S1'],1,original,{},compile_result=compile_bound,validate_source=lambda:None,max_attempts=2)
    assert output['passages']==original['passages'] and original==before
    assert output['_content_review_trace'][0]['expression']==before['_content_review_trace'][0]['expression']
    assert result[1]['relation_binding']['target']=='栈顶'


def test_binding_is_invalidated_by_changed_claim_or_source_and_does_not_waive_compound_properties():
    from knowledge_relation_binding import seal_binding,CONTRACT
    from knowledge_semantic_contract import quality_point
    from knowledge_correction_plan import KnowledgePointValidationError
    p=point('方法',property='与时间的关系',value='有关');source='方法涉及时间和空间。'
    b=seal_binding(p,source,{'kind':'relation','target':'时间','relation_type':'关联'})
    for updated,text in [({**p,'value':'无关'},source),(p,source+'新增内容。')]:
        with pytest.raises(KnowledgePointValidationError) as exc:quality_point(updated,text,semantic_roles=True,relation_binding_contract=CONTRACT,relation_binding=b)
        assert any(d['code']=='relation_binding_stale' for d in exc.value.diagnostics)
    compound={**p,'property':'与时间和空间的关系'};b=seal_binding(compound,source,{'kind':'relation','target':'时间','relation_type':'关联'})
    with pytest.raises(KnowledgePointValidationError) as exc:quality_point(compound,source,semantic_roles=True,relation_binding_contract=CONTRACT,relation_binding=b)
    assert any(d['code']=='compound_property' for d in exc.value.diagnostics)


@pytest.mark.asyncio
async def test_uncertain_binding_stops_and_preserves_original_evidence(svc,monkeypatch):
    from knowledge_extraction_repair import correct_points
    from knowledge_correction_plan import KnowledgePointValidationError
    from knowledge_relation_binding import CONTRACT
    from knowledge_expression import bind_name
    from backend.tests.test_knowledge_extraction_repair import value
    raw,context=context_for(svc,monkeypatch)
    context.update(knowledge_correction_contract='knowledge_correction_plan_v5',relation_binding_contract=CONTRACT)
    source='入栈把元素加入栈顶。'
    passages=[dict(key='S1.1',source_key='S1',text=source,start=0,end=len(source))]
    monkeypatch.setattr('knowledge_extraction_repair.passage_catalog',lambda *a,**k:deepcopy(passages))
    p=point(property='与栈顶的逻辑关系');name='入栈把元素加入栈顶'
    original=value([p]);original['_content_review_trace']=[{'expression':bind_name(name,p,source)}]
    before=deepcopy(original);calls=[];record={}
    async def call(*args):
        calls.append(1)
        return json.dumps({'repairs':{'S1.1:0':{'handling':'bind_relation',
            'bindings':[{'kind':'uncertain','target':'','relation_type':''}],'reason':'尚不能确定'}},
            'short_statements':{'S1.1:0':[name]},'source_issues':[]})
    monkeypatch.setattr('knowledge_atomic.call_stage',call)
    with pytest.raises(KnowledgePointValidationError) as exc:
        await correct_points(svc,'c-pilot','j',None,raw,context,['S1'],1,original,record,
            compile_result=lambda r:pytest.fail('未确定的绑定不得进入编译'),validate_source=lambda:None,max_attempts=2)
    assert exc.value.diagnostics[0]['code']=='relation_binding_uncertain'
    assert calls==[1] and original==before
    assert record['attempts'][0]['raw_response']


@pytest.mark.asyncio
async def test_valid_binding_survives_a_separate_semantic_failure(svc,monkeypatch):
    from knowledge_extraction_repair import correct_points
    from knowledge_relation_binding import CONTRACT
    from knowledge_expression import bind_name
    from knowledge_semantic_contract import quality_point
    from backend.tests.test_knowledge_extraction_repair import value
    raw,context=context_for(svc,monkeypatch)
    context.update(knowledge_correction_contract='knowledge_correction_plan_v5',relation_binding_contract=CONTRACT)
    source='入栈把元素加入栈顶，栈底保持不变。'
    passages=[dict(key='S1.1',source_key='S1',text=source,start=0,end=len(source))]
    monkeypatch.setattr('knowledge_extraction_repair.passage_catalog',lambda *a,**k:deepcopy(passages))
    p=point(property='与栈顶和栈底的关系',value='改变栈顶而不改变栈底')
    name='入栈改变栈顶而不改变栈底'
    original=value([p]);original['_content_review_trace']=[{'expression':bind_name(name,p,source)}]
    before=deepcopy(original);calls=[];record={}
    async def call(*args):
        payload=json.loads(args[-2].split('\nINPUT_JSON:\n')[1])
        plan=payload['targets']['S1.1:0']['correction_plan'];calls.append(plan)
        if len(calls)==1:
            assert plan['binding_only']
            repair={'handling':'bind_relation','bindings':[{'kind':'relation','target':'栈顶','relation_type':'操作影响'}],'reason':'识别另一对象'}
            names=[name]
        else:
            assert not plan['binding_only']
            assert [d['code'] for d in plan['diagnostics']]==['compound_property']
            assert payload['targets']['S1.1:0']['point']==p
            repair={'handling':'replace','points':[
                point(property='与栈顶的关系'),point(property='与栈底的关系',value='保持不变')],
                'bindings':[{'kind':'relation','target':target,'relation_type':'操作影响'} for target in ['栈顶','栈底']],
                'reason':'两种独立影响分别保留'}
            names=['入栈把元素加入栈顶','入栈不改变栈底']
        return json.dumps({'repairs':{'S1.1:0':repair},'short_statements':{'S1.1:0':names},'source_issues':[]})
    monkeypatch.setattr('knowledge_atomic.call_stage',call)
    def compile_bound(response):
        return [quality_point(p,source,semantic_roles=True,relation_binding_contract=CONTRACT,
            relation_binding=trace['relation_binding']) for p,trace in
            zip(response['passages']['S1.1']['points'],response['_content_review_trace'])]
    output,compiled=await correct_points(svc,'c-pilot','j',None,raw,context,['S1'],1,original,record,
        compile_result=compile_bound,validate_source=lambda:None,max_attempts=2)
    assert len(calls)==2 and len(compiled)==2 and original==before
    staged=record['attempts'][0]['validated_binding_response']
    assert staged['passages']==before['passages']
    assert staged['_content_review_trace'][0]['relation_binding']['target']=='栈顶'
    assert [row['relation_binding']['target'] for row in output['_content_review_trace']]==['栈顶','栈底']
