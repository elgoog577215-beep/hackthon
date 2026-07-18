<template>
  <div class="course-evolution-content">
    <MarkdownRenderer :content="content" :search-words="searchWords" />

    <section v-if="isTargetedPractice" class="course-evolution-practice">
      <span><ClipboardCheck :size="15" />{{ t('courseEvolution.targetedPractice', '针对性练习') }}</span>
      <button type="button" @click="startPractice">
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
      <div class="course-evolution-animation__frame" :class="{ 'is-composition': isLinearCompositionAnimation }">
        <template v-if="isLinearCompositionAnimation">
          <div class="composition-formula" aria-hidden="true">
            <span :class="{ active: activeFrame === 0, reached: activeFrame > 0 }">v</span>
            <ArrowRight :size="13" />
            <span :class="{ active: activeFrame === 1, reached: activeFrame > 1 }">Bv</span>
            <ArrowRight :size="13" />
            <span :class="{ active: activeFrame === 2 }">A(Bv)</span>
          </div>
          <div class="composition-stage">
            <svg viewBox="-52 -52 104 104" role="img" :aria-label="activeKeyframeDescription">
              <g class="composition-grid">
                <template v-for="line in gridLines" :key="`grid-${line}`">
                  <line :x1="line" y1="-48" :x2="line" y2="48" />
                  <line x1="-48" :y1="line" x2="48" :y2="line" />
                </template>
              </g>
              <line class="composition-axis" x1="-48" y1="0" x2="48" y2="0" />
              <line class="composition-axis" x1="0" y1="-48" x2="0" y2="48" />
              <polygon class="composition-shape" :points="compositionShapePoints" />
              <line class="composition-vector" x1="0" y1="0" :x2="compositionVector.x" :y2="compositionVector.y" />
              <circle class="composition-vector-tip" :cx="compositionVector.x" :cy="compositionVector.y" r="2.8" />
              <circle class="composition-origin" cx="0" cy="0" r="2" />
            </svg>
            <div class="composition-copy">
              <small>{{ activeKeyframe.index }} / {{ animationSpec.keyframes.length }}</small>
              <b>{{ activeKeyframe.state?.formula || activeKeyframe.label }}</b>
              <strong>{{ activeKeyframe.label }}</strong>
              <p>{{ activeKeyframeDescription }}</p>
            </div>
          </div>
        </template>
        <template v-else>
          <small>{{ activeKeyframe.index }} / {{ animationSpec.keyframes.length }}</small>
          <b>{{ activeKeyframe.label }}</b>
          <p>{{ activeKeyframeDescription }}</p>
        </template>
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
      <div v-if="isLinearCompositionAnimation" class="composition-check">
        <small>{{ t('courseEvolution.animationChallenge.eyebrow', '先判断，再验证') }}</small>
        <p>{{ t('courseEvolution.animationChallenge.prompt', '计算 ABv 时，应该按什么顺序执行变换？') }}</p>
        <div role="group" :aria-label="t('courseEvolution.animationChallenge.prompt', '计算 ABv 时，应该按什么顺序执行变换？')">
          <button
            type="button"
            :class="{ selected: compositionAnswer === 'right_then_left', correct: compositionAnswer === 'right_then_left' }"
            :aria-pressed="compositionAnswer === 'right_then_left'"
            @click="answerComposition('right_then_left')"
          >
            {{ t('courseEvolution.animationChallenge.rightThenLeft', '先 B，再 A') }}
          </button>
          <button
            type="button"
            :class="{ selected: compositionAnswer === 'left_then_right', wrong: compositionAnswer === 'left_then_right' }"
            :aria-pressed="compositionAnswer === 'left_then_right'"
            @click="answerComposition('left_then_right')"
          >
            {{ t('courseEvolution.animationChallenge.leftThenRight', '先 A，再 B') }}
          </button>
        </div>
        <p v-if="compositionAnswer" class="composition-check__result" :class="{ 'is-correct': compositionAnswerCorrect }" aria-live="polite">
          <CheckCircle2 v-if="compositionAnswerCorrect" :size="13" />
          <CircleX v-else :size="13" />
          {{
            compositionAnswerCorrect
              ? t('courseEvolution.animationChallenge.correct', '正确。右侧 B 先作用于 v，再由 A 作用于 Bv。')
              : t('courseEvolution.animationChallenge.wrong', '顺序反了。先看离输入 v 最近的变换，再重新选择。')
          }}
        </p>
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
import { ArrowRight, CheckCircle2, CircleX, ClipboardCheck, GitBranchPlus, Pause, Play, SquarePlay, ThumbsDown, ThumbsUp } from 'lucide-vue-next'
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
const compositionAnswer = ref<'right_then_left' | 'left_then_right' | ''>('')
const recordedInteractions = new Set<string>()
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
const isLinearCompositionAnimation = computed(() => (
  animationSpec.value?.scene?.renderer === 'linear_transform_composition_v1'
))
const compositionAnswerCorrect = computed(() => compositionAnswer.value === 'right_then_left')
const gridLines = [-40, -20, 20, 40]
const compositionShapePoints = computed(() => String(
  activeKeyframe.value?.state?.shape_points || '0,0 35,0 0,-25',
))
const compositionVector = computed(() => ({
  x: Number(activeKeyframe.value?.state?.vector_x || 35),
  y: Number(activeKeyframe.value?.state?.vector_y || 0),
}))
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

