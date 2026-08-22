<template>
  <section class="learning-view" :class="{ 'focus-mode': courseStore.isFocusMode, 'has-mobile-resume': showMobileResumePrompt, 'is-generation-preview': isGenerationPreview, 'has-ai-course-growth': hasAppliedCourseGrowth, 'is-teacher-preview': isTeacherPreview }">
    <div v-if="overlayVisible" class="surface-backdrop" @click="closeMobileSurfaces"></div>

    <Transition name="slide-left">
      <CourseNavigator
        v-if="navigatorVisible"
        class="navigator-surface"
        :active-block-id="activeCourseBlockId"
        :production-mode="isGenerationPreview"
        :generation-task="generationTask"
        @select="selectNode"
        @select-block="selectCourseBlock"
        @back="leaveTeacherPreview"
        @close="navigatorOpen = false"
      />
    </Transition>

    <main class="learning-main glass-panel-elevated">
      <div v-if="isTeacherPreview" class="teacher-preview-bar" role="status">
        <span class="teacher-preview-copy">
          <Eye :size="15" />
          <strong>{{ t('learningShell.teacherPreviewTitle', '学生视角预览') }}</strong>
          <span class="teacher-preview-help">{{ t('learningShell.teacherPreviewHelp', '内容、练习、笔记与学生端一致；体验记录不写入学生数据。') }}</span>
        </span>
        <button type="button" @click="leaveTeacherPreview"><ArrowLeft :size="15" />{{ t('learningShell.backToCourseFiles', '返回课程文件') }}</button>
      </div>
      <div
        class="learning-context-bar"
        :class="{ 'is-generation': isGenerationPreview }"
      >
        <div class="context-leading">
          <button v-if="!navigatorVisible && canOpenNavigator" type="button" :title="t('learningShell.openNavigator', '打开课程目录')" :aria-label="t('learningShell.openNavigator', '打开课程目录')" @click="navigatorOpen = true">
            <PanelLeftOpen :size="17" />
          </button>
          <div class="context-copy">
            <span>{{ currentParentLabel }}</span>
            <strong>{{ courseStore.currentNode?.node_name || t('learningShell.selectNode', '选择一个学习目标') }}</strong>
          </div>
        </div>
        <div class="context-actions">
          <div v-if="hasAppliedCourseGrowth" class="ai-course-version" role="status">
            <Sparkles :size="14" />
            <span>
              <small>{{ t('courseEvolution.applicationVisual.courseEyebrow', 'AI 个体化课程') }}</small>
              <strong>{{ t('courseEvolution.applicationVisual.newVersion', '新版本已应用') }}</strong>
            </span>
          </div>
          <button v-if="isGenerationPreview && !autoFollowGeneration" type="button" :title="t('courseGeneration.workspace.follow', '跟随当前生成章节')" :aria-label="t('courseGeneration.workspace.follow', '跟随当前生成章节')" @click="resumeGenerationFollow">
            <LocateFixed :size="17" />
          </button>
          <button v-if="!aiVisible && !isGenerationPreview" type="button" :title="t('learningShell.openAi', '打开 AI 老师')" :aria-label="t('learningShell.openAi', '打开 AI 老师')" @click="openAi()">
            <MessageSquareText :size="17" />
          </button>
        </div>
      </div>

      <AITeacherSuggestion
        :suggestion="aiTeacherStore.suggestion"
        @shown="aiTeacherStore.markSuggestionShown"
        @accept="acceptSuggestion"
        @decline="declineSuggestion"
      />
      <ContentArea
        ref="contentAreaRef"
        :side-ai-panel-visible="aiVisible"
        class="learning-content"
        @quote-ask="openAi"
        @start-practice="openTask"
        @improve-block="openBlockImprovement"
        @active-block-change="handleActiveBlockChange"
      />

      <LearningDock
        v-if="!isGenerationPreview"
        :location="dockLocation"
        :note-count="noteCount"
        :question-count="questionCount"
        :resume-action-label="resumeActionLabel"
        :resume-action-available="resumableAction?.availability === 'available'"
        :resume-action-busy="continuityBusy"
        :active-domain="activeDomain"
        @notebook="openNotebook"
        @question-book="openQuestionBook"
        @stats="openStats"
        @knowledge-library="openKnowledgeLibrary"
        @ai="openAi()"
        @resume="runResumeAction"
      />

      <LearningTaskOverlay
        v-if="taskOpen && courseStore.currentCourseId && !isGenerationPreview"
        :course-id="courseStore.currentCourseId"
        :node-id="taskNode?.node_id"
        :node-label="taskNode?.node_name"
        :origin-rect="taskOriginRect"
        :record-count="questionCount"
        @close="closeTask"
        @ask-teacher="openAiForPractice"
        @graded="refreshAfterGrade"
      />

      <Teleport to="body">
        <Transition name="learning-modal">
          <section
            v-if="notebookOpen && isNarrow"
            class="learning-tool-modal notebook-overlay"
            role="dialog"
            aria-modal="true"
            :aria-label="t('notebook.title', '笔记本')"
            @keydown.esc="closeNotebook"
          >
            <button
              type="button"
              class="learning-tool-modal__backdrop"
              :aria-label="t('common.close', '关闭')"
              @click="closeNotebook"
            ></button>
            <div class="learning-tool-modal__card is-notebook">
              <NotesPanel class="notebook-tool" @locate="locateRecord" @view-detail="locateRecord" @close="closeNotebook" />
            </div>
          </section>
        </Transition>
      </Teleport>

      <section v-if="statsOpen" class="learning-tool-overlay stats-overlay" role="dialog" aria-modal="true" :aria-label="t('learningDock.stats', '学习概况')">
        <LearningStats class="stats-tool" closable @close="closeStats" />
      </section>

    </main>

    <Transition name="slide-right">
      <aside v-if="notebookOpen && !isNarrow" class="notebook-side-panel" :aria-label="t('notebook.title', '笔记本')">
        <NotesPanel mode="sidebar" @locate="locateRecord" @view-detail="locateRecord" @close="closeNotebook" />
      </aside>
    </Transition>

    <Transition name="slide-right">
      <SideAIPanel
        v-if="aiVisible && !courseStore.isFocusMode && !isGenerationPreview"
        :visible="aiVisible"
        :quote-text="aiQuote"
        :quote-node-id="aiNodeId"
        :quote-anchor="aiAnchor"
        :prefill="aiPrefill"
        :entrypoint="aiEntrypoint"
        :block-target="aiBlockTarget"
        @close="closeAi"
        @clear-block-target="clearBlockImprovement"
        @block-applied="handleBlockApplied"
        @course-applied="handleCourseGrowthApplied"
        @open-course-adjustment="openCourseAdjustment"
      />
    </Transition>

    <CourseEvolutionWorkspace
      v-model="courseAdjustmentOpen"
      :course-id="courseStore.currentCourseId"
      :course-title="courseStore.currentCourse?.course_name || ''"
      :section-id="courseAdjustmentSectionId"
      :section-title="courseAdjustmentSectionTitle"
      :focus-plan-id="courseAdjustmentFocusPlanId"
      @course-applied="handleCourseGrowthApplied"
    />

    <button v-if="showMobileResumePrompt && resumableAction && !isGenerationPreview" type="button" class="mobile-resume-prompt" :disabled="continuityBusy || resumableAction.availability !== 'available'" @click="runResumeAction">
      <LoaderCircle v-if="continuityBusy" :size="15" class="mobile-resume-prompt__spin" />
      <History v-else :size="15" />
      <span>{{ resumeActionLabel }}</span>
    </button>

  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, Eye, History, LoaderCircle, LocateFixed, MessageSquareText, PanelLeftOpen, Sparkles } from 'lucide-vue-next'
