import MarkdownIt from 'markdown-it';
import markdownItKatex from 'markdown-it-katex';
import mermaid from 'mermaid';
import hljs from 'highlight.js';
import DOMPurify from 'dompurify';
import linkAttributes from 'markdown-it-link-attributes';
import 'highlight.js/styles/atom-one-dark.css';

// Initialize mermaid
mermaid.initialize({
    startOnLoad: false,
    theme: 'base',
    securityLevel: 'loose',
    fontFamily: 'ui-sans-serif, system-ui, sans-serif',
    themeVariables: {
        primaryColor: '#8b5cf6', // primary-500
        primaryTextColor: '#ffffff',
        primaryBorderColor: '#7c3aed', // primary-600
        lineColor: '#64748b', // slate-500
        secondaryColor: '#ede9fe', // primary-100
        tertiaryColor: '#ffffff',
        mainBkg: '#f8fafc', // slate-50
        nodeBorder: '#cbd5e1', // slate-300
        clusterBkg: '#f1f5f9', // slate-100
        clusterBorder: '#cbd5e1', // slate-300
        titleColor: '#1e293b', // slate-800
        edgeLabelBackground: '#ffffff',
    }
});

// Markdown Configuration
const md = new MarkdownIt({
    html: true,
    breaks: true, // Enable line breaks
    linkify: true,
    typographer: true,
    highlight: function (str: string, lang: string) {
        if (lang && hljs.getLanguage(lang)) {
            try {
                return hljs.highlight(str, { language: lang }).value;
            } catch (__) {}
        }
        return ''; // use external default escaping
    }
});

// Security: Open links in new tab
md.use(linkAttributes, {
  attrs: {
    target: '_blank',
    rel: 'noopener'
  }
});

// Use standard katex plugin
md.use(markdownItKatex, {
    throwOnError: false,
    errorColor: '#cc0000'
});

// Custom renderer for mermaid code blocks
// @ts-ignore
const defaultFence = md.renderer.rules.fence || function(tokens: any, idx: number, options: any, _env: any, self: any) {
  return self.renderToken(tokens, idx, options);
};

md.renderer.rules.fence = function(tokens: any, idx: number, options: any) {
  const token = tokens[idx];
  const info = token.info ? token.info.trim() : '';
  
  if (info === 'mermaid') {
    let code = token.content.trim();
    
    // Auto-fix 1: Ensure valid diagram type header
    // If code doesn't start with a known type, default to graph TD
    const knownTypes = [
        'graph', 'flowchart', 'sequenceDiagram', 'classDiagram', 
        'stateDiagram', 'erDiagram', 'gantt', 'pie', 'mindmap', 
        'timeline', 'gitGraph', 'journey', 'sankey-beta', 'quadrantChart'
    ];
    
    // Simple heuristic: if it doesn't start with a known type, assume it's a graph
    const firstWord = code.split(/[\s\n]/)[0];
    if (!knownTypes.includes(firstWord) && !code.trim().startsWith('%%')) {
        if (code.includes('-->') || code.includes('---')) {
            code = 'graph TD\n' + code;
        }
    }

    // Auto-fix 2: Removed aggressive text quoting as it was causing syntax errors with modern Mermaid versions
    // Mermaid 10+ handles special characters much better

    // Encode the code to prevent HTML tag parsing issues (e.g. A["<Label>"])
    const encodedCode = md.utils.escapeHtml(code);
    
    return `<div class="mermaid">${encodedCode}</div>`;
  }
  
  const langName = info.split(/\s+/g)[0];
  let highlighted = '';
  if (options.highlight) {
    highlighted = options.highlight(token.content, langName, '') || '';
  }
  const code = highlighted || md.utils.escapeHtml(token.content);
  const rawCode = encodeURIComponent(token.content);

  return `<div class="relative group code-block-wrapper my-2 rounded-lg overflow-hidden border border-slate-200/50 shadow-sm bg-[#282c34]">
            <div class="absolute top-2 right-2 flex items-center gap-2 z-10">
                <span class="text-xs text-slate-400 font-mono opacity-0 group-hover:opacity-100 transition-opacity select-none">${langName}</span>
                <button class="p-1.5 rounded-md bg-slate-700/50 hover:bg-slate-700 text-white/70 hover:text-white backdrop-blur-md opacity-0 group-hover:opacity-100 transition-all copy-btn" title="复制代码" data-code="${rawCode}">复制</button>
            </div>
            <pre class="hljs p-4 rounded-lg text-sm overflow-x-auto"><code>${code}</code></pre>
          </div>`;
};

// Add image lazy loading support
md.renderer.rules.image = function (tokens, idx, options, _env, self) {
  const token = tokens[idx];
  if (token) {
    token.attrSet('loading', 'lazy');
    token.attrSet('class', 'rounded-xl shadow-sm border border-slate-100 my-4 max-w-full h-auto');
  }
  return self.renderToken(tokens, idx, options);
};

// Memoization cache
const markdownCache = new Map<string, string>()

