<template>
  <section
    ref="workbenchRoot"
    class="teacher-workbench"
    :class="{ 'is-ai-collaboration': aiCollaborationOpen }"
    :style="{ '--ai-pane-width': `${aiPanePercent}%` }"
  >
    <aside v-show="!aiCollaborationOpen" class="stage-rail" :aria-label="t('courseWorkbench.stageNavigation', '课程生产阶段')">
      <header><strong class="stage-rail-title">{{ t('courseWorkbench.title', '课程工作台') }}</strong></header>
      <nav>
        <button v-for="stage in stages" :key="stage.id" type="button" :class="{ active: activeStage === stage.id }" @click="activeStage = stage.id">
          <span>{{ stage.step }}</span><component :is="stage.icon" :size="18" /><strong>{{ stage.label }}</strong><Check v-if="stageReady(stage.id)" :size="15" />
        </button>
      </nav>
      <section class="companion-entry">
        <small>{{ t('courseWorkbench.supporting.group', '其他课程文件') }}</small>
        <button type="button" :class="{ active: activeStage === 'companion' }" @click="activeStage = 'companion'">
          <FileCheck2 :size="18" /><strong>{{ t('courseWorkbench.supporting.title', '配套文档') }}</strong><ChevronRight :size="16" />
        </button>
      </section>
      <footer><span>{{ readyStageCount }}/5</span><div><i :style="{ width: `${readyStageCount / 5 * 100}%` }" /></div></footer>
    </aside>

    <main
      ref="workbenchCenter"
      class="workbench-center"
      :class="{
        'is-outline-workspace': showOutlineWorkspace,
        'is-lesson-workspace': !['foundation', 'companion'].includes(activeStage),
      }"
    >
      <header class="center-heading">
        <div><small>{{ activeStage === 'companion' ? t('courseWorkbench.supporting.kicker', '配套文档') : `${activeStageDefinition.step} / 05` }}</small><h2>{{ activeStageDefinition.label }}</h2></div>
        <button
          v-if="showOutlineWorkspace"
          type="button"
          :aria-pressed="editingOutline"
          :disabled="finishingOutline"
          @click="toggleOutlineEditing"
        >
          <LoaderCircle v-if="finishingOutline" :size="15" class="spin" />
          <Check v-else-if="editingOutline" :size="15" />
          <Pencil v-else :size="15" />
          {{ editingOutline
            ? t('courseWorkbench.finishOutlineEditing', '完成编辑')
            : t('courseWorkbench.editOutline', '编辑大纲') }}
        </button>
      </header>

      <section v-if="showStreaming" class="generation-surface" aria-live="polite">
        <header>
          <div><TriangleAlert v-if="generationFailed" :size="18" /><LoaderCircle v-else :size="18" class="spin" /><span><strong>{{ generationFailed ? t('courseWorkbench.generationInterrupted', '生成已中断') : t('courseWorkbench.generating', '正在生成课程大纲') }}</strong><small>{{ generationFailed ? generationErrorPresentation?.summary : currentGenerationLabel }}</small></span></div>
          <button v-if="generationRunning" type="button" @click="stopGeneration"><Pause :size="15" />{{ t('courseWorkbench.pause', '暂停') }}</button>
        </header>
        <div class="generation-progress"><i :style="{ transform: `scaleX(${generationProgress / 100})` }" /></div>
        <article class="stream-content">
          <OutlineGrowthStream
            v-if="outlineGrowth || (hasOutline && !hasStreamedBody)"
            :growth="outlineGrowth"
            :nodes="outlinePreviewNodes"
          />
          <section v-for="node in visibleStreamNodes" v-else :key="node.node_id">
            <h3>{{ node.node_name }}</h3>
            <MarkdownRenderer :content="nodeContent(node)" />
            <span v-if="node.node_id === generationStore.currentGeneratingNodeId" class="stream-caret" />
          </section>
          <div v-if="!outlineGrowth && !visibleStreamNodes.length && !generationFailed" class="stream-waiting"><LoaderCircle :size="20" class="spin" />{{ t('courseWorkbench.waitingForContent', 'AI 正在建立课程结构…') }}</div>
          <div v-else-if="!outlineGrowth && !visibleStreamNodes.length && generationFailed" class="stream-waiting stream-failed"><TriangleAlert :size="22" />{{ t('courseWorkbench.noContentGenerated', '本次没有生成课程内容，请检查提示后重试。') }}</div>
        </article>
        <AppErrorNotice v-if="generationErrorPresentation" class="workbench-error" :presentation="generationErrorPresentation" compact>
          <template #action><button type="button" @click="submitFoundation">{{ t('common.retry', '重试') }}</button></template>
        </AppErrorNotice>
      </section>

      <section v-else-if="activeStage === 'foundation' && outlineShapeAwaitingReview" class="formal-surface outline-shape-review" data-testid="outline-shape-review">
        <article>
          <ol class="shape-chapter-list">
            <li v-for="(chapter, index) in outlineGrowthChapters" :key="String(chapter.chapter_number || index)">
              <span class="shape-chapter-index">{{ String(index + 1).padStart(2, '0') }}</span>
              <div><strong>{{ chapter.title }}</strong><small>{{ chapter.learning_focus }}</small></div>
              <label><input v-model.number="chapterSectionCounts[index]" type="number" min="1" max="100" :aria-label="t('courseWorkbench.shapeReview.countLabel', '{chapter}的小节数').replace('{chapter}', String(chapter.title || index + 1))" /><span>{{ t('courseWorkbench.form.sectionUnit', '小节') }}</span></label>
            </li>
          </ol>
          <AppErrorNotice v-if="shapeConfirmErrorPresentation" class="shape-confirm-error" :presentation="shapeConfirmErrorPresentation" compact />
        </article>
        <footer><span>{{ t('courseWorkbench.shapeReview.total', '确认后将生成 {count} 个小节').replace('{count}', String(totalSectionCount)) }}</span><button class="primary" type="button" :disabled="shapeConfirming || !shapeCountsValid" @click="confirmOutlineShape"><Sparkles :size="16" />{{ shapeConfirming ? t('courseWorkbench.shapeReview.confirming', '正在继续…') : t('courseWorkbench.shapeReview.confirm', '确认并生成小章节') }}</button></footer>
      </section>

      <section v-else-if="showOutlineWorkspace" class="formal-surface outline-workspace" data-testid="outline-workspace">
        <CourseOutlineReview
          ref="outlineEditor"
          class="inline-outline-review"
          :course-id="courseId"
          :course-name="courseTitle"
          :nodes="courseStore.nodes"
          :task="generationTask"
          :editable="editingOutline"
          :requires-confirmation="outlineAwaitingReview"
          variant="inline"
          surface="teacher"
          @confirmed="handleInlineOutlineConfirmed"
          @next="activeStage = 'lesson'"
        />
      </section>

      <form v-else-if="activeStage === 'foundation'" class="stage-form" @submit.prevent="submitFoundation">
        <label class="form-field form-field--wide"><span>{{ t('courseWorkbench.form.learningGoal', '教学目标') }} <b>*</b></span><textarea v-model.trim="foundation.goal" required rows="4" :placeholder="t('courseWorkbench.form.learningGoalPlaceholder', '学生完成课程后能够……')" /></label>
        <div class="form-grid">
          <label class="form-field"><span>{{ t('courseWorkbench.form.totalHours', '总学时') }}</span><input v-model.number="foundation.totalHours" type="number" min="1" max="1000" /></label>
        </div>
        <label class="form-field form-field--wide"><span>{{ t('courseWorkbench.form.requirements', '补充要求') }}</span><textarea v-model.trim="foundation.requirements" rows="4" :placeholder="t('courseWorkbench.form.requirementsPlaceholder', '例如：每章包含案例讨论，兼顾理论与实践')" /></label>
        <footer><button class="primary" type="submit" :disabled="generationStarting || !foundation.goal"><Sparkles :size="16" />{{ t('courseWorkbench.generateChapterSkeleton', '生成大章节') }}</button></footer>
      </form>

      <CompanionDocumentStudio
        v-else-if="activeStage === 'companion'"
        :course-id="courseId"
        @saved="handleCompanionSaved"
      />

      <section v-else class="lesson-stage" :class="{ 'has-lesson-outline': activeStage === 'lesson' && lessonStore.lessons.length && !outlineGatePending }">
        <div class="lesson-workspace" :class="{ 'is-outline-collapsed': lessonOutlineCollapsed }">
          <aside
            v-if="activeStage === 'lesson' && lessonStore.lessons.length && !outlineGatePending"
            v-show="!lessonOutlineCollapsed"
            class="lesson-outline"
            :aria-label="t('courseWorkbench.lessonOutline.title', '教案目录')"
          >
            <nav id="lesson-outline-navigation">
              <section v-for="lesson in lessonStore.lessons" :key="lesson.lesson_unit_id" class="lesson-outline-chapter">
                <button
                  class="lesson-outline-chapter-button"
                  type="button"
                  :class="{ active: selectedLessonId === lesson.lesson_unit_id }"
                  :disabled="aiCandidatePending && selectedLessonId !== lesson.lesson_unit_id"
                  :aria-current="selectedLessonId === lesson.lesson_unit_id ? 'page' : undefined"
                  :aria-label="`${lesson.title}，${lessonGenerationStateLabel(lesson)}`"
                  @click="selectLesson(lesson.lesson_unit_id)"
                >
                  <i class="lesson-outline-chapter-marker" :data-state="lessonGenerationState(lesson)" aria-hidden="true" />
                  <span class="lesson-outline-chapter-copy">
                    <strong>{{ lesson.title }}</strong>
                    <small :data-state="lessonGenerationState(lesson)">{{ lessonGenerationStateLabel(lesson) }}</small>
                  </span>
                </button>
              </section>
            </nav>
          </aside>

          <div class="lesson-stage-content">
        <nav v-if="lessonStore.lessons.length && !outlineGatePending" class="lesson-navigator" :aria-label="t('courseWorkbench.lessonNavigation', '课次导航')">
          <button
            class="lesson-outline-toggle"
            type="button"
            :aria-expanded="!lessonOutlineCollapsed"
            aria-controls="lesson-outline-navigation"
            :title="lessonOutlineCollapsed
              ? t('courseWorkbench.lessonOutline.showProgress', '展示总进度')
              : t('courseWorkbench.lessonOutline.hideProgress', '收起总进度')"
            @click="lessonOutlineCollapsed = !lessonOutlineCollapsed"
          >
            <PanelLeftOpen v-if="lessonOutlineCollapsed" :size="15" />
            <PanelLeftClose v-else :size="15" />
            {{ t('courseWorkbench.lessonOutline.progress', '总进度') }}
          </button>
          <button type="button" :disabled="!previousLesson || aiCandidatePending" @click="selectLesson(previousLesson?.lesson_unit_id)"><ChevronLeft :size="15" />{{ t('courseWorkbench.previousLesson', '上一讲') }}</button>
          <label class="lesson-selector"><span>{{ t('courseWorkbench.form.lesson', '选择课次') }}</span><select v-model="selectedLessonId" :disabled="aiCandidatePending"><option value="" disabled>{{ t('courseWorkbench.form.chooseLesson', '请选择课次') }}</option><option v-for="lesson in lessonStore.lessons" :key="lesson.lesson_unit_id" :value="lesson.lesson_unit_id">{{ lesson.title }}</option></select></label>
          <button type="button" :disabled="!nextLesson || aiCandidatePending" @click="selectLesson(nextLesson?.lesson_unit_id)">{{ t('courseWorkbench.nextLesson', '下一讲') }}<ChevronRight :size="15" /></button>
        </nav>
        <nav
          v-if="activeStage === 'lesson' && selectedLesson?.sections.length && !lessonStageBlocked"
          class="lesson-section-tabs"
          :aria-label="t('courseWorkbench.lessonDocument.sectionNavigation', '教案小节')"
        >
          <button
            v-for="(section, sectionIndex) in selectedLesson.sections"
            :key="section.section_node_id"
            type="button"
            :class="{ active: selectedLessonSectionId === section.section_node_id }"
            :disabled="aiCandidatePending && selectedLessonSectionId !== section.section_node_id"
            :title="aiCandidatePending && selectedLessonSectionId !== section.section_node_id
              ? t('courseWorkbench.aiCollaboration.scopeLocked', '请先采用或放弃当前候选')
              : ''"
            :aria-current="selectedLessonSectionId === section.section_node_id ? 'page' : undefined"
            @click="selectLessonSection(selectedLesson.lesson_unit_id, section.section_node_id)"
          >
            <span>{{ String(sectionIndex + 1).padStart(2, '0') }}</span>
            <strong>{{ section.title }}</strong>
          </button>
        </nav>
        <AppErrorNotice v-if="lessonStageBlocked && lessonPrerequisiteError" class="prerequisite-error" :presentation="lessonPrerequisiteError" compact>
          <template #action><button type="button" :disabled="lessonStore.loading" @click="resolveLessonPrerequisite">{{ lessonPrerequisiteState.action }}</button></template>
        </AppErrorNotice>
        <div v-else-if="lessonStageBlocked" class="prerequisite" :data-state="lessonPrerequisiteState.kind" aria-live="polite">
          <LoaderCircle v-if="lessonPrerequisiteState.kind === 'loading'" :size="24" class="spin" />
          <FileText v-else :size="24" />
          <strong>{{ lessonPrerequisiteState.title }}</strong>
          <button v-if="lessonPrerequisiteState.action" type="button" :disabled="lessonStore.loading" @click="resolveLessonPrerequisite">{{ lessonPrerequisiteState.action }}</button>
        </div>

        <template v-else-if="activeStage === 'question-bank'">
          <QuestionBankReviewPanel
            class="question-workbench-surface"
            :course-id="courseId"
            :initial-node-ids="selectedLessonQuestionNodeIds"
            :initial-scope-label="selectedLesson?.title || ''"
            :material-asset-ids="activeReferences.map(item => item.material_asset_id)"
            @updated="questionBankReady = true"
          />
          <footer class="stage-next-bar"><span /><button class="primary" type="button" @click="activeStage = 'script'"><ChevronRight :size="15" />{{ t('courseWorkbench.nextToScript', '进入讲稿') }}</button></footer>
        </template>

        <template v-else-if="activeStage === 'lesson'">
          <section v-if="lessonGenerationActive" class="generation-surface lesson-generation-surface" aria-live="polite">
            <header><div><LoaderCircle :size="18" class="spin" /><span><strong>{{ t('courseWorkbench.generatingLessonPlan', '正在生成本讲教案') }}</strong><small>{{ lessonJob?.message || selectedLesson?.title }}</small></span></div></header>
            <div class="generation-progress"><i :style="{ transform: `scaleX(${lessonGenerationProgress / 100})` }" /></div>
            <article v-if="lessonStreamSegments.length" class="lesson-stream-document" :aria-label="t('courseWorkbench.lessonStreamDraft', 'AI 工作稿')">
              <small>{{ t('courseWorkbench.lessonStreamDraft', 'AI 工作稿') }}</small>
              <h3>{{ selectedLesson?.title }}</h3>
              <p v-for="(segment, index) in lessonStreamSegments" :key="`${index}-${segment}`">
                {{ segment }}<span v-if="index === lessonStreamSegments.length - 1" class="stream-caret" />
              </p>
            </article>
            <div v-else class="lesson-stream-waiting">{{ t('courseWorkbench.lessonStreamWaiting', '正在组织教案结构…') }}</div>
          </section>
          <form v-else-if="selectedLesson && !workingLessonRevision" class="stage-form stage-form--lesson" @submit.prevent="generateLessonPlan">
            <label class="form-field form-field--wide"><span>{{ t('courseWorkbench.form.lessonFocus', '本讲重点') }}</span><textarea v-model.trim="lessonRequirements" rows="4" :placeholder="t('courseWorkbench.form.lessonFocusPlaceholder', '填写重难点、教学方法或课堂活动要求')" /></label>
            <AppErrorNotice v-if="lessonGenerationErrorPresentation" class="lesson-generation-error" :presentation="lessonGenerationErrorPresentation" compact />
            <footer class="lesson-form-actions"><button class="primary" type="submit" :disabled="lessonBusy || lessonGenerationActive || !selectedLessonId"><LoaderCircle v-if="lessonBusy" :size="16" class="spin" /><Sparkles v-else :size="16" />{{ lessonGenerationFailed ? t('courseWorkbench.retryLessonPlan', '重新生成本讲教案') : t('courseWorkbench.generateLessonPlan', '生成本讲教案') }}</button></footer>
          </form>
          <TeacherLessonPlanDocument
            v-else-if="workingLessonRevision && selectedLesson"
            ref="lessonPlanDocument"
            :course-id="courseId"
            :lesson="selectedLesson"
            :confirmed="lessonPlanConfirmed"
            :assistant-open="aiCollaborationOpen"
            :confirming="lessonConfirming"
            :confirm-error="lessonConfirmError"
            :active-section-id="selectedLessonSectionId"
            @update:active-section-id="selectedLessonSectionId = $event"
            @confirm="confirmLessonPlan"
            @next="activeStage = 'question-bank'"
            @open-ai="openLessonAiCollaboration"
            @ai-candidate-change="handleAiCandidateChange"
            @ai-resolving="handleAiResolving"
            @ai-resolved="handleAiResolved"
            @ai-error="handleAiError"
          />
        </template>

        <template v-else-if="activeStage === 'script'">
          <TeacherScriptDocument
            v-if="selectedLesson"
            :course-id="courseId"
            :lesson="selectedLesson"
            :confirmed="scriptConfirmed"
            :confirming="scriptConfirming"
            :confirm-error="scriptConfirmError"
            :generating="scriptGenerating"
            :generation-error="scriptGenerationError"
            :can-generate="Boolean(confirmedLessonRevision)"
            @generate="generateScript"
            @saved="handleScriptSaved"
            @confirm="confirmScript"
            @next="activeStage = 'ppt'"
          />
        </template>

        <template v-else-if="activeStage === 'ppt'">
          <section class="ppt-entry">
            <Presentation :size="24" />
            <div><strong>{{ selectedLesson?.title }}</strong></div>
            <button class="primary" type="button" :disabled="!confirmedLessonRevision || !scriptConfirmed" @click="openPptWorkspace"><Presentation :size="15" />{{ t('courseWorkbench.openPptWorkbench', '进入 PPT 工作台') }}</button>
          </section>
        </template>
          </div>
        </div>
      </section>
    </main>

    <div
      v-if="aiCollaborationOpen"
      class="ai-workspace-resizer"
      role="separator"
      tabindex="0"
      aria-orientation="vertical"
      :aria-label="t('courseWorkbench.aiCollaboration.resize', '调整 AI 助手宽度')"
      aria-valuemin="32"
      aria-valuemax="46"
      :aria-valuenow="aiPanePercent"
      @pointerdown="startAiPaneResize"
      @keydown="resizeAiPaneWithKeyboard"
    ><i /></div>

    <TeacherLessonAiWorkspace
      v-if="aiCollaborationOpen && selectedLesson"
      :course-title="courseTitle"
      :lesson-title="selectedLesson.title"
      :section-title="selectedLessonSectionTitle"
      :reference-count="activeReferences.length"
      :messages="aiMessages"
      :phase="aiPhase"
      :busy="aiCollaborationBusy"
      :candidate-pending="aiCandidatePending"
      :candidate-fields="aiCandidateFieldLabels"
      :clarification-options="aiClarificationOptions"
      :can-retry="Boolean(lastAiOperation)"
      @close="closeLessonAiCollaboration"
      @send="handleAiRequest"
      @clarify="handleAiClarification"
      @retry="retryAiAction"
      @accept="resolveAiCandidate(true)"
      @reject="resolveAiCandidate(false)"
      @focus-candidate="focusAiCandidate"
    />

    <CourseReferenceTray
      v-else
      v-model="activeReferences"
      :course-id="courseId"
      :stage="activeStage"
      :lesson-id="activeReferenceLessonId"
      :scope-target-id="lessonReferenceTargetId"
      :scope-target-type="lessonReferenceTargetId ? 'lesson_plan' : ''"
      :scope-target-label="selectedLesson?.title || ''"
      :previous-scope-target-id="previousLessonReferenceTargetId"
      @open-course-information="emit('open-course-information')"
    />
  </section>