import ContentArea from '../components/ContentArea.vue'
import CourseEvolutionWorkspace from '../components/CourseEvolutionWorkspace.vue'
import CourseNavigator from '../components/CourseNavigator.vue'
import LearningDock from '../components/LearningDock.vue'
import LearningStats from '../components/LearningStats.vue'
import LearningTaskOverlay from '../components/LearningTaskOverlay.vue'
import NotesPanel from '../components/NotesPanel.vue'
import SideAIPanel from '../components/SideAIPanel.vue'
import AITeacherSuggestion from '../components/AITeacherSuggestion.vue'
import { useAITeacherStore, type AISuggestion } from '../stores/aiTeacher'
import { useChangeProposalsStore } from '../stores/changeProposals'
import { useCourseStore } from '../stores/course'
import { useCourseWorkspaceStore } from '../stores/courseWorkspace'
import { useGenerationStore } from '../stores/generation'
import { useLearningProgressStore, type NextLearningAction } from '../stores/learningProgress'
import { useNoteStore } from '../stores/notes'
import {
  useCourseEvolutionStore,
  type CourseEvolutionApplicationPresentation,
} from '../stores/courseEvolution'
import type { CourseBlockEditTarget, CourseBlockNavigationTarget, Node } from '../stores/types'
import { isWorkspaceTaskAction, learningActionLabel } from '../utils/learning-action'
import { isStartableLearningObjective } from '../utils/learning-scope'
import { isResumableLearningAction } from '../utils/learning-resume'
import { t } from '../shared/i18n'

const route = useRoute()
const router = useRouter()
const courseStore = useCourseStore()
const noteStore = useNoteStore()
const generationStore = useGenerationStore()
const workspaceStore = useCourseWorkspaceStore()
const learningProgressStore = useLearningProgressStore()
const aiTeacherStore = useAITeacherStore()
const changeProposalsStore = useChangeProposalsStore()
const courseEvolutionStore = useCourseEvolutionStore()
const contentAreaRef = ref<InstanceType<typeof ContentArea> | null>(null)

const windowWidth = ref(window.innerWidth)
const navigatorOpen = ref(window.innerWidth >= 1024)
const aiVisible = ref(false)
const notebookOpen = ref(false)
const statsOpen = ref(false)
const taskOpen = ref(false)
const courseAdjustmentOpen = ref(false)
const courseAdjustmentFocusPlanId = ref('')
const courseAdjustmentSectionId = ref('')
const taskNode = ref<Node | null>(null)
const taskReturnScroll = ref(0)
const taskOriginRect = ref<{ top: number; left: number; width: number; height: number } | null>(null)
const taskReturnElement = ref<HTMLElement | null>(null)
const continuityBusy = ref(false)
const aiQuote = ref('')
const aiNodeId = ref('')
const aiAnchor = ref<Record<string, unknown> | undefined>(undefined)
const aiPrefill = ref('')
const aiEntrypoint = ref<'global' | 'selection' | 'practice' | 'continuity' | 'record'>('global')
const aiBlockTarget = ref<CourseBlockEditTarget | undefined>(undefined)
const autoFollowGeneration = ref(true)
const practiceApiNodeId = ref('')
let practiceAvailabilityRequest = 0
const loadedLearningCourseId = ref('')
const activeDomain = ref<'course' | 'notebook' | 'question-book' | 'overview' | 'knowledge-library' | 'assistant'>('course')
const activeCourseBlockId = ref('')
let courseGrowthLocationTimer: ReturnType<typeof setTimeout> | undefined
let courseGrowthSettleTimer: ReturnType<typeof setTimeout> | undefined

