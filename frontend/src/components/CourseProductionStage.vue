<template>
  <section
    class="course-production-stage"
    :data-state="stageStatus"
    :aria-label="productionAriaLabel"
    aria-live="polite"
  >
    <article class="production-panel">
      <p class="production-panel__stage">{{ stageLabel }}</p>
      <h2>{{ stageTitle }}</h2>
      <p class="production-panel__description">{{ stageDescription }}</p>

      <section class="production-progress" :data-state="stageStatus">
        <div class="production-progress__heading">
          <span>{{ progressCaption }}</span>
          <strong>{{ progressValue }}%</strong>
        </div>
        <div class="production-progress__track" aria-hidden="true">
          <i :style="{ width: `${progressValue}%` }"></i>
        </div>
        <p v-if="activeDetail">
          {{ activeDetail }}
          <span v-if="showElapsed">· {{ elapsedLabel }}</span>
        </p>
      </section>

      <dl class="production-summary">
        <div>
          <dt>{{ t('courseGeneration.production.outputLabel', '本阶段产出') }}</dt>
          <dd>{{ outputTitle }}</dd>
        </div>
        <div v-if="savedSummary">
          <dt>{{ t('courseGeneration.production.savedLabel', '现场已保存') }}</dt>
          <dd><Check :size="13" />{{ savedSummary }}</dd>
        </div>
      </dl>

      <footer class="production-footer">
        <p>{{ footerHint }}</p>
        <div v-if="canResume || hasDraft" class="production-actions">
          <button v-if="canResume" type="button" :disabled="acting" @click="emit('resume')">
            <LoaderCircle v-if="acting" :size="15" />
            <RotateCw v-else :size="15" />
            {{ resumeLabel }}
          </button>
          <button v-if="hasDraft" type="button" class="secondary" :disabled="acting" @click="emit('viewDraft')">
            <BookOpenText :size="15" />
            {{ t('courseGeneration.production.viewSavedDraft', '查看已保存正文') }}
          </button>
        </div>
      </footer>

      <details v-if="technicalError" class="production-error-detail">
        <summary>{{ t('courseGeneration.production.technicalReason', '查看技术原因') }}</summary>
        <code>{{ technicalError }}</code>
      </details>
    </article>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { BookOpenText, Check, LoaderCircle, RotateCw } from 'lucide-vue-next'
import type { Task } from '../stores/types'
import { activeLocale, t } from '../shared/i18n'
import {
  canResumeCourseProduction,
  courseProductionRecoveryDetail,
  courseProductionStageIndex,
  courseProductionStageKey,
  courseProductionStageStatus,
  type CourseProductionStageKey,
} from '../utils/course-production'

const props = withDefaults(defineProps<{
  task?: Task
  courseName?: string
  elapsedSeconds?: number
  acting?: boolean
  hasDraft?: boolean
}>(), {
  task: undefined,
  courseName: '',
  elapsedSeconds: 0,
  acting: false,
  hasDraft: false,
})

const emit = defineEmits<{
  (event: 'resume'): void
  (event: 'viewDraft'): void
}>()

const stageIndex = computed(() => courseProductionStageIndex(props.task))
const stageKey = computed(() => courseProductionStageKey(props.task))
const stageStatus = computed(() => courseProductionStageStatus(props.task, stageIndex.value))
const stageNumber = computed(() => String(stageIndex.value + 1).padStart(2, '0'))
const canResume = computed(() => canResumeCourseProduction(props.task))
const progressValue = computed(() => Math.max(0, Math.min(100, Math.round(Number(props.task?.progress || 0)))))
const productionAriaLabel = computed(() => {
  const label = t('courseGeneration.production.ariaLabel', '课程生产现场')
  return props.courseName ? `${label}：${props.courseName}` : label
})

const showElapsed = computed(() => stageStatus.value === 'active' && props.elapsedSeconds > 0)
const elapsedLabel = computed(() => {
  const minutes = Math.floor(props.elapsedSeconds / 60)
  const seconds = String(props.elapsedSeconds % 60).padStart(2, '0')
  return t('courseGeneration.production.elapsed', '已运行 {time}').replace('{time}', `${minutes}:${seconds}`)
})

