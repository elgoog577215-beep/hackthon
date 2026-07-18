<template>
  <section v-if="visiblePlans.length" class="evolution-panel" aria-live="polite">
    <header>
      <span><GitBranchPlus :size="14" /></span>
      <div><small>{{ t('courseEvolution.eyebrow', '证据驱动') }}</small><strong>{{ t('courseEvolution.title', '课程调整建议') }}</strong></div>
      <button type="button" :title="t('courseEvolution.refresh', '重新分析学习证据')" :aria-label="t('courseEvolution.refresh', '重新分析学习证据')" :disabled="store.loading" @click="store.evaluate(courseId)"><RefreshCw :size="14" :class="{ spinning: store.loading }" /></button>
    </header>

    <article v-for="plan in visiblePlans" :key="plan.change_set_id" :data-status="plan.status" :data-effect="planEffectState(plan)">
      <template v-if="plan.status === 'pending'">
        <div class="evolution-evidence" :aria-label="t('courseEvolution.evidenceConvergence', '多类证据汇聚')">
          <template v-for="(evidence, index) in evidenceFor(plan)" :key="evidence.evidence_id">
            <span :data-source="evidence.source_type">
              <component :is="evidenceIcon(evidence.source_type)" :size="12" />{{ evidenceLabel(evidence.source_type) }}
            </span>
            <ArrowRight v-if="index < evidenceFor(plan).length - 1" :size="10" />
          </template>
        </div>
        <div class="evidence-maturity" :data-maturity="evidenceAssessment(plan).maturity || 'observing'">
          <span>
            <Network :size="11" />
            {{ t('courseEvolution.independentSources', '{count} 类独立来源').replace('{count}', String(evidenceAssessment(plan).independent_source_count || 0)) }}
          </span>
          <span v-if="evidenceAssessment(plan).has_formal_evidence">
            <BadgeCheck :size="11" />{{ t('courseEvolution.formalEvidenceIncluded', '含正式证据') }}
          </span>
          <span>
            <ShieldCheck :size="11" />
            {{
              evidenceAssessment(plan).counterevidence_count
                ? t('courseEvolution.counterevidenceIncluded', '已纳入 {count} 条反证').replace('{count}', String(evidenceAssessment(plan).counterevidence_count))
                : t('courseEvolution.noCounterevidence', '暂无反证冲突')
            }}
          </span>
        </div>
        <div class="evolution-diagnosis">
          <span><BrainCircuit :size="14" />{{ t('courseEvolution.diagnosis', 'AI 学习判断') }}</span>
          <strong>{{ diagnosisFor(plan) }}</strong>
        </div>
        <div v-if="impactLabels(plan).length" class="evolution-impact">
          <span v-for="label in impactLabels(plan)" :key="label">{{ label }}</span>
          <small v-if="plan.impact_summary?.dependent_block_ids?.length">
            {{ t('courseEvolution.dependentBlocks', '关联后续 {count} 个教学块').replace('{count}', String(plan.impact_summary.dependent_block_ids.length)) }}
          </small>
        </div>
        <p class="evolution-effect"><Sparkles :size="13" />{{ plan.expected_effect }}</p>
        <button type="button" class="evolution-details-toggle" @click="expandedId = expandedId === plan.change_set_id ? '' : plan.change_set_id">
          <ChevronUp v-if="expandedId === plan.change_set_id" :size="13" /><ChevronDown v-else :size="13" />
          {{ expandedId === plan.change_set_id ? t('courseEvolution.hideDetails', '收起依据与范围') : t('courseEvolution.showDetails', '查看依据与范围') }}
        </button>
        <div v-if="expandedId === plan.change_set_id" class="evolution-details">
          <p v-for="evidence in evidenceFor(plan)" :key="evidence.evidence_id">
            <b>{{ evidenceLabel(evidence.source_type) }}</b>
            <span>{{ evidence.summary }}</span>
            <button type="button" :title="t('courseEvolution.locateEvidence', '回到证据位置')" :aria-label="t('courseEvolution.locateEvidence', '回到证据位置')" @click="locateEvidence(evidence)"><LocateFixed :size="12" /></button>
          </p>
          <ul><li v-for="operation in plan.operations" :key="operation.operation_id"><span>{{ operationLabel(operation.operation_type) }}</span>{{ operation.reason }}</li></ul>
          <p class="validation-plan"><ScanSearch :size="13" /><b>{{ t('courseEvolution.validation', '效果复验') }}</b>{{ validationFor(plan) }}</p>
          <p class="protected"><ShieldCheck :size="13" />{{ t('courseEvolution.protected', '只修改当前课程所选范围；不修改其他课程、历史作答和笔记原文') }}</p>
        </div>
        <div class="scope-control" v-if="plan.allowed_scopes.length > 1">
          <button type="button" :class="{ active: selectedScope[plan.change_set_id] !== 'current_and_next' }" @click="selectedScope[plan.change_set_id] = 'current'">{{ t('courseEvolution.currentOnly', '只应用本小节') }}</button>
          <button type="button" :class="{ active: selectedScope[plan.change_set_id] === 'current_and_next' }" @click="selectedScope[plan.change_set_id] = 'current_and_next'">{{ t('courseEvolution.currentAndNext', '本小节及后续') }}</button>
        </div>
        <div class="evolution-actions">
          <button type="button" class="primary" :disabled="store.actingId === plan.change_set_id" @click="accept(plan)"><LoaderCircle v-if="store.actingId === plan.change_set_id" :size="13" class="spinning" /><Check v-else :size="13" />{{ t('courseEvolution.accept', '确认并更新课程') }}</button>
          <button type="button" :disabled="store.actingId === plan.change_set_id" @click="store.reject(plan.change_set_id)"><X :size="13" />{{ t('courseEvolution.reject', '暂不调整') }}</button>
        </div>
      </template>
      <template v-else>
        <div class="applied-growth">
          <component :is="effectIcon(plan)" :size="15" />
          <span>
            <strong>{{ effectTitle(plan) }}</strong>
            <small>{{ effectLabel(plan) }}</small>
          </span>
          <button v-if="plan.effect_evaluation?.status === 'ineffective'" type="button" :disabled="store.actingId === plan.change_set_id" @click="adjust(plan)"><RefreshCw :size="13" />{{ t('courseEvolution.adjust', '生成调整方案') }}</button>
          <button v-else type="button" @click="undo(plan)"><Undo2 :size="13" />{{ plan.effect_evaluation?.status === 'harmful' ? t('courseEvolution.rollback', '确认回退') : t('courseEvolution.undo', '撤销') }}</button>
        </div>
        <p class="applied-diagnosis">{{ diagnosisFor(plan) }}</p>
        <div v-if="verificationFor(plan)" class="verification-flow">
          <div>
            <small>{{ t('courseEvolution.verification.baseline', '调整前') }}</small>
            <strong>{{ attemptResultLabel(verificationFor(plan).baseline) }}</strong>
          </div>
          <ArrowRight :size="12" />
          <div>
            <small>{{ t('courseEvolution.verification.courseChange', '课程生长') }}</small>
            <strong>{{ t('courseEvolution.verification.blockCount', '{count} 个教学块').replace('{count}', String(verificationFor(plan).course_change?.applied_block_count || 0)) }}</strong>
          </div>
          <ArrowRight :size="12" />
          <div>
            <small>{{ t('courseEvolution.verification.followUp', '独立复验') }}</small>
            <strong>{{ attemptResultLabel(verificationFor(plan).follow_up) }}</strong>
          </div>
        </div>
        <p v-if="verificationFor(plan)?.interpretation" class="verification-interpretation">
          <ScanSearch :size="12" />{{ verificationFor(plan).interpretation }}
        </p>
      </template>
    </article>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ArrowRight, BadgeCheck, BookOpenText, BrainCircuit, Check, CheckCircle2, ChevronDown, ChevronUp, CircleDot, FileQuestion, GitBranchPlus, LoaderCircle, LocateFixed, Network, NotebookTabs, RefreshCw, ScanSearch, Sparkles, TriangleAlert, Undo2, X, ShieldCheck } from 'lucide-vue-next'
