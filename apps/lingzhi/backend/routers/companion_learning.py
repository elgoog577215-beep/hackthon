"""Verified learner companion settings and source-scoped learning context."""
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field
from ai_teacher_state import ai_teacher_repository, InteractionConflict
from companion_learning import CompanionService
from learner_model_service import build_current_learner_model
from routers.course_learning_access import read_learning_course
from study.auth import study_identity
from study.repository import StudyRepository
from storage import storage

router=APIRouter(tags=['companion-learning'])

class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid')

class Preferences(Strict):
    expected_revision:int=Field(ge=1)
    request_id:str=Field(min_length=8,max_length=160)
    mode:Literal['gentle','on_request']

class Value(Strict):
    text:str=Field(default='',max_length=2000)
    purpose:Literal['systematic','exam','project','mixed']='systematic'
    baseline:str=Field(default='',max_length=1000)
    deadline:str|None=Field(default=None,max_length=40)
    minutes_per_week:int|None=Field(default=None,ge=1,le=10080)
    kind:Literal['preference','agreement','unresolved']='agreement'
    memory_id:str=Field(default='',max_length=160)
    step_id:str=Field(default='',max_length=160)
    enabled:bool=False

class Command(Strict):
    expected_revision:int=Field(ge=1)
    request_id:str=Field(min_length=8,max_length=160)
    action:Literal['save_goal','propose_plan','adopt_plan','reject_plan','defer_step','resume_step','remember','correct_memory','disable_memory','feedback_consent']
    value:Value=Field(default_factory=Value)

class Suppress(Strict):
    key:str=Field(min_length=1,max_length=200)
    mode:Literal['not_now','never','restore']

def service(): return CompanionService(ai_teacher_repository)

def failure(exc):
    if isinstance(exc,InteractionConflict): return HTTPException(409,{'code':'companion_revision_conflict','current':exc.current})
    return HTTPException(422,str(exc))

@router.get('/study/companion/preferences')
def preferences(user=Depends(study_identity)):
    return service().preferences(user['id'])

@router.patch('/study/companion/preferences')
def set_preferences(body:Preferences,user=Depends(study_identity)):
    try: return service().set_preferences(user['id'],body.mode,body.expected_revision,body.request_id)
    except (ValueError,InteractionConflict) as exc: raise failure(exc) from exc

async def course_context(course_id,user):
    course=await read_learning_course(course_id,user)
    model=await run_in_threadpool(build_current_learner_model,course,user_id=user['id'])
    catalog=[{'id':n['node_id'],'title':str(n.get('node_name') or n['node_id'])} for n in course.get('nodes',[])
             if n.get('node_id') and (n.get('node_content') or n.get('course_blocks') or n.get('content_blocks'))]
    return course,model,catalog,str(course.get('current_course_version_id') or '')

def view(user,resource,catalog,revision,model=None,resource_type='course'):
    result=service().read(user['id'],resource,resource_type)
    result.pop('receipts',None)
    result.update(catalog=catalog,source_revision=revision,progress=(model or {}).get('objectives',[]),
                  model_revision_id=(model or {}).get('model_revision_id'))
    return result

@router.get('/courses/{course_id}/learning-records/companion')
async def get_context(course_id:str,user=Depends(study_identity)):
    _,model,catalog,revision=await course_context(course_id,user)
    return view(user,course_id,catalog,revision,model)

@router.post('/courses/{course_id}/learning-records/companion')
async def change_context(course_id:str,body:Command,user=Depends(study_identity)):
    _,model,catalog,revision=await course_context(course_id,user)
    try:
        await run_in_threadpool(service().command,user['id'],course_id,action=body.action,
            expected_revision=body.expected_revision,request_id=body.request_id,value=body.value.model_dump(),catalog=catalog,source_revision=revision)
    except (ValueError,InteractionConflict) as exc: raise failure(exc) from exc
    return view(user,course_id,catalog,revision,model)

def material_context(material_id,user):
    try: material=StudyRepository(storage).get(user['id'],material_id)
    except KeyError: raise HTTPException(404,'Material not found') from None
    revision=(material.get('revisions') or [{}])[-1]
    catalog=[{'id':s['id'],'title':s['title']} for s in revision.get('sections',[]) if s.get('blocks')]
    return catalog,str(revision.get('id') or '')

@router.get('/study/materials/{material_id}/companion')
def get_material_context(material_id:str,user=Depends(study_identity)):
    catalog,revision=material_context(material_id,user)
    return view(user,material_id,catalog,revision,resource_type='personal_material')

@router.post('/study/materials/{material_id}/companion')
def change_material_context(material_id:str,body:Command,user=Depends(study_identity)):
    catalog,revision=material_context(material_id,user)
    try: service().command(user['id'],material_id,action=body.action,expected_revision=body.expected_revision,
        request_id=body.request_id,value=body.value.model_dump(),catalog=catalog,source_revision=revision,resource_type='personal_material')
    except (ValueError,InteractionConflict) as exc: raise failure(exc) from exc
    return view(user,material_id,catalog,revision,resource_type='personal_material')

@router.get('/courses/{course_id}/learning-records/companion/suppressions')
async def get_suppressions(course_id:str,user=Depends(study_identity)):
    await read_learning_course(course_id,user)
    return ai_teacher_repository.list_suppressions(user['id'],course_id)

@router.post('/courses/{course_id}/learning-records/companion/suppressions')
async def suppress(course_id:str,body:Suppress,user=Depends(study_identity)):
    await read_learning_course(course_id,user)
    return ai_teacher_repository.save_suppression(user['id'],course_id,{'suppression_key':body.key,
        'mode':body.mode,'quiet_until':'','action_type':'companion_reminder'})
