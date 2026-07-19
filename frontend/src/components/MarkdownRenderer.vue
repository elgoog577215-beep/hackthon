<template>
  <div ref="containerRef" v-html="renderedContent" class="markdown-renderer"></div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import { renderMarkdown } from '../utils/markdown'
import { highlightRenderedMarkdownText } from '../utils/markdown-highlight'
import logger from '../utils/logger'
import { renderMermaidSvg } from '../utils/mermaid'
import http from '../utils/http'
import { ElMessage } from 'element-plus'

const props = withDefaults(defineProps<{
  content: string
  searchWords?: string[]
  enableCodeRun?: boolean
}>(), {
  searchWords: () => [],
  enableCodeRun: true,
})

const containerRef = ref<HTMLElement | null>(null)
const renderedContent = ref('')
const throttleDelay = 150 // 150ms 节流，平衡流畅度和性能

let isThrottled = false
let hasPendingUpdate = false

const escapeHtml = (val: string) => val
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
const decodeMermaidCode = (raw: string) => {
    try {
        return decodeURIComponent(raw)
    } catch {
        return raw
    }
}

const renderMermaid = async () => {
    await nextTick()
    if (!containerRef.value) return
    
    const mermaidDivs = containerRef.value.querySelectorAll('.mermaid')
    if (mermaidDivs.length === 0) return

    // Process each diagram individually for better error handling
    for (const el of Array.from(mermaidDivs)) {
        const mermaidEl = el as HTMLElement
        
        try {
            // Skip if already processed successfully
            if (mermaidEl.getAttribute('data-processed') === 'true') continue
            
            // Get and clean the code
            let code = ''
            const rawCode = mermaidEl.getAttribute('data-code')
            if (rawCode) {
                code = decodeURIComponent(rawCode)
            } else {
                code = mermaidEl.textContent || ''
            }
            
            if (!code.trim()) {
                throw new Error('Empty diagram code')
            }
            
            // Clean the syntax
            // Generate unique ID
            const id = `mermaid-${Date.now()}-${Math.floor(Math.random() * 10000)}`
            const adjustedSvg = await renderMermaidSvg(id, code)
            
            // Update the element
            mermaidEl.innerHTML = adjustedSvg
            mermaidEl.setAttribute('data-processed', 'true')
            mermaidEl.style.opacity = '1'
            
        } catch (err: any) {
            logger.warn('Mermaid diagram fell back to source preview:', err?.message || err)
            
            // Keep reading smooth when AI-generated diagrams use unsupported syntax.
            const rawCode = decodeMermaidCode(mermaidEl.getAttribute('data-code') || mermaidEl.textContent || '')
            mermaidEl.innerHTML = `
                <div class="mermaid-fallback bg-slate-50 border border-slate-200 rounded-lg p-4 my-2">
                    <div class="flex items-center gap-2 text-slate-600 font-medium mb-2">
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19h16"/><path d="M4 5h16"/><path d="M8 9v6"/><path d="M16 9v6"/><path d="M12 7v10"/></svg>
                        图表暂不可渲染
                    </div>
                    <div class="text-xs text-slate-500 mb-2">已保留源代码，不影响继续阅读。</div>
                    <details class="text-xs">
                        <summary class="cursor-pointer text-slate-600 hover:text-slate-800">查看源代码</summary>
                        <pre class="mt-2 p-2 bg-white rounded border border-slate-200 overflow-auto max-h-32 text-slate-600">${escapeHtml(rawCode)}</pre>
                    </details>
                </div>
            `
            mermaidEl.setAttribute('data-processed', 'true')
            mermaidEl.style.opacity = '1'
        }
    }
}

const codeLanguage = (codeEl: HTMLElement) => {
    const className = Array.from(codeEl.classList).find(name => name.startsWith('language-')) || ''
    const raw = className.replace('language-', '').toLowerCase()
    if (raw === 'python' || raw === 'py') return 'python'
    if (raw === 'javascript' || raw === 'js') return 'javascript'
    return ''
}

const enhanceCodeBlocks = async () => {
    await nextTick()
    if (!containerRef.value || !props.enableCodeRun) return
    const blocks = containerRef.value.querySelectorAll('pre > code')
    blocks.forEach((codeEl) => {
        const code = codeEl as HTMLElement
        const pre = code.parentElement as HTMLElement | null
        if (!pre || pre.dataset.runEnhanced === 'true') return
        const language = codeLanguage(code)
        if (!language) return

        pre.dataset.runEnhanced = 'true'
        pre.classList.add('code-run-block')
        const button = document.createElement('button')
        button.type = 'button'
        button.className = 'code-run-button'
        button.textContent = '运行'
        button.title = `运行 ${language} 代码`
        const result = document.createElement('pre')
        result.className = 'code-run-result'
        result.style.display = 'none'

        button.onclick = async () => {
            button.setAttribute('disabled', 'true')
            result.style.display = 'block'
            result.textContent = '运行中...'
            try {
                const res = await http.post('/api/execute', {
                    code: code.textContent || '',
                    language,
                    timeout: 10,
                })
                const output = [res.data?.output, res.data?.error].filter(Boolean).join('\n')
                result.textContent = output || '无输出'
            } catch (error) {
                result.textContent = '运行失败'
                ElMessage.error('代码运行失败')
            } finally {
                button.removeAttribute('disabled')
            }
        }

        pre.appendChild(button)
        pre.insertAdjacentElement('afterend', result)
    })
}

const updateContent = () => {
    // 确保处理空内容
    if (!props.content) {
        renderedContent.value = ''
        return
    }
    // 这里执行耗时的 renderMarkdown
    let html = renderMarkdown(props.content)

    // Apply search highlighting
    if (props.searchWords && props.searchWords.length > 0) {
        html = highlightRenderedMarkdownText(html, props.searchWords)
    }

    renderedContent.value = html
}

watch(renderedContent, () => {
    renderMermaid()
    enhanceCodeBlocks()
}, { flush: 'post' })

watch(() => [props.content, props.searchWords], () => {
    if (!isThrottled) {
        updateContent()
        isThrottled = true
        setTimeout(() => {
            isThrottled = false
            if (hasPendingUpdate) {
                updateContent()
                hasPendingUpdate = false
            }
        }, throttleDelay)
    } else {
        hasPendingUpdate = true
    }
}, { immediate: true })

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

:deep(.code-run-block) {
    position: relative;
}

:deep(.code-run-button) {
    position: absolute;
    top: 8px;
    right: 8px;
    border: 1px solid rgba(148, 163, 184, 0.45);
    border-radius: 8px;
    background: rgba(255, 255, 255, 0.92);
    color: #334155;
    cursor: pointer;
    font-size: 12px;
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
    font-size: 12px;
    padding: 0.75rem;
    white-space: pre-wrap;
}
</style>
