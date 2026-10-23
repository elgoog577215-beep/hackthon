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
    return dict(n=name, s=statement, t='rule', c=[], y=[], p=['栈', '基本操作'], k=['判断新元素加入的位置'])


def review(points, materials):
    return {'keep': [p['key'] for p in points], 'correct': {}, 'split': {}, 'match': {},
            'checks': {}, 'context': {}, 'uncertain': {}, 'add': [], 'names': {}, 'paths': {},
            'types': {}, 'coverage': {m['key']: ['complete', '已检查独立结论与必要条件'] for m in materials}}


def transport_review(points,materials):
    return {'decisions':{p['key']:{'type':'rule','action':'keep','test':'已检查边界条件与独立规则'} for p in points},
            'add':[],'coverage':{m['key']:['complete','独立知识完整'] for m in materials}}


def test_core_material_groups_retain_every_unabridged_input():
    from knowledge_core_contract import group_materials
    material = [{'key': f'S{i}', 'text': '完整材料' * 110} for i in range(16)]
    groups = group_materials(material)
    assert len(groups) <= 8
    assert [m for g in groups for m in g] == material


def test_extraction_transport_closes_field_positions_without_guessing_knowledge():
    from knowledge_core_contract import extraction_schema,parse_extraction
    from jsonschema import Draft202012Validator
    value={'points':[{'n':'入栈','s':'入栈将元素加入栈顶。','t':'domain-label','c':[], 'y':[], 'p':['栈'],'k':[]}],'context_note':''}
    validator=Draft202012Validator(extraction_schema());assert not list(validator.iter_errors(value))
    points=parse_extraction(value,'B1',['S1'])
    assert points[0]['statement']=='入栈将元素加入栈顶。' and points[0]['unresolved_type']
    value['points'][0]['extra']='不能丢弃或猜补额外列'
    assert list(validator.iter_errors(value))


def test_transport_grammar_preserves_formula_escapes_and_forbids_literal_controls():
    from knowledge_core_contract import extraction_schema
    from jsonschema import Draft202012Validator
    value={'points':[{'n':'公式符号','s':r'当 $x\to0$ 时使用 $\theta$。','t':'rule','c':[], 'y':[], 'p':['符号'],'k':[]}],'context_note':''}
    validator=Draft202012Validator(extraction_schema())
    assert not list(validator.iter_errors(value))
    value['points'][0]['s']='公式包含实际\t制表符'
    assert list(validator.iter_errors(value))


def test_core_math_transport_escapes_tex_only_in_explicit_math_and_preserves_structure():
    from knowledge_core_contract import parse_core_response
    from knowledge_registry_contract import parse_json
    raw = r'{"s":"当 $\Delta x\to0$，$\frac{dy}{dx}$ 存在。","u":"\u516c","key":"S1"}'
    value = parse_core_response(raw)
    assert value == {'s':r'当 $\Delta x\to0$，$\frac{dy}{dx}$ 存在。','u':'公','key':'S1'}
    canonical = json.dumps(value, ensure_ascii=False)
    assert parse_core_response(canonical) == parse_json(canonical)
    for invalid in [r'{"s":"outside \Delta"}', r'{"s":"$\Delta$","s":"duplicate"}', raw[:-1]]:
        with pytest.raises(ValueError):
            parse_core_response(invalid)


def test_balancing_does_not_create_an_extra_serial_wave_for_uneven_units():
    from knowledge_core_contract import group_materials
    sizes=[600,900,500,450,1300,800,500,600,1000,800,1000,750,1300,350,1200,650]
    material=[{'key':f'S{i}','text':'a'*size} for i,size in enumerate(sizes)]
    groups=group_materials(material,target_chars=3500)
    assert len(groups)==4
    assert [m for group in groups for m in group]==material


def test_core_review_keeps_conditions_splits_and_explicit_shared_checks():
    from knowledge_core_contract import parse_extraction, compile_review
    reminder=row('操作提醒', '应用完整规则时漏写一个操作位置。');reminder['t']='comparison'
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
    source=row();source['t']='domain-specific-label'
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


def test_non_owning_review_grammar_has_no_impossible_empty_enumeration():
    from knowledge_core_contract import review_schema
    schema=review_schema([{'key':'P'}],[])
    assert schema['properties']['add']=={'type':'array','maxItems':0}


