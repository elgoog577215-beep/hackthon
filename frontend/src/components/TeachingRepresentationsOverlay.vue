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
          @ppt="emit('ppt')"
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

          <section v-if="overviewMode" class="material-suite" aria-labelledby="material-suite-title">
            <div class="material-suite__heading">
              <div>
                <small>{{ t('teachingRepresentations.materialSuite.eyebrow', '一份课程真源 · 六类教学材料') }}</small>
                <h3 id="material-suite-title">{{ t('teachingRepresentations.materialSuite.title', '教学材料已一键生成，并保持同源连接') }}</h3>
                <p>{{ t('teachingRepresentations.materialSuite.description', '大纲决定方向，教案与讲义承载细节，PPT、练习和图解共同引用同一份课程结构。') }}</p>
              </div>
              <button type="button" :disabled="store.building" @click="rebuild">
                <LoaderCircle v-if="store.building" :size="15" class="spinning" />
                <RefreshCw v-else :size="15" />
                {{ store.building
                  ? t('teachingRepresentations.materialSuite.updating', '正在联动生成…')
                  : t('teachingRepresentations.materialSuite.updateAll', '一键更新全部材料') }}
              </button>
            </div>
            <div class="material-suite__grid">
              <button
                v-for="item in selectableTypes"
                :key="`suite:${item.representation_type}`"
                type="button"
                :data-status="item.status"
                :aria-pressed="selected.representation_type === item.representation_type"
                @click="selectType(item.representation_type)"
              >
                <span>{{ typeLabel(item.representation_type) }}</span>
                <strong>{{ t('teachingRepresentations.materialSuite.connected', '同源已连接') }}</strong>
                <small>{{ statusLabel(item) }} · {{ t('teachingRepresentations.materialSuite.traceable', '可追溯到课程结构') }}</small>
              </button>
            </div>
          </section>

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
              <button
                type="button"
                class="material-edit-trigger"
                :aria-label="t('teachingRepresentations.materialEdit.editObjective', '编辑学习目标并联动')"
                @click="openMaterialEdit(unit)"
              >
                <PencilLine :size="14" />
                {{ t('teachingRepresentations.materialEdit.editAndSync', '编辑并联动') }}
              </button>
            </article>
          </div>

          <div v-else class="units-preview">
            <article v-for="unit in content.units || []" :key="unit.unit_id" :class="{ stale: isStale(unit.unit_id) }">
              <header>
                <strong>{{ unit.title || unit.section_title || unit.prompt }}</strong>
                <div>
                  <span v-if="unit.duration_minutes">{{ unit.duration_minutes }} min</span>
                  <button
                    v-if="materialUnitEdit(unit)"
                    type="button"
                    class="material-edit-trigger"
                    :aria-label="t('teachingRepresentations.materialEdit.editContent', '编辑当前材料并联动')"
                    @click="openMaterialEdit(unit)"
                  >
                    <PencilLine :size="14" />
                    {{ t('teachingRepresentations.materialEdit.editAndSync', '编辑并联动') }}
                  </button>
                </div>
              </header>
              <p v-if="unit.learning_objective">{{ unit.learning_objective }}</p>
              <p v-if="selected.representation_type === 'handout' && unit.blocks?.[0]?.markdown" class="handout-body">
                {{ unit.blocks[0].markdown }}
              </p>
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

    <Teleport to="body">
      <div v-if="materialEditorOpen" class="material-editor-shell" @click.self="closeMaterialEditor">
        <section class="material-editor" role="dialog" :aria-modal="materialEditorOpen" :aria-label="t('teachingRepresentations.materialEdit.dialogTitle', '编辑教学材料并分析联动')">
          <header>
            <div>
              <small>{{ t('teachingRepresentations.materialEdit.eyebrow', '结构化同源 · 上游可编辑') }}</small>
              <h2>{{ materialEditorTitle }}</h2>
              <p>{{ t('teachingRepresentations.materialEdit.description', '修改会先形成影响预览；教师确认后，系统只更新共享同一来源的材料。') }}</p>
            </div>
            <button type="button" :disabled="materialEditBusy" :aria-label="t('common.close', '关闭')" @click="closeMaterialEditor">
              <X :size="18" />
            </button>
          </header>
          <div class="material-editor__body">
            <article>
              <small>{{ t('teachingRepresentations.materialEdit.before', '当前内容') }}</small>
              <p>{{ materialEditBefore }}</p>
            </article>
            <label>
              <span>{{ t('teachingRepresentations.materialEdit.after', '修改后的内容') }}</span>
              <textarea v-model="materialEditAfter" rows="7" />
            </label>
            <div class="material-editor__guard">
              <GitBranch :size="16" />
              <span>{{ t('teachingRepresentations.materialEdit.guard', '分析阶段不会修改课程；确认后才写入课程真源。') }}</span>
            </div>
          </div>
          <footer>
            <button type="button" :disabled="materialEditBusy" @click="closeMaterialEditor">
              {{ t('common.cancel', '取消') }}
            </button>
            <button
              type="button"
              class="primary"
              :disabled="materialEditBusy || !materialEditChanged"
              @click="previewMaterialEdit"
            >
              <LoaderCircle v-if="materialEditBusy" :size="15" class="spinning" />
              <ScanSearch v-else :size="15" />
              {{ t('teachingRepresentations.materialEdit.analyze', '分析联动影响') }}
            </button>
          </footer>
        </section>
      </div>
    </Teleport>

    <TeachingImpactDialog
      :open="impactDialogOpen"
      :preview="impactPreview"
      :proposal-item="pendingMaterialItem"
      :receipt="syncReceipt"
      :before-text="materialEditBefore"
      :after-text="materialEditAfter"
      :source-type="materialEditSourceType"
      :allow-local="false"
      :busy="materialEditBusy"
      :syncing="materialSyncing"
      @close="closeImpactDialog"
      @propose="proposeMaterialEdit"
      @confirm="confirmMaterialEdit"
      @reject="rejectMaterialEdit"
    />
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ClipboardList, Clock3, GitBranch, Layers3, ListTree, LoaderCircle, Network, PencilLine, RefreshCw, ScanSearch, X } from 'lucide-vue-next'
import { useTeachingRepresentationsStore, type RepresentationType, type TeachingRepresentation } from '../stores/teachingRepresentations'
import { useChangeProposalsStore } from '../stores/changeProposals'
import type { ChangeProposal, ChangeProposalItem } from '../types/changeProposal'
import { t } from '../shared/i18n'
import CourseWorkspaceTabs from './CourseWorkspaceTabs.vue'
import DiagramSpecRenderer from './DiagramSpecRenderer.vue'
import TeachingImpactDialog from './TeachingImpactDialog.vue'
const props = withDefaults(defineProps<{
  visible: boolean
  courseId: string
  activeType?: 'outline' | 'lesson_plan'
  overviewMode?: boolean
  practiceAvailable?: boolean
  practiceRepairAvailable?: boolean
}>(), {
  activeType: 'outline',
  overviewMode: false,
  practiceAvailable: false,
  practiceRepairAvailable: false,
})

