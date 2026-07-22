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
              :class="{ active: selectedTaskId === task.id }"
              @click="selectTask(task.id)"
            >
              <span class="task-row__state" :data-status="task.status"><component :is="statusIcon(task.status)" :size="15" /></span>
              <span class="task-row__copy">
                <strong>{{ task.courseName }}</strong>
                <small>
                  {{ statusLabel(task.status, task.recovery) }} · {{ Math.round(task.progress) }}%
                  <template v-if="task.updatedAt"> · {{ formatTaskTime(task.updatedAt) }}</template>
                </small>
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
                  <p>{{ taskStepLabel(selectedTask) }}</p>
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

            <section v-if="workflowSteps.length" class="guided-workflow" :aria-label="t('courseTasks.workflow.label', '课程生成四步流程')">
              <ol>
                <li v-for="step in workflowSteps" :key="step.key" :data-status="step.displayStatus">
                  <button
                    type="button"
                    class="guided-workflow__step"
                    :disabled="!canReopenWorkflowStep(step)"
                    :title="canReopenWorkflowStep(step) ? t('courseTasks.workflow.reopenHint', '返回修改课程目录；后续步骤将按新目录重建') : ''"
                    @click="reopenWorkflowStep(step)"
                  >
                    <span class="guided-workflow__marker">
                      <CircleCheck v-if="step.displayStatus === 'confirmed'" :size="14" />
                      <LoaderCircle v-else-if="step.displayStatus === 'in_progress'" class="spin" :size="14" />
                      <span v-else>{{ step.number }}</span>
                    </span>
                    <span class="guided-workflow__copy">
                      <strong>{{ step.label }}</strong>
                      <small>{{ canReopenWorkflowStep(step) ? t('courseTasks.workflow.clickToEdit', '可返回修改') : workflowStatusLabel(step.displayStatus) }}</small>
                    </span>
                  </button>
                </li>
              </ol>
            </section>

            <section v-if="selectedTask.status === 'waiting_for_review'" class="generation-review">
              <header>
                <div>
                  <span class="generation-review__step">{{ currentReviewNumber }}</span>
                  <h4>{{ currentReviewTitle }}</h4>
                  <p>{{ currentReviewHelp }}</p>
                </div>
                <LoaderCircle v-if="workspace.loading" class="spin" :size="18" />
              </header>
              <template v-if="currentReviewStep === 'outline' && blueprintDraft">
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
              <template v-else-if="reviewArtifact && currentReviewStep === 'content'">
                <div class="review-callout">
                  <BookOpenText :size="18" />
                  <div>
                    <strong>{{ t('courseTasks.review.contentReady', '完整课程已经生成') }}</strong>
                    <p>{{ t('courseTasks.review.contentReadyHelp', '可以先进入课程逐节查看，再回到这里确认内容。') }}</p>
                  </div>
                </div>
                <div class="content-evidence">
                  <div>
                    <span>{{ t('courseTasks.review.contentQuality', '内容检查') }}</span>
                    <strong>{{ contentQualityLabel }}</strong>
                  </div>
                  <div>
                    <span>{{ t('courseTasks.review.learningAssets', '学习资产') }}</span>
                    <strong>{{ totalLearningAssetCount }}</strong>
                  </div>
                  <div>
                    <span>{{ t('courseTasks.review.manualReview', '需人工关注') }}</span>
                    <strong>{{ reviewArtifact.manual_review_count || 0 }}</strong>
                  </div>
                </div>
                <div v-if="assetCountEntries.length" class="asset-counts">
                  <span v-for="entry in assetCountEntries" :key="entry.type">{{ learningAssetLabel(entry.type) }} · {{ entry.count }}</span>
                </div>
                <section v-if="reviewArtifact.question_review?.total" class="question-review">
                  <header>
                    <div>
                      <strong>{{ t('courseTasks.review.questionReview', '题目合同与可判定性') }}</strong>
                      <p>{{ t('courseTasks.review.questionReviewHelp', '题目直接继承知识、能力、易错与答案合同，并通过确定性引用和可判定性检查。') }}</p>
                    </div>
                    <span :data-blocked="Boolean(reviewArtifact.question_review.blocked)">
                      {{ reviewArtifact.question_review.passed }} / {{ reviewArtifact.question_review.total }}
                      {{ t('courseTasks.review.questionPassed', '题通过') }}
                    </span>
                  </header>
                  <div class="question-review__list">
                    <article
                      v-for="(question, index) in reviewArtifact.question_review.samples || []"
                      :key="question.question_id || index"
                      :data-status="question.status"
                    >
                      <div class="question-review__index">{{ String(index + 1).padStart(2, '0') }}</div>
                      <div>
                        <div class="question-review__meta">
                          <span>{{ question.practice_level }}</span>
                          <b>{{ question.library_fit || t('courseTasks.review.questionPending', '待解析') }}</b>
                        </div>
                        <strong>{{ question.prompt }}</strong>
                        <dl>
                          <div>
                            <dt>{{ t('courseTasks.review.questionWhy', '为什么出这道题') }}</dt>
                            <dd>{{ question.why_this_question }}</dd>
                          </div>
                          <div>
                            <dt>{{ t('courseTasks.review.questionActuallyTests', '它实际在考什么') }}</dt>
                            <dd>{{ question.task_goal || t('courseTasks.review.questionPending', '待解析') }}</dd>
                          </div>
                        </dl>
                        <div class="question-review__targets">
                          <span v-for="skill in question.target_skills || []" :key="skill.id">{{ skill.name }}</span>
                          <span v-for="mistake in question.target_misconceptions || []" :key="mistake.id" data-kind="mistake">{{ mistake.name }}</span>
                        </div>
                        <ul v-if="question.issues?.length">
                          <li v-for="(issue, issueIndex) in question.issues" :key="`${issue.gate}-${issueIndex}`">{{ issue.message }}</li>
                        </ul>
                      </div>
                    </article>
                  </div>
                </section>
                <ul v-if="contentReviewIssues.length" class="release-issues">
                  <li v-for="(issue, index) in contentReviewIssues" :key="`${issue.code || 'content-issue'}-${index}`">{{ reviewIssueMessage(issue) }}</li>
                </ul>
                <div class="review-cards review-cards--compact">
                  <article v-for="(section, index) in reviewArtifact.sections || []" :key="section.node_id || index">
                    <span>{{ String(index + 1).padStart(2, '0') }}</span>
                    <div>
                      <strong>{{ section.name }}</strong>
                      <p>{{ t('courseTasks.review.contentStats', '{characters} 字 · {blocks} 个内容块')
                        .replace('{characters}', String(section.character_count || 0))
                        .replace('{blocks}', String(section.block_count || 0)) }}</p>
                    </div>
                  </article>
                </div>
              </template>
              <template v-else-if="reviewArtifact && currentReviewStep === 'release'">
                <div class="release-verdict" :data-pass="canConfirmCurrentStep">
                  <CircleCheck v-if="canConfirmCurrentStep" :size="20" />
                  <TriangleAlert v-else :size="20" />
                  <div>
                    <strong>{{ canConfirmCurrentStep ? t('courseTasks.review.releaseReady', '检查通过，可以发布') : t('courseTasks.review.releaseBlocked', '还有问题，暂时不能发布') }}</strong>
                    <p>{{ t('courseTasks.review.sourceChain', '目录、全课小节教案、知识库和课程内容已按同一版本链核对。') }}</p>
                  </div>
                </div>
                <ul v-if="releaseIssues.length" class="release-issues">
                  <li v-for="(issue, index) in releaseIssues" :key="`${issue.code || 'issue'}-${index}`">{{ reviewIssueMessage(issue) }}</li>
                </ul>
              </template>
              <p v-else-if="reviewError" class="blueprint-error">{{ reviewError }}</p>
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
              <button
                v-if="canPause(selectedTask)"
                type="button"
                class="secondary-button"
                :title="pauseActionHelp(selectedTask)"
                :disabled="acting"
                @click="pauseSelected"
              >
                <Pause :size="16" />{{ pauseActionLabel(selectedTask) }}
              </button>
              <button v-if="canResume(selectedTask)" type="button" class="primary-button" :disabled="acting" @click="resumeSelected">
                <RotateCw :size="16" />{{ resumeActionLabel(selectedTask) }}
              </button>
              <button v-if="selectedTask.status === 'waiting_for_review'" type="button" class="primary-button" :disabled="acting || workspace.loading || !canConfirmCurrentStep" @click="confirmCurrentStep">
                <CircleCheck :size="16" />{{ confirmCurrentStepLabel }}
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
import type { GuidedGenerationStepKey, Task } from '@/stores/types'
import { activeLocale, t } from '@/shared/i18n'
import { courseProductionTaskDetail } from '@/utils/course-production'

