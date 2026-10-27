<template>
  <section class="check-journey" :aria-label="t('knowledgeCheckJourney.title')">
    <h4>{{ t('knowledgeCheckJourney.title') }}</h4>
    <p v-if="preview">{{ t('knowledgeCheckJourney.preview') }}</p>
    <p v-else-if="loading" role="status">{{ t('knowledgeCheckJourney.loading') }}</p>
    <template v-else>
      <p v-if="!rows.length">{{ t('knowledgeCheckJourney.empty') }}</p>
      <article v-for="row in rows" :key="row.criterion_id" class="check-target">
        <MathText tag="strong" :content="row.name" />
        <p>{{ status(row.measurement) }} · {{ t('knowledgeCheckJourney.independent') }} {{ row.measurement.independent_successes }}</p>
        <button v-if="!attempt && row.has_next" data-testid="check-start" :disabled="busy" @click="start(row)">{{ t('knowledgeCheckJourney.start') }}</button>
        <p v-else-if="!attempt && !row.has_next">{{ t('knowledgeCheckJourney.noNext') }}</p>
      </article>
      <div v-if="attempt && task" class="check-task">
        <MarkdownRenderer :content="task.question.prompt" />
        <template v-if="attempt.status === 'in_progress'">
          <PracticeAnswerRenderer v-if="typedMode" v-model="typedAnswer" :contract="task.question.input_contract" :options="task.question.options" :question-type="task.question.question_type" :disabled="busy" @focusout="saveDraft" />
          <template v-else><label :for="uid">{{ t('knowledgeCheckJourney.answer') }}</label>
          <textarea :id="uid" v-model="answer" rows="5" maxlength="20000" :disabled="busy" @blur="saveDraft" /></template>
          <div class="check-actions"><button data-testid="check-submit" :disabled="busy || !hasAnswer" @click="submit">{{ t('knowledgeCheckJourney.submit') }}</button><button data-testid="check-hint" :disabled="busy" @click="hint">{{ t('knowledgeCheckJourney.hint') }}</button></div>
        </template>
        <MarkdownRenderer v-if="help" :content="help" />
        <div v-if="result" class="check-result" role="status">
          <p>{{ result.status === 'pending_review' ? t('knowledgeCheckJourney.pending') : result.passed && result.support_level > 0 ? t('knowledgeCheckJourney.assisted') : result.passed ? t('knowledgeCheckJourney.passed') : t('knowledgeCheckJourney.retry') }}</p>
          <ul><li v-for="item in result.checkpoint_feedback" :key="item.checkpoint_id"><MathText tag="strong" :content="item.label" /> · {{ t(item.met ? 'knowledgeCheckJourney.met' : 'knowledgeCheckJourney.notMet') }}<MarkdownRenderer :content="item.feedback" /></li></ul>
          <div class="check-actions"><button v-if="attempt.status === 'graded'" :disabled="busy" @click="hint">{{ t('knowledgeCheckJourney.helpRetry') }}</button><button v-if="rows.find(r => r.criterion_id === selected?.criterion_id)?.has_next" data-testid="check-next" :disabled="busy" @click="start(selected)">{{ t('knowledgeCheckJourney.next') }}</button></div>
        </div>
      </div>
      <p v-if="notice" role="status">{{ notice }}</p>
      <p v-if="error" role="alert">{{ error }}</p>
    </template>
  </section>
</template>
<script setup lang="ts">
import { ref,computed,watch,onBeforeUnmount,useId } from 'vue'
import http from '../utils/http'
import { createUuid } from '../utils/client-id'
import { t } from '../shared/i18n'
import MarkdownRenderer from './MarkdownRenderer.vue'
import MathText from './MathText.vue'
import PracticeAnswerRenderer from './PracticeAnswerRenderer.vue'
const props=defineProps<{courseId:string;knowledgeId:string;knowledgeRevision:string;preview?:boolean}>()
const emit=defineEmits<{graded:[]}>()
const uid=useId(),rows=ref<any[]>([]),attempt=ref<any>(null),task=ref<any>(null),selected=ref<any>(null),result=ref<any>(null)
const loading=ref(false),busy=ref(false),answer=ref(''),help=ref(''),notice=ref(''),error=ref('')
const typedAnswer=ref<Record<string,any>>({})
const typedMode=computed(()=>['choice','numeric_unit'].includes(task.value?.question?.input_contract?.mode))
const hasAnswer=computed(()=>{
 if(!typedMode.value)return Boolean(answer.value.trim())
 if(task.value.question.input_contract.mode==='choice')return Boolean(typedAnswer.value.selected_option_id)
 const fields=task.value.question.input_contract.fields || [{field_id:'value',required:true}]
 return fields.filter((f:any)=>f.required).every((f:any)=>typedAnswer.value[f.field_id]!==undefined && typedAnswer.value[f.field_id]!==null && String(typedAnswer.value[f.field_id]).trim()!=='')
})
const answerPayload=()=>typedMode.value?{...typedAnswer.value}:{text:answer.value}
let epoch=0,disposed=false
let draftSaving:Promise<void>|null=null
const valid=(token:number)=>!disposed && token===epoch && !props.preview
const root=()=>`/api/courses/${encodeURIComponent(props.courseId)}`
function status(m:any){return t(`knowledgeCheckJourney.${m.status === 'unassessed' ? 'unassessed' : m.status === 'check_supported' ? 'supported' : 'moreEvidence'}`)}
async function load(token:number){const {data}=await http.get(`${root()}/learning-records/knowledge-checks`,{params:{knowledge_id:props.knowledgeId,knowledge_revision:props.knowledgeRevision}});if(valid(token)){rows.value=data.criteria || [];const saved=data.last_check
 if(!attempt.value && saved && rows.value.some(r=>r.criterion_id===saved.criterion_id)){attempt.value=saved.attempt;task.value=saved.task;result.value=saved.result;selected.value=rows.value.find(r=>r.criterion_id===saved.criterion_id);answer.value=saved.attempt.answer_payload?.text || '';typedAnswer.value={...(saved.attempt.answer_payload || {})}}
 }}
