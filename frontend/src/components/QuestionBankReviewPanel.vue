<template>
  <section
    class="question-bank-panel"
    :class="`is-${workspaceMode}`"
    :aria-label="t('courseWorkbench.stages.questionBank', '题库')"
  >
    <header class="question-bank-page-heading">
      <div class="question-bank-page-identity">
        <strong>{{ t('questionBank.workspace.courseBank', '课程题库') }}</strong>
        <span v-if="workspaceMode !== 'bank'" class="question-bank-workspace-context">{{ workspaceTitle }}</span>
        <span
          v-if="workspaceMode !== 'bank' || loading || rebuilding || pendingAiCandidate"
          class="question-bank-workspace-status"
          role="status"
        >
          <LoaderCircle v-if="loading || rebuilding" :size="14" class="spin" />
          <WandSparkles v-else-if="pendingAiCandidate" :size="14" />
          <CircleCheck v-else-if="items.length" :size="14" />
          <LibraryBig v-else :size="14" />
          {{ workspaceStatus }}
        </span>
        <button
          v-else-if="items.length"
          type="button"
          class="question-bank-quality-trigger"
          :aria-expanded="qualityPanelOpen"
          @click="qualityPanelOpen = !qualityPanelOpen"
        >
          <ShieldCheck :size="14" />
          <span>{{ t('questionBank.studio.qualityReview', '质量检查') }}</span>
          <small>{{ qualitySummaryText }}</small>
          <ChevronUp v-if="qualityPanelOpen" :size="14" />
          <ChevronDown v-else :size="14" />
        </button>
      </div>
      <nav class="question-bank-workspace-actions" :aria-label="t('questionBank.workspace.actions', '题库操作')">
        <button v-if="workspaceMode !== 'bank'" type="button" class="question-bank-back" @click="workspaceMode = 'bank'">
          <ArrowLeft :size="15" />{{ t('questionBank.workspace.backToBank', '返回题库') }}
        </button>
        <button v-if="workspaceMode !== 'import'" type="button" class="question-bank-import-action" @click="workspaceMode = 'import'">
          <FileUp :size="15" />{{ t('questionBank.importFlow.importFile', '导入题目文件') }}
        </button>
        <button v-if="workspaceMode !== 'generate'" type="button" class="question-bank-ai-action" @click="workspaceMode = 'generate'">
          <WandSparkles :size="15" />{{ t('questionBank.importFlow.aiGenerate', 'AI 生成题目') }}
        </button>
      </nav>
    </header>
    <div class="question-bank-document-surface">
    <div class="question-bank-workspace-body">
    <QuestionBankImportWorkspace
      v-if="workspaceMode === 'import'"
      :course-id="courseId"
      :initial-node-ids="initialNodeIds"
      @show-bank="workspaceMode = 'bank'"
      @imported="handleFileImport"
    />
    <template v-else>
    <main class="question-bank-workspace-main">
    <section v-if="workspaceMode === 'generate'" class="question-generation-studio" data-testid="question-generation-studio">
      <header class="question-generation-studio__header">
        <div v-if="publishedCount" class="question-generation-studio__published">
          <CircleCheck :size="15" />
          <span>{{ t('questionBank.studio.published', '已发布 {count} 道').replace('{count}', String(publishedCount)) }}</span>
        </div>
        <button
          v-if="!assistantOpen"
          type="button"
          class="question-generation-studio__ai"
          :disabled="loading || rebuilding"
          @click="emit('open-ai')"
        ><WandSparkles :size="15" />{{ t('questionBank.aiEdit', 'AI 调整') }}</button>
      </header>

      <div v-if="pendingAiCandidate" ref="candidateRef" class="question-ai-candidate" tabindex="-1">
        <WandSparkles :size="15" />
        <strong>{{ t('questionBank.aiTask', 'AI 出题任务') }}</strong>
        <span>{{ pendingAiCandidate.scope === 'nodes' ? (props.initialScopeLabel || t('questionBank.studio.currentLesson', '当前课次')) : t('questionBank.studio.wholeCourse', '整门课程') }}</span>
      </div>

      <div class="question-generation-flow">
        <section
          class="question-generation-step"
          role="radiogroup"
          aria-labelledby="question-scope-title"
        >
          <h4 id="question-scope-title">{{ t('questionBank.studio.scope', '出题范围') }}</h4>
          <div class="question-generation-scope">
            <label v-if="props.initialNodeIds.length" :class="{ active: generationScope === 'lesson' }">
              <input v-model="generationScope" type="radio" value="lesson" />
              <span>
                <strong>{{ props.initialScopeLabel || t('questionBank.studio.currentLesson', '当前课次') }}</strong>
              </span>
            </label>
            <label :class="{ active: generationScope === 'course' }">
              <input v-model="generationScope" type="radio" value="course" />
              <span>
                <strong>{{ t('questionBank.studio.wholeCourse', '整门课程') }}</strong>
              </span>
            </label>
          </div>
        </section>

        <section class="question-generation-step" aria-labelledby="question-intelligence-title">
          <h4 id="question-intelligence-title">{{ t('questionBank.studio.intelligence', '智能编排') }}</h4>
          <div class="question-intelligence-grid">
            <article>
              <SlidersHorizontal :size="16" />
              <span>
                <strong>{{ t('questionBank.studio.difficulty', '智能难度') }}</strong>
              </span>
              <em>{{ t('questionBank.studio.automatic', '自动') }}</em>
            </article>
            <article>
              <Shapes :size="16" />
              <span>
                <strong>{{ t('questionBank.studio.questionTypes', '题型组合') }}</strong>
              </span>
              <em>{{ t('questionBank.studio.automatic', '自动') }}</em>
            </article>
          </div>
        </section>

        <section class="question-generation-step question-generation-options" aria-labelledby="question-source-title">
          <h4 id="question-source-title">{{ t('questionBank.studio.sources', '生成设置') }}</h4>
          <div class="question-generation-option-list">
            <label class="question-generation-toggle">
              <span>
                <strong>{{ t('questionBank.studio.keepPublished', '保留已发布题目') }}</strong>
              </span>
              <input v-model="keepPublished" type="checkbox" />
            </label>
            <label class="question-generation-toggle">
              <span>
                <strong>{{ t('questionBank.studio.retrieval', '联网补充资料') }}</strong>
              </span>
              <input v-model="retrievalEnabled" type="checkbox" />
            </label>
          </div>
        </section>
      </div>

      <footer>
        <div class="question-bank-panel__header-action">
          <div v-if="canContinueGeneration" class="question-bank-panel__header-copy">
            <span v-if="canContinueGeneration" data-testid="chapter-generation-checkpoint">
              已发布新版章节 {{ completedChapters }}/{{ totalChapters }}
            </span>
          </div>
          <div class="question-bank-panel__header-buttons">
            <button
              v-if="canContinueGeneration && generationScope === 'course'"
              type="button"
              data-testid="continue-course-question-bank"
              :disabled="loading || rebuilding"
              @click="rebuild(undefined, true)"
            >
              <RefreshCw :size="14" :class="{ spin: rebuilding }" />
              {{ rebuilding
                ? t('questionBank.continuingCourse', '正在继续生成')
                : `继续生成剩余 ${remainingChapters} 章` }}
            </button>
            <button
              type="button"
              data-testid="generate-question-bank"
              class="question-generation-primary"
              :disabled="loading || rebuilding"
              @click="startGeneration"
            >
              <LoaderCircle v-if="rebuilding" :size="15" class="spin" />
              <WandSparkles v-else :size="15" />
              {{ rebuilding
                ? t('questionBank.studio.generating', '正在智能出题')
                : t('questionBank.studio.generate', '开始智能出题') }}
            </button>
          </div>
        </div>
      </footer>
    </section>

    <section
      v-if="rebuildJob"
      class="question-bank-progress"
      :data-status="rebuildJob.status"
      role="progressbar"
      aria-valuemin="0"
      aria-valuemax="100"
      :aria-valuenow="rebuildJob.progress"
      :aria-label="t('questionBank.regenerateProgress', '课程题目重新生成进度')"
      aria-live="polite"
    >
      <div>
        <strong>{{ rebuildHeadline }}</strong>
        <span>{{ rebuildJob.message || rebuildStageLabel }}</span>
        <small
          v-if="chapterProgressLabel"
          class="question-bank-progress__chapter"
        >
          {{ chapterProgressLabel }}
        </small>
      </div>
      <b>{{ rebuildJob.progress }}%</b>
      <i><span :style="{ transform: `scaleX(${rebuildJob.progress / 100})` }"></span></i>
      <small v-if="rebuildErrorMessage" class="question-bank-progress__error">
        {{ rebuildErrorMessage }}
      </small>
      <button
        v-if="canRetryFailedChapters"
        type="button"
        class="question-bank-progress__retry"
        data-testid="retry-failed-question-bank-chapters"
        :disabled="rebuilding"
        @click="retryFailedChapters"
      >
        <RefreshCw :size="14" :class="{ spin: rebuilding }" />
        {{ t('questionBank.retryFailedChapters', '重试失败章节') }}
      </button>
    </section>

    <div v-if="loading" class="question-bank-panel__state">
      <LoaderCircle :size="18" class="spin" />
      {{ t('questionBank.loading', '正在读取题库') }}
    </div>
    <div v-else-if="errorMessage" class="question-bank-panel__state question-bank-panel__state--error">
      <TriangleAlert :size="18" />
      <span>{{ errorMessage }}</span>
    </div>

    <section v-else-if="workspaceMode === 'bank' && (questionBankMissing || !items.length)" class="question-bank-empty-state">
      <span><LibraryBig :size="24" /></span>
      <strong>{{ t('questionBank.workspace.emptyTitle', '课程题库还没有题目') }}</strong>
      <p>{{ t('questionBank.workspace.emptyHint', '优先导入已有试卷，也可以让 AI 根据课程内容生成题目。') }}</p>
      <div>
        <button type="button" class="question-bank-empty-import" data-testid="empty-import-questions" @click="workspaceMode = 'import'">
          <FileUp :size="16" />{{ t('questionBank.workspace.importPrimary', '导入题目文件') }}
        </button>
        <button type="button" data-testid="empty-generate-questions" @click="workspaceMode = 'generate'">
          <WandSparkles :size="16" />{{ t('questionBank.importFlow.aiGenerate', 'AI 生成题目') }}
        </button>
      </div>
    </section>

    <template v-else-if="!questionBankMissing">
      <section v-show="qualityPanelOpen" class="question-quality-details">
        <header class="question-quality-details__header">
          <span>
            <ShieldCheck :size="15" />
            <strong>{{ t('questionBank.studio.qualityReview', '质量与覆盖检查') }}</strong>
          </span>
          <button
            type="button"
            :aria-label="t('common.close', '关闭')"
            @click="qualityPanelOpen = false"
          ><X :size="15" /></button>
        </header>
        <div class="question-quality-details__body">
      <div class="question-bank-summary">
        <article>
          <span>{{ t('questionBank.coverage', '必需目标覆盖') }}</span>
          <strong>{{ coverage.covered_objective_count || 0 }} / {{ coverage.required_objective_count || 0 }}</strong>
          <small>{{ Math.round(Number(coverage.coverage_ratio || 0) * 100) }}%</small>
        </article>
        <article>
          <span>{{ t('questionBank.availableQuestions', '当前可用题目') }}</span>
          <strong>{{ publishedCount }} {{ t('questionBank.questionUnit', '道') }}</strong>
          <small>
            {{ t('questionBank.exceptionReviewHint', '普通题自动生效；{count} 道高风险题等待发布前确认')
              .replace('{count}', String(reviewQueue.blocking_count || 0)) }}
          </small>
        </article>
        <article>
          <span>{{ t('questionBank.webSources', '联网补充') }}</span>
          <strong>{{ webStatusLabel }}</strong>
          <small>{{ t('questionBank.sourceCount', '{count} 个来源').replace('{count}', String(webEnrichment.source_count || 0)) }}</small>
          <small v-if="webRetrievalError" data-testid="question-bank-retrieval-error">
            {{ webRetrievalError }}
          </small>
        </article>
        <article data-testid="question-diversity-monitor">
          <span>{{ t('questionBank.diversity', '题组多样性') }}</span>
          <strong>{{ generationSummary.diversity_rejection_count || 0 }} 次拦截</strong>
          <small>
            重生成 {{ generationSummary.diversity_regeneration_count || 0 }} 次
            · 历史比较 {{ generationSummary.historical_diversity_comparison_count || 0 }} 道
          </small>
        </article>
      </div>

      <section class="assessment-profile" data-testid="assessment-profile">
        <header>
          <div>
            <span>{{ t('questionBank.profile', '课程测评画像') }}</span>
            <strong>{{ assessmentProfile.domain || assessmentProfile.subject_family || t('questionBank.profileUnknown', '待识别学科') }}</strong>
          </div>
          <small>
            {{ assessmentProfile.education_stage || '-' }}
            · {{ Math.round(Number(assessmentProfile.confidence || 0) * 100) }}%
          </small>
        </header>
        <p v-if="profileCapabilities">{{ profileCapabilities }}</p>
      </section>

      <section class="assessment-matrix" data-testid="assessment-coverage-matrix">
        <header>
          <div>
            <span>{{ t('questionBank.matrix', '目标—题型—来源—验证器覆盖矩阵') }}</span>
          </div>
          <div class="assessment-matrix__summary">
            <strong>{{ coveredObjectiveRows.length }} / {{ objectiveRows.length }}</strong>
            <small>
              {{ issueObjectiveRows.length
                ? `${issueObjectiveRows.length} 项需要处理`
                : t('questionBank.objective.allCovered', '全部已覆盖') }}
            </small>
          </div>
        </header>

        <section
          v-if="issueObjectiveRows.length"
          class="assessment-matrix__group assessment-matrix__group--issues"
          aria-labelledby="assessment-matrix-issues"
        >
          <header>
            <strong id="assessment-matrix-issues">
              {{ t('questionBank.objective.needsAttention', '需要处理') }}
            </strong>
            <small>{{ issueObjectiveRows.length }}</small>
          </header>
          <div class="assessment-matrix__rows">
            <article
              v-for="row in issueObjectiveRows"
              :key="row.objective_id"
              data-testid="objective-issue-row"
            >
              <div>
                <strong>{{ row.objective }}</strong>
                <small>{{ row.archetype }} · {{ row.validator }}</small>
              </div>
              <span :data-status="row.status">{{ objectiveStatusLabel(row.status) }}</span>
              <button
                type="button"
                :data-testid="`rebuild-objective-${row.node_id}`"
                :disabled="rebuilding"
                @click="rebuild(row.node_id)"
              >
                <RefreshCw :size="13" />
                {{ t('questionBank.rebuildNode', '重建节点') }}
              </button>
            </article>
          </div>
        </section>

        <section
          v-if="coveredObjectiveRows.length"
          class="assessment-matrix__group assessment-matrix__group--covered"
          aria-labelledby="assessment-matrix-covered"
        >
          <button
            id="assessment-matrix-covered"
            type="button"
            class="assessment-matrix__covered-toggle"
            data-testid="toggle-covered-objectives"
            :aria-expanded="coveredObjectivesExpanded"
            aria-controls="assessment-matrix-covered-list"
            @click="toggleCoveredObjectives"
          >
            <span>
              <CircleCheck :size="16" />
              <strong>
                {{ coveredObjectiveRows.length }}
                {{ t('questionBank.objective.coveredItems', '项已覆盖') }}
              </strong>
            </span>
            <span>
              {{ coveredObjectivesExpanded
                ? t('questionBank.objective.collapseCovered', '收起已覆盖项')
                : t('questionBank.objective.viewCovered', '查看全部已覆盖项') }}
              <ChevronUp v-if="coveredObjectivesExpanded" :size="15" />
              <ChevronDown v-else :size="15" />
            </span>
          </button>

          <div
            v-if="coveredObjectivesExpanded"
            id="assessment-matrix-covered-list"
            class="assessment-matrix__covered-content"
          >
            <div class="assessment-matrix__rows assessment-matrix__rows--covered">
              <article
                v-for="row in paginatedCoveredObjectiveRows"
                :key="row.objective_id"
                data-testid="objective-covered-row"
              >
                <div>
                  <strong>{{ row.objective }}</strong>
                </div>
                <span :data-status="row.status">{{ objectiveStatusLabel(row.status) }}</span>
                <details class="assessment-matrix__menu">
                  <summary
                    :aria-label="`${row.objective}的更多操作`"
                    :title="t('common.moreActions', '更多操作')"
                  >
                    <Ellipsis :size="16" />
                  </summary>
                  <div>
                    <button
                      type="button"
                      :data-testid="`rebuild-objective-${row.node_id}`"
                      :disabled="rebuilding"
                      @click="rebuild(row.node_id)"
                    >
                      <RefreshCw :size="13" />
                      {{ t('questionBank.rebuildNode', '重建节点') }}
                    </button>
                  </div>
                </details>
              </article>
            </div>

            <CompactPagination
              v-if="coveredObjectivePageCount > 1"
              class="assessment-matrix__pagination"
              :label="t('questionBank.objective.pagination', '已覆盖目标分页')"
              :page="coveredObjectivePage"
              :page-count="coveredObjectivePageCount"
              :range-text="objectivePageRangeText"
              :previous-label="t('common.previousPage', '上一页')"
              :next-label="t('common.nextPage', '下一页')"
              :page-select-label="t('questionBank.objective.jumpToPage', '选择页码')"
              test-id-prefix="objective"
              @update:page="setCoveredObjectivePage"
            />
          </div>
        </section>

        <div v-if="!objectiveRows.length" class="assessment-matrix__empty">
          {{ t('questionBank.objective.empty', '暂无测评目标') }}
        </div>
      </section>
        </div>
      </section>

      <section v-if="browseItems.length" class="question-browser question-review-workspace">
        <aside class="question-index" :aria-label="t('questionBank.questionIndex', '题目目录')">
          <header class="question-index__toolbar">
            <div class="question-browser__identity">
              <strong>{{ t('questionBank.browseTitle', '浏览全部题目') }}</strong>
              <small v-if="browseItems.length === activeItems.length">{{ activeItems.length }} 道</small>
              <small v-else>{{ browseItems.length }} / {{ activeItems.length }}</small>
            </div>
            <div class="question-browser__controls">
              <label>
                <Search :size="14" />
                <input
                  v-model="browserQuery"
                  data-testid="question-search-input"
                  type="search"
                  :placeholder="t('questionBank.searchQuestion', '搜索题目内容')"
                />
              </label>
              <select v-model="browserStatus" data-testid="question-status-filter" :aria-label="t('questionBank.filter.label', '筛选题目状态')">
                <option value="all">{{ t('questionBank.filter.all', '全部状态') }}</option>
                <option value="published">{{ t('questionBank.filter.published', '已发布') }}</option>
                <option value="mandatory">{{ t('questionBank.filter.mandatory', '发布前审核') }}</option>
                <option value="rework">{{ t('questionBank.filter.rework', '重做中') }}</option>
              </select>
            </div>
          </header>

          <div class="question-review-list">
            <article
              v-for="item in paginatedBrowseItems"
              :key="item.revision_id"
              data-testid="question-review-item"
              class="question-review-item"
              :class="{ 'is-expanded': isQuestionExpanded(item) }"
            >
              <button
                type="button"
                class="question-review-item__summary"
                data-testid="toggle-question-details"
                :aria-expanded="isQuestionExpanded(item)"
                :aria-controls="`question-details-${item.revision_id}`"
                :aria-current="isQuestionExpanded(item) ? 'true' : undefined"
                @click="toggleQuestionDetails(item)"
              >
                <span class="question-review-item__number">{{ questionNumber(item) }}</span>
                <span class="question-review-item__question">
                  <strong class="question-review-item__preview">{{ questionPreview(item) }}</strong>
                  <small>{{ questionTypeLabel(item) }} · {{ validationModeLabel(item.validation_mode) }}</small>
                </span>
                <span class="question-review-item__status" :data-status="item.lifecycle_status">
                  <i aria-hidden="true"></i>
                  {{ shortItemStatusLabel(item) }}
                </span>
              </button>
            </article>
          </div>

          <CompactPagination
            v-if="questionPageCount > 1"
            class="question-browser__pagination"
            :label="t('questionBank.questionPagination', '题目列表分页')"
            :page="questionPage"
            :page-count="questionPageCount"
            :range-text="questionPageRangeText"
            :previous-label="t('common.previousPage', '上一页')"
            :next-label="t('common.nextPage', '下一页')"
            :page-select-label="t('questionBank.jumpToQuestionPage', '选择题目页码')"
            test-id-prefix="question"
            @update:page="setQuestionPage"
          />
        </aside>

        <article
          v-if="selectedQuestion"
          :id="`question-details-${selectedQuestion.revision_id}`"
          class="question-review-item__details question-reader"
          :aria-label="t('questionBank.questionReader', '题目查看与审阅')"
        >
          <header class="question-reader__header">
            <div>
              <span class="question-review-item__status" :data-status="selectedQuestion.lifecycle_status">
                <i aria-hidden="true"></i>{{ itemStatusLabel(selectedQuestion) }}
              </span>
              <strong>{{ t('questionBank.questionPosition', '第 {current} / {total} 题')
                .replace('{current}', String(selectedQuestionNumber))
                .replace('{total}', String(browseItems.length)) }}</strong>
            </div>
            <nav :aria-label="t('questionBank.questionNavigation', '切换题目')">
              <button type="button" :disabled="!hasPreviousQuestion" :aria-label="t('questionBank.previousQuestion', '上一题')" @click="selectAdjacentQuestion(-1)"><ChevronLeft :size="16" /></button>
              <button type="button" :disabled="!hasNextQuestion" :aria-label="t('questionBank.nextQuestion', '下一题')" @click="selectAdjacentQuestion(1)"><ChevronRight :size="16" /></button>
            </nav>
          </header>

          <div class="question-reader__scroll">
            <section class="question-sheet">
              <div class="question-sheet__meta">
                <span>{{ questionTypeLabel(selectedQuestion) }}</span>
                <span>{{ sourceLabel(selectedQuestion.source_records) }}</span>
                <span>{{ validationModeLabel(selectedQuestion.validation_mode) }}</span>
                <span :data-status="selectedQuestion.quality_report?.passed ? 'passed' : 'failed'">
                  {{ selectedQuestion.quality_report?.passed
                    ? t('questionBank.qualityPassed', '质量检查通过')
                    : t('questionBank.qualityFailed', '需要修正') }}
                </span>
              </div>

              <div v-if="questionStimulus(selectedQuestion)" class="question-sheet__section question-sheet__stimulus">
                <small>{{ t('questionBank.questionStimulus', '题目材料') }}</small>
                <MarkdownRenderer :content="questionStimulus(selectedQuestion)" :enable-code-run="false" />
              </div>
              <div class="question-sheet__section question-sheet__task">
                <small>{{ t('questionBank.questionContent', '题目') }}</small>
                <MarkdownRenderer :content="questionTask(selectedQuestion)" :enable-code-run="false" />
              </div>

              <ol v-if="questionOptions(selectedQuestion).length" class="question-sheet__options">
                <li v-for="option in questionOptions(selectedQuestion)" :key="`${selectedQuestion.revision_id}-${option.id}`">
                  <b>{{ option.id }}</b>
                  <MarkdownRenderer :content="option.text" :enable-code-run="false" />
                </li>
              </ol>

              <div v-if="questionDeliverable(selectedQuestion) || questionConstraints(selectedQuestion).length" class="question-sheet__requirements">
                <strong>{{ t('questionBank.answerRequirements', '作答要求') }}</strong>
                <p v-if="questionDeliverable(selectedQuestion)">{{ questionDeliverable(selectedQuestion) }}</p>
                <ul v-if="questionConstraints(selectedQuestion).length">
                  <li v-for="constraint in questionConstraints(selectedQuestion)" :key="constraint">{{ constraint }}</li>
                </ul>
              </div>
            </section>

            <section class="question-answer-panel">
              <header>
                <div>
                  <strong>{{ t('questionBank.answerReview', '答案与解析') }}</strong>
                  <span>{{ t('questionBank.teacherOnlyAnswer', '仅教师可见') }}</span>
                </div>
                <button
                  v-if="!solutions[selectedQuestion.revision_id]"
                  type="button"
                  class="question-review-item__solution"
                  data-testid="load-question-solution"
                  :disabled="solutionLoadingRevision === selectedQuestion.revision_id"
                  @click="loadSolution(selectedQuestion)"
                >
                  <LoaderCircle v-if="solutionLoadingRevision === selectedQuestion.revision_id" :size="14" class="spin" />
                  <Eye v-else :size="14" />
                  {{ t('questionBank.solutionDiff', '查看答案与解析') }}
                </button>
              </header>

              <div v-if="!solutions[selectedQuestion.revision_id]" class="question-answer-panel__locked">
                <Eye :size="18" />
                <span>{{ t('questionBank.answerHiddenHint', '答案默认收起，查看后可对照完整解析与独立验证结果。') }}</span>
              </div>
              <section v-else class="question-solution-diff">
                <div class="question-solution-diff__worked">
                  <strong>{{ t('questionBank.workedSolution', '完整解析') }}</strong>
                  <p v-if="solutionSpec(solutions[selectedQuestion.revision_id] || {}).summary">
                    {{ solutionSpec(solutions[selectedQuestion.revision_id] || {}).summary }}
                  </p>
                  <ol v-if="solutionSpec(solutions[selectedQuestion.revision_id] || {}).steps?.length">
                    <li v-for="(step, stepIndex) in solutionSpec(solutions[selectedQuestion.revision_id] || {}).steps" :key="`${selectedQuestion.revision_id}-solution-step-${stepIndex}`">
                      {{ formatSolutionStep(step) }}
                    </li>
                  </ol>
                  <strong>{{ t('questionBank.canonicalAnswer', '标准答案') }}</strong>
                  <pre>{{ formatValue(solutionSpec(solutions[selectedQuestion.revision_id] || {}).final_answer ?? '-') }}</pre>
                  <section v-if="solutionSpec(solutions[selectedQuestion.revision_id] || {}).option_analysis?.length" class="question-solution-diff__analysis">
                    <strong>{{ t('questionBank.optionAnalysis', '选项解析') }}</strong>
                    <ul>
                      <li v-for="analysis in solutionSpec(solutions[selectedQuestion.revision_id] || {}).option_analysis" :key="`${selectedQuestion.revision_id}-option-${analysis.option_id}`">
                        <b>{{ analysis.option_id }}</b>：{{ analysis.explanation }}
                      </li>
                    </ul>
                  </section>
                  <section v-if="solutionSpec(solutions[selectedQuestion.revision_id] || {}).checks?.length" class="question-solution-diff__analysis">
                    <strong>{{ t('questionBank.solutionChecks', '结果检查') }}</strong>
                    <ul><li v-for="check in solutionSpec(solutions[selectedQuestion.revision_id] || {}).checks" :key="`${selectedQuestion.revision_id}-check-${check}`">{{ check }}</li></ul>
                  </section>
                  <section v-if="solutionSpec(solutions[selectedQuestion.revision_id] || {}).common_errors?.length" class="question-solution-diff__analysis">
                    <strong>{{ t('questionBank.commonErrors', '常见错误') }}</strong>
                    <ul><li v-for="error in solutionSpec(solutions[selectedQuestion.revision_id] || {}).common_errors" :key="`${selectedQuestion.revision_id}-error-${error}`">{{ error }}</li></ul>
                  </section>
                </div>
                <details class="question-solution-diff__validation">
                  <summary>{{ t('questionBank.independentValidation', '独立验证详情') }}</summary>
                  <strong>{{ t('questionBank.canonicalAnswer', '标准答案或量规') }}</strong>
                  <pre>{{ solutionAnswer(solutions[selectedQuestion.revision_id] || {}) }}</pre>
                  <strong>{{ t('questionBank.independentValidation', '独立求解与验证') }}</strong>
                  <pre>{{ solutionValidation(solutions[selectedQuestion.revision_id] || {}) }}</pre>
                </details>
              </section>
            </section>

            <details v-if="selectedQuestion.design_brief_summary?.schema_version" class="question-generation-audit" data-testid="question-generation-audit">
              <summary>
                <span>{{ t('questionBank.qualityDetails', '生成与质量检查详情') }}</span>
                <small>{{ selectedQuestion.design_brief_summary.semantics_registry_id || selectedQuestion.question_type }}</small>
              </summary>
              <div class="question-generation-audit__grid">
                <span>内容 RAG<b :data-status="selectedQuestion.design_brief_summary.content_coverage ? 'passed' : 'warning'">{{ selectedQuestion.design_brief_summary.content_coverage ? '已覆盖' : '缺口回退' }}</b></span>
                <span>题型方法 RAG<b :data-status="selectedQuestion.design_brief_summary.method_coverage ? 'passed' : 'warning'">{{ selectedQuestion.design_brief_summary.method_coverage ? '已覆盖' : '内置模板' }}</b></span>
                <span>语义预检<b :data-status="selectedQuestion.semantic_preflight?.passed ? 'passed' : 'failed'">{{ selectedQuestion.semantic_preflight?.passed ? '通过' : '未通过' }}</b></span>
                <span>首轮生成<b :data-status="selectedQuestion.generation_audit_summary?.first_pass_passed ? 'passed' : 'warning'">{{ selectedQuestion.generation_audit_summary?.first_pass_passed ? '一次通过' : `修复 ${selectedQuestion.generation_audit_summary?.repair_count || 0} 次` }}</b></span>
                <span>LLM 语义评审<b>{{ selectedQuestion.generation_audit_summary?.semantic_reviewer_trigger ? '已调用' : '规则通过，未调用' }}</b></span>
                <span>题组多样性<b :data-status="selectedQuestion.diversity_report?.passed === false ? 'failed' : 'passed'">{{ selectedQuestion.diversity_report?.passed === false ? `重复 ${Math.round(Number(selectedQuestion.diversity_report?.max_similarity || 0) * 100)}%` : `通过 ${Math.round(Number(selectedQuestion.diversity_report?.max_similarity || 0) * 100)}%` }}</b></span>
              </div>
              <p v-if="selectedQuestion.generation_audit_summary?.issue_codes?.length">问题代码：{{ selectedQuestion.generation_audit_summary.issue_codes.join('、') }}</p>
              <p v-if="selectedQuestion.diversity_report?.passed === false">最接近题目：{{ selectedQuestion.diversity_report.closest_question_id || '-' }} · 原因：{{ selectedQuestion.diversity_report.reasons?.join('、') || '语义重复' }}</p>
            </details>

            <section class="question-review-decision">
              <label>
                <span>{{ t('questionBank.reviewNote', '审阅意见') }}</span>
                <textarea v-model="reviewNotes[selectedQuestion.revision_id]" :placeholder="t('questionBank.reworkNote', '可选：说明哪里有问题，帮助下一版改进')" />
              </label>
            </section>
          </div>

          <footer class="question-reader__footer">
            <label
              class="question-reader__paper-select"
              :class="{ disabled: !canAddToExamPaper(selectedQuestion) }"
              :title="canAddToExamPaper(selectedQuestion) ? t('questionBank.examPaper.selectQuestion') : t('questionBank.examPaper.approvedOnly')"
            >
              <input
                type="checkbox"
                :checked="isQuestionSelected(selectedQuestion)"
                :disabled="!canAddToExamPaper(selectedQuestion)"
                @change="toggleQuestionSelection(selectedQuestion)"
              />
              <span>{{ isQuestionSelected(selectedQuestion)
                ? t('questionBank.examPaper.selectedQuestion', '已选入试卷')
                : t('questionBank.examPaper.selectQuestion', '选入试卷') }}</span>
            </label>
            <div class="question-reader__actions">
              <button v-if="selectedQuestions.length" type="button" class="question-reader__compose" :disabled="!bundleRevisionId" @click="paperComposerOpen = true">
                <FilePlus2 :size="15" />{{ t('questionBank.examPaper.selectedCount').replace('{count}', String(selectedQuestions.length)) }} · {{ t('questionBank.examPaper.compose') }}
              </button>
              <button
                type="button"
                class="question-review-item__reject"
                data-testid="rework-question"
                :disabled="actingRevision === selectedQuestion.revision_id"
                @click="rework(selectedQuestion)"
              >
                <RefreshCw v-if="actingRevision === selectedQuestion.revision_id" :size="14" class="spin" />
                <X v-else :size="14" />
                {{ selectedQuestion.lifecycle_status === 'rejected' ? t('questionBank.retryRework', '重新尝试') : t('questionBank.rework', '打回重做') }}
              </button>
              <button
                v-if="selectedQuestion.lifecycle_status === 'needs_review'"
                type="button"
                class="question-review-item__approve"
                data-testid="approve-question"
                :disabled="actingRevision === selectedQuestion.revision_id"
                @click="approve(selectedQuestion)"
              >
                <Check :size="14" />{{ t('questionBank.approve', '批准发布') }}
              </button>
            </div>
          </footer>
        </article>
      </section>
      <div v-else class="question-bank-panel__empty">
        <CircleCheck :size="21" />
        <strong>{{ t('questionBank.noMatchingQuestions', '没有符合条件的题目') }}</strong>
      </div>
    </template>
    <ExamPaperComposer
      v-if="paperComposerOpen"
      :course-id="courseId"
      :bundle-revision-id="bundleRevisionId"
      :questions="selectedQuestions"
      @close="paperComposerOpen = false"
      @created="handlePaperCreated"
    />
    </main>
    </template>
    <aside ref="workspaceSideRef" class="question-bank-workspace-side">
      <CourseReferenceTray
        v-model="questionReferences"
        :course-id="courseId"
        stage="question-bank"
        variant="question-bank"
        scope-target-id="managed:question-bank"
        scope-target-type="question_bank"
        :scope-target-label="t('questionBank.workspace.courseBank', '课程题库')"
      />
    </aside>
    </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import {
  computed,
  onBeforeUnmount,
  onMounted,
  reactive,
  ref,
  watch,
} from 'vue'
import {
  ArrowLeft,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  CircleCheck,
  Ellipsis,
  Eye,
  FileUp,
  FilePlus2,
  LibraryBig,
  LoaderCircle,
  RefreshCw,
  Search,
  Shapes,
  ShieldCheck,
  SlidersHorizontal,
  TriangleAlert,
  WandSparkles,
  X,
} from 'lucide-vue-next'
import ExamPaperComposer from './ExamPaperComposer.vue'
import CompactPagination from './CompactPagination.vue'
import CourseReferenceTray, { type CourseReferenceItem } from './CourseReferenceTray.vue'
import MarkdownRenderer from './MarkdownRenderer.vue'
import QuestionBankImportWorkspace from './QuestionBankImportWorkspace.vue'
import http from '@/utils/http'
import { t } from '@/shared/i18n'
import { retrievalErrorTranslationKey } from '@/utils/retrieval-errors'
import { createUuid } from '@/utils/client-id'
import {
  resumeQuestionBankRebuild,
  runQuestionBankRebuild,
  type QuestionBankRebuildJob,
} from '@/utils/question-bank-rebuild'

