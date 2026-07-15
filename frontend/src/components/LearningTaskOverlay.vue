<template>
  <MorphingDialog
    ref="dialogRef"
    :ariaLabel="t('taskOverlay.title', '学习任务')"
    :origin-rect="originRect"
    size="large"
    @close="emit('close')"
  >
    <section class="task-overlay">
      <header>
        <div>
          <span>{{ t('taskOverlay.eyebrow', '当前课程任务') }}</span>
          <strong>{{ nodeLabel || t('taskOverlay.title', '学习任务') }}</strong>
        </div>
        <button
          type="button"
          :title="t('taskOverlay.close', '关闭并返回正文')"
          :aria-label="t('taskOverlay.close', '关闭并返回正文')"
          @click="closeDialog"
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
  </MorphingDialog>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { X } from 'lucide-vue-next'
import MorphingDialog from './MorphingDialog.vue'
import PracticeWorkspace from './PracticeWorkspace.vue'
import { t } from '../shared/i18n'

defineProps<{
  courseId: string
  nodeId?: string
  nodeLabel?: string
  originRect?: { top: number; left: number; width: number; height: number } | null
}>()
const emit = defineEmits<{
  (event: 'close' | 'graded'): void
  (event: 'askTeacher', payload: { text: string; nodeId: string }): void
}>()
const dialogRef = ref<InstanceType<typeof MorphingDialog> | null>(null)

function closeDialog() {
  void dialogRef.value?.close()
}
</script>

<style scoped>
.task-overlay { width:100%; height:100%; min-width:0; min-height:0; display:grid; grid-template-rows:60px minmax(0,1fr); background:#fff; }
.task-overlay > header { display:flex; align-items:center; justify-content:space-between; gap:12px; padding:0 18px 0 22px; border-bottom:1px solid var(--lz-border); background:rgba(255,255,255,.96); }
.task-overlay header div { min-width: 0; display: flex; flex-direction: column; }
.task-overlay header span { color: var(--lz-text-muted); font-size: 10px; }
.task-overlay header strong { margin-top:3px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:var(--lz-text-strong); font-size:14px; }
.task-overlay header button { width:34px; height:34px; display:grid; place-items:center; border:0; border-radius:8px; color:var(--lz-text-secondary); background:transparent; cursor:pointer; }
.task-overlay header button:hover { color: var(--lz-text-strong); background: var(--lz-surface-muted); }
.task-overlay header button:focus-visible { outline:2px solid var(--lz-brand); outline-offset:2px; }
.task-workspace { min-height: 0; }
@media (max-width:767px) {
  .task-overlay { grid-template-rows:calc(58px + env(safe-area-inset-top, 0px)) minmax(0,1fr); }
  .task-overlay > header { padding-top:env(safe-area-inset-top,0px); padding-inline:16px 12px; }
}
</style>
