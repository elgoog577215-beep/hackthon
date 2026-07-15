<template>
  <div
    class="not-prose markdown-document-editor"
  >
    <main ref="bodyRef" class="document-body prose prose-slate max-w-none">
      <MarkdownRenderer :content="sourceMarkdown" :search-words="searchWords" />
      <span v-if="isStreaming" class="inline-block w-0.5 h-5 bg-slate-800 animate-blink ml-0.5 align-text-bottom"></span>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import MarkdownRenderer from './MarkdownRenderer.vue'
import type { Node } from '@/stores/types'
import { applyContentBlockAnchors } from '@/utils/learning-position'

const props = defineProps<{
  node: Node
  content: string
  searchWords?: string[]
  isStreaming?: boolean
}>()

const bodyRef = ref<HTMLElement | null>(null)
const draftContent = ref(props.content || '')
const foldedHeadingKeys = ref<Set<string>>(new Set())
let headingObserver: MutationObserver | null = null
let enhanceTimer: number | null = null
let isEnhancingHeadings = false

watch(
  () => props.content,
  (value) => {
    draftContent.value = value || ''
  },
)

const sourceMarkdown = computed(() => draftContent.value || '')

const getMarkdownRenderer = () => bodyRef.value?.querySelector('.markdown-renderer') as HTMLElement | null

const cleanHeadingTitle = (heading: HTMLElement) => {
  const cloned = heading.cloneNode(true) as HTMLElement
  cloned.querySelectorAll('.inline-fold-toggle').forEach((button) => button.remove())
  return cloned.textContent?.trim().replace(/\s+/g, ' ') || '未命名标题'
}

const headingLevel = (element: Element) => {
  const match = element.tagName.match(/^H([1-6])$/)
  return match ? Number(match[1]) : 0
}

const ensureHeadingKeys = () => {
  const renderer = getMarkdownRenderer()
  if (!renderer) return [] as HTMLElement[]
  const headings = Array.from(renderer.querySelectorAll('h1,h2,h3,h4,h5,h6')) as HTMLElement[]
  headings.forEach((heading, index) => {
    const title = heading.dataset.headingTitle || cleanHeadingTitle(heading)
    heading.dataset.headingTitle = title
    heading.dataset.foldKey = `${index}:${headingLevel(heading)}:${title}`
  })
  return headings
}

const syncFoldButtons = (headings: HTMLElement[]) => {
  headings.forEach((heading) => {
    const key = heading.dataset.foldKey || ''
    const button = heading.querySelector(':scope > .inline-fold-toggle') as HTMLButtonElement | null
    if (!button) return
    const folded = foldedHeadingKeys.value.has(key)
    heading.dataset.folded = folded ? 'true' : 'false'
    button.dataset.folded = folded ? 'true' : 'false'
    button.setAttribute('aria-expanded', String(!folded))
    button.setAttribute('title', folded ? '展开本节' : '折叠本节')
  })
}

const applyFoldState = () => {
  const renderer = getMarkdownRenderer()
  if (!renderer) return
  const children = Array.from(renderer.children) as HTMLElement[]
  const foldedLevels: number[] = []

  children.forEach((element) => {
    const level = headingLevel(element)
    if (level > 0) {
      while (foldedLevels.length > 0 && foldedLevels[foldedLevels.length - 1]! >= level) {
        foldedLevels.pop()
      }

      const hiddenByParent = foldedLevels.length > 0
      element.style.display = hiddenByParent ? 'none' : ''

      const key = element.dataset.foldKey || ''
      if (!hiddenByParent && foldedHeadingKeys.value.has(key)) {
        foldedLevels.push(level)
      }
      return
    }

    element.style.display = foldedLevels.length > 0 ? 'none' : ''
  })

  syncFoldButtons(Array.from(renderer.querySelectorAll('h1,h2,h3,h4,h5,h6')) as HTMLElement[])
}

const toggleHeadingByKey = (key: string) => {
  const next = new Set(foldedHeadingKeys.value)
  if (next.has(key)) {
    next.delete(key)
  } else {
    next.add(key)
  }
  foldedHeadingKeys.value = next
  applyFoldState()
}

const enhanceHeadings = () => {
  if (isEnhancingHeadings) return
  isEnhancingHeadings = true
  const headings = ensureHeadingKeys()
  const renderer = getMarkdownRenderer()
  if (renderer) applyContentBlockAnchors(renderer, props.node.content_blocks || [])

  headings.forEach((heading) => {
    heading.classList.add('markdown-heading-inline')
    const key = heading.dataset.foldKey || ''
    let button = heading.querySelector(':scope > .inline-fold-toggle') as HTMLButtonElement | null
    if (!button) {
      button = document.createElement('button')
      button.type = 'button'
      button.className = 'inline-fold-toggle'
      button.setAttribute('aria-label', '折叠或展开本节')
      button.setAttribute('tabindex', '-1')
      heading.insertBefore(button, heading.firstChild)
    }
    const toggleCurrentHeading = (event: MouseEvent) => {
      event.preventDefault()
      event.stopPropagation()
      toggleHeadingByKey(heading.dataset.foldKey || key)
    }
    heading.onclick = toggleCurrentHeading
    button.onclick = toggleCurrentHeading
  })

  applyFoldState()
  isEnhancingHeadings = false
}

