<template>
  <div class="learning-overview">
    <header class="overview-header">
      <div class="overview-heading">
        <span class="overview-heading__icon" aria-hidden="true"><ChartNoAxesCombined :size="19" /></span>
        <div>
          <h1>{{ t('courseWorkspace.learningOverview.title', '学习概况') }}</h1>
          <p>{{ evidenceLevelLabel }}</p>
        </div>
      </div>
      <div class="overview-actions">
        <button type="button" :title="t('courseWorkspace.learningOverview.refresh', '刷新学习概况')" :aria-label="t('courseWorkspace.learningOverview.refresh', '刷新学习概况')" :disabled="loading" @click="refresh">
          <RefreshCw :size="17" :class="{ spinning: loading }" />
        </button>
        <button type="button" :title="t('courseWorkspace.learningOverview.export', '导出正式学习概况')" :aria-label="t('courseWorkspace.learningOverview.export', '导出正式学习概况')" :disabled="!model" @click="exportModel">
          <Download :size="17" />
        </button>
      </div>
    </header>

    <div v-if="loading && !model" class="overview-state" role="status">
      <LoaderCircle :size="20" class="spinning" />
      <span>{{ t('courseWorkspace.learningOverview.loading', '正在汇总正式学习证据') }}</span>
    </div>

    <div v-else-if="error && !model" class="overview-state overview-state--error" role="alert">
      <CircleAlert :size="20" />
      <div>
        <strong>{{ t('courseWorkspace.learningOverview.unavailable', '学习概况暂时不可用') }}</strong>
        <p>{{ t('courseWorkspace.learningOverview.unavailableBody', '课程阅读和练习仍可继续，可以稍后重试。') }}</p>
      </div>
    </div>

    <div v-else class="overview-body">
      <section class="overview-section overview-section--progress">
        <div class="section-heading">
          <div>
            <span>{{ t('courseWorkspace.learningOverview.progressEyebrow', '当前课程') }}</span>
            <h2>{{ t('courseWorkspace.learningOverview.progress', '阅读与掌握') }}</h2>
          </div>
          <span class="evidence-badge" :data-level="sufficiencyLevel">
            <ShieldCheck :size="14" />{{ evidenceLevelLabel }}
          </span>
        </div>

        <div class="metric-grid">
          <div class="metric">
            <strong>{{ summary.learned_objectives }}</strong>
            <span>{{ t('courseWorkspace.learningOverview.learned', '已学完') }}</span>
          </div>
          <div class="metric">
            <strong>{{ summary.mastered_objectives }}</strong>
            <span>{{ t('courseWorkspace.learningOverview.mastered', '已验证掌握') }}</span>
          </div>
          <div class="metric">
            <strong>{{ needsAttention.length }}</strong>
            <span>{{ t('courseWorkspace.learningOverview.attention', '待巩固目标') }}</span>
          </div>
        </div>

        <div class="progress-pair">
          <div>
            <span>{{ t('courseWorkspace.learningOverview.readingProgress', '阅读进度') }}</span>
            <strong>{{ readingPercentage }}%</strong>
          </div>
          <div class="progress-track"><span :style="{ width: `${readingPercentage}%` }"></span></div>
          <div>
            <span>{{ t('courseWorkspace.learningOverview.masteryProgress', '掌握验证') }}</span>
            <strong>{{ masteryPercentage }}%</strong>
          </div>
          <div class="progress-track progress-track--mastery"><span :style="{ width: `${masteryPercentage}%` }"></span></div>
        </div>
      </section>

      <section v-if="currentObjective" class="overview-section">
        <div class="section-heading">
          <div>
            <span>{{ t('courseWorkspace.learningOverview.currentEyebrow', '当前位置') }}</span>
            <h2>{{ currentObjective.node_name || t('courseWorkspace.learningOverview.currentObjective', '当前学习目标') }}</h2>
          </div>
          <span class="confidence-badge">{{ currentObjectiveIsCurrent ? confidenceLabel(currentObjective.confidence) : t('courseWorkspace.learningOverview.expiredEvidence', '证据已过期') }}</span>
        </div>
        <p v-if="currentObjective.statement" class="objective-statement">{{ currentObjective.statement }}</p>
        <div class="status-row">
          <span><BookOpenCheck :size="15" />{{ readingStatusLabel(currentObjective.reading_status) }}</span>
          <span><BadgeCheck :size="15" />{{ masteryStatusLabel(currentObjective.mastery_status) }}</span>
        </div>
        <div v-if="currentObjectiveIsCurrent && currentObjective.support_need?.status === 'needs_support'" class="support-callout">
          <CircleAlert :size="17" />
          <div>
            <strong>{{ t('courseWorkspace.learningOverview.supportNeeded', '当前有待处理证据') }}</strong>
            <p>{{ supportReasonLabel(currentObjective.support_need.reason_code) }}</p>
          </div>
        </div>
      </section>

      <section v-if="nextAction" class="overview-section next-action">
        <div class="next-action__icon" aria-hidden="true"><Route :size="18" /></div>
        <div>
          <span>{{ t('courseWorkspace.learningOverview.nextEyebrow', '统一下一步') }}</span>
          <strong>{{ nextAction.label }}</strong>
          <p>{{ nextAction.reason }}</p>
        </div>
      </section>

      <section class="overview-section evidence-section">
        <div class="section-heading">
          <div>
            <span>{{ t('courseWorkspace.learningOverview.evidenceEyebrow', '事实基础') }}</span>
            <h2>{{ t('courseWorkspace.learningOverview.evidence', '正式学习证据') }}</h2>
          </div>
          <strong>{{ evidenceCount }}</strong>
        </div>
        <div v-if="evidenceCount" class="evidence-breakdown">
          <div><ClipboardCheck :size="17" /><span>{{ t('courseWorkspace.learningOverview.formalAttempts', '正式练习') }}</span><strong>{{ formalAttemptCount }}</strong></div>
          <div><NotebookTabs :size="17" /><span>{{ t('courseWorkspace.learningOverview.records', '学习记录') }}</span><strong>{{ summary.active_record_count }}</strong></div>
          <div><ScanSearch :size="17" /><span>{{ t('courseWorkspace.learningOverview.coveredObjectives', '覆盖目标') }}</span><strong>{{ dataSufficiency.covered_objective_count }}</strong></div>
        </div>
        <p v-else class="empty-copy">{{ t('courseWorkspace.learningOverview.noEvidence', '先完成阅读确认、正式练习或保存学习记录，系统才会形成有依据的判断。') }}</p>
      </section>

      <section v-if="strengths.length || needsAttention.length" class="overview-section signal-grid">
        <div v-if="strengths.length" class="signal-group">
          <h2><BadgeCheck :size="17" />{{ t('courseWorkspace.learningOverview.strengths', '已有可靠优势') }}</h2>
          <ul>
            <li v-for="item in strengths" :key="item.objective_revision_id">
              <span>{{ item.node_name }}</span>
              <small>{{ confidenceLabel(item.confidence) }}</small>
            </li>
          </ul>
        </div>
        <div v-if="needsAttention.length" class="signal-group signal-group--attention">
          <h2><Focus :size="17" />{{ t('courseWorkspace.learningOverview.needsAttention', '当前待巩固') }}</h2>
          <ul>
            <li v-for="item in needsAttention" :key="item.objective_revision_id">
              <span>{{ item.node_name }}</span>
              <small>{{ supportReasonLabel(item.reason_code) }}</small>
            </li>
          </ul>
        </div>
      </section>

      <footer class="overview-policy">
        <Info :size="16" />
        <p>{{ t('courseWorkspace.learningOverview.policy', '学习概况只根据正式证据重算。阅读不等于掌握，AI 对话也不会直接修改这些结论。') }}</p>
        <span v-if="modelRevision">{{ t('courseWorkspace.learningOverview.revision', '模型修订') }} {{ shortRevision }}</span>
      </footer>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  BadgeCheck,
  BookOpenCheck,
  ChartNoAxesCombined,
  CircleAlert,
  ClipboardCheck,
  Download,
  Focus,
  Info,
  LoaderCircle,
  NotebookTabs,
  RefreshCw,
  Route,
  ScanSearch,
  ShieldCheck,
} from 'lucide-vue-next'
import { useCourseStore } from '../stores/course'
import { useLearnerModelStore, type EvidenceConfidence, type LearnerModelItem } from '../stores/learnerModel'
import { useLearningProgressStore } from '../stores/learningProgress'
import { learningActionPresentation } from '../utils/learning-action'
import { t } from '../shared/i18n'

