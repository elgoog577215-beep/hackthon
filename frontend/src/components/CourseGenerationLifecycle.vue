<template>
  <section class="generation-lifecycle" :aria-label="t('courseGeneration.lifecycle.label', '课程生产进度')">
    <div class="generation-lifecycle__summary">
      <span>{{ t('courseGeneration.lifecycle.stage', '第 {current}/{total} 阶段')
        .replace('{current}', String(activeIndex + 1))
        .replace('{total}', String(stages.length)) }}</span>
      <strong>{{ stages[activeIndex]?.label }}</strong>
      <p>{{ activeDetail }}</p>
    </div>
    <ol>
      <li
        v-for="(stage, index) in stages"
        :key="stage.key"
        :data-status="stageStatus(index)"
      >
        <span class="generation-lifecycle__marker">
          <Check v-if="stageStatus(index) === 'completed'" :size="13" />
          <TriangleAlert v-else-if="stageStatus(index) === 'error' || stageStatus(index) === 'blocked'" :size="13" />
          <CirclePause v-else-if="stageStatus(index) === 'paused'" :size="13" />
          <Clock3 v-else-if="stageStatus(index) === 'review'" :size="13" />
          <LoaderCircle v-else-if="stageStatus(index) === 'active'" :size="13" />
          <span v-else>{{ index + 1 }}</span>
        </span>
        <span class="generation-lifecycle__copy">
          <strong>{{ stage.label }}</strong>
          <small>{{ stageStatusLabel(index) }}</small>
        </span>
      </li>
    </ol>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Check, CirclePause, Clock3, LoaderCircle, TriangleAlert } from 'lucide-vue-next'
import type { Task } from '../stores/types'
import { t } from '../shared/i18n'
import { courseProductionRecoveryDetail, courseProductionStageIndex, courseProductionStageStatus } from '../utils/course-production'

const props = withDefaults(defineProps<{
  task?: Task
  elapsedSeconds?: number
}>(), {
  task: undefined,
  elapsedSeconds: 0,
})

const stages = computed(() => [
  { key: 'requirements', label: t('courseGeneration.lifecycle.requirements', '需求') },
  { key: 'outline', label: t('courseGeneration.lifecycle.outline', '目录') },
  { key: 'teaching', label: t('courseGeneration.lifecycle.teaching', '教案与知识库') },
  { key: 'content', label: t('courseGeneration.lifecycle.content', '正文生成') },
  { key: 'release', label: t('courseGeneration.lifecycle.release', '确认发布') },
])

const phase = computed(() => String(props.task?.currentPhase || 'queued'))
const reviewStep = computed(() => props.task?.guidedWorkflow?.review_step || null)
const activeIndex = computed(() => courseProductionStageIndex(props.task))

const activeDetail = computed(() => {
  const status = stageStatus(activeIndex.value)
  if (status === 'error') {
    return courseProductionRecoveryDetail(props.task)
  }
  if (status === 'paused') {
    return courseProductionRecoveryDetail(props.task)
  }
  if (status === 'blocked') {
    return t('courseGeneration.lifecycle.blockedDetail', '当前产物需要完成冲突对账后继续')
  }
  if (activeIndex.value === 1 && reviewStep.value === 'outline') {
    return t('courseGeneration.lifecycle.outlineReady', '目录已就绪，等待你确认后继续')
  }
  if (activeIndex.value === 2) {
    const detail = props.task?.phaseDetail || {}
    const totalSections = Number(detail.total_sections || detail.item_total || props.task?.totalNodes || 0)
    const wait = t('courseGeneration.lifecycle.waited', '已等待 {seconds} 秒')
      .replace('{seconds}', String(props.elapsedSeconds))
    if (/skeleton/.test(phase.value)) {
      const completedSections = Number(detail.completed_sections || 0)
      return totalSections
        ? t('courseGeneration.lifecycle.skeletonProgress', '正在冻结全课知识职责 {completed}/{total} 节 · {wait}')
          .replace('{completed}', String(completedSections))
          .replace('{total}', String(totalSections))
          .replace('{wait}', wait)
        : t('courseGeneration.lifecycle.skeletonWorking', '正在冻结全课知识职责 · {wait}').replace('{wait}', wait)
    }
    const totalBatches = Number(detail.total_batches || 0)
    if (/batch/.test(phase.value) || totalBatches > 0) {
      const completedBatches = Number(detail.completed_batches || 0)
      const completedSections = Number(detail.completed_sections || 0)
      return t('courseGeneration.lifecycle.batchProgress', '详细教案已完成 {completedBatches}/{totalBatches} 批、{completedSections}/{totalSections} 节 · {wait}')
        .replace('{completedBatches}', String(completedBatches))
        .replace('{totalBatches}', String(totalBatches || 1))
        .replace('{completedSections}', String(completedSections))
        .replace('{totalSections}', String(totalSections || props.task?.totalNodes || 0))
        .replace('{wait}', wait)
    }
    if (/assembly|validation/.test(phase.value)) {
      return t('courseGeneration.lifecycle.assembling', '正在汇编并校验唯一的全课教案 · {wait}').replace('{wait}', wait)
    }
    return totalSections
      ? t('courseGeneration.lifecycle.planningAll', '正在生成并汇编全课 {count} 个小节教案 · {wait}')
        .replace('{count}', String(totalSections))
        .replace('{wait}', wait)
      : t('courseGeneration.lifecycle.planning', '正在生成并汇编全课教案 · {wait}').replace('{wait}', wait)
  }
  if (activeIndex.value === 3) {
    const completed = Number(props.task?.completedNodes || props.task?.phaseDetail?.completed_items || 0)
    const total = Number(props.task?.totalNodes || props.task?.phaseDetail?.total_items || 0)
    return total
      ? t('courseGeneration.lifecycle.contentProgress', '正文已完成 {completed}/{total} 个小节')
        .replace('{completed}', String(completed))
        .replace('{total}', String(total))
      : t('courseGeneration.lifecycle.contentWorking', '正在并行生成各节正文')
  }
  if (activeIndex.value === 4 && reviewStep.value === 'release') {
    return t('courseGeneration.lifecycle.releaseReady', '课程已生成完毕，等待确认发布')
  }
  return props.task?.currentStep || t('courseGeneration.workspace.preparing', '正在准备课程结构')
})

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
  if (status === 'active') {
    return t('courseGeneration.lifecycle.inProgress', '进行中')
  }
  return t('courseGeneration.lifecycle.pending', '未开始')
}
</script>

