<template>
  <section ref="documentRoot" class="lesson-document" :class="{ 'is-ai-candidate': pendingCandidate }">
    <header v-if="!externalToolbar" class="document-header">
      <div class="document-title">
        <h3><MathText :content="lesson.title" /></h3>
      </div>
      <div v-if="!pendingCandidate || !assistantOpen" class="document-actions">
        <template v-if="pendingCandidate">
          <button type="button" :disabled="aiBusy || requestBusy" @click="openInlineAi">
            <Sparkles :size="15" />{{ tr('courseWorkbench.aiCollaboration.iterateCandidate') }}
          </button>
          <button type="button" :disabled="aiBusy" @click="resolveAiCandidate(false)">
            <X :size="15" />{{ tr('courseWorkbench.lessonDocument.discardAi') }}
          </button>
          <button class="primary-action" type="button" :disabled="aiBusy" @click="resolveAiCandidate(true)">
            <LoaderCircle v-if="aiBusy" :size="15" class="spin" />
            <Check v-else :size="15" />
            {{ aiBusy ? tr('courseWorkbench.lessonDocument.applyingAi') : tr('courseWorkbench.lessonDocument.applyAi') }}
          </button>
        </template>
        <template v-else-if="editing">
          <button type="button" :disabled="saving" @click="cancelEditing">
            <X :size="15" />{{ tr('courseWorkbench.lessonDocument.cancel') }}
          </button>
          <button class="primary-action" type="button" :disabled="saving" @click="saveDraft">
            <LoaderCircle v-if="saving" :size="15" class="spin" />
            <Check v-else :size="15" />
            {{ saving ? tr('courseWorkbench.lessonDocument.saving') : tr('courseWorkbench.lessonDocument.finishEditing') }}
          </button>
        </template>
        <template v-else>
          <button type="button" :disabled="aiBusy || requestBusy" @click="openInlineAi">
            <Sparkles :size="15" />{{ tr('courseWorkbench.lessonDocument.aiImprove') }}
          </button>
          <button type="button" @click="beginEditing">
            <Pencil :size="15" />{{ tr('courseWorkbench.lessonDocument.edit') }}
          </button>
        </template>
      </div>
    </header>

    <div v-if="pendingCandidate && !inlineCandidateInPlace" class="candidate-canvas-notice" role="status">
      <div>
        <Sparkles :size="16" />
        <span>
          <strong>{{ tr('courseWorkbench.lessonDocument.candidateCanvasTitle') }}</strong>
          <small>{{ tr('courseWorkbench.aiCollaboration.inlineCandidateBoundary') }}</small>
        </span>
      </div>
      <nav :aria-label="tr('courseWorkbench.aiCollaboration.inlineCandidateActions')">
        <button type="button" :disabled="aiBusy || requestBusy" @click="openInlineAi">
          <Sparkles :size="14" />{{ tr('courseWorkbench.aiCollaboration.iterateCandidate') }}
        </button>
        <button type="button" :disabled="aiBusy || requestBusy" @click="resolveAiCandidate(false)">
          <X :size="14" />{{ tr('courseWorkbench.aiCollaboration.keepOriginal') }}
        </button>
        <button class="primary" type="button" :disabled="aiBusy || requestBusy" @click="resolveAiCandidate(true)">
          <LoaderCircle v-if="aiBusy || requestBusy" :size="14" class="spin" />
          <Check v-else :size="14" />{{ tr('courseWorkbench.aiCollaboration.applyCandidate') }}
        </button>
      </nav>
    </div>

    <AppErrorNotice v-if="documentError" :presentation="documentError" compact />

    <TextSelectionAiAction
      v-if="selectionAiEnabled"
      ref="inlineAiAction"
      :container="documentRoot"
      :disabled="editing"
      :busy="aiBusy || requestBusy"
      :label="tr('courseWorkbench.aiCollaboration.selectionModify')"
      :composer-title="tr('courseWorkbench.aiCollaboration.inlineComposerTitle')"
      :placeholder="tr('courseWorkbench.aiCollaboration.selectionPlaceholder')"
      :submit-label="tr('courseWorkbench.aiCollaboration.inlineGenerate')"
      :cancel-label="tr('common.cancel')"
      :working-label="tr('courseWorkbench.aiCollaboration.inlineWorking')"
      :selection-label="tr('courseWorkbench.aiCollaboration.inlineSelectionScope')"
      :block-label="tr('courseWorkbench.aiCollaboration.inlineBlockScope')"
      :document-label="tr('courseWorkbench.aiCollaboration.inlineDocumentScope')"
      :boundary-label="tr('courseWorkbench.aiCollaboration.inlineBoundary')"
      target-selector="[data-ai-field]"
      group-selector="[data-ai-inline-anchor]"
      :select-target-label="tr('courseWorkbench.aiCollaboration.selectTarget')"
      :candidate-pending="Boolean(pendingCandidate)"
      :candidate-title="tr('courseWorkbench.aiCollaboration.candidateReady')"
      :candidate-hint="tr('courseWorkbench.aiCollaboration.inlineCandidateBoundary')"
      :apply-label="tr('courseWorkbench.aiCollaboration.applyCandidate')"
      :discard-label="tr('courseWorkbench.aiCollaboration.keepOriginal')"
      :progress-label="inlineAiProgressLabel"
      :error-message="inlineAiErrorMessage"
      @invoke="requestInlineAiCandidate"
      @resolve="resolveInlineAiCandidate"
    />

    <article v-if="planSections.length" class="document-body">
      <nav v-if="planSections.length > 1" class="lesson-theme-nav" :aria-label="tr('courseWorkbench.lessonDocument.themeNavigation')">
        <button v-for="(section, index) in planSections" :key="section.node_id" type="button" :class="{ active: String(section.node_id || '') === selectedSectionId }" @click="activateSection(section)">
          <span>{{ String(index + 1).padStart(2, '0') }}</span><MathText :content="sectionTitle(section)" />
        </button>
      </nav>

      <section
        v-for="(section, sectionIndex) in planSections"
        :id="themeAnchor(section)"
        :key="section.node_id || sectionIndex"
        class="lesson-theme"
        :class="{ active: String(section.node_id || '') === selectedSectionId, 'is-headingless': !themeHeadingVisible(section) }"
        :data-ai-section-id="String(section.node_id || '')"
        @focusin="activateSection(section, false)"
      >
        <header v-if="themeHeadingVisible(section)" class="lesson-theme-heading">
          <div><span>{{ tr('courseWorkbench.lessonDocument.theme') }} {{ sectionIndex + 1 }}</span><h4><MathText :content="sectionTitle(section)" /></h4></div>
          <small>{{ sectionMinutes(section) }} {{ tr('courseWorkbench.minutes') }}</small>
        </header>
        <div v-if="String(section.node_id || '') === selectedSectionId" data-ai-document-anchor class="lesson-theme-ai-anchor" />

        <section class="document-section objective-section">
          <h4>{{ tr('courseWorkbench.lessonDocument.objectives') }}</h4>
          <div class="objective-grid" data-ai-inline-anchor>
            <div data-ai-field="knowledge_objectives" :data-ai-label="tr('courseWorkbench.lessonDocument.knowledgeObjective')" :class="{ 'ai-change-target': candidateChanged(section, 'knowledge_objectives') }"><i v-if="candidateChanged(section, 'knowledge_objectives')" class="ai-change-marker">{{ tr('courseWorkbench.lessonDocument.changeMarker') }}</i><h5>{{ tr('courseWorkbench.lessonDocument.knowledgeObjective') }}</h5><textarea v-if="editing" :value="listText(section.knowledge_objectives)" rows="3" @input="updateList(section, 'knowledge_objectives', $event)" /><ul v-else-if="sectionKnowledgeObjectives(section).length"><li v-for="(item, itemIndex) in sectionKnowledgeObjectives(section)" :key="`${itemIndex}-${item}`" data-ai-field="knowledge_objectives" :data-ai-item-id="String(itemIndex)" :data-ai-label="tr('courseWorkbench.lessonDocument.knowledgeObjective')" :class="{ 'ai-change-target': candidateListItemChanged(section, 'knowledge_objectives', itemIndex) }"><MathText :content="item" /></li></ul><p v-else>{{ emptyValue }}</p></div>
            <div data-ai-field="ability_objectives" :data-ai-label="tr('courseWorkbench.lessonDocument.abilityObjective')" :class="{ 'ai-change-target': candidateChanged(section, 'ability_objectives') }"><i v-if="candidateChanged(section, 'ability_objectives')" class="ai-change-marker">{{ tr('courseWorkbench.lessonDocument.changeMarker') }}</i><h5>{{ tr('courseWorkbench.lessonDocument.abilityObjective') }}</h5><textarea v-if="editing" :value="listText(section.ability_objectives)" rows="3" @input="updateList(section, 'ability_objectives', $event)" /><ul v-else-if="sectionAbilityObjectives(section).length"><li v-for="(item, itemIndex) in sectionAbilityObjectives(section)" :key="`${itemIndex}-${item}`" data-ai-field="ability_objectives" :data-ai-item-id="String(itemIndex)" :data-ai-label="tr('courseWorkbench.lessonDocument.abilityObjective')" :class="{ 'ai-change-target': candidateListItemChanged(section, 'ability_objectives', itemIndex) }"><MathText :content="item" /></li></ul><p v-else>{{ emptyValue }}</p></div>
            <div data-ai-field="education_objectives" :data-ai-label="tr('courseWorkbench.lessonDocument.educationObjective')" :class="{ 'ai-change-target': candidateChanged(section, 'education_objectives') }"><i v-if="candidateChanged(section, 'education_objectives')" class="ai-change-marker">{{ tr('courseWorkbench.lessonDocument.changeMarker') }}</i><h5>{{ tr('courseWorkbench.lessonDocument.educationObjective') }}</h5><textarea v-if="editing" :value="listText(section.education_objectives)" rows="3" @input="updateList(section, 'education_objectives', $event)" /><ul v-else-if="stringList(section.education_objectives).length"><li v-for="(item, itemIndex) in stringList(section.education_objectives)" :key="`${itemIndex}-${item}`" data-ai-field="education_objectives" :data-ai-item-id="String(itemIndex)" :data-ai-label="tr('courseWorkbench.lessonDocument.educationObjective')" :class="{ 'ai-change-target': candidateListItemChanged(section, 'education_objectives', itemIndex) }"><MathText :content="item" /></li></ul><p v-else>{{ emptyValue }}</p></div>
          </div>
        </section>

        <section v-if="editing || stringList(section.pre_study).length" class="document-section lesson-time-section" data-period="before" data-ai-field="pre_study" data-ai-inline-anchor :data-ai-label="tr('courseWorkbench.lessonDocument.preClassPreparation')" :class="{ 'ai-change-target': candidateChanged(section, 'pre_study') }">
          <div class="section-heading"><h4>{{ tr('courseWorkbench.lessonDocument.preClassPreparation') }}</h4><span>{{ tr('courseWorkbench.lessonDocument.outsideClassTime') }}</span></div>
          <textarea v-if="editing" :value="listText(section.pre_study)" rows="3" @input="updateList(section, 'pre_study', $event)" />
          <ul v-else><li v-for="(item, itemIndex) in stringList(section.pre_study)" :key="`${itemIndex}-${item}`" data-ai-field="pre_study" :data-ai-item-id="String(itemIndex)" :data-ai-label="tr('courseWorkbench.lessonDocument.preClassPreparation')" :class="{ 'ai-change-target': candidateListItemChanged(section, 'pre_study', itemIndex) }"><MathText :content="item" /></li></ul>
        </section>

        <section class="document-section">
          <h4>{{ tr('courseWorkbench.lessonDocument.keyAndDifficult') }}</h4>
          <div class="focus-grid" data-ai-inline-anchor>
            <div data-ai-field="key_points" :data-ai-label="tr('courseWorkbench.lessonDocument.keyPoints')" :class="{ 'ai-change-target': candidateChanged(section, 'key_points') }"><i v-if="candidateChanged(section, 'key_points')" class="ai-change-marker">{{ tr('courseWorkbench.lessonDocument.changeMarker') }}</i><h4>{{ tr('courseWorkbench.lessonDocument.keyPoints') }}</h4><textarea v-if="editing" :value="listText(section.key_points)" rows="3" @input="updateList(section, 'key_points', $event)" /><ul v-else-if="stringList(section.key_points).length"><li v-for="(item, itemIndex) in stringList(section.key_points)" :key="`${itemIndex}-${item}`" data-ai-field="key_points" :data-ai-item-id="String(itemIndex)" :data-ai-label="tr('courseWorkbench.lessonDocument.keyPoints')" :class="{ 'ai-change-target': candidateListItemChanged(section, 'key_points', itemIndex) }"><MathText :content="item" /></li></ul><p v-else>{{ emptyValue }}</p></div>
            <div data-ai-field="key_difficulties" :data-ai-label="tr('courseWorkbench.lessonDocument.difficulties')" :class="{ 'ai-change-target': candidateChanged(section, 'key_difficulties') }"><i v-if="candidateChanged(section, 'key_difficulties')" class="ai-change-marker">{{ tr('courseWorkbench.lessonDocument.changeMarker') }}</i><h4>{{ tr('courseWorkbench.lessonDocument.difficulties') }}</h4><textarea v-if="editing" :value="listText(section.key_difficulties)" rows="3" @input="updateList(section, 'key_difficulties', $event)" /><ul v-else-if="stringList(section.key_difficulties).length"><li v-for="(item, itemIndex) in stringList(section.key_difficulties)" :key="`${itemIndex}-${item}`" data-ai-field="key_difficulties" :data-ai-item-id="String(itemIndex)" :data-ai-label="tr('courseWorkbench.lessonDocument.difficulties')" :class="{ 'ai-change-target': candidateListItemChanged(section, 'key_difficulties', itemIndex) }"><MathText :content="item" /></li></ul><p v-else>{{ emptyValue }}</p></div>
          </div>
        </section>

        <section class="document-section flow-section">
          <div class="section-heading"><h4>{{ tr('courseWorkbench.lessonDocument.classroomProcess') }}</h4><span>{{ sectionMinutes(section) }} {{ tr('courseWorkbench.minutes') }}</span></div>
          <div class="teaching-block-list">
            <article v-for="(module, index) in sectionModules(section)" :key="module.arrangement_block_id || module.module_id || index" class="teaching-block" data-ai-inline-anchor :class="{ 'is-overtime': isOvertimeModule(section, module, index) }">
              <header><strong><MathText :content="moduleTitle(module, index)" /></strong><label class="block-duration" data-ai-field="planned_minutes" :data-ai-item-id="moduleTargetId(module, index)" :data-ai-label="tr('courseWorkbench.lessonDocument.duration')" :class="{ 'ai-change-target': candidateModuleChanged(section, module, 'planned_minutes') }"><span>{{ tr('courseWorkbench.lessonDocument.duration') }}</span><input v-if="editing" v-model.number="module.planned_minutes" type="number" min="0" max="300" @input="recordEditSnapshot" /><b v-else>{{ normalizedMinutes(module.planned_minutes) || emptyValue }} {{ tr('courseWorkbench.minutes') }}</b></label></header>
              <p v-if="isOvertimeModule(section, module, index)" class="overtime-warning"><TriangleAlert :size="13" />{{ tr('courseWorkbench.lessonDocument.overtimeBlock') }}</p>
              <div v-if="editing" class="block-fields block-fields--primary">
                <label><span>{{ tr('courseWorkbench.lessonDocument.blockGoalContent') }}</span><textarea v-if="editing" v-model="module.teaching_purpose" rows="3" @input="recordEditSnapshot" /><MathText v-else tag="p" :content="module.teaching_purpose || emptyValue" /></label>
                <label><span>{{ tr('courseWorkbench.lessonDocument.resourcesTools') }}</span><textarea v-if="editing" :value="listText(resourceItems(section, module))" rows="3" @input="updateResourcesAndTools(module, $event)" /><ul v-else-if="resourceItems(section, module).length"><li v-for="item in resourceItems(section, module)" :key="item"><MathText :content="item" /></li></ul><p v-else>{{ emptyValue }}</p></label>
                <label><span>{{ tr('courseWorkbench.lessonDocument.teacherActivity') }}</span><textarea v-if="editing" v-model="module.teacher_activity" rows="3" @input="recordEditSnapshot" /><MathText v-else tag="p" :content="module.teacher_activity || module.teaching_guidance || emptyValue" /></label>
                <label><span>{{ tr('courseWorkbench.lessonDocument.studentActivity') }}</span><textarea v-if="editing" v-model="module.student_activity" rows="3" @input="recordEditSnapshot" /><MathText v-else tag="p" :content="module.student_activity || emptyValue" /></label>
                <label><span>{{ tr('courseWorkbench.lessonDocument.expectedOutput') }}</span><textarea v-if="editing" v-model="module.expected_output" rows="3" @input="recordEditSnapshot" /><MathText v-else tag="p" :content="module.expected_output || emptyValue" /></label>
                <label><span>{{ tr('courseWorkbench.lessonDocument.attainmentCheck') }}</span><textarea v-if="editing" v-model="module.check_method" rows="3" @input="recordEditSnapshot" /><MathText v-else tag="p" :content="module.check_method || emptyValue" /></label>
              </div>
              <div v-else class="lesson-block-summary" data-ai-inline-anchor>
                <section data-ai-field="teaching_purpose" :data-ai-item-id="moduleTargetId(module, index)" :data-ai-label="tr('courseWorkbench.lessonDocument.blockGoalContent')" :class="{ 'ai-change-target': candidateModuleChanged(section, module, 'teaching_purpose') }">
                  <i v-if="candidateModuleChanged(section, module, 'teaching_purpose')" class="ai-change-marker">{{ tr('courseWorkbench.lessonDocument.changeMarker') }}</i>
                  <strong>{{ tr('courseWorkbench.lessonDocument.blockGoalContent') }}</strong>
                  <MathText tag="p" :content="module.teaching_purpose || module.teaching_guidance || emptyValue" />
                </section>
                <section v-if="resourceItems(section, module).length" data-ai-field="resource_refs" :data-ai-item-id="moduleTargetId(module, index)" :data-ai-label="tr('courseWorkbench.lessonDocument.resourcesTools')" :class="{ 'ai-change-target': candidateModuleChanged(section, module, 'resource_refs') || candidateModuleChanged(section, module, 'tools') }">
                  <i v-if="candidateModuleChanged(section, module, 'resource_refs') || candidateModuleChanged(section, module, 'tools')" class="ai-change-marker">{{ tr('courseWorkbench.lessonDocument.changeMarker') }}</i>
                  <strong>{{ tr('courseWorkbench.lessonDocument.resourcesTools') }}</strong>
                  <ul><li v-for="item in resourceItems(section, module)" :key="item"><MathText :content="item" /></li></ul>
                </section>
                <section>
                  <strong>{{ tr('courseWorkbench.lessonDocument.classroomActivity') }}</strong>
                  <ul v-if="classroomActivityItems(module).length">
                    <li v-if="module.teacher_activity" data-ai-field="teacher_activity" :data-ai-item-id="moduleTargetId(module, index)" :data-ai-label="tr('courseWorkbench.lessonDocument.teacherActivity')" :class="{ 'ai-change-target': candidateModuleChanged(section, module, 'teacher_activity') }"><MathText :content="`${tr('courseWorkbench.lessonDocument.teacherActivity')}：${module.teacher_activity}`" /></li>
                    <li v-if="module.student_activity" data-ai-field="student_activity" :data-ai-item-id="moduleTargetId(module, index)" :data-ai-label="tr('courseWorkbench.lessonDocument.studentActivity')" :class="{ 'ai-change-target': candidateModuleChanged(section, module, 'student_activity') }"><MathText :content="`${tr('courseWorkbench.lessonDocument.studentActivity')}：${module.student_activity}`" /></li>
                  </ul>
                  <p v-else>{{ emptyValue }}</p>
                </section>
                <section>
                  <strong>{{ tr('courseWorkbench.lessonDocument.attainmentJudgement') }}</strong>
                  <ul v-if="attainmentJudgementItems(module).length">
                    <li v-if="module.expected_output" data-ai-field="expected_output" :data-ai-item-id="moduleTargetId(module, index)" :data-ai-label="tr('courseWorkbench.lessonDocument.expectedOutput')" :class="{ 'ai-change-target': candidateModuleChanged(section, module, 'expected_output') }"><MathText :content="`${tr('courseWorkbench.lessonDocument.expectedOutput')}：${module.expected_output}`" /></li>
                    <li v-if="module.check_method" data-ai-field="check_method" :data-ai-item-id="moduleTargetId(module, index)" :data-ai-label="tr('courseWorkbench.lessonDocument.attainmentCheck')" :class="{ 'ai-change-target': candidateModuleChanged(section, module, 'check_method') }"><MathText :content="`${tr('courseWorkbench.lessonDocument.attainmentCheck')}：${module.check_method}`" /></li>
                  </ul>
                  <p v-else>{{ emptyValue }}</p>
                </section>
              </div>
              <details v-if="editing" class="block-contingency">
                <summary>{{ tr('courseWorkbench.lessonDocument.implementationPlan') }}</summary>
                <div class="block-fields">
                  <label><span>{{ tr('courseWorkbench.lessonDocument.feedbackAdjustment') }}</span><textarea v-if="editing" v-model="module.feedback_strategy" rows="3" @input="recordEditSnapshot" /><MathText v-else tag="p" :content="module.feedback_strategy || emptyValue" /></label>
                  <label><span>{{ tr('courseWorkbench.lessonDocument.adaptationOptions') }}</span><textarea v-if="editing" :value="listText(module.adaptation_options)" rows="4" @input="updateList(module, 'adaptation_options', $event)" /><ul v-else-if="stringList(module.adaptation_options).length"><li v-for="item in stringList(module.adaptation_options)" :key="item"><MathText :content="item" /></li></ul><p v-else>{{ emptyValue }}</p></label>
                  <label><span>{{ tr('courseWorkbench.lessonDocument.accessSupport') }}</span><textarea v-if="editing" v-model="module.access_support" rows="3" @input="recordEditSnapshot" /><MathText v-else tag="p" :content="module.access_support || emptyValue" /></label>
                  <label><span>{{ tr('courseWorkbench.lessonDocument.grouping') }}</span><textarea v-if="editing" v-model="module.grouping" rows="3" @input="recordEditSnapshot" /><MathText v-else tag="p" :content="module.grouping || emptyValue" /></label>
                  <label><span>{{ tr('courseWorkbench.lessonDocument.transition') }}</span><textarea v-if="editing" v-model="module.transition" rows="3" @input="recordEditSnapshot" /><MathText v-else tag="p" :content="module.transition || emptyValue" /></label>
                  <label><span>{{ tr('courseWorkbench.lessonDocument.handoutPptMapping') }}</span><textarea v-if="editing" v-model="module.handout_ppt_mapping" rows="3" @input="recordEditSnapshot" /><MathText v-else tag="p" :content="module.handout_ppt_mapping || emptyValue" /></label>
                </div>
              </details>
            </article>
            <div v-if="!sectionModules(section).length" class="flow-empty">{{ tr('courseWorkbench.lessonPlanPreparing') }}</div>
          </div>
        </section>

        <section class="document-section" data-ai-field="class_summary" data-ai-inline-anchor :data-ai-label="tr('courseWorkbench.lessonDocument.classSummary')" :class="{ 'ai-change-target': candidateFieldChanged(section, 'class_summary') }"><i v-if="candidateFieldChanged(section, 'class_summary')" class="ai-change-marker">{{ tr('courseWorkbench.lessonDocument.changeMarker') }}</i><h4>{{ tr('courseWorkbench.lessonDocument.classSummary') }}</h4><textarea v-if="editing" :value="listText(section.class_summary)" rows="4" @input="updateList(section, 'class_summary', $event)" /><ul v-else-if="sectionSummaryItems(section).length"><li v-for="(item, itemIndex) in sectionSummaryItems(section)" :key="`${itemIndex}-${item}`" data-ai-field="class_summary" :data-ai-item-id="String(itemIndex)" :data-ai-label="tr('courseWorkbench.lessonDocument.classSummary')" :class="{ 'ai-change-target': candidateListItemChanged(section, 'class_summary', itemIndex) }"><MathText :content="item" /></li></ul><p v-else>{{ emptyValue }}</p></section>

        <section class="document-section lesson-time-section" data-period="after" data-ai-field="homework" data-ai-inline-anchor :data-ai-label="tr('courseWorkbench.lessonDocument.homework')" :class="{ 'ai-change-target': candidateFieldChanged(section, 'homework') }">
          <div class="section-heading"><h4>{{ tr('courseWorkbench.lessonDocument.homework') }}</h4><span>{{ tr('courseWorkbench.lessonDocument.afterClassTime') }}</span></div>
          <textarea v-if="editing" :value="listText(section.homework)" rows="4" @input="updateList(section, 'homework', $event)" /><ol v-else-if="stringList(section.homework).length"><li v-for="(item, itemIndex) in stringList(section.homework)" :key="`${itemIndex}-${item}`" data-ai-field="homework" :data-ai-item-id="String(itemIndex)" :data-ai-label="tr('courseWorkbench.lessonDocument.homework')" :class="{ 'ai-change-target': candidateListItemChanged(section, 'homework', itemIndex) }"><MathText :content="item" /></li></ol><p v-else>{{ emptyValue }}</p>
          <div class="assignment-contract" data-ai-inline-anchor>
            <label data-ai-field="homework_submission" :data-ai-label="tr('courseWorkbench.lessonDocument.submission')" :class="{ 'ai-change-target': candidateChanged(section, 'homework_submission') }"><span>{{ tr('courseWorkbench.lessonDocument.submission') }}</span><input v-if="editing" v-model="section.homework_submission" :placeholder="tr('courseWorkbench.lessonDocument.submissionPending')" @input="recordEditSnapshot" /><MathText v-else tag="p" :content="section.homework_submission || tr('courseWorkbench.lessonDocument.submissionPending')" /></label>
            <label data-ai-field="homework_evaluation" :data-ai-label="tr('courseWorkbench.lessonDocument.evaluation')" :class="{ 'ai-change-target': candidateChanged(section, 'homework_evaluation') }"><span>{{ tr('courseWorkbench.lessonDocument.evaluation') }}</span><input v-if="editing" v-model="section.homework_evaluation" @input="recordEditSnapshot" /><MathText v-else tag="p" :content="section.homework_evaluation || emptyValue" /></label>
            <label data-ai-field="next_lesson_connection" :data-ai-label="tr('courseWorkbench.lessonDocument.nextLessonConnection')" :class="{ 'ai-change-target': candidateChanged(section, 'next_lesson_connection') }"><span>{{ tr('courseWorkbench.lessonDocument.nextLessonConnection') }}</span><input v-if="editing" v-model="section.next_lesson_connection" @input="recordEditSnapshot" /><MathText v-else tag="p" :content="section.next_lesson_connection || emptyValue" /></label>
          </div>
        </section>

        <section class="document-section materials-record"><h4>{{ tr('courseWorkbench.lessonDocument.materialsAndRecords') }}</h4><div class="closing-grid" data-ai-inline-anchor><div data-ai-field="resource_refs" :data-ai-label="tr('courseWorkbench.lessonDocument.extensionReading')" :class="{ 'ai-change-target': candidateFieldChanged(section, 'resource_refs') }"><i v-if="candidateFieldChanged(section, 'resource_refs')" class="ai-change-marker">{{ tr('courseWorkbench.lessonDocument.changeMarker') }}</i><h4>{{ tr('courseWorkbench.lessonDocument.extensionReading') }}</h4><textarea v-if="editing" :value="listText(section.resource_refs)" rows="4" @input="updateList(section, 'resource_refs', $event)" /><ul v-else-if="stringList(section.resource_refs).length"><li v-for="(item, itemIndex) in stringList(section.resource_refs)" :key="`${itemIndex}-${item}`" data-ai-field="resource_refs" :data-ai-item-id="String(itemIndex)" :data-ai-label="tr('courseWorkbench.lessonDocument.extensionReading')" :class="{ 'ai-change-target': candidateListItemChanged(section, 'resource_refs', itemIndex) }"><MathText :content="item" /></li></ul><p v-else>{{ emptyValue }}</p></div><div><h4>{{ tr('courseWorkbench.lessonDocument.activityPhotos') }}</h4><p>{{ tr('courseWorkbench.lessonDocument.activityPhotosPending') }}</p></div></div></section>

        <section class="document-section" data-ai-field="teaching_notes" data-ai-inline-anchor :data-ai-label="tr('courseWorkbench.lessonDocument.notes')" :class="{ 'ai-change-target': candidateFieldChanged(section, 'teaching_notes') }"><i v-if="candidateFieldChanged(section, 'teaching_notes')" class="ai-change-marker">{{ tr('courseWorkbench.lessonDocument.changeMarker') }}</i><h4>{{ tr('courseWorkbench.lessonDocument.notes') }}</h4><textarea v-if="editing" :value="listText(section.teaching_notes)" rows="4" @input="updateList(section, 'teaching_notes', $event)" /><ul v-else-if="stringList(section.teaching_notes).length"><li v-for="(item, itemIndex) in stringList(section.teaching_notes)" :key="`${itemIndex}-${item}`" data-ai-field="teaching_notes" :data-ai-item-id="String(itemIndex)" :data-ai-label="tr('courseWorkbench.lessonDocument.notes')" :class="{ 'ai-change-target': candidateListItemChanged(section, 'teaching_notes', itemIndex) }"><MathText :content="item" /></li></ul><p v-else>{{ emptyValue }}</p></section>
      </section>
    </article>

    <div v-else class="document-empty">{{ tr('courseWorkbench.lessonPlanPreparing') }}</div>

  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Check, LoaderCircle, Pencil, Sparkles, TriangleAlert, X } from 'lucide-vue-next'
