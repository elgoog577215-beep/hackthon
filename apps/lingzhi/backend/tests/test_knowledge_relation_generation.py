import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from backend.tests.test_knowledge_first import svc
from backend.tests.test_handout_knowledge import handouts
from backend.tests.test_lesson_knowledge import one_lesson_response
from course_repository import CourseDocumentConflict

PIPELINE = 'knowledge_relations_v1'


def seed(svc, monkeypatch):
    from generic_knowledge import compile_tree
    from handout_knowledge import merge_lesson_tree
    monkeypatch.setenv('COURSE_KNOWLEDGE_RELATION_BATCH_SIZE', '1')
    handouts(svc); raw = svc.repository.load_raw('c-pilot'); tree = {}
    for lid in ['cpu','memory']:
        part = compile_tree(raw, svc._context(raw,'handouts',lid), one_lesson_response(lid))
        tree = merge_lesson_tree(tree,part,lid)
    cpu = tree['knowledge_points'][0]
    extra = {**deepcopy(cpu),'id':'cpu-extra','knowledge_id':'cpu-extra','revision_id':'extra-version',
             'name':'控制步骤','statement':'控制器按步骤处理指令。'}
    tree['knowledge_points'].append(extra); tree['lessons'][0]['knowledge_ids'].append('cpu-extra')
    tree.update(revision_id='baseline',status='accepted')
    svc.storage.update_course_data('c-pilot',lambda r:{**r,'course_knowledge_base':tree,'knowledge_first_history':{'baseline':deepcopy(tree)},
        'frozen_question_ref':{'knowledge_id':cpu['knowledge_id'],'revision_id':cpu['revision_id'],'baseline_revision':'baseline'}})
    return tree


def model_response(data):
    points = {p['key']:p for p in data['catalog']}
    decisions = []
    for key in data['focus_keys']:
        target = points[key]; links = []
        if target['name'] != '控制步骤':
            source = next(p for p in points.values() if 'memory' in p['lesson_ids'])
            for kind in ['prerequisite','derives','applies_to']:
                links.append({'source_key':source['key'],'target_key':key,'type':kind,'context':'理解指令处理',
                    'reason':'根据两端冻结命题说明知识在指令处理中的具体教学作用。','conditions':[],
                    'necessity':'recommended' if kind == 'prerequisite' else None,'strength':'medium',
                    'derivation_steps':['明确源知识适用的条件。','结合条件解释目标知识的结论。'] if kind == 'derives' else [],
                    'evidence':[{'point_key':p['key'],'quote':p['statement']} for p in [source,target]]})
        decisions.append({'focus_key':key,'considered_lessons':data['lesson_ids'],'reason':'已按具体命题检查全部讲次，不因同学科或名称相近强行连线。','links':links})
    return {'decisions':decisions,'gaps':[]}


def provider(svc, *, fail_at=None, mutate=None):
    calls = []
    async def call(prompt, **kwargs):
        data = json.loads(prompt.split('\nINPUT_JSON:\n')[1]); calls.append(data)
        assert kwargs['max_attempts'] == 1
        if len(calls) == fail_at: raise TimeoutError('isolated')
        result = model_response(data)
        if mutate: mutate(data,result)
        output = json.dumps(result,ensure_ascii=False); kwargs['on_content_delta'](output)
        return output
    svc.provider_factory = lambda:SimpleNamespace(_call_llm=call,model_smart='test-qwen',client=None)
    return calls


def start(svc, request='relations', **kwargs):
    view = svc.view('c-pilot',source_mode='handouts')
    return svc.start('c-pilot','tree',request,view['knowledge_revision'],view['document_revision'],
        source_mode='handouts',lesson_id='cpu',pipeline=PIPELINE,**kwargs)[0]


@pytest.mark.asyncio
async def test_relation_only_candidate_preserves_every_point_and_has_three_directed_types(svc,monkeypatch):
    tree = seed(svc,monkeypatch); before = deepcopy(svc.repository.load_raw('c-pilot')); calls = provider(svc)
    job = start(svc); await svc.run('c-pilot',job['id'])
    saved = svc.authoring.get_job('c-pilot',job['id']); assert saved['status'] == 'completed'
    candidate = saved['checkpoint']['candidate']
    assert candidate['knowledge_points'] == tree['knowledge_points']
    assert candidate['categories'] == tree['categories']
    assert {r['type'] for r in candidate['relations']} == {'prerequisite','derives','applies_to'}
    assert all(r['confidence'] is None and r['strength'] == 0.6 and r['cross_lesson'] for r in candidate['relations'])
    assert all(r['source_revision_id'] and r['target_revision_id'] and len(r['evidence_refs']) == 2 for r in candidate['relations'])
    assert candidate['relation_assessment']['semantics_verified'] is False
    assert all(set(c['lesson_ids']) == {'cpu','memory'} for c in calls)
    assert len(calls) == 2 and svc.repository.load_raw('c-pilot') == before


