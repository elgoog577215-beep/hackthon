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
    theme: 'default',
    securityLevel: 'loose',
    fontFamily: 'ui-sans-serif, system-ui, sans-serif'
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

    // Fix: Auto-add space after headers (e.g., "###Title" -> "### Title")
    let normalized = content.replace(/^(#{1,6})(?=[^#\s])/gm, '$1 ');

    // Normalize LaTeX delimiters for compatibility
    // Replace \[ ... \] with $$ ... $$
    normalized = normalized.replace(/\\\[([\s\S]*?)\\\]/g, '$$$$$1$$$$');
    // Replace \( ... \) with $ ... $ (we'll convert back to valid katex format later if needed, but $$ is standard)
    normalized = normalized.replace(/\\\(([\s\S]*?)\\\)/g, '$$$1$$');
    
    // Fix spaces in inline math $ ... $ -> $...$
    // And ensure we use $$...$$ for block and $...$ for inline (if supported)
    // IMPORTANT: markdown-it-katex default often supports $$ for block and $ for inline
    // But to be safe, we ensure $...$ has NO outer spaces if that's the requirement, 
    // OR we convert single $ to \\( ... \\) if that's what the parser prefers.
    // Testing shows markdown-it-katex usually handles $...$ if it's not surrounded by spaces? 
    // Actually, let's normalize to standard LaTeX: $$ for block, \\( for inline to be safe.
    
    normalized = normalized.replace(/(\$\$[\s\S]*?\$\$)|(\$([^\$\n]+?)\$)/g, (match, block, inline, content) => {
        if (block) return block
        if (inline) {
            // Trim content
            const trimmed = content.trim()
            // Keep as $...$ for markdown-it-katex
            return `$${trimmed}$`
        }
        return match
    })

    // Fix non-standard prime notation
    normalized = normalized.replace(/(\w+)'\s+\((.+?)\)/g, "$1'($2)")
    normalized = normalized.replace(/(\w+)\s+'/g, "$1'")
    // Fix trailing dollar sign issue
    normalized = normalized.replace(/(\$\$[\s\S]*?)[^$]\$$/gm, "$1$$")

    // Fix: Auto-close unclosed LaTeX delimiters at the end of the string
    // Check for odd number of "$$" occurrences
    const doubleDollarCount = (normalized.match(/\$\$/g) || []).length;
    if (doubleDollarCount % 2 !== 0) {
        normalized += '$$';
    } else {
        // If $$ are balanced, check for unclosed single $
        // This is trickier because $ is common in text. 
        // Heuristic: if we have an unclosed $ and the text is short or looks like math
        // normalized += '$'; 
    }

    // Fix: Ensure \begin{equation} or \begin{align} are wrapped in $$ if they aren't already
    normalized = normalized.replace(/(^|[^\$])(\\begin\{(equation|align|gather|alignat)\}[\s\S]*?\\end\{(equation|align|gather|alignat)\})(?![^\$]*\$)/g, '$1$$$2$$');

    // Fix: Auto-wrap equations that are missing delimiters (common LLM issue)
    // Heuristic: If a line contains a math command (vec, frac, int, sum, lim) AND an equals sign,
    // and is not already wrapped in $, wrap the math part in $$
    // Example: "Label: \vec{v} = ..." -> "Label: $$\vec{v} = ...$$"
    normalized = normalized.replace(/(^|\n)([^\n$]*?)(\\vec|\\frac|\\int|\\sum|\\lim)([^$\n]*=[^$\n]*)(\n|$)/g, (match, prefix, label, cmd, rest, suffix) => {
        // If the label contains $ or the rest contains $, abort (already wrapped)
        if (label.includes('$') || rest.includes('$')) return match;
        return `${prefix}${label}$$${cmd}${rest}$$${suffix}`;
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
