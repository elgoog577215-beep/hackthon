<template>
  <Teleport to="body" :disabled="embedded">
    <div v-if="modelValue" class="task-center-layer" :class="{ 'task-center-layer--embedded': embedded }" @keydown="handleDialogKeydown">
      <button v-if="!embedded" type="button" class="task-center-backdrop" :aria-label="t('common.cancel', '取消')" @click="close" />
      <section
        ref="panelRef"
        class="task-center"
        :class="{
          'task-center--embedded': embedded,
          'task-center--empty': !tasks.length,
        }"
        :role="embedded ? 'region' : 'dialog'"
        :aria-modal="embedded ? undefined : true"
        :aria-labelledby="embedded ? undefined : titleId"
        :aria-label="embedded ? t('courseTasks.title', '课程任务中心') : undefined"
        tabindex="-1"
      >
        <header v-if="!embedded" class="task-center__header">
          <div>
            <span><ListChecks :size="16" /></span>
            <div>
              <p>{{ t('courseTasks.eyebrow', '后台处理') }}</p>
              <h2 :id="titleId">{{ t('courseTasks.title', '课程任务中心') }}</h2>
            </div>
          </div>
          <div class="task-center__header-actions">
            <button type="button" class="icon-button" :title="t('courseTasks.refresh', '刷新任务')" :disabled="refreshing" @click="refresh">
              <RefreshCw :size="17" :class="{ spin: refreshing }" />
            </button>
            <button type="button" class="icon-button" :title="t('common.cancel', '取消')" @click="close"><X :size="18" /></button>
          </div>
        </header>

        <div class="task-center__body" :class="{ 'task-center__body--empty': !tasks.length }">
          <main v-if="!tasks.length" class="task-center-empty">
            <span class="task-center-empty__icon">
              <Inbox :size="23" />
            </span>
            <strong>{{ props.courseId ? (activeLocale === 'en' ? 'No tasks for this course' : '当前课程暂无任务') : t('courseTasks.empty', '暂无课程任务') }}</strong>
            <p>{{ props.courseId ? (activeLocale === 'en' ? 'There are no running or recoverable tasks for this course.' : '当前课程没有正在处理或可恢复的任务。') : t('courseTasks.emptyHelp', '新建或导入课程后，处理状态会出现在这里。') }}</p>
          </main>

          <template v-else>
          <aside class="task-list" :aria-label="t('courseTasks.listLabel', '课程任务列表')">
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
                  {{ statusLabel(task.status, task.recovery, task.taskType) }} · {{ taskDisplayProgress(task) }}%
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
                  <div class="task-summary__chips">
                    <span class="task-kind-chip">{{ taskKindLabel(selectedTask) }}</span>
                    <span class="status-chip" :data-status="selectedTask.status">{{ statusLabel(selectedTask.status, selectedTask.recovery, selectedTask.taskType) }}</span>
                  </div>
                  <h3>{{ selectedTask.courseName }}</h3>
                  <p v-if="['running', 'pending', 'paused', 'waiting_for_review'].includes(selectedTask.status)" class="task-summary__live-status" role="status" aria-live="polite" aria-atomic="true">{{ taskStepLabel(selectedTask) }}</p>
                </div>
                <strong>{{ selectedDisplayProgress }}%</strong>
              </div>
              <div
                class="task-progress"
                role="progressbar"
                :aria-valuenow="selectedDisplayProgress"
                aria-valuemin="0"
                aria-valuemax="100"
                :aria-valuetext="`${taskPhaseLabel(selectedTask)}，${selectedDisplayProgress}%`"
              >
                <span :style="{ transform: `scaleX(${selectedDisplayProgress / 100})` }" />
              </div>
              <dl>
                <div><dt>{{ t('courseTasks.phase', '当前阶段') }}</dt><dd>{{ taskPhaseLabel(selectedTask) }}</dd></div>
                <div v-if="phaseItemProgress"><dt>{{ phaseItemProgress.label }}</dt><dd>{{ phaseItemProgress.completed }} / {{ phaseItemProgress.total }}</dd></div>
                <div v-else-if="selectedProgress?.totalNodes"><dt>{{ t('courseTasks.nodes', '内容进度') }}</dt><dd>{{ selectedProgress.completedNodes }} / {{ selectedProgress.totalNodes }}</dd></div>
                <div v-else-if="selectedTask.recovery?.checkpoint.total_nodes"><dt>{{ t('courseTasks.nodes', '内容进度') }}</dt><dd>{{ selectedTask.recovery.checkpoint.completed_nodes }} / {{ selectedTask.recovery.checkpoint.total_nodes }}</dd></div>
                <div v-if="selectedProgress?.estimatedTimeRemaining"><dt>{{ t('courseTasks.remaining', '预计剩余') }}</dt><dd>{{ formatDuration(selectedProgress.estimatedTimeRemaining) }}</dd></div>
                <div v-if="selectedTask.heartbeatAt"><dt>{{ t('taskObservability.lastHeartbeat', '最后更新') }}</dt><dd>{{ formatTaskTime(selectedTask.heartbeatAt) }}</dd></div>
              </dl>
            </section>

            <details class="task-detail-group task-detail-group--technical">
              <summary>{{ activeLocale === 'en' ? 'Processing details' : '处理详情' }}</summary>
            <section class="task-observability" :aria-label="t('taskObservability.label', '任务处理阶段')">
              <ol>
                <li
                  v-for="stage in selectedObservableStages"
                  :key="stage.key"
                  class="task-observability__stage"
                  :data-status="stage.status"
                  :aria-current="stage.status === 'active' || stage.status === 'error' || stage.status === 'paused' ? 'step' : undefined"
                >
                  <span class="task-observability__marker">
                    <CircleCheck v-if="stage.status === 'completed'" :size="13" />
                    <TriangleAlert v-else-if="stage.status === 'error' || stage.status === 'blocked'" :size="13" />
                    <CirclePause v-else-if="stage.status === 'paused'" :size="13" />
                    <LoaderCircle v-else-if="stage.status === 'active'" class="spin" :size="13" />
                    <CircleDashed v-else :size="13" />
                  </span>
                  <strong>{{ stage.label }}</strong>
                  <small>{{ observableStageStatusLabel(stage.status) }}</small>
                </li>
              </ol>
              <p v-if="selectedHeartbeat.state === 'stalled'" class="task-heartbeat-alert" role="status">
                <Clock3 :size="15" />
                {{ t('taskObservability.stalled', '任务长时间没有更新，可能已经停滞；请先刷新状态，再决定暂停或恢复。') }}
              </p>
            </section>
            </details>

            <section
              v-if="webSearchSummary"
              class="web-search-summary"
              data-testid="web-search-summary"
              :aria-label="t('courseGeneration.materials.webSearch.reviewTitle', '联网资料审阅')"
            >
              <header class="web-search-summary__head">
                <strong>{{ t('courseGeneration.materials.webSearch.label', '联网资料') }}</strong>
                <span class="web-search-summary__status" :data-degraded="webSearchSummary.degraded">
                  {{ webSearchSummary.statusLabel }}
                </span>
              </header>
              <p v-if="webSearchSummary.degraded" class="web-search-summary__degraded" role="status">
                {{ webSearchSummary.message || t('courseGeneration.materials.webSearch.degraded', '本次未获取联网资料，仅使用已有资料') }}
              </p>
              <p class="web-search-summary__hint">
                {{ t('courseGeneration.materials.webSearch.reviewHint', '采用前请确认出处与内容适用性；引用内容会保留出处，不作为原创产物。') }}
              </p>
              <div v-if="webSearchSummary.queries.length" class="web-search-summary__queries">
                <dt>{{ t('courseGeneration.materials.webSearch.queries', '检索关键词') }}</dt>
                <dd>
                  <span v-for="query in webSearchSummary.queries" :key="query">{{ query }}</span>
                </dd>
              </div>
              <ul v-if="webSearchSummary.sources.length" class="web-search-summary__sources">
                <li
                  v-for="source in webSearchSummary.sources"
                  :key="source.sourceId || source.url"
                  :data-excluded="source.excluded"
                >
                  <div class="web-search-summary__source-line">
                    <a :href="source.url" target="_blank" rel="noopener noreferrer nofollow">{{ source.title }}</a>
                    <button
                      type="button"
                      class="web-search-summary__exclude"
                      :data-testid="`web-source-toggle-${source.sourceId || source.url}`"
                      :aria-pressed="source.excluded"
                      @click="toggleWebSourceExclusion(source)"
                    >
                      {{ source.excluded
                        ? t('courseGeneration.materials.webSearch.restore', '恢复')
                        : t('courseGeneration.materials.webSearch.exclude', '剔除这条') }}
                    </button>
                  </div>
                  <small>
                    <template v-if="source.excluded">
                      {{ t('courseGeneration.materials.webSearch.excluded', '已剔除') }} ·
                    </template>
                    {{ t('courseGeneration.materials.webSearch.trustValue', '可信度：{value}')
                        .replace('{value}', t(`courseGeneration.materials.webSearch.trustLevel.${source.credibility}`, source.credibility)) }}
                    · {{ t('courseGeneration.materials.webSearch.fetchedAtValue', '抓取时间：{value}')
                        .replace('{value}', source.retrievedAt) }}
                  </small>
                </li>
              </ul>
              <p v-if="excludedWebSourceIds.length" class="web-search-summary__pending" role="status">
                {{ t('courseGeneration.materials.webSearch.excludePending', '剔除将在下次生成时生效').replace('{count}', String(excludedWebSourceIds.length)) }}
              </p>
              <p v-else-if="!webSearchSummary.degraded" class="web-search-summary__empty">
                {{ t('courseGeneration.materials.webSearch.none', '本次没有联网资料') }}
              </p>
              <details v-if="webSearchSummary.rejected.length" class="web-search-summary__rejected">
                <summary>
                  {{ t('courseGeneration.materials.webSearch.rejectedCount', '已排除 {count} 条').replace('{count}', String(webSearchSummary.rejected.length)) }}
                </summary>
                <ul>
                  <li v-for="item in webSearchSummary.rejected" :key="item.url">
                    <span>{{ item.url }}</span>
                    <small>{{ item.reasonLabel }}</small>
                  </li>
                </ul>
              </details>
            </section>

            <details v-if="workflowSteps.length" class="task-detail-group">
              <summary>{{ activeLocale === 'en' ? 'Generation steps' : '生成步骤' }}</summary>
            <section class="guided-workflow" :aria-label="t('courseTasks.workflow.label', '课程生成四步流程')">
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
            </details>

            <section v-if="shouldShowGenerationReview(selectedTask)" class="generation-review">
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
                <section v-if="releaseIssues.length" class="quality-blockers" :aria-labelledby="qualityBlockersId">
                  <header>
                    <h5 :id="qualityBlockersId">{{ t('courseTasks.review.blockersTitle', '具体阻断项') }}</h5>
                    <span>{{ t('courseTasks.review.blockerCount', '共 {count} 项阻断').replace('{count}', String(releaseIssues.length)) }}</span>
                  </header>
                  <ol class="quality-blocker-list">
                    <li v-for="(issue, index) in releaseIssues" :key="qualityIssueKey(issue, index)">
                      <div class="quality-blocker-list__meta">
                        <code>{{ issue.code || issue.issue_id || t('courseTasks.review.qualityGate', '质量门禁') }}</code>
                        <span v-if="reviewIssueTarget(issue)">{{ t('courseTasks.review.target', '目标') }}：{{ reviewIssueTarget(issue) }}</span>
                      </div>
                      <strong>{{ reviewIssueMessage(issue) }}</strong>
                      <p v-if="reviewIssueSuggestion(issue)">{{ t('courseTasks.review.suggestion', '建议动作') }}：{{ reviewIssueSuggestion(issue) }}</p>
                    </li>
                  </ol>
                </section>
              </template>
              <p v-else-if="reviewError" class="blueprint-error">{{ reviewError }}</p>
            </section>

            <section v-if="selectedTask.status === 'error' || selectedTask.status === 'completed_with_warnings' || selectedTask.status === 'conflict'" class="task-notice" :data-status="selectedTask.status">
              <TriangleAlert :size="18" />
              <div>
                <strong>{{ problemTitle(selectedTask) }}</strong>
                <p>{{ selectedError.message || problemHelp(selectedTask) }}</p>
                <details v-if="selectedError.technicalDetail" class="task-error-detail">
                  <summary>{{ t('courseTasks.problem.technicalReason', '查看技术原因') }}</summary>
                  <code>{{ selectedError.technicalDetail }}</code>
                </details>
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
            <p>{{ t('courseTasks.select', '选择一个任务查看处理详情。') }}</p>
          </main>
          </template>
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
import {
  qualityIssueKey,
  reviewBlockingIssues,
  reviewIssueMessage,
  reviewIssueSuggestion,
  reviewIssueTarget,
} from '@/utils/review-issues'
import { taskProgressStep } from '@/utils/course-progress'
import { courseProductionTaskDetail } from '@/utils/course-production'
import {
  observableTaskPhase,
  observableTaskStages,
  taskDisplayProgress,
  taskHeartbeatState,
  taskUserError,
  type ObservableTaskStageStatus,
} from '@/utils/task-observability'

