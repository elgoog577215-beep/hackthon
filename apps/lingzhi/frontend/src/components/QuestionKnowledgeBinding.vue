<template>
  <section class="knowledge-binding" tabindex="0" :aria-label="t('questionBank.binding.title', '题目与元知识点')" :aria-busy="busy">
    <div class="binding-summary">
      <div>
        <strong>{{ t('questionBank.binding.title', '题目与元知识点') }}</strong>
        <p v-if="view.tree_ready" role="status" aria-live="polite">
          {{ t('questionBank.binding.summary', '已绑定 {bound} 道 · 待绑定 {unbound} 道 · 待确认 {pending} 道 · 已过期 {stale} 道')
            .replace('{bound}', String(view.counts.bound || 0)).replace('{unbound}', String(view.counts.unbound || 0))
            .replace('{pending}', String(view.counts.pending || 0)).replace('{stale}', String(view.counts.stale || 0)) }}
        </p>
        <p v-else>{{ t('questionBank.binding.noTree', '请先生成并采用知识树，题库将自动匹配元知识点。') }}</p>
      </div>
      <div class="binding-actions">
      <button type="button" data-testid="auto-bind-knowledge" :disabled="!view.tree_ready || !view.can_edit || busy || !(view.counts.unbound || view.counts.pending)" @click="runBinding('auto', true)">
        <ListTree :size="17" />{{ t('questionBank.binding.adapt', '一键适配元知识点') }}
      </button>
      <button type="button" data-testid="open-knowledge-binding" :disabled="!view.tree_ready || !view.can_edit" :aria-expanded="opened" @click="opened = !opened">
        <ListTree :size="17" />{{ t('questionBank.binding.bind', '绑定知识点') }}
      </button>
      </div>
    </div>
    <p v-if="busy" class="binding-notice" role="status"><LoaderCircle class="binding-spin" :size="16" />{{ t('questionBank.binding.working', '正在绑定元知识点…') }}</p>
    <p v-if="error" class="binding-error" role="alert">{{ error }}</p>
    <div v-if="opened && view.tree_ready" class="binding-editor">
      <p>{{ t('questionBank.binding.help', '仅绑定题目实际考查的元知识点。多知识点题需逐点评分后才能判断掌握度；知识关联不代表已经确定错因。') }}</p>
      <div class="binding-controls">
        <label>
          {{ t('questionBank.binding.question', '选择题目') }}
          <select v-model="selectedRevision" :disabled="busy">
            <option v-for="(item, index) in view.items" :key="item.revision_id" :value="item.revision_id">
              {{ index + 1 }}. {{ item.prompt.slice(0, 65) }} — {{ statusLabel(item.status) }}
            </option>
          </select>
        </label>
        <button type="button" :disabled="busy || !retryable" @click="runBinding('auto', true)">
          <RefreshCw :size="16" />{{ t('questionBank.binding.retry', '重新自动匹配待绑定题') }}
        </button>
      </div>
      <p v-if="selectedItem?.status === 'stale'" class="binding-notice">{{ t('questionBank.binding.staleHint', '知识树已更新，请核对后重新绑定。历史作答仍关联原知识修订。') }}</p>
      <label class="binding-search">
        {{ t('questionBank.binding.search', '筛选元知识点') }}
        <input v-model="query" type="search" :placeholder="t('questionBank.binding.searchPlaceholder', '输入知识名称或命题')" />
      </label>
      <fieldset :disabled="busy">
        <legend>{{ t('questionBank.binding.select', '选择实际考查的知识点（最多 5 个）') }}</legend>
        <label v-for="point in visiblePoints" :key="point.knowledge_id" class="binding-point">
          <input v-model="selectedIds" type="checkbox" :value="point.knowledge_id" :disabled="selectedIds.length >= 5 && !selectedIds.includes(point.knowledge_id)" />
          <span><strong>{{ point.name || point.statement }}</strong><small v-if="point.name && point.statement">{{ point.statement }}</small></span>
        </label>
        <p v-if="!visiblePoints.length">{{ t('questionBank.binding.noMatches', '没有匹配的元知识点') }}</p>
      </fieldset>
      <div class="binding-footer">
        <span>{{ t('questionBank.binding.selected', '已选 {count} 个').replace('{count}', String(selectedIds.length)) }}</span>
        <button type="button" data-testid="save-knowledge-binding" :disabled="busy || !selectedRevision" @click="runBinding('manual')">
          {{ selectedIds.length ? t('questionBank.binding.save', '保存绑定') : t('questionBank.binding.clear', '标记为待确认') }}
        </button>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ListTree, LoaderCircle, RefreshCw } from 'lucide-vue-next'
