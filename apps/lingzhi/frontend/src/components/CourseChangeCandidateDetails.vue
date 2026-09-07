<template>
  <details class="candidate-details">
    <summary>{{ lessonTitle }} · {{ t('courseReviewDetails.sourceAndChecks') }}</summary>
    <dl>
      <div><dt>{{ t('courseReviewDetails.revision') }}</dt><dd>{{ item.source_revision || t('courseReviewDetails.unknown') }}</dd></div>
      <div><dt>{{ t('courseReviewDetails.fields') }}</dt><dd>{{ (item.source_fields || item.matched_fields || []).join(', ') || t('courseReviewDetails.unknown') }}</dd></div>
      <div v-for="kind in ['formula', 'answer', 'citation']" :key="kind"><dt>{{ t(`courseReviewDetails.${kind}`) }}</dt><dd>{{ item.review_signals?.[kind] ? t('courseReviewDetails.check') : t('courseReviewDetails.notDetected') }}</dd></div>
      <div v-if="item.asset_type === 'ppt'"><dt>{{ t('courseReviewDetails.render') }}</dt><dd>{{ t('courseReviewDetails.renderAfterApply') }}</dd></div>
    </dl>
  </details>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import { t } from '../shared/i18n'
const props = defineProps<{ item: Record<string, any>; outline: Array<Record<string, any>> }>()
const lessonTitle = computed(() => {
  const id = props.item.lesson_id || props.item.unit_id?.split(':')[1]
  return props.outline.find(node => node.node_id === id)?.node_name || props.item.title
})
</script>
<style scoped>
.candidate-details{grid-column:2;min-width:0;font-size:15px;color:#536176}.candidate-details summary{cursor:pointer;padding:5px 0}.candidate-details dl{display:grid;gap:8px;margin:8px 0 12px}.candidate-details dl>div{display:grid;grid-template-columns:100px minmax(0,1fr);gap:10px}.candidate-details dd{margin:0;overflow-wrap:anywhere}.candidate-details dt{color:#6b778a}
</style>
