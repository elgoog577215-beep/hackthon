<template>
  <section class="outline-review" :aria-label="t('courseGeneration.outlineReview.ariaLabel', '课程目录确认')">
    <article class="outline-review__sheet">
      <header class="outline-review__header">
        <div>
          <span class="outline-review__eyebrow">
            <CircleCheckBig :size="14" />
            {{ t('courseGeneration.outlineReview.eyebrow', '需要你的判断') }}
          </span>
          <h1>{{ t('courseGeneration.outlineReview.title', '确认这门课怎样展开') }}</h1>
          <p>{{ t('courseGeneration.outlineReview.help', '只检查课程名称、章节顺序和学习目标。确认后，教案与正文会沿用这份结构在当前页面继续生长。') }}</p>
        </div>
        <span class="outline-review__count">
          {{ t('courseGeneration.outlineReview.sectionCount', '{count} 个目录节点').replace('{count}', String(blueprintNodes.length)) }}
        </span>
      </header>

      <div v-if="loading" class="outline-review__loading" aria-live="polite">
        <LoaderCircle :size="18" />
        <span>{{ t('courseGeneration.outlineReview.loading', '正在载入可编辑目录') }}</span>
      </div>

      <div v-else-if="loadError" class="outline-review__load-error" role="alert">
        <TriangleAlert :size="17" />
        <div>
          <strong>{{ loadError }}</strong>
          <p>{{ t('courseGeneration.outlineReview.loadErrorHelp', '已生成结果仍然保留，重新载入不会重复创建课程。') }}</p>
        </div>
        <button type="button" @click="loadBlueprint">{{ t('courseGeneration.outlineReview.retry', '重试') }}</button>
      </div>

      <template v-else>
        <label class="outline-review__course-name">
          <span>{{ t('courseWorkspace.blueprint.courseName', '课程名称') }}</span>
          <input v-model="blueprintDraft.course_name" type="text" :placeholder="courseName" />
        </label>

        <ol class="outline-review__nodes">
          <li
            v-for="(node, index) in blueprintNodes"
            :key="node.node_id || index"
            :data-level="node.node_level || 2"
          >
            <span class="outline-review__index">{{ String(index + 1).padStart(2, '0') }}</span>
            <span class="outline-review__branch" aria-hidden="true"></span>
            <div>
              <input
                v-model="node.node_name"
                type="text"
                :aria-label="t('courseTasks.blueprint.nodeName', '章节名称')"
              />
              <textarea
                v-if="Number(node.node_level || 2) >= 2 || 'learning_objective' in node"
                v-model="node.learning_objective"
                rows="1"
                :placeholder="t('courseGeneration.outlineReview.objectivePlaceholder', '写清这一节结束后，学习者能够做到什么')"
                :aria-label="t('courseTasks.blueprint.objective', '学习目标')"
              />
            </div>
          </li>
        </ol>

        <p v-if="!blueprintNodes.length" class="outline-review__empty">
          {{ t('courseGeneration.outlineReview.empty', '目录尚未形成，请重新载入后再确认。') }}
        </p>
      </template>

      <footer class="outline-review__footer">
        <div>
          <strong>{{ footerTitle }}</strong>
          <p>{{ t('courseGeneration.outlineReview.guard', '这是生成过程中唯一需要编辑结构的确认点；后续只在发布前做最终确认。') }}</p>
          <p v-if="actionError" class="outline-review__action-error">{{ actionError }}</p>
        </div>
        <div class="outline-review__actions">
          <button
            type="button"
            class="secondary"
            :disabled="loading || acting || !dirty || !blueprintNodes.length"
            @click="saveDraft"
          >
            <LoaderCircle v-if="saving" :size="15" />
            <Save v-else :size="15" />
            {{ saving
              ? t('courseGeneration.outlineReview.saving', '保存中')
              : dirty
                ? t('courseGeneration.outlineReview.save', '保存修改')
                : t('courseGeneration.outlineReview.saved', '修改已保存') }}
          </button>
          <button
            type="button"
            class="primary"
            :disabled="loading || acting || !blueprintNodes.length"
            @click="confirmOutline"
          >
            <LoaderCircle v-if="confirming" :size="15" />
            <ArrowRight v-else :size="15" />
            {{ t('courseGeneration.gate.confirmOutline', '确认目录并继续') }}
          </button>
        </div>
      </footer>
    </article>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ArrowRight, CircleCheckBig, LoaderCircle, Save, TriangleAlert } from 'lucide-vue-next'
