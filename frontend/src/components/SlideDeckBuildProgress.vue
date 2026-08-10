<template>
  <section
    class="slide-build-progress"
    :data-variant="variant"
    :data-stage="stage"
    data-testid="slide-build-progress"
    aria-live="polite"
  >
    <header class="slide-build-progress__header">
      <div class="slide-build-progress__current">
        <LoaderCircle :size="18" class="spinning" aria-hidden="true" />
        <div>
          <small>课件生成进度</small>
          <strong>{{ currentStageLabel }}</strong>
        </div>
      </div>
      <b>{{ normalizedProgress }}%</b>
    </header>

    <div
      class="slide-build-progress__bar"
      role="progressbar"
      aria-label="课件生成进度"
      :aria-valuenow="normalizedProgress"
      aria-valuemin="0"
      aria-valuemax="100"
    >
      <i :style="{ width: `${normalizedProgress}%` }"></i>
    </div>

    <p class="slide-build-progress__detail">{{ currentDetailLabel }}</p>

    <ol class="slide-build-progress__steps" aria-label="课件生成步骤">
      <li
        v-for="(step, index) in steps"
        :key="step.key"
        data-build-step
        :data-state="stepState(index)"
      >
        <span class="slide-build-progress__step-mark">
          <CircleCheck v-if="stepState(index) === 'done'" :size="14" aria-hidden="true" />
          <LoaderCircle v-else-if="stepState(index) === 'active'" :size="14" class="spinning" aria-hidden="true" />
          <b v-else>{{ index + 1 }}</b>
        </span>
        <div>
          <strong>{{ step.label }}</strong>
          <small data-step-description>{{ step.description }}</small>
        </div>
      </li>
    </ol>

    <section
      class="slide-build-progress__tasks"
      :aria-label="`当前阶段具体任务：${currentStep.label}`"
    >
      <header>
        <div>
          <small>当前阶段具体任务 · 第 {{ activeStepIndex + 1 }} / {{ steps.length }} 步</small>
          <strong>{{ currentStep.label }}</strong>
        </div>
        <b>{{ completedTaskCount }} / {{ currentTasks.length }} 项完成</b>
      </header>
      <ul data-testid="build-task-list">
        <li
          v-for="(task, index) in currentTasks"
          :key="task"
          data-build-task
          :data-state="taskState(index)"
          :aria-current="taskState(index) === 'active' ? 'step' : undefined"
        >
          <span class="slide-build-progress__task-mark">
            <CircleCheck v-if="taskState(index) === 'done'" :size="13" aria-hidden="true" />
            <LoaderCircle v-else-if="taskState(index) === 'active'" :size="13" class="spinning" aria-hidden="true" />
            <i v-else aria-hidden="true"></i>
          </span>
          <div>
            <strong>{{ task }}</strong>
            <small v-if="taskState(index) === 'active'" data-current-activity>{{ currentDetailLabel }}</small>
          </div>
          <em>{{ taskStateLabel(index) }}</em>
        </li>
      </ul>
    </section>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { CircleCheck, LoaderCircle } from 'lucide-vue-next'
import type { SlideDeckBuildDetail } from '../stores/teachingRepresentations'

interface BuildStep {
  key: string
  label: string
  description: string
  tasks: readonly string[]
}

const props = withDefaults(defineProps<{
  progress: number
  stage: string
  detail?: SlideDeckBuildDetail | null
  estimatedSlideCount?: number
  variant?: 'toolbar' | 'initial' | 'embedded'
}>(), {
  detail: null,
  estimatedSlideCount: 0,
  variant: 'embedded',
})

