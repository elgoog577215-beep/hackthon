import MarkdownIt from 'markdown-it';
import katex from 'katex';
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

// Ported from markdown-it-katex to use local katex instance
// License: MIT

function isValidDelim(_state: any, _pos: number) {
    var can_open = true,
        can_close = true;

    return {
        can_open: can_open,
        can_close: can_close
    };
}

function math_inline(state: any, silent: boolean) {
    var start, match, token, res, pos;

    if (state.src[state.pos] !== "$") { return false; }

    res = isValidDelim(state, state.pos);
    if (!res.can_open) {
        if (!silent) { state.pending += "$"; }
        state.pos += 1;
        return true;
    }

    start = state.pos + 1;
    match = start;
    while ( (match = state.src.indexOf("$", match)) !== -1) {
        pos = match - 1;
        while (state.src[pos] === "\\") { pos -= 1; }

        // Even number of escapes, potential closing delimiter found
        if ( ((match - pos) % 2) == 1 ) { break; }
        match += 1;
    }

    if (match === -1) {
        if (!silent) { state.pending += "$"; }
        state.pos = start;
        return true;
    }

    if (match - start === 0) {
        if (!silent) { state.pending += "$$"; }
        state.pos = start + 1;
        return true;
    }

    res = isValidDelim(state, match);
    if (!res.can_close) {
        if (!silent) { state.pending += "$"; }
        state.pos = start;
        return true;
    }

    if (!silent) {
        token         = state.push('math_inline', 'math', 0);
        token.markup  = "$";
        token.content = state.src.slice(start, match);
    }

    state.pos = match + 1;
    return true;
}

function math_block(state: any, start: number, end: number, silent: boolean){
    var firstLine, lastLine, next, lastPos, found = false, token,
        pos = state.bMarks[start] + state.tShift[start],
        max = state.eMarks[start]

    if(pos + 2 > max){ return false; }
    if(state.src.slice(pos,pos+2)!=='$$'){ return false; }

    pos += 2;
    firstLine = state.src.slice(pos,max);

    if(silent){ return true; }
    if(firstLine.trim().slice(-2)==='$$'){
        // Single line expression
        firstLine = firstLine.trim().slice(0, -2);
        found = true;
    }

    for(next = start; !found; ){

        next++;

        if(next >= end){ break; }

        pos = state.bMarks[next]+state.tShift[next];
        max = state.eMarks[next];

        if(pos < max && state.tShift[next] < state.blkIndent){
            // non-empty line with negative indent should stop the list:
            break;
        }

        if(state.src.slice(pos,max).trim().slice(-2)==='$$'){
            lastPos = state.src.slice(0,max).lastIndexOf('$$');
            lastLine = state.src.slice(pos,lastPos);
            found = true;
        }

    }

    state.line = next + 1;

    token = state.push('math_block', 'math', 0);
    token.block = true;
    token.content = (firstLine && firstLine.trim() ? firstLine + '\n' : '')
    + state.getLines(start + 1, next, state.tShift[start], true)
    + (lastLine && lastLine.trim() ? lastLine : '');
    token.map = [ start, state.line ];
    token.markup = '$$';
    return true;
}

function math_plugin(md: any, options: any) {
    options = options || {};

    var katexInline = function(latex: string){
        options.displayMode = false;
        try{
            return katex.renderToString(latex, options);
        }
        catch(error){
            if(options.throwOnError){ console.log(error); }
            return latex;
        }
    };

    var inlineRenderer = function(tokens: any, idx: number){
        return katexInline(tokens[idx].content);
    };

    var katexBlock = function(latex: string){
        options.displayMode = true;
        try{
            return "<p class='katex-block'>" + katex.renderToString(latex, options) + "</p>";
        }
        catch(error){
            if(options.throwOnError){ console.log(error); }
            return latex;
        }
    }

    var blockRenderer = function(tokens: any, idx: number){
        return  katexBlock(tokens[idx].content) + '\n';
    }

    md.inline.ruler.before('escape', 'math_inline', math_inline);
    md.block.ruler.after('blockquote', 'math_block', math_block, {
        alt: [ 'paragraph', 'reference', 'blockquote', 'list' ]
    });
    md.renderer.rules.math_inline = inlineRenderer;
    md.renderer.rules.math_block = blockRenderer;
};

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

md.use(math_plugin);

// Custom renderer for mermaid code blocks
// @ts-ignore
const defaultFence = md.renderer.rules.fence || function(tokens: any, idx: number, options: any, _env: any, self: any) {
  return self.renderToken(tokens, idx, options);
};

md.renderer.rules.fence = function(tokens: any, idx: number, options: any, env: any, self: any) {
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
    
    // Auto-fix 3: Replace Common invalid characters in IDs (if needed)
    // This is harder to do safely with regex, so we skip for now unless specific errors arise.

    return `<div class="mermaid">${code}</div>`;
  }
  
  return defaultFence(tokens, idx, options, env, self);
};

export const renderMarkdown = (content: string) => {
    if (!content) return '';
    
    // Normalize LaTeX delimiters for compatibility
    // Replace \[ ... \] with $$ ... $$
    let normalized = content.replace(/\\\[([\s\S]*?)\\\]/g, '$$$$$1$$$$');
    // Replace \( ... \) with $ ... $
    normalized = normalized.replace(/\\\(([\s\S]*?)\\\)/g, '$$$1$$');
    
    // Fix: Remove redundant escaping of brackets in text if not math
    // Sometimes AI outputs \[Text\] for simple brackets. 
    // If inside $$ it's fine, but outside it might be ugly.
    // We trust markdown-it-math to handle $$ blocks.
    
    // Render markdown to HTML
    const rawHtml = md.render(normalized);
    
    // Sanitize HTML
    return DOMPurify.sanitize(rawHtml, {
        ADD_TAGS: ['iframe'], // Allow iframes if needed (e.g. video embeds), be careful
        ADD_ATTR: ['allow', 'allowfullscreen', 'frameborder', 'scrolling', 'target']
    });
};
