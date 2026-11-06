import { nextTick, onBeforeUnmount, ref, type Ref } from 'vue'

export type ReadingOwner = 'body' | 'reference' | 'explicit'
export const readingScrollKeys = new Set(['ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Home', 'End', ' '])

/** One authority for navigation; follower scroll events never claim ownership. */
export function useReadingNavigation(root: Ref<HTMLElement | null>, afterNavigate: () => void) {
  const owner = ref<ReadingOwner>('body')
  const referenceId = ref('')
  let sequence = 0, disposed = false
  function claim(source: ReadingOwner) {
    owner.value = source
    sequence++
    if (source !== 'reference') referenceId.value = ''
  }
  function interact(event: Event) {
    if (event instanceof KeyboardEvent && !readingScrollKeys.has(event.key)) return
    claim('body')
  }
  async function navigate(anchor: string, options: { source?: ReadingOwner; referenceId?: string; focus?: boolean; rect?: () => DOMRect | null } = {}) {
    const source = options.source || 'explicit'
    claim(source)
    referenceId.value = options.referenceId || ''
    const request = sequence, host = root.value
    await nextTick()
    if (disposed || request !== sequence || !host || host !== root.value) return false
    const target = Array.from(host.querySelectorAll<HTMLElement>('[id]')).find(n => n.id === anchor)
    if (!target) return false
    // Only an explicit action can reveal answers and take keyboard focus.
    if (source === 'explicit') {
      for (let node: HTMLElement | null = target; node && node !== host; node = node.parentElement) {
        if (node instanceof HTMLDetailsElement) node.open = true
      }
      if (target.matches('[data-block-id]')) target.querySelectorAll<HTMLDetailsElement>('details.handout-block--answer').forEach(n => { n.open = true })
    }
    const rect = options.rect?.() || target.getBoundingClientRect()
    host.scrollTo({ top: Math.max(0, host.scrollTop + rect.top - host.getBoundingClientRect().top - 24), behavior: 'instant' })
    if (options.focus ?? source === 'explicit') {
      target.tabIndex = -1
      target.focus({ preventScroll: true })
      target.classList.remove('study-jump-target')
      void target.offsetWidth
      target.classList.add('study-jump-target')
    }
    afterNavigate()
    return true
  }
  onBeforeUnmount(() => { disposed = true; sequence++ })
  return { owner, referenceId, claim, interact, navigate }
}
