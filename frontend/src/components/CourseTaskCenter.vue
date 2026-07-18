<template>
  <Teleport to="body">
    <div v-if="modelValue" class="task-center-layer" @keydown.esc="close">
      <button type="button" class="task-center-backdrop" :aria-label="t('common.cancel', '取消')" @click="close" />
      <section ref="panelRef" class="task-center" role="dialog" aria-modal="true" :aria-labelledby="titleId" tabindex="-1">
        <header class="task-center__header">
          <div>
            <span><ListChecks :size="16" /></span>
            <div>
              <p>{{ t('courseTasks.eyebrow', '后台生成') }}</p>
              <h2 :id="titleId">{{ t('courseTasks.title', '课程生成任务') }}</h2>
            </div>
          </div>
          <div class="task-center__header-actions">
            <button type="button" class="icon-button" :title="t('courseTasks.refresh', '刷新任务')" :disabled="refreshing" @click="refresh">
              <RefreshCw :size="17" :class="{ spin: refreshing }" />
            </button>
            <button type="button" class="icon-button" :title="t('common.cancel', '取消')" @click="close"><X :size="18" /></button>
          </div>
        </header>

        <div class="task-center__body">
          <aside class="task-list" :aria-label="t('courseTasks.listLabel', '生成任务列表')">
            <div v-if="!tasks.length" class="task-list__empty">
              <Inbox :size="23" />
              <strong>{{ t('courseTasks.empty', '暂无生成任务') }}</strong>
              <span>{{ t('courseTasks.emptyHelp', '新建课程后，生成状态会出现在这里。') }}</span>
            </div>
            <button
              v-for="task in tasks"
              :key="task.id"
              type="button"
              class="task-row"
              :class="{ active: selectedCourseId === task.courseId }"
              @click="selectTask(task.courseId)"
            >
              <span class="task-row__state" :data-status="task.status"><component :is="statusIcon(task.status)" :size="15" /></span>
              <span class="task-row__copy">
                <strong>{{ task.courseName }}</strong>
                <small>{{ statusLabel(task.status, task.recovery) }} · {{ Math.round(task.progress) }}%</small>
              </span>
              <ChevronRight :size="15" />
            </button>
          </aside>

          <main v-if="selectedTask" class="task-detail">
            <div class="task-detail__scroll">
            <section class="task-summary">
              <div class="task-summary__top">
                <div>
                  <span class="status-chip" :data-status="selectedTask.status">{{ statusLabel(selectedTask.status, selectedTask.recovery) }}</span>
                  <h3>{{ selectedTask.courseName }}</h3>
                  <p>{{ selectedTask.currentStep || phaseLabel(selectedTask.currentPhase, selectedTask.status) }}</p>
                </div>
                <strong>{{ Math.round(selectedTask.progress) }}%</strong>
              </div>
              <div class="task-progress" role="progressbar" :aria-valuenow="Math.round(selectedTask.progress)" aria-valuemin="0" aria-valuemax="100">
                <span :style="{ width: `${selectedTask.progress}%` }" />
              </div>
              <dl>
                <div><dt>{{ t('courseTasks.phase', '当前阶段') }}</dt><dd>{{ phaseLabel(selectedTask.currentPhase, selectedTask.status) }}</dd></div>
                <div v-if="phaseItemProgress"><dt>{{ phaseItemProgress.label }}</dt><dd>{{ phaseItemProgress.completed }} / {{ phaseItemProgress.total }}</dd></div>
                <div v-else-if="selectedProgress?.totalNodes"><dt>{{ t('courseTasks.nodes', '内容进度') }}</dt><dd>{{ selectedProgress.completedNodes }} / {{ selectedProgress.totalNodes }}</dd></div>
                <div v-else-if="selectedTask.recovery?.checkpoint.total_nodes"><dt>{{ t('courseTasks.nodes', '内容进度') }}</dt><dd>{{ selectedTask.recovery.checkpoint.completed_nodes }} / {{ selectedTask.recovery.checkpoint.total_nodes }}</dd></div>
                <div v-if="selectedProgress?.estimatedTimeRemaining"><dt>{{ t('courseTasks.remaining', '预计剩余') }}</dt><dd>{{ formatDuration(selectedProgress.estimatedTimeRemaining) }}</dd></div>
              </dl>
            </section>

            <section v-if="selectedTask.status === 'waiting_for_review'" class="blueprint-review">
              <header>
                <div>
                  <h4>{{ t('courseTasks.blueprint.title', '确认课程目录') }}</h4>
                  <p>{{ t('courseTasks.blueprint.help', '先确认章节、顺序和学习目标；确认后才会逐节生成知识包和正文。') }}</p>
                </div>
                <LoaderCircle v-if="workspace.loading" class="spin" :size="18" />
              </header>
              <template v-if="blueprintDraft">
                <label class="blueprint-course-name">
                  <span>{{ t('courseWorkspace.blueprint.courseName', '课程名称') }}</span>
                  <input v-model="blueprintDraft.course_name" type="text" />
                </label>
                <div class="blueprint-nodes">
                  <article v-for="(node, index) in blueprintNodes" :key="node.node_id || index">
                    <span>{{ String(index + 1).padStart(2, '0') }}</span>
                    <div>
                      <input v-model="node.node_name" type="text" :aria-label="t('courseTasks.blueprint.nodeName', '章节名称')" />
                      <textarea v-if="'learning_objective' in node" v-model="node.learning_objective" :aria-label="t('courseTasks.blueprint.objective', '学习目标')" />
                    </div>
                  </article>
                </div>
                <p v-if="blueprintNodes.length === 0" class="blueprint-empty">{{ t('courseTasks.blueprint.noNodes', '蓝图暂未返回可编辑节点，请刷新后重试。') }}</p>
              </template>
              <p v-else-if="blueprintError" class="blueprint-error">{{ blueprintError }}</p>
            </section>

            <section v-if="selectedTask.status === 'error' || selectedTask.status === 'completed_with_warnings' || selectedTask.status === 'conflict'" class="task-notice" :data-status="selectedTask.status">
              <TriangleAlert :size="18" />
              <div>
                <strong>{{ problemTitle(selectedTask) }}</strong>
                <p>{{ problemHelp(selectedTask) }}</p>
                <small v-if="selectedTask.error" class="task-error-detail">{{ t('courseTasks.problem.detail', '具体原因：{error}').replace('{error}', selectedTask.error) }}</small>
                <small v-if="selectedTask.recovery?.can_resume" class="recovery-checkpoint">{{ recoveryCheckpointLabel(selectedTask) }}</small>
              </div>
            </section>
            </div>

            <footer class="task-actions">
              <button v-if="canPause(selectedTask)" type="button" class="secondary-button" :disabled="acting" @click="pauseSelected">
                <Pause :size="16" />{{ t('courseGeneration.actions.pause', '暂停') }}
              </button>
              <button v-if="canResume(selectedTask)" type="button" class="primary-button" :disabled="acting" @click="resumeSelected">
                <RotateCw :size="16" />{{ t('courseTasks.resumeCheckpoint', '从保存点继续') }}
              </button>
              <button v-if="selectedTask.status === 'waiting_for_review'" type="button" class="primary-button" :disabled="acting || workspace.loading || !blueprintDraft" @click="confirmBlueprint">
                <CircleCheck :size="16" />{{ t('courseTasks.blueprint.confirm', '确认并继续生成') }}
              </button>
              <button v-if="courseExists(selectedTask.courseId)" type="button" class="secondary-button task-actions__open" @click="openCourse(selectedTask.courseId)">
                <BookOpenText :size="16" />{{ t('courseTasks.openCourse', '进入课程') }}
              </button>
              <button type="button" class="danger-button" :disabled="acting" @click="deleteSelected">
                <Trash2 :size="16" />{{ taskDeleteLabel(selectedTask) }}
              </button>
            </footer>
          </main>

          <main v-else class="task-detail task-detail--empty">
            <ListChecks :size="28" />
            <p>{{ t('courseTasks.select', '选择一个任务查看生成详情。') }}</p>
          </main>
        </div>
      </section>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  BookOpenText, ChevronRight, CircleCheck, CircleDashed, CirclePause, CircleX,
  Clock3, Inbox, ListChecks, LoaderCircle, Pause, RefreshCw, RotateCw,
  Trash2, TriangleAlert, X,
} from 'lucide-vue-next'
import { useCourseStore } from '@/stores/course'
import { useCourseWorkspaceStore } from '@/stores/courseWorkspace'
import { useGenerationStore } from '@/stores/generation'
import type { Task } from '@/stores/types'
import { t } from '@/shared/i18n'

