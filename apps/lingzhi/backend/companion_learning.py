"""Goal/plan/remembered context and bounded teaching decisions; no score store."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json

from ai_teacher_state import InteractionConflict


def stamp():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:24]


def empty():
    return {'schema_version':'companion_context_v1','revision':1,'goal':None,'goal_history':[],
            'plan':None,'proposal':None,'memories':[],'receipts':{},'feedback_consent':False}


class CompanionService:
    def __init__(self, repository):
        self.repository = repository

    def read(self, user, resource, resource_type='course'):
        return {**empty(), **self.repository.companion_state(user,resource,resource_type=resource_type)}

    def preferences(self,user):
        return {'revision':1,'mode':'gentle', **self.repository.companion_state(user,'settings',resource_type='companion_preferences')}

    def set_preferences(self,user,mode,expected_revision,request_id):
        if mode not in {'gentle','on_request'}: raise ValueError('Invalid companion mode')
        def update(raw):
            state={'revision':1,'mode':'gentle',**raw}
            if state.get('last_request') == request_id:
                if state['mode'] != mode: raise InteractionConflict(state)
                return
            if state['revision'] != expected_revision: raise InteractionConflict(state)
            raw.update(revision=state['revision']+1,mode=mode,last_request=request_id,updated_at=stamp())
        self.repository.companion_state(user,'settings',resource_type='companion_preferences',update=update)
        return self.preferences(user)

    def command(self,user,resource,*,action,expected_revision,request_id,value,catalog,source_revision,resource_type='course'):
        fingerprint=digest([action,value,source_revision])
        def update(raw):
            state={**empty(),**raw}
            if request_id in state['receipts']:
                if state['receipts'][request_id] != fingerprint: raise InteractionConflict(state)
                return
            if state['revision'] != expected_revision: raise InteractionConflict(state)
            now=stamp()
            if action=='save_goal':
                text=str(value.get('text') or '').strip()
                purpose=value.get('purpose','systematic')
                minutes=value.get('minutes_per_week')
                if not text or len(text)>2000 or purpose not in {'systematic','exam','project','mixed'}: raise ValueError('Invalid goal')
                if minutes is not None and (type(minutes) is not int or not 1<=minutes<=10080): raise ValueError('Invalid available time')
                if state['goal']: state['goal_history'].append(deepcopy(state['goal']))
                state['goal']={'text':text,'purpose':purpose,'deadline':value.get('deadline'),
                    'minutes_per_week':minutes,'baseline':str(value.get('baseline') or '')[:1000],
                    'revision':(state['goal'] or {}).get('revision',0)+1,'updated_at':now}
                state['proposal']=None
                if state['plan']: state['plan']['status']='needs_review'
            elif action=='propose_plan':
                if not state['goal']: raise ValueError('Set a goal before planning')
                if not catalog: raise ValueError('No readable learning content')
                purpose=state['goal']['purpose']
                intent={'exam':'辨析重点并独立检查','project':'理解后尝试应用','mixed':'理解并检查应用','systematic':'理解、尝试与自查'}[purpose]
                old={s['node_id']:s for s in (state['plan'] or {}).get('steps',[])}
                state['proposal']={'plan_id':'plan_'+digest([source_revision,state['goal']]),'goal_revision':state['goal']['revision'],
                    'source_revision':source_revision,'status':'proposed','created_at':now,
                    'steps':[{'step_id':'step_'+digest(item['id']),'node_id':item['id'],'title':item['title'],
                              'intent':intent,'decision':old.get(item['id'],{}).get('decision','pending')} for item in catalog]}
            elif action=='adopt_plan':
                proposal=state['proposal']
                if not proposal or proposal['source_revision']!=source_revision: raise InteractionConflict(state)
                state['plan']={**proposal,'status':'active','adopted_at':now}; state['proposal']=None
            elif action=='reject_plan': state['proposal']=None
            elif action in {'defer_step','resume_step'}:
                step=next((s for s in (state['plan'] or {}).get('steps',[]) if s['step_id']==value.get('step_id')),None)
                if not step: raise ValueError('Plan step not found')
                step['decision']='deferred' if action=='defer_step' else 'pending'
            elif action=='remember':
                kind=value.get('kind','agreement'); text=str(value.get('text') or '').strip()
                if kind not in {'preference','agreement','unresolved'} or not text or len(text)>2000: raise ValueError('Invalid memory')
                if len(state['memories'])>=200: raise ValueError('Review existing memories before adding more')
                state['memories'].append({'memory_id':'mem_'+digest([request_id,user,resource]),'kind':kind,'text':text,
                    'status':'active','origin':'student_explicit','source_ref':value.get('source_ref') or {},
                    'source_revision':source_revision,'created_at':now,'updated_at':now,'history':[]})
            elif action in {'correct_memory','disable_memory'}:
                memory=next((m for m in state['memories'] if m['memory_id']==value.get('memory_id')),None)
                if not memory: raise ValueError('Memory not found')
                memory['history'].append({'text':memory['text'],'status':memory['status'],'changed_at':now})
                if action=='correct_memory':
                    text=str(value.get('text') or '').strip()
                    if not text or len(text)>2000: raise ValueError('Invalid memory correction')
                    memory.update(text=text,status='active')
                else: memory['status']='disabled'
                memory['updated_at']=now
            elif action=='feedback_consent': state['feedback_consent']=value.get('enabled') is True
            else: raise ValueError('Unsupported companion command')
            state['revision']+=1; state['updated_at']=now; state['receipts'][request_id]=fingerprint
            raw.clear(); raw.update(state)
        self.repository.companion_state(user,resource,resource_type=resource_type,update=update)
        return self.read(user,resource,resource_type)

    def prompt(self,user,resource,resource_type='course'):
        state=self.read(user,resource,resource_type)
        context={'goal':state['goal'],'plan':state['plan'],
                 'memories':[m for m in state['memories'] if m['status']=='active'][-12:]}
        return json.dumps(context,ensure_ascii=False)


def teaching_decision(model,*,question,knowledge_refs,node_id,requested_action=''):
    """Choose ONE bounded action from exact current evidence; never write mastery."""
    nodes=[n for n in (model.get('knowledge_profile') or {}).get('nodes',[]) if n.get('knowledge_id') in knowledge_refs
           and knowledge_refs[n['knowledge_id']]==n.get('knowledge_revision_id')]
    evidence=[e for n in nodes for e in n.get('evidence',[])]
    current_ids={n['knowledge_id'] for n in nodes}
    signals=[s for s in model.get('mistake_signals',[]) if s.get('status','confirmed')=='confirmed' and set(s.get('concept_ids') or []) & current_ids]
    action='explain'; form='brief'; uncertainty='insufficient_evidence'
    if requested_action in {'explain','contrast','step','verify'}: action=requested_action
    elif any(t in question.lower() for t in ['举例','例子','example']): form='example'
    elif any(t in question.lower() for t in ['带我','一步','step by step','next step']): action='step'
    elif signals: action='contrast' if signals[0].get('category') in {'concept_gap','boundary_confusion'} else 'step'
    elif evidence and evidence[-1].get('outcome')=='passed' and evidence[-1].get('support')!='independent': action='verify'
    if evidence: uncertainty='bounded_evidence'
    return {'schema_version':'teaching_decision_v1','decision_id':'td_'+digest([model.get('model_revision_id'),knowledge_refs,question,action]),
        'action':action,'format':form,'model_revision_id':model.get('model_revision_id'), 'node_id':node_id,
        'knowledge_revision_refs':knowledge_refs,'evidence_refs':evidence,'uncertainty':uncertainty,
        'mastery_write':False,'requires_qualified_question':action=='verify',
        'instruction':{'explain':'直接解释当前问题，短答优先；例子注明假设。未知错因不要确诊。',
                       'contrast':'用关键条件不同的一组对比例子辨析，请学生说明区别，保留待核实判断。',
                       'step':'保留正确步骤，只给下一步最小提示并等待学生回应；不默认展开全部答案。',
                       'verify':'邀请学生做未展示答案的合格新题或独立解释；缺少合格检查材料则明确待验证，不能宣称掌握。'}[action]}
