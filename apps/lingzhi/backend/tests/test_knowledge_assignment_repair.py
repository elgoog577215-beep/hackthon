from copy import deepcopy
import json

import pytest

from course_repository import CourseDocumentConflict


@pytest.mark.asyncio
@pytest.mark.parametrize('invalid',[False,True])
async def test_only_missing_assignments_can_be_filled_and_original_tree_stays_frozen(monkeypatch,invalid):
    from knowledge_hierarchy import repair_assignments
    points=[{'key':'K1','name':'入栈','statement':'入栈插入栈顶','conditions':[]},
        {'key':'K2','name':'出栈','statement':'出栈移除栈顶','conditions':[]}]
    response={'response_contract':'knowledge_hierarchy_v5','categories':[{'key':'S1','name':'操作','scope':'基本操作','parent_key':None}],
        'point_categories':{'K1':'S1'}}
    before=deepcopy(response);task={'key':'C2'};calls=[]
    async def call(*args):
        payload=json.loads(args[-2].split('\nINPUT_JSON:\n')[1]);calls.append(payload)
        assert [p['key'] for p in payload['points']]==['K2']
        assert payload['frozen_assignments']=={'K1':'S1'}
        return json.dumps({'point_categories':{'K2':'S1',**({'K1':'__direct__'} if invalid else {})}})
    monkeypatch.setattr('knowledge_atomic.call_stage',call)
    args=(None,'c','j',None,{}, {'scope_lesson_id':'l'},task,response,points,lambda:None,lambda:None)
    if invalid:
        with pytest.raises(CourseDocumentConflict,match='缺失'):
            await repair_assignments(*args)
        assert task['assignment_repair']['status']=='failed'
    else:
        result=await repair_assignments(*args)
        assert result['point_categories']=={'K1':'S1','K2':'S1'} and result['categories']==response['categories']
        assert task['assignment_repair']['status']=='completed'
    assert response==before and len(calls)==1 and task['assignment_repair']['raw_response']


@pytest.mark.asyncio
async def test_complete_or_unknown_mapping_never_triggers_model_repair(monkeypatch):
    from knowledge_hierarchy import repair_assignments
    async def no_call(*args):pytest.fail('Unneeded model call')
    monkeypatch.setattr('knowledge_atomic.call_stage',no_call)
    for mapping in ({'K1':'S1'},{'foreign':'S1'}):
        response={'categories':[],'point_categories':mapping}
        result=await repair_assignments(None,'c','j',None,{}, {},{},response,[{'key':'K1'}],lambda:None,lambda:None)
        assert result==response
