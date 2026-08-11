<template>
  <section v-if="!dismissed" class="adaptive-block" :data-kind="block.kind">
    <header>
      <span class="adaptive-block__icon"><component :is="kindIcon" :size="17" /></span>
      <div>
        <small>{{ t('adaptiveBlocks.eyebrow', 'AI 临时支持') }}</small>
        <strong>{{ kindLabel }}</strong>
      </div>
      <div class="adaptive-block__actions">
        <button type="button" :title="collapsed ? t('adaptiveBlocks.expand', '展开') : t('adaptiveBlocks.collapse', '收起')" @click="collapsed = !collapsed">
          <ChevronDown v-if="collapsed" :size="16" />
          <ChevronUp v-else :size="16" />
        </button>
        <button type="button" :title="t('adaptiveBlocks.dismiss', '跳过这条支持')" @click="sendFeedback('dismissed')">
          <X :size="16" />
        </button>
      </div>
    </header>

    <div v-if="!collapsed" class="adaptive-block__body">
      <p>{{ block.payload.body }}</p>
      <p v-if="block.payload.contrast" class="adaptive-block__contrast">{{ block.payload.contrast }}</p>
      <div v-if="structuredAnimation" class="structured-animation" :aria-label="structuredAnimation.accessibility_text">
        <div class="structured-animation__header">
          <span><SquarePlay :size="14" />{{ t('adaptiveBlocks.structuredAnimation', '结构化动画') }}</span>
          <div class="structured-animation__controls">
            <button
              type="button"
              :title="t('adaptiveBlocks.previousFrame', '上一步')"
              :disabled="activeFrame === 0"
              @click="previousFrame"
            ><ChevronLeft :size="14" /></button>
            <button
              type="button"
              class="structured-animation__play"
              :title="isPlaying
                ? t('adaptiveBlocks.pauseAnimation', '暂停动画')
                : activeFrame === structuredAnimation.keyframes.length - 1
                  ? t('adaptiveBlocks.restartAnimation', '重新播放')
                  : t('adaptiveBlocks.playAnimation', '播放动画')"
              @click="toggleAnimation"
            >
              <Pause v-if="isPlaying" :size="14" /><Play v-else :size="14" />
            </button>
            <button
              type="button"
              :title="t('adaptiveBlocks.nextFrame', '下一步')"
              :disabled="activeFrame === structuredAnimation.keyframes.length - 1"
              @click="nextFrame"
            ><ChevronRight :size="14" /></button>
          </div>
        </div>
        <strong>{{ structuredAnimation.title }}</strong>
        <Transition name="frame-shift" mode="out-in">
          <div :key="activeKeyframe.index" class="structured-animation__frame" aria-live="polite">
            <small>{{ activeKeyframe.index }} / {{ structuredAnimation.keyframes.length }}</small>
            <b>{{ activeKeyframe.label }}</b>
            <p>{{ activeKeyframe.state.description }}</p>
          </div>
        </Transition>
        <ol class="structured-animation__timeline" :aria-label="t('adaptiveBlocks.animationTimeline', '动画步骤')">
          <li v-for="(frame, index) in structuredAnimation.keyframes" :key="frame.index" :class="{ active: activeFrame === index, complete: activeFrame > index }">
            <button
              type="button"
              :aria-current="activeFrame === index ? 'step' : undefined"
              :aria-label="t('adaptiveBlocks.selectFrame', '查看第 {index} 步：{label}').replace('{index}', String(frame.index)).replace('{label}', frame.label)"
              @click="selectFrame(index)"
            >{{ frame.index }}</button>
          </li>
        </ol>
      </div>
      <ol v-else-if="block.payload.steps?.length" class="adaptive-block__steps">
        <li v-for="step in block.payload.steps" :key="step.index"><span>{{ step.index }}</span>{{ step.label }}</li>
      </ol>
      <p v-if="structuredAnimation" class="adaptive-block__fallback">
        {{ t('adaptiveBlocks.animationFallbackAvailable', '每个关键帧都可暂停；动态渲染失败时自动保留为静态步骤。') }}
      </p>
      <p v-else-if="block.kind === 'animation' && block.payload.steps?.length" class="adaptive-block__fallback">
        {{ t('adaptiveBlocks.animationFallback', '当前使用可验证的静态分步演示；动态渲染不可用时，学习步骤仍然完整保留。') }}
      </p>
      <div v-if="block.kind === 'understanding_check' && block.payload.prompt" class="adaptive-block__check">
        <CircleHelp :size="16" />
        <span>
          {{ block.payload.prompt }}
          <small>{{ t('adaptiveBlocks.informal', '先自查，不计入掌握判断') }}</small>
        </span>
        <button
          v-if="practiceAvailable"
          type="button"
          class="adaptive-block__verify"
          @click="startFormalValidation"
        >
          <ClipboardCheck :size="14" />
          {{ t('adaptiveBlocks.startFormalValidation', '进行独立复验') }}
        </button>
      </div>
      <footer>
        <span><ShieldCheck :size="14" />{{ t(`adaptiveBlocks.reasons.${block.reason_code}`, t('adaptiveBlocks.evidenceBased', '基于当前学习证据')) }}</span>
        <div :aria-label="t('adaptiveBlocks.feedback', '这条支持是否有帮助')">
          <button type="button" :class="{ active: feedback === 'helpful' }" :title="t('adaptiveBlocks.helpful', '有帮助')" @click="sendFeedback('helpful')">
            <ThumbsUp :size="15" />
          </button>
          <button type="button" :class="{ active: feedback === 'not_helpful' }" :title="t('adaptiveBlocks.notHelpful', '没有帮助')" @click="sendFeedback('not_helpful')">
            <ThumbsDown :size="15" />
          </button>
        </div>
      </footer>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { ArrowRight, ChevronDown, ChevronLeft, ChevronRight, ChevronUp, CircleHelp, ClipboardCheck, Lightbulb, Pause, Play, ScanSearch, ShieldCheck, SquarePlay, ThumbsDown, ThumbsUp, X } from 'lucide-vue-next'
