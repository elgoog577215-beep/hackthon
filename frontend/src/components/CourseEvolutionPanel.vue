<template>
  <section v-if="visibleChangeSets.length" class="evolution-panel" aria-live="polite">
    <header>
      <span><GitBranchPlus :size="14" /></span>
      <div><small>{{ t('courseEvolution.eyebrow', '证据驱动') }}</small><strong>{{ t('courseEvolution.title', '个人课程生长建议') }}</strong></div>
      <button type="button" :title="t('courseEvolution.refresh', '重新分析学习证据')" :aria-label="t('courseEvolution.refresh', '重新分析学习证据')" :disabled="store.loading" @click="store.evaluate(courseId)"><RefreshCw :size="14" :class="{ spinning: store.loading }" /></button>
    </header>

    <article v-for="changeSet in visibleChangeSets" :key="changeSet.change_set_id" :data-status="changeSet.status">
      <template v-if="changeSet.status === 'pending'">
        <p class="evolution-effect">{{ changeSet.expected_effect }}</p>
        <div class="evolution-evidence">
          <span v-for="evidence in evidenceFor(changeSet)" :key="evidence.evidence_id" :data-source="evidence.source_type">
            <component :is="evidenceIcon(evidence.source_type)" :size="12" />{{ evidenceLabel(evidence.source_type) }}
          </span>
        </div>
        <button type="button" class="evolution-details-toggle" @click="expandedId = expandedId === changeSet.change_set_id ? '' : changeSet.change_set_id">
          <ChevronUp v-if="expandedId === changeSet.change_set_id" :size="13" /><ChevronDown v-else :size="13" />
          {{ expandedId === changeSet.change_set_id ? t('courseEvolution.hideDetails', '收起依据与范围') : t('courseEvolution.showDetails', '查看依据与范围') }}
        </button>
        <div v-if="expandedId === changeSet.change_set_id" class="evolution-details">
          <p v-for="evidence in evidenceFor(changeSet)" :key="evidence.evidence_id"><b>{{ evidenceLabel(evidence.source_type) }}</b>{{ evidence.summary }}</p>
          <ul><li v-for="operation in changeSet.operations" :key="operation.operation_id"><span>{{ operationLabel(operation.operation_type) }}</span>{{ operation.reason }}</li></ul>
          <p class="protected"><ShieldCheck :size="13" />{{ t('courseEvolution.protected', '不会修改基础课程、其他学习者、历史作答和笔记原文') }}</p>
        </div>
        <div class="scope-control" v-if="changeSet.allowed_scopes.length > 1">
          <button type="button" :class="{ active: selectedScope[changeSet.change_set_id] !== 'current_and_next' }" @click="selectedScope[changeSet.change_set_id] = 'current'">{{ t('courseEvolution.currentOnly', '只应用本小节') }}</button>
          <button type="button" :class="{ active: selectedScope[changeSet.change_set_id] === 'current_and_next' }" @click="selectedScope[changeSet.change_set_id] = 'current_and_next'">{{ t('courseEvolution.currentAndNext', '本小节及后续') }}</button>
        </div>
        <div class="evolution-actions">
          <button type="button" class="primary" :disabled="store.actingId === changeSet.change_set_id" @click="accept(changeSet)"><LoaderCircle v-if="store.actingId === changeSet.change_set_id" :size="13" class="spinning" /><Check v-else :size="13" />{{ t('courseEvolution.accept', '应用到个人课程') }}</button>
          <button type="button" :disabled="store.actingId === changeSet.change_set_id" @click="store.reject(changeSet.change_set_id)"><X :size="13" />{{ t('courseEvolution.reject', '暂不调整') }}</button>
        </div>
      </template>
      <template v-else>
        <div class="applied-growth"><CheckCircle2 :size="15" /><span><strong>{{ t('courseEvolution.applied', '个人课程已应用调整') }}</strong><small>{{ effectLabel(changeSet.effect_evaluation?.status) }}</small></span><button type="button" @click="undo(changeSet)"><Undo2 :size="13" />{{ t('courseEvolution.undo', '撤销') }}</button></div>
      </template>
    </article>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { BookOpenText, Check, CheckCircle2, ChevronDown, ChevronUp, FileQuestion, GitBranchPlus, LoaderCircle, NotebookTabs, RefreshCw, ShieldCheck, Undo2, X } from 'lucide-vue-next'
import { useCourseEvolutionStore, type EvolutionChangeSet, type EvolutionEvidence } from '../stores/courseEvolution'
import { useLearningProgressStore } from '../stores/learningProgress'
import { t } from '../shared/i18n'

const props = defineProps<{ courseId: string }>()
const store = useCourseEvolutionStore()
const progressStore = useLearningProgressStore()
const expandedId = ref('')
const selectedScope = reactive<Record<string, 'current' | 'current_and_next'>>({})
const visibleChangeSets = computed(() => [...store.pendingChangeSets, ...store.appliedChangeSets.slice(-1)])

