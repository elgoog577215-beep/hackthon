import { nextTick, onUnmounted } from 'vue'
import logger from '../utils/logger'
import { renderMermaidSvg } from '../utils/mermaid'

// Render Queue System
// Mermaid is not concurrency-safe for rendering. We must process one by one.
const renderQueue: Array<() => Promise<void>> = [];
let isProcessing = false;

const processQueue = async () => {
    if (isProcessing || renderQueue.length === 0) return;
    
    isProcessing = true;
    while (renderQueue.length > 0) {
        const task = renderQueue.shift();
        if (task) {
            try {
                await task();
            } catch (e) {
                logger.error('Queue task failed', e);
            }
            // Small delay to allow UI updates
            await new Promise(resolve => setTimeout(resolve, 50));
        }
    }
    isProcessing = false;
};

const addToQueue = (task: () => Promise<void>) => {
    renderQueue.push(task);
    processQueue();
};

const escapeHtml = (val: string) => val
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

export function useMermaid() {
    const observedElements = new WeakSet()
    let observer: IntersectionObserver | null = null

    const renderDiagram = (target: HTMLElement) => {
        // Double check to prevent duplicate processing
        if (target.getAttribute('data-processed') === 'true') return
        
        // Mark as processing immediately to prevent duplicate queuing
        target.setAttribute('data-processed', 'true')
        
        addToQueue(async () => {
             // Re-check if element is still in document
             if (!document.contains(target)) return;

             // Capture original code
             let code = ''
             const codeAttr = target.getAttribute('data-code')
             if (codeAttr) {
                 try {
                     code = decodeURIComponent(codeAttr)
                 } catch (e) {
                     code = target.textContent || ''
                 }
             } else {
                 code = target.textContent || ''
             }
             
             // Generate unique ID for this diagram
             const id = `mermaid-${Date.now()}-${Math.floor(Math.random() * 10000)}`
             
             try {
                 // Check if code is empty
                 if (!code.trim()) {
                     throw new Error('Empty diagram code')
                 }
     
                  const svg = await renderMermaidSvg(id, code)

                  // Update target content with generated SVG
                  target.innerHTML = svg
                 target.style.opacity = '1'
                 
             } catch (err: any) {
                 logger.warn('Mermaid diagram fell back to source preview:', err?.message || err)
                 
                 // Keep reading smooth when AI-generated diagrams use unsupported syntax.
                 target.innerHTML = `
                     <div class="text-slate-600 text-sm p-3 border border-slate-200 rounded-lg bg-slate-50">
                         <div class="font-bold mb-2 flex items-center gap-2">
                             <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19h16"/><path d="M4 5h16"/><path d="M8 9v6"/><path d="M16 9v6"/><path d="M12 7v10"/></svg>
                             图表暂不可渲染
                         </div>
                         <div class="text-xs text-slate-500 mb-2">已保留源代码，不影响继续阅读。</div>
                         <pre class="text-xs font-mono overflow-auto text-slate-600 bg-white p-2 rounded border border-slate-200 max-h-40 whitespace-pre-wrap break-all">${escapeHtml(code)}</pre>
                     </div>`
                 target.style.opacity = '1'
             }
        });
    }

    const initObserver = () => {
        if (observer) return
        
        observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const target = entry.target as HTMLElement
                    // Only process if not already processed
                    if (target.getAttribute('data-processed') !== 'true') {
                        renderDiagram(target)
                    }
                    // Stop observing regardless of success/fail to prevent loops
                    observer?.unobserve(target)
                }
            })
        }, { rootMargin: '200px 0px' })
    }

    const scan = () => {
        nextTick(() => {
            const diagrams = document.querySelectorAll('.mermaid')
            diagrams.forEach(el => {
                if (!observedElements.has(el)) {
                    if (!observer) initObserver()
                    observer?.observe(el)
                    observedElements.add(el)
                }
            })
        })
    }
    
    // Cleanup on component unmount
    onUnmounted(() => {
        if (observer) {
            observer.disconnect()
            observer = null
        }
    })

    return {
        scanMermaidDiagrams: scan
    }
}
