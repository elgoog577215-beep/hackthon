import asyncio
from copy import deepcopy
from io import BytesIO
import multiprocessing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

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


def test_pause_before_worker_starts_does_not_restart_generation(fixture, monkeypatch):
    svc, _, doc = fixture
    calls = []
    async def build(**kwargs):
        calls.append(kwargs)
    monkeypatch.setattr(svc.orchestrator, 'build', build)
    async def scenario():
        project = svc.create('c', ['l1'], [], title='', expected_revision=doc.document_revision)
        project = svc.start('c', project['project_id'], project['revision'])
        svc.pause('c', project['project_id'], project['revision'])
        await asyncio.gather(*list(svc.jobs._runtime_jobs['c']))
        assert svc.jobs.get_job('c', project['job_id'])['status'] == 'paused'
        assert svc.load('c', project['project_id'])['status'] == 'paused'
        assert not calls
    asyncio.run(scenario())


def test_manuscript_stream_is_page_isolated_in_memory_and_retry_replaces_old_text(fixture, monkeypatch):
    import ppt_projects
    svc, _, doc = fixture
    monkeypatch.setattr(ppt_projects, 'build_ai_base_story_planner_v6', lambda **kwargs: kwargs['on_content_stream'])
    monkeypatch.setattr(ppt_projects, 'build_ai_base_visual_planner_v2', lambda: None)
    ticks = iter(i * 0.2 for i in range(100))
    monkeypatch.setattr(ppt_projects, 'time', SimpleNamespace(monotonic=lambda: next(ticks)))
    save = Mock(wraps=svc.jobs._save)
    monkeypatch.setattr(svc.jobs, '_save', save)
    async def build(**kwargs):
        stream, jid = kwargs['story_planner'], kwargs['task_id']
        count = save.call_count
        async def emit(bid, event, delta=''):
            await stream({'batch_id': bid, 'event': event, 'delta': delta})
        await emit('page-1', 'reset')
        await emit('page-1', 'delta', '{"title":"第一')
        assert svc.jobs.get_job('c', jid)['stream_batches'] == {'page-1': '第一'}
        await emit('page-2', 'delta', '{"title":"第二页"}')
        await emit('page-1', 'delta', '页"}')
        assert svc.jobs.get_job('c', jid)['stream_batches'] == {'page-1': '第一页', 'page-2': '第二页'}
        await emit('page-1', 'reset')
        assert svc.jobs.get_job('c', jid)['stream_batches'] == {'page-1': '', 'page-2': '第二页'}
        await emit('page-1', 'delta', '{"title":"第一讲修正版"}')
        await emit('page-1', 'complete')
        assert svc.jobs.get_job('c', jid)['stream_batches'] == {'page-1': '第一讲修正版', 'page-2': '第二页'}
        assert save.call_count == count
        return {'ppt_manuscript': {'revision': 'stream-tested', 'pages': []}}
    monkeypatch.setattr(svc.orchestrator, 'build', build)
    async def scenario():
        project = svc.create('c', ['l1'], [], title='', expected_revision=doc.document_revision)
        project = svc.start('c', project['project_id'], project['revision'])
        await asyncio.gather(*list(svc.jobs._runtime_jobs['c']))
        assert svc.load('c', project['project_id'])['status'] == 'draft'
        assert svc.jobs.get_job('c', project['job_id'])['status'] == 'completed'
    asyncio.run(scenario())


@pytest.mark.parametrize('boundary', ['pause', 'source'])
def test_stream_cannot_publish_after_pause_or_source_change(fixture, monkeypatch, boundary):
    import ppt_projects
    svc, storage, doc = fixture
    monkeypatch.setattr(ppt_projects, 'build_ai_base_story_planner_v6', lambda **kwargs: kwargs['on_content_stream'])
    monkeypatch.setattr(ppt_projects, 'build_ai_base_visual_planner_v2', lambda: None)
    async def build(**kwargs):
        stream, jid = kwargs['story_planner'], kwargs['task_id']
        await stream({'batch_id': 'page-1', 'event': 'delta', 'delta': '{"title":"已到内容"}'})
        if boundary == 'pause':
            project = svc.load('c', kwargs['course_data']['teacher_lesson_source']['project_id'])
            svc.pause('c', project['project_id'], project['revision'])
        else:
            def change(raw):
                raw['course_document']['blocks'][0]['internal_revision'] = 'changed'
                return raw
            storage.update_course_data('c', change)
        with pytest.raises(TeacherLessonAuthoringError):
            await stream({'batch_id': 'page-1', 'event': 'complete', 'delta': '\nlate invalid data'})
        assert svc.jobs.get_job('c', jid)['stream_batches'] == {'page-1': '已到内容'}
        return {'ppt_manuscript': {'revision': 'late-must-not-publish', 'pages': []}}
    monkeypatch.setattr(svc.orchestrator, 'build', build)
    async def scenario():
        project = svc.create('c', ['l1'], [], title='', expected_revision=doc.document_revision)
        project = svc.start('c', project['project_id'], project['revision'])
        await asyncio.gather(*list(svc.jobs._runtime_jobs['c']))
        current = svc.load('c', project['project_id'])
        assert current['status'] == 'paused'
        assert current['manuscript'] is None
    asyncio.run(scenario())


def test_stale_pause_cannot_stop_replacement_job(fixture):
    svc, _, doc = fixture
    project = svc.create('c', ['l1'], [], title='', expected_revision=doc.document_revision)
    job = svc.jobs.create_job('c', project['project_id'], job_type='teacher_lesson_ppt_manuscript_generation', request_id='new')
    current = svc.update('c', project['project_id'], {'status':'building', 'job_id':job['id']})
    with pytest.raises(TeacherLessonAuthoringError):
        svc.pause('c', project['project_id'], project['revision'])
    assert svc.jobs.get_job('c', job['id'])['status'] == 'pending'
    assert svc.load('c', project['project_id']) == current