watch(()=>[props.courseId,props.knowledgeId,props.knowledgeRevision,props.preview],async()=>{
 const token=++epoch;rows.value=[];attempt.value=null;task.value=null;selected.value=null;result.value=null;answer.value='';help.value='';error.value='';notice.value='';busy.value=false;loading.value=false
 typedAnswer.value={}
 if(props.preview || !props.courseId)return
 loading.value=true;try{await load(token)}catch{if(valid(token))error.value=t('knowledgeCheckJourney.failed')}finally{if(valid(token))loading.value=false}
},{immediate:true})
async function start(row:any){if(busy.value || !row || props.preview)return;const token=epoch;busy.value=true;error.value='';notice.value=''
 try{const {data}=await http.post(`${root()}/learning-records/knowledge-checks/target`,{knowledge_id:props.knowledgeId,knowledge_revision:props.knowledgeRevision,criterion_id:row.criterion_id,criterion_revision:row.revision_id});if(!valid(token))return
  if(data.status!=='available'){notice.value=t('knowledgeCheckJourney.noNext');return}
  const a=await http.post(`${root()}/practice/attempts`,{task_revision_id:data.task_revision_id,resume:true});if(!valid(token))return
  task.value=data;attempt.value=a.data.attempt;selected.value=row;answer.value=attempt.value.answer_payload?.text || '';typedAnswer.value={...(attempt.value.answer_payload || {})};result.value=null;help.value=''
 }catch{if(valid(token))error.value=t('knowledgeCheckJourney.failed')}finally{if(valid(token))busy.value=false}}
function saveDraft(){if(busy.value || !attempt.value || attempt.value.status!=='in_progress' || props.preview)return; if(draftSaving)return draftSaving
 const token=epoch, url=`${root()}/practice/attempts/${attempt.value.attempt_id}/draft`, body={expected_revision:attempt.value.revision,answer_payload:answerPayload(),active_seconds:0}
 const saving=(async()=>{try{const {data}=await http.patch(url,body);if(valid(token))attempt.value=data.attempt}catch{if(valid(token))error.value=t('knowledgeCheckJourney.failed')}})()
 draftSaving=saving;void saving.finally(()=>{if(draftSaving===saving)draftSaving=null});return saving}

async function submit(){if(busy.value || !hasAnswer.value || props.preview)return;const token=epoch;busy.value=true;error.value=''
 try{await draftSaving;if(!valid(token))return;const {data}=await http.post(`${root()}/practice/attempts/${attempt.value.attempt_id}/submit`,{expected_revision:attempt.value.revision,request_id:createUuid(),answer_payload:answerPayload(),active_seconds:0});if(!valid(token))return
  attempt.value=data.attempt;result.value=data.result;emit('graded');await load(token)
 }catch{if(valid(token))error.value=t('knowledgeCheckJourney.failed')}finally{if(valid(token))busy.value=false}}
async function hint(){if(busy.value || !attempt.value || props.preview)return;const token=epoch;busy.value=true;error.value=''
 try{await draftSaving;if(!valid(token))return;let current=attempt.value
  if(current.status==='graded'){const a=await http.post(`${root()}/practice/attempts`,{task_revision_id:task.value.task_revision_id,resume:false});if(!valid(token))return;current=a.data.attempt;attempt.value=current;result.value=null}
  const {data}=await http.post(`${root()}/practice/attempts/${current.attempt_id}/hints/1`,{expected_revision:current.revision});if(!valid(token))return
  attempt.value=data.attempt;help.value=data.hint?.text || data.hint?.content || '';notice.value=t('knowledgeCheckJourney.helpUsed')
 }catch{if(valid(token))error.value=t('knowledgeCheckJourney.noHint')}finally{if(valid(token))busy.value=false}}
onBeforeUnmount(()=>{disposed=true;epoch++})
</script>
<style scoped>
.check-journey { margin:24px 0; padding:20px; border:1px solid #e0d8f2; border-radius:12px; background:#faf8ff; color:#3b3552; font-size:15px; line-height:1.7; }
h4 { margin:0 0 14px; font-size:18px; }.check-target { margin:12px 0; }.check-target p { color:#766b85; margin:6px 0; }
textarea { width:100%; box-sizing:border-box; resize:vertical; border:1px solid #d8d0e9; border-radius:9px; padding:12px; font:inherit; background:#fff; color:inherit; }
label { display:block; margin:12px 0 8px; }.check-actions { display:flex; flex-wrap:wrap; gap:10px; margin:12px 0; }
button { border:1px solid #d9cdec; border-radius:8px; padding:9px 14px; background:#fff; color:#62458e; font:inherit; cursor:pointer; }button:disabled { opacity:.5; cursor:default; }button:focus-visible,textarea:focus-visible { outline:2px solid #8b73c8; outline-offset:3px; }
.check-task { border-top:1px solid #e4ddef; padding-top:16px; margin-top:16px; }.check-result { margin-top:18px; }.check-result li { margin:12px 0; }[role=alert] { color:#a7434c; }
</style>
