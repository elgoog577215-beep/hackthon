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
      <div class="learning-context-bar">
        <button v-if="!navigatorVisible" type="button" :title="t('learningShell.openNavigator', '打开课程目录')" :aria-label="t('learningShell.openNavigator', '打开课程目录')" @click="navigatorOpen = true">
          <PanelLeftOpen :size="17" />
        </button>
        <div>
          <span>{{ currentParentLabel }}</span>
          <strong>{{ courseStore.currentNode?.node_name || t('learningShell.selectNode', '选择一个学习目标') }}</strong>
        </div>
        <button v-if="!aiVisible" type="button" :title="t('learningShell.openAi', '打开 AI 老师')" :aria-label="t('learningShell.openAi', '打开 AI 老师')" @click="openAi()">
          <MessageSquareText :size="17" />
        </button>
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
        :location="dockLocation"
        :record-count="recordCount"
        :practice-available="Boolean(currentPracticeNode)"
        :resume-action-label="resumeActionLabel"
        :resume-action-available="resumableAction?.availability === 'available'"
        :resume-action-busy="continuityBusy"
        @records="openRecords"
        @practice="openCurrentPractice"
        @stats="statsOpen = true"
        @knowledge-library="openKnowledgeLibrary"
        @ai="openAi()"
        @resume="runResumeAction"
      />

      <LearningTaskOverlay
        v-if="taskOpen && courseStore.currentCourseId"
        :course-id="courseStore.currentCourseId"
        :node-id="taskNode?.node_id"
        :node-label="taskNode?.node_name"
        :origin-rect="taskOriginRect"
        @close="closeTask"
        @ask-teacher="openAiForPractice"
        @graded="refreshRuntime"
      />

      <section v-if="recordsOpen" class="records-overlay" role="dialog" aria-modal="true" :aria-label="t('learningNavigator.records', '学习记录')">
        <button type="button" :title="t('learningShell.closeRecords', '关闭学习记录')" :aria-label="t('learningShell.closeRecords', '关闭学习记录')" @click="recordsOpen = false"><X :size="18" /></button>
        <NotesPanel class="records-tool" @locate="locateRecord" @view-detail="locateRecord" @close="recordsOpen = false" />
      </section>

      <section v-if="statsOpen" class="stats-overlay" role="dialog" aria-modal="true" :aria-label="t('learningDock.stats', '学习概况')">
        <button type="button" :title="t('learningDock.closeStats', '关闭学习概况')" :aria-label="t('learningDock.closeStats', '关闭学习概况')" @click="statsOpen = false"><X :size="18" /></button>
        <LearningStats class="stats-tool" />
      </section>
    </main>

    <Transition name="slide-right">
      <SideAIPanel
        v-if="aiVisible && !courseStore.isFocusMode"
        :visible="aiVisible"
        :quote-text="aiQuote"
        :quote-node-id="aiNodeId"
        :quote-anchor="aiAnchor"
        :prefill="aiPrefill"
        :entrypoint="aiEntrypoint"
        :block-target="aiBlockTarget"
        @close="aiVisible = false"
        @clear-block-target="clearBlockImprovement"
        @block-applied="handleBlockApplied"
      />
    </Transition>

    <button v-if="showMobileResumePrompt && resumableAction" type="button" class="mobile-resume-prompt" :disabled="continuityBusy || resumableAction.availability !== 'available'" @click="runResumeAction">
      <LoaderCircle v-if="continuityBusy" :size="15" class="mobile-resume-prompt__spin" />
      <History v-else :size="15" />
      <span>{{ resumeActionLabel }}</span>
    </button>

    <nav class="mobile-learning-nav" :aria-label="t('learningShell.mobileNavigation', '学习导航')">
      <button type="button" :class="{ active: navigatorOpen }" @click="toggleMobileSurface('navigator')"><ListTree :size="17" /><span>{{ t('learningShell.navigator', '目录') }}</span></button>
      <button type="button" :disabled="!currentPracticeNode" @click="openCurrentPractice"><ClipboardCheck :size="17" /><span>{{ t('learningShell.practice', '练习') }}</span></button>
      <button type="button" :class="{ active: recordsOpen }" @click="toggleMobileSurface('records')"><NotebookTabs :size="17" /><span>{{ t('learningShell.records', '记录') }}</span></button>
      <button type="button" @click="openKnowledgeLibrary"><Library :size="17" /><span>{{ t('learningShell.knowledgeLibrary', '知识库') }}</span></button>
      <button type="button" :class="{ active: aiVisible }" @click="toggleMobileSurface('ai')"><MessageSquareText :size="17" /><span>{{ t('learningShell.ai', 'AI') }}</span></button>
    </nav>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ClipboardCheck, History, Library, ListTree, LoaderCircle, MessageSquareText, NotebookTabs, PanelLeftOpen, X } from 'lucide-vue-next'
