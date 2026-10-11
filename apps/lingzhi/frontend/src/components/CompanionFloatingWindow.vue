<template>
  <Teleport to="body">
    <div v-show="visible" class="companion-modal-layer">
      <section ref="windowRef" class="companion-modal-window" :class="{ 'with-detail': detail, 'is-stacked': detail && rect.width < 700 }" :style="windowStyle" role="dialog" aria-modal="false" :aria-label="t('companionWorkspace.title')" tabindex="-1" @keydown.esc.stop.prevent="emit('close')">
        <header class="window-titlebar">
          <button type="button" class="window-move" :aria-label="t('companionWindow.move')" @pointerdown="startGesture($event, 'move')" @pointermove="moveGesture" @pointerup="endGesture" @pointercancel="endGesture" @lostpointercapture="endGesture" @keydown="keyboard($event, 'move')">⠿ {{ t('companionWorkspace.title') }}</button>
          <button type="button" @click="reset">{{ t('companionWindow.reset') }}</button>
          <button type="button" :aria-label="t('companionWorkspace.close')" @click="emit('close')">×</button>
        </header>
        <div v-show="detail" :id="`${windowId}-detail`" class="companion-modal-detail" />
        <div :id="`${windowId}-chat`" class="companion-modal-chat" />
        <button type="button" class="window-resize" :aria-label="t('companionWindow.resize')" @pointerdown="startGesture($event, 'resize')" @pointermove="moveGesture" @pointerup="endGesture" @pointercancel="endGesture" @lostpointercapture="endGesture" @keydown="keyboard($event, 'resize')">◢</button>
      </section>
    </div>
  </Teleport>
