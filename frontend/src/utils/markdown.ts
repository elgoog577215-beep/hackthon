import MarkdownIt from 'markdown-it';
// import markdownItKatex from 'markdown-it-katex'; // Replaced by custom implementation
import katex from 'katex';
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
        primaryTextColor: '#0f172a', // slate-900 (Black text for better visibility)
        primaryBorderColor: '#7c3aed', // primary-600
        lineColor: '#334155', // slate-700
        secondaryColor: '#ede9fe', // primary-100
        tertiaryColor: '#ffffff',
        mainBkg: '#f8fafc', // slate-50
        nodeBorder: '#cbd5e1', // slate-300
        clusterBkg: '#f1f5f9', // slate-100
        clusterBorder: '#cbd5e1', // slate-300
        titleColor: '#0f172a', // slate-900
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

// Custom Math Plugin for KaTeX
const mathPlugin = (md: any) => {
    // Inline math rule ($...$ and $$...$$)
    md.inline.ruler.after('escape', 'math_inline', (state: any, silent: boolean) => {
        const start = state.pos;
        if (state.src[start] !== '$') return false;

        let isDisplay = false;
        let marker = '$';
        
        if (start + 1 < state.posMax && state.src[start + 1] === '$') {
            isDisplay = true;
            marker = '$$';
        }

        const markerLen = marker.length;
        let pos = start + markerLen;
        let found = false;

        while (pos < state.posMax) {
            if (state.src.startsWith(marker, pos)) {
                // Check for escaped $ (not perfect but good enough)
                if (pos > 0 && state.src[pos - 1] === '\\') {
                    pos++;
                    continue;
                }
                found = true;
                break;
            }
            pos++;
        }

        if (!found) {
            if (!silent) state.pending += marker;
            state.pos += markerLen;
            return true;
        }

        if (silent) return true;

        const content = state.src.slice(start + markerLen, pos);
        
        // Heuristic: If content contains newlines, it might be a broken block.
        // But markdown-it inline usually doesn't span newlines unless breaks enabled.
        // My robust preprocessing ensures blocks are clean.
        
        const token = state.push(isDisplay ? 'math_display' : 'math_inline', 'math', 0);
        token.content = content.trim();
        token.markup = marker;

        state.pos = pos + markerLen;
        return true;
    });

    // Block math rule for top-level $$...$$
    // (Optional if inline rule catches it, but better for structure)
    md.block.ruler.after('blockquote', 'math_block', (state: any, start: number, end: number, silent: boolean) => {
        const firstLine = state.src.slice(state.bMarks[start] + state.tShift[start], state.eMarks[start]);
        if (!firstLine.trim().startsWith('$$')) return false;

        // Search for end
        let next = start;
        let found = false;
        
        // If single line $$...$$
        if (firstLine.trim().length > 2 && firstLine.trim().endsWith('$$')) {
            found = true;
        } else {
            // Multiline
            next++;
            while (next < end) {
                const line = state.src.slice(state.bMarks[next] + state.tShift[next], state.eMarks[next]);
                if (line.trim().endsWith('$$')) {
                    found = true;
                    break;
                }
                next++;
            }
        }

        if (!found) return false;
        if (silent) return true;

        const token = state.push('math_display_block', 'math', 0);
        // Extract content
        const lines = state.getLines(start, next + 1, state.tShift[start], false);
        let content = lines.trim();
        if (content.startsWith('$$')) content = content.slice(2);
        if (content.endsWith('$$')) content = content.slice(0, -2);
        
        token.content = content.trim();
        token.map = [start, next + 1];
        token.markup = '$$';

        state.line = next + 1;
        return true;
    }, { alt: ['paragraph', 'reference', 'blockquote', 'list'] });

    // Renderers
    const renderMath = (content: string, displayMode: boolean) => {
        try {
            return katex.renderToString(content, { 
                throwOnError: true, // Throw error to catch it
                displayMode,
                output: 'html' // Render to HTML
            });
        } catch (e) {
            // Fallback to text if rendering fails
            // This prevents red error blocks for invalid LaTeX (like incomplete formulas from LLM)
            return `<span class="math-error">${content}</span>`;
        }
    };

    md.renderer.rules.math_inline = (tokens: any, idx: number) => {
        return renderMath(tokens[idx].content, false);
    };
    
    md.renderer.rules.math_display = (tokens: any, idx: number) => {
        return renderMath(tokens[idx].content, true);
    };

    md.renderer.rules.math_display_block = (tokens: any, idx: number) => {
        return '<div class="katex-display">' + renderMath(tokens[idx].content, true) + '</div>';
    };
};

