<template>
  <section ref="learningLayoutRoot" class="learning-view" :style="columnLayoutStyle" :class="{ 'focus-mode': courseStore.isFocusMode, 'has-mobile-resume': showMobileResumePrompt, 'is-generation-preview': isGenerationPreview, 'has-ai-course-growth': hasAppliedCourseGrowth }">
  <CompanionFloatingWindow window-id="course-companion-window" :visible="aiFloating && aiVisible && !inlineCompanion && !courseStore.isFocusMode" :detail="Boolean(selectedKnowledge) && (statsOpen || courseStore.showKnowledgeLibrary)" @close="closeAi" />
    <div v-if="overlayVisible" class="surface-backdrop" @click="closeMobileSurfaces"></div>

    <Transition name="slide-left">
      <CourseNavigator
        v-if="navigatorVisible"
        class="navigator-surface"
        data-companion-obstacle
        :active-block-id="activeCourseBlockId"
        :production-mode="isGenerationPreview"
        :generation-task="generationTask"
        :back-label="isTeacherPreview ? t('courseWorkspaceFlow.returnWorkbench') : getStudyIdentity()?.role === 'student' ? t('courseWorkspaceFlow.returnStudy') : undefined"
        @select="selectNode"
        @select-block="selectCourseBlock"
        @back="leaveTeacherPreview"
        @close="navigatorOpen = false"
      />
    </Transition>

    <ColumnResizeHandle v-if="!isNarrow && navigatorVisible" v-bind="leftColumnHandle" />
    <main class="learning-main glass-panel-elevated" data-companion-obstacle>
      <div v-if="!isGenerationPreview" class="learning-plan-tools"><CompanionPlanPanel :course-id="courseStore.currentCourseId" :preview="isTeacherPreview" @visibility-change="companionSettingsOpen=$event" @navigate="navigatePlanStep" @prepare-material="target => router.push({path:'/study',query:{fromCourse:target.courseId,purpose:target.purpose}})" /><span v-if="companionPreferences.suppressionError" role="status">{{ t('companionPolicy.saveFailed') }}</span></div>
      <AITeacherSuggestion
        v-if="companionEligible"
        :suggestion="aiTeacherStore.suggestion"
        @shown="aiTeacherStore.markSuggestionShown"
        @accept="acceptSuggestion"
        @decline="declineSuggestion"
      />
      <div class="learning-stage">
        <div v-if="isExchangeCourse" class="exchange-course-notice"><span>{{ exchangeCopy('教师发布课程 · 正式作答对教师可见', 'Published course · Formal attempts are shared with your teacher') }}</span><RouterLink to="/study?view=courses">{{ exchangeCopy('课程提问与更新', 'Questions & updates') }}</RouterLink></div>
        <ContentArea
          v-show="!taskOpen && !statsOpen && !mistakesOpen && !courseStore.showKnowledgeLibrary"
          ref="contentAreaRef"
          :side-ai-panel-visible="aiVisible && !inlineCompanion"
          :teacher-preview="isTeacherPreview"
          study-dialogues
          @study-dialogue="openStudyDialogue"
          class="learning-content"
          @quote-ask="openSelectionStudy"
          @start-practice="openTask"
          @improve-block="openBlockImprovement"
          @active-block-change="handleActiveBlockChange"
          @retry-load="reloadLearningCourse"
          @return-workbench="leaveTeacherPreview"
        />

        <section v-show="courseStore.showKnowledgeLibrary" class="learning-tool-overlay knowledge-study-overlay">
          <Teleport to="#course-companion-window-detail" :disabled="!aiFloating || !aiVisible || !selectedKnowledge || !courseStore.showKnowledgeLibrary">
            <CourseKnowledgeStudy ref="knowledgeStudyRef" :visible="courseStore.showKnowledgeLibrary" :preview="isTeacherPreview" @close="closeKnowledgeLibrary" @select="selectKnowledge" @evidence="discussEvidence" @lecture="openKnowledgeLecture" @practice="openKnowledgePractice" />
          </Teleport>
        </section>
        <section v-if="mistakesOpen && courseStore.currentCourseId" class="learning-tool-overlay mistakes-overlay" role="region" :aria-label="t('studentWorkspace.mistakes')">
          <MistakeNotebookPanel :course-id="courseStore.currentCourseId" @close="activateTool('reading')" @retry="openMistakeRetry" />
        </section>
        <LearningTaskOverlay
          :embedded="!isNarrow"
          v-if="taskOpen && courseStore.currentCourseId && !isGenerationPreview"
          :course-id="courseStore.currentCourseId"
          :node-id="workspaceStore.practiceScope === 'all' ? undefined : taskNode?.node_id"
          :node-label="workspaceStore.practiceScope === 'all' ? undefined : taskNode?.node_name"
          :scope="workspaceStore.practiceScope"
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
                <NotesPanel class="notebook-tool" @locate="locateRecord" @view-detail="record => openStudyRecord(record.id)" @close="closeNotebook" />
              </div>
            </section>
          </Transition>
        </Teleport>

        <section v-if="statsOpen" class="learning-tool-overlay stats-overlay" role="region" :aria-label="t('learningDock.stats', '学习概况')">
          <LearningStats class="stats-tool" closable @close="closeStats" @open-lecture="openKnowledgeLecture" @open-knowledge="openMatrixKnowledge" @open-record="openStudyRecord" @open-practice="openMatrixPractice" />
        </section>
      </div>



      <LearningDock toolbar placement="bottom"
        v-if="!isGenerationPreview"
        :location="dockLocation"
        :notebook-open="notebookOpen"
        :navigator-hidden="!navigatorVisible"
        :note-count="noteCount"
        :question-count="questionCount"
        :resume-action-label="resumeActionLabel"
        :resume-action-available="resumableAction?.availability === 'available'"
        :resume-action-busy="continuityBusy"
        :active-domain="dockActiveDomain"
        :assistant-open="aiVisible && !courseStore.isFocusMode"
        @navigator="navigatorOpen = true"
        @notebook="openNotebook"
        @question-book="activateTool('practice')"
        @stats="activateTool('overview')"
        @knowledge-library="activateTool('knowledge')"
        @ai="toggleAi"
        @resume="runResumeAction"
        @reading="activateTool('reading')"
        @mistakes="activateTool('mistakes')"
      />
    </main>

    <ColumnResizeHandle v-if="dockedSidePanelVisible" v-bind="rightColumnHandle" />
    <Transition name="side-panel">
      <div v-show="sidePanelVisible" class="learning-side-panel" :class="{ 'is-docked': !isNarrow, 'is-companion-floating': aiFloating && !notesVisible && !notebookOpen && !isNarrow }">
        <ReadingNotesPanel v-if="!isNarrow && !isGenerationPreview" v-show="!aiVisible && !notebookOpen" :key="courseStore.currentCourseId" :visible="sidePanelVisible && !aiVisible && !notebookOpen && !taskOpen && !statsOpen" @open="openReadingNote" @create="createReadingNote" @locate="locateRecord" @notebook="openNotebook" />
        <aside id="all-notes-panel" v-show="notebookOpen && !aiVisible" v-if="!isNarrow" role="region" class="notebook-side-panel" :aria-label="t('notebook.title', '笔记本')" data-companion-obstacle>
          <NotesPanel mode="sidebar" @locate="locateRecord" @view-detail="record => openStudyRecord(record.id)" @close="closeNotebook" />
        </aside>
        <ReadingCompanionSurface ref="companionSurfaceRef" minimal bubble v-slot="{expand}" :anchor="readingCompanionAnchor" :full-target="aiFloating ? '#course-companion-window-chat' : ''" :visible="aiVisible && !courseStore.isFocusMode" @presentation-change="inlineCompanion = $event">
        <SideAIPanel
          data-companion-obstacle
          id="reading-assistant-panel" @expand-companion="expand()"
          role="region"
          :aria-label="t('companionWorkspace.title')"
          v-if="!isGenerationPreview"
          v-show="aiVisible && !courseStore.isFocusMode"
          :key="`${courseStore.currentCourseId}:${isTeacherPreview}`"
          :docked="!isNarrow"
          :embedded="inlineCompanion"
          :compact="inlineCompanion"
          :visible="aiVisible && !courseStore.isFocusMode"
          :companion-avatar="companionAvatar"
          :floating="aiFloating"
          :live-pet="!isNarrow"
          :knowledge-context="selectedKnowledge"
          @toggle-mode="aiFloating = !aiFloating"
          @clear-knowledge="selectedKnowledge = null"
          :reading-context="isNarrow ? undefined : readingContext"
          :quote-text="aiQuote"
          :quote-node-id="aiNodeId"
          :quote-anchor="aiAnchor"
          :prefill="aiPrefill"
          :study-request="studyRequest"
          @open-study-record="openStudyRecord"
          @practice="target => { closeAi(); openMatrixPractice(target.nodeId,target.taskRevisionId) }"
          :entrypoint="aiEntrypoint"
          :identity-scope="isTeacherPreview ? 'teacher' : 'learner'"
          :block-target="aiBlockTarget"
          @close="closeAi"
          @clear-block-target="clearBlockImprovement"
          @block-applied="handleBlockApplied"
          @course-applied="handleCourseGrowthApplied"
          @open-course-adjustment="openCourseAdjustment"
        />
        </ReadingCompanionSurface>
      </div>
    </Transition>

    <LearningCompanion
      v-if="!isNarrow && !isGenerationPreview"
      ref="companionRef"
      :expanded="aiVisible && !inlineCompanion"
      :modal="aiFloating && aiVisible && !inlineCompanion"
      :help-open="aiVisible && inlineCompanion"
      :help-range="companionHelpRange"
      @close-help="closeAi"
      :active="!courseStore.isFocusMode"
      :reminder="companionReminder"
      :reminders-enabled="companionPreferences.proactive"
      :welcome="companionWelcome"
      @dismiss-welcome="dismissCompanionWelcome"
      @open="toggleAi"
      @reminder="openCompanionReminder"
      @dismiss-reminder="dismissReminder($event)"
      @toggle-reminders="toggleCompanionMode"
    />

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
import { computed, nextTick, onMounted, onUnmounted, ref, shallowRef, watch } from 'vue'
import ColumnResizeHandle from '../components/ColumnResizeHandle.vue'
import { useResizableColumns } from '../composables/useResizableColumns'
import { useRoute, useRouter } from 'vue-router'
import { History, LoaderCircle } from 'lucide-vue-next'
import type { KnowledgeProfileNode } from '../types/knowledge-profile'
import CompanionFloatingWindow from '../components/CompanionFloatingWindow.vue'
import CourseKnowledgeStudy from '../components/CourseKnowledgeStudy.vue'
import ContentArea from '../components/ContentArea.vue'
import CourseEvolutionWorkspace from '../components/CourseEvolutionWorkspace.vue'
import CourseNavigator from '../components/CourseNavigator.vue'
import LearningDock from '../components/LearningDock.vue'
import MistakeNotebookPanel from '../components/MistakeNotebookPanel.vue'
import { isPublishedExchangeCourse, studentWorkspaceTool, type StudentWorkspaceTool } from '../shared/student-workspace'
import LearningCompanion from '../components/LearningCompanion.vue'
import LearningStats from '../components/LearningStats.vue'
import LearningTaskOverlay from '../components/LearningTaskOverlay.vue'
import NotesPanel from '../components/NotesPanel.vue'
import ReadingNotesPanel from '../components/ReadingNotesPanel.vue'
import SideAIPanel from '../components/SideAIPanel.vue'
import ReadingCompanionSurface from '../components/ReadingCompanionSurface.vue'
import CompanionPlanPanel from '../components/CompanionPlanPanel.vue'
import { useCompanionPreferencesStore } from '../stores/companionPreferences'
import AITeacherSuggestion from '../components/AITeacherSuggestion.vue'
import { useAITeacherStore, type AISuggestion } from '../stores/aiTeacher'
import { useChangeProposalsStore } from '../stores/changeProposals'
import { useCourseStore } from '../stores/course'
import { useCourseWorkspaceStore } from '../stores/courseWorkspace'
import { useGenerationStore } from '../stores/generation'
import { useLearningProgressStore, type NextLearningAction } from '../stores/learningProgress'
import { useLearnerModelStore } from '../stores/learnerModel'
import { useNoteStore } from '../stores/notes'
import {
  useCourseEvolutionStore,
  type CourseEvolutionApplicationPresentation,
} from '../stores/courseEvolution'
import type { CourseBlockEditTarget, CourseBlockNavigationTarget, Node, Note } from '../stores/types'
import { isWorkspaceTaskAction, learningActionLabel } from '../utils/learning-action'
import { isStartableLearningObjective } from '../utils/learning-scope'
import { isResumableLearningAction } from '../utils/learning-resume'
import { t, activeLocale } from '../shared/i18n'
import type { StudyRequest } from '../types/study-dialogue'
import { resolvePublicAssetUrl } from '../utils/publicAssetUrl'
import { useCompanionReminders, type CompanionReminder } from '../composables/useCompanionReminders'
import { useCompanionLayout } from '../composables/useCompanionLayout'
import { useCompanionWelcome } from '../composables/useCompanionWelcome'
import { getLearnerIdentity } from '../utils/http'
import { getStudyIdentity } from '../utils/study-identity'

