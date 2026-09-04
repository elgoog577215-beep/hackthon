<template>
  <section
    class="practice-workspace"
    :class="{ 'has-external-view-switch': props.hideViewSwitch }"
    :aria-busy="workspace.loading"
  >
    <header v-if="!props.hideViewSwitch" class="question-book-context">
      <div class="question-book-context__copy">
        <span>{{ practiceScopeLabel }}</span>
        <strong><MathText :content="currentQuestion?.learning_objective || currentNodeLabel" /></strong>
      </div>

      <nav class="question-book-views" :aria-label="t('courseWorkspace.practice.views', '练习视图')">
        <button :class="{ active: practiceView === 'current' }" @click="selectView('current')">
          {{ t('courseWorkspace.practice.current', '当前练习') }}
        </button>
        <button :class="{ active: practiceView === 'history' }" @click="openHistory('all')">
          {{ t('courseWorkspace.practice.history', '练习历史') }}
        </button>
        <button :class="{ active: practiceView === 'needs_review' }" @click="openHistory('needs_review')">
          {{ t('courseWorkspace.practice.needsReview', '错题本') }}
        </button>
      </nav>

      <div v-if="questions.length" class="question-book-context__state">
        <span class="practice-selection-policy">
          <Sparkles :size="13" />
          {{ t('courseWorkspace.practice.smartComposition', '智能编排') }}
        </span>
        <strong v-if="practiceView === 'current'" class="practice-progress">
          {{ workspace.currentQuestionIndex + 1 }} / {{ questions.length }}
        </strong>
      </div>
    </header>

    <section v-if="workflowActive" class="workflow-band" :data-phase="workflowPhase">
      <div>
        <span>{{ workflowPhaseLabel }}</span>
        <strong><MathText :content="workflowHeadline" /></strong>
      </div>
      <MathText v-if="workflowHypothesis" tag="p" :content="workflowHypothesis" />
    </section>

    <div v-if="workspace.loading" class="practice-empty">
      <LoaderCircle :size="22" class="animate-spin" />
      <span>{{ t('courseWorkspace.practice.loading', '正在恢复练习') }}</span>
    </div>

    <template v-else-if="practiceView === 'current'">
      <div v-if="workspace.taskResumeError" class="practice-empty workflow-result warning">
        <CircleAlert :size="30" />
        <strong>{{ t('courseWorkspace.practiceRuntime.resumeUnavailableTitle', '原学习任务已经发生变化') }}</strong>
        <span>{{ t('courseWorkspace.practiceRuntime.resumeUnavailableBody', '系统没有打开其他题目。请返回课程，按最新学习状态重新选择下一步。') }}</span>
      </div>

      <div v-else-if="workflowPhase === 'resolved'" class="practice-empty workflow-result">
        <CheckCircle2 :size="30" />
        <strong>{{ t('courseWorkspace.practice.workflow.resolvedTitle', '本次卡点已经通过独立复验') }}</strong>
        <span>{{ t('courseWorkspace.practice.workflow.resolvedBody', '诊断案例已结案，可以返回原课程目标继续学习。') }}</span>
        <button class="primary-command" @click="resumeCoursePractice">
          <ArrowRight :size="16" />
          {{ t('courseWorkspace.practice.workflow.resume', '返回课程练习') }}
        </button>
      </div>

      <div v-else-if="workflowPhase === 'needs_support'" class="practice-empty workflow-result warning">
        <CircleAlert :size="30" />
        <strong>{{ t('courseWorkspace.practice.workflow.needsSupportTitle', '当前证据不足以继续自动补救') }}</strong>
        <span>{{ t('courseWorkspace.practice.workflow.needsSupportBody', '记录已经保留，可以让 AI 老师结合完整过程进一步判断。') }}</span>
        <button class="primary-command" @click="escalateToTeacher">
          <MessageCircleQuestion :size="16" />
          {{ t('courseWorkspace.practice.askTeacher', '问老师') }}
        </button>
      </div>

      <div v-else-if="!currentQuestion" class="question-book-empty">
        <section class="question-book-empty__intro">
          <span class="question-book-empty__icon" aria-hidden="true">
            <CircleAlert v-if="workspace.practice?.practice_availability?.status === 'blocked'" :size="23" />
            <ClipboardCheck v-else :size="23" />
          </span>
          <div>
            <small>{{ t('questionBook.readyWhenNeeded', '需要时再生成') }}</small>
            <strong>{{ canRebuildQuestionBank ? t('questionBook.emptyTitle', '这里还没有题目') : emptyState.title }}</strong>
            <p>{{ canRebuildQuestionBank
              ? t('questionBook.emptyBody', '课程默认不生成题目。选择范围后，系统会结合课程目标自动出题。')
              : emptyState.body }}</p>
          </div>
        </section>

        <section v-if="canRebuildQuestionBank" class="question-bank-rebuild">
          <div class="question-bank-rebuild__heading">
            <strong>{{ t('questionBook.generateNow', '开始出题') }}</strong>
            <span>{{ t('questionBook.generationScope', '出题范围') }}</span>
          </div>
          <div class="question-bank-rebuild__scope" role="group" :aria-label="t('questionBook.generationScope', '出题范围')">
            <button type="button" :class="{ active: generationScope === 'node' }" @click="generationScope = 'node'">
              {{ t('questionBook.currentSection', '当前小节') }}
            </button>
            <button type="button" :class="{ active: generationScope === 'course' }" @click="generationScope = 'course'">
              {{ t('questionBook.entireCourse', '全课程') }}
            </button>
          </div>
          <label class="question-bank-rebuild__retrieval">
            <input v-model="generationRetrievalEnabled" type="checkbox" />
            <span>
              <strong>{{ t('questionBook.useRetrieval', '补充外部可靠来源') }}</strong>
              <small>{{ t('questionBook.useRetrievalHelp', '适合需要时效资料或更多案例的题目') }}</small>
            </span>
          </label>
          <button
            type="button"
            class="primary-command question-bank-rebuild__submit"
            data-testid="rebuild-question-bank"
            :disabled="questionBankRebuilding"
            @click="rebuildQuestionBank"
          >
            <LoaderCircle v-if="questionBankRebuilding" :size="16" class="animate-spin" />
            <Sparkles v-else :size="16" />
            {{ questionBankRebuilding
              ? t('questionBook.generating', '正在生成题目')
              : t('questionBook.generate', '生成题目') }}
          </button>
          <p class="question-bank-rebuild__help">
            {{ t('questionBook.generateHelp', '难度和题型会根据课程目标自动匹配；已有作答记录会保留。') }}
          </p>
          <div
            v-if="questionBankRebuildJob"
            class="question-bank-rebuild__progress"
            role="status"
            aria-live="polite"
          >
            <span>{{ questionBankRebuildJob.message || emptyState.title }}</span>
            <strong>{{ questionBankRebuildJob.progress }}%</strong>
            <i><b :style="{ transform: `scaleX(${questionBankRebuildJob.progress / 100})` }"></b></i>
          </div>
          <small v-if="questionBankRebuildError" class="question-bank-rebuild__error">
            {{ questionBankRebuildError }}
          </small>
        </section>
      </div>

      <main v-else class="question-stage">
        <article class="question-content">
          <section v-if="workspace.targetedRetryContext" class="targeted-retry-context">
            <RotateCcw :size="17" aria-hidden="true" />
            <div>
              <strong>{{ t('courseWorkspace.targetedRetry.title', '针对错题再练') }}</strong>
              <p>{{ workspace.targetedRetryContext.usedAlternateQuestion
                ? t('courseWorkspace.targetedRetry.alternateHint', '已优先选择同一易错点或能力的另一道正式练习')
                : t('courseWorkspace.targetedRetry.sameHint', '当前没有同能力的替代题，继续用原题巩固') }}</p>
            </div>
          </section>
          <section v-if="workflowPhase === 'remediation' && remediationUnit" class="remediation-context">
            <strong><MathText :content="remediationUnit.remediation_objective" /></strong>
            <MathText tag="p" :content="remediationUnit.micro_explanation" />
            <MathText tag="small" :content="remediationUnit.worked_contrast" />
          </section>
          <div class="question-meta">
            <div>
              <span>{{ questionTypeLabel }}</span>
              <span>{{ saveStateLabel }}</span>
            </div>
            <button
              type="button"
              class="refresh-question-command"
              data-testid="refresh-practice-question"
              :disabled="!canRefreshQuestion || questionRefreshing || submitting"
              @click="refreshQuestion"
            >
              <LoaderCircle v-if="questionRefreshing" :size="14" class="animate-spin" />
              <RefreshCw v-else :size="14" />
              {{ questionRefreshing
                ? t('courseWorkspace.practice.refreshing', '正在换题')
                : t('courseWorkspace.practice.refreshQuestion', '换一题') }}
            </button>
          </div>
          <section
            class="question-prompt"
            data-testid="practice-question-markdown"
            :aria-label="t('courseWorkspace.practice.questionContent', '题目内容')"
          >
            <div
              v-if="currentQuestionMarkdown.stimulus"
              class="question-stimulus"
              data-testid="practice-question-stimulus"
            >
              <header>
                <strong>{{ t('courseWorkspace.practice.questionStimulus', '题目材料') }}</strong>
              </header>
              <MarkdownRenderer
                :content="currentQuestionMarkdown.stimulus"
                :enable-code-run="false"
              />
            </div>

            <div class="question-task" data-testid="practice-question-task">
              <header>
                <strong>{{ t('courseWorkspace.practice.answerTask', '作答任务') }}</strong>
                <span>{{ t('courseWorkspace.practice.answerTaskHint', '先明确要求，再开始作答') }}</span>
              </header>
              <MarkdownRenderer
                :content="currentQuestionMarkdown.task"
                :enable-code-run="false"
              />
            </div>

            <details
              v-if="currentQuestionMarkdown.material"
              :key="currentQuestion?.revision_id || currentQuestion?.asset_id || currentQuestion?.question_id"
              class="question-material"
              data-testid="practice-question-material"
            >
              <summary>
                <span class="question-material__icon" aria-hidden="true">
                  <BookOpenCheck :size="17" />
                </span>
                <span class="question-material__copy">
                  <strong>{{ t('courseWorkspace.practice.referenceMaterial', '参考材料') }}</strong>
                  <small>{{ t('courseWorkspace.practice.referenceMaterialHint', '课程原文较长，需要时再展开查看') }}</small>
                </span>
                <span class="question-material__action" aria-hidden="true">
                  <span class="expand-label">{{ t('courseWorkspace.practice.expandMaterial', '展开材料') }}</span>
                  <span class="collapse-label">{{ t('courseWorkspace.practice.collapseMaterial', '收起材料') }}</span>
                  <ChevronDown :size="16" />
                </span>
              </summary>
              <div class="question-material__body">
                <MarkdownRenderer
                  :content="currentQuestionMarkdown.material"
                  :enable-code-run="false"
                />
              </div>
            </details>
          </section>

          <div v-if="workspace.currentAttempt?.status === 'invalidated'" class="state-notice danger">
            <CircleAlert :size="18" />
            <span>{{ t('courseWorkspace.practice.invalidated', '题目版本已经更新，本次草稿已保留，请重新开始') }}</span>
          </div>

          <PracticeAnswerRenderer
            v-model="workspace.currentDraft"
            :contract="currentQuestion.input_contract"
            :options="currentQuestion.options || []"
            :question-type="currentQuestion.question_type"
            :disabled="answerLocked"
            :placeholder="answerPlaceholder"
          />

          <section
            v-if="hintDisplayRows.length"
            class="hint-results"
            aria-live="polite"
            :aria-busy="hintLoadingLevel !== null"
          >
            <div
              v-for="hint in hintDisplayRows"
              :key="hint.loading ? `loading-${hint.level}` : `hint-${hint.level}`"
              class="hint-result"
              :class="{ loading: hint.loading }"
              :data-testid="hint.loading ? 'hint-loading-placeholder' : undefined"
              :aria-live="hint.loading ? 'polite' : undefined"
              :aria-busy="hint.loading ? 'true' : undefined"
            >
              <span>{{ t('courseWorkspace.practice.hintLevel', '{level} 级提示').replace('{level}', String(hint.level)) }}</span>
              <p>
                <LoaderCircle v-if="hint.loading" :size="15" class="animate-spin hint-loading-icon" aria-hidden="true" />
                <MathText :content="hint.content" />
              </p>
            </div>
          </section>

          <section
            v-if="guidanceTurns.length || guidanceOpen"
            class="guidance-panel"
            data-testid="guidance-panel"
            aria-live="polite"
          >
            <header class="guidance-heading">
              <MessageCircleQuestion :size="16" aria-hidden="true" />
              <strong>{{ t('courseWorkspace.practice.guidanceTitle', 'AI 老师引导') }}</strong>
              <small>{{ t('courseWorkspace.practice.guidanceEvidenceNote', '引导只提问、不给答案；用得越多，本次作答作为独立掌握证据越弱。') }}</small>
            </header>

            <div
              v-for="(turn, index) in guidanceTurns"
              :key="`turn-${index}`"
              class="guidance-turn"
              :class="turn.role"
            >
              <span class="guidance-role">
                {{ turn.role === 'student'
                  ? t('courseWorkspace.practice.guidanceYou', '你')
                  : t('courseWorkspace.practice.guidanceTeacher', 'AI 老师') }}
              </span>
              <MathText tag="p" :content="turn.text" />
              <small
                v-if="turn.role === 'assistant' && turn.status && turn.status !== 'ok'"
                class="guidance-degraded"
                data-testid="guidance-degraded"
              >
                {{ guidanceStatusNote(String(turn.status)) }}
              </small>
            </div>

            <div class="guidance-compose">
              <textarea
                v-model="guidanceMessage"
                class="guidance-input"
                :disabled="answerLocked || guidanceSending || guidanceExhausted"
                :placeholder="t('courseWorkspace.practice.guidancePlaceholder', '说说你现在卡在哪一步，以及你用了什么条件')"
                data-testid="guidance-input"
              />
              <button
                type="button"
                class="text-command"
                :disabled="answerLocked || guidanceSending || guidanceExhausted || !guidanceMessage.trim()"
                data-testid="guidance-send"
                @click="sendGuidance"
              >
                <LoaderCircle v-if="guidanceSending" :size="15" class="animate-spin" aria-hidden="true" />
                {{ guidanceSending
                  ? t('courseWorkspace.practice.guidanceSending', '正在思考…')
                  : t('courseWorkspace.practice.guidanceSend', '继续追问') }}
              </button>
            </div>
            <small v-if="guidanceExhausted" class="guidance-degraded" data-testid="guidance-exhausted">
              {{ t('courseWorkspace.practice.guidanceExhausted', '本题引导轮次已用完，请先自己往下写一步。') }}
            </small>
          </section>

          <section v-if="workspace.practiceResult" class="practice-feedback" :data-passed="workspace.practiceResult.passed">
            <div class="feedback-heading">
              <CheckCircle2 v-if="workspace.practiceResult.passed" :size="21" />
              <Clock3 v-else-if="workspace.practiceResult.status === 'pending_review'" :size="21" />
              <CircleAlert v-else :size="21" />
              <strong>{{ feedbackTitle }}</strong>
              <span v-if="workspace.practiceResult.score !== null && workspace.practiceResult.score !== undefined">{{ workspace.practiceResult.score }}</span>
            </div>
            <MathText tag="p" :content="workspace.practiceResult.feedback" />
            <div v-if="workspace.practiceResult.rubric_results?.length" class="rubric-list">
              <div v-for="item in workspace.practiceResult.rubric_results" :key="item.criterion">
                <component :is="item.met ? CheckCircle2 : Circle" :size="15" />
                <MathText :content="item.criterion" />
                <MathText tag="small" :content="item.feedback" />
              </div>
            </div>
            <section
              v-if="stepwiseJudgement?.steps?.length"
              class="stepwise-judgement"
              data-testid="stepwise-judgement"
            >
              <header>
                <strong>{{ t('courseWorkspace.practice.stepwiseResultTitle', '逐步判定') }}</strong>
                <span v-if="stepwiseJudgement.first_flawed_step_index">
                  {{ t('courseWorkspace.practice.stepwiseFirstFlawed', '推导从第 {index} 步开始出问题')
                    .replace('{index}', String(stepwiseJudgement.first_flawed_step_index)) }}
                </span>
                <span v-else>
                  {{ t('courseWorkspace.practice.stepwiseNoFlaw', '没有发现出错的步骤') }}
                </span>
              </header>
              <div
                v-for="step in stepwiseJudgement.steps"
                :key="`judged-${step.step_index}`"
                class="stepwise-verdict"
                :data-verdict="step.verdict"
              >
                <span class="verdict-index">
                  {{ t('courseWorkspace.practice.stepLabel', '第 {index} 步').replace('{index}', String(step.step_index)) }}
                </span>
                <span class="verdict-tag">{{ stepVerdictLabel(step.verdict) }}</span>
                <MathText v-if="step.comment" tag="small" :content="step.comment" />
              </div>
            </section>
            <section v-if="answerDiagnosis" class="answer-diagnosis">
              <header>
                <strong>{{ t('courseWorkspace.practiceAnalysis.title', '题目解析与本次判断') }}</strong>
                <span v-if="answerDiagnosis.diagnosis?.library_fit">
                  {{ analysisFitLabel }}
                </span>
              </header>
              <dl>
                <div>
                  <dt>{{ t('courseWorkspace.practiceAnalysis.taskGoal', '这道题在考什么') }}</dt>
                  <dd><MathText :content="answerDiagnosis.question_understanding?.task_goal" /></dd>
                </div>
                <div v-if="answerDiagnosis.student_response?.approach">
                  <dt>{{ studentResponseEvidenceLabel }}</dt>
                  <dd><MathText :content="answerDiagnosis.student_response.approach" /></dd>
                </div>
                <div v-if="answerDiagnosis.student_response?.behavior_gap">
                  <dt>{{ t('courseWorkspace.practiceAnalysis.behaviorGap', '当前最关键的差距') }}</dt>
                  <dd><MathText :content="answerDiagnosis.student_response.behavior_gap" /></dd>
                </div>
              </dl>
              <div v-if="diagnosisTags.length" class="diagnosis-tags">
                <span v-for="tag in diagnosisTags" :key="`${tag.kind}-${tag.id}`" :data-kind="tag.kind">
                  {{ tag.name }}
                </span>
              </div>
              <ul v-if="answerDiagnosis.diagnosis?.issues?.length" class="diagnosis-issues">
                <li v-for="issue in answerDiagnosis.diagnosis.issues" :key="issue.issue_id">
                  <strong><MathText :content="issue.title" /></strong>
                  <MathText :content="issue.what_happened" />
                </li>
              </ul>
              <MathText tag="p" class="diagnosis-summary" :content="answerDiagnosis.student_feedback?.summary" />
              <div class="diagnosis-next">
                <span>{{ t('courseWorkspace.practiceAnalysis.nextAction', '下一步只做这一件事') }}</span>
                <strong><MathText :content="answerDiagnosis.student_feedback?.next_action" /></strong>
              </div>
            </section>
            <small>{{ evidenceLabel }}</small>
          </section>

          <section v-if="workspace.revealedSolution" class="solution-result">
            <strong>{{ t('courseWorkspace.practice.solutionTitle', '完整解析') }}</strong>
            <MathText
              v-if="workspace.revealedSolution.summary || workspace.revealedSolution.guidance"
              tag="p"
              :content="workspace.revealedSolution.summary || workspace.revealedSolution.guidance"
            />
            <div v-if="workspace.revealedSolution.steps?.length" class="solution-steps">
              <h4>{{ t('courseWorkspace.practice.solutionSteps', '解题步骤') }}</h4>
              <ol>
                <li v-for="(step, index) in workspace.revealedSolution.steps" :key="`${index}-${step}`">
                  <MathText :content="step" />
                </li>
              </ol>
            </div>
            <div
              v-if="
                workspace.revealedSolution.representation?.content
                && workspace.revealedSolution.representation?.kind !== 'reasoning_path'
              "
              class="solution-representation"
            >
              <h4>{{ t('courseWorkspace.practice.referenceImplementation', '参考实现或结构') }}</h4>
              <pre><MathText :content="formatSolutionValue(workspace.revealedSolution.representation.content)" /></pre>
            </div>
            <div
              v-if="workspace.revealedSolution.final_answer !== null && workspace.revealedSolution.final_answer !== undefined"
              class="solution-final-answer"
            >
              <h4>{{ t('courseWorkspace.practice.referenceAnswer', '参考答案') }}</h4>
              <pre><MathText :content="formatSolutionValue(workspace.revealedSolution.final_answer)" /></pre>
            </div>
            <div v-if="workspace.revealedSolution.checks?.length" class="solution-checks">
              <h4>{{ t('courseWorkspace.practice.resultChecks', '结果检查') }}</h4>
              <ul>
                <li v-for="check in workspace.revealedSolution.checks" :key="check"><MathText :content="check" /></li>
              </ul>
            </div>
            <div v-if="workspace.revealedSolution.option_analysis?.length" class="solution-option-analysis">
              <h4>{{ t('courseWorkspace.practice.optionAnalysis', '选项解析') }}</h4>
              <ul>
                <li
                  v-for="analysis in workspace.revealedSolution.option_analysis"
                  :key="analysis.option_id"
                >
                  <strong>{{ analysis.option_id }}</strong>：<MathText :content="analysis.explanation" />
                </li>
              </ul>
            </div>
            <div v-if="workspace.revealedSolution.common_errors?.length" class="solution-common-errors">
              <h4>{{ t('courseWorkspace.practice.commonErrors', '常见错误') }}</h4>
              <ul>
                <li v-for="error in workspace.revealedSolution.common_errors" :key="error"><MathText :content="error" /></li>
              </ul>
            </div>
            <p
              v-else-if="workspace.revealedSolution.correct_answer !== null && workspace.revealedSolution.correct_answer !== undefined"
            >
              {{ t('courseWorkspace.practice.referenceAnswer', '参考答案') }}：
              <MathText :content="formatSolutionValue(workspace.revealedSolution.correct_answer)" />
            </p>
            <ul v-if="workspace.revealedSolution.criteria?.length">
              <li v-for="criterion in workspace.revealedSolution.criteria" :key="criterion"><MathText :content="criterion" /></li>
            </ul>
            <ol v-if="workspace.revealedSolution.key_steps?.length">
              <li v-for="step in workspace.revealedSolution.key_steps" :key="step"><MathText :content="step" /></li>
            </ol>
            <p v-if="workspace.revealedSolution.self_check">
              {{ t('courseWorkspace.practiceAnalysis.selfCheck', '自查方法') }}：<MathText :content="workspace.revealedSolution.self_check" />
            </p>
          </section>
        </article>

        <footer class="practice-actions">
          <div class="support-actions">
            <button
              v-for="level in [1, 2, 3]"
              :key="level"
              class="icon-command"
              :disabled="!canRevealHint(level) || answerLocked || hintLoadingLevel !== null"
              :title="hintButtonLabel(level)"
              :aria-label="hintButtonLabel(level)"
              :aria-busy="hintLoadingLevel === level"
              @click="revealHint(level)"
            >
              <LoaderCircle v-if="hintLoadingLevel === level" :size="16" class="animate-spin" aria-hidden="true" />
              <Lightbulb v-else :size="16" aria-hidden="true" />
              <span>{{ level }}</span>
            </button>
            <button class="text-command" :disabled="!workspace.currentAttempt || answerLocked" @click="askTeacher">
              <MessageCircleQuestion :size="16" />
              {{ t('courseWorkspace.practice.askTeacher', '问老师') }}
            </button>
          </div>
          <button v-if="answerLocked && canRetry" class="primary-command" @click="retry">
            <RotateCcw :size="16" />
            {{ t('courseWorkspace.practice.retry', '重新尝试') }}
          </button>
          <button
            v-if="answerLocked && canRevealSolution"
            class="text-command"
            @click="revealSolution"
          >
            <BookOpenCheck :size="16" />
            {{ t('courseWorkspace.practice.revealSolution', '查看完整解析') }}
          </button>
          <button v-else-if="answerLocked && hasNext" class="primary-command" @click="nextQuestion">
            <ArrowRight :size="16" />
            {{ t('courseWorkspace.practice.next', '继续下一题') }}
          </button>
          <button v-else-if="!answerLocked" class="primary-command" :disabled="!hasAnswer || submitting || workspace.practiceSaveState === 'saving' || workspace.practiceSaveState === 'conflict'" @click="submit">
            <LoaderCircle v-if="submitting" :size="16" class="animate-spin" />
            <Send v-else :size="16" />
            {{ t('courseWorkspace.practice.submit', '提交作答') }}
          </button>
        </footer>
      </main>
    </template>

    <div v-else class="history-list">
      <div v-if="!historyAttempts.length && !legacyEvents.length" class="practice-empty">
        <History :size="24" />
        <strong>{{ practiceView === 'needs_review'
          ? t('courseWorkspace.practice.wrongBookEmpty', '错题本还没有记录')
          : t('courseWorkspace.practice.noHistory', '还没有相关练习记录') }}</strong>
        <span v-if="practiceView === 'needs_review'">{{ t('courseWorkspace.practice.wrongBookEmptyHelp', '未通过的正式练习会自动收进这里，之后可以直接针对再练。') }}</span>
      </div>
      <article v-for="attempt in historyAttempts" :key="attempt.attempt_id" class="history-row">
        <div>
          <strong><MathText :content="attempt.node_name || t('courseWorkspace.practice.unknownNode', '课程练习')" /></strong>
          <div class="history-row-actions">
            <span>{{ statusLabel(attempt) }}</span>
            <button
              v-if="canTargetRetry(attempt)"
              class="targeted-retry-command"
              type="button"
              :disabled="targetedRetryingId === attempt.attempt_id"
              @click="startTargetedRetry(attempt)"
            >
              <LoaderCircle v-if="targetedRetryingId === attempt.attempt_id" :size="14" class="animate-spin" />
              <RotateCcw v-else :size="14" />
              {{ t('courseWorkspace.targetedRetry.action', '针对再练') }}
            </button>
          </div>
        </div>
        <MathText tag="small" :content="attempt.result?.feedback || t('courseWorkspace.practice.savedAttempt', '作答历史已保留')" />
      </article>
      <article v-for="event in legacyEvents" :key="event.event_id" class="history-row legacy">
        <div>
          <strong><MathText :content="event.node_name || t('courseWorkspace.practice.legacy', '历史导入')" /></strong>
          <span>{{ t('courseWorkspace.practice.lowConfidence', '低置信历史') }}</span>
        </div>
        <small>{{ t('courseWorkspace.practice.notMasteryEvidence', '不参与当前掌握判断') }}</small>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  ArrowRight, BookOpenCheck, CheckCircle2, ChevronDown, Circle, CircleAlert, ClipboardCheck, Clock3, History,
  Lightbulb, LoaderCircle, MessageCircleQuestion, RefreshCw, RotateCcw, Send, Sparkles,
} from 'lucide-vue-next'
import MarkdownRenderer from './MarkdownRenderer.vue'
import MathText from './MathText.vue'
import PracticeAnswerRenderer from './PracticeAnswerRenderer.vue'
import { useCourseWorkspaceStore } from '../stores/courseWorkspace'
import { t } from '../shared/i18n'
import { isQuestionBankRepairReason, practiceAvailabilityCopy } from '../utils/course-availability'
import { practiceScopeKind } from '../utils/learning-scope'
import { splitPracticeQuestionMarkdown } from '../utils/practice-question-markdown'
import { hasMeaningfulAnswer } from '../utils/answer-payload'
import { presentSolutionValue } from '../utils/solution-presentation'
import { createUuid } from '../utils/client-id'
import {
  runQuestionBankRebuild,
  type QuestionBankRebuildJob,
} from '../utils/question-bank-rebuild'

