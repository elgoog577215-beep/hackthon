<template>
  <nav class="hierarchy-stepper" aria-label="资源层级导航">
    <template v-for="(step, idx) in steps" :key="step.key">
      <span v-if="idx > 0" class="step-arrow" aria-hidden="true">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
          <path d="M9 18l6-6-6-6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      </span>
      <component
        :is="step.to && step.state === 'done' ? 'button' : 'span'"
        class="step-chip"
        :class="`is-${step.state}`"
        type="button"
        @click="step.to && step.state === 'done' ? $router.push(step.to) : undefined"
      >
        <span class="step-index">{{ idx + 1 }}</span>
        <span class="step-texts">
          <span class="step-label">{{ step.label }}</span>
          <span v-if="step.name" class="step-name" :title="step.name">{{ step.name }}</span>
        </span>
      </component>
    </template>
  </nav>
</template>

<script setup lang="ts">
import { computed } from 'vue'

export type HierarchyLevel = 'course' | 'outline' | 'plan' | 'ppt'

const props = defineProps<{
  /** 当前所处层级 */
  current: HierarchyLevel
  courseId: string
  courseName?: string
  outlineId?: string
  outlineName?: string
  planId?: string
  planName?: string
  pptName?: string
}>()

type StepState = 'done' | 'current' | 'todo'

const LEVEL_ORDER: HierarchyLevel[] = ['course', 'outline', 'plan', 'ppt']

function stateOf(level: HierarchyLevel): StepState {
  const cur = LEVEL_ORDER.indexOf(props.current)
  const idx = LEVEL_ORDER.indexOf(level)
  if (idx < cur) return 'done'
  if (idx === cur) return 'current'
  return 'todo'
}

const steps = computed(() => [
  {
    key: 'course',
    label: '课程',
    name: props.courseName,
    state: stateOf('course'),
    to: `/course/${props.courseId}`,
  },
  {
    key: 'outline',
    label: '大纲',
    name: props.outlineName,
    state: stateOf('outline'),
    to: props.outlineId ? `/course/${props.courseId}/outline/${props.outlineId}` : undefined,
  },
  {
    key: 'plan',
    label: '教案',
    name: props.planName,
    state: stateOf('plan'),
    to:
      props.outlineId && props.planId
        ? `/course/${props.courseId}/outline/${props.outlineId}/plan/${props.planId}`
        : undefined,
  },
  {
    key: 'ppt',
    label: '课件',
    name: props.pptName,
    state: stateOf('ppt'),
    to: undefined,
  },
])
</script>

<style scoped>
.hierarchy-stepper {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.step-arrow {
  display: inline-flex;
  align-items: center;
  color: #c2c8d4;
}

.step-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 5px 12px 5px 6px;
  border-radius: 999px;
  border: 1px solid #e3e7ef;
  background: #fff;
  font: inherit;
  text-align: left;
  color: #9aa3b2;
}

.step-chip.is-done {
  color: #4b5563;
  cursor: pointer;
}

.step-chip.is-done:hover {
  border-color: #3b82f6;
  color: #3b82f6;
}

.step-chip.is-current {
  border-color: #3b82f6;
  background: #eff6ff;
  color: #1d4ed8;
}

.step-index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #f1f3f8;
  font-size: 12px;
  font-weight: 600;
  flex: none;
}

.step-chip.is-current .step-index {
  background: #3b82f6;
  color: #fff;
}

.step-chip.is-done .step-index {
  background: #e0e7ff;
  color: #4f46e5;
}

.step-texts {
  display: inline-flex;
  align-items: baseline;
  gap: 6px;
  min-width: 0;
}

.step-label {
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
}

.step-name {
  font-size: 12px;
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  opacity: 0.85;
}
</style>
