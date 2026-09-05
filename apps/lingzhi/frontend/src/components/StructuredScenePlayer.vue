<template>
  <section class="scene-player" :data-playing="playing ? 'true' : 'false'" :data-scene-version="sceneVersion">
    <svg
      v-if="validV2"
      viewBox="0 0 800 420"
      role="img"
      :aria-label="sceneTitle"
      class="scene-canvas scene-canvas-v2"
    >
      <title>{{ sceneTitle }}</title>
      <defs>
        <marker id="scene-arrow-head" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M 0 0 L 10 5 L 0 10 z" />
        </marker>
      </defs>
      <g
        v-for="object in sceneObjects"
        :key="object.object_id"
        class="scene-object scene-primitive"
        :class="[`kind-${object.kind}`, { focused: isPulsing(object.object_id) }]"
        :data-object-id="object.object_id"
        :data-kind="object.kind"
        :transform="objectTransform(object)"
        :style="objectStyle(object)"
      >
        <circle
          v-if="object.kind === 'circle'"
          cx="0"
          cy="0"
          :r="radiusPx(object)"
          :fill="color(object.fill)"
          :stroke="color(object.stroke)"
          :stroke-width="object.stroke_width || 1.5"
        />
        <line
          v-if="object.kind === 'circle'"
          x1="0"
          y1="0"
          :x2="radiusPx(object) * 0.82"
          y2="0"
          :stroke="color(object.stroke)"
          stroke-width="2"
          stroke-linecap="round"
        />
        <rect
          v-else-if="object.kind === 'rect'"
          :x="-widthPx(object) / 2"
          :y="-heightPx(object) / 2"
          :width="widthPx(object)"
          :height="heightPx(object)"
          rx="10"
          :fill="color(object.fill)"
          :stroke="color(object.stroke)"
          :stroke-width="object.stroke_width || 1.5"
        />
        <polygon
          v-else-if="object.kind === 'polygon'"
          :points="pointsAttribute(object.points)"
          :fill="color(object.fill)"
          :stroke="color(object.stroke)"
          :stroke-width="object.stroke_width || 1.5"
          stroke-linejoin="round"
        />
        <polyline
          v-else-if="object.kind === 'line'"
          :points="pointsAttribute(object.points)"
          fill="none"
          :stroke="color(object.stroke)"
          :stroke-width="object.stroke_width || 1.5"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
        <polyline
          v-else-if="object.kind === 'arrow'"
          :points="pointsAttribute(object.points)"
          fill="none"
          :stroke="color(object.stroke)"
          :stroke-width="object.stroke_width || 1.5"
          stroke-linecap="round"
          stroke-linejoin="round"
          marker-end="url(#scene-arrow-head)"
        />
        <polyline
          v-else-if="object.kind === 'path'"
          :points="pointsAttribute(object.points)"
          fill="none"
          :stroke="color(object.stroke)"
          :stroke-width="object.stroke_width || 1.5"
          stroke-linecap="round"
          stroke-linejoin="round"
          pathLength="100"
          :style="traceStyle(object.object_id)"
        />
        <text
          v-else-if="object.kind === 'text'"
          x="0"
          y="0"
          class="scene-text"
          :fill="color(object.fill)"
          text-anchor="middle"
          dominant-baseline="middle"
        >{{ object.label }}</text>
        <text
          v-if="object.label && object.kind === 'circle'"
          x="0"
          :y="-(radiusPx(object) + 10)"
          class="scene-label"
          text-anchor="middle"
        >{{ object.label }}</text>
        <text
          v-else-if="object.label && ['line', 'polygon', 'arrow'].includes(object.kind)"
          :x="labelPosition(object).x"
          :y="labelPosition(object).y"
          class="scene-label"
          text-anchor="middle"
        >{{ object.label }}</text>
      </g>
    </svg>

    <svg
      v-else-if="validV1"
      viewBox="0 0 800 300"
      role="img"
      :aria-label="sceneTitle"
      class="scene-canvas"
    >
      <title>{{ sceneTitle }}</title>
      <g class="scene-connections">
        <line
          v-for="edge in visibleConnections"
          :key="edge.action_id"
          :x1="legacyPosition(edge.target_ids[0] || '').x"
          :y1="legacyPosition(edge.target_ids[0] || '').y"
          :x2="legacyPosition(edge.target_ids[1] || '').x"
          :y2="legacyPosition(edge.target_ids[1] || '').y"
        />
      </g>
      <g
        v-for="object in legacyObjects"
        :key="object.object_id"
        class="legacy-scene-object"
        :class="{ visible: visibleIds.has(object.object_id), focused: focusedIds.has(object.object_id) }"
        :data-object-id="object.object_id"
        :transform="`translate(${object.x * 7.2 + 40} ${object.y * 2.2 + 30})`"
      >
        <rect x="-88" y="-30" width="176" height="60" rx="12" />
        <foreignObject x="-76" y="-22" width="152" height="44">
          <div xmlns="http://www.w3.org/1999/xhtml"><MathText :content="object.label" /></div>
        </foreignObject>
      </g>
    </svg>
    <DiagramSpecRenderer
      v-else-if="fallbackUnit"
      :unit="fallbackUnit"
      :title="sceneTitle"
    />
    <p v-else class="scene-unavailable">{{ tr('unavailable', '动画规格暂时无法播放', 'This animation cannot be played yet') }}</p>

    <div v-if="validV2" class="scene-purpose">
      <strong>{{ sceneModeLabel }}</strong>
      <span>{{ String(scene.learning_focus || '') }}</span>
    </div>
    <div class="scene-progress" aria-live="polite">
      <span>{{ currentCheckpoint?.label || sceneTitle }}</span>
      <small>{{ Math.min(currentIndex + 1, checkpoints.length) }}/{{ checkpoints.length }}</small>
    </div>
    <nav class="scene-controls" :aria-label="tr('controls', '动画播放控制', 'Animation controls')">
      <button type="button" :disabled="currentIndex <= 0" @click="previous">
        <StepBack :size="15" />{{ tr('previous', '上一步', 'Previous') }}
      </button>
      <button v-if="!playing" type="button" class="primary" :disabled="!valid" @click="play">
        <Play :size="15" />{{ tr('play', '播放', 'Play') }}
      </button>
      <button v-else type="button" class="primary" @click="pause">
        <Pause :size="15" />{{ tr('pause', '暂停', 'Pause') }}
      </button>
      <button type="button" :disabled="currentIndex >= checkpoints.length - 1" @click="next">
        <StepForward :size="15" />{{ tr('next', '下一步', 'Next') }}
      </button>
      <button type="button" :disabled="!valid" @click="replay">
        <RotateCcw :size="15" />{{ tr('replay', '重新播放', 'Replay') }}
      </button>
    </nav>
  </section>
