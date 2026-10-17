<template>
  <details class="atomic-workbench" open data-testid="knowledge-atomic-workbench">
    <summary>{{ t(run.adopted ? 'knowledgeFirst.atomicAdoptedRecord' : 'knowledgeFirst.atomicCandidates') }} · {{ t('knowledgeFirst.atomicSummary').replace('{items}', String(pipeline.items?.length || 0)).replace('{done}', String(done)).replace('{total}', String(pipeline.batches?.length || 0)) }}</summary>
    <p class="atomic-note">{{ t('knowledgeFirst.atomicReviewHint') }}</p>
    <details v-if="sourceIssues.length" class="atomic-issues" open data-testid="knowledge-source-issues"><summary>{{ t('knowledgeFirst.sourceIssuesTitle') }}</summary><div v-for="(issue,index) in sourceIssues" :key="index"><p>{{ issue.source_key }} · {{ issue.detail }}</p><blockquote>{{ issue.quote }}</blockquote></div></details>
    <button v-if="canEdit && !run.adopted && hasPending && ['failed','paused','cancelled'].includes(run.status)" type="button" :disabled="disabled" data-testid="continue-knowledge-batches" @click="emit('continue')">{{ t('knowledgeFirst.continueAtomic') }}</button>
    <details class="inventory-panel" open>
      <summary>{{ t('knowledgeFirst.inventoryTitle') }} · {{ pipeline.items?.length || 0 }}</summary>
      <p v-if="!pipeline.items?.length">{{ t('knowledgeFirst.inventoryPending') }}</p>
      <ol v-else class="inventory-list">
        <li v-for="item in pipeline.items" :key="item.key">
          <strong>{{ item.key }} · {{ item.name }}</strong><span class="inventory-kind">{{ t(`knowledgeFirst.inventoryKinds.${item.kind}`, item.kind) }}</span>
          <p>{{ item.claim }}</p>
          <details><summary>{{ t('knowledgeFirst.boundQuotation') }}</summary><blockquote v-for="(source, index) in item.sources" :key="index">{{ source.quote }}</blockquote></details>
        </li>
      </ol>
      <details v-if="pipeline.inventory_batches?.some((b:any) => b.source_coverage?.length)"><summary>{{ t('knowledgeFirst.inventorySourceCoverage') }}</summary>
        <p v-for="row in sourceCoverage" :key="row.source_key">{{ row.source_key }} → {{ row.item_keys?.join(' / ') || t(`knowledgeFirst.inventoryHandling.${row.handling}`, row.handling) }} · {{ row.reason }}</p>
      </details>
    </details>
    <details v-for="(batch, index) in pipeline.batches || []" :key="batch.id" class="atomic-batch" :open="index === 0">
      <summary>{{ t('knowledgeFirst.atomicBatch').replace('{number}', String(Number(index) + 1)) }} · {{ t(batch.status === 'completed' ? 'knowledgeFirst.batchSaved' : 'knowledgeFirst.batchPending') }}<span v-if="batch.report?.issues?.length"> · {{ batch.report.issues.length }} {{ t('knowledgeFirst.atomicIssues') }}</span></summary>
      <p v-if="batch.status !== 'completed'">{{ t('knowledgeFirst.batchNotReady') }}</p>
      <p v-else-if="!batch.report?.issues?.length" class="batch-checked">{{ t('knowledgeFirst.atomicChecksPassed') }}</p>
      <ul v-if="batch.report?.issues?.length" class="atomic-issues"><li v-for="(issue, i) in batch.report.issues" :key="i"><strong v-if="issueContext(issue, batch)">{{ issueContext(issue, batch) }} · </strong>{{ t(`knowledgeFirst.atomicIssueCodes.${issue.code}`, t('knowledgeFirst.atomicCheckFailed')) }}</li></ul>
      <details v-if="batch.report?.coverage?.length"><summary>{{ t('knowledgeFirst.inventoryMapping') }}</summary><p v-for="row in batch.report.coverage" :key="row.inventory_key">{{ row.inventory_key }} → {{ row.point_keys?.join(' / ') || t(`knowledgeFirst.inventoryHandling.${row.handling}`, row.handling) }} · {{ row.reason }}</p></details>
      <article v-for="point in batch.tree?.knowledge_points || []" :key="point.knowledge_id" class="atomic-point">
        <h4>{{ point.key ? `${point.key} · ` : '' }}{{ point.name }}</h4><MarkdownRenderer :content="point.statement" />
        <p v-if="point.meta_question"><strong>{{ t('knowledgeFirst.question') }}</strong> · {{ point.meta_question }}</p>
        <MarkdownRenderer v-if="point.meta_answer" :content="point.meta_answer" />
      </article>
      <button v-if="canEdit && !run.adopted && !['pending','running'].includes(run.status)" type="button" :disabled="disabled" @click="emit('retry', batch.id)">{{ t('knowledgeFirst.retryAtomicBatch') }}</button>
    </details>
  </details>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import { t } from '../shared/i18n'