</template>

<script setup lang="ts">
import { computed, markRaw, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { BookOpenText, Check, ChevronLeft, ChevronRight, ClipboardList, FileCheck2, FileText, Layers3, ListChecks, LoaderCircle, PanelLeftClose, PanelLeftOpen, Pause, Pencil, Presentation, Sparkles, TriangleAlert } from 'lucide-vue-next'
import AppErrorNotice from './AppErrorNotice.vue'
import CompanionDocumentStudio from './CompanionDocumentStudio.vue'
import CourseOutlineReview from './CourseOutlineReview.vue'
import CourseReferenceTray, { type CourseReferenceItem } from './CourseReferenceTray.vue'
import MarkdownRenderer from './MarkdownRenderer.vue'
import OutlineGrowthStream from './OutlineGrowthStream.vue'
import QuestionBankReviewPanel from './QuestionBankReviewPanel.vue'
import TeacherLessonAiWorkspace from './TeacherLessonAiWorkspace.vue'
import TeacherLessonPlanDocument from './TeacherLessonPlanDocument.vue'
import TeacherScriptDocument from './TeacherScriptDocument.vue'
import {
  assessTeacherLessonRequest,
  buildTeacherLessonAiInstruction,
  changedTeacherLessonFields,
  teacherLessonAiBusy,
  transitionTeacherLessonAiPhase,
  type TeacherLessonAiEvent,
  type TeacherLessonAiMessage,
  type TeacherLessonAiPhase,
} from '../composables/useTeacherLessonAiCollaboration'
import { t } from '../shared/i18n'
import type { CourseGenerationOptions } from '../shared/prompt-config'
import { useCourseStore } from '../stores/course'
import { useCourseWorkspaceStore } from '../stores/courseWorkspace'
import { useGenerationStore } from '../stores/generation'
import { lessonPlanStreamSegments, useTeacherLessonAuthoringStore, type TeacherLessonPlanCandidate } from '../stores/teacherLessonAuthoring'
import { toAppError } from '../utils/app-error'
import http, { teacherRequestConfig } from '../utils/http'

type CoreStageId = 'foundation' | 'lesson' | 'question-bank' | 'script' | 'ppt'
type StageId = CoreStageId | 'companion'
type LessonPlanDocumentHandle = {
  requestAiCandidate: (instruction: string) => Promise<TeacherLessonPlanCandidate | null>
  resolveAiCandidate: (accept: boolean) => Promise<boolean>
  focusCandidate: () => void
}
const props = withDefaults(defineProps<{ courseId: string; courseTitle: string; generationOptions: CourseGenerationOptions & { subject?: string }; generationStarting?: boolean; initialStage?: StageId; initialLessonId?: string; outlineEditing?: boolean }>(), { initialStage: 'foundation', initialLessonId: '', outlineEditing: false })
const emit = defineEmits<{
  (event: 'generateOutline', payload: { subject: string; options: CourseGenerationOptions; references: CourseReferenceItem[] }): void
  (event: 'update:outlineEditing', value: boolean): void
  (event: 'outlineConfirmed'): void
  (event: 'open-course-information'): void
}>()
const courseStore = useCourseStore(); const courseWorkspaceStore = useCourseWorkspaceStore(); const generationStore = useGenerationStore(); const lessonStore = useTeacherLessonAuthoringStore()
const activeStage = ref<StageId>(props.initialStage); const selectedLessonId = ref(props.initialLessonId)
const selectedLessonSectionId = ref('')
const lessonOutlineCollapsed = ref(true)
const workbenchRoot = ref<HTMLElement | null>(null)
const workbenchCenter = ref<HTMLElement | null>(null)
const lessonPlanDocument = ref<LessonPlanDocumentHandle | null>(null)
const aiCollaborationOpen = ref(false)
const aiPanePercent = ref(38)
const aiPhase = ref<TeacherLessonAiPhase>('ready')
const aiCandidate = ref<TeacherLessonPlanCandidate | null>(null)
const aiMessages = ref<TeacherLessonAiMessage[]>([])
const aiSessionScopeKey = ref('')
const aiMessageSequence = ref(0)
const aiClarificationOptions = ref<string[]>([])
const lastAiOperation = ref<'generate' | 'accept' | 'reject' | ''>('')
const replacingAiCandidate = ref(false)
const outlineEditor = ref<{ finishEditing: () => Promise<boolean> } | null>(null)
const finishingOutline = ref(false)
const editingOutline = computed({
  get: () => props.outlineEditing,
  set: value => emit('update:outlineEditing', value),
})
const referencesByScope = reactive<Record<string, CourseReferenceItem[]>>({})
const activeReferenceScope = computed(() => (
  activeStage.value === 'lesson' && selectedLessonId.value
    ? `lesson:${selectedLessonId.value}`
    : activeStage.value
))
const activeReferences = computed({
  get: () => referencesByScope[activeReferenceScope.value] || [],
  set: value => { referencesByScope[activeReferenceScope.value] = value },
})
const activeReferenceLessonId = computed(() => ['lesson', 'question-bank', 'script', 'ppt'].includes(activeStage.value) ? selectedLessonId.value : '')
const foundation = reactive({ goal: '', totalHours: 32, requirements: '' })
const chapterSectionCounts = ref<number[]>([])
const loadedShapeRevision = ref('')
const shapeConfirming = ref(false)
const shapeConfirmError = ref<unknown>(null)
const totalSectionCount = computed(() => chapterSectionCounts.value.reduce((total, count) => total + Math.max(1, Number(count || 1)), 0))
const lessonRequirements = ref('')
const lessonBusy = ref(false); const lessonConfirming = ref(false); const lessonConfirmError = ref(''); const scriptGenerating = ref(false); const scriptGenerationError = ref(''); const scriptConfirming = ref(false); const scriptConfirmError = ref(''); const generationRequested = ref(false)
const retainedOutlineGrowth = ref<Record<string, any> | null>(null)
const questionBankReady = ref(false)
const stages = computed(() => [
  { id: 'foundation' as const, step: '01', label: t('courseWorkbench.stages.foundation', '课程基础'), icon: markRaw(Layers3) },
  { id: 'lesson' as const, step: '02', label: t('courseWorkbench.stages.lesson', '教案'), icon: markRaw(ClipboardList) },
  { id: 'question-bank' as const, step: '03', label: t('courseWorkbench.stages.questionBank', '题库'), icon: markRaw(ListChecks) },
  { id: 'script' as const, step: '04', label: t('courseWorkbench.stages.script', '讲稿'), icon: markRaw(BookOpenText) },
  { id: 'ppt' as const, step: '05', label: t('courseWorkbench.stages.ppt', 'PPT'), icon: markRaw(Presentation) },
])
const activeStageDefinition = computed(() => stages.value.find(item => item.id === activeStage.value) || {
  id: 'companion' as const,
  step: '',
  label: t('courseWorkbench.supporting.title', '配套文档'),
  icon: markRaw(FileCheck2),
})
const selectedLesson = computed(() => lessonStore.lessons.find(item => item.lesson_unit_id === selectedLessonId.value))
const selectedLessonSectionTitle = computed(() => selectedLesson.value?.sections.find(
  item => item.section_node_id === selectedLessonSectionId.value,
)?.title || '')
const currentAiScopeKey = computed(() => [props.courseId, selectedLessonId.value, selectedLessonSectionId.value].join(':'))
const lessonReferenceTargetId = computed(() => (
  activeStage.value === 'lesson' && selectedLessonId.value
    ? `lesson-plan:${selectedLessonId.value}`
    : ''
))
const selectedLessonIndex = computed(() => lessonStore.lessons.findIndex(item => item.lesson_unit_id === selectedLessonId.value))
const previousLesson = computed(() => selectedLessonIndex.value > 0 ? lessonStore.lessons[selectedLessonIndex.value - 1] : undefined)
const previousLessonReferenceTargetId = computed(() => (
  activeStage.value === 'lesson' && previousLesson.value?.lesson_unit_id
    ? `lesson-plan:${previousLesson.value.lesson_unit_id}`
    : ''
))
const nextLesson = computed(() => selectedLessonIndex.value >= 0 && selectedLessonIndex.value < lessonStore.lessons.length - 1 ? lessonStore.lessons[selectedLessonIndex.value + 1] : undefined)
const workingLessonRevision = computed(() => selectedLesson.value?.plan.revisions.find(item => item.revision_id === selectedLesson.value?.plan.working_revision_id))
const confirmedLessonRevision = computed(() => selectedLesson.value?.plan.revisions.find(item => item.revision_id === selectedLesson.value?.plan.confirmed_revision_id))
const aiCollaborationBusy = computed(() => teacherLessonAiBusy(aiPhase.value))
const aiCandidatePending = computed(() => Boolean(aiCandidate.value))
const aiCandidateFieldLabels = computed(() => {
  const labels: Record<string, string> = {
    learning_objective: t('courseWorkbench.lessonDocument.objective', '教学目标'),
    key_points: t('courseWorkbench.lessonDocument.keyPoints', '教学重点'),
    key_difficulties: t('courseWorkbench.lessonDocument.difficulties', '教学难点'),
    teaching_modules: t('courseWorkbench.lessonDocument.flow', '教学流程'),
    in_class_checks: t('courseWorkbench.lessonDocument.check', '课堂检查'),
    homework: t('courseWorkbench.lessonDocument.homework', '课后作业'),
    teaching_notes: t('courseWorkbench.lessonDocument.notes', '教学备注'),
  }
  return changedTeacherLessonFields(
    workingLessonRevision.value?.plan,
    aiCandidate.value?.plan,
    selectedLessonSectionId.value,
  ).map(field => labels[field] || field)
})
const lessonPlanConfirmed = computed(() => Boolean(workingLessonRevision.value?.revision_id && workingLessonRevision.value.revision_id === selectedLesson.value?.plan.confirmed_revision_id))
const scriptConfirmed = computed(() => Boolean(selectedLesson.value?.script?.confirmed))
const generationTask = computed(() => generationStore.getTask(props.courseId))
const taskStatus = computed(() => String(generationTask.value?.status || ''))
const taskInFlight = computed(() => ['pending', 'running'].includes(taskStatus.value))
const taskPaused = computed(() => taskStatus.value === 'paused')
const outlineShapeAwaitingReview = computed(() => taskStatus.value === 'waiting_for_review' && generationTask.value?.currentPhase === 'outline_shape_ready')
const outlineAwaitingReview = computed(() => taskStatus.value === 'waiting_for_review' && !outlineShapeAwaitingReview.value)
const outlineGatePending = computed(() => outlineShapeAwaitingReview.value || outlineAwaitingReview.value)
const generationFailed = computed(() => generationTask.value
  ? ['error', 'failed', 'conflict'].includes(taskStatus.value)
  : generationStore.generationStatus === 'error')
const generationRunning = computed(() => taskInFlight.value)
const showStreaming = computed(() => activeStage.value === 'foundation'
  && !outlineShapeAwaitingReview.value
  && !outlineAwaitingReview.value
  && (generationRequested.value || taskInFlight.value || taskPaused.value || generationFailed.value))
const hasOutline = computed(() => courseStore.nodes.some(node => Number(node.node_level || 0) <= 2))
const outlinePreviewNodes = computed(() => courseStore.nodes.filter(node => Number(node.node_level || 0) <= 2).slice(0, 24))
const visibleStreamNodes = computed(() => courseStore.nodes.filter(node => node.node_content || generationStore.streamingContent[node.node_id]).slice(0, 20))
const hasStreamedBody = computed(() => visibleStreamNodes.value.length > 0)
const outlineGrowth = computed<Record<string, any> | null>(() => {
  const value = generationTask.value?.phaseDetail?.outline_growth
  return value && typeof value === 'object' ? value as Record<string, any> : retainedOutlineGrowth.value
})
const outlineGrowthChapters = computed<Record<string, any>[]>(() => Array.isArray(outlineGrowth.value?.chapters) ? outlineGrowth.value!.chapters as Record<string, any>[] : [])
const outlineShapeRevision = computed(() => String(generationTask.value?.phaseDetail?.skeleton_revision_id || ''))
const shapeCountsValid = computed(() => chapterSectionCounts.value.length === outlineGrowthChapters.value.length && chapterSectionCounts.value.every(count => Number.isInteger(Number(count)) && Number(count) >= 1 && Number(count) <= 100))
const showOutlineWorkspace = computed(() => activeStage.value === 'foundation'
  && !showStreaming.value
  && !outlineShapeAwaitingReview.value
  && (outlineAwaitingReview.value || hasOutline.value || editingOutline.value))
const generationProgress = computed(() => Math.max(2, Number(generationTask.value?.progress || generationStore.generationProgress || 0)))
const currentGenerationLabel = computed(() => generationTask.value?.currentStep || generationStore.currentGeneratingNode || t('courseWorkbench.waitingForContent', 'AI 正在建立课程结构…'))
const generationError = computed(() => generationFailed.value ? String(generationTask.value?.error || generationStore.failureReport?.failed_nodes?.[0]?.error || t('courseWorkbench.generationFailed', '生成中断，可以从当前结果重试。')) : '')
const generationErrorPresentation = computed(() => generationError.value ? toAppError(generationError.value, {
  title: t('courseWorkbench.outlineGenerationFailed', '课程大纲生成失败'),
  fallback: t('courseWorkbench.generationFailed', '生成中断，可以从当前结果重试。'),
  code: String(generationTask.value?.errorCode || ''),
  requestId: String(generationTask.value?.id || ''),
}) : null)
const lessonJob = computed(() => selectedLessonId.value ? lessonStore.latestJobByLesson(selectedLessonId.value) : undefined)
const lessonGenerationActive = computed(() => ['pending', 'running'].includes(String(lessonJob.value?.status || '')))
const lessonGenerationFailed = computed(() => lessonJob.value?.status === 'failed')
const lessonGenerationProgress = computed(() => Math.max(3, Number(lessonJob.value?.progress || 0)))
const lessonGenerationError = computed(() => String(lessonJob.value?.error?.message || lessonStore.error || ''))
const lessonGenerationErrorPresentation = computed(() => lessonGenerationError.value ? toAppError(
  lessonJob.value?.error || lessonGenerationError.value,
  {
    title: t('courseWorkbench.lessonGenerationFailed', '本讲教案生成失败'),
    fallback: lessonGenerationError.value,
    code: String(lessonJob.value?.error?.code || ''),
    requestId: String(lessonJob.value?.id || ''),
  },
) : null)
const lessonStreamSegments = computed(() => lessonPlanStreamSegments(lessonJob.value?.stream_batches))
const selectedLessonQuestionNodeIds = computed(() => selectedLesson.value?.sections.map(item => item.section_node_id).filter(Boolean) || [])
const readyStageCount = computed(() => stages.value.filter(item => stageReady(item.id)).length)
const lessonStageBlocked = computed(() => (
  lessonStore.loading
  || outlineGatePending.value
  || !lessonStore.lessons.length
))
const lessonPrerequisiteState = computed(() => {
  if (lessonStore.loading) return {
    kind: 'loading',
    title: t('courseWorkbench.lessonPrerequisite.loading', '正在读取大纲课次'),
    detail: t('courseWorkbench.lessonPrerequisite.loadingHelp', '已生成内容不会重复创建。'),
    action: '',
  }
  if (outlineShapeAwaitingReview.value) return {
    kind: 'review',
    title: t('courseWorkbench.lessonPrerequisite.shapeReview', '大章节已生成，等待确认小节数'),
    detail: t('courseWorkbench.lessonPrerequisite.shapeReviewHelp', '完成这一步后，系统会继续生成完整大纲。'),
    action: t('courseWorkbench.lessonPrerequisite.continueOutline', '继续完善大纲'),
  }
  if (outlineAwaitingReview.value) return {
    kind: 'review',
    title: t('courseWorkbench.lessonPrerequisite.outlineReview', '课程大纲已生成，等待确认'),
    detail: t('courseWorkbench.lessonPrerequisite.outlineReviewHelp', '确认后会直接形成可选择的课次，不需要重新生成大纲。'),
    action: t('courseWorkbench.lessonPrerequisite.reviewOutline', '查看并确认大纲'),
  }
  if (lessonStore.error && !lessonStore.lessons.length) return {
    kind: 'error',
    title: t('courseWorkbench.lessonPrerequisite.loadFailed', '课次读取失败'),
    detail: lessonStore.error,
    action: t('courseWorkbench.lessonPrerequisite.retry', '重新读取课次'),
  }
  if (hasOutline.value || lessonStore.outlineRevisionId) return {
    kind: 'sync',
    title: t('courseWorkbench.lessonPrerequisite.syncPending', '课程大纲已存在，课次尚未同步'),
    detail: t('courseWorkbench.lessonPrerequisite.syncPendingHelp', '重新读取会沿用当前大纲，不会重复生成内容。'),
    action: t('courseWorkbench.lessonPrerequisite.retry', '重新读取课次'),
  }
  return {
    kind: 'missing',
    title: t('courseWorkbench.lessonPrerequisite.missing', '尚未生成可用的课程大纲'),
    detail: t('courseWorkbench.lessonPrerequisite.missingHelp', '先生成大纲，再在当前页面确认后进入教案。'),
    action: t('courseWorkbench.lessonPrerequisite.createOutline', '生成课程大纲'),
  }
})
const lessonPrerequisiteError = computed(() => (
  lessonPrerequisiteState.value.kind === 'error'
    ? toAppError(lessonStore.error, {
        title: lessonPrerequisiteState.value.title,
        fallback: lessonPrerequisiteState.value.detail,
      })
    : null
))
const shapeConfirmErrorPresentation = computed(() => shapeConfirmError.value ? toAppError(shapeConfirmError.value, {
  title: t('courseWorkbench.shapeReview.failedTitle', '课程大纲继续生成失败'),
  fallback: t('courseWorkbench.shapeReview.failed', '无法继续生成，请稍后重试'),
}) : null)

function stageReady(stage: CoreStageId) { if (stage === 'foundation') return hasOutline.value; if (stage === 'lesson') return lessonStore.lessons.some(item => Boolean(item.plan.confirmed_revision_id)); if (stage === 'question-bank') return questionBankReady.value; if (stage === 'script') return lessonStore.lessons.some(item => item.script?.confirmed); return lessonStore.lessons.some(item => item.plan.ppt_assets.some(asset => asset.engine === 'slide_deck_v6' && asset.source_state === 'current')) }
function nodeContent(node: any) { return generationStore.streamingContent[node.node_id] || node.node_content || '' }
function stopGeneration() { void generationStore.stopGeneration() }
function appendAiMessage(role: TeacherLessonAiMessage['role'], kind: TeacherLessonAiMessage['kind'], text: string) {
  aiMessageSequence.value += 1
  aiMessages.value.push({ id: `lesson-ai-${aiMessageSequence.value}`, role, kind, text })
}
function transitionAi(event: TeacherLessonAiEvent) {
  aiPhase.value = transitionTeacherLessonAiPhase(aiPhase.value, event)
}
function appendRestoredAiCandidate() {
  appendAiMessage(
    'assistant',
    'text',
    t('courseWorkbench.aiCollaboration.restoredCandidate', '已恢复上次未处理的修改候选，请核对左侧高亮内容。'),
  )
  appendAiMessage(
    'assistant',
    'candidate',
    t('courseWorkbench.aiCollaboration.candidateSummary', '候选已显示在左侧，请核对高亮内容。'),
  )
}
function resetAiSession() {
  aiMessages.value = []
  aiClarificationOptions.value = []
  lastAiOperation.value = ''
  aiSessionScopeKey.value = currentAiScopeKey.value
  transitionAi({ type: 'RESET' })
  if (aiCandidatePending.value) {
    appendRestoredAiCandidate()
    transitionAi({ type: 'CANDIDATE_RESTORED' })
  } else {
    appendAiMessage(
      'assistant',
      'text',
      t('courseWorkbench.aiCollaboration.welcome', '告诉我你想调整什么；要求不够明确时，我会先向你确认。'),
    )
  }
}
function openLessonAiCollaboration() {
  if (!selectedLesson.value || !workingLessonRevision.value) return
  if (aiSessionScopeKey.value !== currentAiScopeKey.value || !aiMessages.value.length) resetAiSession()
  if (aiCandidatePending.value && !aiMessages.value.some(message => message.kind === 'candidate')) {
    appendRestoredAiCandidate()
    transitionAi({ type: 'CANDIDATE_RESTORED' })
  }
  aiCollaborationOpen.value = true
  transitionAi({ type: 'OPEN', candidatePending: aiCandidatePending.value })
}
function closeLessonAiCollaboration() {
  aiCollaborationOpen.value = false
}
function buildAiInstruction(): string {
  return buildTeacherLessonAiInstruction(aiMessages.value, {
    courseTitle: props.courseTitle,
    lessonTitle: selectedLesson.value?.title || '',
    sectionTitle: selectedLessonSectionTitle.value,
    referenceCount: activeReferences.value.length,
  })
}
function replacePreviousCandidateMessage() {
  const previousCandidate = [...aiMessages.value].reverse().find(message => message.kind === 'candidate')
  if (!previousCandidate) return
  previousCandidate.kind = 'receipt'
  previousCandidate.text = t('courseWorkbench.aiCollaboration.replacedReceipt', '上一版候选已由本轮要求替换。')
}
async function generateAiCandidateFromConversation() {
  if (aiCollaborationBusy.value || !lessonPlanDocument.value) return
  lastAiOperation.value = 'generate'
  aiClarificationOptions.value = []
  transitionAi({ type: 'GENERATE' })
  if (aiCandidatePending.value) {
    replacingAiCandidate.value = true
    const discarded = await lessonPlanDocument.value.resolveAiCandidate(false).finally(() => {
      replacingAiCandidate.value = false
    })
    if (!discarded) return
    replacePreviousCandidateMessage()
  }
  const candidate = await lessonPlanDocument.value.requestAiCandidate(buildAiInstruction())
  if (!candidate) {
    if (aiPhase.value !== 'error') transitionAi({ type: 'FAIL' })
    return
  }
  aiCandidate.value = candidate
  appendAiMessage(
    'assistant',
    'candidate',
    t('courseWorkbench.aiCollaboration.candidateSummary', '候选已显示在左侧，请核对高亮内容。'),
  )
  transitionAi({ type: 'CANDIDATE_READY' })
  lastAiOperation.value = ''
  lessonPlanDocument.value.focusCandidate()
}
async function handleAiRequest(instruction: string) {
  const request = instruction.trim()
  if (!request || aiCollaborationBusy.value || !lessonPlanDocument.value) return
  appendAiMessage('user', 'text', request)
  if (assessTeacherLessonRequest(request) === 'clarify') {
    aiClarificationOptions.value = [
      t('courseWorkbench.aiCollaboration.quickObjective', '让目标可观察'),
      t('courseWorkbench.aiCollaboration.quickActivity', '增加互动与检查'),
      t('courseWorkbench.aiCollaboration.quickPacing', '压缩讲授，突出活动'),
    ]
    appendAiMessage(
      'assistant',
      'text',
      t('courseWorkbench.aiCollaboration.clarificationQuestion', '为了避免整段重写，你希望优先调整哪一部分？'),
    )
    lastAiOperation.value = ''
    transitionAi({ type: 'ASK_CLARIFICATION' })
    return
  }
  await generateAiCandidateFromConversation()
}
async function handleAiClarification(option: string) {
  if (!option || aiCollaborationBusy.value) return
  appendAiMessage('user', 'text', option)
  await generateAiCandidateFromConversation()
}
function handleAiCandidateChange(candidate: TeacherLessonPlanCandidate | null) {
  aiCandidate.value = candidate
  if (candidate && aiCollaborationOpen.value && aiPhase.value !== 'generating') {
    transitionAi({ type: 'CANDIDATE_RESTORED' })
  }
}
function handleAiResolving(result: { accept: boolean }) {
  lastAiOperation.value = result.accept ? 'accept' : 'reject'
  transitionAi({ type: result.accept ? 'ACCEPT' : 'REJECT' })
}
function handleAiResolved(result: { accept: boolean }) {
  aiCandidate.value = null
  if (replacingAiCandidate.value) return
  transitionAi({ type: 'RESOLVED' })
  lastAiOperation.value = ''
  const receipt = result.accept
    ? t('courseWorkbench.aiCollaboration.acceptedReceipt', '候选已采用，并形成新的教案工作修订。')
    : t('courseWorkbench.aiCollaboration.rejectedReceipt', '候选已放弃，当前教案保持不变。')
  const candidateMessage = [...aiMessages.value].reverse().find(message => message.kind === 'candidate')
  if (candidateMessage) {
    candidateMessage.kind = 'receipt'
    candidateMessage.text = receipt
  } else {
    appendAiMessage('assistant', 'receipt', receipt)
  }
}
function handleAiError(error: string) {
  if (!error || aiMessages.value.at(-1)?.text === error) return
  transitionAi({ type: 'FAIL' })
  appendAiMessage('assistant', 'error', error)
}
async function resolveAiCandidate(accept: boolean) {
  if (!lessonPlanDocument.value || !aiCandidatePending.value || aiCollaborationBusy.value) return
  lastAiOperation.value = accept ? 'accept' : 'reject'
  transitionAi({ type: accept ? 'ACCEPT' : 'REJECT' })
  const resolved = await lessonPlanDocument.value.resolveAiCandidate(accept)
  if (!resolved && aiPhase.value !== 'error') transitionAi({ type: 'FAIL' })
}
async function retryAiAction() {
  if (aiCollaborationBusy.value || !lastAiOperation.value) return
  if (lastAiOperation.value === 'accept' && aiCandidatePending.value) {
    await resolveAiCandidate(true)
    return
  }
  if (lastAiOperation.value === 'reject' && aiCandidatePending.value) {
    await resolveAiCandidate(false)
    return
  }
  await generateAiCandidateFromConversation()
}
function focusAiCandidate() {
  lessonPlanDocument.value?.focusCandidate()
}
function clampAiPanePercent(value: number) {
  aiPanePercent.value = Math.min(46, Math.max(32, Math.round(value)))
}
function handleAiPanePointerMove(event: PointerEvent) {
  const bounds = workbenchRoot.value?.getBoundingClientRect()
  if (!bounds?.width) return
  clampAiPanePercent((bounds.right - event.clientX) / bounds.width * 100)
}
function stopAiPaneResize() {
  window.removeEventListener('pointermove', handleAiPanePointerMove)
  window.removeEventListener('pointerup', stopAiPaneResize)
}
function startAiPaneResize(event: PointerEvent) {
  event.preventDefault()
  window.addEventListener('pointermove', handleAiPanePointerMove)
  window.addEventListener('pointerup', stopAiPaneResize)
}
function resizeAiPaneWithKeyboard(event: KeyboardEvent) {
  if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return
  event.preventDefault()
  clampAiPanePercent(aiPanePercent.value + (event.key === 'ArrowLeft' ? 2 : -2))
}
async function toggleOutlineEditing() {
  if (!editingOutline.value) {
    editingOutline.value = true
    return
  }
  if (finishingOutline.value) return
  finishingOutline.value = true
  try {
    const finished = await outlineEditor.value?.finishEditing()
    if (finished !== false) editingOutline.value = false
  } finally {
    finishingOutline.value = false
  }
}
function resolveLessonPrerequisite() {
  if (outlineGatePending.value) {
    activeStage.value = 'foundation'
    return
  }
  if (lessonStore.error || hasOutline.value || lessonStore.outlineRevisionId) {
    void lessonStore.load(props.courseId).catch(() => undefined)
    return
  }
  activeStage.value = 'foundation'
}
function generationBindings(references: CourseReferenceItem[]) { return references.map(item => { const web = item.origin === 'web_search'; const highTrust = item.source_metadata?.credibility === 'high'; return { asset_id: item.material_asset_id, purpose: item.role === 'primary' ? 'content_source' as const : web && !highTrust ? 'weak_context' as const : 'supplement' as const, priority: item.role === 'primary' ? 'core' as const : web && !highTrust ? 'weak' as const : 'supporting' as const, authority: item.role === 'primary' ? 'primary' as const : web && !highTrust ? 'context_only' as const : 'secondary' as const, usage_policy: item.role === 'primary' ? 'must_use' as const : web && !highTrust ? 'optional' as const : 'prefer' as const, reuse_policy: item.reuse_policy || 'reference_only' as const, rights_basis: item.rights_basis || (web ? 'license_unknown' as const : 'teacher_asserted' as const), source_metadata: item.source_metadata || {}, source_label: item.source_label || item.filename } }) }
async function saveRelationships(targetId: string, targetType: string, label: string) { const refs = activeReferences.value; const packageId = refs[0]?.package_id || String((await http.get('/api/teacher-course-spaces', teacherRequestConfig({ params: { course_id: props.courseId }, silentError: true }))).data?.[0]?.package_id || ''); if (!packageId) return; await http.put(`/api/teacher-course-spaces/${packageId}/relationships`, { target_id: targetId, target_type: targetType, target_label: label, sources: refs.map(item => ({ source_asset_id: item.asset_id, role: item.role })) }, teacherRequestConfig({ silentError: true })) }
async function submitFoundation() { generationRequested.value = true; try { const baseTeacherBrief = { ...(props.generationOptions.teacher_course_brief || {}) }; delete baseTeacherBrief.chapter_count; delete baseTeacherBrief.section_count; await saveRelationships('managed:outline', 'outline', t('courseFiles.names.outline', '课程大纲')); emit('generateOutline', { subject: props.courseTitle, options: { ...props.generationOptions, requirements: [props.generationOptions.requirements, foundation.requirements].filter(Boolean).join('\n'), course_intent: { schema_version: 'course_intent_v1', type: 'systematic', learning_goal: foundation.goal }, teacher_course_brief: { ...baseTeacherBrief, schema_version: 'teacher_course_brief_v1', target_audience: baseTeacherBrief.target_audience || '大学生', total_class_hours: foundation.totalHours, lesson_duration_minutes: baseTeacherBrief.lesson_duration_minutes || 45, teaching_context: baseTeacherBrief.teaching_context || 'classroom' }, material_bindings: generationBindings(activeReferences.value) }, references: activeReferences.value }) } catch { generationRequested.value = false } }
async function confirmOutlineShape() { if (!shapeCountsValid.value || shapeConfirming.value) return; shapeConfirming.value = true; shapeConfirmError.value = null; try { const counts = chapterSectionCounts.value.map(count => Number(count)); await courseWorkspaceStore.confirmOutlineShape(props.courseId, counts); generationRequested.value = true; await generationStore.fetchGlobalTasks() } catch (error: any) { shapeConfirmError.value = error } finally { shapeConfirming.value = false } }
async function generateLessonPlan() { if (!selectedLesson.value || lessonGenerationActive.value) return; lessonBusy.value = true; lessonConfirmError.value = ''; try { await saveRelationships(`lesson-plan:${selectedLessonId.value}`, 'lesson_plan', selectedLesson.value.title); const primary = activeReferences.value.find(item => item.role === 'primary'); await lessonStore.generateLesson(props.courseId, selectedLessonId.value, primary ? { packageId: primary.package_id, assetId: primary.asset_id } : undefined, lessonRequirements.value, activeReferences.value.map(item => item.material_asset_id)) } catch { /* The store keeps the teacher-visible reason. */ } finally { lessonBusy.value = false } }
async function confirmLessonPlan() { const revision = workingLessonRevision.value?.revision_id; if (!selectedLesson.value || !revision || lessonPlanConfirmed.value || lessonConfirming.value) return; lessonConfirming.value = true; lessonConfirmError.value = ''; try { await lessonStore.confirm(props.courseId, selectedLessonId.value, revision); activeStage.value = 'question-bank' } catch { lessonConfirmError.value = lessonStore.error || t('courseWorkbench.lessonConfirmFailed', '本讲教案确认失败，请重试。') } finally { lessonConfirming.value = false } }
function selectLesson(lessonId?: string) {
  if (!lessonId) return
  if (aiCandidatePending.value && selectedLessonId.value !== lessonId) return
  const lesson = lessonStore.lessons.find(item => item.lesson_unit_id === lessonId)
  const lessonChanged = selectedLessonId.value !== lessonId
  selectedLessonId.value = lessonId
  if (lessonChanged || !lesson?.sections.some(section => section.section_node_id === selectedLessonSectionId.value)) {
    selectedLessonSectionId.value = lesson?.sections[0]?.section_node_id || ''
  }
}
function selectLessonSection(lessonId: string, sectionId: string) {
  if (aiCandidatePending.value && selectedLessonSectionId.value !== sectionId) return
  selectedLessonId.value = lessonId
  selectedLessonSectionId.value = sectionId
}
function lessonGenerationState(lesson: any): 'pending' | 'generating' | 'review' | 'confirmed' | 'failed' {
  const jobStatus = String(lessonStore.latestJobByLesson(lesson.lesson_unit_id)?.status || '')
  if (['pending', 'running'].includes(jobStatus)) return 'generating'
  if (jobStatus === 'failed') return 'failed'
  if (lesson.plan?.confirmed_revision_id) return 'confirmed'
  if (lesson.plan?.working_revision_id || ['completed', 'completed_with_warnings'].includes(jobStatus)) return 'review'
  return 'pending'
}
function lessonGenerationStateLabel(lesson: any): string {
  const state = lessonGenerationState(lesson)
  const labels = {
    pending: t('courseWorkbench.lessonOutline.status.pending', '未生成'),
    generating: t('courseWorkbench.lessonOutline.status.generating', '生成中'),
    review: t('courseWorkbench.lessonOutline.status.review', '待确认'),
    confirmed: t('courseWorkbench.lessonOutline.status.confirmed', '已确认'),
    failed: t('courseWorkbench.lessonOutline.status.failed', '生成失败'),
  }
  return labels[state]
}
async function handleScriptSaved() { scriptConfirmError.value = ''; await lessonStore.load(props.courseId) }
async function generateScript(requirements: string) {
  if (!selectedLesson.value || !confirmedLessonRevision.value || scriptGenerating.value) return
  scriptGenerating.value = true
  scriptGenerationError.value = ''
  scriptConfirmError.value = ''
  try {
    await saveRelationships(`script:${selectedLessonId.value}`, 'script', `${selectedLesson.value.title} 讲稿`)
    await lessonStore.generateScript(
      props.courseId,
      selectedLessonId.value,
      requirements,
      activeReferences.value.map(item => item.material_asset_id),
    )
  } catch {
    scriptGenerationError.value = lessonStore.error || t('courseWorkbench.scriptGenerationFailed', '本讲讲稿生成失败，请重试。')
  } finally {
    scriptGenerating.value = false
  }
}
async function confirmScript() {
  const revision = selectedLesson.value?.script.current_revision_id
  if (!selectedLesson.value || !revision || scriptConfirmed.value || scriptConfirming.value) return
  scriptConfirming.value = true
  scriptConfirmError.value = ''
  try {
    await lessonStore.confirmScript(props.courseId, selectedLessonId.value, revision)
    activeStage.value = 'ppt'
  } catch {
    scriptConfirmError.value = lessonStore.error || t('courseWorkbench.scriptConfirmFailed', '本讲讲稿确认失败，请重试。')
  } finally {
    scriptConfirming.value = false
  }
}
async function openPptWorkspace() {
  if (!selectedLesson.value || !confirmedLessonRevision.value || !scriptConfirmed.value) return
  await saveRelationships(`ppt-v6:${selectedLessonId.value}`, 'ppt', `${selectedLesson.value.title} PPT`)
  window.location.assign(`/course/${props.courseId}/ppt?lesson=${selectedLessonId.value}`)
}
async function handleCompanionSaved(document: { document_id: string; title: string; revision_id: string }) { await saveRelationships(`companion-document:${document.document_id}`, 'companion_document', document.title) }
function handleInlineOutlineConfirmed() { editingOutline.value = false; emit('outlineConfirmed') }
async function loadQuestionBankStatus() { if (!props.courseId) return; try { const response = await http.get(`/api/courses/${props.courseId}/question-bank`, teacherRequestConfig({ silentError: true })); questionBankReady.value = Number(response.data?.total || 0) > 0 } catch { questionBankReady.value = false } }

watch(() => props.generationOptions, options => { const intent = options.course_intent as any; const brief = options.teacher_course_brief; foundation.goal = String(intent?.learning_goal || options.requirements || props.courseTitle); foundation.totalHours = Number(brief?.total_class_hours || 32); foundation.requirements = String(options.requirements || '') }, { immediate: true, deep: true })
watch([outlineShapeAwaitingReview, outlineShapeRevision], ([waiting, revision]) => { if (!waiting || !revision || loadedShapeRevision.value === revision) return; chapterSectionCounts.value = outlineGrowthChapters.value.map(chapter => Math.max(1, Number(chapter.section_count || 1))); loadedShapeRevision.value = revision; shapeConfirmError.value = null }, { immediate: true })
watch(() => generationTask.value?.phaseDetail?.outline_growth, value => { if (value && typeof value === 'object') retainedOutlineGrowth.value = JSON.parse(JSON.stringify(value)) as Record<string, any> }, { immediate: true, deep: true })
watch(outlineAwaitingReview, waiting => { if (waiting) void courseStore.refreshGenerationPreview(props.courseId, 'teacher') }, { immediate: true })
watch(() => props.initialStage, stage => { activeStage.value = stage })
watch(() => props.initialLessonId, lessonId => { if (lessonId) selectedLessonId.value = lessonId })
watch(activeStage, stage => { if (stage !== 'foundation') editingOutline.value = false; if (stage !== 'lesson') closeLessonAiCollaboration(); if (workbenchCenter.value) workbenchCenter.value.scrollTop = 0 }, { flush: 'post' })
watch(() => lessonStore.lessons, lessons => {
  if (props.initialLessonId && lessons.some(item => item.lesson_unit_id === props.initialLessonId)) {
    selectedLessonId.value = props.initialLessonId
  } else if (!lessons.some(item => item.lesson_unit_id === selectedLessonId.value)) {
    selectedLessonId.value = lessons[0]?.lesson_unit_id || ''
  }
  const lesson = lessons.find(item => item.lesson_unit_id === selectedLessonId.value)
  if (!lesson) return
  if (!lesson.sections.some(section => section.section_node_id === selectedLessonSectionId.value)) {
    selectedLessonSectionId.value = lesson.sections[0]?.section_node_id || ''
  }
}, { immediate: true, deep: true })
watch(selectedLessonId, (lessonId, previousLessonId) => {
  if (previousLessonId && lessonId !== previousLessonId) closeLessonAiCollaboration()
  lessonConfirmError.value = ''
  scriptGenerationError.value = ''
  scriptConfirmError.value = ''
  const lesson = lessonStore.lessons.find(item => item.lesson_unit_id === lessonId)
  if (!lesson) {
    selectedLessonSectionId.value = ''
    return
  }
  if (previousLessonId !== lessonId || !lesson.sections.some(section => section.section_node_id === selectedLessonSectionId.value)) {
    selectedLessonSectionId.value = lesson.sections[0]?.section_node_id || ''
  }
}, { immediate: true })
watch(() => props.courseId, () => { void loadQuestionBankStatus() }, { immediate: true })
watch(taskStatus, status => { if (!['pending', 'running'].includes(status)) generationRequested.value = false })
onBeforeUnmount(stopAiPaneResize)
</script>

<style scoped>
.teacher-workbench{height:100%;min-height:0;display:grid;grid-template-columns:210px minmax(520px,1fr) 310px;overflow:hidden;background:#f3f5f9}.stage-rail{min-height:0;display:flex;flex-direction:column;border-right:1px solid #e4e9f1;background:#fff}.stage-rail>header{display:grid;gap:4px;padding:21px 18px 16px}.stage-rail>header strong{color:#1f2a40;font-size:15px}.stage-rail>header small{color:#64748b;font-size:12px}.stage-rail nav{display:grid;gap:4px;padding:4px 9px}.stage-rail nav button{min-height:54px;display:grid;grid-template-columns:26px 22px minmax(0,1fr) 18px;align-items:center;gap:8px;padding:8px 10px;border:0;border-radius:10px;color:#64748b;background:transparent;text-align:left;cursor:pointer}.stage-rail nav button:hover{background:#f6f7fb}.stage-rail nav button.active{color:#4338ca;background:#eef0ff}.stage-rail nav button>span{font-size:15px;font-weight:800}.stage-rail nav strong{min-width:0;color:#334155;font-size:13px}.stage-rail nav button.active strong{color:#3730a3}.stage-rail nav button>svg:last-child{color:#16a34a}.stage-rail>footer{display:grid;grid-template-columns:auto minmax(0,1fr);align-items:center;gap:9px;margin-top:auto;padding:16px 18px;color:#64748b;font-size:12px}.stage-rail>footer>div{height:4px;overflow:hidden;border-radius:2px;background:#e8ecf3}.stage-rail>footer i{height:100%;display:block;background:#5b57e8}.workbench-center{min-width:0;min-height:0;overflow:auto;padding:24px 26px 52px}.center-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;max-width:860px;margin:0 auto 18px}.center-heading>div{display:grid;gap:4px}.center-heading small{color:#6366f1;font-size:11px;font-weight:800}.center-heading h2{margin:0;color:#172033;font-size:24px;letter-spacing:-.018em}.center-heading>button,.formal-surface>header button,.generation-surface>header button{min-height:36px;display:flex;align-items:center;gap:7px;padding:0 11px;border:1px solid #d7dde7;border-radius:8px;color:#475569;background:#fff;font-size:12px;font-weight:700;cursor:pointer}.stage-form,.formal-surface,.generation-surface,.lesson-stage{max-width:860px;margin:0 auto;border:1px solid #e0e6ef;border-radius:14px;background:#fff;box-shadow:0 10px 30px rgba(30,41,59,.05)}.stage-form{display:grid;gap:20px;padding:26px}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.form-field{display:grid;gap:8px}.form-field>span,.lesson-selector>span{color:#334155;font-size:13px;font-weight:700}.form-field b{color:#dc2626}.form-field input,.form-field select,.form-field textarea,.lesson-selector select{width:100%;min-height:44px;padding:10px 11px;border:1px solid #cfd7e3;border-radius:8px;outline:0;color:#172033;background:#fff;font:inherit;font-size:13px}.form-field textarea{resize:vertical;line-height:1.6}.form-field input:focus,.form-field select:focus,.form-field textarea:focus,.form-field textarea:focus,.lesson-selector select:focus{border-color:#5b57e8;box-shadow:0 0 0 3px rgba(91,87,232,.11)}.stage-form>footer{display:flex;align-items:center;justify-content:space-between;gap:16px;padding-top:2px}.stage-form>footer>span{color:#64748b;font-size:12px}.primary{min-height:42px;display:flex;align-items:center;gap:7px;padding:0 15px;border:1px solid #514bdc;border-radius:8px;color:#fff;background:#514bdc;font-size:13px;font-weight:750;cursor:pointer;box-shadow:0 7px 18px rgba(81,75,220,.16)}.primary:disabled{opacity:.48;cursor:not-allowed}.generation-surface{overflow:hidden}.generation-surface>header,.formal-surface>header{min-height:64px;display:flex;align-items:center;justify-content:space-between;gap:16px;padding:0 20px;border-bottom:1px solid #e7ebf2}.generation-surface>header>div{display:flex;align-items:center;gap:10px;color:#4f46e5}.generation-surface>header span,.formal-surface>header>div{display:grid;gap:3px}.generation-surface>header strong,.formal-surface>header strong{color:#263147;font-size:13px}.generation-surface>header small,.formal-surface>header small{color:#64748b;font-size:11px}.generation-progress{height:3px;background:#e8ebf5}.generation-progress i{width:100%;height:100%;display:block;transform-origin:left;background:#5b57e8;transition:transform .25s ease-out}.stream-content,.formal-surface>article{max-height:calc(100vh - 260px);overflow:auto;padding:22px 28px 42px}.stream-content section,.formal-surface article section{margin-bottom:26px}.stream-content h3,.formal-surface h3{margin:0 0 10px;color:#202b40;font-size:17px}.stream-waiting{min-height:260px;display:flex;align-items:center;justify-content:center;gap:9px;color:#64748b;font-size:13px}.stream-caret{width:2px;height:18px;display:inline-block;background:#5b57e8;animation:blink .8s steps(1) infinite}.generation-error{margin:0;padding:12px 20px;color:#b91c1c;background:#fff1f2;font-size:12px}.generation-error button{border:0;color:inherit;background:transparent;font-weight:750;text-decoration:underline;cursor:pointer}.lesson-stage{padding:0 0 24px}.lesson-selector{display:grid;grid-template-columns:110px minmax(0,1fr);align-items:center;gap:14px;padding:18px 22px;border-bottom:1px solid #e7ebf2}.stage-form--lesson{border:0;box-shadow:none}.prerequisite,.empty-asset{min-height:260px;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:10px;color:#64748b;font-size:13px}.prerequisite strong{color:#334155}.prerequisite button{padding:7px 10px;border:1px solid #d7dde7;border-radius:7px;color:#4f46e5;background:#fff;font-weight:700;cursor:pointer}.lesson-formal{margin:20px 20px 0;border-radius:10px;box-shadow:none}.lesson-formal>article{max-height:calc(100vh - 360px)}.formal-surface ol{display:grid;gap:8px;padding-left:22px;color:#475569;font-size:13px}.spin{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}@keyframes blink{50%{opacity:0}}
.stage-form>footer{justify-content:flex-end}
.teacher-workbench.is-ai-collaboration{grid-template-columns:minmax(560px,1fr) 1px minmax(360px,var(--ai-pane-width));background:#eef1f6}.is-ai-collaboration>.workbench-center{padding:0;overflow:auto;background:#f3f5f9;scrollbar-width:thin;scrollbar-color:transparent transparent}.is-ai-collaboration>.workbench-center:hover{scrollbar-color:#cbd3df transparent}.is-ai-collaboration>.workbench-center::-webkit-scrollbar{width:6px}.is-ai-collaboration>.workbench-center::-webkit-scrollbar-thumb{border-radius:6px;background:transparent}.is-ai-collaboration>.workbench-center:hover::-webkit-scrollbar-thumb{background:#cbd3df}.is-ai-collaboration>.workbench-center>.center-heading{display:none}.is-ai-collaboration .lesson-stage{max-width:none;min-height:100%;margin:0;border:0;border-radius:0;box-shadow:none}.is-ai-collaboration .lesson-outline,.is-ai-collaboration .lesson-outline-toggle{display:none}.is-ai-collaboration .has-lesson-outline .lesson-workspace{display:block}.is-ai-collaboration .has-lesson-outline .lesson-stage-content{overflow:visible;border:0;border-radius:0;box-shadow:none}.is-ai-collaboration :deep(.lesson-document){min-height:100vh}.ai-workspace-resizer{position:relative;z-index:4;min-height:0;cursor:col-resize;background:#dfe4ec;touch-action:none}.ai-workspace-resizer::before{position:absolute;inset-block:0;inset-inline:-5px;content:""}.ai-workspace-resizer i{position:absolute;top:50%;left:50%;width:3px;height:34px;border-radius:3px;background:#818cf8;opacity:0;transform:translate(-50%,-50%);transition:opacity .14s ease}.ai-workspace-resizer:hover i,.ai-workspace-resizer:focus-visible i{opacity:1}.ai-workspace-resizer:focus-visible{outline:2px solid #818cf8;outline-offset:3px}
.stage-rail>header{display:block;padding:22px 18px 18px}.stage-rail>header .stage-rail-title{color:#1f2a40;font-size:18px;line-height:1.25}
.companion-entry{display:grid;gap:7px;margin:10px 9px 0;padding-top:14px;border-top:1px solid #e7ebf2}.companion-entry>small{padding:0 10px;color:#64748b;font-size:11px;font-weight:700}.companion-entry>button{min-height:50px;display:grid;grid-template-columns:22px minmax(0,1fr) 16px;align-items:center;gap:9px;padding:8px 10px;border:0;border-radius:10px;color:#64748b;background:transparent;text-align:left;cursor:pointer}.companion-entry>button:hover{background:#f6f7fb}.companion-entry>button.active{color:#4338ca;background:#eef0ff}.companion-entry strong{min-width:0;color:#334155;font-size:13px}.companion-entry>button.active strong{color:#3730a3}
.question-workbench-surface{max-width:860px;margin:0 auto;padding:0}
@media(max-width:1050px){.teacher-workbench{grid-template-columns:180px minmax(0,1fr) 280px}.workbench-center{padding-inline:18px}.stage-rail nav button{grid-template-columns:23px minmax(0,1fr)}.stage-rail nav button>svg,.stage-rail nav button>svg:last-child{display:none}}
@media(max-width:760px){.teacher-workbench{height:auto;min-height:100%;grid-template-columns:1fr;overflow:auto}.stage-rail{display:block;border-right:0;border-bottom:1px solid #e4e9f1}.stage-rail>header,.stage-rail>footer{display:none}.stage-rail nav{grid-template-columns:repeat(5,minmax(0,1fr));overflow:auto;padding:8px}.stage-rail nav button{min-width:108px;min-height:50px;grid-template-columns:22px minmax(0,1fr);padding:6px 8px}.workbench-center{overflow:visible;padding:18px 12px 30px}.center-heading h2{font-size:21px}.center-heading>button{font-size:0;width:38px;padding:0;justify-content:center}.stage-form{padding:19px 16px}.form-grid{grid-template-columns:1fr}.stage-form>footer{align-items:stretch;flex-direction:column}.primary{justify-content:center}.lesson-selector{grid-template-columns:1fr}.stream-content,.formal-surface>article{max-height:none;padding-inline:18px}.reference-tray{border-left:0;border-top:1px solid #e4e9f1}}
.stream-failed{color:#b91c1c;background:#fffafa}
.outline-shape-review>article{padding-bottom:20px}.shape-chapter-list{display:grid;gap:0;margin:0;padding:0!important;list-style:none}.shape-chapter-list li{min-height:72px;display:grid;grid-template-columns:34px minmax(0,1fr) auto;align-items:center;gap:12px;padding:10px 2px;border-bottom:1px solid #edf1f6}.shape-chapter-index{width:30px;height:30px;display:grid;place-items:center;border-radius:50%;color:#4f46e5;background:#eef2ff;font-size:11px;font-weight:800}.shape-chapter-list li>div{min-width:0;display:grid;gap:4px}.shape-chapter-list li>div strong{color:#263147;font-size:13px}.shape-chapter-list li>div small{color:#64748b;font-size:11px;line-height:1.45}.shape-chapter-list label{display:flex;align-items:center;gap:7px;color:#64748b;font-size:11px}.shape-chapter-list input{width:68px;min-height:36px;padding:6px 8px;border:1px solid #cfd7e3;border-radius:7px;outline:0;color:#172033;background:#fff;font:inherit;font-size:13px;text-align:center}.shape-chapter-list input:focus{border-color:#5b57e8;box-shadow:0 0 0 3px rgba(91,87,232,.11)}.outline-shape-review>footer{min-height:66px;display:flex;align-items:center;justify-content:space-between;gap:16px;padding:10px 20px;border-top:1px solid #e7ebf2}.outline-shape-review>footer>span{color:#64748b;font-size:12px}.shape-confirm-error{margin:12px 0 0}
.workbench-error{margin:12px 20px 16px}.prerequisite-error{margin:24px}.lesson-generation-surface{min-height:68px}.lesson-generation-error{margin:-4px 0 0}.lesson-stream-document{max-height:calc(100vh - 350px);overflow:auto;padding:26px 30px 44px}.lesson-stream-document>small{display:block;margin-bottom:9px;color:#6366f1;font-size:10px;font-weight:800;letter-spacing:.08em}.lesson-stream-document h3{margin:0 0 22px;color:#202b40;font-size:20px}.lesson-stream-document p{margin:0 0 15px;color:#475569;font-size:13px;line-height:1.85}.lesson-stream-document .stream-caret{height:15px;margin-left:3px;vertical-align:-2px}.lesson-stream-waiting{min-height:220px;display:flex;align-items:center;justify-content:center;color:#64748b;font-size:13px}
.workbench-center.is-outline-workspace{padding-bottom:24px}.outline-workspace{overflow:hidden}.outline-workspace>.inline-outline-review{width:100%;min-height:0}
.prerequisite{padding:28px;text-align:center}.prerequisite>span{max-width:480px;line-height:1.55}.prerequisite[data-state="review"]>svg{color:#4f46e5}.prerequisite[data-state="error"]>svg{color:#b91c1c}.prerequisite button{min-height:36px;padding:7px 11px}.prerequisite button:hover{border-color:#aaa7f4;background:#f7f7ff}.prerequisite button:focus-visible{outline:2px solid #5b57e8;outline-offset:2px}.prerequisite button:disabled{opacity:.5;cursor:not-allowed}
.workbench-center.is-lesson-workspace .center-heading,.workbench-center.is-lesson-workspace .lesson-stage{max-width:1160px}.lesson-workspace{min-width:0}.lesson-stage-content{min-width:0}.lesson-stage.has-lesson-outline{overflow:visible;border:0;border-radius:0;background:transparent;box-shadow:none}.has-lesson-outline .lesson-workspace{display:grid;grid-template-columns:206px minmax(0,1fr);gap:12px;transition:grid-template-columns .2s cubic-bezier(.2,.8,.2,1)}.has-lesson-outline .lesson-workspace.is-outline-collapsed{grid-template-columns:30px minmax(0,1fr)}.has-lesson-outline .lesson-stage-content{overflow:hidden;border:1px solid #e0e6ef;border-radius:14px;background:#fff;box-shadow:0 10px 30px rgba(30,41,59,.05)}.lesson-outline{min-width:0;align-self:start;display:grid;grid-template-columns:minmax(0,1fr) 28px;background:transparent}.is-outline-collapsed .lesson-outline{grid-template-columns:28px}.lesson-outline>nav{max-height:calc(100vh - 205px);overflow:auto;padding:0 4px 0 0}.lesson-outline-chapter{display:grid}.lesson-outline-chapter-button{min-height:48px;display:grid;grid-template-columns:9px minmax(0,1fr);align-items:center;gap:7px;width:100%;padding:6px 5px;border:0;color:#94a3b8;background:transparent;text-align:left;cursor:pointer}.lesson-outline-chapter-marker{width:5px;height:5px;justify-self:center;border:1px solid #b8c2d0;border-radius:50%;background:transparent}.lesson-outline-chapter-marker[data-state="generating"]{border-color:#6366f1;background:#6366f1;animation:lesson-pulse 1.4s ease-in-out infinite}.lesson-outline-chapter-marker[data-state="review"]{border-color:#d97706;background:#f59e0b}.lesson-outline-chapter-marker[data-state="confirmed"]{border-color:#16a34a;background:#22c55e}.lesson-outline-chapter-marker[data-state="failed"]{border-color:#dc2626;background:#ef4444}.lesson-outline-chapter-copy{min-width:0;display:grid;gap:2px}.lesson-outline-chapter-copy strong{overflow:hidden;color:#59677b;font-size:11.5px;font-weight:600;line-height:1.35;text-overflow:ellipsis;white-space:nowrap}.lesson-outline-chapter-copy small{color:#8a97aa;font-size:9.5px;line-height:1.3}.lesson-outline-chapter-button:hover strong{color:#334155}.lesson-outline-chapter-button.active .lesson-outline-chapter-marker{box-shadow:0 0 0 3px rgba(99,102,241,.12)}.lesson-outline-chapter-button.active strong{color:#373b71;font-weight:700}.lesson-outline-chapter-button.active small{color:#6366f1}.lesson-section-tabs{display:flex;min-width:0;overflow-x:auto;padding:0 18px;border-bottom:1px solid #e7ebf2;background:#fff;scrollbar-width:thin}.lesson-section-tabs button{min-height:56px;flex:0 0 auto;display:flex;align-items:center;gap:8px;padding:0 14px;border:0;color:#718096;background:transparent;cursor:pointer;white-space:nowrap}.lesson-section-tabs button>span{color:#94a3b8;font-size:10px;font-weight:750;font-variant-numeric:tabular-nums}.lesson-section-tabs button>strong{max-width:260px;overflow:hidden;font-size:12px;font-weight:600;text-overflow:ellipsis}.lesson-section-tabs button:hover{color:#475569}.lesson-section-tabs button.active{color:#3730a3;box-shadow:inset 0 -2px #5b57e8}.lesson-section-tabs button.active>span{color:#6366f1}.lesson-section-tabs button.active>strong{font-weight:700}.has-lesson-outline :deep(.lesson-document .document-title h3){overflow:visible;line-height:1.35;text-overflow:clip;white-space:normal}.has-lesson-outline :deep(.lesson-document .flow-table){overflow:auto}.has-lesson-outline :deep(.lesson-document .flow-row){min-width:800px}@keyframes lesson-pulse{50%{opacity:.42;transform:scale(.72)}}
.lesson-stage{padding:0;overflow:hidden}.lesson-navigator{min-height:54px;display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:center;gap:14px;padding:0 20px;border-bottom:1px solid #e7ebf2;background:#fbfcfe}.lesson-navigator>button{min-height:36px;display:flex;align-items:center;gap:5px;padding:0 11px;border:1px solid #d9dcfa;border-radius:8px;color:#4338ca;background:#f3f2ff;font-size:12px;font-weight:750;cursor:pointer;transition:color .16s ease,border-color .16s ease,background .16s ease,transform .16s ease}.lesson-navigator>button:hover:not(:disabled){transform:translateY(-1px);border-color:#aaa7f2;color:#3730a3;background:#eae8ff}.lesson-navigator>button:focus-visible{outline:3px solid rgba(91,87,232,.18);outline-offset:2px}.lesson-navigator>button:disabled{border-color:transparent;color:#94a3b8;background:transparent;opacity:.48;cursor:not-allowed}.lesson-selector{min-width:0;display:flex;align-items:center;justify-content:center;gap:0;padding:0;border:0}.lesson-selector>span{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}.lesson-selector select{width:min(100%,560px);min-height:36px;padding:0 34px 0 12px;border:0;border-radius:7px;color:#263147;background:transparent;font-size:13px;font-weight:750;text-align:center;box-shadow:none}.lesson-selector select:hover{background:#f3f5fa}.lesson-selector select:focus{background:#fff}.stage-form--lesson{border:0;border-radius:0;box-shadow:none}.stage-form>.lesson-form-actions{justify-content:flex-end}.stage-next-bar{min-height:64px;display:flex;align-items:center;justify-content:space-between;padding:12px 28px;border-top:1px solid #e8ecf2;background:#fbfcfe}.ppt-entry{min-height:180px;display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:center;gap:16px;padding:36px 28px}.ppt-entry>svg{color:#5b57e8}.ppt-entry>div{min-width:0;display:grid;gap:5px}.ppt-entry strong{color:#1f2a40;font-size:15px}.ppt-entry span{color:#64748b;font-size:12px}.question-workbench-surface{max-width:860px;margin:0 auto;padding:0;border:0;border-radius:0;box-shadow:none}
.has-lesson-outline .lesson-workspace{grid-template-columns:190px minmax(0,1fr);gap:14px}.has-lesson-outline .lesson-workspace.is-outline-collapsed{grid-template-columns:minmax(0,1fr);gap:0}.lesson-outline{display:block;min-height:156px}.lesson-outline>nav{position:relative;padding:3px 0 3px 2px}.lesson-outline>nav::before{position:absolute;top:18px;bottom:18px;left:12px;width:1px;background:#dde3ec;content:""}.lesson-outline-chapter-button{position:relative;min-height:46px;grid-template-columns:20px minmax(0,1fr);gap:7px;padding:5px 7px 5px 2px;border-radius:8px}.lesson-outline-chapter-button:disabled{opacity:.48;cursor:not-allowed}.lesson-outline-chapter-marker{position:relative;z-index:1;width:6px;height:6px;border-color:#c4cedb;background:#f3f5f9}.lesson-outline-chapter-marker[data-state="generating"]{border-color:#6661dc;background:#6661dc}.lesson-outline-chapter-marker[data-state="review"]{border-color:#8884d8;background:#f3f2ff}.lesson-outline-chapter-marker[data-state="confirmed"]{border-color:#6661dc;background:#6661dc}.lesson-outline-chapter-marker[data-state="failed"]{border-color:#d75563;background:#d75563}.lesson-outline-chapter-copy{gap:1px}.lesson-outline-chapter-copy strong{color:#5e6b7e;font-size:11.5px;font-weight:620;line-height:1.4}.lesson-outline-chapter-copy small{color:#8a96a8;font-size:9.5px}.lesson-outline-chapter-copy small[data-state="review"]{color:#7773bd}.lesson-outline-chapter-copy small[data-state="failed"]{color:#b94b57}.lesson-outline-chapter-button:hover:not(:disabled){background:rgba(255,255,255,.52)}.lesson-outline-chapter-button.active{background:rgba(239,240,255,.62)}.lesson-outline-chapter-button.active .lesson-outline-chapter-marker{box-shadow:none}.lesson-outline-chapter-button.active strong{color:#34316f}.lesson-outline-chapter-button.active small{color:#6965b9}.lesson-outline-toggle{color:#596579!important;background:transparent!important;border-color:transparent!important;font-weight:650!important;box-shadow:none!important}.lesson-outline-toggle:hover{color:#3730a3!important;background:#f1f2f7!important}.lesson-section-tabs button:disabled{opacity:.5;cursor:not-allowed}
.teacher-workbench.is-ai-collaboration{grid-template-columns:minmax(0,1fr) 1px minmax(320px,var(--ai-pane-width))}.lesson-navigator{grid-template-columns:auto auto minmax(0,1fr) auto;gap:8px}.is-ai-collaboration .lesson-navigator{grid-template-columns:auto minmax(0,1fr) auto}.lesson-selector select:disabled{color:#94a3b8;cursor:not-allowed}.lesson-outline-chapter-button:focus-visible,.lesson-section-tabs button:focus-visible{outline:2px solid #5b57e8;outline-offset:2px}
@media(max-width:1320px){.has-lesson-outline .lesson-workspace{grid-template-columns:184px minmax(0,1fr);gap:12px}.has-lesson-outline .lesson-workspace.is-outline-collapsed{grid-template-columns:minmax(0,1fr);gap:0}}
@media(max-width:760px){.lesson-navigator{gap:6px;padding-inline:10px}.lesson-navigator>button{font-size:0}.lesson-navigator>button svg{display:block}.lesson-selector select{padding-inline:8px;font-size:12px}.ppt-entry{grid-template-columns:auto minmax(0,1fr);padding:28px 18px}.ppt-entry .primary{grid-column:1/-1}}
@media(prefers-reduced-motion:reduce){.has-lesson-outline .lesson-workspace{transition:none}.lesson-outline-chapter-marker[data-state="generating"]{animation:none}}
</style>
