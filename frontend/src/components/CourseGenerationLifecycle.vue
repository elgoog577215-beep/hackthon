<template>
  <nav class="generation-lifecycle" :aria-label="t('courseGeneration.lifecycle.label', '课程生产进度')">
    <div class="generation-lifecycle__inner">
      <div class="generation-lifecycle__summary" :data-status="currentStatus">
        <span>
          <TriangleAlert v-if="currentStatus === 'error' || currentStatus === 'blocked'" :size="14" />
          <CirclePause v-else-if="currentStatus === 'paused'" :size="14" />
          <Clock3 v-else-if="currentStatus === 'review'" :size="14" />
          <LoaderCircle v-else-if="currentStatus === 'active'" :size="14" />
          <Check v-else :size="14" />
        </span>
        <div>
          <small>{{ t('courseGeneration.workspace.label', '课程生产') }}</small>
          <strong>{{ activeIndex + 1 }} / {{ stages.length }}</strong>
        </div>
      </div>

      <ol>
        <li
          v-for="(stage, index) in stages"
          :key="stage.key"
          :data-status="stageStatus(index)"
          :aria-current="index === activeIndex ? 'step' : undefined"
          :aria-label="`${stage.label}：${stageStatusLabel(index)}`"
        >
          <span class="generation-lifecycle__marker">
            <Check v-if="stageStatus(index) === 'completed'" :size="11" />
            <TriangleAlert v-else-if="stageStatus(index) === 'error' || stageStatus(index) === 'blocked'" :size="11" />
            <CirclePause v-else-if="stageStatus(index) === 'paused'" :size="11" />
            <Clock3 v-else-if="stageStatus(index) === 'review'" :size="11" />
            <LoaderCircle v-else-if="stageStatus(index) === 'active'" :size="11" />
            <span v-else>{{ index + 1 }}</span>
          </span>
          <strong>{{ stage.label }}</strong>
        </li>
      </ol>

      <span class="generation-lifecycle__value" :data-status="currentStatus">{{ currentValue }}</span>
    </div>
    <div class="generation-lifecycle__track" aria-hidden="true">
      <i :style="{ width: `${progressValue}%` }"></i>
    </div>
  </nav>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Check, CirclePause, Clock3, LoaderCircle, TriangleAlert } from 'lucide-vue-next'
import type { Task } from '../stores/types'
import { t } from '../shared/i18n'
import { courseProductionStageIndex, courseProductionStageStatus } from '../utils/course-production'

const props = withDefaults(defineProps<{
  task?: Task
}>(), {
  task: undefined,
})

const isProjectCourse = computed(() => props.task?.courseType === 'project')
const stages = computed(() => [
  {
    key: 'outline',
    backendIndex: 1,
    label: isProjectCourse.value
      ? t('courseGeneration.lifecycle.projectOutline', '个人路径')
      : t('courseGeneration.lifecycle.outline', '目录确认'),
  },
  {
    key: 'teaching',
    backendIndex: 2,
    label: isProjectCourse.value
      ? t('courseGeneration.lifecycle.projectTeaching', '能力与知识')
      : t('courseGeneration.lifecycle.teaching', '教案确认'),
  },
  {
    key: 'content',
    backendIndex: 3,
    label: isProjectCourse.value
      ? t('courseGeneration.lifecycle.projectContent', '项目课程')
      : t('courseGeneration.lifecycle.content', '正文生成'),
  },
  {
    key: 'release',
    backendIndex: 4,
    label: isProjectCourse.value
      ? t('courseGeneration.lifecycle.projectRelease', '确认课程')
      : t('courseGeneration.lifecycle.release', '确认发布'),
  },
])
const backendStageIndex = computed(() => courseProductionStageIndex(props.task))
const activeIndex = computed(() => Math.max(0, Math.min(stages.value.length - 1, backendStageIndex.value - 1)))
const currentStatus = computed(() => stageStatus(activeIndex.value))
const progressValue = computed(() => Math.max(0, Math.min(100, Math.round(Number(props.task?.progress || 0)))))
const currentValue = computed(() => (
  currentStatus.value === 'active' || currentStatus.value === 'completed'
    ? liveCount.value || `${progressValue.value}%`
    : stageStatusLabel(activeIndex.value)
))

