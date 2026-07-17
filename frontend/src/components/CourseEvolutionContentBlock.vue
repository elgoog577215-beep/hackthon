<template>
  <div class="course-evolution-content">
    <MarkdownRenderer :content="content" :search-words="searchWords" />

    <section v-if="isTargetedPractice" class="course-evolution-practice">
      <span><ClipboardCheck :size="15" />{{ t('courseEvolution.targetedPractice', '针对性练习') }}</span>
      <button type="button" @click="emit('startPractice', practiceTaskId)">
        {{ t('courseEvolution.startTargetedPractice', '开始练习') }}
        <ArrowRight :size="14" />
      </button>
    </section>

    <section
      v-if="animationSpec"
      class="course-evolution-animation"
      :aria-label="String(animationSpec.accessibility_text || animationSpec.title || '')"
    >
      <header>
        <span><SquarePlay :size="14" />{{ t('adaptiveBlocks.structuredAnimation', '结构化动画') }}</span>
        <button
          type="button"
          :title="isPlaying ? t('adaptiveBlocks.pauseAnimation', '暂停动画') : t('adaptiveBlocks.playAnimation', '播放动画')"
          @click="toggleAnimation"
        >
          <Pause v-if="isPlaying" :size="14" /><Play v-else :size="14" />
        </button>
      </header>
      <strong>{{ animationSpec.title }}</strong>
      <div class="course-evolution-animation__frame">
        <small>{{ activeKeyframe.index }} / {{ animationSpec.keyframes.length }}</small>
        <b>{{ activeKeyframe.label }}</b>
        <p>{{ activeKeyframeDescription }}</p>
      </div>
      <div class="course-evolution-animation__timeline">
        <button
          v-for="(frame, index) in animationSpec.keyframes"
          :key="frame.index"
          type="button"
          :class="{ active: activeFrame === index }"
          :title="String(frame.label || '')"
          @click="selectFrame(index)"
        >
          {{ frame.index }}
        </button>
      </div>
    </section>

    <footer v-if="evolutionSource">
      <span>
        <GitBranchPlus :size="14" />
        <b>{{ t('courseEvolution.formalEyebrow', '学习证据形成的课程版本') }}</b>
        {{ t('courseEvolution.formalEvidence', '依据可追踪，效果将由后续学习复验') }}
      </span>
      <div :aria-label="t('adaptiveBlocks.feedback', '这段内容是否有帮助')">
        <button
          type="button"
          :class="{ active: feedback === 'helpful' }"
          :title="t('adaptiveBlocks.helpful', '有帮助')"
          @click="sendFeedback('helpful')"
        >
          <ThumbsUp :size="14" />
        </button>
        <button
          type="button"
          :class="{ active: feedback === 'not_helpful' }"
          :title="t('adaptiveBlocks.notHelpful', '没有帮助')"
          @click="sendFeedback('not_helpful')"
        >
          <ThumbsDown :size="14" />
        </button>
      </div>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { ArrowRight, ClipboardCheck, GitBranchPlus, Pause, Play, SquarePlay, ThumbsDown, ThumbsUp } from 'lucide-vue-next'
import MarkdownRenderer from './MarkdownRenderer.vue'
import { useCourseStore } from '../stores/course'
import {
  useLearningProgressStore,
  type AdaptiveBlockFeedback,
  type AdaptiveLearningBlock,
} from '../stores/learningProgress'
import { t } from '../shared/i18n'

const props = withDefaults(defineProps<{
  blockId: string
  nodeId: string
  kind: string
  content: string
  metadata?: Record<string, any>
  searchWords?: string[]
}>(), { metadata: () => ({}) })
const emit = defineEmits<{ startPractice: [taskRevisionId: string] }>()

const courseStore = useCourseStore()
const progressStore = useLearningProgressStore()
const activeFrame = ref(0)
const isPlaying = ref(false)
const feedback = ref<AdaptiveBlockFeedback>('unrated')
let animationTimer: number | undefined

const evolutionSource = computed<Record<string, any> | null>(() => (
  props.metadata?.course_evolution && typeof props.metadata.course_evolution === 'object'
    ? props.metadata.course_evolution
    : null
))
const animationSpec = computed<any | null>(() => {
  const value = props.metadata?.animation_spec
  return value?.schema_version === 'animation_spec_v1' && value.keyframes?.length ? value : null
})
const practiceTaskId = computed(() => String(props.metadata?.practice_task_id || ''))
const isTargetedPractice = computed(() => (
  props.kind === 'practice_ref'
  || String(props.metadata?.practice_intent || '') === 'targeted_retry'
))
const activeKeyframe = computed(() => animationSpec.value?.keyframes[activeFrame.value] || {
  index: 1,
  label: '',
  state: { description: '' },
})
const activeKeyframeDescription = computed(() => String(
  activeKeyframe.value?.state?.description || activeKeyframe.value?.description || '',
))
const supportBlock = computed<AdaptiveLearningBlock | null>(() => {
  const source = evolutionSource.value
  const operationId = String(source?.operation_id || '')
  if (!operationId) return null
  return {
    adaptive_block_id: operationId,
    change_set_id: String(source?.change_set_id || ''),
    anchor: {
      node_id: props.nodeId,
      content_block_id: props.blockId,
      placement: 'after_block',
    },
    kind: props.kind === 'diagram' ? 'animation' : isTargetedPractice.value ? 'understanding_check' : 'explanation',
    role: 'course_evolution_block',
    payload: {
      body: props.content,
      contrast: '',
      prompt: '',
      objective: '',
      animation_spec: animationSpec.value || undefined,
    },
    reason_code: 'accepted_evidence_driven_growth',
    evidence_refs: Array.isArray(source?.evidence_ids) ? source.evidence_ids : [],
    status: 'active',
    expires_at: '',
    feedback: {
      value: feedback.value,
      options: ['unrated', 'helpful', 'not_helpful'],
    },
  }
})

