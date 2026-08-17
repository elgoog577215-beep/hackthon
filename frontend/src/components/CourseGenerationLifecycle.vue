<template>
  <nav class="generation-lifecycle" :aria-label="t('courseGeneration.lifecycle.label', '课程生产进度')">
    <div class="generation-lifecycle__inner">
      <div class="generation-lifecycle__summary" :data-status="currentStatus">
        <span>
          <TriangleAlert v-if="currentStatus === 'error' || currentStatus === 'blocked'" :size="14" />
          <CirclePause v-else-if="currentStatus === 'paused'" :size="14" />
          <LoaderCircle v-else-if="currentStatus === 'active'" :size="14" />
          <Check v-else :size="14" />
        </span>
        <div>
          <small>{{ t('courseGeneration.workspace.label', '课程生产') }}</small>
          <strong>{{ activeMilestoneIndex + 1 }} / {{ milestones.length }}</strong>
        </div>
      </div>

      <ol data-testid="generation-milestones">
        <li
          v-for="(milestone, index) in milestones"
          :key="milestone.key"
          :data-status="milestone.status"
          :data-milestone="milestone.key"
          :aria-current="index === activeMilestoneIndex ? 'step' : undefined"
          :aria-label="`${milestone.label}：${milestoneStatusLabel(milestone.status)}`"
        >
          <span class="generation-lifecycle__marker">
            <Check v-if="milestone.status === 'completed'" :size="11" />
            <TriangleAlert v-else-if="milestone.status === 'error' || milestone.status === 'blocked'" :size="11" />
            <CirclePause v-else-if="milestone.status === 'paused'" :size="11" />
            <LoaderCircle v-else-if="milestone.status === 'active'" :size="11" />
            <span v-else>{{ index + 1 }}</span>
          </span>
          <strong>{{ milestone.label }}</strong>
        </li>
      </ol>

      <span class="generation-lifecycle__value" :data-status="currentStatus">{{ currentValue }}</span>

      <button
        type="button"
        class="generation-lifecycle__toggle"
        data-testid="generation-diagnostics-toggle"
        :aria-expanded="diagnosticsOpen"
        aria-controls="generation-lifecycle-diagnostics"
        @click="diagnosticsOpen = !diagnosticsOpen"
      >
        {{ diagnosticsOpen
          ? t('courseGeneration.lifecycle.hideDetail', '收起细节')
          : t('courseGeneration.lifecycle.showDetail', '查看细节') }}
      </button>
    </div>

    <!-- 阶段/批次这类系统内部划分收进诊断面板：默认折叠，
         需要排查时再展开，不和四个里程碑抢用户注意力。
         用 hidden 而不是 v-if——六阶段是 D-05 的可观察性契约，
         必须始终在 DOM 里（屏幕阅读器与自动化验收都靠它），只是默认不可见。 -->
    <ol
      :hidden="!diagnosticsOpen"
      id="generation-lifecycle-diagnostics"
      class="generation-lifecycle__diagnostics"
      data-testid="generation-diagnostics"
    >
      <li
        v-for="(stage, index) in stages"
        :key="stage.key"
        :data-status="stageStatus(index)"
        :data-stage="stage.key"
        :aria-label="`${stage.label}：${stageStatusLabel(index)}`"
      >
        <strong>{{ stage.label }}</strong>
        <span>{{ stageStatusLabel(index) }}</span>
      </li>
    </ol>

    <div class="generation-lifecycle__track" aria-hidden="true">
      <i :style="{ width: `${progressValue}%` }"></i>
    </div>
  </nav>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { Check, CirclePause, LoaderCircle, TriangleAlert } from 'lucide-vue-next'
import type { Task } from '../stores/types'
import { t } from '../shared/i18n'
import {
  OBSERVABLE_TASK_STAGE_KEYS,
  courseMilestones,
  observableTaskStages,
  taskDisplayProgress,
  type ObservableTaskStageStatus,
} from '../utils/task-observability'

const props = withDefaults(defineProps<{
  task?: Task
}>(), {
  task: undefined,
})