<style scoped>
.generation-lifecycle { flex:0 0 auto; display:grid; grid-template-columns:minmax(240px,.78fr) minmax(560px,1.55fr); align-items:center; gap:30px; padding:15px 20px 16px; border-bottom:1px solid #e6e9f2; background:linear-gradient(90deg,#fbfcff,#f8f9fd); }
.generation-lifecycle__summary { min-width:0; display:grid; grid-template-columns:auto 1fr; align-items:baseline; gap:4px 10px; }
.generation-lifecycle__summary > span { color:#6466d8; font-size:9px; font-weight:850; letter-spacing:.08em; }
.generation-lifecycle__summary > strong { color:#1f2937; font-size:13px; }
.generation-lifecycle__summary > p { grid-column:1/-1; margin:0; overflow:hidden; color:#667085; font-size:10px; line-height:1.5; text-overflow:ellipsis; white-space:nowrap; }
.generation-lifecycle ol { min-width:0; display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); margin:0; padding:0; list-style:none; }
.generation-lifecycle li { position:relative; min-width:0; display:grid; grid-template-columns:27px minmax(0,1fr); align-items:center; gap:8px; }
.generation-lifecycle li:not(:last-child)::after { content:""; position:absolute; z-index:0; top:13px; left:26px; right:1px; height:1px; background:#d8deea; }
.generation-lifecycle li[data-status="completed"]:not(:last-child)::after { background:#8ed1b7; }
.generation-lifecycle__marker { position:relative; z-index:1; width:27px; height:27px; display:grid; place-items:center; border:1px solid #d5dce8; border-radius:50%; color:#98a2b3; background:#fff; font-size:9px; font-weight:800; }
li[data-status="completed"] .generation-lifecycle__marker { border-color:#8ed1b7; color:#087a5b; background:#ecfdf5; }
li[data-status="active"] .generation-lifecycle__marker { border-color:#7c83ee; color:#4f46e5; background:#eef0ff; box-shadow:0 0 0 4px rgba(99,102,241,.1); }
li[data-status="review"] .generation-lifecycle__marker { border-color:#76c9ad; color:#087a5b; background:#ecfdf5; box-shadow:0 0 0 4px rgba(16,163,127,.08); }
li[data-status="error"] .generation-lifecycle__marker,li[data-status="blocked"] .generation-lifecycle__marker { border-color:#edb56a; color:#b54708; background:#fff7e8; box-shadow:0 0 0 4px rgba(217,119,6,.08); }
li[data-status="paused"] .generation-lifecycle__marker { border-color:#c3c9d4; color:#667085; background:#f2f4f7; }
li[data-status="active"] .generation-lifecycle__marker svg { animation:lifecycle-spin .9s linear infinite; }
.generation-lifecycle__copy { position:relative; z-index:1; min-width:0; display:flex; flex-direction:column; padding-right:6px; background:#fbfcff; }
.generation-lifecycle__copy strong { overflow:hidden; color:#667085; font-size:10px; line-height:1.3; text-overflow:ellipsis; white-space:nowrap; }
.generation-lifecycle__copy small { color:#a0a8b5; font-size:8px; }
li[data-status="active"] .generation-lifecycle__copy strong { color:#242b3a; }
li[data-status="completed"] .generation-lifecycle__copy strong { color:#3f6e60; }
li[data-status="review"] .generation-lifecycle__copy strong { color:#087a5b; }
li[data-status="error"] .generation-lifecycle__copy strong,li[data-status="blocked"] .generation-lifecycle__copy strong { color:#9a4d13; }
@keyframes lifecycle-spin { to { transform:rotate(360deg); } }
@media (max-width:1050px) {
  .generation-lifecycle { grid-template-columns:1fr; gap:12px; }
}
@media (max-width:767px) {
  .generation-lifecycle { gap:10px; padding:10px 10px 12px; overflow:hidden; }
  .generation-lifecycle__summary { grid-template-columns:auto 1fr; padding:0 2px; }
  .generation-lifecycle__summary > strong { font-size:11px; }
  .generation-lifecycle__summary > p { font-size:9px; white-space:normal; }
  .generation-lifecycle ol { width:100%; }
  .generation-lifecycle li { grid-template-columns:1fr; justify-items:center; gap:5px; text-align:center; }
  .generation-lifecycle li:not(:last-child)::after { top:11px; left:50%; right:-50%; }
  .generation-lifecycle__marker { width:23px; height:23px; }
  .generation-lifecycle__copy { align-items:center; padding:0 2px; background:transparent; }
  .generation-lifecycle__copy strong { max-width:62px; overflow:visible; font-size:8px; line-height:1.15; text-overflow:clip; white-space:normal; }
  .generation-lifecycle__copy small { margin-top:2px; font-size:7px; }
}
@media (prefers-reduced-motion:reduce) {
  li[data-status="active"] .generation-lifecycle__marker svg { animation:none; }
}
</style>
