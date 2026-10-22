from copy import deepcopy
from companion_teaching_feedback import summarize_feedback, learning_summary

ROSTER=[{'learner_id':'u','status':'active'},{'learner_id':'v','status':'active'},{'learner_id':'w','status':'active'}]
def row(actor='u',attempt='a',release='r',passed=False,support=0):
    return {'feedback_id':'f'+attempt,'actor_id':actor,'kind':'practice_result','release_id':release,'received_at':'2026-10-22T01:00:00Z',
        'payload':{'attempt_id':attempt,'receipt_id':'receipt'+attempt},'assessment':{'result':{'passed':passed,'grading_confidence':.9,'support_level':support},
            'task':{'concept_ids':['k'],'knowledge_revision_refs':{'k':'kr'},'node_id':'n','prompt':'一题'}}}

def test_denominator_deduplication_and_no_data_are_explicit():
    a=row();result=summarize_feedback(ROSTER,[a,a,row(attempt='b'),row(actor='v',attempt='c',passed=True,support=1)],release_id='r')
    topic=result['topics'][0]
    assert result['roster_count']==3
    assert topic['evidence_students']==2 and topic['no_data_students']==1
    assert topic['repeated_failure_students']==1 and topic['assisted_students']==1
    assert len(topic['evidence'])==3

def test_other_release_revoked_learner_and_private_questions_do_not_enter_counts():
    data=[row(release='old'),row(actor='not-granted'),{'kind':'course_question','actor_id':'u','payload':{'text':'private wording'}}]
    result=summarize_feedback(ROSTER,data,release_id='r')
    assert not result['topics'] and result['evidence_students']==0
    assert 'private wording' not in str(result)

def test_old_knowledge_revisions_are_separate_and_low_confidence_is_unknown():
    a=row();b=row(attempt='b');b['assessment']['task']['knowledge_revision_refs']={'k':'old'}
    b['assessment']['result']['grading_confidence']=.3
    result=summarize_feedback(ROSTER,[a,b],release_id='r')
    assert len(result['topics'])==2
    assert sum(t['unknown_students'] for t in result['topics'])==1

def test_unbound_multi_point_question_does_not_invent_exact_attribution():
    a=row();a['assessment']['task']['concept_ids']=['k','other']
    assert summarize_feedback(ROSTER,[a],release_id='r')['unattributed_attempts']==1

def test_time_window_does_not_count_outside_events():
    assert not summarize_feedback(ROSTER,[row()],release_id='r',since='2026-10-23T00:00:00Z')['topics']

def test_summary_does_not_include_private_memory_and_opt_out_withdraws_data():
    context={'revision':3,'feedback_consent':True,'goal':{'text':'考试','purpose':'exam'},'memories':[{'text':'private'}]}
    public=learning_summary(context,{'summary':{'formal_evidence_count':2}})
    assert public['goal']=={'text':'考试','purpose':'exam'} and 'private' not in str(public)
    context['feedback_consent']=False
    assert learning_summary(context,{})=={'schema_version':'companion_feedback_v1','consent_revision':3,'withdrawn':True}