type TaskView = Task & { updatedAt?: string }

const props = withDefaults(defineProps<{ modelValue: boolean; courseId?: string }>(), { courseId: '' })
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()
const router = useRouter()
const courseStore = useCourseStore()
const generationStore = useGenerationStore()
const workspace = useCourseWorkspaceStore()
const titleId = `course-task-center-${Math.random().toString(36).slice(2)}`
const panelRef = ref<HTMLElement | null>(null)
const selectedCourseId = ref('')
const refreshing = ref(false)
const acting = ref(false)
const blueprintDraft = ref<any>(null)
const blueprintError = ref('')

const tasks = computed<TaskView[]>(() => {
  const byCourse = new Map<string, TaskView>()
  for (const raw of generationStore.globalTasks || []) {
    const local = generationStore.getTask(raw.course_id)
    byCourse.set(raw.course_id, {
      id: raw.id,
      courseId: raw.course_id,
      courseName: raw.course_name || local?.courseName || t('courseTasks.untitled', '未命名课程'),
      status: normalizeStatus(raw.status),
      progress: Math.max(0, Math.min(100, Number(raw.progress || 0))),
      currentStep: raw.current_node_name ? String(raw.current_node_name) : String(raw.message || local?.currentStep || ''),
      currentPhase: String(raw.current_phase || raw.phase || local?.currentPhase || ''),
      phaseProgress: Number(raw.phase_progress || local?.phaseProgress || 0),
      phaseDetail: raw.phase_detail || local?.phaseDetail || {},
      error: raw.error ? String(raw.error) : local?.error,
      recovery: raw.recovery || local?.recovery,
      publicationAllowed: typeof raw.publication_allowed === 'boolean' ? raw.publication_allowed : local?.publicationAllowed,
      qualityStatus: raw.quality_status || local?.qualityStatus,
      logs: local?.logs || [],
      shouldStop: false,
      updatedAt: raw.updated_at || raw.created_at,
    })
  }
  for (const local of generationStore.tasks.values()) {
    if (!byCourse.has(local.courseId)) byCourse.set(local.courseId, { ...local })
  }
  return [...byCourse.values()].sort((a, b) => {
    const priority = (task: TaskView) => taskNeedsAttention(task) ? 0 : 1
    return priority(a) - priority(b) || String(b.updatedAt || '').localeCompare(String(a.updatedAt || ''))
  })
})
const selectedTask = computed(() => tasks.value.find(task => task.courseId === selectedCourseId.value) || null)
const selectedProgress = computed(() => selectedTask.value ? generationStore.taskProgress[selectedTask.value.courseId] : null)
const phaseItemProgress = computed(() => {
  const detail = selectedTask.value?.phaseDetail || {}
  const total = Number(detail.total_items || 0)
  if (!total) return null
  const label = String(detail.artifact_type || '') === 'course_outline'
    ? t('courseTasks.outlineItems', '目录小节')
    : t('courseTasks.knowledgePackages', '知识包进度')
  return {
    completed: Math.max(0, Number(detail.completed_items || 0)),
    total,
    label,
  }
})
const blueprintNodes = computed<any[]>(() => Array.isArray(blueprintDraft.value?.nodes)
  ? blueprintDraft.value.nodes
  : Array.isArray(blueprintDraft.value?.course_blueprint?.nodes) ? blueprintDraft.value.course_blueprint.nodes : [])