const isNarrow = computed(() => windowWidth.value < 1024)
const isTeacherPreview = computed(() => String(route.query.teacherPreview || '') === '1')
const isGenerationPreview = computed(() => courseStore.currentCourseProjection === 'generation_preview')
const generationTask = computed(() => courseStore.currentCourseId ? generationStore.tasks.get(courseStore.currentCourseId) : undefined)
const activeGenerationNodeId = computed(() => generationTask.value?.currentNodes?.[0]?.node_id || generationStore.currentGeneratingNodeId || '')
const navigatorVisible = computed(() => (
  !courseStore.isFocusMode
  && navigatorOpen.value
  && (!isGenerationPreview.value || courseStore.courseTree.length > 0)
))
const courseAdjustmentSectionTitle = computed(() => (
  courseStore.nodes.find(node => node.node_id === courseAdjustmentSectionId.value)?.node_name || ''
))
const canOpenNavigator = computed(() => (
  !isGenerationPreview.value || courseStore.courseTree.length > 0
))
const hasAppliedCourseGrowth = computed(() => (
  courseEvolutionStore.courseId === courseStore.currentCourseId
  && courseEvolutionStore.appliedPlans.length > 0
))
const overlayVisible = computed(() => isNarrow.value && navigatorVisible.value && !taskOpen.value)
const noteCount = computed(() => noteStore.notes.filter(item => item.sourceType !== 'format' && item.sourceType !== 'wrong').length)
const questionCount = computed(() => workspaceStore.assets?.assets?.questions?.length || 0)
const currentParentLabel = computed(() => {
  const current = courseStore.currentNode
  if (!current) return t('learningShell.course', '当前课程')
  const parent = courseStore.nodes.find(node => node.node_id === current.parent_node_id)
  return parent?.node_name || courseStore.currentCourse?.course_name || t('learningShell.course', '当前课程')
})
const dockLocation = computed(() => {
  const current = courseStore.currentNode?.node_name || t('learningShell.selectNode', '选择一个学习目标')
  return `${currentParentLabel.value} · ${current}`
})
const currentPracticeNode = computed(() => {
  if (isGenerationPreview.value) return null
  let candidate = courseStore.currentNode
  if (!candidate) return null
  const questions = workspaceStore.assets?.assets?.questions || []
  const questionNodeIds = new Set(
    questions
      .map(question => String(question.node_id || ''))
      .filter(Boolean),
  )
  const visitedNodeIds = new Set<string>()
  while (candidate && !visitedNodeIds.has(candidate.node_id)) {
    if (
      questionNodeIds.has(candidate.node_id)
      || practiceApiNodeId.value === candidate.node_id
    ) return candidate
    visitedNodeIds.add(candidate.node_id)
    candidate = courseStore.nodes.find(node => node.node_id === candidate?.parent_node_id) || null
  }
  return null
})
const continuationAction = computed(() => learningProgressStore.continuation?.primary_action || null)
const resumableAction = computed(() => isResumableLearningAction(continuationAction.value) ? continuationAction.value : null)
const resumeActionLabel = computed(() => resumableAction.value ? learningActionLabel(resumableAction.value.action_type) : '')
const showMobileResumePrompt = computed(() => Boolean(
  resumableAction.value
  && !navigatorOpen.value
  && !notebookOpen.value
  && !statsOpen.value
  && !taskOpen.value
  && !aiVisible.value
  && !courseStore.isFocusMode
  && !isGenerationPreview.value,
))

watch(
  () => [
    courseStore.currentCourseId,
    courseStore.currentNode?.node_id,
    workspaceStore.assets?.bundle_revision_id,
    workspaceStore.assets?.assets?.questions?.length,
  ],
  () => { void refreshCurrentPracticeAvailability() },
  { immediate: true },
)

watch(() => route.params.courseId, async value => {
  if (!value) return
  const courseId = String(value)
  loadedLearningCourseId.value = loadedLearningCourseId.value === courseId ? loadedLearningCourseId.value : ''
  autoFollowGeneration.value = true
  activeCourseBlockId.value = ''
  aiVisible.value = false
  courseAdjustmentOpen.value = false
  courseAdjustmentFocusPlanId.value = ''
  courseAdjustmentSectionId.value = ''
  activeDomain.value = 'course'
  notebookOpen.value = false
  statsOpen.value = false
  taskOpen.value = false
  workspaceStore.mistakeBookAttempts = []
  workspaceStore.practiceNeedsReviewCount = 0
  await Promise.all([
    courseStore.fetchCourseList(),
    courseStore.loadCourse(courseId),
  ])
  generationStore.observeCourse(courseId)
  if (isGenerationPreview.value) {
    selectInitialNode()
    return
  }
  await loadPublishedLearningContext(courseId)
  selectInitialNode()
  if (['practice', 'question-book'].includes(String(route.query.workspace || ''))) {
    await nextTick()
    openQuestionBook()
  }
}, { immediate: true })

watch(() => courseStore.showKnowledgeLibrary, visible => {
  if (visible) activeDomain.value = 'knowledge-library'
  else if (activeDomain.value === 'knowledge-library') activeDomain.value = 'course'
})

