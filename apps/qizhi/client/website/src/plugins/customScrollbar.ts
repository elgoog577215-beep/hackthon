import type { Router } from 'vue-router'

import '../assets/custom-scrollbar.css'

const SKIP_ANCESTOR =
  '[data-cscroll-skip], .md-editor, .md-editor-menu, .md-editor-dropdown, .cscroll-track, .cscroll-thumb'

const MIN_THUMB = 36
/** 相对标准滑块长度再缩短一点（仅影响视觉长度，位置仍按标准比例映射） */
const THUMB_LENGTH_SCALE = 0.72
const TRACK_INSET = 8

interface ScrollbarState {
  el: HTMLElement
  outer: HTMLElement
  track: HTMLDivElement
  thumb: HTMLDivElement
  ro: ResizeObserver
  onScroll: () => void
  hideTimer: number | null
}

const states = new WeakMap<HTMLElement, ScrollbarState>()
const enhancedEls = new Set<HTMLElement>()

function debounce(fn: () => void, ms: number) {
  let t: ReturnType<typeof setTimeout> | null = null
  return () => {
    if (t) clearTimeout(t)
    t = setTimeout(fn, ms)
  }
}

function getOuter(el: HTMLElement): HTMLElement | null {
  const parent = el.parentElement
  return parent?.classList.contains('cscroll-outer') ? parent : null
}

function wrapScrollHost(el: HTMLElement): HTMLElement {
  const existing = getOuter(el)
  if (existing) return existing

  const outer = document.createElement('div')
  outer.className = 'cscroll-outer'
  el.parentNode?.insertBefore(outer, el)
  outer.appendChild(el)
  return outer
}

function unwrapScrollHost(el: HTMLElement, outer: HTMLElement) {
  const parent = outer.parentNode
  if (!parent) return
  parent.insertBefore(el, outer)
  outer.remove()
}

function isScrollableTarget(el: HTMLElement): boolean {
  if (el.classList.contains('cscroll-outer')) return false
  if (el.closest(SKIP_ANCESTOR)) return false
  if (el.dataset.cscrollSkip !== undefined) return false
  const style = getComputedStyle(el)
  if (style.display === 'none' || style.visibility === 'hidden') return false
  const oy = style.overflowY
  return oy === 'auto' || oy === 'scroll' || oy === 'overlay'
}

function getScrollMetrics(el: HTMLElement) {
  const trackHeight = Math.max(0, el.clientHeight - TRACK_INSET * 2)
  const scrollHeight = el.scrollHeight
  const clientHeight = el.clientHeight
  const maxScroll = Math.max(0, scrollHeight - clientHeight)
  const visibleRatio = scrollHeight > 0 ? clientHeight / scrollHeight : 1
  const standardThumb = trackHeight * visibleRatio
  let thumbHeight = Math.max(MIN_THUMB, standardThumb * THUMB_LENGTH_SCALE)
  thumbHeight = Math.min(trackHeight, thumbHeight)
  const travel = Math.max(0, trackHeight - thumbHeight)
  const thumbTop = maxScroll > 0 ? (el.scrollTop / maxScroll) * travel : 0
  return { trackHeight, thumbHeight, thumbTop, maxScroll, travel, needsBar: maxScroll > 1 }
}

function updateThumb(state: ScrollbarState) {
  const { el, track, thumb } = state
  const { thumbHeight, thumbTop, needsBar } = getScrollMetrics(el)
  if (!needsBar) {
    track.style.display = 'none'
    return
  }
  track.style.display = 'block'
  thumb.style.height = `${thumbHeight}px`
  thumb.style.transform = ''
  thumb.style.top = `${thumbTop}px`
}