import { ElMessage } from 'element-plus'
import type { Node, Task } from '../stores/types'
import { useCourseStore } from '../stores/course'
import { useCourseWorkspaceStore } from '../stores/courseWorkspace'
import { useGenerationStore } from '../stores/generation'
import { t } from '../shared/i18n'

const props = withDefaults(defineProps<{
  courseId: string
  courseName?: string
  nodes?: Node[]
  task?: Task
}>(), {
  courseName: '',
  nodes: () => [],
  task: undefined,
})

const emit = defineEmits<{
  (event: 'confirmed'): void
}>()

const courseStore = useCourseStore()
const workspace = useCourseWorkspaceStore()
const generationStore = useGenerationStore()
const blueprintDraft = ref<Record<string, any>>({})
const baseline = ref('')
const loading = ref(false)
const saving = ref(false)
const confirming = ref(false)
const loadError = ref('')
const actionError = ref('')

const acting = computed(() => saving.value || confirming.value)
const blueprintNodes = computed<any[]>(() => (
  Array.isArray(blueprintDraft.value?.nodes)
    ? blueprintDraft.value.nodes
    : Array.isArray(blueprintDraft.value?.course_blueprint?.nodes)
      ? blueprintDraft.value.course_blueprint.nodes
      : []
))
const draftSignature = computed(() => JSON.stringify({
  course_name: blueprintDraft.value?.course_name || '',
  nodes: blueprintNodes.value.map(node => ({
    node_id: node.node_id,
    node_name: node.node_name,
    node_level: node.node_level,
    learning_objective: node.learning_objective || '',
  })),
}))
const dirty = computed(() => Boolean(baseline.value && draftSignature.value !== baseline.value))
const footerTitle = computed(() => {
  if (confirming.value) return t('courseGeneration.outlineReview.confirming', '正在确认目录')
  if (saving.value) return t('courseGeneration.outlineReview.savingChanges', '正在保存修改')
  if (dirty.value) return t('courseGeneration.outlineReview.unsaved', '有未保存的修改')
  const progress = Math.max(0, Math.min(100, Math.round(Number(props.task?.progress || 0))))
  return t('courseGeneration.outlineReview.ready', '目录已就绪 · 当前生产进度 {progress}%')
    .replace('{progress}', String(progress))
})

onMounted(loadBlueprint)
watch(() => props.courseId, (courseId, previous) => {
  if (courseId && courseId !== previous) void loadBlueprint()
})

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value))
}

function seedNodesFromCourse() {
  if (blueprintNodes.value.length || !props.nodes.length) return
  blueprintDraft.value.nodes = props.nodes
    .filter(node => node.node_level <= 2)
    .map(node => ({
      node_id: node.node_id,
      parent_node_id: node.parent_node_id,
      node_name: node.node_name,
      node_level: node.node_level,
      learning_objective: node.learning_objective || '',
    }))
}

async function loadBlueprint() {
  if (!props.courseId || loading.value) return
  loading.value = true
  loadError.value = ''
  actionError.value = ''
  try {
    const data = await workspace.loadBlueprint(props.courseId)
    blueprintDraft.value = clone(data.draft || data.current || data || {})
    seedNodesFromCourse()
    if (!blueprintDraft.value.course_name) blueprintDraft.value.course_name = props.courseName
    baseline.value = draftSignature.value
  } catch {
    loadError.value = t('courseGeneration.gate.loadFailed', '当前确认内容读取失败，请稍后重试。')
  } finally {
    loading.value = false
  }
}

function draftPayload() {
  const draft = blueprintDraft.value
  return {
    base_blueprint_revision_id: draft.base_blueprint_revision_id,
    course_name: draft.course_name,
    course_purpose: draft.course_purpose,
    course_blueprint: draft.course_blueprint,
    nodes: draft.nodes,
    learning_asset_plan: draft.learning_asset_plan,
    blueprint_locks: draft.blueprint_locks || {},
  }
}

async function persistDraft(showMessage = true) {
  if (!blueprintNodes.value.length) return
  const result = await workspace.saveBlueprint(props.courseId, draftPayload())
  if (result?.draft) blueprintDraft.value = clone(result.draft)
  baseline.value = draftSignature.value
  if (showMessage) ElMessage.success(t('courseGeneration.outlineReview.savedMessage', '目录修改已保存'))
}