import AppErrorNotice from './AppErrorNotice.vue'
import MathText from './MathText.vue'
import TextSelectionAiAction, { type TeacherInlineAiRequest, type TeacherInlineAiTarget } from './TextSelectionAiAction.vue'
import { useDocumentEditHistory } from '../composables/useDocumentEditHistory'
import { t } from '../shared/i18n'
import {
  useTeacherLessonAuthoringStore,
  type TeacherLessonPlanCandidate,
  type TeacherLessonProjection,
} from '../stores/teacherLessonAuthoring'
import { toAppError } from '../utils/app-error'
import type { GenerationProgress } from '../shared/generation-stream'

const props = withDefaults(defineProps<{
  courseId: string
  courseTitle?: string
  lesson: TeacherLessonProjection
  externalError?: string
  assistantOpen?: boolean
  activeSectionId?: string
  materialAssetIds?: string[]
  externalToolbar?: boolean
  selectionAiEnabled?: boolean
  requestBusy?: boolean
}>(), {
  assistantOpen: false,
  externalError: '',
  activeSectionId: '',
  materialAssetIds: () => [],
  externalToolbar: false,
  selectionAiEnabled: true,
  requestBusy: false,
  courseTitle: '',
})

const emit = defineEmits<{
  (event: 'saved'): void
  (event: 'open-ai'): void
  (event: 'open-ai-selection', value: TeacherInlineAiRequest): void
  (event: 'ai-candidate-change', value: TeacherLessonPlanCandidate | null): void
  (event: 'ai-busy-change', value: boolean): void
  (event: 'ai-resolving', value: { accept: boolean }): void
  (event: 'ai-resolved', value: { accept: boolean }): void
  (event: 'ai-error', value: string): void
  (event: 'update:activeSectionId', value: string): void
}>()

