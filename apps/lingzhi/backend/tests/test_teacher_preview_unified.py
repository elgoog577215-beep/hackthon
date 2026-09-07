import asyncio
import hashlib
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from course_document import CourseDocument, CourseBlock, CourseSection, refresh_document_revision
from storage import Storage
from routers import teacher_preview as api
from teacher_lesson_authoring import TeacherLessonAuthoringRepository


@pytest.fixture
def client(tmp_path, monkeypatch):
    storage = Storage(str(tmp_path/'data'))
    doc = refresh_document_revision(CourseDocument(course_id='c',title='课程',sections=[CourseSection(section_id='s',title='定义',position=0)],blocks=[
        CourseBlock(block_id='public',section_id='s',position=0,payload={'markdown':'函数把输入映射到唯一输出。','private_note':'secret'},status='final'),
        CourseBlock(block_id='private',section_id='s',position=1,payload={'markdown':'private'},status='final',visibility_rule={'audience':'teacher'}),
        CourseBlock(block_id='retired',section_id='s',position=2,payload={'markdown':'retired'},status='retired')]))
    storage.save_course_sync('c',{'course_id':'c','authoring_surface':'teacher','owner_id':'t','course_document':doc.model_dump(mode='json'), 'course_document_revision':doc.document_revision})
    repository = TeacherLessonAuthoringRepository(tmp_path/'data'/'teacher_lesson_authoring')
    repository._save({'course_id':'c', 'lessons':{'s':{'working_revision_id':'p1', 'working_script_revision_id':'r1',
        'script_revisions':[{'revision_id':'r1','source_lesson_plan_revision_id':'p1','publication_eligible':True,
            'sections':[{'section_node_id':'s','blocks':[{'block_id':b.block_id,'content':b.payload['markdown'],
                'visibility_rule':b.visibility_rule,'status':b.status} for b in doc.blocks]}]}]}}})
    repository.load('c')
    question={'revision_id':'q1','question_id':'q','node_id':'s','prompt':'唯一输出？','options':[{'id':'A','text':'是'},{'id':'B','text':'否'}], 'question_type':'single_choice', 'answer_spec':{'type':'choice','correct_option_ids':['A']}, 'grading_policy':{'method':'choice'}}
    monkeypatch.setattr(api,'storage',storage)
    monkeypatch.setattr(api,'formal_questions',lambda raw:[question])
    async def answer(question,**kwargs):
        assert not kwargs['context_package'].get('learner_evidence')
        assert 'private' not in json.dumps(kwargs['context_package'])
        yield '根据讲义，函数的输出唯一。'
    monkeypatch.setattr(api.qa_service,'answer_question_stream',answer)
    app=FastAPI();app.include_router(api.router,prefix='/api')
    return TestClient(app),storage,tmp_path


def digest(root):
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}


def test_teacher_trial_is_public_projection_and_has_no_persistence(client):
    c,storage,root=client;headers={'X-User-Id':'t'};url='/api/teacher/courses/c/preview'
    before=digest(root)
    view=c.get(url,headers=headers).json()
    assert [b['block_id'] for b in view['document']['blocks']]==['public']
    assert 'private_note' not in json.dumps(view)
    assert 'answer_spec' not in view['questions'][0]
    result=c.post(url+'/grade',headers=headers,json={'preview_revision':view['preview_revision'],'question_revision_id':'q1','answer_payload':{'selected_option_ids':['A']}})
    assert result.status_code==200,result.text
    result=c.post(url+'/ask',headers=headers,json={'preview_revision':view['preview_revision'],'question':'什么是函数','section_id':'s'})
    assert result.status_code==200,result.text
    assert result.json()['sources'][0]['block_id']=='public'
    assert digest(root)==before


def test_preview_knowledge_is_lazy_and_read_only(client):
    c, _, root = client
    before = digest(root)
    url = '/api/teacher/courses/c/preview'
    basic = c.get(url, headers={'X-User-Id':'t'}).json()
    assert 'assets' not in basic
    response = c.get(url, params={'include_assets':True}, headers={'X-User-Id':'t'})
    assert response.status_code == 200, response.text
    assert response.json()['preview_revision'] == basic['preview_revision']
    assert 'knowledge_library' in response.json()['assets']
    assert 'private' not in json.dumps(response.json()['assets'])
    assert 'retired' not in json.dumps(response.json()['assets'])
    assert digest(root) == before


def test_preview_stream_delivers_real_chunks_without_learning_writes(client):
    c, _, root = client
    before = digest(root)
    url = '/api/teacher/courses/c/preview'
    headers = {'X-User-Id':'t'}
    revision = c.get(url, headers=headers).json()['preview_revision']
    response = c.post(url+'/ask', headers={**headers,'Accept':'text/event-stream'}, json={
        'preview_revision':revision,'question':'什么是函数','section_id':'s'})
    assert response.status_code == 200
    assert 'event: answer' in response.text
    assert '根据讲义，函数的输出唯一。' in response.text
    assert 'event: complete' in response.text
    assert digest(root) == before


def test_preview_knowledge_keeps_formal_structure_but_excludes_private_body(client, monkeypatch):
    from course_knowledge_map import project_learning_assets_to_knowledge
    import course_knowledge_map
    c, storage, _ = client
    raw = storage.load_course('c')
    raw['course_document']['sections'][0]['attributes'] = {'knowledge_structure': [{
        'concept_group': '函数', 'knowledge_points': [{'name': '单值性', 'statement': '每个输入只有一个输出。'}]}]}
    storage.save_course_sync('c', raw)
    def inspect_source(course, assets):
        assert course['nodes'][0]['knowledge_structure'][0]['concept_group'] == '函数'
        assert 'private' not in json.dumps(course)
        assert assets == {}
        return project_learning_assets_to_knowledge(course, assets)
    monkeypatch.setattr(course_knowledge_map, 'project_learning_assets_to_knowledge', inspect_source)
    response = c.get('/api/teacher/courses/c/preview', params={'include_assets': True}, headers={'X-User-Id': 't'})
    assert response.status_code == 200, response.text


def test_owner_revision_and_reference_guards(client):
    c,storage,_=client;url='/api/teacher/courses/c/preview';h={'X-User-Id':'t'}
    assert c.get(url,headers={'X-User-Id':'other'}).status_code==404
    rev=c.get(url,headers=h).json()['preview_revision']
    assert c.post(url+'/ask',headers=h,json={'preview_revision':rev,'question':'x','block_ids':['private']}).status_code==422
    assert c.post(url+'/grade',headers=h,json={'preview_revision':'old','question_revision_id':'q1','answer_payload':{}}).status_code==409
    assert c.post(url+'/grade',headers=h,json={'preview_revision':rev,'question_revision_id':'q-old','answer_payload':{}}).status_code==409