import http, { teacherReadRequestConfig, teacherRequestConfig } from '@/utils/http'
import { t } from '@/shared/i18n'

interface BindingItem { revision_id: string; item_id?: string; prompt: string; status: string; knowledge_ids: string[] }
interface BindingPoint { knowledge_id: string; name: string; statement: string }
interface BindingView {
  tree_ready: boolean; can_edit: boolean; knowledge_baseline_revision: string; bundle_revision_id: string
  counts: Record<string, number>; points: BindingPoint[]; items: BindingItem[]; auto_revision_ids: string[]
}
const props = defineProps<{ courseId: string; bundleRevision: string; generationActive?: boolean }>()
const emit = defineEmits<{ updated: [revision: string] }>()
const emptyView = (): BindingView => ({ tree_ready: false, can_edit: false, knowledge_baseline_revision: '', bundle_revision_id: '', counts: {}, points: [], items: [], auto_revision_ids: [] })
const view = ref<BindingView>(emptyView())
const busy = ref(false)
const opened = ref(false)
const error = ref('')
const query = ref('')
const selectedRevision = ref('')
const selectedIds = ref<string[]>([])
const attempted = new Set<string>()
let sequence = 0
let disposed = false
let controller: AbortController | null = null
const selectedItem = computed(() => view.value.items.find(i => i.revision_id === selectedRevision.value))
const visiblePoints = computed(() => view.value.points.filter(p => `${p.name} ${p.statement}`.toLowerCase().includes(query.value.trim().toLowerCase())))
const retryable = computed(() => view.value.items.some(i => ['unbound', 'pending'].includes(i.status)))

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    bound: t('questionBank.binding.bound', '已绑定'), unbound: t('questionBank.binding.unbound', '待绑定'),
    pending: t('questionBank.binding.pending', '待确认'), stale: t('questionBank.binding.stale', '知识树已更新'),
  }
  return labels[status] || status
}
function applyView(data: Partial<BindingView>) {
  const previousId = selectedItem.value?.item_id
  view.value = { ...emptyView(), ...data }
  selectedRevision.value = view.value.items.find(i => i.revision_id === selectedRevision.value || (previousId && i.item_id === previousId))?.revision_id || view.value.items[0]?.revision_id || ''
  selectedIds.value = (selectedItem.value?.knowledge_ids || []).filter(id => view.value.points.some(p => p.knowledge_id === id))
}
watch(selectedRevision, () => {
  selectedIds.value = (selectedItem.value?.knowledge_ids || []).filter(id => view.value.points.some(p => p.knowledge_id === id))
})

async function refresh() {
  if (!props.courseId || !props.bundleRevision || busy.value) return
  const courseId = props.courseId
  const token = ++sequence
  try {
    const response = await http.get(`/api/courses/${courseId}/question-bank/knowledge-bindings`, teacherReadRequestConfig({ silentError: true }))
    if (disposed || courseId !== props.courseId || token !== sequence) return
    applyView(response.data || {})
    const key = `${courseId}:${view.value.bundle_revision_id}:${view.value.knowledge_baseline_revision}`
    if (view.value.tree_ready && view.value.can_edit && view.value.auto_revision_ids.length && !attempted.has(key) && !props.generationActive) {
      attempted.add(key)
      await runBinding('auto')
    }
  } catch {
    if (!disposed && token === sequence) error.value = t('questionBank.binding.loadFailed', '知识绑定状态读取失败，请刷新后重试。')
  }
}

