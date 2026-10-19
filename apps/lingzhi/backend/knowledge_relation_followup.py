"""Post-save orchestration. Knowledge generation and its candidate are immutable here."""
import asyncio
import logging

logger = logging.getLogger(__name__)


def record(svc, course_id, source_id, value):
    # Completed jobs are frozen by the repository. Coordination belongs alongside
    # them in the same durable course state, never inside the saved candidate.
    with svc.authoring._course_lock(course_id):
        state = svc.authoring.load(course_id)
        state.setdefault('knowledge_relation_followups', {})[source_id] = value
        svc.authoring._save(state)


async def run_followup(svc, course_id, source_id):
    from knowledge_relation_generation import PIPELINE, run
    try:
        with svc.authoring._course_lock(course_id):
            source = svc.authoring.get_job(course_id, source_id)
            if not (source.get('auto_relations') and source['status'] == 'completed'
                    and (source.get('checkpoint') or {}).get('candidate')):
                return
            job, created = svc.start(course_id, 'tree', f'relations-after-{source_id}',
                source['source_knowledge_revision'], source['source_document_revision'],
                source_mode='handouts', lesson_id=source['knowledge_lesson_id'],
                pipeline=PIPELINE, relation_source_job_id=source_id)
            record(svc, course_id, source_id, {'job_id':job['id'], 'status':'created'})
        # A duplicate request observes the existing job; it cannot run it twice.
        if created:
            task = asyncio.create_task(run(svc, course_id, job['id']), name=job['id'])
            svc.authoring.track_runtime_job(course_id, task)
            await task
    except Exception as exc:
        logger.exception('Relation followup failed for source job %s', source_id)
        record(svc, course_id, source_id, {
            'status':'failed', 'error':{'code':type(exc).__name__,
                'message':'关联任务未能接续，知识树已保存；请单独发起关联分析。'}})