const stageLabels = computed<Record<CourseProductionStageKey, string>>(() => ({
  requirements: t('courseGeneration.lifecycle.requirements', '需求'),
  outline: t('courseGeneration.lifecycle.outline', '目录'),
  teaching: t('courseGeneration.lifecycle.teaching', '教案与知识库'),
  content: t('courseGeneration.lifecycle.content', '正文生成'),
  release: t('courseGeneration.lifecycle.release', '确认发布'),
}))
const stageLabel = computed(() => t('courseGeneration.production.stageLabel', '第 {current} 阶段 · {stage}')
  .replace('{current}', stageNumber.value)
  .replace('{stage}', stageLabels.value[stageKey.value]))

const workingTitles = computed<Record<CourseProductionStageKey, string>>(() => ({
  requirements: t('courseGeneration.production.requirementsTitle', '正在锁定课程需求'),
  outline: t('courseGeneration.production.outlineTitle', '正在搭建课程骨架'),
  teaching: t('courseGeneration.production.teachingTitle', '正在编排全课教案'),
  content: t('courseGeneration.production.contentTitle', '课程正文正在逐节生长'),
  release: t('courseGeneration.production.releaseTitle', '正在完成发布前检查'),
}))
const reviewTitles = computed<Record<CourseProductionStageKey, string>>(() => ({
  requirements: t('courseGeneration.production.requirementsReviewTitle', '课程需求等待确认'),
  outline: t('courseGeneration.production.outlineReviewTitle', '课程目录已经准备好'),
  teaching: t('courseGeneration.production.teachingReviewTitle', '全课教案等待确认'),
  content: t('courseGeneration.production.contentReviewTitle', '课程正文等待审阅'),
  release: t('courseGeneration.production.releaseReviewTitle', '课程已经长成，等待发布'),
}))
const stageTitle = computed(() => {
  if (stageStatus.value === 'error') return t('courseGeneration.production.interruptedTitle', '课程生产暂时中断')
  if (stageStatus.value === 'paused') return t('courseGeneration.production.pausedTitle', '课程生产已暂停')
  if (stageStatus.value === 'blocked') return t('courseGeneration.production.blockedTitle', '课程生产需要处理冲突')
  if (stageStatus.value === 'review') return reviewTitles.value[stageKey.value]
  return workingTitles.value[stageKey.value]
})

const descriptions = computed<Record<CourseProductionStageKey, string>>(() => ({
  requirements: t('courseGeneration.production.requirementsDescription', '主题、难度、编排偏好与资料边界会被写入同一份生产契约。'),
  outline: t('courseGeneration.production.outlineDescription', '系统正在把学习需求转成可确认的章节顺序、学习目标与课程范围。'),
  teaching: t('courseGeneration.production.teachingDescription', '系统先冻结全课知识职责，再按预算生成详细教案，并从同一计划编译课程知识库。'),
  content: t('courseGeneration.production.contentDescription', '各小节按真实前置关系并行生成，已完成的草稿会立即保存并出现在课程目录中。'),
  release: t('courseGeneration.production.releaseDescription', '系统正在核对结构、稳定引用与同源版本链；通过后由你确认发布。'),
}))
const stageDescription = computed(() => {
  if (stageStatus.value === 'error') return friendlyError.value
  if (stageStatus.value === 'paused') return t('courseGeneration.production.pausedDescription', '当前模型调用已经停止。')
  if (stageStatus.value === 'blocked') return t('courseGeneration.production.blockedDescription', '当前产物与课程真源存在冲突。')
  if (stageStatus.value === 'review') return t('courseGeneration.production.reviewDescription', '这一阶段需要你的判断；确认前，后续产物不会写入正式课程。')
  return descriptions.value[stageKey.value]
})

const progressCaption = computed(() => stageStatus.value === 'error'
  ? t('courseGeneration.production.progressStopped', '中断时进度')
  : t('courseGeneration.workspace.progress', '生成进度'))
const activeDetail = computed(() => {
  if (stageStatus.value !== 'active') return ''
  if (props.task?.completedNodes && props.task?.totalNodes) {
    return t('courseGeneration.lifecycle.contentProgress', '正文已完成 {completed}/{total} 个小节')
      .replace('{completed}', String(props.task.completedNodes))
      .replace('{total}', String(props.task.totalNodes))
  }
  if (activeLocale.value === 'en' && props.task?.currentPhase) {
    return t(`courseGeneration.phases.${props.task.currentPhase}`, props.task.currentPhase)
  }
  return props.task?.currentStep || t('courseGeneration.workspace.preparing', '正在准备课程结构')
})

