<template>
  <section class="question-bank-panel" aria-labelledby="question-bank-title">
    <header class="question-bank-panel__header">
      <div>
        <p>{{ t('questionBank.eyebrow', '教师工作区') }}</p>
        <h3 id="question-bank-title">{{ t('questionBank.title', '课程题库质量管理') }}</h3>
      </div>
      <button type="button" :disabled="loading || rebuilding" @click="rebuild()">
        <RefreshCw :size="14" :class="{ spin: rebuilding }" />
        {{ t('questionBank.rebuild', '重新整理') }}
      </button>
    </header>

    <section
      v-if="rebuildJob"
      class="question-bank-progress"
      role="status"
      aria-live="polite"
    >
      <div>
        <strong>{{ rebuildJob.message || rebuildStageLabel }}</strong>
        <span>{{ rebuildStageLabel }}</span>
      </div>
      <b>{{ rebuildJob.progress }}%</b>
      <i><span :style="{ width: `${rebuildJob.progress}%` }"></span></i>
    </section>

    <div v-if="loading" class="question-bank-panel__state">
      <LoaderCircle :size="18" class="spin" />
      {{ t('questionBank.loading', '正在读取题库') }}
    </div>
    <div v-else-if="errorMessage" class="question-bank-panel__state question-bank-panel__state--error">
      <TriangleAlert :size="18" />
      <span>{{ errorMessage }}</span>
      <button type="button" @click="load">{{ t('common.retry', '重试') }}</button>
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
        </header>
        <div class="assessment-matrix__rows">
          <article v-for="row in objectiveRows" :key="row.objective_id">
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
                type="search"
                :placeholder="t('questionBank.searchQuestion', '搜索题目内容')"
              />
            </label>
            <select v-model="browserStatus">
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
          v-for="item in browseItems"
          :key="item.revision_id"
          data-testid="question-review-item"
          class="question-review-item"
        >
          <header>
            <span>{{ roleLabel(item.assessment_role) }}</span>
            <small :data-status="item.lifecycle_status">
              {{ itemStatusLabel(item) }}
            </small>
          </header>
          <p>{{ item.prompt }}</p>
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
        </article>
      </div>
      <div v-else class="question-bank-panel__empty">
        <CircleCheck :size="21" />
        <strong>{{ t('questionBank.noMatchingQuestions', '没有符合条件的题目') }}</strong>
        <span>{{ t('questionBank.noMatchingQuestionsHelp', '调整搜索内容或状态筛选后再试。') }}</span>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import {
  Check,
  CircleCheck,
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
const bundleRevisionId = ref('')
const coverage = ref<Record<string, number>>({})
const reviewQueue = ref<Record<string, any>>({})
const webEnrichment = ref<Record<string, unknown>>({})
const assessmentProfile = ref<Record<string, any>>({})
const assessmentObjectives = ref<AssessmentObjective[]>([])
const items = ref<QuestionBankItem[]>([])
const reviewNotes = reactive<Record<string, string>>({})
const rebuildJob = ref<QuestionBankRebuildJob | null>(null)
const solutionLoadingRevision = ref('')
const solutions = reactive<Record<string, Record<string, any>>>({})
const browserQuery = ref('')
const browserStatus = ref<'all' | 'published' | 'mandatory' | 'rework'>('all')

const activeItems = computed(() => items.value.filter(
  item => item.lifecycle_status !== 'retired',
))
const publishedCount = computed(() => activeItems.value.filter(
  item => item.lifecycle_status === 'approved',
).length)
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

onMounted(load)
watch(() => props.courseId, () => { void load() })

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

async function rebuild(nodeId?: string) {
  if (!props.courseId || rebuilding.value) return
  rebuilding.value = true
  errorMessage.value = ''
  try {
    const scopedNodeId = String(nodeId || '')
    await runQuestionBankRebuild(
      props.courseId,
      {
        request_id: crypto.randomUUID(),
        scope: scopedNodeId ? 'nodes' : 'course',
        node_ids: scopedNodeId ? [scopedNodeId] : [],
        mode: 'incremental',
      },
      {
        onUpdate: job => {
          rebuildJob.value = job
        },
      },
    )
    await load()
  } catch (error: any) {
    errorMessage.value = error?.message || t(
      'questionBank.rebuildFailed',
      '题库整理失败，原有课程与题目未被覆盖。',
    )
  } finally {
    rebuilding.value = false
  }
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
.question-bank-panel__header button, .question-bank-panel__state button { display: inline-flex; align-items: center; gap: 6px; padding: 7px 10px; border: 1px solid var(--lz-border); border-radius: 8px; color: var(--lz-text-secondary); background: #fff; cursor: pointer; }
.question-bank-summary { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
.question-bank-summary article { display: grid; gap: 4px; padding: 12px; border-radius: 10px; background: var(--lz-surface-muted); }
.question-bank-summary span, .question-bank-summary small { color: var(--lz-text-muted); font-size: 10px; }
.question-bank-summary strong { color: var(--lz-text-strong); font-size: 14px; }
.question-bank-progress { display:grid; grid-template-columns:1fr auto; gap:8px 12px; padding:12px 14px; border:1px solid #bfdbfe; border-radius:10px; background:#eff6ff; }.question-bank-progress div { display:grid; gap:2px; }.question-bank-progress strong { color:#1e3a8a; font-size:12px; }.question-bank-progress span,.question-bank-progress b { color:#475569; font-size:10px; }.question-bank-progress i { grid-column:1/-1; height:5px; overflow:hidden; border-radius:999px; background:#dbeafe; }.question-bank-progress i span { display:block; height:100%; border-radius:inherit; background:#2563eb; transition:width .25s ease; }
.assessment-profile,.assessment-matrix { display:grid; gap:10px; padding:13px; border:1px solid var(--lz-border); border-radius:11px; background:#fff; }.assessment-profile header,.assessment-matrix>header { display:flex; align-items:flex-start; justify-content:space-between; gap:12px; }.assessment-profile header div,.assessment-matrix>header div { display:grid; gap:3px; }.assessment-profile span,.assessment-matrix span { color:var(--lz-text-muted); font-size:10px; }.assessment-profile strong,.assessment-matrix strong { color:var(--lz-text-strong); font-size:12px; }.assessment-profile small,.assessment-matrix small,.assessment-profile p { margin:0; color:var(--lz-text-muted); font-size:10px; line-height:1.55; }
.assessment-matrix__rows { display:grid; gap:6px; }.assessment-matrix__rows article { display:grid; grid-template-columns:minmax(0,1fr) auto auto; align-items:center; gap:10px; padding:9px 10px; border-radius:8px; background:var(--lz-surface-muted); }.assessment-matrix__rows article>div { min-width:0; display:grid; gap:3px; }.assessment-matrix__rows article>strong { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }.assessment-matrix__rows article>span { padding:3px 6px; border-radius:999px; color:#475569; background:#e2e8f0; }.assessment-matrix__rows article>span[data-status="covered"] { color:#047857; background:#d1fae5; }.assessment-matrix__rows article>span[data-status="review"] { color:#b45309; background:#fef3c7; }.assessment-matrix__rows article>span[data-status="failed"] { color:#b91c1c; background:#fee2e2; }.assessment-matrix__rows button { display:inline-flex; align-items:center; gap:5px; padding:6px 8px; border:1px solid var(--lz-border); border-radius:7px; color:var(--lz-text-secondary); background:#fff; font-size:10px; }
.question-browser { position:sticky; top:0; z-index:2; padding:10px 12px; border:1px solid var(--lz-border); border-radius:10px; background:rgba(255,255,255,.96); backdrop-filter:blur(8px); }
.question-browser>header { display:flex; align-items:center; justify-content:space-between; gap:12px; }
.question-browser>header>div:first-child { display:flex; align-items:baseline; gap:7px; }
.question-browser strong { color:var(--lz-text-strong); font-size:12px; }
.question-browser small { color:var(--lz-text-muted); font-size:10px; }
.question-browser__controls { display:flex; align-items:center; gap:8px; }
.question-browser__controls label { min-width:220px; display:flex; align-items:center; gap:7px; padding:0 9px; border:1px solid var(--lz-border); border-radius:8px; color:var(--lz-text-muted); background:#fff; }
.question-browser__controls input { min-width:0; width:100%; height:31px; border:0; outline:0; color:var(--lz-text); background:transparent; font-size:11px; }
.question-browser__controls select { height:33px; padding:0 28px 0 9px; border:1px solid var(--lz-border); border-radius:8px; color:var(--lz-text-secondary); background:#fff; font-size:11px; }
.question-review-list { display: grid; gap: 11px; }
.question-review-item { display: grid; gap: 10px; padding: 14px; border: 1px solid var(--lz-border); border-radius: 11px; background: #fff; }
.question-review-item > header, .question-review-item > footer { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.question-review-item > header span { color: var(--lz-brand-strong); font-size: 11px; font-weight: 750; }
.question-review-item > header small { padding:3px 7px; border-radius:999px; color:#b45309; background:#fef3c7; font-size:10px; }
.question-review-item > header small[data-status="approved"] { color:#047857; background:#d1fae5; }
.question-review-item > header small[data-status="rejected"] { color:#b91c1c; background:#fee2e2; }
.question-review-item p { margin: 0; color: var(--lz-text); font-size: 12px; line-height: 1.65; white-space: pre-line; }
.question-review-item dl { display: flex; flex-wrap: wrap; gap: 14px; margin: 0; }
.question-review-item dl div { display: flex; gap: 5px; font-size: 10px; }
.question-review-item dt { color: var(--lz-text-muted); }
.question-review-item dd { margin: 0; color: var(--lz-text-secondary); }
.question-review-item textarea { min-height: 54px; padding: 8px 9px; border: 1px solid var(--lz-border); border-radius: 8px; resize: vertical; color: var(--lz-text); font: inherit; font-size: 11px; }
.question-review-item__solution { justify-self:start; display:inline-flex; align-items:center; gap:6px; padding:6px 8px; border:1px solid var(--lz-border); border-radius:7px; color:var(--lz-text-secondary); background:#fff; font-size:10px; }.question-solution-diff { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px; }.question-solution-diff>div { min-width:0; display:grid; gap:5px; }.question-solution-diff strong { color:var(--lz-text-secondary); font-size:10px; }.question-solution-diff pre { max-height:220px; overflow:auto; margin:0; padding:9px; border-radius:8px; color:#334155; background:#f8fafc; font:10px/1.55 ui-monospace,SFMono-Regular,Consolas,monospace; white-space:pre-wrap; overflow-wrap:anywhere; }
.question-review-item footer { justify-content: flex-end; }
.question-review-item footer button { display: inline-flex; align-items: center; gap: 5px; padding: 7px 11px; border-radius: 8px; cursor: pointer; }
.question-review-item__reject { border: 1px solid #fecaca; color: #b91c1c; background: #fff; }
.question-review-item__approve { border: 1px solid var(--lz-brand-strong); color: #fff; background: var(--lz-brand-strong); }
.question-bank-panel__state, .question-bank-panel__empty { min-height: 100px; display: flex; align-items: center; justify-content: center; gap: 8px; color: var(--lz-text-muted); font-size: 12px; }
.question-bank-panel__state--error { color: #b45309; }
.question-bank-panel__empty { flex-direction: column; text-align: center; }
.question-bank-panel__empty strong { color: var(--lz-text-strong); }
.question-bank-panel__empty span { max-width: 420px; font-size: 11px; }
.spin { animation: question-bank-spin .9s linear infinite; }
@keyframes question-bank-spin { to { transform: rotate(360deg); } }
@media (max-width: 720px) { .question-bank-summary { grid-template-columns: 1fr; }.assessment-matrix__rows article { grid-template-columns:1fr auto; }.assessment-matrix__rows button { grid-column:1/-1; justify-self:start; }.question-solution-diff { grid-template-columns:1fr; }.question-browser>header,.question-browser__controls { align-items:stretch; flex-direction:column; }.question-browser__controls label { min-width:0; } }
</style>