const props = defineProps<{
  courseId: string
  nodeId?: string
  nodeLabel?: string
  scope: 'node' | 'final' | 'all'
  hideViewSwitch?: boolean
}>()
const emit = defineEmits<{
  (event: 'askTeacher', payload: { text: string; nodeId: string }): void
  (event: 'graded'): void
  (event: 'viewChange', view: 'current' | 'history' | 'needs_review'): void
}>()
// Mirrors socratic_guidance.MAX_ROUNDS; the server is authoritative and returns
// guidance_round_limit_reached, this only avoids offering a doomed request.
const MAX_GUIDANCE_ROUNDS = 6

const workspace = useCourseWorkspaceStore()
const practiceView = ref<'current' | 'history' | 'needs_review'>(workspace.practiceLandingView)
watch(practiceView, view => emit('viewChange', view), { immediate: true })
const submitting = ref(false)
const targetedRetryingId = ref('')
const questionRefreshing = ref(false)
const hintLoadingLevel = ref<number | null>(null)
const guidanceOpen = ref(false)
const guidanceMessage = ref('')
const guidanceSending = ref(false)
const guidanceRoundLimitReached = ref(false)
const questionBankRebuilding = ref(false)
const questionBankRebuildError = ref('')
const questionBankRebuildJob = ref<QuestionBankRebuildJob | null>(null)
const generationScope = ref<'node' | 'course'>('node')
const generationRetrievalEnabled = ref(false)
let saveTimer: ReturnType<typeof setTimeout> | null = null
let rebuildAbortController: AbortController | null = null

