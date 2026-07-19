<template>
  <Teleport to="body">
    <div class="review-backdrop" @click.self="emit('close')">
      <section
        class="review-workbench"
        role="dialog"
        aria-modal="true"
        :aria-labelledby="titleId"
        :data-state="dialogState"
      >
        <header class="review-header">
          <div class="review-title-mark" :class="{ scanning: isGenerating }">
            <ScanSearch v-if="isGenerating" :size="21" />
            <Layers3 v-else :size="21" />
          </div>
          <div>
            <small>{{ headerEyebrow }}</small>
            <h2 :id="titleId">{{ headerTitle }}</h2>
          </div>
          <button
            type="button"
            class="icon-button"
            :title="t('courseEvolution.review.close', '关闭审阅')"
            :aria-label="t('courseEvolution.review.close', '关闭审阅')"
            @click="emit('close')"
          >
            <X :size="19" />
          </button>
        </header>

        <div class="scope-contract">
          <div class="scope-sentence">
            <span><Sparkles :size="15" />{{ t('courseEvolution.review.interpretation', 'AI 作用范围解释') }}</span>
            <strong>{{ interpretation }}</strong>
            <p>{{ matchingPolicy }}</p>
          </div>
          <dl>
            <div>
              <dt>{{ t('courseEvolution.review.hardBoundary', '用户硬边界') }}</dt>
              <dd>{{ t('courseEvolution.scope.wholeCourse', '当前全课程') }}</dd>
            </div>
            <div>
              <dt>{{ t('courseEvolution.review.semanticTarget', '语义目标') }}</dt>
              <dd>{{ targetRoleSummary }}</dd>
            </div>
            <div>
              <dt>{{ t('courseEvolution.review.matchedNodes', '匹配节点') }}</dt>
              <dd>{{ matchedCount || '—' }}</dd>
            </div>
            <div>
              <dt>{{ isReady ? t('courseEvolution.review.selectedNodes', '本次纳入') : t('courseEvolution.review.generatedNodes', '已生成候选') }}</dt>
              <dd>{{ isReady ? selectedCount : `${readyCount}/${matchedCount || '—'}` }}</dd>
            </div>
          </dl>
        </div>

        <section class="live-scan-status" :data-state="dialogState" aria-live="polite">
          <div class="scan-status-icon">
            <LoaderCircle v-if="isGenerating" :size="18" class="spinning" />
            <TriangleAlert v-else-if="generationError" :size="18" />
            <CheckCircle2 v-else :size="18" />
          </div>
          <div class="scan-status-copy">
            <strong>{{ scanStatusTitle }}</strong>
            <small>{{ scanStatusDetail }}</small>
          </div>
          <div class="scan-meter" :class="{ indeterminate: isGenerating && !matchedCount }" aria-hidden="true">
            <i :style="{ width: `${progressPercent}%` }" />
          </div>
          <b v-if="matchedCount">{{ processedCount }}/{{ matchedCount }}</b>
        </section>

        <div class="review-body">
          <aside class="review-guardrails">
            <div>
              <Target :size="17" />
              <span>
                <b>{{ t('courseEvolution.review.aiUnderstands', 'AI 负责理解') }}</b>
                <small>{{ t('courseEvolution.review.aiUnderstandsDetail', '从你的话中判断要调整的是例子、推导、概念还是检查。') }}</small>
              </span>
            </div>
            <div>
              <ShieldCheck :size="17" />
              <span>
                <b>{{ t('courseEvolution.review.systemGuards', '系统负责守界') }}</b>
                <small>{{ t('courseEvolution.review.systemGuardsDetail', '只匹配当前课程中的合法节点，未匹配内容保持不变。') }}</small>
              </span>
            </div>
            <div>
              <Check :size="17" />
              <span>
                <b>{{ t('courseEvolution.review.youDecide', '你负责决定') }}</b>
                <small>{{ t('courseEvolution.review.youDecideDetail', '逐项纳入或排除，最后一次性更新课程。') }}</small>
              </span>
            </div>
            <p><BookOpen :size="15" />{{ t('courseEvolution.review.atomicNotice', '提交前正式课程不变；提交时只应用已勾选节点。') }}</p>
          </aside>

          <main class="operation-review">
            <div class="review-toolbar">
              <div>
                <strong>{{ isGenerating ? t('courseEvolution.review.liveNodeList', '实时扫描结果') : t('courseEvolution.review.nodeList', '节点生成预览') }}</strong>
                <small>{{ isGenerating ? t('courseEvolution.review.liveNodeListHint', '每完成一个节点，就会立即出现在这里') : t('courseEvolution.review.nodeListHint', '每一项都对应一个真实课程块') }}</small>
              </div>
              <span v-if="isReady">
                <button type="button" @click="selectAll">{{ t('courseEvolution.review.selectAll', '全选') }}</button>
                <button type="button" @click="clearAll">{{ t('courseEvolution.review.clearAll', '清空') }}</button>
              </span>
              <em v-else class="live-update-badge"><span />{{ t('courseEvolution.review.liveUpdating', '实时更新') }}</em>
            </div>

            <ol class="review-list">
              <li v-if="!operations.length && isGenerating" class="scan-empty-state">
                <div class="scanner-orbit"><ScanSearch :size="25" /></div>
                <strong>{{ t('courseEvolution.review.analyzingRequest', '正在理解要求并定位课程节点') }}</strong>
                <p>{{ t('courseEvolution.review.analyzingRequestHint', '系统正在读取当前课程结构、教学作用与知识契约，首个结果会自动出现。') }}</p>
              </li>
              <li v-else-if="!operations.length && generationError" class="scan-empty-state error">
                <TriangleAlert :size="25" />
                <strong>{{ t('courseEvolution.review.scanFailed', '扫描未完成') }}</strong>
                <p>{{ generationError }}</p>
              </li>
              <li
                v-for="(operation, index) in operations"
                :key="operation.operation_id"
                :data-selected="isSelected(operation.operation_id)"
                :data-status="candidateStatus(operation)"
                :class="{ 'latest-result': index === operations.length - 1 && isGenerating }"
              >
                <label v-if="isReady && candidateStatus(operation) === 'ready'" class="operation-choice">
                  <input
                    type="checkbox"
                    :checked="isSelected(operation.operation_id)"
                    @change="toggle(operation.operation_id)"
                  >
                  <span><Check :size="13" /></span>
                  <b>
                    {{ isSelected(operation.operation_id)
                      ? t('courseEvolution.review.included', '纳入本次修改')
                      : t('courseEvolution.review.excluded', '本次不应用') }}
                  </b>
                </label>
                <span v-else class="operation-live-state" :data-status="candidateStatus(operation)">
                  <LoaderCircle v-if="candidateStatus(operation) === 'generating'" :size="13" class="spinning" />
                  <TriangleAlert v-else-if="candidateStatus(operation) === 'quality_failed'" :size="13" />
                  <Check v-else :size="13" />
                  {{ candidateStatusLabel(operation) }}
                </span>
                <div class="operation-heading">
                  <span>{{ String(index + 1).padStart(2, '0') }}</span>
                  <div>
                    <small>{{ operation.payload?.target_section_title || operation.target_section_id }}</small>
                    <strong>{{ operation.payload?.target_block_title || roleLabel(operation.payload?.desired_role) }}</strong>
                  </div>
                  <em>{{ roleLabel(operation.payload?.desired_role) }}</em>
                </div>
                <p class="operation-reason">{{ operation.reason }}</p>
                <div class="content-diff">
                  <section>
                    <small>{{ t('courseEvolution.sectionGrowth.before', '原内容') }}</small>
                    <p>{{ operation.payload?.before_preview || t('courseEvolution.review.noOriginal', '此处原本没有对应内容') }}</p>
                  </section>
                  <ArrowRight :size="17" />
                  <section :class="{ pending: candidateStatus(operation) === 'generating' }">
                    <small>{{ t('courseEvolution.review.aiCandidate', 'AI 候选') }}</small>
                    <template v-if="operation.payload?.after_preview">
                      <p>{{ operation.payload.after_preview }}</p>
                    </template>
                    <div v-else class="candidate-skeleton">
                      <span /><span /><span />
                      <b>{{ t('courseEvolution.review.generatingNode', '正在生成并检查这个节点…') }}</b>
                    </div>
                  </section>
                </div>
              </li>
              <li v-for="index in queuedCount" :key="`queued-${index}`" class="queued-node" data-status="queued">
                <span>{{ String(operations.length + index).padStart(2, '0') }}</span>
                <div>
                  <b>{{ t('courseEvolution.review.queuedNode', '等待扫描的课程节点') }}</b>
                  <small>{{ t('courseEvolution.review.queuedNodeHint', '前一个候选完成后自动开始') }}</small>
                </div>
                <LoaderCircle :size="15" />
              </li>
            </ol>
          </main>
        </div>

        <footer class="review-footer">
          <p>
            <ShieldCheck :size="15" />
            {{ t('courseEvolution.review.footerGuard', '未勾选节点、其他教学作用、其他课程与历史学习事实都不会改变。') }}
          </p>
          <div>
            <button type="button" class="secondary" @click="emit('close')">
              {{ isGenerating ? t('courseEvolution.review.continueInBackground', '后台继续扫描') : t('courseEvolution.review.continueLater', '稍后继续') }}
            </button>
            <button v-if="isGenerating" type="button" class="scan-running" disabled>
              <LoaderCircle :size="15" class="spinning" />
              {{ t('courseEvolution.review.generatedProgress', '已生成 {ready}/{total}').replace('{ready}', String(readyCount)).replace('{total}', String(matchedCount || '—')) }}
            </button>
            <button
              v-else-if="isReady"
              type="button"
              class="apply-selected"
              :disabled="acting || selectedCount === 0"
              @click="emit('apply')"
            >
              <LoaderCircle v-if="acting" :size="15" class="spinning" />
              <Check v-else :size="15" />
              {{
                t('courseEvolution.review.applySelected', '应用所选 {count} 项')
                  .replace('{count}', String(selectedCount))
              }}
            </button>
          </div>
        </footer>
      </section>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted } from 'vue'
