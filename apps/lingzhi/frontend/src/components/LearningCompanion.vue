<template>
  <Teleport to="body">
  <div v-show="active" ref="surface" class="learning-companion" :class="{ 'is-dragging': dragging, 'is-resting': compact, 'is-perched': expanded, 'is-modal': modal }">
    <div v-show="available" class="companion-pet" :class="{ 'is-expanded': expanded, 'is-compact': compact }"
      :style="{ transform: `translate(${x}px, ${y}px)` }"
      :data-x="x" :data-y="y" :data-edge="dragging ? undefined : edge">
      <button v-if="compact" ref="restoreButton" type="button" class="companion-edge"
        :aria-controls="resting ? undefined : 'reading-assistant-panel'" :aria-expanded="resting ? undefined : expanded"
        data-testid="companion-restore" :aria-label="resting ? t('learningCompanion.restore', '唤回学习小助手') : expanded ? t('learningCompanion.close', '收起 AI 面板') : t('learningCompanion.open', '打开学习小助手')" aria-describedby="companion-drag-help"
        @pointerdown="startDrag" @pointermove="moveDrag" @pointerup="finishDrag" @pointercancel="cancelDrag" @lostpointercapture="cancelDrag" @keydown="moveWithKeyboard" @click="restore">
        <ChevronLeft :size="12" aria-hidden="true" />
        <img :src="avatarUrl" alt="" width="32" height="40" draggable="false" />
      </button>
      <template v-else>
        <button ref="openButton" type="button" class="companion-open" data-testid="companion-open"
          aria-controls="reading-assistant-panel" :aria-expanded="expanded"
          :aria-label="expanded ? t('learningCompanion.close', '收起 AI 面板') : t('learningCompanion.open', '打开学习小助手')"
          :title="t('learningCompanion.dragHint', '拖动调整位置 · 点击打开 AI')" aria-describedby="companion-drag-help"
          @pointerdown="startDrag" @pointermove="moveDrag" @pointerup="finishDrag" @pointercancel="cancelDrag" @lostpointercapture="cancelDrag" @keydown="moveWithKeyboard" @click="activate">
          <img :src="avatarUrl" alt="" width="112" height="124" draggable="false" />
        </button>
        <span class="companion-name" aria-hidden="true">{{ t('learningCompanion.shortName', '学伴') }}</span>
        <button type="button" class="companion-dock" data-testid="companion-dock"
          :aria-label="t('learningCompanion.dock', '收起到边缘')" :title="t('learningCompanion.dock', '收起到边缘')" @click="dock">
          <PanelRightClose :size="14" aria-hidden="true" />
        </button>
      </template>
      <button v-if="remindersEnabled !== undefined" type="button" class="companion-reminder-toggle" :aria-label="t(remindersEnabled ? 'companionReminder.pause' : 'companionReminder.resume')" :title="t(remindersEnabled ? 'companionReminder.pause' : 'companionReminder.resume')" :aria-pressed="remindersEnabled" @click="emit('toggle-reminders')"><Bell v-if="remindersEnabled" :size="16" /><BellOff v-else :size="16" /></button>
    </div>
    <aside key="companion-speech" v-show="(helpOpen || welcome) && !dragging" :class="{'companion-reminder companion-welcome':helpOpen||welcome,'is-help':helpOpen}" :style="reminderStyle" aria-live="polite" :aria-label="t('companionWorkspace.title')" @keydown.esc.stop.prevent="helpOpen ? emit('close-help') : dismissWelcome()">
      <div v-if="helpOpen || welcome" class="reminder-heading"><strong>{{ t('companionWorkspace.title') }}</strong><button type="button" :aria-label="t('common.close', '关闭')" @click="helpOpen ? emit('close-help') : dismissWelcome()">×</button></div>
      <div key="companion-help" v-show="helpOpen" ref="helpHost" data-companion-help-host></div>
      <template v-if="welcome && !helpOpen"><p>{{ t('companionWelcome.message') }}</p>
      <footer><button type="button" @click="dismissWelcome">{{ t('companionWelcome.dismiss') }}</button></footer></template>
    </aside>
    <aside v-if="!helpOpen && !welcome && reminder && available && !dragging" class="companion-reminder" :style="reminderStyle" aria-live="polite" :aria-label="t('companionReminder.label')">
      <div class="reminder-heading"><strong>{{ reminder.title }}</strong><button type="button" :aria-label="t('companionReminder.dismiss')" @click="emit('dismiss-reminder')">×</button></div>
      <button type="button" class="reminder-body" @click="emit('reminder', reminder)"><span v-if="reminder.quote" class="reminder-quote">“{{ reminder.quote }}”</span><span>{{ reminder.message }}</span><span class="reminder-link">{{ t('companionReminder.open') }} →</span></button>
      <details v-if="reminder.source"><summary>{{ t('companionReminder.source') }}</summary><p>{{ reminder.source }}</p></details>
      <footer><button type="button" @click="emit('dismiss-reminder','not_now')">{{ t('companionPolicy.later') }}</button><button type="button" @click="emit('dismiss-reminder','never')">{{ t('companionPolicy.never') }}</button><button type="button" @click="emit('toggle-reminders')">{{ t('companionReminder.pause') }}</button></footer>
    </aside>
    <span id="companion-drag-help" class="companion-sr-only">{{ t('learningCompanion.dragHelp', '自由拖动，松手后自动避开正文和操作。方向键调整位置，Home 和 End 移到顶部和底部，Enter 打开。') }}</span>
  </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { Bell, BellOff, ChevronLeft, PanelRightClose } from 'lucide-vue-next'