const questions = computed(() => workspace.practice?.questions || [])
const currentQuestion = computed(() => workspace.currentPracticeQuestion)
const currentQuestionMarkdown = computed(() => (
  splitPracticeQuestionMarkdown(currentQuestion.value)
))

interface HintDisplayRow {
  level: number
  content: string
  loading: boolean
  [key: string]: unknown
}

const hintDisplayRows = computed<HintDisplayRow[]>(() => {
  const loadingLevel = hintLoadingLevel.value
  const rows: HintDisplayRow[] = workspace.revealedHints
    .filter(hint => Number(hint.level) !== loadingLevel)
    .map(hint => ({
      ...hint,
      level: Number(hint.level),
      content: String(hint.content || ''),
      loading: false,
    }))
  if (loadingLevel !== null) {
    rows.push({
      level: loadingLevel,
      kind: 'loading',
      content: t('courseWorkspace.practice.hintGenerating', '正在生成提示，请稍候…'),
      loading: true,
    })
  }
  return rows.sort((left, right) => Number(left.level) - Number(right.level))
})
const canRebuildQuestionBank = computed(() => isQuestionBankRepairReason(
  workspace.practice?.practice_availability?.reason_code,
))
const currentNodeLabel = computed(() => props.nodeLabel || t('courseWorkspace.allCourse', '全课程'))
const practiceScopeLabel = computed(() => {
  const kind = practiceScopeKind(props.scope)
  if (kind === 'final') return t('courseWorkspace.scope.finalAssessment', '综合检测')
  if (kind === 'course') return t('courseWorkspace.scope.entireCourse', '全课程')
  return `${t('courseWorkspace.scope.currentObjective', '当前目标')} · ${currentNodeLabel.value}`
})
const emptyState = computed(() => practiceAvailabilityCopy(
  workspace.practice?.practice_availability?.reason_code || 'no_questions_in_scope',
  t,
))
const isChoiceQuestion = computed(() => currentQuestion.value?.input_contract?.mode === 'choice')