type TaskView = Task & { updatedAt?: string }

const props = withDefaults(defineProps<{ modelValue: boolean; courseId?: string }>(), { courseId: '' })
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()
const router = useRouter()
const courseStore = useCourseStore()
const generationStore = useGenerationStore()
const workspace = useCourseWorkspaceStore()
const titleId = `course-task-center-${Math.random().toString(36).slice(2)}`
const panelRef = ref<HTMLElement | null>(null)
const selectedTaskId = ref('')
const refreshing = ref(false)
const acting = ref(false)
const blueprintDraft = ref<any>(null)
const generationReview = ref<any>(null)
const reviewError = ref('')

const tasks = computed<TaskView[]>(() => {
  const byTaskId = new Map<string, TaskView>()
  for (const raw of generationStore.globalTasks || []) {
    const local = generationStore.getTask(raw.course_id)
    const matchingLocal = local?.id === raw.id ? local : undefined
    byTaskId.set(raw.id, {
      id: raw.id,
      courseId: raw.course_id,
      courseName: raw.course_name || matchingLocal?.courseName || t('courseTasks.untitled', '未命名课程'),
      status: normalizeStatus(raw.status),
      progress: Math.max(0, Math.min(100, Number(raw.progress || 0))),
      currentStep: raw.current_node_name ? String(raw.current_node_name) : String(raw.message || matchingLocal?.currentStep || ''),
      currentPhase: String(raw.current_phase || raw.phase || matchingLocal?.currentPhase || ''),
      phaseProgress: Number(raw.phase_progress || matchingLocal?.phaseProgress || 0),
      phaseDetail: raw.phase_detail || matchingLocal?.phaseDetail || {},
      error: raw.error ? String(raw.error) : matchingLocal?.error,
      recovery: raw.recovery || matchingLocal?.recovery,
      publicationAllowed: typeof raw.publication_allowed === 'boolean' ? raw.publication_allowed : matchingLocal?.publicationAllowed,
      qualityStatus: raw.quality_status || matchingLocal?.qualityStatus,
      guidedWorkflow: raw.guided_workflow || matchingLocal?.guidedWorkflow,
      logs: matchingLocal?.logs || [],
      shouldStop: false,
      updatedAt: raw.updated_at || raw.created_at,
    })
  }
  for (const local of generationStore.tasks.values()) {
    if (!byTaskId.has(local.id)) byTaskId.set(local.id, { ...local })
  }
  return [...byTaskId.values()].sort((a, b) => {
    const priority = (task: TaskView) => taskNeedsAttention(task) ? 0 : 1
    return priority(a) - priority(b) || String(b.updatedAt || '').localeCompare(String(a.updatedAt || ''))
  })
})
const selectedTask = computed(() => tasks.value.find(task => task.id === selectedTaskId.value) || null)
const selectedProgress = computed(() => {
  if (!selectedTask.value) return null
  const current = generationStore.getTask(selectedTask.value.courseId)
  return current?.id === selectedTask.value.id
    ? generationStore.taskProgress[selectedTask.value.courseId]
    : null
})
const phaseItemProgress = computed(() => {
  const detail = selectedTask.value?.phaseDetail || {}
  const total = Number(detail.total_items || 0)
  if (!total) return null
  const artifactType = String(detail.artifact_type || '')
  const label = artifactType === 'course_outline'
    ? t('courseTasks.outlineItems', '目录小节')
    : artifactType === 'course_teaching_plan'
      ? t('courseTasks.teachingPlanItems', '小节教案进度')
      : artifactType === 'section_knowledge_package'
        ? t('courseTasks.knowledgePackages', '旧版知识检查点')
      : t('courseTasks.nodes', '内容进度')
  return {
    completed: Math.max(0, Number(detail.completed_items || 0)),
    total,
    label,
  }
})
const blueprintNodes = computed<any[]>(() => Array.isArray(blueprintDraft.value?.nodes)
  ? blueprintDraft.value.nodes
  : Array.isArray(blueprintDraft.value?.course_blueprint?.nodes) ? blueprintDraft.value.course_blueprint.nodes : [])
