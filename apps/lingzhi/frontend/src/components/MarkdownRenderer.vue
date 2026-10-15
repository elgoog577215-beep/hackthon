<template>
  <div ref="containerRef" class="markdown-renderer"></div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount, h, render, getCurrentInstance, useId } from 'vue'
import TeachingDiagram from './TeachingDiagram.vue'
import { activeLocale } from '../shared/i18n'
import { renderMarkdown } from '../utils/markdown'
import { bindInlineMarkdownSource } from '../utils/inline-markdown-source'
import { highlightRenderedMarkdownText } from '../utils/markdown-highlight'
import { createMarkdownDom } from '../utils/markdown-dom'
import { createMarkdownMermaidQueue } from '../utils/markdown-mermaid-queue'
import { createMarkdownCodeActions, MarkdownCodeExecutionError } from '../utils/markdown-code-actions'
import logger from '../utils/logger'
import { renderMermaidSvg } from '../utils/mermaid'
import http from '../utils/http'
import { ElMessage } from 'element-plus'

const props = withDefaults(defineProps<{
  content: string
  inlineEditable?: boolean
  searchWords?: string[]
  enableCodeRun?: boolean
}>(), {
  searchWords: () => [],
  enableCodeRun: true,
})

const containerRef = ref<HTMLElement | null>(null)
const appContext = getCurrentInstance()?.appContext
const diagramPrefix = useId().replace(/[^\w-]/g, '-')
const diagramHosts = new Set<Element>()
const mermaidHosts = new Set<HTMLElement>()
const tr = (zh: string, en: string) => activeLocale.value === 'en' ? en : zh
let identity = 0
let dom: ReturnType<typeof createMarkdownDom> | undefined
let codeActions: ReturnType<typeof createMarkdownCodeActions> | undefined
let lastHtml = ''
let displayedContent = ''
const decodeSource = (raw: string) => { try { return decodeURIComponent(raw) } catch { return raw } }

function refreshMermaidText() {
  if (!containerRef.value) return
  containerRef.value.querySelectorAll<HTMLElement>('[data-mermaid-label]').forEach(el => {
    const label = el.dataset.mermaidLabel
    el.textContent = label === 'pending' ? tr('图表正在生成…', 'Generating diagram…')
      : label === 'title' ? tr('图表暂不可渲染', 'Diagram cannot be rendered')
      : label === 'summary' ? tr('查看源代码', 'View source')
      : tr('已保留源代码，不影响继续阅读。', 'The source is preserved. You can continue reading.')
  })
}

const mermaidQueue = createMarkdownMermaidQueue(diagramPrefix, renderMermaidSvg, (host, result) => {
  if (!mermaidHosts.has(host)) return
  if (result.svg !== undefined) {
    // renderMermaidSvg uses Mermaid's strict security mode; never insert raw Markdown here.
    host.innerHTML = result.svg
  } else {
    logger.warn('Mermaid diagram fell back to source preview:', result.error instanceof Error ? result.error.message : result.error)
    const fallback = document.createElement('div')
    fallback.className = 'mermaid-fallback'
    const title = document.createElement('p')
    title.dataset.mermaidLabel = 'title'; title.setAttribute('role', 'status')
    const note = document.createElement('p'); note.dataset.mermaidLabel = 'note'
    const details = document.createElement('details')
    const summary = document.createElement('summary'); summary.dataset.mermaidLabel = 'summary'
    const pre = document.createElement('pre'); pre.textContent = decodeSource(host.dataset.code || '')
    details.append(summary, pre); fallback.append(title, note, details); host.replaceChildren(fallback)
    refreshMermaidText()
  }
  host.dataset.processed = 'true'
  host.style.opacity = '1'
})

function removeEnhancements(node: Node) {
  for (const host of diagramHosts) if (node.contains(host)) {
    render(null, host); diagramHosts.delete(host)
  }
  for (const host of mermaidHosts) if (node.contains(host)) {
    mermaidQueue.forget(host); mermaidHosts.delete(host)
  }
  codeActions?.remove(node)
}

