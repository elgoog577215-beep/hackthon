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
              <small>{{ t('courseEvolution.workspace.kicker', '课程内容迭代') }}</small>
              <h2 :id="titleId">{{ t('courseEvolution.workspace.title', '课程调整工作台') }}</h2>
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
            <aside class="course-adjustment-guide">
              <div>
                <small>{{ t('courseEvolution.workspace.guideKicker', '调整流程') }}</small>
                <strong>{{ t('courseEvolution.workspace.guideTitle', '先定目标，再看影响') }}</strong>
                <p>{{ t('courseEvolution.workspace.guideBody', '描述你希望课程发生的变化，系统会在选定边界内生成候选，由你逐项确认。') }}</p>
              </div>
              <ol>
                <li>
                  <span>1</span>
                  <div>
                    <b>{{ t('courseEvolution.workspace.stepIntent', '说明变化') }}</b>
                    <small>{{ t('courseEvolution.workspace.stepIntentDetail', '用一句话描述希望课程怎么变') }}</small>
                  </div>
                </li>
                <li>
                  <span>2</span>
                  <div>
                    <b>{{ t('courseEvolution.workspace.stepScope', '限定范围') }}</b>
                    <small>{{ t('courseEvolution.workspace.stepScopeDetail', '范围是硬边界，AI 不会自行扩大') }}</small>
                  </div>
                </li>
                <li>
                  <span>3</span>
                  <div>
                    <b>{{ t('courseEvolution.workspace.stepReview', '审阅候选') }}</b>
                    <small>{{ t('courseEvolution.workspace.stepReviewDetail', '确认前正式课程保持不变') }}</small>
                  </div>
                </li>
              </ol>
              <p class="course-adjustment-guard">
                <ShieldCheck :size="17" />
                <span>
                  <b>{{ t('courseEvolution.workspace.guardTitle', '修改始终可控') }}</b>
                  <small>{{ t('courseEvolution.workspace.guardBody', '未确认内容、其他课程和历史学习记录都不会改变。') }}</small>
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
          </div>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { BookOpenText, GitBranchPlus, RefreshCw, ShieldCheck, X } from 'lucide-vue-next'
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
.course-adjustment-body { min-height:0; display:grid; grid-template-columns:260px minmax(0,1fr); }
.course-adjustment-guide { min-height:0; display:flex; flex-direction:column; gap:28px; padding:28px 24px 24px; border-right:1px solid var(--lz-border); background:#fff; }
.course-adjustment-guide>div { display:grid; gap:6px; }
.course-adjustment-guide>div small { color:var(--lz-brand-strong); font-size:11px; font-weight:750; }
.course-adjustment-guide>div strong { color:var(--lz-text-strong); font-size:17px; letter-spacing:-.015em; }
.course-adjustment-guide>div p { margin:0; color:var(--lz-text-secondary); font-size:12px; line-height:1.65; }
.course-adjustment-guide ol { position:relative; display:grid; gap:24px; margin:0; padding:0; list-style:none; }
.course-adjustment-guide ol::before { position:absolute; top:28px; bottom:28px; left:16px; width:1px; background:#dbe1ee; content:""; }
.course-adjustment-guide li { position:relative; display:grid; grid-template-columns:32px minmax(0,1fr); gap:11px; }
.course-adjustment-guide li>span { z-index:1; width:32px; height:32px; display:grid; place-items:center; border:1px solid #cfd6e6; border-radius:10px; color:var(--lz-brand-strong); background:#fff; font-size:12px; font-weight:800; }
.course-adjustment-guide li>div { display:grid; gap:3px; padding-top:1px; }
.course-adjustment-guide li b { color:var(--lz-text-strong); font-size:13px; }
.course-adjustment-guide li small { color:var(--lz-text-muted); font-size:11px; line-height:1.5; }
.course-adjustment-guard { display:grid; grid-template-columns:20px minmax(0,1fr); gap:9px; margin:auto 0 0; padding-top:18px; border-top:1px solid var(--lz-border); color:#047857; }
.course-adjustment-guard span { display:grid; gap:3px; }
.course-adjustment-guard b { font-size:12px; }
.course-adjustment-guard small { color:#527265; font-size:11px; line-height:1.5; }
.course-adjustment-main { min-height:0; overflow:hidden; }
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
  .course-adjustment-guide { display:none; }
}
@media (prefers-reduced-motion:reduce) {
  .course-adjustment-layer-enter-active,.course-adjustment-layer-leave-active,.course-adjustment-layer-enter-active .course-adjustment-workspace { transition:none; }
}
</style>