watch(() => props.modelValue, async open => {
  if (!open) return
  await refresh()
  selectedCourseId.value = props.courseId || selectedCourseId.value || tasks.value[0]?.courseId || ''
  await loadSelectedBlueprint()
  await nextTick()
  panelRef.value?.focus()
}, { immediate: true })
watch(() => props.courseId, value => {
  if (value) selectedCourseId.value = value
})
watch(selectedCourseId, () => { void loadSelectedBlueprint() })
onMounted(() => generationStore.startGlobalMonitor())

function normalizeStatus(status: string): Task['status'] {
  if (status === 'failed') return 'error'
  if (['idle', 'running', 'paused', 'completed', 'error', 'pending', 'waiting_for_review', 'completed_with_warnings', 'conflict'].includes(status)) return status as Task['status']
  return 'pending'
}
function close() { emit('update:modelValue', false) }
function selectTask(courseId: string) { selectedCourseId.value = courseId }
async function refresh() {
  refreshing.value = true
  try { await Promise.all([generationStore.fetchGlobalTasks(), courseStore.fetchCourseList()]) }
  finally { refreshing.value = false }
}
async function loadSelectedBlueprint() {
  blueprintDraft.value = null
  blueprintError.value = ''
  if (selectedTask.value?.status !== 'waiting_for_review') return
  try {
    const data = await workspace.loadBlueprint(selectedTask.value.courseId)
    blueprintDraft.value = JSON.parse(JSON.stringify(data.draft || data.current || data))
  } catch {
    blueprintError.value = t('courseTasks.blueprint.loadFailed', '课程蓝图读取失败，请刷新后重试。')
  }
}
async function pauseSelected() {
  if (!selectedTask.value) return
  await runAction(() => generationStore.pauseTask(selectedTask.value!.courseId))
}
async function resumeSelected() {
  if (!selectedTask.value) return
  await runAction(() => generationStore.resumeTask(selectedTask.value!.courseId))
}
async function confirmBlueprint() {
  if (!selectedTask.value || !blueprintDraft.value) return
  await runAction(async () => {
    const draft = blueprintDraft.value
    if (draft.base_blueprint_revision_id) {
      await workspace.saveBlueprint(selectedTask.value!.courseId, {
        base_blueprint_revision_id: draft.base_blueprint_revision_id,
        course_name: draft.course_name,
        course_purpose: draft.course_purpose,
        course_blueprint: draft.course_blueprint,
        nodes: draft.nodes,
        learning_asset_plan: draft.learning_asset_plan,
        blueprint_locks: draft.blueprint_locks || {},
      })
    }
    await workspace.confirmBlueprint(selectedTask.value!.courseId)
    generationStore.startGlobalMonitor()
    ElMessage.success(t('courseTasks.blueprint.confirmed', '蓝图已确认，课程继续在后台生成'))
  })
}
async function deleteSelected() {
  if (!selectedTask.value) return
  const task = selectedTask.value
  const preservesCourse = deletePreservesCourse(task)
  const active = ['pending', 'running', 'paused', 'waiting_for_review'].includes(task.status)
  const title = taskDeleteLabel(task)
  const message = preservesCourse
    ? t('courseTasks.deleteRecordConfirm', '清除任务记录和生成现场后，已经发布的正式课程仍会保留。')
    : active
      ? t('courseTasks.deleteActiveConfirm', '这会停止后台生成，并删除未发布课程、草稿和任务工作区。此操作不可撤销。')
      : t('courseTasks.deleteTaskConfirm', '这会删除未发布课程、草稿和任务工作区。此操作不可撤销。')
  try {
    await ElMessageBox.confirm(
      message,
      title,
      { type: 'warning', confirmButtonText: title, cancelButtonText: t('common.cancel', '取消') },
    )
    await runAction(() => generationStore.deleteTask(task.courseId))
    selectedCourseId.value = tasks.value[0]?.courseId || ''
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error(t('courseTasks.actionFailed', '任务操作失败'))
  }
}
async function runAction(action: () => Promise<unknown>) {
  acting.value = true
  try { await action(); await refresh() }
  catch { ElMessage.error(t('courseTasks.actionFailed', '任务操作失败')) }
  finally { acting.value = false }
}
function openCourse(courseId: string) { close(); void router.push({ name: 'learning', params: { courseId } }) }
function courseExists(courseId: string) { return courseStore.courseList.some(course => course.course_id === courseId) }
function canPause(task: TaskView) { return ['pending', 'running'].includes(task.status) }
function canResume(task: TaskView) {
  if (task.recovery) return task.recovery.can_resume
  return ['paused', 'error'].includes(task.status)
}
function deletePreservesCourse(task: TaskView) {
  return courseExists(task.courseId) && (task.status === 'completed' || isPublishedWarning(task))
}
function taskDeleteLabel(task: TaskView) {
  if (deletePreservesCourse(task)) return t('courseTasks.clearRecord', '清除任务记录')
  if (['pending', 'running', 'paused', 'waiting_for_review'].includes(task.status)) {
    return t('courseTasks.cancelAndDelete', '取消并删除')
  }
  return t('courseTasks.deleteTask', '删除任务')
}
function phaseLabel(phase: string | undefined, status: Task['status']) {
  const labels: Record<string, string> = {
    requirement_analysis: t('courseTasks.phases.requirementAnalysis', '整理课程需求'),
    material_processing: t('courseTasks.phases.materialProcessing', '解析资料与证据'),
    pedagogy_resolution: t('courseTasks.phases.pedagogyResolution', '确定教学结构与难度'),
    outline_generation: t('courseTasks.phases.outlineGeneration', '生成轻量课程目录'),
    outline_validation: t('courseTasks.phases.outlineValidation', '检查课程目录'),
    outline_ready: t('courseTasks.phases.outlineReady', '等待确认课程目录'),
    section_knowledge_generation: t('courseTasks.phases.sectionKnowledgeGeneration', '逐节生成知识包'),
    section_knowledge_validation: t('courseTasks.phases.sectionKnowledgeValidation', '检查当前小节知识包'),
    knowledge_mapping: t('courseTasks.phases.knowledgeMapping', '编译全课知识关系'),
    course_knowledge_blueprint: t('courseTasks.phases.knowledgeMapping', '编译全课知识关系'),
    blueprint_generation: t('courseTasks.phases.blueprintGeneration', '生成课程蓝图'),
    blueprint_validation: t('courseTasks.phases.blueprintValidation', '检查课程蓝图'),
    blueprint_ready: t('courseTasks.phases.blueprintReady', '等待确认课程蓝图'),
    content_generation: t('courseTasks.phases.contentGeneration', '生成课程内容'),
    resuming: t('courseTasks.phases.resuming', '从保存点恢复'),
    recovery_unavailable: t('courseTasks.phases.recoveryUnavailable', '无法恢复原任务'),
    quality_failed: t('courseTasks.phases.qualityFailed', '质量检查未通过'),
    conflict: t('courseTasks.phases.conflict', '等待处理版本冲突'),
    completed: t('courseTasks.phases.completed', '课程生成完成'),
  }
  return (phase ? labels[phase] : '') || statusLabel(status)
}
function statusIcon(status: Task['status']) {
  if (status === 'completed') return CircleCheck
  if (status === 'running') return Clock3
  if (status === 'paused') return CirclePause
  if (status === 'completed_with_warnings') return TriangleAlert
  if (['error', 'conflict'].includes(status)) return CircleX
  return CircleDashed
}
function statusLabel(status: Task['status'], recovery?: Task['recovery']) {
  if (recovery?.state === 'auto_resuming') return t('courseTasks.recovery.autoResuming', '正在恢复')
  if (status === 'completed_with_warnings' && recovery?.state === 'completed') {
    return t('courseLibrary.status.readyWithSuggestions', '可以学习，有优化建议')
  }
  const labels: Record<Task['status'], string> = {
    idle: t('courseLibrary.status.preparing', '正在准备课程'), pending: t('courseLibrary.status.pending', '等待生成'),
    running: t('courseLibrary.status.running', '正在生成'), paused: t('courseLibrary.status.paused', '已暂停'),
    waiting_for_review: t('courseLibrary.status.waitingReview', '等待确认目录'), conflict: t('courseLibrary.status.conflict', '需要确认'),
    error: t('courseLibrary.status.error', '生成失败'), completed_with_warnings: t('courseLibrary.status.warnings', '生成完成但有警告'),
    completed: t('courseLibrary.status.ready', '可以学习'),
  }
  return labels[status]
}
function problemTitle(task: TaskView) {
  if (task.status === 'completed_with_warnings' && task.recovery?.state === 'completed') {
    return t('courseTasks.problem.publishedWarning', '课程已经发布，仍有优化建议')
  }
  if (task.recovery?.state === 'quality_blocked') return t('courseTasks.problem.qualityBlocked', '内容已生成，但质量检查未通过')
  if (task.recovery?.state === 'unavailable') return t('courseTasks.problem.unavailable', '原任务没有可用的恢复点')
  if (task.status === 'error') return t('courseTasks.problem.failed', '生成中断，可以从保存点继续')
  if (task.status === 'conflict') return t('courseTasks.problem.conflict', '当前任务需要人工确认')
  return t('courseTasks.problem.warning', '课程已生成，但仍有质量警告')
}
function problemHelp(task: TaskView) {
  if (task.status === 'completed_with_warnings' && task.recovery?.state === 'completed') {
    return t('courseTasks.problem.publishedWarningHelp', '课程可以正常学习；这些建议用于后续局部优化，不需要重新生成整门课程。')
  }
  if (task.recovery?.state === 'quality_blocked') return t('courseTasks.problem.qualityBlockedHelp', '重复生成不会自动修复同一质量问题；请先查看质量结果，再决定局部优化。')
  if (task.recovery?.state === 'unavailable') return t('courseTasks.problem.unavailableHelp', '为避免覆盖现有内容，系统不会盲目重跑这个旧任务。')
  if (task.status === 'error') return t('courseTasks.problem.failedHelp', '继续时会保留已完成内容和中断草稿，不会新建重复课程。')
  if (task.status === 'conflict') return t('courseTasks.problem.conflictHelp', '保留当前内容，刷新任务状态后再决定继续或取消。')
  return t('courseTasks.problem.warningHelp', '可以继续补齐失败节点，也可以先进入课程查看已生成内容。')
}
function isPublishedWarning(task: TaskView) {
  return task.status === 'completed_with_warnings'
    && (task.publicationAllowed === true || task.recovery?.state === 'completed')
}
function taskNeedsAttention(task: TaskView) {
  if (isPublishedWarning(task)) return false
  return ['running', 'pending', 'waiting_for_review', 'error', 'conflict', 'paused', 'completed_with_warnings'].includes(task.status)
}
function recoveryCheckpointLabel(task: TaskView) {
  const checkpoint = task.recovery?.checkpoint
  if (!checkpoint) return ''
  const knowledgeCompleted = Number(checkpoint.completed_knowledge_packages || 0)
  const knowledgeTotal = Number(checkpoint.total_knowledge_packages || 0)
  if (knowledgeTotal && (knowledgeCompleted || checkpoint.outline_ready) && !checkpoint.completed_nodes) {
    return t('courseTasks.recovery.knowledgeCheckpoint', '目录已保留，知识包已完成 {completed}/{total}')
      .replace('{completed}', String(knowledgeCompleted))
      .replace('{total}', String(knowledgeTotal))
  }
  if (checkpoint.outline_ready && !checkpoint.total_nodes) {
    return t('courseTasks.recovery.outlineCheckpoint', '课程目录已保留，可从逐节知识包阶段继续')
  }
  return t('courseTasks.recovery.checkpoint', '已保留 {completed}/{total} 个内容块和 {drafts} 份草稿')
    .replace('{completed}', String(checkpoint.completed_nodes || 0))
    .replace('{total}', String(checkpoint.total_nodes || 0))
    .replace('{drafts}', String(checkpoint.draft_node_ids?.length || 0))
}
function formatDuration(seconds: number) {
  if (seconds < 60) return t('courseTasks.lessThanMinute', '少于 1 分钟')
  return t('courseTasks.minutes', '约 {count} 分钟').replace('{count}', String(Math.ceil(seconds / 60)))
}
</script>