import ContentArea from '../components/ContentArea.vue'
import CourseNavigator from '../components/CourseNavigator.vue'
import LearningDock from '../components/LearningDock.vue'
import LearningStats from '../components/LearningStats.vue'
import LearningTaskOverlay from '../components/LearningTaskOverlay.vue'
import NotesPanel from '../components/NotesPanel.vue'
import SideAIPanel from '../components/SideAIPanel.vue'
import { useAITeacherStore } from '../stores/aiTeacher'
import { useChangeProposalsStore } from '../stores/changeProposals'
import { useCourseStore } from '../stores/course'
import { useCourseWorkspaceStore } from '../stores/courseWorkspace'
import { useGenerationStore } from '../stores/generation'
import { useLearningProgressStore, type NextLearningAction } from '../stores/learningProgress'
import { useNoteStore } from '../stores/notes'
import type { CourseBlockEditTarget, Node } from '../stores/types'
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
const contentAreaRef = ref<InstanceType<typeof ContentArea> | null>(null)

const windowWidth = ref(window.innerWidth)
const navigatorOpen = ref(window.innerWidth >= 1024)
const aiVisible = ref(false)
const recordsOpen = ref(false)
const statsOpen = ref(false)
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

const isNarrow = computed(() => windowWidth.value < 1024)
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
  const current = courseStore.currentNode
  if (!current) return null
  const questions = workspaceStore.assets?.assets?.questions || []
  return questions.some(question => question.node_id === current.node_id) ? current : null
})
const continuationAction = computed(() => learningProgressStore.continuation?.primary_action || null)
const resumableAction = computed(() => isResumableLearningAction(continuationAction.value) ? continuationAction.value : null)
const resumeActionLabel = computed(() => resumableAction.value ? learningActionLabel(resumableAction.value.action_type) : '')
const showMobileResumePrompt = computed(() => Boolean(
  resumableAction.value
  && !navigatorOpen.value
  && !recordsOpen.value
  && !statsOpen.value
  && !taskOpen.value
  && !aiVisible.value
  && !courseStore.isFocusMode,
))

watch(() => route.params.courseId, async value => {
  if (!value) return
  const courseId = String(value)
  await courseStore.fetchCourseList()
  await courseStore.loadCourse(courseId)
  await workspaceStore.loadAssets(courseId)
  await noteStore.loadCourseRecords(courseId)
  await workspaceStore.migrateLegacyPracticeData(courseId, courseStore.nodes.map(node => node.node_id)).catch(() => undefined)
  await learningProgressStore.load(courseId, String(route.params.nodeId || '') || undefined)
  await aiTeacherStore.load(courseId, String(route.params.nodeId || '') || undefined)
  // 不阻塞主流程：变更提案是旁路信息，加载失败/慢不应拖慢课程进入
  void changeProposalsStore.fetchChangeProposals(courseId)
  selectInitialNode()
}, { immediate: true })

watch(() => route.params.nodeId, value => {
  if (!value || String(value) === courseStore.currentNode?.node_id) return
  const node = courseStore.nodes.find(item => item.node_id === String(value))
  if (node) selectNode(node, false)
})