async function runBinding(mode: 'auto' | 'manual', retryPending = false) {
  if (busy.value || !view.value.tree_ready || !view.value.can_edit || props.generationActive) return
  const courseId = props.courseId
  const token = ++sequence
  const initialRevision = view.value.bundle_revision_id
  const remaining = view.value.items.filter(i => i.status === 'unbound' || (retryPending && i.status === 'pending')).map(i => i.revision_id)
  const current = () => !disposed && token === sequence && courseId === props.courseId
  controller = new AbortController()
  busy.value = true
  error.value = ''
  try {
    do {
      const previousRevision = view.value.bundle_revision_id
      const response = await http.post(`/api/courses/${courseId}/question-bank/knowledge-bindings`, {
        mode, expected_bundle_revision_id: previousRevision,
        knowledge_baseline_revision: view.value.knowledge_baseline_revision,
        ...(mode === 'manual' ? { revision_id: selectedRevision.value, knowledge_ids: selectedIds.value } : { retry_pending: retryPending, revision_ids: remaining.slice(0, 8) }),
      }, teacherRequestConfig({ signal: controller.signal, timeout: 60000, silentError: true }))
      if (!current()) return
      applyView(response.data || {})
      remaining.splice(0, 8)
      if (mode === 'manual') break
    } while (remaining.length)
  } catch (cause: any) {
    if (!current()) return
    error.value = cause?.response?.status === 409
      ? t('questionBank.binding.conflict', '课程或题库正在更新，请刷新后重新绑定。')
      : mode === 'manual'
        ? t('questionBank.binding.saveFailed', '绑定保存失败，请稍后重试。')
        : t('questionBank.binding.failed', '自动绑定暂不可用，已保存的题目不受影响。可手动选择知识点，或稍后重试。')
  } finally {
    if (current()) {
      busy.value = false
      if (initialRevision !== view.value.bundle_revision_id) emit('updated', view.value.bundle_revision_id)
    }
  }
}
watch(() => props.courseId, () => {
  sequence++
  controller?.abort()
  busy.value = false
  opened.value = false
  error.value = ''
  attempted.clear()
  view.value = emptyView()
  void refresh()
})
watch(() => [props.bundleRevision, props.generationActive], () => { void refresh() })
onMounted(() => { void refresh(); window.addEventListener('focus', refresh) })
onBeforeUnmount(() => { disposed = true; sequence++; controller?.abort(); window.removeEventListener('focus', refresh) })
</script>

<style scoped>
.knowledge-binding { margin: 16px 24px; padding: 16px 20px; border: 1px solid #dedcf2; border-radius: 14px; background: #faf9ff; color: #302e49; font-size: 15px; }
.knowledge-binding:focus-visible { outline:2px solid #7562c8; outline-offset:-2px; }
.binding-summary, .binding-controls, .binding-footer { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.binding-actions { display: flex; align-items: center; gap: 8px; }
p { margin: 6px 0; line-height: 1.6; color: #605d76; }
button { display: inline-flex; gap: 7px; align-items: center; justify-content: center; min-height: 38px; padding: 7px 12px; border: 1px solid #c6c0e4; border-radius: 8px; color: #51418f; background: white; font: inherit; white-space: nowrap; cursor: pointer; }
button:disabled { opacity: .5; cursor: not-allowed; }
button:focus-visible, input:focus-visible, select:focus-visible { outline: 2px solid #7562c8; outline-offset: 3px; }
.binding-editor { margin-top: 16px; border-top: 1px solid #dedcf2; padding-top: 12px; }
.binding-controls { margin: 12px 0; }
.binding-controls label { flex: 1; min-width: 0; }
select, input[type=search] { display: block; width: 100%; margin-top: 6px; padding: 8px; border: 1px solid #cbc7db; border-radius: 6px; font: inherit; background: white; color: inherit; }
.binding-search { display: block; margin: 12px 0; }
fieldset { max-height: 290px; overflow: auto; border: 1px solid #dedcf2; border-radius: 8px; }
legend { padding: 0 6px; }
.binding-point { display: flex; gap: 10px; padding: 10px; align-items: flex-start; cursor: pointer; }
.binding-point input { margin-top: 4px; accent-color: #6b55b7; }
.binding-point small { display: block; margin-top: 4px; color: #605d76; font-size: 15px; line-height: 1.5; }
.binding-footer { margin-top: 12px; }
.binding-notice { display: flex; gap: 8px; align-items: center; }
.binding-error { color: #a43535; }
.binding-spin { animation: binding-rotate 1s linear infinite; }
@keyframes binding-rotate { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .binding-spin { animation: none; } }
@media (max-width: 1000px) { .binding-summary, .binding-controls, .binding-actions { flex-wrap: wrap; } }
</style>
