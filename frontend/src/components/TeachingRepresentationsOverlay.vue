<template>
  <section
    v-if="visible"
    class="representations-layer resource-workspace-overlay"
    role="dialog"
    aria-modal="true"
    :aria-label="workspaceTitle"
  >
    <div class="representations-shell resource-workspace-shell">
      <header class="resource-workspace-header">
        <div class="representations-heading">
          <span>
            <ListTree v-if="displayType === 'outline'" :size="18" />
            <Network v-else-if="displayType === 'diagram'" :size="18" />
            <ClipboardList v-else :size="18" />
          </span>
          <div>
            <strong>{{ workspaceTitle }}</strong>
            <small>{{ t('teachingRepresentations.eyebrow', '结构化同源') }}</small>
          </div>
        </div>

        <CourseWorkspaceTabs
          active-item="lesson-plan"
          :practice-available="practiceAvailable"
          :practice-repair-available="practiceRepairAvailable"
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

          <nav class="representation-types" :aria-label="t('teachingRepresentations.typeNav', '资源类型')">
            <button
              v-for="item in selectableTypes"
              :key="item.representation_type"
              type="button"
              :data-representation-type="item.representation_type"
              :aria-pressed="selected.representation_type === item.representation_type"
              @click="selectType(item.representation_type)"
            >
              {{ typeLabel(item.representation_type) }}
            </button>
          </nav>

          <div v-if="selected.status === 'stale'" class="stale-notice">
            <Clock3 :size="16" />
            <span>{{ t('teachingRepresentations.staleNotice', '课程已更新，以下单元等待同步') }}：{{ selected.stale_unit_ids.length }}</span>
          </div>

          <div v-if="selected.representation_type === 'diagram'" class="diagram-preview">
            <div class="diagram-quality" :data-passed="String(Boolean(content.quality_report?.passed))">
              <strong>{{ content.quality_report?.passed ? t('teachingRepresentations.diagram.qualityPassed', '来源与结构校验通过') : t('teachingRepresentations.diagram.qualityReview', '图解需要检查') }}</strong>
              <span>{{ t('teachingRepresentations.diagram.unitCount', '{count} 个同源图解单元').replace('{count}', String(content.quality_report?.unit_count ?? content.units?.length ?? 0)) }}</span>
            </div>
            <article v-for="unit in content.units || []" :key="unit.unit_id" :class="{ stale: isStale(unit.unit_id) }">
              <header>
                <div>
                  <strong>{{ unit.title }}</strong>
                  <small>{{ diagramBindingSummary(unit) }}</small>
                </div>
                <span>{{ unit.diagram_kind === 'learning_path' ? t('teachingRepresentations.diagram.learningPath', '学习路径') : t('teachingRepresentations.diagram.conceptMap', '概念图') }}</span>
              </header>
              <DiagramSpecRenderer :unit="unit" :title="unit.title" />
            </article>
          </div>

          <div v-else-if="selected.representation_type === 'outline'" class="outline-preview">
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
import { ClipboardList, Clock3, Layers3, ListTree, LoaderCircle, Network, RefreshCw, X } from 'lucide-vue-next'
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
  return t(`teachingRepresentations.types.${type}`, ({ outline: '大纲', lesson_plan: '教案', handout: '讲义', practice_sheet: '练习册', slide_deck: '演示文稿', diagram: '知识图解' } as Record<string, string>)[type])
}

/** 头部图标按“当前实际展示的表征类型”走，未选中时回落到入口 activeType。 */
const displayType = computed<RepresentationType>(() => selected.value?.representation_type ?? props.activeType)

/** 类型切换条：已生成（非归档）的表征，按固定顺序展示，保证渲染稳定。 */
const TYPE_ORDER: RepresentationType[] = ['outline', 'lesson_plan', 'handout', 'practice_sheet', 'slide_deck', 'diagram']
const selectableTypes = computed<TeachingRepresentation[]>(() => (
  store.representations
    .filter(item => item.status !== 'archived')
    .slice()
    .sort((a, b) => TYPE_ORDER.indexOf(a.representation_type) - TYPE_ORDER.indexOf(b.representation_type))
))

async function selectType(type: RepresentationType) {
  const target = store.representations.find(item => item.representation_type === type)
  if (target && target.representation_id !== store.selectedId) await store.select(target.representation_id)
}

/** 图解单元的同源绑定摘要，纯文本。 */
function diagramBindingSummary(unit: Record<string, any>) {
  const sections = Array.isArray(unit?.source_section_ids) ? unit.source_section_ids.length : 0
  const blocks = Array.isArray(unit?.source_block_ids) ? unit.source_block_ids.length : 0
  const knowledge = Array.isArray(unit?.knowledge_refs) ? unit.knowledge_refs.length : 0
  return t('teachingRepresentations.diagram.bindingSummary', '{sections} 个章节 · {blocks} 个内容块 · {knowledge} 个知识点')
    .replace('{sections}', String(sections))
    .replace('{blocks}', String(blocks))
    .replace('{knowledge}', String(knowledge))
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
.representations-shell { display:grid; grid-template-rows:72px minmax(0,1fr); }
.representations-shell > header { display:grid; grid-template-columns:minmax(180px,1fr) auto minmax(120px,1fr); align-items:center; gap:12px; }
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
  .representations-shell { grid-template-rows:106px minmax(0,1fr); }
  .representations-shell > header { grid-template-columns:minmax(0,1fr) auto; grid-template-rows:52px 44px; padding:4px 10px 6px 14px; }
  .representations-shell > header :deep(.course-workspace-tabs) { grid-column:1 / -1; grid-row:2; }
  .representations-actions { grid-column:2; grid-row:1; }
  .representation-preview { padding:22px 18px 34px; }
  .preview-heading h3 { font-size:22px; }
}
</style>