interface QuestionBankItem {
  item_id: string
  revision_id: string
  prompt: string
  assessment_role: string
  lifecycle_status: string
  risk_flags: string[]
  quality_report?: {
    passed?: boolean
    status?: string
    diversity_report?: QuestionDiversityReport
  }
  source_records?: Array<Record<string, unknown>>
  node_id?: string
  objective_id?: string
  archetype_id?: string
  validation_mode?: string
  generation_status?: string
  review_status?: string
  review_tier?: 'auto_publish' | 'sample_review' | 'mandatory_review'
  question_type?: string
  question_form?: string
  deliverable?: string
  input_materials?: string[]
  constraints?: string[]
  question_spec?: {
    stimulus?: { rendered_text?: string }
    task?: { rendered_text?: string; deliverable?: string }
    options?: Array<{ id: string; text: string }>
    constraints?: string[]
    response_contract?: { format?: string }
  }
  design_brief_summary?: {
    schema_version?: string
    semantics_registry_id?: string
    content_coverage?: boolean
    method_coverage?: boolean
  }
  semantic_preflight?: {
    passed?: boolean
    issues?: Array<{ code?: string }>
  }
  generation_audit_summary?: {
    first_pass_passed?: boolean
    repair_count?: number
    semantic_reviewer_trigger?: boolean
    issue_codes?: string[]
  }
  diversity_report?: QuestionDiversityReport
  diversity_signature?: {
    signature_id?: string
    plugin_id?: string
    material_preview?: string
  }
}