import { ArrowRight, BookOpen, Check, CheckCircle2, Layers3, LoaderCircle, ScanSearch, ShieldCheck, Sparkles, Target, TriangleAlert, X } from 'lucide-vue-next'
import { t } from '../shared/i18n'
import type { CourseEvolutionPlan, EvolutionOperation } from '../stores/courseEvolution'

const props = withDefaults(defineProps<{
  plan: CourseEvolutionPlan | null
  selectedOperationIds: string[]
  acting?: boolean
  generating?: boolean
  instruction?: string
  error?: string
}>(), {
  acting: false,
  generating: false,
  instruction: '',
  error: '',
})
const emit = defineEmits<{
  close: []
  apply: []
  'update:selectedOperationIds': [value: string[]]
}>()

const titleId = computed(() => `course-evolution-review-${props.plan?.change_set_id || 'live-scan'}`)
const operations = computed(() => (props.plan?.operations || []).filter(
  operation => operation.operation_type !== 'ADJUST_COURSE_DIFFICULTY',
))
const generationError = computed(() => String(
  props.error
  || props.plan?.impact_summary?.generation_error
  || '',
))
const isGenerating = computed(() => Boolean(
  props.generating || props.plan?.generation_status === 'generating',
))
const isReady = computed(() => props.plan?.generation_status === 'ready' && !isGenerating.value)
const dialogState = computed(() => generationError.value ? 'failed' : isGenerating.value ? 'generating' : 'ready')
const matchedCount = computed(() => Math.max(
  Number(props.plan?.impact_summary?.matched_block_count || 0),
  operations.value.length,
))
const readyCount = computed(() => operations.value.filter(operation => candidateStatus(operation) === 'ready').length)
const failedCount = computed(() => operations.value.filter(operation => candidateStatus(operation) === 'quality_failed').length)
const processedCount = computed(() => Math.min(matchedCount.value, readyCount.value + failedCount.value))
const queuedCount = computed(() => isGenerating.value ? Math.max(0, matchedCount.value - operations.value.length) : 0)
const progressPercent = computed(() => {
  if (isReady.value) return 100
  if (!matchedCount.value) return 18
  return Math.max(6, Math.min(96, Math.round((processedCount.value / matchedCount.value) * 100)))
})
const selectedCount = computed(() => props.selectedOperationIds.filter(
  id => operations.value.some(operation => operation.operation_id === id),
).length)
const targetRoleLabels = computed(() => {
  const labels = props.plan?.impact_summary?.target_role_labels || []
  return labels.length ? labels : (props.plan?.requested_roles || []).map(roleLabel)
})
const targetRoleSummary = computed(() => targetRoleLabels.value.join('、') || t('courseEvolution.review.resolvingTarget', '正在解析'))
const interpretation = computed(() => String(
  props.plan?.impact_summary?.diagnosis
  || props.instruction
  || t('courseEvolution.review.interpretationFallback', 'AI 已按你的要求定位当前课程中的相关节点。'),
))
const matchingPolicy = computed(() => String(
  props.plan?.impact_summary?.matching_policy
  || t('courseEvolution.review.scanningPolicy', '只扫描当前课程内与语义目标匹配的合法节点，确认前不会修改课程。'),
))
const headerEyebrow = computed(() => isGenerating.value
  ? t('courseEvolution.review.liveEyebrow', '全课程实时扫描')
  : t('courseEvolution.review.eyebrow', '全课程影响审阅'))
