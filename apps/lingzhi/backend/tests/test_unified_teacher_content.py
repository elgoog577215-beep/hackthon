import asyncio
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import json

import pytest
from course_document import CourseDocument, course_view_from_document
from course_repository import CourseDocumentRepository, CourseDocumentConflict
from storage import Storage
from teacher_course_content import commit_outline, commit_authoring, hydrate_authoring
from teacher_lesson_authoring import TeacherLessonAuthoringRepository


@pytest.fixture
def course(tmp_path):
    storage = Storage(str(tmp_path / 'data'))
    repo = CourseDocumentRepository(storage)
    asyncio.run(repo.create_teacher_draft('c1', title='测试课程', metadata={'owner_id': 'teacher'}))
    source = {'course_id': 'c1', 'course_name': '测试课程', 'blueprint_revision_id': 'outline-1', 'nodes': [
        {'node_id': 'l1', 'node_level': 1, 'node_name': '第一讲'},
        {'node_id': 's1', 'parent_node_id': 'l1', 'node_level': 2, 'node_name': '主题一'},
        {'node_id': 'l2', 'node_level': 1, 'node_name': '第二讲'},
        {'node_id': 's2', 'parent_node_id': 'l2', 'node_level': 2, 'node_name': '主题二'}]}
    commit_outline(storage, source)
    return storage, source


def authoring(lesson='l1', section='s1', rev='r1', text='正式定义与推导。', block='b1'):
    return {'course_id': 'c1', 'outline_revision_id': 'outline-1', 'lessons': {lesson: {
        'working_revision_id': 'plan1', 'working_script_revision_id': rev,
        'script_revisions': [{'revision_id': rev, 'source_lesson_plan_revision_id': 'plan1',
            'publication_eligible': True, 'sections': [{'section_node_id': section, 'blocks': [
                {'block_id': block, 'role': 'concept', 'module_id': 'core_explanation', 'content': text}]}]}]}}}


def test_formal_handout_reference_roundtrip_and_outline_idempotent(course):
    storage, source = course
    initial = deepcopy(storage.load_course('c1'))
    commit_outline(storage, source)
    assert storage.load_course('c1') == initial
    compact = commit_authoring(storage, authoring())
    assert 'sections' not in compact['lessons']['l1']['script_revisions'][0]
    raw = storage.load_course('c1')
    assert raw['course_document']['blocks'][0]['block_id'] == 'b1'
    assert not raw.get('is_published')
    hydrated = hydrate_authoring(raw, compact)
    assert hydrated['lessons']['l1']['script_revisions'][0]['sections'][0]['blocks'][0]['content'] == '正式定义与推导。'
    commit_authoring(storage, hydrated)
    assert storage.load_course('c1') == raw


def test_different_lectures_merge_and_same_lecture_conflicts(course):
    storage, _ = course
    with ThreadPoolExecutor(2) as executor:
        list(executor.map(lambda value: commit_authoring(storage, value), [authoring(), authoring('l2','s2','r2',block='b2')]))
    raw = storage.load_course('c1')
    assert {b['block_id'] for b in raw['course_document']['blocks']} == {'b1', 'b2'}
    with pytest.raises(CourseDocumentConflict):
        commit_authoring(storage, authoring(rev='r3', text='stale'))
    assert storage.load_course('c1') == raw


def test_interruption_repair_invalid_draft_history_and_retired_blocks(course):
    storage, _ = course
    compact = commit_authoring(storage, authoring())
    # Authoring file write never happened: repair purely from course receipt/binding.
    restored = hydrate_authoring(storage.load_course('c1'), {'course_id': 'c1', 'lessons': {'l1': {}}})
    assert restored['lessons']['l1']['working_script_revision_id'] == 'r1'
    value = hydrate_authoring(storage.load_course('c1'), compact)
    newer = authoring(rev='r2', text='新定义', block='b-new')['lessons']['l1']['script_revisions'][0]
    value['lessons']['l1']['script_revisions'].append(newer)
    value['lessons']['l1']['working_script_revision_id'] = 'r2'
    current = commit_authoring(storage, value)
    raw = storage.load_course('c1')
    assert next(b for b in raw['course_document']['blocks'] if b['block_id']=='b1')['status'] == 'retired'
    assert 'b1' not in {b['block_id'] for n in course_view_from_document(raw, raw['course_document'])['nodes'] for b in n['content_blocks']}
    old = hydrate_authoring(raw, current)['lessons']['l1']['script_revisions'][0]
    assert old['sections'][0]['blocks'][0]['content'] == '正式定义与推导。'
    draft = hydrate_authoring(raw, current)
    draft['lessons']['l1']['script_revisions'].append({'revision_id':'bad', 'publication_eligible':False})
    draft['lessons']['l1']['working_script_revision_id']='bad'
    commit_authoring(storage, draft)
    assert storage.load_course('c1') == raw


def test_repository_shared_save_compacts_and_preserves_conflict(course,tmp_path):
    storage, _ = course
    repo = TeacherLessonAuthoringRepository(tmp_path/'authoring', canonical_storage=storage)
    saved = repo._save(authoring())
    assert saved['lessons']['l1']['script_revisions'][0]['sections']
    disk = json.loads((tmp_path/'authoring/c1.json').read_text())
    assert '_canonical_baselines' not in disk
    assert 'sections' not in disk['lessons']['l1']['script_revisions'][0]
    from teacher_lesson_authoring import TeacherLessonAuthoringError
    with pytest.raises(TeacherLessonAuthoringError, match='已变化'):
        repo._save(authoring(rev='late'))
    assert 'commit_conflict' in json.loads((tmp_path/'authoring/c1.json').read_text())['lessons']['l1']['script_revisions'][0]
    assert storage.load_course('c1')['teacher_handouts']['l1']['revision_id'] == 'r1'


def test_stale_general_write_cannot_overwrite_handout(course):
    storage, _ = course
    stale = storage.load_course('c1')
    commit_authoring(storage, authoring())
    with pytest.raises(CourseDocumentConflict):
        asyncio.run(storage.save_course('c1', stale))


def test_metadata_save_preserves_concurrent_ppt_project(course):
    storage, _ = course
    stale = storage.load_course('c1')
    storage.update_course_data('c1', lambda raw: {**raw, 'teacher_ppt_projects':{'p':{'revision':'r'}}})
    stale['course_name'] = '新名称'
    storage.save_course_sync('c1', stale)
    assert storage.load_course('c1')['teacher_ppt_projects']=={'p':{'revision':'r'}}