// Guidance transcript lives on the attempt, so it survives reload and can never
// disagree with the support level it drove.
const guidanceTurns = computed(() => {
  const turns = (workspace.currentAttempt as any)?.guidance_turns
  return Array.isArray(turns)
    ? turns.filter((turn: any) => turn && String(turn.text || '').trim())
    : []
})
const guidanceRoundsUsed = computed(() => guidanceTurns.value.filter(
  (turn: any) => turn.role === 'assistant' && turn.status === 'ok',
).length)
const guidanceExhausted = computed(() => (
  guidanceRoundLimitReached.value || guidanceRoundsUsed.value >= MAX_GUIDANCE_ROUNDS
))
const answerLocked = computed(() => !!workspace.currentAttempt && workspace.currentAttempt.status !== 'in_progress')
const hasAnswer = computed(() => hasMeaningfulAnswer(workspace.currentDraft || {}))
const hasNext = computed(() => workspace.currentQuestionIndex < questions.value.length - 1)
const normalizedCurrentPrompt = computed(() => String(currentQuestion.value?.prompt || '').trim().replace(/\s+/g, ' ').toLocaleLowerCase())
const canRefreshQuestion = computed(() => (
  !!currentQuestion.value
  && questions.value.some((question: any) => (
    String(question?.prompt || '').trim().replace(/\s+/g, ' ').toLocaleLowerCase()
    !== normalizedCurrentPrompt.value
  ))
  && workflowPhase.value === 'practice'
  && workspace.practiceSaveState !== 'saving'
  && workspace.practiceSaveState !== 'conflict'
))
const canRetry = computed(() => answerLocked.value && workspace.currentAttempt?.status !== 'grading')
const canRevealSolution = computed(() => workspace.practiceResult?.passed === false && !workspace.currentAttempt?.solution_revealed)
const answerDiagnosis = computed(() => {
  const value = workspace.practiceResult?.answer_diagnosis
  return value?.status === 'completed' ? value : null
})
const analysisFitLabel = computed(() => t(
  `courseWorkspace.practiceAnalysis.fit.${answerDiagnosis.value?.diagnosis?.library_fit || 'MISS'}`,
  ({ HIT: '已定位到本课目标', PARTIAL: '部分定位到本课目标', MISS: '暂未归入现有目标' } as Record<string, string>)[answerDiagnosis.value?.diagnosis?.library_fit || 'MISS'],
))
const studentResponseEvidenceLabel = computed(() => (
  isChoiceQuestion.value
    ? t('courseWorkspace.practiceAnalysis.selectedMeaning', '你的选择反映了什么')
    : t('courseWorkspace.practiceAnalysis.studentApproach', '你采用了什么思路')
))
const diagnosisTags = computed(() => {
  if (!answerDiagnosis.value) return []
  const diagnosis = answerDiagnosis.value.diagnosis || {}
  return [
    ...(diagnosis.knowledge || []).map((item: any) => ({ ...item, kind: 'knowledge' })),
    ...(diagnosis.skills || []).map((item: any) => ({ ...item, kind: 'skill' })),
    ...(diagnosis.misconceptions || []).map((item: any) => ({ ...item, kind: 'misconception' })),
  ]
})
const historyAttempts = computed(() => workspace.practiceHistory?.attempts || [])
const legacyEvents = computed(() => workspace.practiceHistory?.legacy_events || [])
const workflowPhase = computed(() => workspace.diagnosticWorkflow?.phase || 'practice')
const workflowActive = computed(() => workflowPhase.value !== 'practice')
const remediationUnit = computed(() => workspace.diagnosticWorkflow?.session?.unit || null)
const workflowHypothesis = computed(() => {
  const current = workspace.diagnosticWorkflow?.case
  const id = current?.confirmed_hypothesis_id
  return (current?.hypotheses || []).find((item: any) => item.hypothesis_id === id)?.claim
    || (current?.hypotheses || []).find((item: any) => item.status === 'testing')?.claim
    || ''
})
const workflowPhaseLabel = computed(() => t(
  `courseWorkspace.practice.workflow.phase.${workflowPhase.value}`,
  ({ diagnostic: '辨别卡点', remediation: '局部补救', validation: '独立复验', resolved: '已经结案', needs_support: '需要老师介入' } as Record<string, string>)[workflowPhase.value] || '正式练习',
))
const workflowHeadline = computed(() => t(
  `courseWorkspace.practice.workflow.headline.${workflowPhase.value}`,
  ({
    diagnostic: '先查清原因，不根据一次错误直接下结论',
    remediation: '只修复已确认的局部问题',
    validation: '换一道未见题，独立证明已经解决',
    resolved: '独立复验已经通过',
    needs_support: '自动链路已停止，等待进一步判断',
  } as Record<string, string>)[workflowPhase.value] || '',
))
const questionTypeLabel = computed(() => t(
  `courseWorkspace.questionTypes.${currentQuestion.value?.question_type || 'short_answer'}`,
  currentQuestion.value?.question_type || '练习',
))
const answerPlaceholder = computed(() => t('courseWorkspace.practice.answerPlaceholder', '写下完整过程、依据和结果检查'))
const saveStateLabel = computed(() => t(
  `courseWorkspace.practice.saveState.${workspace.practiceSaveState}`,
  ({ idle: '尚未保存', saving: '正在保存', saved: '已保存', local_only: '仅保存在本机', conflict: '草稿冲突' } as Record<string, string>)[workspace.practiceSaveState],
))
const feedbackTitle = computed(() => {
  const result = workspace.practiceResult || {}
  if (result.status === 'pending_review') return t('courseWorkspace.practice.pendingReview', '等待评阅')
  return result.passed ? t('courseWorkspace.practice.passed', '达到本题标准') : t('courseWorkspace.practice.notPassed', '尚未达到标准')
})
const evidenceLabel = computed(() => t(
  `courseWorkspace.practice.evidence.${workspace.practiceResult?.evidence_strength || 'invalid'}`,
  `证据强度：${workspace.practiceResult?.evidence_strength || '待确认'}`,
))