import MarkdownRenderer from './MarkdownRenderer.vue'
const props = defineProps<{ run:any; canEdit:boolean; disabled:boolean }>()
const emit = defineEmits<{ continue:[]; retry:[batchId:string] }>()
const pipeline = computed(()=>props.run.pipeline)
const done = computed(()=>(pipeline.value.batches || []).filter((b:any)=>b.status==='completed').length)
const hasPending = computed(()=>!pipeline.value.batches?.length || [...(pipeline.value.inventory_batches || []), ...(pipeline.value.batches || [])].some((b:any)=>b.status !== 'completed'))
const sourceCoverage = computed(()=>(pipeline.value.inventory_batches || []).flatMap((b:any)=>b.source_coverage || []))
const sourceIssues = computed(()=>(pipeline.value.inventory_batches || []).flatMap((b:any)=>b.source_issues || []))
function issueContext(issue:any, batch:any) {
  return [...new Set([
    batch.tree?.knowledge_points?.find((p:any)=>p.key === issue.point_key)?.name,
    pipeline.value.items?.find((item:any)=>item.key === issue.inventory_key)?.name,
  ].filter(Boolean))].join(' / ')
}
</script>
<style scoped>
.atomic-workbench{margin:18px 0;padding:18px 20px;border:1px solid #ded4ed;border-radius:12px;background:#faf8fd;color:#514267;font-size:15px;line-height:1.75;overflow-wrap:anywhere}.atomic-workbench summary{cursor:pointer;font-weight:600}.atomic-note{color:#7c6b8d}.inventory-panel,.atomic-batch{margin-top:16px;padding:14px;border:1px solid #e6dff0;border-radius:9px;background:#fff}.inventory-list{max-height:300px;overflow:auto;padding-left:25px}.inventory-list>li{padding:10px 4px;border-bottom:1px solid #eee8f4}.inventory-list p{margin:5px 0}.inventory-kind{margin-left:12px;color:#8a769e}.inventory-list blockquote{margin:8px 0;padding:10px;border-left:3px solid #b4a0d0;background:#f7f4fa}.atomic-point{padding:12px 0;border-top:1px solid #eee7f5}.atomic-point h4{font-size:16px;margin:8px 0}.atomic-issues{padding:12px 12px 12px 32px;background:#fff5e9;border-radius:8px}.batch-checked{color:#52705e}.atomic-workbench button{font:inherit;padding:8px 12px;border:1px solid #d9cee8;border-radius:8px;background:#fff;color:#695184;cursor:pointer}.atomic-workbench button:disabled{opacity:.5;cursor:not-allowed}.atomic-workbench button:focus-visible,.atomic-workbench summary:focus-visible{outline:3px solid #b3a1d1;outline-offset:2px}
</style>
