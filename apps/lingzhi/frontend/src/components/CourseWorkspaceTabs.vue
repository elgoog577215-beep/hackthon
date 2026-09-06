<template>
  <nav
    class="course-workspace-tabs"
    :class="{ 'is-two': !showLessonPlan }"
    role="tablist"
    :aria-label="t('courseWorkspaceTabs.navigation', '课程工作区')"
  >
    <button
      v-if="showLessonPlan"
      type="button"
      role="tab"
      data-workspace-item="lesson-plan"
      :class="{ 'is-active': activeItem === 'lesson-plan', 'is-building': lessonPlanBuilding }"
      :aria-selected="activeItem === 'lesson-plan'"
      :disabled="lessonPlanPending"
      :title="lessonPlanPending
        ? t('courseWorkspaceTabs.lessonPlanPending', '课程目录确认后生成全课教案')
        : lessonPlanBuilding
          ? t('courseWorkspaceTabs.lessonPlanBuilding', '教案正在后台形成，可随时查看')
        : t('courseWorkspaceTabs.lessonPlanHint', '查看当前课程的教案')"
      @click="emit('lesson-plan')"
    >
      <LoaderCircle v-if="lessonPlanBuilding" :size="16" />
      <ClipboardList v-else :size="16" />
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
      data-workspace-item="ppt"
      :class="{ 'is-active': activeItem === 'ppt' }"
      :aria-selected="activeItem === 'ppt'"
      :disabled="!pptAvailable"
      :title="pptAvailable
        ? t('courseWorkspaceTabs.pptHint', '打开当前课程的 PPT 工作台')
        : t('courseWorkspaceTabs.pptPending', '课程发布后开放 PPT 工作台')"
      @click="emit('ppt')"
    >
      <Presentation :size="16" />
      <span>{{ t('courseWorkspaceTabs.ppt', 'PPT') }}</span>
    </button>
  </nav>
</template>

<script setup lang="ts">
import { BookOpenText, ClipboardList, LoaderCircle, Presentation } from 'lucide-vue-next'
import { t } from '../shared/i18n'

export type CourseWorkspaceItem = 'lesson-plan' | 'course' | 'ppt'

withDefaults(defineProps<{
  activeItem: CourseWorkspaceItem
  lessonPlanPending?: boolean
  lessonPlanBuilding?: boolean
  pptAvailable?: boolean
  showLessonPlan?: boolean
}>(), {
  lessonPlanPending: false,
  lessonPlanBuilding: false,
  pptAvailable: true,
  showLessonPlan: true,
})

const emit = defineEmits<{
  (event: 'lesson-plan' | 'course' | 'ppt'): void
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
.course-workspace-tabs button.is-building:not(:disabled) svg {
  color:#5b61cf;
  animation:workspace-tab-spin .9s linear infinite;
}
@keyframes workspace-tab-spin { to { transform:rotate(360deg); } }
@media (max-width:767px) {
  .course-workspace-tabs {
    width:100%;
    min-height:40px;
    display:grid;
    grid-template-columns:repeat(3,minmax(0,1fr));
    gap:2px;
    padding:3px;
    border-radius:10px;
  }
  .course-workspace-tabs.is-two { grid-template-columns:repeat(2,minmax(0,1fr)); }
  .course-workspace-tabs button {
    width:100%;
    min-width:0;
    min-height:32px;
    gap:3px;
    padding:0 3px;
    font-size:10px;
    overflow:hidden;
  }
  .course-workspace-tabs button svg { display:none; }
  .course-workspace-tabs button span { overflow:hidden; text-overflow:ellipsis; }
}
@media (prefers-reduced-motion:reduce) {
  .course-workspace-tabs button { transition:none; }
  .course-workspace-tabs button svg { animation:none!important; }
}
</style>
