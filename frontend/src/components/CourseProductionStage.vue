<template>
  <section
    class="course-production-stage"
    :data-state="stageStatus"
    :aria-label="productionAriaLabel"
    aria-live="polite"
  >
    <article class="formation-sheet">
      <header class="formation-sheet__header">
        <span class="formation-sheet__state" :data-state="stageStatus">
          <TriangleAlert v-if="stageStatus === 'error' || stageStatus === 'blocked'" :size="14" />
          <CirclePause v-else-if="stageStatus === 'paused'" :size="14" />
          <LoaderCircle v-else :size="14" />
          {{ stageLabel }}
        </span>
        <h1>{{ courseName || t('courseGeneration.production.untitled', '新课程') }}</h1>
        <p>{{ stageDescription }}</p>
      </header>

      <section class="formation-outline" :aria-label="t('courseGeneration.production.navigatorLabel', '课程结构')">
        <header>
          <div>
            <span>{{ t('courseGeneration.production.navigatorLabel', '课程结构') }}</span>
            <strong>{{ outlineTitle }}</strong>
          </div>
          <small>{{ outlineMeta }}</small>
        </header>

        <ol v-if="outlineNodes.length" class="formation-outline__nodes">
          <li
            v-for="(node, index) in outlineNodes"
            :key="node.node_id"
            :data-level="node.node_level"
            :data-state="nodeState(node)"
          >
            <span class="formation-outline__index">{{ String(index + 1).padStart(2, '0') }}</span>
            <span class="formation-outline__marker" aria-hidden="true"></span>
            <div>
              <strong>{{ node.node_name }}</strong>
              <p v-if="node.learning_objective">{{ node.learning_objective }}</p>
            </div>
            <span class="formation-outline__status">
              <LoaderCircle v-if="nodeState(node) === 'generating'" :size="12" />
              <Check v-else-if="nodeState(node) === 'finalized'" :size="12" />
              <TriangleAlert v-else-if="nodeState(node) === 'failed'" :size="12" />
              {{ nodeStateLabel(node) }}
            </span>
          </li>
        </ol>

        <div v-else class="formation-outline__skeleton" aria-hidden="true">
          <div v-for="row in skeletonRows" :key="row" :data-level="row === 1 || row === 4 ? 1 : 2">
            <span></span>
            <i></i>
            <p><b></b><small></small></p>
          </div>
        </div>
      </section>

      <aside v-if="isTerminal" class="formation-recovery" :data-state="stageStatus">
        <span class="formation-recovery__icon">
          <CirclePause v-if="stageStatus === 'paused'" :size="17" />
          <GitCompareArrows v-else-if="stageStatus === 'blocked'" :size="17" />
          <TriangleAlert v-else :size="17" />
        </span>
        <div>
          <strong>{{ terminalTitle }}</strong>
          <p>{{ friendlyError }} {{ recoveryDetail }}</p>
          <div v-if="savedItems.length" class="formation-recovery__saved">
            <span v-for="item in savedItems" :key="item"><Check :size="11" />{{ item }}</span>
          </div>
          <details v-if="technicalError">
            <summary>{{ t('courseGeneration.production.technicalReason', '查看技术原因') }}</summary>
            <code>{{ technicalError }}</code>
          </details>
        </div>
        <button v-if="canResume" type="button" :disabled="acting" @click="emit('resume')">
          <LoaderCircle v-if="acting" :size="15" />
          <RotateCw v-else :size="15" />
          {{ resumeLabel }}
        </button>
      </aside>

      <footer v-else class="formation-sheet__footer">
        <div>
          <span>{{ t('courseGeneration.production.nextLabel', '接下来') }}</span>
          <p>{{ footerHint }}</p>
        </div>
        <span v-if="savedSummary"><Check :size="12" />{{ savedSummary }}</span>
      </footer>
    </article>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Check, CirclePause, GitCompareArrows, LoaderCircle, RotateCw, TriangleAlert } from 'lucide-vue-next'
import type { Node, Task } from '../stores/types'
import { t } from '../shared/i18n'
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
  nodes?: Node[]
  acting?: boolean
}>(), {
  task: undefined,
  courseName: '',
  nodes: () => [],
  acting: false,
})

