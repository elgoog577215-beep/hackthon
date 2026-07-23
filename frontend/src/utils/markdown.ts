import MarkdownIt from 'markdown-it';
// import markdownItKatex from 'markdown-it-katex'; // Replaced by custom implementation
import katex from 'katex';
import hljs from 'highlight.js';
import DOMPurify from 'dompurify';
import linkAttributes from 'markdown-it-link-attributes';
import 'highlight.js/styles/atom-one-dark.css';
import { prepareMermaidBlockSource, initializeMermaid } from './mermaid';

initializeMermaid();

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

const renderMathContent = (content: string, displayMode: boolean) => {
    try {
        let cleanedContent = content.trim();

        // Older model output sometimes escapes subscripts as `\_`. Normalize
        // only that known case; broad backslash stripping corrupts matrix row
        // separators (`\\`) and valid LaTeX spacing commands.
        cleanedContent = cleanedContent.replace(/\\_/g, '_');
        // JSON/prompt pipelines sometimes double-escape a command (`\\vec`,
        // `\\mathbf`) even though the surrounding `$...$` delimiters survive.
        // Restrict normalization to known commands: a generic "two slashes
        // before a letter" rule also matches a matrix row break followed by a
        // value (for example `a \\\\ b`) and corrupts valid environments.
        const doubledCommandRe = /(?<!\\)\\\\(?=(?:vec|mathbf|mathrm|mathit|mathbb|mathcal|mathsf|mathtt|text|frac|dfrac|tfrac|sqrt|left|right|begin|end|operatorname|overline|underline|hat|bar|dot|ddot|sum|prod|int|lim|log|ln|sin|cos|tan|exp|partial|nabla|infty|alpha|beta|gamma|delta|epsilon|theta|lambda|mu|pi|rho|sigma|tau|phi|psi|omega|Gamma|Delta|Theta|Lambda|Pi|Sigma|Phi|Psi|Omega)\b)/g;
        cleanedContent = cleanedContent.replace(doubledCommandRe, '\\');
        cleanedContent = cleanedContent.replace(/\\text\{([^{}]*)\}/g, (_match, text) => {
            return `\\text{${String(text).replace(/(^|[^\\])_/g, '$1\\_')}}`;
        });

        return katex.renderToString(cleanedContent, {
            throwOnError: true,
            displayMode,
            output: 'html',
            strict: false,
            trust: true
        });
    } catch {
        return `<code class="math-fallback">${md.utils.escapeHtml(content.trim())}</code>`;
    }
};