const route = useRoute()
const isExchangeCourse = computed(() => isPublishedExchangeCourse(String(route.params.courseId || route.params.id || '')))
const exchangeCopy = (zh: string, en: string) => activeLocale.value === 'en' ? en : zh
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
const knowledgeStudyRef = ref<InstanceType<typeof CourseKnowledgeStudy> | null>(null)
const companionRef = ref<InstanceType<typeof LearningCompanion> | null>(null)
const companionHelpRange = shallowRef<Range | null>(null)
const companionAvatar = resolvePublicAssetUrl('images/learning-companion.png', import.meta.env.BASE_URL)
const companionPreferences=useCompanionPreferencesStore()
const companionSettingsOpen=ref(false)
const companionEditing=ref(false), companionPageVisible=ref(document.visibilityState!=='hidden')
function updateCompanionAttention(){companionEditing.value=Boolean(document.activeElement?.matches('input,textarea,[contenteditable="true"]'));companionPageVisible.value=document.visibilityState!=='hidden'}
async function toggleCompanionMode(){try{await companionPreferences.change(companionPreferences.proactive?'on_request':'gentle')}catch{/* Keep the last verified server setting. */}}
function navigatePlanStep(id:string){const node=courseStore.nodes.find(n=>n.node_id===id);if(node)selectNode(node)}

