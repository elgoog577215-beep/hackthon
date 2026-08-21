<template>
  <Teleport to="body">
    <div v-if="modelValue" class="course-workbench-layer" @keydown="handleDialogKeydown">
      <button
        type="button"
        class="course-workbench-backdrop"
        :aria-label="t('common.cancel', '关闭')"
        @click="close"
      />
      <section
        ref="panelRef"
        class="course-workbench"
        :class="{ 'course-workbench--compact': activeSection === 'tasks' && !hasVisibleTasks }"
        data-testid="course-workbench"
        role="dialog"
        aria-modal="true"
        :aria-labelledby="titleId"
        tabindex="-1"
      >
        <header class="course-workbench__header">
          <div class="course-workbench__identity">
            <h2 :id="titleId">{{ workbenchTitle }}</h2>
          </div>

          <nav class="course-workbench__tabs" role="tablist" :aria-label="workbenchTitle">
            <button
              type="button"
              role="tab"
              data-testid="course-workbench-tab-tasks"
              :aria-selected="activeSection === 'tasks'"
              :class="{ active: activeSection === 'tasks' }"
              @click="selectSection('tasks')"
            >
              <ListChecks :size="16" />
              <span>{{ taskTabLabel }}</span>
              <small v-if="actionRequiredCount">{{ actionRequiredCount }}</small>
            </button>
            <button
              type="button"
              role="tab"
              data-testid="course-workbench-tab-question-bank"
              :aria-selected="activeSection === 'question-bank'"
              :class="{ active: activeSection === 'question-bank' }"
              @click="selectSection('question-bank')"
            >
              <ShieldCheck :size="16" />
              <span>{{ questionBankTabLabel }}</span>
            </button>
          </nav>

          <button type="button" class="course-workbench__close" :title="t('common.cancel', '关闭')" @click="close">
            <X :size="19" />
          </button>
        </header>

        <div class="course-workbench__body">
          <CourseTaskCenter
            v-if="activeSection === 'tasks'"
            :model-value="true"
            :course-id="courseId"
            embedded
            @update:model-value="close"
          />
          <QuestionBankReviewCenter
            v-else
            :model-value="true"
            :course-id="courseId"
            embedded
            @update:model-value="close"
          />
        </div>
      </section>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { ListChecks, ShieldCheck, X } from 'lucide-vue-next'
import CourseTaskCenter from '@/components/CourseTaskCenter.vue'
import QuestionBankReviewCenter from '@/components/QuestionBankReviewCenter.vue'
import { useGenerationStore } from '@/stores/generation'
import { activeLocale, t } from '@/shared/i18n'

type WorkbenchSection = 'tasks' | 'question-bank'

const props = withDefaults(defineProps<{
  modelValue: boolean
  initialSection?: WorkbenchSection
  courseId?: string
}>(), {
  initialSection: 'tasks',
  courseId: '',
})
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()
const generationStore = useGenerationStore()
const titleId = `course-workbench-${Math.random().toString(36).slice(2)}`
const panelRef = ref<HTMLElement | null>(null)
const activeSection = ref<WorkbenchSection>(props.initialSection)
const previousFocus = ref<HTMLElement | null>(null)

const isEnglish = computed(() => activeLocale.value === 'en')
const workbenchTitle = computed(() => isEnglish.value ? 'Course workbench' : '课程工作台')
const taskTabLabel = computed(() => isEnglish.value ? 'Generation tasks' : '生成任务')
const questionBankTabLabel = computed(() => isEnglish.value ? 'Question bank' : '题库管理')
const actionRequiredCount = computed(() => Array.from(generationStore.tasks.values()).filter(task => (
  (!props.courseId || task.courseId === props.courseId)
  && (
  ['waiting_for_review', 'conflict', 'error', 'paused'].includes(task.status)
  || (task.status === 'completed_with_warnings'
    && task.publicationAllowed !== true
    && task.recovery?.state !== 'completed')
  )
)).length)
const hasVisibleTasks = computed(() => {
  const globalTasks = generationStore.globalTasks || []
  const localTasks = Array.from(generationStore.tasks.values())
  if (!props.courseId) return globalTasks.length > 0 || localTasks.length > 0
  return globalTasks.some(task => task.course_id === props.courseId)
    || localTasks.some(task => task.courseId === props.courseId)
})