async function loadPublishedLearningContext(courseId: string) {
  if (courseStore.currentCourseProjection !== 'published' || loadedLearningCourseId.value === courseId) return
  await Promise.all([
    workspaceStore.loadAssets(courseId),
    noteStore.loadCourseRecords(courseId),
    learningProgressStore.load(courseId, String(route.params.nodeId || '') || undefined),
    aiTeacherStore.load(courseId, String(route.params.nodeId || '') || undefined),
  ])
  await Promise.all([
    workspaceStore.migrateLegacyPracticeData(courseId, courseStore.nodes.map(node => node.node_id)).catch(() => undefined),
    workspaceStore.loadMistakeBook(courseId).catch(() => undefined),
  ])
  loadedLearningCourseId.value = courseId
  void changeProposalsStore.fetchChangeProposals(courseId)
  // Natural pause #3: arriving at the course, before any reading has started.
  void aiTeacherStore.checkSuggestion('course_entered', String(route.params.nodeId || '') || undefined)
}

watch(() => courseStore.currentCourseProjection, async (projection, previous) => {
  if (projection !== 'published' || previous !== 'generation_preview' || !courseStore.currentCourseId) return
  autoFollowGeneration.value = false
  await loadPublishedLearningContext(courseStore.currentCourseId)
  selectInitialNode()
})

watch(activeGenerationNodeId, nodeId => {
  if (!nodeId || !isGenerationPreview.value || !autoFollowGeneration.value) return
  const node = courseStore.nodes.find(item => item.node_id === nodeId)
  if (node) selectNode(node, false, false)
})

watch(() => route.params.nodeId, value => {
  if (!value || String(value) === courseStore.currentNode?.node_id) return
  const node = courseStore.nodes.find(item => item.node_id === String(value))
  if (node) selectNode(node, false, false)
})

watch(() => courseStore.currentNode, async node => {
  if (!node || !courseStore.currentCourseId || isGenerationPreview.value) return
  if (isStartableLearningObjective(node)) {
    await learningProgressStore.startNode(courseStore.currentCourseId, node.node_id)
      .catch(() => learningProgressStore.loadRuntime(courseStore.currentCourseId, node.node_id))
  } else {
    await learningProgressStore.loadRuntime(courseStore.currentCourseId, node.node_id)
  }
})

async function refreshCurrentPracticeAvailability() {
  const request = ++practiceAvailabilityRequest
  practiceApiNodeId.value = ''
  if (
    isGenerationPreview.value
    || !courseStore.currentCourseId
    || !courseStore.currentNode
  ) return

  const questionNodeIds = new Set(
    (workspaceStore.assets?.assets?.questions || [])
      .map(question => String(question.node_id || ''))
      .filter(Boolean),
  )
  const candidates: Node[] = []
  const visitedNodeIds = new Set<string>()
  let candidate: Node | null = courseStore.currentNode
  while (candidate && !visitedNodeIds.has(candidate.node_id)) {
    if (questionNodeIds.has(candidate.node_id)) return
    candidates.push(candidate)
    visitedNodeIds.add(candidate.node_id)
    candidate = courseStore.nodes.find(
      node => node.node_id === candidate?.parent_node_id,
    ) || null
  }

  for (const node of candidates) {
    try {
      const available = await workspaceStore.checkPracticeAvailability(
        courseStore.currentCourseId,
        node.node_id,
      )
      if (request !== practiceAvailabilityRequest) return
      if (available) {
        practiceApiNodeId.value = node.node_id
        return
      }
    } catch {
      if (request !== practiceAvailabilityRequest) return
    }
  }
}

onMounted(() => {
  generationStore.restoreGenerationState()
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  generationStore.unobserveCourse(courseStore.currentCourseId)
  if (courseGrowthLocationTimer) clearTimeout(courseGrowthLocationTimer)
  if (courseGrowthSettleTimer) clearTimeout(courseGrowthSettleTimer)
})

function handleResize() {
  const wasNarrow = windowWidth.value < 1024
  windowWidth.value = window.innerWidth
  if (windowWidth.value >= 1024) navigatorOpen.value = true
  if (windowWidth.value < 1024 && (!wasNarrow || aiVisible.value)) navigatorOpen.value = false
}

function selectInitialNode() {
  const requested = String(route.params.nodeId || '')
  if (isGenerationPreview.value) {
    const node = courseStore.nodes.find(item => item.node_id === requested)
      || courseStore.nodes.find(item => item.node_id === activeGenerationNodeId.value)
      || courseStore.currentNode
      || courseStore.nodes.find(item => item.node_level >= 2 && Boolean(item.node_content))
      || courseStore.nodes[0]
    if (node) selectNode(node, false, false)
    return
  }
  const runtimeNode = learningProgressStore.runtime?.context.node_id || ''
  const node = courseStore.nodes.find(item => item.node_id === (requested || runtimeNode))
    || courseStore.nodes.find(item => item.node_level >= 2 && Boolean(item.node_content))
    || courseStore.nodes[0]
  if (node) selectNode(node, false, false)
}

function selectNode(node: Node, updateRoute = true, manualSelection = true) {
  if (isGenerationPreview.value && manualSelection && node.node_id !== activeGenerationNodeId.value) {
    autoFollowGeneration.value = false
  }
  activeCourseBlockId.value = ''
  courseStore.selectNode(node)
  courseStore.scrollToNode(node.node_id)
  if (updateRoute) void router.replace({
    name: 'learning',
    params: { courseId: courseStore.currentCourseId, nodeId: node.node_id },
    query: isTeacherPreview.value ? route.query : undefined,
  })
  if (isNarrow.value) navigatorOpen.value = false
}

