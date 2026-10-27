<template>
  <section class="criterion-supply" :aria-label="t('criterionSupply.title')">
    <h5>{{ t('criterionSupply.title') }}</h5>
    <p v-if="loading" role="status">{{ t('criterionSupply.loading') }}</p>
    <template v-else-if="supply">
      <p>{{ t('criterionSupply.available') }} {{ supply.available_count }} · {{ t('criterionSupply.pending') }} {{ supply.pending_count }}</p>
      <p>{{ t('criterionSupply.hint') }}</p>
      <button data-testid="criterion-generate" :disabled="busy || running || !supply.can_generate" @click="generate">{{ t('criterionSupply.generate') }}</button>
      <p v-if="!supply.can_generate">{{ t('criterionSupply.noSource') }}</p>
    </template>
    <p v-if="running" role="status">{{ job?.message || t('criterionSupply.running') }}</p>
    <p v-else-if="job?.related && job.status === 'failed'" role="alert">{{ t('criterionSupply.failed') }}</p>
    <p v-if="error" role="alert">{{ error }}</p>
    <button v-if="error" :disabled="busy" @click="load">{{ t('criterionSupply.refresh') }}</button>
  </section>
</template>
<script setup lang="ts">
import { computed,ref,watch,onBeforeUnmount } from 'vue'
import http,{teacherRequestConfig} from '../utils/http'
import { createUuid } from '../utils/client-id'
import { t } from '../shared/i18n'
const props=defineProps<{courseId:string;knowledgeId:string;knowledgeRevision:string;criterionId:string;criterionRevision:string}>()
const supply=ref<any>(null),job=ref<any>(null),loading=ref(false),busy=ref(false),error=ref('')
const running=computed(()=>['queued','running'].includes(job.value?.status))
let epoch=0,disposed=false,timer:ReturnType<typeof setTimeout>|undefined
const root=()=>`/api/courses/${encodeURIComponent(props.courseId)}/question-bank`
async function load(){clearTimeout(timer);const token=++epoch;loading.value=!supply.value
 try{const config=teacherRequestConfig();config.params={knowledge_id:props.knowledgeId,knowledge_revision:props.knowledgeRevision,criterion_id:props.criterionId,criterion_revision:props.criterionRevision};const {data}=await http.get(`${root()}/criterion-supply`,config)
  if(disposed || token!==epoch)return;supply.value=data;job.value=data.job || null;error.value=''
  if(running.value)timer=setTimeout(load,3000)
 }catch{if(!disposed && token===epoch)error.value=t('criterionSupply.unavailable')}finally{if(!disposed && token===epoch)loading.value=false}}
async function generate(){if(busy.value || running.value || !supply.value?.can_generate)return;const token=epoch;busy.value=true;error.value=''
 try{const {data}=await http.post(`${root()}/rebuild`,{request_id:createUuid(),scope:'nodes',node_ids:[supply.value.node_id],
  knowledge_ids:[props.knowledgeId],knowledge_baseline_revision:supply.value.knowledge_baseline_revision,
  criterion_revision_refs:{[props.criterionId]:props.criterionRevision},mode:'incremental',resume_existing:false,retrieval_enabled:false},teacherRequestConfig())
  if(disposed || token!==epoch)return;job.value={...data,related:true};await load()
 }catch{if(!disposed && token===epoch)error.value=t('criterionSupply.unavailable')}finally{if(!disposed)busy.value=false}}
watch(()=>[props.courseId,props.knowledgeId,props.knowledgeRevision,props.criterionId,props.criterionRevision],()=>{supply.value=null;job.value=null;error.value='';void load()},{immediate:true})
onBeforeUnmount(()=>{disposed=true;epoch++;clearTimeout(timer)})
</script>
<style scoped>
.criterion-supply { margin-top:18px;padding:16px;border:1px solid #e2daef;border-radius:10px;background:#f8f5ff;font-size:15px;line-height:1.7; }
h5 { margin:0 0 8px;font-size:16px; }p { margin:7px 0; }button { padding:9px 14px;border:1px solid #d6c9e8;border-radius:8px;background:#fff;color:#62458e;font:inherit;cursor:pointer; }button:disabled { opacity:.5;cursor:default; }button:focus-visible { outline:2px solid #8670c8;outline-offset:3px; }[role=alert] {color:#a34d43}
</style>