const scheduleEnhanceHeadings = () => {
  if (enhanceTimer) window.clearTimeout(enhanceTimer)
  enhanceTimer = window.setTimeout(() => {
    void nextTick(() => enhanceHeadings())
  }, 180)
}

onMounted(() => {
  headingObserver = new MutationObserver(() => {
    if (!isEnhancingHeadings) scheduleEnhanceHeadings()
  })
  if (bodyRef.value) {
    headingObserver.observe(bodyRef.value, { childList: true, subtree: true })
  }
  scheduleEnhanceHeadings()
})

onBeforeUnmount(() => {
  headingObserver?.disconnect()
  if (enhanceTimer) window.clearTimeout(enhanceTimer)
})

watch(
  () => [props.content, props.searchWords?.join('|') || ''],
  () => scheduleEnhanceHeadings(),
  { flush: 'post' },
)

</script>

<style scoped>
.markdown-document-editor {
  position: relative;
  width: 100%;
}

.document-body {
  min-width: 0;
  color: #1e293b;
}

.document-body :deep(.markdown-renderer hr) {
  display: none;
}

.document-body :deep(.markdown-renderer h1),
.document-body :deep(.markdown-renderer h2),
.document-body :deep(.markdown-renderer h3),
.document-body :deep(.markdown-renderer h4),
.document-body :deep(.markdown-renderer h5),
.document-body :deep(.markdown-renderer h6) {
  border-bottom: 0 !important;
}

.document-body :deep(.markdown-heading-inline) {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  width: calc(100% + 2.15rem);
  margin-left: -2.15rem;
  padding: 0.28em 0.6em 0.28em 0.35em;
  border-radius: 10px;
  cursor: pointer;
  scroll-margin-top: 96px;
  transition:
    background 0.18s ease,
    color 0.18s ease,
    box-shadow 0.18s ease,
    transform 0.18s ease;
}

.document-body :deep(.markdown-heading-inline:hover) {
  background: linear-gradient(90deg, rgba(59, 130, 246, 0.08), rgba(15, 118, 110, 0.05));
  color: #172554;
  box-shadow: inset 3px 0 0 rgba(59, 130, 246, 0.42);
}

.document-body :deep(.markdown-heading-inline[data-folded='true']) {
  background: linear-gradient(90deg, rgba(99, 102, 241, 0.11), rgba(14, 165, 233, 0.05));
  color: #1e3a8a;
  box-shadow: inset 3px 0 0 rgba(99, 102, 241, 0.58);
}

.document-body :deep(.markdown-heading-inline:hover .inline-fold-toggle) {
  background: rgba(255, 255, 255, 0.82);
  color: #2563eb;
  opacity: 1;
  transform: translateX(1px);
}

.document-body :deep(.inline-fold-toggle) {
  display: inline-flex;
  width: 1.55em;
  height: 1.55em;
  min-width: 1.55em;
  align-items: center;
  justify-content: center;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: #64748b;
  cursor: pointer;
  line-height: 1;
  opacity: 0.64;
  transition:
    background 0.18s ease,
    color 0.18s ease,
    opacity 0.18s ease,
    transform 0.2s cubic-bezier(0.22, 1, 0.36, 1);
}

.document-body :deep(.inline-fold-toggle::before) {
  content: '';
  width: 0.42em;
  height: 0.42em;
  border-right: 2px solid currentColor;
  border-bottom: 2px solid currentColor;
  transform: rotate(45deg) translate(-1px, -1px);
  transition: transform 0.22s cubic-bezier(0.22, 1, 0.36, 1);
}

.document-body :deep(.inline-fold-toggle:hover) {
  background: rgba(255, 255, 255, 0.92);
  color: #1d4ed8;
  opacity: 1;
}

.document-body :deep(.inline-fold-toggle[data-folded='true']) {
  background: rgba(255, 255, 255, 0.84);
  color: #4f46e5;
  opacity: 1;
}

.document-body :deep(.inline-fold-toggle[data-folded='true']::before) {
  transform: rotate(-45deg) translate(-1px, -1px);
}

.document-body :deep(.markdown-heading-inline[data-folded='true'] .inline-fold-toggle) {
  transform: translateX(2px);
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

.animate-blink {
  animation: blink 1s step-end infinite;
}

@media (max-width: 860px) {
  .document-body :deep(.markdown-heading-inline) {
    width: calc(100% + 0.55rem);
    margin-left: -0.55rem;
    padding-left: 0.25em;
  }
}
</style>