async function selectCourseBlock(target: CourseBlockNavigationTarget) {
  activeCourseBlockId.value = target.blockId
  courseStore.selectNode(target.node)
  if (String(route.params.nodeId || '') !== target.node.node_id) {
    await router.replace({
      name: 'learning',
      params: { courseId: courseStore.currentCourseId, nodeId: target.node.node_id },
      query: isTeacherPreview.value ? route.query : undefined,
    })
  }
  await nextTick()
  await contentAreaRef.value?.scrollToCourseBlock(target.node.node_id, target.blockId)
  if (isNarrow.value) navigatorOpen.value = false
}

function handleActiveBlockChange(payload: { nodeId: string; blockId: string }) {
  activeCourseBlockId.value = payload.blockId
}

function resumeGenerationFollow() {
  autoFollowGeneration.value = true
  const node = courseStore.nodes.find(item => item.node_id === activeGenerationNodeId.value)
  if (node) selectNode(node, false, false)
}

function openAi(payload?: { text: string; nodeId: string; anchor?: Record<string, unknown> }) {
  if (isGenerationPreview.value) return
  activeDomain.value = 'assistant'
  notebookOpen.value = false
  statsOpen.value = false
  courseStore.showKnowledgeLibrary = false
  aiBlockTarget.value = undefined
  aiQuote.value = payload?.text || ''
  aiNodeId.value = payload?.nodeId || courseStore.currentNode?.node_id || ''
  aiAnchor.value = payload?.anchor
  aiPrefill.value = ''
  aiEntrypoint.value = payload?.text ? 'selection' : 'global'
  aiVisible.value = true
  if (isNarrow.value) navigatorOpen.value = false
}

function openCourseAdjustment(payload?: { planId?: string; sectionId?: string }) {
  courseAdjustmentFocusPlanId.value = payload?.planId || ''
  courseAdjustmentSectionId.value = payload?.sectionId || courseStore.currentNode?.node_id || ''
  aiVisible.value = false
  activeDomain.value = 'course'
  courseAdjustmentOpen.value = true
}

/** Accepting only opens the AI panel to explain the action — it executes nothing. */
function acceptSuggestion(candidate: AISuggestion) {
  aiTeacherStore.dismissSuggestion()
  openAi({
    text: '',
    nodeId: candidate.node_id || courseStore.currentNode?.node_id || '',
  })
  aiPrefill.value = t(
    'courseWorkspace.aiTeacher.explainRuntimePrompt',
    '请解释为什么我现在应该执行这个学习动作，并说明依据：',
  )
}

/**
 * Refusals go to the server, not just to local state: the archived protocol
 * requires them to hold across a refresh and on another device, and `not_now`
 * additionally carries a 24-hour floor so evidence churn cannot revive it.
 */
async function declineSuggestion(payload: { suggestion: AISuggestion; reason: 'not_now' | 'never' }) {
  aiTeacherStore.dismissSuggestion()
  await aiTeacherStore.suppressSuggestion(payload.suggestion, payload.reason)
}

function openBlockImprovement(target: CourseBlockEditTarget) {
  activeDomain.value = 'assistant'
  aiBlockTarget.value = target
  aiQuote.value = ''
  aiNodeId.value = target.nodeId
  aiAnchor.value = {
    block_id: target.block.block_id,
    block_revision_id: target.block.internal_revision,
  }
  aiPrefill.value = ''
  aiEntrypoint.value = 'selection'
  aiVisible.value = true
  if (isNarrow.value) navigatorOpen.value = false
}

function clearBlockImprovement() {
  aiBlockTarget.value = undefined
  aiPrefill.value = ''
}

async function handleBlockApplied(target: CourseBlockEditTarget) {
  await nextTick()
  document.getElementById(`course-block-${target.block.block_id}`)?.scrollIntoView({ block: 'center' })
}

function handleCourseGrowthApplied(presentation: CourseEvolutionApplicationPresentation) {
  if (courseGrowthLocationTimer) clearTimeout(courseGrowthLocationTimer)
  if (courseGrowthSettleTimer) clearTimeout(courseGrowthSettleTimer)
  const token = courseEvolutionStore.beginApplicationVisual(presentation)
  navigatorOpen.value = true

  courseGrowthLocationTimer = setTimeout(async () => {
    if (courseEvolutionStore.applicationVisual?.token !== token) return
    const targetNode = courseStore.nodes.find(
      node => node.node_id === presentation.targetSectionId,
    )
    if (targetNode && presentation.targetBlockId) {
      await selectCourseBlock({
        node: targetNode,
        blockId: presentation.targetBlockId,
      })
    } else if (targetNode) {
      selectNode(targetNode)
    }
    if (courseEvolutionStore.applicationVisual?.token !== token) return
    await nextTick()
    await new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve())))
    if (courseEvolutionStore.applicationVisual?.token !== token) return
    courseEvolutionStore.setApplicationVisualPhase(token, 'content')
    courseGrowthSettleTimer = setTimeout(() => {
      courseEvolutionStore.setApplicationVisualPhase(token, 'settled')
    }, 2200)
  }, 980)
}

function openAiForPractice(payload: { text: string; nodeId: string }) {
  activeDomain.value = 'assistant'
  aiBlockTarget.value = undefined
  aiQuote.value = payload.text
  aiNodeId.value = payload.nodeId
  aiAnchor.value = undefined
  aiPrefill.value = t('courseWorkspace.aiTeacher.quickExplainPrompt', '请解释当前内容的核心概念。')
  aiEntrypoint.value = 'practice'
  aiVisible.value = true
}