// Use custom math plugin
md.use(mathPlugin);

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
    
    // We wrap it in a div.mermaid. 
    // IMPORTANT: The content inside must NOT be HTML encoded again by the browser when we insert it.
    // However, markdown-it's renderer expects a string that will be put into HTML.
    // So escapeHtml is correct. 
    // But for mermaid, we want the raw code in the textContent of the div initially?
    // Actually, mermaid.run looks at textContent. 
    // If we put encoded HTML entities in the div, textContent will decode them back to raw chars.
    // So `<` becomes `&lt;` in HTML, but `textContext` reads `<`. This is correct.
    
    // Encode raw code for data attribute to ensure we have the exact original source
    const rawCode = encodeURIComponent(code);
    return `<div class="mermaid" data-code="${rawCode}">${encodedCode}</div>`;
  }
  
  const langName = info.split(/\s+/g)[0];
  let highlighted = '';
  if (options.highlight) {
    highlighted = options.highlight(token.content, langName, '') || '';
  }
  const code = highlighted || md.utils.escapeHtml(token.content);
  const rawCode = encodeURIComponent(token.content);

  return `<div class="relative group code-block-wrapper my-2 rounded-lg overflow-hidden border border-slate-200/50 shadow-sm bg-[#282c34]" data-lang="${langName}">
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

// Memoization cache with simple LRU strategy
const MAX_CACHE_SIZE = 500;
const markdownCache = new Map<string, string>()

// --- Math Detection Helpers ---

// Helper to find the matching closing bracket/paren/brace for \left
const findMatchingRight = (text: string, startIdx: number): number => {
    let depth = 0;
    // Regex to find \left or \right commands
    // We strictly look for \left followed by delimiter or \right followed by delimiter.
    // Delimiters can be anything non-alphanumeric (roughly).
    const re = /(\\left\s*[^a-zA-Z0-9\s]|\\right\s*[^a-zA-Z0-9\s])/g;
    re.lastIndex = startIdx;
    
    let match: RegExpExecArray | null;
    while ((match = re.exec(text)) !== null) {
        if (match[0] && match[0].startsWith('\\left')) {
            depth++;
        } else if (match[0] && match[0].startsWith('\\right')) {
            depth--;
        }
        
        if (depth === 0) {
            // Found the matching right. Return index AFTER this match.
            return re.lastIndex;
        }
    }
    return -1; // Unbalanced
};

// Helper to find matching \end{env} for \begin{env}
const findBalancedEnvironment = (text: string, startIdx: number, envName: string): number => {
    let depth = 0;
    const re = new RegExp(`(\\\\begin\\{${envName}\\})|(\\\\end\\{${envName}\\})`, 'g');
    re.lastIndex = startIdx;
    
    let match: RegExpExecArray | null;
    while ((match = re.exec(text)) !== null) {
        if (match[1]) { // begin
            depth++;
        } else if (match[2]) { // end
            depth--;
        }
        
        if (depth === 0) {
            return re.lastIndex;
        }
    }
    return -1;
};

// Helper to expand math block backwards to include prefixes like "U = " or "\text{span}"
const expandPrefix = (text: string, startPos: number): number => {
    let currentPos = startPos;
    
    // Check for "U = " or "var =" or "dim(U) ="
    const suffix = text.substring(0, currentPos);
    
    // Regex looks for: (Word or Function) = 
    // Relaxed to allow spaces between tokens to handle cases like "\text{span} (S) ="
    // We match a sequence of allowed characters, optionally separated by spaces, ending with =
    // Allowed chars: letters, numbers, _, {, }, (, ), ^, |, \, [, ], space
    
    // Heuristic: We capture everything from the last newline or clear text break up to the equals sign.
    // But we need to be careful not to capture plain text like "The value of x ="
    // Let's try to match a pattern that looks like math/variable/function.
    
    // Pattern: 
    // 1. Ends with "=" (and optional spaces)
    // 2. Preceded by "allowed chars" (including \text{...})
    
    const eqMatch = suffix.match(/((?:[a-zA-Z0-9_{}()\^\|\\[\]]+|\\text\{[^}]+\})(?:\s+(?:[a-zA-Z0-9_{}()\^\|\\[\]]+|\\text\{[^}]+\}))*\s*=\s*)$/);
     
     if (eqMatch && eqMatch[1]) {
          // Check if it's a real variable and not just "Then ="
          const matchStr = eqMatch[1];
          if (!matchStr) return currentPos; // Safety check
          
          const parts = matchStr.split('=');
          const varPart = parts[0] ? parts[0].trim() : '';
          // Simple stop list for common text words ending with = (rare but possible)
          const stopWords = ['Then', 'If', 'So', 'Hence', 'Therefore', 'Where', 'Thus', 'Here'];
          // If the captured part consists ONLY of a stop word, ignore it.
          // But "If x =" should be captured as "x =".
          // The regex is greedy, so it might capture "If x =".
          // We should refine the regex to NOT capture starting stop words?
          // Or just check the first word.
          
          const firstWord = varPart.split(/\s+/)[0];
          if (firstWord && stopWords.includes(firstWord) && varPart.split(/\s+/).length === 1) {
              // Only a stop word, e.g. "Then =" (unlikely but possible)
              return currentPos;
          }
         
         // If it starts with a stop word, we might want to trim it?
          // E.g. "Then x =" -> "x ="
          // But the regex anchors to the end ($).
          // It might be safer to just take the match.
          // The regex ensures it's composed of "math-like" chars.
          // "Then" contains only letters. It matches.
          // But we probably want to include "Then" in the math block? "Then $x=...$"
          // No, usually "Then" is text.
          
          // Let's rely on the user's intent. If they wrote "Then x = \left...", they probably want "Then $x = \left...$"
          // So wrapping "x =" is good. Wrapping "Then x =" is weird ($Then x = ...$).
          
          // Refined Strategy:
          // Look for the last "="
          // Capture backwards until we hit something that IS NOT math-like.
          // Spaces are allowed between math tokens.
          
          return currentPos - matchStr.length;
     }
    
    return currentPos;
};

// Main function to detect and wrap complex math
const detectAndWrapComplexMath = (content: string, maskIdRef: {val: number}, maskMap: Map<string, string>): string => {
    // Regex to find POTENTIAL starts:
    // 1. \text{...}\left... (Group 1)
    // 2. \left... (Group 2)
    // 3. \begin{...} (Group 3, env name in Group 4)
    // UPDATED: Allow \left followed by ANY character that looks like a delimiter (including \ for \{, \|)
    // We match \left followed by optional space, then either a backslash (for \{, \|, etc.) or a non-word char (for (, [, |)
    const startRegex = /(\\text\{[^}]+\}\s*\\left)|(\\left)|(\\begin\{([a-zA-Z0-9*]+)\})/g;
    
    let result = '';
    let lastIndex = 0;
    let match: RegExpExecArray | null;
    
    while ((match = startRegex.exec(content)) !== null) {
        if (match.index < lastIndex) continue; 
        
        const startPos = match.index;
        const matchedStr = match[0];
        let endPos = -1;
        
        if (matchedStr.includes('\\begin')) {
             const envName = match[4];
             if (envName) {
                 endPos = findBalancedEnvironment(content, startPos, envName);
             }
        } else {
             // \left case
             // We need to verify if it's a valid \left... start
             // findMatchingRight will check this.
             // match[0] is just "\left" (or with prefix).
             
             // If we matched via group 1 (\text... \left), startPos is at \text.
             // We need to find where \left is.
             let absLeftIdx = startPos;
             if (matchedStr.startsWith('\\text')) {
                 const leftIdx = matchedStr.indexOf('\\left');
                 absLeftIdx = startPos + leftIdx;
             }
             
             endPos = findMatchingRight(content, absLeftIdx);
        }
        
        if (endPos !== -1) {
            // Check for prefix (e.g. "U = ")
            const prefixStart = expandPrefix(content, startPos);
            
            // Extract block
            const fullBlock = content.substring(prefixStart, endPos);
            
            // Mask it
            const id = `__MATH_BLOCK_COMPLEX_${maskIdRef.val++}__`;
            // Heuristic: if it contains newlines or \begin, make it display math
            const isDisplay = fullBlock.includes('\n') || fullBlock.includes('\\\\') || fullBlock.includes('\\begin');
            const wrapped = isDisplay ? `\n$$\n${fullBlock}\n$$\n` : `$${fullBlock}$`;
            
            maskMap.set(id, wrapped);
            
            result += content.substring(lastIndex, prefixStart) + id;
            lastIndex = endPos;
            startRegex.lastIndex = endPos;
        }
    }
    
    result += content.substring(lastIndex);
    return result;
};

// Universal Line-Based Math Detector
// Scans for lines that look like math equations but lack delimiters.
const detectAndWrapNakedMathLines = (content: string, maskIdRef: {val: number}, maskMap: Map<string, string>): string => {
    return content.split('\n').map(line => {
        // Skip masked lines or empty lines
        if (line.trim().startsWith('__MATH') || line.trim().startsWith('__CODE') || !line.trim()) return line;
        
        // Skip lines that look like headers, lists, or blockquotes
        if (line.match(/^(\s*)(#{1,6}|-|\*|\d+\.|>)\s/)) {
            // But sometimes a list item IS a formula: "1. x = y"
            // We should strip the marker and check the rest.
            // Let's implement a "content only" check.
            const contentMatch = line.match(/^(\s*(?:#{1,6}|-|\*|\d+\.|>)\s+)(.*)$/);
            if (contentMatch) {
                const marker = contentMatch[1];
                const rest = contentMatch[2];
                if (marker && rest && isLikelyMath(rest)) {
                     const id = `__MATH_INLINE_AUTO_${maskIdRef.val++}__`;
                     maskMap.set(id, `$${rest}$`);
                     return marker + id;
                }
            }
            return line;
        }

        if (isLikelyMath(line)) {
            const id = `__MATH_BLOCK_AUTO_${maskIdRef.val++}__`;
            // If it's a full line, treat as block math
            maskMap.set(id, `\n$$\n${line.trim()}\n$$\n`);
            return id;
        }
        
        return line;
    }).join('\n');
};

// Heuristic to check if a string is likely a math formula
const isLikelyMath = (text: string): boolean => {
    const trimmed = text.trim();
    if (!trimmed) return false;
    
    // Must contain at least one "strong" math signal or multiple "weak" ones
    // Strong: \, =, ^, _, { }
    // Weak: +, -, *, /, (, ), numbers
    
    // Filter out common text patterns
    // If it contains too many english words, it's prose.
    // Word definition: sequence of a-z chars > 2 length.
    const words = trimmed.match(/[a-zA-Z]{3,}/g) || [];
    // Filter out math commands from words (e.g. "frac", "text", "left")
    const mathCmds = ['frac', 'text', 'left', 'right', 'begin', 'end', 'sqrt', 'sum', 'int', 'prod', 'lim', 'vec', 'hat', 'bar', 'tilde', 'alpha', 'beta', 'gamma', 'delta', 'theta', 'lambda', 'sigma', 'omega', 'phi', 'psi', 'rho', 'mu', 'nu', 'tau', 'epsilon', 'eta', 'zeta', 'xi', 'chi', 'pi', 'span', 'rank', 'dim', 'ker', 'im', 'det', 'tr', 'log', 'ln', 'sin', 'cos', 'tan', 'cot', 'sec', 'csc', 'arcsin', 'arccos', 'arctan'];
    const nonMathWords = words.filter(w => !mathCmds.includes(w.toLowerCase()));
    
    // If text is mostly words, it's prose.
    if (nonMathWords.length > trimmed.length / 10 && nonMathWords.length > 3) return false;
    
    // Indicators
    const hasBackslash = /\\/.test(trimmed);
    const hasEquals = /=/.test(trimmed);
    const hasStructure = /[\^_{}\[\]]/.test(trimmed);
    const hasOps = /[+\-*\/]/.test(trimmed);
    
    // Decision Tree
    if (hasBackslash && (hasEquals || hasStructure || hasOps)) return true;
    if (hasEquals && hasStructure) return true;
    if (hasEquals && hasOps && trimmed.length < 50) return true; // Simple equation "y = x + 1"
    
    // Special case: "Variable = Expression" (even without backslash)
    // e.g. "E = mc^2"
    if (hasEquals && trimmed.split('=').length === 2) {
        // Check LHS and RHS
        // If LHS is short and RHS looks mathy
        const parts = trimmed.split('=');
        const lhs = parts[0];
        const rhs = parts[1];
        if (lhs && rhs && lhs.trim().length < 10 && (rhs.match(/[0-9\^_{}]/) || rhs.match(/[+\-*\/]/))) {
            return true;
        }
    }

    return false;
};

export const renderMarkdown = (content: string) => {
    if (!content) return '';
    
    // Check cache
    if (markdownCache.has(content)) {
        return markdownCache.get(content) || ''
    }

    // Fast path: If content looks simple (no code, no math delimiters, no obvious math symbols), 
    // skip the heavy robust preprocessing.
    // We check for:
    // 1. Code blocks (``` or `)
    // 2. Math delimiters ($ or \)
    // 3. Math operators often used in naked equations (=, ^, {)
    // If none of these exist, it's likely plain text.
    if (!content.includes('`') && 
        !content.includes('$') && 
        !content.includes('\\') && 
        !content.includes('=') && 
        !content.includes('{') &&
        !content.includes('^')) {
        
        const html = md.render(content);
        const result = DOMPurify.sanitize(html, {
            ADD_TAGS: ['math-field', 'iframe'], 
            ADD_ATTR: ['target', 'allow', 'allowfullscreen', 'frameborder', 'scrolling']
        });
        
        // Cache management
        if (markdownCache.size > MAX_CACHE_SIZE) {
            const firstKey = markdownCache.keys().next().value;
            if (firstKey) markdownCache.delete(firstKey);
        }
        markdownCache.set(content, result);
        return result;
    }

    // --- Pre-processing for Robustness ---
    let normalized = content;

    // Protection: Mask code blocks to prevent math heuristics from messing up code
    // We replace code blocks with placeholders, then restore them at the end.
    const codeBlockMap = new Map<string, string>();
    let codeBlockId = 0;
    
    // Mask fenced code blocks (```...```)
    normalized = normalized.replace(/^```[\s\S]*?^```/gm, (match) => {
        const id = `__CODE_BLOCK_${codeBlockId++}__`;
        codeBlockMap.set(id, match);
        return id;
    });

    // Mask inline code (`...`)
    // Note: This regex is simple and might not handle escaped backticks perfectly, but good enough for protection
    normalized = normalized.replace(/`[^`\n]+`/g, (match) => {
        const id = `__INLINE_CODE_${codeBlockId++}__`;
        codeBlockMap.set(id, match);
        return id;
    });

    // Protection: Mask Existing Math to prevent double wrapping or corrupting valid math
    // We mask $$...$$, \[...\], \(...\), and $...$
    const mathMaskMap = new Map<string, string>();
    let mathMaskId = 0;

    // Mask $$...$$ (Block)
    normalized = normalized.replace(/\$\$([\s\S]*?)\$\$/g, (match) => {
        const id = `__MATH_BLOCK_${mathMaskId++}__`;
        mathMaskMap.set(id, match);
        return id;
    });

    // Mask \[...\] (LaTeX Block)
    normalized = normalized.replace(/\\\[([\s\S]*?)\\\]/g, (match) => {
        const id = `__LATEX_BLOCK_${mathMaskId++}__`;
        mathMaskMap.set(id, match);
        return id;
    });

    // Mask \(...\) (LaTeX Inline)
    normalized = normalized.replace(/\\\(([\s\S]*?)\\\)/g, (match) => {
        const id = `__LATEX_INLINE_${mathMaskId++}__`;
        mathMaskMap.set(id, match);
        return id;
    });

    // Mask $...$ (Inline - careful with currency)
    // We reuse the currency protection logic here to only mask VALID math
    normalized = normalized.replace(/\$([^\$\n]+?)\$/g, (match, content) => {
        // Currency check
        if (content.match(/\s(and|or|with|for)\s/)) return match;
        // If it looks like a price (e.g. $100.00), skip
        if (content.match(/^\s*\d+(\.\d+)?\s*$/)) return match;
        
        const id = `__MATH_INLINE_${mathMaskId++}__`;
        mathMaskMap.set(id, match);
        return id;
    });

    // 3. Smart Detection of Complex Math (Universal Fix)
    // Replaces rigid command lists with a robust structural detector.
    // Detects any \command or structure that looks like math and wraps it.
    // This runs BEFORE the simpler heuristics but AFTER masking existing math.
    const maskIdRef = { val: mathMaskId };
    normalized = detectAndWrapComplexMath(normalized, maskIdRef, mathMaskMap);
    mathMaskId = maskIdRef.val;
    
    // 4. Universal Line-Based Math Detector (New "Intelligence")
    // Scans lines for high density of math tokens.
    // If a line is predominantly math-like but missed by specific triggers, wrap it.
    // This catches "broken" LLM output like: "x^2 + y^2 = z^2" (no delimiters)
    normalized = detectAndWrapNakedMathLines(normalized, maskIdRef, mathMaskMap);
    mathMaskId = maskIdRef.val;

    // 1. Fix unclosed block math $$ ... (Only for unmasked new additions if any, but mostly irrelevant now)
    const blockMathCount = (normalized.match(/\$\$/g) || []).length;
    if (blockMathCount % 2 !== 0) {
        normalized += '\n$$';
    }

    // 2. Fix unclosed code blocks ``` ... (Only if not masked? But we masked valid ones)
    // If we masked them, this check might be irrelevant for valid blocks, 
    // but if the user has an open block at the very end that wasn't matched by the regex (because no closing fence),
    // we might need to handle it.
    // However, since we mask *valid* blocks, any remaining ``` are unclosed.
    const fenceCount = (normalized.match(/^```/gm) || []).length;
    if (fenceCount % 2 !== 0) {
        normalized += '\n```';
    }

    // 3. Robust Fix for Block Math Environments
    // Detects \begin{...} blocks that are naked or wrapped in single $ (broken if multiline)
    // and wraps them in $$ ... $$ for proper display.
    // Excludes blocks that are already part of a $$ ... $$ sequence (via regex logic).
    const blockEnvs = "bmatrix|pmatrix|vmatrix|Bmatrix|Vmatrix|matrix|aligned|split|cases|equation|gather";
    // Modified regex to allow arbitrary prefix (like "A = ") before \begin, as long as it's not inside existing $$
    const blockRe = new RegExp(`(^|[^\\$])([\\s\\S]*?)(\\\\begin\\{(${blockEnvs})\\}[\\s\\S]*?\\\\end\\{\\4\\})`, 'gm');
    normalized = normalized.replace(blockRe, (match, prefixChar, preText, envContent) => {
        // If the match contains $$, it might be already wrapped. 
        // But our regex start (^|[^$]) tries to avoid starting inside $$.
        // However, [^$] only checks the char immediately before. 
        // preText might contain $$.
        if (preText.includes('$$') || envContent.includes('$$')) return match;
        
        // If it's already inside $...$ (inline), we shouldn't touch it?
        // But block environments inside inline math are usually bad style or broken.
        // We assume block environments should be display math.
        
        return `${prefixChar}${preText}\n$$\n${envContent}\n$$\n`;
    });

    // Fix: Auto-add space after headers (e.g., "###Title" -> "### Title")
    normalized = normalized.replace(/^(#{1,6})(?=[^#\s])/gm, '$1 ');

    // --- Unmask Math ---
    // Now that heuristics have run on "naked" content, we restore the original math blocks.
    mathMaskMap.forEach((value, key) => {
         normalized = normalized.replace(key, value);
    });

    // Normalize LaTeX delimiters for compatibility
    // Replace \[ ... \] with $$ ... $$
    normalized = normalized.replace(/\\\[([\s\S]*?)\\\]/g, '\n$$\n$1\n$$\n');
    // Replace \( ... \) with $ ... $ (Inline math)
    normalized = normalized.replace(/\\\(([\s\S]*?)\\\)/g, '$$$1$$');
    
    // Fix: Ensure display math $$...$$ has proper spacing for rendering
    normalized = normalized.replace(/\$\$([\s\S]*?)\$\$/g, (_match, content) => {
        return `\n$$\n${content.trim()}\n$$\n`;
    });
    
    // Fix spaces in inline math $ ... $ -> $...$ (ONLY if it looks like math, not currency)
    // We run this again because we unmasked original math which might need spacing fixes
    normalized = normalized.replace(/(\$\$[\s\S]*?\$\$)|(\$([^\$\n]+?)\$)/g, (match, block, inline, content) => {
        if (block) return block
        if (inline) {
            // Currency check (redundant if we masked correctly, but good for safety)
            if (content.match(/\s(and|or|with|for)\s/)) return match;
            if (content.match(/^\s*\d+(\.\d+)?\s*$/)) return match;
            
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
    // Added boundary check (?![a-zA-Z]) to prevent partial matches (e.g. \in matching \infty)
    const mathCmds = [
        'vec', 'frac', 'int', 'sum', 'lim', 'mathbb', 'mathcal', 'in', 'times', 'cdot', 
        'leq', 'geq', 'neq', 'approx', 'equiv', 'forall', 'exists', 'partial', 'nabla', 
        'alpha', 'beta', 'gamma', 'sigma', 'lambda', 'mu', 'pi', 'infty', 'ell', 'mid', 
        'langle', 'rangle', 'lVert', 'rVert', 'left', 'right'
    ].join('|');
    
    const mathCmdRegex = new RegExp(`(^|\\n)([^\\n$]*?)(\\\\(${mathCmds}))(?![a-zA-Z])([^$\\n]*[=><\\u2248\\u2260\\u2264\\u2265\\u2208][^$\\n]*)(\\n|$)`, 'g');

    normalized = normalized.replace(mathCmdRegex, (match, prefix, label, cmdFull, _cmdName, rest, suffix) => {
        // If the label contains $ or the rest contains $, abort (already wrapped)
        if (label.includes('$') || rest.includes('$')) return match;
        
        // Don't wrap if it looks like code (e.g. inside `...`) - simple check
        if (label.includes('`') || rest.includes('`')) return match;

        // Try to capture preceding math content in label (e.g. "f(x) = " or "\ell^2 = ")
        // This is a simple heuristic to include "x =" or "f(x) =" into the math block
        // We look for a suffix of label that looks like math
        
        // Revised Logic:
        // 1. If label contains any LaTeX-like commands (backslashes), treat the whole label as part of the formula.
        //    (Except if it looks like typical text, but checking for \ is a strong signal).
        // 2. If label ends with typical math structure (A = , f(x) = ), capture it.
        
        let preMath = '';
        let textLabel = label;

        if (label.includes('\\') || label.match(/[=><]\s*$/)) {
             // Strong signal: Label contains LaTeX or ends with operator.
             // We should probably wrap the whole thing, or at least from the first math-char.
             // Let's try to find the split point between "Text: " and "Math".
             // We look for the last occurrence of common text punctuation (: or .) followed by space.
             const splitMatch = label.match(/^(.*[:。，,]\s*)(.*)$/);
             if (splitMatch) {
                 textLabel = splitMatch[1];
                 preMath = splitMatch[2];
             } else {
                 // No punctuation split, assume it's all math if it has backslash?
                 // Or maybe it's just "Therefore " + math.
                 // Let's use a safe heuristic: if it has backslash, wrap it all.
                 if (label.includes('\\')) {
                     preMath = label;
                     textLabel = '';
                 } else {
                     // Just text ending in = ?
                     const labelMatch = label.match(/([a-zA-Z0-9_{}\(\)\^\|\s]+(=|:)\s*)$/);
                     if (labelMatch) {
                        preMath = labelMatch[0];
                        textLabel = label.substring(0, label.length - preMath.length);
                     }
                 }
             }
        } else {
             // Standard short label check
             if (label.trim().length < 10 && !label.match(/[.,;!?]$/)) {
                 preMath = label;
                 textLabel = '';
             }
        }

        return `${prefix}${textLabel}$$${preMath}${cmdFull}${rest}$$${suffix}`;
    });

    // Heuristic 2: Wrap standalone math lines that start with typical LaTeX commands but miss delimiters
    // e.g. "A \in \mathbb{R}^{m \times n}"
    const standaloneCmds = ['mathbb', 'mathcal', 'in', 'times', 'ell', 'infty', 'sum', 'int'].join('|');
    const standaloneRegex = new RegExp(`(^|\\n)([^\\n$]*?)(\\\\(${standaloneCmds}))(?![a-zA-Z])([^$\\n]*)(\\n|$)`, 'g');
    
    normalized = normalized.replace(standaloneRegex, (match, prefix, label, cmdFull, _cmdName, rest, suffix) => {
         if (label.includes('$') || rest.includes('$')) return match;
         if (label.includes('`') || rest.includes('`')) return match;
         
         if (rest.match(/[\^_{}=]/) || label.match(/[A-Za-z0-9]\s*$/)) {
             return `${prefix}${label}$$${cmdFull}${rest}$$${suffix}`;
         }
         return match;
    });

    let sanitized = ''
    try {
        // Restore code blocks before rendering? 
        // No, markdown-it needs to see the code blocks to render them as code.
        // So we must restore them now.
        codeBlockMap.forEach((value, key) => {
             normalized = normalized.replace(key, value);
        });

        const rawHtml = md.render(normalized);
        sanitized = DOMPurify.sanitize(rawHtml, {
            ADD_TAGS: ['iframe', 'span', 'div', 'p', 'button', 'math', 'semantics', 'mrow', 'mi', 'mo', 'mn', 'msup', 'msub', 'mfrac', 'msqrt', 'mtable', 'mtr', 'mtd', 'table', 'thead', 'tbody', 'tr', 'th', 'td'],
            ADD_ATTR: ['allow', 'allowfullscreen', 'frameborder', 'scrolling', 'target', 'class', 'style', 'xmlns', 'display', 'mathvariant', 'loading', 'data-code', 'title']
        });
    } catch (e) {
        sanitized = DOMPurify.sanitize(normalized)
    }

    // Cache result (limit cache size)
    if (markdownCache.size > MAX_CACHE_SIZE) {
        const firstKey = markdownCache.keys().next().value
        if (firstKey) markdownCache.delete(firstKey)
    }
    markdownCache.set(content, sanitized)
    
    return sanitized;
};