const headerTitle = computed(() => isGenerating.value
  ? t('courseEvolution.review.liveTitle', '正在逐项生成课程节点候选')
  : generationError.value
    ? t('courseEvolution.review.failedTitle', '扫描结果需要处理')
    : t('courseEvolution.review.title', '确认 AI 找到的每一个修改节点'))
const scanStatusTitle = computed(() => {
  if (generationError.value) return t('courseEvolution.review.scanFailed', '扫描未完成')
  if (!props.plan) return t('courseEvolution.review.analyzingRequest', '正在理解要求并定位课程节点')
  if (isGenerating.value) {
    return t('courseEvolution.review.scanningNodes', '已匹配 {count} 个节点，正在生成最新候选')
      .replace('{count}', String(matchedCount.value))
  }
  return t('courseEvolution.review.scanComplete', '扫描完成，可以逐项审阅')
})
const scanStatusDetail = computed(() => {
  if (generationError.value) return generationError.value
  if (!props.plan) return t('courseEvolution.review.analyzingRequestHint', '系统正在读取当前课程结构、教学作用与知识契约，首个结果会自动出现。')
  if (isGenerating.value) {
    return t('courseEvolution.review.scanProgressDetail', '{ready} 个候选已通过检查，结果会继续自动追加。')
      .replace('{ready}', String(readyCount.value))
  }
  return t('courseEvolution.review.scanCompleteDetail', '所有候选均已完成结构化同源检查；正式课程仍未发生变化。')
})