function bindThumbDrag(state: ScrollbarState) {
  const { el, outer, thumb } = state
  let dragging = false
  let startY = 0
  let startScroll = 0

  const onPointerMove = (e: PointerEvent) => {
    if (!dragging) return
    const { travel, maxScroll } = getScrollMetrics(el)
    if (travel <= 0 || maxScroll <= 0) return
    const deltaY = e.clientY - startY
    el.scrollTop = startScroll + (deltaY / travel) * maxScroll
    updateThumb(state)
  }

  const endDrag = (e: PointerEvent) => {
    if (!dragging) return
    dragging = false
    outer.classList.remove('is-dragging')
    document.removeEventListener('pointermove', onPointerMove)
    document.removeEventListener('pointerup', endDrag)
    document.removeEventListener('pointercancel', endDrag)
    try {
      thumb.releasePointerCapture(e.pointerId)
    } catch {
      /* ignore */
    }
  }

  thumb.addEventListener('pointerdown', (e: PointerEvent) => {
    if (e.button !== 0) return
    dragging = true
    outer.classList.add('is-dragging')
    startY = e.clientY
    startScroll = el.scrollTop
    thumb.setPointerCapture(e.pointerId)
    document.addEventListener('pointermove', onPointerMove)
    document.addEventListener('pointerup', endDrag)
    document.addEventListener('pointercancel', endDrag)
    e.preventDefault()
  })
}

function attachScrollbar(el: HTMLElement) {
  if (states.has(el)) return
  if (!isScrollableTarget(el)) return

  const outer = wrapScrollHost(el)
  el.classList.add('cscroll-native')

  const track = document.createElement('div')
  track.className = 'cscroll-track'
  track.setAttribute('aria-hidden', 'true')

  const thumb = document.createElement('div')
  thumb.className = 'cscroll-thumb'
  track.appendChild(thumb)
  outer.appendChild(track)

  const state: ScrollbarState = {
    el,
    outer,
    track,
    thumb,
    ro: new ResizeObserver(() => updateThumb(state)),
    onScroll: () => {
      updateThumb(state)
      outer.classList.add('is-scrolling')
      if (state.hideTimer) window.clearTimeout(state.hideTimer)
      state.hideTimer = window.setTimeout(() => {
        outer.classList.remove('is-scrolling')
        state.hideTimer = null
      }, 900)
    },
    hideTimer: null,
  }
  states.set(el, state)
  enhancedEls.add(el)

  el.addEventListener('scroll', state.onScroll, { passive: true })
  state.ro.observe(el)
  state.ro.observe(outer)

  bindThumbDrag(state)
  updateThumb(state)
}

function detachScrollbar(el: HTMLElement) {
  const state = states.get(el)
  if (!state) return
  state.ro.disconnect()
  el.removeEventListener('scroll', state.onScroll)
  if (state.hideTimer) window.clearTimeout(state.hideTimer)
  state.track.remove()
  el.classList.remove('cscroll-native')
  state.outer.classList.remove('is-scrolling', 'is-dragging')
  unwrapScrollHost(el, state.outer)
  states.delete(el)
  enhancedEls.delete(el)
}

function collectScrollables(root: ParentNode): HTMLElement[] {
  const result: HTMLElement[] = []
  root.querySelectorAll<HTMLElement>('*').forEach((node) => {
    if (isScrollableTarget(node)) result.push(node)
  })
  return result
}

function scanScrollables() {
  const app = document.getElementById('app')
  if (!app) return

  const targets = new Set<HTMLElement>()
  collectScrollables(app).forEach((el) => targets.add(el))

  targets.forEach((el) => {
    if (!states.has(el)) attachScrollbar(el)
    else updateThumb(states.get(el)!)
  })

  enhancedEls.forEach((el) => {
    if (!document.contains(el)) {
      detachScrollbar(el)
      return
    }
    const oy = getComputedStyle(el).overflowY
    if (!['auto', 'scroll', 'overlay'].includes(oy)) {
      detachScrollbar(el)
    }
  })
}

export function installCustomScrollbar(router: Router) {
  const scheduleScan = debounce(() => {
    requestAnimationFrame(scanScrollables)
  }, 120)

  router.isReady().then(() => scheduleScan())
  router.afterEach(() => scheduleScan())

  const app = document.getElementById('app')
  if (app) {
    const mo = new MutationObserver(() => scheduleScan())
    mo.observe(app, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['class', 'style'],
    })
  }

  window.addEventListener('resize', scheduleScan, { passive: true })
}