// Per-step verdicts (J3). The grader only attaches this when the student
// actually submitted steps, so its absence is the whole-answer path, not an error.
const stepwiseJudgement = computed(() => (workspace.practiceResult as any)?.stepwise || null)

function stepVerdictLabel(verdict: string): string {
  if (verdict === 'correct') return t('courseWorkspace.practice.stepCorrect', '这一步成立')
  if (verdict === 'flawed') return t('courseWorkspace.practice.stepFlawed', '这一步有问题')
  // "unclear" is a real answer, not a failure: the model must say so rather than
  // guess, so it has to be shown as its own state instead of being hidden.
  return t('courseWorkspace.practice.stepUnclear', '这一步看不出依据')
}

watch(
  () => [props.courseId, props.nodeId, props.scope],
  async () => {
    if (!props.courseId) return
    questionBankRebuildError.value = ''
    await workspace.loadPractice(props.courseId, props.nodeId, props.scope)
    await ensureAttempt()
  },
  { immediate: true },
)

watch(
  () => workspace.practiceLandingView,
  async view => {
    if (view === 'current') practiceView.value = 'current'
    else await openHistory(view === 'history' ? 'all' : 'needs_review')
  },
  { immediate: true },
)

watch(
  () => currentQuestion.value?.revision_id,
  async () => {
    if (practiceView.value === 'current') await ensureAttempt()
  },
)

watch(
  () => workspace.currentDraft,
  () => {
    if (!workspace.currentAttempt || answerLocked.value) return
    if (JSON.stringify(workspace.currentDraft) === JSON.stringify(workspace.currentAttempt.answer_payload || {})) return
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => {
      void workspace.savePracticeDraft(props.courseId).catch(() => undefined)
    }, 700)
  },
  { deep: true },
)

onBeforeUnmount(() => {
  if (saveTimer) clearTimeout(saveTimer)
  rebuildAbortController?.abort()
  if (workspace.currentAttempt?.status === 'in_progress') {
    void workspace.savePracticeDraft(props.courseId).catch(() => undefined)
  }
})

async function ensureAttempt() {
  const question = currentQuestion.value
  if (
    !question || !props.courseId || workspace.practiceLoading || workspace.requestedTaskRef
    || workspace.taskResumeError || ['resolved', 'needs_support'].includes(workflowPhase.value)
  ) return
  const taskId = question.task_revision_id || question.revision_id
  if ((workspace.currentAttempt?.task_revision_id || workspace.currentAttempt?.question_revision_id) === taskId) return
  await workspace.startPracticeAttempt(props.courseId, taskId)
}

function canRevealHint(level: number) {
  const attempt = workspace.currentAttempt
  if (!attempt || attempt.status !== 'in_progress') return false
  const used = attempt.revealed_hint_levels || []
  if (used.includes(level)) return true
  return level === 1 || used.includes(level - 1)
}

function hintButtonLabel(level: number) {
  if (hintLoadingLevel.value === level) {
    return t(
      'courseWorkspace.practice.hintGeneratingLevel',
      '正在生成 {level} 级提示',
    ).replace('{level}', String(level))
  }
  return t(
    'courseWorkspace.practice.hintLevel',
    '{level} 级提示',
  ).replace('{level}', String(level))
}

async function revealHint(level: number) {
  if (hintLoadingLevel.value !== null) return
  if (level >= 2) {
    await ElMessageBox.confirm(
      level === 3
        ? t('courseWorkspace.practice.hintThreeImpact', '三级提示会使本次作答不能单独证明掌握，仍要继续吗？')
        : t('courseWorkspace.practice.hintTwoImpact', '二级提示会把本次结果标记为在支持下完成，仍要继续吗？'),
      t('courseWorkspace.practice.useHint', '使用提示'),
      { confirmButtonText: t('common.confirm', '确认'), cancelButtonText: t('common.cancel', '取消') },
    )
  }
  hintLoadingLevel.value = level
  try {
    await workspace.revealPracticeHint(props.courseId, level)
  } catch {
    // The shared HTTP layer already reports the request error.
  } finally {
    if (hintLoadingLevel.value === level) hintLoadingLevel.value = null
  }
}

async function askTeacher() {
  // Opening the guidance panel is the multi-round Socratic entry (K2). The
  // support level is still recorded here so simply opening the AI tutor keeps
  // counting exactly as it did before.
  guidanceOpen.value = true
  await workspace.recordPracticeAiSupport(props.courseId, 1)
  emit('askTeacher', { text: currentQuestion.value?.prompt || '', nodeId: props.nodeId || '' })
}

async function escalateToTeacher() {
  // This path used to emit straight to the AI tutor without recording anything,
  // which quietly bypassed the support accounting that mastery depends on —
  // remediation help was free. It has to cost the same as any other AI help.
  guidanceOpen.value = true
  if (workspace.currentAttempt && !answerLocked.value) {
    try {
      await workspace.recordPracticeAiSupport(props.courseId, 1)
    } catch {
      // The shared HTTP layer already surfaced the error; escalation itself must
      // still proceed so a recording failure never blocks a student asking.
    }
  }
  emit('askTeacher', {
    text: workflowHypothesis.value || currentQuestion.value?.prompt || '',
    nodeId: props.nodeId || '',
  })
}

async function sendGuidance() {
  const message = guidanceMessage.value.trim()
  if (!message || guidanceSending.value) return
  guidanceSending.value = true
  try {
    await workspace.recordPracticeAiSupport(props.courseId, 1, message)
    guidanceMessage.value = ''
  } catch (error: any) {
    if (error?.response?.data?.detail?.code === 'guidance_round_limit_reached') {
      guidanceRoundLimitReached.value = true
    }
    // Other failures are already reported by the shared HTTP layer; the student's
    // text stays in the box so a transient error never eats what they typed.
  } finally {
    guidanceSending.value = false
  }
}

function guidanceStatusNote(status: string): string {
  if (status === 'screened') {
    // Deliberately honest: we stopped our own output, and it cost the student
    // nothing (the backend does not charge support for undelivered turns).
    return t(
      'courseWorkspace.practice.guidanceScreened',
      '这一轮引导没有通过安全检查，已换成一个不泄露答案的问题，本轮不计入求助。',
    )
  }
  if (status === 'unavailable') {
    return t('courseWorkspace.practice.guidanceUnavailable', 'AI 老师暂时不可用，本轮不计入求助。')
  }
  return t('courseWorkspace.practice.guidanceDegraded', '这一轮没能生成有效引导，本轮不计入求助。')
}

async function submit() {
  if (saveTimer) {
    clearTimeout(saveTimer)
    saveTimer = null
  }
  submitting.value = true
  try {
    await workspace.submitCurrentPractice(props.courseId)
    if (workspace.diagnosticWorkflow?.current_task && !['resolved', 'needs_support'].includes(workflowPhase.value)) {
      await ensureAttempt()
    }
    emit('graded')
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || t('courseWorkspace.practice.submitFailed', '提交失败，请确认网络后重试'))
  } finally {
    submitting.value = false
  }
}

async function revealSolution() {
  await ElMessageBox.confirm(
    t('courseWorkspace.practice.solutionImpact', '查看完整解析后，本次结果不再作为独立掌握证据。仍要继续吗？'),
    t('courseWorkspace.practice.revealSolution', '查看完整解析'),
    { confirmButtonText: t('common.confirm', '确认'), cancelButtonText: t('common.cancel', '取消') },
  )
  await workspace.revealPracticeSolution(props.courseId)
}

async function retry() {
  await workspace.retryCurrentPractice(props.courseId)
}

async function nextQuestion() {
  workspace.nextPracticeQuestion()
  await ensureAttempt()
}

async function refreshQuestion() {
  if (!canRefreshQuestion.value || questionRefreshing.value) return
  if (
    workspace.currentAttempt?.status === 'in_progress'
    && hasAnswer.value
  ) {
    try {
      await ElMessageBox.confirm(
        t(
          'courseWorkspace.practice.refreshDraftWarning',
          '当前未提交草稿会结束并保留为一次已放弃记录，确定换一题吗？',
        ),
        t('courseWorkspace.practice.refreshQuestion', '换一题'),
        {
          confirmButtonText: t('common.confirm', '确认'),
          cancelButtonText: t('common.cancel', '取消'),
        },
      )
    } catch {
      return
    }
  }
  questionRefreshing.value = true
  try {
    await workspace.refreshPracticeQuestion(
      props.courseId,
      props.nodeId,
      props.scope,
    )
    await ensureAttempt()
    ElMessage.success(t(
      'courseWorkspace.practice.refreshSuccess',
      '已切换到同一课程范围内的另一道题。',
    ))
  } catch (error: any) {
    const detail = error?.response?.data?.detail
    ElMessage.error(
      (typeof detail === 'string' ? detail : detail?.message)
      || t(
        'courseWorkspace.practice.refreshFailed',
        '当前没有可切换的正式题目，请稍后重试。',
      ),
    )
  } finally {
    questionRefreshing.value = false
  }
}

