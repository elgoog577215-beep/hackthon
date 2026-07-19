<template>
  <section
    class="course-production-stage"
    :data-state="stageStatus"
    :aria-label="t('courseGeneration.production.ariaLabel', '课程生产现场')"
    aria-live="polite"
  >
    <div class="course-production-stage__grid" aria-hidden="true"></div>
    <article class="production-sheet">
      <header class="production-sheet__header">
        <div class="production-sheet__identity">
          <span class="production-sheet__mark">
            <Layers3 :size="17" />
          </span>
          <div>
            <span>{{ t('courseGeneration.production.eyebrow', 'COURSE PRODUCTION') }}</span>
            <strong>{{ courseName || t('courseGeneration.production.untitled', '新课程') }}</strong>
          </div>
        </div>
        <span class="production-sheet__status" :data-state="stageStatus">
          <LoaderCircle v-if="stageStatus === 'active'" :size="14" />
          <CirclePause v-else-if="stageStatus === 'paused'" :size="14" />
          <TriangleAlert v-else-if="stageStatus === 'error' || stageStatus === 'blocked'" :size="14" />
          <Clock3 v-else-if="stageStatus === 'review'" :size="14" />
          <Check v-else :size="14" />
          {{ statusLabel }}
        </span>
      </header>

      <div class="production-sheet__body">
        <aside class="production-sheet__number" aria-hidden="true">
          <span>{{ stageNumber }}</span>
          <i></i>
          <small>05</small>
        </aside>

        <main>
          <p class="production-sheet__stage-label">{{ stageLabel }}</p>
          <h2>{{ stageTitle }}</h2>
          <p class="production-sheet__description">{{ stageDescription }}</p>

          <section class="production-progress" :data-state="stageStatus">
            <div class="production-progress__heading">
              <span>{{ progressCaption }}</span>
              <strong>{{ progressValue }}%</strong>
            </div>
            <div class="production-progress__track" aria-hidden="true">
              <i :style="{ width: `${progressValue}%` }"></i>
            </div>
            <div class="production-progress__meta">
              <span>{{ progressDetail }}</span>
              <span v-if="showElapsed">{{ elapsedLabel }}</span>
            </div>
          </section>

          <div class="production-output">
            <div>
              <span>{{ t('courseGeneration.production.outputLabel', '本阶段产出') }}</span>
              <strong>{{ outputTitle }}</strong>
            </div>
            <ul>
              <li v-for="item in outputItems" :key="item"><FileCheck2 :size="13" />{{ item }}</li>
            </ul>
          </div>

          <div v-if="savedItems.length" class="production-saved">
            <span>{{ t('courseGeneration.production.savedLabel', '现场已保存') }}</span>
            <div>
              <span v-for="item in savedItems" :key="item"><Check :size="12" />{{ item }}</span>
            </div>
          </div>

          <div class="production-next" :data-state="stageStatus">
            <ArrowRight :size="17" />
            <div>
              <span>{{ nextLabel }}</span>
              <p>{{ nextDetail }}</p>
            </div>
          </div>

          <details v-if="technicalError" class="production-error-detail">
            <summary>{{ t('courseGeneration.production.technicalReason', '查看技术原因') }}</summary>
            <code>{{ technicalError }}</code>
          </details>

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
            <p>{{ recoveryDetail }}</p>
          </div>
        </main>
      </div>
    </article>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import {
  ArrowRight,
  BookOpenText,
  Check,
  CirclePause,
  Clock3,
  FileCheck2,
  Layers3,
  LoaderCircle,
  RotateCw,
  TriangleAlert,
} from 'lucide-vue-next'
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
  if (stageStatus.value === 'paused') return t('courseGeneration.production.pausedDescription', '当前模型调用已经停止，完整检查点与已生成草稿仍保留在这门课程中。')
  if (stageStatus.value === 'blocked') return t('courseGeneration.production.blockedDescription', '当前产物与课程真源存在冲突，需要先完成对账，再继续生产。')
  if (stageStatus.value === 'review') return t('courseGeneration.production.reviewDescription', '这一阶段需要你的判断；确认前，后续产物不会写入正式课程。')
  return descriptions.value[stageKey.value]
})

