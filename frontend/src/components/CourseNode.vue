<template>
  <section :id="`node-${node.node_id}`" class="course-node" :data-level="node.node_level">
    <template v-if="node.node_level === 1">
      <header class="course-opening">
        <span>{{ t('courseBlocks.courseUnit', '课程单元') }}</span>
        <h1>{{ cleanName }}</h1>
        <p v-if="node.learning_objective">{{ node.learning_objective }}</p>
      </header>
      <div v-if="node.node_content" class="opening-content" :style="contentStyle">
        <CourseBlockStream :node="node" :content="node.node_content" :records="records" :search-words="searchWords" :is-streaming="isStreaming" :can-improve-blocks="canImproveBlocks" @open-record="emit('openRecord', $event)" @improve-block="emit('improveBlock', $event)" @start-practice="emit('startPractice', node, $event)" />
      </div>
      <div v-else-if="generationPreview" class="generation-placeholder" :data-state="generationState">
        <component :is="generationIcon" :size="16" :class="{ spinning: generationState === 'generating' }" />
        <span>{{ generationLabel }}</span>
      </div>
      <AdaptiveLearningBlock v-for="block in adaptiveBlocks" v-if="!generationPreview" :key="block.adaptive_block_id" :block="block" :practice-available="hasFormalPractice" @verify="emit('startPractice', node)" />
    </template>

    <template v-else-if="node.node_level === 2">
      <header class="chapter-heading">
        <div class="chapter-meta">
          <span class="chapter-badge">
            <BookOpenText :size="13" />
            {{ t('courseBlocks.chapter', '章节') }}
          </span>
          <span class="chapter-index">{{ String(index + 1).padStart(2, '0') }}</span>
        </div>
        <div v-if="generationPreview || nodeProgress" class="chapter-status">
          <span v-if="generationPreview" class="generation-status" :data-state="generationState">
            <component :is="generationIcon" :size="13" :class="{ spinning: generationState === 'generating' }" />
            {{ generationLabel }}
          </span>
          <template v-else>
            <span :data-state="nodeProgress?.reading_status">{{ readingStatusLabel }}</span>
            <span :data-state="nodeProgress?.mastery_status">{{ masteryStatusLabel }}</span>
          </template>
        </div>
        <div class="chapter-copy">
          <h2>{{ node.node_name }}</h2>
          <div class="chapter-divider" aria-hidden="true">
            <span></span><i></i><b></b>
          </div>
          <p v-if="node.learning_objective">{{ node.learning_objective }}</p>
        </div>
      </header>

      <div v-if="node.node_content" class="chapter-content" :style="contentStyle">
        <CourseBlockStream :node="node" :content="node.node_content" :records="records" :search-words="searchWords" :is-streaming="isStreaming" :can-improve-blocks="canImproveBlocks" @open-record="emit('openRecord', $event)" @improve-block="emit('improveBlock', $event)" @start-practice="emit('startPractice', node, $event)" />
      </div>

      <div v-else-if="generationPreview" class="generation-placeholder" :data-state="generationState">
        <component :is="generationIcon" :size="16" :class="{ spinning: generationState === 'generating' }" />
        <span>{{ generationLabel }}</span>
      </div>

      <AdaptiveLearningBlock v-for="block in adaptiveBlocks" v-if="!generationPreview" :key="block.adaptive_block_id" :block="block" :practice-available="hasFormalPractice" @verify="emit('startPractice', node)" />

      <button
        v-if="hasFormalPractice && !generationPreview"
        :id="`practice-block-${node.node_id}`"
        type="button"
        class="task-launcher"
        aria-haspopup="dialog"
        @click="emit('startPractice', node)"
      >
        <span class="task-icon"><ClipboardCheck :size="17" /></span>
        <span class="task-copy">
          <span class="task-meta">
            {{ t('courseBlocks.chapterPractice', '章节练习') }} · {{ practiceCountLabel }}
          </span>
          <strong>{{ practicePreview || node.node_name }}</strong>
          <small>{{ t('courseBlocks.practiceHint', '从正式题目进入，作答进度会自动保存') }}</small>
        </span>
        <span class="task-action">
          {{ t('courseBlocks.practiceOpen', '打开练习') }}
          <ArrowRight :size="15" />
        </span>
      </button>
    </template>

    <template v-else>
      <header class="section-heading">
        <span></span>
        <h3>{{ node.node_name }}</h3>
        <small v-if="generationPreview" class="section-generation-status" :data-state="generationState">
          <component :is="generationIcon" :size="12" :class="{ spinning: generationState === 'generating' }" />
          {{ generationLabel }}
        </small>
      </header>
      <div v-if="node.node_content" class="section-content" :style="contentStyle">
        <CourseBlockStream :node="node" :content="node.node_content" :records="records" :search-words="searchWords" :is-streaming="isStreaming" :can-improve-blocks="canImproveBlocks" @open-record="emit('openRecord', $event)" @improve-block="emit('improveBlock', $event)" @start-practice="emit('startPractice', node, $event)" />
      </div>
      <div v-else-if="generationPreview" class="generation-placeholder" :data-state="generationState">
        <component :is="generationIcon" :size="16" :class="{ spinning: generationState === 'generating' }" />
        <span>{{ generationLabel }}</span>
      </div>
      <AdaptiveLearningBlock v-for="block in adaptiveBlocks" v-if="!generationPreview" :key="block.adaptive_block_id" :block="block" :practice-available="hasFormalPractice" @verify="emit('startPractice', node)" />
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ArrowRight, BookOpenText, CheckCircle2, ClipboardCheck, Clock3, LoaderCircle, TriangleAlert } from 'lucide-vue-next'
import AdaptiveLearningBlock from './AdaptiveLearningBlock.vue'
import CourseBlockStream from './CourseBlockStream.vue'
import { useCourseWorkspaceStore } from '../stores/courseWorkspace'
import { useLearningProgressStore } from '../stores/learningProgress'
import type { CourseBlockEditTarget, Node, Note } from '../stores/types'
import { t } from '../shared/i18n'

