<template>
  <Teleport to="body">
    <div class="review-backdrop" @click.self="emit('close')">
      <section
        class="review-workbench"
        role="dialog"
        aria-modal="true"
        :aria-labelledby="titleId"
      >
        <header class="review-header">
          <div class="review-title-mark"><Layers3 :size="20" /></div>
          <div>
            <small>{{ t('courseEvolution.review.eyebrow', '全课程影响审阅') }}</small>
            <h2 :id="titleId">{{ t('courseEvolution.review.title', '确认 AI 找到的每一个修改节点') }}</h2>
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
            <p>{{ plan.impact_summary?.matching_policy }}</p>
          </div>
          <dl>
            <div>
              <dt>{{ t('courseEvolution.review.hardBoundary', '用户硬边界') }}</dt>
              <dd>{{ t('courseEvolution.scope.wholeCourse', '当前全课程') }}</dd>
            </div>
            <div>
              <dt>{{ t('courseEvolution.review.semanticTarget', '语义目标') }}</dt>
              <dd>{{ targetRoleLabels.join('、') }}</dd>
            </div>
            <div>
              <dt>{{ t('courseEvolution.review.matchedNodes', '匹配节点') }}</dt>
              <dd>{{ operations.length }}</dd>
            </div>
            <div>
              <dt>{{ t('courseEvolution.review.selectedNodes', '本次纳入') }}</dt>
              <dd>{{ selectedCount }}</dd>
            </div>
          </dl>
        </div>

        <div class="review-body">
          <aside class="review-guardrails">
            <div>
              <Target :size="16" />
              <span>
                <b>{{ t('courseEvolution.review.aiUnderstands', 'AI 负责理解') }}</b>
                <small>{{ t('courseEvolution.review.aiUnderstandsDetail', '从你的话中判断要调整的是例子、推导、概念还是检查。') }}</small>
              </span>
            </div>
            <div>
              <ShieldCheck :size="16" />
              <span>
                <b>{{ t('courseEvolution.review.systemGuards', '系统负责守界') }}</b>
                <small>{{ t('courseEvolution.review.systemGuardsDetail', '只匹配当前课程中的合法节点，未匹配内容保持不变。') }}</small>
              </span>
            </div>
            <div>
              <Check :size="16" />
              <span>
                <b>{{ t('courseEvolution.review.youDecide', '你负责决定') }}</b>
                <small>{{ t('courseEvolution.review.youDecideDetail', '逐项纳入或排除，最后一次性更新课程。') }}</small>
              </span>
            </div>
            <p><BookOpen :size="14" />{{ t('courseEvolution.review.atomicNotice', '提交前正式课程不变；提交时只应用已勾选节点。') }}</p>
          </aside>

          <main class="operation-review">
            <div class="review-toolbar">
              <div>
                <strong>{{ t('courseEvolution.review.nodeList', '节点生成预览') }}</strong>
                <small>{{ t('courseEvolution.review.nodeListHint', '每一项都对应一个真实课程块') }}</small>
              </div>
              <span>
                <button type="button" @click="selectAll">{{ t('courseEvolution.review.selectAll', '全选') }}</button>
                <button type="button" @click="clearAll">{{ t('courseEvolution.review.clearAll', '清空') }}</button>
              </span>
            </div>

            <ol class="review-list">
              <li
                v-for="(operation, index) in operations"
                :key="operation.operation_id"
                :data-selected="isSelected(operation.operation_id)"
              >
                <label class="operation-choice">
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
                  <ArrowRight :size="16" />
                  <section>
                    <small>{{ t('courseEvolution.review.aiCandidate', 'AI 候选') }}</small>
                    <p>{{ operation.payload?.after_preview }}</p>
                  </section>
                </div>
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
              {{ t('courseEvolution.review.continueLater', '稍后继续') }}
            </button>
            <button
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
import { ArrowRight, BookOpen, Check, Layers3, LoaderCircle, ShieldCheck, Sparkles, Target, X } from 'lucide-vue-next'
import { t } from '../shared/i18n'
import type { CourseEvolutionPlan } from '../stores/courseEvolution'

const props = defineProps<{
  plan: CourseEvolutionPlan
  selectedOperationIds: string[]
  acting?: boolean
}>()
const emit = defineEmits<{
  close: []
  apply: []
  'update:selectedOperationIds': [value: string[]]
}>()

