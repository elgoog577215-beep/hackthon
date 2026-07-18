<template>
  <section class="learning-view" :class="{ 'focus-mode': courseStore.isFocusMode, 'has-mobile-resume': showMobileResumePrompt }">
    <div v-if="overlayVisible" class="surface-backdrop" @click="closeMobileSurfaces"></div>

    <Transition name="slide-left">
      <CourseNavigator
        v-if="navigatorVisible"
        class="navigator-surface"
        @select="selectNode"
        @back="router.push('/courses')"
        @close="navigatorOpen = false"
      />
    </Transition>

    <main class="learning-main glass-panel-elevated">
      <div class="learning-context-bar" :class="{ 'is-generation': isGenerationPreview }">
        <button v-if="!navigatorVisible" type="button" :title="t('learningShell.openNavigator', '打开课程目录')" :aria-label="t('learningShell.openNavigator', '打开课程目录')" @click="navigatorOpen = true">
          <PanelLeftOpen :size="17" />
        </button>
        <div class="context-copy">
          <span>{{ isGenerationPreview ? t('courseGeneration.workspace.live', '课程正在生成') : currentParentLabel }}</span>
          <strong>{{ isGenerationPreview ? generationStatusText : (courseStore.currentNode?.node_name || t('learningShell.selectNode', '选择一个学习目标')) }}</strong>
        </div>
        <div class="context-actions">
          <div v-if="isGenerationPreview" class="generation-meter" :aria-label="t('courseGeneration.workspace.progress', '生成进度')">
            <span>{{ generationProgress }}%</span>
            <i><b :style="{ width: `${generationProgress}%` }"></b></i>
          </div>
          <button v-if="isGenerationPreview && !autoFollowGeneration" type="button" :title="t('courseGeneration.workspace.follow', '跟随当前生成章节')" :aria-label="t('courseGeneration.workspace.follow', '跟随当前生成章节')" @click="resumeGenerationFollow">
            <LocateFixed :size="17" />
          </button>
          <button v-if="!aiVisible && !isGenerationPreview" type="button" :title="t('learningShell.openAi', '打开 AI 老师')" :aria-label="t('learningShell.openAi', '打开 AI 老师')" @click="openAi()">
            <MessageSquareText :size="17" />
          </button>
        </div>
      </div>

      <ContentArea
        ref="contentAreaRef"
        :side-ai-panel-visible="aiVisible"
        class="learning-content"
        @quote-ask="openAi"
        @start-practice="openTask"
        @improve-block="openBlockImprovement"
      />

      <LearningDock
        v-if="!isGenerationPreview"
        :location="dockLocation"
        :record-count="recordCount"
        :practice-available="Boolean(currentPracticeNode)"
        :practice-repair-available="questionBankRepairAvailable"
        :resume-action-label="resumeActionLabel"
        :resume-action-available="resumableAction?.availability === 'available'"
        :resume-action-busy="continuityBusy"
        :active-domain="activeDomain"
        @practice="openCurrentPractice"
        @records="openRecords"
        @stats="openStats"
        @knowledge-library="openKnowledgeLibrary"
        @teaching-resources="openTeachingResources"
        @ai="openAi()"
        @resume="runResumeAction"
      />

      <LearningTaskOverlay
        v-if="taskOpen && courseStore.currentCourseId && !isGenerationPreview"
        :course-id="courseStore.currentCourseId"
        :node-id="taskNode?.node_id"
        :node-label="taskNode?.node_name"
        :origin-rect="taskOriginRect"
        :record-count="recordCount"
        @close="closeTask"
        @ask-teacher="openAiForPractice"
        @graded="refreshRuntime"
        @records="openRecords"
        @stats="openStats"
      />

      <section v-if="recordsOpen" class="learning-tool-overlay records-overlay" role="dialog" aria-modal="true" :aria-label="t('learningNavigator.records', '学习记录')">
        <button type="button" :title="t('learningShell.closeRecords', '关闭学习记录')" :aria-label="t('learningShell.closeRecords', '关闭学习记录')" @click="recordsOpen = false"><X :size="18" /></button>
        <LearningContextTabs
          domain="learning"
          active-item="records"
          :record-count="recordCount"
          :practice-available="Boolean(currentPracticeNode)"
          :practice-repair-available="questionBankRepairAvailable"
          @practice="openCurrentPractice"
          @records="openRecords"
          @stats="openStats"
        />
        <NotesPanel class="records-tool" @locate="locateRecord" @view-detail="locateRecord" @close="recordsOpen = false" />
      </section>

      <section v-if="statsOpen" class="learning-tool-overlay stats-overlay" role="dialog" aria-modal="true" :aria-label="t('learningDock.stats', '学习概况')">
        <button type="button" :title="t('learningDock.closeStats', '关闭学习概况')" :aria-label="t('learningDock.closeStats', '关闭学习概况')" @click="statsOpen = false"><X :size="18" /></button>
        <LearningContextTabs
          domain="learning"
          active-item="stats"
          :record-count="recordCount"
          :practice-available="Boolean(currentPracticeNode)"
          :practice-repair-available="questionBankRepairAvailable"
          @practice="openCurrentPractice"
          @records="openRecords"
          @stats="openStats"
        />
        <LearningStats class="stats-tool" />
      </section>

      <TeachingRepresentationsOverlay
        :visible="resourcesOpen"
        :course-id="courseStore.currentCourseId"
        @close="resourcesOpen = false"
        @knowledge-library="openKnowledgeLibrary"
      />
    </main>

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
      />
    </Transition>

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
import { History, LoaderCircle, LocateFixed, MessageSquareText, PanelLeftOpen, X } from 'lucide-vue-next'
import ContentArea from '../components/ContentArea.vue'
import CourseNavigator from '../components/CourseNavigator.vue'
import LearningContextTabs from '../components/LearningContextTabs.vue'
import LearningDock from '../components/LearningDock.vue'
import LearningStats from '../components/LearningStats.vue'
import LearningTaskOverlay from '../components/LearningTaskOverlay.vue'
import NotesPanel from '../components/NotesPanel.vue'
import SideAIPanel from '../components/SideAIPanel.vue'
import TeachingRepresentationsOverlay from '../components/TeachingRepresentationsOverlay.vue'
import { useAITeacherStore } from '../stores/aiTeacher'
import { useChangeProposalsStore } from '../stores/changeProposals'
import { useCourseStore } from '../stores/course'
import { useCourseWorkspaceStore } from '../stores/courseWorkspace'
import { useGenerationStore } from '../stores/generation'
import { useLearningProgressStore, type NextLearningAction } from '../stores/learningProgress'
import { useNoteStore } from '../stores/notes'
import type { CourseBlockEditTarget, Node } from '../stores/types'
import { isWorkspaceTaskAction, learningActionLabel } from '../utils/learning-action'
import { isQuestionBankRepairReason } from '../utils/course-availability'
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
const contentAreaRef = ref<InstanceType<typeof ContentArea> | null>(null)