async function saveDraft() {
  if (!dirty.value || acting.value) return
  saving.value = true
  actionError.value = ''
  try {
    await persistDraft()
  } catch {
    actionError.value = t('courseGeneration.outlineReview.saveFailed', '目录修改保存失败，请检查后重试。')
  } finally {
    saving.value = false
  }
}

async function confirmOutline() {
  if (!blueprintNodes.value.length || acting.value) return
  confirming.value = true
  actionError.value = ''
  try {
    if (dirty.value) await persistDraft(false)
    await workspace.confirmGenerationStep(props.courseId, 'outline')
    generationStore.startGlobalMonitor()
    await courseStore.refreshCourseData(props.courseId)
    ElMessage.success(t('courseGeneration.gate.confirmed', '已确认，课程继续生成'))
    emit('confirmed')
  } catch {
    actionError.value = t('courseGeneration.gate.confirmFailed', '确认失败，请检查目录后重试。')
  } finally {
    confirming.value = false
  }
}
</script>

<style scoped>
.outline-review {
  min-height:0;
  flex:1;
  display:flex;
  overflow:hidden;
  padding:10px clamp(14px,2.5vw,28px) 16px;
  background:#f6f7f9;
}
.outline-review__sheet {
  width:min(1040px,100%);
  height:100%;
  min-height:0;
  display:grid;
  grid-template-rows:auto auto minmax(0,1fr) auto;
  margin:0 auto;
  overflow:hidden;
  border:1px solid #dde1e8;
  border-radius:10px;
  background:#fff;
  box-shadow:0 8px 22px rgba(30,41,59,.05);
}
.outline-review__header {
  display:flex;
  align-items:flex-start;
  justify-content:space-between;
  gap:16px;
  padding:13px 20px 11px;
  border-bottom:1px solid #e7e9ee;
}
.outline-review__eyebrow {
  display:inline-flex;
  align-items:center;
  gap:7px;
  color:#087a5b;
  font-size:9px;
  font-weight:850;
  letter-spacing:.08em;
}
.outline-review__header h1 {
  margin:3px 0;
  color:#182230;
  font:720 clamp(20px,1.65vw,24px)/1.18 var(--font-sans);
  letter-spacing:-.015em;
}
.outline-review__header p {
  max-width:660px;
  margin:0;
  color:#687386;
  font-size:11px;
  line-height:1.4;
}
.outline-review__count {
  flex:0 0 auto;
  padding:5px 8px;
  border:1px solid #d9e5e0;
  border-radius:999px;
  color:#26715d;
  background:#f2faf7;
  font-size:9px;
  font-weight:750;
}
.outline-review__loading,
.outline-review__load-error {
  grid-row:2/4;
  min-height:260px;
  display:flex;
  align-items:center;
  justify-content:center;
  gap:9px;
  padding:30px;
  color:#687386;
  font-size:11px;
}
.outline-review__loading svg {
  color:#4f46d9;
  animation:outline-review-spin .9s linear infinite;
}
.outline-review__load-error {
  min-height:150px;
  color:#9a4d13;
}
.outline-review__load-error > div { max-width:520px; }
.outline-review__load-error p { margin:3px 0 0; color:#84664c; font-size:9px; }
.outline-review__load-error button {
  min-height:32px;
  padding:0 11px;
  border:1px solid #e2a753;
  border-radius:7px;
  color:#9a4d13;
  background:#fffaf0;
  font-size:9px;
  font-weight:800;
  cursor:pointer;
}
.outline-review__course-name {
  display:grid;
  grid-template-columns:84px minmax(0,1fr);
  align-items:center;
  gap:10px;
  margin:0 20px;
  padding:7px 0 6px;
  border-bottom:1px solid #eceef2;
}
.outline-review__course-name span {
  color:#7b8494;
  font-size:9px;
  font-weight:750;
}
.outline-review input,
.outline-review textarea {
  width:100%;
  border:1px solid transparent;
  border-radius:7px;
  color:#273144;
  background:transparent;
  outline:none;
  transition:border-color .16s ease,background .16s ease,box-shadow .16s ease;
}
.outline-review input:hover,
.outline-review textarea:hover { background:#f8f9fb; }
.outline-review input:focus,
.outline-review textarea:focus {
  border-color:#aeb4e9;
  background:#fff;
  box-shadow:0 0 0 3px rgba(79,70,217,.08);
}
.outline-review__course-name input {
  height:28px;
  padding:0 8px;
  font-size:12px;
  font-weight:780;
}
.outline-review__nodes {
  display:grid;
  min-height:0;
  overflow:auto;
  margin:0;
  padding:3px 20px 10px;
  list-style:none;
}
.outline-review__nodes li {
  position:relative;
  display:grid;
  grid-template-columns:28px 11px minmax(0,1fr);
  gap:6px;
  padding:5px 0;
  border-bottom:1px solid #eef0f3;
}
.outline-review__nodes li:last-child { border-bottom:0; }
.outline-review__nodes li[data-level="1"] { margin-top:2px; }
.outline-review__index {
  padding-top:6px;
  color:#969eac;
  font:700 9px/1 ui-monospace,SFMono-Regular,monospace;
}
.outline-review__branch {
  width:8px;
  height:8px;
  margin-top:5px;
  border:1.5px solid #8f96a5;
  border-radius:50%;
  background:#fff;
}
.outline-review__nodes li[data-level="1"] .outline-review__branch {
  width:10px;
  height:10px;
  margin-top:4px;
  border:0;
  border-radius:3px;
  background:#4f5b70;
}
.outline-review__nodes input {
  height:25px;
  padding:0 6px;
  font-size:11px;
  font-weight:750;
}
.outline-review__nodes li[data-level="1"] input {
  color:#182230;
  font-size:12px;
}
.outline-review__nodes textarea {
  height:26px;
  min-height:26px;
  margin-top:1px;
  padding:4px 6px;
  resize:vertical;
  color:#687386;
  font-size:9px;
  line-height:1.35;
}
.outline-review__empty {
  grid-row:3;
  margin:0;
  padding:42px 30px;
  color:#8a93a3;
  text-align:center;
  font-size:10px;
}
.outline-review__footer {
  grid-row:4;
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:16px;
  padding:7px 12px 7px 20px;
  border-top:1px solid #dfe3e9;
  background:#fafbfc;
}
.outline-review__footer > div:first-child { min-width:0; }
.outline-review__footer strong { color:#344054; font-size:10px; }
.outline-review__footer p { margin:2px 0 0; color:#7b8494; font-size:8px; line-height:1.45; }
.outline-review__footer p.outline-review__action-error { color:#b42318; }
.outline-review__actions {
  flex:0 0 auto;
  display:flex;
  gap:8px;
}
.outline-review__actions button {
  min-height:32px;
  display:inline-flex;
  align-items:center;
  justify-content:center;
  gap:7px;
  padding:0 13px;
  border-radius:8px;
  font-size:9px;
  font-weight:800;
  cursor:pointer;
}
.outline-review__actions button:disabled { opacity:.5; cursor:not-allowed; }
.outline-review__actions .secondary {
  border:1px solid #d5dae3;
  color:#596579;
  background:#fff;
}
.outline-review__actions .primary {
  border:1px solid #3f47a8;
  color:#fff;
  background:#3f47a8;
}
.outline-review__actions svg.lucide-loader-circle { animation:outline-review-spin .9s linear infinite; }
@keyframes outline-review-spin { to { transform:rotate(360deg); } }
@media (max-width:767px) {
  .outline-review { padding:6px 5px 12px; }
  .outline-review__sheet { border-radius:10px; }
  .outline-review__header { display:grid; gap:6px; padding:12px 12px 10px; }
  .outline-review__count { justify-self:start; }
  .outline-review__course-name { grid-template-columns:1fr; gap:2px; margin:0 12px; padding:7px 0 6px; }
  .outline-review__nodes { padding:3px 12px 9px; }
  .outline-review__nodes li { grid-template-columns:25px 11px minmax(0,1fr); gap:5px; }
  .outline-review__footer { align-items:stretch; flex-direction:column; gap:6px; padding:8px 10px 10px; }
  .outline-review__actions { display:grid; grid-template-columns:.85fr 1.15fr; }
  .outline-review__actions button { padding:0 9px; }
}
@media (prefers-reduced-motion:reduce) {
  .outline-review__loading svg,
  .outline-review__actions svg { animation:none!important; }
}
</style>