@pytest.mark.asyncio
@pytest.mark.parametrize('bad',['endpoint','self','evidence','steps','point_edit','missing_decision','scope'])
async def test_invalid_relationship_output_is_not_adoptable(svc,monkeypatch,bad):
    seed(svc,monkeypatch); before = deepcopy(svc.repository.load_raw('c-pilot'))
    def corrupt(data,result):
        if not result['decisions'][0]['links']: return
        edge = result['decisions'][0]['links'][0]
        if bad == 'endpoint': edge['source_key'] = 'foreign-id'
        if bad == 'self': edge['source_key'] = edge['target_key']
        if bad == 'evidence': edge['evidence'][0]['quote'] = '原文没有这个片段'
        if bad == 'steps': result['decisions'][0]['links'][1]['derivation_steps'] = []
        if bad == 'point_edit': result['points'] = [{'knowledge_id':'overwrite'}]
        if bad == 'missing_decision': result['decisions'] = []
        if bad == 'scope': edge['target_key'] = next(p['key'] for p in data['catalog'] if p['name']=='控制步骤')
    provider(svc,mutate=corrupt); job = start(svc); await svc.run('c-pilot',job['id'])
    saved = svc.authoring.get_job('c-pilot',job['id'])
    assert saved['status'] == 'failed' and not saved['checkpoint'].get('candidate')
    if bad == 'scope': assert 'P2→P3' in saved['error']['message']
    assert svc.repository.load_raw('c-pilot') == before


@pytest.mark.asyncio
async def test_existing_reverse_prerequisite_cannot_form_a_cycle(svc,monkeypatch):
    tree = seed(svc,monkeypatch); a,b = tree['knowledge_points'][:2]
    edge = {'id':'keep-edge','type':'prerequisite','source_id':a['knowledge_id'],'target_id':b['knowledge_id'],'reason':'既有方向','conditions':[]}
    svc.storage.update_course_data('c-pilot',lambda r:{**r,'course_knowledge_base':{**tree,'relations':[edge]}})
    provider(svc); job = start(svc); await svc.run('c-pilot',job['id'])
    saved = svc.authoring.get_job('c-pilot',job['id'])
    assert saved['status'] == 'failed' and '环' in saved['error']['message']
    assert svc.repository.load_raw('c-pilot')['course_knowledge_base']['relations'] == [edge]


@pytest.mark.asyncio
async def test_continue_only_missing_relation_batches_keeps_original_attempt(svc,monkeypatch):
    seed(svc,monkeypatch); provider(svc,fail_at=2); job = start(svc); await svc.run('c-pilot',job['id'])
    original = deepcopy(svc.authoring.get_job('c-pilot',job['id'])); assert original['status'] == 'failed'
    calls = provider(svc); continued = start(svc,'continue-relations',resume_job_id=job['id']); await svc.run('c-pilot',continued['id'])
    assert len(calls) == 1 and svc.authoring.get_job('c-pilot',continued['id'])['status'] == 'completed'
    assert svc.authoring.get_job('c-pilot',job['id']) == original


@pytest.mark.asyncio
async def test_adoption_is_explicit_and_preserves_point_objects_and_history_refs(svc,monkeypatch):
    tree = seed(svc,monkeypatch); provider(svc); job = start(svc); await svc.run('c-pilot',job['id'])
    view = svc.view('c-pilot',source_mode='handouts')
    with pytest.raises(CourseDocumentConflict,match='关系'):
        svc.adopt('c-pilot',job['id'],'baseline',view['document_revision'])
    svc.adopt('c-pilot',job['id'],'baseline',view['document_revision'],confirm_relations=True)
    raw = svc.repository.load_raw('c-pilot')
    assert raw['course_knowledge_base']['knowledge_points'] == tree['knowledge_points']
    assert raw['knowledge_first_history']['baseline'] == tree
    assert raw['frozen_question_ref']['baseline_revision'] == 'baseline'
    assert all(r.get('review_status') == 'accepted' for r in raw['course_knowledge_base']['relations'])


@pytest.mark.asyncio
async def test_cross_lecture_definition_change_rejects_old_candidate(svc,monkeypatch):
    seed(svc,monkeypatch); provider(svc); job = start(svc); await svc.run('c-pilot',job['id'])
    def change(raw):
        raw['course_knowledge_base']['knowledge_points'][1]['statement'] += '修改'
        return raw
    svc.storage.update_course_data('c-pilot',change)
    view = svc.view('c-pilot',source_mode='handouts')
    with pytest.raises(CourseDocumentConflict):
        svc.adopt('c-pilot',job['id'],view['knowledge_revision'],view['document_revision'],confirm_relations=True)


