<template>
  <nav class="course-mode-tabs" :aria-label="t('unifiedCourseWorkspace.modeNavigation', '课程工作模式')">
    <button
      v-for="item in modes"
      :key="item.key"
      type="button"
      :class="{ 'is-active': active === item.key }"
      :aria-current="active === item.key ? 'page' : undefined"
      :data-testid="`course-mode-${item.key}`"
      @click="openMode(item.key)"
    >
      <component :is="item.icon" :size="17" />
      <span>
        <strong>{{ item.label }}</strong>
        <small>{{ item.help }}</small>
      </span>
    </button>
  </nav>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Settings2, Sparkles, Presentation } from 'lucide-vue-next'
import { useRouter } from 'vue-router'
import { t } from '../shared/i18n'

export type CourseMode = 'setup' | 'build' | 'formal'

const props = defineProps<{ active: CourseMode; courseId: string }>()
const router = useRouter()
const modes = computed(() => [
  {
    key: 'setup' as const,
    icon: Settings2,
    label: t('unifiedCourseWorkspace.modes.setup', '课程设置'),
    help: t('unifiedCourseWorkspace.modes.setupHelp', '信息、资料与排课'),
  },
  {
    key: 'build' as const,
    icon: Sparkles,
    label: t('unifiedCourseWorkspace.modes.build', '备课制作'),
    help: t('unifiedCourseWorkspace.modes.buildHelp', '大纲、讲次与课件'),
  },
  {
    key: 'formal' as const,
    icon: Presentation,
    label: t('unifiedCourseWorkspace.modes.formal', '正式课程'),
    help: t('unifiedCourseWorkspace.modes.formalHelp', '上课与学习现场'),
  },
])

function openMode(mode: CourseMode) {
  if (mode === props.active) return
  if (mode === 'formal') {
    void router.push({ name: 'learning', params: { courseId: props.courseId } })
    return
  }
  void router.push({
    name: 'course-workspace',
    params: { courseId: props.courseId, mode },
    query: { section: mode === 'setup' ? 'basic' : 'outline' },
  })
}
</script>

<style scoped>
.course-mode-tabs {
  width: min(720px, 100%);
  min-width: 0;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 4px;
  padding: 4px;
  border: 1px solid var(--lz-border);
  border-radius: 13px;
  background: var(--lz-fill);
}
.course-mode-tabs button {
  min-width: 0;
  min-height: 46px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 9px;
  padding: 5px 12px;
  border: 1px solid transparent;
  border-radius: 9px;
  color: var(--lz-text-secondary);
  background: transparent;
  cursor: pointer;
  transition: color .16s ease, background .16s ease, border-color .16s ease, box-shadow .16s ease;
}
.course-mode-tabs button:hover {
  color: var(--lz-brand-strong);
  background: rgba(255, 255, 255, .72);
}
.course-mode-tabs button:focus-visible {
  outline: 3px solid rgba(99, 102, 241, .24);
  outline-offset: 2px;
}
.course-mode-tabs button.is-active {
  color: var(--lz-brand-strong);
  border-color: var(--lz-brand-border);
  background: var(--lz-surface);
  box-shadow: 0 3px 10px rgba(79, 70, 229, .1);
}
.course-mode-tabs button > svg { flex: 0 0 auto; }
.course-mode-tabs button > span { min-width: 0; display: grid; gap: 2px; text-align: left; }
.course-mode-tabs strong,
.course-mode-tabs small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.course-mode-tabs strong { font-size: 12px; }
.course-mode-tabs small { color: var(--lz-text-muted); font-size: 9px; font-weight: 500; }
.course-mode-tabs button.is-active small { color: #6366a8; }
@media (max-width: 767px) {
  .course-mode-tabs { width: 100%; gap: 2px; padding: 3px; border-radius: 10px; }
  .course-mode-tabs button { min-height: 38px; gap: 4px; padding: 3px 4px; }
  .course-mode-tabs button > svg,
  .course-mode-tabs small { display: none; }
  .course-mode-tabs strong { font-size: 11px; }
}
@media (prefers-reduced-motion: reduce) {
  .course-mode-tabs button { transition: none; }
}
</style>