interface QuestionDiversityReport {
  passed?: boolean
  max_similarity?: number
  closest_question_id?: string
  reasons?: string[]
  threshold?: number
}

interface AssessmentObjective {
  objective_id: string
  node_id: string
  objective: string
  source_sufficiency?: string
  preferred_archetype_ids?: string[]
  generation_status?: string
  risk_level?: string
}

interface ExamPaperSummary {
  paper_id: string
  title: string
  item_count: number
  updated_at?: string
}

const props = withDefaults(defineProps<{
  courseId: string
  initialNodeIds?: string[]
  initialScopeLabel?: string
  assistantOpen?: boolean
  initialWorkspaceMode?: 'import' | 'bank' | 'generate'
}>(), {
  initialNodeIds: () => [],
  initialScopeLabel: '',
  assistantOpen: false,
  initialWorkspaceMode: 'bank',
})
interface QuestionBankAiCandidate {
  candidate_id: string
  base_bundle_revision_id: string
  scope: 'course' | 'nodes'
  node_ids: string[]
  material_asset_ids: string[]
  teacher_instruction: string
  mode: 'incremental' | 'full'
  retrieval_enabled: boolean
  created_at: string
}
const emit = defineEmits<{
  updated: [bundleRevisionId: string]
  'open-ai': []
  'ai-candidate-change': [candidate: QuestionBankAiCandidate | null]
  'ai-resolving': [result: { accept: boolean }]
  'ai-resolved': [result: { accept: boolean }]
  'ai-error': [message: string]
  'import-mode-change': [active: boolean]
  'references-change': [references: CourseReferenceItem[]]
}>()
const workspaceMode = ref<'import' | 'bank' | 'generate'>(props.initialWorkspaceMode)
const questionReferences = ref<CourseReferenceItem[]>([])
const workspaceSideRef = ref<HTMLElement | null>(null)
const effectiveMaterialAssetIds = computed(() => [...new Set(
  questionReferences.value.map(item => item.material_asset_id).filter(Boolean),
)])
const loading = ref(false)
const rebuilding = ref(false)
const actingRevision = ref('')
const errorMessage = ref('')
const questionBankMissing = ref(false)
const rebuildErrorMessage = ref('')
const bundleRevisionId = ref('')
const coverage = ref<Record<string, number>>({})
const reviewQueue = ref<Record<string, any>>({})
const generationSummary = ref<Record<string, any>>({})
const webEnrichment = ref<Record<string, unknown>>({})
const assessmentProfile = ref<Record<string, any>>({})
const assessmentObjectives = ref<AssessmentObjective[]>([])
const chapterRebuild = ref<Record<string, any>>({})
const items = ref<QuestionBankItem[]>([])
const examPapers = ref<ExamPaperSummary[]>([])
const selectedQuestionRevisions = ref<string[]>([])
const paperComposerOpen = ref(false)
const qualityPanelOpen = ref(false)
const reviewNotes = reactive<Record<string, string>>({})
const expandedQuestionRevision = ref('')
const rebuildJob = ref<QuestionBankRebuildJob | null>(null)
const solutionLoadingRevision = ref('')
const solutions = reactive<Record<string, Record<string, any>>>({})
const browserQuery = ref('')
const browserStatus = ref<'all' | 'published' | 'mandatory' | 'rework'>('all')
const questionPage = ref(1)
const coveredObjectivesExpanded = ref(false)
const coveredObjectivePage = ref(1)
const generationScope = ref<'lesson' | 'course'>(props.initialNodeIds.length ? 'lesson' : 'course')
const retrievalEnabled = ref(false)
const keepPublished = ref(true)
const pendingAiCandidate = ref<QuestionBankAiCandidate | null>(null)
const candidateRef = ref<HTMLElement | null>(null)
let rebuildAbortController: AbortController | null = null
const QUESTION_PAGE_SIZE = 10
const COVERED_OBJECTIVE_PAGE_SIZE = 10

