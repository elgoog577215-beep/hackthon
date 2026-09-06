<template>
  <Teleport to="body">
    <div class="morphing-dialog" :class="{ 'is-preparing': preparing, 'is-closing': closing }">
      <div ref="backdropRef" class="morphing-dialog__backdrop" @click="handleBackdrop"></div>
      <section
        ref="panelRef"
        class="morphing-dialog__panel"
        :data-size="size"
        role="dialog"
        aria-modal="true"
        :aria-label="ariaLabel"
        tabindex="-1"
        @keydown="handlePanelKeydown"
      >
        <div ref="surfaceRef" class="morphing-dialog__surface">
          <slot />
        </div>
      </section>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref } from 'vue'

type OriginRect = {
  top: number
  left: number
  width: number
  height: number
}

const props = withDefaults(defineProps<{
  ariaLabel: string
  originRect?: OriginRect | null
  size?: 'medium' | 'large' | 'canvas'
  closeOnBackdrop?: boolean
}>(), {
  originRect: null,
  size: 'large',
  closeOnBackdrop: true,
})

const emit = defineEmits<{ (event: 'close'): void }>()
const panelRef = ref<HTMLElement | null>(null)
const surfaceRef = ref<HTMLElement | null>(null)
const backdropRef = ref<HTMLElement | null>(null)
const preparing = ref(true)
const closing = ref(false)
let previousBodyOverflow = ''
let previousActiveElement: HTMLElement | null = null

const focusableSelector = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

function prefersReducedMotion() {
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
}

function validOrigin(target: DOMRect) {
  const origin = props.originRect
  if (!origin || origin.width <= 0 || origin.height <= 0 || target.width <= 0 || target.height <= 0) return null
  return origin
}

function sourceTransform(origin: OriginRect, target: DOMRect) {
  const scaleX = Math.max(0.04, Math.min(1.4, origin.width / target.width))
  const scaleY = Math.max(0.04, Math.min(1.4, origin.height / target.height))
  return `translate3d(${origin.left - target.left}px, ${origin.top - target.top}px, 0) scale(${scaleX}, ${scaleY})`
}

async function finishAnimations(animations: Animation[]) {
  await Promise.allSettled(animations.map(animation => animation.finished))
  animations.forEach(animation => animation.cancel())
}

async function playEnter() {
  await nextTick()
  const panel = panelRef.value
  const surface = surfaceRef.value
  const backdrop = backdropRef.value
  if (!panel || !surface || !backdrop || prefersReducedMotion() || typeof panel.animate !== 'function') {
    preparing.value = false
    panel?.focus({ preventScroll: true })
    return
  }

  panel.focus({ preventScroll: true })
  const target = panel.getBoundingClientRect()
  const origin = validOrigin(target)
  const startTransform = origin
    ? sourceTransform(origin, target)
    : 'translate3d(0, 14px, 0) scale(.965)'
  const animations = [
    backdrop.animate(
      [{ opacity: 0 }, { opacity: 1 }],
      { duration: 220, easing: 'ease-out', fill: 'both' },
    ),
    panel.animate(
      [
        { transform: startTransform, opacity: origin ? 0.92 : 0 },
        { transform: 'translate3d(0, 0, 0) scale(1)', opacity: 1 },
      ],
      { duration: 340, easing: 'cubic-bezier(.2,.82,.2,1)', fill: 'both' },
    ),
    surface.animate(
      [{ opacity: 0 }, { opacity: 0 }, { opacity: 1 }],
      { duration: 300, easing: 'ease-out', fill: 'both', delay: origin ? 45 : 0 },
    ),
  ]
  await finishAnimations(animations)
  preparing.value = false
  panel.focus({ preventScroll: true })
}