const lessonStore = useTeacherLessonAuthoringStore()
const editing = ref(false)
const saving = ref(false)
const inlineAiAction = ref<{ openForDocument: (text?: string) => void } | null>(null)
const saveError = ref<unknown>(null)
const draftPlan = ref<Record<string, any> | null>(null)
const localSectionId = ref('')
const aiBusy = ref(false)
const aiError = ref<unknown>(null)
const pendingCandidate = ref<TeacherLessonPlanCandidate | null>(null)
const inlineCandidateInPlace = ref(false)
const inlineAiProgress = ref<GenerationProgress | null>(null)
const documentRoot = ref<HTMLElement | null>(null)
const editHistory = useDocumentEditHistory<Record<string, any>>(snapshot => {
  draftPlan.value = clonePlan(snapshot)
})

const documentError = computed(() => {
  if (saveError.value) return toAppError(saveError.value, {
    title: tr('courseWorkbench.lessonDocument.saveFailed').replace(/，?请重试。?$/, ''),
    fallback: tr('courseWorkbench.lessonDocument.saveFailed'),
  })
  if (aiError.value) return toAppError(aiError.value, {
    title: tr('courseWorkbench.lessonDocument.aiFailed').replace(/，?请重试。?$/, ''),
    fallback: tr('courseWorkbench.lessonDocument.aiFailed'),
  })
  if (props.externalError) return toAppError(props.externalError, {
    title: tr('courseWorkbench.lessonDocument.operationFailed'),
    fallback: props.externalError,
  })
  return null
})

