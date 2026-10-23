"""Rebuildable read projections of committed authoring state, never a task owner."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import threading

_READERS=ThreadPoolExecutor(max_workers=2,thread_name_prefix='knowledge-observation')
_FIELDS=('id','type','lesson_unit_id','knowledge_lesson_id','status','phase','progress','message',
    'created_at','generation_started_at','completed_at','last_content_at','received_chars','pipeline_stage',
    'batch_index','batch_total','inventory_count','completed_batches','relation_count','model_call_count',
    'total_model_seconds','failed_stage','failed_batch_id','transport_retry_count','transport_retry_limit',
    'transport_retry_active_count','transport_retry_stage','knowledge_pipeline')


def progress_summary(pipeline):
    result={k:deepcopy(pipeline[k]) for k in ('schema_version','generation_contract','processing_contract',
        'revision','organize_hierarchy','include_relations','semantic_equivalence_contract') if k in pipeline}
    result.update(summary_contract='knowledge_progress_summary_v1',items=[])
    def rows(values):
        return [{k:deepcopy(row[k]) for k in ('id','key','status','validation_error') if k in row} for row in values]
    result['inventory_batches']=rows(pipeline.get('inventory_batches',[]))
    result['batches']=rows(pipeline.get('batches',[]))
    for key in ('semantic_review','truth_review','identity_review','check_placement','names','hierarchy',
                'registry_relations','relations','semantic_equivalence','kc_profiles'):
        if key not in pipeline:continue
        stage=pipeline[key]
        result[key]={k:deepcopy(stage[k]) for k in ('status','contract') if k in stage}
        if 'batches' in stage:result[key]['batches']=rows(stage['batches'])
        if key=='hierarchy' and stage.get('result'):
            result[key]['result']={'schema_version':stage['result'].get('schema_version')}
    if 'registry_relations' in result:result['relations']=deepcopy(result['registry_relations'])
    return result


def metadata(job):
    result={k:deepcopy(job[k]) for k in _FIELDS if k in job}
    result['received_chars']=int(job.get('received_chars') or len(job.get('partial_text') or ''))
    return result


def observation_state(state):
    jobs=state.get('jobs',{})
    latest={}
    for key,job in jobs.items():
        if job.get('knowledge_pipeline'):
            latest[(job.get('type'),job.get('knowledge_lesson_id') or job.get('lesson_unit_id'))]=key
    selected=set(latest.values()) | {k for k,j in jobs.items() if j.get('status') in {'pending','running'}}
    rows={}
    for key,job in jobs.items():
        row=metadata(job)
        pipeline=(job.get('checkpoint') or {}).get('atomic_pipeline') or {}
        if pipeline:
            projected={'revision':pipeline.get('revision',0)}
            if key in selected:
                for field in ('schema_version','generation_contract','processing_contract','preview_tree',
                              'semantic_equivalence','hierarchy'):
                    if field in pipeline:projected[field]=deepcopy(pipeline[field])
                projected['batches']=[{k:deepcopy(b[k]) for k in ('id','status','tree') if k in b}
                                      for b in pipeline.get('batches',[])]
            row['checkpoint']={'atomic_pipeline':projected}
        rows[key]=row
    return {'course_id':state.get('course_id'),'jobs':rows,'lessons':{
        key:{k:lesson.get(k) for k in ('working_revision_id','working_script_revision_id')}
        for key,lesson in state.get('lessons',{}).items()}}


class KnowledgeObservation:
    def __init__(self,path):
        self.path=path
        self.lock=threading.Lock()
        self.snapshots={}
        self.refreshing=set()

    def publish(self,course_id,state,signature):
        projected=observation_state(state)
        with self.lock:
            previous=self.snapshots.get(course_id)
            if previous and previous[0][0]>signature[0]:return
            self.snapshots[course_id]=(signature,projected)

    def live(self,course_id,job):
        with self.lock:
            cached=self.snapshots.get(course_id)
            if not cached:return
            state=cached[1];old=state['jobs'].get(job.get('id'))
            if not old or old.get('status') not in {'pending','running'}:return
            row={**old,**metadata(job)}
            self.snapshots[course_id]=(cached[0],{**state,'jobs':{**state['jobs'],job['id']:row}})

    def _reload(self,course_id):
        try:
            path=self.path(course_id);before=path.stat()
            state=json.loads(path.read_text(encoding='utf-8'));after=path.stat()
            signature=(after.st_mtime_ns,after.st_size)
            if (before.st_mtime_ns,before.st_size)==signature:self.publish(course_id,state,signature)
        finally:
            with self.lock:self.refreshing.discard(course_id)

    def read(self,course_id,projector):
        path=self.path(course_id)
        try:
            stat=path.stat();signature=(stat.st_mtime_ns,stat.st_size)
        except FileNotFoundError:
            return projector({'jobs':{},'lessons':{}})
        with self.lock:
            cached=self.snapshots.get(course_id)
            if cached and cached[0]!=signature and course_id not in self.refreshing:
                self.refreshing.add(course_id);_READERS.submit(self._reload,course_id)
        if not cached:
            # Atomic replacement keeps this cold read independent of the writer's lock.
            self._reload(course_id)
            with self.lock:cached=self.snapshots.get(course_id)
            if not cached:return projector({'jobs':{},'lessons':{}})
        return projector(cached[1])