def test_core_admission_atomically_binds_recovery_batches_before_running(svc,monkeypatch):
    setup_course(svc,monkeypatch);view=svc.view('c-pilot',source_mode='handouts')
    job=svc.start('c-pilot','tree','atomic-core-start',view['knowledge_revision'],view['document_revision'],
        source_mode='handouts',lesson_id='cpu',pipeline='inventory_atomic_v1',generation_mode='core_v1')[0]
    fresh=type(svc.authoring)(svc.authoring.root)
    pipeline=fresh.get_job('c-pilot',job['id'])['checkpoint']['atomic_pipeline']
    assert pipeline['identity_job_id']==job['id'] and pipeline['inventory_batches']


@pytest.mark.asyncio
async def test_core_finishes_with_one_extraction_and_one_combined_audit(svc, monkeypatch):
    setup_course(svc, monkeypatch)
    calls = []
    async def model(prompt, **kwargs):
        payload = json.loads(prompt.split('\nINPUT_JSON:\n')[1]); calls.append(payload['stage'])
        if payload['stage'] == 'candidate_core_extract':
            return json.dumps({'points': [row(), row('出栈', '出栈移除并返回栈顶元素。')], 'context_note': ''})
        assert payload['stage'] == 'candidate_core_review'
        return json.dumps(transport_review(payload['points'], payload.get('coverage_materials',payload['materials'])))
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


@pytest.mark.parametrize('stream',[False,True])
def test_first_live_update_copies_only_its_job(svc,monkeypatch,stream):
    job=svc.authoring.create_job('c-pilot','tree',job_type='course_knowledge_tree_generation')
    monkeypatch.setattr(svc.authoring,'load',lambda *_:pytest.fail('first live update copied the full history'))
    if stream:
        result=svc.authoring.update_job_stream('c-pilot',job['id'],phase='model_streaming',progress=1,
            message='received',batch_id='B',event='delta',delta='text')
    else:result=svc.authoring.update_job_live('c-pilot',job['id'],progress=1)
    assert result['id']==job['id']


def test_committed_job_snapshot_is_cached_without_exposing_mutable_aliases(svc,monkeypatch):
    from pathlib import Path
    job=svc.authoring.create_job('c-pilot','tree',job_type='course_knowledge_tree_generation')
    path=svc.authoring._path('c-pilot');read=Path.read_text
    def checked(target,*args,**kwargs):
        if target==path:pytest.fail('a just-committed course snapshot was decoded from disk again')
        return read(target,*args,**kwargs)
    monkeypatch.setattr(Path,'read_text',checked)
    assert svc.authoring.get_job('c-pilot',job['id'])['id']==job['id']
    returned=svc.authoring.update_job('c-pilot',job['id'],message='saved',request_snapshot={'nested':['original']})
    returned['request_snapshot']['nested'].append('mutated')
    assert svc.authoring.get_job('c-pilot',job['id'])['request_snapshot']=={'nested':['original']}


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
        if p['stage']=='candidate_core_identity':
            return json.dumps({'pairs':{pair['key']:'different'for pair in p['pairs']}})
        return json.dumps(transport_review(p['points'],p.get('coverage_materials',p['materials'])))
    svc.provider_factory=lambda:SimpleNamespace(_call_llm=model,model_smart='test',client=None)
    view=svc.view('c-pilot',source_mode='handouts')
    job=svc.start('c-pilot','tree','bounded-writes',view['knowledge_revision'],view['document_revision'],
        source_mode='handouts',lesson_id='cpu',pipeline='inventory_atomic_v1',generation_mode='core_v1')[0]
    await svc.run('c-pilot',job['id'])
    assert svc.authoring.get_job('c-pilot',job['id'])['status']=='completed'
    assert len(writes)<=4, 'completed batches should persist small attachments before the phase commit'