import type { CompanionReminder } from '../composables/useCompanionReminders'
import { t } from '../shared/i18n'
import { resolvePublicAssetUrl } from '../utils/publicAssetUrl'
import { placeCompanion, type CompanionPoint, type CompanionRect } from '../utils/companion-placement'

const props = withDefaults(defineProps<{ expanded?: boolean; active?: boolean; modal?: boolean; reminder?:CompanionReminder|null; remindersEnabled?:boolean; welcome?:boolean;helpOpen?:boolean;helpRange?:Range|null }>(), { expanded: false, active: true, remindersEnabled:undefined })
const emit = defineEmits<{ (event: 'open'): void; (event:'close-help'):void;(event:'reminder', reminder:CompanionReminder):void; (event:'dismiss-reminder',mode?:'not_now'|'never'):void; (event:'toggle-reminders'):void; (event:'dismiss-welcome'):void }>()
function dismissWelcome() { emit('dismiss-welcome'); void nextTick(focus) }
const avatarUrl = resolvePublicAssetUrl('images/learning-companion.png', import.meta.env.BASE_URL)
const fullSize = { width: 112, height: 144 }
const smallSize = { width: 48, height: 44 }
const surface = ref<HTMLElement | null>(null)
const helpHost=ref<HTMLElement|null>(null)
const openButton = ref<HTMLButtonElement | null>(null)
const restoreButton = ref<HTMLButtonElement | null>(null)
const resting = ref(false)
const compact = ref(false)
const available = ref(true)
const dragging = ref(false)
const edge = ref('right')
const x = ref(0)
const y = ref(0)
const selectionStyle = ref<Record<string,string> | null>(null)
const reminderStyle = computed(() => props.helpOpen && selectionStyle.value ? selectionStyle.value : ({ left:`${Math.max(8, Math.min(x.value - 304, window.innerWidth - 328))}px`, top:`${Math.max(8, Math.min(y.value - 230, window.innerHeight - 380))}px` }))
function placeSelectionHelp() {
  const range=props.helpRange
  if (!props.helpOpen || !range?.startContainer.isConnected) { selectionStyle.value=null;return }
  const rect=range.getBoundingClientRect()
  const viewport={width:window.innerWidth,height:window.innerHeight}
  const bubble=helpHost.value?.parentElement
  const width=Math.min(480,viewport.width-24), gap=12
  const height=Math.min(bubble?.offsetHeight || 300,370,viewport.height-24)
  let left=rect.right+gap, top=rect.top
  if(left+width>viewport.width-gap){
    if(rect.left-width-gap>=gap)left=rect.left-width-gap
    else {left=rect.left;top=rect.bottom+gap;if(top+height>viewport.height-gap)top=rect.top-height-gap}
  }
  const offscreen=rect.bottom<0 || rect.top>viewport.height || rect.right<0 || rect.left>viewport.width
  selectionStyle.value={left:`${Math.max(gap,Math.min(left,viewport.width-width-gap))}px`,top:`${Math.max(gap,Math.min(top,viewport.height-height-gap))}px`,width:`${width}px`,visibility:offscreen?'hidden':'visible'}
}
let preferred: CompanionPoint | null = null
let observer: ResizeObserver | undefined
let mutations: MutationObserver | undefined
let queued = false
let disposed = false
let suppressClick = false
let gesture: { id: number; startX: number; startY: number; originX: number; originY: number; target: HTMLElement } | null = null
const clamp = (value: number, maximum: number) => Math.max(0, Math.min(value, Math.max(0, maximum)))