const outputTitles = computed<Record<CourseProductionStageKey, string>>(() => ({
  requirements: t('courseGeneration.production.requirementsOutput', '课程生产契约'),
  outline: t('courseGeneration.production.outlineOutput', '可确认课程目录'),
  teaching: t('courseGeneration.production.teachingOutput', '唯一正式全课教案'),
  content: t('courseGeneration.production.contentOutput', '可审阅课程正文'),
  release: t('courseGeneration.production.releaseOutput', '正式学习课程'),
}))
const outputTitle = computed(() => outputTitles.value[stageKey.value])

const savedItems = computed(() => {
  const checkpoint = props.task?.recovery?.checkpoint
  if (!checkpoint) return []
  const items: string[] = []
  if (checkpoint.requirements_ready) items.push(t('courseGeneration.production.savedRequirements', '课程需求'))
  if (checkpoint.outline_ready) items.push(t('courseGeneration.production.savedOutline', '课程目录'))
  if (checkpoint.teaching_plan_ready) items.push(t('courseGeneration.production.savedPlan', '全课教案'))
  if (Number(checkpoint.completed_nodes || 0) > 0) {
    items.push(t('courseGeneration.production.savedLessons', '{count} 节正文')
      .replace('{count}', String(checkpoint.completed_nodes)))
  }
  return items
})
const savedSummary = computed(() => savedItems.value.join(' · '))

const nextDetails = computed<Record<CourseProductionStageKey, string>>(() => ({
  requirements: t('courseGeneration.production.requirementsNext', '需求确认后立即生成课程目录；不会再增加额外确认门。'),
  outline: t('courseGeneration.production.outlineNext', '目录确认后，系统自动生成全课教案、知识库与各节正文。'),
  teaching: t('courseGeneration.production.teachingNext', '全课教案汇编通过后，正文会按依赖波次并行生成。'),
  content: t('courseGeneration.production.contentNext', '所有小节完成后进入确定性发布检查，不追加 AI 返工循环。'),
  release: t('courseGeneration.production.releaseNext', '确认发布后，当前页面会原地切换为正式学习现场。'),
}))
const footerHint = computed(() => (
  ['error', 'paused', 'blocked'].includes(stageStatus.value)
    ? courseProductionRecoveryDetail(props.task)
    : nextDetails.value[stageKey.value]
))

const technicalError = computed(() => String(props.task?.error || '').trim())
const friendlyError = computed(() => {
  const error = technicalError.value.toLowerCase()
  if (/authentication|credential|api[_ -]?key/.test(error)) {
    return t('courseGeneration.production.authError', 'AI 服务暂时无法完成身份校验。')
  }
  if (/timeout|timed out/.test(error)) {
    return t('courseGeneration.production.timeoutError', 'AI 服务响应超时，本阶段尚未完成。')
  }
  if (/unavailable|connection|network/.test(error)) {
    return t('courseGeneration.production.unavailableError', 'AI 服务暂时不可用，本阶段尚未完成。')
  }
  return t('courseGeneration.production.genericError', '本阶段尚未完成。')
})
const resumeLabel = computed(() => props.task?.status === 'paused'
  ? t('courseGeneration.production.continueAction', '继续课程生产')
  : t('courseGeneration.production.retryAction', '重试当前阶段'))
</script>

