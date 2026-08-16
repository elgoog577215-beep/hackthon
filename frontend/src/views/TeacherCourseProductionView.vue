<template>
  <section class="teacher-production" :class="{ 'has-lessons': showLessonRail }">
    <header class="product-bar">
      <button type="button" class="brand" @click="router.push({ name: 'teacher-course-library' })">
        <img src="/qizhi-favicon.svg" alt="" />
        <strong>启智</strong>
      </button>
      <nav aria-label="当前位置">
        <button type="button" @click="router.push({ name: 'teacher-course-library' })">课程工作台</button>
        <ChevronRight :size="14" />
        <button type="button" @click="router.push({ name: 'teacher-course-overview', params: { courseId } })">{{ courseTitle }}</button>
        <ChevronRight :size="14" />
        <strong>{{ pageTitle }}</strong>
      </nav>
      <div class="product-actions">
        <button type="button" @click="openStudentPreview"><Eye :size="16" />预览学生版</button>
        <button type="button" aria-label="刷新课程状态" title="刷新课程状态" @click="refresh"><RefreshCw :size="17" :class="{ spin: loading }" /></button>
      </div>
    </header>

    <div class="production-shell">
      <TeacherCourseSidebar
        :course-id="courseId"
        :title="courseTitle"
        :meta="courseMeta"
        :active="pageMode"
        :attention-count="attentionCount"
      />

      <main class="production-main">
        <div class="course-status" role="status" aria-label="课程生产状态">
          <strong>{{ courseTitle }}</strong>
          <span>{{ currentContextLabel }}</span>
          <span>{{ taskStatusLabel }}</span>
          <span v-if="task && !teacherAuthoringReady">进度 {{ projectedTaskProgress }}%</span>
          <span v-if="reviewStep">待确认：{{ stageLabel(reviewStep) }}</span>
          <span v-if="failedLessonCount">异常讲次 {{ failedLessonCount }}</span>
          <span class="status-spacer"></span>
          <button v-if="canResume" type="button" class="status-action" :disabled="actionBusy" @click="resumeTask"><Play :size="14" />继续生成</button>
          <button v-else-if="canPause" type="button" class="status-action" :disabled="actionBusy" @click="pauseTask"><Pause :size="14" />暂停</button>
          <span v-else class="next-action">{{ nextActionLabel }}</span>
        </div>

        <div v-if="pageMode === 'production'" class="production-tabs" aria-label="课程生产分类">
          <div class="segmented-tabs" role="tablist">
            <button
              v-for="item in stages"
              :key="item.key"
              type="button"
              role="tab"
              :data-testid="`production-stage-${item.key}`"
              :class="{ active: activeStage === item.key }"
              :aria-selected="activeStage === item.key"
              @click="selectStage(item.key)"
            >
              {{ item.label }}
              <span :data-state="stageStatus(item.key)">{{ stageStatusLabel(item.key) }}</span>
            </button>
          </div>
          <span class="production-tabs__summary">已开放 {{ availableStageCount }}/{{ stages.length }}</span>
          <div class="production-tabs__actions">
            <button
              v-if="activeStage === 'teaching'"
              type="button"
              class="ai-toggle"
              :aria-expanded="aiDockOpen"
              @click="aiDockOpen = !aiDockOpen"
            ><Sparkles :size="14" />{{ aiDockOpen ? '收起 AI 助手' : 'AI 助手' }}</button>
            <button
              v-if="activeStage === 'teaching'"
              type="button"
              class="next-step-button"
              :disabled="!pptAvailable"
              :title="pptAvailable ? '进入独立 PPT 阶段' : pptBlockedReason"
              @click="selectStage('ppt')"
            ><Presentation :size="14" />{{ pptAvailable ? '下一步：制作 PPT' : 'PPT 等待教案确认' }}</button>
            <button v-if="showLessonRail" type="button" class="exit-immersive" @click="selectStage('overview')">返回课次总览</button>
          </div>
        </div>

        <div class="workspace-grid" :class="{ 'single-page': pageMode !== 'production', immersive: showLessonRail, 'with-ai-dock': showAiDock }">
          <aside v-if="showLessonRail" class="lesson-rail" aria-label="课程讲次">
            <header><strong>课程讲次</strong><small>{{ lessons.length }}</small></header>
            <div class="lesson-list">
              <button
                v-for="(lesson, index) in lessons"
                :key="lesson.node_id"
                type="button"
                :class="{ active: selectedNodeId === lesson.node_id }"
                @click="selectLesson(lesson)"
              >
                <span>{{ String(index + 1).padStart(2, '0') }}</span>
                <span><strong>{{ lesson.node_name }}</strong><small>{{ lessonState(lesson) }}</small></span>
              </button>
            </div>
          </aside>

          <section class="stage-workspace" :class="{ 'outline-mode': pageMode === 'outline' }" :aria-label="activeStageLabel">
            <div v-if="loading" class="workspace-state"><LoaderCircle class="spin" :size="24" /><span>正在读取课程生产状态</span></div>
            <div v-else-if="loadError" class="workspace-state is-error"><TriangleAlert :size="24" /><strong>课程状态读取失败</strong><span>{{ loadError }}</span><button type="button" @click="refresh">重试</button></div>

            <CourseOutlineReview
              v-else-if="pageMode === 'outline'"
              :course-id="courseId"
              :course-name="courseTitle"
              :nodes="courseStore.nodes"
              :task="task"
              @confirmed="handleGateConfirmed('outline')"
            />

            <template v-else-if="pageMode === 'release'">
              <header class="workspace-header"><div><small>课程级</small><h1>发布管理</h1></div><span :data-state="publicationState">{{ publicationLabel }}</span></header>
              <CourseGenerationGate v-if="task" :course-id="courseId" :task="task" @confirmed="handleGateConfirmed" />
              <section class="release-workspace">
                <div class="release-boundary"><CheckCircle2 :size="17" /><span><strong>教师工作稿与学生发布版相互隔离</strong>保存和 AI 优化只进入教师草稿；完成确认并发布后，学生端才读取新的冻结快照。</span></div>
                <div class="release-table" role="table" aria-label="发布资产检查">
                  <div class="release-table__head" role="row"><span>课程资产</span><span>教师当前状态</span><span>学生当前读取</span><span>处理</span></div>
                  <div v-for="row in releaseRows" :key="row.key" class="release-row" role="row">
                    <span><strong>{{ row.name }}</strong><small>{{ row.detail }}</small></span>
                    <span :data-state="row.teacherState">{{ row.teacherLabel }}</span>
                    <span>{{ row.studentLabel }}</span>
                    <button type="button" @click="row.action">{{ row.actionLabel }}</button>
                  </div>
                </div>
                <footer class="release-footer">
                  <span>当前正式修订：{{ courseStore.currentDocumentRevision || '尚未形成' }}</span>
                  <button type="button" @click="openStudentPreview"><Eye :size="15" />查看学生版</button>
                </footer>
              </section>
            </template>

            <div v-else-if="activeStageBlocked" class="stage-blocked" data-testid="production-stage-blocked" role="status">
              <LockKeyhole :size="28" />
              <div><strong>{{ activeStageLabel }}尚未开放</strong><span>{{ activeStageBlockReason }}</span></div>
              <button type="button" @click="router.push({ name: 'teacher-course-outline', params: { courseId } })">返回教学大纲</button>
            </div>

            <template v-else-if="activeStage === 'overview'">
              <header class="workspace-header"><div><small>全部课次</small><h1>课程生产总览</h1></div><span>{{ lessons.length }} 讲</span></header>
              <div class="lesson-overview">
                <table data-testid="production-lesson-table">
                  <thead><tr><th>讲次</th><th>教学主题</th><th>上课日期</th><th>教案状态</th><th>PPT 状态</th><th>学生发布版</th><th>下一步</th></tr></thead>
                  <tbody>
                    <tr
                      v-for="(lesson, index) in lessons"
                      :key="lesson.node_id"
                      :class="{ selected: previewLesson?.node_id === lesson.node_id }"
                      tabindex="0"
                      :aria-label="`预览第 ${index + 1} 讲：${lesson.node_name}`"
                      @click="previewLesson = lesson"
                      @keydown.enter="previewLesson = lesson"
                      @keydown.space.prevent="previewLesson = lesson"
                    >
                      <td><strong>{{ String(index + 1).padStart(2, '0') }}</strong></td>
                      <td><button type="button" class="lesson-link" @click.stop="previewLesson = lesson">{{ lesson.node_name }}</button></td>
                      <td><span class="lesson-date">{{ lessonDateLabel(lesson, index) }}</span></td>
                      <td><span :data-state="lessonState(lesson)">{{ lessonState(lesson) }}</span></td>
                      <td><span :data-state="pptStageState">{{ pptStageLabel }}</span></td>
                      <td>{{ isPublished ? '已发布' : '未发布' }}</td>
                      <td><button type="button" class="row-action" @click.stop="previewLesson = lesson">快速预览</button></td>
                    </tr>
                  </tbody>
                </table>
                <section v-if="previewLesson" class="lesson-preview" data-testid="production-lesson-preview">
                  <header>
                    <div><small>第 {{ lessonNumber(previewLesson) }} 讲 · {{ previewLessonPosition }}</small><h2>{{ previewLesson.node_name }}</h2></div>
                    <div class="preview-header-actions">
                      <button v-if="pptAvailable" type="button" class="preview-next" @click="continuePpt(previewLesson)"><Presentation :size="14" />下一步：PPT</button>
                      <button type="button" class="preview-close" aria-label="关闭预览" @click="previewLesson = null">×</button>
                    </div>
                  </header>
                  <div class="preview-scroll">
                    <div class="preview-body">
                      <div class="preview-context"><span>教案 {{ lessonState(previewLesson) }}</span><span>PPT {{ pptStageLabel }}</span><span>学生版 {{ isPublished ? '已发布' : '未发布' }}</span></div>
                      <strong>教学内容预览</strong>
                      <MarkdownRenderer class="preview-markdown" :content="nodePreviewContent(previewLesson)" :enable-code-run="false" />
                    </div>
                  </div>
                  <footer><div class="preview-navigation"><button type="button" :disabled="!previousPreviewLesson" @click="showPreviousLesson">上一讲</button><button type="button" :disabled="!nextPreviewLesson" @click="showNextLesson">下一讲</button></div><div class="preview-actions"><button type="button" @click="continueTeaching(previewLesson)">继续制作教案</button><button type="button" :disabled="!pptAvailable" @click="continuePpt(previewLesson)">进入 PPT 工作台</button></div></footer>
                </section>
              </div>
            </template>

            <template v-else-if="activeStage === 'teaching'">
              <div v-if="reviewStep === 'teaching' && task" class="teaching-review-gate">
                <CourseGenerationGate :course-id="courseId" :task="task" @confirmed="handleGateConfirmed" />
              </div>
              <div v-if="canConfirmTeacherSource" class="teacher-source-confirm" role="status">
                <div>
                  <strong>生成结果已完成，等待建立教师工作稿</strong>
                  <span>确认后建立可编辑教案与 PPT 的共同来源；不会发布学生版。</span>
                </div>
                <button type="button" class="primary-button" :disabled="teachingWorkbenchStore.pendingAction === 'confirmSource'" @click="confirmTeacherSource">
                  <LoaderCircle v-if="teachingWorkbenchStore.pendingAction === 'confirmSource'" :size="16" class="spin" />
                  <CheckCircle2 v-else :size="16" />
                  {{ teachingWorkbenchStore.pendingAction === 'confirmSource' ? '正在建立' : '确认并建立教案' }}
                </button>
              </div>
              <GenerationLessonPlan
                ref="lessonPlanRef"
                :plan="courseStore.currentTeachingPlan"
                :nodes="courseStore.nodes"
                :active-node-id="selectedNodeId"
                :course-id="courseId"
                :live="teachingPlanLive"
                :task="task"
                ai-dock-target="#teacher-course-ai-dock"
                prefer-section-view
                @select="selectLesson"
                @open-outline-editor="router.push({ name: 'teacher-course-outline', params: { courseId } })"
                @applied="handleTeachingPlanApplied"
              @ai-open-change="handleAiOpenChange"
              />
            </template>

            <template v-else-if="activeStage === 'ppt'">
              <header class="workspace-header"><div><small>下游表达</small><h1>课堂课件</h1></div><span :data-state="pptStageState">{{ pptStageLabel }}</span></header>
              <div class="ppt-entry">
                <Presentation :size="32" />
                <div><strong>{{ courseTitle }} · PPT 工作台</strong><span>课件继续使用现有同源构建、版本、预览和导出接口。</span></div>
                <button type="button" class="primary-button" :disabled="!pptAvailable" @click="openPpt"><ExternalLink :size="16" />打开 PPT 工作台</button>
              </div>
              <div v-if="!pptAvailable" class="boundary-note" role="status"><LockKeyhole :size="16" /><span>{{ pptBlockedReason }}</span><button type="button" @click="selectStage('teaching')">返回教案制作</button></div>
            </template>

          </section>

          <aside v-if="showAiDock" v-show="aiDockOpen" id="teacher-course-ai-dock" class="ai-dock" aria-label="AI 教案协作区">
            <div v-show="!aiPanelOpen" class="ai-dock__idle">
              <header class="ai-dock__header">
                <div><Sparkles :size="17" /><strong>AI 教案助手</strong></div>
                <div class="ai-dock__header-actions"><span>真实候选</span><button type="button" aria-label="收起 AI 助手" @click="aiDockOpen = false">×</button></div>
              </header>
              <div class="ai-dock__context">
                <small>当前处理</small>
                <strong>{{ selectedLessonLabel }}</strong>
                <span>{{ teacherAuthoringReady ? '建议只进入当前草稿，不会直接改正式版本' : '先确认生成结果并建立教师工作稿' }}</span>
              </div>
              <div class="ai-dock__flow" aria-label="AI 优化流程">
                <span><i>1</i>说明希望怎样优化</span>
                <span><i>2</i>逐项审阅 AI 候选</span>
                <span><i>3</i>接受后再确认新修订</span>
              </div>
              <div class="ai-dock__boundary">
                <strong>不会自动发布</strong>
                <span>学生仍读取当前发布快照；教师确认并重新发布后才会变化。</span>
              </div>
              <div v-if="aiFailureMessage" class="ai-dock__error" role="alert">
                <strong>当前还不能发起 AI 优化</strong>
                <span>{{ aiFailureMessage }}</span>
              </div>
              <button v-if="aiFailureMessage" type="button" class="ai-dock__primary" @click="router.push({ name: 'teacher-course-outline', params: { courseId } })">
                检查并补齐教学大纲
              </button>
              <button v-else type="button" class="ai-dock__primary" :disabled="!teacherAuthoringReady" @click="openTeachingAi">
                <Sparkles :size="16" />AI 优化当前教案
              </button>
            </div>
          </aside>
        </div>
      </main>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  CheckCircle2, ChevronRight, ExternalLink, Eye, LoaderCircle,
  LockKeyhole, Pause, Play, Presentation, RefreshCw, Sparkles, TriangleAlert,
} from 'lucide-vue-next'
import CourseGenerationGate from '../components/CourseGenerationGate.vue'
import CourseOutlineReview from '../components/CourseOutlineReview.vue'
import GenerationLessonPlan from '../components/GenerationLessonPlan.vue'
import MarkdownRenderer from '../components/MarkdownRenderer.vue'
import TeacherCourseSidebar from '../components/TeacherCourseSidebar.vue'
import { useTeacherCourseRuntime } from '../features/teacher-course/useTeacherCourseRuntime'
import { useTeachingRepresentationsStore } from '../stores/teachingRepresentations'
import { useTeachingPlanWorkbenchStore } from '../stores/teachingPlanWorkbench'
import { useTeachingCalendarStore } from '../stores/teachingCalendar'
import type { GuidedGenerationStep, GuidedGenerationStepKey, Node } from '../stores/types'
import {
  lessonUnitHasContent,
  lessonUnitPreviewMarkdown,
  projectLessonUnits,
  resolveLessonUnit,
} from '../utils/lesson-units'