const steps: readonly BuildStep[] = [
  {
    key: 'source',
    label: '读取课程源',
    description: '读取资料、解析正文并核验完整性',
    tasks: ['读取课程资料与教学目标', '解析正文结构和知识单元', '核验来源与内容完整性'],
  },
  {
    key: 'story',
    label: '设计教学主线',
    description: '提取目标、组织知识并确定教学顺序',
    tasks: ['提取课程目标与重点', '组织知识关系和先后顺序', '确定整套课件教学主线'],
  },
  {
    key: 'chapter',
    label: '编排章节场景',
    description: '划分章节、编排场景并设置讲解节奏',
    tasks: ['划分章节主题与边界', '编排章节教学场景', '设置讲解节奏与过渡'],
  },
  {
    key: 'page-plan',
    label: '规划页面结构',
    description: '估算页数、分配内容并确定页面用途',
    tasks: ['估算课件页数与章节占比', '分配章节内容和知识点', '确定每页用途与分页结构'],
  },
  {
    key: 'layout',
    label: '匹配语义版式',
    description: '识别内容类型、选择版式并校验密度',
    tasks: ['识别每页内容类型', '选择对应的语义版式', '校验信息密度与层级'],
  },
  {
    key: 'visual',
    label: '准备视觉素材',
    description: '规划图示、准备素材并编译页面资源',
    tasks: ['规划重点页面图示类型', '准备图片、图标与图表素材', '编译并绑定页面视觉资源'],
  },
  {
    key: 'build',
    label: '逐页生成课件',
    description: '读取页面计划、生成内容并逐页写入',
    tasks: ['读取当前页面计划', '生成页面内容与讲者备注', '写入并校验全部页面'],
  },
  {
    key: 'repair',
    label: '补图与语义修复',
    description: '检索图片、核验来源并修复内容缺口',
    tasks: ['识别需要配图的页面', '检索并去重候选图片', '核验图片来源并修复缺口'],
  },
  {
    key: 'quality',
    label: '内容视觉质检',
    description: '检查知识覆盖、文字密度与版式安全',
    tasks: ['检查知识点与目标覆盖', '检查文字密度和可读性', '检查版式安全并标记问题页'],
  },
  {
    key: 'publish',
    label: '渲染与发布',
    description: '渲染成品、修复问题并准备下载',
    tasks: ['渲染全部页面', '修复溢出、遮挡与错位', '发布可下载课件'],
  },
]

const stageLabels: Record<string, string> = {
  fragmenting: '正在切分并校验课程原文',
  planning: '正在准备课程结构',
  story_plan: '正在梳理整套课件的教学主线',
  chapter_plan: '正在编排章节叙事',
  episode_progress: '正在生成教学场景',
  layout_plan: '正在匹配语义版式',
  slide_plan: '正在规划整套页面',
  visual_plan: '正在规划课件视觉',
  asset_compilation: '正在准备课件视觉素材',
  bundle_plan: '正在按章节拆分课件',
  bundle_part_build: '正在逐册生成课件',
  slide_build: '正在逐页生成教学内容',
  reviewing: '正在审核页面分配',
  quality: '正在检查课堂可用性',
  visual_quality: '正在检查视觉质量',
  semantic_repair: '正在修复内容完整性与分页',
  image_search: '正在检索并核验教学图片',
  render_review: '正在渲染复核成品',
  render_repair: '正在修复导出版式问题',
  repair_progress: '正在定向修复问题页面',
  complete: '课件生成完成',
}

const stageStepIndex: Record<string, number> = {
  fragmenting: 0,
  planning: 0,
  story_plan: 1,
  chapter_plan: 2,
  episode_progress: 2,
  slide_plan: 3,
  bundle_plan: 3,
  layout_plan: 4,
  visual_plan: 5,
  asset_compilation: 5,
  bundle_part_build: 6,
  slide_build: 6,
  semantic_repair: 7,
  image_search: 7,
  reviewing: 8,
  quality: 8,
  visual_quality: 8,
  render_review: 9,
  render_repair: 9,
  repair_progress: 9,
  complete: 9,
}

const stageTaskIndex: Record<string, number> = {
  planning: 0,
  fragmenting: 1,
  story_plan: 1,
  chapter_plan: 0,
  episode_progress: 1,
  slide_plan: 1,
  bundle_plan: 2,
  layout_plan: 1,
  visual_plan: 0,
  asset_compilation: 1,
  bundle_part_build: 0,
  slide_build: 1,
  image_search: 1,
  semantic_repair: 2,
  reviewing: 0,
  quality: 1,
  visual_quality: 2,
  render_review: 0,
  render_repair: 1,
  repair_progress: 1,
  complete: 2,
}

const eventTaskIndex: Record<string, number> = {
  planning: 0,
  fragmenting: 1,
  story_plan: 1,
  chapter_plan: 0,
  episode_progress: 1,
  deck_plan: 1,
  layout_plan: 1,
  visual_plan: 0,
  asset_progress: 1,
  asset_ready: 2,
  bundle_part_build: 0,
  slide_upsert: 1,
  image_search: 1,
  semantic_repair: 2,
  slide_quality: 1,
  visual_quality: 2,
  render_review: 0,
  render_repair: 1,
  repair_progress: 1,
  build_complete: 2,
}

