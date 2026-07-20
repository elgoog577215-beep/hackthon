<template>
  <section class="question-bank-panel" aria-labelledby="question-bank-title">
    <header class="question-bank-panel__header">
      <div>
        <p>{{ t('questionBank.eyebrow', '教师工作区') }}</p>
        <h3 id="question-bank-title">{{ t('questionBank.title', '课程题库质量管理') }}</h3>
      </div>
      <div class="question-bank-panel__header-action">
        <div>
          <small>{{ generationActionHelp }}</small>
          <span v-if="canContinueGeneration" data-testid="chapter-generation-checkpoint">
            已发布新版章节 {{ completedChapters }}/{{ totalChapters }}
          </span>
        </div>
        <div class="question-bank-panel__header-buttons">
          <button
            v-if="canContinueGeneration"
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
            data-testid="rebuild-course-question-bank"
            :disabled="loading || rebuilding"
            @click="rebuild(undefined, false)"
          >
            <RefreshCw :size="14" :class="{ spin: rebuilding }" />
            {{ rebuilding
              ? t('questionBank.regeneratingCourse', '正在重新生成课程题目')
              : t('questionBank.regenerateCourse', '重新生成整门课程题目') }}
          </button>
        </div>
      </div>
    </header>

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
      <i><span :style="{ width: `${rebuildJob.progress}%` }"></span></i>
      <small v-if="rebuildErrorMessage" class="question-bank-progress__error">
        {{ rebuildErrorMessage }}
      </small>
    </section>

    <div v-if="loading" class="question-bank-panel__state">
      <LoaderCircle :size="18" class="spin" />
      {{ t('questionBank.loading', '正在读取题库') }}
    </div>
    <div v-else-if="errorMessage" class="question-bank-panel__state question-bank-panel__state--error">
      <TriangleAlert :size="18" />
      <span>{{ errorMessage }}</span>
      <button
        type="button"
        data-testid="rebuild-missing-question-bank"
        :disabled="rebuilding"
        @click="rebuild(undefined, false)"
      >
        <RefreshCw :size="14" :class="{ spin: rebuilding }" />
        {{ rebuilding
          ? t('questionBank.regeneratingCourse', '正在重新生成课程题目')
          : t('questionBank.rebuildMissing', '重新整理题库') }}
      </button>
    </div>

    <template v-else>
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
        <p>{{ profileCapabilities }}</p>
      </section>

      <section class="assessment-matrix" data-testid="assessment-coverage-matrix">
        <header>
          <div>
            <span>{{ t('questionBank.matrix', '目标—题型—来源—验证器覆盖矩阵') }}</span>
            <small>{{ t('questionBank.matrixHelp', '按节点查看阻断原因并安全重建') }}</small>
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

            <nav
              v-if="coveredObjectivePageCount > 1"
              class="assessment-matrix__pagination"
              data-testid="objective-pagination"
              :aria-label="t('questionBank.objective.pagination', '已覆盖目标分页')"
            >
              <span class="assessment-matrix__page-range">
                第 {{ coveredObjectivePageStart }}–{{ coveredObjectivePageEnd }} 条，共 {{ coveredObjectiveRows.length }} 条
              </span>
              <div class="assessment-matrix__page-buttons">
                <button
                  type="button"
                  :disabled="coveredObjectivePage === 1"
                  @click="setCoveredObjectivePage(coveredObjectivePage - 1)"
                >
                  {{ t('common.previousPage', '上一页') }}
                </button>
                <template v-for="item in coveredObjectivePageItems" :key="item.key">
                  <span v-if="item.page === null" aria-hidden="true">…</span>
                  <button
                    v-else
                    type="button"
                    :class="{ active: item.page === coveredObjectivePage }"
                    :aria-current="item.page === coveredObjectivePage ? 'page' : undefined"
                    :data-testid="`objective-page-${item.page}`"
                    @click="setCoveredObjectivePage(item.page)"
                  >
                    {{ item.page }}
                  </button>
                </template>
                <button
                  type="button"
                  :disabled="coveredObjectivePage === coveredObjectivePageCount"
                  @click="setCoveredObjectivePage(coveredObjectivePage + 1)"
                >
                  {{ t('common.nextPage', '下一页') }}
                </button>
              </div>
              <form
                class="assessment-matrix__page-jump"
                data-testid="objective-page-jump-form"
                @submit.prevent="jumpToCoveredObjectivePage"
              >
                <label for="assessment-matrix-page-input">
                  {{ t('common.jumpTo', '跳至') }}
                </label>
                <input
                  id="assessment-matrix-page-input"
                  v-model="coveredObjectivePageInput"
                  data-testid="objective-page-jump-input"
                  type="number"
                  inputmode="numeric"
                  min="1"
                  :max="coveredObjectivePageCount"
                  :aria-label="t('questionBank.objective.jumpToPage', '跳转到页码')"
                />
                <span>页</span>
                <button type="submit" data-testid="objective-page-jump">
                  {{ t('common.jump', '跳转') }}
                </button>
              </form>
            </nav>
          </div>
        </section>

        <div v-if="!objectiveRows.length" class="assessment-matrix__empty">
          {{ t('questionBank.objective.empty', '暂无测评目标') }}
        </div>
      </section>

      <section class="question-browser">
        <header>
          <div>
            <strong>{{ t('questionBank.browseTitle', '浏览全部题目') }}</strong>
            <small>{{ browseItems.length }} / {{ activeItems.length }}</small>
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
            <select v-model="browserStatus" data-testid="question-status-filter">
              <option value="all">{{ t('questionBank.filter.all', '全部状态') }}</option>
              <option value="published">{{ t('questionBank.filter.published', '已发布') }}</option>
              <option value="mandatory">{{ t('questionBank.filter.mandatory', '发布前审核') }}</option>
              <option value="rework">{{ t('questionBank.filter.rework', '重做中') }}</option>
            </select>
          </div>
        </header>
      </section>

      <div v-if="browseItems.length" class="question-review-list">
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
            @click="toggleQuestionDetails(item)"
          >
            <span class="question-review-item__summary-main">
              <span class="question-review-item__role">
                {{ roleLabel(item.assessment_role) }}
              </span>
              <strong class="question-review-item__preview">
                {{ item.prompt }}
              </strong>
              <span class="question-review-item__meta">
                {{ sourceLabel(item.source_records) }}
                · {{ item.validation_mode || '-' }}
              </span>
            </span>
            <span class="question-review-item__summary-action">
              <small :data-status="item.lifecycle_status">
                {{ itemStatusLabel(item) }}
              </small>
              <span>
                {{ isQuestionExpanded(item)
                  ? t('questionBank.collapseReview', '收起审核')
                  : t('questionBank.expandReview', '展开审核') }}
                <ChevronUp v-if="isQuestionExpanded(item)" :size="15" />
                <ChevronDown v-else :size="15" />
              </span>
            </span>
          </button>
          <div
            v-if="isQuestionExpanded(item)"
            :id="`question-details-${item.revision_id}`"
            class="question-review-item__details"
          >
            <p class="question-review-item__prompt">
              {{ item.prompt }}
            </p>
            <dl>
              <div>
                <dt>{{ t('questionBank.quality', '质量') }}</dt>
                <dd>{{ item.quality_report?.passed ? t('questionBank.qualityPassed', '自动检查通过') : t('questionBank.qualityFailed', '需要修正') }}</dd>
              </div>
              <div>
                <dt>{{ t('questionBank.source', '来源') }}</dt>
                <dd>{{ sourceLabel(item.source_records) }}</dd>
              </div>
              <div>
                <dt>{{ t('questionBank.validator', '验证器') }}</dt>
                <dd>{{ item.validation_mode || '-' }}</dd>
              </div>
            </dl>
            <section
              v-if="item.design_brief_summary?.schema_version"
              class="question-generation-audit"
              data-testid="question-generation-audit"
            >
              <header>
                <strong>生成与质量闭环</strong>
                <small>{{ item.design_brief_summary.semantics_registry_id || item.question_type }}</small>
              </header>
              <div class="question-generation-audit__grid">
                <span>
                  内容 RAG
                  <b :data-status="item.design_brief_summary.content_coverage ? 'passed' : 'warning'">
                    {{ item.design_brief_summary.content_coverage ? '已覆盖' : '缺口回退' }}
                  </b>
                </span>
                <span>
                  题型方法 RAG
                  <b :data-status="item.design_brief_summary.method_coverage ? 'passed' : 'warning'">
                    {{ item.design_brief_summary.method_coverage ? '已覆盖' : '内置模板' }}
                  </b>
                </span>
                <span>
                  语义预检
                  <b :data-status="item.semantic_preflight?.passed ? 'passed' : 'failed'">
                    {{ item.semantic_preflight?.passed ? '通过' : '未通过' }}
                  </b>
                </span>
                <span>
                  首轮生成
                  <b :data-status="item.generation_audit_summary?.first_pass_passed ? 'passed' : 'warning'">
                    {{ item.generation_audit_summary?.first_pass_passed
                      ? '一次通过'
                      : `修复 ${item.generation_audit_summary?.repair_count || 0} 次` }}
                  </b>
                </span>
                <span>
                  LLM 语义评审
                  <b>
                    {{ item.generation_audit_summary?.semantic_reviewer_trigger
                      ? '已调用'
                      : '规则通过，未调用' }}
                  </b>
                </span>
              </div>
              <p v-if="item.generation_audit_summary?.issue_codes?.length">
                问题代码：{{ item.generation_audit_summary.issue_codes.join('、') }}
              </p>
            </section>
            <button
              type="button"
              class="question-review-item__solution"
              data-testid="load-question-solution"
              :disabled="solutionLoadingRevision === item.revision_id"
              @click="loadSolution(item)"
            >
              <LoaderCircle
                v-if="solutionLoadingRevision === item.revision_id"
                :size="14"
                class="spin"
              />
              <Eye v-else :size="14" />
              {{ t('questionBank.solutionDiff', '查看答案与独立验证') }}
            </button>
            <section
              v-if="solutions[item.revision_id]"
              class="question-solution-diff"
            >
              <div>
                <strong>{{ t('questionBank.canonicalAnswer', '标准答案或量规') }}</strong>
                <pre>{{ solutionAnswer(solutions[item.revision_id] || {}) }}</pre>
              </div>
              <div>
                <strong>{{ t('questionBank.independentValidation', '独立求解与验证') }}</strong>
                <pre>{{ solutionValidation(solutions[item.revision_id] || {}) }}</pre>
              </div>
            </section>
            <textarea
              v-model="reviewNotes[item.revision_id]"
              :placeholder="t('questionBank.reworkNote', '可选：说明哪里有问题，帮助下一版改进')"
            />
            <footer>
              <button
                type="button"
                class="question-review-item__reject"
                data-testid="rework-question"
                :disabled="actingRevision === item.revision_id"
                @click="rework(item)"
              >
                <RefreshCw
                  v-if="actingRevision === item.revision_id"
                  :size="14"
                  class="spin"
                />
                <X v-else :size="14" />
                {{ item.lifecycle_status === 'rejected'
                  ? t('questionBank.retryRework', '重新尝试')
                  : t('questionBank.rework', '打回重做') }}
              </button>
              <button
                v-if="item.lifecycle_status === 'needs_review'"
                type="button"
                class="question-review-item__approve"
                data-testid="approve-question"
                :disabled="actingRevision === item.revision_id"
                @click="approve(item)"
              >
                <Check :size="14" />{{ t('questionBank.approve', '批准') }}
              </button>
            </footer>
          </div>
        </article>
      </div>
      <nav
        v-if="questionPageCount > 1"
        class="question-browser__pagination"
        data-testid="question-pagination"
        :aria-label="t('questionBank.questionPagination', '题目列表分页')"
      >
        <span class="question-browser__page-range">
          第 {{ questionPageStart }}–{{ questionPageEnd }} 条，共 {{ browseItems.length }} 条
        </span>
        <div class="question-browser__page-buttons">
          <button
            type="button"
            :disabled="questionPage === 1"
            @click="setQuestionPage(questionPage - 1)"
          >
            {{ t('common.previousPage', '上一页') }}
          </button>
          <template v-for="item in questionPageItems" :key="item.key">
            <span v-if="item.page === null" aria-hidden="true">…</span>
            <button
              v-else
              type="button"
              :class="{ active: item.page === questionPage }"
              :aria-current="item.page === questionPage ? 'page' : undefined"
              :data-testid="`question-page-${item.page}`"
              @click="setQuestionPage(item.page)"
            >
              {{ item.page }}
            </button>
          </template>
          <button
            type="button"
            :disabled="questionPage === questionPageCount"
            @click="setQuestionPage(questionPage + 1)"
          >
            {{ t('common.nextPage', '下一页') }}
          </button>
        </div>
        <form
          class="question-browser__page-jump"
          data-testid="question-page-jump-form"
          @submit.prevent="jumpToQuestionPage"
        >
          <label for="question-browser-page-input">
            {{ t('common.jumpTo', '跳至') }}
          </label>
          <input
            id="question-browser-page-input"
            v-model="questionPageInput"
            data-testid="question-page-jump-input"
            type="number"
            inputmode="numeric"
            min="1"
            :max="questionPageCount"
            :aria-label="t('questionBank.jumpToQuestionPage', '跳转到题目页码')"
          />
          <span>页</span>
          <button type="submit" data-testid="question-page-jump">
            {{ t('common.jump', '跳转') }}
          </button>
        </form>
      </nav>
      <div v-if="!browseItems.length" class="question-bank-panel__empty">
        <CircleCheck :size="21" />
        <strong>{{ t('questionBank.noMatchingQuestions', '没有符合条件的题目') }}</strong>
        <span>{{ t('questionBank.noMatchingQuestionsHelp', '调整搜索内容或状态筛选后再试。') }}</span>
      </div>
    </template>
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
  Check,
  ChevronDown,
  ChevronUp,
  CircleCheck,
  Ellipsis,
  Eye,
  LoaderCircle,
  RefreshCw,
  Search,
  TriangleAlert,
  X,
} from 'lucide-vue-next'
import http from '@/utils/http'
import { t } from '@/shared/i18n'
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
  quality_report?: { passed?: boolean; status?: string }
  source_records?: Array<Record<string, unknown>>
  node_id?: string
  objective_id?: string
  archetype_id?: string
  validation_mode?: string
  generation_status?: string
  review_status?: string
  review_tier?: 'auto_publish' | 'sample_review' | 'mandatory_review'
  question_type?: string
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

