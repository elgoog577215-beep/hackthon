import { nextTick, onUnmounted } from 'vue'
import mermaid from 'mermaid'

// Initialize globally once
mermaid.initialize({
    startOnLoad: false,
    theme: 'base',
    securityLevel: 'loose',
    fontFamily: 'ui-sans-serif, system-ui, sans-serif',
    themeVariables: {
        primaryColor: '#8b5cf6',
        primaryTextColor: '#0f172a',
        primaryBorderColor: '#7c3aed',
        lineColor: '#334155',
        secondaryColor: '#ede9fe',
        tertiaryColor: '#ffffff',
        mainBkg: '#f8fafc',
        nodeBorder: '#cbd5e1',
        clusterBkg: '#f1f5f9',
        clusterBorder: '#cbd5e1',
        titleColor: '#0f172a',
        edgeLabelBackground: '#ffffff',
    }
});

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
                console.error('Queue task failed', e);
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

export function useMermaid() {
    const observedElements = new WeakSet()
    let observer: IntersectionObserver | null = null

    // Helper to fix common Mermaid syntax errors
    const fixMermaidCode = (code: string): string => {
        let fixed = code;
        const replaceQuotes = (match: string, start: string, content: string, end: string) => {
            const safeContent = content.replace(/"/g, "'");
            return `${start}${safeContent}${end}`;
        };

        // Fix various bracket types with quoted content
        // 1. ["..."]
        fixed = fixed.replace(/(\[")([\s\S]*?)("\])/g, replaceQuotes);
        // 2. ("...")
        fixed = fixed.replace(/(\(")([\s\S]*?)("\))/g, replaceQuotes);
        // 3. {"..."}
        fixed = fixed.replace(/(\{")([\s\S]*?)("\})/g, replaceQuotes);
        // 4. [["..."]]
        fixed = fixed.replace(/(\[\[")([\s\S]*?)("\]\])/g, replaceQuotes);
        // 5. (["..."])
        fixed = fixed.replace(/(\(\[")([\s\S]*?)("\]\))/g, replaceQuotes);
        // 6. [("...")]
        fixed = fixed.replace(/(\[\(")([\s\S]*?)("\)\])/g, replaceQuotes);
        // 7. (("..."))
        fixed = fixed.replace(/(\(\(")([\s\S]*?)("\)\))/g, replaceQuotes);
        // 8. {{"..."}}
        fixed = fixed.replace(/(\{\{")([\s\S]*?)("\}\})/g, replaceQuotes);
        
        // Fix: Replace backslash in labels if not escaping something? 
        // Actually, LLMs sometimes output \ without escaping. But let's stick to quotes for now.
        
        return fixed;
    }

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
             
             // Auto-fix common syntax errors
             code = fixMermaidCode(code);
             
             // Generate unique ID for this diagram
             const id = `mermaid-${Date.now()}-${Math.floor(Math.random() * 10000)}`
             
             try {
                 // Check if code is empty
                 if (!code.trim()) {
                     throw new Error('Empty diagram code')
                 }
     
                 // Use mermaid.render instead of mermaid.run for better control and stability
                 const { svg } = await mermaid.render(id, code)
                 
                 // Update target content with generated SVG
                 target.innerHTML = svg
                 target.style.opacity = '1'
                 
             } catch (err: any) {
                 console.error('Mermaid render error:', err)
                 
                 // If render fails, we construct a nice error UI
                 target.innerHTML = `
                     <div class="text-red-500 text-sm p-3 border border-red-200 rounded-lg bg-red-50">
                         <div class="font-bold mb-2 flex items-center gap-2">
                             <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                             图表渲染失败
                         </div>
                         <div class="text-xs text-slate-500 mb-2">${err.message || '未知错误'}</div>
                         <pre class="text-xs font-mono overflow-auto text-slate-600 bg-white p-2 rounded border border-red-100 max-h-40 whitespace-pre-wrap break-all">${code.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</pre>
                         <button class="mt-2 px-3 py-1 bg-white border border-slate-300 rounded hover:bg-slate-50 text-xs text-slate-600 transition-colors retry-btn">重试渲染</button>
                     </div>`
                 target.style.opacity = '1'
                 
                 // Attach retry handler
                 const retryBtn = target.querySelector('.retry-btn')
                 if (retryBtn) {
                     retryBtn.addEventListener('click', (e) => {
                         e.stopPropagation()
                         target.removeAttribute('data-processed')
                         target.innerHTML = '' // Clear error
                         renderDiagram(target)
                     })
                 }
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