</template>

<script setup lang="ts">
import { computed, onUnmounted, ref } from 'vue'
import { Pause, Play, RotateCcw, StepBack, StepForward } from 'lucide-vue-next'
import DiagramSpecRenderer from './DiagramSpecRenderer.vue'
import MathText from './MathText.vue'
import { activeLocale, t } from '../shared/i18n'

interface ScenePoint { x: number; y: number }
interface SceneObjectV1 { object_id: string; label: string; kind: string; x: number; y: number }
interface SceneObjectV2 {
  object_id: string
  label: string
  kind: 'circle' | 'rect' | 'line' | 'polygon' | 'path' | 'arrow' | 'text'
  x: number
  y: number
  width: number
  height: number
  radius: number
  points: ScenePoint[]
  fill: string
  stroke: string
  stroke_width: number
  visible: boolean
}
interface SceneActionV1 {
  action_id: string
  action_type: 'reveal' | 'focus' | 'connect'
  target_ids: string[]
  start_ms: number
  duration_ms: number
}
interface SceneActionV2 {
  action_id: string
  action_type: 'reveal' | 'move' | 'rotate' | 'pulse' | 'trace'
  target_id: string
  start_ms: number
  duration_ms: number
  easing: 'linear' | 'accelerate' | 'decelerate' | 'ease_in_out'
  path: ScenePoint[]
  from_rotation: number
  to_rotation: number
}
interface SceneCheckpoint { checkpoint_id: string; label: string; at_ms: number }

const props = defineProps<{ scene: Record<string, any> }>()
const currentIndex = ref(0)
const elapsedMs = ref(0)
const playing = ref(false)
let animationFrame = 0
let playStartedAt = 0
let playStartedMs = 0

function tr(key: string, zh: string, en: string) {
  return t(`courseWorkbench.scriptVisual.scene.${key}`, activeLocale.value === 'en' ? en : zh)
}

const sceneVersion = computed(() => String(props.scene?.schema_version || 'unknown'))
const legacyObjects = computed<SceneObjectV1[]>(() => Array.isArray(props.scene?.objects)
  ? props.scene.objects.filter(item => (
      item && typeof item.object_id === 'string' && typeof item.label === 'string'
      && Number.isFinite(item.x) && Number.isFinite(item.y)
    ))
  : [])