import { useCourseStore } from '../stores/course'
import { useLearningProgressStore, type AdaptiveBlockFeedback, type AdaptiveLearningBlock } from '../stores/learningProgress'
import { t } from '../shared/i18n'

const props = withDefaults(defineProps<{
  block: AdaptiveLearningBlock
  practiceAvailable?: boolean
}>(), { practiceAvailable: false })
const emit = defineEmits<{ (event: 'verify'): void }>()
const courseStore = useCourseStore()
const progressStore = useLearningProgressStore()
const collapsed = ref(false)
const dismissed = ref(false)
const feedback = ref<AdaptiveBlockFeedback>(props.block.feedback.value)
const activeFrame = ref(0)
const isPlaying = ref(false)
let animationTimer: number | undefined
const reduceMotion = typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
const structuredAnimation = computed(() => (
  props.block.kind === 'animation'
  && props.block.payload.animation_spec?.schema_version === 'animation_spec_v1'
  && props.block.payload.animation_spec.keyframes?.length
    ? props.block.payload.animation_spec
    : null
))
const activeKeyframe = computed(() => structuredAnimation.value?.keyframes[activeFrame.value] || {
  index: 1,
  label: '',
  state: { description: '' },
})
const kindIcon = computed(() => ({
  explanation: Lightbulb,
  counterexample: ScanSearch,
  transition: ArrowRight,
  understanding_check: CircleHelp,
  animation: SquarePlay,
}[props.block.kind]))
const kindLabel = computed(() => t(`adaptiveBlocks.kinds.${props.block.kind}`, t('adaptiveBlocks.kinds.explanation', '补充解释')))

const sendFeedback = (value: Exclude<AdaptiveBlockFeedback, 'unrated'>) => {
  feedback.value = value
  if (value === 'dismissed') dismissed.value = true
  void progressStore.feedbackAdaptiveBlock(courseStore.currentCourseId, props.block, value)
}

