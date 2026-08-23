<template>
  <section class="teacher-workbench">
    <aside class="stage-rail" :aria-label="t('courseWorkbench.stageNavigation', '课程生产阶段')">
      <header><strong>{{ t('courseWorkbench.title', '课程工作台') }}</strong><small>{{ t('courseWorkbench.progress', '五类资产可独立创建') }}</small></header>
      <nav>
        <button v-for="stage in stages" :key="stage.id" type="button" :class="{ active: activeStage === stage.id }" @click="activeStage = stage.id">
          <span>{{ stage.step }}</span><component :is="stage.icon" :size="18" /><div><strong>{{ stage.label }}</strong><small>{{ stage.description }}</small></div><Check v-if="stageReady(stage.id)" :size="15" />
        </button>
      </nav>
      <section class="companion-entry">
        <small>{{ t('courseWorkbench.supporting.group', '其他课程文件') }}</small>
        <button type="button" :class="{ active: activeStage === 'companion' }" @click="activeStage = 'companion'">
          <FileCheck2 :size="18" /><div><strong>{{ t('courseWorkbench.supporting.title', '配套文档') }}</strong><small>{{ t('courseWorkbench.supporting.help', '学校模板快捷生成') }}</small></div><ChevronRight :size="16" />
        </button>
      </section>
      <footer><span>{{ readyStageCount }}/5</span><div><i :style="{ width: `${readyStageCount / 5 * 100}%` }" /></div></footer>
    </aside>

    <main ref="workbenchCenter" class="workbench-center" :class="{ 'is-outline-workspace': showOutlineWorkspace }">
      <header class="center-heading">
        <div><small>{{ activeStage === 'companion' ? t('courseWorkbench.supporting.kicker', '配套文档') : `${activeStageDefinition.step} / 05` }}</small><h2>{{ activeStageDefinition.label }}</h2><p>{{ activeStageDefinition.description }}</p></div>
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
          <div><TriangleAlert v-if="generationFailed" :size="18" /><LoaderCircle v-else :size="18" class="spin" /><span><strong>{{ generationFailed ? t('courseWorkbench.generationInterrupted', '生成已中断') : t('courseWorkbench.generating', '正在生成课程大纲') }}</strong><small>{{ generationFailed ? generationError : currentGenerationLabel }}</small></span></div>
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
        <p v-if="generationError" class="generation-error" role="alert">{{ generationError }} <button type="button" @click="submitFoundation">{{ t('common.retry', '重试') }}</button></p>
      </section>

      <section v-else-if="activeStage === 'foundation' && outlineShapeAwaitingReview" class="formal-surface outline-shape-review" data-testid="outline-shape-review">
        <header>
          <div><strong>{{ t('courseWorkbench.shapeReview.title', '大章节已生成') }}</strong><small>{{ t('courseWorkbench.shapeReview.help', '请根据真实章节内容确认每章需要展开几个小节') }}</small></div>
        </header>
        <article>
          <ol class="shape-chapter-list">
            <li v-for="(chapter, index) in outlineGrowthChapters" :key="String(chapter.chapter_number || index)">
              <span class="shape-chapter-index">{{ String(index + 1).padStart(2, '0') }}</span>
              <div><strong>{{ chapter.title }}</strong><small>{{ chapter.learning_focus }}</small></div>
              <label><input v-model.number="chapterSectionCounts[index]" type="number" min="1" max="100" :aria-label="t('courseWorkbench.shapeReview.countLabel', '{chapter}的小节数').replace('{chapter}', String(chapter.title || index + 1))" /><span>{{ t('courseWorkbench.form.sectionUnit', '小节') }}</span></label>
            </li>
          </ol>
          <p v-if="shapeConfirmError" class="shape-confirm-error" role="alert">{{ shapeConfirmError }}</p>
        </article>
        <footer><span>{{ t('courseWorkbench.shapeReview.total', '确认后将生成 {count} 个小节').replace('{count}', String(totalSectionCount)) }}</span><button class="primary" type="button" :disabled="shapeConfirming || !shapeCountsValid" @click="confirmOutlineShape"><Sparkles :size="16" />{{ shapeConfirming ? t('courseWorkbench.shapeReview.confirming', '正在继续…') : t('courseWorkbench.shapeReview.confirm', '确认并生成小章节') }}</button></footer>
      </section>

      <section v-else-if="showOutlineWorkspace" class="formal-surface outline-workspace" data-testid="outline-workspace">
        <header>
          <div>
            <strong>{{ outlineAwaitingReview
              ? t('courseWorkbench.outlineReady', '课程大纲已生成')
              : t('courseWorkbench.formalOutline', '正式课程大纲') }}</strong>
            <small>{{ outlineAwaitingReview
              ? t('courseWorkbench.outlineReadyHelp', '已保存完整章节结构，等待确认')
              : t('courseWorkbench.formalSaved', '已进入课程正式文件') }}</small>
          </div>
        </header>
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
        <footer><span>{{ t('courseWorkbench.form.sourceHint', '右侧资料会与这些信息一起交给 AI') }}</span><button class="primary" type="submit" :disabled="generationStarting || !foundation.goal"><Sparkles :size="16" />{{ t('courseWorkbench.generateChapterSkeleton', '生成大章节') }}</button></footer>
      </form>

      <CompanionDocumentStudio
        v-else-if="activeStage === 'companion'"
        :course-id="courseId"
        @saved="handleCompanionSaved"
      />

      <section v-else class="lesson-stage">
        <nav v-if="lessonStore.lessons.length && !outlineGatePending" class="lesson-navigator" :aria-label="t('courseWorkbench.lessonNavigation', '课次导航')">
          <button type="button" :disabled="!previousLesson" @click="selectLesson(previousLesson?.lesson_unit_id)"><ChevronLeft :size="15" />{{ t('courseWorkbench.previousLesson', '上一讲') }}</button>
          <label class="lesson-selector"><span>{{ t('courseWorkbench.form.lesson', '选择课次') }}</span><select v-model="selectedLessonId"><option value="" disabled>{{ t('courseWorkbench.form.chooseLesson', '请选择课次') }}</option><option v-for="lesson in lessonStore.lessons" :key="lesson.lesson_unit_id" :value="lesson.lesson_unit_id">{{ String(lesson.number).padStart(2, '0') }} · {{ lesson.title }}</option></select></label>
          <button type="button" :disabled="!nextLesson" @click="selectLesson(nextLesson?.lesson_unit_id)">{{ t('courseWorkbench.nextLesson', '下一讲') }}<ChevronRight :size="15" /></button>
        </nav>
        <div v-if="lessonStageBlocked" class="prerequisite" :data-state="lessonPrerequisiteState.kind" aria-live="polite">
          <LoaderCircle v-if="lessonPrerequisiteState.kind === 'loading'" :size="24" class="spin" />
          <TriangleAlert v-else-if="lessonPrerequisiteState.kind === 'error'" :size="24" />
          <FileText v-else :size="24" />
          <strong>{{ lessonPrerequisiteState.title }}</strong>
          <span>{{ lessonPrerequisiteState.detail }}</span>
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
          </section>
          <form v-else-if="selectedLesson && !workingLessonRevision" class="stage-form stage-form--lesson" @submit.prevent="generateLessonPlan">
            <label class="form-field form-field--wide"><span>{{ t('courseWorkbench.form.lessonFocus', '本讲重点') }}</span><textarea v-model.trim="lessonRequirements" rows="4" :placeholder="t('courseWorkbench.form.lessonFocusPlaceholder', '填写重难点、教学方法或课堂活动要求')" /></label>
            <p v-if="lessonGenerationError" class="generation-error lesson-generation-error" role="alert">{{ lessonGenerationError }}</p>
            <footer><span>{{ t('courseWorkbench.form.lessonGenerationHint', '生成本讲各小节的目标、课堂环节与时间分配') }}</span><button class="primary" type="submit" :disabled="lessonBusy || lessonGenerationActive || !selectedLessonId"><LoaderCircle v-if="lessonBusy" :size="16" class="spin" /><Sparkles v-else :size="16" />{{ lessonGenerationFailed ? t('courseWorkbench.retryLessonPlan', '重新生成本讲教案') : t('courseWorkbench.generateLessonPlan', '生成本讲教案') }}</button></footer>
          </form>
          <TeacherLessonPlanDocument
            v-else-if="workingLessonRevision && selectedLesson"
            :course-id="courseId"
            :lesson="selectedLesson"
            :confirmed="lessonPlanConfirmed"
            :confirming="lessonConfirming"
            :confirm-error="lessonConfirmError"
            @confirm="confirmLessonPlan"
            @next="activeStage = 'question-bank'"
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
            <div><strong>{{ selectedLesson?.title }}</strong><span>{{ t('courseWorkbench.pptFromScript', '从已确认教案与讲稿进入同一份 V6 PPT') }}</span></div>
            <button class="primary" type="button" :disabled="!confirmedLessonRevision || !scriptConfirmed" @click="openPptWorkspace"><Presentation :size="15" />{{ t('courseWorkbench.openPptWorkbench', '进入 PPT 工作台') }}</button>
          </section>
        </template>
      </section>
    </main>

    <CourseReferenceTray v-model="activeReferences" :course-id="courseId" :stage="activeStage" :lesson-id="activeReferenceLessonId" />
  </section>
