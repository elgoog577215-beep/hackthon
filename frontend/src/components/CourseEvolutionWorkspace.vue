<template>
  <Teleport to="body">
    <Transition name="course-adjustment-layer">
      <div v-if="modelValue" class="course-adjustment-layer" @keydown="handleKeydown">
        <button
          type="button"
          class="course-adjustment-backdrop"
          :aria-label="t('courseEvolution.workspace.close', '关闭课程调整工作台')"
          @click="close"
        />
        <section
          ref="workspaceRef"
          class="course-adjustment-workspace"
          role="dialog"
          aria-modal="true"
          :aria-labelledby="titleId"
          tabindex="-1"
        >
          <header class="course-adjustment-header">
            <span class="course-adjustment-mark"><GitBranchPlus :size="20" /></span>
            <div class="course-adjustment-title">
              <small>{{ t('courseEvolution.workspace.kicker', '课程发布后维护') }}</small>
              <h2 :id="titleId">{{ t('courseEvolution.workspace.title', '全课联动修改') }}</h2>
            </div>
            <div class="course-adjustment-context" :title="contextLabel">
              <BookOpenText :size="15" />
              <span>{{ contextLabel }}</span>
            </div>
            <button
              type="button"
              class="course-adjustment-refresh"
              :title="t('courseEvolution.workspace.refresh', '重新读取调整状态')"
              :aria-label="t('courseEvolution.workspace.refresh', '重新读取调整状态')"
              :disabled="store.loading"
              @click="store.evaluate(courseId)"
            >
              <RefreshCw :size="17" :class="{ spinning: store.loading }" />
            </button>
            <button
              type="button"
              class="course-adjustment-close"
              :title="t('courseEvolution.workspace.close', '关闭课程调整工作台')"
              :aria-label="t('courseEvolution.workspace.close', '关闭课程调整工作台')"
              @click="close"
            >
              <X :size="19" />
            </button>
          </header>

          <div class="course-adjustment-body">
            <aside class="course-change-impact" aria-label="课程影响范围">
              <div class="course-change-pane-heading">
                <small>{{ t('courseEvolution.workspace.impactKicker', '全课联动') }}</small>
                <strong>{{ t('courseEvolution.workspace.impactTitle', '影响范围') }}</strong>
                <p v-if="planning">{{ impactStatusLabel }}</p>
                <p v-else>{{ t('courseEvolution.workspace.impactPending', '直接说明你想达到的效果，AI 会读取当前课程并自行判断是局部更新、结构重整还是混合修改。') }}</p>
              </div>

              <div class="course-change-assets">
                <div
                  v-for="asset in assetImpactItems"
                  :key="asset.key"
                  class="course-change-asset"
                  :class="{ affected: asset.count > 0 }"
                >
                  <span><component :is="asset.icon" :size="15" />{{ asset.label }}</span>
                  <b>{{ planning ? asset.count : '—' }}</b>
                </div>
              </div>

              <div v-if="planning?.structural_operations.length" class="course-change-structure-note">
                <GitMerge :size="16" />
                <span>
                  <b>{{ t('courseEvolution.workspace.structureChange', '包含结构变化') }}</b>
                  <small>{{ structureSummary }}</small>
                </span>
              </div>

              <ol v-else-if="!planning" class="course-change-flow">
                <li><span>1</span>{{ t('courseEvolution.workspace.flowUnderstand', '理解目标与保护要求') }}</li>
                <li><span>2</span>{{ t('courseEvolution.workspace.flowDiscover', '扫描并扩展真实影响') }}</li>
                <li><span>3</span>{{ t('courseEvolution.workspace.flowReview', '逐项审阅并一次应用') }}</li>
              </ol>

              <p class="course-adjustment-guard">
                <ShieldCheck :size="17" />
                <span>
                  <b>{{ t('courseEvolution.workspace.guardTitle', '修改始终可控') }}</b>
                  <small>{{ t('courseEvolution.workspace.guardBody', '确认前正式课程不变；保护项、历史版本和最后可用结果不会被静默覆盖。') }}</small>
                </span>
              </p>
            </aside>

            <main class="course-adjustment-main">
              <CourseEvolutionPanel
                :course-id="courseId"
                :section-id="sectionId"
                :focus-plan-id="focusPlanId"
                surface="workspace"
                :show-heading="false"
                @course-applied="emit('courseApplied', $event)"
              />
            </main>

            <aside class="course-change-ai" aria-label="AI 对课程变更的理解">
              <div class="course-change-pane-heading">
                <small>{{ t('courseEvolution.workspace.aiKicker', 'AI 课程编辑') }}</small>
                <strong>{{ t('courseEvolution.workspace.aiTitle', '当前理解') }}</strong>
                <p>{{ t('courseEvolution.workspace.aiHint', '这里保留你的原话和 AI 当前判断；发现新影响时，方案会升级而不会曲解原意。') }}</p>
              </div>

              <template v-if="planning">
                <section class="course-change-brief-block raw-request">
                  <small>{{ t('courseEvolution.workspace.teacherRequest', '老师原话') }}</small>
                  <p>{{ planning.intent.raw_request }}</p>
                </section>
                <section class="course-change-brief-block">
                  <small>{{ t('courseEvolution.workspace.aiInterpretation', 'AI 当前的理解') }}</small>
                  <p>{{ planning.intent.interpreted_goal }}</p>
                  <span class="course-change-strategy" :class="planning.strategy_status">
                    {{ strategyLabel }}
                  </span>
                </section>
                <section v-if="planning.intent.hard_constraints.length || planning.intent.protected_requirements.length" class="course-change-brief-block">
                  <small>{{ t('courseEvolution.workspace.protectedRequirements', '必须遵守') }}</small>
                  <ul>
                    <li v-for="item in protectedRequirements" :key="item">{{ item }}</li>
                  </ul>
                </section>
                <section v-if="planning.replan_reasons.length" class="course-change-replan">
                  <RefreshCw :size="15" />
                  <span>
                    <b>{{ t('courseEvolution.workspace.replanned', '已根据新证据升级方案') }}</b>
                    <small>{{ planning.replan_reasons.at(-1) }}</small>
                  </span>
                </section>
                <section v-if="planning.structure_review_status !== 'not_required'" class="course-change-checkpoint" :class="planning.structure_review_status">
                  <CircleCheckBig v-if="planning.structure_review_status === 'confirmed'" :size="16" />
                  <GitPullRequestDraft v-else :size="16" />
                  <span>
                    <b>{{ structureReviewLabel }}</b>
                    <small>{{ t('courseEvolution.workspace.structureReviewHint', '只确认 AI 是否理解对了新结构；确认后才批量生成下游候选。') }}</small>
                  </span>
                </section>
              </template>
              <div v-else class="course-change-ai-empty">
                <Sparkles :size="22" />
                <strong>{{ t('courseEvolution.workspace.noPlanTitle', '等待你说明想要的结果') }}</strong>
                <p>{{ t('courseEvolution.workspace.noPlanBody', '不用先选“内容修改”还是“结构修改”，也不用使用系统术语。') }}</p>
              </div>
            </aside>
          </div>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import {
  BookOpenText,
  BookText,
  CircleCheckBig,
  ClipboardList,
  FileQuestion,
  GitBranchPlus,
  GitMerge,
  GitPullRequestDraft,
  Presentation,
  RefreshCw,
  ScrollText,
  ShieldCheck,
  Sparkles,
  X,
} from 'lucide-vue-next'
import CourseEvolutionPanel from './CourseEvolutionPanel.vue'
import { t } from '../shared/i18n'
import {
  useCourseEvolutionStore,
  type CourseEvolutionApplicationPresentation,
} from '../stores/courseEvolution'