watch(() => props.modelValue, async open => {
  if (!open) return
  previousFocus.value = document.activeElement instanceof HTMLElement ? document.activeElement : null
  activeSection.value = props.initialSection
  await nextTick()
  panelRef.value?.focus()
}, { immediate: true })

watch(() => props.initialSection, section => {
  if (props.modelValue) activeSection.value = section
})

function selectSection(section: WorkbenchSection) {
  activeSection.value = section
}

function close() {
  emit('update:modelValue', false)
  nextTick(() => previousFocus.value?.focus())
}

function handleDialogKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    event.preventDefault()
    close()
    return
  }
  if (event.key !== 'Tab' || !panelRef.value) return
  const focusable = [...panelRef.value.querySelectorAll<HTMLElement>(
    'button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [href], [tabindex]:not([tabindex="-1"])',
  )].filter(element => !element.hasAttribute('hidden'))
  if (!focusable.length) {
    event.preventDefault()
    panelRef.value.focus()
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
.course-workbench-layer { position:fixed; inset:0; z-index:540; display:grid; place-items:center; padding:20px; }
.course-workbench-backdrop { position:absolute; inset:0; width:100%; height:100%; border:0; background:rgba(30,41,59,.38); cursor:default; }
.course-workbench { position:relative; width:min(1320px,calc(100vw - 40px)); height:min(860px,calc(100vh - 40px)); display:grid; grid-template-rows:64px minmax(0,1fr); overflow:hidden; border:1px solid var(--lz-border); border-radius:12px; color:var(--lz-text); background:#fff; box-shadow:var(--lz-shadow-overlay); outline:none; }
.course-workbench--compact { height:min(360px,calc(100vh - 40px)); }
.course-workbench__header { display:grid; grid-template-columns:minmax(220px,1fr) auto minmax(44px,1fr); align-items:center; gap:16px; padding:0 12px 0 20px; border-bottom:1px solid var(--lz-border); background:#fff; }
.course-workbench__identity { min-width:0; display:flex; align-items:center; }
.course-workbench__identity h2 { margin:0; color:var(--lz-text-strong); font-size:18px; }
.course-workbench__tabs { align-self:stretch; display:flex; align-items:stretch; gap:22px; }
.course-workbench__tabs button { min-height:40px; display:inline-flex; align-items:center; gap:7px; padding:0 2px; border:0; border-bottom:2px solid transparent; color:var(--lz-text-secondary); background:transparent; font-size:13px; font-weight:700; cursor:pointer; }
.course-workbench__tabs button:hover,.course-workbench__tabs button:focus-visible { color:var(--lz-text-strong); outline:none; }
.course-workbench__tabs button.active { border-bottom-color:var(--lz-brand); color:var(--lz-brand-strong); }
.course-workbench__tabs small { min-width:20px; height:20px; display:grid; place-items:center; padding:0 6px; border-radius:10px; color:#fff; background:var(--lz-warning); font-size:12px; }
.course-workbench__close { width:38px; height:38px; display:grid; justify-self:end; place-items:center; border:0; border-radius:9px; color:var(--lz-text-secondary); background:transparent; cursor:pointer; }
.course-workbench__close:hover,.course-workbench__close:focus-visible { color:var(--lz-text-strong); background:var(--lz-surface-muted); outline:none; }
.course-workbench__body { min-height:0; overflow:hidden; }
@media (max-width:760px) {
  .course-workbench-layer { align-items:end; padding:0; }
  .course-workbench { width:100%; height:calc(100vh - 40px); grid-template-rows:auto minmax(0,1fr); border-radius:12px 12px 0 0; }
  .course-workbench--compact { height:min(390px,calc(100vh - 40px)); }
  .course-workbench__header { grid-template-columns:minmax(0,1fr) auto; gap:7px 10px; padding:8px 10px 8px 14px; }
  .course-workbench__identity h2 { font-size:16px; }
  .course-workbench__tabs { grid-column:1 / -1; grid-row:2; width:100%; gap:12px; }
  .course-workbench__tabs button { min-height:38px; flex:1; justify-content:center; }
  .course-workbench__close { width:34px; height:34px; }
}
</style>