@pytest.mark.asyncio
async def test_explicit_resume_after_lost_live_state_reuses_durable_model_results(svc,monkeypatch):
    from knowledge_first import KnowledgeFirstService
    setup_course(svc,monkeypatch);view=svc.view('c-pilot',source_mode='handouts')
    async def first(prompt,**kwargs):
        if json.loads(prompt.split('\nINPUT_JSON:\n')[1])['stage']=='candidate_core_review':raise asyncio.CancelledError
        return json.dumps({'points':[row()],'context_note':''})
    svc.provider_factory=lambda:SimpleNamespace(_call_llm=first,model_smart='test',client=None)
    job=svc.start('c-pilot','tree','crash-before-phase-commit',view['knowledge_revision'],view['document_revision'],
        source_mode='handouts',lesson_id='cpu',pipeline='inventory_atomic_v1',generation_mode='core_v1')[0]
    with pytest.raises(asyncio.CancelledError):await svc.run('c-pilot',job['id'])
    fresh=type(svc.authoring)(svc.authoring.root,canonical_storage=svc.storage)
    fresh.update_job('c-pilot',job['id'],status='failed',error={'code':'process_interrupted','retryable':True})
    resumed=KnowledgeFirstService(svc.repository,fresh);calls=[]
    async def second(prompt,**kwargs):
        p=json.loads(prompt.split('\nINPUT_JSON:\n')[1]);calls.append(p['stage'])
        assert p['stage']=='candidate_core_review','a completed extraction was sent to the model again'
        return json.dumps(transport_review(p['points'],p['coverage_materials']))
    resumed.provider_factory=lambda:SimpleNamespace(_call_llm=second,model_smart='test',client=None)
    continued=resumed.start('c-pilot','tree','resume-cache',view['knowledge_revision'],view['document_revision'],
        source_mode='handouts',lesson_id='cpu',pipeline='inventory_atomic_v1',resume_job_id=job['id'])[0]
    await resumed.run('c-pilot',continued['id'])
    result=fresh.get_job('c-pilot',continued['id'])
    assert result['status']=='completed',result.get('error')
    assert calls==['candidate_core_review']
    assert fresh.get_job('c-pilot',job['id'])['status']=='failed'


def test_attachment_scope_and_initial_job_fields_cannot_override_ownership(svc):
    job=svc.authoring.create_job('c-pilot','tree',job_type='course_knowledge_tree_generation',initial_fields={'actor':'owner','source_context_revision':'A'})
    other=svc.authoring.create_job('c-pilot','tree',job_type='course_knowledge_tree_generation',initial_fields={'actor':'foreign','source_context_revision':'A'})
    before=svc.authoring._path('c-pilot').read_bytes()
    with pytest.raises(ValueError):svc.authoring.read_knowledge_response('c-pilot',other['id'],job['id'],'known')
    with pytest.raises(ValueError):svc.authoring.create_job('c-pilot','tree',initial_fields={'status':'completed'})
    assert svc.authoring._path('c-pilot').read_bytes()==before


@pytest.mark.asyncio
async def test_core_source_change_and_cancel_never_publish_late_candidates(svc,monkeypatch):
    setup_course(svc,monkeypatch);view=svc.view('c-pilot',source_mode='handouts')
    async def model(prompt,**kwargs):
        p=json.loads(prompt.split('\nINPUT_JSON:\n')[1])
        if p['stage']=='candidate_core_extract':return json.dumps({'points':[row()],'context_note':''})
        await asyncio.to_thread(svc.authoring.cancel_job,'c-pilot',job['id'])
        return json.dumps(transport_review(p['points'],p['coverage_materials']))
    svc.provider_factory=lambda:SimpleNamespace(_call_llm=model,model_smart='test',client=None)
    before=deepcopy(svc.repository.load_raw('c-pilot'))
    job=svc.start('c-pilot','tree','late-after-cancel',view['knowledge_revision'],view['document_revision'],
        source_mode='handouts',lesson_id='cpu',pipeline='inventory_atomic_v1',generation_mode='core_v1')[0]
    await svc.run('c-pilot',job['id'])
    saved=svc.authoring.get_job('c-pilot',job['id'])
    assert saved['status']=='cancelled' and 'candidate' not in saved.get('checkpoint',{})
    assert svc.repository.load_raw('c-pilot')==before


@pytest.mark.asyncio
async def test_core_adoption_uses_original_course_command_and_keeps_other_lessons(svc,monkeypatch):
    setup_course(svc,monkeypatch);before=deepcopy(svc.authoring.view('c-pilot')['lessons'])
    async def model(prompt,**kwargs):
        p=json.loads(prompt.split('\nINPUT_JSON:\n')[1])
        if p['stage']=='candidate_core_extract':return json.dumps({'points':[row()],'context_note':''})
        return json.dumps(transport_review(p['points'],p['coverage_materials']))
    svc.provider_factory=lambda:SimpleNamespace(_call_llm=model,model_smart='test',client=None)
    view=svc.view('c-pilot',source_mode='handouts')
    job=svc.start('c-pilot','tree','adopt-core',view['knowledge_revision'],view['document_revision'],
        source_mode='handouts',lesson_id='cpu',pipeline='inventory_atomic_v1',generation_mode='core_v1')[0]
    await svc.run('c-pilot',job['id'])
    svc.adopt('c-pilot',job['id'],view['knowledge_revision'],view['document_revision'])
    tree=svc.repository.load_raw('c-pilot')['course_knowledge_base']
    assert tree['status']=='accepted' and tree['generation_contract']=='knowledge_core_v1'
    assert svc.authoring.view('c-pilot')['lessons']==before


