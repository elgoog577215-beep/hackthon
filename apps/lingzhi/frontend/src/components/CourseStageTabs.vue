<template>
  <nav class="course-stage-tabs" :aria-label="t('unifiedCourseWorkspace.stageNavigation', '课程制作流程')">
    <ol>
      <li v-for="(item, index) in stages" :key="item.key">
        <button
          type="button"
          :class="{ 'is-active': active === item.key }"
          :aria-current="active === item.key ? 'step' : undefined"
          :data-testid="`course-stage-${item.key}`"
          @click="openStage(item.key)"
        >
          <span class="stage-index" aria-hidden="true">{{ index + 1 }}</span>
          <strong>{{ item.label }}</strong>
        </button>
      </li>
    </ol>
  </nav>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { t } from '../shared/i18n'

export type CourseStage = 'course' | 'outline' | 'content' | 'ppt'

const props = defineProps<{ active: CourseStage; courseId: string }>()
const route = useRoute()
const router = useRouter()

const stages = computed(() => [
  { key: 'course' as const, label: t('unifiedCourseWorkspace.stages.course', '课程') },
  { key: 'outline' as const, label: t('unifiedCourseWorkspace.stages.outline', '大纲') },
  { key: 'content' as const, label: t('unifiedCourseWorkspace.stages.content', '正文') },
  { key: 'ppt' as const, label: 'PPT' },
])

function openStage(stage: CourseStage) {
  if (stage === props.active) return
  if (stage === 'course') {
    void router.push({
      name: 'course-workspace',
      params: { courseId: props.courseId, mode: 'setup' },
      query: { section: 'basic' },
    })
    return
  }
  if (stage === 'outline') {
    void router.push({
      name: 'course-workspace',
      params: { courseId: props.courseId, mode: 'build' },
      query: { section: 'outline' },
    })
    return
  }
  if (stage === 'content') {
    void router.push({ name: 'learning', params: { courseId: props.courseId } })
    return
  }
  void router.push({
    name: 'ppt-workspace',
    params: { courseId: props.courseId },
    query: route.name === 'ppt-workspace' ? undefined : { returnTo: route.fullPath },
  })
}
</script>

<style scoped>
.course-stage-tabs {
  width: min(660px, 100%);
  min-width: 0;
}
.course-stage-tabs ol {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  align-items: center;
  margin: 0;
  padding: 0;
  list-style: none;
}
.course-stage-tabs li {
  position: relative;
  min-width: 0;
}
.course-stage-tabs li:not(:last-child)::after {
  content: "";
  position: absolute;
  z-index: 0;
  top: 50%;
  right: -10%;
  width: 20%;
  height: 1px;
  background: var(--lz-border);
}
.course-stage-tabs button {
  position: relative;
  z-index: 1;
  width: 100%;
  min-height: 42px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 4px 12px;
  border: 0;
  border-radius: 10px;
  color: var(--lz-text-muted);
  background: transparent;
  cursor: pointer;
  transition: color .16s ease, background .16s ease;
}
.course-stage-tabs button:hover {
  color: var(--lz-text-strong);
  background: var(--lz-fill);
}
.course-stage-tabs button:focus-visible {
  outline: 3px solid rgba(99, 102, 241, .24);
  outline-offset: 2px;
}
.course-stage-tabs button.is-active {
  color: var(--lz-brand-strong);
  background: var(--lz-brand-soft);
}
.stage-index {
  width: 22px;
  height: 22px;
  flex: 0 0 22px;
  display: grid;
  place-items: center;
  border: 1px solid var(--lz-border);
  border-radius: 50%;
  color: var(--lz-text-muted);
  background: var(--lz-surface);
  font-size: 10px;
  font-weight: 800;
}
.course-stage-tabs button.is-active .stage-index {
  border-color: var(--lz-brand);
  color: #fff;
  background: var(--lz-brand);
}
.course-stage-tabs strong {
  min-width: 0;
  overflow: hidden;
  font-size: 12px;
  font-weight: 750;
  text-overflow: ellipsis;
  white-space: nowrap;
}
@media (max-width: 600px) {
  .course-stage-tabs button {
    min-height: 38px;
    gap: 5px;
    padding: 3px 4px;
    border-radius: 8px;
  }
  .stage-index { width: 20px; height: 20px; flex-basis: 20px; font-size: 9px; }
  .course-stage-tabs strong { font-size: 11px; }
  .course-stage-tabs li:not(:last-child)::after { display: none; }
}
@media (prefers-reduced-motion: reduce) {
  .course-stage-tabs button { transition: none; }
}
</style>