@pytest.mark.asyncio
async def test_retry_only_one_relation_batch_keeps_existing_edges_and_saved_batches(svc,monkeypatch):
    tree = seed(svc,monkeypatch)
    a,b = tree['knowledge_points'][:2]
    old = {'id':'keep-legacy','source_id':b['knowledge_id'],'target_id':a['knowledge_id'],'type':'applies_to','reason':'旧理由','conditions':[]}
    svc.storage.update_course_data('c-pilot',lambda r:{**r,'course_knowledge_base':{**tree,'relations':[old]}})
    provider(svc);job=start(svc);await svc.run('c-pilot',job['id'])
    prior=deepcopy(svc.authoring.get_job('c-pilot',job['id']))
    calls=provider(svc);retry=start(svc,'retry-selected',resume_job_id=job['id'],retry_batch_id='relations-2');await svc.run('c-pilot',retry['id'])
    saved=svc.authoring.get_job('c-pilot',retry['id'])
    assert len(calls)==1 and saved['status']=='completed'
    assert saved['checkpoint']['relation_pipeline']['batches'][0]==prior['checkpoint']['relation_pipeline']['batches'][0]
    assert next(e for e in saved['checkpoint']['candidate']['relations'] if e['id']=='keep-legacy')==old
    assert saved['checkpoint']['candidate']['base_knowledge_revision']=='baseline'


@pytest.mark.asyncio
async def test_reader_cannot_access_relation_comparison_or_private_candidate(svc,monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from dependencies import get_course_document_repository,get_teacher_lesson_authoring_repository
    from routers.knowledge_first import router
    seed(svc,monkeypatch);provider(svc);job=start(svc);await svc.run('c-pilot',job['id'])
    view=svc.view('c-pilot',source_mode='handouts')
    svc.adopt('c-pilot',job['id'],'baseline',view['document_revision'],confirm_relations=True)
    svc.storage.update_course_data('c-pilot',lambda r:{**r,'is_published':True})
    app=FastAPI();app.include_router(router,prefix='/api')
    app.dependency_overrides[get_course_document_repository]=lambda:svc.repository
    app.dependency_overrides[get_teacher_lesson_authoring_repository]=lambda:svc.authoring
    result=TestClient(app).get('/api/courses/c-pilot/knowledge-first?source_mode=handouts',headers={'X-User-Id':'reader'}).json()
    assert result['relation_runs']==[] and result['candidates']==[] and result['history']==[]
    assert 'relation_assessment' not in result['tree']


@pytest.mark.asyncio
async def test_relation_status_is_light_and_changes_when_a_batch_finishes(svc,monkeypatch):
    seed(svc,monkeypatch);versions=[]
    def observe(data,result):versions.append(svc.status('c-pilot')['result_version'])
    provider(svc,mutate=observe);job=start(svc);await svc.run('c-pilot',job['id'])
    status=svc.status('c-pilot');body=json.dumps(status,ensure_ascii=False)
    assert len(versions)==2 and versions[0]!=versions[1]
    assert len(body)<20000 and '控制器按步骤' not in body and 'catalog' not in body


@pytest.mark.asyncio
async def test_owner_can_adopt_selected_relations_without_accepting_all_model_suggestions(svc,monkeypatch):
    tree=seed(svc,monkeypatch);provider(svc);job=start(svc);await svc.run('c-pilot',job['id'])
    candidate=svc.authoring.get_job('c-pilot',job['id'])['checkpoint']['candidate']
    chosen=next(e['id'] for e in candidate['relations'] if e['type']=='applies_to')
    view=svc.view('c-pilot',source_mode='handouts')
    svc.adopt('c-pilot',job['id'],'baseline',view['document_revision'],confirm_relations=True,selected_relation_ids=[chosen])
    raw=svc.repository.load_raw('c-pilot');current=raw['course_knowledge_base']
    assert [e['id'] for e in current['relations']]==[chosen]
    assert len(current['relation_assessment']['rejected_ids'])==2
    assert current['knowledge_points']==tree['knowledge_points']
    assert raw['knowledge_first_history']['baseline']==tree
    assert svc.view('c-pilot',source_mode='handouts')['relation_runs'][0]['accepted_ids']==[chosen]


@pytest.mark.asyncio
async def test_relation_selection_may_not_inject_an_unknown_edge(svc,monkeypatch):
    seed(svc,monkeypatch);provider(svc);job=start(svc);await svc.run('c-pilot',job['id'])
    view=svc.view('c-pilot',source_mode='handouts');before=deepcopy(svc.repository.load_raw('c-pilot'))
    with pytest.raises(CourseDocumentConflict):
        svc.adopt('c-pilot',job['id'],'baseline',view['document_revision'],confirm_relations=True,selected_relation_ids=['foreign'])
    assert svc.repository.load_raw('c-pilot')==before


def test_three_type_relation_prompt_does_not_prime_reemission_of_locked_other_types():
    from knowledge_relation_generation import prompt_for
    points=[{'key':'P1','knowledge_id':'one','revision_id':'r1','name':'源','statement':'源命题','conditions':[],'lesson_ids':['cpu']}]
    pipeline={'catalog':points,'existing_relations':[{'source_key':'P1','target_key':'P2','type':'contrasts_with','reason':'旧的对比关系'}]}
    data=json.loads(prompt_for({'course_name':'课'},pipeline,{'focus_keys':['P1']},'cpu').split('\nINPUT_JSON:\n')[1])
    assert data['existing_relations']==[] and data['retained_other_relation_count']==1
