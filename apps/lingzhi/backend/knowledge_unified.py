"""Select version-matched completed knowledge, never infer lexical provenance."""
from copy import deepcopy

from course_document import stable_hash
from course_repository import CourseDocumentConflict
from generic_knowledge import require
from handout_knowledge import handout_input_signature

CONTRACT='knowledge_unified_v1'


def protected_body(tree):
    """Every knowledge field is frozen; only its teaching profile may be added."""
    return {**{k:deepcopy(tree.get(k)) for k in ('categories','concept_groups','lessons','knowledge_coverage',
        'knowledge_inventory','inventory_source_coverage','terminology_revision','gap_records','gaps')},
        'knowledge_points':[{k:deepcopy(v) for k,v in p.items() if k!='kc_skill_profile'}
                            for p in tree.get('knowledge_points',[])]}


def body_signature(tree):
    return stable_hash(protected_body(tree),prefix='kbody_')


def validate_core(tree,lesson_id):
    require(isinstance(tree,dict) and not tree.get('generation_preview')
        and tree.get('atomic_assessment',{}).get('ready_for_adoption') is True,
        '知识主体尚未完成或有阻塞项，不能作为配套生成基线')
    points=tree.get('knowledge_points',[])
    require(points and any(lesson_id in p.get('section_refs',[])for p in points),'知识主体没有当前讲次')
    require(all(p.get('knowledge_id') and p.get('revision_id') and p.get('statement') and p.get('name')for p in points)
        and len({p['knowledge_id']for p in points})==len(points),'知识主体身份或完整知识缺失')
    require(not tree.get('knowledge_coverage',{}).get('missing_unit_ids'),'知识主体的覆盖缺口尚未处理')


def select_core(raw,state,context,lesson_id,base_job_id=''):
    """Prefer the current displayed candidate; accepted content remains authoritative."""
    from knowledge_first import knowledge_revision
    jobs=state.get('jobs',{})
    current=raw.get('course_knowledge_base') or {}
    def eligible(job,tree,*,adopted=False):
        require(job.get('actor')==raw.get('owner_id') and job.get('course_id')==raw['course_id']
            and job.get('knowledge_lesson_id')==lesson_id and job.get('source_mode')=='handouts',
            '知识主体不属于当前课程、讲次或拥有者')
        require(job.get('status')=='completed' or job.get('execution_contract')==CONTRACT
            and job.get('status')in {'failed','paused','cancelled'},'原任务的知识主体尚未完成')
        frozen=job.get('request_snapshot',{}).get('knowledge_generation_context')
        require(frozen and handout_input_signature(frozen)==handout_input_signature(context)
            and job.get('source_document_revision')==raw.get('course_document_revision'),
            '本讲讲义或课程信息已变化，不能复用旧知识主体')
        require(adopted or job.get('source_knowledge_revision')==knowledge_revision(raw),
            '知识基线已变化，不能复用旧候选')
        validate_core(tree,lesson_id)
        return {'tree':deepcopy(tree),'origin_job_id':job['id'],'origin_tree_revision':tree.get('revision_id'),
                'body_signature':body_signature(tree),'origin':'accepted' if adopted else 'candidate'}
    def tree_of(job):
        cp=job.get('checkpoint') or {}
        return cp.get('candidate') or cp.get('atomic_pipeline',{}).get('core_tree') or {}
    if base_job_id:
        require(base_job_id in jobs,'指定知识主体不存在')
        adopted=current.get('status')=='accepted' and current.get('generation_job_id')==base_job_id
        return eligible(jobs[base_job_id],current if adopted else tree_of(jobs[base_job_id]),adopted=adopted)
    # A newer completed enrichment can extend an accepted baseline without
    # overwriting it; candidates must still bind the current knowledge revision.
    for job in sorted(jobs.values(),key=lambda j:j.get('created_at',''),reverse=True):
        if job.get('type')!='course_knowledge_tree_generation' or job.get('knowledge_lesson_id')!=lesson_id:continue
        try:return eligible(job,tree_of(job))
        except CourseDocumentConflict:continue
    origin=jobs.get(current.get('generation_job_id'))
    if current.get('status')=='accepted' and origin:
        try:return eligible(origin,current,adopted=True)
        except CourseDocumentConflict:pass
    return None


def prepare_pipeline(raw,context,job_id,generation_mode,reuse=None):
    from knowledge_core import initial_pipeline
    pipeline=initial_pipeline(raw,context,job_id)
    pipeline.update(execution_contract=CONTRACT,generation_mode=generation_mode,
                    include_relations=generation_mode=='full_v1')
    if reuse:
        pipeline.update(core_tree=deepcopy(reuse['tree']),core_reuse={k:v for k,v in reuse.items()if k!='tree'},
            inventory_batches=[],core_review={'status':'completed'},
            hierarchy={'status':'completed','result':{'schema_version':'knowledge_hierarchy_v5'}})
    return pipeline