const props = defineProps<{
  node: Node
  index: number
  fontSize: number
  fontFamily: string
  lineHeight: number
  searchWords?: string[]
  isStreaming?: boolean
  records?: Note[]
  canImproveBlocks?: boolean
  generationPreview?: boolean
}>()
const emit = defineEmits<{
  (event: 'startPractice', node: Node, taskRevisionId?: string): void
  (event: 'openRecord', payload: { note: Note; x: number; y: number }): void
  (event: 'improveBlock', payload: CourseBlockEditTarget): void
}>()
const progressStore = useLearningProgressStore()
const workspaceStore = useCourseWorkspaceStore()
const cleanName = computed(() => props.node.node_name.replace(/《|》/g, ''))
const generationState = computed(() => {
  const status = String(props.node.generation_status || '')
  if (status === 'generating') return 'generating'
  if (status === 'completed' || props.node.content_state === 'finalized') return 'finalized'
  if (status === 'error' || props.node.content_state === 'failed') return 'failed'
  if (props.node.content_state === 'draft' || Boolean(props.node.node_content)) return 'draft'
  return 'waiting'
})
const generationLabel = computed(() => {
  if (generationState.value === 'generating') return t('courseGeneration.workspace.generating', '正在生成')
  if (generationState.value === 'finalized') return t('courseGeneration.workspace.finalized', '已定稿')
  if (generationState.value === 'failed') return t('courseGeneration.workspace.failed', '生成失败')
  if (generationState.value === 'draft') return t('courseGeneration.workspace.draft', 'AI 草稿')
  return t('courseGeneration.workspace.waiting', '等待生成')
})
const generationIcon = computed(() => {
  if (generationState.value === 'generating') return LoaderCircle
  if (generationState.value === 'finalized') return CheckCircle2
  if (generationState.value === 'failed') return TriangleAlert
  return Clock3
})
const practiceQuestions = computed(() => (
  workspaceStore.assets?.assets?.questions || []
).filter(item => item.node_id === props.node.node_id))
const hasFormalPractice = computed(() => practiceQuestions.value.length > 0)
const practicePreview = computed(() => String(
  practiceQuestions.value[0]?.prompt
  || practiceQuestions.value[0]?.question_text
  || practiceQuestions.value[0]?.title
  || '',
).trim())
const practiceCountLabel = computed(() => (
  t('courseBlocks.practiceCount', '{count} 道正式题').replace('{count}', String(practiceQuestions.value.length))
))
const nodeProgress = computed(() => progressStore.nodeProgress(props.node.node_id))
const adaptiveBlocks = computed(() => (progressStore.runtime?.adaptive_blocks || []).filter(block => (
  block.status === 'active' && block.anchor.node_id === props.node.node_id
)))
const readingStatusLabel = computed(() => t(`courseWorkspace.progress.reading.${nodeProgress.value?.reading_status || 'not_started'}`, '尚未开始'))
const masteryStatusLabel = computed(() => t(`courseWorkspace.progress.mastery.${nodeProgress.value?.mastery_status || 'not_checked'}`, '尚未检查'))
const contentStyle = computed(() => ({
  '--content-font-size': `${props.fontSize}px`,
  '--content-line-height': String(props.lineHeight),
  fontSize: `${props.fontSize}px`,
  fontFamily: props.fontFamily === 'mono'
    ? 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace'
    : props.fontFamily === 'serif'
      ? '"Noto Serif SC", "Songti SC", serif'
      : '"Noto Sans SC", "PingFang SC", system-ui, sans-serif',
  lineHeight: props.lineHeight,
}))
</script>