function enhanceContent() {
  const root = containerRef.value
  if (!root) return
  root.querySelectorAll<HTMLElement>('.teaching-diagram-host').forEach(host => {
    if (diagramHosts.has(host)) return
    const vnode = h(TeachingDiagram, {
      raw: decodeSource(host.dataset.diagram || ''),
      pending: host.dataset.pending === 'true',
      instanceId: diagramPrefix + '-teaching-' + (++identity),
    })
    if (appContext) vnode.appContext = appContext
    render(vnode, host)
    diagramHosts.add(host)
  })
  root.querySelectorAll<HTMLElement>('.mermaid').forEach(host => {
    if (mermaidHosts.has(host)) return
    mermaidHosts.add(host)
    if (host.dataset.pending === 'true') {
      const status = document.createElement('p')
      status.dataset.mermaidLabel = 'pending'; status.setAttribute('role', 'status')
      host.replaceChildren(status)
    } else mermaidQueue.observe(host, decodeSource(host.dataset.code || host.textContent || ''))
  })
  refreshMermaidText()
  codeActions?.enhance(props.enableCodeRun)
}

const updateContent = () => {
  if (!dom) return
  let html = renderMarkdown(props.content || '')
  if (props.inlineEditable) html = bindInlineMarkdownSource(html, props.content)
  if (props.searchWords.length) html = highlightRenderedMarkdownText(html, props.searchWords)
  const replacement = Boolean(displayedContent && props.content !== displayedContent && !props.content.startsWith(displayedContent))
  if (html !== lastHtml || replacement) {
    dom.update(html, replacement)
    lastHtml = html
    enhanceContent()
  }
  displayedContent = props.content || ''
}

// Keep the existing frame cadence: every arriving append reaches the next
// frame, while settled DOM islands keep their live component and UI state.
let pendingFrame = 0
let lastContent = ''
const scheduleUpdate = () => {
  if (pendingFrame) return
  if (typeof requestAnimationFrame !== 'function') { updateContent(); return }
  pendingFrame = requestAnimationFrame(() => { pendingFrame = 0; updateContent() })
}

watch(() => [props.content, props.searchWords, props.inlineEditable], () => {
  const nextContent = props.content || ''
  const append = Boolean(lastContent && nextContent.length > lastContent.length && nextContent.startsWith(lastContent))
  lastContent = nextContent
  if (append) { scheduleUpdate(); return }
  if (pendingFrame) cancelAnimationFrame(pendingFrame)
  pendingFrame = 0
  updateContent()
}, { immediate: true, flush: 'sync' })
watch(() => props.enableCodeRun, enabled => codeActions?.enhance(enabled))
watch(activeLocale, () => { refreshMermaidText(); codeActions?.refresh() })

onMounted(() => {
  const root = containerRef.value!
  codeActions = createMarkdownCodeActions(root, {
    tr,
    execute: async (code, language, signal) => {
      const res = await http.post('/api/execute', { code, language, timeout: 10 }, { signal })
      const output = [res.data?.output, res.data?.error].filter(Boolean).join('\n')
      if (res.data?.success === false) throw new MarkdownCodeExecutionError(output)
      return output
    },
    notify: (message, error) => { if (error) ElMessage.error(message); else ElMessage.success(message) },
  })
  dom = createMarkdownDom(root, removeEnhancements)
  updateContent()
})

onBeforeUnmount(() => {
  if (pendingFrame) cancelAnimationFrame(pendingFrame)
  dom?.clear()
  mermaidQueue.dispose()
  codeActions?.dispose()
})
</script>

<style scoped>
.markdown-renderer {
    overflow-wrap: break-word;
    word-break: break-word;
    color: inherit;
    line-height: 1.78;
}

:deep(p) {
    margin: 0 0 0.9em;
}

:deep(p:last-child) {
    margin-bottom: 0;
}