const props = withDefaults(defineProps<{
  modelValue: boolean
  courseId: string
  sectionId?: string
  courseTitle?: string
  sectionTitle?: string
  focusPlanId?: string
}>(), {
  sectionId: '',
  courseTitle: '',
  sectionTitle: '',
  focusPlanId: '',
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  courseApplied: [presentation: CourseEvolutionApplicationPresentation]
}>()

const store = useCourseEvolutionStore()
const workspaceRef = ref<HTMLElement | null>(null)
const previousFocus = ref<HTMLElement | null>(null)
const titleId = `course-adjustment-${Math.random().toString(36).slice(2)}`
const contextLabel = computed(() => [
  props.courseTitle || t('courseEvolution.workspace.currentCourse', '当前课程'),
  props.sectionTitle,
].filter(Boolean).join(' · '))
const focusedPlan = computed(() => {
  if (props.focusPlanId) {
    const focused = store.plans.find(plan => (
      plan.change_set_id === props.focusPlanId || plan.plan_id === props.focusPlanId
    ))
    if (focused?.teacher_change_planning) return focused
  }
  return [...store.plans].reverse().find(plan => plan.teacher_change_planning) || null
})
const planning = computed(() => focusedPlan.value?.teacher_change_planning || null)
const assetImpactItems = computed(() => {
  const definitions = [
    { key: 'outline', label: t('courseEvolution.workspace.assetOutline', '课程大纲'), icon: BookText },
    { key: 'lesson_plan', label: t('courseEvolution.workspace.assetLessonPlan', '教案'), icon: ClipboardList },
    { key: 'question_bank', label: t('courseEvolution.workspace.assetQuestionBank', '题库'), icon: FileQuestion },
    { key: 'teacher_script', label: t('courseEvolution.workspace.assetTeacherScript', '讲稿'), icon: ScrollText },
    { key: 'slide_deck', label: t('courseEvolution.workspace.assetSlides', 'PPT'), icon: Presentation },
  ]
  return definitions.map(item => ({
    ...item,
    count: planning.value?.unit_migrations.filter(migration => migration.asset_type === item.key).length || 0,
  }))
})
const protectedRequirements = computed(() => [
  ...(planning.value?.intent.hard_constraints || []),
  ...(planning.value?.intent.protected_requirements || []),
])
const impactStatusLabel = computed(() => {
  if (!planning.value) return ''
  const count = planning.value.unit_migrations.length
  if (planning.value.strategy_status === 'provisional') {
    return t('courseEvolution.workspace.impactExpanding', '已找到 {count} 个候选，影响范围仍在扩展。').replace('{count}', String(count))
  }
  return t('courseEvolution.workspace.impactResolved', '已确认 {count} 个受影响单元。').replace('{count}', String(count))
})
const structureSummary = computed(() => t(
  'courseEvolution.workspace.structureSummary',
  '{count} 个结构操作，先核对新课程树，再处理教案、题库、讲稿与 PPT。',
).replace('{count}', String(planning.value?.structural_operations.length || 0)))
const strategyLabel = computed(() => {
  if (!planning.value) return ''
  if (planning.value.strategy_status === 'provisional') {
    return t('courseEvolution.workspace.strategyProvisional', '暂定理解 · 会随扫描结果调整')
  }
  const structural = planning.value.execution_strategies.includes('structural_regeneration')
  const semantic = planning.value.execution_strategies.includes('semantic_impact')
  if (structural && semantic) return t('courseEvolution.workspace.strategyMixed', '结构重整 + 内容联动')
  if (structural) return t('courseEvolution.workspace.strategyStructural', '结构迁移与约束式重新生成')
  return t('courseEvolution.workspace.strategySemantic', '内容影响与定向修改')
})
const structureReviewLabel = computed(() => planning.value?.structure_review_status === 'confirmed'
  ? t('courseEvolution.workspace.structureConfirmed', '新结构已确认')
  : t('courseEvolution.workspace.structurePending', '等待确认新结构'))

watch(() => props.modelValue, async open => {
  if (!open) return
  previousFocus.value = document.activeElement instanceof HTMLElement ? document.activeElement : null
  await nextTick()
  workspaceRef.value?.focus()
}, { immediate: true })

function close() {
  emit('update:modelValue', false)
  nextTick(() => previousFocus.value?.focus())
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    event.preventDefault()
    close()
    return
  }
  if (event.key !== 'Tab' || !workspaceRef.value) return
  const focusable = [...workspaceRef.value.querySelectorAll<HTMLElement>(
    'button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [href], [tabindex]:not([tabindex="-1"])',
  )].filter(element => !element.hasAttribute('hidden'))
  if (!focusable.length) {
    event.preventDefault()
    workspaceRef.value.focus()
    return
  }
  const first = focusable[0]!
  const last = focusable[focusable.length - 1]!
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}
</script>