const props = defineProps<{ courseId: string }>()
const emit = defineEmits<{ updated: [bundleRevisionId: string] }>()
const loading = ref(false)
const rebuilding = ref(false)
const actingRevision = ref('')
const errorMessage = ref('')
const rebuildErrorMessage = ref('')
const bundleRevisionId = ref('')
const coverage = ref<Record<string, number>>({})
const reviewQueue = ref<Record<string, any>>({})
const webEnrichment = ref<Record<string, unknown>>({})
const assessmentProfile = ref<Record<string, any>>({})
const assessmentObjectives = ref<AssessmentObjective[]>([])
const chapterRebuild = ref<Record<string, any>>({})
const items = ref<QuestionBankItem[]>([])
const reviewNotes = reactive<Record<string, string>>({})
const expandedQuestionRevision = ref('')
const rebuildJob = ref<QuestionBankRebuildJob | null>(null)
const solutionLoadingRevision = ref('')
const solutions = reactive<Record<string, Record<string, any>>>({})
const browserQuery = ref('')
const browserStatus = ref<'all' | 'published' | 'mandatory' | 'rework'>('all')
const questionPage = ref(1)
const questionPageInput = ref('1')
const coveredObjectivesExpanded = ref(false)
const coveredObjectivePage = ref(1)
const coveredObjectivePageInput = ref('1')
let rebuildAbortController: AbortController | null = null
const QUESTION_PAGE_SIZE = 10
const COVERED_OBJECTIVE_PAGE_SIZE = 10

