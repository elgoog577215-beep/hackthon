from copy import deepcopy
import json

from course_document import CourseDocument, refresh_document_revision
from teacher_content_migration import migrate


def write_fixture(root,cid='c',conflict=False):
    (root/'courses').mkdir(parents=True,exist_ok=True);(root/'teacher_lesson_authoring').mkdir(exist_ok=True)
    doc=refresh_document_revision(CourseDocument(course_id=cid,title='课程'))
    nodes=[{'node_id':'l1','node_name':'第一讲','node_level':1},{'node_id':'s1','node_name':'主题','parent_node_id':'l1','node_level':2}]
    raw={'course_id':cid,'course_name':'课程','authoring_surface':'teacher','owner_id':'t','course_document':doc.model_dump(mode='json'),
        'course_document_revision':doc.document_revision,'generation_job_id':'j-'+cid}
    author={'course_id':cid,'outline_revision_id':'o1','lessons':{'l1':{'working_revision_id':'p1','working_script_revision_id':'r1','source_state':'stale' if conflict else 'current',
        'revisions':[{'revision_id':'p1','source_outline_revision_id':'o1'}], 'script_revisions':[{'revision_id':'r1','publication_eligible':True,'source_lesson_plan_revision_id':'p1',
        'sections':[{'section_node_id':'s1','blocks':[{'block_id':'b1','content':'课程定义。','role':'concept'}]}]}]}}}
    source={'course_id':cid,'course_name':'课程','nodes':nodes,'blueprint_revision_id':'o1','course_plan':{'chapters':[{'node_id':'l1','sections':[{'node_id':'s1'}]}]}}
    (root/'generation_workspaces').mkdir(exist_ok=True)
    (root/'courses'/f'{cid}.json').write_text(json.dumps(raw))
    (root/'teacher_lesson_authoring'/f'{cid}.json').write_text(json.dumps(author))
    (root/'generation_workspaces'/f'j-{cid}.json').write_text(json.dumps({'course_id':cid,'course_data':source}))


def files(root):return {str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*.json')}


def test_preflight_apply_verify_are_idempotent_and_conflicts_untouched(tmp_path):
    root=tmp_path/'data';write_fixture(root);write_fixture(root,'conflict',True)
    (root/'courses'/'student.json').write_text(json.dumps({'course_id':'student','nodes':[],'original':'preserved'}))
    before=files(root)
    pre=migrate(root)
    assert {r['course_id']:r['status'] for r in pre['courses']}=={'c':'ready','conflict':'conflict','student':'historical_student'},pre
    assert files(root)==before
    report=migrate(root,mode='apply',backup_dir=tmp_path/'backups')
    assert report['backup']
    assert report['courses'][0]['status']=='migrated',report
    after=files(root)
    assert after['courses/conflict.json']==before['courses/conflict.json']
    assert after['courses/student.json']==before['courses/student.json']
    assert after['generation_workspaces/j-c.json']==before['generation_workspaces/j-c.json']
    again=migrate(root,mode='apply',backup_dir=tmp_path/'backups',course_ids=['c'])
    assert again['courses'][0]['status']=='already_unified'
    assert files(root)==after
    verified=migrate(root,mode='verify',course_ids=['c'])
    assert verified['courses'][0]['lessons']==1


def test_interrupted_projection_is_repaired_without_recommitting_content(tmp_path):
    root=tmp_path/'data';write_fixture(root)
    ap=root/'teacher_lesson_authoring/c.json'
    original=ap.read_bytes()
    migrate(root,mode='apply',backup_dir=tmp_path/'backup')
    canonical=(root/'courses/c.json').read_bytes()
    ap.write_bytes(original)
    assert migrate(root)['courses'][0]['status']=='projection_repair'
    assert ap.read_bytes()==original
    assert migrate(root,mode='apply',backup_dir=tmp_path/'backup')['courses'][0]['status']=='migrated'
    assert (root/'courses/c.json').read_bytes()==canonical
    assert 'sections' not in json.loads(ap.read_text())['lessons']['l1']['script_revisions'][0]
    assert migrate(root,mode='verify')['courses'][0]['status']=='already_unified'
