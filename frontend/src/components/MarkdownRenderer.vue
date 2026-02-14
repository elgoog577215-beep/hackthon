<template>
  <div ref="containerRef" v-html="renderedContent" class="markdown-renderer"></div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick, onMounted } from 'vue'
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
    if (mermaidDivs.length > 0) {
        try {
            // Reset processed attribute to allow re-rendering if content changed
            mermaidDivs.forEach(el => {
                if (el.getAttribute('data-processed')) {
                    el.removeAttribute('data-processed')
                }
                // Always restore and clean code
                const rawCode = el.getAttribute('data-code')
                if (rawCode) {
                    const decoded = decodeURIComponent(rawCode)
                    // Clean the syntax before rendering
                    const cleaned = cleanMermaidCode(decoded)
                    el.textContent = cleaned
                }
            })
            
            await mermaid.run({
                nodes: Array.from(mermaidDivs) as HTMLElement[]
            })
        } catch (e) {
            console.error('Mermaid rendering failed:', e)
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
