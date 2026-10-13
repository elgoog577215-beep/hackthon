import { computed, onBeforeUnmount, onMounted, ref, toValue, watch, type MaybeRefOrGetter, type Ref } from 'vue'

type Side = 'left' | 'right'
interface ColumnOptions {
  storageKey: string
  left: number
  right: number
  leftMin?: number
  rightMin?: number
  centerMin?: number
  enabled?: MaybeRefOrGetter<boolean>
  leftVisible?: MaybeRefOrGetter<boolean>
  rightVisible?: MaybeRefOrGetter<boolean>
}

/** Keep preferred widths separate from the temporary fit used by a smaller window. */
export function useResizableColumns(root: Ref<HTMLElement | null>, options: ColumnOptions) {
  const preferred = ref({ left: options.left, right: options.right })
  const available = ref(window.innerWidth)
  const enabled = computed(() => options.enabled === undefined || toValue(options.enabled))
  const leftVisible = computed(() => options.leftVisible === undefined || toValue(options.leftVisible))
  const rightVisible = computed(() => options.rightVisible === undefined || toValue(options.rightVisible))
  const widths = computed(() => {
    const leftMin = leftVisible.value ? options.leftMin ?? 180 : 0
    const rightMin = rightVisible.value ? options.rightMin ?? 260 : 0
    const centerMin = options.centerMin ?? 400
    const total = Math.max(0, available.value - 10 * (Number(leftVisible.value) + Number(rightVisible.value)))
    const scale = Math.min(1, total / (leftMin + rightMin + centerMin))
    const minLeft = leftMin * scale, minRight = rightMin * scale, center = centerMin * scale
    let left = leftVisible.value ? Math.max(minLeft, preferred.value.left) : 0
    let right = rightVisible.value ? Math.max(minRight, preferred.value.right) : 0
    const excess = Math.max(0, left + right + center - total)
    const flexible = left - minLeft + right - minRight
    if (flexible > 0) {
      left -= excess * (left - minLeft) / flexible
      right -= excess * (right - minRight) / flexible
    }
    return { left, right, minLeft, minRight, total, center }
  })

  function persist() {
    try { localStorage.setItem(options.storageKey, JSON.stringify(preferred.value)) } catch { /* Layout still works without storage. */ }
  }
  function resize(side: Side, value: number) {
    if (!Number.isFinite(value) || !enabled.value) return
    const fit = widths.value
    const minimum = side === 'left' ? fit.minLeft : fit.minRight
    const maximum = fit.total - fit.center - fit[side === 'left' ? 'right' : 'left']
    // Start from the displayed fit so dragging one side keeps the other stationary.
    preferred.value = {
      left: leftVisible.value ? fit.left : preferred.value.left,
      right: rightVisible.value ? fit.right : preferred.value.right,
      [side]: Math.max(minimum, Math.min(maximum, value)),
    }
  }
  function reset(side: Side) {
    preferred.value = { ...preferred.value, [side]: options[side] }
    persist()
  }
  function handle(side: Side) {
    return computed(() => {
      const fit = widths.value
      return {
        side,
        width: Math.round(fit[side]),
        min: Math.round(side === 'left' ? fit.minLeft : fit.minRight),
        max: Math.round(fit.total - fit.center - fit[side === 'left' ? 'right' : 'left']),
        onResize: (value: number) => resize(side, value),
        onCommit: persist,
        onReset: () => reset(side),
      }
    })
  }
  const layoutStyle = computed(() => enabled.value ? {
    '--column-left-width': `${widths.value.left}px`,
    '--column-right-width': `${widths.value.right}px`,
  } : {})

  function measure() {
    if (!root.value) return
    const style = getComputedStyle(root.value)
    const width = root.value.clientWidth || root.value.getBoundingClientRect().width
    if (width > 0) available.value = Math.max(0, width - (parseFloat(style.paddingLeft) || 0) - (parseFloat(style.paddingRight) || 0))
  }
  let observer: ResizeObserver | undefined
  watch([root, enabled, leftVisible, rightVisible], () => {
    observer?.disconnect()
    if (root.value) observer?.observe(root.value)
    measure()
  }, { flush: 'post' })
  onMounted(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(options.storageKey) || 'null')
      if (saved && ['left', 'right'].every(side => typeof saved[side] === 'number' && Number.isFinite(saved[side]) && saved[side] > 0)) {
        preferred.value = { left: saved.left, right: saved.right }
      }
    } catch { /* Ignore invalid or unavailable layout storage. */ }
    if (typeof ResizeObserver !== 'undefined') {
      observer = new ResizeObserver(measure)
      if (root.value) observer.observe(root.value)
    }
    window.addEventListener('resize', measure)
    measure()
  })
  onBeforeUnmount(() => {
    observer?.disconnect()
    window.removeEventListener('resize', measure)
  })
  return { layoutStyle, leftHandle: handle('left'), rightHandle: handle('right') }
}
