<template>
  <nav
    class="course-workspace-tabs"
    role="tablist"
    :aria-label="t('courseWorkspaceTabs.navigation', '课程工作区')"
  >
    <button
      type="button"
      role="tab"
      data-workspace-item="lesson-plan"
      :class="{ 'is-active': activeItem === 'lesson-plan' }"
      :aria-selected="activeItem === 'lesson-plan'"
      :title="t('courseWorkspaceTabs.lessonPlanHint', '查看当前课程的教案')"
      @click="emit('lesson-plan')"
    >
      <ClipboardList :size="16" />
      <span>{{ t('courseWorkspaceTabs.lessonPlan', '教案') }}</span>
    </button>
    <button
      type="button"
      role="tab"
      data-workspace-item="course"
      :class="{ 'is-active': activeItem === 'course' }"
      :aria-selected="activeItem === 'course'"
      :title="t('courseWorkspaceTabs.courseHint', '返回课程正文')"
      @click="emit('course')"
    >
      <BookOpenText :size="16" />
      <span>{{ t('courseWorkspaceTabs.course', '课程') }}</span>
    </button>
    <button
      type="button"
      role="tab"
      data-workspace-item="practice"
      :class="{ 'is-active': activeItem === 'practice' }"
      :aria-selected="activeItem === 'practice'"
      :disabled="!practiceEntryAvailable"
      :title="practiceRepairAvailable
        ? t('courseWorkspaceTabs.practiceRepairHint', '打开练习并重新生成旧版题目')
        : practiceAvailable
          ? t('courseWorkspaceTabs.practiceHint', '打开当前章节的正式练习')
          : practicePending
            ? t('courseWorkspaceTabs.practicePending', '课程发布后开放正式练习')
            : t('courseWorkspaceTabs.practiceUnavailable', '当前章节暂时没有正式练习')"
      @click="emit('practice')"
    >
      <ClipboardCheck :size="16" />
      <span>{{ t('courseWorkspaceTabs.practice', '练习') }}</span>
    </button>
  </nav>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { BookOpenText, ClipboardCheck, ClipboardList } from 'lucide-vue-next'
import { t } from '../shared/i18n'

export type CourseWorkspaceItem = 'lesson-plan' | 'course' | 'practice'

const props = withDefaults(defineProps<{
  activeItem: CourseWorkspaceItem
  practiceAvailable?: boolean
  practiceRepairAvailable?: boolean
  practicePending?: boolean
}>(), {
  practiceAvailable: false,
  practiceRepairAvailable: false,
  practicePending: false,
})

const practiceEntryAvailable = computed(() => (
  props.practiceAvailable || props.practiceRepairAvailable
))

const emit = defineEmits<{
  (event: 'lesson-plan' | 'course' | 'practice'): void
}>()
</script>

<style scoped>
.course-workspace-tabs {
  min-width:0;
  min-height:42px;
  display:flex;
  align-items:center;
  justify-content:center;
  gap:4px;
  padding:4px;
  border:1px solid #e1e5f1;
  border-radius:12px;
  background:#f7f8fc;
}
.course-workspace-tabs button {
  min-width:78px;
  min-height:34px;
  display:inline-flex;
  align-items:center;
  justify-content:center;
  gap:7px;
  padding:0 13px;
  border:1px solid transparent;
  border-radius:9px;
  color:var(--lz-text-secondary);
  background:transparent;
  font-size:11px;
  font-weight:700;
  white-space:nowrap;
  cursor:pointer;
  transition:color .16s ease,background .16s ease,border-color .16s ease,box-shadow .16s ease;
}
.course-workspace-tabs button:hover:not(:disabled) {
  color:var(--lz-brand-strong);
  border-color:#e0e4ff;
  background:#fff;
}
.course-workspace-tabs button:focus-visible {
  outline:3px solid rgba(99,102,241,.24);
  outline-offset:2px;
}
.course-workspace-tabs button.is-active {
  color:var(--lz-brand-strong);
  border-color:#d8ddff;
  background:#fff;
  box-shadow:0 3px 10px rgba(79,70,229,.1);
}
.course-workspace-tabs button:disabled {
  color:#b4bdcc;
  cursor:not-allowed;
}
@media (max-width:767px) {
  .course-workspace-tabs {
    width:100%;
    min-height:40px;
    justify-content:flex-start;
    overflow-x:auto;
    padding:3px;
    border-radius:10px;
    scrollbar-width:none;
  }
  .course-workspace-tabs::-webkit-scrollbar { display:none; }
  .course-workspace-tabs button {
    min-width:70px;
    min-height:32px;
    flex:1 0 auto;
    padding:0 10px;
    font-size:10px;
  }
}
@media (prefers-reduced-motion:reduce) {
  .course-workspace-tabs button { transition:none; }
}
</style>
