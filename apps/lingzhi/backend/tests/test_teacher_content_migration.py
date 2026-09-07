from copy import deepcopy
import json

import pytest

from course_document import CourseDocument, document_from_legacy_course
from teacher_content_migration import migrate
from teacher_course_content import commit_authoring
from teacher_lesson_authoring import TeacherLessonAuthoringRepository, TeacherLessonAuthoringError


def write_fixture(root, cid='c', conflict=False):
    (root/'courses').mkdir(parents=True, exist_ok=True)
    (root/'teacher_lesson_authoring').mkdir(exist_ok=True)
    doc = document_from_legacy_course({'course_id':cid, 'course_name':'课程', 'nodes':[
        {'node_id':'l1','node_name':'第一讲','node_level':1},
        {'node_id':'s1','node_name':'主题','parent_node_id':'l1','node_level':2}]})
    raw = {'course_id':cid, 'authoring_surface':'teacher', 'teacher_production_schema':'unified_teacher_v1',
           'course_document':doc.model_dump(mode='json'), 'course_document_revision':doc.document_revision}
    author = {'course_id':cid, 'outline_revision_id':'o1', 'lessons':{'l1':{
        'working_revision_id':'p1', 'working_script_revision_id':'r1', 'source_state':'current',
        'script_revisions':[{'revision_id':'r1','publication_eligible':True,'source_lesson_plan_revision_id':'p1',
            'sections':[{'section_node_id':'s1','blocks':[{'block_id':'b1','content':'课程定义。','role':'concept'}]}]}]}}}
    class OldStorage:
        emit_course_events = False
        def update_course_data(self, course_id, update):
            nonlocal raw
            raw = update(deepcopy(raw))
            return deepcopy(raw)
    compact = commit_authoring(OldStorage(), author)
    if conflict:
        raw['course_document']['blocks'] = []
    (root/'courses'/f'{cid}.json').write_text(json.dumps(raw))
    (root/'teacher_lesson_authoring'/f'{cid}.json').write_text(json.dumps(compact))
    return raw, compact


def files(root):
    return {str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*.json')}


def test_preflight_apply_verify_are_idempotent_and_conflicts_untouched(tmp_path):
    root = tmp_path/'data'
    write_fixture(root)
    write_fixture(root, 'conflict', True)
    (root/'courses'/'student.json').write_text(json.dumps({'course_id':'student','nodes':[]}))
    before = files(root)
    assert {r['course_id']:r['status'] for r in migrate(root)['courses']} == {
        'c':'ready', 'conflict':'conflict', 'student':'historical_student'}
    assert files(root) == before
    report = migrate(root, mode='apply', backup_dir=tmp_path/'backup')
    assert any(item['status'] == 'conflict' for item in report['courses'])
    assert files(root) == before
    assert not (tmp_path/'backup').exists()
    report = migrate(root, mode='apply', backup_dir=tmp_path/'backup', course_ids=['c'])
    assert report['courses'][0]['status'] == 'migrated'
    after = files(root)
    assert after['courses/conflict.json'] == before['courses/conflict.json']
    assert after['courses/student.json'] == before['courses/student.json']
    restored = json.loads(after['teacher_lesson_authoring/c.json'])
    assert restored['lessons']['l1']['script_revisions'][0]['sections'][0]['blocks'][0]['content'] == '课程定义。'
    assert not json.loads(after['courses/c.json'])['course_document']['blocks']
    assert migrate(root, mode='verify', course_ids=['c'])['courses'][0]['status'] == 'already_authoritative'
    assert migrate(root, mode='apply', backup_dir=tmp_path/'backup', course_ids=['c'])['courses'][0]['status'] == 'already_authoritative'
    assert files(root) == after


def test_interrupted_cleanup_can_resume_and_runtime_does_not_resolve_old_refs(tmp_path):
    root = tmp_path/'data'
    raw, _ = write_fixture(root)
    repo = TeacherLessonAuthoringRepository(root/'teacher_lesson_authoring')
    with pytest.raises(TeacherLessonAuthoringError, match='旧正文引用'):
        repo.load('c')
    migrate(root, mode='apply', backup_dir=tmp_path/'backup')
    author = (root/'teacher_lesson_authoring/c.json').read_bytes()
    (root/'courses/c.json').write_text(json.dumps(raw))
    assert migrate(root, mode='apply', backup_dir=tmp_path/'backup')['courses'][0]['status'] == 'migrated'
    assert (root/'teacher_lesson_authoring/c.json').read_bytes() == author
    assert repo.load('c')['lessons']['l1']['script_revisions'][0]['sections']


def test_live_tasks_and_unbound_body_are_not_migrated(tmp_path):
    root = tmp_path/'data'
    raw, author = write_fixture(root)
    author['jobs'] = {'j':{'status':'running'}}
    (root/'teacher_lesson_authoring/c.json').write_text(json.dumps(author))
    before = files(root)
    assert migrate(root)['courses'][0]['status'] == 'conflict'
    assert files(root) == before
    raw.pop('teacher_handouts')
    (root/'courses/c.json').write_text(json.dumps(raw))
    (root/'teacher_lesson_authoring/c.json').write_text(json.dumps({'course_id':'c','lessons':{}}))
    assert migrate(root)['courses'][0]['status'] == 'conflict'


def test_activation_preserves_paused_jobs_without_permitting_migration(tmp_path):
    root = tmp_path/'data'
    write_fixture(root)
    migrate(root, mode='apply', backup_dir=tmp_path/'backup')
    path = root/'teacher_lesson_authoring/c.json'
    author = json.loads(path.read_text())
    author['jobs'] = {'j': {'status': 'paused', 'checkpoint': {'complete_blocks': ['b1']}}}
    path.write_text(json.dumps(author))
    before = files(root)
    report = migrate(root, activation_check=True)['courses'][0]
    assert report['status'] == 'already_authoritative'
    assert report['reference_revisions'] == 0
    assert migrate(root)['courses'][0]['status'] == 'conflict'
    assert migrate(root, mode='apply', backup_dir=tmp_path/'backup')['courses'][0]['status'] == 'conflict'
    assert files(root) == before
    with pytest.raises(ValueError, match='read-only'):
        migrate(root, mode='apply', activation_check=True)
    author['jobs']['j']['status'] = 'running'
    path.write_text(json.dumps(author))
    assert migrate(root, activation_check=True)['courses'][0]['status'] == 'conflict'


def test_activation_still_reports_legacy_references_on_paused_courses(tmp_path):
    import subprocess
    import sys
    from pathlib import Path
    root = tmp_path/'data'
    _, author = write_fixture(root)
    author['jobs'] = {'j': {'status': 'paused'}}
    (root/'teacher_lesson_authoring/c.json').write_text(json.dumps(author))
    before = files(root)
    script = Path(__file__).resolve().parents[2]/'scripts/migrate_teacher_content.py'
    result = subprocess.run([sys.executable, str(script), '--data-dir', str(root), '--require-teacher-bodies'], capture_output=True, text=True)
    assert result.returncode == 1
    assert json.loads(result.stdout)['courses'][0]['reference_revisions'] == 1
    assert files(root) == before