const fallbackMessages: Record<string, string> = {
  'courseWorkbench.lessonDocument.edit': '编辑教案',
  'courseWorkbench.lessonDocument.editing': '编辑中',
  'courseWorkbench.lessonDocument.cancel': '取消',
  'courseWorkbench.lessonDocument.finishEditing': '完成编辑',
  'courseWorkbench.lessonDocument.saving': '正在保存…',
  'courseWorkbench.lessonDocument.saveFailed': '教案保存失败，请重试。',
  'courseWorkbench.lessonDocument.operationFailed': '教案操作失败',
  'courseWorkbench.lessonDocument.aiImprove': 'AI 修改',
  'courseWorkbench.lessonDocument.aiCandidate': 'AI 方案',
  'courseWorkbench.lessonDocument.discardAi': '放弃',
  'courseWorkbench.lessonDocument.applyAi': '采用',
  'courseWorkbench.lessonDocument.applyingAi': '正在采用…',
  'courseWorkbench.lessonDocument.aiFailed': 'AI 优化失败，请重试。',
  'courseWorkbench.lessonDocument.candidateCanvasTitle': 'AI 候选已嵌入教案正文',
  'courseWorkbench.lessonDocument.changeMarker': 'AI 修改',
  'courseWorkbench.aiCollaboration.selectionModify': 'AI 修改',
  'courseWorkbench.aiCollaboration.inlineComposerTitle': '告诉 AI 怎么改',
  'courseWorkbench.aiCollaboration.inlineGenerate': '生成修改',
  'courseWorkbench.aiCollaboration.inlineWorking': '正在生成候选…',
  'courseWorkbench.aiCollaboration.inlineElapsed': '已等待 {seconds} 秒',
  'courseWorkbench.aiCollaboration.candidateReady': '修改候选已生成',
  'courseWorkbench.aiCollaboration.inlineSelectionScope': '修改选中内容',
  'courseWorkbench.aiCollaboration.inlineBlockScope': '修改当前段落',
  'courseWorkbench.aiCollaboration.selectTarget': '选择要修改的内容',
  'courseWorkbench.aiCollaboration.inlineDocumentScope': '修改当前教案',
  'courseWorkbench.aiCollaboration.inlineBoundary': 'AI 只生成候选，采用后才会写入正式教案。',
  'courseWorkbench.aiCollaboration.inlineCandidateBoundary': '原文仍然保留，只有采用后候选才会写入正式教案。',
  'courseWorkbench.aiCollaboration.inlineCandidateActions': 'AI 候选操作',
  'courseWorkbench.aiCollaboration.iterateCandidate': '继续调整',
  'courseWorkbench.aiCollaboration.keepOriginal': '保留原文',
  'courseWorkbench.aiCollaboration.applyCandidate': '采用修改',
  'courseWorkbench.lessonDocument.objective': '教学目标',
  'courseWorkbench.lessonDocument.courseName': '课程名称',
  'courseWorkbench.lessonDocument.lessonName': '课次',
  'courseWorkbench.lessonDocument.objectives': '教学目标',
  'courseWorkbench.lessonDocument.knowledgeObjective': '知识目标',
  'courseWorkbench.lessonDocument.abilityObjective': '能力目标',
  'courseWorkbench.lessonDocument.educationObjective': '育人目标',
  'courseWorkbench.lessonDocument.preClassPreparation': '课前准备（按需）',
  'courseWorkbench.lessonDocument.outsideClassTime': '课前，不计课堂时长',
  'courseWorkbench.lessonDocument.afterClassTime': '课后完成',
  'courseWorkbench.lessonDocument.keyAndDifficult': '教学重点与难点',
  'courseWorkbench.lessonDocument.classroomProcess': '课堂教学过程',
  'courseWorkbench.lessonDocument.classSummary': '课程总结',
  'courseWorkbench.lessonDocument.extensionLearning': '拓展学习',
  'courseWorkbench.lessonDocument.activityPhotos': '教学活动照片',
  'courseWorkbench.lessonDocument.activityPhotosPending': '待教师课后补充，系统不编造照片。',
  'courseWorkbench.lessonDocument.keyPoints': '教学重点',
  'courseWorkbench.lessonDocument.difficulties': '教学难点',
  'courseWorkbench.lessonDocument.flow': '教学流程',
  'courseWorkbench.lessonDocument.duration': '时间',
  'courseWorkbench.lessonDocument.phase': '教学环节',
  'courseWorkbench.lessonDocument.phasePurpose': '环节目的',
  'courseWorkbench.lessonDocument.phaseFallback': '环节 {count}',
  'courseWorkbench.lessonDocument.teacherActivity': '教师活动',
  'courseWorkbench.lessonDocument.studentActivity': '学生活动',
  'courseWorkbench.lessonDocument.check': '检查与产出',
  'courseWorkbench.lessonDocument.blockGoalContent': '本块目标与内容',
  'courseWorkbench.lessonDocument.expectedOutput': '课堂产出',
  'courseWorkbench.lessonDocument.attainmentCheck': '达成检查',
  'courseWorkbench.lessonDocument.classroomActivity': '课堂活动',
  'courseWorkbench.lessonDocument.attainmentJudgement': '达成判断',
  'courseWorkbench.lessonDocument.feedbackAdjustment': '反馈与调整',
  'courseWorkbench.lessonDocument.adaptationOptions': '不同达成状态下的处理',
  'courseWorkbench.lessonDocument.resourcesTools': '资料与工具',
  'courseWorkbench.lessonDocument.implementationPlan': '实施预案',
  'courseWorkbench.lessonDocument.accessSupport': '进入支持',
  'courseWorkbench.lessonDocument.grouping': '分组方式',
  'courseWorkbench.lessonDocument.transition': '与前后教学块的衔接',
  'courseWorkbench.lessonDocument.handoutPptMapping': '讲义与 PPT 对应关系',
  'courseWorkbench.lessonDocument.materialsAndRecords': '教学资料与活动记录',
  'courseWorkbench.lessonDocument.extensionReading': '拓展阅读',
  'courseWorkbench.lessonDocument.homework': '课后作业',
  'courseWorkbench.lessonDocument.submission': '提交方式',
  'courseWorkbench.lessonDocument.submissionPending': '待教师确认提交渠道与截止时间',
  'courseWorkbench.lessonDocument.evaluation': '评价方式',
  'courseWorkbench.lessonDocument.nextLessonConnection': '与下一讲衔接',
  'courseWorkbench.lessonDocument.overtimeBlock': '从本教学块开始超出本讲课堂时长，请调整分钟数。',
  'courseWorkbench.lessonDocument.themeNavigation': '讲内主题目录',
  'courseWorkbench.lessonDocument.theme': '内容主题',
  'courseWorkbench.lessonDocument.notes': '教学备注',
  'courseWorkbench.lessonDocument.empty': '-',
  'courseWorkbench.lessonPlanPreparing': '教案内容正在整理，请稍后刷新。',
  'courseWorkbench.lessonSection': '本讲教案',
  'courseWorkbench.minutes': '分钟',
  'courseWorkbench.lessonModules.goal': '教学目标',
  'courseWorkbench.lessonModules.explanation': '核心讲解',
  'courseWorkbench.lessonModules.activity': '课堂活动',
  'courseWorkbench.lessonModules.example': '案例示范',
  'courseWorkbench.lessonModules.practice': '练习反馈',
  'courseWorkbench.lessonModules.feedback': '检查反馈',
  'courseWorkbench.lessonModules.concept': '概念梳理',
  'courseWorkbench.lessonModules.comparison': '对比辨析',
  'courseWorkbench.lessonModules.application': '迁移应用',
  'courseWorkbench.lessonModules.summary': '课堂小结',
  'courseWorkbench.lessonModules.transfer': '总结迁移',
  'courseWorkbench.lessonModules.assessment': '学习检查',
}