type StageKey = 'overview' | 'teaching' | 'ppt'
type PageMode = 'outline' | 'production' | 'release'

const route = useRoute()
const router = useRouter()
const {
  course: courseStore,
  generation: generationStore,
  loadCourse: loadTeacherCourse,
  pptRoute,
} = useTeacherCourseRuntime()
const teachingRepresentationsStore = useTeachingRepresentationsStore()
const teachingWorkbenchStore = useTeachingPlanWorkbenchStore()
const teachingCalendarStore = useTeachingCalendarStore()
const activeStage = ref<StageKey>('overview')
const previewLesson = ref<Node | null>(null)
const loading = ref(false)
const loadError = ref('')
const actionBusy = ref(false)
const loadedCourseId = ref('')
const lessonPlanRef = ref<InstanceType<typeof GenerationLessonPlan> | null>(null)
const aiPanelOpen = ref(false)
const compactAiLayout = ref(typeof window !== 'undefined' ? window.innerWidth <= 1180 : false)
const aiDockOpen = ref(!compactAiLayout.value)
const aiFailureMessage = computed(() => teachingWorkbenchStore.errorMessage || '')

const courseId = computed(() => String(route.params.courseId || ''))
const pageMode = computed<PageMode>(() => route.name === 'teacher-course-outline' ? 'outline' : route.name === 'teacher-course-release' ? 'release' : 'production')
const pageTitle = computed(() => ({ outline: '教学大纲', production: '课程生产', release: '发布管理' } as Record<PageMode, string>)[pageMode.value])
const task = computed(() => generationStore.tasks.get(courseId.value))
const courseSummary = computed(() => courseStore.courseList.find(item => item.course_id === courseId.value))
const isPublished = computed(() => Boolean(courseSummary.value?.is_published))
const courseTitle = computed(() => courseStore.currentCourse?.course_name || task.value?.courseName || '未命名课程')
const courseTypeLabels: Record<string, string> = {
  systematic: '体系课程',
  project: '项目课程',
  inquiry: '探究课程',
  exam: '备考课程',
}
const courseMeta = computed(() => {
  if (isPublished.value) return '正式课程'
  const courseType = String(task.value?.courseType || '')
  if (courseTypeLabels[courseType]) return courseTypeLabels[courseType]
  return courseStore.currentCourseProjection === 'generation_preview' ? '生成中' : '课程草稿'
})
const isGenerationPreview = computed(() => courseStore.currentCourseProjection === 'generation_preview')
const activeWorkbench = computed(() => teachingWorkbenchStore.courseId === courseId.value ? teachingWorkbenchStore.workbench : null)
const teacherAuthoringReady = computed(() => Boolean(activeWorkbench.value?.available || activeWorkbench.value?.can_initialize))
const teachingPlanConfirmed = computed(() => Boolean(
  activeWorkbench.value?.available
  && activeWorkbench.value.current_plan_revision_id
  && !activeWorkbench.value.draft,
))
const generationTerminal = computed(() => ['completed', 'completed_with_warnings', 'error', 'conflict'].includes(String(task.value?.status || '')))
const canConfirmTeacherSource = computed(() => isGenerationPreview.value && generationTerminal.value && !teacherAuthoringReady.value)
const teachingPlanLive = computed(() => isGenerationPreview.value && !teacherAuthoringReady.value)
const reviewStep = computed(() => task.value?.guidedWorkflow?.review_step || '')
const stages = [
  { key: 'overview' as const, index: '01', label: '课次总览', scope: '巡视全课' },
  { key: 'teaching' as const, index: '02', label: '教案制作', scope: '按讲次' },
  { key: 'ppt' as const, index: '03', label: 'PPT', scope: '按需继续' },
]
const activeStageLabel = computed(() => stages.find(item => item.key === activeStage.value)?.label || '课程生产')
const currentContextLabel = computed(() => pageMode.value === 'production' ? activeStageLabel.value : pageTitle.value)
const showLessonRail = computed(() => pageMode.value === 'production' && ['teaching', 'ppt'].includes(activeStage.value) && lessons.value.length > 0)
const showAiDock = computed(() => pageMode.value === 'production' && activeStage.value === 'teaching')
const lessons = computed<Node[]>(() => projectLessonUnits(courseStore.nodes))
const courseSessions = computed(() => teachingCalendarStore.calendar?.course_id === courseId.value ? teachingCalendarStore.calendar.sessions : [])
const selectedLesson = computed(() => (
  resolveLessonUnit(courseStore.nodes, courseStore.currentNode?.node_id || '')
  || lessons.value[0]
  || null
))
const selectedNodeId = computed(() => selectedLesson.value?.node_id || '')
const selectedLessonLabel = computed(() => {
  const index = lessons.value.findIndex(item => item.node_id === selectedNodeId.value)
  const lesson = lessons.value[index]
  return lesson ? `第 ${String(index + 1).padStart(2, '0')} 讲 · ${lesson.node_name}` : '全课教案'
})
const pptAvailable = computed(() => teachingPlanConfirmed.value || isPublished.value)
const pptBlockedReason = computed(() => {
  if (!teacherAuthoringReady.value) return '请先确认生成结果，建立教师工作稿。'
  if (activeWorkbench.value?.draft) return '当前教案还有未确认草稿。请先审阅并确认，再制作 PPT。'
  return '请先建立并确认教案版本，再制作 PPT。'
})
const slideDeckRepresentation = computed(() => teachingRepresentationsStore.courseId === courseId.value
  ? teachingRepresentationsStore.representations.find(item => item.representation_type === 'slide_deck' && item.status !== 'archived')
  : undefined)