const liveCount = computed(() => {
  const checkpoint = props.task?.recovery?.checkpoint
  const detail = props.task?.phaseDetail || {}
  if (activeIndex.value === 1) {
    const completed = Number(checkpoint?.completed_teaching_plan_sections ?? detail.completed_items ?? 0)
    const total = Number(checkpoint?.total_teaching_plan_sections ?? detail.total_items ?? 0)
    return total ? `${completed}/${total}` : ''
  }
  if (activeIndex.value === 2) {
    const completed = Number(props.task?.completedNodes ?? checkpoint?.completed_nodes ?? detail.completed_items ?? 0)
    const total = Number(props.task?.totalNodes ?? checkpoint?.total_nodes ?? detail.total_items ?? 0)
    return total ? `${completed}/${total}` : ''
  }
  return ''
})

function stageStatus(index: number) {
  return courseProductionStageStatus(props.task, stages.value[index]?.backendIndex ?? index)
}

function stageStatusLabel(index: number) {
  const status = stageStatus(index)
  if (status === 'completed') return t('courseGeneration.lifecycle.completed', '已完成')
  if (status === 'error') return t('courseGeneration.lifecycle.interrupted', '已中断')
  if (status === 'paused') return t('courseGeneration.lifecycle.paused', '已暂停')
  if (status === 'blocked') return t('courseGeneration.lifecycle.blocked', '需处理')
  if (status === 'review') return t('courseGeneration.lifecycle.needsConfirmation', '待确认')
  if (status === 'active') return t('courseGeneration.lifecycle.inProgress', '进行中')
  return t('courseGeneration.lifecycle.pending', '未开始')
}
</script>