:deep(h2),
:deep(h3),
:deep(h4) {
    margin: 1.45em 0 0.58em;
    color: var(--lz-text-strong, #172033);
    font-weight: 780;
    line-height: 1.38;
}

:deep(h2:first-child),
:deep(h3:first-child),
:deep(h4:first-child) {
    margin-top: 0;
}

:deep(h2) { font-size: 1.34em; }
:deep(h3) { font-size: 1.18em; }
:deep(h4) { font-size: 1.06em; }

:deep(ul),
:deep(ol) {
    margin: 0.55em 0 1em;
    padding-inline-start: 1.55em;
}

:deep(ul) { list-style: disc outside; }
:deep(ol) { list-style: decimal outside; }
:deep(ul ul) { list-style-type: circle; }
:deep(ol ol) { list-style-type: lower-alpha; }

:deep(li) {
    margin: 0.34em 0;
    padding-inline-start: 0.16em;
}

:deep(li::marker) {
    color: color-mix(in srgb, currentColor 65%, #10b981);
    font-weight: 720;
}

:deep(blockquote) {
    margin: 1em 0;
    padding: 0.65em 0.95em;
    border-left: 3px solid #94a3b8;
    border-radius: 0 7px 7px 0;
    background: rgba(248, 250, 252, 0.9);
    color: var(--lz-text-secondary, #475569);
}

:deep(code:not(pre code):not(.math-fallback)) {
    border: 1px solid rgba(203, 213, 225, 0.66);
    border-radius: 5px;
    background: #f8fafc;
    color: #334155;
    font-size: 0.88em;
    padding: 0.08em 0.28em;
}

:deep(table) {
    width: 100%;
    margin: 1em 0;
    border-collapse: collapse;
    font-size: 0.94em;
}

:deep(th),
:deep(td) {
    padding: 0.58em 0.72em;
    border: 1px solid rgba(203, 213, 225, 0.82);
    text-align: left;
    vertical-align: top;
}

:deep(th) {
    background: #f8fafc;
    color: var(--lz-text-strong, #172033);
    font-weight: 750;
}

:deep(hr) {
    margin: 1.4em 0;
    border: 0;
    border-top: 1px solid rgba(203, 213, 225, 0.82);
}

:deep(.math-fallback) {
    display: inline-block;
    max-width: 100%;
    overflow-x: auto;
    border: 1px dashed rgba(148, 163, 184, 0.7);
    border-radius: 6px;
    background: rgba(248, 250, 252, 0.9);
    color: #475569;
    font-size: 0.88em;
    line-height: 1.55;
    padding: 0.12rem 0.35rem;
    white-space: pre-wrap;
    word-break: break-word;
}

:deep(.katex-display > .math-fallback) {
    padding: 0.5rem 0.7rem;
    text-align: left;
}

:deep(.katex-display) {
    max-width: 100%;
    overflow-x: auto;
    overflow-y: hidden;
    padding-bottom: 0.2rem;
    -webkit-overflow-scrolling: touch;
}

:deep(pre),
:deep(table) {
    max-width: 100%;
    overflow-x: auto;
}

:deep(.markdown-code-tools) {
    position: static;
    display: flex;
    justify-content: flex-end;
    align-items: center;
    gap: 8px;
    padding: 8px 12px 0;
}

:deep(.markdown-code-tools .copy-btn),
:deep(.markdown-code-tools span) {
    opacity: 1;
    font-size: 15px;
}

:deep(.copy-btn) {
    min-height: 32px;
    font-size: 15px;
}

:deep(.code-run-button) {
    border: 1px solid rgba(148, 163, 184, 0.45);
    border-radius: 8px;
    background: rgba(255, 255, 255, 0.92);
    color: #334155;
    cursor: pointer;
    font-size: 15px;
    font-weight: 700;
    line-height: 1;
    padding: 6px 8px;
}

:deep(.code-run-button:hover) {
    background: #f8fafc;
    color: #4f46e5;
}

:deep(.code-run-button:disabled) {
    cursor: wait;
    opacity: 0.6;
}

:deep(.code-run-result) {
    margin-top: -0.5rem;
    margin-bottom: 1rem;
    border: 1px solid rgba(203, 213, 225, 0.8);
    border-radius: 8px;
    background: #f8fafc;
    color: #334155;
    font-size: 15px;
    padding: 0.75rem;
    white-space: pre-wrap;
}

:deep(.mermaid-fallback) {
    padding: 16px;
    margin: 8px 0;
    border: 1px solid #cbd5e1;
    background: #f8fafc;
    color: #475569;
    font-size: 15px;
}

:deep(.mermaid-fallback summary) { cursor: pointer; }
:deep(.mermaid-fallback pre) { max-height: 160px; overflow: auto; }
</style>