async function resumeCoursePractice() {
  workspace.diagnosticWorkflow = null
  workspace.currentAttempt = null
  workspace.currentDraft = {}
  workspace.practiceResult = null
  await ensureAttempt()
}

async function openHistory(view: 'all' | 'needs_review') {
  practiceView.value = view === 'all' ? 'history' : 'needs_review'
  workspace.practiceLandingView = practiceView.value
  await workspace.loadPracticeHistory(props.courseId, view, props.nodeId)
}

function canTargetRetry(attempt: any) {
  return attempt?.status === 'graded' && attempt?.result?.passed === false
}

async function startTargetedRetry(attempt: any) {
  targetedRetryingId.value = attempt.attempt_id
  try {
    const started = await workspace.startTargetedRetry(props.courseId, attempt)
    if (!started) {
      ElMessage.warning(t('courseWorkspace.targetedRetry.unavailable', '原题已不在当前课程版本中，无法发起针对练习'))
      return
    }
    practiceView.value = 'current'
    workspace.practiceLandingView = 'current'
  } catch (error: any) {
    const detail = error?.response?.data?.detail
    ElMessage.error(
      (typeof detail === 'string' ? detail : detail?.message)
      || t('courseWorkspace.targetedRetry.failed', '针对练习启动失败，请稍后重试'),
    )
  } finally {
    targetedRetryingId.value = ''
  }
}

function selectView(view: 'current') {
  practiceView.value = view
  workspace.practiceLandingView = view
}

defineExpose({ openHistory, selectView })

async function rebuildQuestionBank() {
  if (!props.courseId || questionBankRebuilding.value) return
  questionBankRebuilding.value = true
  questionBankRebuildError.value = ''
  questionBankRebuildJob.value = null
  rebuildAbortController = new AbortController()
  try {
    const nodeScoped = generationScope.value === 'node' && Boolean(props.nodeId)
    const job = await runQuestionBankRebuild(
      props.courseId,
      {
        request_id: createUuid(),
        scope: nodeScoped ? 'nodes' : 'course',
        node_ids: nodeScoped ? [String(props.nodeId)] : [],
        mode: 'incremental',
        retrieval_enabled: generationRetrievalEnabled.value,
      },
      {
        signal: rebuildAbortController.signal,
        onUpdate: update => {
          questionBankRebuildJob.value = update
        },
      },
    )
    workspace.currentQuestionIndex = 0
    workspace.currentAttempt = null
    workspace.currentDraft = {}
    workspace.practiceResult = null
    await workspace.loadAssets(props.courseId, props.nodeId)
    await workspace.loadPractice(props.courseId, props.nodeId, props.scope)
    if (job.status === 'waiting_review') {
      ElMessage.warning(t(
        'questionBook.generateReview',
        '候选题已经生成，完成质量验证后会出现在题库本中。',
      ))
    } else {
      ElMessage.success(t(
        'questionBook.generateSuccess',
        '题目已生成并进入题库本，可以开始练习。',
      ))
    }
  } catch (error: any) {
    if (error?.name === 'AbortError') return
    const detail = error?.response?.data?.detail
    questionBankRebuildError.value = (
      typeof detail === 'string'
        ? detail
        : detail?.message
    ) || error?.message || t(
      'courseAvailability.rebuildQuestionsFailed',
      '题目生成失败，旧题库和历史记录未被覆盖，请稍后重试。',
    )
  } finally {
    rebuildAbortController = null
    questionBankRebuilding.value = false
  }
}

function statusLabel(attempt: any) {
  if (attempt.status === 'grading') return t('courseWorkspace.practice.pendingReview', '等待评阅')
  if (attempt.result?.passed) return t('courseWorkspace.practice.passed', '达到本题标准')
  if (attempt.status === 'in_progress') return t('courseWorkspace.practice.inProgress', '进行中')
  return t('courseWorkspace.practice.notPassed', '尚未达到标准')
}

function formatSolutionValue(value: unknown) {
  return presentSolutionValue(value)
}

</script>

<style scoped>
.practice-workspace {
  height: 100%;
  min-height: 0;
  overflow: auto;
  color: #172033;
  background: #f6f7fb;
  scrollbar-gutter: stable;
}

.question-book-context {
  position: sticky;
  top: 0;
  z-index: 5;
  min-height: 68px;
  display: grid;
  grid-template-columns: minmax(190px, 1fr) auto minmax(150px, 1fr);
  align-items: center;
  gap: 18px;
  padding: 10px 22px;
  border-bottom: 1px solid #e3e7ef;
  background: rgba(255, 255, 255, .98);
}

.question-book-context__copy {
  min-width: 0;
  display: grid;
  gap: 3px;
}