</template>

<script setup lang="ts">
import { computed, markRaw, reactive, ref, watch } from 'vue'
import { BookOpenText, Check, ChevronLeft, ChevronRight, ClipboardList, FileCheck2, FileText, Layers3, ListChecks, LoaderCircle, Pause, Pencil, Presentation, Sparkles, TriangleAlert } from 'lucide-vue-next'
import CompanionDocumentStudio from './CompanionDocumentStudio.vue'
import CourseOutlineReview from './CourseOutlineReview.vue'
import CourseReferenceTray, { type CourseReferenceItem } from './CourseReferenceTray.vue'
import MarkdownRenderer from './MarkdownRenderer.vue'
import OutlineGrowthStream from './OutlineGrowthStream.vue'
import QuestionBankReviewPanel from './QuestionBankReviewPanel.vue'
import TeacherLessonPlanDocument from './TeacherLessonPlanDocument.vue'
import TeacherScriptDocument from './TeacherScriptDocument.vue'
import { t } from '../shared/i18n'
import type { CourseGenerationOptions } from '../shared/prompt-config'
import { useCourseStore } from '../stores/course'
import { useCourseWorkspaceStore } from '../stores/courseWorkspace'
import { useGenerationStore } from '../stores/generation'
import { useTeacherLessonAuthoringStore } from '../stores/teacherLessonAuthoring'
import http, { teacherRequestConfig } from '../utils/http'