const legacyActions = computed<SceneActionV1[]>(() => Array.isArray(props.scene?.actions)
  ? props.scene.actions.filter(item => (
      item && typeof item.action_id === 'string' && Array.isArray(item.target_ids)
      && ['reveal', 'focus', 'connect'].includes(item.action_type)
      && Number.isFinite(item.start_ms)
    ))
  : [])
const sceneObjects = computed<SceneObjectV2[]>(() => Array.isArray(props.scene?.objects)
  ? props.scene.objects.filter(item => (
      item && typeof item.object_id === 'string'
      && ['circle', 'rect', 'line', 'polygon', 'path', 'arrow', 'text'].includes(item.kind)
    ))
  : [])
const sceneActions = computed<SceneActionV2[]>(() => Array.isArray(props.scene?.actions)
  ? props.scene.actions.filter(item => (
      item && typeof item.action_id === 'string' && typeof item.target_id === 'string'
      && ['reveal', 'move', 'rotate', 'pulse', 'trace'].includes(item.action_type)
      && Number.isFinite(item.start_ms) && Number.isFinite(item.duration_ms)
    )).sort((left, right) => left.start_ms - right.start_ms)
  : [])
const checkpoints = computed<SceneCheckpoint[]>(() => Array.isArray(props.scene?.checkpoints)
  ? props.scene.checkpoints.filter(item => (
      item && typeof item.checkpoint_id === 'string' && typeof item.label === 'string'
      && Number.isFinite(item.at_ms)
    )).sort((left, right) => left.at_ms - right.at_ms)
  : [])
const legacyObjectIds = computed(() => new Set(legacyObjects.value.map(item => item.object_id)))
const sceneObjectIds = computed(() => new Set(sceneObjects.value.map(item => item.object_id)))
const validV1 = computed(() => (
  props.scene?.schema_version === 'scene_spec_v1'
  && legacyObjects.value.length >= 2
  && checkpoints.value.length >= 2
  && legacyActions.value.every(action => action.target_ids.every(id => legacyObjectIds.value.has(id)))
))
const validV2 = computed(() => (
  props.scene?.schema_version === 'scene_spec_v2'
  && sceneObjects.value.length >= 2
  && checkpoints.value.length >= 2
  && sceneActions.value.length >= 1
  && sceneActions.value.every(action => sceneObjectIds.value.has(action.target_id))
))
const valid = computed(() => validV1.value || validV2.value)
const sceneTitle = computed(() => String(props.scene?.title || tr('title', '结构化动画', 'Structured animation')))
const currentCheckpoint = computed(() => checkpoints.value[currentIndex.value])
const visibleIds = computed(() => new Set(
  legacyActions.value
    .filter(action => action.action_type === 'reveal' && action.start_ms <= elapsedMs.value)
    .flatMap(action => action.target_ids),
))
const focusedIds = computed(() => new Set(
  legacyActions.value
    .filter(action => action.action_type === 'focus' && action.start_ms <= elapsedMs.value)
    .slice(-1)
    .flatMap(action => action.target_ids),
))
const visibleConnections = computed(() => legacyActions.value.filter(action => (
  action.action_type === 'connect'
  && action.start_ms <= elapsedMs.value
  && action.target_ids.length === 2
)))
const fallbackUnit = computed(() => props.scene?.static_fallback?.unit || null)
const sceneModeLabel = computed(() => props.scene?.generation_mode === 'ai_planned'
  ? tr('aiPlanned', 'AI 场景动画', 'AI-planned scene')
  : tr('templatePlanned', '可运动场景动画', 'Motion scene'))