function openNotebook() {
  activeDomain.value = 'notebook'
  notebookOpen.value = true
  statsOpen.value = false
  taskOpen.value = false
  aiVisible.value = false
  courseStore.showKnowledgeLibrary = false
  if (isNarrow.value) navigatorOpen.value = false
}

function closeNotebook() {
  notebookOpen.value = false
  activeDomain.value = 'course'
}

function openQuestionBook() {
  const source = currentPracticeNode.value || courseStore.currentNode
  if (!source) return
  activeDomain.value = 'question-book'
  notebookOpen.value = false
  statsOpen.value = false
  aiVisible.value = false
  courseStore.showKnowledgeLibrary = false
  openTask(source)
  if (isNarrow.value) navigatorOpen.value = false
}

function openKnowledgeLibrary() {
  activeDomain.value = 'knowledge-library'
  notebookOpen.value = false
  statsOpen.value = false
  taskOpen.value = false
  aiVisible.value = false
  courseStore.showKnowledgeLibrary = true
  if (isNarrow.value) navigatorOpen.value = false
}

function openStats() {
  activeDomain.value = 'overview'
  statsOpen.value = true
  notebookOpen.value = false
  taskOpen.value = false
  aiVisible.value = false
  courseStore.showKnowledgeLibrary = false
}

function closeStats() {
  statsOpen.value = false
  activeDomain.value = 'course'
}

function closeAi() {
  aiVisible.value = false
  activeDomain.value = 'course'
}

function locateRecord(record: any) {
  notebookOpen.value = false
  activeDomain.value = 'course'
  const node = courseStore.nodes.find(item => item.node_id === record.nodeId)
  if (node) selectNode(node)
  window.setTimeout(() => courseStore.scrollToNote(record.id), 160)
}

function openTask(node?: Node | null, taskRevisionId = '') {
  const source = node || courseStore.currentNode
  if (!source) return
  activeDomain.value = 'question-book'
  notebookOpen.value = false
  statsOpen.value = false
  if (taskRevisionId && courseStore.currentCourseId) {
    workspaceStore.preparePracticeTask(courseStore.currentCourseId, source.node_id, taskRevisionId)
  }
  const trigger = document.activeElement instanceof HTMLElement ? document.activeElement : null
  const sourceBlock = document.getElementById(`practice-block-${source.node_id}`)
  const openedFromSourceBlock = Boolean(sourceBlock && (trigger === sourceBlock || sourceBlock.contains(trigger)))
  const rect = openedFromSourceBlock ? sourceBlock?.getBoundingClientRect() : null
  const sourceIsVisible = Boolean(rect
    && rect.width > 0
    && rect.height > 0
    && rect.bottom > 0
    && rect.top < window.innerHeight
    && rect.right > 0
    && rect.left < window.innerWidth)
  taskNode.value = source
  taskReturnScroll.value = document.getElementById('content-scroll-container')?.scrollTop || 0
  taskReturnElement.value = trigger && trigger !== document.body ? trigger : sourceBlock
  taskOriginRect.value = sourceIsVisible && rect
    ? { top: rect.top, left: rect.left, width: rect.width, height: rect.height }
    : null
  workspaceStore.practiceScope = 'node'
  taskOpen.value = true
}

async function closeTask() {
  taskOpen.value = false
  if (!aiVisible.value) activeDomain.value = 'course'
  await refreshRuntime()
  await nextTick()
  requestAnimationFrame(() => {
    const container = document.getElementById('content-scroll-container')
    if (container) container.scrollTop = taskReturnScroll.value
    if (taskReturnElement.value?.isConnected) taskReturnElement.value.focus({ preventScroll: true })
    taskOriginRect.value = null
    taskReturnElement.value = null
  })
}

async function refreshRuntime() {
  if (courseStore.currentCourseId) await learningProgressStore.loadRuntime(courseStore.currentCourseId, taskNode.value?.node_id || courseStore.currentNode?.node_id)
}

async function refreshAfterGrade() {
  await refreshRuntime()
  if (courseStore.currentCourseId) {
    await workspaceStore.loadMistakeBook(courseStore.currentCourseId).catch(() => undefined)
  }
  // Natural pause #2: a practice attempt was just submitted and graded.
  void aiTeacherStore.checkSuggestion('practice_submitted', courseStore.currentNode?.node_id)
}

async function handleContinuationAction(action: NextLearningAction) {
  if (!courseStore.currentCourseId || continuityBusy.value) return
  continuityBusy.value = true
  try {
    if (action.action_type === 'view_chapter_result') {
      openStats()
      return
    }
    const node = courseStore.nodes.find(item => item.node_id === action.node_id) || courseStore.currentNode
    if (node) selectNode(node)
    if (action.action_type === 'complete_reading' && node) {
      await learningProgressStore.completeReading(courseStore.currentCourseId, node.node_id)
      // Natural pause #1: the learner just finished a section.
      void aiTeacherStore.checkSuggestion('section_completed', node.node_id)
    } else if (isWorkspaceTaskAction(action)) {
      workspaceStore.prepareLearningAction(action)
      openTask(node)
    } else if (action.scope === 'learning_record') {
      openNotebook()
    }
  } finally {
    continuityBusy.value = false
  }
}

function runResumeAction() {
  if (resumableAction.value) void handleContinuationAction(resumableAction.value)
}

