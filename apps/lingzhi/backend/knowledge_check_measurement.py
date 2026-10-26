"""Read-only checks against approved rubric revisions, not a new mastery score."""

POLICY={'rule_version':'criterion_evidence_v1','policy_status':'proposed','min_independent_successes':2,
        'min_distinct_variants':2,'requires_independence':True,'unknown_score':None,
        'same_source_counts_once':True,'calibrated':False}


def summarize_check(criterion,attempts,*,user_id,course_id,course_version_id):
    result={'status':'unassessed','latest_score':None,'max_score':len(criterion['checkpoints']),
        'independent_successes':0,'independent_variants':0,'evidence':[], 'mastery_probability':None}
    if criterion.get('review_status')not in {'approved','owner_accepted'} or criterion.get('readiness')!='ready':
        return {**result,'availability':'design_pending'}
    cid=criterion['criterion_id'];items={c['checkpoint_id']for c in criterion['checkpoints']}
    independent=[];seen=set()
    for attempt in sorted(attempts,key=lambda a:(str(a.get('created_at','')),str(a.get('attempt_id','')))):
        aid=attempt.get('attempt_id');key=attempt.get('assessment_evidence_key');graded=attempt.get('result')or{}
        confidence=graded.get('grading_confidence')
        if (not user_id or attempt.get('user_id')!=user_id or attempt.get('course_id')!=course_id or not aid or aid in seen
            or not course_version_id or attempt.get('course_version_id')!=course_version_id
            or type(confidence)not in {int,float} or not .72<=confidence<=1
            or not key or not attempt.get('task_revision_id') or attempt.get('status')!='graded'
            or graded.get('status')=='pending_review' or graded.get('historical_only')
            or attempt.get('criterion_revision_refs',{}).get(cid)!=criterion['revision_id']
            or any(attempt.get('knowledge_revision_refs',{}).get(k)!=v for k,v in criterion['knowledge_revision_refs'].items())):continue
        seen.add(aid);checks=graded.get('criterion_results',{}).get(cid,{})
        if set(checks)!=items or any(type(v)is not bool for v in checks.values()):continue
        score=sum(checks.values());passed=score==len(items)
        support=bool(attempt.get('support_level')or attempt.get('ai_support_level')or graded.get('support_level')or attempt.get('revealed_hint_levels'))
        revealed=bool(attempt.get('solution_revealed')or graded.get('solution_revealed'))
        eligible=not support and not revealed and graded.get('mastery_eligible')is not False and graded.get('evidence_strength')not in {'invalid','scaffolded'}
        result['latest_score']=score
        result['evidence'].append({'attempt_id':aid,'assessment_evidence_key':key,'score':score,
            'independent':eligible,'support':'solution_seen' if revealed else 'assisted' if support else 'independent' if eligible else 'practice_only'})
        if eligible:
            aliases={('evidence',key),('task',attempt['task_revision_id'])}
            overlaps=[g for g in independent if g['aliases'] & aliases]
            for group in overlaps:aliases.update(group['aliases'])
            independent=[g for g in independent if g not in overlaps]
            independent.append({'aliases':aliases,'passed':passed})
    count=sum(g['passed']for g in independent);policy=criterion['evidence_policy']
    result.update(independent_successes=count,independent_variants=len(independent))
    if result['latest_score']is not None:
        result['status']='check_supported' if count>=policy['min_independent_successes'] and count>=policy['min_distinct_variants'] else 'needs_more_evidence'
    return result
