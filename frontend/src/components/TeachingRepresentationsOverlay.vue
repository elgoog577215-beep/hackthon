<template>
  <section v-if="visible" class="representations-layer resource-workspace-overlay" role="dialog" aria-modal="true" :aria-label="t('teachingRepresentations.title', '课程教学资源')">
    <div class="representations-shell resource-workspace-shell">
      <header class="resource-workspace-header">
        <div class="representations-heading">
          <span><Layers3 :size="18" /></span>
          <div>
            <strong>{{ t('teachingRepresentations.title', '课程教学资源') }}</strong>
            <small>{{ t('teachingRepresentations.eyebrow', '结构化同源') }}</small>
          </div>
        </div>
        <LearningContextTabs
          domain="resources"
          active-item="teaching-resources"
          @knowledge-library="emit('knowledge-library')"
        />
        <div class="representations-actions">
          <button type="button" class="representations-refresh" :disabled="store.building" :title="t('teachingRepresentations.rebuild', '同步课程最新内容')" :aria-label="t('teachingRepresentations.rebuild', '同步课程最新内容')" @click="rebuild">
            <RefreshCw :size="17" :class="{ spinning: store.building }" />
          </button>
          <button type="button" class="representations-close" :title="t('teachingRepresentations.close', '关闭课程教学资源')" :aria-label="t('teachingRepresentations.close', '关闭课程教学资源')" @click="emit('close')"><X :size="18" /></button>
        </div>
      </header>

      <div v-if="store.loading && !store.registry" class="representations-loading"><LoaderCircle :size="24" /><span>{{ t('teachingRepresentations.loading', '正在整理课程教学资源') }}</span></div>

      <div v-else class="representations-body">
        <nav :aria-label="t('teachingRepresentations.resourceList', '教学资源列表')">
          <button
            v-for="item in orderedRepresentations"
            :key="item.representation_id"
            type="button"
            :class="{ active: item.representation_id === store.selectedId }"
            @click="store.select(item.representation_id)"
          >
            <component :is="typeIcon(item.representation_type)" :size="17" />
            <span><strong>{{ typeLabel(item.representation_type) }}</strong><small>{{ statusLabel(item) }}</small></span>
            <i :data-status="item.status"></i>
          </button>
        </nav>

        <SlideDeckWorkbench
          v-if="selected?.representation_type === 'slide_deck' && (content || store.liveSlides.length)"
          :course-id="courseId"
          :representation-id="selected.representation_id"
          :deck-title="content?.title || typeLabel('slide_deck')"
          :slides="displaySlides"
          :stale-unit-ids="selected.stale_unit_ids"
          :building="store.building"
          :progress="store.buildProgress"
          :stage="store.buildStage"
          :error="store.buildError"
          :quality="store.slideQuality"
          @ask-ai="emit('ask-ai', $event)"
        />

        <main v-else-if="selected && content" class="representation-preview">
          <div class="preview-heading">
            <div>
              <small>{{ typeLabel(selected.representation_type) }}</small>
              <h3>{{ content.title || typeLabel(selected.representation_type) }}</h3>
              <p>{{ sourceSummary }}</p>
            </div>
          </div>

          <div v-if="selected.status === 'stale'" class="stale-notice">
            <Clock3 :size="16" />
            <span>{{ t('teachingRepresentations.staleNotice', '课程已更新，以下单元等待同步') }}：{{ selected.stale_unit_ids.length }}</span>
          </div>

          <div v-if="selected.representation_type === 'outline'" class="outline-preview">
            <article v-for="unit in content.sections || []" :key="unit.unit_id" :class="{ stale: isStale(unit.unit_id) }">
              <span>{{ String(unit.position + 1).padStart(2, '0') }}</span>
              <div><strong>{{ unit.title }}</strong><p>{{ unit.learning_objective }}</p></div>
            </article>
          </div>

          <div v-else class="units-preview">
            <article v-for="unit in content.units || []" :key="unit.unit_id" :class="{ stale: isStale(unit.unit_id) }">
              <header><strong>{{ unit.title || unit.section_title || unit.prompt }}</strong><span v-if="unit.duration_minutes">{{ unit.duration_minutes }} min</span></header>
              <p v-if="unit.learning_objective">{{ unit.learning_objective }}</p>
              <ol v-if="unit.activities"><li v-for="activity in unit.activities" :key="activity.phase"><b>{{ activity.phase }}</b>{{ activity.prompt }}</li></ol>
              <div v-if="unit.blocks" class="handout-blocks"><p v-for="block in unit.blocks" :key="block.block_id">{{ block.markdown }}</p></div>
              <small v-if="unit.practice_task_id">{{ t('teachingRepresentations.formalQuestion', '正式题目引用') }} · {{ unit.practice_task_id }}</small>
            </article>
          </div>
        </main>

        <div v-else class="representations-empty">
          <Layers3 :size="28" />
          <strong>{{ t('teachingRepresentations.empty', '还没有可用的教学资源') }}</strong>
          <button type="button" :disabled="store.building" @click="rebuild">{{ t('teachingRepresentations.build', '从当前课程生成') }}</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { BookOpenText, ClipboardList, Clock3, FileText, Layers3, ListTree, LoaderCircle, Presentation, RefreshCw, X } from 'lucide-vue-next'