const palette: Record<string, string> = {
  ink: '#344054', primary: '#514bdc', accent: '#3b82f6', warm: '#f59e0b',
  muted: '#e9edf5', success: '#16a34a', danger: '#dc4c64',
}
function color(value: string) { return palette[value] || palette.ink }
function xPx(value: number) { return Number(value || 0) * 8 }
function yPx(value: number) { return Number(value || 0) * 4.2 }
function radiusPx(object: SceneObjectV2) { return Number(object.radius || 0) * 4.2 }
function widthPx(object: SceneObjectV2) { return Number(object.width || 0) * 8 }
function heightPx(object: SceneObjectV2) { return Number(object.height || 0) * 4.2 }
function pointsAttribute(points: ScenePoint[] = []) {
  return points.map(point => `${xPx(point.x)},${yPx(point.y)}`).join(' ')
}
function labelPosition(object: SceneObjectV2) {
  const points = object.points || []
  if (!points.length) return { x: 0, y: 0 }
  return {
    x: points.reduce((sum, point) => sum + xPx(point.x), 0) / points.length,
    y: points.reduce((sum, point) => sum + yPx(point.y), 0) / points.length - 8,
  }
}
function actionProgress(action: SceneActionV2) {
  if (elapsedMs.value <= action.start_ms) return 0
  if (elapsedMs.value >= action.start_ms + action.duration_ms) return 1
  return (elapsedMs.value - action.start_ms) / action.duration_ms
}
function eased(progress: number, easing: SceneActionV2['easing']) {
  if (easing === 'accelerate') return progress * progress
  if (easing === 'decelerate') return 1 - ((1 - progress) * (1 - progress))
  if (easing === 'ease_in_out') return progress < 0.5
    ? 2 * progress * progress
    : 1 - Math.pow(-2 * progress + 2, 2) / 2
  return progress
}
function pointOnPath(points: ScenePoint[], progress: number): ScenePoint {
  const first = points[0]
  if (!first) return { x: 0, y: 0 }
  const last = points[points.length - 1] || first
  if (points.length === 1 || progress <= 0) return first
  if (progress >= 1) return last
  const scaled = progress * (points.length - 1)
  const index = Math.min(points.length - 2, Math.floor(scaled))
  const local = scaled - index
  const from = points[index] || first
  const to = points[index + 1] || last
  return {
    x: from.x + ((to.x - from.x) * local),
    y: from.y + ((to.y - from.y) * local),
  }
}
function objectState(object: SceneObjectV2) {
  let x = Number(object.x || 0)
  let y = Number(object.y || 0)
  let rotation = 0
  let scale = 1
  let opacity = object.visible === false ? 0 : 1
  for (const action of sceneActions.value.filter(item => item.target_id === object.object_id)) {
    const progress = actionProgress(action)
    const motionProgress = eased(progress, action.easing || 'linear')
    if (action.action_type === 'move' && action.path?.length >= 2) {
      const point = pointOnPath(action.path, motionProgress)
      x = point.x
      y = point.y
    } else if (action.action_type === 'rotate') {
      rotation = Number(action.from_rotation || 0)
        + ((Number(action.to_rotation || 0) - Number(action.from_rotation || 0)) * motionProgress)
    } else if (action.action_type === 'reveal') {
      opacity = progress
    } else if (action.action_type === 'pulse' && progress > 0 && progress < 1) {
      scale = 1 + (Math.sin(Math.PI * progress) * 0.12)
    }
  }
  return { x, y, rotation, scale, opacity }
}
function objectTransform(object: SceneObjectV2) {
  if (['line', 'polygon', 'path', 'arrow'].includes(object.kind)) return ''
  const state = objectState(object)
  return `translate(${xPx(state.x)} ${yPx(state.y)}) rotate(${state.rotation}) scale(${state.scale})`
}
function objectStyle(object: SceneObjectV2) {
  const state = objectState(object)
  if (object.kind === 'path') return { opacity: traceProgress(object.object_id) > 0 ? 1 : 0 }
  return { opacity: state.opacity }
}
function traceProgress(objectId: string) {
  const action = sceneActions.value.find(item => item.target_id === objectId && item.action_type === 'trace')
  return action ? eased(actionProgress(action), action.easing || 'linear') : 1
}
function traceStyle(objectId: string) {
  return { strokeDasharray: 100, strokeDashoffset: 100 * (1 - traceProgress(objectId)) }
}
function isPulsing(objectId: string) {
  return sceneActions.value.some(action => (
    action.target_id === objectId && action.action_type === 'pulse'
    && actionProgress(action) > 0 && actionProgress(action) < 1
  ))
}
function legacyPosition(objectId: string) {
  const object = legacyObjects.value.find(item => item.object_id === objectId)
  return object ? { x: object.x * 7.2 + 40, y: object.y * 2.2 + 30 } : { x: 0, y: 0 }
}

