<template>
  <section :id="`node-${node.node_id}`" class="course-node" :data-level="node.node_level">
    <template v-if="node.node_level === 1">
      <header class="course-opening">
        <span>{{ t('courseBlocks.courseUnit', '课程单元') }}</span>
        <h1><MathText :content="cleanName" /></h1>
        <MathText v-if="node.learning_objective" tag="p" :content="node.learning_objective" />
      </header>
      <div v-if="node.node_content" class="opening-content" :style="contentStyle">
        <CourseBlockStream :node="node" :content="node.node_content" :records="readOnly ? [] : records" :search-words="searchWords" :is-streaming="isStreaming" :can-improve-blocks="canImproveBlocks" :read-only="readOnly" @open-record="emit('openRecord', $event)" @improve-block="emit('improveBlock', $event)" @start-practice="emit('startPractice', node, $event)" />
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
          <span class="chapter-label">{{ chapterNumberLabel }}</span>
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
          <h2><MathText :content="node.node_name" /></h2>
          <MathText v-if="node.learning_objective" tag="p" :content="node.learning_objective" />
        </div>
      </header>

      <div v-if="node.node_content" class="chapter-content" :style="contentStyle">
        <CourseBlockStream :node="node" :content="node.node_content" :records="readOnly ? [] : records" :search-words="searchWords" :is-streaming="isStreaming" :can-improve-blocks="canImproveBlocks" :read-only="readOnly" @open-record="emit('openRecord', $event)" @improve-block="emit('improveBlock', $event)" @start-practice="emit('startPractice', node, $event)" />
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
            {{ lesson ? t('courseBlocks.lessonPractice', '本讲练习') : t('courseBlocks.chapterPractice', '章节练习') }} · {{ practiceCountLabel }}
          </span>
          <strong><MathText :content="practicePreview || node.node_name" /></strong>
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
        <h3><MathText :content="node.node_name" /></h3>
        <small v-if="generationPreview" class="section-generation-status" :data-state="generationState">
          <component :is="generationIcon" :size="12" :class="{ spinning: generationState === 'generating' }" />
          {{ generationLabel }}
        </small>
      </header>
      <div v-if="node.node_content" class="section-content" :style="contentStyle">
        <CourseBlockStream :node="node" :content="node.node_content" :records="readOnly ? [] : records" :search-words="searchWords" :is-streaming="isStreaming" :can-improve-blocks="canImproveBlocks" :read-only="readOnly" @open-record="emit('openRecord', $event)" @improve-block="emit('improveBlock', $event)" @start-practice="emit('startPractice', node, $event)" />
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
import { ArrowRight, CheckCircle2, ClipboardCheck, Clock3, LoaderCircle, TriangleAlert } from 'lucide-vue-next'
import AdaptiveLearningBlock from './AdaptiveLearningBlock.vue'
import CourseBlockStream from './CourseBlockStream.vue'
import MathText from './MathText.vue'
import { useCourseWorkspaceStore } from '../stores/courseWorkspace'
import { useLearningProgressStore } from '../stores/learningProgress'
import type { CourseBlockEditTarget, Node, Note } from '../stores/types'
import { t } from '../shared/i18n'

