<template>
 <section class="teacher-concerns" :aria-label="c('班级学习关注点','Class learning concerns')">
  <header><h3>{{c('班级学习关注点','Class learning concerns')}}</h3><button :disabled="busy" @click="load">{{c('刷新','Refresh')}}</button></header>
  <div class="concern-filters"><label>{{c('发布版本','Published version')}}<select v-model="release" @change="load"><option value="">{{c('当前版本','Current version')}}</option><option v-for="id in data?.available_releases||[]" :key="id" :value="id">{{id}}</option></select></label><label>{{c('起始日期','From')}}<input v-model="since" type="date" /></label><label>{{c('截止日期','To')}}<input v-model="until" type="date" /></label><button :disabled="busy" @click="load">{{c('按范围查看','Apply filters')}}</button></div>
  <p v-if="error" role="alert">{{error}}</p><p v-if="busy" role="status">{{c('正在处理…','Working…')}}</p>
  <template v-if="data"><p>{{c('授权名单','Authorized roster')}} {{data.roster_count}} · {{c('有正式证据','With formal evidence')}} {{data.evidence_students}} · {{c('尚无数据','No data')}} {{data.no_data_students}}</p><small>{{c('只比较同一发布和知识修订；人数口径可重叠，不代表掌握概率。','Only matching release and knowledge revisions are compared. Counts can overlap; they are not mastery probabilities.')}} {{data.release_id}}</small>
   <p v-if="data.unattributed_attempts">{{c('尚不能精确归因的作答','Attempts awaiting exact attribution')}}: {{data.unattributed_attempts}}</p>
   <p v-if="!data.topics.length">{{c('当前范围没有可精确归因的知识点证据。','No precisely attributed knowledge evidence in this scope.')}}</p>
   <article v-for="topic in data.topics" :key="topic.topic_id"><h4>{{topic.title}}</h4><p>{{c('重复独立困难','Repeated independent difficulty')}} {{topic.repeated_failure_students}} · {{c('使用帮助','Used assistance')}} {{topic.assisted_students}} · {{c('独立通过','Independent passes')}} {{topic.independent_pass_students}} · {{c('待判断','Uncertain')}} {{topic.unknown_students}} · {{c('尚无数据','No data')}} {{topic.no_data_students}}</p><details><summary>{{c('查看授权依据','View authorized evidence')}} ({{topic.evidence.length}})</summary><ul><li v-for="entry in topic.evidence" :key="entry.actor_id+entry.attempt_id">{{entry.actor_id}} · {{entry.outcome}} · {{entry.support}} · {{entry.observed_at}} · {{entry.receipt_id}}</li></ul></details><button data-testid="teacher-concern-suggest" :disabled="busy || !topic.node_id" @click="suggest(topic)">{{c('生成补讲或练习建议，供我审阅','Generate a teaching suggestion for review')}}</button><small v-if="!topic.node_id">{{c('缺少讲次关联，先核对来源。','Verify the missing lesson binding first.')}}</small></article>
   <details><summary>{{c('学生明确分享的目标','Goals explicitly shared by students')}} ({{data.shared_goals.length}})</summary><p v-for="goal in data.shared_goals" :key="goal.actor_id">{{goal.actor_id}} · {{goal.goal?.purpose}} · {{goal.goal?.text}}</p></details>
  </template>
 </section>
</template>
<script setup lang="ts">
import {ref,onMounted,onBeforeUnmount,watch} from 'vue'
import {activeLocale} from '../shared/i18n'
import http,{teacherRequestConfig} from '../utils/http'
import {useCourseEvolutionStore} from '../stores/courseEvolution'
import {useCourseStore} from '../stores/course'
import {createUuid} from '../utils/client-id'
const props=defineProps<{courseId:string}>(),emit=defineEmits<{openPlan:[payload:{planId:string;sectionId:string}]}>()
const c=(zh:string,en:string)=>activeLocale.value==='en'?en:zh
const data=ref<any>(null),busy=ref(false),error=ref(''),release=ref(''),since=ref(''),until=ref('')
const evolution=useCourseEvolutionStore(),course=useCourseStore();let epoch=0
const requests=new Map<string,string>()
async function load(){const token=++epoch;busy.value=true;error.value='';try{const response=await http.get(`/api/teacher/courses/${encodeURIComponent(props.courseId)}/exchange/learning-analysis`,teacherRequestConfig({params:{release_id:release.value,since:since.value?since.value+'T00:00:00Z':'',until:until.value?until.value+'T23:59:59Z':''}}));if(token===epoch)data.value=response.data}catch{if(token===epoch)error.value=c('读取失败，请重试。','Could not load. Try again.')}finally{if(token===epoch)busy.value=false}}
async function suggest(topic:any){if(busy.value||!topic.node_id)return;const token=epoch,snapshot=data.value.snapshot_id;busy.value=true;error.value='';try{await evolution.load(props.courseId);if(token!==epoch)return;const previous=new Set(evolution.plans.map(p=>p.change_set_id));const key=topic.topic_id+snapshot;const requestId=requests.get(key)||createUuid();requests.set(key,requestId)
  await evolution.createPlan({sectionId:topic.node_id,scopeSelection:'current_section',requestId,expectedDocumentRevision:course.currentDocumentRevision,
   instruction:c('根据以下已授权正式作答证据，为当前讲生成一项可审阅的补讲、对比例子或练习建议。不要改变共同教学要求，不宣称已经改善。','Using the following authorized formal-attempt evidence, propose one reviewable explanation, contrast or exercise for this lesson. Preserve common requirements; do not claim improved learning.')+'\n'+JSON.stringify({snapshot_id:snapshot,release_id:data.value.release_id,knowledge_id:topic.knowledge_id,knowledge_revision_id:topic.knowledge_revision_id,roster_count:data.value.roster_count,concern:topic})})
  if(token!==epoch)return;const plan=evolution.plans.find(p=>!previous.has(p.change_set_id));if(!plan)throw Error('No reviewable plan returned');emit('openPlan',{planId:plan.change_set_id,sectionId:topic.node_id})
 }catch(e:any){if(token===epoch)error.value=e?.response?.data?.detail?.message||c('建议尚未生成，保留当前依据，可重试。','Suggestion unavailable. Evidence is kept; retry.')}finally{if(token===epoch)busy.value=false}}
watch(()=>props.courseId,()=>{data.value=null;requests.clear();void load()});onMounted(load);onBeforeUnmount(()=>epoch++)
</script>
<style scoped>
.teacher-concerns{margin:16px 0;border:1px solid #e1d9eb;border-radius:12px;padding:16px;font-size:15px;line-height:1.6}.teacher-concerns header,.concern-filters{display:flex;gap:12px;align-items:center;flex-wrap:wrap}.teacher-concerns header h3{margin-right:auto}.concern-filters label{display:grid;gap:4px}.teacher-concerns article{margin:14px 0;padding:12px;border-left:3px solid #ad94cc;background:#faf8fd}.teacher-concerns button,.teacher-concerns select,.teacher-concerns input{font:inherit;border:1px solid #d9d0e4;border-radius:7px;padding:6px 9px;background:white;color:inherit}.teacher-concerns button{cursor:pointer}.teacher-concerns button:disabled{opacity:.5;cursor:default}.teacher-concerns :focus-visible{outline:2px solid #8e72bd;outline-offset:2px}.teacher-concerns ul{overflow-wrap:anywhere}
</style>