<style scoped>
.course-adjustment-layer { position:fixed; inset:0; z-index:1200; display:grid; place-items:center; padding:24px; }
.course-adjustment-backdrop { position:absolute; inset:0; width:100%; height:100%; border:0; background:rgba(15,23,42,.5); backdrop-filter:blur(4px); cursor:default; }
.course-adjustment-workspace { position:relative; width:min(1240px,calc(100vw - 48px)); height:min(840px,calc(100dvh - 48px)); display:grid; grid-template-rows:72px minmax(0,1fr); overflow:hidden; border-radius:16px; color:var(--lz-text); background:#f7f8fc; box-shadow:0 30px 80px rgba(15,23,42,.28); outline:0; }
.course-adjustment-header { display:grid; grid-template-columns:42px minmax(190px,1fr) minmax(180px,auto) 38px 38px; align-items:center; gap:12px; padding:0 18px 0 20px; border-bottom:1px solid var(--lz-border); background:#fff; }
.course-adjustment-mark { width:42px; height:42px; display:grid; place-items:center; border-radius:12px; color:#fff; background:#5b54e8; box-shadow:0 9px 20px rgba(79,70,229,.22); }
.course-adjustment-title { min-width:0; }
.course-adjustment-title small { display:block; color:var(--lz-text-muted); font-size:11px; font-weight:700; }
.course-adjustment-title h2 { margin:2px 0 0; color:var(--lz-text-strong); font-family:inherit; font-size:19px; letter-spacing:-.02em; }
.course-adjustment-context { min-width:0; max-width:360px; display:flex; align-items:center; justify-self:end; gap:7px; padding:8px 10px; border-radius:9px; color:var(--lz-text-secondary); background:#f4f5f8; font-size:12px; }
.course-adjustment-context svg { flex:none; color:var(--lz-brand); }
.course-adjustment-context span { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.course-adjustment-refresh,.course-adjustment-close { width:38px; height:38px; display:grid; place-items:center; border:0; border-radius:9px; color:var(--lz-text-secondary); background:transparent; cursor:pointer; }
.course-adjustment-refresh:hover:not(:disabled),.course-adjustment-close:hover { color:var(--lz-brand-strong); background:var(--lz-brand-soft); }
.course-adjustment-refresh:focus-visible,.course-adjustment-close:focus-visible { outline:3px solid rgba(99,102,241,.24); outline-offset:1px; }
.course-adjustment-refresh:disabled { opacity:.45; cursor:not-allowed; }
.course-adjustment-body { min-height:0; display:grid; grid-template-columns:clamp(184px,19vw,232px) minmax(350px,1fr) clamp(230px,24vw,292px); }
.course-change-impact,.course-change-ai { min-height:0; overflow:auto; padding:24px 20px; background:#fff; }
.course-change-impact { display:flex; flex-direction:column; gap:22px; border-right:1px solid var(--lz-border); }
.course-change-ai { display:flex; flex-direction:column; gap:18px; border-left:1px solid var(--lz-border); }
.course-change-pane-heading { display:grid; gap:5px; }
.course-change-pane-heading small { color:var(--lz-brand-strong); font-size:10px; font-weight:800; letter-spacing:.08em; text-transform:uppercase; }
.course-change-pane-heading strong { color:var(--lz-text-strong); font-size:16px; letter-spacing:-.015em; }
.course-change-pane-heading p { margin:0; color:var(--lz-text-secondary); font-size:11px; line-height:1.6; }
.course-change-assets { display:grid; gap:6px; }
.course-change-asset { display:flex; align-items:center; justify-content:space-between; min-height:38px; padding:0 10px; border:1px solid transparent; border-radius:9px; color:var(--lz-text-secondary); background:#f7f8fb; }
.course-change-asset.affected { border-color:#dcd9ff; color:var(--lz-brand-strong); background:#f4f2ff; }
.course-change-asset span { display:flex; align-items:center; gap:8px; font-size:12px; font-weight:650; }
.course-change-asset b { min-width:22px; text-align:center; font-size:12px; }
.course-change-structure-note,.course-change-replan,.course-change-checkpoint { display:grid; grid-template-columns:18px minmax(0,1fr); gap:8px; padding:11px; border-radius:10px; }
.course-change-structure-note { color:#8a4b08; background:#fff7e8; }
.course-change-structure-note span,.course-change-replan span,.course-change-checkpoint span { display:grid; gap:3px; }
.course-change-structure-note b,.course-change-replan b,.course-change-checkpoint b { font-size:11px; }
.course-change-structure-note small,.course-change-replan small,.course-change-checkpoint small { color:inherit; font-size:10px; line-height:1.5; opacity:.84; }
.course-change-flow { display:grid; gap:14px; margin:0; padding:0; list-style:none; }
.course-change-flow li { display:grid; grid-template-columns:24px minmax(0,1fr); align-items:center; gap:8px; color:var(--lz-text-secondary); font-size:11px; line-height:1.45; }
.course-change-flow span { width:24px; height:24px; display:grid; place-items:center; border-radius:8px; color:var(--lz-brand-strong); background:var(--lz-brand-soft); font-size:10px; font-weight:800; }
.course-adjustment-guard { display:grid; grid-template-columns:20px minmax(0,1fr); gap:9px; margin:auto 0 0; padding-top:18px; border-top:1px solid var(--lz-border); color:#047857; }
.course-adjustment-guard span { display:grid; gap:3px; }
.course-adjustment-guard b { font-size:12px; }
.course-adjustment-guard small { color:#527265; font-size:11px; line-height:1.5; }
.course-adjustment-main { min-height:0; overflow:hidden; }
.course-change-brief-block { display:grid; gap:7px; padding-bottom:14px; border-bottom:1px solid var(--lz-border); }
.course-change-brief-block small { color:var(--lz-text-muted); font-size:10px; font-weight:700; }
.course-change-brief-block p { margin:0; color:var(--lz-text-strong); font-size:12px; line-height:1.65; }
.course-change-brief-block.raw-request p { padding-left:10px; border-left:2px solid #c9c5ff; color:var(--lz-text-secondary); }
.course-change-brief-block ul { display:grid; gap:6px; margin:0; padding-left:17px; color:var(--lz-text-secondary); font-size:11px; line-height:1.5; }
.course-change-strategy { width:fit-content; padding:5px 7px; border-radius:7px; color:#315f52; background:#edf8f4; font-size:10px; font-weight:750; }
.course-change-strategy.provisional { color:#89590f; background:#fff7e8; }
.course-change-replan { color:#554bb8; background:#f3f1ff; }
.course-change-checkpoint { color:#965b0b; background:#fff7e8; }
.course-change-checkpoint.confirmed { color:#087354; background:#ecf9f4; }
.course-change-ai-empty { display:grid; place-items:center; gap:8px; margin:auto 0; padding:20px 12px; text-align:center; color:var(--lz-text-muted); }
.course-change-ai-empty svg { color:var(--lz-brand); }
.course-change-ai-empty strong { color:var(--lz-text-strong); font-size:13px; }
.course-change-ai-empty p { margin:0; font-size:11px; line-height:1.6; }
.spinning { animation:course-adjustment-spin .8s linear infinite; }
.course-adjustment-layer-enter-active,.course-adjustment-layer-leave-active { transition:opacity .2s ease; }
.course-adjustment-layer-enter-active .course-adjustment-workspace { transition:transform .28s cubic-bezier(.16,1,.3,1),filter .28s ease; }
.course-adjustment-layer-enter-from,.course-adjustment-layer-leave-to { opacity:0; }
.course-adjustment-layer-enter-from .course-adjustment-workspace { transform:translateY(18px) scale(.985); filter:blur(4px); }
@keyframes course-adjustment-spin { to { transform:rotate(360deg); } }
@media (max-width:820px) {
  .course-adjustment-layer { align-items:end; padding:0; }
  .course-adjustment-workspace { width:100%; height:calc(100dvh - 32px); border-radius:16px 16px 0 0; }
  .course-adjustment-header { grid-template-columns:38px minmax(0,1fr) 38px 38px; gap:8px; padding:0 10px 0 14px; }
  .course-adjustment-mark { width:38px; height:38px; }
  .course-adjustment-title h2 { font-size:17px; }
  .course-adjustment-context { display:none; }
  .course-adjustment-body { grid-template-columns:minmax(0,1fr); }
  .course-change-impact,.course-change-ai { display:none; }
}
@media (prefers-reduced-motion:reduce) {
  .course-adjustment-layer-enter-active,.course-adjustment-layer-leave-active,.course-adjustment-layer-enter-active .course-adjustment-workspace { transition:none; }
}
</style>