const windowWidth = ref(window.innerWidth)
const navigatorOpen = ref(window.innerWidth >= 1024)
const aiVisible = ref(false)
const recordsOpen = ref(false)
const statsOpen = ref(false)
const resourcesOpen = computed({
  get: () => courseStore.showTeachingResources,
  set: value => { courseStore.showTeachingResources = value },
})
const taskOpen = ref(false)
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
const loadedLearningCourseId = ref('')
const activeDomain = ref<'learning' | 'resources' | 'assistant'>('learning')

const isNarrow = computed(() => windowWidth.value < 1024)
const isGenerationPreview = computed(() => courseStore.currentCourseProjection === 'generation_preview')
const generationTask = computed(() => courseStore.currentCourseId ? generationStore.tasks.get(courseStore.currentCourseId) : undefined)
const generationProgress = computed(() => Math.max(0, Math.min(100, Math.round(generationTask.value?.progress || generationStore.generationProgress || 0))))
const activeGenerationNodeId = computed(() => generationTask.value?.currentNodes?.[0]?.node_id || generationStore.currentGeneratingNodeId || '')
const generationStatusText = computed(() => (
  generationTask.value?.currentStep
  || (generationTask.value?.currentPhase
    ? t(`courseGeneration.phases.${generationTask.value.currentPhase}`, generationTask.value.currentPhase)
    : '')
  || t('courseGeneration.workspace.preparing', '正在准备课程结构')
))
const navigatorVisible = computed(() => !courseStore.isFocusMode && (isNarrow.value ? navigatorOpen.value : navigatorOpen.value))
const overlayVisible = computed(() => isNarrow.value && navigatorOpen.value && !taskOpen.value)
const recordCount = computed(() => noteStore.notes.filter(item => item.sourceType !== 'format').length)
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
    if (questionNodeIds.has(candidate.node_id)) return candidate
    visitedNodeIds.add(candidate.node_id)
    candidate = courseStore.nodes.find(node => node.node_id === candidate?.parent_node_id) || null
  }
  return null
})
const questionBankRepairAvailable = computed(() => {
  if (isGenerationPreview.value || !courseStore.currentNode) return false
  const availability = workspaceStore.assets?.course_availability
  return isQuestionBankRepairReason(
    availability?.capabilities?.practice?.reason_code || availability?.reason_code,
  )
})
const continuationAction = computed(() => learningProgressStore.continuation?.primary_action || null)
const resumableAction = computed(() => isResumableLearningAction(continuationAction.value) ? continuationAction.value : null)
const resumeActionLabel = computed(() => resumableAction.value ? learningActionLabel(resumableAction.value.action_type) : '')
const showMobileResumePrompt = computed(() => Boolean(
  resumableAction.value
  && !navigatorOpen.value
  && !recordsOpen.value
  && !statsOpen.value
  && !resourcesOpen.value
  && !taskOpen.value
  && !aiVisible.value
  && !courseStore.isFocusMode
  && !isGenerationPreview.value,
))