import { useCourseEvolutionStore, type CourseEvolutionPlan, type EvolutionEvidence } from '../stores/courseEvolution'
import { useCourseStore } from '../stores/course'
import { useLearningProgressStore } from '../stores/learningProgress'
import { t } from '../shared/i18n'

const props = defineProps<{ courseId: string }>()
const store = useCourseEvolutionStore()
const courseStore = useCourseStore()
const progressStore = useLearningProgressStore()
const expandedId = ref('')
const selectedScope = reactive<Record<string, 'current' | 'current_and_next'>>({})
const visiblePlans = computed(() => [...store.pendingPlans, ...store.appliedPlans.slice(-1)])

function evidenceFor(plan: CourseEvolutionPlan) { return store.evidenceItems.filter(item => plan.evidence_ids.includes(item.evidence_id)) }
function hypothesisFor(plan: CourseEvolutionPlan) { return store.hypotheses.find(item => item.hypothesis_id === plan.hypothesis_id) }
function diagnosisFor(plan: CourseEvolutionPlan) { return String(plan.impact_summary?.diagnosis || hypothesisFor(plan)?.claim || t('courseEvolution.diagnosisFallback', '多条证据共同指向当前理解缺口')) }
function validationFor(plan: CourseEvolutionPlan) { return String(plan.impact_summary?.validation_plan || hypothesisFor(plan)?.validation_plan || t('courseEvolution.validationFallback', '用后续同能力正式题检验调整是否有效')) }
function evidenceLabel(source: EvolutionEvidence['source_type']) { return ({ learning_event: t('courseEvolution.sources.dialogue', '对话与反馈'), learning_record: t('courseEvolution.sources.record', '学习记录'), practice_attempt: t('courseEvolution.sources.practice', '正式练习') })[source] }
function evidenceIcon(source: EvolutionEvidence['source_type']) { return ({ learning_event: FileQuestion, learning_record: NotebookTabs, practice_attempt: BookOpenText })[source] }
function operationLabel(type: string) { return ({ INSERT_COURSE_SUPPORT: t('courseEvolution.operations.explanation', '补充解释'), INSERT_PERSONAL_SUPPORT: t('courseEvolution.operations.explanation', '补充解释'), ADD_TRANSITION_SUPPORT: t('courseEvolution.operations.transition', '后续承接'), ADD_CHECKPOINT: t('courseEvolution.operations.checkpoint', '理解检查'), ADD_TARGETED_PRACTICE: t('courseEvolution.operations.targetedPractice', '针对性练习'), ADD_ANIMATION: t('courseEvolution.operations.animation', '分步演示') } as Record<string, string>)[type] || type }
function impactLabels(plan: CourseEvolutionPlan) { return [...(plan.impact_summary?.knowledge_labels || []), ...(plan.impact_summary?.ability_labels || []), ...(plan.impact_summary?.misconception_labels || [])].slice(0, 4) }
function evidenceAssessment(plan: CourseEvolutionPlan) { return plan.impact_summary?.evidence_assessment || hypothesisFor(plan)?.evidence_assessment || {} }
function planEffectState(plan: CourseEvolutionPlan) { return plan.status === 'pending' ? 'pending' : String(plan.effect_evaluation?.status || 'insufficient_evidence') }
function effectIcon(plan: CourseEvolutionPlan) { return plan.effect_evaluation?.status === 'effective' ? CheckCircle2 : plan.effect_evaluation?.status === 'ineffective' || plan.effect_evaluation?.status === 'harmful' ? TriangleAlert : CircleDot }
function effectTitle(plan: CourseEvolutionPlan) {
  if (plan.effect_evaluation?.status === 'effective') {
    return plan.effect_evaluation?.verification_level === 'confirmed'
      ? t('courseEvolution.confirmed', '持续证据已确认')
      : t('courseEvolution.initiallyValidated', '本轮独立复验通过')
  }
  return plan.effect_evaluation?.status === 'ineffective' || plan.effect_evaluation?.status === 'harmful'
    ? t('courseEvolution.needsReview', '当前课程变化需要复核')
    : t('courseEvolution.applied', '课程新版本已应用')
}
function effectLabel(plan: CourseEvolutionPlan) { return ({ effective: t('courseEvolution.effects.effective', '原判断获得新证据支持，继续观察后续迁移'), ineffective: t('courseEvolution.effects.ineffective', '后续证据显示需要调整'), harmful: t('courseEvolution.effects.harmful', '后续证据显示有副作用，建议回退'), insufficient_evidence: t('courseEvolution.effects.insufficient', '等待后续同能力正式题复验') } as Record<string, string>)[plan.effect_evaluation?.status || ''] || t('courseEvolution.effects.insufficient', '等待后续同能力正式题复验') }
function verificationFor(plan: CourseEvolutionPlan) { return plan.effect_evaluation?.verification_summary || null }
function attemptResultLabel(value: Record<string, any> | undefined) {
  if (!value || value.attempt_count === 0) return t('courseEvolution.verification.noEvidence', '暂无')
  if (typeof value.score === 'number') return `${Math.round(value.score)} ${t('courseEvolution.verification.points', '分')}`
  return value.passed
    ? t('courseEvolution.verification.passed', '已通过')
    : t('courseEvolution.verification.failed', '未通过')
}
function locateEvidence(evidence: EvolutionEvidence) {
  const sectionId = String(evidence.anchor?.section_id || '')
  const node = courseStore.courseTree.find(item => item.node_id === sectionId)
  if (node) courseStore.selectNode(node)
  if (sectionId) courseStore.scrollToNode(sectionId)
  if (evidence.source_type === 'learning_record') courseStore.scrollToNote(evidence.source_id)
}
async function refreshCourseAndRuntime() {
  await courseStore.refreshCourseData(props.courseId)
  await progressStore.loadRuntime(props.courseId)
}
async function accept(plan: CourseEvolutionPlan) { await store.accept(plan.change_set_id, selectedScope[plan.change_set_id] || 'current'); await refreshCourseAndRuntime() }
async function undo(plan: CourseEvolutionPlan) { await store.undo(plan.change_set_id); await refreshCourseAndRuntime() }
async function adjust(plan: CourseEvolutionPlan) { await store.adjust(plan.change_set_id) }
async function load() {
  if (!props.courseId) return
  if (import.meta.env.MODE === 'test') return
  try {
    await store.load(props.courseId)
  } catch {
    // The AI teacher remains usable when the evolution projection is offline.
  }
}
watch(() => props.courseId, load)
onMounted(load)
</script>

