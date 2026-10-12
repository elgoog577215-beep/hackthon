from copy import deepcopy

from course_document import stable_hash
from knowledge_first import material
from knowledge_mastery import build_knowledge_profile, freeze_knowledge_refs
from knowledge_practice import adopted_knowledge_checks
from assessment_contracts import project_public_question
from practice_grading import PracticeGrader


def course():
    package = material()
    points = [dict(deepcopy(p), topic=topic, revision_id='rev-' + p['key'], parent_id=topic)
              for topic, bundle in package['bundles'].items() for p in bundle['points']]
    return {'course_id':'c', 'current_course_version_id':'cv', 'nodes':[{'node_id':topic,'node_level':2} for topic in package['bundles']],
        'course_knowledge_base': {'tree_schema':'knowledge_first_c17_v1', 'status':'accepted','revision_id':'kb',
        'material_revision':stable_hash(package,prefix='mat_'), 'knowledge_points':points,'categories':[]}}


def test_authored_checks_bind_current_point_revisions_and_keep_answers_private():
    c = course()
    checks = adopted_knowledge_checks(c)
    assert len(checks) == 49
    check = next(q for q in checks if q['question_id'] == 'Q-T07')
    assert check['answer_spec']['correct_answer'] == '-3'
    assert check['grading_policy']['method'] == 'deterministic'
    assert freeze_knowledge_refs(c['course_knowledge_base'], check) == check['knowledge_revision_refs']
    public = project_public_question(check)
    assert 'answer_spec' not in public
    assert public['knowledge_revision_refs'] == check['knowledge_revision_refs']
    assert check['revision_id'] == next(q for q in adopted_knowledge_checks(c) if q['question_id']=='Q-T07')['revision_id']


def test_unadopted_or_changed_material_does_not_publish_stale_checks():
    c=course()
    c['course_knowledge_base']['status']='candidate'
    assert not adopted_knowledge_checks(c)
    c['course_knowledge_base']['status']='accepted'
    c['course_knowledge_base']['material_revision']='outdated'
    assert not adopted_knowledge_checks(c)
    c=course(); c['course_knowledge_base']['knowledge_points'][6]['statement']='Changed rule'
    assert 'Q-T07' not in {q['question_id'] for q in adopted_knowledge_checks(c)}


def test_real_check_results_raise_and_lower_mastery_without_repeat_credit():
    c=course(); q=next(q for q in adopted_knowledge_checks(c) if q['question_id']=='Q-T07')
    kid=q['concept_ids'][0]
    def attempt(number,answer):
        return {'attempt_id':f'a{number}','user_id':'u','course_id':'c','course_version_id':'cv',
            'task_revision_id':q['revision_id'],'concept_ids':q['concept_ids'],'knowledge_revision_refs':q['knowledge_revision_refs'],
            'status':'graded','updated_at':str(number),'result':PracticeGrader._grade_deterministic(q,q['answer_spec'],{'text':answer})}
    def score(attempts):
        result=build_knowledge_profile(c['course_knowledge_base'],course_id='c',course_version_id='cv',user_id='u',attempts=attempts,events=[])
        return next(n for n in result['nodes'] if n['knowledge_id']==kid)['mastery']
    assert score([]) is None
    assert score([attempt(1,'-3')]) == 66.7
    assert score([attempt(1,'-3'),attempt(2,'-3')]) == 66.7
    assert score([attempt(1,'-3'),attempt(2,'-4')]) == 33.3


def test_question_and_note_context_count_as_activity_only():
    c=course(); p=c['course_knowledge_base']['knowledge_points'][0]; kid=p['knowledge_id']
    anchor={'concept_ids':[kid],'knowledge_revision_refs':{kid:p['revision_id']}}
    events=[{'event_id':'e1','event_type':'assistant_question_submitted','user_id':'u','course_id':'c','course_version_id':'cv','metadata':{'context_ref':{'content_anchor':anchor}}},
            {'event_id':'e2','event_type':'learning_record_created','user_id':'u','course_id':'c','course_version_id':'cv','record_id':'note1','evidence':{'anchor':{'block_id':'b'}},'metadata':{'content_anchor':anchor}}]
    result=build_knowledge_profile(c['course_knowledge_base'],course_id='c',course_version_id='cv',user_id='u',attempts=[],events=events)
    point=next(n for n in result['nodes'] if n['knowledge_id']==kid)
    assert point['activity_count']==2
    assert point['mastery'] is None