const pptStageState = computed(() => {
  if (!pptAvailable.value) return 'locked'
  if (slideDeckRepresentation.value?.status === 'ready') return 'confirmed'
  if (slideDeckRepresentation.value?.status === 'stale') return 'needs_regeneration'
  if (slideDeckRepresentation.value?.status === 'failed') return 'failed'
  if (slideDeckRepresentation.value?.status === 'building') return 'in_progress'
  return 'ready'
})
const pptStageLabel = computed(() => ({
  locked: '等待教案确认', confirmed: '已生成', needs_regeneration: '来源已更新',
  failed: '生成失败', in_progress: '生成中', ready: '可制作',
} as Record<string, string>)[pptStageState.value])
const previewLessonIndex = computed(() => lessons.value.findIndex(item => item.node_id === previewLesson.value?.node_id))
const previewLessonPosition = computed(() => previewLessonIndex.value >= 0 ? `${previewLessonIndex.value + 1} / ${lessons.value.length}` : '')
const previousPreviewLesson = computed(() => previewLessonIndex.value > 0 ? lessons.value[previewLessonIndex.value - 1] : null)
const nextPreviewLesson = computed(() => previewLessonIndex.value >= 0 && previewLessonIndex.value < lessons.value.length - 1 ? lessons.value[previewLessonIndex.value + 1] : null)
const canResume = computed(() => Boolean(
  task.value?.recovery?.can_resume
  && ['paused', 'error', 'conflict'].includes(String(task.value?.status || ''))
  && !actionBusy.value,
))
const canPause = computed(() => ['running', 'pending'].includes(String(task.value?.status || '')) && !actionBusy.value)
const taskStatusLabel = computed(() => {
  if (activeWorkbench.value?.draft) return '教案草稿编辑中'
  if (teachingPlanConfirmed.value) return '教案已确认'
  if (teacherAuthoringReady.value) return '教师工作稿已建立'
  return ({ pending: '等待开始', running: '生成中', paused: '已暂停', waiting_for_review: '等待确认', completed: '已完成', completed_with_warnings: '已完成，有建议', error: '生成失败', conflict: '版本冲突', idle: '未开始' }[task.value?.status || 'idle'])
})
const projectedTaskProgress = computed(() => generationTerminal.value ? 100 : Math.round(task.value?.progress || 0))
const nextActionLabel = computed(() => {
  if (isPublished.value && activeStage.value === 'teaching') return '教案可继续维护；下一步按需制作 PPT'
  if (isPublished.value && activeStage.value === 'ppt') return '正式课程源已就绪，可进入 PPT 工作台'
  if (isPublished.value) return '课程已发布，可继续维护教案或制作 PPT'
  if (reviewStep.value) return `请确认${stageLabel(reviewStep.value)}`
  if (canConfirmTeacherSource.value) return '生成已完成；请到教案制作建立教师工作稿'
  if (teacherAuthoringReady.value && !teachingPlanConfirmed.value) return '教师工作稿已建立；请确认教案后按需制作 PPT'
  return task.value?.currentStep || '等待任务推进'
})
const failedLessonCount = computed(() => task.value?.failedNodes?.length || 0)
const attentionCount = computed(() => failedLessonCount.value + (reviewStep.value ? 1 : 0))
const workflowSteps = computed<GuidedGenerationStep[]>(() => task.value?.guidedWorkflow?.steps || [])
const availableStageCount = computed(() => {
  return Number(lessons.value.length > 0) + Number(stageStatus('teaching') !== 'locked') + Number(pptAvailable.value)
})
const publicationState = computed(() => task.value?.publicationAllowed === false ? 'failed' : isPublished.value ? 'confirmed' : 'pending')
const publicationLabel = computed(() => task.value?.publicationAllowed === false ? '发布受阻' : isPublished.value ? '已发布' : '待发布')
const releaseRows = computed(() => [
  {
    key: 'outline', name: '教学大纲', detail: `${courseStore.nodes.length} 个课程节点`,
    teacherState: courseStore.nodes.length ? 'confirmed' : 'pending', teacherLabel: courseStore.nodes.length ? '已有内容' : '尚未建立',
    studentLabel: isPublished.value ? '随正式课程发布' : '不可见', actionLabel: '查看大纲',
    action: () => router.push({ name: 'teacher-course-outline', params: { courseId: courseId.value } }),
  },
  {
    key: 'teaching', name: '分讲教案', detail: `${lessons.value.length} 讲`,
    teacherState: lessons.value.length ? 'confirmed' : 'pending', teacherLabel: lessons.value.length ? '已有教案来源' : '等待大纲',
    studentLabel: isPublished.value ? '按正式课程读取' : '不可见', actionLabel: '继续制作',
    action: () => router.push({ name: 'teacher-course-production', params: { courseId: courseId.value }, query: { stage: 'teaching' } }),
  },
  {
    key: 'ppt', name: '课堂 PPT', detail: '独立版本与导出工作台',
    teacherState: pptStageState.value, teacherLabel: pptStageLabel.value,
    studentLabel: isPublished.value ? '读取已发布课件快照' : '不可见', actionLabel: '打开 PPT', action: openPpt,
  },
])
const activeStageBlocked = computed(() => activeStage.value === 'teaching' && stageStatus('teaching') === 'locked')
const activeStageBlockReason = computed(() => '请先到教学大纲页完成并确认大纲。确认后可以进入分讲教案；教学日历可与教案并行维护。')

