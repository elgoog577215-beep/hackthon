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
        :class="{ 'course-workbench--compact': !hasVisibleTasks }"
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

          <button type="button" class="course-workbench__close" :title="t('common.cancel', '关闭')" @click="close">
            <X :size="19" />
          </button>
        </header>

        <div class="course-workbench__body">
          <CourseTaskCenter
            :model-value="true"
            :course-id="courseId"
            :surface="surface"
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
import { X } from 'lucide-vue-next'
import CourseTaskCenter from '@/components/CourseTaskCenter.vue'
import { useGenerationStore } from '@/stores/generation'
import { activeLocale, t } from '@/shared/i18n'

const props = withDefaults(defineProps<{
  modelValue: boolean
  courseId?: string
  /** 透传给任务中心：教师端与学生端的状态说法不同。 */
  surface?: 'learner' | 'teacher'
}>(), {
  courseId: '',
  surface: 'learner',
})
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()
const generationStore = useGenerationStore()
const titleId = `course-workbench-${Math.random().toString(36).slice(2)}`
const panelRef = ref<HTMLElement | null>(null)
const previousFocus = ref<HTMLElement | null>(null)

const isEnglish = computed(() => activeLocale.value === 'en')
const workbenchTitle = computed(() => isEnglish.value ? 'Course tasks' : '课程任务')
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
  await nextTick()
  panelRef.value?.focus()
}, { immediate: true })

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
.course-workbench__header { display:grid; grid-template-columns:minmax(0,1fr) auto; align-items:center; gap:16px; padding:0 12px 0 20px; border-bottom:1px solid var(--lz-border); background:#fff; }
.course-workbench__identity { min-width:0; display:flex; align-items:center; }
.course-workbench__identity h2 { margin:0; color:var(--lz-text-strong); font-size:18px; }
.course-workbench__close { width:38px; height:38px; display:grid; justify-self:end; place-items:center; border:0; border-radius:9px; color:var(--lz-text-secondary); background:transparent; cursor:pointer; }
.course-workbench__close:hover,.course-workbench__close:focus-visible { color:var(--lz-text-strong); background:var(--lz-surface-muted); outline:none; }
.course-workbench__body { min-height:0; overflow:hidden; }
@media (max-width:760px) {
  .course-workbench-layer { align-items:end; padding:0; }
  .course-workbench { width:100%; height:calc(100vh - 40px); grid-template-rows:auto minmax(0,1fr); border-radius:12px 12px 0 0; }
  .course-workbench--compact { height:min(390px,calc(100vh - 40px)); }
  .course-workbench__header { grid-template-columns:minmax(0,1fr) auto; gap:7px 10px; padding:8px 10px 8px 14px; }
  .course-workbench__identity h2 { font-size:16px; }
  .course-workbench__close { width:34px; height:34px; }
}
</style>