const statusLabel = computed(() => ({
  active: t('courseGeneration.production.statusWorking', '生产中'),
  completed: t('courseGeneration.lifecycle.completed', '已完成'),
  pending: t('courseGeneration.lifecycle.pending', '未开始'),
  review: t('courseGeneration.lifecycle.needsConfirmation', '待确认'),
  error: t('courseGeneration.production.statusInterrupted', '已中断'),
  paused: t('courseGeneration.production.statusPaused', '已暂停'),
  blocked: t('courseGeneration.production.statusBlocked', '需处理'),
}[stageStatus.value]))

const progressCaption = computed(() => stageStatus.value === 'error'
  ? t('courseGeneration.production.progressStopped', '中断时进度')
  : t('courseGeneration.workspace.progress', '生成进度'))
const progressDetail = computed(() => {
  if (stageStatus.value === 'error' || stageStatus.value === 'paused' || stageStatus.value === 'blocked') {
    return courseProductionRecoveryDetail(props.task)
  }
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

const outputs = computed<Record<CourseProductionStageKey, { title: string, items: string[] }>>(() => ({
  requirements: {
    title: t('courseGeneration.production.requirementsOutput', '课程生产契约'),
    items: [
      t('courseGeneration.production.outputGoal', '学习目标'),
      t('courseGeneration.production.outputDifficulty', '难度契约'),
      t('courseGeneration.production.outputSources', '资料边界'),
    ],
  },
  outline: {
    title: t('courseGeneration.production.outlineOutput', '可确认课程目录'),
    items: [
      t('courseGeneration.production.outputSections', '章节顺序'),
      t('courseGeneration.production.outputObjectives', '小节目标'),
      t('courseGeneration.production.outputScope', '课程范围'),
    ],
  },
  teaching: {
    title: t('courseGeneration.production.teachingOutput', '唯一正式全课教案'),
    items: [
      t('courseGeneration.production.outputResponsibilities', '知识职责'),
      t('courseGeneration.production.outputKnowledge', '课程知识库'),
      t('courseGeneration.production.outputBlocks', '教学块编排'),
    ],
  },
  content: {
    title: t('courseGeneration.production.contentOutput', '可审阅课程正文'),
    items: [
      t('courseGeneration.production.outputLessons', '逐节正文'),
      t('courseGeneration.production.outputPractice', '正式练习'),
      t('courseGeneration.production.outputBindings', '同源绑定'),
    ],
  },
  release: {
    title: t('courseGeneration.production.releaseOutput', '正式学习课程'),
    items: [
      t('courseGeneration.production.outputGuards', '结构门禁'),
      t('courseGeneration.production.outputReceipt', '发布回执'),
      t('courseGeneration.production.outputWorkspace', '学习现场'),
    ],
  },
}))
const outputTitle = computed(() => outputs.value[stageKey.value].title)
const outputItems = computed(() => outputs.value[stageKey.value].items)

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

const nextLabel = computed(() => stageStatus.value === 'review'
  ? t('courseGeneration.production.yourTurn', '轮到你确认')
  : stageStatus.value === 'error' || stageStatus.value === 'paused'
    ? t('courseGeneration.production.resumeFromHere', '从这里继续')
    : t('courseGeneration.production.nextLabel', '接下来'))
const nextDetails = computed<Record<CourseProductionStageKey, string>>(() => ({
  requirements: t('courseGeneration.production.requirementsNext', '需求确认后立即生成课程目录；不会再增加额外确认门。'),
  outline: t('courseGeneration.production.outlineNext', '目录确认后，系统自动生成全课教案、知识库与各节正文。'),
  teaching: t('courseGeneration.production.teachingNext', '全课教案汇编通过后，正文会按依赖波次并行生成。'),
  content: t('courseGeneration.production.contentNext', '所有小节完成后进入确定性发布检查，不追加 AI 返工循环。'),
  release: t('courseGeneration.production.releaseNext', '确认发布后，当前页面会原地切换为正式学习现场。'),
}))
const nextDetail = computed(() => {
  if (stageStatus.value === 'error' || stageStatus.value === 'paused' || stageStatus.value === 'blocked') {
    return courseProductionRecoveryDetail(props.task)
  }
  return nextDetails.value[stageKey.value]
})

const technicalError = computed(() => String(props.task?.error || '').trim())
const friendlyError = computed(() => {
  const error = technicalError.value.toLowerCase()
  if (/authentication|credential|api[_ -]?key/.test(error)) {
    return t('courseGeneration.production.authError', 'AI 服务暂时无法完成身份校验。课程需求与已有产物没有丢失，修复服务配置后可从当前阶段继续。')
  }
  if (/timeout|timed out/.test(error)) {
    return t('courseGeneration.production.timeoutError', '本阶段等待 AI 服务超时。已经保存的完整产物不会重做，可以从当前检查点继续。')
  }
  if (/unavailable|connection|network/.test(error)) {
    return t('courseGeneration.production.unavailableError', 'AI 服务暂时不可用。课程现场已经保留，服务恢复后可以继续当前阶段。')
  }
  return t('courseGeneration.production.genericError', '本阶段没有完成，但课程需求、资料处理结果和已生成产物仍然保留。')
})
const resumeLabel = computed(() => props.task?.status === 'paused'
  ? t('courseGeneration.production.continueAction', '继续课程生产')
  : t('courseGeneration.production.retryAction', '重试当前阶段'))
const recoveryDetail = computed(() => courseProductionRecoveryDetail(props.task))
</script>

<style scoped>
.course-production-stage { position:relative; min-height:0; flex:1; display:grid; place-items:center; overflow:auto; padding:clamp(28px,5vw,74px) clamp(18px,5vw,76px) 96px; background:radial-gradient(circle at 78% 18%,rgba(99,102,241,.08),transparent 28%),linear-gradient(145deg,#fbfcff 0%,#f6f7fb 100%); }
.course-production-stage__grid { position:absolute; inset:0; opacity:.42; pointer-events:none; background-image:linear-gradient(rgba(71,85,105,.045) 1px,transparent 1px),linear-gradient(90deg,rgba(71,85,105,.045) 1px,transparent 1px); background-size:32px 32px; mask-image:linear-gradient(to bottom,rgba(0,0,0,.7),transparent 82%); }
.production-sheet { position:relative; z-index:1; width:min(920px,100%); overflow:hidden; border:1px solid rgba(215,220,233,.9); border-radius:18px; background:rgba(255,255,255,.94); box-shadow:0 24px 70px rgba(36,46,74,.11),0 2px 8px rgba(36,46,74,.04); }
.production-sheet::before { content:""; position:absolute; top:0; left:0; right:0; height:3px; background:linear-gradient(90deg,#5756d9,#8d86f7 42%,#c9c6ff); }
.production-sheet__header { min-height:66px; display:flex; align-items:center; justify-content:space-between; gap:20px; padding:14px 20px; border-bottom:1px solid #e8ebf2; }
.production-sheet__identity { min-width:0; display:flex; align-items:center; gap:11px; }
.production-sheet__mark { width:36px; height:36px; flex:0 0 36px; display:grid; place-items:center; border:1px solid #dcdfff; border-radius:10px; color:#5552d9; background:#f4f3ff; }
.production-sheet__identity > div { min-width:0; display:flex; flex-direction:column; }
.production-sheet__identity span:not(.production-sheet__mark) { color:#7c8497; font:750 8px/1.2 ui-monospace,SFMono-Regular,monospace; letter-spacing:.14em; }
.production-sheet__identity strong { max-width:min(460px,52vw); margin-top:3px; overflow:hidden; color:#273144; font-size:12px; text-overflow:ellipsis; white-space:nowrap; }
.production-sheet__status { flex:0 0 auto; display:inline-flex; align-items:center; gap:6px; padding:6px 9px; border-radius:999px; color:#4548bd; background:#f0f1ff; font-size:9px; font-weight:800; }
.production-sheet__status[data-state="active"] svg { animation:production-spin .9s linear infinite; }
.production-sheet__status[data-state="error"],.production-sheet__status[data-state="blocked"] { color:#b54708; background:#fff4e5; }
.production-sheet__status[data-state="paused"] { color:#475467; background:#f2f4f7; }
.production-sheet__status[data-state="review"] { color:#087a5b; background:#ecfdf5; }
.production-sheet__body { display:grid; grid-template-columns:96px minmax(0,1fr); }
.production-sheet__number { display:flex; flex-direction:column; align-items:center; padding:36px 18px; border-right:1px solid #e8ebf2; background:linear-gradient(180deg,#fafbfe,#f6f7fb); }
.production-sheet__number span { color:#4f46e5; font:650 34px/1 Georgia,"Noto Serif SC",serif; }
.production-sheet__number i { width:1px; min-height:94px; flex:1; margin:14px 0; background:linear-gradient(#c8ccf4,transparent); }
.production-sheet__number small { color:#a1a8b7; font:700 9px/1 ui-monospace,SFMono-Regular,monospace; }
.production-sheet main { min-width:0; padding:38px clamp(26px,4vw,54px) 42px; }
.production-sheet__stage-label { margin:0 0 8px; color:#5a5fd0; font-size:9px; font-weight:850; letter-spacing:.08em; }
.production-sheet h2 { margin:0; color:#1c2637; font:700 clamp(26px,3vw,38px)/1.16 Georgia,"Noto Serif SC",serif; letter-spacing:-.025em; }
.production-sheet__description { max-width:680px; margin:12px 0 0; color:#697386; font-size:12px; line-height:1.75; }
.production-progress { margin-top:25px; padding:15px 0 17px; border-top:1px solid #e7eaf1; border-bottom:1px solid #e7eaf1; }
.production-progress__heading,.production-progress__meta { display:flex; align-items:center; justify-content:space-between; gap:16px; }
.production-progress__heading span { color:#4b5565; font-size:10px; font-weight:750; }
.production-progress__heading strong { color:#4f46e5; font:750 18px/1 ui-monospace,SFMono-Regular,monospace; }
.production-progress__track { height:5px; margin:10px 0 8px; overflow:hidden; border-radius:999px; background:#eceef7; }
.production-progress__track i { display:block; height:100%; min-width:4px; border-radius:inherit; background:linear-gradient(90deg,#5b58e3,#8a82f4); transition:width .3s ease; }
.production-progress[data-state="error"] .production-progress__track i,.production-progress[data-state="blocked"] .production-progress__track i { background:linear-gradient(90deg,#d97706,#f2b94b); }
.production-progress[data-state="paused"] .production-progress__track i { background:#98a2b3; }
.production-progress__meta { align-items:flex-start; color:#8a93a4; font-size:9px; line-height:1.5; }
.production-progress__meta span:first-child { min-width:0; flex:1; }
.production-progress__meta span:last-child { flex:0 0 auto; font-family:ui-monospace,SFMono-Regular,monospace; }
.production-output { display:grid; grid-template-columns:minmax(150px,.7fr) minmax(300px,1.3fr); align-items:center; gap:24px; padding:19px 0; border-bottom:1px solid #e7eaf1; }
.production-output > div { display:flex; flex-direction:column; }
.production-output > div span,.production-saved > span,.production-next span { color:#8a93a4; font-size:8px; font-weight:800; letter-spacing:.06em; }
.production-output > div strong { margin-top:4px; color:#303b4e; font-size:12px; }
.production-output ul { display:flex; flex-wrap:wrap; justify-content:flex-end; gap:7px; margin:0; padding:0; list-style:none; }
.production-output li { display:inline-flex; align-items:center; gap:5px; padding:6px 8px; border:1px solid #e3e6ef; border-radius:7px; color:#5e687a; background:#fafbfc; font-size:9px; }
.production-output li svg { color:#6a68dd; }
.production-saved { display:grid; grid-template-columns:96px minmax(0,1fr); align-items:center; gap:16px; padding:14px 0; border-bottom:1px solid #e7eaf1; }
.production-saved > div { display:flex; flex-wrap:wrap; gap:8px; }
.production-saved > div span { display:inline-flex; align-items:center; gap:4px; color:#087a5b; font-size:9px; font-weight:700; }
.production-saved > div svg { padding:1px; border-radius:50%; color:#fff; background:#10a37f; }
.production-next { display:grid; grid-template-columns:32px minmax(0,1fr); gap:10px; margin-top:20px; padding:12px 14px; border-left:2px solid #7b78e7; background:#f7f7ff; }
.production-next > svg { width:28px; height:28px; padding:7px; border-radius:8px; color:#5552d9; background:#eaeaff; }
.production-next p { margin:3px 0 0; color:#596579; font-size:10px; line-height:1.55; }
.production-next[data-state="error"],.production-next[data-state="blocked"] { border-left-color:#d97706; background:#fffaf0; }
.production-next[data-state="error"] > svg,.production-next[data-state="blocked"] > svg { color:#b54708; background:#fff0d5; }
.production-error-detail { margin-top:12px; color:#7b8495; font-size:9px; }
.production-error-detail summary { width:max-content; cursor:pointer; }
.production-error-detail code { display:block; margin-top:8px; padding:8px 10px; overflow:auto; border-radius:6px; color:#8a3b12; background:#fff7ed; font-size:9px; white-space:pre-wrap; }
.production-actions { display:flex; align-items:center; gap:14px; margin-top:18px; }
.production-actions button { min-height:38px; flex:0 0 auto; display:inline-flex; align-items:center; justify-content:center; gap:7px; padding:0 15px; border:0; border-radius:9px; color:#fff; background:#5552df; box-shadow:0 8px 20px rgba(79,70,229,.2); font-size:10px; font-weight:800; cursor:pointer; transition:transform .16s ease,box-shadow .16s ease,background .16s ease; }
.production-actions button:hover:not(:disabled) { transform:translateY(-1px); background:#4542cb; box-shadow:0 11px 24px rgba(79,70,229,.24); }
.production-actions button:disabled { opacity:.58; cursor:wait; }
.production-actions button:disabled svg:first-child { animation:production-spin .9s linear infinite; }
.production-actions button.secondary { color:#525b6d; border:1px solid #d9deea; background:#fff; box-shadow:none; }
.production-actions button.secondary:hover:not(:disabled) { color:#4f46e5; border-color:#c9cbfa; background:#f8f8ff; box-shadow:none; }
.production-actions p { margin:0; color:#7b8495; font-size:9px; line-height:1.5; }
@keyframes production-spin { to { transform:rotate(360deg); } }
@media (max-width:767px) {
  .course-production-stage { align-items:start; padding:18px 12px 92px; }
  .course-production-stage__grid { background-size:24px 24px; }
  .production-sheet { border-radius:14px; }
  .production-sheet__header { min-height:58px; padding:11px 12px; }
  .production-sheet__identity strong { max-width:185px; }
  .production-sheet__status { padding:5px 7px; }
  .production-sheet__body { grid-template-columns:52px minmax(0,1fr); }
  .production-sheet__number { padding:25px 10px; }
  .production-sheet__number span { font-size:24px; }
  .production-sheet main { padding:27px 16px 30px; }
  .production-sheet h2 { font-size:25px; }
  .production-sheet__description { font-size:11px; }
  .production-output { grid-template-columns:1fr; gap:11px; }
  .production-output ul { justify-content:flex-start; }
  .production-saved { grid-template-columns:1fr; gap:8px; }
  .production-actions { align-items:flex-start; flex-direction:column; }
  .production-actions button { width:100%; }
}
@media (prefers-reduced-motion:reduce) {
  .production-sheet__status svg,.production-actions button svg,.production-progress__track i { animation:none!important; transition:none; }
}
</style>