const activeItems = computed(() => items.value.filter(
  item => item.lifecycle_status !== 'retired',
))
const selectedQuestions = computed(() => {
  const selected = new Set(selectedQuestionRevisions.value)
  return activeItems.value
    .filter(item => selected.has(item.revision_id))
    .map(item => ({
      revision_id: item.revision_id,
      prompt: item.prompt,
      question_type: item.question_type,
    }))
})
const publishedCount = computed(() => activeItems.value.filter(
  item => item.lifecycle_status === 'approved',
).length)
const workspaceTitle = computed(() => {
  if (workspaceMode.value === 'import') return t('questionBank.workspace.importTitle', '导入与校对')
  if (workspaceMode.value === 'generate') return t('questionBank.workspace.generateTitle', 'AI 生成题目')
  return t('questionBank.workspace.manageTitle', '全部题目')
})
const workspaceStatus = computed(() => {
  if (loading.value) return t('questionBank.loading', '正在读取题库')
  if (rebuilding.value) return t('questionBank.studio.generating', '正在智能出题')
  if (pendingAiCandidate.value) return t('courseWorkbench.lessonDocument.aiCandidatePending', 'AI 方案待处理')
  if (items.value.length) return t('questionBank.workspace.publishedStatus', '{count} 道已发布').replace('{count}', String(publishedCount.value))
  return t('questionBank.workspace.emptyStatus', '尚无题目')
})
const totalChapters = computed(() => Number(
  chapterRebuild.value.total_chapters || 0,
))
const completedChapters = computed(() => Number(
  chapterRebuild.value.completed_chapters
  ?? chapterRebuild.value.published_node_ids?.length
  ?? 0,
))
const remainingChapters = computed(() => Math.max(
  0,
  Number(
    chapterRebuild.value.remaining_chapters
    ?? totalChapters.value - completedChapters.value,
  ),
))
const canContinueGeneration = computed(() => Boolean(
  chapterRebuild.value.can_resume
  && completedChapters.value > 0
  && remainingChapters.value > 0,
))
const browseItems = computed(() => {
  const keyword = browserQuery.value.trim().toLocaleLowerCase()
  return activeItems.value.filter(item => {
    const matchesQuery = !keyword || [
      item.prompt,
      item.assessment_role,
      item.node_id,
      item.objective_id,
    ].some(value => String(value || '').toLocaleLowerCase().includes(keyword))
    const matchesStatus = (
      browserStatus.value === 'all'
      || (
        browserStatus.value === 'published'
        && item.lifecycle_status === 'approved'
      )
      || (
        browserStatus.value === 'mandatory'
        && item.lifecycle_status === 'needs_review'
      )
      || (
        browserStatus.value === 'rework'
        && item.lifecycle_status === 'rejected'
      )
    )
    return matchesQuery && matchesStatus
  })
})
const questionPageCount = computed(() => Math.max(
  1,
  Math.ceil(browseItems.value.length / QUESTION_PAGE_SIZE),
))
const paginatedBrowseItems = computed(() => {
  const start = (questionPage.value - 1) * QUESTION_PAGE_SIZE
  return browseItems.value.slice(start, start + QUESTION_PAGE_SIZE)
})
const selectedQuestion = computed<QuestionBankItem | null>(() => (
  browseItems.value.find(
    item => item.revision_id === expandedQuestionRevision.value,
  )
  || paginatedBrowseItems.value[0]
  || null
))
const selectedQuestionNumber = computed(() => {
  if (!selectedQuestion.value) return 0
  return browseItems.value.findIndex(
    item => item.revision_id === selectedQuestion.value?.revision_id,
  ) + 1
})
const hasPreviousQuestion = computed(() => selectedQuestionNumber.value > 1)
const hasNextQuestion = computed(() => (
  selectedQuestionNumber.value > 0
  && selectedQuestionNumber.value < browseItems.value.length
))
const questionPageStart = computed(() => (
  (questionPage.value - 1) * QUESTION_PAGE_SIZE + 1
))
const questionPageEnd = computed(() => Math.min(
  browseItems.value.length,
  questionPage.value * QUESTION_PAGE_SIZE,
))
const questionPageRangeText = computed(() => t(
  'questionBank.pagination.questionRange',
  '第 {start}–{end} 题，共 {total} 题',
).replace('{start}', String(questionPageStart.value))
  .replace('{end}', String(questionPageEnd.value))
  .replace('{total}', String(browseItems.value.length)))
const objectiveRows = computed(() => assessmentObjectives.value.map(objective => {
  const related = items.value.filter(item => (
    item.objective_id === objective.objective_id
    || item.node_id === objective.node_id
  ))
  const published = related.some(item => item.generation_status === 'published')
  const review = related.some(item => item.generation_status === 'waiting_review')
  const failed = related.some(item => item.generation_status === 'validation_failed')
  const status = published
    ? 'covered'
    : review
      ? 'review'
      : failed
        ? 'failed'
        : objective.source_sufficiency === 'insufficient'
          ? 'source'
          : 'missing'
  return {
    ...objective,
    archetype: related[0]?.archetype_id
      || objective.preferred_archetype_ids?.[0]
      || '-',
    validator: related[0]?.validation_mode || '-',
    status,
  }
}))
const issueObjectiveRows = computed(() => objectiveRows.value.filter(
  row => row.status !== 'covered',
))
const coveredObjectiveRows = computed(() => objectiveRows.value.filter(
  row => row.status === 'covered',
))
const qualitySummaryText = computed(() => {
  const pendingReviewCount = Number(reviewQueue.value.blocking_count || 0)
  if (pendingReviewCount > 0) {
    return t(
      'questionBank.studio.pendingReview',
      '{count} 道待审核',
    ).replace('{count}', String(pendingReviewCount))
  }
  const coverageGapCount = Math.max(
    issueObjectiveRows.value.length,
    Number(coverage.value.required_objective_count || 0)
      - Number(coverage.value.covered_objective_count || 0),
  )
  if (coverageGapCount > 0) {
    return t(
      'questionBank.studio.coverageGap',
      '{count} 项待覆盖',
    ).replace('{count}', String(coverageGapCount))
  }
  return t('questionBank.objective.allCovered', '全部已覆盖')
})
const coveredObjectivePageCount = computed(() => Math.max(
  1,
  Math.ceil(
    coveredObjectiveRows.value.length / COVERED_OBJECTIVE_PAGE_SIZE,
  ),
))
const paginatedCoveredObjectiveRows = computed(() => {
  const start = (
    coveredObjectivePage.value - 1
  ) * COVERED_OBJECTIVE_PAGE_SIZE
  return coveredObjectiveRows.value.slice(
    start,
    start + COVERED_OBJECTIVE_PAGE_SIZE,
  )
})
const coveredObjectivePageStart = computed(() => (
  (coveredObjectivePage.value - 1) * COVERED_OBJECTIVE_PAGE_SIZE + 1
))
const coveredObjectivePageEnd = computed(() => Math.min(
  coveredObjectiveRows.value.length,
  coveredObjectivePage.value * COVERED_OBJECTIVE_PAGE_SIZE,
))
const objectivePageRangeText = computed(() => t(
  'questionBank.pagination.objectiveRange',
  '第 {start}–{end} 项，共 {total} 项',
).replace('{start}', String(coveredObjectivePageStart.value))
  .replace('{end}', String(coveredObjectivePageEnd.value))
  .replace('{total}', String(coveredObjectiveRows.value.length)))
const profileCapabilities = computed(() => {
  const archetypes = assessmentProfile.value.allowed_archetype_ids || []
  const validators = assessmentProfile.value.validator_ids || assessmentProfile.value.validation_modes || []
  return [
    archetypes.length
      ? t('questionBank.profileArchetypes', '{count} question archetypes').replace('{count}', String(archetypes.length))
      : '',
    validators.length
      ? t('questionBank.profileValidators', '{count} validation modes').replace('{count}', String(validators.length))
      : '',
  ].filter(Boolean).join(' · ')
})
const rebuildStageLabel = computed(() => {
  const current = rebuildJob.value?.current_stage || ''
  const stage = rebuildJob.value?.stages?.find(item => item.stage_id === current)
  return String(stage?.label || current || t('questionBank.rebuildQueued', '等待生成'))
})
const rebuildHeadline = computed(() => {
  const status = rebuildJob.value?.status
  if (status === 'completed') {
    return t(
      'questionBank.regenerateCompleted',
      '课程题目已重新生成并发布',
    )
  }
  if (status === 'waiting_review') {
    return t(
      'questionBank.regenerateWaitingReview',
      '题目已生成，部分高风险题目待审核',
    )
  }
  if (status === 'failed') {
    return t(
      'questionBank.regenerateFailed',
      '重新生成失败，当前有效题库保持不变',
    )
  }
  return t(
    'questionBank.regenerateRunning',
    '正在按章节重新生成课程题目',
  )
})
const chapterProgressLabel = computed(() => {
  const details = rebuildJob.value?.stage_details
  const total = Number(details?.total_chapters || 0)
  if (!total) return ''
  const published = Number(details?.published_chapters || 0)
  const current = String(details?.current_chapter || '').trim()
  const currentItem = Number(details?.current_chapter_item || 0)
  const itemTotal = Number(details?.chapter_item_total || 3)
  return [
    `章节发布 ${published}/${total}`,
    current
      ? `当前 ${current}${currentItem ? `（${currentItem}/${itemTotal}）` : ''}`
      : '',
  ].filter(Boolean).join(' · ')
})
const failedChapterNodeIds = computed(() => [
  ...new Set(
    (rebuildJob.value?.stage_details?.failed_chapters || [])
      .map(item => String(item?.node_id || '').trim())
      .filter(Boolean),
  ),
])
const canRetryFailedChapters = computed(() => Boolean(
  rebuildJob.value?.status === 'failed'
  && rebuildJob.value?.error?.retryable !== false
  && failedChapterNodeIds.value.length,
))
const webStatusLabel = computed(() => {
  const status = String(webEnrichment.value.status || '')
  const labels: Record<string, string> = {
    completed: t('questionBank.web.completed', '已补充'),
    not_needed: t('questionBank.web.notNeeded', '无需补充'),
    not_started: t('questionBank.web.notStarted', '未启用'),
    unavailable_fallback_local: t('questionBank.web.fallback', '已回退本地'),
    failed_fallback_local: t('questionBank.web.fallback', '已回退本地'),
  }
  return labels[status] || t('questionBank.web.notStarted', '未启用')
})
const webRetrievalError = computed(() => {
  const key = retrievalErrorTranslationKey(webEnrichment.value)
  return key ? t(key, '') : ''
})

onMounted(() => {
  emit('import-mode-change', workspaceMode.value === 'import')
  void load().then(restoreAiCandidate)
  void loadExamPapers()
  void recoverActiveRebuild()
})
onBeforeUnmount(() => {
  emit('import-mode-change', false)
  rebuildAbortController?.abort()
})
watch(() => props.courseId, () => {
  workspaceMode.value = 'bank'
  questionReferences.value = []
  rebuildAbortController?.abort()
  rebuildAbortController = null
  rebuildJob.value = null
  rebuildErrorMessage.value = ''
  browserQuery.value = ''
  browserStatus.value = 'all'
  setQuestionPage(1)
  expandedQuestionRevision.value = ''
  coveredObjectivesExpanded.value = false
  selectedQuestionRevisions.value = []
  paperComposerOpen.value = false
  pendingAiCandidate.value = null
  setCoveredObjectivePage(1)
  void load().then(restoreAiCandidate)
  void loadExamPapers()
  void recoverActiveRebuild()
})
watch(workspaceMode, mode => {
  emit('import-mode-change', mode === 'import')
})
watch(questionReferences, references => {
  emit('references-change', references)
}, { deep: true, immediate: true })
watch(() => props.initialNodeIds, value => {
  generationScope.value = value.length ? 'lesson' : 'course'
}, { deep: true })
watch(coveredObjectivePageCount, pageCount => {
  if (coveredObjectivePage.value > pageCount) {
    setCoveredObjectivePage(pageCount)
  }
})
watch([browserQuery, browserStatus], () => {
  expandedQuestionRevision.value = ''
  setQuestionPage(1)
})
watch(questionPageCount, pageCount => {
  if (questionPage.value > pageCount) {
    setQuestionPage(pageCount)
  }
})

function setQuestionPage(page: number) {
  const normalizedPage = Number.isFinite(page) ? Math.trunc(page) : 1
  expandedQuestionRevision.value = ''
  questionPage.value = Math.min(
    questionPageCount.value,
    Math.max(1, normalizedPage),
  )
}

function isQuestionExpanded(item: QuestionBankItem) {
  return selectedQuestion.value?.revision_id === item.revision_id
}

function toggleQuestionDetails(item: QuestionBankItem) {
  expandedQuestionRevision.value = item.revision_id
}

function selectAdjacentQuestion(offset: -1 | 1) {
  const currentIndex = selectedQuestionNumber.value - 1
  const targetIndex = currentIndex + offset
  const target = browseItems.value[targetIndex]
  if (!target) return
  questionPage.value = Math.floor(targetIndex / QUESTION_PAGE_SIZE) + 1
  expandedQuestionRevision.value = target.revision_id
}

function questionNumber(item: QuestionBankItem) {
  const index = browseItems.value.findIndex(
    candidate => candidate.revision_id === item.revision_id,
  )
  return String(Math.max(0, index) + 1).padStart(2, '0')
}

function questionStimulus(item: QuestionBankItem) {
  return String(item.question_spec?.stimulus?.rendered_text || '').trim()
}

function questionTask(item: QuestionBankItem) {
  return String(
    item.question_spec?.task?.rendered_text
    || item.prompt
    || '',
  ).trim()
}

function questionPreview(item: QuestionBankItem) {
  return questionTask(item) || item.prompt
}

function questionOptions(item: QuestionBankItem) {
  return (item.question_spec?.options || []).filter(
    option => option?.id && option?.text,
  )
}

function questionDeliverable(item: QuestionBankItem) {
  return String(
    item.question_spec?.task?.deliverable
    || item.deliverable
    || '',
  ).trim()
}

function questionConstraints(item: QuestionBankItem) {
  const values = item.question_spec?.constraints || item.constraints || []
  return values.map(value => String(value || '').trim()).filter(Boolean)
}