const emit = defineEmits<{
  (event: 'resume'): void
}>()

const skeletonRows = [1, 2, 3, 4, 5, 6]
const stageIndex = computed(() => courseProductionStageIndex(props.task))
const stageKey = computed(() => courseProductionStageKey(props.task))
const stageStatus = computed(() => courseProductionStageStatus(props.task, stageIndex.value))
const isTerminal = computed(() => ['error', 'paused', 'blocked'].includes(stageStatus.value))
const canResume = computed(() => canResumeCourseProduction(props.task))
const progressValue = computed(() => Math.max(0, Math.min(100, Math.round(Number(props.task?.progress || 0)))))
const productionAriaLabel = computed(() => {
  const label = t('courseGeneration.production.ariaLabel', '课程生产现场')
  return props.courseName ? `${label}：${props.courseName}` : label
})
const outlineNodes = computed(() => props.nodes
  .filter(node => node.node_level <= 2)
  .slice()
  .sort((left, right) => {
    const source = props.nodes
    return source.findIndex(node => node.node_id === left.node_id) - source.findIndex(node => node.node_id === right.node_id)
  }))

const stageLabels = computed<Record<CourseProductionStageKey, string>>(() => ({
  requirements: t('courseGeneration.lifecycle.requirements', '需求'),
  outline: t('courseGeneration.lifecycle.outline', '目录'),
  teaching: t('courseGeneration.lifecycle.teaching', '教案与知识库'),
  content: t('courseGeneration.lifecycle.content', '正文生成'),
  release: t('courseGeneration.lifecycle.release', '确认发布'),
}))
const statusLabels = computed(() => ({
  active: t('courseGeneration.lifecycle.inProgress', '进行中'),
  review: t('courseGeneration.lifecycle.needsConfirmation', '待确认'),
  error: t('courseGeneration.lifecycle.interrupted', '已中断'),
  paused: t('courseGeneration.lifecycle.paused', '已暂停'),
  blocked: t('courseGeneration.lifecycle.blocked', '需处理'),
  completed: t('courseGeneration.lifecycle.completed', '已完成'),
  pending: t('courseGeneration.lifecycle.pending', '未开始'),
}))
const stageLabel = computed(() => `${stageLabels.value[stageKey.value]} · ${statusLabels.value[stageStatus.value]}`)
const descriptions = computed<Record<CourseProductionStageKey, string>>(() => ({
  requirements: t('courseGeneration.production.requirementsDescription', '主题、难度、编排偏好与资料边界会被写入同一份生产契约。'),
  outline: t('courseGeneration.production.outlineDescription', '系统正在把学习需求转成可确认的章节顺序、学习目标与课程范围。'),
  teaching: t('courseGeneration.production.teachingDescription', '系统先冻结全课知识职责，再按预算生成详细教案，并从同一计划编译课程知识库。'),
  content: t('courseGeneration.production.contentDescription', '各小节按真实前置关系并行生成，已完成的草稿会立即保存并出现在课程目录中。'),
  release: t('courseGeneration.production.releaseDescription', '系统正在核对结构、稳定引用与同源版本链；通过后由你确认发布。'),
}))
const stageDescription = computed(() => descriptions.value[stageKey.value])
const outlineTitle = computed(() => {
  if (outlineNodes.value.length) {
    return t('courseGeneration.production.outlineVisible', '目录已经进入课程工作区')
  }
  return t('courseGeneration.production.outlineForming', '目录会在最终位置逐步出现')
})
const outlineMeta = computed(() => {
  if (outlineNodes.value.length) {
    return t('courseGeneration.production.nodeCount', '{count} 个节点')
      .replace('{count}', String(outlineNodes.value.length))
  }
  return t('courseGeneration.production.progressValue', '{progress}%')
    .replace('{progress}', String(progressValue.value))
})

function nodeState(node: Node) {
  const status = String(node.generation_status || '')
  if (status === 'generating' || node.content_state === 'generating') return 'generating'
  if (status === 'error' || node.content_state === 'failed' || node.content_state === 'error') return 'failed'
  if (status === 'completed' || node.content_state === 'finalized') return 'finalized'
  if (node.content_state === 'draft' || Boolean(node.node_content)) return 'draft'
  return 'waiting'
}