def test_semantic_reuse_does_not_rename_or_rewrite_the_registered_knowledge():
    from knowledge_core_contract import parse_extraction, compile_review
    points=parse_extraction({'points':[row()],'context_note':''},'B1',['S1'])
    old={k:deepcopy(points[0][k]) for k in ['statement','knowledge_type','conditions','symbol_definitions','teaching_context','examples']}
    old.update(key='E1',knowledge_id='existing',revision_id='unchanged',name='原有知识名称')
    old['_registered_point']=deepcopy({k:v for k,v in old.items()})
    before=deepcopy(old);value=review(points,[{'key':'S1'}]);value['keep']=[]
    value['match']={points[0]['key']:{'target':'E1','same_claim':True,'same_scope':True,'same_symbols':True,'reason':'完整知识相同'}}
    result=compile_review(value,points,[old],[{'key':'S1'}])
    assert old==before
    assert result['registry']['points'][0]['knowledge_id']=='existing'
    assert result['registry']['points'][0]['_registered_point']['name']=='原有知识名称'


def test_final_identity_screen_never_merges_from_names_without_full_semantic_proof():
    from knowledge_core_contract import parse_extraction,compile_review
    from knowledge_core_identity import candidate_pairs,apply_pairs
    points=parse_extraction({'points':[row('操作规则','操作将元素放到指定位置。'),row('操作的规则','该操作把元素加入指定位置。')],'context_note':''},'B1',['S1'])
    result=compile_review(review(points,[{'key':'S1'}]),points,[],[{'key':'S1'}])
    pairs=candidate_pairs(result);assert len(pairs)==1
    before=deepcopy(result)
    distinct=apply_pairs(result,pairs,{'pairs':{pairs[0]['key']:'different'}},[])
    assert len(distinct['registry']['points'])==2 and result==before
    merged=apply_pairs(result,pairs,{'pairs':{pairs[0]['key']:'same_claim_scope_symbols'}},[])
    assert len(merged['registry']['points'])==1
    assert merged['registry']['points'][0]['coverage_unit_ids']==['B1P1','B1P2']


def test_global_identity_keeps_all_members_when_equivalences_form_a_chain():
    from knowledge_core_contract import parse_extraction,compile_review
    from knowledge_core_identity import apply_pairs
    points=parse_extraction({'points':[row(),row(),row()],'context_note':''},'B1',['S1'])
    result=compile_review(review(points,[{'key':'S1'}]),points,[],[{'key':'S1'}])
    pairs=[{'key':'EQ1','left':'B1P1','right':'B1P2'},{'key':'EQ2','left':'B1P1','right':'B1P3'}]
    merged=apply_pairs(result,pairs,{'pairs':{p['key']:'same_claim_scope_symbols'for p in pairs}},[])
    assert len(merged['registry']['points'])==1
    assert set(merged['registry']['points'][0]['coverage_unit_ids'])=={'B1P1','B1P2','B1P3'}


@pytest.mark.asyncio
async def test_source_revision_change_stops_core_before_audit_and_keeps_checkpoint(svc,monkeypatch):
    setup_course(svc,monkeypatch);view=svc.view('c-pilot',source_mode='handouts');calls=[]
    async def model(prompt,**kwargs):
        p=json.loads(prompt.split('\nINPUT_JSON:\n')[1]);calls.append(p['stage'])
        svc.storage.update_course_data('c-pilot',lambda raw:{**raw,'course_document_revision':'new-source'})
        return json.dumps({'points':[row()],'context_note':''})
    svc.provider_factory=lambda:SimpleNamespace(_call_llm=model,model_smart='test',client=None)
    job=svc.start('c-pilot','tree','changed-source-core',view['knowledge_revision'],view['document_revision'],
        source_mode='handouts',lesson_id='cpu',pipeline='inventory_atomic_v1',generation_mode='core_v1')[0]
    await svc.run('c-pilot',job['id']);saved=svc.authoring.get_job('c-pilot',job['id'])
    assert saved['status']=='failed' and 'candidate' not in saved['checkpoint']
    assert calls==['candidate_core_extract']
    assert saved['checkpoint']['atomic_pipeline']['inventory_batches'][0]['points']
