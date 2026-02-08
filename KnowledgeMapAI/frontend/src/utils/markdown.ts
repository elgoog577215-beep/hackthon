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
        'timeline', 'gitGraph', 'journey'
    ];
    
    if (!knownTypes.some(type => code.startsWith(type))) {
        // Simple heuristic: if it looks like A -> B, it's a graph
        if (code.includes('-->') || code.includes('---')) {
            code = 'graph TD\n' + code;
        }
    }

    // Auto-fix 2: Quote node text containing parens or special chars
    const quoteIfNeeded = (text: string) => {
        if (text.startsWith('"') && text.endsWith('"')) {
            return text;
        }
        // Escape existing quotes
        const escaped = text.replace(/"/g, '\\"');
        return `"${escaped}"`;
    };

    // 2.1 Fix [Text] -> ["Text"] (Rectangular nodes)
    // Allow newlines in text
    code = code.replace(/\[(?![(\[/\\<])([^\[\]]+?)\]/g, (_match: string, p1: string) => {
        // Don't touch if it looks like a subgraph or class definition
        if (p1.trim().startsWith('id=') || p1.trim().startsWith('class:')) return _match;
        return `[${quoteIfNeeded(p1)}]`;
    });
    
    // 2.2 Fix (Text) -> ("Text") (Round nodes)
    code = code.replace(/\((?!\()([^()]+?)\)/g, (_match: string, p1: string) => {
        return `(${quoteIfNeeded(p1)})`;
    });

    // 2.3 Fix {Text} -> {"Text"} (Rhombus nodes)
    code = code.replace(/\{(?![{!])([^{}]+?)\}/g, (_match: string, p1: string) => {
        return `{${quoteIfNeeded(p1)}}`;
    });
    
    return `<div class="mermaid">${code}</div>`;
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

    // Normalize LaTeX delimiters for compatibility
    // Replace \[ ... \] with $$ ... $$
    let normalized = content.replace(/\\\[([\s\S]*?)\\\]/g, '$$$$$1$$$$');
    // Replace \( ... \) with $ ... $
    normalized = normalized.replace(/\\\(([\s\S]*?)\\\)/g, '$$$1$$');
    
    // Fix spaces in inline math $ ... $ -> $...$ to ensure markdown-it-katex parses it
    normalized = normalized.replace(/(\$\$[\s\S]*?\$\$)|(\$\s+(.+?)\s+\$)/g, (match, block, inline, content) => {
        if (block) return block
        if (inline) return `$${content}$`
        return match
    })
    // Fix non-standard prime notation
    normalized = normalized.replace(/(\w+)'\s+\((.+?)\)/g, "$1'($2)")
    normalized = normalized.replace(/(\w+)\s+'/g, "$1'")
    // Fix trailing dollar sign issue
    normalized = normalized.replace(/(\$\$[\s\S]*?)[^$]\$$/gm, "$1$$")

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
