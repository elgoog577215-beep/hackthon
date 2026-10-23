"""A complete lesson core uses bounded calls and the original course owner."""
import asyncio
from copy import deepcopy
import json
import threading
from types import SimpleNamespace

import pytest

from backend.tests.test_knowledge_first import svc
from backend.tests.test_knowledge_atomic import setup_course


def row(name='入栈', statement='入栈将新元素放到栈顶。'):
    return [name, statement, 'rule', [], [], ['栈', '基本操作'], ['判断新元素加入的位置']]


def review(points, materials):
    return {'keep': [p['key'] for p in points], 'correct': {}, 'split': {}, 'match': {},
            'checks': {}, 'context': {}, 'uncertain': {}, 'add': [], 'names': {}, 'paths': {},
            'types': {}, 'coverage': {m['key']: ['complete', '已检查独立结论与必要条件'] for m in materials}}


def test_core_material_groups_retain_every_unabridged_input():
    from knowledge_core_contract import group_materials
    material = [{'key': f'S{i}', 'text': '完整材料' * 110} for i in range(16)]
    groups = group_materials(material)
    assert len(groups) <= 8
    assert [m for g in groups for m in g] == material


def test_balancing_does_not_create_an_extra_serial_wave_for_uneven_units():
    from knowledge_core_contract import group_materials
    sizes=[600,900,500,450,1300,800,500,600,1000,800,1000,750,1300,350,1200,650]
    material=[{'key':f'S{i}','text':'a'*size} for i,size in enumerate(sizes)]
    groups=group_materials(material,target_chars=3500)
    assert len(groups)==4
    assert [m for group in groups for m in group]==material


def test_core_review_keeps_conditions_splits_and_explicit_shared_checks():
    from knowledge_core_contract import parse_extraction, compile_review
    reminder=row('操作提醒', '应用完整规则时漏写一个操作位置。');reminder[2]='comparison'
    points = parse_extraction({'points': [row(), row('组合结论', '和与常数倍分别求导。'), reminder], 'context_note': ''}, 'B1', ['S1'])
    value = review(points, [{'key': 'S1'}])
    value['keep'] = [points[0]['key']]
    value['split'][points[1]['key']] = [row('和求导', '可导函数的和的导数等于导数的和。'), row('常数倍求导', '常数倍函数的导数等于常数乘原函数的导数。')]
    value['checks'][points[2]['key']] = {'target': points[0]['key'], 'intent': '独立辨别操作规则', 'reason': '错误表现作为检查，不另建叶子',
        'same_scope':True,'adds_knowledge':False,'operational_only':True}
    result = compile_review(value, points, [], [{'key': 'S1'}])
    assert len(result['registry']['points']) == 3
    assert result['registry']['check_resolutions']
    assert len(result['frozen_units']) == 3


def test_truth_patch_cannot_overwrite_ancillary_fields_or_skip_any_claim():
    from knowledge_core_contract import parse_extraction, compile_review
    points = parse_extraction({'points': [row('导函数奇偶性', '偶函数的导函数是偶函数。')], 'context_note': ''}, 'B1', ['S1'])
    points[0]['examples'] = ['保留的示例']
    value = review(points, [{'key': 'S1'}]); key = points[0]['key']
    value['keep'] = []
    value['correct'][key] = {'statement': '在关于原点对称的可导定义域上，偶函数的导函数是奇函数。', 'conditions': ['定义域关于原点对称且函数可导'], 'symbol_definitions': []}
    result = compile_review(value, points, [], [{'key': 'S1'}])
    assert result['registry']['points'][0]['examples'] == ['保留的示例']
    value['correct'][key]['examples'] = []
    with pytest.raises(ValueError): compile_review(value, points, [], [{'key': 'S1'}])
    value['correct'] = {}
    with pytest.raises(ValueError): compile_review(value, points, [], [{'key': 'S1'}])


def test_open_draft_type_requires_explicit_classification_before_publication():
    from knowledge_core_contract import parse_extraction, compile_review
    source=row();source[2]='domain-specific-label'
    points=parse_extraction({'points':[source],'context_note':''},'B1',['S1'])
    assert points[0]['knowledge_type']=='domain-specific-label'
    value=review(points,[{'key':'S1'}])
    with pytest.raises(ValueError):compile_review(value,points,[],[{'key':'S1'}])
    value['types']={points[0]['key']:'rule'}
    assert compile_review(value,points,[],[{'key':'S1'}])['registry']['points'][0]['knowledge_type']=='rule'


def test_combined_review_schema_separates_material_keys_from_candidate_decisions():
    from knowledge_core_contract import review_schema, parse_extraction, compile_review
    points=parse_extraction({'points':[row()],'context_note':''},'B1',['S1'])
    schema=review_schema(points,[{'key':'S1'}]);decisions=schema['properties']['decisions']
    assert decisions['required']==['B1P1'] and decisions['additionalProperties'] is False
    assert set(decisions['properties']['B1P1']['properties']['type']['enum'])=={'definition','rule','method','comparison'}
    value={'decisions':{'B1P1':{'type':'rule','action':'keep','test':'检查空栈与非空栈的插入位置'}},
           'add':[],'coverage':{'S1':['complete','完整操作已承载']}}
    assert compile_review(value,points,[],[{'key':'S1'}])['registry']['points'][0]['truth_review']['test_case']
    value['decisions']['S1']={'type':'rule','action':'keep','test':'材料不是候选'}
    with pytest.raises(ValueError):compile_review(value,points,[],[{'key':'S1'}])