const emit = defineEmits<{
  (event: 'close' | 'outline' | 'lesson-plan' | 'course' | 'practice' | 'ppt'): void
}>()

const store = useTeachingRepresentationsStore()
const changeProposalsStore = useChangeProposalsStore()
const selected = computed(() => store.selectedRepresentation)
const content = computed(() => store.selectedSpec?.payload?.content || null)
const materialEditorOpen = ref(false)
const materialEditUnit = ref<Record<string, any> | null>(null)
const materialEditField = ref('')
const materialEditBefore = ref('')
const materialEditAfter = ref('')
const materialEditBusy = ref(false)
const materialSyncing = ref(false)
const impactDialogOpen = ref(false)
const impactPreview = ref<Record<string, any> | null>(null)
const inlineMaterialProposal = ref<ChangeProposal | null>(null)
const syncReceipt = ref<Record<string, any> | null>(null)
const materialEditRepresentationId = ref('')
const materialEditSourceType = ref<RepresentationType>('outline')
const pendingMaterialItem = computed<ChangeProposalItem | null>(() => (
  inlineMaterialProposal.value?.items.find(item => item.status === 'pending') || null
))
const materialEditChanged = computed(() => (
  materialEditAfter.value.trim().length > 0
  && materialEditAfter.value.trim() !== materialEditBefore.value.trim()
))
const materialEditorTitle = computed(() => (
  t('teachingRepresentations.materialEdit.titleTemplate', '修改{material}，联动更新相关材料')
    .replace('{material}', typeLabel(materialEditSourceType.value))
))
const workspaceTitle = computed(() => (
  props.overviewMode
    ? t('teachingRepresentations.materialSuite.workspaceTitle', '教学材料一键生成')
    :
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

function materialUnitEdit(unit: Record<string, any>) {
  const type = selected.value?.representation_type
  if (type === 'lesson_plan') {
    return { field: 'learning_objective', value: String(unit.learning_objective || '') }
  }
  if (type === 'handout') {
    return { field: 'body', value: String(unit.blocks?.[0]?.markdown || '') }
  }
  if (type === 'practice_sheet') {
    return { field: 'prompt', value: String(unit.prompt || '') }
  }
  return null
}

function openMaterialEdit(unit: Record<string, any>) {
  const representation = selected.value
  if (!representation) return
  const editable = representation.representation_type === 'outline'
    ? { field: 'learning_objective', value: String(unit.learning_objective || '') }
    : materialUnitEdit(unit)
  if (!editable?.value) return
  materialEditUnit.value = unit
  materialEditField.value = editable.field
  materialEditBefore.value = editable.value
  materialEditAfter.value = editable.value
  materialEditRepresentationId.value = representation.representation_id
  materialEditSourceType.value = representation.representation_type
  impactPreview.value = null
  inlineMaterialProposal.value = null
  syncReceipt.value = null
  impactDialogOpen.value = false
  materialEditorOpen.value = true
}

function closeMaterialEditor() {
  if (!materialEditBusy.value) materialEditorOpen.value = false
}

async function previewMaterialEdit() {
  const unit = materialEditUnit.value
  if (!unit || !materialEditChanged.value) return
  materialEditBusy.value = true
  try {
    impactPreview.value = await store.previewEdit(materialEditRepresentationId.value, {
      unit_id: String(unit.unit_id),
      field: materialEditField.value,
      before: materialEditBefore.value,
      after: materialEditAfter.value,
      semantic_intent: true,
    })
    materialEditorOpen.value = false
    impactDialogOpen.value = true
  } finally {
    materialEditBusy.value = false
  }
}

async function proposeMaterialEdit() {
  const unit = materialEditUnit.value
  if (!unit) return
  materialEditBusy.value = true
  try {
    const result = await store.applyEdit(materialEditRepresentationId.value, {
      unit_id: String(unit.unit_id),
      field: materialEditField.value,
      before: materialEditBefore.value,
      after: materialEditAfter.value,
      decision: 'course_semantic',
      semantic_intent: true,
    })
    await changeProposalsStore.fetchChangeProposals(props.courseId)
    inlineMaterialProposal.value = changeProposalsStore.findProposal(result.authoring_change?.proposal_id)
      || result.authoring_change
      || null
  } finally {
    materialEditBusy.value = false
  }
}

async function confirmMaterialEdit() {
  const proposal = inlineMaterialProposal.value
  const item = pendingMaterialItem.value
  if (!proposal || !item) return
  materialEditBusy.value = true
  materialSyncing.value = true
  try {
    const result = await changeProposalsStore.applyItem(proposal.proposal_id, item.item_id)
    await store.load(props.courseId)
    await store.select(materialEditRepresentationId.value)
    inlineMaterialProposal.value = null
    syncReceipt.value = result?.representation_sync || null
    impactDialogOpen.value = true
  } finally {
    materialSyncing.value = false
    materialEditBusy.value = false
  }
}

async function rejectMaterialEdit() {
  const proposal = inlineMaterialProposal.value
  const item = pendingMaterialItem.value
  if (!proposal || !item) return
  materialEditBusy.value = true
  try {
    await changeProposalsStore.rejectItem(proposal.proposal_id, item.item_id)
    inlineMaterialProposal.value = null
    impactDialogOpen.value = false
  } finally {
    materialEditBusy.value = false
  }
}

function closeImpactDialog() {
  if (!materialSyncing.value) impactDialogOpen.value = false
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
.material-suite {
  margin:0 0 24px;
  padding:20px;
  border:1px solid #dfe4f5;
  border-radius:18px;
  background:
    radial-gradient(circle at 88% 4%,rgba(99,102,241,.12),transparent 34%),
    linear-gradient(135deg,#f8f9ff,#fff);
  box-shadow:0 14px 36px rgba(49,46,129,.07);
}
.material-suite__heading { display:flex; align-items:flex-start; justify-content:space-between; gap:20px; }
.material-suite__heading small { color:#5b56d7; font-size:9px; font-weight:800; letter-spacing:.08em; }
.material-suite__heading h3 { margin:5px 0 0; color:#182033; font-size:18px; }
.material-suite__heading p { max-width:620px; margin:7px 0 0; color:#667085; font-size:11px; line-height:1.6; }
.material-suite__heading button {
  min-height:38px;
  flex:0 0 auto;
  display:inline-flex;
  align-items:center;
  gap:7px;
  padding:0 13px;
  border:0;
  border-radius:10px;
  color:#fff;
  background:#4f46e5;
  box-shadow:0 8px 18px rgba(79,70,229,.2);
  font-size:11px;
  font-weight:750;
  cursor:pointer;
}
.material-suite__heading button:disabled { opacity:.55; cursor:wait; }
.material-suite__grid { display:grid; grid-template-columns:repeat(6,minmax(0,1fr)); gap:8px; margin-top:17px; }
.material-suite__grid button {
  min-width:0;
  display:flex;
  flex-direction:column;
  align-items:flex-start;
  padding:11px;
  border:1px solid #e3e6ef;
  border-radius:11px;
  color:#475467;
  background:rgba(255,255,255,.86);
  cursor:pointer;
  text-align:left;
}
.material-suite__grid button[aria-pressed="true"] { border-color:#8983f0; background:#f1f0ff; box-shadow:0 0 0 2px rgba(79,70,229,.08); }
.material-suite__grid button[data-status="stale"] { border-color:#f4cf73; background:#fffaf0; }
.material-suite__grid span { font-size:10px; font-weight:750; }
.material-suite__grid strong { margin-top:7px; color:#1f2937; font-size:12px; line-height:1.2; }
.material-suite__grid small { margin-top:5px; overflow:hidden; color:#8490a2; font-size:8px; text-overflow:ellipsis; white-space:nowrap; }
.representations-empty button { min-height:36px; display:inline-flex; align-items:center; gap:7px; padding:0 12px; border:1px solid #c7d2fe; border-radius:8px; color:var(--lz-brand-strong); background:#fff; cursor:pointer; }
.stale-notice { display:flex; align-items:center; gap:8px; margin:0 0 18px; padding:10px 12px; border-left:3px solid #f59e0b; color:#92400e; background:#fffbeb; font-size:11px; }
.outline-preview article,.units-preview article { position:relative; display:grid; grid-template-columns:34px minmax(0,1fr) auto; align-items:center; gap:12px; padding:17px 0; border-bottom:1px solid #edf0f5; }
.outline-preview article > span { color:#a5b4fc; font:700 11px ui-monospace,monospace; }
.outline-preview strong,.units-preview strong { font-size:13px; }
.outline-preview p,.units-preview p { margin:4px 0 0; color:var(--lz-text-secondary); font-size:11px; line-height:1.6; }
.stale::after { content:""; position:absolute; inset:7px auto 7px -10px; width:3px; border-radius:3px; background:#f59e0b; }
.units-preview article { display:block; }
.units-preview article header { display:flex; align-items:center; justify-content:space-between; gap:12px; }
.units-preview article header > div { display:flex; align-items:center; gap:8px; }
.material-edit-trigger {
  min-height:30px;
  display:inline-flex;
  align-items:center;
  gap:6px;
  padding:0 10px;
  border:1px solid #d9dcf7;
  border-radius:8px;
  color:#5146ce;
  background:#f6f5ff;
  font-size:10px;
  font-weight:750;
  cursor:pointer;
  white-space:nowrap;
}
.material-edit-trigger:hover { border-color:#9d97ed; background:#eeecff; }
.handout-body {
  max-height:96px;
  overflow:hidden;
  white-space:pre-wrap;
  mask-image:linear-gradient(#000 65%,transparent);
}
.units-preview ol { margin:10px 0 0; padding:0; list-style:none; }
.units-preview li { display:grid; grid-template-columns:64px minmax(0,1fr); gap:8px; padding:5px 0; color:var(--lz-text-secondary); font-size:10px; }
.units-preview li b { color:var(--lz-brand-strong); }
.representations-loading,.representations-empty { width:100%; height:100%; min-height:0; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:10px; color:var(--lz-text-muted); }
.representations-loading { grid-row:2; }
.representations-empty strong { color:var(--lz-text-secondary); font-size:13px; }
.material-editor-shell {
  position:fixed;
  inset:0;
  z-index:10030;
  display:grid;
  place-items:center;
  padding:20px;
  background:rgba(10,16,28,.68);
  backdrop-filter:blur(12px);
}
.material-editor {
  width:min(760px,calc(100vw - 40px));
  max-height:calc(100dvh - 40px);
  display:grid;
  grid-template-rows:auto minmax(0,1fr) auto;
  overflow:hidden;
  border:1px solid rgba(255,255,255,.4);
  border-radius:20px;
  color:#172033;
  background:#fff;
  box-shadow:0 28px 90px rgba(0,0,0,.34);
}
.material-editor > header {
  display:flex;
  align-items:flex-start;
  justify-content:space-between;
  gap:20px;
  padding:22px 24px;
  color:#fff;
  background:linear-gradient(120deg,#172033,#243553);
}
.material-editor > header small { color:#aebbf7; font-size:9px; font-weight:800; letter-spacing:.11em; }
.material-editor > header h2 { margin:5px 0 0; font-size:22px; }
.material-editor > header p { margin:7px 0 0; color:#b9c3d1; font-size:11px; line-height:1.5; }
.material-editor > header button {
  width:36px;
  height:36px;
  display:grid;
  place-items:center;
  border:1px solid rgba(255,255,255,.14);
  border-radius:10px;
  color:#d6dce7;
  background:rgba(255,255,255,.06);
  cursor:pointer;
}
.material-editor__body { min-height:0; display:grid; gap:16px; overflow:auto; padding:22px 24px; }
.material-editor__body article { padding:14px 16px; border:1px solid #e2e6ed; border-radius:12px; background:#f7f9fc; }
.material-editor__body article small,.material-editor__body label span { display:block; color:#7a8798; font-size:10px; font-weight:750; }
.material-editor__body article p { max-height:108px; margin:7px 0 0; overflow:auto; color:#344054; font-size:12px; line-height:1.65; white-space:pre-wrap; }
.material-editor__body textarea {
  width:100%;
  margin-top:7px;
  padding:13px 14px;
  resize:vertical;
  border:1px solid #cfd5df;
  border-radius:11px;
  color:#172033;
  background:#fff;
  font:12px/1.65 inherit;
  outline:none;
}
.material-editor__body textarea:focus { border-color:#6d64df; box-shadow:0 0 0 3px rgba(79,70,229,.1); }
.material-editor__guard { display:flex; align-items:center; gap:8px; color:#5b5fc7; font-size:10px; }
.material-editor > footer { display:flex; justify-content:flex-end; gap:10px; padding:15px 24px 20px; border-top:1px solid #edf0f4; }
.material-editor > footer button {
  min-height:38px;
  display:inline-flex;
  align-items:center;
  gap:7px;
  padding:0 15px;
  border:1px solid #d9dee7;
  border-radius:9px;
  color:#475467;
  background:#fff;
  font-size:11px;
  font-weight:750;
  cursor:pointer;
}
.material-editor > footer button.primary { border-color:#4f46e5; color:#fff; background:#4f46e5; }
.material-editor > footer button:disabled { opacity:.5; cursor:not-allowed; }
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
  .material-suite__heading { flex-direction:column; }
  .material-suite__grid { grid-template-columns:repeat(2,minmax(0,1fr)); }
}
</style>