function prefersReducedMotion() {
  return typeof window !== 'undefined'
    && typeof window.matchMedia === 'function'
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches
}
function pause() {
  playing.value = false
  if (animationFrame) cancelAnimationFrame(animationFrame)
  animationFrame = 0
}
function syncCheckpoint() {
  let index = 0
  checkpoints.value.forEach((checkpoint, checkpointIndex) => {
    if (checkpoint.at_ms <= elapsedMs.value) index = checkpointIndex
  })
  currentIndex.value = index
}
function tick(timestamp: number) {
  if (!playing.value) return
  const duration = Number(props.scene?.duration_ms || checkpoints.value.at(-1)?.at_ms || 0)
  elapsedMs.value = Math.min(duration, playStartedMs + (timestamp - playStartedAt))
  syncCheckpoint()
  if (elapsedMs.value >= duration) {
    currentIndex.value = Math.max(0, checkpoints.value.length - 1)
    pause()
    return
  }
  animationFrame = requestAnimationFrame(tick)
}
function play() {
  if (!valid.value || playing.value) return
  const duration = Number(props.scene?.duration_ms || checkpoints.value.at(-1)?.at_ms || 0)
  if (elapsedMs.value >= duration || currentIndex.value >= checkpoints.value.length - 1) {
    currentIndex.value = 0
    elapsedMs.value = checkpoints.value[0]?.at_ms || 0
  }
  if (prefersReducedMotion()) {
    currentIndex.value = checkpoints.value.length - 1
    elapsedMs.value = checkpoints.value.at(-1)?.at_ms || duration
    return
  }
  playing.value = true
  playStartedMs = elapsedMs.value
  playStartedAt = performance.now()
  animationFrame = requestAnimationFrame(tick)
}
function previous() {
  pause()
  currentIndex.value = Math.max(0, currentIndex.value - 1)
  elapsedMs.value = checkpoints.value[currentIndex.value]?.at_ms || 0
}
function next() {
  pause()
  currentIndex.value = Math.min(checkpoints.value.length - 1, currentIndex.value + 1)
  elapsedMs.value = checkpoints.value[currentIndex.value]?.at_ms || 0
}
function replay() {
  pause()
  currentIndex.value = 0
  elapsedMs.value = checkpoints.value[0]?.at_ms || 0
  play()
}

onUnmounted(pause)
</script>

<style scoped>
.scene-player{display:grid;gap:10px}.scene-canvas{width:100%;height:auto;min-height:190px;border:1px solid #e3e7ef;border-radius:10px;background:#fbfcff}.scene-canvas-v2{min-height:250px;background:linear-gradient(180deg,#fbfcff 0%,#f7f9fc 100%)}.scene-canvas-v2 marker path{fill:#344054}.scene-primitive{transition:opacity .18s linear}.scene-primitive.kind-path{pointer-events:none}.scene-primitive.focused{filter:drop-shadow(0 4px 10px rgba(79,70,229,.28))}.scene-text{font-size:15px;font-weight:700}.scene-label{fill:#475467;font-size:13px;font-weight:700}.scene-purpose{display:grid;gap:2px;padding:8px 10px;border-left:3px solid #6366f1;color:#46536a;background:#f7f7ff;font-size:13px;line-height:1.45}.scene-purpose strong{color:#3730a3;font-size:13px}.scene-connections line{stroke:#9ca3d9;stroke-width:2.5;stroke-linecap:round}.legacy-scene-object{opacity:.12;transition:opacity .32s ease,filter .32s ease}.legacy-scene-object.visible{opacity:1}.legacy-scene-object.focused{filter:drop-shadow(0 4px 8px rgba(79,70,229,.25))}.legacy-scene-object rect{fill:#fff;stroke:#bfc5ec;stroke-width:1.5}.legacy-scene-object.focused rect{fill:#eef2ff;stroke:#6366f1;stroke-width:2}.legacy-scene-object foreignObject div{height:100%;display:flex;align-items:center;justify-content:center;overflow:hidden;color:#27324a;font-size:13px;line-height:1.35;text-align:center}.scene-progress{display:flex;align-items:center;justify-content:space-between;gap:16px;color:#46536a;font-size:14px}.scene-progress small{color:#7c8799;font-size:13px;font-variant-numeric:tabular-nums}.scene-controls{display:flex;align-items:center;gap:6px;flex-wrap:wrap}.scene-controls button{min-height:32px;display:inline-flex;align-items:center;gap:5px;padding:0 9px;border:1px solid #d5dbea;border-radius:7px;color:#4f5e75;background:#fff;font:inherit;font-size:13px;font-weight:700;cursor:pointer}.scene-controls button:hover:not(:disabled){border-color:#a9a9ea;color:#3730a3;background:#f7f7ff}.scene-controls button.primary{border-color:#514bdc;color:#fff;background:#514bdc}.scene-controls button:focus-visible{outline:2px solid #5b57e8;outline-offset:2px}.scene-controls button:disabled{opacity:.4;cursor:not-allowed}.scene-unavailable{margin:0;padding:14px;border:1px dashed #e1b567;border-radius:8px;color:#8a5218;background:#fffaf0;font-size:14px}@media(prefers-reduced-motion:reduce){.legacy-scene-object,.scene-primitive{transition:none}}
</style>