function stageLabel(value: string) {
  return ({ requirements: '课程要求', outline: '教学大纲', knowledge: '课程知识', teaching: '课堂教案', content: '课程正文', ppt: '课堂课件', release: '发布审阅', overview: '课次总览' } as Record<string, string>)[value] || value
}
function workflowStatusLabel(value: string) {
  return ({ locked: '尚未开放', ready: '可制作', pending: '等待处理', in_progress: '进行中', waiting_for_confirmation: '等待确认', confirmed: '已确认', needs_regeneration: '需要重建', failed: '失败', auto_resuming: '自动恢复中', manual_resume: '等待手动恢复', quality_blocked: '质量检查阻断', conflict: '版本冲突', unavailable: '不可恢复', completed: '已完成' } as Record<string, string>)[value] || value
}
function stageStatus(key: StageKey) {
  if (key === 'overview') return lessons.value.length ? 'confirmed' : 'pending'
  if (key === 'ppt') return pptStageState.value
  if (activeWorkbench.value?.draft) return 'in_progress'
  if (teachingPlanConfirmed.value) return 'confirmed'
  if (activeWorkbench.value?.can_initialize) return 'ready'
  const step = workflowSteps.value.find(item => item.key === key)
  if (step) return step.status
  if (!task.value && !isGenerationPreview.value) return 'pending'
  return 'locked'
}
function stageStatusLabel(key: StageKey) { return workflowStatusLabel(stageStatus(key)) }
function lessonState(node: Node) { return node.error_summary ? '需要处理' : lessonUnitHasContent(courseStore.nodes, node) ? '已有内容' : '等待生成' }
function lessonDateLabel(node: Node, index: number) {
  const matched = courseSessions.value.filter(session => session.lesson_unit_id === node.node_id || (!session.lesson_unit_id && session.sequence === index + 1))
  if (!matched.length) return '待排期'
  const dated = matched.filter(session => session.date)
  if (!dated.length) return `${matched.length} 条待排期`
  const first = dated[0]?.date?.slice(5).replace('-', '/') || '待排期'
  return dated.length > 1 ? `${first} 等 ${dated.length} 次` : first
}
function selectStage(key: StageKey) {
  activeStage.value = key
  if (['teaching', 'ppt'].includes(key) && lessons.value[0] && !lessons.value.some(node => node.node_id === courseStore.currentNode?.node_id)) {
    courseStore.selectNode(lessons.value[0])
  }
  if (pageMode.value === 'production') {
    const nextStage = key === 'overview' ? '' : key
    if (String(route.query.stage || '') !== nextStage) {
      const query = { ...route.query, stage: nextStage || undefined }
      void router.replace({ name: 'teacher-course-production', params: { courseId: courseId.value }, query })
    }
  }
}
function selectLesson(node: Node) {
  courseStore.selectNode(node)
  if (pageMode.value !== 'production' || String(route.query.node || '') === node.node_id) return
  void router.replace({
    name: 'teacher-course-production',
    params: { courseId: courseId.value },
    query: { ...route.query, node: node.node_id },
  })
}
function lessonNumber(node: Node) { return String(Math.max(1, lessons.value.findIndex(item => item.node_id === node.node_id) + 1)).padStart(2, '0') }
function nodePreviewContent(node: Node) {
  return lessonUnitPreviewMarkdown(courseStore.nodes, node)
}
function showPreviousLesson() { if (previousPreviewLesson.value) previewLesson.value = previousPreviewLesson.value }
function showNextLesson() { if (nextPreviewLesson.value) previewLesson.value = nextPreviewLesson.value }
function continueTeaching(node: Node) { selectLesson(node); selectStage('teaching'); previewLesson.value = null }
async function openTeachingAi() { aiDockOpen.value = true; await nextTick(); void lessonPlanRef.value?.openAiAssistant('section') }
function handleAiOpenChange(open: boolean) { aiPanelOpen.value = open; if (open) aiDockOpen.value = true }
function continuePpt(node: Node) { selectLesson(node); openPpt() }
function openPpt() {
  if (!pptAvailable.value) return
  const returnTo = router.resolve({ name: 'teacher-course-production', params: { courseId: courseId.value }, query: { stage: 'ppt', node: selectedNodeId.value || undefined } }).fullPath
  void router.push(pptRoute(courseId.value, {
    returnTo,
    nodeId: selectedNodeId.value,
  }))
}
function openStudentPreview() {
  const returnTo = router.resolve({
    name: pageMode.value === 'release' ? 'teacher-course-release' : 'teacher-course-production',
    params: { courseId: courseId.value },
    query: pageMode.value === 'production' ? { stage: activeStage.value, node: selectedNodeId.value || undefined } : undefined,
  }).fullPath
  void router.push({
    name: 'learning',
    params: { courseId: courseId.value },
    query: { teacherPreview: '1', returnTo },
  })
}