function tr(key: string): string {
  return t(key, fallbackMessages[key] || key)
}

const workingRevision = computed(() => props.lesson.plan.revisions.find(
  item => item.revision_id === props.lesson.plan.working_revision_id,
))
const currentPlan = computed(() => draftPlan.value || pendingCandidate.value?.plan || workingRevision.value?.plan || {})
const planSections = computed<any[]>(() => Array.isArray(currentPlan.value.sections) ? currentPlan.value.sections : [])
const selectedSectionId = computed({
  get: () => String(props.activeSectionId || localSectionId.value),
  set: (value: string) => {
    localSectionId.value = value
    emit('update:activeSectionId', value)
  },
})
const basePlanSections = computed<any[]>(() => Array.isArray(workingRevision.value?.plan?.sections)
  ? workingRevision.value!.plan.sections
  : [])
const emptyValue = computed(() => tr('courseWorkbench.lessonDocument.empty'))
const inlineAiErrorMessage = computed(() => aiError.value ? documentError.value?.summary || tr('courseWorkbench.lessonDocument.aiFailed') : '')
const inlineAiProgressLabel = computed(() => {
  const elapsedSeconds = Math.max(0, Math.floor(Number(inlineAiProgress.value?.elapsed_ms || 0) / 1000))
  const message = String(inlineAiProgress.value?.message || tr('courseWorkbench.aiCollaboration.inlineWorking'))
  return elapsedSeconds
    ? `${message} · ${tr('courseWorkbench.aiCollaboration.inlineElapsed').replace('{seconds}', String(elapsedSeconds))}`
    : message
})

const moduleLabels = computed<Record<string, string>>(() => ({
  lesson_goal: tr('courseWorkbench.lessonModules.goal'),
  core_explanation: tr('courseWorkbench.lessonModules.explanation'),
  learner_action: tr('courseWorkbench.lessonModules.activity'),
  explained_example: tr('courseWorkbench.lessonModules.example'),
  guided_practice: tr('courseWorkbench.lessonModules.practice'),
  feedback_check: tr('courseWorkbench.lessonModules.feedback'),
  general_concept_model: tr('courseWorkbench.lessonModules.concept'),
  general_comparison: tr('courseWorkbench.lessonModules.comparison'),
  general_explained_example: tr('courseWorkbench.lessonModules.example'),
  general_application: tr('courseWorkbench.lessonModules.application'),
  general_checklist: tr('courseWorkbench.lessonModules.summary'),
  summary_and_transfer: tr('courseWorkbench.lessonModules.transfer'),
  assessment: tr('courseWorkbench.lessonModules.assessment'),
}))

function clonePlan(plan: Record<string, any>): Record<string, any> {
  return JSON.parse(JSON.stringify(plan)) as Record<string, any>
}