// Custom Math Plugin for KaTeX
const mathPlugin = (md: any) => {
    // Inline math rule ($...$ only)
    md.inline.ruler.after('escape', 'math_inline', (state: any, silent: boolean) => {
        const start = state.pos;
        if (state.src[start] !== '$') return false;

        // Reserve $$...$$ for the block rule. If inline parsing consumes the
        // first '$' of a multiline display block, the second '$' can be
        // reparsed and produce leaked delimiters or partial math tokens.
        if (start + 1 < state.posMax && state.src[start + 1] === '$') {
            return false;
        }

        let marker = '$';

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
            // No closing delimiter found - treat $ as literal character
            if (!silent) state.pending += '$';
            state.pos = start + 1;  // Only move past the single $
            return true;
        }

        if (silent) return true;

        const content = state.src.slice(start + markerLen, pos);
        
        // Heuristic: If content contains newlines, it might be a broken block.
        // But markdown-it inline usually doesn't span newlines unless breaks enabled.
        // My robust preprocessing ensures blocks are clean.
        
        const token = state.push('math_inline', 'math', 0);
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
        
        const trimmedFirstLine = firstLine.trim();

        // If single line $$...$$
        if (trimmedFirstLine.length > 4 && trimmedFirstLine.endsWith('$$')) {
            found = true;
        } else {
            // Multiline
            next++;
            while (next < end) {
                const line = state.src.slice(state.bMarks[next] + state.tShift[next], state.eMarks[next]);
                if (line.trim() === '$$') {
                    found = true;
                    break;
                }
                next++;
            }
        }

        if (!found) return false;
        if (silent) return true;

        const token = state.push('math_display_block', 'math', 0);
        let content = '';

        if (trimmedFirstLine.length > 4 && trimmedFirstLine.endsWith('$$')) {
            content = trimmedFirstLine.slice(2, -2).trim();
        } else {
            const contentLines: string[] = [];
            for (let lineNo = start + 1; lineNo < next; lineNo++) {
                const lineStart = state.bMarks[lineNo] + state.tShift[lineNo];
                const lineEnd = state.eMarks[lineNo];
                contentLines.push(state.src.slice(lineStart, lineEnd));
            }
            content = contentLines.join('\n').trim();
        }
        
        token.content = content.trim();
        token.map = [start, next + 1];
        token.markup = '$$';

        state.line = next + 1;
        return true;
    }, { alt: ['paragraph', 'reference', 'blockquote', 'list'] });

    md.renderer.rules.math_inline = (tokens: any, idx: number) => {
        return renderMathContent(tokens[idx].content, false);
    };
    
    md.renderer.rules.math_display = (tokens: any, idx: number) => {
        return renderMathContent(tokens[idx].content, true);
    };

    md.renderer.rules.math_display_block = (tokens: any, idx: number) => {
        return '<div class="katex-display">' + renderMathContent(tokens[idx].content, true) + '</div>';
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
    const code = prepareMermaidBlockSource(token.content);

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
const DISPLAY_MATH_ENVIRONMENTS = 'bmatrix|pmatrix|vmatrix|Bmatrix|Vmatrix|matrix|array|aligned|split|cases|equation|gather'

// AI-generated lessons frequently contain correct LaTeX environments wrapped
// in malformed runs such as $$$ / $$$$. Normalize each balanced environment
// independently so one broken delimiter cannot corrupt formulas later in the
// same long lesson.
const normalizeBalancedDisplayEnvironments = (content: string) => {
    const environmentRe = new RegExp(
        `\\$*\\s*(\\\\begin\\{(${DISPLAY_MATH_ENVIRONMENTS})\\}[\\s\\S]*?\\\\end\\{\\2\\})\\s*\\$*`,
        'g'
    );
    return content.replace(environmentRe, (match, environment, _name, offset) => {
        // Earlier normalization may have promoted an inline outer expression
        // such as `span(left($$ matrix $$)right))` to one valid display block.
        // Do not wrap its balanced matrix environments a second time.
        const prefix = content.slice(0, Number(offset));
        const displayDelimiterCount = (prefix.match(/\$\$/g) || []).length;
        if (displayDelimiterCount % 2 === 1) return match;
        return `\n$$\n${String(environment).trim()}\n$$\n`;
    });
};

// Some generated legacy lessons wrap an otherwise valid `$$ environment $$`
// block with lines containing a single `$`.  That creates nested delimiters
// which Markdown parses as code, headings, or leaked dollar signs.  Remove
// only this exact invalid shell, then merge an immediately preceding display
// prefix such as `\vec{v} =` into the same formula.
const normalizeLegacyDisplayShells = (content: string) => {
    const prefixedShellRe = new RegExp(
        `(^|\\n)[\\t ]*\\$\\$[\\t ]*\\n([^\\n$]+(?:\\n[^\\n$]+){0,2})\\n[\\t ]*\\$[\\t ]*\\n[\\t ]*\\$\\$[\\t ]*\\n(\\\\begin\\{(${DISPLAY_MATH_ENVIRONMENTS})\\}[\\s\\S]*?\\\\end\\{\\4\\})[\\t ]*\\n[\\t ]*\\$\\$[\\t ]*\\n[\\t ]*\\$(?=\\n|$)`,
        'g'
    );
    let normalized = content.replace(prefixedShellRe, (_match, boundary, prefix, environment) => (
        `${boundary}\n$$\n${String(prefix).trim()}\n${String(environment).trim()}\n$$`
    ));
    const shellRe = new RegExp(
        `(^|\\n)[\\t ]*\\$[\\t ]*\\n[\\t ]*\\$\\$[\\t ]*\\n(\\\\begin\\{(${DISPLAY_MATH_ENVIRONMENTS})\\}[\\s\\S]*?\\\\end\\{\\3\\})[\\t ]*\\n[\\t ]*\\$\\$[\\t ]*\\n[\\t ]*\\$(?=\\n|$)`,
        'g'
    );
    normalized = normalized.replace(shellRe, (_match, boundary, environment) => (
        `${boundary}\n$$\n${String(environment).trim()}\n$$`
    ));
    const prefixedEnvironmentRe = new RegExp(
        `\\$\\$[\\t ]*\\n([^\\n$]*(?:\\n[^\\n$]*){0,2})\\n[\\t ]*\\$\\$[\\t ]*\\n(\\\\begin\\{(${DISPLAY_MATH_ENVIRONMENTS})\\}[\\s\\S]*?\\\\end\\{\\3\\})[\\t ]*\\n[\\t ]*\\$\\$`,
        'g'
    );
    normalized = normalized.replace(prefixedEnvironmentRe, (_match, prefix, environment) => (
        `$$\n${String(prefix).trim()}\n${String(environment).trim()}\n$$`
    ));
    const adjacentEnvironmentRe = new RegExp(
        `\\$\\$[\\t ]*\\n(\\\\begin\\{(${DISPLAY_MATH_ENVIRONMENTS})\\}[\\s\\S]*?\\\\end\\{\\2\\})[\\t ]*\\n[\\t ]*\\$\\$[\\t ]*\\n[\\t ]*([+\\-=])?[\\t ]*\\n[\\t ]*\\$\\$[\\t ]*\\n(\\\\begin\\{(${DISPLAY_MATH_ENVIRONMENTS})\\}[\\s\\S]*?\\\\end\\{\\5\\})[\\t ]*\\n[\\t ]*\\$\\$`,
        'g'
    );
    normalized = normalized.replace(adjacentEnvironmentRe, (_match, left, _leftName, operator, right) => (
        `$$\n${String(left).trim()}\n${String(operator || '').trim()}\n${String(right).trim()}\n$$`
    ));
    return normalized;
};

// Historical lessons sometimes put `$$ matrix $$` blocks inside a surrounding
// `$\text{span}\left(...\right)$` formula. Nested dollar delimiters are not a
// valid math grammar and can make placeholder recovery swallow the rest of the
// paragraph. Remove only environment-local inner delimiters, then promote the
// complete multiline outer expression to one display formula.
const normalizeNestedDisplayEnvironments = (content: string) => {
    const sizedGroupRe = /\\left([\s\S]*?)\\right/g;
    let normalized = content.replace(sizedGroupRe, group => group.replace(
        new RegExp(`\\$\\$\\s*(\\\\begin\\{(?:${DISPLAY_MATH_ENVIRONMENTS})\\}[\\s\\S]*?\\\\end\\{(?:${DISPLAY_MATH_ENVIRONMENTS})\\})\\s*\\$\\$`, 'g'),
        (_match, environment) => String(environment).trim()
    ));

    const multilineInlineEnvironmentRe = new RegExp(
        `(?<!\\$)\\$([^$]*?\\\\begin\\{(?:${DISPLAY_MATH_ENVIRONMENTS})\\}[\\s\\S]*?\\\\end\\{(?:${DISPLAY_MATH_ENVIRONMENTS})\\}[^$]*?)\\$(?!\\$)`,
        'g'
    );
    normalized = normalized.replace(multilineInlineEnvironmentRe, (_match, formula) => `\n$$\n${String(formula).trim()}\n$$\n`);
    return normalized;
};

const protectBalancedDisplayEnvironments = (content: string) => {
    const blocks = new Map<string, string>();
    let index = 0;
    const environmentRe = new RegExp(
        `(\\\\begin\\{(${DISPLAY_MATH_ENVIRONMENTS})\\}[\\s\\S]*?\\\\end\\{\\2\\})`,
        'g'
    );
    let normalized = content.replace(environmentRe, (_match, environment) => {
        const id = `MATHDISPLAYPLACEHOLDER${index++}`;
        blocks.set(id, `<div class="katex-display">${renderMathContent(String(environment), true)}</div>`);
        return `\n\n${id}\n\n`;
    });

    // Remove only display-sized dollar runs next to a protected block. A
    // single `$` may still be the legitimate end of an inline prefix (`$A =$`).
    normalized = normalized.replace(/(?:\${2,}\s*)+(MATHDISPLAYPLACEHOLDER\d+)/g, (_match, id) => `\n${id}`);
    normalized = normalized.replace(/(MATHDISPLAYPLACEHOLDER\d+)(?:\s*\${2,})+/g, (_match, id) => `${id}\n`);

    return { normalized, blocks };
};

const recoverProtectedMathBlocks = (rawHtml: string, blocks: Map<string, string>) => {
    let recovered = rawHtml;
    blocks.forEach((html, id) => {
        recovered = recovered.replace(new RegExp(`<p>\\s*${id}\\s*</p>`, 'g'), () => html);
        recovered = recovered.replace(new RegExp(id, 'g'), () => html);
    });

    // A malformed outer delimiter can make KaTeX split a placeholder across
    // many spans. Recover the whole swallowed shell and replace it with all
    // protected environments found inside that shell.
    const container = document.createElement('div');
    container.innerHTML = recovered;
    for (const id of blocks.keys()) {
        if (!container.textContent?.includes(id)) continue;

        const candidate = Array.from(container.querySelectorAll<HTMLElement>('*'))
            .filter(element => element.textContent?.includes(id))
            .sort((left, right) => (left.textContent?.length || 0) - (right.textContent?.length || 0))[0];
        if (!candidate) continue;

        const target = candidate.closest<HTMLElement>('.math-fallback, .katex')?.closest<HTMLElement>('.katex-display')
            || candidate.closest<HTMLElement>('.math-fallback, .katex')
            || candidate;
        const swallowedIds = Array.from(target.textContent?.matchAll(/MATHDISPLAYPLACEHOLDER\d+/g) || [], match => match[0]);
        const template = document.createElement('template');
        template.innerHTML = swallowedIds.map(swallowedId => blocks.get(swallowedId) || '').join('');
        target.replaceWith(template.content);
    }
    return container.innerHTML;
};

const fallbackResidualMathMarkup = (html: string) => {
    const container = document.createElement('div');
    container.innerHTML = html;
    const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
    const leakedNodes: Text[] = [];
    let current: Node | null;
    while ((current = walker.nextNode())) {
        const parent = current.parentElement;
        // KaTeX keeps the original TeX inside an annotation node. It is
        // expected to contain commands such as `\begin`; treating that hidden
        // source as leaked markup replaces a successfully rendered formula
        // with a fallback block.
        if (!parent || parent.closest('code, pre, annotation, .math-fallback, .mermaid, .katex, .katex-display')) continue;
        if (/MATHDISPLAYPLACEHOLDER\d+|\\(?:begin|end|frac|left|right|mathbf|mathbb)\b|\$\$/.test(current.textContent || '')) {
            leakedNodes.push(current as Text);
        }
    }
    leakedNodes.forEach(node => {
        if ((node.textContent || '').trim() === '$$') {
            node.remove();
            return;
        }
        const fallback = document.createElement('code');
        fallback.className = 'math-fallback';
        fallback.textContent = (node.textContent || '').replace(/\$\$/g, '');
        node.replaceWith(fallback);
    });
    return container.innerHTML;
};

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
const hasExplicitMarkdownStructure = (line: string): boolean => {
    const trimmed = line.trim();
    if (!trimmed) return false;

    // Markdown syntax is an authoring contract, not formula source. Naked-math
    // recovery must never reinterpret the delimiters or destinations of these
    // structures. Explicit $...$ formulas have already been masked, so opting
    // out here does not prevent formulas inside tables or link labels.
    const isTableRow = /^\|.*\|\s*$/.test(trimmed)
        || (trimmed.match(/(?<!\\)\|/g)?.length || 0) >= 2;
    const hasLinkOrImage = /!?\[[^\]\n]+\]\([^)]+\)|\[[^\]\n]+\]\[[^\]\n]*\]|^\[[^\]\n]+\]:\s*\S+/.test(trimmed);
    const hasRawHtml = /<\/?[A-Za-z][^>]*>/.test(trimmed);
    const hasExplicitInlineStyle = /\*\*[^*\n]+\*\*|(?<!\*)\*[^*\n]+\*(?!\*)|~~[^~\n]+~~/.test(trimmed);

    return isTableRow || hasLinkOrImage || hasRawHtml || hasExplicitInlineStyle;
};