<style scoped>
.course-production-stage {
  min-height:0;
  flex:1;
  display:block;
  overflow:auto;
  padding:clamp(44px,7vh,70px) clamp(28px,8vw,120px) 96px;
  background:#fbfcfe;
}
.production-panel {
  width:100%;
  max-width:760px;
  margin:0 auto;
  color:#202939;
}
.production-panel__stage {
  margin:0 0 10px;
  color:#585bc9;
  font-size:10px;
  font-weight:800;
  letter-spacing:.06em;
}
.production-panel h2 {
  margin:0;
  color:#182230;
  font:700 clamp(30px,3.2vw,42px)/1.14 Georgia,"Noto Serif SC",serif;
  letter-spacing:-.025em;
}
.production-panel__description {
  max-width:650px;
  margin:13px 0 0;
  color:#667085;
  font-size:13px;
  line-height:1.75;
}
.production-progress {
  margin-top:31px;
}
.production-progress__heading {
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:16px;
}
.production-progress__heading span {
  color:#475467;
  font-size:10px;
  font-weight:750;
}
.production-progress__heading strong {
  color:#4f46e5;
  font:750 17px/1 ui-monospace,SFMono-Regular,monospace;
}
.production-progress__track {
  height:4px;
  margin-top:10px;
  overflow:hidden;
  border-radius:999px;
  background:#e9ecf3;
}
.production-progress__track i {
  display:block;
  height:100%;
  min-width:4px;
  border-radius:inherit;
  background:#6664df;
  transition:width .3s ease;
}
.production-progress[data-state="error"] .production-progress__track i,
.production-progress[data-state="blocked"] .production-progress__track i {
  background:#d97706;
}
.production-progress[data-state="paused"] .production-progress__track i {
  background:#98a2b3;
}
.production-progress > p {
  margin:8px 0 0;
  color:#8a93a4;
  font-size:9px;
  line-height:1.5;
}
.production-summary {
  display:flex;
  flex-wrap:wrap;
  gap:24px 54px;
  margin:25px 0 0;
  padding:20px 0 0;
  border-top:1px solid #e4e7ec;
}
.production-summary > div {
  min-width:180px;
}
.production-summary dt {
  color:#98a2b3;
  font-size:9px;
}
.production-summary dd {
  display:flex;
  align-items:center;
  gap:6px;
  margin:5px 0 0;
  color:#344054;
  font-size:12px;
  font-weight:750;
}
.production-summary dd svg {
  color:#07956d;
}
.production-footer {
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:28px;
  margin-top:26px;
  padding-top:22px;
  border-top:1px solid #e4e7ec;
}
.production-footer > p {
  max-width:470px;
  margin:0;
  color:#667085;
  font-size:10px;
  line-height:1.65;
}
.production-actions {
  flex:0 0 auto;
  display:flex;
  align-items:center;
  gap:9px;
}
.production-actions button {
  min-height:38px;
  display:inline-flex;
  align-items:center;
  justify-content:center;
  gap:7px;
  padding:0 15px;
  border:0;
  border-radius:8px;
  color:#fff;
  background:#4f46d9;
  font-size:10px;
  font-weight:800;
  cursor:pointer;
  transition:background .16s ease,transform .16s ease;
}
.production-actions button:hover:not(:disabled) {
  transform:translateY(-1px);
  background:#4038c4;
}
.production-actions button:disabled {
  opacity:.58;
  cursor:wait;
}
.production-actions button:disabled svg:first-child {
  animation:production-spin .9s linear infinite;
}
.production-actions button.secondary {
  color:#475467;
  border:1px solid #d0d5dd;
  background:transparent;
}
.production-actions button.secondary:hover:not(:disabled) {
  color:#4338ca;
  border-color:#b9b8ed;
  background:#f7f7ff;
}
.production-error-detail {
  margin-top:14px;
  color:#7b8495;
  font-size:9px;
}
.production-error-detail summary {
  width:max-content;
  cursor:pointer;
}
.production-error-detail code {
  display:block;
  margin-top:8px;
  padding:8px 10px;
  overflow:auto;
  border-left:2px solid #e7a74e;
  color:#8a3b12;
  background:#fffaf2;
  font-size:9px;
  white-space:pre-wrap;
}
@keyframes production-spin {
  to { transform:rotate(360deg); }
}
@media (max-width:767px) {
  .course-production-stage {
    padding:36px 22px 72px;
  }
  .production-panel h2 {
    font-size:29px;
  }
  .production-panel__description {
    font-size:12px;
  }
  .production-summary {
    display:grid;
    grid-template-columns:1fr;
    gap:16px;
  }
  .production-footer {
    align-items:stretch;
    flex-direction:column;
    gap:18px;
  }
  .production-actions {
    width:100%;
  }
  .production-actions button {
    flex:1;
  }
}
@media (prefers-reduced-motion:reduce) {
  .production-actions button svg,
  .production-progress__track i {
    animation:none!important;
    transition:none;
  }
}
</style>