watch(() => courseStore.currentNode, async node => {
  if (!node || !courseStore.currentCourseId) return
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

onUnmounted(() => window.removeEventListener('resize', handleResize))

function handleResize() {
  windowWidth.value = window.innerWidth
  if (windowWidth.value >= 1024) navigatorOpen.value = true
  if (windowWidth.value < 1024 && aiVisible.value) navigatorOpen.value = false
}

function selectInitialNode() {
  const requested = String(route.params.nodeId || '')
  const runtimeNode = learningProgressStore.runtime?.context.node_id || ''
  const node = courseStore.nodes.find(item => item.node_id === (requested || runtimeNode))
    || courseStore.nodes.find(item => item.node_level >= 2 && Boolean(item.node_content))
    || courseStore.nodes[0]
  if (node) selectNode(node, false)
}

function selectNode(node: Node, updateRoute = true) {
  courseStore.selectNode(node)
  courseStore.scrollToNode(node.node_id)
  if (updateRoute) void router.replace({ name: 'learning', params: { courseId: courseStore.currentCourseId, nodeId: node.node_id } })
  if (isNarrow.value) navigatorOpen.value = false
}

function openAi(payload?: { text: string; nodeId: string; anchor?: Record<string, unknown> }) {
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
  aiBlockTarget.value = undefined
  aiQuote.value = payload.text
  aiNodeId.value = payload.nodeId
  aiAnchor.value = undefined
  aiPrefill.value = t('courseWorkspace.aiTeacher.quickExplainPrompt', '请解释当前内容的核心概念。')
  aiEntrypoint.value = 'practice'
  aiVisible.value = true
}

function openRecords() {
  recordsOpen.value = true
  statsOpen.value = false
  if (isNarrow.value) navigatorOpen.value = false
}

function openKnowledgeLibrary() {
  courseStore.showKnowledgeLibrary = true
  if (isNarrow.value) navigatorOpen.value = false
}

function openCurrentPractice() {
  if (currentPracticeNode.value) openTask(currentPracticeNode.value)
}

function locateRecord(record: any) {
  recordsOpen.value = false
  const node = courseStore.nodes.find(item => item.node_id === record.nodeId)
  if (node) selectNode(node)
  window.setTimeout(() => courseStore.scrollToNote(record.id), 160)
}

function openTask(node?: Node | null) {
  const source = node || courseStore.currentNode
  if (!source) return
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
      statsOpen.value = true
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

function toggleMobileSurface(surface: 'navigator' | 'records' | 'ai') {
  if (surface === 'navigator') { navigatorOpen.value = !navigatorOpen.value; aiVisible.value = false; recordsOpen.value = false; statsOpen.value = false }
  if (surface === 'records') { recordsOpen.value = !recordsOpen.value; navigatorOpen.value = false; aiVisible.value = false; statsOpen.value = false }
  if (surface === 'ai') { aiVisible.value = !aiVisible.value; navigatorOpen.value = false; recordsOpen.value = false; statsOpen.value = false }
}

function closeMobileSurfaces() {
  if (isNarrow.value) { navigatorOpen.value = false; aiVisible.value = false }
  recordsOpen.value = false
  statsOpen.value = false
}
</script>

<style scoped>
.learning-view { position: relative; width: 100%; height: 100%; min-width: 0; min-height: 0; display: flex; gap: 12px; overflow: hidden; background: transparent; }
.navigator-surface { flex: 0 0 280px; }
.learning-main { position: relative; min-width: 0; min-height: 0; flex: 1; display: flex; flex-direction: column; overflow: hidden; container-type: inline-size; border: 1px solid rgba(255,255,255,.82); border-radius: var(--lz-radius-surface); background: #fff; box-shadow: var(--lz-shadow-panel); backdrop-filter:none; -webkit-backdrop-filter:none; }
.learning-context-bar { min-height: 44px; flex: 0 0 auto; display: none; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center; gap: 9px; padding: 5px 10px; border-bottom: 1px solid var(--lz-border); background: rgba(255,255,255,.72); }
.learning-context-bar button { width: 32px; height: 32px; display: grid; place-items: center; border: 0; border-radius: 6px; color: var(--lz-text-secondary); background: transparent; cursor: pointer; }
.learning-context-bar button:hover { color: var(--lz-brand-strong); background: var(--lz-brand-soft); }
.learning-context-bar div { min-width: 0; display: flex; flex-direction: column; }
.learning-context-bar span { color: var(--lz-text-muted); font-size: 9px; }
.learning-context-bar strong { margin-top: 1px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--lz-text-strong); font-size: 12px; }
.learning-content { min-height: 0; flex: 1; }
.records-overlay, .stats-overlay { position:absolute; inset:0; z-index:34; min-width:0; min-height:0; display:flex; background:#fff; box-shadow:var(--lz-shadow-overlay); }
.records-overlay > button, .stats-overlay > button { position:absolute; top:11px; right:12px; z-index:2; width:32px; height:32px; display:grid; place-items:center; border:0; border-radius:6px; color:var(--lz-text-secondary); background:#fff; cursor:pointer; }
.records-tool { flex: 1; min-width: 0; min-height: 0; }
.stats-tool { flex:1; min-width:0; min-height:0; padding-top:46px; }
.surface-backdrop { display: none; }
.mobile-learning-nav { display: none; }
.focus-mode .learning-main { max-width: 1040px; margin: 0 auto; }
.focus-mode :deep(.learning-context-bar) { display: none; }
.slide-left-enter-active, .slide-left-leave-active, .slide-right-enter-active, .slide-right-leave-active { transition: transform .2s ease, opacity .2s ease; }
.slide-left-enter-from, .slide-left-leave-to { transform: translateX(-100%); opacity: 0; }
.slide-right-enter-from, .slide-right-leave-to { transform: translateX(100%); opacity: 0; }
@media (max-width: 1279px) { .learning-context-bar { display:grid; } .learning-view :deep(.ai-teacher-panel.is-overlay) { inset: 0; padding: 80px 12px 12px; } }
@media (max-width: 1023px) {
  .learning-view { gap: 0; }
  .navigator-surface { position: fixed; left: 12px; top: 80px; bottom: 12px; z-index: 101; width: min(82vw, 300px); height: auto; box-shadow: var(--lz-shadow-overlay); }
  .surface-backdrop { position: fixed; inset: 0; z-index: 100; display: block; background: rgba(49, 46, 129, .18); backdrop-filter: blur(2px); }
}
@media (max-width: 767px) {
  .learning-view { padding-bottom:calc(52px + env(safe-area-inset-bottom, 0px)); }
  .learning-view.has-mobile-resume { padding-bottom:calc(96px + env(safe-area-inset-bottom, 0px)); }
  .navigator-surface { left:0; top:56px; bottom:calc(52px + env(safe-area-inset-bottom, 0px)); border-radius:0 16px 0 0; }
  .learning-main { border: 0; border-radius: 0; box-shadow: none; }
  .learning-view :deep(.ai-teacher-panel.is-overlay) { padding:56px 0 calc(52px + env(safe-area-inset-bottom, 0px)); }
  .records-overlay, .stats-overlay { position:fixed; inset:56px 0 calc(52px + env(safe-area-inset-bottom, 0px)); z-index:105; }
  .mobile-resume-prompt { position:fixed; left:10px; right:10px; bottom:calc(58px + env(safe-area-inset-bottom, 0px)); z-index:119; min-height:38px; display:flex; align-items:center; justify-content:center; gap:7px; border:1px solid #15803d; border-radius:11px; color:#fff; background:#15803d; box-shadow:0 8px 22px rgba(21,128,61,.2); font-size:12px; font-weight:750; }
  .mobile-resume-prompt:disabled { opacity:.6; }
  .mobile-resume-prompt__spin { animation:mobile-resume-spin .8s linear infinite; }
  .mobile-learning-nav { position: fixed; left: 0; right: 0; bottom: 0; z-index: 120; height: calc(52px + env(safe-area-inset-bottom, 0px)); display: grid; grid-template-columns: repeat(5, 1fr); padding-bottom: env(safe-area-inset-bottom, 0px); border-top: 1px solid var(--lz-border); background: #fff; }
  .mobile-learning-nav button { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 3px; border: 0; color: var(--lz-text-muted); background: transparent; font-size: 9px; }
  .mobile-learning-nav button.active { color: var(--lz-brand-strong); }
  .mobile-learning-nav button:disabled { color:#cbd5e1; }
}
@media (min-width:768px) { .mobile-resume-prompt { display:none; } }
@keyframes mobile-resume-spin { to { transform:rotate(360deg); } }
</style>