</template>
<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { t } from '../shared/i18n'
const props = defineProps<{ visible:boolean; detail:boolean; windowId:string }>()
const emit = defineEmits<{ (event:'close'):void }>()
const windowRef = ref<HTMLElement|null>(null)
let previousFocus:HTMLElement|null = null
const rect = reactive({ x: 0, y: 0, width: 480, height: 680 })
const windowStyle = computed(() => ({ left: `${rect.x}px`, top: `${rect.y}px`, width: `${rect.width}px`, height: `${rect.height}px` }))
let gesture: { id:number; kind:'move'|'resize'; x:number; y:number; rect:typeof rect; target:HTMLElement } | null = null
function constrain() {
  rect.width = Math.max(Math.min(360, window.innerWidth - 16), Math.min(rect.width, window.innerWidth - 16))
  rect.height = Math.max(Math.min(520, window.innerHeight - 16), Math.min(rect.height, window.innerHeight - 16))
  rect.x = Math.max(8, Math.min(rect.x, window.innerWidth - rect.width - 8))
  rect.y = Math.max(8, Math.min(rect.y, window.innerHeight - rect.height - 8))
}
function reset() {
  rect.width = Math.min(props.detail ? 1120 : 480, window.innerWidth - 48)
  rect.height = Math.min(720, window.innerHeight - 80)
  rect.x = (window.innerWidth - rect.width) / 2
  rect.y = (window.innerHeight - rect.height) / 2
  constrain()
}
function startGesture(event:PointerEvent, kind:'move'|'resize') {
  if (event.button !== 0 || gesture) return
  const target = event.currentTarget as HTMLElement
  gesture = { id:event.pointerId, kind, x:event.clientX, y:event.clientY, rect:{ ...rect }, target }
  target.setPointerCapture?.(event.pointerId)
  event.preventDefault()
}
function moveGesture(event:PointerEvent) {
  if (!gesture || event.pointerId !== gesture.id) return
  const dx = event.clientX - gesture.x, dy = event.clientY - gesture.y
  if (gesture.kind === 'move') { rect.x = gesture.rect.x + dx; rect.y = gesture.rect.y + dy }
  else { rect.width = Math.min(gesture.rect.width + dx, window.innerWidth - rect.x - 8); rect.height = Math.min(gesture.rect.height + dy, window.innerHeight - rect.y - 8) }
  constrain()
}
function endGesture() {
  const previous = gesture
  gesture = null
  if (previous?.target.hasPointerCapture?.(previous.id)) previous.target.releasePointerCapture(previous.id)
}
function keyboard(event:KeyboardEvent, kind:'move'|'resize') {
  if (!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key)) return
  event.preventDefault()
  const dx = event.key === 'ArrowLeft' ? -20 : event.key === 'ArrowRight' ? 20 : 0
  const dy = event.key === 'ArrowUp' ? -20 : event.key === 'ArrowDown' ? 20 : 0
  if (kind === 'move') { rect.x += dx; rect.y += dy }
  else { rect.width += dx; rect.height += dy }
  constrain()
}
watch(() => props.detail, reset)
onMounted(() => { reset(); window.addEventListener('resize', constrain); window.addEventListener('blur', endGesture) })
onUnmounted(() => { endGesture(); window.removeEventListener('resize', constrain); window.removeEventListener('blur', endGesture) })
watch(() => props.visible, async visible => {
  endGesture()
  constrain()
  if (visible) previousFocus = document.activeElement as HTMLElement
  await nextTick()
  if (visible) windowRef.value?.focus({ preventScroll:true })
  else if (previousFocus?.isConnected) previousFocus.focus({ preventScroll:true })
})
</script>
<style scoped>
.companion-modal-layer { position:fixed; inset:0; z-index:1000; pointer-events:none; }
.companion-modal-window { position:absolute; pointer-events:auto; display:grid; grid-template-columns:minmax(0,1fr); grid-template-rows:40px minmax(0,1fr); min-height:0; background:#fff; border:1px solid #ded4ef; border-radius:18px; overflow:hidden; box-shadow:0 16px 56px #25143f30; outline:none; container-type:inline-size; }
.window-titlebar { grid-column:1/-1; display:flex; align-items:center; gap:8px; padding:0 10px; background:#f7f4fc; border-bottom:1px solid #e8e1f1; }
.window-titlebar button { border:0; background:transparent; color:#665185; padding:5px 8px; cursor:pointer; font-size:13px; }
.window-titlebar .window-move { flex:1; text-align:left; cursor:grab; touch-action:none; user-select:none; }
.window-titlebar .window-move:active { cursor:grabbing; }
.window-resize { position:absolute; bottom:0; right:0; width:24px; height:24px; border:0; border-radius:8px 0 0; background:#f3eefb; color:#7655b1; cursor:nwse-resize; touch-action:none; }
button:focus-visible { outline:2px solid #8561cc; outline-offset:-2px; }
.companion-modal-window.with-detail { width:min(1180px,calc(100vw - 64px)); grid-template-columns:minmax(0,1fr) minmax(350px,1.15fr); }
.companion-modal-detail { min-height:0; min-width:0; overflow:auto; border-right:1px solid #e8e1f1; background:#fdfcff; }
.companion-modal-chat { min-width:0; min-height:0; display:flex; flex-direction:column; overflow:hidden; }
.companion-modal-chat :deep(.ai-teacher-panel),.companion-modal-chat :deep(.demo-chat) { position:relative!important; inset:auto!important; transform:none!important; width:100%!important; height:100%!important; min-height:0!important; flex:1; border:0!important; border-radius:0!important; box-shadow:none!important; }
.companion-modal-detail :deep(.learning-overview) { height:auto; overflow:visible; padding:0; }
.companion-modal-detail :deep(.overview-demo-link) { display:none; }
.companion-modal-detail :deep(.profile-detail) { padding:8px 24px 24px; }
.companion-modal-detail :deep(.profile-detail h3) { font-size:25px; }
.companion-modal-detail :deep(.point-dialog-header) { padding:18px 24px 0; }
.companion-modal-detail :deep(.point-evaluation) { padding:14px; gap:16px; }
.companion-modal-detail :deep(.detail-orb) { width:76px!important; height:76px!important; }
.companion-modal-detail :deep(.detail-orb>span) { width:68px!important; height:68px!important; font-size:25px; }
.companion-modal-detail :deep(.point-evidence li) { padding:12px; }
.companion-modal-detail :deep(.point-next) { padding:14px; margin-top:18px; }
.companion-modal-detail :deep(.detail-actions) { margin-top:16px; }
.companion-modal-window.with-detail.is-stacked { grid-template-columns:minmax(0,1fr); grid-template-rows:40px minmax(100px,.7fr) minmax(160px,1fr); }
.is-stacked .companion-modal-detail { border-right:0; border-bottom:1px solid #e8e1f1; }
</style>