const stopAnimation = () => {
  if (animationTimer !== undefined) window.clearTimeout(animationTimer)
  animationTimer = undefined
  isPlaying.value = false
}
const selectFrame = (index: number) => {
  stopAnimation()
  activeFrame.value = index
}
const previousFrame = () => selectFrame(Math.max(0, activeFrame.value - 1))
const nextFrame = () => {
  const finalIndex = Math.max(0, (structuredAnimation.value?.keyframes.length || 1) - 1)
  selectFrame(Math.min(finalIndex, activeFrame.value + 1))
}
const scheduleNextFrame = () => {
  const frames = structuredAnimation.value?.keyframes || []
  if (!isPlaying.value || activeFrame.value >= frames.length - 1) return stopAnimation()
  const duration = Math.max(500, frames[activeFrame.value]?.duration_ms || 1200)
  animationTimer = window.setTimeout(() => {
    activeFrame.value += 1
    scheduleNextFrame()
  }, duration)
}
const toggleAnimation = () => {
  if (isPlaying.value) return stopAnimation()
  const frames = structuredAnimation.value?.keyframes || []
  if (frames.length < 2) return
  void progressStore.recordAdaptiveBlockInteraction(
    courseStore.currentCourseId,
    props.block,
    'animation_played',
  )
  if (reduceMotion) {
    activeFrame.value = activeFrame.value >= frames.length - 1 ? 0 : activeFrame.value + 1
    return
  }
  if (activeFrame.value >= frames.length - 1) activeFrame.value = 0
  isPlaying.value = true
  scheduleNextFrame()
}
const startFormalValidation = () => {
  void progressStore.recordAdaptiveBlockInteraction(
    courseStore.currentCourseId,
    props.block,
    'validation_started',
  )
  emit('verify')
}
onBeforeUnmount(stopAnimation)
</script>