const courseStore = useCourseStore()
const learnerModelStore = useLearnerModelStore()
const learningProgressStore = useLearningProgressStore()

const model = computed(() => learnerModelStore.model)
const runtimeModel = computed(() => learningProgressStore.runtime?.learner_model)
const loading = computed(() => learnerModelStore.loading || learningProgressStore.runtimeLoading)
const error = computed(() => learnerModelStore.error)
const summary = computed(() => model.value?.summary || runtimeModel.value?.summary || {
  total_objectives: 0,
  started_objectives: 0,
  learned_objectives: 0,
  mastered_objectives: 0,
  needs_attention_objectives: 0,
  formal_evidence_count: 0,
  active_record_count: 0,
})
const dataSufficiency = computed(() => model.value?.data_sufficiency || runtimeModel.value?.data_sufficiency || {
  level: 'none' as const,
  formal_evidence_count: 0,
  total_evidence_count: 0,
  covered_objective_count: 0,
  reason_code: 'insufficient_for_stable_inference',
})
const sufficiencyLevel = computed(() => dataSufficiency.value.level || 'none')
const currentObjective = computed(() => {
  const currentNodeId = courseStore.currentNode?.node_id
  return model.value?.objectives.find(item => item.node_id === currentNodeId)
    || runtimeModel.value?.current_objective
    || null
})
const currentObjectiveIsCurrent = computed(() => isCurrentModelItem(currentObjective.value))
const strengths = computed<LearnerModelItem[]>(() => (
  model.value?.strengths || runtimeModel.value?.strengths || []
).filter(isCurrentModelItem))
const needsAttention = computed<LearnerModelItem[]>(() => (
  model.value?.needs_attention || runtimeModel.value?.needs_attention || []
).filter(isCurrentModelItem))
const evidenceCount = computed(() => dataSufficiency.value.total_evidence_count || 0)
const formalAttemptCount = computed(() => model.value?.evidence_catalog.filter(item => item.type === 'practice_attempt' && item.status === 'graded').length || summary.value.formal_evidence_count || 0)
const modelRevision = computed(() => model.value?.model_revision_id || runtimeModel.value?.model_revision_id || '')
const shortRevision = computed(() => modelRevision.value.slice(-10))
const readingPercentage = computed(() => percentage(summary.value.learned_objectives, summary.value.total_objectives))
const masteryPercentage = computed(() => percentage(summary.value.mastered_objectives, summary.value.total_objectives))
const nextAction = computed(() => {
  const action = learningProgressStore.runtime?.continuation?.primary_action
  return action ? learningActionPresentation(action) : null
})
const evidenceLevelLabel = computed(() => t(
  `courseWorkspace.learningOverview.evidenceLevel.${sufficiencyLevel.value}`,
  ({ none: '暂无正式证据', limited: '有限证据', moderate: '中等证据', strong: '强证据' } as Record<string, string>)[sufficiencyLevel.value] || '暂无正式证据',
))