const windowWidth = ref(window.innerWidth)
const navigatorOpen = ref(window.innerWidth >= 1024)
const aiVisible = ref(false)
const readingCompanionAnchor = ref<HTMLElement | null>(null)
const inlineCompanion = ref(false)
const companionSurfaceRef = ref<InstanceType<typeof ReadingCompanionSurface> | null>(null)
let studyEntrySequence = 0
const aiFloating = useCompanionLayout()
const selectedKnowledge = ref<KnowledgeProfileNode | null>(null)
function selectKnowledge(point: KnowledgeProfileNode | null) {
  readingCompanionAnchor.value = null
  studyRequest.value = undefined
  selectedKnowledge.value = point
  if (point) { aiVisible.value = true; aiQuote.value = ''; aiAnchor.value = undefined; aiPrefill.value = ''; aiBlockTarget.value = undefined }
}
function askKnowledge(point: KnowledgeProfileNode) {
  readingCompanionAnchor.value = null
  studyRequest.value = undefined
  selectedKnowledge.value = point
  aiVisible.value = true
}
function discussEvidence(point: KnowledgeProfileNode, evidence: KnowledgeProfileNode['evidence'][number]) {
  askKnowledge(point)
  aiQuote.value = `${t('companionWorkspace.checkReference', '检查记录')} · ${t(`knowledgeProfile.outcomes.${evidence.outcome}`)} · ${t(`knowledgeProfile.support.${evidence.support}`)}`
  aiAnchor.value = { source_id: evidence.source_id, question_revision_id: evidence.question_revision_id, concept_ids: [point.knowledge_id] }
}
async function openKnowledgeLecture(point: KnowledgeProfileNode) {
  const node = courseStore.nodes.find(item => point.section_refs.includes(item.node_id))
  if (node) { await closeKnowledgeLibrary(false); statsOpen.value = false
    const blockId=point.block_refs?.find(id=>node.course_blocks?.some(b=>b.block_id===id))
    if(blockId) await selectCourseBlock({node,blockId})
    else selectNode(node)
  }
}
watch(() => courseStore.currentCourseId, () => { notesVisible.value = false; mistakesOpen.value = false; studyRequest.value = undefined; selectedKnowledge.value = null; knowledgeReadingReturn = null; knowledgeReturnSequence++ })
const notesVisible = ref(false)
const notebookOpen = ref(false)
const statsOpen = ref(false)
const mistakesOpen = ref(false)
const taskOpen = ref(false)
const courseAdjustmentOpen = ref(false)
const courseAdjustmentFocusPlanId = ref('')
const courseAdjustmentSectionId = ref('')
const taskNode = ref<Node | null>(null)
const taskReturnScroll = ref(0)
const taskOriginRect = ref<{ top: number; left: number; width: number; height: number } | null>(null)
const taskReturnElement = ref<HTMLElement | null>(null)
const continuityBusy = ref(false)
const studyRequest = ref<StudyRequest | undefined>()
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
const activeWorkspaceTool = computed<StudentWorkspaceTool>(() => mistakesOpen.value ? 'mistakes' : taskOpen.value ? 'practice' : statsOpen.value ? 'overview' : courseStore.showKnowledgeLibrary ? 'knowledge' : 'reading')
let restoringWorkspaceTool = false
let pendingWorkspaceTool: StudentWorkspaceTool | null = null
let workspaceNavigationSequence = 0
let workspaceToolSequence = 0
async function persistWorkspaceTool(tool: StudentWorkspaceTool) {
  if (route.name !== 'learning') return
  const sequence = ++workspaceNavigationSequence
  pendingWorkspaceTool = tool
  try { await router.replace({ name: 'learning', params: { ...route.params, nodeId: courseStore.currentNode?.node_id || route.params.nodeId }, query: { ...route.query, tool } }) }
  finally { if (sequence === workspaceNavigationSequence) pendingWorkspaceTool = null }
}
async function activateTool(tool: StudentWorkspaceTool, fromRoute = false) {
  const sequence = ++workspaceToolSequence
  const current = activeWorkspaceTool.value
  if (tool === current && tool !== 'reading') {
    if (fromRoute) return
    tool = 'reading'
  }
  if (tool === 'reading') {
    mistakesOpen.value = false
    closeStats()
    if (taskOpen.value) await closeTask()
    if (sequence !== workspaceToolSequence) return
    if (courseStore.showKnowledgeLibrary) await closeKnowledgeLibrary()
  } else {
    mistakesOpen.value = false
    if (tool !== 'knowledge' && courseStore.showKnowledgeLibrary) await closeKnowledgeLibrary(false)
    if (sequence !== workspaceToolSequence) return
    if (tool === 'practice') openQuestionBook()
    else if (tool === 'overview') openStats()
    else if (tool === 'knowledge') openKnowledgeLibrary()
    else { taskOpen.value = false; statsOpen.value = false; mistakesOpen.value = true }
  }
}
function openMistakeRetry(payload: { nodeId: string; taskRevisionId: string }) {
  const node = courseStore.nodes.find(item => item.node_id === payload.nodeId)
  if (!node) return
  mistakesOpen.value = false
  openTask(node, payload.taskRevisionId)
}
watch([() => route.query.tool, loadedLearningCourseId], async () => {
  if (pendingWorkspaceTool || restoringWorkspaceTool || !loadedLearningCourseId.value || loadedLearningCourseId.value !== String(route.params.courseId || '')) return
  if (activeWorkspaceTool.value === studentWorkspaceTool(route.query.tool)) return
  restoringWorkspaceTool = true
  try { await activateTool(studentWorkspaceTool(route.query.tool), true) } finally { restoringWorkspaceTool = false }
}, { flush: 'post' })
watch(activeWorkspaceTool, tool => {
  if (route.name !== 'learning' || restoringWorkspaceTool || loadedLearningCourseId.value !== courseStore.currentCourseId || !loadedLearningCourseId.value) return
  if (!pendingWorkspaceTool && studentWorkspaceTool(route.query.tool) === tool) return
  void persistWorkspaceTool(tool)
}, { flush: 'post' })
const activeCourseBlockId = ref('')
let courseGrowthLocationTimer: ReturnType<typeof setTimeout> | undefined
let courseGrowthSettleTimer: ReturnType<typeof setTimeout> | undefined

