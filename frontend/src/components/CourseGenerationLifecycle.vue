<template>
  <nav class="generation-lifecycle" :aria-label="t('courseGeneration.lifecycle.label', '课程生产进度')">
    <ol>
      <li
        v-for="(stage, index) in stages"
        :key="stage.key"
        :data-status="stageStatus(index)"
        :aria-current="index === activeIndex ? 'step' : undefined"
        :aria-label="`${stage.label}：${stageStatusLabel(index)}`"
      >
        <span class="generation-lifecycle__marker">
          <Check v-if="stageStatus(index) === 'completed'" :size="12" />
          <TriangleAlert v-else-if="stageStatus(index) === 'error' || stageStatus(index) === 'blocked'" :size="12" />
          <CirclePause v-else-if="stageStatus(index) === 'paused'" :size="12" />
          <Clock3 v-else-if="stageStatus(index) === 'review'" :size="12" />
          <LoaderCircle v-else-if="stageStatus(index) === 'active'" :size="12" />
          <span v-else>{{ index + 1 }}</span>
        </span>
        <strong>{{ stage.label }}</strong>
      </li>
    </ol>
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

const stages = computed(() => [
  { key: 'requirements', label: t('courseGeneration.lifecycle.requirements', '需求') },
  { key: 'outline', label: t('courseGeneration.lifecycle.outline', '目录') },
  { key: 'teaching', label: t('courseGeneration.lifecycle.teaching', '教案与知识库') },
  { key: 'content', label: t('courseGeneration.lifecycle.content', '正文生成') },
  { key: 'release', label: t('courseGeneration.lifecycle.release', '确认发布') },
])
const activeIndex = computed(() => courseProductionStageIndex(props.task))

function stageStatus(index: number) {
  return courseProductionStageStatus(props.task, index)
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
  padding:11px clamp(18px,5vw,64px) 12px;
  border-bottom:1px solid #e7eaf0;
  background:#fff;
}
.generation-lifecycle ol {
  width:100%;
  max-width:760px;
  display:grid;
  grid-template-columns:repeat(5,minmax(0,1fr));
  margin:0 auto;
  padding:0;
  list-style:none;
}
.generation-lifecycle li {
  position:relative;
  min-width:0;
  display:grid;
  grid-template-columns:24px minmax(0,1fr);
  align-items:center;
  gap:7px;
}
.generation-lifecycle li:not(:last-child)::after {
  content:"";
  position:absolute;
  z-index:0;
  top:11px;
  left:23px;
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
  width:24px;
  height:24px;
  display:grid;
  place-items:center;
  border:1px solid #d5dbe5;
  border-radius:50%;
  color:#98a2b3;
  background:#fff;
  font-size:8px;
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
  font-size:9px;
  line-height:1.25;
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
li[data-status="active"] strong,
li[data-status="review"] strong {
  color:#344054;
}
li[data-status="error"] strong,
li[data-status="blocked"] strong {
  color:#9a4d13;
}
@keyframes lifecycle-spin {
  to { transform:rotate(360deg); }
}
@media (max-width:767px) {
  .generation-lifecycle {
    padding:9px 10px 10px;
  }
  .generation-lifecycle li {
    grid-template-columns:1fr;
    justify-items:center;
    gap:4px;
    text-align:center;
  }
  .generation-lifecycle li:not(:last-child)::after {
    top:10px;
    left:50%;
    right:-50%;
  }
  .generation-lifecycle__marker {
    width:22px;
    height:22px;
  }
  .generation-lifecycle strong {
    max-width:64px;
    width:auto;
    overflow:visible;
    background:transparent;
    font-size:8px;
    line-height:1.15;
    text-overflow:clip;
    white-space:normal;
  }
}
@media (prefers-reduced-motion:reduce) {
  li[data-status="active"] .generation-lifecycle__marker svg {
    animation:none;
  }
}
</style>
