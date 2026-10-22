<template>
  <button v-if="!preview" type="button" data-testid="companion-plan-open" class="plan-entry" @click="show">{{ c('学习主线与学伴设置','Learning plan & companion') }}</button>
  <Teleport to="body"><div v-if="open && !preview" class="plan-backdrop" @click.self="open=false"><section data-testid="companion-plan-dialog" class="plan-dialog" role="dialog" aria-modal="true" :aria-label="c('我的学习主线','My learning plan')" @keydown.esc="open=false">
    <header><h2>{{ c('我的学习主线','My learning plan') }}</h2><button type="button" @click="open=false">{{ c('关闭','Close') }}</button></header>
    <p v-if="error" role="alert">{{ error }} <button type="button" @click="load">{{ c('重新读取','Reload') }}</button></p>
    <p v-if="loading" role="status">{{ c('正在读取本人设置…','Loading your settings…') }}</p>
    <section class="plan-mode"><label>{{ c('学伴主动程度','Companion initiative') }}<select :value="preferences.ready ? preferences.mode : ''" :disabled="!preferences.ready || preferences.busy" @change="changeMode"><option disabled value="">{{ c('正在读取','Loading') }}</option><option value="gentle">{{ c('轻主动：在自然停顿时建议','Gentle suggestions at natural pauses') }}</option><option value="on_request">{{ c('仅在我提问时回应','Respond only when I ask') }}</option></select></label><p>{{ c('只影响主动建议，不删除计划、记忆或已发起的任务。','This changes suggestions, keeping your plan, memory and requested tasks.') }}</p></section>
    <template v-if="state">
      <form @submit.prevent="run('save_goal',{text:goalText,purpose,baseline,deadline:deadline||null,minutes_per_week:minutes||null})">
        <h3>{{ c('总体目标','Overall goal') }}</h3>
        <label>{{ c('你希望学到什么程度？','What do you want to achieve?') }}<textarea v-model="goalText" maxlength="2000" rows="3" required /></label>
        <div class="plan-fields"><label>{{ c('主要场景','Main purpose') }}<select v-model="purpose"><option value="systematic">{{c('系统理解','Understanding')}}</option><option value="exam">{{c('准备考试','Exam preparation')}}</option><option value="project">{{c('完成项目','Project')}}</option><option value="mixed">{{c('混合目标','Mixed goals')}}</option></select></label><label>{{c('期限（可留空）','Deadline (optional)')}}<input v-model="deadline" type="date" /></label><label>{{c('每周可用分钟（可留空）','Minutes per week (optional)')}}<input v-model.number="minutes" type="number" min="1" max="10080" /></label></div>
        <label>{{c('目前基础（不确定可留空）','Starting point (leave blank if unsure)')}}<input v-model="baseline" maxlength="1000" /></label>
        <button type="submit" :disabled="busy || !goalText.trim()">{{c('保存总体目标','Save goal')}}</button>
      </form>
      <section><h3>{{c('阶段计划','Learning stages')}}</h3><p>{{c('临时提问不会改变总体目标；阅读或接受提示不等于独立掌握。','A temporary question keeps your goal. Reading or using hints does not prove independent mastery.')}}</p><button type="button" :disabled="busy || !state.goal" @click="run('propose_plan')">{{c('预览新的学习安排','Preview a revised plan')}}</button>
        <div v-if="state.proposal" class="plan-proposal"><ol><li v-for="step in state.proposal.steps" :key="step.step_id">{{step.title}} · {{stepIntent(step)}}</li></ol><button :disabled="busy" @click="run('adopt_plan')">{{c('采用这个安排','Adopt this plan')}}</button><button :disabled="busy" @click="run('reject_plan')">{{c('保留原安排','Keep the current plan')}}</button></div>
        <p v-if="state.plan?.status==='needs_review' || state.plan && state.plan.source_revision!==state.source_revision" role="status">{{c('目标或来源已变，请核对未来安排。历史记录保留。','Your goal or source changed. Review future steps; history is preserved.')}}</p>
        <ol v-if="state.plan"><li v-for="step in state.plan.steps" :key="step.step_id"><strong>{{step.title}}</strong> · {{stepIntent(step)}} <span>{{progress(step.node_id)}}</span><button :disabled="busy" @click="run(step.decision==='deferred'?'resume_step':'defer_step',{step_id:step.step_id})">{{step.decision==='deferred'?c('恢复','Resume'):c('稍后学习','Defer')}}</button><button type="button" @click="emit('navigate',step.node_id);open=false">{{c('到这里学习','Open this step')}}</button></li></ol>
        <p v-else>{{c('保存目标后预览安排，确认后作为持续主线。','Save a goal, preview the stages, then adopt your ongoing plan.')}}</p>
      </section>
      <section><h3>{{c('学伴记住的约定与偏好','Remembered agreements & preferences')}}</h3><div class="memory-compose"><input v-model="memoryText" maxlength="2000" :aria-label="c('希望学伴记住什么','What should your companion remember?')" /><button :disabled="busy || !memoryText.trim()" @click="remember">{{c('记住这个约定','Remember this')}}</button></div>
        <article v-for="memory in state.memories" :key="memory.memory_id"><p>{{memory.text}}</p><small>{{memory.origin}} · {{memory.updated_at}}</small><template v-if="memory.status==='active'"><button :disabled="busy" @click="editingMemory=memory.memory_id;correction=memory.text">{{c('纠正','Correct')}}</button><button :disabled="busy" @click="run('disable_memory',{memory_id:memory.memory_id})">{{c('停止使用','Stop using')}}</button></template><span v-else>{{c('已停用','Disabled')}}</span><div v-if="editingMemory===memory.memory_id"><input v-model="correction" maxlength="2000" :aria-label="c('纠正后的内容','Corrected memory')" /><button :disabled="busy || !correction.trim()" @click="correctMemory(memory.memory_id)">{{c('保存纠正','Save correction')}}</button></div></article>
      </section>
      <section v-if="courseId"><label><input type="checkbox" :checked="state.feedback_consent" :disabled="busy" @change="run('feedback_consent',{enabled:($event.target as HTMLInputElement).checked})" />{{c('允许将本课程目标和帮助效果摘要用于教师反馈（不含私人对话、笔记原文）','Allow course goals and help-outcome summaries for teacher feedback (excluding private notes and conversations)')}}</label><button :disabled="busy" @click="restoreReminders">{{c('恢复我忽略的本课提醒','Restore dismissed reminders for this course')}}</button></section>
    </template>
  </section></div></Teleport>
