<template>
  <div ref="containerRef" v-html="renderedContent" class="markdown-renderer"></div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import { renderMarkdown } from '../utils/markdown'
import mermaid from 'mermaid'
import logger from '../utils/logger'

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
    securityLevel: 'strict',
    fontFamily: 'Inter, system-ui, sans-serif',
})

let isThrottled = false
let hasPendingUpdate = false

const escapeRegExp = (val: string) => val.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

const cleanMermaidCode = (code: string): string => {
    const sanitizeQuotedLabels = (input: string): string => {
        const pairs: Record<string, string> = {
            '[': ']',
            '(': ')',
            '{': '}',
            '|': '|',
        }

        let output = ''
        for (let i = 0; i < input.length; i++) {
            const start = input[i]
            const end = pairs[start]

            if (end && input[i + 1] === '"') {
                let j = i + 2
                while (j < input.length) {
                    if (input[j] === '"' && input[j + 1] === end) {
                        const content = input.slice(i + 2, j).replace(/"/g, "'")
                        output += `${start}"${content}"${end}`
                        i = j + 1
                        break
                    }
                    j++
                }

                if (j < input.length) {
                    continue
                }
            }

            output += start
        }

        return output
    }

    return sanitizeQuotedLabels(code)
        .replace(/\r\n?/g, '\n')
        .replace(/[\u201C\u201D]/g, '"')
        .replace(/[\u2018\u2019]/g, "'")
        .replace(/\u00A0/g, ' ')
        .replace(/\t/g, '    ')
        .trim()
}

const addMermaidSafetyMargin = (svgMarkup: string): string => {
    if (typeof window === 'undefined') return svgMarkup

    const parser = new DOMParser()
    const doc = parser.parseFromString(svgMarkup, 'image/svg+xml')
    const svg = doc.documentElement

    if (!svg || svg.tagName.toLowerCase() !== 'svg') {
        return svgMarkup
    }

    const extraRight = 24
    const extraNodeWidth = 12

    const viewBox = svg.getAttribute('viewBox')
    if (viewBox) {
        const parts = viewBox.split(/\s+/).map(Number)
        if (parts.length === 4 && parts.every(Number.isFinite)) {
            parts[2] += extraRight
            svg.setAttribute('viewBox', parts.join(' '))
        }
    }

    const width = svg.getAttribute('width')
    if (width) {
        const match = width.match(/^([\d.]+)(px)?$/)
        if (match) {
            const nextWidth = Number(match[1]) + extraRight
            svg.setAttribute('width', `${nextWidth}${match[2] || ''}`)
        }
    }

    const currentStyle = svg.getAttribute('style') || ''
    const nextStyle = /overflow\s*:/.test(currentStyle)
        ? currentStyle
        : `${currentStyle}${currentStyle && !currentStyle.trim().endsWith(';') ? ';' : ''}overflow: visible;`
    svg.setAttribute('style', nextStyle)

    const shapeSelectors = ['rect.basic.label-container', 'rect.label-container', 'g.node rect']
    const adjusted = new Set<Element>()

    shapeSelectors.forEach(selector => {
        svg.querySelectorAll(selector).forEach(node => {
            if (adjusted.has(node)) return
            adjusted.add(node)

            const widthAttr = node.getAttribute('width')
            if (widthAttr) {
                const currentWidth = Number(widthAttr)
                if (Number.isFinite(currentWidth)) {
                    node.setAttribute('width', String(currentWidth + extraNodeWidth))
                }
            }
        })
    })

    return svg.outerHTML
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
            const adjustedSvg = addMermaidSafetyMargin(svg)
            
            // Update the element
            mermaidEl.innerHTML = adjustedSvg
            mermaidEl.setAttribute('data-processed', 'true')
            mermaidEl.style.opacity = '1'
            
        } catch (err: any) {
            logger.error('Mermaid render error:', err)
            
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