function ensureFormalObjectiveFields(section: Record<string, any>) {
  if (!Array.isArray(section.knowledge_objectives)) {
    section.knowledge_objectives = stringList(section.learning_objective)
  }
  if (!Array.isArray(section.ability_objectives)) {
    section.ability_objectives = uniqueItems([
      ...stringList(section.student_activities),
      ...(Array.isArray(section.teaching_modules) ? section.teaching_modules.map((item: any) => item.student_activity) : []),
    ], 3)
  }
  if (!Array.isArray(section.education_objectives)) section.education_objectives = []
}

function stringList(value: unknown): string[] {
  if (typeof value === 'string') return value.split(/\n|；/).map(item => item.trim()).filter(Boolean)
  return Array.isArray(value) ? value.map(item => String(item).trim()).filter(Boolean) : []
}

function listText(value: unknown): string {
  return stringList(value).join('\n')
}

function uniqueItems(values: unknown[], limit = 8): string[] {
  return [...new Set(values.map(item => String(item || '').trim()).filter(Boolean))].slice(0, limit)
}

function moduleItems(section: Record<string, any>, signals: string[]): string[] {
  return uniqueItems(sectionModules(section).flatMap(module => {
    const identity = `${String(module.module_id || '').toLowerCase()} ${String(module.label || '').toLowerCase()}`
    if (!signals.some(signal => identity.includes(signal))) return []
    return [module.teacher_activity, module.student_activity]
  }))
}

function sectionModules(section: Record<string, any>): any[] {
  return Array.isArray(section.teaching_modules) ? section.teaching_modules : []
}

function sectionMinutes(section: Record<string, any>): number {
  return sectionModules(section).reduce((total, module) => total + normalizedMinutes(module.planned_minutes), 0)
}

function sectionKnowledgeObjectives(section: Record<string, any>): string[] {
  return stringList(section.knowledge_objectives).length
    ? stringList(section.knowledge_objectives)
    : uniqueItems([section.learning_objective], 3)
}

function sectionAbilityObjectives(section: Record<string, any>): string[] {
  return stringList(section.ability_objectives).length
    ? stringList(section.ability_objectives)
    : uniqueItems([
        ...stringList(section.student_activities),
        ...sectionModules(section).map(module => module.student_activity),
      ], 3)
}

function sectionSummaryItems(section: Record<string, any>): string[] {
  return stringList(section.class_summary).length
    ? stringList(section.class_summary)
    : moduleItems(section, ['summary', 'reflection', 'closure', 'transfer'])
}

function resourceItems(section: Record<string, any>, module: Record<string, any>): string[] {
  return uniqueItems([
    ...stringList(module.resource_refs),
    ...stringList(module.tools),
    ...stringList(section.resource_refs),
  ], 16)
}

function classroomActivityItems(module: Record<string, any>): string[] {
  return uniqueItems([
    module.teacher_activity ? `${tr('courseWorkbench.lessonDocument.teacherActivity')}：${module.teacher_activity}` : '',
    module.student_activity ? `${tr('courseWorkbench.lessonDocument.studentActivity')}：${module.student_activity}` : '',
  ])
}

function attainmentJudgementItems(module: Record<string, any>): string[] {
  return uniqueItems([
    module.expected_output ? `${tr('courseWorkbench.lessonDocument.expectedOutput')}：${module.expected_output}` : '',
    module.check_method ? `${tr('courseWorkbench.lessonDocument.attainmentCheck')}：${module.check_method}` : '',
  ])
}

function updateResourcesAndTools(module: Record<string, any>, event: Event) {
  const values = (event.target as HTMLTextAreaElement).value.split('\n').map(item => item.trim()).filter(Boolean)
  module.resource_refs = values
  module.tools = []
  recordEditSnapshot()
}

function moduleIdentity(section: Record<string, any>, module: Record<string, any>, index: number): string {
  return String(module.arrangement_block_id || `${section.node_id || 'section'}:${module.module_id || index}`)
}

function isOvertimeModule(section: Record<string, any>, module: Record<string, any>, index: number): boolean {
  let elapsed = 0
  for (const currentSection of planSections.value) {
    for (const [currentIndex, currentModule] of sectionModules(currentSection).entries()) {
      elapsed += normalizedMinutes(currentModule.planned_minutes)
      if (moduleIdentity(currentSection, currentModule, currentIndex) === moduleIdentity(section, module, index)) {
        return elapsed > Number(props.lesson.duration_minutes || 0)
      }
    }
  }
  return false
}

function updateList(target: Record<string, any>, key: string, event: Event) {
  const value = (event.target as HTMLTextAreaElement).value
  target[key] = value.split('\n').map(item => item.trim()).filter(Boolean)
  recordEditSnapshot()
}

function recordEditSnapshot() {
  queueMicrotask(() => {
    if (editing.value && draftPlan.value) editHistory.record(draftPlan.value)
  })
}

function normalizedMinutes(value: unknown): number {
  const minutes = Number(value || 0)
  return Number.isFinite(minutes) ? Math.max(0, minutes) : 0
}

function sectionTitle(section: Record<string, any>): string {
  const nodeId = String(section.node_id || '')
  return props.lesson.sections.find(item => item.section_node_id === nodeId)?.title
    || tr('courseWorkbench.lessonSection')
}

function comparableTitle(value: unknown): string {
  return String(value || '')
    .replace(/^第\s*[0-9一二三四五六七八九十百]+\s*[讲章节课]\s*/u, '')
    .replace(/^\d+(?:\.\d+)+\s*/u, '')
    .replace(/^\d+\s*[.、：:]\s*/u, '')
    .replace(/^内容主题\s*\d+\s*/u, '')
    .replace(/[\s·：:，,。！？!?、]/gu, '')
    .toLocaleLowerCase()
}

function themeHeadingVisible(section: Record<string, any>): boolean {
  if (planSections.value.length > 1) return true
  const lessonTitle = comparableTitle(props.lesson.title)
  const currentSectionTitle = comparableTitle(sectionTitle(section))
  return !lessonTitle || !currentSectionTitle || lessonTitle !== currentSectionTitle
}

function themeAnchor(section: Record<string, any>): string {
  return `lesson-theme-${String(section.node_id || '').replace(/[^a-zA-Z0-9_-]/g, '-')}`
}