const activeItems = computed(() => items.value.filter(
  item => item.lifecycle_status !== 'retired',
))
const publishedCount = computed(() => activeItems.value.filter(
  item => item.lifecycle_status === 'approved',
).length)
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
const generationActionHelp = computed(() => (
  canContinueGeneration.value
    ? `已完成的 ${completedChapters.value} 章不会重做；每完成一章立即替换该章旧题`
    : t(
      'questionBank.regenerateHelp',
      '新题通过质量检查后才会替换当前题库',
    )
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
const questionPageStart = computed(() => (
  (questionPage.value - 1) * QUESTION_PAGE_SIZE + 1
))
const questionPageEnd = computed(() => Math.min(
  browseItems.value.length,
  questionPage.value * QUESTION_PAGE_SIZE,
))
const questionPageItems = computed(() => {
  const total = questionPageCount.value
  const current = questionPage.value
  const pages = new Set<number>([1, total])
  for (
    let page = Math.max(1, current - 2);
    page <= Math.min(total, current + 2);
    page += 1
  ) {
    pages.add(page)
  }
  const sorted = [...pages].sort((left, right) => left - right)
  const result: Array<{ key: string; page: number | null }> = []
  sorted.forEach((page, index) => {
    const previous = sorted[index - 1]
    if (previous && page - previous > 1) {
      result.push({ key: `gap-${previous}-${page}`, page: null })
    }
    result.push({ key: `page-${page}`, page })
  })
  return result
})
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
const coveredObjectivePageItems = computed(() => {
  const total = coveredObjectivePageCount.value
  const current = coveredObjectivePage.value
  const pages = new Set<number>([1, total])
  for (
    let page = Math.max(1, current - 2);
    page <= Math.min(total, current + 2);
    page += 1
  ) {
    pages.add(page)
  }
  const sorted = [...pages].sort((left, right) => left - right)
  const result: Array<{ key: string; page: number | null }> = []
  sorted.forEach((page, index) => {
    const previous = sorted[index - 1]
    if (previous && page - previous > 1) {
      result.push({ key: `gap-${previous}-${page}`, page: null })
    }
    result.push({ key: `page-${page}`, page })
  })
  return result
})
const profileCapabilities = computed(() => {
  const archetypes = assessmentProfile.value.allowed_archetype_ids || []
  const validators = assessmentProfile.value.validator_ids || assessmentProfile.value.validation_modes || []
  return [
    archetypes.length ? `${archetypes.length} 种题型原型` : '',
    validators.length ? `${validators.length} 类验证器` : '',
  ].filter(Boolean).join(' · ') || t(
    'questionBank.profileCompiling',
    '画像已编译，详细能力随课程资料持续补全。',
  )
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

onMounted(() => {
  void load()
  void recoverActiveRebuild()
})
onBeforeUnmount(() => {
  rebuildAbortController?.abort()
})
watch(() => props.courseId, () => {
  rebuildAbortController?.abort()
  rebuildAbortController = null
  rebuildJob.value = null
  rebuildErrorMessage.value = ''
  browserQuery.value = ''
  browserStatus.value = 'all'
  setQuestionPage(1)
  expandedQuestionRevision.value = ''
  coveredObjectivesExpanded.value = false
  setCoveredObjectivePage(1)
  void load()
  void recoverActiveRebuild()
})
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
  questionPageInput.value = String(questionPage.value)
}

function jumpToQuestionPage() {
  const requestedPage = Number.parseInt(questionPageInput.value, 10)
  setQuestionPage(requestedPage)
}

function isQuestionExpanded(item: QuestionBankItem) {
  return expandedQuestionRevision.value === item.revision_id
}

function toggleQuestionDetails(item: QuestionBankItem) {
  expandedQuestionRevision.value = isQuestionExpanded(item)
    ? ''
    : item.revision_id
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
  coveredObjectivePageInput.value = String(coveredObjectivePage.value)
}

function jumpToCoveredObjectivePage() {
  const requestedPage = Number.parseInt(
    coveredObjectivePageInput.value,
    10,
  )
  setCoveredObjectivePage(requestedPage)
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
  try {
    const response = await http.get(
      `/api/courses/${props.courseId}/question-bank`,
      { silentError: true },
    )
    const data = response.data || {}
    bundleRevisionId.value = String(data.bundle_revision_id || '')
    coverage.value = data.coverage || {}
    reviewQueue.value = data.review_queue || {}
    webEnrichment.value = data.web_enrichment || {}
    assessmentProfile.value = data.assessment_profile || {}
    chapterRebuild.value = data.chapter_rebuild || {}
    assessmentObjectives.value = Array.isArray(data.assessment_objectives)
      ? data.assessment_objectives
      : []
    items.value = Array.isArray(data.items) ? data.items : []
  } catch (error: any) {
    errorMessage.value = error?.response?.status === 404
      ? t('questionBank.notBuilt', '该课程尚未整理题库，请点击“重新整理”。')
      : t('questionBank.loadFailed', '题库读取失败，请稍后重试。')
  } finally {
    loading.value = false
  }
}

async function rebuild(nodeId?: string, resumeExisting = true) {
  if (!props.courseId || rebuilding.value) return
  rebuildAbortController?.abort()
  const controller = new AbortController()
  rebuildAbortController = controller
  rebuilding.value = true
  errorMessage.value = ''
  rebuildErrorMessage.value = ''
  rebuildJob.value = null
  try {
    const scopedNodeId = String(nodeId || '')
    await runQuestionBankRebuild(
      props.courseId,
      {
        request_id: crypto.randomUUID(),
        scope: scopedNodeId ? 'nodes' : 'course',
        node_ids: scopedNodeId ? [scopedNodeId] : [],
        mode: scopedNodeId ? 'incremental' : 'full',
        ...(!scopedNodeId ? { resume_existing: resumeExisting } : {}),
      },
      {
        maxPolls: scopedNodeId ? 450 : 3600,
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
        request_id: crypto.randomUUID(),
        scope: 'items',
        node_ids: [],
        revision_ids: [item.revision_id],
        mode: 'incremental',
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

function roleLabel(role: string) {
  const labels: Record<string, string> = {
    cross_chapter_transfer: t('questionBank.role.crossChapter', '跨章节综合题'),
    coverage_task: t('questionBank.role.coverage', '目标覆盖题'),
    reference: t('questionBank.role.reference', '参考题'),
  }
  return labels[role] || t('questionBank.role.candidate', '候选题')
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

function solutionValidation(payload: Record<string, any>) {
  return formatValue(payload.solution_validation || '-')
}

function formatValue(value: unknown) {
  if (typeof value === 'string') return value
  return JSON.stringify(value, null, 2)
}
</script>

<style scoped>
.question-bank-panel { display: grid; gap: 16px; padding: 18px; border: 1px solid var(--lz-border); border-radius: var(--lz-radius-surface); background: var(--lz-surface); }
.question-bank-panel__header { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.question-bank-panel__header p { margin: 0 0 3px; color: var(--lz-text-muted); font-size: 10px; font-weight: 750; text-transform: uppercase; letter-spacing: .08em; }
.question-bank-panel__header h3 { margin: 0; color: var(--lz-text-strong); font-size: 15px; }
.question-bank-panel__header-action { display:flex; align-items:flex-end; gap:10px; }
.question-bank-panel__header-action>div:first-child { display:grid; max-width:250px; gap:3px; text-align:right; }
.question-bank-panel__header-action small,.question-bank-panel__header-action span { color:var(--lz-text-muted); font-size:10px; line-height:1.4; }
.question-bank-panel__header-action span { color:#047857; font-weight:700; }
.question-bank-panel__header-buttons { display:flex; align-items:center; gap:7px; }
.question-bank-panel__header button, .question-bank-panel__state button { display: inline-flex; align-items: center; gap: 6px; padding: 7px 10px; border: 1px solid var(--lz-border); border-radius: 8px; color: var(--lz-text-secondary); background: #fff; cursor: pointer; }
.question-bank-panel__header button:disabled { opacity:.55; cursor:not-allowed; }
.question-bank-summary { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
.question-bank-summary article { display: grid; gap: 4px; padding: 12px; border-radius: 10px; background: var(--lz-surface-muted); }
.question-bank-summary span, .question-bank-summary small { color: var(--lz-text-muted); font-size: 10px; }
.question-bank-summary strong { color: var(--lz-text-strong); font-size: 14px; }
.question-bank-progress { display:grid; grid-template-columns:1fr auto; gap:8px 12px; padding:12px 14px; border:1px solid #bfdbfe; border-radius:10px; background:#eff6ff; }.question-bank-progress div { display:grid; gap:2px; }.question-bank-progress strong { color:#1e3a8a; font-size:12px; }.question-bank-progress span,.question-bank-progress b { color:#475569; font-size:10px; }.question-bank-progress i { grid-column:1/-1; height:6px; overflow:hidden; border-radius:999px; background:#dbeafe; }.question-bank-progress i span { display:block; height:100%; border-radius:inherit; background:#2563eb; transition:width .25s ease; }.question-bank-progress[data-status="completed"],.question-bank-progress[data-status="waiting_review"] { border-color:#a7f3d0; background:#ecfdf5; }.question-bank-progress[data-status="completed"] strong,.question-bank-progress[data-status="waiting_review"] strong { color:#065f46; }.question-bank-progress[data-status="completed"] i,.question-bank-progress[data-status="waiting_review"] i { background:#d1fae5; }.question-bank-progress[data-status="completed"] i span,.question-bank-progress[data-status="waiting_review"] i span { background:#059669; }.question-bank-progress[data-status="failed"] { border-color:#fecaca; background:#fff7ed; }.question-bank-progress[data-status="failed"] strong,.question-bank-progress__error { color:#b91c1c; }.question-bank-progress__error { grid-column:1/-1; font-size:10px; }
.question-bank-progress__chapter { color:#1d4ed8; font-size:10px; }
.assessment-profile,.assessment-matrix { display:grid; gap:10px; padding:13px; border:1px solid var(--lz-border); border-radius:11px; background:#fff; }
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
.assessment-matrix__covered-toggle:focus-visible,.assessment-matrix__pagination button:focus-visible,.assessment-matrix__page-jump input:focus-visible,.assessment-matrix__menu summary:focus-visible,.question-browser__pagination button:focus-visible,.question-browser__page-jump input:focus-visible { outline:2px solid var(--lz-brand); outline-offset:2px; }
.assessment-matrix__covered-content { display:grid; gap:9px; }
.assessment-matrix__rows--covered article { min-height:42px; padding-block:5px; background:#f8fafc; }
.assessment-matrix__menu { position:relative; }
.assessment-matrix__menu summary { width:34px; height:34px; display:grid; place-items:center; border-radius:7px; color:var(--lz-text-secondary); cursor:pointer; list-style:none; }
.assessment-matrix__menu summary::-webkit-details-marker { display:none; }
.assessment-matrix__menu summary:hover,.assessment-matrix__menu[open] summary { color:var(--lz-brand-strong); background:var(--lz-brand-soft); }
.assessment-matrix__menu>div { position:absolute; top:38px; right:0; z-index:4; min-width:112px; padding:5px; border:1px solid var(--lz-border); border-radius:8px; background:#fff; box-shadow:0 10px 24px rgba(15,23,42,.12); }
.assessment-matrix__menu>div button { width:100%; justify-content:flex-start; border:0; }
.assessment-matrix__pagination { min-width:0; display:flex; flex-wrap:wrap; align-items:center; justify-content:flex-end; gap:8px 10px; padding:9px 10px; border-top:1px solid var(--lz-border); color:var(--lz-text-muted); font-size:10px; }
.assessment-matrix__page-range { flex:1 1 140px; color:var(--lz-text-secondary)!important; }
.assessment-matrix__page-buttons,.assessment-matrix__page-jump { min-width:0; display:flex; align-items:center; gap:5px; }
.assessment-matrix__page-buttons { flex-wrap:wrap; }
.assessment-matrix__page-jump { flex:0 0 auto; }
.assessment-matrix__pagination button { min-width:34px; height:34px; padding:0 8px; border:1px solid var(--lz-border); border-radius:7px; color:var(--lz-text-secondary); background:#fff; font-size:10px; cursor:pointer; }
.assessment-matrix__pagination button.active { border-color:var(--lz-brand); color:#fff; background:var(--lz-brand); }
.assessment-matrix__pagination button:disabled { opacity:.45; cursor:not-allowed; }
.assessment-matrix__page-jump label,.assessment-matrix__page-jump span { color:var(--lz-text-muted); font-size:10px; }
.assessment-matrix__page-jump input { width:48px; height:34px; padding:0 6px; border:1px solid var(--lz-border); border-radius:7px; color:var(--lz-text); background:#fff; font-size:11px; text-align:center; }
.assessment-matrix__page-jump button { min-width:auto; }
.assessment-matrix__empty { min-height:54px; display:grid; place-items:center; color:var(--lz-text-muted); font-size:10px; }
.question-browser { position:sticky; top:0; z-index:2; padding:10px 12px; border:1px solid var(--lz-border); border-radius:10px; background:rgba(255,255,255,.96); backdrop-filter:blur(8px); }
.question-browser>header { display:flex; align-items:center; justify-content:space-between; gap:12px; }
.question-browser>header>div:first-child { display:flex; align-items:baseline; gap:7px; }
.question-browser strong { color:var(--lz-text-strong); font-size:12px; }
.question-browser small { color:var(--lz-text-muted); font-size:10px; }
.question-browser__controls { display:flex; align-items:center; gap:8px; }
.question-browser__controls label { min-width:220px; display:flex; align-items:center; gap:7px; padding:0 9px; border:1px solid var(--lz-border); border-radius:8px; color:var(--lz-text-muted); background:#fff; }
.question-browser__controls input { min-width:0; width:100%; height:31px; border:0; outline:0; color:var(--lz-text); background:transparent; font-size:11px; }
.question-browser__controls select { height:33px; padding:0 28px 0 9px; border:1px solid var(--lz-border); border-radius:8px; color:var(--lz-text-secondary); background:#fff; font-size:11px; }
.question-browser__pagination { min-width:0; display:flex; flex-wrap:wrap; align-items:center; justify-content:flex-end; gap:8px 10px; padding:10px 12px; border:1px solid var(--lz-border); border-radius:10px; color:var(--lz-text-muted); background:#fff; font-size:10px; }
.question-browser__page-range { flex:1 1 140px; color:var(--lz-text-secondary); }
.question-browser__page-buttons,.question-browser__page-jump { min-width:0; display:flex; align-items:center; gap:5px; }
.question-browser__page-buttons { flex-wrap:wrap; }
.question-browser__page-jump { flex:0 0 auto; }
.question-browser__pagination button { min-width:34px; height:34px; padding:0 8px; border:1px solid var(--lz-border); border-radius:7px; color:var(--lz-text-secondary); background:#fff; font-size:10px; cursor:pointer; }
.question-browser__pagination button.active { border-color:var(--lz-brand); color:#fff; background:var(--lz-brand); }
.question-browser__pagination button:disabled { opacity:.45; cursor:not-allowed; }
.question-browser__page-jump label,.question-browser__page-jump span { color:var(--lz-text-muted); font-size:10px; }
.question-browser__page-jump input { width:48px; height:34px; padding:0 6px; border:1px solid var(--lz-border); border-radius:7px; color:var(--lz-text); background:#fff; font-size:11px; text-align:center; }
.question-browser__page-jump button { min-width:auto; }
.question-review-list { display:grid; gap:5px; }
.question-review-item { overflow:hidden; border:1px solid var(--lz-border); border-radius:10px; background:#fff; transition:border-color .15s ease,box-shadow .15s ease; }
.question-review-item:hover { border-color:#c7d2fe; }
.question-review-item.is-expanded { border-color:#c7d2fe; box-shadow:0 8px 22px rgba(30,41,59,.06); }
.question-review-item__summary { width:100%; min-height:53px; display:grid; grid-template-columns:minmax(0,1fr) auto; align-items:center; gap:14px; padding:7px 12px; border:0; color:inherit; background:#fff; text-align:left; cursor:pointer; }
.question-review-item__summary:hover { background:#fafbff; }
.question-review-item__summary:focus-visible { position:relative; z-index:1; outline:2px solid var(--lz-brand); outline-offset:-2px; }
.question-review-item__summary-main { min-width:0; display:grid; grid-template-columns:auto minmax(0,1fr) minmax(120px,auto); align-items:center; gap:10px; }
.question-review-item__role { color:var(--lz-brand-strong); font-size:10px; font-weight:750; white-space:nowrap; }
.question-review-item__preview { min-width:0; overflow:hidden; color:var(--lz-text); font-size:12px; font-weight:600; line-height:1.45; text-overflow:ellipsis; white-space:nowrap; }
.question-review-item__meta { max-width:210px; overflow:hidden; color:var(--lz-text-muted); font-size:10px; line-height:1.4; text-overflow:ellipsis; white-space:nowrap; }
.question-review-item__summary-action { display:flex; align-items:center; gap:10px; }
.question-review-item__summary-action>small { padding:3px 7px; border-radius:999px; color:#b45309; background:#fef3c7; font-size:10px; white-space:nowrap; }
.question-review-item__summary-action>small[data-status="approved"] { color:#047857; background:#d1fae5; }
.question-review-item__summary-action>small[data-status="rejected"] { color:#b91c1c; background:#fee2e2; }
.question-review-item__summary-action>span { display:inline-flex; align-items:center; gap:4px; color:var(--lz-brand-strong); font-size:10px; font-weight:700; white-space:nowrap; }
.question-review-item__details { display:grid; gap:10px; padding:13px; border-top:1px solid var(--lz-border); background:#fff; }
.question-review-item p { margin:0; color:var(--lz-text); font-size:12px; line-height:1.65; white-space:pre-line; }
.question-review-item dl { display:flex; flex-wrap:wrap; gap:14px; margin:0; }
.question-review-item dl div { display: flex; gap: 5px; font-size: 10px; }
.question-review-item dt { color: var(--lz-text-muted); }
.question-review-item dd { margin: 0; color: var(--lz-text-secondary); }
.question-review-item textarea { min-height: 54px; padding: 8px 9px; border: 1px solid var(--lz-border); border-radius: 8px; resize: vertical; color: var(--lz-text); font: inherit; font-size: 11px; }
.question-review-item__solution { justify-self:start; display:inline-flex; align-items:center; gap:6px; padding:6px 8px; border:1px solid var(--lz-border); border-radius:7px; color:var(--lz-text-secondary); background:#fff; font-size:10px; }.question-solution-diff { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px; }.question-solution-diff>div { min-width:0; display:grid; gap:5px; }.question-solution-diff strong { color:var(--lz-text-secondary); font-size:10px; }.question-solution-diff pre { max-height:220px; overflow:auto; margin:0; padding:9px; border-radius:8px; color:#334155; background:#f8fafc; font:10px/1.55 ui-monospace,SFMono-Regular,Consolas,monospace; white-space:pre-wrap; overflow-wrap:anywhere; }
.question-review-item footer { display:flex; align-items:center; justify-content:flex-end; gap:10px; }
.question-review-item footer button { display: inline-flex; align-items: center; gap: 5px; padding: 7px 11px; border-radius: 8px; cursor: pointer; }
.question-review-item__reject { border: 1px solid #fecaca; color: #b91c1c; background: #fff; }
.question-review-item__approve { border: 1px solid var(--lz-brand-strong); color: #fff; background: var(--lz-brand-strong); }
.question-bank-panel__state, .question-bank-panel__empty { min-height: 100px; display: flex; align-items: center; justify-content: center; gap: 8px; color: var(--lz-text-muted); font-size: 12px; }
.question-bank-panel__state--error { color: #b45309; }
.question-bank-panel__empty { flex-direction: column; text-align: center; }
.question-bank-panel__empty strong { color: var(--lz-text-strong); }
.question-bank-panel__empty span { max-width: 420px; font-size: 11px; }
.question-generation-audit { display:grid; gap:8px; padding:10px; border:1px solid #dbeafe; border-radius:9px; background:#f8fbff; }
.question-generation-audit>header { display:flex; align-items:center; justify-content:space-between; gap:10px; }
.question-generation-audit>header strong { color:#1e3a5f; font-size:11px; }
.question-generation-audit>header small { color:#64748b; font:9px/1.4 ui-monospace,SFMono-Regular,Consolas,monospace; }
.question-generation-audit__grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:6px; }
.question-generation-audit__grid span { display:flex; align-items:center; justify-content:space-between; gap:8px; padding:6px 8px; border-radius:7px; color:#64748b; background:#fff; font-size:9px; }
.question-generation-audit__grid b { color:#334155; font-weight:700; }
.question-generation-audit__grid b[data-status="passed"] { color:#047857; }
.question-generation-audit__grid b[data-status="warning"] { color:#b45309; }
.question-generation-audit__grid b[data-status="failed"] { color:#b91c1c; }
.question-generation-audit>p { margin:0; color:#b45309; font:9px/1.5 ui-monospace,SFMono-Regular,Consolas,monospace; overflow-wrap:anywhere; }
.spin { animation: question-bank-spin .9s linear infinite; }
@keyframes question-bank-spin { to { transform: rotate(360deg); } }
@media (max-width: 900px) { .question-review-item__summary-main { grid-template-columns:auto minmax(0,1fr); }.question-review-item__meta { grid-column:1/-1; max-width:none; } }
@media (max-width: 720px) { .question-bank-panel__header { align-items:flex-start; flex-direction:column; }.question-bank-panel__header-action { width:100%; align-items:flex-start; flex-direction:column; }.question-bank-panel__header-action>div:first-child { max-width:none; text-align:left; }.question-bank-panel__header-buttons { width:100%; flex-wrap:wrap; }.question-bank-summary { grid-template-columns: 1fr; }.assessment-matrix>header { align-items:flex-start; flex-direction:column; }.assessment-matrix__summary { text-align:left; }.assessment-matrix__rows article { grid-template-columns:minmax(0,1fr) auto auto; }.assessment-matrix__group--issues .assessment-matrix__rows article { grid-template-columns:1fr auto; }.assessment-matrix__group--issues .assessment-matrix__rows article>button { grid-column:1/-1; justify-self:start; }.assessment-matrix__covered-toggle { align-items:flex-start; flex-direction:column; }.assessment-matrix__pagination { grid-template-columns:1fr; justify-items:start; }.assessment-matrix__page-buttons { max-width:100%; flex-wrap:wrap; }.question-solution-diff { grid-template-columns:1fr; }.question-browser>header,.question-browser__controls { align-items:stretch; flex-direction:column; }.question-browser__controls label { min-width:0; }.question-review-item__summary { grid-template-columns:1fr; gap:8px; }.question-review-item__summary-action { justify-content:space-between; }.question-review-item__preview { white-space:normal; display:-webkit-box; overflow:hidden; -webkit-box-orient:vertical; -webkit-line-clamp:2; } }
</style>