<style scoped>
.generation-lifecycle {
  flex:0 0 auto;
  padding:9px clamp(18px,2.4vw,32px) 0;
  border-bottom:1px solid #e6e9f0;
  background:#fff;
}
.generation-lifecycle__inner {
  display:grid;
  grid-template-columns:88px minmax(520px,1fr) 54px;
  align-items:center;
  gap:16px;
}
.generation-lifecycle__summary {
  min-width:0;
  display:flex;
  align-items:center;
  gap:8px;
}
.generation-lifecycle__summary > span {
  width:28px;
  height:28px;
  flex:0 0 28px;
  display:grid;
  place-items:center;
  border:1px solid #d7dce5;
  border-radius:8px;
  color:#596579;
  background:#f8f9fb;
}
.generation-lifecycle__summary > div {
  min-width:0;
  display:flex;
  flex-direction:column;
}
.generation-lifecycle__summary small {
  color:#9aa1ae;
  font-size:9px;
  font-weight:800;
  letter-spacing:.08em;
}
.generation-lifecycle__summary strong {
  overflow:hidden;
  color:#354052;
  font:750 11px/1.35 ui-monospace,SFMono-Regular,monospace;
  line-height:1.35;
  text-overflow:ellipsis;
  white-space:nowrap;
}
.generation-lifecycle__summary[data-status="active"] > span {
  border-color:#caccef;
  color:#4f55b5;
  background:#f3f3ff;
}
.generation-lifecycle__summary[data-status="review"] > span,
.generation-lifecycle__summary[data-status="completed"] > span {
  border-color:#b9dccc;
  color:#087a5b;
  background:#eff9f5;
}
.generation-lifecycle__summary[data-status="error"] > span,
.generation-lifecycle__summary[data-status="blocked"] > span {
  border-color:#e8c38d;
  color:#b05a18;
  background:#fff8ed;
}
.generation-lifecycle__summary[data-status="paused"] > span {
  border-color:#d0d5dd;
  color:#667085;
  background:#f2f4f7;
}
.generation-lifecycle ol {
  width:100%;
  display:grid;
  grid-template-columns:repeat(4,minmax(0,1fr));
  margin:0;
  padding:0;
  list-style:none;
}
.generation-lifecycle li {
  position:relative;
  min-width:0;
  display:grid;
  grid-template-columns:22px minmax(0,1fr);
  align-items:center;
  gap:5px;
}
.generation-lifecycle li:not(:last-child)::after {
  content:"";
  position:absolute;
  z-index:0;
  top:10px;
  left:21px;
  right:1px;
  height:1px;
  background:#dfe3eb;
}
.generation-lifecycle li[data-status="completed"]:not(:last-child)::after {
  background:#9bcdbb;
}
.generation-lifecycle__marker {
  position:relative;
  z-index:1;
  width:22px;
  height:22px;
  display:grid;
  place-items:center;
  border:1px solid #d5dbe5;
  border-radius:50%;
  color:#98a2b3;
  background:#fff;
  font-size:10px;
  font-weight:800;
}
.generation-lifecycle strong {
  position:relative;
  z-index:1;
  width:max-content;
  max-width:calc(100% - 6px);
  overflow:hidden;
  color:#8a93a4;
  background:#fff;
  font-size:11px;
  line-height:1.35;
  text-overflow:ellipsis;
  white-space:nowrap;
}
li[data-status="completed"] .generation-lifecycle__marker {
  border-color:#86c6ae;
  color:#087a5b;
  background:#f0faf6;
}
li[data-status="active"] .generation-lifecycle__marker {
  border-color:#7775e6;
  color:#4f46e5;
  background:#f2f2ff;
}
li[data-status="review"] .generation-lifecycle__marker {
  border-color:#76c9ad;
  color:#087a5b;
  background:#ecfdf5;
}
li[data-status="error"] .generation-lifecycle__marker,
li[data-status="blocked"] .generation-lifecycle__marker {
  border-color:#e7a750;
  color:#b54708;
  background:#fff8ed;
}
li[data-status="paused"] .generation-lifecycle__marker {
  border-color:#c3c9d4;
  color:#667085;
  background:#f2f4f7;
}
li[data-status="active"] .generation-lifecycle__marker svg {
  animation:lifecycle-spin .9s linear infinite;
}
.generation-lifecycle__summary[data-status="active"] > span svg {
  animation:lifecycle-spin .9s linear infinite;
}
li[data-status="active"] strong,
li[data-status="review"] strong {
  color:#344054;
}
li[data-status="error"] strong,
li[data-status="blocked"] strong {
  color:#9a4d13;
}
.generation-lifecycle__value {
  justify-self:end;
  color:#4f55b5;
  font:750 12px/1 ui-monospace,SFMono-Regular,monospace;
  white-space:nowrap;
}
.generation-lifecycle__value[data-status="review"],
.generation-lifecycle__value[data-status="completed"] { color:#087a5b; }
.generation-lifecycle__value[data-status="error"],
.generation-lifecycle__value[data-status="blocked"] { color:#b05a18; }
.generation-lifecycle__value[data-status="paused"] { color:#667085; }
.generation-lifecycle__track {
  height:2px;
  margin:8px calc(-1 * clamp(18px,2.4vw,32px)) 0;
  overflow:hidden;
  background:#edf0f4;
}
.generation-lifecycle__track i {
  display:block;
  height:100%;
  border-radius:0 999px 999px 0;
  background:linear-gradient(90deg,#5662d7,#855ee3);
  transition:width .3s ease;
}
@keyframes lifecycle-spin {
  to { transform:rotate(360deg); }
}
@media (max-width:1050px) {
  .generation-lifecycle__inner {
    grid-template-columns:76px minmax(0,1fr) 44px;
    gap:10px;
  }
  .generation-lifecycle strong { font-size:11px; }
}
@media (max-width:767px) {
  .generation-lifecycle {
    padding:10px 12px 0;
  }
  .generation-lifecycle__inner {
    grid-template-columns:minmax(0,1fr) auto;
    gap:8px;
  }
  .generation-lifecycle__summary {
    order:0;
  }
  .generation-lifecycle__summary > span {
    width:28px;
    height:28px;
    flex-basis:28px;
  }
  .generation-lifecycle__value {
    order:1;
  }
  .generation-lifecycle ol {
    grid-column:1/-1;
    order:2;
    margin-top:2px;
  }
  .generation-lifecycle li {
    grid-template-columns:1fr;
    justify-items:center;
    gap:4px;
    text-align:center;
  }
  .generation-lifecycle li:not(:last-child)::after {
    top:9px;
    left:50%;
    right:-50%;
  }
  .generation-lifecycle__marker {
    width:20px;
    height:20px;
  }
  .generation-lifecycle strong {
    max-width:72px;
    width:auto;
    overflow:visible;
    background:transparent;
    font-size:10.5px;
    line-height:1.25;
    text-overflow:clip;
    white-space:normal;
  }
}
@media (prefers-reduced-motion:reduce) {
  li[data-status="active"] .generation-lifecycle__marker svg {
    animation:none;
  }
  .generation-lifecycle__summary > span svg,
  .generation-lifecycle__track i {
    animation:none;
    transition:none;
  }
}
</style>