const titleId = `course-evolution-review-${props.plan.change_set_id}`
const operations = computed(() => props.plan.operations.filter(
  operation => operation.operation_type !== 'ADJUST_COURSE_DIFFICULTY',
))
const selectedCount = computed(() => props.selectedOperationIds.length)
const targetRoleLabels = computed(() => {
  const labels = props.plan.impact_summary?.target_role_labels || []
  return labels.length ? labels : (props.plan.requested_roles || []).map(roleLabel)
})
const interpretation = computed(() => String(
  props.plan.impact_summary?.diagnosis
  || t('courseEvolution.review.interpretationFallback', 'AI 已按你的要求定位当前课程中的相关节点。'),
))

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
  emit('update:selectedOperationIds', operations.value.map(operation => operation.operation_id))
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
.review-backdrop { position:fixed; inset:0; z-index:1500; display:grid; place-items:center; padding:24px; background:rgba(15,23,42,.58); backdrop-filter:blur(8px); }
.review-workbench { width:min(1180px,100%); height:min(820px,calc(100vh - 48px)); display:grid; grid-template-rows:auto auto minmax(0,1fr) auto; overflow:hidden; border:1px solid rgba(255,255,255,.72); border-radius:18px; color:#172033; background:#f8fafc; box-shadow:0 30px 80px rgba(15,23,42,.28); }
.review-header { display:grid; grid-template-columns:40px minmax(0,1fr) 38px; align-items:center; gap:12px; padding:18px 22px 15px; border-bottom:1px solid #e2e8f0; background:#fff; }
.review-title-mark { width:40px; height:40px; display:grid; place-items:center; border-radius:11px; color:#fff; background:#4f46e5; }
.review-header div:nth-child(2) { min-width:0; }
.review-header small { display:block; color:#64748b; font-size:11px; font-weight:800; letter-spacing:.08em; text-transform:uppercase; }
.review-header h2 { margin:3px 0 0; font-size:19px; line-height:1.3; }
.icon-button { width:38px; height:38px; display:grid; place-items:center; border:1px solid #e2e8f0; border-radius:10px; color:#475569; background:#fff; cursor:pointer; }
.scope-contract { display:grid; grid-template-columns:minmax(0,1fr) minmax(420px,.9fr); gap:18px; padding:14px 22px; color:#eef2ff; background:#1e293b; }
.scope-sentence { min-width:0; }
.scope-sentence > span { display:flex; align-items:center; gap:6px; color:#c7d2fe; font-size:11px; font-weight:800; }
.scope-sentence strong { display:block; margin-top:5px; font-size:13px; line-height:1.5; }
.scope-sentence p { margin:3px 0 0; color:#94a3b8; font-size:11px; line-height:1.45; }
.scope-contract dl { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:7px; margin:0; }
.scope-contract dl div { min-width:0; padding:8px 10px; border:1px solid rgba(148,163,184,.22); border-radius:9px; background:rgba(255,255,255,.06); }
.scope-contract dt { overflow:hidden; color:#94a3b8; font-size:9px; text-overflow:ellipsis; white-space:nowrap; }
.scope-contract dd { overflow:hidden; margin:3px 0 0; color:#fff; font-size:12px; font-weight:800; text-overflow:ellipsis; white-space:nowrap; }
.review-body { min-height:0; display:grid; grid-template-columns:220px minmax(0,1fr); }
.review-guardrails { display:flex; flex-direction:column; gap:15px; padding:20px 18px; border-right:1px solid #e2e8f0; background:#fff; }
.review-guardrails > div { display:grid; grid-template-columns:22px minmax(0,1fr); gap:8px; color:#4f46e5; }
.review-guardrails span { display:flex; flex-direction:column; gap:3px; }
.review-guardrails b { color:#1e293b; font-size:11px; }
.review-guardrails small { color:#64748b; font-size:10px; line-height:1.5; }
.review-guardrails > p { display:flex; gap:7px; margin:auto 0 0; padding:11px; border-radius:9px; color:#0f766e; background:#f0fdfa; font-size:10px; line-height:1.5; }
.review-guardrails > p svg { flex:0 0 auto; margin-top:1px; }
.operation-review { min-height:0; display:grid; grid-template-rows:auto minmax(0,1fr); padding:16px 18px 0; }
.review-toolbar { display:flex; align-items:center; justify-content:space-between; gap:12px; padding:0 2px 12px; }
.review-toolbar > div { display:flex; flex-direction:column; gap:2px; }
.review-toolbar strong { font-size:13px; }
.review-toolbar small { color:#64748b; font-size:10px; }
.review-toolbar > span { display:flex; gap:6px; }
.review-toolbar button { min-height:28px; padding:0 10px; border:1px solid #cbd5e1; border-radius:7px; color:#475569; background:#fff; font-size:10px; cursor:pointer; }
.review-list { min-height:0; overflow:auto; display:grid; align-content:start; gap:10px; margin:0; padding:0 4px 18px 2px; list-style:none; }
.review-list > li { position:relative; padding:13px 14px; border:1px solid #cbd5e1; border-radius:12px; background:#fff; transition:border-color .16s,box-shadow .16s,opacity .16s; }
.review-list > li[data-selected="true"] { border-color:#818cf8; box-shadow:0 0 0 2px rgba(99,102,241,.1); }
.review-list > li[data-selected="false"] { opacity:.6; }
.operation-choice { position:absolute; top:12px; right:12px; display:flex; align-items:center; gap:6px; cursor:pointer; }
.operation-choice input { position:absolute; opacity:0; pointer-events:none; }
.operation-choice > span { width:20px; height:20px; display:grid; place-items:center; border:1px solid #cbd5e1; border-radius:6px; color:transparent; background:#fff; }
[data-selected="true"] .operation-choice > span { color:#fff; border-color:#4f46e5; background:#4f46e5; }
.operation-choice b { color:#475569; font-size:10px; }
.operation-heading { display:grid; grid-template-columns:30px minmax(0,1fr) auto; align-items:center; gap:9px; padding-right:150px; }
.operation-heading > span { color:#94a3b8; font:800 11px/1 ui-monospace,SFMono-Regular,Menlo,monospace; }
.operation-heading > div { min-width:0; display:flex; flex-direction:column; gap:2px; }
.operation-heading small { overflow:hidden; color:#64748b; font-size:9px; text-overflow:ellipsis; white-space:nowrap; }
.operation-heading strong { font-size:12px; }
.operation-heading em { padding:4px 7px; border-radius:999px; color:#4338ca; background:#eef2ff; font-size:9px; font-style:normal; font-weight:800; }
.operation-reason { margin:8px 0 9px 39px; color:#64748b; font-size:10px; line-height:1.45; }
.content-diff { display:grid; grid-template-columns:minmax(0,1fr) 20px minmax(0,1fr); align-items:center; gap:8px; margin-left:39px; }
.content-diff > svg { color:#94a3b8; }
.content-diff section { min-width:0; padding:9px 10px; border-radius:8px; background:#f8fafc; }
.content-diff section:last-child { background:#eef2ff; }
.content-diff small { color:#64748b; font-size:9px; font-weight:800; }
.content-diff p { max-height:78px; overflow:auto; margin:4px 0 0; color:#334155; font-size:10px; line-height:1.55; white-space:pre-wrap; }
.review-footer { display:flex; align-items:center; justify-content:space-between; gap:16px; padding:14px 22px; border-top:1px solid #e2e8f0; background:#fff; }
.review-footer > p { display:flex; align-items:center; gap:7px; margin:0; color:#64748b; font-size:10px; }
.review-footer > p svg { color:#0f766e; }
.review-footer > div { display:flex; gap:8px; }
.review-footer button { min-height:36px; display:inline-flex; align-items:center; justify-content:center; gap:6px; padding:0 15px; border-radius:9px; font-size:11px; font-weight:800; cursor:pointer; }
.review-footer .secondary { border:1px solid #cbd5e1; color:#475569; background:#fff; }
.review-footer .apply-selected { border:1px solid #4f46e5; color:#fff; background:#4f46e5; }
.review-footer .apply-selected:disabled { opacity:.48; cursor:not-allowed; }
.spinning { animation:review-spin .8s linear infinite; }
@keyframes review-spin { to { transform:rotate(360deg); } }
@media (max-width:760px) {
  .review-backdrop { padding:0; }
  .review-workbench { width:100%; height:100dvh; border:0; border-radius:0; }
  .scope-contract { grid-template-columns:1fr; gap:10px; padding:12px 14px; }
  .scope-contract dl { grid-template-columns:repeat(2,minmax(0,1fr)); }
  .review-header { padding:13px 14px; }
  .review-body { grid-template-columns:1fr; }
  .review-guardrails { display:none; }
  .operation-review { padding:13px 10px 0; }
  .operation-heading { padding-right:0; grid-template-columns:25px minmax(0,1fr); }
  .operation-heading em { display:none; }
  .operation-choice { position:static; margin-bottom:9px; }
  .operation-reason,.content-diff { margin-left:0; }
  .content-diff { grid-template-columns:1fr; }
  .content-diff > svg { justify-self:center; transform:rotate(90deg); }
  .review-footer { align-items:stretch; flex-direction:column; padding:10px 12px calc(10px + env(safe-area-inset-bottom)); }
  .review-footer > p { display:none; }
  .review-footer > div { display:grid; grid-template-columns:.8fr 1.2fr; }
}
</style>