type TaskView = Task

const props = withDefaults(defineProps<{ modelValue: boolean; courseId?: string; embedded?: boolean }>(), {
  courseId: '',
  embedded: false,
})
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()
const router = useRouter()
const courseStore = useCourseStore()
const generationStore = useGenerationStore()
const workspace = useCourseWorkspaceStore()
const titleId = `course-task-center-${Math.random().toString(36).slice(2)}`
const qualityBlockersId = `${titleId}-quality-blockers`
const panelRef = ref<HTMLElement | null>(null)
const selectedTaskId = ref('')
const refreshing = ref(false)
const acting = ref(false)
const blueprintDraft = ref<any>(null)
const generationReview = ref<any>(null)
const reviewError = ref('')
const previousFocus = ref<HTMLElement | null>(null)

const tasks = computed<TaskView[]>(() => {
  const byTaskId = new Map<string, TaskView>()
  for (const raw of generationStore.globalTasks || []) {
    const local = generationStore.getTask(raw.course_id)
    const matchingLocal = local?.id === raw.id ? local : undefined
    byTaskId.set(raw.id, {
      id: raw.id,
      courseId: raw.course_id,
      courseName: raw.course_name || matchingLocal?.courseName || t('courseTasks.untitled', '未命名课程'),
      taskType: String(raw.type || matchingLocal?.taskType || 'course_generation'),
      status: normalizeStatus(raw.status),
      progress: Math.max(0, Math.min(100, Number(raw.progress || 0))),
      currentStep: taskProgressStep(raw as any, String(matchingLocal?.currentStep || '')),
      currentPhase: String(raw.current_phase || raw.phase || matchingLocal?.currentPhase || ''),
      phaseProgress: Number(raw.phase_progress || matchingLocal?.phaseProgress || 0),
      phaseDetail: raw.phase_detail || matchingLocal?.phaseDetail || {},
      error: raw.error ? String(raw.error) : matchingLocal?.error,
      errorCode: raw.error_code ? String(raw.error_code) : matchingLocal?.errorCode,
      errorUserMessage: raw.error_user_message ? String(raw.error_user_message) : matchingLocal?.errorUserMessage,
      recovery: raw.recovery || matchingLocal?.recovery,
      publicationAllowed: typeof raw.publication_allowed === 'boolean' ? raw.publication_allowed : matchingLocal?.publicationAllowed,
      qualityStatus: raw.quality_status || matchingLocal?.qualityStatus,
      guidedWorkflow: raw.guided_workflow || matchingLocal?.guidedWorkflow,
      logs: matchingLocal?.logs || [],
      shouldStop: false,
      updatedAt: raw.updated_at || raw.created_at,
      heartbeatAt: raw.heartbeat_at || raw.updated_at || raw.created_at,
      phaseHistory: raw.phase_history || matchingLocal?.phaseHistory || [],
    })
  }
  for (const local of generationStore.tasks.values()) {
    if (!byTaskId.has(local.id)) byTaskId.set(local.id, { ...local })
  }
  const scopedTasks = props.courseId
    ? [...byTaskId.values()].filter(task => task.courseId === props.courseId)
    : [...byTaskId.values()]
  return scopedTasks.sort((a, b) => {
    const priority = (task: TaskView) => taskNeedsAttention(task) ? 0 : 1
    return priority(a) - priority(b) || String(b.updatedAt || '').localeCompare(String(a.updatedAt || ''))
  })
})
const selectedTask = computed(() => tasks.value.find(task => task.id === selectedTaskId.value) || null)
const selectedDisplayProgress = computed(() => selectedTask.value ? taskDisplayProgress(selectedTask.value) : 0)
const selectedObservableStages = computed(() => selectedTask.value ? observableTaskStages(selectedTask.value) : [])
const selectedHeartbeat = computed(() => selectedTask.value
  ? taskHeartbeatState(selectedTask.value)
  : { state: 'unknown' as const, ageSeconds: null })