function geometry() {
  const bounds = surface.value?.getBoundingClientRect()
  if (!bounds?.width || !bounds.height) return null
  const occupied: CompanionRect[] = []
  const major = Array.from(document.querySelectorAll<HTMLElement>('[data-companion-obstacle], [role="dialog"]')).filter(el => !el.classList.contains('learning-main'))
  const controls = Array.from(document.querySelectorAll<HTMLElement>('button, input, textarea, select, a, summary, [role="tab"], [contenteditable="true"]'))
  for (const element of [...major, ...controls.filter(el => !major.some(parent => parent.contains(el)))]) {
    if (surface.value?.contains(element)) continue
    const box = element.getBoundingClientRect()
    if (!box.width || !box.height || box.bottom <= bounds.top || box.top >= bounds.bottom || box.right <= bounds.left || box.left >= bounds.right) continue
    // Clip notes to their scroll viewport; off-screen notes are not obstacles.
    const scrollArea = element.closest('.reading-notes-viewport')?.getBoundingClientRect()
    const top = Math.max(box.top, bounds.top, scrollArea?.top ?? bounds.top)
    const bottom = Math.min(box.bottom, bounds.bottom, scrollArea?.bottom ?? bounds.bottom)
    if (bottom <= top) continue
    occupied.push({ x: box.left - bounds.left, y: top - bounds.top, width: box.width, height: bottom - top })
  }
  return { viewport: { width: bounds.width, height: bounds.height }, occupied }
}
function settle() {
  placeSelectionHelp()
  if (!props.active || dragging.value || disposed) return
  if (props.expanded) {
    const perch = Array.from(document.querySelectorAll<HTMLElement>('[data-companion-perch]')).find(el => el.getBoundingClientRect().width > 0)
    if (perch) {
      const box = perch.getBoundingClientRect()
      compact.value = false
      available.value = true
      x.value = box.left
      y.value = box.top
      return
    }
  }
  const layout = geometry()
  if (!layout) return
  preferred ??= { x: layout.viewport.width - fullSize.width - 8, y: layout.viewport.height * .74 }
  let point = resting.value ? null : placeCompanion(layout.viewport, fullSize, preferred, layout.occupied)
  compact.value = !point
  if (!point) point = placeCompanion(layout.viewport, smallSize, preferred, layout.occupied)
  available.value = Boolean(point)
  if (!point) return // A covering modal leaves the existing AI entry available after closing.
  x.value = point.x
  y.value = point.y
  edge.value = point.x < layout.viewport.width / 2 ? 'left' : 'right'
}
function scheduleSettle() {
  if (queued || disposed || dragging.value) return
  queued = true
  void nextTick(() => { queued = false; settle() })
}
function startDrag(event: PointerEvent) {
  if (event.button !== 0 || gesture || !props.active || props.expanded) return
  suppressClick = false
  const target = event.currentTarget as HTMLElement
  gesture = { id: event.pointerId, startX: event.clientX, startY: event.clientY, originX: x.value, originY: y.value, target }
  target.setPointerCapture?.(event.pointerId)
}
function moveDrag(event: PointerEvent) {
  if (!gesture || event.pointerId !== gesture.id) return
  const dx = event.clientX - gesture.startX
  const dy = event.clientY - gesture.startY
  if (!dragging.value && Math.hypot(dx, dy) < 5) return
  const bounds = surface.value?.getBoundingClientRect()
  if (!bounds) return
  dragging.value = true
  suppressClick = true
  const size = compact.value ? smallSize : fullSize
  // During dragging, follow the pointer across the whole viewport.
  x.value = clamp(gesture.originX + dx, bounds.width - size.width)
  y.value = clamp(gesture.originY + dy, bounds.height - size.height)
}
function endGesture(cancelled: boolean) {
  if (!gesture) return
  const previous = gesture
  gesture = null
  suppressClick = suppressClick || cancelled || dragging.value
  if (dragging.value && !cancelled) preferred = { x: x.value, y: y.value }
  dragging.value = false
  if (previous.target.hasPointerCapture?.(previous.id)) previous.target.releasePointerCapture(previous.id)
  settle()
}
function finishDrag(event: PointerEvent) { if (gesture?.id === event.pointerId) endGesture(false) }
function cancelDrag() { endGesture(true) }
function moveWithKeyboard(event: KeyboardEvent) {
  if (!['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
  event.preventDefault()
  event.stopPropagation()
  cancelDrag()
  const bounds = surface.value?.getBoundingClientRect()
  if (!bounds) return
  preferred = { x: x.value, y: y.value }
  if (event.key === 'Home') preferred.y = 0
  else if (event.key === 'End') preferred.y = bounds.height
  else if (event.key === 'ArrowLeft') preferred.x = 0
  else if (event.key === 'ArrowRight') preferred.x = bounds.width
  else preferred.y += event.key === 'ArrowUp' ? -24 : 24
  settle()
}
function activate(event: MouseEvent) {
  if (event.detail !== 0 && suppressClick) { suppressClick = false; return }
  emit('open')
}
function focus() { (compact.value ? restoreButton.value : openButton.value)?.focus({ preventScroll: true }) }
async function dock() {
  cancelDrag()
  resting.value = true
  compact.value = true
  settle()
  await nextTick()
  focus()
}
async function restore(event: MouseEvent) {
  if (event.detail !== 0 && suppressClick) { suppressClick = false; return }
  if (!resting.value) { emit('open'); return }
  resting.value = false
  compact.value = false
  settle()
  if (compact.value) emit('open')
  await nextTick()
  focus()
}
watch(() => [props.active, props.expanded, props.modal], () => { cancelDrag(); scheduleSettle() })
watch(() => [props.helpRange,props.helpOpen],scheduleSettle,{flush:'post'})
onMounted(() => {
  settle()
  if (typeof ResizeObserver !== 'undefined') {
    observer = new ResizeObserver(scheduleSettle)
    if (surface.value) observer.observe(surface.value)
    if (helpHost.value?.parentElement) observer.observe(helpHost.value.parentElement)
    document.querySelectorAll('[data-companion-obstacle]').forEach(el => observer?.observe(el))
  }
  mutations = new MutationObserver(records => {
    if (records.some(record => !surface.value?.contains(record.target))) scheduleSettle()
  })
  const app = document.body
  if (app) mutations.observe(app, { childList: true, characterData: true, subtree: true, attributes: true, attributeFilter: ['style', 'class', 'hidden'] })
  window.addEventListener('resize', scheduleSettle)
  document.addEventListener('scroll', scheduleSettle, true)
  window.addEventListener('blur', cancelDrag)
})
onUnmounted(() => {
  disposed = true
  cancelDrag()
  observer?.disconnect()
  mutations?.disconnect()
  window.removeEventListener('resize', scheduleSettle)
  document.removeEventListener('scroll', scheduleSettle, true)
  window.removeEventListener('blur', cancelDrag)
})
defineExpose({ focus,helpHost })
</script>

<style scoped>
.learning-companion { position:fixed; inset:0; pointer-events:none; z-index:90; }
.companion-pet { position:absolute; left:0; top:0; width:112px; height:144px; pointer-events:none; transition:none; }
.is-dragging .companion-pet { transition:none; }
.companion-open { width:112px; height:124px; display:grid; place-items:center; padding:0; border:0; border-radius:24px; background:transparent; cursor:grab; touch-action:none; user-select:none; pointer-events:auto; -webkit-user-select:none; }
.companion-open img { width:112px; height:124px; object-fit:contain; pointer-events:none; filter:drop-shadow(0 5px 5px rgba(99,82,170,.16)); transition:transform 160ms ease; }
.companion-open:hover img { transform:translateY(-2px) rotate(-3deg); }
.is-dragging .companion-open { cursor:grabbing; }
.is-dragging .companion-open img { transform:rotate(-7deg) scale(1.04); }
.companion-name { display:block; width:fit-content; max-width:80px; margin:0 auto; padding:2px 8px; border-radius:12px; color:#66539d; background:#f3effdcc; font-size:11px; line-height:16px; opacity:0; transition:opacity 140ms ease; }
.companion-pet:hover .companion-name,.companion-pet:focus-within .companion-name { opacity:1; }
.companion-dock { position:absolute; top:0; left:0; display:grid; place-items:center; width:26px; height:26px; padding:0; border:1px solid #ded8ef; border-radius:50%; color:#6755a7; background:#fff; cursor:pointer; pointer-events:auto; opacity:0; transition:opacity 140ms ease; }
.companion-pet:hover .companion-dock,.companion-pet:focus-within .companion-dock { opacity:1; }
.is-dragging .companion-dock,.is-dragging .companion-name { opacity:0; pointer-events:none; }
.is-expanded .companion-open { background:radial-gradient(ellipse at center, #e5dfff88, transparent 70%); }
.companion-pet.is-compact { width:48px; height:44px; }
.companion-edge { position:absolute; inset:0; width:48px; height:44px; display:flex; align-items:center; justify-content:center; padding:0; border:1px solid #dcd5f2; border-radius:16px; color:#6755a7; background:#f0ecfa; box-shadow:0 3px 10px #7360b514; cursor:grab; touch-action:none; user-select:none; pointer-events:auto; }
.companion-edge img { object-fit:contain; pointer-events:none; }
.is-dragging .companion-edge { cursor:grabbing; }
button:focus-visible { outline:2px solid var(--lz-brand, #7462df); outline-offset:2px; }
.companion-sr-only { position:absolute; width:1px; height:1px; overflow:hidden; clip-path:inset(50%); white-space:nowrap; }
.companion-reminder-toggle { position:absolute; right:0; bottom:0; pointer-events:auto; width:28px; height:28px; display:grid; place-items:center; border:1px solid #ded8ef; border-radius:50%; color:#6755a7; background:#fff; cursor:pointer; }
.companion-reminder { position:absolute; width:320px; max-width:calc(100vw - 16px); max-height:min(370px,calc(100dvh - 16px)); overflow:auto; pointer-events:auto; padding:14px; border:1px solid #d9ccef; border-radius:16px 16px 4px 16px; background:#fff; color:#453655; box-shadow:0 8px 30px #60417c24; font-size:14px; line-height:1.6; }
.reminder-heading { display:flex; align-items:center; justify-content:space-between; gap:8px; }
.reminder-heading strong { font-size:15px; color:#71529c; }
.companion-reminder button { border:0; background:transparent; color:inherit; cursor:pointer; }
.reminder-heading button { padding:0 6px; font-size:20px; }
.reminder-body { display:flex; flex-direction:column; gap:8px; width:100%; padding:10px 0; text-align:left; font:inherit; overflow-wrap:anywhere; }
.reminder-quote { color:#756782; padding-left:10px; border-left:2px solid #c5b1e5; }
.reminder-link { color:#71529c; font-weight:600; }
.companion-reminder summary { cursor:pointer; color:#71529c; }
.companion-reminder p { margin:8px 0; overflow-wrap:anywhere; }
.companion-reminder footer { display:flex; align-items:center; justify-content:space-between; gap:8px; padding-top:8px; border-top:1px solid #eee7f6; font-size:12px; color:#82728f; }
.companion-reminder footer button { color:#71529c; white-space:nowrap; }
.companion-welcome { font-size:15px; }
.companion-welcome footer { justify-content:flex-end; }
.companion-welcome footer button { min-height:32px; padding:6px 12px; border-radius:var(--lz-action-radius); background:var(--lz-action-bg); color:var(--lz-action-text); font-size:14px; border:1px solid var(--lz-action-border); box-shadow:var(--lz-action-shadow); }
@media (hover:none) { .companion-dock { opacity:1; } }
@media (prefers-reduced-motion:reduce) {
  .companion-pet,.companion-open img,.companion-dock,.companion-name { transition:none; }
  .companion-open:hover img,.is-dragging .companion-open img { transform:none; }
}
</style>

<style scoped>
.is-perched .companion-pet { transition:none; }.is-perched .companion-dock,.is-perched .companion-name { display:none; }.is-perched .companion-open { cursor:pointer; background:none; }
@media(prefers-reduced-motion:reduce) { .is-perched .companion-pet { transition:none; } }
</style>

<style scoped>
.learning-companion.is-modal { z-index:1010; }
.is-perched .companion-pet { width:76px; height:40px; }
.is-perched .companion-open,.is-perched .companion-open img { width:40px; height:40px; }
.is-perched .companion-reminder-toggle { top:6px; bottom:auto; }
</style>
