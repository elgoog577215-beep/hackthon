<template>
  <section ref="root" class="knowledge-source-reader" tabindex="-1" data-testid="knowledge-source-reader" :aria-label="t('knowledgeFirst.sourceReader')">
    <button type="button" data-testid="close-knowledge-source" @click="emit('close')">{{ t('knowledgeFirst.backToPoint') }}</button>
    <h2>{{ t('knowledgeFirst.sourceReader') }}</h2>
    <p class="source-kind">{{ t(sourceKind === 'generated_handout' ? 'knowledgeFirst.generatedHandout' : sourceKind === 'provided_material' ? 'knowledgeFirst.providedMaterial' : 'knowledgeFirst.sourceSnapshot') }}</p>
    <dl class="source-location">
      <template v-if="sourceRef.script_revision_id"><dt>{{ t('knowledgeFirst.recordedHandoutVersion') }}</dt><dd>{{ sourceRef.script_revision_id }}</dd></template>
      <template v-if="sourceRef.block_id"><dt>{{ t('knowledgeFirst.sourceBlock') }}</dt><dd>{{ sourceRef.block_id }}</dd></template>
      <template v-if="data?.locator?.page != null"><dt>{{ t('knowledgeFirst.sourcePage') }}</dt><dd>{{ data.locator.page }}</dd></template>
      <template v-if="data?.locator?.slide != null"><dt>{{ t('knowledgeFirst.sourceSlide') }}</dt><dd>{{ data.locator.slide }}</dd></template>
    </dl>
    <p v-if="loading" role="status">{{ t('knowledgeFirst.loadingSource') }}</p>
    <p v-if="error" class="source-warning" role="alert">{{ t('knowledgeFirst.sourceLoadFailed') }} <button type="button" @click="load">{{ t('common.retry') }}</button></p>
    <p v-else-if="data && !data.available" class="source-warning" role="status">{{ t(data.reason === 'source_quote_mismatch' ? 'knowledgeFirst.sourceQuoteMismatch' : 'knowledgeFirst.sourceVersionUnavailable') }}</p>
    <p v-if="data?.available && data.quote_match === 'frozen_split_passage'" class="source-note" role="status">{{ t('knowledgeFirst.sourceSplitMatched') }}</p>
    <section class="source-excerpt" data-testid="knowledge-source-excerpt">
      <h3>{{ t('knowledgeFirst.boundQuotation') }}</h3>
      <p v-if="data?.quote_scope !== 'exact_excerpt'" class="source-note">{{ t('knowledgeFirst.passageQuotation') }}</p>
      <MarkdownRenderer :content="data?.quote || source.quote || ''" />
    </section>
    <details v-if="data?.available && data.content" class="source-context" open>
      <summary>{{ t('knowledgeFirst.sourceContext') }}</summary>
      <MarkdownRenderer :content="data.content" />
    </details>
    <p class="source-note">{{ t(data?.available ? 'knowledgeFirst.sourcePositionDisclaimer' : 'knowledgeFirst.sourceSnapshotDisclaimer') }}</p>
  </section>
</template>
<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import http from '../utils/http'
import { t } from '../shared/i18n'
import MarkdownRenderer from './MarkdownRenderer.vue'

const props = defineProps<{ courseId: string; treeRevision: string; knowledgeId: string; source: any }>()
const emit = defineEmits<{ close: [] }>()
const data = ref<any>(null), loading = ref(false), error = ref(false), root = ref<HTMLElement | null>(null)
let sequence = 0, disposed = false, controller: AbortController | undefined
const sourceRef = computed(() => data.value?.handout_ref || props.source.handout_ref || {})
const sourceKind = computed(() => data.value?.source_kind || (props.source.handout_ref ? 'generated_handout' : ''))
async function load() {
  const request = ++sequence
  controller?.abort(); controller = new AbortController()
  loading.value = true; error.value = false; data.value = null
  try {
    const result = await http.get(`/api/courses/${props.courseId}/knowledge-first/source`, {
      params: { tree_revision: props.treeRevision, knowledge_id: props.knowledgeId, evidence_id: props.source.evidence_id },
      timeout: 10000, silentError: true, signal: controller.signal,
    })
    if (disposed || request !== sequence) return
    data.value = result.data
    await nextTick()
    if (!disposed && request === sequence) root.value?.focus({ preventScroll: true })
  } catch { if (!disposed && request === sequence) error.value = true }
  finally { if (!disposed && request === sequence) loading.value = false }
}
watch(() => [props.courseId, props.treeRevision, props.knowledgeId, props.source.evidence_id], load, { immediate: true })
onBeforeUnmount(() => { disposed = true; sequence++; controller?.abort() })
</script>
<style scoped>
.knowledge-source-reader{padding:24px;color:#49365e;font-size:15px;line-height:1.8;overflow-wrap:anywhere}.knowledge-source-reader:focus{outline:none}.knowledge-source-reader h2{font-size:22px}.knowledge-source-reader h3{font-size:16px;margin:0 0 10px}.knowledge-source-reader button{font:inherit;padding:8px 12px;border:1px solid #dfd4eb;border-radius:8px;background:#fff;color:#655083;cursor:pointer}.knowledge-source-reader button:focus-visible,.source-context summary:focus-visible{outline:3px solid #a99bc9;outline-offset:2px}.source-kind{font-weight:600;color:#74618e}.source-location{font-size:15px;display:grid;grid-template-columns:110px minmax(0,1fr);gap:6px 12px}.source-location dd{margin:0}.source-excerpt{margin:20px 0;padding:16px;border-left:3px solid #9176b7;border-radius:8px;background:#f3eef9}.source-context summary{font-weight:600;cursor:pointer;margin:18px 0 12px}.source-warning{padding:12px;background:#fff7e8;border-radius:8px}.source-note{color:#786983;font-size:15px}
</style>