</template>
<script setup lang="ts">
import { ref, onBeforeUnmount, watch } from 'vue'
import http from '../utils/http'
import { activeLocale } from '../shared/i18n'
import { useCompanionPreferencesStore } from '../stores/companionPreferences'
import { createUuid } from '../utils/client-id'
const props=defineProps<{courseId?:string;materialId?:string;preview?:boolean}>()
const emit=defineEmits<{navigate:[nodeId:string]}>()
const c=(zh:string,en:string)=>activeLocale.value==='en'?en:zh
const preferences=useCompanionPreferencesStore()
const open=ref(false),loading=ref(false),busy=ref(false),error=ref(''),state=ref<any>(null)
const goalText=ref(''),purpose=ref('systematic'),baseline=ref(''),deadline=ref(''),minutes=ref<number|''>('')
const memoryText=ref(''),editingMemory=ref(''),correction=ref('')
let epoch=0
const url=()=>props.materialId?`/api/study/materials/${encodeURIComponent(props.materialId)}/companion`:`/api/courses/${encodeURIComponent(props.courseId||'')}/learning-records/companion`
watch(()=>[props.courseId,props.materialId,props.preview],()=>{epoch++;state.value=null;open.value=false})
onBeforeUnmount(()=>epoch++)
async function load(){if(props.preview)return;const token=++epoch;loading.value=true;error.value='';try{const [response]=await Promise.all([http.get(url()),preferences.load()]);if(token!==epoch)return;state.value=response.data;const g=state.value?.goal;goalText.value=g?.text||'';purpose.value=g?.purpose||'systematic';baseline.value=g?.baseline||'';deadline.value=g?.deadline||'';minutes.value=g?.minutes_per_week||''}catch{if(token===epoch)error.value=c('读取失败，输入保留。','Could not load. Your input is kept.')}finally{if(token===epoch)loading.value=false}}
async function show(){open.value=true;await load()}
async function changeMode(event:Event){try{await preferences.change((event.target as HTMLSelectElement).value as 'gentle'|'on_request')}catch{error.value=c('设置未保存，请重读后再试。','Setting was not saved. Reload and try again.')}}
async function run(action:string,value:Record<string,unknown>={}){if(busy.value||!state.value||props.preview)return;const token=epoch;busy.value=true;error.value='';try{const {data}=await http.post(url(),{action,value,expected_revision:state.value.revision,request_id:createUuid()});if(token===epoch)state.value=data}catch(e:any){if(token===epoch)error.value=e?.response?.status===409?c('状态已变化，未覆盖你的输入，请重新读取。','State changed. Your input is kept; reload before retrying.'):c('操作未完成，请重试。','Action did not complete. Please retry.')}finally{if(token===epoch)busy.value=false}}
async function remember(){await run('remember',{text:memoryText.value,kind:'agreement'});if(!error.value)memoryText.value=''}
async function correctMemory(id:string){await run('correct_memory',{memory_id:id,text:correction.value});if(!error.value)editingMemory.value=''}
function progress(id:string){const p=state.value?.progress?.find((x:any)=>x.node_id===id);return p?`${c('阅读','Reading')}: ${p.reading_status} · ${c('验证','Verification')}: ${p.mastery_status}`:c('尚无正式学习证据','No formal learning evidence')}
function stepIntent(step:any){return activeLocale.value==='en'?({exam:'Distinguish key ideas and check independently',project:'Understand and apply',mixed:'Understand and check application',systematic:'Understand, try and self-check'} as Record<string,string>)[state.value?.goal?.purpose||'systematic']:step.intent}
async function restoreReminders(){if(!props.courseId)return;try{const base=url()+'/suppressions';const {data}=await http.get(base);await Promise.all(data.map((s:any)=>http.post(base,{key:s.suppression_key,mode:'restore'})))}catch{error.value=c('恢复提醒失败，请重试。','Could not restore reminders. Try again.')}}
</script>
<style scoped>
.plan-entry{font:inherit;font-size:15px;border:1px solid #ddd5ee;border-radius:8px;padding:7px 11px;color:#655184;background:#f8f5fc;cursor:pointer}.plan-backdrop{position:fixed;inset:0;z-index:120;display:grid;place-items:center;background:#231c3a55;padding:24px}.plan-dialog{background:#fff;color:#354052;border-radius:16px;max-width:860px;width:100%;max-height:90vh;overflow:auto;padding:24px;font-size:15px;line-height:1.6}.plan-dialog header{display:flex;align-items:center;justify-content:space-between}.plan-dialog h2{font-size:21px}.plan-dialog section,.plan-dialog form{border-top:1px solid #e7e1ef;margin-top:20px;padding-top:16px}.plan-dialog label{display:grid;gap:6px;margin:10px 0}.plan-fields{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.plan-dialog input,.plan-dialog select,.plan-dialog textarea{font:inherit;min-width:0;border:1px solid #d7d0e4;border-radius:7px;padding:8px}.plan-dialog button{font:inherit;border:1px solid #dbd3e9;border-radius:7px;padding:5px 9px;margin:4px;background:#f7f3fc;color:#614d84;cursor:pointer}.plan-dialog li,.plan-dialog article{margin:10px 0;padding:10px;background:#faf8fd}.plan-dialog button:disabled{opacity:.5;cursor:default}.plan-dialog :focus-visible{outline:2px solid #8e72bd;outline-offset:2px}.memory-compose{display:flex;gap:8px}.memory-compose input{flex:1}.plan-proposal{border:1px solid #cfc0e6;border-radius:8px;padding:12px}
</style>