<style scoped>
.course-node { width:min(100%,920px); margin:0 auto; color:var(--lz-text); }
.course-node[data-level="1"] { margin:34px auto 48px; padding:44px clamp(24px,5vw,64px); overflow:visible; border:1px solid rgba(255,255,255,.9); border-radius:28px; background:linear-gradient(145deg,rgba(255,255,255,.82),rgba(248,247,255,.68)); box-shadow:0 16px 42px rgba(79,70,229,.09),inset 0 1px 0 rgba(255,255,255,.95); }
.course-node[data-level="2"] { position:relative; margin:30px auto 38px; padding:0 clamp(22px,4vw,42px) 34px; overflow:visible; border:1px solid rgba(241,245,249,.96); border-radius:24px; background:#fff; box-shadow:0 8px 28px rgba(15,23,42,.08),inset 0 1px 0 rgba(255,255,255,.95); transition:box-shadow .3s ease,transform .3s ease; }
.course-node[data-level="2"]:hover { box-shadow:0 18px 42px rgba(15,23,42,.11); transform:translateY(-1px); }
.course-node[data-level="2"]::before { content:""; position:absolute; inset:0 0 auto; height:5px; border-radius:24px 24px 0 0; background:linear-gradient(90deg,#818cf8,#8b5cf6,#a855f7); pointer-events:none; }
.course-node[data-level="3"],.course-node[data-level="4"],.course-node[data-level="5"] { --inline-ai-menu-offset:calc(clamp(18px,4vw,30px) + clamp(16px,3vw,24px) + 15px); position:relative; margin:16px auto 24px; padding:2px 0 2px clamp(18px,4vw,30px); border-left:2px solid #e2e8f0; transition:border-color .2s ease; }
.course-node[data-level="3"]::before,.course-node[data-level="4"]::before,.course-node[data-level="5"]::before { content:""; position:absolute; top:7px; left:-5px; width:8px; height:8px; border:1px solid #fff; border-radius:50%; background:#e2e8f0; box-shadow:0 1px 3px rgba(15,23,42,.12); transition:background .2s ease,transform .2s ease; }
.course-node[data-level="3"]:hover,.course-node[data-level="4"]:hover,.course-node[data-level="5"]:hover { border-left-color:#a5b4fc; }
.course-node[data-level="3"]:hover::before,.course-node[data-level="4"]:hover::before,.course-node[data-level="5"]:hover::before { background:#818cf8; transform:scale(1.15); }
.course-opening { display:flex; flex-direction:column; align-items:center; padding:10px 0 24px; border-bottom:0; text-align:center; }
.course-opening > span { padding:6px 12px; border:1px solid rgba(203,213,225,.68); border-radius:999px; color:#6366f1; background:rgba(255,255,255,.7); font-size:9px; font-weight:800; text-transform:uppercase; }
.course-opening h1 { max-width:760px; margin:22px 0 14px; color:#312e81; font-size:clamp(30px,4vw,46px); line-height:1.16; }
.course-opening p,.chapter-copy p { max-width:720px; margin:0; color:var(--lz-text-secondary); font-size:13px; line-height:1.7; }
.opening-content { padding-top:22px; border-top:0; }
.chapter-heading { display:grid; grid-template-columns:minmax(0,1fr) auto; align-items:start; gap:20px; padding:34px 0 24px; border-bottom:0; }
.chapter-meta { min-width:0; display:flex; align-items:center; gap:12px; }
.chapter-badge { display:inline-flex; align-items:center; gap:7px; padding:7px 12px; border-radius:999px; color:#fff; background:linear-gradient(90deg,#1e293b,#334155); box-shadow:0 5px 12px rgba(15,23,42,.13); font-size:10px; font-weight:800; letter-spacing:0; }
.chapter-badge svg { color:#a5b4fc; }
.chapter-index { color:#e2e8f0; font-size:28px; font-weight:900; line-height:1; }
.chapter-copy { min-width:0; grid-column:1/-1; }
.chapter-copy h2 { margin:0 0 16px; color:#1e293b; font-size:clamp(29px,3.4vw,44px); font-weight:850; line-height:1.12; }
.chapter-divider { display:flex; align-items:center; gap:10px; margin:0 0 17px; }
.chapter-divider span { width:64px; height:4px; border-radius:999px; background:linear-gradient(90deg,#6366f1,#8b5cf6); }
.chapter-divider i { width:7px; height:7px; border-radius:50%; background:#818cf8; }
.chapter-divider b { width:30px; height:2px; border-radius:999px; background:#e2e8f0; }
.chapter-status { display:flex; flex-wrap:wrap; justify-content:flex-end; gap:5px; }
.chapter-status span { padding:4px 8px; border:1px solid rgba(203,213,225,.68); border-radius:999px; color:var(--lz-text-muted); background:rgba(255,255,255,.72); font-size:9px; }
.chapter-status span[data-state="completed"],.chapter-status span[data-state="mastered"] { border-color:#a7f3d0; color:var(--lz-success); background:var(--lz-success-soft); }
.chapter-status .generation-status { display:inline-flex; align-items:center; gap:5px; }
.generation-status[data-state="generating"],.section-generation-status[data-state="generating"] { border-color:#c7d2fe; color:#4f46e5; background:#eef2ff; }
.generation-status[data-state="finalized"],.section-generation-status[data-state="finalized"] { border-color:#a7f3d0; color:#047857; background:#ecfdf5; }
.generation-status[data-state="failed"],.section-generation-status[data-state="failed"] { border-color:#fecaca; color:#b91c1c; background:#fef2f2; }
.generation-status[data-state="draft"],.section-generation-status[data-state="draft"] { border-color:#ddd6fe; color:#6d28d9; background:#f5f3ff; }
.spinning { animation:generation-status-spin .9s linear infinite; }
.chapter-content { padding:20px 0 8px; }
.generation-placeholder { min-height:52px; display:flex; align-items:center; gap:9px; margin:8px 0 0; padding:12px 14px; border:1px dashed #dbe2ee; border-radius:10px; color:#64748b; background:#f8fafc; font-size:11px; font-weight:650; }
.generation-placeholder[data-state="generating"] { border-color:#c7d2fe; color:#4f46e5; background:#f5f7ff; }
.generation-placeholder[data-state="failed"] { border-color:#fecaca; color:#b91c1c; background:#fef2f2; }
.task-launcher { position:relative; width:100%; min-height:112px; margin:30px 0 0; display:grid; grid-template-columns:44px minmax(0,1fr) auto; align-items:center; gap:16px; overflow:hidden; padding:18px 18px 18px 20px; border:1px solid #dbe2ee; border-radius:16px; color:var(--lz-text); background:#f8fafc; text-align:left; box-shadow:0 1px 2px rgba(15,23,42,.03),inset 0 1px 0 rgba(255,255,255,.9); cursor:pointer; transition:border-color .22s ease,box-shadow .22s ease,transform .22s ease,background .22s ease; }
.task-launcher::before { content:""; position:absolute; inset:14px auto 14px 0; width:3px; border-radius:0 999px 999px 0; background:#6366f1; }
.task-launcher:hover { border-color:#a5b4fc; background:#fff; box-shadow:0 10px 28px rgba(15,23,42,.08); transform:translateY(-2px); }
.task-launcher:focus-visible { outline:3px solid rgba(99,102,241,.28); outline-offset:3px; }
.task-icon { width:44px; height:44px; display:grid; place-items:center; border:1px solid #c7d2fe; border-radius:13px; color:#4f46e5; background:#eef2ff; box-shadow:0 5px 12px rgba(79,70,229,.08); }
.task-copy { min-width:0; display:flex; flex-direction:column; }
.task-meta { margin-bottom:7px; color:#6366f1; font-size:10px; font-weight:800; letter-spacing:.02em; }
.task-copy strong { display:-webkit-box; overflow:hidden; -webkit-box-orient:vertical; -webkit-line-clamp:2; color:var(--lz-text-strong); font-size:14px; font-weight:720; line-height:1.55; }
.task-copy small { margin-top:6px; color:var(--lz-text-muted); font-size:10px; line-height:1.45; }
.task-action { display:inline-flex; align-items:center; gap:6px; padding:8px 10px; border-radius:9px; color:var(--lz-brand-strong); background:#eef2ff; font-size:11px; font-weight:750; white-space:nowrap; }
.task-launcher:hover .task-action svg { transform:translateX(2px); }
.task-action svg { transition:transform .2s ease; }
.section-heading { display:grid; grid-template-columns:minmax(0,1fr); align-items:center; gap:10px; }
.section-heading span { display:none; }
.section-heading h3 { margin:0; color:#312e81; font-size:19px; line-height:1.35; }
.section-generation-status { width:max-content; display:inline-flex; align-items:center; gap:4px; margin-top:2px; padding:3px 7px; border:1px solid #dbe2ee; border-radius:999px; color:#64748b; background:#f8fafc; font-size:9px; font-weight:700; }
.section-content { margin:12px 0 0; padding:18px clamp(16px,3vw,24px); border:1px solid rgba(226,232,240,.7); border-radius:12px; background:rgba(255,255,255,.66); font-size:var(--content-font-size); line-height:var(--content-line-height); transition:background .2s ease,border-color .2s ease,box-shadow .2s ease; }
.course-node[data-level="3"]:hover .section-content,.course-node[data-level="4"]:hover .section-content,.course-node[data-level="5"]:hover .section-content { border-color:rgba(203,213,225,.82); background:rgba(255,255,255,.84); box-shadow:0 4px 12px rgba(15,23,42,.04); }
@media (max-width: 700px) {
  .course-node[data-level="1"] { margin:18px auto 26px; padding:24px 18px 26px; border-radius:18px; }
  .course-node[data-level="2"] { margin:18px auto 26px; padding:0 18px 26px; border-radius:18px; }
  .course-node[data-level="2"]::before { border-radius:18px 18px 0 0; }
  .chapter-heading { grid-template-columns:minmax(0,1fr); gap:12px; padding-top:28px; }
  .chapter-status { justify-content:flex-start; }
  .chapter-copy { grid-column:1; }
  .chapter-copy h2 { overflow-wrap:anywhere; }
  .chapter-content { padding-left: 0; }
  .task-launcher { width:100%; min-height:0; margin-left:0; grid-template-columns:40px minmax(0,1fr); gap:12px; padding:16px 14px 15px 17px; }
  .task-icon { width:40px; height:40px; border-radius:12px; }
  .task-action { grid-column: 2; }
}
@container (max-width:680px) {
  .course-node[data-level="2"] { padding-inline:18px; }
  .chapter-copy h2 { font-size:28px; }
  .chapter-content { padding-left:0; }
  .task-launcher { width:100%; margin-left:0; }
}
@keyframes generation-status-spin { to { transform:rotate(360deg); } }
</style>