async function confirmTeacherSource() {
  if (!task.value || !canConfirmTeacherSource.value) return
  actionBusy.value = true
  try {
    await teachingWorkbenchStore.confirmGenerationPreview(courseId.value, task.value.id)
    ElMessage.success('已建立教师工作稿；学生版仍保持不变')
  } catch {
    ElMessage.error(teachingWorkbenchStore.errorMessage || '教师工作稿建立失败，请重试')
  } finally {
    actionBusy.value = false
  }
}

async function loadCourse() {
  const id = courseId.value
  if (!id || loadedCourseId.value === id || loading.value) return
  loading.value = true
  loadError.value = ''
  try {
    generationStore.restoreGenerationState()
    generationStore.initWebSocket()
    await courseStore.fetchCourseList()
    await loadTeacherCourse(id)
    try { await teachingCalendarStore.loadCourse(id) } catch { /* Calendar absence does not block production. */ }
    try { await teachingWorkbenchStore.load(id) } catch { /* Workbench state is rendered as an actionable boundary. */ }
    if (isPublished.value || teacherAuthoringReady.value) {
      try { await teachingRepresentationsStore.load(id) } catch { /* PPT registry failure must not block the course workspace. */ }
    }
    generationStore.observeCourse(id)
    loadedCourseId.value = id
    const requestedStage = String(route.query.stage || '')
    activeStage.value = requestedStage === 'teaching' || requestedStage === 'ppt' ? requestedStage : 'overview'
    const requestedNode = String(route.query.node || '')
    const requestedLesson = resolveLessonUnit(courseStore.nodes, requestedNode)
    if (requestedLesson) {
      courseStore.selectNode(requestedLesson)
      if (activeStage.value === 'overview') previewLesson.value = requestedLesson
    }
    else if (lessons.value[0] && !lessons.value.some(node => node.node_id === courseStore.currentNode?.node_id)) courseStore.selectNode(lessons.value[0])
  } catch (error) {
    loadError.value = String((error as any)?.response?.data?.detail || (error as Error)?.message || '未知错误')
  } finally { loading.value = false }
}
async function refresh() {
  loadedCourseId.value = ''
  await loadCourse()
}
async function pauseTask() {
  if (!task.value || actionBusy.value) return
  actionBusy.value = true
  try { await generationStore.pauseTask(courseId.value, task.value.id); await refresh() } finally { actionBusy.value = false }
}
async function resumeTask() {
  if (!task.value || actionBusy.value) return
  actionBusy.value = true
  try { await generationStore.resumeTask(courseId.value, task.value.id); await refresh() } finally { actionBusy.value = false }
}
async function handleGateConfirmed(step?: GuidedGenerationStepKey) {
  if (step) ElMessage.success(`${stageLabel(step)}已确认`)
  await refresh()
}
async function handleTeachingPlanApplied() { await refresh(); ElMessage.success('教案修订已应用，影响状态已刷新') }

watch(courseId, async (next, previous) => {
  if (previous) generationStore.unobserveCourse(previous)
  loadedCourseId.value = ''
  if (next) await loadCourse()
}, { immediate: true })
watch(() => route.query.stage, value => {
  if (pageMode.value !== 'production') return
  const requestedStage = String(value || '')
  if (requestedStage === 'teaching' || requestedStage === 'ppt') selectStage(requestedStage)
})
function syncAiLayout() {
  const nextCompact = window.innerWidth <= 1180
  if (nextCompact === compactAiLayout.value) return
  compactAiLayout.value = nextCompact
  aiDockOpen.value = !nextCompact
}
onMounted(() => window.addEventListener('resize', syncAiLayout))
onBeforeUnmount(() => {
  window.removeEventListener('resize', syncAiLayout)
  if (courseId.value) generationStore.unobserveCourse(courseId.value)
})
</script>

