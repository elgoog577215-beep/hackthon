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
    binding=seal_binding(p,source,{'kind':'relation','target':'不存在的对象','relation_type':'逻辑关系'})
    with pytest.raises(KnowledgePointValidationError) as exc:quality_point(p,source,semantic_roles=True,relation_binding_contract=CONTRACT,relation_binding=binding)
    assert exc.value.diagnostics[0]['code']=='relation_source_missing'
    assert exc.value.diagnostics[0]['actual']=='不存在的对象'
    assert exc.value.diagnostics[0]['field']=='relation_binding.target'


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
