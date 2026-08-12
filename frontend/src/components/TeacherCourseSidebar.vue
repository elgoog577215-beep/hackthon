<template>
  <aside class="teacher-course-sidebar" aria-label="课程功能">
    <div class="course-identity">
      <span>{{ title.slice(0, 1) }}</span>
      <div><strong>{{ title }}</strong><small>{{ meta }}</small></div>
    </div>
    <nav>
      <button type="button" :title="t('teacherWorkbench.nav.overview', '课程概览')" :class="{ active: active === 'overview' }" @click="open('teacher-course-overview')">
        <LayoutGrid :size="17" /><span class="nav-label">{{ t('teacherWorkbench.nav.overview', '课程概览') }}</span>
      </button>
      <button type="button" :title="t('teacherWorkbench.nav.outline', '教学大纲')" :class="{ active: active === 'outline' }" @click="open('teacher-course-outline')">
        <BookOpenText :size="17" /><span class="nav-label">{{ t('teacherWorkbench.nav.outline', '教学大纲') }}</span>
      </button>
      <button type="button" :title="t('teacherWorkbench.nav.calendar', '教学日历')" :class="{ active: active === 'calendar' }" @click="open('teacher-course-calendar')">
        <CalendarDays :size="17" /><span class="nav-label">{{ t('teacherWorkbench.nav.calendar', '教学日历') }}</span>
      </button>
      <button type="button" :title="t('teacherWorkbench.nav.production', '课程生产')" :class="{ active: active === 'production' }" @click="open('teacher-course-production')">
        <Workflow :size="17" /><span class="nav-label">{{ t('teacherWorkbench.nav.production', '课程生产') }}</span><span v-if="attentionCount" class="attention-count">{{ attentionCount }}</span>
      </button>
      <button type="button" :title="t('teacherWorkbench.nav.files', '课程文件')" :class="{ active: active === 'files' }" @click="open('teacher-course-files')">
        <FolderOpen :size="17" /><span class="nav-label">{{ t('teacherWorkbench.nav.files', '课程文件') }}</span>
      </button>
      <button type="button" :title="t('teacherWorkbench.nav.release', '发布管理')" :class="{ active: active === 'release' }" @click="open('teacher-course-release')">
        <FileCheck2 :size="17" /><span class="nav-label">{{ t('teacherWorkbench.nav.release', '发布管理') }}</span>
      </button>
    </nav>
    <button type="button" class="back-library" @click="router.push('/courses')">
      <ArrowLeft :size="16" />{{ t('teacherWorkbench.backToWorkspace', '返回课程工作台') }}
    </button>
  </aside>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { ArrowLeft, BookOpenText, CalendarDays, FileCheck2, FolderOpen, LayoutGrid, Workflow } from 'lucide-vue-next'
import { t } from '../shared/i18n'

const props = defineProps<{
  courseId: string
  title: string
  meta: string
  active: 'overview' | 'outline' | 'calendar' | 'production' | 'files' | 'release'
  attentionCount?: number
}>()

const router = useRouter()
function open(name: string) {
  void router.push({ name, params: { courseId: props.courseId } })
}
</script>

<style scoped>
.teacher-course-sidebar { min-height:0; display:flex; flex-direction:column; border-right:1px solid var(--lz-border); background:var(--lz-surface); }
.course-identity { min-height:66px; display:flex; align-items:center; gap:10px; padding:0 15px; border-bottom:1px solid var(--lz-border); }
.course-identity > span { width:34px; height:34px; display:grid; place-items:center; border-radius:9px; color:var(--lz-brand-strong); background:var(--lz-brand-soft); font-weight:800; }
.course-identity div { min-width:0; display:grid; }
.course-identity strong,.course-identity small { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.course-identity strong { font-size:12px; }
.course-identity small { margin-top:3px; color:var(--lz-text-muted); font-size:10px; }
nav { display:grid; gap:4px; padding:12px 8px; }
nav button { height:38px; display:grid; grid-template-columns:22px minmax(0,1fr) auto; align-items:center; gap:7px; padding:0 10px; border:0; border-radius:8px; color:var(--lz-text-secondary); background:transparent; text-align:left; cursor:pointer; }
nav button.active { color:var(--lz-brand-strong); background:var(--lz-brand-soft); font-weight:700; }
nav button .nav-label { min-width:0; padding:0; overflow:hidden; border-radius:0; color:inherit; background:transparent; font-size:inherit; text-align:left; text-overflow:ellipsis; white-space:nowrap; }
nav button .attention-count { min-width:19px; padding:2px 5px; border-radius:9px; background:var(--lz-surface); color:var(--lz-brand-strong); font-size:9px; text-align:center; }
.back-library { margin-top:auto; height:42px; display:flex; align-items:center; gap:7px; padding:0 18px; border:0; border-top:1px solid var(--lz-border); color:var(--lz-text-muted); background:transparent; cursor:pointer; }
@media (max-width:900px) {
  .course-identity div,nav .nav-label,.back-library { display:none; }
  .course-identity { justify-content:center; padding:0; }
  nav button { grid-template-columns:1fr; justify-items:center; padding:0; }
  nav button.active { grid-template-columns:1fr; }
  nav button .attention-count { display:none; }
}
@media (max-width:680px) {
  .teacher-course-sidebar { min-height:auto; border-right:0; border-bottom:1px solid var(--lz-border); }
  .course-identity { display:none; }
  nav { display:flex; gap:4px; overflow-x:auto; padding:6px 8px; }
  nav button,nav button.active { flex:0 0 auto; width:auto; height:34px; display:inline-flex; grid-template-columns:none; justify-items:initial; gap:6px; padding:0 10px; white-space:nowrap; }
  nav .nav-label { display:inline; }
  nav button .attention-count { display:inline-block; }
}
</style>