function questionTypeLabel(item: QuestionBankItem) {
  const type = String(
    item.question_spec?.response_contract?.format
    || item.question_form
    || item.question_type
    || '',
  )
  const labels: Record<string, string> = {
    single_choice: t('questionBank.types.singleChoice', '单选题'),
    multiple_choice: t('questionBank.types.multipleChoice', '多选题'),
    true_false: t('questionBank.types.trueFalse', '判断题'),
    fill_blank: t('questionBank.types.fillBlank', '填空题'),
    numeric: t('questionBank.types.numeric', '计算题'),
    numeric_with_work: t('questionBank.types.numericWithWork', '计算题'),
    structured: t('questionBank.types.structured', '结构化作答'),
    symbolic_reasoning: t('questionBank.types.symbolicReasoning', '推导题'),
    case_analysis: t('questionBank.types.caseAnalysis', '综合分析题'),
    essay: t('questionBank.types.essay', '论述题'),
  }
  return labels[type] || t('questionBank.types.question', '题目')
}

async function handleFileImport(bundleRevision: string) {
  await load()
  workspaceMode.value = 'bank'
  emit('updated', bundleRevision)
}

function toggleCoveredObjectives() {
  coveredObjectivesExpanded.value = !coveredObjectivesExpanded.value
  if (coveredObjectivesExpanded.value) {
    setCoveredObjectivePage(1)
  }
}

function setCoveredObjectivePage(page: number) {
  const normalizedPage = Number.isFinite(page) ? Math.trunc(page) : 1
  coveredObjectivePage.value = Math.min(
    coveredObjectivePageCount.value,
    Math.max(1, normalizedPage),
  )
}

async function recoverActiveRebuild() {
  const courseId = props.courseId
  if (!courseId) return
  const controller = new AbortController()
  rebuildAbortController?.abort()
  rebuildAbortController = controller
  try {
    const job = await resumeQuestionBankRebuild(
      courseId,
      {
        maxPolls: 3600,
        signal: controller.signal,
        onUpdate: update => {
          if (
            controller.signal.aborted
            || props.courseId !== courseId
          ) return
          rebuildJob.value = update
          rebuilding.value = (
            update.status === 'queued'
            || update.status === 'running'
          )
        },
      },
    )
    if (
      job
      && !controller.signal.aborted
      && props.courseId === courseId
    ) {
      await load()
    }
  } catch (error: any) {
    if (!isAbortError(error)) {
      if (error?.job) {
        rebuildJob.value = error.job
        rebuildErrorMessage.value = error?.message || t(
          'questionBank.rebuildFailed',
          '课程题目重新生成失败，当前有效题库未被覆盖，可以稍后重试。',
        )
      } else {
        rebuildErrorMessage.value = t(
          'questionBank.rebuildProgressRecoveryFailed',
          '暂时无法恢复生成进度，请稍后重新打开题库面板。',
        )
      }
    }
  } finally {
    if (rebuildAbortController === controller) {
      rebuildAbortController = null
      rebuilding.value = false
    }
  }
}

async function load() {
  if (!props.courseId) return
  loading.value = true
  errorMessage.value = ''
  questionBankMissing.value = false
  try {
    const response = await http.get(
      `/api/courses/${props.courseId}/question-bank`,
      { silentError: true },
    )
    const data = response.data || {}
    bundleRevisionId.value = String(data.bundle_revision_id || '')
    coverage.value = data.coverage || {}
    reviewQueue.value = data.review_queue || {}
    generationSummary.value = data.generation_summary || {}
    webEnrichment.value = data.web_enrichment || {}
    assessmentProfile.value = data.assessment_profile || {}
    chapterRebuild.value = data.chapter_rebuild || {}
    assessmentObjectives.value = Array.isArray(data.assessment_objectives)
      ? data.assessment_objectives
      : []
    items.value = Array.isArray(data.items) ? data.items : []
    const available = new Set(items.value.map(item => item.revision_id))
    selectedQuestionRevisions.value = selectedQuestionRevisions.value.filter(
      revisionId => available.has(revisionId),
    )
  } catch (error: any) {
    if (error?.response?.status === 404) {
      questionBankMissing.value = true
    } else {
      errorMessage.value = t('questionBank.loadFailed', '题库读取失败，请稍后重试。')
    }
  } finally {
    loading.value = false
  }
}

async function loadExamPapers() {
  if (!props.courseId) return
  try {
    const response = await http.get(
      `/api/courses/${props.courseId}/question-bank/exam-papers`,
      { silentError: true },
    )
    examPapers.value = Array.isArray(response.data?.papers)
      ? response.data.papers
      : []
  } catch {
    examPapers.value = []
  }
}

function canAddToExamPaper(item: QuestionBankItem) {
  return item.lifecycle_status === 'approved'
    && item.quality_report?.passed !== false
}

function isQuestionSelected(item: QuestionBankItem) {
  return selectedQuestionRevisions.value.includes(item.revision_id)
}

function toggleQuestionSelection(item: QuestionBankItem) {
  if (!canAddToExamPaper(item)) return
  selectedQuestionRevisions.value = isQuestionSelected(item)
    ? selectedQuestionRevisions.value.filter(
      revisionId => revisionId !== item.revision_id,
    )
    : [...selectedQuestionRevisions.value, item.revision_id]
}

function handlePaperCreated() {
  paperComposerOpen.value = false
  selectedQuestionRevisions.value = []
  void loadExamPapers()
}

function startGeneration() {
  const nodeIds = generationScope.value === 'lesson'
    ? props.initialNodeIds
    : undefined
  return rebuild(
    nodeIds,
    questionBankMissing.value ? false : keepPublished.value,
  )
}

function aiCandidateStorageKey() {
  return `question-bank-ai-candidate:${props.courseId}`
}

function persistAiCandidate() {
  try {
    if (pendingAiCandidate.value) {
      window.localStorage.setItem(
        aiCandidateStorageKey(),
        JSON.stringify(pendingAiCandidate.value),
      )
    } else {
      window.localStorage.removeItem(aiCandidateStorageKey())
    }
  } catch { /* local recovery is best effort */ }
}

function restoreAiCandidate() {
  try {
    const raw = window.localStorage.getItem(aiCandidateStorageKey())
    if (!raw) return
    const candidate = JSON.parse(raw) as QuestionBankAiCandidate
    if (
      candidate?.teacher_instruction
      && (!candidate.base_bundle_revision_id
        || candidate.base_bundle_revision_id === bundleRevisionId.value)
    ) {
      pendingAiCandidate.value = candidate
      emit('ai-candidate-change', candidate)
    } else {
      window.localStorage.removeItem(aiCandidateStorageKey())
    }
  } catch { /* ignore malformed recovery state */ }
}

async function requestAiCandidate(value: string) {
  const instruction = value.trim()
  if (!instruction || rebuilding.value) return null
  const scope = generationScope.value === 'lesson' && props.initialNodeIds.length
    ? 'nodes'
    : 'course'
  pendingAiCandidate.value = {
    candidate_id: createUuid(),
    base_bundle_revision_id: bundleRevisionId.value,
    scope,
    node_ids: scope === 'nodes' ? [...props.initialNodeIds] : [],
    material_asset_ids: [...effectiveMaterialAssetIds.value],
    teacher_instruction: instruction,
    mode: keepPublished.value ? 'incremental' : 'full',
    retrieval_enabled: retrievalEnabled.value,
    created_at: new Date().toISOString(),
  }
  persistAiCandidate()
  emit('ai-candidate-change', pendingAiCandidate.value)
  return pendingAiCandidate.value
}

async function resolveAiCandidate(accept: boolean) {
  const candidate = pendingAiCandidate.value
  if (!candidate || rebuilding.value) return false
  emit('ai-resolving', { accept })
  try {
    if (accept) {
      const response = await http.post(
        `/api/courses/${props.courseId}/question-bank/rebuild`,
        {
          request_id: createUuid(),
          scope: candidate.scope,
          node_ids: candidate.node_ids,
          material_asset_ids: candidate.material_asset_ids,
          mode: candidate.mode,
          resume_existing: true,
          retrieval_enabled: candidate.retrieval_enabled,
          teacher_instruction: candidate.teacher_instruction,
        },
      )
      rebuildJob.value = response.data as QuestionBankRebuildJob
      rebuilding.value = true
      void recoverActiveRebuild()
    }
    pendingAiCandidate.value = null
    persistAiCandidate()
    emit('ai-candidate-change', null)
    emit('ai-resolved', { accept })
    return true
  } catch (error: any) {
    emit(
      'ai-error',
      error?.response?.data?.detail?.message
        || t('questionBank.rebuildFailed', '题库任务创建失败'),
    )
    return false
  }
}

function focusAiCandidate() {
  candidateRef.value?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  candidateRef.value?.focus({ preventScroll: true })
}

function focusReferenceSources() {
  workspaceSideRef.value?.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'nearest' })
  workspaceSideRef.value?.querySelector<HTMLElement>('button, [tabindex]')?.focus()
}

async function rebuild(nodeId?: string | string[], resumeExisting = true) {
  if (!props.courseId || rebuilding.value) return
  rebuildAbortController?.abort()
  const controller = new AbortController()
  rebuildAbortController = controller
  rebuilding.value = true
  errorMessage.value = ''
  rebuildErrorMessage.value = ''
  rebuildJob.value = null
  try {
    const scopedNodeIds = (Array.isArray(nodeId) ? nodeId : [nodeId])
      .map(value => String(value || ''))
      .filter(Boolean)
    await runQuestionBankRebuild(
      props.courseId,
      {
        request_id: createUuid(),
        scope: scopedNodeIds.length ? 'nodes' : 'course',
        node_ids: scopedNodeIds,
        mode: scopedNodeIds.length && resumeExisting ? 'incremental' : 'full',
        retrieval_enabled: retrievalEnabled.value,
        material_asset_ids: effectiveMaterialAssetIds.value,
        teacher_instruction: '',
        ...(!scopedNodeIds.length ? { resume_existing: resumeExisting } : {}),
      },
      {
        maxPolls: scopedNodeIds.length ? 450 : 3600,
        signal: controller.signal,
        onUpdate: job => {
          rebuildJob.value = job
        },
      },
    )
    await load()
  } catch (error: any) {
    if (isAbortError(error)) return
    rebuildErrorMessage.value = error?.message || t(
      'questionBank.rebuildFailed',
      '课程题目重新生成失败，当前有效题库未被覆盖，可以稍后重试。',
    )
    const latestJob = rebuildJob.value as QuestionBankRebuildJob | null
    rebuildJob.value = error?.job || {
      job_id: 'local-rebuild-error',
      status: 'failed',
      progress: latestJob?.progress || 0,
      current_stage: latestJob?.current_stage,
      message: latestJob?.message,
      status_url: '',
    }
  } finally {
    if (rebuildAbortController === controller) {
      rebuildAbortController = null
      rebuilding.value = false
    }
  }
}

async function retryFailedChapters() {
  if (!failedChapterNodeIds.value.length) return
  await rebuild(failedChapterNodeIds.value, true)
}

function isAbortError(error: any) {
  return error?.name === 'AbortError'
}

async function loadSolution(item: QuestionBankItem) {
  if (solutions[item.revision_id]) return
  solutionLoadingRevision.value = item.revision_id
  try {
    const response = await http.get(
      `/api/courses/${props.courseId}/question-bank/items/${item.revision_id}/solution`,
    )
    solutions[item.revision_id] = response.data || {}
  } catch {
    errorMessage.value = t(
      'questionBank.solutionLoadFailed',
      '私有答案与验证结果读取失败，请稍后重试。',
    )
  } finally {
    solutionLoadingRevision.value = ''
  }
}

async function approve(item: QuestionBankItem) {
  actingRevision.value = item.revision_id
  try {
    await submitDecision(item, 'approved')
    delete reviewNotes[item.revision_id]
    delete solutions[item.revision_id]
    emit('updated', bundleRevisionId.value)
  } catch (error: any) {
    errorMessage.value = error?.response?.status === 409
      ? t('questionBank.conflict', '题库已被其他操作更新，已重新加载。')
      : t('questionBank.reviewFailed', '审核保存失败，请重试。')
    if (error?.response?.status === 409) await load()
  } finally {
    actingRevision.value = ''
  }
}

async function rework(item: QuestionBankItem) {
  if (!props.courseId || actingRevision.value) return
  actingRevision.value = item.revision_id
  rebuilding.value = true
  errorMessage.value = ''
  try {
    if (item.lifecycle_status !== 'rejected') {
      await submitDecision(item, 'rejected')
    }
    await runQuestionBankRebuild(
      props.courseId,
      {
        request_id: createUuid(),
        scope: 'items',
        node_ids: [],
        revision_ids: [item.revision_id],
        mode: 'incremental',
        retrieval_enabled: retrievalEnabled.value,
        material_asset_ids: effectiveMaterialAssetIds.value,
        teacher_instruction: reviewNotes[item.revision_id] || '',
      },
      {
        onUpdate: job => {
          rebuildJob.value = job
        },
      },
    )
    delete reviewNotes[item.revision_id]
    delete solutions[item.revision_id]
    await load()
    emit('updated', bundleRevisionId.value)
  } catch (error: any) {
    errorMessage.value = error?.response?.status === 409
      ? t('questionBank.conflict', '题库已被其他操作更新，已重新加载。')
      : t(
        'questionBank.reworkFailed',
        '题目已从练习中下架，但重新生成失败；可在“重做中”再次尝试。',
      )
    if (error?.response?.status === 409) await load()
  } finally {
    actingRevision.value = ''
    rebuilding.value = false
  }
}

