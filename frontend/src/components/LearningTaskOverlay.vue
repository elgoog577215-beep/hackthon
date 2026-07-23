<template>
  <section
    class="learning-tool-overlay task-overlay"
    role="dialog"
    aria-modal="true"
    :aria-label="t('taskOverlay.title', '学习任务')"
    @keydown.esc.prevent="emit('close')"
  >
    <button
      class="task-overlay__close"
      type="button"
      :title="t('taskOverlay.close', '关闭并返回正文')"
      :aria-label="t('taskOverlay.close', '关闭并返回正文')"
      @click="emit('close')"
    >
      <X :size="18" />
    </button>
    <CourseWorkspaceTabs
      active-item="practice"
      :practice-available="true"
      @lesson-plan="emit('lesson-plan')"
      @course="emit('course')"
      @ppt="emit('ppt')"
    />
    <PracticeWorkspace
      class="task-workspace"
      :course-id="courseId"
      :node-id="nodeId"
      :node-label="nodeLabel"
      scope="node"
      @ask-teacher="emit('askTeacher', $event)"
      @graded="emit('graded')"
    />
  </section>
</template>

<script setup lang="ts">
import { X } from 'lucide-vue-next'
import CourseWorkspaceTabs from './CourseWorkspaceTabs.vue'
import PracticeWorkspace from './PracticeWorkspace.vue'
import { t } from '../shared/i18n'

withDefaults(defineProps<{
  courseId: string
  nodeId?: string
  nodeLabel?: string
  originRect?: { top: number; left: number; width: number; height: number } | null
  recordCount?: number
}>(), {
  recordCount: 0,
})
const emit = defineEmits<{
  (event: 'close' | 'graded' | 'records' | 'stats' | 'outline' | 'lesson-plan' | 'course' | 'ppt'): void
  (event: 'askTeacher', payload: { text: string; nodeId: string }): void
}>()
</script>

<style scoped>
.task-overlay { position:absolute; inset:0; z-index:34; width:100%; height:100%; min-width:0; min-height:0; display:flex; flex-direction:column; overflow:hidden; background:#fff; box-shadow:var(--lz-shadow-overlay); }
.task-overlay__close { position:absolute; top:11px; right:12px; z-index:3; width:32px; height:32px; display:grid; place-items:center; padding:0; border:0; border-radius:6px; color:var(--lz-text-secondary); background:#fff; cursor:pointer; }
.task-overlay__close:hover { color:var(--lz-text-strong); background:var(--lz-surface-muted); }
.task-overlay__close:focus-visible { outline:2px solid var(--lz-brand); outline-offset:2px; }
.task-overlay :deep(.course-workspace-tabs) { min-height:50px; flex:0 0 auto; border:0; border-bottom:1px solid var(--lz-border); border-radius:0; padding:6px 52px 6px 12px; background:#fff; }
.task-workspace { flex:1; min-width:0; min-height:0; }
@media (max-width:767px) {
  .task-overlay { position:fixed; inset:56px 0 calc(52px + env(safe-area-inset-bottom,0px)); z-index:105; width:auto; height:auto; }
}
</style>
