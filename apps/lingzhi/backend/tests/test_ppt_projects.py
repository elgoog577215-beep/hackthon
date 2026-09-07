import asyncio
from copy import deepcopy
from io import BytesIO

import pytest
from starlette.datastructures import UploadFile
from course_document import CourseDocument, CourseSection, CourseBlock, refresh_document_revision
from storage import Storage
from material_storage import MaterialRepository
from teacher_lesson_authoring import TeacherLessonAuthoringRepository, TeacherLessonAuthoringError
from ppt_projects import PptProjectService


@pytest.fixture
def fixture(tmp_path):
    storage=Storage(str(tmp_path/'data'))
    doc=refresh_document_revision(CourseDocument(course_id='c',title='课程',sections=[
        CourseSection(section_id='l1',title='第一讲',position=0),CourseSection(section_id='s1',parent_section_id='l1',title='主题一',level=2,position=1),
        CourseSection(section_id='l2',title='第二讲',position=2),CourseSection(section_id='s2',parent_section_id='l2',title='主题二',level=2,position=3)],blocks=[
        CourseBlock(block_id='b1',section_id='s1',position=0,status='final',payload={'markdown':'第一讲正文'}),
        CourseBlock(block_id='b2',section_id='s2',position=0,status='final',payload={'markdown':'第二讲正文'})]))
    storage.save_course_sync('c',{'course_id':'c','course_document':doc.model_dump(mode='json'),'course_document_revision':doc.document_revision})
    jobs=TeacherLessonAuthoringRepository(tmp_path/'teacher')
    materials=MaterialRepository(tmp_path/'materials')
    return PptProjectService(storage,jobs,materials=materials),storage,doc


def test_multi_lecture_selection_keeps_real_ids_and_never_generates_during_selection(fixture):
    svc,storage,doc=fixture
    raw=storage.load_course('c')
    project=svc.create('c',['l1','l2'],[],title='',expected_revision=doc.document_revision)
    assert project['manuscript'] is None
    assert svc.jobs.load('c')['jobs']=={}
    source=svc.document(project)
    assert source.course_id=='c'
    assert {b.block_id for b in source.blocks}=={'b1','b2'}
    assert storage.load_course('c')['course_document']==raw['course_document']
    single=svc.create('c',['l1'],[],title='',expected_revision=doc.document_revision)
    def change(raw):
        raw['course_document']['blocks'][1]['internal_revision']='changed'
        return raw
    storage.update_course_data('c',change)
    assert svc.source_current(single)
    assert not svc.source_current(project)


def test_missing_handout_is_not_reported_as_a_revision_conflict(fixture):
    svc, storage, doc = fixture
    storage.update_course_data('c', lambda raw: {**raw, 'course_document': {
        **raw['course_document'], 'blocks': []}})
    with pytest.raises(TeacherLessonAuthoringError) as error:
        svc.create('c', ['l1'], [], title='', expected_revision=doc.document_revision)
    assert error.value.code == 'ppt_project_handout_unavailable'
    assert not storage.load_course('c').get('teacher_ppt_projects')


def test_upload_only_source_is_parsed_on_prepare_and_has_stable_evidence(fixture):
    svc,storage,doc=fixture
    asset=asyncio.run(svc.materials.save_upload(UploadFile(BytesIO('上传资料正文。'.encode()),filename='notes.md')))
    def register(raw):
        raw['teacher_ppt_uploads']={asset.asset_id:{'sha256':asset.sha256}}
        return raw
    storage.update_course_data('c',register)
    project=svc.create('c',[],[asset.asset_id],title='',expected_revision=doc.document_revision)
    assert svc.materials.load_parsed_document(asset.asset_id) is None
    from material_parser import parse_material_asset
    asyncio.run(parse_material_asset(svc.materials,asset))
    source=svc.document(project)
    assert source.course_id=='c'
    assert source.blocks[0].asset_refs==[asset.asset_id]
    assert source.blocks[0].evidence_refs
    assert storage.load_course('c')['course_document']==doc.model_dump(mode='json')


def test_render_requires_confirmation_and_conflict_preserves_existing_result(fixture):
    svc,storage,doc=fixture
    project=svc.create('c',['l1'],[],title='',expected_revision=doc.document_revision)
    with pytest.raises(TeacherLessonAuthoringError):
        svc.start('c',project['project_id'],project['revision'],render=True)
    saved=svc.update('c',project['project_id'],{'last_good_render':{'task_id':'old','manuscript_revision':'old'}})
    with pytest.raises(TeacherLessonAuthoringError):
        svc.update('c',project['project_id'],{'last_good_render':None},expected=project['revision'])
    assert svc.load('c',project['project_id'])['last_good_render']['task_id']=='old'
    with pytest.raises(TeacherLessonAuthoringError):
        svc.create('c',[],['foreign'],title='',expected_revision=doc.document_revision)


def test_late_completion_cannot_replace_paused_or_changed_sources(fixture):
    svc, storage, doc = fixture
    project = svc.create('c', ['l1'], [], title='', expected_revision=doc.document_revision)
    project = svc.update('c', project['project_id'], {'status':'paused', 'job_id':'old'})
    with pytest.raises(TeacherLessonAuthoringError):
        svc.update('c', project['project_id'], {'status':'ready'}, job_id='old', require_running=True)
    svc.update('c', project['project_id'], {'status':'building', 'job_id':'new'})
    with pytest.raises(TeacherLessonAuthoringError):
        svc.update('c', project['project_id'], {'status':'ready'}, job_id='old')
    def edit(raw):
        raw['course_document']['blocks'][0]['internal_revision']='new'
        return raw
    storage.update_course_data('c', edit)
    with pytest.raises(TeacherLessonAuthoringError):
        svc.update('c', project['project_id'], {'status':'ready'}, job_id='new', source_snapshot=project['sources'])
    assert svc.load('c', project['project_id'])['status']=='building'


def test_failed_checkpoint_copy_does_not_leave_a_pending_job(fixture, monkeypatch):
    svc, storage, doc = fixture
    project = svc.create('c', ['l1'], [], title='', expected_revision=doc.document_revision)
    old = svc.jobs.create_job('c', project['project_id'], job_type='teacher_lesson_ppt_manuscript_generation', request_id='old')
    svc.jobs.update_job('c', old['id'], status='paused', request_snapshot={'render':False})
    project = svc.update('c', project['project_id'], {'status':'paused', 'job_id':old['id']})
    def fail(*args):
        raise OSError('checkpoint unavailable')
    monkeypatch.setattr(svc.candidates, 'clone_checkpoint', fail)
    with pytest.raises(OSError):
        svc.start('c', project['project_id'], project['revision'])
    assert svc.load('c', project['project_id'])['job_id'] == old['id']
    assert all(job['status'] in {'paused','cancelled'} for job in svc.jobs.load('c')['jobs'].values())