async function submitDecision(
  item: QuestionBankItem,
  decision: 'approved' | 'rejected',
) {
  const response = await http.post(
    `/api/courses/${props.courseId}/question-bank/items/${item.revision_id}/reviews`,
    {
      decision,
      note: reviewNotes[item.revision_id] || '',
      expected_bundle_revision_id: bundleRevisionId.value,
    },
  )
  const data = response.data || {}
  const updatedItem = data.item || {
    ...item,
    lifecycle_status: decision,
  }
  const itemIndex = items.value.findIndex(
    candidate => candidate.revision_id === item.revision_id,
  )
  if (itemIndex >= 0) {
    items.value.splice(itemIndex, 1, {
      ...items.value[itemIndex],
      ...updatedItem,
    })
  }
  bundleRevisionId.value = String(
    data.bundle_revision_id || bundleRevisionId.value,
  )
  reviewQueue.value = data.review_queue || reviewQueue.value
  return updatedItem
}

function itemStatusLabel(item: QuestionBankItem) {
  if (item.lifecycle_status === 'approved') {
    return t('questionBank.status.published', '已发布')
  }
  if (item.lifecycle_status === 'rejected') {
    return t('questionBank.status.rework', '已下架 · 等待重做')
  }
  if (item.lifecycle_status === 'needs_review') {
    return `${t('questionBank.status.mandatory', '发布前审核')} · ${riskLabel(item.risk_flags)}`
  }
  return item.lifecycle_status
}

function shortItemStatusLabel(item: QuestionBankItem) {
  if (item.lifecycle_status === 'approved') {
    return t('questionBank.status.published', '已发布')
  }
  if (item.lifecycle_status === 'rejected') {
    return t('questionBank.status.reworkShort', '重做中')
  }
  if (item.lifecycle_status === 'needs_review') {
    return t('questionBank.status.reviewShort', '待审核')
  }
  return item.lifecycle_status
}

function validationModeLabel(mode = '') {
  const labels: Record<string, string> = {
    exact_validator: t('questionBank.validationMode.exact', '精确答案校验'),
    numeric_unit_validator: t('questionBank.validationMode.numericUnit', '数值与单位校验'),
    symbolic_validator: t('questionBank.validationMode.symbolic', '公式校验'),
    code_validator: t('questionBank.validationMode.code', '代码校验'),
    rubric_validator: t('questionBank.validationMode.rubric', '量规校验'),
    expert_rubric_validator: t('questionBank.validationMode.expertRubric', '专家量规审核'),
  }
  return labels[mode] || t('questionBank.validationMode.automatic', '自动校验')
}

function riskLabel(risks: string[] = []) {
  const labels: Record<string, string> = {
    comprehensive_task: t('questionBank.risk.comprehensive', '综合题需确认'),
    low_parse_confidence: t('questionBank.risk.ocr', '解析置信度低'),
    missing_answer: t('questionBank.risk.answer', '缺少答案'),
    answer_conflict: t('questionBank.risk.conflict', '答案冲突'),
    web_license_unknown: t('questionBank.risk.rights', '联网许可不明'),
    near_duplicate: t('questionBank.risk.duplicate', '近似重复'),
  }
  return risks.map(risk => labels[risk] || risk).join(' · ') || t('questionBank.risk.manual', '人工确认')
}

function sourceLabel(records: Array<Record<string, unknown>> = []) {
  const source = records[0] || {}
  const type = String(source.source_type || '')
  if (type === 'teacher_upload') return t('questionBank.source.teacher', '教师资料')
  if (type === 'web') return t('questionBank.source.web', '联网参考')
  if (type === 'course_knowledge_base') return t('questionBank.source.course', '课程知识库')
  return t('questionBank.source.generated', '课程内生成')
}

function objectiveStatusLabel(status: string) {
  const labels: Record<string, string> = {
    covered: t('questionBank.objective.covered', '已覆盖'),
    review: t('questionBank.objective.review', '待审核'),
    failed: t('questionBank.objective.failed', '验证失败'),
    source: t('questionBank.objective.source', '资料不足'),
    missing: t('questionBank.objective.missing', '未覆盖'),
  }
  return labels[status] || status
}

function solutionAnswer(payload: Record<string, any>) {
  const envelope = payload.solution_envelope || {}
  return formatValue(
    envelope.canonical_answer
    ?? envelope.acceptable_answers
    ?? envelope.rubric
    ?? '-',
  )
}

function solutionSpec(payload: Record<string, any>) {
  return payload.solution_spec || {}
}

function formatSolutionStep(step: unknown) {
  if (typeof step === 'string') return step
  if (!step || typeof step !== 'object') return String(step || '')
  const value = step as Record<string, unknown>
  return [
    value.title,
    value.explanation,
    value.calculation,
    value.result,
    value.check,
  ].filter(Boolean).join('；')
}

function solutionValidation(payload: Record<string, any>) {
  return formatValue(payload.solution_validation || '-')
}

function formatValue(value: unknown) {
  if (typeof value === 'string') return value
  return JSON.stringify(value, null, 2)
}

defineExpose({ requestAiCandidate, resolveAiCandidate, focusAiCandidate, focusReferenceSources })
</script>

