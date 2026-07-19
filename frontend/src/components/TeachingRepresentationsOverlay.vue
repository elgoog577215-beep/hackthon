<template>
  <section
    v-if="visible"
    class="representations-layer resource-workspace-overlay"
    role="region"
    :aria-label="workspaceTitle"
  >
    <div class="representations-shell resource-workspace-shell">
      <header class="resource-workspace-header">
        <div class="representations-heading">
          <span>
            <ListTree v-if="activeType === 'outline'" :size="18" />
            <ClipboardList v-else :size="18" />
          </span>
          <div>
            <strong>{{ workspaceTitle }}</strong>
            <small>{{ t('teachingRepresentations.eyebrow', '结构化同源') }}</small>
          </div>
        </div>

        <CourseWorkspaceTabs
          :active-item="activeType === 'outline' ? 'outline' : 'lesson-plan'"
          :practice-available="practiceAvailable"
          :practice-repair-available="practiceRepairAvailable"
          @outline="emit('outline')"
          @lesson-plan="emit('lesson-plan')"
          @course="emit('course')"
          @practice="emit('practice')"
        />

        <div class="representations-actions">
          <button
            type="button"
            class="representations-refresh"
            :disabled="store.building"
            :title="t('teachingRepresentations.rebuild', '同步课程最新内容')"
            :aria-label="t('teachingRepresentations.rebuild', '同步课程最新内容')"
            @click="rebuild"
          >
            <RefreshCw :size="17" :class="{ spinning: store.building }" />
          </button>
          <button
            type="button"
            class="representations-close"
            :title="t('teachingRepresentations.close', '关闭并返回课程')"
            :aria-label="t('teachingRepresentations.close', '关闭并返回课程')"
            @click="emit('close')"
          >
            <X :size="18" />
          </button>
        </div>
      </header>

      <div v-if="store.loading && !store.registry" class="representations-loading">
        <LoaderCircle :size="24" />
        <span>{{ t('teachingRepresentations.loading', '正在整理课程教学资源') }}</span>
      </div>

      <div v-else class="representations-body">
        <main v-if="selected && content" class="representation-preview">
          <div class="preview-heading">
            <div>
              <small>{{ typeLabel(selected.representation_type) }}</small>
              <h3>{{ content.title || typeLabel(selected.representation_type) }}</h3>
              <p>{{ sourceSummary }}</p>
            </div>
            <span class="representation-status" :data-status="selected.status">{{ statusLabel(selected) }}</span>
          </div>

          <div v-if="selected.status === 'stale'" class="stale-notice">
            <Clock3 :size="16" />
            <span>{{ t('teachingRepresentations.staleNotice', '课程已更新，以下单元等待同步') }}：{{ selected.stale_unit_ids.length }}</span>
          </div>

          <div v-if="selected.representation_type === 'outline'" class="outline-preview">
            <article v-for="unit in content.sections || []" :key="unit.unit_id" :class="{ stale: isStale(unit.unit_id) }">
              <span>{{ String(unit.position + 1).padStart(2, '0') }}</span>
              <div>
                <strong>{{ unit.title }}</strong>
                <p>{{ unit.learning_objective }}</p>
              </div>
            </article>
          </div>

          <div v-else class="units-preview">
            <article v-for="unit in content.units || []" :key="unit.unit_id" :class="{ stale: isStale(unit.unit_id) }">
              <header>
                <strong>{{ unit.title || unit.section_title || unit.prompt }}</strong>
                <span v-if="unit.duration_minutes">{{ unit.duration_minutes }} min</span>
              </header>
              <p v-if="unit.learning_objective">{{ unit.learning_objective }}</p>
              <ol v-if="unit.activities">
                <li v-for="activity in unit.activities" :key="activity.phase">
                  <b>{{ activity.phase }}</b>{{ activity.prompt }}
                </li>
              </ol>
            </article>
          </div>
        </main>

        <div v-else class="representations-empty">
          <Layers3 :size="28" />
          <strong>{{ t('teachingRepresentations.empty', '还没有可用的教学资源') }}</strong>
          <button type="button" :disabled="store.building" @click="rebuild">
            {{ t('teachingRepresentations.build', '从当前课程生成') }}
          </button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { ClipboardList, Clock3, Layers3, ListTree, LoaderCircle, RefreshCw, X } from 'lucide-vue-next'