type CoreStageId = 'foundation' | 'lesson' | 'question-bank' | 'script' | 'ppt'
type StageId = CoreStageId | 'companion'
const props = withDefaults(defineProps<{ courseId: string; courseTitle: string; generationOptions: CourseGenerationOptions & { subject?: string }; generationStarting?: boolean; initialStage?: StageId; initialLessonId?: string; outlineEditing?: boolean }>(), { initialStage: 'foundation', initialLessonId: '', outlineEditing: false })
const emit = defineEmits<{
  (event: 'generateOutline', payload: { subject: string; options: CourseGenerationOptions; references: CourseReferenceItem[] }): void
  (event: 'update:outlineEditing', value: boolean): void
  (event: 'outlineConfirmed'): void
}>()
const courseStore = useCourseStore(); const courseWorkspaceStore = useCourseWorkspaceStore(); const generationStore = useGenerationStore(); const lessonStore = useTeacherLessonAuthoringStore()
const activeStage = ref<StageId>(props.initialStage); const selectedLessonId = ref(props.initialLessonId)
const workbenchCenter = ref<HTMLElement | null>(null)
const outlineEditor = ref<{ finishEditing: () => Promise<boolean> } | null>(null)
const finishingOutline = ref(false)
const editingOutline = computed({
  get: () => props.outlineEditing,
  set: value => emit('update:outlineEditing', value),
})
const referencesByStage = reactive<Record<StageId, CourseReferenceItem[]>>({ foundation: [], lesson: [], 'question-bank': [], script: [], ppt: [], companion: [] })
const activeReferences = computed({ get: () => referencesByStage[activeStage.value], set: value => { referencesByStage[activeStage.value] = value } })
const activeReferenceLessonId = computed(() => ['lesson', 'question-bank', 'script', 'ppt'].includes(activeStage.value) ? selectedLessonId.value : '')
const foundation = reactive({ goal: '', totalHours: 32, requirements: '' })
const chapterSectionCounts = ref<number[]>([])
const loadedShapeRevision = ref('')
const shapeConfirming = ref(false)
const shapeConfirmError = ref('')
const totalSectionCount = computed(() => chapterSectionCounts.value.reduce((total, count) => total + Math.max(1, Number(count || 1)), 0))
const lessonRequirements = ref('')
const lessonBusy = ref(false); const lessonConfirming = ref(false); const lessonConfirmError = ref(''); const scriptGenerating = ref(false); const scriptGenerationError = ref(''); const scriptConfirming = ref(false); const scriptConfirmError = ref(''); const generationRequested = ref(false)
const retainedOutlineGrowth = ref<Record<string, any> | null>(null)
const questionBankReady = ref(false)
const stages = computed(() => [
  { id: 'foundation' as const, step: '01', label: t('courseWorkbench.stages.foundation', '课程基础'), description: t('courseWorkbench.stages.foundationHelp', '大纲与教学日历'), icon: markRaw(Layers3) },
  { id: 'lesson' as const, step: '02', label: t('courseWorkbench.stages.lesson', '教案'), description: t('courseWorkbench.stages.lessonHelp', '按课次组织教学'), icon: markRaw(ClipboardList) },
  { id: 'question-bank' as const, step: '03', label: t('courseWorkbench.stages.questionBank', '题库'), description: t('courseWorkbench.stages.questionBankHelp', '可选 · 出题与组卷'), icon: markRaw(ListChecks) },
  { id: 'script' as const, step: '04', label: t('courseWorkbench.stages.script', '讲稿'), description: t('courseWorkbench.stages.scriptHelp', '轻量可编辑正文'), icon: markRaw(BookOpenText) },
  { id: 'ppt' as const, step: '05', label: t('courseWorkbench.stages.ppt', 'PPT'), description: t('courseWorkbench.stages.pptHelp', '与讲稿结构化同源'), icon: markRaw(Presentation) },
])
const activeStageDefinition = computed(() => stages.value.find(item => item.id === activeStage.value) || {
  id: 'companion' as const,
  step: '',
  label: t('courseWorkbench.supporting.title', '配套文档'),
  description: t('courseWorkbench.supporting.description', '从学校模板快速生成正式文件'),
  icon: markRaw(FileCheck2),
})
const selectedLesson = computed(() => lessonStore.lessons.find(item => item.lesson_unit_id === selectedLessonId.value))
const selectedLessonIndex = computed(() => lessonStore.lessons.findIndex(item => item.lesson_unit_id === selectedLessonId.value))
const previousLesson = computed(() => selectedLessonIndex.value > 0 ? lessonStore.lessons[selectedLessonIndex.value - 1] : undefined)
const nextLesson = computed(() => selectedLessonIndex.value >= 0 && selectedLessonIndex.value < lessonStore.lessons.length - 1 ? lessonStore.lessons[selectedLessonIndex.value + 1] : undefined)
const workingLessonRevision = computed(() => selectedLesson.value?.plan.revisions.find(item => item.revision_id === selectedLesson.value?.plan.working_revision_id))
const confirmedLessonRevision = computed(() => selectedLesson.value?.plan.revisions.find(item => item.revision_id === selectedLesson.value?.plan.confirmed_revision_id))
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
const lessonJob = computed(() => selectedLessonId.value ? lessonStore.latestJobByLesson(selectedLessonId.value) : undefined)
const lessonGenerationActive = computed(() => ['pending', 'running'].includes(String(lessonJob.value?.status || '')))
const lessonGenerationFailed = computed(() => lessonJob.value?.status === 'failed')
const lessonGenerationProgress = computed(() => Math.max(3, Number(lessonJob.value?.progress || 0)))
const lessonGenerationError = computed(() => String(lessonJob.value?.error?.message || lessonStore.error || ''))
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