watch(() => route.params.courseId, async value => {
  if (!value) return
  const courseId = String(value)
  loadedLearningCourseId.value = loadedLearningCourseId.value === courseId ? loadedLearningCourseId.value : ''
  autoFollowGeneration.value = true
  aiVisible.value = false
  activeDomain.value = 'learning'
  recordsOpen.value = false
  statsOpen.value = false
  resourcesOpen.value = false
  taskOpen.value = false
  await courseStore.fetchCourseList()
  await courseStore.loadCourse(courseId)
  generationStore.observeCourse(courseId)
  if (isGenerationPreview.value) {
    selectInitialNode()
    return
  }
  await loadPublishedLearningContext(courseId)
  selectInitialNode()
}, { immediate: true })

watch(() => courseStore.showTeachingResources, visible => {
  if (!visible) return
  activeDomain.value = 'resources'
})

async function loadPublishedLearningContext(courseId: string) {
  if (courseStore.currentCourseProjection !== 'published' || loadedLearningCourseId.value === courseId) return
  await workspaceStore.loadAssets(courseId)
  await noteStore.loadCourseRecords(courseId)
  await workspaceStore.migrateLegacyPracticeData(courseId, courseStore.nodes.map(node => node.node_id)).catch(() => undefined)
  await learningProgressStore.load(courseId, String(route.params.nodeId || '') || undefined)
  await aiTeacherStore.load(courseId, String(route.params.nodeId || '') || undefined)
  loadedLearningCourseId.value = courseId
  void changeProposalsStore.fetchChangeProposals(courseId)
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

onMounted(() => {
  generationStore.restoreGenerationState()
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  generationStore.unobserveCourse(courseStore.currentCourseId)
})

function handleResize() {
  windowWidth.value = window.innerWidth
  if (windowWidth.value >= 1024) navigatorOpen.value = true
  if (windowWidth.value < 1024 && aiVisible.value) navigatorOpen.value = false
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
  courseStore.selectNode(node)
  courseStore.scrollToNode(node.node_id)
  if (updateRoute) void router.replace({ name: 'learning', params: { courseId: courseStore.currentCourseId, nodeId: node.node_id } })
  if (isNarrow.value) navigatorOpen.value = false
}

function resumeGenerationFollow() {
  autoFollowGeneration.value = true
  const node = courseStore.nodes.find(item => item.node_id === activeGenerationNodeId.value)
  if (node) selectNode(node, false, false)
}

function openAi(payload?: { text: string; nodeId: string; anchor?: Record<string, unknown> }) {
  if (isGenerationPreview.value) return
  activeDomain.value = 'assistant'
  resourcesOpen.value = false
  recordsOpen.value = false
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

function openBlockImprovement(target: CourseBlockEditTarget) {
  activeDomain.value = 'assistant'
  aiBlockTarget.value = target
  aiQuote.value = ''
  aiNodeId.value = target.nodeId
  aiAnchor.value = {
    block_id: target.block.block_id,
    block_revision_id: target.block.internal_revision,
  }
  aiPrefill.value = t('courseWorkspace.blockRegeneration.defaultInstruction', '把这段内容讲得更准确、更清楚，并保持与前后文衔接。')
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

function openRecords() {
  activeDomain.value = 'learning'
  recordsOpen.value = true
  statsOpen.value = false
  taskOpen.value = false
  resourcesOpen.value = false
  if (isNarrow.value) navigatorOpen.value = false
}

function openKnowledgeLibrary() {
  activeDomain.value = 'resources'
  resourcesOpen.value = false
  courseStore.showKnowledgeLibrary = true
  if (isNarrow.value) navigatorOpen.value = false
}

function openTeachingResources() {
  activeDomain.value = 'resources'
  resourcesOpen.value = true
  recordsOpen.value = false
  statsOpen.value = false
  aiVisible.value = false
  if (isNarrow.value) navigatorOpen.value = false
}

function openCurrentPractice() {
  activeDomain.value = 'learning'
  recordsOpen.value = false
  statsOpen.value = false
  const targetNode = currentPracticeNode.value
    || (questionBankRepairAvailable.value ? courseStore.currentNode : null)
  if (targetNode) openTask(targetNode)
}

function openStats() {
  activeDomain.value = 'learning'
  statsOpen.value = true
  recordsOpen.value = false
  taskOpen.value = false
  resourcesOpen.value = false
}

function closeAi() {
  aiVisible.value = false
  activeDomain.value = 'learning'
}

function locateRecord(record: any) {
  recordsOpen.value = false
  const node = courseStore.nodes.find(item => item.node_id === record.nodeId)
  if (node) selectNode(node)
  window.setTimeout(() => courseStore.scrollToNote(record.id), 160)
}

function openTask(node?: Node | null, taskRevisionId = '') {
  const source = node || courseStore.currentNode
  if (!source) return
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
    } else if (isWorkspaceTaskAction(action)) {
      workspaceStore.prepareLearningAction(action)
      openTask(node)
    } else if (action.scope === 'learning_record') {
      openRecords()
    }
  } finally {
    continuityBusy.value = false
  }
}

function runResumeAction() {
  if (resumableAction.value) void handleContinuationAction(resumableAction.value)
}

function closeMobileSurfaces() {
  if (isNarrow.value) { navigatorOpen.value = false; aiVisible.value = false }
  recordsOpen.value = false
  statsOpen.value = false
  resourcesOpen.value = false
}
</script>

<style scoped>
.learning-view { position: relative; width: 100%; height: 100%; min-width: 0; min-height: 0; display: flex; gap: 12px; overflow: hidden; background: transparent; }
.navigator-surface { flex: 0 0 280px; }
.learning-main { position: relative; min-width: 0; min-height: 0; flex: 1; display: flex; flex-direction: column; overflow: hidden; container-type: inline-size; border: 1px solid rgba(255,255,255,.82); border-radius: var(--lz-radius-surface); background: #fff; box-shadow: var(--lz-shadow-panel); backdrop-filter:none; -webkit-backdrop-filter:none; }
.learning-context-bar { min-height: 44px; flex: 0 0 auto; display:none; align-items:center; gap:9px; padding:5px 10px; border-bottom:1px solid var(--lz-border); background:rgba(255,255,255,.72); }
.learning-context-bar.is-generation { display:flex; min-height:52px; background:rgba(255,255,255,.9); }
.learning-context-bar button { width: 32px; height: 32px; display: grid; place-items: center; border: 0; border-radius: 6px; color: var(--lz-text-secondary); background: transparent; cursor: pointer; }
.learning-context-bar button:hover { color: var(--lz-brand-strong); background: var(--lz-brand-soft); }
.context-copy { min-width:0; flex:1; display:flex; flex-direction:column; }
.context-copy span { color:var(--lz-text-muted); font-size:9px; }
.context-copy strong { margin-top:1px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:var(--lz-text-strong); font-size:12px; }
.context-actions { flex:0 0 auto; display:flex; align-items:center; gap:7px; }
.generation-meter { width:clamp(112px,16vw,220px); display:grid; grid-template-columns:auto minmax(60px,1fr); align-items:center; gap:8px; color:var(--lz-brand-strong); font-size:11px; font-weight:800; }
.generation-meter i { height:5px; overflow:hidden; border-radius:999px; background:#e8eaff; }
.generation-meter b { height:100%; display:block; border-radius:inherit; background:#6366f1; transition:width .35s ease; }
.learning-content { min-height: 0; flex: 1; }
.learning-tool-overlay { position:absolute; inset:0; z-index:34; min-width:0; min-height:0; display:flex; flex-direction:column; background:#fff; box-shadow:var(--lz-shadow-overlay); }
.records-overlay > button, .stats-overlay > button { position:absolute; top:11px; right:12px; z-index:2; width:32px; height:32px; display:grid; place-items:center; border:0; border-radius:6px; color:var(--lz-text-secondary); background:#fff; cursor:pointer; }
.records-tool { flex: 1; min-width: 0; min-height: 0; }
.stats-tool { flex:1; min-width:0; min-height:0; }
.surface-backdrop { display: none; }
.focus-mode .learning-main { max-width: 1040px; margin: 0 auto; }
.focus-mode :deep(.learning-context-bar) { display: none; }
.slide-left-enter-active, .slide-left-leave-active, .slide-right-enter-active, .slide-right-leave-active { transition: transform .2s ease, opacity .2s ease; }
.slide-left-enter-from, .slide-left-leave-to { transform: translateX(-100%); opacity: 0; }
.slide-right-enter-from, .slide-right-leave-to { transform: translateX(100%); opacity: 0; }
@media (max-width: 1279px) { .learning-context-bar { display:flex; } .learning-view :deep(.ai-teacher-panel.is-overlay) { inset: 0; padding: 80px 12px 12px; } }
@media (max-width: 1023px) {
  .learning-view { gap: 0; }
  .navigator-surface { position: fixed; left: 12px; top: 80px; bottom: 12px; z-index: 101; width: min(82vw, 300px); height: auto; box-shadow: var(--lz-shadow-overlay); }
  .surface-backdrop { position: fixed; inset: 0; z-index: 100; display: block; background: rgba(49, 46, 129, .18); backdrop-filter: blur(2px); }
}
@media (max-width: 767px) {
  .learning-view { padding-bottom:calc(58px + env(safe-area-inset-bottom, 0px)); }
  .learning-view.has-mobile-resume { padding-bottom:calc(102px + env(safe-area-inset-bottom, 0px)); }
  .navigator-surface { left:0; top:56px; bottom:calc(58px + env(safe-area-inset-bottom, 0px)); border-radius:0 16px 0 0; }
  .learning-main { border: 0; border-radius: 0; box-shadow: none; }
  .generation-meter { width:92px; grid-template-columns:auto minmax(44px,1fr); }
  .learning-view :deep(.ai-teacher-panel.is-overlay) { padding:56px 0 calc(58px + env(safe-area-inset-bottom, 0px)); }
  .learning-tool-overlay { position:fixed; inset:56px 0 calc(58px + env(safe-area-inset-bottom, 0px)); z-index:105; }
  .mobile-resume-prompt { position:fixed; left:10px; right:10px; bottom:calc(64px + env(safe-area-inset-bottom, 0px)); z-index:119; min-height:38px; display:flex; align-items:center; justify-content:center; gap:7px; border:1px solid #15803d; border-radius:11px; color:#fff; background:#15803d; box-shadow:0 8px 22px rgba(21,128,61,.2); font-size:12px; font-weight:750; }
  .mobile-resume-prompt:disabled { opacity:.6; }
  .mobile-resume-prompt__spin { animation:mobile-resume-spin .8s linear infinite; }
}
@media (min-width:768px) { .mobile-resume-prompt { display:none; } }
@keyframes mobile-resume-spin { to { transform:rotate(360deg); } }
</style>
