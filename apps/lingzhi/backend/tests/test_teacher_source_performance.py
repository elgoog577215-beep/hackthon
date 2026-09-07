import asyncio
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import multiprocessing
from pathlib import Path
import threading

from course_repository import CourseDocumentRepository
from ppt_projects import PptProjectService
from teacher_content_projection import project_teacher_content
from teacher_lesson_authoring import TeacherLessonAuthoringRepository, TeacherLessonAuthoringService
from backend.tests.test_teacher_lesson_authoring import standard_lesson_plan, single_section_course_data
from backend.tests.test_unified_teacher_content import course, authoring


def test_teacher_draft_can_start_with_different_generation_title(tmp_path):
    import pytest
    from storage import Storage
    from course_repository import CourseDocumentConflict
    storage = Storage(data_dir=str(tmp_path))
    repository = CourseDocumentRepository(storage)
    asyncio.run(repository.create_teacher_draft('draft', title='Course shell', metadata={'owner_id': 'teacher'}))
    asyncio.run(repository.claim_teacher_draft_for_generation('draft', title='Generation topic', job_id='job-1'))
    saved = storage.load_course('draft')
    assert saved['course_name'] == 'Generation topic'
    assert saved['course_document']['title'] == 'Generation topic'
    assert saved['course_document']['blocks'] == []
    assert saved['generation_job_id'] == 'job-1'
    assert saved['owner_id'] == 'teacher'
    with pytest.raises(CourseDocumentConflict):
        asyncio.run(repository.claim_teacher_draft_for_generation('draft', title='Other', job_id='job-2'))
    assert storage.load_course('draft') == saved


def test_teacher_body_is_the_only_read_source_for_preview_and_ppt(course):
    storage, _ = course
    repo = TeacherLessonAuthoringRepository(Path(storage._courses_dir).parent / 'teacher_lesson_authoring')
    value = authoring()
    repo._save(value)
    before = deepcopy(storage.load_course('c1'))
    assert before['course_document']['blocks'] == []
    document, _ = CourseDocumentRepository(storage).load_document('c1')
    assert [b.payload['markdown'] for b in document.blocks] == ['正式定义与推导。']
    svc = PptProjectService(storage, repo)
    project = svc.create('c1', ['l1'], [], title='讲义课件', expected_revision=document.document_revision)
    assert svc.document(project).blocks == document.blocks
    value['lessons']['l1']['script_revisions'][0]['sections'][0]['blocks'][0]['content'] = '教师修改后的正文。'
    value['lessons']['l1']['script_revisions'][0]['revision_id'] = 'r2'
    value['lessons']['l1']['working_script_revision_id'] = 'r2'
    repo._save(value)
    assert not svc.source_current(project)
    assert project_teacher_content(storage.load_course('c1'), storage=storage)['course_document']['blocks'][0]['payload']['markdown'] == '教师修改后的正文。'
    assert storage.load_course('c1')['course_document'] == before['course_document']


def test_advisory_plan_does_not_call_repair_model(tmp_path):
    repo = TeacherLessonAuthoringRepository(tmp_path)
    repo.set_outline('course-1', 'outline-v1')
    job = repo.create_job('course-1', 'L1-1', request_id='advice', source_outline_revision_id='outline-v1')
    async def planner(*args):
        return {'plan':standard_lesson_plan(), 'generation_source':'model'}
    async def repairer(**kwargs):
        raise AssertionError('Advice must not request another model generation')
    result = asyncio.run(TeacherLessonAuthoringService(repo).run_plan_job(
        course_id='course-1', lesson_unit_id='L1-1', job_id=job['id'],
        course_data=single_section_course_data(), planner=planner, repairer=repairer))
    assert result['status'] == 'completed'
    assert repo.lesson('course-1', 'L1-1')['working_revision_id']
    assert not result.get('auto_improvement')


def test_other_courses_do_not_wait_on_locked_course_and_noop_does_not_save(tmp_path):
    repo = TeacherLessonAuthoringRepository(tmp_path)
    ready = threading.Event()
    release = threading.Event()
    def hold():
        with repo._course_lock('a'):
            ready.set()
            assert release.wait(5)
    with ThreadPoolExecutor(2) as executor:
        held = executor.submit(hold)
        assert ready.wait(2)
        try:
            executor.submit(repo.set_outline, 'b', 'o1').result(timeout=2)
        finally:
            release.set()
        held.result(timeout=2)
    job = repo.create_job('b', 'l', request_id='j')
    before = (tmp_path/'b.json').read_bytes()
    repo.update_job('b', job['id'], status=job['status'])
    assert (tmp_path/'b.json').read_bytes() == before


def _write_job(root, index):
    repo = TeacherLessonAuthoringRepository(root)
    repo.create_job('course', f'lesson-{index}', request_id=f'job-{index}')


def test_multiprocess_writes_keep_all_four_lessons(tmp_path):
    context = multiprocessing.get_context('spawn')
    processes = [context.Process(target=_write_job, args=(str(tmp_path), i)) for i in range(4)]
    for process in processes:
        process.start()
    for process in processes:
        process.join(20)
        assert process.exitcode == 0
    assert len(TeacherLessonAuthoringRepository(tmp_path).load('course')['jobs']) == 4


def test_course_metadata_writes_are_isolated_by_course(tmp_path):
    from storage import Storage
    storage = Storage(str(tmp_path))
    ready, release = threading.Event(), threading.Event()
    def hold(raw):
        ready.set()
        assert release.wait(5)
        return {'course_id':'a'}
    with ThreadPoolExecutor(2) as executor:
        first = executor.submit(storage.update_course_data, 'a', hold)
        assert ready.wait(2)
        try:
            second = executor.submit(storage.update_course_data, 'b', lambda raw: {'course_id':'b'})
            assert second.result(timeout=2)['course_id'] == 'b'
        finally:
            release.set()
        first.result(timeout=2)