onMounted(refresh)
watch(() => [courseStore.currentCourseId, courseStore.currentNode?.node_id], ([courseId], previous) => {
  if (courseId && courseId !== previous?.[0]) void refresh()
})

async function refresh() {
  const courseId = courseStore.currentCourseId
  if (!courseId) return
  await Promise.allSettled([
    learnerModelStore.load(courseId),
    learningProgressStore.loadRuntime(courseId, courseStore.currentNode?.node_id),
  ])
}

function percentage(value: number, total: number) {
  return total > 0 ? Math.round((value / total) * 100) : 0
}

function isCurrentModelItem(item: LearnerModelItem | { valid_until?: string | null } | null | undefined) {
  if (!item?.valid_until) return true
  const boundary = Date.parse(item.valid_until)
  return Number.isFinite(boundary) && boundary >= Date.now()
}

function readingStatusLabel(status: string) {
  return t(
    `courseWorkspace.progress.reading.${status}`,
    ({ not_started: '尚未开始', in_progress: '学习中', learned: '已学完' } as Record<string, string>)[status] || '状态未知',
  )
}

function masteryStatusLabel(status: string) {
  return t(
    `courseWorkspace.progress.mastery.${status}`,
    ({
      not_checked: '尚未检查', evidence_insufficient: '证据不足', partial: '部分掌握',
      mastered: '已掌握', needs_review: '需要复习',
    } as Record<string, string>)[status] || '状态未知',
  )
}

