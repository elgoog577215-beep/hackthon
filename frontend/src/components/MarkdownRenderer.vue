<template>
  <div ref="containerRef" v-html="renderedContent" class="markdown-renderer"></div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import { renderMarkdown } from '../utils/markdown'
import mermaid from 'mermaid'

const props = defineProps<{
  content: string
  searchWords?: string[]
}>()

const containerRef = ref<HTMLElement | null>(null)
const renderedContent = ref('')
const throttleDelay = 150 // 150ms 节流，平衡流畅度和性能

// Initialize mermaid
mermaid.initialize({
    startOnLoad: false,
    theme: 'default',
    securityLevel: 'loose',
    fontFamily: 'Inter, system-ui, sans-serif',
})

let isThrottled = false
let hasPendingUpdate = false

const escapeRegExp = (val: string) => val.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

const cleanMermaidCode = (code: string): string => {
    // Helper to escape quotes and wrap in quotes
    const cleanLabel = (text: string): string => {
        text = text.trim()
        // If already wrapped in quotes, strip them first to avoid double quoting
        if (text.startsWith('"') && text.endsWith('"') && text.length >= 2) {
            text = text.slice(1, -1)
        }
        // Escape internal double quotes
        text = text.replace(/"/g, '#quot;')
        // Also escape parentheses if they are causing issues, but usually quotes are enough
        // text = text.replace(/\(/g, '#40;').replace(/\)/g, '#41;')
        return `"${text}"`
    }

    let cleaned = code

    // 1. Clean node labels
    // Order matters: match longest/most specific delimiters first
    
    // {{...}} -> {{"..."}}
    cleaned = cleaned.replace(/\{\{(?!\{)(.*?)\}\}/g, (_, content) => `{{${cleanLabel(content)}}}`)
    
    // [[...]] -> [["..."]]
    cleaned = cleaned.replace(/\[\[(?!\[)(.*?)\]\]/g, (_, content) => `[[${cleanLabel(content)}]]`)
    
    // [(...)] -> [("...")]
    cleaned = cleaned.replace(/\[\((?!\()(.*?)\)\]/g, (_, content) => `[(${cleanLabel(content)})]`)
    
    // ((...)) -> (("..."))
    cleaned = cleaned.replace(/\(\((?!\()(.*?)\)\)/g, (_, content) => `((${cleanLabel(content)}))`)
    
    // ([...]) -> (["..."])
    cleaned = cleaned.replace(/\(\[(?!\[)(.*?)\]\)/g, (_, content) => `([${cleanLabel(content)}])`)
    
    // [...] -> ["..."]
    // Exclude [[, [(, [/, [\
    cleaned = cleaned.replace(/(?<!\()\[(?![(\[\/\\])(.*?)(?<![)\]\/\\])\](?!\])/g, (_, content) => `[${cleanLabel(content)}]`)
    
    // (...) -> ("...")
    // Exclude ((, ([
    cleaned = cleaned.replace(/(?<!\()(\()(?!\(|\[)(.*?)(?<!\))(\))/g, (_, _p1, content, _p3) => `(${cleanLabel(content)})`)
    
    // {...} -> {"..."}
    // Exclude {{
    cleaned = cleaned.replace(/(?<!\{)\{(?!\{)(.*?)\}(?!\})/g, (_, content) => `{${cleanLabel(content)}}`)

    // 2. Clean link labels: |...| -> |"..."|
    cleaned = cleaned.replace(/\|(.*?)\|/g, (_, content) => `|${cleanLabel(content)}|`)

    return cleaned
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
            const cleaned = cleanMermaidCode(code)
            
            // Generate unique ID
            const id = `mermaid-${Date.now()}-${Math.floor(Math.random() * 10000)}`
            
            // Render using mermaid.render for better error handling
            const { svg } = await mermaid.render(id, cleaned)
            
            // Update the element
            mermaidEl.innerHTML = svg
            mermaidEl.setAttribute('data-processed', 'true')
            mermaidEl.style.opacity = '1'
            
        } catch (err: any) {
            console.error('Mermaid render error:', err)
            
            // Show error UI with retry button
            const rawCode = mermaidEl.getAttribute('data-code') || mermaidEl.textContent || ''
            mermaidEl.innerHTML = `
                <div class="mermaid-error bg-red-50 border border-red-200 rounded-lg p-4 my-2">
                    <div class="flex items-center gap-2 text-red-600 font-medium mb-2">
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                        图表渲染失败
                    </div>
                    <div class="text-xs text-slate-500 mb-2">${err.message || '语法错误'}</div>
                    <details class="text-xs">
                        <summary class="cursor-pointer text-slate-600 hover:text-slate-800">查看源代码</summary>
                        <pre class="mt-2 p-2 bg-white rounded border border-slate-200 overflow-auto max-h-32 text-slate-600">${rawCode.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</pre>
                    </details>
                    <button class="retry-btn mt-3 px-3 py-1.5 bg-white border border-slate-300 rounded-lg text-xs text-slate-600 hover:bg-slate-50 transition-colors">
                        重试渲染
                    </button>
                </div>
            `
            mermaidEl.style.opacity = '1'
            
            // Attach retry handler
            const retryBtn = mermaidEl.querySelector('.retry-btn')
            if (retryBtn) {
                retryBtn.addEventListener('click', (e) => {
                    e.stopPropagation()
                    mermaidEl.removeAttribute('data-processed')
                    const rawCode = mermaidEl.getAttribute('data-code')
                    if (rawCode) {
                        mermaidEl.textContent = decodeURIComponent(rawCode)
                    }
                    renderMermaid()
                })
            }
        }
    }
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
        const tokens = Array.from(new Set(props.searchWords.map(t => escapeRegExp(t)).filter(Boolean)))
        if (tokens.length > 0) {
            const regex = new RegExp(`(${tokens.join('|')})`, 'gi')
            html = html.replace(regex, '<span class="bg-yellow-200 text-slate-900 rounded px-0.5 box-decoration-clone">$1</span>')
        }
    }

    renderedContent.value = html
}

watch(renderedContent, () => {
    renderMermaid()
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
    /* display: inline; Removed to allow default block behavior */
}
/* 继承父级的排版样式 */
:deep(p:last-child) {
    margin-bottom: 0;
}
</style>
