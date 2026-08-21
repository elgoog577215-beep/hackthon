<template>
  <section
    class="learning-tool-overlay task-overlay"
    role="dialog"
    aria-modal="true"
    :aria-label="t('questionBook.title', '题库本')"
    @keydown.esc.prevent="emit('close')"
  >
    <header class="task-overlay__header">
      <div class="task-overlay__identity">
        <span><BookOpenCheck :size="18" /></span>
        <div>
          <strong>{{ t('questionBook.title', '题库本') }}</strong>
          <small>{{ t('questionBook.subtitle', '按课程目标生成、练习与巩固') }}</small>
        </div>
      </div>
      <button
        class="task-overlay__close"
        type="button"
        :title="t('taskOverlay.close', '关闭并返回正文')"
        :aria-label="t('taskOverlay.close', '关闭并返回正文')"
        @click="emit('close')"
      >
        <X :size="18" />
      </button>
    </header>
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
import { BookOpenCheck, X } from 'lucide-vue-next'
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
  (event: 'close' | 'graded'): void
  (event: 'askTeacher', payload: { text: string; nodeId: string }): void
}>()
</script>

<style scoped>
.task-overlay { position:absolute; inset:0; z-index:34; width:100%; height:100%; min-width:0; min-height:0; display:flex; flex-direction:column; overflow:hidden; background:#fff; box-shadow:var(--lz-shadow-overlay); }
.task-overlay__header { min-height:56px; flex:0 0 auto; display:flex; align-items:center; justify-content:space-between; gap:16px; padding:8px 12px 8px 16px; border-bottom:1px solid var(--lz-border); background:#fff; }
.task-overlay__identity { min-width:0; display:flex; align-items:center; gap:10px; }
.task-overlay__identity>span { width:34px; height:34px; flex:0 0 auto; display:grid; place-items:center; border-radius:9px; color:var(--lz-brand-strong); background:var(--lz-brand-soft); }
.task-overlay__identity div { min-width:0; display:grid; gap:1px; }
.task-overlay__identity strong { color:var(--lz-text-strong); font-size:14px; }
.task-overlay__identity small { color:var(--lz-text-muted); font-size:10px; }
.task-overlay__close { width:32px; height:32px; display:grid; place-items:center; padding:0; border:0; border-radius:6px; color:var(--lz-text-secondary); background:#fff; cursor:pointer; }
.task-overlay__close:hover { color:var(--lz-text-strong); background:var(--lz-surface-muted); }
.task-overlay__close:focus-visible { outline:2px solid var(--lz-brand); outline-offset:2px; }
.task-workspace { flex:1; min-width:0; min-height:0; }
@media (max-width:767px) {
  .task-overlay { position:fixed; inset:56px 0 calc(52px + env(safe-area-inset-bottom,0px)); z-index:105; width:auto; height:auto; }
}
</style>