function confidenceLabel(confidence: EvidenceConfidence | string) {
  return t(
    `courseWorkspace.learningOverview.confidence.${confidence}`,
    ({ insufficient: '证据不足', low: '低置信', medium: '中等置信', high: '高置信' } as Record<string, string>)[confidence] || '证据不足',
  )
}

function supportReasonLabel(reason: string) {
  return t(
    `courseWorkspace.learningOverview.supportReason.${reason}`,
    ({
      active_diagnostic: '当前正在辨别具体卡点',
      formal_evidence_needs_review: '当前正式检测显示需要复习',
      repeated_independent_failure: '多次独立练习尚未通过',
      open_user_issue: '你保留了一条未解决问题',
      single_formal_failure_insufficient: '仅有一次未通过记录，尚不足以判断为稳定薄弱点',
      no_current_support_need: '当前没有需要额外处理的证据',
      insufficient_evidence: '现有证据不足以形成判断',
      formally_mastered: '已经由正式检测验证',
    } as Record<string, string>)[reason] || '现有证据不足以形成判断',
  )
}

function exportModel() {
  if (!model.value) return
  const blob = new Blob([JSON.stringify(model.value, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `learner-model-${model.value.course_id}.json`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
  ElMessage.success(t('courseWorkspace.learningOverview.exported', '正式学习概况已导出'))
}
</script>

<style scoped>
.learning-overview { height:100%; overflow:auto; color:#24324a; background:rgba(255,255,255,.94); }
.overview-header { position:sticky; top:0; z-index:4; display:flex; align-items:center; justify-content:space-between; min-height:68px; padding:12px 24px; border-bottom:1px solid #e8edf5; background:rgba(255,255,255,.96); backdrop-filter:blur(14px); }
.overview-heading { display:flex; align-items:center; gap:11px; min-width:0; }
.overview-heading__icon { display:grid; place-items:center; width:36px; height:36px; border-radius:8px; color:#fff; background:#7058ee; box-shadow:0 6px 16px rgba(112,88,238,.22); }
.overview-heading h1,.section-heading h2,.signal-group h2 { margin:0; letter-spacing:0; }
.overview-heading h1 { font-size:16px; font-weight:750; }
.overview-heading p { margin:2px 0 0; font-size:11px; color:#7c8aa3; }
.overview-actions { display:flex; gap:6px; }
.overview-actions button { display:grid; place-items:center; width:34px; height:34px; padding:0; border:1px solid #e1e7f0; border-radius:8px; color:#65748d; background:#fff; cursor:pointer; }
.overview-actions button:hover:not(:disabled) { color:#6047dc; border-color:#cfc6fb; background:#f8f6ff; }
.overview-actions button:disabled { opacity:.45; cursor:not-allowed; }
.overview-state { min-height:260px; display:flex; align-items:center; justify-content:center; gap:10px; color:#6d7a91; font-size:13px; }
.overview-state--error { align-items:flex-start; margin:24px; min-height:auto; padding:16px; border:1px solid #f0d9dc; border-radius:8px; color:#9b3f49; background:#fff8f8; }
.overview-state--error strong { font-size:13px; }
.overview-state--error p { margin:4px 0 0; color:#7e6670; }
.overview-body { padding:0 24px 28px; }
.overview-section { padding:22px 0; border-bottom:1px solid #edf0f5; }
.overview-section:last-of-type { border-bottom:0; }
.section-heading { display:flex; justify-content:space-between; align-items:flex-start; gap:14px; }
.section-heading span,.next-action span { display:block; margin-bottom:4px; font-size:10px; font-weight:700; color:#8a96aa; text-transform:uppercase; }
.section-heading h2 { font-size:14px; font-weight:750; color:#27344b; }
.evidence-badge,.confidence-badge { display:inline-flex!important; align-items:center; gap:5px; margin:0!important; padding:5px 8px; border-radius:999px; font-size:10px!important; text-transform:none!important; color:#5e6c84!important; background:#f1f4f8; }
.evidence-badge[data-level='strong'] { color:#167452!important; background:#e9f8f1; }
.evidence-badge[data-level='moderate'] { color:#4469a7!important; background:#edf3ff; }
.evidence-badge[data-level='limited'] { color:#9a661a!important; background:#fff6df; }
.metric-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:0; margin-top:20px; border:1px solid #e8ecf3; border-radius:8px; overflow:hidden; }
.metric { min-width:0; padding:14px; border-right:1px solid #e8ecf3; background:#fbfcfe; }
.metric:last-child { border-right:0; }
.metric strong { display:block; font-size:24px; line-height:1; color:#2c3850; }
.metric span { display:block; margin-top:7px; font-size:11px; color:#7a879b; }
.progress-pair { display:grid; grid-template-columns:minmax(100px,auto) 1fr; gap:9px 14px; align-items:center; margin-top:18px; }
.progress-pair>div:nth-child(odd) { display:flex; justify-content:space-between; gap:12px; font-size:11px; color:#718097; }
.progress-pair strong { color:#45536a; }
.progress-track { height:6px; overflow:hidden; border-radius:999px; background:#edf0f5; }
.progress-track span { display:block; height:100%; border-radius:inherit; background:#7b64ef; transition:width .25s ease; }
.progress-track--mastery span { background:#27a574; }
.objective-statement { margin:14px 0 0; color:#58677e; font-size:13px; line-height:1.7; }
.status-row { display:flex; flex-wrap:wrap; gap:8px; margin-top:14px; }
.status-row span { display:inline-flex; align-items:center; gap:6px; padding:6px 9px; border:1px solid #e5e9f1; border-radius:7px; color:#56647a; background:#fbfcfe; font-size:11px; }
.support-callout { display:flex; gap:10px; margin-top:14px; padding:12px; border-left:3px solid #d69a35; color:#855b21; background:#fff9ed; }
.support-callout strong { font-size:12px; }
.support-callout p { margin:3px 0 0; font-size:11px; line-height:1.55; color:#7d6a4a; }
.next-action { display:flex; gap:12px; align-items:flex-start; }
.next-action__icon { display:grid; place-items:center; flex:0 0 34px; height:34px; border-radius:8px; color:#6047dc; background:#f0edff; }
.next-action strong { display:block; font-size:14px; color:#2e3b52; }
.next-action p { margin:5px 0 0; font-size:11px; line-height:1.55; color:#748198; }
.evidence-section .section-heading>strong { font-size:22px; color:#334058; }
.evidence-breakdown { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:10px; margin-top:16px; }
.evidence-breakdown>div { display:grid; grid-template-columns:auto 1fr auto; align-items:center; gap:7px; min-width:0; padding:10px; border:1px solid #e8ecf3; border-radius:8px; color:#65748b; background:#fff; }
.evidence-breakdown span { min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:11px; }
.evidence-breakdown strong { font-size:13px; color:#354258; }
.empty-copy { margin:14px 0 0; font-size:12px; line-height:1.7; color:#7b889b; }
.signal-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:24px; }
.signal-group h2 { display:flex; align-items:center; gap:7px; font-size:13px; color:#257253; }
.signal-group--attention h2 { color:#9a671f; }
.signal-group ul { margin:12px 0 0; padding:0; list-style:none; }
.signal-group li { display:flex; justify-content:space-between; gap:10px; padding:8px 0; border-top:1px solid #edf0f5; font-size:12px; color:#46546a; }
.signal-group small { color:#8793a6; text-align:right; }
.overview-policy { display:grid; grid-template-columns:auto 1fr; gap:8px 10px; margin-top:18px; padding:12px; border-radius:8px; color:#6f7d92; background:#f5f7fa; }
.overview-policy p { margin:0; font-size:11px; line-height:1.6; }
.overview-policy>span { grid-column:2; font-size:9px; color:#98a2b2; }
.spinning { animation:spin 1s linear infinite; }
@keyframes spin { to { transform:rotate(360deg); } }
@media (max-width:640px) {
  .overview-header { padding:10px 16px; }
  .overview-body { padding:0 16px 22px; }
  .metric-grid { grid-template-columns:1fr; }
  .metric { display:flex; align-items:center; justify-content:space-between; border-right:0; border-bottom:1px solid #e8ecf3; }
  .metric:last-child { border-bottom:0; }
  .metric span { margin-top:0; text-align:right; }
  .progress-pair { grid-template-columns:1fr; }
  .progress-pair>div:nth-child(odd) { margin-top:4px; }
  .evidence-breakdown,.signal-grid { grid-template-columns:1fr; }
}
</style>