.question-book-context__copy > span {
  overflow: hidden;
  color: #686f83;
  font-size: 10px;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.question-book-context__copy > strong {
  overflow: hidden;
  color: #20263a;
  font-size: 13px;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.question-book-views {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 3px;
  border: 1px solid #e1e5ee;
  border-radius: 10px;
  background: #f5f6fa;
}

.question-book-views button {
  min-height: 32px;
  padding: 0 12px;
  border: 0;
  border-radius: 7px;
  color: #646c80;
  background: transparent;
  font-size: 11px;
  cursor: pointer;
}

.question-book-views button:hover { color: #292f43; }
.question-book-views button.active {
  color: var(--lz-brand-strong);
  background: #fff;
  box-shadow: 0 2px 8px rgba(35, 40, 67, .09);
  font-weight: 700;
}

.question-book-views button:focus-visible,
.question-bank-rebuild__scope button:focus-visible,
.refresh-question-command:focus-visible,
.icon-command:focus-visible,
.text-command:focus-visible,
.primary-command:focus-visible,
.targeted-retry-command:focus-visible {
  outline: 2px solid var(--lz-brand);
  outline-offset: 2px;
}

.question-book-context__state {
  min-width: 0;
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 10px;
}

.practice-selection-policy {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: #535bb6;
  font-size: 10px;
  white-space: nowrap;
}

.practice-progress {
  color: #343b55;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.workflow-band {
  width: min(820px, calc(100% - 48px));
  margin: 20px auto 0;
  display: grid;
  grid-template-columns: minmax(160px, .7fr) minmax(0, 1.3fr);
  gap: 24px;
  align-items: start;
  padding: 14px 16px;
  border: 1px solid #b9ddd8;
  border-radius: 12px;
  background: #f4fbfa;
}

.workflow-band > div { display: grid; gap: 4px; }
.workflow-band span { color: #0f766e; font-size: 10px; font-weight: 800; }
.workflow-band strong { font-size: 13px; }
.workflow-band p { margin: 0; color: #4f5d70; font-size: 12px; line-height: 1.6; }
.workflow-band[data-phase="needs_support"] { border-color: #f0cf95; background: #fffaf0; }
.workflow-band[data-phase="resolved"] { border-color: #a7d7c0; background: #f3fbf7; }

.question-book-empty {
  min-height: calc(100% - 68px);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 28px;
  padding: clamp(38px, 8vh, 82px) 24px;
  background: #f6f7fb;
}

.practice-workspace.has-external-view-switch .question-book-empty {
  min-height: 100%;
}

.question-book-empty__intro {
  width: min(520px, 100%);
  display: flex;
  align-items: flex-start;
  gap: 16px;
  padding: 0;
  background: transparent;
}

.question-book-empty__icon {
  width: 44px;
  height: 44px;
  flex: 0 0 auto;
  display: grid;
  place-items: center;
  border-radius: 12px;
  color: var(--lz-brand-strong);
  background: var(--lz-brand-soft);
}

.question-book-empty__intro > div {
  max-width: 370px;
  display: grid;
  gap: 8px;
  padding-top: 2px;
}

.question-book-empty__intro small {
  color: var(--lz-brand-strong);
  font-size: 10px;
  font-weight: 700;
}

.question-book-empty__intro strong {
  color: #1f2538;
  font-size: clamp(20px, 2.3vw, 27px);
  line-height: 1.28;
  letter-spacing: -.02em;
}

.question-book-empty__intro p {
  margin: 0;
  color: #626a7c;
  font-size: 13px;
  line-height: 1.7;
}

.question-bank-rebuild {
  width: min(420px, 100%);
  display: grid;
  gap: 14px;
  margin: 0;
}

.question-bank-rebuild__heading {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16px;
}

.question-bank-rebuild__heading strong { color: #20263a; font-size: 15px; }
.question-bank-rebuild__heading span { color: #747b8d; font-size: 10px; }

.question-bank-rebuild__scope {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 4px;
  padding: 4px;
  border: 1px solid #dfe3ec;
  border-radius: 10px;
  background: #eceef4;
}

.question-bank-rebuild__scope button {
  min-height: 36px;
  padding: 0 12px;
  border: 0;
  border-radius: 7px;
  color: #5f677a;
  background: transparent;
  font-size: 12px;
  cursor: pointer;
}

.question-bank-rebuild__scope button.active {
  color: var(--lz-brand-strong);
  background: #fff;
  box-shadow: 0 2px 7px rgba(30, 36, 66, .1);
  font-weight: 700;
}

.question-bank-rebuild__retrieval {
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr);
  align-items: start;
  gap: 9px;
  padding: 11px 0;
  color: #444b5f;
  cursor: pointer;
}

.question-bank-rebuild__retrieval input {
  width: 16px;
  height: 16px;
  margin: 1px 0 0;
  accent-color: var(--lz-brand);
}

.question-bank-rebuild__retrieval > span { display: grid; gap: 2px; }
.question-bank-rebuild__retrieval strong { font-size: 12px; font-weight: 650; }
.question-bank-rebuild__retrieval small { color: #777f91; font-size: 10px; line-height: 1.45; }

.question-bank-rebuild__submit { width: 100%; min-height: 40px; }
.question-bank-rebuild__help {
  margin: -5px 0 0;
  color: #747b8d;
  font-size: 10px;
  line-height: 1.55;
  text-align: center;
}

.question-bank-rebuild__progress {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 7px 10px;
  align-items: center;
  color: #596175;
  font-size: 10px;
}

.question-bank-rebuild__progress strong { color: var(--lz-brand-strong); }
.question-bank-rebuild__progress i {
  grid-column: 1 / -1;
  height: 5px;
  overflow: hidden;
  border-radius: 999px;
  background: #dde1ea;
}

.question-bank-rebuild__progress b {
  display: block;
  width: 100%;
  height: 100%;
  border-radius: inherit;
  background: var(--lz-brand);
  transform-origin: left center;
  transition: transform .25s ease;
}

.question-bank-rebuild__error { color: #b42318; font-size: 11px; line-height: 1.5; }

.practice-empty {
  min-height: 330px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 32px;
  color: #626a7c;
  text-align: center;
}

.practice-empty strong { color: #252b3f; font-size: 15px; }
.practice-empty > span { max-width: 540px; font-size: 12px; line-height: 1.65; }

.question-stage,
.history-list {
  width: min(820px, calc(100% - 48px));
  margin: 0 auto;
  padding: 24px 0 34px;
}

.question-content {
  padding: 24px 28px 0;
  border-radius: 14px;
  background: #fff;
  box-shadow: 0 8px 24px rgba(29, 34, 59, .07);
}

.question-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 18px;
  color: #71798c;
  font-size: 10px;
}

.question-meta > div { display: flex; gap: 14px; }

.refresh-question-command,
.targeted-retry-command {
  min-height: 30px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 0 9px;
  border: 1px solid #d6dbe5;
  border-radius: 7px;
  color: #555e72;
  background: #fff;
  font-size: 11px;
  cursor: pointer;
}

.refresh-question-command:hover:not(:disabled),
.targeted-retry-command:hover:not(:disabled) {
  border-color: #a9afe8;
  color: var(--lz-brand-strong);
}

.refresh-question-command:disabled,
.targeted-retry-command:disabled { opacity: .45; cursor: not-allowed; }

.question-prompt {
  display: grid;
  gap: 14px;
  margin: 15px 0 22px;
  color: #31384c;
  font-size: 14px;
  line-height: 1.75;
}

.question-stimulus {
  padding: 16px 18px;
  border-radius: 10px;
  background: #f4f6fa;
}

.question-stimulus > header { margin-bottom: 8px; }
.question-stimulus > header strong { color: #5e6679; font-size: 11px; }

.question-task {
  padding: 2px 0 2px 15px;
  border-left: 1px solid var(--lz-brand);
}

.question-task > header {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  align-items: center;
  margin-bottom: 7px;
}

.question-task > header strong { color: var(--lz-brand-strong); font-size: 11px; }
.question-task > header span { color: #7a8192; font-size: 10px; }

.question-stimulus :deep(p:last-child),
.question-stimulus :deep(pre:last-child),
.question-task :deep(p:last-child) { margin-bottom: 0; }

.question-material {
  overflow: hidden;
  border-top: 1px solid #e3e7ef;
  border-bottom: 1px solid #e3e7ef;
  background: #fff;
}

.question-material > summary {
  min-width: 0;
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  padding: 12px 2px;
  cursor: pointer;
  list-style: none;
}

.question-material > summary::-webkit-details-marker { display: none; }
.question-material > summary:focus-visible { outline: 2px solid var(--lz-brand); outline-offset: -2px; }

.question-material__icon {
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  border-radius: 8px;
  color: var(--lz-brand-strong);
  background: var(--lz-brand-soft);
}

.question-material__copy { min-width: 0; }
.question-material__copy strong { display: block; color: #3a4155; font-size: 11px; }
.question-material__copy small {
  display: block;
  margin-top: 2px;
  overflow: hidden;
  color: #747c8e;
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.question-material__action {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--lz-brand-strong);
  font-size: 10px;
  font-weight: 650;
}

.question-material__action svg { transition: transform .18s ease; }
.question-material .collapse-label { display: none; }
.question-material[open] .question-material__action svg { transform: rotate(180deg); }
.question-material[open] .expand-label { display: none; }
.question-material[open] .collapse-label { display: inline; }
.question-material[open] .question-material__copy small { white-space: normal; }

.question-material__body {
  padding: 18px 2px 20px;
  border-top: 1px solid #e3e7ef;
}

.question-prompt :deep(h1),
.question-prompt :deep(h2),
.question-prompt :deep(h3),
.question-prompt :deep(h4),
.question-prompt :deep(h5),
.question-prompt :deep(h6) {
  color: #20263a;
  letter-spacing: -.01em;
}

.question-prompt :deep(h1) { margin: 0 0 16px; font-size: 22px; line-height: 1.35; }
.question-prompt :deep(h2) { margin: 26px 0 10px; font-size: 18px; line-height: 1.4; }
.question-prompt :deep(h3) { margin: 22px 0 9px; font-size: 15px; line-height: 1.45; }
.question-prompt :deep(p) { margin: 0 0 12px; line-height: 1.78; }
.question-prompt :deep(ul),
.question-prompt :deep(ol) { margin: 8px 0 16px; padding-left: 22px; }
.question-prompt :deep(li) { margin: 5px 0; line-height: 1.7; }
.question-prompt :deep(hr) { margin: 22px 0; border-color: #e1e5ed; }
.question-prompt :deep(pre) {
  margin: 13px 0 18px;
  padding: 15px 17px;
  overflow: auto;
  border-radius: 9px;
  background: #151a2b;
  color: #e7eaf3;
  font: 12px/1.7 ui-monospace, SFMono-Regular, Consolas, monospace;
  white-space: pre;
}
.question-prompt :deep(pre code) { color: inherit; font: inherit; }
.question-prompt :deep(blockquote) { margin: 15px 0; border-left-color: var(--lz-brand); background: var(--lz-brand-soft); }
.question-prompt :deep(table) { display: block; width: 100%; overflow-x: auto; }

.practice-actions {
  position: sticky;
  bottom: 0;
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  margin: 22px -28px 0;
  padding: 12px 28px;
  border-top: 1px solid #e3e7ef;
  border-radius: 0 0 14px 14px;
  background: rgba(255, 255, 255, .98);
}

.support-actions { display: flex; align-items: center; gap: 7px; }

.icon-command,
.text-command,
.primary-command {
  min-height: 36px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 0 12px;
  border: 1px solid #d3d8e3;
  border-radius: 8px;
  color: #424a5f;
  background: #fff;
  font-size: 11px;
  cursor: pointer;
}

.icon-command { width: 38px; padding: 0; }
.icon-command:disabled,
.text-command:disabled,
.primary-command:disabled { opacity: .45; cursor: not-allowed; }

.icon-command:hover:not(:disabled),
.text-command:hover:not(:disabled) { border-color: #a9afe8; color: var(--lz-brand-strong); }

.primary-command {
  border-color: var(--lz-brand-strong);
  color: #fff;
  background: var(--lz-brand-strong);
  font-weight: 700;
}

.primary-command:hover:not(:disabled) { filter: brightness(.96); }

.hint-results,
.practice-feedback,
.solution-result,
.guidance-panel {
  margin-top: 18px;
  padding-top: 16px;
  border-top: 1px solid #e2e6ee;
}

.hint-result {
  display: grid;
  grid-template-columns: 72px 1fr;
  gap: 12px;
  margin: 8px 0;
}

.hint-result span { color: #9a6508; font-size: 11px; font-weight: 700; }
.hint-result p { margin: 0; line-height: 1.6; }
.hint-result.loading p { display: flex; align-items: center; gap: 8px; color: #697286; }
.hint-loading-icon { flex: 0 0 auto; color: #0f766e; }

.guidance-panel { display: grid; gap: 10px; }
.guidance-heading {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  color: #0f766e;
}

.guidance-heading small {
  flex-basis: 100%;
  color: #6b7386;
  font-weight: 400;
  line-height: 1.5;
}

.guidance-turn {
  display: grid;
  grid-template-columns: 70px 1fr;
  gap: 12px;
  align-items: start;
}

.guidance-role { color: #6e7689; font-size: 11px; font-weight: 700; }
.guidance-turn.assistant .guidance-role { color: #0f766e; }
.guidance-turn p { margin: 0; line-height: 1.6; }
.guidance-turn small { grid-column: 2; }
.guidance-degraded { color: #a45f08; line-height: 1.5; }

.guidance-compose { display: grid; gap: 8px; }
.guidance-input {
  width: 100%;
  min-height: 74px;
  box-sizing: border-box;
  padding: 10px 12px;
  border: 1px solid #ced4df;
  border-radius: 9px;
  color: #20263a;
  background: #fff;
  font: inherit;
  line-height: 1.6;
  resize: vertical;
}

.guidance-input:focus { border-color: var(--lz-brand); outline: 2px solid rgba(99, 102, 241, .13); }
.guidance-compose button { justify-self: start; }

.practice-feedback { color: #984311; }
.practice-feedback[data-passed="true"] { color: #047857; }
.feedback-heading { display: flex; gap: 9px; align-items: center; }
.feedback-heading span { margin-left: auto; font-size: 22px; font-weight: 800; }
.practice-feedback > p { color: #50596e; }

.rubric-list { display: grid; gap: 7px; margin: 12px 0; }
.rubric-list > div {
  display: grid;
  grid-template-columns: 18px minmax(120px, auto) 1fr;
  gap: 7px;
  align-items: start;
  color: #343b4e;
}
.rubric-list small { color: #6d7588; }

.stepwise-judgement { margin-top: 14px; display: grid; gap: 8px; }
.stepwise-judgement header { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.stepwise-judgement header strong { color: #0f766e; }
.stepwise-judgement header span { color: #a25b05; font-size: 11px; }
.stepwise-verdict {
  display: grid;
  grid-template-columns: 74px auto 1fr;
  gap: 10px;
  align-items: baseline;
}
.verdict-index { color: #6e7689; font-size: 11px; font-weight: 700; }
.verdict-tag { font-size: 11px; font-weight: 700; }
.stepwise-verdict[data-verdict="correct"] .verdict-tag { color: #0f766e; }
.stepwise-verdict[data-verdict="flawed"] .verdict-tag { color: #b42318; }
.stepwise-verdict[data-verdict="unclear"] .verdict-tag { color: #a25b05; }
.stepwise-verdict small { color: #4f586c; line-height: 1.5; }

.answer-diagnosis {
  margin: 18px 0 12px;
  padding: 16px;
  border-radius: 10px;
  background: #f5f6fa;
  color: #20263a;
}

.answer-diagnosis > header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  padding-bottom: 11px;
  border-bottom: 1px solid #dfe3eb;
}

.answer-diagnosis > header span { color: #0f766e; font-size: 10px; font-weight: 700; }
.answer-diagnosis dl {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
  margin: 14px 0;
}
.answer-diagnosis dl > div { min-width: 0; }
.answer-diagnosis dt { color: #6b7386; font-size: 10px; font-weight: 700; }
.answer-diagnosis dd { margin: 5px 0 0; color: #3d4559; line-height: 1.55; overflow-wrap: anywhere; }

.diagnosis-tags { display: flex; flex-wrap: wrap; gap: 6px; }
.diagnosis-tags span {
  padding: 4px 8px;
  border-radius: 999px;
  color: #4f586b;
  background: #e9ecf2;
  font-size: 10px;
}
.diagnosis-tags span[data-kind="skill"] { color: #0e7490; background: #e5f7fa; }
.diagnosis-tags span[data-kind="misconception"] { color: #ad4b11; background: #fff0e6; }

.diagnosis-issues { display: grid; gap: 8px; padding: 0; margin: 14px 0; list-style: none; }
.diagnosis-issues li { display: grid; gap: 3px; padding: 9px 10px; border-radius: 8px; background: #fff7dd; }
.diagnosis-issues span,
.diagnosis-summary { color: #4e576b; line-height: 1.6; }

.diagnosis-next {
  display: grid;
  gap: 4px;
  margin-top: 14px;
  padding: 11px 12px;
  border-radius: 8px;
  background: var(--lz-brand-soft);
}
.diagnosis-next span { color: var(--lz-brand-strong); font-size: 10px; }
.diagnosis-next strong { color: #252b3f; line-height: 1.5; }

.solution-result { color: #343b4e; }
.solution-result p,
.solution-result li { line-height: 1.65; }
.solution-result ul,
.solution-result ol { padding-left: 20px; }
.solution-result h4 { margin: 14px 0 7px; color: #20263a; font-size: 12px; }
.solution-result pre {
  max-height: 420px;
  margin: 0;
  padding: 12px 14px;
  overflow: auto;
  border-radius: 8px;
  color: #20263a;
  background: #eef0f5;
  font: 12px/1.65 ui-monospace, SFMono-Regular, Consolas, monospace;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.remediation-context,
.targeted-retry-context {
  margin-bottom: 18px;
  padding: 13px 14px;
  border-radius: 9px;
  color: #135f59;
  background: #edf9f7;
}

.remediation-context strong { color: #135f59; }
.remediation-context p { margin: 8px 0; line-height: 1.65; }
.remediation-context small { color: #667084; }

.targeted-retry-context { display: flex; align-items: flex-start; gap: 10px; }
.targeted-retry-context > div { min-width: 0; }
.targeted-retry-context strong { font-size: 11px; }
.targeted-retry-context p { margin: 3px 0 0; color: #576174; font-size: 10px; line-height: 1.55; }

.state-notice {
  display: flex;
  gap: 9px;
  padding: 11px 12px;
  margin-bottom: 14px;
  border-radius: 8px;
  color: #b42318;
  background: #fff0ee;
}

.workflow-result.warning svg { color: #a25b05; }

.history-list { display: grid; gap: 0; }
.history-row {
  padding: 16px 18px;
  border-bottom: 1px solid #e2e6ee;
  background: #fff;
}

.history-row:first-of-type { border-radius: 12px 12px 0 0; }
.history-row:last-child { border-bottom: 0; border-radius: 0 0 12px 12px; }
.history-row > div { display: flex; justify-content: space-between; gap: 20px; }
.history-row span,
.history-row small { color: #687185; }
.history-row > small { display: block; margin-top: 5px; line-height: 1.5; }
.history-row.legacy { margin-top: 8px; border: 0; border-radius: 10px; background: #eef0f5; }
.history-row-actions { display: flex; align-items: center; gap: 10px; }

@media (max-width: 760px) {
  .question-book-context {
    min-height: 62px;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 10px;
    padding: 8px 12px;
  }

  .question-book-context__copy > span { display: none; }
  .question-book-context__copy > strong { font-size: 12px; }
  .question-book-views { grid-column: 1 / -1; grid-row: 2; width: 100%; order: 3; }
  .question-book-views button { flex: 1; min-width: 0; padding: 0 6px; }
  .question-book-context__state { grid-column: 2; grid-row: 1; }
  .practice-selection-policy { display: none; }

  .question-book-empty {
    min-height: calc(100% - 98px);
    display: flex;
    gap: 24px;
    padding: 30px 20px;
    overflow: auto;
  }

  .question-book-empty__intro {
    gap: 12px;
    padding: 0;
    border-right: 0;
    border-bottom: 0;
  }

  .question-book-empty__icon { width: 38px; height: 38px; }
  .question-book-empty__intro > div { gap: 6px; }
  .question-book-empty__intro strong { font-size: 19px; }
  .question-book-empty__intro p { font-size: 12px; line-height: 1.6; }

  .question-bank-rebuild {
    width: 100%;
    gap: 11px;
    margin: 0;
  }

  .workflow-band,
  .question-stage,
  .history-list { width: calc(100% - 24px); }

  .workflow-band { grid-template-columns: 1fr; gap: 8px; }
  .question-stage,
  .history-list { padding: 12px 0 22px; }

  .question-content {
    padding: 18px 16px 0;
    border-radius: 12px;
    box-shadow: 0 4px 14px rgba(29, 34, 59, .06);
  }

  .question-meta > div { gap: 8px; }
  .question-prompt { font-size: 13px; }
  .question-task { padding-left: 11px; }
  .question-task > header { display: grid; gap: 2px; }
  .question-material > summary { grid-template-columns: 32px minmax(0, 1fr) 20px; gap: 8px; }
  .question-material__action > span {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
  }

  .question-prompt :deep(h1) { font-size: 19px; }
  .question-prompt :deep(h2) { font-size: 16px; }

  .practice-actions {
    gap: 8px;
    margin: 18px -16px 0;
    padding: 10px 16px max(10px, env(safe-area-inset-bottom));
  }

  .support-actions { gap: 4px; }
  .icon-command { width: 34px; min-height: 34px; }
  .text-command { width: 36px; min-height: 34px; padding: 0; font-size: 0; }
  .primary-command { min-height: 36px; padding: 0 10px; }

  .hint-result,
  .guidance-turn,
  .stepwise-verdict { grid-template-columns: 1fr; gap: 3px; }
  .guidance-turn small { grid-column: 1; }
  .guidance-compose button { justify-self: stretch; }
  .answer-diagnosis dl { grid-template-columns: 1fr; }
  .answer-diagnosis > header { align-items: flex-start; }
  .rubric-list > div { grid-template-columns: 18px 1fr; }
  .rubric-list small { grid-column: 2; }
}

@media (prefers-reduced-motion: reduce) {
  .question-bank-rebuild__progress b,
  .question-material__action svg { transition: none; }
}
</style>
