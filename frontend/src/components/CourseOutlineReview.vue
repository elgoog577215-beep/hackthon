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
        <div class="outline-review__setup">
          <label class="outline-review__course-name">
            <span>{{ t('courseWorkspace.blueprint.courseName', '课程名称') }}</span>
            <input v-model="blueprintDraft.course_name" type="text" :placeholder="courseName" />
          </label>

          <section v-if="isProjectCourse" class="outline-review__starting-point" :data-status="startingProfileStatus">
            <header>
              <span>{{ t('courseGeneration.outlineReview.startingPoint', '你的项目起点（暂定）') }}</span>
              <strong>{{ startingProfileStatusLabel }}</strong>
            </header>
            <div>
              <p>
                <small>{{ t('courseGeneration.outlineReview.deliverable', '最终交付物') }}</small>
                <span>{{ projectDeliverable || t('courseGeneration.outlineReview.deliverablePending', '按项目目标确定') }}</span>
              </p>
              <p>
                <small>{{ t('courseGeneration.outlineReview.experience', '已有经验') }}</small>
                <span>{{ startingStrengths || t('courseGeneration.outlineReview.notProvided', '暂未提供') }}</span>
              </p>
              <p>
                <small>{{ t('courseGeneration.outlineReview.focusAreas', '重点补充') }}</small>
                <span>{{ startingFocus || t('courseGeneration.outlineReview.discoverInProject', '将在项目过程中继续识别') }}</span>
              </p>
            </div>
            <footer>{{ t('courseGeneration.outlineReview.startingPointGuard', '起点来自你的自述，只用于安排第一版路径，不等同于已经掌握。') }}</footer>
          </section>
        </div>

        <ol class="outline-review__nodes">
          <li
            v-for="(node, index) in blueprintNodes"
            :key="node.node_id || index"
            :data-level="node.node_level || 2"
          >
            <span class="outline-review__index">{{ String(index + 1).padStart(2, '0') }}</span>
            <span class="outline-review__branch" aria-hidden="true"></span>
            <div>
              <div v-if="node.learning_path_role" class="outline-review__node-meta">
                <span :data-role="normalizedPathRole(node.learning_path_role)">
                  {{ pathRoleLabel(node.learning_path_role) }}
                </span>
                <p v-if="node.path_reason">{{ node.path_reason }}</p>
              </div>
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
          <p>{{ t('courseGeneration.outlineReview.guard', '这是唯一需要编辑课程结构的步骤；下一步还会确认全课教案，再开始生成正文。') }}</p>
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
const isProjectCourse = computed(() => (
  String(blueprintDraft.value?.course_type || props.task?.courseType || '') === 'project'
))
const courseIntent = computed<Record<string, any>>(() => blueprintDraft.value?.course_intent || {})
const startingProfile = computed<Record<string, any>>(() => blueprintDraft.value?.learner_starting_profile || {})
const startingProfileStatus = computed(() => String(startingProfile.value.status || 'insufficient'))
const projectDeliverable = computed(() => String(courseIntent.value.expected_deliverable || '').trim())
const startingStrengths = computed(() => listText(startingProfile.value.self_reported_strengths))
const startingFocus = computed(() => listText(startingProfile.value.focus_areas))
const startingProfileStatusLabel = computed(() => startingProfileStatus.value === 'insufficient'
  ? t('courseGeneration.outlineReview.startingPointInsufficient', '起点信息不足')
  : t('courseGeneration.outlineReview.startingPointTentative', '暂定起点'))
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

function listText(value: unknown) {
  if (!Array.isArray(value)) return ''
  return value.map(item => String(item || '').trim()).filter(Boolean).join('；')
}

function normalizedPathRole(value: unknown) {
  const role = String(value || '')
  return ['focus', 'standard', 'compressed', 'verify_in_project', 'milestone'].includes(role)
    ? role
    : 'standard'
}