const currentReviewStep = computed<GuidedGenerationStepKey>(() => (
  generationReview.value?.step
  || selectedTask.value?.guidedWorkflow?.review_step
  || selectedTask.value?.guidedWorkflow?.current_step
  || 'outline'
))
const reviewArtifact = computed(() => generationReview.value?.artifact || null)
const workflowSteps = computed(() => {
  const workflow = selectedTask.value?.guidedWorkflow || generationReview.value?.guided_workflow
  const current = workflow?.current_step
  return (workflow?.steps || []).map((step: any) => ({
    ...step,
    label: guidedStepLabel(step.key),
    displayStatus: (
      step.status === 'pending'
      && current === step.key
      && selectedTask.value?.status === 'running'
    ) ? 'in_progress' : step.status,
  }))
})
const currentReviewNumber = computed(() => {
  const step = workflowSteps.value.find((item: any) => item.key === currentReviewStep.value)
  return String(step?.number || 2).padStart(2, '0')
})
const currentReviewTitle = computed(() => ({
  outline: t('courseTasks.blueprint.title', '确认课程目录'),
  teaching: t('courseTasks.review.teachingTitle', '确认全课教案'),
  content: t('courseTasks.review.contentTitle', '审阅课程内容'),
  release: t('courseTasks.review.releaseTitle', '确认并发布'),
  requirements: t('courseTasks.review.requirementsTitle', '确认课程需求'),
}[currentReviewStep.value]))
const currentReviewHelp = computed(() => ({
  outline: t('courseTasks.blueprint.help', '确认章节、顺序和学习目标；确认后会冻结全课知识职责，按预算生成详细教案与各节正文。'),
  teaching: t('courseTasks.review.teachingHelp', '详细教案已按批次生成并汇编；确认后才会开始逐节生成课程正文。'),
  content: t('courseTasks.review.contentHelp', '小节教案、知识库与关系图已由同一计划编译；进入学习现场检查正文后确认。'),
  release: t('courseTasks.review.releaseHelp', '确认结构、引用和同源版本链完整后发布；这里不再调用 AI 评分或重写。'),
  requirements: t('courseTasks.review.requirementsHelp', '确认本次课程生成需求。'),
}[currentReviewStep.value]))
const canConfirmCurrentStep = computed(() => {
  if (selectedTask.value?.status !== 'waiting_for_review') return false
  if (currentReviewStep.value === 'outline') return Boolean(blueprintDraft.value)
  return Boolean(generationReview.value?.can_confirm)
})
const confirmCurrentStepLabel = computed(() => (
  currentReviewStep.value === 'release'
    ? t('courseTasks.review.publish', '确认并发布课程')
    : t('courseTasks.review.confirm', '确认这一步，继续生成')
))
const releaseIssues = computed<any[]>(() => [
  ...(reviewArtifact.value?.blocking_issues || []),
  ...(reviewArtifact.value?.source_chain?.issues || []),
])
const assetCountEntries = computed(() => (
  Object.entries(reviewArtifact.value?.asset_counts || {})
    .map(([type, count]) => ({ type, count: Number(count || 0) }))
    .filter(entry => entry.count > 0)
    .sort((a, b) => b.count - a.count || a.type.localeCompare(b.type))
))
const totalLearningAssetCount = computed(() => (
  assetCountEntries.value.reduce((sum, entry) => sum + entry.count, 0)
))
const contentReviewIssues = computed<any[]>(() => [
  ...(reviewArtifact.value?.blocking_issues || []),
  ...(reviewArtifact.value?.warnings || []),
])
const contentQualityLabel = computed(() => {
  const status = String(reviewArtifact.value?.quality_status || '')
  if (status === 'passed') return t('courseTasks.review.qualityPassed', '通过')
  if (status === 'completed_with_warnings') return t('courseTasks.review.qualityWarnings', '有提醒')
  return status
    ? t('courseTasks.review.qualityBlocked', '需处理')
    : t('courseTasks.review.qualityPending', '待检查')
})

watch(() => props.modelValue, async open => {
  if (!open) return
  await refresh()
  if (!tasks.value.some(task => task.id === selectedTaskId.value)) {
    selectedTaskId.value = preferredTaskId(props.courseId)
  }
  await loadSelectedReview()
  await nextTick()
  panelRef.value?.focus()
}, { immediate: true })
watch(() => props.courseId, value => {
  if (value) selectedTaskId.value = preferredTaskId(value)
})
watch(selectedTaskId, () => { void loadSelectedReview() })
watch(
  () => [
    selectedTask.value?.status,
    selectedTask.value?.guidedWorkflow?.review_step,
  ],
  ([status]) => {
    if (status === 'waiting_for_review') void loadSelectedReview()
  },
)
onMounted(() => generationStore.startGlobalMonitor())