export const renderMarkdown = (content: string) => {
    if (!content) return '';
    
    // Check cache
    if (markdownCache.has(content)) {
        return markdownCache.get(content) || ''
    }

    // --- Pre-processing for Robustness ---
    let normalized = content;

    // 1. Fix unclosed block math $$ ...
    const blockMathCount = (normalized.match(/\$\$/g) || []).length;
    if (blockMathCount % 2 !== 0) {
        normalized += '\n$$';
    }

    // 2. Fix unclosed code blocks ``` ...
    const fenceCount = (normalized.match(/^```/gm) || []).length;
    if (fenceCount % 2 !== 0) {
        normalized += '\n```';
    }

    // 3. Fix bare LaTeX environments (wrap in $$ if not already)
    // Matches \begin{matrix}... \end{matrix} that are NOT surrounded by $$
    // We use a simplified check: if we see \begin{...} and it's not preceded by $$, wrap it.
    // This is heuristic and might be risky, but addresses the specific issue.
    // Better approach: Let's assume block environments starting at newline.
    normalized = normalized.replace(/(^|\n)\\begin\{([a-z*]+)\}([\s\S]*?)\\end\{\2\}/gm, (match) => {
        return `\n$$\n${match.trim()}\n$$\n`;
    });

    // Fix: Auto-add space after headers (e.g., "###Title" -> "### Title")
    normalized = normalized.replace(/^(#{1,6})(?=[^#\s])/gm, '$1 ');

    // Normalize LaTeX delimiters for compatibility
    // Replace \[ ... \] with $$ ... $$
    normalized = normalized.replace(/\\\[([\s\S]*?)\\\]/g, '$$$$$1$$$$');
    // Replace \( ... \) with $ ... $ 
    normalized = normalized.replace(/\\\(([\s\S]*?)\\\)/g, '$$$1$$');
    
    // Fix: Ensure display math $$...$$ has proper spacing for rendering
    normalized = normalized.replace(/\$\$([\s\S]*?)\$\$/g, (_match, content) => {
        return `\n$$\n${content.trim()}\n$$\n`;
    });
    
    // Fix spaces in inline math $ ... $ -> $...$
    normalized = normalized.replace(/(\$\$[\s\S]*?\$\$)|(\$([^\$\n]+?)\$)/g, (match, block, inline, content) => {
        if (block) return block
        if (inline) {
            const trimmed = content.trim()
            return `$${trimmed}$`
        }
        return match
    })

    // Fix non-standard prime notation
    normalized = normalized.replace(/(\w+)'\s+\((.+?)\)/g, "$1'($2)")
    normalized = normalized.replace(/(\w+)\s+'/g, "$1'")
    // Fix trailing dollar sign issue
    normalized = normalized.replace(/(\$\$[\s\S]*?)[^$]\$$/gm, "$1$$")

    // Fix: Auto-wrap equations that are missing delimiters (common LLM issue)
    // Heuristic: If a line contains a math command (vec, frac, int, sum, lim, etc.) AND an equals sign or typical math operators,
    // and is not already wrapped in $, wrap the math part in $$
    // Example: "Label: \vec{v} = ..." -> "Label: $$\vec{v} = ...$$"
    normalized = normalized.replace(/(^|\n)([^\n$]*?)(\\vec|\\frac|\\int|\\sum|\\lim|\\mathbb|\\mathcal|\\in|\\times|\\cdot|\\leq|\\geq|\\neq|\\approx|\\equiv|\\forall|\\exists|\\partial|\\nabla|\\alpha|\\beta|\\gamma|\\sigma|\\lambda|\\mu|\\pi)([^$\n]*[=><\u2248\u2260\u2264\u2265\u2208][^$\n]*)(\n|$)/g, (match, prefix, label, cmd, rest, suffix) => {
        // If the label contains $ or the rest contains $, abort (already wrapped)
        if (label.includes('$') || rest.includes('$')) return match;
        
        // Don't wrap if it looks like code (e.g. inside `...`) - simple check
        if (label.includes('`') || rest.includes('`')) return match;

        return `${prefix}${label}$$${cmd}${rest}$$${suffix}`;
    });

    // Heuristic 2: Wrap standalone math lines that start with typical LaTeX commands but miss delimiters
    // e.g. "A \in \mathbb{R}^{m \times n}"
    normalized = normalized.replace(/(^|\n)([^\n$]*?)(\\mathbb|\\mathcal|\\in|\\times)([^$\n]*)(\n|$)/g, (match, prefix, label, cmd, rest, suffix) => {
         if (label.includes('$') || rest.includes('$')) return match;
         if (label.includes('`') || rest.includes('`')) return match;
         // Avoid wrapping if it's just text explaining "the symbol \in means..."
         // But if it looks like a formula (contains super/subscripts or operators), wrap it.
         if (rest.match(/[\^_{}=]/) || label.match(/[A-Za-z0-9]\s*$/)) {
             return `${prefix}${label}$$${cmd}${rest}$$${suffix}`;
         }
         return match;
    });

    let sanitized = ''
    try {
        const rawHtml = md.render(normalized);
        sanitized = DOMPurify.sanitize(rawHtml, {
            ADD_TAGS: ['iframe', 'span', 'div', 'p', 'button', 'math', 'semantics', 'mrow', 'mi', 'mo', 'mn', 'msup', 'msub', 'mfrac', 'msqrt', 'mtable', 'mtr', 'mtd', 'table', 'thead', 'tbody', 'tr', 'th', 'td'],
            ADD_ATTR: ['allow', 'allowfullscreen', 'frameborder', 'scrolling', 'target', 'class', 'style', 'xmlns', 'display', 'mathvariant', 'loading', 'data-code', 'title']
        });
    } catch (e) {
        sanitized = DOMPurify.sanitize(normalized)
    }

    // Cache result (limit cache size)
    if (markdownCache.size > 500) {
        const firstKey = markdownCache.keys().next().value
        if (firstKey) markdownCache.delete(firstKey)
    }
    markdownCache.set(content, sanitized)
    
    return sanitized;
};