function candidateStatus(operation: EvolutionOperation) {
  return String(operation.payload?.candidate_status || (operation.payload?.after_preview ? 'ready' : 'generating'))
}
function candidateStatusLabel(operation: EvolutionOperation) {
  const status = candidateStatus(operation)
  if (status === 'ready') return t('courseEvolution.review.nodeReady', '候选已通过')
  if (status === 'quality_failed') return t('courseEvolution.review.nodeFailed', '检查未通过')
  return t('courseEvolution.review.nodeGenerating', '正在生成')
}
function roleLabel(role = '') {
  return ({
    reasoning: t('courseEvolution.sectionGrowth.roles.reasoning', '理论推导'),
    application: t('courseEvolution.sectionGrowth.roles.application', '实战应用'),
    example: t('courseEvolution.sectionGrowth.roles.example', '例子讲解'),
    checkpoint: t('courseEvolution.sectionGrowth.roles.checkpoint', '理解检查'),
    concept: t('courseEvolution.sectionGrowth.roles.concept', '核心概念'),
  } as Record<string, string>)[role] || role
}
function isSelected(operationId: string) {
  return props.selectedOperationIds.includes(operationId)
}
function toggle(operationId: string) {
  const next = new Set(props.selectedOperationIds)
  if (next.has(operationId)) next.delete(operationId)
  else next.add(operationId)
  emit(
    'update:selectedOperationIds',
    operations.value
      .map(operation => operation.operation_id)
      .filter(id => next.has(id)),
  )
}
function selectAll() {
  emit('update:selectedOperationIds', operations.value
    .filter(operation => candidateStatus(operation) === 'ready')
    .map(operation => operation.operation_id))
}
function clearAll() {
  emit('update:selectedOperationIds', [])
}
function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') emit('close')
}