<style scoped>
.evolution-panel { min-height:0; max-height:58%; overflow:auto; margin:0 12px 10px; padding:10px 11px; border:1px solid rgba(221,214,254,.9); border-radius:10px; background:linear-gradient(110deg,rgba(245,243,255,.78),rgba(248,250,252,.66)); }
.evolution-panel > header { display:grid; grid-template-columns:24px minmax(0,1fr) 28px; align-items:center; gap:6px; margin-bottom:8px; color:#6d28d9; }
.evolution-panel > header > span { display:grid; place-items:center; }
.evolution-panel header div { display:flex; flex-direction:column; }
.evolution-panel header small { color:#6b7280; font-size:8px; }
.evolution-panel header strong { font-size:11px; }
.evolution-panel header button { width:28px; height:28px; display:grid; place-items:center; border:0; border-radius:6px; color:#6d28d9; background:transparent; cursor:pointer; }
.evolution-panel article { padding:9px 10px; border:1px solid #e5e7eb; border-left:3px solid #8b5cf6; border-radius:8px; background:#fff; }
.evolution-panel article[data-effect="insufficient_evidence"] { border-left-color:#3b82f6; }
.evolution-panel article[data-effect="effective"] { border-color:#bbf7d0; border-left-color:#16a34a; background:#f7fef9; }
.evolution-panel article[data-effect="ineffective"],.evolution-panel article[data-effect="harmful"] { border-color:#fde68a; border-left-color:#d97706; background:#fffbeb; }
.evolution-evidence { display:flex; flex-wrap:wrap; align-items:center; gap:3px; color:#a78bfa; }
.evolution-evidence span { display:inline-flex; align-items:center; gap:4px; padding:3px 6px; border-radius:4px; color:#475569; background:#f1f5f9; font-size:8px; }
.evolution-evidence span[data-source="practice_attempt"] { color:#075985; background:#f0f9ff; }
.evolution-evidence span[data-source="learning_record"] { color:#6d28d9; background:#f5f3ff; }
.evidence-maturity { display:flex; flex-wrap:wrap; gap:4px; margin-top:6px; }
.evidence-maturity span { display:inline-flex; align-items:center; gap:3px; color:#475569; font-size:8px; }
.evidence-maturity[data-maturity="confirmed_gap"] span { color:#047857; }
.evolution-diagnosis { display:grid; gap:4px; margin-top:8px; padding:8px 9px; border:1px solid #ddd6fe; border-radius:7px; background:#faf5ff; }
.evolution-diagnosis span { display:inline-flex; align-items:center; gap:5px; color:#7c3aed; font-size:8px; font-weight:800; }
.evolution-diagnosis strong { color:#2e1065; font-size:11px; line-height:1.55; }
.evolution-impact { display:flex; flex-wrap:wrap; align-items:center; gap:4px; margin-top:7px; }
.evolution-impact span { max-width:100%; overflow:hidden; padding:3px 6px; border:1px solid #dbeafe; border-radius:5px; color:#1d4ed8; background:#eff6ff; font-size:8px; text-overflow:ellipsis; white-space:nowrap; }
.evolution-impact small { color:#64748b; font-size:8px; }
.evolution-effect { display:flex; align-items:flex-start; gap:5px; margin:8px 0 0; color:#475569; font-size:9px; line-height:1.5; }
.evolution-effect svg { flex:0 0 auto; margin-top:1px; color:#8b5cf6; }
.evolution-details-toggle { min-height:28px; display:flex; align-items:center; gap:4px; margin-top:3px; padding:0; border:0; color:#64748b; background:transparent; font-size:9px; cursor:pointer; }
.evolution-details { margin:4px 0 9px; padding:8px 0; border-top:1px solid #ede9fe; border-bottom:1px solid #ede9fe; }
.evolution-details > p { display:grid; grid-template-columns:60px minmax(0,1fr) 24px; align-items:start; gap:6px; margin:4px 0; color:#64748b; font-size:9px; line-height:1.45; }
.evolution-details p b { color:#334155; }
.evolution-details > p > button { width:24px; height:24px; display:grid; place-items:center; border:0; border-radius:5px; color:#64748b; background:#f8fafc; cursor:pointer; }
.evolution-details ul { display:grid; gap:5px; margin:8px 0 0; padding:0; list-style:none; }
.evolution-details li { color:#64748b; font-size:9px; line-height:1.45; }
.evolution-details li span { display:inline-block; min-width:58px; color:#7c3aed; font-weight:700; }
.evolution-details .validation-plan,.evolution-details .protected { display:flex; grid-template-columns:none; align-items:flex-start; gap:5px; margin-top:8px; }
.evolution-details .validation-plan { color:#1d4ed8; }
.evolution-details .validation-plan b { white-space:nowrap; }
.evolution-details .protected { color:#047857; }
.scope-control { display:grid; grid-template-columns:1fr 1fr; gap:4px; margin:7px 0; padding:3px; border-radius:7px; background:#f1f5f9; }
.scope-control button { min-height:28px; border:0; border-radius:5px; color:#64748b; background:transparent; font-size:9px; cursor:pointer; }
.scope-control button.active { color:#6d28d9; background:#fff; box-shadow:0 1px 4px rgba(15,23,42,.08); font-weight:700; }
.evolution-actions { display:flex; gap:5px; margin-top:8px; }
.evolution-actions button,.applied-growth button { min-height:30px; display:inline-flex; align-items:center; justify-content:center; gap:5px; padding:0 8px; border:1px solid #d1d5db; border-radius:6px; color:#64748b; background:#fff; font-size:9px; cursor:pointer; }
.evolution-actions button.primary { color:#fff; border-color:#7c3aed; background:#7c3aed; }
.applied-growth { display:grid; grid-template-columns:20px minmax(0,1fr) auto; align-items:center; gap:7px; color:#2563eb; }
article[data-effect="effective"] .applied-growth { color:#15803d; }
article[data-effect="ineffective"] .applied-growth,article[data-effect="harmful"] .applied-growth { color:#b45309; }
.applied-growth > span { display:flex; flex-direction:column; }
.applied-growth strong { font-size:10px; }
.applied-growth small { margin-top:2px; color:#64748b; font-size:8px; }
.applied-diagnosis { margin:7px 0 0 27px; color:#475569; font-size:9px; line-height:1.45; }
.verification-flow { display:grid; grid-template-columns:minmax(0,1fr) 12px minmax(0,1fr) 12px minmax(0,1fr); align-items:center; gap:4px; margin:9px 0 0 27px; padding:7px; border-radius:7px; background:rgba(255,255,255,.72); }
.verification-flow > div { min-width:0; display:flex; flex-direction:column; gap:2px; }
.verification-flow small { color:#64748b; font-size:7px; }
.verification-flow strong { overflow:hidden; color:#1f2937; font-size:9px; text-overflow:ellipsis; white-space:nowrap; }
.verification-flow > svg { color:#94a3b8; }
.verification-interpretation { display:flex; align-items:flex-start; gap:5px; margin:7px 0 0 27px; color:#475569; font-size:8px; line-height:1.5; }
.verification-interpretation svg { flex:0 0 auto; margin-top:1px; color:#2563eb; }
.spinning { animation:evolution-spin .8s linear infinite; }
@keyframes evolution-spin { to { transform:rotate(360deg); } }
</style>