<style scoped>
.task-center-layer { position: fixed; inset: 0; z-index: 520; display: grid; place-items: center; padding: 20px; }
.task-center-backdrop { position: absolute; inset: 0; width: 100%; height: 100%; border: 0; background: rgba(30,41,59,.34); backdrop-filter: blur(5px); cursor: default; }
.task-center { position: relative; width: min(980px,100%); height: min(720px,calc(100vh - 40px)); display: grid; grid-template-rows: 62px minmax(0,1fr); overflow: hidden; border: 1px solid rgba(255,255,255,.92); border-radius: var(--lz-radius-surface); color: var(--lz-text); background: rgba(255,255,255,.98); box-shadow: var(--lz-shadow-overlay); outline: none; }
.task-center__header { display:flex; align-items:center; justify-content:space-between; gap:16px; padding:0 14px 0 20px; border-bottom:1px solid var(--lz-border); }
.task-center__header > div:first-child { min-width:0; display:flex; align-items:center; gap:10px; }
.task-center__header > div:first-child > span { width:34px; height:34px; display:grid; place-items:center; border-radius:9px; color:var(--lz-brand-strong); background:var(--lz-brand-soft); }
.task-center__header p { margin:0 0 1px; color:var(--lz-text-muted); font-size:10px; font-weight:700; }
.task-center__header h2 { margin:0; color:var(--lz-text-strong); font-size:16px; }
.task-center__header-actions { display:flex; gap:4px; }
.icon-button { width:34px; height:34px; display:grid; place-items:center; border:0; border-radius:7px; color:var(--lz-text-secondary); background:transparent; cursor:pointer; }
.icon-button:hover { color:var(--lz-text-strong); background:var(--lz-surface-muted); }
.task-center__body { min-height:0; display:grid; grid-template-columns:280px minmax(0,1fr); }
.task-list { min-height:0; overflow:auto; padding:9px; border-right:1px solid var(--lz-border); background:rgba(248,250,252,.76); }
.task-list__empty,.task-detail--empty { height:100%; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:8px; color:var(--lz-text-muted); text-align:center; }
.task-list__empty strong { color:var(--lz-text); font-size:12px; }.task-list__empty span { max-width:190px; font-size:10px; line-height:1.5; }
.task-row { width:100%; min-height:62px; display:grid; grid-template-columns:30px minmax(0,1fr) auto; align-items:center; gap:8px; padding:8px 9px; border:1px solid transparent; border-radius:8px; color:var(--lz-text); background:transparent; text-align:left; cursor:pointer; }
.task-row:hover { background:#fff; }.task-row.active { border-color:rgba(99,102,241,.24); background:var(--lz-brand-soft); }
.task-row__state { width:28px; height:28px; display:grid; place-items:center; border-radius:8px; color:var(--lz-text-muted); background:#fff; }
.task-row__state[data-status="running"],.task-row__state[data-status="waiting_for_review"] { color:var(--lz-brand-strong); }
.task-row__state[data-status="completed"] { color:var(--lz-success); }.task-row__state[data-status="error"],.task-row__state[data-status="conflict"],.task-row__state[data-status="completed_with_warnings"] { color:var(--lz-warning); }
.task-row__copy { min-width:0; display:block; }.task-row__copy strong,.task-row__copy small { overflow:hidden; display:block; text-overflow:ellipsis; white-space:nowrap; }.task-row__copy strong { color:var(--lz-text-strong); font-size:12px; }.task-row__copy small { margin-top:4px; color:var(--lz-text-muted); font-size:10px; }
.task-detail { min-height:0; display:grid; grid-template-rows:minmax(0,1fr) auto; overflow:hidden; }
.task-detail__scroll { min-height:0; overflow:auto; padding:26px clamp(20px,4vw,38px) 18px; }
.task-summary { padding-bottom:24px; border-bottom:1px solid var(--lz-border); }
.task-summary__top { display:flex; align-items:flex-start; justify-content:space-between; gap:20px; }.task-summary__top > div { min-width:0; }.task-summary__top > strong { color:var(--lz-brand-strong); font-size:28px; line-height:1; }
.status-chip { display:inline-flex; min-height:24px; align-items:center; padding:0 8px; border-radius:5px; color:var(--lz-brand-strong); background:var(--lz-brand-soft); font-size:10px; font-weight:700; }.status-chip[data-status="completed"] { color:var(--lz-success); background:var(--lz-success-soft); }.status-chip[data-status="error"],.status-chip[data-status="conflict"],.status-chip[data-status="completed_with_warnings"] { color:var(--lz-warning); background:var(--lz-warning-soft); }
.task-summary h3 { margin:11px 0 5px; color:var(--lz-text-strong); font-size:21px; }.task-summary p { margin:0; color:var(--lz-text-secondary); font-size:12px; line-height:1.55; }
.task-progress { height:6px; margin:20px 0 17px; overflow:hidden; border-radius:3px; background:var(--lz-surface-muted); }.task-progress span { display:block; height:100%; border-radius:inherit; background:var(--lz-brand); transition:width .2s ease; }
.task-summary dl { margin:0; display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:14px; }.task-summary dl div { min-width:0; }.task-summary dt { color:var(--lz-text-muted); font-size:10px; }.task-summary dd { margin:4px 0 0; overflow:hidden; color:var(--lz-text); font-size:12px; font-weight:650; text-overflow:ellipsis; white-space:nowrap; }
.blueprint-review { padding:24px 0 4px; }.blueprint-review > header { display:flex; align-items:flex-start; justify-content:space-between; gap:14px; margin-bottom:16px; }.blueprint-review h4 { margin:0; color:var(--lz-text-strong); font-size:14px; }.blueprint-review header p { margin:5px 0 0; color:var(--lz-text-muted); font-size:11px; }
.blueprint-course-name span { display:block; margin-bottom:6px; color:var(--lz-text-muted); font-size:10px; }.blueprint-course-name input,.blueprint-nodes input,.blueprint-nodes textarea { width:100%; border:1px solid var(--lz-border); border-radius:7px; color:var(--lz-text); background:#fff; outline:none; }.blueprint-course-name input { height:38px; padding:0 10px; font-weight:650; }.blueprint-nodes { margin-top:12px; }.blueprint-nodes article { display:grid; grid-template-columns:28px minmax(0,1fr); gap:9px; padding:11px 0; border-top:1px solid rgba(226,232,240,.76); }.blueprint-nodes article > span { padding-top:9px; color:var(--lz-text-muted); font-size:10px; font-family:ui-monospace,monospace; }.blueprint-nodes input { height:36px; padding:0 9px; font-size:12px; font-weight:650; }.blueprint-nodes textarea { min-height:54px; margin-top:6px; padding:8px 9px; resize:vertical; font-size:11px; line-height:1.45; }.blueprint-course-name input:focus,.blueprint-nodes input:focus,.blueprint-nodes textarea:focus { border-color:var(--lz-brand); box-shadow:0 0 0 3px rgba(99,102,241,.08); }.blueprint-error,.blueprint-empty { color:var(--lz-warning); font-size:11px; }
.task-notice { margin-top:20px; display:flex; gap:10px; padding:13px 14px; border-left:3px solid var(--lz-warning); color:var(--lz-warning); background:var(--lz-warning-soft); }.task-notice strong { display:block; font-size:12px; }.task-notice p { margin:4px 0 0; font-size:11px; line-height:1.5; }.task-error-detail,.recovery-checkpoint { display:block; margin-top:7px; color:inherit; font-size:9px; line-height:1.5; opacity:.88; }
.task-actions { display:flex; flex-wrap:wrap; align-items:center; gap:8px; padding:13px clamp(20px,4vw,38px); border-top:1px solid var(--lz-border); background:rgba(255,255,255,.98); box-shadow:0 -8px 22px rgba(15,23,42,.035); }.task-actions__open { margin-left:auto; }
.primary-button,.secondary-button,.danger-button { min-height:38px; display:inline-flex; align-items:center; justify-content:center; gap:7px; padding:0 13px; border-radius:8px; font-size:12px; font-weight:700; cursor:pointer; }.primary-button { border:1px solid var(--lz-brand-strong); color:#fff; background:var(--lz-brand-strong); }.secondary-button { border:1px solid var(--lz-border); color:var(--lz-text-secondary); background:#fff; }.danger-button { border:1px solid rgba(185,28,28,.22); color:var(--lz-danger); background:var(--lz-danger-soft); }.primary-button:disabled,.secondary-button:disabled,.danger-button:disabled,.icon-button:disabled { cursor:not-allowed; opacity:.5; }
.spin { animation:spin 1s linear infinite; }@keyframes spin { to { transform:rotate(360deg); } }
@media (max-width:720px) { .task-center-layer { align-items:end; padding:0; }.task-center { width:100%; height:calc(100vh - 56px); border-radius:14px 14px 0 0; }.task-center__body { grid-template-columns:1fr; grid-template-rows:auto minmax(0,1fr); }.task-list { max-height:168px; border-right:0; border-bottom:1px solid var(--lz-border); }.task-detail__scroll { padding:20px 16px 14px; }.task-actions { padding:12px 16px calc(12px + env(safe-area-inset-bottom)); }.task-summary dl { grid-template-columns:1fr 1fr; }.task-actions__open { margin-left:0; } }
</style>
