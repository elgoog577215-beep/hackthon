import { nextTick, onBeforeUnmount, ref, watch, type Ref } from 'vue'

/** Follow new chat content until the reader scrolls away from the latest reply. */
export function useFollowingScroll(
  element: Ref<HTMLElement | null>,
  content: () => unknown,
  enabled: () => boolean = () => true,
  resizedContent?: Ref<HTMLElement | null>,
) {
  const followingLatest = ref(true)
  let disposed = false, lastScrollTop = 0
  let observer: ResizeObserver | undefined
  onBeforeUnmount(() => { disposed = true; observer?.disconnect() })
  const follow = () => {
    if (disposed || !enabled() || !followingLatest.value || !element.value) return
    element.value.scrollTop = element.value.scrollHeight
    lastScrollTop = element.value.scrollTop
  }
  watch(content, () => { if (enabled() && followingLatest.value) void nextTick(follow) }, { immediate: true })
  if (resizedContent && typeof ResizeObserver !== 'undefined') {
    observer = new ResizeObserver(() => { void nextTick(follow) })
    watch(resizedContent, target => { observer?.disconnect(); if (target) observer?.observe(target) }, { flush: 'post' })
  }
  function handleMessageScroll() {
    const target = element.value
    if (!target || !enabled() || target.clientHeight === 0) return
    if (target.scrollHeight - target.scrollTop - target.clientHeight < 64) followingLatest.value = true
    else if (target.scrollTop < lastScrollTop - 1) followingLatest.value = false
    lastScrollTop = target.scrollTop
  }
  function scrollToBottom() {
    followingLatest.value = true
    void nextTick(follow)
  }
  return { followingLatest, handleMessageScroll, scrollToBottom }
}