const normalizedProgress = computed(() => (
  Math.max(0, Math.min(100, Math.round(Number(props.progress || 0))))
))

const activeStepIndex = computed(() => {
  if (stageStepIndex[props.stage] != null) return stageStepIndex[props.stage]!
  if (normalizedProgress.value >= 98) return 9
  if (normalizedProgress.value >= 96) return 8
  if (normalizedProgress.value >= 93) return 7
  if (normalizedProgress.value >= 22) return 6
  if (normalizedProgress.value >= 18) return 5
  if (normalizedProgress.value >= 14) return 4
  if (normalizedProgress.value >= 10) return 3
  if (normalizedProgress.value >= 6) return 2
  if (normalizedProgress.value >= 2) return 1
  return 0
})

const currentStep = computed(() => steps[activeStepIndex.value] || steps[0]!)
const currentTasks = computed(() => currentStep.value.tasks)

const currentStageLabel = computed(() => (
  stageLabels[props.stage] || props.detail?.message || '正在生成课件'
))

const currentDetailLabel = computed(() => {
  const detail = props.detail
  const completed = Number(detail?.completed || 0)
  const total = Number(detail?.total || props.estimatedSlideCount || 0)
  const itemTitle = String(detail?.itemTitle || '')
  const itemId = String(detail?.itemId || '')

  if (props.stage === 'slide_build') {
    const pagePosition = completed && total
      ? `第 ${completed} / ${total} 页`
      : completed
        ? `已生成 ${completed} 页`
        : '正在生成第一页'
    return itemTitle ? `${pagePosition} · ${itemTitle}` : pagePosition
  }
  if (props.stage === 'asset_compilation') {
    return completed && total
      ? `正在准备视觉素材 ${completed} / ${total}`
      : '正在为重点页面准备图示与视觉素材'
  }
  if (props.stage === 'chapter_plan' && itemTitle) return `当前章节：${itemTitle}`
  if (props.stage === 'slide_plan' && total) return `正在为 ${total} 页分配课程内容与分页结构`
  if (props.stage === 'layout_plan' && total) return `已为 ${total} 页建立内容与版式计划`
  if (props.stage === 'visual_plan' && total) return `正在为 ${total} 页确定图示类型与视觉锚点`
  if (props.stage === 'bundle_part_build') {
    const partIndex = Number(detail?.partIndex || 0)
    const partCount = Number(detail?.partCount || 0)
    if (partIndex && partCount) return `正在生成第 ${partIndex} / ${partCount} 册${itemTitle ? ` · ${itemTitle}` : ''}`
  }
  if (props.stage === 'image_search') {
    return itemTitle || itemId
      ? `正在为「${itemTitle || itemId}」查找可用教学图片`
      : '正在查找、去重并核验教学图片来源'
  }
  if (props.stage === 'render_repair' || props.stage === 'repair_progress') {
    const attempt = Number(detail?.repairAttempt || 0)
    return attempt ? `正在执行第 ${attempt} 轮版式修复` : '正在修复渲染检查发现的问题'
  }
  if (props.stage === 'semantic_repair') {
    const attempt = Number(detail?.repairAttempt || 0)
    return attempt
      ? `已检查 ${total || '全部'} 页，正在执行第 ${attempt} 轮语义与分页修复`
      : `正在检查 ${total || '全部'} 页的内容完整性与分页`
  }
  if ((props.stage === 'quality' || props.stage === 'visual_quality') && total) {
    return `正在逐页检查 ${total} 页的内容覆盖、文字密度与版式安全`
  }
  if (props.stage === 'render_review' && total) return `正在渲染并复核 ${total} 页最终成品`
  if (detail?.message) return detail.message

  return steps[activeStepIndex.value]?.description || '正在处理当前步骤'
})

const activeTaskIndex = computed(() => {
  const taskCount = currentTasks.value.length
  if (!taskCount) return 0
  if (normalizedProgress.value >= 100 || props.stage === 'complete') return taskCount - 1

  const completed = Number(props.detail?.completed || 0)
  const total = Number(props.detail?.total || props.estimatedSlideCount || 0)
  let index = eventTaskIndex[String(props.detail?.event || '')]
    ?? stageTaskIndex[props.stage]
    ?? 0

  if (
    total > 0
    && completed >= total
    && ['slide_build', 'image_search', 'asset_compilation'].includes(props.stage)
  ) index = taskCount - 1

  return Math.max(0, Math.min(taskCount - 1, index))
})