function activateSection(section: Record<string, any>, scroll = true) {
  const sectionId = String(section.node_id || '')
  if (!sectionId || (pendingCandidate.value && pendingCandidate.value.section_node_id !== sectionId)) return
  selectedSectionId.value = sectionId
  if (scroll) document.getElementById(themeAnchor(section))?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function moduleTitle(module: Record<string, any>, index: number): string {
  const phase = tr('courseWorkbench.lessonDocument.phaseFallback').replace('{count}', String(index + 1))
  const moduleId = String(module.module_id || '').trim()
  const rawLabel = String(module.label || '').trim()
  const placeholder = /^(?:环节|教学块|模块)\s*\d*$/u.test(rawLabel)
    || rawLabel === moduleId
  const purpose = (String(module.teaching_purpose || module.teaching_guidance || '')
    .split(/[，。；：]/u)[0] || '')
    .trim()
    .slice(0, 24)
  const name = (!placeholder && rawLabel)
    || moduleLabels.value[moduleId]
    || purpose
  return name ? `${phase}：${name}` : phase
}

function baseSection(sectionId: string): Record<string, any> | null {
  return basePlanSections.value.find(section => String(section.node_id || '') === sectionId) || null
}

function rawCandidateChanged(section: Record<string, any>, key: string): boolean {
  if (!pendingCandidate.value) return false
  const original = baseSection(String(section.node_id || ''))
  if (!original) return true
  if (key === 'knowledge_objectives') {
    return JSON.stringify(sectionKnowledgeObjectives(section)) !== JSON.stringify(sectionKnowledgeObjectives(original))
  }
  if (key === 'ability_objectives') {
    return JSON.stringify(sectionAbilityObjectives(section)) !== JSON.stringify(sectionAbilityObjectives(original))
  }
  return JSON.stringify(section[key] ?? null) !== JSON.stringify(original[key] ?? null)
}

function candidateChanged(section: Record<string, any>, key: string): boolean {
  const targetsOneListItem = pendingCandidate.value?.target_field === key
    && /^\d+$/.test(String(pendingCandidate.value?.target_item_id || ''))
  return !targetsOneListItem && rawCandidateChanged(section, key)
}

function candidateFieldChanged(section: Record<string, any>, key: string): boolean {
  return candidateChanged(section, key)
}

function candidateListItemChanged(section: Record<string, any>, key: string, index: number): boolean {
  if (!pendingCandidate.value) return false
  const original = baseSection(String(section.node_id || ''))
  if (!original) return true
  return stringList(section[key])[index] !== stringList(original[key])[index]
}

function moduleTargetId(module: Record<string, any>, index: number): string {
  return String(module.module_id || module.arrangement_block_id || index)
}

function candidateModuleChanged(
  section: Record<string, any>,
  module: Record<string, any>,
  key: string,
): boolean {
  if (!pendingCandidate.value) return false
  const originalSection = baseSection(String(section.node_id || ''))
  if (!originalSection) return true
  const targetId = String(module.module_id || module.arrangement_block_id || '')
  const original = sectionModules(originalSection).find(item => (
    String(item.module_id || item.arrangement_block_id || '') === targetId
  ))
  if (!original) return true
  return JSON.stringify(module[key] ?? null) !== JSON.stringify(original[key] ?? null)
}

function beginEditing() {
  if (!workingRevision.value?.plan) return
  draftPlan.value = clonePlan(workingRevision.value.plan)
  for (const section of draftPlan.value.sections || []) ensureFormalObjectiveFields(section)
  editHistory.reset(draftPlan.value)
  editing.value = true
  saveError.value = null
}

async function requestAiCandidate(
  instructionValue: string,
  target: TeacherInlineAiTarget = {},
  selectedText = '',
): Promise<TeacherLessonPlanCandidate | null> {
  const instruction = instructionValue.trim()
  if (!instruction || aiBusy.value || !workingRevision.value?.revision_id) return null
  aiBusy.value = true
  aiError.value = null
  inlineAiProgress.value = null
  try {
    pendingCandidate.value = await lessonStore.createAiCandidate(
      props.courseId,
      props.lesson.lesson_unit_id,
      workingRevision.value.revision_id,
      instruction,
      target.sectionNodeId || selectedSectionId.value,
      props.materialAssetIds,
      {
        sectionNodeId: target.sectionNodeId || selectedSectionId.value,
        field: target.field,
        itemId: target.itemId,
        selectedText,
      },
      progress => { inlineAiProgress.value = progress },
    )
    return pendingCandidate.value
  } catch (error: any) {
    aiError.value = error
    return null
  } finally {
    aiBusy.value = false
  }
}

async function requestInlineAiCandidate(payload: TeacherInlineAiRequest) {
  if (!payload.target?.field) {
    inlineCandidateInPlace.value = false
    emit('open-ai-selection', payload)
    return
  }
  inlineCandidateInPlace.value = true
  if (pendingCandidate.value) {
    const discarded = await resolveAiCandidate(false)
    if (!discarded) return
  }
  await requestAiCandidate(payload.instruction, payload.target, payload.text)
}

async function resolveInlineAiCandidate(accept: boolean) {
  const resolved = await resolveAiCandidate(accept)
  if (resolved) inlineCandidateInPlace.value = false
}

async function resolveAiCandidate(accept: boolean): Promise<boolean> {
  if (!pendingCandidate.value || aiBusy.value) return false
  emit('ai-resolving', { accept })
  aiBusy.value = true
  aiError.value = null
  try {
    await lessonStore.resolveAiCandidate(
      props.courseId,
      props.lesson.lesson_unit_id,
      pendingCandidate.value.candidate_id,
      accept,
    )
    pendingCandidate.value = null
    emit('ai-resolved', { accept })
    return true
  } catch (error: any) {
    aiError.value = error
    return false
  } finally {
    aiBusy.value = false
  }
}

function focusCandidate() {
  const target = documentRoot.value?.querySelector<HTMLElement>('.ai-change-target')
  if (target && typeof target.scrollIntoView === 'function') {
    target.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }
}

function openInlineAi() {
  inlineAiAction.value?.openForDocument()
}

function cancelEditing() {
  draftPlan.value = null
  editHistory.clear()
  editing.value = false
  saveError.value = null
}

async function saveDraft() {
  if (!draftPlan.value || saving.value) return
  saving.value = true
  saveError.value = null
  try {
    for (const section of draftPlan.value.sections || []) {
      ensureFormalObjectiveFields(section)
      section.learning_objective = [...section.knowledge_objectives, ...section.ability_objectives].join('；')
    }
    await lessonStore.saveDraft(props.courseId, props.lesson.lesson_unit_id, draftPlan.value)
    draftPlan.value = null
    editing.value = false
    emit('saved')
  } catch (error: any) {
    saveError.value = error
  } finally {
    saving.value = false
  }
}

watch(() => [
  props.lesson.lesson_unit_id,
  props.lesson.plan.working_revision_id,
  props.lesson.plan.ai_candidates,
], () => {
  cancelEditing()
  aiError.value = null
  inlineCandidateInPlace.value = false
  inlineAiProgress.value = null
  pendingCandidate.value = [...(props.lesson.plan.ai_candidates || [])]
    .reverse()
    .find(candidate => (
      candidate.status === 'pending'
      && candidate.base_revision_id === props.lesson.plan.working_revision_id
    )) || null
  selectedSectionId.value = String(
    pendingCandidate.value?.section_node_id
    || planSections.value[0]?.node_id
    || '',
  )
}, { immediate: true, deep: true })

watch(planSections, sections => {
  if (!sections.some(section => String(section.node_id || '') === selectedSectionId.value)) {
    selectedSectionId.value = String(sections[0]?.node_id || '')
  }
}, { deep: true })

watch(pendingCandidate, candidate => emit('ai-candidate-change', candidate), { immediate: true })
watch(aiBusy, busy => emit('ai-busy-change', busy))
watch(aiError, error => emit('ai-error', error ? toAppError(error, {
  title: tr('courseWorkbench.lessonDocument.aiFailed'),
  fallback: tr('courseWorkbench.lessonDocument.aiFailed'),
}).summary : ''))

defineExpose({
  requestAiCandidate,
  resolveAiCandidate,
  focusCandidate,
  openInlineAi,
  editing,
  saving,
  aiBusy,
  beginEditing,
  cancelEditing,
  saveDraft,
  canUndo: editHistory.canUndo,
  canRedo: editHistory.canRedo,
  undoEdit: editHistory.undo,
  redoEdit: editHistory.redo,
})
</script>

<style scoped>
.lesson-document{position:relative;background:#fff}
.document-header{min-height:92px;display:flex;align-items:center;justify-content:space-between;gap:24px;padding:20px 28px;border-bottom:1px solid #e8ecf2}
.document-title{min-width:0;display:flex;align-items:center}.document-title h3{margin:0;overflow:hidden;color:#172033;font-size:20px;letter-spacing:-.015em;text-overflow:ellipsis;white-space:nowrap}
.document-actions{flex:none;display:flex;align-items:center;gap:2px}.document-actions button{min-height:34px;display:flex;align-items:center;justify-content:center;gap:7px;padding:0 10px;border:1px solid transparent;border-radius:7px;color:#526077;background:transparent;font-size:15px;font-weight:750;cursor:pointer}.document-actions button:hover{color:#3730a3;background:#f2f3fa}.document-actions button:focus-visible{outline:2px solid #5b57e8;outline-offset:2px}.document-actions button:disabled{opacity:.5;cursor:not-allowed}.document-actions .primary-action{margin-left:4px;border-color:#d7ddea;color:#3730a3;background:#fff}.document-actions .primary-action:hover{border-color:#c6cbe0;background:#f7f7ff}
.candidate-canvas-notice{display:flex;align-items:center;justify-content:space-between;gap:18px;padding:11px 28px;border-bottom:1px solid #d9ddf5;color:#4338ca;background:#f5f5ff}.candidate-canvas-notice>div{min-width:0;display:flex;align-items:center;gap:9px}.candidate-canvas-notice>div>span{display:grid;gap:2px}.candidate-canvas-notice strong{font-size:15px}.candidate-canvas-notice small{color:#676aa0;font-size:11px}.candidate-canvas-notice nav{flex:none;display:flex;align-items:center;gap:6px}.candidate-canvas-notice button{min-height:32px;display:inline-flex;align-items:center;gap:5px;padding:0 9px;border:1px solid #d0d1ee;border-radius:7px;color:#4f55a9;background:#fff;font-size:11px;font-weight:750;cursor:pointer}.candidate-canvas-notice button.primary{border-color:#5148dc;color:#fff;background:#5148dc}.candidate-canvas-notice button:hover:not(:disabled){border-color:#9692e8;color:#4338ca;background:#f8f7ff}.candidate-canvas-notice button.primary:hover:not(:disabled){border-color:#433bc4;color:#fff;background:#433bc4}.candidate-canvas-notice button:focus-visible{outline:3px solid rgba(91,84,232,.22);outline-offset:2px}.candidate-canvas-notice button:disabled{opacity:.5;cursor:not-allowed}.lesson-document>:deep(.app-error-notice){margin:12px 28px 0}
.document-body{min-width:0;display:grid;padding:12px 28px 38px}.section-title{display:flex;align-items:center;gap:10px;padding:20px 0 3px}.section-title span{color:#6366f1;font-size:15px;font-weight:850}.section-title h4{margin:0;color:#172033;font-size:17px}.document-section{min-width:0;padding:24px 0;border-bottom:1px solid #e8ecf2}.document-section:last-child{border-bottom:0}.document-section h4{margin:0 0 13px;color:#263147;font-size:17px}.document-section p{margin:0;color:#536176;font-size:16px;line-height:1.8}.document-section ul,.document-section ol{display:grid;gap:8px;margin:0;padding-left:19px;color:#536176;font-size:16px;line-height:1.75}.document-section textarea,.flow-row input,.assignment-contract input{width:100%;box-sizing:border-box;border:1px solid #cbd4e1;border-radius:7px;outline:0;color:#263147;background:#fff;font:inherit;font-size:15px;line-height:1.6}.document-section textarea{min-height:78px;padding:10px 11px;font-size:16px;resize:vertical}.assignment-contract input{min-height:38px;padding:7px 9px}.document-section textarea:focus,.flow-row input:focus,.assignment-contract input:focus{border-color:#5b57e8;box-shadow:0 0 0 3px rgba(91,87,232,.1)}
.objective-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:24px}.objective-grid>div{min-width:0}.objective-grid h5{margin:0 0 9px;color:#4a5568;font-size:15px}.objective-section p{font-size:16px}.focus-grid,.closing-grid{display:grid;grid-template-columns:1fr 1fr;gap:0}.focus-grid>div,.closing-grid>div{min-width:0;padding-right:26px}.focus-grid>div+div,.closing-grid>div+div{padding-right:0;padding-left:26px;border-left:1px solid #e8ecf2}.section-heading{display:flex;align-items:center;justify-content:space-between;gap:16px}.section-heading span{color:#7a8699;font-size:15px}
.teaching-block-list{display:grid;gap:16px}.teaching-block{overflow:hidden;border:1px solid #dde3ec;border-radius:10px;background:#fff}.teaching-block>header{min-height:50px;display:flex;align-items:center;justify-content:space-between;gap:16px;padding:8px 14px;border-bottom:1px solid #e5eaf1;background:#f7f9fc}.teaching-block>header>strong{color:#334155;font-size:16px}.block-duration{display:flex;align-items:center;gap:8px;color:#718096;font-size:15px}.block-duration input{width:64px;height:34px;padding:5px;border:1px solid #cbd4e1;border-radius:7px;text-align:center}.block-duration b{color:#475569;font-size:15px}.block-fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0}.block-fields>label{min-width:0;display:grid;align-content:start;gap:8px;padding:15px;border-right:1px solid #e8ecf2;border-bottom:1px solid #e8ecf2}.block-fields>label:nth-child(2n){border-right:0}.block-fields>label.wide{grid-column:1/-1;border-right:0}.block-fields>label>span{color:#64748b;font-size:15px;font-weight:750}.block-fields textarea{min-height:80px;font-size:16px}.block-fields p{font-size:16px;line-height:1.75}.block-fields ul{font-size:16px}.materials-record>h4{margin-bottom:18px}
.lesson-block-summary{display:grid;grid-template-columns:repeat(2,minmax(0,1fr))}.lesson-block-summary>section{min-width:0;display:grid;align-content:start;gap:9px;padding:16px 17px;border-right:1px solid #e8ecf2;border-bottom:1px solid #e8ecf2}.lesson-block-summary>section:nth-child(2n){border-right:0}.lesson-block-summary>section:nth-child(n+3){border-bottom:0}.lesson-block-summary strong{color:#64748b;font-size:15px}.lesson-block-summary p{font-size:16px;line-height:1.75}.lesson-block-summary ul{gap:6px;font-size:16px;line-height:1.7}
.lesson-theme-nav{display:flex;gap:18px;overflow:auto;padding:4px 0 0;border-bottom:1px solid #e8ecf2}.lesson-theme-nav button{min-height:44px;display:flex;align-items:center;gap:6px;padding:0;border:0;border-bottom:2px solid transparent;color:#667085;background:transparent;font-size:15px;white-space:nowrap;cursor:pointer}.lesson-theme-nav button span{color:#98a2b3;font-size:15px;font-weight:800}.lesson-theme-nav button.active{border-bottom-color:#5b57e8;color:#3730a3;font-weight:750}.lesson-theme{scroll-margin-top:16px;padding:20px 0 12px;border-bottom:2px solid #e4e8ef}.lesson-theme.is-headingless{padding-top:0}.lesson-theme:last-child{border-bottom:0}.lesson-theme-heading{display:flex;align-items:center;justify-content:space-between;gap:18px;padding:9px 0 3px}.lesson-theme-heading>div{display:flex;align-items:baseline;gap:9px}.lesson-theme-heading span{color:#6366f1;font-size:15px;font-weight:800}.lesson-theme-heading h4{margin:0;color:#172033;font-size:18px}.lesson-theme-heading small{color:#667085;font-size:15px}.lesson-time-section .section-heading span{color:#667085}.teaching-block.is-overtime{border-color:#e9b98b}.overtime-warning{display:flex;align-items:center;gap:6px!important;padding:8px 14px;color:#9a4f12!important;background:#fff8ef;font-size:15px!important}.block-contingency{border-top:1px solid #e8ecf2}.block-contingency summary{width:max-content;margin:12px 14px;color:#514dc0;font-size:15px;font-weight:750;cursor:pointer}.block-contingency[open] summary{margin-bottom:0}.assignment-contract{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin-top:16px;padding-top:15px;border-top:1px solid #edf0f4}.assignment-contract label{min-width:0;display:grid;align-content:start;gap:6px}.assignment-contract label>span{color:#64748b;font-size:15px;font-weight:750}.assignment-contract p{font-size:15px}
.ai-change-target{position:relative}.is-ai-candidate .ai-change-target{margin-inline:-10px;padding-inline:10px;border-radius:9px;background:linear-gradient(90deg,rgba(238,242,255,.92),rgba(248,250,255,.42))}.ai-change-target::before{position:absolute;top:8px;bottom:8px;left:0;width:2px;border-radius:2px;background:#6366f1;content:""}.ai-change-marker{position:absolute;top:7px;right:9px;padding:3px 6px;border-radius:5px;color:#4338ca;background:#e0e7ff;font-size:15px;font-style:normal;font-weight:800}.flow-section.ai-change-target{padding-inline:10px}.focus-grid>div.ai-change-target,.closing-grid>div.ai-change-target{padding-top:12px;padding-bottom:12px}.focus-grid>div+div.ai-change-target,.closing-grid>div+div.ai-change-target{padding-left:36px}
.flow-table{width:100%;max-width:100%;box-sizing:border-box;overflow:hidden;border:1px solid #dde3ec;border-radius:8px}.flow-row{display:grid;grid-template-columns:72px minmax(120px,.82fr) minmax(170px,1.2fr) minmax(150px,1fr) minmax(150px,1fr);border-top:1px solid #e3e8f0}.flow-row:first-child{border-top:0}.flow-row>div,.flow-head>span{min-width:0;padding:13px 12px;border-left:1px solid #e3e8f0}.flow-row>div:first-child,.flow-head>span:first-child{border-left:0}.flow-head{color:#64748b;background:#f6f8fb;font-size:15px;font-weight:750}.flow-row p{font-size:16px;line-height:1.75}.flow-row ul{gap:6px;padding-left:16px;font-size:16px;line-height:1.7}.duration-cell{color:#475569;font-size:15px;text-align:center}.duration-cell input{height:34px;padding:6px;text-align:center}.phase-cell{display:grid;align-content:start;gap:8px}.phase-cell strong{color:#334155;font-size:15px}.phase-cell p{color:#667386;font-size:16px}.flow-row textarea{min-height:116px;font-size:16px}.flow-empty{padding:28px;color:#7a8699;font-size:15px;text-align:center}
.document-empty{min-height:280px;display:grid;place-items:center;color:#7a8699;font-size:15px}.spin{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}
@media(max-width:1050px){.document-body{padding-inline:20px}.objective-grid,.assignment-contract{grid-template-columns:1fr}}
@media(max-width:760px){.document-header{align-items:flex-start;flex-direction:column;padding-inline:18px}.document-actions{width:100%;justify-content:flex-end}.focus-grid,.closing-grid,.block-fields,.lesson-block-summary{grid-template-columns:1fr}.focus-grid>div,.closing-grid>div{padding-right:0}.focus-grid>div+div,.closing-grid>div+div{margin-top:20px;padding:20px 0 0;border-top:1px solid #e8ecf2;border-left:0}.block-fields>label,.lesson-block-summary>section{border-right:0;border-bottom:1px solid #e8ecf2}.lesson-block-summary>section:last-child{border-bottom:0}}
.document-actions button:hover{background:var(--teacher-component-tint,#f7f7ff)}
</style>
