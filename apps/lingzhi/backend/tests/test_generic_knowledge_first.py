from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from backend.tests.test_knowledge_first import svc
from course_knowledge_context import documents_from_text_sources
from course_repository import CourseDocumentConflict


def source(svc):
    docs, bindings = documents_from_text_sources('c-pilot', [{'id': 'uploaded', 'text':
        'CPU执行指令。主存保存正在使用的数据。缓存利用时间局部性和空间局部性降低平均访存开销。'}])
    svc.storage.update_course_data('c-pilot', lambda raw: {**raw, 'course_name': '计算机系统',
        'parsed_documents': docs, 'material_bindings': bindings,
        'generation_request': {'requirements': '理解处理器与存储层次'}, 'knowledge_lesson_count': 2})


def response():
    return {'categories': [{'key': 'C1', 'name': '硬件基础', 'parent_key': None},
        {'key': 'C2', 'name': '组成与存储', 'parent_key': 'C1'}], 'points': [
        {'key': 'K1', 'category_key': 'C2', 'name': 'CPU作用', 'statement': 'CPU执行指令。',
         'knowledge_type': 'definition', 'conditions': [], 'meta_question': '谁执行指令？', 'meta_answer': 'CPU。',
         'sources': [{'key': 'S1', 'quote': 'CPU执行指令。'}]},
        {'key': 'K2', 'category_key': 'C2', 'name': '主存作用', 'statement': '主存保存正在使用的数据。',
         'knowledge_type': 'definition', 'conditions': [], 'meta_question': '主存保存什么？', 'meta_answer': '正在使用的数据。',
         'sources': [{'key': 'S1', 'quote': '主存保存正在使用的数据。'}]}],
        'relations': [], 'lessons': [{'key': 'L1', 'title': '处理器', 'knowledge_keys': ['K1']},
                                     {'key': 'L2', 'title': '存储器', 'knowledge_keys': ['K2']}],
        'gaps': ['缓存局部性需要进一步细化。']}


@pytest.mark.asyncio
async def test_new_course_uses_only_uploaded_material_and_requires_adoption(svc, monkeypatch):
    source(svc)
    monkeypatch.setattr('knowledge_first.material', lambda: pytest.fail('generic course read C17 seed'))
    raw = svc.repository.load_raw('c-pilot')
    svc.initialize('c-pilot', raw['course_document_revision'])
    view = svc.view('c-pilot')
    assert view['workflow'] == 'knowledge_first_generic_v1'
    assert not svc.repository.load_raw('c-pilot')['course_document']['sections']
    calls = []
    async def call(prompt, **kwargs):
        calls.append(prompt)
        assert 'CPU执行指令' in prompt and 'C17' not in kwargs['system_prompt']
        assert kwargs['max_attempts'] == 1
        return json.dumps(response(), ensure_ascii=False)
    svc.provider_factory = lambda: SimpleNamespace(_call_llm=call, model_smart='test', client=None)
    job, _ = svc.start('c-pilot', 'tree', 'tree1', '', view['document_revision'])
    await svc.run('c-pilot', job['id'])
    view = svc.view('c-pilot')
    assert view['candidate'] and view['tree'] is None
    with pytest.raises(CourseDocumentConflict):
        svc.start('c-pilot', 'L1', 'early', '', view['document_revision'])
    svc.adopt('c-pilot', job['id'], '', view['document_revision'])
    view = svc.view('c-pilot')
    assert len(view['handouts']) == 2
    assert len(view['tree']['knowledge_points']) == 2
    assert len(svc.repository.load_raw('c-pilot')['course_document']['sections']) == 2
    assert len(calls) == 1


def test_empty_course_never_substitutes_a_seed(svc, monkeypatch):
    monkeypatch.setattr('knowledge_first.material', lambda: pytest.fail('unexpected sample'))
    raw = svc.repository.load_raw('c-pilot')
    svc.initialize('c-pilot', raw['course_document_revision'])
    view = svc.view('c-pilot')
    with pytest.raises(CourseDocumentConflict, match='资料'):
        svc.start('c-pilot', 'tree', 'missing', '', view['document_revision'])


@pytest.mark.asyncio
async def test_generic_handout_keeps_ids_versions_and_old_body_after_new_baseline(svc):
    source(svc)
    svc.initialize('c-pilot', svc.view('c-pilot')['document_revision'])
    async def call(prompt, **kwargs):
        if '知识树候选' in kwargs['system_prompt']: return json.dumps(response(), ensure_ascii=False)
        return '<!-- block:{"type":"explanation","title":"处理器作用","key":"explain","knowledge":["K1"]} -->\nCPU执行程序中的指令，取指和执行属于处理器的基本工作。\n'
    svc.provider_factory = lambda: SimpleNamespace(_call_llm=call, model_smart='test', client=None)
    v = svc.view('c-pilot');job,_ = svc.start('c-pilot','tree','tree','',v['document_revision']);await svc.run('c-pilot',job['id'])
    svc.adopt('c-pilot',job['id'],'',v['document_revision'])
    v = svc.view('c-pilot');lesson = v['handouts'][0]['topic']
    job,_ = svc.start('c-pilot',lesson,'handout',v['knowledge_revision'],v['document_revision']);await svc.run('c-pilot',job['id'])
    assert svc.authoring.load('c-pilot')['jobs'][job['id']]['status']=='completed'
    output=svc.view('c-pilot')['handouts'][0]['revisions'][0]
    assert output['source_knowledge_revision']==v['knowledge_revision']
    assert output['sections'][0]['blocks'][0]['knowledge_refs'][0]['knowledge_id']==v['tree']['knowledge_points'][0]['knowledge_id']
    assert output['pipeline_version']=='knowledge_first_generic_v1'


@pytest.mark.asyncio
async def test_invented_quote_and_source_change_do_not_publish(svc):
    source(svc);svc.initialize('c-pilot',svc.view('c-pilot')['document_revision'])
    bad=response();bad['points'][0]['sources'][0]['quote']='根本不存在的材料引文'
    async def call(*args,**kwargs):return json.dumps(bad,ensure_ascii=False)
    svc.provider_factory=lambda:SimpleNamespace(_call_llm=call,model_smart='test',client=None)
    v=svc.view('c-pilot');job,_=svc.start('c-pilot','tree','bad','',v['document_revision']);await svc.run('c-pilot',job['id'])
    assert svc.view('c-pilot')['tree'] is None
    assert svc.authoring.load('c-pilot')['jobs'][job['id']]['status']=='failed'