function nodeStateLabel(node: Node) {
  const state = nodeState(node)
  if (state === 'generating') return t('courseGeneration.workspace.generating', '正在生成')
  if (state === 'finalized') return t('courseGeneration.workspace.finalized', '已定稿')
  if (state === 'failed') return t('courseGeneration.workspace.failed', '生成失败')
  if (state === 'draft') return t('courseGeneration.workspace.draft', 'AI 草稿')
  return t('courseGeneration.workspace.waiting', '等待生成')
}

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
const savedSummary = computed(() => savedItems.value.length
  ? t('courseGeneration.production.savedInline', '已保存：{items}').replace('{items}', savedItems.value.join(' · '))
  : '')
const nextDetails = computed<Record<CourseProductionStageKey, string>>(() => ({
  requirements: t('courseGeneration.production.requirementsNext', '需求确认后立即生成课程目录；不会再增加额外确认门。'),
  outline: t('courseGeneration.production.outlineNext', '目录确认后，系统自动生成全课教案、知识库与各节正文。'),
  teaching: t('courseGeneration.production.teachingNext', '全课教案汇编通过后，正文会按依赖波次并行生成。'),
  content: t('courseGeneration.production.contentNext', '所有小节完成后进入确定性发布检查，不追加 AI 返工循环。'),
  release: t('courseGeneration.production.releaseNext', '确认发布后，当前页面会原地切换为正式学习现场。'),
}))
const footerHint = computed(() => nextDetails.value[stageKey.value])
const recoveryDetail = computed(() => courseProductionRecoveryDetail(props.task))
const technicalError = computed(() => String(props.task?.error || '').trim())
const terminalTitle = computed(() => {
  if (stageStatus.value === 'paused') return t('courseGeneration.production.pausedTitle', '课程生产已暂停')
  if (stageStatus.value === 'blocked') return t('courseGeneration.production.blockedTitle', '课程生产需要处理冲突')
  return t('courseGeneration.production.interruptedTitle', '课程生产暂时中断')
})
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
  if (stageStatus.value === 'paused') return t('courseGeneration.production.pausedDescription', '当前模型调用已经停止。')
  if (stageStatus.value === 'blocked') return t('courseGeneration.production.blockedDescription', '当前产物与课程真源存在冲突。')
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
  overflow:auto;
  padding:10px clamp(14px,2.5vw,28px) 16px;
  background:#f6f7f9;
}
.formation-sheet {
  width:min(1040px,100%);
  margin:0 auto;
  overflow:hidden;
  border:1px solid #dde1e8;
  border-radius:10px;
  background:#fff;
  box-shadow:0 8px 22px rgba(30,41,59,.05);
}
.formation-sheet__header {
  padding:14px 20px 12px;
  border-bottom:1px solid #e7e9ee;
}
.formation-sheet__state {
  display:inline-flex;
  align-items:center;
  gap:7px;
  color:#4f55b5;
  font-size:9px;
  font-weight:850;
  letter-spacing:.07em;
}
.formation-sheet__state[data-state="error"],
.formation-sheet__state[data-state="blocked"] { color:#a85b1a; }
.formation-sheet__state[data-state="paused"] { color:#667085; }
.formation-sheet__state svg.lucide-loader-circle { animation:formation-spin .9s linear infinite; }
.formation-sheet__header h1 {
  margin:3px 0;
  color:#17202e;
  font:720 clamp(20px,1.75vw,25px)/1.18 var(--font-sans);
  letter-spacing:-.015em;
}
.formation-sheet__header p {
  max-width:690px;
  margin:0;
  color:#687386;
  font-size:11px;
  line-height:1.4;
}
.formation-outline { padding:0 20px; }
.formation-outline > header {
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:14px;
  padding:9px 0 7px;
  border-bottom:1px solid #e9ebef;
}
.formation-outline > header div { display:flex; align-items:baseline; gap:9px; }
.formation-outline > header span {
  color:#8a93a3;
  font-size:8px;
  font-weight:800;
  letter-spacing:.08em;
}
.formation-outline > header strong { color:#354052; font-size:10px; }
.formation-outline > header small {
  color:#697386;
  font:700 8px/1 ui-monospace,SFMono-Regular,monospace;
}
.formation-outline__nodes {
  display:grid;
  margin:0;
  padding:3px 0 9px;
  list-style:none;
}
.formation-outline__nodes li {
  display:grid;
  grid-template-columns:30px 13px minmax(0,1fr) auto;
  align-items:start;
  gap:8px;
  padding:6px 0;
  border-bottom:1px solid #f0f1f4;
}
.formation-outline__nodes li:last-child { border-bottom:0; }
.formation-outline__index {
  padding-top:3px;
  color:#9aa1ae;
  font:700 8px/1 ui-monospace,SFMono-Regular,monospace;
}
.formation-outline__marker {
  width:8px;
  height:8px;
  margin-top:2px;
  border:1.5px solid #aab1bf;
  border-radius:50%;
  background:#fff;
}
.formation-outline__nodes li[data-level="1"] .formation-outline__marker {
  width:10px;
  height:10px;
  margin-top:1px;
  border:0;
  border-radius:3px;
  background:#4f5b70;
}
.formation-outline__nodes li[data-state="generating"] .formation-outline__marker {
  border-color:#676bd6;
  background:#dfe1ff;
  box-shadow:0 0 0 3px #f0f0ff;
}
.formation-outline__nodes li[data-state="finalized"] .formation-outline__marker {
  border-color:#158467;
  background:#bce8d8;
}
.formation-outline__nodes li[data-state="failed"] .formation-outline__marker {
  border-color:#c36420;
  background:#fee1bf;
}
.formation-outline__nodes li > div { min-width:0; }
.formation-outline__nodes li > div strong {
  display:block;
  overflow:hidden;
  color:#354052;
  font-size:10px;
  text-overflow:ellipsis;
  white-space:nowrap;
}
.formation-outline__nodes li[data-level="1"] > div strong { color:#1f2937; font-size:11px; }
.formation-outline__nodes li > div p {
  margin:3px 0 0;
  overflow:hidden;
  color:#7b8494;
  font-size:8px;
  text-overflow:ellipsis;
  white-space:nowrap;
}
.formation-outline__status {
  display:inline-flex;
  align-items:center;
  gap:4px;
  padding:2px 0 0 8px;
  color:#8790a0;
  font-size:8px;
  white-space:nowrap;
}
li[data-state="generating"] .formation-outline__status { color:#5056b5; }
li[data-state="finalized"] .formation-outline__status { color:#087a5b; }
li[data-state="failed"] .formation-outline__status { color:#b54708; }
.formation-outline__status svg.lucide-loader-circle { animation:formation-spin .9s linear infinite; }
.formation-outline__skeleton { display:grid; padding:3px 0 9px; }
.formation-outline__skeleton > div {
  display:grid;
  grid-template-columns:30px 13px minmax(0,1fr);
  align-items:start;
  gap:8px;
  padding:6px 0;
  border-bottom:1px solid #f0f1f4;
}
.formation-outline__skeleton > div:last-child { border-bottom:0; }
.formation-outline__skeleton span {
  width:18px;
  height:6px;
  margin-top:3px;
  border-radius:2px;
  background:#edf0f3;
}
.formation-outline__skeleton i {
  width:8px;
  height:8px;
  border:1px solid #d9dde4;
  border-radius:50%;
  background:#fff;
}
.formation-outline__skeleton div[data-level="1"] i {
  width:10px;
  height:10px;
  border:0;
  border-radius:3px;
  background:#d7dce3;
}
.formation-outline__skeleton p { display:grid; gap:6px; margin:0; }
.formation-outline__skeleton b,
.formation-outline__skeleton small {
  display:block;
  height:8px;
  border-radius:3px;
  background:linear-gradient(90deg,#eceff3 20%,#f7f8fa 45%,#eceff3 70%);
  background-size:220% 100%;
  animation:formation-shimmer 1.5s ease infinite;
}
.formation-outline__skeleton b { width:52%; }
.formation-outline__skeleton small { width:76%; height:6px; }
.formation-outline__skeleton div:nth-child(2) b,
.formation-outline__skeleton div:nth-child(5) b { width:68%; }
.formation-recovery {
  display:grid;
  grid-template-columns:34px minmax(0,1fr) auto;
  align-items:start;
  gap:11px;
  margin:0 20px 10px;
  padding:9px;
  border:1px solid #efd3a8;
  border-radius:9px;
  color:#75431c;
  background:#fffbf3;
}
.formation-recovery[data-state="paused"] {
  border-color:#d8dde5;
  color:#4b5565;
  background:#f7f8fa;
}
.formation-recovery__icon {
  width:34px;
  height:34px;
  display:grid;
  place-items:center;
  border-radius:8px;
  color:#b54708;
  background:#fff0d9;
}
.formation-recovery[data-state="paused"] .formation-recovery__icon {
  color:#667085;
  background:#e8ebf0;
}
.formation-recovery strong { color:#643713; font-size:10px; }
.formation-recovery[data-state="paused"] strong { color:#344054; }
.formation-recovery p {
  margin:3px 0 0;
  color:#84664c;
  font-size:9px;
  line-height:1.55;
}
.formation-recovery__saved {
  display:flex;
  flex-wrap:wrap;
  gap:5px;
  margin-top:7px;
}
.formation-recovery__saved span {
  display:inline-flex;
  align-items:center;
  gap:4px;
  padding:3px 6px;
  border-radius:999px;
  color:#26715d;
  background:#edf8f4;
  font-size:8px;
  font-weight:750;
}
.formation-recovery details { margin-top:6px; color:#8a6b4f; font-size:8px; }
.formation-recovery summary { width:max-content; cursor:pointer; }
.formation-recovery code {
  display:block;
  max-height:90px;
  margin-top:5px;
  padding:6px 8px;
  overflow:auto;
  border-left:2px solid #d89b43;
  background:rgba(255,255,255,.72);
  white-space:pre-wrap;
}
.formation-recovery > button {
  min-height:34px;
  display:inline-flex;
  align-items:center;
  justify-content:center;
  gap:6px;
  padding:0 12px;
  border:1px solid #a85b1a;
  border-radius:7px;
  color:#fff;
  background:#a85b1a;
  font-size:9px;
  font-weight:800;
  cursor:pointer;
}
.formation-recovery > button:disabled { opacity:.55; cursor:wait; }
.formation-recovery > button svg.lucide-loader-circle { animation:formation-spin .9s linear infinite; }
.formation-sheet__footer {
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:14px;
  padding:8px 20px;
  border-top:1px solid #e2e5ea;
  background:#fafbfc;
}
.formation-sheet__footer > div { min-width:0; }
.formation-sheet__footer > div span {
  color:#8a93a3;
  font-size:8px;
  font-weight:800;
  letter-spacing:.08em;
}
.formation-sheet__footer p { margin:2px 0 0; color:#687386; font-size:9px; line-height:1.5; }
.formation-sheet__footer > span {
  flex:0 0 auto;
  display:inline-flex;
  align-items:center;
  gap:5px;
  color:#26715d;
  font-size:8px;
  font-weight:750;
}
@keyframes formation-spin { to { transform:rotate(360deg); } }
@keyframes formation-shimmer { to { background-position:-220% 0; } }
@media (max-width:767px) {
  .course-production-stage { padding:6px 5px 12px; }
  .formation-sheet { border-radius:10px; }
  .formation-sheet__header { padding:12px 12px 10px; }
  .formation-outline { padding:0 12px; }
  .formation-outline__nodes li { grid-template-columns:24px 11px minmax(0,1fr); }
  .formation-outline__status { grid-column:3; justify-self:start; padding:3px 0 0; }
  .formation-outline__skeleton > div { grid-template-columns:24px 11px minmax(0,1fr); }
  .formation-recovery { grid-template-columns:32px minmax(0,1fr); margin:0 12px 9px; }
  .formation-recovery > button { grid-column:1/-1; width:100%; }
  .formation-sheet__footer { align-items:flex-start; flex-direction:column; gap:6px; padding:8px 12px; }
}
@media (prefers-reduced-motion:reduce) {
  .formation-sheet svg,
  .formation-outline__skeleton b,
  .formation-outline__skeleton small { animation:none!important; }
}
</style>
