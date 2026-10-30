<template>
  <section class="knowledge-preparation" aria-live="polite">
    <p v-if="loading">{{t('unifiedGeneration.preparing','正在读取本讲知识候选…')}}</p>
    <p v-if="error" role="alert">{{error}}</p>
    <template v-if="candidate">
      <details>
        <summary>{{t('unifiedGeneration.baselinePreview','确认本讲知识基线')}} · {{points.length}} / {{readyCount}}</summary>
        <p>{{t('unifiedGeneration.baselineScope','采用本讲已有知识和就绪检查标准；待核对内容保留，关系不在本次确认范围内。')}}</p>
        <ul><li v-for="p in points" :key="p.knowledge_id"><strong>{{p.name}}</strong><MathText :content="p.statement || ''" /></li></ul>
        <p v-for="issue in candidate.tree.atomic_assessment?.issues || []" :key="issue.message">{{issue.message}}</p>
        <p v-for="c in pending" :key="c.criterion_id">{{c.name}} · {{t('unifiedGeneration.pendingStandard','待核对，暂不用于出题')}}</p>
        <a :href="`/course/${encodeURIComponent(courseId)}/workspace/build?stage=knowledge&lesson=${encodeURIComponent(lessonId)}`">{{t('unifiedGeneration.openKnowledge','查看知识树与检查标准')}}</a>
      </details>
      <label><input v-model="acknowledged" type="checkbox" :disabled="busy || blocked" />{{t('unifiedGeneration.confirmBaselineRead','已阅读本讲知识和待核对提示，确认采用就绪标准')}}</label>
      <p v-if="blocked">{{t('unifiedGeneration.baselineBlocked','候选未就绪或有任务运行，请先到知识树处理。')}}</p>
      <button type="button" data-testid="confirm-question-baseline" :disabled="!acknowledged || busy || blocked" @click="adopt">{{busy?t('unifiedGeneration.confirming','正在确认…'):t('unifiedGeneration.confirmBaseline','确认基线并返回出题')}}</button>
    </template>
    <p v-else-if="!loading && !error">{{t('unifiedGeneration.noCandidate','本讲尚无完成的知识候选，请先到知识树生成或核对。')}}</p>
  </section>
</template>
<script setup lang="ts">
import {computed,ref,watch}from 'vue'
import http,{teacherRequestConfig,teacherReadRequestConfig}from '@/utils/http'
import {t}from '@/shared/i18n'
import MathText from './MathText.vue'
const props=defineProps<{courseId:string;lessonId:string}>()
const emit=defineEmits<{adopted:[]}>()
const data=ref<any>(null),loading=ref(false),busy=ref(false),error=ref(''),acknowledged=ref(false)
const candidate=computed(()=>data.value?.candidates?.find((c:any)=>c.lesson_id===props.lessonId))
const points=computed<any[]>(()=>candidate.value?.tree?.knowledge_points||[])
const pending=computed<any[]>(()=>candidate.value?.tree?.mastery_criteria?.filter((c:any)=>c.readiness!=='ready')||[])
const readyCount=computed(()=>candidate.value?.tree?.mastery_criteria?.filter((c:any)=>c.readiness==='ready').length||0)
const blocked=computed(()=>!data.value?.can_edit || data.value?.blocking_job_ids?.length>0 || !readyCount.value || candidate.value?.tree?.atomic_assessment?.ready_for_adoption===false || candidate.value?.tree?.teaching_assessment?.ready_for_adoption===false || candidate.value?.tree?.relation_assessment?.ready_for_adoption===false)
let epoch=0
watch(()=>[props.courseId,props.lessonId],async()=>{
 const current=++epoch;data.value=null;acknowledged.value=false;error.value='';loading.value=true
 try{const r=await http.get(`/api/courses/${props.courseId}/knowledge-first`,teacherReadRequestConfig());if(current===epoch)data.value=r.data}
 catch(e:any){if(current===epoch)error.value=e?.response?.data?.detail?.message||t('unifiedGeneration.baselineReadFailed','知识候选读取失败，请到知识树重新读取。')}
 finally{if(current===epoch)loading.value=false}
},{immediate:true})
async function adopt(){
 if(!candidate.value || !acknowledged.value || blocked.value || busy.value)return
 const current=epoch;const c=candidate.value;busy.value=true;error.value=''
 try{await http.post(`/api/courses/${props.courseId}/knowledge-first/adopt/${encodeURIComponent(c.job_id)}`,{document_revision:data.value.document_revision,knowledge_revision:data.value.knowledge_revision,confirm_atomic_review:true,confirm_identity_changes:true,confirm_relations:true,selected_relation_ids:[]},teacherRequestConfig());if(current===epoch)emit('adopted')}
 catch(e:any){if(current===epoch){acknowledged.value=false;error.value=e?.response?.data?.detail?.message||String(e?.response?.data?.detail||t('unifiedGeneration.baselineConflict','确认失败，课程可能已变化，请到知识树刷新后核对。'))}}
 finally{if(current===epoch)busy.value=false}
}
</script>
<style scoped>
.knowledge-preparation{display:grid;gap:12px;font-size:15px;line-height:1.65;min-width:0}.knowledge-preparation p{margin:0;overflow-wrap:anywhere}.knowledge-preparation label{display:flex;align-items:flex-start;gap:8px}.knowledge-preparation input{margin-top:6px;flex:none}.knowledge-preparation details{border:1px solid #e4def2;padding:10px;border-radius:8px}.knowledge-preparation summary{cursor:pointer}.knowledge-preparation ul{max-height:260px;overflow:auto;padding-left:20px}.knowledge-preparation li{margin:10px 0}.knowledge-preparation strong{display:block}.knowledge-preparation button{font:inherit;padding:9px 12px;background:#f2efff;color:#51418b;border:1px solid #d8cfee;border-radius:8px;cursor:pointer}.knowledge-preparation button:disabled{opacity:.5;cursor:default}.knowledge-preparation :focus-visible{outline:3px solid #9dacec;outline-offset:2px}
</style>
