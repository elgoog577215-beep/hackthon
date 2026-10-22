"""Read-only teacher concerns from authorized immutable formal-attempt receipts."""
from collections import defaultdict
from companion_learning import digest


def summarize_feedback(roster,rows,*,release_id,since='',until=''):
    actors={r['learner_id'] for r in roster if r.get('status')=='active'}
    groups={}; seen=set(); attempted=set(); unattributed=0
    for row in rows:
        if row.get('actor_id') not in actors or row.get('kind')!='practice_result' or row.get('release_id')!=release_id:continue
        when=row.get('received_at') or ''
        if since and when<since or until and when>until:continue
        actor=row['actor_id'];payload=row.get('payload') or {};aid=payload.get('attempt_id') or payload.get('receipt_id')
        key=(actor,aid)
        if not aid or key in seen:continue
        seen.add(key);attempted.add(actor)
        assessment=row.get('assessment') or {};task=assessment.get('task') or {};result=assessment.get('result') or {}
        ids=task.get('concept_ids') or [];refs=task.get('knowledge_revision_refs') or {}
        if len(ids)!=1 or not refs.get(ids[0]):unattributed+=1;continue
        kid=ids[0];group_key=(kid,refs[kid],release_id)
        group=groups.setdefault(group_key,{'topic_id':'topic_'+digest(group_key),'knowledge_id':kid,'knowledge_revision_id':refs[kid],
             'release_id':release_id,'node_id':task.get('node_id') or '', 'title':task.get('knowledge_name') or kid,'evidence':[]})
        strength='unknown'
        passed=result.get('passed')
        if type(passed) is bool and float(result.get('grading_confidence') or 0)>=.72:
            strength='assisted' if result.get('support_level') or result.get('solution_seen') else 'independent'
        group['evidence'].append({'actor_id':actor,'attempt_id':aid,'receipt_id':payload.get('receipt_id'),
             'feedback_id':row.get('feedback_id'),'observed_at':when,'outcome':'unknown' if strength=='unknown' else 'passed' if passed else 'not_passed','support':strength})
    topics=[]
    for group in groups.values():
        evidence=group['evidence'];students={e['actor_id'] for e in evidence};failed=defaultdict(int)
        for e in evidence:
            if e['outcome']=='not_passed' and e['support']=='independent':failed[e['actor_id']]+=1
        group.update(evidence_students=len(students),no_data_students=len(actors-students),
          repeated_failure_students=sum(n>=2 for n in failed.values()),
          failed_students=len({e['actor_id'] for e in evidence if e['outcome']=='not_passed'}),
          assisted_students=len({e['actor_id'] for e in evidence if e['support']=='assisted'}),
          independent_pass_students=len({e['actor_id'] for e in evidence if e['support']=='independent' and e['outcome']=='passed'}),
          unknown_students=len({e['actor_id'] for e in evidence if e['outcome']=='unknown'}))
        topics.append(group)
    topics.sort(key=lambda x:(-x['repeated_failure_students'],-x['failed_students'],x['topic_id']))
    return {'schema_version':'teacher_companion_feedback_v1','release_id':release_id,'since':since,'until':until,
       'roster_count':len(actors),'roster_snapshot':'roster_'+digest(sorted(actors)),'evidence_students':len(attempted),
       'no_data_students':len(actors-attempted),'unattributed_attempts':unattributed,'topics':topics,
       'snapshot_id':'feedback_'+digest([sorted(actors),release_id,since,until,topics]),'causal_effect_verified':False}


def learning_summary(context,model):
    base={'schema_version':'companion_feedback_v1','consent_revision':context['revision'],'withdrawn':not context.get('feedback_consent',False)}
    if base['withdrawn']:return base
    goal=context.get('goal') or {}
    return {**base,'goal':{'text':str(goal.get('text') or '')[:2000],'purpose':goal.get('purpose','systematic')},
         'formal_evidence_count':int((model.get('summary') or {}).get('formal_evidence_count') or 0)}