function normalizeStatus(status: string): Task['status'] {
  if (status === 'failed') return 'error'
  if (['idle', 'running', 'paused', 'completed', 'error', 'pending', 'waiting_for_review', 'completed_with_warnings', 'conflict'].includes(status)) return status as Task['status']
  return 'pending'
}
function close() { emit('update:modelValue', false) }
function preferredTaskId(courseId?: string) {
  return tasks.value.find(task => task.courseId === courseId)?.id || tasks.value[0]?.id || ''
}
function selectTask(taskId: string) { selectedTaskId.value = taskId }
async function refresh() {
  refreshing.value = true
  try { await Promise.all([generationStore.fetchGlobalTasks(), courseStore.fetchCourseList()]) }
  finally { refreshing.value = false }
}
async function loadSelectedReview() {
  blueprintDraft.value = null
  generationReview.value = null
  reviewError.value = ''
  if (selectedTask.value?.status !== 'waiting_for_review') return
  try {
    const review = await workspace.loadGenerationReview(selectedTask.value.courseId)
    generationReview.value = review
    if (review.step === 'outline') {
      const data = await workspace.loadBlueprint(selectedTask.value.courseId)
      blueprintDraft.value = JSON.parse(JSON.stringify(data.draft || data.current || data))
    }
  } catch {
    reviewError.value = t('courseTasks.review.loadFailed', '当前步骤读取失败，请刷新后重试。')
  }
}
async function pauseSelected() {
  if (!selectedTask.value) return
  await runAction(() => generationStore.pauseTask(selectedTask.value!.courseId, selectedTask.value!.id))
}
async function resumeSelected() {
  if (!selectedTask.value) return
  await runAction(() => generationStore.resumeTask(selectedTask.value!.courseId, selectedTask.value!.id))
}
async function confirmCurrentStep() {
  if (!selectedTask.value || !canConfirmCurrentStep.value) return
  await runAction(async () => {
    const step = currentReviewStep.value
    const draft = blueprintDraft.value
    if (step === 'outline' && draft?.base_blueprint_revision_id) {
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
    await workspace.confirmGenerationStep(
      selectedTask.value!.courseId,
      step as Exclude<GuidedGenerationStepKey, 'requirements'>,
    )
    generationStore.startGlobalMonitor()
    ElMessage.success(
      step === 'release'
        ? t('courseTasks.review.publishing', '发布已确认，正在完成课程发布')
        : t('courseTasks.review.confirmed', '当前步骤已确认，课程继续在后台生成'),
    )
  })
}
function canReopenWorkflowStep(step: any) {
  return (
    selectedTask.value?.status === 'waiting_for_review'
    && step?.key === 'outline'
    && step?.status === 'confirmed'
    && currentReviewStep.value !== 'outline'
  )
}
async function reopenWorkflowStep(step: any) {
  if (!selectedTask.value || !canReopenWorkflowStep(step)) return
  try {
    await ElMessageBox.confirm(
      t(
        'courseTasks.workflow.reopenConfirm',
        '返回修改目录后，全课小节教案、知识库、课程内容和发布确认都会失效，并按照新目录重新生成。',
      ),
      t('courseTasks.workflow.reopenTitle', '返回修改课程目录'),
      {
        type: 'warning',
        confirmButtonText: t('courseTasks.workflow.reopenAction', '返回并修改'),
        cancelButtonText: t('common.cancel', '取消'),
      },
    )
    await runAction(() => workspace.reopenGenerationStep(
      selectedTask.value!.courseId,
      'outline',
    ))
    await loadSelectedReview()
    ElMessage.success(t('courseTasks.workflow.reopened', '已返回目录步骤，可以修改后重新确认'))
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error(t('courseTasks.actionFailed', '任务操作失败'))
    }
  }
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
    await runAction(() => generationStore.deleteTask(task.courseId, task.id))
    selectedTaskId.value = tasks.value[0]?.id || ''
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
function pauseContinuesDraft(task: TaskView) {
  return (
    task.currentPhase === 'content_generation'
    || Boolean(task.recovery?.checkpoint?.draft_node_ids?.length)
  )
}
function pauseActionLabel(task: TaskView) {
  return pauseContinuesDraft(task)
    ? t('courseTasks.pauseKeepDraft', '暂停并保留草稿')
    : t('courseTasks.pauseRestartStep', '停止本步并保留检查点')
}
function pauseActionHelp(task: TaskView) {
  return pauseContinuesDraft(task)
    ? t('courseTasks.pauseKeepDraftHelp', '停止当前模型调用；已经保存的正文草稿会保留，恢复后从草稿继续。')
    : t('courseTasks.pauseRestartStepHelp', '停止当前模型调用；恢复后从最近完整产物继续，当前未完成步骤会重新生成。')
}
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
function formatTaskTime(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat(activeLocale.value === 'en' ? 'en-US' : 'zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}
function guidedStepLabel(step: GuidedGenerationStepKey) {
  return {
    requirements: t('courseTasks.workflow.requirements', '需求'),
    outline: t('courseTasks.workflow.outline', '目录'),
    teaching: t('courseTasks.workflow.teaching', '教案'),
    content: t('courseTasks.workflow.content', '课程生成'),
    release: t('courseTasks.workflow.release', '确认发布'),
  }[step]
}
function workflowStatusLabel(status: string) {
  return {
    locked: t('courseTasks.workflow.locked', '未开始'),
    pending: t('courseTasks.workflow.pending', '等待开始'),
    in_progress: t('courseTasks.workflow.inProgress', '生成中'),
    waiting_for_confirmation: t('courseTasks.workflow.waiting', '待确认'),
    confirmed: t('courseTasks.workflow.confirmed', '已确认'),
    needs_regeneration: t('courseTasks.workflow.needsRegeneration', '需要重做'),
    failed: t('courseTasks.workflow.failed', '失败'),
  }[status] || status
}
function learningAssetLabel(type: string) {
  return t(`courseTasks.review.assets.${type}`, {
    questions: '练习题',
    mastery_criteria: '掌握标准',
    misconceptions: '易错点',
    checklist: '检查清单',
    final_assessment: '综合检测',
    diagnostic_templates: '诊断题',
    remediation_units: '补救单元',
    validation_questions: '复验题',
    course_knowledge_map: '知识地图',
    course_knowledge_base: '知识库',
    knowledge_library: '知识库视图',
    overview: '课程总览',
    chapter_progression_contracts: '章节进阶规则',
  }[type] || type)
}
function reviewIssueMessage(issue: any) {
  if (String(issue?.code || '') === 'teaching_plan:local_fallback') {
    return t(
      'courseTasks.review.teachingPlanFallback',
      '部分教案单元使用本地保底生成，请重点复核标记小节的教学语义。',
    )
  }
  return String(issue?.message || issue || '')
}
function taskStepLabel(task: TaskView) {
  return courseProductionTaskDetail(task) || phaseLabel(task.currentPhase, task.status)
}
function phaseLabel(phase: string | undefined, status: Task['status']) {
  const labels: Record<string, string> = {
    requirement_analysis: t('courseTasks.phases.requirementAnalysis', '整理课程需求'),
    material_processing: t('courseTasks.phases.materialProcessing', '解析资料与证据'),
    pedagogy_resolution: t('courseTasks.phases.pedagogyResolution', '确定教学结构与难度'),
    outline_generation: t('courseTasks.phases.outlineGeneration', '生成轻量课程目录'),
    outline_validation: t('courseTasks.phases.outlineValidation', '检查课程目录'),
    outline_ready: t('courseTasks.phases.outlineReady', '等待确认课程目录'),
    outline_rebuild_required: t('courseTasks.phases.outlineRebuildRequired', '按完整课程模式重建目录'),
    outline_confirmed: t('courseTasks.phases.outlineConfirmed', '目录已确认'),
    course_teaching_plan: t('courseTasks.phases.courseTeachingPlan', '规划并汇编全课小节教案'),
    course_teaching_plan_skeleton: t('courseTasks.phases.courseTeachingPlanSkeleton', '冻结全课知识职责'),
    course_teaching_plan_skeleton_validation: t('courseTasks.phases.courseTeachingPlanSkeletonValidation', '检查全课知识职责'),
    course_teaching_plan_batch: t('courseTasks.phases.courseTeachingPlanBatch', '并行生成详细教案批次'),
    course_teaching_plan_batch_validation: t('courseTasks.phases.courseTeachingPlanBatchValidation', '检查当前详细教案批次'),
    course_teaching_plan_assembly: t('courseTasks.phases.courseTeachingPlanAssembly', '汇编唯一的全课教案'),
    course_teaching_plan_validation: t('courseTasks.phases.courseTeachingPlanValidation', '检查教案结构、知识与课程块绑定'),
    course_knowledge_index: t('courseTasks.phases.courseKnowledgeIndex', '迁移旧版整课知识索引'),
    course_knowledge_index_validation: t('courseTasks.phases.courseKnowledgeIndexValidation', '检查旧版知识索引'),
    course_knowledge_skeleton: t('courseTasks.phases.knowledgeSkeleton', '恢复旧版知识身份检查点'),
    course_knowledge_skeleton_validation: t('courseTasks.phases.knowledgeSkeletonValidation', '检查旧版知识身份检查点'),
    section_knowledge_generation: t('courseTasks.phases.sectionKnowledgeGeneration', '恢复旧版知识检查点'),
    section_knowledge_validation: t('courseTasks.phases.sectionKnowledgeValidation', '检查旧版知识检查点'),
    course_relation_generation: t('courseTasks.phases.courseRelationGeneration', '恢复旧版关系检查点'),
    course_relation_validation: t('courseTasks.phases.courseRelationValidation', '检查旧版关系检查点'),
    course_graph_generation: t('courseTasks.phases.courseGraphGeneration', '迁移旧版知识关系图'),
    course_graph_validation: t('courseTasks.phases.courseGraphValidation', '检查旧版关系图结构'),
    knowledge_mapping: t('courseTasks.phases.knowledgeMapping', '编译全课知识关系'),
    course_knowledge_blueprint: t('courseTasks.phases.knowledgeMapping', '编译全课知识关系'),
    knowledge_ready: t('courseTasks.phases.knowledgeReady', '迁移旧版知识确认点'),
    knowledge_confirmed: t('courseTasks.phases.knowledgeConfirmed', '旧版知识确认点已迁移'),
    teaching_ready: t('courseTasks.phases.teachingReady', '迁移旧版教案确认点'),
    teaching_confirmed: t('courseTasks.phases.teachingConfirmed', '旧版教案确认点已迁移'),
    blueprint_generation: t('courseTasks.phases.blueprintGeneration', '生成课程蓝图'),
    blueprint_validation: t('courseTasks.phases.blueprintValidation', '检查课程蓝图'),
    blueprint_ready: t('courseTasks.phases.blueprintReady', '等待确认课程蓝图'),
    content_generation: t('courseTasks.phases.contentGeneration', '生成课程内容'),
    content_partial: t('courseTasks.phases.contentPartial', '正文已部分完成，可从保存点继续'),
    content_and_course_graph_generation: t('courseTasks.phases.contentAndCourseGraphGeneration', '恢复旧版正文与图谱并行检查点'),
    learning_assets: t('courseTasks.phases.learningAssets', '生成练习与综合测评'),
    question_bank: t('courseTasks.phases.questionBank', '整理题库、联网补充与风险审核'),
    content_validation: t('courseTasks.phases.contentValidation', '检查结构、引用、答案合同与覆盖'),
    question_analysis: t('courseTasks.phases.questionAnalysis', '编译题目考查与答案合同'),
    content_ready: t('courseTasks.phases.contentReady', '等待确认课程内容'),
    content_confirmed: t('courseTasks.phases.contentConfirmed', '课程内容已确认'),
    release_ready: t('courseTasks.phases.releaseReady', '等待确认发布'),
    release_confirmed: t('courseTasks.phases.releaseConfirmed', '正在发布课程'),
    resuming: t('courseTasks.phases.resuming', '从保存点恢复'),
    recovery_unavailable: t('courseTasks.phases.recoveryUnavailable', '无法恢复原任务'),
    quality_failed: t('courseTasks.phases.qualityFailed', '结构检查未通过'),
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
    waiting_for_review: t('courseLibrary.status.waitingReview', '等待你的确认'), conflict: t('courseLibrary.status.conflict', '需要确认'),
    error: t('courseLibrary.status.error', '生成失败'), completed_with_warnings: t('courseLibrary.status.warnings', '生成完成但有警告'),
    completed: t('courseLibrary.status.ready', '可以学习'),
  }
  return labels[status]
}
function problemTitle(task: TaskView) {
  if (task.status === 'completed_with_warnings' && task.recovery?.state === 'completed') {
    return t('courseTasks.problem.publishedWarning', '课程已经发布，仍有优化建议')
  }
  if (task.recovery?.state === 'quality_blocked') return t('courseTasks.problem.qualityBlocked', '内容已生成，但结构或引用检查未通过')
  if (task.recovery?.state === 'unavailable') return t('courseTasks.problem.unavailable', '原任务没有可用的恢复点')
  if (task.status === 'error' && restartsCurrentStage(task)) {
    return t('courseTasks.problem.restartStage', '生成中断，可以重试当前阶段')
  }
  if (task.status === 'error') return t('courseTasks.problem.failed', '生成中断，可以从保存点继续')
  if (task.status === 'conflict') return t('courseTasks.problem.conflict', '当前任务需要人工确认')
  return t('courseTasks.problem.warning', '课程已生成，但仍有质量警告')
}
function problemHelp(task: TaskView) {
  if (task.status === 'completed_with_warnings' && task.recovery?.state === 'completed') {
    return t('courseTasks.problem.publishedWarningHelp', '课程可以正常学习；这些建议用于后续局部优化，不需要重新生成整门课程。')
  }
  if (task.recovery?.state === 'quality_blocked') return t('courseTasks.problem.qualityBlockedHelp', '重复生成不会绕过同一结构错误；请先查看引用、绑定和版本链，再决定局部处理。')
  if (task.recovery?.state === 'unavailable') return t('courseTasks.problem.unavailableHelp', '为避免覆盖现有内容，系统不会盲目重跑这个旧任务。')
  if (task.status === 'error' && restartsCurrentStage(task)) {
    return t('courseTasks.problem.restartStageHelp', '继续后会复用已保存的课程需求和资料处理结果，重新生成课程目录，不会新建重复课程。')
  }
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
function restartsCurrentStage(task: TaskView) {
  const checkpoint = task.recovery?.checkpoint
  return task.recovery?.reason_code === 'stage_restart_available'
    || Boolean(checkpoint && !checkpoint.outline_ready && !checkpoint.total_nodes)
}
function resumeActionLabel(task: TaskView) {
  return restartsCurrentStage(task)
    ? t('courseTasks.retryStage', '重试当前阶段')
    : t('courseTasks.resumeCheckpoint', '从保存点继续')
}
function recoveryCheckpointLabel(task: TaskView) {
  const checkpoint = task.recovery?.checkpoint
  if (!checkpoint) return ''
  const teachingBatchCompleted = Number(checkpoint.completed_teaching_plan_batches || 0)
  const teachingBatchTotal = Number(checkpoint.total_teaching_plan_batches || 0)
  const teachingSectionCompleted = Number(checkpoint.completed_teaching_plan_sections || 0)
  const teachingSectionTotal = Number(checkpoint.total_teaching_plan_sections || 0)
  const nextTeachingBatch = Number(checkpoint.next_teaching_plan_batch_index || 0)
  const knowledgeCompleted = Number(checkpoint.completed_knowledge_packages || 0)
  const knowledgeTotal = Number(checkpoint.total_knowledge_packages || 0)
  if (checkpoint.teaching_plan_ready && !checkpoint.completed_nodes) {
    return t('courseTasks.recovery.teachingPlanCheckpoint', '全课小节教案、知识库与关系图已保留，可直接继续生成正文')
  }
  if (teachingBatchTotal && teachingBatchCompleted < teachingBatchTotal) {
    return t('courseTasks.recovery.teachingPlanBatchCheckpoint', '已保留 {sections}/{totalSections} 个小节教案，可从第 {batch} 批继续；正文尚未开始')
      .replace('{sections}', String(teachingSectionCompleted))
      .replace('{totalSections}', String(teachingSectionTotal))
      .replace('{batch}', String(nextTeachingBatch || teachingBatchCompleted + 1))
  }
  if (knowledgeTotal && knowledgeCompleted === knowledgeTotal && !checkpoint.completed_nodes) {
    return t('courseTasks.recovery.knowledgeCheckpoint', '旧版知识检查点已迁移，覆盖 {completed}/{total} 个小节')
      .replace('{completed}', String(knowledgeCompleted))
      .replace('{total}', String(knowledgeTotal))
  }
  if (knowledgeTotal && knowledgeCompleted && !checkpoint.completed_nodes) {
    return t('courseTasks.recovery.legacyKnowledgeCheckpoint', '目录与旧版知识检查点已保留，完成 {completed}/{total}')
      .replace('{completed}', String(knowledgeCompleted))
      .replace('{total}', String(knowledgeTotal))
  }
  if (checkpoint.outline_ready && !checkpoint.total_nodes) {
    return t('courseTasks.recovery.outlineCheckpoint', '课程目录已保留，可从全课知识职责阶段继续')
  }
  if (!checkpoint.outline_ready && !checkpoint.total_nodes) {
    return checkpoint.requirements_ready
      ? t('courseTasks.recovery.requirementsCheckpoint', '已保存课程需求和资料处理结果；继续后将重新生成课程目录')
      : t('courseTasks.recovery.stageRetry', '尚未生成课程内容；继续后将重试当前阶段')
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
.guided-workflow { padding:22px 0; border-bottom:1px solid var(--lz-border); }
.guided-workflow ol { margin:0; padding:0; display:grid; grid-template-columns:repeat(6,minmax(0,1fr)); list-style:none; }
.guided-workflow li { position:relative; min-width:0; display:grid; justify-items:center; gap:7px; color:var(--lz-text-muted); text-align:center; }
.guided-workflow li:not(:last-child)::after { content:""; position:absolute; z-index:0; top:14px; left:calc(50% + 18px); right:calc(-50% + 18px); height:1px; background:var(--lz-border); }
.guided-workflow__step { min-width:0; width:100%; display:grid; justify-items:center; gap:7px; padding:0 3px; border:0; color:inherit; background:transparent; text-align:center; }
.guided-workflow__step:disabled { cursor:default; }.guided-workflow__step:not(:disabled) { cursor:pointer; }.guided-workflow__step:not(:disabled):hover .guided-workflow__marker { transform:translateY(-2px); box-shadow:0 5px 13px rgba(15,23,42,.12); }
.guided-workflow__marker { position:relative; z-index:1; width:29px; height:29px; display:grid; place-items:center; border:1px solid var(--lz-border); border-radius:50%; color:var(--lz-text-muted); background:#fff; font-family:ui-monospace,monospace; font-size:10px; font-weight:750; }
.guided-workflow__marker { transition:transform .16s ease,box-shadow .16s ease; }.guided-workflow__copy { min-width:0; max-width:100%; }
.guided-workflow li strong,.guided-workflow li small { display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.guided-workflow li strong { color:var(--lz-text-secondary); font-size:10px; }.guided-workflow li small { margin-top:3px; font-size:9px; }
.guided-workflow li[data-status="confirmed"] .guided-workflow__marker { border-color:rgba(5,150,105,.3); color:var(--lz-success); background:var(--lz-success-soft); }
.guided-workflow li[data-status="confirmed"]:not(:last-child)::after { background:rgba(5,150,105,.35); }
.guided-workflow li[data-status="in_progress"] .guided-workflow__marker,.guided-workflow li[data-status="waiting_for_confirmation"] .guided-workflow__marker { border-color:rgba(79,70,229,.32); color:var(--lz-brand-strong); background:var(--lz-brand-soft); box-shadow:0 0 0 4px rgba(99,102,241,.06); }
.guided-workflow li[data-status="in_progress"] strong,.guided-workflow li[data-status="waiting_for_confirmation"] strong { color:var(--lz-text-strong); }
.guided-workflow li[data-status="needs_regeneration"] .guided-workflow__marker,.guided-workflow li[data-status="failed"] .guided-workflow__marker { border-color:rgba(217,119,6,.3); color:var(--lz-warning); background:var(--lz-warning-soft); }
.generation-review { padding:24px 0 4px; }.generation-review > header { display:flex; align-items:flex-start; justify-content:space-between; gap:14px; margin-bottom:16px; }.generation-review > header > div { position:relative; padding-left:42px; }.generation-review__step { position:absolute; left:0; top:-2px; width:31px; height:31px; display:grid; place-items:center; border-radius:8px; color:var(--lz-brand-strong); background:var(--lz-brand-soft); font-family:ui-monospace,monospace; font-size:10px; font-weight:800; }.generation-review h4 { margin:0; color:var(--lz-text-strong); font-size:14px; }.generation-review header p { margin:5px 0 0; color:var(--lz-text-muted); font-size:11px; }
.blueprint-course-name span { display:block; margin-bottom:6px; color:var(--lz-text-muted); font-size:10px; }.blueprint-course-name input,.blueprint-nodes input,.blueprint-nodes textarea { width:100%; border:1px solid var(--lz-border); border-radius:7px; color:var(--lz-text); background:#fff; outline:none; }.blueprint-course-name input { height:38px; padding:0 10px; font-weight:650; }.blueprint-nodes { margin-top:12px; }.blueprint-nodes article { display:grid; grid-template-columns:28px minmax(0,1fr); gap:9px; padding:11px 0; border-top:1px solid rgba(226,232,240,.76); }.blueprint-nodes article > span { padding-top:9px; color:var(--lz-text-muted); font-size:10px; font-family:ui-monospace,monospace; }.blueprint-nodes input { height:36px; padding:0 9px; font-size:12px; font-weight:650; }.blueprint-nodes textarea { min-height:54px; margin-top:6px; padding:8px 9px; resize:vertical; font-size:11px; line-height:1.45; }.blueprint-course-name input:focus,.blueprint-nodes input:focus,.blueprint-nodes textarea:focus { border-color:var(--lz-brand); box-shadow:0 0 0 3px rgba(99,102,241,.08); }.blueprint-error,.blueprint-empty { color:var(--lz-warning); font-size:11px; }
.review-metrics { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:9px; margin-bottom:15px; }.review-metrics div { padding:13px; border:1px solid var(--lz-border); border-radius:9px; background:var(--lz-surface-muted); }.review-metrics strong,.review-metrics span { display:block; }.review-metrics strong { color:var(--lz-text-strong); font-size:20px; }.review-metrics span { margin-top:3px; color:var(--lz-text-muted); font-size:9px; }
.knowledge-scope { margin-bottom:16px; padding:14px; border:1px solid rgba(14,116,144,.16); border-radius:10px; background:rgba(236,254,255,.58); }.knowledge-scope > header strong,.knowledge-scope > header span { display:block; }.knowledge-scope > header strong { color:var(--lz-text-strong); font-size:12px; }.knowledge-scope > header span { margin-top:4px; color:var(--lz-text-secondary); font-size:10px; line-height:1.5; }.knowledge-scope > div { margin-top:10px; display:grid; gap:7px; }.knowledge-scope article { display:grid; grid-template-columns:34px minmax(0,1fr); gap:8px; padding-top:8px; border-top:1px solid rgba(14,116,144,.12); }.knowledge-scope article > span { color:#0e7490; font-family:ui-monospace,monospace; font-size:9px; font-weight:800; }.knowledge-scope article strong { display:block; color:var(--lz-text-strong); font-size:11px; }.knowledge-scope article p { margin:3px 0 0; color:var(--lz-text-secondary); font-size:9px; line-height:1.45; }.knowledge-scope article small { display:block; margin-top:4px; color:#0e7490; font-size:9px; line-height:1.4; }
.knowledge-relations { margin-top:16px; }.knowledge-relations > strong { color:var(--lz-text-strong); font-size:11px; }.knowledge-relations ul { margin:8px 0 0; padding:0; display:grid; gap:6px; list-style:none; }.knowledge-relations li { display:grid; grid-template-columns:minmax(0,1fr) 14px minmax(0,1fr); align-items:center; gap:5px; padding:8px 9px; border:1px solid var(--lz-border); border-radius:7px; color:var(--lz-text-secondary); background:var(--lz-surface-muted); font-size:9px; }.knowledge-relations li b { color:var(--lz-brand-strong); text-align:center; }.knowledge-relations li small { grid-column:1 / -1; color:var(--lz-text-muted); line-height:1.4; }
.composition-review { margin-bottom:16px; padding:14px; border:1px solid rgba(99,102,241,.18); border-radius:10px; background:var(--lz-brand-soft); }.composition-review__heading > span,.composition-review__rhythm > span { display:block; margin-bottom:3px; color:var(--lz-text-muted); font-size:9px; }.composition-review__heading strong { color:var(--lz-text-strong); font-size:14px; }.composition-review__heading p,.composition-review__rhythm p { margin:4px 0 0; color:var(--lz-text-secondary); font-size:10px; line-height:1.5; }.composition-review__rhythm { margin-top:10px; padding-top:10px; border-top:1px solid rgba(99,102,241,.12); }.role-distribution { display:flex; flex-wrap:wrap; gap:6px; margin:11px 0 0; }.role-distribution div { display:inline-flex; align-items:center; gap:5px; padding:4px 7px; border:1px solid rgba(99,102,241,.14); border-radius:999px; color:var(--lz-text-secondary); background:#fff; }.role-distribution dt,.role-distribution dd { margin:0; font-size:9px; }.role-distribution dd { color:var(--lz-brand-strong); font-weight:800; }
.review-cards { border-top:1px solid var(--lz-border); }.review-cards article { display:grid; grid-template-columns:30px minmax(0,1fr); gap:10px; padding:12px 0; border-bottom:1px solid rgba(226,232,240,.75); }.review-cards article > span { color:var(--lz-text-muted); font-family:ui-monospace,monospace; font-size:9px; }.review-cards strong { display:block; color:var(--lz-text-strong); font-size:12px; }.review-cards p { margin:4px 0 0; color:var(--lz-text-secondary); font-size:10px; line-height:1.5; }.review-cards small { display:block; margin-top:6px; color:var(--lz-brand-strong); font-size:9px; line-height:1.45; }.review-cards--compact article { padding:9px 0; }
.module-sequence { display:flex; flex-wrap:wrap; gap:6px; margin-top:10px; }.module-sequence__item { position:relative; min-width:130px; max-width:220px; display:grid; gap:2px; padding:7px 8px; border-left:2px solid var(--lz-border); color:var(--lz-text-secondary); background:var(--lz-surface-muted); }.module-sequence__item[data-added="true"] { border-left-color:var(--lz-brand); background:var(--lz-brand-soft); }.module-sequence__item[data-source="difficulty_level"] { border-left-color:var(--lz-warning); background:var(--lz-warning-soft); }.module-sequence__item b { overflow:hidden; color:var(--lz-text-strong); font-size:9px; text-overflow:ellipsis; white-space:nowrap; }.module-sequence__item em { color:var(--lz-text-muted); font-size:8px; font-style:normal; line-height:1.35; }.module-sequence__item i { color:var(--lz-brand-strong); font-size:8px; font-style:normal; font-weight:700; }.module-sequence__item[data-source="difficulty_level"] i { color:var(--lz-warning); }
.review-callout,.release-verdict { display:flex; gap:11px; align-items:flex-start; padding:14px; border:1px solid rgba(99,102,241,.18); border-radius:10px; color:var(--lz-brand-strong); background:var(--lz-brand-soft); }.review-callout strong,.release-verdict strong { display:block; color:var(--lz-text-strong); font-size:12px; }.review-callout p,.release-verdict p { margin:4px 0 0; color:var(--lz-text-secondary); font-size:10px; line-height:1.5; }
.content-evidence { margin:10px 0; display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:8px; }.content-evidence > div { padding:10px; border:1px solid var(--lz-border); border-radius:8px; background:var(--lz-surface-muted); }.content-evidence span,.content-evidence strong { display:block; }.content-evidence span { color:var(--lz-text-muted); font-size:9px; }.content-evidence strong { margin-top:4px; color:var(--lz-text-strong); font-size:13px; }.asset-counts { display:flex; flex-wrap:wrap; gap:5px; margin-bottom:10px; }.asset-counts span { padding:4px 7px; border:1px solid rgba(99,102,241,.14); border-radius:999px; color:var(--lz-brand-strong); background:var(--lz-brand-soft); font-size:8px; font-weight:650; }
.question-review { margin:14px 0; padding:14px; border:1px solid rgba(14,116,144,.16); border-radius:10px; background:rgba(236,254,255,.42); }.question-review>header { display:flex; justify-content:space-between; align-items:flex-start; gap:14px; }.question-review>header strong { color:var(--lz-text-strong); font-size:12px; }.question-review>header p { margin:4px 0 0; max-width:460px; color:var(--lz-text-secondary); font-size:9px; line-height:1.5; }.question-review>header>span { flex:0 0 auto; padding:5px 8px; border-radius:999px; color:#047857; background:#ecfdf5; font-size:9px; font-weight:800; }.question-review>header>span[data-blocked="true"] { color:var(--lz-warning); background:var(--lz-warning-soft); }.question-review__list { margin-top:12px; display:grid; gap:8px; }.question-review__list>article { display:grid; grid-template-columns:28px minmax(0,1fr); gap:9px; padding:10px; border:1px solid rgba(14,116,144,.12); border-radius:8px; background:#fff; }.question-review__list>article[data-status="blocked"] { border-color:rgba(217,119,6,.28); }.question-review__index { color:#0e7490; font-family:ui-monospace,monospace; font-size:9px; font-weight:800; }.question-review__meta { display:flex; justify-content:space-between; gap:8px; margin-bottom:5px; color:var(--lz-text-muted); font-size:8px; }.question-review__meta b { color:#0e7490; }.question-review__list article>div>strong { display:block; color:var(--lz-text-strong); font-size:10px; line-height:1.5; }.question-review dl { display:grid; grid-template-columns:1fr 1fr; gap:10px; margin:9px 0; }.question-review dt { color:var(--lz-text-muted); font-size:8px; }.question-review dd { margin:3px 0 0; color:var(--lz-text-secondary); font-size:9px; line-height:1.45; }.question-review__targets { display:flex; flex-wrap:wrap; gap:4px; }.question-review__targets span { padding:3px 6px; border-radius:999px; color:#0e7490; background:#ecfeff; font-size:8px; }.question-review__targets span[data-kind="mistake"] { color:#c2410c; background:#fff7ed; }.question-review ul { margin:8px 0 0; padding-left:16px; color:var(--lz-warning); font-size:9px; line-height:1.5; }
.release-verdict[data-pass="false"] { border-color:rgba(217,119,6,.2); color:var(--lz-warning); background:var(--lz-warning-soft); }.release-issues { margin:12px 0 0; padding:0 0 0 18px; color:var(--lz-warning); font-size:10px; line-height:1.6; }
.task-notice { margin-top:20px; display:flex; gap:10px; padding:13px 14px; border-left:3px solid var(--lz-warning); color:var(--lz-warning); background:var(--lz-warning-soft); }.task-notice strong { display:block; font-size:12px; }.task-notice p { margin:4px 0 0; font-size:11px; line-height:1.5; }.task-error-detail,.recovery-checkpoint { display:block; margin-top:7px; color:inherit; font-size:9px; line-height:1.5; opacity:.88; }
.task-actions { display:flex; flex-wrap:wrap; align-items:center; gap:8px; padding:13px clamp(20px,4vw,38px); border-top:1px solid var(--lz-border); background:rgba(255,255,255,.98); box-shadow:0 -8px 22px rgba(15,23,42,.035); }.task-actions__open { margin-left:auto; }
.primary-button,.secondary-button,.danger-button { min-height:38px; display:inline-flex; align-items:center; justify-content:center; gap:7px; padding:0 13px; border-radius:8px; font-size:12px; font-weight:700; cursor:pointer; }.primary-button { border:1px solid var(--lz-brand-strong); color:#fff; background:var(--lz-brand-strong); }.secondary-button { border:1px solid var(--lz-border); color:var(--lz-text-secondary); background:#fff; }.danger-button { border:1px solid rgba(185,28,28,.22); color:var(--lz-danger); background:var(--lz-danger-soft); }.primary-button:disabled,.secondary-button:disabled,.danger-button:disabled,.icon-button:disabled { cursor:not-allowed; opacity:.5; }
.spin { animation:spin 1s linear infinite; }@keyframes spin { to { transform:rotate(360deg); } }
@media (max-width:720px) { .task-center-layer { align-items:end; padding:0; }.task-center { width:100%; height:calc(100vh - 56px); border-radius:14px 14px 0 0; }.task-center__body { grid-template-columns:1fr; grid-template-rows:auto minmax(0,1fr); }.task-list { max-height:168px; border-right:0; border-bottom:1px solid var(--lz-border); }.task-detail__scroll { padding:20px 16px 14px; }.task-actions { padding:12px 16px calc(12px + env(safe-area-inset-bottom)); }.task-summary dl { grid-template-columns:1fr 1fr; }.task-actions__open { margin-left:0; }.guided-workflow ol { grid-template-columns:repeat(3,minmax(0,1fr)); row-gap:18px; }.guided-workflow li:nth-child(3n)::after { display:none; }.review-metrics { grid-template-columns:1fr 1fr 1fr; } }
</style>
