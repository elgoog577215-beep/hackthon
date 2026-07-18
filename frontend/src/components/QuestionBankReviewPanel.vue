<template>
  <section class="question-bank-panel" aria-labelledby="question-bank-title">
    <header class="question-bank-panel__header">
      <div>
        <p>{{ t('questionBank.eyebrow', '教师工作区') }}</p>
        <h3 id="question-bank-title">{{ t('questionBank.title', '课程题库与风险审核') }}</h3>
      </div>
      <button type="button" :disabled="loading || rebuilding" @click="rebuild">
        <RefreshCw :size="14" :class="{ spin: rebuilding }" />
        {{ t('questionBank.rebuild', '重新整理') }}
      </button>
    </header>

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
          <span>{{ t('questionBank.reviewQueue', '风险队列') }}</span>
          <strong>{{ t('questionBank.pendingCount', '待审核 {count}').replace('{count}', String(reviewQueue.blocking_count || 0)) }}</strong>
          <small>{{ t('questionBank.blockingOnly', '只列出阻断题') }}</small>
        </article>
        <article>
          <span>{{ t('questionBank.webSources', '联网补充') }}</span>
          <strong>{{ webStatusLabel }}</strong>
          <small>{{ t('questionBank.sourceCount', '{count} 个来源').replace('{count}', String(webEnrichment.source_count || 0)) }}</small>
        </article>
      </div>

      <div v-if="reviewItems.length" class="question-review-list">
        <article
          v-for="item in reviewItems"
          :key="item.revision_id"
          data-testid="question-review-item"
          class="question-review-item"
        >
          <header>
            <span>{{ roleLabel(item.assessment_role) }}</span>
            <small>{{ riskLabel(item.risk_flags) }}</small>
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
          </dl>
          <textarea
            v-model="reviewNotes[item.revision_id]"
            :placeholder="t('questionBank.reviewNote', '可选：填写审核说明')"
          />
          <footer>
            <button
              type="button"
              class="question-review-item__reject"
              :disabled="actingRevision === item.revision_id"
              @click="review(item, 'rejected')"
            >
              <X :size="14" />{{ t('questionBank.reject', '拒绝') }}
            </button>
            <button
              type="button"
              class="question-review-item__approve"
              data-testid="approve-question"
              :disabled="actingRevision === item.revision_id"
              @click="review(item, 'approved')"
            >
              <Check :size="14" />{{ t('questionBank.approve', '批准') }}
            </button>
          </footer>
        </article>
      </div>
      <div v-else class="question-bank-panel__empty">
        <CircleCheck :size="21" />
        <strong>{{ t('questionBank.noBlocking', '没有待处理的阻断题') }}</strong>
        <span>{{ t('questionBank.noBlockingHelp', '普通高质量题已自动生效；综合题仍需教师逐项确认。') }}</span>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import {
  Check,
  CircleCheck,
  LoaderCircle,
  RefreshCw,
  TriangleAlert,
  X,
} from 'lucide-vue-next'
import http from '@/utils/http'
import { t } from '@/shared/i18n'

interface QuestionBankItem {
  item_id: string
  revision_id: string
  prompt: string
  assessment_role: string
  lifecycle_status: string
  risk_flags: string[]
  quality_report?: { passed?: boolean; status?: string }
  source_records?: Array<Record<string, unknown>>
}

const props = defineProps<{ courseId: string }>()
const emit = defineEmits<{ updated: [bundleRevisionId: string] }>()
const loading = ref(false)
const rebuilding = ref(false)
const actingRevision = ref('')
const errorMessage = ref('')
const bundleRevisionId = ref('')
const coverage = ref<Record<string, number>>({})
const reviewQueue = ref<Record<string, number>>({})
const webEnrichment = ref<Record<string, unknown>>({})
const items = ref<QuestionBankItem[]>([])
const reviewNotes = reactive<Record<string, string>>({})

const reviewItems = computed(() => items.value.filter(item => item.lifecycle_status === 'needs_review'))
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
    const response = await http.get(`/api/courses/${props.courseId}/question-bank`)
    const data = response.data || {}
    bundleRevisionId.value = String(data.bundle_revision_id || '')
    coverage.value = data.coverage || {}
    reviewQueue.value = data.review_queue || {}
    webEnrichment.value = data.web_enrichment || {}
    items.value = Array.isArray(data.items) ? data.items : []
  } catch (error: any) {
    errorMessage.value = error?.response?.status === 404
      ? t('questionBank.notBuilt', '该课程尚未整理题库，请点击“重新整理”。')
      : t('questionBank.loadFailed', '题库读取失败，请稍后重试。')
  } finally {
    loading.value = false
  }
}

async function rebuild() {
  if (!props.courseId || rebuilding.value) return
  rebuilding.value = true
  errorMessage.value = ''
  try {
    await http.post(`/api/courses/${props.courseId}/question-bank/rebuild`, {
      request_id: crypto.randomUUID(),
    })
    await load()
  } catch {
    errorMessage.value = t('questionBank.rebuildFailed', '题库整理失败，原有课程与题目未被覆盖。')
  } finally {
    rebuilding.value = false
  }
}

async function review(item: QuestionBankItem, decision: 'approved' | 'rejected') {
  actingRevision.value = item.revision_id
  try {
    await http.post(
      `/api/courses/${props.courseId}/question-bank/items/${item.revision_id}/reviews`,
      {
        decision,
        note: reviewNotes[item.revision_id] || '',
        expected_bundle_revision_id: bundleRevisionId.value,
      },
    )
    await load()
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
.question-review-list { display: grid; gap: 11px; }
.question-review-item { display: grid; gap: 10px; padding: 14px; border: 1px solid var(--lz-border); border-radius: 11px; background: #fff; }
.question-review-item > header, .question-review-item > footer { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.question-review-item > header span { color: var(--lz-brand-strong); font-size: 11px; font-weight: 750; }
.question-review-item > header small { color: #b45309; font-size: 10px; }
.question-review-item p { margin: 0; color: var(--lz-text); font-size: 12px; line-height: 1.65; white-space: pre-line; }
.question-review-item dl { display: flex; flex-wrap: wrap; gap: 14px; margin: 0; }
.question-review-item dl div { display: flex; gap: 5px; font-size: 10px; }
.question-review-item dt { color: var(--lz-text-muted); }
.question-review-item dd { margin: 0; color: var(--lz-text-secondary); }
.question-review-item textarea { min-height: 54px; padding: 8px 9px; border: 1px solid var(--lz-border); border-radius: 8px; resize: vertical; color: var(--lz-text); font: inherit; font-size: 11px; }
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
@media (max-width: 720px) { .question-bank-summary { grid-template-columns: 1fr; } }
</style>