function evidenceFor(changeSet: EvolutionChangeSet) { return store.evidenceItems.filter(item => changeSet.evidence_ids.includes(item.evidence_id)) }
function evidenceLabel(source: EvolutionEvidence['source_type']) { return ({ learning_event: t('courseEvolution.sources.dialogue', '对话与反馈'), learning_record: t('courseEvolution.sources.record', '学习记录'), practice_attempt: t('courseEvolution.sources.practice', '正式练习') })[source] }
function evidenceIcon(source: EvolutionEvidence['source_type']) { return ({ learning_event: FileQuestion, learning_record: NotebookTabs, practice_attempt: BookOpenText })[source] }
function operationLabel(type: string) { return ({ INSERT_PERSONAL_SUPPORT: t('courseEvolution.operations.explanation', '补充解释'), ADD_TRANSITION_SUPPORT: t('courseEvolution.operations.transition', '后续承接'), ADD_CHECKPOINT: t('courseEvolution.operations.checkpoint', '理解检查'), ADD_ANIMATION: t('courseEvolution.operations.animation', '分步演示') } as Record<string, string>)[type] || type }
function effectLabel(status?: string) { return ({ effective: t('courseEvolution.effects.effective', '后续证据显示有效'), ineffective: t('courseEvolution.effects.ineffective', '后续证据显示需要调整'), insufficient_evidence: t('courseEvolution.effects.insufficient', '等待后续正式证据') } as Record<string, string>)[status || ''] || t('courseEvolution.effects.insufficient', '等待后续正式证据') }
async function accept(changeSet: EvolutionChangeSet) { await store.accept(changeSet.change_set_id, selectedScope[changeSet.change_set_id] || 'current'); await progressStore.loadRuntime(props.courseId) }
async function undo(changeSet: EvolutionChangeSet) { await store.undo(changeSet.change_set_id); await progressStore.loadRuntime(props.courseId) }
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
.evolution-panel { min-height:0; max-height:52%; overflow:auto; margin:0 12px 10px; padding:10px 11px; border:1px solid rgba(167,243,208,.8); border-radius:10px; background:linear-gradient(110deg,rgba(236,253,245,.72),rgba(248,250,252,.62)); }.evolution-panel > header { display:grid; grid-template-columns:24px minmax(0,1fr) 28px; align-items:center; gap:6px; margin-bottom:8px; color:#047857; }.evolution-panel > header > span { display:grid; place-items:center; }.evolution-panel header div { display:flex; flex-direction:column; }.evolution-panel header small { color:#6b7280; font-size:8px; }.evolution-panel header strong { font-size:11px; }.evolution-panel header button { width:28px; height:28px; display:grid; place-items:center; border:0; border-radius:6px; color:#047857; background:transparent; cursor:pointer; }
.evolution-panel article { padding:9px 10px; border:1px solid #dbe7df; border-radius:8px; background:#fff; }.evolution-effect { margin:0 0 8px; color:#1f2937; font-size:11px; font-weight:700; line-height:1.55; }.evolution-evidence { display:flex; flex-wrap:wrap; gap:4px; }.evolution-evidence span { display:inline-flex; align-items:center; gap:4px; padding:3px 6px; border-radius:4px; color:#475569; background:#f1f5f9; font-size:8px; }.evolution-evidence span[data-source="practice_attempt"] { color:#075985; background:#f0f9ff; }.evolution-evidence span[data-source="learning_record"] { color:#6d28d9; background:#f5f3ff; }
.evolution-details-toggle { min-height:28px; display:flex; align-items:center; gap:4px; margin-top:6px; padding:0; border:0; color:#64748b; background:transparent; font-size:9px; cursor:pointer; }.evolution-details { margin:6px 0 9px; padding:8px 0; border-top:1px solid #edf2ef; border-bottom:1px solid #edf2ef; }.evolution-details > p { display:grid; grid-template-columns:60px minmax(0,1fr); gap:6px; margin:4px 0; color:#64748b; font-size:9px; line-height:1.45; }.evolution-details p b { color:#334155; }.evolution-details ul { display:grid; gap:5px; margin:8px 0 0; padding:0; list-style:none; }.evolution-details li { color:#64748b; font-size:9px; line-height:1.45; }.evolution-details li span { display:inline-block; min-width:58px; color:#047857; font-weight:700; }.evolution-details .protected { display:flex; grid-template-columns:none; align-items:center; gap:5px; margin-top:8px; color:#047857; }
.scope-control { display:grid; grid-template-columns:1fr 1fr; gap:4px; margin:7px 0; padding:3px; border-radius:7px; background:#f1f5f9; }.scope-control button { min-height:28px; border:0; border-radius:5px; color:#64748b; background:transparent; font-size:9px; cursor:pointer; }.scope-control button.active { color:#065f46; background:#fff; box-shadow:0 1px 4px rgba(15,23,42,.08); font-weight:700; }.evolution-actions { display:flex; gap:5px; margin-top:8px; }.evolution-actions button,.applied-growth button { min-height:30px; display:inline-flex; align-items:center; justify-content:center; gap:5px; padding:0 8px; border:1px solid #d1d5db; border-radius:6px; color:#64748b; background:#fff; font-size:9px; cursor:pointer; }.evolution-actions button.primary { color:#fff; border-color:#059669; background:#059669; }.applied-growth { display:grid; grid-template-columns:20px minmax(0,1fr) auto; align-items:center; gap:7px; color:#047857; }.applied-growth > span { display:flex; flex-direction:column; }.applied-growth strong { font-size:10px; }.applied-growth small { margin-top:2px; color:#64748b; font-size:8px; }.spinning { animation:evolution-spin .8s linear infinite; }@keyframes evolution-spin { to { transform:rotate(360deg); } }
</style>