const splitNakedFormulaFromProse = (text: string): { formula: string; prose: string } | null => {
    const proseBoundary = findTopLevelCjkBoundary(text);
    if (proseBoundary === 0) return null;

    const formula = (proseBoundary > 0 ? text.slice(0, proseBoundary) : text).trimEnd();
    if (!isLikelyMath(formula)) return null;

    return {
        formula: formula.trim(),
        prose: proseBoundary > 0 ? text.slice(proseBoundary) : '',
    };
};

const splitNakedFormulaInsideProse = (text: string): { prefix: string; formula: string; suffix: string } | null => {
    if (!/[\u3400-\u9fff]/.test(text)) return null;

    const commandStart = text.search(/\\[A-Za-z]+/);
    const assignmentStart = text.search(/\b[A-Za-z][A-Za-z0-9]*(?:[_^]\{?[A-Za-z0-9]+\}?)?\s*=/);
    const starts = [commandStart, assignmentStart].filter(index => index > 0);
    if (starts.length === 0) return null;

    const start = Math.min(...starts);
    const tail = text.slice(start);
    const proseBoundary = findTopLevelCjkBoundary(tail);
    const rawFormula = proseBoundary > 0 ? tail.slice(0, proseBoundary) : tail;
    const punctuation = rawFormula.match(/[，。；：！？、\s]+$/)?.[0] || '';
    const formula = rawFormula.slice(0, rawFormula.length - punctuation.length).trim();
    if (!isLikelyMath(formula)) return null;

    return {
        prefix: text.slice(0, start),
        formula,
        suffix: `${punctuation}${proseBoundary > 0 ? tail.slice(proseBoundary) : ''}`,
    };
};