const selectedError = computed(() => selectedTask.value
  ? taskUserError(selectedTask.value)
  : { message: '', technicalDetail: '' })
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
// 教师逐条剔除的联网来源。后端目前没有"看到结果后剔除"的写入端点，
// 因此这里只保留前端态，随下次生成请求的 web_material_ingest.excluded_source_ids
// 一起下发。按 courseId 分组，避免不同课程之间串味。
const excludedWebSources = ref<Record<string, string[]>>({})
const excludedWebSourceIds = computed(() => {
  const courseId = String(selectedTask.value?.courseId || '')
  return courseId ? (excludedWebSources.value[courseId] || []) : []
})

function toggleWebSourceExclusion(source: { sourceId: string; url: string }) {
  const courseId = String(selectedTask.value?.courseId || '')
  if (!courseId) return
  const key = source.sourceId || source.url
  if (!key) return
  const current = excludedWebSources.value[courseId] || []
  excludedWebSources.value = {
    ...excludedWebSources.value,
    [courseId]: current.includes(key)
      ? current.filter(item => item !== key)
      : [...current, key],
  }
}

defineExpose({ excludedWebSourceIds })

const webSearchSummary = computed(() => {
  const detail = selectedTask.value?.phaseDetail || {}
  const raw = (detail as Record<string, any>).web_search
  if (!raw || typeof raw !== 'object') return null
  if (!raw.enabled) return null
  const sources = Array.isArray(raw.sources) ? raw.sources : []
  const rejected = Array.isArray(raw.rejected) ? raw.rejected : []
  const status = String(raw.status || '')
  return {
    status,
    statusLabel: t(`courseGeneration.materials.webSearch.status.${status}`, status),
    // degraded 时明确告诉教师本次没有联网资料，而不是静默留白。
    degraded: Boolean(raw.degraded),
    messageCode: String(raw.message_code || ''),
    message: raw.message_code
      ? t(`courseGeneration.materials.webSearch.messageCode.${raw.message_code}`, '')
      : '',
    queries: (Array.isArray(raw.queries) ? raw.queries : []).map((item: unknown) => String(item)),
    sources: sources.map((item: Record<string, any>) => {
      const sourceId = String(item.source_id || '')
      const url = String(item.url || '')
      return {
        sourceId,
        url,
        title: String(item.title || item.domain || url),
        domain: String(item.domain || ''),
        credibility: String(item.credibility || 'low'),
        retrievedAt: String(item.retrieved_at || ''),
        excluded: excludedWebSourceIds.value.includes(sourceId || url),
      }
    }),
    rejected: rejected.map((item: Record<string, any>) => ({
      url: String(item.url || ''),
      reason: String(item.reason || ''),
      reasonLabel: t(`courseGeneration.materials.webSearch.reason.${item.reason}`, String(item.reason || '')),
    })),
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
  if (selectedTask.value?.taskType === 'course_import') return []
  const workflow = selectedTask.value?.guidedWorkflow || generationReview.value?.guided_workflow
  const current = workflow?.current_step
  const sourceSteps = workflow?.steps || []
  const visibleKeys: Exclude<GuidedGenerationStepKey, 'requirements'>[] = ['outline', 'teaching', 'content', 'release']
  const currentIndex = visibleKeys.indexOf(current as Exclude<GuidedGenerationStepKey, 'requirements'>)
  return visibleKeys.map((key, index) => {
    const source = sourceSteps.find((step: any) => step.key === key)
    const status = source?.status || (
      currentIndex > index ? 'confirmed'
        : currentIndex === index ? 'pending'
          : 'locked'
    )
    return {
      ...source,
      key,
      number: index + 1,
      status,
      label: guidedStepLabel(key),
      displayStatus: (
        status === 'pending'
        && current === key
        && selectedTask.value?.status === 'running'
      ) ? 'in_progress' : status,
    }
  })
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
const releaseIssues = computed<any[]>(() => reviewBlockingIssues(reviewArtifact.value))
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
  if (!props.embedded) previousFocus.value = document.activeElement instanceof HTMLElement ? document.activeElement : null
  await refresh()
  if (!tasks.value.some(task => task.id === selectedTaskId.value)) {
    selectedTaskId.value = preferredTaskId(props.courseId)
  }
  await loadSelectedReview()
  await nextTick()
  if (!props.embedded) panelRef.value?.focus()
}, { immediate: true })
watch(() => props.courseId, value => {
  if (value) selectedTaskId.value = preferredTaskId(value)
})
watch(selectedTaskId, () => { void loadSelectedReview() })
watch(
  () => [
    selectedTask.value?.status,
    selectedTask.value?.recovery?.state,
    selectedTask.value?.guidedWorkflow?.review_step,
  ],
  () => {
    if (selectedTask.value && shouldShowGenerationReview(selectedTask.value)) void loadSelectedReview()
  },
)
onMounted(() => generationStore.startGlobalMonitor())

function normalizeStatus(status: string): Task['status'] {
  if (status === 'failed') return 'error'
  if (['idle', 'running', 'paused', 'completed', 'error', 'pending', 'waiting_for_review', 'completed_with_warnings', 'conflict'].includes(status)) return status as Task['status']
  return 'pending'
}
function close() {
  emit('update:modelValue', false)
  if (!props.embedded) nextTick(() => previousFocus.value?.focus())
}
function handleDialogKeydown(event: KeyboardEvent) {
  if (props.embedded) return
  if (event.key === 'Escape') {
    event.preventDefault()
    close()
    return
  }
  if (event.key !== 'Tab' || !panelRef.value) return
  const focusable = [...panelRef.value.querySelectorAll<HTMLElement>(
    'button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [href], [tabindex]:not([tabindex="-1"])',
  )].filter(element => !element.hasAttribute('hidden'))
  if (!focusable.length) {
    event.preventDefault()
    panelRef.value.focus()
    return
  }
  const first = focusable[0]!
  const last = focusable[focusable.length - 1]!
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}
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
  if (!selectedTask.value || !shouldShowGenerationReview(selectedTask.value)) return
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
    requirements: t('courseTasks.workflow.requirements', '需求输入'),
    outline: t('courseTasks.workflow.outline', '目录确认'),
    teaching: t('courseTasks.workflow.teaching', '教案确认'),
    content: t('courseTasks.workflow.content', '正文生成'),
    release: t('courseTasks.workflow.release', '确认发布'),
  }[step]
}
function observableStageStatusLabel(status: ObservableTaskStageStatus) {
  return {
    completed: t('taskObservability.status.completed', '已完成'),
    active: t('taskObservability.status.active', '进行中'),
    pending: t('taskObservability.status.pending', '未开始'),
    error: t('taskObservability.status.error', '已中断'),
    paused: t('taskObservability.status.paused', '已暂停'),
    blocked: t('taskObservability.status.blocked', '需处理'),
  }[status]
}
function taskKindLabel(task: TaskView) {
  return task.taskType === 'course_import'
    ? t('taskObservability.kind.import', '课程导入')
    : t('taskObservability.kind.generation', '课程生成')
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
function shouldShowGenerationReview(task: TaskView) {
  return task.status === 'waiting_for_review' || task.recovery?.state === 'quality_blocked'
}
function taskStepLabel(task: TaskView) {
  const detail = courseProductionTaskDetail(task).trim()
  const generic = /^(?:正在)?(?:处理|生成|准备)(?:中)?[.。…]*$/
  return (detail && !generic.test(detail)) ? detail : taskPhaseLabel(task)
}
function taskPhaseLabel(task: TaskView) {
  return phaseLabel(observableTaskPhase(task), task.status, task.taskType)
}
function phaseLabel(phase: string | undefined, status: Task['status'], taskType?: string) {
  if (phase === 'completed' && taskType === 'course_import') {
    return t('taskObservability.import.completed', '导入完成')
  }
  const labels: Record<string, string> = {
    material_receiving: t('taskObservability.receive', '资料接收'),
    material_parsing: t('taskObservability.parse', '解析与分类'),
    source_retrieval: t('taskObservability.retrieve', '检索证据'),
    quality_validation: t('taskObservability.validate', '质量检查'),
    exporting: t('taskObservability.export', '导出与发布'),
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
    quality_repair: t('courseTasks.phases.qualityRepair', '定向修复质量阻断'),
    question_bank: t('courseTasks.phases.questionBank', '整理题库、联网补充与风险审核'),
    content_validation: t('courseTasks.phases.contentValidation', '检查结构、引用、答案合同与覆盖'),
    question_analysis: t('courseTasks.phases.questionAnalysis', '编译题目考查与答案合同'),
    content_ready: t('courseTasks.phases.contentReady', '等待确认课程内容'),
    content_confirmed: t('courseTasks.phases.contentConfirmed', '课程内容已确认'),
    publication_quality_check: t('courseTasks.phases.publicationQualityCheck', '正在执行发布前质量检查'),
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
function statusLabel(status: Task['status'], recovery?: Task['recovery'], taskType?: string) {
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
  const label = labels[status]
  if (taskType !== 'course_import') return label
  const importLabels: Partial<Record<Task['status'], string>> = {
    pending: t('taskObservability.import.pending', '等待导入'),
    running: t('taskObservability.import.running', '正在导入'),
    paused: t('taskObservability.import.paused', '导入已暂停'),
    error: t('taskObservability.import.error', '导入失败'),
    completed: t('taskObservability.import.completed', '导入完成'),
  }
  return importLabels[status] || label
}
function problemTitle(task: TaskView) {
  if (task.taskType === 'course_import' && task.status === 'error') {
    return task.recovery?.can_resume
      ? t('taskObservability.import.retryableTitle', '导入中断，可以从保存点继续')
      : t('taskObservability.import.replaceTitle', '导入文件需要修正')
  }
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
  if (task.taskType === 'course_import') {
    return task.recovery?.can_resume
      ? t('taskObservability.import.retryableHelp', '已解析的结构和源文件均已保留，继续不会创建重复课程。')
      : t('taskObservability.import.replaceHelp', '请根据错误提示修正或替换源文件，然后重新发起导入。')
  }
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
  if (task.taskType === 'course_import') {
    return task.recovery?.checkpoint.parsed_ready
      ? t('taskObservability.import.resumeParsed', '从解析结果继续')
      : t('courseTasks.retryStage', '重试当前阶段')
  }
  if (task.recovery?.state === 'quality_blocked') {
    return t('courseTasks.repairAndRecheck', '修复阻断项并复检')
  }
  return restartsCurrentStage(task)
    ? t('courseTasks.retryStage', '重试当前阶段')
    : t('courseTasks.resumeCheckpoint', '从保存点继续')
}
function recoveryCheckpointLabel(task: TaskView) {
  const checkpoint = task.recovery?.checkpoint
  if (!checkpoint) return ''
  if (task.taskType === 'course_import') {
    return checkpoint.parsed_ready
      ? t('taskObservability.import.parsedCheckpoint', '源文件和解析结果已保存，只重试未完成的保存与导出步骤')
      : t('taskObservability.import.sourceCheckpoint', '源文件已保存，可以重试当前导入阶段')
  }
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
.task-center-layer--embedded { position:relative; inset:auto; z-index:auto; width:100%; height:100%; display:block; padding:0; }
.task-center-backdrop { position: absolute; inset: 0; width: 100%; height: 100%; border: 0; background: rgba(30,41,59,.34); backdrop-filter: blur(5px); cursor: default; }
.task-center { position: relative; width: min(980px,100%); height: min(720px,calc(100vh - 40px)); display: grid; grid-template-rows: 62px minmax(0,1fr); overflow: hidden; border: 1px solid rgba(255,255,255,.92); border-radius: var(--lz-radius-surface); color: var(--lz-text); background: rgba(255,255,255,.98); box-shadow: var(--lz-shadow-overlay); outline: none; }
.task-center--embedded { width:100%; height:100%; grid-template-rows:minmax(0,1fr); border:0; border-radius:0; box-shadow:none; }
.task-center__header { display:flex; align-items:center; justify-content:space-between; gap:16px; padding:0 14px 0 20px; border-bottom:1px solid var(--lz-border); }
.task-center__header > div:first-child { min-width:0; display:flex; align-items:center; gap:10px; }
.task-center__header > div:first-child > span { width:34px; height:34px; display:grid; place-items:center; border-radius:9px; color:var(--lz-brand-strong); background:var(--lz-brand-soft); }
.task-center__header p { margin:0 0 1px; color:var(--lz-text-muted); font-size:10px; font-weight:700; }
.task-center__header h2 { margin:0; color:var(--lz-text-strong); font-size:16px; }
.task-center__header-actions { display:flex; gap:4px; }
.icon-button { width:34px; height:34px; display:grid; place-items:center; border:0; border-radius:7px; color:var(--lz-text-secondary); background:transparent; cursor:pointer; }
.icon-button:hover { color:var(--lz-text-strong); background:var(--lz-surface-muted); }
.task-center__body { min-height:0; display:grid; grid-template-columns:260px minmax(0,1fr); }
.task-center__body--empty { display:block; }
.task-list { min-height:0; overflow:auto; padding:7px; border-right:1px solid var(--lz-border); background:rgba(248,250,252,.76); }
.task-center-empty { min-height:208px; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:8px; padding:28px; color:var(--lz-text-muted); text-align:center; }
.task-center-empty__icon { width:38px; height:38px; display:grid; place-items:center; border-radius:10px; color:var(--lz-brand-strong); background:var(--lz-brand-soft); }
.task-center-empty strong { color:var(--lz-text-strong); font-size:14px; }
.task-center-empty p { max-width:360px; margin:0; font-size:11px; line-height:1.6; }
.task-detail--empty { height:100%; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:8px; color:var(--lz-text-muted); text-align:center; }
.task-row { width:100%; min-height:56px; display:grid; grid-template-columns:28px minmax(0,1fr) auto; align-items:center; gap:7px; padding:7px 8px; border:1px solid transparent; border-radius:8px; color:var(--lz-text); background:transparent; text-align:left; cursor:pointer; }
.task-row:hover { background:#fff; }.task-row.active { border-color:rgba(99,102,241,.24); background:var(--lz-brand-soft); }
.task-row__state { width:26px; height:26px; display:grid; place-items:center; border-radius:7px; color:var(--lz-text-muted); background:#fff; }
.task-row__state[data-status="running"],.task-row__state[data-status="waiting_for_review"] { color:var(--lz-brand-strong); }
.task-row__state[data-status="completed"] { color:var(--lz-success); }.task-row__state[data-status="error"],.task-row__state[data-status="conflict"],.task-row__state[data-status="completed_with_warnings"] { color:var(--lz-warning); }
.task-row__copy { min-width:0; display:block; }.task-row__copy strong,.task-row__copy small { overflow:hidden; display:block; text-overflow:ellipsis; white-space:nowrap; }.task-row__copy strong { color:var(--lz-text-strong); font-size:12px; }.task-row__copy small { margin-top:4px; color:var(--lz-text-muted); font-size:10px; }
.task-detail { min-height:0; display:grid; grid-template-rows:minmax(0,1fr) auto; overflow:hidden; }
.task-detail__scroll { min-height:0; overflow:auto; padding:20px clamp(20px,3vw,34px) 16px; }
.task-summary { padding-bottom:18px; border-bottom:1px solid var(--lz-border); }
.task-summary__top { display:flex; align-items:flex-start; justify-content:space-between; gap:20px; }.task-summary__top > div { min-width:0; }.task-summary__top > strong { color:var(--lz-brand-strong); font-size:24px; line-height:1; }
.task-summary__chips { display:flex; align-items:center; gap:7px; }
.task-kind-chip { display:inline-flex; min-height:24px; align-items:center; padding:0 8px; border:1px solid var(--lz-border); border-radius:999px; color:var(--lz-text-secondary); background:var(--lz-surface-muted); font-size:10px; font-weight:700; }
.status-chip { display:inline-flex; min-height:24px; align-items:center; padding:0 8px; border-radius:5px; color:var(--lz-brand-strong); background:var(--lz-brand-soft); font-size:10px; font-weight:700; }.status-chip[data-status="completed"] { color:var(--lz-success); background:var(--lz-success-soft); }.status-chip[data-status="error"],.status-chip[data-status="conflict"],.status-chip[data-status="completed_with_warnings"] { color:var(--lz-warning); background:var(--lz-warning-soft); }
.task-summary h3 { margin:8px 0 4px; color:var(--lz-text-strong); font-size:19px; }.task-summary p { margin:0; color:var(--lz-text-secondary); font-size:11px; line-height:1.5; }
.task-progress { height:5px; margin:15px 0 13px; overflow:hidden; border-radius:3px; background:var(--lz-surface-muted); }.task-progress span { display:block; width:100%; height:100%; border-radius:inherit; background:var(--lz-brand); transform-origin:left center; transition:transform .2s ease; }
.task-summary dl { margin:0; display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:14px; }.task-summary dl div { min-width:0; }.task-summary dt { color:var(--lz-text-muted); font-size:10px; }.task-summary dd { margin:4px 0 0; overflow:hidden; color:var(--lz-text); font-size:12px; font-weight:650; text-overflow:ellipsis; white-space:nowrap; }
.task-detail-group { padding:14px 0; border-bottom:1px solid var(--lz-border); }
.task-detail-group>summary { color:var(--lz-text-secondary); font-size:11px; font-weight:700; cursor:pointer; }
.task-detail-group[open]>summary { margin-bottom:14px; color:var(--lz-brand-strong); }
.task-detail-group .task-observability,.task-detail-group .guided-workflow { padding:0; border-bottom:0; }
.task-observability { padding:17px 0; border-bottom:1px solid var(--lz-border); }
.web-search-summary { padding:18px 0; border-bottom:1px solid var(--lz-border); display:grid; gap:9px; }
.web-search-summary__head { display:flex; align-items:center; gap:10px; }
.web-search-summary__head strong { font-size:13px; color:var(--lz-text-strong); }
.web-search-summary__status { font-size:11px; padding:2px 8px; border-radius:999px; color:var(--lz-brand-strong); background:var(--lz-brand-soft); }
.web-search-summary__status[data-degraded="true"] { color:#92400e; background:#fef3c7; }
.web-search-summary__degraded { margin:0; font-size:12px; color:#92400e; }
.web-search-summary__hint,.web-search-summary__empty { margin:0; font-size:11px; color:var(--lz-text-muted); }
.web-search-summary__queries { display:grid; gap:5px; }
.web-search-summary__queries dt { font-size:11px; color:var(--lz-text-muted); }
.web-search-summary__queries dd { margin:0; display:flex; flex-wrap:wrap; gap:6px; }
.web-search-summary__queries dd span { font-size:11px; padding:2px 8px; border-radius:6px; color:var(--lz-text); background:var(--lz-surface-muted,#f1f5f9); }
.web-search-summary__sources { margin:0; padding:0; list-style:none; display:grid; gap:8px; }
.web-search-summary__sources li { display:grid; gap:2px; min-width:0; }
.web-search-summary__sources li[data-excluded="true"] { opacity:.55; }
.web-search-summary__sources li[data-excluded="true"] a { text-decoration:line-through; }
.web-search-summary__source-line { display:flex; align-items:baseline; gap:8px; min-width:0; }
.web-search-summary__source-line a { min-width:0; flex:1 1 auto; }
.web-search-summary__exclude { flex:0 0 auto; padding:1px 8px; border:1px solid var(--lz-border); border-radius:999px; background:transparent; color:var(--lz-text-muted); font-size:11px; line-height:1.7; cursor:pointer; }
.web-search-summary__exclude:hover { color:var(--lz-text-strong); border-color:var(--lz-text-muted); }
.web-search-summary__exclude[aria-pressed="true"] { color:var(--lz-brand-strong); border-color:var(--lz-brand-strong); }
.web-search-summary__pending { margin:0; font-size:11px; color:#92400e; }
.web-search-summary__sources a { font-size:12px; color:var(--lz-brand-strong); overflow-wrap:anywhere; }
.web-search-summary__sources small,.web-search-summary__rejected small { font-size:11px; color:var(--lz-text-muted); }
.web-search-summary__rejected summary { font-size:11px; color:var(--lz-text-muted); cursor:pointer; }
.web-search-summary__rejected ul { margin:8px 0 0; padding:0; list-style:none; display:grid; gap:6px; }
.web-search-summary__rejected li { display:grid; gap:2px; font-size:11px; overflow-wrap:anywhere; word-break:break-all; min-width:0; }
.web-search-summary__rejected li span { min-width:0; overflow-wrap:anywhere; word-break:break-all; }
.task-observability ol { display:grid; grid-template-columns:repeat(6,minmax(0,1fr)); margin:0; padding:0; list-style:none; }
.task-observability__stage { position:relative; min-width:0; display:grid; justify-items:center; gap:5px; padding:0 3px; color:var(--lz-text-muted); text-align:center; }
.task-observability__stage:not(:last-child)::after { content:""; position:absolute; z-index:0; top:12px; left:calc(50% + 15px); right:calc(-50% + 15px); height:1px; background:var(--lz-border); }
.task-observability__marker { position:relative; z-index:1; width:25px; height:25px; display:grid; place-items:center; border:1px solid var(--lz-border); border-radius:50%; color:var(--lz-text-muted); background:#fff; }
.task-observability__stage strong { max-width:100%; overflow:hidden; color:var(--lz-text-secondary); font-size:10px; text-overflow:ellipsis; white-space:nowrap; }
.task-observability__stage small { color:var(--lz-text-muted); font-size:9px; }
.task-observability__stage[data-status="completed"] .task-observability__marker { border-color:rgba(5,150,105,.35); color:var(--lz-success); background:var(--lz-success-soft); }
.task-observability__stage[data-status="completed"]:not(:last-child)::after { background:rgba(5,150,105,.35); }
.task-observability__stage[data-status="active"] .task-observability__marker { border-color:rgba(79,70,229,.35); color:var(--lz-brand-strong); background:var(--lz-brand-soft); }
.task-observability__stage[data-status="active"] strong { color:var(--lz-text-strong); }
.task-observability__stage[data-status="error"] .task-observability__marker,.task-observability__stage[data-status="blocked"] .task-observability__marker { border-color:rgba(217,119,6,.35); color:var(--lz-warning); background:var(--lz-warning-soft); }
.task-observability__stage[data-status="paused"] .task-observability__marker { color:var(--lz-text-secondary); background:var(--lz-surface-muted); }
.task-heartbeat-alert { display:flex; align-items:flex-start; gap:7px; margin:16px 0 0; padding:10px 12px; border-radius:8px; color:#9a4d13; background:#fff8ed; font-size:11px; line-height:1.5; }
.task-heartbeat-alert svg { flex:0 0 auto; margin-top:1px; }
.guided-workflow { padding:17px 0; border-bottom:1px solid var(--lz-border); }
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
.module-sequence { display:flex; flex-wrap:wrap; gap:6px; margin-top:10px; }.module-sequence__item { position:relative; min-width:130px; max-width:220px; display:grid; gap:2px; padding:7px 8px; border:1px solid var(--lz-border); border-radius:7px; color:var(--lz-text-secondary); background:var(--lz-surface-muted); }.module-sequence__item[data-added="true"] { border-color:rgba(99,102,241,.28); background:var(--lz-brand-soft); }.module-sequence__item[data-source="difficulty_level"] { border-color:rgba(217,119,6,.28); background:var(--lz-warning-soft); }.module-sequence__item b { overflow:hidden; color:var(--lz-text-strong); font-size:9px; text-overflow:ellipsis; white-space:nowrap; }.module-sequence__item em { color:var(--lz-text-muted); font-size:8px; font-style:normal; line-height:1.35; }.module-sequence__item i { color:var(--lz-brand-strong); font-size:8px; font-style:normal; font-weight:700; }.module-sequence__item[data-source="difficulty_level"] i { color:var(--lz-warning); }
.review-callout,.release-verdict { display:flex; gap:11px; align-items:flex-start; padding:14px; border:1px solid rgba(99,102,241,.18); border-radius:10px; color:var(--lz-brand-strong); background:var(--lz-brand-soft); }.review-callout strong,.release-verdict strong { display:block; color:var(--lz-text-strong); font-size:12px; }.review-callout p,.release-verdict p { margin:4px 0 0; color:var(--lz-text-secondary); font-size:10px; line-height:1.5; }
.content-evidence { margin:10px 0; display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:8px; }.content-evidence > div { padding:10px; border:1px solid var(--lz-border); border-radius:8px; background:var(--lz-surface-muted); }.content-evidence span,.content-evidence strong { display:block; }.content-evidence span { color:var(--lz-text-muted); font-size:9px; }.content-evidence strong { margin-top:4px; color:var(--lz-text-strong); font-size:13px; }.asset-counts { display:flex; flex-wrap:wrap; gap:5px; margin-bottom:10px; }.asset-counts span { padding:4px 7px; border:1px solid rgba(99,102,241,.14); border-radius:999px; color:var(--lz-brand-strong); background:var(--lz-brand-soft); font-size:8px; font-weight:650; }
.question-review { margin:14px 0; padding:14px; border:1px solid rgba(14,116,144,.16); border-radius:10px; background:rgba(236,254,255,.42); }.question-review>header { display:flex; justify-content:space-between; align-items:flex-start; gap:14px; }.question-review>header strong { color:var(--lz-text-strong); font-size:12px; }.question-review>header p { margin:4px 0 0; max-width:460px; color:var(--lz-text-secondary); font-size:9px; line-height:1.5; }.question-review>header>span { flex:0 0 auto; padding:5px 8px; border-radius:999px; color:#047857; background:#ecfdf5; font-size:9px; font-weight:800; }.question-review>header>span[data-blocked="true"] { color:var(--lz-warning); background:var(--lz-warning-soft); }.question-review__list { margin-top:12px; display:grid; gap:8px; }.question-review__list>article { display:grid; grid-template-columns:28px minmax(0,1fr); gap:9px; padding:10px; border:1px solid rgba(14,116,144,.12); border-radius:8px; background:#fff; }.question-review__list>article[data-status="blocked"] { border-color:rgba(217,119,6,.28); }.question-review__index { color:#0e7490; font-family:ui-monospace,monospace; font-size:9px; font-weight:800; }.question-review__meta { display:flex; justify-content:space-between; gap:8px; margin-bottom:5px; color:var(--lz-text-muted); font-size:8px; }.question-review__meta b { color:#0e7490; }.question-review__list article>div>strong { display:block; color:var(--lz-text-strong); font-size:10px; line-height:1.5; }.question-review dl { display:grid; grid-template-columns:1fr 1fr; gap:10px; margin:9px 0; }.question-review dt { color:var(--lz-text-muted); font-size:8px; }.question-review dd { margin:3px 0 0; color:var(--lz-text-secondary); font-size:9px; line-height:1.45; }.question-review__targets { display:flex; flex-wrap:wrap; gap:4px; }.question-review__targets span { padding:3px 6px; border-radius:999px; color:#0e7490; background:#ecfeff; font-size:8px; }.question-review__targets span[data-kind="mistake"] { color:#c2410c; background:#fff7ed; }.question-review ul { margin:8px 0 0; padding-left:16px; color:var(--lz-warning); font-size:9px; line-height:1.5; }
.release-verdict[data-pass="false"] { border-color:rgba(217,119,6,.2); color:var(--lz-warning); background:var(--lz-warning-soft); }.release-issues { margin:12px 0 0; padding:0 0 0 18px; color:var(--lz-warning); font-size:10px; line-height:1.6; }
.quality-blockers { margin-top:12px; padding:13px; border:1px solid rgba(217,119,6,.22); border-radius:10px; background:#fffbeb; }.quality-blockers>header { display:flex; align-items:center; justify-content:space-between; gap:12px; }.quality-blockers h5 { margin:0; color:#92400e; font-size:12px; }.quality-blockers>header span { color:#b45309; font-size:9px; font-weight:700; }.quality-blocker-list { margin:10px 0 0; padding:0; display:grid; gap:8px; list-style:none; }.quality-blocker-list>li { padding:10px; border:1px solid rgba(217,119,6,.24); border-radius:8px; color:var(--lz-text-secondary); background:#fff; }.quality-blocker-list__meta { display:flex; flex-wrap:wrap; justify-content:space-between; gap:6px; margin-bottom:5px; }.quality-blocker-list__meta code { color:#92400e; font-family:ui-monospace,monospace; font-size:8px; }.quality-blocker-list__meta span { color:var(--lz-text-muted); font-size:8px; }.quality-blocker-list strong { display:block; color:var(--lz-text-strong); font-size:10px; line-height:1.5; }.quality-blocker-list p { margin:4px 0 0; color:#9a4d13; font-size:9px; line-height:1.5; }
.task-notice { margin-top:16px; display:flex; gap:10px; padding:12px 13px; border:1px solid rgba(217,119,6,.22); border-radius:9px; color:var(--lz-warning); background:var(--lz-warning-soft); }.task-notice strong { display:block; font-size:12px; }.task-notice p { margin:4px 0 0; font-size:11px; line-height:1.5; }.recovery-checkpoint { display:block; margin-top:7px; color:inherit; font-size:9px; line-height:1.5; opacity:.88; }.task-error-detail { margin-top:7px; color:inherit; font-size:9px; opacity:.9; }.task-error-detail summary { width:max-content; cursor:pointer; font-weight:700; }.task-error-detail code { display:block; margin-top:6px; color:#92400e; font:9px/1.5 ui-monospace,SFMono-Regular,Consolas,monospace; overflow-wrap:anywhere; }
.task-actions { display:flex; flex-wrap:wrap; align-items:center; gap:8px; padding:13px clamp(20px,4vw,38px); border-top:1px solid var(--lz-border); background:rgba(255,255,255,.98); box-shadow:0 -8px 22px rgba(15,23,42,.035); }.task-actions__open { margin-left:auto; }
.primary-button,.secondary-button,.danger-button { min-height:38px; display:inline-flex; align-items:center; justify-content:center; gap:7px; padding:0 13px; border-radius:8px; font-size:12px; font-weight:700; cursor:pointer; }.primary-button { border:1px solid var(--lz-brand-strong); color:#fff; background:var(--lz-brand-strong); }.secondary-button { border:1px solid var(--lz-border); color:var(--lz-text-secondary); background:#fff; }.danger-button { border:1px solid rgba(185,28,28,.22); color:var(--lz-danger); background:var(--lz-danger-soft); }.primary-button:disabled,.secondary-button:disabled,.danger-button:disabled,.icon-button:disabled { cursor:not-allowed; opacity:.5; }
.spin { animation:spin 1s linear infinite; }@keyframes spin { to { transform:rotate(360deg); } }
@media (max-width:720px) { .task-center-layer { align-items:end; padding:0; }.task-center { width:100%; height:calc(100dvh - 56px); border-radius:14px 14px 0 0; }.task-center--embedded { height:100%; border-radius:0; }.task-center--empty { height:auto; min-height:280px; }.task-center__body { grid-template-columns:1fr; grid-template-rows:76px minmax(0,1fr); }.task-center__body--empty { display:block; }.task-list { display:flex; gap:6px; max-height:none; overflow-x:auto; overflow-y:hidden; padding:7px 10px; border-right:0; border-bottom:1px solid var(--lz-border); scroll-snap-type:x proximity; }.task-row { width:auto; flex:0 0 min(270px,calc(100vw - 52px)); min-height:60px; scroll-snap-align:start; }.task-center-empty { min-height:218px; padding:26px 24px calc(30px + env(safe-area-inset-bottom)); }.task-detail__scroll { padding:16px 14px 12px; }.task-summary { padding-bottom:18px; }.task-summary__top { gap:12px; }.task-summary__top > strong { font-size:22px; }.task-summary h3 { margin:8px 0 4px; font-size:18px; }.task-progress { margin:14px 0 13px; }.task-summary dl { grid-template-columns:1fr 1fr; gap:9px; }.task-actions { padding:10px 14px calc(10px + env(safe-area-inset-bottom)); }.task-actions__open { margin-left:0; }.task-observability { padding:18px 0; }.task-observability ol,.guided-workflow ol { grid-template-columns:repeat(3,minmax(0,1fr)); row-gap:16px; }.task-observability__stage:nth-child(3n)::after,.guided-workflow li:nth-child(3n)::after { display:none; }.review-metrics { grid-template-columns:1fr 1fr 1fr; } }
@media (prefers-reduced-motion: reduce) { .task-center { animation:none; }.spin { animation:none; } }
</style>