<style scoped>
.question-bank-panel { height:calc(100vh - 128px); min-height:500px; display:grid; grid-template-rows:auto minmax(0,1fr); gap:14px; overflow:visible; padding:0; color:#263147; background:transparent; }
.question-bank-page-heading { min-height:54px; display:flex; align-items:center; justify-content:space-between; gap:20px; padding:0 2px; }
.question-bank-page-identity { min-width:0; display:flex; align-items:center; gap:10px; }
.question-bank-page-identity>strong { min-width:0; overflow:hidden; color:#202a3d; font-size:18px; font-weight:760; line-height:1.35; letter-spacing:-.015em; text-overflow:ellipsis; white-space:nowrap; }
.question-bank-workspace-context { flex:none; color:#5552c8; font-size:11.5px; font-weight:700; white-space:nowrap; }
.question-bank-workspace-status { flex:none; display:inline-flex; align-items:center; gap:5px; color:#687386; font-size:11.5px; font-weight:680; white-space:nowrap; }
.question-bank-workspace-status svg { color:#667085; }
.question-bank-quality-trigger { min-height:32px; display:inline-flex; align-items:center; gap:6px; padding:0 8px; border:0; border-radius:7px; color:#596579; background:transparent; font:inherit; font-size:11.5px; font-weight:700; cursor:pointer; }
.question-bank-quality-trigger svg { color:#5552c8; }
.question-bank-quality-trigger small { color:#8a94a5; font-size:10.5px; font-weight:600; }
.question-bank-quality-trigger:hover,.question-bank-quality-trigger[aria-expanded="true"] { color:#3f3b9d; background:#f0f1ff; }
.question-bank-quality-trigger:focus-visible { outline:2px solid #6366f1; outline-offset:2px; }
.question-bank-document-surface { min-width:0; min-height:0; display:grid; grid-template-rows:minmax(0,1fr); overflow:hidden; border-block:1px solid #dfe5ee; background:#fff; }
.question-bank-workspace-actions { flex:0 0 auto; display:flex; align-items:center; gap:7px; }
.question-bank-workspace-actions button { min-height:34px; display:inline-flex; align-items:center; justify-content:center; gap:6px; padding:0 10px; border:1px solid #d7dde7; border-radius:8px; color:#475569; background:#fff; font:inherit; font-size:11.5px; font-weight:700; cursor:pointer; }
.question-bank-workspace-actions button:hover { border-color:#a5b4fc; color:#4338ca; background:#fafaff; }
.question-bank-workspace-actions button:focus-visible { outline:2px solid #6366f1; outline-offset:2px; }
.question-bank-workspace-actions .question-bank-ai-action { border-color:transparent; color:#5552c8; background:transparent; }
.question-bank-workspace-actions .question-bank-back { border-color:transparent; padding-left:4px; }
.question-bank-workspace-body { min-width:0; min-height:0; display:grid; grid-template-columns:minmax(0,1fr) 260px; }
.question-bank-workspace-main { min-width:0; min-height:0; display:grid; grid-template-rows:max-content minmax(0,1fr); overflow:hidden; background:#fff; }
.question-bank-workspace-side { min-width:0; min-height:0; overflow:hidden; border-left:1px solid #e4e9f1; background:#fbfcfe; }
.question-bank-empty-state { min-height:340px; display:grid; place-content:center; justify-items:center; gap:9px; padding:28px; text-align:center; }
.question-bank-empty-state>span { width:48px; height:48px; display:grid; place-items:center; border-radius:12px; color:#5b57d9; background:#f0f1ff; }
.question-bank-empty-state>strong { color:#263147; font-size:16px; }
.question-bank-empty-state>p { max-width:430px; margin:0; color:#7a8699; font-size:11.5px; line-height:1.65; }
.question-bank-empty-state>div { display:flex; align-items:center; gap:8px; margin-top:8px; }
.question-bank-empty-state button { min-height:36px; display:inline-flex; align-items:center; gap:6px; padding:0 12px; border:1px solid #d7dde7; border-radius:8px; color:#5552c8; background:#fff; font:inherit; font-size:11.5px; font-weight:750; cursor:pointer; }
.question-bank-empty-state .question-bank-empty-import { border-color:#514bdc; color:#fff; background:#514bdc; }
.question-bank-empty-state button:focus-visible { outline:2px solid #6366f1; outline-offset:2px; }
.question-bank-panel.is-import .question-bank-workspace-body { display:block; }
.question-bank-panel.is-generate .question-bank-workspace-main { grid-template-rows:repeat(3,max-content) minmax(620px,1fr); align-content:start; gap:14px; overflow:auto; padding:18px 20px 20px; }
.question-bank-panel.is-generate .question-review-workspace { min-height:620px; border:1px solid #dfe5ee; }
.question-bank-panel.is-generate .question-bank-workspace-side :deep(.reference-tray) { min-height:100%; border:0; border-radius:0; box-shadow:none; }
.question-generation-studio { overflow:hidden; border:1px solid #dfe4ec; border-radius:14px; background:#fff; }
.question-generation-studio__header { min-height:52px; display:flex; align-items:center; justify-content:space-between; gap:12px; padding:10px 20px; }
.question-generation-studio__ai{min-height:34px;display:inline-flex;align-items:center;gap:6px;padding:0 10px;border:1px solid #d7dde7;border-radius:8px;color:#4338ca;background:#fff;font-size:12px;font-weight:750;cursor:pointer}.question-generation-studio__ai:hover:not(:disabled){border-color:#a5b4fc;background:#f8f9ff}.question-generation-studio__ai:focus-visible{outline:2px solid #6366f1;outline-offset:2px}.question-generation-studio__ai:disabled{opacity:.45;cursor:not-allowed}.question-ai-candidate{min-height:44px;display:flex;align-items:center;gap:8px;padding:0 20px;border-block:1px solid #dfe2f5;color:#4f46e5;background:#f8f8ff;outline:0}.question-ai-candidate strong{color:#3730a3;font-size:12px}.question-ai-candidate span{margin-left:auto;color:#6b7280;font-size:11px}
.question-generation-studio__published { flex:0 0 auto; display:inline-flex; align-items:center; gap:6px; color:#047857; font-size:11px; font-weight:700; }
.question-generation-flow { padding:0 20px; }
.question-generation-step { min-width:0; display:grid; grid-template-columns:132px minmax(0,1fr); align-items:start; gap:24px; margin:0; padding:18px 0; border:0; border-top:1px solid #edf0f4; }
.question-generation-step h4 { margin:0; padding:2px 0 0; color:#334155; font-size:12px; font-weight:750; line-height:1.5; }
.question-generation-scope { min-width:0; display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px; }
.question-generation-scope label { min-width:0; min-height:58px; display:flex; align-items:center; gap:10px; padding:9px 11px; border:1px solid #dfe4ec; border-radius:10px; background:#fff; cursor:pointer; transition:border-color .15s ease,background-color .15s ease; }
.question-generation-scope label:hover { border-color:#c7d2fe; background:#fafaff; }
.question-generation-scope label.active { border-color:#a5b4fc; background:#f4f5ff; }
.question-generation-scope label:only-child { max-width:300px; }
.question-generation-scope input { width:15px; height:15px; flex:0 0 auto; accent-color:#4f46e5; }
.question-generation-step label>span,.question-intelligence-grid article>span { min-width:0; display:grid; gap:2px; }
.question-generation-step label strong,.question-intelligence-grid strong { color:#334155; font-size:12px; line-height:1.4; }
.question-generation-step label small,.question-intelligence-grid small { overflow:hidden; color:#64748b; font-size:11px; line-height:1.45; text-overflow:ellipsis; }
.question-intelligence-grid { min-width:0; display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); }
.question-intelligence-grid article { min-width:0; display:grid; grid-template-columns:18px minmax(0,1fr) auto; align-items:center; gap:9px; padding:3px 20px; color:#6366f1; }
.question-intelligence-grid article:first-child { padding-left:0; }
.question-intelligence-grid article+article { border-left:1px solid #edf0f4; }
.question-intelligence-grid em { color:#4f46e5; font-size:10px; font-style:normal; font-weight:750; }
.question-generation-option-list { min-width:0; display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); }
.question-generation-toggle { min-width:0; display:flex; align-items:center; justify-content:space-between; gap:12px; padding:3px 20px; cursor:pointer; }
.question-generation-toggle:first-child { padding-left:0; }
.question-generation-toggle+.question-generation-toggle { border-left:1px solid #edf0f4; }
.question-generation-toggle input { width:16px; height:16px; flex:0 0 auto; accent-color:#4f46e5; }
.question-generation-studio>footer { display:flex; align-items:center; min-height:66px; padding:13px 20px; border-top:1px solid #edf0f4; background:#fafbfc; }
.question-bank-panel__header-action { width:100%; display:flex; align-items:center; justify-content:space-between; gap:18px; }
.question-bank-panel__header-copy { min-width:0; display:grid; gap:3px; text-align:left; }
.question-bank-panel__header-action small,.question-bank-panel__header-action span { color:#64748b; font-size:11px; line-height:1.45; }
.question-bank-panel__header-action span { color:#047857; font-weight:700; }
.question-bank-panel__header-buttons { flex:0 0 auto; display:flex; align-items:center; gap:8px; }
.question-bank-panel__header-buttons button { min-height:38px; display:inline-flex; align-items:center; justify-content:center; gap:6px; padding:0 12px; border:1px solid #d7dde7; border-radius:8px; color:#475569; background:#fff; font-size:12px; font-weight:700; cursor:pointer; transition:border-color .15s ease,background-color .15s ease; }
.question-bank-panel__header-buttons button:hover:not(:disabled) { border-color:#a5b4fc; background:#f8f9ff; }
.question-bank-panel__header-buttons button:focus-visible,.question-generation-scope label:has(input:focus-visible),.question-generation-toggle:has(input:focus-visible) { outline:2px solid #6366f1; outline-offset:2px; }
.question-bank-panel__header-buttons button:disabled { opacity:.5; cursor:not-allowed; }
.question-bank-panel__header-buttons .question-generation-primary { border-color:#4f46e5; color:#fff; background:#4f46e5; }
.question-bank-panel__header-buttons .question-generation-primary:hover:not(:disabled) { border-color:#4338ca; background:#4338ca; }
.question-quality-details { overflow:hidden; margin:0; border-bottom:1px solid #e5eaf1; background:#fafbfe; }
.question-quality-details__header { min-height:48px; display:flex; align-items:center; justify-content:space-between; gap:12px; padding:0 28px; }
.question-quality-details__header>span { display:flex; align-items:center; gap:8px; color:#5552c8; }
.question-quality-details__header strong { color:#2c374b; font-size:13px; }
.question-quality-details__header button { width:30px; height:30px; display:grid; place-items:center; border:0; border-radius:7px; color:#778397; background:transparent; cursor:pointer; }
.question-quality-details__header button:hover { color:#334155; background:#eef1f6; }
.question-quality-details__header button:focus-visible { outline:2px solid #6366f1; outline-offset:2px; }
.question-quality-details__body { display:grid; gap:0; padding:0 28px 18px; background:#fafbfe; }
.question-bank-summary { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); padding:10px 0; border-block:1px solid var(--lz-border); }
.question-bank-summary article { min-width:0; display:grid; align-content:start; gap:4px; padding:0 12px; }
.question-bank-summary article + article { border-left:1px solid var(--lz-border); }
.question-bank-summary span, .question-bank-summary small { color: var(--lz-text-muted); font-size: 10px; }
.question-bank-summary strong { color: var(--lz-text-strong); font-size: 14px; }
.question-bank-progress { display:grid; grid-template-columns:1fr auto; gap:8px 12px; padding:12px 14px; border:1px solid #bfdbfe; border-radius:10px; background:#eff6ff; }.question-bank-progress div { display:grid; gap:2px; }.question-bank-progress strong { color:#1e3a8a; font-size:12px; }.question-bank-progress span,.question-bank-progress b { color:#475569; font-size:10px; }.question-bank-progress i { grid-column:1/-1; height:6px; overflow:hidden; border-radius:999px; background:#dbeafe; }.question-bank-progress i span { display:block; width:100%; height:100%; border-radius:inherit; background:#2563eb; transform-origin:left center; transition:transform .25s ease; }.question-bank-progress[data-status="completed"],.question-bank-progress[data-status="waiting_review"] { border-color:#a7f3d0; background:#ecfdf5; }.question-bank-progress[data-status="completed"] strong,.question-bank-progress[data-status="waiting_review"] strong { color:#065f46; }.question-bank-progress[data-status="completed"] i,.question-bank-progress[data-status="waiting_review"] i { background:#d1fae5; }.question-bank-progress[data-status="completed"] i span,.question-bank-progress[data-status="waiting_review"] i span { background:#059669; }.question-bank-progress[data-status="failed"] { border-color:#fecaca; background:#fff7ed; }.question-bank-progress[data-status="failed"] strong,.question-bank-progress__error { color:#b91c1c; }.question-bank-progress__error { grid-column:1/-1; font-size:10px; }
.question-bank-progress__chapter { color:#1d4ed8; font-size:10px; }
.question-bank-progress__retry { grid-column:1/-1; justify-self:start; min-height:30px; display:inline-flex; align-items:center; gap:6px; padding:0 10px; border:1px solid #fca5a5; border-radius:8px; color:#991b1b; background:#fff; font-size:10px; font-weight:720; cursor:pointer; }.question-bank-progress__retry:hover:not(:disabled) { border-color:#dc2626; color:#fff; background:#dc2626; }.question-bank-progress__retry:disabled { opacity:.55; cursor:not-allowed; }
.assessment-profile,.assessment-matrix { display:grid; gap:10px; padding:13px 12px; border:0; border-radius:0; background:transparent; }
.assessment-profile+.assessment-matrix { border-top:1px solid #edf0f5; }
.assessment-profile header,.assessment-matrix>header { display:flex; align-items:flex-start; justify-content:space-between; gap:12px; }
.assessment-profile header div,.assessment-matrix>header div { display:grid; gap:3px; }
.assessment-profile span,.assessment-matrix span { color:var(--lz-text-muted); font-size:10px; }
.assessment-profile strong,.assessment-matrix strong { color:var(--lz-text-strong); font-size:12px; }
.assessment-profile small,.assessment-matrix small,.assessment-profile p { margin:0; color:var(--lz-text-muted); font-size:10px; line-height:1.55; }
.assessment-matrix__summary { flex:0 0 auto; text-align:right; }
.assessment-matrix__summary strong { font-size:13px; }
.assessment-matrix__group { min-width:0; display:grid; gap:7px; }
.assessment-matrix__group>header { display:flex; align-items:center; gap:7px; padding:0 2px; }
.assessment-matrix__group>header small { min-width:18px; height:18px; display:inline-flex; align-items:center; justify-content:center; padding:0 5px; border-radius:999px; color:#b45309; background:#fef3c7; font-size:9px; font-weight:750; }
.assessment-matrix__rows { display:grid; gap:6px; }
.assessment-matrix__rows article { position:relative; display:grid; grid-template-columns:minmax(0,1fr) auto auto; align-items:center; gap:10px; min-height:46px; padding:7px 9px 7px 11px; border-radius:8px; background:var(--lz-surface-muted); }
.assessment-matrix__rows article>div { min-width:0; display:grid; gap:2px; }
.assessment-matrix__rows article>div>strong { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.assessment-matrix__rows article>span { padding:3px 6px; border-radius:999px; color:#475569; background:#e2e8f0; white-space:nowrap; }
.assessment-matrix__rows article>span[data-status="covered"] { color:#047857; background:#d1fae5; }
.assessment-matrix__rows article>span[data-status="review"] { color:#b45309; background:#fef3c7; }
.assessment-matrix__rows article>span[data-status="failed"] { color:#b91c1c; background:#fee2e2; }
.assessment-matrix__rows article>span[data-status="source"],.assessment-matrix__rows article>span[data-status="missing"] { color:#b45309; background:#fef3c7; }
.assessment-matrix__rows button { min-height:34px; display:inline-flex; align-items:center; justify-content:center; gap:5px; padding:6px 9px; border:1px solid var(--lz-border); border-radius:7px; color:var(--lz-text-secondary); background:#fff; font-size:10px; cursor:pointer; }
.assessment-matrix__rows button:disabled { opacity:.55; cursor:not-allowed; }
.assessment-matrix__covered-toggle { width:100%; min-height:48px; display:flex; align-items:center; justify-content:space-between; gap:12px; padding:8px 11px; border:1px solid #a7f3d0; border-radius:9px; color:#047857; background:#ecfdf5; cursor:pointer; }
.assessment-matrix__covered-toggle>span { display:inline-flex; align-items:center; gap:7px; color:inherit; font-size:10px; }
.assessment-matrix__covered-toggle>span:last-child { color:var(--lz-brand-strong); font-weight:700; }
.assessment-matrix__covered-toggle:hover { border-color:#6ee7b7; background:#d1fae5; }
.assessment-matrix__covered-toggle:focus-visible,.assessment-matrix__menu summary:focus-visible { outline:2px solid var(--lz-brand); outline-offset:2px; }
.assessment-matrix__covered-content { display:grid; gap:9px; }
.assessment-matrix__rows--covered article { min-height:42px; padding-block:5px; background:#f8fafc; }
.assessment-matrix__menu { position:relative; }
.assessment-matrix__menu summary { width:34px; height:34px; display:grid; place-items:center; border-radius:7px; color:var(--lz-text-secondary); cursor:pointer; list-style:none; }
.assessment-matrix__menu summary::-webkit-details-marker { display:none; }
.assessment-matrix__menu summary:hover,.assessment-matrix__menu[open] summary { color:var(--lz-brand-strong); background:var(--lz-brand-soft); }
.assessment-matrix__menu>div { position:absolute; top:38px; right:0; z-index:4; min-width:112px; padding:5px; border:1px solid var(--lz-border); border-radius:8px; background:#fff; box-shadow:0 10px 24px rgba(15,23,42,.12); }
.assessment-matrix__menu>div button { width:100%; justify-content:flex-start; border:0; }
.assessment-matrix__pagination { padding:6px 2px 0; border-top:1px solid var(--lz-border); }
.assessment-matrix__empty { min-height:54px; display:grid; place-items:center; color:var(--lz-text-muted); font-size:10px; }
.question-browser { min-width:0; min-height:0; display:grid; grid-template-columns:310px minmax(0,1fr); overflow:hidden; background:#fff; }
.question-index { min-width:0; min-height:0; display:grid; grid-template-rows:auto minmax(0,1fr) auto; overflow:hidden; border-right:1px solid #e3e8f0; background:#fbfcfe; }
.question-index__toolbar { display:grid; gap:12px; padding:15px 14px 13px; border-bottom:1px solid #e5eaf1; background:#fff; }
.question-browser__identity { min-width:0; display:flex; align-items:baseline; gap:8px; }
.question-browser__identity strong { color:#253047; font-size:13.5px; font-weight:760; }
.question-browser__identity small { color:#8a94a5; font-size:11px; }
.question-browser__controls { min-width:0; display:grid; grid-template-columns:minmax(0,1fr) 92px; gap:7px; }
.question-browser__controls label { min-width:0; display:flex; align-items:center; gap:7px; padding:0 9px; border:1px solid #dce2eb; border-radius:8px; color:#7b8798; background:#fff; }
.question-browser__controls label:focus-within { border-color:#8f8ce9; box-shadow:0 0 0 3px rgba(91,87,232,.09); }
.question-browser__controls input { min-width:0; width:100%; height:34px; border:0; outline:0; color:#253047; background:transparent; font-size:11.5px; }
.question-browser__controls select { min-width:0; height:36px; padding:0 25px 0 9px; border:1px solid #dce2eb; border-radius:8px; color:#4b576b; background:#fff; font-size:11px; }
.question-browser__controls select:focus-visible { outline:2px solid #6366f1; outline-offset:2px; }
.question-review-list { min-height:0; overflow:auto; scrollbar-width:thin; scrollbar-color:#cbd3df transparent; }
.question-review-item { border-bottom:1px solid #e7ebf1; background:transparent; }
.question-review-item__summary { width:100%; min-height:76px; display:grid; grid-template-columns:27px minmax(0,1fr) auto; align-items:start; gap:9px; padding:11px 11px 10px 12px; border:0; color:inherit; background:transparent; text-align:left; cursor:pointer; transition:background-color .15s ease,color .15s ease; }
.question-review-item__summary:hover { background:#f4f5fb; }
.question-review-item__summary:focus-visible { position:relative; z-index:1; outline:2px solid #6366f1; outline-offset:-2px; }
.question-review-item.is-expanded .question-review-item__summary { background:#eef0ff; }
.question-review-item__number { width:24px; height:24px; display:grid; place-items:center; border-radius:6px; color:#7b8798; background:#f0f2f6; font-size:9.5px; font-weight:780; font-variant-numeric:tabular-nums; }
.question-review-item.is-expanded .question-review-item__number { color:#4338ca; background:#fff; box-shadow:0 1px 4px rgba(67,56,202,.1); }
.question-review-item__question { min-width:0; display:grid; gap:5px; }
.question-review-item__preview { display:-webkit-box; overflow:hidden; color:#2d374c; font-size:11.5px; font-weight:650; line-height:1.48; -webkit-box-orient:vertical; -webkit-line-clamp:2; }
.question-review-item__question small { overflow:hidden; color:#7a8699; font-size:9.5px; font-weight:580; line-height:1.4; text-overflow:ellipsis; white-space:nowrap; }
.question-review-item__status { display:inline-flex; align-items:center; gap:5px; color:#596579; font-size:9.5px; font-weight:700; white-space:nowrap; }
.question-review-item__status i { width:6px; height:6px; flex:0 0 auto; border-radius:999px; background:#22a06b; }
.question-review-item__status[data-status="needs_review"] { color:#9a6700; }
.question-review-item__status[data-status="needs_review"] i { background:#f0a202; }
.question-review-item__status[data-status="rejected"] { color:#c9372c; }
.question-review-item__status[data-status="rejected"] i { background:#e2483d; }
.question-browser__pagination { padding:9px 10px; border-top:1px solid #e5eaf1; background:#fff; }
.question-browser__pagination :deep(.compact-pagination__range) { font-size:9.5px; }
.question-reader { min-width:0; min-height:0; display:grid; grid-template-rows:58px minmax(0,1fr) 62px; overflow:hidden; padding:0; border:0; background:#f5f7fa; }
.question-reader__header { min-width:0; display:flex; align-items:center; justify-content:space-between; gap:18px; padding:0 18px 0 22px; border-bottom:1px solid #e3e8f0; background:#fff; }
.question-reader__header>div { min-width:0; display:flex; align-items:center; gap:11px; }
.question-reader__header>div>strong { color:#344054; font-size:11px; font-weight:700; }
.question-reader__header nav { display:flex; align-items:center; gap:4px; }
.question-reader__header nav button { width:32px; height:32px; display:grid; place-items:center; border:1px solid transparent; border-radius:7px; color:#667085; background:transparent; cursor:pointer; }
.question-reader__header nav button:hover:not(:disabled) { color:#4338ca; background:#eef0ff; }
.question-reader__header nav button:focus-visible { outline:2px solid #6366f1; outline-offset:2px; }
.question-reader__header nav button:disabled { opacity:.3; cursor:not-allowed; }
.question-reader__scroll { min-height:0; overflow:auto; padding:24px 28px 40px; scrollbar-width:thin; scrollbar-color:#cbd3df transparent; }
.question-sheet,.question-answer-panel,.question-generation-audit,.question-review-decision { width:min(760px,100%); margin:0 auto; }
.question-sheet { overflow:hidden; border:1px solid #dfe5ed; border-radius:13px; background:#fff; box-shadow:0 10px 28px rgba(30,41,59,.07); }
.question-sheet__meta { min-height:43px; display:flex; align-items:center; flex-wrap:wrap; gap:7px 14px; padding:0 22px; border-bottom:1px solid #edf0f4; color:#748095; font-size:10px; }
.question-sheet__meta span:last-child { margin-left:auto; color:#b45309; font-weight:700; }
.question-sheet__meta span[data-status="passed"] { color:#047857; }
.question-sheet__section { padding:20px 24px 4px; }
.question-sheet__section+.question-sheet__section { padding-top:16px; }
.question-sheet__section>small { display:block; margin-bottom:9px; color:#6b6fc2; font-size:10px; font-weight:780; }
.question-sheet__section :deep(.markdown-renderer) { color:#243047; font-size:14px; line-height:1.82; }
.question-sheet__section :deep(.markdown-renderer > :first-child) { margin-top:0; }
.question-sheet__section :deep(.markdown-renderer > :last-child) { margin-bottom:0; }
.question-sheet__stimulus { margin:18px 24px 0; padding:14px 16px; border-radius:9px; background:#f7f8fb; }
.question-sheet__task { padding-bottom:20px; }
.question-sheet__options { display:grid; gap:9px; margin:0; padding:2px 24px 22px; list-style:none; }
.question-sheet__options li { min-width:0; display:grid; grid-template-columns:28px minmax(0,1fr); align-items:start; gap:10px; padding:10px 12px; border:1px solid #e1e6ed; border-radius:9px; color:#344054; background:#fbfcfe; }
.question-sheet__options li>b { width:25px; height:25px; display:grid; place-items:center; border-radius:6px; color:#5552c8; background:#ececff; font-size:11px; }
.question-sheet__options :deep(.markdown-renderer) { font-size:12.5px; line-height:1.65; }
.question-sheet__options :deep(.markdown-renderer > :first-child) { margin-top:0; }
.question-sheet__options :deep(.markdown-renderer > :last-child) { margin-bottom:0; }
.question-sheet__requirements { display:grid; gap:7px; padding:14px 24px 18px; border-top:1px solid #edf0f4; color:#667085; background:#fbfcfe; font-size:10.5px; line-height:1.65; }
.question-sheet__requirements strong { color:#344054; font-size:11px; }
.question-sheet__requirements p,.question-sheet__requirements ul { max-width:72ch; margin:0; }
.question-sheet__requirements ul { display:grid; gap:3px; padding-left:18px; }
.question-answer-panel { display:grid; gap:13px; margin-top:16px; padding:18px 20px; border:1px solid #dfe5ed; border-radius:12px; background:#fff; }
.question-answer-panel>header { display:flex; align-items:center; justify-content:space-between; gap:14px; }
.question-answer-panel>header>div { display:flex; align-items:baseline; gap:8px; }
.question-answer-panel>header strong { color:#29354b; font-size:12.5px; }
.question-answer-panel>header span { color:#8993a4; font-size:9.5px; }
.question-review-item__solution { min-height:32px; display:inline-flex; align-items:center; gap:6px; padding:0 9px; border:1px solid #d8deea; border-radius:7px; color:#4f46e5; background:#fff; font-size:10.5px; font-weight:720; cursor:pointer; }
.question-review-item__solution:hover:not(:disabled) { border-color:#a5b4fc; background:#f7f7ff; }
.question-review-item__solution:focus-visible { outline:2px solid #6366f1; outline-offset:2px; }
.question-answer-panel__locked { min-height:56px; display:flex; align-items:center; gap:9px; padding:0 2px; color:#7a8699; font-size:10.5px; line-height:1.55; }
.question-answer-panel__locked svg { color:#6b6fc2; }
.question-solution-diff { display:grid; gap:11px; }
.question-solution-diff__worked { min-width:0; display:grid; gap:8px; padding:14px 15px; border-radius:9px; background:#f7f9fc; }
.question-solution-diff strong { color:#475467; font-size:10.5px; }
.question-solution-diff p,.question-solution-diff li { margin:0; color:#344054; font-size:11px; line-height:1.68; }
.question-solution-diff ol,.question-solution-diff ul { display:grid; gap:5px; margin:0; padding-left:20px; }
.question-solution-diff pre { max-height:220px; overflow:auto; margin:0; padding:10px 11px; border:1px solid #e4e8ef; border-radius:8px; color:#344054; background:#fff; font:10px/1.6 ui-monospace,SFMono-Regular,Consolas,monospace; white-space:pre-wrap; overflow-wrap:anywhere; }
.question-solution-diff__analysis { display:grid; gap:6px; }
.question-solution-diff__validation { display:grid; gap:8px; padding:1px 2px; }
.question-solution-diff__validation summary { color:#5552c8; font-size:10.5px; font-weight:720; cursor:pointer; }
.question-solution-diff__validation[open] summary { margin-bottom:6px; }
.question-generation-audit { margin-top:16px; padding:0; border:1px solid #dfe5ed; border-radius:10px; background:#fff; }
.question-generation-audit>summary { min-height:43px; display:flex; align-items:center; justify-content:space-between; gap:10px; padding:0 13px; color:#475467; font-size:10.5px; font-weight:720; cursor:pointer; }
.question-generation-audit>summary small { color:#8a94a5; font:9px/1.4 ui-monospace,SFMono-Regular,Consolas,monospace; }
.question-generation-audit[open] { padding-bottom:12px; }
.question-generation-audit[open]>summary { border-bottom:1px solid #edf0f4; }
.question-generation-audit__grid,.question-generation-audit>p { margin-inline:12px; }
.question-review-decision { margin-top:16px; }
.question-review-decision label { display:grid; gap:7px; }
.question-review-decision label>span { color:#475467; font-size:10.5px; font-weight:720; }
.question-review-decision textarea { min-height:70px; padding:10px 11px; border:1px solid #d8dee8; border-radius:9px; outline:0; resize:vertical; color:#344054; background:#fff; font:inherit; font-size:11px; line-height:1.6; }
.question-review-decision textarea:focus { border-color:#8f8ce9; box-shadow:0 0 0 3px rgba(91,87,232,.09); }
.question-reader__footer { min-width:0; display:flex; align-items:center; justify-content:space-between; gap:14px; padding:9px 18px 9px 22px; border-top:1px solid #dfe5ed; background:#fff; }
.question-reader__paper-select { display:flex; align-items:center; gap:7px; color:#475467; font-size:10.5px; font-weight:700; cursor:pointer; }
.question-reader__paper-select input { width:15px; height:15px; accent-color:#4f46e5; }
.question-reader__paper-select.disabled { opacity:.45; cursor:not-allowed; }
.question-reader__actions { min-width:0; display:flex; align-items:center; justify-content:flex-end; gap:7px; }
.question-reader__actions button { min-height:34px; display:inline-flex; align-items:center; justify-content:center; gap:6px; padding:0 10px; border-radius:8px; font-size:10.5px; font-weight:730; cursor:pointer; }
.question-reader__actions button:focus-visible { outline:2px solid #6366f1; outline-offset:2px; }
.question-reader__actions button:disabled { opacity:.5; cursor:not-allowed; }
.question-reader__compose { border:1px solid #c7d2fe; color:#4338ca; background:#eef2ff; }
.question-review-item__reject { border:1px solid #fecaca; color:#b42318; background:#fff; }
.question-review-item__reject:hover:not(:disabled) { border-color:#fca5a5; background:#fff7f7; }
.question-review-item__approve { border:1px solid #514bdc; color:#fff; background:#514bdc; box-shadow:0 5px 14px rgba(81,75,220,.16); }
.question-review-item__approve:hover:not(:disabled) { background:#4338ca; }
.question-bank-panel__state, .question-bank-panel__empty { min-height: 64px; display: flex; align-items: center; justify-content: center; gap: 8px; color: var(--lz-text-muted); font-size: 12px; }
.question-bank-panel__state--error { min-height:auto; justify-content:flex-start; padding:10px 12px; border:1px solid #fed7aa; border-radius:10px; color:#9a3412; background:#fff7ed; }
.question-bank-panel__empty { flex-direction: column; text-align: center; }
.question-bank-panel__empty strong { color: var(--lz-text-strong); }
.question-bank-panel__empty span { max-width: 420px; font-size: 11px; }
.visually-hidden { position:absolute; width:1px; height:1px; overflow:hidden; clip:rect(0 0 0 0); clip-path:inset(50%); white-space:nowrap; }
.question-generation-audit { display:grid; gap:8px; }
.question-generation-audit>header { display:flex; align-items:center; justify-content:space-between; gap:10px; }
.question-generation-audit>header strong { color:#1e3a5f; font-size:11px; }
.question-generation-audit>header small { color:#64748b; font:9px/1.4 ui-monospace,SFMono-Regular,Consolas,monospace; }
.question-generation-audit__grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:6px; }
.question-generation-audit__grid span { display:flex; align-items:center; justify-content:space-between; gap:8px; padding:6px 8px; border-radius:7px; color:#64748b; background:#fff; font-size:9px; }
.question-generation-audit__grid b { color:#334155; font-weight:700; }
.question-generation-audit__grid b[data-status="passed"] { color:#047857; }
.question-generation-audit__grid b[data-status="warning"] { color:#b45309; }
.question-generation-audit__grid b[data-status="failed"] { color:#b91c1c; }
.question-generation-audit>p { margin:0 12px; color:#b45309; font:9px/1.5 ui-monospace,SFMono-Regular,Consolas,monospace; overflow-wrap:anywhere; }
.spin { animation: question-bank-spin .9s linear infinite; }
@keyframes question-bank-spin { to { transform: rotate(360deg); } }
@media (max-width: 900px) { .question-review-item__summary-main { grid-template-columns:auto minmax(0,1fr); }.question-review-item__meta { grid-column:1/-1; max-width:none; } }
@media (max-width: 720px) { .question-bank-page-heading { min-height:44px; align-items:flex-start; flex-direction:column; gap:8px; }.question-bank-page-identity { width:100%; }.question-bank-workspace-status { margin-left:auto; font-size:0; }.question-bank-workspace-actions { width:100%; flex-wrap:wrap; justify-content:flex-end; }.question-generation-studio__header { align-items:flex-start; }.question-generation-flow { padding-inline:16px; }.question-generation-step { grid-template-columns:1fr; gap:10px; }.question-generation-scope,.question-intelligence-grid,.question-generation-option-list { grid-template-columns:1fr; }.question-intelligence-grid article,.question-generation-toggle { padding:8px 0; }.question-intelligence-grid article+article,.question-generation-toggle+.question-generation-toggle { border-top:1px solid #edf0f4; border-left:0; }.question-generation-studio>footer { padding-inline:16px; }.question-bank-panel__header-action { align-items:stretch; flex-direction:column; gap:10px; }.question-bank-panel__header-buttons { width:100%; flex-wrap:wrap; }.question-bank-panel__header-buttons button { flex:1; }.question-bank-summary { grid-template-columns:repeat(2,minmax(0,1fr)); padding:0; }.question-bank-summary article { padding:9px 10px; }.question-bank-summary article + article { border-left:0; }.question-bank-summary article:nth-child(even) { border-left:1px solid var(--lz-border); }.question-bank-summary article:nth-child(n+3) { border-top:1px solid var(--lz-border); }.assessment-matrix>header { align-items:flex-start; flex-direction:column; }.assessment-matrix__summary { text-align:left; }.assessment-matrix__rows article { grid-template-columns:minmax(0,1fr) auto auto; }.assessment-matrix__group--issues .assessment-matrix__rows article { grid-template-columns:1fr auto; }.assessment-matrix__group--issues .assessment-matrix__rows article>button { grid-column:1/-1; justify-self:start; }.assessment-matrix__covered-toggle { align-items:flex-start; flex-direction:column; }.assessment-matrix__pagination { grid-template-columns:1fr; justify-items:start; }.assessment-matrix__page-buttons { max-width:100%; flex-wrap:wrap; }.question-solution-diff { grid-template-columns:1fr; }.question-browser>header,.question-browser__controls { align-items:stretch; flex-direction:column; }.question-browser__controls label { min-width:0; }.question-review-item__summary { grid-template-columns:1fr; gap:8px; }.question-review-item__summary-action { justify-content:space-between; }.question-review-item__preview { white-space:normal; display:-webkit-box; overflow:hidden; -webkit-box-orient:vertical; -webkit-line-clamp:2; } }
@media (max-width: 720px) { .exam-paper-bar { align-items:stretch; flex-direction:column; }.exam-paper-bar__actions { justify-content:space-between; }.exam-paper-bar__actions>span { max-width:160px; } }
</style>
