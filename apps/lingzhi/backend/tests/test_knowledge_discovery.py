from copy import deepcopy
import pytest


def point(text='可导函数的常数倍可逐项求导'):
    return {'statement':text,'knowledge_type':'rule','conditions':[], 'symbol_definitions':[],
            'teaching_context':[],'examples':[], 'branch':'规则','profile_focus':'',
            'check_intents':['在新情境中应用这一规则']}


def test_discovery_reads_complete_small_material_batches_without_global_summary():
    from knowledge_discovery import material_batches,discovery_prompt
    materials=[{'key':f'S{i}','text':'完整材料'+str(i)} for i in range(5)]
    batches=material_batches(materials)
    assert [key for b in batches for key in b['source_keys']]==[m['key'] for m in materials]
    assert max(len(b['source_keys']) for b in batches)<=2
    prompt=discovery_prompt({'course_name':'课程'},'本讲',[materials[0]],[])
    assert '完整材料0' in prompt and '完整材料1' not in prompt
    assert 'coverage_plan' not in prompt and '指定知识清单' not in prompt


def test_discovered_claims_are_not_reexpanded_or_rewritten_by_program():
    from knowledge_discovery import parse_discovery,discovered_units
    payload={'points':[point('法线过切点且垂直于切线'),point('法线斜率为切线斜率的负倒数')],'context_note':''}
    before=deepcopy(payload)
    rows=parse_discovery(payload,'inventory-1',['S1'],[])
    assert payload==before and len(rows)==2
    assert rows[0]['statement']==payload['points'][0]['statement']
    assert rows[0]['coverage_unit_ids']!=rows[1]['coverage_unit_ids']
    units=discovered_units(rows)
    assert [u['statement'] for u in units]==[p['statement'] for p in rows]
    assert units[0]['key']==rows[0]['coverage_unit_ids'][0]
    assert rows[0]['input_material_keys']==['S1']


def test_context_only_material_is_recorded_without_inventing_leaves():
    from knowledge_discovery import parse_discovery
    assert parse_discovery({'points':[],'context_note':'本块只有课堂安排'},'b',['S1'],[])==[]
    with pytest.raises(ValueError):parse_discovery({'points':[],'context_note':''},'b',['S1'],[])
    with pytest.raises(ValueError):parse_discovery({'points':[point()],'context_note':'','unexpected':1},'b',['S1'],[])


def test_atomicization_keeps_each_complete_claim_and_inherits_only_tracking_metadata():
    from knowledge_discovery import parse_discovery,parse_atoms
    from knowledge_registry_contract import FIELDS
    original=parse_discovery({'points':[point('两个独立结论')],'context_note':''},'b',['S1'],[])
    key=original[0]['key'];row={k:v for k,v in point().items() if k in {'statement','knowledge_type','conditions','check_intents'}}
    response={'items':{key:{'disposition':'knowledge','reason':'两个独立可检查的结论',
        'points':[{**row,'statement':'完整结论甲'},{**row,'statement':'完整结论乙'}]}}}
    result=parse_atoms(response,original)
    assert [p['statement'] for p in result]==['完整结论甲','完整结论乙']
    assert result[0]['coverage_unit_ids']!=result[1]['coverage_unit_ids']
    assert all(p['discovery_parent_key']==key and p['input_material_keys']==['S1'] for p in result)
    with pytest.raises(ValueError):parse_atoms({'items':{}},original)
    response['items'][key]['points']=[]
    with pytest.raises(ValueError):parse_atoms(response,original)
    response['items'][key]['disposition']='example'
    assert parse_atoms(response,original)==[]


def test_atomization_request_never_regroups_claims_into_a_summary():
    from knowledge_discovery import atomization_prompt
    with pytest.raises(ValueError):atomization_prompt([point(),point()])