@pytest.mark.asyncio
async def test_core_finishes_with_one_extraction_and_one_combined_audit(svc, monkeypatch):
    setup_course(svc, monkeypatch)
    calls = []
    async def model(prompt, **kwargs):
        payload = json.loads(prompt.split('\nINPUT_JSON:\n')[1]); calls.append(payload['stage'])
        if payload['stage'] == 'candidate_core_extract':
            return json.dumps({'points': [row(), row('出栈', '出栈移除并返回栈顶元素。')], 'context_note': ''})
        assert payload['stage'] == 'candidate_core_review'
        return json.dumps(review(payload['points'], payload['materials']))
    svc.provider_factory = lambda: SimpleNamespace(_call_llm=model, model_smart='test-qwen', client=None)
    before = deepcopy(svc.repository.load_raw('c-pilot')); view = svc.view('c-pilot', source_mode='handouts')
    job = svc.start('c-pilot', 'tree', 'core', view['knowledge_revision'], view['document_revision'], source_mode='handouts',
                    lesson_id='cpu', pipeline='inventory_atomic_v1', generation_mode='core_v1', organize_hierarchy=True)[0]
    event_thread=threading.get_ident();on_loop=[];project=svc.authoring.read_projection
    def recorded(*args,**kwargs):
        if threading.get_ident()==event_thread:on_loop.append('read_projection')
        return project(*args,**kwargs)
    monkeypatch.setattr(svc.authoring,'read_projection',recorded)
    await svc.run('c-pilot', job['id'])
    assert not on_loop, 'the model request path waited for the course lock on the HTTP loop'
    monkeypatch.setattr(svc.authoring,'read_projection',project)
    saved = svc.authoring.get_job('c-pilot', job['id'])
    assert saved['status'] == 'completed', saved.get('error')
    tree = saved['checkpoint']['candidate']
    assert len(tree['knowledge_points']) == 2
    assert tree['atomic_assessment']['ready_for_adoption']
    assert all(len(p['name']) < 15 and p['conditions'] == [] for p in tree['knowledge_points'])
    assert tree['generation_contract'] == 'knowledge_core_v1'
    assert tree['relations'] == [] and not any(p.get('kc_skill_profile') for p in tree['knowledge_points'])
    assert calls == ['candidate_core_extract', 'candidate_core_review']
    assert svc.repository.load_raw('c-pilot') == before
    assert svc.view('c-pilot', source_mode='handouts')['candidate']['revision_id'] == tree['revision_id']


def test_get_job_projects_only_the_requested_job_without_copying_all_history(svc, monkeypatch):
    job = svc.authoring.create_job('c-pilot', 'tree', job_type='course_knowledge_tree_generation')
    monkeypatch.setattr(svc.authoring, 'load', lambda *_: pytest.fail('a job read copied all course history'))
    assert svc.authoring.get_job('c-pilot', job['id'])['id'] == job['id']


def test_model_response_attachments_are_durable_and_cannot_change_job_state(svc, monkeypatch):
    job=svc.authoring.create_job('c-pilot','tree',job_type='course_knowledge_tree_generation',
        initial_fields={'actor':'owner','source_context_revision':'frozen'})
    before=svc.authoring._path('c-pilot').read_bytes()
    monkeypatch.setattr(svc.authoring,'_save',lambda *_:pytest.fail('a small response rewrote all history'))
    svc.authoring.save_knowledge_response('c-pilot',job['id'],job['id'],'request-1','{"points":[]}')
    fresh=type(svc.authoring)(svc.authoring.root)
    assert fresh.read_knowledge_response('c-pilot',job['id'],job['id'],'request-1')=='{"points":[]}'
    assert svc.authoring._path('c-pilot').read_bytes()==before
    with pytest.raises(ValueError):svc.authoring.save_knowledge_response('c-pilot',job['id'],job['id'],'request-1','different result')
    with pytest.raises(ValueError):fresh.read_knowledge_response('c-pilot',job['id'],job['id'],'../outside')


@pytest.mark.asyncio
async def test_parallel_batches_do_not_each_commit_the_full_course(svc,monkeypatch):
    setup_course(svc,monkeypatch)
    state=svc.authoring.load('c-pilot')
    state['lessons']['cpu']['script_revisions'][0]['sections'][0]['blocks']=[
        {'block_id':f'b{i}','content':('独立操作的定义和边界。'*200),'status':'completed'} for i in range(3)]
    svc.authoring._save(state)
    writes=[];save=svc.authoring._save
    def recorded(value):writes.append(1);return save(value)
    monkeypatch.setattr(svc.authoring,'_save',recorded)
    async def model(prompt,**kwargs):
        p=json.loads(prompt.split('\nINPUT_JSON:\n')[1])
        if p['stage']=='candidate_core_extract':
            await asyncio.sleep(.02*int(p['materials'][0]['key'][1:]))
            return json.dumps({'points':[row(p['materials'][0]['key'],'独立操作的完整规则。')],'context_note':''})
        return json.dumps(review(p['points'],p.get('coverage_materials',p['materials'])))
    svc.provider_factory=lambda:SimpleNamespace(_call_llm=model,model_smart='test',client=None)
    view=svc.view('c-pilot',source_mode='handouts')
    job=svc.start('c-pilot','tree','bounded-writes',view['knowledge_revision'],view['document_revision'],
        source_mode='handouts',lesson_id='cpu',pipeline='inventory_atomic_v1',generation_mode='core_v1')[0]
    await svc.run('c-pilot',job['id'])
    assert svc.authoring.get_job('c-pilot',job['id'])['status']=='completed'
    assert len(writes)<=4, 'completed batches should persist small attachments before the phase commit'