async function requestClose() {
  if (closing.value) return
  closing.value = true
  const panel = panelRef.value
  const surface = surfaceRef.value
  const backdrop = backdropRef.value
  if (!panel || !surface || !backdrop || prefersReducedMotion() || typeof panel.animate !== 'function') {
    emit('close')
    return
  }

  const target = panel.getBoundingClientRect()
  const origin = validOrigin(target)
  const endTransform = origin
    ? sourceTransform(origin, target)
    : 'translate3d(0, 10px, 0) scale(.975)'
  await finishAnimations([
    surface.animate(
      [{ opacity: 1 }, { opacity: 0 }],
      { duration: 110, easing: 'ease-in', fill: 'both' },
    ),
    panel.animate(
      [
        { transform: 'translate3d(0, 0, 0) scale(1)', opacity: 1 },
        { transform: endTransform, opacity: origin ? 0.88 : 0 },
      ],
      { duration: origin ? 280 : 180, easing: 'cubic-bezier(.4,0,.7,.2)', fill: 'both' },
    ),
    backdrop.animate(
      [{ opacity: 1 }, { opacity: 0 }],
      { duration: 180, easing: 'ease-in', fill: 'both' },
    ),
  ])
  emit('close')
}

function handleBackdrop() {
  if (props.closeOnBackdrop) void requestClose()
}

function handlePanelKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    event.preventDefault()
    void requestClose()
    return
  }
  if (event.key !== 'Tab' || !panelRef.value) return
  const focusable = Array.from(panelRef.value.querySelectorAll<HTMLElement>(focusableSelector))
    .filter(element => !element.hidden && element.getAttribute('aria-hidden') !== 'true')
  if (!focusable.length) {
    event.preventDefault()
    panelRef.value.focus({ preventScroll: true })
    return
  }
  const first = focusable[0]!
  const last = focusable[focusable.length - 1]!
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

onMounted(() => {
  previousActiveElement = document.activeElement instanceof HTMLElement ? document.activeElement : null
  previousBodyOverflow = document.body.style.overflow
  document.body.style.overflow = 'hidden'
  void playEnter()
})

onUnmounted(() => {
  document.body.style.overflow = previousBodyOverflow
  if (previousActiveElement?.isConnected) previousActiveElement.focus({ preventScroll: true })
})

defineExpose({ close: requestClose })
</script>

<style scoped>
.morphing-dialog {
  position: fixed;
  inset: 0;
  z-index: 220;
  display: grid;
  place-items: center;
  padding: 32px;
  isolation: isolate;
}
.morphing-dialog__backdrop {
  position: absolute;
  inset: 0;
  z-index: -1;
  background: rgba(15, 23, 42, .48);
  backdrop-filter: blur(5px);
}
.morphing-dialog__panel {
  width: min(1040px, calc(100vw - 64px));
  height: min(82vh, 780px);
  min-height: min(560px, calc(100vh - 64px));
  overflow: hidden;
  border: 1px solid rgba(226, 232, 240, .92);
  border-radius: 22px;
  outline: none;
  background: #fff;
  box-shadow: 0 28px 80px rgba(15, 23, 42, .3), 0 3px 12px rgba(15, 23, 42, .12);
  transform-origin: 0 0;
}
.morphing-dialog__panel[data-size="medium"] { width: min(760px, calc(100vw - 64px)); }
.morphing-dialog__panel[data-size="canvas"] { width: min(1240px, calc(100vw - 64px)); height: min(90vh, 920px); }
.morphing-dialog__surface { width: 100%; height: 100%; min-width: 0; min-height: 0; }
.morphing-dialog.is-preparing .morphing-dialog__panel,
.morphing-dialog.is-preparing .morphing-dialog__backdrop,
.morphing-dialog.is-preparing .morphing-dialog__surface { opacity: 0; }
@media (max-width: 767px) {
  .morphing-dialog { padding: 0; place-items: stretch; }
  .morphing-dialog__backdrop { backdrop-filter: none; }
  .morphing-dialog__panel,
  .morphing-dialog__panel[data-size="medium"],
  .morphing-dialog__panel[data-size="canvas"] {
    width: 100vw;
    height: 100dvh;
    min-height: 0;
    border: 0;
    border-radius: 0;
  }
}
@media (prefers-reduced-motion: reduce) {
  .morphing-dialog__panel,
  .morphing-dialog__surface,
  .morphing-dialog__backdrop { animation: none !important; }
}
</style>
