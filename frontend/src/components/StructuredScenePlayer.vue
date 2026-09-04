<template>
  <section class="scene-player" :data-playing="playing ? 'true' : 'false'">
    <svg
      v-if="valid"
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
          :x1="position(edge.target_ids[0] || '').x"
          :y1="position(edge.target_ids[0] || '').y"
          :x2="position(edge.target_ids[1] || '').x"
          :y2="position(edge.target_ids[1] || '').y"
        />
      </g>
      <g
        v-for="object in objects"
        :key="object.object_id"
        class="scene-object"
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

interface SceneObject {
  object_id: string
  label: string
  kind: string
  x: number
  y: number
}

interface SceneAction {
  action_id: string
  action_type: 'reveal' | 'focus' | 'connect'
  target_ids: string[]
  start_ms: number
  duration_ms: number
}

interface SceneCheckpoint {
  checkpoint_id: string
  label: string
  at_ms: number
}

const props = defineProps<{ scene: Record<string, any> }>()
const currentIndex = ref(0)
const playing = ref(false)
let animationFrame = 0
let playStartedAt = 0
let playStartedMs = 0

function tr(key: string, zh: string, en: string) {
  return t(`courseWorkbench.scriptVisual.scene.${key}`, activeLocale.value === 'en' ? en : zh)
}

const objects = computed<SceneObject[]>(() => Array.isArray(props.scene?.objects)
  ? props.scene.objects.filter(item => (
      item && typeof item.object_id === 'string' && typeof item.label === 'string'
      && Number.isFinite(item.x) && Number.isFinite(item.y)
    ))
  : [])
const actions = computed<SceneAction[]>(() => Array.isArray(props.scene?.actions)
  ? props.scene.actions.filter(item => (
      item && typeof item.action_id === 'string' && Array.isArray(item.target_ids)
      && ['reveal', 'focus', 'connect'].includes(item.action_type)
      && Number.isFinite(item.start_ms)
    ))
  : [])
const checkpoints = computed<SceneCheckpoint[]>(() => Array.isArray(props.scene?.checkpoints)
  ? props.scene.checkpoints.filter(item => (
      item && typeof item.checkpoint_id === 'string' && typeof item.label === 'string'
      && Number.isFinite(item.at_ms)
    )).sort((left, right) => left.at_ms - right.at_ms)
  : [])
const objectIds = computed(() => new Set(objects.value.map(item => item.object_id)))
const valid = computed(() => (
  props.scene?.schema_version === 'scene_spec_v1'
  && objects.value.length >= 2
  && checkpoints.value.length >= 2
  && actions.value.every(action => action.target_ids.every(id => objectIds.value.has(id)))
))
const sceneTitle = computed(() => String(props.scene?.title || tr('title', '结构化动画', 'Structured animation')))
const currentCheckpoint = computed(() => checkpoints.value[currentIndex.value])
const currentMs = computed(() => currentCheckpoint.value?.at_ms ?? 0)
const visibleIds = computed(() => new Set(
  actions.value
    .filter(action => action.action_type === 'reveal' && action.start_ms <= currentMs.value)
    .flatMap(action => action.target_ids),
))
const focusedIds = computed(() => new Set(
  actions.value
    .filter(action => action.action_type === 'focus' && action.start_ms <= currentMs.value)
    .slice(-1)
    .flatMap(action => action.target_ids),
))
const visibleConnections = computed(() => actions.value.filter(action => (
  action.action_type === 'connect'
  && action.start_ms <= currentMs.value
  && action.target_ids.length === 2
)))
const fallbackUnit = computed(() => props.scene?.static_fallback?.unit || null)

function position(objectId: string) {
  const object = objects.value.find(item => item.object_id === objectId)
  return object
    ? { x: object.x * 7.2 + 40, y: object.y * 2.2 + 30 }
    : { x: 0, y: 0 }
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

function tick(timestamp: number) {
  if (!playing.value) return
  const elapsed = playStartedMs + (timestamp - playStartedAt)
  let index = currentIndex.value
  checkpoints.value.forEach((checkpoint, checkpointIndex) => {
    if (checkpoint.at_ms <= elapsed) index = checkpointIndex
  })
  currentIndex.value = index
  if (elapsed >= Number(props.scene?.duration_ms || checkpoints.value.at(-1)?.at_ms || 0)) {
    currentIndex.value = Math.max(0, checkpoints.value.length - 1)
    pause()
    return
  }
  animationFrame = requestAnimationFrame(tick)
}

function play() {
  if (!valid.value || playing.value) return
  if (currentIndex.value >= checkpoints.value.length - 1) currentIndex.value = 0
  if (prefersReducedMotion()) {
    currentIndex.value = checkpoints.value.length - 1
    return
  }
  playing.value = true
  playStartedMs = currentMs.value
  playStartedAt = performance.now()
  animationFrame = requestAnimationFrame(tick)
}

function previous() {
  pause()
  currentIndex.value = Math.max(0, currentIndex.value - 1)
}

function next() {
  pause()
  currentIndex.value = Math.min(checkpoints.value.length - 1, currentIndex.value + 1)
}

function replay() {
  pause()
  currentIndex.value = 0
  play()
}

onUnmounted(pause)
</script>

<style scoped>
.scene-player{display:grid;gap:10px}.scene-canvas{width:100%;height:auto;min-height:190px;border:1px solid #e3e7ef;border-radius:10px;background:#fbfcff}.scene-connections line{stroke:#9ca3d9;stroke-width:2.5;stroke-linecap:round}.scene-object{opacity:.12;transition:opacity .32s ease,filter .32s ease}.scene-object.visible{opacity:1}.scene-object.focused{filter:drop-shadow(0 4px 8px rgba(79,70,229,.25))}.scene-object rect{fill:#fff;stroke:#bfc5ec;stroke-width:1.5}.scene-object.focused rect{fill:#eef2ff;stroke:#6366f1;stroke-width:2}.scene-object foreignObject div{height:100%;display:flex;align-items:center;justify-content:center;overflow:hidden;color:#27324a;font-size:13px;line-height:1.35;text-align:center}.scene-progress{display:flex;align-items:center;justify-content:space-between;gap:16px;color:#46536a;font-size:14px}.scene-progress small{color:#7c8799;font-size:13px;font-variant-numeric:tabular-nums}.scene-controls{display:flex;align-items:center;gap:6px;flex-wrap:wrap}.scene-controls button{min-height:32px;display:inline-flex;align-items:center;gap:5px;padding:0 9px;border:1px solid #d5dbea;border-radius:7px;color:#4f5e75;background:#fff;font:inherit;font-size:13px;font-weight:700;cursor:pointer}.scene-controls button:hover:not(:disabled){border-color:#a9a9ea;color:#3730a3;background:#f7f7ff}.scene-controls button.primary{border-color:#514bdc;color:#fff;background:#514bdc}.scene-controls button:focus-visible{outline:2px solid #5b57e8;outline-offset:2px}.scene-controls button:disabled{opacity:.4;cursor:not-allowed}.scene-unavailable{margin:0;padding:14px;border:1px dashed #e1b567;border-radius:8px;color:#8a5218;background:#fffaf0;font-size:14px}@media(prefers-reduced-motion:reduce){.scene-object{transition:none}}
</style>