import { useTeachingRepresentationsStore, type RepresentationType, type TeachingRepresentation } from '../stores/teachingRepresentations'
import { t } from '../shared/i18n'
import CourseWorkspaceTabs from './CourseWorkspaceTabs.vue'

const props = withDefaults(defineProps<{
  visible: boolean
  courseId: string
  activeType?: 'outline' | 'lesson_plan'
  practiceAvailable?: boolean
  practiceRepairAvailable?: boolean
}>(), {
  activeType: 'outline',
  practiceAvailable: false,
  practiceRepairAvailable: false,
})

const emit = defineEmits<{
  (event: 'close' | 'outline' | 'lesson-plan' | 'course' | 'practice'): void
}>()

const store = useTeachingRepresentationsStore()
const selected = computed(() => store.selectedRepresentation)
const content = computed(() => store.selectedSpec?.payload?.content || null)
const workspaceTitle = computed(() => (
  props.activeType === 'outline'
    ? t('teachingRepresentations.outlineTitle', '课程大纲')
    : t('teachingRepresentations.lessonPlanTitle', '课程教案')
))
const sourceSummary = computed(() => {
  const count = Object.keys(store.selectedSpec?.unit_bindings || {}).length
  return t('teachingRepresentations.sourceSummary', '与当前课程同源 · {count} 个精确绑定').replace('{count}', String(count))
})

function typeLabel(type: RepresentationType) {
  return t(`teachingRepresentations.types.${type}`, ({ outline: '大纲', lesson_plan: '教案', handout: '讲义', practice_sheet: '练习册', slide_deck: '演示文稿' } as Record<string, string>)[type])
}

function statusLabel(item: TeachingRepresentation) {
  if (item.status === 'stale') return t('teachingRepresentations.status.stale', '待同步')
  if (item.status === 'failed') return t('teachingRepresentations.status.failed', '生成失败')
  if (item.status === 'building') return t('teachingRepresentations.status.building', '正在生成')
  return t('teachingRepresentations.status.ready', '已同步')
}

function isStale(unitId: string) {
  return selected.value?.stale_unit_ids.includes(unitId)
}

async function selectActiveType() {
  const target = store.representations.find(item => item.representation_type === props.activeType)
  if (target && target.representation_id !== store.selectedId) await store.select(target.representation_id)
}

async function rebuild() {
  await store.buildProgressive(props.courseId).catch(() => undefined)
  await selectActiveType()
}

async function ensureLoaded() {
  if (!props.visible || !props.courseId) return
  await store.ensure(props.courseId)
  await selectActiveType()
}

watch(() => [props.visible, props.courseId], ensureLoaded)
watch(() => props.activeType, () => {
  if (props.visible) void selectActiveType()
})
onMounted(ensureLoaded)
</script>