@pytest.mark.parametrize('code,retryable', [('teaching_provider_failed', True), ('v6_recovery_contract_mismatch', False)])
def test_engine_failure_keeps_public_code_and_recovery_contract(fixture, monkeypatch, code, retryable):
    from slide_deck_v6_models import V6BuildError
    svc, _, doc = fixture
    async def build(**kwargs):
        raise V6BuildError(stage='story', code=code, message='页面内容规划未完成', retryable=retryable, page_id='p1')
    monkeypatch.setattr(svc.orchestrator, 'build', build)
    async def scenario():
        project = svc.create('c', ['l1'], [], title='', expected_revision=doc.document_revision)
        project = svc.start('c', project['project_id'], project['revision'])
        await asyncio.gather(*list(svc.jobs._runtime_jobs['c']))
        error = svc.load('c', project['project_id'])['error']
        assert error['code'] == code
        assert error['retryable'] is retryable
        assert error['message'] == '页面内容规划未完成'
        assert svc.jobs.get_job('c', project['job_id'])['error'] == error
    asyncio.run(scenario())


def test_invalid_manuscript_returns_public_validation_error():
    from fastapi import HTTPException
    from routers.ppt_projects import call
    from slide_deck_v6_models import V6BuildError
    def invalid():
        raise V6BuildError(stage='manuscript', code='teaching_page_validation_failed', message='当前页面缺少必要正文')
    with pytest.raises(HTTPException) as failure:
        call(invalid)
    assert failure.value.status_code == 422
    assert failure.value.detail['code'] == 'teaching_page_validation_failed'


def test_restart_recovery_reuses_failed_job_checkpoint(fixture, monkeypatch):
    svc, _, doc = fixture
    project = svc.create('c', ['l1'], [], title='', expected_revision=doc.document_revision)
    old = svc.jobs.create_job('c', project['project_id'], job_type='teacher_lesson_ppt_manuscript_generation', request_id='old')
    svc.jobs.update_job('c', old['id'], status='failed', request_snapshot={'render':False})
    project = svc.update('c', project['project_id'], {'status':'building', 'job_id':old['id']})
    copies = []
    monkeypatch.setattr(svc.candidates, 'clone_checkpoint', lambda source, target: copies.append((source, target)))
    async def scenario():
        started = svc.start('c', project['project_id'], project['revision'])
        svc.pause('c', project['project_id'], started['revision'])
        await asyncio.gather(*list(svc.jobs._runtime_jobs['c']))
        assert copies == [(old['id'], started['job_id'])]
    asyncio.run(scenario())


def _create_parallel_project(storage_root, jobs_root, document_revision, index):
    svc = PptProjectService(Storage(storage_root), TeacherLessonAuthoringRepository(jobs_root))
    svc.create('c', ['l1'], [], title=f'PPT {index}', expected_revision=document_revision)


def test_four_process_project_saves_keep_every_result(fixture):
    svc, storage, doc = fixture
    context = multiprocessing.get_context('spawn')
    processes = [context.Process(target=_create_parallel_project, args=(
        str(Path(storage._courses_dir).parent), str(svc.jobs.root), doc.document_revision, index)) for index in range(4)]
    for process in processes:
        process.start()
    try:
        for process in processes:
            process.join(20)
            assert process.exitcode == 0
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(5)
    projects = storage.load_course('c')['teacher_ppt_projects']
    assert {project['title'] for project in projects.values()} == {f'PPT {index}' for index in range(4)}


def test_failed_export_never_publishes_partial_file_and_retry_keeps_original_revision(fixture, monkeypatch):
    from routers import ppt_projects as routes
    from starlette.requests import Request
    svc, _, doc = fixture
    project = svc.create('c', ['l1'], [], title='', expected_revision=doc.document_revision)
    rendered = {'task_id':'old-render', 'manuscript_revision':'old-manuscript',
                'deck':{'source':'old'}, 'ppt_manuscript':{'manuscript_revision':'old-manuscript'}}
    svc.update('c', project['project_id'], {'status':'paused', 'source_state':'stale',
        'manuscript':{'manuscript_revision':'new'}, 'last_good_render':rendered})
    monkeypatch.setattr(routes, 'owned_course', lambda *_: {})
    target = svc.jobs.root / 'ppt_project_exports' / f"{project['project_id']}-old-render.pptx"
    calls = []
    def fail(content, path):
        calls.append(content)
        path.write_bytes(b'partial')
        raise RuntimeError('renderer unavailable')
    monkeypatch.setattr(routes, 'export_slide_deck_v6_pptx', fail)
    request = Request({'type':'http','headers':[]})
    with pytest.raises(RuntimeError, match='renderer unavailable'):
        asyncio.run(routes.export('c', project['project_id'], request, svc))
    assert not target.exists()
    assert svc.load('c', project['project_id'])['last_good_render'] == rendered
    def succeed(content, path):
        calls.append(content)
        path.write_bytes(b'complete')
    monkeypatch.setattr(routes, 'export_slide_deck_v6_pptx', succeed)
    result = asyncio.run(routes.export('c', project['project_id'], request, svc))
    assert Path(result.path).read_bytes() == b'complete'
    asyncio.run(routes.export('c', project['project_id'], request, svc))
    assert len(calls) == 2
    assert all(content['ppt_manuscript']['manuscript_revision'] == 'old-manuscript' for content in calls)
