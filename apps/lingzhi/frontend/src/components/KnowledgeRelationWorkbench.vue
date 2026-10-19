<template>
  <details class="relation-workbench" data-testid="knowledge-relation-workbench">
    <summary>{{ t(run.adopted ? 'knowledgeFirst.adoptedRelationRecord' : 'knowledgeFirst.relationCandidates') }} · {{ t('knowledgeFirst.relationBatchSummary').replace('{done}',String(done)).replace('{total}',String(pipeline.batches.length)) }}</summary>
    <p>{{ t('knowledgeFirst.relationSelectHint') }}</p>
    <button v-if="canEdit && !run.adopted && pending && ['failed','cancelled','paused'].includes(run.status)" :disabled="disabled" type="button" data-testid="continue-relation-batches" @click="emit('continue')">{{ t('knowledgeFirst.continueRelationBatches') }}</button>
    <details v-for="(batch,index) in pipeline.batches" :key="batch.id" class="relation-batch">
      <summary>{{ t('knowledgeFirst.relationBatch').replace('{number}',String(Number(index)+1)) }} · {{ t(batch.status === 'completed' ? 'knowledgeFirst.batchSaved' : 'knowledgeFirst.batchPending') }}</summary>
      <p v-if="batch.status !== 'completed'">{{ t('knowledgeFirst.relationBatchPending') }}</p>
      <p v-else-if="!batch.result?.relations?.length">{{ t('knowledgeFirst.noProposedRelations') }}</p>
      <article v-for="edge in batch.result?.relations || []" :key="edge.id" class="relation-card">
        <p v-if="run.adopted">{{ t(run.rejected_ids?.includes(edge.id) ? 'knowledgeFirst.relationSkipped' : run.accepted_ids?.includes(edge.id) ? 'knowledgeFirst.relationSelected' : 'knowledgeFirst.relationRecordOnly') }}</p>
        <div class="relation-direction"><button type="button" @click="navigate(edge.source_id)">{{ name(edge.source_id) }}</button><span> → </span><button type="button" @click="navigate(edge.target_id)">{{ name(edge.target_id) }}</button><strong> · {{ t(`knowledgeFirst.relationTypes.${edge.type}`,edge.type) }}</strong></div>
        <p v-if="edge.cross_lesson" class="cross-lecture">{{ t('knowledgeFirst.crossLessonLinks') }}</p>
        <p>{{ edge.reason }}</p><ul v-if="edge.conditions?.length"><li v-for="condition in edge.conditions" :key="condition">{{ condition }}</li></ul>
        <KnowledgeRelationEvidence :edge="edge" />
      </article>
      <details v-if="batch.result?.decisions?.length"><summary>{{ t('knowledgeFirst.relationComparisonRecord') }}</summary><p v-for="row in batch.result.decisions" :key="row.focus_key">{{ pipeline.catalog.find((p:any)=>p.key === row.focus_key)?.name }} · {{ row.reason }}</p></details>
      <p v-for="(gap,i) in batch.result?.gaps || []" :key="i">{{ gap }}</p>
      <button v-if="canEdit && !run.adopted && !['pending','running'].includes(run.status)" type="button" :disabled="disabled" @click="emit('retry',batch.id)">{{ t('knowledgeFirst.retryRelationBatch') }}</button>
    </details>
  </details>
</template>
<script setup lang="ts">
import {computed} from 'vue'
import {t} from '../shared/i18n'
import KnowledgeRelationEvidence from './KnowledgeRelationEvidence.vue'
const props = defineProps<{run:any;canEdit:boolean;disabled:boolean}>()
const emit = defineEmits<{continue:[];retry:[batchId:string];navigate:[target:{lesson_id:string;knowledge_id:string}]}>()
const pipeline = computed(()=>props.run.pipeline)
const done = computed(()=>pipeline.value.batches.filter((b:any)=>b.status === 'completed').length)
const pending = computed(()=>done.value < pipeline.value.batches.length)
const name = (id:string)=>pipeline.value.catalog.find((p:any)=>p.knowledge_id === id)?.name || id
function navigate(id:string){const p=pipeline.value.catalog.find((p:any)=>p.knowledge_id === id);if(p)emit('navigate',{lesson_id:p.lesson_ids.includes(props.run.lesson_id)?props.run.lesson_id:p.lesson_ids[0],knowledge_id:id})}
</script>
<style scoped>
.relation-workbench{margin:18px 0;padding:18px 20px;border:1px solid #d9d2ec;border-radius:12px;background:#f8f6fd;color:#52436b;font-size:15px;line-height:1.8;overflow-wrap:anywhere}.relation-workbench summary{font-weight:600;cursor:pointer}.relation-batch{margin:16px 0 0;padding:15px;background:#fff;border:1px solid #e4def0;border-radius:10px}.relation-card{margin:14px 0;padding:14px;border:1px solid #e7e0f1;border-radius:9px}.relation-card p{margin:8px 0}.relation-workbench button{font:inherit;border:1px solid #d9cfe8;border-radius:7px;padding:7px 10px;background:#fff;color:#6a5289;cursor:pointer}.relation-workbench button:disabled{opacity:.5;cursor:not-allowed}.relation-direction button{border:0;padding:2px;text-decoration:underline;text-underline-offset:4px}.cross-lecture{color:#766397}.relation-workbench button:focus-visible,.relation-workbench summary:focus-visible{outline:3px solid #b3a1d1;outline-offset:3px}
</style>