<style scoped>
.representations-layer {
  position:absolute;
  inset:0;
  z-index:36;
  width:100%;
  height:100%;
  min-width:0;
  min-height:0;
}
.representations-shell {
  width:100%;
  height:100%;
  display:grid;
  grid-template-rows:58px minmax(0,1fr);
}
.representations-shell > header {
  min-height:58px;
  display:grid;
  grid-template-columns:minmax(180px,1fr) auto minmax(120px,1fr);
  align-items:center;
  gap:12px;
  padding:7px 12px;
}
.representations-shell > header :deep(.course-workspace-tabs) { border-color:transparent; background:transparent; }
.representations-heading { min-width:0; display:flex; align-items:center; gap:12px; }
.representations-heading > span { width:38px; height:38px; flex:0 0 38px; display:grid; place-items:center; border:1px solid #ddd6fe; border-radius:11px; color:#6d4aff; background:#f4f1ff; box-shadow:0 4px 12px rgba(109,74,255,.12); }
.representations-heading div { min-width:0; display:flex; flex-direction:column; }
.representations-heading strong { color:#252a43; font-size:16px; line-height:1.3; font-weight:760; }
.representations-heading small { margin-top:3px; overflow:hidden; color:#858ba3; font-size:11px; line-height:1.35; text-overflow:ellipsis; white-space:nowrap; }
.representations-actions { justify-self:end; display:flex; gap:8px; }
.representations-actions button { width:36px; height:36px; display:grid; place-items:center; border:1px solid #e2e5ef; border-radius:10px; color:#868ca3; background:transparent; cursor:pointer; }
.representations-actions .representations-refresh:hover { color:#5f46e8; border-color:#d7d1fb; background:#f4f1ff; }
.representations-actions .representations-close:hover { color:#d14343; border-color:#f0caca; background:#fff6f6; }
.representations-actions button:disabled { opacity:.5; }
.spinning,.representations-loading svg { animation:representation-spin .8s linear infinite; }
.representations-body { min-height:0; overflow:hidden; background:#fff; }
.representation-preview { width:min(980px,100%); height:100%; min-width:0; min-height:0; overflow:auto; margin:0 auto; padding:32px clamp(24px,5vw,64px) 48px; }
.preview-heading { display:flex; align-items:flex-start; justify-content:space-between; gap:18px; margin-bottom:22px; }
.preview-heading small { color:var(--lz-brand); font-size:10px; font-weight:750; }
.preview-heading h3 { margin:5px 0; color:var(--lz-text-strong); font-size:26px; }
.preview-heading p { margin:0; color:var(--lz-text-muted); font-size:10px; }
.representation-status { flex:0 0 auto; padding:5px 9px; border-radius:999px; color:#047857; background:#ecfdf5; font-size:9px; font-weight:750; }
.representation-status[data-status="stale"] { color:#92400e; background:#fffbeb; }
.representation-status[data-status="failed"] { color:#b91c1c; background:#fef2f2; }
.representation-status[data-status="building"] { color:#4338ca; background:#eef2ff; }
.representations-empty button { min-height:36px; display:inline-flex; align-items:center; gap:7px; padding:0 12px; border:1px solid #c7d2fe; border-radius:8px; color:var(--lz-brand-strong); background:#fff; cursor:pointer; }
.stale-notice { display:flex; align-items:center; gap:8px; margin:0 0 18px; padding:10px 12px; border-left:3px solid #f59e0b; color:#92400e; background:#fffbeb; font-size:11px; }
.outline-preview article,.units-preview article { position:relative; display:grid; grid-template-columns:34px minmax(0,1fr); gap:12px; padding:17px 0; border-bottom:1px solid #edf0f5; }
.outline-preview article > span { color:#a5b4fc; font:700 11px ui-monospace,monospace; }
.outline-preview strong,.units-preview strong { font-size:13px; }
.outline-preview p,.units-preview p { margin:4px 0 0; color:var(--lz-text-secondary); font-size:11px; line-height:1.6; }
.stale::after { content:""; position:absolute; inset:7px auto 7px -10px; width:3px; border-radius:3px; background:#f59e0b; }
.units-preview article { display:block; }
.units-preview article header { display:flex; align-items:center; justify-content:space-between; gap:12px; }
.units-preview ol { margin:10px 0 0; padding:0; list-style:none; }
.units-preview li { display:grid; grid-template-columns:64px minmax(0,1fr); gap:8px; padding:5px 0; color:var(--lz-text-secondary); font-size:10px; }
.units-preview li b { color:var(--lz-brand-strong); }
.representations-loading,.representations-empty { width:100%; height:100%; min-height:0; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:10px; color:var(--lz-text-muted); }
.representations-loading { grid-row:2; }
.representations-empty strong { color:var(--lz-text-secondary); font-size:13px; }
@keyframes representation-spin { to { transform:rotate(360deg); } }
@media (max-width:700px) {
  .representations-shell { grid-template-rows:52px minmax(0,1fr); }
  .representations-shell > header {
    min-height:52px;
    grid-template-columns:minmax(0,1fr) auto;
    gap:6px;
    padding:5px 7px;
  }
  .representations-heading { display:none; }
  .representations-shell > header :deep(.course-workspace-tabs) { grid-column:1; }
  .representations-actions { grid-column:2; }
  .representation-preview { padding:22px 18px 34px; }
  .preview-heading h3 { font-size:22px; }
}
</style>
