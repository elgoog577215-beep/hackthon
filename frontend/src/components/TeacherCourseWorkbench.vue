<template>
  <section
    ref="workbenchRoot"
    class="teacher-workbench"
    :class="{
      'is-ai-collaboration': aiCollaborationOpen && activeStage === 'question-bank',
      'is-question-bank-workspace': activeStage === 'question-bank',
      'is-lesson-plan-stage': activeStage === 'lesson',
      'is-ppt-stage': activeStage === 'ppt',
    }"
    :style="{ '--ai-pane-width': `${aiPaneWidth}px` }"
  >
    <aside v-show="!aiCollaborationOpen || activeStage !== 'question-bank'" class="stage-rail" :aria-label="t('courseWorkbench.stageNavigation', '课程生产阶段')">
      <header>
        <strong class="stage-rail-title">{{ t('courseWorkbench.title', '课程工作台') }}</strong>
      </header>
      <nav>
        <button v-for="stage in stages" :key="stage.id" type="button" :class="{ active: activeStage === stage.id }" :disabled="stageSwitching || (aiCandidatePending && activeStage !== stage.id)" @click="requestStageChange(stage.id)">
          <span>{{ stage.step }}</span><component :is="stage.icon" :size="18" /><strong>{{ stage.label }}</strong><Check v-if="stageReady(stage.id)" :size="15" />
        </button>
      </nav>
      <section class="companion-entry">
        <small>{{ t('courseWorkbench.supporting.group', '其他课程文件') }}</small>
        <button type="button" :class="{ active: activeStage === 'question-bank' }" :disabled="stageSwitching || (aiCandidatePending && activeStage !== 'question-bank')" @click="requestStageChange('question-bank')">
          <ListChecks :size="18" /><strong>{{ t('courseWorkbench.stages.questionBank', '题库') }}</strong><ChevronRight :size="16" />
        </button>
        <button type="button" :class="{ active: activeStage === 'companion' && activeCompanionTemplateId === GRADING_RUBRIC_TEMPLATE_ID }" :disabled="stageSwitching || (aiCandidatePending && activeStage !== 'companion')" @click="openCompanionTemplate(GRADING_RUBRIC_TEMPLATE_ID)">
          <ClipboardCheck :size="18" /><strong>{{ t('courseWorkbench.supporting.gradingRubric', '评分细则') }}</strong><ChevronRight :size="16" />
        </button>
        <button type="button" :class="{ active: activeStage === 'companion' && activeCompanionTemplateId === MATERIAL_CHECKLIST_TEMPLATE_ID }" :disabled="stageSwitching || (aiCandidatePending && activeStage !== 'companion')" @click="openCompanionTemplate(MATERIAL_CHECKLIST_TEMPLATE_ID)">
          <CheckSquare2 :size="18" /><strong>{{ t('courseWorkbench.supporting.materialChecklist', '考试课程材料自查清单') }}</strong><ChevronRight :size="16" />
        </button>
      </section>
      <footer><span>{{ readyStageCount }}/4</span><div><i :style="{ width: `${readyStageCount / 4 * 100}%` }" /></div></footer>
    </aside>

    <main
      ref="workbenchCenter"
      class="workbench-center"
      :class="{
        'is-outline-workspace': showOutlineWorkspace,
        'is-lesson-workspace': !['foundation', 'companion'].includes(activeStage),
      }"
    >
      <header v-if="activeStage === 'foundation'" class="center-heading">
        <div><small>{{ activeStageDefinition.step }} / 04</small><h2>{{ activeStageDefinition.label }}</h2></div>
      </header>

      <template v-if="showOutlineWorkspace">
        <TeacherDocumentCommandBar
          :label="t('courseWorkbench.outlineDocument.actions', '大纲操作')"
          :editing="editingOutline"
          :can-undo="outlineCanUndo"
          :can-redo="outlineCanRedo"
          :disabled="stageSwitching || outlineConfirming || aiCollaborationBusy"
          :history-open="historyOpen && historyDomain === 'outline'"
          :history-count="outlineHistoryCount"
          :status-label="outlineDocumentStatusLabel"
          :status-tone="outlineDocumentStatusTone"
          @undo="outlineEditor?.undoEdit()"
          @redo="outlineEditor?.redoEdit()"
          @history="toggleDocumentHistory('outline')"
        >
          <button
            class="outline-manual-action"
            :class="{ 'primary-action': !outlineAwaitingReview }"
            data-testid="outline-manual-action"
            type="button"
            :aria-pressed="editingOutline"
            :disabled="stageSwitching || outlineConfirming"
            @click="toggleOutlineEditing"
          >
            <Check v-if="editingOutline" :size="15" />
            <Pencil v-else :size="15" />
            {{ editingOutline
              ? t('courseWorkbench.finishOutlineEditing', '完成编辑')
              : t('courseWorkbench.editOutline', '编辑大纲') }}
          </button>
          <button
            v-if="outlineAwaitingReview"
            class="primary-action outline-confirm-action"
            data-testid="outline-confirm-action"
            type="button"
            :disabled="stageSwitching || outlineConfirming"
            @click="confirmInlineOutline"
          >
            <LoaderCircle v-if="outlineConfirming" :size="15" class="spin" />
            <Check v-else :size="15" />
            {{ t('courseWorkbench.confirmOutline', '确认课程大纲') }}
          </button>
        </TeacherDocumentCommandBar>
        <TeacherDocumentHistoryPanel
          v-if="historyOpen && historyDomain === 'outline'"
          title="大纲历史版本"
          :items="documentHistoryItems"
          :restoring-id="historyRestoringId"
          :restore-disabled="editingOutline"
          @close="closeDocumentHistory"
          @restore="restoreDocumentHistory"
        />
      </template>

      <section v-if="showStreaming" class="generation-surface" aria-live="polite">
        <header>
          <div><TriangleAlert v-if="generationFailed" :size="18" /><LoaderCircle v-else :size="18" class="spin" /><span><strong>{{ generationFailed ? t('courseWorkbench.generationInterrupted', '生成已中断') : t('courseWorkbench.generating', '正在生成课程大纲') }}</strong><small>{{ generationFailed ? generationErrorPresentation?.summary : currentGenerationLabel }}</small></span></div>
          <div v-if="generationRunning" class="generation-header-actions">
            <button type="button" @click="stopGeneration"><Pause :size="15" />{{ t('courseWorkbench.pause', '暂停') }}</button>
            <button type="button" @click="cancelOutlineGeneration"><X :size="15" />{{ t('common.cancel', '取消') }}</button>
          </div>
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
          <LoaderCircle :size="22" class="spin" />
          <div><strong>{{ t('courseWorkbench.shapeReview.lectureContinuing', '讲数已经确认，正在继续生成课程大纲') }}</strong><small>{{ t('courseWorkbench.shapeReview.lectureAdapterHelp', '系统正在整理每一讲的内容与前后关系，不需要再填写章或小节。') }}</small></div>
          <AppErrorNotice v-if="shapeConfirmErrorPresentation" class="shape-confirm-error" :presentation="shapeConfirmErrorPresentation" compact />
        </article>
      </section>

      <section
        v-else-if="showOutlineWorkspace"
        class="formal-surface outline-workspace"
        :class="{ 'is-outline-editing': editingOutline }"
        data-testid="outline-workspace"
      >
        <CourseOutlineReview
          ref="outlineEditor"
          class="inline-outline-review"
          :course-id="courseId"
          :course-name="courseTitle"
          :nodes="courseStore.nodes"
          :task="generationTask"
          :editable="editingOutline"
          :requires-confirmation="outlineAwaitingReview"
          confirmation-placement="external"
          :assistant-open="aiCollaborationOpen && aiDomain === 'outline'"
          variant="inline"
          surface="teacher"
          @confirmed="handleInlineOutlineConfirmed"
          @open-ai="openAiCollaboration('outline')"
          @ai-candidate-change="handleAiCandidateChange"
          @ai-resolving="handleAiResolving"
          @ai-resolved="handleAiResolved"
          @ai-error="handleAiError"
        />
      </section>

      <form v-else-if="activeStage === 'foundation'" class="stage-form" @submit.prevent="submitFoundation">
        <label class="form-field form-field--wide"><span>{{ foundationGoalLabel }} <b>*</b></span><textarea v-model.trim="foundation.goal" required rows="4" :placeholder="foundationGoalPlaceholder" /></label>
        <div class="form-grid">
          <label class="form-field"><span>{{ t('courseWorkbench.form.totalHours', '总学时') }}</span><input v-model.number="foundation.totalHours" type="number" min="1" max="1000" /></label>
          <label class="form-field"><span>{{ t('courseWorkbench.form.lectureCount', '计划讲数') }} <b>*</b></span><input v-model.number="foundation.lectureCount" type="number" min="1" max="1000" required /></label>
        </div>
        <section class="foundation-semantics" aria-labelledby="foundation-semantics-title">
          <header>
            <div>
              <strong id="foundation-semantics-title">{{ t('courseWorkbench.form.teachingPlan', '教学编排') }}</strong>
              <span>{{ t('courseWorkbench.form.teachingPlanHelp', '学习目的决定结果，学科类型决定专业方法，课程教学类型决定整课怎样组织。') }}</span>
            </div>
            <small>{{ t('courseWorkbench.form.courseLevel', '整课级') }}</small>
          </header>
          <div class="foundation-semantic-row">
            <div>
              <strong>{{ t('courseWorkbench.form.learningPurpose', '学习目的') }}</strong>
              <span>{{ t('courseWorkbench.form.learningPurposeHelp', '为什么学，最终要得到什么') }}</span>
            </div>
            <div class="foundation-semantic-options foundation-semantic-options--three">
              <button
                v-for="option in learningPurposeOptions"
                :key="option.value"
                type="button"
                :class="{ selected: foundation.learningPurpose === option.value }"
                :aria-pressed="foundation.learningPurpose === option.value"
                @click="selectLearningPurpose(option.value)"
              >
                <Check v-if="foundation.learningPurpose === option.value" :size="13" />
                <span><strong>{{ option.label }}</strong><small>{{ option.description }}</small></span>
              </button>
            </div>
          </div>
          <div class="foundation-semantic-row foundation-semantic-row--compact">
            <div>
              <strong>{{ t('courseWorkbench.form.subjectType', '学科类型') }}</strong>
              <span>{{ t('courseWorkbench.form.subjectTypeHelp', '这类知识怎样建立、练习和验证') }}</span>
            </div>
            <label class="foundation-subject-select">
              <span class="sr-only">{{ t('courseWorkbench.form.subjectType', '学科类型') }}</span>
              <select v-model="foundation.subjectType">
                <option v-for="option in subjectTypeOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
              </select>
              <small>{{ selectedSubjectTypeDescription }}</small>
            </label>
          </div>
          <div class="foundation-semantic-row">
            <div>
              <strong>{{ t('courseWorkbench.form.courseTeachingType', '课程教学类型') }}</strong>
              <span>{{ t('courseWorkbench.form.courseTeachingTypeHelp', '整门课主要用什么方式教') }}</span>
            </div>
            <div class="foundation-semantic-options foundation-semantic-options--six">
              <button
                v-for="option in courseTeachingTypeOptions"
                :key="option.value"
                type="button"
                :class="{ selected: foundation.courseTeachingType === option.value }"
                :aria-pressed="foundation.courseTeachingType === option.value"
                @click="foundation.courseTeachingType = option.value"
              >
                <Check v-if="foundation.courseTeachingType === option.value" :size="13" />
                <span><strong>{{ option.label }}</strong><small>{{ option.description }}</small></span>
              </button>
            </div>
          </div>
          <div v-if="foundation.learningPurpose === 'project'" class="foundation-purpose-fields">
            <label class="form-field form-field--wide"><span>{{ t('courseWorkbench.form.projectDeliverable', '项目成果') }} <b>*</b></span><input v-model.trim="foundation.projectDeliverable" required maxlength="500" :placeholder="t('courseWorkbench.form.projectDeliverablePlaceholder', '例如：完成一套可运行原型及设计说明')" /></label>
          </div>
          <div v-else-if="foundation.learningPurpose === 'exam'" class="foundation-purpose-fields foundation-purpose-fields--two">
            <label class="form-field"><span>{{ t('courseWorkbench.form.examDate', '考试日期') }} <b>*</b></span><input v-model="foundation.examDate" required type="date" /></label>
            <label class="form-field"><span>{{ t('courseWorkbench.form.examScope', '考试范围') }} <b>*</b></span><input v-model.trim="foundation.examScope" required maxlength="1000" :placeholder="t('courseWorkbench.form.examScopePlaceholder', '例如：教材第 1—8 章与课堂重点')" /></label>
          </div>
        </section>
        <label class="form-field form-field--wide"><span>{{ t('courseWorkbench.form.requirements', '补充要求') }}</span><textarea v-model.trim="foundation.requirements" rows="4" :placeholder="t('courseWorkbench.form.requirementsPlaceholder', '例如：部分讲次安排案例讨论，兼顾理论与实践')" /></label>
        <footer>
          <span>{{ t('courseWorkbench.form.semanticHint', '系统先规划整课的课型分布，再为每一讲编排可调整的教学块。') }}</span>
          <button class="primary" type="submit" :disabled="generationStarting || !foundationReady"><Sparkles :size="16" />{{ t('courseWorkbench.generateOutline', '生成课程大纲') }}</button>
        </footer>
      </form>

      <CompanionDocumentStudio
        v-else-if="activeStage === 'companion'"
        :course-id="courseId"
        :template-id="activeCompanionTemplateId"
        :show-template-picker="false"
        @saved="handleCompanionSaved"
      />

      <section v-else class="lesson-stage" :class="{ 'has-lesson-outline': ['lesson', 'script'].includes(activeStage) && lessonStore.lessons.length && !outlineGatePending }">
        <div class="lesson-workspace">
          <div class="lesson-stage-content">
        <nav
          v-if="lessonStore.lessons.length && !outlineGatePending"
          class="lesson-navigator"
          :class="{ 'has-document-actions': lessonPageHeaderVisible }"
          :aria-label="t('courseWorkbench.lessonNavigation', '课次导航')"
        >
          <div class="lesson-heading-cluster">
            <div class="lesson-current-group">
              <div ref="lessonOutlineRoot" class="lesson-outline-control">
              <button
                ref="lessonOutlineTrigger"
                class="lesson-title-trigger"
                type="button"
                :aria-expanded="lessonOutlineOpen"
                :aria-label="`${t('courseWorkbench.lessonOutline.trigger', '目录')}：${selectedLesson?.title || t('courseWorkbench.form.chooseLesson', '请选择课次')}，${selectedLessonPosition}/${lessonStore.lessons.length}`"
                aria-controls="lesson-outline-navigation"
                :disabled="aiCandidatePending"
                @click="toggleLessonOutline"
              >
                <strong>{{ selectedLesson?.title || t('courseWorkbench.form.chooseLesson', '请选择课次') }}</strong>
                <small>{{ selectedLessonPosition }}/{{ lessonStore.lessons.length }}</small>
                <ChevronDown class="lesson-title-chevron" :size="15" aria-hidden="true" />
              </button>
              <nav
                v-if="lessonOutlineOpen"
                id="lesson-outline-navigation"
                class="lesson-outline-popover"
                :aria-label="t('courseWorkbench.lessonOutline.title', '讲次目录')"
                @keydown.esc.stop.prevent="closeLessonOutline(true)"
              >
                <button
                  v-for="lesson in lessonStore.lessons"
                  :key="lesson.lesson_unit_id"
                  class="lesson-outline-chapter-button"
                  type="button"
                  :class="{ active: selectedLessonId === lesson.lesson_unit_id }"
                  :disabled="aiCandidatePending && selectedLessonId !== lesson.lesson_unit_id"
                  :aria-current="selectedLessonId === lesson.lesson_unit_id ? 'page' : undefined"
                  :aria-label="`${lesson.title}，${lessonGenerationStateLabel(lesson)}`"
                  @click="selectLessonFromOutline(lesson.lesson_unit_id)"
                >
                  <strong>{{ lesson.title }}</strong>
                  <span
                    class="lesson-outline-status"
                    :data-state="lessonGenerationState(lesson)"
                    :title="lessonGenerationStateLabel(lesson)"
                    aria-hidden="true"
                  >
                    <LoaderCircle v-if="lessonGenerationIsRunning(lesson)" :size="14" class="spin" />
                    <Check v-else-if="lessonGenerationState(lesson) === 'confirmed'" :size="14" />
                    <TriangleAlert v-else-if="['needs_review', 'failed'].includes(lessonGenerationState(lesson))" :size="14" />
                    <i v-else />
                  </span>
                </button>
              </nav>
              </div>
            </div>
            <div v-if="lessonPageHeaderVisible && !(activeStage === 'lesson' && lessonToolbarVisible)" class="lesson-toolbar-status" role="status">
              <LoaderCircle v-if="lessonHeaderBusy" :size="14" class="spin" />
              <Sparkles v-else-if="aiCandidatePending" :size="14" />
              <Pencil v-else-if="lessonHeaderEditing" :size="14" />
              <Check v-else-if="lessonHeaderConfirmed" :size="14" />
              <TriangleAlert v-else-if="activeStage === 'ppt' && pptNeedsRefresh" :size="14" />
              <Presentation v-else-if="activeStage === 'ppt'" :size="14" />
              <span>{{ lessonHeaderStatusLabel }}</span>
            </div>
          </div>
          <div class="lesson-switch-actions">
            <button type="button" :disabled="!previousLesson || aiCandidatePending" @click="selectLesson(previousLesson?.lesson_unit_id)"><ChevronLeft :size="15" />{{ t('courseWorkbench.previousLesson', '上一讲') }}</button>
            <button type="button" :disabled="!nextLesson || aiCandidatePending" @click="selectLesson(nextLesson?.lesson_unit_id)">{{ t('courseWorkbench.nextLesson', '下一讲') }}<ChevronRight :size="15" /></button>
          </div>
        </nav>
        <TeacherLessonArrangementSummary
          v-if="activeStage === 'lesson' && !lessonStageBlocked && selectedLesson?.arrangement?.blocks?.length"
          :arrangement="selectedLesson.arrangement"
          :impact-labels="lessonArrangementImpactLabels"
          :selected-lesson-type="selectedLessonTypeDraft"
          :busy="arrangementConfirming"
          :generating="lessonGenerationActive"
          :sticky-actions="lessonGenerationActionsVisible || lessonGenerationRunning"
          :supporting="Boolean(workingLessonRevision && !lessonGenerationActive)"
          :error="arrangementError || lessonGenerationError"
          @update:selected-lesson-type="selectedLessonTypeDraft = $event"
          @confirm="confirmSelectedLessonArrangement"
        >
          <template #generation-actions>
            <div
              v-if="lessonGenerationActionsVisible"
              class="lesson-generation-actions"
              data-testid="lesson-generation-actions"
            >
              <button
                data-testid="lesson-single-start"
                type="button"
                :disabled="!selectedLessonCanGenerate || batchStarting"
                :title="selectedLessonCanGenerate ? '' : t('courseWorkbench.lessonBatch.confirmFirst', '请先确认本讲课型与教学结构')"
                @click="generateSelectedLessonPlan"
              >
                <Sparkles :size="16" />
                {{ t('courseWorkbench.arrangement.generateLesson', '只生成本讲') }}
              </button>
              <button
                v-if="lessonBatchLaunchVisible || batchStarting"
                class="primary-action"
                data-testid="lesson-batch-start"
                type="button"
                :disabled="batchStarting"
                @click="generateAllLessonPlans"
              >
                <LoaderCircle v-if="batchStarting" :size="16" class="spin" />
                <Sparkles v-else :size="16" />
                {{ batchStarting
                  ? t('courseWorkbench.lessonBatch.starting', '正在开始…')
                  : t('courseWorkbench.lessonBatch.generateAllCount', '生成全部教案（{count}讲）').replace('{count}', String(batchEligibleCount)) }}
              </button>
            </div>
            <div v-else-if="lessonGenerationRunning" class="lesson-generation-toolbar-status" aria-live="polite">
              <LoaderCircle :size="17" class="spin" />
              <strong>{{ t('courseWorkbench.lessonBatch.generatingCurrent', '正在生成{lesson}').replace('{lesson}', selectedLesson?.title || '') }}</strong>
              <em>{{ Math.min(100, Math.round(lessonGenerationProgress)) }}%</em>
            </div>
          </template>
        </TeacherLessonArrangementSummary>

        <TeacherDocumentCommandBar
          v-if="activeStage === 'lesson' && lessonToolbarVisible"
          class="lesson-command-bar"
          :label="t('courseWorkbench.lessonDocument.actions', '教案操作')"
          :editing="lessonDocumentEditing"
          :can-undo="lessonCanUndo"
          :can-redo="lessonCanRedo"
          :disabled="lessonConfirming || aiCollaborationBusy"
          :history-open="historyOpen && historyDomain === 'lesson'"
          :history-count="lessonHistoryCount"
          :status-label="lessonHeaderStatusLabel"
          :status-tone="documentStatusTone"
          @undo="lessonPlanDocument?.undoEdit()"
          @redo="lessonPlanDocument?.redoEdit()"
          @history="toggleDocumentHistory('lesson')"
        >
            <template v-if="aiCandidatePending">
              <button type="button" :disabled="aiCollaborationBusy" @click="openAiCollaboration('lesson')"><Sparkles :size="15" />{{ t('courseWorkbench.lessonDocument.aiCandidate', 'AI 方案') }}</button>
              <button type="button" :disabled="aiCollaborationBusy" @click="resolveAiCandidate(false)"><X :size="15" />{{ t('courseWorkbench.lessonDocument.discardAi', '放弃') }}</button>
              <button class="primary-action" type="button" :disabled="aiCollaborationBusy" @click="resolveAiCandidate(true)">
                <LoaderCircle v-if="aiCollaborationBusy" :size="15" class="spin" />
                <Check v-else :size="15" />
                {{ aiCollaborationBusy ? t('courseWorkbench.lessonDocument.applyingAi', '正在采用…') : t('courseWorkbench.lessonDocument.applyAi', '采用') }}
              </button>
            </template>
            <template v-else-if="lessonDocumentEditing">
              <button type="button" :disabled="lessonDocumentSaving" @click="cancelLessonPlanEditing"><X :size="15" />{{ t('courseWorkbench.lessonDocument.cancel', '取消') }}</button>
              <button class="primary-action" type="button" :disabled="lessonDocumentSaving" @click="saveLessonPlanDraft">
                <LoaderCircle v-if="lessonDocumentSaving" :size="15" class="spin" />
                <Check v-else :size="15" />
                {{ lessonDocumentSaving ? t('courseWorkbench.lessonDocument.saving', '正在保存…') : t('courseWorkbench.lessonDocument.finishEditing', '完成编辑') }}
              </button>
            </template>
            <template v-else>
              <button type="button" :disabled="lessonDocumentAiBusy || lessonConfirming" @click="openAiCollaboration('lesson')"><Sparkles :size="15" />{{ t('courseWorkbench.lessonDocument.aiImprove', 'AI 修改') }}</button>
              <button type="button" :disabled="lessonConfirming" @click="beginLessonPlanEditing"><Pencil :size="15" />{{ t('courseWorkbench.lessonDocument.edit', '编辑教案') }}</button>
              <button
                v-if="!lessonPlanConfirmed"
                class="primary-action"
                type="button"
                :disabled="lessonConfirming || lessonDocumentQualityBlocked"
                :title="lessonDocumentQualityBlocked ? lessonDocumentQualityBlockMessage : ''"
                @click="confirmLessonPlan"
              >
                <LoaderCircle v-if="lessonConfirming" :size="15" class="spin" />
                <Check v-else :size="15" />
                {{ lessonConfirming
                  ? t('courseWorkbench.confirmingLessonPlan', '正在确认…')
                  : t('courseWorkbench.confirmLessonPlan', '确认本讲教案') }}
              </button>
            </template>
        </TeacherDocumentCommandBar>
        <TeacherDocumentHistoryPanel
          v-if="activeStage === 'lesson' && historyOpen && historyDomain === 'lesson'"
          title="教案历史版本"
          :items="documentHistoryItems"
          :restoring-id="historyRestoringId"
          :restore-disabled="lessonDocumentEditing"
          @close="closeDocumentHistory"
          @restore="restoreDocumentHistory"
        />
        <AppErrorNotice v-if="lessonStageBlocked && lessonPrerequisiteError" class="prerequisite-error" :presentation="lessonPrerequisiteError" compact>
          <template #action><button type="button" :disabled="lessonStore.loading" @click="resolveLessonPrerequisite">{{ lessonPrerequisiteState.action }}</button></template>
        </AppErrorNotice>
        <div v-else-if="lessonStageBlocked" class="prerequisite" :data-state="lessonPrerequisiteState.kind" aria-live="polite">
          <LoaderCircle v-if="lessonPrerequisiteState.kind === 'loading'" :size="24" class="spin" />
          <FileText v-else :size="24" />
          <strong>{{ lessonPrerequisiteState.title }}</strong>
          <span>{{ lessonPrerequisiteState.detail }}</span>
          <button v-if="lessonPrerequisiteState.action" type="button" :disabled="lessonStore.loading" @click="resolveLessonPrerequisite">{{ lessonPrerequisiteState.action }}</button>
        </div>

        <template v-else-if="activeStage === 'question-bank'">
          <QuestionBankReviewPanel
            ref="questionBankPanel"
            class="question-workbench-surface"
            :course-id="courseId"
            :course-title="courseTitle"
            :assistant-open="aiCollaborationOpen && aiDomain === 'question-bank'"
            @updated="handleQuestionBankUpdated"
            @open-ai="openAiCollaboration('question-bank')"
            @ai-candidate-change="handleAiCandidateChange"
            @ai-resolving="handleAiResolving"
            @ai-resolved="handleAiResolved"
            @ai-error="handleAiError"
            @import-mode-change="questionBankImportMode = $event"
            @references-change="handleQuestionBankReferencesChange"
          />
        </template>

        <template v-else-if="activeStage === 'lesson'">
          <template v-if="lessonGenerationRunning">
            <div v-if="!selectedLesson?.arrangement?.blocks?.length" class="lesson-generation-status" aria-live="polite">
              <div>
                <LoaderCircle :size="17" class="spin" />
                <span>
                  <strong>{{ t('courseWorkbench.lessonBatch.generatingCurrent', '正在生成{lesson}').replace('{lesson}', selectedLesson?.title || '') }}</strong>
                  <small>{{ lessonJob?.message || t('courseWorkbench.lessonStreamWaiting', '正在组织教案结构…') }}</small>
                </span>
              </div>
              <em>{{ Math.min(100, Math.round(lessonGenerationProgress)) }}%</em>
            </div>
            <article v-if="lessonStreamSegments.length" class="lesson-stream-document" :aria-label="t('courseWorkbench.lessonStreamDraft', 'AI 工作稿')">
              <small>{{ t('courseWorkbench.lessonStreamDraft', 'AI 工作稿') }}</small>
              <p v-for="(segment, index) in lessonStreamSegments" :key="`${index}-${segment}`">
                {{ segment }}<span v-if="index === lessonStreamSegments.length - 1" class="stream-caret" />
              </p>
            </article>
            <div v-else class="lesson-stream-waiting">{{ t('courseWorkbench.lessonStreamWaiting', '正在组织教案结构…') }}</div>
          </template>
          <div v-else-if="selectedLesson && !workingLessonRevision && lessonGenerationQueued" class="lesson-queue-state" aria-live="polite">
            <LoaderCircle :size="22" />
            <strong>{{ t('courseWorkbench.lessonBatch.waitingTitle', '等待按顺序生成') }}</strong>
            <p>{{ t('courseWorkbench.lessonBatch.waitingDetail', '上一讲完成后，系统会自动生成本讲，不需要再次操作。') }}</p>
          </div>
          <div v-else-if="selectedLesson && !workingLessonRevision && !selectedLesson.arrangement?.blocks?.length" class="lesson-empty-canvas" aria-live="polite">
            <span>{{ t('courseWorkbench.lessonBatch.empty', '教案尚未生成') }}</span>
          </div>
          <TeacherLessonPlanDocument
            v-else-if="workingLessonRevision && selectedLesson"
            ref="lessonPlanDocument"
            :course-id="courseId"
            :course-title="courseTitle"
            :lesson="selectedLesson"
            :confirmed="lessonPlanConfirmed"
            :assistant-open="aiCollaborationOpen && aiDomain === 'lesson'"
            :confirming="lessonConfirming"
            :confirm-error="lessonConfirmError"
            :active-section-id="selectedLessonSectionId"
            :material-asset-ids="activeReferences.map(item => item.material_asset_id)"
            external-toolbar
            @update:active-section-id="selectLessonSection(selectedLesson.lesson_unit_id, $event)"
            @confirm="confirmLessonPlan"
            @open-ai="openAiCollaboration('lesson')"
            @ai-candidate-change="handleAiCandidateChange"
            @ai-resolving="handleAiResolving"
            @ai-resolved="handleAiResolved"
            @ai-error="handleAiError"
            @open-ai-selection="openAiFromSelection('lesson', $event)"
          />
        </template>

        <template v-else-if="activeStage === 'script'">
          <TeacherScriptDocument
            v-if="selectedLesson"
            ref="scriptDocument"
            :course-id="courseId"
            :lesson="selectedLesson"
            :assistant-open="aiCollaborationOpen && aiDomain === 'script'"
            :material-asset-ids="activeReferences.map(item => item.asset_id)"
            :confirmed="scriptConfirmed"
            :confirming="scriptConfirming"
            :confirm-error="scriptConfirmError"
            :generating="scriptGenerationBusy"
            :generation-job="scriptJob"
            :generation-error="effectiveScriptGenerationError"
            :can-generate="Boolean(confirmedLessonRevision)"
            external-toolbar
            @generate="generateScript"
            @pause-generation="pauseScriptGeneration"
            @cancel-generation="cancelScriptGeneration"
            @saved="handleScriptSaved"
            @confirm="confirmScript"
            @open-ai="openAiCollaboration('script')"
            @ai-candidate-change="handleAiCandidateChange"
            @ai-resolving="handleAiResolving"
            @ai-resolved="handleAiResolved"
            @ai-error="handleAiError"
            @ai-scope-change="handleScriptAiScopeChange"
            @open-ai-selection="openAiFromSelection('script', $event)"
          >
            <template #toolbar>
              <TeacherDocumentCommandBar
                v-if="scriptToolbarVisible"
                :label="t('courseWorkbench.scriptDocument.actions', '讲义操作')"
                :editing="scriptDocumentEditing"
                :can-undo="scriptCanUndo"
                :can-redo="scriptCanRedo"
                :disabled="scriptConfirming || aiCollaborationBusy"
                :history-open="historyOpen && historyDomain === 'script'"
                :history-count="scriptHistoryCount"
                :status-label="lessonHeaderStatusLabel"
                :status-tone="documentStatusTone"
                @undo="scriptDocument?.undoEdit()"
                @redo="scriptDocument?.redoEdit()"
                @history="toggleDocumentHistory('script')"
              >
                  <template v-if="aiCandidatePending">
                    <button type="button" :disabled="aiCollaborationBusy" @click="openAiCollaboration('script')"><Sparkles :size="15" />{{ t('courseWorkbench.scriptDocument.aiCandidate', 'AI 方案') }}</button>
                    <button type="button" :disabled="aiCollaborationBusy" @click="resolveAiCandidate(false)"><X :size="15" />{{ t('courseWorkbench.scriptDocument.discardAi', '放弃') }}</button>
                    <button class="primary-action" type="button" :disabled="aiCollaborationBusy" @click="resolveAiCandidate(true)">
                      <LoaderCircle v-if="aiCollaborationBusy" :size="15" class="spin" />
                      <Check v-else :size="15" />
                      {{ aiCollaborationBusy ? t('courseWorkbench.scriptDocument.applyingAi', '正在采用…') : t('courseWorkbench.scriptDocument.applyAi', '采用') }}
                    </button>
                  </template>
                  <template v-else-if="scriptDocumentEditing">
                    <button type="button" :disabled="scriptDocumentSaving" @click="cancelScriptEditing"><X :size="15" />{{ t('courseWorkbench.scriptDocument.cancel', '取消') }}</button>
                    <button class="primary-action" type="button" :disabled="scriptDocumentSaving" @click="saveScriptDraft">
                      <LoaderCircle v-if="scriptDocumentSaving" :size="15" class="spin" />
                      <Check v-else :size="15" />
                      {{ scriptDocumentSaving ? t('courseWorkbench.scriptDocument.saving', '正在保存…') : t('courseWorkbench.scriptDocument.finishEditing', '完成编辑') }}
                    </button>
                  </template>
                  <template v-else>
                    <button type="button" :disabled="scriptDocumentAiBusy || scriptConfirming" @click="openAiCollaboration('script')"><Sparkles :size="15" />{{ t('courseWorkbench.scriptDocument.aiImprove', 'AI 修改') }}</button>
                    <button type="button" :disabled="scriptConfirming" @click="beginScriptEditing"><Pencil :size="15" />{{ t('courseWorkbench.scriptDocument.edit', '编辑讲义') }}</button>
                    <button v-if="!scriptConfirmed && !scriptPublicationEligible" class="primary-action" type="button" :disabled="scriptGenerationBusy || scriptConfirming" :title="scriptPublicationBlockReason" @click="generateScript()">
                      <LoaderCircle v-if="scriptGenerationBusy" :size="15" class="spin" />
                      <RefreshCw v-else :size="15" />
                      {{ scriptGenerationBusy ? t('courseWorkbench.scriptGenerating', '正在生成…') : t('courseWorkbench.scriptRegenerate', '重新生成本讲讲义') }}
                    </button>
                    <button v-else-if="!scriptConfirmed" class="primary-action" type="button" :disabled="scriptConfirming" @click="confirmScript">
                      <LoaderCircle v-if="scriptConfirming" :size="15" class="spin" />
                      <Check v-else :size="15" />
                      {{ scriptConfirming ? t('courseWorkbench.scriptDocument.confirming', '正在确认…') : t('courseWorkbench.scriptDocument.confirm', '确认本讲讲义') }}
                    </button>
                  </template>
              </TeacherDocumentCommandBar>
              <TeacherDocumentHistoryPanel
                v-if="historyOpen && historyDomain === 'script'"
                :title="t('courseWorkbench.scriptDocument.historyTitle', '讲义历史版本')"
                :items="documentHistoryItems"
                :restoring-id="historyRestoringId"
                :restore-disabled="scriptDocumentEditing"
                @close="closeDocumentHistory"
                @restore="restoreDocumentHistory"
              />
            </template>
          </TeacherScriptDocument>
        </template>

        <template v-else-if="activeStage === 'ppt'">
          <UploadedPptReviewWorkspace
            v-if="selectedLesson"
            :course-id="courseId"
            :course-title="courseTitle"
            :lesson-id="selectedLesson.lesson_unit_id"
            :lesson-title="selectedLesson.title"
            :can-generate="Boolean(confirmedLessonRevision && scriptConfirmed)"
            :reference-count="activeReferences.length"
            :prepare-sources="preparePptSources"
            @generate="openPptWorkspace"
            @confirmed="lessonStore.load(courseId)"
          />
        </template>
          </div>
        </div>
      </section>
    </main>

    <div
      v-if="aiCollaborationOpen && activeStage === 'question-bank'"
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

    <aside v-if="activeStage !== 'question-bank'" class="context-pane" :class="{ 'is-ai-tab': contextPaneTab === 'ai' }" :aria-label="t('courseWorkbench.contextPane.title', '工作台侧栏')">
      <nav class="context-pane-tabs" role="tablist" :aria-label="t('courseWorkbench.contextPane.title', '工作台侧栏')">
        <button
          type="button"
          role="tab"
          :aria-selected="contextPaneTab === 'ai'"
          :disabled="!contextAiAvailable"
          @click="openContextAiTab"
        ><Sparkles :size="14" />{{ t('courseWorkbench.contextPane.ai', 'AI 助手') }}</button>
        <button
          type="button"
          role="tab"
          :aria-selected="contextPaneTab === 'references'"
          @click="showReferenceTab"
        ><FileText :size="14" />{{ t('courseWorkbench.contextPane.references', '课程资料') }}<small>{{ activeReferences.length }}</small></button>
      </nav>

      <TeacherLessonAiWorkspace
        v-if="contextPaneTab === 'ai' && aiCollaborationOpen"
        class="ai-workspace-panel"
        embedded
        :domain="aiDomain"
        :scope-title="aiScopeTitle"
        :scope-detail="aiScopeDetail"
        :scope-options="aiScopeOptions"
        :scope-value="currentAiScopeId"
        :reference-count="aiActiveReferences.length"
        :reference-labels="aiActiveReferences.map(item => item.source_label || item.filename)"
        :messages="aiMessages"
        :phase="aiPhase"
        :busy="aiCollaborationBusy"
        :candidate-pending="aiCandidatePending"
        :candidate-fields="aiCandidateFieldLabels"
        :candidate-impacts="aiCandidateImpacts"
        :clarification-options="aiClarificationOptions"
        :quick-actions="aiQuickActions"
        :placeholder="aiPlaceholder"
        :selection-text="aiSelectionContext"
        :can-retry="Boolean(lastAiOperation)"
        @change-scope="changeAiScope"
        @open-sources="showReferenceTab"
        @clear-selection="aiSelectionContext = ''"
        @send="handleAiRequest"
        @clarify="handleAiClarification"
        @retry="retryAiAction"
        @accept="resolveAiCandidate(true)"
        @reject="resolveAiCandidate(false)"
        @focus-candidate="focusAiCandidate"
        @open-course-plan="planId => emit('open-course-adjustment', { planId })"
      />

      <CourseReferenceTray
        v-else
        v-model="activeReferences"
        class="context-pane-references"
        :course-id="courseId"
        :stage="activeStage"
        :lesson-id="activeReferenceLessonId"
        :scope-target-id="lessonReferenceTargetId"
        :scope-target-type="lessonReferenceTargetType"
        :scope-target-label="selectedLesson?.title || ''"
        :scope-target-position="selectedLessonPosition"
        :previous-scope-target-id="previousLessonReferenceTargetId"
        :refresh-token="materialRefreshToken"
        :workflow-state="referenceWorkflowState"
        :workflow-detail="referenceWorkflowDetail"
        :workflow-progress="referenceWorkflowProgress"
        :workflow-can-pause="referenceWorkflowCanPause"
        :workflow-can-resume="referenceWorkflowCanResume"
        :workflow-can-cancel="referenceWorkflowCanCancel"
        :workflow-can-retry="referenceWorkflowCanRetry"
        @open-course-information="emit('open-course-information')"
        @pause-workflow="pauseReferenceWorkflow"
        @resume-workflow="resumeReferenceWorkflow"
        @cancel-workflow="cancelReferenceWorkflow"
        @retry-workflow="retryReferenceWorkflow"
      />
    </aside>

    <TeacherLessonAiWorkspace
      v-else-if="aiCollaborationOpen"
      class="ai-workspace-panel"
      :domain="aiDomain"
      :scope-title="aiScopeTitle"
      :scope-detail="aiScopeDetail"
      :scope-options="aiScopeOptions"
      :scope-value="currentAiScopeId"
      :reference-count="aiActiveReferences.length"
      :reference-labels="aiActiveReferences.map(item => item.source_label || item.filename)"
      :sources-open="true"
      :messages="aiMessages"
      :phase="aiPhase"
      :busy="aiCollaborationBusy"
      :candidate-pending="aiCandidatePending"
      :candidate-fields="aiCandidateFieldLabels"
      :candidate-impacts="aiCandidateImpacts"
      :clarification-options="aiClarificationOptions"
      :quick-actions="aiQuickActions"
      :placeholder="aiPlaceholder"
      :can-retry="Boolean(lastAiOperation)"
      @close="closeAiCollaboration"
      @change-scope="changeAiScope"
      @open-sources="handleAiSourcesOpen"
      @send="handleAiRequest"
      @clarify="handleAiClarification"
      @retry="retryAiAction"
      @accept="resolveAiCandidate(true)"
      @reject="resolveAiCandidate(false)"
      @focus-candidate="focusAiCandidate"
      @open-course-plan="planId => emit('open-course-adjustment', { planId })"
    />
  </section>