let previousBodyOverflow = ''
onMounted(() => {
  previousBodyOverflow = document.body.style.overflow
  document.body.style.overflow = 'hidden'
  window.addEventListener('keydown', onKeydown)
})
onUnmounted(() => {
  document.body.style.overflow = previousBodyOverflow
  window.removeEventListener('keydown', onKeydown)
})
</script>

<style scoped>
.review-backdrop { position:fixed; inset:0; z-index:1500; display:grid; place-items:center; padding:24px; background:rgba(15,23,42,.62); backdrop-filter:blur(10px); }
.review-workbench { width:min(1280px,100%); height:min(880px,calc(100vh - 48px)); display:grid; grid-template-rows:auto auto auto minmax(0,1fr) auto; overflow:hidden; border:1px solid rgba(255,255,255,.72); border-radius:20px; color:#172033; background:#f8fafc; box-shadow:0 34px 90px rgba(15,23,42,.34); }
.review-header { display:grid; grid-template-columns:44px minmax(0,1fr) 40px; align-items:center; gap:13px; padding:18px 22px 16px; border-bottom:1px solid #e2e8f0; background:#fff; }
.review-title-mark { width:44px; height:44px; display:grid; place-items:center; border-radius:12px; color:#fff; background:#4f46e5; }
.review-title-mark.scanning { background:linear-gradient(135deg,#7c3aed,#4f46e5); box-shadow:0 0 0 5px rgba(124,58,237,.09); }
.review-header div:nth-child(2) { min-width:0; }
.review-header small { display:block; color:#64748b; font-size:11px; font-weight:800; letter-spacing:.08em; text-transform:uppercase; }
.review-header h2 { margin:3px 0 0; font-size:21px; line-height:1.3; }
.icon-button { width:40px; height:40px; display:grid; place-items:center; border:1px solid #e2e8f0; border-radius:11px; color:#475569; background:#fff; cursor:pointer; }
.scope-contract { display:grid; grid-template-columns:minmax(0,1.15fr) minmax(440px,.85fr); gap:20px; padding:15px 22px; color:#eef2ff; background:#1e293b; }
.scope-sentence { min-width:0; }
.scope-sentence > span { display:flex; align-items:center; gap:6px; color:#c7d2fe; font-size:11px; font-weight:800; }
.scope-sentence strong { display:block; margin-top:5px; font-size:14px; line-height:1.5; }
.scope-sentence p { margin:4px 0 0; color:#94a3b8; font-size:11px; line-height:1.45; }
.scope-contract dl { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:8px; margin:0; }
.scope-contract dl div { min-width:0; padding:9px 10px; border:1px solid rgba(148,163,184,.22); border-radius:10px; background:rgba(255,255,255,.06); }
.scope-contract dt { overflow:hidden; color:#94a3b8; font-size:10px; text-overflow:ellipsis; white-space:nowrap; }
.scope-contract dd { overflow:hidden; margin:4px 0 0; color:#fff; font-size:13px; font-weight:800; text-overflow:ellipsis; white-space:nowrap; }
.live-scan-status { display:grid; grid-template-columns:34px minmax(0,1fr) minmax(180px,280px) auto; align-items:center; gap:11px; padding:11px 22px; border-bottom:1px solid #ddd6fe; color:#4338ca; background:#f5f3ff; }
.live-scan-status[data-state="ready"] { color:#047857; border-color:#bbf7d0; background:#f0fdf4; }
.live-scan-status[data-state="failed"] { color:#b45309; border-color:#fed7aa; background:#fff7ed; }
.scan-status-icon { width:32px; height:32px; display:grid; place-items:center; border-radius:9px; background:rgba(255,255,255,.78); }
.scan-status-copy { min-width:0; display:flex; flex-direction:column; gap:2px; }
.scan-status-copy strong { font-size:12px; }
.scan-status-copy small { overflow:hidden; color:#64748b; font-size:10px; text-overflow:ellipsis; white-space:nowrap; }
.scan-meter { height:7px; overflow:hidden; border-radius:999px; background:rgba(99,102,241,.14); }
.scan-meter i { display:block; height:100%; border-radius:inherit; background:linear-gradient(90deg,#8b5cf6,#4f46e5); transition:width .35s ease; }
.live-scan-status[data-state="ready"] .scan-meter i { background:#10b981; }
.scan-meter.indeterminate i { width:36% !important; animation:scan-progress 1.2s ease-in-out infinite; }
.live-scan-status > b { min-width:42px; font-size:11px; text-align:right; }
.review-body { min-height:0; display:grid; grid-template-columns:238px minmax(0,1fr); }
.review-guardrails { display:flex; flex-direction:column; gap:18px; padding:22px 19px; border-right:1px solid #e2e8f0; background:#fff; }
.review-guardrails > div { display:grid; grid-template-columns:24px minmax(0,1fr); gap:9px; color:#4f46e5; }
.review-guardrails span { display:flex; flex-direction:column; gap:4px; }
.review-guardrails b { color:#1e293b; font-size:12px; }
.review-guardrails small { color:#64748b; font-size:11px; line-height:1.55; }
.review-guardrails > p { display:flex; gap:8px; margin:auto 0 0; padding:12px; border-radius:10px; color:#0f766e; background:#f0fdfa; font-size:11px; line-height:1.55; }
.review-guardrails > p svg { flex:0 0 auto; margin-top:1px; }
.operation-review { min-height:0; display:grid; grid-template-rows:auto minmax(0,1fr); padding:17px 18px 0; }
.review-toolbar { display:flex; align-items:center; justify-content:space-between; gap:12px; padding:0 2px 13px; }
.review-toolbar > div { display:flex; flex-direction:column; gap:2px; }
.review-toolbar strong { font-size:14px; }
.review-toolbar small { color:#64748b; font-size:11px; }
.review-toolbar > span { display:flex; gap:7px; }
.review-toolbar button { min-height:30px; padding:0 11px; border:1px solid #cbd5e1; border-radius:8px; color:#475569; background:#fff; font-size:11px; cursor:pointer; }
.live-update-badge { display:inline-flex; align-items:center; gap:6px; padding:5px 9px; border-radius:999px; color:#6d28d9; background:#ede9fe; font-size:10px; font-style:normal; font-weight:800; }
.live-update-badge span { width:7px; height:7px; border-radius:50%; background:#8b5cf6; box-shadow:0 0 0 0 rgba(139,92,246,.4); animation:scan-pulse 1.4s infinite; }
.review-list { min-height:0; overflow:auto; display:grid; align-content:start; gap:12px; margin:0; padding:0 5px 20px 2px; list-style:none; }
.review-list > li { position:relative; padding:15px 16px; border:1px solid #cbd5e1; border-radius:13px; background:#fff; transition:border-color .18s,box-shadow .18s,opacity .18s,transform .18s; }
.review-list > li[data-selected="true"] { border-color:#818cf8; box-shadow:0 0 0 2px rgba(99,102,241,.1); }
.review-list > li[data-selected="false"] { opacity:.64; }
.review-list > li.latest-result { border-color:#8b5cf6; box-shadow:0 10px 28px rgba(91,33,182,.11); animation:result-arrive .38s ease-out; }
.review-list > li[data-status="generating"] { border-style:dashed; }
.review-list > li[data-status="quality_failed"] { border-color:#fdba74; background:#fffaf5; }
.operation-choice { position:absolute; top:14px; right:14px; display:flex; align-items:center; gap:7px; cursor:pointer; }
.operation-choice input { position:absolute; opacity:0; pointer-events:none; }
.operation-choice > span { width:22px; height:22px; display:grid; place-items:center; border:1px solid #cbd5e1; border-radius:6px; color:transparent; background:#fff; }
[data-selected="true"] .operation-choice > span { color:#fff; border-color:#4f46e5; background:#4f46e5; }
.operation-choice b { color:#475569; font-size:11px; }
.operation-live-state { position:absolute; top:14px; right:14px; display:inline-flex; align-items:center; gap:5px; padding:5px 8px; border-radius:999px; color:#6d28d9; background:#f5f3ff; font-size:10px; font-weight:800; }
.operation-live-state[data-status="ready"] { color:#047857; background:#ecfdf5; }
.operation-live-state[data-status="quality_failed"] { color:#b45309; background:#ffedd5; }
.operation-heading { display:grid; grid-template-columns:32px minmax(0,1fr) auto; align-items:center; gap:10px; padding-right:165px; }
.operation-heading > span { color:#94a3b8; font:800 12px/1 ui-monospace,SFMono-Regular,Menlo,monospace; }
.operation-heading > div { min-width:0; display:flex; flex-direction:column; gap:2px; }
.operation-heading small { overflow:hidden; color:#64748b; font-size:10px; text-overflow:ellipsis; white-space:nowrap; }
.operation-heading strong { font-size:14px; }
.operation-heading em { padding:4px 8px; border-radius:999px; color:#4338ca; background:#eef2ff; font-size:10px; font-style:normal; font-weight:800; }
.operation-reason { margin:9px 0 10px 42px; color:#64748b; font-size:11px; line-height:1.5; }
.content-diff { display:grid; grid-template-columns:minmax(0,1fr) 22px minmax(0,1fr); align-items:stretch; gap:9px; margin-left:42px; }
.content-diff > svg { align-self:center; color:#94a3b8; }
.content-diff section { min-width:0; padding:11px 12px; border-radius:9px; background:#f8fafc; }
.content-diff section:last-child { background:#eef2ff; }
.content-diff section.pending { background:#f5f3ff; }
.content-diff small { color:#64748b; font-size:10px; font-weight:800; }
.content-diff p { max-height:168px; overflow:auto; margin:5px 0 0; color:#334155; font-size:12px; line-height:1.6; white-space:pre-wrap; }
.candidate-skeleton { display:grid; gap:7px; margin-top:8px; }
.candidate-skeleton span { height:8px; border-radius:999px; background:linear-gradient(90deg,#ddd6fe,#f5f3ff,#ddd6fe); background-size:220% 100%; animation:skeleton-shift 1.2s linear infinite; }
.candidate-skeleton span:nth-child(2) { width:86%; }
.candidate-skeleton span:nth-child(3) { width:64%; }
.candidate-skeleton b { color:#7c3aed; font-size:10px; }
.scan-empty-state { min-height:260px; display:grid; place-content:center; justify-items:center; gap:9px; border-style:dashed !important; color:#6d28d9; text-align:center; }
.scan-empty-state strong { color:#312e81; font-size:15px; }
.scan-empty-state p { max-width:440px; margin:0; color:#64748b; font-size:12px; line-height:1.6; }
.scan-empty-state.error { color:#b45309; }
.scanner-orbit { width:62px; height:62px; display:grid; place-items:center; border:1px solid #c4b5fd; border-radius:50%; background:#f5f3ff; animation:scan-breathe 1.6s ease-in-out infinite; }
.queued-node { min-height:60px; display:grid !important; grid-template-columns:32px minmax(0,1fr) 20px; align-items:center; gap:10px; color:#94a3b8; border-style:dashed !important; background:rgba(248,250,252,.72) !important; }
.queued-node > span { font:800 12px/1 ui-monospace,SFMono-Regular,Menlo,monospace; }
.queued-node > div { display:flex; flex-direction:column; gap:2px; }
.queued-node b { color:#64748b; font-size:12px; }
.queued-node small { font-size:10px; }
.review-footer { display:flex; align-items:center; justify-content:space-between; gap:16px; padding:14px 22px; border-top:1px solid #e2e8f0; background:#fff; }
.review-footer > p { display:flex; align-items:center; gap:7px; margin:0; color:#64748b; font-size:11px; }
.review-footer > p svg { color:#0f766e; }
.review-footer > div { display:flex; gap:8px; }
.review-footer button { min-height:38px; display:inline-flex; align-items:center; justify-content:center; gap:6px; padding:0 16px; border-radius:10px; font-size:11px; font-weight:800; cursor:pointer; }
.review-footer .secondary { border:1px solid #cbd5e1; color:#475569; background:#fff; }
.review-footer .apply-selected { border:1px solid #4f46e5; color:#fff; background:#4f46e5; }
.review-footer .scan-running { border:1px solid #7c3aed; color:#fff; background:#7c3aed; }
.review-footer .apply-selected:disabled,.review-footer .scan-running:disabled { opacity:.58; cursor:not-allowed; }
.spinning { animation:review-spin .8s linear infinite; }
@keyframes review-spin { to { transform:rotate(360deg); } }
@keyframes scan-progress { 0% { transform:translateX(-110%); } 100% { transform:translateX(310%); } }
@keyframes scan-pulse { 70% { box-shadow:0 0 0 7px rgba(139,92,246,0); } 100% { box-shadow:0 0 0 0 rgba(139,92,246,0); } }
@keyframes result-arrive { from { opacity:.35; transform:translateY(7px); } to { opacity:1; transform:translateY(0); } }
@keyframes skeleton-shift { to { background-position:-220% 0; } }
@keyframes scan-breathe { 50% { transform:scale(1.06); box-shadow:0 0 0 10px rgba(139,92,246,.06); } }
@media (max-width:900px) {
  .scope-contract { grid-template-columns:1fr; gap:11px; }
  .review-body { grid-template-columns:190px minmax(0,1fr); }
  .live-scan-status { grid-template-columns:34px minmax(0,1fr) auto; }
  .scan-meter { display:none; }
}
@media (max-width:760px) {
  .review-backdrop { padding:0; }
  .review-workbench { width:100%; height:100dvh; border:0; border-radius:0; }
  .scope-contract { padding:12px 14px; }
  .scope-contract dl { grid-template-columns:repeat(2,minmax(0,1fr)); }
  .review-header { padding:13px 14px; }
  .review-header h2 { font-size:17px; }
  .live-scan-status { padding:9px 14px; }
  .scan-status-copy small { white-space:normal; }
  .review-body { grid-template-columns:1fr; }
  .review-guardrails { display:none; }
  .operation-review { padding:13px 10px 0; }
  .operation-heading { padding-right:0; grid-template-columns:27px minmax(0,1fr); }
  .operation-heading em { display:none; }
  .operation-choice,.operation-live-state { position:static; width:max-content; margin-bottom:10px; }
  .operation-reason,.content-diff { margin-left:0; }
  .content-diff { grid-template-columns:1fr; }
  .content-diff > svg { justify-self:center; transform:rotate(90deg); }
  .review-footer { align-items:stretch; flex-direction:column; padding:10px 12px calc(10px + env(safe-area-inset-bottom)); }
  .review-footer > p { display:none; }
  .review-footer > div { display:grid; grid-template-columns:.8fr 1.2fr; }
}
</style>
