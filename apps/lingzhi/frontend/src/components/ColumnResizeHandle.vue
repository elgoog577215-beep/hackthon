<template>
  <div
    class="column-resize-handle"
    :class="{ 'is-resizing': dragging }"
    role="separator"
    tabindex="0"
    aria-orientation="vertical"
    :aria-label="t(`columnLayout.${side}`)"
    :aria-valuemin="min"
    :aria-valuemax="max"
    :aria-valuenow="width"
    :aria-valuetext="t('columnLayout.value').replace('{width}', String(width))"
    :title="t('columnLayout.hint')"
    @pointerdown="start"
    @keydown="keydown"
    @dblclick="emit('reset')"
  ><span aria-hidden="true" /></div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import { t } from '../shared/i18n'

const props = defineProps<{ side: 'left' | 'right'; width: number; min: number; max: number }>()
const emit = defineEmits<{ resize: [width: number]; commit: []; reset: [] }>()
const dragging = ref(false)
let pointerId: number | undefined, startX = 0, startWidth = 0
let previousCursor = '', previousUserSelect = ''
let target: HTMLElement | undefined

function move(event: PointerEvent) {
  if (event.pointerId !== pointerId) return
  emit('resize', startWidth + (event.clientX - startX) * (props.side === 'left' ? 1 : -1))
}
function finish(event?: PointerEvent) {
  if (!dragging.value || (event && event.pointerId !== pointerId)) return
  window.removeEventListener('pointermove', move)
  window.removeEventListener('pointerup', finish)
  window.removeEventListener('pointercancel', finish)
  window.removeEventListener('blur', blur)
  target?.removeEventListener('lostpointercapture', finish)
  if (pointerId !== undefined && target?.hasPointerCapture?.(pointerId)) target.releasePointerCapture(pointerId)
  document.documentElement.style.cursor = previousCursor
  document.documentElement.style.userSelect = previousUserSelect
  dragging.value = false
  pointerId = undefined
  target = undefined
  emit('commit')
}
function blur() { finish() }
function start(event: PointerEvent) {
  if (event.button !== 0 || dragging.value) return
  event.preventDefault()
  target = event.currentTarget as HTMLElement
  target.focus({ preventScroll: true })
  pointerId = event.pointerId
  startX = event.clientX
  startWidth = props.width
  previousCursor = document.documentElement.style.cursor
  previousUserSelect = document.documentElement.style.userSelect
  document.documentElement.style.cursor = 'col-resize'
  document.documentElement.style.userSelect = 'none'
  dragging.value = true
  target.addEventListener('lostpointercapture', finish)
  target.setPointerCapture?.(event.pointerId)
  window.addEventListener('pointermove', move)
  window.addEventListener('pointerup', finish)
  window.addEventListener('pointercancel', finish)
  window.addEventListener('blur', blur)
}
function keydown(event: KeyboardEvent) {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End', 'Enter'].includes(event.key)) return
  event.preventDefault()
  if (event.key === 'Enter') { emit('reset'); return }
  const step = event.shiftKey ? 40 : 12
  const direction = (event.key === 'ArrowRight' ? 1 : -1) * (props.side === 'left' ? 1 : -1)
  emit('resize', event.key === 'Home' ? props.min : event.key === 'End' ? props.max : props.width + direction * step)
  emit('commit')
}
onBeforeUnmount(() => finish())
</script>

<style scoped>
.column-resize-handle{position:relative;z-index:6;align-self:stretch;flex:0 0 10px;width:10px;min-height:32px;display:grid;place-items:center;cursor:col-resize;touch-action:none;user-select:none;outline:none;background:transparent}
.column-resize-handle::before{position:absolute;inset:0 3px;content:"";border-radius:4px;background:transparent;transition:background .15s}
.column-resize-handle>span{position:relative;width:2px;height:32px;border-radius:2px;background:#c8cede;pointer-events:none}
.column-resize-handle:hover::before,.column-resize-handle:focus-visible::before,.column-resize-handle.is-resizing::before{background:#e8e5fb}
.column-resize-handle:hover>span,.column-resize-handle:focus-visible>span,.column-resize-handle.is-resizing>span{background:#7561cb}
.column-resize-handle:focus-visible{box-shadow:inset 0 0 0 2px #9385ed;border-radius:4px}
@media(prefers-reduced-motion:reduce){.column-resize-handle::before{transition:none}}
</style>