function stageReady(stage: CoreStageId) { if (stage === 'foundation') return hasOutline.value; if (stage === 'lesson') return lessonStore.lessons.some(item => Boolean(item.plan.confirmed_revision_id)); if (stage === 'question-bank') return questionBankReady.value; if (stage === 'script') return lessonStore.lessons.some(item => item.script?.confirmed); return lessonStore.lessons.some(item => item.plan.ppt_assets.some(asset => asset.engine === 'slide_deck_v6' && asset.source_state === 'current')) }
function nodeContent(node: any) { return generationStore.streamingContent[node.node_id] || node.node_content || '' }
function stopGeneration() { void generationStore.stopGeneration() }
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
async function confirmOutlineShape() { if (!shapeCountsValid.value || shapeConfirming.value) return; shapeConfirming.value = true; shapeConfirmError.value = ''; try { const counts = chapterSectionCounts.value.map(count => Number(count)); await courseWorkspaceStore.confirmOutlineShape(props.courseId, counts); generationRequested.value = true; await generationStore.fetchGlobalTasks() } catch (error: any) { shapeConfirmError.value = String(error?.response?.data?.detail || error?.message || t('courseWorkbench.shapeReview.failed', '无法继续生成，请稍后重试')) } finally { shapeConfirming.value = false } }
async function generateLessonPlan() { if (!selectedLesson.value || lessonGenerationActive.value) return; lessonBusy.value = true; lessonConfirmError.value = ''; try { await saveRelationships(`lesson-plan:${selectedLessonId.value}`, 'lesson_plan', selectedLesson.value.title); const primary = activeReferences.value.find(item => item.role === 'primary'); await lessonStore.generateLesson(props.courseId, selectedLessonId.value, primary ? { packageId: primary.package_id, assetId: primary.asset_id } : undefined, lessonRequirements.value, activeReferences.value.map(item => item.material_asset_id)) } catch { /* The store keeps the teacher-visible reason. */ } finally { lessonBusy.value = false } }
async function confirmLessonPlan() { const revision = workingLessonRevision.value?.revision_id; if (!selectedLesson.value || !revision || lessonPlanConfirmed.value || lessonConfirming.value) return; lessonConfirming.value = true; lessonConfirmError.value = ''; try { await lessonStore.confirm(props.courseId, selectedLessonId.value, revision); activeStage.value = 'question-bank' } catch { lessonConfirmError.value = lessonStore.error || t('courseWorkbench.lessonConfirmFailed', '本讲教案确认失败，请重试。') } finally { lessonConfirming.value = false } }
function selectLesson(lessonId?: string) { if (lessonId) selectedLessonId.value = lessonId }
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
watch([outlineShapeAwaitingReview, outlineShapeRevision], ([waiting, revision]) => { if (!waiting || !revision || loadedShapeRevision.value === revision) return; chapterSectionCounts.value = outlineGrowthChapters.value.map(chapter => Math.max(1, Number(chapter.section_count || 1))); loadedShapeRevision.value = revision; shapeConfirmError.value = '' }, { immediate: true })
watch(() => generationTask.value?.phaseDetail?.outline_growth, value => { if (value && typeof value === 'object') retainedOutlineGrowth.value = JSON.parse(JSON.stringify(value)) as Record<string, any> }, { immediate: true, deep: true })
watch(outlineAwaitingReview, waiting => { if (waiting) void courseStore.refreshGenerationPreview(props.courseId, 'teacher') }, { immediate: true })
watch(() => props.initialStage, stage => { activeStage.value = stage })
watch(() => props.initialLessonId, lessonId => { if (lessonId) selectedLessonId.value = lessonId })
watch(activeStage, stage => { if (stage !== 'foundation') editingOutline.value = false; if (workbenchCenter.value) workbenchCenter.value.scrollTop = 0 }, { flush: 'post' })
watch(() => lessonStore.lessons, lessons => {
  if (props.initialLessonId && lessons.some(item => item.lesson_unit_id === props.initialLessonId)) {
    selectedLessonId.value = props.initialLessonId
    return
  }
  if (!lessons.some(item => item.lesson_unit_id === selectedLessonId.value)) selectedLessonId.value = lessons[0]?.lesson_unit_id || ''
}, { immediate: true, deep: true })
watch(selectedLessonId, () => { lessonConfirmError.value = ''; scriptGenerationError.value = ''; scriptConfirmError.value = '' })
watch(() => props.courseId, () => { void loadQuestionBankStatus() }, { immediate: true })
watch(taskStatus, status => { if (!['pending', 'running'].includes(status)) generationRequested.value = false })
</script>