const isNarrow = computed(() => windowWidth.value < 1024)
const sidePanelVisible = computed(() => !courseStore.isFocusMode && !isGenerationPreview.value && ((aiVisible.value && !inlineCompanion.value) || (!isNarrow.value && (notesVisible.value || notebookOpen.value))))
watch(() => [courseStore.currentCourseId, courseStore.currentCourseVersionId], () => { readingCompanionAnchor.value = null; studyEntrySequence++ })
const dockActiveDomain = computed(() => mistakesOpen.value ? 'mistakes' : taskOpen.value ? 'question-book'
  : statsOpen.value ? 'overview'
  : courseStore.showKnowledgeLibrary ? 'knowledge-library'
  : 'course')

const isTeacherPreview = computed(() => String(route.query.teacherPreview || '') === '1')
// Keep the full learning UI; teacher trials use only session state and teacher APIs.
const isGenerationPreview = computed(() => (
  courseStore.currentCourseProjection === 'generation_preview' && !isTeacherPreview.value
))
const isTeacherCurrentProjection = computed(() => (
  courseStore.currentCourseProjection === 'generation_preview' && isTeacherPreview.value
))
const { visible: companionWelcome, dismiss: dismissCompanionWelcome } = useCompanionWelcome(
  computed(() => companionPreferences.proactive && !companionSettingsOpen.value && !companionEditing.value && !aiVisible.value && !taskOpen.value && !notebookOpen.value && !isTeacherPreview.value && !isGenerationPreview.value && !isNarrow.value
    && !courseStore.isFocusMode && Boolean(courseStore.currentCourseId)
    && loadedLearningCourseId.value === courseStore.currentCourseId
    && String(route.params.courseId || '') === courseStore.currentCourseId),
  computed(() => isTeacherPreview.value ? '' : getLearnerIdentity()),
)
const companionEligible=computed(()=>companionPreferences.proactive && !companionSettingsOpen.value && companionPageVisible.value && !companionEditing.value && !taskOpen.value && !aiVisible.value && !isTeacherPreview.value && !isGenerationPreview.value && !courseStore.isFocusMode && !isNarrow.value)
const { reminder:companionReminder, dismiss:dismissReminder } = useCompanionReminders(companionEligible,{suppressed:computed(()=>new Set(companionPreferences.suppressions[courseStore.currentCourseId]||[])),dismiss:(key,mode)=>{void companionPreferences.suppress(courseStore.currentCourseId,key,mode)}})
watch(()=>[courseStore.currentCourseId,isTeacherPreview.value],()=>{if(courseStore.currentCourseId&&!isTeacherPreview.value){void companionPreferences.load();void companionPreferences.loadSuppressions(courseStore.currentCourseId)}},{immediate:true})
async function openCompanionReminder(reminder:CompanionReminder) {
  const courseId = courseStore.currentCourseId
  await contentAreaRef.value?.closeInlineRecord?.()
  if (courseStore.currentCourseId !== courseId) return
  const note = noteStore.notes.find(item => item.id === reminder.note.id)
  if (!note) return
  closeAi()
  statsOpen.value = false
  taskOpen.value = false
  await closeKnowledgeLibrary(false)
  locateRecord(note)
  await nextTick()
  contentAreaRef.value?.openInlineRecord({ note, x:Math.max(20, window.innerWidth / 2 - 150), y:140 })
  dismissReminder()
}
const generationTask = computed(() => courseStore.currentCourseId ? generationStore.tasks.get(courseStore.currentCourseId) : undefined)
const activeGenerationNodeId = computed(() => generationTask.value?.currentNodes?.[0]?.node_id || generationStore.currentGeneratingNodeId || '')
const navigatorVisible = computed(() => (
  !courseStore.isFocusMode
  && navigatorOpen.value
  && (!isGenerationPreview.value || courseStore.courseTree.length > 0)
))
const learningLayoutRoot = ref<HTMLElement | null>(null)
const dockedSidePanelVisible = computed(() => !isNarrow.value && sidePanelVisible.value && !(aiFloating.value && !notesVisible.value && !notebookOpen.value))
const { layoutStyle: columnLayoutStyle, leftHandle: leftColumnHandle, rightHandle: rightColumnHandle } = useResizableColumns(learningLayoutRoot, {
  storageKey: 'lingzhi:course-reading:columns', left: 292, right: 360, leftMin: 200, rightMin: 280,
  enabled: () => !isNarrow.value,
  leftVisible: navigatorVisible, rightVisible: dockedSidePanelVisible,
})
const courseAdjustmentSectionTitle = computed(() => (
  courseStore.nodes.find(node => node.node_id === courseAdjustmentSectionId.value)?.node_name || ''
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

let learningCourseRequest = 0
async function loadLearningCourse(courseId: string) {
  const request = ++learningCourseRequest
  loadedLearningCourseId.value = ''
  autoFollowGeneration.value = true
  activeCourseBlockId.value = ''
  aiQuote.value = ''
  aiNodeId.value = ''
  aiAnchor.value = undefined
  aiPrefill.value = ''
  aiBlockTarget.value = undefined
  aiVisible.value = false
  courseAdjustmentOpen.value = false
  courseAdjustmentFocusPlanId.value = ''
  courseAdjustmentSectionId.value = ''
  notebookOpen.value = false
  statsOpen.value = false
  taskOpen.value = false
  workspaceStore.mistakeBookAttempts = []
  workspaceStore.practiceNeedsReviewCount = 0
  if (isTeacherPreview.value) {
    workspaceStore.$reset()
    noteStore.$reset()
    aiTeacherStore.clearPreviewSession()
  }
  await Promise.all([
    // The owner-checked preview snapshot supplies this course's navigation.
    // Loading every teacher course here competes with ongoing authoring jobs.
    isTeacherPreview.value ? Promise.resolve() : courseStore.fetchCourseList({ surface: 'student', background: true }),
    courseStore.loadCourse(courseId, isTeacherPreview.value ? {
      includeLearningRecords: false,
      taskType: 'teacher_outline_generation',
      monitorTask: false,
      previewSurface: 'teacher',
      teacherTrial: true,
      silentError: true,
    } : {}),
  ])
  if (request !== learningCourseRequest || courseStore.currentCourseId !== courseId || courseStore.courseLoadError) return
  if (!isTeacherPreview.value && getStudyIdentity()?.role !== 'student') generationStore.observeCourse(courseId)
  if (isGenerationPreview.value) {
    selectInitialNode()
    return
  }
  await loadLearningContext(courseId)
  if (request !== learningCourseRequest) return
  selectInitialNode()
  const requestedAction = continuationAction.value
  if (requestedAction?.availability === 'available'
      && route.query.learningAction === requestedAction.action_type
      && (isWorkspaceTaskAction(requestedAction) || requestedAction.action_type === 'view_chapter_result')) {
    await handleContinuationAction(requestedAction)
  }
  if (['practice', 'question-book'].includes(String(route.query.workspace || ''))) {
    await nextTick()
    openQuestionBook()
  }
}

function reloadLearningCourse() {
  if (!courseStore.loading && route.params.courseId) void loadLearningCourse(String(route.params.courseId))
}

watch(() => route.params.courseId, value => {
  if (value) void loadLearningCourse(String(value))
}, { immediate: true })


async function loadLearningContext(courseId: string) {
  if (
    (!isTeacherPreview.value && courseStore.currentCourseProjection !== 'published')
    || loadedLearningCourseId.value === courseId
  ) return
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
  if (isTeacherPreview.value) return
  // Natural pause #3: arriving at the course, before any reading has started.
  void aiTeacherStore.checkSuggestion('course_entered', String(route.params.nodeId || '') || undefined)
}

watch(() => courseStore.currentCourseProjection, async (projection, previous) => {
  if (isTeacherPreview.value || projection !== 'published' || previous !== 'generation_preview' || !courseStore.currentCourseId) return
  autoFollowGeneration.value = false
  await loadLearningContext(courseStore.currentCourseId)
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
  if (
    !node
    || !courseStore.currentCourseId
    || isGenerationPreview.value
    || isTeacherPreview.value
    || (isTeacherCurrentProjection.value && !node.objective_id)
  ) return
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
  if (!isTeacherPreview.value) generationStore.restoreGenerationState()
  window.addEventListener('resize', handleResize)
  document.addEventListener('focusin',updateCompanionAttention)
  document.addEventListener('focusout',updateCompanionAttention)
  document.addEventListener('visibilitychange',updateCompanionAttention)
})

onUnmounted(() => {
  document.removeEventListener('focusin',updateCompanionAttention)
  document.removeEventListener('focusout',updateCompanionAttention)
  document.removeEventListener('visibilitychange',updateCompanionAttention)
  learningCourseRequest++
  knowledgeReturnSequence++
  knowledgeReadingReturn = null
  aiTeacherStore.clearPreviewSession()
  if (noteStore.previewSession) {
    noteStore.$reset()
    workspaceStore.$reset()
  }
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
  if (manualSelection) mistakesOpen.value = false
  if(manualSelection && courseStore.showKnowledgeLibrary) void closeKnowledgeLibrary(false)
  if (isGenerationPreview.value && manualSelection && node.node_id !== activeGenerationNodeId.value) {
    autoFollowGeneration.value = false
  }
  activeCourseBlockId.value = ''
  courseStore.selectNode(node)
  courseStore.scrollToNode(node.node_id)
  if (updateRoute) void router.replace({
    name: 'learning',
    params: { courseId: courseStore.currentCourseId, nodeId: node.node_id },
    query: isTeacherPreview.value ? route.query : { ...route.query, tool: activeWorkspaceTool.value, learningAction: undefined, workspace: undefined },
  })
  if (isNarrow.value) navigatorOpen.value = false
}

async function selectCourseBlock(target: CourseBlockNavigationTarget) {
  if(courseStore.showKnowledgeLibrary) await closeKnowledgeLibrary(false)
  activeCourseBlockId.value = target.blockId
  courseStore.selectNode(target.node)
  if (String(route.params.nodeId || '') !== target.node.node_id) {
    await router.replace({
      name: 'learning',
      params: { courseId: courseStore.currentCourseId, nodeId: target.node.node_id },
      query: isTeacherPreview.value ? route.query : { ...route.query, tool: activeWorkspaceTool.value, learningAction: undefined, workspace: undefined },
    })
  }
  await nextTick()
  await contentAreaRef.value?.scrollToCourseBlock(target.node.node_id, target.blockId)
  if (isNarrow.value) navigatorOpen.value = false
}

function handleActiveBlockChange(payload: { nodeId: string; blockId: string }) {
  activeCourseBlockId.value = payload.blockId
}

const readingContext = computed(() => {
  const node = courseStore.currentNode
  const block = node?.course_blocks?.find(item => item.block_id === activeCourseBlockId.value)
  const legacyBlock = node?.content_blocks?.find(item => item.block_id === activeCourseBlockId.value)
  return {
    nodeId: node?.node_id || '', nodeName: node?.node_name || '',
    blockId: block?.block_id || legacyBlock?.block_id || '',
    blockTitle: String(block?.payload?.title || legacyBlock?.title || ''),
  }
})

function showAssistant() {
  void contentAreaRef.value?.closeInlineRecord?.()
  notesVisible.value = false
  notebookOpen.value = false
  aiVisible.value = true
}
function openReadingNote(payload: { note: Note; x: number; y: number }) {
  openStudyRecord(payload.note.id)
}
function createReadingNote(_event: MouseEvent) {
  if (courseStore.currentNode) void openStudyDialogue({ kind:'note', nodeId:courseStore.currentNode.node_id, quote:'' })
}
async function openStudyDialogue(request:StudyRequest, selectionRange?:Range) {
  const sequence = ++studyEntrySequence, courseId = courseStore.currentCourseId
  await contentAreaRef.value?.closeInlineRecord?.()
  if (sequence !== studyEntrySequence || courseId !== courseStore.currentCourseId) return
  openAi({ text:request.quote, nodeId:request.nodeId, anchor:request.anchor })
  companionHelpRange.value = selectionRange || null
  if (request.kind === 'explain' && !isNarrow.value) {
    readingCompanionAnchor.value = companionRef.value?.helpHost || null
  }
  studyRequest.value = { ...request, token:Date.now() + Math.random() }
}
function openSelectionStudy(payload: { text: string; nodeId: string; anchor?: Record<string, unknown>; selectionRange?:Range }) {
  void openStudyDialogue({ kind: 'explain', nodeId: payload.nodeId, quote: payload.text, anchor: payload.anchor, prompt:t('courseWorkspace.inlineAi.selectionExplain','请简要解释选中的内容，先说清含义，再给一个必要的小例子。') },payload.selectionRange)
}
function openStudyRecord(id:string) {
  const note = noteStore.notes.find(item=>item.id===id)
  if (note) void openStudyDialogue({ kind:'note', nodeId:note.nodeId, quote:note.quote, anchor:note.anchor, recordId:note.revision ? note.id : undefined })
}

function openAi(payload?: { text: string; nodeId: string; anchor?: Record<string, unknown> }) {
  companionHelpRange.value = null
  studyEntrySequence++
  readingCompanionAnchor.value = null
  studyRequest.value = undefined
  selectedKnowledge.value = null
  if (isGenerationPreview.value) return
  notebookOpen.value = false
  statsOpen.value = false
  courseStore.showKnowledgeLibrary = false
  aiBlockTarget.value = undefined
  aiQuote.value = payload?.text || ''
  aiNodeId.value = payload?.nodeId || ''
  aiAnchor.value = payload?.anchor
  aiPrefill.value = ''
  aiEntrypoint.value = payload?.text ? 'selection' : 'global'
  aiVisible.value = true
  if (isNarrow.value) navigatorOpen.value = false
}

function openCourseAdjustment(payload?: { planId?: string; sectionId?: string }) {
  void changeProposalsStore.fetchChangeProposals(courseStore.currentCourseId)
  courseAdjustmentFocusPlanId.value = payload?.planId || ''
  courseAdjustmentSectionId.value = payload?.sectionId || courseStore.currentNode?.node_id || ''
  aiVisible.value = false
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
  aiBlockTarget.value = isTeacherPreview.value ? undefined : target
  aiQuote.value = isTeacherPreview.value ? String(target.block.payload?.markdown || '') : ''
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
  studyRequest.value = undefined
  aiBlockTarget.value = undefined
  aiQuote.value = payload.text
  aiNodeId.value = payload.nodeId
  aiAnchor.value = undefined
  aiPrefill.value = t('courseWorkspace.aiTeacher.quickExplainPrompt', '请解释当前内容的核心概念。')
  aiEntrypoint.value = 'practice'
  aiVisible.value = true
}

function openNotebook() {
  if (notebookOpen.value) { closeNotebook(); return }
  notebookOpen.value = true
  aiVisible.value = false
  if (isNarrow.value) navigatorOpen.value = false
}

function closeNotebook() {
  notesVisible.value = false
  notebookOpen.value = false
}

function openQuestionBook() {
  if (taskOpen.value) { void closeTask(); return }
  const source = currentPracticeNode.value || courseStore.currentNode
  notebookOpen.value = false
  statsOpen.value = false
  courseStore.showKnowledgeLibrary = false
  openTask(source, '', 'all')
  if (isNarrow.value) navigatorOpen.value = false
}

type KnowledgeReadingReturn = { courseId:string; version:string; nodeId:string; scrollTop:number; blockDomId:string; blockOffset:number; activeBlockId:string; aiVisible:boolean; notebookOpen:boolean }
let knowledgeReadingReturn:KnowledgeReadingReturn|null = null
let knowledgeReturnSequence = 0
function captureKnowledgeReading() {
  knowledgeReturnSequence++
  const container=document.getElementById('content-scroll-container')
  const top=container?.getBoundingClientRect().top || 0
  const block=Array.from(container?.querySelectorAll<HTMLElement>('[id^="course-block-"]') || []).find(el=>el.getBoundingClientRect().height>0 && el.getBoundingClientRect().bottom>top+2)
  knowledgeReadingReturn={courseId:courseStore.currentCourseId,version:courseStore.currentCourseVersionId,nodeId:courseStore.currentNode?.node_id || '',scrollTop:container?.scrollTop || 0,
    blockDomId:block?.id || '',blockOffset:block ? block.getBoundingClientRect().top-top : 0,activeBlockId:activeCourseBlockId.value,aiVisible:aiVisible.value,notebookOpen:notebookOpen.value}
}
async function closeKnowledgeLibrary(restoreReading = true) {
  const saved=knowledgeReadingReturn
  const sequence=++knowledgeReturnSequence
  knowledgeReadingReturn=null
  selectedKnowledge.value=null
  courseStore.showKnowledgeLibrary=false
  if(!restoreReading || !saved || saved.courseId!==courseStore.currentCourseId || saved.version!==courseStore.currentCourseVersionId) return
  aiVisible.value=saved.aiVisible
  notebookOpen.value=saved.notebookOpen
  const node=courseStore.nodes.find(n=>n.node_id===saved.nodeId)
  if(node && courseStore.currentNode?.node_id!==node.node_id) courseStore.selectNode(node)
  activeCourseBlockId.value=saved.activeBlockId
  await nextTick()
  const restore=()=>{
    if(sequence!==knowledgeReturnSequence || courseStore.showKnowledgeLibrary || saved.courseId!==courseStore.currentCourseId || saved.version!==courseStore.currentCourseVersionId) return
    const container=document.getElementById('content-scroll-container')
    if(!container) return
    const block=saved.blockDomId ? document.getElementById(saved.blockDomId) : null
    const target=block?.getBoundingClientRect().height ? container.scrollTop + block.getBoundingClientRect().top-container.getBoundingClientRect().top-saved.blockOffset : saved.scrollTop
    const behavior=container.style.scrollBehavior
    container.style.scrollBehavior='auto'; container.scrollTop=target; container.style.scrollBehavior=behavior
  }
  restore()
  await new Promise<void>(resolve=>requestAnimationFrame(()=>{ restore(); resolve() }))
}
async function openKnowledgePractice(nodeId:string, revision:string) {
  const node=courseStore.nodes.find(n=>n.node_id===nodeId)
  if(!node) return
  await closeKnowledgeLibrary(false)
  openTask(node,revision)
}
function openMatrixKnowledge(point: KnowledgeProfileNode) {
  statsOpen.value = false
  selectedKnowledge.value = null
  courseStore.focusKnowledgeId = point.knowledge_id
  courseStore.showKnowledgeLibrary = true
}
function openMatrixPractice(nodeId: string, revision: string) {
  const node = courseStore.nodes.find(item => item.node_id === nodeId)
  if (!node) return
  statsOpen.value = false
  openTask(node, revision)
}
function openKnowledgeLibrary() {
  if(courseStore.showKnowledgeLibrary) { void closeKnowledgeLibrary(); return }
  captureKnowledgeReading()
  notebookOpen.value=false
  statsOpen.value=false
  taskOpen.value=false
  courseStore.showKnowledgeLibrary=true
  if(isNarrow.value) navigatorOpen.value=false
}
// Other course tools can also request this same knowledge view.
watch(()=>courseStore.showKnowledgeLibrary,visible=>{ if(visible && !knowledgeReadingReturn) captureKnowledgeReading(); else if(!visible) knowledgeReadingReturn=null },{flush:'sync'})

function openStats() {
  if (statsOpen.value) { closeStats(); return }
  selectedKnowledge.value = null
  statsOpen.value = true
  notebookOpen.value = false
  taskOpen.value = false
  courseStore.showKnowledgeLibrary = false
}

function closeStats() {
  selectedKnowledge.value = null
  statsOpen.value = false
}

function toggleAi() {
  if(inlineCompanion.value){showAssistant();void companionSurfaceRef.value?.expand();return}
  if (aiVisible.value) { closeAi(); return }
  showAssistant()
  if (isNarrow.value) navigatorOpen.value = false
}

function closeAi() {
  notesVisible.value = false
  if (aiFloating.value && courseStore.showKnowledgeLibrary) knowledgeStudyRef.value?.closePoint()
  aiVisible.value = false
  if (!isNarrow.value && !courseStore.isFocusMode) {
    nextTick(() => companionRef.value?.focus())
  }
}

function locateRecord(record: any) {
  notebookOpen.value = false
  const node = courseStore.nodes.find(item => item.node_id === record.nodeId)
  if (node) selectNode(node)
  window.setTimeout(() => courseStore.scrollToNote(record.id), 160)
}

function openTask(node?: Node | null, taskRevisionId = '', scope: 'node' | 'final' | 'all' = 'node') {
  mistakesOpen.value = false
  const source = node || courseStore.currentNode
  if (!source && scope === 'node') return
  notebookOpen.value = false
  statsOpen.value = false
  if (taskRevisionId && source && courseStore.currentCourseId) {
    workspaceStore.preparePracticeTask(courseStore.currentCourseId, source.node_id, taskRevisionId)
  }
  const trigger = document.activeElement instanceof HTMLElement ? document.activeElement : null
  const sourceBlock = source ? document.getElementById(`practice-block-${source.node_id}`) : null
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
  workspaceStore.practiceScope = scope
  taskOpen.value = true
}

async function closeTask() {
  taskOpen.value = false
  workspaceStore.endExplicitPracticeTask()
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
  if(!isTeacherPreview.value && courseStore.currentCourseId) await useLearnerModelStore().load(courseStore.currentCourseId).catch(()=>undefined)
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
    void router.push(getStudyIdentity()?.role === 'student' ? '/study?view=courses' : '/courses')
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
.learning-side-panel { min-width:0; min-height:0; }
.learning-side-panel.is-docked { display:flex; flex-direction:column; background:#fff; border:1px solid var(--lz-border); --side-width:clamp(320px,25vw,380px); width:var(--side-width); flex:0 0 var(--side-width); overflow:hidden; border-radius:var(--lz-radius-surface); }
.learning-side-panel.is-docked > .ai-teacher-panel,.learning-side-panel.is-docked > .reading-notes { width:100%; flex:1; min-height:0; height:auto; }
.learning-stage { position:relative; flex:1; display:flex; flex-direction:column; min-height:0; min-width:0; overflow:hidden; }
.exchange-course-notice{flex:none;display:flex;align-items:center;justify-content:space-between;gap:16px;padding:10px 18px;background:#f6f3fc;color:#66548a;font-size:15px;border-bottom:1px solid #e4dff0}.exchange-course-notice a{color:#6551c7;white-space:nowrap}.exchange-course-notice a:focus-visible{outline:3px solid #9385ed;outline-offset:3px}
.learning-main { position: relative; min-width: 0; min-height: 0; flex: 1; display: flex; flex-direction: column; overflow: hidden; container-type: inline-size; border: 1px solid rgba(255,255,255,.82); border-radius: var(--lz-radius-surface); background: #fff; box-shadow: var(--lz-shadow-panel); backdrop-filter:none; -webkit-backdrop-filter:none; }
.has-ai-course-growth .learning-main { border-color:rgba(165,180,252,.7); box-shadow:0 16px 42px rgba(30,64,175,.1),0 2px 8px rgba(15,23,42,.05); }
.learning-content { min-height: 0; flex: 1; }
.notebook-side-panel { width:100%; flex:1; min-width:0; min-height:0; overflow:hidden; border:1px solid rgba(255,255,255,.82); border-radius:var(--lz-radius-surface); background:#fff; box-shadow:var(--lz-shadow-panel); }
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
.slide-left-enter-active, .slide-left-leave-active { transition: transform .2s ease, opacity .2s ease; }
.slide-left-enter-from, .slide-left-leave-to { transform: translateX(-100%); opacity: 0; }
@media (min-width:1024px) {
  .side-panel-enter-active,.side-panel-leave-active { transition:opacity .16s ease,transform .16s ease; }
  .learning-side-panel.side-panel-enter-from,.learning-side-panel.side-panel-leave-to { opacity:0; transform:translateX(8px); }
}
@media (prefers-reduced-motion:reduce) {
  .side-panel-enter-active,.side-panel-leave-active { transition:none; }
}
@media (max-width:1279px) {
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
  .learning-main { transition:none; }
}
</style>

<style scoped>
.learning-side-panel.is-docked { --side-width:clamp(350px,29vw,430px); }
.learning-side-panel.is-companion-floating { align-self:flex-start; height:calc(100% - 26px); margin-top:14px; border:1px solid #dcd0f0; border-radius:20px; box-shadow:0 12px 32px #5d42731c; transform:none; }
.stats-tool :deep(.learning-overview:has(.knowledge-detail-inline)) { padding:0; }
</style>

<style scoped>
.learning-side-panel.is-companion-floating { background:transparent; border:0; box-shadow:none; overflow:visible; }
.learning-side-panel.is-companion-floating { display:none; }
@media(min-width:1024px){
  .learning-view{gap:0}
  .navigator-surface{min-width:0;width:var(--column-left-width);flex:0 0 var(--column-left-width)}
  .learning-side-panel.is-docked:not(.is-companion-floating){--side-width:var(--column-right-width)}
}
</style>

<style scoped>
.mistakes-overlay{overflow:auto;background:#fff}.mistakes-overlay :deep(.mistake-notebook){min-height:100%;border:0;border-radius:0}.learning-view :deep(.learning-dock.is-toolbar){position:relative;z-index:12}.learning-main{display:flex;flex-direction:column;min-height:0}.learning-stage{flex:1;min-height:0}
</style>