const completedTaskCount = computed(() => (
  normalizedProgress.value >= 100
    ? currentTasks.value.length
    : activeTaskIndex.value
))

function taskState(index: number) {
  if (normalizedProgress.value >= 100) return 'done'
  if (index < activeTaskIndex.value) return 'done'
  if (index === activeTaskIndex.value) return 'active'
  return 'pending'
}

function taskStateLabel(index: number) {
  const state = taskState(index)
  if (state === 'done') return '已完成'
  if (state === 'active') return '进行中'
  return '待执行'
}

function stepState(index: number) {
  if (normalizedProgress.value >= 100) return 'done'
  if (index < activeStepIndex.value) return 'done'
  if (index === activeStepIndex.value) return 'active'
  return 'pending'
}
</script>

<style scoped>
.slide-build-progress {
  --build-accent:#2556d8;
  --build-accent-soft:#eaf0ff;
  min-width:0;
  padding:11px 18px 12px;
  color:#243247;
  border-bottom:1px solid #dce3ed;
  background:rgba(255,255,255,.98);
  box-shadow:0 7px 18px rgba(31,45,68,.06);
}
.slide-build-progress[data-variant="initial"] {
  width:min(660px,84vw);
  box-sizing:border-box;
  margin-top:24px;
  padding:18px 20px 20px;
  border:1px solid #d8e1ed;
  border-radius:15px;
  text-align:left;
  box-shadow:0 18px 44px rgba(31,55,92,.1);
}
.slide-build-progress__header { display:flex; align-items:center; justify-content:space-between; gap:16px; }
.slide-build-progress__current { min-width:0; display:flex; align-items:center; gap:9px; color:var(--build-accent); }
.slide-build-progress__current > div { min-width:0; display:flex; flex-direction:column; gap:1px; }
.slide-build-progress__current small { color:#718096; font-size:9px; font-weight:800; letter-spacing:.08em; }
.slide-build-progress__current strong { overflow:hidden; color:#243247; font-size:12px; line-height:1.35; text-overflow:ellipsis; white-space:nowrap; }
.slide-build-progress__header > b { color:var(--build-accent); font:800 12px/1 "Aptos Mono","SFMono-Regular",monospace; }
.slide-build-progress__bar { height:4px; overflow:hidden; margin-top:9px; border-radius:99px; background:#e5eaf1; }
.slide-build-progress__bar i { display:block; height:100%; border-radius:inherit; background:linear-gradient(90deg,#2556d8,#0b8c82); transition:width .28s ease; }
.slide-build-progress__detail { overflow:hidden; margin:7px 0 0; color:#536174; font-size:10px; line-height:1.4; text-overflow:ellipsis; white-space:nowrap; }
.slide-build-progress__steps { display:grid; grid-template-columns:repeat(10,minmax(0,1fr)); gap:6px; margin:10px 0 0; padding:0; list-style:none; }
.slide-build-progress__steps li { min-width:0; display:grid; grid-template-columns:22px minmax(0,1fr); align-items:center; gap:6px; color:#8a95a5; }
.slide-build-progress__step-mark { width:20px; height:20px; display:grid; place-items:center; border:1px solid #d9dfe7; border-radius:50%; color:#8894a5; background:#f7f8fa; }
.slide-build-progress__step-mark b { font-size:9px; }
.slide-build-progress__steps li > div { min-width:0; display:flex; flex-direction:column; }
.slide-build-progress__steps strong { overflow:hidden; font-size:9px; line-height:1.25; text-overflow:ellipsis; white-space:nowrap; }
.slide-build-progress__steps small { display:block; overflow:hidden; min-height:20px; margin-top:2px; color:#7b8797; font-size:8px; line-height:1.25; }
.slide-build-progress__steps li[data-state="done"] { color:#16837a; }
.slide-build-progress__steps li[data-state="done"] .slide-build-progress__step-mark { color:#fff; border-color:#16837a; background:#16837a; }
.slide-build-progress__steps li[data-state="active"] { color:var(--build-accent); }
.slide-build-progress__steps li[data-state="active"] .slide-build-progress__step-mark { color:#fff; border-color:var(--build-accent); background:var(--build-accent); box-shadow:0 0 0 4px var(--build-accent-soft); }
.slide-build-progress__steps li[data-state="active"] small { color:#536174; }
.slide-build-progress__tasks { margin-top:10px; padding:9px 11px 10px; border:1px solid #dfe6ef; border-radius:10px; background:#f8fafc; }
.slide-build-progress__tasks > header { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; }
.slide-build-progress__tasks > header > div { min-width:0; display:flex; flex-direction:column; gap:1px; }
.slide-build-progress__tasks > header small { color:#7a8798; font-size:8px; font-weight:800; letter-spacing:.04em; }
.slide-build-progress__tasks > header strong { color:#2d3b50; font-size:10px; }
.slide-build-progress__tasks > header > b { flex:none; color:#647287; font:700 9px/1.4 "Aptos Mono","SFMono-Regular",monospace; }
.slide-build-progress__tasks ul { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:7px; margin:7px 0 0; padding:0; list-style:none; }
.slide-build-progress__tasks li { min-width:0; display:grid; grid-template-columns:17px minmax(0,1fr) auto; align-items:start; gap:6px; padding:7px 8px; border:1px solid #e2e8f0; border-radius:8px; color:#7e8998; background:#fff; }
.slide-build-progress__task-mark { width:15px; height:15px; display:grid; place-items:center; margin-top:1px; color:#9aa5b4; }
.slide-build-progress__task-mark i { width:7px; height:7px; border:1px solid #b9c2ce; border-radius:50%; }
.slide-build-progress__tasks li > div { min-width:0; display:flex; flex-direction:column; }
.slide-build-progress__tasks li strong { overflow:hidden; font-size:9px; line-height:1.35; text-overflow:ellipsis; white-space:nowrap; }
.slide-build-progress__tasks li small { overflow:hidden; margin-top:2px; color:#536174; font-size:8px; line-height:1.35; text-overflow:ellipsis; white-space:nowrap; }
.slide-build-progress__tasks li em { padding:2px 5px; border-radius:99px; color:#8994a3; background:#f1f4f7; font-size:8px; font-style:normal; line-height:1.2; white-space:nowrap; }
.slide-build-progress__tasks li[data-state="done"] { color:#16837a; border-color:#d4ebe7; background:#f5fbfa; }
.slide-build-progress__tasks li[data-state="done"] .slide-build-progress__task-mark { color:#16837a; }
.slide-build-progress__tasks li[data-state="done"] em { color:#147970; background:#dff3ef; }
.slide-build-progress__tasks li[data-state="active"] { color:#244fc3; border-color:#b9c9f8; background:#f5f7ff; box-shadow:0 0 0 2px rgba(37,86,216,.06); }
.slide-build-progress__tasks li[data-state="active"] .slide-build-progress__task-mark { color:#2556d8; }
.slide-build-progress__tasks li[data-state="active"] em { color:#244fc3; background:#e4eaff; }
.slide-build-progress[data-variant="initial"] .slide-build-progress__current small { font-size:10px; }
.slide-build-progress[data-variant="initial"] .slide-build-progress__current strong { font-size:14px; }
.slide-build-progress[data-variant="initial"] .slide-build-progress__detail { font-size:11px; }
.slide-build-progress[data-variant="initial"] .slide-build-progress__steps { grid-template-columns:repeat(5,minmax(0,1fr)); gap:14px 10px; margin-top:15px; }
.slide-build-progress[data-variant="initial"] .slide-build-progress__steps strong { font-size:10px; }
.spinning { animation:build-progress-spin .8s linear infinite; }
@keyframes build-progress-spin { to { transform:rotate(360deg); } }
@media (max-width:1180px) and (min-width:841px) {
  .slide-build-progress:not([data-variant="initial"]) .slide-build-progress__steps { grid-template-columns:repeat(5,minmax(0,1fr)); gap:10px 6px; }
}
@media (max-width:840px) {
  .slide-build-progress { padding-right:12px; padding-left:12px; }
  .slide-build-progress__steps,.slide-build-progress[data-variant="initial"] .slide-build-progress__steps { display:flex; gap:5px; overflow-x:auto; padding:4px 4px 7px; scroll-snap-type:x proximity; }
  .slide-build-progress__steps li { min-width:108px; grid-template-columns:1fr; justify-items:center; text-align:center; scroll-snap-align:start; }
  .slide-build-progress__steps small { display:none !important; }
  .slide-build-progress__tasks ul { grid-template-columns:1fr; }
}
</style>