<style scoped>
.teacher-workbench{height:100%;min-height:0;display:grid;grid-template-columns:238px minmax(520px,1fr) 310px;overflow:hidden;background:#f3f5f9}.stage-rail{min-height:0;display:flex;flex-direction:column;border-right:1px solid #e4e9f1;background:#fff}.stage-rail>header{display:grid;gap:4px;padding:21px 18px 16px}.stage-rail>header strong{color:#1f2a40;font-size:15px}.stage-rail>header small{color:#64748b;font-size:12px}.stage-rail nav{display:grid;gap:4px;padding:4px 9px}.stage-rail nav button{min-height:66px;display:grid;grid-template-columns:26px 22px minmax(0,1fr) 18px;align-items:center;gap:8px;padding:8px 10px;border:0;border-radius:10px;color:#64748b;background:transparent;text-align:left;cursor:pointer}.stage-rail nav button:hover{background:#f6f7fb}.stage-rail nav button.active{color:#4338ca;background:#eef0ff}.stage-rail nav button>span{font-size:11px;font-weight:750}.stage-rail nav button>div{min-width:0;display:grid;gap:3px}.stage-rail nav strong{color:#334155;font-size:13px}.stage-rail nav small{overflow:hidden;color:#64748b;font-size:11px;text-overflow:ellipsis;white-space:nowrap}.stage-rail nav button.active strong{color:#3730a3}.stage-rail nav button>svg:last-child{color:#16a34a}.stage-rail>footer{display:grid;grid-template-columns:auto minmax(0,1fr);align-items:center;gap:9px;margin-top:auto;padding:16px 18px;color:#64748b;font-size:12px}.stage-rail>footer>div{height:4px;overflow:hidden;border-radius:2px;background:#e8ecf3}.stage-rail>footer i{height:100%;display:block;background:#5b57e8}.workbench-center{min-width:0;min-height:0;overflow:auto;padding:24px 26px 52px}.center-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;max-width:860px;margin:0 auto 18px}.center-heading>div{display:grid;gap:4px}.center-heading small{color:#6366f1;font-size:11px;font-weight:800}.center-heading h2{margin:0;color:#172033;font-size:24px;letter-spacing:-.018em}.center-heading p{margin:0;color:#64748b;font-size:13px}.center-heading>button,.formal-surface>header button,.generation-surface>header button{min-height:36px;display:flex;align-items:center;gap:7px;padding:0 11px;border:1px solid #d7dde7;border-radius:8px;color:#475569;background:#fff;font-size:12px;font-weight:700;cursor:pointer}.stage-form,.formal-surface,.generation-surface,.lesson-stage{max-width:860px;margin:0 auto;border:1px solid #e0e6ef;border-radius:14px;background:#fff;box-shadow:0 10px 30px rgba(30,41,59,.05)}.stage-form{display:grid;gap:20px;padding:26px}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.form-field{display:grid;gap:8px}.form-field>span,.lesson-selector>span{color:#334155;font-size:13px;font-weight:700}.form-field b{color:#dc2626}.form-field input,.form-field select,.form-field textarea,.lesson-selector select{width:100%;min-height:44px;padding:10px 11px;border:1px solid #cfd7e3;border-radius:8px;outline:0;color:#172033;background:#fff;font:inherit;font-size:13px}.form-field textarea{resize:vertical;line-height:1.6}.form-field input:focus,.form-field select:focus,.form-field textarea:focus,.lesson-selector select:focus{border-color:#5b57e8;box-shadow:0 0 0 3px rgba(91,87,232,.11)}.stage-form>footer{display:flex;align-items:center;justify-content:space-between;gap:16px;padding-top:2px}.stage-form>footer>span{color:#64748b;font-size:12px}.primary{min-height:42px;display:flex;align-items:center;gap:7px;padding:0 15px;border:1px solid #514bdc;border-radius:8px;color:#fff;background:#514bdc;font-size:13px;font-weight:750;cursor:pointer;box-shadow:0 7px 18px rgba(81,75,220,.16)}.primary:disabled{opacity:.48;cursor:not-allowed}.generation-surface{overflow:hidden}.generation-surface>header,.formal-surface>header{min-height:64px;display:flex;align-items:center;justify-content:space-between;gap:16px;padding:0 20px;border-bottom:1px solid #e7ebf2}.generation-surface>header>div{display:flex;align-items:center;gap:10px;color:#4f46e5}.generation-surface>header span,.formal-surface>header>div{display:grid;gap:3px}.generation-surface>header strong,.formal-surface>header strong{color:#263147;font-size:13px}.generation-surface>header small,.formal-surface>header small{color:#64748b;font-size:11px}.generation-progress{height:3px;background:#e8ebf5}.generation-progress i{width:100%;height:100%;display:block;transform-origin:left;background:#5b57e8;transition:transform .25s ease-out}.stream-content,.formal-surface>article{max-height:calc(100vh - 260px);overflow:auto;padding:22px 28px 42px}.stream-content section,.formal-surface article section{margin-bottom:26px}.stream-content h3,.formal-surface h3{margin:0 0 10px;color:#202b40;font-size:17px}.stream-waiting{min-height:260px;display:flex;align-items:center;justify-content:center;gap:9px;color:#64748b;font-size:13px}.stream-caret{width:2px;height:18px;display:inline-block;background:#5b57e8;animation:blink .8s steps(1) infinite}.generation-error{margin:0;padding:12px 20px;color:#b91c1c;background:#fff1f2;font-size:12px}.generation-error button{border:0;color:inherit;background:transparent;font-weight:750;text-decoration:underline;cursor:pointer}.lesson-stage{padding:0 0 24px}.lesson-selector{display:grid;grid-template-columns:110px minmax(0,1fr);align-items:center;gap:14px;padding:18px 22px;border-bottom:1px solid #e7ebf2}.stage-form--lesson{border:0;box-shadow:none}.prerequisite,.empty-asset{min-height:260px;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:10px;color:#64748b;font-size:13px}.prerequisite strong{color:#334155}.prerequisite button{padding:7px 10px;border:1px solid #d7dde7;border-radius:7px;color:#4f46e5;background:#fff;font-weight:700;cursor:pointer}.lesson-formal{margin:20px 20px 0;border-radius:10px;box-shadow:none}.lesson-formal>article{max-height:calc(100vh - 360px)}.formal-surface ol{display:grid;gap:8px;padding-left:22px;color:#475569;font-size:13px}.spin{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}@keyframes blink{50%{opacity:0}}
.companion-entry{display:grid;gap:7px;margin:10px 9px 0;padding-top:14px;border-top:1px solid #e7ebf2}.companion-entry>small{padding:0 10px;color:#64748b;font-size:11px;font-weight:700}.companion-entry>button{min-height:58px;display:grid;grid-template-columns:22px minmax(0,1fr) 16px;align-items:center;gap:9px;padding:8px 10px;border:0;border-radius:10px;color:#64748b;background:transparent;text-align:left;cursor:pointer}.companion-entry>button:hover{background:#f6f7fb}.companion-entry>button.active{color:#4338ca;background:#eef0ff}.companion-entry>button>div{min-width:0;display:grid;gap:3px}.companion-entry strong{color:#334155;font-size:13px}.companion-entry small{overflow:hidden;color:#64748b;font-size:11px;text-overflow:ellipsis;white-space:nowrap}.companion-entry>button.active strong{color:#3730a3}
.question-workbench-surface{max-width:860px;margin:0 auto;padding:0}
@media(max-width:1050px){.teacher-workbench{grid-template-columns:190px minmax(0,1fr) 280px}.workbench-center{padding-inline:18px}.stage-rail nav button{grid-template-columns:23px minmax(0,1fr)}.stage-rail nav button>svg,.stage-rail nav button>svg:last-child{display:none}}
@media(max-width:760px){.teacher-workbench{height:auto;min-height:100%;grid-template-columns:1fr;overflow:auto}.stage-rail{display:block;border-right:0;border-bottom:1px solid #e4e9f1}.stage-rail>header,.stage-rail>footer{display:none}.stage-rail nav{grid-template-columns:repeat(5,minmax(0,1fr));overflow:auto;padding:8px}.stage-rail nav button{min-width:108px;min-height:50px;grid-template-columns:22px minmax(0,1fr);padding:6px 8px}.stage-rail nav small{display:none}.workbench-center{overflow:visible;padding:18px 12px 30px}.center-heading h2{font-size:21px}.center-heading>button{font-size:0;width:38px;padding:0;justify-content:center}.stage-form{padding:19px 16px}.form-grid{grid-template-columns:1fr}.stage-form>footer{align-items:stretch;flex-direction:column}.primary{justify-content:center}.lesson-selector{grid-template-columns:1fr}.stream-content,.formal-surface>article{max-height:none;padding-inline:18px}.reference-tray{border-left:0;border-top:1px solid #e4e9f1}}
.stream-failed{color:#b91c1c;background:#fffafa}
.outline-shape-review>article{padding-bottom:20px}.shape-chapter-list{display:grid;gap:0;margin:0;padding:0!important;list-style:none}.shape-chapter-list li{min-height:72px;display:grid;grid-template-columns:34px minmax(0,1fr) auto;align-items:center;gap:12px;padding:10px 2px;border-bottom:1px solid #edf1f6}.shape-chapter-index{width:30px;height:30px;display:grid;place-items:center;border-radius:50%;color:#4f46e5;background:#eef2ff;font-size:11px;font-weight:800}.shape-chapter-list li>div{min-width:0;display:grid;gap:4px}.shape-chapter-list li>div strong{color:#263147;font-size:13px}.shape-chapter-list li>div small{color:#64748b;font-size:11px;line-height:1.45}.shape-chapter-list label{display:flex;align-items:center;gap:7px;color:#64748b;font-size:11px}.shape-chapter-list input{width:68px;min-height:36px;padding:6px 8px;border:1px solid #cfd7e3;border-radius:7px;outline:0;color:#172033;background:#fff;font:inherit;font-size:13px;text-align:center}.shape-chapter-list input:focus{border-color:#5b57e8;box-shadow:0 0 0 3px rgba(91,87,232,.11)}.outline-shape-review>footer{min-height:66px;display:flex;align-items:center;justify-content:space-between;gap:16px;padding:10px 20px;border-top:1px solid #e7ebf2}.outline-shape-review>footer>span{color:#64748b;font-size:12px}.shape-confirm-error{margin:12px 0 0;color:#b91c1c;font-size:12px}
.lesson-generation-surface{min-height:68px}.lesson-generation-error{margin:-4px 0 0;padding:10px 12px;border-radius:8px}
.workbench-center.is-outline-workspace{padding-bottom:24px}.outline-workspace{overflow:hidden}.outline-workspace>header{border-bottom:1px solid #e7ebf2}.outline-workspace>.inline-outline-review{width:100%;min-height:0}
.prerequisite{padding:28px;text-align:center}.prerequisite>span{max-width:480px;line-height:1.55}.prerequisite[data-state="review"]>svg{color:#4f46e5}.prerequisite[data-state="error"]>svg{color:#b91c1c}.prerequisite button{min-height:36px;padding:7px 11px}.prerequisite button:hover{border-color:#aaa7f4;background:#f7f7ff}.prerequisite button:focus-visible{outline:2px solid #5b57e8;outline-offset:2px}.prerequisite button:disabled{opacity:.5;cursor:not-allowed}
.lesson-stage{padding:0;overflow:hidden}.lesson-navigator{min-height:54px;display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:center;gap:14px;padding:0 20px;border-bottom:1px solid #e7ebf2;background:#fbfcfe}.lesson-navigator>button{min-height:34px;display:flex;align-items:center;gap:5px;padding:0 5px;border:0;color:#64748b;background:transparent;font-size:12px;font-weight:700;cursor:pointer}.lesson-navigator>button:hover:not(:disabled){color:#4338ca}.lesson-navigator>button:disabled{opacity:.35;cursor:not-allowed}.lesson-selector{min-width:0;display:flex;align-items:center;justify-content:center;gap:0;padding:0;border:0}.lesson-selector>span{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}.lesson-selector select{width:min(100%,560px);min-height:36px;padding:0 34px 0 12px;border:0;border-radius:7px;color:#263147;background:transparent;font-size:13px;font-weight:750;text-align:center;box-shadow:none}.lesson-selector select:hover{background:#f3f5fa}.lesson-selector select:focus{background:#fff}.stage-form--lesson{border:0;border-radius:0;box-shadow:none}.stage-next-bar{min-height:64px;display:flex;align-items:center;justify-content:space-between;padding:12px 28px;border-top:1px solid #e8ecf2;background:#fbfcfe}.ppt-entry{min-height:180px;display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:center;gap:16px;padding:36px 28px}.ppt-entry>svg{color:#5b57e8}.ppt-entry>div{min-width:0;display:grid;gap:5px}.ppt-entry strong{color:#1f2a40;font-size:15px}.ppt-entry span{color:#64748b;font-size:12px}.question-workbench-surface{max-width:860px;margin:0 auto;padding:0;border:0;border-radius:0;box-shadow:none}
@media(max-width:760px){.lesson-navigator{gap:6px;padding-inline:10px}.lesson-navigator>button{font-size:0}.lesson-navigator>button svg{display:block}.lesson-selector select{padding-inline:8px;font-size:12px}.ppt-entry{grid-template-columns:auto minmax(0,1fr);padding:28px 18px}.ppt-entry .primary{grid-column:1/-1}}
</style>