const props = defineProps<{
  node: Node
  lesson?: boolean
  index: number
  fontSize: number
  fontFamily: string
  lineHeight: number
  searchWords?: string[]
  isStreaming?: boolean
  records?: Note[]
  canImproveBlocks?: boolean
  readOnly?: boolean
  generationPreview?: boolean
}>()
const emit = defineEmits<{
  (event: 'startPractice', node: Node, taskRevisionId?: string): void
  (event: 'openRecord', payload: { note: Note; x: number; y: number }): void
  (event: 'improveBlock', payload: CourseBlockEditTarget): void
}>()
const progressStore = useLearningProgressStore()
const workspaceStore = useCourseWorkspaceStore()
const chapterNumberLabel = computed(() => (props.lesson
  ? t('courseBlocks.lessonNumber', '第 {number} 讲')
  : t('courseBlocks.chapterNumber', '第 {number} 章')
).replace('{number}', String(props.index + 1)))
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
.course-node {
  width: min(100%, 860px);
  margin: 0 auto;
  color: var(--lz-text);
  container-type: inline-size;
}
.course-node[data-level="1"],
.course-node[data-level="2"] {
  margin: 22px auto 36px;
  padding: 0 clamp(28px, 4vw, 44px) 36px;
  border: 1px solid #e9ecf3;
  border-radius: 20px;
  background: #fff;
  box-shadow: 0 2px 4px rgba(31, 41, 74, .025), 0 12px 36px rgba(31, 41, 74, .045);
}
.course-opening, .chapter-heading {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: start;
  gap: 18px;
  padding: 32px 0 26px;
  border-bottom: 1px solid #e9ecf3;
}
.course-opening > span, .chapter-label {
  color: var(--lz-brand-strong);
  font-size: 14px;
  font-weight: 650;
  line-height: 1.5;
}
.course-opening h1, .chapter-copy h2 {
  margin: 0;
  color: var(--lz-text-strong);
  font-size: clamp(28px, 5cqi, 36px);
  font-weight: 720;
  line-height: 1.4;
  text-wrap: balance;
  overflow-wrap: anywhere;
}
.course-opening h1 { grid-column: 1 / -1; font-size: clamp(30px, 5cqi, 40px); }
.course-opening p, .chapter-copy p {
  max-width: 720px;
  margin: 14px 0 0;
  color: var(--lz-text-secondary);
  font-size: 15px;
  line-height: 1.75;
}
.course-opening p { grid-column: 1 / -1; margin-top: 0; }
.chapter-meta { min-width: 0; display: flex; align-items: center; }
.chapter-copy { min-width: 0; grid-column: 1 / -1; }
.chapter-status { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 6px; }
.chapter-status span, .section-generation-status {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 7px;
  border-radius: 6px;
  color: var(--lz-text-secondary);
  background: #f4f6fa;
  font-size: 12px;
  font-weight: 500;
  line-height: 1.5;
}
.chapter-status span[data-state="completed"],
.chapter-status span[data-state="mastered"] { color: var(--lz-success); background: var(--lz-success-soft); }
.generation-status[data-state="generating"],.section-generation-status[data-state="generating"] { color:#4f46e5; background:#eef2ff; }
.generation-status[data-state="finalized"],.section-generation-status[data-state="finalized"] { color:#047857; background:#ecfdf5; }
.generation-status[data-state="failed"],.section-generation-status[data-state="failed"] { color:#b91c1c; background:#fef2f2; }
.generation-status[data-state="draft"],.section-generation-status[data-state="draft"] { color:#6d28d9; background:#f5f3ff; }
.spinning { animation: generation-status-spin .9s linear infinite; }
.chapter-content, .opening-content { padding: 28px 0 0; }
/* Keep the reader's typography settings across shared Markdown renderers. */
.chapter-content :deep(.markdown-renderer),
.opening-content :deep(.markdown-renderer),
.section-content :deep(.markdown-renderer) { line-height: var(--content-line-height, 1.8); }
.generation-placeholder {
  min-height: 52px;
  display: flex;
  align-items: center;
  gap: 9px;
  margin-top: 24px;
  padding: 14px;
  border: 1px dashed #dbe2ee;
  border-radius: 10px;
  color: var(--lz-text-secondary);
  background: #f8fafc;
  font-size: 14px;
}
.generation-placeholder[data-state="generating"] { border-color:#c7d2fe; color:#4f46e5; background:#f5f7ff; }
.generation-placeholder[data-state="failed"] { border-color:#fecaca; color:#b91c1c; background:#fef2f2; }
.task-launcher {
  position: relative;
  width: 100%;
  margin-top: 32px;
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr) auto;
  align-items: start;
  gap: 14px;
  padding: 22px;
  border: 1px solid var(--color-primary-100);
  border-radius: 12px;
  color: var(--lz-text);
  background: #f8f9ff;
  text-align: left;
  cursor: pointer;
  transition: border-color .18s var(--ease-out), background-color .18s var(--ease-out);
}
.task-launcher:hover { border-color: var(--color-primary-300); background: #f3f5ff; }
.task-launcher:active { background: var(--color-primary-50); }
.task-launcher:focus-visible { outline: 2px solid var(--lz-brand-strong); outline-offset: 3px; }
.task-icon { padding-top: 2px; color: var(--lz-brand-strong); }
.task-icon :deep(svg) { width: 23px; height: 23px; }
.task-copy { min-width: 0; display: flex; flex-direction: column; gap: 8px; }
.task-meta { color: var(--lz-brand-strong); font-size: 13px; font-weight: 650; line-height: 1.6; }
.task-copy strong { color: var(--lz-text-strong); font-size: 16px; font-weight: 600; line-height: 1.7; overflow-wrap: anywhere; }
.task-copy small { color: var(--lz-text-secondary); font-size: 13px; line-height: 1.65; }
.task-action {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 8px 10px;
  border: 1px solid var(--color-primary-200);
  border-radius: 8px;
  color: var(--lz-brand-strong);
  background: #fff;
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
  transition: background-color .18s var(--ease-out);
}
.task-launcher:hover .task-action { background: var(--color-primary-50); }
.course-node[data-level="3"],.course-node[data-level="4"],.course-node[data-level="5"] {
  --inline-ai-menu-offset: 0px;
  margin: 24px auto 32px;
  padding: 0 clamp(28px, 4vw, 44px);
}
.section-heading { display: grid; gap: 10px; }
.section-heading > span { display: none; }
.section-heading h3 { margin: 0; color: var(--lz-text-strong); font-size: 22px; font-weight: 650; line-height: 1.5; text-wrap: balance; }
.section-generation-status { width: max-content; }
.section-content { margin-top: 16px; font-size: var(--content-font-size); line-height: var(--content-line-height); }
@container (max-width: 580px) {
  .task-launcher { grid-template-columns: 24px minmax(0, 1fr); padding: 18px; }
  .task-action { grid-column: 2; justify-self: start; }
}
@keyframes generation-status-spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) {
  .task-launcher,.task-action { transition: none; }
  .spinning { animation: none; }
}
</style>
