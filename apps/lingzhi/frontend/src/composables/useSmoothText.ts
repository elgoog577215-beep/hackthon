import { onBeforeUnmount, ref, watch } from 'vue'

/** Do not briefly expose half a formula, inline code token, or diagram as prose. */
export function safeRevealEnd(text: string, end: number): number {
  const protectedTokens = /```(?:mermaid|diagram|teaching-diagram|lingzhi-diagram)[^\n]*\n[\s\S]*?```|```[^\n]*\n|\$\$[\s\S]*?\$\$|(?<![\\$])\$(?!\s)[^\n$]+?\$|`[^`\n]+`|\*\*[^*\n]+\*\*|\[[^\]\n]+\]\([^\n)]*\)/g
  for (const match of text.matchAll(protectedTokens)) {
    const start = match.index!, stop = start + match[0].length
    if (start >= end) break
    if (end > start && end < stop) end = stop
  }
  // Avoid splitting UTF-16 pairs, including emoji.
  if (end > 0 && /[\uD800-\uDBFF]/.test(text[end - 1] || '')) end++
  return Math.min(end, text.length)
}

/** Presentation only: persisted content and generation state remain authoritative. */
export function useSmoothText(source: () => string, enabled: () => boolean, animateInitial: () => boolean) {
  const reduced = typeof matchMedia === 'function' ? matchMedia('(prefers-reduced-motion: reduce)') : undefined
  const visible = ref(animateInitial() && enabled() && !reduced?.matches && !document.hidden ? '' : source())
  let target = source(), frame = 0, deadline = 0, lastTime = 0, paintedAt = 0
  function stop() { if (frame) cancelAnimationFrame(frame); frame = 0 }
  function finish() { stop(); visible.value = target }
  function tick(now: number) {
    frame = 0
    if (document.hidden || reduced?.matches || now >= deadline) { finish(); return }
    if (now - paintedAt >= 30) {
      const remaining = target.length - visible.value.length
      const elapsed = Math.max(16, now - lastTime)
      const amount = Math.max(1, Math.ceil(remaining * elapsed / Math.max(elapsed, deadline - lastTime)))
      visible.value = target.slice(0, safeRevealEnd(target, visible.value.length + amount))
      lastTime = now; paintedAt = now
    }
    if (visible.value.length < target.length) frame = requestAnimationFrame(tick)
  }
  function schedule() {
    if (!enabled() || reduced?.matches || document.hidden || typeof requestAnimationFrame !== 'function') { finish(); return }
    const now = performance.now()
    // Bound each received batch to <700ms, even if it contains a whole paragraph.
    deadline = now + Math.min(650, Math.max(100, (target.length - visible.value.length) * 12))
    if (!frame) { lastTime = now; paintedAt = now - 30; frame = requestAnimationFrame(tick) }
  }
  watch([source, enabled], ([next]) => {
    const append = next.startsWith(target)
    target = next
    if (!append || !next || !enabled()) { finish(); return }
    schedule()
  }, { flush: 'sync' })
  function onVisibility() { if (document.hidden) finish() }
  function onMotion() { if (reduced?.matches) finish() }
  watch(enabled, active => {
    document.removeEventListener('visibilitychange', onVisibility)
    reduced?.removeEventListener?.('change', onMotion)
    if (active) { document.addEventListener('visibilitychange', onVisibility); reduced?.addEventListener?.('change', onMotion) }
  }, { immediate: true })
  if (visible.value !== target) schedule()
  onBeforeUnmount(() => {
    stop(); document.removeEventListener('visibilitychange', onVisibility)
    reduced?.removeEventListener?.('change', onMotion)
  })
  return visible
}