<style scoped>
.teacher-production { min-height:100vh; height:100vh; overflow:hidden; color:var(--lz-text-primary); background:var(--lz-canvas); }
button { font:inherit; }
.product-bar { height:52px; display:grid; grid-template-columns:188px minmax(0,1fr) auto; align-items:center; border-bottom:1px solid var(--lz-border); background:var(--lz-surface); }
.brand { height:100%; display:flex; align-items:center; gap:10px; padding:0 20px; border:0; border-right:1px solid var(--lz-border); color:var(--lz-text-primary); background:transparent; cursor:pointer; }
.brand img { width:25px; height:25px; }.brand strong { font-size:17px; }
.product-bar nav { min-width:0; display:flex; align-items:center; gap:8px; padding:0 24px; color:var(--lz-text-muted); font-size:12px; }
.product-bar nav button { max-width:220px; overflow:hidden; padding:0; border:0; color:inherit; background:transparent; text-overflow:ellipsis; white-space:nowrap; cursor:pointer; }.product-bar nav strong { color:var(--lz-text-primary); }
.product-actions { display:flex; align-items:center; gap:6px; padding-right:14px; }.product-actions button { height:34px; display:inline-flex; align-items:center; gap:6px; padding:0 11px; border:1px solid var(--lz-border); border-radius:9px; color:var(--lz-text-secondary); background:var(--lz-surface); cursor:pointer; }
.production-shell { height:calc(100vh - 52px); display:grid; grid-template-columns:188px minmax(0,1fr); }
.course-sidebar { min-height:0; display:flex; flex-direction:column; border-right:1px solid var(--lz-border); background:var(--lz-surface); }
.course-identity { min-height:66px; display:flex; align-items:center; gap:10px; padding:0 15px; border-bottom:1px solid var(--lz-border); }.course-identity > span { width:34px; height:34px; display:grid; place-items:center; border-radius:9px; color:var(--lz-brand-strong); background:var(--lz-brand-soft); font-weight:800; }.course-identity div { min-width:0; display:grid; }.course-identity strong,.course-identity small { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }.course-identity strong { font-size:12px; }.course-identity small { margin-top:3px; color:var(--lz-text-muted); font-size:10px; }
.course-sidebar nav { display:grid; gap:4px; padding:12px 8px; }.course-sidebar nav button { height:38px; display:grid; grid-template-columns:22px minmax(0,1fr) auto; align-items:center; gap:7px; padding:0 10px; border:0; border-radius:8px; color:var(--lz-text-secondary); background:transparent; text-align:left; cursor:pointer; }.course-sidebar nav button.active { color:var(--lz-brand-strong); background:var(--lz-brand-soft); font-weight:700; }.course-sidebar nav button span { min-width:19px; padding:2px 5px; border-radius:9px; background:var(--lz-surface); color:var(--lz-brand-strong); font-size:9px; text-align:center; }
.back-library { margin-top:auto; height:42px; display:flex; align-items:center; gap:7px; padding:0 18px; border:0; border-top:1px solid var(--lz-border); color:var(--lz-text-muted); background:transparent; cursor:pointer; }
.production-main { min-width:0; min-height:0; display:flex; flex-direction:column; }
.course-status { min-width:0; display:flex; align-items:center; gap:0; padding:0 14px; border-bottom:1px solid var(--lz-border); background:var(--lz-surface); font-size:11px; white-space:nowrap; }.course-status > strong,.course-status > span { padding:0 11px; border-right:1px solid var(--lz-border); }.course-status > strong { padding-left:0; }.course-status .status-spacer { flex:1; border:0; }.course-status .next-action { max-width:260px; overflow:hidden; border:0; color:var(--lz-brand-strong); text-overflow:ellipsis; }.status-action { display:flex; align-items:center; gap:5px; height:28px; padding:0 10px; border:0; border-radius:7px; color:var(--lz-brand-strong); background:var(--lz-brand-soft); cursor:pointer; }
.course-status { flex:0 0 42px; }
.production-tabs { flex:0 0 46px; min-width:0; display:flex; align-items:center; gap:12px; padding:0 14px; border-bottom:1px solid var(--lz-border); background:var(--lz-surface); }
.segmented-tabs { display:flex; align-items:center; gap:2px; padding:3px; border:1px solid var(--lz-border); border-radius:9px; background:var(--lz-fill); }
.segmented-tabs button { height:30px; display:inline-flex; align-items:center; gap:7px; padding:0 11px; border:0; border-radius:6px; color:var(--lz-text-secondary); background:transparent; cursor:pointer; }
.segmented-tabs button.active { color:var(--lz-brand-strong); background:var(--lz-surface); box-shadow:0 1px 3px rgb(15 23 42 / 8%); font-weight:700; }
.segmented-tabs button span { color:var(--lz-text-muted); font-size:9px; font-weight:500; }
.segmented-tabs button span[data-state="confirmed"] { color:var(--lz-success); }
.segmented-tabs button span[data-state="ready"] { color:var(--lz-brand-strong); }
.segmented-tabs button span[data-state="failed"],.segmented-tabs button span[data-state="needs_regeneration"] { color:var(--lz-danger); }
.production-tabs__summary { color:var(--lz-text-muted); font-size:10px; }
.teacher-source-confirm{display:flex;align-items:center;justify-content:space-between;gap:18px;margin:14px 18px 0;padding:12px 14px;border:1px solid var(--lz-brand-border);border-radius:10px;background:var(--lz-brand-soft)}.teacher-source-confirm>div{min-width:0;display:grid;gap:4px}.teacher-source-confirm strong{font-size:12px}.teacher-source-confirm span{color:var(--lz-text-secondary);font-size:10px}.teacher-source-confirm .primary-button{flex:0 0 auto}
.production-tabs__actions{display:flex;flex:0 0 auto;align-items:center;gap:6px;margin-left:auto}.production-tabs__actions button{height:30px;display:inline-flex;align-items:center;gap:5px;padding:0 10px;border:1px solid var(--lz-border);border-radius:7px;color:var(--lz-text-secondary);background:var(--lz-surface);cursor:pointer;white-space:nowrap}.production-tabs__actions .next-step-button{border-color:var(--lz-brand);color:#fff;background:var(--lz-brand);font-weight:700}.production-tabs__actions button:disabled{opacity:.45;cursor:not-allowed}.production-tabs__actions .ai-toggle[aria-expanded="true"]{border-color:var(--lz-brand-border);color:var(--lz-brand-strong);background:var(--lz-brand-soft)}
.workspace-grid { flex:1 1 auto; min-width:0; min-height:0; display:grid; grid-template-columns:minmax(0,1fr); }
.workspace-grid.immersive { grid-template-columns:196px minmax(0,1fr); }
.workspace-grid.immersive.with-ai-dock { grid-template-columns:196px minmax(0,1fr) 316px; }
.workspace-grid.single-page { grid-template-columns:minmax(0,1fr); }
.lesson-rail { min-width:0; min-height:0; overflow:auto; border-right:1px solid var(--lz-border); background:var(--lz-surface); }
.lesson-rail > header { height:38px; display:flex; align-items:center; justify-content:space-between; padding:0 12px; border-bottom:1px solid var(--lz-border); color:var(--lz-text-secondary); font-size:10px; }
.teaching-review-gate { border-bottom:1px solid var(--lz-border); background:var(--lz-warning-soft); }
.stage-sidebar,.status-sidebar { min-height:0; overflow:auto; background:var(--lz-surface); }.stage-sidebar { border-right:1px solid var(--lz-border); }.stage-sidebar > header,.status-sidebar > header { height:42px; display:flex; align-items:center; justify-content:space-between; padding:0 12px; border-bottom:1px solid var(--lz-border); font-size:11px; }.stage-sidebar header small { color:var(--lz-text-muted); }
.stage-list { display:grid; padding:6px; }.stage-list button { min-height:48px; display:grid; grid-template-columns:25px minmax(0,1fr) 18px; align-items:center; gap:7px; padding:6px 8px; border:1px solid transparent; border-radius:8px; color:var(--lz-text-secondary); background:transparent; text-align:left; cursor:pointer; }.stage-list button.active { border-color:var(--lz-brand-border); color:var(--lz-brand-strong); background:var(--lz-brand-soft); }.stage-index { color:var(--lz-brand); font-size:10px; font-weight:800; }.stage-list button > span:nth-child(2) { min-width:0; display:grid; gap:2px; }.stage-list strong { overflow:hidden; font-size:11px; text-overflow:ellipsis; white-space:nowrap; }.stage-list small { color:var(--lz-text-muted); font-size:9px; }.stage-list i { width:18px; height:18px; display:grid; place-items:center; border-radius:50%; color:var(--lz-text-muted); background:var(--lz-fill); }.stage-list i[data-state="confirmed"] { color:var(--lz-success); background:var(--lz-success-soft); }.stage-list i[data-state="failed"],.stage-list i[data-state="needs_regeneration"] { color:var(--lz-warning); background:var(--lz-warning-soft); }
.lesson-heading { height:34px; display:flex; align-items:center; justify-content:space-between; padding:0 12px; border-top:1px solid var(--lz-border); border-bottom:1px solid var(--lz-border); color:var(--lz-text-secondary); font-size:10px; }.lesson-list { display:grid; padding:5px; }.lesson-list button { min-height:43px; display:grid; grid-template-columns:26px minmax(0,1fr); align-items:center; gap:6px; padding:5px 7px; border:1px solid transparent; border-radius:7px; color:var(--lz-text-secondary); background:transparent; text-align:left; cursor:pointer; }.lesson-list button.active { border-color:var(--lz-brand-border); background:var(--lz-brand-soft); }.lesson-list button > span:first-child { color:var(--lz-brand); font-size:9px; font-weight:800; }.lesson-list button > span:last-child { min-width:0; display:grid; gap:2px; }.lesson-list strong { overflow:hidden; font-size:10px; text-overflow:ellipsis; white-space:nowrap; }.lesson-list small { color:var(--lz-text-muted); font-size:9px; }
.stage-workspace { min-width:0; min-height:0; overflow:auto; background:var(--lz-surface); }.stage-workspace.outline-mode{overflow:hidden}.workspace-state { height:100%; display:grid; place-content:center; justify-items:center; gap:9px; color:var(--lz-text-muted); }.workspace-state.is-error { color:var(--lz-danger); }.workspace-state button { padding:7px 14px; border:1px solid var(--lz-border); border-radius:8px; background:var(--lz-surface); cursor:pointer; }
.ai-dock { min-width:0; min-height:0; overflow:auto; border-left:1px solid var(--lz-border); background:var(--lz-surface); }
.ai-dock__idle { min-height:100%; }
.ai-dock__header { height:48px; display:flex; align-items:center; justify-content:space-between; padding:0 15px; border-bottom:1px solid var(--lz-border); }
.ai-dock__header div { display:flex; align-items:center; gap:8px; color:var(--lz-brand-strong); }
.ai-dock__header .ai-dock__header-actions{gap:6px}.ai-dock__header-actions button{width:25px;height:25px;display:grid;place-items:center;border:0;border-radius:6px;color:var(--lz-text-muted);background:var(--lz-fill);cursor:pointer;font-size:16px}
.ai-dock__header strong { color:var(--lz-text-primary); font-size:12px; }
.ai-dock__header span { padding:3px 7px; border-radius:7px; color:var(--lz-success); background:var(--lz-success-soft); font-size:9px; }
.ai-dock__context { display:grid; gap:6px; padding:17px 15px; border-bottom:1px solid var(--lz-border); }
.ai-dock__context small { color:var(--lz-text-muted); font-size:9px; }
.ai-dock__context strong { font-size:12px; line-height:1.45; }
.ai-dock__context span,.ai-dock__boundary span { color:var(--lz-text-secondary); font-size:10px; line-height:1.65; }
.ai-dock__flow { display:grid; gap:11px; padding:16px 15px; border-bottom:1px solid var(--lz-border); }
.ai-dock__flow span { display:flex; align-items:center; gap:8px; color:var(--lz-text-secondary); font-size:10px; }
.ai-dock__flow i { width:20px; height:20px; display:grid; place-items:center; flex:0 0 auto; border-radius:50%; color:var(--lz-brand-strong); background:var(--lz-brand-soft); font-size:9px; font-style:normal; font-weight:800; }
.ai-dock__boundary { display:grid; gap:5px; margin:14px 15px; padding:11px 12px; border:1px solid var(--lz-warning-border); border-radius:8px; background:var(--lz-warning-soft); }
.ai-dock__boundary strong { color:var(--lz-text-primary); font-size:10px; }
.ai-dock__error{display:grid;gap:5px;margin:0 15px 12px;padding:10px 11px;border:1px solid var(--lz-danger-border);border-radius:8px;color:var(--lz-danger);background:var(--lz-danger-soft)}.ai-dock__error strong{font-size:10px}.ai-dock__error span{font-size:9px;line-height:1.55}
.ai-dock__primary { width:calc(100% - 30px); height:36px; display:flex; align-items:center; justify-content:center; gap:7px; margin:0 15px; border:1px solid var(--lz-brand); border-radius:8px; color:#fff; background:var(--lz-brand); cursor:pointer; font-weight:700; }
.ai-dock__primary:disabled { opacity:.45; cursor:not-allowed; }
.lesson-overview { position:relative; min-height:calc(100% - 58px); overflow:auto; }
.lesson-overview table { width:100%; border-collapse:collapse; table-layout:fixed; font-size:11px; }
.lesson-overview th { height:38px; padding:0 12px; border-bottom:1px solid var(--lz-border); color:var(--lz-text-muted); background:var(--lz-fill); text-align:left; font-size:10px; font-weight:650; }
.lesson-overview th:nth-child(1) { width:64px; }.lesson-overview th:nth-child(3) { width:96px; }.lesson-overview th:nth-child(4),.lesson-overview th:nth-child(5),.lesson-overview th:nth-child(6) { width:106px; }.lesson-overview th:last-child { width:92px; }
.lesson-overview td { height:48px; padding:7px 12px; border-bottom:1px solid var(--lz-border); color:var(--lz-text-secondary); vertical-align:middle; }
.lesson-overview tbody tr { cursor:pointer; }.lesson-overview tbody tr:hover td,.lesson-overview tr.selected td { background:var(--lz-brand-soft); }.lesson-overview td:first-child strong { color:var(--lz-brand); }
.lesson-link,.row-action { padding:0; border:0; color:var(--lz-text-primary); background:transparent; cursor:pointer; text-align:left; }.lesson-link { max-width:100%; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-weight:650; }.row-action { color:var(--lz-brand-strong); }
.lesson-overview td span { display:inline-flex; padding:3px 7px; border-radius:7px; color:var(--lz-text-muted); background:var(--lz-fill); font-size:9px; }.lesson-overview td span[data-state="已有内容"],.lesson-overview td span[data-state="ready"] { color:var(--lz-success); background:var(--lz-success-soft); }.lesson-overview td span[data-state="需要处理"] { color:var(--lz-danger); background:var(--lz-danger-soft); }
.lesson-preview { position:absolute; inset:0; z-index:3; display:grid; grid-template-rows:62px minmax(0,1fr) 54px; background:#fff; box-shadow:-8px 0 24px rgb(15 23 42 / 6%); }.lesson-preview > header { display:flex; align-items:center; justify-content:space-between; gap:18px; padding:0 22px; border-bottom:1px solid var(--lz-border); background:#fff; }.lesson-preview header>div:first-child { min-width:0; display:grid; gap:3px; }.lesson-preview header small { color:var(--lz-brand); font-size:9px; font-weight:800; }.lesson-preview h2 { overflow:hidden;margin:0;font-size:17px;text-overflow:ellipsis;white-space:nowrap}.preview-header-actions{display:flex!important;grid-auto-flow:column!important;align-items:center;gap:7px!important}.lesson-preview header .preview-close { width:30px; height:30px; border:0; border-radius:7px; color:var(--lz-text-muted); background:var(--lz-fill); cursor:pointer; font-size:20px; }.lesson-preview header .preview-next{width:auto;height:30px;display:inline-flex;align-items:center;gap:5px;padding:0 10px;border:1px solid var(--lz-brand);border-radius:7px;color:#fff;background:var(--lz-brand);cursor:pointer;font-size:10px;font-weight:700}.preview-scroll{min-height:0;overflow:auto;background:#fff}.preview-body { max-width:900px; padding:24px 34px 42px; background:#fff; }.preview-body>strong { display:block;margin-bottom:12px;font-size:12px; }.preview-markdown{color:var(--lz-text-secondary);font-size:12px;line-height:1.82}.lesson-preview footer { display:flex; justify-content:flex-end; gap:8px; padding:9px 18px; border-top:1px solid var(--lz-border); background:#fff; }.lesson-preview footer button { height:34px; padding:0 13px; border:1px solid var(--lz-border); border-radius:8px; color:var(--lz-text-secondary); background:var(--lz-surface); cursor:pointer; }.lesson-preview footer button:first-child { border-color:var(--lz-brand); color:#fff; background:var(--lz-brand); }.lesson-preview footer button:disabled { opacity:.45; cursor:not-allowed; }
.preview-context { min-height:34px; display:flex; align-items:center; margin-bottom:22px; border-bottom:1px solid var(--lz-border); color:var(--lz-text-muted); font-size:10px; }.preview-context span { padding:0 12px; border-right:1px solid var(--lz-border); }.preview-context span:first-child { padding-left:0; }.lesson-preview footer { align-items:center; justify-content:space-between; }.preview-navigation,.preview-actions { display:flex; gap:8px; }.lesson-preview footer .preview-navigation button:first-child { border-color:var(--lz-border); color:var(--lz-text-secondary); background:var(--lz-surface); }.lesson-preview footer .preview-actions button:first-child { border-color:var(--lz-brand); color:#fff; background:var(--lz-brand); }
.workspace-header { height:58px; display:flex; align-items:center; justify-content:space-between; padding:0 18px; border-bottom:1px solid var(--lz-border); }.workspace-header > div { display:grid; gap:2px; }.workspace-header small { color:var(--lz-brand); font-size:9px; font-weight:800; }.workspace-header h1 { margin:0; font-size:17px; }.workspace-header > span { padding:4px 8px; border-radius:8px; color:var(--lz-text-muted); background:var(--lz-fill); font-size:10px; }.workspace-header > span[data-state="confirmed"] { color:var(--lz-success); background:var(--lz-success-soft); }.workspace-header > span[data-state="failed"] { color:var(--lz-danger); background:var(--lz-danger-soft); }
.brief-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); margin:0; padding:0 18px; }.brief-grid > div { min-height:62px; display:grid; align-content:center; gap:5px; border-bottom:1px solid var(--lz-border); }.brief-grid > div:nth-child(odd) { padding-right:18px; border-right:1px solid var(--lz-border); }.brief-grid > div:nth-child(even) { padding-left:18px; }.brief-grid .wide { grid-column:1/-1; padding:14px 0 !important; border-right:0 !important; }.brief-grid dt { color:var(--lz-text-muted); font-size:10px; }.brief-grid dd { margin:0; font-size:12px; font-weight:650; line-height:1.6; }.boundary-note { display:flex; align-items:flex-start; gap:8px; margin:16px 18px; padding:10px 12px; border:1px solid var(--lz-warning-border); border-radius:8px; color:var(--lz-text-secondary); background:var(--lz-warning-soft); font-size:11px; line-height:1.6; }.boundary-note svg { flex:0 0 auto; margin-top:1px; }
.ppt-entry,.release-summary { min-height:86px; display:grid; grid-template-columns:42px minmax(0,1fr) auto; align-items:center; gap:12px; margin:0 18px; border-bottom:1px solid var(--lz-border); }.ppt-entry > div,.release-summary > div { display:grid; gap:4px; }.ppt-entry span,.release-summary span { color:var(--lz-text-muted); font-size:10px; }.ppt-entry button,.release-summary button { height:34px; display:flex; align-items:center; gap:6px; padding:0 12px; border:1px solid var(--lz-border); border-radius:8px; background:var(--lz-surface); cursor:pointer; }.ppt-entry .primary-button { border-color:var(--lz-brand); color:#fff; background:var(--lz-brand); }.ppt-entry button:disabled { opacity:.45; cursor:not-allowed; }.production-content { min-height:100%; }
.release-workspace{max-width:1080px;margin:0 auto;padding:0 24px 30px}.release-boundary{display:flex;align-items:flex-start;gap:9px;padding:13px 0 15px;border-bottom:1px solid var(--lz-border);color:var(--lz-brand-strong);font-size:10px}.release-boundary span{display:grid;gap:3px;color:var(--lz-text-secondary);line-height:1.55}.release-boundary strong{color:var(--lz-text-primary);font-size:11px}.release-table{border-top:1px solid var(--lz-border)}.release-table__head,.release-row{display:grid;grid-template-columns:minmax(210px,1.2fr) 150px minmax(160px,1fr) 92px;align-items:center;gap:12px;padding:0 8px;border-bottom:1px solid var(--lz-border)}.release-table__head{height:35px;color:var(--lz-text-muted);background:var(--lz-fill);font-size:9px}.release-row{min-height:58px;color:var(--lz-text-secondary);font-size:10px}.release-row>span:first-child{display:grid;gap:4px}.release-row strong{color:var(--lz-text-primary);font-size:11px}.release-row small{color:var(--lz-text-muted);font-size:9px}.release-row>span:nth-child(2){width:max-content;padding:3px 7px;border-radius:7px;background:var(--lz-fill);font-size:9px}.release-row>span[data-state="confirmed"]{color:var(--lz-success);background:var(--lz-success-soft)}.release-row button{height:30px;padding:0 9px;border:1px solid var(--lz-border);border-radius:7px;color:var(--lz-brand-strong);background:var(--lz-surface);cursor:pointer}.release-footer{min-height:54px;display:flex;align-items:center;justify-content:space-between;gap:14px;border-bottom:1px solid var(--lz-border);color:var(--lz-text-muted);font-size:10px}.release-footer button{height:32px;display:inline-flex;align-items:center;gap:6px;padding:0 10px;border:1px solid var(--lz-border);border-radius:8px;color:var(--lz-text-secondary);background:var(--lz-surface);cursor:pointer}
.stage-blocked { height:100%; display:grid; place-content:center; grid-template-columns:34px minmax(0,360px); align-items:start; gap:10px; color:var(--lz-text-muted); }.stage-blocked > div { display:grid; gap:5px; }.stage-blocked strong { color:var(--lz-text-primary); font-size:13px; }.stage-blocked span { font-size:10px; line-height:1.6; }.stage-blocked button { grid-column:2; justify-self:start; height:32px; padding:0 11px; border:1px solid var(--lz-border); border-radius:7px; color:var(--lz-brand-strong); background:var(--lz-surface); cursor:pointer; }
.status-sidebar { border-left:1px solid var(--lz-border); }.status-sidebar header button { display:grid; place-items:center; padding:4px; border:0; color:var(--lz-text-muted); background:transparent; cursor:pointer; }.status-facts { display:grid; grid-template-columns:1fr 1fr; margin:0; border-bottom:1px solid var(--lz-border); }.status-facts div { min-height:56px; display:grid; align-content:center; gap:4px; padding:9px 11px; border-right:1px solid var(--lz-border); border-bottom:1px solid var(--lz-border); }.status-facts div:nth-child(even) { border-right:0; }.status-facts dt { color:var(--lz-text-muted); font-size:9px; }.status-facts dd { overflow:hidden; margin:0; font-size:10px; font-weight:700; text-overflow:ellipsis; white-space:nowrap; }.status-sidebar section { padding:12px; border-bottom:1px solid var(--lz-border); }.status-sidebar h2 { margin:0 0 9px; font-size:10px; }.status-sidebar p { margin:0; color:var(--lz-text-secondary); font-size:10px; line-height:1.6; }.workflow-list { display:grid; gap:9px; margin:0; padding:0; list-style:none; }.workflow-list li { display:grid; grid-template-columns:20px minmax(0,1fr); gap:7px; align-items:center; }.workflow-list li > span { width:18px; height:18px; display:grid; place-items:center; border-radius:50%; color:var(--lz-text-muted); background:var(--lz-fill); font-size:9px; }.workflow-list li[data-state="confirmed"] > span { color:var(--lz-success); background:var(--lz-success-soft); }.workflow-list li > div { min-width:0; display:grid; }.workflow-list strong { font-size:10px; }.workflow-list small { color:var(--lz-text-muted); font-size:9px; }.error-panel { color:var(--lz-danger); background:var(--lz-danger-soft); }.error-panel code { display:block; margin-top:6px; font-size:9px; }.sidebar-actions { display:grid; gap:7px; padding:12px; }.sidebar-actions button { height:32px; border:1px solid var(--lz-border); border-radius:8px; color:var(--lz-text-secondary); background:var(--lz-surface); cursor:pointer; }
.spin { animation:spin .9s linear infinite; } @keyframes spin { to { transform:rotate(360deg); } }
@media (max-width:1180px) { .course-status > span:nth-of-type(n+4) { display:none; } }
@media (max-width:1180px) { .workspace-grid.immersive.with-ai-dock { position:relative;grid-template-columns:176px minmax(0,1fr); }.workspace-grid.immersive.with-ai-dock .ai-dock{position:absolute;z-index:8;top:0;right:0;bottom:0;width:316px;box-shadow:-12px 0 28px rgb(15 23 42 / 13%)} }
@media (max-width:900px) { .product-bar { grid-template-columns:150px minmax(0,1fr) auto; }.brand { padding:0 15px; }.production-shell { grid-template-columns:64px minmax(0,1fr); }.workspace-grid.immersive,.workspace-grid.immersive.with-ai-dock { grid-template-columns:156px minmax(0,1fr); }.production-tabs__summary { display:none; } }
@media (max-width:680px) { .teacher-production { height:auto; min-height:100vh; overflow:auto; }.product-bar { grid-template-columns:64px minmax(0,1fr) auto; }.brand strong,.product-bar nav button:first-child,.product-bar nav svg,.product-actions button:first-child { display:none; }.product-bar nav { padding:0 10px; }.production-shell { height:auto; min-height:calc(100vh - 52px); display:block; }.production-main { min-height:calc(100vh - 52px); }.production-tabs { overflow-x:auto; padding:6px 10px; }.segmented-tabs { flex:0 0 auto; }.segmented-tabs button span { display:none; }.workspace-grid.immersive,.workspace-grid.immersive.with-ai-dock { display:block; }.lesson-rail { max-height:none; border-right:0; border-bottom:1px solid var(--lz-border); }.lesson-list { grid-template-columns:repeat(2,minmax(0,1fr)); }.stage-workspace { min-height:420px; }.workspace-grid.immersive.with-ai-dock .ai-dock { position:fixed; z-index:20; top:98px; right:0; bottom:0; width:min(316px,100vw); max-height:none; border-top:1px solid var(--lz-border); border-left:1px solid var(--lz-border); box-shadow:-12px 0 28px rgb(15 23 42 / 13%); }.course-status > span { display:none; }.brief-grid { grid-template-columns:1fr; }.brief-grid > div { padding:12px 0 !important; border-right:0 !important; }.ppt-entry,.release-summary { grid-template-columns:34px minmax(0,1fr); }.ppt-entry button,.release-summary button { grid-column:1/-1; justify-content:center; } }
</style>