function recordInteraction(
  interaction: 'animation_played' | 'animation_answered' | 'validation_started',
  details: {
    answer?: 'right_then_left' | 'left_then_right'
    correct?: boolean
    frame_index?: number
  } = {},
) {
  const block = supportBlock.value
  const courseId = courseStore.currentCourseId
  const interactionKey = `${interaction}:${details.answer || ''}:${String(details.correct ?? '')}`
  if (!block || !courseId || recordedInteractions.has(interactionKey)) return
  recordedInteractions.add(interactionKey)
  void progressStore.recordAdaptiveBlockInteraction(courseId, block, interaction, details)
    .then(recorded => {
      if (!recorded) recordedInteractions.delete(interactionKey)
    })
}

function answerComposition(answer: 'right_then_left' | 'left_then_right') {
  stopAnimation()
  compositionAnswer.value = answer
  const correct = answer === 'right_then_left'
  recordInteraction('animation_answered', {
    answer,
    correct,
    frame_index: activeFrame.value,
  })
  if (correct && activeFrame.value === 0) activeFrame.value = 1
}

function selectFrame(index: number) {
  stopAnimation()
  if (activeFrame.value !== index) recordInteraction('animation_played')
  activeFrame.value = index
}

function startPractice() {
  recordInteraction('validation_started')
  emit('startPractice', practiceTaskId.value)
}

function toggleAnimation() {
  if (isPlaying.value) return stopAnimation()
  const frames = animationSpec.value?.keyframes || []
  if (frames.length < 2) return
  if (activeFrame.value >= frames.length - 1) activeFrame.value = 0
  recordInteraction('animation_played')
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
.course-evolution-animation__frame.is-composition { min-height:184px; display:grid; grid-template-columns:1fr; align-content:start; padding:10px; }
.composition-formula { display:flex; align-items:center; justify-content:center; gap:7px; color:#94a3b8; }
.composition-formula span { min-width:38px; padding:4px 7px; border:1px solid #e2e8f0; border-radius:6px; background:#fff; text-align:center; font-size:10px; font-weight:800; transition:color .18s ease,border-color .18s ease,background .18s ease; }
.composition-formula span.active { color:#fff; border-color:#7c3aed; background:#7c3aed; }
.composition-formula span.reached { color:#047857; border-color:#a7f3d0; background:#ecfdf5; }
.composition-formula svg { flex:0 0 auto; }
.composition-stage { min-width:0; display:grid; grid-template-columns:132px minmax(0,1fr); align-items:center; gap:12px; margin-top:8px; }
.composition-stage > svg { width:132px; height:132px; overflow:visible; border:1px solid #e2e8f0; border-radius:7px; background:#fff; }
.composition-grid line { stroke:#eef2f7; stroke-width:.8; }
.composition-axis { stroke:#94a3b8; stroke-width:1.1; }
.composition-shape { fill:rgba(20,184,166,.2); stroke:#0f766e; stroke-width:2; stroke-linejoin:round; transition:all .24s ease; }
.composition-vector { stroke:#7c3aed; stroke-width:2.4; stroke-linecap:round; transition:all .24s ease; }
.composition-vector-tip { fill:#7c3aed; transition:all .24s ease; }
.composition-origin { fill:#334155; }
.composition-copy { min-width:0; display:flex; flex-direction:column; align-items:flex-start; gap:4px; }
.composition-copy small { color:#7c3aed; font-size:9px; font-weight:800; }
.composition-copy b { padding:3px 6px; border-radius:5px; color:#0f766e; background:#ecfdf5; font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:11px; }
.composition-copy strong { color:var(--lz-text); font-size:11px; }
.composition-copy p { color:var(--lz-text-secondary); font-size:10px; line-height:1.55; }
.course-evolution-animation__timeline { display:flex; gap:5px; }
.course-evolution-animation__timeline button { width:25px; height:25px; border:1px solid #ddd6fe; border-radius:50%; background:#fff; font-size:9px; }
.course-evolution-animation__timeline button.active { color:#fff; border-color:#7c3aed; background:#7c3aed; }
.composition-check { display:grid; gap:7px; padding:10px; border:1px solid #e2e8f0; border-radius:7px; background:#f8fafc; }
.composition-check > small { color:#7c3aed; font-size:9px; font-weight:800; }
.composition-check > p { margin:0; color:var(--lz-text); font-size:10px; line-height:1.5; }
.composition-check > div { display:grid; grid-template-columns:1fr 1fr; gap:6px; }
.composition-check > div button { width:auto; min-width:0; height:32px; padding:0 8px; border:1px solid #ddd6fe; border-radius:6px; color:#5b21b6; background:#fff; font-size:10px; font-weight:700; }
.composition-check > div button:hover { border-color:#8b5cf6; background:#faf5ff; }
.composition-check > div button.correct { color:#047857; border-color:#6ee7b7; background:#ecfdf5; }
.composition-check > div button.wrong { color:#b91c1c; border-color:#fecaca; background:#fef2f2; }
.composition-check__result { display:flex; align-items:flex-start; gap:5px; color:#475569 !important; }
.composition-check__result svg { flex:0 0 auto; margin-top:1px; }
.composition-check__result svg { color:#dc2626; }
.composition-check__result.is-correct svg { color:#059669; }
.course-evolution-content footer { display:flex; align-items:center; justify-content:space-between; gap:12px; margin:13px 12px 0 0; padding-top:10px; border-top:1px solid rgba(221,214,254,.7); }
.course-evolution-content footer > span { display:flex; flex-wrap:wrap; align-items:center; gap:5px; color:var(--lz-text-muted); font-size:9px; line-height:1.5; }
.course-evolution-content footer b { color:#6d28d9; }
.course-evolution-content footer > div { display:flex; gap:3px; }
.course-evolution-content footer button.active { color:#fff; background:#7c3aed; }
@media (max-width:560px) {
  .composition-stage { grid-template-columns:1fr; }
  .composition-stage > svg { width:min(100%,180px); height:auto; aspect-ratio:1; margin:0 auto; }
}
</style>
