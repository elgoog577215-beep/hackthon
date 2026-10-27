"""Pure version/content binding checks shared by authoring and practice."""
from copy import deepcopy
from course_versioning import stable_hash

BINDING = 'knowledge_criterion_binding_v1'


def criterion_signature(c):
    return stable_hash({k:deepcopy(c.get(k))for k in ('criterion_id','revision_id','knowledge_ids','knowledge_revision_refs',
        'dimension','observable_performance','verification_method','controlled_conditions','checkpoints','scoring','evidence_policy')},prefix='kcgs_')


def content_signature(q):
    return stable_hash({'prompt':q.get('prompt'),'spec':q.get('question_spec'),'solution':q.get('solution_revision_id')},prefix='kcqcontent_')


def valid_binding(q,c):
    b=q.get('criterion_binding')or{}
    return bool(b.get('contract')==BINDING and b.get('reviewed')is True
        and b.get('criterion_id')==c['criterion_id'] and b.get('criterion_revision')==c['revision_id']
        and b.get('criterion_signature')==criterion_signature(c) and b.get('knowledge_revision_refs')==c['knowledge_revision_refs']
        and b.get('checkpoint_ids')==[p['checkpoint_id']for p in c['checkpoints']]
        and b.get('content_signature')==content_signature(q))