import SlideDeckWorkbench from './SlideDeckWorkbench.vue'
import { useTeachingRepresentationsStore, type RepresentationType, type TeachingRepresentation } from '../stores/teachingRepresentations'
import { t } from '../shared/i18n'
import LearningContextTabs from './LearningContextTabs.vue'

const props = defineProps<{ visible: boolean; courseId: string }>()
const emit = defineEmits<{
  (event: 'close' | 'knowledge-library'): void
  (event: 'ask-ai', payload: { text: string; nodeId: string; anchor: Record<string, unknown>; prefill: string }): void
}>()
const store = useTeachingRepresentationsStore()
const order: RepresentationType[] = ['outline', 'lesson_plan', 'handout', 'practice_sheet', 'slide_deck']
const orderedRepresentations = computed(() => [...store.representations].sort((a, b) => order.indexOf(a.representation_type) - order.indexOf(b.representation_type)))
const selected = computed(() => store.selectedRepresentation)
const content = computed(() => store.selectedSpec?.payload?.content || null)
const displaySlides = computed(() => (
  store.building && store.liveSlides.length
    ? store.liveSlides
    : (content.value?.slides || [])
))
const sourceSummary = computed(() => {
  const count = Object.keys(store.selectedSpec?.unit_bindings || {}).length
  return t('teachingRepresentations.sourceSummary', '与当前课程同源 · {count} 个精确绑定').replace('{count}', String(count))
})

function typeLabel(type: RepresentationType) {
  return t(`teachingRepresentations.types.${type}`, ({ outline: '大纲', lesson_plan: '教案', handout: '讲义', practice_sheet: '练习册', slide_deck: '演示文稿' } as Record<string, string>)[type])
}
function typeIcon(type: RepresentationType) {
  return ({ outline: ListTree, lesson_plan: ClipboardList, handout: BookOpenText, practice_sheet: FileText, slide_deck: Presentation })[type]
}
function statusLabel(item: TeachingRepresentation) {
  if (item.status === 'stale') return t('teachingRepresentations.status.stale', '待同步')
  if (item.status === 'failed') return t('teachingRepresentations.status.failed', '生成失败')
  if (item.status === 'building') return t('teachingRepresentations.status.building', '正在生成')
  return t('teachingRepresentations.status.ready', '已同步')
}
function isStale(unitId: string) { return selected.value?.stale_unit_ids.includes(unitId) }
async function rebuild() { await store.buildProgressive(props.courseId).catch(() => undefined) }
async function ensureLoaded() { if (props.visible && props.courseId) await store.ensure(props.courseId) }
watch(() => [props.visible, props.courseId], ensureLoaded)
onMounted(ensureLoaded)
</script>