function pathRoleLabel(value: unknown) {
  const labels = {
    focus: t('courseGeneration.outlineReview.pathRoles.focus', '重点补充'),
    standard: t('courseGeneration.outlineReview.pathRoles.standard', '正常学习'),
    compressed: t('courseGeneration.outlineReview.pathRoles.compressed', '快速通过'),
    verify_in_project: t('courseGeneration.outlineReview.pathRoles.verifyInProject', '项目中验证'),
    milestone: t('courseGeneration.outlineReview.pathRoles.milestone', '项目节点'),
  }
  return labels[normalizedPathRole(value) as keyof typeof labels]
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
      learning_path_role: node.learning_path_role,
      path_reason: node.path_reason,
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
    course_type: draft.course_type,
    course_intent: draft.course_intent,
    learner_starting_profile: draft.learner_starting_profile,
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
  padding:18px clamp(18px,3vw,40px) 26px;
  background:radial-gradient(circle at 88% 2%,rgba(99,102,241,.065),transparent 28%),linear-gradient(180deg,#f8f9fc 0%,#f4f6f9 100%);
}
.outline-review__sheet {
  position:relative;
  width:min(1100px,100%);
  height:100%;
  min-height:0;
  display:grid;
  grid-template-rows:auto auto minmax(0,1fr) auto;
  margin:0 auto;
  overflow:hidden;
  border:1px solid rgba(208,213,223,.88);
  border-radius:16px;
  background:rgba(255,255,255,.98);
  box-shadow:0 18px 48px rgba(30,41,59,.075),0 2px 7px rgba(30,41,59,.035);
}
.outline-review__sheet::before {
  content:"";
  position:absolute;
  z-index:3;
  top:0;
  right:0;
  left:0;
  height:3px;
  background:linear-gradient(90deg,#5963d8,#7a63e4 58%,#9956d9);
}
.outline-review__header {
  display:flex;
  align-items:flex-start;
  justify-content:space-between;
  gap:28px;
  padding:26px 30px 22px;
  border-bottom:1px solid #e7e9ee;
}
.outline-review__eyebrow {
  display:inline-flex;
  align-items:center;
  gap:7px;
  color:#087a5b;
  font-size:12px;
  font-weight:850;
  letter-spacing:.08em;
}
.outline-review__header h1 {
  margin:7px 0 6px;
  color:#182230;
  font:700 clamp(27px,2.6vw,36px)/1.18 Georgia,"Noto Serif SC",serif;
  letter-spacing:-.025em;
}
.outline-review__header p {
  max-width:660px;
  margin:0;
  color:#687386;
  font-size:13px;
  line-height:1.65;
}
.outline-review__count {
  flex:0 0 auto;
  padding:7px 11px;
  border:1px solid #d9e5e0;
  border-radius:999px;
  color:#26715d;
  background:#f2faf7;
  font-size:12px;
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
  font-size:13px;
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
.outline-review__load-error p { margin:4px 0 0; color:#84664c; font-size:12px; }
.outline-review__load-error button {
  min-height:38px;
  padding:0 14px;
  border:1px solid #e2a753;
  border-radius:7px;
  color:#9a4d13;
  background:#fffaf0;
  font-size:12px;
  font-weight:800;
  cursor:pointer;
}
.outline-review__setup {
  min-width:0;
  border-bottom:1px solid #eceef2;
}
.outline-review__course-name {
  display:grid;
  grid-template-columns:100px minmax(0,1fr);
  align-items:center;
  gap:14px;
  margin:0 30px;
  padding:14px 0 12px;
}
.outline-review__course-name span {
  color:#7b8494;
  font-size:12px;
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
  height:36px;
  padding:0 10px;
  font-size:14px;
  font-weight:780;
}
.outline-review__starting-point {
  margin:0 30px;
  padding:13px 0 15px 114px;
  border-top:1px solid #eceef2;
}
.outline-review__starting-point > header {
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:12px;
  margin-bottom:10px;
}
.outline-review__starting-point > header span {
  color:#344054;
  font-size:12px;
  font-weight:800;
}
.outline-review__starting-point > header strong {
  padding:4px 8px;
  border:1px solid #c7dbd2;
  border-radius:5px;
  color:#087a5b;
  background:#f2faf7;
  font-size:10px;
}
.outline-review__starting-point[data-status="insufficient"] > header strong {
  border-color:#e7c790;
  color:#9a5b17;
  background:#fff9ef;
}
.outline-review__starting-point > div {
  display:grid;
  grid-template-columns:repeat(3,minmax(0,1fr));
  gap:16px;
}
.outline-review__starting-point p { min-width:0; margin:0; }
.outline-review__starting-point small {
  display:block;
  margin-bottom:3px;
  color:#8a93a3;
  font-size:10px;
  font-weight:750;
}
.outline-review__starting-point p span {
  display:block;
  overflow-wrap:anywhere;
  color:#455166;
  font-size:11px;
  line-height:1.5;
}
.outline-review__starting-point > footer {
  margin-top:9px;
  color:#7b8494;
  font-size:10px;
  line-height:1.5;
}
.outline-review__nodes {
  display:grid;
  min-height:0;
  overflow:auto;
  margin:0;
  padding:6px 30px 18px;
  list-style:none;
}
.outline-review__nodes li {
  position:relative;
  display:grid;
  grid-template-columns:34px 14px minmax(0,1fr);
  gap:9px;
  padding:10px 0;
  border-bottom:1px solid #eef0f3;
}
.outline-review__nodes li:last-child { border-bottom:0; }
.outline-review__nodes li[data-level="1"] { margin-top:2px; }
.outline-review__index {
  padding-top:8px;
  color:#969eac;
  font:700 11px/1 ui-monospace,SFMono-Regular,monospace;
}
.outline-review__branch {
  width:8px;
  height:8px;
  margin-top:7px;
  border:1.5px solid #8f96a5;
  border-radius:50%;
  background:#fff;
}
.outline-review__nodes li[data-level="1"] .outline-review__branch {
  width:10px;
  height:10px;
  margin-top:6px;
  border:0;
  border-radius:3px;
  background:#4f5b70;
}
.outline-review__node-meta {
  min-width:0;
  display:flex;
  align-items:center;
  gap:8px;
  padding:0 8px 2px;
}
.outline-review__node-meta > span {
  flex:0 0 auto;
  padding:3px 6px;
  border:1px solid #d9dee7;
  border-radius:4px;
  color:#596579;
  background:#f8f9fb;
  font-size:9px;
  font-weight:800;
}
.outline-review__node-meta > span[data-role="focus"] {
  border-color:#e7c790;
  color:#9a5b17;
  background:#fff9ef;
}
.outline-review__node-meta > span[data-role="compressed"] {
  border-color:#bfd7cc;
  color:#087a5b;
  background:#f2faf7;
}
.outline-review__node-meta > span[data-role="verify_in_project"] {
  border-color:#c8c9ed;
  color:#4f55b5;
  background:#f4f4ff;
}
.outline-review__node-meta > span[data-role="milestone"] {
  border-color:#b9c7db;
  color:#35506f;
  background:#f3f7fb;
}
.outline-review__node-meta p {
  min-width:0;
  overflow:hidden;
  margin:0;
  color:#7b8494;
  font-size:10px;
  line-height:1.35;
  text-overflow:ellipsis;
  white-space:nowrap;
}
.outline-review__nodes input {
  height:31px;
  padding:0 8px;
  font-size:14px;
  font-weight:750;
}
.outline-review__nodes li[data-level="1"] input {
  color:#182230;
  font-size:15px;
}
.outline-review__nodes textarea {
  height:38px;
  min-height:38px;
  margin-top:3px;
  padding:7px 8px;
  resize:vertical;
  color:#687386;
  font-size:13px;
  line-height:1.55;
}
.outline-review__empty {
  grid-row:3;
  margin:0;
  padding:42px 30px;
  color:#8a93a3;
  text-align:center;
  font-size:13px;
}
.outline-review__footer {
  grid-row:4;
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:24px;
  padding:13px 18px 14px 30px;
  border-top:1px solid #dfe3e9;
  background:#fafbfc;
}
.outline-review__footer > div:first-child { min-width:0; }
.outline-review__footer strong { color:#344054; font-size:13px; }
.outline-review__footer p { margin:3px 0 0; color:#7b8494; font-size:11px; line-height:1.5; }
.outline-review__footer p.outline-review__action-error { color:#b42318; }
.outline-review__actions {
  flex:0 0 auto;
  display:flex;
  gap:8px;
}
.outline-review__actions button {
  min-height:40px;
  display:inline-flex;
  align-items:center;
  justify-content:center;
  gap:7px;
  padding:0 16px;
  border-radius:9px;
  font-size:12px;
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
  box-shadow:0 7px 18px rgba(63,71,168,.18);
}
.outline-review__actions button:not(:disabled):hover { transform:translateY(-1px); }
.outline-review__actions svg.lucide-loader-circle { animation:outline-review-spin .9s linear infinite; }
@keyframes outline-review-spin { to { transform:rotate(360deg); } }
@media (max-width:767px) {
  .outline-review { padding:8px 6px 14px; }
  .outline-review__sheet { border-radius:13px; }
  .outline-review__header { display:grid; gap:9px; padding:19px 16px 15px; }
  .outline-review__header h1 { font-size:27px; }
  .outline-review__count { justify-self:start; }
  .outline-review__setup { min-height:0; }
  .outline-review__course-name { grid-template-columns:1fr; gap:3px; margin:0 16px; padding:10px 0 8px; }
  .outline-review__starting-point { margin:0 16px; padding:11px 0 13px; }
  .outline-review__starting-point > div { grid-template-columns:1fr; gap:8px; }
  .outline-review__nodes { padding:4px 16px 12px; }
  .outline-review__nodes li { grid-template-columns:26px 12px minmax(0,1fr); gap:6px; }
  .outline-review__footer { align-items:stretch; flex-direction:column; gap:9px; padding:11px 12px 13px; }
  .outline-review__actions { display:grid; grid-template-columns:.85fr 1.15fr; }
  .outline-review__actions button { padding:0 9px; }
}
@media (prefers-reduced-motion:reduce) {
  .outline-review__loading svg,
  .outline-review__actions svg { animation:none!important; }
}
</style>