function leaveTeacherPreview() {
  if (!isTeacherPreview.value) {
    void router.push('/courses')
    return
  }
  const returnTo = String(route.query.returnTo || '')
  if (isTeacherPreview.value && returnTo.startsWith('/') && !returnTo.startsWith('//')) {
    void router.push(returnTo)
    return
  }
  void router.push({
    name: 'course-workspace',
    params: { courseId: courseStore.currentCourseId || route.params.courseId, mode: 'setup' },
    query: { section: 'basic' },
  })
}

function closeMobileSurfaces() {
  if (isNarrow.value) { navigatorOpen.value = false; aiVisible.value = false }
  notebookOpen.value = false
  statsOpen.value = false
}
</script>

<style scoped>
.learning-view { position: relative; width: 100%; height: 100%; min-width: 0; min-height: 0; display: flex; gap: 12px; overflow: hidden; background: transparent; }
.navigator-surface { flex: 0 0 292px; }
.learning-main { position: relative; min-width: 0; min-height: 0; flex: 1; display: flex; flex-direction: column; overflow: hidden; container-type: inline-size; border: 1px solid rgba(255,255,255,.82); border-radius: var(--lz-radius-surface); background: #fff; box-shadow: var(--lz-shadow-panel); backdrop-filter:none; -webkit-backdrop-filter:none; }
.teacher-preview-bar{min-height:38px;flex:0 0 auto;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:0 12px;border-bottom:1px solid var(--lz-brand-border);color:var(--lz-brand-strong);background:var(--lz-brand-soft);font-size:10px}.teacher-preview-copy,.teacher-preview-bar button{display:flex;align-items:center;gap:6px}.teacher-preview-copy{min-width:0}.teacher-preview-help{min-width:0}.teacher-preview-bar button{height:28px;flex:0 0 auto;padding:0 9px;border:1px solid var(--lz-brand-border);border-radius:7px;color:var(--lz-brand-strong);background:var(--lz-surface);cursor:pointer;white-space:nowrap}
.learning-context-bar { min-height:58px; flex:0 0 auto; display:grid; grid-template-columns:minmax(180px,1fr) auto; align-items:center; gap:12px; padding:7px 12px; border-bottom:1px solid var(--lz-border); background:rgba(255,255,255,.94); }
.has-ai-course-growth .learning-main { border-color:rgba(165,180,252,.7); box-shadow:0 16px 42px rgba(30,64,175,.1),0 2px 8px rgba(15,23,42,.05); }
.has-ai-course-growth .learning-context-bar:not(.is-generation) { position:relative; border-bottom-color:rgba(191,219,254,.9); background:linear-gradient(90deg,rgba(248,250,255,.98),rgba(240,249,255,.96) 58%,rgba(248,250,252,.98)); }
.has-ai-course-growth .learning-context-bar:not(.is-generation)::after { content:""; position:absolute; right:0; bottom:-1px; left:0; height:2px; background:linear-gradient(90deg,#4f46e5 0 24%,#0891b2 62%,rgba(14,165,233,0)); opacity:.72; }
.learning-context-bar.is-generation { min-height:52px; background:rgba(255,255,255,.96); }
.learning-context-bar.is-generation { grid-template-columns:minmax(0,1fr) auto; }
.learning-context-bar.is-generation .context-copy span { font-size:11px; line-height:1.35; }
.learning-context-bar.is-generation .context-copy strong { margin-top:2px; font-size:14px; line-height:1.4; }
.context-leading { min-width:0; display:flex; align-items:center; gap:9px; }
.context-leading > button,.context-actions > button { width:32px; height:32px; flex:0 0 32px; display:grid; place-items:center; border:0; border-radius:6px; color:var(--lz-text-secondary); background:transparent; cursor:pointer; }
.context-leading > button:hover,.context-actions > button:hover { color:var(--lz-brand-strong); background:var(--lz-brand-soft); }
.context-copy { min-width:0; flex:1; display:flex; flex-direction:column; }
.context-copy span { color:var(--lz-text-muted); font-size:9px; }
.context-copy strong { margin-top:1px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:var(--lz-text-strong); font-size:12px; }
.context-actions { min-width:0; justify-self:end; display:flex; align-items:center; gap:7px; }
.ai-course-version { min-width:0; display:flex; align-items:center; gap:7px; padding:5px 8px; border:1px solid rgba(165,180,252,.72); border-radius:9px; color:#4338ca; background:rgba(255,255,255,.86); box-shadow:0 5px 14px rgba(79,70,229,.08); }
.ai-course-version > svg { flex:0 0 auto; color:#0891b2; }
.ai-course-version > span { min-width:0; display:flex; flex-direction:column; line-height:1.12; }
.ai-course-version small { color:#64748b; font-size:8px; font-weight:700; white-space:nowrap; }
.ai-course-version strong { color:#312e81; font-size:10px; font-weight:800; white-space:nowrap; }
.learning-content { min-height: 0; flex: 1; }
.notebook-side-panel { width:clamp(340px,28vw,410px); min-width:0; min-height:0; flex:0 0 clamp(340px,28vw,410px); overflow:hidden; border:1px solid rgba(255,255,255,.82); border-radius:var(--lz-radius-surface); background:#fff; box-shadow:var(--lz-shadow-panel); }
.notebook-side-panel :deep(.records-panel) { height:100%; min-height:0; }
.learning-tool-overlay { position:absolute; inset:0; z-index:34; min-width:0; min-height:0; display:flex; flex-direction:column; background:#fff; box-shadow:var(--lz-shadow-overlay); }
.learning-tool-modal { position:fixed; inset:0; z-index:1000; display:grid; place-items:center; padding:24px; }
.learning-tool-modal__backdrop { position:absolute; inset:0; width:100%; height:100%; padding:0; border:0; border-radius:0; background:rgba(15,23,42,.42); backdrop-filter:blur(4px); -webkit-backdrop-filter:blur(4px); cursor:default; }
.learning-tool-modal__card { position:relative; z-index:1; width:min(768px,calc(100vw - 32px)); max-height:min(85vh,720px); overflow:hidden; border:1px solid rgba(255,255,255,.84); border-radius:20px; background:#fff; box-shadow:0 30px 80px rgba(15,23,42,.28),0 8px 28px rgba(79,70,229,.12); }
.learning-tool-modal__card.is-mistake-book { width:min(700px,calc(100vw - 32px)); }
.notebook-tool,.learning-tool-modal__card.is-mistake-book > * { min-width:0; min-height:0; }
.learning-modal-enter-active,.learning-modal-leave-active { transition:opacity .22s ease; }
.learning-modal-enter-active .learning-tool-modal__card,.learning-modal-leave-active .learning-tool-modal__card { transition:transform .24s cubic-bezier(.2,.8,.2,1),opacity .2s ease; }
.learning-modal-enter-from,.learning-modal-leave-to { opacity:0; }
.learning-modal-enter-from .learning-tool-modal__card,.learning-modal-leave-to .learning-tool-modal__card { opacity:0; transform:translateY(10px) scale(.96); }
.stats-tool { flex:1; min-width:0; min-height:0; }
.surface-backdrop { display: none; }
.focus-mode .learning-main { max-width: 1040px; margin: 0 auto; }
.focus-mode :deep(.learning-context-bar) { display: none; }
.slide-left-enter-active, .slide-left-leave-active, .slide-right-enter-active, .slide-right-leave-active { transition: transform .2s ease, opacity .2s ease; }
.slide-left-enter-from, .slide-left-leave-to { transform: translateX(-100%); opacity: 0; }
.slide-right-enter-from, .slide-right-leave-to { transform: translateX(100%); opacity: 0; }
@media (max-width:1279px) {
  .learning-context-bar { grid-template-columns:minmax(120px,1fr) auto; }
  .ai-course-version small { display:none; }
  .learning-view :deep(.ai-teacher-panel.is-overlay) { inset:0; padding:80px 12px 12px; }
}
@media (max-width: 1023px) {
  .learning-view { gap: 0; }
  .navigator-surface { position: fixed; left: 12px; top: 80px; bottom: 12px; z-index: 101; width: min(82vw, 300px); height: auto; box-shadow: var(--lz-shadow-overlay); }
  .surface-backdrop { position: fixed; inset: 0; z-index: 100; display: block; background: rgba(49, 46, 129, .18); backdrop-filter: blur(2px); }
  .notebook-side-panel { display:none; }
}
@media (max-width: 767px) {
  .learning-view { padding-bottom:calc(58px + env(safe-area-inset-bottom, 0px)); }
  .learning-view.has-mobile-resume { padding-bottom:calc(102px + env(safe-area-inset-bottom, 0px)); }
  .navigator-surface { left:0; top:96px; bottom:calc(58px + env(safe-area-inset-bottom, 0px)); border-radius:0 16px 0 0; }
  .learning-main { border: 0; border-radius: 0; box-shadow: none; }
  .teacher-preview-bar { align-items:flex-start; gap:8px; padding:7px 8px; }
  .teacher-preview-copy { display:grid; grid-template-columns:15px minmax(0,1fr); align-items:center; gap:2px 5px; line-height:1.3; }
  .teacher-preview-help { grid-column:2; }
  .teacher-preview-bar button { height:26px; padding:0 7px; }
  .learning-context-bar { min-height:52px; grid-template-columns:minmax(0,1fr) auto; gap:6px; padding:5px 7px; }
  .context-copy { display:none; }
  .learning-context-bar.is-generation .context-copy { display:flex; }
  .ai-course-version { padding:6px; }
  .ai-course-version > span { display:none; }
  .learning-view :deep(.ai-teacher-panel.is-overlay) { padding:96px 0 calc(58px + env(safe-area-inset-bottom, 0px)); }
  .learning-tool-overlay { position:fixed; inset:96px 0 calc(58px + env(safe-area-inset-bottom, 0px)); z-index:105; }
  .learning-tool-modal { padding:10px; }
  .learning-tool-modal__card,.learning-tool-modal__card.is-mistake-book { width:calc(100vw - 20px); max-height:calc(100dvh - 20px); border-radius:18px; }
  .is-generation-preview { padding-bottom:0; }
  .mobile-resume-prompt { position:fixed; left:10px; right:10px; bottom:calc(64px + env(safe-area-inset-bottom, 0px)); z-index:119; min-height:38px; display:flex; align-items:center; justify-content:center; gap:7px; border:1px solid #15803d; border-radius:11px; color:#fff; background:#15803d; box-shadow:0 8px 22px rgba(21,128,61,.2); font-size:12px; font-weight:750; }
  .mobile-resume-prompt:disabled { opacity:.6; }
  .mobile-resume-prompt__spin { animation:mobile-resume-spin .8s linear infinite; }
}
@media (min-width:768px) { .mobile-resume-prompt { display:none; } }
@keyframes mobile-resume-spin { to { transform:rotate(360deg); } }
@media (prefers-reduced-motion:reduce) {
  .learning-main,.learning-context-bar { transition:none; }
}
</style>