const emptyLabels = {
  receive: () => t('taskObservability.receive', '资料接收'),
  parse: () => t('taskObservability.parse', '解析与分类'),
  retrieve: () => t('taskObservability.retrieve', '检索证据'),
  generate: () => t('taskObservability.generate', '内容生成'),
  validate: () => t('taskObservability.validate', '质量检查'),
  export: () => t('taskObservability.export', '导出与发布'),
}
const stages = computed(() => props.task
  ? observableTaskStages(props.task)
  : OBSERVABLE_TASK_STAGE_KEYS.map(key => ({ key, label: emptyLabels[key](), status: 'pending' as const })))
const activeIndex = computed(() => {
  const index = stages.value.findIndex(stage => ['active', 'error', 'paused', 'blocked'].includes(stage.status))
  if (index >= 0) return index
  return props.task?.status === 'completed' ? stages.value.length - 1 : 0
})

const diagnosticsOpen = ref(false)
const milestones = computed(() => courseMilestones(props.task))
const activeMilestoneIndex = computed(() => {
  const index = milestones.value.findIndex(m => ['active', 'error', 'paused', 'blocked'].includes(m.status))
  if (index >= 0) return index
  return props.task?.status === 'completed' ? milestones.value.length - 1 : 0
})

function milestoneStatusLabel(status: ObservableTaskStageStatus) {
  const labels: Record<ObservableTaskStageStatus, string> = {
    completed: t('taskObservability.statusCompleted', '已完成'),
    active: t('taskObservability.statusActive', '进行中'),
    pending: t('taskObservability.statusPending', '待开始'),
    error: t('taskObservability.statusError', '出错'),
    paused: t('taskObservability.statusPaused', '已暂停'),
    blocked: t('taskObservability.statusBlocked', '被阻断'),
  }
  return labels[status]
}
const currentStatus = computed(() => stageStatus(activeIndex.value))
const progressValue = computed(() => props.task ? taskDisplayProgress(props.task) : 0)
const currentValue = computed(() => (
  currentStatus.value === 'active' || currentStatus.value === 'completed'
    ? liveCount.value || `${progressValue.value}%`
    : stageStatusLabel(activeIndex.value)
))

const liveCount = computed(() => {
  const checkpoint = props.task?.recovery?.checkpoint
  const detail = props.task?.phaseDetail || {}
  const completed = Number(
    detail.completed_items
    ?? props.task?.completedNodes
    ?? checkpoint?.completed_nodes
    ?? checkpoint?.completed_teaching_plan_sections
    ?? 0,
  )
  const total = Number(
    detail.total_items
    ?? props.task?.totalNodes
    ?? checkpoint?.total_nodes
    ?? checkpoint?.total_teaching_plan_sections
    ?? 0,
  )
  return total ? `${completed}/${total}` : ''
})

function stageStatus(index: number): ObservableTaskStageStatus {
  return stages.value[index]?.status || 'pending'
}

function stageStatusLabel(index: number) {
  const status = stageStatus(index)
  if (status === 'completed') return t('courseGeneration.lifecycle.completed', '已完成')
  if (status === 'error') return t('courseGeneration.lifecycle.interrupted', '已中断')
  if (status === 'paused') return t('courseGeneration.lifecycle.paused', '已暂停')
  if (status === 'blocked') return t('courseGeneration.lifecycle.blocked', '需处理')
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
  grid-template-columns:repeat(6,minmax(0,1fr));
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
.generation-lifecycle__toggle { flex:0 0 auto; padding:3px 8px; border:1px solid #e2e4ed; border-radius:7px; color:#6f758b; background:#fff; font-size:11px; font-weight:650; cursor:pointer; }
.generation-lifecycle__toggle:hover { color:#41475e; border-color:#cfd3e2; }
.generation-lifecycle__diagnostics { display:flex; flex-wrap:wrap; gap:4px 18px; margin:0; padding:8px 14px; border-top:1px solid #eef0f6; list-style:none; background:#fbfbfe; }
.generation-lifecycle__diagnostics li { display:inline-flex; align-items:baseline; gap:6px; color:#8a90a4; font-size:11px; }
.generation-lifecycle__diagnostics strong { color:#6f758b; font-weight:650; }
.generation-lifecycle__diagnostics li[data-status="error"] span,
.generation-lifecycle__diagnostics li[data-status="blocked"] span { color:#b05a18; font-weight:650; }
.generation-lifecycle__diagnostics li[data-status="active"] span { color:#6b50e8; font-weight:650; }
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
