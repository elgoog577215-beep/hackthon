<template>
  <section class="question-supply" :aria-label="t('knowledgeSupply.title')">
    <h3>{{ t('knowledgeSupply.title') }}</h3>
    <p v-if="loading" role="status">{{ t('knowledgeSupply.loading') }}</p>
    <template v-else-if="point">
      <p>{{ t('knowledgeSupply.available') }} {{ point.available_count }} · {{ t('knowledgeSupply.pending') }} {{ point.pending_count }}</p>
      <p class="sources">{{ t('knowledgeSupply.imported') }} {{ point.sources.imported || 0 }} · {{ t('knowledgeSupply.authored') }} {{ point.sources.authored || 0 }} · {{ t('knowledgeSupply.generated') }} {{ point.sources.generated || 0 }}</p>
      <p v-if="!point.available_count">{{ t('knowledgeSupply.empty') }}</p>
      <p v-if="point.pending_count">{{ t('knowledgeSupply.reviewHint') }}</p>
      <button v-if="!point.available_count && !point.pending_count" :disabled="busy || running || !point.can_generate || stale" @click="generate">{{ t('knowledgeSupply.generate') }}</button>
      <p v-if="!point.can_generate">{{ t('knowledgeSupply.noSource') }}</p>
      <p v-if="stale">{{ t('knowledgeSupply.stale') }}</p>
    </template>
    <p v-if="job && relevantJob" role="status">{{ job.message || t('knowledgeSupply.running') }}</p>
    <p v-if="error" role="alert">{{ error }}</p>
    <button v-if="error || (!loading && !point)" :disabled="busy" @click="load">{{ t('knowledgeSupply.refresh') }}</button>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import http, { teacherRequestConfig } from '../utils/http'
import { createUuid } from '../utils/client-id'
import { t } from '../shared/i18n'

type Supply = { knowledge_id: string; revision_id: string; node_id: string; available_count: number; pending_count: number; sources: Record<string, number>; can_generate: boolean }
type Job = { job_id: string; status: string; message?: string; knowledge_ids?: string[]; error?: { message?: string } }
const props = defineProps<{ courseId: string; knowledgeId: string; baselineRevision: string }>()
const point = ref<Supply | null>(null), job = ref<Job | null>(null)
const loading = ref(false), busy = ref(false), error = ref(''), actualBaseline = ref('')
const running = computed(() => !!job.value && ['queued', 'running'].includes(job.value.status))
const relevantJob = computed(() => job.value?.knowledge_ids?.includes(props.knowledgeId))
const stale = computed(() => actualBaseline.value !== props.baselineRevision)
let sequence = 0, disposed = false
let timer: ReturnType<typeof setTimeout> | undefined
const endpoint = () => `/api/courses/${props.courseId}/question-bank`
const message = (e: any) => e?.response?.data?.detail?.message || t('knowledgeSupply.failed')

async function load() {
  clearTimeout(timer)
  const token = ++sequence
  loading.value = !point.value
  try {
    const response = await http.get(`${endpoint()}/knowledge-supply`, teacherRequestConfig())
    if (disposed || sequence !== token) return
    actualBaseline.value = response.data.knowledge_baseline_revision
    point.value = (response.data.points || []).find((p: Supply) => p.knowledge_id === props.knowledgeId) || null
    job.value = response.data.job || null
    error.value = relevantJob.value && job.value?.status === 'failed' ? job.value.error?.message || t('knowledgeSupply.failed') : ''
    if (running.value) timer = setTimeout(load, 3000)
  } catch (e) { if (!disposed && token === sequence) error.value = message(e) }
  finally { if (!disposed && token === sequence) loading.value = false }
}

async function generate() {
  if (!point.value || busy.value || running.value || stale.value || point.value.available_count || point.value.pending_count) return
  const token = sequence
  busy.value = true; error.value = ''
  try {
    await http.post(`${endpoint()}/rebuild`, {
      request_id: createUuid(), scope: 'nodes', node_ids: [point.value.node_id],
      knowledge_ids: [props.knowledgeId], knowledge_baseline_revision: props.baselineRevision,
      mode: 'incremental', resume_existing: false, retrieval_enabled: false,
    }, teacherRequestConfig())
    if (!disposed && token === sequence) await load()
  } catch (e) { if (!disposed && token === sequence) error.value = message(e) }
  finally { busy.value = false }
}

watch(() => [props.courseId, props.knowledgeId, props.baselineRevision], () => {
  point.value = null; job.value = null; error.value = ''; void load()
}, { immediate: true })
onBeforeUnmount(() => { disposed = true; sequence++; clearTimeout(timer) })
</script>

<style scoped>
.question-supply { margin-top:24px; padding:18px; border:1px solid #dfd8ef; border-radius:12px; background:#f7f5fc; font-size:15px; }
.question-supply h3 { margin:0 0 10px; font-size:16px; }
.question-supply p { margin:8px 0; line-height:1.7; }
.sources { color:#74748b; }
.question-supply button { padding:9px 14px; border:1px solid #7765ba; border-radius:8px; background:#7765ba; color:white; font:inherit; cursor:pointer; }
.question-supply button:disabled { opacity:.5; cursor:not-allowed; }
.question-supply button:focus-visible { outline:3px solid #a296d1; outline-offset:3px; }
[role=alert] { color:#9c3e53; }
</style>
