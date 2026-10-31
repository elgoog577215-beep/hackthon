"""Build an empty core task checkpoint from frozen inputs."""
from generic_knowledge import sources
from knowledge_core_contract import CONTRACT,group_materials
from knowledge_registry_identity import existing_catalog

def initial_pipeline(raw,context,job_id):
    materials=[{'key':key,'text':unit['source_text']} for key,unit in sources(context).items()]
    return {'schema_version':'inventory_atomic_v1','generation_contract':CONTRACT,'prompt_contract':CONTRACT,
        'processing_contract':CONTRACT,'generation_mode':'core_v1','revision':0,'identity_job_id':job_id,
        'organize_hierarchy':True,'include_relations':False,'items':[],'batches':[],
        'inventory_batches':[{'id':f'core-{i}','source_keys':[m['key'] for m in group],'status':'pending'}
            for i,group in enumerate(group_materials(materials),1)],'names':{'result':{}},'catalog':existing_catalog(raw)}