const detectAndWrapNakedMathLines = (content: string, maskIdRef: {val: number}, maskMap: Map<string, string>): string => {
    return content.split('\n').map(line => {
        // Skip masked lines or empty lines
        if (line.includes('__MATH') || line.includes('__CODE') || !line.trim()) return line;
        if (hasExplicitMarkdownStructure(line)) return line;
        
        // Skip lines that look like headers, lists, or blockquotes
        if (line.match(/^(\s*)(#{1,6}|-|\*|\d+\.|>)\s/)) {
            const contentMatch = line.match(/^(\s*(?:#{1,6}|-|\*|\d+\.|>)\s+)(.*)$/);
            if (contentMatch) {
                const marker = contentMatch[1];
                const rest = contentMatch[2];
                const parts = rest ? splitNakedFormulaFromProse(rest) : null;
                if (marker && parts) {
                    const id = `__MATH_INLINE_AUTO_${maskIdRef.val++}__`;
                    maskMap.set(id, `$${parts.formula}$`);
                    return `${marker}${id}${parts.prose}`;
                }
                const inlineParts = rest ? splitNakedFormulaInsideProse(rest) : null;
                if (marker && inlineParts) {
                    const id = `__MATH_INLINE_AUTO_${maskIdRef.val++}__`;
                    maskMap.set(id, `$${inlineParts.formula}$`);
                    return `${marker}${inlineParts.prefix}${id}${inlineParts.suffix}`;
                }
            }
            return line;
        }

        // A frequent model format is a delimiter-free equation immediately
        // followed by Chinese explanation. Sending the whole line to KaTeX
        // either turns prose into math italics or makes the complete line fall
        // back to raw source. Split only at a top-level CJK boundary so Chinese
        // inside `\text{...}` remains part of the formula.
        const leadingWhitespace = line.match(/^\s*/)?.[0] || '';
        const parts = splitNakedFormulaFromProse(line.slice(leadingWhitespace.length));
        if (parts) {
            const id = `__MATH_BLOCK_AUTO_${maskIdRef.val++}__`;
            maskMap.set(id, `\n$$\n${parts.formula}\n$$\n`);
            return `${leadingWhitespace}${id}${parts.prose}`;
        }

        const inlineParts = splitNakedFormulaInsideProse(line);
        if (inlineParts) {
            const id = `__MATH_INLINE_AUTO_${maskIdRef.val++}__`;
            maskMap.set(id, `$${inlineParts.formula}$`);
            return `${inlineParts.prefix}${id}${inlineParts.suffix}`;
        }
        
        return line;
    }).join('\n');
};

const findTopLevelCjkBoundary = (text: string): number => {
    let braceDepth = 0;
    for (let index = 0; index < text.length; index++) {
        const char = text[index];
        if (char === '{' && text[index - 1] !== '\\') braceDepth++;
        if (char === '}' && text[index - 1] !== '\\') braceDepth = Math.max(0, braceDepth - 1);
        if (braceDepth === 0 && char && /[\u3400-\u9fff]/.test(char)) return index;
    }
    return -1;
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
            ADD_TAGS: ['math-field'], 
            ADD_ATTR: ['target']
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
    normalized = normalizeNestedDisplayEnvironments(normalized);
    normalized = normalizeLegacyDisplayShells(normalized);
    normalized = normalized.replace(/\$\$\s*([=+\-])\s*\$\$/g, (_match, op) => `$$\n${op}\n$$`);
    // Recover the common model output `$A =$$$\begin{...}` as one inline
    // prefix followed by a display environment. Do not start inside `$$`.
    normalized = normalized.replace(/(?<!\$)\$([^\$\n]+?)\${2,}(?=\\begin\{)/g, (_match, inline) => `$${inline.trim()}$\n$$`);
    // Four dollars can mean "close display + open the next display", but only
    // when the next token is unquestionably mathematical. Treat `- $R_2...`
    // and ordinary prose as Markdown/text, not as a new display formula.
    normalized = normalized.replace(/\${4,}(?=\s*(?:=|\\begin\{))/g, (_match, offset, full) => {
        const before = full.slice(Math.max(0, offset - 24), offset);
        return /(\\right|\\end\{[a-zA-Z0-9*]+\}|[)\]}])\s*$/.test(before) ? '$$\n$$' : '\n$$';
    });
    normalized = normalized.replace(/\${3,}/g, () => '$$');

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
        // Keep the same `__CODE` prefix as fenced-code placeholders. The
        // naked-math detector skips protected code lines; using the old
        // `__INLINE_CODE` prefix exposed placeholder underscores to its math
        // heuristics and turned Markdown such as `**t=0** ... \`θ(0)\`` into
        // one malformed formula.
        const id = `__CODE_INLINE_${codeBlockId++}__`;
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
    const blockEnvs = DISPLAY_MATH_ENVIRONMENTS;
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
    // NOTE: Must use a function replacement to avoid $$ being interpreted as
    // a special replacement pattern (literal $) by String.prototype.replace.
    for (let pass = 0; pass < 3; pass++) {
        let changed = false;
        mathMaskMap.forEach((value, key) => {
            if (!normalized.includes(key)) return;
            normalized = normalized.replace(key, () => value);
            changed = true;
        });
        if (!changed) break;
    }
    normalized = normalized.replace(/\${3,}/g, () => '$$');
    const displayEnvRe = DISPLAY_MATH_ENVIRONMENTS;
    normalized = normalized.replace(new RegExp(`\\$\\$(\\\\begin\\{(?:${displayEnvRe})\\})`, 'g'), (_match, begin) => `$$\n${begin}`);
    normalized = normalized.replace(new RegExp(`(\\\\end\\{(?:${displayEnvRe})\\})\\$\\$`, 'g'), (_match, end) => `${end}\n$$\n`);

    // Normalize LaTeX delimiters for compatibility
    // Replace \[ ... \] with $$ ... $$
    normalized = normalized.replace(/\\\[([\s\S]*?)\\\]/g, (_match, content) => {
        return `\n$$\n${String(content).trim()}\n$$\n`;
    });
    // Replace \( ... \) with $ ... $ (Inline math)
    normalized = normalized.replace(/\\\(([\s\S]*?)\\\)/g, (_match, content) => {
        return `$${String(content).trim()}$`;
    });
    
    // Normalize single-line display math into a block form. Existing multiline
    // $$ blocks were already masked and restored, so avoid rewriting them again.
    normalized = normalized.replace(/\$\$([^\n$][^\n]*?)\$\$/g, (_match, content) => {
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

    normalized = normalizeBalancedDisplayEnvironments(normalized)
    const protectedDisplayMath = protectBalancedDisplayEnvironments(normalized)
    normalized = protectedDisplayMath.normalized
    normalized = normalized.replace(
        /(MATHDISPLAYPLACEHOLDER\d+)\s*\n\s*([+\-=])\s*\n\s*(MATHDISPLAYPLACEHOLDER\d+)/g,
        (_match, left, operator, right) => `${left}\n\n$${operator}$\n\n${right}`
    )


    // NOTE: Do not run additional auto-wrapping heuristics after restoring valid
    // math delimiters. They can mistakenly re-wrap already-correct imported
    // formulas and cause red error spans, leaked delimiters, or missing inline math.

    let sanitized = ''
    try {
        // Restore code blocks before rendering? 
        // No, markdown-it needs to see the code blocks to render them as code.
        // So we must restore them now.
        // NOTE: Must use function replacement to avoid $ special patterns in String.replace.
        codeBlockMap.forEach((value, key) => {
             normalized = normalized.replace(key, () => value);
        });

        const rawHtml = recoverProtectedMathBlocks(md.render(normalized), protectedDisplayMath.blocks);
        sanitized = DOMPurify.sanitize(rawHtml, {
            ADD_TAGS: ['span', 'div', 'p', 'button', 'math', 'semantics', 'mrow', 'mi', 'mo', 'mn', 'msup', 'msub', 'mfrac', 'msqrt', 'mtable', 'mtr', 'mtd', 'table', 'thead', 'tbody', 'tr', 'th', 'td'],
            ADD_ATTR: ['target', 'class', 'xmlns', 'display', 'mathvariant', 'loading', 'data-code', 'title']
        });
        sanitized = fallbackResidualMathMarkup(sanitized);
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
