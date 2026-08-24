<template>
  <section
    ref="workbenchRoot"
    class="teacher-workbench"
    :class="{ 'is-ai-collaboration': aiCollaborationOpen }"
    :style="{ '--ai-pane-width': `${aiPaneWidth}px` }"
  >
    <aside v-show="!aiCollaborationOpen" class="stage-rail" :aria-label="t('courseWorkbench.stageNavigation', '课程生产阶段')">
      <header><strong class="stage-rail-title">{{ t('courseWorkbench.title', '课程工作台') }}</strong></header>
      <nav>
        <button v-for="stage in stages" :key="stage.id" type="button" :class="{ active: activeStage === stage.id }" :disabled="aiCandidatePending && activeStage !== stage.id" @click="activeStage = stage.id">
          <span>{{ stage.step }}</span><component :is="stage.icon" :size="18" /><strong>{{ stage.label }}</strong><Check v-if="stageReady(stage.id)" :size="15" />
        </button>
      </nav>
      <section class="companion-entry">
        <small>{{ t('courseWorkbench.supporting.group', '其他课程文件') }}</small>
        <button type="button" :class="{ active: activeStage === 'companion' }" :disabled="aiCandidatePending && activeStage !== 'companion'" @click="activeStage = 'companion'">
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
          :assistant-open="aiCollaborationOpen && aiDomain === 'outline'"
          variant="inline"
          surface="teacher"
          @confirmed="handleInlineOutlineConfirmed"
          @next="activeStage = 'lesson'"
          @open-ai="openAiCollaboration('outline')"
          @ai-candidate-change="handleAiCandidateChange"
          @ai-resolving="handleAiResolving"
          @ai-resolved="handleAiResolved"
          @ai-error="handleAiError"
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
        <div class="lesson-workspace">
          <div class="lesson-stage-content">
        <nav v-if="lessonStore.lessons.length && !outlineGatePending" class="lesson-navigator" :aria-label="t('courseWorkbench.lessonNavigation', '课次导航')">
          <button type="button" :disabled="!previousLesson || aiCandidatePending" @click="selectLesson(previousLesson?.lesson_unit_id)"><ChevronLeft :size="15" />{{ t('courseWorkbench.previousLesson', '上一讲') }}</button>
          <div class="lesson-current-group">
            <div ref="lessonOutlineRoot" class="lesson-outline-control">
              <button
                ref="lessonOutlineTrigger"
                class="lesson-outline-trigger"
                type="button"
                :aria-expanded="lessonOutlineOpen"
                aria-controls="lesson-outline-navigation"
                @click="toggleLessonOutline"
              >
                <ListTree :size="15" />
                <span>{{ t('courseWorkbench.lessonOutline.trigger', '目录') }}</span>
                <small>{{ selectedLessonPosition }}/{{ lessonStore.lessons.length }}</small>
              </button>
              <nav
                v-if="lessonOutlineOpen"
                id="lesson-outline-navigation"
                class="lesson-outline-popover"
                :aria-label="t('courseWorkbench.lessonOutline.title', '教案目录')"
                @keydown.esc.stop.prevent="closeLessonOutline(true)"
              >
                <button
                  v-for="(lesson, lessonIndex) in lessonStore.lessons"
                  :key="lesson.lesson_unit_id"
                  class="lesson-outline-chapter-button"
                  type="button"
                  :class="{ active: selectedLessonId === lesson.lesson_unit_id }"
                  :disabled="aiCandidatePending && selectedLessonId !== lesson.lesson_unit_id"
                  :aria-current="selectedLessonId === lesson.lesson_unit_id ? 'page' : undefined"
                  :aria-label="`${lesson.title}，${lessonGenerationStateLabel(lesson)}`"
                  @click="selectLessonFromOutline(lesson.lesson_unit_id)"
                >
                  <span class="lesson-outline-chapter-index">{{ String(lessonIndex + 1).padStart(2, '0') }}</span>
                  <strong>{{ lesson.title }}</strong>
                  <span
                    class="lesson-outline-status"
                    :data-state="lessonGenerationState(lesson)"
                    :title="lessonGenerationStateLabel(lesson)"
                    aria-hidden="true"
                  >
                    <LoaderCircle v-if="lessonGenerationState(lesson) === 'generating'" :size="14" class="spin" />
                    <Check v-else-if="lessonGenerationState(lesson) === 'confirmed'" :size="14" />
                    <TriangleAlert v-else-if="lessonGenerationState(lesson) === 'failed'" :size="14" />
                    <i v-else />
                  </span>
                </button>
              </nav>
            </div>
            <label class="lesson-selector"><span>{{ t('courseWorkbench.form.lesson', '选择课次') }}</span><select v-model="selectedLessonId" :disabled="aiCandidatePending"><option value="" disabled>{{ t('courseWorkbench.form.chooseLesson', '请选择课次') }}</option><option v-for="lesson in lessonStore.lessons" :key="lesson.lesson_unit_id" :value="lesson.lesson_unit_id">{{ lesson.title }}</option></select></label>
          </div>
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
          <div v-else-if="selectedLesson && !workingLessonRevision" class="lesson-generation-step">
            <form class="lesson-generation-entry" data-testid="lesson-generation-form" @submit.prevent="generateLessonPlan">
              <div class="lesson-generation-copy">
                <strong>{{ t('courseWorkbench.generateLessonPlan', '生成本讲教案') }}</strong>
                <span>{{ t('courseWorkbench.lessonGenerationHint', 'AI 会根据课程大纲和所选资料自动组织本讲；生成后可通过 AI 助手继续调整。') }}</span>
              </div>
              <label class="lesson-focus-field">
                <span>{{ t('courseWorkbench.form.lessonFocus', '本讲重点') }}</span>
                <textarea v-model.trim="lessonRequirements" rows="2" :placeholder="t('courseWorkbench.form.lessonFocusPlaceholder', '填写重难点、教学方法或课堂活动要求')" />
              </label>
              <button class="primary" type="submit" :disabled="lessonBusy || lessonGenerationActive || !selectedLessonId">
                <LoaderCircle v-if="lessonBusy" :size="16" class="spin" />
                <Sparkles v-else :size="16" />
                {{ lessonGenerationFailed ? t('courseWorkbench.retryLessonPlan', '重新生成本讲教案') : t('courseWorkbench.generateLessonPlan', '生成本讲教案') }}
              </button>
            </form>
            <AppErrorNotice v-if="lessonGenerationErrorPresentation" class="lesson-generation-error" :presentation="lessonGenerationErrorPresentation" compact />
          </div>
          <TeacherLessonPlanDocument
            v-else-if="workingLessonRevision && selectedLesson"
            ref="lessonPlanDocument"
            :course-id="courseId"
            :lesson="selectedLesson"
            :confirmed="lessonPlanConfirmed"
            :assistant-open="aiCollaborationOpen && aiDomain === 'lesson'"
            :confirming="lessonConfirming"
            :confirm-error="lessonConfirmError"
            :active-section-id="selectedLessonSectionId"
            @update:active-section-id="selectedLessonSectionId = $event"
            @confirm="confirmLessonPlan"
            @next="activeStage = 'question-bank'"
            @open-ai="openAiCollaboration('lesson')"
            @ai-candidate-change="handleAiCandidateChange"
            @ai-resolving="handleAiResolving"
            @ai-resolved="handleAiResolved"
            @ai-error="handleAiError"
          />
        </template>

        <template v-else-if="activeStage === 'script'">
          <TeacherScriptDocument
            v-if="selectedLesson"
            ref="scriptDocument"
            :course-id="courseId"
            :lesson="selectedLesson"
            :assistant-open="aiCollaborationOpen && aiDomain === 'script'"
            :confirmed="scriptConfirmed"
            :confirming="scriptConfirming"
            :confirm-error="scriptConfirmError"
            :generating="scriptGenerationBusy"
            :generation-job="scriptJob"
            :generation-error="effectiveScriptGenerationError"
            :can-generate="Boolean(confirmedLessonRevision)"
            @generate="generateScript"
            @saved="handleScriptSaved"
            @confirm="confirmScript"
            @next="activeStage = 'ppt'"
            @open-ai="openAiCollaboration('script')"
            @ai-candidate-change="handleAiCandidateChange"
            @ai-resolving="handleAiResolving"
            @ai-resolved="handleAiResolved"
            @ai-error="handleAiError"
            @ai-scope-change="aiScriptSectionTitle = $event"
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
      :class="{ 'is-resizing': aiPaneResizing }"
      :aria-valuemin="AI_PANE_MIN_WIDTH"
      :aria-valuemax="aiPaneMaxWidth"
      :aria-valuenow="aiPaneWidth"
      :aria-valuetext="t('courseWorkbench.aiCollaboration.resizeValue', '{width} 像素').replace('{width}', String(aiPaneWidth))"
      :title="t('courseWorkbench.aiCollaboration.resizeHint', '拖动调整宽度，或使用左右方向键')"
      @pointerdown="startAiPaneResize"
      @keydown="resizeAiPaneWithKeyboard"
    ><GripVertical :size="14" /></div>

    <TeacherLessonAiWorkspace
      v-if="aiCollaborationOpen"
      :domain="aiDomain"
      :scope-title="aiScopeTitle"
      :scope-detail="aiScopeDetail"
      :reference-count="activeReferences.length"
      :sources-open="aiSourcesOpen"
      :messages="aiMessages"
      :phase="aiPhase"
      :busy="aiCollaborationBusy"
      :candidate-pending="aiCandidatePending"
      :candidate-fields="aiCandidateFieldLabels"
      :clarification-options="aiClarificationOptions"
      :quick-actions="aiQuickActions"
      :placeholder="aiPlaceholder"
      :can-retry="Boolean(lastAiOperation)"
      @close="closeAiCollaboration"
      @open-sources="aiSourcesOpen = !aiSourcesOpen"
      @send="handleAiRequest"
      @clarify="handleAiClarification"
      @retry="retryAiAction"
      @accept="resolveAiCandidate(true)"
      @reject="resolveAiCandidate(false)"
      @focus-candidate="focusAiCandidate"
    />

    <CourseReferenceTray
      v-if="!aiCollaborationOpen || aiSourcesOpen"
      v-model="activeReferences"
      :class="{ 'ai-source-drawer': aiCollaborationOpen }"
      :course-id="courseId"
      :compact="aiCollaborationOpen"
      :show-close="aiCollaborationOpen"
      :stage="activeStage"
      :lesson-id="activeReferenceLessonId"
      :scope-target-id="lessonReferenceTargetId"
      :scope-target-type="lessonReferenceTargetId ? 'lesson_plan' : ''"
      :scope-target-label="selectedLesson?.title || ''"
      :previous-scope-target-id="previousLessonReferenceTargetId"
      @close="aiSourcesOpen = false"
      @open-course-information="emit('open-course-information')"
    />
  </section>
