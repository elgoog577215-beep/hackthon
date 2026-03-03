/**
 * 虚拟滚动组合式函数
 * 
 * 用于优化长列表渲染性能，只渲染可视区域内的元素
 */

import { ref, computed, onMounted, onUnmounted, watch, type Ref } from 'vue'

interface VirtualScrollOptions {
  itemHeight: number
  buffer?: number
  items: Ref<any[]>
}

export function useVirtualScroll(options: VirtualScrollOptions) {
  const { itemHeight, buffer = 5, items } = options

  const containerRef = ref<HTMLElement | null>(null)
  const scrollTop = ref(0)
  const containerHeight = ref(0)

  const visibleRange = computed(() => {
    const start = Math.max(0, Math.floor(scrollTop.value / itemHeight) - buffer)
    const visibleCount = Math.ceil(containerHeight.value / itemHeight) + buffer * 2
    const end = Math.min(items.value.length, start + visibleCount)
    
    return { start, end }
  })

  const visibleItems = computed(() => {
    const { start, end } = visibleRange.value
    return items.value.slice(start, end).map((item, index) => ({
      ...item,
      _index: start + index
    }))
  })

  const totalHeight = computed(() => items.value.length * itemHeight)

  const offsetY = computed(() => visibleRange.value.start * itemHeight)

  const handleScroll = (e: Event) => {
    const target = e.target as HTMLElement
    scrollTop.value = target.scrollTop
  }

  const updateContainerHeight = () => {
    if (containerRef.value) {
      containerHeight.value = containerRef.value.clientHeight
    }
  }

  let resizeObserver: ResizeObserver | null = null

  onMounted(() => {
    if (containerRef.value) {
      containerHeight.value = containerRef.value.clientHeight
      containerRef.value.addEventListener('scroll', handleScroll)
      
      resizeObserver = new ResizeObserver(() => {
        updateContainerHeight()
      })
      resizeObserver.observe(containerRef.value)
    }
  })

  onUnmounted(() => {
    if (containerRef.value) {
      containerRef.value.removeEventListener('scroll', handleScroll)
    }
    if (resizeObserver) {
      resizeObserver.disconnect()
    }
  })

  const scrollToIndex = (index: number) => {
    if (containerRef.value) {
      containerRef.value.scrollTop = index * itemHeight
    }
  }

  return {
    containerRef,
    visibleItems,
    totalHeight,
    offsetY,
    visibleRange,
    scrollToIndex
  }
}

export function useLazyLoad<T>(
  fetchFn: (page: number, pageSize: number) => Promise<{ items: T[]; total: number }>,
  options: {
    pageSize?: number
    immediate?: boolean
  } = {}
) {
  const { pageSize = 20, immediate = true } = options

  const items = ref<T[]>([]) as Ref<T[]>
  const loading = ref(false)
  const error = ref<Error | null>(null)
  const page = ref(1)
  const total = ref(0)
  const hasMore = computed(() => items.value.length < total.value)

  const loadMore = async () => {
    if (loading.value || !hasMore.value) return

    loading.value = true
    error.value = null

    try {
      const result = await fetchFn(page.value, pageSize)
      items.value.push(...result.items)
      total.value = result.total
      page.value++
    } catch (e) {
      error.value = e as Error
    } finally {
      loading.value = false
    }
  }

  const refresh = async () => {
    items.value = []
    page.value = 1
    total.value = 0
    await loadMore()
  }

  const handleIntersection = (entries: IntersectionObserverEntry[]) => {
    if (entries[0].isIntersecting && hasMore.value && !loading.value) {
      loadMore()
    }
  }

  const sentinelRef = ref<HTMLElement | null>(null)
  let intersectionObserver: IntersectionObserver | null = null

  onMounted(() => {
    if (immediate) {
      loadMore()
    }

    if (sentinelRef.value) {
      intersectionObserver = new IntersectionObserver(handleIntersection, {
        rootMargin: '100px'
      })
      intersectionObserver.observe(sentinelRef.value)
    }
  })

  onUnmounted(() => {
    if (intersectionObserver) {
      intersectionObserver.disconnect()
    }
  })

  return {
    items,
    loading,
    error,
    hasMore,
    loadMore,
    refresh,
    sentinelRef
  }
}
