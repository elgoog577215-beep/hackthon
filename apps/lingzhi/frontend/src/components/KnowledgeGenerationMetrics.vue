<template>
  <details class="generation-metrics" data-testid="knowledge-generation-metrics">
    <summary>{{ t('knowledgeFirst.stageMetrics') }} · {{ observations.length }}</summary>
    <p>{{ t('knowledgeFirst.stageMetricsHint') }}</p>
    <div class="metrics-table"><table><thead><tr><th scope="col">{{ t('knowledgeFirst.metricsStage') }}</th><th scope="col">{{ t('knowledgeFirst.requestSeconds') }}</th><th scope="col">{{ t('knowledgeFirst.firstContentSeconds') }}</th><th scope="col">{{ t('knowledgeFirst.inputOutputTokens') }}</th></tr></thead>
      <tbody><tr v-for="(row,index) in observations" :key="index"><th scope="row">{{ Number(index)+1 }} · {{ t(row.stage === 'inventory' ? 'knowledgeFirst.inventoryTitle' : row.stage === 'relations' ? 'knowledgeFirst.relations' : 'knowledgeFirst.atomicCandidates') }}</th>
        <td>{{ duration(row.seconds) }}</td><td>{{ row.first_content_seconds == null ? t('knowledgeFirst.noFirstContent') : duration(row.first_content_seconds) }}</td>
        <td>{{ row.input_tokens == null || row.output_tokens == null ? t('knowledgeFirst.metricsUnknown') : `${row.tokens_source === 'provider' ? '' : t('knowledgeFirst.metricsEstimated')}${row.input_tokens} / ${row.output_tokens}` }}</td></tr></tbody></table></div>
  </details>
</template>
<script setup lang="ts">
import {t} from '../shared/i18n'
defineProps<{observations:any[]}>()
const duration=(value:unknown)=>typeof value === 'number' && Number.isFinite(value) ? `${value.toFixed(1)} s` : t('knowledgeFirst.metricsUnknown')
</script>
<style scoped>
.generation-metrics{margin:16px 0;padding:14px 18px;border:1px solid #e0d8ef;background:#faf8fd;border-radius:10px;font-size:15px;line-height:1.8;color:#65517b}.generation-metrics summary{font-weight:600;cursor:pointer}.generation-metrics summary:focus-visible{outline:3px solid #b5a1d1;outline-offset:3px}.metrics-table{overflow-x:auto}.metrics-table table{width:100%;border-collapse:collapse;text-align:left}.metrics-table th,.metrics-table td{padding:9px 12px;border-bottom:1px solid #e9e2f2;white-space:nowrap}.metrics-table th{font-weight:500}.generation-metrics p{color:#82718e}
</style>