<style scoped>
.representations-shell { display:grid; grid-template-rows:72px minmax(0,1fr); }
.representations-shell > header { display:grid; grid-template-columns:minmax(210px,1fr) auto minmax(210px,1fr); align-items:center; gap:12px; }
.representations-shell > header :deep(.learning-context-tabs) { min-height:44px; padding:4px; border:0; background:transparent; }
.representations-heading { min-width:0; display:flex; align-items:center; gap:12px; }.representations-heading > span { width:38px; height:38px; flex:0 0 38px; display:grid; place-items:center; border:1px solid #ddd6fe; border-radius:11px; color:#6d4aff; background:#f4f1ff; box-shadow:0 4px 12px rgba(109,74,255,.12); }.representations-heading div { min-width:0; display:flex; flex-direction:column; }.representations-heading strong { color:#252a43; font-size:16px; line-height:1.3; font-weight:760; }.representations-heading small { margin-top:3px; overflow:hidden; color:#858ba3; font-size:11px; line-height:1.35; text-overflow:ellipsis; white-space:nowrap; }
.representations-actions { justify-self:end; display:flex; gap:8px; }.representations-actions button { width:36px; height:36px; display:grid; place-items:center; border:1px solid #e2e5ef; border-radius:10px; color:#868ca3; background:transparent; cursor:pointer; }.representations-actions .representations-refresh:hover { color:#5f46e8; border-color:#d7d1fb; background:#f4f1ff; }.representations-actions .representations-close:hover { color:#d14343; border-color:#f0caca; background:#fff6f6; }.representations-actions button:disabled { opacity:.5; }.spinning,.representations-loading svg { animation:representation-spin .8s linear infinite; }
.representations-body { min-height:0; display:grid; grid-template-columns:230px minmax(0,1fr); }.representations-body > nav { min-height:0; overflow:auto; padding:10px; border-right:1px solid var(--lz-border); background:#fafbfe; }.representations-body > nav button { width:100%; min-height:54px; display:grid; grid-template-columns:28px minmax(0,1fr) 8px; align-items:center; gap:6px; margin:0 0 3px; padding:7px 9px; border:1px solid transparent; border-radius:8px; color:var(--lz-text-secondary); background:transparent; text-align:left; cursor:pointer; }.representations-body > nav button:hover { background:#fff; }.representations-body > nav button.active { border-color:#c7d2fe; color:var(--lz-brand-strong); background:#fff; box-shadow:0 3px 10px rgba(79,70,229,.06); }.representations-body > nav button > span { min-width:0; display:flex; flex-direction:column; }.representations-body > nav strong { font-size:11px; }.representations-body > nav small { margin-top:2px; color:var(--lz-text-muted); font-size:9px; }.representations-body > nav i { width:7px; height:7px; border-radius:50%; background:#10b981; }.representations-body > nav i[data-status="stale"] { background:#f59e0b; }.representations-body > nav i[data-status="failed"] { background:#ef4444; }
.representation-preview { min-width:0; min-height:0; overflow:auto; padding:26px clamp(24px,4vw,48px) 40px; }.preview-heading { display:flex; align-items:flex-start; justify-content:space-between; gap:18px; margin-bottom:22px; }.preview-heading small { color:var(--lz-brand); font-size:10px; font-weight:750; }.preview-heading h3 { margin:5px 0 5px; color:var(--lz-text-strong); font-size:24px; }.preview-heading p { margin:0; color:var(--lz-text-muted); font-size:10px; }.download-command,.representations-empty button { min-height:36px; display:inline-flex; align-items:center; gap:7px; padding:0 12px; border:1px solid #c7d2fe; border-radius:8px; color:var(--lz-brand-strong); background:#fff; cursor:pointer; }.stale-notice { display:flex; align-items:center; gap:8px; margin:0 0 18px; padding:10px 12px; border-left:3px solid #f59e0b; color:#92400e; background:#fffbeb; font-size:11px; }
.outline-preview article,.units-preview article { position:relative; display:grid; grid-template-columns:34px minmax(0,1fr); gap:12px; padding:15px 0; border-bottom:1px solid #edf0f5; }.outline-preview article > span { color:#a5b4fc; font:700 11px ui-monospace,monospace; }.outline-preview strong,.units-preview strong { font-size:13px; }.outline-preview p,.units-preview p { margin:4px 0 0; color:var(--lz-text-secondary); font-size:11px; line-height:1.6; }.stale::after { content:""; position:absolute; inset:7px auto 7px -10px; width:3px; border-radius:3px; background:#f59e0b; }
.slides-preview { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:14px; }.slides-preview article { position:relative; aspect-ratio:16/9; display:grid; grid-template-columns:24px minmax(0,1fr); gap:9px; padding:18px; border:1px solid #e3e7ef; border-radius:8px; background:#fff; box-shadow:0 7px 18px rgba(15,23,42,.05); }.slides-preview article > span { color:#a5b4fc; font:700 10px ui-monospace,monospace; }.slides-preview strong { color:#312e81; font-size:13px; }.slides-preview ul { margin:10px 0 0; padding-left:16px; color:var(--lz-text-secondary); font-size:9px; line-height:1.6; }
.slide-edit-command { position:absolute; top:9px; right:9px; width:28px; height:28px; display:grid; place-items:center; border:0; border-radius:6px; color:var(--lz-text-muted); background:rgba(248,250,252,.9); cursor:pointer; }.slide-edit-command:hover { color:var(--lz-brand-strong); background:var(--lz-brand-soft); }.slide-edit-panel { position:absolute; inset:7px; z-index:2; display:flex; flex-direction:column; gap:6px; padding:11px; border:1px solid #c7d2fe; border-radius:7px; background:#fff; box-shadow:0 10px 26px rgba(49,46,129,.14); }.slide-edit-panel input { height:32px; padding:0 8px; border:1px solid var(--lz-border); border-radius:6px; color:var(--lz-text); font-size:11px; outline:none; }.slide-edit-panel input:focus { border-color:#818cf8; }.slide-edit-panel p { margin:0; color:var(--lz-text-secondary); font-size:9px; line-height:1.45; }.slide-edit-panel p strong { display:inline-block; margin-right:6px; color:var(--lz-brand-strong); font-size:9px; }.slide-edit-panel small { color:var(--lz-text-muted); font-size:8px; }.slide-edit-panel > div { display:flex; flex-wrap:wrap; gap:4px; margin-top:auto; }.slide-edit-panel > div button { min-height:27px; display:inline-flex; align-items:center; justify-content:center; gap:4px; padding:0 7px; border:1px solid var(--lz-border); border-radius:5px; color:var(--lz-text-secondary); background:#fff; font-size:8px; cursor:pointer; }.slide-edit-panel > div button.semantic-command { color:#fff; border-color:#6366f1; background:#6366f1; }.slide-edit-panel em { color:#047857; font-size:8px; font-style:normal; }
.units-preview article { display:block; }.units-preview article header { display:flex; align-items:center; justify-content:space-between; gap:12px; }.units-preview ol { margin:10px 0 0; padding:0; list-style:none; }.units-preview li { display:grid; grid-template-columns:54px minmax(0,1fr); gap:8px; padding:5px 0; color:var(--lz-text-secondary); font-size:10px; }.units-preview li b { color:var(--lz-brand-strong); }.handout-blocks p { white-space:pre-line; }.units-preview article > small { display:inline-block; margin-top:8px; color:var(--lz-brand); font-size:9px; }
.representations-loading,.representations-empty { min-height:0; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:10px; color:var(--lz-text-muted); }.representations-loading { grid-row:2; }.representations-empty { grid-column:2; }.representations-empty strong { color:var(--lz-text-secondary); font-size:13px; }
@keyframes representation-spin { to { transform:rotate(360deg); } }
@media (max-width:700px) { .representations-shell { grid-template-rows:106px minmax(0,1fr); }.representations-shell > header { grid-template-columns:minmax(0,1fr) auto; grid-template-rows:52px 44px; padding:4px 10px 6px 14px; }.representations-shell > header :deep(.learning-context-tabs) { grid-column:1 / -1; grid-row:2; justify-content:center; }.representations-actions { grid-column:2; grid-row:1; }.representations-body { grid-template-columns:1fr; grid-template-rows:auto minmax(0,1fr); }.representations-body > nav { display:flex; overflow-x:auto; border-right:0; border-bottom:1px solid var(--lz-border); }.representations-body > nav button { min-width:124px; }.representation-preview { padding:20px 16px 32px; }.slides-preview { grid-template-columns:1fr; }.representations-empty { grid-column:1; } }
</style>