function sendFeedback(value: 'helpful' | 'not_helpful') {
  feedback.value = value
  if (!supportBlock.value || !courseStore.currentCourseId) return
  void progressStore.feedbackAdaptiveBlock(courseStore.currentCourseId, supportBlock.value, value)
}

function stopAnimation() {
  if (animationTimer !== undefined) window.clearInterval(animationTimer)
  animationTimer = undefined
  isPlaying.value = false
}

function selectFrame(index: number) {
  stopAnimation()
  activeFrame.value = index
}

function toggleAnimation() {
  if (isPlaying.value) return stopAnimation()
  const frames = animationSpec.value?.keyframes || []
  if (frames.length < 2) return
  if (activeFrame.value >= frames.length - 1) activeFrame.value = 0
  if (supportBlock.value && courseStore.currentCourseId) {
    void progressStore.recordAdaptiveBlockInteraction(
      courseStore.currentCourseId,
      supportBlock.value,
      'animation_played',
    )
  }
  isPlaying.value = true
  const duration = Math.max(500, Number(frames[activeFrame.value]?.duration_ms || 1200))
  animationTimer = window.setInterval(() => {
    if (activeFrame.value >= frames.length - 1) return stopAnimation()
    activeFrame.value += 1
  }, duration)
}

onBeforeUnmount(stopAnimation)
</script>

<style scoped>
.course-evolution-content { min-width:0; padding:2px 0 0 15px; border-left:3px solid #8b5cf6; background:linear-gradient(90deg,rgba(245,243,255,.62),rgba(255,255,255,0)); }
.course-evolution-practice { display:flex; align-items:center; justify-content:space-between; gap:12px; margin:14px 12px 0 0; padding:11px 12px; border:1px solid rgba(190,24,93,.2); border-radius:8px; background:#fdf2f8; }
.course-evolution-practice > span { display:inline-flex; align-items:center; gap:6px; color:#9d174d; font-size:11px; font-weight:800; }
.course-evolution-practice > button { min-height:31px; display:inline-flex; align-items:center; gap:5px; padding:0 10px; border:1px solid #f9a8d4; border-radius:7px; color:#9d174d; background:#fff; font-size:10px; font-weight:700; cursor:pointer; }
.course-evolution-practice > button:hover { border-color:#ec4899; color:#831843; }
.course-evolution-animation { display:grid; gap:8px; margin:14px 12px 0 0; padding:12px; border:1px solid rgba(139,92,246,.24); border-radius:8px; background:rgba(255,255,255,.78); }
.course-evolution-animation > header { display:flex; align-items:center; justify-content:space-between; gap:8px; }
.course-evolution-animation > header span { display:inline-flex; align-items:center; gap:5px; color:#6d28d9; font-size:10px; font-weight:800; }
.course-evolution-animation button,.course-evolution-content footer button { width:28px; height:28px; display:grid; place-items:center; border:0; border-radius:6px; color:#6d28d9; background:#f5f3ff; cursor:pointer; }
.course-evolution-animation > strong { color:var(--lz-text-strong); font-size:13px; }
.course-evolution-animation__frame { min-height:76px; display:grid; grid-template-columns:auto minmax(0,1fr); align-content:center; gap:4px 8px; padding:10px; border-radius:7px; background:#f8fafc; }
.course-evolution-animation__frame small { grid-row:1 / 3; color:#7c3aed; font-size:9px; font-weight:800; }
.course-evolution-animation__frame b { color:var(--lz-text); font-size:12px; }
.course-evolution-animation__frame p { margin:0; color:var(--lz-text-secondary); font-size:11px; line-height:1.55; }
.course-evolution-animation__timeline { display:flex; gap:5px; }
.course-evolution-animation__timeline button { width:25px; height:25px; border:1px solid #ddd6fe; border-radius:50%; background:#fff; font-size:9px; }
.course-evolution-animation__timeline button.active { color:#fff; border-color:#7c3aed; background:#7c3aed; }
.course-evolution-content footer { display:flex; align-items:center; justify-content:space-between; gap:12px; margin:13px 12px 0 0; padding-top:10px; border-top:1px solid rgba(221,214,254,.7); }
.course-evolution-content footer > span { display:flex; flex-wrap:wrap; align-items:center; gap:5px; color:var(--lz-text-muted); font-size:9px; line-height:1.5; }
.course-evolution-content footer b { color:#6d28d9; }
.course-evolution-content footer > div { display:flex; gap:3px; }
.course-evolution-content footer button.active { color:#fff; background:#7c3aed; }
</style>