</template>

<script setup lang="ts">
import { computed, markRaw, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { BookOpenText, Check, CheckSquare2, ChevronDown, ChevronLeft, ChevronRight, ClipboardCheck, ClipboardList, FileText, GripVertical, Layers3, ListChecks, LoaderCircle, Pause, Pencil, Presentation, RefreshCw, Sparkles, TriangleAlert, X } from 'lucide-vue-next'
import AppErrorNotice from './AppErrorNotice.vue'
import CompanionDocumentStudio from './CompanionDocumentStudio.vue'
import CourseOutlineReview from './CourseOutlineReview.vue'
import CourseReferenceTray, { type CourseReferenceItem, type CourseReferenceWorkflowState } from './CourseReferenceTray.vue'
import MarkdownRenderer from './MarkdownRenderer.vue'
import OutlineGrowthStream from './OutlineGrowthStream.vue'
import QuestionBankReviewPanel from './QuestionBankReviewPanel.vue'
import TeacherLessonAiWorkspace, { type TeacherAiQuickAction, type TeacherAiScopeOption } from './TeacherLessonAiWorkspace.vue'
import TeacherLessonArrangementSummary from './TeacherLessonArrangementSummary.vue'
import TeacherDocumentCommandBar from './TeacherDocumentCommandBar.vue'
import TeacherDocumentHistoryPanel, { type TeacherDocumentHistoryItem } from './TeacherDocumentHistoryPanel.vue'
import TeacherLessonPlanDocument from './TeacherLessonPlanDocument.vue'
import TeacherScriptDocument from './TeacherScriptDocument.vue'
import UploadedPptReviewWorkspace from './UploadedPptReviewWorkspace.vue'
import {
  buildTeacherCourseChangeInstruction,
  buildTeacherProductionAiInstruction,
  changedTeacherLessonFields,
  projectTeacherCoursePlan,
  routeTeacherProductionRequest,
  teacherProductionAiBusy,
  transitionTeacherProductionAiPhase,
  type TeacherProductionAiDomain,
  type TeacherProductionAiEvent,
  type TeacherProductionAiMessage,
  type TeacherProductionAiPhase,
  type TeacherProductionAiScope,
  type TeacherCoursePlanProjection,
} from '../composables/useTeacherProductionAiCollaboration'
import { t } from '../shared/i18n'
import {
  canonicalizeCourseGenerationOptions,
  type CourseGenerationOptions,
  type CourseTeachingType,
  type LearningPurpose,
  type PedagogyModeSelection,
} from '../shared/prompt-config'
import { useCourseStore } from '../stores/course'
import { useCourseEvolutionStore } from '../stores/courseEvolution'
import { useCourseWorkspaceStore } from '../stores/courseWorkspace'
import { useGenerationStore } from '../stores/generation'
import { lessonPlanStreamSegments, useTeacherLessonAuthoringStore, type TeacherLessonJob, type TeacherLessonPlanCandidate } from '../stores/teacherLessonAuthoring'
import { toAppError } from '../utils/app-error'
import http, { teacherReadRequestConfig, teacherRequestConfig } from '../utils/http'
import { createUuid } from '../utils/client-id'

type CoreStageId = 'foundation' | 'lesson' | 'script' | 'ppt'
type StageId = CoreStageId | 'question-bank' | 'companion'
type CompanionTemplateId = typeof GRADING_RUBRIC_TEMPLATE_ID | typeof MATERIAL_CHECKLIST_TEMPLATE_ID
const GRADING_RUBRIC_TEMPLATE_ID = 'zju-grading-rubric-v1'
const MATERIAL_CHECKLIST_TEMPLATE_ID = 'zju-exam-course-material-checklist-v1'
type LessonPlanDocumentHandle = {
  requestAiCandidate: (instruction: string) => Promise<TeacherLessonPlanCandidate | null>
  resolveAiCandidate: (accept: boolean) => Promise<boolean>
  focusCandidate: () => void
  editing: boolean
  saving: boolean
  aiBusy: boolean
  qualityBlocked: boolean
  qualityBlockMessage: string
  beginEditing: () => void
  cancelEditing: () => void
  saveDraft: () => Promise<void>
  canUndo: boolean
  canRedo: boolean
  undoEdit: () => boolean
  redoEdit: () => boolean
}
type ProductionAiDocumentHandle = {
  requestAiCandidate: (instruction: string) => Promise<Record<string, any> | null>
  resolveAiCandidate: (accept: boolean) => Promise<boolean>
  focusAiCandidate?: () => void
  focusCandidate?: () => void
  focusReferenceSources?: () => void
  selectAiScope?: (scopeId: string) => boolean
}
type ScriptDocumentHandle = ProductionAiDocumentHandle & {
  editing: boolean
  saving: boolean
  aiBusy: boolean
  beginEditing: () => void
  cancelEditing: () => void
  saveDraft: () => Promise<void>
  canUndo: boolean
  canRedo: boolean
  undoEdit: () => boolean
  redoEdit: () => boolean
}
type AiLessonPlanModule = {
  module_id?: string
  planned_minutes?: number | null
  teacher_activity?: string
  student_activity?: string
}
type AiLessonPlanSection = {
  node_id: string
  learning_objective?: string
  key_points?: unknown[]
  key_difficulties?: unknown[]
  in_class_checks?: unknown[]
  teaching_modules?: AiLessonPlanModule[]
}
type OutlineEditorHandle = ProductionAiDocumentHandle & {
  finishEditing: () => Promise<boolean>
  confirmOutline: () => Promise<void>
  dirty: boolean
  canUndo: boolean
  canRedo: boolean
  undoEdit: () => void
  redoEdit: () => void
  restoreHistoryVersion: (historyEntryId: string) => Promise<boolean>
}
const props = withDefaults(defineProps<{ courseId: string; courseTitle: string; generationOptions: CourseGenerationOptions & { subject?: string }; generationStarting?: boolean; materialRefreshToken?: number; initialStage?: StageId; initialLessonId?: string; outlineEditing?: boolean }>(), { materialRefreshToken: 0, initialStage: 'foundation', initialLessonId: '', outlineEditing: false })
const emit = defineEmits<{
  (event: 'generateOutline', payload: { subject: string; options: CourseGenerationOptions; references: CourseReferenceItem[] }): void
  (event: 'update:outlineEditing', value: boolean): void
  (event: 'outlineConfirmed'): void
  (event: 'open-course-information'): void
  (event: 'open-course-adjustment', payload: { planId: string }): void
}>()
const courseStore = useCourseStore(); const courseEvolutionStore = useCourseEvolutionStore(); const courseWorkspaceStore = useCourseWorkspaceStore(); const generationStore = useGenerationStore(); const lessonStore = useTeacherLessonAuthoringStore()
const activeStage = ref<StageId>(props.initialStage); const selectedLessonId = ref(props.initialLessonId)
const activeCompanionTemplateId = ref<CompanionTemplateId>(GRADING_RUBRIC_TEMPLATE_ID)
const stageSwitching = ref(false)
const outlineConfirming = ref(false)
const selectedLessonSectionId = ref('')
const lessonOutlineOpen = ref(false)
const lessonOutlineRoot = ref<HTMLElement | null>(null)
const lessonOutlineTrigger = ref<HTMLButtonElement | null>(null)
const workbenchRoot = ref<HTMLElement | null>(null)
const workbenchCenter = ref<HTMLElement | null>(null)
const lessonPlanDocument = ref<LessonPlanDocumentHandle | null>(null)
const scriptDocument = ref<ScriptDocumentHandle | null>(null)
const questionBankPanel = ref<ProductionAiDocumentHandle | null>(null)
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
const contextPaneTab = ref<'ai' | 'references'>('references')
const aiSelectionContext = ref('')
const aiMessages = ref<TeacherProductionAiMessage[]>([])
const aiSessionScopeKey = ref('')
const aiMessageSequence = ref(0)
const aiClarificationOptions = ref<string[]>([])
const lastAiOperation = ref<'generate' | 'course_plan' | 'accept' | 'reject' | ''>('')
const lastAiCoursePlanRequestId = ref('')
const replacingAiCandidate = ref(false)
const outlineEditor = ref<OutlineEditorHandle | null>(null)
type TeacherHistoryDomain = 'outline' | 'lesson' | 'script'
const historyOpen = ref(false)
const historyDomain = ref<TeacherHistoryDomain>('outline')
const historyRestoringId = ref('')
const editingOutline = computed({
  get: () => props.outlineEditing,
  set: value => emit('update:outlineEditing', value),
})
const referencesByScope = reactive<Record<string, CourseReferenceItem[]>>({})
const activeReferenceScope = computed(() => (
  ['lesson', 'script', 'ppt'].includes(activeStage.value) && selectedLessonId.value
    ? `${activeStage.value}:${selectedLessonId.value}`
    : activeStage.value
))
const activeReferences = computed({
  get: () => referencesByScope[activeReferenceScope.value] || [],
  set: value => { referencesByScope[activeReferenceScope.value] = value },
})
const questionBankReferences = ref<CourseReferenceItem[]>([])
const aiActiveReferences = computed(() => aiDomain.value === 'question-bank'
  ? questionBankReferences.value
  : activeReferences.value)
const activeReferenceLessonId = computed(() => ['lesson', 'script', 'ppt'].includes(activeStage.value) ? selectedLessonId.value : '')
const foundation = reactive({
  goal: '',
  totalHours: 32,
  lectureCount: 16,
  requirements: '',
  learningPurpose: 'systematic' as LearningPurpose,
  subjectType: 'auto' as PedagogyModeSelection,
  courseTeachingType: 'comprehensive' as CourseTeachingType,
  projectDeliverable: '',
  examDate: '',
  examScope: '',
})
const learningPurposeOptions = computed(() => [
  { value: 'systematic' as const, label: t('courseWorkbench.form.learningPurposes.systematic', '系统学习'), description: t('courseWorkbench.form.learningPurposes.systematicHelp', '形成完整知识与能力结构') },
  { value: 'project' as const, label: t('courseWorkbench.form.learningPurposes.project', '项目实战'), description: t('courseWorkbench.form.learningPurposes.projectHelp', '完成可展示、可评价的成果') },
  { value: 'exam' as const, label: t('courseWorkbench.form.learningPurposes.exam', '期末冲刺'), description: t('courseWorkbench.form.learningPurposes.examHelp', '限时补齐重点并通过测评') },
])
const subjectTypeOptions = computed(() => [
  { value: 'auto' as const, label: t('courseWorkbench.form.subjectTypes.auto', '自动判断'), description: t('courseWorkbench.form.subjectTypes.autoHelp', '根据课程名称、目标和资料识别') },
  { value: 'general' as const, label: t('courseWorkbench.form.subjectTypes.general', '通用课程'), description: t('courseWorkbench.form.subjectTypes.generalHelp', '用概念、案例与综合应用建立理解') },
  { value: 'math_formal' as const, label: t('courseWorkbench.form.subjectTypes.math', '数学与形式科学'), description: t('courseWorkbench.form.subjectTypes.mathHelp', '强调定义、推导、证明与解题') },
  { value: 'programming_engineering' as const, label: t('courseWorkbench.form.subjectTypes.engineering', '编程与工程技术'), description: t('courseWorkbench.form.subjectTypes.engineeringHelp', '强调设计、实现、调试与验证') },
  { value: 'natural_science' as const, label: t('courseWorkbench.form.subjectTypes.science', '自然科学'), description: t('courseWorkbench.form.subjectTypes.scienceHelp', '强调模型、实验、观察与证据') },
  { value: 'life_medical' as const, label: t('courseWorkbench.form.subjectTypes.medical', '生命科学与医学基础'), description: t('courseWorkbench.form.subjectTypes.medicalHelp', '强调机制、证据、决策与安全') },
  { value: 'humanities_social' as const, label: t('courseWorkbench.form.subjectTypes.humanities', '人文社科'), description: t('courseWorkbench.form.subjectTypes.humanitiesHelp', '强调文本、语境、论证与多元解释') },
  { value: 'language_learning' as const, label: t('courseWorkbench.form.subjectTypes.language', '语言学习'), description: t('courseWorkbench.form.subjectTypes.languageHelp', '强调输入、输出、互动与纠错') },
  { value: 'business_career' as const, label: t('courseWorkbench.form.subjectTypes.business', '商业与职业技能'), description: t('courseWorkbench.form.subjectTypes.businessHelp', '强调场景、工具、决策与成果') },
])
const courseTeachingTypeOptions = computed(() => [
  { value: 'theory' as const, label: t('courseWorkbench.form.courseTeachingTypes.theory', '理论课'), description: t('courseWorkbench.form.courseTeachingTypes.theoryHelp', '概念、原理与推导为主') },
  { value: 'laboratory' as const, label: t('courseWorkbench.form.courseTeachingTypes.laboratory', '实验课'), description: t('courseWorkbench.form.courseTeachingTypes.laboratoryHelp', '实验、观察与证据为主') },
  { value: 'practice' as const, label: t('courseWorkbench.form.courseTeachingTypes.practice', '实践课'), description: t('courseWorkbench.form.courseTeachingTypes.practiceHelp', '示范、操作与反馈为主') },
  { value: 'seminar' as const, label: t('courseWorkbench.form.courseTeachingTypes.seminar', '研讨课'), description: t('courseWorkbench.form.courseTeachingTypes.seminarHelp', '问题、案例与讨论为主') },
  { value: 'project' as const, label: t('courseWorkbench.form.courseTeachingTypes.project', '项目课'), description: t('courseWorkbench.form.courseTeachingTypes.projectHelp', '阶段成果与评审迭代为主') },
  { value: 'comprehensive' as const, label: t('courseWorkbench.form.courseTeachingTypes.comprehensive', '综合课'), description: t('courseWorkbench.form.courseTeachingTypes.comprehensiveHelp', '按内容组合多种方式') },
])
const selectedSubjectTypeDescription = computed(() => subjectTypeOptions.value.find(option => option.value === foundation.subjectType)?.description || '')
const foundationGoalLabel = computed(() => ({
  systematic: t('courseWorkbench.form.learningGoal', '教学目标'),
  project: t('courseWorkbench.form.projectGoal', '项目目标'),
  exam: t('courseWorkbench.form.examGoal', '冲刺目标'),
}[foundation.learningPurpose]))
const foundationGoalPlaceholder = computed(() => ({
  systematic: t('courseWorkbench.form.learningGoalPlaceholder', '学生完成课程后能够……'),
  project: t('courseWorkbench.form.projectGoalPlaceholder', '学生将围绕什么真实任务完成项目……'),
  exam: t('courseWorkbench.form.examGoalPlaceholder', '学生需要在考试前重点达到什么水平……'),
}[foundation.learningPurpose]))
const foundationReady = computed(() => Boolean(
  foundation.goal.trim()
  && Number.isInteger(Number(foundation.lectureCount))
  && Number(foundation.lectureCount) > 0
  && (foundation.learningPurpose !== 'project' || foundation.projectDeliverable.trim())
  && (foundation.learningPurpose !== 'exam' || (foundation.examDate && foundation.examScope.trim()))
))
const foundationSemanticRequirement = computed(() => {
  const purpose = learningPurposeOptions.value.find(option => option.value === foundation.learningPurpose)?.label || ''
  const subject = subjectTypeOptions.value.find(option => option.value === foundation.subjectType)?.label || ''
  const teachingType = courseTeachingTypeOptions.value.find(option => option.value === foundation.courseTeachingType)?.label || ''
  return [`学习目的：${purpose}`, `学科类型：${subject}`, `课程教学类型：${teachingType}`].join('\n')
})
const loadedShapeRevision = ref('')
const shapeConfirming = ref(false)
const shapeConfirmError = ref<unknown>(null)
const batchStarting = ref(false)
const LESSON_SYNC_RETRY_DELAYS = [0, 1200, 3200] as const
const lessonSyncAttempt = ref(0)
const lessonSyncRunning = ref(false)
const lessonSyncRetryScheduled = ref(false)
let lessonSyncRetryTimer: number | null = null
const arrangementConfirming = ref(false)
const arrangementError = ref('')
const selectedLessonTypeDraft = ref('')
const lessonConfirming = ref(false); const lessonConfirmError = ref(''); const scriptGenerating = ref(false); const scriptGenerationError = ref(''); const scriptConfirming = ref(false); const scriptConfirmError = ref(''); const generationRequested = ref(false)
const retainedOutlineGrowth = ref<Record<string, any> | null>(null)
const questionBankReady = ref(false)
const questionBankImportMode = ref(false)
const questionBankRevisionId = ref('')
const stages = computed(() => [
  { id: 'foundation' as const, step: '01', label: t('courseWorkbench.stages.foundation', '大纲'), icon: markRaw(Layers3) },
  { id: 'lesson' as const, step: '02', label: t('courseWorkbench.stages.lesson', '教案'), icon: markRaw(ClipboardList) },
  { id: 'script' as const, step: '03', label: t('courseWorkbench.stages.script', '讲义'), icon: markRaw(BookOpenText) },
  { id: 'ppt' as const, step: '04', label: t('courseWorkbench.stages.ppt', 'PPT'), icon: markRaw(Presentation) },
])
const activeStageDefinition = computed(() => stages.value.find(item => item.id === activeStage.value) || {
  id: activeStage.value === 'question-bank' ? 'question-bank' as const : 'companion' as const,
  step: '',
  label: activeStage.value === 'question-bank'
    ? t('courseWorkbench.stages.questionBank', '题库')
    : activeCompanionTemplateId.value === GRADING_RUBRIC_TEMPLATE_ID
      ? t('courseWorkbench.supporting.gradingRubric', '评分细则')
      : t('courseWorkbench.supporting.materialChecklist', '考试课程材料自查清单'),
  icon: markRaw(activeStage.value === 'question-bank'
    ? ListChecks
    : activeCompanionTemplateId.value === GRADING_RUBRIC_TEMPLATE_ID ? ClipboardCheck : CheckSquare2),
})
const selectedLesson = computed(() => lessonStore.lessons.find(item => item.lesson_unit_id === selectedLessonId.value))
const selectedLessonPosition = computed(() => {
  const index = lessonStore.lessons.findIndex(item => item.lesson_unit_id === selectedLessonId.value)
  return index >= 0 ? index + 1 : 1
})
const selectedLessonSectionTitle = computed(() => selectedLesson.value?.sections.find(
  item => item.section_node_id === selectedLessonSectionId.value,
)?.title || '')
const aiScriptSectionId = ref('')
const aiScriptSectionTitle = ref('')
const aiScopeTitle = computed(() => ['outline', 'question-bank'].includes(aiDomain.value)
  ? props.courseTitle
  : selectedLesson.value?.title || props.courseTitle)
const aiScopeDetail = computed(() => {
  if (aiDomain.value === 'outline') return t('courseWorkbench.aiCollaboration.outlineScope', '课程大纲')
  if (aiDomain.value === 'question-bank') return t('courseWorkbench.aiCollaboration.questionBankScope', '整门课程题库')
  if (aiDomain.value === 'script') return aiScriptSectionTitle.value || t('courseWorkbench.aiCollaboration.scriptScope', '当前讲义内容')
  return selectedLessonSectionTitle.value || t('courseWorkbench.aiCollaboration.lessonScope', '整讲教案')
})
const aiScopeOptions = computed<TeacherAiScopeOption[]>(() => {
  if (aiDomain.value === 'lesson') {
    return (selectedLesson.value?.sections || []).map(section => ({ id: section.section_node_id, label: section.title }))
  }
  if (aiDomain.value === 'script') {
    return (selectedLesson.value?.script.sections || []).map(section => ({ id: section.section_node_id, label: section.title }))
  }
  return []
})
const currentAiScopeId = computed(() => {
  if (aiDomain.value === 'outline') return 'outline'
  if (aiDomain.value === 'question-bank') return 'question-bank'
  if (aiDomain.value === 'script') return aiScriptSectionId.value || aiScopeOptions.value[0]?.id || 'script'
  return selectedLessonSectionId.value || aiScopeOptions.value[0]?.id || 'lesson'
})
function prioritizeAiActions(actions: TeacherAiQuickAction[], priorities: string[]) {
  const uniquePriorities = [...new Set(priorities)]
  return uniquePriorities
    .map(id => actions.find(action => action.id === id))
    .filter((action): action is TeacherAiQuickAction => Boolean(action))
    .concat(actions.filter(action => !uniquePriorities.includes(action.id)))
}
const aiQuickActions = computed<TeacherAiQuickAction[]>(() => {
  if (aiDomain.value === 'outline') {
    const actions: TeacherAiQuickAction[] = [
    { id: 'outline-diagnose', icon: 'diagnose', label: t('courseWorkbench.aiCollaboration.quickOutlineDiagnose', '检查结构问题'), prompt: t('courseWorkbench.aiCollaboration.quickOutlineDiagnosePrompt', '检查当前大纲的讲次顺序、学习路径和重复内容，只调整确有必要的部分') },
    { id: 'outline-sequence', icon: 'sequence', label: t('courseWorkbench.aiCollaboration.quickOutlineSequence', '调整讲次顺序'), prompt: t('courseWorkbench.aiCollaboration.quickOutlineSequencePrompt', '调整讲次顺序，让知识难度与前置关系更合理') },
    { id: 'outline-path', icon: 'path', label: t('courseWorkbench.aiCollaboration.quickOutlinePath', '补齐学习路径'), prompt: t('courseWorkbench.aiCollaboration.quickOutlinePathPrompt', '补齐缺失的学习路径和前置衔接') },
    { id: 'outline-merge', icon: 'merge', label: t('courseWorkbench.aiCollaboration.quickOutlineMerge', '合并重复内容'), prompt: t('courseWorkbench.aiCollaboration.quickOutlineMergePrompt', '合并重复的讲次内容，同时保留必要的知识覆盖') },
    { id: 'outline-objective', icon: 'target', label: t('courseWorkbench.aiCollaboration.quickOutlineObjective', '细化学习目标'), prompt: t('courseWorkbench.aiCollaboration.quickOutlineObjectivePrompt', '细化每一讲的学习目标，使其具体、可观察且与内容对应') },
    { id: 'outline-split', icon: 'split', label: t('courseWorkbench.aiCollaboration.quickOutlineSplit', '拆分过大讲次'), prompt: t('courseWorkbench.aiCollaboration.quickOutlineSplitPrompt', '拆分内容范围过大的讲次，使每次课的学习任务更聚焦') },
    ]
    const nodes = courseStore.nodes as Array<Record<string, any>>
    const titles = nodes.map(node => String(node.node_name || '').trim()).filter(Boolean)
    const priorities: string[] = ['outline-diagnose']
    if (new Set(titles).size < titles.length) priorities.unshift('outline-merge')
    if (nodes.some(node => !String(node.learning_objective || '').trim())) priorities.unshift('outline-objective')
    if (nodes.some(node => String(node.node_content || '').length > 1800)) priorities.unshift('outline-split')
    return prioritizeAiActions(actions, priorities)
  }
  if (aiDomain.value === 'script') {
    const actions: TeacherAiQuickAction[] = [
    { id: 'script-voice', icon: 'voice', label: t('courseWorkbench.aiCollaboration.quickScriptVoice', '改得更适合口语'), prompt: t('courseWorkbench.aiCollaboration.quickScriptVoicePrompt', '改得更适合老师在课堂上自然讲解，保留知识事实和教学结构') },
    { id: 'script-compress', icon: 'compress', label: t('courseWorkbench.aiCollaboration.quickScriptCompress', '压缩重复表达'), prompt: t('courseWorkbench.aiCollaboration.quickScriptCompressPrompt', '压缩重复表达，保留关键解释和必要例子') },
    { id: 'script-example', icon: 'example', label: t('courseWorkbench.aiCollaboration.quickScriptExample', '加入课堂案例'), prompt: t('courseWorkbench.aiCollaboration.quickScriptExamplePrompt', '加入一个贴合当前知识点、适合课堂讲解的具体案例') },
    { id: 'script-question', icon: 'question', label: t('courseWorkbench.aiCollaboration.quickScriptQuestion', '增加引导提问'), prompt: t('courseWorkbench.aiCollaboration.quickScriptQuestionPrompt', '增加能引导学生思考的课堂提问，并自然衔接讲解') },
    { id: 'script-transition', icon: 'transition', label: t('courseWorkbench.aiCollaboration.quickScriptTransition', '优化段落过渡'), prompt: t('courseWorkbench.aiCollaboration.quickScriptTransitionPrompt', '优化段落之间的过渡，让讲解推进更自然') },
    { id: 'script-timing', icon: 'timing', label: t('courseWorkbench.aiCollaboration.quickScriptTiming', '适配授课时长'), prompt: t('courseWorkbench.aiCollaboration.quickScriptTimingPrompt', '在不改变教学目标的前提下调整内容密度，使讲义适配当前授课时长') },
    ]
    const scriptSection = (selectedLesson.value?.script.sections || []).find(
      section => section.section_node_id === currentAiScopeId.value,
    )
    const scriptText = String(scriptSection?.content || '')
    const priorities: string[] = []
    if (scriptText.length > 1400) priorities.push('script-compress')
    if (!/[？?]/.test(scriptText)) priorities.push('script-question')
    if (!/(例如|案例|示例|举个例子)/.test(scriptText)) priorities.push('script-example')
    if (!/(接下来|因此|由此|回到|总结)/.test(scriptText)) priorities.push('script-transition')
    return prioritizeAiActions(actions, priorities.length ? priorities : ['script-voice'])
  }
  if (aiDomain.value === 'question-bank') {
    const actions: TeacherAiQuickAction[] = [
    { id: 'question-application', icon: 'example', label: t('courseWorkbench.aiCollaboration.quickQuestionApplication', '补应用题'), prompt: t('courseWorkbench.aiCollaboration.quickQuestionApplicationPrompt', '为整门课程补充能检查知识迁移的应用题') },
    { id: 'question-diagnosis', icon: 'diagnose', label: t('courseWorkbench.aiCollaboration.quickQuestionDiagnosis', '强化错因诊断'), prompt: t('courseWorkbench.aiCollaboration.quickQuestionDiagnosisPrompt', '增加能区分典型错因的诊断性题目和干扰项') },
    { id: 'question-coverage', icon: 'check', label: t('courseWorkbench.aiCollaboration.quickQuestionCoverage', '补齐目标覆盖'), prompt: t('courseWorkbench.aiCollaboration.quickQuestionCoveragePrompt', '补齐整门课程尚未覆盖的必需学习目标') },
    { id: 'question-difficulty', icon: 'timing', label: t('courseWorkbench.aiCollaboration.quickQuestionDifficulty', '拉开难度梯度'), prompt: t('courseWorkbench.aiCollaboration.quickQuestionDifficultyPrompt', '调整题组，使基础、应用与迁移难度形成清晰梯度') },
    { id: 'question-diversity', icon: 'split', label: t('courseWorkbench.aiCollaboration.quickQuestionDiversity', '增加题组多样性'), prompt: t('courseWorkbench.aiCollaboration.quickQuestionDiversityPrompt', '增加题型、材料和推理路径多样性，避免仅换措辞或数字') },
    { id: 'question-explanation', icon: 'focus', label: t('courseWorkbench.aiCollaboration.quickQuestionExplanation', '完善教学解析'), prompt: t('courseWorkbench.aiCollaboration.quickQuestionExplanationPrompt', '完善标准答案、逐步解析、错误选项说明和结果检查') },
    ]
    return prioritizeAiActions(
      actions,
      questionBankReady.value
        ? ['question-diagnosis', 'question-diversity', 'question-explanation']
        : ['question-coverage', 'question-application', 'question-difficulty'],
    )
  }
  const actions: TeacherAiQuickAction[] = [
    { id: 'lesson-objective', icon: 'target', label: t('courseWorkbench.aiCollaboration.quickObjective', '让目标可观察'), prompt: t('courseWorkbench.aiCollaboration.quickObjectivePrompt', '把教学目标改成具体、可观察、可检查的学习行为') },
    { id: 'lesson-interaction', icon: 'interaction', label: t('courseWorkbench.aiCollaboration.quickInteraction', '增加课堂互动'), prompt: t('courseWorkbench.aiCollaboration.quickInteractionPrompt', '增加与当前教学目标对应的课堂互动活动') },
    { id: 'lesson-check', icon: 'check', label: t('courseWorkbench.aiCollaboration.quickCheck', '补充检查点'), prompt: t('courseWorkbench.aiCollaboration.quickCheckPrompt', '补充能判断学生是否达成目标的课堂检查点') },
    { id: 'lesson-pacing', icon: 'timing', label: t('courseWorkbench.aiCollaboration.quickPacing', '调整时间节奏'), prompt: t('courseWorkbench.aiCollaboration.quickPacingPrompt', '调整教学时间分配，压缩单向讲授并给活动和检查留出时间') },
    { id: 'lesson-focus', icon: 'focus', label: t('courseWorkbench.aiCollaboration.quickFocus', '突出重点难点'), prompt: t('courseWorkbench.aiCollaboration.quickFocusPrompt', '突出本节教学重点和难点，并让教学活动与之对应') },
    { id: 'lesson-example', icon: 'example', label: t('courseWorkbench.aiCollaboration.quickLessonExample', '加入课堂案例'), prompt: t('courseWorkbench.aiCollaboration.quickLessonExamplePrompt', '加入一个贴合当前知识点、适合学生理解的课堂案例') },
  ]
  const revision = selectedLesson.value?.plan.revisions.find(item => item.revision_id === selectedLesson.value?.plan.working_revision_id)
  const sections = revision?.plan.sections as AiLessonPlanSection[] | undefined
  const section = sections?.find(item => item.node_id === selectedLessonSectionId.value)
  if (!section) return actions
  const priorities: string[] = []
  if (!section.in_class_checks?.length) priorities.push('lesson-check')
  if (!section.key_points?.length || !section.key_difficulties?.length) priorities.push('lesson-focus')
  const plannedMinutes = (section.teaching_modules || []).reduce((total, module) => total + Number(module.planned_minutes || 0), 0)
  if (plannedMinutes && Math.abs(plannedMinutes - Number(selectedLesson.value?.duration_minutes || 0)) > 5) priorities.push('lesson-pacing')
  const moduleText = (section.teaching_modules || []).map(module => `${module.module_id} ${module.teacher_activity} ${module.student_activity}`).join(' ')
  if (!/(案例|示例|example|case)/i.test(moduleText)) priorities.push('lesson-example')
  if (!/(讨论|提问|练习|小组|回答|展示|互评|操作|绘制|实验|任务)/.test(moduleText)) priorities.push('lesson-interaction')
  if (!section.learning_objective?.trim()) priorities.push('lesson-objective')
  return [...new Set(priorities)].map(id => actions.find(action => action.id === id)!).filter(Boolean)
    .concat(actions.filter(action => !priorities.includes(action.id)))
})
const aiPlaceholder = computed(() => aiDomain.value === 'outline'
  ? '说说你想怎么调整大纲…'
  : aiDomain.value === 'question-bank'
    ? '说说你想怎么调整题库…'
  : aiDomain.value === 'script'
    ? t('courseWorkbench.aiCollaboration.scriptPlaceholder', '说说你想怎么改这段讲义…')
    : '说说你想怎么调整教案…')
const currentAiScopeKey = computed(() => aiDomain.value === 'question-bank'
  ? [props.courseId, aiDomain.value, 'course'].join(':')
  : [props.courseId, aiDomain.value, selectedLessonId.value, currentAiScopeId.value].join(':'))
const lessonReferenceTargetId = computed(() => (
  activeStage.value === 'foundation'
    ? 'managed:outline'
    : !selectedLessonId.value
      ? ''
      : activeStage.value === 'ppt'
        ? `ppt-v6:${selectedLessonId.value}`
        : activeStage.value === 'script'
          ? `script:${selectedLessonId.value}`
          : activeStage.value === 'lesson'
            ? `lesson-plan:${selectedLessonId.value}`
            : ''
))
const lessonReferenceTargetType = computed(() => (
  !lessonReferenceTargetId.value
    ? ''
    : activeStage.value === 'foundation'
      ? 'outline'
      : activeStage.value === 'ppt'
        ? 'ppt'
        : activeStage.value === 'script'
          ? 'script'
          : 'lesson_plan'
))
const selectedLessonIndex = computed(() => lessonStore.lessons.findIndex(item => item.lesson_unit_id === selectedLessonId.value))
const previousLesson = computed(() => selectedLessonIndex.value > 0 ? lessonStore.lessons[selectedLessonIndex.value - 1] : undefined)
const previousLessonReferenceTargetId = computed(() => (
  !previousLesson.value?.lesson_unit_id
    ? ''
    : activeStage.value === 'ppt'
      ? `ppt-v6:${previousLesson.value.lesson_unit_id}`
      : activeStage.value === 'script'
        ? `script:${previousLesson.value.lesson_unit_id}`
        : activeStage.value === 'lesson'
        ? `lesson-plan:${previousLesson.value.lesson_unit_id}`
        : ''
))
const nextLesson = computed(() => selectedLessonIndex.value >= 0 && selectedLessonIndex.value < lessonStore.lessons.length - 1 ? lessonStore.lessons[selectedLessonIndex.value + 1] : undefined)
const workingLessonRevision = computed(() => selectedLesson.value?.plan.revisions.find(item => item.revision_id === selectedLesson.value?.plan.working_revision_id))
const confirmedLessonRevision = computed(() => selectedLesson.value?.plan.revisions.find(item => item.revision_id === selectedLesson.value?.plan.confirmed_revision_id))
const currentAiBaseRevision = computed(() => {
  if (aiDomain.value === 'lesson') return String(workingLessonRevision.value?.revision_id || '')
  if (aiDomain.value === 'question-bank') return String(aiCandidate.value?.base_bundle_revision_id || questionBankRevisionId.value || 'course-question-bank')
  if (aiDomain.value === 'script') return String(selectedLesson.value?.script?.current_revision_id || '')
  return String(generationTask.value?.phaseDetail?.skeleton_revision_id || '')
})
const aiCollaborationBusy = computed(() => teacherProductionAiBusy(aiPhase.value))
const aiCandidatePending = computed(() => Boolean(aiCandidate.value))
const activeAiDocument = computed<ProductionAiDocumentHandle | null>(() => {
  if (aiDomain.value === 'outline') return outlineEditor.value
  if (aiDomain.value === 'question-bank') return questionBankPanel.value
  if (aiDomain.value === 'script') return scriptDocument.value
  return lessonPlanDocument.value as ProductionAiDocumentHandle | null
})
const contextAiDomain = computed<TeacherProductionAiDomain | null>(() => {
  if (activeStage.value === 'foundation') return 'outline'
  if (activeStage.value === 'lesson') return 'lesson'
  if (activeStage.value === 'script') return 'script'
  return null
})
const contextAiAvailable = computed(() => {
  if (contextAiDomain.value === 'outline') return Boolean(showOutlineWorkspace.value && outlineEditor.value)
  if (contextAiDomain.value === 'lesson') return Boolean(selectedLesson.value && workingLessonRevision.value)
  if (contextAiDomain.value === 'script') return Boolean(selectedLesson.value?.script.ready && scriptDocument.value)
  return false
})
const aiCandidateFieldLabels = computed(() => {
  if (aiDomain.value === 'outline') {
    const diff = aiCandidate.value?.diff || {}
    const operationLabels = [
      ...(Array.isArray(diff.moved) ? diff.moved.map((item: any) => `移动 ${item.node_name || '讲次'}：${item.old_position || '原位置'} → ${item.new_position || '新位置'}`) : []),
      ...(Array.isArray(diff.updated) ? diff.updated.map((item: any) => `修改 ${item.node_name || '讲次'}`) : []),
      ...(Array.isArray(diff.added) ? diff.added.map((item: any) => `新增 ${item.node_name || '讲次'}`) : []),
      ...(Array.isArray(diff.removed) ? diff.removed.map((item: any) => `删除 ${item.node_name || '讲次'}`) : []),
    ]
    return operationLabels.length ? operationLabels : ['大纲内容']
  }
  if (aiDomain.value === 'script') return [t('courseWorkbench.aiCollaboration.scriptBody', '讲义正文')]
  if (aiDomain.value === 'question-bank') return [
    t('courseWorkbench.aiCollaboration.questionScopeField', '出题范围'),
    t('courseWorkbench.aiCollaboration.questionInstructionField', '教师要求'),
    t('courseWorkbench.aiCollaboration.questionSourcesField', '资料范围'),
  ]
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
const aiCandidateImpacts = computed(() => {
  if (!aiCandidatePending.value) return []
  if (aiDomain.value === 'outline') {
    return lessonStore.lessons.length
      ? [t('courseWorkbench.aiCollaboration.impactLessons', '教案需重新核对')]
      : []
  }
  if (aiDomain.value === 'lesson') {
    return [
      selectedLesson.value?.script?.ready
        ? t('courseWorkbench.aiCollaboration.impactScript', '讲义需更新')
        : '',
      questionBankReady.value
        ? t('courseWorkbench.aiCollaboration.impactQuestionBank', '题库需核对')
        : '',
      selectedLesson.value?.plan?.ppt_assets?.length
        ? t('courseWorkbench.aiCollaboration.impactPpt', 'PPT 需更新')
        : '',
    ].filter(Boolean)
  }
  if (aiDomain.value === 'question-bank') {
    return [t('courseWorkbench.aiCollaboration.impactQuestionTask', '旧题库继续生效')]
  }
  if (aiDomain.value === 'script' && selectedLesson.value?.plan?.ppt_assets?.length) {
    return [t('courseWorkbench.aiCollaboration.impactPpt', 'PPT 需更新')]
  }
  return []
})
const lessonPlanConfirmed = computed(() => Boolean(workingLessonRevision.value?.revision_id && workingLessonRevision.value.revision_id === selectedLesson.value?.plan.confirmed_revision_id))
const lessonArrangementImpactLabels = computed(() => {
  const lesson = selectedLesson.value
  if (!lesson?.arrangement) return []
  const pendingChange = selectedLessonTypeDraft.value && selectedLessonTypeDraft.value !== lesson.arrangement.lesson_type
  const alreadyAffected = lesson.plan.source_state === 'stale'
  if (!pendingChange && !alreadyAffected) return []
  const labels: string[] = []
  if (lesson.plan.working_revision_id) labels.push(t('courseWorkbench.arrangement.impactLessonPlan', '当前教案需要重新核对'))
  if (lesson.script?.ready) labels.push(t('courseWorkbench.arrangement.impactScript', '讲义需要更新'))
  if (lesson.plan.ppt_assets?.length) labels.push(t('courseWorkbench.arrangement.impactPpt', 'PPT 需要更新'))
  return labels
})
const selectedLessonCanGenerate = computed(() => Boolean(
  selectedLesson.value?.arrangement?.confirmed
  && !lessonGenerationActive.value
  && (
    !workingLessonRevision.value
    || selectedLesson.value?.plan.source_state === 'stale'
    || ['failed', 'cancelled', 'paused'].includes(String(lessonJob.value?.status || ''))
  )
))
const lessonToolbarVisible = computed(() => activeStage.value === 'lesson' && Boolean(workingLessonRevision.value && selectedLesson.value) && !lessonGenerationActive.value)
const lessonPageHeaderVisible = computed(() => ['lesson', 'script', 'ppt'].includes(activeStage.value) && Boolean(selectedLesson.value))
const lessonDocumentEditing = computed(() => Boolean(lessonPlanDocument.value?.editing))
const lessonDocumentSaving = computed(() => Boolean(lessonPlanDocument.value?.saving))
const lessonDocumentAiBusy = computed(() => Boolean(lessonPlanDocument.value?.aiBusy))
const lessonDocumentQualityBlocked = computed(() => Boolean(lessonPlanDocument.value?.qualityBlocked))
const lessonDocumentQualityBlockMessage = computed(() => String(lessonPlanDocument.value?.qualityBlockMessage || ''))
const scriptConfirmed = computed(() => Boolean(selectedLesson.value?.script?.confirmed))
const scriptPublicationEligible = computed(() => selectedLesson.value?.script?.publication_eligible !== false)
const scriptPublicationBlockReason = computed(() => String(
  selectedLesson.value?.script?.quality_report?.blocking_issues?.[0]?.message
  || (!scriptPublicationEligible.value ? t('courseWorkbench.scriptDocument.qualityBlocked', '讲义尚未通过当前质量与来源检查') : ''),
))
const scriptToolbarVisible = computed(() => activeStage.value === 'script' && Boolean(selectedLesson.value?.script?.ready) && !scriptGenerationBusy.value)
const scriptDocumentEditing = computed(() => Boolean(scriptDocument.value?.editing))
const scriptDocumentSaving = computed(() => Boolean(scriptDocument.value?.saving))
const scriptDocumentAiBusy = computed(() => Boolean(scriptDocument.value?.aiBusy))
const outlineCanUndo = computed(() => Boolean(outlineEditor.value?.canUndo))
const outlineCanRedo = computed(() => Boolean(outlineEditor.value?.canRedo))
const outlineDocumentDirty = computed(() => Boolean(outlineEditor.value?.dirty))
const lessonCanUndo = computed(() => Boolean(lessonPlanDocument.value?.canUndo))
const lessonCanRedo = computed(() => Boolean(lessonPlanDocument.value?.canRedo))
const scriptCanUndo = computed(() => Boolean(scriptDocument.value?.canUndo))
const scriptCanRedo = computed(() => Boolean(scriptDocument.value?.canRedo))
const outlineHistoryCount = computed(() => courseWorkspaceStore.blueprintDraftVersions.length)
const lessonHistoryCount = computed(() => selectedLesson.value?.plan.revisions.length || 0)
const scriptHistoryCount = computed(() => selectedLesson.value?.script.revisions?.length || 0)
const outlineDocumentStatusLabel = computed(() => {
  if (outlineConfirming.value) return '正在确认…'
  if (stageSwitching.value && editingOutline.value) return '正在保存…'
  if (aiCandidatePending.value && aiDomain.value === 'outline') return 'AI 修改待确认'
  if (editingOutline.value) return outlineDocumentDirty.value ? '编辑中·未保存' : '编辑中·已保存'
  return '已保存'
})
const outlineDocumentStatusTone = computed<'normal' | 'busy' | 'warning'>(() => {
  if (outlineConfirming.value || stageSwitching.value) return 'busy'
  if ((editingOutline.value && outlineDocumentDirty.value) || (aiCandidatePending.value && aiDomain.value === 'outline')) return 'warning'
  return 'normal'
})
const documentStatusTone = computed<'normal' | 'busy' | 'warning'>(() => {
  if (lessonHeaderBusy.value || aiCollaborationBusy.value) return 'busy'
  if (lessonHeaderEditing.value || aiCandidatePending.value) return 'warning'
  return 'normal'
})
const formatHistoryTime = (value: unknown) => {
  const date = new Date(String(value || ''))
  if (Number.isNaN(date.getTime())) return '时间未记录'
  return new Intl.DateTimeFormat('zh-CN', {
    month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit',
  }).format(date)
}
const historySourceLabel = (value: unknown) => {
  const source = String(value || '')
  if (source === 'history_restore' || source === 'restore') return '恢复的版本'
  if (source === 'ai_apply' || source === 'ai_optimization') return 'AI 修改'
  if (source.includes('model')) return 'AI 生成'
  if (source.includes('fallback') || source.includes('recovery')) return '恢复草稿'
  if (source.startsWith('legacy')) return '旧版内容'
  return '手动编辑'
}
const documentHistoryItems = computed<TeacherDocumentHistoryItem[]>(() => {
  if (historyDomain.value === 'outline') {
    const currentRevision = String(courseWorkspaceStore.blueprint?.draft?.draft_revision_id || '')
    let currentMarked = false
    return courseWorkspaceStore.blueprintDraftVersions.map((item: any) => {
      const current = !currentMarked && String(item.draft_revision_id || '') === currentRevision
      if (current) currentMarked = true
      return {
        id: String(item.history_entry_id || ''),
        title: historySourceLabel(item.operation),
        time: formatHistoryTime(item.created_at),
        actor: String(item.actor || ''),
        detail: `${Number(item.section_count || item.chapter_count || 0)} 讲`,
        current,
      }
    })
  }
  if (historyDomain.value === 'lesson') {
    const currentRevision = String(selectedLesson.value?.plan.working_revision_id || '')
    return [...(selectedLesson.value?.plan.revisions || [])].reverse().map(item => ({
      id: item.revision_id,
      title: historySourceLabel(item.generation_source),
      time: formatHistoryTime(item.created_at),
      actor: item.actor,
      detail: item.restored_from_revision_id ? '从历史版本恢复' : '',
      current: item.revision_id === currentRevision,
    }))
  }
  const currentRevision = String(selectedLesson.value?.script.current_revision_id || '')
  return (selectedLesson.value?.script.revisions || []).map(item => ({
    id: item.revision_id,
    title: historySourceLabel(item.generation_source),
    time: formatHistoryTime(item.created_at || item.updated_at),
    actor: item.actor,
    detail: item.restored_from_revision_id ? '从历史版本恢复' : '',
    current: item.revision_id === currentRevision,
  }))
})
const currentPptAsset = computed(() => selectedLesson.value?.plan.ppt_assets.find(asset => (
  ['slide_deck_v6', 'uploaded_pptx'].includes(String(asset.engine || '')) && asset.source_state === 'current'
)))
const pptNeedsRefresh = computed(() => Boolean(
  !currentPptAsset.value && selectedLesson.value?.plan.ppt_assets.some(asset => ['slide_deck_v6', 'uploaded_pptx'].includes(String(asset.engine || ''))),
))
const lessonHeaderBusy = computed(() => activeStage.value === 'script'
  ? scriptGenerationBusy.value || scriptConfirming.value
  : activeStage.value === 'lesson' && lessonConfirming.value)
const lessonHeaderEditing = computed(() => activeStage.value === 'script'
  ? scriptDocumentEditing.value
  : activeStage.value === 'lesson' && lessonDocumentEditing.value)
const lessonHeaderConfirmed = computed(() => activeStage.value === 'ppt'
  ? Boolean(currentPptAsset.value)
  : activeStage.value === 'script'
    ? scriptConfirmed.value
    : lessonPlanConfirmed.value)
const lessonHeaderStatusLabel = computed(() => {
  if (activeStage.value === 'ppt') {
    if (currentPptAsset.value) return t('courseWorkbench.pptReview.currentStatus', '已有当前 PPT')
    if (pptNeedsRefresh.value) return t('courseWorkbench.pptReview.refreshRequired', '待更新')
    return t('courseWorkbench.pptReview.pendingStatus', '待生成')
  }
  if (activeStage.value === 'script' && scriptGenerationBusy.value) return t('courseWorkbench.scriptDocument.generating', '正在生成…')
  if (activeStage.value === 'script' && scriptConfirming.value) return t('courseWorkbench.scriptDocument.confirming', '正在确认…')
  if (activeStage.value === 'lesson' && lessonConfirming.value) return t('courseWorkbench.confirmingLessonPlan', '正在确认…')
  if (activeStage.value === 'lesson' && String(lessonJob.value?.status || '') === 'failed') return t('courseWorkbench.lessonOutline.status.failed', '失败')
  if (aiCandidatePending.value) return t('courseWorkbench.lessonDocument.aiCandidatePending', 'AI 方案待处理')
  if (activeStage.value === 'script' && scriptDocumentEditing.value) return t('courseWorkbench.scriptDocument.editing', '编辑中')
  if (activeStage.value === 'lesson' && lessonDocumentEditing.value) return t('courseWorkbench.lessonDocument.editing', '编辑中')
  if (activeStage.value === 'script' && scriptConfirmed.value) return t('courseWorkbench.scriptDocument.confirmed', '已确认')
  if (activeStage.value === 'lesson' && selectedLesson.value?.plan.source_state === 'stale') return t('courseWorkbench.lessonOutline.status.needsReview', '需复核')
  if (activeStage.value === 'lesson' && lessonPlanConfirmed.value) return t('courseWorkbench.lessonPlanConfirmed', '已确认')
  if (activeStage.value === 'script' && !selectedLesson.value?.script.ready) return t('courseWorkbench.scriptPending', '待生成')
  return t('courseWorkbench.lessonPlanPendingReview', '待确认')
})
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
const lessonGenerationRunning = computed(() => lessonJob.value?.status === 'running')
const lessonGenerationQueued = computed(() => lessonJob.value?.status === 'pending' && Boolean(lessonJob.value?.parent_job_id))
const batchEligibleCount = computed(() => lessonStore.lessons.filter(lesson => (
  !lesson.plan.working_revision_id || lesson.plan.source_state !== 'current'
)).length)
const latestBatchParentId = computed(() => [...lessonStore.jobs]
  .filter(job => job.type === 'teacher_lesson_plan_generation' && job.parent_job_id)
  .sort((left, right) => String(right.updated_at || '').localeCompare(String(left.updated_at || '')))[0]?.parent_job_id || '')
const batchLessonJobs = computed(() => {
  if (!latestBatchParentId.value) return []
  const lessonIds = new Set(lessonStore.jobs
    .filter(job => job.parent_job_id === latestBatchParentId.value)
    .map(job => job.lesson_unit_id))
  return lessonStore.lessons
    .filter(lesson => lessonIds.has(lesson.lesson_unit_id))
    .map(lesson => lessonStore.latestJobByLesson(lesson.lesson_unit_id))
    .filter((job): job is TeacherLessonJob => Boolean(job))
})
const batchRunning = computed(() => batchLessonJobs.value.some(job => ['pending', 'running'].includes(job.status)))
const batchCompletedCount = computed(() => batchLessonJobs.value.filter(job => ['completed', 'completed_with_warnings'].includes(job.status)).length)
const batchPaused = computed(() => (
  batchLessonJobs.value.some(job => job.status === 'paused')
  && !batchRunning.value
))
const batchFailed = computed(() => batchLessonJobs.value.some(job => ['failed', 'cancelled'].includes(job.status)))
const batchRecoveryAvailable = computed(() => batchPaused.value || batchFailed.value || lessonStore.lessons.some(lesson => (
  (!lesson.plan.working_revision_id || lesson.plan.source_state !== 'current')
  && ['paused', 'failed', 'cancelled'].includes(String(lessonStore.latestJobByLesson(lesson.lesson_unit_id)?.status || ''))
)))
const lessonBatchLaunchVisible = computed(() => (
  activeStage.value === 'lesson'
  && batchEligibleCount.value > 0
  && !batchRunning.value
  && !batchStarting.value
  && !batchPaused.value
  && !batchRecoveryAvailable.value
))
const lessonGenerationActionsVisible = computed(() => (
  activeStage.value === 'lesson'
  && Boolean(selectedLesson.value?.arrangement?.blocks?.length)
  && !lessonGenerationActive.value
  && (selectedLessonCanGenerate.value || lessonBatchLaunchVisible.value || batchStarting.value)
))
const batchTotalCount = computed(() => Math.max(
  ...batchLessonJobs.value.map(job => Number(job.batch_size || 0)),
  batchLessonJobs.value.length,
  0,
))
const batchCurrentJob = computed(() => batchLessonJobs.value.find(job => job.status === 'running'))
const batchProgress = computed(() => {
  if (!batchTotalCount.value) return 0
  const completed = batchLessonJobs.value.reduce((total, job) => {
    if (['completed', 'completed_with_warnings'].includes(job.status)) return total + 100
    if (job.status === 'running') return total + Math.max(0, Math.min(100, Number(job.progress || 0)))
    return total
  }, 0)
  return Math.round(completed / batchTotalCount.value)
})
const batchError = computed(() => String(
  [...(batchLessonJobs.value.length ? batchLessonJobs.value : lessonStore.jobs)].reverse().find(job => job.status === 'failed')?.error?.message || '',
))
const lessonGenerationProgress = computed(() => Math.max(3, Number(lessonJob.value?.progress || 0)))
const lessonGenerationError = computed(() => lessonJob.value?.status === 'cancelled'
  ? ''
  : String(lessonJob.value?.error?.message || lessonConfirmError.value || lessonStore.error || ''))
const lessonStreamSegments = computed(() => lessonPlanStreamSegments(lessonJob.value?.stream_batches))
const scriptJob = computed(() => selectedLessonId.value ? lessonStore.latestScriptJobByLesson(selectedLessonId.value) : undefined)
const scriptGenerationActive = computed(() => ['pending', 'running'].includes(String(scriptJob.value?.status || '')))
const scriptGenerationBusy = computed(() => scriptGenerating.value || scriptGenerationActive.value)
const scriptGenerationProgress = computed(() => Math.max(3, Number(scriptJob.value?.progress || 0)))
const effectiveScriptGenerationError = computed(() => String(
  selectedLesson.value?.script?.ready
    ? ''
    : scriptJob.value?.status === 'cancelled'
    ? ''
    : scriptJob.value?.status === 'failed'
    ? scriptJob.value.error?.message || scriptGenerationError.value
    : scriptGenerationError.value,
))
const referenceWorkflowState = computed<CourseReferenceWorkflowState>(() => {
  if (activeStage.value === 'foundation') {
    if (props.generationStarting || taskInFlight.value) return 'generating'
    if (taskPaused.value) return 'paused'
    if (generationFailed.value) return 'failed'
    if (outlineGatePending.value || hasOutline.value) return 'review'
    return activeReferences.value.length ? 'ready' : 'collecting'
  }
  if (activeStage.value === 'lesson') {
    if (batchRunning.value || batchStarting.value) return 'generating'
    if (batchPaused.value) return 'paused'
    if (batchRecoveryAvailable.value && batchEligibleCount.value) return batchPaused.value ? 'paused' : 'failed'
    if (lessonPlanConfirmed.value) return 'confirmed'
    if (workingLessonRevision.value) return 'review'
    return activeReferences.value.length ? 'ready' : 'collecting'
  }
  if (activeStage.value === 'script') {
    if (scriptGenerationBusy.value) return 'generating'
    if (scriptJob.value?.status === 'paused') return 'paused'
    if (['failed', 'cancelled'].includes(String(scriptJob.value?.status || '')) || effectiveScriptGenerationError.value) return 'failed'
    if (scriptConfirmed.value) return 'confirmed'
    if (selectedLesson.value?.script?.ready) return 'review'
    return activeReferences.value.length ? 'ready' : 'collecting'
  }
  if (activeStage.value === 'ppt') return currentPptAsset.value ? 'confirmed' : activeReferences.value.length ? 'ready' : 'collecting'
  return activeReferences.value.length ? 'ready' : 'collecting'
})
const referenceWorkflowDetail = computed(() => {
  if (referenceWorkflowState.value === 'generating') {
    if (activeStage.value === 'foundation') return currentGenerationLabel.value
    if (activeStage.value === 'lesson') {
      const currentTitle = batchCurrentJob.value ? lessonTitleForJob(batchCurrentJob.value.lesson_unit_id) : ''
      return t('courseWorkbench.lessonBatch.overallProgress', '已完成 {completed}/{total} 讲{current}')
        .replace('{completed}', String(batchCompletedCount.value))
        .replace('{total}', String(batchTotalCount.value || batchEligibleCount.value))
        .replace('{current}', currentTitle ? ` · ${currentTitle}` : '')
    }
    if (activeStage.value === 'script') return String(scriptJob.value?.message || t('courseWorkbench.references.generatingDetail', 'AI 正在读取资料并构建内容。'))
  }
  if (referenceWorkflowState.value === 'failed') {
    if (activeStage.value === 'foundation') return generationError.value
    if (activeStage.value === 'lesson') return batchError.value || lessonGenerationError.value
    if (activeStage.value === 'script') return effectiveScriptGenerationError.value
  }
  return ''
})
const referenceWorkflowProgress = computed(() => {
  if (activeStage.value === 'foundation') return generationProgress.value
  if (activeStage.value === 'lesson') return batchRunning.value || batchLessonJobs.value.length ? batchProgress.value : 0
  if (activeStage.value === 'script') return scriptGenerationProgress.value
  return referenceWorkflowState.value === 'confirmed' ? 100 : 0
})
const referenceWorkflowCanPause = computed(() => (
  activeStage.value === 'foundation' ? taskInFlight.value
    : activeStage.value === 'lesson' ? batchRunning.value
      : activeStage.value === 'script' ? scriptGenerationActive.value
        : false
))
const referenceWorkflowCanResume = computed(() => (
  activeStage.value === 'foundation' ? taskPaused.value
    : activeStage.value === 'lesson' ? batchPaused.value
      : activeStage.value === 'script' ? scriptJob.value?.status === 'paused'
        : false
))
const referenceWorkflowCanCancel = computed(() => referenceWorkflowCanPause.value || referenceWorkflowCanResume.value)
const referenceWorkflowCanRetry = computed(() => referenceWorkflowState.value === 'failed' && activeStage.value !== 'ppt')
const readyStageCount = computed(() => stages.value.filter(item => stageReady(item.id)).length)
const lessonStageBlocked = computed(() => (
  lessonStore.loading
  || outlineGatePending.value
  || !lessonStore.lessons.length
))
const lessonSyncNeedsRecovery = computed(() => (
  ['lesson', 'script', 'ppt'].includes(activeStage.value)
  && !outlineGatePending.value
  && !lessonStore.lessons.length
  && Boolean(hasOutline.value || lessonStore.outlineRevisionId)
))
const lessonSyncExhausted = computed(() => (
  lessonSyncNeedsRecovery.value
  && lessonSyncAttempt.value >= LESSON_SYNC_RETRY_DELAYS.length
  && !lessonSyncRunning.value
  && !lessonSyncRetryScheduled.value
))
const lessonSyncing = computed(() => (
  lessonSyncNeedsRecovery.value
  && !lessonSyncExhausted.value
))
const lessonPrerequisiteState = computed(() => {
  if (lessonSyncing.value) return {
    kind: 'loading',
    title: t('courseWorkbench.lessonPrerequisite.preparing', '正在准备教案'),
    detail: t('courseWorkbench.lessonPrerequisite.preparingHelp', '系统正在自动同步大纲课次并重试，无需重复操作。'),
    action: '',
  }
  if (lessonStore.loading) return {
    kind: 'loading',
    title: t('courseWorkbench.lessonPrerequisite.loading', '正在准备教案'),
    detail: t('courseWorkbench.lessonPrerequisite.loadingHelp', '系统正在读取大纲课次，无需重复操作。'),
    action: '',
  }
  if (outlineShapeAwaitingReview.value) return {
    kind: 'review',
    title: t('courseWorkbench.lessonPrerequisite.shapeReview', '课程讲数已确认，正在生成大纲'),
    detail: t('courseWorkbench.lessonPrerequisite.shapeReviewHelp', '完成这一步后，系统会继续生成完整大纲。'),
    action: t('courseWorkbench.lessonPrerequisite.continueOutline', '继续完善大纲'),
  }
  if (outlineAwaitingReview.value) return {
    kind: 'review',
    title: t('courseWorkbench.lessonPrerequisite.outlineReview', '课程大纲已生成，等待确认'),
    detail: t('courseWorkbench.lessonPrerequisite.outlineReviewHelp', '确认后会直接形成可选择的课次，不需要重新生成大纲。'),
    action: t('courseWorkbench.lessonPrerequisite.reviewOutline', '查看并确认大纲'),
  }
  if ((lessonStore.error && !lessonStore.lessons.length) || lessonSyncExhausted.value) return {
    kind: 'error',
    title: t('courseWorkbench.lessonPrerequisite.loadFailed', '教案读取失败'),
    detail: lessonStore.error || t('courseWorkbench.lessonPrerequisite.loadFailedHelp', '系统多次尝试后仍未能准备教案，请重试。'),
    action: t('common.retry', '重试'),
  }
  if (hasOutline.value || lessonStore.outlineRevisionId) return {
    kind: 'loading',
    title: t('courseWorkbench.lessonPrerequisite.syncPending', '正在准备教案'),
    detail: t('courseWorkbench.lessonPrerequisite.syncPendingHelp', '系统正在按当前大纲自动准备课次，无需重复操作。'),
    action: '',
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

function stageReady(stage: CoreStageId) {
  if (stage === 'foundation') return hasOutline.value && !outlineAwaitingReview.value
  if (!lessonStore.lessons.length) return false
  if (stage === 'lesson') return lessonStore.lessons.every(item => Boolean(item.plan.confirmed_revision_id))
  if (stage === 'script') return lessonStore.lessons.every(item => item.script?.confirmed)
  return lessonStore.lessons.every(item => item.plan.ppt_assets.some(asset => asset.source_state === 'current' && asset.ppt_manuscript_status === 'confirmed'))
}
function nodeContent(node: any) { return generationStore.streamingContent[node.node_id] || node.node_content || '' }
function stopGeneration() { void generationStore.stopGeneration() }
function cancelOutlineGeneration() { void generationStore.cancelTask(props.courseId) }
async function pauseReferenceWorkflow() {
  if (activeStage.value === 'foundation') return generationStore.stopGeneration()
  if (activeStage.value === 'lesson') return pauseAllLessonGeneration()
  if (activeStage.value === 'script') return pauseScriptGeneration()
}
async function resumeReferenceWorkflow() {
  if (activeStage.value === 'foundation' && generationTask.value?.id) {
    await generationStore.resumeTask(props.courseId, generationTask.value.id)
    return
  }
  if (activeStage.value === 'lesson') return generateAllLessonPlans()
  if (activeStage.value === 'script') return generateScript()
}
async function cancelReferenceWorkflow() {
  if (activeStage.value === 'foundation') return generationStore.cancelTask(props.courseId)
  if (activeStage.value === 'lesson') return cancelAllLessonGeneration()
  if (activeStage.value === 'script') return cancelScriptGeneration()
}
async function retryReferenceWorkflow() {
  if (activeStage.value === 'foundation') return submitFoundation()
  if (activeStage.value === 'lesson') return generateAllLessonPlans()
  if (activeStage.value === 'script') return generateScript()
}
function appendAiMessage(
  role: TeacherProductionAiMessage['role'],
  kind: TeacherProductionAiMessage['kind'],
  text: string,
  metadata: Partial<Pick<TeacherProductionAiMessage, 'planId' | 'planStatus' | 'impacts'>> = {},
) {
  aiMessageSequence.value += 1
  aiMessages.value.push({ id: `production-ai-${aiMessageSequence.value}`, role, kind, text, ...metadata })
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
  lastAiCoursePlanRequestId.value = ''
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
    aiPhase.value = aiCandidatePending.value || aiMessages.value.some(message => message.kind === 'course_plan')
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
function openAiCollaboration(domain: TeacherProductionAiDomain, selectionText = '') {
  if (domain === 'lesson' && (!selectedLesson.value || !workingLessonRevision.value)) return
  if (domain === 'script' && (!selectedLesson.value?.script.ready || !scriptDocument.value)) return
  if (domain === 'outline' && !outlineEditor.value) return
  if (aiDomain.value !== domain) {
    aiDomain.value = domain
    aiCandidate.value = null
  }
  aiSelectionContext.value = selectionText.trim().slice(0, 1200)
  contextPaneTab.value = 'ai'
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
  contextPaneTab.value = 'references'
  aiSourcesOpen.value = false
  aiSelectionContext.value = ''
}
function openAiFromSelection(domain: TeacherProductionAiDomain, selection: { text: string }) {
  openAiCollaboration(domain, selection.text)
}
function openContextAiTab() {
  if (!contextAiDomain.value || !contextAiAvailable.value) return
  openAiCollaboration(contextAiDomain.value, aiSelectionContext.value)
}
function showReferenceTab() {
  contextPaneTab.value = 'references'
  aiSourcesOpen.value = false
}
function handleAiSourcesOpen() {
  if (aiDomain.value === 'question-bank') {
    questionBankPanel.value?.focusReferenceSources?.()
    return
  }
  showReferenceTab()
}
function handleQuestionBankReferencesChange(references: CourseReferenceItem[]) {
  questionBankReferences.value = references
}
function handleQuestionBankUpdated(bundleRevisionId: string) {
  questionBankReady.value = true
  questionBankRevisionId.value = bundleRevisionId
}
function handleScriptAiScopeChange(scope: { id: string; title: string }) {
  aiScriptSectionId.value = scope.id
  aiScriptSectionTitle.value = scope.title
}
function changeAiScope(scopeId: string) {
  if (!scopeId || aiCollaborationBusy.value || aiCandidatePending.value || scopeId === currentAiScopeId.value) return
  persistAiSession()
  aiSourcesOpen.value = false
  if (aiDomain.value === 'lesson') {
    selectedLessonSectionId.value = scopeId
    return
  }
  if (aiDomain.value === 'script') {
    const option = aiScopeOptions.value.find(item => item.id === scopeId)
    if (!option || !scriptDocument.value?.selectAiScope?.(scopeId)) return
    aiScriptSectionId.value = option.id
    aiScriptSectionTitle.value = option.label
  }
}
function currentAiScope(): TeacherProductionAiScope {
  return {
    domain: aiDomain.value,
    courseTitle: props.courseTitle,
    primaryTitle: aiScopeTitle.value,
    secondaryTitle: aiScopeDetail.value,
    referenceCount: aiActiveReferences.value.length,
    references: aiActiveReferences.value.map(item => ({
      id: item.material_asset_id,
      label: item.source_label || item.filename,
      role: item.role,
      origin: item.origin,
    })),
    selectionText: aiSelectionContext.value,
  }
}
function buildAiInstruction(): string {
  return buildTeacherProductionAiInstruction(aiMessages.value, currentAiScope())
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
      : aiDomain.value === 'question-bank'
        ? '出题任务已在左侧展示，请核对范围与资料。'
      : aiDomain.value === 'script'
        ? t('courseWorkbench.aiCollaboration.scriptCandidateSummary', '讲义候选已在左侧高亮，请核对表达和事实。')
        : t('courseWorkbench.aiCollaboration.candidateSummary', '候选已显示在左侧，请核对高亮内容。'),
  )
  transitionAi({ type: 'CANDIDATE_READY' })
  lastAiOperation.value = ''
  focusAiCandidate()
}
function coursePlanImpacts(projection: TeacherCoursePlanProjection): string[] {
  const labels: Record<string, string> = {
    outline: t('courseWorkbench.aiCollaboration.assetOutline', '大纲'),
    course_content: t('courseWorkbench.aiCollaboration.assetCourseContent', '课程内容'),
    lesson_plan: t('courseWorkbench.aiCollaboration.assetLessonPlan', '教案'),
    script: t('courseWorkbench.aiCollaboration.assetScript', '讲义'),
    ppt: 'PPT',
    question_bank: t('courseWorkbench.aiCollaboration.assetQuestionBank', '题库'),
  }
  const assets = projection.assetTypes.map(assetType => labels[assetType] || assetType)
  return [
    projection.affectedUnitCount
      ? t('courseWorkbench.aiCollaboration.affectedUnits', '{count} 个受影响单元').replace('{count}', String(projection.affectedUnitCount))
      : '',
    projection.structuralOperationCount
      ? t('courseWorkbench.aiCollaboration.structuralOperations', '{count} 项结构调整').replace('{count}', String(projection.structuralOperationCount))
      : '',
    assets.length ? assets.join('、') : '',
  ].filter(Boolean)
}
async function createCourseChangePlanFromConversation() {
  if (aiCollaborationBusy.value) return
  const requestId = lastAiCoursePlanRequestId.value || `teacher-workbench-${createUuid()}`
  lastAiCoursePlanRequestId.value = requestId
  lastAiOperation.value = 'course_plan'
  aiClarificationOptions.value = []
  transitionAi({ type: 'GENERATE' })
  try {
    const payload = await courseEvolutionStore.createCoursePlan({
      courseId: props.courseId,
      requestId,
      instruction: buildTeacherCourseChangeInstruction(aiMessages.value, currentAiScope()),
    })
    const plans = (payload?.course_evolution_plans || payload?.change_sets || []) as Array<Record<string, any>>
    const plan = plans.find(item => String(item.impact_summary?.request_id || '') === requestId)
    const projection = plan ? projectTeacherCoursePlan(plan) : null
    if (!projection) throw new Error('course_change_plan_missing')
    const summary = projection.blockingQuestionCount
      ? t('courseWorkbench.aiCollaboration.coursePlanNeedsDetailSummary', '我已整理修改范围，但有 {count} 个问题需要你补充。正式课程尚未改变。').replace('{count}', String(projection.blockingQuestionCount))
      : t('courseWorkbench.aiCollaboration.coursePlanSummary', '我已把要求整理成整课修改方案。请先核对影响范围，再决定生成并应用哪些修改。')
    appendAiMessage('assistant', 'course_plan', summary, {
      planId: projection.planId,
      planStatus: projection.status,
      impacts: coursePlanImpacts(projection),
    })
    lastAiOperation.value = ''
    transitionAi({ type: 'COURSE_PLAN_READY' })
  } catch (error: any) {
    handleAiError(String(
      error?.response?.data?.detail?.message
      || error?.response?.data?.detail
      || error?.message
      || t('courseWorkbench.aiCollaboration.coursePlanFailed', '课程修改方案生成失败，请重试。'),
    ))
  }
}
async function handleAiRequest(instruction: string) {
  const request = instruction.trim()
  if (!request || aiCollaborationBusy.value || !activeAiDocument.value) return
  appendAiMessage('user', 'text', request)
  const route = routeTeacherProductionRequest(aiDomain.value, request)
  if (route.capability === 'clarify_request') {
    aiClarificationOptions.value = aiQuickActions.value.slice(0, 3).map(action => action.prompt)
    appendAiMessage(
      'assistant',
      'text',
      aiDomain.value === 'outline'
        ? '你希望先调整讲次顺序、学习路径，还是合并重复内容？'
        : aiDomain.value === 'question-bank'
          ? '你希望先补齐目标覆盖、增加应用题，还是强化错因诊断？'
        : aiDomain.value === 'script'
          ? '你希望先调整口语表达、课堂案例，还是讲解节奏？'
          : t('courseWorkbench.aiCollaboration.clarificationQuestion', '为了避免整段重写，你希望优先调整哪一部分？'),
    )
    lastAiOperation.value = ''
    transitionAi({ type: 'ASK_CLARIFICATION' })
    return
  }
  if (route.capability === 'plan_course_change') {
    lastAiCoursePlanRequestId.value = ''
    await createCourseChangePlanFromConversation()
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
  const objectName = aiDomain.value === 'outline'
    ? t('courseWorkbench.aiCollaboration.assetOutline', '大纲')
    : aiDomain.value === 'question-bank'
      ? t('courseWorkbench.aiCollaboration.assetQuestionBank', '题库')
      : aiDomain.value === 'script'
        ? t('courseWorkbench.aiCollaboration.assetScript', '讲义')
        : t('courseWorkbench.aiCollaboration.assetLessonPlan', '教案')
  const receipt = t(
    result.accept
      ? 'courseWorkbench.aiCollaboration.candidateReceiptApplied'
      : 'courseWorkbench.aiCollaboration.candidateReceiptDiscarded',
    result.accept
      ? '候选已采用，并形成新的{asset}工作修订。'
      : '候选已放弃，当前{asset}保持不变。',
  ).replace('{asset}', objectName)
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
  if (lastAiOperation.value === 'course_plan') {
    await createCourseChangePlanFromConversation()
    return
  }
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
function resolveLessonPrerequisite() {
  if (outlineGatePending.value) {
    activeStage.value = 'foundation'
    return
  }
  if (lessonStore.error || hasOutline.value || lessonStore.outlineRevisionId) {
    retryLessonSync()
    return
  }
  activeStage.value = 'foundation'
}
function clearLessonSyncRetryTimer() {
  if (lessonSyncRetryTimer !== null) window.clearTimeout(lessonSyncRetryTimer)
  lessonSyncRetryTimer = null
  lessonSyncRetryScheduled.value = false
}
function scheduleLessonSyncRetry() {
  if (!lessonSyncNeedsRecovery.value || lessonSyncRunning.value || lessonStore.loading || lessonSyncRetryTimer !== null) return
  if (lessonSyncAttempt.value >= LESSON_SYNC_RETRY_DELAYS.length) return
  lessonSyncRetryScheduled.value = true
  lessonSyncRetryTimer = window.setTimeout(() => {
    lessonSyncRetryTimer = null
    lessonSyncRetryScheduled.value = false
    void runLessonSyncAttempt()
  }, LESSON_SYNC_RETRY_DELAYS[lessonSyncAttempt.value])
}
async function runLessonSyncAttempt() {
  if (!lessonSyncNeedsRecovery.value || lessonSyncRunning.value || lessonStore.loading) return
  lessonSyncRunning.value = true
  lessonSyncAttempt.value += 1
  try {
    await lessonStore.load(props.courseId)
  } catch {
    // The page owns recovery; teachers only see a retry after automatic attempts are exhausted.
  } finally {
    lessonSyncRunning.value = false
    if (lessonStore.lessons.length) lessonSyncAttempt.value = 0
    else scheduleLessonSyncRetry()
  }
}
function retryLessonSync() {
  clearLessonSyncRetryTimer()
  lessonSyncAttempt.value = 0
  if (lessonSyncNeedsRecovery.value) void runLessonSyncAttempt()
  else void lessonStore.load(props.courseId).catch(() => undefined)
}
function selectLearningPurpose(value: LearningPurpose) {
  const previous = foundation.learningPurpose
  foundation.learningPurpose = value
  if (value === 'project' && (previous === 'systematic' || foundation.courseTeachingType === 'comprehensive')) {
    foundation.courseTeachingType = 'project'
  } else if (value !== 'project' && foundation.courseTeachingType === 'project') {
    foundation.courseTeachingType = 'comprehensive'
  }
}
function generationBindings(references: CourseReferenceItem[]) { return references.map(item => { const web = item.origin === 'web_search'; const highTrust = item.source_metadata?.credibility === 'high'; return { asset_id: item.material_asset_id, purpose: item.role === 'primary' ? 'content_source' as const : web && !highTrust ? 'weak_context' as const : 'supplement' as const, priority: item.role === 'primary' ? 'core' as const : web && !highTrust ? 'weak' as const : 'supporting' as const, authority: item.role === 'primary' ? 'primary' as const : web && !highTrust ? 'context_only' as const : 'secondary' as const, usage_policy: item.role === 'primary' ? 'must_use' as const : web && !highTrust ? 'optional' as const : 'prefer' as const, reuse_policy: item.reuse_policy || 'reference_only' as const, rights_basis: item.rights_basis || (web ? 'license_unknown' as const : 'teacher_asserted' as const), source_metadata: item.source_metadata || {}, source_label: item.source_label || item.filename } }) }
function currentGenerationOptions() {
  return canonicalizeCourseGenerationOptions(props.generationOptions)
}
async function saveRelationships(targetId: string, targetType: string, label: string) { const refs = activeReferences.value; const packageId = refs[0]?.package_id || String((await http.get('/api/teacher-course-spaces', teacherReadRequestConfig({ params: { course_id: props.courseId }, silentError: true }))).data?.[0]?.package_id || ''); if (!packageId) return; await http.put(`/api/teacher-course-spaces/${packageId}/relationships`, { target_id: targetId, target_type: targetType, target_label: label, sources: refs.map(item => ({ source_asset_id: item.asset_id, role: item.role })) }, teacherRequestConfig({ silentError: true })) }
async function submitFoundation() {
  generationRequested.value = true
  try {
    if (generationFailed.value && generationTask.value?.id) {
      await generationStore.resumeTask(
        props.courseId,
        generationTask.value.id,
      )
      return
    }
    const baseTeacherBrief = { ...(props.generationOptions.teacher_course_brief || {}) }
    delete baseTeacherBrief.chapter_count
    delete baseTeacherBrief.section_count
    const semanticRequirement = foundationSemanticRequirement.value
    const requirements = [
      props.generationOptions.requirements,
      semanticRequirement,
      foundation.requirements,
    ].filter(Boolean).join('\n')
    const additionalRequirements = [
      baseTeacherBrief.additional_requirements,
      semanticRequirement,
    ].filter(Boolean).join('\n')
    const courseIntent = foundation.learningPurpose === 'project'
      ? {
          schema_version: 'course_intent_v1' as const,
          type: 'project' as const,
          project_goal: foundation.goal,
          expected_deliverable: foundation.projectDeliverable,
          project_constraints: foundation.requirements,
        }
      : foundation.learningPurpose === 'exam'
        ? {
            schema_version: 'course_intent_v1' as const,
            type: 'exam' as const,
            exam_name: foundation.goal,
            exam_date: foundation.examDate,
            exam_scope: foundation.examScope,
          }
        : {
            schema_version: 'course_intent_v1' as const,
            type: 'systematic' as const,
            learning_goal: foundation.goal,
          }
    await saveRelationships('managed:outline', 'outline', t('courseFiles.names.outline', '课程大纲'))
    emit('generateOutline', {
      subject: props.courseTitle,
      options: {
        ...currentGenerationOptions(),
        requirements,
        learning_purpose: foundation.learningPurpose,
        course_teaching_type: foundation.courseTeachingType,
        pedagogy_mode: foundation.subjectType,
        course_intent: courseIntent,
        teacher_course_brief: {
          ...baseTeacherBrief,
          schema_version: 'teacher_course_brief_v1',
          target_audience: baseTeacherBrief.target_audience || '大学生',
          total_class_hours: foundation.totalHours,
          lesson_duration_minutes: 45,
          course_period_minutes: 45,
          lecture_count: Number(foundation.lectureCount),
          teaching_context: baseTeacherBrief.teaching_context || 'classroom',
          additional_requirements: additionalRequirements,
        },
        material_bindings: generationBindings(activeReferences.value),
      },
      references: activeReferences.value,
    })
  } catch {
    generationRequested.value = false
  }
}
async function confirmLectureOutlineShape() {
  if (shapeConfirming.value) return
  const count = Math.max(1, Number(foundation.lectureCount || outlineGrowthChapters.value.length || 1))
  shapeConfirming.value = true; shapeConfirmError.value = null
  try {
    await courseWorkspaceStore.confirmOutlineShape(props.courseId, Array.from({ length: count }, () => 1))
    generationRequested.value = true
    await generationStore.fetchGlobalTasks()
  } catch (error: any) { shapeConfirmError.value = error } finally { shapeConfirming.value = false }
}
function activeLessonGenerationSource() {
  const primary = activeReferences.value.find(item => item.role === 'primary')
  return primary ? { packageId: primary.package_id, assetId: primary.asset_id } : undefined
}
async function confirmSelectedLessonArrangement() {
  const lesson = selectedLesson.value
  if (!lesson?.arrangement || arrangementConfirming.value || lessonGenerationActive.value) return
  arrangementConfirming.value = true
  arrangementError.value = ''
  try {
    const updated = await lessonStore.confirmArrangement(
      props.courseId,
      lesson.lesson_unit_id,
      {
        lesson_type: (selectedLessonTypeDraft.value || lesson.arrangement.lesson_type) as typeof lesson.arrangement.lesson_type,
        blocks: lesson.arrangement.blocks,
      },
    )
    selectedLessonTypeDraft.value = updated.arrangement.lesson_type
  } catch {
    arrangementError.value = lessonStore.error || t('courseWorkbench.arrangement.confirmFailed', '本讲课型与教学结构确认失败，请重试。')
  } finally {
    arrangementConfirming.value = false
  }
}
async function generateSelectedLessonPlan() {
  const lesson = selectedLesson.value
  if (!lesson || lessonGenerationActive.value) return
  if (!lesson.arrangement?.confirmed) {
    arrangementError.value = t('courseWorkbench.arrangement.confirmBeforeGenerate', '请先确认本讲课型与教学结构。')
    return
  }
  arrangementError.value = ''
  lessonConfirmError.value = ''
  try {
    await lessonStore.generateLesson(
      props.courseId,
      lesson.lesson_unit_id,
      activeLessonGenerationSource(),
      '',
      activeReferences.value.map(item => item.material_asset_id),
      ['failed', 'cancelled', 'paused'].includes(String(lessonJob.value?.status || '')) ? lessonJob.value?.id || '' : '',
    )
  } catch {
    arrangementError.value = lessonStore.error || t('courseWorkbench.arrangement.generateFailed', '本讲教案生成失败，请重试。')
  }
}
async function generateAllLessonPlans() {
  if (batchStarting.value || batchRunning.value || !batchEligibleCount.value) return
  batchStarting.value = true
  lessonConfirmError.value = ''
  try {
    await lessonStore.generateAllLessons(
      props.courseId,
      activeLessonGenerationSource(),
      '',
      activeReferences.value.map(item => item.material_asset_id),
    )
  } catch {
    lessonConfirmError.value = lessonStore.error || t('courseWorkbench.lessonBatch.failed', '全部教案任务创建失败，请重试。')
  } finally {
    batchStarting.value = false
  }
}
function lessonTitleForJob(lessonUnitId: string) {
  return lessonStore.lessons.find(lesson => lesson.lesson_unit_id === lessonUnitId)?.title || lessonUnitId
}
async function pauseLessonJob(jobId: string) { await lessonStore.pauseJob(props.courseId, jobId).catch(() => undefined) }
async function cancelLessonJob(jobId: string) { await lessonStore.cancelJob(props.courseId, jobId).catch(() => undefined) }
async function pauseAllLessonGeneration() { await Promise.all(batchLessonJobs.value.filter(job => ['pending', 'running'].includes(job.status)).map(job => pauseLessonJob(job.id))) }
async function cancelAllLessonGeneration() { await Promise.all(batchLessonJobs.value.filter(job => ['pending', 'running'].includes(job.status)).map(job => cancelLessonJob(job.id))) }
async function confirmLessonPlan() { const revision = workingLessonRevision.value?.revision_id; if (!selectedLesson.value || !revision || lessonPlanConfirmed.value || lessonConfirming.value) return; lessonConfirming.value = true; lessonConfirmError.value = ''; try { await lessonStore.confirm(props.courseId, selectedLessonId.value, revision) } catch { lessonConfirmError.value = lessonStore.error || t('courseWorkbench.lessonConfirmFailed', '本讲教案确认失败，请重试。') } finally { lessonConfirming.value = false } }
function beginLessonPlanEditing() { lessonPlanDocument.value?.beginEditing() }
function cancelLessonPlanEditing() { lessonPlanDocument.value?.cancelEditing() }
async function saveLessonPlanDraft() { await lessonPlanDocument.value?.saveDraft() }
function beginScriptEditing() { scriptDocument.value?.beginEditing() }
function cancelScriptEditing() { scriptDocument.value?.cancelEditing() }
async function saveScriptDraft() { await scriptDocument.value?.saveDraft() }
async function toggleDocumentHistory(domain: TeacherHistoryDomain) {
  if (historyOpen.value && historyDomain.value === domain) {
    closeDocumentHistory()
    return
  }
  historyDomain.value = domain
  historyOpen.value = true
  if (domain === 'outline') {
    await courseWorkspaceStore.loadBlueprintDraftVersions(props.courseId).catch(() => undefined)
  }
}
function closeDocumentHistory() {
  historyOpen.value = false
  historyRestoringId.value = ''
}
async function restoreDocumentHistory(revisionId: string) {
  if (!revisionId || historyRestoringId.value) return
  if (editingOutline.value || lessonDocumentEditing.value || scriptDocumentEditing.value) return
  historyRestoringId.value = revisionId
  try {
    if (historyDomain.value === 'outline') {
      await outlineEditor.value?.restoreHistoryVersion(revisionId)
      await courseWorkspaceStore.loadBlueprintDraftVersions(props.courseId)
    } else if (historyDomain.value === 'lesson' && selectedLessonId.value) {
      await lessonStore.restorePlanRevision(props.courseId, selectedLessonId.value, revisionId)
    } else if (historyDomain.value === 'script' && selectedLessonId.value) {
      await lessonStore.restoreScriptRevision(props.courseId, selectedLessonId.value, revisionId)
    }
    handleAiCandidateChange(null)
  } catch {
    if (historyDomain.value === 'lesson') {
      lessonConfirmError.value = lessonStore.error || '教案历史版本恢复失败，请重试。'
    } else if (historyDomain.value === 'script') {
      scriptConfirmError.value = lessonStore.error || t('courseWorkbench.scriptDocument.restoreFailed', '讲义历史版本恢复失败，请重试。')
    }
  } finally {
    historyRestoringId.value = ''
  }
}
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
function preferredLessonId(lessons: typeof lessonStore.lessons): string {
  if (!lessons.length) return ''
  if (props.initialLessonId && lessons.some(item => item.lesson_unit_id === props.initialLessonId)) return props.initialLessonId
  const latestFailed = lessons
    .map(lesson => ({ lesson, job: lessonStore.latestJobByLesson(lesson.lesson_unit_id) }))
    .filter(item => ['failed', 'cancelled'].includes(String(item.job?.status || '')))
    .sort((left, right) => String(right.job?.updated_at || '').localeCompare(String(left.job?.updated_at || '')))[0]?.lesson
  if (latestFailed) return latestFailed.lesson_unit_id
  const affected = lessons.find(lesson => (
    lesson.plan.source_state === 'stale'
    || lesson.script?.source_state === 'stale'
    || lesson.plan.ppt_assets?.some(asset => asset.source_state === 'stale')
  ))
  if (affected) return affected.lesson_unit_id
  const unfinished = lessons.find(lesson => (
    !lesson.plan.confirmed_revision_id
    || !lesson.script?.confirmed
    || !lesson.plan.ppt_assets?.some(asset => asset.source_state === 'current' && asset.ppt_manuscript_status === 'confirmed')
  ))
  return unfinished?.lesson_unit_id || lessons[0]?.lesson_unit_id || ''
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
  if (aiCollaborationOpen.value && aiDomain.value === 'lesson' && selectedLessonSectionId.value !== sectionId) persistAiSession()
  selectedLessonId.value = lessonId
  selectedLessonSectionId.value = sectionId
}
function lessonGenerationState(lesson: any): 'pending' | 'generating' | 'review' | 'confirmed' | 'needs_review' | 'failed' {
  const jobStatus = String(lessonStore.latestJobByLesson(lesson.lesson_unit_id)?.status || '')
  if (jobStatus === 'running') return 'generating'
  if (['pending', 'paused'].includes(jobStatus)) return 'generating'
  if (['failed', 'cancelled'].includes(jobStatus)) return 'failed'
  if (lesson.plan?.source_state === 'stale' || jobStatus === 'completed_with_warnings') return 'needs_review'
  if (lesson.plan?.confirmed_revision_id) return 'confirmed'
  if (lesson.plan?.working_revision_id || ['completed', 'completed_with_warnings'].includes(jobStatus)) return 'review'
  return 'pending'
}
function lessonGenerationIsRunning(lesson: any): boolean {
  return String(lessonStore.latestJobByLesson(lesson.lesson_unit_id)?.status || '') === 'running'
}
function lessonGenerationStateLabel(lesson: any): string {
  const state = lessonGenerationState(lesson)
  const labels = {
    pending: t('courseWorkbench.lessonOutline.status.pending', '未生成'),
    generating: t('courseWorkbench.lessonOutline.status.generating', '生成中'),
    review: t('courseWorkbench.lessonOutline.status.review', '待确认'),
    confirmed: t('courseWorkbench.lessonOutline.status.confirmed', '已确认'),
    needs_review: t('courseWorkbench.lessonOutline.status.needsReview', '需复核'),
    failed: t('courseWorkbench.lessonOutline.status.failed', '失败'),
  }
  return labels[state]
}
async function handleScriptSaved() { scriptConfirmError.value = ''; await lessonStore.load(props.courseId) }
async function generateScript(requirements = '') {
  if (!selectedLesson.value || !confirmedLessonRevision.value || scriptGenerationBusy.value) return
  scriptGenerating.value = true
  scriptGenerationError.value = ''
  scriptConfirmError.value = ''
  try {
    await saveRelationships(`script:${selectedLessonId.value}`, 'script', `${selectedLesson.value.title} 讲义`)
    await lessonStore.generateScript(
      props.courseId,
      selectedLessonId.value,
      requirements,
      activeReferences.value.map(item => item.material_asset_id),
      ['failed', 'cancelled', 'paused'].includes(String(scriptJob.value?.status || '')) ? scriptJob.value?.id || '' : '',
    )
  } catch {
    scriptGenerationError.value = lessonStore.error || t('courseWorkbench.scriptGenerationFailed', '本讲讲义生成失败，请重试。')
  } finally {
    scriptGenerating.value = false
  }
}
async function cancelScriptGeneration() {
  if (!scriptJob.value || !scriptGenerationActive.value) return
  scriptGenerationError.value = ''
  await lessonStore.cancelJob(props.courseId, scriptJob.value.id).catch(() => undefined)
}
async function pauseScriptGeneration() {
  if (!scriptJob.value || !scriptGenerationActive.value) return
  scriptGenerationError.value = ''
  await lessonStore.pauseJob(props.courseId, scriptJob.value.id).catch(() => undefined)
}
async function confirmScript() {
  const revision = selectedLesson.value?.script.current_revision_id
  if (!selectedLesson.value || !revision || scriptConfirmed.value || scriptConfirming.value || !scriptPublicationEligible.value) return
  scriptConfirming.value = true
  scriptConfirmError.value = ''
  try {
    await lessonStore.confirmScript(props.courseId, selectedLessonId.value, revision)
  } catch {
    scriptConfirmError.value = lessonStore.error || t('courseWorkbench.scriptConfirmFailed', '本讲讲义确认失败，请重试。')
  } finally {
    scriptConfirming.value = false
  }
}
async function openPptWorkspace() {
  if (!selectedLesson.value || !confirmedLessonRevision.value || !scriptConfirmed.value) return
  await preparePptSources()
  window.location.assign(`/course/${props.courseId}/ppt?lesson=${selectedLessonId.value}`)
}
async function preparePptSources() {
  if (!selectedLesson.value) return
  await saveRelationships(
    `ppt-v6:${selectedLessonId.value}`,
    'ppt',
    `${selectedLesson.value.title} PPT`,
  )
}
async function handleCompanionSaved(document: { document_id: string; title: string; revision_id: string }) { await saveRelationships(`companion-document:${document.document_id}`, 'companion_document', document.title) }
function handleInlineOutlineConfirmed() { emit('outlineConfirmed') }
async function confirmInlineOutline() {
  if (!outlineEditor.value || outlineConfirming.value) return
  outlineConfirming.value = true
  try {
    await outlineEditor.value.confirmOutline()
  } finally {
    outlineConfirming.value = false
  }
}
async function toggleOutlineEditing() {
  if (stageSwitching.value) return
  if (!editingOutline.value) {
    editingOutline.value = true
    return
  }
  if (!outlineEditor.value) return
  stageSwitching.value = true
  try {
    const saved = await outlineEditor.value.finishEditing()
    if (saved) editingOutline.value = false
  } finally {
    stageSwitching.value = false
  }
}
async function requestStageChange(stage: StageId) {
  if (stage === activeStage.value || stageSwitching.value) return
  stageSwitching.value = true
  try {
    if (activeStage.value === 'foundation' && showOutlineWorkspace.value && outlineEditor.value) {
      const saved = await outlineEditor.value.finishEditing()
      if (!saved) return
    }
    activeStage.value = stage
  } finally {
    stageSwitching.value = false
  }
}
async function openCompanionTemplate(templateId: CompanionTemplateId) {
  activeCompanionTemplateId.value = templateId
  if (activeStage.value === 'companion') {
    closeAiCollaboration()
    closeLessonOutline()
    closeDocumentHistory()
    if (workbenchCenter.value) workbenchCenter.value.scrollTop = 0
    return
  }
  await requestStageChange('companion')
}
async function loadQuestionBankStatus() { if (!props.courseId) return; try { const response = await http.get(`/api/courses/${props.courseId}/question-bank`, teacherReadRequestConfig({ silentError: true })); questionBankReady.value = Number(response.data?.total || 0) > 0; questionBankRevisionId.value = String(response.data?.bundle_revision_id || '') } catch { questionBankReady.value = false; questionBankRevisionId.value = '' } }

watch(() => props.generationOptions, options => {
  const canonical = canonicalizeCourseGenerationOptions(options)
  const intent = canonical.course_intent as any
  const brief = canonical.teacher_course_brief
  foundation.learningPurpose = (canonical.learning_purpose || 'systematic') as LearningPurpose
  foundation.goal = String(
    intent?.learning_goal
    || intent?.project_goal
    || intent?.exam_name
    || intent?.core_question
    || canonical.requirements
    || props.courseTitle,
  )
  foundation.projectDeliverable = String(intent?.expected_deliverable || '')
  foundation.examDate = String(intent?.exam_date || '')
  foundation.examScope = String(intent?.exam_scope || '')
  foundation.subjectType = (canonical.pedagogy_mode || 'auto') as PedagogyModeSelection
  foundation.courseTeachingType = (canonical.course_teaching_type || 'comprehensive') as CourseTeachingType
  foundation.totalHours = Number(brief?.total_class_hours || 32)
  foundation.lectureCount = Number(brief?.lecture_count || brief?.section_count || 16)
  foundation.requirements = String(canonical.requirements || '')
}, { immediate: true, deep: true })
watch([outlineShapeAwaitingReview, outlineShapeRevision], ([waiting, revision]) => {
  if (!waiting || !revision || loadedShapeRevision.value === revision) return
  loadedShapeRevision.value = revision
  shapeConfirmError.value = null
  void confirmLectureOutlineShape()
}, { immediate: true })
watch(() => generationTask.value?.phaseDetail?.outline_growth, value => { if (value && typeof value === 'object') retainedOutlineGrowth.value = JSON.parse(JSON.stringify(value)) as Record<string, any> }, { immediate: true, deep: true })
watch(outlineAwaitingReview, waiting => { if (waiting) void courseStore.refreshGenerationPreview(props.courseId, 'teacher') }, { immediate: true })
watch(() => props.initialStage, stage => { void requestStageChange(stage) })
watch(() => props.initialLessonId, lessonId => { if (lessonId) selectedLessonId.value = lessonId })
watch([() => props.courseId, () => lessonStore.outlineRevisionId], () => {
  clearLessonSyncRetryTimer()
  lessonSyncAttempt.value = 0
})
watch([
  activeStage,
  outlineGatePending,
  hasOutline,
  () => lessonStore.outlineRevisionId,
  () => lessonStore.loading,
  () => lessonStore.lessons.length,
], () => {
  if (lessonStore.lessons.length || !lessonSyncNeedsRecovery.value) {
    clearLessonSyncRetryTimer()
    if (lessonStore.lessons.length) lessonSyncAttempt.value = 0
    return
  }
  scheduleLessonSyncRetry()
}, { immediate: true })
watch(activeStage, stage => { if (stage !== 'foundation') editingOutline.value = false; closeAiCollaboration(); closeLessonOutline(); closeDocumentHistory(); aiCandidate.value = null; if (workbenchCenter.value) workbenchCenter.value.scrollTop = 0 }, { flush: 'post' })
watch(aiCollaborationOpen, open => {
  if (open) closeLessonOutline()
  else aiSourcesOpen.value = false
})
watch([aiMessages, aiPhase, aiClarificationOptions], persistAiSession, { deep: true, flush: 'post' })
watch(currentAiScopeKey, scopeKey => {
  if (!aiCollaborationOpen.value || aiCandidatePending.value || scopeKey === aiSessionScopeKey.value) return
  aiCandidate.value = null
  aiClarificationOptions.value = []
  if (!restoreAiSession()) resetAiSession()
  transitionAi({ type: 'OPEN', candidatePending: false })
})
watch(lessonOutlineRoot, (root, _previousRoot, onCleanup) => {
  if (!root) return
  document.addEventListener('pointerdown', closeLessonOutlineOnOutsidePointer)
  onCleanup(() => document.removeEventListener('pointerdown', closeLessonOutlineOnOutsidePointer))
}, { flush: 'post' })
watch(() => lessonStore.lessons, lessons => {
  if (!lessons.some(item => item.lesson_unit_id === selectedLessonId.value)) {
    selectedLessonId.value = preferredLessonId(lessons)
  }
  const lesson = lessons.find(item => item.lesson_unit_id === selectedLessonId.value)
  if (!lesson) return
  if (!selectedLessonTypeDraft.value || selectedLessonTypeDraft.value === selectedLesson.value?.arrangement?.lesson_type) {
    selectedLessonTypeDraft.value = lesson.arrangement?.lesson_type || ''
  }
  if (!lesson.sections.some(section => section.section_node_id === selectedLessonSectionId.value)) {
    selectedLessonSectionId.value = lesson.sections[0]?.section_node_id || ''
  }
}, { immediate: true, deep: true })
watch(selectedLessonId, (lessonId, previousLessonId) => {
  if (previousLessonId && lessonId !== previousLessonId) closeAiCollaboration()
  if (previousLessonId && lessonId !== previousLessonId) closeDocumentHistory()
  lessonConfirmError.value = ''
  arrangementError.value = ''
  scriptGenerationError.value = ''
  scriptConfirmError.value = ''
  const lesson = lessonStore.lessons.find(item => item.lesson_unit_id === lessonId)
  if (!lesson) {
    selectedLessonSectionId.value = ''
    selectedLessonTypeDraft.value = ''
    return
  }
  selectedLessonTypeDraft.value = lesson.arrangement?.lesson_type || ''
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
  clearLessonSyncRetryTimer()
  stopAiPaneResize()
  window.removeEventListener('resize', updateAiPaneBounds)
})
</script>

<style scoped>
.teacher-workbench{height:100%;min-height:0;display:grid;grid-template-columns:210px minmax(520px,1fr) 310px;overflow:hidden;background:#f3f5f9}.stage-rail{min-height:0;display:flex;flex-direction:column;border-right:1px solid #e4e9f1;background:#fff}.stage-rail>header{display:grid;gap:10px;padding:21px 18px 16px}.stage-rail>header strong{color:#1f2a40;font-size:15px}.course-information-entry{min-height:32px;display:flex;align-items:center;gap:7px;padding:0 9px;border:1px solid #dfe4ec;border-radius:8px;color:#566279;background:#fff;font-size:14px;font-weight:700;cursor:pointer}.course-information-entry:hover,.course-information-entry:focus-visible{border-color:#c7c9ee;color:#4338ca;background:#f7f7ff;outline:none}.stage-rail nav{display:grid;gap:4px;padding:4px 9px}.stage-rail nav button{min-height:54px;display:grid;grid-template-columns:26px 22px minmax(0,1fr) 18px;align-items:center;gap:8px;padding:8px 10px;border:0;border-radius:10px;color:#64748b;background:transparent;text-align:left;cursor:pointer}.stage-rail nav button:hover{background:#f6f7fb}.stage-rail nav button.active{color:#4338ca;background:#eef0ff}.stage-rail nav button>span{font-size:15px;font-weight:800}.stage-rail nav strong{min-width:0;color:#334155;font-size:14px}.stage-rail nav button.active strong{color:#3730a3}.stage-rail nav button>svg:last-child{color:#16a34a}.stage-rail>footer{display:grid;grid-template-columns:auto minmax(0,1fr);align-items:center;gap:9px;margin-top:auto;padding:16px 18px;color:#64748b;font-size:14px}.stage-rail>footer>div{height:4px;overflow:hidden;border-radius:2px;background:#e8ecf3}.stage-rail>footer i{height:100%;display:block;background:#5b57e8}.workbench-center{min-width:0;min-height:0;overflow:auto;padding:24px 26px 52px}.center-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;max-width:860px;margin:0 auto 18px}.center-heading>div{display:grid;gap:4px}.center-heading small{color:#6366f1;font-size:14px;font-weight:800}.center-heading h2{margin:0;color:#172033;font-size:24px;letter-spacing:-.018em}.center-heading>button,.formal-surface>header button,.generation-surface>header button{min-height:36px;display:flex;align-items:center;gap:7px;padding:0 11px;border:1px solid #d7dde7;border-radius:8px;color:#475569;background:#fff;font-size:14px;font-weight:700;cursor:pointer}.generation-header-actions{display:flex!important;align-items:center;gap:7px}.stage-form,.formal-surface,.generation-surface,.lesson-stage{max-width:860px;margin:0 auto;border:1px solid #e0e6ef;border-radius:14px;background:#fff;box-shadow:0 10px 30px rgba(30,41,59,.05)}.stage-form{display:grid;gap:20px;padding:26px}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.form-field{display:grid;gap:8px}.form-field>span,.lesson-selector>span{color:#334155;font-size:14px;font-weight:700}.form-field b{color:#dc2626}.form-field input,.form-field select,.form-field textarea,.lesson-selector select{width:100%;min-height:44px;padding:10px 11px;border:1px solid #cfd7e3;border-radius:8px;outline:0;color:#172033;background:#fff;font:inherit;font-size:14px}.form-field textarea{resize:vertical;line-height:1.6}.form-field input:focus,.form-field select:focus,.form-field textarea:focus,.form-field textarea:focus,.lesson-selector select:focus{border-color:#5b57e8;box-shadow:0 0 0 3px rgba(91,87,232,.11)}.stage-form>footer{display:flex;align-items:center;justify-content:space-between;gap:16px;padding-top:2px}.stage-form>footer>span{color:#64748b;font-size:14px}.primary{min-height:42px;display:flex;align-items:center;gap:7px;padding:0 15px;border:1px solid #514bdc;border-radius:8px;color:#fff;background:#514bdc;font-size:14px;font-weight:750;cursor:pointer;box-shadow:0 7px 18px rgba(81,75,220,.16)}.primary:disabled{opacity:.48;cursor:not-allowed}.generation-surface{overflow:hidden}.generation-surface>header,.formal-surface>header{min-height:64px;display:flex;align-items:center;justify-content:space-between;gap:16px;padding:0 20px;border-bottom:1px solid #e7ebf2}.generation-surface>header>div{display:flex;align-items:center;gap:10px;color:#4f46e5}.generation-surface>header span,.formal-surface>header>div{display:grid;gap:3px}.generation-surface>header strong,.formal-surface>header strong{color:#263147;font-size:14px}.generation-surface>header small,.formal-surface>header small{color:#64748b;font-size:14px}.generation-progress{height:3px;background:#e8ebf5}.generation-progress i{width:100%;height:100%;display:block;transform-origin:left;background:#5b57e8;transition:transform .25s ease-out}.stream-content,.formal-surface>article{max-height:calc(100vh - 260px);overflow:auto;padding:22px 28px 42px}.stream-content section,.formal-surface article section{margin-bottom:26px}.stream-content h3,.formal-surface h3{margin:0 0 10px;color:#202b40;font-size:17px}.stream-waiting{min-height:260px;display:flex;align-items:center;justify-content:center;gap:9px;color:#64748b;font-size:14px}.stream-caret{width:2px;height:18px;display:inline-block;background:#5b57e8;animation:blink .8s steps(1) infinite}.generation-error{margin:0;padding:12px 20px;color:#b91c1c;background:#fff1f2;font-size:14px}.generation-error button{border:0;color:inherit;background:transparent;font-weight:750;text-decoration:underline;cursor:pointer}.lesson-stage{padding:0 0 24px}.lesson-selector{display:grid;grid-template-columns:110px minmax(0,1fr);align-items:center;gap:14px;padding:18px 22px;border-bottom:1px solid #e7ebf2}.stage-form--lesson{border:0;box-shadow:none}.prerequisite,.empty-asset{min-height:260px;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:10px;color:#64748b;font-size:14px}.prerequisite strong{color:#334155}.prerequisite button{padding:7px 10px;border:1px solid #d7dde7;border-radius:7px;color:#4f46e5;background:#fff;font-weight:700;cursor:pointer}.lesson-formal{margin:20px 20px 0;border-radius:10px;box-shadow:none}.lesson-formal>article{max-height:calc(100vh - 360px)}.formal-surface ol{display:grid;gap:8px;padding-left:22px;color:#475569;font-size:14px}.spin{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}@keyframes blink{50%{opacity:0}}
.center-heading>.center-heading-actions{display:flex;align-items:center;gap:8px}
.center-heading-actions>button{min-height:36px;display:flex;align-items:center;gap:7px;padding:0 11px;border:1px solid #d7dde7;border-radius:8px;color:#475569;background:#fff;font-size:14px;font-weight:700;cursor:pointer}
.center-heading-actions>button:focus-visible{outline:2px solid #5b57e8;outline-offset:2px}
.center-heading-actions>button:disabled{opacity:.48;cursor:not-allowed}
.center-heading-actions>.outline-manual-action{border-color:#d7dde7;color:#475569;background:#fff;box-shadow:none}
.center-heading-actions>.outline-manual-action:hover:not(:disabled){border-color:#bfc7d4;color:#3730a3;background:#f8f8fc}
.center-heading-actions>.outline-manual-action[aria-pressed="true"]{border-color:#c9c8ee;color:#3730a3;background:#f4f3ff}
.center-heading-actions>.outline-confirm-action{border-color:#454ca8;color:#fff;background:#454ca8;box-shadow:0 7px 18px rgba(69,76,168,.16)}
.center-heading-actions>.outline-confirm-action:hover:not(:disabled){border-color:#3f4598;background:#3f4598}
.stage-form>footer{justify-content:flex-end}
.foundation-presets{display:grid;margin:2px 0 0;padding:4px 0;border-top:1px solid #e8ebf2;border-bottom:1px solid #e8ebf2}.foundation-presets>header{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;padding:17px 2px 14px}.foundation-presets>header>div{display:grid;gap:4px}.foundation-presets>header strong{color:#273247;font-size:14px}.foundation-presets>header span{color:#778195;font-size:14px;line-height:1.55}.foundation-presets>header>small{padding-top:2px;color:#555db6;font-size:14px;font-weight:750;white-space:nowrap}.foundation-preset-row{display:grid;grid-template-columns:150px minmax(0,1fr);align-items:center;gap:18px;padding:15px 2px;border-top:1px solid #eff1f5}.foundation-preset-row>div:first-child{display:grid;gap:3px}.foundation-preset-row>div:first-child strong{color:#354056;font-size:14px}.foundation-preset-row>div:first-child span{color:#8991a0;font-size:14px;line-height:1.45}.foundation-preset-options{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.foundation-preset-options>button{min-width:0;min-height:58px;display:grid;grid-template-columns:auto minmax(0,1fr);align-items:center;gap:7px;padding:8px 10px;border:1px solid #dfe3eb;border-radius:10px;color:#5e687b;background:#fff;text-align:left;cursor:pointer;transition:border-color .18s ease,background .18s ease,color .18s ease,transform .18s cubic-bezier(.16,1,.3,1)}.foundation-preset-options>button:not(.selected){grid-template-columns:minmax(0,1fr)}.foundation-preset-options>button:hover{transform:translateY(-1px);border-color:#c7cae9;background:#fafaff}.foundation-preset-options>button:focus-visible{outline:3px solid rgba(79,70,217,.14);outline-offset:1px}.foundation-preset-options>button.selected{border-color:#bfc2e8;color:#41489f;background:#f4f4ff}.foundation-preset-options>button>svg{color:#555db6}.foundation-preset-options>button>span{min-width:0;display:grid;gap:2px}.foundation-preset-options>button strong{overflow:hidden;color:inherit;font-size:14px;font-weight:800;text-overflow:ellipsis;white-space:nowrap}.foundation-preset-options>button small{overflow:hidden;color:#828b9c;font-size:14px;line-height:1.35;text-overflow:ellipsis;white-space:nowrap}.stage-form>footer>span{max-width:520px;color:#7b8495;font-size:14px;line-height:1.5}.stage-form>footer{justify-content:space-between}
.foundation-semantics{display:grid;margin:2px 0 0;border-block:1px solid #e8ebf2}.foundation-semantics>header{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;padding:18px 2px 15px}.foundation-semantics>header>div{display:grid;gap:4px}.foundation-semantics>header strong{color:#273247;font-size:14px}.foundation-semantics>header span{max-width:68ch;color:#778195;font-size:14px;line-height:1.55}.foundation-semantics>header>small{padding-top:2px;color:#555db6;font-size:14px;font-weight:750;white-space:nowrap}.foundation-semantic-row{display:grid;grid-template-columns:145px minmax(0,1fr);align-items:center;gap:18px;padding:16px 2px;border-top:1px solid #eff1f5}.foundation-semantic-row>div:first-child{display:grid;gap:4px}.foundation-semantic-row>div:first-child strong{color:#354056;font-size:14px}.foundation-semantic-row>div:first-child span{color:#8991a0;font-size:14px;line-height:1.45}.foundation-semantic-options{display:grid;gap:8px}.foundation-semantic-options--three,.foundation-semantic-options--six{grid-template-columns:repeat(3,minmax(0,1fr))}.foundation-semantic-options>button{min-width:0;min-height:62px;display:grid;grid-template-columns:auto minmax(0,1fr);align-items:center;gap:8px;padding:9px 11px;border:1px solid #dfe3eb;border-radius:10px;color:#5e687b;background:#fff;text-align:left;cursor:pointer;transition:border-color .18s ease,background-color .18s ease,color .18s ease,transform .18s cubic-bezier(.16,1,.3,1)}.foundation-semantic-options>button:not(.selected){grid-template-columns:minmax(0,1fr)}.foundation-semantic-options>button:hover{transform:translateY(-1px);border-color:#c7cae9;background:#fafaff}.foundation-semantic-options>button:focus-visible,.foundation-subject-select select:focus-visible{outline:3px solid rgba(79,70,217,.14);outline-offset:1px}.foundation-semantic-options>button.selected{border-color:#bfc2e8;color:#41489f;background:#f4f4ff}.foundation-semantic-options>button>svg{color:#555db6}.foundation-semantic-options>button>span{min-width:0;display:grid;gap:3px}.foundation-semantic-options>button strong{color:inherit;font-size:14px;font-weight:800;line-height:1.35}.foundation-semantic-options>button small{color:#7d8799;font-size:14px;line-height:1.4}.foundation-semantic-row--compact{align-items:start}.foundation-subject-select{display:grid;grid-template-columns:minmax(220px,300px) minmax(0,1fr);align-items:center;gap:14px}.foundation-subject-select select{width:100%;min-height:42px;padding:8px 34px 8px 11px;border:1px solid #cfd7e3;border-radius:8px;outline:0;color:#263147;background:#fff;font:inherit;font-size:14px}.foundation-subject-select small{color:#7b8495;font-size:14px;line-height:1.5}.foundation-purpose-fields{display:grid;padding:16px 2px;border-top:1px solid #eff1f5}.foundation-purpose-fields--two{grid-template-columns:minmax(160px,.55fr) minmax(0,1.45fr);gap:14px}.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap}.stage-form>footer>span{max-width:520px;color:#7b8495;font-size:14px;line-height:1.5}.stage-form>footer{justify-content:space-between}
.teacher-workbench.is-ai-collaboration{grid-template-columns:minmax(560px,1fr) 10px var(--ai-pane-width);background:#eef1f6}.is-ai-collaboration>.workbench-center{padding:0;overflow:auto;background:#f3f5f9;scrollbar-width:thin;scrollbar-color:transparent transparent}.is-ai-collaboration>.workbench-center:hover{scrollbar-color:#cbd3df transparent}.is-ai-collaboration>.workbench-center::-webkit-scrollbar{width:6px}.is-ai-collaboration>.workbench-center::-webkit-scrollbar-thumb{border-radius:6px;background:transparent}.is-ai-collaboration>.workbench-center:hover::-webkit-scrollbar-thumb{background:#cbd3df}.is-ai-collaboration>.workbench-center>.center-heading{display:none}.is-ai-collaboration .lesson-stage{max-width:none;min-height:100%;margin:0;border:0;border-radius:0;box-shadow:none}.is-ai-collaboration .lesson-outline,.is-ai-collaboration .lesson-outline-toggle{display:none}.is-ai-collaboration .has-lesson-outline .lesson-workspace{display:block}.is-ai-collaboration .has-lesson-outline .lesson-stage-content{overflow:visible;border:0;border-radius:0;box-shadow:none}.is-ai-collaboration :deep(.lesson-document){min-height:100vh}.ai-workspace-resizer{position:relative;z-index:4;min-height:0;cursor:col-resize;background:#eef1f6;touch-action:none}.ai-workspace-resizer::before{position:absolute;inset:0;content:""}.ai-workspace-resizer::after{position:absolute;inset-block:0;left:50%;width:1px;background:#d9dee8;content:"";transform:translateX(-50%)}.ai-workspace-resizer i{position:absolute;z-index:1;top:50%;left:50%;width:3px;height:52px;border-radius:3px;background:#9aa3b5;opacity:.5;transform:translate(-50%,-50%) scaleY(.8);transition:transform .14s ease,opacity .14s ease,background-color .14s ease}.ai-workspace-resizer:hover,.ai-workspace-resizer:focus-visible,.ai-workspace-resizer.is-resizing{background:#f5f4ff}.ai-workspace-resizer:hover i,.ai-workspace-resizer:focus-visible i,.ai-workspace-resizer.is-resizing i{background:#625dd7;opacity:1;transform:translate(-50%,-50%) scaleY(1)}.ai-workspace-resizer:focus-visible{outline:2px solid #818cf8;outline-offset:-2px}
.stage-rail>header{display:block;padding:22px 18px 18px}.stage-rail>header .stage-rail-title{color:#1f2a40;font-size:18px;line-height:1.25}
.companion-entry{display:grid;gap:7px;margin:10px 9px 0;padding-top:14px;border-top:1px solid #e7ebf2}.companion-entry>small{padding:0 10px;color:#64748b;font-size:14px;font-weight:700}.companion-entry>button{min-height:50px;display:grid;grid-template-columns:22px minmax(0,1fr) 16px;align-items:center;gap:9px;padding:8px 10px;border:0;border-radius:10px;color:#64748b;background:transparent;text-align:left;cursor:pointer}.companion-entry>button:hover{background:#f6f7fb}.companion-entry>button.active{color:#4338ca;background:#eef0ff}.companion-entry strong{min-width:0;color:#334155;font-size:14px}.companion-entry>button.active strong{color:#3730a3}
.question-workbench-surface{max-width:860px;margin:0 auto;padding:0}
@media(max-width:1050px){.teacher-workbench{grid-template-columns:180px minmax(0,1fr) 280px}.workbench-center{padding-inline:18px}.stage-rail nav button{grid-template-columns:23px minmax(0,1fr)}.stage-rail nav button>svg,.stage-rail nav button>svg:last-child{display:none}}
@media(max-width:760px){.teacher-workbench{height:auto;min-height:100%;grid-template-columns:1fr;overflow:auto}.stage-rail{display:block;border-right:0;border-bottom:1px solid #e4e9f1}.stage-rail>header,.stage-rail>footer{display:none}.stage-rail nav{grid-template-columns:repeat(4,minmax(0,1fr));overflow:auto;padding:8px}.stage-rail nav button{min-width:108px;min-height:50px;grid-template-columns:22px minmax(0,1fr);padding:6px 8px}.workbench-center{overflow:visible;padding:18px 12px 30px}.center-heading h2{font-size:21px}.center-heading>button{font-size:0;width:38px;padding:0;justify-content:center}.stage-form{padding:19px 16px}.form-grid{grid-template-columns:1fr}.foundation-preset-row{grid-template-columns:1fr;gap:9px}.foundation-preset-options{grid-template-columns:1fr}.foundation-preset-options>button{min-height:52px}.stage-form>footer{align-items:stretch;flex-direction:column}.primary{justify-content:center}.lesson-selector{grid-template-columns:1fr}.stream-content,.formal-surface>article{max-height:none;padding-inline:18px}.reference-tray{border-left:0;border-top:1px solid #e4e9f1}}
@media(max-width:760px){.foundation-semantic-row{grid-template-columns:1fr;gap:10px}.foundation-semantic-options--three,.foundation-semantic-options--six{grid-template-columns:1fr}.foundation-semantic-options>button{min-height:54px}.foundation-subject-select{grid-template-columns:1fr;gap:7px}.foundation-purpose-fields--two{grid-template-columns:1fr}}
@media(max-width:760px){.center-heading-actions>button{width:38px;padding:0;justify-content:center;font-size:0}}
.stream-failed{color:#b91c1c;background:#fffafa}
.outline-shape-review>article{padding-bottom:20px}.shape-chapter-list{display:grid;gap:0;margin:0;padding:0!important;list-style:none}.shape-chapter-list li{min-height:72px;display:grid;grid-template-columns:34px minmax(0,1fr) auto;align-items:center;gap:12px;padding:10px 2px;border-bottom:1px solid #edf1f6}.shape-chapter-index{width:30px;height:30px;display:grid;place-items:center;border-radius:50%;color:#4f46e5;background:#eef2ff;font-size:14px;font-weight:800}.shape-chapter-list li>div{min-width:0;display:grid;gap:4px}.shape-chapter-list li>div strong{color:#263147;font-size:14px}.shape-chapter-list li>div small{color:#64748b;font-size:14px;line-height:1.45}.shape-chapter-list label{display:flex;align-items:center;gap:7px;color:#64748b;font-size:14px}.shape-chapter-list input{width:68px;min-height:36px;padding:6px 8px;border:1px solid #cfd7e3;border-radius:7px;outline:0;color:#172033;background:#fff;font:inherit;font-size:14px;text-align:center}.shape-chapter-list input:focus{border-color:#5b57e8;box-shadow:0 0 0 3px rgba(91,87,232,.11)}.outline-shape-review>footer{min-height:66px;display:flex;align-items:center;justify-content:space-between;gap:16px;padding:10px 20px;border-top:1px solid #e7ebf2}.outline-shape-review>footer>span{color:#64748b;font-size:14px}.shape-confirm-error{margin:12px 0 0}
.workbench-error{margin:12px 20px 16px}.prerequisite-error{margin:24px}.lesson-generation-actions{display:flex;align-items:center;gap:9px}.lesson-generation-actions button{min-height:44px;display:inline-flex;align-items:center;justify-content:center;gap:7px;padding:0 15px;border:1px solid #cfd6e3;border-radius:8px;color:#475569;background:#fff;font-size:15px;font-weight:750;cursor:pointer}.lesson-generation-actions button:hover:not(:disabled){border-color:#aaa7e8;color:#3730a3;background:#f8f8ff}.lesson-generation-actions button:focus-visible{outline:2px solid #5b57e8;outline-offset:2px}.lesson-generation-actions button:disabled{opacity:.5;cursor:not-allowed}.lesson-generation-actions .primary-action{border-color:#514bdc;color:#fff;background:#514bdc}.lesson-generation-actions .primary-action:hover:not(:disabled){border-color:#4338ca;color:#fff;background:#4338ca}.lesson-generation-toolbar-status{min-height:44px;display:flex;align-items:center;gap:9px;color:#5551c6;font-size:15px;white-space:nowrap}.lesson-generation-toolbar-status strong{color:#30394e;font-size:15px}.lesson-generation-toolbar-status em{font-size:15px;font-style:normal;font-weight:750;font-variant-numeric:tabular-nums}.lesson-generation-status{min-height:58px;display:flex;align-items:center;justify-content:space-between;gap:18px;padding:0 30px;border-bottom:1px solid #eceef4;background:#fafaff}.lesson-generation-status>div{min-width:0;display:flex;align-items:center;gap:10px;color:#5752d4}.lesson-generation-status span{min-width:0;display:grid;gap:2px}.lesson-generation-status strong,.lesson-generation-status small{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.lesson-generation-status strong{color:#30394e;font-size:15px}.lesson-generation-status small{color:#667386;font-size:15px}.lesson-generation-status em{color:#5b57d7;font-size:15px;font-style:normal;font-weight:750;font-variant-numeric:tabular-nums}.lesson-stream-document{padding:34px 50px 64px}.lesson-stream-document>small{display:block;margin-bottom:9px;color:#6366f1;font-size:15px;font-weight:800;letter-spacing:.04em}.lesson-stream-document h3{margin:0 0 22px;color:#202b40;font-size:20px}.lesson-stream-document p{max-width:75ch;margin:0 0 15px;color:#475569;font-size:15px;line-height:1.8}.lesson-stream-document .stream-caret{height:15px;margin-left:3px;vertical-align:-2px}.lesson-stream-waiting{min-height:280px;display:flex;align-items:center;justify-content:center;color:#64748b;font-size:15px}.lesson-queue-state{min-height:330px;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:32px;color:#6f7a90;text-align:center}.lesson-queue-state svg{margin-bottom:15px;color:#7470d8}.lesson-queue-state strong{color:#354057;font-size:16px}.lesson-queue-state p{max-width:38ch;margin:8px 0 0;font-size:15px;line-height:1.65}.lesson-empty-canvas{min-height:430px;display:grid;place-items:center;color:#778397;background:#fff;font-size:15px}
.workbench-center.is-outline-workspace{padding-bottom:24px}.outline-workspace{overflow:hidden}.outline-workspace.is-outline-editing{overflow:visible}.outline-workspace>.inline-outline-review{width:100%;min-height:0}
.prerequisite{padding:28px;text-align:center}.prerequisite>span{max-width:480px;line-height:1.55}.prerequisite[data-state="review"]>svg{color:#4f46e5}.prerequisite[data-state="error"]>svg{color:#b91c1c}.prerequisite button{min-height:36px;padding:7px 11px}.prerequisite button:hover{border-color:#aaa7f4;background:#f7f7ff}.prerequisite button:focus-visible{outline:2px solid #5b57e8;outline-offset:2px}.prerequisite button:disabled{opacity:.5;cursor:not-allowed}
.workbench-center.is-lesson-workspace .center-heading,.workbench-center.is-lesson-workspace .lesson-stage{max-width:1160px}.lesson-workspace{min-width:0}.lesson-stage-content{min-width:0}.lesson-stage.has-lesson-outline{overflow:visible;border:0;border-radius:0;background:transparent;box-shadow:none}.has-lesson-outline .lesson-workspace{display:grid;grid-template-columns:206px minmax(0,1fr);gap:12px;transition:grid-template-columns .2s cubic-bezier(.2,.8,.2,1)}.has-lesson-outline .lesson-workspace.is-outline-collapsed{grid-template-columns:30px minmax(0,1fr)}.has-lesson-outline .lesson-stage-content{overflow:hidden;border:1px solid #e0e6ef;border-radius:14px;background:#fff;box-shadow:0 10px 30px rgba(30,41,59,.05)}.lesson-outline{min-width:0;align-self:start;display:grid;grid-template-columns:minmax(0,1fr) 28px;background:transparent}.is-outline-collapsed .lesson-outline{grid-template-columns:28px}.lesson-outline>nav{max-height:calc(100vh - 205px);overflow:auto;padding:0 4px 0 0}.lesson-outline-chapter{display:grid}.lesson-outline-chapter-button{min-height:48px;display:grid;grid-template-columns:9px minmax(0,1fr);align-items:center;gap:7px;width:100%;padding:6px 5px;border:0;color:#94a3b8;background:transparent;text-align:left;cursor:pointer}.lesson-outline-chapter-marker{width:5px;height:5px;justify-self:center;border:1px solid #b8c2d0;border-radius:50%;background:transparent}.lesson-outline-chapter-marker[data-state="generating"]{border-color:#6366f1;background:#6366f1;animation:lesson-pulse 1.4s ease-in-out infinite}.lesson-outline-chapter-marker[data-state="review"]{border-color:#d97706;background:#f59e0b}.lesson-outline-chapter-marker[data-state="confirmed"]{border-color:#16a34a;background:#22c55e}.lesson-outline-chapter-marker[data-state="failed"]{border-color:#dc2626;background:#ef4444}.lesson-outline-chapter-copy{min-width:0;display:grid;gap:2px}.lesson-outline-chapter-copy strong{overflow:hidden;color:#59677b;font-size:14px;font-weight:600;line-height:1.35;text-overflow:ellipsis;white-space:nowrap}.lesson-outline-chapter-copy small{color:#8a97aa;font-size:14px;line-height:1.3}.lesson-outline-chapter-button:hover strong{color:#334155}.lesson-outline-chapter-button.active .lesson-outline-chapter-marker{box-shadow:0 0 0 3px rgba(99,102,241,.12)}.lesson-outline-chapter-button.active strong{color:#373b71;font-weight:700}.lesson-outline-chapter-button.active small{color:#6366f1}.lesson-section-tabs{display:flex;min-width:0;overflow-x:auto;padding:0 18px;border-bottom:1px solid #e7ebf2;background:#fff;scrollbar-width:thin}.lesson-section-tabs button{min-height:56px;flex:0 0 auto;display:flex;align-items:center;gap:8px;padding:0 14px;border:0;color:#718096;background:transparent;cursor:pointer;white-space:nowrap}.lesson-section-tabs button>span{color:#94a3b8;font-size:14px;font-weight:750;font-variant-numeric:tabular-nums}.lesson-section-tabs button>strong{max-width:260px;overflow:hidden;font-size:14px;font-weight:600;text-overflow:ellipsis}.lesson-section-tabs button:hover{color:#475569}.lesson-section-tabs button.active{color:#3730a3;box-shadow:inset 0 -2px #5b57e8}.lesson-section-tabs button.active>span{color:#6366f1}.lesson-section-tabs button.active>strong{font-weight:700}.has-lesson-outline :deep(.lesson-document .document-title h3){overflow:visible;line-height:1.35;text-overflow:clip;white-space:normal}.has-lesson-outline :deep(.lesson-document .flow-table){overflow:auto}.has-lesson-outline :deep(.lesson-document .flow-row){min-width:800px}@keyframes lesson-pulse{50%{opacity:.42;transform:scale(.72)}}
.lesson-stage{padding:0;overflow:hidden}.lesson-navigator{min-height:54px;display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:center;gap:14px;padding:0 20px;border-bottom:1px solid #e7ebf2;background:#fbfcfe}.lesson-navigator>button{min-height:36px;display:flex;align-items:center;gap:5px;padding:0 11px;border:1px solid #d9dcfa;border-radius:8px;color:#4338ca;background:#f3f2ff;font-size:14px;font-weight:750;cursor:pointer;transition:color .16s ease,border-color .16s ease,background .16s ease,transform .16s ease}.lesson-navigator>button:hover:not(:disabled){transform:translateY(-1px);border-color:#aaa7f2;color:#3730a3;background:#eae8ff}.lesson-navigator>button:focus-visible{outline:3px solid rgba(91,87,232,.18);outline-offset:2px}.lesson-navigator>button:disabled{border-color:transparent;color:#94a3b8;background:transparent;opacity:.48;cursor:not-allowed}.lesson-selector{min-width:0;display:flex;align-items:center;justify-content:center;gap:0;padding:0;border:0}.lesson-selector>span{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}.lesson-selector select{width:min(100%,560px);min-height:36px;padding:0 34px 0 12px;border:0;border-radius:7px;color:#263147;background:transparent;font-size:14px;font-weight:750;text-align:center;box-shadow:none}.lesson-selector select:hover{background:#f3f5fa}.lesson-selector select:focus{background:#fff}.stage-form>.lesson-form-actions{justify-content:flex-end}.stage-next-bar{min-height:64px;display:flex;align-items:center;justify-content:space-between;padding:12px 28px;border-top:1px solid #e8ecf2;background:#fbfcfe}.ppt-entry{min-height:180px;display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:center;gap:16px;padding:36px 28px}.ppt-entry>svg{color:#5b57e8}.ppt-entry>div{min-width:0;display:grid;gap:5px}.ppt-entry strong{color:#1f2a40;font-size:15px}.ppt-entry span{color:#64748b;font-size:14px}.question-workbench-surface{max-width:860px;margin:0 auto;padding:0;border:0;border-radius:0;box-shadow:none}
.has-lesson-outline .lesson-workspace{grid-template-columns:190px minmax(0,1fr);gap:14px}.has-lesson-outline .lesson-workspace.is-outline-collapsed{grid-template-columns:minmax(0,1fr);gap:0}.lesson-outline{display:block;min-height:156px}.lesson-outline>nav{position:relative;padding:3px 0 3px 2px}.lesson-outline>nav::before{position:absolute;top:18px;bottom:18px;left:12px;width:1px;background:#dde3ec;content:""}.lesson-outline-chapter-button{position:relative;min-height:46px;grid-template-columns:20px minmax(0,1fr);gap:7px;padding:5px 7px 5px 2px;border-radius:8px}.lesson-outline-chapter-button:disabled{opacity:.48;cursor:not-allowed}.lesson-outline-chapter-marker{position:relative;z-index:1;width:6px;height:6px;border-color:#c4cedb;background:#f3f5f9}.lesson-outline-chapter-marker[data-state="generating"]{border-color:#6661dc;background:#6661dc}.lesson-outline-chapter-marker[data-state="review"]{border-color:#8884d8;background:#f3f2ff}.lesson-outline-chapter-marker[data-state="confirmed"]{border-color:#6661dc;background:#6661dc}.lesson-outline-chapter-marker[data-state="failed"]{border-color:#d75563;background:#d75563}.lesson-outline-chapter-copy{gap:1px}.lesson-outline-chapter-copy strong{color:#5e6b7e;font-size:14px;font-weight:620;line-height:1.4}.lesson-outline-chapter-copy small{color:#8a96a8;font-size:14px}.lesson-outline-chapter-copy small[data-state="review"]{color:#7773bd}.lesson-outline-chapter-copy small[data-state="failed"]{color:#b94b57}.lesson-outline-chapter-button:hover:not(:disabled){background:rgba(255,255,255,.52)}.lesson-outline-chapter-button.active{background:rgba(239,240,255,.62)}.lesson-outline-chapter-button.active .lesson-outline-chapter-marker{box-shadow:none}.lesson-outline-chapter-button.active strong{color:#34316f}.lesson-outline-chapter-button.active small{color:#6965b9}.lesson-outline-toggle{color:#596579!important;background:transparent!important;border-color:transparent!important;font-weight:650!important;box-shadow:none!important}.lesson-outline-toggle:hover{color:#3730a3!important;background:#f1f2f7!important}.lesson-section-tabs button:disabled{opacity:.5;cursor:not-allowed}
.teacher-workbench.is-ai-collaboration{grid-template-columns:minmax(0,1fr) 10px var(--ai-pane-width)}.lesson-navigator{grid-template-columns:auto auto minmax(0,1fr) auto;gap:8px}.is-ai-collaboration .lesson-navigator{grid-template-columns:auto minmax(0,1fr) auto}.lesson-selector select:disabled{color:#94a3b8;cursor:not-allowed}.lesson-outline-chapter-button:focus-visible,.lesson-section-tabs button:focus-visible{outline:2px solid #5b57e8;outline-offset:2px}
@media(max-width:1320px){.has-lesson-outline .lesson-workspace{grid-template-columns:184px minmax(0,1fr);gap:12px}.has-lesson-outline .lesson-workspace.is-outline-collapsed{grid-template-columns:minmax(0,1fr);gap:0}}
@media(max-width:760px){.lesson-navigator{gap:6px;padding-inline:10px}.lesson-navigator>button{font-size:0}.lesson-navigator>button svg{display:block}.lesson-selector select{padding-inline:8px;font-size:14px}.ppt-entry{grid-template-columns:auto minmax(0,1fr);padding:28px 18px}.ppt-entry .primary{grid-column:1/-1}}
.stage-rail nav button:disabled,.companion-entry>button:disabled{opacity:.45;cursor:not-allowed}.teacher-workbench.is-ai-collaboration{min-width:0;grid-template-columns:minmax(0,1fr) 10px var(--ai-pane-width);background:#eef1f6}.is-ai-collaboration>.workbench-center{min-width:0;overflow:auto}.is-ai-collaboration .has-lesson-outline .lesson-stage-content{min-width:0;overflow:hidden}.is-ai-collaboration .lesson-workspace,.is-ai-collaboration .lesson-stage,.is-ai-collaboration .outline-workspace{min-width:0;max-width:none}.is-ai-collaboration :deep(.lesson-document .flow-table){max-width:100%;overflow:auto}
@media(max-width:900px){.teacher-workbench.is-ai-collaboration{grid-template-columns:minmax(0,1fr) 8px 340px}.is-ai-collaboration>.workbench-center{padding:0}}
@media(prefers-reduced-motion:reduce){.has-lesson-outline .lesson-workspace{transition:none}.lesson-outline-chapter-marker[data-state="generating"]{animation:none}}

/* Lesson navigation keeps the document full width; the course outline appears only when requested. */
.shape-chapter-list li{grid-template-columns:minmax(0,1fr) auto;gap:16px}
.teacher-workbench{
  --teacher-component-surface:#fff;
  --teacher-component-tint:#f7f7ff;
  --teacher-component-active:#f0efff;
}
.lesson-navigator,.stage-next-bar{background:var(--teacher-component-tint)}
.lesson-selector select:hover,.lesson-title-trigger:hover,.lesson-title-trigger[aria-expanded="true"]{background:var(--teacher-component-tint)}
.lesson-outline-chapter-button:hover:not(:disabled){background:var(--teacher-component-tint)}
.lesson-outline-chapter-button.active{background:var(--teacher-component-active)}
.has-lesson-outline .lesson-workspace{display:block}
.has-lesson-outline .lesson-stage-content{overflow:visible}
.lesson-navigator{position:relative;z-index:5;grid-template-columns:auto minmax(0,1fr) auto;overflow:visible;border-radius:13px 13px 0 0}
.lesson-current-group{min-width:0;display:flex;align-items:center;justify-content:center;gap:8px}
.lesson-outline-control{position:relative;min-width:0;width:min(100%,560px);display:flex;align-items:center;justify-content:center}
.lesson-title-trigger{min-width:0;max-width:100%;min-height:38px;display:grid;grid-template-columns:minmax(0,auto) auto 16px;align-items:center;gap:9px;padding:0 10px 0 14px;border:0;border-radius:8px;color:#263147;background:transparent;cursor:pointer;transition:color .16s ease,background-color .16s ease}
.lesson-title-trigger:hover,.lesson-title-trigger[aria-expanded="true"]{color:#37348c;background:#f2f3fa}
.lesson-title-trigger:disabled{color:#94a3b8;cursor:not-allowed}
.lesson-title-trigger:focus-visible{outline:3px solid rgba(91,87,232,.16);outline-offset:2px}
.lesson-title-trigger strong{min-width:0;overflow:hidden;color:inherit;font-size:14px;font-weight:760;line-height:1.35;text-overflow:ellipsis;white-space:nowrap}
.lesson-title-trigger small{padding-left:9px;border-left:1px solid #dce1e9;color:#8a95a5;font-size:14px;font-weight:750;font-variant-numeric:tabular-nums}
.lesson-title-chevron{color:#8a95a5;transition:transform .18s cubic-bezier(.16,1,.3,1)}
.lesson-title-trigger[aria-expanded="true"] .lesson-title-chevron{transform:rotate(180deg)}
.lesson-outline-popover{position:absolute;z-index:30;top:calc(100% + 8px);left:50%;width:340px;max-width:calc(100vw - 48px);max-height:min(480px,calc(100vh - 190px));overflow:auto;padding:7px;border-radius:11px;background:#fff;box-shadow:0 16px 42px rgba(30,41,59,.16);transform:translateX(-50%);animation:lesson-outline-in .16s cubic-bezier(.16,1,.3,1)}
.lesson-outline-chapter-button{min-height:44px;display:grid;grid-template-columns:minmax(0,1fr) 18px;align-items:center;gap:8px;width:100%;padding:0 9px;border:0;border-radius:8px;color:#536176;background:transparent;text-align:left;cursor:pointer}
.lesson-outline-chapter-button:hover:not(:disabled){background:#f5f7fa}
.lesson-outline-chapter-button.active{color:#37348c;background:#f0f1ff}
.lesson-outline-chapter-button:disabled{opacity:.46;cursor:not-allowed}
.lesson-outline-chapter-button:focus-visible{outline:2px solid #5b57e8;outline-offset:-2px}
.lesson-outline-chapter-index{color:#9aa5b5;font-size:14px;font-weight:750;font-variant-numeric:tabular-nums}
.lesson-outline-chapter-button.active .lesson-outline-chapter-index{color:#6a66ce}
.lesson-outline-chapter-button strong{min-width:0;overflow:hidden;color:inherit;font-size:14px;font-weight:620;line-height:1.35;text-overflow:ellipsis;white-space:nowrap}
.lesson-outline-status{width:18px;height:18px;display:grid;place-items:center;justify-self:end;color:#a8b2c1}
.lesson-outline-status[data-state="generating"],.lesson-outline-status[data-state="confirmed"]{color:#625dd7}
.lesson-outline-status[data-state="failed"]{color:#c94c5a}
.lesson-outline-status i{width:7px;height:7px;border:1px solid #b8c2d0;border-radius:50%;background:#fff}
.lesson-outline-status[data-state="review"] i{border-color:#8b87dc;background:#8b87dc}
.is-ai-collaboration .lesson-outline-control{display:flex;width:min(100%,420px)}
.is-ai-collaboration .lesson-navigator{grid-template-columns:auto minmax(0,1fr) auto;border-radius:0}
@keyframes lesson-outline-in{from{opacity:.5;transform:translateX(-50%) translateY(-5px) scale(.985)}to{opacity:1;transform:translateX(-50%) translateY(0) scale(1)}}
@media(min-width:1051px){.teacher-workbench:not(.is-ai-collaboration){grid-template-columns:196px minmax(520px,1fr) 310px}}
.teacher-workbench.is-question-bank-workspace:not(.is-ai-collaboration){grid-template-columns:196px minmax(0,1fr)}
.is-ppt-stage>.workbench-center{padding:24px 30px 0}
.is-ppt-stage>.workbench-center>.center-heading,.is-ppt-stage .lesson-stage{width:100%;max-width:none}
.is-ppt-stage .lesson-stage{overflow:hidden;border-radius:14px}
.is-question-bank-workspace>.workbench-center{padding:24px 30px 0}
.is-question-bank-workspace>.workbench-center>.center-heading,.is-question-bank-workspace .lesson-stage,.is-question-bank-workspace .question-workbench-surface{width:100%;max-width:none}
.is-question-bank-workspace>.workbench-center.is-lesson-workspace>.lesson-stage{width:100%;max-width:none;margin-inline:0}
.is-question-bank-workspace>.workbench-center>.center-heading{margin-bottom:14px}
.is-question-bank-workspace .lesson-stage,.is-question-bank-workspace .lesson-stage-content{overflow:visible;padding:0;border:0;border-radius:0;background:transparent;box-shadow:none}
.is-question-bank-workspace .lesson-navigator{display:none}
@media(prefers-reduced-motion:reduce){.lesson-outline-popover{animation:none}}

.teacher-workbench{position:relative;background:transparent}
.teacher-workbench.is-ai-collaboration{box-sizing:border-box;grid-template-columns:minmax(0,1fr) 18px var(--ai-pane-width);padding:16px;background:transparent}
.is-ai-collaboration>.workbench-center{overflow:auto;background:transparent}
.is-ai-collaboration .outline-workspace,.is-ai-collaboration .lesson-stage,.ai-workspace-panel{border:1px solid #dfe5ee;border-radius:14px;background:#fff;box-shadow:0 8px 24px rgba(30,41,59,.045)}
.is-ai-collaboration>.workbench-center.is-lesson-workspace>.lesson-stage{width:100%;max-width:none;margin:0}
.is-ai-collaboration .lesson-stage{min-height:100%;overflow:hidden}
.ai-workspace-panel{min-height:0;overflow:hidden}
.context-pane{min-width:0;min-height:0;display:grid;grid-template-rows:54px minmax(0,1fr);overflow:hidden;border-left:1px solid #e4e9f1;background:#fbfcfe}
.context-pane-tabs{display:grid;grid-template-columns:1fr 1fr;align-items:stretch;padding:0 12px;border-bottom:1px solid #e7ebf2;background:#fff}
.context-pane-tabs button{position:relative;min-width:0;display:flex;align-items:center;justify-content:center;gap:6px;padding:0 8px;border:0;color:#758195;background:transparent;font-size:14px;font-weight:700;cursor:pointer}
.context-pane-tabs button::after{position:absolute;right:10px;bottom:-1px;left:10px;height:2px;border-radius:2px;background:transparent;content:""}
.context-pane-tabs button[aria-selected="true"]{color:#4338ca}
.context-pane-tabs button[aria-selected="true"]::after{background:#5b57e8}
.context-pane-tabs button:hover:not(:disabled){color:#4338ca;background:#fafaff}
.context-pane-tabs button:focus-visible{z-index:1;outline:2px solid #6366f1;outline-offset:-3px}
.context-pane-tabs button:disabled{color:#adb5c2;cursor:not-allowed}
.context-pane-tabs small{min-width:18px;height:18px;display:grid;place-items:center;border-radius:9px;color:#6965a9;background:#f0f0fb;font-size:14px}
.context-pane>.ai-workspace-panel{height:100%;border:0;border-radius:0;box-shadow:none}
.context-pane>.context-pane-references{height:100%;border-left:0}
.context-pane>:deep(.reference-tray__header){display:none}
.teacher-workbench.is-ai-collaboration .context-pane{border:1px solid #dfe5ee;border-radius:14px;background:#fff;box-shadow:0 8px 24px rgba(30,41,59,.045)}
.ai-workspace-resizer{z-index:6;display:grid;place-items:center;background:transparent}
.ai-workspace-resizer::after{inset-block:18px;background:#d9e0e9}
.ai-workspace-resizer>svg{position:relative;z-index:1;width:20px;height:32px;padding:8px 3px;border-radius:7px;color:#9aa6b6;background:#fff;box-shadow:0 0 0 1px #dfe4ec;opacity:0;transition:color .16s ease,opacity .16s ease,box-shadow .16s ease}
.ai-workspace-resizer:hover>svg,.ai-workspace-resizer:focus-visible>svg,.ai-workspace-resizer.is-resizing>svg{color:#5b57d9;box-shadow:0 0 0 1px #c8c6f1;opacity:1}
.ai-workspace-resizer:hover,.ai-workspace-resizer:focus-visible,.ai-workspace-resizer.is-resizing{background:transparent}
.ai-source-drawer{position:absolute;z-index:10;top:16px;right:calc(var(--ai-pane-width) + 34px);bottom:16px;width:min(340px,calc(100% - var(--ai-pane-width) - 108px));overflow:hidden;border:1px solid #dfe5ee;border-left:1px solid #dfe5ee;border-radius:14px;background:#fff;box-shadow:0 18px 50px rgba(30,41,59,.14);animation:ai-source-drawer-in .18s cubic-bezier(.16,1,.3,1)}
@keyframes ai-source-drawer-in{from{opacity:0;transform:translateX(8px)}to{opacity:1;transform:none}}
@media(max-width:900px){.teacher-workbench.is-ai-collaboration{grid-template-columns:minmax(0,1fr) 14px 340px;padding:10px}.ai-workspace-resizer::after{inset-block:12px}.ai-source-drawer{top:10px;right:364px;bottom:10px;width:min(320px,calc(100% - 442px))}}
@media(prefers-reduced-motion:reduce){.ai-workspace-resizer>svg{transition:none}.ai-source-drawer{animation:none}}

/* The lesson page reads as one workspace: identity, actions, then the document. */
.workbench-center.is-lesson-workspace:has(.lesson-navigator.has-document-actions) {
  padding-top: 24px;
}

.workbench-center.is-lesson-workspace .has-lesson-outline .lesson-stage-content {
  overflow: visible;
  border: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}

.lesson-navigator.has-document-actions {
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 16px;
  min-height: 64px;
  padding: 0 4px 12px;
  border: 0;
  border-radius: 0;
  background: transparent;
}

.lesson-heading-cluster {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 12px;
}

.lesson-navigator.has-document-actions .lesson-current-group {
  min-width: 0;
  justify-content: flex-start;
}

.lesson-navigator.has-document-actions .lesson-outline-control {
  width: min(100%, 720px);
  justify-content: flex-start;
}

.lesson-navigator.has-document-actions .lesson-title-trigger {
  padding-left: 0;
}

.lesson-navigator.has-document-actions .lesson-title-trigger strong {
  font-size: 16px;
  font-weight: 760;
}

.lesson-toolbar-status {
  flex: none;
  min-height: 30px;
  display: flex;
  align-items: center;
  gap: 5px;
  color: #687386;
  font-size: 14px;
  font-weight: 680;
  white-space: nowrap;
}

.lesson-toolbar-status svg {
  color: #667085;
}

.lesson-switch-actions {
  flex: none;
  display: flex;
  align-items: center;
  gap: 6px;
}

.lesson-switch-actions button {
  min-height: 34px;
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 0 10px;
  border: 1px solid #dfe3eb;
  border-radius: 7px;
  color: #59667a;
  background: #fff;
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
}

.lesson-switch-actions button:hover:not(:disabled) {
  border-color: #c9cfe0;
  color: #3730a3;
  background: #f7f7fb;
}

.lesson-switch-actions button:focus-visible {
  outline: 2px solid #5b57e8;
  outline-offset: 2px;
}

.lesson-switch-actions button:disabled {
  border-color: transparent;
  color: #a3acba;
  background: transparent;
  opacity: .55;
  cursor: not-allowed;
}

.lesson-generation-actions {
  flex-wrap: wrap;
}

.workbench-center.is-lesson-workspace .lesson-command-bar {
  width: calc(100% - 8px);
  margin: 0 4px 10px;
}

.workbench-center.is-lesson-workspace .lesson-section-tabs {
  border: 1px solid #e0e6ef;
  border-bottom-color: #e7ebf2;
  border-radius: 14px 14px 0 0;
  background: #fff;
}

.workbench-center.is-lesson-workspace :deep(.lesson-document) {
  overflow: hidden;
  border: 1px solid #e0e6ef;
  border-top: 0;
  border-radius: 0 0 14px 14px;
  background: #fff;
}

.workbench-center.is-lesson-workspace :deep(.script-document) {
  overflow: hidden;
  border: 1px solid #e0e6ef;
  border-radius: 14px;
  background: #fff;
}

.is-lesson-plan-stage > .workbench-center > .lesson-stage.has-lesson-outline {
  overflow: visible;
  border: 1px solid #dfe5ee;
  border-radius: 14px;
  background: #fff;
  box-shadow: 0 12px 34px rgba(30, 41, 59, .06);
}

.is-lesson-plan-stage .lesson-stage-content {
  container-type: inline-size;
  overflow: visible;
  border: 0;
  border-radius: 14px;
  background: #fff;
  box-shadow: none;
}

.is-lesson-plan-stage .lesson-navigator.has-document-actions {
  min-height: 108px;
  padding: 20px 30px;
  border-bottom: 1px solid #e7ebf2;
  border-radius: 14px 14px 0 0;
  background: #fff;
}

.is-lesson-plan-stage .lesson-navigator.has-document-actions .lesson-outline-control {
  width: 100%;
  max-width: 760px;
}

.is-lesson-plan-stage .lesson-navigator.has-document-actions .lesson-title-trigger {
  min-height: 48px;
  padding: 0 10px 0 0;
  text-align: left;
}

.is-lesson-plan-stage .lesson-navigator.has-document-actions .lesson-title-trigger strong {
  overflow: visible;
  font-size: 28px;
  font-weight: 760;
  letter-spacing: -.025em;
  line-height: 1.28;
  text-overflow: clip;
  white-space: normal;
}

.is-lesson-plan-stage .lesson-navigator.has-document-actions .lesson-title-trigger small,
.is-lesson-plan-stage .lesson-toolbar-status {
  font-size: 15px;
}

.is-lesson-plan-stage .lesson-switch-actions {
  gap: 8px;
}

.is-lesson-plan-stage .lesson-switch-actions button {
  min-width: 108px;
  min-height: 44px;
  justify-content: center;
  padding: 0 15px;
  font-size: 15px;
  font-weight: 680;
}

.is-lesson-plan-stage .lesson-command-bar {
  position: relative;
  top: auto;
  width: calc(100% - 48px);
  margin: 14px 24px 12px;
}

.is-lesson-plan-stage :deep(.arrangement-summary.has-sticky-actions .arrangement-toolbar),
.is-lesson-plan-stage :deep(.arrangement-summary.has-sticky-actions:is(.is-supporting, .is-generating)) {
  top: -24px;
}

.is-lesson-plan-stage :deep(.lesson-command-bar .teacher-document-command-bar__status),
.is-lesson-plan-stage :deep(.lesson-command-bar .teacher-document-command-bar button),
.is-lesson-plan-stage :deep(.lesson-command-bar .teacher-document-command-bar__actions button) {
  font-size: 15px;
}

.is-lesson-plan-stage :deep(.lesson-command-bar .teacher-document-command-bar button),
.is-lesson-plan-stage :deep(.lesson-command-bar .teacher-document-command-bar__actions button) {
  min-height: 38px;
}

.is-lesson-plan-stage :deep(.lesson-document) {
  border: 0;
  border-radius: 0 0 14px 14px;
}

@container (max-width: 760px) {
  .lesson-navigator.has-document-actions {
    grid-template-columns: minmax(0, 1fr);
    gap: 14px;
  }

  .lesson-heading-cluster {
    gap: 8px;
  }

  .is-lesson-plan-stage .lesson-navigator.has-document-actions {
    padding: 20px;
  }

  .is-lesson-plan-stage .lesson-title-trigger {
    grid-template-columns: minmax(0, 1fr) auto 16px;
    width: 100%;
  }

  .is-lesson-plan-stage .lesson-title-trigger strong {
    overflow: visible;
    white-space: normal;
  }

  .is-lesson-plan-stage .lesson-switch-actions {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    width: 100%;
  }

  .is-lesson-plan-stage .lesson-switch-actions button {
    width: 100%;
    min-width: 0;
    padding: 0 12px;
    font-size: 15px;
  }

  .lesson-toolbar-status > span {
    display: none;
  }
}
</style>