<style scoped>
.adaptive-block { position:relative; margin:24px 0 4px; padding:17px 0 15px 18px; border-left:1px solid #818cf8; color:var(--lz-text); background:linear-gradient(90deg,rgba(238,242,255,.72),rgba(255,255,255,0)); }
.adaptive-block[data-kind="counterexample"] { border-left-color:#f59e0b; background:linear-gradient(90deg,rgba(255,251,235,.78),rgba(255,255,255,0)); }
.adaptive-block[data-kind="transition"] { border-left-color:#22c55e; background:linear-gradient(90deg,rgba(240,253,244,.72),rgba(255,255,255,0)); }
.adaptive-block[data-kind="animation"] { border-left-color:#8b5cf6; background:linear-gradient(90deg,rgba(245,243,255,.8),rgba(255,255,255,0)); }
.adaptive-block header { min-height:34px; display:grid; grid-template-columns:34px minmax(0,1fr) auto; align-items:center; gap:10px; }
.adaptive-block__icon { width:34px; height:34px; display:grid; place-items:center; border-radius:9px; color:#4f46e5; background:rgba(255,255,255,.88); box-shadow:0 2px 8px rgba(79,70,229,.09); }
.adaptive-block header div:nth-child(2) { min-width:0; display:flex; flex-direction:column; gap:2px; }
.adaptive-block header small { color:var(--lz-text-muted); font-size:9px; font-weight:700; }
.adaptive-block header strong { color:var(--lz-text-strong); font-size:14px; }
.adaptive-block__actions { display:flex; gap:3px; }
.adaptive-block button { width:30px; height:30px; display:grid; place-items:center; border:0; border-radius:6px; color:var(--lz-text-muted); background:transparent; cursor:pointer; }
.adaptive-block button:hover,.adaptive-block button.active { color:var(--lz-brand-strong); background:rgba(255,255,255,.9); }
.adaptive-block__body { padding:12px 40px 0 44px; }
.adaptive-block__body > p { margin:0; color:var(--lz-text-secondary); font-size:13px; line-height:1.75; }
.adaptive-block__contrast { margin-top:7px!important; color:var(--lz-text)!important; }
.adaptive-block__steps { display:grid; gap:7px; margin:12px 0 0; padding:0; list-style:none; }.adaptive-block__steps li { display:grid; grid-template-columns:22px minmax(0,1fr); align-items:center; gap:8px; color:var(--lz-text-secondary); font-size:12px; }.adaptive-block__steps span { width:22px; height:22px; display:grid; place-items:center; border-radius:50%; color:#fff; background:#6366f1; font-size:9px; font-weight:800; }
.structured-animation {
  display:grid;
  gap:9px;
  margin-top:12px;
  padding:12px 0 11px;
  border-top:1px solid rgba(139,92,246,.2);
  border-bottom:1px solid rgba(139,92,246,.16);
}
.structured-animation__header {
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:8px;
}
.structured-animation__header > span {
  display:inline-flex;
  align-items:center;
  gap:5px;
  color:#6d28d9;
  font-size:9px;
  font-weight:800;
}
.structured-animation__controls {
  display:flex;
  align-items:center;
  gap:3px;
}
.structured-animation__controls button {
  width:28px;
  height:28px;
  color:#6d28d9;
  background:transparent;
}
.structured-animation__controls button:hover:not(:disabled) {
  color:#5b21b6;
  background:#f5f3ff;
}
.structured-animation__controls button:disabled {
  opacity:.32;
  cursor:default;
}
.structured-animation__controls .structured-animation__play {
  border:1px solid #ddd6fe;
  background:#f5f3ff;
}
.structured-animation > strong {
  color:var(--lz-text-strong);
  font-size:12px;
}
.structured-animation__frame {
  min-height:64px;
  display:grid;
  grid-template-columns:34px minmax(0,1fr);
  align-content:center;
  gap:4px 8px;
  padding:3px 0;
}
.structured-animation__frame small {
  grid-row:1 / 3;
  align-self:start;
  color:#7c3aed;
  font-size:9px;
  font-weight:800;
}
.structured-animation__frame b { color:var(--lz-text); font-size:11px; }
.structured-animation__frame p { margin:0; color:var(--lz-text-secondary); font-size:10px; line-height:1.55; }
.structured-animation__timeline {
  display:flex;
  align-items:center;
  margin:0;
  padding:0;
  list-style:none;
}
.structured-animation__timeline li {
  position:relative;
  flex:1 1 0;
  display:flex;
  align-items:center;
}
.structured-animation__timeline li:not(:last-child)::after {
  content:"";
  height:1px;
  flex:1 1 auto;
  background:#ddd6fe;
}
.structured-animation__timeline li.complete:not(:last-child)::after { background:#8b5cf6; }
.structured-animation__timeline button {
  width:24px;
  height:24px;
  flex:0 0 auto;
  border:1px solid #ddd6fe;
  border-radius:50%;
  color:#7c3aed;
  background:#fff;
  font-size:9px;
  transition:transform .18s cubic-bezier(.16,1,.3,1), color .18s ease, border-color .18s ease, background .18s ease;
}
.structured-animation__timeline li.active button {
  color:#fff;
  border-color:#7c3aed;
  background:#7c3aed;
  transform:scale(1.08);
}
.structured-animation__timeline li.complete button {
  border-color:#8b5cf6;
  color:#6d28d9;
  background:#f5f3ff;
}
.frame-shift-enter-active,
.frame-shift-leave-active {
  transition:opacity .18s ease, transform .18s cubic-bezier(.16,1,.3,1), filter .18s ease;
}
.frame-shift-enter-from {
  opacity:0;
  transform:translateX(8px);
  filter:blur(2px);
}
.frame-shift-leave-to {
  opacity:0;
  transform:translateX(-5px);
  filter:blur(1px);
}
.adaptive-block__fallback { margin-top:9px!important; color:#7c3aed!important; font-size:10px!important; }
.adaptive-block__check { margin-top:11px; display:grid; grid-template-columns:18px minmax(0,1fr) auto; align-items:center; gap:8px; padding:9px 10px; border:1px solid rgba(165,180,252,.56); border-radius:8px; background:rgba(255,255,255,.7); color:var(--lz-text); font-size:12px; }
.adaptive-block__check > span { min-width:0; display:flex; flex-direction:column; gap:3px; line-height:1.5; }
.adaptive-block__check small { color:var(--lz-text-muted); font-size:9px; white-space:normal; }
.adaptive-block .adaptive-block__verify { width:auto; min-height:30px; display:inline-flex; grid-auto-flow:column; align-items:center; gap:5px; padding:0 9px; color:#fff; background:#4f46e5; font-size:9px; font-weight:750; white-space:nowrap; }
.adaptive-block .adaptive-block__verify:hover { color:#fff; background:#4338ca; }
.adaptive-block footer { margin-top:12px; display:flex; align-items:center; justify-content:space-between; gap:12px; }
.adaptive-block footer > span { display:inline-flex; align-items:center; gap:5px; color:var(--lz-text-muted); font-size:9px; }
.adaptive-block footer > div { display:flex; gap:3px; }
@media (max-width:640px) {
  .adaptive-block { margin-top:20px; padding-left:13px; }
  .adaptive-block__body { padding:10px 4px 0 44px; }
  .adaptive-block__check { grid-template-columns:18px minmax(0,1fr); }
  .adaptive-block__verify { grid-column:2; justify-self:start; }
}
@media (prefers-reduced-motion:reduce) {
  .structured-animation__timeline button,
  .frame-shift-enter-active,
  .frame-shift-leave-active { transition:none; }
  .structured-animation__timeline li.active button { transform:none; }
}
</style>