</template>

<script setup lang="ts">
import { computed, markRaw, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { BookOpenText, Check, ChevronLeft, ChevronRight, ClipboardList, FileCheck2, FileText, GripVertical, Layers3, ListChecks, ListTree, LoaderCircle, Pause, Pencil, Presentation, Sparkles, TriangleAlert } from 'lucide-vue-next'
import AppErrorNotice from './AppErrorNotice.vue'
import CompanionDocumentStudio from './CompanionDocumentStudio.vue'
import CourseOutlineReview from './CourseOutlineReview.vue'
import CourseReferenceTray, { type CourseReferenceItem } from './CourseReferenceTray.vue'
import MarkdownRenderer from './MarkdownRenderer.vue'
import OutlineGrowthStream from './OutlineGrowthStream.vue'
import QuestionBankReviewPanel from './QuestionBankReviewPanel.vue'
import TeacherLessonAiWorkspace, { type TeacherAiQuickAction } from './TeacherLessonAiWorkspace.vue'
import TeacherLessonPlanDocument from './TeacherLessonPlanDocument.vue'
import TeacherScriptDocument from './TeacherScriptDocument.vue'
import {
  assessTeacherProductionRequest,
  buildTeacherProductionAiInstruction,
  changedTeacherLessonFields,
  teacherProductionAiBusy,
  transitionTeacherProductionAiPhase,
  type TeacherProductionAiDomain,
  type TeacherProductionAiEvent,
  type TeacherProductionAiMessage,
  type TeacherProductionAiPhase,
} from '../composables/useTeacherProductionAiCollaboration'
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
type ProductionAiDocumentHandle = {
  requestAiCandidate: (instruction: string) => Promise<Record<string, any> | null>
  resolveAiCandidate: (accept: boolean) => Promise<boolean>
  focusAiCandidate?: () => void
  focusCandidate?: () => void
}
type OutlineEditorHandle = ProductionAiDocumentHandle & {
  finishEditing: () => Promise<boolean>
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
const lessonOutlineOpen = ref(false)
const lessonOutlineRoot = ref<HTMLElement | null>(null)
const lessonOutlineTrigger = ref<HTMLButtonElement | null>(null)
const workbenchRoot = ref<HTMLElement | null>(null)
const workbenchCenter = ref<HTMLElement | null>(null)
const lessonPlanDocument = ref<LessonPlanDocumentHandle | null>(null)
const scriptDocument = ref<ProductionAiDocumentHandle | null>(null)
const aiCollaborationOpen = ref(false)
const aiSourcesOpen = ref(false)
const aiDomain = ref<TeacherProductionAiDomain>('lesson')
const AI_PANE_STORAGE_KEY = 'teacher-course-workbench:ai-pane-width'
const AI_SESSION_STORAGE_PREFIX = 'teacher-course-workbench:ai-session:'
const AI_PANE_MIN_WIDTH = 360
const AI_PANE_MAX_WIDTH = 680
const AI_CANVAS_MIN_WIDTH = 560
const aiPaneWidth = ref(460)
const aiPaneMaxWidth = ref(AI_PANE_MAX_WIDTH)
const aiPaneResizing = ref(false)
const aiPhase = ref<TeacherProductionAiPhase>('ready')
const aiCandidate = ref<Record<string, any> | null>(null)
const aiMessages = ref<TeacherProductionAiMessage[]>([])
const aiSessionScopeKey = ref('')
const aiMessageSequence = ref(0)
const aiClarificationOptions = ref<string[]>([])
const lastAiOperation = ref<'generate' | 'accept' | 'reject' | ''>('')
const replacingAiCandidate = ref(false)
const outlineEditor = ref<OutlineEditorHandle | null>(null)
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
const selectedLessonPosition = computed(() => {
  const index = lessonStore.lessons.findIndex(item => item.lesson_unit_id === selectedLessonId.value)
  return index >= 0 ? index + 1 : 1
})
const selectedLessonSectionTitle = computed(() => selectedLesson.value?.sections.find(
  item => item.section_node_id === selectedLessonSectionId.value,
)?.title || '')
const aiScriptSectionTitle = ref('')
const aiScopeTitle = computed(() => aiDomain.value === 'outline' ? props.courseTitle : selectedLesson.value?.title || props.courseTitle)
const aiScopeDetail = computed(() => {
  if (aiDomain.value === 'outline') return t('courseWorkbench.aiCollaboration.outlineScope', '课程大纲')
  if (aiDomain.value === 'script') return aiScriptSectionTitle.value || t('courseWorkbench.aiCollaboration.scriptScope', '当前讲稿小节')
  return selectedLessonSectionTitle.value || t('courseWorkbench.aiCollaboration.lessonScope', '整讲教案')
})
const aiQuickActions = computed<TeacherAiQuickAction[]>(() => {
  if (aiDomain.value === 'outline') return [
    { id: 'outline-diagnose', icon: 'diagnose', label: t('courseWorkbench.aiCollaboration.quickOutlineDiagnose', '检查结构问题'), prompt: t('courseWorkbench.aiCollaboration.quickOutlineDiagnosePrompt', '检查当前大纲的章节顺序、学习路径和重复内容，只调整确有必要的部分') },
    { id: 'outline-sequence', icon: 'sequence', label: t('courseWorkbench.aiCollaboration.quickOutlineSequence', '调整章节顺序'), prompt: t('courseWorkbench.aiCollaboration.quickOutlineSequencePrompt', '调整章节顺序，让知识难度与前置关系更合理') },
    { id: 'outline-path', icon: 'path', label: t('courseWorkbench.aiCollaboration.quickOutlinePath', '补齐学习路径'), prompt: t('courseWorkbench.aiCollaboration.quickOutlinePathPrompt', '补齐缺失的学习路径和前置衔接') },
    { id: 'outline-merge', icon: 'merge', label: t('courseWorkbench.aiCollaboration.quickOutlineMerge', '合并重复内容'), prompt: t('courseWorkbench.aiCollaboration.quickOutlineMergePrompt', '合并重复的小节，同时保留必要的知识覆盖') },
    { id: 'outline-objective', icon: 'target', label: t('courseWorkbench.aiCollaboration.quickOutlineObjective', '细化学习目标'), prompt: t('courseWorkbench.aiCollaboration.quickOutlineObjectivePrompt', '细化各小节学习目标，使其具体、可观察且与内容对应') },
    { id: 'outline-split', icon: 'split', label: t('courseWorkbench.aiCollaboration.quickOutlineSplit', '拆分过大小节'), prompt: t('courseWorkbench.aiCollaboration.quickOutlineSplitPrompt', '拆分范围过大的小节，使每节课的学习任务更聚焦') },
  ]
  if (aiDomain.value === 'script') return [
    { id: 'script-voice', icon: 'voice', label: t('courseWorkbench.aiCollaboration.quickScriptVoice', '改得更适合口语'), prompt: t('courseWorkbench.aiCollaboration.quickScriptVoicePrompt', '改得更适合老师在课堂上自然讲解，保留知识事实和教学结构') },
    { id: 'script-compress', icon: 'compress', label: t('courseWorkbench.aiCollaboration.quickScriptCompress', '压缩重复表达'), prompt: t('courseWorkbench.aiCollaboration.quickScriptCompressPrompt', '压缩重复表达，保留关键解释和必要例子') },
    { id: 'script-example', icon: 'example', label: t('courseWorkbench.aiCollaboration.quickScriptExample', '加入课堂案例'), prompt: t('courseWorkbench.aiCollaboration.quickScriptExamplePrompt', '加入一个贴合当前知识点、适合课堂讲解的具体案例') },
    { id: 'script-question', icon: 'question', label: t('courseWorkbench.aiCollaboration.quickScriptQuestion', '增加引导提问'), prompt: t('courseWorkbench.aiCollaboration.quickScriptQuestionPrompt', '增加能引导学生思考的课堂提问，并自然衔接讲解') },
    { id: 'script-transition', icon: 'transition', label: t('courseWorkbench.aiCollaboration.quickScriptTransition', '优化段落过渡'), prompt: t('courseWorkbench.aiCollaboration.quickScriptTransitionPrompt', '优化段落之间的过渡，让讲解推进更自然') },
    { id: 'script-timing', icon: 'timing', label: t('courseWorkbench.aiCollaboration.quickScriptTiming', '适配授课时长'), prompt: t('courseWorkbench.aiCollaboration.quickScriptTimingPrompt', '在不改变教学目标的前提下调整内容密度，使讲稿适配当前授课时长') },
  ]
  return [
    { id: 'lesson-objective', icon: 'target', label: t('courseWorkbench.aiCollaboration.quickObjective', '让目标可观察'), prompt: t('courseWorkbench.aiCollaboration.quickObjectivePrompt', '把教学目标改成具体、可观察、可检查的学习行为') },
    { id: 'lesson-interaction', icon: 'interaction', label: t('courseWorkbench.aiCollaboration.quickInteraction', '增加课堂互动'), prompt: t('courseWorkbench.aiCollaboration.quickInteractionPrompt', '增加与当前教学目标对应的课堂互动活动') },
    { id: 'lesson-check', icon: 'check', label: t('courseWorkbench.aiCollaboration.quickCheck', '补充检查点'), prompt: t('courseWorkbench.aiCollaboration.quickCheckPrompt', '补充能判断学生是否达成目标的课堂检查点') },
    { id: 'lesson-pacing', icon: 'timing', label: t('courseWorkbench.aiCollaboration.quickPacing', '调整时间节奏'), prompt: t('courseWorkbench.aiCollaboration.quickPacingPrompt', '调整教学时间分配，压缩单向讲授并给活动和检查留出时间') },
    { id: 'lesson-focus', icon: 'focus', label: t('courseWorkbench.aiCollaboration.quickFocus', '突出重点难点'), prompt: t('courseWorkbench.aiCollaboration.quickFocusPrompt', '突出本节教学重点和难点，并让教学活动与之对应') },
    { id: 'lesson-example', icon: 'example', label: t('courseWorkbench.aiCollaboration.quickLessonExample', '加入课堂案例'), prompt: t('courseWorkbench.aiCollaboration.quickLessonExamplePrompt', '加入一个贴合当前知识点、适合学生理解的课堂案例') },
  ]
})
const aiPlaceholder = computed(() => aiDomain.value === 'outline'
  ? '说说你想怎么调整大纲…'
  : aiDomain.value === 'script'
    ? '说说你想怎么改这段讲稿…'
    : '说说你想怎么调整教案…')
const currentAiScopeKey = computed(() => [props.courseId, aiDomain.value, selectedLessonId.value, aiScopeDetail.value].join(':'))
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
const currentAiBaseRevision = computed(() => {
  if (aiDomain.value === 'lesson') return String(workingLessonRevision.value?.revision_id || '')
  if (aiDomain.value === 'script') return String(selectedLesson.value?.script?.current_revision_id || '')
  return String(generationTask.value?.phaseDetail?.skeleton_revision_id || '')
})
const aiCollaborationBusy = computed(() => teacherProductionAiBusy(aiPhase.value))
const aiCandidatePending = computed(() => Boolean(aiCandidate.value))
const activeAiDocument = computed<ProductionAiDocumentHandle | null>(() => {
  if (aiDomain.value === 'outline') return outlineEditor.value
  if (aiDomain.value === 'script') return scriptDocument.value
  return lessonPlanDocument.value as ProductionAiDocumentHandle | null
})
const aiCandidateFieldLabels = computed(() => {
  if (aiDomain.value === 'outline') {
    const diff = aiCandidate.value?.diff || {}
    return [
      Array.isArray(diff.added) && diff.added.length ? `新增 ${diff.added.length} 项` : '',
      Array.isArray(diff.removed) && diff.removed.length ? `删除 ${diff.removed.length} 项` : '',
      Array.isArray(diff.moved) && diff.moved.length ? `移动 ${diff.moved.length} 项` : '',
      Array.isArray(diff.updated) && diff.updated.length ? `修改 ${diff.updated.length} 项` : '',
    ].filter(Boolean)
  }
  if (aiDomain.value === 'script') return [t('courseWorkbench.aiCollaboration.scriptBody', '讲稿正文')]
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
const lessonGenerationError = computed(() => String(lessonJob.value?.error?.message || lessonConfirmError.value || lessonStore.error || ''))
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
const scriptJob = computed(() => selectedLessonId.value ? lessonStore.latestScriptJobByLesson(selectedLessonId.value) : undefined)
const scriptGenerationActive = computed(() => ['pending', 'running'].includes(String(scriptJob.value?.status || '')))
const scriptGenerationBusy = computed(() => scriptGenerating.value || scriptGenerationActive.value)
const effectiveScriptGenerationError = computed(() => String(
  scriptJob.value?.status === 'failed'
    ? scriptJob.value.error?.message || scriptGenerationError.value
    : scriptGenerationError.value,
))
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
function appendAiMessage(role: TeacherProductionAiMessage['role'], kind: TeacherProductionAiMessage['kind'], text: string) {
  aiMessageSequence.value += 1
  aiMessages.value.push({ id: `production-ai-${aiMessageSequence.value}`, role, kind, text })
}
function transitionAi(event: TeacherProductionAiEvent) {
  aiPhase.value = transitionTeacherProductionAiPhase(aiPhase.value, event)
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
  }
}
function aiSessionStorageKey() {
  return `${AI_SESSION_STORAGE_PREFIX}${currentAiScopeKey.value}`
}
function restoreAiSession() {
  try {
    const raw = window.localStorage.getItem(aiSessionStorageKey())
    if (!raw) return false
    const stored = JSON.parse(raw) as {
      baseRevision?: string
      messages?: TeacherProductionAiMessage[]
      phase?: TeacherProductionAiPhase
      clarificationOptions?: string[]
      sequence?: number
    }
    if (!Array.isArray(stored.messages) || !stored.messages.length) return false
    const baseMatches = String(stored.baseRevision || '') === currentAiBaseRevision.value
    aiMessages.value = stored.messages.filter(message => (
      message
      && typeof message.id === 'string'
      && typeof message.text === 'string'
      && (baseMatches || !['candidate', 'error'].includes(message.kind))
    ))
    if (!aiMessages.value.length) return false
    aiClarificationOptions.value = baseMatches && Array.isArray(stored.clarificationOptions)
      ? stored.clarificationOptions.filter(option => typeof option === 'string')
      : []
    aiMessageSequence.value = Math.max(Number(stored.sequence || 0), aiMessages.value.length)
    aiSessionScopeKey.value = currentAiScopeKey.value
    aiPhase.value = aiCandidatePending.value
      ? 'review'
      : baseMatches && stored.phase === 'clarifying'
        ? 'clarifying'
        : 'ready'
    return true
  } catch {
    return false
  }
}
function persistAiSession() {
  if (!aiSessionScopeKey.value || aiSessionScopeKey.value !== currentAiScopeKey.value || !aiMessages.value.length) return
  try {
    window.localStorage.setItem(aiSessionStorageKey(), JSON.stringify({
      baseRevision: currentAiBaseRevision.value,
      messages: aiMessages.value,
      phase: aiPhase.value,
      clarificationOptions: aiClarificationOptions.value,
      sequence: aiMessageSequence.value,
    }))
  } catch { /* local storage can be unavailable */ }
}
function openAiCollaboration(domain: TeacherProductionAiDomain) {
  if (domain === 'lesson' && (!selectedLesson.value || !workingLessonRevision.value)) return
  if (domain === 'script' && (!selectedLesson.value?.script.ready || !scriptDocument.value)) return
  if (domain === 'outline' && !outlineEditor.value) return
  if (aiDomain.value !== domain) {
    aiDomain.value = domain
    aiCandidate.value = null
  }
  aiSourcesOpen.value = false
  if (aiSessionScopeKey.value !== currentAiScopeKey.value || !aiMessages.value.length) {
    if (!restoreAiSession()) resetAiSession()
  }
  if (aiCandidatePending.value && !aiMessages.value.some(message => message.kind === 'candidate')) {
    appendRestoredAiCandidate()
    transitionAi({ type: 'CANDIDATE_RESTORED' })
  }
  aiCollaborationOpen.value = true
  transitionAi({ type: 'OPEN', candidatePending: aiCandidatePending.value })
}
function closeAiCollaboration() {
  aiCollaborationOpen.value = false
  aiSourcesOpen.value = false
}
function buildAiInstruction(): string {
  return buildTeacherProductionAiInstruction(aiMessages.value, {
    domain: aiDomain.value,
    courseTitle: props.courseTitle,
    primaryTitle: aiScopeTitle.value,
    secondaryTitle: aiScopeDetail.value,
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
  const document = activeAiDocument.value
  if (aiCollaborationBusy.value || !document) return
  lastAiOperation.value = 'generate'
  aiClarificationOptions.value = []
  transitionAi({ type: 'GENERATE' })
  if (aiCandidatePending.value) {
    replacingAiCandidate.value = true
    const discarded = await document.resolveAiCandidate(false).finally(() => {
      replacingAiCandidate.value = false
    })
    if (!discarded) return
    replacePreviousCandidateMessage()
  }
  const candidate = await document.requestAiCandidate(buildAiInstruction())
  if (!candidate) {
    if (aiPhase.value !== 'error') transitionAi({ type: 'FAIL' })
    return
  }
  aiCandidate.value = candidate
  appendAiMessage(
    'assistant',
    'candidate',
    aiDomain.value === 'outline'
      ? '大纲调整已在左侧展开，请核对整套差异。'
      : aiDomain.value === 'script'
        ? '讲稿候选已在左侧高亮，请核对表达和事实。'
        : t('courseWorkbench.aiCollaboration.candidateSummary', '候选已显示在左侧，请核对高亮内容。'),
  )
  transitionAi({ type: 'CANDIDATE_READY' })
  lastAiOperation.value = ''
  focusAiCandidate()
}
async function handleAiRequest(instruction: string) {
  const request = instruction.trim()
  if (!request || aiCollaborationBusy.value || !activeAiDocument.value) return
  appendAiMessage('user', 'text', request)
  if (assessTeacherProductionRequest(aiDomain.value, request) === 'clarify') {
    aiClarificationOptions.value = aiQuickActions.value.slice(0, 3).map(action => action.prompt)
    appendAiMessage(
      'assistant',
      'text',
      aiDomain.value === 'outline'
        ? '你希望先调整章节顺序、学习路径，还是合并重复内容？'
        : aiDomain.value === 'script'
          ? '你希望先调整口语表达、课堂案例，还是讲解节奏？'
          : t('courseWorkbench.aiCollaboration.clarificationQuestion', '为了避免整段重写，你希望优先调整哪一部分？'),
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
function handleAiCandidateChange(candidate: Record<string, any> | TeacherLessonPlanCandidate | null) {
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
  const objectName = aiDomain.value === 'outline' ? '大纲' : aiDomain.value === 'script' ? '讲稿' : '教案'
  const receipt = result.accept
    ? `候选已采用，并形成新的${objectName}工作修订。`
    : `候选已放弃，当前${objectName}保持不变。`
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
  const document = activeAiDocument.value
  if (!document || !aiCandidatePending.value || aiCollaborationBusy.value) return
  lastAiOperation.value = accept ? 'accept' : 'reject'
  transitionAi({ type: accept ? 'ACCEPT' : 'REJECT' })
  const resolved = await document.resolveAiCandidate(accept)
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
  const document = activeAiDocument.value
  if (document?.focusAiCandidate) document.focusAiCandidate()
  else document?.focusCandidate?.()
}
function updateAiPaneBounds() {
  const rootWidth = workbenchRoot.value?.getBoundingClientRect().width || window.innerWidth
  aiPaneMaxWidth.value = Math.max(AI_PANE_MIN_WIDTH, Math.min(AI_PANE_MAX_WIDTH, Math.floor(rootWidth - AI_CANVAS_MIN_WIDTH - 8)))
  aiPaneWidth.value = Math.min(aiPaneMaxWidth.value, Math.max(AI_PANE_MIN_WIDTH, Math.round(aiPaneWidth.value)))
}
function clampAiPaneWidth(value: number) {
  updateAiPaneBounds()
  aiPaneWidth.value = Math.min(aiPaneMaxWidth.value, Math.max(AI_PANE_MIN_WIDTH, Math.round(value)))
}
function handleAiPanePointerMove(event: PointerEvent) {
  const bounds = workbenchRoot.value?.getBoundingClientRect()
  if (!bounds?.width) return
  clampAiPaneWidth(bounds.right - event.clientX)
}
function stopAiPaneResize() {
  window.removeEventListener('pointermove', handleAiPanePointerMove)
  window.removeEventListener('pointerup', stopAiPaneResize)
  window.removeEventListener('pointercancel', stopAiPaneResize)
  aiPaneResizing.value = false
  document.documentElement.style.cursor = ''
  document.documentElement.style.userSelect = ''
  try { window.localStorage.setItem(AI_PANE_STORAGE_KEY, String(aiPaneWidth.value)) } catch { /* local storage can be unavailable */ }
}
function startAiPaneResize(event: PointerEvent) {
  if (event.button !== 0) return
  event.preventDefault()
  aiPaneResizing.value = true
  document.documentElement.style.cursor = 'col-resize'
  document.documentElement.style.userSelect = 'none'
  window.addEventListener('pointermove', handleAiPanePointerMove)
  window.addEventListener('pointerup', stopAiPaneResize)
  window.addEventListener('pointercancel', stopAiPaneResize)
}
function resizeAiPaneWithKeyboard(event: KeyboardEvent) {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
  event.preventDefault()
  if (event.key === 'Home') clampAiPaneWidth(AI_PANE_MIN_WIDTH)
  else if (event.key === 'End') clampAiPaneWidth(aiPaneMaxWidth.value)
  else clampAiPaneWidth(aiPaneWidth.value + (event.key === 'ArrowLeft' ? 24 : -24))
  try { window.localStorage.setItem(AI_PANE_STORAGE_KEY, String(aiPaneWidth.value)) } catch { /* local storage can be unavailable */ }
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
async function generateLessonPlan() {
  const lesson = selectedLesson.value
  if (!lesson || lessonBusy.value || lessonGenerationActive.value) return
  const arrangement = lesson.arrangement
  if (!arrangement?.lesson_type || !arrangement.blocks?.length) {
    lessonConfirmError.value = t('courseWorkbench.arrangement.autoPlanningUnavailable', '暂时无法准备本讲教学结构，请重新载入后再试。')
    return
  }
  lessonBusy.value = true
  lessonConfirmError.value = ''
  try {
    if (!arrangement.confirmed) {
      await lessonStore.confirmArrangement(props.courseId, selectedLessonId.value, {
        lesson_type: arrangement.lesson_type,
        blocks: arrangement.blocks,
      })
    }
    await saveRelationships(`lesson-plan:${selectedLessonId.value}`, 'lesson_plan', lesson.title)
    const primary = activeReferences.value.find(item => item.role === 'primary')
    await lessonStore.generateLesson(
      props.courseId,
      selectedLessonId.value,
      primary ? { packageId: primary.package_id, assetId: primary.asset_id } : undefined,
      lessonRequirements.value,
      activeReferences.value.map(item => item.material_asset_id),
    )
  } catch {
    lessonConfirmError.value = lessonStore.error || t('courseWorkbench.arrangement.confirmFailed', '本讲教学结构准备失败，请重试。')
  } finally {
    lessonBusy.value = false
  }
}
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
function selectLessonFromOutline(lessonId: string) {
  selectLesson(lessonId)
  if (selectedLessonId.value === lessonId) closeLessonOutline()
}
function toggleLessonOutline() {
  lessonOutlineOpen.value = !lessonOutlineOpen.value
}
function closeLessonOutline(restoreFocus = false) {
  if (!lessonOutlineOpen.value) return
  lessonOutlineOpen.value = false
  if (restoreFocus) lessonOutlineTrigger.value?.focus()
}
function closeLessonOutlineOnOutsidePointer(event: PointerEvent) {
  if (lessonOutlineOpen.value && !lessonOutlineRoot.value?.contains(event.target as Node)) closeLessonOutline()
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
  if (!selectedLesson.value || !confirmedLessonRevision.value || scriptGenerationBusy.value) return
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
      scriptJob.value?.status === 'failed' ? scriptJob.value.id : '',
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
watch(activeStage, stage => { if (stage !== 'foundation') editingOutline.value = false; closeAiCollaboration(); closeLessonOutline(); aiCandidate.value = null; if (workbenchCenter.value) workbenchCenter.value.scrollTop = 0 }, { flush: 'post' })
watch(aiCollaborationOpen, open => {
  if (open) closeLessonOutline()
  else aiSourcesOpen.value = false
})
watch([aiMessages, aiPhase, aiClarificationOptions], persistAiSession, { deep: true, flush: 'post' })
watch(lessonOutlineRoot, (root, _previousRoot, onCleanup) => {
  if (!root) return
  document.addEventListener('pointerdown', closeLessonOutlineOnOutsidePointer)
  onCleanup(() => document.removeEventListener('pointerdown', closeLessonOutlineOnOutsidePointer))
}, { flush: 'post' })
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
  if (previousLessonId && lessonId !== previousLessonId) closeAiCollaboration()
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
onMounted(() => {
  try {
    const storedWidth = Number(window.localStorage.getItem(AI_PANE_STORAGE_KEY))
    if (Number.isFinite(storedWidth) && storedWidth > 0) aiPaneWidth.value = storedWidth
  } catch { /* local storage can be unavailable */ }
  updateAiPaneBounds()
  window.addEventListener('resize', updateAiPaneBounds)
})
onBeforeUnmount(() => {
  stopAiPaneResize()
  window.removeEventListener('resize', updateAiPaneBounds)
})
</script>

<style scoped>
.teacher-workbench{height:100%;min-height:0;display:grid;grid-template-columns:210px minmax(520px,1fr) 310px;overflow:hidden;background:#f3f5f9}.stage-rail{min-height:0;display:flex;flex-direction:column;border-right:1px solid #e4e9f1;background:#fff}.stage-rail>header{display:grid;gap:4px;padding:21px 18px 16px}.stage-rail>header strong{color:#1f2a40;font-size:15px}.stage-rail>header small{color:#64748b;font-size:12px}.stage-rail nav{display:grid;gap:4px;padding:4px 9px}.stage-rail nav button{min-height:54px;display:grid;grid-template-columns:26px 22px minmax(0,1fr) 18px;align-items:center;gap:8px;padding:8px 10px;border:0;border-radius:10px;color:#64748b;background:transparent;text-align:left;cursor:pointer}.stage-rail nav button:hover{background:#f6f7fb}.stage-rail nav button.active{color:#4338ca;background:#eef0ff}.stage-rail nav button>span{font-size:15px;font-weight:800}.stage-rail nav strong{min-width:0;color:#334155;font-size:13px}.stage-rail nav button.active strong{color:#3730a3}.stage-rail nav button>svg:last-child{color:#16a34a}.stage-rail>footer{display:grid;grid-template-columns:auto minmax(0,1fr);align-items:center;gap:9px;margin-top:auto;padding:16px 18px;color:#64748b;font-size:12px}.stage-rail>footer>div{height:4px;overflow:hidden;border-radius:2px;background:#e8ecf3}.stage-rail>footer i{height:100%;display:block;background:#5b57e8}.workbench-center{min-width:0;min-height:0;overflow:auto;padding:24px 26px 52px}.center-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;max-width:860px;margin:0 auto 18px}.center-heading>div{display:grid;gap:4px}.center-heading small{color:#6366f1;font-size:11px;font-weight:800}.center-heading h2{margin:0;color:#172033;font-size:24px;letter-spacing:-.018em}.center-heading>button,.formal-surface>header button,.generation-surface>header button{min-height:36px;display:flex;align-items:center;gap:7px;padding:0 11px;border:1px solid #d7dde7;border-radius:8px;color:#475569;background:#fff;font-size:12px;font-weight:700;cursor:pointer}.stage-form,.formal-surface,.generation-surface,.lesson-stage{max-width:860px;margin:0 auto;border:1px solid #e0e6ef;border-radius:14px;background:#fff;box-shadow:0 10px 30px rgba(30,41,59,.05)}.stage-form{display:grid;gap:20px;padding:26px}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.form-field{display:grid;gap:8px}.form-field>span,.lesson-selector>span{color:#334155;font-size:13px;font-weight:700}.form-field b{color:#dc2626}.form-field input,.form-field select,.form-field textarea,.lesson-selector select{width:100%;min-height:44px;padding:10px 11px;border:1px solid #cfd7e3;border-radius:8px;outline:0;color:#172033;background:#fff;font:inherit;font-size:13px}.form-field textarea{resize:vertical;line-height:1.6}.form-field input:focus,.form-field select:focus,.form-field textarea:focus,.form-field textarea:focus,.lesson-selector select:focus{border-color:#5b57e8;box-shadow:0 0 0 3px rgba(91,87,232,.11)}.stage-form>footer{display:flex;align-items:center;justify-content:space-between;gap:16px;padding-top:2px}.stage-form>footer>span{color:#64748b;font-size:12px}.primary{min-height:42px;display:flex;align-items:center;gap:7px;padding:0 15px;border:1px solid #514bdc;border-radius:8px;color:#fff;background:#514bdc;font-size:13px;font-weight:750;cursor:pointer;box-shadow:0 7px 18px rgba(81,75,220,.16)}.primary:disabled{opacity:.48;cursor:not-allowed}.generation-surface{overflow:hidden}.generation-surface>header,.formal-surface>header{min-height:64px;display:flex;align-items:center;justify-content:space-between;gap:16px;padding:0 20px;border-bottom:1px solid #e7ebf2}.generation-surface>header>div{display:flex;align-items:center;gap:10px;color:#4f46e5}.generation-surface>header span,.formal-surface>header>div{display:grid;gap:3px}.generation-surface>header strong,.formal-surface>header strong{color:#263147;font-size:13px}.generation-surface>header small,.formal-surface>header small{color:#64748b;font-size:11px}.generation-progress{height:3px;background:#e8ebf5}.generation-progress i{width:100%;height:100%;display:block;transform-origin:left;background:#5b57e8;transition:transform .25s ease-out}.stream-content,.formal-surface>article{max-height:calc(100vh - 260px);overflow:auto;padding:22px 28px 42px}.stream-content section,.formal-surface article section{margin-bottom:26px}.stream-content h3,.formal-surface h3{margin:0 0 10px;color:#202b40;font-size:17px}.stream-waiting{min-height:260px;display:flex;align-items:center;justify-content:center;gap:9px;color:#64748b;font-size:13px}.stream-caret{width:2px;height:18px;display:inline-block;background:#5b57e8;animation:blink .8s steps(1) infinite}.generation-error{margin:0;padding:12px 20px;color:#b91c1c;background:#fff1f2;font-size:12px}.generation-error button{border:0;color:inherit;background:transparent;font-weight:750;text-decoration:underline;cursor:pointer}.lesson-stage{padding:0 0 24px}.lesson-selector{display:grid;grid-template-columns:110px minmax(0,1fr);align-items:center;gap:14px;padding:18px 22px;border-bottom:1px solid #e7ebf2}.stage-form--lesson{border:0;box-shadow:none}.prerequisite,.empty-asset{min-height:260px;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:10px;color:#64748b;font-size:13px}.prerequisite strong{color:#334155}.prerequisite button{padding:7px 10px;border:1px solid #d7dde7;border-radius:7px;color:#4f46e5;background:#fff;font-weight:700;cursor:pointer}.lesson-formal{margin:20px 20px 0;border-radius:10px;box-shadow:none}.lesson-formal>article{max-height:calc(100vh - 360px)}.formal-surface ol{display:grid;gap:8px;padding-left:22px;color:#475569;font-size:13px}.spin{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}@keyframes blink{50%{opacity:0}}
.stage-form>footer{justify-content:flex-end}
.teacher-workbench.is-ai-collaboration{grid-template-columns:minmax(560px,1fr) 10px var(--ai-pane-width);background:#eef1f6}.is-ai-collaboration>.workbench-center{padding:0;overflow:auto;background:#f3f5f9;scrollbar-width:thin;scrollbar-color:transparent transparent}.is-ai-collaboration>.workbench-center:hover{scrollbar-color:#cbd3df transparent}.is-ai-collaboration>.workbench-center::-webkit-scrollbar{width:6px}.is-ai-collaboration>.workbench-center::-webkit-scrollbar-thumb{border-radius:6px;background:transparent}.is-ai-collaboration>.workbench-center:hover::-webkit-scrollbar-thumb{background:#cbd3df}.is-ai-collaboration>.workbench-center>.center-heading{display:none}.is-ai-collaboration .lesson-stage{max-width:none;min-height:100%;margin:0;border:0;border-radius:0;box-shadow:none}.is-ai-collaboration .lesson-outline,.is-ai-collaboration .lesson-outline-toggle{display:none}.is-ai-collaboration .has-lesson-outline .lesson-workspace{display:block}.is-ai-collaboration .has-lesson-outline .lesson-stage-content{overflow:visible;border:0;border-radius:0;box-shadow:none}.is-ai-collaboration :deep(.lesson-document){min-height:100vh}.ai-workspace-resizer{position:relative;z-index:4;min-height:0;cursor:col-resize;background:#eef1f6;touch-action:none}.ai-workspace-resizer::before{position:absolute;inset:0;content:""}.ai-workspace-resizer::after{position:absolute;inset-block:0;left:50%;width:1px;background:#d9dee8;content:"";transform:translateX(-50%)}.ai-workspace-resizer i{position:absolute;z-index:1;top:50%;left:50%;width:3px;height:52px;border-radius:3px;background:#9aa3b5;opacity:.5;transform:translate(-50%,-50%) scaleY(.8);transition:transform .14s ease,opacity .14s ease,background-color .14s ease}.ai-workspace-resizer:hover,.ai-workspace-resizer:focus-visible,.ai-workspace-resizer.is-resizing{background:#f5f4ff}.ai-workspace-resizer:hover i,.ai-workspace-resizer:focus-visible i,.ai-workspace-resizer.is-resizing i{background:#625dd7;opacity:1;transform:translate(-50%,-50%) scaleY(1)}.ai-workspace-resizer:focus-visible{outline:2px solid #818cf8;outline-offset:-2px}
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
.lesson-stage{padding:0;overflow:hidden}.lesson-navigator{min-height:54px;display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:center;gap:14px;padding:0 20px;border-bottom:1px solid #e7ebf2;background:#fbfcfe}.lesson-navigator>button{min-height:36px;display:flex;align-items:center;gap:5px;padding:0 11px;border:1px solid #d9dcfa;border-radius:8px;color:#4338ca;background:#f3f2ff;font-size:12px;font-weight:750;cursor:pointer;transition:color .16s ease,border-color .16s ease,background .16s ease,transform .16s ease}.lesson-navigator>button:hover:not(:disabled){transform:translateY(-1px);border-color:#aaa7f2;color:#3730a3;background:#eae8ff}.lesson-navigator>button:focus-visible{outline:3px solid rgba(91,87,232,.18);outline-offset:2px}.lesson-navigator>button:disabled{border-color:transparent;color:#94a3b8;background:transparent;opacity:.48;cursor:not-allowed}.lesson-selector{min-width:0;display:flex;align-items:center;justify-content:center;gap:0;padding:0;border:0}.lesson-selector>span{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}.lesson-selector select{width:min(100%,560px);min-height:36px;padding:0 34px 0 12px;border:0;border-radius:7px;color:#263147;background:transparent;font-size:13px;font-weight:750;text-align:center;box-shadow:none}.lesson-selector select:hover{background:#f3f5fa}.lesson-selector select:focus{background:#fff}.stage-form>.lesson-form-actions{justify-content:flex-end}.stage-next-bar{min-height:64px;display:flex;align-items:center;justify-content:space-between;padding:12px 28px;border-top:1px solid #e8ecf2;background:#fbfcfe}.ppt-entry{min-height:180px;display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:center;gap:16px;padding:36px 28px}.ppt-entry>svg{color:#5b57e8}.ppt-entry>div{min-width:0;display:grid;gap:5px}.ppt-entry strong{color:#1f2a40;font-size:15px}.ppt-entry span{color:#64748b;font-size:12px}.question-workbench-surface{max-width:860px;margin:0 auto;padding:0;border:0;border-radius:0;box-shadow:none}
.lesson-generation-entry{display:grid;grid-template-columns:minmax(0,1fr) auto;grid-template-areas:"copy action" "focus focus";align-items:start;gap:15px 26px;padding:22px 28px 24px;background:#fff}.lesson-generation-copy{grid-area:copy;display:grid;gap:5px}.lesson-generation-copy strong{color:#202b40;font-size:18px;letter-spacing:-.015em}.lesson-generation-copy span{max-width:640px;color:#64748b;font-size:12px;line-height:1.55}.lesson-generation-entry>.primary{grid-area:action;min-height:38px;padding-inline:16px}.lesson-focus-field{grid-area:focus;display:grid;grid-template-columns:72px minmax(0,1fr);align-items:start;gap:14px;padding-top:12px;border-top:1px solid #e7ebf2}.lesson-focus-field>span{padding-top:8px;color:#64748b;font-size:12px}.lesson-focus-field textarea{width:100%;min-height:52px;padding:7px 8px;border:0;border-bottom:1px solid #cfd7e3;border-radius:0;outline:0;color:#263147;background:transparent;font:inherit;font-size:13px;line-height:1.55;resize:vertical}.lesson-focus-field textarea:hover{background:#fafbfc}.lesson-focus-field textarea:focus{border-color:#5b57e8;background:#fff}.lesson-focus-field textarea::placeholder{color:#667085}.lesson-generation-entry>.primary:focus-visible{outline:2px solid #5b57e8;outline-offset:2px}
.has-lesson-outline .lesson-workspace{grid-template-columns:190px minmax(0,1fr);gap:14px}.has-lesson-outline .lesson-workspace.is-outline-collapsed{grid-template-columns:minmax(0,1fr);gap:0}.lesson-outline{display:block;min-height:156px}.lesson-outline>nav{position:relative;padding:3px 0 3px 2px}.lesson-outline>nav::before{position:absolute;top:18px;bottom:18px;left:12px;width:1px;background:#dde3ec;content:""}.lesson-outline-chapter-button{position:relative;min-height:46px;grid-template-columns:20px minmax(0,1fr);gap:7px;padding:5px 7px 5px 2px;border-radius:8px}.lesson-outline-chapter-button:disabled{opacity:.48;cursor:not-allowed}.lesson-outline-chapter-marker{position:relative;z-index:1;width:6px;height:6px;border-color:#c4cedb;background:#f3f5f9}.lesson-outline-chapter-marker[data-state="generating"]{border-color:#6661dc;background:#6661dc}.lesson-outline-chapter-marker[data-state="review"]{border-color:#8884d8;background:#f3f2ff}.lesson-outline-chapter-marker[data-state="confirmed"]{border-color:#6661dc;background:#6661dc}.lesson-outline-chapter-marker[data-state="failed"]{border-color:#d75563;background:#d75563}.lesson-outline-chapter-copy{gap:1px}.lesson-outline-chapter-copy strong{color:#5e6b7e;font-size:11.5px;font-weight:620;line-height:1.4}.lesson-outline-chapter-copy small{color:#8a96a8;font-size:9.5px}.lesson-outline-chapter-copy small[data-state="review"]{color:#7773bd}.lesson-outline-chapter-copy small[data-state="failed"]{color:#b94b57}.lesson-outline-chapter-button:hover:not(:disabled){background:rgba(255,255,255,.52)}.lesson-outline-chapter-button.active{background:rgba(239,240,255,.62)}.lesson-outline-chapter-button.active .lesson-outline-chapter-marker{box-shadow:none}.lesson-outline-chapter-button.active strong{color:#34316f}.lesson-outline-chapter-button.active small{color:#6965b9}.lesson-outline-toggle{color:#596579!important;background:transparent!important;border-color:transparent!important;font-weight:650!important;box-shadow:none!important}.lesson-outline-toggle:hover{color:#3730a3!important;background:#f1f2f7!important}.lesson-section-tabs button:disabled{opacity:.5;cursor:not-allowed}
.teacher-workbench.is-ai-collaboration{grid-template-columns:minmax(0,1fr) 10px var(--ai-pane-width)}.lesson-navigator{grid-template-columns:auto auto minmax(0,1fr) auto;gap:8px}.is-ai-collaboration .lesson-navigator{grid-template-columns:auto minmax(0,1fr) auto}.lesson-selector select:disabled{color:#94a3b8;cursor:not-allowed}.lesson-outline-chapter-button:focus-visible,.lesson-section-tabs button:focus-visible{outline:2px solid #5b57e8;outline-offset:2px}
@media(max-width:1320px){.has-lesson-outline .lesson-workspace{grid-template-columns:184px minmax(0,1fr);gap:12px}.has-lesson-outline .lesson-workspace.is-outline-collapsed{grid-template-columns:minmax(0,1fr);gap:0}}
@media(max-width:760px){.lesson-navigator{gap:6px;padding-inline:10px}.lesson-navigator>button{font-size:0}.lesson-navigator>button svg{display:block}.lesson-selector select{padding-inline:8px;font-size:12px}.ppt-entry{grid-template-columns:auto minmax(0,1fr);padding:28px 18px}.ppt-entry .primary{grid-column:1/-1}}
.stage-rail nav button:disabled,.companion-entry>button:disabled{opacity:.45;cursor:not-allowed}.teacher-workbench.is-ai-collaboration{min-width:0;grid-template-columns:minmax(0,1fr) 10px var(--ai-pane-width);background:#eef1f6}.is-ai-collaboration>.workbench-center{min-width:0;overflow:auto}.is-ai-collaboration .has-lesson-outline .lesson-stage-content{min-width:0;overflow:hidden}.is-ai-collaboration .lesson-workspace,.is-ai-collaboration .lesson-stage,.is-ai-collaboration .outline-workspace{min-width:0;max-width:none}.is-ai-collaboration :deep(.lesson-document .flow-table){max-width:100%;overflow:auto}
@media(max-width:900px){.teacher-workbench.is-ai-collaboration{grid-template-columns:minmax(0,1fr) 8px 340px}.is-ai-collaboration>.workbench-center{padding:0}}
@media(prefers-reduced-motion:reduce){.has-lesson-outline .lesson-workspace{transition:none}.lesson-outline-chapter-marker[data-state="generating"]{animation:none}}

/* Lesson navigation keeps the document full width; the course outline appears only when requested. */
.has-lesson-outline .lesson-workspace{display:block}
.has-lesson-outline .lesson-stage-content{overflow:visible}
.lesson-navigator{position:relative;z-index:5;grid-template-columns:auto minmax(0,1fr) auto;overflow:visible}
.lesson-current-group{min-width:0;display:flex;align-items:center;justify-content:center;gap:8px}
.lesson-current-group .lesson-selector{flex:0 1 auto;max-width:calc(100% - 104px)}
.lesson-current-group .lesson-selector select{width:auto;max-width:100%}
.lesson-outline-control{position:relative;align-self:center}
.lesson-outline-trigger{min-height:34px;display:flex;align-items:center;gap:6px;padding:0 10px;border:1px solid #dde2eb;border-radius:8px;color:#536176;background:#fff;font-size:12px;font-weight:700;cursor:pointer;transition:border-color .16s ease,color .16s ease,background-color .16s ease,box-shadow .16s ease}
.lesson-outline-trigger:hover,.lesson-outline-trigger[aria-expanded="true"]{border-color:#c8c9ee;color:#403b9f;background:#f7f7ff}
.lesson-outline-trigger:focus-visible{outline:3px solid rgba(91,87,232,.16);outline-offset:2px}
.lesson-outline-trigger small{padding-left:6px;border-left:1px solid #e3e7ee;color:#8994a5;font-size:10px;font-weight:750;font-variant-numeric:tabular-nums}
.lesson-outline-popover{position:absolute;z-index:30;top:calc(100% + 9px);left:0;width:286px;max-height:min(480px,calc(100vh - 190px));overflow:auto;padding:7px;border-radius:12px;background:#fff;box-shadow:0 16px 42px rgba(30,41,59,.16);animation:lesson-outline-in .16s cubic-bezier(.16,1,.3,1)}
.lesson-outline-chapter-button{min-height:44px;display:grid;grid-template-columns:25px minmax(0,1fr) 18px;align-items:center;gap:8px;width:100%;padding:0 9px;border:0;border-radius:8px;color:#536176;background:transparent;text-align:left;cursor:pointer}
.lesson-outline-chapter-button:hover:not(:disabled){background:#f5f7fa}
.lesson-outline-chapter-button.active{color:#37348c;background:#f0f1ff}
.lesson-outline-chapter-button:disabled{opacity:.46;cursor:not-allowed}
.lesson-outline-chapter-button:focus-visible{outline:2px solid #5b57e8;outline-offset:-2px}
.lesson-outline-chapter-index{color:#9aa5b5;font-size:10px;font-weight:750;font-variant-numeric:tabular-nums}
.lesson-outline-chapter-button.active .lesson-outline-chapter-index{color:#6a66ce}
.lesson-outline-chapter-button strong{min-width:0;overflow:hidden;color:inherit;font-size:12.5px;font-weight:620;line-height:1.35;text-overflow:ellipsis;white-space:nowrap}
.lesson-outline-status{width:18px;height:18px;display:grid;place-items:center;justify-self:end;color:#a8b2c1}
.lesson-outline-status[data-state="generating"],.lesson-outline-status[data-state="confirmed"]{color:#625dd7}
.lesson-outline-status[data-state="failed"]{color:#c94c5a}
.lesson-outline-status i{width:7px;height:7px;border:1px solid #b8c2d0;border-radius:50%;background:#fff}
.lesson-outline-status[data-state="review"] i{border-color:#8b87dc;background:#8b87dc}
.is-ai-collaboration .lesson-outline-control{display:none}
.is-ai-collaboration .lesson-navigator{grid-template-columns:auto minmax(0,1fr) auto}
@keyframes lesson-outline-in{from{opacity:.5;transform:translateY(-5px) scale(.985)}to{opacity:1;transform:none}}
@media(min-width:1051px){.teacher-workbench:not(.is-ai-collaboration){grid-template-columns:196px minmax(520px,1fr) 310px}}
@media(prefers-reduced-motion:reduce){.lesson-outline-popover{animation:none}}

.teacher-workbench{position:relative}
.teacher-workbench.is-ai-collaboration{grid-template-columns:minmax(0,1fr) 8px var(--ai-pane-width);background:#f4f6f9}
.ai-workspace-resizer{z-index:6;display:grid;place-items:center;background:#f4f6f9}
.ai-workspace-resizer::after{background:#dfe4ec}
.ai-workspace-resizer>svg{position:relative;z-index:1;width:20px;height:32px;padding:8px 3px;border-radius:7px;color:#9aa6b6;background:#fff;box-shadow:0 0 0 1px #dfe4ec;opacity:0;transition:color .16s ease,opacity .16s ease,box-shadow .16s ease}
.ai-workspace-resizer:hover>svg,.ai-workspace-resizer:focus-visible>svg,.ai-workspace-resizer.is-resizing>svg{color:#5b57d9;box-shadow:0 0 0 1px #c8c6f1;opacity:1}
.ai-workspace-resizer:hover,.ai-workspace-resizer:focus-visible,.ai-workspace-resizer.is-resizing{background:#f4f6f9}
.ai-source-drawer{position:absolute;z-index:10;top:0;right:calc(var(--ai-pane-width) + 8px);bottom:0;width:min(340px,calc(100% - var(--ai-pane-width) - 72px));border-left:0;box-shadow:0 18px 50px rgba(30,41,59,.14);animation:ai-source-drawer-in .18s cubic-bezier(.16,1,.3,1)}
@keyframes ai-source-drawer-in{from{opacity:0;transform:translateX(8px)}to{opacity:1;transform:none}}
@media(max-width:900px){.teacher-workbench.is-ai-collaboration{grid-template-columns:minmax(0,1fr) 8px 340px}.ai-source-drawer{right:348px;width:min(320px,calc(100% - 420px))}}
@media(prefers-reduced-motion:reduce){.ai-workspace-resizer>svg{transition:none}.ai-source-drawer{animation:none}}
</style>
